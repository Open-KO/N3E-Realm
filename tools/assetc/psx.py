#!/usr/bin/env python3
"""Generic PlayStation (PS1) formats for local, player-supplied disc images (exploration).

- a raw 2352-byte-sector disc image with an ISO 9660 file system (Mode 2 Form 1);
- TIM images loaded into a model of the 1024x512 16-bit VRAM, sampled through
  4/8-bit texture pages and CLUTs as the GPU does;
- TOD animation streams (object create/parent/TMD-link and RST coordinate
  packets), played into per-object transforms.

Nothing here is game-specific. Game containers live in their own modules (for
example `shadow_tower.py`). Disc contents are never committed.
"""
import math
import struct
import zlib
from pathlib import Path

SECTOR, USER = 2352, 24          # raw sector size; Mode 2 Form 1 user data offset


class Disc:
    """Read files from a raw .bin image by ISO 9660 path (e.g. "ST/CHR1/M12.T")."""

    def __init__(self, path):
        self.f = open(path, "rb")
        pvd = self.sector(16)
        if pvd[1:6] != b"CD001":
            raise ValueError(f"{path}: no ISO 9660 volume descriptor")
        self.root = struct.unpack_from("<I", pvd, 156 + 2)[0], struct.unpack_from("<I", pvd, 156 + 10)[0]

    def sector(self, lba):
        self.f.seek(lba * SECTOR)
        raw = self.f.read(SECTOR)
        if len(raw) != SECTOR:
            raise ValueError("sector out of range")
        return raw[USER:USER + 2048]

    def extent(self, lba, size):
        return b"".join(self.sector(lba + k) for k in range((size + 2047) // 2048))[:size]

    def listdir(self, lba, size):
        data, out, at = self.extent(lba, size), {}, 0
        while at < len(data):
            n = data[at]
            if n == 0:
                at = (at // 2048 + 1) * 2048
                continue
            ext, length, flags, nl = (struct.unpack_from("<I", data, at + 2)[0], struct.unpack_from("<I", data, at + 10)[0],
                                      data[at + 25], data[at + 32])
            name = data[at + 33:at + 33 + nl].decode("ascii", "replace").split(";")[0]
            if name not in ("\0", "\1"):
                out[name] = (ext, length, bool(flags & 2))
            at += n
        return out

    def read(self, path):
        lba, size = self.root
        for part in path.strip("/").split("/"):
            entries = self.listdir(lba, size)
            if part not in entries:
                raise FileNotFoundError(path)
            lba, size, _ = entries[part]
        return self.extent(lba, size)


# ---------------------------------------------------------------- TIM / VRAM

class VRAM:
    def __init__(self):
        self.m = [[0] * 1024 for _ in range(512)]

    def load_tim(self, t):
        magic, flags = struct.unpack_from("<II", t, 0)
        if magic != 0x10 or flags & ~0xF:
            raise ValueError("not a TIM")
        blocks, at = [], 8
        if flags & 8:
            blocks.append(at)
            at += struct.unpack_from("<I", t, at)[0]
        blocks.append(at)
        for b in blocks:
            _, x, y, w, h = struct.unpack_from("<IHHHH", t, b)
            for r in range(h):
                self.m[y + r][x:x + w] = struct.unpack_from("<%dH" % w, t, b + 12 + r * w * 2)

    def texel(self, tsb, cba, u, v):
        """The 15-bit colour the GPU samples for texture page `tsb`, CLUT `cba` at (u, v)."""
        px, py, mode = (tsb & 15) * 64, ((tsb >> 4) & 1) * 256, (tsb >> 7) & 3
        cx, cy = (cba & 63) * 16, cba >> 6
        if mode == 2:
            return self.m[py + v][px + u]
        if mode == 1:
            idx = (self.m[py + v][px + u // 2] >> (8 * (u & 1))) & 255
        else:
            idx = (self.m[py + v][px + u // 4] >> (4 * (u & 3))) & 15
        return self.m[cy][cx + idx]


def rgb(c):
    return ((c & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, ((c >> 10) & 31) * 255 // 31)


def write_png(path, width, height, pixels):
    """RGB8, no ancillary chunks (the `gltf.cook` texture subset)."""
    rows = b"".join(b"\0" + bytes(v for p in pixels[y * width:(y + 1) * width] for v in p) for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- TOD

def tod_parse(d, start):
    """Frames of (frame_no, [(object_id, type, flag, data)])."""
    ident, _version, _resolution, nframes = struct.unpack_from("<BBHI", d, start)
    if ident != 0x50:
        raise ValueError("not a TOD stream")
    at, frames = start + 8, []
    for _ in range(nframes):
        size, npackets, frame_no = struct.unpack_from("<HHI", d, at)
        q, packets = at + 8, []
        for _ in range(npackets):
            oid, tf, length = struct.unpack_from("<HBB", d, q)
            packets.append((oid, tf & 15, tf >> 4, d[q + 4:q + 4 * length]))
            q += 4 * length
        if q - at != size * 4:
            raise ValueError("TOD frame size")
        frames.append((frame_no, packets))
        at = q
    return frames


def _s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def _s20(v):
    v &= 0xFFFFF
    return v - (1 << 20) if v & 0x80000 else v


def tod_play(frames):
    """Per-frame object state {id: {parent, tmd, r, s, t}}.

    Coordinate packets: flag bit 0 differential (added to the previous frame),
    bit 1 rotation (3 x s32, 1/4096 degree), bit 2 scale (3 x s16 + pad, 4096 = 1),
    bit 3 translation (3 x s32, of which 20 bits are significant here).
    """
    state, out = {}, []
    for _frame_no, packets in frames:
        for oid, kind, flag, data in packets:
            if kind not in (1, 2, 3):
                continue                     # 0 attribute, 8 create/kill, 15 end
            o = state.setdefault(oid, {"parent": 0, "tmd": None, "r": [0, 0, 0], "s": [4096] * 3, "t": [0, 0, 0]})
            if kind == 2:
                o["tmd"] = struct.unpack_from("<H", data)[0]
            elif kind == 3:
                o["parent"] = struct.unpack_from("<H", data)[0]
            else:
                at, diff = 0, flag & 1
                if flag & 2:
                    r = [_s32(x) for x in struct.unpack_from("<3I", data, at)]
                    at += 12
                    o["r"] = [a + b for a, b in zip(o["r"], r)] if diff else r
                if flag & 4:
                    o["s"] = list(struct.unpack_from("<3h", data, at))
                    at += 8
                if flag & 8:
                    t = [_s20(x) for x in struct.unpack_from("<3I", data, at)]
                    o["t"] = [a + b for a, b in zip(o["t"], t)] if diff else t
        out.append({k: {**v, "r": list(v["r"]), "s": list(v["s"]), "t": list(v["t"])} for k, v in state.items()})
    return out


# ---------------------------------------------------------------- matrices

def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def rst(o):
    """An object's local matrix: translate, then rotate (Z * Y * X), then scale."""
    rx, ry, rz = [math.radians(v / 4096) for v in o["r"]]
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    X = [[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]]
    Y = [[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]]
    Z = [[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    m = matmul(Z, matmul(Y, X))
    for i in range(3):
        for j in range(3):
            m[i][j] *= o["s"][j] / 4096
        m[i][3] = o["t"][i]
    return m


def world(state, oid, cache):
    if oid not in cache:
        o = state[oid]
        m = rst(o)
        if o["parent"] in state:
            m = matmul(world(state, o["parent"], cache), m)
        cache[oid] = m
    return cache[oid]


def invert_rigid(m):
    """Inverse of a rotation(+uniform scale) and translation matrix."""
    r = [[m[j][i] for j in range(3)] for i in range(3)]
    s2 = sum(r[0][k] ** 2 for k in range(3))
    r = [[v / s2 for v in row] for row in r]
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]], [0, 0, 0, 1]]


def quat(m):
    """Unit quaternion (x, y, z, w) of a rotation matrix's upper 3x3."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1) * 2
        q = [(m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, s / 4]
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1 + m[0][0] - m[1][1] - m[2][2]) * 2
        q = [s / 4, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s]
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1 + m[1][1] - m[0][0] - m[2][2]) * 2
        q = [(m[0][1] + m[1][0]) / s, s / 4, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s]
    else:
        s = math.sqrt(1 + m[2][2] - m[0][0] - m[1][1]) * 2
        q = [(m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, s / 4, (m[1][0] - m[0][1]) / s]
    n = math.sqrt(sum(x * x for x in q))
    return [x / n for x in q]
