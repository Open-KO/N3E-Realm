# 11 — KO front-end: intro, login, server list, character select, loading

**Status: approved 2026-10-31** (the maintainer accepted Q50–Q56 as drafted); M4c implements it.

## Purpose

Players should start in Knight Online, not in a test panel. The client today opens on
a text box ("N3E / ADVENTURE", ACCOUNT, SELECT CHARACTER), drawn in code in
`client/render/play.h`. This spec replaces that, for the realm, with KO's own front
end, cooked from the pinned client tree (`assets/ko/`, spec 10, option C):

1. **Intro and login.** KO's login scene, with the orc and the axe under the moon, and
   the login bar, as KO draws it (Q61). Its Login button starts spec 02's Discord login.
2. **Server list.** KO's server group, with the realm as its one entry.
3. **Character select.** The Karus select hall in 3D, with up to three characters,
   rotated left and right as KO does, and the info bar (ID, level, class) with KO's
   left, right, Back and Exit buttons. As in KO, ENTER or a click on the character in
   front starts the game, and ENTER on an empty slot opens create; Delete is hidden
   (Q53).
4. **Character create.** KO's create screen, reduced to what the realm supports (Q52).
5. **Loading.** KO's Karus loading art, with a progress bar that tracks real work.

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
`games/moradon/front-end.json`; the engine knows none of them.

| Screen | Scene | UI layout (`UI_US/`) |
|---|---|---|
| Intro and login | `CGameProcLogIn_1098`'s: `Intro/Intro.N3Chr` (its joint, clip 0, parts and the axe plug), `Intro/0..2.N3Light` (2 is off), `Intro/Moon.dxt`, the camera from the source | `co_login_us.uif` (`Group_LogIn`, `Group_ServerList`) |
| Server list | the intro scene, still running | `co_login_us.uif` `Group_ServerList` |
| Character select | `ChrSelect/ka_chairs.n3shape`, `ka_light_0/1.n3light`, the Karus slots, spots and cameras of `CGameProcCharacterSelect::Init`; the Tuarek priest (`upc_ka_tu_pri.n3joint`, `upc_ka_at_wa.n3anim` clips 0, 1 and 2, `UPC_DefaultLooks`, the mace plug) | `ka_characterselect_us.uif` |
| Character create | the character in `area_character` | `Ka_CharacterCreate_us.uif` |
| Loading | none | `ka_loading_us.uif` |
| Message box | over any screen | `co_MsgBoxOk_us.uif` |

Music (Q57, RQ-018): KO 1298's front-end track, `Snd/Intro_Sound.mp3`, looping from
login through the realm list, select and create, stopped when the chosen character's
clip has played; its frames are carried as they are (Q69). Text is drawn with
Liberation Sans regular and bold for KO's Arial, at points × 96 / 72, baked as N3H9's
nameplate fonts are.

What the cook reuses: `ko_hud.parse()` for the UIF trees, `ko_hud.texture()` and the
character texture reader for NTF3, `ko_character.py` and `gltf.py` for the two
characters (N3SM with render runs for the intro, N3S1 for the select hall), and
`ko_appearance.read_plug()` for the plugs. New: strict `.n3light` and standalone
`.n3shape` readers (`tools/assetc/ko_front_end.py`).

## Interfaces

### Package file `front-end.bin` (normative)

An optional presentation file, N3FE version 4, engine 42 (so wire 30). Its layout,
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
  `char_view`, `class_desc`, `progress`, `version`, `info`, `message`, `ok`. The cook
  and the loader refuse an unknown action, an action bound twice in a screen and a
  screen whose required actions are unbound. Required per screen:
  - login: `login`, `exit`, `login_group`, `realm_group`, `realm_list`,
    `realm_connect` (`notice` is optional; the Moradon package has none, Q61);
  - select: `select_prev`, `select_next`, `back`, `exit`, `char_info`;
  - create: `create_confirm`, `back`, `name_field`, `char_view`;
  - loading: `progress`;
  - message: `message`, `ok`.
