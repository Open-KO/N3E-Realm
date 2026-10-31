"""PQ-221: the research unpacker's installer pins (tools/ko-reference/unpack_installer.py).

A synthetic self-extractor (a PE stub, an MSZIP Microsoft Cabinet, an
InstallShield 6 data1.hdr/data1.cab set; original bytes only) is unpacked
through the tool's own main(). Its hash is entered in the tool's tables for
each case, so the real dispatch runs: a pinned secondary installer unpacks
into DEFAULT_OUTPUT-<version>, the 1298 pin keeps DEFAULT_OUTPUT, a refused
hash writes nothing even with --allow-unpinned, an unknown hash is refused
without the flag and unpacks into DEFAULT_OUTPUT with it, --output wins, and a
game file that fails its MD5 still exits 1. With the player's own 2145
installer in ref/ko-bin/installer/ (never committed; SKIP without it) the real
refusal is also run. `tests/ko_terrain.py` (so `make test`) runs this file; it
also runs alone.
"""
import contextlib, hashlib, importlib.util, io, json, os, shutil, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("unpack_installer", ROOT / "tools/ko-reference/unpack_installer.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

B = ROOT / "build/pq221-test"
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)


def mscab(files):
    """A one-folder MSZIP cabinet holding {name: bytes}."""
    data = b"".join(files.values())
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    block = b"CK" + comp.compress(data) + comp.flush()
    entries, offset = b"", 0
    for name, blob in files.items():
        entries += struct.pack("<IIHHHH", len(blob), offset, 0, 0, 0, 0) + name.encode() + b"\0"
        offset += len(blob)
    coff_files = 36 + 8
    start = coff_files + len(entries)
    total = start + 8 + len(block)
    head = struct.pack("<4sIIIIIBBHHHHH", b"MSCF", 0, total, 0, coff_files, 0, 3, 1, 1, len(files), 0, 0, 0)
    return head + struct.pack("<IHH", start, 1, 1) + entries + struct.pack("<IHH", 0, len(block), len(data)) + block


