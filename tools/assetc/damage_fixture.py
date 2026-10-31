#!/usr/bin/env python3
"""Original KO-04 lab: explicitly synthetic stats, optional local presentation."""
import argparse
import json
from pathlib import Path
import melee_fixture
import main


def cook(ko=False):
    melee_fixture.cook(ko)
    root = Path("build/ko-01/source-ko" if ko else "build/ko-01/source")
    m = json.loads((root / "package.json").read_text())
    m.update(
        engine_version=5,
        damage={
            "model": "contested_melee_v1",
            "player": dict(attack=36, defense=20, accuracy=50, evasion=100),
            "npc": dict(attack=18, defense=40, accuracy=50, evasion=100),
        },
    )
    m["gameplay"].update(npc_health=150)
    (root / "package.json").write_text(json.dumps(m, indent=2) + "\n")
    out = Path("build/packages/damage-ko" if ko else "build/packages/damage")
    print(main.cook(root, out))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ko", action="store_true")
    cook(p.parse_args().ko)
