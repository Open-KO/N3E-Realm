"""PQ-387 (D-204): a KO zone's terrain light maps (`.tlt`, Zones.tbl column 5)
as an N3WO world overlay (`world_overlay`). Offline only; it reads the player's
own client data.

Client behaviour (`KnightOnLine.exe` 1298, PQ-385 and PQ-387, binary):

* `0059ba90` opens the file the zone's Zones.tbl row names at `+0x38`
  (column 5), reads an int32 it never compares (a version), then one int32
  per patch, index pz * P + px with P = (map size - 1) / 8 (`0059a264`).
* `0059c450` reads, for a patch whose int32 is above 0, from that offset an
  int32 count and, when it is above 0, that many (int32 tx, int32 tz, N3
  texture) entries (`0043e880`, vtable +0xc: the colour map's texture load),
  keyed 4 * (10000 * (2 px + tx) + 2 pz + tz): one texture per 4 x 4-tile
  block (`0059c720` looks a tile up by x / 4 and z / 4).
* Only the 3 x 3 patches around the eye's patch are loaded (`0059c450` on
  slots `[+0x40d0] - 1 + sx`; `0059b6f0`, `0059b890`: the eye's patch), and
  `005a0410` writes a tile's UVs from ((x mod 4) * 8 + 1) / 32 to
  ((x mod 4) * 8 + 7) / 32 and ((4 - z mod 4) * 8 - 1) / 32 at the low-z edge
  to ((4 - z mod 4) * 8 - 7) / 32 at the high-z edge (`006a8310` = 1 / 32),
  so a block's 32-texel map gives each tile the inside of its 8-texel cell:
  N3WO patch_tiles 8, block_tiles 4, window 1, side 32, cell 8, inset 1.

n3e differences, all in the fail-closed direction and none reached by the
local data (PQ-385 claims 19-21): a version other than 0, an entry whose tx or
tz is not 0 or 1, a block named twice, a map that is not 32 x 32 or whose
mip chain differs from the others, and a record past the file's end are
refused. A zone without a map gives no overlay.
"""
import hashlib
import struct

from common import read
import ko_tiles
import world_overlay

PATCH_TILES = 8    # 0059c720, 005a0410: x / 8 is the patch, x mod 8 the tile
BLOCK_TILES = 4    # 0059c720: the key's x / 4, z / 4
WINDOW = 1         # 0059c720: ix, iz in 0..2 around [+0x40d0]
CELL, INSET = 8, 1  # 005a0410: (x mod 4) * 8 + 1 .. + 7, over 32
SIDE = BLOCK_TILES * CELL
# The local files are about 11 MiB at most (elmo2004, 4,062 maps).
MAX_TLT = 64 * 1024 * 1024


def load(path, samples):
    """The maps of a `.tlt` for a map of `samples` a side: {(bx, bz): mip
    chain of RGBA8 levels} and a report. Block coordinates are the
    reference's tile grid over 4, z as the GTD's (n3e's terrain policy z)."""
    if (samples - 1) % PATCH_TILES or samples < PATCH_TILES + 1:
        raise ValueError("light maps need whole %d-tile patches" % PATCH_TILES)
    patches = (samples - 1) // PATCH_TILES
    data = read(path, MAX_TLT)
    table = 4 + 4 * patches * patches
    if len(data) < table:
        raise ValueError("%s is shorter than its patch table" % path)
    (version,) = struct.unpack_from("<i", data, 0)
    if version != 0:
        raise ValueError("%s has light-map version %d, not 0" % (path, version))
    addresses = struct.unpack_from("<%di" % (patches * patches), data, 4)
    maps, levels, patches_with = {}, None, 0
    alpha_max = coloured = 0
    for index, address in enumerate(addresses):
        if address <= 0:
            continue  # 0059c450 reads a patch only at an offset above 0
        if address + 4 > len(data):
            raise ValueError("%s: patch %d's light maps start past the file" % (path, index))
        px, pz = index % patches, index // patches
        (count,) = struct.unpack_from("<i", data, address)
        if count <= 0:
            continue
        patches_with += 1
        reader = ko_tiles.Reader(memoryview(data)[address + 4:], limit=MAX_TLT)
        for _ in range(count):
            tx, tz = struct.unpack("<2i", reader.take(8))
            if tx not in (0, 1) or tz not in (0, 1):
                raise ValueError("%s: patch (%d, %d) names block (%d, %d)" % (path, px, pz, tx, tz))
            key = (2 * px + tx, 2 * pz + tz)
            if key in maps:
                raise ValueError("%s: block %s is named twice" % (path, key))
            chain = _chain(reader)
            if chain[0][:2] != (SIDE, SIDE):
                raise ValueError("%s: block %s's map is %dx%d, not %dx%d" % (path, key, *chain[0][:2], SIDE, SIDE))
            shape = [(w, h) for w, h, _ in chain]
            if levels is None:
                levels = shape
            elif shape != levels:
                raise ValueError("%s: block %s's mip chain differs from the others" % (path, key))
            base = chain[0][2]
            alpha_max = max(alpha_max, max(base[3::4]))
            coloured += sum(1 for i in range(0, len(base), 4) if base[i + 3] and any(base[i:i + 3]))
            maps[key] = [rgba for _, _, rgba in chain]
    report = dict(file=str(path), sha256=hashlib.sha256(data).hexdigest(), version=version,
                  patches=patches, patches_with_maps=patches_with, maps=len(maps),
                  levels=len(levels) if levels else 0, max_alpha=alpha_max, coloured_base_texels=coloured,
                  binary="KnightOnLine.exe 0059ba90 (file, table), 0059c450 (entries), 0059c720 (key), "
                         "005a0410 (UVs), 005a2640 (blend)")
    return maps, report


def _chain(reader):
    """One N3 texture's mip chain as RGBA8 levels: (w, h, rgba) from the top."""
    w, h, fmt, mips = reader.header()
    if fmt not in ko_tiles.PIXEL_BYTES:
        raise ValueError("light map format %#x is not a pixel format" % fmt)
    body = reader.take(ko_tiles._payload(w, h, fmt, mips))
    stride, at, out = ko_tiles.PIXEL_BYTES[fmt], 0, []
    while True:
        size = w * h * stride
        out.append((w, h, ko_tiles.decode_pixels(body[at:at + size], fmt)))
        at += size
        if not mips or min(w, h) <= 4:
            return out
        w //= 2
        h //= 2


def overlay(path, samples):
    """N3WO bytes of the zone's light maps and the report, or (None, report)
    when the zone has none."""
    maps, report = load(path, samples)
    if not maps:
        return None, report
    header = dict(patch_tiles=PATCH_TILES, block_tiles=BLOCK_TILES, window=WINDOW, side=SIDE, cell=CELL,
                  inset=INSET, levels=report["levels"], width=(samples - 1) // BLOCK_TILES)
    return world_overlay.serialize(header, maps), report
