"""The KO front end (spec 11): front-end.bin (N3FE, content/front-end.md).

KO's 1098 login scene (the orc with the axe under the moon, GameProcLogIn_1098),
its login and server-list layout, the Karus character select hall
(GameProcCharacterSelect), character create, loading and the OK message box,
cooked from the pinned client tree, (version 3) the screens' music, KO's
MP3 frames carried as they are, (version 4) each model clip's blend time
and the select spot's growth rate, and (version 5) PCM music tracks from KO's
WAVs and a track's restart period. games/moradon/front-end.json names every KO
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

VERSION = 5
# The rate KO's frame-scaled code is written for: its per-frame steps are
# scaled by 30 / s_fFrmPerSec (source: GameProcCharacterSelect.cpp's fade,
# N3Pond.cpp). The select spot's per-tick step (1097 binary: 0043f280 adds
# 0.02, Karus, or 0.015, El Morad, every tick) is cooked as a rate at it.
TICKS_PER_SECOND = 30
# A clip's blend time (__AnimData::fTimeBlend, seconds), as the client bounds it.
MAX_BLEND = 10.0
# The select model's clips by role (version 4): the hover clip (pre_select),
# the start clip (selected) and the rest clip (dummy), as DoProcPreselect and
# the select (1097: 0043f280, 0043ea30) name them.
SELECT_CLIPS = 3
START_CLIP = 1
# ANI_BREATH (GameDef.h): the idle InventoryChrAnimationInitialize plays.
BREATH = 0
CANVAS = (1024, 768)
SCREENS = ("login", "select", "create", "loading", "message")
KINDS = {"image": 0, "text": 1, "button": 2, "edit": 3, "progress": 4, "group": 5, "area": 6, "list": 7}
# The UIF node types (CN3UIBase) the front-end layouts use; any other refuses.
UIF_KINDS = {0: "group", 1: "button", 3: "progress", 4: "image", 6: "text", 8: "edit", 9: "area", 14: "list"}
# The engine's closed action set (spec 11); the client gives each its behaviour.
ACTIONS = ("", "login", "exit", "login_group", "realm_group", "realm_list", "realm_connect", "notice",
           "select_prev", "select_next", "back", "char_info", "create_confirm", "name_field", "char_view",
           "class_desc", "progress", "version", "info", "message", "ok")
REQUIRED = {"login": {"login", "exit", "login_group", "realm_group", "realm_list", "realm_connect"},
            "select": {"select_prev", "select_next", "back", "exit", "char_info"},
            "create": {"create_confirm", "back", "name_field", "char_view"},
            "loading": {"progress"},
            "message": {"message", "ok"}}
# The client's strings, in file order. {level}, {class}, {name} and {version}
# are the only substitutions the client makes.
STRINGS = ("select_info", "select_hint", "class_name", "class_desc", "loading_info", "version")
# Node flags.
FIXED_ON, FIXED_DISABLED, FOREGROUND = 1, 2, 4
STATES = {"on": FIXED_ON, "disabled": FIXED_DISABLED}
# Mesh flags.
DOUBLE_SIDED, ALPHA_TEST = 1, 2
# Light types (D3DLIGHTTYPE).
POINT, SPOT, DIRECTIONAL = 1, 2, 3
MAX_NODES = 1024
MAX_TEXTURES = 64
MAX_FONTS = 8
MAX_TEXT = 1024
MAX_FILE = 64 * 1024 * 1024
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
    add("select.turn_sound", select.get("turn_sound"))
    look = section(select.get("character"))
    add("select.character.joint", look.get("joint"))
    add("select.character.animation", look.get("animation"))
    each("select.character.plugs", look.get("plugs"))
    tracks = section(config.get("music")).get("tracks")
    for at, track in enumerate(tracks if type(tracks) is list else []):
        add("music.tracks[%d].path" % at, section(track).get("path"))
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
    return dict(on=bool(on), kind=kind, diffuse=diffuse[:3], ambient=ambient[:3],
                position=reflect(position), direction=reflect(direction),
                range=rng, falloff=falloff, attenuation=[a0, a1, a2], theta=theta, phi=phi)


def light_record(l):
    if not 0 < l["range"] <= 1e8 or sum(l["attenuation"]) <= 0 or min(l["attenuation"]) < 0:
        raise ValueError("front-end light range/attenuation")
    return u(l["kind"]) + f(l["diffuse"] + l["ambient"] + l["position"] + l["direction"] +
                            [l["range"], l["falloff"]] + l["attenuation"] + [l["theta"], l["phi"]])


def lights(assets, names):
    """The lights a scene applies; CN3Light::Apply enables only a light that
    is on."""
    on = [l for l in (light(assets, n) for n in names) if l["on"]]
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

def place(root, rule):
    """The move that puts a screen's root where KO puts it on the 1024 x 768
    canvas: `origin`; `centre` (CN3UIBase::SetPosCenter); `bottom`, centred
    on the bottom edge (CGameProcLogIn_1098::Init). C integer division."""
    x0, y0, x1, y1 = root["rect"]
    w, h = x1 - x0, y1 - y0
    if rule == "origin":
        return -x0, -y0
    if rule == "centre":
        return int((CANVAS[0] - w) / 2) - x0, int((CANVAS[1] - h) / 2) - y0
    if rule == "bottom":
        return int((CANVAS[0] - w) / 2) - x0, CANVAS[1] - h - y0
    raise ValueError("front-end placement %r" % rule)


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


def move(node, rule, above):
    """One of the reference client's per-node placements, after the root's:
    `x`/`y` set the top-left on the canvas; `bottom` puts the bottom edge
    that far above the canvas's; `above` [node, gap] puts it that far above
    another node (CUICharacterSelect, CUILoading, OpenServerList)."""
    x0, y0, x1, y1 = node["rect"]
    x, y = rule.get("x", x0), rule.get("y", y0)
    if "bottom" in rule:
        y = CANVAS[1] - rule["bottom"] - (y1 - y0)
    if above is not None:
        y = above["rect"][1] - rule["above"][1] - (y1 - y0)
    shift(node, x - x0, y - y0)


def screen(name, spec, assets, textures, fonts):
    """One screen's nodes in draw order, on the canvas. CN3UIBase::Load adds
    each child at the front and Render walks the list backwards, so a parent
    draws before its children and the children in file order; a button draws
    the one state image its state names (the image's reserved field), then
    its other children; an image without a texture draws nothing
    (CN3UIImage::Render)."""
    tree, ui = split(assets, spec["ui"])
    root = ko_hud.parse(tree.get(ui))
    # Every address resolves on KO's tree as read, before anything moves or is added.
    table = lambda key: {id(resolve(root, a)): v for a, v in spec.get(key, {}).items()}
    bindings, texts, states = table("bindings"), table("text"), table("states")
    hidden = {id(resolve(root, a)) for a in spec.get("hidden", [])}
    moves = [(resolve(root, m["node"]), m, resolve(root, m["above"][0]) if "above" in m else None)
             for m in spec.get("moves", [])]
    for extra in spec.get("added", []):
        # A string KO's layout lacks (a status line, say), in UIF
        # coordinates; last among its parent's children, so drawn last.
        node = dict(kind=6, id=extra["id"], rect=vector(extra["rect"], 4), style=extra["style"], reserved=0,
                    children=[], font="Arial", font_size=extra["font"][0], font_flags=extra["font"][1],
                    color=int(extra["color"], 16), text="")
        resolve(root, extra["parent"])["children"].append(node)
        bindings[id(node)] = extra["action"]
    shift(root, *place(root, spec["place"]))
    for node, rule, above in moves:
        move(node, rule, above)
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
        if kind is None:
            raise ValueError("front-end UI type %d" % n["kind"])
        action = bindings.get(id(n), "")
        if action not in ACTIONS:
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

    emit(root, None, 15, 0)
    missing = REQUIRED[name] - seen
    if missing:
        raise ValueError("front-end %s: unbound %s" % (name, sorted(missing)))
    return u(len(nodes)) + b"".join(nodes)


# --- scenes -----------------------------------------------------------------

def hall(assets, textures, name):
    """The select hall (CN3Shape::Load): transform, two collision names, the
    parts, five trailing ints. A part is a pivot, a mesh, a 92-byte material
    (CN3Material: 17 floats, then colour op/args, render flags and blend) and
    its textures; a vertex is ((v + pivot) x scale) x rotation + position.
    Its meshes and textures are its tree's."""
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


def select_scene(assets, textures, config, work):
    """CGameProcCharacterSelect (Karus): the camera, the hall lights, the
    slots (position, yaw, the eye where the camera's turn to the slot ends
    and its spot light), the spot's growth rate, the hall, the character with
    its clips and plugs."""
    camera = config["camera"]
    slots = b""
    for index, slot in enumerate(config["slots"]):
        x, y, z = vector(slot["position"], 3)
        slot_eye = turn_end_eye(camera, slot, index)
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
        raise ValueError("front-end select clips: the hover, start and rest clips")
    # The start clip's blend: the select's own time (1097 binary: 0043ea30
    # sets clip 1 with 0.6 s, `push 0x3f19999a` at 0043ea77), not the
    # record's; the hover and rest clips keep their records' (0043f280 names
    # FLT_MIN).
    tree, joint = character_tree(assets, look)
    _, animation = split(assets, look["animation"])
    definition = dict(joint=joint, animation=animation, parts=default_parts(tree, look["race"]))
    out = camera_record(camera) + lights(assets, config["lights"]) + f(vector(config["ambient"], 3))
    out += u(count(len(config["slots"]), 3)) + slots + f([step * TICKS_PER_SECOND])
    out += hall(assets, textures, config["hall"])
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
    screens = b"".join(screen(n, config["screens"][n], assets, textures, fonts) for n in SCREENS)
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
    scenes += select_scene(assets, textures, config["select"], pathlib.Path(work))
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
    data += u(len(fonts)) + atlases + screens + table + scenes + tracks
    if len(data) > MAX_FILE:
        raise ValueError("front-end.bin past its bound")
    (out / "front-end.bin").write_bytes(data)
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), textures=len(textures.list),
                fonts=len(fonts), music=played, font_substitutes=sorted(str(p) for p in sources.values()),
                sources=dict(sorted(assets.sources.items())))
