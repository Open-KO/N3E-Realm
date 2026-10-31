"""Discord login, sessions, kick, ban and mute (specs/02-auth-sessions.md, roadmap M3).

Starts the native server against a disposable Postgres and Redis and a stand-in for
Discord's OAuth2 API on loopback (`N3E_DISCORD_API`): it issues codes bound to a
PKCE challenge, checks the client secret and verifier at the token endpoint, and
answers `/users/@me`. Peers send `DiscordLogin` / `SessionLogin` the way the client
does after its browser step. Covers spec 02 acceptance tests 1-9 at the wire (test 1
against the stand-in, not a real Discord application; test 10 is tests/check.py),
the roadmap M3 done-when (a session reconnects 30 days on with the clock advanced in
the database; a `ban` over curl ends the live connection and refuses the token),
spec 03's account routes and their events, and the start-up refusals.
"""
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES
from world_peer import Peer, blob, first, DISCONNECTED

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
package = ROOT / "build/packages/demo"
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
CONTENT = (package / "release.sha256").read_text().strip()
name = "n3e-discord-" + uuid.uuid4().hex[:10]
out = ROOT / "build/live/discord-login"
out.mkdir(parents=True, exist_ok=True)
CLIENT_ID = "123456789012345678"
SECRET = "s3cret-" + secrets.token_hex(8)
REDIRECT = "http://127.0.0.1:49152/callback"


def run(*cmd, env=None, good=True):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    assert not good or p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Discord:
    """The OAuth2 stand-in. `authorize` is the browser step: it issues a code for a
    user, bound to the PKCE challenge and redirect URI the client sent."""

    def __init__(self):
        self.codes = {}
        self.access = {}
        self.issued = []  # every access token handed out, for the log check
        self.delay = 0.0
        self.lock = threading.Lock()
        discord = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                time.sleep(discord.delay)
                if self.path != "/api/oauth2/token":
                    return self.reply(404, {"message": "404: Not Found"})
                form = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode()))
                if form.get("client_id") != CLIENT_ID or form.get("client_secret") != SECRET:
                    return self.reply(401, {"error": "invalid_client"})
                with discord.lock:
                    grant = discord.codes.pop(form.get("code"), None)
                if (grant is None or form.get("grant_type") != "authorization_code"
                        or form.get("redirect_uri") != grant["redirect"]
                        or b64url(hashlib.sha256(form.get("code_verifier", "").encode()).digest()) != grant["challenge"]):
                    return self.reply(400, {"error": "invalid_grant", "error_description": 'Invalid "code" in request.'})
                token = "AT" + secrets.token_urlsafe(24)
                with discord.lock:
                    discord.access[token] = grant["user"]
                    discord.issued.append(token)
                self.reply(200, {"access_token": token, "token_type": "Bearer", "expires_in": 604800,
                                 "refresh_token": "RT" + secrets.token_urlsafe(24), "scope": "identify"})

            def do_GET(self):
                time.sleep(discord.delay)
                token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
                with discord.lock:
                    user = discord.access.get(token)
                if self.path != "/api/users/@me" or user is None:
                    return self.reply(401, {"message": "401: Unauthorized", "code": 0})
                self.reply(200, user)

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def authorize(self, user, challenge, redirect=REDIRECT):
        code = secrets.token_urlsafe(20)
        with self.lock:
            self.codes[code] = {"user": user, "challenge": challenge, "redirect": redirect}
        return code


def user(snowflake, global_name, username=None):
    return {"id": snowflake, "username": username or global_name.lower(), "global_name": global_name,
            "discriminator": "0", "avatar": None}


def receive_login(peer):
    """(LoginResult fields, Characters fields), or raise with the Error."""
    tag, data = peer.until(48, 4, seconds=15)
    assert tag == 48, ("refused", first(data, 1), first(data, 2, b"").decode())
    tag, characters = peer.until(6, 4)
    assert tag == 6, ("characters", characters)
    return data, characters


