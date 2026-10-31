"""N3W2: a built world split into a square grid of self-contained chunks.

PQ-231, D-159. Generic: no game IDs, paths or rules. The input is what the N3W1
and N3L3 writers already take, without the atlas: the world's texture count
(its textures are a separate N3WT asset, `world_textures.py`, PQ-233), 12-float
vertices (position, normal, two UV layers, two texture slots) and N3L3-shaped parts (a part without a kind, as N3L1/N3L2 write it, is
kind 0: plain distance levels), parents
and an optional terrain policy (`ko_lod.serialize`). Each part goes to the grid
cell of its position: a progressive part (kind 1) to its parent's, so a parent
and its parts share a chunk; a terrain patch to its patch centre's; every other
part to its sphere centre. A chunk
carries its own vertices, with every index chunk-local, its own parents and parts,
and a box that covers every part sphere it holds.

Terrain patches keep their global patch coordinates and the terrain policy sits
in the header, so neighbour-edge selection never depends on chunk boundaries. A
terrain patch (kind 2) goes to the cell of its patch centre (PQ-232), so the
client can check each streamed chunk holds exactly its cell's patches.
The client (client/assets/assets.cpp `load_world`) applies the same bounds.

N3W3 (PQ-379, D-201) is N3W2 whose kind 0 and kind 1 parts may be alpha parts
(flag bit 4, `ALPHA`), each followed by its alpha record (`alpha_bytes`).
N3W4 (PQ-382, D-202) is N3W3 whose kind 0 and kind 1 parts that are not alpha
parts may set bit 5 (`CUT_ZERO`) and bit 6 (`UNLIT`); `layout` picks the magic.
N3W5 (PQ-388, D-203) is N3W4 whose vertices may set the second-layer slot to
`UNLIT_VERTEX` (-1): a single-layer unlit vertex, drawn as its first layer's
texel without a second layer or light. `serialize` writes N3W5 only when a
vertex carries it; N3W1 and the N3L files cannot.
N3W6 (PQ-394, D-212) is N3W5 whose kind 0 and kind 1 parts may set bit 7
(`SEQUENCE`), each then carrying a texture-sequence record after its alpha
record (`sequence_bytes`): frame k draws its slot in place of the first-layer
slot. `serialize` writes N3W6 only when a part sets the bit.
"""
import math
import struct

from common import f, u
from world_textures import MAX_TEXTURES

MAX_FILE = 384 * 1024 * 1024
# Every chunked world magic, N3W2 to N3W6.
MAGICS = (b"N3W2", b"N3W3", b"N3W4", b"N3W5", b"N3W6")
MAX_SIDE = 64
MIN_SIZE, MAX_SIZE = 1.0, 4096.0
# One chunk keeps N3W1's vertex cap and N3L3's index, part and work caps.
CHUNK_VERTICES = 196608
LEVEL_INDICES = 589824
CHUNK_INDICES = 2000000
CHUNK_PARTS = 8192
CHUNK_PARENTS = 8192
CHUNK_WORK = 2000000
# Totals sized for a 2048 m (513-sample) zone: PQ-055 estimates about 2.6 M
# vertices and 21 M indices for a homeland; these leave headroom over both.
TOTAL_VERTICES = 4194304
TOTAL_INDICES = 33554432
TOTAL_PARTS = 65536
TOTAL_PARENTS = 65536
TOTAL_WORK = 16777216
# D-201 (PQ-379): part flag bit 4 marks an alpha part, drawn in the frame's one
# far-to-near alpha pass rather than the world pass; it carries an alpha record
# after its kind's fields. A world with one is written as N3W3 (and its LOD
# file as N3L4, ko_lod.serialize); without one the bytes stay N3W2 / N3L3.
ALPHA = 16
# The record's state bits: 1 blend (required), 0x40 unlit, 0x80 diffuse alpha,
# 0x100 no depth write, 0x400 no depth test. Fog and culling stay the part's
# flag bits 0 and 3.
ALPHA_STATES = 0x1 | 0x40 | 0x80 | 0x100 | 0x400
ALPHA_LIMIT = 1e6
# D-202 (PQ-382): a part that is not an alpha part may be cut only where its
# texture's 8-bit alpha is 0 (bit 5, Direct3D's GREATER against reference 0)
# instead of below one half, and drawn without light (bit 6). A world with one
# is written as N3W4 (its LOD file as N3L5); neither bit on an alpha part or a
# terrain patch.
CUT_ZERO = 32
UNLIT = 64
OPAQUE_BITS = CUT_ZERO | UNLIT
PART_FLAGS = 127
# D-212 (PQ-394): bit 7 marks a part with a texture sequence: u32 frame count
# (2..64), f32 fps (finite, 0 < fps <= 1000), u32 slot per frame (each below
# the world's texture count), after the alpha record. Every vertex the part
# names carries frame 0's slot as its first slot. Only N3W6 carries it; the
# N3L files keep PART_FLAGS.
SEQUENCE = 128
SEQUENCE_FRAMES = (2, 64)
SEQUENCE_FPS = 1000.0
# D-203 (PQ-388): the second-layer slot of a single-layer unlit vertex. Only
# N3W5 carries it; every other slot names a texture below the world's count.
UNLIT_VERTEX = -1.0


