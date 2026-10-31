#!/usr/bin/env python3
"""Unpack a user-supplied KnightOnLineSetup_1298.exe without running it.

The installer is a Microsoft Cabinet self-extractor (MSZIP) around an
InstallShield 6 cabinet set (data1.hdr, data1.cab, data2.cab). Both layers are
read here with the standard library; nothing from the installer is executed.
Every installed file is checked against the MD5 stored in data1.hdr, and a
manifest of paths, sizes and SHA-256 hashes is written next to the output.

The 1097, 1264 and 1453 installers (secondary references, PQ-214) are the same
format and are pinned too; each unpacks by default into its own
build/ko-reference/installer-<version>/. The 2145 installer is Inno Setup and is
refused by its hash; tools/ko-reference/unpack_inno.py reads it (PQ-227).

Research tool only: the future player-side import owns its own extractor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

# archive.org item knightonline2003, file KnightOnLineSetup_1298.exe
# (349,738,649 bytes): the source of truth (D-118).
PINNED_SHA256 = '54d1c65853bb09b3512ff8778a78697177a02f6c5a0f9fd583751fbcfbc50fe4'
DEFAULT_OUTPUT = 'build/ko-reference/installer'
# sha256 -> client version. The secondary installers are the player-supplied
# ones inventoried in PQ-214. Each unpacks by default into
# DEFAULT_OUTPUT-<version>; their results are labelled with their version and
# never override the 1298 set (BINARY-POLICY).
PINNED = {
    PINNED_SHA256: '1298',
    # KnightOnline_1097.exe, 201,059,508 bytes
    'd7571e183663be3d063af491d68d7db3dc52219f58471c9595d0b745c0b8a93b': '1097',
    # knightonlinesetup_1264.exe, 297,557,888 bytes
    'eb4e1a3508c33f381fbeeedccf95f09a746a7d6ead3ccc97616ab6b2f3ccafb5': '1264',
    # KnightOnlineSetup1453.exe, 467,178,433 bytes
    'c345df520c4d2096be362f56f82c63f07ed94876290d29a39ecc4d3faf21054e': '1453',
}
# Known installers this tool cannot read, refused even with --allow-unpinned.
REFUSED = {
    # KnightOnlineSetup_v2145.exe, 774,488,528 bytes
    '7da88158e1ddb9c689c22d8e3cb1e8b2655d973ac21596d798104c81c30a1edf':
        'the KO 2145 installer is Inno Setup 5.2.3, not an InstallShield 6 set; '
        'this unpacker cannot read it (use tools/ko-reference/unpack_inno.py, PQ-227)',
}
# The cabinet follows the stub's PE sections within this distance.
MSCF_SEARCH_LIMIT = 1 << 20


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def overlay_start(blob):
    pe = struct.unpack_from('<I', blob, 0x3c)[0]
    count, opt = struct.unpack_from('<H', blob, pe + 6)[0], struct.unpack_from('<H', blob, pe + 20)[0]
    ends = [sum(struct.unpack_from('<II', blob, pe + 24 + opt + 40 * i + 16)) for i in range(count)]
    return max(ends)


def unpack_mscab(blob, base):
    """Return {name: bytes} for a single-cabinet, uncompressed or MSZIP CAB at base."""
    sig, _, _, _, coff_files, _, _, _, nfold, nfiles, flags, _, _ = struct.unpack_from(
        '<4sIIIIIBBHHHHH', blob, base)
    if sig != b'MSCF' or flags:
        raise SystemExit(f'unsupported cabinet at {base:#x} (flags {flags})')
    folders = [struct.unpack_from('<IHH', blob, base + 36 + 8 * i) for i in range(nfold)]
    data = []
    for start, ndata, comp in folders:
        if comp & 0xf not in (0, 1):
            raise SystemExit(f'unsupported CAB compression {comp:#x}')
        p, buf = base + start, bytearray()
        for _ in range(ndata):
            _, cbd, cbu = struct.unpack_from('<IHH', blob, p)
            blk = blob[p + 8:p + 8 + cbd]
            p += 8 + cbd
            if comp & 0xf == 0:
                buf += blk
                continue
            if blk[:2] != b'CK':
                raise SystemExit('bad MSZIP block')
            d = zlib.decompressobj(-15, zdict=bytes(buf[-32768:]))
            out = d.decompress(blk[2:]) + d.flush()
            if len(out) != cbu:
                raise SystemExit('MSZIP size mismatch')
            buf += out
        data.append(bytes(buf))
    files, p = {}, base + coff_files
    for _ in range(nfiles):
        size, off, ifold = struct.unpack_from('<IIH', blob, p)
        end = blob.index(b'\0', p + 16)
        name = blob[p + 16:end].decode('latin-1').lstrip('\\').replace('\\', '/')
        files[name] = data[ifold][off:off + size]
        p = end + 1
    return files


def unpack_is6(disk):
    """Yield (relative path, bytes, md5 ok) for every valid file in an IS6 cabinet set."""
    hdr = disk['Disk1/data1.hdr']
    _, version, _, cdo, _ = struct.unpack_from('<IIIII', hdr, 0)
    if version >> 12 != 0x1006:
        raise SystemExit(f'unsupported InstallShield version {version:#x}')
    u32 = lambda o: struct.unpack_from('<I', hdr, o)[0]
    cstr = lambda o: hdr[o:hdr.index(b'\0', o)].decode('latin-1')
    ft = cdo + u32(cdo + 0x0c)
    dir_count, file_count, ft2 = u32(cdo + 0x1c), u32(cdo + 0x28), u32(cdo + 0x2c)
    dirs = [cstr(ft + u32(ft + 4 * i)) for i in range(dir_count)]
    volumes = {}

    def volume(n):
        if n not in volumes:
            blob = disk[f'Disk1/data{n}.cab']
            volumes[n] = (blob, struct.unpack_from('<IIIIQQQQQQ', blob, 0x14))
        return volumes[n]

    for i in range(file_count):
        o = ft + ft2 + i * 0x57
        flags, expanded, compressed, offset = struct.unpack_from('<HQQQ', hdr, o)
        name_offset = u32(o + 0x3a)
        if flags & 8 or not name_offset:
            continue
        if flags & 2:
            raise SystemExit('obfuscated InstallShield files are not supported')
        md5 = hdr[o + 0x1a:o + 0x2a]
        directory = struct.unpack_from('<H', hdr, o + 0x3e)[0]
        vol = struct.unpack_from('<H', hdr, o + 0x55)[0]
        rel = (dirs[directory] + '\\' + cstr(ft + name_offset)).lstrip('\\').replace('\\', '/')
        blob, vh = volume(vol)
        if flags & 1 and i == vh[3] and vh[7]:
            # Split file: the tail of this volume, then the head of the next ones.
            stream, need = blob[vh[7]:vh[7] + vh[9]], compressed - vh[9]
            while need > 0:
                vol += 1
                blob, vh = volume(vol)
                take = vh[6] if i == vh[2] else need
                stream += blob[vh[4]:vh[4] + take]
                need -= take
        else:
            stream = blob[offset:offset + compressed]
        if flags & 4:
            out, p = bytearray(), 0
            while p < len(stream):
                n = struct.unpack_from('<H', stream, p)[0]
                d = zlib.decompressobj(-15)
                out += d.decompress(stream[p + 2:p + 2 + n]) + d.flush()
                p += 2 + n
            stream = bytes(out)
        yield rel, stream, len(stream) == expanded and hashlib.md5(stream).digest() == md5


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('installer', type=Path)
    ap.add_argument('--output', type=Path,
                    help=f'output directory (default {DEFAULT_OUTPUT}, or {DEFAULT_OUTPUT}-<version> '
                         'for a pinned secondary installer)')
    ap.add_argument('--allow-unpinned', action='store_true',
                    help='unpack an installer whose hash is not pinned')
    args = ap.parse_args(argv)

    digest = sha256_file(args.installer)
    if digest in REFUSED:
        raise SystemExit(f'{args.installer}: sha256 {digest}: {REFUSED[digest]}')
    if digest == PINNED_SHA256 or digest not in PINNED and args.allow_unpinned:
        output = DEFAULT_OUTPUT
    elif digest in PINNED:
        output = f'{DEFAULT_OUTPUT}-{PINNED[digest]}'
    else:
        secondary = ', '.join(sorted(v for d, v in PINNED.items() if d != PINNED_SHA256))
        raise SystemExit(f'{args.installer}: sha256 {digest} is not the pinned 1298 installer '
                         f'or a pinned secondary one ({secondary})')
    args.output = args.output or Path(output)
    blob = args.installer.read_bytes()
    start = overlay_start(blob)
    base = blob.find(b'MSCF', start, start + MSCF_SEARCH_LIMIT)
    if base < 0:
        raise SystemExit('no Microsoft Cabinet found in the self-extractor')
    disk = unpack_mscab(blob, base)
    del blob

    root = args.output / 'client'
    manifest, failed = [], []
    for rel, data, ok in unpack_is6(disk):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest.append({'path': rel, 'size': len(data),
                         'sha256': hashlib.sha256(data).hexdigest(), 'md5_ok': ok})
        if not ok:
            failed.append(rel)
    report = {'installer': str(args.installer), 'sha256': digest, 'size': args.installer.stat().st_size,
              'cab_offset': base, 'files': len(manifest), 'md5_failures': failed,
              'manifest': sorted(manifest, key=lambda m: m['path'].lower())}
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=1) + '\n')
    print(f'{len(manifest)} files, {len(failed)} MD5 failures -> {root}')
    for rel in failed:
        print('  md5 mismatch:', rel)
    # Only the installer's own support files are known to carry unusable MD5s.
    support = {'setup.exe', 'setup.ini', 'setup.inx'}
    return 1 if any(Path(f).name.lower() not in support for f in failed) else 0


if __name__ == '__main__':
    sys.exit(main())
