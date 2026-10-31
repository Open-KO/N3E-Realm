#!/usr/bin/env python3
"""Validate source packages and publish deterministic, immutable cooked releases."""
import pathlib, re, shutil, sys, tempfile
from common import *
import gltf
import world_chunks
import world_textures
import world_overlay
import rules
import camera
import melee
import damage
import npc
import npc_looks
import attachments
import life
import animation
import progression
import editing
import inventory
import commerce
import repair
import equipment
import stats
import wear
import storage
import storage_auth
import friends
import party
import exploration
import appearance
import rest
import combat_animation
import ranged_attack
import consumables
import skills
import input_map
import pick
import postprocess
import item_heads


def heightfield_triangles(hf):
    """The terrain surface a heightfield cooks to, in package coordinates.

    How each grid quad is split into two triangles. "fixed" keeps the original
    single diagonal; "alternating" splits by (x + z) % 2, which is what KO
    terrain does (`CN3Terrain::GetHeight` FUN_0059d330 tests
    `(ix + iz) & 0x80000001`, and `CN3TerrainPatch::Tick` FUN_005a0410 fans each
    tile from the matching corner). "alternating-mirrored" is the same rule with
    the opposite phase, for a heightfield whose grid mirrors one of the
    reference's axes: mirroring inverts the parity as well as the winding.
    Visuals and collision must use the same convention or the surface a player
    sees is not the one they stand on.
    """
    width, depth, spacing = hf["width"], hf["depth"], hf["spacing"]
    origin, heights = hf["origin"], hf["heights"]
    diagonal = hf.get("diagonal", "fixed")
    pts = [
        [
            origin[0] + x * spacing,
            origin[1] + heights[z * width + x],
            origin[2] + z * spacing,
        ]
        for z in range(depth)
        for x in range(width)
    ]
    phase = 1 if diagonal == "alternating-mirrored" else 0
    triangles = []
    for z in range(depth - 1):
        for x in range(width - 1):
            i = z * width + x
            a, b, c, d = pts[i], pts[i + width], pts[i + 1], pts[i + width + 1]
            if diagonal != "fixed" and (x + z + phase) % 2:
                # Split along the other diagonal, keeping the same winding.
                triangles.extend([a, b, d, a, d, c])
            else:
                triangles.extend([a, b, c, c, b, d])
    return triangles


# PQ-215 collision encodings. A package whose heightfield and triangles fit
# N3C1 (129 samples a side, 196,608 vertices) still cooks to the same N3C1
# bytes, so its release identity is unchanged; a larger one cooks to N3C2: the
# heightfield carried natively and the object triangles as a list the readers
# index in a uniform grid. A package with an N3W2 world always cooks to N3C2
# (PQ-235, D-160): the client's target marker on a streamed world follows that
# native heightfield.
COLLISION_MAX_SAMPLES = 513
N3C1_SAMPLES = 129
N3C1_POINTS = 196608
N3C2_MAX_EXTENT = 4096
N3C2_MAX_OBJECT_POINTS = 393216
DIAGONALS = ("fixed", "alternating", "alternating-mirrored")
# Spec 11: front-end.bin carries two character models and the UI art, so it
# has its own bound (client/assets/assets.cpp kFrontEndFile).
FRONT_END_FILE = 64 * 1024 * 1024


def nondegenerate(points):
    for i in range(0, len(points), 3):
        a, b, c = points[i : i + 3]
        ab = [b[k] - a[k] for k in range(3)]
        ac = [c[k] - a[k] for k in range(3)]
        cross = [
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        ]
        if sum(x * x for x in cross) < 1e-12:
            raise ValueError("degenerate collision")


