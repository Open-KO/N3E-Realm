"""PQ-211: KO hand-plug weapon effects cooked into N3E2 (N3E5 since PQ-376), on original synthetic bytes.

Checks the effect choice (0045ccc0 and the setter's Item_Ext column 5 fallback),
the trace colour (0045cb5e), the item table layout guard, the FX mesh copies
and reference points (00415910), the tail's target scale (00415370, 00484980),
the cooked N3E2 section and the client reader (build/client/n3e-effects-check)
on the cooked file and on malformed ones; since PQ-376 the N3E5 sort record
(00415910's plug origin and FX mesh y extent) and its bounds, and the refusal
of a tail particle part that does not alpha-blend (004840b0). No KO data is
read.
"""
import math
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/assetc'))
import appearance_effects  # noqa: E402
import ko_character  # noqa: E402
import ko_fx_bake  # noqa: E402
import ko_weapon_fx as w  # noqa: E402
from common import f, string, u  # noqa: E402

CHECK = ROOT / 'build/client/n3e-effects-check'


def pack(fmt, *values):
    return struct.pack('<' + fmt, *values)


def ext(**k):
    row = dict(restriction=0, effect=0, attribute=5, fire=0, ice=0, lightning=0, poison=0)
    row.update(k)
    return row


def org(cls=21, base=0):
    return {'class': cls, 'effect_base': base}


# 0045ccc0 and its fallback: column 5 itself unless column 26 / 1000 and column 5
# are both set; then the staff (class 110) adds 0/10/20 by its largest element
# (ties go to fire), and another class takes the base only with column 3 = 0.
assert w.effect_id(org(), ext(effect=12001)) == 12001
assert w.effect_id(org(), ext()) == 0
assert w.effect_id(org(52, 12070000), ext(effect=12011)) == 12070
assert w.effect_id(org(52, 12070000), ext(effect=0)) == 0
assert w.effect_id(org(52, 12070000), ext(effect=12011, restriction=156210000)) == 12011
assert w.effect_id(org(110, 40000000), ext(effect=12011, fire=5, ice=5)) == 40000
assert w.effect_id(org(110, 40000000), ext(effect=12011, fire=5, ice=6)) == 40010
assert w.effect_id(org(110, 40000000), ext(effect=12011, fire=5, ice=6, lightning=7)) == 40020
assert w.effect_id(org(110, 40000000), ext(effect=12011, fire=9, ice=6, lightning=7)) == 40000
assert w.effect_id(org(110, 40000000), ext(effect=12011)) == 12011
# 0045cb5e: the first element above 63, or any on attribute 4 or 6.
assert w.trace_color(ext(fire=64)) == 0xffffff00 and w.trace_color(ext(fire=63)) == 0xffffffff
assert w.trace_color(ext(ice=64, fire=10)) == 0xffb4c8ff
assert w.trace_color(ext(lightning=1, attribute=4)) == 0xff1e96f0
assert w.trace_color(ext(poison=1, attribute=6)) == 0xffff00ff and w.trace_color(ext(poison=1)) == 0xffffffff


def texture(colour):
    return pack('i', 0) + b'NTF\x03' + pack('4i', 4, 4, 21, 0) + pack('I', colour) * 16


def billboard(frames, fps, flags, loop=1):
    part = pack('ifBBfB', 2, 0, 4, 2, 0, 2) + pack('9f', *[0] * 9) + b'\0' + pack('3f', 0, 0, 0)
    part += pack('if', frames, fps) + b'fx/glow' + bytes(253) + pack('IIffI', 3, 2, 0, 0, flags)
    return part + pack('iffBfB4f', 1, 1, 1, loop, 0, 0, 0, 0, 0, 0)


def particles(life=(.1, .3), gravity=10., flags=455):
    part = pack('ifBBfB', 1, 0, 5, 2, 0, 1) + pack('9f', *[0] * 9) + b'\0' + pack('3f', 0, 0, 0)
    part += pack('if', 1, 20) + b'fx/spark' + bytes(252) + pack('IIffI', 5, 2, 0, 0, flags)
    part += pack('i2f2f3f3ffiIf3f4fBB3f', 30, .05, .2, *life, -.05, -.05, -.05, .05, .05, .05, .03, 10, 1, 0,
                 0, 0, 0, 0, 0, 0, gravity, 0, 0, 0, 0, 0)
    return part


