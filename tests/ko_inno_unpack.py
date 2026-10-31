"""PQ-227: the research Inno Setup 5.2.3 reader (tools/ko-reference/unpack_inno.py).

Synthetic installers (original bytes only: a stub with the loader table, an
LZMA file-data chunk, a setup-0 header of two CRC-checked LZMA blocks) are read
through the tool's own main(). A pinned one unpacks into installer-<version>
with every file's MD5 checked, an x86 file stored through the call-instruction
filter (spanning two 64 KiB buffers) comes back byte for byte, directories that
differ only in case merge as Windows merges them, --list writes nothing, an
unknown hash needs --allow-unpinned, and a destination with `..`, one outside
{app}, a corrupt header chunk, another Inno version and file data outside the
installer are refused, with or without --list, and a wrong MD5 fails the run. With the
player's own 2145 installer in ref/ko-bin/installer/ (never committed; SKIP
without it) its entry table is listed and checked. `tests/ko_terrain.py` (so
`make test`) runs this file; it also runs alone.
"""
import contextlib, hashlib, importlib.util, io, json, lzma, os, shutil, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("unpack_inno", ROOT / "tools/ko-reference/unpack_inno.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

B = ROOT / "build/pq227-test"
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)
LC, LP, PB, DICT = 3, 0, 2, 1 << 16


def lzma_raw(data):
    """Inno's LZMA1 form: five property bytes, then the raw stream."""
    raw = lzma.compress(data, format=lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_LZMA1, "lc": LC, "lp": LP, "pb": PB, "dict_size": DICT}])
    return bytes([(PB * 5 + LP) * 9 + LC]) + struct.pack("<I", DICT) + raw


def block(data, corrupt=False):
    """A setup-0 block: CRC of (stored size, compressed flag), then CRC-prefixed 4096-byte chunks."""
    packed, chunks = lzma_raw(data), b""
    for p in range(0, len(packed), 4096):
        piece = packed[p:p + 4096]
        chunks += struct.pack("<I", zlib.crc32(piece) ^ (1 if corrupt else 0)) + piece
    head = struct.pack("<IB", len(chunks), 1)
    return struct.pack("<I", zlib.crc32(head)) + head + chunks


def call_encode(data):
    """The installer side of the 5.2 call filter: relative to absolute, per 64 KiB buffer."""
    out = bytearray(data)
    for base in range(0, len(out), 0x10000):
        buf = out[base:base + 0x10000]
        i = 0
        while i < len(buf) - 4:
            if buf[i] in (0xE8, 0xE9):
                i += 1
                if buf[i + 3] in (0x00, 0xFF):
                    addr = (base + i + 4) & 0xFFFFFF
                    rel = (buf[i] | buf[i + 1] << 8 | buf[i + 2] << 16) + addr
                    buf[i:i + 3] = (rel & 0xFFFFFF).to_bytes(3, "little")
                i += 4
            else:
                i += 1
        out[base:base + 0x10000] = buf
    return bytes(out)


def s(text):
    raw = text.encode() if isinstance(text, str) else text
    return struct.pack("<I", len(raw)) + raw


