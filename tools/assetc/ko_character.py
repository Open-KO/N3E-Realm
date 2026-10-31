#!/usr/bin/env python3
"""Opt-in local KO character experiment; independent bounded layout implementation.
Reads reference assets without modifying them. Outputs glTF/atlas/provenance under
build/ only; no proprietary data is needed by normal builds or synthetic tests.
See KO-CHARACTER.md for layout sources, supported semantics and limitations.
"""
import argparse
import copy
import hashlib
import json
import math
import pathlib
import struct
import zlib
from common import read, count, vector, canonical


class Reader:
    def __init__(self, data):
        if len(data) > 16 * 1024 * 1024:
            raise ValueError("KO file bound")
        self.data = data
        self.at = 0

    def take(self, n):
        if n < 0 or self.at + n > len(self.data):
            raise ValueError("truncated KO data")
        b = self.data[self.at : self.at + n]
        self.at += n
        return b

    def unpack(self, fmt):
        return list(struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt))))

    def integer(self):
        return self.unpack("i")[0]

    def string(self):
        return self.take(count(self.integer(), 255, 0)).decode("cp949")

    def end(self):
        if self.at != len(self.data):
            raise ValueError("unsupported trailing KO data")

    def floats(self, n):
        return vector(self.unpack(str(n) + "f"), n)


def normalized(q):
    norm = math.sqrt(sum(v * v for v in q))
    if not 0.99 < norm < 1.01:
        raise ValueError("non-unit quaternion")
    return [v / norm for v in q]


def slerp(a, b, t):
    a = normalized(a)
    b = normalized(b)
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b = [-x for x in b]
        d = -d
    if d > 0.9995:
        return normalized([x + (y - x) * t for x, y in zip(a, b)])
    angle = math.acos(min(1, d))
    den = math.sin(angle)
    return [
        (x * math.sin((1 - t) * angle) + y * math.sin(t * angle)) / den
        for x, y in zip(a, b)
    ]


def key(r, kind):
    n = count(r.integer(), 65536, 0)
    if not n:
        return None
    if r.integer() != kind:
        raise ValueError("animation key type")
    rate = r.floats(1)[0]
    if not 0 < rate <= 120:
        raise ValueError("animation sample rate")
    values = [r.floats(3 if kind == 0 else 4) for _ in range(n)]
    if kind == 1:
        values = [normalized(q) for q in values]
    return {"rate": rate, "values": values, "kind": kind}


def sample(k, frame, default):
    """A track's value at `frame`, as KO's key sampler gives it: key index
    i = trunc(frame x rate / 30), the last key while i equals the count, and,
    below that, key i blended toward key i + 1 (the load copies the last key
    past the end, so key count - 1 blends toward itself). 1298 `00427640`
    (PQ-266) and 2233 `0044b450` / `0044b560` (load `0042c150`, PQ-317) both
    take i up to the count; past it KO leaves the joint unchanged, which this
    reader refuses."""
    if k is None:
        return default[:]
    at = frame * k["rate"] / 30
    if not 0 <= at < len(k["values"]) + 1:
        raise ValueError("clip outside key range")
    i = min(int(at), len(k["values"]) - 1)
    j = min(i + 1, len(k["values"]) - 1)
    t = at - int(at)
    a, b = k["values"][i], k["values"][j]
    return slerp(a, b, t) if k["kind"] == 1 else [x + (y - x) * t for x, y in zip(a, b)]


def transform(r, scaled=False):
    """A KO transform: name, position, rotation, scale and their three key
    tracks (the transform load 0043b480 reads them in this order). Only a
    skeleton read for `convert` takes a scale (`scaled`, PQ-266); every other
    reader refuses a scale that is not exactly (1, 1, 1) or a scale track."""
    name = r.string()
    p = r.floats(3)
    q = normalized(r.floats(4))
    scale = r.floats(3)
    keys = [key(r, 0), key(r, 1), key(r, 0)]
    if scale != [1, 1, 1] or keys[2] is not None:
        if not scaled:
            raise ValueError("scaled KO joint unsupported")
        if min(scale + [v for values in (keys[2] or {"values": []})["values"] for v in values]) <= 0:
            raise ValueError("KO joint scale not positive")
    return {"name": name, "translation": p, "rotation": q, "scale": scale, "keys": keys}


def is_scaled(node):
    """Whether a joint has a scale KO applies: the joint matrix 00427a50 skips
    the scale only when all three components are exactly 1.0 (bit compares
    with 0x3f800000); a scale track replaces the scale every tick."""
    return node["scale"] != [1, 1, 1] or node["keys"][2] is not None


def skeleton(data, scaled=False, limit=64):
    """The joint tree in file order (parents first). `scaled` (convert's
    path, PQ-266) accepts joint scales; the bounds readers (nameplates,
    render detail, target marker) build unscaled world matrices and keep
    refusing them. `limit` is the most joints read: 64 for those readers,
    `MAX_JOINTS` for convert (PQ-267; KO's joint set sizes its arrays by
    the joint count, 0041b000)."""
    r = Reader(data)
    nodes = []

    def visit(parent, depth):
        if depth > 63 or len(nodes) >= limit:
            raise ValueError("skeleton bound")
        n = transform(r, scaled)
        orient = key(r, 1)
        if orient is not None:
            raise ValueError("joint orientation track unsupported")
        n["parent"] = parent
        index = len(nodes)
        nodes.append(n)
        for _ in range(count(r.integer(), limit, 0)):
            visit(index, depth + 1)

    visit(-1, 0)
    r.end()
    return nodes


def character(data, strict=True, trailing=False):
    """An .n3chr's joint, parts and animation. Strict (the worm's and the CLI's
    path) refuses collision, FX plug and collision-skin names; otherwise they
    are returned for the caller to record as omitted (PQ-254). `trailing`
    (the 2145 path, PQ-317) stops after the eighth field, as both 2233
    character loads do (`CN3Chr::Load_Old` 0044a990, `CN3Chr::Load` 0044a030:
    they then call 004426c0, which reads no file), and returns how many bytes
    were left unread; otherwise a byte after it is refused."""
    r = Reader(data)
    t = transform(r)
    if t["translation"] != [0, 0, 0] or t["rotation"] != [0, 0, 0, 1] or any(t["keys"]):
        raise ValueError("character transform unsupported")
    collision = [r.string(), r.string()]
    if strict and any(collision):
        raise ValueError("KO collision requires explicit conversion")
    joint = r.string()
    parts = [r.string() for _ in range(count(r.integer(), 8))]
    if r.integer() != 0:
        raise ValueError("equipment plugs unsupported")
    animation = r.string()
    split = r.unpack("4i")
    if any(v != -1 for v in split):
        raise ValueError("split animation unsupported")
    extras = [r.string(), r.string()]
    if strict and any(extras):
        raise ValueError("FX/collision skin unsupported")
    unread = len(r.data) - r.at
    if not trailing:
        r.end()
    return ({"unread": unread} if trailing else {}) | {
        "name": t["name"],
        "joint": joint,
        "parts": parts,
        "animation": animation,
        "collision": collision,
        "split": split,
        "extras": extras,
    }


