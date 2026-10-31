#!/usr/bin/env python3
"""Original KO-05 NPC lab; optional existing local KO presentation."""
import argparse
import json
from pathlib import Path
import damage_fixture
import main


def cook(ko=False, low_health=False):
    damage_fixture.cook(ko)
    root = Path("build/ko-01/source-ko" if ko else "build/ko-01/source")
    m = json.loads((root / "package.json").read_text())
    m.update(engine_version=6, npc=dict(model="hostile_melee_v1", scan_ticks=10,
        acquire_ticks=10, stuck_ticks=40, chase_ticks=400, return_ticks=200, recovery_ticks=40))
    m["gameplay"].update(npc_health=1500, health=30 if low_health else 1000, npc_speed=3.0,
        npc_range=1.0, aggro_range=7.0, leash_range=12.0, spawns=[[-5.0,-5.0]])
    (root / "package.json").write_text(json.dumps(m, indent=2) + "\n")
    out = Path("build/packages/" + ("npc-ko" if ko else "npc") + ("-death" if low_health else ""))
    print(main.cook(root, out))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ko", action="store_true")
    p.add_argument("--low-health", action="store_true", help="isolated target-death verification fixture")
    args = p.parse_args()
    cook(args.ko, args.low_health)
