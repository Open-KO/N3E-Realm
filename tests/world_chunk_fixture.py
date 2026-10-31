"""Original synthetic worlds for the N3W2 checks (PQ-231). No KO data.

small(): a 32 m world of four terrain patches (kind 2) and two progressive
parts (kind 1) with their parents, written as N3W1 + N3L3 and as N3W2 so the
same geometry can be loaded and drawn both ways.

terrain(): PQ-235, a 128 m world of 4 x 4 terrain patches (kind 2) cut from
one heightfield, which the package also carries as its collision heightfield
(with a roof object over the path), so the target marker's ground from the
native heightfield can be compared with the all-resident terrain parts.

large(): a 2048 m world of 64 x 64 plain parts (kind 0, two distance levels),
each 32 m with its own 17 x 17 vertices: 1,183,744 vertices, beyond N3W1's
196,608. Vertices are computed on demand and indices are packed arrays, so the
writer never holds a million Python lists.

PQ-233: N3W2 worlds take their textures from an N3WT asset. textures() gives
the atlas's four slots as solid mip chains of three sizes (three banks), so the
same small world draws identically from the N3W1 atlas and from N3WT; many()
is a world whose parts name 1,200 textures of three sizes, plus the clear one.
"""
import array
import hashlib
import json
import math
import pathlib
import shutil
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko_lod  # noqa: E402
import main  # noqa: E402
import world_chunks  # noqa: E402
import world_textures  # noqa: E402
from common import string, u  # noqa: E402

ATLAS, CELL, PAD = 16, 8, 1
COLOURS = [(200, 80, 60, 255), (70, 160, 80, 255), (60, 90, 200, 255), (0, 0, 0, 0)]
CLEAR = 3  # transparent second layer


