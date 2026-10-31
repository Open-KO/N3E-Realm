"""PQ-308: the research 2145 pack reader (tools/ko-reference/pack_2145.py).

Synthetic packs (original names and bytes) are written as the 2145 launcher
writes them (`00407ae7`: u32 count, then per entry u32 name length, the name,
u32 offset, u32 size), listed, read by name and extracted under build/. Every
refusal (count, name length, name form, traversal, duplicates, the client's
lookup key, file-and-folder names, ranges outside the .src, overlapping ranges,
header and .src bounds, an output outside build/, a symlink inside it on any
selected entry, and a file or folder in a target's way) happens before
anything is written, and an existing hardlink is replaced, not written
through. With the player's own 2145 extraction in
build/ko-reference/installer-2145/ (never committed; SKIP without it) the four
shipped packs are read whole. `tests/ko_terrain.py` (so `make test`) runs this
file; it also runs alone.
"""
import contextlib, importlib.util, io, os, shutil, struct, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pack_2145", ROOT / "tools/ko-reference/pack_2145.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

B = ROOT / "build/pq308-test"
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)


def header(entries, count=None, tail=b""):
    out = struct.pack("<I", len(entries) if count is None else count)
    for name, offset, size in entries:
        raw = name if isinstance(name, bytes) else name.encode("ascii")
        out += struct.pack("<I", len(raw)) + raw + struct.pack("<II", offset, size)
    return out + tail


def pack(tag, entries, src, cut=0, **kw):
    folder = B / tag
    folder.mkdir()
    raw = header(entries, **kw)
    (folder / "pk.hdr").write_bytes(raw[:len(raw) - cut])
    (folder / "pk.src").write_bytes(src)
    return folder / "pk.hdr"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = tool.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


# A pack laid out like the shipped ones: fx-style backslash paths, a zero-size
# entry, unreferenced bytes between ranges and after the last, entries out of
# offset order.
blobs = {"object\\41201item_glow\\glow.n3pmesh": b"mesh bytes " * 7,
         "billboard\\0000cen\\spark_0001.dxt": bytes(range(256)) * 3,
         "13th_knight_final.n3fxbundle.fxb": b"bundle",
         "obj_empty": b""}
src, entries = bytearray(), []
for name, blob in blobs.items():
    src += b"\xee" * 5  # unreferenced
    entries.append((name, len(src), len(blob)))
    src += blob
src += b"\xee" * 9
entries.reverse()
good = pack("good", entries, bytes(src))
p = tool.Pack(good)
assert len(p.entries) == 4 and p.source_size == len(src), p.entries
assert p.unreferenced == 5 * 4 + 9, p.unreferenced
for name, blob in blobs.items():
    assert p.read(name) == blob, name
    assert p.read(name.upper().replace("\\", "/")) == blob, name  # lower-cased, / for \\, as the client looks up
assert p.find("missing.dxt") is None
assert tool.lookup_key(b"ab") == (5381 * 33 + 97) * 33 + 98  # 0047c7a0: djb2 over the name's chars
assert tool.lookup_key(b"\xe9") == (5381 * 33 - 23) & 0xFFFFFFFF  # signed chars

code, out, err = run("list", good)
lines = out.splitlines()
assert code == 0 and len(lines) == 5 and lines[-1].startswith("PACK pk entries=4 selected=4 bytes=%d src=%d unreferenced=29"
                                                                 % (sum(map(len, blobs.values())), len(src))), (code, out, err)
assert "obj_empty\t%d\t0" % entries[0][1] in lines, lines

# Extraction: under build/ only, backslash paths become folders, selection by name and glob.
target = B / "out"
code, out, err = run("extract", good, "--output", target)
assert code == 0 and "output=%s" % target in out, (code, out, err)
for name, blob in blobs.items():
    assert (target.joinpath(*name.split("\\"))).read_bytes() == blob, name
assert sorted(p.name for p in target.iterdir()) == ["13th_knight_final.n3fxbundle.fxb", "billboard", "obj_empty", "object"]
code, out, err = run("extract", good, "--output", B / "some", "--glob", "object/*", "--name", "OBJ_EMPTY")
assert code == 0 and "selected=2" in out, (code, out, err)
assert sorted(str(q.relative_to(B / "some")) for q in (B / "some").rglob("*") if q.is_file()) == \
    ["obj_empty", "object/41201item_glow/glow.n3pmesh"]
