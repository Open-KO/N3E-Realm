# Importer support and provenance

All bundled source geometry, skin, orientation chart, attachment, heightfield,
static triangle, metadata and PMesh bytes are original n3e fixtures. The flag/chart
were intentionally retained from the original Phase 0 fixtures; no production
module imports or builds against `spikes/`. No reference code was copied.

| Input | Supported / verified subset | Explicit exclusions |
|---|---|---|
| glTF 2.0 JSON | One indexed skinned TRIANGLES primitive/skin/clip; TRS tree; up to four normalized joint weights; positive node and instance scale; arbitrary-axis LINEAR quaternion rotation and LINEAR translation/scale; u8/u16 joints, u16/u32 indices; strided nonsparse accessors | GLB, sparse/normalized accessors, matrices, morphs, multiple meshes/material textures/clips, cubic/step tracks, extensions, cameras, extra vertex sets |
| Texture | External noninterlaced RGB8 PNG, all five scanline filters, ≤1,024²; decoded before runtime | Palette/gray/alpha/interlaced PNG, JPEG, compressed GPU textures, extra PNG chunks |
| Material | Single opaque base-color texture, nearest/repeat sampling, Lambert-style basic lighting | PBR fidelity, normal/emissive/occlusion maps, transparency, double sided |
| Scene sidecar | Explicit positive instance scale, attachment node, heightfield and static collision triangles, clip markers preserved in recipe | Markers do not grant damage; multiple render instances and live collision editing |
| `.n3pmesh` | Bounded progressive records, authored LOD controls and grouped split/collapse; maximum-detail standalone output or N3L3 runtime program; explicit meter calibration, reflected winding/edit positions; original fixtures and optional local Moradon verification | Trailing variants, implicit scale guessing, redistribution of local assets |
| `.n3shape` | Rejected by the generic cooker; local-only KO importers are documented below | Real fixtures, transforms/dependency variants/material fidelity unverified |
| `.n3chr`, `.n3joint`, `.n3cpart`, `.n3cplug`, `.n3anim` | Rejected by the generic cooker; local-only KO importers are documented below | Parts, skeleton, marker, collision/climb and attachment metadata cannot be silently discarded |
| NTF/DXT / KO terrain | Rejected by the generic cooker; local-only KO importers are documented below | Real texture variants/terrain conversion unverified |

Run `python tools/assetc/ko.py path/to/original.n3pmesh 0.01` to inspect the supported
static intermediate subset. The caller must provide measured meters per source
unit. Synthetic tests calibrate reflection, winding and scale; they do **not**
calibrate the local official client assets. The Phase 0 read-only format review
identified PMesh field layout; this adapter was independently implemented from
that layout without adapting the GPL addon implementation. Reference revisions
remain unchanged. Engine distribution license remains an open project decision.

Scope decision D-012 records why real KO/character support is not a Phase 1 pass:
local asset availability is not redistribution/provenance approval. The original
demo and explicit bounded adapter are the foundation deliverable; adding any real
legacy variant requires separate approved fixtures and numeric/metadata evidence.

## Post-Phase-3 local character experiment

The separately requested
[`ko_character.py` local experiment](KO-CHARACTER.md) now verifies the local worm's
identity `.n3chr`, 25-joint unit-scale skeleton, version-0 opaque parts/four-influence
skins, NTF3/DXT1 textures and selected walk/attack clips. It emits supported glTF
and an RGB atlas without changing engine binaries. This is **not** general KO
character/texture support: unsupported variants reject, one clip loops per package,
and collision/material/FX/audio/clip-switching behavior remains explicitly excluded.
Only original synthetic fixtures participate in normal CPU tests; real-derived
assets and captures stay in ignored local build output. The user authorized local
asset testing; no redistribution approval is inferred.

KO-07 supports optional [N3A1 metadata](../../content/animation.md) with complete player/NPC clips. `animation_fixture.py` builds original fixtures; `--ko` uses existing local references and retains per-clip provenance. Source FPS is baked into seconds; selected blend/strike data drives a bounded full-body subset, not complete N3 animation authoring.

## Current KX world LOD support

This section supersedes the Phase 1 world/texture exclusions above for the
bounded local exploration importer. N3L3 retains progressive mesh programs and
parent visibility bounds. The client evaluates authored vertex budgets every
frame, including signed truncation and grouped split/collapse. Terrain has three
patch levels, neighbor-dependent shared edges, and authored TCT color maps for
coarse levels (NTF3 A1R5G5B5, alongside existing DXT1/DXT3 support). N3L1/N3L2
remain readable. See LOD correction evidence.

The follow-up audit
confirms object topology coverage but identifies terrain-normal fidelity and
diagnostic capture-state gaps. Near/coarse normals currently use height gradients;
the binary averages triangle normals and forces map-border normals upright.
Texture resampling/regenerated mip chains are also fidelity limits. Three-level
geometry support does not imply matching terrain shading or historical textures.

