#!/usr/bin/env python3
"""Original KO-06 life lab; optional already-local character/HUD presentation."""
import argparse
import json
from pathlib import Path
import npc_fixture
import main


def cook(ko=False):
    npc_fixture.cook(ko, low_health=True)
    root = Path("build/ko-01/source-ko" if ko else "build/ko-01/source")
    m = json.loads((root / "package.json").read_text())
    m.update(
        engine_version=7,
        protocol_version=3,
        life=dict(
            model="requested_v1",
            player_delay_ticks=60,
            npc_corpse_ticks=40,
            npc_respawn_ticks=120,
        ),
    )
    m["gameplay"].update(npc_health=60)
    (root / "package.json").write_text(json.dumps(m, indent=2) + "\n")
    out = Path("build/packages/life-ko" if ko else "build/packages/life")
    print(main.cook(root, out))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ko", action="store_true")
    cook(p.parse_args().ko)
