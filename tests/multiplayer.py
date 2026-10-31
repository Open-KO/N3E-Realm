"""Phase 2 isolated real Compose acceptance. Never touches default volumes."""

import concurrent.futures
import hashlib
import http.client
import json
import os
import pathlib
import re
import socket
import ssl
import struct
import subprocess
import time
import uuid
from world_peer import DISCONNECTED, Peer, blob, integer, first
from readiness import wait_postgres
from isolation import DISPOSABLE_COMPOSE, container_logs
import schema

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
B = ROOT / "build/multiplayer"
B.mkdir(parents=True, exist_ok=True)
project = "n3e-p2-" + uuid.uuid4().hex[:10]
override = B / (project + ".yaml")
override.write_text(
    'services:\n  postgres:\n    ports: ["127.0.0.1::5432"]\n  server:\n    ports: ["127.0.0.1::8080"]\n'
)
if image := os.environ.get("N3E_TEST_IMAGE"):
    override.write_text(override.read_text().replace("  server:\n", f"  server:\n    image: {image}\n") + f"  migrate:\n    image: {image}\n")
env = {
    **os.environ,
    "N3E_PORT": "0",
    "N3E_PACKAGE_PATH": str(ROOT / "build/packages/legacy-demo"),
    "N3E_UID": str(os.getuid()),
    "N3E_GID": str(os.getgid()),
}
base = ["docker", "compose", *DISPOSABLE_COMPOSE, "-f", str(override), "-p", project]
password = "test-only-" + uuid.uuid4().hex


