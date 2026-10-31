#!/usr/bin/env python3
"""Original movement laboratory; optionally reuse already-converted local KO visuals."""
import argparse
import json
import pathlib
import shutil
import main
import ko_player


def cook(ko=False):
    source = pathlib.Path("build/ko-source/field" if ko else "tests/fixtures/legacy-demo")
    root = pathlib.Path("build/ko-01/source-ko" if ko else "build/ko-01/source")
    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, root, dirs_exist_ok=True)
    recipe = json.loads((root / "package.json").read_text())
    recipe.update(engine_version=2, protocol_version=2)
    # The labs share the demo's KO key layout (PQ-009, D-136); the legacy
    # fixture they start from predates package input maps.
    recipe["input"] = json.loads(pathlib.Path("games/demo/package.json").read_text())["input"]
    if ko:
        # Refresh movement clips even when reusing a pre-KO-01 field conversion.
        player = pathlib.Path("build/ko-01/player")
        ko_player.cook(
            pathlib.Path("assets/ko"), player, locomotion=True
        )
        for state in ["idle", "walk", "attack", "death", "run", "backward"]:
            name = "player-" + state + ".bin"
            shutil.copyfile(player / name, root / name)
            recipe["presentation"][name] = name
    r = recipe["gameplay"]
    r.update(
        speed=1.5,
        movement=dict(
            run_speed=4.5, backward_speed=1.5, radius=0.2, height=1.6, step_height=0.25
        ),
        spawns=[[12, 12]],
        spawn_x=12,
        spawn_z=12,
        interest_cell=32,
    )
    (root / "package.json").write_text(json.dumps(recipe, indent=2) + "\n")
    meta = json.loads((root / "scene.json").read_text())
    meta["heightfield"] = dict(
        width=25, depth=25, origin=[-24, 0, -24], spacing=2, heights=[0] * 625
    )
    # Original thin wall, isolated low/high ledges and a 26.6-degree ramp.
    t = []

    def quad(a, b, c, d):
        t.extend([a, b, c, a, c, d])

    quad([2, 0, -3], [2, 2, -3], [2, 2, 3], [2, 0, 3])
    for x, h in [(-4, 0.2), (-8, 0.3)]:
        quad([x, h, 2], [x + 2, h, 2], [x + 2, h, 4], [x, h, 4])
    quad([4, 0, 5], [8, 2, 5], [8, 2, 7], [4, 0, 7])
    meta["triangles"] = [t[i : i + 3] for i in range(0, len(t), 3)]
    (root / "scene.json").write_text(json.dumps(meta, indent=2) + "\n")
    package = pathlib.Path(
        "build/packages/movement-ko" if ko else "build/packages/movement"
    )
    print(main.cook(root, package))
    return package


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ko", action="store_true", help="use existing build/ko-source/field visuals"
    )
    cook(parser.parse_args().ko)
