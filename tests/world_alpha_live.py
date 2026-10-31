"""PQ-379: world parts that 1298 alpha-blends, drawn in the frame's one alpha pass, live.
PQ-382: its opaque parts' alpha test and unlit flag, in the same capture.

1298 queues a world shape part whose material has render flag 1 into its frame
alpha list (00443090: the key is the linear eye distance to the part matrix's
translation, the blend its material's +0xd0/+0xd4, the flags +0xcc), and
draws the list once, far to near, with every other alpha primitive of the
frame, effects included (0043dd80, 0043e6c0). D-201 carries such a part as an
N3L4 / N3W3 alpha part, and the client draws it in the effect pass at its
place in that order. evidence/pq-379-world-shape-alpha-parts-sorted.md labels
each claim.

The package is the PQ-249 fixture (tests/npc_templates_live.py: world, render
detail, effects) with an original synthetic world, render detail world
textures and effects file:

- an opaque black backdrop (a terrain patch) 6 m behind,
- the alpha part: a 4 m square, red with texture alpha 128, blend 5/6, unlit
  (KO's 0x40), its sort point at its centre, 10 m from the camera,
- two non-additive effects (blend 5/6, alpha 0.5, no depth write), started
  offline by the test client (N3E_TEST_EFFECT_AT): a green quad 3 m behind
  the part, a blue one 3 m in front, each over its own half of the part.

Both readers accept the package; the client reports the alpha part's record.
With N3E_GRAPHICAL=1 the test client draws it offline at 320x240 and the suite
reads the capture: where the green quad lies behind the part, the part must
blend over it (red over green over black, about (128, 64, 0)); where the blue
one lies in front, it must blend over the part (blue over red over black,
about (64, 0, 128)). Keeping the alpha test (the part opaque in the world
pass) leaves no green there and blue at half the red; a pass of the part's own
before the effects hides the green behind its depth; one after them puts the
red over the blue. Each fails one of the two colours (the evidence record has
the mutation runs).

PQ-382 (D-202): 1298 draws an opaque part (material flag 1 clear) at once,
alpha-tested as its device set-up leaves the test (0043ade0: GREATER against
reference 0) and unlit for RF_NOTUSELIGHT (00443090 at 004432da). The world's
N3L5 bits carry both. A row of five opaque quads below the alpha part, each
2 x 2.2 m over the black backdrop, in the same capture:

- green at texture alpha 64, cut at zero: drawn (the one-half cut drops it),
- blue at alpha 64 without the bit: cut, as every other package's parts are,
- magenta at alpha 0, cut at zero: cut (the test is still there),
- yellow at alpha 255, cut at zero and unlit: its texture's colour,
- the same yellow, lit: darker than that.

Each mutation of the client's rule (the bit ignored, applied to every part,
no test at all, unlit ignored or applied to every part) fails one count.
"""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq379"
SIZE = (320, 240)
EYE, TARGET = (0.0, 2.0, 10.0), (0.0, 2.0, 0.0)
# The alpha part: x -2..2, y 0..4 at z 0, its sort point at its centre.
PART = dict(x=(-2.0, 2.0), y=(0.0, 4.0), z=0.0, sort=(0.0, 2.0, 0.0))
# The effects: centre, quad side. Behind: farther than the part's sort point;
# in front: nearer. Each covers its own half of the part on screen.
BEHIND = dict(key="behind", at=(-1.2, 2.0, -3.0), side=1.6, texture=1)
FRONT = dict(key="front", at=(0.8, 2.0, 3.0), side=1.0, texture=2)
EFFECT_FLAGS = 0x1 | 0x4 | 0x40 | 0x100  # blend, both faces, unlit, no depth write
RED = (255, 0, 0, 128)
# PQ-382: the opaque row (x centre, texture, flags beyond culling): world
# textures 3 green alpha 64, 4 blue alpha 64, 5 magenta alpha 0, 6 yellow.
CUT_ZERO, UNLIT = 32, 64
ROW_Y = (-3.6, -1.4)
ROW = [dict(name="green", x=-6.0, texture=3, flags=CUT_ZERO), dict(name="blue", x=-3.5, texture=4, flags=0),
       dict(name="magenta", x=-1.0, texture=5, flags=CUT_ZERO),
       dict(name="unlit yellow", x=1.5, texture=6, flags=CUT_ZERO | UNLIT),
       dict(name="lit yellow", x=4.0, texture=6, flags=CUT_ZERO)]
