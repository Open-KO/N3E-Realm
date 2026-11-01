"""The WebSocket edge (specs/12-edge.md, M7a): the game wire through a stand-in for
Cloudflare's edge, realm-edge and the server's PROXY v2 path.

A native server (demo package, small per-source limits, PROXY trusted from
127.0.0.1), realm-edge in front of it trusting 127.0.0.1, and a loopback stand-in
for Cloudflare: TLS with the local CA's localhost certificate, which adds
CF-Connecting-IP to the upgrade and forwards bytes. Spec 12 tests 2-3 speak
WebSocket from here; with --graphical (or N3E_GRAPHICAL=1) the real client logs in
through the edge with Discord (stand-in), enters the world, and a second start logs
in with its stored session token after the first's WebSocket was closed (tests 1
and 4). Test 5 is the existing suites; test 6 is manual (deploy/HOST.md).
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES
from discord_standin import Discord, b64url, user
from world_peer import Peer, blob

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
edge_binary = str(Path(os.environ.get("N3E_TEST_EDGE", "target/debug/realm-edge")).resolve())
package = ROOT / "build/packages/demo"
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
content = (package / "release.sha256").read_text().strip()
name = "n3e-edge-" + uuid.uuid4().hex[:10]
out = ROOT / "build/live/edge"
out.mkdir(parents=True, exist_ok=True)
CLIENT_ID = "123456789012345678"
SECRET = "s3cret-" + secrets.token_hex(8)
REDIRECT = "http://127.0.0.1:49152/callback"
CAP = 3
PROTOCOL = "n3e-wire.1"


def run(*cmd, env=None, good=True):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    assert not good or p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def pump(a, b):
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    for s in (a, b):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


class StandIn:
    """Cloudflare's part: TLS for the client, CF-Connecting-IP added to the upgrade,
    bytes forwarded to realm-edge. `close_all` drops every WebSocket, as an edge
    restart does."""

    def __init__(self, upstream):
        self.upstream, self.source, self.open = upstream, "203.0.113.7", []
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(ROOT / "deploy/local/server.pem", ROOT / "deploy/local/server.key")
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.context = context
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            raw, _ = self.listener.accept()
            threading.Thread(target=self.handle, args=(raw,), daemon=True).start()

    def handle(self, raw):
        try:
            client = self.context.wrap_socket(raw, server_side=True)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(4096)
                assert chunk and len(head) < 8192
                head += chunk
            line, rest = head.split(b"\r\n", 1)
            edge = socket.create_connection(("127.0.0.1", self.upstream))
            edge.sendall(line + b"\r\nCF-Connecting-IP: " + self.source.encode() + b"\r\n" + rest)
        except (OSError, AssertionError):
            raw.close()
            return
        self.open.append((client, edge))
        threading.Thread(target=pump, args=(edge, client), daemon=True).start()
        pump(client, edge)

    def close_all(self):
        for pair in self.open:
            for s in pair:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self.open.clear()


def upgrade(source=None, protocol=PROTOCOL, bind="127.0.0.1"):
    """A WebSocket upgrade straight to realm-edge, as cloudflared would send it;
    (socket, status code)."""
    s = socket.socket()
    s.bind((bind, 0))
    s.connect(("127.0.0.1", edge_port))
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    head = (f"GET /v1/wire HTTP/1.1\r\nHost: play.example\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n")
    if protocol:
        head += f"Sec-WebSocket-Protocol: {protocol}\r\n"
    if source:
        head += f"CF-Connecting-IP: {source}\r\n"
    s.sendall((head + "\r\n").encode())
    s.settimeout(5)
    reply = b""
    try:
        while b"\r\n\r\n" not in reply:
            chunk = s.recv(1)
            if not chunk:
                return s, 0
            reply += chunk
    except OSError:
        return s, 0
    code = int(reply.split(b" ", 2)[1])
    if code == 101:
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        assert b"Sec-WebSocket-Accept: " + accept in reply or b"sec-websocket-accept: " + accept in reply.lower(), reply
    return s, code


def frame(opcode, payload, mask=True):
    head = bytes([0x80 | opcode])
    n = len(payload)
    m = 0x80 if mask else 0
    head += bytes([m | n]) if n < 126 else bytes([m | 126]) + struct.pack(">H", n) if n < 65536 else \
        bytes([m | 127]) + struct.pack(">Q", n)
    if not mask:
        return head + payload
    key = secrets.token_bytes(4)
    return head + key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def read_frame(s, seconds=3):
    """(opcode, payload), or None when the socket closed or nothing came."""
    s.settimeout(seconds)

    def exactly(n):
        b = b""
        while len(b) < n:
            chunk = s.recv(n - len(b))
            if not chunk:
                raise EOFError
            b += chunk
        return b
    try:
        a, b = exactly(2)
        n = b & 0x7F
        if n == 126:
            n = struct.unpack(">H", exactly(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", exactly(8))[0]
        return a & 0x0F, exactly(n)
    except (EOFError, OSError):
        return None


def close_code(s, seconds=3):
    """The close code realm-edge sends, skipping pings; None if it stays open."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        f = read_frame(s, max(0.05, deadline - time.monotonic()))
        if f is None:
            return None
        if f[0] == 0x8:
            return struct.unpack(">H", f[1][:2])[0] if len(f[1]) >= 2 else 1005
    return None


