#!/usr/bin/env python3
"""List and extract the 2145 client's `.hdr`/`.src` packs offline (PQ-308).

Research tooling for the 2145 secondary reference (BINARY-POLICY): never a
build step, never the default player import. Since PQ-317 the opt-in 2233
additions cook (tools/assetc/ko_chrplug_2145.py, `ko_bake.py ... --glow-2233`)
reads the player's Item pack through `Pack`, after checking the `.hdr` and
`.src` against the install's manifest. Record:
docs/implementation/evidence/pq-308-ko-2145-pack-reader.md.

The 2145 client keeps its `Item`, `UI`, `fx` and `Object` folders as one pack
each: `<folder>/<name>.hdr` lists the entries and `<folder>/<name>.src` holds
their bytes. The header is

    u32 count
    count times:  u32 name length, the name (no terminator), u32 offset, u32 size

which the 2145 `Launcher.exe` writes at `00407ae7` (CharLowerA on each name)
and the 2233 client image reads at `0047d0f0` (binary, both; the 2145 client
exe is packed). The 2233 client's lookup (`0047e1f0`, `0047c9e0`) lower-cases
the requested path, turns each `/` into `\\` (`0047dfb0`), takes the part
before its first backslash as the pack folder and looks the rest up by a djb2 key of the name (`0047c7a0`: seed
5381, times 33 plus each signed char); its read cursor ends at offset + size
(`0047c750`, `0047d8b0`), so the first field is the offset.

This reader is stricter than the client, which reads the name into a 256-byte
stack buffer without checking the length. It refuses, before anything is
written:

- a header over MAX_HEADER bytes, a count of 0 or over MAX_ENTRIES, or one the
  header is too short for, and bytes left after the last entry;
- a name length of 0 or over MAX_NAME, or a name that is not printable
  lower-case ASCII as the launcher writes it;
- a name with an empty, `.`, `..`, space- or dot-ended component, a `/` or a
  `:`, so no backslash path in `fx` can leave the output directory;
- a duplicate name, two names with the client's lookup key, and a name that is
  also another entry's folder;
- a range past the end of the `.src`, a `.src` over MAX_SOURCE, and two ranges
  that overlap.

Unreferenced bytes between ranges are allowed (the shipped packs have them)
and are counted. Extraction writes only under the repository's `build/`: every
target is checked for links and clashes before the first write, and each file
is renamed into place, so an existing link is replaced, never written through.
"""

import argparse
import fnmatch
import os
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
DEFAULT_OUTPUT = BUILD / "ko-reference/packs-2145"
MAX_HEADER = 16 << 20       # the shipped headers are at most 456,033 bytes
MAX_ENTRIES = 200_000       # the shipped packs hold at most 10,754
MAX_NAME = 255              # the 2233 reader's buffer is 256 bytes, zeroed
MAX_SOURCE = 1 << 32        # offsets and sizes are u32
MIN_ENTRY = 4 + 1 + 8
CHUNK = 1 << 20
ALLOWED = frozenset(range(0x20, 0x7F)) - frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ/:")


def lookup_key(name):
    """The 2233 client's key for a pack name (0047c7a0): djb2 over signed chars."""
    key = 5381
    for byte in name:
        key = (key * 33 + (byte - 256 if byte > 127 else byte)) & 0xFFFFFFFF
    return key


def check_name(name):
    if not name or len(name) > MAX_NAME:
        raise ValueError("2145 pack: a %d-byte name" % len(name))
    if not set(name) <= ALLOWED:
        raise ValueError("2145 pack: name %r is not printable lower-case ASCII" % name)
    for part in name.split(b"\\"):
        if part in (b"", b".", b"..") or part.endswith((b" ", b".")) or part.startswith(b" "):
            raise ValueError("2145 pack: name %r has an unsafe component" % name)
    return name.decode("ascii")


