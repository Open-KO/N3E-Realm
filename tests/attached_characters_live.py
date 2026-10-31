"""PQ-328: attached characters on equipped appearance keys (N3AT), live.

The rule is the 2233 client's CPlayerWing (a 2233/2145 addition; KO 1298 has
none): two attached characters per player, a slot each, placed on a player
joint every tick, a clip picked from the player's state, and one pulse timer
per player that each attached slot advances (0056a710, 00569590; slot 0 drawn
only with [Effect] Wing, 00568f30). Evidence:
docs/implementation/evidence/pq-328-cospre-attachments-2233.md.

The package is the PQ-272 fixture (tests/npc_scale_live.py) with two new
equipment slots, "Wing" and "Fairy", two items that fit only there (each a
starting item: the operator grants them through package data, and nothing is
bought), their appearance keys 2 and 3, and an original synthetic N3AT table:
a grey wing quad on the player's joint 1 in group 0, optional, every index lit
with the white pulse at 2x (KO's column 3 > 0 rule), and a fairy in group 1 whose
first part alone is lit, at 2x with no emissive (KO's column 3 = 0 rule, its
+0x11e left set), on a clock each attachment advances (KO's shared timer).

Both readers must accept the package and refuse malformed tables. Against a
native server on a disposable Postgres and Redis the server must refuse the
wing in a hand slot and the blade in the wing slot (it alone decides what is
worn where), and two accounts equip the wing over the wire. With
N3E_GRAPHICAL=1 the real test client logs in as the first account while the
second stands 3 m ahead: it must draw the wing on both (ATTACHMENT for itself
and for the other player), on the wearer's joint (the centre of the wing's
vertices as drawn is the wearer's position plus the joint's offset plus the
wing's own centre above the joint, also once the other player has walked
aside, with the walk clip while it walks), its sampled intensities must
follow the pulse on each wearer's clock, and once the other player also wears
the fairy that player's clock must run twice as fast as the local one. It
captures at 7.5 s (the pulse held near 1) and 10.75 s (0) of the local wearer's
clock, as does a second client with Option.ini [Effect] Wing=0, which must draw
no wing and keep the clock. Pixel checks, inside the screen box the client
reports for each player's wing at the peak: at least half the box's pixels
differ (brighter or darker) from the option-off capture of the same clock
(fails without the attachment drawn), and at least half are brighter at the
peak than at the trough (fails without the pulse). They do not check that the
wings are the only regions that change.
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
import appearance_effects_live as effects_live  # noqa: E402
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq328"
# Seconds of the local wearer's clock in all: about 2 into the second cycle
# (the pulse kept near 1) and about 5.25 (0).
PEAK, TROUGH = 7.5, 10.75
AHEAD = effects_live.AHEAD
ASIDE = (AHEAD[0] + 3.0, AHEAD[1])
WING, FAIRY = "demo:item/wing", "demo:item/fairy"
CLOCK = dict(per_attachment=True, rise=1.0, hold=3.0, fall=5.0, period=5.5)


def detail():
    """The fixture's render detail with three appearances: the blade quad of
    tests/equipment_glow_live.py and, for the wing and fairy keys, one small
    triangle inside the body (N3D2 needs a mesh per key; the attached
    character is the N3AT model, not this)."""
    import render_detail

    def body(slot):
        return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]],
                [0, 1, 2])

    def quad(slot):
        corners = [(.3, .2), (.9, .2), (.9, .8), (.3, .8)]
        vertices = [([x, y, 0], [0, -1, 0], [x, y], [0] * 4, [1, 0, 0, 0], slot) for x, y in corners]
        return vertices, [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]

    def speck(slot):
        return ([([x, .01, z], [0, 1, 0], [0, 0], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (.01, 0), (0, .01)]],
                [0, 1, 2])
    white, grey = [(16, 16, bytes([255]) * 1024)], [(16, 16, bytes([90, 90, 90, 255]) * 256)]
    return render_detail.serialize(
        view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=1,
        textures=[white, white, grey], radius=1, levels=[body(1)] * 4,
        appearances=[([1], [quad(2)] * 4), ([], [speck(1)] * 4), ([], [speck(1)] * 4)])


def policy(root):
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import attachment_fixture as fixture
    _, first = fixture.indices("fairy")
    entry = dict(joint=1, scale=1.0, modulate=2)
    return dict(clock=dict(CLOCK), color=[1.0, 1.0, 1.0], entries=[
        dict(item=WING, slot=4, group=0, optional=True, emissive=True, lit="all",
             clips=fixture.write(root, "wing", "wing"), **entry),
        dict(item=FAIRY, slot=5, group=1, optional=False, emissive=False, lit=first,
             clips=fixture.write(root, "fairy", "fairy"), **entry),
    ])


def source(root):
    """Adds the two slots, items, keys and the attachment table to the copied
    fixture source at `root`."""
    m = json.loads((root / "package.json").read_text())
    assert m["appearance"] == [{"item": "demo:item/blade", "slot": 0}], m["appearance"]
    gear = m["equipment"]
    assert len(gear["slots"]) == 4, gear["slots"]
    gear["slots"] += ["Wing", "Fairy"]
    for item, slot in ((WING, 4), (FAIRY, 5)):
        gear["items"].append(dict(id=item, slots=[slot], blocks=[], race=0, title=0, attributes=[0] * 5,
                                  swappable=False))
        m["inventory"]["items"].append(dict(id=item, label=item.split("/")[1].title(), stack_limit=1, durability=0,
                                            starting=1))
        # Offered by no shop, so nothing buys it; weightless, no wear, no stats.
        m["commerce"]["items"].append(dict(id=item, weight=0, price=1, sell_divisor=10000))
        # No wear and no stats: cosmetic only in this fixture.
        m["wear"]["items"].append(dict(id=item, attack_slots=[], defense_slots=[]))
        m["stats"]["items"].append(dict(id=item, category="demo:weapon/none", attack=0, defense=0, health=0,
                                        resource=0, accuracy=0, evasion=0, attributes=[0] * 5))
    m["appearance"] += [dict(item=WING, slot=4), dict(item=FAIRY, slot=5)]
    m["attachments"] = policy(root)
    (root / "detail.bin").write_bytes(detail())
    (root / "package.json").write_text(json.dumps(m))
    return m


@once_per_run
def prepare():
    """Cook the PQ-272 package with the two cospre slots and the N3AT table;
    returns its directory."""
    from npc_scale_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(base().parent / "source", root)
    source(root)
    main.cook(root, out)
    return out.resolve()


def repack(package, out, files):
    """A copy of `package` with `files` ({name: bytes, or None to delete})
    replaced, rehashed into release.bin."""
    import hashlib
    from common import string, u
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(package, out)
    for name, data in files.items():
        if data is None:
            (out / name).unlink()
        else:
            (out / name).write_bytes(data)
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    names = sorted(p.name for p in out.iterdir() if p.name not in ("release.bin", "release.sha256"))
    index = b"N3R1" + u(1) + u(m["engine_version"]) + u(m["protocol_version"]) + string(m["game_id"]) \
        + string(m["package_version"]) + u(len(names))
    for name in names:
        data = (out / name).read_bytes()
        index += string(name) + u(len(data)) + hashlib.sha256(data).digest()
    (out / "release.bin").write_bytes(index)
    (out / "release.sha256").write_text(hashlib.sha256(index).hexdigest() + "\n")


ENTRY = 7 * 4 + 4 * 20  # key .. lit, then four clip records
HEADER = 4 * 10  # magic, flags, timing, colour, count


def check_readers(package):
    """Both readers accept the package; each refuses the malformed tables it
    can see (the client also checks the joint and the lit count against the
    skeleton and mesh). Returns the number of refused packages."""
    npc_looks_live.check_readers(package)
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    table = (package / "attachments.bin").read_bytes()
    assert table[:4] == b"N3AT" and len(table) == HEADER + 2 * ENTRY, len(table)

    def field(entry, offset, value, fmt="<I"):
        at = HEADER + entry * ENTRY + offset
        return table[:at] + struct.pack(fmt, value) + table[at + 4:]
    both, client_only = "both", "client"
    cases = [
        ("key past the appearance", field(0, 0, 4), "attachment appearance key", both),
        ("duplicate key", field(1, 0, 2), "attachment appearance key", both),
        ("joint the skeleton lacks", field(0, 4, 2), "attachment joint", client_only),
        ("joint past 63", field(0, 4, 64), "attachment entry bounds", both),
        ("scale 0", field(0, 8, 0.0, "<f"), "attachment entry bounds", both),
        ("group 16", field(0, 12, 16), "attachment entry bounds", both),
        # Bit 2 is a skeletal plug since PQ-317 (tests/skeletal_plugs_live.py).
        ("unknown flag", field(0, 16, 8), "attachment entry bounds", both),
        ("modulate 3", field(0, 20, 3.0, "<f"), "attachment entry bounds", both),
        ("lit not whole triangles", field(1, 24, 13), "attachment entry bounds", both),
        ("lit past the mesh", field(1, 24, 999), "attachment lit indices", client_only),
        ("colour 1.5", table[:24] + struct.pack("<f", 1.5) + table[28:], "attachment colour", both),
        ("clock out of order", table[:8] + struct.pack("<f", 4.0) + table[12:], "attachment clock", both),
        ("trailing byte", table + b"\0", "cooked trailing bytes", both),
    ]
    bad = OUT / "hostile"
    refused = 0
    for name, data, reason, who in cases:
        repack(package, bad, {"attachments.bin": data})
        p = subprocess.run(["build/client/n3e-asset-check", str(bad)], cwd=ROOT, capture_output=True, text=True)
        assert p.returncode != 0 and reason in p.stdout + p.stderr, (name, p.stdout[-400:], p.stderr[-400:])
        s = subprocess.run(["target/debug/n3e-server", "--check-content"], cwd=ROOT,
                           env={**os.environ, "N3E_PACKAGE": str(bad)}, capture_output=True, text=True)
        # The server cannot see the skeleton or the mesh; it refuses the rest.
        assert (s.returncode != 0) == (who == both), (name, s.returncode, s.stdout[-300:], s.stderr[-300:])
        refused += 1
    # A model missing, or a model the table does not list: both refuse.
    for name, files in [("missing model", {"attachment-1.bin": None}),
                        ("unlisted model", {"attachment-2.bin": (package / "attachment-0.bin").read_bytes()})]:
        repack(package, bad, files)
        for cmd in (["build/client/n3e-asset-check", str(bad)], ["target/debug/n3e-server", "--check-content"]):
            p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(bad)}, capture_output=True,
                               text=True)
            assert p.returncode != 0, (name, cmd, p.stdout[-300:], p.stderr[-300:])
        refused += 1
    shutil.rmtree(bad)
    return refused


def expected(t):
    """The intensity at clock value t (00569590): t up to 1 s, then kept (the
    last rising value, within a frame of 1) to 3 s, falling to 0 at 5 s, then
    kept (within a frame of 0) until the clock restarts past 5.5 s."""
    return t if t <= 1 else 1 if t <= 3 else max(0., 1 - (t - 3) * .5) if t <= 5 else 0


def share(a, b, box, levels=40, either=False):
    """The fraction of the pixels in `box` at least `levels` brighter, by
    channel sum / 3, in capture `a` than in `b` (`either`: brighter or
    darker)."""
    width, _, pa = npc_looks_live.read_ppm(a)
    _, _, pb = npc_looks_live.read_ppm(b)
    x0, y0, x1, y1 = box
    hits = total = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            i = (y * width + x) * 3
            total += 1
            d = sum(pa[i:i + 3]) - sum(pb[i:i + 3])
            hits += (abs(d) if either else d) >= 3 * levels
    return hits / max(1, total)


def judge(on_peak, on_trough, off_peak, boxes):
    """`boxes`: the screen box the client drew each wing in at the peak, the
    local one's first. The wings: in each box at least half of the pixels
    differ at the peak from the option-off capture of the same clock (fails
    without the attachment, whatever its shade). The
    pulse: in each box at least half are brighter at the peak than at the
    trough (fails without it). Returns (failures, report)."""
    wings = [round(share(on_peak, off_peak, box, either=True), 3) for box in boxes]
    pulse = [round(share(on_peak, on_trough, box), 3) for box in boxes]
    failures = []
    if len(boxes) != 2 or boxes[0] == boxes[1] or min(wings) < .5:
        failures.append(("wings", wings, boxes))
    if min(pulse) < .5:
        failures.append(("pulse", pulse, boxes))
    return failures, dict(wings=wings, pulse=pulse, boxes=boxes)


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, blob, fields, first, integer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq328-" + uuid.uuid4().hex[:10]
    passwords = {account: "test-only-" + uuid.uuid4().hex for account in ("explorer", "companion")}
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

    serial = [0]

    def wait(p, tag, predicate=lambda d: True, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            t, d = p.receive()
            assert t != 4, (t, d)
            if t == tag and predicate(d):
                return d
        raise AssertionError(("timeout", tag))

    def bag(p, op=0, source=0, destination=0, state=None, status=b"committed"):
        time.sleep(.22)  # inside the shared inventory request budget
        if not op:
            p.send(32, b"")
            return fields(first(wait(p, 33, lambda d: first(d, 2) == b"ok"), 3))
        serial[0] += 1
        records = state[6] if op == 6 else state[5]
        p.send(32, integer(1, op) + blob(2, f"pq328-{serial[0]}") + integer(3, first(state, 1)) + integer(4, source)
               + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
        d = wait(p, 33)
        assert first(d, 2) == status, (status, d)
        return fields(first(d, 3))

    def slot_of(state, item):
        found = [i for i, r in enumerate(state[5]) if first(fields(r), 2) == item.encode()]
        assert found, (item, state)
        return found[0]

    def vacant(state):
        return [i for i, r in enumerate(state[5]) if not first(fields(r), 1)][0]

    def keys(p, entity):
        return list(first(p.entities.get(entity, {}), 20, b""))

    def walk(p, x, z):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            p.pump(.05)
            me = p.entities[p.id]
            if first(me, 6) < p.seq:
                continue
            dx, dz = x - first(me, 3), z - first(me, 5)
            d = math.hypot(dx, dz)
            if d < .3:
                p.move(0, 0)
                p.pump(.2)
                return
            p.move(dx / max(1, d), dz / max(1, d), mode=1)
        raise AssertionError(("blocked", x, z, p.entities[p.id]))

    try:
        for suffix, image, port, extra in [
            ("", npc_looks_live.POSTGRES, 5432, ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
                                                 "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
            ("-redis", npc_looks_live.REDIS, 6379, []),
        ]:
            run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{port}", image)
            containers.append(name + suffix)
        pg = wait_postgres(name)
        redis = run("docker", "port", name + "-redis", "6379").split()[0]
        listen, health = free_ports(2)
        env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                   REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM="test-" + name,
                   N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "migrate", env=env)
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        for account, password in passwords.items():
            run(server_binary, "account-create", account, env=env, stdin=password + "\n")
        log = open(out / "server.log", "w")
        server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 30
        while True:
            assert server.poll() is None, (out / "server.log").read_text()[-2000:]
            assert time.monotonic() < deadline, "server never reported ready"
            try:
                if urllib.request.urlopen(f"http://127.0.0.1:{health}/ready", timeout=0.2).status == 200:
                    break
            except OSError:
                time.sleep(0.1)

        def peer(account, new=True):
            p = Peer(listen, account, passwords[account], content=(package / "release.sha256").read_text().strip(),
                     game=manifest["game_id"], protocol=manifest["protocol_version"])
            if new:
                p.create(account.title())
            assert p.select(p.characters[0][0])[0] == 10
            return p
        a = peer("explorer")
        state = bag(a)
        assert len(state[6]) == 6, state[6]  # four hand and ring slots, then Wing and Fairy
        # The server alone decides what may be worn where: the wing does not go
        # in the right hand, the blade does not go in the wing slot, and the
        # refused requests change nothing anyone sees.
        bag(a, 5, slot_of(state, WING), 0, state, status=b"incompatible_slot")
        bag(a, 5, slot_of(state, "demo:item/blade"), 4, state, status=b"incompatible_slot")
        a.pump(.3)
        assert keys(a, a.id) == [], keys(a, a.id)
        state = bag(a, 5, slot_of(state, WING), 4, state)
        wait(a, 10, lambda _: keys(a, a.id) == [2])
        # Durable: a new session reads the committed equipment back.
        a.logout()
        a = peer("explorer", new=False)
        assert first(fields(bag(a)[6][4]), 2) == WING.encode()
        wait(a, 10, lambda _: keys(a, a.id) == [2])
        a.logout()
        b = peer("companion")
        b_state = bag(b)
        b_state = bag(b, 5, slot_of(b_state, WING), 4, b_state)
        wait(b, 10, lambda _: keys(b, b.id) == [2])
        walk(b, *AHEAD)
        print(f"PASS the server refuses the wing in a hand slot and the blade in the wing slot; both accounts "
              f"equip the wing over the wire, carry appearance key 2, and the wing stays equipped across "
              f"sessions; the companion stands at {AHEAD}", flush=True)
        if os.environ.get("N3E_GRAPHICAL") != "1":
            b.logout()
            return

        def client(capture, config, steps=()):
            lines = []
            proc = subprocess.Popen(
                ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                 "deploy/local/ca.pem", "--auto-login", "--world-smoke", "24", "--capture", str(capture)],
                env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": passwords["explorer"],
                     "N3E_TEST_ATTACHMENTS": "1", "N3E_TEST_ATTACHMENT_CAPTURES": f"{PEAK},{TROUGH}",
                     "XDG_CONFIG_HOME": config},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
            reader.start()
            pending = list(steps)
            while proc.poll() is None:
                b.pump(.1)
                if pending and pending[0][0]("".join(lines)):
                    pending.pop(0)[1]()
            reader.join(10)
            text = "".join(lines)
            capture.with_suffix(".log").write_text(text)
            assert proc.returncode == 0, (proc.returncode, text[-1500:])
            assert not pending, ("steps not reached", len(pending), text[-1500:])
            made = re.findall(r"^ATTACHMENT_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$", text, re.M)
            assert [float(t) for t, _ in made] == [PEAK, TROUGH], (made, text[-1500:])
            boxes = {(int(e), int(n)): tuple(int(v) for v in b.split(",")) for e, n, b in re.findall(
                rf"^ATTACHMENT_BOX at={PEAK} entity=(\d+) self=\d entry=(\d+) box=(\S+)$", text, re.M)}
            return text, [Path(p) for _, p in made], boxes

        def samples(text, entity=None):
            out = []
            for m in re.finditer(r"^ATTACHMENT_SAMPLE entity=(\d+) entry=(\d+) t=(\S+) total=(\S+) intensity=(\S+) "
                                 r"clip=(\d) joint=(\S+),(\S+),(\S+) placed=(\S+),(\S+),(\S+) wearer=(\S+),(\S+),(\S+)$",
                                 text, re.M):
                e, entry, t, total, i, clip = int(m[1]), int(m[2]), float(m[3]), float(m[4]), float(m[5]), int(m[6])
                joint, placed = [float(m[k]) for k in (7, 8, 9)], [float(m[k]) for k in (10, 11, 12)]
                wearer = [float(m[k]) for k in (13, 14, 15)]
                if entity is None or e == entity:
                    out.append(dict(entity=e, entry=entry, t=t, total=total, intensity=i, clip=clip, joint=joint,
                                    placed=placed, wearer=wearer, at=m.start()))
            return out
        other = b.id

        def found(*patterns):
            return lambda text: all(re.search(p, text, re.M) for p in patterns)

        def fairy_on():
            nonlocal b_state
            b_state = bag(b, 5, slot_of(b_state, FAIRY), 5, b_state)
            wait(b, 10, lambda _: keys(b, b.id) == [2, 3])

        def aside():
            walk(b, *ASIDE)
        start = r"^ATTACHMENT entity={} self={} key={} entry={} group={} joint=1 vertices=\d+ lit=\d+ modulate=2 emissive={}$"
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            text, shown, boxes = client(out / "wing-on.ppm", config, steps=[
                (found(r"^ATTACHMENT_CAPTURE at=10\.75 "), fairy_on),
                (found(start.format(other, 0, 3, 1, 1, 0)), aside)])
            assert "a 2233/2145 addition (N3AT); optional ones shown" in text, text[:1500]
            mine = re.findall(start.format(r"\d+", 1, 2, 0, 0, 1), text, re.M)
            others = re.findall(start.format(other, 0, 2, 0, 0, 1), text, re.M)
            assert len(mine) == 1 and len(others) == 1, (mine, others, text[-2000:])
            me = samples(text)
            me = [s for s in me if s["entity"] != other]
            them = samples(text, other)
            assert me and them, text[-2000:]
            # The local wearer: one attachment, so its pulse follows one clock.
            assert all(abs(s["intensity"] - expected(s["t"])) < .05 for s in me if s["entry"] == 0), me
            phases = {"rise" if c < 1 else "hold" if c <= 3 else "fall" if c < 5 else "off"
                      for s in me for c in [s["t"]]}
            assert {"rise", "hold", "fall"} <= phases, (phases, me)
            # On the wearer's joint, from the vertices as drawn: the fixture's
            # joint 1 stands 1 above the wearer's root and the wing's centre is
            # (0, 0.5, -0.15) from the joint, both times the player's instance
            # scale h (the joint sample's height). However the joint and the
            # beat turn it, the drawn centre is |(0, 0.5, -0.15)| h = 0.522 h
            # from the joint, and above 1.2 h over the wearer (drawn without the
            # joint it would be about 0.5 h over the wearer's root).
            for s in me + them:
                d = [s["joint"][k] - s["wearer"][k] for k in range(3)]
                assert abs(d[0]) < 1e-3 and abs(d[2]) < 1e-3 and .5 < d[1] < 2, s
                if s["entry"] == 0:
                    w = [s["placed"][k] - s["wearer"][k] for k in range(3)]
                    r = math.dist(s["placed"], s["joint"])
                    assert abs(r - .522 * d[1]) < .02 * d[1] and w[1] > 1.2 * d[1], (r, w, d, s)
            wing = [s for s in them if s["entry"] == 0]
            moved = [s for s in wing if math.hypot(s["wearer"][0] - ASIDE[0], s["wearer"][2] - ASIDE[1]) < .4]
            stood = [s for s in wing if math.hypot(s["wearer"][0] - AHEAD[0], s["wearer"][2] - AHEAD[1]) < .4]
            assert moved and stood, ([s["wearer"] for s in wing])
            clips = [int(c) for c in re.findall(rf"^ATTACHMENT_CLIP entity={other} entry=0 clip=(\d)$", text, re.M)]
            assert 1 in clips and clips[-1] == 0, clips  # walked aside with the walk clip, then stood
            # Both slots advance the one clock: with the wing and the fairy the
            # other player's clock runs about twice as fast as the local one's.
            both = [s for s in wing if s["at"] > text.index(re.search(start.format(other, 0, 3, 1, 1, 0), text,
                                                                        re.M)[0])]
            mine_after = [s for s in me if s["at"] > both[0]["at"]] if both else []
            assert len(both) >= 3 and len(mine_after) >= 3, (both, mine_after)
            rate = (both[-1]["total"] - both[0]["total"]) / (mine_after[-1]["total"] - mine_after[0]["total"])
            assert 1.6 < rate < 2.4, (rate, both, mine_after)
            print(f"PASS the client draws the wing on itself and on the other player, on the wearer's joint (also "
                  f"after the other walked aside, with the walk clip); {len(me)} local samples follow the pulse "
                  f"through {sorted(phases)}; with the wing and the fairy the other player's clock runs {rate:.2f} "
                  f"times as fast as the local one's", flush=True)
        # Back as the captures had it: the fairy off, the companion ahead.
        b_state = bag(b, 6, 5, vacant(b_state), b_state)
        wait(b, 10, lambda _: keys(b, b.id) == [2])
        walk(b, *AHEAD)
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            Path(config, "n3e").mkdir()
            Path(config, "n3e", "Option.ini").write_text("[Effect]\nWing=0\n")
            quiet, hidden, _ = client(out / "wing-off.ppm", config)
            assert "optional ones hidden by Option.ini [Effect] Wing=0" in quiet, quiet[:1500]
            assert "ATTACHMENT entity" not in quiet, quiet[-1500:]
        mine_id = int(re.search(r"^ATTACHMENT entity=(\d+) self=1 key=2 ", text, re.M)[1])
        wing_boxes = [boxes.get((mine_id, 0)), boxes.get((other, 0))]
        assert all(wing_boxes), (boxes, mine_id, other)
        failures, report = judge(shown[0], shown[1], hidden[0], wing_boxes)
        assert not failures, (failures, report)
        print(f"PASS graphical client draws the attached wing on the local and the other player: in the wing "
              f"boxes {report['boxes']} {report['wings']} of the pixels differ at the pulse's peak from "
              f"[Effect] Wing=0 at the same clock, and {report['pulse']} brighter at the peak than at the trough; "
              f"{shown[0]}, {shown[1]}, {hidden[0]}", flush=True)
        b.logout()
    finally:
        if server is not None:
            server.kill()
            server.wait()
        if log is not None:
            log.close()
        for c in containers:
            container_logs({name: "postgres", name + "-redis": "redis"}[c], ["docker", "logs", "--timestamps", c])
        for c in containers:
            subprocess.run(["docker", "rm", "-f", c], capture_output=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    assert (package / "attachments.bin").read_bytes()[:4] == b"N3AT"
    refused = check_readers(package)
    print(f"PASS N3AT package: both readers accept it; {refused} malformed packages are refused", flush=True)
    live(package)