def animations(data, empty=False, unused_word=False):
    """The clip table's records; a table without clips is refused unless
    `empty` (an NPC looks row whose table KO starts no clip from, PQ-268).
    `unused_word` (the front end's intro table, spec 11) accepts any value in
    a clip's first word: `Intro/intro.n3anim` carries uninitialised bytes
    there. The reference's __AnimData::Load reads that word into a local
    ("where a string pointer used to be, for compatibility") and never uses
    it. Every other caller keeps refusing a non-zero word."""
    r = Reader(data)
    out = []
    n = r.integer()
    if n == 0 and not empty:
        raise ValueError("animation table has no clips")
    if n == 0:
        r.end()
        return out
    for _ in range(count(n, 256)):
        reserved = r.integer()
        v = r.floats(8)
        flags = r.integer()
        strike = r.floats(2)
        name = r.string()
        if (reserved and not unused_word) or not all(0 <= f <= 100000 for f in v[:2]) or not 0 < v[2] <= 120:
            raise ValueError("animation metadata")
        out.append(
            {
                "name": name,
                "start": v[0],
                "end": v[1],
                "fps": v[2],
                "trace": v[3:5],
                "sound": v[5:7],
                "blend_seconds": v[7],
                "blend_flags": flags,
                "strike": strike,
            }
        )
    r.end()
    return out


# A part's render state (PQ-265, D-173; record:
# docs/implementation/evidence/pq-265-ko-character-part-materials.md, which
# labels each claim). The part load 00412180 (KnightOnLine.exe) reads the
# 0x5c-byte material into +0x88 and copies it to +0x2c (004121ef-00412208,
# binary): 17 floats (the D3D material), then the colour op and its two
# arguments, the render flags (+0x7c) and the source and destination blend
# (+0x80, +0x84). The part renderer 00412570, called only by the character
# render 004196a0 (0041997f) for each part in vector order, tests flags 1
# (alpha blending with the material's two factors), 2 (fog off), 4 (cull off),
# 0x40 (lighting off) and, while [006e268e] is set, 0x800 (a second layer)
# (binary). n3e carries 1, 4 and 0x40; 2 is refused (fails closed) because
# no homeland part uses it and n3e has no check that would show its draw
# (PQ-265 review; queued with PQ-280). It sets the colour op itself (texture x diffuse), so the
# material's own op is never read, and zeroes the emissive colour (binary).
# The device set-up 0043ade0 turns the alpha test on with GREATER and sets no
# reference (binary), so against the default reference 0 (API default) a
# texel of alpha 0 is not drawn on any part.
RF_ALPHABLENDING, RF_DOUBLESIDED, RF_NOTUSELIGHT = 0x1, 0x4, 0x40
PART_FLAGS = RF_ALPHABLENDING | RF_DOUBLESIDED | RF_NOTUSELIGHT
# D3DBLEND 1-10 (ZERO .. INVDESTCOLOR; API, d3d8types.h) by the engine's
# blend factor names (tools/assetc/gltf.py BLEND_FACTORS, same order).
BLEND_FACTORS = ("zero", "one", "src_color", "one_minus_src_color", "src_alpha", "one_minus_src_alpha",
                 "dst_alpha", "one_minus_dst_alpha", "dst_color", "one_minus_dst_color")
OPAQUE_STATE = {"alpha_reference": 0.0, "blend": None, "double_sided": False, "lit": True}


def render_state(material):
    """The engine render state (gltf.py N3E_render_state) of a part material.
    Fails closed on a flag 00412570 does not test, on 2 (fog off: not carried,
    see above) and on 0x800 (its second layer, which n3e does not draw), on blend factors past D3DBLEND 10, and on a
    diffuse colour other than opaque white (lit parts multiply the texture by
    it, which n3e's lighting does not, and whether stage 0's alpha takes it is
    not settled: inference, the record's alpha-op scan). The source and
    destination factors are read only under flag 1, as 00412570 reads them
    (binary)."""
    flags, source, destination = material[20:23]
    if flags & ~PART_FLAGS:
        raise ValueError("KO part render flags 0x%x unsupported" % (flags & ~PART_FLAGS))
    if material[:4] != [1, 1, 1, 1]:
        raise ValueError("KO part diffuse other than opaque white unsupported")
    blend = None
    if flags & RF_ALPHABLENDING:
        if not (1 <= source <= 10 and 1 <= destination <= 10):
            raise ValueError("KO part blend factors %d/%d unsupported" % (source, destination))
        blend = [BLEND_FACTORS[source - 1], BLEND_FACTORS[destination - 1]]
    return {"alpha_reference": 0.0, "blend": blend, "double_sided": bool(flags & RF_DOUBLESIDED),
            "lit": not flags & RF_NOTUSELIGHT}


def part(data):
    r = Reader(data)
    name = r.string()
    if r.integer() != 0:
        raise ValueError("part version unsupported")
    material = r.floats(17) + r.unpack("6I")
    state = render_state(material)
    texture = r.string()
    skin = r.string()
    r.end()
    return {"name": name, "material": material, "texture": texture, "skin": skin, "render_state": state}


# PQ-267 (D-175; record:
# docs/implementation/evidence/pq-267-ko-character-skin-bounds.md). KO has no
# influence or joint bound: the skin load 004286f0 (KnightOnLine.exe) reads
# any number of influences per vertex and the CPU skinning 00419f00 sums every
# one with its weight as read (binary). A skin has at most 64 joints. A
# skeleton may have up to MAX_JOINTS joints so that they, the mesh node and
# any scale nodes (PQ-266) can fit the 128-node scene.
MAX_JOINTS = 127
# PQ-283 (D-176; record:
# docs/implementation/evidence/pq-283-ko-skin-many-influences.md): `convert`
# keeps every influence of a vertex, as read, up to this many (16 glTF
# JOINTS_n / WEIGHTS_n sets; NPC looks clips cook them as N3SI / N3SJ).
MAX_INFLUENCES = 64


