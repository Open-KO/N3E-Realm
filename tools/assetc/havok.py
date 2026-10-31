#!/usr/bin/env python3
"""Havok binary packfiles and wavelet-compressed skeletal animation (exploration).

Reads Havok 5.5 packfiles with 4-byte pointers, as shipped in Demon's Souls
(PS3). Nothing here is game-specific.

Wavelet decoding was reverse-engineered from game data (2026-09-26); no Havok
source or binaries were used. The `hkaWaveletSkeletalAnimation` data buffer is
little-endian even in big-endian files:

- u16 static mask per track: bits 0-1/2-3/4-5 give the position/rotation/scale
  track type (0 dynamic, 1 static, 2 identity); bits 6-8 flag dynamic position
  z/y/x, 9-12 rotation w/z/y/x and 13-15 scale z/y/x.
- Static floats fill every non-dynamic component of static and dynamic tracks,
  in track order. A static rotation w of +-2 means "rebuild w from x, y, z"
  (three-component quaternions).
- Per dynamic channel: f32 offset, f32 scale and u8 bit width.
- Quantized data comes in blocks of `blockSize` (8) frames, located by the block
  index (u32 byte offsets). Per block, each dynamic channel holds a u8 mask of
  dropped coefficients (bit i set = coefficient i is zero), then the kept
  coefficients as LSB-first `bitWidth`-bit integers, padded to a byte.
  coefficient = offset + q / (2^bitWidth - 1) * scale.
- The eight coefficients are a three-level LeGall 5/3 lifting wavelet with
  symmetric (mirrored) block edges, in Mallat order (DC, then coarsest to finest
  detail). A final partial block keeps its first frames.

Validation: fully dynamic quaternions decode to unit length within 0.0007
across 83,632 samples, and consecutive blocks join smoothly.
"""
import math
import struct

WAVELET = "hkaWaveletSkeletalAnimation"


class Packfile:
    """Sections, pointer fixups and typed objects of a binary packfile."""

    def __init__(self, data):
        if data[:8] != b"\x57\xe0\xe0\x57\x10\xc0\xc0\x10":
            raise ValueError("not a Havok packfile")
        self.d = data
        self.ptrsize, little = data[16], data[17]
        if self.ptrsize != 4:
            raise ValueError("only 4-byte pointer packfiles are handled")
        self.e = "<" if little else ">"
        nsec = struct.unpack_from(self.e + "i", data, 20)[0]
        self.version = data[40:56].split(b"\0")[0].decode()
        self.starts, self.ptrs, self.objects = [], {}, []
        heads = []
        for i in range(nsec):
            o = 0x40 + 0x30 * i
            heads.append(struct.unpack_from(self.e + "7I", data, o + 20))
            self.starts.append(heads[-1][0])
        for si, (start, local, glob, virt, exports, _imports, _end) in enumerate(heads):
            for k in range(local, glob - 7, 8):
                src, dst = struct.unpack_from(self.e + "2I", data, start + k)
                if src != 0xFFFFFFFF:
                    self.ptrs[(si, src)] = (si, dst)
            for k in range(glob, virt - 11, 12):
                src, dsec, dst = struct.unpack_from(self.e + "3I", data, start + k)
                if src != 0xFFFFFFFF:
                    self.ptrs[(si, src)] = (dsec, dst)
            for k in range(virt, exports - 11, 12):
                src, csec, coff = struct.unpack_from(self.e + "3I", data, start + k)
                if src != 0xFFFFFFFF:
                    self.objects.append(((si, src), self.cstr((csec, coff))))

    def at(self, loc, off=0):
        return self.starts[loc[0]] + loc[1] + off

    def unpack(self, fmt, loc, off=0):
        return struct.unpack_from(self.e + fmt, self.d, self.at(loc, off))

    def ptr(self, loc, off=0):
        return self.ptrs.get((loc[0], loc[1] + off))

    def cstr(self, loc):
        if not loc:
            return None
        a = self.at(loc)
        return self.d[a:self.d.index(b"\0", a)].decode("latin1")

    def find(self, cls):
        return [loc for loc, name in self.objects if name == cls]


def skeleton(p):
    """(bone names, parent indices, reference pose [(t, q, s)]) of the first hkaSkeleton (Havok 5.5)."""
    loc = p.find("hkaSkeleton")[0]
    n = p.unpack("I", loc, 8)[0]
    parents = list(p.unpack("%dh" % n, p.ptr(loc, 4)))
    bones = p.ptr(loc, 12)
    names = [p.cstr(p.ptr(p.ptr(bones, 4 * k))) for k in range(n)]
    pose = []
    for k in range(n):
        v = p.unpack("12f", p.ptr(loc, 20), 48 * k)
        pose.append((list(v[0:3]), list(v[4:8]), list(v[8:11])))
    return names, parents, pose


