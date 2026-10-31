"""PQ-380: the target marker's parts drawn in the frame's one far-to-near alpha pass, live.

1298's target symbol (005c4e20) draws its shape through slot +0x48
(005c5129: 004442e0 -> 00443090), which queues each part (render flags 9 and
1, blend ONE/ONE) into the frame alpha list, keyed by the linear eye distance
to the part matrix's translation; the frame flushes that list far to near at
005c4d98, after the FX manager has queued its parts (0043dd80, 0043e6c0). n3e
drew the marker in its own pass before every effect. The client now keys each
marker part by target_marker_key and draws it as an external draw of the
effect pass (client/render/viewer.cpp). The evidence record
(docs/implementation/evidence/pq-380-target-marker-in-alpha-list.md) labels
each claim.

The package is the PQ-249 fixture (tests/npc_templates_live.py) with an
original synthetic world, render detail world textures, effects file and
target marker (N3TM):

- an opaque black backdrop (a terrain patch) 6 m behind,
- the marker: one upright quad, red, 4 x 4 m, its key point (the pivot at the
  symbol's scale) at its centre, 10 m from the camera; the test client places
  it offline (N3E_TEST_MARKER_AT) for an NPC at scale 1,
- two non-additive effects (blend 5/6, alpha 0.5, no depth write), started
  offline (N3E_TEST_EFFECT_AT): a green quad 3 m behind the marker, a blue one
  3 m in front, each over its own half of it.

With N3E_GRAPHICAL=1 the test client draws it offline at 320x240 and the suite
reads the capture. Where the green quad lies behind the marker, KO's order
draws it first and the marker adds over it: red and green together. Where the
blue one lies in front, it blends over the marker: half the marker's red with
blue. The marker in a pass of its own before the effects writes its depth
first, so the green fails it there (no green over the marker); a pass after
them adds the full red over the blue. Each fails one of the two counts (the
evidence record has the mutation runs).
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

OUT = ROOT / "build/pq380"
SIZE = (320, 240)
EYE, TARGET = (0.0, 2.0, 10.0), (0.0, 2.0, 0.0)
# N3TM: diameter and height multipliers, ground lift; (radius, height) for the
# player and the NPC. The NPC's symbol is 2 x 2 = 4 m across, 1.3 x 4 / 1.3 =
# 4 m high.
MARKER = dict(diameter=2.0, height=1.3, lift=0.1, player=(0.5, 1.8), npc=(2.0, 4.0 / 1.3))
# The selected NPC's point and the part's pivot: the quad spans x -2..2, y 0..4
# at z 0, and its key point (the pivot at the symbol's scale) is (0, 2, 0).
AT, PIVOT = (0.0, 0.0, 0.0), (0.0, 0.5, 0.0)
KEY_POINT = (0.0, 2.0, 0.0)
# The effects: centre, quad side. Behind: farther than the marker's key point;
# in front: nearer. Each covers its own half of the marker on screen.
BEHIND = dict(key="behind", at=(-1.2, 2.0, -3.0), side=1.6, texture=1)
FRONT = dict(key="front", at=(0.8, 2.0, 3.0), side=1.0, texture=2)
EFFECT_FLAGS = 0x1 | 0x4 | 0x40 | 0x100  # blend, both faces, unlit, no depth write


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


def marker_file():
    """N3TM (content/target-marker.md): one upright, camera-facing part (mode 1),
    a unit quad centred on its origin, pivot (0, 0.5, 0), 1 x 1 red texel."""
    data = b"N3TM" + fl(MARKER["diameter"], MARKER["height"], MARKER["lift"], *MARKER["player"], *MARKER["npc"]) + u(1)
    corners = [(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0)]
    data += u(1) + fl(*PIVOT) + u(1, 1) + bytes([255, 0, 0, 255]) + u(4)
    for k, c in enumerate(corners):
        data += fl(*c, 0, 0, 1, k % 2, k // 2)
    return data + u(6, 0, 1, 2, 0, 2, 3)


def world_files():
    """(N3W1 bytes, N3L bytes): the black backdrop as the one terrain patch
    (both windings)."""
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import ko_lod
    vertices = [[x, y, -6, 0, 0, 1, 0, 0, .5, .5, 1, 0] for x, y in ((-20, -15), (20, -15), (20, 20), (-20, 20))]
    backdrop = [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]
    terrain = dict(center=[0, 2, -6], radius=30, scale=1, flags=2, kind=2, patch=[0, 0],
                   levels=[(float(i), backdrop) for i in range(33)])
    built = dict(terrain_lod=dict(origin=[-64, 0, 64], patch_size=128, far_factor=3 / 512, bias=.6, minimum=2,
                                  band=3, width=1),
                 parents=[[0, 2, 0, 50, 0, 2, 0, 10]], chunks=[terrain])
    world = (b"N3W1" + u(32, 32, 8, 1) + bytes([255]) * 4096 + u(len(vertices))
             + b"".join(fl(*v) for v in vertices) + u(3) + u(0, 1, 2))
    return world, ko_lod.serialize(built)


@once_per_run
def prepare():
    """Cook the PQ-249 package with the synthetic world, detail, effects and marker."""
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
    # World textures 0 clear (the second layer) and 1 black; then the
    # character's and the appearance's.
    (root / "detail.bin").write_bytes(render_detail.serialize(
        view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=2,
        textures=[solid((0, 0, 0, 0)), solid((0, 0, 0, 255)), solid((255, 255, 255, 255)), solid((255, 255, 255, 255))],
        radius=1, levels=[geometry(2)] * 4, appearances=[([2], [geometry(3)] * 4)]))
    (root / "effects.bin").write_bytes(effects_file())
    (root / "target-marker.bin").write_bytes(marker_file())
    m["presentation"]["target-marker.bin"] = "target-marker.bin"
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def check_readers(package):
    """Both readers accept the package."""
    c = subprocess.run(["build/client/n3e-asset-check", str(package)], cwd=ROOT, capture_output=True, text=True)
    assert c.returncode == 0, c.stderr[-2000:]
    s = subprocess.run(["target/debug/n3e-server", "--check-content"], cwd=ROOT,
                       env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
    assert s.returncode == 0, s.stderr[-2000:]
    print("PASS N3TM package with effects: client and server accept it")


def colours(path):
    """The marker's red alone (g and b < 30, r > 60), the median of that red,
    and the pixels that hold red with green (g 90-160, b < 30, r > 60) and red
    with blue (b 90-160, g < 30, r > 30)."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    alone, with_green, with_blue = [], [], []
    for at in range(0, width * height * 3, 3):
        r, g, b = pixels[at:at + 3]
        if r > 60 and g < 30 and b < 30:
            alone.append(r)
        elif r > 60 and 90 <= g <= 160 and b < 30:
            with_green.append(r)
        elif r > 30 and 90 <= b <= 160 and g < 30:
            with_blue.append(r)
    return alone, with_green, with_blue


