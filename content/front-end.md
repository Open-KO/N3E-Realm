# Front end (N3FE, engine 42; version 32 engine 45)

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
presses on the select (version 15, RQ-116), its `none`, 1298's (version 16,
RQ-119), where the select's Back lands (version 17, RQ-112), whether the
select arrow at the end of the row is hidden (version 18, RQ-113),
whether create is a screen of its own or draws over the select hall, with the
new character's turn at each slot (version 19, RQ-125), create's slide,
its panels sliding in each time it opens (version 20, RQ-126), create's
race and class buttons, which a create that binds them waits for, with two
messages (version 21, RQ-130), create's nodes drawn only until its race is
chosen (version 22, RQ-133), create's nodes drawn until a class is clicked,
again from each open and each race click that builds (version 23, RQ-145), a
create model per race the package's create rules name (version 24, RQ-158), and
create's race and class buttons bound to KO's codes, each class button with its
stand-in image and the stat labels its click marks (version 25, RQ-172), and
create's stat arrows, their values and the points left, with a message for
points left at Create (version 26, RQ-173), and create's face and hair
arrows, each create model's face and hair parts carried by number in place of
its face 0 and hair 0 (version 27, RQ-174), create's description text
(version 28, RQ-175), and each create model's specialties in their create
dress, the chosen create table's parts and hand plugs (version 29, RQ-176),
and the select characters per race and class, as KO's AddChr chooses their
joint, animation and plugs, and each specialty's class name for the select's
info (version 31, RQ-005).
Version 30 (RQ-165; "Influence tables", below) was version 29 whose model
records and parts may carry D-176's influence table; since RQ-005 that is
version 32, version 31 with the tables. The cook writes it only for a file
that has one, at engine 45.
`tools/assetc/ko_front_end.py` cooks it from the choice's KO trees with the
recipe of the front end the realm chose ("Choosing the client", below; for
Moradon's default, 1097, `games/moradon/front-end.json`); the client's
`load_front_end` (`client/assets/assets.cpp`) reads it whole when the window
opens. Both release loads hash it in 1 MiB blocks without holding it, and the server
then reads only its first 12 bytes (magic, version and slot count) for the slot
count (RQ-183). A package with it is engine 42, so wire 30 (as engines 38–41);
with a file of the tables version (32; 30 before RQ-005), engine 45 (RQ-165). Its
bound is 256 MiB (RQ-183: `ko_front_end.MAX_FILE` and `FRONT_END_FILE` in the cook,
`kFrontEndFile` in the client, `MAX_FRONT_END_ASSET` in the server; a file a byte
past it is refused by each), since it holds
the character models and the UI art (Moradon's 1097 choice: 62,338,435 bytes with
three create models, RQ-158, its race and class buttons, RQ-172, its stat
arrows, RQ-173, its create models' four faces and three hairs, RQ-174, its
description text, RQ-175, its create dress, RQ-176, the Arch Tuarek's
create model, RQ-169, and the Tuarek rogue's select character and the class
names, RQ-005; the 1298 recipe's 64,447,563).

The bound against what is still to come (RQ-182; local-asset, the pinned trees:
both recipes cooked with each section's bytes counted, KO's textures stored as
RGBA8 and each model's atlas as N3S1's RGB or N3SM's RGBA):

| Bytes (MB) | 1097 choice | 1298 recipe |
|---|---|---|
| Texture table (item 2) | 17.2: the UI art 6.3 (the logo's 1.0 with it), the hall's 5.2, the intro's 2.1, the font atlases 2.8, the dress plugs' 0.8 | 34.8: the select zone's 63 textures 20.6, the UI art 8.4, the intro's 2.1, the font atlases 2.4, the dress plugs' 1.3 |
| Intro scene (item 6) | 16.4, its model's 2048 × 1804 RGBA atlas 14.8 (40% of it empty) | 16.4, the same |
| Select scene (item 7, its meshes and model) | 1.4 | 3.0 |
| Create models (item 8) | 4.9 | 5.9 |
| Music (item 9) | 18.5 (1097's PCM) | 1.7 (MPEG) |
| Total | 58.46 | 61.84 |

A create model's atlases (its own and its parts') are 64–79% of its bytes. With
every race's create model (races 1, 11, 12 and 13 added, each in its create
dress; RQ-165 found that dress leaves no vertex past four influences, so none
needs an influence table) the 1097 choice is 66,298,836 bytes, 0.8 MB under the bound
(1264's table dresses each race in one set, its own parts), and the 1298 recipe
76,259,455, 9.2 MB over (its table dresses the El Morad male and female in four
sets each, 12 dress parts: 4.7 and 4.2 MB a race). RQ-006 then adds El Morad's
select hall (the 1097 choice's `el_chairs`, about 5.1 MB as `ka_chairs` is; the
1298 recipe's zone 10000, about 22 MB as `karus_intro` is, not measured: four of
its object files are missing from the pinned tree), its select character and the
nation select's art: about 75–77 MB and 102–108 MB, before any per-race select
model RQ-005 carries here. Compressed with zstd -3 the two files are 26.0 and
16.7 MB today. RQ-182's choice, made by RQ-183: raise the bound from 64 MiB to
256 MiB rather than split the file or compress its textures, since no byte of
the file changes, the engine already reads files of that order whole
(`render-detail.bin` 128 MiB, `world-textures.bin` 384 MiB), a bound on the
decoded size would remain under any compression, and the atlases that make up
most of the models would not keep KO's DXT blocks.

Integers are little-endian u32, reals f32; strings are a u32 length and that many
bytes. Engine space is KO's with z negated (KO is left-handed).

## Layout

1. `"N3FE"`, version 31 or (RQ-165) 32, character slots (1–3; the server's
   character limit), canvas width 1024 and height 768.
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
     flags (1 fixed on, 2 fixed disabled, 4 progress foreground, 16 and 32 a
     class button's stat label, drawn unless or only while the marking class
     names it: version 25, create's, item 14 and "Actions"; version 22's 8
     and version 23's 16, drawn until the race or a class, are gone), state mask
     (1–15: the button states normal, down, on, disabled it draws in);
   - image: texture, uv u0 v0 u1 v1 in [0, 1];
   - text: text (≤1024 ASCII bytes), font, colour (ARGB), KO string style;
     an edit is its string child's font and colour (its other children are
     images, as the login's untextured ones);
   - edit: font, colour, style (`0x10000000` password); list: font, colour.
   A node draws only when its parent does. A button's state images carry one
   mask bit each; its other children draw in every state.
5. Strings, each ≤1024 ASCII bytes, in order: `select_info`, `select_hint`,
   `class_name`, `loading_info`, `version` (version 28 drops `class_desc`, which
   followed `class_name`: its text is item 16's). The client substitutes only
   `{level}`, `{class}`, `{name}` and `{version}`.
6. The intro scene: camera, lights, global ambient (3 reals), the model, its
   plugs (count ≤4), then the backdrop: a texture index and a rect in 1024×768
   units that the client scales by the window's width and height separately
   (`CGameProcLogIn_1098::Render`'s moon).
7. The select scene: camera, lights, global ambient, the slots (count equal to
   the character slots), the spot's growth rate (version 4: theta per second,
   above 0 and at most 100), the front-clip mode (version 6: 0 hover, 1 loop;
   below), the select's ESC (version 15: 0 back, 1 exit; version 16: 2 none; below), where the select's Back lands (version 17: 0 login, 1 realms; below), the end-of-row arrow (version 18: 0 hide, 1 draw; below), where create draws (version 19: 0 screen, 1 hall, then with 1 each slot's create yaw, a real; below), the turn mode (version 7: 0 rotate, 1 path; below) and a path count
   (0 in the rotate mode, 1–8 in the path mode) and the paths, the hall (part
   count ≤64, each a mesh; version 7: it may be 0), the zone (version 8: a
   mesh count, 0–256, 0 when the hall has parts, each a zone mesh; below), the
   fog (version 8; below), the model (version 4: three
   clips, by role the front, start and rest clips), its plugs.
8. The create models (version 24, RQ-158): a count (1–32), then per race its
   race code (1–65535, each once) and its model and plugs (version 2):
   `CGameProcCharacterCreate`'s player (`InitChr`: the race's `UPC_DefaultLooks`
   joint, animation and default parts, an empty part name setting no part as
   `SetChr` sets them; source `GameProcCharacterCreate.cpp`,
   `content/character-create.md` "The realm's races") with one clip,
   `ANI_BREATH` (0), and no plugs of its own (version 29's dresses carry the
   hand plugs). Version 27
   (RQ-174): the model holds every part but the face and the hair, and after
   its plugs come its faces (a count, 0–32) and its hairs (a count, 0–32),
   each part a byte length and an N3S1 or N3SM scene (in the tables version, 32: or N3SI or
   N3SJ) of that part alone with no tracks, its nodes, joints and instance scale the model's, so the
   client skins it with the model's pose. Part i is the looks row's face or
   hair file with i as two digits before the extension (`InitFace` and
   `InitHair`'s `"%02d"`, source `PlayerMySelf.cpp`); the cook writes
   `create.bin`'s faces and hairs of them (Moradon's 4 and 3, KO's 0..3 and
   0..2), none for a row whose part is empty (the Wrinkle Tuarek's hair,
   which `InitHair` sets to none), and without create rules the face and hair
   0 alone. The new character draws the face and hair the create holds
   ("Actions"), none past the parts (before version 27 the model carried
   face 0 and hair 0). The races
   are the package's `models.create` (`games/<game>/character-create.json`):
   the select character's race first (`select.character.race`, which must be
   one of them), the model a create without race buttons draws, then the
   others in the rules' `races` order; a create with race buttons (version 25,
   item 14) draws the chosen race's (RQ-172), none for a race without one. A
   package with no `character-create.json` beside the recipe carries the select
   race's alone; a malformed one stops the cook (`ko_create.rules`). Before
   version 24 the file held one create model, the select race's. The select
   model's seated clips are for the hall's thrones; it is not the create model
   (KO's select draws `ChrSelect/` joints and clips, its create the looks row's
   `Chr/` ones), so the two are separate records.
   Version 29 (RQ-176; `content/character-create.md` "The create dress (RQ-176)",
   `specs/KO-FINDINGS.md` §10.3, §10.7): after its hairs each model carries its
   dress parts (a count, 0–64, each a part as a face is) and its dresses (a
   count, 0–16), each a specialty (1–65535, once per model), a body flag (0 or
   1), a part count (0–10; 0 with the body) and that many dress-part indices
   (each once), and a plug count (0–2) and per plug its hand (0 right, 1 left,
   each once), a joint of the model and a mesh in that joint's space (as a
   plug's, item 6). Every dress part is some dress's. KO's build dresses the
   model in its row's items (1298 `005fd120`, 1264 `00439970`): with the
   package's create choice (`ko_create.plan`, the realm's `create.table`,
   Q106) the cook writes a dress for each of the race's specialties from
   `ko_create.dress` (RQ-159): its part slots in order but the face's and the
   hair's (a helmet in the hair's slot is refused, KO's order of the helmet
   and `InitHair` being unread), each a dress part, none for the robe's bare
   lower, or the looks row's part where the dress leaves the slot. RQ-181:
   the cook refuses a dress the build would not draw or the loader would
   refuse: a part outside slots 0–9 or a plug outside hands 0 and 1 (the
   build sets part slots 0–9 and attaches two hand plugs, 1298 `005fd120`,
   though a create table may name 16 of each), one file drawn in two slots,
   and a path (a worn part, its texture or skin) that parts of two inputs
   name, each input's files being read by path (RQ-186: a worn file is a
   dress part where its own dress names it and a looks part where the looks
   row does, by its dress, so one spelling that is both, an unprefixed dress
   file in one dress and a looks part in another, is refused unless the
   model's tree is input 0); the parts
   the most specialties wear (the first's on a tie) are the model's own
   parts (body 1), and the others' follow as dress parts, each once, drawn in
   place of the model's own (body 0). A plug's joint is the looks row's
   right hand (column 18), left hand (column 19) or, for a left-hand item of
   class 60, shield (column 20; 1298 `00467b30`'s `+0x108`, `+0x10c`,
   `+0x110`), scaled as `PlugSet` scales it (its scale y × the model's
   `Height()`, the largest joint y, / 1.8). RQ-186: the cook refuses a plug
   whose joint is not one of the skeleton's, negative (KO's `CN3Chr::Render`
   skips that plug, source `N3Chr.cpp`) or at or past its joint count (KO
   reads past its joint matrices); the model's joints are the skeleton's one
   for one (a skeleton of at most 64 joints skins with them all), which the
   cook checks, so the loader's bound is the skeleton's. Without a create choice, or for a
   table without item columns, the model holds the looks parts and carries no
   dresses (KO's `SetChr` without a row). The new character wears the dress
   of the specialty whose row the last build took ("Actions"), none for a
   specialty without one.
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
11. The messages (version 10, RQ-102, Q81): a count (0–14, at most one per
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
   `btn_exit`, 1264's `bt_exit`; named, it makes the select ask, "Actions" below),
   and (version 21, RQ-130) 11 `create_no_race` (create before its race is
   clicked: 1298's `005fffd0` code 7) and 12 `create_no_class` (before its
   class is: code 9), and (version 26, RQ-173) 13 `create_points_left` (stat
   points still to spend: code 10). The client shows a message in the message box
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
13. Create's slide (version 20, RQ-126; `client/render/front_slide.h`;
   `specs/KO-FINDINGS.md` §9.15, binary): a node count (≤8; 0: none), then
   with nodes the rate (real, above 0, at most 100000) and the floor (real,
   1/16 to 1024: at least the real step just below 10⁶, so d always grows
   to the bound below), and each node: a node of the create layout (each
   once), its axis (0 x, 1 y), its start rule (a kind, 1 linear or 2 half, and
   a and c as item 12's) and two reals num and den (above 0, at most 16384).
   Each time create opens a distance d starts at 0 (1298's SetVisible
   `00606650`); each frame, before the frame draws, d grows by max(t · rate ·
   (w − d) / w, floor), t the frame's seconds (none for a frame of no time) and
   w the first node's (the lead's) extent on its axis, and is kept as a real
   (1298's Tick `00606450`: rate 1300, floor 2, w `Group_race`'s width). Each
   node, its subtree with it, then stands on its axis at its start rule's
   coordinate (on the placement's S: the window's, or the canvas's when
   scaled) moved toward its rest, where item 12's moves put it, by
   trunc(num · d / den), never past it; its other coordinate is its rest's.
   On the frame the lead reaches its rest the slide ends, every node staying
   where that frame put it (1298 clears its flag on Group_race's arrival),
   so a node whose travel the lead's outruns ends short of its rest; a d
   past 10⁶ ends it with every node at rest. Hit tests take the nodes where
   they draw.
14. Create's race and class buttons (version 25, RQ-172;
   `client/render/create_choice.h`; `specs/KO-FINDINGS.md` §9.15, §9.16,
   binary): a race button count (≤32), each its node (a create node bound to
   `create_race`, each once), its KO race code (1–65535, each once) and its
   default specialty (1–65535: the class 1298's build `005fd120` takes for the
   race's stat row while none is chosen, 1→101, 2→102, 3→103, 4→104, 11→201,
   12→202, 13→204); then a class button count (≤16), each its node (a create
   node bound to `create_class`, each once), a specialty count (1–16) and the
   specialty codes it stands for (1–65535, none in two buttons: one per nation,
   as 1298's `006062d0` and 1264's `0043ee10` map their four buttons to 101–104
   and 201–204), its stand-in image (an image node of create no other class
   names and no race or class button or label is, or `0xffffffff` for none)
   and a label count (≤8) and its stat labels (create nodes each carrying flag
   16 or flag 32, one of the two for the whole create, none twice in one
   button). Every node bound to `create_race` or `create_class` is one
   button's, every node with flag 16 or 32 some class's label, and at most one
   race and one class button is fixed on (chosen at each open). The client's
   use is "Actions" below.
15. Create's stat arrows (version 26, RQ-173; `client/render/create_choice.h`;
   `specs/KO-FINDINGS.md` §10.4, binary): a stat count (≤8; the cook
   writes the package's create rules' count), each its value text (a create text
   node bound to `create_stat`), its left arrow (a create button bound to
   `create_stat_down`) and its right arrow (`create_stat_up`), in the rules'
   stat order and each node once; then the points text (a create text node
   bound to `create_points`; `0xffffffff` without stats) and the row (0 the
   race's, as 1264's, 1 the race's and class's, as 1298's; 0 without stats).
   Every node bound to those four actions is one stat's or the points text.
   The client's use is "Actions" below.
16. Create's description text (version 28, RQ-175; `client/render/create_choice.h`;
   `specs/KO-FINDINGS.md` §10.6, binary): the rest (0 none, 1 keep, as 1264's,
   2 chosen, as 1298's), the colour (ARGB), the open text (≤1024 ASCII bytes;
   empty with rest 0 or 2) and a tip count (≤32), each tip a create node (an
   area for group 0, a button for groups 1 and 2), its group (0 the stat areas,
   1 the class buttons, 2 the race buttons, never decreasing: KO's loop order)
   and its text (≤1024 ASCII bytes), each node once. Rest 0 is no descriptions:
   colour 0, no open text and no tips. Otherwise create binds `class_desc`.
   The client's use is "Actions" below.

17. The select characters and the class names (version 31, RQ-005;
   `specs/KO-FINDINGS.md` §8.1, §8.3, §8.5; `content/character-create.md`
   "The select hall (RQ-005)"): a count (0–32) of select characters, each a
   race (1–65535), a specialty count (1–16) and the specialties (each
   1–65535; a race and specialty pair at most once in the file), then a model
   record and its plugs as item 7's (three clips by role, each clip's blend
   time; the plugs a count ≤4, each a joint and a mesh); then a count (0–64)
   of class names, each a specialty (1–65535, once) and its text (≤1024 ASCII
   bytes). KO's AddChr chooses a select character's joint, animation and
   plugs by its race and class (source `GameProcCharacterSelect.cpp`'s
   switch; 1097 `0043ba10`, 1298 `005fb4f0`), dressing it in the race's looks
   parts. The cook writes the recipe's `select.characters` (each a race, its
   specialties, its joint, animation and plugs, and `clips` the select
   character's unless named), each cooked as the select model is (the race's
   `UPC_DefaultLooks` parts with face 0 and hair 0, the start clip's blend the
   select's own), and the recipe's `select.class_names` (a text table and
   `{specialty: row}`, each row read as a message's). With create rules it
   refuses a `content` race's specialty that no select character draws,
   unless the race is the select character's (item 7's), so no character the
   realm creates stands in the hall as another race. The client draws each
   listed character with the select character naming its race and specialty,
   or with item 7's model when none does ("Actions"; KO's AddChr draws no
   character for a race and class outside its switch, Q118), each slot
   playing its own model's clips; the select's `{class}` and `char_class`
   show the character's specialty's class name, or the `class_name` string
   for a specialty without one.

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
- Where the select's Back lands (version 17, RQ-112; `client/render/front_end.h`
  `back_lands`, `client/render/viewer.cpp`). Either way Back drops the realm
  connection and returns to the login screen, which connects again; with a
  stored session the client logs in with it at once, as at start, and its
  answer opens the realm list, so the player is back on the realm list after one
  round trip. Without one (none saved, or refused) the login waits for a Discord
  login. 0, login (the realm's): the login bar shows while the client connects,
  and hides from the stored session's login to its answer, as for any login
  (below). 1, realms (1298's, `specs/KO-FINDINGS.md` §9.12, binary: its Back,
  `00607160`, sets the login procedure's byte `+0x21`, whose Init, `005f68e0`,
  connects, asks for the server list and hides the bar; 1264's the same, `+0x35`,
  `005bd9b0`): the bar hidden from the click, through the connection, to the
  stored session's answer and the realm list; it shows again when there is no
  stored session to log in with, and a connection that fails shows the
  `connect_failed` message over it, as after a login press. RQ-123: a
  layout's `login_closed` node is hidden too, from the click through the
  stored session's login and on the realm list after it, until the list is
  left for the select (1264's Back, its store at `00445145`, reaches its server
  list through an Init, `005bd9b0`, that hides `Group_LogIn` alone and never
  calls SetVisibleLogInUIs, `005c2820`, the only code that shows the line);
  without a stored session, or once the flow leaves that login otherwise (a
  refusal, a logout), the hold ends and a later login press shows the line as
  for any login (`client/render/front_login.h` `BackHold`). The recipe names
  it (`select.back`: `login`, the default, or `realms`).
- The select arrow at the end of the row (version 18, RQ-113;
  `client/render/select_bar.h` `select_arrow_shows`). The row runs left to right
  1, 0, 2 (the slots there are). 0, hide (the realm's): with the row's left end
  in focus the node bound to `select_prev` is hidden, with its right end the one
  bound to `select_next` (with one slot, both). 1, draw (KO's,
  `specs/KO-FINDINGS.md` §9.6, §9.13, binary: no code in 1298, 1264 or 1097 hides
  an arrow; their arrow fields are read only to place, compare and click them):
  both draw at every slot. Either way a press at the end of the row does nothing
  (DoJobLeft, DojobRight). The recipe names it (`select.arrows`: `hide`, the
  default, or `draw`).
- Where create draws (version 19, RQ-125; `specs/KO-FINDINGS.md` §9.15,
  binary). 0, screen (the realm's): create is a screen of its own, drawn on the
  black clear, the new character in the node bound to `char_view`. 1, hall
  (1298's): create is a window of the select (1298's `+0x388`, which
  `005fab40` loads), drawn over the hall, which draws behind it as on the
  select (Render `005fb1c0` draws the hall in every state), the zone's blend
  meshes after it; its layout binds no `char_view`. Then each slot's create
  yaw (radians about +y, engine space as the slot's yaw, at most a turn either
  way): once the camera is on the slot in focus (1298's state 7), the new
  character, the create model breathing, stands at that slot's position turned
  by it, under the select's lights and the slot's spot (`005fd120` places
  1298's at the camera's slot); a create that waits for its race (version 21,
  "Actions") draws it only once the race is clicked, at the slot the camera
  was on for that click. `select_create` opens create with the click,
  and from an occupied slot in the path mode the camera flies to the empty
  slot behind it (`005ff920` shows `+0x388` before the camera moves; neither
  ENTER nor ESC skips the flight; ENTER is create's, ESC its Cancel); with no
  such path (or in the rotate mode) the camera is put on the slot at once.
  `back` and ESC on create return to the select at rest on that slot, a
  flight still under way put on its last frame (1298's Cancel, `005ffb90`,
  sets state 5 and shows the bar at once; its camera flies on, the select at
  rest on the slot the flight left: §9.15, RQ-127, not played). The recipe names it
  (`select.create`: `screen`, the default, or `hall`) and, with `hall`, each
  slot's `create_yaw` in degrees (−360 to 360); a slot's `create_yaw` with
  `screen` is refused.
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
  up to 2048 a side; in the tables version, 32: or N3SI or N3SJ, "Influence tables" below), then a count of further clips and each clip's byte length
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

The loader refuses a dress part count above 64, a dress count above 16, a
dress specialty outside 1–65535 or named twice on a model, a body flag above
1, dress parts with the body, more than 10, outside the dress parts or named
twice in a dress, a dress part no dress wears, a dress part that is not its
model's skeleton (as a face), more than two plugs, a hand above 1 or twice, a
plug joint outside the model's joints (version 29; every version before 31 is
refused since RQ-005), a create model count outside 1–32 or a create race
outside 1–65535 or named twice (version 24), a face or hair count above 32, a part that is
not N3S1 or N3SM (or, in version 32, N3SI or N3SJ), has tracks, or whose nodes, joints or instance scale are
not its model's (version 27), an unknown action, a screen missing one of its required
actions (login: `login`, `exit`, `login_group`, `realm_group`, `realm_list`,
`realm_connect`; select: `select_prev`, `select_next`, `back`, `exit` and an
info text, `char_info` or (version 13) any of `char_name`, `char_level` and
`char_class`; create: `create_confirm`, `back`, `name_field` and (version 19)
`char_view` unless create draws over the hall, where it is refused;
loading: `progress`; message: `message`, `ok`), an action bound twice in a
screen (but `create_race` and `create_class`, version 25, and
`create_stat_down`, `create_stat_up` and `create_stat`, version 26), an unknown turn mode, paths in the rotate mode, a path outside the slots
or from a slot to itself, an entry path not to slot 0, a from and to pair twice,
the path mode without its entry path or a way between neighbours, a hall with
a zone, a zone mesh's flags other than above, fog values outside their bounds
(or not all 0 when off), a message outside the set or named twice, a replace
flag other than 0 or 1 or a text that does not replace, a node bound to
`login_closed` on a screen other than the login (version 12), a node bound to
`select_start`, `select_create`, `select_delete`, `char_name`, `char_level` or
`char_class` on a screen other than the select (version 13), a node bound to
`yes` or `no` on a screen other than the message box, or `exit_confirm` named
without nodes bound to both on it (version 14), a node bound to `create_race`
or `create_class` on a screen other than create, or one that is not a button
or is fixed disabled (version 21; fixed on is a choice at each open since
version 25), a node flag above 63 or with flag 8 (version 25), flags 16 and 32
together, on a screen other than create or on the logo screen, item 14's
bounds and references above (version 25), a node bound to `create_stat_down`,
`create_stat_up`, `create_stat` or `create_points` on a screen other than
create, an arrow that is not a button or is fixed on or disabled, a value or
points text that is not a text node, item 15's bounds and references above
(version 26), a node bound to `create_face_down`, `create_face_up`,
`create_hair_down` or `create_hair_up` on a screen other than create, or one
that is not a button or is fixed on or disabled (version 27), a description
rest above 2, a tip on a node outside create, of a group above 2 or below the
last tip's, not an area for group 0 or a button for groups 1 and 2, or named
twice, more than 32 tips, a rest 0 with a colour, open text or tips, and a rest
1 or 2 without a create node bound to `class_desc` or a rest 2 with open text
(version 28), a select ESC other than 0, 1 or
2 (version 15; 2 since version 16), a select Back other than 0 or 1 (version
17), placement flags
other than 0 or 1, a move of a node outside its layout or of a logo screen the
file does not have, a rule of another kind or outside its bounds, a keep rule
with a or c not 0, moves that do not leave the canvas rects where the file puts
them, a slide (version 20) of a node outside the create layout or named twice,
an axis other than 0 or 1, a keep start rule, a lead of no extent on its axis
or a step or scale outside its bounds, a version other than 31 or 32, version
32 below engine 45, a model record or part of N3SI or N3SJ in version 31, an
influence table out of order, of a vertex or joint outside the scene, of a
weight not above 0 or of a vertex whose weights do not sum to 1 (RQ-165), a
select character (version 31) of race 0 or above 65535, with no specialty or
more than 16, a specialty 0, above 65535 or named twice for one race in the
file, a model without three clips or a plug off its joints, more than 32 select
characters, a class name for specialty 0, above 65535 or named twice, more
than 64 class names or a text that is not printable ASCII, and every
reference, count and bound above, truncation or trailing bytes.

### Influence tables (version 32, engine 45; RQ-165, RQ-005)

KO draws the front end's characters with the same class as the world's: the
login's orc (`m_pChr`) and the select hall's characters (`m_pChrs`) are
`CN3Chr`s, and create builds its new character in the player's `m_ChrInv`, a
`CN3Chr` as the world player's `m_Chr` is (source `GameProcLogIn_1098.h`,
`GameProcCharacterSelect.h`, `GameProcCharacterCreate.cpp`, `PlayerMySelf.h`,
`PlayerBase.h`). Its skin load reads any number of
joint influences a vertex and its CPU skinning `00419f00` sums every one with its
weight as read (binary, 1298 `KnightOnLine.exe`; D-176's evidence,
`content/npc.md` "Influence tables"). The Arch Tuarek's looks lower part
(`upc_ka_at_lower.n3cskins`) has 49 drawn vertices with five and the El Morad
male's (`upc_el_rm_lower.n3cskins`) 57 (local-asset, `tests/ko_player_races.py`), so a front end that draws
either in its looks parts needs them, as the player path does since RQ-163.

- A model record's scene (the intro's, the select's, a create model's) and a
  create part's (face, hair, dress part) may be `N3SI` (from `N3S1`) or `N3SJ`
  (from `N3SM`): the same scene with D-176's influence table between the
  vertices and the indices (`tools/assetc/gltf.py`; u32 count of vertices with
  further influences, then per vertex, in strictly increasing order, u32 vertex,
  u32 n (1–60) and n pairs of u32 skin joint and f32 weight above 0; a vertex's
  four slots and further weights sum to 1). `ko_front_end.model` cooks with
  `gltf.cook(..., materials=True)`, which writes the table for a vertex whose
  further sets carry weight; each record or part has its own magic, so an N3SI
  model may have N3S1 faces.
- The file is the tables version, 32, when any record or part has a table,
  version 31 otherwise (byte for byte as without RQ-165's tables; RQ-165 made
  them 30 and 29, RQ-005 31 and 32). The cook's report gives the
  version and how many scenes have tables, and each create model's report how
  many of its own do (`tables`).
- A package with a version 32 file is engine 45 (wire 30; `main.py` reads the
  file's header, `FRONT_END_INFLUENCES_ENGINE`, against
  `FRONT_END_TABLES_VERSION`); one with a version 31 file stays 42 (or the 43
  and 44 of its player clips and render detail). The client loads version 32
  only at engine 45 and reads a table only in version 32, checking it
  as a looks model's; `Scene::skin` adds each further influence after the four
  slots, in order, so the front end draws it as the world does. The server
  reads only the header and takes version 32 only at engine 45.

Moradon's front end needs none: its create races 2, 3 and 4 have no such
vertex, and on both create tables each specialty's create dress replaces the
looks lower part, so the dressed create models of the Arch Tuarek (1, shipped
since RQ-169) and of the El Morad male have none either (local-asset: the 1097
choice's records 2,342,872 and 1,644,968 bytes with their race codes, the 1298
recipe's 2,341,276 and 4,678,215; the Arch Tuarek's N3SM on both tables, the
El Morad male's N3S1 on 1264's and N3SM on 1298's, no influence table in any
model or part; `tests/ko_player_races.py` asserts it for every shipped race).
Moradon's `front-end.bin` stays version 31 (no tables). A create model in its looks lower part (a create table
without item columns, or a dress that leaves that slot) does: undressed, the
Arch Tuarek's and the El Morad male's are N3SI, 2,780,584 and 1,341,684 bytes
with their race codes, four faces and three hairs (their parts N3S1).

