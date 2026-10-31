#!/usr/bin/env python3
"""Build a local KO monster field; imported bytes remain under ignored build/."""
import json
import pathlib
import ko_character
import main
import shutil
import ko_player
import ko_hud
import sys

# --into=DIR writes every output below DIR instead of build/ (DIR/ko-source/field,
# DIR/ko-source/player, DIR/packages/ko-field), so make live-ko (PQ-111) never
# replaces the package a persistent tools/play-ko-field stack mounts.
into = pathlib.Path(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--into=")), "build"))
root = into / "ko-source/field"
ko_character.convert(pathlib.Path("assets/ko"), "Chr/mob_worm.n3chr", root, 1, 1.0)
recipe = json.loads((root / "package.json").read_text())
r = recipe["gameplay"]
r.update(spawns=[[-4, -4], [0, -7], [5, -5], [7, 3]], interest_cell=24,
         npc="kotest:creature/worm", aggro_range=2.5, leash_range=8,
         npc_damage=2, respawn_ticks=200, health=100, resource=20, slots=64)
assets = ko_character.Assets(pathlib.Path("assets/ko"))
player_dir = into / "ko-source/player"
ko_player.cook(assets.root, player_dir)
presentation = {}
for state in ["idle", "walk", "attack", "death"]:
    name = "player-" + state + ".bin"
    shutil.copyfile(player_dir / name, root / name)
    presentation[name] = name
hud_report = ko_hud.cook(assets, root / "hud.bin", r["npc_health"], r["level_xp"])
presentation["hud.bin"] = "hud.bin"
recipe["presentation"] = presentation
(root / "package.json").write_text(json.dumps(recipe))
meta = json.loads((root / "scene.json").read_text())
# 48m field, central paths and gently raised grassy edges; shared visual/collision.
meta["heightfield"] = dict(width=25, depth=25, origin=[-24, 0, -24], spacing=2,
    heights=[max(0, (abs(x-12)-7)*.20)+max(0,(abs(z-12)-8)*.16)
             for z in range(25) for x in range(25)])
meta["triangles"] = []
(root / "scene.json").write_text(json.dumps(meta))
provenance = json.loads((root / "provenance.json").read_text())
provenance["field"] = {"terrain": "original 48m heightfield", "player": "local male Tuarek race 2, face/hair 00",
                       "npc_spawns": r["spawns"], "hud": hud_report, "hud_sources": assets.sources}
provenance["omissions"] = [s for s in provenance["omissions"] if "both player and NPC" not in s]
(root / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
print(main.cook(root, into / "packages/ko-field"))
