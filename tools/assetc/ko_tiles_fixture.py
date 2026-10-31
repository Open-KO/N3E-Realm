"""Original synthetic N3 textures and tile files for the importer tests.

Nothing here comes from reference data: the blocks are constructed so each
decode path is exercised deliberately — an opaque DXT1 block, a punch-through
DXT1 block, a DXT3 block with a known alpha ramp — and so the mip chain has the
exact shape `CN3Texture::SkipFileHandle` walks, which is what makes the ordinal
of a later tile in the same file meaningful.
"""

import struct

DXT1, DXT3 = 0x31545844, 0x33545844


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def dxt1_block(c0, c1, bits):
    return struct.pack("<HHI", c0, c1, bits)


def dxt3_block(alpha, c0, c1, bits):
    return struct.pack("<Q", alpha) + dxt1_block(c0, c1, bits)


def level(width, height, fmt, seed):
    """One mip level of blocks, deterministic in `seed`."""
    out = bytearray()
    for i in range(width * height // 16):
        n = (seed + i) & 0xFF
        high, low = rgb565(255 - n, n, 128), rgb565(n, 128, 255 - n)
        if fmt == DXT3:
            out += dxt3_block(0x0123456789ABCDEF, high, low, 0x1B1B1B1B)
        elif seed & 1:  # punch-through: c0 <= c1 makes index 3 transparent
            out += dxt1_block(low, high, 0xE4E4E4E4) if low <= high else \
                   dxt1_block(high, low, 0xE4E4E4E4)
        else:
            out += dxt1_block(max(high, low), min(high, low), 0x1B1B1B1B)
    return bytes(out)


def texture(width=8, height=8, fmt=DXT1, mips=1, name="", seed=0):
    body = bytearray()
    if mips:
        x, y = width, height
        while x > 3 and y > 3:
            body += level(x, y, fmt, seed)
            x //= 2
            y //= 2
        x, y = width // 2, height // 2
        while x > 3 and y > 3:
            body += bytes(x * y * 2)
            x //= 2
            y //= 2
    else:
        body += level(width, height, fmt, seed)
        body += bytes(width * height * 2)
    raw = name.encode("ascii")
    return (struct.pack("<i", len(raw)) + raw + b"NTF\x03"
            + struct.pack("<4i", width, height, fmt, 1 if mips else 0)
            + bytes(body))


def gtt(count=4, width=8, height=8, fmt=DXT1):
    """A tile file: several textures back to back, no index."""
    return b"".join(texture(width, height, fmt, 1, "tile%d" % i, seed=i)
                    for i in range(count))