def vertex(r):
    """A skin mesh vertex for `convert`: the position as every reader reads
    it and the normal as stored, which may be non-finite (PQ-281: look 2200's
    harpy has two such vertices, undrawn; corner_normals replaces a drawn
    one)."""
    p = r.floats(3)
    n = r.unpack("3f")
    return p + (vector(n, 3) if all(math.isfinite(x) for x in n) else n)


def skins(data, every=False):
    """An .n3cskins' four LODs. Without `every` (render detail, appearance,
    the bounds readers) a vertex with more than four influences or a joint
    index past 63 is refused, as before PQ-267, and so is a non-finite
    normal. With it (convert) a vertex may have up to MAX_INFLUENCES
    influences on joints below MAX_JOINTS, all kept as read, in file order
    (PQ-283), and a non-finite normal (PQ-281); `joints` and `weights` hold
    at least four entries a vertex."""
    r = Reader(data)
    name = r.string()
    lods = []
    for _ in range(4):
        label = r.string()
        nf = count(r.integer(), 65536, 0)
        nv = count(r.integer(), 65536, 0)
        nu = count(r.integer(), 65536, 0)
        if bool(nf) != bool(nv) or (nf and not nu):
            raise ValueError("skin counts")
        vertices = [vertex(r) if every else r.floats(6) for _ in range(nv)]
        indices = r.unpack(str(nf * 3) + "H") if nf else []
        uv = [r.floats(2) for _ in range(nu)]
        ui = r.unpack(str(nf * 3) + "H") if nu else []
        if indices and (max(indices) >= nv or max(ui) >= nu):
            raise ValueError("skin index")
        origins = []
        joints = []
        weights = []
        most, bound = (MAX_INFLUENCES, MAX_JOINTS) if every else (4, 64)
        for k in range(nv):
            origins.append(r.floats(3))
            n = r.integer()
            if not 1 <= n <= most:
                raise ValueError("skin vertex with %d joint influences (1-%d supported)" % (n, most))
            r.take(8)
            j = r.unpack(str(n) + "i")
            w = r.floats(n) if n > 1 else [1.0]
            if min(j) < 0 or max(j) >= bound or min(w) < 0 or abs(sum(w) - 1) > 0.0001:
                raise ValueError("skin influences")
            joints.append(j + [0] * (4 - min(n, 4)))
            weights.append([v / sum(w) for v in w] + [0.0] * (4 - min(n, 4)))
        lods.append(
            {
                "name": label,
                "vertices": vertices,
                "indices": indices,
                "uv": uv,
                "uv_indices": ui,
                "origins": origins,
                "joints": joints,
                "weights": weights,
            }
        )
    r.end()
    return name, lods


