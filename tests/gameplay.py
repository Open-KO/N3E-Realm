"""Phase 3 isolated real Compose acceptance. Never touches default volumes."""

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
import world_peer
from world_peer import DISCONNECTED, Budget, Peer, blob, integer, first, fields
import schema
from isolation import DISPOSABLE_COMPOSE, container_logs

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
PACKAGE = pathlib.Path(
    os.environ.get("N3E_TEST_PACKAGE", "build/packages/legacy-demo")
).resolve()
RECIPE = json.loads((PACKAGE / "recipe.json").read_text())["manifest"]
GAME = RECIPE["game_id"]
CONTENT = (PACKAGE / "release.sha256").read_text().strip()


def package_ticks():
    """The attack cooldown and the respawn delay, in ticks, from the
    gameplay.bin the server loads (PQ-462). Rules::load (server/src/rules.rs)
    reads the magic, the action, item and npc strings (a little-endian u32
    length, then the bytes), then little-endian u32s: health, resource, damage,
    cost, cooldown_ticks, regen_ticks, npc_health, npc_damage,
    npc_cooldown_ticks, respawn_ticks. The cooker writes recipe.json from the
    same rules (tools/assetc/main.py), so the two must agree."""
    data = (PACKAGE / "gameplay.bin").read_bytes()
    assert data[:4] in (b"N3G1", b"N3G2", b"N3G3"), data[:4]
    at = 4
    for _ in range(3):
        at += 4 + struct.unpack_from("<I", data, at)[0]
    values = struct.unpack_from("<10I", data, at)
    ticks = values[4], values[9]
    assert ticks == (RECIPE["gameplay"]["cooldown_ticks"], RECIPE["gameplay"]["respawn_ticks"]), ticks
    return ticks


COOLDOWN, RESPAWN = package_ticks()
# The stand-still stage's bound on one death and revive, in ticks: its old
# 12 s deadline at the 50 ms tick this suite's server runs (it is not scaled;
# server/src/clock.rs).
STAND_TICKS = 240
# PQ-463: the strike's reach and the NPC's full health from the same rules
# (the cooker writes recipe.json from them). The package has no melee policy,
# so the server compares the 3-D distance with `range` (gameplay.rs validate).
RANGE = RECIPE["gameplay"]["range"]
NPC_HEALTH = RECIPE["gameplay"]["npc_health"]
# One step's length: 0.15 times the move direction scaled by speed / 3
# (server/src/simulation.rs apply_movement without a movement policy,
# movement.rs step_soup).
STEP = 0.15 * RECIPE["gameplay"]["speed"] / 3
# Attempts at the first stage's strikes (PQ-463), as the outage stage allows
# three (PQ-419).
ATTEMPTS = 3
B = ROOT / (
    "build/ko-gameplay" if "N3E_TEST_PACKAGE" in os.environ else "build/gameplay"
)
B.mkdir(parents=True, exist_ok=True)
project = "n3e-p3-" + uuid.uuid4().hex[:10]
override = B / (project + ".yaml")
override.write_text(
    'services:\n  postgres:\n    ports: ["127.0.0.1::5432"]\n  server:\n    environment:\n      N3E_REWARD_FAULT: "${N3E_REWARD_FAULT:-}"\n    ports: ["127.0.0.1::8080"]\n'
)
if image := os.environ.get("N3E_TEST_IMAGE"):
    override.write_text(override.read_text().replace("  server:\n", f"  server:\n    image: {image}\n") + f"  migrate:\n    image: {image}\n")
