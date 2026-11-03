"""The KO front end (spec 11): front-end.bin (N3FE, content/front-end.md).

KO's 1098 login scene (the orc with the axe under the moon, GameProcLogIn_1098),
its login and server-list layout, the Karus character select hall
(GameProcCharacterSelect), character create, loading and the OK message box,
cooked from the pinned client tree, (version 3) the screens' music, KO's
MP3 frames carried as they are, (version 4) each model clip's blend time
and the select spot's growth rate, and (version 5) PCM music tracks from KO's
WAVs and a track's restart period, (version 6) the select hall's
front-clip mode, (version 7) the select camera's turn mode with 1298's
recorded camera paths, (version 8) a KO zone drawn as the select hall
(1298's `karus_intro`) and the select camera's fog, and (version 9) a logo
screen before the login (1264's "K2 Network presents Knight Online", RQ-101),
present or absent as the recipe's `logo` says, and (version 10) each message
box message's title and wording (RQ-102, Q81), from the recipe's `messages`:
a KO text-table row or the recipe's own string, and (version 11) where each
layout's nodes go at a window's own size, as KO's UI code places them by the
viewport (RQ-106, Q82), (version 12) the action `login_closed`, a node
drawn only while the login group is not (1264's SetVisibleLogInUIs, RQ-108),
(version 13) 1298's select bar's actions, its start, create and delete
buttons and its three info texts, with two messages (RQ-109), and (version
14) the message box's yes and no buttons, with the message exit_confirm, the
select's exit asked yes or no as 1298 asks it (RQ-111).
games/moradon/front-end.json names every KO
file, binding, override and placement; this module knows the KO formats and the
reference client's placement and drawing rules, and no realm choice. Fonts are
local substitutes (Liberation Sans for Arial, as ko_nameplates).

The recipe's KO paths read from the choice's input trees (`Inputs`, RQ-084):
`<name>:<path>` from the input front-ends.json names so, any other path from
the first input. A file a KO file names (a character's parts and plugs, a
layout's or a hall's textures, a looks row's files) is read from the tree its
referrer came from.
"""
import csv
import hashlib
import io
import json
import math
import pathlib
import struct
import wave

from common import count, f, load, string, u, vector
import front_end_choice
import gltf
import ko
import ko_appearance
import ko_character as character
import ko_hud
import ko_nameplates
import ko_scene

VERSION = 15
# The rate KO's frame-scaled code is written for: its per-frame steps are
# scaled by 30 / s_fFrmPerSec (source: GameProcCharacterSelect.cpp's fade,
# N3Pond.cpp). The select spot's per-tick step (1097 binary: 0043f280 adds
# 0.02, Karus, or 0.015, El Morad, every tick) is cooked as a rate at it.
TICKS_PER_SECOND = 30
# A clip's blend time (__AnimData::fTimeBlend, seconds), as the client bounds it.
MAX_BLEND = 10.0
# The select model's clips by role (version 4): the front clip, the start
# clip and the rest clip. In the hover mode (1097: DoProcPreselect 0043f280,
# the select 0043ea30) they are pre_select, selected and dummy; in the loop
# mode (1298: 005fef90, 005fe7c0) 1298's clips 1, 2 and 0.
SELECT_CLIPS = 3
START_CLIP = 1
# The select hall's front-clip mode (version 6, `select.front_clip`): what the
# character in front plays at rest. `hover`, 1097's (0043f280): the front clip
# once while the pointer is in the centre rect, the rest clip otherwise, the
# others not ticked. `loop`, 1298's (005fef90): the front clip looping
# whatever the pointer does, the rest clip once on the others.
FRONT_CLIP = {"hover": 0, "loop": 1}
# The select camera's turn mode (version 7, `select.turn`): `rotate`, 1097's
# (0043e4e0): the eye turns about `at` to each slot's `turn_end`; `path`,
# 1298's (005fa670, 005fe5b0): it plays the recorded camera path the recipe
# names for the turn (`select.paths`), and an entry path into slot 0 as the
# hall opens.
TURN = {"rotate": 0, "path": 1}
# What ESC presses on the select at rest (version 15, `select.escape`, RQ-116):
# `back`, the realm's (the default), or `exit`, 1264's: its select's OnKeyPress
# (004454e0) sends DIK_ESCAPE to ReceiveMessage as a click on bt_exit, so ESC
# asks the exit question as the Exit button does (specs/KO-FINDINGS.md 9.8).
ESCAPE = {"back": 0, "exit": 1}
# A path's bounds (the client's): paths per package, keys per set, keys a second.
MAX_PATHS = 8
MAX_PATH_KEYS = 4096
ENTRY = 0xFFFFFFFF
# __CameraData as 1298's CN3Camera::Load reads it (00439540: 0x16c bytes).
CAMERA_DATA = 0x16C
# ANI_BREATH (GameDef.h): the idle InventoryChrAnimationInitialize plays.
BREATH = 0
CANVAS = (1024, 768)
SCREENS = ("login", "select", "create", "loading", "message")
KINDS = {"image": 0, "text": 1, "button": 2, "edit": 3, "progress": 4, "group": 5, "area": 6, "list": 7}
# The UIF node types (CN3UIBase) the front-end layouts use; any other refuses.
UIF_KINDS = {0: "group", 1: "button", 3: "progress", 4: "image", 6: "text", 8: "edit", 9: "area", 14: "list"}
# The engine's closed action set (spec 11); the client gives each its behaviour.
# `title` is version 10's (RQ-102), `login_closed` version 12's (RQ-108): a
# login screen node drawn only while the login group is not (a login waiting
# for its answer, and the realm list), as 1264's SetVisibleLogInUIs (005c2820)
# shows Text_Rights.
ACTIONS = ("", "login", "exit", "login_group", "realm_group", "realm_list", "realm_connect", "notice",
           "select_prev", "select_next", "back", "char_info", "create_confirm", "name_field", "char_view",
           "class_desc", "progress", "version", "info", "message", "ok", "title", "login_closed",
           "select_start", "select_create", "select_delete", "char_name", "char_level", "char_class",
           "yes", "no")
# Version 13 (RQ-109, specs/KO-FINDINGS.md 9.6): 1298's select bar
# (co_CharacterSelect_us.uif, its ReceiveMessage 00607160): `select_start`
# (btn_start, 005ff870: the centre click's start), `select_create` (btn_create,
# 005ff920: create in the first empty slot, or KO's message when there is
# none), `select_delete` (btn_delete: KO's "deletion disabled" message for a
# character at rest) and the info texts its 006074c0 fills: `char_name`
# (str_id), `char_level` (str_lev, "%d") and `char_class` (str_job).
SELECT_ONLY = ("select_start", "select_create", "select_delete", "char_name", "char_level", "char_class")
# Version 14 (RQ-111, specs/KO-FINDINGS.md 9.7): the message box's Btn_Yes and
# Btn_No (1298's CUIMessageBox, shown for an MB_YESNO box by SetBoxStyle
# 00527a40), which the client shows for the yes/no message exit_confirm only.
MESSAGE_ONLY = ("yes", "no")
# Actions bound on one screen only (the others never draw or use them).
ONLY_ON = {"login_closed": "login", **{a: "select" for a in SELECT_ONLY}, **{a: "message" for a in MESSAGE_ONLY}}
# The select's info text: 1097's and 1264's one text00 (char_info), or any of
# 1298's three (version 13); a select layout binds at least one.
INFO_TEXTS = {"char_info", "char_name", "char_level", "char_class"}
REQUIRED = {"login": {"login", "exit", "login_group", "realm_group", "realm_list", "realm_connect"},
            "select": {"select_prev", "select_next", "back", "exit"},
            "create": {"create_confirm", "back", "name_field", "char_view"},
            "loading": {"progress"},
            "message": {"message", "ok"}}
# The client's strings, in file order. {level}, {class}, {name} and {version}
# are the only substitutions the client makes.
STRINGS = ("select_info", "select_hint", "class_name", "class_desc", "loading_info", "version")
# Node flags.
FIXED_ON, FIXED_DISABLED, FOREGROUND = 1, 2, 4
STATES = {"on": FIXED_ON, "disabled": FIXED_DISABLED}
# Mesh flags. A zone mesh (version 8) takes UNLIT, and one of CUT_ZERO (opaque,
# cut where its texel's alpha is 0) or BLEND (source alpha over its inverse,
# drawn after the UI far to near).
DOUBLE_SIDED, ALPHA_TEST, UNLIT, BLEND, CUT_ZERO = 1, 2, 4, 8, 16
# Light types (D3DLIGHTTYPE).
POINT, SPOT, DIRECTIONAL = 1, 2, 3
MAX_NODES = 1024
# Version 8 (RQ-095): 256, as a zone hall brings its tile and object textures.
MAX_TEXTURES = 256
MAX_FONTS = 8
MAX_TEXT = 1024
MAX_FILE = 64 * 1024 * 1024
# The logo screen (version 9, RQ-101; 1264's logo procedure, Init 005fa500 and
# Tick 005fa7c0, its UI's Load 00601140, Tick 00601360, Render 00600ce0 and
# OnKeyPress 00601480). Its layout draws groups, images and strings and binds
# no action. Each listed group shows alone in turn: KO's tick raises a fade
# value by the frame time over the group's `seconds` up to `peak`, then lowers
# it the same way until it is below 0, and Render draws the UI with the value,
# clamped to 1, as its alpha; so a group fades in over `seconds`, holds for
# 2 (peak - 1) `seconds` and fades out over `seconds`. The music starts
# `delay` seconds after the screen does and fades out over `fade` seconds
# from the start of group `fade_group`. `skip` "key": a key press ends the
# screen; `cursor` "hidden": the system cursor is hidden while it shows.
LOGO_KEYS = {"ui", "place", "moves", "hidden", "groups", "peak", "music", "skip", "cursor"}
LOGO_KINDS = {"group", "image", "text"}
MAX_LOGO_GROUPS = 8
MAX_LOGO_SECONDS = 60.0
NO_GROUP = 0xFFFFFFFF
LOGO_SKIP_KEY, LOGO_HIDE_CURSOR = 1, 2
# The placement (version 11, RQ-106, Q82). KO draws its UI on the screen's own
# pixels, never scaled: the device viewport is the back buffer (1264:
# 004223c0), and each layout's Load or its procedure's Init places its root and
# some nodes by the viewport's width and height every time it loads
# (CGameProcLogIn_1098::Init, CUICharacterSelect::Load, CUICharacterCreate::Load,
# CUILoading::Load, MessageBoxPost; specs/KO-FINDINGS.md 9.3). A move puts a
# node's top-left, its subtree with it (MoveOffset), by one rule per axis over
# the window's extent S on that axis: KEEP leaves it where the earlier moves put
# it; LINEAR is trunc(a S + c); HALF is trunc(floor(S / 2) + a S + c), KO's
# (S >> 1) + ... (1264's select arrows). trunc is C's cast toward zero. The
# canvas rects are the moves at CANVAS; the client applies them at its window.
KEEP, LINEAR, HALF = 0, 1, 2
MAX_MOVES = 32
MAX_MOVE_SCALE = 4.0
MAX_MOVE_OFFSET = 16384.0
MOVE_KEYS = {"node", "x", "y", "bottom", "above"}
# The recipe's `ui_scale` (version 11's flags): `native`, KO's (absent), or
# `window`, the realm's own uniform scaling of the canvas to fit the window
# (RQ-103's realm-owner option).
UI_SCALE = {"native": 0, "window": 1}
# The messages the client raises in its message box (version 10, RQ-102,
# Q81), the engine's closed set (client/assets/assets.h FrontMessage) in index
# order. The recipe's `messages` words any of them: a `title` (drawn by the
# message screen's node bound to `title`) and a `text` replacing the client's
# own wording, each a string or a KO text-table row ({"table", "row"}).
MESSAGES = ("connect_failed", "disconnected", "login", "login_blocked", "login_unavailable", "create_name",
            "create_refused", "select_refused", "create_full", "delete_disabled", "exit_confirm")
