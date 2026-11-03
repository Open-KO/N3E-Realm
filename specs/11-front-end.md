# 11 — KO front-end: intro, login, server list, character select, loading

**Status: approved 2026-10-31** (the maintainer accepted Q50–Q56 as drafted); M4c implements it.

## Purpose

Players should start in Knight Online, not in a test panel. The client today opens on
a text box ("N3E / ADVENTURE", ACCOUNT, SELECT CHARACTER), drawn in code in
`client/render/play.h`. This spec replaces that, for the realm, with KO's own front
end, cooked from the pinned client tree (`assets/ko/`, spec 10, option C) and,
for the 1097 choice's screens, the pinned 1264 install (RQ-085, "The client choice"):

0. **Logo** (RQ-101, Q82). 1264's "K2 Network presents Knight Online", before the
   login, once a process, when the chosen client shows one (the 1097 choice does).
1. **Intro and login.** KO's login scene, with the orc and the axe under the moon, and
   the login bar, as KO draws it (Q61). Its Login button starts spec 02's Discord login.
2. **Server list.** KO's server group, with the realm as its one entry.
3. **Character select.** The Karus select hall in 3D, with up to three characters,
   rotated left and right as KO does, and the info bar (ID, level, class) with KO's
   left, right, Back and Exit buttons. As in KO, ENTER or a click on the character in
   front starts the game, and ENTER on an empty slot opens create; Delete is hidden
   (Q53).
4. **Character create.** KO's create screen, reduced to what the realm supports (Q52).
5. **Loading.** KO's loading art (1264's for no war victor, Q80), with a progress bar
   that tracks real work.

At the same time the realm package becomes the **player-facing** package
everywhere: the local release, the Windows kit and `tools/local-realm` serve Moradon
(`build/packages/moradon`), not `demo`. `demo` and the other synthetic packages stay
as test fixtures (Q50).

## Scope

In scope:

- An assetc cook step, `ko_front_end.py`, writing an optional package section (below).
- Client screens that draw that section: a 3D scene, then a UI tree over it, with
  bindings to fixed engine actions.