def has_alpha(parts):
    return any(p["flags"] & ALPHA for p in parts)


def layout(parts):
    """0 for the N3L3 / N3W2 layout, 1 with an alpha part (N3L4 / N3W3, D-201),
    2 with a part setting bit 5 or 6 (N3L5 / N3W4, D-202): the lowest that
    holds the parts, so a world keeps its bytes until it needs the next."""
    if any(p["flags"] & OPAQUE_BITS for p in parts):
        return 2
    return 1 if has_alpha(parts) else 0


def has_sequence(parts):
    return any(p["flags"] & SEQUENCE for p in parts)


def sequence_bytes(part, textures):
    """A sequence part's record (D-212): u32 frame count, f32 fps, u32 slot per
    frame; empty for a part without the bit. `textures` is the world's count."""
    record = part.get("sequence")
    if not part["flags"] & SEQUENCE:
        if record is not None:
            raise ValueError("world sequence record without the sequence flag")
        return b""
    if record is None or part.get("kind", 0) == 2:
        raise ValueError("world sequence part record")
    slots, fps = list(record["slots"]), record["fps"]
    lo, hi = SEQUENCE_FRAMES
    if not (lo <= len(slots) <= hi and math.isfinite(fps) and 0 < _f32(fps) <= SEQUENCE_FPS
            and all(s == int(s) and 0 <= s < textures for s in slots)):
        raise ValueError("world sequence part record")
    return u(len(slots)) + f([fps]) + b"".join(u(int(s)) for s in slots)


def _sequence_vertices(part, vertices):
    """The vertex indices a sequence part draws, for the frame-0 slot check."""
    if part.get("kind", 0) == 1:
        return range(part["base"], part["base"] + part["max_vertices"])
    return {i for _, ix in part["levels"] for i in ix}


def alpha_bytes(part):
    """An alpha part's record (D-201): u32 source and destination blend (1..10),
    u32 state, f32 sort point[3]; empty for a part without the flag."""
    record = part.get("alpha")
    flags = part["flags"]
    if flags & ~(PART_FLAGS | SEQUENCE) or (flags & OPAQUE_BITS and (flags & ALPHA or part.get("kind", 0) == 2)):
        raise ValueError("world part flags 0x%x" % flags)
    if not part["flags"] & ALPHA:
        if record is not None:
            raise ValueError("world alpha record without the alpha flag")
        return b""
    if record is None or part.get("kind", 0) == 2:
        raise ValueError("world alpha part record")
    source, destination, state, point = record["source"], record["destination"], record["state"], record["point"]
    if not (1 <= source <= 10 and 1 <= destination <= 10 and state & 1 and not state & ~ALPHA_STATES
            and len(point) == 3 and all(math.isfinite(c) and abs(c) <= ALPHA_LIMIT for c in point)):
        raise ValueError("world alpha part record")
    return u(source) + u(destination) + u(state) + f(list(point))


def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _step(y, down):
    """The next float32 below (down) or above y."""
    if y == 0:
        return struct.unpack("<f", struct.pack("<I", 0x80000001 if down else 1))[0]
    bits = struct.unpack("<I", struct.pack("<f", y))[0]
    bits += -1 if (y > 0) == down else 1
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def _floor32(x):
    y = _f32(x)
    return y if y <= x else _step(y, True)


def _ceil32(x):
    y = _f32(x)
    return y if y >= x else _step(y, False)


def _work(part):
    pm = part["progressive"]
    return len(pm["splits"]) + sum(s[1] for s in pm["splits"])