def median(values):
    return sorted(values)[len(values) // 2]


def graphical(package):
    capture = OUT / "live" / "target-marker-order.ppm"
    capture.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "N3E_TEST_WORLD_VIEW": "%g %g %g %g %g %g" % (*EYE, *TARGET),
           "N3E_TEST_MARKER_AT": "%g %g %g" % AT,
           "N3E_TEST_EFFECT_AT": "%s %g %g %g;%s %g %g %g" % (BEHIND["key"], *BEHIND["at"], FRONT["key"], *FRONT["at"])}
    p = subprocess.run(["build/client/n3e-test-client", str(package), "--smoke", "--fixed-window", "%dx%d" % SIZE,
                        "--capture", str(capture)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    log = p.stdout + p.stderr
    capture.with_suffix(".log").write_text(log)
    assert p.returncode == 0, (p.returncode, log[-2000:])
    marker = re.search(r"^MARKER_ALPHA frame=40 parts=(\d+) eye=(\S+) keys=(\S*)$", log, re.M)
    world = re.search(r"^WORLD_ALPHA frame=40 parts=(\d+) eye=(\S+) keys=(\S*) effects=(\S*)$", log, re.M)
    assert marker and world, log[-2000:]
    # The picture first: both blends must show.
    alone, with_green, with_blue = colours(capture)
    assert len(alone) >= 1000, (len(alone), len(with_green), len(with_blue), marker.group(0))
    red = median(alone)
    # Behind: the green first, the marker's full red added over it.
    over_green = [r for r in with_green if abs(r - red) <= max(12, red * .1)]
    # In front: the blue over the marker, half its red left.
    under_blue = [r for r in with_blue if abs(r - red / 2) <= max(12, red * .1)]
    assert len(over_green) >= 150 and len(under_blue) >= 150, (red, len(over_green), len(under_blue), len(with_green),
                                                                 len(with_blue), marker.group(0), world.group(0))
    # The keys the order turns on: the marker's at 10 m, the effects' either side.
    dist = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b)) ** .5  # noqa: E731
    eye = [float(v) for v in marker.group(2).split(",")]
    keys = [float(v) for v in marker.group(3).split(",") if v]
    effects = sorted(float(v) for v in world.group(4).split(",") if v)
    assert marker.group(1) == "1" and world.group(1) == "0" and max(abs(a - b) for a, b in zip(eye, EYE)) < 1e-4, \
        (marker.group(0), world.group(0))
    assert len(keys) == 1 and abs(keys[0] - dist(EYE, KEY_POINT)) < 1e-3, marker.group(0)
    want = sorted(dist(EYE, e["at"]) for e in (BEHIND, FRONT))
    assert len(effects) == 2 and max(abs(a - b) for a, b in zip(effects, want)) < 1e-3, world.group(0)
    assert effects[0] + 1 < keys[0] < effects[1] - 1, (keys, effects)
    print("PASS graphical client draws the target marker between the effects in one far-to-near pass "
          "(keys %.2f < %.2f < %.2f m; marker red %d alone, %d px with the green behind added over it, "
          "%d px at half under the blue in front)" % (effects[0], keys[0], effects[1], red, len(over_green),
                                                      len(under_blue)))


if __name__ == "__main__":
    package = prepare()
    check_readers(package)
    if os.environ.get("N3E_GRAPHICAL") != "1":
        print("UNVERIFIED target marker order capture needs N3E_GRAPHICAL=1 (make live)")
        sys.exit(0)
    graphical(package)
