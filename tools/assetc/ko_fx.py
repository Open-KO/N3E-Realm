"""Bounded local FX reader. No reference assets are required by normal builds.

Client binary: bundle00478bc0, base0047def0, particles00482f30,
billboard00489980, mesh0048ebf0. The local version2 assets have sixteen
slots; the supplied executable expects twenty-six (and reads nothing past the
end, PQ-423: so a version-1 bundle that ends after sixteen slots has sixteen).
Accept those exact layouts,
never an arbitrary early EOF. Unsupported effect families fail explicitly.

`bundle(data, layout='2233')` (PQ-339) reads a bundle as the 2233 client image
does, a 2233/2145 addition the 1298 reader never takes (bundle_2233, below);
the default layout is the 1298 reader above, unchanged.
"""
import math
from ko_character import Reader as CharacterReader
from common import count


class Reader(CharacterReader):
    def one(self, fmt):
        value = self.unpack(fmt)[0]
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('nonfinite FX value')
        return value

    def boolean(self):
        value = self.one('B')
        if value > 1:
            raise ValueError('FX boolean')
        return bool(value)

    def path(self):
        raw = self.take(260)
        if b'\0' not in raw:
            raise ValueError('unterminated FX path')
        value = raw.split(b'\0')[0].decode('cp949').replace('\\', '/')
        if value.startswith('/') or ':' in value or '..' in value.split('/'):
            raise ValueError('unsafe FX path')
        return value

    def bounded(self, low=0, high=1000):
        value = self.one('f')
        if not low <= value <= high:
            raise ValueError('FX scalar bounds')
        return value


def part(r, kind):
    d = dict(kind=kind, start=r.bounded(0, 10))
    version, base = r.unpack('2B')
    if base not in (1, 2) or kind not in (1, 2, 3) or version not in (4, 5):
        raise ValueError('unsupported FX part/base version')
    d.update(version=version, base=base, life=min(10, r.bounded()))
    if r.one('B') != kind:
        raise ValueError('FX part type mismatch')
    for key in ('velocity', 'acceleration', 'rotation'):
        d[key] = r.floats(3)
    d['ground'] = r.boolean()
    d['position'] = r.floats(3)
    d['textures'] = count(r.integer(), 128, 0)
    d['fps'] = r.bounded(0, 120)
    d['texture'] = r.path()
    alpha = r.integer() if base < 2 else 1
    if alpha not in (0, 1):
        raise ValueError('FX alpha flag')
    d['blend'] = r.unpack('2I')
    if any(x not in range(1, 11) for x in d['blend']):
        raise ValueError('FX blend factor')
    d['fadeout'], d['fadein'] = r.bounded(0, 10), r.bounded(0, 10)
    d['flags'] = r.one('I') if base >= 2 else 198 | alpha
    if kind == 1:
        d['count'] = count(r.integer(), 1024)
        d['size'] = [r.bounded(0, 20), r.bounded(0, 20)]
        d['particle_life'] = [r.bounded(0, 10), r.bounded(0, 10)]
        d['min'], d['max'] = r.floats(3), r.floats(3)
        d['delay'], d['batch'] = r.bounded(0, 10), count(r.integer(), 1024)
        d['emit'] = r.one('I')
        if d['emit'] not in (1, 2):
            raise ValueError('FX emitter kind')
        d['emit_param'] = r.floats(1 if d['emit'] == 1 else 3)
        d['direction'] = r.floats(3)
        d['speed'], d['accel'], d['rotate'], d['gravity'] = r.floats(4)
        d['colors'] = r.unpack(str(count(r.integer(), 256)) + 'I') if r.boolean() else []
        d['animation'] = r.boolean()
        if d['animation']:
            d['meshfps'], d['mesh'] = r.bounded(0, 120), r.path()
        if version >= 5:
            d['texture_rotate'], d['size_velocity_x'], d['size_velocity_y'] = r.floats(3)
        for key in ('size', 'particle_life'):
            if d[key][0] > d[key][1] or d[key][1] <= 0:
                raise ValueError('FX particle range')
        if any(a > b for a, b in zip(d['min'], d['max'])):
            raise ValueError('FX emitter bounds')
    elif kind == 2:
        d['count'] = count(r.integer(), 128)
        d['size'] = [r.bounded(0, 20), r.bounded(0, 20)]
        d['loop'], d['radius'], d['only_y'] = r.boolean(), r.bounded(0, 100), r.boolean()
        d['scale_motion'] = r.floats(4)
        if version >= 5:
            d['matrix'] = r.floats(16)
    else:
        d['mesh'], d['uvdir'], d['uv'] = r.path(), r.one('B'), r.floats(2)
        d['scale_vel'], d['loop'], d['scale_accel'] = r.floats(3), r.boolean(), r.floats(3)
        d['meshfps'] = r.bounded(0, 120)
        d['scale'] = r.floats(3) if version >= 5 else [1, 1, 1]
    return d