def _position(part, parents, terrain=None):
    kind = part.get("kind", 0)
    if kind == 1:
        p = parents[part["parent"]]
        return p[0], p[2]
    if kind == 2 and terrain is not None:
        # PQ-232: a terrain patch goes to the cell of its patch centre, which the
        # client derives from the policy alone, so each streamed chunk can be
        # checked to hold exactly its cell's patches. float32 inputs, double
        # arithmetic, as the client computes it.
        size = _f32(terrain["patch_size"])
        return (_f32(terrain["origin"][0]) + (part["patch"][0] + .5) * size,
                _f32(terrain["origin"][2]) - (part["patch"][1] + .5) * size)
    return part["center"][0], part["center"][2]


def grid(built, size):
    """The smallest grid of `size`-wide chunks, aligned to multiples of `size`,
    that holds every part's position: (origin x, origin z, side)."""
    size = _f32(size)
    terrain = built.get("terrain_lod")
    # A terrain patch's centre is placed exactly (as serialize's cell_of does);
    # every other position is rounded to float32 first.
    points = [(x, z) if p.get("kind", 0) == 2 and terrain is not None else (_f32(x), _f32(z))
              for p in built["chunks"] for x, z in [_position(p, built["parents"], terrain)]]
    if not points:
        raise ValueError("world has no parts")
    ox = _f32(math.floor(min(x for x, _ in points) / size) * size)
    oz = _f32(math.floor(min(z for _, z in points) / size) * size)
    side = 1 + max(max(math.floor((x - ox) / size), math.floor((z - oz) / size))
                   for x, z in points)
    return ox, oz, side


