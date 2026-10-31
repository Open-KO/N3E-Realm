"""The Discord bot (specs/05-bot.md, roadmap M6).

Starts the native server against a disposable Postgres and Redis, then `realm-bot`
against stand-ins on loopback: a Discord gateway (`DISCORD_GATEWAY_PROXY`, a minimal
WebSocket server speaking HELLO/IDENTIFY/READY and pushing INTERACTION_CREATE), Discord's
REST API (`DISCORD_API_PROXY`: command registration, interaction replies, channel
posts) and GitHub's Actions API (`GITHUB_API`). Interactions are sent the way Discord
sends them; replies and channel posts are read back from the REST stand-in.

Covers spec 05 acceptance tests 1-4, 6-10 against the real admin API and event stream.
Tests 5 and 5b need the world routes (M5/M5b): here the world commands are checked to
reach their routes and report "not supported yet", and autocomplete to say the catalog
is unavailable. The manual run against a real test guild is not part of this suite.
"""
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
bot_binary = str(Path(os.environ.get("N3E_TEST_BOT", "target/debug/realm-bot")).resolve())
package = ROOT / "build/packages/demo"
name = "n3e-bot-" + uuid.uuid4().hex[:10]
out = ROOT / "build/live/bot"
out.mkdir(parents=True, exist_ok=True)

GUILD, ANNOUNCE, OPS_CHANNEL = "100000000000000001", "100000000000000002", "100000000000000003"
ROLE_MOD, ROLE_OPS, APP = "100000000000000004", "100000000000000005", "100000000000000006"
OTHER_ROLE = "100000000000000007"
BOT_TOKEN = "discord-bot-" + secrets.token_urlsafe(24)
PAT = "github_pat_" + secrets.token_urlsafe(24)
NELLY = "80351110224678912"
UNAVAILABLE = "Realm admin API unavailable — the server is probably restarting. Try again in a minute."
NOT_YET = "This realm does not support that yet (the admin API route has not landed)."


def run(*cmd, env=None, good=True, stdin=None):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120, input=stdin)
    assert not good or p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def wait(predicate, seconds, what):
    deadline = time.monotonic() + seconds
    while True:
        value = predicate()
        if value:
            return value
        assert time.monotonic() < deadline, what
        time.sleep(0.05)


class WebSocket:
    """The server end of one RFC 6455 connection: text frames out, masked frames in."""

    def __init__(self, sock):
        self.sock = sock
        self.lock = threading.Lock()
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = sock.recv(4096)
            assert chunk, "closed during the handshake"
            request += chunk
        lines = request.decode().split("\r\n")
        self.path = lines[0].split(" ")[1]
        key = next(l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("sec-websocket-key:"))
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        sock.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n")

    def frame(self, opcode, payload):
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([n])
        elif n < 65536:
            head += bytes([126]) + n.to_bytes(2, "big")
        else:
            head += bytes([127]) + n.to_bytes(8, "big")
        with self.lock:
            self.sock.sendall(head + payload)

    def send(self, message):
        self.frame(1, json.dumps(message).encode())

    def close(self, code):
        self.frame(8, code.to_bytes(2, "big"))

    def exactly(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise EOFError
            data += chunk
        return data

    def receive(self):
        """(opcode, payload) of the next frame."""
        b0, b1 = self.exactly(2)
        n = b1 & 0x7F
        if n == 126:
            n = int.from_bytes(self.exactly(2), "big")
        elif n == 127:
            n = int.from_bytes(self.exactly(8), "big")
        mask = self.exactly(4) if b1 & 0x80 else b"\0\0\0\0"
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(self.exactly(n)))
        return b0 & 0x0F, payload