ROW_TEXTURES = [(0, 255, 0, 64), (0, 0, 255, 64), (255, 0, 255, 0), (255, 255, 0, 255)]


def u(*v):
    return struct.pack("<%dI" % len(v), *v)


def fl(*v):
    return struct.pack("<%df" % len(v), *v)


def string(s):
    return u(len(s)) + s.encode()


def effects_file():
    """N3EF: textures 0 white, 1 green, 2 blue (1 x 1); the skill's two blank
    clips and the two test quads, ten one-second frames each (the 10 s bound)."""
    def texture(rgba):
        return u(1, 1) + bytes(rgba)
    data = b"N3EF" + u(3) + texture((255, 255, 255, 255)) + texture((0, 255, 0, 255)) + texture((0, 0, 255, 255))
    blank = lambda name: string(name) + u(0) + u(10) + u(1) + u(0)  # noqa: E731

    def quad(e):
        batch = u(1) + u(1, e["texture"], 5, 6, EFFECT_FLAGS, 1) + fl(0, 0, 0, e["side"], e["side"], 0, 1, 1, 1, .5, 0)
        return string(e["key"]) + u(0) + u(1) + u(10) + batch * 10
    return data + u(4) + blank("cast") + blank("heal") + quad(BEHIND) + quad(FRONT) + u(0)


def world_files():
    """(N3W1 bytes, N3L5 bytes): the backdrop as the one terrain patch (both
    windings), the alpha part and the opaque row (PQ-382) as progressive parts
    at full detail."""
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import ko_lod
    vertices = []
    for x, y in ((-20, -15), (20, -15), (20, 20), (-20, 20)):
        vertices.append([x, y, -6, 0, 0, 1, 0, 0, .5, .5, 1, 0])
    (x0, x1), (y0, y1) = PART["x"], PART["y"]
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        vertices.append([x, y, PART["z"], 0, 0, 1, 0, 0, .5, .5, 2, 0])
    backdrop = [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]
    terrain = dict(center=[0, 2, -6], radius=30, scale=1, flags=2, kind=2, patch=[0, 0],
                   levels=[(float(i), backdrop) for i in range(33)])
    part = dict(center=[0, 2, 0], radius=3, scale=1, flags=8 | 16, kind=1, parent=0, base=4, max_vertices=4,
                levels=[(0., [4, 5, 6, 4, 6, 7])],
                progressive=dict(min_vertices=4, min_indices=6, controls=[], splits=[], edits=[]),
                alpha=dict(source=5, destination=6, state=0x41, point=list(PART["sort"])))
    row = []
    for q in ROW:
        base = len(vertices)
        for x, y in ((q["x"] - 1, ROW_Y[0]), (q["x"] + 1, ROW_Y[0]), (q["x"] + 1, ROW_Y[1]), (q["x"] - 1, ROW_Y[1])):
            vertices.append([x, y, 0, 0, 0, 1, 0, 0, .5, .5, q["texture"], 0])
        row.append(dict(center=[q["x"], sum(ROW_Y) / 2, 0], radius=1.6, scale=1, flags=8 | q["flags"], kind=1,
                        parent=0, base=base, max_vertices=4, levels=[(0., [base, base + 1, base + 2, base, base + 2, base + 3])],
                        progressive=dict(min_vertices=4, min_indices=6, controls=[], splits=[], edits=[])))
    built = dict(terrain_lod=dict(origin=[-64, 0, 64], patch_size=128, far_factor=3 / 512, bias=.6, minimum=2,
                                  band=3, width=1),
                 parents=[[0, 2, 0, 50, 0, 2, 0, 10]], chunks=[terrain, part, *row])
    # A 32 x 32 atlas of 8-texel cells: 16 slots, so the vertices may name the
    # seven world textures render detail replaces them with.
    world = (b"N3W1" + u(32, 32, 8, 1) + bytes([255]) * 4096 + u(len(vertices))
             + b"".join(fl(*v) for v in vertices) + u(3) + u(0, 1, 2))
    lod = ko_lod.serialize(built)
    assert lod[:4] == b"N3L5", lod[:4]
    return world, lod


