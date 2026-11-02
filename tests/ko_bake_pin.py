"""PQ-216/PQ-229: the KO bake against the player's own client data, when present.

* Moradon (Zones.tbl key 210, column 7 `Reserved`) cooks to the pinned release
  hashes. `--preview` changes only the output folders, so it shares the plain
  cook's hash and is not cooked again. A deliberate change to the Moradon cook
  (its demo base, the cooker or the importers) updates these pins in the same
  commit, with the reason in its evidence record.
* Every zone whose column 7 names an OPDEXT selects, reads it against its OPD and
  merges it with the column 3 name re-check (`005b4ef0`, `005a3329`). Their
  cook stops later (their zones have START_POSITION rows in the operator's
  export, but `ko_start.PACKAGE_NATION` has no nation for them; without the
  export, the export is missing) and is not asserted here.
* PQ-217 (with PQ-234's N3W2 branch): key 10 is refused without the operator's
  START_POSITION export or without its zone row. With the export
  (`ko_start.EXPORT`, never committed; SKIP without it), Zones.tbl keys 10
  (`karus2004`) and 20 (`elmo2004`, both 513 samples) go through
  `tools/assetc/ko_bake.py KEY`: the export's hash is in the provenance, both
  nations' START_POSITION areas hold an engine-verified start inside their
  one-sided KO rectangle (`004c6523`), the package starts at its own nation's,
  the cooked N3C2 collision answers the same ground and step there on both
  runtimes, the world is N3W2 with N3WT textures and no `world-lod.bin`, the
  HUD is N3HE with the zone's 512 / 1024 px overview map, and the client's asset
  check and the server's content check accept it (about 35 s and 1.7 GiB each).
  PQ-218: the provenance also holds the walk target the play stack's live check
  (tests/homeland_live.py) walks to, which the engine solver reached from the
  start. Without the export the N3W2 package checks still run on key 10, through
  `ko_bake.package(..., spawn=None)` (the demo's start, no survey).
* PQ-051: each homeland's release hash is pinned for the START_POSITION row it
  was cooked from, named by `ko_start.row_digest` (the read columns spelled one
  way), not by the export file's hash: a re-export of the same row in another
  row order, key order or layout cooks the same release. Another row prints a
  SKIP line for the pin. A deliberate change to the homeland cook updates these
  pins in the same commit, as for Moradon's.
* PQ-274 (D-170): with the player's 1097 install unpacked
  (build/ko-reference/installer-1097, PQ-221; SKIP without it), the 1097
  homelands (its keys 1 and 2, `karus_start` and `elmorad_start`) go through
  `ko_bake.py KEY --client=1097` with the same start, walk, collision, world and
  check assertions, and are pinned the same way. Their map files are the 1097
  table's own, read headerless and checked against the installer's manifest;
  every file they name is present; the overview map is the 1097 one; the player
  and HUD are the 2004 client's. Without the export key 1 is refused as key 10 is.

* PQ-223 (D-171): the classic Moradon, `ko_bake.py 210 --layout=classic` and
  `--layout=classic --features`, cooks to its own pinned release hashes from
  the install's own unnamed `Zones/moradon.*` (the pinned installer's hashes),
  with nothing it refers to missing, into `moradon-classic` beside the default.
  The feature cook keeps the START_POSITION zone 21 start area and the worm
  rows, with its own route to the second worm area; the client's asset check
  and the server's content check accept it, and the cooked collision answers
  the same ground and step at the start on both runtimes. With the player's
  1264 install unpacked (PQ-221; SKIP without it), the rewritten key 210 row
  less its column 7 is the 1264 client's own key 210 row.

* PQ-224 (D-172): with the player's 1097 install unpacked (SKIP without it),
  the 1097 Moradon, `ko_bake.py 21 --client=1097` and `--features`, cooks to its
  own pinned release hashes from the 1097 table's key 21 files (headerless,
  checked against the pinned installer's manifest), with nothing it refers to
  missing, into `moradon-1097` beside the default; the player and HUD are the
  2004 client's. The feature cook keeps the START_POSITION zone 21 start area
  and the worm rows, with the classic routes (`LAYOUT_ROUTES["1097"]`), the 1097
  overview map and the 2004 client's key 210 name rules; the asset and content
  checks accept it, and the cooked collision answers the same ground and step
  at the start on both runtimes. `--des` and `--layout` are refused with it.
  The test also counts the files the 1097 map names whose 2004 copy of the same
  name differs (local-asset).

* PQ-290 (D-180): the 1097 key 1 provenance records its one pinned correction
  (`obj_ka_tree_bra_post.n3pmesh` from the 2004 client); key 2 and the 1097
  Moradon name no corrected file, record none and keep their pins.

* PQ-288 (D-181): each feature cook (default, classic, 1097) draws the worm at
  its committed K_MONSTER `sSize` (`worm_drawn`): the four NPC clip scenes end
  with sSize / 100 as their instance scale, the instanced scene keeps 1, and
  the nameplate style's NPC height is the worm skeleton's padded joint height
  times that factor. Their three pins changed for it; no other pin did.

* PQ-296: in each feature cook the target marker's NPC radius and height are
  the worm skeleton's times the same factor (`worm_drawn`), the player's as
  measured. The three feature pins changed for it; no other pin did.

* PQ-301: the marker's and the nameplate style's heights are each skeleton's
  padded joint box top (0041c300's maximum y, which 00459ff0 and 00459820
  read), not the box's Y span: Tuarek 1.7985 m, the worm 0.5256 m before its
  scale. The three feature pins changed for it; no other pin did.

* PQ-361 (D-196): each feature cook (default, classic, 1097) writes 1298's
  tooltip head for the blade, KO item 120110048 (`heads_1298`), and no plain
  cook writes one; `item-heads.bin` is the only new file, and the three
  feature pins changed for it; no other pin did.

* PQ-387 (D-204): every cook whose zone's `.tlt` (Zones.tbl column 5) holds
  light maps writes them as `world-overlay.bin` (N3WO) with a `world_overlay`
  manifest key, and the client's asset check loads them: 530 for the default
  Moradon (`Moradon_xmas.tlt`), 519 classic, 394 for the 1097 Moradon, 3,649
  and 4,062 for keys 10 and 20. The 1097 homelands' files are patch tables
  only, so they write none and keep their pins; every other pin changed.

* PQ-395 (D-206): each Moradon cook (default, classic, 1097) places the magic
  anvil, which 1298 shows while its object NPC is in, with two first-frame fx
  parts (`NPC_SHOWN_SHAPES`); the six Moradon pins changed for it, the homeland
  pins did not.

Without `assets/ko` it prints SKIP lines: no KO data is committed.
`tests/ko_terrain.py` (so `make test`) runs it last; it also runs alone.
"""
import json, math, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))