class Gateway:
    """Discord's gateway, one session at a time: HELLO, IDENTIFY checked, READY, heartbeat
    ACKs, and dispatches pushed by the test."""

    def __init__(self):
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.url = f"ws://127.0.0.1:{self.port}"
        self.identifies, self.paths = [], []
        self.ready = threading.Event()
        self.ws, self.seq = None, 0
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self.session, args=(sock,), daemon=True).start()

    def session(self, sock):
        try:
            ws = WebSocket(sock)
            self.paths.append(ws.path)
            ws.send({"op": 10, "d": {"heartbeat_interval": 41250}})
            while True:
                opcode, payload = ws.receive()
                if opcode == 8:
                    return
                if opcode == 9:
                    ws.frame(10, payload)
                if opcode != 1:
                    continue
                message = json.loads(payload)
                if message["op"] == 1:
                    ws.send({"op": 11})
                elif message["op"] in (2, 6):
                    self.identifies.append(message)
                    if message["d"].get("token") != "Bot " + BOT_TOKEN:
                        ws.close(4004)
                        return
                    self.seq = 1
                    ws.send({"op": 0, "t": "READY", "s": 1, "d": {
                        "v": 10, "session_id": uuid.uuid4().hex, "resume_gateway_url": self.url,
                        "shard": [0, 1], "guilds": [{"id": GUILD, "unavailable": True}],
                        "application": {"id": APP, "flags": 0},
                        "user": {"id": "100000000000000099", "username": "realm-bot", "discriminator": "0",
                                 "avatar": None, "bot": True, "mfa_enabled": False, "accent_color": None,
                                 "banner": None}}})
                    self.ws = ws
                    self.ready.set()
        except (EOFError, OSError):
            return

    def dispatch(self, kind, data):
        self.seq += 1
        self.ws.send({"op": 0, "t": kind, "s": self.seq, "d": data})