def bundle(data, layout='1298'):
    if layout == '2233':
        return bundle_2233(data)
    if layout != '1298':
        raise ValueError('FX layout %r' % layout)
    r = Reader(data)
    version = r.integer()
    if version not in (0, 1, 2):
        raise ValueError('unsupported FX bundle version')
    life, velocity, scale = min(10, r.bounded()), r.bounded(-100, 100), r.boolean()
    parts, part_slots = [], []
    slots = 8 if version == 0 else 26
    for slot in range(slots):
        if version == 2 and slot == 16 and len(r.data) - r.at == 1:
            slots = 16
            break
        # PQ-423: 00478bc0 reads 26 slots for version 1 too; past the end of
        # a 16-slot file ReadFile reads nothing and leaves the kind at the
        # last value read, so the rest are empty only when slot 15's kind is
        # 0 (1298's arrow.fxb); with a part there 1298 would keep re-reading
        # its kind, which is refused.
        if version == 1 and slot == 16 and len(r.data) == r.at:
            if kind:
                raise ValueError('a 16-slot version-1 FX bundle with a part in its last slot')
            slots = 16
            break
        kind = r.integer()
        if kind:
            parts.append(part(r, kind))
            part_slots.append(slot)
    static = r.boolean() if version >= 2 else False
    r.end()
    # part_slots: each part's slot, as GetPart(slot) finds it (PQ-211).
    return dict(version=version, slots=slots, life=life, velocity=velocity,
                scale=scale, static=static, parts=parts, part_slots=part_slots)


# PQ-339: the 2233 client image's bundle layout (static analysis, PQ-314; binary
# for that image only, a secondary reference; reading the player's 2145 fx pack
# with it is an inference). Evidence:
# docs/implementation/evidence/pq-339-skeletal-plug-weapon-effect-2233.md.
#
# - Bundle load 0057f0b0 (vtable 00b9715c + 0xc): version (+0x60), life
#   (+0x8c), velocity (+0x84), scale byte (+0x164); 8 slots for version 0, else
#   26: a u32 kind, and for kinds 1-4 a u32 (the start, the slot's second word)
#   and the part's own load (ctors 0058ef60 particles, 00595080 billboard,
#   0059abd0 mesh, 0059f690 a fourth class); version > 1 a byte (+0x88),
#   > 2 a byte (+0x98) and a u32 (+0x90), > 3 a u32 (+0x98) and a byte (+0x9c),
#   > 4 a byte (+0x16c), > 5 a byte (+0x16d) copied to every part's +0x345; a
#   life above 10.0 (00b8fbb8) is cut to it unless +0x16c is set.
# - Part base load 00589370: part version and base version bytes (+0x60,
#   +0x64), life; base > 2 two floats (+0x78, +0x7c: 00588610's on/off cycle);
#   the type byte; velocity, acceleration, rotation, the ground byte, position;
#   texture count, fps, the 260-byte texture name; base < 2 the alpha u32 then
#   the blends and fades, else the blends, fades and the render flags (decoded
#   as 1298's 0047def0 does); base > 3 a second 260-byte texture name (+0x205).
# - Particles 00593550 (version < 3: nothing more), billboard 005944a0, mesh
#   0059b3f0, the fourth class 0059f020: the fields by version, below.
#
# n3e reads every field and bounds it (a part's life is kept as read, as
# 00589370 keeps it; only the bundle's is cut to 10.0, by 0057f0b0); what a
# field does is the drawing side's question (ko_fx_bake and, for a tail,
# ko_fx_tail_2233 refuse what they do not draw). n3e's own guards,
# not KO behaviour: the 1298 reader's bounds where a field is the same, a part
# version above the highest the load distinguishes (particles 10, billboard 8,
# mesh 9, the fourth class 3) or a base version outside 1-4 is refused, the type
# byte must be the slot's kind, an unknown kind (2233 skips it without reading
# its start) is refused, and after the last field at most UNREAD bytes may
# remain, all zero: 2233 reads none of them (the 2145 fx pack's version 3 and 4
# bundles end with 0, 2 or 3 such bytes; PQ-339's survey).
UNREAD = 3
PART_VERSIONS = {1: 10, 2: 8, 3: 9, 4: 3}


