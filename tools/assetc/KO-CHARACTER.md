# Local KO character test package

This is an opt-in conversion experiment for the locally available **worm monster**
(`Chr/mob_worm.n3chr`), with two textured skinned parts and real joint animation.
It tests the existing Phase 3 engine; Phase 4 remains paused. No client/server code
or binary changes are required. Normal builds and `make test` use original fixtures
and never require KO data or an asset download.

## Build and preview

Run from the repository root with the existing reference assets available:

```bash
source tools/env.sh
make client
make server
python tests/ko_local.py
build/client/n3e-client build/packages/kotest
build/client/n3e-client build/packages/kotest-attack
```

The script generates deterministic walk and attack variants and checks both runtime
readers and sampled poses. Walk is clip index 1, attack is index 4. Direct conversion:

```bash
python tools/assetc/ko_character.py \
  --root assets/ko \
  --character Chr/mob_worm.n3chr \
  --clip 1 --meters-per-unit 1 --out build/ko-source/walk
python tools/assetc/main.py build/ko-source/walk build/packages/kotest
```

All real source-derived output stays below ignored `build/`: glTF, texture atlas,
cooked releases, provenance, source animation metadata and screenshots. The source
checkout is read-only. `--meters-per-unit 1` is an explicit test-scale assumption,
not a claim about officially calibrated KO world units. The worm is naturally low
and long; the inherited fixed fixture camera looks along its long axis. Offline
preview uses the fixture camera/terrain and multiplayer uses the existing 0.45
actor presentation scale. No source model reorientation or collision scaling is
silently applied.

## Play the existing loop with the KO visual

Use a separate Compose project, realm, port and volume so the demo's characters and
inventory definitions remain separate. This starts a local test stack only:

```bash
bash deploy/local-ca.sh
export N3E_UID="$(id -u)" N3E_GID="$(id -g)"
export N3E_PACKAGE_PATH="$PWD/build/packages/kotest"
export N3E_REALM=kotest N3E_PORT=7778
docker compose -p n3e-ko-test up --build -d --wait
read -rsp 'Password for kotester (12–128 bytes): ' N3E_PASSWORD
printf '\n'
printf '%s\n' "$N3E_PASSWORD" | docker compose -p n3e-ko-test exec -T server n3e-server account-create kotester
unset N3E_PASSWORD
build/client/n3e-client build/packages/kotest --connect localhost:7778 --ca deploy/local/ca.pem
```

Provision a second account the same way for a second client. Log in, N/create,
select, WASD/move, Tab/target and Space/attack. Observe rewards/XP, death/respawn and
F5/reconnect persistence. The package retains the Phase 3 rules and synthetic zone,
with namespaced `kotest` definitions. Both player and NPC display the worm because
the existing engine has one package visual.

Stop this project with `docker compose -p n3e-ko-test down` (data preserved).
Before returning to the default demo commands, run
`unset N3E_PACKAGE_PATH N3E_REALM N3E_PORT`.

For the attack variant, change `N3E_PACKAGE_PATH` to
`$PWD/build/packages/kotest-attack`, recreate that test server with the same `up`
command and use `build/packages/kotest-attack` in the client. Both variants have the
same game/rules and compatible durable inventory, but different content hashes;
client and server must use the same variant.

Automated isolated acceptance, with random fixture passwords and automatic cleanup:

```bash
N3E_TEST_PACKAGE=build/packages/kotest N3E_GRAPHICAL=1 python tests/gameplay.py
```

It creates its own unique project and removes only its own volumes. Logs and real
asset screenshots remain local under `build/ko-gameplay/`. This does not create
`kotester` on your persistent test stack.

## Supported subset and explicit omissions

- Identity-transform `.n3chr`, no source collision/climb mesh, plugs, FX/collision
  skin or split-body animation; those fields are checked and retained in provenance.