CLIENT = Path("assets/ko")
# PQ-288 (D-181) changed the three feature pins (the worm drawn at its sSize):
# default f37f5afd... -> 56fd4e8a..., classic f6cbb167... -> ecbb7a81..., 1097
# f4dbf533... -> c1d4562a...; every plain and homeland pin is unchanged.
# PQ-296 changed them again (the target marker's NPC profile at the worm's
# drawn size): default 56fd4e8a... -> 8c84230c..., classic ecbb7a81... ->
# 4303c8fe..., 1097 c1d4562a... -> cc6bd46c...; no other pin changed.
# PQ-301 changed them again (the marker's and the nameplate style's heights are
# the padded joint box top, not its span): default 8c84230c... -> 4329d647...,
# classic 4303c8fe... -> 8b3808e0..., 1097 cc6bd46c... -> 26732a26...; no other
# pin changed.
# PQ-211 changed them again (the blade's appearance rows name KO item 120110048,
# so effects.bin is N3E2 with its weapon effect): default 4329d647... ->
# b41d125a..., classic 8b3808e0... -> fb947ea0..., 1097 26732a26... -> 580320c8...;
# no other pin changed.
# PQ-361 (D-196) changed them again (the blade, KO item 120110048, draws 1298's
# tooltip head: item-heads.bin is the only new file): default b41d125a... ->
# 296e0396..., classic fb947ea0... -> 3030a3b0..., 1097 580320c8... ->
# 315d0858...; no other pin changed (the glow cook writes its own heads).
# PQ-376 (D-200) changed them again (the blade's weapon effects carry 1298's
# alpha-list sort records, so effects.bin is N3E5): default 296e0396... ->
# bcfbedb4..., classic 3030a3b0... -> ea05b811..., 1097 315d0858... ->
# 6e3d4f07...; no other pin changed.
# PQ-379 (D-201) changed every pin: each map's RF_ALPHABLENDING parts are alpha
# parts, so world-lod.bin is N3L4 (Moradon) and world.bin N3W3 (the
# homelands). Default plain 21d8fadc... -> 3bdc8ec8..., features bcfbedb4... ->
# 1e03e3d8...; classic 4aaf6497... -> caa0e2b1..., ea05b811... -> 4b5119d6...;
# 1097 5139886e... -> 15a307c2..., 6e3d4f07... -> 225df17e...; homelands 10
# 0749ea1a... -> 8fc1d698..., 20 1ec7dd8e... -> d6df67c7...; 1097 homelands 1
# f738e239... -> 3f906ded..., 2 545892e0... -> 2ed2d640....
# PQ-382 (D-202) changed every pin again: each map's opaque object parts set the
# cut-at-zero bit (RF_NOTUSELIGHT ones the unlit bit too), so world-lod.bin is
# N3L5 (Moradon) and world.bin N3W4. Default plain 3bdc8ec8... -> ef2c41f2...,
# features 1e03e3d8... -> df94bc8d...; classic caa0e2b1... -> 7b6d4b4d..., 4b5119d6... ->
# be460aa0...; 1097 15a307c2... -> cdcde6cb..., 225df17e... -> 7dfbe7c6...; homelands 10
# 8fc1d698... -> 1ee5d636..., 20 d6df67c7... -> 45036903...; 1097 homelands 1 3f906ded... ->
# 6afc705a..., 2 2ed2d640... -> b1904988....
# PQ-384 changed homeland 10 only (1ee5d636... -> 8a20a975...): karus2004's six
# tiles whose tex1 is not a tile texture draw its colour map (005a2640), and the
# texture table's slots are numbered without their unused tex2.
# PQ-388 (D-203) changed homeland 10 only (8a20a975... -> 6f772995...): those six
# tiles are single-layer unlit vertices (the colour-map texel without the light),
# so its world.bin is N3W5.
# PQ-387 (D-204) changed every pin of a zone with light maps (its .tlt, Zones.tbl
# column 5, cooks to world-overlay.bin, the only new file): default plain
# ef2c41f2... -> 62a8c6cd..., features df94bc8d... -> 38a3f69a...; classic
# 7b6d4b4d... -> cd1dc1d3..., be460aa0... -> 73f8ddb9...; 1097 cdcde6cb... ->
# 9679c435..., 7dfbe7c6... -> 9b0d4b0d...; homelands 10 6f772995... -> 1eaba55e...,
# 20 45036903... -> f1a96c6a.... The 1097 homelands have none and keep their pins.
# PQ-392 (D-205) changed every pin: each map's bind points and warp gates (event
# types 0 and 5, shown at load by 005b4690) are placed, their magic part an alpha
# part drawn with its first texture (EVENT_SHAPES). Default plain 62a8c6cd... ->
# 67677d2b..., features 38a3f69a... -> f719d190...; classic cd1dc1d3... ->
# 7b689a9f..., 73f8ddb9... -> c2354f3a...; 1097 9679c435... -> edb67aee...,
# 9b0d4b0d... -> 21694c9c...; homelands 10 1eaba55e... -> f3d8d25c..., 20
# f1a96c6a... -> 4784acfc...; 1097 homelands 1 6afc705a... -> e864c5cb..., 2
# b1904988... -> 5d9b7fe8....
# PQ-395 (D-206) changed the six Moradon pins: the magic anvil (event type 8,
# status 1, 0x1000; 005cd620 at 005ce447) is placed in its object NPC's state,
# its two fx parts on their first texture (NPC_SHOWN_SHAPES). Default plain
# 67677d2b... -> 5135a615..., features f719d190... -> 511b15ee...; classic
# 7b689a9f... -> d793e0d0..., c2354f3a... -> 8b9a4e42...; 1097 edb67aee... ->
# af10f571..., 21694c9c... -> ac753299...; the homeland pins are unchanged.
# PQ-407 (D-210) changed every pin: each KO HUD ends with the message block
# (N3HM: five rows, 0xffffff00 for both kinds; hud.bin only). Default plain
# 5135a615... -> 4fefc9ba..., features 511b15ee... -> 78650b2b...; classic
# d793e0d0... -> a6467949..., 8b9a4e42... -> 4f4992b3...; 1097 af10f571... ->
# ac680e7b..., ac753299... -> a95f209d...; homelands 10 f3d8d25c... -> 1756e1c3...,
# 20 4784acfc... -> e3845015...; 1097 homelands 1 e864c5cb... -> d8365ac3..., 2
# 5d9b7fe8... -> 766f6186....
# PQ-408 (D-211) changed every pin: the message window's scroll child becomes
# the message line's scroll records (buttons, track click, thumb) and each KO
# HUD ends with the scroll block (N3HS: 255, 100, 1, 2, 0.5 s; hud.bin only).
# Default plain 4fefc9ba... -> 386bc5f8..., features 78650b2b... -> 2a53ef30...;
# classic a6467949... -> 75adb1bb..., 4f4992b3... -> d8d4a47a...; 1097
# ac680e7b... -> 7c38f866..., a95f209d... -> 6349910a...; homelands 10
# 1756e1c3... -> 7e2caec7..., 20 e3845015... -> e1951c2d...; 1097 homelands 1
# d8365ac3... -> 8c3941b6..., 2 766f6186... -> 02ec4518....
# PQ-394 (D-212) changed every pin: each placed multi-texture part with an fps
# above 0 (the magic parts, the anvil's fx parts) carries its texture sequence
# (N3W6), and its other frame textures join world-textures.bin; only world.bin,
# world-textures.bin, recipe.json and the release index change. Default plain
# 386bc5f8... -> 7f4a3d19..., features 2a53ef30... -> 718623e6...; classic
# 75adb1bb... -> 609eae32..., d8d4a47a... -> 670b6835...; 1097 7c38f866... ->
# 3743e174..., 6349910a... -> 478cfcd0...; homelands 10 7e2caec7... -> 21d009f6...,
# 20 e1951c2d... -> b006d37d...; 1097 homelands 1 8c3941b6... -> 8cb0f2e4..., 2
# 02ec4518... -> dbb1ee41....
# PQ-412 (D-213) changed the pins of the cooks whose map has a static shape
# with a cycling part that does not billboard (MATERIAL_SHAPES): it is placed,
# its cycling part with its sequence; again only world.bin, world-textures.bin,
# recipe.json and the release index change. Classic 609eae32... -> 41f021ea...,
# 670b6835... -> 2478c91a...; 1097 3743e174... -> ef6a5924..., 478cfcd0... ->
# 76fa0b4a...; homeland 20 b006d37d... -> 7a379d6c...; 1097 homelands 1
# 8cb0f2e4... -> c95003e9..., 2 dbb1ee41... -> d3d61037.... The default Moradon
# (moradon_xmas) and homeland 10 (karus2004) have none and keep their pins.
# PQ-347 changed the three --features pins: games/moradon/combat-animation.json
# gains a sixth profile, bow (1298's ready 92 and archery clip 26, 1450 ms), so
# every feature cook carries two more player clips (combat-26, combat-92), the
# profile in combat-animation.bin and its audio timings; no default row selects
# it (only the --glow-2233 cook adds bow rows). Default features 718623e6... ->
# 265c8825...; classic 2478c91a... -> 41c6aab7...; 1097 76fa0b4a... -> 887fbfd6....
# The plain cooks and the homelands keep their pins.
# PQ-465 (D-232) changed the three --features pins: skills.bin is N3K2 with
# games/moradon/skills.json's reach (start 2, hold 15, the ground plane).
# Default features 265c8825... -> f69de0ff...; classic 41c6aab7... ->
# 7c2ef975...; 1097 887fbfd6... -> 258c257f.... The plain cooks and the
# homelands keep their pins.
# PQ-466 (D-234) changed the three --features pins: skills.bin is N3K3 with
# the client's too-far notice, the player's 1298 text 4009 (ko_skills.py).
# Default features f69de0ff... -> 2d0620da...; classic 7c2ef975... ->
# 4bc17ca6...; 1097 258c257f... -> a02f0c6c.... The plain cooks and the
# homelands keep their pins.
# PQ-469 (D-235) changed the three --features pins again: skills.bin is N3K4
# with the client's failed line, the player's 1298 text 4004 in 0xffff3b3b.
# Default features 2d0620da... -> 7cbf2e59...; classic 4bc17ca6... ->
# 428a812b...; 1097 a02f0c6c... -> cd563e3d.... The plain cooks and the
# homelands keep their pins.
# PQ-479 (D-243) changed the three --features pins again: skills.bin is N3K5
# with five refusal lines, the player's 1298 texts 4003, 3004 and 4005 in
# 0xffffff00 and 4002 (twice) in 0xffff3b3b. Default features 7cbf2e59... ->
# bc6493df...; classic 428a812b... -> df3cdb80...; 1097 cd563e3d... -> dc494e1f....
# The plain cooks and the homelands keep their pins.
# Spec 11 (M4c) changed the three --features pins: front-end.bin (N3FE, KO's
# login, select, create and loading screens) makes the package engine 42 and
# wire 30. Default features bc6493df... -> 38654bcd...; classic df3cdb80... ->
# 5f0792a5.... The 1097 pin (dc494e1f...) was not recut: the 1097 install was
# not unpacked on the machine that made this change, so that check SKIPs there
# and fails where it runs until it is recut. The plain cooks and the homelands
# keep their pins.
# Q61 (M4c) changed the two recut --features pins: the login screen keeps KO's
# labels, copyright line, Option and Registration, without the added notice
# line. Default features 38654bcd... -> 4c1008e3...; classic 5f0792a5... ->
# ba567f16.... The 1097 pin is still not recut (no install here, as above).
# N3FE version 2 changed them again: the create screen's own model (the looks
# row's joint and animation, ANI_BREATH, no plugs). Default features 4c1008e3...
# -> c3dfc2bd...; classic ba567f16... -> 0f8ade92....
# RQ-020 recut the 1097 --features pin with the 1097 install unpacked:
# dc494e1f... -> 2fb34600..., covering every front-end change above at once.
# The pre-M4c tree (854c5f5^) still cooks dc494e1f...; against it the new cook
# differs only by front-end.bin (byte-identical to the default --features
# cook's), engine 36 -> 42, wire 29 -> 30 and their recipe and provenance
# entries. The 1097 plain pin and the homelands keep their pins.
# RQ-018 (Q57) changed the three --features pins: front-end.bin is N3FE version 3
# with the screens' music (KO's Snd/Intro_Sound.mp3 frames, looping on login,
# select and create); against the earlier cooks only front-end.bin (the version
# word and the appended section, 1,712,001 bytes), recipe.json and the release
# index change. Default features c3dfc2bd... -> 82d75a6a...; classic 0f8ade92...
# -> 9c3e3d02...; 1097 2fb34600... -> 5f715c99.... The plain cooks and the
# homelands keep their pins.
# RQ-075 (Q71, KO-FINDINGS 8.1) changed the three --features pins: front-end.bin
# is N3FE version 4, with each model clip's blend time, the select spot's growth
# rate and the select model's third clip (dummy). Default features 82d75a6a...
# -> 5d175721...; classic 9c3e3d02... -> 61fc225d...; 1097 5f715c99... ->
# 9d8fa202.... The plain cooks and the homelands keep their pins.
# RQ-076 (KO-FINDINGS 8.1, 0043ea30) changed the three --features pins: the select
# model's start clip blends over the select's own 0.6 s (`start_blend`), not its
# record's 0.3 s. Against the earlier cooks only that real in front-end.bin
# (0x3e99999a -> 0x3f19999a), recipe.json and the release index change. Default
# features 5d175721... -> f89bdc01...; classic 61fc225d... -> 128d73ba...; 1097
# 9d8fa202... -> 07000937.... The plain cooks and the homelands keep their pins.
PINS = {
    "plain": ([], "7f4a3d194954284e26cb72685d66d0e061cd887fb87109b25536de3654908b82"),
    "features": (["--features"], "f89bdc013b44b0b4fbe1c53ebb4210dbf812af7915639a9a02811d3592a16632"),
}
OUT = Path("build/ko-bake-pin")
# PQ-051: key -> (ko_start.row_digest of the zone's START_POSITION row, release).
HOMELAND_PINS = {
    10: ("4277972af5be610c14805b0935fc39732276f5d8641262b195bea39eb5a1fa95",
         "21d009f61818cc752903c121679e56078ddf9a5f2953dc96269f4059441cccc3"),
    20: ("b1142eb867dee95021d34aaade2f74155015fa8450b60771206170fc2cf6c98e",
         "7a379d6c6805384b0f85dcc46c024e39aaf38cc43340e4d6141472cf3acb3485"),
}
# PQ-274: the 1097 homelands, pinned the same way (their zone 1 and 2 rows are the
# same rows as keys 10 and 20 read). PQ-290 (D-180) changed key 1 (cc275d26... ->
# f738e239...): its world reads obj_ka_tree_brA's trunk mesh from the 2004 client.
HOMELAND_1097_PINS = {
    1: ("4277972af5be610c14805b0935fc39732276f5d8641262b195bea39eb5a1fa95", "c95003e9d4d7ebdebda067735abe5140964abcd5323ed8bfd2a2ea0c27223d69"),
    2: ("b1142eb867dee95021d34aaade2f74155015fa8450b60771206170fc2cf6c98e", "d3d61037bab416c33a012a23469a173d0c2e374e19311b23a1a99d07f8ddc3a9"),
}
INSTALL_1097 = Path("build/ko-reference/installer-1097")
# PQ-223: the classic Moradon (ko_bake.py 210 --layout=classic), pinned as Moradon's are.
CLASSIC_PINS = {
    "plain": ([], "41f021ea24a1991b4928c94657e077e67a36017bea3fa49c66c5c1d1aa6c95d2"),
    "features": (["--features"], "128d73baec694f83a63529ff75cdae4ea80d761de4f34066a9b40ab62d92e89c"),
}
INSTALL_1264 = Path("build/ko-reference/installer-1264")
# PQ-224: the 1097 Moradon (ko_bake.py 21 --client=1097), pinned as Moradon's are.
MORADON_1097_PINS = {
    "plain": ([], "ef6a59243cd2b8b8d434de5e8c76a999019528ef07e98e01107c3dfc027ca1f3"),
    "features": (["--features"], "070009372937775298501094d565e0e9fdd10b82646bb05cff161c2a01390348"),
}