def _raw(r, n):
    return list(r.unpack('%dI' % n))


def _base_2233(r, kind, start):
    d = dict(kind=kind, start=start)
    version, base = r.unpack('2B')
    if not 1 <= base <= 4 or not 0 <= version <= PART_VERSIONS[kind]:
        raise ValueError('unsupported 2233 FX part/base version')
    # 00589370 stores the life as read (+0x74); 1298's 0047def0 cuts it to 10.0,
    # 2233's base load does not, so neither does this layout (n3e's bound 0-1000).
    d.update(version=version, base=base, life=r.bounded())
    d['cycle'] = [r.bounded(), r.bounded()] if base > 2 else [0.0, 0.0]
    if r.one('B') != kind:
        raise ValueError('FX part type mismatch')
    for key in ('velocity', 'acceleration', 'rotation'):
        d[key] = r.floats(3)
    d['ground'] = r.boolean()
    d['position'] = r.floats(3)
    d['textures'] = count(r.integer(), 128, 0)
    d['fps'] = r.bounded(0, 120)
    d['texture'] = r.path()
    alpha = r.integer() if base < 2 else 1
    if alpha not in (0, 1):
        raise ValueError('FX alpha flag')
    d['blend'] = r.unpack('2I')
    if any(x not in range(1, 11) for x in d['blend']):
        raise ValueError('FX blend factor')
    d['fadeout'], d['fadein'] = r.bounded(0, 10), r.bounded(0, 10)
    d['flags'] = r.one('I') if base >= 2 else 198 | alpha
    d['texture2'] = r.path() if base > 3 else ''
    return d


