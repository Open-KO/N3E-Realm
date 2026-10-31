"""PQ-317: the 2233 skeletal weapon plug cook (tools/assetc/ko_chrplug_2145.py)
on original synthetic bytes, and the two ko_character rules it needs.

Checks the .n3chrplug layout as 2233's CN3ChrTypePlug loads it (004499e0:
header, trace, mesh flag and embedded progressive mesh, the .n3chr name, the
texture block only while bytes remain) and its refusals; 0042df00's clip map
and 009b3fc0's hand slot; that the placement is the rigid plug rule n3e already
draws (ko_appearance.plug_transform: plug x joint, height / 1.8); the clip map
rows and model slots from a package's player and skill clips; KO's key sampler
taking the frame whose key index equals the count (1298 00427640, 2233
0044b450) and the 2145 path's character read stopping after the eighth field
(0044a030). PQ-338: the 2233 icon rule (009b3fc0: the Item_Ext icon, else the
Item_Org icon, "%.2d" for item / 10^9 of 1-3), the icon map entries it makes
and their refusals, and the HUD reading 4-byte (A8R8G8B8 / X8R8G8B8) textures
as 0043f090 / 00463180 do. No KO data is read; with --local every .n3chrplug
in the player's 2145 Item pack is read to its last byte, the Azagai row of
games/moradon/skeletal-plugs-2233.json is checked against the 2145 Item_Org
and cooked, and its icon is found in the 2145 UI pack and decoded (SKIP
without the install). PQ-337: rows() for several item numbers of one plug
(the Azagai's grades) with their glow and 0056bb50's weapon effect, on
synthetic tables, and with --local the Azagai's +1 and +10 rows. PQ-339:
weapon_effects() (the main bundle on the plug's FX mesh by the rigid rule, no
tail, PlugSet's trace colour) on synthetic bytes, and with --local the grades'
32120 drawn from the 2145 fx pack with its DXT5 frames.
"""
import json
import math
import pathlib
import struct
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/assetc'))
import ko_appearance  # noqa: E402
import ko_character  # noqa: E402
import ko_chrplug_2145 as k  # noqa: E402
import ko_hud  # noqa: E402
import ko_item_icons  # noqa: E402


def refused(call, text):
    try:
        call()
    except ValueError as error:
        assert text in str(error), (text, str(error))
        return
    raise AssertionError('accepted: ' + text)


def name(text):
    raw = text.encode('ascii') if isinstance(text, str) else text
    return struct.pack('<i', len(raw)) + raw


def pmesh():
    """An original progressive mesh: one triangle, no collapses, no LOD controls."""
    vertices = [(0, 0, 0), (0.1, 0, 0), (0, 0.2, 0)]
    out = name('') + struct.pack('<6i', 0, 0, 3, 3, 3, 3)
    for x, y, z in vertices:
        out += struct.pack('<8f', x, y, z, 0, 0, 1, 0, 0)
    return out + struct.pack('<3H', 0, 1, 2) + struct.pack('<i', 0)


