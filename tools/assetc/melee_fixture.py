#!/usr/bin/env python3
"""Original KO-03 interaction lab; optional already-available local presentation."""
import argparse
import json
from pathlib import Path
import camera_fixture
import main
import ko_player
import shutil


def cook(ko=False):
    camera_fixture.cook(ko)
    root = Path("build/ko-01/source-ko" if ko else "build/ko-01/source")
    m = json.loads((root / "package.json").read_text())
    m.update(
        engine_version=4,
        melee=dict(actor_radius=1, target_radius=1, reach=0, facing_dot=0.7),
    )
    if ko:
        player = Path("build/ko-03/player")
        ko_player.cook(Path("assets/ko"), player, locomotion=True, ready=True)
        shutil.copyfile(player / "player-ready.bin", root / "player-ready.bin")
        m["presentation"]["player-ready.bin"] = "player-ready.bin"
    m["gameplay"].update(
        cost=0,
        cooldown_ticks=20,
        npc_health=300,
        health=1000,
        spawns=[[-4, -4], [-8, -4]],
        spawn_x=-4,
        spawn_z=-4,
    )
    (root / "package.json").write_text(json.dumps(m, indent=2) + "\n")
    out = Path("build/packages/melee-ko" if ko else "build/packages/melee")
    print(main.cook(root, out))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ko", action="store_true")
    cook(p.parse_args().ko)
