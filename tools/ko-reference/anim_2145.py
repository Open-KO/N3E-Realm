#!/usr/bin/env python3
"""Read a 2145 client clip table (`*.n3anim`) offline (PQ-330).

Research tooling for the 2145 secondary reference (BINARY-POLICY): never a
build step, and it writes no files. Since PQ-317 the opt-in 2233 additions cook
(tools/assetc/ko_chrplug_2145.py) converts a skeletal plug's clip table with
`parse` and `to_1298` for ko_character. Record:
docs/implementation/evidence/pq-330-ko-2145-anim-cipher.md.

A framed table is a u32 clip count, then per clip a u32 frame length and one
frame of the PQ-309 table cipher: the 16-byte MAGIC, a big-endian u32 plain
length and whole 8-byte blocks. The frame is opened by the block stage alone
(`tbl_2145.crypt_block` under the reversed subkeys) with no autokey stream; the
2233 client image does the same (`0048aaf0`: the key `8sgpV&22dsdLg3k` built on
the stack, `004ea5a0`, then `004ea7f0`, and no call to the stream `00484d40`;
binary for that image, a secondary reference). The plain record is the one the
2233 loose-file clip load reads (`CN3AnimControl::Load_Old` `0042b930`, record
`0042ad90`; picked by `CN3BaseFileAccess::LoadFromFile_ExistingFilename`
`0045ba30` for a file outside the packs):

    [0, 2)    u16, read and dropped
    [2, 6)    u32, read and dropped (the 1298 record's own unused first field,
              `00410c00`, which 1298 also drops)
    [6, 50)   start, end, fps, plug-trace start and end, sound 0 and 1, blend
              seconds (floats), blend flags (i32), strike 0 and 1 (floats):
              the 1298 record's eleven fields in its order
    [50, 54)  i32 name length n
    [54, 54+n) the name; the record ends there

Names are read as C strings, as both clients read them (`00410c00` in 1298,
`0042ad90` in 2233). The 2233 pack load (`CN3AnimControl::Load` `0042b560`,
record `0042ab60`) reads one more u32 before the eleven fields; no 2145 clip
table is in a pack, and this reader does not read that form (its name length
then misses the record end, and the record is refused). A plain table (the 1298
layout, as `Intro/intro.n3anim`) is read as `tools/assetc/ko_character.py`
reads it, without its range checks and with any value in the unused field.

Bounds the client does not have, all refused: a file over 1 MiB, more than 256
clips, a frame over 1 KiB, a frame that is not MAGIC, a body that is empty or
not whole blocks, a plain length past the body or more than 7 bytes short of
it, padding that is not zero, a record shorter than 54 bytes, a name length
outside 0-255 or one that does not end the record exactly, a name byte outside
printable ASCII, a non-finite float, a table that mixes framed and plain
records, and any byte after the last clip.
"""

import argparse
import importlib.util
import math
import struct
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("tbl_2145", Path(__file__).with_name("tbl_2145.py"))
tbl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tbl)

MAX_FILE = 1024 * 1024
MAX_CLIPS = 256
MAX_FRAME = 1024
MAX_NAME = 255
FIXED = 54  # bytes before the name in a framed record
PLAIN_FIXED = 52  # the same in a 1298 record
FIELDS = "<8fi2f"  # start, end, fps, trace x2, sound x2, blend; flags; strike x2


def _clip(head, word, values, name):
    floats = values[:8] + values[9:]
    if not all(math.isfinite(v) for v in floats):
        raise ValueError("2145 clip: a non-finite field")
    name, nul, rest = name.partition(b"\0")  # read as a C string (00410c00, 0042ad90)
    if any(rest):
        raise ValueError("2145 clip: bytes after the name's terminator")
    if not all(0x20 <= b <= 0x7E for b in name):
        raise ValueError("2145 clip: a name byte outside printable ASCII")
    return {
        "head": head,
        "word": word,
        "start": values[0],
        "end": values[1],
        "fps": values[2],
        "trace": list(values[3:5]),
        "sound": list(values[5:7]),
        "blend_seconds": values[7],
        "blend_flags": values[8],
        "strike": list(values[9:11]),
        "name": name.decode("ascii"),
    }


def open_frame(raw):
    """The plain bytes of one clip frame: block stage only, zero padding."""
    if len(raw) > MAX_FRAME:
        raise ValueError("2145 clip: a %d-byte frame, over the bound" % len(raw))
    if len(raw) < 20 or raw[:16] != tbl.MAGIC:
        raise ValueError("2145 clip: no MAGIC frame")
    size, body = struct.unpack(">I", raw[16:20])[0], raw[20:]
    if not body or len(body) % 8 or size > len(body) or len(body) - size > 7:
        raise ValueError("2145 clip: plain length %d for a %d-byte body" % (size, len(body)))
    keys = tbl.KEYS[::-1]
    plain = b"".join(tbl.crypt_block(int.from_bytes(body[i:i + 8], "big"), keys).to_bytes(8, "big")
                     for i in range(0, len(body), 8))
    if any(plain[size:]):
        raise ValueError("2145 clip: padding that is not zero")
    return plain[:size]


def parse_record(plain):
    """One clip from a framed record's plain bytes (the `0042ad90` layout)."""
    if len(plain) < FIXED:
        raise ValueError("2145 clip: a %d-byte record" % len(plain))
    head, word = struct.unpack_from("<HI", plain, 0)
    values = struct.unpack_from(FIELDS, plain, 6)
    length = struct.unpack_from("<i", plain, 50)[0]
    if not 0 <= length <= MAX_NAME:
        raise ValueError("2145 clip: name length %d" % length)
    if FIXED + length != len(plain):
        raise ValueError("2145 clip: the name ends %d bytes before the record" % (len(plain) - FIXED - length))
    return _clip(head, word, values, plain[FIXED:])


