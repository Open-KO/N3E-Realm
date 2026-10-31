#!/usr/bin/env python3
"""Read a 2145 client table (`Data/*.tbl`) offline: unwrap, then parse (PQ-309).

Research tooling for the 2145 secondary reference (BINARY-POLICY): never a
build step. Record: docs/implementation/evidence/pq-309-ko-2145-table-cipher.md.
Since PQ-315 (D-184) the opt-in 2233 equipment glow cook
(tools/assetc/ko_glow_2233.py, `ko_bake.py ... --glow-2233`) reads the player's
own Item tables through it; no default cook does.

223 of the 231 tables in the 2145 installer are framed as

    [0, 16)   the constant MAGIC below
    [16, 20)  the plain length, big-endian u32
    [20, ...) whole 8-byte blocks, each deciphered on its own (ECB)

The block cipher is the DES round function without its initial and final
permutations, and with subkeys that come from a four-round derivation instead of
PC-1. The deciphered bytes, cut to the plain length, then pass through the same
autokey stream as the 1298 tables (the 1298 client's `0044f670`) with seed
`0x418`, multiplier `0x8041` and increment `0x1804`. Six of the other tables
carry that stream alone.

Provenance: the scheme, the key string and the four 56-bit derivation states
come from ThiagQPie/ko-tbl-decrypt commit bbc8dd2e5dc38fa6f828be64ae4fb0a825dfe733
(MIT), whose author read them from a client memory image of an unnamed build.
This file is n3e's own implementation; the DES tables (E as a rotation, P, PC-2,
the shift schedule and the S-boxes) are written from FIPS 46-3. The 2145
`KnightOnLine.exe` is packed, so none of this is located in its binary
(source-only). What is verified locally: every one of the 223 tables decodes,
and its plain bytes parse to the last byte (local-asset).

The plain table is a 5-byte header n3e does not interpret, then the 1298
layout (`006264d0`/`006359b0` in the 1298 client, binary there): an int32
column count, an int32 type per column, an int32 row count, then each row's
fields in column order. Types 1-9 read as in tools/assetc/ko_tbl.py; type 10,
which 1298 refuses, is 8 bytes here (read signed; the width is the only width
with which the four tables that use it parse to the end, local-asset).
"""

import argparse
import struct
import sys
from pathlib import Path

MAGIC = bytes.fromhex("4c26437f80f1579879fcaf2686d6208e")
KEY = b"8sgpV&22dsdLg3k"
STRENGTH = (  # the four derivation states, C||D, most significant bit first
    0b10100000010100110100110111011000001001011100001110010110,
    0b10101100000111101001111010000001101010001100001100000000,
    0b10001111101000110010010110000000111000101000100011111100,
    0b01101000010100011001010111000100111011011111100010011100,
)
SEED, MULTIPLIER, INCREMENT = 0x418, 0x8041, 0x1804
HEADER = 5
MAX_TABLE = 64 * 1024 * 1024
MAX_COLUMNS = 1024
MAX_STRING = 64 * 1024
STRING = 7
FIXED = {1: "<b", 2: "<B", 3: "<h", 4: "<H", 5: "<i", 6: "<I", 8: "<f", 9: "<d", 10: "<q"}

P = (16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10,
     2, 8, 24, 14, 32, 27, 3, 9, 19, 13, 30, 6, 22, 11, 4, 25)
PC2 = (14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4,
       26, 8, 16, 7, 27, 20, 13, 2, 41, 52, 31, 37, 47, 55, 30, 40,
       51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36, 29, 32)
SHIFTS = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)
SBOXES = (
    (14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
     4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13),
    (15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
     0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9),
    (10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
     13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12),
    (7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
     10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14),
    (2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
     4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3),
    (12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
     9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13),
    (4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
     1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12),
    (13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
     7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11),
)


def _sp_tables():
    """For each S-box, its 6-bit input -> its 4-bit output already placed by P."""
    tables = []
    for box, values in enumerate(SBOXES):
        table = []
        for six in range(64):
            nibble = values[((six >> 5) << 1 | (six & 1)) * 16 + ((six >> 1) & 15)]
            spread = nibble << (28 - 4 * box)
            table.append(sum(1 << (31 - i) for i in range(32) if spread >> (32 - P[i]) & 1))
        tables.append(table)
    return tables


SP = _sp_tables()


def schedule(cd):
    """PC-2 subkeys, as eight 6-bit groups each, from a 56-bit C||D state."""
    c, d, keys = cd >> 28, cd & 0xFFFFFFF, []
    for shift in SHIFTS:
        c = (c << shift | c >> (28 - shift)) & 0xFFFFFFF
        d = (d << shift | d >> (28 - shift)) & 0xFFFFFFF
        both = c << 28 | d
        key = 0
        for bit in PC2:
            key = key << 1 | (both >> (56 - bit) & 1)
        keys.append(tuple(key >> (42 - 6 * g) & 63 for g in range(8)))
    return keys


def _f(r, key):
    wide = (r & 1) << 33 | r << 1 | r >> 31  # E: R rotated so each group's six bits sit together
    out = 0
    for g in range(8):
        out |= SP[g][(wide >> (28 - 4 * g) & 63) ^ key[g]]
    return out


def crypt_block(block, keys):
    """Sixteen Feistel rounds without IP/FP; the last round does not swap, so
    deciphering is this with the subkeys reversed."""
    left, right = block >> 32, block & 0xFFFFFFFF
    for key in keys[:15]:
        left, right = right, left ^ _f(right, key)
    return (left ^ _f(right, keys[15])) << 32 | right


