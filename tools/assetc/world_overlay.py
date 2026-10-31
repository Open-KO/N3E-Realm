"""N3WO: maps blended over a world's near terrain around the eye (PQ-387, D-204).

Generic: no game IDs, paths or rules. A map is an authored RGBA8 mip chain
that covers one square block of terrain tiles. The client draws, right after
a terrain patch (an N3L / N3W kind 2 part) drawn at its near level whose patch
lies within `window` patches of the eye's patch on both axes, the patch's near
level again with each fragment's block map: colour the texel times the
terrain light, alpha the texel's, blended source alpha over one minus source
alpha, depth test less-or-equal, texel alpha 0 dropped.

Grid. Terrain tile coordinates are the terrain policy's: from its origin, x
along +x and z along -z, `patch_tiles` tiles a patch side, so a tile is
patch_size / patch_tiles metres. Block (bx, bz) is tiles [bx·B, bx·B + B) x
[bz·B, bz·B + B) with B = `block_tiles`; `width` is the grid's blocks a side,
the terrain policy's patch width times patch_tiles / B.

Texel layout. A fragment at tile coordinates (x, z), tile (tx, tz) =
(floor x, floor z) and fraction (fx, fz), samples its block's map at
u = ((tx mod B)·C + I + (C − 2I)·fx) / S, v = ((B − tz mod B)·C − I − (C − 2I)·fz) / S,
with S = `side`, C = `cell` (texels per tile, B·C = S) and I = `inset`, mirrored
repeat, trilinear. Row 0 of a map is the block's high-z edge.

Layout (little-endian): "N3WO"; u32 patch_tiles [1, 64], block_tiles (divides
patch_tiles, at most 4 blocks a patch side), window [0, 2], side (a power of
two, 4..256), cell, inset (2·inset < cell), levels [1, log2(side) + 1], width
[1, 4096], count [1, min(width², 65536)]; then per map u32 bx, u32 bz and its
levels, level k (side >> k)² × 4 bytes. Maps are in strictly increasing
bz · width + bx order, every block inside the grid. The window's maps must fit
one array of at most 256 layers: (2·window + 1)² · (patch_tiles / block_tiles)².
Trailing bytes are refused. The client (client/assets/assets.cpp
`load_world_overlay`) applies the same rules.
"""
import struct

from common import u

MAGIC = b"N3WO"
MAX_PATCH_TILES = 64
MAX_BLOCKS_PER_PATCH = 4
MAX_WINDOW = 2
MIN_SIDE, MAX_SIDE = 4, 256
MAX_WIDTH = 4096
MAX_MAPS = 65536
MAX_LAYERS = 256
HEADER = 4 + 9 * 4
# 65,536 maps of 64 x 64 with every level, or fewer larger ones.
MAX_PIXEL_BYTES = 1024 * 1024 * 1024 // 4
MAX_FILE = HEADER + MAX_MAPS * 8 + MAX_PIXEL_BYTES


def map_bytes(side, levels):
    return sum((side >> k) ** 2 * 4 for k in range(levels))


def _header(h):
    p, b, window, side, cell, inset, levels, width = (
        h["patch_tiles"], h["block_tiles"], h["window"], h["side"], h["cell"], h["inset"], h["levels"], h["width"])
    if not (1 <= p <= MAX_PATCH_TILES and 1 <= b <= p and p % b == 0 and p // b <= MAX_BLOCKS_PER_PATCH):
        raise ValueError("world overlay grid")
    if not 0 <= window <= MAX_WINDOW or (2 * window + 1) ** 2 * (p // b) ** 2 > MAX_LAYERS:
        raise ValueError("world overlay window")
    if not (MIN_SIDE <= side <= MAX_SIDE and side & (side - 1) == 0 and b * cell == side
            and 0 <= 2 * inset < cell):
        raise ValueError("world overlay texel layout")
    if not 1 <= levels <= side.bit_length():
        raise ValueError("world overlay levels")
    if not 1 <= width <= MAX_WIDTH:
        raise ValueError("world overlay width")
    return p, b, window, side, cell, inset, levels, width


def serialize(header, maps):
    """N3WO bytes. `header` holds the nine fields but `count`; `maps` is
    {(bx, bz): [level 0 rgba, level 1 rgba, ...]}, `levels` levels each."""
    p, b, window, side, cell, inset, levels, width = _header(header)
    if not 1 <= len(maps) <= min(width * width, MAX_MAPS):
        raise ValueError("world overlay count")
    out = bytearray(MAGIC + b"".join(u(v) for v in (p, b, window, side, cell, inset, levels, width, len(maps))))
    total = 0
    for bx, bz in sorted(maps, key=lambda k: k[1] * width + k[0]):
        if not (0 <= bx < width and 0 <= bz < width):
            raise ValueError("world overlay block")
        chain = maps[(bx, bz)]
        if len(chain) != levels or any(len(rgba) != (side >> k) ** 2 * 4 for k, rgba in enumerate(chain)):
            raise ValueError("world overlay map size")
        total += map_bytes(side, levels)
        if total > MAX_PIXEL_BYTES:
            raise ValueError("world overlay byte bound")
        out += u(bx) + u(bz) + b"".join(chain)
    if len(out) > MAX_FILE:
        raise ValueError("world overlay file bound")
    return bytes(out)


def check(data):
    """Refuse what the client refuses; return (header dict with count, [(bx, bz)])."""
    if len(data) > MAX_FILE or len(data) < HEADER or data[:4] != MAGIC:
        raise ValueError("world overlay magic")
    names = ("patch_tiles", "block_tiles", "window", "side", "cell", "inset", "levels", "width", "count")
    header = dict(zip(names, struct.unpack_from("<9I", data, 4)))
    _, _, _, side, _, _, levels, width = _header(header)
    count = header["count"]
    if not 1 <= count <= min(width * width, MAX_MAPS):
        raise ValueError("world overlay count")
    size = map_bytes(side, levels)
    if count * size > MAX_PIXEL_BYTES or len(data) != HEADER + count * (8 + size):
        raise ValueError("world overlay size")
    keys, last = [], -1
    for i in range(count):
        bx, bz = struct.unpack_from("<2I", data, HEADER + i * (8 + size))
        key = bz * width + bx
        if not (bx < width and bz < width) or key <= last:
            raise ValueError("world overlay block order")
        last = key
        keys.append((bx, bz))
    return header, keys
