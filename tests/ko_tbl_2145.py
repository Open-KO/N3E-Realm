"""PQ-309: the research 2145 table reader (tools/ko-reference/tbl_2145.py).

The block cipher is checked against the FIPS 46-3 worked example (key
133457799BBCDFF1, block 0123456789ABCDEF -> 85E813540F0AB405) by wrapping the
reader's IP/FP-less rounds in the standard IP, FP and PC-1, so the round
function, S-boxes, P, PC-2 and shift schedule are checked against DES itself
rather than against the reader. Synthetic tables (original rows) round-trip
through the MAGIC frame and the bare stream, and bad frames, bounds and layouts
are refused. With the player's own 2145 extraction in
build/ko-reference/installer-2145/ (never committed; SKIP without it) Zones.tbl
and an armour extension table are read and Zones.tbl re-enciphers to its exact
bytes. `tests/ko_terrain.py` (so `make test`) runs this file; it also runs alone.
"""
import contextlib, importlib.util, io, shutil, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tbl_2145", ROOT / "tools/ko-reference/tbl_2145.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

B = ROOT / "build/pq309-test"
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)

# FIPS 46-3 permutations, used only to frame the reader's rounds as standard DES.
IP = (58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
      64, 56, 48, 40, 32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3,
      61, 53, 45, 37, 29, 21, 13, 5, 63, 55, 47, 39, 31, 23, 15, 7)
PC1 = (57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27, 19, 11, 3,
       60, 52, 44, 36, 63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37,
       29, 21, 13, 5, 28, 20, 12, 4)


def permute(value, table, width):
    out = 0
    for bit in table:
        out = out << 1 | (value >> (width - bit) & 1)
    return out


def inverse(table):
    inv = [0] * len(table)
    for i, bit in enumerate(table):
        inv[bit - 1] = i + 1
    return tuple(inv)


def refused(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


key = 0x133457799BBCDFF1
keys = tool.schedule(permute(key, PC1, 64))
plain_block, cipher_block = 0x0123456789ABCDEF, 0x85E813540F0AB405
assert permute(tool.crypt_block(permute(plain_block, IP, 64), keys), inverse(IP), 64) == cipher_block
assert permute(tool.crypt_block(permute(cipher_block, IP, 64), keys[::-1]), inverse(IP), 64) == plain_block
print("PASS 2145 table block cipher: FIPS 46-3 example through IP/PC-1 framing")

types = [6, 7, 1, 2, 3, 4, 5, 8, 9, 10, 7]
rows = [[4000000000, "Zones\\karus.gtd", -5, 250, -300, 60000, -70000, 1.5, -2.25, -(1 << 40), ""],
        [7, "Azagai", 0, 0, 0, 0, 0, 0.0, 0.0, 1 << 50, "x" * 300]]
fmt = {1: "<b", 2: "<B", 3: "<h", 4: "<H", 5: "<i", 6: "<I", 8: "<f", 9: "<d", 10: "<q"}


def layout(types, rows, extra=b""):
    out = struct.pack("<i", len(types)) + struct.pack("<%di" % len(types), *types) + struct.pack("<i", len(rows))
    for row in rows:
        for t, v in zip(types, row, strict=True):
            out += struct.pack("<i", len(v)) + v.encode() if t == 7 else struct.pack(fmt[t], v)
    return out + extra


header = bytes.fromhex("a54e000406")
plain = header + layout(types, rows)
raw = tool.wrap(plain)
assert raw[:16] == tool.MAGIC and struct.unpack(">I", raw[16:20])[0] == len(plain)
assert (len(raw) - 20) % 8 == 0 and len(raw) - 20 - len(plain) < 8
assert tool.unwrap(raw) == plain
(B / "block.tbl").write_bytes(raw)
assert tool.load(B / "block.tbl") == ("block", header, types, rows)
(B / "stream.tbl").write_bytes(tool.unstream(layout(types[:2], [r[:2] for r in rows])))
assert tool.load(B / "stream.tbl") == ("stream", b"", types[:2], [r[:2] for r in rows])
out = io.StringIO()
with contextlib.redirect_stdout(out):
    assert tool.main([str(B / "block.tbl"), "--column", "1", "--column", "9"]) == 0
assert out.getvalue().splitlines()[0] == "block.tbl framing=block header=a54e000406 columns=11 rows=2", out.getvalue()
assert out.getvalue().splitlines()[2] == "Zones\\karus.gtd\t%d" % -(1 << 40)
print("PASS 2145 table round trip: MAGIC frame, bare stream, every column type, CLI")

body = raw[20:]
bad_frames = {
    "short": raw[:19],
    "magic": bytes([raw[0] ^ 1]) + raw[1:],
    "partial block": raw[:-1],
    "length past body": raw[:16] + struct.pack(">I", len(body) + 1) + body,
    "eight pad bytes": raw[:16] + struct.pack(">I", len(plain)) + body + bytes(8),
}
for name, data in bad_frames.items():
    assert refused(tool.unwrap, data), name
bad_layouts = {
    "type 11": layout([6, 11], []),
    "no columns": layout([], []),
    "too many columns": struct.pack("<i", tool.MAX_COLUMNS + 1),
    "row count": layout([6], [])[:-4] + struct.pack("<i", 1),
    "after last row": layout([6], [[1]], b"\0"),
    "long string": layout([7], [["a"]])[:-5] + struct.pack("<i", tool.MAX_STRING + 1) + b"a",
    "short field": layout([6, 6], [[1, 2]])[:-1],
}
for name, data in bad_layouts.items():
    assert refused(tool.parse, data), name
    (B / "bad.tbl").write_bytes(tool.wrap(header + data))
    assert refused(tool.load, B / "bad.tbl"), name
(B / "noise.tbl").write_bytes(bytes(range(256)) * 4)
assert refused(tool.load, B / "noise.tbl")
err = io.StringIO()
with contextlib.redirect_stderr(err):
    assert tool.main([str(B / "noise.tbl")]) == 1
assert err.getvalue().startswith("ERROR ")
saved = tool.MAX_TABLE
tool.MAX_TABLE = len(raw) - 1
try:
    assert refused(tool.load, B / "block.tbl") and refused(tool.unwrap, raw)
finally:
    tool.MAX_TABLE = saved
print("PASS 2145 table refusals: %d frames, %d layouts, noise, size bound" % (len(bad_frames), len(bad_layouts)))

data = ROOT / "build/ko-reference/installer-2145/client/Data"
if not (data / "Zones.tbl").is_file():
    print("SKIP 2145 tables: no extraction in build/ko-reference/installer-2145")
else:
    zones = (data / "Zones.tbl").read_bytes()
    framing, head, ztypes, zrows = tool.load(data / "Zones.tbl")
    assert framing == "block" and head[:2] == b"\xa5\x4e" and len(ztypes) == 27, (framing, head, len(ztypes))
    assert zrows[0][:2] == [0, "knightonline.exe"] and zrows[1][:3] == [10, "Zones\\karus2004.gtd", "karus2004"], zrows[1][:3]
    assert tool.wrap(tool.unwrap(zones)) == zones
    _, _, etypes, erows = tool.load(data / "Item_Ext_13_us.tbl")
    assert len(etypes) == 56 and erows and all(r[4] == 0 for r in erows)
    print("PASS 2145 tables: Zones.tbl %d rows, re-enciphered byte for byte; Item_Ext_13_us %d rows, no effect id"
          % (len(zrows), len(erows)))