Runtime collision stays at full authoritative detail. Character/attachment LOD,
alpha blending/billboards, fine non-full-tile color-map fallback, and historical
camera/environment settings remain separate support limits. Finite static
placements with positive LOD scale and positive parent Y visibility scale are
supported; unsupported transforms fail the LOD bake. Local reference assets and
raw binary output are never bundled or required downloads.

KFC opt-in package capabilities: [N3I1 bags](../../content/inventory.md) and
[N3O1 merchants](../../content/commerce.md), independently read by C++/Rust and
verified with original fixtures. Existing shipped demo manifests are unchanged.
These do not imply full KO item flags, derived equipment stats or dynamic prices.
[N3J1 repair](../../content/repair.md) adds bag-item restoration with binary-grounded
pricing and independent quotes. N3Q1 also supports equipped repair. Combat wear, stat refresh and premium
eligibility remain open; damaged items in its live tests are injected fixtures.

[N3Q1 equipment](../../content/equipment.md), engine18/wire11, adds named slots,
base-attribute/race/title requirements and atomic transfers. Shared original
archetype fixtures do not implement character stat allocation or combat bonuses.


N3H5 [dialog item icons](../../content/dialogs.md) map package item IDs to bounded
texture/UV entries. Moradon imports nine local KO icons with provenance; game
balance is unchanged. H1–H4 remain readable and retain their text presentation.


D-081 adds [N3E1 rest and recovery](../../content/rest.md) with engine30/wire23 and
complete N3A3 sit/idle/stand clips. Both readers reject incomplete sets or unbounded
recovery rows. Ordinary Tuarek rest is integrated in Moradon; restoration modifiers
and weapon-specific combat stances remain gaps. Bag merges conserve capped stacks
and overflow; right-click equipment uses existing authoritative operations.

N3H9 [overhead names](../../content/nameplates.md) bakes regular/bold Liberation
Sans substitutes, per-glyph advances and frame-zero joint bounds for the local
Moradon Tuarek/worm. Font paths/settings are in games/moradon/nameplates.json;
font hashes and skeleton provenance are recorded. No runtime system-font lookup.
Exact Windows GDI, full colors, alternate models and special names remain gaps.

D-089: optional `presentation["loot-model.bin"]` accepts a static N3S1 container
alongside complete presentation and durable progression (engine10+). Moradon's
`ko_loot_model.py` imports the observed one-part opaque static shape and identical
texture frames, rejecting unsupported variants. Paths/scale live in
`games/moradon/loot-model.json`. [Contract](../../content/loot-visual.md),
binary/asset provenance and limits.

Optional engine33 `presentation["target-marker.bin"]` uses bounded N3TM static
additive terrain/upright parts. The Moradon importer reads the original local
shape, quads and textures plus initial skeleton bounds; paths and sizing remain
package-owned. No reference art is committed. [Contract](../../content/target-marker.md).

D-099: optional `presentation["loot-policy.bin"]` requires the loot model. N3LP
stores a finite positive float32 open radius up to100m; C++/Rust/assetc validate it
and hash it with the release. Moradon uses strict10m opening independently of its
server-owned3m pickup radius and20-second TTL. Legacy packages retain their prior
opening policy. [Contract and remaining corpse gaps](../../content/loot-visual.md).