def colors(c0, c1, four):
    """A DXT colour block's RGBA palette: four colours when c0 > c1 or when
    `four` (DXT3 always), else three and transparent black (alpha 0) at index
    3 (API: Direct3D's DXT decoding)."""

    def color(v):
        return [
            ((v >> 11) & 31) * 255 // 31,
            ((v >> 5) & 63) * 255 // 63,
            (v & 31) * 255 // 31,
        ]

    a, b = color(c0), color(c1)
    if c0 > c1 or four:
        return [a + [255], b + [255], [(2 * x + y) // 3 for x, y in zip(a, b)] + [255],
                [(x + 2 * y) // 3 for x, y in zip(a, b)] + [255]]
    return [a + [255], b + [255], [(x + y) // 2 for x, y in zip(a, b)] + [255], [0, 0, 0, 0]]


def dxt1(blocks, width, height):
    """RGBA texels of DXT1 blocks; a three-colour block's index 3 is
    transparent black, which KO's alpha test does not draw (PQ-265)."""
    if width % 4 or height % 4 or len(blocks) != width * height // 2:
        raise ValueError("DXT1 block bound")
    rgba = bytearray(width * height * 4)
    for by in range(height // 4):
        for bx in range(width // 4):
            c0, c1, indices = struct.unpack_from(
                "<HHI", blocks, (by * width // 4 + bx) * 8
            )
            palette = colors(c0, c1, False)
            for pixel in range(16):
                at = ((by * 4 + pixel // 4) * width + bx * 4 + pixel % 4) * 4
                rgba[at : at + 4] = bytes(palette[(indices >> (pixel * 2)) & 3])
    return bytes(rgba)


def dxt3(blocks, width, height):
    """RGBA texels of DXT3 blocks (API: a 4-bit alpha per texel, low nibble
    first, expanded by 17, then a four-colour block)."""
    if width % 4 or height % 4 or len(blocks) != width * height:
        raise ValueError("DXT3 block bound")
    rgba = bytearray(width * height * 4)
    for by in range(height // 4):
        for bx in range(width // 4):
            alpha, c0, c1, indices = struct.unpack_from(
                "<QHHI", blocks, (by * width // 4 + bx) * 16
            )
            palette = colors(c0, c1, True)
            for pixel in range(16):
                at = ((by * 4 + pixel // 4) * width + bx * 4 + pixel % 4) * 4
                rgba[at : at + 3] = bytes(palette[(indices >> (pixel * 2)) & 3][:3])
                rgba[at + 3] = ((alpha >> (pixel * 4)) & 15) * 17
    return bytes(rgba)


# NTF3 formats (PQ-265): fourcc -> (decoder, bytes per 4 x 4 block). The
# texture load 0043f090 (KnightOnLine.exe; no function is defined there, the
# audit recovers it at that entry) creates a DXT1-DXT5 texture in its own
# format when the device supports it and otherwise reads the 16-bit chain as
# A1R5G5B5 (DXT1) or A4R4G4B4 (the others), so the file's alpha is kept
# either way (binary).
FORMATS = {0x31545844: (dxt1, 8), 0x33545844: (dxt3, 16)}


def texture(data, limit=512):
    """(width, height, RGBA texels) of an NTF3 DXT1 or DXT3 texture. `limit`
    is the largest side: 512 for every part the world draws; the front end's
    intro model (spec 11) passes 1024, for its eye texture."""
    r = Reader(data)
    name = r.string()
    magic = r.take(4)
    w, h, fmt, mips = r.unpack("4i")
    if magic != b"NTF\x03" or fmt not in FORMATS or mips != 1:
        raise ValueError("only NTF3 mipmapped DXT1 or DXT3 supported")
    for n in [w, h]:
        if not 4 <= n <= limit or n & (n - 1):
            raise ValueError("texture dimensions")
    decode, block = FORMATS[fmt]
    base = r.take(w * h * block // 16)
    small_w, small_h = w // 2, h // 2
    # Compressed mip chain followed by 16-bit half-resolution fallback chain
    # (the DXT3 sizes: local-asset, every DXT3 part texture the homeland
    # looks use ends there).
    for factor in [block / 16, 2]:
        x, y = small_w, small_h
        while x >= 4 and y >= 4:
            r.take(int(x * y * factor))
            x //= 2
            y //= 2
    r.end()
    return w, h, decode(base, w, h)


def png(width, height, pixels, channels=3):
    def chunk(tag, b):
        return (
            struct.pack(">I", len(b))
            + tag
            + b
            + struct.pack(">I", zlib.crc32(tag + b) & 0xFFFFFFFF)
        )

    raw = b"".join(
        b"\0" + pixels[y * width * channels : (y + 1) * width * channels] for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2 if channels == 3 else 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def multiply(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)
    ]


def inverse(m):
    a = [row[:] + [float(i == j) for j in range(4)] for i, row in enumerate(m)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda i: abs(a[i][col]))
        if abs(a[pivot][col]) < 1e-10:
            raise ValueError("singular bind")
        a[col], a[pivot] = a[pivot], a[col]
        d = a[col][col]
        a[col] = [v / d for v in a[col]]
        for i in range(4):
            if i != col:
                factor = a[i][col]
                a[i] = [v - factor * w for v, w in zip(a[i], a[col])]
    return [row[4:] for row in a]


def matrix(p, q):
    x, y, z, w = q
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), p[0]],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), p[1]],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), p[2]],
        [0, 0, 0, 1],
    ]


def converted(node, frame, scale):
    p = sample(node["keys"][0], frame, node["translation"])
    q = sample(node["keys"][1], frame, node["rotation"])
    return [p[0] * scale, p[1] * scale, -p[2] * scale], [-q[0], -q[1], q[2], q[3]]


def joint_bounds(bones):
    """KO's character joint bounds (0041c300, binary; PQ-301), as the target
    marker and the nameplate style read them: (radius, top). 0041c300 reads
    the character's current frame +0x1dc and poses the joints at it (slot
    +0x20, then 00418e00). The constructor sets it to 0 (00417768/0041784d)
    and the joint set 0041b000 calls 0041c300 (0041b1f0) before the looks set
    starts a clip (0045de41), so frame 0 for a fresh character (inference;
    the reused-character path is not traced), as here. It takes
    the joints' positions (+0x84..+0x8c), grows an axis shorter than 0.5 by
    0.25 at each end, and stores the minimum at +0x11c, the maximum at +0x128
    and half the diagonal at +0x118. The height getter 00459ff0, the NPC name
    callback 00459820 and the player name anchor 00459fa0 read the maximum's
    y, +0x12c (actor +0x17c): the top of
    the padded box above the character's origin, not its span."""
    world = []
    for bone in bones:
        m = matrix(*converted(bone, 0, 1.0))
        world.append(multiply(world[bone["parent"]], m) if bone["parent"] >= 0 else m)
    low = [min(m[a][3] for m in world) for a in range(3)]
    high = [max(m[a][3] for m in world) for a in range(3)]
    spans = [h - l for l, h in zip(low, high)]
    radius = math.sqrt(sum((v + 0.5 if v < 0.5 else v) ** 2 for v in spans)) * 0.5
    return radius, high[1] + 0.25 if spans[1] < 0.5 else high[1]


class Assets:
    def __init__(self, root):
        self.root = root.resolve()
        self.sources = {}

    def get(self, name):
        self.last = name  # named in a refusal (PQ-254)
        path = self.root
        parts = [p for p in name.replace("\\", "/").split("/") if p]
        if (
            not parts
            or name.startswith(("/", "\\"))
            or any(p in (".", "..") or ":" in p for p in parts)
        ):
            raise ValueError("unsafe KO dependency")
        for part in parts:
            candidates = [
                p for p in path.iterdir() if p.name.casefold() == part.casefold()
            ]
            if len(candidates) != 1:
                raise ValueError("missing/ambiguous KO dependency: " + name)
            path = candidates[0]
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("KO dependency containment")
        data = read(path)
        self.sources[str(path.relative_to(self.root))] = hashlib.sha256(
            data
        ).hexdigest()
        return data


def wrapped_uv(corners, w, h, border, limit=1024):
    """(corners, region, record) for one part's maximum-detail corner UVs on a
    w x h texture (PQ-264).

    KO draws a character part with wrap texture addressing (inference from
    binary reads; record: docs/implementation/evidence/
    pq-264-ko-character-wrapping-uv.md): the part renderer `00412570`
    (KnightOnLine.exe) binds the part's texture to stage 0 and sets no stage-0
    address state; every other stage-0 address write the disassembled client
    makes (`0043dd80`, the terrain at `0059d0ca`, `005acc55`) is written back
    from the value read before it before its function returns; and the state
    set-up `0043ade0` (by inference) sets no address
    mode, which leaves Direct3D 8's documented default, wrap. Under wrap a UV
    and that UV plus a whole number sample the same texel.

    A part whose corners stay inside 0..1 (within the tolerance the converter
    has always allowed: one texel with the player gutter, 0.0001 without)
    keeps its corners and the region (0, w, 0, h), so its output is
    unchanged, and the record is None. Otherwise each triangle with a corner
    outside that range is moved, per axis, by the whole number that leaves the
    least of it outside 0..1 (the smaller move on a tie), and the region grows,
    in texels, to cover every moved corner; the caller fills it with the
    texture repeated, so the atlas samples what KO's wrap samples. A region
    wider or taller than the atlas (`limit`, 1024 texels unless the caller
    is the front end, spec 11) is refused."""
    sizes = (w, h)

    def inside(v, size):
        return not (v < (-1 / size if border else -0.0001) or v > (1 + 1 / size if border else 1.0001))

    if all(inside(v, size) for uv in corners for v, size in zip(uv, sizes)):
        return corners, (0, w, 0, h), None
    shifted, moved = [], 0
    for t in range(0, len(corners), 3):
        triangle = corners[t:t + 3]
        shift = []
        for axis, size in enumerate(sizes):
            values = [uv[axis] for uv in triangle]
            if all(inside(v, size) for v in values):
                shift.append(0)
                continue
            lo, hi = min(values), max(values)
            shift.append(min(sorted({math.floor(lo), math.ceil(hi) - 1}),
                             key=lambda k: (max(0, k - lo) + max(0, hi - k - 1), abs(k))))
        moved += any(shift)
        shifted.extend([uv[0] - shift[0], uv[1] - shift[1]] for uv in triangle)
    region = []
    for axis, size in enumerate(sizes):
        lo = min(0, math.floor(min(uv[axis] for uv in shifted) * size))
        hi = max(size, math.ceil(max(uv[axis] for uv in shifted) * size))
        if hi - lo + 2 * border > limit:
            raise ValueError("wrapping UV region past the %d-texel atlas" % limit)
        region += [lo, hi]
    return shifted, tuple(region), {"region_texels": [region[0], region[2], region[1], region[3]],
                                    "shifted_triangles": moved}


# A held (zero-length) clip's two keys are one sample of the converter's 60 Hz
# grid apart (PQ-273): KO's tick 00418b20 counts such a clip played (+0x1e4)
# on its first frame advance after any entry blend, a time that depends on the
# frame rate; the pose is the same.
HELD_SECONDS = 1 / 60

# The rest pose of a character whose clip table has no clips (PQ-268, D-178;
# record: docs/implementation/evidence/pq-268-ko-npc-looks-without-clips.md).
# KO's clip starts 0041be40, 0041c160 and 0041c000 start nothing on such a
# table, the frame tick 00418b20 returns without a clip, and the render
# 004196a0 still poses every joint (00418e00) at the current frame, which the
# clip table set (0041bd30, or the .n3chr load 00418020) left at 0 with no
# blend (KnightOnLine.exe, binary). So the character shows its joints at frame
# 0; it converts as that pose held (two keys HELD_SECONDS apart, as PQ-273's
# held clips), with no blend, no loop and no strike frame; every joint's
# rotation is written as a held track, so a skeleton without keys (the
# crystals and three of the guard stones, local-asset) still has a duration.
REST_CLIP = {"name": "rest", "start": 0.0, "end": 0.0, "fps": 30.0, "trace": [0.0, 0.0], "sound": [0.0, 0.0],
             "blend_seconds": 0.0, "blend_flags": 0, "strike": [0.0, 0.0]}


# PQ-281 (D-177; record:
# docs/implementation/evidence/pq-281-ko-skin-nonfinite-normals.md). KO draws
# a part vertex with its normal as loaded: the mesh load 00440870 reads it,
# the skinning 00419f00 writes only the position and the vertex build
# 004401b0 / 00440440 copies the normal unchanged into the lit draw
# (KnightOnLine.exe, binary), so a zero normal gets no directional light
# (inference). n3e's lighting uses a normal's direction only, so a drawn
# corner whose normal has none (non-finite, or a squared length below the
# glTF cooker's 1e-12) is written with its own triangle's unit normal, from
# the skin origins in file winding ((b - a) x (c - a), the side the loaded
# normals face: local-asset). Every other corner keeps its normal as read.
NO_DIRECTION = 1e-12


def corner_normals(skin):
    """Each drawn corner's normal (source basis) and the set of vertices
    whose normal was rebuilt. A corner without a normal on a triangle whose
    cross product is zero is refused by name."""
    ix = skin["indices"]
    normals, rebuilt = [], set()
    for t in range(0, len(ix), 3):
        face = None
        for v in ix[t:t + 3]:
            n = skin["vertices"][v][3:]
            if all(math.isfinite(x) for x in n) and sum(x * x for x in n) >= NO_DIRECTION:
                normals.append(n)
                continue
            if face is None:
                a, b, c = (skin["origins"][i] for i in ix[t:t + 3])
                u = [b[k] - a[k] for k in range(3)]
                w = [c[k] - a[k] for k in range(3)]
                x = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
                length = math.sqrt(sum(e * e for e in x))
                if length == 0:
                    raise ValueError("KO skin vertex without a normal on a zero-area triangle")
                face = [e / length for e in x]
            normals.append(face)
            rebuilt.add(v)
    return normals, rebuilt


def convert(root, source, out, clip_index=1, meters=1.0, definition=None, player=None, assets=None,
            front_end=False):
    """`player` (default: whether a definition is given) selects the player
    path's atlas gutter and 60 Hz clamped sample times; an NPC looks row
    passes a definition with player=False and converts as the worm does.
    `assets` (default: a new reader of `root`) lets the caller name the last
    file read when the conversion is refused. `clip_index` None converts
    the rest pose of a clip table without clips (REST_CLIP); a table with
    clips is then refused.

    `front_end` (spec 11, ko_front_end only) converts the login and select
    models: a clip's unused first word is accepted (animations), part textures
    may be 1024 texels a side in a 2048-texel atlas, and parts with the same
    texture and region share one atlas placement (the intro orc's nine head
    parts share one 1024-texel texture). Every other caller keeps its output
    byte for byte."""
    atlas_limit = 2048 if front_end else 1024
    if player is None:
        player = definition is not None
    if not math.isfinite(meters) or not 0 < meters <= 100:
        raise ValueError("explicit scale bound")
    out = out.resolve()
    build = pathlib.Path("build").resolve()
    if not out.is_relative_to(build) or out == build:
        raise ValueError("local KO outputs must be below build/")
    assets = assets if assets is not None else Assets(root)
    source_data = assets.get(source)
    ch = copy.deepcopy(definition) if definition is not None else character(source_data)
    bones = skeleton(assets.get(ch["joint"]), scaled=True, limit=MAX_JOINTS)
    clips = animations(assets.get(ch["animation"]), empty=clip_index is None, unused_word=front_end)
    if clip_index is None:
        if clips:
            raise ValueError("rest pose asked for a table of %d clips" % len(clips))
        clip = REST_CLIP
    elif not 0 <= clip_index < len(clips):
        raise ValueError("clip %d past the table's %d clips" % (clip_index, len(clips)))
    else:
        clip = clips[clip_index]
    if clip["end"] < clip["start"]:
        raise ValueError("clip ends before it starts")
    # A clip that starts and ends on one frame is a held pose in KO (PQ-273,
    # D-169): the clip start 0041be40 sets the frame to the start, the frame
    # tick 00418b20 clamps it up to the start and, past the end, sets it to the
    # end or back to the start (no length to wrap by), the same frame, and
    # 00418e00 poses every joint at that frame. It converts as two identical
    # keys one 60 Hz sample apart.
    held = clip["end"] == clip["start"]
    duration = HELD_SECONDS if held else (clip["end"] - clip["start"]) / clip["fps"]
    samples = 2 if held else math.ceil(duration * 60) + 1
    count(samples, 4096, 2)
    parts = [part(assets.get(p)) for p in ch["parts"]]
    textures = [texture(assets.get(p["texture"]), 1024 if front_end else 512) for p in parts]
    # PQ-265 (D-173): a model whose parts all have the opaque render state and
    # whose textures have no texel below alpha 255 converts exactly as before
    # (RGB atlas, one glTF primitive). Any other model keeps the atlas's alpha
    # and gives each run of consecutive parts with one render state its own
    # primitive and material, in part order, the order 004196a0 draws them.
    states = [p["render_state"] for p in parts]
    materials = any(st != OPAQUE_STATE for st in states) or any(min(px[3::4]) < 255 for _, _, px in textures)
    channels = 4 if materials else 3
    if materials and player:
        # Only NPC looks models (N3MM) draw render states; the player's scenes
        # stay N3S1 (queued with the appearance work, PQ-047).
        raise ValueError("KO part render states and alpha are drawn for NPC looks only, not on the player path")
    # A two-pixel repeat gutter preserves the player hand's subpixel wrapping UVs.
    border = 2 if player else 0
    # Skins are read in part order after the textures, as before PQ-264; each
    # part's corner UVs then pick its atlas region (wrapped_uv).
    meshes = []
    for (w, h, _), p in zip(textures, parts):
        name, lods = skins(assets.get(p["skin"]), every=True)
        skin = lods[0]
        if not skin["indices"]:
            raise ValueError("empty maximum-detail skin")
        if any(max(j) >= len(bones) for j in skin["joints"]):
            raise ValueError("missing joint")
        corners = [skin["uv"][i] for i in skin["uv_indices"]]
        meshes.append((name, lods, skin) + wrapped_uv(corners, w, h, border, atlas_limit) + corner_normals(skin))
    if front_end:
        # One region per texture: the union of its parts' (wrapped) regions.
        union = {}
        for p, m in zip(parts, meshes):
            k, (x0, x1, y0, y1) = p["texture"].casefold(), m[4]
            u = union.get(k, (x0, x1, y0, y1))
            union[k] = (min(u[0], x0), max(u[1], x1), min(u[2], y0), max(u[3], y1))
        for x0, x1, y0, y1 in union.values():
            if max(x1 - x0, y1 - y0) + 2 * border > atlas_limit:
                raise ValueError("shared texture region past the atlas")
        meshes = [m[:4] + (union[p["texture"].casefold()],) + m[5:] for p, m in zip(parts, meshes)]
    atlas_w = min(atlas_limit, sum(m[4][1] - m[4][0] + border * 2 for m in meshes))
    # The front end packs each texture's region once, tallest first.
    keys = [p["texture"].casefold() if front_end else i for i, p in enumerate(parts)]
    regions = dict(zip(keys, (m[4] for m in meshes)))
    order = sorted(regions, key=lambda k: (-(regions[k][3] - regions[k][2]), -(regions[k][1] - regions[k][0]))) \
        if front_end else list(regions)
    placed = {}
    x = y = row_h = 0
    for k in order:
        x0, x1, y0, y1 = regions[k]
        tw, th = x1 - x0 + border * 2, y1 - y0 + border * 2
        if x + tw > atlas_w:
            y += row_h; x = row_h = 0
        placed[k] = (x, y)
        x += tw; row_h = max(row_h, th)
    placements = [placed[k] for k in keys]
    atlas_h = y + row_h
    if atlas_h > atlas_limit:
        raise ValueError("atlas dimensions")
    atlas = bytearray(atlas_w * atlas_h * channels)
    # PQ-283 (D-176): every influence of a drawn vertex, as read and in file
    # order, the first four in JOINTS_0 / WEIGHTS_0 and the rest in further
    # sets (KO's skinning 00419f00 sums every one). A model without a drawn
    # vertex past four influences writes the one set, as before.
    most = max(len(m[2]["joints"][v]) for m in meshes for v in m[2]["indices"])
    sets = (most + 3) // 4
    if sets > 1 and player:
        # Only NPC looks models (N3NI, N3MI) carry further influences; the
        # player's scenes stay N3S1 (PQ-280).
        raise ValueError("KO skin vertices past four joint influences are drawn for NPC looks only, "
                         "not on the player path")
    attributes = {
        k: [] for k in ["POSITION", "NORMAL", "TEXCOORD_0"] + ["%s_%d" % (a, n) for n in range(sets)
                                                               for a in ("JOINTS", "WEIGHTS")]
    }
    indices = []
    part_info = []
    part_first = []
    for p, (w, h, pixels), (offset, offset_y), (name, lods, skin, shifted, (x0, x1, y0, y1), wrapped, normals,
                                                 _) in zip(parts, textures, placements, meshes):
        # The region repeats the texture (KO samples parts with wrap addressing,
        # PQ-264); a part inside 0..1 has the region (0, w, 0, h) as before.
        for row in range(y0 - border, y1 + border):
            for col in range(x0 - border, x1 + border):
                at = ((row - y0 + border + offset_y) * atlas_w + col - x0 + border + offset) * channels
                source_at = ((row % h) * w + col % w) * 4
                atlas[at:at+channels] = pixels[source_at:source_at+channels]
        for corner, vertex in enumerate(skin["indices"]):
            origin = skin["origins"][vertex]
            normal = normals[corner]
            uv = shifted[corner]
            attributes["POSITION"].append(
                [origin[0] * meters, origin[1] * meters, -origin[2] * meters]
            )
            attributes["NORMAL"].append([normal[0], normal[1], -normal[2]])
            attributes["TEXCOORD_0"].append(
                [
                    (offset + border + ((uv[0] * w if border else min(x1 - 0.5, max(x0 + 0.5, uv[0] * w))) - x0)) / atlas_w,
                    (offset_y + border + ((uv[1] * h if border else min(y1 - 0.5, max(y0 + 0.5, uv[1] * h))) - y0)) / atlas_h,
                ]
            )
            js = skin["joints"][vertex] + [0] * (4 * sets - len(skin["joints"][vertex]))
            ws = skin["weights"][vertex] + [0.0] * (4 * sets - len(skin["weights"][vertex]))
            for n in range(sets):
                attributes["JOINTS_%d" % n].append(js[4 * n:4 * n + 4])
                attributes["WEIGHTS_%d" % n].append(ws[4 * n:4 * n + 4])
        base = len(indices)
        part_first.append(base)
        for i in range(len(skin["indices"]) // 3):
            indices.extend([base + i * 3, base + i * 3 + 2, base + i * 3 + 1])
        info = {
            "name": name,
            "lod_vertices": [len(l["vertices"]) for l in lods],
            "triangles": len(skin["indices"]) // 3,
            "material": p["material"],
        }
        if wrapped is not None:
            info["wrapped_uv"] = wrapped
        if materials:
            info["render_state"] = p["render_state"]
        part_info.append(info)
    count(len(indices), 65536)
    # PQ-267 (D-175): a skeleton past 64 joints skins with the joints that
    # carry weight in the drawn skin (any influence, PQ-283), in joint order
    # (exact: a joint without weight moves no drawn vertex); every joint
    # keeps its node and tracks.
    skin_joints = list(range(len(bones)))
    if len(bones) > 64:
        skin_joints = sorted({j for n in range(sets)
                              for js, ws in zip(attributes["JOINTS_%d" % n], attributes["WEIGHTS_%d" % n])
                              for j, w in zip(js, ws) if w > 0})
        if len(skin_joints) > 64:
            raise ValueError("%d weighted KO joints past the skin's 64" % len(skin_joints))
        slot = {j: i for i, j in enumerate(skin_joints)}
        for n in range(sets):
            attributes["JOINTS_%d" % n] = [[slot.get(j, 0) for j in js] for js in attributes["JOINTS_%d" % n]]
    runs = []  # (first index, end index, state)
    for k, st in enumerate(states):
        end = part_first[k + 1] if k + 1 < len(part_first) else len(indices)
        if runs and runs[-1][2] == st:
            runs[-1] = (runs[-1][0], end, st)
        else:
            runs.append((part_first[k], end, st))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, len(bones)]}],
        "nodes": [],
        "skins": [],
        "meshes": [],
        "accessors": [],
        "bufferViews": [],
        "buffers": [],
        "animations": [],
        "images": [{"uri": "atlas.png"}],
        "textures": [{"source": 0}],
        "materials": ([{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}},
                        "extensions": {"N3E_render_state": st}} for _, _, st in runs] if materials
                      else [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]),
    }
    binary = bytearray()

    def accessor(rows, kind, component=5126):
        while len(binary) % 4:
            binary.append(0)
        start = len(binary)
        fmt = {5126: "f", 5123: "H", 5125: "I"}[component]
        for row in rows:
            binary.extend(struct.pack("<" + fmt * len(row), *row))
        view = len(g["bufferViews"])
        g["bufferViews"].append(
            {"buffer": 0, "byteOffset": start, "byteLength": len(binary) - start}
        )
        index = len(g["accessors"])
        g["accessors"].append(
            {
                "bufferView": view,
                "componentType": component,
                "count": len(rows),
                "type": kind,
            }
        )
        return index

    # A scaled joint (PQ-266; record:
    # docs/implementation/evidence/pq-266-ko-character-joint-scale.md). KO's
    # joint matrix 00427a50 is the rotation matrix times the scale matrix
    # (row vectors: rotate, then scale along the parent's axes), with the
    # position put in after, times the parent's matrix. In column form that is
    # T S R, which one glTF node (T R S) cannot hold when the scale is not
    # uniform. So the joint keeps its node (index i, its rotation) and gets a
    # parent node after the mesh node carrying its translation and scale: the
    # pair composes to T S R exactly. The mirror (x, y, -z) leaves a diagonal
    # scale as it is. A skeleton without a scaled joint converts as before.
    helper = {}
    for i, b in enumerate(bones):
        if is_scaled(b):
            helper[i] = len(bones) + 1 + len(helper)
    if len(bones) + 1 + len(helper) > 128:
        raise ValueError("scaled KO joints past the 128-node scene")

    def top(i):
        return helper.get(i, i)

    def scale_at(b, frame):
        return sample(b["keys"][2], frame, b["scale"])

    world = []
    inverses = []
    helpers = []
    for i, b in enumerate(bones):
        p, q = converted(b, 0, meters)
        children = [top(j) for j, n in enumerate(bones) if n["parent"] == i]
        if i in helper:
            s = scale_at(b, 0)
            node = {"name": b["name"], "translation": [0, 0, 0], "rotation": q}
            helpers.append({"name": b["name"] + " scale", "translation": p, "scale": s, "children": [i]})
            m = multiply(multiply(matrix(p, [0, 0, 0, 1]), [[s[0], 0, 0, 0], [0, s[1], 0, 0], [0, 0, s[2], 0],
                                                            [0, 0, 0, 1]]), matrix([0, 0, 0], q))
        else:
            node = {"name": b["name"], "translation": p, "rotation": q}
            m = matrix(p, q)
        if children:
            node["children"] = children
        g["nodes"].append(node)
        if b["parent"] >= 0:
            m = multiply(world[b["parent"]], m)
        world.append(m)
        iv = inverse(m)
        inverses.append([iv[row][col] for col in range(4) for row in range(4)])
    g["nodes"].append({"mesh": 0, "skin": 0})
    g["nodes"] += helpers
    g["scenes"][0]["nodes"] = [top(0), len(bones)]
    g["skins"] = [
        {
            "joints": skin_joints,
            "inverseBindMatrices": accessor([inverses[j] for j in skin_joints], "MAT4"),
        }
    ]
    attrs = {
        k: accessor(
            v,
            (
                "VEC2"
                if k == "TEXCOORD_0"
                else "VEC4" if k.startswith(("JOINTS_", "WEIGHTS_")) else "VEC3"
            ),
            5123 if k.startswith("JOINTS_") else 5126,
        )
        for k, v in attributes.items()
    }
    g["meshes"] = [
        {
            "primitives": [
                {
                    "attributes": attrs,
                    "indices": accessor([[i] for i in indices[first:end]], "SCALAR", 5125),
                    "material": m,
                }
                for m, (first, end, _) in enumerate(runs if materials else [(0, len(indices), None)])
            ]
        }
    ]
    if materials:
        g["extensionsUsed"] = ["N3E_render_state"]
    times = [min(i / 60, duration) if player else i * duration / (samples - 1) for i in range(samples)]
    time_acc = accessor([[t] for t in times], "SCALAR")
    anim = {"name": clip["name"], "samplers": [], "channels": []}
    for i, b in enumerate(bones):
        frames = [clip["start"] + (0 if held else t * clip["fps"]) for t in times]
        poses = [converted(b, frame, meters) + (scale_at(b, frame),) for frame in frames]
        # A scaled joint's translation and scale tracks drive its helper node,
        # its rotation track the joint's own node.
        for component, path, kind, node in [
            (0, "translation", "VEC3", top(i)),
            (1, "rotation", "VEC4", i),
            (2, "scale", "VEC3", top(i)),
        ]:
            # The rest pose also writes every joint's rotation as a held
            # track, so a skeleton without keys still has tracks (N3LK and
            # the client measure a clip's duration from them; PQ-268).
            if b["keys"][component] is None and not (clip_index is None and component == 1):
                continue
            index = len(anim["samplers"])
            anim["samplers"].append(
                {
                    "input": time_acc,
                    "output": accessor([p[component] for p in poses], kind),
                    "interpolation": "LINEAR",
                }
            )
            anim["channels"].append(
                {"sampler": index, "target": {"node": node, "path": path}}
            )
    g["animations"] = [anim]
    g["buffers"] = [{"uri": "character.bin", "byteLength": len(binary)}]
    recipe = copy.deepcopy(
        json.loads(pathlib.Path("tests/fixtures/legacy-demo/package.json").read_text())
    )
    recipe["game_id"] = "kotest"
    recipe["assets"][0]["id"] = "kotest:scene/monster"
    recipe["assets"][0]["source"] = "character.gltf"
    recipe["properties"][0]["key"] = "kotest:lighting.intensity"
    for key in ["action", "item", "npc"]:
        recipe["gameplay"][key] = recipe["gameplay"][key].replace("demo:", "kotest:")
    meta = json.loads(pathlib.Path("tests/fixtures/legacy-demo/scene.json").read_text())
    meta["instance_scale"] = [1, 1, 1]
    meta["attachment_node"] = 0
    meta["markers"] = [
        {"name": f"strike_{i}", "time": (frame - clip["start"]) / clip["fps"]}
        for i, frame in enumerate(clip["strike"])
        if clip["start"] <= frame <= clip["end"] and frame > 0
    ]
    provenance = {
        "adapter_version": 1,
        "source_character": source,
        "sources": assets.sources,
        "meters_per_source_unit": meters,
        "scale_policy": "explicit local test assumption, not official KO unit calibration",
        "coordinate_conversion": "(x,y,-z), quaternion (-x,-y,z,w), reverse triangle winding; UV unchanged top-left",
        "character_metadata": ch,
        "animations": clips,
        "selected_clip": clip_index,
        "parts": part_info,
        "joint_count": len(bones),
        "render_vertices": len(indices),
        "duration_seconds": duration,
        "sample_rate_hz": 60,
        "omissions": [
            "LOD1-3 not rendered",
            "source material ambient/specular and audio/blend/trace metadata preserved here, not executed",
            "one selected looping clip; no movement/combat clip switching",
            "both player and NPC use the one package visual",
            "synthetic zone collision, not KO world collision",
            "source meshes/textures and derivatives remain local build outputs",
        ],
    }
    if held:
        provenance["held_frame"] = clip["start"]
    if clip_index is None:
        provenance["rest_pose"] = clip
    if sets > 1:
        # The drawn vertices past four influences (PQ-283).
        provenance["many_influences"] = {
            "vertices": sum(1 for m in meshes for v in sorted(set(m[2]["indices"])) if len(m[2]["joints"][v]) > 4),
            "most": most, "sets": sets}
    if any(m[7] for m in meshes):
        # The drawn vertices and corners given their triangle's normal (PQ-281).
        provenance["rebuilt_normals"] = {
            "vertices": sum(len(m[7]) for m in meshes),
            "corners": sum(1 for m in meshes for v in m[2]["indices"] if v in m[7]),
        }
    if len(skin_joints) != len(bones):
        provenance["skin_joints"] = skin_joints
    if helper:
        # Each scaled joint's node and its translation and scale node (PQ-266).
        provenance["scaled_joints"] = [{"joint": i, "name": bones[i]["name"], "scale_node": h}
                                       for i, h in sorted(helper.items())]
    out.mkdir(parents=True, exist_ok=True)
    for name, obj in [
        ("character.gltf", g),
        ("package.json", recipe),
        ("scene.json", meta),
        ("provenance.json", provenance),
    ]:
        (out / name).write_bytes(canonical(obj))
    (out / "character.bin").write_bytes(binary)
    (out / "atlas.png").write_bytes(png(atlas_w, atlas_h, bytes(atlas), channels))
    return provenance


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=pathlib.Path, required=True)
    p.add_argument("--character", default="Chr/mob_worm.n3chr")
    p.add_argument("--clip", type=int, default=1)
    p.add_argument("--meters-per-unit", type=float, required=True)
    p.add_argument("--out", type=pathlib.Path, required=True)
    a = p.parse_args()
    try:
        report = convert(a.root, a.character, a.out, a.clip, a.meters_per_unit)
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in [
                        "source_character",
                        "joint_count",
                        "render_vertices",
                        "selected_clip",
                        "duration_seconds",
                    ]
                },
                indent=2,
            )
        )
    except (ValueError, OSError, UnicodeError, struct.error) as e:
        p.exit(1, "KO character rejected: " + str(e) + "\n")


def animation_metadata(report):
    clip = report['rest_pose'] if report['selected_clip'] is None else report['animations'][report['selected_clip']]
    duration = report['duration_seconds']
    return dict(duration=duration, blend=clip['blend_seconds'],
                loop_blend=bool(clip['blend_flags'] & 1),
                markers=[(v-clip['start'])/clip['fps'] if v > 0 and clip['start'] <= v <= clip['end'] else -1 for v in clip['strike']])