# PQ-392 (D-205): the bind points and warp gates (event types 0 and 5) each cook
# places, with one magic part each, which cycles its textures since PQ-394
# (D-212; a `sequence_parts` count, none left on its first frame) (local-asset counts: moradon_xmas
# and moradon two warp gates, the 1097 Moradon the same two; karus2004 and
# elmo2004 4 bind points and 7 warp gates; 1097 karus_start and elmorad_start 4
# and 6). obj_co_itemup, type 8, is placed since PQ-395 (NPC_SHOWN_SHAPES); the
# 1097 gate doors, type 1, stay out.
EVENT_SHAPES = {"moradon": 2, "moradon-classic": 2, "moradon-1097": 2, 10: 11, 20: 11, 1: 10, 2: 10}
# PQ-395 (D-206): the magic anvil (obj_co_itemup, event 5001, type 8, status 1,
# 0x1000), drawn as its object NPC shows it, in each Moradon cook (local-asset:
# 1298 moradon_xmas and moradon, the 1097 moradon, one each), with two
# fx parts (5 and 10 textures at 8 fps) that cycle since PQ-394; no homeland has
# one.
NPC_SHOWN_SHAPES = {"moradon": 1, "moradon-classic": 1, "moradon-1097": 1, 10: 0, 20: 0, 1: 0, 2: 0}
# PQ-412 (D-213): the static shapes whose cycling part does not billboard, one
# cycling part each (local-asset): the 1298 Moradon's bridge (obj_mora_bri, two
# frames naming one texture, opaque), the 1097 Moradon's dungeon gate
# (obj_dun_dungate, its fire 14 frames at 7 fps, 0x5), elmo2004's two pond
# drops (12 at 7 fps, 0x41), the 1097 homelands' waterfalls and their fog
# (karus_start 6, elmorad_start 4, 16 or 17 at 10 fps, 0x3). moradon_xmas and
# karus2004 have none; their other cycling parts billboard (PQ-413).
MATERIAL_SHAPES = {"moradon": 0, "moradon-classic": 1, "moradon-1097": 1, 10: 0, 20: 2, 1: 6, 2: 4}