def installer(tag, files, version=tool.SETUP_ID, corrupt_header=False, bad_md5=None, short_data=False):
    """files: [(destination, bytes, call_filtered)]; returns (path, sha256)."""
    stream, layout = b"", []
    file_entries = s("") * 9 + struct.pack("<20sIIQhIB", b"\0" * 20, 0xFFFFFFFF, 0, 0, -1, 0x800, 1)  # uninstaller
    for n, (dest, blob, filtered) in enumerate(files):
        md5 = hashlib.md5(b"x" if dest == bad_md5 else blob).digest()
        layout.append((len(stream), len(blob), md5, 0x80 | (0x10 if filtered else 0)))
        file_entries += s("") + s(dest) + s("") * 7 + struct.pack("<20sIIQhIB", b"\0" * 20, n, 0, 0, -1, 0x2020000, 0)
        stream += call_encode(blob) if filtered else blob
    chunk = lzma_raw(stream)
    chunk_size = len(chunk) + (1 << 20 if short_data else 0)
    # Data entry: slices, chunk offset, file offset and size, chunk size, MD5, time, version, flags.
    data_entries = b"".join(struct.pack("<IIIQQQ16sqIIH", 0, 0, 0, off, size, chunk_size, md5, 0, 0, 0, flags)
                            for off, size, md5, flags in layout)
    entries = bytearray()
    strings = [tag, "2145", "{{id}}"] + [""] * (tool.HEADER_STRINGS - 3)
    entries += b"".join(s(x) for x in strings) + b"\0" * 32
    counts = dict.fromkeys(tool.COUNTS, 0)
    counts.update(languages=1, messages=1, directories=1, files=len(files) + 1, data=len(files))
    entries += struct.pack("<16I", *(counts[k] for k in tool.COUNTS))
    tail = bytearray(tool.HEADER_TAIL)
    tail[tool.COMPRESSION_OFFSET] = 3
    struct.pack_into("<I", tail, tool.SLICES_OFFSET, 1)
    entries += tail
    entries += s("english") + s("E\0n\0") + s("") * 4 + s("Inno Setup Messages") + s("") * 3 + b"\0" * 25
    entries += s("NameAndVersion") + s("%1 %2") + struct.pack("<i", -1)
    entries += s("{app}\\Data\\") + s("") * 6 + b"\0" * 27
    entries += file_entries
    setup1 = 0x400
    setup0 = setup1 + 4 + len(chunk)
    head = version.ljust(64, b"\0") + block(bytes(entries), corrupt_header) + block(data_entries)
    total = setup0 + len(head)
    table = tool.LOADER_ID + struct.pack("<7I", 1, total, 0, 0, 0, setup0, setup1)
    table += struct.pack("<I", zlib.crc32(table))
    stub = bytearray(setup1)
    stub[0:2] = b"MZ"
    stub[0x100:0x100 + len(table)] = table
    blob = bytes(stub) + b"zlb\x1a" + chunk + head
    path = B / f"{tag}.exe"
    path.write_bytes(blob)
    return path, hashlib.sha256(blob).hexdigest()


def run(*argv):
    """main() run from B, so default outputs land under B/build/ko-reference/."""
    out, cwd = io.StringIO(), os.getcwd()
    os.chdir(B)
    try:
        with contextlib.redirect_stdout(out):
            try:
                code = tool.main([str(a) for a in argv])
            except SystemExit as stop:
                code = stop.code
    finally:
        os.chdir(cwd)
    return code, out.getvalue()


# An x86 image over two extraction buffers, with CALL/JMP opcodes before and across the 64 KiB edge.
# Opcode-free filler around the edge keeps the scan aligned: 0x10000 - 3 is a CALL whose address
# crosses into the second buffer, so it stays untouched; 0x10000 + 40 is in the second buffer.
exe = bytearray(os.urandom(0x10000 + 3000))
exe[0x10000 - 40:0x10000 + 60] = b"\x90" * 100
for at, rel in ((10, 4321), (500, -1234), (0x10000 - 20, -77), (0x10000 - 3, -1234), (0x10000 + 40, 999)):
    exe[at:at + 5] = b"\xe8" + struct.pack("<i", rel)
exe = bytes(exe)
FILES = [("{code:GetDataDir}\\KnightOnLine.exe", exe, True),
         ("{code:GetDataDir}\\Data\\Zones.tbl", b"zone rows " * 50, False),
         ("{app}\\data\\Texts.tbl", b"texts", False),
         ("{code:GetDataDir}\\Zones\\empty.gev", b"", False)]
assert call_encode(exe) != exe
expected = {"KnightOnLine.exe": exe, "Data/Zones.tbl": b"zone rows " * 50, "Data/Texts.tbl": b"texts",
            "Zones/empty.gev": b""}
ref = B / "build/ko-reference"