- **Strings.** `select_info`, `select_hint`, `class_name`, `class_desc`,
  `loading_info`, `version`; the client fills `{level}`, `{class}`, `{name}`,
  `{version}`.
- **Scenes.** The intro (camera, lights, the model with its clip and plugs, the moon
  as a screen quad) and the select hall (camera, lights, `character_slots` slots with
  their eye and spot light, the spot's growth rate, the hall meshes, the model with
  clips 0, 1 and 2 (hover, start, rest), plugs), each model clip with the time the
  client blends into it over (N3FE version 4, RQ-075; the record's, or the package's
  own for the start clip, RQ-076),
  and the create model (the race's own looks joint and animation, `ANI_BREATH`, no
  plugs; N3FE version 2).
- **Music** (N3FE version 3, RQ-018). Up to 4 tracks of MPEG-1 or MPEG-2 Layer III
  frames (each ≤ 16 MiB, every frame checked at load), and the track the login,
  select, create and loading screens play, or none. The client streams the track
  (one frame decoded at a time, `client/assets/music.h`); a screen naming the track
  already playing keeps it, so it runs on across the screens; entering the world
  stops it. Option.ini `[Sound] Effect=0` silences it with every other sound, as in
  KO 1298 (Q70). The screens have no other sounds: 1298 plays none there (Q70).
- **`text` overrides.** The format allows them; the Moradon package uses none: the
  login screen keeps KO's labels and copyright line (Q61, superseding Q56).
- **`hidden`.** The Moradon package keeps the login bar as KO draws it: `Edit_ID`,
  `Edit_PW`, `Btn_Option` and `Btn_Join` (Registration) are shown, unbound, so they
  take no input (Q60, Q61). It hides `Img_Daum` and `Img_MGame` (their texture is
  not in the pinned tree), `premium` and the three notice groups (KO's news panels,
  empty without KO's server), and the select screen's `bt_delete` (Q53).

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
in this order: scene, then the UI tree scaled uniformly from `canvas` to fit the
window (centred, the scene filling the rest), then the message box. The system cursor
stays. Mouse clicks and hover drive the button states; keyboard
works too (ENTER = the screen's primary action, ESC = back/cancel, arrows =
prev/next).

| State | Shows | Leaves on |
|---|---|---|
| login | intro scene looping; login bar | `login` (the Login button or ENTER) → the flow (spec 02, unchanged) → `LoginResult` → realms. A press while the client is still connecting is held and starts the flow once connected. A stored session skips the browser as today. |
| realms | intro; the server group with the realm's name from `realm.json` | `realm_connect` → select. The connection and login already exist; this is KO's step, kept (Q54). |
| select | hall; up to 3 characters with the realm's player model and default looks, each standing on clip 0's first frame; the one in front, at rest, plays clip 0 (`pre_select`) once while the pointer is in `DoProcPreselect`'s centre rect and holds its last frame, and clip 2 (`dummy`, clip 0's first frame) otherwise, each change blending over the clip's own blend time from the frame reached, the new clip held on its first frame meanwhile; the front slot's spot widens at the package's rate while the pointer is there, narrows when it leaves and is off at 0; the info text (char_info) shows only while the pointer is there. This is the 1097 client's hall for this asset set (KO-FINDINGS §8.1, Q71), not 1298's | At rest only (not while the camera turns or the start clip plays): ENTER or a click on the character in front (`PtInRect` on the centre rect) → `SelectCharacter`, the spot at its full theta, its clip 1 blended in over the package's start blend (Moradon: 1097's 0.6 s) on its first frame and played to the end (`IsAnimEnd`, after the blend), → loading; a refusal returns it to the hover or rest clip; ENTER on an empty slot → create; `back` → login (drops the connection). Prev/next turns the camera to the next slot (left to right: 1, 0, 2); while it turns nothing is ticked and the spot is off. |
| create | KO's create screen; the create model breathing in `char_view` (standing, no weapon); name field; race and class shown, fixed (Q52) | `create_confirm` → `CreateCharacter` → `Characters` → select, the new character in front; a refusal in the message box in the server's wording; `back` → select. |
| loading | the loading art; `progress` by real stages: the package and its textures (loaded at start, 2/3), the first `World` (1); `version` shows the client version | the first `World` → in game after the bar shows full. |

Failures keep their spec 02/03 wording and show in KO's message box
(`co_MsgBoxOk_us.uif`): the Discord flow's failures (and the address to open when no
browser starts), a server that cannot be reached after a login press,
"You were disconnected by an operator…", "Your account is blocked until…". A dropped
connection anywhere before the world returns to login with KO's text 1601,
"Disconnected from server" (KO-FINDINGS §1).

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
| A front-end blob fails to load or validate | The client prints the error and falls back to the panels; it never refuses to start over the front end. `--self-test` fails instead, naming the blob. |
| A package cooked before N3FE version 4 (no music section, or no clip blend times and spot rate) | The server refuses it at start (`front end magic/version`); the client prints `front end version` and falls back to the panels. A Release ships the client, server and package together, so players never meet it; an operator or developer with an older local cook re-cooks it (`make realm-assets`) or installs the matching Release's package. |
| Window smaller than the canvas | The UI scales down uniformly. No minimum beyond SDL's. |
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
   screens, and music that is not whole Layer III frames of one format or names an
   unknown screen or track. It works on synthetic UIF fixtures and synthetic MPEG
   frames (original bytes). (The wrapped-UV
   `ka_login_intro_us.uif` is not an input: the 1098 intro scene replaced it.)
