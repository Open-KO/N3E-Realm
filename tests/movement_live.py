"""KO-01 isolated authority and two-client graphical verification. Own volumes only."""

import cmath
import json
import math
import os
from pathlib import Path
import re
import random
import subprocess
import threading
import time
import uuid
from world_peer import Peer, first, integer, real
from isolation import DISPOSABLE_COMPOSE, container_logs

B = Path("build/ko-01")
B.mkdir(parents=True, exist_ok=True)
package = Path(
    os.environ.get("N3E_MOVEMENT_PACKAGE", "build/packages/movement")
).resolve()
camera = os.environ.get("N3E_CAMERA") == "1"
controls = camera or os.environ.get("N3E_CONTROLS") == "1"
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
content = (package / "release.sha256").read_text().strip()
B = B / ("ko-graphics" if package.name.endswith("-ko") else "synthetic-graphics")
if controls:
    B = B / ("camera" if camera else "controls")
B.mkdir(parents=True, exist_ok=True)
project = "n3e-ko01-" + uuid.uuid4().hex[:10]
env = {
    **os.environ,
    "N3E_PORT": "0",
    "N3E_REALM": project,
    "N3E_PACKAGE_PATH": str(package),
    "N3E_UID": str(os.getuid()),
    "N3E_GID": str(os.getgid()),
}
base = ["docker", "compose", *DISPOSABLE_COMPOSE, "-p", project]
password = "test-only-" + uuid.uuid4().hex
clients = []
handles = []


