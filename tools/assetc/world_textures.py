"""N3WT: an N3W2 world's textures, in their own bounded asset (PQ-233, D-159).

Generic: no game IDs, paths or rules. A texture is an authored mip chain of
RGBA8 levels, as N3D1 carries them: power-of-two sides of at most 2048, each
level half the previous (at least 1), at most 12 levels, no generated tail. The
client groups textures with the same top size and level count into array
banks, as NativeTextures does for render detail, and splits a group into
several banks when it has more layers than one bank holds (2048 here, the
GPU's own limit if lower). Bounds are sized for a 2048 m KO zone, about 750
textures (PQ-055): 4096 textures, 384 MiB of decoded pixels, at most 8 banks
of 2048 layers. The client (client/assets/assets.cpp `load_world_textures`)
applies the same bounds.

Layout (little-endian): "N3WT", u32 texture count [1, 4096]; per texture u32
level count [1, 12], then per level u32 width, height and width x height x 4
bytes. Trailing bytes are refused.
"""
import struct

from common import u

MAGIC = b"N3WT"
MAX_TEXTURES = 4096
MAX_LEVELS = 12
MAX_SIDE = 2048
MAX_PIXEL_BYTES = 384 * 1024 * 1024
BANK_LAYERS = 2048
MAX_BANKS = 8
# Header bytes at most: magic, count and, per texture, a level count and
# 12 level sizes.
MAX_FILE = 8 + MAX_TEXTURES * (4 + MAX_LEVELS * 8) + MAX_PIXEL_BYTES


def banks(keys, layers=BANK_LAYERS):
    """Bank count for texture keys (width, height, levels): one group per key,
    split into banks of at most `layers` textures."""
    groups = {}
    for k in keys:
        groups[k] = groups.get(k, 0) + 1
    return sum(-(-n // layers) for n in groups.values())


def _chain(levels):
    """Refuse a chain the client would: (width, height, levels) of its top."""
    if not 1 <= len(levels) <= MAX_LEVELS:
        raise ValueError("world texture level count")
    pw = ph = 0
    for i, (w, h) in enumerate(levels):
        if not (1 <= w <= MAX_SIDE and 1 <= h <= MAX_SIDE and w & (w - 1) == 0 and h & (h - 1) == 0):
            raise ValueError("world texture dimensions")
        if i and not ((pw > 1 or ph > 1) and w == max(1, pw // 2) and h == max(1, ph // 2)):
            raise ValueError("world texture mip dimensions")
        pw, ph = w, h
    return levels[0][0], levels[0][1], len(levels)


def serialize(textures):
    """N3WT bytes of `textures`: a list of chains, each a list of (width,
    height, rgba) levels."""
    if not 1 <= len(textures) <= MAX_TEXTURES:
        raise ValueError("world texture count")
    total, keys = 0, []
    for chain in textures:
        keys.append(_chain([(w, h) for w, h, _ in chain]))
        for w, h, rgba in chain:
            if len(rgba) != w * h * 4:
                raise ValueError("world texture byte count")
            total += len(rgba)
            if total > MAX_PIXEL_BYTES:
                raise ValueError("world texture byte bound")
    if banks(keys) > MAX_BANKS:
        raise ValueError("world texture bank bound")
    out = bytearray(MAGIC + u(len(textures)))
    for chain in textures:
        out += u(len(chain))
        for w, h, rgba in chain:
            out += u(w) + u(h) + rgba
    return bytes(out)


def check(data):
    """Validate N3WT bytes as the client does; (texture count, banks, pixel
    bytes). Reads sizes only and skips the pixels."""
    if len(data) > MAX_FILE:
        raise ValueError("world texture file bound")
    if data[:4] != MAGIC:
        raise ValueError("world texture magic")
    at = 4

    def take():
        nonlocal at
        if at + 4 > len(data):
            raise ValueError("world texture truncated")
        (v,) = struct.unpack_from("<I", data, at)
        at += 4
        return v
    count = take()
    if not 1 <= count <= MAX_TEXTURES:
        raise ValueError("world texture count")
    total, keys = 0, []
    for _ in range(count):
        n = take()
        if not 1 <= n <= MAX_LEVELS:
            raise ValueError("world texture level count")
        levels = []
        for _ in range(n):
            w, h = take(), take()
            levels.append((w, h))
            _chain(levels)
            total += w * h * 4
            if total > MAX_PIXEL_BYTES:
                raise ValueError("world texture byte bound")
            if at + w * h * 4 > len(data):
                raise ValueError("world texture truncated")
            at += w * h * 4
        keys.append(_chain(levels))
    if at != len(data):
        raise ValueError("world texture trailing bytes")
    n = banks(keys)
    if n > MAX_BANKS:
        raise ValueError("world texture bank bound")
    return count, n, total