def cmd(*args, good=True, stdin=None):
    p = subprocess.run(
        list(map(str, args)),
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert not good or p.returncode == 0, (args, p.returncode, p.stdout, p.stderr)
    return p


def dc(*args, **kw):
    return cmd(*base, *args, **kw)


def sql(q):
    return dc(
        "exec", "-T", "postgres", "psql", "-U", "n3e", "-d", "n3e", "-Atc", q
    ).stdout.strip()


def ready():
    return (
        dc("exec", "-T", "server", "n3e-server", "health", good=False).returncode == 0
    )


def wait(f, seconds=40):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if f():
            return
        time.sleep(0.15)
    raise AssertionError("condition deadline")


def login(name):
    return Peer(port, name, password)


def refresh_port():
    return int(dc("port", "server", "7777").stdout.strip().rsplit(":", 1)[1])


def crash_restarts():
    """Postgres crash-restart lines so far (PQ-155): a backend, or an orphan
    the postmaster reaped, exited abnormally and every session was killed."""
    logs = dc("logs", "--no-color", "postgres").stdout
    return re.findall(r".*(?:terminating any other active server processes|exited with exit code (?:[2-9]|\d\d+)\b|was terminated by signal).*", logs)


try:
    # Upgrade an actual Phase 1 schema without altering its SQL/checksum.
    dc("up", "-d", "postgres", "redis")
    # A socket `SELECT 1` can reach the image's temporary init server, which then
    # shuts down under the next statement (PQ-116 run 4); wait for the real one.
    wait_postgres(dc("ps", "-q", "postgres").stdout.strip())
    original = pathlib.Path("deploy/001-foundation.sql").read_text()
    digest = hashlib.sha256(original.encode()).hexdigest()
    sql(
        "CREATE TABLE schema_migrations(version integer PRIMARY KEY,digest text NOT NULL);"
        + original
        + f"INSERT INTO schema_migrations VALUES(1,'{digest}')"
    )
    dc("up", "-d", "--no-build")
    wait(ready)
    port = refresh_port()
    assert sql(schema.QUERY).splitlines() == schema.rows()
    assert sql("SELECT digest FROM schema_migrations WHERE version=1") == digest
    dc("run", "--rm", "--no-deps", "migrate")
    for name in ["alpha", "beta", "gamma", "delta"]:
        dc(
            "run",
            "--rm",
            "-T",
            "--no-deps",
            "migrate",
            "account-create",
            name,
            stdin=password + "\n",
        )
    print(
        "PASS Phase 1 upgrade, idempotent migration, account provisioning", flush=True
    )
    a, b = login("alpha"), login("beta")
    aid, bid = a.create("Alpha"), b.create("Beta")
    assert a.select(bid)[0] == 4
    assert a.select(aid)[0] == 10 and b.select(bid)[0] == 10
    a.pump()
    b.pump()
    assert (
        sum(not first(e, 9) for e in a.entities.values())
        == sum(not first(e, 9) for e in b.entities.values())
        == 2
    )
    duplicate = login("alpha")
    assert duplicate.select(aid)[0] == 4
    duplicate.logout()
    a.move(1, 0)
    a.pump()
    b.pump()
    assert first(a.entities[a.id], 3) > 0 and first(b.entities[a.id], 3) > 0
    assert abs(first(a.entities[a.id], 3) - 0.15) < 1e-5
    for x, z, seq, session in [
        (9, 0, None, None),
        (float("nan"), 0, None, None),
        (float("inf"), 0, None, None),
        (0, 0, 2**64 - 1, None),
        (0, 0, 0, None),
        (0, 0, 1, None),
        (0, 0, None, a.session + 1),
    ]:
        a.move(x, z, seq, session)
        tag, e = a.until(4)
        assert first(e, 1) == 3
    a.send(11, blob(1, "hello world") + integer(2, 999999))
    chat = b.until(11)[1]
    assert chat[1][0] == b"hello world" and first(chat, 2) == a.id
    a.send(11, blob(1, "x" * 257))
    assert a.until(4)[0] == 4
    health_port = int(dc("port", "server", "8080").stdout.strip().rsplit(":", 1)[1])
    http = http.client.HTTPConnection("127.0.0.1", health_port, timeout=2)
    http.request("GET", "/live")
    response = http.getresponse()
    assert response.status == 200
    (B / "metrics.txt").write_text(response.read().decode())
    http.close()
    print(
        "PASS ownership, duplicate session, movement authority, finite/sequence/session checks, chat",
        flush=True,
    )
    # Walk to opposite ends of the original fixture; cell subscriptions disappear.
    for _ in range(30):
        a.move(1, 0)
        b.move(-1, 0)
        time.sleep(0.06)
    a.pump()
    b.pump()
    assert b.id not in a.entities and a.id not in b.entities
    for _ in range(8):
        a.move(-1, 0)
        b.move(1, 0)
        time.sleep(0.06)
    a.pump()
    b.pump()
    assert b.id in a.entities and a.id in b.entities
    position = first(a.entities[a.id], 3)
    old_session = a.session
    a.logout()
    assert abs(float(sql(f"SELECT x FROM characters WHERE id={aid}")) - position) < 1e-5
    a = login("alpha")
    assert a.select(aid)[0] == 10
    assert a.session > old_session
    assert abs(first(a.entities[a.id], 3) - position) < 1e-5
    print(
        "PASS interest leave/reenter, clean final save, fresh reconnect baseline",
        flush=True,
    )
    # Real Redis outage: existing peers continue; unauthenticated admission closes.
    dc("stop", "redis")
    wait(lambda: not ready())
    for _ in range(8):
        a.move(0.2, 0)
        b.send(14)
        a.pump(0.12)
    a.send(11, blob(1, "redis down"))
    assert b.until(11)[1][1][0] == b"redis down"
    rejected = False
    try:
        Peer(port)
    except AssertionError:
        rejected = True
    assert rejected
    dc("start", "redis")
    wait(ready)
    a.send(14)
    a.pump()
    assert dc(
        "exec", "-T", "redis", "redis-cli", "GET", f"n3e:local:presence:{aid}"
    ).stdout.strip() == str(a.session)
    a.logout()
    b.logout()
    print(
        "PASS Redis outage active movement/chat survival, fail-closed admission, presence recovery",
        flush=True,
    )
    # Two real graphical clients, same production network/render path.
    if os.environ.get("N3E_GRAPHICAL") == "1":
        children = []
        for name in ["alpha", "beta"]:
            output = open(B / f"{name}-graphics.txt", "w")
            child = subprocess.Popen(
                [
                    "build/client/n3e-test-client",
                    "build/packages/legacy-demo",
                    "--connect",
                    f"localhost:{port}",
                    "--ca",
                    "deploy/local/ca.pem",
                    "--world-smoke",
                    "5",
                    "--capture",
                    str(B / f"{name}.ppm"),
                ],
                env={**env, "N3E_TEST_ACCOUNT": name, "N3E_TEST_PASSWORD": password},
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            children.append((child, output))
        for child, output in children:
            assert child.wait(timeout=20) == 0
            output.close()
        print(
            "PASS two simultaneous graphical clients rendered networked entities",
            flush=True,
        )
    # A duplicate realm process waits out its start-up window (D-139) against
    # the live owner's renewals and is refused; nothing is taken over. Before
    # the alpha session: an idle character can die to an NPC in those 5 s.
    before = int(sql("SELECT generation FROM realm_ownership WHERE realm='local'"))
    duplicate = dc("run", "--rm", "--no-deps", "server", good=False)
    assert duplicate.returncode != 0, duplicate.stderr
    # Each takeover attempt locks the fence row behind the owner's open fenced
    # transaction, and its upsert locks the lease row behind the owner's
    # renewal while that commits (D-145). Under the 4-job load such a commit
    # can pass the 800 ms lock_timeout (in a PQ-196 full run the upsert timed
    # out on the lease row), and the attempt is then refused with that lock
    # timeout (55P03) instead. Either way it is refused and takes nothing over
    # (checked below).
    assert (
        "already owned" in duplicate.stderr and "waiting up to" in duplicate.stderr
    ) or (
        "E55P03" in duplicate.stderr
        and ("realm_ownership" in duplicate.stderr or "realm_fence" in duplicate.stderr)
    ), duplicate.stderr
    assert int(sql("SELECT generation FROM realm_ownership WHERE realm='local'")) == before
    assert ready()
    a = login("alpha")
    assert a.select(aid)[0] == 10
    for _ in range(6):
        a.move(-0.4, 0)
        a.pump(0.12)
    a.pump(2.2)
    durable = float(sql(f"SELECT x FROM characters WHERE id={aid}"))
    dc("kill", "-s", "SIGKILL", "server")
    a.s.close()
    # PQ-153 (D-139): restart inside the dead owner's lease. A late renewal of
    # the killed process left it live; here it is set once, before the start,
    # long enough to outlast any container start under load (one start
    # outlasted a 3 s lease, PQ-196). Start-up's attempts each sleep at most
    # 3 s, so it keeps waiting inside START_WAIT. Once it announces that it
    # waits the lease is ended, and start-up must then take over rather than
    # exit with "realm already owned". No lease write runs while the restart
    # makes its first attempt, so that attempt never queues behind a renewal
    # commit (PQ-196 review).
    def dead_lease(expires):
        assert sql(
            f"UPDATE realm_ownership SET expires={expires} "
            "WHERE realm='local' RETURNING generation"
        ).splitlines()[0] == str(before)

    dead_lease("clock_timestamp()+interval '60 seconds'")
    dc("start", "server")
    announced = time.monotonic() + 30
    while "waiting up to" not in dc("logs", "--no-color", "server").stdout:
        assert time.monotonic() < announced, "restarted realm never waited"
        time.sleep(0.2)
    dead_lease("clock_timestamp()")
    wait(ready)
    port = refresh_port()
    a = login("alpha")
    assert a.select(aid)[0] == 10
    assert abs(first(a.entities[a.id], 3) - durable) < 1e-5
    assert (
        int(sql("SELECT generation FROM realm_ownership WHERE realm='local'")) > before
    )
    a.logout()
    print(
        "PASS duplicate realm rejection, crash checkpoint recovery and generation takeover",
        flush=True,
    )
    # Library tests exercise delayed old-session/owner writes under DB locks.
    # Feature suites own their fixture packages and fault workers; run only the
    # shared-schema tests here (tests/schema.py CORE_TESTS).
    pgport = int(dc("port", "postgres", "5432").stdout.strip().rsplit(":", 1)[1])
    env["N3E_TEST_DATABASE_URL"] = (
        f"host=127.0.0.1 port={pgport} user=n3e password=n3e-local dbname=n3e"
    )
    database = cmd(*schema.core_test_command()).stdout
    (B / "database-tests.txt").write_text(database)
    schema.assert_core_tests(database)
    a = login("alpha")
    a.select(aid)
    dc("pause", "postgres")
    try:
        wait(lambda: not ready(), 6)
    finally:
        dc("unpause", "postgres")
    a.s.close()
    dc("restart", "server")
    wait(ready)
    port = refresh_port()
    assert not crash_restarts(), crash_restarts()
    print(
        "PASS Postgres outage bounded admission shutdown and explicit restart",
        flush=True,
    )
    # PQ-155 (D-140): a process orphaned inside the Postgres container (Docker
    # killing a health probe's shell on a timeout or a pause left pg_isready,
    # which exits 2) must never be reaped by the postmaster, which takes a
    # child's exit status 2 for a crashed backend and restarts the cluster
    # under the live realm.
    orphan = dc(
        "exec", "-T", "postgres", "sh", "-c", "(sleep 0.3; exit 2) >/dev/null 2>&1 & echo $!"
    ).stdout.strip()
    assert orphan.isdigit(), orphan
    wait(
        lambda: dc("exec", "-T", "postgres", "test", "-e", f"/proc/{orphan}", good=False).returncode
        != 0,
        10,
    )
    time.sleep(0.5)  # wall: a renewal (every 400 ms) crosses the reap
    assert not crash_restarts(), crash_restarts()
    assert ready()
    print("PASS orphan exiting 2 in the Postgres container leaves the cluster and realm up", flush=True)
    # PQ-155 (D-140): a realm started while Postgres refuses connections with
    # 57P03 (crash recovery, start-up) waits for it inside the start-up window.
    # A standby without hot standby holds that refusal until promoted.
    before = int(sql("SELECT generation FROM realm_ownership WHERE realm='local'"))
    dc("stop", "server")
    sql("ALTER SYSTEM SET hot_standby = off")
    dc("exec", "-T", "postgres", "sh", "-c", 'touch "$PGDATA/standby.signal"')
    dc("restart", "postgres")
    wait(
        lambda: "not accepting connections"
        in dc("exec", "-T", "postgres", "psql", "-U", "n3e", "-d", "n3e", "-c", "SELECT 1", good=False).stderr,
        30,
    )
    # Driven through the container IDs, not Compose: Compose would gate the
    # start on its dependencies' health, and its CLI start-up per call would
    # spend the 5 s window this phase must promote inside.
    server_id = dc("ps", "-aq", "server").stdout.strip()
    postgres_id = dc("ps", "-q", "postgres").stdout.strip()
    retrying = "postgres is not accepting connections yet"
    seen = cmd("docker", "logs", server_id).stderr.count(retrying)
    cmd("docker", "start", server_id)
    wait(lambda: cmd("docker", "logs", server_id).stderr.count(retrying) > seen, 4)
    cmd("docker", "exec", "-u", "postgres", postgres_id, "sh", "-c", 'pg_ctl promote -W -D "$PGDATA"')
    wait(ready)
    sql("ALTER SYSTEM RESET hot_standby")
    assert int(sql("SELECT generation FROM realm_ownership WHERE realm='local'")) > before
    port = refresh_port()
    a = login("alpha")
    assert a.select(aid)[0] == 10
    a.logout()
    print("PASS realm start-up waits for Postgres to accept connections (57P03)", flush=True)
    # Hostile frames, partial trickle and input limits; independent connections survive.
    for data in [
        bytes(4),
        struct.pack(">I", 65537),
        struct.pack(">I", 100) + b"x",
        struct.pack(">I", 1) + b"\xff",
    ]:
        p = Peer(port)
        p.s.sendall(data)
        start = time.monotonic()
        try:
            closed = not p.s.recv(4)
        except (OSError, ssl.SSLError):
            closed = True
        assert closed and time.monotonic() - start < 3.5
        p.s.close()
    p = Peer(port)
    for _ in range(18):
        p.raw(blob(31, b"x" * 60000))
        tag, e = p.receive()
    assert tag == 4 and first(e, 1) == 4
    p.s.close()
    p = Peer(port)
    p.s.sendall(b"".join(struct.pack(">I", 2) + blob(14, b"") for _ in range(101)))
    assert first(p.until(4)[1], 1) == 4
    p.s.close()
    print("PASS hostile framing, byte accounting and frame-rate bounds", flush=True)
    # Cross-language fragmented/coalesced frames and verified TLS failures.
    release = pathlib.Path("build/packages/legacy-demo/release.sha256").read_text().strip()
    for mode, host in [
        ("good", "localhost"),
        ("version", "localhost"),
        ("content", "localhost"),
        ("reject-tls", "wrong.local"),
    ]:
        cmd(
            "build/client/n3e-peer",
            port,
            "deploy/local/ca.pem",
            host,
            mode,
            "demo",
            release,
        )
    cmd(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        B / "other.key",
        "-out",
        B / "other.pem",
        "-days",
        "1",
        "-subj",
        "/CN=other",
    )
    cmd(
        "build/client/n3e-peer",
        port,
        B / "other.pem",
        "localhost",
        "reject-tls",
        "demo",
        release,
    )
    p = Peer(port)
    p.s.sendall(struct.pack(">I", 100))
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:

        def independent(_):
            q = Peer(port)
            q.logout()
            return True

        assert all(pool.map(independent, range(16)))
    while time.monotonic() - start < 3:
        try:
            p.s.sendall(b"x")
        except OSError:
            break
        time.sleep(0.25)
    try:
        closed = not p.s.recv(4)
    except OSError:
        closed = True
    assert closed and time.monotonic() - start < 3.6
    p.s.close()
    sockets = [
        socket.create_connection(("127.0.0.1", port), timeout=2) for _ in range(64)
    ]
    try:
        extra = socket.create_connection(("127.0.0.1", port), timeout=3)
        assert extra.recv(1) == b""
        extra.close()
    finally:
        for sock in sockets:
            sock.close()
    time.sleep(2.1)
    print(
        "PASS C++ fragmented/coalesced framing, CA/hostname/version/content rejection, trickle/concurrent/admission bounds",
        flush=True,
    )
    slow = Peer(port, "gamma", password, receive_buffer=1024)
    sid = slow.create("Slow")
    assert slow.select(sid)[0] == 10
    stopped = False
    start = time.monotonic()
    while time.monotonic() - start < 12:
        try:
            for _ in range(80):
                slow.send(11, blob(1, "x" * 257))
        except OSError:
            stopped = True
            break
        time.sleep(1.05)
        if sql(f"SELECT online FROM characters WHERE id={sid}") == "f":
            stopped = True
            break
    slow.s.close()
    assert stopped, "slow reader did not expire within bounded output deadline"
    wait(lambda: sql(f"SELECT online FROM characters WHERE id={sid}") == "f")
    # PQ-427: the server names a session it ended (the writer's deadline here,
    # or its reply queue), where it used to close it without a line.
    def closes():
        return [line for line in dc("logs", "--no-color", "server").stdout.splitlines()
                if "closed by the server: " in line]
    wait(lambda: any(f"(character {sid}) closed by the server: writer: " in line for line in closes()), 10)
    slow_line = next(line for line in closes() if f"(character {sid}) closed by the server: writer: " in line)
    print("PASS bounded slow-consumer output and cleanup; the server named the close:",
          slow_line.split("closed by the server: ", 1)[1], flush=True)
    # PQ-427: a session over the frame rate bound is told so (an Error, then
    # LoggedOut), closed, and named in the server's log. The keepalive is off
    # and the peer waits out the 1 s window first, so the 101st ping is the last
    # frame sent and the server reads every frame before it closes.
    flooded = "closed by the server: session rate limit: 101 frames and "
    earlier = sum(flooded in line for line in closes())  # the framing probes' own
    flood = Peer(port, "delta", password)
    with flood.lock:
        flood.keepalive = False
    time.sleep(1.2)
    for _ in range(101):
        flood.send(14)
    tag, e = flood.until(4)
    assert first(e, 1) == 4 and first(e, 2) == b"session rate limit", e
    flood.until(13)
    try:
        flood.receive()
        raise AssertionError("a rate-limited session stayed open")
    except DISCONNECTED as error:
        ended = str(error)
    flood.s.close()
    wait(lambda: sum(flooded in line for line in closes()) > earlier, 10)
    print("PASS session frame bound: Error and LoggedOut, then", ended, "; the server named it:",
          [line for line in closes() if flooded in line][-1].split("closed by the server: ", 1)[1],
          flush=True)
    # Authentication rate counters survive reconnect; no default/demo admin exists.
    for _ in range(11):
        p = Peer(port)
        p.send(5, blob(1, "missing") + blob(2, "wrong password"))
        tag, e = p.until(4)
        p.s.close()
    assert first(e, 1) == 4
    assert sql("SELECT count(*) FROM character_roles") == "0"
    sql("UPDATE schema_migrations SET digest='corrupt' WHERE version=2")
    bad = dc("run", "--rm", "--no-deps", "migrate", good=False)
    assert bad.returncode != 0 and "checksum mismatch" in bad.stderr
    dc("restart", "server")
    wait(lambda: not ready())
    print(
        "PASS cross-connection login throttling, no implicit roles, migration checksum rejection",
        flush=True,
    )
    (B / "server.txt").write_text(dc("logs", "--no-color", "server", "migrate").stdout)
finally:
    # PQ-128: every service's log, before the stack is removed.
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    dc("down", "--volumes", "--remove-orphans", good=False)
print("PASS Phase 2 integration", flush=True)
