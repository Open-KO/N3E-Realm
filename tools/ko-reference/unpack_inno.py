#!/usr/bin/env python3
"""Unpack the player-supplied KnightOnlineSetup_v2145.exe without running it.

The KO 2145 installer (PQ-214, a labelled secondary reference that never
overrides the 1298 set) is an Inno Setup 5.2.3 installer. This reader handles
exactly that layout and refuses anything else: the loader table (`rDlPtS`,
version 1) gives the setup header (setup-0) and the file data (setup-1); the
header is two CRC-checked LZMA blocks (the setup entries, then the data
entries); the file data is LZMA chunks behind a `zlb\\x1a` magic. Files the
installer stored with its x86 call-instruction filter are decoded, and every
file is checked against the MD5 its data entry stores. Only the Python standard
library is used; nothing from the installer is executed.

Bounded: the header blocks, entry counts, chunk sizes and total output are
capped, every destination must sit under {app} or {code:GetDataDir} with no
`..`, drive or empty component, and the whole entry table is validated before
the first file is written. Output: <output>/client/ and <output>/manifest.json,
as tools/ko-reference/unpack_installer.py writes for the InstallShield sets.

Research tool only (PQ-227).
"""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re
import struct
import sys
import zlib

# KnightOnlineSetup_v2145.exe, 774,488,528 bytes (PQ-214).
PINNED = {'7da88158e1ddb9c689c22d8e3cb1e8b2655d973ac21596d798104c81c30a1edf': '2145'}
DEFAULT_OUTPUT = 'build/ko-reference/installer'
SETUP_ID = b'Inno Setup Setup Data (5.2.3)'
LOADER_ID = b'rDlPtS\xcd\xe6\xd7\x7b\x0b\x2a'
LOADER_SEARCH = 1 << 20          # the loader table sits in the stub's resources
MAX_HEADER_BLOCK = 64 << 20      # decompressed bytes per setup-0 block
MAX_ENTRIES = 200_000            # per entry kind
MAX_OUTPUT = 16 << 30            # total installed bytes
CHUNK_MAGIC = b'zlb\x1a'
BLOCK = 0x10000                  # Inno's extraction buffer; the call filter works per buffer
# Data entry flags (Inno 5.2.3 TSetupFileLocationEntry options, in declaration order).
CALL_OPTIMIZED, CHUNK_ENCRYPTED, CHUNK_COMPRESSED = 1 << 4, 1 << 6, 1 << 7
DATA_ENTRY = struct.Struct('<IIIQQQ16sqIIH')  # 70 bytes
FILE_TAIL = struct.Struct('<20sIIQhIB')       # after the nine strings
ROOTS = ('{app}\\', '{code:getdatadir}\\')
# Header fields after the strings: lead bytes, then 16 entry counts.
COUNTS = ('languages', 'messages', 'permissions', 'types', 'components', 'tasks', 'directories',
          'files', 'data', 'icons', 'ini', 'registry', 'delete', 'uninstall_delete', 'run', 'uninstall_run')
HEADER_STRINGS = 29
# Version range (20), colours (12), password MD5 (16), salt (8), extra disk space (8),
# slices per disk (4), six byte enums, two architecture sets, signed uninstaller (8), options (6).
HEADER_TAIL = 90
COMPRESSION_OFFSET = 20 + 12 + 16 + 8 + 8 + 4 + 5   # the compression enum; 3 = LZMA
SLICES_OFFSET = 20 + 12 + 16 + 8 + 8


class Refused(SystemExit):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class Cursor:
    def __init__(self, data, what):
        self.data, self.p, self.what = data, 0, what

    def take(self, n):
        if n < 0 or self.p + n > len(self.data):
            raise Refused(f'{self.what}: truncated at {self.p} (wanted {n} bytes)')
        v = self.data[self.p:self.p + n]
        self.p += n
        return v

    def string(self):
        return self.take(struct.unpack('<I', self.take(4))[0])

    def unpack(self, st):
        return st.unpack(self.take(st.size))