def binding(p):
    """Transform track -> bone index of the first hkaAnimationBinding."""
    loc = p.find("hkaAnimationBinding")[0]
    n = p.unpack("I", loc, 8)[0]
    return list(p.unpack("%dh" % n, p.ptr(loc, 4)))


# ---------------------------------------------------------------- wavelet decoding

def _lift_inverse_step(s, d):
    """Inverse LeGall 5/3 step with symmetric edges: e[h] mirrors e[h-1], d[-1] mirrors d[0]."""
    h = len(s)
    e = [s[i] - ((d[i - 1] if i else d[0]) + d[i]) / 4 for i in range(h)]
    o = [d[i] + (e[i] + (e[i + 1] if i + 1 < h else e[i])) / 2 for i in range(h)]
    return [v for pair in zip(e, o) for v in pair]


def inverse_wavelet(c):
    """Mallat-ordered coefficients (length 2^k) -> samples."""
    sizes, n = [], len(c)
    while n > 1:
        n //= 2
        sizes.append(n)
    a, at = c[:1], 1
    for h in reversed(sizes):
        a = _lift_inverse_step(a, c[at:at + h])
        at += h
    return a


def _block_channel(data, at, count, width):
    """One channel of one block: (coefficients with dropped ones as None, next offset)."""
    mask = data[at]
    kept = [i for i in range(count) if not (mask >> i) & 1]
    bits = int.from_bytes(data[at + 1:at + 1 + (len(kept) * width + 7) // 8], "little")
    out = [None] * count
    for k, i in enumerate(kept):
        out[i] = (bits >> (k * width)) & ((1 << width) - 1)
    return out, at + 1 + (len(kept) * width + 7) // 8


def wavelet_animation(p, loc=None):
    """Decode an hkaWaveletSkeletalAnimation (Havok 5.5, 4-byte pointers).

    Returns {duration, frames, tracks}; each track has per-frame "pos" [x, y, z],
    "rot" [x, y, z, w] and "scale" [x, y, z].
    """
    loc = loc or p.find(WAVELET)[0]
    duration = p.unpack("f", loc, 12)[0]
    ntracks = p.unpack("i", loc, 16)[0]
    poses, block = p.unpack("II", loc, 36)
    width_max, _preserved = p.unpack("BB", loc, 44)
    numd, off_i, scale_i, width_i, mask_i, static_i, block_i, nblocks, q_i, q_size = p.unpack("10I", loc, 48)
    buf_loc, nbuf = p.ptr(loc, 88), p.unpack("i", loc, 92)[0]
    if buf_loc is None:
        raise ValueError("animation has no data buffer")
    buf = p.d[p.at(buf_loc):p.at(buf_loc) + nbuf]
    masks = struct.unpack_from("<%dH" % ntracks, buf, mask_i)
    offsets = struct.unpack_from("<%df" % numd, buf, off_i)
    scales = struct.unpack_from("<%df" % numd, buf, scale_i)
    widths = buf[width_i:width_i + numd]
    starts = list(struct.unpack_from("<%dI" % nblocks, buf, block_i))
    qdata = buf[q_i:q_i + q_size]
    channels = [[] for _ in range(numd)]
    for b, start in enumerate(starts):
        at, frames = start, min(block, poses - b * block)
        for ch in range(numd):
            q, at = _block_channel(qdata, at, block, widths[ch])
            span = (1 << widths[ch]) - 1
            coeffs = [0.0 if v is None else offsets[ch] + v / span * scales[ch] for v in q]
            channels[ch] += inverse_wavelet(coeffs)[:frames]
    static = struct.unpack_from("<%df" % ((off_i - static_i) // 4), buf, static_i)
    tracks, si, di = [], 0, 0
    for m in masks:
        track = {}
        for key, shift, bits, identity in (("pos", 0, (8, 7, 6), [0, 0, 0]), ("rot", 2, (12, 11, 10, 9), [0, 0, 0, 1]),
                                           ("scale", 4, (15, 14, 13), [1, 1, 1])):
            kind = (m >> shift) & 3
            if kind == 2:
                comps = [[v] * poses for v in identity]
            elif kind == 1:
                comps = [[static[si + k]] * poses for k in range(len(bits))]
                si += len(bits)
            else:
                comps = []
                for bit in bits:
                    if (m >> bit) & 1:
                        comps.append(channels[di])
                        di += 1
                    else:
                        comps.append([static[si]] * poses)
                        si += 1
            track[key] = [[c[f] for c in comps] for f in range(poses)]
        for q in track["rot"]:
            if abs(abs(q[3]) - 2) < 1e-6:        # three-component quaternion: rebuild w
                q[3] = math.copysign(math.sqrt(max(0.0, 1 - q[0] ** 2 - q[1] ** 2 - q[2] ** 2)), q[3])
        tracks.append(track)
    if di != numd or si != len(static):
        raise ValueError("static mask does not match the channel tables")
    return {"duration": duration, "frames": poses, "tracks": tracks, "max_bit_width": width_max}
