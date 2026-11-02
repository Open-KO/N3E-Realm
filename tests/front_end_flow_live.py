"""Opt-in (make live-ko): spec 11 acceptance 7, the KO screens against a native server
on the Moradon package cooked from the player's own KO data, with the Discord
stand-in (tests/discord_standin.py) and a disposable Postgres and Redis.

- The test client plays the screens with a player's events
  (N3E_TEST_FRONT_FLOW, client/harness/front_end_flow.inc): first the logo
  screen (RQ-101, 1264's, KO-FINDINGS 9.2), its music starting 1 s in and the
  cursor hidden, which a focus gain with a modifier and a key stamped before
  it 0.5 s in leave (Q82), a click 1.1 s in leaves and SPACE 1.3 s in skips, the
  login starting its own track at once; then Discord login on one
  ENTER pressed while the realm connection is held, so before it is up; the
  press is held and the flow starts once the connection goes through. (The
  client connects when the login first shows, as 1264 does (Q82); the test
  holds that connection in a TCP relay until ENTER, not by pausing the
  server, whose 2 s admission lease a paused logo would outlast.) The first
  browser step is denied: KO's message box shows the flow's failure, and ENTER
  again logs in (the browser step played here on the address it prints) -> realms -> select (no
  characters) -> create "Taken", which another account holds: the server's
  refusal in KO's message box, titled as the package words a refused create
  (RQ-102, Q81: 1264's create failure title) where the Discord failure and the
  kick are untitled -> create a fresh name -> select with it (the
  pointer off, on and off the character in front: its hover clip blends in on
  its first frame, plays once and holds its last frame, the rest clip blends
  back, the spot widens and narrows to off and the info text shows only while
  the pointer is on it; RQ-066, RQ-075; the arrows turn the camera one slot
  left, back, one right and back, each ending where 1097's check ends it,
  RQ-067, each playing the turn sound once and the left end of the row none,
  RQ-077) -> start (the start clip blends in over
  1097's 0.6 s on its first frame under the full spot, then plays; RQ-076) ->
  loading -> the world.
- An operator kick (admin API) returns the client to the login screen with the
  operator's wording in the message box.
- The login bar and KO's copyright line (RQ-108, Q85, KO-FINDINGS 9.4: 1264's
  SetVisibleLogInUIs): the bar shows at rest, and the line instead from each
  ENTER (the first held through the connection) until the login's answer; the
  denied Discord step shows the bar again under its message box; the realm
  list keeps the line; the return after the kick shows the bar (and, if the
  client logs in again with its stored session before it stops, the line).
- `character_slots` (3, front-end.bin) refuses a fourth character at the wire,
  in the server's wording; the Characters list names the levels.
- Music (RQ-018; RQ-083, KO-FINDINGS 9): the logo's (bless.wav) 1 s into it,
  replaced by the login's when SPACE skips it (1264's login Init releases it);
  then one stream starts on the login screen
  and plays on through the realm list (1097's sound 35, restarting in place), a
  second replaces it on select (sound 20003, as 1097's game-server login answer
  does) and plays on through create and select again, stops on loading, before
  the world, and (when the client runs a frame more after the kick) a new one
  starts on the login screen.
- The login scene (RQ-104): its clock starts at the login's first entry and
  again at the return after the kick, and keeps the login track's time.
"""
import hashlib
import json
import math
import os
import re
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
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
# RQ-102 (Q81): the package's message titles and wordings, as the cook reads
# them from the chosen front end's recipe and its KO trees (no KO text here).
sys.path.insert(0, str(ROOT / "tools/assetc"))
import front_end_choice  # noqa: E402
import ko_front_end  # noqa: E402
FRONT = front_end_choice.choose("games/moradon")
WORDED = ko_front_end.message_texts(json.loads(FRONT["recipe"].read_text()), ko_front_end.inputs(FRONT))
# The box shows each kind's title (empty when the recipe names none) and its
# text where the recipe replaces the client's. The 1097 recipe titles a
# refused create over the server's wording and leaves the Discord flow's
# failures and a kick untitled; another recipe's wording is checked as it is.


def shown(kind, text):
    title, replaced = WORDED.get(kind, ("", None))
    return (text if replaced is None else replaced, title)


if FRONT["client"] == "1097":
    assert WORDED["create_refused"][0] and WORDED["create_refused"][1] is None, WORDED
    assert "login" not in WORDED and "disconnected" not in WORDED, WORDED