def atlas():
    rgba = bytearray(ATLAS * ATLAS * 4)
    for y in range(ATLAS):
        for x in range(ATLAS):
            slot = (y // CELL) * (ATLAS // CELL) + x // CELL
            rgba[(y * ATLAS + x) * 4:(y * ATLAS + x + 1) * 4] = bytes(COLOURS[slot])
    return ATLAS, ATLAS, CELL, PAD, bytes(rgba)


def chain(side, rgba):
    """A solid mip chain from side x side down to 1 x 1."""
    out = []
    while side >= 1:
        out.append((side, side, bytes(rgba) * (side * side)))
        side //= 2
    return out


# The atlas slots as N3WT textures: sides 8, 16, 8 and 4, so three banks.
SIDES = (8, 16, 8, 4)
COUNT = len(COLOURS)


def textures():
    return [chain(side, colour) for side, colour in zip(SIDES, COLOURS)]


def texture_bytes():
    return world_textures.serialize(textures())


MANY = 1200


def many_colour(i):
    return (40 + i % 11 * 20, 30 + i // 11 % 11 * 20, 20 + i // 121 * 20, 255)


def many_textures():
    """MANY solid textures of sides 8, 16 and 32 by index, then a clear one."""
    return [chain((8, 16, 32)[i % 3], many_colour(i)) for i in range(MANY)] + [chain(4, (0, 0, 0, 0))]


def many(side=36, patch=6.0):
    """(texture count, vertices, built): side x side plain parts, part n naming
    texture n % MANY and the clear one as its second layer."""
    v = LargeVertices(side, patch, 3, slots=lambda px, pz: float((pz * side + px) % MANY), clear=MANY)
    _, _, built = plain(side, patch, 3, v)
    return MANY + 1, v, built


def n3w1(atlas_, vertices, indices):
    w, h, cell, pad, rgba = atlas_
    return (b"N3W1" + struct.pack("<4I", w, h, cell, pad) + rgba + struct.pack("<I", len(vertices))
            + b"".join(struct.pack("<12f", *v) for v in vertices)
            + struct.pack("<I", len(indices)) + struct.pack("<%dI" % len(indices), *indices))


def small():
    """(atlas, vertices, built): N3L3-shaped, global vertex indices."""
    vertices, parts = [], []
    patch = 16.0
    for pz in range(2):
        for px in range(2):
            x0, z1 = px * patch, 32 - pz * patch
            y = 0.5 * (px + 2 * pz)
            base = len(vertices)
            for dx, dz in ((0, 0), (1, 0), (0, 1), (1, 1)):
                vertices.append([x0 + dx * patch, y, z1 - dz * patch, 0, 1, 0,
                                 dx * 2.0, dz * 2.0, .5, .5, float((px + pz) % 3), float(CLEAR)])
            quad = [base, base + 1, base + 2, base + 1, base + 3, base + 2]
            # Variant 0 is the whole quad; each coarse variant keeps one of its
            # triangles by parity, so the chosen level and edge mask show.
            levels = [(0., quad)] + [(float(i), quad[3 * (i % 2):3 * (i % 2) + 3]) for i in range(1, 33)]
            parts.append(dict(center=[x0 + 8, y, z1 - 8], radius=11.5, scale=1, flags=2,
                              levels=levels, kind=2, patch=[px, pz]))
    parents = []
    for n, (x, z) in enumerate(((4.0, 28.0), (28.0, 4.0))):
        base = len(vertices)
        for dx, dy in ((-2, 1), (2, 1), (0, 5)):
            vertices.append([x + dx, 3 + dy, z, 0, 0, 1, dx / 4, dy / 4, .5, .5, float(n + 1), float(CLEAR)])
        parents.append([x, 3, z, 12, x, 5, z, 8])
        pm = dict(min_vertices=2, min_indices=3, controls=[(0., 3), (20., 2)],
                  splits=[(3, 2, 1, 0, 0, 1)], edits=[2, 4])
        parts.append(dict(center=[x, 5, z], radius=4, scale=1, flags=8, kind=1, parent=n, base=base,
                          max_vertices=3, progressive=pm,
                          levels=[(0., [base, base + 1, base + 1, base, base + 1, base])]))
    # Near radius 1 patch (the far factor rounds to 0), middle band 1: a camera
    # a few patches off sees levels 2 and 3 with mixed edge masks.
    built = dict(terrain_lod=dict(origin=[0, 0, 32], patch_size=patch, far_factor=1 / 1024, bias=.6,
                                  minimum=1, band=1, width=2),
                 parents=parents, chunks=parts)
    return atlas(), vertices, built


def small_files():
    """(N3W1 bytes, N3L3 bytes, N3W2 bytes) of the same small world, 16 m chunks."""
    a, vertices, built = small()
    w1 = n3w1(a, vertices, [0, 1, 2])
    w2 = world_chunks.serialize(COUNT, vertices, built, (0, 0), 16, 2)
    return w1, ko_lod.serialize(built), w2


class LargeVertices:
    """A plain world's vertices, computed on demand: part p, sample (i, j).
    The defaults are the large world's."""
    SIDE, PATCH, SAMPLES = 64, 32.0, 17

    def __init__(self, side=64, patch=32.0, samples=17, slots=None, clear=CLEAR):
        self.SIDE, self.PATCH, self.SAMPLES = side, float(patch), samples
        self.slots = slots or (lambda px, pz: float((px + pz) % 3))
        self.clear = float(clear)

    def __len__(self):
        return self.SIDE * self.SIDE * self.SAMPLES * self.SAMPLES

    def __getitem__(self, n):
        part, rest = divmod(n, self.SAMPLES * self.SAMPLES)
        pz, px = divmod(part, self.SIDE)
        j, i = divmod(rest, self.SAMPLES)
        step = self.PATCH / (self.SAMPLES - 1)
        x, z = px * self.PATCH + i * step, pz * self.PATCH + j * step
        y = 6 * math.sin(x / 97) * math.cos(z / 131)
        return (x, y, z, 0, 1, 0, i / 4, j / 4, .5, .5, self.slots(px, pz), self.clear)


def large():
    """(atlas, vertices, built) of the 2048 m world: kind-0 parts, no terrain policy."""
    return plain(64, 32.0, 17)


def plain(side, patch, samples, v=None):
    """(atlas, vertices, built): side x side kind-0 parts of `patch` metres, each
    with its own samples x samples vertices and two distance levels (one when
    samples < 3). PQ-232 streams a 1024 m one (16, 64, 5) and a 64 m one of
    4096 one-metre chunks (64, 1, 2)."""
    v = v or LargeVertices(side, patch, samples)
    s = v.SAMPLES
    full, coarse = array.array("I"), array.array("I")
    for j in range(s - 1):
        for i in range(s - 1):
            a, b, c, d = j * s + i, j * s + i + 1, (j + 1) * s + i, (j + 1) * s + i + 1
            full.extend((a, c, b, b, c, d))
    for j in range(0, s - 2, 2):
        for i in range(0, s - 2, 2):
            a, b, c, d = j * s + i, j * s + i + 2, (j + 2) * s + i, (j + 2) * s + i + 2
            coarse.extend((a, c, b, b, c, d))
    parts = []
    for pz in range(v.SIDE):
        for px in range(v.SIDE):
            base = (pz * v.SIDE + px) * s * s
            shift = lambda t: array.array("I", (base + k for k in t))  # noqa: E731
            levels = [(0., shift(full))] + ([(300., shift(coarse))] if coarse else [])
            parts.append(dict(center=[px * v.PATCH + v.PATCH / 2, 0, pz * v.PATCH + v.PATCH / 2],
                              radius=v.PATCH * .75, scale=1, flags=4, kind=0, levels=levels))
    return atlas(), v, dict(terrain_lod=None, parents=[], chunks=parts)


TERRAIN_SAMPLES, TERRAIN_SPACING, TERRAIN_ORIGIN = 33, 4.0, -64.0
# A 12 m roof 3 m over the terrain, on the marker path: collision, not terrain.
ROOF = (-20.0, -8.0, -20.0, -8.0)


def terrain_height(x, z):
    return round(3 * math.sin(x / 9) * math.cos(z / 7) + .05 * x, 4)


def terrain():
    """(atlas, vertices, built, heightfield, triangles): patches of 8 x 8 cells,
    split as the collision heightfield's "alternating" diagonal splits them,
    each corner's vertices in the order the collision reader lists them."""
    n, s, o = TERRAIN_SAMPLES, TERRAIN_SPACING, TERRAIN_ORIGIN
    heights = [terrain_height(o + i * s, o + j * s) for j in range(n) for i in range(n)]
    width, vertices, parts = (n - 1) // 8, [], []
    for pz in range(width):
        for px in range(width):
            i0, j0, base = 8 * px, (n - 1) - 8 * (pz + 1), len(vertices)
            for dj in range(9):
                for di in range(9):
                    x, z = o + (i0 + di) * s, o + (j0 + dj) * s
                    vertices.append([x, heights[(j0 + dj) * n + i0 + di], z, 0, 1, 0, di / 8, dj / 8, .5, .5,
                                     float((px + pz) % 3), float(CLEAR)])
            full = []
            for dj in range(8):
                for di in range(8):
                    a, b, c, d = (base + dj * 9 + di, base + (dj + 1) * 9 + di,
                                  base + dj * 9 + di + 1, base + (dj + 1) * 9 + di + 1)
                    full.extend((a, b, d, a, d, c) if (i0 + di + j0 + dj) % 2 else (a, b, c, c, b, d))
            centre = [o + (i0 + 4) * s, 0, o + (j0 + 4) * s]
            parts.append(dict(center=centre, radius=8 * s * .75, scale=1, flags=2, kind=2, patch=[px, pz],
                              levels=[(0., full)] + [(float(k), full) for k in range(1, 33)]))
    top = o + (n - 1) * s
    built = dict(terrain_lod=dict(origin=[o, 0, top], patch_size=8 * s, far_factor=1 / 1024, bias=.6,
                                  minimum=1, band=1, width=width), parents=[], chunks=parts)
    hf = dict(width=n, depth=n, origin=[o, 0, o], spacing=s, diagonal="alternating", heights=heights)
    x0, x1, z0, z1 = ROOF
    y = max(terrain_height(x, z) for x in (x0, x1) for z in (z0, z1)) + 3
    roof = [[[x0, y, z0], [x0, y, z1], [x1, y, z0]], [[x1, y, z0], [x0, y, z1], [x1, y, z1]]]
    return atlas(), vertices, built, hf, roof


def package(work, name, world, lod=None, fog_end=900, heightfield=None, triangles=None, textures=None,
            overlay=None):
    """Cook the demo with `world` (and an N3L file when `lod`) at engine 13,
    with its own collision heightfield and object triangles when given. An
    N3W2 world gets `textures` (N3WT bytes), by default texture_bytes().
    `overlay` (N3WO bytes, PQ-387) is the package's world overlay."""
    root, out = pathlib.Path(work) / (name + "-source"), pathlib.Path(work) / name
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(ROOT / "games/demo", root)
    if heightfield is not None:
        meta = json.loads((root / "scene.json").read_text())
        meta.update(heightfield=heightfield, triangles=triangles or [])
        (root / "scene.json").write_text(json.dumps(meta))
    m = json.loads((root / "package.json").read_text())
    exploration = dict(turbo_multiplier=10, fog_start=min(200, fog_end / 2), fog_end=fog_end, fog_color=[.6, .7, .8])
    if lod is not None:
        exploration["lod"] = "lod.bin"
        (root / "lod.bin").write_bytes(lod)
    m.update(engine_version=13, protocol_version=7, world="map.bin", exploration=exploration)
    if world[:4] in world_chunks.MAGICS:
        (root / "textures.bin").write_bytes(texture_bytes() if textures is None else textures)
        m["world_textures"] = "textures.bin"
    if overlay is not None:
        (root / "overlay.bin").write_bytes(overlay)
        m["world_overlay"] = "overlay.bin"
    (root / "package.json").write_text(json.dumps(m))
    (root / "map.bin").write_bytes(world)
    main.cook(root, out)
    return out


def records(package):
    """(prefix, {name: record}) of release.bin."""
    index = (package / "release.bin").read_bytes()
    at = 16
    for _ in range(2):
        at += 4 + struct.unpack_from("<I", index, at)[0]
    count = struct.unpack_from("<I", index, at)[0]
    prefix, at, out = index[:at], at + 4, {}
    for _ in range(count):
        n = struct.unpack_from("<I", index, at)[0]
        out[index[at + 4:at + 4 + n].decode()] = index[at:at + 4 + n + 36]
        at += 4 + n + 36
    return prefix, out


def install(package, name, data):
    """Write `name` (None removes it) and rehash release.bin around it."""
    prefix, entries = records(package)
    if data is None:
        (package / name).unlink(missing_ok=True)
        entries.pop(name, None)
    else:
        (package / name).write_bytes(data)
        entries[name] = string(name) + u(len(data)) + hashlib.sha256(data).digest()
    (package / "release.bin").write_bytes(prefix + u(len(entries)) + b"".join(entries[k] for k in sorted(entries)))


def chunk_body(world, terrain=False):
    """[(x, z, body offset, body bytes)] of an N3W2 file, in table order."""
    at = 4 + 4 + 16
    at += 4 + (36 if struct.unpack_from("<I", world, at)[0] else 0)
    count = struct.unpack_from("<I", world, at)[0]
    entries = [struct.unpack_from("<2I6fI", world, at + 4 + 36 * i) for i in range(count)]
    offset, out = at + 4 + 36 * count, []
    for e in entries:
        out.append((e[0], e[1], offset, e[8]))
        offset += e[8]
    assert offset == len(world)
    return out