@once_per_run
def prepare():
    """Cook the PQ-249 package with the synthetic world, detail and effects."""
    from npc_templates_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import importlib.util
    import main
    spec = importlib.util.spec_from_file_location("render_detail", ROOT / "tools/assetc/render_detail.py")
    render_detail = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_detail)

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    world, lod = world_files()
    (root / "map.bin").write_bytes(world)
    (root / "lod.bin").write_bytes(lod)
    assert m["world"] == "map.bin" and m["exploration"]["lod"] == "lod.bin" and m["render_detail"] == "detail.bin"

    def solid(rgba):
        return [(16, 16, bytes(rgba) * 256)]

    def geometry(slot):
        return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]],
                [0, 1, 2])
    # World textures 0 clear (the second layer), 1 black, 2 the part's red at
    # alpha 128, 3-6 the opaque row's; then the character's and the appearance's.
    (root / "detail.bin").write_bytes(render_detail.serialize(
        view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=7,
        textures=[solid((0, 0, 0, 0)), solid((0, 0, 0, 255)), solid(RED), *(solid(t) for t in ROW_TEXTURES),
                  solid((255, 255, 255, 255)), solid((255, 255, 255, 255))],
        radius=1, levels=[geometry(7)] * 4, appearances=[([7], [geometry(8)] * 4)]))
    (root / "effects.bin").write_bytes(effects_file())
    main.cook(root, out)
    return out.resolve()