def event_shapes(name, report):
    objects = report["visuals"]["objects"]
    want, anvils, material = EVENT_SHAPES[name], NPC_SHOWN_SHAPES[name], MATERIAL_SHAPES[name]
    assert (objects["event_shapes"], objects["npc_shown_shapes"], objects["material_shapes"],
            objects["first_frame_parts"], objects["sequence_parts"]) == \
        (want, anvils, material, 0, want + 2 * anvils + material), (name, objects)
    return want


def worm_drawn(package, report):
    """PQ-288: a feature cook draws its one NPC set (the worm) at its K_MONSTER
    sSize: each of the four clip scenes ends with that factor as its instance
    scale (then the attachment node), the instanced scene keeps 1, and the
    nameplate style's NPC height is the worm skeleton's (0041c300 joint bounds,
    padded) times the factor; since PQ-296 so is the target marker's NPC
    radius and height. Returns the factor."""
    import struct
    import ko_character, moradon_features
    size = moradon_features.reference()["monster"]["sSize"]
    factor = struct.unpack("<f", struct.pack("<f", size / 100))[0]
    for name in ("npc-idle.bin", "npc-walk.bin", "npc-attack.bin", "npc-death.bin"):
        assert struct.unpack("<3f", (package / name).read_bytes()[-16:-4]) == (factor,) * 3, name
    assert struct.unpack("<3f", (package / "scene.bin").read_bytes()[-16:-4]) == (1.0,) * 3
    assert report["features"]["npc_drawn_scale"] == {"sSize": size, "instance_scale": size / 100}, report["features"]
    names = report["hud"]["nameplates"]
    world = []
    for bone in ko_character.skeleton(ko_character.Assets(CLIENT.resolve()).get("Chr/mob_worm.n3joint")):
        m = ko_character.matrix(*ko_character.converted(bone, 0, 1.))
        world.append(ko_character.multiply(world[bone["parent"]], m) if bone["parent"] >= 0 else m)
    # PQ-301: the name height is the padded joint box's top (0041c300's maximum
    # y, character +0x12c, which 00459820 reads as actor +0x17c), not its span:
    # the worm's joints span under 0.5 m, so its box grows 0.25 m at each end.
    low, high = min(m[1][3] for m in world), max(m[1][3] for m in world)
    assert high - low < .5, (low, high)
    assert names["npc_scale"] == size / 100 and names["profiles"][1] == [(high + .25) * (size / 100), 0], names
    # PQ-296: the target marker's NPC profile is the worm skeleton's radius and
    # height (padded joint box top, PQ-301) times the factor, the player's as measured;
    # KO's symbol multiplies the actor's radius and height by its scale +0x90
    # (005c4e20 -> 0045a1d0, 00459ff0).
    config = json.loads(Path("games/moradon/target-marker.json").read_text())
    measured = []
    for skeleton in config["skeletons"]:
        world = []
        for bone in ko_character.skeleton(ko_character.Assets(CLIENT.resolve()).get(skeleton)):
            m = ko_character.matrix(*ko_character.converted(bone, 0, 1.))
            world.append(ko_character.multiply(world[bone["parent"]], m) if bone["parent"] >= 0 else m)
        spans = [max(m[a][3] for m in world) - min(m[a][3] for m in world) for a in range(3)]
        top = max(m[1][3] for m in world) + (.25 if spans[1] < .5 else 0)
        spans = [v + .5 if v < .5 else v for v in spans]
        # PQ-301: the radius (half the padded diagonal, +0x118) and the padded
        # box top (+0x12c), as 0045a1d0 and 00459ff0 return them.
        measured.append([math.sqrt(sum(v * v for v in spans)) * .5, top])
    # The tops PQ-301 measured on the player's client (frame-0 joints): Tuarek
    # 1.7985 m (its Y span is 1.9377 m), the worm 0.5256 m (padded span 0.7385 m).
    assert [round(v[1], 4) for v in measured] == [1.7985, 0.5256], measured
    marker = report["target_marker"]
    expected = [measured[0], [v * (size / 100) for v in measured[1]]]
    assert marker["npc_scale"] == size / 100 and marker["measured_profiles"] == measured, marker
    assert marker["profiles"] == expected, (marker["profiles"], expected)
    stored = struct.unpack("<4f", (package / "target-marker.bin").read_bytes()[16:32])
    assert stored == struct.unpack("<4f", struct.pack("<4f", *expected[0], *expected[1])), stored
    return size / 100


def heads_1298(package, report, features):
    """PQ-361 (D-196): a feature cook writes 1298's tooltip head for its one KO
    item, the blade (120110048, Short Blade(+8), Item_Ext_1 row 48, attribute
    5): c87cc7, "(Upgrade Item)" c87cc7, "One-handed Sword" ffffff, no token;
    a plain cook has no inventory and writes none."""
    import item_heads
    if not features:
        assert not (package / "item-heads.bin").exists() and "item_heads_1298" not in report
        return
    assert item_heads.parse((package / "item-heads.bin").read_bytes(), "demo", {"demo:item/blade"}) == (
        "", {"demo:item/blade": (0xc87cc7, [("(Upgrade Item)", 0xc87cc7), ("One-handed Sword", 0xffffff)])})
    (record,) = report["item_heads_1298"]
    assert (record["ko_item"], record["item_ext"], record["attribute"], record["ko_name"], record["texts"]) == (
        120110048, "Item_Ext_1 row 48", 5, "Short Blade(+8)", [6812, 2529]), record


if not (CLIENT / "Data" / "Zones.tbl.csv").is_file():
    print("SKIP Moradon release pins: local KO client data absent")
    print("SKIP OPDEXT zones: local KO client data absent")
    print("SKIP homeland packages (keys 10, 20): local KO client data absent")
    sys.exit(0)

import ko_zone

_, rows = ko_zone.table(CLIENT)
keys = [int(r[0]) for r in rows[1:] if len(r) > ko_zone.OPDEXT and r[ko_zone.OPDEXT] != ko_zone.RESERVED
        and r[ko_zone.OPDEXT].strip().lower().endswith(".opdext")]
assert keys, "the local Zones.tbl names no OPDEXT"
for key in keys:
    zone = ko_zone.select(CLIENT, key)
    record = zone["provenance"]["opdext"]
    assert record["effective_name"].lower() == zone["row"][ko_zone.NAME].lower(), (key, record)
    assert zone["extension"]["merged"]["baked_faces"] > 0, key
print("PASS OPDEXT zones %s select, read their OPDEXT against the OPD and pass the merged "
      "name check" % ", ".join(map(str, keys)))

# PQ-387 (D-204): the light maps each cook's .tlt holds (PQ-385 claims 19-21,
# local-asset), by (key, zone layout); none for the 1097 homelands, which then
# write no world-overlay.bin.
LIGHT_MAPS = {(10, None): 3649, (20, None): 4062, (1, "1097"): 0, (2, "1097"): 0}