- Up to 64 joints for the bounds readers (nameplates, render detail, target
  marker) and up to 127 for conversion, with no joint orientation tracks
  (PQ-267, D-175): KO's joint set has no joint bound, and a converted skeleton
  past 64 joints skins with only the joints that carry weight in the drawn
  skin, in joint order (exact; refused when more than 64 do), while every
  joint keeps its node and tracks and `skin_joints` in provenance lists the KO
  joint of each skin joint; recursively bounded
  translation, quaternion and scale tracks, sample rates up to 120Hz. A joint
  with a scale other than exactly (1, 1, 1) or a scale track (PQ-266) keeps its
  node for its rotation and gets a parent node, after the mesh node, for its
  translation and scale: KO rotates, then scales along the parent's axes
  (joint matrix `00427a50`), which one glTF node cannot hold for a non-uniform
  scale; the scene stays within 128 nodes and a scale of 0 or below rejects.
  A skeleton without one converts as before. The bounds readers (nameplates,
  render detail, target marker) still reject scaled joints
  (evidence). Imported clip is
  resampled at 60Hz with LINEAR translation/shortest-arc SLERP. Bind pose is source
  frame 0, independent of the selected clip's start. A selected clip whose end equals
  its start is KO's held pose (clip start `0041be40`, tick `00418b20`; PQ-273) and
  converts as two equal keys 1/60 s apart, recorded as `held_frame`; a reversed clip
  is rejected; unusable nonselected source clip records are retained verbatim as data.
  A clip table without clips rejects, except for the NPC rest pose (no clip
  index; PQ-268, D-178: KO poses the joints at frame 0 when no clip starts).