def serialize(textures, vertices, built, origin, size, side):
    """N3W2 bytes. `textures` is the world's texture count (the N3WT asset's);
    `vertices` the 12-float rows, whose two slots name textures below it;
    `built` the N3L3 dict (`terrain_lod` may be None)."""
    ox, oz, size = _f32(origin[0]), _f32(origin[1]), _f32(size)
    if not (MIN_SIZE <= size <= MAX_SIZE and 1 <= side <= MAX_SIDE):
        raise ValueError("world chunk grid bounds")
    if not 1 <= textures <= MAX_TEXTURES:
        raise ValueError("world texture count")
    parents, parts = built["parents"], built["chunks"]

    def cell_of(x, z, exact=False):
        gx = math.floor(((x if exact else _f32(x)) - ox) / size)
        gz = math.floor(((z if exact else _f32(z)) - oz) / size)
        if not (0 <= gx < side and 0 <= gz < side):
            raise ValueError("world part outside the chunk grid")
        return gz * side + gx

    owned = {}
    for i, p in enumerate(parents):
        owned.setdefault(cell_of(p[0], p[2]), ([], []))[0].append(i)
    for i, part in enumerate(parts):
        kind = part.get("kind", 0)
        if kind == 1 and not 0 <= part["parent"] < len(parents):
            raise ValueError("world part parent")
        if kind == 2 and built.get("terrain_lod") is None:
            raise ValueError("terrain part without a terrain policy")
        owned.setdefault(cell_of(*_position(part, parents, built.get("terrain_lod")), exact=kind == 2),
                         ([], []))[1].append(i)

    table, bodies = bytearray(), []
    totals = dict(vertices=0, indices=0, parts=0, parents=0, work=0)
    unlit = False
    chunks = sorted(k for k, v in owned.items() if v[1])
    if not chunks:
        raise ValueError("world has no parts")
    for key in chunks:
        chunk_parents, chunk_parts = owned[key]
        local_parent = {g: i for i, g in enumerate(chunk_parents)}
        order, mapping = [], {}
        out_parts, indices, work = bytearray(), 0, 0
        lo, hi = [math.inf] * 3, [-math.inf] * 3
        for g in chunk_parts:
            part = parts[g]
            levels, kind = part["levels"], part.get("kind", 0)
            if kind == 1:
                base, top = part["base"], part["base"] + part["max_vertices"]
                if not 0 <= base <= top <= len(vertices):
                    raise ValueError("progressive vertex range")
                local = len(order)
                order.extend(range(base, top))

                def remap(i, base=base, top=top, local=local):
                    if not base <= i < top:
                        raise ValueError("progressive index outside its range")
                    return i - base + local
            else:
                def remap(i):
                    if not 0 <= i < len(vertices):
                        raise ValueError("world index")
                    local = mapping.get(i)
                    if local is None:
                        local = mapping[i] = len(order)
                        order.append(i)
                    return local
            center = [_f32(c) for c in part["center"]]
            radius = _f32(part["radius"])
            for a in range(3):
                lo[a] = min(lo[a], _floor32(center[a] - radius))
                hi[a] = max(hi[a], _ceil32(center[a] + radius))
            out_parts += f([*part["center"], part["radius"], part["scale"]]) + u(part["flags"])
            out_parts += u(len(levels))
            for distance, ix in levels:
                if len(ix) > LEVEL_INDICES:
                    raise ValueError("world level index bound")
                indices += len(ix)
                out_parts += f([distance]) + u(len(ix)) + struct.pack(
                    "<%dI" % len(ix), *(remap(i) for i in ix))
            if indices > CHUNK_INDICES:
                raise ValueError("world chunk index bound")
            out_parts += u(kind)
            if kind == 2:
                out_parts += u(part["patch"][0]) + u(part["patch"][1])
            elif kind == 1:
                pm = part["progressive"]
                out_parts += u(local_parent[part["parent"]]) + u(local)
                out_parts += u(pm["min_vertices"]) + u(pm["min_indices"]) + u(part["max_vertices"])
                out_parts += u(len(pm["controls"]))
                for d, budget in pm["controls"]:
                    out_parts += f([d]) + u(budget)
                out_parts += u(len(pm["splits"]))
                for record in pm["splits"]:
                    out_parts += b"".join(u(i) for i in record)
                out_parts += u(len(pm["edits"])) + b"".join(u(i) for i in pm["edits"])
                work += _work(part)
            out_parts += alpha_bytes(part)
            out_parts += sequence_bytes(part, textures)
            if part["flags"] & SEQUENCE:
                first = part["sequence"]["slots"][0]
                if any(vertices[i][10] != first for i in _sequence_vertices(part, vertices)):
                    raise ValueError("world sequence part vertex not on frame 0")
        if (len(order) > CHUNK_VERTICES or len(chunk_parents) > CHUNK_PARENTS
                or len(chunk_parts) > CHUNK_PARTS or work > CHUNK_WORK):
            raise ValueError("world chunk bound")
        for name, n in (("vertices", len(order)), ("indices", indices), ("parts", len(chunk_parts)),
                        ("parents", len(chunk_parents)), ("work", work)):
            totals[name] += n
        body = bytearray(u(len(order)))
        rows = [struct.pack("<12f", *vertices[i]) for i in order]
        for row in rows:
            first, second = struct.unpack_from("<2f", row, 40)
            if second == UNLIT_VERTEX:
                unlit = True
                second = first
            for slot in (first, second):
                if not (0 <= slot < textures and slot == int(slot)):
                    raise ValueError("world texture slot")
        body += b"".join(rows)
        body += u(len(chunk_parents)) + b"".join(f(parents[i]) for i in chunk_parents)
        body += u(len(chunk_parts)) + out_parts
        table += u(key % side) + u(key // side) + f(lo) + f(hi) + u(len(body))
        bodies.append(bytes(body))
    if (totals["vertices"] > TOTAL_VERTICES or totals["indices"] > TOTAL_INDICES
            or totals["parts"] > TOTAL_PARTS or totals["parents"] > TOTAL_PARENTS
            or totals["work"] > TOTAL_WORK):
        raise ValueError("world total bound")

    magic = b"N3W6" if has_sequence(parts) else b"N3W5" if unlit else (b"N3W2", b"N3W3", b"N3W4")[layout(parts)]
    out = bytearray(magic + u(textures))
    out += f([ox, oz, size]) + u(side)
    terrain = built.get("terrain_lod")
    if terrain is None:
        out += u(0)
    else:
        out += u(1) + f([*terrain["origin"], terrain["patch_size"], terrain["far_factor"], terrain["bias"]])
        out += u(terrain["minimum"]) + u(terrain["band"]) + u(terrain["width"])
    out += u(len(chunks)) + table
    for body in bodies:
        out += body
    if len(out) > MAX_FILE:
        raise ValueError("world file bound")
    return bytes(out)


def n3w1_parts(data):
    """(atlas, vertices) of an N3W1 file, for writing the same world as N3W2."""
    if data[:4] != b"N3W1":
        raise ValueError("not N3W1")
    width, height, cell, pad = struct.unpack_from("<4I", data, 4)
    at = 20 + width * height * 4
    rgba = data[20:at]
    (count,) = struct.unpack_from("<I", data, at)
    rows = struct.iter_unpack("<12f", data[at + 4:at + 4 + count * 48])
    return (width, height, cell, pad, bytes(rgba)), [list(r) for r in rows]