- One wire addition (the character's level) and one server rule moved into package
  data (the character limit).
- Moving the player-facing tools and docs from `demo` to `moradon`.

Out of scope:

- Nation choice (Q51).
- Race, class, face, hair and stat choice (Q52).
- Character deletion (Q53).
- More than one realm in the list (Q54).
- Renaming the `demo:` ids inside the Moradon content (Q55).
- In-world UI changes.

## Inputs (all under `assets/ko/`, never committed)

Every path below was checked against the pinned tree. The paths and choices live in
the chosen front end's recipe (`games/moradon/front-end.json` for 1097, "The client
choice" below); the engine knows none of them.

| Screen | Scene | UI layout (`UI_US/`) |
|---|---|---|
| Intro and login | `CGameProcLogIn_1098`'s: `Intro/Intro.N3Chr` (its joint, clip 0, parts and the axe plug), `Intro/0..2.N3Light` (2 is off), `Intro/Moon.dxt`, the camera from the source | `co_login_us.uif` (`Group_LogIn`, `Group_ServerList`) |
| Server list | the intro scene, still running | `co_login_us.uif` `Group_ServerList` |
| Character select | `ChrSelect/ka_chairs.n3shape`, `ka_light_0/1.n3light`, the Karus slots, spots and cameras of `CGameProcCharacterSelect::Init`; the Tuarek priest (`upc_ka_tu_pri.n3joint`, `upc_ka_at_wa.n3anim` clips 0, 1 and 2, `UPC_DefaultLooks`, the mace plug) | `ka_characterselect_us.uif` |
| Character create | the character in `area_character` | `Ka_CharacterCreate_us.uif` |
| Loading | none | `ka_loading_us.uif` |
| Message box | over any screen | `co_MsgBoxOk_us.uif` (the 1097 choice draws 1264's `el_messagebox_us.uif`, §9.2, with Yes and No since RQ-115; the 1298 recipe 1298's, the pinned tree's `el_messagebox_us.uif` with Yes and No, RQ-111) |

Music (Q57, RQ-018, RQ-083): the chosen client's. For 1097 (Moradon's), `Snd/bgm_login.wav`
on the login and the realm list, restarted every 21.66 s, and `Snd/bgm_el_battle.wav`,
looping, on select and create, stopped when the chosen character's clip has played;
both carried as their 16-bit samples (KO-FINDINGS §9). KO 1298's own track,
`Snd/Intro_Sound.mp3`, would be carried as its MPEG frames (Q69). Text is drawn with
Liberation Sans regular and bold for KO's Arial, at points × 96 / 72, baked as N3H9's
nameplate fonts are.

What the cook reuses: `ko_hud.parse()` for the UIF trees, `ko_hud.texture()` and the
character texture reader for NTF3, `ko_character.py` and `gltf.py` for the two
characters (N3SM with render runs for the intro, N3S1 for the select hall), and
`ko_appearance.read_plug()` for the plugs. New: strict `.n3light` and standalone
`.n3shape` readers (`tools/assetc/ko_front_end.py`).

## Interfaces

### Package file `front-end.bin` (normative)

An optional presentation file, N3FE version 17, engine 42 (so wire 30). Its layout,
bounds and the action set are in `content/front-end.md`. The client treats it as
optional: **a package without it gets today's panels**, which is how `demo` and every
test fixture keep working. A package with it is the realm's: the screens below
replace the panels when the client has a Discord realm config.

- **Screens.** Five node lists in draw order (login, select, create, loading,
  message): each node a kind, parent, canvas rect, id, action, state flags and a
  button-state mask, with image, text, edit and list data. The realm list is the
  login screen's server group, shown in the realms state.
- **Actions** form a closed engine set, by index: `none`, `login`, `exit`,
  `login_group`, `realm_group`, `realm_list`, `realm_connect`, `notice`,
  `select_prev`, `select_next`, `back`, `char_info`, `create_confirm`, `name_field`,
  `char_view`, `class_desc`, `progress`, `version`, `info`, `message`, `ok`, `title`,
  `login_closed` (N3FE version 12, RQ-108: a login node drawn only while the login
  group is not, KO's copyright line; RQ-110: every layout hides its login group
  while a login is under way, as 1264 and 1298 do, whether it binds one or not),
  `select_start`, `select_create`, `select_delete`, `char_name`, `char_level`,
  `char_class` (N3FE version 13, RQ-109: 1298's select bar, its Start, Create and
  Delete buttons and its name, level and class texts; KO-FINDINGS §9.6), `yes`,
  `no` (N3FE version 14, RQ-111: the message box's Yes and No, drawn only for the
  select's exit question, `exit_confirm`; KO-FINDINGS §9.7). The cook
  and the loader refuse an unknown action, an action bound twice in a screen, a
  `login_closed` off the login screen, one of version 13's off the select, `yes` or
  `no` off the message box, and a screen whose required actions are unbound.
  Required per screen:
  - login: `login`, `exit`, `login_group`, `realm_group`, `realm_list`,
    `realm_connect` (`notice` is optional; the Moradon package has none, Q61);
  - select: `select_prev`, `select_next`, `back`, `exit`, and an info text:
    `char_info`, or any of `char_name`, `char_level`, `char_class`;
  - create: `create_confirm`, `back`, `name_field`, `char_view`;
  - loading: `progress`;
  - message: `message`, `ok`.
- **Strings.** `select_info`, `select_hint`, `class_name`, `class_desc`,
  `loading_info`, `version`; the client fills `{level}`, `{class}`, `{name}`,
  `{version}`.
- **Scenes.** The intro (camera, lights, the model with its clip and plugs, the moon
  as a screen quad) and the select hall (camera, lights, `character_slots` slots with
  their eye and spot light, the spot's growth rate, the front-clip mode (N3FE
  version 6, RQ-086), the turn mode and its camera paths (N3FE version 7,
  RQ-087), the hall meshes (none or more, version 7) or, since version 8 (RQ-095),
  a zone (up to 256 meshes of a zone's terrain and shapes, each lit or unlit and
  cut at alpha 0 or blended after the UI, far to near) and the camera files' fog
  (on or off, its colour and linear start and end), the model with clips 0, 1 and 2 (front,
  start, rest), plugs), each model clip with the time the
  client blends into it over (N3FE version 4, RQ-075; the record's, or the package's
  own for the start clip, RQ-076),
  and the create model (the race's own looks joint and animation, `ANI_BREATH`, no
  plugs; N3FE version 2).
- **Music** (N3FE version 3, RQ-018; version 5, RQ-083). Up to 4 tracks, each MPEG-1
  or MPEG-2 Layer III frames (every frame checked at load) or, since version 5,
  16-bit PCM samples (KO 1097's WAVs), each ≤ 16 MiB, looping or not, with an
  optional restart period (the track starts again at its first sample after that
  much playback: 1097's login restarts its track every 21.66 s); and the track the
  login, select, create and loading screens play, or none. The client streams the
  track (one MPEG frame or 1152 sample frames at a time, `client/assets/music.h`); a
  screen naming the track already playing keeps it, so it runs on across the
  screens; entering the world stops it. Option.ini `[Sound] Effect=0` silences it with every other sound, as in
  KO 1298 (Q70).
- **The select hall's front-clip mode** (RQ-086, Q71). What the character in front
  plays at rest: `hover`, 1097's (the default: the front clip once while the
  pointer is on the character, the rest clip otherwise, the spot and the info
  text following the pointer), or `loop`, 1298's (the front clip looping and the
  rest clip once on the others whatever the pointer does, the spot widening and
  the info text shown at rest; the centre rect only takes the click). The recipe
  names it (`select.front_clip`); `games/moradon/front-end-1298.json` uses `loop`
  and is not offered yet (`content/front-end.md`, "Choosing the client").
- **The select camera's turn mode** (RQ-087, Q77, Q78). How the camera goes from
  slot to slot: `rotate`, 1097's (the eye turns about `at`, the select UI shown
  throughout), or `path`, 1298's (the camera plays a recorded path: up to 8 paths
  between slots, each its eye and at keys from a `.n3camera`, 30 frames a second;
  the entry path flies in to the centre slot as the hall opens from the realm
  list; the whole select UI is hidden while a path plays, and ENTER or ESC skip to
  its end; `specs/KO-FINDINGS.md` §8.4). The recipe names it (`select.turn`, with
  `select.paths` in the path mode); `games/moradon/front-end.json` uses `rotate`,
  `games/moradon/front-end-1298.json` `path`.