# A pinned installer: installer-<version>, every MD5 checked, the call filter undone.
path, digest = installer("pinned", FILES)
tool.PINNED[digest] = "9999"
code, text = run(path, "--list")
assert code == 0 and "4 files" in text and not ref.exists(), (code, text)
code, text = run(path)
assert code == 0 and "0 MD5 failures" in text, (code, text)
out = ref / "installer-9999"
report = json.loads((out / "manifest.json").read_text())
assert report["sha256"] == digest and report["files"] == 4 and report["md5_failures"] == [], report
assert report["app"]["counts"]["files"] == 5 and report["app"]["counts"]["data"] == 4, report["app"]
assert sorted(m["path"] for m in report["manifest"]) == sorted(expected), report["manifest"]
for rel, blob in expected.items():
    assert (out / "client" / rel).read_bytes() == blob, rel
assert sorted(p.name for p in (out / "client").iterdir()) == ["Data", "KnightOnLine.exe", "Zones"]
code, _ = run(path, "--output", B / "chosen")
assert code == 0 and (B / "chosen/client/KnightOnLine.exe").read_bytes() == exe
del tool.PINNED[digest]

# An unknown hash: refused without the flag, installer-inno with it.
path, digest = installer("unknown", FILES)
code, _ = run(path)
assert isinstance(code, str) and "is not a pinned Inno Setup installer" in code and \
    not (ref / "installer-inno").exists(), code
code, _ = run(path, "--allow-unpinned")
assert code == 0 and (ref / "installer-inno/client/Data/Zones.tbl").exists(), code


def refused(label, needle, **kw):
    files = kw.pop("files", FILES)
    path, _ = installer(label, files, **kw)
    target = B / label
    code, _ = run(path, "--allow-unpinned", "--output", target)
    assert isinstance(code, str) and needle in code, (label, code)
    assert not target.exists(), label  # validated before the first write
    code, _ = run(path, "--allow-unpinned", "--list")  # --list runs every check too
    assert isinstance(code, str) and needle in code, (label, "--list", code)


refused("traversal", "unsafe destination", files=FILES + [("{app}\\..\\evil.dll", b"x", False)])
refused("outside", "destination outside {app}", files=FILES + [("{sys}\\evil.dll", b"x", False)])
refused("crc", "setup-0 chunk CRC mismatch", corrupt_header=True)
refused("version", "setup data is not Inno Setup Setup Data (5.2.3)", version=b"Inno Setup Setup Data (5.5.0)")
refused("short", "chunk outside the file data", short_data=True)

# A wrong stored MD5 is reported and fails the run.
path, _ = installer("md5", FILES, bad_md5="{app}\\data\\Texts.tbl")
code, text = run(path, "--allow-unpinned", "--output", B / "md5")
assert code == 1 and "md5 mismatch: Data/Texts.tbl" in text, (code, text)
print("PASS inno reader: a pinned Inno Setup 5.2.3 installer unpacks into installer-<version> with every MD5 "
      "checked and the x86 call filter undone across two 64 KiB buffers, case-only directory variants merge, "
      "--list writes nothing, an unknown hash needs --allow-unpinned, and traversal, a destination outside {app}, "
      "a corrupt header chunk, another Inno version and file data outside the installer are refused before any "
      "write, and under --list too; a wrong MD5 exits 1 (synthetic installers)")

real = ROOT / "ref/ko-bin/installer/KnightOnlineSetup_v2145.exe"
if real.exists():
    code, text = run(real, "--list")
    assert code == 0 and text.rstrip().endswith("4714 files, 2400556938 bytes"), (code, text[-200:])
    assert "4677016 KnightOnLine.exe" in text and "551741653 Item/item.src" in text
    print("PASS inno reader: the player's 2145 installer lists 4,714 files (2,400,556,938 bytes), nothing written")
else:
    print("SKIP inno reader: no ref/ko-bin/installer/KnightOnlineSetup_v2145.exe")
shutil.rmtree(B, ignore_errors=True)