def is6(files, dirs):
    """data1.hdr and data1.cab for [(dir index, name, bytes, flags, md5 or None)]."""
    cab = bytearray(0x54)  # volume header read at 0x14; zero: no split file
    table_strings = dirs + [name for _, name, _, _, _ in files]
    # The file table: dir offsets, then strings, then 0x57-byte descriptors.
    ft = bytearray(4 * len(dirs))
    offsets = {}
    for text in table_strings:
        if text not in offsets:
            offsets[text] = len(ft)
            ft += text.encode() + b"\0"
    for i, d in enumerate(dirs):
        struct.pack_into("<I", ft, 4 * i, offsets[d])
    ft2 = len(ft)
    for d, name, blob, flags, md5 in files:
        stored = blob
        if flags & 4:
            stored = b""
            for part in (blob[: len(blob) // 2], blob[len(blob) // 2:]):
                comp = zlib.compressobj(9, zlib.DEFLATED, -15)
                chunk = comp.compress(part) + comp.flush()
                stored += struct.pack("<H", len(chunk)) + chunk
        desc = bytearray(0x57)
        struct.pack_into("<HQQQ", desc, 0, flags, len(blob), len(stored), len(cab))
        desc[0x1a:0x2a] = md5 if md5 is not None else hashlib.md5(blob).digest()
        struct.pack_into("<I", desc, 0x3a, offsets[name])
        struct.pack_into("<H", desc, 0x3e, d)
        struct.pack_into("<H", desc, 0x55, 1)
        ft += desc
        cab += stored
    cdo, ft_rel = 0x20, 0x40
    hdr = bytearray(cdo + ft_rel)
    struct.pack_into("<IIIII", hdr, 0, 0x28635349, 0x1006000, 0, cdo, 0)
    struct.pack_into("<I", hdr, cdo + 0x0c, ft_rel)
    struct.pack_into("<I", hdr, cdo + 0x1c, len(dirs))
    struct.pack_into("<I", hdr, cdo + 0x28, len(files))
    struct.pack_into("<I", hdr, cdo + 0x2c, ft2)
    return bytes(hdr + ft), bytes(cab)


def installer(tag, bad_game_md5=False):
    """A synthetic self-extractor; tag makes each variant's hash distinct."""
    zones = b"zone table " * 300 + tag.encode()
    readme = b"original synthetic readme\n"
    hdr, cab = is6([
        (0, "Setup.ini", b"[Startup]\n", 0, b"\0" * 16),  # installer support file, MD5 never matches
        (1, "zones.tbl", zones, 4, None),
        (0, "skipped.bin", b"", 8, None),  # invalid entry, skipped
        (0, "readme.txt", readme, 0, b"\1" * 16 if bad_game_md5 else None),
    ], ["", "Data"])
    stub = bytearray(0x400)
    stub[0:2] = b"MZ"
    struct.pack_into("<I", stub, 0x3c, 0x40)
    stub[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<H", stub, 0x46, 1)  # one section
    struct.pack_into("<H", stub, 0x54, 0)  # no optional header
    struct.pack_into("<II", stub, 0x58 + 16, 0x200, 0x200)  # raw size, raw pointer: overlay at 0x400
    blob = bytes(stub) + b"\0" * 7 + mscab({"Disk1\\data1.hdr": hdr, "Disk1\\data1.cab": cab})
    path = B / f"{tag}.exe"
    path.write_bytes(blob)
    return path, hashlib.sha256(blob).hexdigest(), {"Setup.ini": b"[Startup]\n", "Data/zones.tbl": zones,
                                                    "readme.txt": readme}


def run(*argv):
    """main() run from B, so default outputs land under B/build/ko-reference/."""
    out = io.StringIO()
    cwd = os.getcwd()
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


def unpacked(out, installer_path, digest, expected, failures):
    report = json.loads((out / "manifest.json").read_text())
    assert report["sha256"] == digest and report["installer"] == str(installer_path), report
    assert report["files"] == 3 and report["md5_failures"] == failures, report
    assert [m["path"] for m in report["manifest"]] == sorted(expected, key=str.lower), report["manifest"]
    for rel, blob in expected.items():
        assert (out / "client" / rel).read_bytes() == blob, rel
        entry = next(m for m in report["manifest"] if m["path"] == rel)
        assert entry["sha256"] == hashlib.sha256(blob).hexdigest() and entry["size"] == len(blob), entry


ref = B / "build/ko-reference"
default = ref / "installer"
pinned_tables = dict(tool.PINNED), dict(tool.REFUSED), tool.PINNED_SHA256

# A pinned secondary installer: its own directory, no flag needed, the 1298 tree untouched.
path, digest, files = installer("secondary")
tool.PINNED[digest] = "9999"
code, text = run(path)
assert code == 0, (code, text)
unpacked(ref / "installer-9999", path, digest, files, ["Setup.ini"])
assert not default.exists(), sorted(ref.iterdir())
shutil.rmtree(ref / "installer-9999")
code, text = run(path, "--allow-unpinned")  # the flag does not move a pinned installer
assert code == 0 and (ref / "installer-9999/manifest.json").exists() and not default.exists(), (code, text)
code, text = run(path, "--output", B / "chosen")
assert code == 0 and (B / "chosen/manifest.json").exists(), (code, text)

# The 1298 pin keeps the default directory.
path, digest, files = installer("primary")
tool.PINNED[digest] = "1298"
tool.PINNED_SHA256 = digest
code, text = run(path)
assert code == 0, (code, text)
unpacked(default, path, digest, files, ["Setup.ini"])
assert not (ref / "installer-1298").exists()
tool.PINNED_SHA256 = pinned_tables[2]
del tool.PINNED[digest]
shutil.rmtree(default)

# A refused hash writes nothing, with or without --allow-unpinned.
path, digest, _ = installer("refused")
tool.REFUSED[digest] = "a synthetic refusal reason"
for argv in ((path,), (path, "--allow-unpinned")):
    code, text = run(*argv)
    assert code == f"{path}: sha256 {digest}: a synthetic refusal reason", code
assert sorted(p.name for p in ref.iterdir()) == ["installer-9999"], sorted(ref.iterdir())

# An unknown hash: refused without the flag, the 1298 default directory with it.
path, digest, files = installer("unknown")
code, _ = run(path)
assert code == (f"{path}: sha256 {digest} is not the pinned 1298 installer or a pinned secondary one "
                "(1097, 1264, 1453, 9999)"), code
assert not default.exists()
code, text = run(path, "--allow-unpinned")
assert code == 0, (code, text)
unpacked(default, path, digest, files, ["Setup.ini"])

# A game file failing its MD5 still fails the run (only setup.exe/.ini/.inx are tolerated).
path, digest, files = installer("corrupt", bad_game_md5=True)
code, text = run(path, "--allow-unpinned", "--output", B / "corrupt")
assert code == 1 and "md5 mismatch: readme.txt" in text, (code, text)

tool.PINNED.clear(); tool.PINNED.update(pinned_tables[0])
tool.REFUSED.clear(); tool.REFUSED.update(pinned_tables[1])
print("PASS installer pins: a pinned secondary installer unpacks into installer-<version> without "
      "--allow-unpinned (and there with it), the 1298 pin keeps installer/, --output wins, a refused hash writes nothing "
      "even with --allow-unpinned, an unknown hash is refused (unpacked into installer/ only with the flag), "
      "and a game-file MD5 failure exits 1 (synthetic InstallShield 6 self-extractor)")

real = ROOT / "ref/ko-bin/installer/KnightOnlineSetup_v2145.exe"
if real.exists():
    code, _ = run(real, "--allow-unpinned", "--output", B / "real2145")
    assert isinstance(code, str) and "Inno Setup 5.2.3" in code and "sha256 7da88158" in code, code
    assert not (B / "real2145").exists()
    print("PASS installer pins: the player's 2145 installer is refused by its hash (Inno Setup), nothing written")
else:
    print("SKIP installer pins: no ref/ko-bin/installer/KnightOnlineSetup_v2145.exe")
shutil.rmtree(B)
