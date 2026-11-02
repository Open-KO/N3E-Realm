"""Opt-in (make live-ko): spec 11 acceptance 7, the KO screens against a native server
on the Moradon package cooked from the player's own KO data, with the Discord
stand-in (tests/discord_standin.py) and a disposable Postgres and Redis.

- The test client plays the screens with a player's events
  (N3E_TEST_FRONT_FLOW, client/harness/front_end_flow.inc): Discord login on one
  ENTER pressed while the server is paused (SIGSTOP), so before the connection is
  up; the press is held and the flow starts once the server resumes. The first
  browser step is denied: KO's message box shows the flow's failure, and ENTER
  again logs in (the browser step played here on the address it prints) -> realms -> select (no
  characters) -> create "Taken", which another account holds: the server's
  refusal in KO's message box -> create a fresh name -> select with it (the
  pointer off, on and off the character in front: its hover clip blends in on
  its first frame, plays once and holds its last frame, the rest clip blends
  back, the spot widens and narrows to off and the info text shows only while
  the pointer is on it; RQ-066, RQ-075) -> start -> loading -> the world.
- An operator kick (admin API) returns the client to the login screen with the
  operator's wording in the message box.
- `character_slots` (3, front-end.bin) refuses a fourth character at the wire,
  in the server's wording; the Characters list names the levels.
- Music (RQ-018): one stream starts on the login screen and plays on through the
  realm list, select, create and select again, stops on loading, before the
  world, and (when the client runs a frame more after the kick) a new one starts
  on the login screen.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
from discord_standin import Discord, b64url, user  # noqa: E402
from isolation import DISPOSABLE_POSTGRES  # noqa: E402
from readiness import free_ports, wait_postgres  # noqa: E402
from world_peer import Peer, blob, first  # noqa: E402

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED KO front-end flow needs N3E_GRAPHICAL=1 (make live-ko)")
    sys.exit(0)

WORK = Path(os.environ.get("N3E_KO_WORK", "build/live-ko/work"))
package = (WORK / "packages" / "moradon").resolve()
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
CONTENT = (package / "release.sha256").read_text().strip()
server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
name = "n3e-front-end-" + uuid.uuid4().hex[:10]
out = ROOT / "build/live-ko/front-end-flow"
out.mkdir(parents=True, exist_ok=True)
CLIENT_ID = "223456789012345678"
SECRET = "s3cret-" + secrets.token_hex(8)
REDIRECT = "http://127.0.0.1:49152/callback"
REFUSED = "character name invalid/taken or limit reached"


def run(*cmd, env=None):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def sql(query):
    return run("docker", "exec", name, "psql", "-U", "n3e", "-d", "n3e", "-Atc", query).stdout.strip()


def call(method, path, token, body=None):
    request = urllib.request.Request(f"http://127.0.0.1:{admin}{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode())
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            text = r.read()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read()
        e.close()
        return e.code, (json.loads(text) if text else None)


def peer_login(who, source):
    """A wire peer logged in through the stand-in; returns it with its Characters."""
    p = Peer(listen, content=CONTENT, game=manifest["game_id"], protocol=manifest["protocol_version"], source=source)
    verifier = b64url(secrets.token_bytes(48))
    code = discord.authorize(who, b64url(hashlib.sha256(verifier.encode()).digest()))
    p.send(46, blob(1, code) + blob(2, verifier) + blob(3, REDIRECT) + blob(4, "front-end-flow"))
    tag, data = p.until(48, 4, seconds=15)
    assert tag == 48, ("refused", first(data, 1), first(data, 2, b"").decode())
    tag, _ = p.until(6, 4)
    assert tag == 6
    p.tend()
    return p


discord = Discord(CLIENT_ID, SECRET, REDIRECT)
containers, server, client = [], None, None
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
    env = {k: v for k, v in os.environ.items() if k not in ("N3E_LEGACY_LOGIN", "DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET")}
    env.update(DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
               REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM=f"test-{name}",
               N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}",
               N3E_ADMIN_LISTEN=f"127.0.0.1:{admin}", DISCORD_CLIENT_ID=CLIENT_ID,
               DISCORD_CLIENT_SECRET=SECRET, N3E_DISCORD_API=f"http://127.0.0.1:{discord.port}/api")
    run(server_binary, "migrate", env=env)
    run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
    log = open(out / "server.log", "w")
    server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
    ops = run(server_binary, "admin", "mint", "--name", "ops", "--perm", "realm.status", "--perm", "account.*",
              env=env).stdout.strip()
    deadline = time.monotonic() + 60
    while True:
        assert server.poll() is None, (out / "server.log").read_text()
        try:
            if call("GET", "/v1/realm/status", ops)[1].get("ready"):
                break
        except (urllib.error.URLError, ConnectionError):
            pass
        assert time.monotonic() < deadline, "server not ready"
        time.sleep(0.3)

    # character_slots: another account holds "Taken" and fills its three slots;
    # a fourth is refused in the server's wording.
    holder = peer_login(user("90351110224678001", "Holder"), "127.0.0.31")
    for n in ("Taken", "Second", "Third"):
        holder.create(n)
    holder.send(7, blob(1, "Fourth"))
    tag, data = holder.until(6, 4)
    assert tag == 4 and (first(data, 1), first(data, 2, b"").decode()) == (8, REFUSED), (tag, data)
    assert [n for _, n in holder.characters] == ["Taken", "Second", "Third"], holder.characters
    holder.s.close()
    print(f"PASS character_slots 3: a fourth character refused ({REFUSED})")

    # The client through the KO screens.
    player = user("90351110224678002", "Wanderer")
    home = out / "client-home"
    subprocess.run(["rm", "-rf", str(home)])
    (home / "config").mkdir(parents=True)
    realm_json = home / "realm.json"
    # The client's ENTER must come before the connection is up: pause the
    # server until the client has pressed it.
    server.send_signal(signal.SIGSTOP)
    realm_json.write_text(json.dumps({"id": "front-end", "name": "Front End Realm", "host": "localhost",
                                      "port": listen, "discord_client_id": CLIENT_ID}))
    client = subprocess.Popen(
        ["build/client/n3e-test-client", str(package), "--realm", str(realm_json), "--ca", "deploy/local/ca.pem"],
        env={**env, "XDG_CONFIG_HOME": str(home / "config"), "N3E_TEST_NO_BROWSER": "1",
             "N3E_TEST_FRONT_FLOW": "Taken,Fresh"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines, flow, kicked, denied = [], [], False, False
    deadline = time.monotonic() + 240
    for line in client.stdout:
        lines.append(line)
        assert time.monotonic() < deadline, "flow timed out"
        if line.startswith("Open this address to log in with Discord: "):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(line.split(": ", 1)[1].strip()).query))
            if not denied:
                answer = {"error": "access_denied", "state": q["state"]}
                denied = True
            else:
                answer = {"code": discord.authorize(player, q["code_challenge"], q["redirect_uri"]), "state": q["state"]}
            back = q["redirect_uri"] + "?" + urllib.parse.urlencode(answer)
            with urllib.request.urlopen(back, timeout=5) as r:
                assert r.status == 200
        if line.startswith("FRONT_FLOW "):
            flow.append(line.strip()[len("FRONT_FLOW "):])
            if flow[-1].startswith("enter "):
                server.send_signal(signal.SIGCONT)
            if flow[-1].startswith("screen=world") and not kicked:
                account = sql(f"SELECT id FROM accounts WHERE discord_id='{player['id']}'")
                status, body = call("POST", f"/v1/accounts/{account}/kick", ops, {"reason": "flow test"})
                assert status == 200, (status, body)
                kicked = True
    code = client.wait(timeout=60)
    text = "".join(lines)
    (out / "client.log").write_text(text)
    assert code == 0 and "ENTERED map" in text, (code, text[-3000:])
    screens = [f.split()[0][len("screen="):] for f in flow if f.startswith("screen=")]
    messages = [f[len("message='"):-1] for f in flow if f.startswith("message=")]
    enters = [f for f in flow if f.startswith("enter ")]
    assert enters == ["enter connected=0"], flow
    assert screens == ["login", "realms", "select", "create", "select", "loading", "world", "login"], flow
    assert messages == ["Discord login was cancelled. ENTER to try again.", REFUSED,
                        "You were disconnected by an operator: flow test."], flow
    order = [f.split()[0] for f in flow if f.startswith(("screen=", "music="))]
    want = ["screen=login", "music=stream1", "screen=realms", "screen=select", "screen=create", "screen=select",
            "screen=loading", "music=none", "screen=world", "screen=login"]
    assert order in (want, want + ["music=stream2"]), flow
    # RQ-066, RQ-075 (KO-FINDINGS 8.1, the 1097 hall): with the pointer on the
    # character in front, the hover clip (pre_select) blends in over its own
    # 0.3 s on its first frame, plays once and holds its last frame; off it,
    # the rest clip (dummy) blends back. The spot widens only while the
    # pointer is on (0.02 a tick at 30 ticks/s, to 0.5), narrows when it
    # leaves and is off at 0; the info text shows only while it is on.
    hovers = {h["phase"]: h for h in ({k: v for k, v in (kv.split("=") for kv in f.split()[1:])}
                                      for f in flow if f.startswith("hover "))}
    assert list(hovers) == ["out", "in", "play", "hold", "back", "rest"], flow
    v = {phase: {k: (int(x) if k in ("clip", "spot", "info") else float(x)) for k, x in h.items() if k != "phase"}
         for phase, h in hovers.items()}
    out_, in_, play, hold, back, rest = (v[p] for p in ("out", "in", "play", "hold", "back", "rest"))
    widest, rate = 0.5, 0.02 * 30
    assert out_["clip"] == 2 and out_["blend"] == 1 and out_["theta"] == 0, v
    assert out_["spot"] == 0 and out_["info"] == 0, v
    assert in_["clip"] == 0 and in_["t"] == 0 and 0 < in_["blend"] < 1, v  # held on its first frame
    assert 0 < in_["theta"] < widest and in_["spot"] == 1 and in_["info"] == 1, v
    assert in_["end"] > 0.5 and play["end"] == in_["end"] == hold["end"], v
    # A second after it came in, the clip has played that second less the blend.
    assert play["clip"] == 0 and play["blend"] == 1 and 0.6 < play["t"] < 0.9 < play["end"], v
    assert play["theta"] == widest and play["spot"] == 1 and play["info"] == 1, v
    assert hold["clip"] == 0 and abs(hold["t"] - hold["end"]) < 1e-4 and hold["theta"] == widest, v
    assert hold["info"] == 1, v
    assert back["clip"] == 2 and 0 < back["blend"] < 1 and back["info"] == 0, v
    assert widest - rate * 0.25 <= back["theta"] < widest and back["spot"] == 1, v
    assert rest["clip"] == 2 and rest["blend"] == 1 and abs(rest["t"] - rest["end"]) < 1e-4, v
    assert rest["theta"] == 0 and rest["spot"] == 0 and rest["info"] == 0, v
    assert sql("SELECT count(*) FROM characters WHERE name='Fresh'") == "1"
    assert sql("SELECT count(*) FROM characters WHERE name='Taken'") == "1"
    print(f"PASS front-end flow: one ENTER ({enters[0]}) -> Discord denied (KO's message box) -> ENTER -> Discord login -> realms -> select -> create (Taken refused in the message box, "
          "Fresh created) -> select (the front character's hover clip blends in on its first frame, plays once and holds, the rest clip blends back; "
          "the spot widens and the info text shows only while the pointer is on it) -> loading -> world; a kick returns to login with the operator's wording; "
          "one music stream from login to loading")
    assert server.poll() is None, "server exited"
    print("PASS KO front-end flow")
finally:
    if client is not None and client.poll() is None:
        client.kill()
    if server is not None:
        server.send_signal(signal.SIGCONT)
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    discord.http.shutdown()
    for c in containers:
        subprocess.run(["docker", "rm", "-f", c], capture_output=True)