for argv, needle in ((("--name", "nothing.dxt"), "no entry nothing.dxt"), (("--glob", "*.wav"), "nothing matches *.wav")):
    code, out, err = run("extract", good, "--output", B / "none", *argv)
    assert code == 2 and needle in err and not (B / "none").exists(), (argv, code, err)
away = Path(tempfile.mkdtemp(prefix="pq308-"))
try:
    for outside in (away / "out", ROOT / "build"):
        code, out, err = run("extract", good, "--output", outside)
        assert code == 2 and "is not under" in err and not any(away.iterdir()), (outside, err)
        assert sorted(q.name for q in (ROOT / "build").iterdir() if q.name.endswith(".fxb")) == [], outside
finally:
    shutil.rmtree(away)
# Links already inside the output. Every target is checked before the first
# folder or file is made, so a link on the last entry still leaves the output
# exactly as it was, and nothing outside it changes.
order = [("aaa.dxt", 0, 1), ("mmm.dxt", 1, 1), ("zzz\\b.dxt", 2, 1)]
linky = pack("linky", order, b"ABC")


def tree(top):
    """Every path under top, with its kind and, for a file, its bytes."""
    return sorted((str(q.relative_to(top)), "link" if q.is_symlink() else "dir" if q.is_dir() else q.read_bytes())
                  for q in top.rglob("*"))


away = B / "away"
(away / "dir").mkdir(parents=True)
(away / "file").write_bytes(b"keep")
before = tree(away)
cases = {"folder_link": lambda o: os.symlink(away / "dir", o / "zzz"),
         "file_link": lambda o: ((o / "zzz").mkdir(), os.symlink(away / "file", o / "zzz/b.dxt")),
         "dangling_link": lambda o: ((o / "zzz").mkdir(), os.symlink(away / "dir/new.dxt", o / "zzz/b.dxt")),
         "file_in_way": lambda o: (o / "zzz").write_bytes(b"x"),
         "folder_in_way": lambda o: (o / "mmm.dxt").mkdir()}
for tag, make in cases.items():
    target = B / tag
    target.mkdir()
    make(target)
    start_state = tree(target)
    code, out, err = run("extract", linky, "--output", target)
    assert code == 2 and ("through a link" in err or "is in the way" in err), (tag, code, err)
    assert tree(target) == start_state and tree(away) == before, (tag, tree(target), tree(away))
# A hardlink in the output is replaced, not written through.
target = B / "hardlinked"
target.mkdir()
os.link(away / "file", target / "aaa.dxt")
code, out, err = run("extract", linky, "--output", target)
assert code == 0, (code, err)
assert tree(away) == before and (target / "aaa.dxt").read_bytes() == b"A", tree(away)
assert (target / "aaa.dxt").stat().st_nlink == 1 and (away / "file").stat().st_nlink == 1
assert tree(target) == [("aaa.dxt", b"A"), ("mmm.dxt", b"B"), ("zzz", "dir"), ("zzz/b.dxt", b"C")], tree(target)


def refused(tag, needle, entries, src=b"\0" * 64, **kw):
    """Refused by list and by extract, and nothing written."""
    hdr = pack(tag, entries, src, **kw)
    for argv in (("list", hdr), ("extract", hdr, "--output", B / tag / "out")):
        code, out, err = run(*argv)
        assert code == 2 and "REFUSED" in err and needle in err, (tag, argv, code, err)
        assert not (B / tag / "out").exists(), tag


ok = ("a.dxt", 0, 8)
refused("count0", "0 entries", [])
refused("count_short", "3 entries in a", [ok], count=3)
refused("count_big", "%d entries" % (tool.MAX_ENTRIES + 1), [ok], count=tool.MAX_ENTRIES + 1,
        tail=b"\0" * (13 * tool.MAX_ENTRIES))
refused("trailing", "2 bytes after the last entry", [ok], tail=b"\0\0")
refused("truncated", "ends inside entry 1", [ok, ("b.dxt", 8, 8)], cut=3)
refused("cut_length", "ends inside entry 1", [("a" * 20 + ".dxt", 0, 8), ("b.dxt", 8, 8)], cut=15)
refused("name0", "a 0-byte name", [(b"", 0, 1)], tail=b"\0")
refused("name_long", "a 256-byte name", [(b"a" * 256, 0, 1)])
assert tool.Pack(pack("name_255", [(b"a" * 255, 0, 1)], b"\0")).entries[0][0] == "a" * 255
refused("upper", "not printable lower-case ASCII", [("Item.dxt", 0, 1)])
refused("nonascii", "not printable lower-case ASCII", [(b"\xe9.dxt", 0, 1)])
refused("control", "not printable lower-case ASCII", [(b"a\tb.dxt", 0, 1)])
for tag, name in (("dotdot", "..\\..\\escape.dxt"), ("inner", "object\\..\\..\\escape.dxt"), ("dot", ".\\a.dxt"),
                  ("lead", "\\root.dxt"), ("double", "object\\\\a.dxt"), ("trail", "object\\"),
                  ("dotend", "object.\\a.dxt"), ("spaceend", "object \\a.dxt"), ("spacelead", " a.dxt"),
                  ("dots", "..")):
    refused(tag, "unsafe component", [(name, 0, 1)])