def bundle(*parts, scale=1, life=0.):
    return pack('iffB', 2, life, 0, scale) + b''.join(parts) + pack('i', 0) * (16 - len(parts)) + b'\0'


def mesh(vertices, indices):
    return string('original') + pack('6i', 0, 0, len(vertices), len(indices), len(vertices), len(indices)) \
        + f([x for v in vertices for x in v]) + pack(f'{len(indices)}H', *indices) + u(0)


# The FX mesh: one triangle along the blade, normals +x; the plug turns it a
# quarter about z and lifts it 0.5 m on a joint at (0, 1, 0).
FX = [[0, 0, 0, 1, 0, 0, 0, 0], [0, 1, 0, 1, 0, 0, 1, 0], [0, 0, .2, 1, 0, 0, 0, 1]]
QUARTER = [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
MATERIAL = f([1] * 4 + [0] * 13) + u(0) * 6
COLUMNS = {1: 'UInt32', 2: 'Byte', 11: 'Byte', 26: 'UInt32'}


def header(n, kinds):
    return ','.join(f'"{i} - {kinds.get(i, "Int16")}"' for i in range(1, n + 1))


def tables(root, ext_columns=None):
    data = root / 'Data'
    data.mkdir(parents=True, exist_ok=True)
    o = ['0'] * 37
    o[0], o[1], o[2], o[10] = '120110000', '1', 'Blade', '21'
    (data / 'Item_Org_us.tbl.csv').write_text(header(37, COLUMNS) + '\n' + ','.join(o) + '\n', encoding='utf-8')
    kinds = ext_columns or {1: 'UInt32', 3: 'UInt32', 5: 'UInt32', 8: 'Byte', 22: 'Byte', 23: 'Byte', 24: 'Byte',
                            25: 'Byte'}
    rows = []
    for number, effect, fire in ((47, 0, 70), (48, 12001, 80)):
        e = ['0'] * 53
        e[0], e[1], e[4], e[7], e[21] = str(number), 'Burning', str(effect), '5', str(fire)
        rows.append(','.join(e))
    (data / 'Item_Ext_1_us.tbl.csv').write_text(header(53, kinds) + '\n' + '\n'.join(rows) + '\n', encoding='utf-8')
    (data / 'fx.tbl.csv').write_text('"1 - UInt32","2 - String","3 - String","4 - Int32","5 - Byte"\n'
                                     '"12001","","fx/main.fxb","0","0"\n"12002","","fx/tail.fxb","0","0"\n',
                                     encoding='utf-8')


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    tables(root)
    (root / 'fx').mkdir()
    for i, colour in enumerate((0xffff0000, 0xff00ff00, 0xff0000ff)):
        (root / f'fx/glow{i:04d}.dxt').write_bytes(texture(colour))
    (root / 'fx/spark0000.dxt').write_bytes(texture(0xffffff00))
    (root / 'fx/main.fxb').write_bytes(bundle(billboard(3, 12, 455)))
    (root / 'fx/tail.fxb').write_bytes(bundle(particles()))
    (root / 'Item').mkdir()
    base = string('original') + u(0) + u(0) + f([0, .5, 0]) + f(QUARTER) + f([1, 1, 1]) + MATERIAL \
        + string('item\\blade.n3pmesh') + string('item\\blade.dxt')
    trace = pack('iIff', 8, 0xffffffff, .1, .75)
    (root / 'Item/blade.n3cplug').write_bytes(base + trace + pack('i', 1) + mesh(FX, [0, 1, 2]))
    (root / 'Item/plain.n3cplug').write_bytes(base + trace + pack('i', 0))
    (root / 'Item/old.n3cplug').write_bytes(base)
    assets = ko_character.Assets(root)

    # Item numbers: the base row, then Item_Ext_<column 2> row num % 1000.
    fx = w.effect(assets, 120110048)
    assert (fx['main_id'], fx['main'], fx['tail'], fx['trace_color']) == (12001, 'fx/main.fxb', 'fx/tail.fxb',
                                                                          0xffffff00), fx
    plain = w.effect(assets, 120110047)
    assert plain['main'] is None and plain['tail'] is None, plain  # +7: column 5 = 0, no fx.tbl row 0
    for bad in (120110049, 130110048, 0):
        try:
            w.effect(assets, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(('accepted', bad))

    # The FX mesh, placed by the plug on a joint at (0, 1, 0), height 1.8.
    bind = [[1, 0, 0, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]]
    g = w.geometry(assets, 'Item/blade.n3cplug', 3, bind, 1.8)
    assert w.geometry(assets, 'Item/plain.n3cplug', 3, bind, 1.8) is None
    assert w.geometry(assets, 'Item/old.n3cplug', 3, bind, 1.8) is None  # older file: no flag, no mesh
    assert [len(c['vertices']) for c in g['copies']] == [3, 3, 3]
    assert [(c['jitter'], c['frame_offset']) for c in g['copies']] == [(0, 0), (1, 1), (-1, 2)]

    def close(a, b):
        return all(abs(x - y) < 1e-5 for x, y in zip(a, b))
    # KO row vectors: (x, y, z) x quarter = (-y, x, z); then +0.5 on y, then the
    # joint's +1; z reflects once on the way into model space.
    first = {tuple(round(x, 4) for x in v[:3]) for v in g['copies'][0]['vertices']}
    assert first == {(0, 1.5, 0), (-1, 1.5, 0), (0, 1.5, -.2)}, first
    # The turned copies: -pi/36 and +pi/36 about the plug's y before it is placed.
    for c, angle in zip(g['copies'][1:], (-math.pi / 36, math.pi / 36)):
        tip = next(v for v in c['vertices'] if abs(v[3]) < 1e-6 and abs(v[4] - 1) < 1e-6)
        local = [.2 * math.sin(angle), 0, .2 * math.cos(angle)]  # KO (0, 0, 0.2) after RotationY
        expect = [-local[1], local[0] + .5 + 1, -local[2]]
        assert close(tip[:3], expect), (angle, tip, expect)
    # The jitter axis is the first vertex normal (+x) after the plug: KO (0, 1, 0).
    origin, tip = g['jitter']
    assert close([b - a for a, b in zip(origin, tip)], [0, 1, 0]), g['jitter']
    # Box: min (0, 0, 0), extents (0, 1, 0.2) in KO space; tail scale (1 + 0.2) x 0.7.
    assert close(g['tail_box'][0], [0, 1.5, 0]) and close(g['tail_box'][2], [-1, 1.5, 0])
    assert close(g['tail_box'][3], [0, 1.5, -.2]) and abs(g['tail_scale'] - .84) < 1e-6
    # PQ-376: the copies' sort bias is the FX mesh's y extent in mesh units (1).
    assert g['sort_bias'] == 1, g['sort_bias']

    # The cook: three frame textures, the tail clip with the scaled particles.
    spec = dict(fx, key=1, joint=3, ko_item=120110048, geometry=g)
    out = root / 'effects.bin'
    report = ko_fx_bake.cook(assets, dict(clips={}, bindings=[]), out, appearance=[spec], keys=2)
    data = out.read_bytes()
    assert data[:4] == b'N3E5' and report['appearance'][0]['copies'] == 3 and report['appearance'][0]['tails'] == 2
    # PQ-376: the 1298 effect's sort record, the plug origin and the y extent.
    sort = report['appearance'][0]['sort']
    assert close(sort['origin'], g['jitter'][0]) and close(sort['origin'], [0, 1.5, 0]) and sort['bias'] == 1, sort
    passed = subprocess.run([str(CHECK), str(out)], capture_output=True, text=True)
    assert passed.returncode == 0 and 'clips=1 textures=4' in passed.stdout, (passed.stdout, passed.stderr)
    ids = {'fx/glow0000.dxt': 0, 'fx/glow0001.dxt': 1, 'fx/glow0002.dxt': 2, 'fx/spark0000.dxt': 3}
    cooked, _, _ = ko_fx_bake.appearance_effect(assets, ids.__getitem__, spec, 0)
    assert cooked['frames'] == [0, 1, 2] and cooked['flags'] == 455 and cooked['blend'] == [3, 2]
    clip = next(iter(appearance_effects._scan(b'N3EF' + data[4:])[1]))
    assert clip == 'appearance-1-tail'
    # Particle sizes 0.05..0.2 times 0.84 (the bundle's scale flag); unscaled without it.
    entry, key, tail = ko_fx_bake.appearance_effect(assets, lambda name: 0, spec, 0)
    sizes = []
    at = len(string(key)) + 12
    for _ in range(struct.unpack_from('<I', tail, at - 4)[0]):
        batches = struct.unpack_from('<I', tail, at)[0]
        at += 4
        for _ in range(batches):
            n = struct.unpack_from('<I', tail, at + 20)[0]
            at += 24
            for k in range(n):
                sizes.append(struct.unpack_from('<f', tail, at + k * 44 + 12)[0])
            at += n * 44
    assert sizes and min(sizes) >= .05 * .84 - 1e-6 and max(sizes) <= .2 * .84 + 1e-6 and max(sizes) > .2 * .84 * .5
    (root / 'fx/tail.fxb').write_bytes(bundle(particles(), scale=0))
    _, _, unscaled = ko_fx_bake.appearance_effect(assets, lambda name: 0, spec, 0)
    assert unscaled != tail
    # A non-alpha main part (flag 1 clear) draws no FX mesh; its tails still draw.
    (root / 'fx/main.fxb').write_bytes(bundle(billboard(3, 12, 454)))
    entry, _, _ = ko_fx_bake.appearance_effect(assets, lambda name: 0, spec, 0)
    assert entry['copies'] == [] and entry['tails'] == 2 and entry['sort']['bias'] == 1
    # Unsupported families fail the cook: an ending or non-looping main part,
    # a main bundle without a billboard first part, tail particles that outlive
    # half a link.
    for main, tail_bytes in ((bundle(billboard(3, 12, 455, loop=0)), None),
                             (bundle(billboard(3, 12, 455), life=1), None),
                             (bundle(particles()), None),
                             (bundle(billboard(3, 12, 455)), bundle(particles(life=(.1, 1.5)))),
                             # 004840b0 draws a non-alpha part's sparks at once, outside the list.
                             (bundle(billboard(3, 12, 455)), bundle(particles(flags=454)))):
        (root / 'fx/main.fxb').write_bytes(main)
        (root / 'fx/tail.fxb').write_bytes(tail_bytes or bundle(particles()))
        try:
            ko_fx_bake.appearance_effect(assets, lambda name: 0, spec, 0)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted an unsupported weapon effect bundle')
    # The table layout guard: a column of another type refuses the cook.
    tables(root, {1: 'UInt32', 3: 'UInt32', 5: 'Int16', 8: 'Byte', 22: 'Byte', 23: 'Byte', 24: 'Byte', 25: 'Byte'})
    assets = ko_character.Assets(root)
    try:
        w.effect(assets, 120110048)
    except ValueError:
        pass
    else:
        raise AssertionError('accepted a reordered Item_Ext table')

    # The serializer and the client reader refuse malformed sections.
    good = appearance_effects._scan(b'N3EF' + data[4:])
    sound = cooked
    for change in (dict(key=0), dict(key=3), dict(frames=[9]), dict(fps=0), dict(blend=[0, 2]), dict(flags=0x800),
                   dict(copies=[dict(jitter=2, frame_offset=0, vertices=g['copies'][0]['vertices'])]),
                   dict(copies=[dict(jitter=0, frame_offset=3, vertices=g['copies'][0]['vertices'])]),
                   dict(copies=[dict(jitter=0, frame_offset=0, vertices=g['copies'][0]['vertices'][:2])]),
                   dict(tails=2, tail_clip='missing'), dict(tails=0, tail_clip='appearance-1-tail'),
                   dict(tail_steps=200), dict(phase_steps=2000)):
        try:
            appearance_effects.section([{**sound, **change}], good[0], good[1], 2)
        except ValueError:
            pass
        else:
            raise AssertionError(('serialized', change))
    try:
        appearance_effects.section([sound, sound], good[0], good[1], 2)
    except ValueError:
        pass
    else:
        raise AssertionError('serialized a duplicate key')
    section = appearance_effects.section([sound], good[0], good[1], 2)
    # N3E5: the effect section, an empty glow and rule list, one sort record.
    sorts = [dict(key=1, origin=[0, 1.5, 0], bias=1)]
    after = u(0) + u(0) + appearance_effects.sort_section(sorts, [sound])
    assert after == u(0) + u(0) + u(1) + u(1) + f([0, 1.5, 0, 1]) and data.endswith(section + after)
    prefix = data[:len(data) - len(section) - len(after)]
    for bad in ([], [dict(sorts[0], key=2)], sorts * 2, [dict(sorts[0], bias=-1)], [dict(sorts[0], bias=1001)],
                [dict(sorts[0], origin=[0, float('nan'), 0])], [dict(sorts[0], origin=[0, 0])]):
        try:
            appearance_effects.sort_section(bad, [sound])
        except ValueError:
            pass
        else:
            raise AssertionError(('serialized', bad))

    def reader(blob):
        path = root / 'probe.bin'
        path.write_bytes(blob)
        return subprocess.run([str(CHECK), str(path)], capture_output=True, text=True).returncode == 0
    assert reader(data) and reader(b'N3EF' + prefix[4:]) and not reader(b'N3E2' + prefix[4:])  # N3E2 needs its section
    assert reader(b'N3E2' + prefix[4:] + section)  # the same effect without its record
    # PQ-339: an effect with no tails names no tail clip (''), as the 2233
    # skeletal plug's does; the client reads the empty name.
    tailless = appearance_effects.n3e2(b'N3EF' + prefix[4:], [dict(sound, tails=0, tail_clip='')], 2)
    assert reader(tailless) and tailless.endswith(u(0) + u(0) + u(sound['trace_color']))
    body = b'N3E2' + data[4:len(data) - len(after)]
    hostile = [data[:-1], data + b'\0', b'N3E4' + data[4:], body + after]
    # N3E5's sort section: no record, a key with no effect, a duplicate, a
    # negative or too large bias, a NaN origin.
    record = lambda key=1, origin=(0, 1.5, 0), bias=1: u(key) + f(list(origin) + [bias])  # noqa: E731
    head = data[:len(data) - len(after)] + u(0) + u(0)
    for tail_bytes in (u(0), u(1) + record(2), u(2) + record() + record(), u(1) + record(bias=-1),
                       u(1) + record(bias=1001), u(1) + record(origin=(0, float('nan'), 0)), u(17) + record() * 17):
        hostile.append(head + tail_bytes)
    data = body
    count_at = len(prefix)
    hostile.append(prefix + u(17) + section[4:])                         # count bound
    key_at = count_at + 4
    hostile.append(data[:key_at] + u(0) + data[key_at + 4:])             # key 0
    hostile.append(data[:key_at + 4] + u(256) + data[key_at + 8:])       # joint bound
    hostile.append(data[:key_at + 12] + u(99) + data[key_at + 16:])      # frame texture
    fps_at = key_at + 12 + 4 * 3
    hostile.append(data[:fps_at] + pack('f', 0) + data[fps_at + 4:])     # rate
    hostile.append(data[:fps_at] + pack('f', float('nan')) + data[fps_at + 4:])
    flags_at = fps_at + 4 + 8 + 8
    hostile.append(data[:flags_at] + u(0x800) + data[flags_at + 4:])     # flags
    hostile.append(data[:-4 - 4 - len('appearance-1-tail')] + string('missing') + data[-4:])  # tail clip
    for blob in hostile:
        assert not reader(blob), blob[:8]
print('PASS KO weapon effects: 0045ccc0 choice and fallback, 0045cb5e trace colours, item table guard, '
      'FX mesh copies turned +-pi/36 with jitter axis and tail box, tail target scale, unsupported bundles '
      'refused, N3E2 serializer and client reader bounds; N3E5 sort record (plug origin, y extent 1) and its '
      'bounds, a non-alpha tail part refused')
