# Front end (N3FE, engine 42)

`front-end.bin` is an optional presentation file (spec 11): KO's 1098 login scene,
login and server list, the Karus character select hall, character create, loading
and the OK message box, the screens' music (version 3, Q57), and each model
clip's blend time and the select spot's growth rate (version 4, RQ-075).
`tools/assetc/ko_front_end.py` cooks it from the pinned client tree with the
choices in `games/moradon/front-end.json`; the client's
`load_front_end` (`client/assets/assets.cpp`) reads it and the server reads only
its header. A package with it is engine 42, so wire 30 (as engines 38–41). Its bound is
64 MiB (`FRONT_END_FILE`, `MAX_FRONT_END_ASSET`, `kFrontEndFile`), since it holds
two character models and the UI art.

Integers are little-endian u32, reals f32; strings are a u32 length and that many
bytes. Engine space is KO's with z negated (KO is left-handed).

## Layout

1. `"N3FE"`, version 4, character slots (1–3; the server's character limit),
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
   above 0 and at most 100), the hall (part count ≤64, each a mesh), the model
   (version 4: three clips, by role the hover, start and rest clips), its
   plugs.
8. The create model and its plugs (version 2): `CGameProcCharacterCreate`'s
   player (`InitChr`: the race's `UPC_DefaultLooks` joint, animation and default
   parts) with one clip, `ANI_BREATH` (0), and no plugs (a new character holds
   nothing). The select model's seated clips are for the hall's thrones.
9. Music (version 3, RQ-018): a track count (≤4), each its sample rate,
   channels (1 or 2), loop (0 or 1), an MPEG frame count and a byte length
   (1 to 16 MiB) and then that many bytes: MPEG-1 or MPEG-2 Layer III frames
   back to back, every one whole, at the track's rate and channel count (free
   format, MPEG 2.5 and reserved header values refused; a CRC is allowed). Then
   four track indices, `0xffffffff` for none: the login screen (the realm list
   too), select, create and loading. The client (`client/assets/music.h`)
   checks every frame at load and streams a track while its screen shows:
   one frame decoded at a time (minimp3, `UPSTREAM.md`), resampled linearly
   to 48 kHz, mixed unpositioned at the voices' gain and kept up to six audio
   chunks (128 ms) ahead. A screen naming the track already playing keeps it
   (an ended one too); another track starts at its first frame; none, and
   entering the world, stops it. A looping track starts again at its first
   frame, with a fresh decoder; one whose whole pass decodes nothing ends.

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
- Slot: position, yaw (radians, engine space), the camera eye that faces the
  slot (the scene camera's `at` and up apply), and the slot's spot light (one
  light record). The spot's theta is the widest it opens; the client widens it
  from 0 at the select scene's rate while the pointer is on the character in
  front and narrows it at that rate otherwise, and the spot is off at 0
  (1097: `0043f280`, below).
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
  (`specs/KO-FINDINGS.md` §8.1, binary, Q71): at rest, every tick, the
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
  each tick) and keeps its theta for the next slot. ENTER or a click starts
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
- Music: `Snd/Intro_Sound.mp3` (44.1 kHz stereo, 4,096 frames, 107 s; the
  file's cut-short 4,097th frame is dropped), looping, on login, select and
  create; loading is silent. KO 1298 (binary, `KnightOnLine.exe`): the login
  proc `005f68e0` creates the BGM stream for that file (`0044d240`), loops it
  (`004504a0(1)`) and plays it (`004501b0`), or keeps a BGM of the same file
  already playing; the select proc `005f98c0` restarts it only when the flag
  `00818408` is set (not decoded; the realm's flow never returns from the
  world to select) and otherwise keeps it; the select releases it when the
  chosen character's clip has played, before "Loading data..." (`005fea70`,
  `005fe280`). The create proc does not touch it (source:
  `GameProcCharacterCreate.cpp`). The 1098 scene's own login sound (sound
  table 35, `GameProcLogIn_1098.cpp`) is not 1298's and is not used.
- Other sounds (RQ-071, Q70): none, as KO 1298 plays none on these screens.
  Its UIF buttons play only the hover and click sounds their file names
  (binary: the button loader `00403fc0` creates them with `0044d240`, which
  creates nothing for an empty name), and every button, static, edit and
  window of the five layouts above names none (local-asset: each sound string
  in `co_login_us.uif`, `ka_characterselect_us.uif`,
  `Ka_CharacterCreate_us.uif`, `ka_loading_us.uif` and `co_MsgBoxOk_us.uif`
  is empty), so `front-end.bin` carries no UI sounds. The select's left and
  right (`005fe3c0`, `005fe450`) play no sound, and neither the select proc,
  its UI class (`00606a90`) nor any sound-table creator names sound 2501
  (`char_select_turn.wav`): `ID_SOUND_CHR_SELECT_ROTATE` is the later
  source's (`GameProcCharacterSelect.cpp`), not 1298's.
- Option.ini (`client/render/options.h`): `[Sound] Effect=0` silences the
  music, as it does every KO 1298 sound object (`0044d240`, `006453b0`);
  `[Sound] Bgm` is 1298's zone-music switch only (`00640b10`) and does not
  touch it.