def overlay_checks(maps, root, package, report, manifest, lines):
    """PQ-387: the cook's light maps as N3WO: the file and its manifest key
    exactly when the zone has maps, and the client's asset check line."""
    assert report["light_maps"]["maps"] == maps and report["light_maps"]["version"] == 0, report["light_maps"]
    shown = [line for line in lines if line.startswith("world overlay ")]
    if maps:
        assert manifest["world_overlay"] == "world-overlay.bin" and (package / "world-overlay.bin").is_file()
        assert shown == ["world overlay maps %d side 32 levels 4 window 1 layers 36" % maps], shown
    else:
        assert "world_overlay" not in manifest and not (root / "world-overlay.bin").exists(), manifest
        assert not (package / "world-overlay.bin").exists() and shown == [], shown


for name, (flags, pinned) in PINS.items():
    run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", "210", *flags,
                          "--into=%s" % (OUT / name)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-2000:]
    released = [line for line in run.stdout.splitlines() if re.fullmatch(r"[0-9a-f]{64}", line)]
    assert released == [pinned], (name, released, pinned)
    provenance = json.loads((OUT / name / "ko-moradon" / "provenance.json").read_text())
    event_shapes("moradon", provenance)
    heads_1298(OUT / name / "packages" / "moradon", provenance, bool(flags))
    # PQ-387: Moradon_xmas.tlt's 530 light maps (key 210's column 5).
    check = subprocess.run(["build/client/n3e-asset-check", str(OUT / name / "packages" / "moradon")],
                           capture_output=True, text=True)
    assert check.returncode == 0, check.stderr[-2000:]
    overlay_checks(530, OUT / name / "ko-moradon", OUT / name / "packages" / "moradon", provenance,
                   json.loads((OUT / name / "ko-moradon" / "package.json").read_text()), check.stdout.splitlines())
    if flags:
        drawn = worm_drawn(OUT / name / "packages" / "moradon", provenance)
print("PASS Moradon (key 210, Reserved) cooks to the pinned release hashes: plain/--preview "
      "%s..., --features %s... (the worm drawn at %g: clip scenes, NPC name height and target marker; "
      "the blade's 1298 tooltip head, PQ-361)"
      % (PINS["plain"][1][:8], PINS["features"][1][:8], drawn))

# PQ-217 (with PQ-234's N3W2 branch): each homeland through the bake command,
# which surveys both nations' START_POSITION areas on the 513-sample map.
import hashlib, json, os, struct, time
import ko_start, ko_terrain, world_textures
import ko_bake as ko_bake_1097

# (key, nation, --client, package): the 2004 homelands, then the 1097 ones (PQ-274).
HOMELANDS = [(10, "karus", None, "ko-zone-10"), (20, "elmorad", None, "ko-zone-20"),
             (1, "karus", "1097", "ko-1097-zone-1"), (2, "elmorad", "1097", "ko-1097-zone-2")]
SIDES = {10: 512, 20: 1024, 1: 1024, 2: 1024}  # overview map pixels a side, by key


def probe(package, queries):
    """The cooked collision's ground and one walk step, on both runtimes."""
    path = OUT / "probe.txt"
    path.write_text("".join("%r %r %r %r 0 1\n" % q for q in queries))
    both = [subprocess.run(cmd + [str(package / "collision.bin"), str(path)], capture_output=True, text=True,
                           check=True).stdout.splitlines()[1:]
            for cmd in (["build/client/n3e-collision-check", "probe"], ["target/debug/n3e-server", "--collision-probe"])]
    assert both[0] == both[1], both
    return [list(map(float, line.split())) for line in both[0]]


# Without the operator's START_POSITION export (or without its row) a homeland
# is refused before anything is cooked: no START_POSITION data is committed.
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "no-zone-1.json").write_text("[]")
for flag, phrase in (("--start-positions=%s" % (OUT / "absent.json"), "there is no START_POSITION export"),
                     ("--start-positions=%s" % (OUT / "no-zone-1.json"), "has none for zone 1")):
    run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", "10", flag, "--into=%s" % (OUT / "refused")],
                         capture_output=True, text=True)
    assert run.returncode != 0 and phrase in run.stderr, (flag, run.stdout[-500:], run.stderr[-1000:])
    assert not (OUT / "refused" / "packages").exists()
print("PASS homeland key 10 refused without the operator's START_POSITION export or its zone row")
# PQ-274: the 1097 key 1 the same way (zone 1: its keys are the zone ids), or,
# without the unpacked 1097 install, refused for that by name.
for flag, phrase in (("--start-positions=%s" % (OUT / "absent.json"), "there is no START_POSITION export"),
                     ("--start-positions=%s" % (OUT / "no-zone-1.json"), "has none for zone 1")):
    run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", "1", "--client=1097", flag,
                          "--into=%s" % (OUT / "refused")], capture_output=True, text=True)
    want = phrase if (INSTALL_1097 / "manifest.json").is_file() else "no 1097 install"
    assert run.returncode != 0 and want in run.stderr, (flag, run.stdout[-500:], run.stderr[-1000:])
    assert not (OUT / "refused" / "packages").exists()
print("PASS 1097 key 1 refused %s" % ("without the operator's START_POSITION export or its zone row"
                                       if (INSTALL_1097 / "manifest.json").is_file() else
                                       "without the unpacked 1097 install"))