def lzma1(props):
    """A raw LZMA1 decoder for Inno's five-byte property header."""
    if len(props) != 5 or props[0] >= 9 * 5 * 5:
        raise Refused('bad LZMA properties')
    d = props[0]
    dict_size = struct.unpack_from('<I', props, 1)[0]
    if dict_size > 1 << 28:
        raise Refused(f'LZMA dictionary {dict_size} over the limit')
    return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{
        'id': lzma.FILTER_LZMA1, 'lc': d % 9, 'lp': d // 9 % 5, 'pb': d // 45, 'dict_size': dict_size}])


def header_block(f):
    """One setup-0 block: CRC-checked header, 4096-byte CRC-checked chunks, LZMA."""
    head = f.read(9)
    if len(head) != 9:
        raise Refused('setup-0 block truncated')
    crc, stored, compressed = struct.unpack('<IIB', head)
    if zlib.crc32(head[4:]) != crc:
        raise Refused('setup-0 block header CRC mismatch')
    if compressed != 1 or stored > MAX_HEADER_BLOCK:
        raise Refused(f'setup-0 block not LZMA or too large ({stored} bytes)')
    raw, data = f.read(stored), bytearray()
    if len(raw) != stored:
        raise Refused('setup-0 block truncated')
    for p in range(0, stored, 4100):
        chunk = raw[p + 4:p + 4100]
        if len(chunk) == 0 or zlib.crc32(chunk) != struct.unpack_from('<I', raw, p)[0]:
            raise Refused('setup-0 chunk CRC mismatch')
        data += chunk
    dec = lzma1(bytes(data[:5]))
    out = dec.decompress(bytes(data[5:]), max_length=MAX_HEADER_BLOCK + 1)
    if len(out) > MAX_HEADER_BLOCK:
        raise Refused('setup-0 block decompresses past the limit')
    return out


def parse_setup(entries_blob, data_blob):
    """Return (installer info, file entries, data entries) from the two setup-0 blocks."""
    c = Cursor(entries_blob, 'setup entries')
    strings = [c.string() for _ in range(HEADER_STRINGS)]
    c.take(32)  # lead bytes (ANSI build)
    counts = dict(zip(COUNTS, struct.unpack('<16I', c.take(64))))
    if any(v > MAX_ENTRIES for v in counts.values()):
        raise Refused(f'entry counts over the limit: {counts}')
    if counts['permissions'] or counts['types'] or counts['components']:
        raise Refused('permission, type or component entries are not supported')
    tail = c.take(HEADER_TAIL)
    if tail[COMPRESSION_OFFSET] != 3:
        raise Refused(f'compression {tail[COMPRESSION_OFFSET]} is not LZMA')
    if struct.unpack_from('<I', tail, SLICES_OFFSET)[0] != 1:
        raise Refused('only single-slice installers are supported')
    for _ in range(counts['languages']):
        for _ in range(10):  # name, language name, four fonts, messages, licence, info before/after
            c.string()
        c.take(4 * 6 + 1)    # language id, code page, four font sizes, right to left
    for _ in range(counts['messages']):
        c.string(), c.string(), c.take(4)
    for _ in range(counts['tasks']):
        for _ in range(6):
            c.string()
        c.take(4 + 1 + 20 + 1)
    for _ in range(counts['directories']):
        for _ in range(7):
            c.string()
        c.take(4 + 20 + 2 + 1)
    files = []
    for _ in range(counts['files']):
        s = [c.string() for _ in range(9)]
        _, location, _, external, _, options, kind = c.unpack(FILE_TAIL)
        files.append({'destination': s[1].decode('latin-1'), 'location': location,
                      'external_size': external, 'options': options, 'type': kind})
    if len(data_blob) != counts['data'] * DATA_ENTRY.size:
        raise Refused(f'data entries: {len(data_blob)} bytes for {counts["data"]} entries')
    data = []
    for i in range(counts['data']):
        e = DATA_ENTRY.unpack_from(data_blob, i * DATA_ENTRY.size)
        data.append(dict(zip(('first_slice', 'last_slice', 'chunk_offset', 'offset', 'size',
                              'chunk_size', 'md5', 'filetime', 'ver_ms', 'ver_ls', 'flags'), e)))
    return {'app_name': strings[0].decode('latin-1'), 'app_versioned_name': strings[1].decode('latin-1'),
            'counts': counts}, files, data


def relative_path(destination):
    low = destination.lower()
    root = next((r for r in ROOTS if low.startswith(r)), None)
    if root is None:
        raise Refused(f'destination outside {{app}}: {destination!r}')
    parts = destination[len(root):].split('\\')
    for part in parts:
        if part in ('', '.', '..') or any(ch in part for ch in ':/\0') or part != part.strip():
            raise Refused(f'unsafe destination {destination!r}')
    return parts


def plan(files, data):
    """Validate every entry and return [(relative path, data entry)] in stream order."""
    used, seen, out, spelled = set(), set(), [], {}
    for entry in files:
        if entry['type'] != 0:      # the uninstaller (type 1) is never installed from the data
            continue
        loc = entry['location']
        if loc >= len(data) or loc in used:
            raise Refused(f'file {entry["destination"]!r}: bad data location {loc}')
        used.add(loc)
        parts = relative_path(entry['destination'])
        # Windows merges directories that differ only in case; keep the first spelling.
        for i in range(len(parts) - 1):
            key = '/'.join(parts[:i + 1]).lower()
            parts[i] = spelled.setdefault(key, parts[i])
        rel = '/'.join(parts)
        if rel.lower() in seen:
            raise Refused(f'duplicate destination {rel!r}')
        seen.add(rel.lower())
        d = data[loc]
        if d['first_slice'] or d['last_slice']:
            raise Refused('only data embedded in the installer is supported')
        if d['flags'] & CHUNK_ENCRYPTED or not d['flags'] & CHUNK_COMPRESSED:
            raise Refused(f'{rel}: encrypted or stored chunks are not supported')
        out.append((rel, d))
    if sum(d['size'] for _, d in out) > MAX_OUTPUT:
        raise Refused('installed size over the limit')
    out.sort(key=lambda item: (item[1]['chunk_offset'], item[1]['offset']))
    end = {}
    for rel, d in out:
        key = (d['chunk_offset'], d['chunk_size'])
        if d['offset'] < end.get(key, 0):
            raise Refused(f'{rel}: overlapping file data')
        end[key] = d['offset'] + d['size']
    return out


def call_filter(buf, addr_offset, flip_high_byte=False):
    """Undo Inno 5.2's x86 CALL/JMP address transform on one extraction buffer.

    Relative addresses whose high byte is 00 or FF had their low three bytes
    made absolute (offset of the next instruction added). Inno 5.3.9 and later
    also toggle the high byte when bit 23 is set; 5.2.3 does not, so
    flip_high_byte stays False for the one supported version.
    """
    b = bytearray(buf)
    size, i = len(b) - 4, 0
    pattern = re.compile(b'[\xe8\xe9]')
    while i < size:
        m = pattern.search(b, i, size)
        if not m:
            break
        i = m.start() + 1
        if b[i + 3] in (0x00, 0xff):
            addr = (addr_offset + i + 4) & 0xffffff
            rel = (b[i] | b[i + 1] << 8 | b[i + 2] << 16) - addr
            if flip_high_byte and rel & 0x800000:
                b[i + 3] ^= 0xff
            b[i:i + 3] = (rel & 0xffffff).to_bytes(3, 'little')
        i += 4
    return bytes(b)


class ChunkStream:
    """Sequential reads from one LZMA chunk of setup-1."""

    def __init__(self, f, start, size):
        f.seek(start)
        if f.read(4) != CHUNK_MAGIC:
            raise Refused(f'no chunk magic at {start}')
        self.f, self.left = f, size - 5
        self.dec, self.buf, self.pos = lzma1(f.read(5)), bytearray(), 0

    def read(self, n):
        while len(self.buf) < n:
            if self.dec.eof:
                raise Refused('chunk stream ends before its files')
            if self.dec.needs_input:
                if self.left <= 0:
                    raise Refused('chunk ends before its files')
                piece = self.f.read(min(1 << 20, self.left))
                if not piece:
                    raise Refused('installer truncated inside a chunk')
                self.left -= len(piece)
            else:
                piece = b''
            self.buf += self.dec.decompress(piece, max_length=1 << 22)
        out = bytes(self.buf[:n])
        del self.buf[:n]
        self.pos += n
        return out

    def skip_to(self, offset):
        while self.pos < offset:
            self.read(min(BLOCK, offset - self.pos))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('installer', type=Path)
    ap.add_argument('--output', type=Path,
                    help=f'output directory (default {DEFAULT_OUTPUT}-<version>)')
    ap.add_argument('--allow-unpinned', action='store_true',
                    help='read an Inno Setup 5.2.3 installer whose hash is not pinned')
    ap.add_argument('--list', action='store_true', help='validate and list the entries; write nothing')
    args = ap.parse_args(argv)

    digest = sha256_file(args.installer)
    if digest not in PINNED and not args.allow_unpinned:
        raise Refused(f'{args.installer}: sha256 {digest} is not a pinned Inno Setup installer '
                      f'({", ".join(sorted(PINNED.values()))})')
    output = args.output or Path(f'{DEFAULT_OUTPUT}-{PINNED.get(digest, "inno")}')
    with open(args.installer, 'rb') as f:
        stub = f.read(LOADER_SEARCH)
        at = stub.find(LOADER_ID)
        if at < 0:
            raise Refused('no Inno Setup loader table (rDlPtS)')
        table = stub[at:at + 44]
        version, total, _, _, _, setup0, setup1, crc = struct.unpack_from('<8I', table, 12)
        if version != 1 or zlib.crc32(table[:40]) != crc:
            raise Refused('unsupported or corrupt Inno Setup loader table')
        size = args.installer.stat().st_size
        if not 0 < setup1 < setup0 < total <= size:
            raise Refused('loader table offsets outside the installer')
        f.seek(setup0)
        if f.read(64).rstrip(b'\0') != SETUP_ID:
            raise Refused(f'setup data is not {SETUP_ID.decode()}')
        info, files, data = parse_setup(header_block(f), header_block(f))
        items = plan(files, data)
        for _, d in items:
            if setup1 + d['chunk_offset'] + 4 + d['chunk_size'] > setup0:
                raise Refused('chunk outside the file data')
        if args.list:
            for rel, d in items:
                print(d['size'], rel)
            print(f'{len(items)} files, {sum(d["size"] for _, d in items)} bytes')
            return 0

        root = output / 'client'
        manifest, failed, stream, current = [], [], None, None
        for rel, d in items:
            key = (d['chunk_offset'], d['chunk_size'])
            if key != current:
                stream, current = ChunkStream(f, setup1 + d['chunk_offset'], d['chunk_size']), key
            stream.skip_to(d['offset'])
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            md5, sha = hashlib.md5(), hashlib.sha256()
            with open(path, 'wb') as out:
                done = 0
                while done < d['size']:
                    block = stream.read(min(BLOCK, d['size'] - done))
                    if d['flags'] & CALL_OPTIMIZED:
                        block = call_filter(block, done)
                    md5.update(block)
                    sha.update(block)
                    out.write(block)
                    done += len(block)
            ok = md5.digest() == d['md5']
            manifest.append({'path': rel, 'size': d['size'], 'sha256': sha.hexdigest(), 'md5_ok': ok})
            if not ok:
                failed.append(rel)
    report = {'installer': str(args.installer), 'sha256': digest, 'size': size,
              'format': SETUP_ID.decode(), 'app': info, 'setup0': setup0, 'setup1': setup1,
              'files': len(manifest), 'md5_failures': failed,
              'manifest': sorted(manifest, key=lambda m: m['path'].lower())}
    (output / 'manifest.json').write_text(json.dumps(report, indent=1) + '\n')
    print(f'{len(manifest)} files, {len(failed)} MD5 failures -> {root}')
    for rel in failed:
        print('  md5 mismatch:', rel)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
