"""Offline reader for local KO textures that carry alpha, and for `.gtt` tiles.

`ko_character` decodes the opaque DXT1 atlases a character needs. Map data also
uses DXT3 and 1-bit-alpha DXT1 for foliage and for the partial terrain tiles, so
this module decodes an N3 texture to RGBA instead of refusing it, and reads the
tile files that hold several textures back to back.

A GTT file is a plain concatenation of N3 textures with no index: the map names
a source file and an ordinal, and the loader skips that many textures before
reading the next one. Both halves are confirmed in the client binary:

* `CN3Terrain::LoadTileInfo` (`FUN_0059b140`) reads the tile-texture count, then
  the GTT filename table as fixed `0x104`-byte records, then one
  `(int16 source, int16 ordinal)` pair per tile texture. It opens
  `srcNames[source]`, calls the skip helper `ordinal` times, then loads the next
  texture. A tile texture index therefore means "position within that file".
* `CN3Texture::SkipFileHandle` (`FUN_0043f7e0`) reads the name, then a 20-byte
  header (`NTF\\x03`, width, height, format, mipmapped). For a mipmapped block
  format it advances over the compressed chain from the full size down to 4,
  then over a 16-bit chain from half size down to 4. For the 128x128 tiles in
  the local data that is 21,832 bytes after the header, so a whole record is
  21,856 bytes and a 174,848-byte GTT holds exactly eight tiles.

Nothing here runs at runtime and no reference bytes are bundled; this converts
locally supplied files into package pixels.
"""

from common import *

MAX_TEXTURE_FILE = 8 * 1024 * 1024
MAX_TILES = 64  # a source file holds a handful of tiles; refuse a runaway scan
# A zone colour map (TCT) is a grid whose size follows the map (`color_map_side`),
# so its bounds come from the grid instead of the two above. Per texture it keeps
# the former 8 MiB file bound spread over Moradon's 16 textures.
COLOR_MAP_RECORD = MAX_TEXTURE_FILE // 16
DXT1, DXT3, DXT5 = 0x31545844, 0x33545844, 0x35545844
BLOCK_BYTES = {DXT1: 8, DXT3: 16, DXT5: 16}
# DXT5 is read only on request (`dxt5=True`, PQ-339: the 2233 client's FX
# textures in the player's 2145 fx pack); every 1298 read refuses it as before.
# The 2233 CN3Texture::Load (00463180) takes fourcc DXT5 with 16-byte blocks
# (the size it reads per level for any fourcc but DXT1) and the same chains as
# DXT3; the block itself is the Direct3D format (API).
PIXEL_BYTES = {21: 4, 22: 4, 25: 2, 26: 2}


