"""PQ-348: an equipped part drawn with its KO part render state (N3D3), live.

KO 1298 sets an equipped armour part into the character's part vector
(0045cd90 -> CN3Chr 0041b6d0, slot vector +0x180; the load 00438c40 calls the
part's vtable +0xc, 00412180, which reads its material) and the character
render 004196a0 draws every part of that vector, in order, through 00412570:
alpha blending with the material's source and destination factors (render
flag 1), culling off (flag 4), with the device's alpha test (0043ade0:
ALPHATESTENABLE, GREATER, no reference set, so 0). The inventory preview draws
the same character render (00457420 -> 004196a0). 2233's CN3CPart::Render
(0042cf30) sets the same states and then the glow's emissive and modulate for
the same draw. n3e draws it in the world for every player; the preview is
PQ-352's. Evidence: docs/implementation/evidence/pq-348-armour-part-render-states-2145.md.

The package is the PQ-315 one (tests/equipment_glow_live.py: the PQ-272
fixture, a white pulse at 2x on appearance key 1, the blade in the right
hand) with an N3D3 render detail whose key 1 is two sets of four single-sided
quads (one set in the model's x-y plane, one in its y-z plane, so each player
shows one face on whichever way it turns), all one red, at alpha 255, 192, 64
and 0 (bands A to D), with the state KO's 2145 Krowaz parts carry: blend
src_alpha / one_minus_src_alpha, double-sided, alpha reference 0. Its world
slot is opaque black, so the detail shader's second layer adds nothing and the
fixture's sky, one colour, lies behind the quads.

Both readers must accept the package and the client must refuse a malformed
state. Two accounts equip the blade over the wire. With N3E_GRAPHICAL=1 three
clients log in as the first while the second stands 3 m ahead, each capturing
at 7.5 s and 10.75 s of the local player's drawn time: states drawn with the
glow, states drawn with Option.ini [Addition2233] EquipmentGlow=0, and
N3E_TEST_PART_STATES=ignore with the glow off (the key drawn as N3D2 draws
every key: culled, cut at alpha 0.5, no blend). The local player stands still
under N3E_TEST_PART_STATES, so the three clients draw one scene, which the
suite checks first (PQ-356: the world smoke's walk once put the fixture's
placeholder model behind one capture's bands). Each client reports the key's
state and the drawn corners of its quads; each capture is measured at its own
band centres, and the ignored capture's band D (never drawn) is what lies
behind. On each player, with and without the glow, band A must be drawn, bands
B and C must be their alpha times band A's pixel plus one minus it times the
pixel behind, and band D nothing; the ignored draw must leave band C out (below
its 0.5 cut) and cull the quads that face away on one player at least, which
the state draws; the glow must brighten bands A to C, each by its alpha's share,
and leave band D's pixel alone.
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
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
import equipment_glow_live as glow_live  # noqa: E402
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq348"
PEAK, TROUGH = glow_live.PEAK, glow_live.TROUGH
RED = (200, 40, 40)
BANDS = (255, 192, 64, 0)  # A, B, C, D
# KO's 2145 Krowaz parts: blend (1) and double-sided (2), factors src_alpha (4)
# and one_minus_src_alpha (5), reference 0 (tools/assetc/ko_appearance.part_state).
STATE = (3, 0.0, 4, 5)
TOLERANCE = 14  # levels, per channel, between a measured and a predicted pixel


def texture():
    """16 x 16: columns 4k..4k+3 of the top eight rows red at BANDS[k]; the rest red, opaque."""
    pixels = bytearray()
    for y in range(16):
        for x in range(16):
            pixels += bytes((*RED, BANDS[x // 4] if y < 8 else 255))
    return [(16, 16, bytes(pixels))]


def quads(slot):
    """Two sets of four upright quads beside the body, one winding, band k's
    texture coordinates inside band k's texels: set 0 in the model's x-y plane
    (x .3 + .3k .. .6 + .3k), set 1 in its y-z plane (x -.3, z the same), so
    each player shows one set face on to the camera, whichever way it turns."""
    vertices, indices = [], []
    for plane in range(2):
        for k in range(4):
            a0, a1 = .3 + .3 * k, .6 + .3 * k
            u0, u1, v0, v1 = (4 * k + .5) / 16, (4 * k + 3.5) / 16, .5 / 16, 7.5 / 16
            base = len(vertices)
            for (a, y), uv in zip([(a0, .2), (a1, .2), (a1, .8), (a0, .8)], [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]):
                position, normal = ([a, y, 0], [0, -1, 0]) if plane == 0 else ([-.3, y, a], [0, -1, 0])
                vertices.append((position, normal, list(uv), [0] * 4, [1, 0, 0, 0], slot))
            indices += [base, base + 2, base + 1, base, base + 3, base + 2]
    return vertices, indices


def detail(states=(STATE,)):
    """The fixture's render detail with a black opaque world slot (the detail
    shader adds it as the second layer, so the part keeps its own colour) and
    key 1 as the four band quads; N3D3 with `states`, N3D2 with None."""
    import render_detail

    def body(slot):
        return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]],
                [0, 1, 2])
    black, white = [(16, 16, bytes([0, 0, 0, 255]) * 256)], [(16, 16, bytes([255]) * 1024)]
    return render_detail.serialize(
        view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=1,
        textures=[black, white, texture()], radius=1, levels=[body(1)] * 4, appearances=[([1], [quads(2)] * 4)],
        states=None if states is None else list(states))


@once_per_run
def prepare():
    """Cook the PQ-315 package with the N3D3 render detail; returns its directory."""
    from npc_scale_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    assert m["appearance"] == [{"item": "demo:item/blade", "slot": 0}], m["appearance"]
    (root / "effects.bin").write_bytes(glow_live.n3e3([glow_live.glow()], len(m["appearance"])))
    (root / "detail.bin").write_bytes(detail())
    main.cook(root, out)
    return out.resolve()


def repack(package, out, detail_bytes):
    """A copy of `package` whose render-detail.bin is `detail_bytes`, rehashed
    into release.bin (appearance_effects_live.repack's index)."""
    import hashlib
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(package, out)
    (out / "render-detail.bin").write_bytes(detail_bytes)
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    names = sorted(p.name for p in out.iterdir() if p.name not in ("release.bin", "release.sha256"))
    index = b"N3R1" + effects_live.u(1, m["engine_version"], m["protocol_version"]) + effects_live.string(m["game_id"]) \
        + effects_live.string(m["package_version"]) + effects_live.u(len(names))
    for name in names:
        data = (out / name).read_bytes()
        index += effects_live.string(name) + effects_live.u(len(data)) + hashlib.sha256(data).digest()
    (out / "release.bin").write_bytes(index)


def check_readers(package):
    """Both readers take the package; the client refuses malformed states."""
    npc_looks_live.check_readers(package)
    good = (package / "render-detail.bin").read_bytes()
    assert good[:4] == b"N3D3", good[:4]
    import struct
    at = len(good) - 16
    cases = [
        ("unlit flag", good[:at] + struct.pack("<IfII", 7, 0, 4, 5)),
        ("unknown flag", good[:at] + struct.pack("<IfII", 11, 0, 4, 5)),
        ("reference 1", good[:at] + struct.pack("<IfII", 3, 1.0, 4, 5)),
        ("reference NaN", good[:at] + struct.pack("<IfII", 3, float("nan"), 4, 5)),
        ("factor 10", good[:at] + struct.pack("<IfII", 3, 0, 10, 5)),
        ("factors without blend", good[:at] + struct.pack("<IfII", 2, 0, 4, 5)),
        ("truncated", good[:-4]),
    ]
    bad = OUT / "hostile"
    for name, data in cases:
        repack(package, bad, data)
        p = subprocess.run(["build/client/n3e-asset-check", str(bad)], cwd=ROOT, capture_output=True, text=True)
        reason = {"reference NaN": "cooked finite bound", "truncated": "truncated cooked data"}.get(name, "appearance render state")
        assert p.returncode != 0 and reason in p.stdout + p.stderr, (
            name, p.stdout[-400:], p.stderr[-400:])
    shutil.rmtree(bad)
    return len(cases)


def corners(text):
    """{(capture second, 'self' or entity id): [band centre (x, y) for bands A-D]}
    from PART_STATE_CORNERS (six drawn corners a band, in draw order), of the
    set whose band A covers the most of the screen (the one face on)."""
    found = {}
    for at, entity, me, key, rest in re.findall(
            r"^PART_STATE_CORNERS at=([0-9.]+) entity=(\d+) self=(\d) key=(\d+) corners=(.*)$", text, re.M):
        points = [tuple(float(v) for v in c.split(",")) for c in rest.split(";")]
        assert int(key) == 1 and len(points) == 48, (key, len(points))

        def area(quad):  # the two triangles' screen area
            return sum(abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
                       for a, b, c in (quad[0:3], quad[3:6]))
        sets = [[points[24 * s + 6 * k:24 * s + 6 * k + 6] for k in range(4)] for s in range(2)]
        best = max(sets, key=lambda bands: area(bands[0]))
        assert area(best[0]) >= 100, (at, entity, [area(b[0]) for b in sets])
        found[float(at), "self" if me == "1" else int(entity)] = [
            (sum(p[0] for p in band) / 6, sum(p[1] for p in band) / 6) for band in best]
    return found


def pixel(capture, at, half=2):
    """The per-channel median of the (2 half + 1)^2 pixels around `at`."""
    w, h, pixels = npc_looks_live.read_ppm(capture)
    x, y = int(round(at[0])), int(round(at[1]))
    assert half <= x < w - half and half <= y < h - half, (capture, at)
    window = [pixels[((y + dy) * w + x + dx) * 3:((y + dy) * w + x + dx) * 3 + 3]
              for dy in range(-half, half + 1) for dx in range(-half, half + 1)]
    return tuple(sorted(p[c] for p in window)[len(window) // 2] for c in range(3))


def blended(alpha, source, behind):
    """src_alpha / one_minus_src_alpha of 8-bit pixels."""
    a = alpha / 255
    return tuple(a * s + (1 - a) * b for s, b in zip(source, behind))


def near(a, b, tolerance=TOLERANCE):
    return max(abs(x - y) for x, y in zip(a, b)) <= tolerance


def judge(states, ignored, at_states, at_ignored):
    """The pixel checks for one player in a capture drawn with the part state
    (`states`, band centres `at_states`) and one of the same clock time with
    the key drawn as N3D2 draws it (`ignored`, `at_ignored`). What lies behind
    the bands is the ignored capture's band D (alpha 0: never drawn); the
    fixture's sky is one colour, so it is the same behind every band. Returns
    (failures, report)."""
    on = [pixel(states, c) for c in at_states]
    off = [pixel(ignored, c) for c in at_ignored]
    behind = off[3]
    failures = []
    if not near(off[2], behind):  # band C (alpha 64) is below N3D2's 0.5 cut
        failures.append(("band C drawn when ignored", off[2], behind))
    if near(on[0], behind, 40):  # band A (alpha 255): the part's own colour
        failures.append(("band A not drawn", on[0], behind))
    for k in (1, 2):
        if not near(on[k], blended(BANDS[k], on[0], behind)):
            failures.append(("band %s blend" % "ABCD"[k], on[k], blended(BANDS[k], on[0], behind)))
    if not near(on[3], behind):
        failures.append(("band D drawn", on[3], behind))
    culled = near(off[0], behind) and near(off[1], behind)  # ignored: the single-sided quads culled
    return failures, dict(on=on, ignored=off, culled=culled)


def glow_live_other(where):
    """The other player's entity id in a corners map."""
    others = {who for _, who in where if who != "self"}
    assert len(others) == 1, sorted(where)
    return others.pop()


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, blob, fields, first, integer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq348-" + uuid.uuid4().hex[:10]
    passwords = {account: "test-only-" + uuid.uuid4().hex for account in ("explorer", "companion")}
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

    def wait(p, tag, predicate=lambda d: True, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            t, d = p.receive()
            assert t != 4, (t, d)
            if t == tag and predicate(d):
                return d
        raise AssertionError(("timeout", tag))

    def equip(p):
        time.sleep(.22)  # inside the shared inventory request budget
        p.send(32, b"")
        state = fields(first(wait(p, 33, lambda d: first(d, 2) == b"ok"), 3))
        assert first(fields(state[5][0]), 2) == b"demo:item/blade", state[5][0]
        time.sleep(.22)
        p.send(32, integer(1, 5) + blob(2, "pq348-" + uuid.uuid4().hex[:8]) + integer(3, first(state, 1))
               + integer(4, 0) + integer(5, 0) + integer(6, first(fields(state[5][0]), 1)))
        d = wait(p, 33)
        assert first(d, 2) == b"committed", d
        wait(p, 10, lambda _: list(first(p.entities.get(p.id, {}), 20, b"")) == [1])

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

        def peer(account):
            p = Peer(listen, account, passwords[account], content=(package / "release.sha256").read_text().strip(),
                     game=manifest["game_id"], protocol=manifest["protocol_version"])
            p.create(account.title())
            assert p.select(p.characters[0][0])[0] == 10
            return p
        a = peer("explorer")
        equip(a)
        a.logout()
        b = peer("companion")
        equip(b)
        walk(b, *glow_live.AHEAD)
        print(f"PASS both accounts equip the blade over the wire and carry appearance key 1, whose N3D3 part "
              f"draws with blend, double-sided and reference 0; the companion stands at {glow_live.AHEAD}", flush=True)
        if os.environ.get("N3E_GRAPHICAL") != "1":
            b.logout()
            return

        def client(capture, config, states="1"):
            lines = []
            proc = subprocess.Popen(
                ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                 "deploy/local/ca.pem", "--auto-login", "--world-smoke", "14", "--capture", str(capture)],
                env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": passwords["explorer"],
                     "N3E_TEST_EQUIPMENT_GLOW_CAPTURES": f"{PEAK},{TROUGH}", "N3E_TEST_PART_STATES": states,
                     "XDG_CONFIG_HOME": config},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
            reader.start()
            while proc.poll() is None:
                b.pump(.1)
            reader.join(10)
            text = "".join(lines)
            capture.with_suffix(".log").write_text(text)
            assert proc.returncode == 0, (proc.returncode, text[-1500:])
            made = re.findall(r"^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$", text, re.M)
            assert [float(t) for t, _ in made] == [PEAK, TROUGH], (made, text[-1500:])
            reported = re.findall(r"^PART_STATE entity=(\d+) self=(\d) key=1 flags=3 reference=0 source=4 "
                                  r"destination=5 drawn=(\d) vertices=48$", text, re.M)
            drawn = "0" if states == "ignore" else "1"
            assert sorted(m for _, m, _ in reported) == ["0", "1"] and all(d == drawn for *_, d in reported), (
                reported, text[-1500:])
            found = corners(text)
            assert {t for t, _ in found} == {PEAK, TROUGH} and len(found) == 4, sorted(found)
            return found, [Path(p) for _, p in made]
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            where, glowing = client(out / "states-glow.ppm", config)
            Path(config, "n3e").mkdir()
            Path(config, "n3e", "Option.ini").write_text("[Addition2233]\nEquipmentGlow=0\n")
            drawn_at, states = client(out / "states.ppm", config)
            ignored_at, ignored = client(out / "ignored.ppm", config, states="ignore")
        assert set(where) == set(drawn_at) == set(ignored_at), (sorted(where), sorted(drawn_at), sorted(ignored_at))
        # PQ-356: the three clients must draw one scene, or what lies behind a
        # band in one is not what lies behind it in another. The local player
        # stands still under N3E_TEST_PART_STATES (the world smoke's walk would
        # put it somewhere else each run), so each player's band centres agree.
        for key in where:
            spread = max(math.dist(p, q) for found in (drawn_at, ignored_at)
                         for p, q in zip(where[key], found[key]))
            assert spread <= 1, ("the clients drew different scenes", key, where[key], drawn_at[key], ignored_at[key])
        failures, reports = [], {}
        for i, at in enumerate((PEAK, TROUGH)):
            for who in ("self", glow_live_other(where)):
                for mode, (shot, centres) in (("glow off", (states[i], drawn_at)), ("glow", (glowing[i], where))):
                    f, r = judge(shot, ignored[i], centres[at, who], ignored_at[at, who])
                    failures += [(at, who, mode, x) for x in f]
                    reports[at, who, mode] = r
        # Both faces: the ignored draw culls one player's single-sided quads at least, the state draws them.
        culled = {who for (_, who, _), r in reports.items() if r["culled"]}
        if not culled:
            failures.append(("no player's quads culled when ignored", reports))
        # The glow (a pulse at 2x: held at 1 at the peak, 0 at the trough) brightens
        # bands A-C, each by its alpha's share of band A's gain, and never D.
        for at in (PEAK, TROUGH):
            for who in {w for t, w, _ in reports if t == at}:
                lit, dark = reports[at, who, "glow"]["on"], reports[at, who, "glow off"]["on"]
                if not all(sum(lit[k]) >= sum(dark[k]) + 30 * BANDS[k] / 255 for k in range(3)) \
                        or not near(lit[3], dark[3]):
                    failures.append((at, who, "glow", lit, dark))
        assert not failures, (failures, reports)
        print(f"PASS graphical client draws the equipped part with its render state on the local and the other "
              f"player: at each band's centre the drawn pixel is the band's alpha (255, 192, 64, 0) over what lies "
              f"behind it within {TOLERANCE} levels, with and without the glow; band D draws nothing; the "
              f"single-sided quads the ignored draw culls ({sorted(map(str, culled))}) are drawn; the glow brightens "
              f"bands A-C and leaves D alone; {reports}; {glowing[0]}, {states[0]}, {ignored[0]}", flush=True)
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
    refused = check_readers(package)
    print(f"PASS N3D3 package: both readers accept it; the client refuses {refused} malformed render states",
          flush=True)
    live(package)