class Rest:
    """Discord's REST API: records every call; channel posts can be made to fail."""

    def __init__(self):
        self.calls = []
        self.fail_posts = False
        self.lock = threading.Lock()
        rest = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, body=None):
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(code)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def handle_any(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                path = self.path.split("?")[0]
                call = {"method": self.command, "path": path, "body": json.loads(raw) if raw else None,
                        "auth": self.headers.get("Authorization"), "at": time.monotonic(), "ok": True}
                if path.startswith("/api/v10/channels/") and rest.fail_posts:
                    call["ok"] = False
                with rest.lock:
                    rest.calls.append(call)
                if not call["ok"]:
                    return self.reply(500, {"message": "500: Internal Server Error", "code": 0})
                if path.endswith("/callback"):
                    return self.reply(204)
                if path.endswith("/commands"):
                    return self.reply(200, [])
                self.reply(200, {})

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_any

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def find(self, predicate):
        with self.lock:
            return [c for c in self.calls if predicate(c)]

    def posts(self, channel):
        return [c["body"]["content"] for c in self.find(
            lambda c: c["ok"] and c["method"] == "POST" and c["path"] == f"/api/v10/channels/{channel}/messages")]


class GitHub:
    def __init__(self):
        self.dispatches = []
        github = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, body=None):
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.headers.get("Authorization") != "Bearer " + PAT:
                    return self.reply(401, {"message": "Bad credentials"})
                if self.path != "/repos/o/r/actions/workflows/cd.yml/dispatches":
                    return self.reply(404, {"message": "Not Found"})
                github.dispatches.append(body)
                self.reply(204)

            def do_GET(self):
                runs = [{"html_url": f"https://github.com/o/r/actions/runs/{i + 1}",
                         "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                        for i, _ in enumerate(github.dispatches)][::-1]
                ok = self.path.startswith("/repos/o/r/actions/workflows/cd.yml/runs?event=workflow_dispatch")
                self.reply(200 if ok else 404, {"total_count": len(runs), "workflow_runs": runs})

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()


def sql(query):
    return run("docker", "exec", name, "psql", "-U", "n3e", "-d", "n3e", "-Atc", query).stdout.strip()


def redis_cli(*args):
    return run("docker", "exec", name + "-redis", "redis-cli", *args).stdout.strip()


def call(method, path, token, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{admin}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            text = r.read()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read()
        e.close()
        return e.code, (json.loads(text) if text else None)


OPTION_TYPES = {str: 3, int: 4, bool: 5}
sent = {}  # interaction token -> when it was dispatched


def invoke(command, roles, kind=2, user=("200000000000000001", "alice", "Alice"), focused=None, **options):
    """Sends one interaction; returns its token."""
    token = "itok-" + secrets.token_urlsafe(16)
    opts = []
    for key, value in options.items():
        if key == "who":
            opts.append({"name": "user", "type": 6, "value": value})
        else:
            opts.append({"name": key, "type": OPTION_TYPES[type(value)], "value": value})
    if focused:
        opts.append({"name": focused[0], "type": 3, "value": focused[1], "focused": True})
    gateway.dispatch("INTERACTION_CREATE", {
        "id": str(300000000000000000 + secrets.randbelow(10 ** 15)), "application_id": APP, "type": kind,
        "token": token, "version": 1, "guild_id": GUILD, "channel_id": OPS_CHANNEL, "locale": "en-US",
        "guild_locale": "en-US", "app_permissions": "0", "entitlements": [], "context": 0,
        "authorizing_integration_owners": {"0": GUILD},
        "member": {"user": {"id": user[0], "username": user[1], "global_name": user[2], "discriminator": "0",
                            "avatar": None}, "roles": roles, "joined_at": "2026-01-01T00:00:00.000000+00:00",
                   "deaf": False, "mute": False, "flags": 0, "nick": None, "communication_disabled_until": None},
        "data": {"id": "400000000000000001", "name": command, "type": 1, "options": opts}})
    sent[token] = time.monotonic()
    return token


def answer(token, seconds=15):
    """(text, seconds from the interaction to the final reply) of one interaction."""

    def final():
        for c in rest.find(lambda c: token in c["path"]):
            if c["path"].endswith("/callback") and c["body"]["type"] == 4:
                return c["body"]["data"]["content"], c["at"]
            if c["method"] == "PATCH" and c["path"].endswith("/messages/@original"):
                return c["body"]["content"], c["at"]
        return None

    text, at = wait(final, seconds, f"no reply to {token}")
    return text, at - sent[token]


def command(name_, roles, **options):
    return answer(invoke(name_, roles, **options))[0]


def choices(command_, option, typed):
    token = invoke(command_, [ROLE_MOD], kind=4, focused=(option, typed))
    c = wait(lambda: rest.find(lambda c: token in c["path"] and c["path"].endswith("/callback")), 10,
             "no autocomplete answer")[0]
    assert c["body"]["type"] == 8, c["body"]
    return [(x["name"], x["value"]) for x in c["body"]["data"]["choices"]]


def start_bot(log_name, **extra):
    gateway.ready.clear()
    log = open(out / log_name, "w")
    proc = subprocess.Popen([bot_binary], env={**bot_env, **extra}, stdout=log, stderr=log)
    wait(lambda: gateway.ready.is_set() or proc.poll() is not None, 30, "bot never identified")
    assert proc.poll() is None, (out / log_name).read_text()
    procs.append(proc)
    return proc


def stop(proc, sig=signal.SIGTERM, seconds=10):
    started = time.monotonic()
    proc.send_signal(sig)
    code = proc.wait(seconds)
    return code, time.monotonic() - started


MOD, OPS, NOBODY = [ROLE_MOD], [ROLE_OPS], [OTHER_ROLE]
gateway, rest, github = Gateway(), Rest(), GitHub()
containers, server, procs = [], None, []
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
    listen, health, admin = free_ports(3)
    env = {k: v for k, v in os.environ.items() if k not in ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET")}
    env.update(DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
               REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM=f"test-{name}",
               N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}",
               N3E_ADMIN_LISTEN=f"127.0.0.1:{admin}", N3E_LEGACY_LOGIN="1")
    run(server_binary, "migrate", env=env)
    run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
    server_log = open(out / "server.log", "w")
    server = subprocess.Popen([server_binary], env=env, stdout=server_log, stderr=server_log)
    ops = run(server_binary, "admin", "mint", "--name", "ops", "--perm", "realm.*", env=env).stdout.strip()
    # Spec 03's `bot` token: everything the bot exposes, not world.set.
    bot_admin = run(server_binary, "admin", "mint", "--name", "bot", "--perm", "world.catalog", "--perm", "world.spawn",
                    "--perm", "world.kill", "--perm", "world.event", "--perm", "account.*", "--perm", "realm.status",
                    "--perm", "realm.notice", env=env).stdout.strip()
    def ready():
        assert server.poll() is None, (out / "server.log").read_text()
        try:
            return call("GET", "/v1/realm/status", ops)[1].get("ready")
        except (urllib.error.URLError, ConnectionError):
            return False

    wait(ready, 60, "server not ready")
    nelly = sql(f"INSERT INTO accounts (name, discord_id, discord_name) VALUES ('d{NELLY}', '{NELLY}', 'Nelly') "
                "RETURNING id").splitlines()[0]
    secrets_used = [BOT_TOKEN, PAT, ops, bot_admin]

    bot_env = {"PATH": os.environ["PATH"], "HOSTNAME": "bot-test-1",
               "DISCORD_BOT_TOKEN": BOT_TOKEN, "DISCORD_GUILD_ID": GUILD,
               "DISCORD_CHANNEL_ANNOUNCE": ANNOUNCE, "DISCORD_CHANNEL_OPS": OPS_CHANNEL,
               "DISCORD_ROLE_MOD": ROLE_MOD, "DISCORD_ROLE_OPS": ROLE_OPS,
               "REALM_ADMIN_URL": f"http://127.0.0.1:{admin}", "REALM_ADMIN_TOKEN": bot_admin,
               "REALM_REDIS": redis, "GITHUB_REPO": "o/r", "GITHUB_DISPATCH_TOKEN": PAT,
               "GITHUB_API": f"http://127.0.0.1:{github.port}",
               "DISCORD_API_PROXY": f"127.0.0.1:{rest.port}", "DISCORD_GATEWAY_PROXY": gateway.url,
               # Not this hour: the reminder is checked on its own below.
               "REALM_NAG_HOUR_UTC": str((time.gmtime().tm_hour + 12) % 24)}

    # Start-up refusals: a missing id, a stand-in that is not on this machine.
    for change, says in [({"DISCORD_GUILD_ID": ""}, "DISCORD_GUILD_ID is required"),
                         ({"DISCORD_API_PROXY": "10.0.0.1:443"}, "must name a loopback address"),
                         ({"GITHUB_API": "http://example.com"}, "GITHUB_API")]:
        p = run(bot_binary, env={**bot_env, **change}, good=False)
        assert p.returncode == 2 and says in p.stderr, (change, p.returncode, p.stderr)
    # A token Discord rejects ends the session for good: the bot exits non-zero.
    p = subprocess.run([bot_binary], env={**bot_env, "DISCORD_BOT_TOKEN": "wrong"}, capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 1 and "ended the session for good" in p.stderr, (p.returncode, p.stderr)
    print("PASS start-up refusals: missing ids, non-loopback stand-ins; a rejected Discord token exits 1")

    bot = start_bot("bot.log")
    identify = gateway.identifies[-1]["d"]
    assert identify["intents"] == 0 and gateway.paths[-1] == "/?v=10&encoding=json", (identify, gateway.paths)
    registered = wait(lambda: rest.find(lambda c: c["method"] == "PUT" and c["path"].endswith("/commands")), 10,
                      "no command registration")[0]
    assert registered["path"] == f"/api/v10/applications/{APP}/guilds/{GUILD}/commands", registered["path"]
    assert registered["auth"] == "Bot " + BOT_TOKEN
    names = [c["name"] for c in registered["body"]]
    assert names == ["status", "whois", "kick", "ban", "unban", "mute", "unmute", "motd", "notice", "boss", "kill",
                     "event", "event-stop", "deploy"], names
    kick = next(c for c in registered["body"] if c["name"] == "kick")
    assert [(o["name"], o["type"], o.get("required")) for o in kick["options"]] == [
        ("user", 6, True), ("reason", 3, True)], kick
    print("PASS start-up: IDENTIFY with no intents; 14 guild commands registered in one bulk overwrite")

    # 1. /status renders players, version, draining, pending; anyone may run it.
    text = command("status", NOBODY)
    for part in ["**Realm status**", "Players online: 0", "Version: `", "Draining: no", "Deploy pending: none"]:
        assert part in text, text
    assert call("PUT", "/v1/realm/deploy-pending", ops,
                {"since": "2026-10-30T12:00:00Z", "commits_behind": 3, "head": "abc1234"})[0] == 200
    pending_text = "Deploy pending since 2026-10-30 12:00 UTC (3 commits). Run `/deploy` when the realm is quiet."
    wait(lambda: pending_text in rest.posts(OPS_CHANNEL), 10, "deploy.pending not relayed")
    text = command("status", NOBODY)
    assert "Deploy pending since 2026-10-30 12:00 UTC (3 commits behind)" in text, text
    print("PASS /status: players, version, ready/draining, pending deploy; deploy.pending relayed to ops (test 1, 8)")

    # 2. A non-MOD /kick is refused before any admin call.
    before = (out / "server.log").read_text().count("route=")
    text = command("kick", NOBODY, who=NELLY, reason="afk")
    assert text == "You don't have permission", text
    for c in ["ban", "notice", "whois", "boss", "deploy"]:
        assert command(c, NOBODY) == "You don't have permission", c
    time.sleep(0.5)
    assert (out / "server.log").read_text().count("route=") == before, "an admin call was made"
    print("PASS role gating: non-MOD /kick and friends get the permission reply, no admin call (test 2)")

    # 3. A MOD /kick calls the API; the ops channel hears it from the stream, naming the mod.
    text = command("kick", MOD, who=NELLY, reason="afk")
    assert text == "Kicked Nelly: 0 connections closed.", text
    wait(lambda: "Alice kicked Nelly: afk" in rest.posts(OPS_CHANNEL), 10, "account.kicked not relayed")
    # The same message comes from a kick nobody ran through Discord: it is the stream's.
    assert call("POST", f"/v1/accounts/{nelly}/kick", bot_admin, {"reason": "curl"})[0] == 200
    wait(lambda: "bot kicked Nelly: curl" in rest.posts(OPS_CHANNEL), 10, "curl kick not relayed")
    text = command("ban", MOD, who=NELLY, reason="**spam** @everyone", duration="1h")
    assert text.startswith("Banned Nelly until ") and text.endswith("; 0 connections closed."), text
    banned = wait(lambda: [p for p in rest.posts(OPS_CHANNEL) if p.startswith("Alice banned Nelly until")], 10,
                  "account.banned not relayed")[0]
    assert banned.endswith(r": \*\*spam\*\* \@everyone"), banned
    assert command("ban", MOD, who=NELLY, reason="still spam") == "Banned Nelly permanently; 0 connections closed."
    assert sql(f"SELECT banned_until IS NULL, ban_reason FROM accounts WHERE id={nelly}") == "t|still spam"
    text = command("whois", MOD, who=NELLY)
    for part in ["**Nelly** — account " + nelly, "Online: no", "Banned permanently: still spam", "Not muted"]:
        assert part in text, text
    assert command("unban", MOD, who=NELLY) == "Unbanned Nelly."
    text = command("mute", OPS, who=NELLY, reason="caps", duration="30m")
    assert text.startswith("Muted Nelly until "), text
    assert command("unmute", MOD, who=NELLY) == "Unmuted Nelly."
    for t in ["Alice unbanned Nelly", "Alice unmuted Nelly"]:
        wait(lambda: t in rest.posts(OPS_CHANNEL), 10, t)
    assert "1y" in command("ban", MOD, who=NELLY, reason="x", duration="1y")
    text = command("kick", MOD, who="80351110224678913", reason="afk")
    assert "has no account on this realm" in text, text
    mentions = {json.dumps(c["body"].get("allowed_mentions")) for c in rest.find(
        lambda c: c["method"] in ("POST", "PATCH") and "/messages" in c["path"])}
    assert mentions == {json.dumps({"parse": []})}, mentions
    print("PASS /kick /ban /unban /mute /unmute /whois: API called, ops channel told from the stream, "
          "markdown escaped, no mentions allowed, idempotent ban, unknown user (test 3)")

    # 4. /notice hello: the announce channel gets it exactly once, via the stream.
    text = command("notice", MOD, text="hello")
    assert text.startswith("Notice sent"), text
    wait(lambda: "**Notice:** hello" in rest.posts(ANNOUNCE), 10, "notice not relayed")
    time.sleep(3)
    assert rest.posts(ANNOUNCE).count("**Notice:** hello") == 1, rest.posts(ANNOUNCE)
    print("PASS /notice: announce channel gets it exactly once, from the stream (test 4)")

    # 5/5b (partial until M5b): world commands reach their routes; the catalog is absent.
    assert choices("boss", "name", "iron") == [("realm catalog unavailable", "realm-catalog-unavailable")]
    assert "catalog is unavailable" in command("boss", MOD, name="realm-catalog-unavailable")
    for c, options in [("boss", {"name": "ironfang"}), ("event", {"preset": "weekend-exp"}), ("event-stop", {}),
                       ("kill", {"entity": 12345, "reason": "stuck"}), ("motd", {"lines": "Welcome | Be nice"})]:
        assert command(c, MOD, **options) == NOT_YET, c
    print("PASS world commands: /boss /event /event-stop /kill /motd reach their routes (501 until M5/M5b); "
          "autocomplete says the catalog is unavailable (tests 5, 5b partial)")

    # 9. /deploy: OPS dispatches with force "true"; MOD is denied; nothing pending needs force.
    assert command("deploy", MOD) == "You don't have permission"
    text = command("deploy", OPS, reason="ship it")
    assert text == "Deploy started: https://github.com/o/r/actions/runs/1", text
    assert github.dispatches == [{"ref": "master", "inputs": {"force": "true", "reason": "ship it"}}], github.dispatches
    assert call("DELETE", "/v1/realm/deploy-pending", ops)[0] == 204
    assert command("deploy", OPS).startswith("Nothing pending"), "deploy without force"
    assert command("deploy", OPS, force=True).startswith("Deploy started: "), "forced deploy"
    assert github.dispatches[-1]["inputs"] == {"force": "true", "reason": "/deploy by Alice"}, github.dispatches
    print("PASS /deploy: workflow_dispatch with force \"true\" and the run URL; MOD denied; "
          "nothing pending without force (test 9)")

    # 8. The daily reminder posts the pending deploy in its hour.
    assert call("PUT", "/v1/realm/deploy-pending", ops,
                {"since": "2026-10-31T08:00:00Z", "commits_behind": 1, "head": "def5678"})[0] == 200
    nag = "Deploy pending since 2026-10-31 08:00 UTC (1 commit). Run `/deploy` when the realm is quiet."
    wait(lambda: nag in rest.posts(OPS_CHANNEL), 10, "deploy.pending not relayed")
    code, took = stop(bot)
    assert code == 0 and took < 5, (code, took)
    print(f"PASS SIGTERM: exit 0 in {took:.2f} s")
    bot = start_bot("bot-nag.log", REALM_NAG_HOUR_UTC=str(time.gmtime().tm_hour))
    wait(lambda: rest.posts(OPS_CHANNEL).count(nag) == 2, 15, "no reminder")
    print("PASS daily reminder: REALM_NAG_HOUR_UTC=now posts the pending deploy to ops (test 8)")

    # 7. Three entries the bot could not post survive its death and arrive once each.
    rest.fail_posts = True
    # One transaction, so the bot's blocked read takes all three at once.
    entries = "".join("XADD realm:events * type notice ts 2026-10-31T00:00:00Z data '"
                      + json.dumps({"text": f"redelivered {i}", "level": "info", "by": "test"}) + "'\n"
                      for i in range(3))
    run("docker", "exec", "-i", name + "-redis", "redis-cli", stdin="MULTI\n" + entries + "EXEC\n")
    wait(lambda: rest.find(lambda c: not c["ok"]), 10, "the bot never tried to post")
    stop(bot, signal.SIGKILL)
    rest.fail_posts = False
    pending = redis_cli("XPENDING", "realm:events", "bot").splitlines()
    assert pending[0] == "3", pending
    bot = start_bot("bot-restarted.log", HOSTNAME="bot-test-2")
    for i in range(3):
        wait(lambda: f"**Notice:** redelivered {i}" in rest.posts(ANNOUNCE), 15, f"redelivered {i}")
    time.sleep(2)
    got = [p for p in rest.posts(ANNOUNCE) if "redelivered" in p]
    assert got == [f"**Notice:** redelivered {i}" for i in range(3)], got
    assert redis_cli("XPENDING", "realm:events", "bot").splitlines()[0] == "0"
    print("PASS restart with 3 unacked entries: delivered once each, in order, by a new consumer name (test 7)")

    # Admin 401: the reply names it; ops hears it once.
    run(server_binary, "admin", "revoke", "--name", "bot", env=env)
    rejected = "bot token rejected — ops needs to re-mint"
    wait(lambda: command("status", NOBODY) == rejected, 15, "revoked token still accepted")
    assert command("status", NOBODY) == rejected
    alerts = [p for p in rest.posts(OPS_CHANNEL) if "rejected the bot's token" in p]
    assert len(alerts) == 1, alerts
    print("PASS revoked admin token: \"bot token rejected\" reply, one ops-channel alert")
    bot_admin = run(server_binary, "admin", "mint", "--name", "bot-2", "--perm", "world.catalog", "--perm",
                    "world.spawn", "--perm", "world.kill", "--perm", "world.event", "--perm", "account.*",
                    "--perm", "realm.status", "--perm", "realm.notice", env=env).stdout.strip()
    secrets_used.append(bot_admin)
    stop(bot)
    bot_env["REALM_ADMIN_TOKEN"] = bot_admin
    bot = start_bot("bot-failfast.log", HOSTNAME="bot-test-2")

    # 6. Admin API away: every mutating command fails fast, saying why if the stream did.
    assert call("POST", "/v1/realm/drain", ops, {"reason": "deploy v2"})[0] == 200
    wait(lambda: "Restart soon: deploy v2. 0 online." in rest.posts(ANNOUNCE), 10, "drain not announced")
    mutating = [("kick", {"who": NELLY, "reason": "x"}), ("ban", {"who": NELLY, "reason": "x"}),
                ("unban", {"who": NELLY}), ("mute", {"who": NELLY, "reason": "x"}), ("unmute", {"who": NELLY}),
                ("motd", {"lines": "a"}), ("notice", {"text": "x"}), ("boss", {"name": "ironfang"}),
                ("kill", {"entity": 1, "reason": "x"}), ("event", {"preset": "p"}), ("event-stop", {})]
    for how in [signal.SIGSTOP, signal.SIGKILL]:
        server.send_signal(how)
        tokens = [(c, invoke(c, MOD, **o)) for c, o in mutating]
        slowest = 0
        for c, token in tokens:
            text, took = answer(token)
            assert text == UNAVAILABLE + " The realm is draining for a restart: deploy v2.", (c, text)
            assert took < 6, (c, took)
            slowest = max(slowest, took)
        print(f"PASS admin API {'hung' if how == signal.SIGSTOP else 'gone'}: all {len(mutating)} mutating "
              f"commands fail fast with the drain reason (slowest {slowest:.2f} s, test 6)")
    server.wait(10)
    server = None

    code, took = stop(bot)
    assert code == 0 and took < 5, (code, took)

    # 10. No secret in any log.
    logs = {p.name: p.read_text() for p in out.glob("*.log")}
    leaks = [(n, s[:8]) for n, text in logs.items() for s in secrets_used if s in text]
    assert not leaks, leaks
    print(f"PASS logs: none of the {len(secrets_used)} secrets in {len(logs)} logs (test 10)")
    print("BOT_OK")
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
    if server is not None:
        server.send_signal(signal.SIGCONT)
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    rest.http.shutdown()
    github.http.shutdown()
    for c in containers:
        subprocess.run(["docker", "rm", "-f", c], capture_output=True)