- Version 0 white-diffuse parts. Render flags 1 (blend with the material's
  factors), 4 (double-sided) and `0x40` (unlit) are read into a render state
  (PQ-265, D-173); flag 2 (KO's fog off) and other flags, another diffuse and
  blend factors past D3DBLEND 10 reject. A model with a non-opaque state or a texel below
  alpha 255 writes an RGBA atlas and one glTF primitive per run of parts
  sharing a state (`N3E_render_state`), which only NPC looks clips cook (N3SM);
  the player path rejects it. All four skin LOD records are validated,
  only LOD0 rendered. Up to 64 joint influences per vertex (PQ-283, D-176;
  this replaces PQ-267's four largest within a bound, D-175): KO's skinning
  sums every influence, so a converted vertex keeps every influence as read,
  in file order, the first four in glTF `JOINTS_0`/`WEIGHTS_0` and the rest in
  `JOINTS_1`/`WEIGHTS_1` and on, which only NPC looks clips cook (N3SI,
  N3SJ); a vertex past 64 rejects, and so does a drawn vertex past four on the
  player path. `many_influences` in provenance records the drawn vertices past
  four, the most and the sets; a model without such a vertex writes one set,
  as before. The render detail and appearance readers still reject more than
  four. The bandicoot, rejected for this before PQ-267 (one LOD0 vertex with
  five, a lower LOD with 48), converts with every influence
  (evidence).
  Source vertex normals (with their length) and per-corner UVs are preserved,
  except that a drawn corner whose normal has no direction (non-finite, or
  shorter than the cooker's 10⁻⁶) is written with its own triangle's unit
  normal, from the skin origins in file winding (D-177). KO lights such a
  corner with ambient light only, which n3e's direction-only lighting cannot
  draw (PQ-285); `rebuilt_normals` in provenance counts them, and a corner
  without a normal on a zero-area triangle rejects. Look 2200's harpy has two
  undrawn NaN normals, which the converter reads and never writes
  (evidence).
- NTF version 3 mipmapped DXT1 (transparent selectors decode to alpha 0) and DXT3,
  power-of-two textures up to 512². Compressed and fallback mip-chain lengths are
  checked; top mip decoded into a horizontal RGB atlas ≤1024², or RGBA for a model
  with render states (PQ-265). DXT5 and other variants reject.
  Atlas UVs are inset half a texel at boundaries to prevent sampling adjacent
  parts. A part whose UVs leave [0,1] (KO samples parts with wrap addressing;
  PQ-264) has each such triangle moved by whole repeats and an atlas region that
  repeats its texture over the moved corners (`wrapped_uv`); a region past
  1024 texels is refused. A part inside [0,1] converts as before. Original diffuse textures supply the visual; the
  engine's simple lighting replaces KO material lighting. PQ-360 read KO's: three
  per-frame Direct3D 8 lights (sun, support light, a point light beside the
  player) coloured by the zone's sky keys, with the part material's diffuse 1
  and ambient 0.5 and no global ambient
  (evidence).
  This importer keeps the material in its metadata only; carrying it is PQ-363.
- Coordinate basis is `(x,y,-z)`, quaternion `(-x,-y,z,w)`, reversed triangle winding,
  unchanged top-left texture origin. Inverse binds come from the converted source
  frame-0 world transforms. No Blender intermediate or Blender installation is used.
- **One selected looping clip per package.** Walk/attack variants demonstrate the
  corresponding source clips; animation does not automatically switch with movement,
  attacks or death. Server-authoritative hit bob/death shrink remain Phase 3 behavior.
  Source strike/sound/trace/blend metadata is recorded, not executed; imported
  animation events cannot grant damage. No full KO character compatibility is claimed.
- Synthetic terrain/static collision remains in use. KO terrain, collision,
  attachments, material lighting (ambient, specular), audio and equipment behavior
  are not imported. The
  fixture terrain shares the existing single texture, now the monster atlas.

## Provenance and implementation

The user explicitly requested local character/monster assets with textures and
animations on 2026-09-19. Local asset Git origin is
`https://github.com/Open-KO/ko-client-assets`, revision
`b4636332c7cd818b0ce171eccc973dd3d6b2e56d`; reference CMake selects tag `v1.298.0`.
No assets were downloaded, committed or pushed by this task. This local test does
not establish redistribution permission. Each conversion writes exact input paths
and SHA-256 hashes to `provenance.json`; evidence
records the tested files and results without publishing asset-derived images/data.

The bounded Python reader, DXT1 decoder, matrix math and glTF emitter are new n3e
code. Layouts and semantics were checked against the Open-KO/KnightOnline source
`src/N3Base/{N3Chr,N3Joint,N3Skin,N3Texture,N3AnimKey}` and the documented
layouts in the Open-KO Blender addon's `openko_blender/formats/`. No reference implementation
was copied or imported; the GPL Blender addon is not a runtime/build dependency.
Both reference revisions and the nested Blender path remain unchanged.

The portable tests in `tests/ko_character.py` create original binary fixtures and
exercise decoding, reflected animated poses, deterministic cooking and malformed
input/path rejection. `tests/ko_local.py` is separately opt-in and checks actual
local worm poses against direct source-space skinning and the C++ runtime, plus
C++/Rust content identity. These checks are evidence for this asset subset, not a
certification of every KO file variant.


## Male Tuarek and actual HUD follow-up

The current field launcher additionally
uses `ko_player.py` and `ko_hud.py`. `ko_player` reads race 2 in the existing
`Data/UPC_DefaultLooks.tbl.csv`, assembles its six parts with face/hair 00, and
converts clips 0 (idle), 2 (run), 87 (unarmed punch) and 8 (death). It never selects
the race-11 barbarian. Source key tracks now allow up to 65,536 keys, still within
the 16 MiB file cap; the observed root track has 4,336 keys. Resampled clip keys
retain their existing 4,096 limit. Player sampling uses exact 1/60-second intervals
plus the final endpoint. The existing worm path retains its prior deterministic
output. Player hand UVs just outside [0,1] are preserved with a two-pixel repeating
atlas gutter; the supported overshoot is at most one source texel. Shelf packing
stays inside 1024×1024, preserving every weight and source part.

The independent HUD parser reads bounded UIF 1264 trees (header marker 0/1),
base/button/static/progress/image/scrollbar/string/trackbar/edit/area nodes, all four
button image states, region/UV/colour/alignment and selected semantic bindings.
It reads NTF3 ARGB4444/ARGB1555 textures with straight alpha, validates mip/fallback
lengths and discards only validated lower-resolution texture data. The real source
files are `UI_US/ka_statebar_us.uif`, `ka_hotkey_us.uif`, `ka_cmd_us.uif`,
`ka_chat_us.uif`, `ka_msgoutput_us.uif`, `co_targetbar_us.uif`, and their referenced
textures. Layout and imagery are imported rather than approximated with panels.
The `N3H2` cook preserves control ownership and state masks for images and labels.
Stand/Disband/Knights stay hidden for the supported standing, ungrouped default;
Walk/Run alternate with movement mode, and chat filter defaults stay selected.
Minimap, duplicate lagging HP layers and debug/system text remain omitted.
Nonimplemented menus give availability feedback; party/sitting/chat-filter gameplay
is not added. Fix evidence.
Local Liberation Mono supplies UI string glyphs; it is a Windows-font
substitute, not KO artwork. All derived raster bytes remain under build/.

Layout references inspected read-only: `N3UIBase.cpp`, `N3UIImage.cpp`,
`N3UIString.cpp`, `N3UIButton.cpp`, `N3UIStatic.cpp`, `N3UIEdit.cpp`, `N3UIArea.cpp`,
`N3Texture.cpp` in Open-KO/KnightOnline's `src/N3Base`, plus `GameDef.h`, `GameProcMain.cpp`,
and `UIStateBar.cpp` in its `src/Client/WarFare`. No implementation code is
copied. Presentation format
defines the game-independent runtime asset boundary.


2026-09-22 follow-up: the local hotbar no longer receives an implicit attack
assignment. Known UIF SHA-256 `2ce4ffcd08eb7dfe07f72c3c45b3a5b7f9654109cd1848158947cf5e5e3aefef`
has a (+1,-3) pixel page-button subtree/click registration repair against its
background glyphs. This is local-asset evidence, not binary-derived repositioning;
other UIF hashes retain their authored positions. Saved assignments/page state
remain unsupported. World `N3L2` preserves terrain MIRROR (`0059cd90`) and object
radial sphere culling (`004429b0`) separately from object REPEAT. See
correction evidence.


2026-09-22 text follow-up: new HUD cooks emit N3H3, preserving UIF single-line,
horizontal and vertical alignment. The existing Liberation Mono substitute's
fixed-cell advance, line height and atlas padding are measured with ImageMagick.
This closes missing layout semantics, not Windows Arial glyph/metric fidelity.
State-specific text rectangles remain authored. See
text and masking evidence.

## NPC looks rows (PQ-254)

`ko_npc_looks.py` converts the NPC models a zone's templates name from the
player's own `Data/NPC_Looks.tbl.csv`, building each row as the client builds
the actor (column 16 `.n3chr`, else columns 3 and 4 with parts from columns
5-10) and taking clips 0, 2, 4 and 10; see `content/npc.md` ("KO looks import")
and D-167. `convert(..., definition=..., player=False)` converts a looks row
the way the worm converts (no atlas gutter, evenly spaced samples); a
definition alone still selects the player path. The Moradon worm now comes
from its looks row (sPid 700) and cooks to the same release:

```bash
python3 tools/assetc/ko_npc_looks.py 1   # one OK or FAILED line per looks key
```

Since PQ-264 parts with wrapping UVs convert (27 of the 29 keys PQ-254 refused
for them), and since PQ-273 clips that start and end on one frame convert as a held
pose (looks 12100 and 12200)
(PQ-264,
PQ-273).
Since PQ-268 (D-178) a state whose clip index is past the row's clip table
takes the clip KO keeps playing (`ko_npc_looks.clip_plan`): on a table without
clips every state is the rest pose, `convert(..., clip_index=None)` (the
joints at frame 0 held, recorded as `rest_pose`, every joint's rotation
written as a track; refused for a table with clips), and on a table of one or
two clips the missing states take clip 0; a table with the walk clip that
lacks attack or death is refused. Zone 1 and zone 2 now convert 52 of 52 keys
each (PQ-268).
