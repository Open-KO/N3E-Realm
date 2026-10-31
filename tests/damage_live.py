"""Isolated KO-03 two-peer authority and optional real graphical input replay."""

import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from world_peer import Peer as BasePeer, first, integer, blob
import timescale
from isolation import DISPOSABLE_COMPOSE, container_logs

B = Path("build/ko-04")
B.mkdir(parents=True, exist_ok=True)
package = Path(os.environ.get("N3E_DAMAGE_PACKAGE", "build/packages/damage")).resolve()
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
content = (package / "release.sha256").read_text().strip()
project = "n3e-ko04-" + uuid.uuid4().hex[:10]
realm = "test-" + project  # what a scaled run needs (tests/timescale.py)
env = {
    **os.environ,
    "N3E_PORT": "0",
    "N3E_REALM": realm,
    "N3E_PACKAGE_PATH": str(package),
    "N3E_UID": str(os.getuid()),
    "N3E_GID": str(os.getgid()),
    **timescale.server_env(realm),
}
override = B / (project + ".yaml")
base = ["docker", "compose", *DISPOSABLE_COMPOSE, *timescale.compose_override(override), "-p", project]
password = "test-only-" + uuid.uuid4().hex
peers = []


class Peer(BasePeer):
    def receive(self):
        result = super().receive()
        if result[0] == 16:
            self.last_result = result[1]
        return result


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
    timescale.confirm_log(dc("logs", "--no-color", "server"))
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    for name in ["alpha", "beta"]:
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
    target = npc(p)
    assert p.action(target) == "out_of_range"
    assert p.action(target, session=p.session + 1) == "stale_session"
    assert p.action(target, action="invalid:attack") == "unknown_action"
    assert p.action(q.id) == "stale_target"
    approach(p, target)
    outcomes = set()
    incoming = set()
    damages = set()
    kills = 0
    for attempt in range(80):
        if target not in p.entities or not health(p, target):
            kills += 1
            # Acknowledged reward is durable before reconnect.
            p.pump(0.3)
            target = npc(p)
            approach(p, target)
        before = health(p, target)
        status = p.action(target)
        assert status in ("hit", "miss", "cooldown"), status
        if status == "cooldown":
            p.pump(timescale.scaled(0.15))
            continue
        amount = first(p.last_result, 4)
        outcomes.add(status)
        damages.add(amount)
        assert (21 <= amount <= 28) if status == "hit" else amount == 0
        accepted = p.action_seq
        assert p.action(target, seq=accepted) == "stale_action"
        assert p.action(target, seq=accepted + 1) == (
            "target_dead" if amount >= before else "cooldown"
        )
        # Waits in ticks (3, 2, 16, 2 at 50 ms): about one 20-tick cooldown per attempt.
        p.pump(timescale.scaled(0.15))
        q.pump(timescale.scaled(0.1))
        assert health(p, target) == max(0, before - amount)
        assert health(q, target) == health(p, target)
        assert first(p.entities[p.id], 14) == status.encode()
        assert first(p.entities[p.id], 15) == amount
        for e in p.entities.values():
            if first(e, 9) and first(e, 10):
                result = first(e, 14)
                incoming.add(result)
                damage = first(e, 15)
                assert 11 <= damage <= 21 if result == b"hit" else damage == 0
        p.pump(timescale.scaled(0.8))
        q.pump(timescale.scaled(0.1))
        if kills and outcomes == {"hit", "miss"} and incoming == {b"hit", b"miss"}:
            break
    assert outcomes == {"hit", "miss"} and incoming == {b"hit", b"miss"}, (
        outcomes,
        incoming,
    )
    assert kills >= 1
    rows = dc(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "n3e",
        "-d",
        "n3e",
        "-Atc",
        f"SELECT count(*) FROM reward_operations WHERE character_id={character}",
    )
    assert int(rows) >= 1
    old_session = p.session
    old_id = p.id
    p.logout()
    p = connect("alpha")
    p.select(character)
    assert p.session > old_session and p.id != old_id
    assert p.action(target, session=old_session) == "stale_session"
    print(
        "PASS actual two-peer hit/miss, replicated NPC outcomes, duplicate/cooldown/session/range guards, death/durable reward/reconnect",
        flush=True,
    )
    print(
        "observed damage values", sorted(damages), "attempts", attempt + 1, flush=True
    )
finally:
    for p in peers:
        p.s.close()
    # PQ-128: every service's log, before the stack is removed.
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    (B / f"{package.name}-server.log").write_text(dc("logs", "--no-color", "server"))
    dc("down", "-v", "--remove-orphans")
    override.unlink(missing_ok=True)
