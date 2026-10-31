"""KO-06 isolated real TLS/PG life, stale identity and pending reward checks."""

import json, math, os, select, subprocess, sys, time, uuid
from pathlib import Path
from world_peer import DISCONNECTED, Peer as BasePeer, first, integer
import timescale
from isolation import DISPOSABLE_COMPOSE, container_logs

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import life_fixture, main

B = Path("build/ko-06")
B.mkdir(parents=True, exist_ok=True)
life_fixture.cook()
root = Path("build/ko-01/source")
m = json.loads((root / "package.json").read_text())
m.pop("damage")
m["gameplay"].update(
    health=30,
    npc_health=10,
    npc_damage=30,
    damage=10,
    spawns=[[-5.0, -5.0], [-5.8, -5.0]],
    npc_cooldown_ticks=20,
)
m["melee"]["reach"] = 2.0
packages = []
for label, delay in [("live", 60), ("pending", 4)]:
    m["life"]["player_delay_ticks"] = delay
    if label == "pending":
        m["gameplay"].update(health=90, npc_cooldown_ticks=10)
    (root / "package.json").write_text(json.dumps(m))
    out = B / label
    main.cook(root, out)
    packages.append(out.resolve())
project = "n3e-ko06-" + uuid.uuid4().hex[:10]
# A test- realm: what a scaled run needs (tests/timescale.py); harmless otherwise.
realm = "test-" + project
env = {
    **os.environ,
    "N3E_PORT": "0",
    "N3E_REALM": realm,
    "N3E_PACKAGE_PATH": str(packages[0]),
    "N3E_UID": str(os.getuid()),
    "N3E_GID": str(os.getgid()),
    **timescale.server_env(realm),
}
override = B / (project + ".yaml")
override.write_text(
    'services:\n  server:\n    environment:\n      N3E_LIFE_FAULT: "${N3E_LIFE_FAULT:-}"\n'
    + timescale.COMPOSE_ENV
)
base = ["docker", "compose", *DISPOSABLE_COMPOSE, "-f", str(override), "-p", project]
password = "test-only-" + uuid.uuid4().hex
peers = []
port = 0
# The server sessions' lock_timeout (server/src/persistence.rs config).
LOCK_TIMEOUT = 0.8
package = packages[0]


def dc(*args):
    p = subprocess.run(
        base + list(args), env=env, text=True, capture_output=True, timeout=120
    )
    assert p.returncode == 0, (args, p.stdout, p.stderr)
    return p.stdout


def sql(q):
    return dc(
        "exec", "-T", "postgres", "psql", "-U", "n3e", "-d", "n3e", "-Atc", q
    ).strip()


class Peer(BasePeer):
    def respawn(self, seq, entity=None, session=None):
        self.send(
            19,
            integer(1, self.session if session is None else session)
            + integer(2, seq)
            + integer(3, self.id if entity is None else entity),
        )
        return first(self.until(20)[1], 2).decode()


def connect(name):
    p = Peer(
        port,
        name,
        password,
        game=m["game_id"],
        protocol=3,
        content=(package / "release.sha256").read_text().strip(),
    )
    peers.append(p)
    return p


def update(seconds=0.15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for p in peers:
            if p.s.fileno() >= 0 and p.id:
                p.until(10)


def wait(pred, seconds=12):
    end = time.monotonic() + seconds
    while not pred():
        assert time.monotonic() < end, "condition deadline"
        update(0.05)


def hp(p, id=None):
    return first(p.entities[p.id if id is None else id], 7)


def travel(p, x, z):
    for _ in range(250):
        e = p.entities[p.id]
        dx = x - first(e, 3)
        dz = z - first(e, 5)
        d = math.hypot(dx, dz)
        if d < 0.15:
            return
        assert hp(p) > 0, "died in travel"
        p.move(dx / max(1, d), dz / max(1, d), mode=1)
        time.sleep(timescale.ticks(1.04))  # one accepted move per tick
        update(0.001)
    raise AssertionError("travel deadline")


def start():
    global port
    try:
        dc("up", "--build", "-d", "--wait", "--force-recreate", "server")
    except AssertionError:
        logs = subprocess.run(base + ["logs", "--no-color", "--tail", "40", "server"], env=env, text=True, capture_output=True)
        raise AssertionError("server did not start:\n" + logs.stdout + logs.stderr)
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])


