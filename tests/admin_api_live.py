"""Admin API, admin tokens and the event stream (specs/03-admin-api.md, roadmap M1).

Starts the native server against a disposable Postgres and Redis and drives the
loopback admin listener the way the Bot and CD will: token mint/revoke/list,
bearer auth and per-route permissions, drain/resume, deploy-pending, in-game
notices to a logged-in peer, the `realm:events` stream, a public listen address
refused at start, Redis and Postgres down, and the tick under status polling. Acceptance
tests 1-5, 6b (notice), 8, 9 and 10 of spec 03; the motd and world routes answer 501
until their milestones (account routes: tests/discord_login_live.py).
"""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
from world_peer import Peer, first

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
package = ROOT / "build/packages/demo"
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
name = "n3e-admin-api-" + uuid.uuid4().hex[:10]
out = ROOT / "build/live/admin-api"
out.mkdir(parents=True, exist_ok=True)


def run(*cmd, env=None, good=True, stdin=None):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120, input=stdin)
    assert not good or p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def call(port, method, path, token=None, body=None):
    """(status, parsed JSON or None) of one admin request."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method)
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            text = r.read()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read()
        e.close()
        return e.code, (json.loads(text) if text else None)


def events(redis_container):
    """[(type, data)] of realm:events, oldest first."""
    raw = run("docker", "exec", redis_container, "redis-cli", "--json", "XRANGE", "realm:events", "-", "+").stdout
    found = []
    for _, values in json.loads(raw or "[]"):
        f = dict(zip(values[::2], values[1::2]))
        found.append((f["type"], json.loads(f["data"])))
    return found


def wait_for(what, check, seconds=15):
    deadline = time.monotonic() + seconds
    while True:
        got = check()
        if got:
            return got
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.1)


def start(env, log_name):
    log = open(out / log_name, "w")
    return subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)


containers = []
servers = []
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
    env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
               REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM=f"test-{name}",
               N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}",
               N3E_ADMIN_LISTEN=f"127.0.0.1:{admin}")
    run(server_binary, "migrate", env=env)
    run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})

    # 8. A public admin address is refused before anything starts.
    refused = run(server_binary, env={**env, "N3E_ADMIN_LISTEN": "0.0.0.0:7780"}, good=False)
    assert refused.returncode != 0 and "not loopback or RFC 1918" in refused.stderr, refused.stderr
    print("PASS a public N3E_ADMIN_LISTEN refuses to start")

    # 3. CLI: mint prints the token once; a second mint exits 2; list shows no secret.
    def mint(token_name, *perms):
        p = run(server_binary, "admin", "mint", "--name", token_name, *[a for q in perms for a in ("--perm", q)],
                env=env, good=False)
        return p.returncode, p.stdout.strip()

    code, status_token = mint("t", "realm.status")
    assert code == 0 and len(status_token) == 43, (code, status_token)
    assert mint("t", "realm.status")[0] == 2
    code, ops_token = mint("ops", "realm.*")
    assert code == 0
    listed = run(server_binary, "admin", "list", env=env).stdout
    assert "ops\trealm.status,realm.drain,realm.notice,realm.deploy\t" in listed, listed
    assert status_token not in listed and ops_token not in listed and "\\x" not in listed, listed
    print("PASS admin mint/list: token printed once, globs expanded, second mint exits 2, list has no secret")

    servers.append(start(env, "server.log"))
    def booted():
        assert servers[0].poll() is None, (out / "server.log").read_text()
        try:
            return call(admin, "GET", "/v1/realm/status", ops_token)[1].get("ready")
        except (urllib.error.URLError, ConnectionError):
            return False
    wait_for("ready", booted, seconds=60)

    # 1-2. Permissions and authentication.
    code, s = call(admin, "GET", "/v1/realm/status", status_token)
    assert code == 200 and s["ready"] and not s["draining"] and s["redis"] and s["players"] == 0, (code, s)
    assert s["content_hash"] == (package / "release.sha256").read_text().strip(), s
    assert call(admin, "POST", "/v1/realm/drain", status_token, {}) == (403, {"error": "forbidden",
                                                                            "detail": "needs realm.drain"})
    assert call(admin, "GET", "/v1/realm/status")[0] == 401
    assert call(admin, "GET", "/v1/realm/status", "A" * 43)[0] == 401
    assert call(admin, "GET", "/v1/realm/status", "not a token")[0] == 401
    assert call(admin, "GET", "/v1/nowhere", ops_token)[0] == 404
    assert call(admin, "DELETE", "/v1/realm/status", ops_token)[0] == 405
    assert call(admin, "GET", "/v1/world/catalog", ops_token)[0] == 403
    print("PASS realm.status token: status 200, drain 403 naming realm.drain; missing/unknown 401; 404/405")

    run(server_binary, "admin", "revoke", "--name", "t", env=env)
    assert run(server_binary, "admin", "revoke", "--name", "t", env=env).returncode == 0
    revoked = time.monotonic()
    wait_for("revocation", lambda: call(admin, "GET", "/v1/realm/status", status_token)[0] == 401, seconds=12)
    took = time.monotonic() - revoked
    assert took <= 11, took
    assert mint("t", "realm.status")[0] == 0
    print(f"PASS revoke bites in {took:.1f} s (<= 10 s cache), repeat revoke exits 0, re-mint after revoke ok")

    # 6b. An in-game notice reaches a logged-in, in-world peer as Chat.notice.
    run(server_binary, "account-create", "listener", env=env, stdin="listener-password\n")
    peer = Peer(listen, "listener", "listener-password", content=s["content_hash"], game=manifest["game_id"],
                protocol=manifest["protocol_version"])
    peer.create("Listener")
    assert peer.select(peer.characters[0][0])[0] == 10
    assert call(admin, "GET", "/v1/realm/status", ops_token)[1]["players"] == 1
    for level, number in [("info", 1), ("warn", 2)]:
        text = f"Restart in 2 minutes ({level})"
        assert call(admin, "POST", "/v1/realm/notice", ops_token, {"text": text, "level": level})[0] == 202
        deadline = time.monotonic() + 5
        while True:
            assert time.monotonic() < deadline, f"no notice {text!r}"
            tag, data = peer.receive()
            f = data if tag == 11 else {}
            if tag == 11 and first(f, 1, b"").decode() == text:
                assert first(f, 6) == number and first(f, 2) == 0, f
                break
    assert call(admin, "POST", "/v1/realm/notice", ops_token, {"text": "x", "level": "loud"})[0] == 400
    assert call(admin, "POST", "/v1/realm/notice", ops_token, {"text": "a\nb"})[0] == 400
    assert call(admin, "POST", "/v1/realm/notice", ops_token, {"text": "y" * 501})[0] == 400
    assert call(admin, "POST", "/v1/realm/notice", ops_token, {"text": "Discord only", "in_game": False})[0] == 202
    print("PASS realm/notice: info -> Chat.notice 1, warn -> 2 to an in-world peer; bad level/text 400")

    # 4. Drain and resume, and their events.
    code, d = call(admin, "POST", "/v1/realm/drain", ops_token, {"reason": "deploy v-test"})
    assert code == 200 and d == {"draining": True, "players": 1}, d
    assert call(admin, "POST", "/v1/realm/drain", ops_token, {"reason": "again"})[0] == 200
    assert call(admin, "GET", "/v1/realm/status", ops_token)[1]["draining"] is True
    assert call(admin, "POST", "/v1/realm/resume", ops_token) == (200, {"draining": False})
    assert call(admin, "GET", "/v1/realm/status", ops_token)[1]["draining"] is False

    # 5. deploy-pending round trip; a PUT with the same head emits nothing.
    record = {"since": "2026-10-30T12:00:00Z", "commits_behind": 3, "head": "abc1234"}
    assert call(admin, "GET", "/v1/realm/deploy-pending", ops_token) == (204, None)
    assert call(admin, "PUT", "/v1/realm/deploy-pending", ops_token, record) == (200, record)
    assert call(admin, "PUT", "/v1/realm/deploy-pending", ops_token, {**record, "commits_behind": 4})[0] == 200
    assert call(admin, "GET", "/v1/realm/deploy-pending", ops_token) == (200, {**record, "commits_behind": 4})
    time.sleep(1.1)  # status reads deploy-pending through a one-second cache
    assert call(admin, "GET", "/v1/realm/status", ops_token)[1]["deploy_pending"]["head"] == "abc1234"
    assert call(admin, "PUT", "/v1/realm/deploy-pending", ops_token, {"since": "x", "head": "y"})[0] == 400
    assert call(admin, "DELETE", "/v1/realm/deploy-pending", ops_token) == (204, None)
    assert call(admin, "GET", "/v1/realm/deploy-pending", ops_token) == (204, None)
    print("PASS drain/resume idempotent; deploy-pending PUT/GET/DELETE round trip")

    seen = wait_for("events", lambda: (lambda e: e if any(t == "realm.resumed" for t, _ in e)
                                       and any(t == "deploy.pending" for t, _ in e) else None)(events(name + "-redis")))
    kinds = [t for t, _ in seen]
    assert kinds[0] == "realm.ready" and seen[0][1]["content_hash"] == s["content_hash"], seen[0]
    assert kinds.count("realm.draining") == 1 and kinds.count("realm.resumed") == 1, kinds
    draining = next(d for t, d in seen if t == "realm.draining")
    assert draining == {"reason": "deploy v-test", "players": 1, "by": "ops"}, draining
    assert kinds.count("deploy.pending") == 1, kinds
    notices = [d for t, d in seen if t == "notice"]
    assert [n["level"] for n in notices] == ["info", "warn", "info"] and notices[0]["by"] == "ops", notices
    print("PASS realm:events: realm.ready, one realm.draining{reason,players,by}, one realm.resumed, "
          "one deploy.pending for two PUTs of one head, notice{text,level,by}")

    # Routes in the contract whose milestones have not landed answer 501 behind their permission.
    code, bot_token = mint("bot", "world.catalog", "account.*", "realm.status")
    assert code == 0
    assert call(admin, "GET", "/v1/world/catalog", bot_token) == (501, {"error": "not_implemented"})
    # Account routes landed in M3 (tests/discord_login_live.py covers them).
    assert call(admin, "POST", "/v1/accounts/999999/kick", bot_token, {"reason": "x"}) == (404, {"error": "not_found"})
    print("PASS routes of later milestones answer 501 after the permission check; account routes are served")

    # 10. The tick is unaffected by status polling (the listener is off-tick).
    def metric(key):
        with urllib.request.urlopen(f"http://127.0.0.1:{health}/live", timeout=2) as r:
            return int(dict(p.split("=") for p in r.read().decode().split())[key])
    ticks_before = metric("ticks")
    started = time.monotonic()
    def poll_status(_):
        got = []
        while time.monotonic() - started < 5:
            got.append(call(admin, "GET", "/v1/realm/status", ops_token)[0])
        return got
    with concurrent.futures.ThreadPoolExecutor(16) as pool:
        codes = [c for got in pool.map(poll_status, range(16)) for c in got]
    elapsed = time.monotonic() - started
    ticks = metric("ticks") - ticks_before
    expected = elapsed / 0.05
    assert codes.count(200) == len(codes), {c: codes.count(c) for c in set(codes)}
    assert ticks >= 0.9 * expected - 2, (ticks, expected)
    assert metric("tick_max_us") < 50_000, metric("tick_max_us")
    print(f"PASS {len(codes) / elapsed:.0f} status calls/s for {elapsed:.1f} s: {ticks} ticks of {expected:.0f} "
          f"expected, tick_max_us {metric('tick_max_us')}")

    # 9. Redis down: status still 200, redis false; deploy-pending 503.
    run("docker", "pause", name + "-redis")
    wait_for("redis:false", lambda: call(admin, "GET", "/v1/realm/status", ops_token)[1]["redis"] is False)
    code, s = call(admin, "GET", "/v1/realm/status", ops_token)
    assert code == 200 and s["deploy_pending"] is None, s
    assert call(admin, "GET", "/v1/realm/deploy-pending", ops_token)[0] == 503
    assert call(admin, "POST", "/v1/realm/drain", ops_token, {"reason": "redis down"})[0] == 200
    run("docker", "unpause", name + "-redis")
    wait_for("redis back", lambda: call(admin, "GET", "/v1/realm/status", ops_token)[1]["redis"] is True)
    print("PASS Redis down: status 200 with redis:false, deploy-pending 503, drain still succeeds")
    peer.s.close()

    # 9. Postgres down: a token outside the cache is refused within the 2 s lookup
    # bound (docker's proxy keeps a paused database's socket open, so only that bound
    # ends the wait). The realm's 3 s lease (D-142) has lapsed by the time Postgres
    # answers again, so it is fenced and exits, without a panic.
    code, fresh = mint("fresh", "realm.status")
    assert code == 0
    run("docker", "pause", name)
    try:
        asked = time.monotonic()
        assert call(admin, "GET", "/v1/realm/status", fresh)[0] == 401
        refused_in = time.monotonic() - asked
        assert refused_in < 3, refused_in
        time.sleep(max(0.0, asked + 5 - time.monotonic()))  # past the lease
    finally:
        run("docker", "unpause", name)
    servers[0].wait(20)
    log = (out / "server.log").read_text()
    assert "realm fenced" in log and "panicked" not in log, log[-2000:]
    print(f"PASS Postgres down: uncached token 401 in {refused_in:.1f} s; realm fenced, exit "
          f"{servers[0].returncode}, no panic")
    print("ADMIN_API_OK")
finally:
    for s in servers:
        s.terminate()
        try:
            s.wait(10)
        except subprocess.TimeoutExpired:
            s.kill()
    for c in containers:
        container_logs(c, ["docker", "logs", "--timestamps", c])
        run("docker", "rm", "-f", c, good=False)