class Pack:
    """One `.hdr`/`.src` pair, validated whole on open."""

    def __init__(self, hdr, src=None):
        self.hdr = Path(hdr)
        self.src = Path(src) if src is not None else self.hdr.with_suffix(".src")
        size = self.hdr.stat().st_size
        if size > MAX_HEADER:
            raise ValueError("2145 pack: %s is %d bytes, over the bound" % (self.hdr, size))
        data = self.hdr.read_bytes()
        self.source_size = self.src.stat().st_size
        if self.source_size > MAX_SOURCE:
            raise ValueError("2145 pack: %s is %d bytes, over the bound" % (self.src, self.source_size))
        if len(data) < 4:
            raise ValueError("2145 pack: no count")
        count, = struct.unpack_from("<I", data, 0)
        if not 0 < count <= MAX_ENTRIES or count * MIN_ENTRY > len(data) - 4:
            raise ValueError("2145 pack: %d entries in a %d-byte header" % (count, len(data)))
        entries, at = [], 4
        for _ in range(count):
            if at + 4 > len(data):
                raise ValueError("2145 pack: the header ends inside entry %d" % len(entries))
            length, = struct.unpack_from("<I", data, at)
            if not 0 < length <= MAX_NAME:
                raise ValueError("2145 pack: a %d-byte name" % length)
            if at + 4 + length + 8 > len(data):
                raise ValueError("2145 pack: the header ends inside entry %d" % len(entries))
            name = check_name(data[at + 4:at + 4 + length])
            offset, span = struct.unpack_from("<II", data, at + 4 + length)
            if offset + span > self.source_size:
                raise ValueError("2145 pack: %s runs to byte %d of a %d-byte .src" % (name, offset + span, self.source_size))
            entries.append((name, offset, span))
            at += 4 + length + 8
        if at != len(data):
            raise ValueError("2145 pack: %d bytes after the last entry" % (len(data) - at))
        self.entries = entries
        self.by_name = {}
        keys = {}
        for name, offset, span in entries:
            if name in self.by_name:
                raise ValueError("2145 pack: %s twice" % name)
            other = keys.setdefault(lookup_key(name.encode("ascii")), name)
            if other != name:
                raise ValueError("2145 pack: %s and %s share the client's lookup key" % (other, name))
            self.by_name[name] = (offset, span)
        for name in self.by_name:
            parts = name.split("\\")
            for i in range(1, len(parts)):
                if "\\".join(parts[:i]) in self.by_name:
                    raise ValueError("2145 pack: %s is a file and a folder of %s" % ("\\".join(parts[:i]), name))
        ranges = sorted((offset, span, name) for name, offset, span in entries)
        self.unreferenced = ranges[0][0] if ranges else 0
        for (a, n, x), (b, m, y) in zip(ranges, ranges[1:]):
            if a + n > b:
                raise ValueError("2145 pack: %s and %s overlap" % (x, y))
            self.unreferenced += b - (a + n)
        if ranges:
            self.unreferenced += self.source_size - (ranges[-1][0] + ranges[-1][1])

    def find(self, name):
        """(offset, size) for a name, or None. Lower-cased as the client's
        lookup does (0047c9e0), `/` taken for `\\` as `0047dfb0` does."""
        return self.by_name.get(name.replace("/", "\\").lower())

    def chunks(self, name):
        found = self.find(name)
        if found is None:
            raise KeyError(name)
        offset, size = found
        with self.src.open("rb") as f:
            f.seek(offset)
            while size:
                block = f.read(min(size, CHUNK))
                if not block:
                    raise ValueError("2145 pack: %s ends early" % name)
                size -= len(block)
                yield block

    def read(self, name):
        return b"".join(self.chunks(name))

    def select(self, names=(), patterns=()):
        """Entries matching exact names or fnmatch patterns; all without either."""
        if not names and not patterns:
            return [e[0] for e in self.entries]
        picked = []
        for name in names:
            key = name.replace("/", "\\").lower()
            if key not in self.by_name:
                raise ValueError("2145 pack: no entry %s" % name)
            picked.append(key)
        for pattern in patterns:
            hits = [e[0] for e in self.entries if fnmatch.fnmatchcase(e[0], pattern.replace("/", "\\").lower())]
            if not hits:
                raise ValueError("2145 pack: nothing matches %s" % pattern)
            picked.extend(hits)
        return list(dict.fromkeys(picked))

    def extract(self, output, names):
        """Write the named entries under `output`, which must lie under build/.

        Every target is checked before the first folder or file is made: no
        component of its path under `output` may be a symlink, a folder on it
        must not be a file, and the target must not be a folder. Each file is
        written to a new temporary file in its folder and renamed over the
        target, so an existing link (hard or symbolic) is replaced, never
        written through."""
        root = Path(os.path.realpath(output))
        build = Path(os.path.realpath(BUILD))
        if root == build or build not in root.parents:
            raise ValueError("2145 pack: output %s is not under %s" % (output, BUILD))
        targets = []
        for name in names:
            parts = name.split("\\")
            path = root
            for i, part in enumerate(parts):
                path = path / part
                if path.is_symlink():
                    raise ValueError("2145 pack: %s would leave %s through a link" % (name, root))
                if path.exists() and (path.is_dir() != (i < len(parts) - 1)):
                    raise ValueError("2145 pack: %s is in the way of %s" % (path, name))
            targets.append((name, path))
        written = []
        for name, dest in targets:
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=dest.parent, prefix=".pack_2145-")  # O_CREAT | O_EXCL
            try:
                os.fchmod(fd, 0o644)
                with os.fdopen(fd, "wb") as f:
                    for block in self.chunks(name):
                        f.write(block)
                os.replace(temp, dest)
            except BaseException:
                os.unlink(temp)
                raise
            written.append(dest)
        return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("list", "extract"))
    ap.add_argument("hdr", type=Path, help="the pack's .hdr; its .src sits beside it")
    ap.add_argument("--src", type=Path, help="the .src, if not beside the .hdr")
    ap.add_argument("--name", action="append", default=[], help="an exact entry name (repeatable)")
    ap.add_argument("--glob", action="append", default=[], help="an fnmatch pattern over names (repeatable)")
    ap.add_argument("--output", type=Path, help="extraction directory under build/ (default build/ko-reference/packs-2145/<pack>)")
    ap.add_argument("--summary", action="store_true", help="list: print the summary line only")
    args = ap.parse_args(argv)
    try:
        pack = Pack(args.hdr, args.src)
        names = pack.select(args.name, args.glob)
        if args.command == "list":
            if not args.summary:
                for name in names:
                    offset, size = pack.by_name[name]
                    print("%s\t%d\t%d" % (name, offset, size))
        else:
            output = args.output or DEFAULT_OUTPUT / args.hdr.stem.lower()
            pack.extract(output, names)
    except (OSError, ValueError) as error:
        print("REFUSED %s" % error, file=sys.stderr)
        return 2
    print("PACK %s entries=%d selected=%d bytes=%d src=%d unreferenced=%d%s" % (
        args.hdr.stem.lower(), len(pack.entries), len(names), sum(pack.by_name[n][1] for n in names),
        pack.source_size, pack.unreferenced, "" if args.command == "list" else " output=%s" % output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
