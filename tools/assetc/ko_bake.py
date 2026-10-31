"""KO package assembly: one zone's map, the KO player, HUD and presentation.

The collision bake (KX-03) is `ko_collision` and the map's world presentation
`ko_scene.bake_world` (N3W1, or N3W2 + N3WT when the map does not fit; PQ-234);
`bake` is re-exported here for its existing callers.
"""

from common import *
import ko_shapes
import ko_terrain
from ko_collision import bake  # noqa: F401  (re-exported)


def zone_names(row, input_policy, zone_distance):
    """Set the input table's zone-dependent name rules from the package's Zones.tbl row.

    `row` is the package zone's CSV row (`ko_zone.select`, PQ-216); its column 1
    is the zone key (inferred to equal KO's runtime key, 0046c9d0: +0x89c x 10
    + +0x8a0; PQ-166). Returns the provenance entries.

    Party names beyond the camera limit (PQ-166): 0046ea90 skips the limit for
    a party member unless the row's column 23 (row offset 0xf4) is 0; a missing
    or non-integer value counts as 1.

    Other players' camera limit by zone (PQ-173): 0046ea90 compares with 33.0
    (006a4250) instead of 48.0 (006a40dc) when the zone key is 0x140; the self
    (0046b5a0) and NPC (00459820) callbacks never read the key. `zone_distance`
    (games/moradon/nameplates.json) maps a zone key to per-class limits that
    replace the style's `distance`; any other key leaves the style's.
    """
    try:zone_flag=int(row[22])
    except (IndexError,ValueError):zone_flag=1
    names=input_policy.get('names')
    zone_key=int(row[0])
    if names is not None and names.get('party') is not None:names['party']['beyond_distance']=zone_flag!=0
    limits=zone_distance.get(str(zone_key))
    if names is not None:
        if limits:names['distance']=dict(limits)
        else:names.pop('distance',None)
    return dict(party_names=dict(zone_key=zone_key,column_23=zone_flag,beyond_distance=zone_flag!=0),
                name_distance=dict(zone_key=zone_key,distance=dict(limits or {})))


def npc_names(looks, monster, input_policy):
    """Set the NPC name rule that depends on the package's NPC template.

    `looks` holds the NPC_Looks.tbl CSV rows (header first); `monster` is the
    package's K_MONSTER row (games/moradon/ko-reference.json), whose sPid names
    the looks row (the NPC-in packet's second short, read at 005cd699 and looked
    up in NPC_Looks at 005cdc58; that the server sends sPid there is a source
    name, PQ-174). Column 36 (row offset 0x14c, PQ-170) set to 1 keeps the NPC's
    name at any range and lifts the 48 m camera limit (00470baa, 00459856):
    `npc_lifetime.always`. A missing row or a non-integer value counts as 0 (a
    row that is not found gives KO no flag to read). Returns the provenance entry.
    """
    names = input_policy.get('names')
    pid = int(monster['sPid'])
    row = next((r for r in looks[1:] if r and r[0].strip() == str(pid)), None)
    try:
        flag = int(row[35]) if row is not None else 0
    except (IndexError, ValueError):
        flag = 0
    if names is not None and names.get('npc_lifetime') is not None:
        names['npc_lifetime']['always'] = flag == 1
    return dict(npc_names=dict(template=monster['sSid'], looks=pid, looks_row=row is not None,
                               column_36=flag, always=flag == 1))


def overview_map(zone, report):
    """The zone overview map for the HUD: the zone row's column 8 (ko_zone;
    00562b60 via 005ca842). KO u=x/W, v=1-z/W with W the terrain extent
    (005a3870) maps to n3e origin (-half,-half) and extent W."""
    import hashlib
    assets = pathlib.Path(zone["assets"])
    # Windows paths in the table are case-insensitive; ko_zone resolved the local file.
    overview = str(pathlib.Path(zone["minimap"]).relative_to(assets))
    return dict(path=overview, zone_key=int(zone["row"][0]),
                origin=[report["world_origin"][0], report["world_origin"][2]], extent=report["extent_metres"],
                sha256=hashlib.sha256((assets / overview).read_bytes()).hexdigest(),
                zones_table_sha256=hashlib.sha256(pathlib.Path(zone["table"]).read_bytes()).hexdigest())


def ko_scene_references(zone):
    """PQ-274: refuse a zone whose GTD or OPD names a file that is not there."""
    import ko_scene
    found = ko_scene.references(zone["gtd"], zone["opd"], pathlib.Path(zone["assets"]), zone.get("headerless", False),
                                zone.get("substitutes"))
    if found["missing"]:
        raise ValueError("zone %d names %d missing files under %s: %s" % (
            zone["key"], len(found["missing"]), zone["assets"], ", ".join(found["missing"])))
    return found


