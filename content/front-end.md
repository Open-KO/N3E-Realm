# Front end (N3FE, engine 42)

`front-end.bin` is an optional presentation file (spec 11): KO's 1098 login scene,
login and server list, the Karus character select hall, character create, loading
and the OK message box, the screens' music (version 3, Q57), each model
clip's blend time and the select spot's growth rate (version 4, RQ-075),
PCM music tracks with a restart period (version 5, RQ-083), and the select
hall's front-clip mode (version 6, RQ-086).
`tools/assetc/ko_front_end.py` cooks it from the pinned client tree with the
recipe of the front end the realm chose ("Choosing the client", below; for
Moradon's default, 1097, `games/moradon/front-end.json`); the client's
`load_front_end` (`client/assets/assets.cpp`) reads it and the server reads only
its header. A package with it is engine 42, so wire 30 (as engines 38–41). Its bound is
64 MiB (`FRONT_END_FILE`, `MAX_FRONT_END_ASSET`, `kFrontEndFile`), since it holds
two character models and the UI art.

Integers are little-endian u32, reals f32; strings are a u32 length and that many
bytes. Engine space is KO's with z negated (KO is left-handed).

## Layout

1. `"N3FE"`, version 6, character slots (1–3; the server's character limit),
   canvas width 1024 and height 768.
2. Textures: a count (≤64), each width and height (1–1024) then RGBA8 rows.
3. Fonts: a count (≤8), each texture index, pixel size (6–48), cap height, atlas
   top and 95 advances for ASCII 32–126. A font texture is a 512×192 atlas of
   32×32 cells in 16 columns, glyph origin x=2, baseline y=22 (as the N3H9
   nameplate fonts). A glyph is drawn at (x−2, y−top), y the cap top.
4. Five screens in the order login, select, create, loading, message. Each is a
   node count (1–1024) and the nodes in draw order:
   - kind (0 image, 1 text, 2 button, 3 edit, 4 progress, 5 group, 6 area,
     7 list), parent (none, `0xffffffff`, for the first node only; otherwise an
     earlier node), rect x0 y0 x1 y1 on the canvas, id (≤64 bytes), action,
     flags (1 fixed on, 2 fixed disabled, 4 progress foreground), state mask
     (1–15: the button states normal, down, on, disabled it draws in);
   - image: texture, uv u0 v0 u1 v1 in [0, 1];
   - text: text (≤1024 ASCII bytes), font, colour (ARGB), KO string style;
     an edit is its string child's font and colour (its other children are
     images, as the login's untextured ones);
   - edit: font, colour, style (`0x10000000` password); list: font, colour.
   A node draws only when its parent does. A button's state images carry one
   mask bit each; its other children draw in every state.
5. Strings, each ≤1024 ASCII bytes, in order: `select_info`, `select_hint`,
   `class_name`, `class_desc`, `loading_info`, `version`. The client substitutes
   only `{level}`, `{class}`, `{name}` and `{version}`.
6. The intro scene: camera, lights, global ambient (3 reals), the model, its
   plugs (count ≤4), then the backdrop: a texture index and a rect in 1024×768
   units that the client scales by the window's width and height separately
   (`CGameProcLogIn_1098::Render`'s moon).
7. The select scene: camera, lights, global ambient, the slots (count equal to
   the character slots), the spot's growth rate (version 4: theta per second,
   above 0 and at most 100), the front-clip mode (version 6: 0 hover, 1 loop;
   below), the hall (part count ≤64, each a mesh), the model (version 4: three
   clips, by role the front, start and rest clips), its plugs.
8. The create model and its plugs (version 2): `CGameProcCharacterCreate`'s
   player (`InitChr`: the race's `UPC_DefaultLooks` joint, animation and default
   parts) with one clip, `ANI_BREATH` (0), and no plugs (a new character holds
   nothing). The select model's seated clips are for the hall's thrones.
9. Music (version 3, RQ-018; version 5, RQ-083): a track count (≤4), each
   its kind (version 5: 0 MPEG, 1 PCM), sample rate, channels (1 or 2), loop
   (0 or 1), restart period (version 5: a real, seconds, 0 for none or
   0.1–3600), a frame count and a byte length (1 to 16 MiB) and then that many
   bytes. An MPEG track's bytes are MPEG-1 or MPEG-2 Layer III frames back to
   back, every one whole, at the track's rate and channel count (free format,
   MPEG 2.5 and reserved header values refused; a CRC is allowed), and its
   frame count counts them. A PCM track's bytes are signed 16-bit
   little-endian samples, the channels interleaved, at 8,000–96,000 Hz, and its
   frame count is the sample frames: the byte length is exactly frames ×
   channels × 2. Then four track indices, `0xffffffff` for none: the login
   screen (the realm list too), select, create and loading. The client
   (`client/assets/music.h`) checks every track at load and streams one while
   its screen shows: an MPEG track one frame decoded at a time (minimp3,
   `UPSTREAM.md`), a PCM track 1152 sample frames at a time, resampled
   linearly to 48 kHz, mixed unpositioned at the voices' gain and kept up to
   six audio chunks (128 ms) ahead. A screen naming the track already playing
   keeps it (an ended one too); another track starts at its first frame;
   none, and entering the world, stops it. A looping track starts again at its
   first frame, with a fresh decoder; one whose whole pass decodes nothing
   ends. A track with a restart period starts again at its first sample each
   time it has played that long, whether it has ended (silent meanwhile) or
   not, so it never ends; the period takes precedence over the loop.

The client samples as KO sets its devices: UIF images with point sampling on whole
screen pixels (`CUIManager::RenderStateSet`, `CN3UIImage::SetVB`: KO's atlases
border each tile with black texels a linear filter would blend in); hall meshes
and plugs trilinear with mip LOD bias −1 and wrapped UVs (`CN3Eng`, D3D's default
address mode); the font atlases and the moon linear.

- Camera: eye, at, up (engine space), vertical field of view (radians, (0, π)),
  near and far (0 < near < far ≤ 1000).
- Lights: a count (≤8), each type (1 point, 2 spot, 3 directional), diffuse,
  ambient, position, direction (3 reals each), range (0, 1e8], falloff,
  attenuation 0–2 (non-negative, sum above 0), theta, phi: D3DLIGHT9's fields.
  The client lights as Direct3D 9's fixed function does, without specular.
- Slot: position, yaw (radians, engine space), the camera eye at which the
  camera's turn to the slot ends (the scene camera's `at` and up apply; slot 0's
  is the scene camera's own eye), and the slot's spot light (one light
  record). The client turns the scene camera's eye about the vertical through
  `at`, the short way, at KO's 1.2 rad a second; a turn to another slot ends on
  the first frame past that slot's eye, and a turn back to slot 0 ends on its
  eye (1097: `0043e4e0`, below). The spot's theta is the widest it opens; the
  client widens it from 0 at the select scene's rate, as the front-clip mode
  says, and the spot is off at 0.
- Front-clip mode (version 6, RQ-086; `client/render/select_hall.h`): what the
  hall plays at rest, the camera on a slot. Both start the chosen character's
  start clip once on the press, at rest only, with the spot at its widest, and
  tick only it until the clip has played (below). Both give every character the
  front clip, with no blend, on entering the hall (KO's AddChr).
  - 0, hover (1097, `0043f280`; "Moradon", below): every tick, the character in
    front plays the front clip once while the pointer is in the centre rect and
    the rest clip once otherwise, each over its blend time, and is the only one
    ticked; the spot widens while the pointer is there and narrows otherwise;
    the info text shows only while the pointer is there. While the camera turns
    nothing is ticked.
  - 1, loop (1298, `005fef90`; `specs/KO-FINDINGS.md` §8.3): every tick, the
    character in front loops the front clip and the others play the rest clip
    once, each over its blend time, every character ticked, whatever the
    pointer does; the spot widens to its widest and stays there; the info text
    shows (`select_hint` for an empty slot). While the camera turns every
    character plays the rest clip once and is ticked, and the info text is
    hidden. The centre rect only takes the click.

  While the camera turns the spot is off and keeps its theta, in both modes.
- Model: a byte length and an N3S1 or N3SM scene (`tools/assetc/gltf.py`, atlas
  up to 2048 a side), then a count of further clips and each clip's byte length
  and track list (N3S1's track encoding, on the model's nodes), then (version 4)
  each clip's blend time, seconds, 0–10: the time the client blends into the
  clip over. That is the KO clip record's `fTimeBlend`, which `CN3Chr::AniCurSet`
  takes when the caller names no time of its own, or the caller's own time where
  the package's choices name one (Moradon: the start clip's, `start_blend`).
- Plug: the KO joint index (below the model's joint count), then a mesh in that
  joint's space: world = instance × `Scene::joint_matrix` × vertex.
- Mesh: texture, flags (1 double-sided, 2 alpha test at 0.5), material diffuse
  and ambient (3 reals each), a vertex count (1–65536) of 8 reals (position,
  normal, uv), an index count (a multiple of 3, ≤196608), the indices.

The loader refuses an unknown action, a screen missing one of its required
actions (login: `login`, `exit`, `login_group`, `realm_group`, `realm_list`,
`realm_connect`; select: `select_prev`, `select_next`, `back`, `exit`,
`char_info`; create: `create_confirm`, `back`, `name_field`, `char_view`;
loading: `progress`; message: `message`, `ok`), an action bound twice in a
screen, and every reference, count and bound above, truncation or trailing
bytes.

## Actions

The closed set, by index: none, `login`, `exit`, `login_group`, `realm_group`,
`realm_list`, `realm_connect`, `notice`, `select_prev`, `select_next`, `back`,
`char_info`, `create_confirm`, `name_field`, `char_view`, `class_desc`,
`progress`, `version`, `info`, `message`, `ok`. A group bound to `login_group` or
`realm_group` is shown in its state only; `realm_list` lists the realm from
`realm.json`; `notice`, `char_info`, `class_desc`, `version`, `info` and
`message` are texts the client fills; `name_field` is the name entry; `char_view`
is where create draws the character.

## Choosing the client (RQ-078)

A realm owner chooses which KO client the front end looks and behaves like. The
choice is package data, cooked into `front-end.bin`; the engine knows no client
and plays whatever the file says. Two files in the package source hold it:

- `games/<game>/realm-config.json`, the realm owner's choices:
  `{"front_end": "<client>"}`. It takes no other key (a misspelt one is refused,
  not ignored). Moradon's is `"1097"` (Q71).
- `games/<game>/front-ends.json`, the clients the package can cook, by id
  (lower-case letters, digits and `-`, up to 32): each a `recipe`, the
  `ko_front_end` input beside it (the files, bindings and placements of that
  client's screens, as `front-end.json` below), and its `inputs`, 1 to 4
  repository-relative trees (`tree`, never absolute or with `..`) with how to get
  each (`get`) and, required for every input after the first, a `name` (as a
  client id, unique in the entry).

A recipe path names the first input's tree unless it starts with an input's
name and a colon (RQ-084): `"installer-1097:Intro/Intro.N3Chr"` reads
`Intro/Intro.N3Chr` from the input named `installer-1097`. No KO path holds a
colon, so the first one ends the prefix. The prefixed paths are the KO paths the
recipe names: each screen's `ui`, `intro.character`, `intro.lights`,
`intro.backdrop.texture`, `select.lights`, `select.hall`,
`select.character.joint`, `select.character.animation` (the joint's input: the
two, and the race's `Data/UPC_DefaultLooks.tbl.csv` row that create's model
follows, are one tree's), `select.character.plugs` and `music.tracks[].path`. A
file a KO file names (a character's parts and plugs, a layout's or a hall's
textures and meshes) is read from the tree of the file that names it.
`select.turn_sound` is a sound-table id of the first input, or `"<name>:<id>"`
for another input's: its row (the file and how many play at once, at most 16)
is that tree's `Data/sound.tbl.csv`, or the client's own encrypted
`Data/sound.tbl` (`tools/assetc/ko_tbl.py`; columns u32, string, i32, i32, as
1097's and 1298's), and `audio.bin` carries that tree's file. A first-input id
binds through the player's sound table, as before, when the first input is the
player's own tree.

`make realm-assets` (`tools/assetc/ko_bake.py 210 --features`, and every other
`--features` cook) reads both through `tools/assetc/front_end_choice.py` before
the survey and refuses, with a message naming what to change:

- a missing or malformed `realm-config.json` or `front-ends.json`;
- a choice the package does not offer ("front end '1298' is not one this
  package cooks; it cooks 1097");
- a choice whose input tree is missing on the cooking machine ("front end
  '…' needs <tree>, which is missing on this machine: <get>");
- an input that is a reference install other than a pinned one's `client/`
  tree, or whose `manifest.json` is missing, malformed or not its pinned
  installer's (below);
- a recipe path whose prefix names no input of the choice, or an input after
  the first without a name.

`ko_bake.package` makes the same check before it removes or writes anything,
so a caller that skips the command line's check is refused with nothing changed.

It then cooks the chosen recipe and records the client, recipe and trees in the
package's `provenance.json` (`front_end`). The realm's server never sees KO
inputs: it runs the cooked package (spec 07, `deploy/HOST.md`), so the refusal
is the cook's (Q73). Changing the choice changes `front-end.bin` and so the
package hash: a new package, so a new realm (Q63).

Inputs are pinned before they are cooked from: the pinned tree by `UPSTREAM.md`
(`make ko-assets`); a reference install by its installer's manifest (RQ-084,
`tools/assetc/ko_installs.py`): an input under `build/ko-reference/` must be
`build/ko-reference/<name>/client` of a pinned install, `installer-1097` or
`installer-2145`, whose `manifest.json` (the unpacker's, beside `client/`)
names that installer's SHA-256, as `ko_bake --client=1097` checks the 1097 one
and `ko_glow_2233` the 2145 one; the cook then reads each of its files only when
the file's SHA-256 is the one the manifest lists ("… differs from its
installer's"), and the provenance's `front_end` records each input's name and
manifest (`names`, `installs`) when a choice reads more than one tree or an
install. The Steam install, which Steam updates in place, is refused until a
hash manifest written before any cook reads it pins it (RQ-090). CI's cook (spec 10) has only the
pinned tree, so it can cook only choices whose inputs are that tree; a realm
choosing another cooks on a machine that has the install, as the hosted realm's
packages already are (`deploy/HOST.md`, "Releases").

The clients, per screen, and what the format expresses for each, are in
`specs/KO-FINDINGS.md` §9. Offered today:

| Client | Recipe | Inputs | Status |
|---|---|---|---|
| `1097` | `front-end.json` | `assets/ko` | Default. 1097's login scene, select hall (`front_clip` `hover`), turn sound and music (RQ-083: `bgm_login.wav` restarting every 21.66 s, `bgm_el_battle.wav` looping). Still 1298's: the layouts (`UI_US`, since `ko_hud` does not read 1097's UIF version) |

Not offered yet: `1298`, `2145` (its UIF versions, its Ogg sounds, its clip
format) and `steam` (its packs, its protected exe, the pin). Each is its own
queue item; until it lands the cook refuses it as above. 1298's select
character is data already (RQ-086): `games/moradon/front-end-1298.json`
("1298", below) cooks from the pinned tree, but `front-ends.json` does not offer
it until 1298's recorded camera paths, its select hall and slots, its UIF
login intro and its select UI hidden while the camera turns are data too.

## 1298 (`games/moradon/front-end-1298.json`, not offered)

The parts of 1298's front end the format expresses (RQ-086,
`specs/KO-FINDINGS.md` §8 and §8.3, binary); every other part is the 1097
recipe's, as "Moradon" below says, and marked here:

- Select character: 1298's per-race files, `ChrSelect/upc_ka_tu.n3joint` and
  `upc_ka_tu.n3anim` (`005fb4f0`: race 2, a rogue or a priest), with the race's
  `UPC_DefaultLooks` parts and face and hair 0, as `005fc6f0` takes them for a
  slot with no item, and no plug, as `005fca40` adds none without an item (the
  wire carries no equipment). Its clips by role: front 1 (20–300 at 30 frames a
  second), start 2 (394–466 at 25) and rest 0 (180–220 at 25), each over its
  record's 0.25 s but the start's, over 0.6 s (`005fe7c0`). Clip 2's last frames
  (458–466) are past the joint's 228 keys at 15 a second; KO leaves the joints
  there as the last key set them, and the cook holds the last key.
- `front_clip` `loop` (`005fef90`): the front clip looping on the character in
  front at rest, the rest clip once on the others and on everyone while the
  camera turns; the spot widens to 0.5 by 0.02 a tick (`006a93b4`, `006a93bc`,
  Karus) and stays; the info text shows at rest, empty for an empty slot
  (`006074c0` writes the empty string, so `select_hint` is empty).
- No turn sound: 1298 plays none (`select.turn_sound` absent).
- Music: `Snd/Intro_Sound.mp3`, looping on login, the realm list, select and
  create; loading silent (`005f68e0`, `005fea70`, "Moradon" below).
- Still the 1097 recipe's, not 1298's: the 1098 login scene (1298 draws a UIF
  intro), the select hall `ka_chairs.n3shape`, its lights, camera, slots and the
  turn about `at` (1298 places its characters elsewhere, `005fb4f0`'s positions,
  and turns through recorded `.n3camera` paths), the select UI shown while the
  camera turns (1298 hides it, `005fe3c0`, `005fe450`; Q77), and the layouts (1298's
  `UI_US`, as today).

## Moradon (`games/moradon/front-end.json`)

- Login (`UI_US/co_login_us.uif`, centred on the bottom edge): as KO draws it, with
  KO's labels and copyright line (Q61). Login starts spec 02's flow; Cancel exits.
  ID, Password, Option and Registration are unbound: they take no input (Q60, Q61).
  Hidden: the MGAME and Daum logos (the UIF names `ui_us\service_logos.dxt`, which
  the pinned tree lacks), `premium` and the three notice groups (KO's news panels,
  empty without KO's server). No `notice` line: the flow's failures show in the
  message box. The server group sits at the top of the canvas (`OpenServerList`).
- Select (`UI_US/ka_characterselect_us.uif`): left, right and exit 10 px above
  the bottom edge, back 15 px above exit, delete hidden (Q53).
- Create (`UI_US/Ka_CharacterCreate_us.uif`, centred): Tuarek and Priest fixed
  on, every other race, class, face, hair and stat arrow fixed disabled, the
  bonus points and stat highlights hidden (Q52).
- Loading (`UI_US/ka_loading_us.uif`, centred; `Text_Version` at (10, 10)) and
  the message box (`UI_US/co_MsgBoxOk_us.uif`, centred).
- Intro: `Intro/Intro.N3Chr` clip 0 with its axe plug, `Intro/0-2.N3Light` (2 is
  off), `Intro/Moon.dxt` at (100, 50) × 1.3, KO's fixed camera.
- Select: `ChrSelect/ka_chairs.n3shape`, `ka_light_0/1`, the Karus slots, spots
  and camera from `CGameProcCharacterSelect::Init`, and the Tuarek priest
  (`upc_ka_tu_pri.n3joint`, default looks, the mace plug) with the clips of
  `upc_ka_at_wa.n3anim` the 1097 client plays there: 0 `pre_select` (hover), 1
  `selected` (start) and 2 `dummy` (rest, `pre_select`'s first frame). The
  hover and rest clips blend over their records' 0.3 s (`0043f280` names
  `FLT_MIN`); the start clip over `start_blend`, the select's own 0.6 s
  (`0043ea30`: `push 0x3f19999a` at `0043ea77`), not its record's 0.3 s. The hall plays as 1097's does
  (`front_clip` `hover`; `specs/KO-FINDINGS.md` §8.1, binary, Q71): at rest, every tick, the
  character in front plays `pre_select` once while the pointer is in the centre
  rect and `dummy` once otherwise; setting the clip already set changes
  nothing, so `pre_select` plays once and holds its last frame. Each change
  blends from the frame the previous clip had reached over the new clip's own
  blend time and holds the new clip's first frame meanwhile (`00447e30`,
  `00445bb0`): going in, `pre_select` stays on its first frame for 0.3 s; going
  out, the pose returns to `dummy` over 0.3 s. A change during a blend starts
  from the frame the interrupted clip was held on, not from the blended pose,
  so the pose jumps there first, as KO's does (`00447e30` keeps only the frame,
  `00445e90` blends two frames). Only the character in front is
  ticked; the others stand where they were. The spot (`spot_step`, 0.02 a tick,
  `0043f280`'s Karus step; cooked as 0.6 a second at 30 ticks a second, the
  rate KO's frame-scaled code is written for) widens while the pointer is
  there, up to `spot_theta` (0.5), narrows when it leaves and is off at 0; the
  info text (`text00`, `select_info` or, for an empty slot, `select_hint`:
  KO's 1201 and 1202) shows only while the pointer is there. While the camera
  turns nothing is ticked, the spot is off (`0043b550` turns every light off
  each tick) and keeps its theta for the next slot. The turn (RQ-067,
  `specs/KO-FINDINGS.md` §8.2, binary): LEFT, RIGHT or the arrow buttons put
  the neighbour in focus at once (left to right 1, 0, 2; nothing at the end of
  the row or while the camera turns, `0043e310`, `0043e380`), and the eye turns
  about `at` by 1.2 rad a second, a check before each step (`0043e4e0`). A
  side slot's `turn_end` is the cosine 1097's check ends the turn below: the
  eye turned a further 0.01 rad, against the camera's own eye, both from `at`
  (`0043dc50` left 0.75, `0043dfb0` right 0.77, Karus); the cook puts the
  slot's eye where that check first ends it, so the turn stops on the first
  frame past it, where the last step left it. Back to the centre the turn ends
  once the eye has reached or passed the camera's own and is put back on it.
  The frame that ends a turn is still a turning frame. ENTER or a click starts
  only at rest, never while the camera turns or the start clip plays (the
  click: `0043b550` outside state 1, with `PtInRect` on the rect truncated to
  whole pixels; the hover wants the pointer strictly inside, `0043f280`; the
  start: `0043ea30` in state 2 only). Starting turns the spot to its full theta
  (`0043ea30`), blends into `selected` over 0.6 s on its first frame and plays
  it to its end; loading follows once it has played (`IsAnimEnd`, `0043ed20`:
  the loop count, counted only past the clip's end, after the blend). A refused
  start returns the character in front to the hover or rest clip at once, so
  the next start plays `selected` again. Not 1097's (Q72): 1097 starts the
  clip on the server's answer, takes ENTER during the turn, and a second ENTER
  loads at once (`0043db70`); the realm starts on the press. 1298 draws the
  hall from other files and loops a clip on the character in front without
  the pointer (`specs/KO-FINDINGS.md` §8, Q71).
- Fonts: Liberation Sans regular and bold for Arial, at points × 96 / 72.
- Music (RQ-083, `specs/KO-FINDINGS.md` §9, binary): 1097's. Login and the
  realm list: `Snd/bgm_login.wav`, 1097's sound 35 (PCM, 22,050 Hz stereo
  16-bit, 477,749 frames, 21.67 s), not looping, restarted every 21.66 s.
  Select and create: `Snd/bgm_el_battle.wav`, 1097's sound 20003 (PCM, the
  same format, 3,995,263 frames, 181.19 s), looping. Loading is silent. The
  recipe names the files, not the sound ids: the pinned tree is 1298's, whose
  `sound.tbl` rows 35 and 20003 name MP3s; 1097's name these WAVs, which the
  pinned tree holds byte for byte. KO 1097 (binary, the 1097 image): the login
  Init creates the BGM stream from sound 35 (`0052409d`–`005240b3`) and its
  tick plays it when its timer is 0 and stops it past 21.66 s, setting the
  timer back to 0 (`005248f5`–`00524957`), so it restarts about every 21.66 s,
  just before its own end; its stream alone would stop after one pass, as the
  login sets no loop byte (`00432f60`). The login's answer to the game
  server's login (`00525b70`) releases it and creates sound 20003, sets its
  loop byte and plays it, then opens select; select (`0043a950`,
  `0043b550`) and create leave it; the select releases it when the chosen
  character's clip has played, before loading (`0043ed20`; `0043db70` too).
  Not KO's (Q75): back on the login from select, the realm starts sound 35 at
  once; 1097 waits for its login timer, which no Init resets, to pass 21.66 s
  again. KO 1298 plays `Snd/Intro_Sound.mp3` instead (44.1 kHz stereo, 4,096
  frames, 107 s; the file's cut-short 4,097th frame is dropped), looping on
  login, select and create, carried as its frames (Q69); RQ-018 to RQ-078 cooked
  it, and a 1298 choice would name it. KO 1298 (binary, `KnightOnLine.exe`):
  the login proc `005f68e0` creates the BGM stream for that file (`0044d240`),
  loops it (`004504a0(1)`) and plays it (`004501b0`), or keeps a BGM of the
  same file already playing; the select proc `005f98c0` restarts it only when
  the flag `00818408` is set (not decoded) and otherwise keeps it; the select
  releases it when the chosen character's clip has played, before "Loading
  data..." (`005fea70`, `005fe280`). The create proc does not touch it
  (source: `GameProcCharacterCreate.cpp`).
- The select arrows' turn sound (RQ-077, Q70): `select.turn_sound`, sound
  table 2501 (`Snd/char_select_turn.wav`, up to 9 at once), cooked into
  `audio.bin` as `front:select-turn` by `tools/assetc/ko_bake.py`. The client
  plays it once for each turn an arrow starts: not at the end of the row, not
  while the camera turns and not while the start clip plays. It is one voice, so a new
  turn stops the last play and starts again at the first sample. It is
  unpositioned, at the voices' gain. KO 1097 (binary,
  `specs/KO-FINDINGS.md` §8.2): the select Init `0043a950` creates sound
  2501 as the proc's sound object, and DoJobLeft and DojobRight
  (`0043e310`, `0043e380`) play it through `004327d0` for each turn they
  start. KO creates it as a 3D sound and passes no position; that gain and pan
  were not read. 1298 plays no rotate sound (`005fe3c0`, `005fe450`; no 1298
  function names 2501), so this is the 1097 hall's (Q71), not 1298's.
- Other sounds (RQ-071, RQ-077, Q70): none. KO's UIF buttons play only the hover
  and click sounds their file names (binary: 1298's button loader `00403fc0`
  creates them with `0044d240`, which creates nothing for an empty name;
  1097's `00403ac0` creates one only for a name longer than 0). Every button,
  static, edit and window of the five layouts above names none (local-asset:
  each sound string in `co_login_us.uif`, `ka_characterselect_us.uif`,
  `Ka_CharacterCreate_us.uif`, `ka_loading_us.uif` and `co_MsgBoxOk_us.uif`
  is empty). So do 1097's Karus layouts (`co_login.uif`,
  `Ka_CharacterSelect.uif`, `Ka_CharacterCreate.uif`, `Ka_MessageBox.uif`,
  `Co_Loading.uif`, `ka_loading.uif`). So `front-end.bin` carries no UI sounds.
- Option.ini (`client/render/options.h`): `[Sound] Effect=0` silences the
  music and the turn sound, as it does every KO 1298 sound object (`0044d240`,
  `006453b0`); `[Sound] Bgm` is 1298's zone-music switch only (`00640b10`) and
  does not touch it. 1097's switch is `[Sound] Enable` (`0054ec5e`), which
  does the same; the realm reads 1298's key (Q70).