2. **Loader bounds** (`tests/front_end.py`, `tests/front_end.cpp`). The client loader
   refuses malformed blobs, each with its own message and no crash. The music stream
   (`tests/audio.cpp`) plays a synthetic track once and looping, resamples 32 kHz to
   48 kHz, ends a track that decodes to nothing, and the mixer keeps, replaces and
   stops it.
3. **Fallback.** The demo package (no section) still draws the panels: the existing
   suites pass unchanged.
4. **Wire.** `golden-characters` with `level` is identical from both languages.

KO (`make live-ko`, needs `assets/ko`):

5. **Cook** (`tests/front_end_live.py`). The cook of the pinned tree succeeds twice with identical bytes; the
   section names every screen in the table.
6. **Captures** (`tests/front_end_live.py`). The test client renders each screen at 1280×800 and 1024×768, and
   the suite checks each capture: login shows the intro character in frame (its
   projected box is non-empty and covers the view's centre: KO's close-up runs past
   the frame's edges); the login button's rect has its
   art; the realms list shows the realm name; select shows 1, 2 and 3 characters in
   the slots; loading shows a progress bar that advances. Music: login, the realm
   list, select and create name KO's track, loading none, and the track streams
   audibly past its end.
7. **Flow** (`tests/front_end_flow_live.py`). Against a native server with the Discord
   stand-in (`tests/discord_standin.py`, as `discord_login_live.py`), the test client
   playing the screens with key and text events:
   - Discord login → realms → create a character (the name refusal path, then success)
     → select → start → loading → in world;
   - on select, with the pointer on the character in front, its clip blends in on its
     first frame, plays once and holds its last frame; off it, the rest clip blends
     back; the spot widens only while the pointer is on it and is off at 0; the info
     text shows only then (RQ-066, RQ-075); ENTER then blends clip 1 in over 0.6 s on
     its first frame, under the full spot, before it plays (RQ-076);
   - a kick returns to login with the operator's wording;
   - `character_slots` refuses a fourth character.

Manual (`docs/manual-testing.md`, Linux and Windows):

8. The KO screens look and play like KO 1.298 for the login, server list, select and
   loading; record differences.

## Open questions

Q50–Q57, Q69 and Q71 in `QUESTIONS.md`.