# PQ-388 (D-203): homelands with single-layer unlit colour-map tiles, by
# (key, zone layout): karus2004's six east-edge tiles (PQ-384).
UNLIT_TILES = {(10, None): 6}
def world_checks(key, root, package, report, manifest):
    """PQ-234's N3W2 package checks: N3W2 with N3WT textures and N3C2 collision,
    no N3L3, the N3HE overview map, and the client's asset and server's content
    checks. Returns (the world's magic and its chunks line, textures, banks,
    map side)."""
    assert manifest["world"] == "world.n3world" and manifest["world_textures"] == "world-textures.bin", manifest
    assert "lod" not in manifest["exploration"] and not (root / "world-lod.bin").exists(), manifest["exploration"]
    assert not (package / "world-lod.bin").exists()
    world = (package / "world.bin").read_bytes()
    textures = (package / "world-textures.bin").read_bytes()
    count, banks, pixels = world_textures.check(textures)
    # PQ-379 (D-201): N3W3 when the zone has alpha parts (every homeland does);
    # PQ-382 (D-202): N3W4, since every homeland has opaque object parts;
    # PQ-388 (D-203): N3W5 for karus2004 (key 10), whose six east-edge
    # colour-map tiles are single-layer unlit vertices; no other homeland has one.
    # PQ-394 (D-212): N3W6 when the zone has texture sequences (every homeland's
    # magic parts), whatever its vertices.
    unlit_tiles = UNLIT_TILES.get((key, report["zone"].get("layout")), 0)
    assert report["visuals"]["terrain"]["tiles_unlit"] == unlit_tiles, report["visuals"]["terrain"]
    sequences = report["visuals"]["objects"]["sequence_parts"]
    assert world[:4] == (b"N3W6" if sequences else b"N3W5" if unlit_tiles else b"N3W4"), world[:4]
    assert struct.unpack_from("<I", world, 4)[0] == count == report["world_textures"]["textures"]
    assert (package / "collision.bin").read_bytes()[:4] == b"N3C2"
    magic = world[:4].decode()
    detail = (package / "render-detail.bin").read_bytes()
    # N3D1: magic, view (3 f32), thresholds (16 f32), workload (3 u32), world subset count.
    assert detail[:4] == b"N3D1" and struct.unpack_from("<I", detail, 4 + 12 + 64 + 12)[0] == 1
    del world, textures, detail
    # The overview map (Zones.tbl column 8) on the basic HUD: N3HE, its DXT1
    # at full size, placed over the whole 2048 m map.
    minimap = report["hud"]["minimap"]
    side = SIDES[key]
    assert (package / "hud.bin").read_bytes()[:4] == b"N3HE" and minimap["zone_key"] == key
    assert minimap["origin"] == [-1024.0, -1024.0] and minimap["extent"] == 2048.0, minimap
    import ko_tiles
    assert ko_tiles.texture(Path(report["zone"]["files"]["minimap"]).read_bytes())[:2] == (side, side)
    check = subprocess.run(["build/client/n3e-asset-check", str(package)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout[-2000:] + check.stderr[-2000:]
    lines = check.stdout.splitlines()
    assert ("world textures %d banks %d pixels %d" % (count, banks, pixels)) in lines, lines[:6]
    # PQ-394: the client loads every sequence the report counts.
    assert sum(1 for line in lines if line.startswith("world sequence parts %d first " % sequences)) == \
        (1 if sequences else 0), (sequences, [line for line in lines if line.startswith("world sequence")])
    chunks = [line for line in lines if line.startswith("world chunks ")]
    unlit = [line for line in lines if line.startswith("world unlit vertices ")]
    assert unlit == (["world unlit vertices %d" % (4 * unlit_tiles)] if unlit_tiles else []), unlit
    overlay_checks(LIGHT_MAPS[(key, report["zone"].get("layout"))], root, package, report, manifest, lines)
    server = subprocess.run(["target/debug/n3e-server", "--check-content"], capture_output=True, text=True,
                            env={**os.environ, "N3E_PACKAGE": str(package)})
    assert server.returncode == 0, server.stdout[-2000:] + server.stderr[-2000:]
    return "%s (%s)" % (magic, chunks[0] if chunks else "?"), count, banks, side


# PQ-223 (D-171): the classic Moradon beside the default.
import ko_bake as ko_bake_classic, moradon_features
for name, (flags, pinned) in CLASSIC_PINS.items():
    started = time.monotonic()
    out = OUT / ("classic-" + name)
    run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", "210", "--layout=classic", *flags,
                          "--into=%s" % out], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    released = [line for line in run.stdout.splitlines() if re.fullmatch(r"[0-9a-f]{64}", line)]
    assert released == [pinned], (name, released, pinned)
    assert not (out / "packages" / "moradon").exists() and not (out / "ko-moradon").exists()
    root, package = out / "ko-moradon-classic", out / "packages" / "moradon-classic"
    report = json.loads((root / "provenance.json").read_text())
    event_shapes("moradon-classic", report)
    manifest = json.loads((root / "package.json").read_text())
    zone = report["zone"]
    stem, hashes = ko_bake_classic.MORADON_LAYOUTS["classic"]
    assert zone["variant"]["layout"] == "classic" and zone["variant"]["stem"] == stem == "Moradon", zone["variant"]
    assert zone["variant"]["table_stem"] == "Moradon_xmas" and zone["variant"]["sha256"] == hashes, zone["variant"]
    assert sorted(Path(f).name for f in zone["files"].values()) == [
        "moradon.dxt", "moradon.gtd", "moradon.opd", "moradon.tct"], zone["files"]
    assert zone["names"] == {"gtd": "moradon", "opd": "moradon"} and zone["columns"]["7"] == "Reserved", zone
    references = report["references"]
    assert references["missing"] == [] and references["unreadable_meshes"] == {}, references
    check = subprocess.run(["build/client/n3e-asset-check", str(package)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout[-2000:] + check.stderr[-2000:]
    # PQ-387: the rewritten row's column 5, moradon.tlt (519 light maps, pinned hash).
    assert zone["variant"]["rewritten_columns"]["5"] == ["Zones\\Moradon_xmas.tlt", "Zones\\Moradon.tlt"], zone["variant"]
    overlay_checks(519, root, package, report, manifest, check.stdout.splitlines())
    server = subprocess.run(["target/debug/n3e-server", "--check-content"], capture_output=True, text=True,
                            env={**os.environ, "N3E_PACKAGE": str(package)})
    assert server.returncode == 0, server.stdout[-2000:] + server.stderr[-2000:]
    surveyed = [line for line in run.stdout.splitlines() if line.startswith("surveyed spawn [")]
    printed = [float(v) for v in surveyed[0][len("surveyed spawn ["):-1].split(",")]  # x, z to 0.1 m, y to 0.01 m
    spawn = [manifest["gameplay"]["spawn_x"], printed[1], manifest["gameplay"]["spawn_z"]]
    assert abs(printed[0] - spawn[0]) < 0.051 and abs(printed[2] - spawn[2]) < 0.051, (printed, spawn)
    formats = ((package / "world.bin").read_bytes()[:4].decode(), (package / "collision.bin").read_bytes()[:4].decode())
    detail = ""
    if flags:
        # The feature data on the classic ground: the START_POSITION zone 21 area,
        # the worm rows' areas, the classic route to the second one, its minimap.
        features = report["features"]
        worm_drawn(package, report)  # PQ-288
        heads_1298(package, report, True)  # PQ-361
        x0, z0, x1, z1 = moradon_features.start_area()
        assert features["layout"] == "classic" and x0 <= spawn[0] <= x1 and z0 <= spawn[2] <= z1, (spawn, features)
        assert features["spawn"][0::2] == spawn[0::2] and abs(features["spawn"][1] - spawn[1]) < 0.006, features
        routes = moradon_features.LAYOUT_ROUTES["classic"]
        for worm, route in zip(features["worm"], routes):
            ax0, az0, ax1, az1 = worm["area"]
            assert ax0 <= worm["point"][0] <= ax1 and az0 <= worm["point"][1] <= az1, worm
            assert worm["route"] == route + [worm["point"]], worm
        assert len(features["worm"]) == len(routes) == 2 and routes[1] != moradon_features.ROUTES[1]
        assert report["hud"]["minimap"]["sha256"] == hashes["minimap"], report["hud"]["minimap"]
        detail = "; start KO %.0f,%.0f inside the cook's START_POSITION zone 21 area (+-bRange, PQ-240), worms at %s, classic route %s" % (
            spawn[0] + 256, 256 - spawn[2], [w["point"] for w in features["worm"]], routes[1])
    # The cooked collision agrees with the survey at the start on both runtimes.
    queries = [(spawn[0], spawn[2], dx, dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    for (x, z, dx, dz), answer in zip(queries, probe(package, queries)):
        assert abs(answer[0] - (spawn[1] - 0.1)) < 0.006, (x, z, answer, spawn)
        assert abs(answer[1] - x - 0.15 * dx) < 1e-3 and abs(answer[3] - z - 0.15 * dz) < 1e-3, (x, z, answer)
    print("PASS classic Moradon (key 210 --layout=classic%s) cooks to its pinned release %s... from the "
          "pinned installer's Zones/moradon.* (%d GTT, %d meshes, %d textures referenced, none missing), beside "
          "the default; asset and content checks accept its %s world; its %s collision agrees on both runtimes "
          "at the start%s (%.0f s)"
          % (" ".join([""] + flags), pinned[:8], references["gtt"], references["meshes"], references["textures"],
             formats[0], formats[1], detail, time.monotonic() - started))
row_1298 = ko_zone.restem(ko_zone.row(ko_zone.table(CLIENT)[1], 210), "Moradon")[0]
if (INSTALL_1264 / "client" / "Data" / "Zones.tbl").is_file():
    import ko_tbl
    _, rows_1264 = ko_tbl.load(INSTALL_1264 / "client" / "Data" / "Zones.tbl")
    row_1264 = [repr(v) if isinstance(v, float) else str(v) for v in next(r for r in rows_1264 if r[0] == 210)]
    assert row_1298[:ko_zone.OPDEXT] + row_1298[ko_zone.OPDEXT + 1:] == row_1264, (row_1298, row_1264)
    print("PASS the rewritten key 210 row (Moradon) less column 7 is the 1264 client's own key 210 row, "
          "value for value (local-asset)")
else:
    print("SKIP 1264 key 210 row comparison: the 1264 install is not unpacked at %s" % INSTALL_1264)

# PQ-224 (D-172): the 1097 Moradon (the 1097 table's key 21) beside the default.
if (INSTALL_1097 / "manifest.json").is_file():
    import ko_scene, ko_shapes
    for flags, phrase in ((["--des"], "--des does not combine"), (["--layout=classic"], "does not combine")):
        run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", "21", "--client=1097", *flags,
                              "--into=%s" % (OUT / "refused-1097")], capture_output=True, text=True)
        assert run.returncode != 0 and phrase in run.stderr, (flags, run.stdout[-500:], run.stderr[-1000:])
        assert not (OUT / "refused-1097" / "packages").exists(), flags
    for name, (flags, pinned) in MORADON_1097_PINS.items():
        started = time.monotonic()
        out = OUT / ("moradon-1097-" + name)
        run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", "21", "--client=1097", *flags,
                              "--into=%s" % out], capture_output=True, text=True)
        assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
        released = [line for line in run.stdout.splitlines() if re.fullmatch(r"[0-9a-f]{64}", line)]
        assert released == [pinned], (name, released, pinned)
        assert not (out / "packages" / "moradon").exists() and not (out / "ko-moradon").exists()
        assert not (out / "packages" / "ko-1097-zone-21").exists()
        root, package = out / "ko-moradon-1097", out / "packages" / "moradon-1097"
        report = json.loads((root / "provenance.json").read_text())
        event_shapes("moradon-1097", report)
        manifest = json.loads((root / "package.json").read_text())
        zone = report["zone"]
        # The 1097 table's own key 21 files, headerless, as the pinned installer shipped them.
        assert zone["layout"] == "1097" and zone["zone_key"] == 21, zone
        assert "corrections" not in zone, zone["corrections"]  # PQ-290: it names no corrected file
        assert zone["install"]["installer_sha256"] == ko_bake_1097.INSTALLER_1097_SHA256, zone["install"]
        assert sorted(zone["install"]["files"]) == ["Data/Zones.tbl", "Zones/moradon.dxt", "Zones/moradon.gtd",
                                                    "Zones/moradon.opd", "Zones/moradon.tct",
                                                    "Zones/moradon.tlt"], zone["install"]
        client_1097 = (INSTALL_1097 / "client").resolve()
        assert all(Path(f).resolve().is_relative_to(client_1097) for f in zone["files"].values()), zone["files"]
        # Both read headerless (a headed file is refused with headerless=True, PQ-222).
        assert ko_terrain.header_samples(zone["files"]["gtd"], True) == 129
        ko_shapes.load_collision(zone["files"]["opd"], headerless=True)
        references = report["references"]
        assert references["missing"] == [] and references["unreadable_meshes"] == {}, references
        assert Path(report["character_assets"]).resolve() == CLIENT.resolve(), report["character_assets"]
        # Every world texture source (GTT tiles, object textures, the colour map) is the 1097 install's.
        sources = report["world_textures"]["world_sources"]
        assert sources and all(Path(f).resolve().is_relative_to(client_1097) for f in sources), sources
        check = subprocess.run(["build/client/n3e-asset-check", str(package)], capture_output=True, text=True)
        assert check.returncode == 0, check.stdout[-2000:] + check.stderr[-2000:]
        overlay_checks(394, root, package, report, manifest, check.stdout.splitlines())  # PQ-387
        server = subprocess.run(["target/debug/n3e-server", "--check-content"], capture_output=True, text=True,
                                env={**os.environ, "N3E_PACKAGE": str(package)})
        assert server.returncode == 0, server.stdout[-2000:] + server.stderr[-2000:]
        surveyed = [line for line in run.stdout.splitlines() if line.startswith("surveyed spawn [")]
        printed = [float(v) for v in surveyed[0][len("surveyed spawn ["):-1].split(",")]
        spawn = [manifest["gameplay"]["spawn_x"], printed[1], manifest["gameplay"]["spawn_z"]]
        assert abs(printed[0] - spawn[0]) < 0.051 and abs(printed[2] - spawn[2]) < 0.051, (printed, spawn)
        formats = ((package / "world.bin").read_bytes()[:4].decode(),
                   (package / "collision.bin").read_bytes()[:4].decode())
        detail = ""
        if flags:
            # The feature data on the 1097 ground: the START_POSITION zone 21 area, the
            # worm rows' areas, the routes, the 1097 overview map, the 2004 name rules.
            features = report["features"]
            worm_drawn(package, report)  # PQ-288
            heads_1298(package, report, True)  # PQ-361
            x0, z0, x1, z1 = moradon_features.start_area()
            assert features["layout"] == "1097" and x0 <= spawn[0] <= x1 and z0 <= spawn[2] <= z1, (spawn, features)
            assert features["spawn"][0::2] == spawn[0::2] and abs(features["spawn"][1] - spawn[1]) < 0.006, features
            routes = moradon_features.LAYOUT_ROUTES["1097"]
            for worm, route in zip(features["worm"], routes):
                ax0, az0, ax1, az1 = worm["area"]
                assert ax0 <= worm["point"][0] <= ax1 and az0 <= worm["point"][1] <= az1, worm
                assert worm["route"] == route + [worm["point"]], worm
            assert len(features["worm"]) == len(routes) == 2
            minimap = report["hud"]["minimap"]
            assert minimap["zone_key"] == 21 and minimap["sha256"] == zone["install"]["files"]["Zones/moradon.dxt"]
            assert zone["client_row"]["key"] == 210 and report["party_names"]["zone_key"] == 210, report["party_names"]
            assert report["name_distance"]["zone_key"] == 210, report["name_distance"]
            detail = ("; start KO %.0f,%.0f inside the cook's START_POSITION zone 21 area (+-bRange, PQ-240), worms "
                      "at %s, route %s, the 1097 overview map, the 2004 client's key 210 name rules"
                      % (spawn[0] + 256, 256 - spawn[2], [w["point"] for w in features["worm"]], routes[1]))
        queries = [(spawn[0], spawn[2], dx, dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        for (x, z, dx, dz), answer in zip(queries, probe(package, queries)):
            assert abs(answer[0] - (spawn[1] - 0.1)) < 0.006, (x, z, answer, spawn)
            assert abs(answer[1] - x - 0.15 * dx) < 1e-3 and abs(answer[3] - z - 0.15 * dz) < 1e-3, (x, z, answer)
        print("PASS 1097 Moradon (1097 key 21 --client=1097%s) cooks to its pinned release %s... from the 1097 "
              "table's headerless Zones/moradon.* (the pinned installer's; %d GTT, %d meshes, %d textures "
              "referenced, none missing; all %d world texture sources the 1097 install's), beside the default; asset and content checks accept its %s world; its "
              "%s collision agrees on both runtimes at the start%s (%.0f s)"
              % (" ".join([""] + flags), pinned[:8], references["gtt"], references["meshes"],
                 references["textures"], len(sources), formats[0], formats[1], detail, time.monotonic() - started))
    # The files the 1097 map names, against the 2004 client's files of the same name.
    client_1097 = INSTALL_1097 / "client"
    terrain_1097 = ko_terrain.load(client_1097 / "Zones/moradon.gtd", ko_terrain.CHUNKED_MAX_SAMPLES,
                                   headerless=True)
    named = {"DTex/" + ko_scene._basename(t) for t in terrain_1097["tile_sources"]}
    for shape in ko_shapes.load_shapes(client_1097 / "Zones/moradon.opd", headerless=True)["shapes"]:
        for part in shape["parts"]:
            named.update("Object/" + ko_scene._basename(n) for n in [part["mesh"], *part["textures"]] if n)

    def by_name(root, folder):
        return {f.name.lower(): f for f in (root / folder).iterdir() if f.is_file()}

    folders = {(root, folder): by_name(root, folder) for root in (client_1097, CLIENT) for folder in ("DTex", "Object")}
    differ = absent = 0
    for item in named:
        folder, base = item.split("/")
        theirs = folders[(CLIENT, folder)].get(base)
        if theirs is None:
            absent += 1
        elif hashlib.sha256(theirs.read_bytes()).digest() != hashlib.sha256(
                folders[(client_1097, folder)][base].read_bytes()).digest():
            differ += 1
    assert differ > 0, differ
    print("PASS of the %d files the 1097 Moradon names (GTT, meshes, textures), %d differ in content from the "
          "2004 client's file of the same name and %d have none there (local-asset)" % (len(named), differ, absent))
else:
    print("SKIP 1097 Moradon (1097 key 21): the 1097 install is not unpacked at %s" % INSTALL_1097)

if not ko_start.EXPORT.is_file():
    print("SKIP homeland packages (keys 10, 20): no operator START_POSITION export at %s" % ko_start.EXPORT)
    print("SKIP 1097 homeland packages (keys 1, 2): no operator START_POSITION export at %s" % ko_start.EXPORT)
    # PQ-218 (PQ-217 review): the N3W2 package checks still run on key 10 without
    # the export, through ko_bake.package with no surveyed start (the demo's).
    import ko_bake, main
    started = time.monotonic()
    zone = ko_zone.select(CLIENT, 10)
    root, report = ko_bake.package("games/demo", zone, str(OUT / "no-start" / "ko-zone-10"), None, overview=True)
    package = OUT / "no-start" / "packages" / "ko-zone-10"
    main.cook(root, package)
    manifest = json.loads((root / "package.json").read_text())
    assert "start" not in report
    chunks, count, banks, side = world_checks(10, root, package, report, manifest)
    print("PASS homeland key 10 (karus2004) package without a start: %s, %d N3WT textures in %d banks, "
          "no world-lod.bin, %d-px overview map on N3HE; asset and content checks accept it (%.0f s)"
          % (chunks, count, banks, side, time.monotonic() - started))
    sys.exit(0)
rows, export_sha256 = ko_start.load(ko_start.EXPORT)
for key, nation, client, name in HOMELANDS:
    if client and not (INSTALL_1097 / "manifest.json").is_file():
        print("SKIP 1097 homeland key %d: the 1097 install is not unpacked at %s" % (key, INSTALL_1097))
        continue
    start = time.monotonic()
    run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", str(key),
                          *(["--client=" + client] if client else []), "--into=%s" % OUT],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    released = [line for line in run.stdout.splitlines() if re.fullmatch(r"[0-9a-f]{64}", line)]
    assert len(released) == 1, run.stdout[-2000:]
    root, package = OUT / name, OUT / "packages" / name
    report = json.loads((root / "provenance.json").read_text())
    manifest = json.loads((root / "package.json").read_text())
    event_shapes(key, report)
    zone_id = key if client else key // 10
    # The start: every nation's area held an engine-verified point, each inside its
    # one-sided KO rectangle; the package starts at its own nation's.
    row, record = ko_start.row(key, rows, zone=zone_id), report["start"]
    assert record["row"] == row and record["nation"] == nation and set(record["areas"]) == set(ko_start.NATIONS)
    assert record["export_sha256"] == export_sha256 and record["export"] == str(ko_start.EXPORT), record
    assert record["row_sha256"] == ko_start.row_digest(row), record
    pinned_row, pinned_release = (HOMELAND_1097_PINS if client else HOMELAND_PINS)[key]
    if record["row_sha256"] == pinned_row:
        assert released == [pinned_release], (key, released, pinned_release)
        pin = "pinned release %s..." % pinned_release[:8]
    else:
        print("SKIP homeland key %d release pin: the export's zone %d row is not the pinned one" % (key, zone_id))
        pin = "release %s... (not pinned for this row)" % released[0][:8]
    extent = record["extent_metres"]
    assert extent == 2048.0 and report["extent_metres"] == extent
    for name, (cx, cz) in ko_start.NATIONS.items():
        area = record["areas"][name]
        assert tuple(area["area"]) == ko_start.areas(row, extent)[name]
        kx, kz = area["spawn_ko"]
        assert row[cx] <= kx <= row[cx] + row["bRangeX"] and row[cz] <= kz <= row[cz] + row["bRangeZ"], (name, area)
        assert area["min_away"] > 0.4 and area["worst_return"] < 0.4 and area["crop_points"] <= 196608
    spawn = record["areas"][nation]["spawn"]
    assert [manifest["gameplay"][k] for k in ("spawn_x", "spawn_z")] == [spawn[0], spawn[2]]
    # The cooked N3C2 collision agrees with the survey's soup at both starts:
    # ground under each spawn (the survey stands it 0.1 m above), and a step in
    # every direction moves it, identically in the client and the server.
    queries = [(a["spawn"][0], a["spawn"][2], dx, dz) for a in record["areas"].values()
               for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))]
    for (x, z, dx, dz), answer, area in zip(queries, probe(package, queries),
                                            [a for a in record["areas"].values() for _ in range(4)]):
        assert abs(answer[0] - (area["spawn"][1] - 0.1)) < 1e-3, (x, z, answer, area["spawn"])
        assert abs(answer[1] - x - 0.15 * dx) < 1e-3 and abs(answer[3] - z - 0.15 * dz) < 1e-3, (x, z, dx, dz, answer)
    # PQ-218: the walk target the play stack's live check walks to: an open
    # point the engine solver reached from the start, within the reach of the
    # start area.
    walk, area = record["walk"], record["areas"][nation]["area"]
    assert walk["start"] == spawn and walk["reach"] == 24.0, walk
    tx, tz = walk["target"][0], walk["target"][2]
    assert area[0] - 24 <= tx <= area[2] + 24 and area[1] - 24 <= tz <= area[3] + 24, (walk, area)
    assert abs(walk["distance"] - ((tx - spawn[0]) ** 2 + (tz - spawn[2]) ** 2) ** 0.5) < 1e-6 and walk["distance"] > 8
    assert ((walk["engine_end"][0] - tx) ** 2 + (walk["engine_end"][2] - tz) ** 2) ** 0.5 <= 0.5, walk
    # The world (PQ-234): N3W2 with N3WT textures and N3C2 collision, no N3L3.
    chunks, count, banks, side = world_checks(key, root, package, report, manifest)
    if client:
        # D-170: the 1097 table's own files, headerless, as the installer shipped them;
        # nothing they name missing; the 1097 overview map; the 2004 player and HUD.
        zone = report["zone"]
        assert zone["layout"] == "1097" and zone["install"]["installer_sha256"] == ko_bake_1097.INSTALLER_1097_SHA256
        assert sorted(zone["install"]["files"]) == sorted(["Data/Zones.tbl"] + [
            "Zones/" + Path(zone["files"][k]).name for k in ("gtd", "tct", "opd", "minimap")]
            + ["Zones/" + Path(zone["light_maps"]["file"]).name]), zone["install"]
        assert report["terrain"]["format"] == "N3 GTD headerless (pre-1264)", report["terrain"]["format"]
        assert report["objects"]["format"] == "N3 OPD headerless (pre-1264)", report["objects"]["format"]
        assert report["references"]["missing"] == [], report["references"]
        assert sorted(report["references"]["unreadable_meshes"]) == {
            1: [], 2: ["obj_el_castle02_1_body00.n3pmesh", "obj_el_castle02_2_body00.n3pmesh"]}[key], report["references"]
        minimap_file = Path(zone["files"]["minimap"])
        assert minimap_file.resolve().is_relative_to((INSTALL_1097 / "client").resolve()), minimap_file
        assert report["hud"]["minimap"]["sha256"] == hashlib.sha256(minimap_file.read_bytes()).hexdigest()
        assert report["character_assets"] == str(CLIENT), report["character_assets"]
        assert not any(k.lower().startswith("zones/") for k in report["player"]["hud_sources"]), report["player"]
        # PQ-290 (D-180): the karus_start trunk correction, recorded where applied only.
        corrected = [c["file"] for c in zone.get("corrections", [])]
        assert corrected == {1: ["Object/obj_ka_tree_bra_post.n3pmesh"], 2: []}[key], zone.get("corrections")
        pin += ", 1097 map (%s, headerless, %d referenced files present)" % (
            Path(zone["files"]["gtd"]).stem, report["references"]["gtt"] + report["references"]["meshes"]
            + report["references"]["textures"])
    print("PASS homeland key %d (%s) package, %s: %s start at KO %.0f,%.0f (other nation's start also "
          "verified), N3C2 agrees on both runtimes; a %.0f m engine walk from it; %s, %d N3WT textures "
          "in %d banks, no world-lod.bin, %d-px overview map on N3HE; asset and content checks accept it (%.0f s)"
          % (key, Path(report["zone"]["files"]["gtd"]).stem, pin, nation,
             *record["areas"][nation]["spawn_ko"], walk["distance"], chunks, count, banks, side,
             time.monotonic() - start))
