"""KO-12 original fixture and two-peer lifecycle checks for demo_session."""

import json
import math
from pathlib import Path
import shutil
import sys
import time
from world_peer import first, blob, integer
from isolation import once_per_run


@once_per_run
def prepare():
    sys.path.insert(0, str(Path("tools/assetc").resolve()))
    import main

    root = Path("build/ko-12/source")
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree("games/demo", root, dirs_exist_ok=True)
    manifest = json.loads((root / "package.json").read_text())
    # The demo's 32m cells cover the whole +/-24m zone. Narrow only the
    # subscription grid to exercise leave/reentry without changing life/rewards.
    manifest["gameplay"]["interest_cell"] = 4
    (root / "package.json").write_text(json.dumps(manifest))
    package = Path("build/ko-12/package")
    main.cook(root, package)
    return package.resolve()


def audit(a, b, connect):
    bid = b.characters[0][0]
    # Selected connections cannot switch account or character or create again.
    for tag, data in [
        (5, blob(1, "companion") + blob(2, "irrelevant")),
        (8, integer(1, bid)),
        (7, blob(1, "Intruder")),
    ]:
        a.send(tag, data)
        assert first(a.until(4)[1], 1) == 5
    a.move(0, 0, session=a.session + 1)
    assert first(a.until(4)[1], 1) == 3
    a.send(11, blob(1, "near chat") + integer(2, b.id))
    chat = b.until(11)[1]
    assert first(chat, 1) == b"near chat" and first(chat, 2) == a.id
    a.until(11)
    a.send(11, blob(1, "too soon"))
    assert first(a.until(4)[1], 1) == 4

    def travel(goal):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            a.pump(0.01)
            b.pump(0.01)
            e = b.entities[b.id]
            dx, dz = goal[0] - first(e, 3), goal[1] - first(e, 5)
            distance = math.hypot(dx, dz)
            if distance < 0.25:
                b.move(0, 0)
                a.pump(0.2)
                b.pump(0.2)
                return
            b.move(dx / distance, dz / distance, mode=1)
        raise AssertionError("visibility travel timeout")

    travel((0, 9))
    assert a.id not in b.entities and b.id not in a.entities
    a.send(11, blob(1, "out of range"))
    assert first(a.until(11)[1], 1) == b"out of range"
    # Read all observer frames for a bounded interval: no distant chat delivery.
    end = time.monotonic() + 0.4
    while time.monotonic() < end:
        tag, _ = b.receive()
        assert tag != 11
    travel((-0.5, -0.5))
    assert a.id in b.entities and b.id in a.entities
    stopped = (first(b.entities[b.id], 3), first(b.entities[b.id], 5))
    a.pump(0.3)
    b.pump(0.3)
    assert stopped == (first(b.entities[b.id], 3), first(b.entities[b.id], 5))
    old_id, old_session = a.id, a.session
    a.logout()
    b.pump(0.2)
    assert old_id not in b.entities
    a = connect("explorer")
    assert a.id != old_id and a.session > old_session
    a.move(0, 0, session=old_session)
    assert first(a.until(4)[1], 1) == 3
    b.pump(0.2)
    assert a.id in b.entities and old_id not in b.entities
    print(
        "PASS KO-12 selected identity rejection, stale generation, local chat/rate/isolation, remote start/stop, visibility reentry, logout/reconnect baseline",
        flush=True,
    )
    return a