- **The logo screen** (N3FE version 9, RQ-101, Q82). A package may hold a logo
  screen: its nodes (groups, images and strings, no action), up to 8 groups each
  with its fade-in, hold and fade-out, its music (a track, its delay, the group its
  fade-out starts with and the fade's length) and its flags (a key skips it; it
  hides the cursor). The client starts on it, shows each group alone in turn at
  its alpha over black, then opens the login; a key pressed while it shows skips
  it with the flag (not one queued before its first frame, nor a modifier the
  window system reports as held on a focus gain), a click never does. The realm
  connection starts when it ends, as 1264's login connects; a message raised
  meanwhile shows on the login. Whether a package has one is the recipe's `logo` key alone
  (`content/front-end.md`, section 10 and "Moradon"); the 1097 recipe has 1264's
  (`specs/KO-FINDINGS.md` §9.2).
- **The messages** (N3FE version 10, RQ-102, Q81). The front end's messages are a
  closed engine set (a failed connection, a closed one, the Discord flow's
  failures, a banned or unavailable login, an empty name, a refused create or
  select, (version 13) a create with every slot taken and a delete, and
  (version 14, RQ-111) the select's exit question, `exit_confirm`;
  `content/front-end.md` section 11). The package may give any of them
  a title, drawn in the message box's node bound to `title`, and a text that
  replaces the client's wording; the recipe's `messages` names each as a
  string or a row of a KO client's text table. The 1097 recipe titles and
  words the ones that stand for a box 1264 shows with a title and leaves the
  rest untitled in the realm's words (`content/front-end.md`, "Moradon").
  Every message shows in an OK box but `exit_confirm`, which shows in a yes/no
  box (KO's `MB_YESNO`: the nodes bound to `yes` and `no` drawn, `ok` hidden;
  ENTER Yes, ESC No; Yes leaves the game, No closes the box). A package that
  names `exit_confirm` makes the select's Exit ask so, as 1298's and 1264's do
  (KO-FINDINGS §9.7, §9.8); without it, and on the login, Exit leaves at once.
  The 1298 recipe names it with the pinned tree's row 1502, the 1097 recipe
  with the 1264 install's (RQ-115).
