"""Readiness means admission: once /ready answers 200 the game port accepts (PQ-001).

Starts the native server repeatedly against one disposable Postgres and Redis,
polls /ready without sleeping, and connects to N3E_LISTEN the moment the first 200
arrives. Before PQ-001 attempt 2 the server reported ready about 0.6 ms before it
bound the game listener, and this check was refused on every start.
"""
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
STARTS = 10
server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
name = "n3e-readiness-" + uuid.uuid4().hex[:10]
out = ROOT / "build/live/readiness"
out.mkdir(parents=True, exist_ok=True)


def run(*cmd, env=None, good=True):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    assert not good or p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def probe(url, timeout):
    """One /ready request (PQ-414): True when the server answered 200, False
    when it answered anything else (503: not ready), None when no answer came
    inside `timeout` (refused, reset or timed out). urllib raises a 503 as
    HTTPError, an OSError, so before PQ-414 a probe that got no answer inside
    0.2 s (its own request delayed under the parallel suites) read exactly
    like a server that answered it was no longer ready."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        e.close()
        return False
    except OSError:
        return None


# Lines a realm writes when admission closed after its first 200: the renewal
# thread saw it expired or failed (the realm then exits), a renewal landed
# after it had closed (PQ-414), or Redis was down for two probes in a row.
DROPS = ("admission expired", "lease renewal stopped", "lease renewal failed", "admission was closed",
         " unreachable: ")
# How long /ready may go unanswered inside the held window before the check
# fails: a health endpoint that stops answering is a failure too.
SILENT = 5.0


def hold_ready(server, url, path, seconds):
    """Require the realm ready for `seconds` after its first 200 (PQ-414).
    A 503 the server answers fails at once; so do the realm exiting, a drop
    its log names, and no answer for SILENT s. A probe that went unanswered
    (the suite's own request delayed past its 1 s bound under load) says
    nothing about readiness and is sent again: admission never closes and
    reopens without an answered 503 or a log line (D-142 renews only while
    admission holds, an expired one ends the realm, a renewal that lands
    late names the time admission was closed, and a Redis drop is logged
    before admission closes), and the window ends only on an answered 200.
    The server also closes a request it cannot read within 100 ms without
    answering (health_http), so a reset is unanswered too.
    Returns (answered, unanswered, slowest answered seconds)."""
    held = time.monotonic() + seconds
    answered = unanswered = 0
    slowest = 0.0
    last = time.monotonic()
    while True:
        assert server.poll() is None, f"server exited after it reported ready\n{path.read_text()}"
        sent = time.monotonic()
        state = probe(url, 1.0)
        now = time.monotonic()
        if state is None:
            unanswered += 1
            assert now - last < SILENT, f"/ready went unanswered for {now - last:.1f} s\n{path.read_text()}"
            continue
        if not state:
            time.sleep(0.6)  # the renewal thread checks admission every 400 ms; let it log why
            raise AssertionError(f"/ready answered 503 after the first 200\n{path.read_text()}")
        answered += 1
        slowest = max(slowest, now - sent)
        last = now
        if now >= held:
            break
        # Paced, not a busy loop (about 8600 requests a second unpaced): the
        # check rests on answered 503s and the realm's log, not on sampling
        # every millisecond, and the parallel suites share the machine.
        time.sleep(0.005)
    text = path.read_text()
    for failure in DROPS:
        assert failure not in text, f"the realm logged a readiness drop ({failure.strip()!r})\n{text}"
    return answered, unanswered, slowest


containers = []
server = None
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
    base = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                REDIS_ADDRESS=redis, N3E_PACKAGE=str(ROOT / "build/packages/demo"))
    run(server_binary, "migrate", env=base)
    for start in range(STARTS):
        listen, health = free_ports(2)
        # A fresh realm per start, so no start waits for the previous lease.
        env = dict(base, N3E_REALM=f"test-{name}-{start}", N3E_LISTEN=f"127.0.0.1:{listen}",
                   N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        log = open(out / f"server-{start}.log", "w")
        server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 30
        while True:
            assert server.poll() is None, (out / f"server-{start}.log").read_text()
            assert time.monotonic() < deadline, "server never reported ready"
            if probe(f"http://127.0.0.1:{health}/ready", 0.2):
                break
        try:
            socket.create_connection(("127.0.0.1", listen), timeout=1).close()
        except ConnectionRefusedError:
            raise AssertionError(f"start {start}: /ready answered 200 but the game port refused")
        server.kill()
        server.wait()
        server = None
        log.close()
    print(f"PASS readiness: {STARTS} starts, the game port accepted on the first /ready 200 each time")

    # PQ-156 (D-141): only the account/checkpoint worker's connection fails.
    # A role limited to one connection lets the start-up connection in and
    # refuses the worker's (53300), which start-up now opens second, while the
    # first is still held. Before, the worker opened at the same moment and
    # ended silently; the realm could take the lease and report ready while
    # every login failed with "database queue unavailable".
    role = "n3e_one_connection"
    sql = lambda q: run("docker", "exec", name, "psql", "-v", "ON_ERROR_STOP=1", "-tAq",
                        "-U", "n3e", "-d", "n3e", "-c", q).stdout.strip()
    sql(f"CREATE ROLE {role} LOGIN PASSWORD 'test-only' CONNECTION LIMIT 1; "
        f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role}; "
        f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role}")
    listen, health = free_ports(2)
    realm = f"test-{name}-worker"
    env = dict(base, N3E_REALM=realm, N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
    run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
    # The offline conversion took and released the realm (owner, generation).
    lease = f"SELECT owner || ' ' || generation FROM realm_ownership WHERE realm='{realm}'"
    converted = sql(lease)
    assert converted.startswith("offline-conversion "), converted
    env["DATABASE_URL"] = f"host=127.0.0.1 port={pg} user={role} password=test-only dbname=n3e"
    path = out / "server-worker-refused.log"
    log = open(path, "w")
    server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
    deadline = time.monotonic() + 30
    while server.poll() is None:
        assert time.monotonic() < deadline, "server kept running without its worker connection"
        # An unanswered probe (None) cannot hide a 200: the realm exits, the
        # lease check below runs on what it left, and 1 s bounds each wait.
        assert probe(f"http://127.0.0.1:{health}/ready", 1.0) is not True, \
            "/ready answered 200 with no account/checkpoint worker"
    code = server.wait()
    server = None
    log.close()
    text = path.read_text()
    assert code != 0 and "53300" in text and "too many connections for role" in text, (code, text)
    after = sql(lease)
    assert after == converted, f"start-up took the lease before its worker connected ({converted} -> {after})\n{text}"
    print("PASS readiness: a refused worker connection ends start-up with its error (53300), "
          "never ready and no lease taken")

    # PQ-369 (D-199): a slow Postgres connect must not spend admission. The
    # realm reaches Postgres through a proxy that holds every new connection
    # for SLOW seconds before it forwards a byte (a slow name lookup, TCP
    # connect or handshake; none is bounded by the 2 s admission). Before, the
    # renewal thread opened its connection after the lease was taken, so its
    # first renewal came SLOW + 0.4 s after admission started: the realm
    # reported ready, then exited with "admission expired; restart required".
    slow = 1.7
    (proxy_port,) = free_ports(1)
    accepted = []
    proxy = socket.socket()
    proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy.bind(("127.0.0.1", proxy_port))
    proxy.listen(16)
    # PQ-414 and PQ-415 controls: once armed, the proxy holds a reply of the
    # realm's next lease renewal (its conditional UPDATE, sent in clear) for
    # stall["hold"] s. The client prepares the statement and then executes it,
    # one round trip each. With at="parse" the reply to the prepare is held,
    # so the UPDATE runs only when the hold ends (a slow network before the
    # statement); with at="execute" the UPDATE runs at once and the reply to
    # it is held (a slow commit or answer). Armed before the realm starts, the
    # held renewal is the first: it starts about 900 ms after the lease
    # (start-up's ~500 ms plus the 400 ms renewal pause), so a hold of more
    # than about 1.1 s lands after admission (2 s from the lease attempt)
    # closed, and a parse hold of more than about 2.1 s runs the UPDATE after
    # the database lease (3 s from the lease commit) ran out.
    renewal_sql = b"SET expires=clock_timestamp()+interval '3 seconds'"
    stall = {"armed": 0, "held": None, "hold": 0.0, "at": "parse"}  # armed: renewals left until the held one
    stall_lock = threading.Lock()

    def pump(src, dst, conn, upstream):
        try:
            while data := src.recv(65536):
                if not upstream:
                    with stall_lock:
                        if conn.pop("execute_next", False):
                            conn["hold"] = True  # the held renewal's execute
                        elif stall["armed"] and renewal_sql in data:
                            stall["armed"] -= 1
                            target = not stall["armed"]
                            conn["hold"] = target and stall["at"] == "parse"
                            conn["execute_next"] = target and stall["at"] == "execute"
                elif conn.pop("hold", False):
                    stall["held"] = time.monotonic()
                    time.sleep(stall["hold"])
                dst.sendall(data)
        except OSError:
            pass
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def hold_then_forward(client):
        time.sleep(slow)
        try:
            upstream = socket.create_connection(("127.0.0.1", int(pg)), timeout=5)
        except OSError:
            client.close()  # Postgres already removed at teardown
            return
        upstream.settimeout(None)
        conn = {}
        threading.Thread(target=pump, args=(client, upstream, conn, False), daemon=True).start()
        threading.Thread(target=pump, args=(upstream, client, conn, True), daemon=True).start()

    def accept():
        while True:
            try:
                client, _ = proxy.accept()
            except OSError:
                return
            accepted.append(time.monotonic())
            threading.Thread(target=hold_then_forward, args=(client,), daemon=True).start()

    def start_through_proxy(label):
        listen, health = free_ports(2)
        env = dict(base, N3E_REALM=f"test-{name}-{label}", N3E_LISTEN=f"127.0.0.1:{listen}",
                   N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        env["DATABASE_URL"] = f"host=127.0.0.1 port={proxy_port} user=n3e password=test-only dbname=n3e"
        path = out / f"server-{label}.log"
        log = open(path, "w")
        server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
        url = f"http://127.0.0.1:{health}/ready"
        deadline = time.monotonic() + 30
        # Each connection waits `slow` s, so /ready answers 503 for seconds
        # before the first 200: the probe must read those as answered.
        answered_503 = 0
        while not (state := probe(url, 0.2)):
            answered_503 += state is False
            assert server.poll() is None, f"server exited before ready\n{path.read_text()}"
            assert time.monotonic() < deadline, "server never reported ready"
        assert answered_503, "the probe never read the starting realm's 503 as an answer"
        return server, log, path, url

    threading.Thread(target=accept, daemon=True).start()
    # A listener that accepts and never answers: unanswered, not "not ready".
    (silent_port,) = free_ports(1)
    silent = socket.socket()
    silent.bind(("127.0.0.1", silent_port))
    silent.listen(1)
    assert probe(f"http://127.0.0.1:{silent_port}/ready", 0.2) is None, "a silent listener read as answered"
    silent.close()
    server, log, path, ready_url = start_through_proxy("slow-connect")
    # Past the first admission window and several renewals: ready throughout.
    answered, unanswered, slowest = hold_ready(server, ready_url, path, 3)
    server.kill()
    server.wait()
    server = None
    log.close()
    text = path.read_text()
    for failure in DROPS:
        assert failure not in text, text
    # Each of the realm's connections paid the delay (start-up, worker, renewal).
    assert len(accepted) >= 3, accepted
    took = [line.strip() for line in text.splitlines() if "start-up took" in line]
    late = [line.strip() for line in text.splitlines() if "lease renewal started" in line]
    print(f"PASS readiness: {len(accepted)} connections each held {slow} s by a slow-connect proxy; "
          f"ready for 3 s after the first 200, no renewal outside admission "
          f"({took[0] if took else 'no start-up line'}; late renewals inside admission: {late or 'none'}; "
          f"/ready answered 200 {answered} times, slowest {slowest * 1000:.0f} ms, "
          f"{unanswered} probes unanswered within 1 s)")

    def held_renewal(label, hold, at="parse"):
        """Start a realm whose first renewal reply the proxy holds `hold` s and
        run the held window over it. The window must fail on the answered 503
        or on the realm's logged closure ("admission was closed"); a failure on
        silence alone means the control did not produce the case it tests.
        Returns (server, log, path, ready_url, how the window failed)."""
        global server  # the suite's finally kills it if a check below fails
        with stall_lock:
            stall.update(armed=1, held=None, hold=hold, at=at)
        server, log, path, ready_url = start_through_proxy(label)
        try:
            hold_ready(server, ready_url, path, 4)
            raise RuntimeError(f"a renewal reply held {hold} s did not fail the held window\n{path.read_text()}")
        except AssertionError as e:
            caught = str(e).splitlines()[0]
            assert caught.startswith(("/ready answered 503",
                                      "the realm logged a readiness drop ('admission was closed')",
                                      "server exited after it reported ready")), f"the window failed otherwise: {e}"
        assert stall["held"] is not None, "the proxy never held a renewal reply"
        deadline = time.monotonic() + 5
        while "admission was closed" not in path.read_text():
            assert time.monotonic() < deadline, f"the realm never logged the closure\n{path.read_text()}"
            time.sleep(0.1)
        return server, log, path, ready_url, caught

    def recovers(label, hold, at="parse"):
        """A held renewal the realm recovers from: it lands after admission
        closed and before 2 s after its own start, so its success reopened
        admission; the realm must still run, ready, 1 s later (more than two
        renewal pauses), with no "lease renewal stopped" line. The closure
        line's next pause must be the one D-215 gives for the admission left.
        Returns (the closure line, how the window failed, the logged pause in ms)."""
        global server
        server, log, path, ready_url, caught = held_renewal(label, hold, at)
        time.sleep(1)
        text = path.read_text()
        assert server.poll() is None, f"the realm did not survive the closure\n{text}"
        assert "lease renewal stopped" not in text and "stays closed" not in text, text
        deadline = time.monotonic() + SILENT
        while (state := probe(ready_url, 1.0)) is None:
            assert time.monotonic() < deadline, f"/ready went unanswered after the closure\n{text}"
        assert state, f"/ready answered 503 after the closure\n{text}"
        server.kill()
        server.wait()
        server = None
        log.close()
        named = [line.strip() for line in text.splitlines() if "admission was closed" in line][0]
        assert caught.startswith(("/ready answered 503", "the realm logged")), caught
        found = re.search(r"is open for (\d+) ms more; the next renewal starts in (\d+) ms", named)
        assert found, named
        left, pause = map(int, found.groups())
        assert abs(pause - max(0, min(400, left - 400))) <= 1, named
        return named, caught, pause

    # PQ-414 negative control: a drop the realm recovers from still fails the
    # held window. A first renewal reply held 1.3 s closes admission for about
    # 200 ms; the realm keeps running, so only the answered 503 or the realm's
    # "admission was closed" line can catch it.
    HOLD = 1.3
    named, caught, pause = recovers("renewal-held", HOLD)
    assert pause > 0, named  # about 700 ms left: a cut pause, not an immediate renewal
    print(f"PASS readiness: a first renewal reply held {HOLD} s closes admission and the realm recovers; "
          f"the held window fails on it ({caught}), the realm named it ({named}) "
          f"and was still running and ready 1 s later")

    # PQ-415 (D-215): a reply held 1.8 s lands with about 200 ms of the
    # reopened admission left, less than the 400 ms pause. It is held after
    # the UPDATE ran: held at the prepare, the UPDATE would run about 2.7 s
    # after the lease, about 300 ms before the lease from acquisition runs
    # out, and a start-up slower than about 800 ms would read "realm fenced". Before, the realm
    # slept the full pause, found admission expired and exited ("lease renewal
    # stopped") although its lease had just been renewed. Now the pause is cut
    # to what is left, so the next renewal starts at once and the realm
    # survives: running 1 s later means the next renewals landed, since the
    # reopened admission had only about 200 ms left.
    LONG = 1.8
    named, caught, pause = recovers("renewal-held-long", LONG, at="execute")
    assert pause == 0, named
    print(f"PASS readiness: a first renewal executed at once but answered {LONG} s later (more than 2 s less "
          f"the 400 ms pause) reopens "
          f"admission and the next renewal follows at once; the held window fails on it ({caught}), the realm "
          f"named it ({named}) and was still running and ready 1 s later")

    # PQ-415 safety boundary: the renewal's UPDATE runs at once and renews the
    # database lease, but its reply is held 2.3 s, so it lands after its own
    # attempt's 2 s have passed and its success leaves no admission to reopen.
    # The realm must not admit again: it logs that admission stays closed and
    # exits for restart, as before (D-142, D-215). (A parse hold this long
    # runs the UPDATE after the lease ran out instead: "realm fenced".)
    PAST = 2.3
    server, log, path, ready_url, caught = held_renewal("renewal-held-past", PAST, at="execute")
    try:
        code = server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        raise AssertionError(f"the realm kept running after a renewal that took {PAST} s\n{path.read_text()}")
    server = None
    log.close()
    text = path.read_text()
    assert code != 0 and "stays closed" in text and "lease renewal stopped" in text \
        and "admission expired; restart required" in text, (code, text)
    named = [line.strip() for line in text.splitlines() if "stays closed" in line]
    print(f"PASS readiness: a first renewal executed at once but answered {PAST} s later reopens nothing; "
          f"the realm named it ({named[0]}) "
          f"and exited for restart (code {code})")
    proxy.close()
finally:
    if server is not None:
        server.kill()
        server.wait()
    # PQ-128: each container's log, before it is removed.
    for c in containers:
        container_logs({name: "postgres", name + "-redis": "redis"}[c], ["docker", "logs", "--timestamps", c])
    for c in containers:
        run("docker", "rm", "-f", c, good=False)