# A KO text table's columns (Data/Texts_us.tbl: the row id and its text; the
# 1264 and 1298 clients' tables have these types).
TEXT_TYPES = [6, 7]
# Music (version 3, RQ-018): the client's bounds (client/assets/music.h).
MAX_TRACKS = 4
MAX_TRACK_BYTES = 16 * 1024 * 1024
NO_MUSIC = 0xFFFFFFFF
# Version 5 (RQ-083): a track's kind, a PCM track's rate bounds (as ko_audio's
# WAVs) and a restart period's bounds in seconds (0: none).
MPEG, PCM = 0, 1
PCM_RATES = (8000, 96000)
RESTART = (0.1, 3600.0)
# The screens a track is named for, in file order (login includes the realm list).
MUSIC_SCREENS = ("login", "select", "create", "loading")
# ISO/IEC 11172-3 and 13818-3 Layer III bitrates (kbit/s) and MPEG-1 rates (Hz).
MPEG1_KBPS = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
MPEG2_KBPS = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
MPEG1_HZ = (44100, 48000, 32000)


class Inputs:
    """The front end's input trees in front-ends.json's order, each a
    `ko_character.Assets` (or a stand-in with `get`), and the names a recipe
    path's prefix gives them (`front_end_choice.split`). `get` reads a recipe
    path from its tree; `split` gives the tree and the path within it, for a
    read whose further files come from the same tree."""

    def __init__(self, trees, names=None):
        self.trees = list(trees)
        if not self.trees:
            raise ValueError("front-end inputs: none")
        names = list(names) if names is not None else [None] * len(self.trees)
        if len(names) != len(self.trees) or None in names[1:]:
            raise ValueError("front-end inputs: a name for each tree after the first")
        self.names = names
        self.by_name = {n: t for n, t in zip(names, self.trees) if n is not None}

    def split(self, path):
        if type(path) is not str:
            raise ValueError("front-end path %r: a string" % (path,))
        name, rest = front_end_choice.split(path)
        if name is None:
            return self.trees[0], path
        if name not in self.by_name:
            raise ValueError("front-end path %r: no input named %r (%s)"
                             % (path, name, ", ".join(sorted(self.by_name)) or "the inputs have no names"))
        return self.by_name[name], rest

    def get(self, path):
        tree, rest = self.split(path)
        return tree.get(rest)

    def unique(self):
        """The trees, each once, with the label its sources carry: none for
        the first, `<name>:` for any other."""
        seen, out = set(), []
        for at, (tree, name) in enumerate(zip(self.trees, self.names)):
            if id(tree) not in seen:
                seen.add(id(tree))
                out.append((tree, "" if at == 0 else name + front_end_choice.PREFIX))
        return out

    @property
    def sources(self):
        merged = {}
        for tree, label in self.unique():
            merged.update({label + k: v for k, v in tree.sources.items()})
        return merged


def split(assets, path):
    """(tree, path within it) of a recipe path: through `Inputs`, or as it is
    for a single tree."""
    return assets.split(path) if isinstance(assets, Inputs) else (assets, path)


def inputs(front, reuse=None):
    """The `Inputs` of `front_end_choice.resolve`'s result: an Assets for each
    tree, a reference install's checked against its installer's manifest
    (`ko_installs`). `reuse` maps a resolved root to an Assets already reading
    it (the player's, so the provenance is shared), for a tree that is no
    reference install."""
    reuse = reuse or {}
    trees = []
    for tree, pin in zip(front["inputs"], front["pins"]):
        root = pathlib.Path(tree).resolve()
        trees.append(reuse[root] if pin is None and root in reuse else character.Assets(root, manifest=pin))
    return Inputs(trees, front["names"])


def recipe_paths(config):
    """(where, path) of every KO path a recipe names, for a check of their
    tree prefixes before the cook (front_end_choice.resolve). Reads what is
    there; the cook refuses what is missing or malformed."""
    out = []

    def add(where, value):
        if type(value) is str:
            out.append((where, value))

    def each(where, values):
        for at, value in enumerate(values if type(values) is list else []):
            add("%s[%d]" % (where, at), value)

    section = lambda value: value if type(value) is dict else {}
    for name, spec in section(config.get("screens")).items():
        add("screens.%s.ui" % name, section(spec).get("ui"))
    intro = section(config.get("intro"))
    add("intro.character", intro.get("character"))
    each("intro.lights", intro.get("lights"))
    add("intro.backdrop.texture", section(intro.get("backdrop")).get("texture"))
    select = section(config.get("select"))
    each("select.lights", select.get("lights"))
    add("select.hall", select.get("hall"))
    paths = select.get("paths")
    for at, path in enumerate(paths if type(paths) is list else []):
        add("select.paths[%d].path" % at, section(path).get("path"))
    add("select.turn_sound", select.get("turn_sound"))
    look = section(select.get("character"))
    add("select.character.joint", look.get("joint"))
    add("select.character.animation", look.get("animation"))
    each("select.character.plugs", look.get("plugs"))
    tracks = section(config.get("music")).get("tracks")
    for at, track in enumerate(tracks if type(tracks) is list else []):
        add("music.tracks[%d].path" % at, section(track).get("path"))
    add("logo.ui", section(config.get("logo")).get("ui"))
    for kind, entry in section(config.get("messages")).items():
        for key in ("title", "text"):
            add("messages.%s.%s.table" % (kind, key), section(section(entry).get(key)).get("table"))
    return out


# sound.tbl's columns as the front end reads them: id, file, max at once
# (the pinned tree's CSV; a client's encrypted table, ko_tbl, has the types
# u32, string, i32, i32, as 1097's and 1298's do).
SOUND_TYPES = [6, 7, 5, 5]


def sound_row(tree, ident):
    """(file, max at once) of one sound.tbl row of a tree: the pinned tree's
    `Data/sound.tbl.csv`, or the client's own encrypted `Data/sound.tbl`."""
    if tree.has("Data/sound.tbl.csv"):
        rows = [r for r in csv.reader(io.StringIO(tree.get("Data/sound.tbl.csv").decode("utf-8-sig")))
                if r and r[0].isdigit()]
        rows = [(int(r[0]), r[1], int(r[3])) for r in rows]
    else:
        import ko_tbl
        types, table = ko_tbl.parse(ko_tbl.decrypt(tree.get("Data/sound.tbl")))
        if types[:4] != SOUND_TYPES:
            raise ValueError("front-end sound.tbl columns %s" % types[:4])
        rows = [(r[0], r[1], r[3]) for r in table]
    found = [r for r in rows if r[0] == ident]
    if len(found) != 1:
        raise ValueError("front-end sound %d: %d sound.tbl rows" % (ident, len(found)))
    return found[0][1], found[0][2]


def sounds(config, assets, audio):
    """The audio.bin sounds the recipe names, by key, for `ko_audio.cook`'s
    `extra`: `select.turn_sound` (RQ-077), a sound.tbl id, `<name>:<id>` for
    another input's table. A sound of the tree `audio` reads is its id, as
    before; another tree's is that tree's row: dict(assets, path, maximum,
    input)."""
    out = {}
    value = config["select"].get("turn_sound")
    if value is None:
        return out
    first = assets.trees[0] if isinstance(assets, Inputs) else assets
    tree, ident = split(assets, value) if type(value) is str else (first, value)
    if type(ident) is str:
        ident = int(ident) if ident.isascii() and ident.isdigit() else None
    if type(ident) is not int or ident <= 0:
        raise ValueError("front-end select.turn_sound: a sound.tbl id, or <input>:<id>")
    if tree is audio:
        out["front:select-turn"] = ident
    else:
        path, maximum = sound_row(tree, ident)
        name = front_end_choice.split(value)[0] if type(value) is str else None
        out["front:select-turn"] = dict(assets=tree, path=path, maximum=min(16, max(1, maximum)), input=name)
    return out