def refusal(peer, seconds=15):
    # One receive waits at most 4 s; a slow exchange is waited out across several.
    deadline = time.monotonic() + seconds
    while True:
        try:
            tag, data = peer.until(48, 6, 4, seconds=max(0.1, deadline - time.monotonic()))
            break
        except TimeoutError:
            assert time.monotonic() < deadline, "no reply"
    assert tag == 4, ("expected a refusal", tag, data)
    return first(data, 1), first(data, 2, b"").decode()


def enter(peer, character, seconds=5):
    """Select `character`, waiting out the previous socket's leave and final save."""
    deadline = time.monotonic() + seconds
    while True:
        tag, data = peer.select(character)
        if tag == 10:
            return
        assert time.monotonic() < deadline, ("select", first(data, 2, b""))
        time.sleep(0.2)


def connect(source):
    return Peer(listen, content=CONTENT, game=manifest["game_id"], protocol=manifest["protocol_version"],
                source=source)


def discord_login(peer, who, verifier=None, label="test-host", challenge_from=None):
    """The client's flow after the browser: authorize (stand-in), then DiscordLogin."""
    verifier = verifier or b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256((challenge_from or verifier).encode()).digest())
    code = discord.authorize(who, challenge)
    peer.send(46, blob(1, code) + blob(2, verifier) + blob(3, REDIRECT) + blob(4, label))


def session_login(peer, token, label="test-host"):
    peer.send(47, blob(1, token) + blob(2, label))


def sql(query):
    return run("docker", "exec", name, "psql", "-U", "n3e", "-d", "n3e", "-Atc", query).stdout.strip()


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


def events():
    raw = run("docker", "exec", name + "-redis", "redis-cli", "--json", "XRANGE", "realm:events", "-", "+").stdout
    found = []
    for _, values in json.loads(raw or "[]"):
        f = dict(zip(values[::2], values[1::2]))
        found.append((f["type"], json.loads(f["data"])))
    return found


def closed_within(peer, seconds):
    """The Errors the server sent before it closed `peer`, which must happen in time."""
    errors, deadline = [], time.monotonic() + seconds
    while True:
        assert time.monotonic() < deadline, ("still open", errors)
        try:
            tag, data = peer.receive()
        except DISCONNECTED:
            return errors
        except TimeoutError:
            continue
        if tag == 4:
            errors.append((first(data, 1), first(data, 2, b"").decode()))