## Actions

The closed set, by index: none, `login`, `exit`, `login_group`, `realm_group`,
`realm_list`, `realm_connect`, `notice`, `select_prev`, `select_next`, `back`,
`char_info`, `create_confirm`, `name_field`, `char_view`, `class_desc`,
`progress`, `version`, `info`, `message`, `ok`, `title` (version 10), `login_closed`
(version 12), `select_start`, `select_create`, `select_delete`, `char_name`,
`char_level`, `char_class` (version 13), `yes`, `no` (version 14), `create_race`,
`create_class` (version 21), `create_stat_down`, `create_stat_up`,
`create_stat`, `create_points` (version 26), `create_face_down`,
`create_face_up`, `create_hair_down`, `create_hair_up` (version 27). A group bound to `login_group` or
`realm_group` is shown in its state only; `realm_list` lists the realm from
`realm.json`; `notice`, `char_info`, `class_desc` (version 28: create's
description text, item 16, below; without one, the layout's own text),
`version`, `info`, `message` and `title` (the message's title, item 11) are
texts the client fills; `name_field` is the name entry (RQ-004: printable ASCII up to the package's longest name, `create.bin`); `char_view`
is where create draws the character.

1298's select bar (version 13, RQ-109, `specs/KO-FINDINGS.md` §9.6,
`client/render/select_bar.h`), select screen only: `select_start` is the
start ENTER and the centre click make (the character in focus, or create for
an empty slot; at rest only); `select_create` opens create for the slot in
focus when it is empty, else for the first empty slot, else shows the message
`create_full`. For the first empty slot the camera goes there: in the path
mode (RQ-114) by the package's path from the slot in focus, when it has one,
the select UI hidden and ENTER and ESC not skipping it (1298's state 6), and
create opens on the tick after the path's last frame; otherwise (the rotate
mode, or no such path) it is put on the slot and create opens at once. A
create over the hall (version 19, below) opens with the click instead, the
camera flying behind it; `select_delete` shows the message
`delete_disabled` for a character in focus at rest, and does nothing else. The
texts `char_name`, `char_level` and `char_class` are the character in focus's
name, level (decimal) and class name (version 31, RQ-005: its specialty's,
item 17, else the `class_name` string; before, the string) while the hall is at rest
(the loop front-clip mode: always at rest; hover: while the pointer is on the
character, as `char_info`), and empty for an empty slot or otherwise.

Create's race and class (version 21, RQ-130; version 25, RQ-172;
`specs/KO-FINDINGS.md` §9.15, §9.16; `client/render/create_choice.h`), create
screen only, on item 14's buttons, each a button that is not fixed disabled:
each race button stands for its KO race code and each class button for its
specialty codes. A create with race buttons waits for its race and one with
class buttons for its class (1298's in-select create), unless one of them is
fixed on, which is then chosen at each open (the 1097 choice's Tuarek and
priest, Q52, Q89 (b); 1264's create itself opens with none, `00439550`, which
the 1097 choice does not follow). Each time create opens, only that choice
stands (1298's Init `005fab40` and Cancel `005ffb90` set the race and class to
−1; a create the realm accepts returns to the select, so the next open starts
again). A click on a race button chooses its race and unchooses the class
(ReceiveMessage `00604f90` sets the class to −1 on every race click; 1264's
`0043ec90` too); a click on a class button chooses its class, with or without a
race. A chosen button draws in its down state (its own down image), under the
pointer too (`006060f0` and `006062d0` set `UI_STATE_BUTTON_DOWN`; 1264's
`0043ec90` and `0043ee10`); a fixed-on choice button draws as any other, down
only while chosen. The new character, over the hall or in `char_view`, draws
only once a race is chosen, as the chosen race's create model (item 8; a race
with none draws nothing, as `005fd120` builds nothing without a looks row);
over the hall it stands at the slot the camera was on at the click that chose
the race, or at a later class click that chose the class (`005fd120`, which
builds it on a click that changes either value, puts it by the camera's slot
`+0x38c`: a race clicked while the camera flies stands at the slot the flight
left). Until a class is chosen the build takes the race button's default
specialty for the race's stat row (`005fd120`), which the stat values show
(RQ-173, below). Each build also dresses the new character (version 29,
RQ-176; item 8): it wears the dress of the specialty whose row that build
took, the chosen class's or the race's default, until the next build (a
second click on the chosen race unchooses the class and builds nothing, so
the dress stays; 1264's class click builds nothing, its row being the
race's). A create without race buttons dresses its model as the fixed
choice's specialty when that is the model's race (Q100).

The class column (version 25, RQ-172, binary): before a race is chosen every
class button draws over its stand-in image (1298's reset `006066b0` by
`00605950`); once one is chosen, a class button draws only while the race can
take one of its specialties (the package's `create.bin` races: a race it does
not offer takes none; without rules, every one) and its image only while the
race cannot, so the classes the race cannot take give way to their images
(1298's `006060f0`, 1264's `0043ec90`: a disabled class button is hidden and
its `img_*` shown). A class click chooses, for the chosen race, the one of its
specialties that race has (KO: by the player's nation; 1298's `006062d0`,
1264's `0043ee10`), and Create sends it.

The stat labels (version 25, RQ-172; version 23's flag 16, RQ-145, Q93 (b)):
a class click marks the create with its class, and each open (with the class
chosen there, if any) and each race click that builds the character (the race
changed) clear the mark, so a click on the race already chosen, which
unchooses the class and builds nothing, leaves it (1298's `00604f90` builds
only on a change of race; its build `005fd120` and reset `006066b0` show every
label by `00605950`; 1264's SetChr `00439970` runs its Reset `0043ea10` on a
change, which hides them all). A label with flag 16 draws unless the marking
class names it (1298's `006062d0` hides the clicked class's two cream `*_01`
labels, its `*_02` cyan copies showing: warrior `str`, `sta`; rogue `dex`,
`sta`; mage `int`, `map`; priest `str`, `int`); one with flag 32 draws only
while it does (1264's `0043ee10` shows the clicked class's two pink `img_*`:
warrior `img_str`, `img_sta`; rogue `img_sta`, `img_dex`; mage `img_int`,
`img_map`; priest `img_str`, `img_int`).

The stat arrows (version 26, RQ-173, item 15; `specs/KO-FINDINGS.md` §10.4,
binary: 1298's `00604f90`, `005fd120`, `00605950`, 1264's `0043dfc0`,
`00439970`, `0043ea10`), create screen only, with the package's create rules:
each open starts with no points and the value and points texts empty (1298's
reset `006066b0`; the points a Cancel leaves are not kept, Q111). Each build
takes the stat row (row 0: the race's with the chosen class or the race
button's default; row 1, 1298's: the same, the build happening on a class
click that changes the class too) and writes its stats as the values and its
bonus as the points left, so every build resets the points spent; a build is
an open with the race chosen, a race click that changes the race and (row 1)
a class click that changes the class with a race chosen. A right arrow
(`create_stat_up`) moves a point into its stat while any is left, with or
without a class; a left arrow (`create_stat_down`) takes one back while fewer
than the bonus are left and the stat is above the last build's row (1264's
one row for the race; 1298's for the race and class, every change of either
building), in row 1 only with a class chosen (1298's lookup by race and class
finds none for class −1). The value texts (`create_stat`) and the
points text (`create_points`) show the numbers once a build has written them
(1298's `SetStringAsInt`), empty before.

The face and hair arrows (version 27, RQ-174; `specs/KO-FINDINGS.md` §10.5,
binary: 1298's `00604f90`, 1264's `0043dfc0`), create screen only, with the
package's create rules: `create_face_down` and `create_face_up` step the face
by one, `create_hair_down` and `create_hair_up` the hair, each stopping at 0
and at the last of `create.bin`'s faces or hairs for the chosen race (KO's 3
and 2, constants of both binaries, the same for every race), no wrap, with or
without a race or class. With no race chosen (or one `create.bin` lacks) the
range is the fewest of `create.bin`'s races, and a race click takes a value
past the race's range into it (Q112: KO's range is one, so this never moves
it). No open writes them (1298's player `+0x7d8` and `+0x7dc`: zeroed by the
player's constructor `00465410` and Release `00465740`, written by neither
Init, Cancel nor the build), so a create keeps the face and hair of the last
one, from 0 at the client's start. The new character draws the face and hair
parts they name (item 8; KO's `InitFace` and `InitHair` through the player's
vtable `+0x28` and `+0x24`, called on a change and by each build), none for a
model without that part (the Wrinkle Tuarek's hair: its value moves, nothing
is drawn). A create that binds a face or hair arrow draws and sends the
fixed choice's face or hair for the one it does not bind (Q110).

The description text (version 28, RQ-175, item 16; `specs/KO-FINDINGS.md`
§10.6, binary: 1298's MouseProc `00605bf0`, 1264's `0043eb00`), create screen
only: the node bound to `class_desc` draws in item 16's colour (KO's
`0xffffff00`, set before the first frame, so the layout's colour is never
drawn). Each frame create shows, before it draws, the client takes the text of
the tip whose node's rect, where the frame draws it, holds the pointer
(edges included), the last group's hit winning and within a group the first
tip's, whatever the node's state or visibility (KO's `IsIn` reads the rect
only). Off every tip, rest 1 (`keep`, 1264's) leaves the text as it was, the
open text from each open; rest 2 (`chosen`, 1298's) shows the chosen class
button's tip, else the chosen race button's, else nothing (an assign, not a
join).

`create_confirm` then refuses, in `005fffd0`'s order (1264's `0043a340`), an
empty name (`create_name`), no race (`create_no_race`), no class
(`create_no_class`), (version 26, RQ-173) with stat arrows, points left
(`create_points_left`, code 10) and (RQ-004) a name the package's rule refuses
(`create_refused`, in the package's wording of the server's name refusal),
each in the message box; then (RQ-172) the chosen race and specialty with the
face, hair and stats it would send, as the server's `Policy::choice` checks
them (`create_choice_refusal`, Q95: a race or specialty the package does not
offer is `create_refused` in the package's wording of the server's mismatch
refusal); otherwise it sends the create: the chosen race and specialty, the
face and hair the arrows chose (RQ-174; without them the package's fixed
face and hair, Q110) and the stats the arrows chose (without arrows, the
fixed choice's points on the chosen specialty's base stats; Q110), in the
first free slot. The client's own wording for the three
is "Choose a race.", "Choose a class." and "Spend the stat points left.". A
create that binds neither keeps race and class chosen from the open and the new character at the slot in focus, and sends the
package's fixed choice (Q100), as before version 21.

The recipe binds the buttons in the create screen's `races` (`{"<node>":
{"race": R, "default": S}}`) and `classes` (`{"<node>": {"specialties":
[...], "image": "<node>", "labels": ["<node>", ...]}}`), not in `bindings`,
with `class_labels` (`hide`, flag 16, or `show`, flag 32) when any class names
labels; `states` may make one race and one class button `down`, chosen at each
open, and no other state. The cook refuses them on another screen, a
`create_race` or `create_class` in `bindings`, a node named twice or hidden, a
race code twice, a specialty in two class buttons, an image that is not an
image node, is hidden or is named twice, a label named twice or hidden, a label
that is a button or an image of the column, labels without `class_labels` or
`class_labels` without labels, a node they name that draws nothing, and (with
the package's `character-create.json`) a race that is not one of its races, a
default that is not one of the race's specialties, a specialty no race has, a
class button two of whose specialties one race has, or buttons without the
package's create rules. The race buttons of races the package does not offer
are the recipe's to leave unbound (Q109 (a): fixed disabled, or the 1097
choice's Puri Tuarek unfixed and unbound, Q90). Version 22's `until_race` and
23's `until_class` are refused: the class buttons' images and labels do their
work.

The recipe binds the stat arrows in the create screen's `stats` (`[{"value":
"<node>", "down": "<node>", "up": "<node>"}, ...]`, in the package's
`character-create.json` stat order), `points` (the points text's node) and
`stat_row` (`race` or `class`, item 15's row), all three or none, not in
`bindings`; an arrow takes no fixed state. The cook refuses them on another
screen, one without the others, more than 8 stats, a stat that is not exactly
those three keys, a node bound, hidden, fixed or named twice, a value or
points node that is not a text or an arrow that is not a button, a node they
name that draws nothing, an unknown `stat_row`, and (with the package's create
rules) a stat count other than the rules', stats without race buttons, or
stats without the package's create rules.

The recipe binds the face and hair arrows in the create screen's `bindings`
(version 27, RQ-174), each action once; an arrow takes no fixed state. The
cook refuses them on another screen, on a node that is not a button or has a
state, twice, and without the package's create rules.

The recipe gives the description text in the create screen's `descriptions`
(version 28, RQ-175): `{"colour": "AARRGGBB", "rest": "keep" | "chosen",
"open": <text>, "areas": {"<area>": <text>, ...}, "classes": {"<button>":
<text>, ...}, "races": {"<button>": <text>, ...}}`, each text a client table
row (`{"table": "<path>", "row": N}`, read as the messages' are), each group
in KO's loop order, `open` with `keep` only and optional. The cook refuses
them on another screen, an unknown key, a missing colour or rest, a colour
that is not 8 hex digits, an unknown rest, `open` with `chosen`, a node of
the wrong kind (an area in `areas`, a button in the others), hidden or named
twice, more than 32 tips, a text the realm's fonts cannot draw (non-ASCII;
CP949's `A1 AF`, a right single quotation mark, is drawn as ASCII's
apostrophe, Q113), a node that draws nothing, and descriptions without a node
bound to `class_desc`.

A recipe screen's `states` fixes a node's button state: `on` and `disabled` are
flags 1 and 2. `down` (RQ-138, Q89 (b), `specs/KO-FINDINGS.md` §9.16, binary) is
the cook's, with no flag or version of its own: flag 1, the button's down image
(state image 1) written with the down and on mask bits and its on image (2) not
written, so the button draws as one KO holds down whether or not the pointer is
on it (1264's chosen race and class: `0043ec90` and `0043ee10` set state 3,
which Render `00403a70` draws with `BS_DOWN`). On a race or class button
(version 25) `down` is the choice made at each open instead: flag 1 with every
state image kept, the client drawing the button down while it is chosen. The
cook refuses `down` on a node that is not a button or whose down image is
missing or untextured.

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
  `{"front_end": "<client>"}`, and optionally `create`, the character-create
  choices (RQ-002: `table`, `races`, `reserved`; RQ-154: `start`, `items`;
  `content/character-create.md`, "The realm's create"). It takes no other key (a misspelt one is refused, not
  ignored). Moradon's is `"1097"` (Q71), with no `create`.
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
follows, are one tree's), `select.character.plugs`, each
`select.characters[]`'s joint, animation (one tree's, as the select
character's) and plugs and `select.class_names.table` (RQ-005), and
`music.tracks[].path`. A
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
  RQ-005: since 1298 poses a Tuarek of any class from these files, the recipe
  names no `characters` (every Tuarek draws the select model) and gives
  `class_names` from the pinned tree's own table (`00613ea0`, the same rows as
  1097's `0052e3e0`), with `class_name` "Unknown Class" (`006d8e08`);
  `front-end.bin` is 64,447,563 bytes.
- `front_clip` `loop` (`005fef90`): the front clip looping on the character in
  front at rest, the rest clip once on the others and on everyone while the
  camera turns; the spot widens to 0.5 by 0.02 a tick (`006a93b4`, `006a93bc`,
  Karus) and stays; the info texts show at rest, empty for an empty slot
  (`006074c0` writes the empty string; `select_hint`, which only `char_info`
  shows, is empty).
- `turn` `path` (`005fa670`, `005fe5b0`): `ChrSelect/Data/ka_lording_camera.n3camera`
  flies the camera in to the centre slot in 6 s as the hall opens;
  `ka_center_left`, `ka_center_right`, `ka_left_center` and `ka_right_center`
  turn it between the centre and the side slots in 4 s each (1298's paths 2–5);
  `ka_left_right` and `ka_right_left` (paths 6 and 7, 3 s each) take it from
  side slot to side slot, only for Create from an occupied slot (`005ff920`;
  RQ-114, `specs/KO-FINDINGS.md` §9.14). The select UI is hidden while a path
  plays; ENTER or ESC skip a turn's or the entry's to its end, not Create's.
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
- `select.back` `realms` (RQ-112, `specs/KO-FINDINGS.md` §9.12, binary): Back
  lands on the realm list, the bar hidden from the click, as 1298's Back
  (`00607160`) sets its login procedure's `+0x21` and the login's Init
  (`005f68e0`) then connects, asks for the server list (`0xf5`) and hides
  `Group_LogIn` (Q87).
- `select.arrows` `draw` (RQ-113, `specs/KO-FINDINGS.md` §9.6, binary): both
  arrows draw at every slot, as no code in 1298 hides one (its bar's arrow
  fields are read only by ReceiveMessage `00607160`'s compares); a press at the
  end of the row does nothing (Q87).
- Music: `Snd/Intro_Sound.mp3`, looping on login, the realm list, select and
  create; loading silent (`005f68e0`, `005fea70`, "Moradon" below).
- Still the 1097 recipe's, not 1298's: the 1098 login scene (1298 draws a UIF
  intro), and the login and loading layouts (the pinned tree's `UI_US`, as
  today).
- Create (RQ-125, version 19, `select.create` `hall`, `specs/KO-FINDINGS.md`
  §9.15, binary): 1298's in-select create, the select's window `+0x388`,
  which `005fab40` loads from row 2's 121st string of the pinned tree's
  `Data/UIs_us.tbl` (`+0x794` of its map node, the bar's 120th beside it),
  `UI_US/co_characterCreate_us.uif`: three
  panels, `Group_race` (the race buttons, the description, Create and Cancel),
  `Group_class` (the class buttons and the stats) and `Group_name` (the name
  entry), drawn over the hall. `place` `origin` (`005fab40`'s SetPos(0, 0)),
  each panel moved to where 1298's Tick (`00606450`) clamps its slide: `Group_class`
  50 from the left, `Group_race` 50 from the right (`right`), `Group_name`
  centred (Load `00603850`'s x), each bottom 30 above the window's. Bound as
  its ReceiveMessage (`00604f90`) uses it: `btn_create` `create_confirm`,
  `btn_cancel` `back`, `edit_name` `name_field`, `text_desc` `class_desc`;
  (RQ-172, version 25, item 14) `races` binds `btn_race_ka_tu` as race 2,
  default 102, the one race Moradon offers (Q105), and `classes` the four
  class buttons as 1298's `006062d0` maps them (`btn_class_warrior` 101 and
  201, `_rogue` 102 and 202, `_mage` 103 and 203, `_priest` 104 and 204), each
  with its `img_*` and its two cream labels (warrior `str_01`, `sta_01`; rogue
  `dex_01`, `sta_01`; mage `int_01`, `map_01`; priest `str_01`, `int_01`:
  Load `00603850` keeps them in the order str, dex, sta, int, map, and
  `006062d0` hides flags 0 and 2, 1 and 2, 3 and 4, 0 and 3), `class_labels`
  `hide`; states: the other races (Q109 (a): their textured disabled tiles,
  the Puri Tuarek's too), none chosen at the open; (RQ-174, version 27)
  `bindings` `btn_face_left` `create_face_down`, `btn_face_right`
  `create_face_up`, `btn_hair_left` `create_hair_down` and `btn_hair_right`
  `create_hair_up`, live from the open as `00604f90`'s;
  hidden: El Morad's three race buttons (Load shows Karus's and hides El
  Morad's for a Karus player). (RQ-173, version 26, item 15) `stats` binds
  `text_str`, `text_sta`, `text_dex`, `text_int` and `text_map` with their
  `btn_*_left` and `btn_*_right` arrows, `points` `text_bonus`, `stat_row`
  `class` (`00604f90`'s and `005fd120`'s lookup by race × 10000 + class): the
  texts are empty from each open until the Tuarek click, which writes its
  default class's row (102's) and 10 points; a right arrow spends a point
  before a class too, a left arrow takes one back only with a class; each
  class click that changes the class writes its row and resets the points;
  Create says `create_points_left`, row 1913 titled 1901 (`005fffd0` code 10,
  after codes 7 and 9), until every point is spent, then sends the five
  stats. (RQ-175, version 28, item 16) `descriptions`, rest `chosen`, colour
  `ffffff00`, the pinned tree's `Data/Texts_us.tbl` rows as Load `00603850`
  gives them: `area_str` 3219, `area_dex` 3202, `area_sta` 3220, `area_int`
  3210, `area_map` 3201; the classes 3217, 3215, 3212, 3213; the races `ka_at`
  3211, `ka_tu` 3216, `ka_wt` 3218, the Puri Tuarek's 3214 left out as Korean
  (Q114). `text_desc` is empty in yellow from the open, shows the tip under
  the pointer, and off them the chosen class's text, else the Tuarek's after
  its click (MouseProc `00605bf0`; KO-FINDINGS §10.6).
  Each open draws every class button over its `img_*` (`00605950`, by the
  reset `006066b0`), each live, as 1298's are NORMAL before the race click; the
  Tuarek click hides the warrior and mage buttons, their greyed images standing
  in their place, and the rogue and priest images (`006060f0(2)`), the rogue
  and the priest live (RQ-133's `until_race` drew the same for the Tuarek).
  Each stat label is a cyan `*_02` under a cream `*_01` in one rect; a class
  click hides its class's two cream labels, so after the priest click "STR"
  and "INT" read cyan, after the rogue's "DEX" and "HP" (RQ-145's `until_class`,
  Q93 (b), the maintainer's 2026-11-04, "Match 1298", for the priest; §9.15,
  binary: `006062d0`), cream again on the Tuarek click that builds the
  character (`005fd120`) and at each open, still marked after a click on the
  chosen Tuarek (`00604f90` builds nothing). The Tuarek click draws the
  Tuarek's create model and takes 102 for its stat row.
  The new character stands at the slot turned 213, 143 and 283 degrees at
  slots 0–2 (`create_yaw`; `005fd120`'s `0x406dec5d`, `0x401fbb88`,
  `0x409e0e99` for Karus). The panels slide in each time create opens
  (RQ-126, version 20, `slide`, §9.15, binary): `rate` 1300 and `floor` 2,
  `Group_race` the lead from the right edge (Load `00603850`'s x = W),
  `Group_class` from the left (x = −w) and `Group_name` from the bottom
  (y = H) `with` `Group_class` (trunc((h + 30) d / (w_c + 50)), 102 / 266 on
  the pinned layout), as 1298's Tick (`00606450`) moves them; the slide ends
  on Group_race's arrival, which at frame times under about 0.2 s (its last
  steps the 2 px floor, d ending in [264, 266)) leaves `Group_class` at 48 or
  49 and `Group_name` 29 above the bottom edge, as 1298 leaves them. Race and
  class wait for their clicks (RQ-130, Q87 option (b), the maintainer's
  2026-11-03: "Match 1298: wait for a race"; §9.15, binary): create opens with
  neither chosen and no new character, which stands once the Tuarek is clicked,
  at the slot the camera was on for that click (`005fd120`); a Tuarek click
  unchooses the priest; a chosen button draws down; Create says
  `create_no_race`, row 1908, or `create_no_class`, row 1904, each titled row
  1901, as `005fffd0` and `00600750` post codes 7 and 9 (`messages`). Since
  RQ-172 every class button is live as 1298's (lit under the pointer, taking a
  click), and Create sends the Tuarek with the clicked class, the rogue (102)
  or the priest (104). After a Cancel
  mid-flight 1298's camera flies on to the empty slot (`005ffb90` leaves it
  alone), the select at rest on the slot it left; the recipe's is put on the
  slot at once. The hall lights `ka_light_0/1` are the files both
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
  pinned tree's `Data/Texts_us.tbl`, untitled, as 1298 posts them. Create
  from an occupied slot opens 1298's in-select create at once over the hall,
  the camera flying to the empty slot behind it (RQ-114, RQ-125: `005ff920`;
  "Create", above). Back lands on the realm list (RQ-112, `select.back` `realms`, above).
  Both arrows draw at the ends of the row, as 1298's do (RQ-113,
  `select.arrows` `draw`). Exit asks, as 1298's does (below).
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
  1264's placements, which the cook writes as item 12's rules. Create's
  `slide` (version 20, item 13; create's only, none by default): `rate`,
  `floor` and `nodes` in order, the first the lead, each a `node`, `from`
  (`right`: x = W, `left`: x = −w, `bottom`: y = H, `top`: y = −h, its start
  just past that window edge) and optionally `with` another of its nodes (num
  and den its travel and that node's at the canvas, so the two arrive
  together; num and den 1 without it); a node the layout hides is refused.
  Create's `races`, `classes` and `class_labels` (version 25, item 14;
  create's only, none by default) bind its race and class buttons to KO's
  codes ("Actions"). The recipe's
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
  realm's ESC there, Back, which stays on `bt_back`. Back lands on the realm
  list with neither the bar nor the copyright line (`select.back` `realms`),
  as 1264's lands on its server list (RQ-112, §9.12, binary: `bt_back` sets the
  login procedure's `+0x35` at `00445145`, whose Init `005bd9b0` connects, asks
  for the list and hides `Group_LogIn` alone), the maintainer's choice
  (2026-11-03, "Match 1264", RQ-123). Both arrows draw at the ends of the row
  (`select.arrows` `draw`), where a press does nothing, as 1264's select draws
  both (RQ-113, §9.13, binary: `004448f0`, `00444e60` and `004454e0` only place,
  compare and click them), the maintainer's choice (2026-11-03, "Draw both, as
  1264", RQ-124).
- Create (`UI_US/Ka_CharacterCreate_us.uif`, centred): the buttons bound to
  KO's codes (RQ-172, version 25, item 14): `races` binds `btn_race_ka_tu` as
  race 2, default 102, and `classes` the four class buttons as 1264's
  `0043ee10` maps them (101/201 to 104/204), each with its `img_*` (the
  darker grey tile 1264 shows in place of a class the race cannot take) and its
  two pink labels (warrior `img_str`, `img_sta`; rogue `img_sta`, `img_dex`;
  mage `img_int`, `img_map`; priest `img_str`, `img_int`), `class_labels`
  `show`. The Tuarek and the priest are `down`, chosen at each open (Q52), so
  the open looks as 1264's after a Tuarek and a priest click, as the
  maintainer's choices had it: both drawn with their sunken down tiles (RQ-138,
  Q89 (b), "Sunken, as 1264"; §9.16, binary: `0043ec90`, `0043ee10`,
  `00403a70`); the warrior and mage buttons give way to `img_warrior` and
  `img_mage` and `img_rogue` and `img_priest` are hidden, by the Tuarek's
  classes (RQ-142, Q91 (b), "Match 1264"); "Strength" and "Intelligence" draw
  pink over their light labels, "Health", "Dexterity" and "Magic Power" light,
  by the priest's labels (RQ-144, Q92 (b), "Pink Str/Int, as 1264"; §9.16,
  binary: `0043ee10`, `0043ea10`). The rogue, inert under Q91 (b), is now a
  live NORMAL button as 1264's (lit under the pointer; a click chooses the
  rogue, unchooses the priest and turns "Health" and "Dexterity" pink in
  place of "Strength" and "Intelligence"), as Moradon offers the Tuarek's
  rogue and priest. A click on the Tuarek unchooses the class (`0043ec90`), and
  Create then says `create_no_class`, row 1904 titled 1901, as 1264's
  `0043a340` posts code 9 through `0043a820` (`messages`). Every other race
  (Q109 (a): the Arch and Wrinkle Tuarek fixed disabled; the Puri Tuarek,
  whose disabled image has no texture, unfixed and unbound, its normal grey
  tile, inert: RQ-139, Q90, "Grey button, as 1264"); (RQ-174, version 27) the
  face and hair arrows bound as the 1298 recipe's (`0043dfc0`'s, the same
  steps and ends), no longer fixed disabled (Q52). (RQ-173, version 26, item 15)
  `stats` binds the five `text_*` values and their `btn_*_left` and
  `btn_*_right` arrows, `points` `text_bonus` (pink, as the layout draws it)
  and `stat_row` `race` (1264's `0043dfc0` looks the row up by the race alone,
  and its SetChr `00439970` builds on a race change only): each open, the
  Tuarek chosen, writes the priest's row and 10 points, a class click builds
  nothing, and the left arrows work without a class; Create says
  `create_points_left`, row 1913 titled 1901 (`0043a340` code 10), until every
  point is spent, then sends the five stats. (RQ-175, version 28, item 16)
  `descriptions`, rest `keep`, colour `ffffff00`, the 1264 install's
  `Data/Texts_us.tbl` rows as its Load `0043cd00` gives them: open 6124
  ("Karus Character Window." after two line breaks), `area_str` 3219,
  `area_sta` 3220, `area_dex` 3202, `area_int` 3210, `area_map` 3201
  ("Unconfirmed nation", as 1264 shows it); the classes 3217, 3215, 3212,
  3213 (the warrior's "ally's" drawn with ASCII's apostrophe, Q113); the races
  `ka_at` 3211, `ka_tu` 3216, `ka_wt` 3218, `ka_pt` 3214, the disabled and
  unbound ones too (IsIn reads the rect only). `text_desc` shows row 6124 in
  yellow at each open and the last tip the pointer was over after (MouseProc
  `0043eb00`; KO-FINDINGS §10.6).
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
  | `create_name`: "Enter a name: 1 to 24 letters, digits, _ or -." (RQ-004: from the package's name rule, Moradon's "Enter a name: 1 to 20 letters, digits, _, : or ;.") | an empty name (`0043a340`: code 6 → `0043a820`, ReportErrorCharacterCreate: row 1905, title row 1901) | title and text: the 1264 install's rows 1901 ("Failed creating character") and 1905 ("Please enter your character ID. ") |
  | `create_refused`: the server's wording of the refusal | the server's create answer (`0043a820` by its code: 1911 no more characters, 1912 a name in use, 1906 a forbidden letter, and others; title row 1901) | title only: the 1264 install's row 1901; since RQ-002 the server words each refusal with KO's row for its code, from the package's create table's texts (`content/character-create.md`, "The realm's create"), so its words stay |
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
  `upc_ka_at_wa.n3anim` the 1097 client plays there (since RQ-005 the
  select model of every character but the Tuarek rogue's; `characters` gives
  the rogue, specialties 102, 107 and 108, 1097's `upc_ka_tu_rog.n3joint` with
  the same clips and the bow and quiver plugs, `0043ba10`, KO-FINDINGS §8.1;
  1,128,608 bytes with its plugs' meshes, so the 1097 choice's `front-end.bin`
  is 62,338,435 bytes; `class_names` the 1264 install's rows for KO's 24 class
  codes, 1097 `0052e3e0`, and `class_name` "Unknown Class", its default): 0 `pre_select` (hover), 1
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