def _colors(c0, c1, opaque):
    """The four-entry DXT colour palette, plus whether entry 3 is transparent."""

    def rgb(v):
        return [((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63,
                (v & 31) * 255 // 31]

    a, b = rgb(c0), rgb(c1)
    if opaque or c0 > c1:
        return [a, b, [(2 * x + y) // 3 for x, y in zip(a, b)],
                [(x + 2 * y) // 3 for x, y in zip(a, b)]], False
    return [a, b, [(x + y) // 2 for x, y in zip(a, b)], [0, 0, 0]], True


def decode_blocks(blocks, width, height, fmt):
    """Decode DXT1/DXT3/DXT5 to RGBA. DXT1 keeps its one-bit alpha."""
    stride = BLOCK_BYTES[fmt]
    if width % 4 or height % 4 or len(blocks) != width * height // 16 * stride:
        raise ValueError("DXT block bound")
    rgba = bytearray(b"\xff" * (width * height * 4))
    for by in range(height // 4):
        for bx in range(width // 4):
            at = (by * (width // 4) + bx) * stride
            alpha = ramp = None
            if fmt == DXT3:
                alpha = struct.unpack_from("<Q", blocks, at)[0]
                at += 8
            elif fmt == DXT5:
                # Two end points and 3-bit indices (API): 8 levels when the
                # first is larger, else 6 and the two extremes.
                a0, a1 = blocks[at], blocks[at + 1]
                ramp = [a0, a1] + ([((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)] if a0 > a1 else
                                   [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255])
                alpha = int.from_bytes(blocks[at + 2:at + 8], "little")
                at += 8
            c0, c1, bits = struct.unpack_from("<HHI", blocks, at)
            palette, punch = _colors(c0, c1, fmt != DXT1)
            for pixel in range(16):
                ix = (bits >> (pixel * 2)) & 3
                out = ((by * 4 + pixel // 4) * width + bx * 4 + pixel % 4) * 4
                rgba[out:out + 3] = bytes(palette[ix])
                if ramp is not None:
                    rgba[out + 3] = ramp[(alpha >> (pixel * 3)) & 7]
                elif alpha is not None:
                    nibble = (alpha >> (pixel * 4)) & 15
                    rgba[out + 3] = nibble * 255 // 15
                elif punch and ix == 3:
                    rgba[out + 3] = 0
    return bytes(rgba)


class Reader:
    """Sequential reader that can skip a texture without decoding it."""

    def __init__(self, data, limit=MAX_TEXTURE_FILE, dxt5=False):
        if len(data) > limit:
            raise ValueError("KO texture file bound")
        self.data = data
        self.at = 0
        self.dxt5 = dxt5

    def take(self, n):
        if n < 0 or self.at + n > len(self.data):
            raise ValueError("truncated KO texture data")
        b = self.data[self.at:self.at + n]
        self.at += n
        return b

    def header(self):
        """Read one texture header; return (width, height, format, mipmapped)."""
        length = struct.unpack("<i", self.take(4))[0]
        self.take(count(length, 255, 0))  # texture name, unused here
        if self.take(4) != b"NTF\x03":
            raise ValueError("unsupported KO texture version")
        w, h, fmt, mips = struct.unpack("<4i", self.take(16))
        for n in (w, h):
            if not 4 <= n <= 2048 or n & (n - 1):
                raise ValueError("KO texture dimensions")
        if fmt not in BLOCK_BYTES and fmt not in PIXEL_BYTES or fmt == DXT5 and not self.dxt5:
            raise ValueError("unsupported KO texture format %#x" % fmt)
        if mips not in (0, 1):
            raise ValueError("KO texture mip flag")
        return w, h, fmt, mips


def _payload(w, h, fmt, mips):
    """Bytes after the header, following `CN3Texture::SkipFileHandle`."""
    if fmt in PIXEL_BYTES:  # binary SkipFileHandle0043f7e0, native pixel layout
        stride = PIXEL_BYTES[fmt]
        if not mips: return w*h*stride + (0x20000 if w>=512 else 0)
        size=0
        while w>3 and h>3:
            size+=w*h*stride;w//=2;h//=2
        return size
    per_block = BLOCK_BYTES[fmt]

    def level(x, y):
        return x * y // 16 * per_block

    if not mips:
        return level(w, h) + w * h * 2 + (0x20000 if w > 1024 else 0)
    total, x, y = 0, w, h
    while x > 3 and y > 3:  # compressed chain, base level included
        total += level(x, y)
        x //= 2
        y //= 2
    x, y = w // 2, h // 2
    while x > 3 and y > 3:  # 16-bit half-resolution chain
        total += x * y * 2
        x //= 2
        y //= 2
    return total


def decode_pixels(raw, fmt):
    pixels = bytearray()
    for (v,) in struct.iter_unpack('<H' if PIXEL_BYTES[fmt] == 2 else '<I', raw):
        if fmt == 25:
            pixels.extend(((v>>10&31)*255//31, (v>>5&31)*255//31, (v&31)*255//31, 255 if v&32768 else 0))
        elif fmt == 26:
            pixels.extend(((v>>8&15)*17, (v>>4&15)*17, (v&15)*17, (v>>12&15)*17))
        else:
            pixels.extend((v>>16&255, v>>8&255, v&255, v>>24&255 if fmt == 21 else 255))
    return bytes(pixels)


def _read_one(r, target=None):
    """Decode one texture, preferring the smallest mip level at least `target`.

    Picking a level instead of downscaling the base keeps the reference's own
    filtered mip pixels and avoids decompressing data an atlas cell throws away.
    """
    w, h, fmt, mips = r.header()
    if fmt in PIXEL_BYTES:
        stride=PIXEL_BYTES[fmt]
        body=r.take(_payload(w,h,fmt,mips));at=0;x,y=w,h;chosen=(w,h,0)
        while mips and x>3 and y>3:
            if target and x>=target and y>=target:chosen=(x,y,at)
            at+=x*y*stride;x//=2;y//=2
        w,h,at=chosen
        return w,h,decode_pixels(body[at:at+w*h*stride],fmt)
    per_block = BLOCK_BYTES[fmt]
    if not mips:
        body = r.take(_payload(w, h, fmt, mips))
        return w, h, decode_blocks(body[:w * h // 16 * per_block], w, h, fmt)
    levels, x, y = [], w, h
    while x > 3 and y > 3:
        levels.append((x, y, r.take(x * y // 16 * per_block)))
        x //= 2
        y //= 2
    x, y = w // 2, h // 2
    while x > 3 and y > 3:  # 16-bit half-resolution chain
        r.take(x * y * 2)
        x //= 2
        y //= 2
    chosen = levels[0]
    if target:
        for level in levels:
            if level[0] >= target and level[1] >= target:
                chosen = level
            else:
                break
    return chosen[0], chosen[1], decode_blocks(chosen[2], chosen[0], chosen[1], fmt)


def texture(data, target=None):
    """Decode a single-texture file (object textures) to (w, h, RGBA)."""
    return _read_one(Reader(data), target)


def color_map_side(patches):
    """Colour-map textures a side for a map of `patches` x `patches` patches.

    `0059eff0` sets `+0x4194` to `(patches * 32) / 128` from the patch count at
    `+0x40c8` and reads that many squared textures in sequence, x-major. n3e
    refuses a grid that does not cover whole 32-tile regions instead of
    truncating it as the integer division would.
    """
    if type(patches) is not int or patches <= 0 or patches * 32 % 128:
        raise ValueError("color-map grid must cover whole 32-tile regions")
    return patches * 32 // 128


def color_map_limit(count):
    """File bound for a colour map of `count` textures."""
    return count * COLOR_MAP_RECORD


def tiles(data, wanted=None, target=None, count=None):
    """Decode the textures in one GTT file, keyed by ordinal.

    `wanted` limits decoding to a set of ordinals; the rest are skipped by their
    computed length, which is what the reference loader does and what keeps a
    map import from decompressing tiles it never places.

    With `count` the file is a colour map that must hold exactly `count`
    textures (`color_map_side`), bounded by `color_map_limit(count)` rather than
    the GTT bounds.
    """
    r = Reader(data) if count is None else Reader(data, color_map_limit(count))
    out, index = {}, 0
    while r.at < len(data):
        if index >= (MAX_TILES if count is None else count):
            raise ValueError("GTT tile count" if count is None else "color-map count")
        if wanted is not None and index not in wanted:
            w, h, fmt, mips = r.header()
            r.take(_payload(w, h, fmt, mips))
        else:
            out[index] = _read_one(r, target)
        index += 1
    if index == 0:
        raise ValueError("empty GTT file")
    if count is not None and index != count:
        raise ValueError("color-map count")
    return out


def load_tiles(path, wanted=None, target=None):
    return tiles(read(pathlib.Path(path)), wanted, target)


def mip_chains(data, skip=0, count=None, dxt5=False):
    """Preserve native authored RGBA mip levels, never resize or regenerate.

    0043f090/0043f1be validates requested top-level skipping (0..2, dimensions
    >=16). This decoder follows the supported compressed-capable GPU path.
    Fallback 16-bit chains are consumed but not substituted for DXT artwork.
    With `count`, a colour map of exactly that many textures, as in `tiles`.
    `dxt5` also takes DXT5 (PQ-339, the 2233 FX textures only) and reads a
    no-mip compressed texture as 2233 does (PQ-341, below).
    """
    r=Reader(data,dxt5=dxt5) if count is None else Reader(data,color_map_limit(count),dxt5); out=[]
    while r.at<len(data):
        w,h,fmt,mips=r.header()
        if r.dxt5 and not mips and fmt in BLOCK_BYTES:
            # PQ-341: 2233's CN3Texture::Load (00463180) reads a no-mip
            # compressed texture's level, then seeks w x h / 4 bytes
            # (00463870-0046388e) and reads nothing past it. The 2145 fx
            # pack's no-mip textures hold w x h / 2 bytes there (a w/2 x h/2
            # 16-bit level), 1298's layout w x h x 2. Such a texture is its
            # file: the rest is taken whole, from the bytes 2233 skips to
            # 1298's size (n3e's bounds; at most 512 wide, the FX bound).
            level=w*h//16*BLOCK_BYTES[fmt];rest=len(data)-r.at-level
            if max(w,h)>512 or not w*h//4<=rest<=w*h*2:raise ValueError('2233 KO texture size')
            body=r.take(level+rest)
        else:body=r.take(_payload(w,h,fmt,mips))
        at=0
        x,y=w,h; levels=[]
        while True:
            size=x*y*PIXEL_BYTES[fmt] if fmt in PIXEL_BYTES else x*y//16*BLOCK_BYTES[fmt]
            raw=body[at:at+size];at+=size
            if fmt in PIXEL_BYTES:
                pixels=decode_pixels(raw,fmt)
            else: pixels=decode_blocks(raw,x,y,fmt)
            levels.append((x,y,pixels))
            if not mips or min(x,y)<=4:break
            x//=2;y//=2
        offset=skip if 1<=skip<=2 and min(w,h)>=16 and mips else 0
        out.append(levels[offset:])
        if len(out)>(MAX_TILES if count is None else count):
            raise ValueError('texture chain count' if count is None else 'color-map count')
    if not out:raise ValueError('empty texture chain')
    if count is not None and len(out)!=count:raise ValueError('color-map count')
    return out