refused("slash", "not printable lower-case ASCII", [("object/a.dxt", 0, 1)])
refused("drive", "not printable lower-case ASCII", [("c:\\a.dxt", 0, 1)])
refused("dup", "a.dxt twice", [ok, ("a.dxt", 8, 8)])
assert tool.lookup_key(b"x\\c0") == tool.lookup_key(b"x\\ar")
refused("key", "x\\c0 and x\\ar share the client's lookup key", [("x\\c0", 0, 1), ("x\\ar", 1, 1)])
refused("filedir", "object is a file and a folder of object\\a.dxt", [("object", 0, 1), ("object\\a.dxt", 1, 1)])
refused("past", "runs to byte 65 of a 64-byte .src", [("a.dxt", 60, 5)])
refused("wrap", "runs to byte %d" % (0xFFFFFFFF + 2), [("a.dxt", 0xFFFFFFFF, 2)])
refused("overlap", "a.dxt and b.dxt overlap", [("b.dxt", 7, 4), ok])
refused("inside", "a.dxt and b.dxt overlap", [ok, ("b.dxt", 3, 2)])
assert len(tool.Pack(pack("touch", [ok, ("b.dxt", 8, 8), ("c.dxt", 16, 0), ("d.dxt", 16, 0)], b"\0" * 16)).entries) == 4
saved = tool.MAX_HEADER, tool.MAX_SOURCE
tool.MAX_HEADER = 20
refused("hdr_big", "over the bound", [ok, ("b.dxt", 8, 8)])
tool.MAX_HEADER, tool.MAX_SOURCE = saved[0], 63
refused("src_big", "over the bound", [ok])
tool.MAX_HEADER, tool.MAX_SOURCE = saved
code, _, err = run("list", B / "absent.hdr")
assert code == 2 and "REFUSED" in err, err
print("PASS 2145 pack reader: synthetic packs written as the 2145 launcher writes them list, read by name "
      "(lower-cased and / taken for \\ as the client looks up) and extract under build/ with fx backslash paths as folders; "
      "bad counts, name lengths and forms, traversal, duplicates, a shared lookup key, file-and-folder names, "
      "ranges past the .src, overlapping ranges, oversized headers or .src, an output outside build/ and a "
      "symlink or a clashing file or folder inside it on any selected entry are refused before any write, and "
      "an existing hardlink is replaced, not written through")

client = ROOT / "build/ko-reference/installer-2145/client"
SHIPPED = {"Item/item.hdr": 10754, "UI/ui.hdr": 5788, "fx/fx.hdr": 8458, "Object/object.hdr": 9858}
if not all((client / rel).exists() for rel in SHIPPED):
    print("SKIP 2145 packs: no extraction in build/ko-reference/installer-2145")
else:
    packs = {rel: tool.Pack(client / rel) for rel in SHIPPED}
    assert {rel: len(p.entries) for rel, p in packs.items()} == SHIPPED
    item = packs["Item/item.hdr"]
    for name in ("11_1042_50_0.n3cpart", "11_1042_50_0.n3cplug", "11_1042_50_0.n3chrplug",
                 "bow_boss_uer_h01_poly.n3cskins", "bow_boss_uer_h01_poly.dxt"):
        assert item.find(name), name
    assert item.read("11_1042_50_0.n3cpart")[:8] == b"\x04\0\0\0Poly"  # a plain part: its name, "Poly"
    assert len(item.select(patterns=["2_0800_*"])) == 60
    assert sum(1 for name, _, _ in packs["fx/fx.hdr"].entries if "\\" in name) == 7328
    print("PASS 2145 packs: the player's Item, UI, fx and Object packs read whole (10,754 / 5,788 / 8,458 / "
          "9,858 entries); the Azagai's part, plugs, skin and texture and the 60 Krowaz armour files are in the "
          "Item pack")