discord = Discord()
containers, server = [], None
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

    # 7b. Start-up refusals on prod: legacy login, a test Discord API, no Discord application.
    prod = {**env, "N3E_REALM": "prod"}
    for extra, says in [({"N3E_LEGACY_LOGIN": "1"}, "N3E_LEGACY_LOGIN=1 is refused with N3E_REALM=prod"),
                        ({}, "N3E_DISCORD_API is a test setting"),
                        ({"N3E_DISCORD_API": "", "DISCORD_CLIENT_SECRET": ""}, "required with N3E_REALM=prod")]:
        p = run(server_binary, env={**prod, **extra}, good=False)
        assert p.returncode != 0 and says in p.stderr, (extra, p.stderr)
    for bad in [{"N3E_LEGACY_LOGIN": "yes"}, {"N3E_SESSION_TTL_DAYS": "0"}, {"N3E_SESSION_MAX_PER_ACCOUNT": "x"},
                {"N3E_DISCORD_API": "http://discord.com/api"}]:
        p = run(server_binary, env={**env, **bad}, good=False)
        assert p.returncode != 0, (bad, p.stderr)
    print("PASS start-up refusals: legacy login, N3E_DISCORD_API and a missing Discord application on prod; bad values")

    log = open(out / "server.log", "w")
    server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
    ops = run(server_binary, "admin", "mint", "--name", "ops", "--perm", "realm.status", env=env).stdout.strip()
    bot = run(server_binary, "admin", "mint", "--name", "bot", "--perm", "account.*", env=env).stdout.strip()
    deadline = time.monotonic() + 60
    while True:
        assert server.poll() is None, (out / "server.log").read_text()
        try:
            if call("GET", "/v1/realm/status", ops)[1].get("ready"):
                break
        except (urllib.error.URLError, ConnectionError):
            pass
        assert time.monotonic() < deadline, "server not ready"
        time.sleep(0.2)
    tokens = []  # every session token minted, for the log check

    # 1. First login: LoginResult (the raw token) then Characters; one account, one session.
    nelly = user("80351110224678912", "Nelly")
    p = connect("127.0.0.11")
    started = time.time()
    discord_login(p, nelly, label="nelly-pc\x07")
    result, characters = receive_login(p)
    token = first(result, 1, b"")
    tokens.append(token)
    expires = first(result, 2)
    assert len(token) == 32 and first(result, 3, b"").decode() == nelly["id"], result
    assert first(result, 4, b"").decode() == "Nelly", result
    assert abs(expires - (started + 30 * 86400)) < 120, (expires, started)
    p.tend()
    rows = sql(f"SELECT id,name,discord_name,password_hash IS NULL FROM accounts WHERE discord_id='{nelly['id']}'")
    nelly_id, account_name, shown, no_password = rows.split("|")
    assert (account_name, shown, no_password) == ("d" + nelly["id"], "Nelly", "t"), rows
    stored = sql(f"SELECT encode(token_hash,'hex'),client_label FROM sessions WHERE account_id={nelly_id}")
    assert stored == hashlib.sha256(token).hexdigest() + "|nelly-pc", stored
    print("PASS 1 first login: 32-byte token, expires in 30 days, LoginResult before Characters, "
          "account d<discord_id>, one session row holding sha256(token), label sanitised")

    # The player creates a character and enters the world.
    character = p.create("Nelly")
    tag, _ = p.select(character)
    assert tag == 10
    code, a = call("GET", f"/v1/accounts/{nelly_id}", bot)
    assert code == 200 and a["discord_id"] == nelly["id"] and a["discord_name"] == "Nelly" and a["online"], a
    assert a["sessions"] == 1 and a["characters"] == [{"id": character, "name": "Nelly"}] and a["banned_at"] is None, a
    assert call("GET", f"/v1/accounts/by-discord/{nelly['id']}", bot) == (200, a)
    assert call("GET", "/v1/accounts/by-discord/1", bot)[0] == 404
    assert call("GET", "/v1/accounts/999999", bot)[0] == 404
    assert call("GET", "/v1/accounts/x", bot)[0] == 404
    assert call("GET", f"/v1/accounts/{nelly_id}", ops) == (403, {"error": "forbidden", "detail": "needs account.lookup"})
    print("PASS account lookup by id and by Discord id: sessions, online, characters; 404s; permission checked")
    p.send(12)
    p.s.close()

    # 2. Reconnect with the token, no Discord: Characters arrives, last_seen_at advances.
    seen = sql(f"SELECT last_seen_at FROM sessions WHERE account_id={nelly_id}")
    calls = len(discord.issued)
    time.sleep(0.05)
    p = connect("127.0.0.11")
    session_login(p, token, label="nelly-laptop")
    result, characters = receive_login(p)
    assert first(result, 1, b"") == b"" and first(result, 2) == expires, result
    assert first(result, 3, b"").decode() == nelly["id"] and first(result, 4, b"").decode() == "Nelly", result
    assert len(discord.issued) == calls, "a session login asked Discord"
    later = sql(f"SELECT last_seen_at>'{seen}'::timestamptz,client_label FROM sessions WHERE account_id={nelly_id}")
    assert later == "t|nelly-laptop", later
    p.s.close()
    print("PASS 2 reconnect: SessionLogin -> LoginResult (no new token) then Characters; Discord not asked; "
          "last_seen_at advanced")

    # Roadmap M3: 30 days on (the clock advanced in the database) the token still logs in.
    sql(f"UPDATE sessions SET created_at=now()-interval '29 days 23 hours', expires_at=now()+interval '1 hour', "
        f"last_seen_at=now()-interval '29 days' WHERE account_id={nelly_id}")
    p = connect("127.0.0.11")
    session_login(p, token)
    receive_login(p)
    p.s.close()
    print("PASS a token minted 29 days 23 hours ago logs in without Discord")

    # 3. Expiry: `expired`, the row is gone, the Discord flow works again.
    sql(f"UPDATE sessions SET expires_at=now()-interval '1 second' WHERE account_id={nelly_id}")
    p = connect("127.0.0.11")
    session_login(p, token)
    assert refusal(p) == (5, "expired")
    assert sql(f"SELECT count(*) FROM sessions WHERE account_id={nelly_id}") == "0"
    session_login(p, token)
    assert refusal(p) == (5, "revoked")
    discord_login(p, nelly)
    result, _ = receive_login(p)
    token = first(result, 1, b"")
    tokens.append(token)
    p.s.close()
    print("PASS 3 expiry: expired, row deleted, then revoked; a fresh Discord login on the same socket succeeds")

    # 4. Cap: six Discord logins leave the newest five.
    cap = user("80351110224678913", "Capped")
    minted = []
    for i in range(6):
        p = connect("127.0.0.12")
        discord_login(p, cap, label=f"device-{i}")
        minted.append(first(receive_login(p)[0], 1, b""))
        p.s.close()
        time.sleep(0.01)
    tokens.extend(minted)
    p = connect("127.0.0.13")
    session_login(p, minted[0])
    assert refusal(p) == (5, "revoked")
    p.s.close()
    for t in minted[1:]:
        p = connect("127.0.0.13")
        session_login(p, t)
        receive_login(p)
        p.s.close()
    count = sql(f"SELECT count(*) FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE a.discord_id='{cap['id']}'")
    assert count == "5", count
    print("PASS 4 cap: six sessions -> the oldest revoked, five work, five rows")

    # Discord failures: a wrong verifier (PKCE) and a slow API.
    p = connect("127.0.0.14")
    discord_login(p, nelly, challenge_from="not-the-verifier-" + "x" * 40)
    assert refusal(p) == (5, "discord:invalid_grant")
    p.send(46, blob(1, "c") + blob(2, "short") + blob(3, REDIRECT))
    assert refusal(p) == (5, "discord:invalid_request")
    p.s.close()
    discord.delay = 12
    p = connect("127.0.0.14")
    t0 = time.monotonic()
    discord_login(p, nelly)
    assert refusal(p, seconds=20) == (5, "discord:unavailable")
    slow = time.monotonic() - t0
    assert 9.5 < slow < 12, slow
    discord.delay = 0
    p.s.close()
    p = connect("127.0.0.14")
    session_login(p, token)
    receive_login(p)
    p.s.close()
    print(f"PASS Discord failures: a wrong PKCE verifier is discord:invalid_grant, a bad request "
          f"discord:invalid_request, a slow API discord:unavailable after {slow:.1f} s; token holders unaffected")

    # 5. Ban: the live connection closes within 1 s with kicked:, the token and Discord are refused, unban works.
    p = connect("127.0.0.15")
    session_login(p, token)
    receive_login(p)
    p.tend()
    enter(p, character)
    t0 = time.monotonic()
    code, body = call("POST", f"/v1/accounts/{nelly_id}/ban", bot, {"reason": "cheating", "until": None})
    assert (code, body) == (200, {"banned_until": None, "connections_closed": 1}), (code, body)
    errors = closed_within(p, 1.0)
    took = time.monotonic() - t0
    assert (5, "kicked:cheating") in errors, errors
    p = connect("127.0.0.15")
    session_login(p, token)
    assert refusal(p) == (5, "revoked")  # the ban deleted every session
    discord_login(p, nelly)
    assert refusal(p) == (5, "banned:perm:cheating")
    assert call("POST", f"/v1/accounts/{nelly_id}/unban", bot, {}) == (200, {"banned": False})
    discord_login(p, nelly)
    result, _ = receive_login(p)
    token = first(result, 1, b"")
    tokens.append(token)
    p.s.close()
    # A timed ban names its end; a token minted before it is refused with it.
    until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    assert call("POST", f"/v1/accounts/{nelly_id}/ban", bot, {"reason": "spam", "until": until}) == (
        200, {"banned_until": until, "connections_closed": 0})
    sql(f"INSERT INTO sessions(token_hash,account_id,expires_at) VALUES "
        f"(sha256('\\x{'ab' * 32}'::bytea),{nelly_id},now()+interval '1 day')")
    p = connect("127.0.0.15")
    session_login(p, bytes.fromhex("ab" * 32))
    assert refusal(p) == (5, f"banned:{until}:spam")
    assert sql(f"SELECT count(*) FROM sessions WHERE account_id={nelly_id}") == "0"
    discord_login(p, nelly)
    assert refusal(p) == (5, f"banned:{until}:spam")
    assert call("POST", f"/v1/accounts/{nelly_id}/ban", bot, {"reason": "x", "until": "2001-01-01T00:00:00Z"})[0] == 400
    assert call("POST", f"/v1/accounts/{nelly_id}/ban", bot, {"reason": "x", "until": "tomorrow"})[0] == 400
    assert call("POST", f"/v1/accounts/{nelly_id}/ban", bot, {"until": None})[0] == 400
    assert call("POST", "/v1/accounts/999999/ban", bot, {"reason": "x"})[0] == 404
    assert call("POST", f"/v1/accounts/{nelly_id}/unban", bot)[0] == 200
    discord_login(p, nelly)
    result, _ = receive_login(p)
    token = first(result, 1, b"")
    tokens.append(token)
    p.s.close()
    print(f"PASS 5 ban: live connection closed {took * 1000:.0f} ms after the call with kicked:cheating; "
          "old token revoked, Discord login banned:perm:cheating; unban lets it in; a timed ban names its end")

    # 6. Kick: the connection closes, the next Discord login succeeds, the old token is revoked.
    p = connect("127.0.0.16")
    session_login(p, token)
    receive_login(p)
    p.tend()
    second = connect("127.0.0.16")
    session_login(second, token)
    receive_login(second)
    second.tend()
    code, body = call("POST", f"/v1/accounts/{nelly_id}/kick", bot, {"reason": "afk"})
    assert (code, body) == (200, {"connections_closed": 2}), (code, body)
    assert (5, "kicked:afk") in closed_within(p, 1.0)
    assert (5, "kicked:afk") in closed_within(second, 1.0)
    p = connect("127.0.0.16")
    session_login(p, token)
    assert refusal(p) == (5, "revoked")
    discord_login(p, nelly)
    result, _ = receive_login(p)
    token = first(result, 1, b"")
    tokens.append(token)
    p.s.close()
    assert call("POST", f"/v1/accounts/{nelly_id}/kick", bot, {}) == (
        400, {"error": "bad_request", "detail": "reason is required"})
    print("PASS 6 kick: both sockets of the account closed with kicked:afk; "
          "old token revoked; the next Discord login succeeds")

    # Mute: chat is dropped server-side, the player told once; unmute restores it.
    watcher_user = user("80351110224678914", "Watcher")
    w = connect("127.0.0.17")
    discord_login(w, watcher_user)
    tokens.append(first(receive_login(w)[0], 1, b""))
    w.tend()
    tag, _ = w.select(w.create("Watcher"))
    assert tag == 10
    p = connect("127.0.0.17")
    session_login(p, token)
    receive_login(p)
    p.tend()
    enter(p, character)
    assert call("POST", f"/v1/accounts/{nelly_id}/mute", bot, {"reason": "shouting", "until": None}) == (
        200, {"muted_until": None})

    def heard(peer, text, seconds=2.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                tag, data = peer.receive()
            except TimeoutError:
                continue
            if tag == 11 and first(data, 1, b"").decode() == text:
                return True
        return False

    p.send(11, blob(1, "first muted line"))
    tag, data = p.until(4, seconds=3)
    assert (first(data, 1), first(data, 2, b"").decode(), first(data, 3)) == (7, "muted:perm:shouting", 11), data
    time.sleep(1.1)
    p.send(11, blob(1, "second muted line"))
    assert not heard(w, "second muted line", 1.5)
    try:
        tag, data = p.until(4, seconds=1)
        raise AssertionError(("told twice", data))
    except TimeoutError:
        pass
    assert call("POST", f"/v1/accounts/{nelly_id}/unmute", bot, {}) == (200, {"muted": False})
    p.send(11, blob(1, "audible again"))
    assert heard(w, "audible again", 3)
    # A mute set before login is read at login.
    p.send(12)
    p.s.close()
    call("POST", f"/v1/accounts/{nelly_id}/mute", bot, {"reason": "again", "until": until})
    p = connect("127.0.0.17")
    session_login(p, token)
    receive_login(p)
    p.tend()
    enter(p, character)
    p.send(11, blob(1, "muted at login"))
    tag, data = p.until(4, seconds=3)
    assert first(data, 2, b"").decode() == f"muted:{until}:again", data
    call("POST", f"/v1/accounts/{nelly_id}/unmute", bot, {})
    p.send(12)
    p.s.close()
    w.send(12)
    w.s.close()
    print("PASS mute: chat dropped server-side, the player told once (FORBIDDEN, request 11), others hear nothing; "
          "unmute restores chat; a mute set while offline applies at login")

    # 7a. Legacy Login is refused without N3E_LEGACY_LOGIN.
    p = connect("127.0.0.18")
    p.send(5, blob(1, "legacy") + blob(2, "a long test password"))
    assert refusal(p) == (5, "legacy login disabled")
    p.s.close()
    print("PASS 7 legacy Login refused with UNAUTHENTICATED without N3E_LEGACY_LOGIN (and refused at start on prod)")

    # 8. Throttle: the 31st SessionLogin from one IP within a minute is RATE_LIMITED.
    p = connect("127.0.0.19")
    for i in range(30):
        session_login(p, secrets.token_bytes(32))
        assert refusal(p) == (5, "revoked"), i
    session_login(p, secrets.token_bytes(32))
    assert refusal(p) == (4, "login rate limit")
    p.s.close()
    q = connect("127.0.0.20")
    session_login(q, token)
    receive_login(q)
    q.s.close()
    print("PASS 8 throttle: 30 SessionLogins from one IP answered, the 31st RATE_LIMITED; another IP unaffected")

    # Spec 03 events for the account routes and the player's sessions.
    seen = events()
    kinds = [t for t, _ in seen]
    for kind in ["account.banned", "account.unbanned", "account.kicked", "account.muted", "account.unmuted",
                 "player.joined", "player.left"]:
        assert kind in kinds, (kind, kinds)
    banned = next(d for t, d in seen if t == "account.banned")
    assert banned == {"account_id": int(nelly_id), "discord_name": "Nelly", "reason": "cheating", "until": None,
                      "by": "bot"}, banned
    kicked = next(d for t, d in seen if t == "account.kicked")
    assert kicked == {"account_id": int(nelly_id), "discord_name": "Nelly", "reason": "afk", "by": "bot"}, kicked
    left = next(d for t, d in seen if t == "player.left" and d["discord_name"] == "Nelly")
    assert left["account_id"] == int(nelly_id) and isinstance(left["seconds"], int), left
    print("PASS realm:events: account.banned/unbanned/kicked/muted/unmuted with by, player.joined/left with discord_name")

    # 9. No secrets in the server's log: session tokens, Discord access tokens, the client secret.
    text = (out / "server.log").read_text(errors="replace")
    secrets_seen = [SECRET] + discord.issued
    for t in tokens:
        secrets_seen += [t.hex(), b64url(t), base64.b64encode(t).decode()]
    leaks = [s for s in secrets_seen if s and s in text]
    assert not leaks, leaks
    assert "discord exchange: invalid_grant" in text and "discord exchange: unavailable" in text, text
    print(f"PASS 9 no secrets in the server log ({len(secrets_seen)} values checked); Discord failures are logged "
          "by reason only")
    # The game client's side (N3E_GRAPHICAL=1, make live's default): realm.json, the
    # PKCE authorize address, the loopback callback, session.json, then a restart
    # that logs in without Discord, and a server-side expiry that sends it back.
    if "--graphical" in sys.argv or os.environ.get("N3E_GRAPHICAL") == "1":
        client_user = user("80351110224678915", "Wanderer")
        p = connect("127.0.0.21")  # the account and its character exist before the client's login
        discord_login(p, client_user)
        tokens.append(first(receive_login(p)[0], 1, b""))
        p.tend()
        p.create("Wanderer")
        p.send(12)
        p.s.close()
        home = out / "client-home"
        subprocess.run(["rm", "-rf", str(home)])
        (home / "config").mkdir(parents=True)
        realm_json = home / "realm.json"
        realm_json.write_text(json.dumps({"id": "test-realm", "name": "Test Realm", "host": "localhost",
                                          "port": listen, "discord_client_id": CLIENT_ID}))
        session_json = home / "config/n3e-realm/test-realm/session.json"

        def client(run_name, browse):
            """Run the client; `browse` plays the browser on the address it prints."""
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
            code = proc.wait(timeout=60)
            log_path.write_text("".join(lines))
            text = "".join(lines)
            assert code == 0 and "ENTERED map" in text, (run_name, code, text[-3000:])
            return urls

        def browser(url):
            parsed = urllib.parse.urlsplit(url)
            q = dict(urllib.parse.parse_qsl(parsed.query))
            assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://discord.com/oauth2/authorize", url
            assert (q["client_id"], q["response_type"], q["scope"], q["code_challenge_method"], q["prompt"]) == (
                CLIENT_ID, "code", "identify", "S256", "none"), q
            assert q["redirect_uri"].startswith("http://127.0.0.1:4915") and q["redirect_uri"].endswith("/callback"), q
            stale = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "x", "state": "not-the-state"})
            try:
                urllib.request.urlopen(stale, timeout=5)
                raise AssertionError("a wrong state was accepted")
            except urllib.error.HTTPError as e:
                assert e.code == 400, e.code
            code = discord.authorize(client_user, q["code_challenge"], q["redirect_uri"])
            back = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": code, "state": q["state"]})
            with urllib.request.urlopen(back, timeout=5) as r:
                assert r.status == 200 and b"You are logged in" in r.read()

        def no_browser(url):
            raise AssertionError(("the client asked Discord again", url))

        assert len(client("first", browser)) == 1
        stored = json.loads(session_json.read_text())
        assert oct(session_json.stat().st_mode & 0o777) == "0o600", oct(session_json.stat().st_mode)
        raw = base64.urlsafe_b64decode(stored["token"] + "==")
        tokens.append(raw)
        assert len(raw) == 32 and stored["discord_name"] == "Wanderer", stored
        assert sql(f"SELECT count(*) FROM sessions WHERE token_hash=sha256('\\x{raw.hex()}'::bytea)") == "1"
        client_account = sql(f"SELECT id FROM accounts WHERE discord_id='{client_user['id']}'")
        sessions_before = sql(f"SELECT count(*) FROM sessions WHERE account_id={client_account}")
        print("PASS client first login: realm.json, the authorize address (identify, S256, prompt=none), "
              "a stale state refused, the callback answered, session.json mode 0600 holding the token, world entered")
        seen = sql(f"SELECT last_seen_at FROM sessions WHERE token_hash=sha256('\\x{raw.hex()}'::bytea)")
        assert client("second", no_browser) == []
        assert sql(f"SELECT count(*) FROM sessions WHERE account_id={client_account}") == sessions_before
        assert sql(f"SELECT last_seen_at>'{seen}'::timestamptz FROM sessions "
                   f"WHERE token_hash=sha256('\\x{raw.hex()}'::bytea)") == "t"
        print("PASS client restart: no browser, the stored token logs in, last_seen_at advanced, no new session")
        sql(f"UPDATE sessions SET expires_at=now()-interval '1 second' WHERE account_id={client_account}")
        assert len(client("expired", browser)) == 1
        renewed = json.loads(session_json.read_text())
        assert renewed["token"] != stored["token"], renewed
        tokens.append(base64.urlsafe_b64decode(renewed["token"] + "=="))
        print("PASS client expiry: the server says expired, the client drops session.json and runs the browser flow")
        text = (out / "server.log").read_text(errors="replace")
        for t in tokens[-2:]:
            assert t.hex() not in text and b64url(t) not in text
    assert server.poll() is None, "server exited"
    print("DISCORD_LOGIN_OK")
finally:
    if server is not None:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    discord.http.shutdown()
    for c in containers:
        subprocess.run(["docker", "rm", "-f", c], capture_output=True)