Spec 11: optional engine42 `presentation["front-end.bin"]` (N3FE) holds KO's
front end. `ko_front_end.py` reads the local client's UIF trees (login, Karus
select, create, loading, OK box), the 1098 intro character with its plug and
lights, the select hall's n3shape, slots, spots and the Tuarek priest with three
clips (front, start, rest), all from the paths and choices in the chosen front end's recipe
(RQ-078: `front_end_choice.py` reads `games/moradon/realm-config.json` and
`front-ends.json`, refuses an unoffered client or missing inputs, and gives the
recipe, `front-end.json` for 1097, and its input trees; RQ-084: a recipe path
`<name>:<path>` reads a named later input, and a reference install, pinned in
`ko_installs.py`, is read only against its installer's manifest; RQ-085: the 1097
recipe reads its five layouts from the pinned 1264 install, 1264's OK box
`el_messagebox_us.uif` and no-victor `co_loading_us.uif` among them); the
provenance report records the client and every source path and hash. Text is drawn with the
Liberation Sans substitutes of N3H9. Untextured images draw nothing, as KO's.
N3FE version 3 (RQ-018) adds the screens' music: each track's MPEG-1/2 Layer III
frames as the KO file has them (ID3 tags and a cut-short last frame dropped, any
other irregularity refused), and the track per screen from `front-end.json`'s
`music` (Q69). N3FE version 4 (RQ-075) adds each model clip's blend time, read
from its clip record (the select start clip's from `start_blend` instead, the
select's own 0.6 s, RQ-076), and the select spot's growth rate (`spot_step` a
tick at 30 ticks a second). N3FE version 5 (RQ-083) adds each track's kind and
restart period: a track file that is a RIFF WAVE is cooked as its 16-bit PCM
samples (read as `ko_audio` reads a WAV, integer PCM only, other widths made
16-bit, its own rate and channels kept, the whole file), so 1097's
`bgm_login.wav` and `bgm_el_battle.wav` play as 1097 plays them. N3FE
version 6 (RQ-086) adds the select hall's front-clip mode (`select.front_clip`:
`hover`, 1097's, or `loop`, 1298's); `games/moradon/front-end-1298.json`, not
offered yet, cooks 1298's per-race `ChrSelect/upc_ka_tu` joint and clips with it,
holding a clip's frames past its joint's keys on the last key, as KO leaves them.
N3FE version 7 (RQ-087) adds the select camera's turn mode (`select.turn`:
`rotate`, 1097's, or `path`, 1298's) and, in the path mode, up to 8 camera paths
(`select.paths`, each a from and to slot and an `.n3camera` read as
`CN3Camera::Load` reads it: its eye and at keys, engine space; its up keys, at,
camera data and fog are not cooked), and lets the hall be empty; the 1298 recipe
cooks 1298's `ka_*_camera.n3camera` paths, slots and spots and no hall yet.
N3FE version 8 (RQ-095) adds the select zone (`select.zone`, a `Zones.tbl` key:
the zone's terrain and its shapes cooked as `ko_scene` bakes a world, in hall
space, up to 256 meshes with a sort point, lit or unlit, cut at alpha 0 or
blended; no second tile layer, light map, grass, sky, birds or animation) and
the select fog (`select.fog`, the camera files' one fog, linear from a tenth of
the far plane to it), and lets a front end carry 256 textures; the 1298 recipe
cooks zone 10001, `karus_intro`, with its camera files' white fog, lit
as 1298's select lights it: its light manager's lights (`select.light_manager`,
in the format's light list) replace the hall lights of their number.
N3FE version 9 (RQ-101) adds a logo screen before the login (the recipe's
`logo`: a layout of groups, images and strings, each group's fade-in, hold and
fade-out from KO's seconds and peak, its music's track, delay and fade-out and
whether a key skips it and the cursor hides; none without the key); the 1097
recipe cooks 1264's `co_usa_logo_us.uif` and `Snd/bless.wav` from the 1264
install.
N3FE version 11 (RQ-106) adds the placement: each layout's moves, rules linear in
the window's width or height from the recipe's `place` and `moves`, which put the
nodes where KO's UI code puts them on a window of any size (the client draws the UI
unscaled), and the recipe's `ui_scale` (`native`, or `window` for the realm's
earlier scaling to the window); the 1097 recipe gives 1264's placements
(`specs/KO-FINDINGS.md` §9.3). N3FE version 12 (RQ-108) adds the action
`login_closed`, a login node drawn only while the login group is not; the 1097
recipe binds 1264's copyright line, `Text_Rights`, to it at 1264's place
(`specs/KO-FINDINGS.md` §9.4); the 1298 recipe hides it, 1298's login having none
(§9.5, RQ-110).
N3FE version 13 (RQ-109) adds 1298's select bar actions, select screen only:
`select_start`, `select_create` and `select_delete` (its start, create and
delete buttons) and the info texts `char_name`, `char_level` and `char_class`, any
of which a select may bind in place of `char_info`, with the messages
`create_full` and `delete_disabled`, and a root placement `{"bottom": N}`; the
1298 recipe cooks 1298's own select, the `co_CharacterSelect_us.uif` bar, centred
10 px above the bottom edge, with KO's rows 7675 and 1501 for the two messages
(`specs/KO-FINDINGS.md` §9.6).
N3FE version 14 (RQ-111) adds the message box's `yes` and `no` (message screen
only) and the message `exit_confirm`, which makes the select's exit ask in a box
with Yes and No; the cook refuses it without both bound. The 1298 recipe draws
1298's own message box, the pinned tree's `el_messagebox_us.uif`, and words
`exit_confirm` with KO's row 1502 (`specs/KO-FINDINGS.md` §9.7); the 1097 recipe
binds 1264's box's Yes and No and words it with the 1264 install's row 1502, as
1264's select asks the same (RQ-115, §9.8).
N3FE version 15 (RQ-116) adds what ESC presses on the select (`select.escape`:
`back`, the default, or `exit`, as 1264's select presses `bt_exit` for ESC,
§9.8); the 1097 recipe names `exit`. N3FE version 16 (RQ-119) adds `none`, as
1298's select presses no button for ESC and only skips a playing path (§9.9); the
1298 recipe names it. N3FE version 17 (RQ-112) adds where the select's Back lands
(`select.back`: `login`, the default, or `realms`, as 1298's Back sets its login
procedure's `+0x21`, whose Init connects, asks for the server list and hides the
bar, §9.12); the 1298 recipe names `realms`.
The 1298 Karus/El Morad nation choice and the other races and classes remain
gaps (Q51, Q52). [Contract](../../content/front-end.md).