ROTATION = [0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def plug(trace=True, mesh=True, chr_name='chr\\toy.n3chr', block='tail', extra=b''):
    out = name('') + struct.pack('<II', 99, 7) + struct.pack('<3f', 0.1, -0.2, 0.3) + struct.pack('<16f', *ROTATION)
    out += struct.pack('<3f', 0.9, 0.9, 0.9) + struct.pack('<17f', *([1.0] * 4 + [0.0] * 13)) + struct.pack('<6I', 4, 0, 2, 0, 5, 6)
    out += name('') + name('')
    out += struct.pack('<iIff', 3, 0xffffffff, 0.0, 0.0) if trace else struct.pack('<i', 0)
    out += struct.pack('<i', 1) + pmesh() if mesh else struct.pack('<i', 0)
    out += name(chr_name)
    if block == 'tail':
        out += struct.pack('<iI', 1, 0) + b''.join(name('') for _ in range(5))
    elif block == 'empty':
        out += struct.pack('<i', 0)
    return out + extra


def block(count=1, value=0, names=('',) * 5):
    """2233's texture block (004489c0): count, then when 1 or more 4 bytes and five names."""
    out = struct.pack('<i', count)
    return out + (struct.pack('<I', value) + b''.join(name(n) for n in names) if count >= 1 else b'')


def cplug(trace=True, mesh=True, tail=None, end=None):
    """An original rigid .n3cplug: the plug header, trace, mesh flag and FX
    mesh (no .n3chr name), then `tail` (a texture block or other bytes).
    `end` cuts the file after the header ('header') or the trace ('trace')."""
    full = plug(trace=trace, mesh=mesh, chr_name='', block=None)
    # 1298's 00414570 and n3e's reader take the dropped u32 as 0 for an ordinary plug.
    out = name('') + struct.pack('<II', 0, 7) + full[12:-4]  # without the empty .n3chr name
    header = len(out) - (16 if trace else 4) - (4 + len(pmesh()) if mesh else 4)
    if end == 'header':
        return out[:header]
    if end == 'trace':
        return out[:header + (16 if trace else 4)]
    return out + (tail or b'')


class Files:
    """Assets as ko_appearance.read_plug reads them."""

    def __init__(self, **files):
        self.files = {k.replace('_', '/', 1) + '.n3cplug': v for k, v in files.items()}

    def get(self, path):
        return self.files[path]


def ntf(fmt, w=4, h=4, mips=0, texels=None):
    """An original NTF3 texture: header, then 4-byte texels (B, G, R, A)."""
    texels = bytes(range(w * h * 4)) if texels is None else texels
    return name('') + b'NTF\x03' + struct.pack('<4i', w, h, fmt, mips) + texels


class FakeInstall:
    """2145 tables as ko_glow_2233.item reads them: Item_Org and Item_Ext_33."""

    def __init__(self, ext=True):
        org_types = [6, 2, 7, 7, 6, 2, 6, 6] + [2] * 32
        org = [1110532000, 33, 'bow', 'remark', 1, 0, 111042500, 111043200] + [0] * 31 + [1]
        # Columns 16-20 are shorts (damage, delay, range, weight, durability);
        # PQ-416 reads the range (column 18), a synthetic 350 here.
        org_types[15:20] = [3] * 5
        org[17] = 350
        ext_types = [6, 7, 6, 7, 6, 6, 6, 2] + [3] * 36 + [6]
        row = [1000, '', 0, '', 0, 0, 0, 0] + [0] * 37
        # Texts_us.tbl's kind lines (005aa8e0), synthetic stand-ins.
        texts = {n: [n, '[kind %d]' % n] for n in (6811, 6812, 6815, 6816, 6817, 6818)}
        self.tables = {'Data/Item_Org_us.tbl': (org_types, {org[0]: org}),
                       'Data/Item_Ext_33_us.tbl': (ext_types, {1000: row} if ext else {}),
                       'Data/Texts_us.tbl': ([6, 7], texts)}

    def table(self, name):
        return self.tables[name]


def main():
    # 0042df00 over every range (PQ-302's table).
    table = {0: (0, False), 13: (0, False), 14: (1, True), 15: (1, True), 16: (5, True), 25: (5, True),
             26: (1, True), 103: (1, True), 104: (0, False), 106: (0, False), 107: (1, True), 111: (1, True),
             112: (0, False), 135: (0, False), 136: (1, True), 500: (1, True)}
    assert all(k.plug_clip(i) == v for i, v in table.items()), {i: k.plug_clip(i) for i in table}
    assert k.plug_clip(-1) is None
    # 009b3fc0: attach % 100 of 0, 1, 3 is plug slot 0; 2, 4 slot 1; others none.
    assert [k.hand_slot(v) for v in (0, 1, 2, 3, 4, 5, 104, 102, 6)] == [0, 0, 1, 0, 1, None, 1, 1, None]
    print('PASS 0042df00 clip map over every parent range and 009b3fc0 hand slots', flush=True)

    p = k.read(plug())
    assert p['stored_joint'] == 7 and p['scale'] == [struct.unpack('<f', struct.pack('<f', .9))[0]] * 3
    assert p['trace']['read_steps'] == 3 and len(p['fx_mesh']['vertices']) == 3 and p['chr'] == 'chr\\toy.n3chr'
    assert p['textures'] == dict(count=1, value=0, names=[''] * 5)
    # The texture block is read only while bytes remain (00449e43); with count 0
    # no names follow; without a trace no trace values; without the flag no mesh.
    assert k.read(plug(block=None))['textures'] is None and k.read(plug(block='empty'))['textures'] == dict(count=0)
    q = k.read(plug(trace=False, mesh=False))
    assert q['trace'] is None and q['fx_mesh'] is None and q['chr'] == 'chr\\toy.n3chr'
    refused(lambda: k.read(plug(extra=b'\0')), 'bytes after the texture block')
    refused(lambda: k.read(plug(chr_name='')), 'name length 0')
    refused(lambda: k.read(plug(chr_name='x' * 260)), 'name length 260')
    refused(lambda: k.read(plug(chr_name=b'chr\\\x01.n3chr')), 'not printable ASCII')
    refused(lambda: k.read(plug()[:-10]), 'truncated')
    # A mesh flag set with a mesh one byte short: the strict mesh reader or the
    # field after it fails, never a silent shift.
    broken = plug(block=None)
    at = broken.index(pmesh())
    try:
        k.read(broken[:at] + pmesh()[:-1] + broken[at + len(pmesh()):])
    except ValueError:
        pass
    else:
        raise AssertionError('a short embedded mesh was accepted')
    print('PASS 004499e0 layout: header, trace, embedded FX mesh, .n3chr name, optional texture block, and '
          'trailing, empty, long, unprintable, truncated and mis-sized fields refused', flush=True)

    # PQ-334: the 2145 rigid plug (2233 CN3CPlug 004489c0 / 00448d80) has
    # the same texture block after its FX mesh; 1298's 00415020 has none.
    files = Files(Item_tail=cplug(tail=block()), Item_none=cplug(), Item_nomesh=cplug(mesh=False, tail=block()),
                  Item_empty=cplug(tail=block(0)), Item_negative=cplug(tail=block(-1)),
                  Item_header=cplug(end='header'), Item_trace=cplug(end='trace'),
                  Item_long=cplug(tail=block(names=('', 'x' * 259, '', '', ''))))
    new = ko_appearance.read_plug(files, 'Item/tail.n3cplug', '2145')
    assert new['fx_data'] == pmesh() and new['textures'] == dict(count=1, value=0, names=[''] * 5), new
    assert new['trace']['read_steps'] == 3 and 'steps' not in new['trace'] and new['stored_joint'] == 7
    assert len(k.ko.import_mesh(None, 1.0, data=new['fx_data'])['vertices']) == 3
    # The 1298 layout keeps the block inside the FX mesh bytes, so the mesh
    # reader refuses it (PQ-302's finding); without a mesh it is trailing data.
    old = ko_appearance.read_plug(files, 'Item/tail.n3cplug')
    assert old['fx_data'] == pmesh() + block() and 'textures' not in old
    refused(lambda: k.ko.import_mesh(None, 1.0, data=old['fx_data']), 'KO trailing variant')
    refused(lambda: ko_appearance.read_plug(files, 'Item/nomesh.n3cplug'), 'plug trailing data')
    nomesh = ko_appearance.read_plug(files, 'Item/nomesh.n3cplug', '2145')
    assert nomesh['fx_data'] is None and nomesh['textures']['count'] == 1
    # Without a block both layouts read the same fields (every 1298 plug).
    a, b = (ko_appearance.read_plug(files, 'Item/none.n3cplug', layout) for layout in ('1298', '2145'))
    assert b['textures'] is None and a['fx_data'] == b['fx_data'] == pmesh() and a['trace']['steps'] == 3
    assert all(a[f] == b[f] for f in ('stored_joint', 'position', 'rotation', 'scale', 'material', 'mesh', 'texture',
                                      'fx_bytes'))
    # Count 0 or below: nothing follows (CMP [count],1 / JL, 00448bc1). A file
    # ending after the header or the trace reads as in 1298: no FX mesh, no block.
    assert ko_appearance.read_plug(files, 'Item/empty.n3cplug', '2145')['textures'] == dict(count=0)
    assert ko_appearance.read_plug(files, 'Item/negative.n3cplug', '2145')['textures'] == dict(count=-1)
    for short in ('header', 'trace'):
        q = ko_appearance.read_plug(files, 'Item/%s.n3cplug' % short, '2145')
        assert q['fx_data'] is None and q['textures'] is None and (q['trace'] is None) == (short == 'header'), q
    assert ko_appearance.read_plug(files, 'Item/long.n3cplug', '2145')['textures']['names'][1] == 'x' * 259
    bad = dict(extra=(cplug(tail=block() + b'\0'), 'bytes after the texture block'),
               partial=(cplug(tail=b'\1\0'), 'texture block truncated'),
               cut=(cplug(tail=block()[:-2]), 'texture block truncated'),
               over=(cplug(tail=block(names=('x' * 260, '', '', '', ''))), 'trace texture name length 260'),
               minus=(cplug(tail=block()[:8] + struct.pack('<i', -1) + block()[12:]), 'trace texture name length -1'),
               binary=(cplug(tail=block(names=('', '', b'a\x01b', '', ''))), 'not printable ASCII'),
               mesh=(cplug(tail=block())[:-(len(block()) + 1)] + block(), 'FX mesh'))
    for key, (data, text) in bad.items():
        refused(lambda: ko_appearance.read_plug(Files(Item_bad=data), 'Item/bad.n3cplug', '2145'), text)
    refused(lambda: ko_appearance.read_plug(files, 'Item/tail.n3cplug', '2233'), 'plug layout')
    # A trace texture or a +0x2cc value stays out of packages until PQ-335:
    # the FX mesh path (ko_weapon_fx.geometry) and the skeletal plug cook refuse it.
    ko_appearance.default_traces(None, 'x')
    ko_appearance.default_traces(dict(count=0), 'x')
    ko_appearance.default_traces(dict(count=1, value=0, names=[''] * 5), 'x')
    import ko_weapon_fx
    bind = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
    named = Files(Item_fire=cplug(tail=block(names=('item\\fire_trace.dxt', '', '', '', ''))),
                  Item_value=cplug(tail=block(value=1)), Item_tail=cplug(tail=block()))
    g = ko_weapon_fx.geometry(named, 'Item/tail.n3cplug', 3, bind, 1.8, '2145')
    assert g['fx_vertices'] == 3 and g['fx_triangles'] == 1 and len(g['copies']) == 3, g
    refused(lambda: ko_weapon_fx.geometry(named, 'Item/tail.n3cplug', 3, bind, 1.8), 'KO trailing variant')
    for stem in ('fire', 'value'):
        refused(lambda: ko_weapon_fx.geometry(named, 'Item/%s.n3cplug' % stem, 3, bind, 1.8, '2145'), 'PQ-335')

    class Pack:
        def __init__(self, install):
            self.sources = {}

        def get(self, path):
            assert path == 'Item\\fire.n3chrplug', path
            return plug(mesh=False, block=None) + block(names=('', 'item\\fire_trace.dxt', '', '', ''))
    real = k.Source
    k.Source = Pack
    try:
        refused(lambda: k.cook(dict(chrplug_2145='Item/fire.n3chrplug'), player=None, skills=None, height=1.7,
                               root=None, work=None, install=object()), 'PQ-335')
    finally:
        k.Source = real
    print('PASS 004489c0 layout (PQ-334): the 2145 rigid plug\'s texture block after its FX mesh read only while '
          'bytes remain, the FX mesh exact so the mesh reader takes it (the 1298 layout keeps the block inside it '
          'and is refused as before), count 0 or below ends it, early-ending files as in 1298, without a block both '
          'layouts equal; trailing, partial, long, negative, unprintable and mis-sized fields refused; a trace '
          'texture or +0x2cc value refused by the FX mesh path and the skeletal plug cook', flush=True)

    # The placement is n3e's rigid plug rule at the joint (004133c0, 004137d0,
    # 00574830's height / 1.8): the same point lands at the same place.
    height = 1.7
    rows, factor = k.placement(p, height)
    rule, rule_factor = ko_appearance.plug_transform(p, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], height)
    assert abs(factor - rule_factor) < 1e-9 and abs(factor - height / 1.8 * p['scale'][1]) < 1e-9
    for v in ([0.0, 0.0, 0.0], [0.3, -0.1, 0.25], [-1.0, 2.0, 0.5]):
        ours = [sum(rows[r * 4 + c] * v[c] for c in range(3)) + rows[r * 4 + 3] for r in range(3)]
        assert all(abs(a - b) < 1e-9 for a, b in zip(ours, rule(v, True))), (v, ours, rule(v, True))
    refused(lambda: k.placement(dict(p, scale=[0.9, 0.0, 0.9]), height), 'scale')
    print('PASS the placement is the rigid plug rule at the joint (factor %.4f)' % factor, flush=True)

    # The clip map from a package's clips: Moradon's states, two combat clips
    # and two skill animations (KO 17 and 16).
    player = dict(states={'idle': 0, 'walk': 1, 'attack': 87, 'death': 8, 'run': 2, 'backward': 3, 'ready': 86,
                          'sit-down': 11, 'sit-idle': 12, 'stand-up': 13}, combat=[14, 32])
    rows_, slots = k.clip_map(6, player, {0: 17, 1: 16})
    assert slots == [0, 1, 5, 0], slots
    by = {(r['kind'], r['id']): (r['slot'], r['once']) for r in rows_}
    assert by == {**{('state', s): (0, False) for s in (0, 1, 3, 4, 5, 7, 8, 9)}, ('state', 2): (1, True),
                  ('state', 6): (1, True), ('combat', 0): (1, True), ('combat', 1): (1, True),
                  ('skill', 0): (2, True), ('skill', 1): (2, True)}, by
    # A plug clip past the character's table gets no row (00432760 ignores it).
    rows_, slots = k.clip_map(2, player, {0: 17})
    assert slots == [0, 1, 0, 0] and ('skill', 0) not in {(r['kind'], r['id']) for r in rows_}, (rows_, slots)
    print('PASS the clip map: breath for every basic state, attackbreath once for attack, ready and combat clips, '
          'magic once for the skills, slot 0 the plug\'s clip 0, and no row past the clip table', flush=True)

    # KO's key sampler: index trunc(frame x rate / 30) up to the count is a key
    # (the last one at the count); past it the reader refuses.
    key = dict(rate=15.0, kind=0, values=[[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0]])
    assert ko_character.sample(key, 4.0, None) == [2.0, 0, 0]  # index 2 (the last key)
    assert ko_character.sample(key, 5.0, None) == [2.0, 0, 0]  # index 2.5: key 2 toward the copied last key
    assert ko_character.sample(key, 6.0, None) == [2.0, 0, 0]  # index 3 = the count: the last key
    assert ko_character.sample(key, 7.9, None) == [2.0, 0, 0]  # index 3.95, still 3
    refused(lambda: ko_character.sample(key, 8.0, None), 'clip outside key range')  # index 4
    assert ko_character.sample(key, 1.0, None) == [0.5, 0, 0]
    # The 2145 path reads a character to its eighth field and reports the rest.
    character = (name('toy') + struct.pack('<3f', 0, 0, 0) + struct.pack('<4f', 0, 0, 0, 1)
                 + struct.pack('<3f', 1, 1, 1) + struct.pack('<iii', 0, 0, 0) + name('') + name('')
                 + name('chr\\toy.n3joint') + struct.pack('<i', 1) + name('item\\toy.n3cpart') + struct.pack('<i', 0)
                 + name('chr\\toy.n3anim') + struct.pack('<4i', -1, -1, -1, -1) + name('') + name(''))
    read = ko_character.character(character + b'rest', strict=False, trailing=True)
    assert read['unread'] == 4 and read['joint'] == 'chr\\toy.n3joint' and read['parts'] == ['item\\toy.n3cpart']
    assert 'unread' not in ko_character.character(character)
    refused(lambda: ko_character.character(character + b'rest'), 'trailing')
    print('PASS the key sampler takes the frame whose key index equals the count as the last key and refuses '
          'past it; the 2145 character read stops after its eighth field', flush=True)

    # 2233 009b3fc0: no icon at item / 10^9 of 4 or more; the extension's icon
    # when non-zero; "%.2d" for item / 10^9 of 1-3, else "%.1d" (1298's rule).
    assert ko_item_icons.path_2233(1110532000, 111043200) == 'UI/ItemIcon_11_1043_20_0.dxt'
    assert ko_item_icons.path_2233(1110532000, 51043200) == 'UI/ItemIcon_05_1043_20_0.dxt'
    assert ko_item_icons.path_2233(3110532000, 51043200, 61234560) == 'UI/ItemIcon_06_1234_56_0.dxt'
    assert ko_item_icons.path_2233(110532000, 51043200) == ko_item_icons.path(51043200) == 'UI/ItemIcon_5_1043_20_0.dxt'
    for bad in (4110532000, 0, -1, True, 2 ** 32):
        refused(lambda: ko_item_icons.path_2233(bad, 51043200), '2233 item icon number')
    refused(lambda: ko_item_icons.path_2233(1110532000, -1), 'item icon ID')

    class Pack:
        namespace = '2145'

        def get(self, path):
            assert path == 'UI/ItemIcon_05_1043_20_0.dxt', path
            return b'original 2145 icon fixture'

    class Client:
        def get(self, path):
            assert path == 'UI/ItemIcon_1_2345_67_8.dxt', path
            return b'original client icon fixture'
    drawn = []
    tex = lambda path, source=None: drawn.append((path, source)) or len(drawn) - 1  # noqa: E731
    pack = Pack()
    icons, sources = ko_item_icons.cook(Client(), tex, {
        'demo:item/bow': dict(base=51043200, extension=0, item_2233=1110532000, assets=pack),
        'demo:item/sword': dict(base=12345678, extension=0)})
    assert icons == [('demo:item/bow', 0, (0, 0, 45 / 64, 45 / 64)), ('demo:item/sword', 1, (0, 0, 45 / 64, 45 / 64))]
    assert drawn == [('UI/ItemIcon_05_1043_20_0.dxt', pack), ('UI/ItemIcon_1_2345_67_8.dxt', None)], drawn
    assert [(x['path'], x.get('rule'), x.get('assets')) for x in sources] == [
        ('UI/ItemIcon_05_1043_20_0.dxt', '009b3fc0', '2145'), ('UI/ItemIcon_1_2345_67_8.dxt', None, None)], sources
    for bad in (dict(base=1, extension=0, item_2233=1110532000, assets=Client()),
                dict(base=1, extension=0, item_2233=1110532000),
                dict(base=1, extension=0, assets=pack), dict(base=1, extension=0, rule='009b3fc0')):
        refused(lambda: ko_item_icons.cook(Client(), tex, {'demo:item/bow': bad}), 'item icon vocabulary')
    # icons(): the 2145 rows' icon (Item_Org column 8, Item_Ext column 7).
    items = {'demo:item/bow': ('bow', dict(item_2145=1110532000))}
    refused(lambda: k.icons({'demo:item/bow': dict(base=1, extension=0)}, items, FakeInstall()), 'already has')
    refused(lambda: k.icons({}, items, FakeInstall(ext=False)), 'no Item_Ext_33 row 1000')
    print('PASS 009b3fc0 icon rule ("%.2d" for item / 10^9 of 1-3, the extension icon first, none at 4 and up); '
          'icon map entries from a 2145 pack keep their own source; bad vocabularies, an item already drawn and '
          'an item without an extension row refused', flush=True)

    # PQ-337: rows() for several item numbers of one plug file (the Azagai's
    # grades), each reaching its own Item_Ext row by 2233's rule; a row of
    # attribute 11 or 12 glows as its own item; the label is the extension's
    # name when it has one; effect() is 0056bb50's id (Item_Org column 26 /
    # 1000; a staff adds 0, 10 or 20 by its largest element; another class
    # needs Item_Ext column 3 = 0), else Item_Ext column 5, then fx.tbl.
    fake = FakeInstall()
    org_types, orgs = fake.tables['Data/Item_Org_us.tbl']
    org_types[k.ORG_CLASS], org_types[k.ORG_EFFECT] = 2, 6
    orgs[1110532000][k.ORG_ATTACH] = 4  # the Azagai's attach point: plug slot 1
    ext_types, exts = fake.tables['Data/Item_Ext_33_us.tbl']
    ext_types[k.EXT_FIRE:k.EXT_FIRE + 4] = [2, 2, 2, 2]

    def ext(key, label, attribute, mode, effect=0, base=1110532000, elements=(0, 0, 0, 0), bonus=(0, 0)):
        row = [key, label, base, ''] + [0] * 41
        row[4], row[7], row[44] = effect, attribute, mode
        row[k.EXT_DAMAGE], row[k.EXT_DURABILITY] = bonus  # PQ-434: Item_Ext columns 9 and 13
        row[k.EXT_FIRE:k.EXT_FIRE + len(elements)] = elements
        return row
    exts.update({1501: ext(1501, 'bow(+1)', 12, 1, 32120, bonus=(32, 6000)),
                 1510: ext(1510, 'bow(+10)', 12, 10, 32120, bonus=(47, 7000)),
                 1511: ext(1511, '', 11, 11, 32120), 1520: ext(1520, 'bow(+20)', 4, 20, 32120),
                 1530: ext(1530, 'bow(+30)', 12, 30, 32120, base=0, elements=(0, 0, 0, 9)),
                 1540: ext(1540, 'staff', 12, 0, 32120, base=0, elements=(5, 9, 7)),
                 1541: ext(1541, 'staff', 12, 0, 32120, base=0, elements=(5, 9, 12)),
                 1542: ext(1542, 'staff', 12, 0, 32120, base=0)})
    fake.tables[k.FX_TABLE] = ([6, 7, 7, 6, 2, 2], {i: [i, '', 'fx\\e%d.fxb' % i, 0, 0, 0] for i in
                                                     (32120, 32121, 12, 22, 32)})

    # An original synthetic 2233 bundle (0057f0b0): version 6, no parts, the
    # trailing fields of versions 2-6 (ko_fx's 2233 layout reads it).
    bundle = struct.pack('<iffB', 6, 0, 0, 0) + struct.pack('<26i', *[0] * 26) + struct.pack('<BBIIBBB', *[0] * 7)
    fx_mesh = [True]

    class Bundles:
        namespace = '2145'

        def __init__(self, install, pack='Item'):
            self.pack, self.sources = pack, {}

        def get(self, name):
            if self.pack == 'Item':
                assert name == 'Item\\11_1042_50_0.n3chrplug', name
                return plug(mesh=fx_mesh[0])
            assert self.pack == 'fx' and name.startswith('fx\\e'), name
            return bundle
    real_source, k.Source = k.Source, Bundles
    try:
        with tempfile.TemporaryDirectory() as tmp:
            spec = dict(items=[dict(id='demo:item/bow%s' % n, ko_2145_item=1110532000 + n,
                                    source='Item/11_1042_50_0.n3chrplug', slot=1, joint=7, group=0)
                               for n in (0, 501, 510, 511, 520)])
            definition = pathlib.Path(tmp) / 'plugs.json'
            definition.write_text(json.dumps(spec))
            rows_, items = k.rows(fake, definition)
            assert [r.get('glow_2145_item') for r in rows_] == [None, 1110532501, 1110532510, 1110532511, None], rows_
            # PQ-434 (D-221): each grade carries its own Item_Ext row's attack
            # and durability bonuses (columns 9 and 13) beside the Item_Org
            # base's damage and durability; columns that are not shorts are
            # refused.
            assert [(x['damage'], x['damage_bonus'], x['durability'], x['durability_bonus'])
                    for _, x in items.values()] == [(0, 0, 0, 0), (0, 32, 0, 6000), (0, 47, 0, 7000), (0, 0, 0, 0),
                                                    (0, 0, 0, 0)], items
            for column in (k.EXT_DAMAGE, k.EXT_DURABILITY):
                ext_types[column] = 2
                refused(lambda: k.rows(fake, definition), 'columns 9 and 13 (the attack and durability bonuses)')
                ext_types[column] = 3
            # PQ-350: 005aa8e0's name (the Item_Ext name for attributes 4 and
            # 12, the Item_Org name and "(+column 45)" for 11) and kind line;
            # PQ-354: the label is the name, the kind line the N3IH head's line
            # in the attribute's colour (attribute 0 white, 4 dcc77c, 11
            # ff83a6, 12 ffad4d).
            assert [label for label, _ in items.values()] == [
                'bow', 'bow(+1)', 'bow(+10)', 'bow(+11)', 'bow(+20)'], items
            assert [x['kind_text'] for _, x in items.values()] == [None, 6816, 6816, 6817, 6811], items
            assert [x['head'] for _, x in items.values()] == [
                dict(name_color=0xffffff, lines=[])] + [
                dict(name_color=c, lines=[dict(text='[kind %d]' % n, color=c)])
                for n, c in ((6816, 0xffad4d), (6816, 0xffad4d), (6817, 0xff83a6), (6811, 0xdcc77c))], items
            # add_items() puts each head into the package's N3IH heads, whose
            # token is 2233's "<selfname>".
            manifest = dict(inventory=dict(items=[]), equipment=dict(items=[]), commerce=dict(items=[]),
                            wear=dict(items=[]), stats=dict(items=[]))
            k.add_items(manifest, items, {i: 1 for i in items})
            assert manifest['item_heads']['self_token'] == '<selfname>'
            assert [(h['item'], h['name_color'], h['lines']) for h in manifest['item_heads']['items']] == [
                (i, x['head']['name_color'], x['head']['lines']) for i, (_, x) in items.items()], manifest
            # A set item (need race 101-199) takes 6815 / 6818 and the set
            # colours (d20000, ff83a6 for 11); a kind text the table lacks is
            # refused.
            orgs[1110532000][13] = 124
            assert [x['head'] for _, x in k.rows(fake, definition)[1].values()][1:4] == [
                dict(name_color=c, lines=[dict(text='[kind %d]' % n, color=c)])
                for n, c in ((6815, 0xd20000), (6815, 0xd20000), (6818, 0xff83a6))]
            del fake.tables['Data/Texts_us.tbl'][1][6815]
            refused(lambda: k.rows(fake, definition), "no Data/Texts_us.tbl row 6815 (005aa8e0's kind line)")
            fake.tables['Data/Texts_us.tbl'][1][6815] = [6815, '[kind 6815]']
            orgs[1110532000][13] = 0
            assert [x['glow'] for _, x in items.values()] == [None, dict(wave=1, modulate=1), dict(wave=0, modulate=1),
                                                              dict(wave=1, modulate=2), None], items
            assert items['demo:item/bow0'][1]['effect'] is None  # row 1000: no effect id, fx.tbl has no 0 or 1
            effect = items['demo:item/bow510'][1]['effect']
            assert (effect['main_id'], effect['main']['file'], effect['tail']['file'], effect['main']['version'],
                    effect['main']['parts'], effect['main']['unread'], effect['trace_color'], effect['drawn']) == (
                32120, 'fx\\e32120.fxb', 'fx\\e32121.fxb', 6, [], 0, 'ffffffff', False), effect
            # PQ-339: weapon_effects() puts the main bundle on the plug's FX
            # mesh at the plug placement on the row's bind joint (the rigid
            # rule), key = the row's place in the mappings; PQ-341: and its
            # tail (fx.tbl id + 1), drawn by ko_fx_tail_2233.
            import ko_weapon_fx
            world = [[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]] * 6 + [[[0, 0, 1, .1], [0, 1, 0, 1.2], [-1, 0, 0, .3]]] * 2
            mappings = [dict(item='demo:item/blade', slot=0, joint=3, source='Item/x.n3cplug')] + rows_
            specs, report = k.weapon_effects(mappings, items, world, 1.8, fake)
            assert [(s['key'], s['ko_item'], s['joint'], s['layout'], s['main'], s['tail'], s['tail_id'],
                     s['trace_color']) for s in specs] == [
                (3, 1110532501, 7, '2233', 'fx\\e32120.fxb', 'fx\\e32121.fxb', 32121, 0xffffffff),
                (4, 1110532510, 7, '2233', 'fx\\e32120.fxb', 'fx\\e32121.fxb', 32121, 0xffffffff),
                (5, 1110532511, 7, '2233', 'fx\\e32120.fxb', 'fx\\e32121.fxb', 32121, 0xffffffff),
                (6, 1110532520, 7, '2233', 'fx\\e32120.fxb', 'fx\\e32121.fxb', 32121, 0xffffffff)], specs
            read = k.read(plug())
            assert specs[0]['geometry'] == ko_weapon_fx.placed(read, read['fx_mesh'], world[7], 1.8), specs[0]
            assert specs[0]['geometry']['fx_triangles'] == 1 and len(specs[0]['geometry']['copies']) == 3
            assert effect['drawn'] == dict(main=True, tail=True) and effect['reason'] is None, effect
            assert [(e['key'], e['tail'], e['tail_drawn']) for e in report['effects']] == [
                (k_, 'fx\\e32121.fxb', True) for k_ in (3, 4, 5, 6)], report
            # 004304c0 draws nothing without the FX mesh.
            fx_mesh[0] = False
            rows_, items = k.rows(fake, definition)
            specs, report = k.weapon_effects([mappings[0]] + rows_, items, world, 1.8, fake)
            assert specs == [] and items['demo:item/bow510'][1]['effect']['drawn'] is False, specs
            fx_mesh[0] = True
            rows_, items = k.rows(fake, definition)
            refused(lambda: k.weapon_effects(rows_, items, world[:7], 1.8, fake), 'skeletal plug joint 7')
            # PlugSet's trace colour (00574830): attribute 4, 6, 11 or 12 with an
            # element, or an element above 63; fire, ice, lightning, poison.
            assert k.effect(fake, 1110532530)['trace_color'] == 'ffff00ff'
            assert [k.trace_color(*a) for a in [(12, (0, 0, 0, 9)), (0, (0, 0, 0, 64)), (0, (5, 0, 0, 0)),
                                                 (4, (0, 3, 2, 0)), (6, (0, 0, 7, 0)), (1, (64, 64, 0, 0))]] == [
                0xffff00ff, 0xffff00ff, 0xffffffff, 0xffb4c8ff, 0xff1e96f0, 0xffffff00]
            # 0056bb50: the Item_Org base (12) only for a row whose column 3 is 0,
            # and for a staff (class 110) by its largest element.
            orgs[1110532000][k.ORG_EFFECT] = 12000
            assert k.effect(fake, 1110532510)['main_id'] == 32120  # column 3 names the base: column 5
            assert k.effect(fake, 1110532530)['main_id'] == 12
            orgs[1110532000][k.ORG_CLASS] = 110
            assert [k.effect(fake, 1110532000 + n)['main_id'] for n in (540, 541)] == [22, 32], 'staff'
            assert k.effect(fake, 1110532542)['main_id'] == 32120  # a staff with no element: column 5
            spec['items'][1]['ko_2145_item'] = 1110532999
            definition.write_text(json.dumps(spec))
            refused(lambda: k.rows(fake, definition), 'no Item_Ext_33 row 1999')
    finally:
        k.Source = real_source
    print('PASS rows() for several item numbers of one plug (PQ-337): each reaches its own Item_Ext row, attribute '
          '11/12 rows glow as their own item at their column 45 step, 005aa8e0\'s name and kind line (PQ-350) label the grade; '
          'effect() is 0056bb50\'s id (Item_Org column 26 / 1000 with column 3 = 0, a staff by its largest '
          'element), else Item_Ext column 5, named from fx.tbl and read with ko_fx\'s 2233 layout; PQ-339: '
          'weapon_effects() puts the main bundle on the .n3chrplug\'s FX mesh by the rigid rule on the row\'s '
          'key and joint (none without an FX mesh), with PlugSet\'s trace colour; PQ-341: and its tail (fx.tbl id + 1)', flush=True)

    # PQ-347: combat_rows() gives a kind 70 bow worn alone in the left hand the
    # profile named 'bow', checked against 1298's rules (1298 client 0045bfe0
    # ready 92; 1298 client 004659b0 the class's archery row: its start animation, cast x 100 + 150 ms).
    def skill_csv(rows):
        head = ','.join('"%d - Int32"' % (i + 1) for i in range(30))
        return '﻿' + head + '\n' + ''.join(','.join('"%s"' % v for v in r) + '\n' for r in rows)

    def archery(ident, animation=26, cast=13):
        r = [0] * 30
        r[0], r[1], r[k.SKILL_ANIMATION], r[k.SKILL_CAST] = ident, 'Archery', animation, cast
        return r

    gear_slots = ['Right hand', 'Left hand', 'Right ring']
    config = dict(slots=[0, 1], profiles=[dict(name='unarmed', ready=86, attacks=[87, 88], interval_ms=1000, moving=15),
                                          dict(name='bow', ready=92, attacks=[26], interval_ms=1450, moving=26)])
    bows = {'demo:item/bow_a': ('A', dict(kind=70)), 'demo:item/bow_b': ('B', dict(kind=70))}
    slot_of = {'demo:item/bow_a': 1, 'demo:item/bow_b': 1}
    table = skill_csv([archery(108003), archery(102003, cast=20)])
    rows_, report = k.combat_rows(config, gear_slots, bows, slot_of, table.lstrip('﻿'), 108)
    assert rows_ == [dict(items=[None, 'demo:item/bow_a'], profile=2), dict(items=[None, 'demo:item/bow_b'], profile=2)]
    assert (report['skill'], report['animation'], report['cast_tenths']) == (108003, 26, 13), report
    # The class picks the row: 102003's cast 2.0 s needs a 2150 ms profile.
    refused(lambda: k.combat_rows(config, gear_slots, bows, slot_of, table, 102), "is not 1298's")
    slow = dict(config, profiles=[config['profiles'][0], dict(config['profiles'][1], interval_ms=2150)])
    assert k.combat_rows(slow, gear_slots, bows, slot_of, table, 102)[0] == rows_
    for klass in (104, 0, 103):
        refused(lambda: k.combat_rows(config, gear_slots, bows, slot_of, table, klass), 'no archery skill')
    refused(lambda: k.combat_rows(config, gear_slots, bows, slot_of, table, 107), 'no archery row 107003')
    for wrong in (dict(ready=86), dict(attacks=[27]), dict(moving=15), dict(interval_ms=1300)):
        bad = dict(config, profiles=[config['profiles'][0], dict(config['profiles'][1], **wrong)])
        refused(lambda: k.combat_rows(bad, gear_slots, bows, slot_of, table, 108), "is not 1298's")
    refused(lambda: k.combat_rows(dict(config, profiles=config['profiles'][:1]), gear_slots, bows, slot_of, table, 108),
            "one profile named 'bow'")
    refused(lambda: k.combat_rows(config, gear_slots, bows, slot_of, skill_csv([archery(108003, animation=27)]), 108),
            "is not 1298's")
    for kind in (80, 71, 100, 21):  # a long bow, a crossbow, a launcher, a sword
        refused(lambda: k.combat_rows(config, gear_slots, {'demo:item/bow_a': ('A', dict(kind=kind))}, slot_of, table,
                                      108), 'only a kind 70 bow')
    refused(lambda: k.combat_rows(config, gear_slots, bows, {'demo:item/bow_a': 0, 'demo:item/bow_b': 1}, table, 108),
            'not the left hand')
    refused(lambda: k.combat_rows(dict(config, slots=[1]), gear_slots, bows, slot_of, table, 108), 'both hands')
    refused(lambda: k.combat_rows(config, ['Left hand', 'Right ring'], bows, slot_of, table, 108), 'both hands')
    # PQ-416 (D-216): ranged_attack() makes that profile a ranged basic attack
    # (1298 client 00583780 for a type-2 row: (item +0x4a x 0.1 + both radii +
    # 1.0 + 1.0) x add range / 100, text 0xfa9; 00468620 for the click walk).
    def type2_csv(rows):
        return '"1 - UInt32","2 - Int32","3 - Int32","4 - Int32","5 - Int32","6 - Int32"\n' + ''.join(
            ','.join('"%s"' % v for v in r) + '\n' for r in rows)
    texts = '"1 - UInt32","2 - String"\n"4009","Skill Failed - Too far"\n"4010","other"\n'
    typed = archery(108003)
    typed[k.SKILL_TYPES[0]] = 2
    shots = skill_csv([typed])
    longbows = {n: ('A', dict(kind=70, range=400)) for n in bows}
    value, about = k.ranged_attack(longbows, 2, 108003, shots, type2_csv([[108003, 0, 100, 0, 100, 1]]), texts)
    # PQ-467 (D-233): and the hold, Ebenezer's Type1 2 bound (004c1dbe:
    # dx^2 + dz^2 <= (+0x3e / 10)^2 + 1000.0) as a ground-plane distance.
    hold = dict(distance=math.sqrt(40 ** 2 + 1000), plane='xz')
    assert value == dict(profiles=[dict(profile=2, reach=40.0, range=42.0, cast_ms=1300, hold=hold)],
                         notice='Skill Failed - Too far'), value
    assert 50.99 < hold['distance'] < 51.0
    # The range column is divided by 10 in integers first: 355 is 35 m.
    assert k.archery_hold(355) == dict(distance=math.sqrt(35 ** 2 + 1000), plane='xz')
    assert (about['item_range'], about['add_range'], about['text']) == (400, 100, 4009), about
    second = archery(108003)
    second[k.SKILL_TYPES[1]] = 2  # either type column (+0x8c or +0x90) may be 2
    assert k.ranged_attack(longbows, 2, 108003, skill_csv([second]), type2_csv([[108003, 0, 100, 0, 100, 1]]),
                           texts)[0] == value
    mixed = {'demo:item/bow_a': ('A', dict(kind=70, range=400)), 'demo:item/bow_b': ('B', dict(kind=70, range=350))}
    refused(lambda: k.ranged_attack(mixed, 2, 108003, shots, type2_csv([[108003, 0, 100, 0, 100, 1]]), texts),
            'do not share one range')
    for bad in (0, 981):
        refused(lambda: k.ranged_attack({n: ('A', dict(kind=70, range=bad)) for n in bows}, 2, 108003, shots,
                                        type2_csv([[108003, 0, 100, 0, 100, 1]]), texts), 'one range in 1..980')
    refused(lambda: k.ranged_attack(longbows, 2, 108003, table, type2_csv([[108003, 0, 100, 0, 100, 1]]), texts),
            'not a type-2 skill')
    ranged_row = archery(108003)
    ranged_row[k.SKILL_TYPES[0]], ranged_row[k.SKILL_RANGE] = 2, 20
    refused(lambda: k.ranged_attack(longbows, 2, 108003, skill_csv([ranged_row]), type2_csv([[108003, 0, 100, 0, 100, 1]]),
                                    texts), 'its own range')
    for rows2 in ([[108003, 0, 100, 0, 150, 1]], [[102003, 0, 100, 0, 100, 1]]):
        refused(lambda: k.ranged_attack(longbows, 2, 108003, shots, type2_csv(rows2), texts), 'add range of 100')
    # PQ-420 (D-217): the cast time becomes cast_ms; 00461ab0 stretches only above 0.1 s.
    for tenths in (1, 0, 101):
        slow = archery(108003, cast=tenths)
        slow[k.SKILL_TYPES[0]] = 2
        refused(lambda: k.ranged_attack(longbows, 2, 108003, skill_csv([slow]), type2_csv([[108003, 0, 100, 0, 100, 1]]),
                                        texts), 'cast time')
    for bad_texts in ('"1 - UInt32","2 - String"\n"4010","other"\n', '"1 - UInt32","2 - String"\n"4009","%s too far"\n'):
        refused(lambda: k.ranged_attack(longbows, 2, 108003, shots, type2_csv([[108003, 0, 100, 0, 100, 1]]), bad_texts),
                'no plain text 4009')
    # PQ-421 (D-218): arrows() from the archery row's need item (+0x70, 7 =
    # kind 70 / 10) and exhaust item (+0x74, 391010000), its type-2 arrow
    # count (+0x14) and the Item_Org row of that arrow (countable kind 120),
    # with 1298's text 4007 (1298 client 0057f7f0; Ebenezer 0046f3f1, 004b0792).
    def armed(need=7, exhaust=391010000):
        r = archery(108003)
        r[k.SKILL_TYPES[0]], r[k.SKILL_NEED_ITEM], r[k.SKILL_EXHAUST_ITEM] = 2, need, exhaust
        return skill_csv([r])

    def org_row(kind=120, countable=1, weight=0, price=1, ident=391010000):
        r = ['0'] * 37
        r[0], r[1], r[2], r[7], r[k.ORG_KIND_1298], r[k.ORG_WEIGHT], r[k.ORG_PRICE], r[k.ORG_COUNTABLE] = (
            str(ident), '22', 'Arrow', '39101000', str(kind), str(weight), str(price), str(countable))
        return r
    notices = texts + '"4007","Skill Failed - Not enough item"\n'
    one = type2_csv([[108003, 0, 100, 0, 100, 1]])
    item, sale, icon, ammo, notice, about = k.arrows('demo:item/arrow', 108003, armed(), one, [org_row()], notices, 100)
    assert item == dict(id='demo:item/arrow', label='Arrow', stack_limit=9999, durability=0, starting=100), item
    assert (sale, icon, ammo, notice) == (dict(id='demo:item/arrow', weight=0, price=1, sell_divisor=6),
                                          dict(base=39101000, extension=0), dict(item='demo:item/arrow', count=1),
                                          'Skill Failed - Not enough item'), (sale, icon, ammo, notice)
    assert (about['need_item'], about['exhaust_item'], about['arrows_per_shot'], about['text']) == (7, 391010000, 1, 4007)
    assert k.arrows('demo:item/arrow', 108003, armed(), type2_csv([[108003, 0, 99, 0, 100, 3]]), [org_row()], notices,
                    0)[3] == dict(item='demo:item/arrow', count=3)  # a multiple shot's 3 arrows
    for args, why in [((armed(need=8), one, [org_row()], notices, 100), 'not a bow'),
                      ((armed(exhaust=379006000), one, [org_row()], notices, 100), 'not the arrow'),
                      ((armed(), type2_csv([[108003, 0, 100, 0, 100, 0]]), [org_row()], notices, 100), 'arrow count'),
                      ((armed(), type2_csv([[102003, 0, 100, 0, 100, 1]]), [org_row()], notices, 100), 'arrow count'),
                      ((armed(), one, [org_row(ident=391020000)], notices, 100), 'no row 391010000'),
                      ((armed(), one, [org_row(kind=110)], notices, 100), 'not a countable kind 120'),
                      ((armed(), one, [org_row(countable=0)], notices, 100), 'not a countable kind 120'),
                      ((armed(), one, [org_row(weight=5)], notices, 100), 'weight'),
                      ((armed(), one, [org_row(price=0)], notices, 100), 'price'),
                      ((armed(), one, [org_row()], notices, 10000), 'starting arrows'),
                      ((armed(), one, [org_row()], texts, 100), 'no plain text 4007'),
                      ((armed(), one, [org_row()], texts + '"4007","%d left"\n', 100), 'no plain text 4007')]:
        refused(lambda: k.arrows('demo:item/arrow', 108003, *args), why)
    # PQ-422 (D-219): bow_stats() gives each bow its 2145 Item_Org damage
    # (column 16) as attack and durability (column 20) under the package's
    # dexterity, full off-hand bow category (Ebenezer 004a0d2a, 0049e11c).
    def manifest_with(*ids, category=dict(id='demo:weapon/bow', coefficient=0.0002, dexterity=1, offhand=2)):
        return dict(stats=dict(categories=[category, dict(id='demo:weapon/none', coefficient=0, dexterity=0, offhand=0)],
                               items=[dict(id=i, category='demo:weapon/none', attack=0) for i in ids]),
                    inventory=dict(items=[dict(id=i, durability=0) for i in ids]))
    # PQ-434 (D-221): plus its Item_Ext bonuses (columns 9 and 13).
    def bow(damage=116, durability=8000, damage_bonus=0, durability_bonus=0, kind=70):
        return ('A', dict(kind=kind, damage=damage, durability=durability, damage_bonus=damage_bonus,
                          durability_bonus=durability_bonus, item_2145=1110532000))
    bonuses = [(0, 0), (66, 9000), (32, 6000), (47, 7000), (84, 9000)]
    grades = ['demo:item/grade%d' % n for n in range(len(bonuses))]
    graded = {n: bow(damage_bonus=b, durability_bonus=d) for n, (b, d) in zip(grades, bonuses)}
    m = manifest_with(*grades)
    bow0 = grades[0]
    about = k.bow_stats(m, graded, 'demo:weapon/bow')
    expected = [(116 + b, 8000 + d) for b, d in bonuses]
    assert expected == [(116, 8000), (182, 17000), (148, 14000), (163, 15000), (200, 17000)], expected
    assert [(i['category'], i['attack']) for i in m['stats']['items']] == [
        ('demo:weapon/bow', a) for a, _ in expected], m
    assert [i['durability'] for i in m['inventory']['items']] == [d for _, d in expected], m
    assert [(r['attack'], r['durability']) for r in about['items']] == expected, about
    assert [(r['item_org_damage'], r['item_ext_damage'], r['item_org_durability'], r['item_ext_durability'])
            for r in about['items']] == [(116, b, 8000, d) for b, d in bonuses], about
    for items_, manifest, why in [
            ({bow0: bow(kind=71)}, manifest_with(bow0), 'not a kind 70'),
            ({bow0: bow(damage=10001)}, manifest_with(bow0), 'attack 10001 + 0'),
            ({bow0: bow(damage_bonus=9885)}, manifest_with(bow0), 'attack 116 + 9885'),
            ({bow0: bow(damage_bonus=-1)}, manifest_with(bow0), 'Item_Ext attack bonus -1'),
            ({bow0: bow(durability=0)}, manifest_with(bow0), 'durability 0 + 0'),
            ({bow0: bow(durability_bonus=57536)}, manifest_with(bow0), 'durability 8000 + 57536'),
            ({bow0: bow(durability_bonus=-8000)}, manifest_with(bow0), 'Item_Ext durability bonus -8000'),
            ({bow0: bow()}, manifest_with(), 'not one package item'),
            ({bow0: bow()},
             manifest_with(bow0, category=dict(id='demo:weapon/bow', coefficient=0.0002, dexterity=1, offhand=1)),
             'full off-hand')]:
        refused(lambda: k.bow_stats(manifest, items_, 'demo:weapon/bow'), why)
    edge = manifest_with(bow0)
    k.bow_stats(edge, {bow0: bow(damage_bonus=9884, durability_bonus=57535)}, 'demo:weapon/bow')
    assert (edge['stats']['items'][0]['attack'], edge['inventory']['items'][0]['durability']) == (10000, 65535), edge
    print('PASS bow_stats() (PQ-422, PQ-434): each kind 70 bow takes its Item_Org damage + Item_Ext column 9 as attack '
          'and its Item_Org durability + Item_Ext column 13 under the package\'s dexterity, full off-hand bow category '
          '(Ebenezer 004a0d2a, 0049e11c, 0041f077; 1298 004d6320, 2233 005aa8e0): the grades 116, 182, 148, 163, 200 '
          '/ 8000, 17000, 14000, 15000, 17000, the sums 10000 / 65535 accepted; another kind, a sum above 10000 or '
          '65535, a negative bonus, durability 0, a missing item and another category refused', flush=True)
    # PQ-422 (D-219): archery_hit() from the operator's MAGIC_TYPE2 row
    # (AI 0040d471 -> 00443a34), which must be HitType 0 and agree with the
    # 1298 client's type-2 row on HitType, HitRate, AddRange and NeedArrow.
    def magic2(num=108003, **kw):
        row = dict(iNum=num, Name='Archery', Description='?', HitType=0, HitRate=100, AddDamage=100, AddRange=100,
                   NeedArrow=1, AddDamagePlus=0)
        row.update(kw)
        return row
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as tmp:
        def export(*rows):
            (pathlib.Path(tmp) / 'MAGIC_TYPE2.json').write_text(__import__('json').dumps(list(rows)))
            return tmp
        hit, about = k.archery_hit(108003, one, export(magic2(), magic2(102003, AddDamagePlus=9)))
        assert hit == dict(hit_rate=100, add_damage=100, add_damage_plus=0), hit
        assert (about['client_add_damage'], about['magic_type2']['iNum']) == (0, 108003), about
        assert k.archery_hit(108003, one, export(magic2(AddDamagePlus=12, AddDamage=150)))[0] == dict(
            hit_rate=100, add_damage=150, add_damage_plus=12)
        for rows, csv_, why in [((magic2(102003),), one, 'no row 108003'),
                                ((magic2(HitType=1),), one, 'only HitType 0'),
                                ((magic2(HitType=2),), one, 'only HitType 0'),
                                ((magic2(HitRate=50),), one, 'disagrees'),
                                ((magic2(AddRange=150),), one, 'disagrees'),
                                ((magic2(NeedArrow=3),), one, 'disagrees'),
                                ((magic2(),), type2_csv([[102003, 0, 100, 0, 100, 1]]), 'disagrees'),
                                ((magic2(AddDamage=301),), one, 'add_damage 301'),
                                ((magic2(AddDamagePlus=-1),), one, 'add_damage_plus -1')]:
            refused(lambda: k.archery_hit(108003, csv_, export(*rows)), why)
        (pathlib.Path(tmp) / 'MAGIC_TYPE2.json').unlink()
        refused(lambda: k.archery_hit(108003, one, tmp), 'MAGIC_TYPE2 export')
    # PQ-423 (D-220): the cast start plays clip 0x1c for a type-2 row with a
    # kind 71 crossbow in either hand (1298 00583f20, 005844c7-0058451f), and
    # triggers the row's self FX (+0x40) at part +0x44 % 1000 and
    # |+0x44 / 1000| when not 0 (00479de0 at 0058447f / 0058449a).
    crossbow = archery(108003)
    crossbow[k.SKILL_TYPES[1]] = 2
    assert [k.cast_animation(crossbow, kinds) for kinds in ({70}, {71}, {None, 71}, {70, 71}, set())] == [26, 28, 28, 28, 26]
    assert k.cast_animation(archery(108003), {71}) == 26  # not a type-2 row: the start animation
    def selfed(fx=500, part=12, flying=590):
        r = archery(108003)
        r[k.SKILL_SELF_FX], r[k.SKILL_SELF_PART], r[k.SKILL_FLYING_FX] = fx, part, flying
        return skill_csv([r])
    fx_csv = '"1 - UInt32","2 - String","3 - String","4 - Int32","5 - Byte"\n"500","","fx/arrow.fxb","311","0"\n'
    key, spec, effect, about = k.cast_effect(108003, selfed(), fx_csv, 40)
    assert (key, spec, effect) == ('ranged-cast-500', dict(fx=500, duration=10, self=True),
                                   dict(clip='ranged-cast-500', joints=[12])), (key, spec, effect)
    assert (about['self_fx'], about['part'], about['flying_fx']) == (500, 12, 590), about
    assert k.cast_effect(108003, selfed(part=7012), fx_csv, 40)[2]['joints'] == [12, 7]
    assert k.cast_effect(108003, selfed(part=7000), fx_csv, 40)[2]['joints'] == [0, 7]
    for csv_, joints, why in [(selfed(fx=0), 40, 'flying FX'), (selfed(flying=0), 40, 'flying FX'),
                              (selfed(fx=501), 40, 'no FX 501'), (selfed(), 12, 'do not fit'),
                              (selfed(part=-12), 40, 'do not fit'), (selfed(part=12012), 40, 'do not fit'),
                              (skill_csv([archery(102003)]), 40, 'no archery row 108003')]:
        refused(lambda: k.cast_effect(108003, csv_, fx_csv, joints), why)
    # PQ-417 (D-222): the release's 00587ac0 flies the row's flying FX
    # (+0x50) from part +0x44 % 1000 at the bundle velocity for MAGIC_TYPE2
    # HitType 0 and NumArrow 1, with the target FX (+0x54) at part +0x58 and
    # sound 0x157c for a left kind / 10 == 7.
    def flown(flying=590, target=550, part=12, target_part=0):
        r = archery(108003)
        r[k.SKILL_FLYING_FX], r[k.SKILL_TARGET_FX], r[k.SKILL_SELF_PART], r[k.SKILL_TARGET_PART] = flying, target, part, target_part
        return skill_csv([r])
    def type2(hit_type=0, arrows=1):
        return '"1","2","3","4","5","6"\n"108003","%d","100","0","100","%d"\n' % (hit_type, arrows)
    fx_all = fx_csv + '"590","","fx/arrow.fxb","5500","0"\n"550","","fx/blow.fxb","5500","0"\n'
    part = lambda start, life, fadeout=0: dict(start=start, life=life, fadeout=fadeout)
    bundles = {'fx/arrow.fxb': dict(velocity=77.0, parts=[part(0, 10, .2)]),
               'fx/blow.fxb': dict(velocity=0.0, parts=[part(0, .5), part(.1, .3, .05)])}
    clips, flight, release, about = k.flight(108003, flown(), type2(), fx_all, bundles.__getitem__, 40, 70)
    assert clips == {'ranged-flight-590': dict(fx=590, duration=10, flying=True),
                     'ranged-hit-550': dict(fx=550, duration=0.5)}, clips
    assert flight == dict(clip='ranged-flight-590', joint=12, speed=77.0, hit_clip='ranged-hit-550', hit_joint=0,
                          release='ranged-release') and release == 0x157c == 5500, (flight, release)
    assert (about['hit_type'], about['arrows'], about['velocity']) == (0, 1, 77.0), about
    assert k.flight(108003, flown(part=7012), type2(), fx_all, bundles.__getitem__, 40, 70)[1]['joint'] == 12
    no_release = k.flight(108003, flown(), type2(), fx_all, bundles.__getitem__, 40, 80)
    assert 'release' not in no_release[1] and no_release[2] is None, no_release
    slow = dict(bundles, **{'fx/arrow.fxb': dict(velocity=0.0, parts=[part(0, 10)])})
    empty = dict(bundles, **{'fx/blow.fxb': dict(velocity=0.0, parts=[])})
    for args, why in [((flown(), type2(hit_type=1), fx_all, bundles), 'HitType 1'),
                      ((flown(), type2(arrows=3), fx_all, bundles), 'NumArrow 3'),
                      ((flown(), type2(), fx_csv, bundles), 'no FX 590'),
                      ((flown(target=551), type2(), fx_all, bundles), 'no FX 551'),
                      ((flown(part=40), type2(), fx_all, bundles), 'does not fit'),
                      ((flown(target_part=-1), type2(), fx_all, bundles), 'does not fit'),
                      ((flown(), type2(), fx_all, slow), 'not a flight'),
                      ((flown(), type2(), fx_all, empty), 'no parts'),
                      ((flown(), '"1"\n', fx_all, bundles), 'no row 108003')]:
        refused(lambda: k.flight(108003, *args[:3], args[3].__getitem__, 40, 70), why)
    print('PASS flight() (PQ-417): the archery row\'s flying FX (+0x50) as a flight clip at the bundle velocity from '
          'part +0x44 % 1000, its target FX (+0x54) as a hit clip as long as its parts at part +0x58, the release '
          'sound 0x157c for a left kind 70-79; HitType other than 0, NumArrow other than 1, a missing FX, a bundle '
          'without velocity or parts and a part past the skeleton refused', flush=True)
    print('PASS cast_effect() and cast_animation() (PQ-423): the archery row\'s self FX (+0x40) as a 10 s self clip '
          'and its parts (+0x44 % 1000, |+0x44 / 1000| when not 0) as the joints; no self or flying FX, an FX fx.tbl '
          'lacks, a part past the skeleton or a repeated part refused; clip 0x1c (28) for a type-2 row with a kind 71 '
          'item in either hand, else the start animation', flush=True)
    print('PASS archery_hit() (PQ-422): the archery row\'s HitRate, AddDamage and AddDamagePlus from the operator\'s '
          'MAGIC_TYPE2 export (AI 0040d471 -> 00443a34); a missing export or row, HitType 1 or 2, a row that disagrees '
          'with the 1298 client\'s type-2 row and values outside N3RE\'s bounds refused', flush=True)
    print('PASS arrows() (PQ-421): the archery row must need a bow (+0x70 = 70 / 10) and exhaust Item_Org 391010000, a '
          'countable kind 120 item; its name, price and icon, the type-2 arrow count per shot and 1298\'s text 4007; '
          'anything else refused', flush=True)
    print('PASS ranged_attack() (PQ-416, PQ-420): the bow profile\'s reach is the bow\'s range column x 0.1 and its range '
          'that + 2.0 (1298 00583780 / 00468620, add range 100), its hold sqrt((range column // 10)^2 + 1000) on the '
          'ground plane (Ebenezer 004c1dbe, PQ-467), its cast time the archery row\'s x 100 ms (00461ab0; 1 '
          'tenth or less, or over 10 s, refused), the notice 1298\'s text 4009; mixed or unbounded ranges, '
          'a row that is not type 2 or carries its own range, another add range and a missing or formatted text '
          'refused', flush=True)
    print('PASS combat_rows() (PQ-347): a kind 70 bow alone in the left hand selects the profile named bow, which must '
          'be 1298 0045bfe0\'s ready 92 and the class\'s archery row (1298 004659b0: class x 1000 + 3 for 102/107/108/202/207/'
          '208): its start animation as the attack and moving attack, its cast x 100 + 150 ms as the interval; other '
          'classes, a missing row, a mismatched profile, other kinds, another slot and missing hand selectors refused',
          flush=True)

    # 0043f090 / 00463180: A8R8G8B8 (21) and X8R8G8B8 (22) are 4 bytes a texel.
    raw = bytes([10, 20, 30, 40] * 16)
    assert ko_hud.texture(ntf(22, texels=raw)) == (4, 4, bytes([30, 20, 10, 255] * 16))
    assert ko_hud.texture(ntf(21, texels=raw)) == (4, 4, bytes([30, 20, 10, 40] * 16))
    for bad, text in ((ntf(22, mips=1), 'subset'), (ntf(22, 512, 4, texels=b''), 'subset'),
                      (ntf(22, 6, 4, texels=b''), 'subset'), (ntf(22)[:-1], 'truncated'),
                      (ntf(22) + b'\0', 'trailing'), (ntf(20, texels=b'\0' * 48), 'subset')):
        refused(lambda: ko_hud.texture(bad), text)
    print('PASS HUD textures: A8R8G8B8 and X8R8G8B8 read as 4-byte B, G, R, A texels (X8 opaque); mipmapped, '
          'over 256, non-power-of-two, truncated, trailing and R8G8B8 refused', flush=True)

    if '--local' in sys.argv:
        install_root = k.ko_glow_2233.INSTALL
        if not (install_root / 'manifest.json').is_file():
            print('SKIP --local: no 2145 install at %s' % install_root, flush=True)
            return
        install = k.ko_glow_2233.Install()
        source = k.Source(install)
        names = [n for n in source.pack.by_name if n.endswith('.n3chrplug')]
        parsed = {n: k.read(source.pack.read(n)) for n in names}
        assert len(parsed) == 38, len(parsed)
        azagai = parsed['11_1042_50_0.n3chrplug']
        assert (azagai['stored_joint'], azagai['chr'], len(azagai['fx_mesh']['vertices'])) == (
            7, 'chr\\11_1042_50_0.n3chr', 74), azagai
        # PQ-334: every 2145 Item-pack .n3cplug reads to its last byte as 2233's
        # CN3CPlug (004489c0); 54 carry the texture block, all five names empty
        # and +0x2cc 0; the 1298 layout refuses exactly those 54 (21 inside the
        # FX mesh, 33 with no mesh as trailing data) and reads the rest alike.
        cplugs = sorted(n for n in source.pack.by_name if n.endswith('.n3cplug'))
        blocks, unchanged, old_refused = 0, 0, []
        for n in cplugs:
            rigid = ko_appearance.read_plug(source, 'Item/' + n, '2145')
            if rigid['textures'] is not None:
                assert rigid['textures'] == dict(count=1, value=0, names=[''] * 5), (n, rigid['textures'])
                blocks += 1
            try:
                old = ko_appearance.read_plug(source, 'Item/' + n)
                if old['fx_data'] is not None and old['fx_data'] != rigid['fx_data']:
                    k.ko.import_mesh(None, 1.0, data=old['fx_data'])
                    raise AssertionError('%s: the 1298 layout read another FX mesh' % n)
                assert rigid['textures'] is None, n
                unchanged += 1
            except ValueError as error:
                old_refused.append((n, str(error)))
        assert (len(cplugs), blocks, unchanged) == (397, 54, 343), (len(cplugs), blocks, unchanged)
        assert sorted(e for _, e in old_refused) == ['KO trailing variant'] * 21 + ['plug trailing data'] * 33, old_refused
        bind = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
        import ko_weapon_fx
        bow = ko_weapon_fx.geometry(source, 'Item/11_1042_50_0.n3cplug', 7, bind, 1.8, '2145')
        assert (bow['fx_vertices'], bow['fx_triangles']) == (74, 74), bow
        rows_, items = k.rows(install)
        assert [(r['item'], r['slot'], r['joint'], r['ko_2145_item'], r.get('glow_2145_item')) for r in rows_] == [
            ('demo:item/azagai', 1, 7, 1110532000, None), ('demo:item/azagai_normal10', 1, 7, 1110432510, None),
            ('demo:item/azagai_reverse1', 1, 7, 1110532501, 1110532501),
            ('demo:item/azagai_reverse10', 1, 7, 1110532510, 1110532510),
            ('demo:item/azagai_reverse30', 1, 7, 1110532600, 1110532600)], rows_
        assert items['demo:item/azagai'][1] == dict(id=1110532000, name="<selfname>'s Azagai", kind_text=None,
                                                     head=dict(name_color=0xffffff, lines=[]), model=111042500,
                                                     kind=70, attach=4, skeletal=1, item_2145=1110532000,
                                                     extension_table=33,
                                                     extension_key=1000, attribute=0, column_45=0, glow=None,
                                                     effect=None, range=400, damage=116, durability=8000,
                                                     damage_bonus=0, durability_bonus=0), items
        # PQ-422: every grade's base Item_Org row has damage 116 and durability 8000.
        assert {(x['damage'], x['durability']) for _, x in items.values()} == {(116, 8000)}, items
        # PQ-434 (D-221): the grades' Item_Ext columns 9 and 13 (Item_Ext_33
        # row 1000, Item_Ext_9 row 1510, Item_Ext_33 rows 1501, 1510, 1600),
        # and bow_stats() gives each the sum (2233 005aa8e0's attack and
        # maximum durability lines).
        assert [(x['damage_bonus'], x['durability_bonus']) for _, x in items.values()] == [
            (0, 0), (66, 9000), (32, 6000), (47, 7000), (84, 9000)], items
        local = dict(stats=dict(categories=[dict(id='demo:weapon/bow', coefficient=0.0002, dexterity=1, offhand=2)],
                                items=[dict(id=i, category='demo:weapon/none', attack=0) for i in items]),
                     inventory=dict(items=[dict(id=i, durability=0) for i in items]))
        k.bow_stats(local, items, 'demo:weapon/bow')
        assert [(s['attack'], i['durability']) for s, i in zip(local['stats']['items'], local['inventory']['items'])] == [
            (116, 8000), (182, 17000), (148, 14000), (163, 15000), (200, 17000)], local
        print('PASS --local (PQ-434): the Azagai grades\' attack 116, 182, 148, 163, 200 and durability 8000, 17000, '
              '14000, 15000, 17000 (2145 Item_Org columns 16 and 20 + Item_Ext columns 9 and 13)', flush=True)
        # PQ-416: every grade's range column is 400, so the bow profile's
        # reach is 40 m and its range 42 m with the 1298 archery row 108003
        # (type 2, add range 100) and text 4009, from the bake's 1298 tables;
        # PQ-420: its cast time 13 tenths makes cast_ms 1300.
        data = ROOT / 'assets/ko/Data'
        csvs = [(data / n.split('/')[1]).read_text(encoding='utf-8-sig')
                for n in (k.SKILL_TABLE, k.TYPE2_TABLE, k.TEXTS_TABLE)]
        assert k.ranged_attack(items, 6, 108003, *csvs)[0] == dict(
            profiles=[dict(profile=6, reach=40.0, range=42.0, cast_ms=1300,
                           hold=dict(distance=math.sqrt(2600), plane='xz'))], notice='Skill Failed - Too far')
        # PQ-421: row 108003 needs a bow and exhausts 391010000 ("Arrow", kind
        # 120, countable, price 1, icon 39101000), one per shot; text 4007.
        import csv
        org = list(csv.reader((data / 'Item_Org_us.tbl.csv').open(encoding='utf-8-sig')))
        got = k.arrows('demo:item/arrow', 108003, csvs[0], csvs[1], org, csvs[2], 100)
        # PQ-423: row 108003's self FX 500 (fx/arrow.fxb) at part 12, flying FX 590.
        fx_csv = (data / 'fx.tbl.csv').read_text(encoding='utf-8-sig')
        cast = k.cast_effect(108003, csvs[0], fx_csv, 40)
        assert cast[2] == dict(clip='ranged-cast-500', joints=[12]) and cast[3]['flying_fx'] == 590, cast
        print('PASS --local (PQ-423): cast_effect(108003) from the 1298 tables is FX 500 at joint 12 (flying FX 590)',
              flush=True)
        # PQ-417: row 108003 flies FX 590 (fx/arrow.fxb, 77 m/s) from part 12,
        # then FX 550 (fx/blow.fxb, 0.5 s) at part 0; release sound 5500.
        sys.path.insert(0, str(ROOT / 'tools/assetc'))
        import ko_fx
        client = ROOT / 'assets/ko'
        clips, flight, release, _ = k.flight(108003, csvs[0], csvs[1], fx_csv,
                                             lambda p: ko_fx.bundle((client / p).read_bytes()), 40, k.BOW_KIND)
        assert flight == dict(clip='ranged-flight-590', joint=12, speed=77.0, hit_clip='ranged-hit-550', hit_joint=0,
                              release='ranged-release') and release == 5500, (flight, release)
        assert clips['ranged-hit-550']['duration'] == 0.5, clips
        print('PASS --local (PQ-417): flight(108003) from the 1298 tables flies FX 590 from joint 12 at 77 m/s, then '
              'FX 550 (0.5 s) at joint 0, release sound 5500', flush=True)
        # PQ-422: the operator's MAGIC_TYPE2 row 108003 (HitType 0, HitRate
        # 100, AddDamage 100, AddDamagePlus 0) agrees with the client's.
        if (k.ko_tables_export() / 'MAGIC_TYPE2.json').is_file():
            assert k.archery_hit(108003, csvs[1])[0] == dict(hit_rate=100, add_damage=100, add_damage_plus=0)
            print('PASS --local (PQ-422): archery_hit(108003) from the operator\'s MAGIC_TYPE2 export is HitRate 100, '
                  'AddDamage 100, AddDamagePlus 0', flush=True)
        else:
            print('SKIP --local archery_hit(): no operator MAGIC_TYPE2 export', flush=True)
        assert got[:5] == (dict(id='demo:item/arrow', label='Arrow', stack_limit=9999, durability=0, starting=100),
                           dict(id='demo:item/arrow', weight=0, price=1, sell_divisor=6), dict(base=39101000, extension=0),
                           dict(item='demo:item/arrow', count=1), 'Skill Failed - Not enough item'), got
        # PQ-337, PQ-350: the normal +10 reaches Item_Ext_9 row 1510
        # (attribute 4, no glow) through its own Item_Org row 1110432000
        # (column 40 = 1, the same model and plug); the reverse grades reach
        # Item_Ext_33 rows 1501, 1510 and 1600 (attribute 12, column 45 1,
        # 10 and 30: a pulse at 1x, a steady light at 1x and at 2x); each has
        # effect 32120 / 32121, bundle versions 6 and 4, read with ko_fx's
        # 2233 layout (PQ-339): a billboard (part version 8, base 4); two mesh
        # parts and four particle parts, 2 unread zero bytes.
        grades = [(x['name'], x['id'], x['extension_table'], x['extension_key'], x['attribute'], x['column_45'],
                   x['glow'], x['effect']['main_id'],
                   x['effect']['main']['file'], x['effect']['main']['version'], x['effect']['main']['parts'],
                   x['effect']['tail']['file'], x['effect']['tail']['version'], x['effect']['tail']['parts'],
                   x['effect']['tail']['unread'], x['effect']['trace_color'])
                  for i, (_, x) in items.items() if i != 'demo:item/azagai']
        tail_parts = [[0, 3, 8, 3], [1, 3, 8, 3], [2, 1, 9, 3], [3, 1, 9, 3], [4, 1, 9, 3], [5, 1, 9, 3]]
        fx = ('fx\\poison_wepon_2011_all.fxb', 6, [[0, 2, 8, 4]], 'fx\\corea_new_tail_poision_bow.fxb', 4, tail_parts, 2,
              'ffff00ff')
        assert grades == [
            ("<selfname>'s Azagai(+10)", 1110432000, 9, 1510, 4, 0, None, 32120, *fx),
            ("<selfname>'s Azagai(+1)", 1110532000, 33, 1501, 12, 1, dict(wave=1, modulate=1), 32120, *fx),
            ("<selfname>'s Azagai(+10)", 1110532000, 33, 1510, 12, 10, dict(wave=0, modulate=1), 32120, *fx),
            ("<selfname>'s Azagai(+30)", 1110532000, 33, 1600, 12, 30, dict(wave=0, modulate=2), 32120, *fx)], grades
        # PQ-354: their heads, 005aa8e0's colours: the normal +10's gold
        # "(Unique Item)", the reverse grades' orange "(Reverse unique item)".
        assert [x['head'] for i, (_, x) in items.items() if i != 'demo:item/azagai'] == [
            dict(name_color=0xdcc77c, lines=[dict(text='(Unique Item)', color=0xdcc77c)])] + [
            dict(name_color=0xffad4d, lines=[dict(text='(Reverse unique item)', color=0xffad4d)])] * 3, items
        # PQ-339: the main bundle on the bow's FX mesh, with its 15 DXT5
        # frames from the 2145 fx pack; the plain bow has none.
        import ko_fx_bake
        specs, fx_report = k.weapon_effects(rows_, items, [bind] * 8, 1.8, install)
        assert [(s['key'], s['ko_item'], s['geometry']['fx_vertices']) for s in specs] == [
            (2, 1110432510, 74), (3, 1110532501, 74), (4, 1110532510, 74), (5, 1110532600, 74)], specs
        frames = []
        entry, clip, data = ko_fx_bake.appearance_effect(None, lambda n, source: frames.append(
            k.ko_appearance.ko_tiles.mip_chains(source.get(n), dxt5=True)[0][0][:2]) or len(frames) - 1, specs[0], 0)
        tail = entry.pop('tail_2233')
        assert (clip, entry['fps'], entry['blend'], entry['flags'], len(entry['copies']), entry['tails']) == (
            'appearance-2-tail', 30.0, [5, 2], 0x1c7, 3, 2) and frames[:15] == [(64, 64)] * 15, (entry['fps'], frames)
        # PQ-341: the tail 32121 as a 20 s clip of two 10 s links (its meshes
        # cycle 50 frames at 15 and 40 a second): the two shapes' 32 x 32
        # textures and the four particle textures (64 x 64), its records.
        assert (tail['link_seconds'], tail['frames'], tail['parts'], tail['scale']) == (
            10.0, 600, [[3, 8], [3, 8], [1, 9], [1, 9], [1, 9], [1, 9]], True), tail
        assert frames[15:] == [(32, 32)] * 2 + [(64, 64)] * 4 and 70000 < tail['records'] < 90000, (frames, tail)
        # PQ-342: each particle part's camera-distance rule (2233 00592900):
        # pool 20, 40 and 70 m for the kind-2 puffs, pool 11, 20 and 50 m for
        # the kind-1 sparks, each on its own texture.
        assert [(r['texture'], r['count'], r['near'], r['far'], r['blend'], r['flags']) for r in tail['thinning']] == [
            (17, 20, 40.0, 70.0, [5, 2], 0x1c7), (18, 20, 40.0, 70.0, [5, 2], 0x1c7),
            (19, 11, 20.0, 50.0, [5, 2], 0x1c7), (20, 11, 20.0, 50.0, [5, 2], 0x1c7)], tail['thinning']
        assert len(data) < 4 * 1024 * 1024, len(data)
        assert items['demo:item/azagai_reverse10'][1]['effect']['drawn'] == dict(main=True, tail=True)
        records, glow = k.ko_glow_2233.cook(rows_, install)
        assert [(r['key'], r['wave'], r['modulate']) for r in records] == [(3, 1, 1), (4, 0, 1), (5, 0, 2)], records
        # The Azagai's icon: Item_Org column 8 (Item_Ext_33 row 1000 has none),
        # by the 2233 rule, from the player's 2145 UI pack.
        icons, report = k.icons({}, items, install)
        entry = icons['demo:item/azagai']
        assert (entry['base'], entry['extension'], entry['item_2233']) == (111043200, 0, 1110532000), entry
        assert [(r['path'], r['item_ext']) for r in report['items']] == [
            ('UI/ItemIcon_11_1043_20_0.dxt', 1000), ('UI/ItemIcon_11_1043_20_0.dxt', 1510),
            ('UI/ItemIcon_11_1043_20_0.dxt', 1501), ('UI/ItemIcon_11_1043_20_0.dxt', 1510),
            ('UI/ItemIcon_11_1043_20_0.dxt', 1600)], report
        data = entry['assets'].get(report['items'][0]['path'])
        assert ko_hud.texture(data)[:2] == (64, 64)
        assert report['sources'] == {'UI/ui.hdr': install.hashes['ui/ui.hdr'], 'UI/ui.src': install.hashes['ui/ui.src'],
                                     'UI/itemicon_11_1043_20_0.dxt': __import__('hashlib').sha256(data).hexdigest()}, \
            report['sources']
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as tmp:
            entry, report = k.cook(dict(rows_[0]), player, {0: 17, 1: 16}, 1.7984575206272155,
                                   pathlib.Path(tmp) / 'root', pathlib.Path(tmp) / 'work', install)
        assert [(s['name'], s['ko_clip']) for s in report['slots']] == [
            ('breath', 0), ('attackbreath', 1), ('magic', 5), ('breath', 0)], report['slots']
        assert report['inner_unread_bytes'] == 3109 and abs(report['factor'] - 1.7984575206272155 / 1.8 * .93) < 1e-6
        print('PASS --local (PQ-334): all %d 2145 Item-pack .n3cplug read to their last byte as 004489c0 reads them, '
              '%d with the texture block (five empty names, +0x2cc 0) that the 1298 layout refuses, the other %d '
              'read alike by both layouts; the plain Azagai\'s FX mesh (11_1042_50_0.n3cplug) reads: %d vertices, '
              '%d triangles' % (len(cplugs), blocks, unchanged, bow['fx_vertices'], bow['fx_triangles']), flush=True)
        print('PASS --local: all %d 2145 .n3chrplug files read to their last byte; the <selfname>\'s Azagai '
              '(1110532000, column 40 = 1, attach 4: plug slot 1) cooks breath, attackbreath, magic (frames '
              '160-195 at 55 fps) on joint 7 at factor %.4f, with the icon %s (64 x 64 X8R8G8B8) from the 2145 UI pack; '
              'its normal +10 (1110432510: Item_Ext_9 row 1510, attribute 4) has no glow, its reverse +1, +10 and '
              '+30 (1110532501, 1110532510, 1110532600) reach Item_Ext_33 rows 1501, 1510 and 1600 (attribute 12, '
              'column 45 1, 10 and 30: a pulse at 1x, a steady glow at 1x and at 2x), each with 005aa8e0\'s name and '
              'its head\'s kind line (PQ-354), and all four have effect 32120 / 32121 (bundle versions 6 and '
              '4, read by ko_fx\'s 2233 layout); PQ-339: 32120 is drawn on the bow\'s FX mesh (74 vertices) with '
              'its 15 64 x 64 DXT5 frames at 30 fps; PQ-341: and its tail 32121 as a 20 s clip of two 10 s links '
              '(%d records: two turning, blinking meshes and four particle parts); PQ-342: with 00592900\'s '
              'camera-distance rules on its particle batches (pool 20, 40 and 70 m for the puffs; pool 11, 20 and 50 m '
              'for the sparks), its particles written as emission candidates'
              % (len(parsed), report['factor'], 'UI/ItemIcon_11_1043_20_0.dxt', tail['records']), flush=True)


if __name__ == '__main__':
    main()
