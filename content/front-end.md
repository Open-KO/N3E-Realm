# Front end (N3FE, engine 42)

`front-end.bin` is an optional presentation file (spec 11): KO's 1098 login scene,
login and server list, the Karus character select hall, character create, loading
and the OK message box. `tools/assetc/ko_front_end.py` cooks it from the pinned
client tree with the choices in `games/moradon/front-end.json`; the client's
`load_front_end` (`client/assets/assets.cpp`) reads it and the server reads only
its header. A package with it is engine 42, so wire 30 (as engines 38–41). Its bound is
64 MiB (`FRONT_END_FILE`, `MAX_FRONT_END_ASSET`, `kFrontEndFile`), since it holds
two character models and the UI art.

Integers are little-endian u32, reals f32; strings are a u32 length and that many
bytes. Engine space is KO's with z negated (KO is left-handed).

## Layout

1. `"N3FE"`, version 1, character slots (1–3; the server's character limit),
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
   the character slots), the hall (part count ≤64, each a mesh), the model, its
   plugs.

- Camera: eye, at, up (engine space), vertical field of view (radians, (0, π)),
  near and far (0 < near < far ≤ 1000).
- Lights: a count (≤8), each type (1 point, 2 spot, 3 directional), diffuse,
  ambient, position, direction (3 reals each), range (0, 1e8], falloff,
  attenuation 0–2 (non-negative, sum above 0), theta, phi: D3DLIGHT9's fields.
  The client lights as Direct3D 9's fixed function does, without specular.
- Slot: position, yaw (radians, engine space), the camera eye that faces the
  slot (the scene camera's `at` and up apply), and the slot's spot light (one
  light record). The spot's theta is its value when the slot is chosen; it is
  0 otherwise (`CGameProcCharacterSelect::Tick`).
- Model: a byte length and an N3S1 or N3SM scene (`tools/assetc/gltf.py`, atlas
  up to 2048 a side), then a count of further clips and each clip's byte length
  and track list (N3S1's track encoding, on the model's nodes).
- Plug: the KO joint index (below the model's joint count), then a mesh in that
  joint's space: world = instance × `Scene::joint_matrix` × vertex.
- Mesh: texture, flags (1 double-sided, 2 alpha test at 0.5), material diffuse
  and ambient (3 reals each), a vertex count (1–65536) of 8 reals (position,
  normal, uv), an index count (a multiple of 3, ≤196608), the indices.

The loader refuses an unknown action, a screen missing one of its required
actions (login: `login`, `exit`, `login_group`, `realm_group`, `realm_list`,
`realm_connect`, `notice`; select: `select_prev`, `select_next`, `back`, `exit`,
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

- Login (`UI_US/co_login_us.uif`, centred on the bottom edge): the Login button,
  relabelled "Discord", starts spec 02's flow; Cancel exits. The ID and password
  fields and their labels stay, as KO draws them, unbound: they take no input
  (Q60). Hidden: Option, Registration, the MGAME and Daum logos, `premium` and the
  three notice groups. The bar's art has the four buttons
  painted in, so Option and Registration leave two blank buttons (Q58). Added:
  the `notice` line above the bar. `Text_Rights` reads "N3E Realm, a community
  project. Not affiliated with MGAME or Noahsystem." (Q56). The server group sits
  at the top of the canvas (`OpenServerList`).
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
  (`upc_ka_tu_pri.n3joint`, default looks, clips 0 and 1, the mace plug).
- Fonts: Liberation Sans regular and bold for Arial, at points × 96 / 72.
