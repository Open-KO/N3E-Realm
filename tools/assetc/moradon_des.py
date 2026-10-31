#!/usr/bin/env python3
"""Demon's Souls characters on the KO Moradon feature map (exploration).

Applied by `ko_bake.py --features --des` after the Moradon features, writing a
separate package (build/packages/moradon-des) so the Moradon demo is untouched.
Everything Demon's Souls comes from the user's own dump through
`demons_souls.py`; nothing extracted is committed.

The enemy: Moradon's reference worm slots keep their placement, AI and rules,
but are drawn with the Demon's Souls soldier (c2010) and its decoded clips.
Attack pacing and corpse time follow the soldier's clip lengths.

The player: the Demon's Souls player skeleton (c0000) in armour 8100 with its own
clips for every presentation state (locomotion, rest, combat profiles, skills).
The render detail keeps Moradon's world textures and replaces the character: the
body with one texture slot per armour part, and the equipment appearances with
Demon's Souls weapons, shield and armour 8010. Every mesh and clip shares one skin
joint list.
"""
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gltf  # noqa: E402

SOLDIER = ("c2010", {"idle": "a00_0000", "walk": "a00_0200", "attack": "a00_3000", "death": "a00_2200"},
           {"c2010_body", "HD_F_8000_L", "WP_A_1509_L_shield", "WP_A_0700_L_short_spear"})
NPC_FIRST = 10          # the 14 clips are 7 player, 3 rest, then npc idle/walk/attack/death


def apply_enemy(root, manifest):
    import demons_souls
    demons_souls.ensure_usrdir(("chr",))
    char, clips, textures = SOLDIER
    out = root / "des-npc"
    results, triangles, height = demons_souls.package(char, clips, out, textures)
    scale = round(1.8 / height, 4)
    for state in clips:
        cooked, _ = gltf.cook(root, f"des-npc/npc-{state}.gltf", {"instance_scale": [scale] * 3, "attachment_node": 0})
        (root / f"npc-{state}.bin").write_bytes(cooked)
    for k, state in enumerate(clips):
        manifest["animation"][NPC_FIRST + k] = {
            "duration": results[state][0], "blend": .2, "loop_blend": False,
            "markers": [results[state][1], -1] if state == "attack" else [-1, -1]}
    # NPC clips must share the instanced scene's texture: the scene (and the editable
    # decoration) becomes the soldier too, keeping the map's collision metadata.
    manifest["assets"][0]["source"] = "des-npc/npc-idle.gltf"
    meta = json.loads((root / "scene.json").read_text())
    meta.update(instance_scale=[scale] * 3, attachment_node=0)
    for marker in meta.get("markers", []):
        marker["time"] = results["attack"][1]
    (root / "scene.json").write_text(json.dumps(meta))
    rules, life = manifest["gameplay"], manifest["life"]
    attack, death = results["attack"][0], results["death"][0]
    rules["npc_cooldown_ticks"] = max(rules["npc_cooldown_ticks"], math.ceil((attack + .2) * 20))
    life["npc_corpse_ticks"] = max(life["npc_corpse_ticks"], math.ceil((death + 2.5) * 20))
    life["npc_respawn_ticks"] = max(life["npc_respawn_ticks"], life["npc_corpse_ticks"])
    for slot in manifest.get("npc", {}).get("slots", []):
        slot["respawn_ticks"] = max(slot["respawn_ticks"], life["npc_corpse_ticks"])
    return {"enemy": char, "triangles": triangles, "scale": scale, "clips": results,
            "npc_cooldown_ticks": rules["npc_cooldown_ticks"], "npc_corpse_ticks": life["npc_corpse_ticks"]}


BASE = [f"{k}_m_8100" for k in ("hd", "bd", "am", "lg")]
ARMOR = [f"{k}_m_8010" for k in ("hd", "bd", "am", "lg")]
# Appearance rows follow games/moradon/appearance.json: blade (right), blade (left),
# shield (left), two-hander (right), armour.
PLUGS = {("demo:item/blade", 0): "wp_a_0200@R_Weapon", ("demo:item/blade", 1): "wp_a_0200@L_Weapon",
         ("demo:item/shield", 1): "wp_a_1510@L_Shield", ("demo:item/twohand", 0): "wp_a_0300@R_Weapon"}