def texture(data):
    """(width, height, RGBA) of an NTF3 texture: DXT1/DXT3 with a mip chain
    (ko_character.texture) or without one (the moon, the loading art), or the
    UI's 16-bit and ARGB forms (ko_hud.texture)."""
    r = character.Reader(data)
    r.string()
    if r.take(4) != b"NTF\x03":
        raise ValueError("front-end texture: NTF3 only")
    w, h, fmt, mips = r.unpack("4i")
    if fmt not in character.FORMATS:
        return ko_hud.texture(data)
    if mips:
        return character.texture(data, 1024)
    if any(not 4 <= n <= 1024 or n & (n - 1) for n in (w, h)):
        raise ValueError("front-end texture dimensions")
    decode, block = character.FORMATS[fmt]
    base = r.take(w * h * block // 16)
    # Without a mip chain a texture of 512 or more carries one half-size
    # 16-bit copy (the moon: 512 x 512 DXT1 then 256 x 256 x 2 bytes) for
    # cards without DXT; skipped, as ko_hud skips it.
    if w >= 512:
        r.take((w // 2) * (h // 2) * 2)
    r.end()
    return w, h, decode(base, w, h)


def chr_file(data):
    """An .n3chr as the 1098 login reads it (CN3Chr::Load): the transform, two
    collision names, the joint, the parts, the plugs, the clip table and the
    split. The intro's file ends there (no FX or collision-skin names) and
    carries 19 parts and one plug, past ko_character.character()'s player
    bounds."""
    r = character.Reader(data)
    t = character.transform(r)
    if t["translation"] != [0, 0, 0] or t["rotation"] != [0, 0, 0, 1] or any(t["keys"]):
        raise ValueError("front-end character transform")
    if any([r.string(), r.string()]):
        raise ValueError("front-end character collision")
    joint = r.string()
    parts = [r.string() for _ in range(count(r.integer(), 32))]
    plugs = [r.string() for _ in range(count(r.integer(), 4, 0))]
    animation = r.string()
    if r.unpack("4i") != [-1] * 4:
        raise ValueError("front-end character split animation")
    r.end()
    return dict(joint=joint, parts=parts, plugs=plugs, animation=animation)


def scene_tracks(data):
    """(head, tracks, tail) of a cooked N3SM scene (gltf.cook): a further clip
    of the same model is carried as its tracks alone."""
    at = 4
    w, h = struct.unpack_from("<2I", data, at)
    # N3S1's atlas is RGB, N3SM's RGBA; nodes are 44 bytes, joints 68.
    at += 8 + w * h * (4 if data[:4] == b"N3SM" else 3)
    at += 4 + struct.unpack_from("<I", data, at)[0] * 44
    at += 4 + struct.unpack_from("<I", data, at)[0] * 68
    start = at
    tracks = struct.unpack_from("<I", data, at)[0]
    at += 4
    for _ in range(tracks):
        keys = struct.unpack_from("<3I", data, at)[2]
        at += 12 + keys * 20
    return data[:start], data[start:at], data[at:]


def reflect(v):
    return [v[0], v[1], -v[2]]


def light(assets, name):
    """An .n3light (CN3Light::Load): a transform, D3DLIGHT9, bOn and the light
    number. Engine space reflects z."""
    r = character.Reader(assets.get(name))
    if any(character.transform(r)["keys"]):
        raise ValueError("animated front-end light")
    kind = r.integer()
    diffuse, _specular, ambient = r.floats(4), r.floats(4), r.floats(4)
    position, direction = r.floats(3), r.floats(3)
    # Range is unclamped (the intro's point lights carry 1e6 and 1e7).
    rng, falloff, a0, a1, a2, theta, phi = r.unpack("7f")
    if not all(math.isfinite(v) for v in (rng, falloff, a0, a1, a2, theta, phi)):
        raise ValueError("front-end light values")
    on, number = r.unpack("2i")
    r.end()
    if kind not in (POINT, SPOT, DIRECTIONAL) or not 0 <= number < 8:
        raise ValueError("front-end light type")
    return dict(on=bool(on), number=number, kind=kind, diffuse=diffuse[:3], ambient=ambient[:3],
                position=reflect(position), direction=reflect(direction),
                range=rng, falloff=falloff, attenuation=[a0, a1, a2], theta=theta, phi=phi)


def light_record(l):
    if not 0 < l["range"] <= 1e8 or sum(l["attenuation"]) <= 0 or min(l["attenuation"]) < 0:
        raise ValueError("front-end light range/attenuation")
    return u(l["kind"]) + f(l["diffuse"] + l["ambient"] + l["position"] + l["direction"] +
                            [l["range"], l["falloff"]] + l["attenuation"] + [l["theta"], l["phi"]])


MANAGER_LIGHT_KINDS = {"point": POINT, "directional": DIRECTIONAL}
MANAGER_LIGHT_KEYS = {
    "point": {"number", "kind", "diffuse", "ambient", "position", "range", "falloff", "attenuation"},
    "directional": {"number", "kind", "diffuse", "ambient", "direction"},
}


def manager_lights(values):
    """`select.light_manager` (version 8 recipes, RQ-095): the lights a client's
    light manager applies after the hall's on every select tick, each in the
    D3D light of its `number`, so replacing a hall light of that number. 1298:
    the select Init (005f98c0) resets its CLightMgr (vtable 006a872c, Release
    005ba7a0: two directional lights and a point light) and the select tick
    (005faf10) applies the two hall lights and then the manager's (005baae0).
    Each is D3DLIGHT9's values in KO space, a point or a directional light.
    A directional light's range and attenuation, which D3D ignores, are
    written as 1 and (1, 0, 0), within the record's bounds."""
    if not isinstance(values, list) or len(values) > 8:
        raise ValueError("front-end select.light_manager: a list of at most 8 lights")
    out, numbers = [], set()
    for value in values:
        kind = value.get("kind") if isinstance(value, dict) else None
        if type(kind) is not str or kind not in MANAGER_LIGHT_KINDS or set(value) != MANAGER_LIGHT_KEYS[kind]:
            raise ValueError("front-end select.light_manager: a point light (%s) or a directional light (%s)"
                             % tuple(", ".join(sorted(MANAGER_LIGHT_KEYS[k])) for k in ("point", "directional")))
        number = value["number"]
        if type(number) is not int or not 0 <= number < 8 or number in numbers:
            raise ValueError("front-end select.light_manager: light numbers 0 to 7, each once")
        numbers.add(number)
        colours = [vector(value[k], 3) for k in ("diffuse", "ambient")]
        if not all(0 <= c <= 1 for colour in colours for c in colour):
            raise ValueError("front-end select.light_manager: colours 0 to 1")
        if kind == "directional":
            direction = vector(value["direction"], 3)
            if not any(direction):
                raise ValueError("front-end select.light_manager: a directional light without a direction")
            out.append(dict(on=True, number=number, kind=DIRECTIONAL, diffuse=colours[0], ambient=colours[1],
                            position=[0, 0, 0], direction=reflect(direction), range=1.0, falloff=0.0,
                            attenuation=[1.0, 0, 0], theta=0.0, phi=0.0))
        else:
            rng, falloff = vector([value["range"], value["falloff"]], 2)
            out.append(dict(on=True, number=number, kind=POINT, diffuse=colours[0], ambient=colours[1],
                            position=reflect(vector(value["position"], 3)), direction=[0, 0, 0],
                            range=float(rng), falloff=float(falloff),
                            attenuation=vector(value["attenuation"], 3), theta=0.0, phi=0.0))
    return out


def lights(assets, names, manager=None):
    """The lights a scene applies; CN3Light::Apply enables only a light that
    is on. With `manager` (`manager_lights`), the D3D lights as the select
    tick leaves them: the scene's, then the manager's, each the last applied
    to its number, by number."""
    on = [l for l in (light(assets, n) for n in names) if l["on"]]
    if manager is not None:
        applied = {}
        for l in (light(assets, n) for n in names):
            applied.pop(l["number"], None)
            if l["on"]:
                applied[l["number"]] = l
        for l in manager_lights(manager):
            applied[l["number"]] = l
        on = [applied[n] for n in sorted(applied)]
    return u(count(len(on), 8, 0)) + b"".join(light_record(l) for l in on)


def camera_record(camera):
    """Eye, at, up (engine space), vertical FOV in radians, near and far."""
    eye, at = vector(camera["eye"], 3), vector(camera["at"], 3)
    if not 0 < camera["fov"] < math.pi or not 0 < camera["near"] < camera["far"] <= 1000:
        raise ValueError("front-end camera")
    return f(reflect(eye) + reflect(at) + [0, 1, 0, camera["fov"], camera["near"], camera["far"]])


class Textures:
    def __init__(self, assets):
        self.assets, self.list, self.index = assets, [], {}

    def add(self, name, tree=None):
        """The texture `name` names in `tree`, or, for a recipe path, in its
        input's tree (`split`); each file once."""
        if tree is None:
            tree, name = split(self.assets, name)
        key = (id(tree), name.replace("\\", "/").casefold())
        if key not in self.index:
            self.index[key] = self.raw(*texture(tree.get(name)))
        return self.index[key]

    def raw(self, w, h, rgba):
        self.list.append((w, h, rgba))
        if len(self.list) > MAX_TEXTURES:
            raise ValueError("front-end texture count")
        return len(self.list) - 1

    def masked(self, index):
        """Whether the texture has texels the alpha test drops (KO draws its
        shapes and plugs with alpha test at reference 0x80)."""
        return any(a < 0x80 for a in self.list[index][2][3::4])


def mesh_record(vertices, indices, tex, flags, diffuse, ambient):
    count(len(vertices), 65536)
    count(len(indices), 3 * 65536, 3)
    if len(indices) % 3 or max(indices) >= len(vertices):
        raise ValueError("front-end mesh indices")
    out = u(tex) + u(flags) + f(list(diffuse) + list(ambient)) + u(len(vertices))
    out += b"".join(f(v) for v in vertices)
    return out + u(len(indices)) + struct.pack("<%dI" % len(indices), *indices)


def mesh_file(assets, name):
    return ko.import_mesh(pathlib.Path(name.replace("\\", "/")), 1.0, data=assets.get(name))


def plug_record(assets, textures, name):
    """A plug in its joint's space (CN3CPlugBase::ReCalcMatrix: scale,
    rotation, position x scale; Render: plug x joint x character), engine
    space, after its joint index. Its mesh and texture are its tree's."""
    assets, name = split(assets, name)
    plug = ko_appearance.read_plug(assets, name)
    if min(plug["scale"]) <= 0 or plug["material"][20] != 0:
        raise ValueError("front-end plug scale/render state")
    mesh = mesh_file(assets, plug["mesh"])
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    move, _ = ko_appearance.plug_transform(plug, identity, 1.8)
    vertices = [move(v[:3], True) + move(v[3:6], False) + list(v[6:8]) for v in mesh["vertices"]]
    tex = textures.add(plug["texture"], assets)
    material = plug["material"]
    return u(count(plug["stored_joint"], 63, 0)) + mesh_record(
        vertices, mesh["indices"], tex, ALPHA_TEST if textures.masked(tex) else 0, material[:3], material[4:7])


def model(assets, source, definition, clips, work, own_blends=None):
    """A character for the front end (ko_character.convert's front-end
    switch): the first clip's N3SM, then each further clip's tracks, each
    length-prefixed, then (version 4) each clip's blend time: the time the
    client blends into the clip over. That is the clip record's fTimeBlend,
    which CN3Chr::AniCurSet takes when the caller names no time of its own
    (FLT_MIN; 1097 binary: 00447e30 reads the record's +0x2c), or, where
    own_blends names one for the clip's position, the caller's own."""
    table = character.animations(assets.get(definition["animation"]), unused_word=True)
    blends = []
    for at, clip in enumerate(clips):
        if not 0 <= clip < len(table):
            raise ValueError("front-end clip %d past the table's %d clips" % (clip, len(table)))
        blend = table[clip]["blend_seconds"]
        if own_blends and own_blends.get(at) is not None:
            blend = own_blends[at]
        if not (isinstance(blend, (int, float)) and math.isfinite(blend) and 0 <= blend <= MAX_BLEND):
            raise ValueError("front-end clip blend time")
        blends.append(blend)
    blobs = []
    for clip in clips:
        target = (work / ("clip-%d" % clip)).resolve()
        character.convert(assets.root, source, target, clip, 1.0,
                          definition=dict(definition, name="front-end", collision=[], split=[-1] * 4, extras=[]),
                          player=False, assets=assets, front_end=True)
        meta = json.loads((target / "scene.json").read_text())
        scene, _ = gltf.cook(target, "character.gltf", meta, materials=True, atlas=2048)
        if scene[:4] not in (b"N3S1", b"N3SM"):
            raise ValueError("front-end model magic")
        blobs.append(scene)
    head, _, tail = scene_tracks(blobs[0])
    extra = []
    for other in blobs[1:]:
        h, tracks, t = scene_tracks(other)
        if h != head or t != tail:
            raise ValueError("front-end clips do not share one model")
        extra.append(u(len(tracks)) + tracks)
    return u(len(blobs[0])) + blobs[0] + u(len(extra)) + b"".join(extra) + f(blends)


# --- UI ---------------------------------------------------------------------

def f32(value):
    """`value` as the f32 the file holds."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def axis(kind, a=0.0, c=0.0):
    """A move's rule on one axis (KEEP, LINEAR, HALF), its reals as stored."""
    if not (math.isfinite(a) and math.isfinite(c) and abs(a) <= MAX_MOVE_SCALE and abs(c) <= MAX_MOVE_OFFSET):
        raise ValueError("front-end move bound")
    return kind, f32(a), f32(c)


def axis_at(rule, extent):
    """Where `rule` puts a top-left coordinate on an axis `extent` pixels long,
    or None (KEEP). The client's front_place.h computes the same in doubles."""
    kind, a, c = rule
    if kind == KEEP:
        return None
    return int(a * extent + c + (extent // 2 if kind == HALF else 0))


def centred(size):
    """(S - size) / 2 in C's integer division (SetPosCenter), for S >= size."""
    return axis(LINEAR, 0.5, -size / 2)


def place(root, rule):
    """The root's move: where KO puts a screen's root on a window. `origin`
    (CGameProcCharacterSelect::Init's SetPos(0, 0)); `centre`
    (CN3UIBase::SetPosCenter, CUICharacterCreate::Load, MessageBoxPost);
    `bottom`, centred on the bottom edge (CGameProcLogIn_1098::Init: 1264
    005bde22-005bde3b, 1097 00524147-00524165); {"bottom": N}, centred with
    its bottom edge N pixels above the window's (1298's select bar,
    co_CharacterSelect_us.uif's Load 00606c10: ((W - w) >> 1, H - 10 - h),
    006070bd-0060710a)."""
    x0, y0, x1, y1 = root["rect"]
    w, h = x1 - x0, y1 - y0
    if type(rule) is dict:
        if set(rule) != {"bottom"}:
            raise ValueError("front-end placement %r" % rule)
        return centred(w), axis(LINEAR, 1.0, -offset(rule["bottom"]) - h)
    if rule == "origin":
        return axis(LINEAR), axis(LINEAR)
    if rule == "centre":
        return centred(w), centred(h)
    if rule == "bottom":
        return centred(w), axis(LINEAR, 1.0, -h)
    raise ValueError("front-end placement %r" % rule)


def offset(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > MAX_MOVE_OFFSET:
        raise ValueError("front-end move value")
    return float(value)


def move_axis(value, size, root_size):
    """A move's `x` or `y`: a number (that coordinate on the window), `centre`
    (centred on the window), or (x) {"middle": c, "ratio": k, "edge": "start"
    or "end"}: the node's start edge, or with `end` its end edge, at
    (S >> 1) + c + k S / R, R the root's own extent (1264's
    CUICharacterSelect::Load 004448f0: bt_left's x is (W >> 1) - w - 100 -
    26 W / 1024, bt_right's (W >> 1) + 26 W / 1024 + 100)."""
    if value == "centre":
        return centred(size)
    if type(value) is dict:
        if set(value) - {"middle", "ratio", "edge"} or "middle" not in value or \
                value.get("edge", "start") not in ("start", "end"):
            raise ValueError("front-end move middle")
        ratio = offset(value.get("ratio", 0))
        if ratio and root_size <= 0:
            raise ValueError("front-end move ratio")
        return axis(HALF, ratio / root_size if ratio else 0.0,
                    offset(value["middle"]) - (size if value.get("edge") == "end" else 0))
    return axis(LINEAR, 0.0, offset(value))


def moves(root, spec):
    """A screen's moves in order, (node, x rule, y rule): the root's `place`,
    then the recipe's `moves`. A move's `y` is a number or `centre`, or
    `bottom` (its bottom edge that far above the window's) or `above` [node,
    gap] (its bottom edge that far above that node's top, a node an earlier
    move places on y; CUICharacterSelect, CUILoading, OpenServerList); an axis
    a move does not name keeps where the earlier moves left it."""
    x0, y0, x1, y1 = root["rect"]
    out = [(root,) + place(root, spec["place"])]
    ys = {id(root): out[0][2]}
    listed = spec.get("moves", [])
    if type(listed) is not list or len(listed) + 1 > MAX_MOVES:
        raise ValueError("front-end moves")
    for m in listed:
        if type(m) is not dict or "node" not in m or set(m) - MOVE_KEYS or \
                sum(k in m for k in ("y", "bottom", "above")) > 1:
            raise ValueError("front-end move keys")
        node = resolve(root, m["node"])
        nx0, ny0, nx1, ny1 = node["rect"]
        x = move_axis(m["x"], nx1 - nx0, x1 - x0) if "x" in m else axis(KEEP)
        if "y" in m:
            if type(m["y"]) is dict:
                raise ValueError("front-end move middle")
            y = move_axis(m["y"], ny1 - ny0, y1 - y0)
        elif "bottom" in m:
            y = axis(LINEAR, 1.0, -offset(m["bottom"]) - (ny1 - ny0))
        elif "above" in m:
            if type(m["above"]) is not list or len(m["above"]) != 2:
                raise ValueError("front-end move above")
            kind, a, c = ys.get(id(resolve(root, m["above"][0])), (KEEP, 0.0, 0.0))
            if kind == KEEP:
                raise ValueError("front-end move above a node no earlier move places")
            y = axis(kind, a, c - offset(m["above"][1]) - (ny1 - ny0))
        else:
            y = axis(KEEP)
        ys[id(node)] = y
        out.append((node, x, y))
    return out


def apply_moves(placed, extent=CANVAS):
    """Each move in order at a window `extent`: the node's top-left where its
    rules say, its subtree moved with it (MoveOffset)."""
    for node, x, y in placed:
        x0, y0 = node["rect"][:2]
        tx, ty = axis_at(x, extent[0]), axis_at(y, extent[1])
        shift(node, (x0 if tx is None else tx) - x0, (y0 if ty is None else ty) - y0)


def resolve(root, address):
    """The node an address names: a unique id, then `#i` steps into the i-th
    child (UIF order) for KO's anonymous nodes; `#i` alone starts at the
    root."""
    head, *steps = address.split("#")
    node = root
    if head:
        hits = []

        def walk(n):
            if n["id"].casefold() == head.casefold():
                hits.append(n)
            for c in n["children"]:
                walk(c)
        walk(root)
        if len(hits) != 1:
            raise ValueError("front-end address %r: %d matches" % (address, len(hits)))
        node = hits[0]
    for step in steps:
        i = int(step)
        if not 0 <= i < len(node["children"]):
            raise ValueError("front-end address %r: no child %d" % (address, i))
        node = node["children"][i]
    return node


def shift(node, dx, dy):
    x0, y0, x1, y1 = node["rect"]
    node["rect"] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
    for c in node["children"]:
        shift(c, dx, dy)


def screen(name, spec, assets, textures, fonts, find=(), placements=None):
    """One screen's nodes in draw order, on the canvas. CN3UIBase::Load adds
    each child at the front and Render walks the list backwards, so a parent
    draws before its children and the children in file order; a button draws
    the one state image its state names (the image's reserved field), then
    its other children; an image without a texture draws nothing
    (CN3UIImage::Render). `find`: addresses whose node indices are returned
    too, as (data, indices); one that is hidden or draws nothing refuses.
    `placements`: a list the screen's moves (version 11) are appended to, as
    the section writes them: a count and each drawn node's index and rules."""
    tree, ui = split(assets, spec["ui"])
    root = ko_hud.parse(tree.get(ui))
    # Every address resolves on KO's tree as read, before anything moves or is added.
    table = lambda key: {id(resolve(root, a)): v for a, v in spec.get(key, {}).items()}
    bindings, texts, states = table("bindings"), table("text"), table("states")
    hidden = {id(resolve(root, a)) for a in spec.get("hidden", [])}
    wanted = [id(resolve(root, a)) for a in find]
    for extra in spec.get("added", []):
        # A string KO's layout lacks (a status line, say), in UIF
        # coordinates; last among its parent's children, so drawn last.
        node = dict(kind=6, id=extra["id"], rect=vector(extra["rect"], 4), style=extra["style"], reserved=0,
                    children=[], font="Arial", font_size=extra["font"][0], font_flags=extra["font"][1],
                    color=int(extra["color"], 16), text="")
        resolve(root, extra["parent"])["children"].append(node)
        bindings[id(node)] = extra["action"]
    placed = moves(root, spec)
    apply_moves(placed)
    nodes, seen = [], set()

    def font(size, flags):
        key = (count(size, 32, 6), bool(flags & 1))
        if key not in fonts:
            if len(fonts) >= MAX_FONTS:
                raise ValueError("front-end font count")
            fonts[key] = len(fonts)
        return fonts[key]

    def emit(n, parent, mask, flags):
        if id(n) in hidden:
            return
        kind = UIF_KINDS.get(n["kind"])
        if kind is None or (name == "logo" and kind not in LOGO_KINDS):
            raise ValueError("front-end UI type %d" % n["kind"])
        action = bindings.get(id(n), "")
        if action not in ACTIONS or ONLY_ON.get(action, name) != name:
            raise ValueError("front-end action %r" % action)
        if action in seen:
            raise ValueError("front-end action %r bound twice" % action)
        if action:
            seen.add(action)
        if id(n) in states:
            if states[id(n)] not in STATES:
                raise ValueError("front-end state %r" % states[id(n)])
            flags |= STATES[states[id(n)]]
        record = u(KINDS[kind]) + u(0xFFFFFFFF if parent is None else parent) + f(n["rect"]) + \
            string(n["id"][:64]) + u(ACTIONS.index(action)) + u(flags) + u(mask)
        if kind == "image" and not n["texture"]:
            return
        if kind == "image":
            record += u(textures.add(n["texture"], tree)) + f(n["uv"])
        elif kind == "text":
            if not n.get("font"):
                raise ValueError("front-end string without a font")
            data = texts.get(id(n), n["text"]).encode("ascii")
            if len(data) > MAX_TEXT:
                raise ValueError("front-end text length")
            record += u(len(data)) + data + u(font(n["font_size"], n["font_flags"])) + u(n["color"]) + u(n["style"])
        elif kind == "edit":
            # CN3UIEdit draws its one string child itself; the login's edits
            # also hold an image (untextured, so drawn as nothing).
            strings = [c for c in n["children"] if c["kind"] == 6]
            if len(strings) != 1 or any(c["kind"] not in (4, 6) for c in n["children"]):
                raise ValueError("front-end edit layout")
            label = strings[0]
            record += u(font(label["font_size"], label["font_flags"])) + u(label["color"]) + u(n["style"])
        elif kind == "list":
            size, color, bold, _italic = n["list_font"]
            record += u(font(size, bold)) + u(color)
        index = len(nodes)
        found[id(n)] = index
        nodes.append(record)
        if len(nodes) > MAX_NODES:
            raise ValueError("front-end node count")
        if kind == "edit":
            return
        for c in n["children"]:
            child_mask, child_flags = mask, 0
            if kind == "button" and c["kind"] == 4:
                if not 0 <= c["reserved"] <= 3:
                    raise ValueError("front-end button image state")
                child_mask = 1 << c["reserved"]
            if kind == "progress" and c["kind"] == 4 and c["reserved"] == 1:
                child_flags = FOREGROUND
            emit(c, index, child_mask, child_flags)

    found = {}
    emit(root, None, 15, 0)
    missing = REQUIRED.get(name, set()) - seen
    if name == "select" and not INFO_TEXTS & seen:
        missing = missing | {"char_info"}
    if missing:
        raise ValueError("front-end %s: unbound %s" % (name, sorted(missing)))
    data = u(len(nodes)) + b"".join(nodes)
    if placements is not None:
        # A move of a node that draws nothing (hidden) is not written.
        drawn = [(found[id(n)], x, y) for n, x, y in placed if id(n) in found]
        placements.append(u(len(drawn)) + b"".join(u(i) + u(x[0]) + f(x[1:]) + u(y[0]) + f(y[1:])
                                                   for i, x, y in drawn))
    if not find:
        return data
    if any(w not in found for w in wanted):
        raise ValueError("front-end %s: a node it names is not drawn" % name)
    return data, [found[w] for w in wanted]


# --- scenes -----------------------------------------------------------------

def hall(assets, textures, name):
    """The select hall (CN3Shape::Load): transform, two collision names, the
    parts, five trailing ints. A part is a pivot, a mesh, a 92-byte material
    (CN3Material: 17 floats, then colour op/args, render flags and blend) and
    its textures; a vertex is ((v + pivot) x scale) x rotation + position.
    Its meshes and textures are its tree's. No name (version 7): a hall of no
    parts (1298 draws a zone there instead: `zone`, version 8)."""
    if name is None:
        return u(0)
    assets, name = split(assets, name)
    r = character.Reader(assets.get(name))
    t = character.transform(r)
    if any(t["keys"]) or any([r.string(), r.string()]):
        raise ValueError("front-end hall transform/collision")
    position = reflect(t["translation"])
    qx, qy, qz, qw = t["rotation"]
    q = [-qx, -qy, qz, qw]
    out, parts = b"", count(r.integer(), 64)
    for _ in range(parts):
        pivot = reflect(r.floats(3))
        mesh = mesh_file(assets, r.string())
        material = r.floats(17) + r.unpack("6I")
        names = count(r.integer(), 1)
        r.floats(1)
        tex = textures.add([r.string() for _ in range(names)][0], assets)
        flags = material[20]
        if flags & ~0x4:
            raise ValueError("front-end hall part render flags %#x" % flags)
        vertices = []
        for v in mesh["vertices"]:
            p = ko_scene._rotate(q, [v[i] + pivot[i] for i in range(3)])
            vertices.append([p[i] + position[i] for i in range(3)] + ko_scene._rotate(q, v[3:6]) + list(v[6:8]))
        mesh_flags = (DOUBLE_SIDED if flags & 0x4 else 0) | (ALPHA_TEST if textures.masked(tex) else 0)
        out += mesh_record(vertices, mesh["indices"], tex, mesh_flags, material[:3], material[4:7])
    r.unpack("5i")
    r.end()
    return u(parts) + out


# Version 8 (RQ-095, specs/KO-FINDINGS.md 8.4): a KO zone drawn as the select
# hall. 1298's select Init (005f98c0) calls 00600950, which sets the zone 1000
# and the nation, so the key 0046c9d0 builds (zone x 10 + nation) is 10001 for
# Karus, and loads it through CN3WorldManager::InitWorld (005c0de0, a
# CN3TerrainManager, 005a2f30); Render (005fb1c0) draws the world's sky, terrain
# and shapes before the characters, under the select's lights. Its bounds are
# N3W1's (ko_scene), the zone being at most N3W1's 129 samples a side.
MAX_ZONE_MESHES = 256
MAX_ZONE_VERTICES = ko_scene.MAX_VERTICES
MAX_ZONE_INDICES = ko_scene.MAX_INDICES
MAX_ZONE_TEXTURE = 1024
# The material 1298's terrain render (0059cd90) sets: Diffuse 1, Ambient 0.5
# (`SetMaterial`, vtable +0xa8). A shape part sets its own (CN3SPart's
# __Material); the zone hall carries one material, so every part's must be it.
ZONE_DIFFUSE, ZONE_AMBIENT = [1.0, 1.0, 1.0], [0.5, 0.5, 0.5]
# An alpha part's blend as the alpha flush (0043dd80) draws it: SRCALPHA over
# INVSRCALPHA, blending only (no diffuse alpha, depth written and tested).
ZONE_BLEND = (5, 6, 1)


def zone(assets, textures, value, report):
    """The select hall's zone (version 8): a mesh count (up to 256) and the
    meshes, each a mesh record and a sort point (engine space; a BLEND mesh
    is drawn after the UI, far to near by the eye's distance to it), cooked
    from the zone `value` names, a Zones.tbl key of the first input or
    `<input>:<key>`: the row's terrain (column 2), colour map (column 4) and
    objects (column 6), checked as the world loader checks them (005a3110,
    `ko_zone`), expanded as the package's world is (`ko_scene.expand`: the
    terrain's tiles and colour-map tiles, every static shape's parts) and
    grouped by texture, light and blend. None: no zone (u32 0)."""
    if value is None:
        return u(0)
    import ko_collision
    import ko_shapes
    import ko_terrain
    import ko_zone
    import world_chunks
    first = assets.trees[0] if isinstance(assets, Inputs) else assets
    tree, key = split(assets, value) if type(value) is str else (first, value)
    if type(key) is str:
        key = int(key) if key.isascii() and key.isdigit() else None
    if type(key) is not int or key <= 0:
        raise ValueError("front-end select.zone: a Zones.tbl key, or <input>:<key>")
    root = tree.root
    table, rows = ko_zone.table(root)
    row = ko_zone.row(rows, key)

    def column(index):
        return ko_zone.resolve(root, row[index], "Zones.tbl row %d column %d" % (key, index + 1))

    gtd, tct, opd = column(ko_zone.GTD), column(ko_zone.TCT), column(ko_zone.OPD)
    if row[ko_zone.OPDEXT] != ko_zone.RESERVED:
        raise ValueError("front-end select.zone %d: its row names an OPDEXT, which the zone hall does not merge" % key)
    ko_zone.check_names(key, row[ko_zone.NAME], gtd, opd)
    if ko_terrain.header_samples(gtd, False) > ko_terrain.MAX_SUPPORTED_SAMPLES:
        raise ValueError("front-end select.zone %d: past %d samples a side"
                         % (key, ko_terrain.MAX_SUPPORTED_SAMPLES))
    found = ko_scene.references(gtd, opd, root)
    if found["missing"]:
        raise ValueError("front-end select.zone %d names %d missing files: %s"
                         % (key, len(found["missing"]), ", ".join(found["missing"])))
    shapes = ko_shapes.load_shapes(opd)["shapes"]
    objects = ko_scene.object_files(root)
    meshes = set()
    for shape in shapes:
        if ko_shapes.classify(shape) not in ko_shapes.BAKED:
            continue
        for part in shape["parts"]:
            if not part["mesh"]:
                continue
            meshes.add(ko_scene._basename(part["mesh"]))
            if part["diffuse"] != ZONE_DIFFUSE or part["ambient"] != ZONE_AMBIENT:
                raise ValueError("front-end select.zone %d: a part of %s has the material %s / %s, not the "
                                 "terrain's" % (key, shape["name"], part["diffuse"], part["ambient"]))
    heightfield = ko_collision.bake(gtd, opd)[0]
    built = ko_scene.expand(gtd, opd, root, heightfield, detail=True, color_map=tct, chunked=True)
    chains, texture_sources = ko_scene.world_chains(root, built)
    # Every file the zone reads, through the tree (its hash recorded, a
    # reference install's checked against its manifest).
    files = {table, gtd, tct, opd} | {pathlib.Path(p) for p in texture_sources}
    files |= {objects[name] for name in meshes}
    for path in sorted(files):
        tree.get(str(pathlib.Path(path).resolve().relative_to(root)))

    vertices, records = built["vertices"], built["chunks"]
    terrain = built["report"]["terrain_vertices"]
    if any(v[11] not in (ko_scene.CLEAR, world_chunks.UNLIT_VERTEX) for v in vertices[:terrain]):
        raise ValueError("front-end select.zone %d: a second tile layer, which the zone hall does not carry" % key)
    owner = {}
    for index, record in enumerate(records):
        if record["kind"] != 1:
            continue
        if record["flags"] & world_chunks.SEQUENCE:
            raise ValueError("front-end select.zone %d: a texture sequence, which the zone hall does not carry" % key)
        if record["flags"] & world_chunks.ALPHA:
            alpha = record["alpha"]
            if (alpha["source"], alpha["destination"], alpha["state"]) != ZONE_BLEND:
                raise ValueError("front-end select.zone %d: an alpha part's blend %s" % (key, alpha))
        for v in range(record["base"], record["base"] + record["max_vertices"]):
            owner[v] = index
    half = (heightfield["width"] - 1) * heightfield["spacing"] / 2.0

    def place(p):  # the world bake's coordinates to the hall's (KO's, z negated)
        return [p[0] + half, p[1], p[2] - half]

    groups = {}
    indices = built["indices"]
    for t in range(0, len(indices), 3):
        a, b, c = indices[t:t + 3]
        slot = int(vertices[a][10])
        if int(vertices[b][10]) != slot or int(vertices[c][10]) != slot or slot == ko_scene.CLEAR:
            raise ValueError("front-end select.zone %d: a triangle without one texture" % key)
        record = records[owner[a]] if a in owner else None
        unlit = vertices[a][11] == world_chunks.UNLIT_VERTEX or bool(record and record["flags"] & world_chunks.UNLIT)
        if record and record["flags"] & world_chunks.ALPHA:
            group = (1, owner[a], slot, unlit)
        else:
            group = (0, 0, slot, unlit)
        groups.setdefault(group, []).append((a, b, c))

    out, slots, emitted, total_vertices, total_indices = [], {}, 0, 0, 0
    for group in sorted(groups):
        blended, which, slot, unlit = group
        if slot not in slots:
            w, h, rgba = chains[slot][0]
            if w > MAX_ZONE_TEXTURE or h > MAX_ZONE_TEXTURE:
                raise ValueError("front-end select.zone %d: a %dx%d texture" % (key, w, h))
            slots[slot] = textures.raw(w, h, bytes(rgba))
        flags = (BLEND if blended else CUT_ZERO) | (UNLIT if unlit else 0)
        sort = place(records[which]["alpha"]["point"]) if blended else [0.0, 0.0, 0.0]
        triangles, at = groups[group], 0
        while at < len(triangles):
            # A mesh holds at most 65536 vertices and 3 x 65536 indices.
            local, mesh_vertices, mesh_indices = {}, [], []
            while at < len(triangles) and len(mesh_indices) + 3 <= 3 * 65536 and len(local) + 3 <= 65536:
                for v in triangles[at]:
                    if v not in local:
                        local[v] = len(mesh_vertices)
                        x = vertices[v]
                        mesh_vertices.append(place(x[:3]) + list(x[3:8]))
                    mesh_indices.append(local[v])
                at += 1
            out.append(mesh_record(mesh_vertices, mesh_indices, slots[slot], flags, ZONE_DIFFUSE, ZONE_AMBIENT)
                       + f(sort))
            total_vertices += len(mesh_vertices)
            total_indices += len(mesh_indices)
            emitted += blended
    if not out or len(out) > MAX_ZONE_MESHES:
        raise ValueError("front-end select.zone %d: %d meshes, not 1 to %d" % (key, len(out), MAX_ZONE_MESHES))
    if total_vertices > MAX_ZONE_VERTICES or total_indices > MAX_ZONE_INDICES:
        raise ValueError("front-end select.zone %d: past %d vertices or %d indices"
                         % (key, MAX_ZONE_VERTICES, MAX_ZONE_INDICES))
    objects_report = built["report"]["objects"]
    report.update(zone=dict(
        key=key, name=row[ko_zone.NAME], terrain=row[ko_zone.GTD], colour_map=row[ko_zone.TCT],
        objects=row[ko_zone.OPD], meshes=len(out), blended_meshes=emitted, textures=len(slots),
        vertices=total_vertices, triangles=total_indices // 3, terrain_tiles=built["report"]["terrain"],
        placements=objects_report["placements"], alpha_parts=objects_report["alpha_parts"],
        unlit_parts=objects_report["unlit_parts"],
        left_out=sorted({ko_shapes.classify(s) for s in shapes} - set(ko_shapes.BAKED)),
        binary="KnightOnLine.exe 005f98c0, 00600950, 0046c9d0, 005c0de0, 005fb1c0, 0059cd90, 0043dd80"))
    return u(len(out)) + b"".join(out)


def looks(assets, race):
    """The race's UPC_DefaultLooks row."""
    rows = list(csv.reader(io.StringIO(assets.get("Data/UPC_DefaultLooks.tbl.csv").decode("utf-8-sig"))))
    row = next((r for r in rows[1:] if r[0] == str(race)), None)
    if row is None:
        raise ValueError("front-end race %d not in UPC_DefaultLooks" % race)
    return row


def default_parts(assets, race):
    """The race's default looks (UPC_DefaultLooks, face 0 and hair 0, as
    ko_player): what select shows, since the wire carries no equipment."""
    parts = looks(assets, race)[4:10]
    parts[2] = parts[2].replace("_face.n3cpart", "_face00.n3cpart")
    parts[5] = parts[5].replace("_hair.n3cpart", "_hair00.n3cpart")
    return parts


def intro_scene(assets, textures, config, work):
    """CGameProcLogIn_1098: the camera, lights 0-2, the looping character and
    its plugs, and the moon, a screen quad in 1024 x 768 units. The
    character's parts and plugs are its tree's."""
    tree, name = split(assets, config["character"])
    chr_ = chr_file(tree.get(name))
    out = camera_record(config["camera"]) + lights(assets, config["lights"]) + f(vector(config["ambient"], 3))
    out += model(tree, name, chr_, [config["clip"]], work / "intro")
    out += u(len(chr_["plugs"])) + b"".join(plug_record(tree, textures, p) for p in chr_["plugs"])
    moon = config["backdrop"]
    tex = textures.add(moon["texture"])
    w, h, _ = textures.list[tex]
    x, y = vector(moon["at"], 2)
    return out + u(tex) + f([x, y, x + w * moon["scale"], y + h * moon["scale"]])


# CheckRotateLeft/Right (1097 binary: 0043dc50, 0043dfb0) test the eye one
# RotationY step further on, by this angle (the doubles at 0058cd78 and 0058cd88,
# +-0.01), against the turn's end.
TURN_CHECK_STEP = 0.01


def turn_end_eye(camera, slot, index):
    """The eye (KO space) at which the select camera's turn to the slot ends
    (specs/KO-FINDINGS.md 8.2). Slot 0 is the camera's own eye. For the others,
    1097's check (0043dc50, 0043dfb0) turns a copy of the eye a further 0.01 rad
    about the vertical through `at` and ends the turn once the cosine between
    it and the camera's own eye, both from `at`, falls below the slot's
    `turn_end` (Karus: 0.75 left, 0.77 right). So the turn ends on the first
    tick whose angle is past the one cooked here; the client turns until
    then. The slot's side is the side its character stands on."""
    eye, at = vector(camera["eye"], 3), vector(camera["at"], 3)
    if index == 0:
        if "turn_end" in slot:
            raise ValueError("front-end slot 0 is the camera's own eye")
        return eye
    end = slot.get("turn_end")
    ox, oy, oz = (eye[i] - at[i] for i in range(3))
    flat = ox * ox + oz * oz
    side = math.atan2(slot["position"][0] - at[0], slot["position"][2] - at[2])
    if not isinstance(end, (int, float)) or flat <= 0 or abs(side) < 1e-6:
        raise ValueError("front-end slot %d turn" % index)
    # The cosine between the eye's offset o and o turned by b about y is
    # (flat * cos b + oy^2) / |o|^2.
    cos_b = (end * (flat + oy * oy) - oy * oy) / flat
    if not -1 < cos_b < 1:
        raise ValueError("front-end slot %d turn_end" % index)
    angle = math.acos(cos_b) - TURN_CHECK_STEP
    if not 0 < angle < math.pi / 2:
        raise ValueError("front-end slot %d turn_end" % index)
    angle = math.copysign(angle, side)
    # RotationY(angle) on a row vector: x' = x cos + z sin, z' = -x sin + z cos.
    c, s = math.cos(angle), math.sin(angle)
    return [at[0] + ox * c + oz * s, eye[1], at[2] - ox * s + oz * c]


def camera_path(assets, name):
    """An .n3camera as 1298's select plays it (specs/KO-FINDINGS.md 8.4):
    CN3Camera::Load (00439540, after the transform load 0043b480): the name,
    the eye, a rotation, the up vector, three key sets, the at, __CameraData
    (0x16c bytes) and the fog's use and colour. The select's camera
    (004396c0) takes the first key set as the eye's path and the second, when
    it is vectors, as the at's; it ticks no third (the up), and its Render
    (005fb1c0) sets its own field of view, near and far, so the file's are
    not read. (rate, eye keys, rate, at keys), KO space."""
    eye, at, _ = camera_file(assets, name)
    return eye["rate"], eye["values"], at["rate"], at["values"]


def camera_file(assets, name):
    """(eye keys, at keys, (fog use, fog colour)) of an .n3camera
    (`camera_path`)."""
    r = character.Reader(assets.get(name))
    r.string()
    r.floats(3), r.floats(4), r.floats(3)
    eye, at, up = character.key(r, 0), character.key(r, 0), character.key(r, 0)
    if eye is None or at is None or up is not None:
        raise ValueError("front-end camera path %s: eye and at keys, no up keys" % name)
    if max(len(eye["values"]), len(at["values"])) > MAX_PATH_KEYS:
        raise ValueError("front-end camera path %s: past %d keys" % (name, MAX_PATH_KEYS))
    r.floats(3)
    r.take(CAMERA_DATA)
    fog = r.unpack("iI")
    r.end()
    return eye, at, fog


# Version 8 (RQ-095): CN3Camera::Apply (1298: 004395c0) sets linear range
# vertex fog (D3DRS_FOGVERTEXMODE 3, FOGTABLEMODE 0, RANGEFOGENABLE 1) from
# FOGSTART = far x 0.1 (`006a3d1c`) to FOGEND = far, the camera's +0x154,
# which the select's Render (005fb1c0) sets to 500 before it applies.
FOG_START = 0.1


def path_fog(assets, config):
    """The fog record (version 8): on, colour (r, g, b, 0-1), start, end.
    `select.fog` true: the fog the path mode's camera files carry
    (CN3Camera::Load reads its use and colour, 00439540, and Apply sets them,
    004395c0), which must be one fog for every path (the select keeps one
    camera and loads each path into it, 005fa670), from 0.1 x far to the
    select camera's far. Absent: none (all zeros)."""
    fog = config.get("fog")
    if fog is None:
        return u(0) + f([0.0] * 5)
    if fog is not True or config.get("turn") != "path":
        raise ValueError("front-end select.fog: true, in the path turn mode (the camera files' fog)")
    fogs = {tuple(camera_file(assets, path["path"])[2]) for path in config["paths"]}
    if len(fogs) != 1:
        raise ValueError("front-end select.fog: the camera paths' files carry %d different fogs" % len(fogs))
    use, colour = fogs.pop()
    if use not in (0, 1):
        raise ValueError("front-end select.fog: a camera file's fog use is %d" % use)
    if not use:
        return u(0) + f([0.0] * 5)
    far = config["camera"]["far"]
    rgb = [((colour >> shift) & 0xFF) / 255 for shift in (16, 8, 0)]
    return u(1) + f(rgb + [far * FOG_START, far])


def turn_paths(assets, config, slots):
    """The path mode's paths (version 7): each {from, to, path}, `from`
    absent for the entry path into slot 0; the arrows' neighbours (1, 0, 2)
    both ways; a pair once. Returns the records and each slot's rest eye (KO
    space), the last eye key of the path into it (the entry path's for slot 0,
    else the one from slot 0)."""
    paths = config.get("paths")
    if type(paths) is not list or not 1 <= len(paths) <= MAX_PATHS:
        raise ValueError("front-end select.paths: 1 to %d camera paths" % MAX_PATHS)
    out, ends = b"", {}
    for path in paths:
        if type(path) is not dict or set(path) - {"from", "to", "path"}:
            raise ValueError("front-end select.paths: each {from, to, path}")
        source, to = path.get("from"), path.get("to")
        if type(to) is not int or not 0 <= to < slots or (
                source is None and to != 0) or (
                source is not None and (type(source) is not int or not 0 <= source < slots or source == to)):
            raise ValueError("front-end select.paths: from a slot (or none, into slot 0) to another")
        key = (ENTRY if source is None else source, to)
        if key in ends:
            raise ValueError("front-end select.paths: %s to %d twice" % (source, to))
        eye_rate, eye, at_rate, at = camera_path(assets, path.get("path"))
        ends[key] = eye[-1]
        out += u(key[0]) + u(to) + f([eye_rate]) + u(len(eye)) + b"".join(f(reflect(v)) for v in eye)
        out += f([at_rate]) + u(len(at)) + b"".join(f(reflect(v)) for v in at)
    needed = [(ENTRY, 0)] + [pair for side in (1, 2) if side < slots for pair in ((0, side), (side, 0))]
    missing = [pair for pair in needed if pair not in ends]
    if missing:
        raise ValueError("front-end select.paths: none from %s to %d"
                         % ("the entry" if missing[0][0] == ENTRY else missing[0][0], missing[0][1]))
    rest = [ends[(ENTRY, 0)]] + [ends[(0, side)] for side in range(1, slots)]
    return u(len(paths)) + out, rest


def select_scene(assets, textures, config, work, report=None):
    """CGameProcCharacterSelect (Karus): the camera, the hall lights, the
    slots (position, yaw, the eye where the camera's turn to the slot ends
    and its spot light), the spot's growth rate, the front-clip mode, what
    ESC presses (version 15), the turn mode and its paths (version 7), the hall, the zone and the fog
    (version 8), the character with its clips and plugs. `report` receives
    the zone's provenance."""
    camera = config["camera"]
    if config.get("zone") is not None and config.get("hall") is not None:
        raise ValueError("front-end select: a hall or a zone, not both")
    mode = config.get("front_clip")
    if type(mode) is not str or mode not in FRONT_CLIP:
        raise ValueError("front-end select.front_clip: one of %s" % ", ".join(FRONT_CLIP))
    turn = config.get("turn")
    if type(turn) is not str or turn not in TURN:
        raise ValueError("front-end select.turn: one of %s" % ", ".join(TURN))
    escape = config.get("escape", "back")
    if type(escape) is not str or escape not in ESCAPE:
        raise ValueError("front-end select.escape: one of %s" % ", ".join(ESCAPE))
    if turn == "path":
        if any("turn_end" in slot for slot in config["slots"]):
            raise ValueError("front-end select.turn path: a slot's turn ends with its path, no turn_end")
        path_records, rest = turn_paths(assets, config, len(config["slots"]))
    elif "paths" in config:
        raise ValueError("front-end select.paths: only in the path turn mode")
    else:
        path_records, rest = u(0), None
    slots = b""
    for index, slot in enumerate(config["slots"]):
        x, y, z = vector(slot["position"], 3)
        slot_eye = rest[index] if rest else turn_end_eye(camera, slot, index)
        spot, target = vector(slot["spot"], 3), vector(slot["spot_target"], 3)
        light = dict(kind=SPOT, diffuse=[1, 1, 1], ambient=[0, 0, 0], position=reflect(spot),
                     direction=reflect([target[i] - spot[i] for i in range(3)]),
                     range=6.0, falloff=20.0, attenuation=[0.1, 0, 0], theta=config["spot_theta"],
                     phi=config["spot_phi"])
        slots += f(reflect([x, y, z]) + [-math.radians(slot["yaw"])] + reflect(slot_eye)) + light_record(light)
    # The spot's growth (version 4): KO's per-tick step as a rate at
    # TICKS_PER_SECOND, at most the spot's whole theta per tick and the
    # client's bound of 100 a second.
    step = config["spot_step"]
    if not (isinstance(step, (int, float)) and 0 < step <= config["spot_theta"] and step * TICKS_PER_SECOND <= 100):
        raise ValueError("front-end spot step")
    look = config["character"]
    if len(look["clips"]) != SELECT_CLIPS:
        raise ValueError("front-end select clips: the front, start and rest clips")
    # The start clip's blend: the select's own time (1097 binary: 0043ea30
    # sets clip 1 with 0.6 s, `push 0x3f19999a` at 0043ea77; 1298: 005fe7c0
    # sets clip 2 the same way), not the record's; the front and rest clips
    # keep their records' (0043f280 and 005fef90 name FLT_MIN).
    tree, joint = character_tree(assets, look)
    _, animation = split(assets, look["animation"])
    definition = dict(joint=joint, animation=animation, parts=default_parts(tree, look["race"]))
    out = (camera_record(camera) + lights(assets, config["lights"], config.get("light_manager")) +
           f(vector(config["ambient"], 3)))
    out += u(count(len(config["slots"]), 3)) + slots + f([step * TICKS_PER_SECOND]) + u(FRONT_CLIP[mode])
    out += u(ESCAPE[escape])
    out += u(TURN[turn]) + path_records
    out += hall(assets, textures, config.get("hall"))
    # Version 8 (RQ-095): the zone the hall draws (1298's karus_intro) and the
    # camera's fog.
    out += zone(assets, textures, config.get("zone"), report if report is not None else {})
    out += path_fog(assets, config)
    out += model(tree, joint, definition, look["clips"], work / "select",
                 own_blends={START_CLIP: config["start_blend"]})
    return out + u(len(look["plugs"])) + b"".join(plug_record(assets, textures, p) for p in look["plugs"])


def character_tree(assets, look):
    """(tree, joint) of the select character: its joint, animation and race's
    looks row (and so the create model) are one tree's."""
    tree, joint = split(assets, look["joint"])
    if split(assets, look["animation"])[0] is not tree:
        raise ValueError("front-end select character: the joint and animation are in different inputs")
    return tree, joint


def create_scene(assets, race, work):
    """CGameProcCharacterCreate: the player's own model (InitChr from the
    race's UPC_DefaultLooks row: its joint, animation and default parts),
    breathing (ANI_BREATH), with no plugs: a new character holds nothing."""
    row = looks(assets, race)
    joint, animation = row[2].replace("\\", "/"), row[3].replace("\\", "/")
    definition = dict(joint=joint, animation=animation, parts=default_parts(assets, race))
    return model(assets, joint, definition, [BREATH], work / "create") + u(0)


def mpeg_frame(data, at, end):
    """(bytes, rate, channels, mpeg1) of the MPEG-1 or MPEG-2 Layer III frame
    header at `at` (its four bytes before `end`), or None: free format,
    MPEG 2.5 and reserved values are refused, as client/assets/music.cpp's
    mpeg_frame. The frame itself may run past `end`."""
    if at + 4 > end or data[at] != 0xFF or data[at + 1] & 0xE0 != 0xE0:
        return None
    version, layer = (data[at + 1] >> 3) & 3, (data[at + 1] >> 1) & 3
    bitrate, rate, padding = data[at + 2] >> 4, (data[at + 2] >> 2) & 3, (data[at + 2] >> 1) & 1
    if version not in (2, 3) or layer != 1 or bitrate in (0, 15) or rate == 3:
        return None
    mpeg1 = version == 3
    hz = MPEG1_HZ[rate] if mpeg1 else MPEG1_HZ[rate] // 2
    kbps = (MPEG1_KBPS if mpeg1 else MPEG2_KBPS)[bitrate]
    return (144000 if mpeg1 else 72000) * kbps // hz + padding, hz, 1 if data[at + 3] >> 6 == 3 else 2, mpeg1


def music_track(data):
    """A KO MP3 file's Layer III frames: (rate, channels, frames, the frames'
    bytes, bytes dropped). A leading ID3v2 tag and a trailing ID3v1 tag are
    dropped, and so is a last frame the file cuts short (KO's
    Snd/Intro_Sound.mp3 lacks the last 196 bytes of its 4097th frame,
    local-asset); anything else that is not a whole frame of the first
    frame's format refuses. The frames are carried unchanged (Q69)."""
    start, end = 0, len(data)
    if data[:3] == b"ID3" and len(data) >= 10:
        size = data[6:10]
        if any(b & 0x80 for b in size):
            raise ValueError("music ID3v2 tag size")
        start = 10 + (size[0] << 21 | size[1] << 14 | size[2] << 7 | size[3]) + (10 if data[5] & 0x10 else 0)
    if end - start >= 128 and data[end - 128:end - 125] == b"TAG":
        end -= 128
    at, frames, form = start, 0, None
    while at < end:
        frame = mpeg_frame(data, at, end)
        if frame is None or (form is not None and frame[1:] != form):
            raise ValueError("music frame at byte %d" % at)
        if at + frame[0] > end:
            if form is None:
                raise ValueError("music frame at byte %d" % at)
            break
        form = frame[1:]
        at += frame[0]
        frames += 1
    if not frames:
        raise ValueError("music without frames")
    body = data[start:at]
    if len(body) > MAX_TRACK_BYTES:
        raise ValueError("music track past its bound")
    return form[0], form[1], frames, body, len(data) - len(body)


def wav_format(data):
    """The format tag of a RIFF WAVE's first `fmt ` chunk, or None."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    at = 12
    while at + 8 <= len(data):
        size = struct.unpack_from("<I", data, at + 4)[0]
        if data[at:at + 4] == b"fmt ":
            return struct.unpack_from("<H", data, at + 8)[0] if size >= 2 and at + 10 <= len(data) else None
        at += 8 + size + (size & 1)
    return None


def pcm_track(data):
    """A KO WAV file as the music's PCM: (rate, channels, sample frames, s16le
    bytes, source sample width). Read as ko_audio.pcm reads a WAV (the wave
    module: uncompressed PCM, 1 or 2 channels, 1-4 byte samples, 8-96 kHz),
    but kept at its own rate and channels and whole, not cut to 10 s; samples
    of another width become 16-bit as ko_audio's do (round(x * 32768)). The
    format tag must be 1, integer PCM: the wave module of newer Pythons also
    reads other tags (IEEE float) and reports them as uncompressed."""
    if wav_format(data) != 1:
        raise ValueError("music WAV format")
    try:
        with wave.open(io.BytesIO(data)) as w:
            channels, width, rate, frames, compression, _ = w.getparams()
            if channels not in (1, 2) or width not in (1, 2, 3, 4) or compression != "NONE":
                raise ValueError("music WAV format")
            if not PCM_RATES[0] <= rate <= PCM_RATES[1] or frames <= 0:
                raise ValueError("music WAV format")
            if frames * channels * 2 > MAX_TRACK_BYTES:
                raise ValueError("music track past its bound")
            raw = w.readframes(frames)
    except (wave.Error, EOFError) as e:
        raise ValueError("music WAV: %s" % e)
    if len(raw) != frames * channels * width:
        raise ValueError("music WAV truncated")
    if width != 2:
        samples = []
        for i in range(frames * channels):
            sample = int.from_bytes(raw[i * width:(i + 1) * width], "little", signed=width > 1)
            value = (sample - 128) / 128 if width == 1 else sample / (1 << (width * 8 - 1))
            samples.append(max(-32768, min(32767, round(value * 32768))))
        raw = struct.pack("<%dh" % len(samples), *samples)
    return rate, channels, frames, raw, width


def music(assets, config):
    """Section 9: the tracks and the track each screen plays, as the client
    the recipe names plays them (content/front-end.md, "Moradon"). A track
    file that is a RIFF WAVE is cooked as PCM (version 5, `pcm_track`), any
    other as MPEG Layer III frames (`music_track`); `loop` starts it again at
    its end, and `restart` (seconds, version 5) starts it again at its first
    sample after that much playback, ended or not (KO 1097's login tick,
    005248f5-00524957, restarts sound 35 every 21.66 s)."""
    config = config or {"tracks": [], "screens": {}}
    tracks = config["tracks"]
    count(len(tracks), MAX_TRACKS, 0)
    if set(config["screens"]) - set(MUSIC_SCREENS):
        raise ValueError("music screens")
    data, report = u(len(tracks)), []
    for track in tracks:
        if set(track) - {"path", "loop", "restart"}:
            raise ValueError("music track keys")
        if type(track.get("loop")) is not bool:
            raise ValueError("music loop")
        restart = track.get("restart", 0)
        if type(restart) not in (int, float) or not (restart == 0 or RESTART[0] <= restart <= RESTART[1]):
            raise ValueError("music restart")
        source = assets.get(track["path"])
        entry = dict(path=track["path"])
        if source[:4] == b"RIFF" and source[8:12] == b"WAVE":
            rate, channels, frames, body, width = pcm_track(source)
            kind = PCM
            entry.update(kind="pcm", rate=rate, channels=channels, frames=frames, bytes=len(body), width=width)
        else:
            rate, channels, frames, body, dropped = music_track(source)
            kind = MPEG
            entry.update(kind="mpeg", rate=rate, channels=channels, frames=frames, bytes=len(body), dropped=dropped)
        data += u(kind) + u(rate) + u(channels) + u(int(track["loop"])) + f([restart]) + u(frames) + u(len(body))
        data += body
        report.append(dict(entry, loop=track["loop"], restart=restart))
    for name in MUSIC_SCREENS:
        index = config["screens"].get(name)
        if index is not None and (type(index) is not int or not 0 <= index < len(tracks)):
            raise ValueError("music screen track")
        data += u(NO_MUSIC if index is None else index)
    return data, report


def seconds(value, what, low=0.0, high=MAX_LOGO_SECONDS, above=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value > high or \
            (value <= low if above else value < low):
        raise ValueError("front-end logo %s" % what)
    return float(value)


def logo(config, assets, textures, fonts, tracks, placements=None):
    """Section 10 (version 9, RQ-101): the logo screen, or its absence (0).
    `config` is the recipe's `logo` (None: no logo screen); `tracks` the
    music section's track count. Its layout is cooked as a screen (`screen`)
    that binds nothing and draws groups, images and strings only; then each
    group (its node, fade-in, hold and fade-out seconds), the music (a track
    or none, its delay, the group its fade-out starts with or none, the fade's
    seconds) and the flags (`LOGO_SKIP_KEY`, `LOGO_HIDE_CURSOR`). 1264's: the
    groups group_k2, group_presents and group_knight at 1.5, 1 and 1.5 s
    (00601360: the divisor 1.5 at 00648f10, 1 for group 1) to the peak 1.5,
    Snd\\bless.wav 1 s after the first tick (005fa7c0, 006489e4), its 4 s
    fade (004371a0(4.0)) from group 2, a key skipping (00601480) and the
    cursor hidden (00601140: SetCursor(NULL)). `placements`: as `screen`'s;
    no logo appends an empty move list."""
    if config is None:
        if placements is not None:
            placements.append(u(0))
        return u(0), None
    if type(config) is not dict or set(config) - LOGO_KEYS or not {"ui", "place", "groups", "peak"} <= set(config):
        raise ValueError("front-end logo keys")
    groups = config["groups"]
    if type(groups) is not list or not 1 <= len(groups) <= MAX_LOGO_GROUPS:
        raise ValueError("front-end logo groups")
    if any(type(g) is not dict or set(g) != {"node", "seconds"} or type(g["node"]) is not str for g in groups):
        raise ValueError("front-end logo group keys")
    peak = seconds(config["peak"], "peak", 1.0, 10.0, above=True)
    screen_data, indices = screen("logo", config, assets, textures, fonts, [g["node"] for g in groups],
                                  placements)
    if len(set(indices)) != len(indices):
        raise ValueError("front-end logo group twice")
    data = screen_data
    nodes = struct.unpack_from("<I", data)[0]
    report = dict(nodes=nodes, groups=[])
    data = u(1) + data + u(len(groups))
    for g, index in zip(groups, indices):
        if data_kind(screen_data, index) != KINDS["group"]:
            raise ValueError("front-end logo group %r is not a group" % g["node"])
        t = seconds(g["seconds"], "group seconds", above=True)
        fade_in, hold, fade_out = t, 2 * (peak - 1) * t, t
        if fade_in + hold + fade_out > MAX_LOGO_SECONDS:
            raise ValueError("front-end logo group seconds")
        data += u(index) + f([fade_in, hold, fade_out])
        report["groups"].append(dict(node=g["node"], fade_in=fade_in, hold=hold, fade_out=fade_out))
    music_config = config.get("music")
    track, delay, fade_group, fade = NO_MUSIC, 0.0, NO_GROUP, 0.0
    if music_config is not None:
        if type(music_config) is not dict or set(music_config) - {"track", "delay", "fade_group", "fade"} or \
                "track" not in music_config or ("fade_group" in music_config) != ("fade" in music_config):
            raise ValueError("front-end logo music keys")
        track = music_config["track"]
        if type(track) is not int or not 0 <= track < tracks:
            raise ValueError("front-end logo music track")
        delay = seconds(music_config.get("delay", 0), "music delay")
        if "fade_group" in music_config:
            fade_group = music_config["fade_group"]
            if type(fade_group) is not int or not 0 <= fade_group < len(groups):
                raise ValueError("front-end logo fade group")
            fade = seconds(music_config["fade"], "music fade", above=True)
    flags = 0
    skip, cursor = config.get("skip", "none"), config.get("cursor", "shown")
    if skip not in ("key", "none") or cursor not in ("hidden", "shown"):
        raise ValueError("front-end logo skip or cursor")
    flags |= LOGO_SKIP_KEY if skip == "key" else 0
    flags |= LOGO_HIDE_CURSOR if cursor == "hidden" else 0
    report.update(music=None if track == NO_MUSIC else track, delay=delay,
                  fade_group=None if fade_group == NO_GROUP else fade_group, fade=fade, skip=skip, cursor=cursor)
    return data + u(track) + f([delay]) + u(fade_group) + f([fade]) + u(flags), report


def text_row(assets, ref, what):
    """A message's title or text: the recipe's string, or KO's own: one row
    of a client's encrypted text table ({"table": path, "row": id}; the
    1264 and 1298 clients load `Data\\Texts` plus `_us.tbl` and look a row up
    by id, 005d2350 in 1264). ASCII, at most MAX_TEXT bytes; KO's trailing
    spaces are kept."""
    if type(ref) is str:
        text = ref
    elif type(ref) is dict and set(ref) == {"table", "row"} and type(ref["table"]) is str and \
            type(ref["row"]) is int and ref["row"] > 0:
        import ko_tbl
        types, rows = ko_tbl.parse(ko_tbl.decrypt(assets.get(ref["table"])))
        if types[:2] != TEXT_TYPES:
            raise ValueError("front-end %s: %s columns %s" % (what, ref["table"], types[:2]))
        found = [r[1] for r in rows if r[0] == ref["row"]]
        if len(found) != 1:
            raise ValueError("front-end %s: %d rows %d in %s" % (what, len(found), ref["row"], ref["table"]))
        text = found[0]
    else:
        raise ValueError("front-end %s: a string or {\"table\", \"row\"}" % what)
    if not text.isascii() or len(text) > MAX_TEXT or any(c != "\n" and not " " <= c <= "~" for c in text):
        raise ValueError("front-end %s: not printable ASCII of at most %d bytes" % (what, MAX_TEXT))
    return text


def message_texts(config, assets):
    """{kind: (title, text or None)} of the recipe's `messages` (version 10,
    RQ-102), None where the client's own wording stays."""
    messages = config.get("messages") or {}
    if type(messages) is not dict or set(messages) - set(MESSAGES):
        raise ValueError("front-end messages: kinds of %s" % ", ".join(MESSAGES))
    out = {}
    for kind, entry in messages.items():
        if type(entry) is not dict or not entry or set(entry) - {"title", "text"}:
            raise ValueError("front-end message %s: a title, a text or both" % kind)
        title = text_row(assets, entry["title"], "message %s title" % kind) if "title" in entry else ""
        text = text_row(assets, entry["text"], "message %s text" % kind) if "text" in entry else None
        out[kind] = (title, text)
    return out


def messages_section(config, assets):
    """Section 11 (version 10, RQ-102, Q81): a count and, for each worded
    message, its index in MESSAGES, its title, whether its text replaces the
    client's (0 or 1) and that text (empty when not). A title needs the
    message screen's `title` binding to be drawn, so one without it is refused.
    Version 14 (RQ-111): `exit_confirm` makes the select's exit ask in a box
    with Yes and No (1298's btn_exit, 00607160), so it needs the message
    screen's `yes` and `no` bindings."""
    worded = message_texts(config, assets)
    bound = set(((config.get("screens") or {}).get("message") or {}).get("bindings", {}).values())
    if any(title for title, _ in worded.values()) and "title" not in bound:
        raise ValueError("front-end messages: a title, and no message screen node bound to `title`")
    if "exit_confirm" in worded and not {"yes", "no"} <= bound:
        raise ValueError("front-end messages: exit_confirm, and no message screen nodes bound to `yes` and `no`")
    data = u(len(worded))
    for kind in MESSAGES:
        if kind in worded:
            title, text = worded[kind]
            data += u(MESSAGES.index(kind)) + string(title) + u(0 if text is None else 1) + string(text or "")
    return data, {k: dict(title=t, text=x) for k, (t, x) in worded.items()}


def data_kind(data, index):
    """The kind of node `index` in a cooked screen (`screen`'s bytes)."""
    at = 4
    for _ in range(index):
        at = node_end(data, at)
    return struct.unpack_from("<I", data, at)[0]


def node_end(data, at):
    """The offset past the cooked node record at `at` (`screen`'s `emit`)."""
    kind = struct.unpack_from("<I", data, at)[0]
    at += 4 + 4 + 16
    at += 4 + struct.unpack_from("<I", data, at)[0] + 12
    if kind == KINDS["image"]:
        at += 4 + 16
    elif kind == KINDS["text"]:
        at += 4 + struct.unpack_from("<I", data, at)[0] + 12
    elif kind == KINDS["edit"]:
        at += 12
    elif kind == KINDS["list"]:
        at += 8
    return at


def cook(assets, out, config_path, work):
    """Writes front-end.bin into the directory `out`; returns its provenance.
    `assets` is the choice's `Inputs`, or one tree."""
    config = load(pathlib.Path(config_path))
    assets = assets if isinstance(assets, Inputs) else Inputs([assets])
    # The client files this cook reads, with their hashes (ko_character.Assets).
    shared = []
    for tree, _ in assets.unique():
        shared.append((tree, tree.sources))
        tree.sources = {}
    try:
        return write(assets, out, config, work)
    finally:
        for tree, earlier in shared:
            cooked, tree.sources = tree.sources, earlier
            earlier.update(cooked)


def write(assets, out, config, work):
    assets = assets if isinstance(assets, Inputs) else Inputs([assets])
    if set(config["screens"]) != set(SCREENS):
        raise ValueError("front-end screens")
    textures, fonts = Textures(assets), {}
    placements = []
    screens = b"".join(screen(n, config["screens"][n], assets, textures, fonts, placements=placements)
                       for n in SCREENS)
    # Version 9 (RQ-101): the logo screen, or none; its textures and fonts
    # join the tables before they are written.
    track_count = len((config.get("music") or {}).get("tracks", []))
    logo_section, logo_report = logo(config.get("logo"), assets, textures, fonts, track_count, placements)
    # Version 11 (RQ-106, Q82): the placement, its flags (the recipe's
    # `ui_scale`) and each layout's moves (the five screens, then the logo).
    if config.get("ui_scale", "native") not in UI_SCALE:
        raise ValueError("front-end ui_scale")
    placement_section = u(UI_SCALE[config.get("ui_scale", "native")]) + b"".join(placements)
    strings = config["strings"]
    if set(strings) != set(STRINGS):
        raise ValueError("front-end strings")
    table = b""
    for key in STRINGS:
        data = strings[key].encode("ascii")
        if len(data) > MAX_TEXT:
            raise ValueError("front-end string length")
        table += u(len(data)) + data
    scenes = intro_scene(assets, textures, config["intro"], pathlib.Path(work))
    zone_report = {}
    scenes += select_scene(assets, textures, config["select"], pathlib.Path(work), zone_report)
    scenes += create_scene(character_tree(assets, config["select"]["character"])[0],
                           config["select"]["character"]["race"], pathlib.Path(work))
    atlases = b""
    sources = {False: pathlib.Path(config["fonts"]["regular"]), True: pathlib.Path(config["fonts"]["bold"])}
    for (size, bold), _ in sorted(fonts.items(), key=lambda kv: kv[1]):
        # A KO font height is in points (CDFont: MulDiv(h, LOGPIXELSY, 72)), 96 dpi.
        pixels = round(size * 96 / 72)
        (w, h, rgba), (height, top, advances) = ko_nameplates.atlas(sources[bold], pixels)
        atlases += u(textures.raw(w, h, rgba)) + u(pixels) + u(height) + u(top) + f(advances)
    data = b"N3FE" + u(VERSION) + u(count(config["character_slots"], 3)) + u(CANVAS[0]) + u(CANVAS[1])
    data += u(len(textures.list)) + b"".join(u(w) + u(h) + rgba for w, h, rgba in textures.list)
    tracks, played = music(assets, config.get("music"))
    # Version 10 (RQ-102): each message's title and wording.
    message_section, message_report = messages_section(config, assets)
    data += u(len(fonts)) + atlases + screens + table + scenes + tracks + logo_section + message_section + placement_section
    if len(data) > MAX_FILE:
        raise ValueError("front-end.bin past its bound")
    (out / "front-end.bin").write_bytes(data)
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), textures=len(textures.list),
                fonts=len(fonts), music=played, logo=logo_report, messages=message_report, font_substitutes=sorted(str(p) for p in sources.values()),
                sources=dict(sorted(assets.sources.items())), **zone_report)