try:
    start()
    timescale.confirm_log(dc("logs", "--no-color", "server"))
    for name in ["alpha", "beta", "crash0", "crash1", "crash2", "crash3"]:
        p = subprocess.run(
            base + ["exec", "-T", "server", "n3e-server", "account-create", name],
            env=env,
            input=password + "\n",
            text=True,
            capture_output=True,
        )
        assert p.returncode == 0, p.stderr
    p = connect("alpha")
    aid = p.create("Alpha")
    p.select(aid)
    q = connect("beta")
    bid = q.create("Beta")
    q.select(bid)
    assert p.respawn(1) == "not_dead"
    assert p.respawn(2, session=p.session + 1) == "stale_session"
    travel(p, -1.5, -1.5)
    old = p.id
    wait(lambda: hp(p) == 0)
    assert p.respawn(2) == "too_early"
    # The durable deadline is the 60-tick delay at the server's tick, never longer
    # (PQ-115: 1.5 s at a 25 ms test tick, 3 s in production); "too_early" above
    # and the ready state below show it is not shorter either.
    left = float(sql(f"SELECT extract(epoch FROM respawn_ready_at - clock_timestamp()) FROM characters WHERE id={aid}"))
    assert left <= timescale.ticks(60) + 0.05, (left, timescale.TICK_MS)
    deadline = sql(f"SELECT respawn_ready_at FROM characters WHERE id={aid}")
    death_pos = (first(p.entities[p.id], 3), first(p.entities[p.id], 5))
    p.logout()
    p = connect("alpha")
    p.select(aid)
    assert hp(p) == 0 and p.id != old
    old = p.id
    assert death_pos == (first(p.entities[p.id], 3), first(p.entities[p.id], 5))
    assert sql(f"SELECT respawn_ready_at FROM characters WHERE id={aid}") == deadline
    assert p.respawn(1) == "too_early"
    assert (
        p.action(next(i for i, e in p.entities.items() if first(e, 9))) == "actor_dead"
    )
    wait(lambda: first(p.entities[p.id], 16) == 3)
    update(timescale.ticks(10))
    assert p.id == old and hp(p) == 0
    # Login left the observer with queued baselines; compare at the same or later tick.
    while q.tick < p.tick:
        q.until(10)
    assert q.entities[old][16] == p.entities[old][16]
    pos = (first(p.entities[old], 3), first(p.entities[old], 5))
    p.move(1, 0)
    update()
    assert pos == (first(p.entities[old], 3), first(p.entities[old], 5))
    assert p.respawn(3, entity=q.id) == "stale_entity"
    assert p.respawn(4) == "respawned"
    assert p.respawn(4, entity=old) == "stale_request"
    assert p.respawn(5, entity=old) == "stale_entity"
    update()
    assert p.id != old and old not in q.entities and p.id in q.entities
    assert hp(p) == 30 and first(p.entities[p.id], 16) == 1
    assert p.respawn(6) == "not_dead"
    print(
        "PASS live/premature/duplicate/stale guards, death movement/action denial, two-peer ready state and replacement",
        flush=True,
    )
    # Kill from outside the smaller NPC attack range; corpse disappears before automatic replacement.
    travel(p, -1.5, -1.5)
    target = next(i for i, e in p.entities.items() if first(e, 9))
    wait(
        lambda: math.hypot(
            first(p.entities[target], 3) - first(p.entities[p.id], 3),
            first(p.entities[target], 5) - first(p.entities[p.id], 5),
        )
        <= 2.9
    )
    result = p.action(target)
    assert result == "hit", result
    update(0.1)
    assert hp(p, target) == 0 and first(p.entities[target], 16) == 4
    respawn_tick = first(p.entities[target], 11)
    wait(lambda: target not in p.entities and target not in q.entities, 4)
    assert p.tick < respawn_tick and target not in q.entities
    wait(lambda: p.tick >= respawn_tick + 2, 8)
    assert (
        target not in p.entities
        and len([e for e in p.entities.values() if first(e, 9)]) == 2
    )
    op = target
    assert sql(f"SELECT count(*) FROM reward_operations WHERE operation={op}") == "1"
    wait(lambda: hp(p) == 0)
    dead = p.id
    generation = p.session
    p.logout()
    p = connect("alpha")
    p.select(aid)
    assert p.id != dead and hp(p) == 0
    assert p.respawn(1, entity=dead, session=generation) == "stale_session"
    assert p.respawn(1, entity=dead) == "stale_entity"
    wait(lambda: first(p.entities[p.id], 16) == 3)
    assert p.respawn(2) == "respawned"
    update()
    p.send(17, integer(1, op))
    assert first(p.until(18)[1], 2) == b"committed"
    print(
        "PASS NPC corpse absence/independent respawn, dead reconnect fresh identity and recovered durable grant",
        flush=True,
    )
    p.logout()
    q.logout()
    # Recreate with same durable volume and a shorter synthetic player delay so the
    # pending reward overlap fits inside the retained 2-second lease safety window.
    package = packages[1]
    env["N3E_PACKAGE_PATH"] = str(package)
    # Since Phase 4 a realm's world revision is bound to its release hash and the
    # server refuses another package (incompatible_base). This lab swaps packages
    # only to shorten the delay, so drop the revision to re-baseline (PQ-001).
    sql(f"DELETE FROM world_revisions WHERE realm='{realm}'")
    start()
    p = connect("alpha")
    p.select(aid)
    assert hp(p) == 90 and p.id != dead
    p.send(17, integer(1, op))
    assert first(p.until(18)[1], 2) == b"committed"
    # A real table lock blocks only reward INSERT. The server's sessions wait for a
    # lock at most lock_timeout (800 ms, server/src/persistence.rs), and a grant that
    # times out fails closed: the realm ends admission and exits (simulation.rs), and
    # its renewal thread logs "lease renewal stopped: realm lease lost". PQ-374: the
    # gate's run held the lock past that bound. Its hold was the action, a
    # `docker compose exec` (a pg_stat_activity check), a 0.2 s sleep and the
    # COMMIT; which of them stretched to 800 ms is not known (evidence
    # record). The hold now ends once the death is pending or one NPC cooldown
    # after the INSERT started waiting (Postgres says when), and only reads on the
    # open psql session and on the peer's socket run inside it.
    # PQ-128: the psql session starts here, before the race below. One NPC strikes
    # twice, a cooldown (10 ticks) apart (90 -> 60 -> 30 HP), and the other, still
    # closing in, strikes 3 or 4 ticks later and kills (PQ-374 run: 30 HP at tick 90,
    # no frame after tick 92), so the player has about 3 ticks between seeing 30 HP
    # and dying: 75 ms at a 25 ms test tick. `docker compose exec` took about 70 ms,
    # and a slower start under load lost the race (`actor_dead` in the action below,
    # PQ-128 evidence); only the LOCK statement and the action run in it.
    locker = subprocess.Popen(
        base + ["exec", "-T", "postgres", "psql", "-U", "n3e", "-d", "n3e", "-At"],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def psql(statement, answer):
        """The first output line that starts with `answer`, without that prefix."""
        locker.stdin.write(statement + "\n")
        locker.stdin.flush()
        while not (line := locker.stdout.readline()).startswith(answer):
            assert line, "psql session ended"
        return line.strip()[len(answer):]

    def frames(until, quiet):
        """Reads p's world frames until none has come for `quiet` seconds, or until
        `until` (monotonic), and never blocks past either: the server publishes no
        world frame while a death commit is pending, so a blocking read (update)
        would stretch the hold. Frames that arrived while this process was not
        running are read before a gap counts. Returns when the last frame came."""
        last = time.monotonic()
        while True:
            if p.s.pending() or select.select([p.s], [], [], 0)[0]:
                if p.receive()[0] == 10:
                    last = time.monotonic()
                    # Death cannot be published while its commit queues behind this grant.
                    assert hp(p) == 30, ("death published before its grant", hp(p))
                continue
            now = time.monotonic()
            if now >= until or now - last >= quiet:
                return last
            select.select([p.s], [], [], min(until, last + quiet) - now)

    # World frames come every 2 ticks, and while the realm owns admission only a
    # pending life commit stops them (simulation.rs): a 6-tick gap is the death,
    # queued behind this grant. The hold ends there, and after one NPC cooldown
    # (10 ticks) at the latest, well inside lock_timeout.
    quiet, hold = timescale.ticks(6), timescale.ticks(10)  # 300 and 500 ms at 50 ms
    assert hold + 0.2 < LOCK_TIMEOUT, hold
    waiting = released = None
    try:
        psql("SELECT 'ready';", "ready")
        # Let both NPCs approach; the second can kill the player after the first's grant starts.
        travel(p, -1.5, -1.5)
        targets = [i for i, e in p.entities.items() if first(e, 9)]
        wait(lambda: hp(p) == 30)
        # Hit the NPC that struck last (dict order named it before PQ-374): the other
        # one's next strike is the lethal one, inside the hold below.
        target = max(targets, key=lambda i: first(p.entities[i], 10))
        seen = p.tick
        psql("BEGIN; LOCK TABLE reward_operations IN SHARE MODE; SELECT 'locked';", "locked")
        locked = time.monotonic()
        before = (first(p.inventory, 2), first(p.inventory, 4))
        result = p.action(target)
        assert result == "hit", result
        # The grant's INSERT queues behind the lock: its own lock request, not
        # granted, and how long it has waited (pg_locks.waitstart, Postgres 14+;
        # null for a moment after the wait starts), so the hold is timed from the
        # wait's start even when the action's reply came late.
        while not (age := psql(
            "SELECT 'waiting ' || coalesce(extract(epoch FROM clock_timestamp() - min(waitstart))::text, '')"
            " FROM pg_locks WHERE relation = 'reward_operations'::regclass AND NOT granted;",
            "waiting ",
        )):
            assert time.monotonic() < locked + 0.3, "the grant never waited on the lock"
        waiting = time.monotonic() - float(age)
        assert (first(p.inventory, 2), first(p.inventory, 4)) == before
        last = frames(waiting + hold, quiet)
    finally:
        locker.stdin.write("ROLLBACK;\n")
        locker.stdin.flush()
        released = time.monotonic()
        locker.stdin.close()
        assert locker.wait(timeout=5) == 0
    held = released - waiting
    print(
        f"INFO reward lock: grant waiting {1000 * (waiting - locked):.0f} ms after the lock,"
        f" for {1000 * held:.0f} ms; 30 HP at tick {seen}, last frame at tick"
        f" {p.tick}, {1000 * (released - last):.0f} ms before the release",
        flush=True,
    )
    # A hold this suite stretched past the server's bound would end the realm.
    assert held < LOCK_TIMEOUT - 0.1, ("reward lock held past lock_timeout", held)
    # The death was decided while the grant waited (the frames stopped before the
    # release), and the first frame once the grant has committed shows it.
    assert released - last >= quiet, ("frames until the release", released - last)
    p.until(10)
    assert hp(p) == 0, ("death not pending behind the grant", hp(p))
    old = p.id
    wait(lambda: first(p.entities[p.id], 16) == 3, 2)
    assert p.respawn(1) == "respawned"
    update(0.05)
    new = p.id
    assert new != old
    wait(lambda: first(p.inventory, 6) == 0, 3)
    assert p.id == new and hp(p) == 90
    assert (
        sql(f"SELECT count(*) FROM reward_operations WHERE operation={target}") == "1"
    )
    count, xp = first(p.inventory, 2), first(p.inventory, 4)
    assert (count, xp) == (
        before[0] + m["gameplay"]["reward_items"],
        before[1] + m["gameplay"]["reward_xp"],
    )
    p.logout()
    dc("restart", "server")
    dc("up", "-d", "--wait", "server")
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    p = connect("alpha")
    p.select(aid)
    assert p.id != new and (first(p.inventory, 2), first(p.inventory, 4)) == (count, xp)
    assert p.respawn(1, entity=old) == "stale_entity"
    print(
        "PASS real pending grant across death/request/replacement, no stale entity revival, exactly-once grant after restart",
        flush=True,
    )
    travel(p, -1.5, -1.5)
    wait(lambda: hp(p) == 0)
    crashed = p.id
    death_pos = (first(p.entities[p.id], 3), first(p.entities[p.id], 5))
    assert sql(f"SELECT dead FROM characters WHERE id={aid}") == "t"
    dc("kill", "-s", "SIGKILL", "server")
    p.s.close()
    time.sleep(3.2)
    dc("up", "-d", "--wait", "server")
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    p = connect("alpha")
    p.select(aid)
    assert p.id != crashed and hp(p) == 0
    assert (first(p.inventory, 2), first(p.inventory, 4)) == (count, xp)
    assert death_pos == (first(p.entities[p.id], 3), first(p.entities[p.id], 5))
    assert first(p.entities[p.id], 16) == 3
    assert p.respawn(1, entity=crashed) == "stale_entity"
    assert p.respawn(2) == "respawned"
    print(
        "PASS process killed while dead: dead instance recovered, stale corpse request denied, acknowledged grant preserved",
        flush=True,
    )
    p.logout()
    # The same disposable volume crosses real process exits on both sides of each commit.
    # An account per crash point (three logins each): the server allows 10 logins
    # per account per 60 s of wall time (server/src/cache.rs), which this loop on
    # one account reaches when a scaled run compresses it (PQ-115).
    for crash, point in enumerate([
        "death_before_commit",
        "death_after_commit",
        "respawn_before_commit",
        "respawn_after_commit",
    ]):
        p = connect(f"crash{crash}")
        cid = p.create("Crash" + point.replace("_", "")[:18])
        p.select(cid)
        if point.startswith("respawn"):
            travel(p, -1.5, -1.5)
            wait(lambda: hp(p) == 0)
            wait(lambda: first(p.entities[p.id], 16) == 3)
        p.logout()
        env["N3E_LIFE_FAULT"] = point
        start()
        p = connect(f"crash{crash}")
        p.select(cid)
        try:
            if point.startswith("death"):
                travel(p, -1.5, -1.5)
                update(5)
            else:
                p.send(19, integer(1, p.session) + integer(2, 1) + integer(3, p.id))
                p.until(20)
            raise AssertionError("life fault did not terminate server")
        except DISCONNECTED:  # not a timeout (PQ-126)
            pass
        finally:
            p.s.close()
        deadline = time.monotonic() + 5
        while dc("ps", "-a", "--format", "{{.State}}", "server").strip() != "exited":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        expected_dead = point in ["death_after_commit", "respawn_before_commit"]
        assert sql(f"SELECT dead FROM characters WHERE id={cid}") == (
            "t" if expected_dead else "f"
        )
        revision = int(sql(f"SELECT life_revision FROM characters WHERE id={cid}"))
        assert (
            revision
            == {
                "death_before_commit": 0,
                "death_after_commit": 1,
                "respawn_before_commit": 1,
                "respawn_after_commit": 2,
            }[point]
        )
        time.sleep(3.2)
        env["N3E_LIFE_FAULT"] = ""
        start()
        p = connect(f"crash{crash}")
        p.select(cid)
        assert (hp(p) == 0) == expected_dead
        if expected_dead:
            assert first(p.entities[p.id], 16) == 3
            assert p.respawn(1) == "respawned"
            update()
        else:
            assert hp(p) == 90
        p.logout()
        print(
            "PASS " + point + ": committed lifecycle recovered after lost response",
            flush=True,
        )
finally:
    for p in peers:
        p.s.close()
    # PQ-128: every service's log, before the stack is removed.
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    (B / "live-server.log").write_text(dc("logs", "--no-color", "server"))
    dc("down", "-v", "--remove-orphans")
    override.unlink(missing_ok=True)
