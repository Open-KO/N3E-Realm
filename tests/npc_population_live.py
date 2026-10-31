"""PQ-250: a zone's whole NPC population (about 1,300 NPCs) with many sessions, live.

The package is the PQ-249 engine 37 fixture (tests/npc_templates_live.py) on a
256 m flat heightfield with 1,300 spawn points, one N3N3 slot each: 400 passive
"crowd" NPCs packed into the 3 x 3 interest window around the player spawn and
900 aggressive "field" NPCs over the rest of the map. Template names and looks
keys are long (about 100 bytes), so the crowded window does not fit one view
frame. The editing table names two of the 1,300 spawn points (PQ-250 `spawns`).

Against a native server on a disposable Postgres and Redis it checks, over the
wire and from the server's health line:

1. both readers accept the package (2,048 spawn bound) and the server starts
   with every NPC: startup reserves one runtime id per spawn plus the base pool;
2. 48 sessions (16 of them operators holding `entity.kill`) in the crowded
   window, from eight loopback addresses, all stay connected, every view frame
   is at most 65,536 bytes, the server reports trimmed views and no unsendable
   one; the 32 movers send each move after the last one's ack (the server
   admits one movement per tick) and the server refuses none of them;
3. an observer's crowded view keeps the nearest NPCs: every crowd NPC it lacks
   stands at least as far as every crowd NPC it has;
4. respawn churn: the operators kill a crowd NPC a second each; every killed
   NPC comes back at its spawn point with a fresh id and the id pool never
   runs dry;
5. it prints the tick time, command queue depth, id pool and memory measured
   under that load (MEASURE line) and bounds them.

With N3E_GRAPHICAL=1 the real test client joins the crowded window offscreen
and must render it (its frame check fails on any frame over 65,536 bytes).
"""
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import select
import shutil
import struct
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402

OUT = ROOT / "build/pq250"
CELL = 16
PLAYER = (8.0, 8.0)
CROWD, FIELD = 400, 900
SESSIONS, OPERATORS, WORKERS = 48, 16, 8
LOAD_SECONDS = 30
FRAME_LIMIT = 65536
# Long names make each crowd NPC about 250 bytes on the wire (a template name
# or looks key is the game prefix and at most 96 characters).
CROWD_NAME = "demo:creature/crowd-" + "c" * 81
FIELD_NAME = "demo:creature/field-" + "f" * 60
TEMPLATES = [
    dict(name=CROWD_NAME, looks="demo:looks/crowd-" + "l" * 84, acquisition="passive", health=40, level=1,
         xp=10, damage=1, attack=4, defense=0, accuracy=100, evasion=1, attack_ticks=20, speed=3,
         attack_range=1, search_range=3, tracing_range=8),
    dict(name=FIELD_NAME, looks="demo:looks/field-" + "l" * 60, acquisition="aggressive", health=60, level=2,
         xp=20, damage=1, attack=8, defense=0, accuracy=100, evasion=1, attack_ticks=40, speed=3,
         attack_range=1, search_range=6, tracing_range=12),
]


def window(x, z):
    """Whether (x, z) is in the 3 x 3 interest window around the player spawn."""
    cx, cz = math.floor(PLAYER[0] / CELL), math.floor(PLAYER[1] / CELL)
    return abs(math.floor(x / CELL) - cx) <= 1 and abs(math.floor(z / CELL) - cz) <= 1


def spawns():
    crowd = [[-14 + i * 2.3, -14 + j * 2.3] for j in range(20) for i in range(20)]
    field = [[float(x), float(z)] for z in range(-120, 121, 7) for x in range(-120, 121, 7)
             if not (-20 <= x <= 36 and -20 <= z <= 36)][:FIELD]
    assert len(crowd) == CROWD and len(field) == FIELD and all(window(*p) for p in crowd)
    assert not any(window(*p) for p in field)
    return crowd + field


