#!/usr/bin/env python3
"""KO-11 optional local artwork and original alternate package boundary fixture."""
import argparse
import json
from pathlib import Path
import shutil
import animation
import animation_fixture
import ko_character
import ko_hud
import ko_player
import main
import gltf


def cook(imported=False):
    name = "demo-ko" if imported else "demo-alt"
    root = Path("build/ko-11") / name
    shutil.copytree("games/demo", root, dirs_exist_ok=True)
    m = json.loads((root / "package.json").read_text())
    if imported:
        assets = Path("assets/ko")
        report = {
            "player": ko_player.cook(
                assets, root / "player", locomotion=True, ready=True
            ),
            "npc": {},
        }
        clips = []
        for state in animation.STATES:
            shutil.copyfile(
                root / "player" / f"player-{state}.bin", root / f"player-{state}.bin"
            )
            clips.append(animation_fixture.metadata(report["player"][state]))
        for state, index in [("idle", 0), ("walk", 2), ("attack", 4), ("death", 10)]:
            target = root / "npc" / state
            provenance = ko_character.convert(
                assets, "Chr/mob_worm.n3chr", target, index, 1.0
            )
            main.cook(target, target / "cooked")
            shutil.copyfile(target / "cooked/scene.bin", root / f"npc-{state}.bin")
            clips.append(animation_fixture.metadata(provenance))
            report["npc"][state] = provenance
        for name in ("character.gltf", "character.bin", "atlas.png"):
            shutil.copyfile(root / "npc/idle" / name, root / name)
        m["assets"][0]["source"] = "character.gltf"
        meta = json.loads((root / "scene.json").read_text())
        meta["attachment_node"] = 0
        (root / "scene.json").write_text(json.dumps(meta, indent=2) + "\n")
        for i in (2, 3, 9, 10):
            clips[i]["loop_blend"] = False
        m["animation"] = clips
        source = ko_character.Assets(assets)
        report["hud"] = ko_hud.cook(
            source,
            root / "hud.bin",
            m["gameplay"]["npc_health"],
            m["gameplay"]["level_xp"],
        )
        report["hud_sources"] = source.sources
        report["policy"] = (
            "Cosmetic override only; demo gameplay, progression, collision and camera unchanged. Local use only."
        )
        (root / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    else:
        # Different namespace, pace, balance, camera and texture, same engine.
        def namespace(v):
            if isinstance(v, dict):
                return {k: namespace(x) for k, x in v.items()}
            if isinstance(v, list):
                return [namespace(x) for x in v]
            if isinstance(v, str):
                return v.replace("demo:", "alternate:")
            return v

        m = namespace(m)
        m["game_id"] = "alternate"
        m["gameplay"]["movement"]["run_speed"] = 3.0
        m["gameplay"]["health"] = 160
        m["camera"]["distance"] = 5
        m["progression"].update(author="n3e KO-11 original alternate", base_xp=15)
        w, h, pixels = gltf.png((root / "orientation.png").read_bytes())
        pixels = bytearray(pixels)
        for i in range(0, len(pixels), 3):
            pixels[i], pixels[i + 2] = pixels[i + 2], pixels[i]
        (root / "orientation.png").write_bytes(ko_character.png(w, h, pixels))
        # Alter every original N3S1 atlas identically, preserving clip compatibility.
        for name in animation.NAMES:
            path = root / name
            data = bytearray(path.read_bytes())
            import struct

            w, h = struct.unpack_from("<II", data, 4)
            for i in range(12, 12 + w * h * 3, 3):
                data[i], data[i + 2] = data[i + 2], data[i]
            path.write_bytes(data)
    (root / "package.json").write_text(json.dumps(m, indent=2) + "\n")
    out = Path("build/packages") / ("demo-ko" if imported else "demo-alt")
    print(main.cook(root, out))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ko", action="store_true")
    cook(p.parse_args().ko)
