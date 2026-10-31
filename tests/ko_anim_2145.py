"""PQ-330: the research 2145 clip-table reader (tools/ko-reference/anim_2145.py).

Synthetic clip tables (original clip names and values) are written here byte by
byte, with the record layout the 2233 loose-file clip load reads (`0042ad90`:
u16, u32, eleven 4-byte fields, i32 name length, name), each record framed
with the PQ-309 block cipher alone (the 2233 frame `0048aaf0`, no autokey
stream). They are read back, converted to the 1298 layout and read by n3e's
1299 reader, and every malformed table is refused. With the player's own 2145
unpack in build/ko-reference/installer-2145/ (never committed; SKIP without
it) the 441 shipped clip tables are read. `tests/ko_terrain.py` (so
`make test`) runs this file; it also runs alone. It writes nothing.
"""
import contextlib, importlib.util, io, math, struct, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("anim_2145", ROOT / "tools/ko-reference/anim_2145.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
tbl = tool.tbl
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko_character  # noqa: E402


def encipher(data):
    """Whole blocks enciphered one by one under the forward subkeys."""
    assert len(data) % 8 == 0
    return b"".join(tbl.crypt_block(int.from_bytes(data[i:i + 8], "big"), tbl.KEYS).to_bytes(8, "big")
                    for i in range(0, len(data), 8))


def plain_record(head, word, start, end, fps, trace, sound, blend, flags, strike, name, extra=b""):
    """The 0042ad90 layout, written field by field at fixed offsets."""
    out = bytearray(54)
    struct.pack_into("<H", out, 0, head)
    struct.pack_into("<I", out, 2, word)
    struct.pack_into("<f", out, 6, start)
    struct.pack_into("<f", out, 10, end)
    struct.pack_into("<f", out, 14, fps)
    struct.pack_into("<ff", out, 18, *trace)
    struct.pack_into("<ff", out, 26, *sound)
    struct.pack_into("<f", out, 34, blend)
    struct.pack_into("<i", out, 38, flags)
    struct.pack_into("<ff", out, 42, *strike)
    struct.pack_into("<i", out, 50, len(name))
    return bytes(out[:50]) + extra + bytes(out[50:]) + name


def framed(plain, size=None, pad=b"", magic=None):
    data = plain + (pad or bytes(-len(plain) % 8))
    return (magic or tbl.MAGIC) + struct.pack(">I", len(plain) if size is None else size) + encipher(data)


def table(frames, count=None, tail=b""):
    out = struct.pack("<I", len(frames) if count is None else count)
    for raw in frames:
        out += struct.pack("<I", len(raw)) + raw
    return out + tail


def refused(tag, data, needle):
    try:
        tool.parse(data)
    except ValueError as error:
        assert needle in str(error), (tag, str(error))
        return
    raise AssertionError("%s: not refused" % tag)


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tool.main([str(a) for a in argv])
    return code, out.getvalue()


# A table of clips whose names run 0 to 9 bytes, so the plain lengths 54-63 give
# every padding length from 0 to 7 bytes (and two of them twice).
CLIPS = []
for n in range(10):
    CLIPS.append(dict(head=n % 10, word=0x40490FDB, start=float(10 * n), end=float(10 * n + 30), fps=30.0 + n,
                      trace=(1.5, 2.5), sound=(float(n), 0.0), blend=0.25, flags=n % 2,
                      strike=(float(10 * n + 15), 0.0), name=b"clipxyzwv"[:n]))
FRAMES = [framed(plain_record(**c)) for c in CLIPS]
assert sorted({len(f) - 20 - (54 + len(c["name"])) for f, c in zip(FRAMES, CLIPS)}) == list(range(8))
DATA = table(FRAMES)
framing, clips = tool.parse(DATA)
assert framing == "block" and len(clips) == 10
for c, got in zip(CLIPS, clips):
    assert got == {"head": c["head"], "word": c["word"], "start": c["start"], "end": c["end"], "fps": c["fps"],
                   "trace": list(c["trace"]), "sound": list(c["sound"]), "blend_seconds": c["blend"],
                   "blend_flags": c["flags"], "strike": list(c["strike"]), "name": c["name"].decode()}, got

# The tool's own fixture writers agree with the hand-written bytes.
assert tool.table(clips) == DATA

# Converted to the 1298 layout, n3e's 1299 reader reads the same clips.
old = ko_character.animations(tool.to_1298(clips))
assert [(c["name"], c["start"], c["end"], c["fps"], c["blend_seconds"], c["blend_flags"], c["strike"])
        for c in old] == [(c["name"], c["start"], c["end"], c["fps"], c["blend_seconds"], c["blend_flags"],
                           c["strike"]) for c in clips]
assert all(o["trace"] == c["trace"] and o["sound"] == c["sound"] for o, c in zip(old, clips))
# ... and this reader reads that 1298 table back as a plain one.
framing, back = tool.parse(tool.to_1298(clips))
assert framing == "plain" and [dict(c, head=None, word=0) for c in clips] == back

# A plain 1298 table (original values) whose name length counts a terminator
# and whose dropped first field is not zero, the two traits the shipped
# Intro/intro.n3anim shows.
plain_nul = struct.pack("<II8fi2fi", 1, 0x01020304, 5, 420, 25, 0, 0, 0, 0, 0.5, 0, 0, 0, 5) + b"idle\0"
framing, got = tool.parse(plain_nul)
assert framing == "plain" and got[0]["name"] == "idle" and got[0]["end"] == 420 and got[0]["word"] == 0x01020304
# A framed name read as a C string the same way.
assert tool.parse(table([framed(plain_record(**dict(CLIPS[0], name=b"ab\0\0")))]))[1][0]["name"] == "ab"
# Empty tables, a 255-byte name, 256 clips.
assert tool.parse(struct.pack("<I", 0)) == ("empty", [])
assert tool.parse(table([framed(plain_record(**dict(CLIPS[0], name=b"n" * 255)))]))[1][0]["name"] == "n" * 255
assert len(tool.parse(table([FRAMES[3]] * 256))[1]) == 256
# The u16 is read unsigned.
assert tool.parse(table([framed(plain_record(**dict(CLIPS[1], head=0xFFFF)))]))[1][0]["head"] == 0xFFFF
# A flags field holding float bits (as some shipped 1298 and 2145 NPC tables do) is kept as read.
assert tool.parse(table([framed(plain_record(**dict(CLIPS[1], flags=0x3E99999A)))]))[1][0]["blend_flags"] == 0x3E99999A

# Refusals.
rec = plain_record(**CLIPS[4])
refused("count", table(FRAMES[:1], count=257), "257 clips")
refused("short count", b"\0\0\0", "no count")
refused("empty with tail", struct.pack("<I", 0) + b"x", "bytes after the last clip")
refused("trailing", table(FRAMES[:2], tail=b"\0"), "bytes after the last clip")
refused("cut in a length", table(FRAMES[:2])[:-len(FRAMES[1]) - 2], "truncated")
refused("cut in a frame", table(FRAMES[:2])[:-3], "frame at byte")
big = framed(plain_record(**dict(CLIPS[0], name=b"n" * 255)) + bytes(1000))
refused("frame bound", table([big]), "frame")
try:
    tool.open_frame(big)
    raise AssertionError("open_frame: frame bound not refused")
except ValueError as error:
    assert "over the bound" in str(error), error
refused("no magic", table(FRAMES[:1] + [framed(rec, magic=bytes(16))]), "no MAGIC frame")
refused("magic only", table([FRAMES[0], tbl.MAGIC + struct.pack(">I", 0)]), "plain length 0 for a 0-byte body")
refused("part block", table([FRAMES[0], FRAMES[1][:-1]]), "-byte body")
refused("length past body", table([framed(rec, size=len(rec) + 8)]), "plain length")
rec56 = plain_record(**dict(CLIPS[2], name=b"ab"))
assert len(rec56) == 56
refused("length 8 short", table([framed(rec56 + bytes(8), size=56)]), "plain length 56 for a 64-byte body")
refused("padding", table([framed(rec, pad=b"\x01" + bytes(-len(rec) % 8 - 1))]), "padding")
refused("record short", table([framed(rec[:53])]), "53-byte record")
refused("name length -1", table([framed(rec[:50] + struct.pack("<i", -1) + rec[54:])]), "name length -1")
refused("name length 256", table([framed(rec[:50] + struct.pack("<i", 256) + bytes(256))]), "name length 256")
refused("name short", table([framed(rec + b"z")]), "the name ends 1 bytes before")
refused("name long", table([framed(rec[:-1])]), "the name ends -1 bytes before")
refused("name byte", table([framed(plain_record(**dict(CLIPS[3], name=b"a\xb0b")))]), "printable ASCII")
refused("name control", table([framed(plain_record(**dict(CLIPS[3], name=b"a\tb")))]), "printable ASCII")
refused("after terminator", table([framed(plain_record(**dict(CLIPS[3], name=b"a\0b")))]), "terminator")
refused("nan", table([framed(plain_record(**dict(CLIPS[3], fps=math.nan)))]), "non-finite")
refused("inf", table([framed(plain_record(**dict(CLIPS[3], strike=(0.0, math.inf))))]), "non-finite")
# The 2233 pack-form record (0042ab60): one more u32 before the eleven fields.
refused("pack form", table([framed(plain_record(**dict(CLIPS[4], extra=struct.pack("<f", 9.0))))]), "name")
# A frame enciphered with the PQ-309 table stream as well does not read.
refused("stream", table([tbl.wrap(rec)]), "2145 clip: ")
# A table mixing a plain 1298 record with a framed one.
plain1 = tool.to_1298(clips[:1])
refused("mixed", plain1 + struct.pack("<I", len(FRAMES[0])) + FRAMES[0], "bytes after the last clip")
refused("mixed count", struct.pack("<I", 2) + plain1[4:] + struct.pack("<I", len(FRAMES[0])) + FRAMES[0],
        "framed and plain records mixed")
refused("text", b"[section]\r\nfoo=1\r\n", "clips")
saved = tool.MAX_FILE
tool.MAX_FILE = len(DATA) - 1
refused("file bound", DATA, "over the bound")
tool.MAX_FILE = saved

# The command line: a folder (any extension case, not recursive), one refusal.
with tempfile.TemporaryDirectory() as top:
    top = Path(top)
    (top / "a.n3anim").write_bytes(DATA)
    (top / "b.n3Anim").write_bytes(struct.pack("<I", 0))
    (top / "c.n3anim").write_bytes(b"[_x_]")
    (top / "d.txt").write_bytes(b"ignored")
    (top / "sub").mkdir()
    (top / "sub" / "e.n3anim").write_bytes(DATA)
    code, out = run(top, "--summary")
    assert code == 2 and out.splitlines() == [
        "TABLE a.n3anim framing=block clips=10", "TABLE b.n3Anim framing=empty clips=0",
        "REFUSED c.n3anim 2145 clip table: 1601724251 clips", "ANIM files=3 ok=2 refused=1 clips=10"], out
    code, out = run(top / "a.n3anim")
    lines = out.splitlines()
    assert code == 0 and lines[0] == "TABLE a.n3anim framing=block clips=10" and lines[-1].startswith("ANIM files=1 ok=1")
    assert lines[3].split("\t") == ["1", "c", "10", "40", "31", "1.5", "2.5", "1", "0", "0.25", "1", "25", "0",
                                    "1", "0x40490fdb"], lines[3]
    assert lines[2].split("\t")[1] == "-"
    assert run(top / "missing.n3anim")[0] == 2

print("PASS 2145 clip reader: synthetic tables in the 2233 loose-file record layout (0042ad90), each record "
      "framed by the block cipher alone, read back field by field and through n3e's 1299 reader after "
      "conversion; empty tables, C-string names and every padding length read, and 30 malformed tables refused")

CLIENT = ROOT / "build/ko-reference/installer-2145/client"
if not (CLIENT / "Chr").is_dir():
    print("SKIP 2145 clip tables: no unpack in build/ko-reference/installer-2145")
    sys.exit(0)
code, out = run(CLIENT / "Chr", "--summary")
assert code == 0 and out.splitlines()[-1] == "ANIM files=412 ok=412 refused=0 clips=8760", out[-200:]
assert out.count("framing=empty") == 2 and out.count("framing=block") == 410
code, out = run(CLIENT / "ChrSelect", "--summary")
assert code == 2 and out.splitlines()[-1] == "ANIM files=28 ok=27 refused=1 clips=81"
assert "REFUSED upc_ka_wt_ma_ARES1.n3anim" in out and out.count("framing=block") == 27
framing, intro_clips = tool.load(CLIENT / "Intro/intro.n3anim")
assert framing == "plain" and [c["name"] for c in intro_clips] == ["loop"]
framing, bow = tool.load(CLIENT / "Chr/bow_boss_uer_h01.n3anim")
assert framing == "block" and [c["name"] for c in bow] == ["breath", "attackbreath", "attack", "die", "struck", "magic"]
assert [(c["start"], c["end"], c["fps"]) for c in bow] == [(1, 80, 45), (100, 140, 50), (140, 140, 25), (1, 100, 40),
                                                           (170, 170, 30), (160, 195, 55)]
assert ko_character.animations(tool.to_1298(bow))[0]["name"] == "breath"
print("PASS 2145 clip tables: the player's 412 tables in Chr/ (8,760 clips, 2 empty) and 27 of the 28 in "
      "ChrSelect/ (81 clips; the text file refused) read framed, Intro/intro.n3anim plain, and the Azagai "
      "bow's six clips read through n3e's 1299 reader")