def run(*cmd, env=None):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


class Relay:
    """A TCP relay to the realm that holds each connection (reading nothing
    from the client) until `released` is set, then joins it to `port`.
    `held_at`: when the first connection arrived. `close` closes the
    listener and every socket it opened."""

    def __init__(self, port):
        self.port, self.released, self.held_at = port, threading.Event(), None
        self.sockets, self.lock = [], threading.Lock()
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listen = self.listener.getsockname()[1]
        threading.Thread(target=self.accept, daemon=True).start()

    def keep(self, s):
        with self.lock:
            self.sockets.append(s)
        return s

    def accept(self):
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            self.held_at = self.held_at or time.monotonic()
            threading.Thread(target=self.join, args=(self.keep(client),), daemon=True).start()

    def join(self, client):
        self.released.wait(240)
        try:
            server = self.keep(socket.create_connection(("127.0.0.1", self.port), timeout=5))
            server.settimeout(None)
        except OSError:
            client.close()
            return
        for a, b in ((client, server), (server, client)):
            threading.Thread(target=self.pump, args=(a, b), daemon=True).start()

    @staticmethod
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

    def close(self):
        self.listener.close()
        with self.lock:
            for s in self.sockets:
                s.close()
            self.sockets.clear()


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
containers, server, client, relay = [], None, None, None
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
    # The client's ENTER must come before the connection is up: hold it in
    # the relay until the client has pressed it.
    relay = Relay(listen)
    realm_json.write_text(json.dumps({"id": "front-end", "name": "Front End Realm", "host": "localhost",
                                      "port": relay.listen, "discord_client_id": CLIENT_ID}))
    client = subprocess.Popen(
        ["build/client/n3e-test-client", str(package), "--realm", str(realm_json), "--ca", "deploy/local/ca.pem"],
        env={**env, "XDG_CONFIG_HOME": str(home / "config"), "N3E_TEST_NO_BROWSER": "1",
             "N3E_TEST_FRONT_FLOW": "Taken,Fresh"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines, flow, kicked, denied, held = [], [], False, False, None
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
                held = time.monotonic() - relay.held_at if relay.held_at else None
                relay.released.set()
                # The client connects from the login (RQ-101, Q82), so the
                # hold is a frame or two, far inside its 3 s receive timeout.
                assert held is None or held < 2, ("the realm connection was held %.2f s" % held, flow)
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
    messages = [re.fullmatch(r"message='(.*)' title='(.*)'", f).groups() for f in flow if f.startswith("message=")]
    enters = [f for f in flow if f.startswith("enter ")]
    assert enters == ["enter connected=0"], flow
    assert screens == ["logo", "login", "realms", "select", "create", "select", "loading", "world", "login"], flow
    assert messages == [shown("login", "Discord login was cancelled. ENTER to try again."),
                        shown("create_refused", REFUSED),
                        shown("disconnected", "You were disconnected by an operator: flow test.")], flow
    order = [f.split()[0] for f in flow if f.startswith(("screen=", "music="))]
    want = ["screen=logo", "music=stream1", "screen=login", "music=stream2", "screen=realms", "screen=select",
            "music=stream3", "screen=create", "screen=select", "screen=loading", "music=none", "screen=world",
            "screen=login"]
    assert order in (want, want + ["music=stream4"]), flow
    # RQ-108: the bar at rest, the line instead while a login is under way and
    # on the realm list.
    bars = [f[len("bar "):] for f in flow if f.startswith("bar ")]
    rest, wait = "screen=login group=1 line=0", "screen=login group=0 line=1"
    assert bars[:6] == [rest, wait, rest, wait, "screen=realms group=0 line=1", rest], flow
    assert bars[6:] in ([], [wait]), flow
    # The first ENTER hid the bar; the denied step showed it again under its
    # box, before the box was answered.
    at = [i for i, f in enumerate(flow) if f.startswith("bar ")]
    denied_box = next(i for i, f in enumerate(flow) if f.startswith("message='Discord login was cancelled."))
    assert flow.index("enter connected=0") < at[1] < at[2] < denied_box < at[3], flow
    # RQ-101 (KO-FINDINGS 9.2, 1264's logo procedure): the first group fades in
    # over 1.5 s (its alpha in KO's 255ths); the music (bless.wav) plays from
    # 1 s at full gain; the cursor is hidden; a click leaves the screen
    # (00601480 takes keys only) and a key skips it to the login.
    logos = {g["phase"]: g for g in ({k: v for k, v in (kv.split("=") for kv in f.split()[1:])}
                                     for f in flow if f.startswith("logo "))}
    # The stray keys 0.5 s in (a modifier right after a focus gain, a key-down
    # stamped before the screen) leave it showing (Q82): the click still
    # finds the first group.
    assert list(logos) == ["stray", "click", "skip"], flow
    stray, click, skip = logos["stray"], logos["click"], logos["skip"]
    assert 0.5 <= float(stray["t"]) < 0.65 and stray["group"] == "0" and stray["music"] == "0", logos
    assert 1.1 <= float(click["t"]) < 1.25 and 1.3 <= float(skip["t"]) < 1.45, logos
    for g in (click, skip):
        assert g["group"] == "0" and abs(float(g["alpha"]) - math.floor(float(g["t"]) / 1.5 * 255) / 255) < 1e-4, logos
        assert g["music"] == "1" and float(g["gain"]) == 1 and g["cursor"] == "0", logos
    assert flow.index("screen=login characters=0") > flow.index(next(f for f in flow if f.startswith("logo phase=skip")))
    # RQ-104 (KO-FINDINGS 9.1: 1264's login Init sets the character's clip
    # from its first frame, 0044fa20 at 005bdb3c, and its track starts on the
    # same tick): the login scene's clock starts at each entry, the first
    # (after the logo) and the return after the kick, and keeps the login
    # track's time: half a second in it is near that half second (behind by
    # at most the earlier stream's frames still queued for the device when the
    # track started, seven 1,024-frame chunks, 0.15 s, and a frame; ahead by at
    # most the block the device takes at once), never the process's clock.
    scenes = [{k: float(x) for k, x in (kv.split("=") for kv in f.split()[1:])} for f in flow if f.startswith("scene ")]
    assert [int(c["entry"]) for c in scenes] == [1, 2], flow
    for c in scenes:
        assert 0.5 <= c["since"] < 1 and c["since"] - 0.3 <= c["t"] <= c["since"] + 0.1, scenes
    assert scenes[1]["process"] > scenes[0]["process"] + 5, scenes
    # RQ-066, RQ-075 (KO-FINDINGS 8.1, the 1097 hall): with the pointer on the
    # character in front, the hover clip (pre_select) blends in over its own
    # 0.3 s on its first frame, plays once and holds its last frame; off it,
    # the rest clip (dummy) blends back. The spot widens only while the
    # pointer is on (0.02 a tick at 30 ticks/s, to 0.5), narrows when it
    # leaves and is off at 0; the info text shows only while it is on.
    hovers = {h["phase"]: h for h in ({k: v for k, v in (kv.split("=") for kv in f.split()[1:])}
                                      for f in flow if f.startswith("hover "))}
    assert list(hovers) == ["out", "in", "play", "hold", "back", "rest", "start", "blend", "started"], flow
    v = {phase: {k: (int(x) if k in ("clip", "spot", "info") else float(x)) for k, x in h.items() if k != "phase"}
         for phase, h in hovers.items()}
    out_, in_, play, hold, back, rest, start, blend, started = (
        v[p] for p in ("out", "in", "play", "hold", "back", "rest", "start", "blend", "started"))
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
    # RQ-076 (KO-FINDINGS 8.1, 0043ea30): ENTER sets the start clip (selected)
    # with the select's own 0.6 s blend, not the record's 0.3 s: 0.3 s in it is
    # still blending, held on its first frame; once the blend is done it plays.
    # The spot is at its full theta throughout.
    assert start["clip"] == 1 and start["t"] == 0 and 0 < start["blend"] < 1, v
    assert start["end"] > 2 and blend["end"] == started["end"] == start["end"], v
    assert blend["clip"] == 1 and blend["t"] == 0 and 0.45 < blend["blend"] < 1, v
    assert started["clip"] == 1 and started["blend"] == 1 and 0.2 < started["t"] < 1.2 < started["end"], v
    for h in (start, blend, started):
        assert h["theta"] == widest and h["spot"] == 1 and h["info"] == 0, v
    # RQ-067 (KO-FINDINGS 8.2, 1097's CheckJobState 0043e4e0): an arrow turns
    # the camera one slot, about `at` at 1.2 rad/s, the short way: LEFT to slot 1
    # (positive turns), RIGHT back to the centre, RIGHT to slot 2 (negative),
    # LEFT back. A side turn ends on the first frame past the angle where 1097's
    # check (the eye a further 0.01 rad on, its cosine with the camera's own
    # eye from `at` below 0.75 left or 0.77 right) ends it; a turn back ends on
    # the camera's own eye. No frame leaves the two slots' angles by more than
    # a frame's step (the client's frames are at most 0.25 s).
    # The recipe of the front end the package was cooked with (RQ-078).
    select = json.loads(FRONT["recipe"].read_text())["select"]
    eye, at = select["camera"]["eye"], select["camera"]["at"]
    o = [eye[i] - at[i] for i in range(3)]
    flat = o[0] ** 2 + o[2] ** 2

    def turn_end(cos):
        return math.acos((cos * (flat + o[1] ** 2) - o[1] ** 2) / flat) - 0.01
    left_end, right_end = turn_end(0.75), -turn_end(0.77)
    step = 1.2 * 0.25
    turns = {t["phase"]: {k: float(x) for k, x in t.items() if k != "phase"}
             for t in ({k: x for k, x in (kv.split("=") for kv in f.split()[1:])} for f in flow if f.startswith("turn "))}
    assert list(turns) == ["left", "centre", "right", "back"], flow
    left, centre, right, back_ = (turns[p] for p in ("left", "centre", "right", "back"))
    assert left["slot"] == 1 and left_end < left["angle"] <= left_end + step, (turns, left_end)
    assert left["low"] == 0 and left["high"] == left["angle"], turns
    assert centre["slot"] == 0 and centre["angle"] == 0, turns
    assert centre["high"] == left["angle"] and -step <= centre["low"] <= 0, turns
    assert right["slot"] == 2 and right_end - step <= right["angle"] < right_end, (turns, right_end)
    assert right["high"] == 0 and right["low"] == right["angle"], turns
    assert back_["slot"] == 0 and back_["angle"] == 0, turns
    assert back_["low"] == right["angle"] and 0 <= back_["high"] <= step, turns
    # RQ-077 (Q70, KO-FINDINGS 8.2): 1097's DoJobLeft/DojobRight play the select
    # proc's sound 2501 (char_select_turn.wav, audio.bin's front:select-turn)
    # once for each turn they start, and nothing at the end of the row.
    assert all(t["sounds"] == 1 and t["clip"] == 1 for t in turns.values()), turns
    edges = [{k: float(x) for k, x in (kv.split("=") for kv in f.split()[1:])} for f in flow if f.startswith("edge ")]
    assert edges == [{"slot": 1, "focus": 1, "sounds": 0, "clip": 1}], edges
    assert sql("SELECT count(*) FROM characters WHERE name='Fresh'") == "1"
    assert sql("SELECT count(*) FROM characters WHERE name='Taken'") == "1"
    print(f"PASS front-end flow: the logo (its music 1 s in, the cursor hidden, a click ignored, SPACE skips it) -> "
          f"one ENTER ({enters[0]}) -> Discord denied (KO's message box) -> ENTER -> Discord login -> realms -> select -> create (Taken refused in the message box under KO's title, "
          "Fresh created) -> select (the front character's hover clip blends in on its first frame, plays once and holds, the rest clip blends back; "
          "the spot widens and the info text shows only while the pointer is on it; the arrows turn the camera one slot each way, "
          "ending where 1097's check ends it, each with the turn sound) -> start (blends in over 0.6 s, then plays) -> loading -> world; "
          "a kick returns to login with the operator's wording; "
          "the login scene's clock starts at each entry and keeps its track's time; "
          "the logo's music, then one stream on login and the realm list, another from select to loading")
    assert server.poll() is None, "server exited"
    print("PASS KO front-end flow (%s)" % ("the realm connection held %.2f s before ENTER" % held if held is not None
                                           else "the realm connection not yet opened at ENTER"))
finally:
    if client is not None and client.poll() is None:
        client.kill()
    if relay is not None:
        relay.close()
    if server is not None:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    discord.http.shutdown()
    for c in containers:
        subprocess.run(["docker", "rm", "-f", c], capture_output=True)
