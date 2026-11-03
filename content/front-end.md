# Front end (N3FE, engine 42)

`front-end.bin` is an optional presentation file (spec 11): KO's 1098 login scene,
login and server list, the Karus character select hall, character create, loading
and the OK message box, the screens' music (version 3, Q57), each model
clip's blend time and the select spot's growth rate (version 4, RQ-075),
PCM music tracks with a restart period (version 5, RQ-083), the select
hall's front-clip mode (version 6, RQ-086), the select camera's turn mode
with 1298's recorded camera paths (version 7, RQ-087), a KO zone drawn as
the select hall with the select camera's fog (version 8, RQ-095), a logo
screen before the login (version 9, RQ-101: 1264's "K2 Network presents Knight
Online"), each message box message's title and wording (version 10,
RQ-102, Q81), where each layout's nodes go on a window of its own size
(version 11, RQ-106, Q82), the action `login_closed`, a login node drawn
only while the login group is not (version 12, RQ-108, Q85), 1298's select
bar's actions and two messages (version 13, RQ-109), the message box's
Yes and No with the select's exit question (version 14, RQ-111), what ESC
presses on the select (version 15, RQ-116) and its `none`, 1298's (version 16,
RQ-119).
`tools/assetc/ko_front_end.py` cooks it from the choice's KO trees with the
recipe of the front end the realm chose ("Choosing the client", below; for
Moradon's default, 1097, `games/moradon/front-end.json`); the client's
`load_front_end` (`client/assets/assets.cpp`) reads it and the server reads only
its header. A package with it is engine 42, so wire 30 (as engines 38–41). Its bound is
64 MiB (`FRONT_END_FILE`, `MAX_FRONT_END_ASSET`, `kFrontEndFile`), since it holds
two character models and the UI art.

Integers are little-endian u32, reals f32; strings are a u32 length and that many
bytes. Engine space is KO's with z negated (KO is left-handed).

## Layout

1. `"N3FE"`, version 16, character slots (1–3; the server's character limit),
   canvas width 1024 and height 768.
2. Textures: a count (≤256 since version 8, ≤64 before), each width and height
   (1–1024) then RGBA8 rows.
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
   below), the select's ESC (version 15: 0 back, 1 exit; version 16: 2 none; below), the turn mode (version 7: 0 rotate, 1 path; below) and a path count
   (0 in the rotate mode, 1–8 in the path mode) and the paths, the hall (part
   count ≤64, each a mesh; version 7: it may be 0), the zone (version 8: a
   mesh count, 0–256, 0 when the hall has parts, each a zone mesh; below), the
   fog (version 8; below), the model (version 4: three
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
   not, so it never ends; the period takes precedence over the loop. The
   period counts from the stream's start (RQ-105, Q75 (a);
   `client/render/audio.h`): every entry to a screen whose track is not the
   one playing starts it at its first sample at once, a return to the login
   included. The client also carries KO 1097's and 1264's process clock
   (RQ-096), off by default (`AudioMixer::carry_music_clock`, RQ-103's
   realm-owner option): the period's clock is then the track's for the
   process, counting only while a screen naming the track shows; the first
   entry starts the track at once and a later one only when the clock next
   reaches the period, silent until then. No byte of this section changes
   with it. The login scene (item 6) keeps time by its screen's restarting
   track (RQ-104, Q83; `client/render/scene_clock.h`): its clock starts at 0
   on each entry to the login (the login or the realm list after any other
   screen, a return from the world included), as KO's login Init starts its
   character's clip at its first frame (`specs/KO-FINDINGS.md` §9.1), and
   while a device plays that track it is held to the listener's position in
   the track's period: within the block the device has taken and is playing
   (the frames mixed less those still queued for the device are its end),
   running on the frame time inside it, so its steps stay even and none goes
   back. The clip and the track restart together, and a stall the device runs
   dry over leaves them in step. Otherwise, and from where it was when the
   track stops being heard (the device closed), it runs on the frame time.
10. The logo screen (version 9, RQ-101; `client/render/front_logo.h`): 0 for
   none, or 1 and then its nodes (a node count, 1–1024, and the nodes as a
   screen's, item 4: groups, images and strings only, none bound to an action),
   a group count (1–8) and each group: its node (a group node of the screen, each
   once) and its fade-in, hold and fade-out (reals, seconds, each 0–60, together
   above 0 and at most 60); then the music: a track (an index of item 9's tracks,
   or `0xffffffff` for none), its delay (seconds, 0–60), the group its fade-out
   starts with (or `0xffffffff` for none; a group needs a track) and the
   fade-out's seconds (above 0 and at most 60 with a group, 0 without); then the
   flags (1: a key press skips the screen; 2: the system cursor is hidden while
   it shows; nothing else). A package with a logo screen starts on it, once a
   process, before the login (1264's WinMain, `00602506`). The groups show one at
   a time, in order, each alone (the screen's other nodes, outside every group,
   always): a group's alpha rises linearly over its fade-in, holds at 1 and falls
   linearly over its fade-out, cut to 255ths as KO's texture factor is, and the
   whole screen draws at it over the black clear (no scene). After the last group
   the login starts. Its music starts its track at its first sample once the
   delay has run, at full gain, and from the start of its fade group the gain
   falls linearly to 0 over the fade, after which the track stops; the login
   then plays its own track, so a skip cuts the logo's off. The time is the sum
   of the client's frame times from the screen's first frame (each at most
   0.25 s). With the skip flag a key pressed while the screen shows starts the
   login: a key down (not a repeat) stamped at or after its first frame, other
   than a modifier within 100 ms after a focus gain (a window system reporting
   a key already held; Q82); a click does nothing. The realm connection starts
   when the screen ends, as 1264 connects from its login; a message raised
   while it shows (the latest) waits for the login. A reset connection leaves
   the screen playing.
11. The messages (version 10, RQ-102, Q81): a count (0–11, at most one per
   message) and each: the message (an index of the closed set below, each
   once), its title (≤1024 ASCII bytes, may be empty), whether its text
   replaces the client's own wording (0 or 1) and that text (≤1024 ASCII
   bytes; empty unless it replaces). The set, by index, is the engine's
   (`FrontMessage`, `client/assets/assets.h`): 0 `connect_failed` (the realm
   cannot be reached after a login press), 1 `disconnected` (the connection
   closed: a drop or a kick), 2 `login` (the Discord flow's other failures and
   the address to open), 3 `login_blocked` (the realm refused the login: a
   banned account), 4 `login_unavailable` (the realm refused the login: a
   dependency is down), 5 `create_name` (create with an empty name),
   6 `create_refused` (the realm refused a create), 7 `select_refused` (the
   realm refused a select), and (version 13, RQ-109) 8 `create_full` (create
   with every slot taken: 1298's `btn_create`) and 9 `delete_disabled` (delete,
   which the realm does not offer: 1298's `btn_delete`), and (version 14,
   RQ-111) 10 `exit_confirm` (the select's exit, asked yes or no: 1298's
   `btn_exit`, 1264's `bt_exit`; named, it makes the select ask, "Actions" below). The client shows a message in the message box
   with the package's title in the node bound to `title` (empty for a message
   the package does not name) and the package's text where it replaces, its
   own wording otherwise. The cook writes the recipe's `messages` (below): a
   title or text is the recipe's string or one row of a KO client's text
   table (`{"table": "<input>:Data/Texts_us.tbl", "row": N}`, decrypted as
   `tools/assetc/ko_tbl.py` reads it; 1264 and 1298 look a row up by its id,
   1264's `005d2350`); it refuses a title without a `title` binding on the
   message screen, `exit_confirm` without both `yes` and `no` bindings there
   (version 14), a row the table lacks or holds twice, and text that is not
   printable ASCII.
12. The placement (version 11, RQ-106, Q82; `client/assets/front_place.h`):
   flags (0, or 1: the client scales the canvas to fit the window), then for
   each of six layouts, the five screens of item 4 in order and then the logo
   screen's (item 10; none without one), a move count (≤32; 0 for the logo
   screen without one) and each move: a node of that layout, then its x rule
   and its y rule. A rule is a kind and two reals a and c (finite, |a| ≤ 4,
   |c| ≤ 16384): 0 keep (a and c 0: the coordinate stays where the earlier
   moves left it), 1 linear (trunc(a·S + c)), 2 half
   (trunc(floor(S / 2) + a·S + c)), S the window's width for x and height for
   y and trunc C's cast toward zero. A move puts its node's top-left there and
   moves the node's subtree with it (KO's `MoveOffset`); a layout's moves
   apply in order, its root's first. The rects of item 4 (and item 10) are the
   moves applied at the canvas's size, and the loader checks that they are
   (each within half a pixel). With flags 0 the client draws every layout
   unscaled on the window's own pixels, its moves applied at the window's size,
   as KO places its UI by the viewport each time a layout loads
   (`specs/KO-FINDINGS.md` §9.3): where no node draws the window shows the
   scene behind the UI or the clear's black. With flags 1, or on a window
   smaller than the canvas (KO's placements would cut a layout off there), it
   applies no moves and scales the canvas to fit the window, centred (the
   realm's look before version 11). Hit tests and the cursor take the same
   pixels as the drawing; the 3D views (the intro, the hall, the create
   figure) keep their projection either way, the hall's centre rect a share
   of the window and the intro backdrop item 6's.

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
  is the scene camera's own eye; in the path mode the last eye key of the path
  into the slot, which the client does not read), and the slot's spot light (one
  light record). In the rotate mode the client turns the scene camera's eye about the vertical through
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
- The select's ESC (version 15, RQ-116; `client/render/front_end.h`): what ESC
  presses on the select, in every select state but two: in the path mode ESC
  while a path plays still skips it (below), and in both modes ESC, like a
  click on the select's `exit`, does nothing while the start clip plays
  (RQ-121: KO's select takes no input then, `specs/KO-FINDINGS.md` §9.10),
  whatever this says. So in the rotate mode it presses while the camera turns
  too. 0, back (the realm's): the select's `back`.
  1, exit (1264's: its select's OnKeyPress, `004454e0`, sends `DIK_ESCAPE` to
  ReceiveMessage as a click on `bt_exit`, `specs/KO-FINDINGS.md` §9.8): the
  select's `exit`, as a click on it, so a package that names `exit_confirm`
  asks the exit question and one that does not leaves at once. The node bound
  to `back` keeps its click either way. The recipe names it
  (`select.escape`: `back`, the default, `exit` or `none`).
  2, none (version 16, RQ-119; 1298's, `specs/KO-FINDINGS.md` §9.9, binary:
  its bar's OnKeyPress, `00607810`, presses no button for ESC; it sends it to
  `005faad0`, which only puts the select at rest, skipping a playing path):
  nothing, so ESC only skips a path and otherwise does nothing, the start
  clip's time included. The nodes bound to `back` and `exit` keep their
  clicks.
- Turn mode (version 7, RQ-087): how the camera goes from slot to slot.
  - 0, rotate (1097, `0043e4e0`; the slot above): the eye turns about `at`.
    No paths; the select UI shows throughout.
  - 1, path (1298, `005fa670`, `005fe5b0`; `specs/KO-FINDINGS.md` §8.4,
    `client/render/select_path.h`): the camera plays a recorded path. A path is
    its from slot (`0xffffffff`: the entry path), its to slot (below the slot
    count; the entry path's is 0; from and to differ), then the eye's keys and the
    at's keys (engine space), each set a rate (keys a second, above 0 and at most
    1000) and a key count (1–4096) and the keys (3 reals each). A from and to pair
    is there at most once; the entry path and both ways between the neighbours the
    arrows turn between (left to right 1, 0, 2) must be. The path's last frame is
    the larger of its sets' count × rate / 30; the client advances the frame 30 a
    second (a path started since the last frame takes one step more, its load's),
    holds it on the last, and takes each set's key i = trunc(frame × rate / 30),
    the last key at the count, key i blended toward key i + 1 below it
    (`CN3AnimKey::DataGet`). The scene camera's up, field of view, near and far
    apply. The entry path flies the camera in to slot 0 when the hall opens from
    the realm list (KO's Init); an arrow plays the path from the slot to its
    neighbour; the camera has arrived on the frame after the one that reached the
    path's last frame. While it plays, the whole select UI is hidden (no node
    draws or takes a click; Q77) and ENTER or ESC put the camera on the last frame
    and arrive. At rest the camera is on the last frame of the path into the slot
    (the entry path's for slot 0, the one from slot 0 for the others), which is
    where the realm puts it on returning to the hall from create or a start
    (Q78). The characters play the turn as the front-clip mode says.
- Zone (version 8, RQ-095; `specs/KO-FINDINGS.md` §8.4,
  `client/render/select_zone.h`): the terrain and shapes of a KO zone the
  select draws in place of a hall. Each mesh is a mesh record (below) and its
  sort point (3 reals, engine space); a zone mesh's flags are 4 unlit or none,
  and exactly one of 16 cut-zero (opaque: its texels of alpha 0 are cut, KO's
  alpha test GREATER than 0) and 8 blend (source alpha over its inverse, depth
  tested and written, texels of alpha 0 cut); it is drawn culled (a
  double-sided part's back faces are triangles of their own) with the select's
  lights. The opaque meshes draw before the hall's characters; the blend meshes
  draw after the select UI and the message box, far to near by the eye's
  distance to their sort points (a tie in file order), as 1298's alpha flush
  does. The zone's meshes together hold at most 196,608 vertices and 589,824
  indices (N3W1's bounds).
- Fog (version 8): on (0 or 1), colour (3 reals, 0–1), start and end (reals,
  metres from the eye; on: 0 ≤ start < end ≤ the select camera's far; off: all
  0). Every draw of the select scene, the zone, the hall, the characters and
  their plugs, lit or not, takes D3D's linear range fog: its colour kept by
  (end − d) / (end − start), clamped to 0–1, d its distance from the eye,
  mixed toward the fog colour (the client per pixel, D3D per vertex). The intro
  and create draw without fog.
- Model: a byte length and an N3S1 or N3SM scene (`tools/assetc/gltf.py`, atlas
  up to 2048 a side), then a count of further clips and each clip's byte length
  and track list (N3S1's track encoding, on the model's nodes), then (version 4)
  each clip's blend time, seconds, 0–10: the time the client blends into the
  clip over. That is the KO clip record's `fTimeBlend`, which `CN3Chr::AniCurSet`
  takes when the caller names no time of its own, or the caller's own time where
  the package's choices name one (Moradon: the start clip's, `start_blend`).
- Plug: the KO joint index (below the model's joint count), then a mesh in that
  joint's space: world = instance × `Scene::joint_matrix` × vertex.
- Mesh: texture, flags (1 double-sided, 2 alpha test at 0.5; a zone mesh's
  above), material diffuse
  and ambient (3 reals each), a vertex count (1–65536) of 8 reals (position,
  normal, uv), an index count (a multiple of 3, ≤196608), the indices.

The loader refuses an unknown action, a screen missing one of its required
actions (login: `login`, `exit`, `login_group`, `realm_group`, `realm_list`,
`realm_connect`; select: `select_prev`, `select_next`, `back`, `exit` and an
info text, `char_info` or (version 13) any of `char_name`, `char_level` and
`char_class`; create: `create_confirm`, `back`, `name_field`, `char_view`;
loading: `progress`; message: `message`, `ok`), an action bound twice in a
screen, an unknown turn mode, paths in the rotate mode, a path outside the slots
or from a slot to itself, an entry path not to slot 0, a from and to pair twice,
the path mode without its entry path or a way between neighbours, a hall with
a zone, a zone mesh's flags other than above, fog values outside their bounds
(or not all 0 when off), a message outside the set or named twice, a replace
flag other than 0 or 1 or a text that does not replace, a node bound to
`login_closed` on a screen other than the login (version 12), a node bound to
`select_start`, `select_create`, `select_delete`, `char_name`, `char_level` or
`char_class` on a screen other than the select (version 13), a node bound to
`yes` or `no` on a screen other than the message box, or `exit_confirm` named
without nodes bound to both on it (version 14), a select ESC other than 0, 1 or
2 (version 15; 2 since version 16), placement flags
other than 0 or 1, a move of a node outside its layout or of a logo screen the
file does not have, a rule of another kind or outside its bounds, a keep rule
with a or c not 0, moves that do not leave the canvas rects where the file puts
them, and every reference, count and bound above, truncation or trailing bytes.

## Actions

The closed set, by index: none, `login`, `exit`, `login_group`, `realm_group`,
`realm_list`, `realm_connect`, `notice`, `select_prev`, `select_next`, `back`,
`char_info`, `create_confirm`, `name_field`, `char_view`, `class_desc`,
`progress`, `version`, `info`, `message`, `ok`, `title` (version 10), `login_closed`
(version 12), `select_start`, `select_create`, `select_delete`, `char_name`,
`char_level`, `char_class` (version 13), `yes`, `no` (version 14). A group bound to `login_group` or
`realm_group` is shown in its state only; `realm_list` lists the realm from
`realm.json`; `notice`, `char_info`, `class_desc`, `version`, `info`,
`message` and `title` (the message's title, item 11) are texts the client fills; `name_field` is the name entry; `char_view`
is where create draws the character.

1298's select bar (version 13, RQ-109, `specs/KO-FINDINGS.md` §9.6,
`client/render/select_bar.h`), select screen only: `select_start` is the
start ENTER and the centre click make (the character in focus, or create for
an empty slot; at rest only); `select_create` opens create for the slot in
focus when it is empty, else for the first empty slot (the camera put on it),
else shows the message `create_full`; `select_delete` shows the message
`delete_disabled` for a character in focus at rest, and does nothing else. The
texts `char_name`, `char_level` and `char_class` are the character in focus's
name, level (decimal) and the `class_name` string while the hall is at rest
(the loop front-clip mode: always at rest; hover: while the pointer is on the
character, as `char_info`), and empty for an empty slot or otherwise.

The message box's styles (version 14, RQ-111, `specs/KO-FINDINGS.md` §9.7,
`client/render/message_box.h`), message screen only: every message shows in an
OK box, the node bound to `ok` drawn and those bound to `yes` and `no` hidden,
but `exit_confirm`, which shows in a yes/no box, `yes` and `no` drawn and `ok`
hidden (1298's SetBoxStyle, `00527a40`). In an OK box ENTER, the keypad's ENTER
and ESC press OK; in the yes/no box ENTER and the keypad's ENTER press Yes and
ESC presses No (OnKeyPress, `00527c60`); a click released on a drawn button
presses it. Every press closes the box; Yes on `exit_confirm` also leaves the
game (`BEHAVIOR_EXIT`, `00526d00`). A package that names `exit_confirm` (section
11) makes the select's `exit` ask in that box instead of leaving at once (1298's
select bar's `btn_exit`, `00607160`; 1264's `bt_exit`, `00444e60`, RQ-115, which
asks in the same box, `0050bfb0`, `0050c1d0`, `0050b510`), and so ESC on the
select where the package's select ESC is exit (version 15); the login's `exit` and a package that does
not name it leave at once. The client's own wording for it is "Exit the game?".

On the login screen (RQ-108, Q85, RQ-110, `client/render/front_login.h`) a
login under way closes the login group:
from a login press (held while the realm
connection comes up) or a stored session's login, through the Discord
browser step and its code, to the realm's answer, the node bound to
`login_group` and everything under it is hidden (no hit tests) and a node bound
to `login_closed` (login screen only) is drawn; on the realm list the
`login_closed` node is drawn too, beside the realm group. At rest, after a
failed login, and after a reset or dropped connection, the login group draws and
the `login_closed` node does not. That is KO's SetVisibleLogInUIs
(`specs/KO-FINDINGS.md` §9.4): 1264 hides its login bar from the press until the
answer and shows its copyright line meanwhile; a failure shows the bar again,
a success keeps the line into the server list. ESC still cancels the browser
step while the bar is hidden. 1298 hides its bar the same way and has no line
(`specs/KO-FINDINGS.md` §9.5, RQ-110), so a layout with no `login_closed` node hides its login group
through a login too and shows neither (RQ-108 kept such a layout's bar up; Q86).

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
`build/ko-reference/<name>/client` of a pinned install, `installer-1097`,
`installer-1264` or `installer-2145`, whose `manifest.json` (the unpacker's, beside `client/`)
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
| `1097` | `front-end.json` | `assets/ko`, `installer-1264` (`build/ko-reference/installer-1264/client`) | Default. 1097's login scene, select hall (`front_clip` `hover`), turn sound and music (RQ-083: `bgm_login.wav` restarting every 21.66 s, `bgm_el_battle.wav` looping); the 1264 client's English screens (RQ-085, the maintainer's choice over 1097's Korean art): its layouts and their textures from the 1264 install, its message box and its no-victor loading screen, and (RQ-101) its logo screen before the login (`specs/KO-FINDINGS.md` §9.2) |

Not offered yet: `1298`, `2145` (its UIF versions, its Ogg sounds, its clip
format) and `steam` (its packs, its protected exe, the pin). Each is its own
queue item; until it lands the cook refuses it as above. 1298's select
character is data already (RQ-086), its camera paths, slots and spots with
the select UI hidden while the camera moves (RQ-087), and its hall, the
`karus_intro` zone, with the camera's fog (RQ-095):
`games/moradon/front-end-1298.json` ("1298", below) cooks from the pinned tree,
but `front-ends.json` does not offer it until its UIF login intro is data too
(RQ-088); its zone's sky is not drawn yet.

## 1298 (`games/moradon/front-end-1298.json`, not offered)

The parts of 1298's front end the format expresses (RQ-086, RQ-087,
`specs/KO-FINDINGS.md` §8, §8.3 and §8.4, binary); every other part is the 1097
recipe's, as "Moradon" below says, or missing, and marked here:

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
  Karus) and stays; the info texts show at rest, empty for an empty slot
  (`006074c0` writes the empty string; `select_hint`, which only `char_info`
  shows, is empty).
- `turn` `path` (`005fa670`, `005fe5b0`): `ChrSelect/Data/ka_lording_camera.n3camera`
  flies the camera in to the centre slot in 6 s as the hall opens;
  `ka_center_left`, `ka_center_right`, `ka_left_center` and `ka_right_center`
  turn it between the centre and the side slots in 4 s each (1298's paths 2–5;
  `ka_left_right` and `ka_right_left` are only 1298's in-select create's move,
  `005ff920`, and are not cooked). The select UI is hidden while a path plays;
  ENTER or ESC skip to its end.
- Slots, spots and camera (`005fb4f0`, `005f98c0`, `005fb1c0`): the characters at
  (128, 0, 91), (108.7, 0.2, 62.9) and (141.3, 0.3, 68.5) turned 180°, 110° and
  245°; each spot 2 m above and behind its character, pointing at it, phi 1.5; the
  camera's rest eye and at (128.011, 0.534, 85.922) and (128.077, 4.087, 105.862),
  field of view 0.96, near 0.1, far 500. These are the `karus_intro` zone's
  coordinates.
- Zone (`select.zone` 10001, `select.fog` true; RQ-095, `specs/KO-FINDINGS.md`
  §8.4, binary): 1298's select Init (`005f98c0`) loads zone 10001
  (`00600950`, `0046c9d0`), `Data/Zones.tbl`'s `karus_intro`
  (`Zones/karus_intro.gtd`, `.tct`, `.opd`), and Render (`005fb1c0`) draws the
  world's terrain and shapes before the characters. `select.zone` names a
  Zones.tbl key of the first input (or `<input>:<key>`); the cook reads its row's
  terrain, colour map and objects as the world loader does (`005a3110`:
  `ko_zone`'s row and name checks; an OPDEXT is refused), checks every file the
  zone names is there, and expands it as the package's world is
  (`ko_scene.expand`): every 4 m tile with its tile texture or, where 1298
  draws the colour map (`005a2640`), the colour map unlit; every static,
  shown-event and texture-cycling shape's parts in their loaded pose. It
  groups the triangles into zone meshes by texture and light, each alpha part
  (`RF_ALPHABLENDING`) a blend mesh of its own with its sort point. For
  `karus_intro`: 63 native textures (128–512 a side), 88 meshes (19 blend),
  40,540 vertices and 30,966 triangles; the 1298 recipe's `front-end.bin` is
  about 56.1 MB of its 64 MiB (54.0 MB before RQ-109's select bar). Every mesh takes the material
  1298's terrain render sets (`0059cd90`: diffuse 1, ambient 0.5); the cook
  refuses a zone part whose own material differs (every `karus_intro` part's
  is that, local-asset), a second tile layer (`karus_intro` has none), a
  texture sequence and an alpha part not blended source alpha over its
  inverse. The fog (`004395c0`, `005fb1c0`): the camera files' (each Karus
  path's: on, white), linear range fog from 50 to 500 m (0.1 × and 1 × the far
  Render sets, 500). Not drawn yet (QUESTIONS Q79): the zone's sky
  (`Misc/Sky/Karus.N3Sky`; Render clears to the sky's colour and draws the sky
  first, so the background stays black), its terrain light maps
  (`karus_intro.tlt`), grass and birds, and its animated shapes (11 of 100:
  those the world bake leaves out too, `ko_shapes.classify`). Approximations:
  the terrain's near tiles everywhere (1298 draws far patches from the colour
  map), the shapes' full-detail meshes (no progressive LOD), the textures'
  mip chains made by the client (KO's DXT files carry their own), fog per
  pixel.
- No turn sound: 1298 plays none (`select.turn_sound` absent).
- `select.escape` `none` (RQ-119, the maintainer's choice, 2026-11-02: "Do
  nothing, as 1298"): ESC on the select skips a playing path and otherwise
  does nothing, as 1298's (RQ-117, `specs/KO-FINDINGS.md` §9.9, binary):
  1298's bar OnKeyPress (`00607810`) presses no button for ESC; it calls
  `005faad0`, the select tick's own ESC body, which skips a playing path and
  at rest changes nothing (Q87). Back and Exit stay on their buttons.
- Music: `Snd/Intro_Sound.mp3`, looping on login, the realm list, select and
  create; loading silent (`005f68e0`, `005fea70`, "Moradon" below).
- Still the 1097 recipe's, not 1298's: the 1098 login scene (1298 draws a UIF
  intro), and the login, create and loading layouts (the pinned tree's
  `UI_US`, as today). The hall lights `ka_light_0/1` are the files both
  clients name.
- Select (RQ-109, version 13, `specs/KO-FINDINGS.md` §9.6, binary): 1298's own,
  `UI_US/co_CharacterSelect_us.uif`, a 1024 × 113 bar, every node drawn,
  `place` `{"bottom": 10}` (its Load `00606c10`: ((W − w) >> 1, H − 10 − h)),
  bound as its ReceiveMessage (`00607160`) and info fill (`006074c0`) use it:
  `btn_start` `select_start`, `btn_create` `select_create`, `btn_delete`
  `select_delete`, `btn_back` `back`, `btn_exit` `exit`, `btn_left`
  `select_prev`, `btn_right` `select_next`, `str_id` `char_name`, `str_lev`
  `char_level`, `str_job` `char_class`. `messages` words `create_full` with
  row 7675 ("Cannot create additional characters.") and `delete_disabled`
  with row 1501 ("Character deletion has been disabled currently") of the
  pinned tree's `Data/Texts_us.tbl`, untitled, as 1298 posts them. Not 1298's
  (QUESTIONS Q87): Back returns to the login (1298's to the server list), an
  arrow with no neighbour is hidden (1298 draws both), and Create from an
  occupied slot puts the camera on the empty slot (1298 flies it there). Exit
  asks, as 1298's does (below).
- Message box (RQ-111, version 14, `specs/KO-FINDINGS.md` §9.7, binary): 1298's
  own, the one its box manager (`005282a0`) loads for every message, the pinned
  tree's `UI_US/el_messagebox_us.uif` (row 2, column 26 of its
  `Data/UIs_us.tbl`) with the pinned tree's `ui_message_us.dxt` (its frame
  grey), centred; the recipe drew `co_MsgBoxOk_us.uif` before, which 1298's
  MessageBoxPost never loads. `Text_Message` is bound to `message`,
  `Text_title` to `title` (every 1298 recipe message is untitled, so it draws
  empty), `btn_ok` to `ok`, `btn_yes` to `yes` and `btn_no` to `no`;
  `Edit_Common` and `btn_cancel` hidden. `messages` words `exit_confirm` with
  row 1502 ("Are you sure you want to exit? "), untitled, as 1298's
  `btn_exit` posts it (`00607160`: `MB_YESNO`, `BEHAVIOR_EXIT`), so the bar's
  Exit asks: Yes (KO labels it "O  K") or ENTER leaves, No ("Cancel") or ESC
  closes the box. The login's Cancel leaves at once, as 1298's does (source).
- Placement (RQ-106, `specs/KO-FINDINGS.md` §9.3, binary): the 1097 recipe's
  `place` and `moves` (1264's code) for the login, create, loading and message
  layouts, but for the login's copyright line (below); the select's is 1298's
  (above).
- The copyright line (RQ-110, `specs/KO-FINDINGS.md` §9.5, binary): hidden.
  1298's login draws none: its Init (`005f68e0`) loads only the nation's
  intro layout (`ka_login_intro_us.uif` or `el_login_intro_us.uif`), which has
  no `Text_Rights`, and the image names no `Text_Rights`. Its login bar hides
  from a login press until a failed answer, and stays hidden into the server
  list after a success (`005f74c0`, `005f7b50`), as 1264's does, so while a
  login is under way the 1298 recipe shows neither the bar nor a line; its
  realm list has no line.
- Lights (`select.light_manager`; RQ-095, `specs/KO-FINDINGS.md` §8.4, binary):
  1298's select Init (`005f98c0`) resets its light manager (`CLightMgr`,
  Release `005ba7a0`) and every select tick (`005faf10`) applies the hall lights
  (D3D lights 0 and 1, point lights 7 m round the hall's origin, far from the
  zone's slots) and then the manager's (`005baae0`): light 0 directional,
  straight down, diffuse 0.8, ambient 0.56; light 1 directional, straight up,
  diffuse 0.5, ambient 0.35; light 2 a point light at the origin, diffuse 0.3,
  ambient 0.21, range 128, attenuation (0.5, 1/64, 1/2048). They replace the
  hall lights of their number, so the zone and the characters are lit by the
  manager's lights and the front slot's spot. `select.light_manager` lists such
  lights in KO space (each a `number` 0–7 once, a `kind`, `point` with
  `position`, `range`, `falloff` and `attenuation` or `directional` with
  `direction`, and `diffuse` and `ambient` colours 0–1); the cook writes the
  select's lights as the tick leaves them, by number (a directional light's
  range and attenuation, which D3D ignores, as 1 and (1, 0, 0)). The 1097
  recipe names none: its lights are as before.

## Moradon (`games/moradon/front-end.json`)

- Logo (RQ-101, Q82, `specs/KO-FINDINGS.md` §9.2, binary): 1264's, first in the
  process. `logo` names the layout (`installer-1264:UI_US/co_usa_logo_us.uif`,
  `place` `centre`: its root is the canvas), its `groups` (`group_k2`,
  `group_presents`, `group_knight`) each with KO's `seconds` (1.5, 1 and 1.5:
  `00601360` raises its fade value by the frame time over them) and KO's `peak`
  (1.5, `00648f10`), from which the cook writes each group's fade-in (`seconds`),
  hold (2 × (`peak` − 1) × `seconds`) and fade-out (`seconds`): 4.5, 3 and 4.5 s,
  12 s in all; `music` (`track` 2, `installer-1264:Snd/bless.wav`, once, 22,050 Hz
  mono, 13.84 s; `delay` 1 s, `005fa7c0`; `fade_group` 2 and `fade` 4 s,
  `004371a0(4.0)`); `skip` `key` (`00601480`: any key, no click) and `cursor`
  `hidden` (`00601140`). **Whether the screen shows is this one key** (and so the
  logo section's first word in `front-end.bin`): without `logo` the cook writes
  0 and the client starts on the login; RQ-103 can expose it as a
  `realm-config.json` switch that drops or keeps the key. The screen's music and
  the login's are separate tracks: the login's first entry starts
  `bgm_login.wav` at once, as 1264's first login does (its timer `007ac9d0`
  starts at 0), and its restart period (Q75) counts from there.

The five layouts, and the textures they name, are the 1264 install's
(`installer-1264:UI_US/...`, RQ-085, `specs/KO-FINDINGS.md` §9.2): the login,
select and create layouts and textures are the pinned tree's bytes too; the message
box and loading are 1264's.

- Placement (RQ-106, Q82, `specs/KO-FINDINGS.md` §9.3, binary): each screen's
  `place` (its root: `origin`, `centre` or `bottom`, centred on the bottom
  edge, or `{"bottom": N}`, centred with its bottom edge N pixels above the
  window's, 1298's select bar, RQ-109) and `moves` (a node, then `x`: a number, `centre` or
  `{"middle": c, "ratio": k, "edge": "start"|"end"}`, the node's start or end
  edge at (S >> 1) + c + k·S / the root's extent; and one of `y`: a number or
  `centre`, `bottom`: its bottom edge that far above the window's, or
  `above` [node, gap]: its bottom edge that far above that node's top) are
  1264's placements, which the cook writes as item 12's rules. The recipe's
  `ui_scale` (`native`, the default, or `window`: item 12's flags 1, the
  realm's scaling to the window before RQ-106) is RQ-103's realm-owner switch.
- Login (`UI_US/co_login_us.uif`, centred on the bottom edge): as KO draws it, with
  KO's labels and copyright line (Q61). Login starts spec 02's flow; Cancel exits.
  ID, Password, Option and Registration are unbound: they take no input (Q60, Q61).
  Hidden: the MGAME and Daum logos (1264 hides them at Load and never shows them,
  its login classification being 0, `specs/KO-FINDINGS.md` §9.4; the UIF names
  `ui_us\service_logos.dxt`, which
  neither the pinned tree nor the 1264 install has), `premium` and the three notice groups (KO's news panels,
  empty without KO's server). No `notice` line: the flow's failures show in the
  message box. The server group rests at the window's top-left, (0, 0), where
  1264's login tick slides it (`005c25b0`).
- The copyright line (RQ-108, Q85, `specs/KO-FINDINGS.md` §9.4, binary):
  `Text_Rights` is bound to `login_closed` and moved to 1264's place, centred
  20 px above the bottom edge (`x` `centre`, `bottom` 20: `((W − w) / 2,
  H − h − 20)`, SetVisibleLogInUIs `005c2820`), so it is drawn, as 1264 draws
  it, only while the login bar is not. Each realm state, by the 1264 state it
  stands for:

  | Realm state | 1264's | Bar | Line |
  |---|---|---|---|
  | The login at rest: after the logo, a return from select, a dropped or kicked connection | the login loaded | shown | hidden |
  | A login press held while the realm connection comes up | the press | hidden | shown |
  | A stored session's login, with no press | Init's auto-login (never in 1264) | hidden | shown |
  | Waiting for Discord (the browser step) and its code sent | the press until the answer (Q85) | hidden | shown |
  | A message box during that wait (the address to open) | none: the wait goes on | hidden | shown |
  | Logged in, a message box still over the login | result 1, before the server list | hidden | shown |
  | The realm list | the server list | hidden | shown |
  | A failed login (Discord's or the realm's), its box over the login | a failed answer | shown | hidden |
  | The realm unreachable after a press, its box over the login | the login server unreachable, whose OK quits; the realm's returns to the login, so it takes a failed answer's look | shown | hidden |
- Select (`UI_US/ka_characterselect_us.uif`, its root at the window's top-left):
  1264's CUICharacterSelect::Load (`004448f0`, Q84): left's right edge at
  (W >> 1) − 100 − 26·W/1024 and right at (W >> 1) + 100 + 26·W/1024, each
  10 px above the bottom edge; exit centred 10 px above the bottom edge, back
  centred 10 px above exit; delete hidden (Q53). Exit asks before it leaves, as
  1264's `bt_exit` does (RQ-115, `specs/KO-FINDINGS.md` §9.8, binary:
  ReceiveMessage `00444e60` posts row 1502 untitled, `MB_YESNO`,
  `BEHAVIOR_EXIT`): Yes (KO labels it "O  K") or ENTER leaves, No ("Cancel")
  or ESC closes the box. ESC on the select asks the same (`select.escape`
  `exit`; RQ-116, §9.8, binary: OnKeyPress `004454e0` presses `bt_exit` for
  `DIK_ESCAPE`, as a click), the maintainer's choice (2026-11-02) over the
  realm's ESC there, Back, which stays on `bt_back`.
- Create (`UI_US/Ka_CharacterCreate_us.uif`, centred): Tuarek and Priest fixed
  on, every other race, class, face, hair and stat arrow fixed disabled, the
  bonus points and stat highlights hidden (Q52).
- Loading (`UI_US/co_loading_us.uif`, centred; `Text_Version` at (10, 10)):
  1264's layout when no nation has won the last war (`005f9a30`); the realm has
  no war, so no victor (Q80).
- Message box (`UI_US/el_messagebox_us.uif`, centred): 1264's, for both nations
  (`0050c730`), with 1264's `ui_message_us.dxt` (its frame black, where the
  pinned tree's is grey). An OK box, as KO's `SetBoxStyle(MB_OK)` shows one:
  `Text_Message` holds the message, `btn_ok` is OK; Cancel and the edit
  hidden; `Text_title` holds the message's title, bound to `title` (RQ-102,
  Q81: as `MessageBoxPost` sets it from its caller, empty where the caller
  passes none). `btn_yes` is bound to `yes` and `btn_no` to `no` (RQ-115,
  §9.8): drawn only in the select's exit question, a yes/no box as 1264's
  `SetBoxStyle(MB_YESNO)` (`0050bfb0`) shows one, OK hidden; every other
  message shows them hidden. Each button state image holds
  its own label, and the client draws a node's children only when it draws the
  node (`CN3UIBase::Render`), so one label shows per state.
- Messages (RQ-102, Q81, `specs/KO-FINDINGS.md` §9.2, binary): `messages`
  words the realm's messages that stand for one 1264 shows with a title, with
  that title and wording; every other message shows untitled in the realm's
  words. Each realm message beside the 1264 box it stands for (the 1264
  binary `ko1264-unpacked.exe`; its texts by row of a KO `Data/Texts_us.tbl`):

  | Realm message (its words) | 1264's box (caller; text row; title row) | `messages` |
  |---|---|---|
  | `connect_failed`: the client's connection status | the login server unreachable (`005bdf00` → `005f8ab0`, ReportServerConnectionFailed: row 2905 with "LogIn Server" and the error; title empty, `00674f68`) | none: untitled, the realm's words |
  | `disconnected`: "Disconnected from server", or a kick's "You were disconnected by an operator: …" (spec 02) | the connection closed (`005f8cd0`, ReportServerConnectionClosed: row 1601; title empty). KO has no kick box of its own | none: untitled, the realm's words |
  | `login_blocked`: spec 02's "Your account is blocked until …: …" | the login answer's result 4 (`005bf010`, MsgRecv_AccountLogIn: row 2907, title row 2909) | title and text: the pinned tree's rows 2909 ("Connection failed.") and 2907 ("Your account is currently blocked. Please contact customer support.") |
  | `login_unavailable`: "The realm cannot log you in right now. ENTER to try again." | the login answer's other results (`005bf010`'s last branch: row 2908, title row 2909) | title and text: the pinned tree's rows 2909 and 2908 ("There is an error in the selected server. ") |
  | `login`: the Discord flow's own failures (denied, timed out, its callback, the redirect ports, a refused code, a logout the realm could not end) and the address to open | none: KO has no Discord step | none: untitled, the realm's words |
  | `create_name`: "Enter a name: 1 to 24 letters, digits, _ or -." | an empty name (`0043a340`: code 6 → `0043a820`, ReportErrorCharacterCreate: row 1905, title row 1901) | title and text: the 1264 install's rows 1901 ("Failed creating character") and 1905 ("Please enter your character ID. ") |
  | `create_refused`: the server's "character name invalid/taken or limit reached" | the server's create answer (`0043a820` by its code: 1911 no more characters, 1912 a name in use, 1906 a forbidden letter, and others; title row 1901) | title only: the 1264 install's row 1901; the realm's refusal does not say which of KO's reasons it is, so its words stay |
  | `select_refused`: the server's "character not owned or already online" | the select refused (`004436a0`, CharacterSelectFailed: row 6066; title empty) | none: untitled, the realm's words |
  | `exit_confirm` (RQ-115, §9.8): the client's "Exit the game?" | the select's `bt_exit` (`00444e60` → `005f7f80`: row 1502, title empty, `MB_YESNO`, `BEHAVIOR_EXIT`) | text: the 1264 install's row 1502 ("Are you sure you want to exit? "), untitled |

  The login rows come from the pinned tree's `Data/Texts_us.tbl` (1298's),
  not the 1264 install's: 1264 asks for rows 2907–2909 there (pushes at
  `005bf30c`, `005bf31b`, `005bf7a2`), and the 1264 install's table holds other
  texts at those rows (a stat's description at 2909, "Karus" at 2907), while
  1298's binary asks for the same rows (`5f7e6f`, `5f7e82`) and its table
  holds the login wording, the source's (`text_resources.h`). The create rows
  are the 1264 install's (1298's are the same text). KO's text keeps its
  trailing spaces. The OpenKO source's "Failed to connect to login server"
  title is its `_DEBUG` build's (`GameProcLogIn_1098.cpp` `Init`); the 1264
  binary has no such string and its release path posts the failure untitled.
- Intro: `Intro/Intro.N3Chr` clip 0 with its axe plug, `Intro/0-2.N3Light` (2 is
  off), `Intro/Moon.dxt` at (100, 50) × 1.3, KO's fixed camera. The clip (frames
  0–650 at 30 a second, 21.667 s) starts at its first frame on each entry to the
  login and keeps `bgm_login.wav`'s time (section 9, RQ-104): the orc's roars
  are in the track.
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
  hall from other files, loops a clip on the character in front without
  the pointer and turns through recorded paths (`specs/KO-FINDINGS.md` §8,
  §8.4, Q71; "1298" above). The recipe's `turn` is `rotate`.
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
  Back on the login from select (RQ-096, Q75, KO's): the login Init creates
  sound 35 again but does not play it; only the tick's timer, which no Init
  resets and which runs only while the login shows, does, when it next passes
  21.66 s, so a return is silent for the rest of that period. The realm
  does not (RQ-105, Q75 (a), maintainer): a return starts `bgm_login.wav` at
  once from its first sample and its period counts from there; KO's carried
  clock is the off-by-default `carry_music_clock` (section 9).
  KO 1264 keeps the same timer (`specs/KO-FINDINGS.md` §9.1, binary: the tick
  `005be500` and its timer `007ac9d0`). KO 1298 plays `Snd/Intro_Sound.mp3`
  instead (44.1 kHz stereo, 4,096 frames, 107 s; the file's cut-short 4,097th frame is dropped), looping on
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
  is empty; RQ-085: `co_loading_us.uif` and `el_messagebox_us.uif` name no
  sound file either; RQ-101: nor does `co_usa_logo_us.uif`, whose only strings
are its group names and its texture's). So do 1097's Karus layouts (`co_login.uif`,
  `Ka_CharacterSelect.uif`, `Ka_CharacterCreate.uif`, `Ka_MessageBox.uif`,
  `Co_Loading.uif`, `ka_loading.uif`). So `front-end.bin` carries no UI sounds.
- Option.ini (`client/render/options.h`): `[Sound] Effect=0` silences the
  music and the turn sound, as it does every KO 1298 sound object (`0044d240`,
  `006453b0`); `[Sound] Bgm` is 1298's zone-music switch only (`00640b10`) and
  does not touch it. 1097's switch is `[Sound] Enable` (`0054ec5e`), which
  does the same; the realm reads 1298's key (Q70).