def check_readers(package):
    """Both readers accept the package; the client reads the alpha record."""
    c = subprocess.run(["build/client/n3e-asset-check", str(package)], cwd=ROOT, capture_output=True, text=True)
    assert c.returncode == 0, c.stderr[-2000:]
    assert "world alpha parts 1 first 5 6 65 0 2 0" in c.stdout.splitlines(), c.stdout[-2000:]
    assert "world opaque parts cut-zero 4 unlit 1" in c.stdout.splitlines(), c.stdout[-2000:]
    s = subprocess.run(["target/debug/n3e-server", "--check-content"], cwd=ROOT,
                       env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
    assert s.returncode == 0, s.stderr[-2000:]
    print("PASS N3L5 package: client and server accept it; the client reads the alpha part's record "
          "(5/6, state 0x41, sort point (0, 2, 0)) and the opaque row's bits (4 cut at zero, 1 unlit)")


def colours(path):
    """Pixels of the two blends: red over green (r 100-160, g 40-90, b < 30)
    and blue over red (r 40-90, b 100-160, g < 30), and the part alone over
    black (r 100-160, g and b < 30)."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    over_green = over_red = alone = 0
    for at in range(0, width * height * 3, 3):
        r, g, b = pixels[at:at + 3]
        if 100 <= r <= 160 and 40 <= g <= 90 and b < 30:
            over_green += 1
        elif 40 <= r <= 90 and 100 <= b <= 160 and g < 30:
            over_red += 1
        elif 100 <= r <= 160 and g < 30 and b < 30:
            alone += 1
    return over_green, over_red, alone


def row_colours(path):
    """PQ-382: pixels of the opaque row: green (g >= 60, r and b < 30), blue
    (b >= 60, r and g < 30), magenta (r and b >= 40 within 8 of each other,
    g < 30; the effect's blue over the red part is not), the texture's
    own yellow (r and g >= 240, b < 40) and a darker yellow (r and g 40-225
    within 8 of each other, b < 40)."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    counts = dict(green=0, blue=0, magenta=0, bright=0, dim=0)
    for at in range(0, width * height * 3, 3):
        r, g, b = pixels[at:at + 3]
        if g >= 60 and r < 30 and b < 30:
            counts["green"] += 1
        elif b >= 60 and r < 30 and g < 30:
            counts["blue"] += 1
        elif r >= 40 and b >= 40 and abs(r - b) <= 8 and g < 30:
            counts["magenta"] += 1
        elif r >= 240 and g >= 240 and b < 40:
            counts["bright"] += 1
        elif 40 <= r <= 225 and 40 <= g <= 225 and abs(r - g) <= 8 and b < 40:
            counts["dim"] += 1
    return counts


def graphical(package):
    capture = OUT / "live" / "world-alpha.ppm"
    capture.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "N3E_TEST_WORLD_VIEW": "%g %g %g %g %g %g" % (*EYE, *TARGET),
           "N3E_TEST_EFFECT_AT": "%s %g %g %g;%s %g %g %g" % (BEHIND["key"], *BEHIND["at"], FRONT["key"], *FRONT["at"])}
    p = subprocess.run(["build/client/n3e-test-client", str(package), "--smoke", "--fixed-window", "%dx%d" % SIZE,
                        "--capture", str(capture)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    log = p.stdout + p.stderr
    capture.with_suffix(".log").write_text(log)
    assert p.returncode == 0, (p.returncode, log[-2000:])
    line = re.search(r"^WORLD_ALPHA frame=40 parts=(\d+) eye=(\S+) keys=(\S*) effects=(\S*)$", log, re.M)
    assert line, log[-2000:]
    # The picture first: both blends must show.
    over_green, over_red, alone = colours(capture)
    assert over_green >= 150 and over_red >= 150 and alone >= 1000, (over_green, over_red, alone, line.group(0))
    eye = [float(v) for v in line.group(2).split(",")]
    keys = [float(v) for v in line.group(3).split(",") if v]
    effects = sorted(float(v) for v in line.group(4).split(",") if v)
    # The keys the order turns on: the part's at 10 m, the effects' either side.
    dist = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b)) ** .5  # noqa: E731
    assert line.group(1) == "1" and max(abs(a - b) for a, b in zip(eye, EYE)) < 1e-4, line.group(0)
    assert len(keys) == 1 and abs(keys[0] - dist(EYE, PART["sort"])) < 1e-3, line.group(0)
    want = sorted(dist(EYE, e["at"]) for e in (BEHIND, FRONT))
    assert len(effects) == 2 and max(abs(a - b) for a, b in zip(effects, want)) < 1e-3, line.group(0)
    assert effects[0] + 1 < keys[0] < effects[1] - 1, (keys, effects)
    print("PASS graphical client draws the world alpha part between the effects in one far-to-near pass "
          "(keys %.2f < %.2f < %.2f m; %d px red over green, %d px blue over red, %d px red over black)"
          % (effects[0], keys[0], effects[1], over_green, over_red, alone))
    # PQ-382: the opaque row in the same capture.
    row = row_colours(capture)
    assert row["green"] >= 800 and row["blue"] <= 20 and row["magenta"] <= 20, row
    assert row["bright"] >= 800 and row["dim"] >= 800, row
    print("PASS graphical client draws opaque world parts with KO's alpha test and unlit flag (%d px green at "
          "alpha 64 cut at zero, %d px blue at alpha 64 cut at one half, %d px magenta at alpha 0, %d px unlit "
          "yellow at its texture's colour, %d px lit yellow darker)"
          % (row["green"], row["blue"], row["magenta"], row["bright"], row["dim"]))


if __name__ == "__main__":
    package = prepare()
    check_readers(package)
    if os.environ.get("N3E_GRAPHICAL") != "1":
        print("UNVERIFIED world alpha capture needs N3E_GRAPHICAL=1 (make live)")
        sys.exit(0)
    graphical(package)
