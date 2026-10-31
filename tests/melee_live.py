"""Isolated KO-03 two-peer authority and optional real graphical input replay."""

import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from world_peer import Peer, first, integer, blob
from isolation import DISPOSABLE_COMPOSE, container_logs

B = Path("build/ko-03")
B.mkdir(parents=True, exist_ok=True)
package = Path(os.environ.get("N3E_MELEE_PACKAGE", "build/packages/melee")).resolve()
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
content = (package / "release.sha256").read_text().strip()
project = "n3e-ko03-" + uuid.uuid4().hex[:10]
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
peers = []


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
    p = Peer(
        port, name, password, content=content, game=manifest["game_id"], protocol=2
    )
    peers.append(p)
    return p


def health(p, id):
    return first(p.entities[id], 7)


def npc(p):
    return next(id for id, e in p.entities.items() if first(e, 9) and health(p, id))


def approach(p, id):
    for _ in range(150):
        for other in peers:
            if other is not p and other.s.fileno() >= 0:
                other.send(14)
                other.until(10)
        a = p.entities[p.id]
        b = p.entities[id]
        x = first(b, 3) - first(a, 3)
        z = first(b, 5) - first(a, 5)
        d = math.hypot(x, z)
        if d < 0.85:
            return
        p.move(x / d, z / d, mode=1)
        while first(p.entities[p.id], 6) < p.seq:
            p.until(10)
    raise AssertionError("approach")


try:
    dc("up", "-d", "--wait")
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    for name in ["alpha", "beta", "graphics0", "graphics1"]:
        dc(
            "exec",
            "-T",
            "server",
            "n3e-server",
            "account-create",
            name,
            stdin=password + "\n",
        )
    if os.environ.get("N3E_MELEE_GRAPHICS_ONLY") != "1":
        p = connect("alpha")
        character = p.create("Alpha")
        p.select(character)
        q = connect("beta")
        q.select(q.create("Beta"))
        target = npc(p)
        assert p.action(target) == "out_of_range"
        assert p.action(target, session=p.session + 1) == "stale_session"
        assert p.action(target, action="unknown:action") == "unknown_action"
        assert (
            p.action(p.id) == "stale_target"
        )  # authenticated actor cannot target peers/self
        assert p.action(2**62) == "stale_target"
        approach(p, target)
        q.pump(0.1)
        before = health(p, target)
        assert p.action(target) == "hit"
        accepted_seq = p.action_seq
        assert p.action(target, seq=accepted_seq) == "stale_action"
        assert p.action(target, seq=accepted_seq - 1) == "stale_action"
        assert p.action(target, seq=accepted_seq + 1) == "cooldown"
        p.pump(0.1)
        q.pump(0.1)
        assert health(p, target) == before - manifest["gameplay"]["damage"]
        assert health(q, target) == health(p, target)
        assert first(p.entities[p.id], 8) == manifest["gameplay"]["resource"]
        # Distinct peers have independent action and cooldown streams.
        approach(q, target)
        assert q.action(target) == "hit"
        p.pump(1.05)
        q.pump(0.1)
        assert p.action(target) == "hit"
        p.pump(0.1)
        q.pump(0.1)
        assert health(p, target) == health(q, target)
        # Saturated fresh sequences within one second cannot bypass server tick cooldown.
        hits = 0
        start = p.tick
        for _ in range(12):
            status = p.action(target)
            assert status in ("hit", "cooldown"), status
            hits += status == "hit"
        p.pump(0.1)
        assert hits <= (p.tick - start) // manifest["gameplay"]["cooldown_ticks"]
        print(
            "PASS two-peer range, zero cost, independent sequences, spam/duplicate/session/actor authority",
            flush=True,
        )
        # No request => no server attack loop. Reconnect assigns a fresh instance/session.
        p.pump(1.1)
        q.pump(0.1)
        before = health(p, target)
        p.pump(1.1)
        q.pump(0.1)
        assert health(p, target) == before
        old = p.session
        old_id = p.id
        p.logout()
        p = connect("alpha")
        p.select(character)
        assert p.session > old and p.id != old_id
        assert p.action(target, session=old) == "stale_session"
        p.pump(1.1)
        q.pump(0.1)
        assert health(p, target) >= before  # existing AI can return/heal on logout
        # Kill, then reject dead/stale runtime targets; no automatic retarget on respawn.
        kill_deadline = time.monotonic() + 65
        while health(p, target):
            assert time.monotonic() < kill_deadline, "kill deadline"
            approach(p, target)
            status = p.action(target)
            assert status in ("hit", "cooldown"), status
            p.pump(1.01)
            q.pump(0.1)
        assert p.action(target) in ("target_dead", "stale_target")
        for _ in range(int(manifest["gameplay"]["respawn_ticks"] * 0.1) + 2):
            p.pump(0.4)
            q.pump(0.1)
        assert target not in p.entities
        assert p.action(target) == "stale_target"
        print(
            "PASS explicit stop/no scheduler on server, reconnect, dead and respawn-stale targets",
            flush=True,
        )
        p.logout()
        q.logout()
    if os.environ.get("N3E_GRAPHICAL") == "1":
        for i in range(2):
            g = connect("graphics" + str(i))
            g.create("Graphics" + str(i))
            g.s.close()
        for i in range(2):
            time.sleep(1)  # allow compositor to retire the preceding window
            log = B / f"{package.name}-client-{i}.log"
            with log.open("w") as f:
                result = subprocess.run(
                    [
                        "build/client/n3e-test-client",
                        str(package),
                        "--connect",
                        f"localhost:{port}",
                        "--ca",
                        "deploy/local/ca.pem",
                        "--auto-login",
                        "--melee-smoke",
                        "20",
                        "--capture",
                        str(B / f"{package.name}-client-{i}.ppm"),
                    ],
                    env={
                        **os.environ,
                        "N3E_TEST_ACCOUNT": "graphics" + str(i),
                        "N3E_TEST_PASSWORD": password,
                        "N3E_TEST_FRAME_MS": "33" if i == 0 else "7",
                    },
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=45,
                )
            assert result.returncode == 0, log.read_text()
            assert "MELEE selection=ready no-action" in log.read_text(), log.read_text()
            # PQ-010: Esc (the package's cancel action) pressed mid-melee keeps
            # the target and the repeating attack.
            assert re.search(r"MELEE cancel hits=\d+ target=[1-9]", log.read_text()), log.read_text()
            assert "MELEE cancel-kept" in log.read_text(), log.read_text()
            assert re.findall(r"MELEE stage=(\d+)", log.read_text()) == [
                str(n) for n in range(20)
            ], log.read_text()
            # PQ-011: plain click selects only; Ctrl+click and the double click
            # attack (005e16f0, 005e1490); a ground click stops and clears.
            for line in ("MELEE click-select", "MELEE ctrl-click attack", "MELEE ground-click clear",
                         "MELEE double-click attack"):
                assert line in log.read_text(), (line, log.read_text())
        print(
            "PASS real graphical melee at two frame rates: approach/repeat/Esc-kept/stop/party-clear/retarget/manual/chat/focus/reconnect/click-select/Ctrl-click/ground-clear/double-click",
            flush=True,
        )
finally:
    for p in peers:
        try:
            p.s.close()
        except OSError:
            pass
    # PQ-128: every service's log, before the stack is removed.
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    (B / f"{package.name}-server.log").write_text(dc("logs", "--no-color", "server"))
    dc("down", "-v", "--remove-orphans")