def collision_bytes(hf, objects, native=False):
    """collision.bin for a validated heightfield and object vertex list; N3C2
    whenever `native`."""
    width, depth, spacing = hf["width"], hf["depth"], hf["spacing"]
    terrain_points = (width - 1) * (depth - 1) * 6
    if not native and width <= N3C1_SAMPLES and depth <= N3C1_SAMPLES and terrain_points + len(objects) <= N3C1_POINTS:
        triangles = heightfield_triangles(hf) + list(objects)
        count(len(triangles), N3C1_POINTS)
        for p in triangles:
            vector(p, 3)
        nondegenerate(triangles)
        return b"N3C1" + u(len(triangles)) + b"".join(f(p) for p in triangles)
    origin = hf["origin"]
    stored = struct.unpack("<f", struct.pack("<f", spacing))[0]
    extent = [(width - 1) * stored, (depth - 1) * stored]
    if max(extent) > N3C2_MAX_EXTENT or any(
        abs(o + e) > 1e6 for o, e in zip((origin[0], origin[2]), extent)
    ):
        raise ValueError("heightfield extent")
    # A terrain triangle's cross product has |y| = spacing squared.
    if spacing**4 < 1e-12:
        raise ValueError("degenerate collision")
    absolute = [origin[1] + h for h in hf["heights"]]
    vector(absolute, len(absolute))
    count(len(objects), N3C2_MAX_OBJECT_POINTS, 0)
    for p in objects:
        vector(p, 3)
    nondegenerate(objects)
    return (
        b"N3C2"
        + u(width)
        + u(depth)
        + f([origin[0], origin[2], spacing])
        + u(DIAGONALS.index(hf.get("diagonal", "fixed")))
        + f(absolute)
        + u(len(objects))
        + b"".join(f(p) for p in objects)
    )