STATES = {"idle": "a00_0000", "walk": "a00_0200", "attack": "a20_3000", "death": "a00_6010", "run": "a00_0300",
          "backward": "a00_0201", "ready": "a00_0001", "sit-down": "a00_8280", "sit-idle": "a00_8281",
          "stand-up": "a00_8282"}
READY, ATTACKS = "a00_0001", {"one": ("a20_3000", "a20_3001"), "two": ("a23_3000", "a23_3001")}
SKILLS = {0: "a00_8305", 1: "a20_3001"}       # tiny healing (a kneeling prayer), light strike


def _combat_clip(index, config):
    for profile in config["profiles"]:
        if index == profile["ready"]:
            return READY
        if index in profile["attacks"]:
            pair = ATTACKS["two" if profile["name"].startswith("two-hand") else "one"]
            return pair[profile["attacks"].index(index)]
    return ATTACKS["one"][0]                      # attacking while moving


def _chain(demons_souls, tex, size):
    chain, level = [], size
    while level >= 4:
        chain.append((level, level, demons_souls.texture_rgba(tex, level)))
        level //= 2
    return chain


def apply_player(root, manifest):
    import demons_souls
    import render_detail
    demons_souls.ensure_usrdir(("chr", "parts"))
    armor_rows = [row for row in json.loads(Path("games/moradon/appearance.json").read_text())]
    # One skin joint list for the body, the armour appearance and every carried part.
    union = set()
    for parts in [BASE, ARMOR] + [[plug] for plug in PLUGS.values()]:
        union |= set(demons_souls.weighted_joints(demons_souls.character("c0000", None, parts)))
    skin = sorted(union)
    if len(skin) > 64:
        raise ValueError("player skin exceeds 64 joints")

    # Clips: every player presentation state on the Demon's Souls skeleton.
    config = json.loads(Path("games/moradon/combat-animation.json").read_text())
    combat_sources = {c["source"]: c for c in manifest["combat_animation"]["clips"]}
    clips = dict(STATES)
    for source in combat_sources:
        index = int(source.rsplit("-", 1)[1].split(".")[0])
        clips[f"combat-{index}"] = _combat_clip(index, config)
    for index, clip in SKILLS.items():
        clips[f"skill-{index}"] = clip
    out = root / "des-player"
    results, triangles, _ = demons_souls.package("c0000", clips, out, None, "player", size=64, parts=BASE, skin_joints=skin)
    for key in clips:
        cooked, _ = gltf.cook(root, f"des-player/player-{key}.gltf", {"instance_scale": [1, 1, 1], "attachment_node": 0})
        (root / f"player-{key}.bin").write_bytes(cooked)
    order = ["idle", "walk", "attack", "death", "run", "backward", "ready", "sit-down", "sit-idle", "stand-up"]
    for k, state in enumerate(order):
        entry = manifest["animation"][k]
        entry.update(duration=results[state][0], blend=.2,
                     markers=[results[state][1], -1] if state == "attack" else [-1, -1])
    for source, entry in combat_sources.items():
        key = source[len("player-"):-len(".bin")]
        attack = clips[key] != READY
        entry.update(duration=results[key][0], markers=[results[key][1], -1] if attack else [-1, -1])
    doc = json.loads((out / "player-idle.gltf").read_text())
    names = [n["name"] for n in doc["nodes"]]
    parents = [-1] * len(names)
    for i, n in enumerate(doc["nodes"]):
        for child in n.get("children", []):
            parents[child] = i
    skin_nodes = set(doc["skins"][0]["joints"])      # the mask may only name skinned joints
    top, upper = names.index("Upper_Root"), []
    for i in range(len(parents)):              # Upper_Root and everything below it, fingers excepted
        k = i
        while k >= 0 and k != top:
            k = parents[k]
        if k == top and "Finger" not in names[i] and i in skin_nodes:
            upper.append(i)
    # The upper-body layer is a 64-bit node mask: the exporter orders finger bones last.
    if not (max(upper) < 64 and len(upper) <= 63):
        raise ValueError("upper-body nodes do not fit the 64-bit mask")
    manifest["combat_animation"]["upper_nodes"] = upper
    havok_names = demons_souls.havok.skeleton(demons_souls.animations("c0000")[1])[0]
    hand = {k: skin.index(havok_names.index(n)) for k, n in ((12, "R_Hand"), (7, "L_Hand"), (5, "L_Shield"))}
    for skill in manifest["skills"]["skills"]:
        skill["cast_joints"] = [hand.get(j, 0) for j in skill["cast_joints"]]
        if skill["target_joint"] > 0:
            skill["target_joint"] = hand.get(skill["target_joint"], 0)

    # Render detail: Moradon's world textures, then the Demon's Souls character.
    data = (root / "render-detail.bin").read_bytes()
    view = list(struct.unpack_from("<3f", data, 4))
    thresholds = [list(struct.unpack_from("<4f", data, 16 + 16 * r)) for r in range(4)]
    workload = list(struct.unpack_from("<3I", data, 80))
    world_count, _ = struct.unpack_from("<II", data, 92)
    at, textures = 100, []
    for _ in range(world_count):
        levels = struct.unpack_from("<I", data, at)[0]
        at += 4
        chain = []
        for _ in range(levels):
            w, h = struct.unpack_from("<II", data, at)
            chain.append((w, h, data[at + 8:at + 8 + w * h * 4]))
            at += 8 + w * h * 4
        textures.append(chain)

    def mesh(parts):
        c = demons_souls.character("c0000", None, parts, skin)
        position = {j: i for i, j in enumerate(skin)}
        vertices, indices, slots = [], [], {}
        for texture, tris in c["groups"].items():
            if texture not in c["textures"]:
                continue
            if texture not in slots:
                _, w, h, _ = c["textures"][texture]
                slots[texture] = len(textures)
                textures.append(_chain(demons_souls, c["textures"][texture], 512 if max(w, h) >= 512 else 256))
            remap = {}
            for tri in tris:
                for k in tri:
                    if k not in remap:
                        remap[k] = len(vertices)
                        joints = [position[j] if x > 0 else 0 for j, x in zip(c["jnt"][k], c["wgt"][k])]
                        vertices.append((c["pos"][k], c["nrm"][k], c["uv"][k], joints, c["wgt"][k], slots[texture]))
                    indices.append(remap[k])
        return (vertices, indices), slots, c
    body, body_slots, base = mesh(BASE)
    armor_slots = [body_slots[t] for t in body_slots if not t.startswith(("BD_M_body", "FC_M_"))]
    appearances = []
    for row in armor_rows:
        if row["item"] == "demo:item/armor":
            geometry, _, _ = mesh(ARMOR)
            appearances.append((armor_slots, [geometry] * 4))
        else:
            geometry, _, _ = mesh([PLUGS[(row["item"], row["slot"])]])
            appearances.append(([], [geometry] * 4))
    spans = [max(m[a][3] for m in base["world"]) - min(m[a][3] for m in base["world"]) for a in range(3)]
    radius = math.sqrt(sum((v + .5 if v < .5 else v) ** 2 for v in spans)) * .5
    payload = render_detail.serialize(view, thresholds, workload, world_count, textures, radius, [body] * 4,
                                      appearances=appearances)
    (root / "render-detail.bin").write_bytes(payload)
    return {"skin_joints": len(skin), "clips": {k: clips[k] for k in sorted(clips)}, "triangles": triangles,
            "upper_nodes": len(upper), "character_textures": len(textures) - world_count,
            "render_detail_bytes": len(payload)}


def apply(root, manifest):
    return {"enemy": apply_enemy(root, manifest), "player": apply_player(root, manifest)}