def parse(data):
    """(framing, clips) of one clip table's bytes: framing is `empty`,
    `block` (every clip a frame) or `plain` (the 1298 layout)."""
    if len(data) > MAX_FILE:
        raise ValueError("2145 clip table: %d bytes, over the bound" % len(data))
    if len(data) < 4:
        raise ValueError("2145 clip table: no count")
    count = struct.unpack_from("<I", data, 0)[0]
    if count > MAX_CLIPS:
        raise ValueError("2145 clip table: %d clips" % count)
    if count == 0:
        if len(data) != 4:
            raise ValueError("2145 clip table: %d bytes after the last clip" % (len(data) - 4))
        return "empty", []
    framing = "block" if data[8:24] == tbl.MAGIC else "plain"
    at, clips = 4, []
    for _ in range(count):
        if framing == "block":
            if at + 4 > len(data):
                raise ValueError("2145 clip table: truncated at byte %d" % at)
            size = struct.unpack_from("<I", data, at)[0]
            if size > MAX_FRAME or at + 4 + size > len(data):
                raise ValueError("2145 clip table: a %d-byte frame at byte %d" % (size, at))
            clips.append(parse_record(open_frame(data[at + 4:at + 4 + size])))
            at += 4 + size
        else:
            if at + PLAIN_FIXED > len(data):
                raise ValueError("2145 clip table: truncated at byte %d" % at)
            if data[at + 4:at + 20] == tbl.MAGIC:
                raise ValueError("2145 clip table: framed and plain records mixed")
            word = struct.unpack_from("<I", data, at)[0]
            values = struct.unpack_from(FIELDS, data, at + 4)
            length = struct.unpack_from("<i", data, at + 48)[0]
            if not 0 <= length <= MAX_NAME or at + PLAIN_FIXED + length > len(data):
                raise ValueError("2145 clip table: name length %d at byte %d" % (length, at))
            clips.append(_clip(None, word, values, data[at + PLAIN_FIXED:at + PLAIN_FIXED + length]))
            at += PLAIN_FIXED + length
    if at != len(data):
        raise ValueError("2145 clip table: %d bytes after the last clip" % (len(data) - at))
    return framing, clips


def load(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE:
        raise ValueError("2145 clip table: %s is over the bound" % path)
    return parse(path.read_bytes())


def _fields(clip):
    return struct.pack(FIELDS, clip["start"], clip["end"], clip["fps"], *clip["trace"], *clip["sound"],
                       clip["blend_seconds"], clip["blend_flags"], *clip["strike"])


def to_1298(clips):
    """The same clips in the 1298 plain layout, unused field 0, which
    `tools/assetc/ko_character.animations` reads."""
    out = struct.pack("<I", len(clips))
    for clip in clips:
        name = clip["name"].encode("ascii")
        out += struct.pack("<I", 0) + _fields(clip) + struct.pack("<i", len(name)) + name
    return out


def frame(plain):
    """The inverse of `open_frame`, for synthetic fixtures: zero padding."""
    data = plain + bytes(-len(plain) % 8)
    body = b"".join(tbl.crypt_block(int.from_bytes(data[i:i + 8], "big"), tbl.KEYS).to_bytes(8, "big")
                    for i in range(0, len(data), 8))
    return tbl.MAGIC + struct.pack(">I", len(plain)) + body


def record(clip):
    """A framed record's plain bytes, for synthetic fixtures."""
    name = clip["name"].encode("ascii")
    return struct.pack("<HI", clip["head"], clip["word"]) + _fields(clip) + struct.pack("<i", len(name)) + name


def table(clips):
    """A framed clip table, for synthetic fixtures."""
    out = struct.pack("<I", len(clips))
    for clip in clips:
        raw = frame(record(clip))
        out += struct.pack("<I", len(raw)) + raw
    return out


def _paths(args):
    for path in args:
        if path.is_dir():
            yield from sorted(p for p in path.iterdir() if p.suffix.lower() == ".n3anim" and p.is_file())
        else:
            yield path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", type=Path, nargs="+", help="a clip table, or a folder of them (not recursive)")
    ap.add_argument("--summary", action="store_true", help="one line per table, no clip lines")
    args = ap.parse_args(argv)
    files = ok = clips = 0
    for path in _paths(args.path):
        files += 1
        try:
            framing, rows = load(path)
        except (OSError, ValueError) as error:
            print("REFUSED %s %s" % (path.name, error))
            continue
        ok += 1
        clips += len(rows)
        print("TABLE %s framing=%s clips=%d" % (path.name, framing, len(rows)))
        if args.summary:
            continue
        print("#\tname\tstart\tend\tfps\ttrace0\ttrace1\tsound0\tsound1\tblend\tflags\tstrike0\tstrike1\thead\tword")
        for i, c in enumerate(rows):
            floats = (c["start"], c["end"], c["fps"], *c["trace"], *c["sound"], c["blend_seconds"])
            print("\t".join([str(i), c["name"] or "-"] + ["%.7g" % v for v in floats] + [str(c["blend_flags"])]
                             + ["%.7g" % v for v in c["strike"]]
                             + ["-" if c["head"] is None else str(c["head"]), "0x%08x" % c["word"]]))
    print("ANIM files=%d ok=%d refused=%d clips=%d" % (files, ok, files - ok, clips))
    return 0 if files and ok == files else 2


if __name__ == "__main__":
    sys.exit(main())