def cook(root, out, materials=False):
    """Cooks the package at `root` into `out`. `materials` lets the scene's
    glTF carry N3SM render states and further joint influence sets
    (gltf.cook): only ko_npc_looks passes it, for the throwaway package whose
    scene.bin is a looks clip (PQ-265, PQ-283)."""
    manifest = load(root / "package.json")
    if set(manifest) - {"attachments", "npc_looks", "input", "pick", "postprocess", "item_heads", "skills", "consumables", "combat_animation", "ranged_attack", "rest", "appearance", "party", "friends", "storage_auth", "storage", "wear", "stats", "equipment", "repair", "commerce", "inventory", "render_detail", "exploration", "editing", "world", "world_textures", "world_overlay", "presentation", "camera", "melee", "damage", "npc", "life", "animation", "progression"} != set(
        [
            "game_id",
            "package_version",
            "content_schema_version",
            "engine_version",
            "protocol_version",
            "assets",
            "properties",
            "gameplay",
        ]
    ):
        raise ValueError("manifest keys")
    game = manifest["game_id"]
    if not re.fullmatch("[a-z][a-z0-9_-]{0,31}", game):
        raise ValueError("game namespace")
    if manifest["engine_version"] >= 10 and "life" not in manifest:
        raise ValueError("loot requires durable requested life policy")
    if "editing" in manifest and not {"life", "progression"} <= manifest.keys():
        raise ValueError("editing requires life and progression")
    if "world" in manifest and "editing" not in manifest:
        raise ValueError("world assets require the engine 11 editing contract")
    if "exploration" in manifest and not {"world", "editing"} <= manifest.keys():
        raise ValueError("exploration requires world and editing")
    if "inventory" in manifest and not {"editing", "life", "progression"} <= manifest.keys():
        raise ValueError("inventory requires editing/life/progression")
    if "commerce" in manifest and "inventory" not in manifest: raise ValueError("commerce requires inventory")
    if "repair" in manifest and "commerce" not in manifest: raise ValueError("repair requires commerce")
    if "equipment" in manifest and "repair" not in manifest: raise ValueError("equipment requires repair")
    if "stats" in manifest and not {"equipment","damage"} <= manifest.keys(): raise ValueError("stats requires equipment/damage")
    if ("stats" in manifest) != (manifest.get("progression",{}).get("stat_policy")=="equipment_v1"): raise ValueError("stats policy mismatch")
    if "friends" in manifest and "editing" not in manifest: raise ValueError("friends requires the durable editing/life/progression foundation")
    if "party" in manifest and "editing" not in manifest: raise ValueError("party requires the durable editing/life/progression foundation")
    if "storage_auth" in manifest and "storage" not in manifest: raise ValueError("storage auth requires storage")
    if "storage" in manifest and "wear" not in manifest: raise ValueError("storage requires wear")
    if "wear" in manifest and "stats" not in manifest: raise ValueError("wear requires stats")
    item_drops = manifest.get('progression',{}).get('model') == 'contribution_items_v5'
    coins = manifest.get('progression',{}).get('model') in ('contribution_drops_v4','contribution_items_v5')
    party_loot = manifest.get('progression',{}).get('model') in ('contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5')
    if coins and ('inventory' not in manifest or manifest['progression'].get('coins',{}).get('currency')!=manifest['inventory']['currency'] or manifest['inventory']['currency_limit']>2100000000):raise ValueError('coin drops require matching inventory currency')
    party_rewards = manifest.get('progression',{}).get('model') in ('contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5')
    if party_rewards and 'party' not in manifest: raise ValueError('party rewards require party membership')
    if item_drops:
        definitions={i['id']:i for i in manifest['inventory']['items']}
        for i in manifest['progression']['items']['items']:
            if i['id'] not in definitions or i['quantity']>definitions[i['id']]['stack_limit'] or i['durability']!=definitions[i['id']]['durability']:raise ValueError('drop inventory definition')
    if 'appearance' in manifest and not {'equipment', 'render_detail'} <= manifest.keys():
        raise ValueError('appearance requires equipment and render detail')
    # PQ-328 (D-186): attached characters ride on appearance keys.
    if 'attachments' in manifest and 'appearance' not in manifest:
        raise ValueError('attachments require appearance')
    if "consumables" in manifest and ("inventory" not in manifest or "upper_nodes" not in manifest.get("combat_animation",{})):
        raise ValueError("consumables require inventory and current combat presentation")
    templated_npc = manifest.get("npc", {}).get("model") == "reference_templates_v3"
    reference_npc = manifest.get("npc", {}).get("model") == "reference_melee_v2" or templated_npc
    if reference_npc:
        if "life" not in manifest:
            raise ValueError("reference npc slots require requested life policy")
        slots = manifest["npc"].get("slots")
        if not isinstance(slots, list) or any(
            not isinstance(slot, dict) or manifest["life"]["npc_corpse_ticks"] > slot.get("respawn_ticks", 0) for slot in slots
        ):
            raise ValueError("reference npc slot respawn must not precede corpse removal")
    # PQ-253 (D-166): per-template NPC models need templates; engine 38 keeps wire 30.
    if "npc_looks" in manifest and not templated_npc:
        raise ValueError("npc looks require npc templates")
    # PQ-317 (D-187): an engine 38+ package (attachments) with templates
    # carries their looks table, as both readers require.
    if "attachments" in manifest and templated_npc and "npc_looks" not in manifest:
        raise ValueError("attachments with npc templates require npc looks")
    # PQ-272 (D-179): a drawn scale per template (N3N4) is engine 41 and scales
    # the template's looks model, so it needs the looks table.
    scaled_npc = templated_npc and npc.scaled(manifest["npc"])
    if scaled_npc and "npc_looks" not in manifest:
        raise ValueError("npc scale requires npc looks")
    # PQ-317 (D-187): attachments are engine 38+, which is wire 30 with or
    # without NPC templates; so is the front end (spec 11, engine 42).
    front_end = "front-end.bin" in manifest.get("presentation", {})
    compatibility = 30 if templated_npc or "attachments" in manifest or front_end else 29 if reference_npc else 28 if "skills" in manifest else 26 if "consumables" in manifest else 25 if 'upper_nodes' in manifest.get('combat_animation',{}) else 24 if 'combat_animation' in manifest else 23 if 'rest' in manifest else 22 if 'appearance' in manifest else 21 if item_drops else 20 if coins else 19 if party_loot else 18 if party_rewards else 17 if "party" in manifest else 16 if "friends" in manifest else 15 if "storage_auth" in manifest else 14 if "storage" in manifest else 13 if "wear" in manifest else 12 if "stats" in manifest else 11 if "equipment" in manifest else 10 if "repair" in manifest else 9 if "commerce" in manifest else 8 if "inventory" in manifest else 7 if "exploration" in manifest else 6 if "editing" in manifest else (5 if manifest["engine_version"] >= 10 else 4) if "progression" in manifest else 3 if "life" in manifest else 2 if "movement" in manifest["gameplay"] else 1
    if any(
        type(manifest[k]) is not int or manifest[k] != value
        for k, value in [
            ("content_schema_version", 1),
            (
                "engine_version",
                max(
                    # PQ-328 (D-186): attachment models are looks models, so a
                    # package with attachments is at least the engine they need.
                    attachments.engine(manifest["attachments"], root) if "attachments" in manifest else 0,
                    # Spec 11: the KO front end (front-end.bin, N3FE) is engine 42.
                    42 if "front-end.bin" in manifest.get("presentation", {}) else 0,
                    # PQ-265 (D-173): N3MM looks models (render states) are engine 39;
                    # PQ-283 (D-176): N3NI / N3MI (influence tables) engine 40;
                    # PQ-272 (D-179): N3N4 templates (a drawn scale) engine 41.
                    41 if scaled_npc else
                    npc_looks.engine(manifest["npc_looks"], root) if "npc_looks" in manifest else
                    37 if templated_npc else
                    36 if reference_npc else
                    35 if "skills" in manifest else
                    33 if "consumables" in manifest else
                    32 if "upper_nodes" in manifest.get("combat_animation",{}) else
                    31 if "combat_animation" in manifest else
                    30 if "rest" in manifest else
                    29 if "appearance" in manifest else
                    28 if item_drops else
                    27 if coins else
                    26 if party_loot else
                    25 if party_rewards else
                    24 if "party" in manifest else
                    23 if "friends" in manifest else
                    22 if "storage_auth" in manifest else
                    21 if "storage" in manifest else
                    20 if "wear" in manifest else
                    19 if "stats" in manifest else
                    18 if "equipment" in manifest else
                    17 if "repair" in manifest else
                    16 if "commerce" in manifest else
                    15 if "inventory" in manifest else
                    14 if "render_detail" in manifest else
                    13 if "exploration" in manifest else
                    12 if "world" in manifest else
                    11 if "editing" in manifest else (10 if manifest["engine_version"] >= 10 else 9) if "progression" in manifest else 8 if "animation" in manifest else 7 if "life" in manifest else 6 if "npc" in manifest else 5
                    if "damage" in manifest
                    else (
                        4
                        if "melee" in manifest
                        else 3 if "camera" in manifest else compatibility
                    )
                ),
            ),
            ("protocol_version", compatibility),
        ]
    ):
        raise ValueError("incompatible schema/engine/protocol")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest["package_version"]):
        raise ValueError("package version")
    assets = manifest["assets"]
    count(len(assets), 256)
    ids = {a["id"] for a in assets}
    if len(ids) != len(assets) or any(
        not re.fullmatch(re.escape(game) + r":[a-z][a-z0-9_/-]{0,95}", i) for i in ids
    ):
        raise ValueError("asset namespace/duplicate")
    byid = {a["id"]: a for a in assets}

    def walk(i, seen):
        if i in seen:
            raise ValueError("dependency cycle")
        for d in byid[i]["dependencies"]:
            if d not in ids:
                raise ValueError("missing dependency")
            walk(d, seen | {i})

    for i in ids:
        walk(i, set())
    # Phase 1 has one rendered scene; declaring additional assets cannot silently drop them.
    if len(assets) != 1:
        raise ValueError("one scene asset per foundation release")
    a = assets[0]
    if set(a) != set(["id", "source", "metadata", "dependencies"]) or a["dependencies"]:
        raise ValueError("scene asset fields")
    meta = load(safe(root, a["metadata"]))
    if set(meta) != set(
        ["instance_scale", "attachment_node", "heightfield", "triangles", "markers"]
    ):
        raise ValueError("scene metadata")
    for marker in meta["markers"]:
        if (
            set(marker) != set(["name", "time"])
            or not re.fullmatch("[a-z][a-z0-9_]{0,31}", marker["name"])
            or not 0 <= marker["time"] <= 3600
        ):
            raise ValueError("marker")
    count(len(meta["markers"]), 256, 0)
    props = manifest["properties"]
    count(len(props), 128, 0)
    keys = set()
    for p in props:
        if set(p) != set(
            [
                "key",
                "type",
                "scope",
                "min",
                "max",
                "capability",
                "persistence",
                "activation",
                "schema_version",
            ]
        ):
            raise ValueError("property fields")
        if (
            not re.fullmatch(re.escape(game) + r":[a-z][a-z0-9_.]{0,95}", p["key"])
            or p["key"] in keys
        ):
            raise ValueError("property namespace")
        keys.add(p["key"])
        if (
            p["type"] != "number"
            or p["scope"] not in ["realm", "zone"]
            or p["min"] > p["max"]
            or p["capability"] not in ["world.edit", "config.edit"]
            or p["persistence"] != "durable"
            or p["activation"] not in ["next_tick", "next_spawn", "restart"]
            or p["schema_version"] != 1
        ):
            raise ValueError("property policy")
    scene, deps = gltf.cook(root, a["source"], meta, materials)
    deps[a["metadata"]] = digest(canonical(meta)).hex()
    hf = meta["heightfield"]
    if set(hf) - {"diagonal"} != {"width", "depth", "origin", "spacing", "heights"}:
        raise ValueError("heightfield fields")
    width = count(hf["width"], COLLISION_MAX_SAMPLES, 2)
    depth = count(hf["depth"], COLLISION_MAX_SAMPLES, 2)
    heights = hf["heights"]
    origin = vector(hf["origin"], 3)
    spacing = hf["spacing"]
    diagonal = hf.get("diagonal", "fixed")
    if diagonal not in DIAGONALS:
        raise ValueError("heightfield diagonal")
    if (
        type(spacing) not in [int, float]
        or not 0 < spacing <= 100
        or len(heights) != width * depth
    ):
        raise ValueError("heightfield")
    objects = []
    for tri in meta["triangles"]:
        if len(tri) != 3:
            raise ValueError("triangle")
        objects.extend(tri)
    # An N3W2 world (PQ-231) carries its own parts, so its exploration policy
    # names no separate world-lod.bin; it needs the policy's fog distance.
    world_data = read(safe(root, manifest["world"]), world_chunks.MAX_FILE) if "world" in manifest else None
    # N3W3 (PQ-379, D-201) is N3W2 with alpha parts; N3W4 (PQ-382, D-202)
    # N3W3 with the opaque part bits; N3W5 (PQ-388, D-203) N3W4 with
    # single-layer unlit vertices; N3W6 (PQ-394, D-212) N3W5 with texture
    # sequences.
    chunked = world_data is not None and world_data[:4] in world_chunks.MAGICS
    collision = collision_bytes(hf, objects, native=chunked)
    extras = {}
    if "render_detail" in manifest:
        if not {"exploration", "presentation"} <= manifest.keys(): raise ValueError("detail requires world and player")
        data=read(safe(root,manifest["render_detail"]),128*1024*1024)
        # N3D3 (PQ-348, D-191): N3D2 with a render state per appearance entry.
        if data[:4] not in ((b"N3D2",b"N3D3") if "appearance" in manifest else (b"N3D1",)):raise ValueError("render detail magic")
        extras["render-detail.bin"]=data
        deps[manifest["render_detail"]]=digest(data).hex()
    if "rest" in manifest:
        if "appearance" not in manifest or len(manifest.get("animation",[]))!=14:raise ValueError("rest requires full presentation")
        extras["rest.bin"]=rest.cook(manifest["rest"])
    if "consumables" in manifest:
        extras["consumables.bin"]=consumables.cook(manifest["consumables"],manifest["inventory"])
    if "combat_animation" in manifest:
        if "rest" not in manifest:raise ValueError("combat animations require rest presentation")
        policy=manifest["combat_animation"]
        extras["combat-animation.bin"]=combat_animation.cook(policy,manifest['inventory'],manifest['equipment'])
        total=0
        for i,clip in enumerate(policy['clips']):
            data=read(safe(root,clip['source']))
            if data[:4]!=b'N3S1':raise ValueError('combat clip magic')
            total+=len(data)
            if total>combat_animation.MAX_BYTES:raise ValueError('combat clip byte budget')
            extras[combat_animation.filename(i)]=data;deps[clip['source']]=digest(data).hex()
    # PQ-416 (D-216): ranged basic attacks name N3A5 profiles and add to the
    # melee radii, so they need both; the server and the client read the file.
    if "ranged_attack" in manifest:
        extras["ranged-attack.bin"]=ranged_attack.cook(manifest["ranged_attack"],manifest.get("combat_animation"),manifest.get("melee"),manifest.get("inventory"),manifest.get("wear"))
    if "skills" in manifest:
        if "consumables" not in manifest:raise ValueError('skills require current combat capabilities')
        policy=manifest['skills'];known={i['id'] for i in manifest['inventory']['items']}
        if not policy['archetype'].startswith(game+':') or any(not s['id'].startswith(game+':') or any(w not in known for w in s['weapons']) for s in policy['skills']):raise ValueError('skill references')
        extras['skills.bin']=skills.cook(policy)
        for i in sorted({s['animation'] for s in manifest['skills']['skills']}):
            name=f'player-skill-{i}.bin';data=read(root/name)
            if data[:4]!=b'N3S1':raise ValueError('skill clip magic')
            extras[name]=data;deps[name]=digest(data).hex()
    if "appearance" in manifest:
        extras["appearance.bin"]=appearance.cook(manifest["appearance"],manifest["equipment"])
    if "attachments" in manifest:
        attached, sources = attachments.cook(
            manifest["attachments"], root, manifest["appearance"], manifest["equipment"],
            len(manifest.get("combat_animation", {}).get("clips", [])),
            {s["animation"] for s in manifest.get("skills", {}).get("skills", [])})
        extras.update(attached)
        deps.update(sources)
    if "progression" in manifest:
        extras["progression.bin"] = progression.cook(manifest["progression"], manifest["gameplay"], game)
    if "animation" in manifest:
        extras["animation.bin"] = animation.cook(manifest["animation"])
        if set(manifest.get("presentation", {})) - {"loot-model.bin", "loot-policy.bin", "target-marker.bin", "effects.bin", "audio.bin", "front-end.bin"} != set(animation.names(len(manifest["animation"]))) | {"hud.bin"}:
            raise ValueError("animation requires matching complete clip sets")
    if "life" in manifest:
        extras["life.bin"] = life.cook(manifest["life"])
    if "npc" in manifest:
        extras["npc.bin"] = npc.cook(manifest["npc"], manifest["gameplay"].get("spawns"), game)
    if "npc_looks" in manifest:
        looks, sources = npc_looks.cook(manifest["npc_looks"], root, game, manifest["npc"]["templates"])
        extras.update(looks)
        deps.update(sources)
    if "damage" in manifest:
        extras["damage.bin"] = damage.cook(manifest["damage"])
    if "melee" in manifest:
        extras["melee.bin"] = melee.cook(manifest["melee"])
    if "camera" in manifest:
        extras["camera.bin"] = camera.cook(manifest["camera"])
    if chunked and "exploration" not in manifest:
        raise ValueError("N3W2 world requires exploration")
    if "exploration" in manifest:
        extras["exploration.bin"] = exploration.cook(manifest["exploration"], lod=not chunked)
        if not chunked:
            lod = manifest["exploration"]["lod"]
            data = read(safe(root, lod))
            if data[:4] not in (b'N3L1',b'N3L2',b'N3L3',b'N3L4',b'N3L5'): raise ValueError('world LOD magic')
            extras['world-lod.bin'] = data
            deps[lod] = digest(data).hex()
    if "input" in manifest:
        extras["input.bin"] = input_map.cook(manifest["input"])
    if "pick" in manifest:
        extras["pick.bin"] = pick.cook(manifest["pick"])
    # PQ-316 (D-185): the screen post-process (bloom and tone map) is client
    # presentation, so it needs the presentation assets and engine 33 like
    # effects.bin; the server checks its bounds and otherwise ignores it.
    if "postprocess" in manifest:
        if manifest["engine_version"] < 33 or "presentation" not in manifest:
            raise ValueError("postprocess compatibility")
        extras["postprocess.bin"] = postprocess.cook(manifest["postprocess"])
    # PQ-354 (D-194): item tooltip heads are client presentation over the
    # inventory's items, so they need the presentation assets, engine 33 and the
    # inventory; the server checks them and otherwise ignores them.
    if "item_heads" in manifest:
        if manifest["engine_version"] < 33 or "presentation" not in manifest or "inventory" not in manifest:
            raise ValueError("item heads compatibility")
        extras["item-heads.bin"] = item_heads.cook(manifest["item_heads"], game, manifest["inventory"])
    if "friends" in manifest:
        extras["friends.bin"] = friends.cook(manifest["friends"])
    if "party" in manifest:
        extras["party.bin"] = party.cook(manifest["party"])
    if "storage_auth" in manifest:
        extras["storage-auth.bin"] = storage_auth.cook(manifest["storage_auth"])
    if "storage" in manifest:
        extras["storage.bin"] = storage.cook(manifest["storage"],game)
    if "wear" in manifest:
        extras["wear.bin"] = wear.cook(manifest["wear"],manifest["equipment"])
    if "stats" in manifest:
        extras["stats.bin"] = stats.cook(manifest["stats"],manifest["inventory"],manifest["equipment"],game)
    if "equipment" in manifest:
        extras["equipment.bin"] = equipment.cook(manifest["equipment"],manifest["inventory"],game)
    if "repair" in manifest:
        extras["repair.bin"] = repair.cook(manifest["repair"],manifest["inventory"])
    if "commerce" in manifest:
        extras["commerce.bin"] = commerce.cook(manifest["commerce"],game,manifest["inventory"],manifest["gameplay"]["item"])
    if "inventory" in manifest:
        extras["inventory.bin"] = inventory.cook(manifest["inventory"], game, manifest["gameplay"]["item"], manifest["gameplay"]["slots"])
    if "world" in manifest:
        # The static world asset: the package's visible map geometry and its own
        # atlas, in one buffer the client uploads once. Hashed as a dependency
        # like any other input, so release identity is unchanged in kind.
        # N3W2 (PQ-231, D-159) is the chunked encoding for worlds that do not
        # fit N3W1; it has its own, larger fixed bound.
        data = world_data
        if data[:4] not in (b"N3W1",) + world_chunks.MAGICS or (data[:4] == b"N3W1" and len(data) > MAX_WORLD_FILE):
            raise ValueError("world asset is not N3W1, N3W2, N3W3, N3W4, N3W5 or N3W6")
        extras["world.bin"] = data
        deps[manifest["world"]] = digest(data).hex()
    # An N3W2 world's textures are their own asset (PQ-233): required with N3W2,
    # refused otherwise, checked as the client checks it, and its texture count
    # must be the one the world's header names.
    if ("world_textures" in manifest) != chunked:
        raise ValueError("world textures pair with an N3W2 world")
    if chunked:
        data = read(safe(root, manifest["world_textures"]), world_textures.MAX_FILE)
        texture_count, _, _ = world_textures.check(data)
        if len(world_data) < 8 or struct.unpack_from("<I", world_data, 4)[0] != texture_count:
            raise ValueError("world texture count differs from the N3W2 world")
        extras["world-textures.bin"] = data
        deps[manifest["world_textures"]] = digest(data).hex()
    # PQ-387 (D-204): maps blended over the near terrain around the eye (N3WO).
    # Client data over the world's terrain policy: it needs the world and
    # exploration, and its block grid must cover the policy's patches.
    if "world_overlay" in manifest:
        if "world" not in manifest or "exploration" not in manifest:
            raise ValueError("world overlay requires a world and exploration")
        data = read(safe(root, manifest["world_overlay"]), world_overlay.MAX_FILE)
        header, _ = world_overlay.check(data)
        policy = world_data if chunked else extras["world-lod.bin"]
        at = 28 if chunked else 4
        # N3W2..N3W6 flag their policy; N3L3..N3L5 always carry one (ko_lod).
        if (struct.unpack_from("<I", policy, 24)[0] != 1 if chunked
                else policy[:4] not in (b"N3L3", b"N3L4", b"N3L5")):
            raise ValueError("world overlay requires a terrain policy")
        patches = struct.unpack_from("<I", policy, at + 32)[0]
        if header["width"] * header["block_tiles"] != patches * header["patch_tiles"]:
            raise ValueError("world overlay grid differs from the terrain policy")
        extras["world-overlay.bin"] = data
        deps[manifest["world_overlay"]] = digest(data).hex()
    if "presentation" in manifest:
        presentation = manifest["presentation"]
        expected = {
            "player-idle.bin",
            "player-walk.bin",
            "player-attack.bin",
            "player-death.bin",
            "hud.bin",
        }
        if isinstance(presentation, dict) and "player-ready.bin" in presentation:
            if "melee" not in manifest:
                raise ValueError("ready pose requires melee")
            expected.add("player-ready.bin")
        if "animation" in manifest and len(manifest["animation"]) in (11,14):
            expected |= {name for name in animation.NAMES if name.startswith("npc-")}
        if "rest" in manifest:expected |= {f"player-{s}.bin" for s in animation.REST_STATES}
        if isinstance(presentation,dict) and "loot-model.bin" in presentation:
            if manifest['engine_version']<10 or 'progression' not in manifest:raise ValueError('loot model requires durable loot')
            expected.add('loot-model.bin')
        if isinstance(presentation,dict) and "loot-policy.bin" in presentation:
            if 'loot-model.bin' not in presentation:raise ValueError('loot policy requires loot model')
            expected.add('loot-policy.bin')
        if isinstance(presentation,dict) and "target-marker.bin" in presentation:
            if manifest['engine_version']<33 or 'melee' not in manifest:raise ValueError('target marker compatibility')
            expected.add('target-marker.bin')
        if isinstance(presentation,dict) and "effects.bin" in presentation:
            if manifest['engine_version']<33:raise ValueError('effects compatibility')
            expected.add('effects.bin')
        if isinstance(presentation,dict) and "audio.bin" in presentation:
            if manifest['engine_version']<33:raise ValueError('audio compatibility')
            expected.add('audio.bin')
        if isinstance(presentation,dict) and "front-end.bin" in presentation:
            # Spec 11: KO's login, select, create and loading screens; its
            # models are the player's, so it needs the full presentation.
            if 'appearance' not in manifest:raise ValueError('front end requires appearance')
            expected.add('front-end.bin')
        extended = expected | {"player-run.bin", "player-backward.bin"}
        if not isinstance(presentation, dict) or not (
            set(presentation) == expected
            or ("movement" in manifest["gameplay"] and set(presentation) == extended)
        ):
            raise ValueError("presentation asset set")
        for name, source in presentation.items():
            data = read(safe(root, source), FRONT_END_FILE if name == "front-end.bin" else MAX_FILE)
            if name=='loot-policy.bin':
                if len(data)!=8 or data[:4]!=b'N3LP':raise ValueError('loot policy format')
                radius=struct.unpack('<f',data[4:])[0]
                if not math.isfinite(radius) or not 0<radius<=100:raise ValueError('loot open radius')
                extras[name]=data;deps[source]=digest(data).hex();continue
            if data[:4] not in ((b"N3H1", b"N3H2", b"N3H3", b"N3H4", b"N3H5", b"N3H6", b"N3H7", b"N3H8", b"N3H9", b"N3HA", b"N3HB", b"N3HC", b"N3HD", b"N3HE") if name == "hud.bin" else (b"N3TM",) if name == "target-marker.bin" else (b"N3EF", b"N3E2", b"N3E3", b"N3E4", b"N3E5") if name == "effects.bin" else (b"N3AU", b"N3A2") if name == "audio.bin" else (b"N3FE",) if name == "front-end.bin" else (b"N3S1",)):
                raise ValueError("presentation magic")
            extras[name] = data
            deps[source] = digest(data).hex()
    # Canonical source manifest is part of identity; metadata floats use Python's
    # shortest finite binary64 round-trip spelling (format version 1).
    recipe = canonical({"manifest": manifest, "sources": deps, "cooker_version": 1})
    files = {
        "scene.bin": scene,
        "collision.bin": collision,
        "recipe.json": recipe,
        "gameplay.bin": rules.cook(manifest["gameplay"], game, "melee" in manifest),
    }
    files.update(extras)
    if "editing" in manifest:
        files["editing.bin"] = editing.cook(manifest)
    if any(
        len(data) > (128*1024*1024 if name == "render-detail.bin" else
                     FRONT_END_FILE if name == "front-end.bin" else
                     (world_chunks.MAX_FILE if data[:4] in world_chunks.MAGICS else MAX_WORLD_FILE) if name == "world.bin" else
                     world_textures.MAX_FILE if name == "world-textures.bin" else
                     world_overlay.MAX_FILE if name == "world-overlay.bin" else MAX_FILE)
        for name, data in files.items()
    ):
        raise ValueError("cooked file exceeds its size bound")
    # Both readers take at most 256 files (PQ-253: one model per NPC looks).
    if len(files) > 256:
        raise ValueError("release file count")
    index = (
        b"N3R1"
        + u(1)
        + u(manifest["engine_version"])
        + u(manifest["protocol_version"])
        + string(game)
        + string(manifest["package_version"])
        + u(len(files))
    )
    for name, data in sorted(files.items()):
        index += string(name) + u(len(data)) + digest(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        tmp = pathlib.Path(td)
        for name, data in files.items():
            (tmp / name).write_bytes(data)
        (tmp / "release.bin").write_bytes(index)
        (tmp / "release.sha256").write_text(digest(index).hex() + "\n")
        # Never publish a partially cooked package after a validation error.
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(tmp, out)
    return digest(index).hex()


if __name__ == "__main__":
    try:
        print(cook(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])))
    except (
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        OSError,
        struct.error,
        OverflowError,
    ) as e:
        sys.exit("assetc rejected: " + str(e))
