"""Read a KO client data table (`Data/*.tbl`) offline: decrypt, then parse (PQ-274).

The player's own client tables are encrypted. The pinned 1298 client
(`KnightOnLine.exe`, binary) loads one as follows; the record is
docs/implementation/evidence/pq-274-homeland-1097-bake.md:

* `006113b0` reads `Data\\Zones.tbl` (string `006d8ddc`) whole and decrypts it in
  place with `0044f670(buffer, size, 0x816, 0x6081, 0x1608)`: each byte is
  XOR-ed with bits 8-15 of the key, and the key becomes
  `(cipher byte + key) * 0x6081 + 0x1608`. It then parses the plain bytes with
  `006264d0`.
* `006264d0` reads an int32 column count, one int32 type per column and an
  int32 row count, then every row's fields in column order. `006359b0` reads a
  field: types 1 and 2 take one byte, 3 and 4 two, 5, 6 and 8 four, 9 eight,
  and 7 is an int32 length followed by that many bytes (a string). Any other
  type is refused (`return 0`).
* Each table class then checks its own row layout (`00635be0` computes the
  offsets); for Zones.tbl `006264d0` wants a 0x108-byte row whose first type
  is 6. That check is the caller's: `ko_zone` checks the column types it reads.

Signedness is not visible in the binary: n3e reads types 1, 3 and 5 signed and
2, 4 and 6 unsigned, 8 as a float32 and 9 as a float64 (the source's DT_CHAR
... DT_DOUBLE names; source-only). Strings are returned as ASCII text with any
other byte replaced (U+FFFD): the callers read file paths, which `ko_zone`
then refuses unless they name a local file.

n3e differences, all in the fail-closed direction: a size, column, row or string
past a bound, a field that runs past the end, and bytes left after the last row
are refused (the client stops reading at the last row).
"""

import struct

from common import *

KEY, MULTIPLIER, INCREMENT = 0x816, 0x6081, 0x1608  # 006113b0 -> 0044f670
MAX_TABLE = 64 * 1024 * 1024
MAX_COLUMNS = 256
MAX_STRING = 4096
STRING = 7
FIXED = {1: "<b", 2: "<B", 3: "<h", 4: "<H", 5: "<i", 6: "<I", 8: "<f", 9: "<d"}


def decrypt(data, key=KEY):
    """`0044f670`: the plain bytes of an encrypted table."""
    out = bytearray(len(data))
    for i, byte in enumerate(data):
        out[i] = byte ^ ((key >> 8) & 0xFF)
        key = ((byte + key) * MULTIPLIER + INCREMENT) & 0xFFFFFFFF
    return bytes(out)


def encrypt(plain, key=KEY):
    """The inverse of `decrypt`, for synthetic fixtures."""
    out = bytearray(len(plain))
    for i, byte in enumerate(plain):
        cipher = byte ^ ((key >> 8) & 0xFF)
        out[i] = cipher
        key = ((cipher + key) * MULTIPLIER + INCREMENT) & 0xFFFFFFFF
    return bytes(out)


def parse(plain):
    """`006264d0` / `006359b0`: (column types, rows) of a decrypted table.

    Every row is a list of Python values: int for types 1-6, float for 8 and 9,
    str for 7."""
    offset = 0

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(plain):
            raise ValueError("KO table: a field runs past the end at byte %d" % offset)
        piece = plain[offset:offset + size]
        offset += size
        return piece

    columns = struct.unpack("<i", take(4))[0]
    if not 1 <= columns <= MAX_COLUMNS:
        raise ValueError("KO table: %d columns" % columns)
    types = list(struct.unpack("<%di" % columns, take(4 * columns)))
    for t in types:
        if t != STRING and t not in FIXED:
            raise ValueError("KO table: column type %d" % t)
    count = struct.unpack("<i", take(4))[0]
    # Each row takes at least one byte per column, so the remaining bytes bound it.
    if count < 0 or count * columns > len(plain) - offset:
        raise ValueError("KO table: %d rows" % count)
    rows = []
    for _ in range(count):
        row = []
        for t in types:
            if t == STRING:
                length = struct.unpack("<i", take(4))[0]
                if not 0 <= length <= MAX_STRING:
                    raise ValueError("KO table: a %d-byte string" % length)
                row.append(take(length).decode("ascii", errors="replace"))
            else:
                fmt = FIXED[t]
                row.append(struct.unpack(fmt, take(struct.calcsize(fmt)))[0])
        rows.append(row)
    if offset != len(plain):
        raise ValueError("KO table: %d bytes after the last row" % (len(plain) - offset))
    return types, rows


def load(path):
    """Decrypt and parse one table file: (types, rows)."""
    return parse(decrypt(read(pathlib.Path(path), MAX_TABLE)))


def build(types, rows):
    """A plain table with these columns and rows, for synthetic fixtures."""
    out = bytearray(struct.pack("<i", len(types)) + struct.pack("<%di" % len(types), *types))
    out += struct.pack("<i", len(rows))
    for row in rows:
        for t, value in zip(types, row, strict=True):
            if t == STRING:
                data = value.encode("ascii")
                out += struct.pack("<i", len(data)) + data
            else:
                out += struct.pack(FIXED[t], value)
    return bytes(out)