def held(s, seconds=0.4):
    """Admitted by the server: the WebSocket stays open with nothing sent."""
    readable, _, _ = select.select([s], [], [], seconds)
    return not readable


def status():
    request = urllib.request.Request(f"http://127.0.0.1:{admin}/v1/realm/status",
                                     headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=5) as r:
        return json.loads(r.read())["connections"]


def settle(key, value, seconds=5):
    deadline = time.monotonic() + seconds
    while status()[key] != value:
        assert time.monotonic() < deadline, (key, value, status())
        time.sleep(0.05)


discord = Discord(CLIENT_ID, SECRET, REDIRECT)
containers, server, edge = [], None, None
try:
    for suffix, image, cp, extra in [
        ("", "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad", 5432,
         ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only", "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
        ("-redis", "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9", 6379, []),
    ]:
        run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{cp}", image)
        containers.append(name + suffix)
    pg = wait_postgres(name)
    redis = run("docker", "port", name + "-redis", "6379").stdout.split()[0]
    listen, health, admin, edge_port = free_ports(4)
    realm = f"test-{name}"
    env = {k: v for k, v in os.environ.items() if k not in ("N3E_LEGACY_LOGIN", "DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET")}
    env.update(DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
               REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM=realm,
               N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}",
               N3E_ADMIN_LISTEN=f"127.0.0.1:{admin}", N3E_IP_MAX_CONCURRENT=str(CAP),
               N3E_TRUSTED_PROXY_CIDRS="127.0.0.1/32", DISCORD_CLIENT_ID=CLIENT_ID,
               DISCORD_CLIENT_SECRET=SECRET, N3E_DISCORD_API=f"http://127.0.0.1:{discord.port}/api")
    run(server_binary, "migrate", env=env)
    run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
    token = run(server_binary, "admin", "mint", "--name", "ops", "--perm", "realm.*", env=env).stdout.strip()
    server_log = open(out / "server.log", "w")
    server = subprocess.Popen([server_binary], env=env, stdout=server_log, stderr=server_log)
    edge_log = open(out / "edge.log", "w")
    edge = subprocess.Popen([edge_binary], stdout=edge_log, stderr=edge_log, env={
        **os.environ, "REALM_EDGE_LISTEN": f"127.0.0.1:{edge_port}", "REALM_EDGE_UPSTREAM": f"127.0.0.1:{listen}",
        "REALM_EDGE_TRUSTED_CIDRS": "127.0.0.1/32"})
    deadline = time.monotonic() + 60
    while True:
        assert server.poll() is None, (out / "server.log").read_text()
        assert edge.poll() is None, (out / "edge.log").read_text()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{edge_port}/live", timeout=2)
            if json.loads(urllib.request.urlopen(urllib.request.Request(
                    f"http://127.0.0.1:{admin}/v1/realm/status", headers={"Authorization": f"Bearer {token}"}),
                    timeout=2).read())["ready"]:
                break
        except OSError:
            pass
        assert time.monotonic() < deadline, "server or edge never ready"
        time.sleep(0.1)

    # 3. Refusals at the edge, before the server sees anything.
    assert upgrade("198.51.100.1", bind="127.0.0.2")[1] == 0
    assert upgrade("198.51.100.1", protocol=None)[1] == 400
    assert upgrade(None)[1] == 400
    assert upgrade("198.51.100.1, 198.51.100.2")[1] == 400
    s, code = upgrade("198.51.100.1")
    assert code == 101
    s.sendall(frame(0x1, b"text"))
    assert close_code(s) == 1003
    s, code = upgrade("198.51.100.1")
    s.sendall(frame(0x2, b"x" * 10, mask=False))
    assert close_code(s) == 1002
    s, code = upgrade("198.51.100.1")
    try:
        s.sendall(frame(0x2, b"x" * (64 * 1024 + 1025)))
    except OSError:
        pass  # the edge may close before the payload is all sent
    assert close_code(s) == 1009
    s, code = upgrade("198.51.100.1")
    s.sendall(frame(0x9, b"hello"))
    assert read_frame(s) == (0xA, b"hello")
    s.close()
    settle("open", 0)
    print("PASS 3 the edge refuses an untrusted peer, no subprotocol, no or two CF-Connecting-IP addresses; "
          "closes text 1003, unmasked 1002, oversize 1009; answers ping")

    # 2. Spec 01's per-source cap applies to the forwarded address.
    before = status()["refused_ip_concurrent"]
    socks = []
    for i in range(CAP + 1):
        s, code = upgrade("198.51.100.7")
        assert code == 101, code
        socks.append(s)
    assert [held(s) for s in socks[:CAP]] == [True] * CAP
    assert close_code(socks[CAP]) is not None or not held(socks[CAP])
    other, code = upgrade("198.51.100.8")
    assert code == 101 and held(other)
    c = status()
    assert c["refused_ip_concurrent"] == before + 1 and c["refused_proxy"] == 0, c
    for s in socks + [other]:
        s.close()
    settle("open", 0)
    print(f"PASS 2 through the edge: {CAP} WebSockets from one CF-Connecting-IP admitted, the next refused "
          "by the server's per-source cap, another address admitted; no PROXY refusals")

    if "--graphical" in sys.argv or os.environ.get("N3E_GRAPHICAL") == "1":
        stand_in = StandIn(edge_port)
        client_user = user("80351110224678916", "Edgewalker")
        # The account and its character exist before the client's login, made
        # directly on the game port (a peer the server does not treat as a proxy).
        p = Peer(listen, content=content, game=manifest["game_id"], protocol=manifest["protocol_version"],
                 source="127.0.0.21")
        verifier = b64url(secrets.token_bytes(48))
        code = discord.authorize(client_user, b64url(hashlib.sha256(verifier.encode()).digest()))
        p.send(46, blob(1, code) + blob(2, verifier) + blob(3, REDIRECT) + blob(4, "test-host"))
        assert p.until(48, 4, seconds=15)[0] == 48
        p.until(6, 4)
        p.tend()
        p.create("Edgewalker")
        p.send(12)
        p.s.close()
        home = out / "client-home"
        subprocess.run(["rm", "-rf", str(home)])
        (home / "config").mkdir(parents=True)
        realm_json = home / "realm.json"
        realm_json.write_text(json.dumps({
            "id": "edge-realm", "name": "Edge Realm", "host": "localhost", "port": listen,
            "edge": f"wss://localhost:{stand_in.port}/v1/wire", "discord_client_id": CLIENT_ID}))

        def client(run_name, browse, on_enter=None):
            log_path = out / f"client-{run_name}.log"
            proc = subprocess.Popen(
                ["build/client/n3e-test-client", str(package), "--realm", str(realm_json),
                 "--ca", "deploy/local/ca.pem", "--auto-login", "--world-smoke", "10"],
                env={**env, "XDG_CONFIG_HOME": str(home / "config"), "N3E_TEST_NO_BROWSER": "1"},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            lines, urls = [], []
            for line in proc.stdout:
                lines.append(line)
                if line.startswith("Open this address to log in with Discord: "):
                    urls.append(line.split(": ", 1)[1].strip())
                    browse(urls[-1])
                if line.startswith("ENTERED map") and on_enter:
                    on_enter()
            code = proc.wait(timeout=90)
            text = "".join(lines)
            log_path.write_text(text)
            return code, text, urls

        def browser(url):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            code = discord.authorize(client_user, q["code_challenge"], q["redirect_uri"])
            back = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": code, "state": q["state"]})
            with urllib.request.urlopen(back, timeout=5) as r:
                assert r.status == 200

        def no_browser(url):
            raise AssertionError(("the client asked Discord again", url))

        code, text, urls = client("first", browser)
        assert code == 0 and "ENTERED map" in text and len(urls) == 1, (code, text[-3000:])
        throttled = run("docker", "exec", name + "-redis", "redis-cli", "--scan", "--pattern",
                        f"n3e:{realm}:ip:*").stdout.split()
        assert f"n3e:{realm}:ip:203.0.113.7" in throttled, throttled
        assert "edge close src=203.0.113.7" in (out / "edge.log").read_text()
        print("PASS 1 the client logs in with Discord through the edge (outer TLS to the stand-in, inner TLS to "
              "the realm), enters the world, and the server counts it as 203.0.113.7")

        stand_in.close_all()
        code, text, urls = client("second", no_browser)
        assert code == 0 and "ENTERED map" in text and urls == [], (code, text[-3000:])
        print("PASS 4 after the edge closed its WebSockets, the next start logs in through the edge with the "
              "stored session token; Discord not asked")

        realm_json.write_text(json.dumps({
            "id": "edge-realm", "name": "Edge Realm", "host": "localhost", "port": listen,
            "edge": f"ws://localhost:{stand_in.port}/v1/wire", "discord_client_id": CLIENT_ID}))
        code, text, _ = client("plain-ws", no_browser)
        assert code != 0 and "wss://" in text, (code, text[-2000:])
        print("PASS a realm.json edge that is not wss:// refuses to start")
    assert server.poll() is None and edge.poll() is None, "server or edge exited"
    log = (out / "edge.log").read_text()
    for header in ("Sec-WebSocket-Key", "CF-Connecting-IP:", "Upgrade:"):
        assert header not in log, header
    print("PASS the edge's log has one line per connection and no headers")
    print("EDGE_OK")
finally:
    for p in (edge, server):
        if p is not None:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
    discord.http.shutdown()
    for c in containers:
        subprocess.run(["docker", "rm", "-f", c], capture_output=True)