@once_per_run
def prepare():
    """Cook the 1,300-spawn package; returns its directory."""
    from npc_templates_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    scene = json.loads((root / "scene.json").read_text())
    scene["heightfield"] = dict(width=129, depth=129, origin=[-128, 0, -128], spacing=2, heights=[0] * 129 * 129)
    (root / "scene.json").write_text(json.dumps(scene))
    m = json.loads((root / "package.json").read_text())
    points = spawns()
    m["gameplay"].update(spawns=points, interest_cell=CELL, spawn_x=PLAYER[0], spawn_z=PLAYER[1])
    m["npc"]["templates"] = TEMPLATES
    m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=40, template=CROWD_NAME if i < CROWD else FIELD_NAME)
                         for i in range(len(points))]
    # PQ-250: 1,300 editable spawn points would exceed the 128-property table.
    m["editing"]["spawns"] = [0, len(points) - 1]
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def check_readers(package):
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
        assert p.returncode == 0, (cmd, p.stdout[-600:], p.stderr[-600:])
    print(f"PASS both readers accept {CROWD + FIELD} spawn points and slots (bound 2,048)", flush=True)


def metrics(port):
    import urllib.request
    try:
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/live", timeout=1).read().decode()
    except OSError:
        return {}
    return {k: int(v) if v.isdigit() else v for k, v in re.findall(r"(\w+)=(\S+)", body)}


def memory(pid):
    text = Path(f"/proc/{pid}/status").read_text()
    return {k: int(re.search(rf"^{k}:\s+(\d+) kB", text, re.M).group(1)) for k in ("VmRSS", "VmHWM")}


def kill_request(session, request, entity):
    from world_peer import blob, integer
    return (integer(1, session) + blob(2, request) + blob(3, "kill") + integer(4, 0)
            + blob(5, BASE_IDENTITY) + blob(7, "pq250 churn") + integer(8, 0) + integer(10, entity))


BASE_IDENTITY = ""


def acked(p):
    """Whether the server has applied this session's last movement: its own entity
    in the latest view carries that movement's seq as its ack. The server admits
    one movement per session per tick and rejects a second that reaches the same
    tick's command drain (server/src/simulation.rs, "one movement per tick"), so a
    mover sends the next only once the last is acknowledged, as the other movement
    suites do (PQ-402). Pacing by the wall clock alone fails whenever two sends
    100 ms apart reach the server inside one late tick. The viewer itself is never
    trimmed from its view (server/src/view_frame.rs), so the ack is always there.
    Only each entity's leading id varint is read: the view holds about 260."""
    from world_peer import fields, first
    if p.seq == 0:
        return True
    if p.latest is None:
        return False
    world = fields(fields(p.latest)[10][0])
    me = first(world, 3)
    for raw in world.get(4, []):
        if raw[:1] != b"\x08":  # Entity field 1 (id), varint, leads the encoding
            continue
        n, shift = 0, 0
        for x in raw[1:11]:
            n |= (x & 127) << shift
            shift += 7
            if x < 128:
                break
        if n == me:
            return first(fields(raw), 6) >= p.seq
    return False


