#!/usr/bin/env python3
"""PQ-215 synthetic large map: a 513 x 513 heightfield (2048 m a side at 4 m)
with objects, generated (no KO data) and cooked to an N3C2 collision package.

Terrain: flat within 48 m of the origin, rolling hills beyond, and a 56-degree
cliff band at x = 200..208 m (steeper than the 45-degree walkable limit, so the
cliff cells act as walls). Objects: a thin wall, two ledges and a ramp at the
origin (the movement laboratory's shapes), a bridge deck, and a wall in the far
corner so the object grid spans the map.
"""
import json
import math
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import main  # noqa: E402

SAMPLES, SPACING, ORIGIN = 513, 4, -1024


def height(x, z):
    r = math.hypot(x, z)
    blend = min(max((r - 48) / 50, 0), 1)
    h = blend * 4 * math.sin(x / 37) * math.cos(z / 53)
    if x >= 200:
        h += 12 * min((x - 200) / 8, 1)
    return round(h, 4)


def objects():
    t = []

    def quad(a, b, c, d):
        t.extend([a, b, c, a, c, d])

    quad([2, 0, -3], [2, 2, -3], [2, 2, 3], [2, 0, 3])
    for x, h in [(-4, 0.2), (-8, 0.3)]:
        quad([x, h, 2], [x + 2, h, 2], [x + 2, h, 4], [x, h, 4])
    quad([4, 0, 5], [8, 2, 5], [8, 2, 7], [4, 0, 7])
    # Bridge deck 2.2 m over the flat ground: overhead support and headroom.
    quad([-20, 2.2, -10], [-12, 2.2, -10], [-12, 2.2, -6], [-20, 2.2, -6])
    y = height(900, 900)
    quad([900, y - 1, 896], [900, y + 3, 896], [900, y + 3, 904], [900, y - 1, 904])
    return [t[i : i + 3] for i in range(0, len(t), 3)]


def source(root):
    root = pathlib.Path(root)
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree("tests/fixtures/legacy-demo", root)
    recipe = json.loads((root / "package.json").read_text())
    recipe.update(engine_version=2, protocol_version=2, package_version="0.215.0")
    recipe["input"] = json.loads(pathlib.Path("games/demo/package.json").read_text())["input"]
    recipe["gameplay"].update(
        speed=1.5,
        movement=dict(run_speed=4.5, backward_speed=1.5, radius=0.2, height=1.6, step_height=0.25),
        spawns=[[12, 12]],
        spawn_x=12,
        spawn_z=12,
        interest_cell=32,
    )
    (root / "package.json").write_text(json.dumps(recipe, indent=2) + "\n")
    meta = json.loads((root / "scene.json").read_text())
    meta["heightfield"] = dict(
        width=SAMPLES,
        depth=SAMPLES,
        origin=[ORIGIN, 0, ORIGIN],
        spacing=SPACING,
        diagonal="alternating",
        heights=[
            height(ORIGIN + i * SPACING, ORIGIN + j * SPACING)
            for j in range(SAMPLES)
            for i in range(SAMPLES)
        ],
    )
    meta["triangles"] = objects()
    (root / "scene.json").write_text(json.dumps(meta) + "\n")
    return root


def cook(out="build/packages/large-map", work="build/pq-215/source"):
    return main.cook(source(work), pathlib.Path(out))


if __name__ == "__main__":
    print(cook(*sys.argv[1:3]))