- **The select's ESC** (N3FE version 15, RQ-116; version 16, RQ-119). What ESC
  presses on the select: `back` (the realm's, the default), `exit`, as a click on
  it, so it asks the exit question where the package names `exit_confirm`, or
  (version 16) `none`, nothing. It does so in every select state but two: in the
  path mode ESC while a path plays skips it instead, whatever the package says,
  and in both modes ESC does nothing while the start clip plays (RQ-121). So in
  the rotate mode it presses too while the camera turns. 1264's
  select presses `bt_exit` for ESC (OnKeyPress `004454e0`, `specs/KO-FINDINGS.md`
  §9.8), and the maintainer chose that for the 1097 choice (2026-11-02): its
  recipe names `exit` (`select.escape`), and its Back stays on its button. 1298's
  presses neither (RQ-117, §9.9: its bar's OnKeyPress `00607810` only skips a
  path, so at rest ESC does nothing), and the maintainer chose that for the 1298
  recipe (2026-11-02, RQ-119): it names `none` (Q87). 1264's and 1097's selects
  take no input from the select request until the main procedure (RQ-120, §9.10:
  the request and CharacterSelect clear the UI flag their OnKeyPress and
  ReceiveMessage test), nor does 1298's, so KO asks nothing while the start clip
  plays; the maintainer chose to match it (2026-11-03, RQ-121): then neither ESC
  nor a click on Exit does anything, whatever the package says (its `exit_confirm`
  included), as the arrows, Create, Back and a second start already do nothing.
- **Where the select's Back lands** (N3FE version 17, RQ-112). Back drops the
  connection and returns to the login, which connects again; a stored session
  logs in at once, as at start, and its answer opens the realm list, so with one
  the player is back on the realm list after a round trip. The package says how
  the login looks meanwhile (`select.back`): `login` (the realm's, the default),
  the bar shown while the client connects and hidden from the session's login to
  its answer, as for any login; or `realms`, the bar hidden from the click
  through the connection to the list, as 1298's Back sets its login procedure's
  `+0x21` and its login Init then connects, asks for the server list and hides
  the bar (`specs/KO-FINDINGS.md` §9.12, `00607160`, `005f68e0`). Without a stored
  session the bar shows and waits for a Discord login either way. The 1298 recipe
  names `realms` (Q87). 1264's Back lands on its server list the same way
  (`+0x35`, `005bd9b0`), its copyright line hidden too; the 1097 choice keeps
  `login`, a known difference left to the maintainer.
- **The placement** (N3FE version 11, RQ-106, Q82). KO draws its front end on the
  screen's own pixels, never scaled, and places each layout's root and some of its
  nodes by the viewport's size each time the layout loads (`specs/KO-FINDINGS.md`
  §9.3). The package carries those placements as each layout's moves, rules linear
  in the window's width or height (`content/front-end.md` section 12), from the
  recipe's `place` and `moves`; the canvas rects are the moves at 1024 × 768. Its
  flag, the recipe's `ui_scale` (`native` by default, or `window`), keeps the
  realm's earlier scaling of the canvas to the window as RQ-103's realm-owner
  option.
- **The select arrows' turn sound** (RQ-077, Q70). 1097's hall plays sound 2501,
  `char_select_turn.wav`, for each turn its arrows start. The package names the
  sound-table id (`front-end.json` `select.turn_sound`), and the cook binds it in
  `audio.bin` as `front:select-turn`. The client plays it once, unpositioned, for
  each turn an arrow starts; a new turn restarts it. The screens have no other
  sounds: neither 1298's nor 1097's layouts name a button sound (Q70).
- **`text` overrides.** The format allows them; the Moradon package uses none: the
  login screen keeps KO's labels and copyright line (Q61, superseding Q56), the
  line bound to `login_closed` at 1264's place (RQ-108, Q85).
- **`hidden`.** The Moradon package keeps the login bar as KO draws it: `Edit_ID`,
  `Edit_PW`, `Btn_Option` and `Btn_Join` (Registration) are shown, unbound, so they
  take no input (Q60, Q61). It hides `Img_Daum` and `Img_MGame` (their texture is
  not in the pinned tree, and 1264 never shows them, KO-FINDINGS §9.4), `premium` and the three notice groups (KO's news panels,
  empty without KO's server), and the select screen's `bt_delete` (Q53).

### The client choice (RQ-078)

The realm owner chooses which KO client the front end looks and behaves like, in
the package source: `games/<game>/realm-config.json` (`{"front_end": "<client>"}`)
names one of the clients `games/<game>/front-ends.json` offers, each with its
recipe (the `ko_front_end` input: for 1097, `front-end.json`) and the input trees
it reads. A recipe path reads the first tree, or the input it names by prefix
(`<name>:<path>`, RQ-084); a reference install is read only as a pinned
installer's unpack, each file checked against its manifest. Both files are
normative; their fields and rules are in `content/front-end.md`, "Choosing the
client". The cook (`make realm-assets`, every `ko_bake.py --features`, and
`ko_bake.package` itself) refuses, before the survey and before writing
anything, a choice the package does not offer, a choice whose inputs are
missing on the cooking machine or not their pinned installers' unpacks, a
recipe prefix naming no input, and a malformed file, each naming what to
change. The engine knows no client id: what
differs between clients is recipe data and N3FE fields, and the client and server
read `front-end.bin` as before. Moradon offers `1097`, the default (Q71), whose
screens are the 1264 client's English ones from the pinned 1264 install
(`specs/KO-FINDINGS.md` §9.2, RQ-085); what each other client needs is
`specs/KO-FINDINGS.md` §9 (Q73).

### Wire (`protocol/wire.proto`)

```proto
message Character { uint64 id = 1; string name = 2; uint32 level = 3; }
```

`level` is the character's level from `characters`/progression, as the HUD shows it.
It is a new optional field, so the wire version doesn't change. Golden
`golden-characters` is regenerated by both languages (`tests/check.py`). Class is not
on the wire: the realm has one class, and the select screen shows the package's label
for it (Q52).

### Server

- The character limit comes from the package: `front-end.bin`'s character slots when
  the file exists, else today's 8. `CreateCharacter` past it is error 8, unchanged
  ("character name invalid/taken or limit reached").
- `Characters` keeps creation order. The select screen puts the first three in the
  slots centre, left, right, as KO does.

### Client

The screens form a state machine in the client's front-end module
(`client/render/front_end.h`, not in `viewer.cpp`'s frame loop); it returns commands
and the viewer sends the protocol messages the panels send. The module draws a screen
in this order: scene, then the UI tree, then the message box. The UI is drawn
unscaled on the window's own pixels, each layout placed by its moves at the window's
size, as KO draws it (RQ-106, Q82); the 3D scenes keep their own projection and fill
the window, and where no node draws the window shows the scene or black. With the
package's `ui_scale` `window` flag, or on a window smaller than the canvas, the
client applies no moves and scales the canvas uniformly to fit the window, centred.
Hit tests and the cursor use the pixels the UI is drawn on. The system cursor
stays. Mouse clicks and hover drive the button states; keyboard
works too (ENTER = the screen's primary action, ESC = back/cancel, arrows =
prev/next; on the select ESC is the package's choice, below).

| State | Shows | Leaves on |
|---|---|---|
| logo | only with a logo section, first, once a process (1264's WinMain); each group alone in turn on black, fading in, holding and fading out; the system cursor hidden with the flag; its track from the delay, faded out from its fade group | the last group's end, or a key pressed while it shows with the skip flag (not a click) → login, whose own track starts at once and whose first frame starts the realm connection. A reset connection leaves it playing; a message waits for the login. |
| login | intro scene looping; login bar; while a login is under way (from the press, or a stored session's login, to the answer) the bar hidden and the package's `login_closed` node shown instead, when the layout binds one (KO's copyright line, RQ-108, Q85; RQ-110: the 1298 recipe binds none, 1298's login having no line, so it shows neither) | `login` (the Login button or ENTER) → the flow (spec 02, unchanged) → `LoginResult` → realms; a failure shows the bar again. A press while the client is still connecting is held and starts the flow once connected. A stored session skips the browser as today. Started with `--logout` (spec 02, RQ-068), the client first ends the stored session; a press meanwhile is held until the realm answers. The KO screens have no logout of their own (Q61, Q74). |
| realms | intro; the server group with the realm's name from `realm.json`; the `login_closed` node (RQ-108) | `realm_connect` → select. The connection and login already exist; this is KO's step, kept (Q54). |
| select | hall; up to 3 characters with the realm's player model and default looks, each standing on clip 0's first frame; the one in front, at rest, plays clip 0 (`pre_select`) once while the pointer is in `DoProcPreselect`'s centre rect and holds its last frame, and clip 2 (`dummy`, clip 0's first frame) otherwise, each change blending over the clip's own blend time from the frame reached, the new clip held on its first frame meanwhile; the front slot's spot widens at the package's rate while the pointer is there, narrows when it leaves and is off at 0; the info text (char_info) shows only while the pointer is there. This is the 1097 client's hall for this asset set (KO-FINDINGS §8.1, Q71), not 1298's | At rest only (not while the camera turns or the start clip plays): ENTER or a click on the character in front (`PtInRect` on the centre rect) → `SelectCharacter`, the spot at its full theta, its clip 1 blended in over the package's start blend (Moradon: 1097's 0.6 s) on its first frame and played to the end (`IsAnimEnd`, after the blend), → loading; a refusal returns it to the hover or rest clip; ENTER on an empty slot → create. `back` → login (drops the connection; the stored session's login then opens the realm list, the bar hidden from the click where the package's `select.back` is `realms`, RQ-112), also while the camera turns in the rotate mode (the path mode hides it then) but not while the start clip plays. Prev/next (the arrow buttons, LEFT, RIGHT) turns the camera one slot, the short way about `at` at 1.2 rad/s, to where 1097's check ends the turn (left to right: 1, 0, 2; nothing at the end of the row or while it turns; KO-FINDINGS §8.2); while it turns nothing is ticked and the spot is off. ESC presses `back`, `exit` or nothing, as the package says (RQ-116: `exit` for the 1097 choice, as 1264's select presses `bt_exit` for ESC; RQ-119: nothing for the 1298 recipe, as 1298's presses neither, RQ-117), in every state (not only at rest) but two: in the path mode while a path plays it skips the path, and while the start clip plays it does nothing, nor does a click on Exit (RQ-121: KO's select takes no input then, RQ-120). |
| create | KO's create screen; the create model breathing in `char_view` (standing, no weapon); name field; race and class shown, fixed (Q52) | `create_confirm` → `CreateCharacter` → `Characters` → select, the new character in front; a refusal in the message box in the server's wording, under the package's title for it (RQ-102); `back` → select. |
| loading | the loading art; `progress` by real stages: the package and its textures (loaded at start, 2/3), the first `World` (1); `version` shows the client version | the first `World` → in game after the bar shows full. No KO key or click acts, ESC included; the engine's F12 reconnect and the window close still do (RQ-122, KO-FINDINGS §9.11: 1264 reads no input while it loads and then gives ESC only to the main procedure's focused UI, so ESC neither asks nor quits). |

Failures show in KO's message box (the package's; Moradon's is 1264's
`el_messagebox_us.uif`): the Discord flow's failures (and the address to open when no
browser starts), a logout the realm refused, a server that cannot be reached after a login press,
a kick, a ban. Each shows in its spec 02/03 wording ("You were disconnected by an
operator…", "Your account is blocked until…") unless the package words that kind
of message (N3FE version 10, above), whose title and text then apply. A dropped
connection anywhere before the world returns to login with KO's text 1601,
"Disconnected from server" (KO-FINDINGS §1). Moradon's 1097 choice gives a banned
or unavailable login and an empty name KO's title and wording, so its ban shows
KO's blocked-account text with neither the ban's end nor its reason (the
maintainer approved it, 2026-11-02), and a refused create KO's title over the
server's wording (RQ-102, Q81); the panels keep the spec 02 wording.

Without `front-end.bin`, or without a Discord realm config, the client draws
today's panels; the play scripts and the suites use them.

### Player-facing tools (the demo leaves the player path)

| Tool | Today | After |
|---|---|---|
| `tools/local_release.py` | publishes `build/packages/demo` | publishes `build/packages/moradon`; refuses if it is missing ("run make realm-assets") |
| `tools/windows_kit.py` | `--package build/packages/demo` | defaults to `moradon` |
| `tools/local-realm` | builds and serves the demo package | serves `moradon`; refuses without it |
| `tests/release_smoke.py` | demo | unchanged: CI has no KO tree, so the smoke stays on a fixture. The front-end suite (below) covers the Moradon path. |
| README, `docs/manual-testing.md` | demo | Moradon; the steps L1–L4 and W2–W3 describe the KO screens |

The Moradon package is about 91 MB, which spec 04's limits allow. Publishing it in a
Release is publishing cooked KO assets, which spec 10 already allows; the raw tree
stays private.

## Failure modes

| Case | Behaviour |
|---|---|
| Package without `front_end` | Today's panels, unchanged. |
| `realm-config.json` names a client `front-ends.json` does not offer, or one whose input tree is missing, or either file is malformed | The cook stops before the survey with the reason and the file or input to fix (`content/front-end.md`, "Choosing the client"); nothing is written. |
| A choice's reference install is not a pinned one, its manifest is missing or names another installer, or a recipe prefix names no input (RQ-084) | The same, before anything is written. |
| A file the cook reads from a reference install differs from its manifest's hash | The cook stops with the file and the manifest named; nothing is published. |
| A front-end blob fails to load or validate | The client prints the error and falls back to the panels; it never refuses to start over the front end. `--self-test` fails instead, naming the blob. |
| A package cooked before N3FE version 17 (no music section, no clip blend times and spot rate, no track kinds and restart periods, no front-clip mode, no turn mode, no zone and fog, no logo section, no message section, no placement, no `login_closed` action, no select bar actions, no message box Yes and No or exit question, no select ESC or its `none`, or no select Back) | The server refuses it at start (`front end magic/version`); the client prints `front end version` and falls back to the panels. A Release ships the client, server and package together, so players never meet it; an operator or developer with an older local cook re-cooks it (`make realm-assets`) or installs the matching Release's package. |
| Window smaller than the canvas (1024 × 768) | KO's placements would cut the layouts off, so the UI scales down uniformly, centred, as with `ui_scale` `window` (RQ-106). No minimum beyond SDL's. |
| No mouse | The keyboard covers every action. |
| An account with more characters than slots (test realms) | The select screen shows the first `character_slots`; the rest stay in the database. Create is refused as today. |

## Security

- Nothing in the section is executable: bounded trees (depth 24, nodes 2048, as the HUD
  parser), bounded strings, textures within the HUD bounds; every bound is checked in
  the client loader as well as the cook.
- `text` overrides and character names are drawn as text, never interpreted.
- The front end changes no server authority. `character_slots` is package data the
  server reads from the revision, like the other rules.

## Build

- `tools/assetc/ko_front_end.py` and `make realm-assets` cook the section into
  `build/packages/moradon`. The cook is deterministic: the same tree gives the same
  bytes (the package hash covers it).
- The client front-end module lives in `client/render/front_end.h`. It draws with its
  own two small shader programs (the lit scene as Direct3D 9's fixed function, the UI
  quads) and skins the characters with the engine's `Scene`.
- The music decoder is minimp3 (CC0), vendored at a pinned commit in
  `client/third_party/minimp3/` (`UPSTREAM.md`, Q69).

## Acceptance tests

CPU (`make test`):

1. **Cook bounds** (`tests/front_end.py`). `ko_front_end` refuses truncated inputs,
   trees over the bounds, unknown actions, unbound required actions and missing
   screens, and music that is not whole Layer III frames of one format, a WAV that
   is not integer PCM within the rate and byte bounds, a restart period out of
   bounds, or that names an unknown screen or track. It works on synthetic UIF
   fixtures, synthetic MPEG frames and synthetic WAVs (original bytes). It refuses a
   select hall without a known front-clip mode (`hover` or `loop`, RQ-086), without a
   known turn mode (`rotate` or `path`), with paths in the rotate mode or a `turn_end`
   in the path mode, a path outside the slots or from a slot to itself, a pair twice,
   a missing entry path or way between neighbours, or a `.n3camera` that is truncated, has trailing
   bytes, or lacks its eye or at keys (RQ-087, synthetic camera files). It cooks a
   synthetic zone (RQ-095: terrain, an opaque, a blended and an unlit shape) into
   its meshes in hall space and refuses a hall with a zone, an unknown zone key, a
   zone with an extension file, a second tile layer or a part material other than
   the terrain's, and a fog the camera files disagree on or outside the path mode;
   `select.light_manager`'s lights replace the hall lights of their number, and
   the cook refuses a number twice or past 7, an unknown kind or key, colours
   past 0–1 and a point light's range or attenuation out of bounds.
   (The wrapped-UV
   `ka_login_intro_us.uif` is not an input: the 1098 intro scene replaced it.)
2. **Loader bounds** (`tests/front_end.py`, `tests/front_end.cpp`). The client loader
   refuses malformed blobs, each with its own message and no crash. The music stream
   (`tests/audio.cpp`) plays a synthetic track once and looping, resamples 32 kHz to
   48 kHz, ends a track that decodes to nothing, and the mixer keeps, replaces and
   stops it; a synthetic PCM track plays its samples once and looping, resampled from
   22,050 Hz, and a restart period starts a track again on time, ended or not
   (RQ-083). The select hall (`client/render/select_hall.h`, `tests/front_end.cpp`)
   plays both front-clip modes on synthetic clips: the hover mode's character in
   front by the pointer, the others still; the loop mode's front clip looping, the
   others' rest clip once, the spot and info without the pointer, the turn's rest
   clip on everyone (RQ-086). The path player (`client/render/select_path.h`) gives
   a path's last frame and its keys at a frame as 1298's `DataGet` does, takes a
   loaded path's two first steps, holds the last frame and skips to it; the loader
   refuses an unknown turn mode, paths in the rotate mode and every path bound
   (RQ-087). The zone helpers (`client/render/select_zone.h`) give D3D's linear
   fog factor and the blended meshes far to near; the loader refuses a hall with
   a zone, zone mesh flags other than lit or unlit with one of cut-zero or blend,
   more than 256 zone meshes, a zone one mesh past the vertex total (196,608) or
   the index total (589,824), a zone cut inside a mesh, and a fog out of its
   range or an off fog with values (RQ-095); the cook refuses a zone past its
   mesh, vertex or index bound. RQ-101: the cook writes a recipe's `logo` as its
   groups' fade-in, hold and fade-out (from KO's seconds and peak), its music and
   flags, and nothing without one, and refuses an unknown key, no group or more
   than 8, a group that is no group node, hidden or named twice, seconds out of
   bounds, a peak of 1 or less, a track past the tracks, a fade group without its
   fade or past the groups, an unknown skip or cursor, and a layout node other
   than a group, image or string; the loader refuses a logo flag other than 0 or
   1, a bound action, a node of another kind, 0 or 9 groups, a group that is not
   a group node or is named twice, group times out of bounds (negative, NaN, all
   0 or past 60 s), a delay past 60 s, a fade without a group or a track or of
   0, a fade group past the groups, unknown flags and truncation; the logo
   helpers (`client/render/front_logo.h`, `tests/front_end.cpp`) give 1264's
   12 s, each group's alpha in 255ths and the music from 1 s, faded over 4 s,
   and skip on a key stamped during the screen but not on one stamped before it
   or a modifier right after a focus gain (Q82). RQ-102: the cook writes a
   recipe's `messages` in the set's order, each title and text the recipe's
   string or a synthetic encrypted text table's row, and refuses an unknown
   message or key, an empty entry, a title without a `title` binding, a row the
   table lacks, a table of other columns, a row id that is not a positive
   integer, text outside printable ASCII or past 1024 bytes; the loader
   refuses more than 8 messages, one outside the set or named twice, a replace
   flag other than 0 or 1, a text that does not replace, a title or text out of
   bounds and truncation. RQ-106: the cook writes each layout's `place` and
   `moves` as rules that give 1264's placements (written independently in
   `tests/front_end.py`) at 1024×768, 1280×1024, 1600×1200 and an odd size,
   omits a hidden node's move, writes `ui_scale`, and refuses a bad placement,
   move key, value or count; the loader refuses placement flags other than 0
   or 1, a move of a node outside its layout or of an absent logo, a rule of
   another kind or out of bounds, a keep rule with values, more than 32 moves,
   moves that do not give the canvas rects and truncation, and places the
   nodes where 1264 does at those sizes (unscaled) and scaled with the flag or
   at 800×600. RQ-108: the cook refuses `login_closed` off the login screen and
   places a synthetic copyright line where 1264's SetVisibleLogInUIs does; the
   loader takes `login_closed` on the login and refuses it elsewhere and version
   11; the login states (`client/render/front_login.h`, `tests/front_end.cpp`)
   draw the login group at rest and the `login_closed` node instead while a
   login is under way and on the realm list; RQ-110: the login group is hidden
   while a login is under way whatever the layout binds, and the 1298 recipe
   hides `Text_Rights` and binds nothing to `login_closed` (`tests/front_end.py`).
   RQ-109: the cook takes a synthetic 1298 select bar with its info texts in place
   of `char_info` and places it as 1298's Load does (`{"bottom": 10}`), and refuses
   a select with no info text and a bar action off the select; the loader takes the
   bar and refuses version 12, a bar action off the select and a select with no
   info text, and puts the bar's nodes where 1298 puts them at each size; Create
   takes the slot in focus or the first empty one, or none, and Delete's box shows
   only for a character at rest (`client/render/select_bar.h`, `tests/front_end.cpp`);
   the 1298 recipe binds its bar as 1298 does.
3. **Fallback.** The demo package (no section) still draws the panels: the existing
   suites pass unchanged.
4. **Wire.** `golden-characters` with `level` is identical from both languages.
4a. **Client choice** (`tests/front_end_choice.py`, RQ-078). Moradon's
   `front-ends.json` is well formed, each recipe names the five screens, and its
   `realm-config.json` choice (1097) resolves to its recipe once its input tree
   exists. On synthetic packages the cook refuses a client the package does not
   offer (naming the ones it does), a choice whose input tree is missing (naming
   the tree and how to get it), a missing or malformed `realm-config.json`, an
   unknown key, and a malformed catalogue. RQ-084: a synthetic pinned install
   as a named second input resolves with its manifest; the cook refuses an
   unnamed or doubly named later input, a prefix naming no input, an unpinned
   or misplaced reference tree, and a missing, malformed or other installer's
   manifest; an install's file reads only when the manifest lists it as it
   is; a layout and its textures, and the turn sound with its sound-table row
   (CSV or encrypted), come from the input the recipe names
   (`tests/front_end.py` too); `ko_bake.package` refuses with nothing removed
   or written.

KO (`make live-ko`, needs `assets/ko`):

5. **Cook** (`tests/front_end_live.py`). Each client `front-ends.json` offers
   cooks twice with identical bytes and the client loader takes it; the chosen
   one's bytes are the package's; the section names every screen in the table.
6. **Captures** (`tests/front_end_live.py`). The test client renders each screen at 1024×768, 1280×1024 and
   1600×1200, the launcher's sizes (Q62), and the suite checks each capture: every
   screen is unscaled, and the login button, the realm list, the select's arrows,
   exit and back, the create name field, the loading bar and the message text are
   where 1264's code places them at that size (RQ-106, Q82, Q84); login shows the intro character in frame (its
   projected box is non-empty and covers the view's centre: KO's close-up runs past
   the frame's edges); the login button's rect has its
   art; the realms list shows the realm name; select shows 1, 2 and 3 characters in
   the slots; loading shows a progress bar that advances; the logo (RQ-101) draws
   each group's art in its rect and black elsewhere, half bright half way into
   the first fade-in, and gives way to the login after 12 s. Music: login and the realm
   list name one track, select and create another, loading none (1097's
   `bgm_login.wav`, which restarts at 21.66 s, and `bgm_el_battle.wav`, which loops,
   RQ-083), and each streams audibly past its end; the logo names a third,
   `bless.wav`, from 1 s with its 4 s fade from group 2, which plays once
   (RQ-101). The message box with a message the package titles differs from
   the same message untitled only at the title (its rect and the few pixels its
   glyphs stand past it; RQ-102). The login with a login under way (RQ-108)
   draws the copyright line, where 1264 places it at that size, and not the bar:
   it differs from the login at rest only within the bar and the line, and from
   the realm list only within the server group; the login group, the server
   group and the line draw in exactly their states. RQ-109: the 1298 recipe's cook,
   swapped into the chosen package, draws 1298's select bar unscaled at
   ((W − w) >> 1, H − 10 − h) at each size, its ten bound nodes where 1298's Load
   puts them, its art drawn, and its name, level and class texts filled for a
   character and empty with none. RQ-111: the 1298 recipe's Exit, clicked, asks in
   its centred box with Yes and No and without OK (an OK box the reverse), its
   frame drawing Yes and No where an OK box draws OK; ESC and No close it, ENTER,
   the keypad's ENTER and Yes leave, the hidden OK does nothing. RQ-115: the
   chosen package's (1097) Exit asks the same in 1264's box, checked the same
   way. RQ-116: ESC on the chosen package's select, pressed with the camera
   still and no character starting, asks the same question; RQ-119: on the 1298
   recipe's, pressed so, it does nothing. RQ-121: on each, with a character whose
   start clip ENTER has started, ESC and a click on Exit do nothing. RQ-112: a
   click on Back at rest is the Back command on each; the 1298 recipe's lands
   on the realm list, the chosen package's on the login.
7. **Flow** (`tests/front_end_flow_live.py`). Against a native server with the Discord
   stand-in (`tests/discord_standin.py`, as `discord_login_live.py`), the test client
   playing the screens with key and text events:
   - the logo first (RQ-101): its music 1 s in and the cursor hidden; a focus gain
     with a modifier right after it and a key stamped before the screen leave it
     (Q82), a click leaves it, SPACE skips it to the login, whose track replaces
     the logo's;
   - Discord login → realms → create a character (the name refusal path, then success)
     → select → start → loading → in world;
   - on select, with the pointer on the character in front, its clip blends in on its
     first frame, plays once and holds its last frame; off it, the rest clip blends
     back; the spot widens only while the pointer is on it and is off at 0; the info
     text shows only then (RQ-066, RQ-075); LEFT and RIGHT turn the camera one slot
     each way and back, the short way, each turn ending on the first frame past where
     1097's check ends it or back on the camera's own eye (RQ-067), each turn playing
     the turn sound (`front:select-turn`) once and LEFT at the end of the row none
     (RQ-077); ENTER then blends
     clip 1 in over 0.6 s on its first frame, under the full spot, before it plays
     (RQ-076);
   - a kick returns to login with the operator's wording;
   - the login bar shows at rest and after the denied Discord step, and the
     copyright line instead from each ENTER through the login and on the realm
     list (RQ-108);
   - the Discord failure and the kick show untitled, the name refusal under the
     package's create failure title in the server's wording (RQ-102, Q81);
   - `character_slots` refuses a fourth character.

Manual (`docs/manual-testing.md`, Linux and Windows):

8. The KO screens look and play like KO 1.298 for the login, server list, select and
   loading; record differences.

## Open questions

Q50–Q57, Q69, Q71, Q73, Q74, Q81, Q82 and Q84 in `QUESTIONS.md`.