def derive():
    """The subkeys: four rounds of folding eight key-string bytes into a 64-bit
    state and enciphering it under one derivation state's subkeys; then the
    first 56 bits of the state are C||D. A finished string contributes zeros."""
    state, at = 0, 0
    for strength in STRENGTH:
        for k in range(8):
            byte = KEY[at] if at < len(KEY) else 0
            at += byte != 0
            state ^= byte << (56 - 8 * k)
        state = crypt_block(state, schedule(strength))
    return schedule(state >> 8)


KEYS = derive()


def stream(data, key=SEED):
    """The 1298 autokey stream (`0044f670` form) with the 2145 constants."""
    out = bytearray(len(data))
    for i, byte in enumerate(data):
        out[i] = byte ^ (key >> 8 & 0xFF)
        key = ((byte + key) * MULTIPLIER + INCREMENT) & 0xFFFF
    return bytes(out)


def unstream(plain, key=SEED):
    """The inverse of `stream`, for synthetic fixtures."""
    out = bytearray(len(plain))
    for i, byte in enumerate(plain):
        out[i] = byte ^ (key >> 8 & 0xFF)
        key = ((out[i] + key) * MULTIPLIER + INCREMENT) & 0xFFFF
    return bytes(out)


def unwrap(raw):
    """The plain bytes of a MAGIC-framed table."""
    if len(raw) > MAX_TABLE:
        raise ValueError("2145 table: %d bytes, over the bound" % len(raw))
    if len(raw) < 20 or raw[:16] != MAGIC:
        raise ValueError("2145 table: no MAGIC frame")
    size, body = struct.unpack(">I", raw[16:20])[0], raw[20:]
    if len(body) % 8 or size > len(body) or len(body) - size > 7:
        raise ValueError("2145 table: plain length %d for a %d-byte body" % (size, len(body)))
    keys = KEYS[::-1]
    plain = bytearray()
    for i in range(0, len(body), 8):
        plain += crypt_block(int.from_bytes(body[i:i + 8], "big"), keys).to_bytes(8, "big")
    return stream(bytes(plain[:size]))


def wrap(plain):
    """The inverse of `unwrap`, for synthetic fixtures: zero padding to a block."""
    data = unstream(plain)
    data += bytes(-len(data) % 8)
    body = b"".join(crypt_block(int.from_bytes(data[i:i + 8], "big"), KEYS).to_bytes(8, "big")
                    for i in range(0, len(data), 8))
    return MAGIC + struct.pack(">I", len(plain)) + body


def parse(plain, offset=0):
    """(column types, rows) of the 1298 layout starting at `offset`; refuses a
    bound overrun, an unknown type, a short field and any byte after the last row."""

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(plain):
            raise ValueError("2145 table: a field runs past the end at byte %d" % offset)
        offset += size
        return plain[offset - size:offset]

    columns = struct.unpack("<i", take(4))[0]
    if not 1 <= columns <= MAX_COLUMNS:
        raise ValueError("2145 table: %d columns" % columns)
    types = list(struct.unpack("<%di" % columns, take(4 * columns)))
    for t in types:
        if t != STRING and t not in FIXED:
            raise ValueError("2145 table: column type %d" % t)
    count = struct.unpack("<i", take(4))[0]
    if count < 0 or count * columns > len(plain) - offset:
        raise ValueError("2145 table: %d rows" % count)
    rows = []
    for _ in range(count):
        row = []
        for t in types:
            if t == STRING:
                length = struct.unpack("<i", take(4))[0]
                if not 0 <= length <= MAX_STRING:
                    raise ValueError("2145 table: a %d-byte string" % length)
                row.append(take(length).decode("cp949", errors="replace"))
            else:
                fmt = FIXED[t]
                row.append(struct.unpack(fmt, take(struct.calcsize(fmt)))[0])
        rows.append(row)
    if offset != len(plain):
        raise ValueError("2145 table: %d bytes after the last row" % (len(plain) - offset))
    return types, rows


def load(path):
    """(framing, header, column types, rows) of one table file. A MAGIC frame is
    unwrapped and its 5-byte header kept; any other file is tried as the bare
    stream with no header, and refused when that does not parse."""
    path = Path(path)
    if path.stat().st_size > MAX_TABLE:
        raise ValueError("2145 table: %s is over the bound" % path)
    raw = path.read_bytes()
    if raw[:16] == MAGIC:
        plain = unwrap(raw)
        if len(plain) < HEADER:
            raise ValueError("2145 table: no header")
        return ("block", plain[:HEADER]) + parse(plain, HEADER)
    return ("stream", b"") + parse(stream(raw))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("table", type=Path)
    ap.add_argument("--rows", type=int, default=3, help="rows to print (default 3; -1 for all)")
    ap.add_argument("--column", type=int, action="append", default=[],
                    help="print only these 0-based columns (repeatable)")
    args = ap.parse_args(argv)
    try:
        framing, header, types, rows = load(args.table)
    except (OSError, ValueError) as error:
        print("ERROR %s" % error, file=sys.stderr)
        return 1
    print("%s framing=%s header=%s columns=%d rows=%d" % (args.table.name, framing, header.hex() or "-", len(types), len(rows)))
    print("types " + " ".join(map(str, types)))
    for row in rows if args.rows < 0 else rows[:args.rows]:
        picked = [row[c] for c in args.column if 0 <= c < len(row)] if args.column else row
        print("\t".join(map(str, picked)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
