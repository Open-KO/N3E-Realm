#!/usr/bin/env python3
"""KO-02 original camera laboratory, with optional existing local presentation."""
import argparse
import json
import math
from pathlib import Path
import main
import movement_fixture

PROFILE = dict(
    pitch=math.radians(25),
    pitch_min=math.radians(10),
    pitch_max=math.radians(70),
    distance=7,
    distance_min=2,
    distance_max=10,
    focus_height=0,
    focus_scale=0.8,
    yaw_per_pixel=0.006,
    pitch_per_pixel=0.005,
    zoom_per_step=0.7,
    clearance=0.2,
    turn_rate=math.pi / 3,
    hold_delay=0.1,
    facing_relative=True,
)


def cook(ko=False):
    movement_fixture.cook(ko)
    root = Path("build/ko-01/source-ko" if ko else "build/ko-01/source")
    manifest = json.loads((root / "package.json").read_text())
    manifest.update(camera=PROFILE, engine_version=3)
    (root / "package.json").write_text(json.dumps(manifest, indent=2) + "\n")
    out = Path("build/packages/camera-ko" if ko else "build/packages/camera")
    print(main.cook(root, out))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ko", action="store_true")
    cook(parser.parse_args().ko)