def package(source, zone, out, spawn=None, features=False, des=False, overview=False, start=None,
            character_assets=None, layout=None, glow=False):
    """Build a cookable package that carries one KO zone's map and a KO player.

    `zone` is `ko_zone.select`'s result: the GTD, TCT, OPD and minimap DXT its
    Zones.tbl row names, already checked as the client's world loader checks
    them. The feature data (start, NPCs, routes) is still Moradon's.

    The map is the package's `world` asset: terrain, tiles and every static
    placement in one static buffer with its own atlas (N3W1, with N3L3 as
    `world-lod.bin`). A map that does not fit N3W1 (above 129 samples a side,
    or past an N3W1 / N3L3 bound) is written as N3W2 with its textures as N3WT
    and no `world-lod.bin`; its collision then cooks to N3C2 (PQ-234, D-159). `scene.bin` stays the
    base package's instanced model, so the world's atlas never has to match a
    character's and the map is not constrained by an animated scene's budget.

    The player is the real male Tuarek from the local default-looks table, the
    same assembly `tools/play-demo --ko` uses, with the reference HUD. The NPC
    section is dropped: NPC clips must share the instanced scene's atlas, and
    there are no creatures on a map preview. Player metadata remains available.

    `overview` gives a package without the feature HUD the zone's overview map
    (Zones.tbl column 8) on the basic HUD (N3HE, PQ-217); the feature HUD always
    carries it (N3HD). `start` is the start survey's record for provenance.

    `character_assets` is the client data the player, HUD and render detail come
    from when it is not the map's (the 1097 homelands, PQ-274, D-170: the map from
    the 1097 install, the rest from the 2004 client). A zone of the 1097 layout
    (`ko_zone.select_1097`) is read headerless, and every file its GTD and OPD
    name must be present (`ko_scene.references`) or the cook is refused by name.

    `layout` names a Moradon layout of `MORADON_LAYOUTS` (PQ-223, D-171): the
    zone is then `ko_zone.select(..., stem=...)`'s and the feature data uses
    that layout's demo routes (`moradon_features.LAYOUT_ROUTES`). Layout
    `1097` (PQ-224, D-172) is the 1097 install's Moradon (`ko_zone.select_1097`
    key 21) with `character_assets` the 2004 client: the feature data (worm
    model, HUD, effects, skills, audio) then comes from `character_assets`
    too, and the zone's name rules from `zone["client_row"]`, the 2004
    client's own Moradon row (0046ea90 reads the row of the runtime key).
    """
    import json
    import shutil

    import animation
    import ko_character
    import ko_hud
    import ko_player
    import ko_scene

    root = pathlib.Path(out)
    gtd_path, opd_path = zone["gtd"], zone["opd"]
    assets = pathlib.Path(zone["assets"])
    characters = pathlib.Path(character_assets) if character_assets is not None else assets
    separate = characters.resolve() != assets.resolve()
    if separate and des:
        raise ValueError("--des needs the map's own client data for the player")
    if separate and features and layout != "1097":
        # PQ-224 (D-172): only the 1097 Moradon takes its features from another install.
        raise ValueError("--features needs the map's own client data for the player")
    headerless = zone.get("headerless", False)
    references = None
    if zone.get("layout") == "1097" or zone.get("stem") is not None:
        # The 1097 maps (PQ-274) and a renamed layout (PQ-223): files no table of
        # this install names, so every file they refer to is checked first.
        references = ko_scene_references(zone)
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(source, root)
    manifest = json.loads((root / "package.json").read_text())
    for optional in ("npc", "animation"):
        manifest.pop(optional, None)
    # KO key layout from the client's input handler (005c6990; PQ-009, D-136),
    # replacing the demo layout the copied source carries.
    manifest["input"] = json.loads(pathlib.Path("games/moradon/input.json").read_text())
    # KO's actor pick box (PQ-146, D-138): the skeleton's joint positions, an
    # axis under 0.5 grown by 0.25 a side (0041c300), mesh tie-break at LOD 0-1.
    manifest["pick"] = json.loads(pathlib.Path("games/moradon/pick.json").read_text())
    # KO camera mode 3 (PQ-012, D-143): right-drag yaw and distance, Home/End
    # pitch, screen-edge yaw (005e3e20, 005c6990), over the copied camera block.
    manifest["camera"] = {**manifest["camera"],
                          **json.loads(pathlib.Path("games/moradon/camera.json").read_text())}
    if spawn is not None:
        # The demo spawns at the origin, which on this map is the centre — and
        # the survey shows the engine will not move an actor there. Spawn at
        # the surveyed coordinate instead.
        manifest["gameplay"]["spawn_x"] = float(spawn[0])
        manifest["gameplay"]["spawn_z"] = float(spawn[2])
        manifest["gameplay"]["spawns"] = [[float(spawn[0]), float(spawn[2])]]

    # Player metadata is independent of NPC presentation (N3A2), retaining
    # source entry/loop timing and enabling the existing smooth-stop path.
    player = ko_player.cook(characters, root / "player", locomotion=True, ready=True, rest=features,combat=features)
    manifest["animation"] = [ko_character.animation_metadata(player[state]) for state in animation.STATES]
    for index in (2, 3):
        manifest["animation"][index]["loop_blend"] = False # Existing once-only action subset.
    for state in animation.STATES:
        shutil.copyfile(root / "player" / ("player-%s.bin" % state),
                        root / ("player-%s.bin" % state))
    presentation = {"player-%s.bin" % state: "player-%s.bin" % state
                    for state in animation.STATES}
    presentation["hud.bin"] = "hud.bin"
    manifest["presentation"] = presentation
    source_assets = ko_character.Assets(characters)
    # The overview map is the map's own (Zones.tbl column 8, or the 1097 table's 6).
    minimap_assets = ko_character.Assets(assets) if separate else None
    hud = None
    if not overview or features:
        hud = ko_hud.cook(source_assets, root / "hud.bin",
                          manifest["gameplay"]["npc_health"],
                          manifest["gameplay"]["level_xp"])

    world = ko_scene.bake_world(gtd_path, opd_path, assets, zone["tct"], headerless, zone.get("substitutes"))
    heightfield, triangles, report = world["heightfield"], world["triangles"], world["report"]
    built, chunked = world["built"], world["chunked"]
    meta = json.loads((root / "scene.json").read_text())
    meta["heightfield"] = heightfield
    meta["triangles"] = triangles
    (root / "scene.json").write_text(json.dumps(meta))

    if hud is None:
        hud = ko_hud.cook(source_assets, root / "hud.bin", manifest["gameplay"]["npc_health"],
                          manifest["gameplay"]["level_xp"], minimap=overview_map(zone, report),
                          minimap_assets=minimap_assets)

    import ko_detail
    if chunked:
        (root / "world-textures.bin").write_bytes(world["textures"])
        manifest["world_textures"] = "world-textures.bin"
    world_file = "world.n3world" if chunked else "moradon.n3world"
    (root / world_file).write_bytes(world["world"])
    manifest["world"] = world_file
    # PQ-387 (D-204): the zone's terrain light maps (Zones.tbl column 5, the
    # .tlt 0059ba90 opens) as an N3WO overlay over the near terrain. A zone
    # without a map writes none, so its release keeps its bytes.
    import ko_light_maps
    overlay, report["light_maps"] = ko_light_maps.overlay(zone["tlt"], heightfield["width"])
    if overlay is not None:
        (root / "world-overlay.bin").write_bytes(overlay)
        manifest["world_overlay"] = "world-overlay.bin"
    del overlay
    lod = world["lod"]
    del world
    mappings=json.loads(pathlib.Path('games/moradon/appearance.json').read_text()) if features else []
    if glow:
        # PQ-320: the glow package draws a row's glow_2233_source in place of its
        # source (Durandal on the two-hander); the default cooks never read it.
        import ko_glow_2233
        mappings=ko_glow_2233.artwork(mappings)
        # PQ-317 (D-187): the same additions package carries the 2233 skeletal
        # weapon plugs of games/moradon/skeletal-plugs-2233.json (the
        # <selfname>'s Azagai), each checked against its 2145 Item_Org row; a
        # skeletal row draws no rigid mesh, its N3AT plug entry draws the bow.
        import ko_chrplug_2145
        skeletal_install=ko_glow_2233.Install()
        skeletal_rows,skeletal_items=ko_chrplug_2145.rows(skeletal_install)
        mappings=mappings+skeletal_rows
        # PQ-319 (D-190): the same package carries the 2145 armour of
        # games/moradon/armour-2233.json (the Krowaz Assassin set) on the
        # package's KO race and class, in equipment slots it adds, each part
        # drawn from the player's 2145 Item pack as 2233's 009b3fc0 names it.
        import ko_armour_2145
        base=json.loads(pathlib.Path('games/moradon/features.json').read_text())['equipment']['slots']
        armour=ko_armour_2145.rows(skeletal_install,base,
                                   json.loads(pathlib.Path('games/moradon/ui.json').read_text())['equipment_slots'],
                                   ko_player.RACE)
        mappings=mappings+armour['rows']
    detail, detail_report = ko_detail.cook(characters,built,player["idle"]["character_metadata"],mappings,
                                           world_root=assets)
    if mappings:manifest['appearance']=[dict(item=r['item'],slot=r['slot']) for r in mappings]
    weapon_effects=detail_report.pop('weapon_effects')
    (root / "render-detail.bin").write_bytes(detail)
    manifest["render_detail"] = "render-detail.bin"
    report["render_detail"] = detail_report
    manifest["engine_version"] = 14
    manifest["protocol_version"] = 7
    # Binary camera Apply 004395c0: linear range fog from .1*far to far.
    # Static preview colour/view distance are explicit package choices;
    # dynamic sky/weather remains outside this preview.
    manifest["exploration"] = dict(turbo_multiplier=10, fog_start=25.6,
                                    fog_end=256, fog_color=[.62,.70,.78])
    if lod is not None:  # an N3W2 world carries its own parts
        (root / "world-lod.bin").write_bytes(lod)
        manifest["exploration"]["lod"] = "world-lod.bin"
    if spawn is not None:
        # Keep the editable decoration on the ground beside the spawn instead of
        # at the map centre, where the demo's origin-relative placement lands
        # under the terrain.
        for decoration in manifest["editing"]["decorations"]:
            decoration["position"] = [float(spawn[0]) + 2.0, float(spawn[1]),
                                      float(spawn[2])]
    if features:
        if spawn is None:raise ValueError('feature integration needs surveyed spawn')
        import moradon_features, ko_loot_model, ko_target_marker
        report['features']=moradon_features.apply(root,manifest,characters,spawn,heightfield,triangles,player,layout)
        item_icons=presented=None
        if not glow:
            # PQ-361 (D-196): the default feature cooks draw 1298's tooltip head
            # (004d6320) for each item whose appearance rows name a KO item (the
            # blade, 120110048): N3IH's name colour, kind line and type line from
            # this client's tables. The glow cook keeps its 2233 heads (D-194).
            import ko_item_heads
            heads,report['item_heads_1298']=ko_item_heads.cook(source_assets,mappings)
            if heads:manifest['item_heads']=heads
        extra_clips={}  # PQ-423: effect clips only the glow cook adds
        extra_sounds={}  # PQ-417: sound keys only the glow cook adds
        if glow:
            # PQ-321: the glow package names and draws the replaced artwork's item
            # (Durandal) in its own inventory definition and icon map; the default
            # cooks keep features.json's label and ui.json's icon.
            import csv, io, hashlib
            org_data=ko_character.Assets(characters).get('Data/Item_Org_us.tbl.csv')
            org=list(csv.reader(io.StringIO(org_data.decode('utf-8-sig'))))
            manifest['inventory']['items'],item_icons,presented=ko_glow_2233.presentation(
                mappings,manifest['inventory']['items'],json.loads(pathlib.Path('games/moradon/ui.json').read_text())['item_icons'],org)
            ko_chrplug_2145.add_items(manifest,skeletal_items,{r['item']:r['slot'] for r in skeletal_rows})
            # PQ-422 (D-219): the bow's own attack and durability (2145 Item_Org
            # columns 16 and 20) under the package's bow stats category.
            report['bow_stats_2145']=ko_chrplug_2145.bow_stats(manifest,skeletal_items,'demo:weapon/bow')
            # PQ-347: the bow, alone in the left hand, selects the combat
            # profile 1298 gives a kind 70 bow (ready 92, the class's archery
            # animation and cast interval), checked against 1298's tables.
            bow_rows,report['bow_combat_1298']=ko_chrplug_2145.combat_rows(
                json.loads(pathlib.Path('games/moradon/combat-animation.json').read_text()),manifest['equipment']['slots'],
                skeletal_items,{r['item']:r['slot'] for r in skeletal_rows},
                source_assets.get(ko_chrplug_2145.SKILL_TABLE).decode('utf-8-sig'),armour['character']['class'])
            manifest['combat_animation']['rows']+=bow_rows
            # PQ-416 (D-216): that profile is a ranged basic attack: the bow's
            # range from its Item_Org row, 1298's archery add range and text.
            manifest['ranged_attack'],report['ranged_attack_1298']=ko_chrplug_2145.ranged_attack(
                skeletal_items,bow_rows[0]['profile'],report['bow_combat_1298']['skill'],
                source_assets.get(ko_chrplug_2145.SKILL_TABLE).decode('utf-8-sig'),
                source_assets.get(ko_chrplug_2145.TYPE2_TABLE).decode('utf-8-sig'),
                source_assets.get(ko_chrplug_2145.TEXTS_TABLE).decode('utf-8-sig'))
            # PQ-421 (D-218): the shot needs and uses 1298's arrow (Item_Org
            # 391010000, one per shot by the archery row's type-2 count): an
            # inventory item granted at start and sold by the supplies shop.
            arrow,arrow_sale,arrow_icon,ammo,ammo_notice,report['arrows_1298']=ko_chrplug_2145.arrows(
                'demo:item/arrow',report['bow_combat_1298']['skill'],
                source_assets.get(ko_chrplug_2145.SKILL_TABLE).decode('utf-8-sig'),
                source_assets.get(ko_chrplug_2145.TYPE2_TABLE).decode('utf-8-sig'),org,
                source_assets.get(ko_chrplug_2145.TEXTS_TABLE).decode('utf-8-sig'),GLOW_ARROWS)
            manifest['inventory']['items'].append(arrow)
            manifest['commerce']['items'].append(arrow_sale)
            next(shop for shop in manifest['commerce']['shops'] if shop['id']=='demo:shop/supplies')['items'].append(arrow['id'])
            item_icons[arrow['id']]=arrow_icon
            for entry in manifest['ranged_attack']['profiles']:entry['ammo']=dict(ammo)
            manifest['ranged_attack']['ammo_notice']=ammo_notice
            # PQ-422 (D-219): its damage on an NPC is the AI server's archery
            # (0040d471): the type-2 terms of the operator's MAGIC_TYPE2 row.
            hit,report['archery_hit_1298']=ko_chrplug_2145.archery_hit(
                report['bow_combat_1298']['skill'],source_assets.get(ko_chrplug_2145.TYPE2_TABLE).decode('utf-8-sig'))
            for entry in manifest['ranged_attack']['profiles']:entry['skill_hit']=dict(hit)
            # PQ-423 (D-220): the cast draws the archery row's self FX (500,
            # the arrow) on the archer's part 12 until the release (1298
            # 00583f20 -> 00479de0; 00584b00 -> 0047a710): a self clip of
            # this package's effects and the profile's cast-effect joints.
            joints=len(ko_detail.bind_world(ko_character.Assets(characters),player['idle']['character_metadata']))
            cast_key,cast_clip,cast_effect,report['archery_cast_fx_1298']=ko_chrplug_2145.cast_effect(
                report['bow_combat_1298']['skill'],source_assets.get(ko_chrplug_2145.SKILL_TABLE).decode('utf-8-sig'),
                source_assets.get(ko_chrplug_2145.FX_TABLE_1298).decode('utf-8-sig'),joints)
            for entry in manifest['ranged_attack']['profiles']:entry['cast_effect']=dict(cast_effect)
            extra_clips[cast_key]=cast_clip
            # PQ-417 (D-222): at the landing the row's flying FX (590, the
            # arrow) flies from the archer's part 12 to the target's box at
            # the bundle's velocity, then its target FX (550) plays on the
            # target's part (1298 00587ac0 -> 0047a2d0; 0047a8d0; 00586fa0),
            # with the bow's release sound 0x157c (left kind 70).
            import ko_fx
            flight_clips,flight,release_sound,report['archery_flight_1298']=ko_chrplug_2145.flight(
                report['bow_combat_1298']['skill'],source_assets.get(ko_chrplug_2145.SKILL_TABLE).decode('utf-8-sig'),
                source_assets.get(ko_chrplug_2145.TYPE2_TABLE).decode('utf-8-sig'),
                source_assets.get(ko_chrplug_2145.FX_TABLE_1298).decode('utf-8-sig'),
                lambda path:ko_fx.bundle(source_assets.get(path)),joints,ko_chrplug_2145.BOW_KIND)
            for entry in manifest['ranged_attack']['profiles']:entry['flight']=dict(flight)
            extra_clips.update(flight_clips)
            if release_sound:extra_sounds['ranged-release']=release_sound
            # PQ-319: the armour's slots, then its items (worn only in their
            # part's slot, granted at start, presentation only) and 2145 icons.
            if manifest['equipment']['slots']!=base:raise ValueError('the armour slots extend features.json\'s')
            manifest['equipment']['slots']=base+armour['slots']
            ko_chrplug_2145.add_items(manifest,armour['items'],{r['item']:r['slot'] for r in armour['rows']})
            # PQ-350: both upgrade paths' starting items (20) do not fit
            # features.json's 32-slot bag beside its own and the progression's
            # reward slots; this package's bag is two pages of the HUD's
            # 28-slot bag window (the realm is per release, so no stored bag
            # changes shape).
            manifest['inventory']['capacity']=max(manifest['inventory']['capacity'],56)
            # PQ-338: the 1298 client has no icon for a 2145-only item; the
            # skeletal plug items take theirs from the player's 2145 UI pack by
            # the 2233 rule (009b3fc0) into this package's own icon map.
            item_icons,skeletal_icons=ko_chrplug_2145.icons(item_icons,skeletal_items,skeletal_install)
            item_icons,armour_icons=ko_chrplug_2145.icons(item_icons,armour['items'],skeletal_install)
            presented=dict(item_org='Data/Item_Org_us.tbl.csv',item_org_sha256=hashlib.sha256(org_data).hexdigest(),items=presented,
                           skeletal_icons=skeletal_icons,armour_icons=armour_icons)
            report['armour_2145']=dict(addition='2233 code (009b3fc0, 005e5a90, 00930030, 005aa8e0), 2145 data',
                                       definition=str(ko_armour_2145.DEFINITION),character=armour['character'],
                                       slots=armour['slots'],areas=armour['areas'],
                                       items={k:v[1] for k,v in armour['items'].items()},
                                       sources=ko_armour_2145.source(skeletal_install).sources)
        report['loot_model']=ko_loot_model.cook(source_assets,root/'loot-model.bin')
        manifest['presentation']['loot-model.bin']='loot-model.bin'
        (root/'loot-policy.bin').write_bytes(b'N3LP'+struct.pack('<f',report['loot_model']['definition']['open_radius']))
        manifest['presentation']['loot-policy.bin']='loot-policy.bin'
        report['target_marker']=ko_target_marker.cook(source_assets,root/'target-marker.bin',moradon_features.drawn_scale())
        manifest['presentation']['target-marker.bin']='target-marker.bin'
        import ko_fx_bake
        effect_definition=pathlib.Path('games/moradon/effects.json')
        # PQ-315 (D-184): --glow-2233 adds the 2233 client's equipment glow
        # from the player's 2145 tables (a 2233/2145 addition, opt-in).
        glow_records=()
        if glow:
            import ko_glow_2233
            glow_records,report['glow_2233']=ko_glow_2233.cook(mappings)
            report['glow_2233']['presentation']=presented
            # PQ-316 (D-185): the same additions package carries the zone's
            # 2233 HDR bloom and tone map from the player's 2145 hdr.n3pp; the
            # client draws it only with Option.ini [Addition2233] HDR=1. The
            # key is the runtime zone's (00476f50 is called with the zone row's id).
            import ko_hdr_2233
            manifest['postprocess'],report['hdr_2233']=ko_hdr_2233.cook(int(zone.get('client_row',zone['row'])[0]))
        if glow:
            # PQ-339: the skeletal plugs' weapon effect (2233 004304c0 on the
            # .n3chrplug's FX mesh, rigid on the hand joint) from the player's
            # 2145 fx pack, on the same N3E2 records as the rigid plugs'.
            bind=ko_detail.bind_world(ko_character.Assets(characters),player['idle']['character_metadata'])
            skeletal_fx,report['skeletal_effects_2233']=ko_chrplug_2145.weapon_effects(
                mappings,skeletal_items,bind,max(m[1][3] for m in bind),skeletal_install)
            weapon_effects=weapon_effects+skeletal_fx
        # PQ-211: equipped weapon effects from the appearance rows' KO items.
        effects=json.loads(effect_definition.read_text())
        if set(extra_clips)&set(effects['clips']):raise ValueError('a cast effect clip key is taken: %r'%sorted(extra_clips))
        effects['clips'].update(extra_clips)
        report['effects']=ko_fx_bake.cook(source_assets,effects,root/'effects.bin',
                                          appearance=weapon_effects,keys=len(mappings),glow=glow_records)
        manifest['presentation']['effects.bin']='effects.bin'
        import csv, io
        # PQ-224: a map from another install takes the name rules of the client
        # whose player and HUD it plays (its own Moradon row, zone["client_row"]).
        row=zone.get('client_row',zone['row'])
        report.update(zone_names(row,manifest['input'],json.loads(pathlib.Path('games/moradon/nameplates.json').read_text())['zone_distance']))
        # NPC names (PQ-174): the template's looks row, NPC_Looks.tbl column 36.
        looks=list(csv.reader(io.StringIO(source_assets.get('Data/NPC_Looks.tbl.csv').decode('utf-8-sig',errors='replace'))))
        report.update(npc_names(looks,moradon_features.reference()['monster'],manifest['input']))
        hud=ko_hud.cook(source_assets,root/'hud.bin',manifest['gameplay']['npc_health'],manifest['gameplay']['level_xp'],features=True,minimap=overview_map(zone,report),
                    minimap_assets=minimap_assets,npc_scale=moradon_features.drawn_scale(),item_icons=item_icons,
                    equipment_slots=armour['areas'] if glow else None)
        import ko_audio, ko_skills
        report['skills']=ko_skills.cook(source_assets,root,manifest)
        if manifest.get('npc',{}).get('model')=='reference_melee_v2':
            # Reference NPC slots require the engine 36 / wire 29 readers.
            manifest.update(engine_version=36,protocol_version=29)
        if glow:
            # PQ-317 (D-187): the skeletal plugs' N3AT table, from the player's
            # and skill clips' KO indices; its looks models make the package
            # engine 39 (N3MM: the bow's render state), so wire 30.
            import attachments
            height=max(m[1][3] for m in ko_detail.bind_world(ko_character.Assets(characters),player['idle']['character_metadata']))
            report['skeletal_plugs_2233']=ko_chrplug_2145.package(manifest,mappings,height,root,
                                                                  root.parent/(root.name+'-skeletal'),skeletal_install)
            report['skeletal_plugs_2233']['items']={k:v[1] for k,v in skeletal_items.items()}
            manifest.update(engine_version=max(manifest['engine_version'],attachments.engine(manifest['attachments'],root)),
                            protocol_version=30)
        report['audio']=ko_audio.cook(source_assets,report['effects'],hud,root/'audio.bin',item_icons,extra_sounds)
        manifest['presentation']['audio.bin']='audio.bin'
        # Spec 11: KO's login scene, select hall, create, loading and message
        # box from the same client tree; engine 42.
        import ko_front_end
        report['front_end']=ko_front_end.cook(source_assets,root,'games/moradon/front-end.json',root.parent/(root.name+'-front-end'))
        manifest['presentation']['front-end.bin']='front-end.bin'
        manifest.update(engine_version=max(manifest['engine_version'],42),protocol_version=30)
        if des:
            # Exploration: Demon's Souls characters from the user's own dump (moradon_des.py).
            import moradon_des
            report['demons_souls']=moradon_des.apply(root,manifest)
    (root / "package.json").write_text(json.dumps(manifest, indent=2))

    report["zone"] = zone["provenance"]
    if references is not None:
        report["references"] = references
    if separate:
        report["character_assets"] = str(characters)
    if start is not None:
        report["start"] = start
    report["visuals"] = built["report"]
    report["player"] = {"race": "male Tuarek", "states": sorted(player),
                        "hud_sources": source_assets.sources}
    report["hud"] = hud
    (root / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    return root, report


CLIENT = pathlib.Path("assets/ko")
# PQ-421 (D-218): the arrows the glow package grants a new character (an n3e
# package choice, not KO data: KO characters buy them; the supplies shop sells
# more at 1298's price).
GLOW_ARROWS = 100
# PQ-274 (D-170): the 1097 client's zones, from the pinned PQ-221 unpack of the
# player's KnightOnline_1097.exe (tools/ko-reference/unpack_installer.py PINNED).
INSTALL_1097 = pathlib.Path("build/ko-reference/installer-1097")
INSTALLER_1097_SHA256 = "d7571e183663be3d063af491d68d7db3dc52219f58471c9595d0b745c0b8a93b"

# PQ-290 (D-180): 1097 install files that KO itself replaced by the 1264 install,
# read from the 2004 client (CLIENT, the 1097 bake's player and HUD source) in
# their place. By base name: (the 1097 installer's file, the 2004 client's file),
# as SHA-256 (local-asset). `obj_ka_tree_bra_post` is obj_ka_tree_brA's trunk:
# every OPD from 1097 to 1453 places it at pivot (0.037, 0.018, 0.092); the
# 1097 mesh is centred on its own box (y -3.44..3.44), so under the client's
# part rule (`004445a0`, PQ-290) the trunk sinks 3.4 m and stops below the
# crown, while the 1264, 1298 and 1453 installs' re-export (y -0.19..6.62)
# stands on the ground and reaches into it.
CORRECTIONS_1097 = {
    "obj_ka_tree_bra_post.n3pmesh": ("645099499b8dbedc5cf963917ea6b75fd4cdb2daaed78d6e24b59f4cd69b8343",
                                     "eba7a66fe5952551349da727998976264494b5175f92384cb7fe3152d838dfe4"),
}


def corrections_1097(zone, client=CLIENT, table=None):
    """The pinned corrections (`CORRECTIONS_1097`, or `table`) a 1097 zone refers
    to, as ({name: the 2004 client's path}, provenance records).

    Only files the zone's OPD names are corrected, so a zone that names none
    cooks exactly as before. Each file must be the pinned one on both sides, or
    the cook is refused by name: a correction never applies to a file it was
    not checked against."""
    import hashlib
    import ko_scene
    table = CORRECTIONS_1097 if table is None else table
    named = set()
    for shape in ko_shapes.load_shapes(zone["opd"], headerless=zone.get("headerless", False))["shapes"]:
        for part in shape["parts"]:
            named.update(ko_scene._basename(n) for n in [part["mesh"], *part["textures"]] if n)
    objects = ko_scene.object_files(pathlib.Path(zone["assets"]))
    substitutes, records = {}, []
    for name in sorted(set(table) & named):
        stale, fixed = table[name]
        replacement = pathlib.Path(client) / "Object" / name
        for path, expected, side in ((objects.get(name), stale, "1097 install's"),
                                     (replacement, fixed, "2004 client's")):
            if path is None or not path.is_file():
                raise ValueError("correction %s: the %s file is missing" % (name, side))
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("correction %s: %s is not the pinned %s file" % (name, path, side))
        substitutes[name] = replacement
        records.append(dict(file="Object/" + name, replaced_sha256=stale, source=str(replacement),
                            sha256=fixed, decision="D-180"))
    return substitutes, records


# PQ-223 (D-171): Moradon layouts the pinned Zones.tbl does not name, by the file
# stem key 210's row is rewritten to (ko_zone.restem) and the SHA-256 of each file
# the rewritten row selects, as the pinned 1298 installer ships them (its
# manifest, PQ-214; local-asset). The table's own row (Moradon_xmas) is the
# default and has no entry here.
MORADON_LAYOUTS = {"classic": ("Moradon", {
    "gtd": "0d386e290b6dd282020ac56b74737c4e2b23b3e19beee7dcca7805bd00ad8325",
    "tct": "3199ab3438b8c0c483146866f90ce90691663c6579b484b0d4b47bda9a635734",
    "opd": "b63c491bbb99b76a2988f53ca611c661f534b980230446cc94b5efc95a0a7b06",
    "minimap": "16c0ea0b8cebaa8a9b1891c4bec45e67e1a99bf05909eb2c1ca5787ee5d7dfaf",
    # PQ-387: column 5, the terrain light maps (PQ-385 local-asset).
    "tlt": "3bc9296f9265d1c5d3e6acb9b6bb7b4e64a1a8cde327b4c65d6f8228b7efd8c5"})}


def moradon_layout(zone, layout):
    """Refuse a layout whose selected files are not the pinned install's; returns
    their hashes for the provenance."""
    import hashlib
    expected = MORADON_LAYOUTS[layout][1]
    found = {kind: hashlib.sha256(pathlib.Path(zone[kind]).read_bytes()).hexdigest() for kind in expected}
    differ = ["%s (%s)" % (zone[kind], kind) for kind in expected if found[kind] != expected[kind]]
    if differ:
        raise ValueError("the %s layout's files differ from the pinned 1298 installer's: %s"
                         % (layout, ", ".join(differ)))
    return found


def install_1097(zone, install=INSTALL_1097):
    """Check the files `ko_zone.select_1097` chose against the unpack's manifest,
    which must name the pinned 1097 installer; returns the provenance record."""
    import hashlib
    import json
    path = install / "manifest.json"
    if not path.is_file():
        raise ValueError("no 1097 install at %s: run python3 -I tools/ko-reference/unpack_installer.py "
                         "ref/ko-bin/installer/KnightOnline_1097.exe" % install)
    data = read(path, 64 * 1024 * 1024)
    manifest = json.loads(data)
    if manifest.get("sha256") != INSTALLER_1097_SHA256:
        raise ValueError("%s is not the pinned 1097 installer's unpack" % path)
    hashes = {entry["path"].lower(): entry["sha256"] for entry in manifest["manifest"]}
    client = (install / "client").resolve()
    checked = {}
    for kind in ("table", "gtd", "tct", "tlt", "opd", "minimap"):
        relative = pathlib.Path(zone[kind]).resolve().relative_to(client).as_posix()
        actual = hashlib.sha256(pathlib.Path(zone[kind]).read_bytes()).hexdigest()
        if hashes.get(relative.lower()) != actual:
            raise ValueError("%s differs from the 1097 installer's (manifest %s)" % (zone[kind], path))
        checked[relative] = actual
    return dict(manifest=str(path), manifest_sha256=hashlib.sha256(data).hexdigest(),
                installer_sha256=INSTALLER_1097_SHA256, files=checked)


if __name__ == "__main__":
    import json
    import sys
    import ko_zone
    # The zone is chosen by its Zones.tbl key (column 1; 210 is Moradon), and the
    # row names its files, as the client's world loader 005a3110 reads them.
    arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "210"
    if not (arg.isascii() and arg.isdigit()):
        raise SystemExit("ko_bake.py takes a Zones.tbl zone key (210 is Moradon), not %r" % arg)
    # --client=1097 (PQ-274, D-170): the zone from the 1097 install's own table and
    # headerless files, under the 1097 keys (the zone ids: 1 Karus, 2 El Morad);
    # the player and HUD still come from CLIENT.
    legacy = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--client=")), None)
    if legacy not in (None, "1097"):
        raise SystemExit("--client takes 1097 (the 1097 install's zones), not %r" % legacy)
    # --layout=classic (PQ-223, D-171): Moradon from the same install's files of
    # another stem (MORADON_LAYOUTS), through the rewritten key 210 row.
    layout = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--layout=")), None)
    if layout is not None and layout not in MORADON_LAYOUTS:
        raise SystemExit("--layout takes %s (Moradon layouts the Zones.tbl does not name), not %r"
                         % (", ".join(sorted(MORADON_LAYOUTS)), layout))
    if layout is not None and (legacy or "--des" in sys.argv):
        raise SystemExit("--layout is a 1298 Moradon layout; it does not combine with --client or --des")
    try:
        if legacy:
            # Name the missing install before touching its table: on a machine
            # without the unpack, `ko_zone.select` would otherwise fail first on
            # Zones.tbl and hide the actual cause (tests/ko_bake_pin.py).
            if not (INSTALL_1097 / "manifest.json").is_file():
                install_1097({})
            zone = ko_zone.select(INSTALL_1097 / "client", int(arg), layout="1097")
            zone["provenance"]["install"] = install_1097(zone)
            zone["substitutes"], corrected = corrections_1097(zone)
            if corrected:  # recorded only where applied, so other 1097 cooks keep their pins
                zone["provenance"]["corrections"] = corrected
        elif layout is not None:
            zone = ko_zone.select(CLIENT, int(arg), stem=MORADON_LAYOUTS[layout][0])
            zone["provenance"]["variant"].update(layout=layout, sha256=moradon_layout(zone, layout))
        else:
            zone = ko_zone.select(CLIENT, int(arg))
    except ValueError as error:
        raise SystemExit("zone %s%s: %s" % (arg, " (1097)" if legacy else " (%s)" % layout if layout else "", error))
    print("zone %d: %s, %s, %s, %s" % (zone["key"], zone["gtd"], zone["tct"], zone["opd"], zone["minimap"]))
    if zone["opdext"] is not None:  # merged by ko_zone (005b4ef0); the OPD faces are baked
        print("opdext: %s, %d extension faces, name %r" % (
            zone["opdext"], zone["extension"]["read"]["faces"], zone["extension"]["merged"]["name"]))
    # --into=DIR writes every output below DIR instead of build/ (DIR/kx/survey,
    # DIR/ko-moradon, DIR/packages/moradon), so make live-ko (PQ-111) never
    # replaces the package a persistent tools/play-moradon stack mounts.
    into = pathlib.Path(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--into=")), "build"))
    gtd, opd = zone["gtd"], zone["opd"]
    features, des, preview = "--features" in sys.argv, "--des" in sys.argv, "--preview" in sys.argv
    # --glow-2233 (PQ-315, D-184): the 2233 client's equipment glow from the
    # player's 2145 install, a 2233/2145 addition in a package of its own;
    # since PQ-316 (D-185) also the zone's HDR bloom and tone map (hdr.n3pp).
    glow = "--glow-2233" in sys.argv
    if glow and (not features or des or preview):
        raise SystemExit("--glow-2233 is a Moradon feature cook addition: it needs --features, without --des or --preview")
    # Imported here rather than at module scope: ko_survey imports this module.
    import ko_start
    import ko_survey
    import moradon_features
    # The feature data (start, NPCs, routes) is Moradon's: its zone keeps the
    # ko-moradon / moradon names, and any other zone cooks without it under its
    # own key (PQ-217).
    # PQ-224 (D-172): the 1097 install's key 21 is its Moradon (zone 21), cooked
    # with Moradon's feature data as layout "1097" beside the default.
    moradon = zone["zone_id"] == moradon_features.reference()["start_position"]["ZoneID"]
    if legacy and moradon:
        if des:
            raise SystemExit("zone %d (1097): --des does not combine with --client" % zone["key"])
        layout = "1097"
        # The name rules are the 2004 client's for its own Moradon row (0046ea90).
        zone["client_row"] = ko_zone.row(ko_zone.table(CLIENT)[1], zone["zone_id"] * 10)
        zone["provenance"]["client_row"] = dict(
            zones_table=str(CLIENT / "Data" / "Zones.tbl.csv"), key=int(zone["client_row"][0]),
            use="the zone's name rules (column 23, the zone key; 0046ea90): the 2004 client whose player "
                "and HUD the package plays")
    if layout is not None and not moradon:
        raise SystemExit("--layout=%s is a Moradon layout; zone %d is not Moradon" % (layout, zone["key"]))
    if (features or des) and not moradon:
        raise SystemExit("--features and --des carry Moradon's start, NPC and route data; "
                         "zone %d%s cooks without them" % (zone["key"], " (1097)" if legacy else ""))
    samples = ko_terrain.header_samples(gtd, zone["headerless"])
    # PQ-217: any other zone starts from the operator's own START_POSITION export
    # (never committed; --start-positions=PATH, default ko_start.EXPORT). Moradon
    # keeps its committed D-106 start and its pinned cook.
    export = pathlib.Path(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--start-positions=")),
                               ko_start.EXPORT))
    try:
        rows, export_sha256 = (None, None) if moradon else ko_start.load(export)
        start_row = ko_start.row(zone["key"], rows, zone=zone["zone_id"]) if rows is not None else None
    except ValueError as error:
        raise SystemExit("zone %d: %s" % (zone["key"], error))
    if legacy and not moradon and start_row is None:
        # No 1097 server data exists: the start is the operator's row for the zone (D-170).
        raise SystemExit("zone %d (1097) starts from its START_POSITION row, and %s" % (
            zone["key"], "%s has none for zone %d" % (export, zone["zone_id"]) if rows is not None else
            "there is no START_POSITION export at %s (or --start-positions=PATH)" % export))
    start = None
    if start_row is not None:
        # PQ-217: each nation's START_POSITION area (004c6523), surveyed with the
        # engine on its own crop of the map; every area must hold a spawn.
        extent = (samples - 1) * ko_terrain.TILE_SIZE
        try:
            areas, package_nation = (ko_start.areas(start_row, extent),
                                     ko_start.nation(zone["key"], zone=zone["zone_id"]))
        except ValueError as error:
            raise SystemExit("zone %d: %s" % (zone["key"], error))
        scratch = str(into / "kx" / (("survey-1097-%d" if legacy else "survey-%d") % zone["key"]))
        found, triangles = ko_survey.survey_starts(gtd, opd, scratch, areas, headerless=zone["headerless"])
        start = dict(export=str(export), export_sha256=export_sha256, row=start_row,
                     row_sha256=ko_start.row_digest(start_row), extent_metres=extent,
                     rule="start + rand(0, range) per axis (Ebenezer 004c6523, 00422261)",
                     nation=package_nation, areas={})
        for nation, result in found["starts"].items():
            chosen = result["spawn"]
            if chosen is None:
                raise SystemExit("zone %d: no engine-verified spawn in the %s start area %s; refusing "
                                 "to publish a map nobody can stand on" % (zone["key"], nation, result["area"]))
            start["areas"][nation] = dict(
                area=result["area"], crop_points=result["crop_points"], pre_filtered=result["pre_filtered"],
                engine_checked=result["engine_checked"], spawn=chosen["position"],
                spawn_ko=ko_start.to_ko(chosen["position"], extent), min_away=chosen["min_away"],
                worst_return=chosen["worst_return"])
            print("%s start area %s: spawn [%.1f, %.2f, %.1f] (KO %.0f, %.0f), %d of %d candidates checked"
                  % (nation, result["area"], *chosen["position"], *start["areas"][nation]["spawn_ko"],
                     result["engine_checked"], result["pre_filtered"]))
        del found
        spawn = start["areas"][start["nation"]]["spawn"]
        # PQ-218: a point the engine walks to from the package start (the run speed
        # and capsule of the copied demo rules), for the play stack's live check
        # (tests/homeland_live.py) to walk through the server.
        rules = json.loads(pathlib.Path("games/demo/package.json").read_text())["gameplay"]
        area = start["areas"][start["nation"]]["area"]
        walk = ko_survey.walk_target(ko_survey.crop(triangles, area), area, spawn,
                                     dict(rules["movement"], speed=rules["speed"]), scratch)
        del triangles
        if walk is None:
            raise SystemExit("zone %d: the engine reaches no surveyed point within %.0f m of the %s start; "
                             "refusing to publish a start nobody can walk from"
                             % (zone["key"], ko_survey.WALK_REACH, start["nation"]))
        start["walk"] = dict(walk, start=spawn, reach=ko_survey.WALK_REACH)
        print("walk from the %s start to [%.1f, %.2f, %.1f] (%.1f m), engine end [%.2f, %.2f, %.2f]"
              % (start["nation"], *walk["target"], walk["distance"], *walk["engine_end"]))
    elif samples > ko_terrain.MAX_SUPPORTED_SAMPLES:
        raise SystemExit("zone %d: a %d-sample map starts from its START_POSITION row, and %s" % (
            zone["key"], samples, "%s has none for zone %d" % (export, zone["key"] // 10) if rows is not None else
            "there is no START_POSITION export at %s (your own reference database's table as a JSON list "
            "of rows, as tools/ko-reference/inspect_db.py writes it; or --start-positions=PATH)" % export))
    elif zone["headerless"] and not moradon:
        raise SystemExit("zone %d: a headerless map is surveyed only from its START_POSITION row" % zone["key"])
    else:
        # Feature builds start players inside the reference start rectangle; the survey
        # still proves the chosen point with the engine and fails closed.
        within = moradon_features.start_area() if features else None
        found, _ = ko_survey.survey(gtd, opd, str(into / ("kx/survey-moradon-%s%s" % (layout, "-glow2233" if glow else "") if layout
                                                  else "kx/survey-glow2233" if glow else "kx/survey")),
                                    limit=24, within=within, headerless=zone["headerless"])
        if not found["spawn"]:
            raise SystemExit("no spawn qualified; refusing to publish a map "
                             "nobody can stand on")
        spawn = found["spawn"]["position"]
    print("surveyed spawn [%.1f, %.2f, %.1f]" % tuple(spawn))
    # PQ-274 (D-170): the 1097 zones cook beside the current homelands under keys of
    # their own (ko-1097-zone-1 and -2), never ko-zone-1 and -2.
    base, source = ("moradon", "ko-moradon") if moradon else (
        (("ko-1097-zone-%d" if legacy else "ko-zone-%d") % zone["key"],) * 2)
    if layout is not None:  # PQ-223, PQ-224: beside the default Moradon, never over it
        base, source = "moradon-" + layout, "ko-moradon-" + layout
    suffix = "-preview" if preview else "-des" if des else "-glow2233" if glow else ""
    # Every zone but Moradon carries its overview map on the basic HUD (N3HE);
    # Moradon's plain and preview cooks stay as pinned, its feature HUD has one.
    root, report = package("games/demo", zone, str(into / (source + suffix)), spawn, features=features,
                           des=des, overview=not moradon, start=start,
                           character_assets=CLIENT if legacy else None, layout=layout, glow=glow)
    report["spawn"] = spawn
    import main
    print(main.cook(root, into / "packages" / (base + suffix)))
    print("package %s" % (into / "packages" / (base + suffix)))
    print(json.dumps({k: report[k] for k in (
        "extent_metres", "collision_faces", "collision_points",
        "terrain_points", "faces_dropped_degenerate", "barrier_faces",
        "vertices_clamped")} | {"visuals": report["visuals"]}, indent=2))