def dc(*args, stdin=None):
    p = subprocess.run(
        base + list(args),
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert p.returncode == 0, (args, p.stdout, p.stderr)
    return p.stdout


def connect(name):
    return Peer(
        port, name, password, content=content, game=manifest["game_id"], protocol=2
    )


def position(p):
    e = p.entities[p.id]
    return [first(e, k) for k in [3, 4, 5]]


def jittered_walk(p, sends=200, jitter=0.02, before_drain=0.01):
    """PQ-404 (D-207): a peer on the test client's send schedule
    (client/network/world.cpp: one Move per 50 ms slot, `next += .05`, a late
    slot moves to `now + .05`), each send delayed by U(0, jitter), with the
    slots set `before_drain` ahead of the server's command drain, so arrival
    jitter often puts two sends in one drain (PQ-403: 93 of 400 refused under
    D-014's rule, 0 with one held ahead). The server must refuse none of them
    and, view by view, the position must be the start plus every input up to
    the view's ack, with at most one input applied per tick. Walks in legs of
    20 steps forward and back, so it stays within 1.5 m of where it starts."""
    views, errors, failure, stop = [], [], [], threading.Event()

    def reader():
        try:
            while not stop.is_set():
                tag, data = p.receive()
                now = time.monotonic()
                if tag == 4:
                    errors.append((first(data, 1), first(data, 2, b"")))
                elif tag == 10 and p.id in p.entities:
                    e = p.entities[p.id]
                    views.append((now, p.tick, first(e, 6), first(e, 3), first(e, 5)))
        except BaseException as e:  # reported by the main thread
            failure.append(e)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    time.sleep(1.5)
    assert not failure and len(views) > 8, (failure, len(views))
    # Views leave at the end of even ticks, a fraction of a millisecond after
    # that tick's drain: their arrival phase marks the drain.
    period = (views[-1][0] - views[0][0]) / (views[-1][1] - views[0][1])
    assert abs(period - 0.05) < 0.005, period
    drain = cmath.phase(
        sum(cmath.exp(2j * math.pi * (v[0] % 0.05) / 0.05) for v in views)
    ) / (2 * math.pi) * 0.05
    start_ack, x0, z0 = views[-1][2], views[-1][3], views[-1][4]
    assert start_ack == p.seq, (start_ack, p.seq)
    first_view = len(views)
    rng = random.Random(404)
    step_m = 1.5 * 0.05  # walk speed (movement_fixture) over one 50 ms tick
    expected = {p.seq: 0.0}
    now = time.monotonic()
    slot = now + (drain + 0.05 - before_drain - now) % 0.05
    for i in range(sends):
        while time.monotonic() < slot:
            time.sleep(0.0005)
        now = time.monotonic()
        slot += 0.05
        if slot <= now:
            slot = now + 0.05
        leave = now + rng.uniform(0, jitter)
        while time.monotonic() < leave:
            time.sleep(0.0005)
        z = -1 if (i // 20) % 2 == 0 else 1
        p.move(0, z, mode=0)
        expected[p.seq] = expected[p.seq - 1] + z * step_m
    deadline = time.monotonic() + 5
    while not failure and (len(views) == first_view or views[-1][2] < p.seq):
        assert time.monotonic() < deadline, (views[-1], p.seq, errors)
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5)
    assert not failure and not thread.is_alive(), failure
    assert errors == [], (len(errors), sends, errors[:5])
    run = views[first_view - 1 :]
    for (_, tick0, ack0, _, z0v), (_, tick1, ack1, x1, z1) in zip(run, run[1:]):
        assert 0 <= ack1 - ack0 <= tick1 - tick0, ("more than one input a tick", tick0, ack0, tick1, ack1)
        assert abs(z1 - z0v) <= (tick1 - tick0) * step_m + 1e-4, ("farther than one step a tick", tick0, z0v, tick1, z1)
        assert abs(x1 - x0) < 1e-5 and abs(z1 - (z0 + expected[ack1])) < 1e-3, (ack1, x1, z1, x0, z0 + expected[ack1])
    assert run[-1][2] == p.seq == start_ack + sends, (run[-1], p.seq)
    return len(run)


def step(p, x, z, mode):
    p.move(x, z, mode=mode)
    until = time.monotonic() + 3
    while first(p.entities[p.id], 6) < p.seq:
        assert time.monotonic() < until
        p.until(10)
    assert first(p.entities[p.id], 13) == mode
    q.send(14)
    q.until(10)


try:
    dc("up", "-d", "--wait")
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    # Old clients must fail even with the exact new package hash.
    try:
        Peer(port, content=content, game=manifest["game_id"], protocol=1)
    except AssertionError:
        pass
    else:
        raise AssertionError("old protocol admitted")
    for name in ["alpha", "beta", "jitter", "graphical0", "graphical1"]:
        dc(
            "exec",
            "-T",
            "server",
            "n3e-server",
            "account-create",
            name,
            stdin=password + "\n",
        )
    p = connect("alpha")
    character = p.create("Alpha")
    p.select(character)
    q = connect("beta")
    q.select(q.create("Beta"))
    for mode, speed in [(0, 1.5), (1, 4.5), (2, 1.5)]:
        before = position(p)
        for _ in range(20):
            step(p, 0, -1, mode)
        after = position(p)
        assert abs(after[2] - before[2] + speed) < 2e-5, (mode, before, after)
        q.pump(0.1)
        assert p.id in q.entities
        print(
            "PASS authoritative mode",
            mode,
            "20 accepted steps",
            speed,
            "metres",
            flush=True,
        )
    before = position(p)
    for _ in range(5):
        step(p, 0, 0, 1)
    assert position(p) == before
    # Invalid/stale requests cannot move or consume an accepted sequence.
    for x, z, mode, seq, session in [
        (1, 0, 99, p.seq + 1, p.session),
        (1.01, 0, 1, p.seq + 1, p.session),
        (float("nan"), 0, 1, p.seq + 1, p.session),
        (1, 0, 1, p.seq, p.session),
        (1, 0, 1, p.seq + 1, p.session + 1),
    ]:
        p.send(
            9,
            integer(1, session)
            + integer(2, seq)
            + real(3, x)
            + real(4, z)
            + integer(5, mode),
        )
        tag, data = p.until(4)
        assert first(data, 1) == 3, (tag, data)
        p.pump(0.1)
        assert position(p) == before
    # No elapsed-time/speed field exists; unknown fields cannot increase distance.
    p.seq += 1
    p.send(
        9,
        integer(1, p.session)
        + integer(2, p.seq)
        + real(3, 0)
        + real(4, -1)
        + integer(5, 0)
        + real(99, 10000),
    )
    while first(p.entities[p.id], 6) < p.seq:
        p.until(10)
    assert abs(position(p)[2] - before[2] + 0.075) < 2e-5
    q.pump(0.1)
    print(
        "PASS invalid mode/vector/NaN, stale sequence/session and forged speed rejection",
        flush=True,
    )
    j = connect("jitter")
    j.select(j.create("Jitter"))
    seen = jittered_walk(j)
    j.logout()
    print(
        "PASS jittered client schedule: 200 sends 0-20 ms late, 10 ms before the drain,",
        "none refused; each of",
        seen,
        "views at the start plus every acknowledged input, at most one a tick (D-207)",
        flush=True,
    )
    # Move toward the thin wall at x=2, at a Z within its span.
    for _ in range(101):
        step(p, 0, 1, 0)
    for _ in range(30):
        step(p, 1, 0, 1)
    assert position(p)[0] <= 1.80001, position(p)
    q.pump(0.1)
    old_session = p.session
    saved = position(p)
    p.logout()
    p = connect("alpha")
    p.select(character)
    assert (
        p.session > old_session
        and max(abs(a - b) for a, b in zip(saved, position(p))) < 1e-6
    )
    print(
        "PASS authoritative thin wall and durable reconnect position/session",
        flush=True,
    )
    p.logout()
    q.logout()
    if os.environ.get("N3E_GRAPHICAL") == "1":
        for i in range(2):
            peer = connect("graphical" + str(i))
            peer.create("Graphics" + str(i))
            peer.s.close()
        for i in range(2):
            log = B / f"movement-client-{i}.log"
            f = log.open("w")
            handles.append(f)
            clientenv = {
                **os.environ,
                "N3E_TEST_ACCOUNT": "graphical" + str(i),
                "N3E_TEST_PASSWORD": password,
            }
            # Render at different rates; both network workers still use fixed 50ms input.
            clientenv["N3E_TEST_FRAME_MS"] = "33" if i == 0 else "7"
            client = subprocess.Popen(
                [
                    "build/client/n3e-test-client",
                    str(package),
                    "--connect",
                    f"localhost:{port}",
                    "--ca",
                    "deploy/local/ca.pem",
                    "--auto-login",
                    (
                        "--camera-smoke"
                        if camera
                        else "--controls-smoke" if controls else "--movement-smoke"
                    ),
                    "13",
                    "--capture",
                    str(B / f"movement-client-{i}.ppm"),
                ],
                env=clientenv,
                stdout=f,
                stderr=subprocess.STDOUT,
            )
            clients.append(client)
            # Keyboard/focus replay owns one real window at a time.
            if controls:
                assert client.wait(timeout=30) == 0, log.read_text()
        for c in clients:
            assert c.wait(timeout=30) == 0
        for f in handles:
            f.flush()
        for i in range(2):
            log = (B / f"movement-client-{i}.log").read_text()
            if controls:
                assert re.findall(r"CONTROLS stage=(\d+)", log) == [
                    str(i) for i in range(23 if camera else 8)
                ], log
                continue
            stages = re.findall(r"MOVEMENT stage=([\w-]+) z=([-\d.]+) session=(\d+)", log)
            # PQ-010: Esc (cancel) pressed during E's run; the auto distance
            # below proves it kept running.
            assert re.search(r"MOVEMENT cancel z=", log), log
            assert [x[0] for x in stages] == [
                "walk",
                "run",
                "backward",
                "stop",
                "auto",
                "auto-stop",
                "reconnect",
            ], log
            z = [float(x[1]) for x in stages]
            assert (
                -3.5 < z[0] < -2 and 7 < z[0] - z[1] < 10 and 2 < z[2] - z[1] < 3.5
            ), z
            assert abs(z[3] - z[2]) < 0.2, z
            # E (PQ-009): two seconds of continuous forward running with no
            # movement key held, then a second E stops it: under 1 m in the next second
            # (a few ticks of latency), where running on would cover 4.5 m.
            assert 7 < z[3] - z[4] < 10 and abs(z[5] - z[4]) < 1.0, z
            assert abs(z[6] - z[5]) < 0.01, z
            assert int(stages[6][2]) > int(stages[0][2]), stages
            assert "WORLD tick=" in log
            if "player-backward.bin" in manifest.get("presentation", {}):
                poses = re.findall(
                    r"POSE state=(\d+) tick=\d+ heading=([-\d.e+]+)", log
                )
                assert {0, 1, 4, 5} <= {int(s) for s, h in poses}, poses
                assert all(
                    abs(float(h)) < 0.001 for s, h in poses if int(s) in [1, 4, 5]
                ), poses
        print(
            "PASS two real graphical clients at different frame rates: "
            + (
                "camera UI/capture/drag/wheel/chat/Escape, obstruction/recovery and navigation, 23 stages and captures"
                if camera
                else (
                    "tank turn/forward/backward, independent camera yaw, held cursor repick/release, focus cancellation, captures"
                    if controls
                    else "walk/run/backward/stop, run toggle, E continuous move (Esc keeps it) and stop, F12 reconnect, captures"
                )
            ),
            flush=True,
        )
    else:
        print("UNVERIFIED: graphical gate; rerun with N3E_GRAPHICAL=1", flush=True)
finally:
    for c in clients:
        if c.poll() is None:
            c.terminate()
            c.wait(timeout=5)
    for f in handles:
        f.close()
    # PQ-128: every service's log, before the stack is removed.
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    dc("down", "-v", "--remove-orphans")