env = {
    **os.environ,
    "N3E_PORT": "0",
    "N3E_PACKAGE_PATH": str(PACKAGE),
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
    return Peer(port, name, password, content=CONTENT, game=GAME)


def recreate_server():
    """Replace the server container, first appending the old one's log to
    servers.txt: Compose logs show only the current container, so a server the
    suite replaced (a fault point's crash included) would leave no trace (PQ-368)."""
    with open(B / "servers.txt", "a") as out:
        out.write(dc("logs", "--no-color", "--timestamps", "server", good=False).stdout)
    dc("up", "-d", "--no-deps", "--force-recreate", "server")


def refresh_port():
    return int(dc("port", "server", "7777").stdout.strip().rsplit(":", 1)[1])


def crash_restarts():
    """Postgres crash-restart lines so far (PQ-155): a backend, or an orphan
    the postmaster reaped, exited abnormally and every session was killed."""
    logs = dc("logs", "--no-color", "postgres").stdout
    return re.findall(r".*(?:terminating any other active server processes|exited with exit code (?:[2-9]|\d\d+)\b|was terminated by signal).*", logs)


def npc(p):
    return next((i for i, e in p.entities.items() if first(e, 9)), None)


def after_result(p):
    """The inventories of the World frames `p` reads after a result, up to the
    first frame the server published after it resolved that request (PQ-459).

    Results go out on the session's reliable queue, World frames through a
    latest-only slot, and the writer prefers the queue (server/src/network.rs).
    So the first frame read after a result can be one the simulation published
    before it resolved the request, but that frame's tick is at least the last
    one published before it, and every frame published since carries a later
    tick. The first frame with a tick past the first one's is therefore the
    server's state after the request, however late the frames arrive: the wait
    is two server frames (each under `until`'s own hang deadline), never a
    wall-time pump."""
    frames = [p.until(10)[1]]
    while first(frames[-1], 1) <= first(frames[0], 1):
        frames.append(p.until(10)[1])
    return [fields(first(f, 5, b"")) for f in frames]


def watch(p, done, what, ticks=None, guard=30):
    """Read `p`'s World frames until `done()` holds for what they show
    (PQ-463), the one wait the stages' conditions share. `ticks` bounds the
    server ticks that may pass from the first frame looked at: a condition the
    server meets within that many of its own ticks, however slowly the harness
    reads. `guard` wall seconds (None for none) only catch a server that stops
    publishing or never meets it; each frame is read under `until`'s own hang
    deadline."""
    start, end = p.tick, None if guard is None else time.monotonic() + guard
    while not done():
        assert ticks is None or p.tick - start <= ticks, (what, "tick bound", start, p.tick, ticks)
        assert end is None or time.monotonic() < end, (what, "hang guard", guard, start, p.tick)
        p.until(10)


def frame_since(p, tick):
    """Read `p`'s World frames up to the first with a tick of at least `tick`
    (PQ-461). Every session's frames carry the realm's one tick, so a peer that
    received no result itself still sees a request another peer made once its
    frame's tick reaches the tick of the frame `after_result` returned there.
    Each frame is read under `until`'s own hang deadline."""
    watch(p, lambda: p.tick >= tick, ("frame since", tick), guard=None)


def refused(p, since):
    """An Error frame `p` received since `since` (time.monotonic()): `until`
    drops frames it was not asked for, but Peer notes each Error's arrival."""
    return [w for w, (_, at) in p.notices.items() if w.startswith("Error") and at >= since]


def walk(p, x, z, steps):
    """Take `steps` movement steps of (x, z), each one applied by the server
    (PQ-463). The simulation applies one movement per session per tick, holds
    one more for the tick after and refuses a third (server/src/move_queue.rs,
    D-207), and frames go out every second tick. So the moves go two at a
    time, and the next two only once a frame's own entity acknowledges the
    second (Entity.ack, set where the move is applied: simulation.rs
    apply_movement): the server admits every move whatever the pace of either
    side, and the last frame read shows where the last one left the character.
    A refused move fails the walk."""
    since = time.monotonic()
    for i in range(0, steps, 2):
        for _ in range(min(2, steps - i)):
            p.move(x, z)
        seq = p.seq
        watch(p, lambda: first(p.entities[p.id], 6) >= seq or refused(p, since), ("move ack", seq))
        assert not refused(p, since), ("move refused", seq, refused(p, since))


def gap(p, target):
    """The 3-D distance between `p`'s character and `target` in `p`'s last
    frame, as validate measures it, or None when the frame does not show it."""
    me, other = p.entities.get(p.id), p.entities.get(target)
    if not me or not other:
        return None
    return sum((first(me, k, 0.0) - first(other, k, 0.0)) ** 2 for k in (3, 4, 5)) ** 0.5


class Lost(Exception):
    """The server's own frames show that the state the first stage's checks
    rest on had passed: the NPC killed the character (or killed and revived
    it), was still within reach after the walk away or reached the character
    before the strike from out of reach was handled, or the re-strike may have
    been handled after the cooldown ran out (PQ-463). The attempt starts over
    (at most ATTEMPTS); only `check` and `strikes` raise it."""


def check(p, start, what):
    """Raise Lost when `p`'s last frame shows its character dead, or revived
    under an id other than `start`: the NPC fights back on the server's clock,
    and once it has killed the character it heals at home (gameplay.rs Npc
    step, `return`)."""
    me = p.entities.get(p.id, {})
    if p.id != start or first(me, 7) == 0:
        raise Lost(f"{what}: the NPC killed the character first (entity {start} -> {p.id}, health {first(me, 7)}, tick {p.tick})")


def burst(p, target, seqs):
    """Send one strike Action per sequence number in `seqs` in a single write
    and return their results in order (PQ-463). The server's session reader
    forwards each request to the simulation as it decodes it
    (server/src/network.rs, Body::Action), and the simulation handles every
    queued command at the start of its next iteration (up to 256,
    simulation.rs), so requests sent together are handled in one iteration, or
    in the next if one starts between two decodes. How the harness is paced
    after the write no longer matters."""
    data = b""
    for seq in seqs:
        envelope = blob(15, integer(1, p.session) + integer(2, seq) + integer(3, target) + blob(4, p.action_id))
        data += struct.pack(">I", len(envelope)) + envelope
    world_peer._check()  # as Peer.raw: a failed keepalive fails here
    with p.lock:
        try:
            p.s.sendall(data)
        except BaseException:
            p.keepalive = False  # as Peer._write: no usable stream after a failed send
            raise
        p.last = time.monotonic()
    p.action_seq = max(p.action_seq, *seqs)
    results = []
    for seq in seqs:
        tag, result = p.until(16, 4)
        assert tag == 16 and first(result, 1) == seq, (tag, result, seq)
        results.append(first(result, 2, b"").decode())
    return results


def cooled(p, other=None):
    """Wait out `p`'s attack cooldown in the server's ticks, not wall time
    (PQ-462). The frame after_result returns postdates `p`'s last request, so
    `p`'s own entity there carries the tick of its last strike. The server
    refuses an action as cooldown only while the tick it handles it with is
    below that strike's tick plus cooldown_ticks (gameplay.rs validate and
    finish_attack), and it handles an action that left after a frame of tick
    F with the tick of the last iteration run, F or later (simulation.rs drains
    commands before it advances the tick). So an action sent once a frame
    reaches the strike's tick plus COOLDOWN is past the cooldown, however many
    ticks the timer skipped. `other`'s frames are read up to the same tick."""
    after_result(p)
    frame_since(p, first(p.entities[p.id], 10) + COOLDOWN)
    if other:
        frame_since(other, p.tick)


def stand_still(a, cycles=3):
    """Leave `a` idle until the NPC kills it and the server revives it under a
    new runtime entity id, and strike on every frame that shows it dead
    (PQ-462). Bounded by STAND_TICKS frame ticks per death, not wall time.

    A strike is answered `actor_dead` while the character is dead, but the
    server can revive it between the frame that showed it dead and the
    strike's handling. So a strike answered otherwise passes only when the
    frame published after it shows the character revived, and the stage
    waits for another death (at most `cycles`) until one strike was denied.
    The revive must come no earlier than the respawn tick the dead entity
    carried. The 30 s a death adds to the wall guard only catch a server that
    stops publishing; they are no bound the stage is expected to meet."""
    guard = time.monotonic() + 30 * cycles
    for _ in range(cycles):
        old, start, respawn, denied = a.id, a.tick, None, False
        while a.id == old:
            assert a.tick - start <= STAND_TICKS and time.monotonic() < guard, (
                "stand-still deadline", start, a.tick, respawn, denied)
            a.until(10)
            if a.id != old or first(a.entities[a.id], 7) != 0:
                continue
            respawn = first(a.entities[a.id], 11)
            result = a.action(npc(a))
            after_result(a)
            if result == "actor_dead":
                denied = True
            else:
                assert a.id != old, ("a dead character's strike was not denied", result, a.tick, respawn)
        assert respawn is not None and a.tick >= respawn, (old, a.id, a.tick, respawn)
        if denied:
            return
        print(
            f"NOTE stand-still: every strike while dead was answered after the revive at tick {a.tick}; waiting for another death",
            flush=True,
        )
    raise AssertionError(("no strike while dead was denied", cycles))


def settled(p, op, seen, guard=30):
    """Continue `seen` (after_result's inventories after a lethal strike on
    `op`) with every World frame `p` reads while that reward stays pending,
    and return them all (PQ-461). The reward task commits in Postgres when it
    does, so the wait ends on the server's own state, the first frame that no
    longer shows `op` pending. `guard` seconds only catch a reward that never
    settles; it is no bound the commit is expected to meet."""
    end = time.monotonic() + guard
    while first(seen[-1], 6) == op and first(seen[-1], 8) == b"pending":
        assert time.monotonic() < end, ("reward did not settle", op, guard)
        seen.append(fields(first(p.until(10)[1], 5, b"")))
    return seen


def kill(p, other=None):
    """Strike the NPC until the frame after a strike shows its reward pending
    or committed, and return its id. PQ-463: bounded by resolved strikes and
    other answers (world_peer.Budget, PQ-123), not by 15 s of wall time: the
    NPC fights back on the server's clock and heals once it has killed the
    character, so the strikes a kill takes depend on how the two paces
    interleave. Twelve strikes are four of the NPC's lives; the 120 s guard
    only catches a stalled server."""
    budget = Budget("kill", strikes=12)
    while budget.ok():
        p.until(10)
        if other:
            frame_since(other, p.tick)
        if first(p.entities[p.id], 7) == 0:
            # PQ-462: dead; the server revives the character at the respawn
            # tick its entity carries. Wait for that tick, not 3.3 s.
            frame_since(p, first(p.entities[p.id], 11))
            continue
        target = npc(p)
        # Strike only when the frame shows the NPC alive and in reach, rather
        # than every 0.15 s whatever it shows.
        if not target or first(p.entities[target], 7) == 0 or gap(p, target) > RANGE:
            continue
        if budget.result(p.action(target)) == "hit":
            # PQ-461: a 0.1 s pump could read only a frame that predated
            # the strike and so miss the kill. The frame published after
            # the strike shows this NPC's reward pending, or committed.
            inventory = after_result(p)[-1]
            if first(inventory, 6) == target or first(inventory, 7) == target:
                return target
            cooled(p, other)


def placed(p, start, x, z, what):
    """Assert the position `p`'s last frame reports for its character: the
    walk's steps were applied, not only acknowledged (`ack` also advances for
    a dead character's move, which does not move it, and when moves are
    cleared). Call after check(), so a death is Lost rather than a failure;
    a live character's applied steps do not depend on either side's pace."""
    check(p, start, what)
    me = p.entities[p.id]
    assert abs(first(me, 3, 0.0) - x) < 1e-3 and abs(first(me, 5, 0.0) - z) < 1e-3, (
        what, "position", (first(me, 3, 0.0), first(me, 5, 0.0)), (x, z), p.tick)


def strike(p, target, start, what):
    """One strike that must hit; any other answer raises Lost when the frame
    published after it shows the character dead or revived, and fails
    otherwise."""
    result = p.action(target)
    if result != "hit":
        after_result(p)
        check(p, start, f"{what} answered {result}")
        raise AssertionError((what, result, p.tick, p.entities))


def strikes(a, b, target):
    """One attempt at the first stage's strikes (PQ-463): out of reach, back in
    reach, a hit with its repeated packet and an immediate re-strike, then two
    hits past the cooldown, the second lethal. Returns the counts before the
    lethal strike and the inventories after it (after_result).

    Every answer is the one the stage expects, or the attempt raises Lost on
    the server's own evidence that the harness fell behind its clock (see
    Lost); any other answer fails, and so does a position after a walk that is
    not exactly where the steps lead (placed). The NPC
    fights the character from the start (aggro_range), kills it in five
    swings and heals once it has (gameplay.rs Npc step), and chases it at
    npc_speed while it stands out of reach. No attempt that raises Lost has
    killed the NPC: a lethal strike leaves the character alive under its id."""
    start = a.id
    assert first(a.entities[start], 7) > 0 and first(a.entities[target], 7) == NPC_HEALTH, (a.tick, a.entities)
    x0, z0 = first(a.entities[start], 3, 0.0), first(a.entities[start], 5, 0.0)
    walk(a, 0, -1, 12)
    placed(a, start, x0, z0 - 12 * STEP, "walking out of reach")
    far = gap(a, target)
    if far is not None and far <= RANGE:
        raise Lost(f"the NPC was within reach ({far:.3f} <= {RANGE}) after the character's 12 steps away, tick {a.tick}")
    result = a.action(target)
    if result != "out_of_range":
        # The NPC chases a character that stands still, so it is no farther
        # at the frame after the strike than when the strike was handled: a
        # hit is a lost race only if that frame shows it within reach. A dead
        # or revived character is Lost (check); any other answer fails.
        after_result(a)
        check(a, start, f"the strike from out of reach answered {result}")
        near = gap(a, target)
        if result == "hit" and near is not None and near <= RANGE + 1e-4:
            raise Lost(f"the NPC reached the character ({near:.3f} <= {RANGE}, tick {a.tick}) before the strike from out of reach was handled")
        raise AssertionError(("out_of_range", result, far, near, a.tick, a.entities))
    walk(a, 0, 1, 12)
    placed(a, start, x0, z0, "walking back into reach")

    def reach():
        check(a, start, "walking back into reach")
        d = gap(a, target)
        return d is not None and d <= RANGE - 1e-4

    # The NPC chases the character until it is within npc_range, so once a
    # frame shows it within reach it stays there.
    watch(a, reach, "the NPC within reach", ticks=STAND_TICKS)
    # The hit, its repeated packet and the re-strike go in one write, so the
    # re-strike is handled with the hit or an iteration later, whatever the
    # harness's pace (burst). The first must hit and the repeat answer
    # stale_action. The re-strike must answer cooldown unless the server's
    # ticks show it may have come cooldown_ticks after the hit (its strike
    # tick at least that far past the last frame read before the write, the
    # earliest the hit can have been handled): then Lost. A hit sooner, or any
    # other answer, fails, except that a dead or revived character is Lost.
    last = a.tick
    seq = a.action_seq + 1
    hit, stale, again = burst(a, target, [seq, seq, seq + 1])
    if hit != "hit":
        after_result(a)
        check(a, start, f"the strike in reach answered {hit}")
        raise AssertionError(("hit", hit, stale, again, a.tick, a.entities))
    assert stale == "stale_action", (stale, again)
    if again != "cooldown":
        after_result(a)
        check(a, start, f"the re-strike answered {again}")
        struck = first(a.entities[a.id], 10)
        if again == "hit" and struck >= last + COOLDOWN:
            raise Lost(f"the server handled the re-strike at tick {struck}, {struck - last} ticks after the last frame before the write (cooldown {COOLDOWN})")
        raise AssertionError(("cooldown", again, last, struck, a.tick))
    cooled(a, b)
    check(a, start, "waiting out the cooldown")
    strike(a, target, start, "the strike after the cooldown")
    cooled(a, b)
    check(a, start, "waiting out the second cooldown")
    before = (first(a.inventory, 2), first(a.inventory, 4))
    strike(a, target, start, "the lethal strike")
    seen = after_result(a)
    check(a, start, "the lethal strike")
    return before, seen


def alive(p):
    """Wait out a death `p`'s frames show: the server revives the character
    at the respawn tick its entity carries (PQ-462)."""
    me = p.entities[p.id]
    if first(me, 7) == 0:
        frame_since(p, first(me, 11))
        assert first(p.entities[p.id], 7) > 0, (p.tick, p.entities[p.id])


def restart(a, b, target, spawn):
    """Set the first stage up again after Lost (PQ-463): both characters
    alive, alpha back at the spawn point, then both logged out, so the NPC
    loses its target, walks home and heals (gameplay.rs Npc step, `return`),
    and selected again in the stage's order. A selection gives full health
    and resource (simulation.rs Join) at the saved position, and the NPC takes
    the lowest character id within aggro_range, alpha's, as at the start."""
    frame_since(b, a.tick)
    alive(b)
    # The stage moves alpha along z only. A revive puts it at the spawn point,
    # so a death during the walk back is walked again.
    for tries in range(4):
        alive(a)
        me = a.entities[a.id]
        assert abs(first(me, 3, 0.0) - spawn[0]) < 1e-3, (me, spawn)
        steps = round((spawn[1] - first(me, 5, 0.0)) / STEP)
        if not steps:
            break
        assert tries < 3, ("alpha did not get back to the spawn point", spawn, me)
        walk(a, 0, 1 if steps > 0 else -1, abs(steps))
    a.logout()
    b.logout()
    a, b = login("alpha"), login("beta")
    assert a.select(aid)[0] == 10
    assert b.select(bid)[0] == 10
    watch(
        a,
        lambda: first(a.entities.get(target, {}), 7) == NPC_HEALTH and first(a.entities[target], 12, b"") != b"return",
        "the NPC heals at home",
        ticks=STAND_TICKS,
    )
    frame_since(b, a.tick)
    assert target in b.entities, (b.tick, b.entities)
    return a, b


(B / "servers.txt").write_text("")
try:
    dc("up", "-d", "--no-build")
    wait(ready)
    port = refresh_port()
    assert sql(schema.QUERY).splitlines() == schema.rows()
    for name in ["alpha", "beta"]:
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
    a, b = login("alpha"), login("beta")
    aid, bid = a.create("Alpha"), b.create("Beta")
    assert a.select(aid)[0] == 10
    assert b.select(bid)[0] == 10
    target = npc(a)
    assert target and target in b.entities
    assert a.action(target, session=a.session + 1) == "stale_session"
    assert a.action(target, action="forged:action") == "unknown_action"
    assert a.action(target + 999999) == "stale_target"
    # PQ-463: the moves are applied one per tick and the checks after them
    # rest on the NPC's own clock, so the strikes run as attempts that start
    # over (restart) when the server's frames show the harness fell behind
    # (Lost); a third lost attempt fails the stage.
    me = a.entities[a.id]
    spawn = (first(me, 3, 0.0), first(me, 5, 0.0))
    for attempt in range(ATTEMPTS):
        try:
            before, seen = strikes(a, b, target)
            break
        except Lost as lost:
            if attempt == ATTEMPTS - 1:
                raise AssertionError(("every attempt at the first stage's strikes was lost", str(lost)))
            print(f"RETRY first stage strikes: {lost}", flush=True)
            a, b = restart(a, b, target, spawn)
    # PQ-461: a 0.2 s pump read the reward and beta's view from whatever frames
    # arrived in that time, and the first frame after a result can predate the
    # strike. Read up to the frame published after it (strikes), then follow
    # the reward until it leaves pending: every frame shows either the counts
    # before the strike or this NPC's committed grant, never one and then the
    # other again, and the last shows the grant.
    frame_since(b, a.tick)
    assert first(b.entities[target], 7) == 0, (a.tick, b.tick, b.entities.get(target))
    # PQ-462: the dead NPC carries the tick it respawns at, the strike's tick
    # (alpha's entity in the frame after it) plus the package's respawn_ticks.
    respawn = first(b.entities[target], 11)
    assert respawn == first(a.entities[a.id], 10) + RESPAWN, (respawn, first(a.entities[a.id], 10), RESPAWN)
    seen = settled(a, target, seen)
    shown = [{k: first(i, k) for k in (2, 4, 6, 7, 8)} for i in seen]
    granted = [
        (first(i, 2), first(i, 4), first(i, 7), first(i, 8)) == (2, 10, target, b"committed")
        for i in seen
    ]
    assert all(g or (first(i, 2), first(i, 4)) == before for g, i in zip(granted, seen)), (before, shown)
    assert granted[-1] and granted == sorted(granted), (before, shown)
    assert first(a.inventory, 2) == 2 and first(a.inventory, 4) == 10, shown
    assert first(a.inventory, 8) == b"committed" and first(a.inventory, 7) == target, shown
    # PQ-463: once the reward settles the server replaces the dead NPC at its
    # respawn tick (simulation.rs keeps a pending NPC), and the commit runs in
    # Postgres on wall time. So the strike answers target_dead unless the
    # server handled it at or after the respawn tick. stale_target is then
    # accepted only if the frame published after it (a tick no earlier than
    # the handling) is at or past that tick and lacks the old NPC; any other
    # answer fails.
    result = a.action(target)
    if result != "target_dead":
        after_result(a)
        assert result == "stale_target" and a.tick >= respawn and target not in a.entities, (result, a.tick, respawn, a.entities.get(target))
        print(f"NOTE first stage: the strike on the dead NPC was handled after its respawn tick {respawn} (frame {a.tick}); stale_target", flush=True)
    for _ in range(2):
        a.send(17, integer(1, target))
        tag, result = a.until(18)
        assert first(result, 2) == b"committed" and first(result, 3) == 2
    b.send(17, integer(1, target))
    assert first(b.until(18)[1], 2) == b"unknown"
    a.send(18, integer(1, target + 1) + blob(2, "committed"))
    assert a.until(4)[0] == 4
    assert (
        sql(f"SELECT count(*) FROM reward_operations WHERE character_id={aid}") == "1"
    )
    print(
        "PASS two-player combat, authority, repeated packets, read-only reward status, forged reward denial",
        flush=True,
    )
    # PQ-462: the first frame at the respawn tick already shows the new NPC
    # (simulation.rs steps NPCs before it publishes), however many ticks the
    # timer skipped on the way; 3.1 s of wall time did not promise 60 ticks.
    frame_since(a, respawn)
    frame_since(b, a.tick)
    assert npc(a) != target, (a.tick, respawn, a.entities.get(target))
    assert a.action(target) == "stale_target"
    b.logout()
    # Stand still: NPC death and automatic respawn must replace runtime instance.
    stand_still(a)
    a.logout()
    a = login("alpha")
    assert a.select(aid)[0] == 10
    assert first(a.inventory, 2) == 2 and first(a.inventory, 4) == 10
    a.logout()
    print(
        "PASS NPC/player respawn identity, death denial and durable reconnect",
        flush=True,
    )
    # Run actual DB concurrency/fencing/migration tests against this isolated DB.
    pgport = int(dc("port", "postgres", "5432").stdout.strip().rsplit(":", 1)[1])
    testenv = {
        **os.environ,
        "N3E_TEST_DATABASE_URL": f"host=127.0.0.1 port={pgport} user=n3e password=n3e-local dbname=n3e",
    }
    p = subprocess.run(
        schema.core_test_command(),
        env=testenv,
        capture_output=True,
        text=True,
        timeout=90,
    )
    (B / "database-tests.txt").write_text(p.stdout + p.stderr)
    assert p.returncode == 0, (p.stdout, p.stderr)
    schema.assert_core_tests(p.stdout)
    print(
        "PASS real DB concurrent grants, duplicate/conflicting operation IDs, atomic full inventory, old-session fencing and migrations",
        flush=True,
    )
    # Crash at all durable boundaries, restart same volume, inspect immutable results.
    for point in ["before_commit", "after_commit", "before_response"]:
        dc("stop", "server")
        env["N3E_REWARD_FAULT"] = point
        recreate_server()
        wait(ready)
        port = refresh_port()
        a = login("alpha")
        assert a.select(aid)[0] == 10
        before = sql(
            f"SELECT count || ':' || xp FROM character_progress WHERE character_id={aid}"
        )
        ops = int(
            sql(f"SELECT count(*) FROM reward_operations WHERE character_id={aid}")
        )
        try:
            kill(a)
            # PQ-463: the fault fires in the reward task, which runs on
            # Postgres's wall-time pace, not within 1 s of the frame that
            # showed the reward. Read frames until the server goes; 30 s only
            # catch a server that stays up.
            end = time.monotonic() + 30
            while time.monotonic() < end:
                a.until(10)
            raise AssertionError("fault did not terminate server")
        except DISCONNECTED:  # not a timeout (PQ-126)
            pass
        finally:
            a.s.close()
        wait(
            lambda: dc("ps", "-a", "--format", "{{.State}}", "server").stdout.strip()
            == "exited"
        )
        after = sql(
            f"SELECT count || ':' || xp FROM character_progress WHERE character_id={aid}"
        )
        assert (after == before) == (point == "before_commit"), (point, before, after)
        assert int(
            sql(f"SELECT count(*) FROM reward_operations WHERE character_id={aid}")
        ) == ops + (point != "before_commit")
        wait(
            lambda: sql(
                "SELECT expires<=clock_timestamp() FROM realm_ownership WHERE realm='local'"
            )
            == "t",
            5,
        )
        env["N3E_REWARD_FAULT"] = ""
        recreate_server()
        wait(ready)
        port = refresh_port()
        a = login("alpha")
        assert a.select(aid)[0] == 10
        assert f"{first(a.inventory,2)}:{first(a.inventory,4)}" == after
        op = first(a.inventory, 7)
        a.send(17, integer(1, op))
        result = a.until(18)[1]
        assert first(result, 2) == b"committed"
        a.logout()
        print(
            "PASS crash " + point + ": restart preserved exactly-once durable state",
            flush=True,
        )
    # Disconnect immediately after a qualifying action: worker drains before logout acknowledgement.
    a = login("alpha")
    assert a.select(aid)[0] == 10
    op = kill(a)
    a.logout()
    assert sql(f"SELECT count(*) FROM reward_operations WHERE operation={op}") == "1"
    print("PASS disconnect reward drain", flush=True)
    if os.environ.get("N3E_GRAPHICAL") == "1":
        # Clients authenticate using fixture accounts; production controls/rendering carry combat.
        procs = []
        for name in ["alpha", "beta"]:
            log = open(B / (name + "-graphics.txt"), "w")
            procs.append(
                (
                    subprocess.Popen(
                        [
                            "build/client/n3e-test-client",
                            str(PACKAGE),
                            "--connect",
                            f"localhost:{port}",
                            "--ca",
                            "deploy/local/ca.pem",
                            "--world-smoke",
                            "18",
                            "--capture",
                            str(B / (name + ".ppm")),
                        ],
                        env={
                            **os.environ,
                            "N3E_TEST_ACCOUNT": name,
                            "N3E_TEST_PASSWORD": password,
                            "N3E_TEST_COMBAT": "1" if name == "alpha" else "observe",
                        },
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    ),
                    log,
                )
            )
        for p, log in procs:
            assert p.wait(timeout=30) == 0
            log.close()
        # PQ-199: the stand-in NPC has no death clip, so the one alpha kills is
        # a corpse at once; the replay aimed the click pick and B at it.
        corpse = (B / "alpha-graphics.txt").read_text()
        assert re.search(r"CORPSE_PICK entity=\d+ picked=\d+ b=\d+", corpse), "no corpse pick check ran"
        print("PASS simultaneous graphical combat walkthrough", flush=True)
    # Block an actual qualifying reward: snapshots must expose only pending, never a grant.
    # PQ-419: the NPC fights back from the moment the character enters and kills
    # it about 4 s later (30 health, 6 a swing every 20 ticks), while the stage
    # needs about 1.6 s plus the pause call. A pause call that stalls for the
    # rest (the gate's full run on 772251a) lets the NPC win, and the server
    # refuses the hit as actor_dead. That refusal, or any answer whose
    # following frame shows the character revived under a new id (PQ-463), is
    # retried on a new character once Postgres is unpaused and the server
    # restarted; any other result, or either case on the third attempt, fails
    # the stage.
    character = bid
    for attempt in range(3):
        a = login("beta")
        if attempt:
            character = a.create(f"Beta{attempt + 1}")
        assert a.select(character)[0] == 10
        # PQ-463: bounded by strikes and answers (Budget), not 10 s of wall
        # time; strike when a frame shows the character alive and the NPC in
        # reach, then wait out the cooldown in ticks.
        approach = Budget("pending reward approach", strikes=8)
        while approach.ok():
            a.until(10)
            target = npc(a)
            hp = first(a.entities[target], 7) if target else 0
            if hp == 10:
                break
            # PQ-461: the next read starts at the frame published after a hit,
            # so a frame that predates it cannot show the NPC's old health.
            if hp > 10 and first(a.entities[a.id], 7) > 0 and gap(a, target) <= RANGE:
                if approach.result(a.action(target)) == "hit":
                    cooled(a)
        assert hp == 10
        before_count = first(a.inventory, 2)
        before_xp = first(a.inventory, 4)
        # PQ-462: past the last approach strike's cooldown in ticks.
        cooled(a)
        me = a.id
        started = time.monotonic()
        dc("pause", "postgres")
        took = time.monotonic() - started
        landed = False
        try:
            result = a.action(target)
            # PQ-463: a stall long enough for the NPC to kill the character
            # and the server to revive it under a new id (the NPC healing
            # meanwhile) answers otherwise than actor_dead; the frame
            # published after the strike shows the new id. Retried as
            # actor_dead is (header above).
            if result != "actor_dead":
                seen = after_result(a)
            if (result == "actor_dead" or a.id != me) and attempt < 2:
                print(
                    f"RETRY pending reward outage: the NPC killed the character before the hit ({result}, entity {me} -> {a.id}, pause call {took:.2f} s)",
                    flush=True,
                )
            else:
                assert result == "hit" and a.id == me, (
                    result,
                    (me, a.id),
                    f"pause call {took:.2f} s",
                    {k: first(a.entities[a.id], k) for k in (3, 5, 7, 8)},
                    {k: first(a.entities.get(target, {}), k) for k in (3, 5, 7, 12)},
                )
                landed = True
                # PQ-459: a fixed 0.15 s pump read only the first frame after
                # the result when it arrived late, and that frame can predate
                # the strike. Every frame up to the first published after it
                # must show no grant; that one must show the reward pending.
                shown = [
                    {k: first(i, k) for k in (2, 4, 6, 8)} for i in seen
                ]
                if first(seen[0], 6) != target:
                    print(
                        f"NOTE pending reward outage: the first frame after the result predated the strike {shown[0]}",
                        flush=True,
                    )
                assert all(
                    first(i, 2) == before_count and first(i, 4) == before_xp for i in seen
                ), shown
                assert first(seen[-1], 6) == target and first(seen[-1], 8) == b"pending", (
                    target,
                    shown,
                )
                wait(lambda: not ready(), 8)
        finally:
            dc("unpause", "postgres")
            a.s.close()
        dc("restart", "server")
        wait(ready)
        if landed:
            break
        port = refresh_port()
    # PQ-155 (D-140): the outage must not crash-restart Postgres (a health probe
    # caught by the pause used to orphan pg_isready to the postmaster).
    assert not crash_restarts(), crash_restarts()
    print(
        "PASS pending reward cannot grant during Postgres outage; admission shuts down and explicit restart recovers",
        flush=True,
    )
    (B / "server.txt").write_text(dc("logs", "--no-color", "server", "migrate").stdout)
finally:
    (B / "server.txt").write_text(
        dc("logs", "--no-color", "server", "migrate", good=False).stdout
    )
    dc("unpause", "postgres", good=False)
    # PQ-128: every service's log, before the stack is removed.
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    dc("down", "--volumes", "--remove-orphans", good=False)
print("PASS Phase 3 gameplay integration", flush=True)