def part_2233(r, kind, start):
    d = _base_2233(r, kind, start)
    v = d['version']
    if kind == 1:
        if v < 3:
            return d
        d['count'] = count(r.integer(), 1024)
        d['size'] = [r.bounded(0, 20)] * 2 if v < 4 else [r.bounded(0, 20), r.bounded(0, 20)]
        d['particle_life'] = [r.bounded(0, 10), r.bounded(0, 10)]
        d['min'], d['max'] = r.floats(3), r.floats(3)
        d['delay'], d['batch'] = r.bounded(0, 10), count(r.integer(), 1024)
        d['emit'] = r.one('I')
        if d['emit'] not in (1, 2):
            raise ValueError('FX emitter kind')
        d['emit_param'] = r.floats(1 if d['emit'] == 1 else 3)
        d['direction'] = r.floats(3)
        d['speed'], d['accel'], d['rotate'], d['gravity'] = r.floats(4)
        d['colors'] = r.unpack(str(count(r.integer(), 256)) + 'I') if r.boolean() else []
        d['animation'] = r.boolean()
        if d['animation']:
            d['meshfps'], d['mesh'] = r.bounded(0, 120), r.path()
        if v > 4:
            d['texture_rotate'], d['size_velocity_x'], d['size_velocity_y'] = r.floats(3)
        d['v6'] = r.one('B') if v > 5 else 0
        d['v7'] = r.one('B') if v > 6 else 0
        d['v8'] = [r.one('B')] + _raw(r, 3) if v > 7 else [0] * 4
        d['v9'] = _raw(r, 2) if v > 8 else [0] * 2
        d['v10'] = _raw(r, 1) + [r.one('B')] if v > 9 else [0] * 2
    elif kind == 2:
        d['count'] = count(r.integer(), 128)
        d['size'] = [r.bounded(0, 20), r.bounded(0, 20)]
        d['loop'], d['radius'] = r.boolean(), r.bounded(0, 100)
        d['only_y'] = r.boolean() if v > 2 else False
        d['scale_motion'] = r.floats(4) if v > 3 else [0.0] * 4
        if v > 4:
            d['matrix'] = r.floats(16)
        d['v6'] = r.one('B') if v > 5 else 0
        d['v7'] = r.one('B') if v > 6 else 0
        d['v8'] = [r.one('B')] + _raw(r, 3) if v > 7 else [0] * 4
    elif kind == 3:
        d['mesh'], d['uvdir'], d['uv'] = r.path(), r.one('B'), r.floats(2)
        d['scale_vel'] = r.floats(3)
        d['loop'] = r.boolean() if v > 1 else False
        d['scale_accel'] = r.floats(3) if v > 2 else [0.0] * 3
        d['meshfps'] = r.bounded(0, 120) if v > 3 else 0.0
        d['scale'] = r.floats(3) if v > 4 else [1, 1, 1]
        d['v6'] = r.one('B') if v > 5 else 0
        d['v7'] = r.one('B') if v > 6 else 0
        d['v8'] = r.one('B') if v > 7 else 0
        d['mesh2'] = r.path() if v > 8 else ''
    else:
        d['k4'] = _raw(r, 1) + r.floats(3) + [r.one('B')]
        d['k4_v1'] = r.floats(1) if v > 0 else [0.0]
        d['k4_v2'] = r.one('B') if v > 1 else 0
        d['k4_v3'] = r.one('B') if v > 2 else 0
    return d


def bundle_2233(data):
    """A 2233 FX bundle (0057f0b0), versions 0-6, to its last field."""
    r = Reader(data)
    version = r.integer()
    if not 0 <= version <= 6:
        raise ValueError('unsupported 2233 FX bundle version')
    life, velocity, scale = r.bounded(), r.bounded(-100, 100), r.boolean()
    parts, part_slots = [], []
    slots = 8 if version == 0 else 26
    for slot in range(slots):
        kind = r.integer()
        if kind:
            if kind not in PART_VERSIONS:
                raise ValueError('unsupported 2233 FX part kind')
            parts.append(part_2233(r, kind, r.bounded(0, 10)))
            part_slots.append(slot)
    extra = dict(b88=r.boolean() if version > 1 else False)
    if version > 2:
        extra.update(b98=r.one('B'), d90=r.one('I'))
    if version > 3:
        extra.update(d98=r.one('I'), b9c=r.one('B'))
    extra['b16c'] = r.one('B') if version > 4 else 0
    extra['b16d'] = r.one('B') if version > 5 else 0
    if not extra['b16c']:
        life = min(10, life)
    unread = len(r.data) - r.at
    if unread > UNREAD or any(r.data[r.at:]):
        raise ValueError('unsupported trailing 2233 FX data')
    return dict(layout='2233', version=version, slots=slots, life=life, velocity=velocity, scale=scale,
                static=extra['b88'], parts=parts, part_slots=part_slots, extra=extra, unread=unread)