def worker(index, port, identity, manifest, accounts, password, operators, seconds, results, ready, go, login):
    """One process driving `accounts` sessions from 127.0.0.<index + 2>: movers walk
    back and forth, operators kill a crowd NPC about once a second. Every session
    is read continuously from its selection on (a session the server cannot write
    to for two seconds is dropped). Reports frame sizes, kill statuses and the
    killed NPCs' positions. `login` serialises logins across the workers: the
    server hashes at most two passwords at once and refuses a third."""
    global BASE_IDENTITY
    BASE_IDENTITY = identity
    sys.path.insert(0, str(ROOT / "tests"))
    from world_peer import Peer, fields, first
    stats = dict(frames=0, largest=0, statuses={}, killed=[], errors=[], moves=0, movers=0)
    peers = []

    def drain(timeout):
        readable = select.select([p.s for p in peers], [], [], timeout)[0] if peers else time.sleep(timeout)
        for p in peers:
            if p.s not in (readable or []) and not p.s.pending():
                continue
            while True:
                frame = p._take()
                if frame is None:
                    break
                stats["frames"] += 1
                stats["largest"] = max(stats["largest"], len(frame))
                if frame[0] == 0x52:  # Envelope field 10, World
                    p.latest = frame
                elif frame[0] == 0xEA and frame[1] == 0x01:  # field 29, AdminResult
                    result = fields(fields(frame)[29][0])
                    status = first(result, 2, b"").decode()
                    stats["statuses"][status] = stats["statuses"].get(status, 0) + 1
                    target = p.requests.get(first(result, 1, b"").decode())
                    if status == "killed" and target is not None:
                        stats["killed"].append(target)
                elif frame[0] == 0x22:  # field 4, Error
                    stats["errors"].append(first(fields(fields(frame)[4][0]), 2, b"").decode())

    try:
        for name in accounts:
            while not login.acquire(timeout=0.05):
                drain(0)
            try:
                p = Peer(port, name, password, content=identity, game=manifest["game_id"],
                         protocol=manifest["protocol_version"], source=f"127.0.0.{index + 2}")
            finally:
                login.release()
            p.create(name.capitalize())
            assert p.select(p.characters[0][0])[0] == 10
            p.operator = name in operators
            p.latest = None
            p.requests = {}
            p.direction = 1 if len(peers) % 2 else -1
            p.next_move = 0.0
            peers.append(p)
            drain(0)
        ready.put((index, [(name, p.characters[0][0]) for name, p in zip(accounts, peers)]))
        while not go.is_set():
            drain(0.05)
        end = time.monotonic() + seconds
        next_kill = time.monotonic()
        flip = time.monotonic() + 2
        while time.monotonic() < end:
            drain(0.02)
            now = time.monotonic()
            if now >= flip:
                for p in peers:
                    p.direction = -p.direction
                flip = now + 2
            # At most ten moves a second per mover, each after the last one's ack.
            for p in peers:
                if not p.operator and now >= p.next_move and acked(p):
                    p.move(0.7 * p.direction, 0.7 * p.direction)
                    stats["moves"] += 1
                    p.next_move = now + 0.1
            if now >= next_kill:
                for i, p in enumerate(peers):
                    if not p.operator or p.latest is None:
                        continue
                    world = fields(fields(p.latest)[10][0])
                    crowd = []
                    for raw in world.get(4, []):
                        e = fields(raw)
                        if first(e, 9) == 1 and first(e, 2, b"").decode() == CROWD_NAME and first(e, 7) > 0:
                            crowd.append((first(e, 1), first(e, 3), first(e, 5)))
                    if crowd:
                        target = crowd[(index * 7 + i * 13 + int(now)) % len(crowd)]
                        request = uuid.uuid4().hex
                        p.requests[request] = target
                        p.send(28, kill_request(first(world, 2), request, target[0]))
                next_kill = now + 1.1
        stats["connected"] = len(peers)
        stats["movers"] = sum(not p.operator for p in peers)
    except Exception as error:  # reported to the parent, which fails the suite
        import traceback
        stats["errors"].append("worker %d: %r\n%s" % (index, error, traceback.format_exc()))
    finally:
        results.put((index, stats))
        for p in peers:
            try:
                p.s.close()
            except Exception:
                pass


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, fields, first

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    identity = (package / "release.sha256").read_text().strip()
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq250-" + uuid.uuid4().hex[:10]
    password = "test-only-" + uuid.uuid4().hex
    containers, server, log, processes = [], None, None, []
    POSTGRES = "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad"
    REDIS = "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9"

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

    try:
        for suffix, image, port, extra in [
            ("", POSTGRES, 5432, ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
                                  "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
            ("-redis", REDIS, 6379, []),
        ]:
            run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{port}", image)
            containers.append(name + suffix)
        pg = wait_postgres(name)
        redis = run("docker", "port", name + "-redis", "6379").split()[0]
        listen, health = free_ports(2)
        realm = "test-" + name
        env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                   REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM=realm,
                   N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "migrate", env=env)
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        accounts = [f"pop{i:02d}" for i in range(SESSIONS)] + ["observer", "viewer"]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda a: run(server_binary, "account-create", a, env=env, stdin=password + "\n"), accounts))
        log = open(out / "server.log", "w")
        started = time.monotonic()
        server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 60
        while metrics(health).get("ready") != "true" or not metrics(health).get("npcs"):
            assert server.poll() is None, (out / "server.log").read_text()[-2000:]
            assert time.monotonic() < deadline, "server never reported ready"
            time.sleep(0.1)
        m = metrics(health)
        assert m["npcs"] == CROWD + FIELD, m
        idle = memory(server.pid)
        print(f"PASS server ready with {m['npcs']} NPCs in {time.monotonic() - started:.1f} s; "
              f"id pool {m['ids']} after startup; RSS {idle['VmRSS']} kB before any session", flush=True)

        # Sessions: eight processes, six sessions each, two of them operators.
        ctx = multiprocessing.get_context("spawn")
        results, ready, go, login = ctx.Queue(), ctx.Queue(), ctx.Event(), ctx.Lock()
        per = SESSIONS // WORKERS
        operators = {f"pop{i:02d}" for i in range(SESSIONS) if i % per < OPERATORS // WORKERS}
        for w in range(WORKERS):
            mine = accounts[w * per:(w + 1) * per]
            proc = ctx.Process(target=worker, args=(w, listen, identity, manifest, mine, password,
                                                     operators & set(mine), LOAD_SECONDS, results, ready, go, login))
            proc.start()
            processes.append(proc)
        characters = {}
        for _ in range(WORKERS):
            try:
                index, chars = ready.get(timeout=180)
            except Exception:
                failures = []
                while not results.empty():
                    failures.append(results.get())
                raise AssertionError(("sessions did not join", failures))
            characters.update(dict(chars))
        for account in sorted(operators):
            run(server_binary, "role", "grant", account, str(characters[account]), realm, "entity.kill", env=env)
        observer = Peer(listen, "observer", password, content=identity, game=manifest["game_id"],
                        protocol=manifest["protocol_version"], source="127.0.0.200")
        observer.create("Observer")
        assert observer.select(observer.characters[0][0])[0] == 10
        go.set()
        samples, rss = [], []
        load_end = time.monotonic() + LOAD_SECONDS
        checked = 0
        while time.monotonic() < load_end:
            observer.pump(0.5)
            samples.append(metrics(health))
            rss.append(memory(server.pid))
            if checked < 3 and time.monotonic() > load_end - LOAD_SECONDS + 5 * (checked + 1):
                nearest_prefix(observer, first)
                checked += 1
        stats = {}
        for _ in range(WORKERS):
            index, s = results.get(timeout=60)
            stats[index] = s
        for proc in processes:
            proc.join(30)
        errors = [e for s in stats.values() for e in s["errors"]]
        assert not errors, errors[:5]
        assert all(s.get("connected") == per for s in stats.values()), {i: s.get("connected") for i, s in stats.items()}
        # The movers kept the load up: ack pacing must not stall them (about 7 to
        # 10 moves a second each when the server keeps its tick).
        movers = sum(s["movers"] for s in stats.values())
        moves = sum(s["moves"] for s in stats.values())
        assert movers == SESSIONS - OPERATORS and moves >= movers * LOAD_SECONDS * 2, (movers, moves)
        largest = max(s["largest"] for s in stats.values())
        frames = sum(s["frames"] for s in stats.values())
        assert 0 < largest <= FRAME_LIMIT, largest
        final = metrics(health)
        # Every session was in the world through the load (the workers have left now).
        during = [s.get("sessions") for s in samples[4:-4]]
        assert during and all(n == SESSIONS + 1 for n in during), during
        assert final["views_trimmed"] > 0 and final["views_over"] == 0, final
        print(f"PASS {SESSIONS} sessions in the crowded window stayed connected: {movers} movers sent {moves} "
              f"acknowledged moves and none was refused; {frames} frames, largest "
              f"{largest} bytes (bound {FRAME_LIMIT}); views trimmed {final['views_trimmed']}, unsent "
              f"{final['views_over']}", flush=True)

        # Respawn churn: every killed NPC is back at its point with a fresh id.
        statuses = {}
        for s in stats.values():
            for k, v in s["statuses"].items():
                statuses[k] = statuses.get(k, 0) + v
        killed = [k for s in stats.values() for k in s["killed"]]
        assert len(killed) >= 100, (len(killed), statuses)
        assert min(s["ids"] for s in samples if "ids" in s) > 0, [s.get("ids") for s in samples]
        killed_ids = {k[0] for k in killed}
        observer.pump(4)  # corpse 40 + respawn 40 ticks
        seen = {}
        for e in observer.entities.values():
            if first(e, 9) == 1:
                seen[(round(first(e, 3), 1), round(first(e, 5), 1))] = e
        back = 0
        for entity, x, z in killed:
            e = seen.get((round(x, 1), round(z, 1)))
            if e is not None:
                assert first(e, 1) not in killed_ids and first(e, 7) > 0, (entity, e)
                back += 1
        assert back > 0, "no killed NPC position is in the observer's view: the check proves nothing"
        print(f"PASS respawn churn: {len(killed)} operator kills ({statuses}); each of the {back} killed NPCs in "
              f"view is back with a fresh id; the id pool never ran dry (lowest {min(s['ids'] for s in samples)})",
              flush=True)

        print("SAMPLES " + " ".join(f"{s.get('tick_max_us')}/{s.get('queue_max')}/{s.get('ids')}/{s.get('sessions')}"
                                    for s in samples), flush=True)
        windows = [s for s in samples if s.get("tick_max_us")]
        tick_max = max(s["tick_max_us"] for s in windows)
        queue_max = max(s["queue_max"] for s in windows)
        print(f"MEASURE npcs={final['npcs']} sessions={final['sessions']} tick_ms={final['tick_ms']} "
              f"tick_max_us={tick_max} queue_max={queue_max} ids_min={min(s['ids'] for s in samples)} "
              f"rss_kb={max(r['VmRSS'] for r in rss)} hwm_kb={max(r['VmHWM'] for r in rss)} "
              f"largest_frame={largest} views_trimmed={final['views_trimmed']} kills={len(killed)}", flush=True)
        # The gate runs the debug server beside other suites, so this bounds a
        # regression (no tick may take three ticks), not the release budget; the
        # release measurement is in the PQ-250 evidence.
        assert tick_max < 150000, f"a tick took {tick_max} us, three 50 ms ticks"
        assert queue_max < 256, f"command queue reached {queue_max} (one tick drains 256)"
        print("PASS tick time, queue depth and memory measured under the population load", flush=True)
        observer.logout()

        if os.environ.get("N3E_GRAPHICAL") == "1":
            # The client selects the account's first character.
            viewer = Peer(listen, "viewer", password, content=identity, game=manifest["game_id"],
                          protocol=manifest["protocol_version"], source="127.0.0.201")
            viewer.create("Viewer")
            viewer.s.close()
            capture = out / "crowd.ppm"
            capture.unlink(missing_ok=True)
            with open(out / "client.log", "w") as client_log:
                code = subprocess.run(
                    ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                     "deploy/local/ca.pem", "--auto-login", "--world-smoke", "6", "--capture", str(capture)],
                    env={**os.environ, "N3E_TEST_ACCOUNT": "viewer", "N3E_TEST_PASSWORD": password},
                    stdout=client_log, stderr=subprocess.STDOUT, timeout=180).returncode
            text = (out / "client.log").read_text()
            visible = [int(line.split("visible=")[1].split()[0]) for line in text.splitlines() if line.startswith("WORLD ")]
            assert code == 0 and visible and visible[-1] >= 100 and capture.stat().st_size > 0, (code, text[-1500:])
            print(f"PASS graphical client renders the crowded window: {visible[-1]} entities, {capture}", flush=True)
    finally:
        for proc in processes:
            if proc.is_alive():
                proc.kill()
        if server is not None:
            server.kill()
            server.wait()
        if log is not None:
            log.close()
        for c in containers:
            container_logs({name: "postgres", name + "-redis": "redis"}[c], ["docker", "logs", "--timestamps", c])
        for c in containers:
            subprocess.run(["docker", "rm", "-f", c], capture_output=True)


def nearest_prefix(observer, first):
    """The observer's crowd NPCs are a nearest-first prefix of the crowd spawn
    points: no crowd point it lacks is nearer than one it has."""
    me = observer.entities[observer.id]
    x0, z0 = first(me, 3), first(me, 5)
    have = {(round(first(e, 3), 1), round(first(e, 5), 1)) for e in observer.entities.values()
            if first(e, 9) == 1 and first(e, 2, b"").decode() == CROWD_NAME}
    crowd = [(round(x, 1), round(z, 1)) for x, z in spawns()[:CROWD]]
    if not window(x0, z0):
        return
    distance = lambda p: (p[0] - x0) ** 2 + (p[1] - z0) ** 2
    kept = [distance(p) for p in crowd if p in have]
    lacking = [distance(p) for p in crowd if p not in have]
    assert kept and lacking, (len(kept), len(lacking))
    # A killed NPC is missing for its corpse and respawn time; allow those.
    nearer = [d for d in lacking if d < max(kept) - 1e-3]
    assert len(nearer) <= 2 * OPERATORS, (len(nearer), max(kept))
    print(f"PASS crowded view keeps the nearest: {len(kept)} of {CROWD} crowd NPCs, the farthest kept at "
          f"{math.sqrt(max(kept)):.1f} m; {len(nearer)} nearer points empty (killed, awaiting respawn)", flush=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    check_readers(package)
    live(package)
