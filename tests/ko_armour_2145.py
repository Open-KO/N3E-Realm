"""PQ-319: the 2233 client's 2145 armour cook (tools/assetc/ko_armour_2145.py)
on original synthetic tables, and the part reader change it needs.

Checks 2233's artwork name for an armour row (009b3fc0 with 0092fd30: the
model column plus race x 1000, "Item\\%.1d_%.4d_%.2d_%.1d%s", "%.2d" first
for an item / 10^9 of 1-3, the part slot of each attach byte, the races and
classes it names nothing for), the wear rule (005e5a90's need-race and
need-class bytes, 00930030's kinds per class), the tooltip name (005aa8e0:
the Item_Org name and "(+%d)"), the inventory area of each attach byte (1298
004a1ed0), rows() on a synthetic install and definition (slots appended,
areas merged, the glow item, the refusals), the glow cook's guard on an
armour row (its artwork must be 009b3fc0's for the row's race and class),
and that a part whose skin has a corner without a normal now takes its
triangle's normal on the appearance path (PQ-281's rule), while a part
without one reads as before. No KO data is read; with --local the
definition games/moradon/armour-2233.json is checked against the player's
own 2145 install (SKIP without it).
"""
import hashlib
import json
import pathlib
import struct
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/assetc'))
import ko_appearance  # noqa: E402
import ko_armour_2145 as k  # noqa: E402
import ko_glow_2233 as g  # noqa: E402

ORG_TYPES = [6, 2, 7, 7, 6, 2, 6, 6, 6, 6, 2, 2, 2, 2, 2]
EXT_TYPES = [6, 7, 6, 7] + [6] * 3 + [2] + [6] * 37


def refused(call, text):
    try:
        call()
    except ValueError as error:
        assert text in str(error), (text, str(error))
        return
    raise AssertionError('accepted: ' + text)


class Reader:
    """tbl_2145.load's shape over JSON stand-ins: (framing, header, types, rows)."""
    @staticmethod
    def load(path):
        data = json.loads(pathlib.Path(path).read_text())
        return 'block', b'', data['types'], data['rows']


def org(number, table, name, model, kind=220, attach=5, race=124, klass=8):
    return [number, table, name, '', 0, 0, model, model + 4000000, 0, 0, kind, 0, attach, race, klass]


def ext(key, attribute, mode, name='Stamina'):
    row = [key, name, 0, ''] + [0] * 41
    row[g.ATTRIBUTE], row[g.MODE] = attribute, mode
    return row


# Texts_us.tbl's kind lines (005aa8e0), synthetic stand-ins.
TEXTS = {n: '[kind %d]' % n for n in (6808, 6809, 6810, 6811, 6812, 6814, 6815, 6816, 6817, 6818, 6819)}


def install(root, orgs, exts):
    files = {g.ORG: dict(types=ORG_TYPES, rows=orgs),
             k.TEXTS: dict(types=[6, 7], rows=[[n, t] for n, t in TEXTS.items()])}
    for table, rows in exts.items():
        files[g.EXT.format(table)] = dict(types=EXT_TYPES, rows=rows)
    entries = []
    for name, data in files.items():
        path = root / 'client' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        entries.append(dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (root / 'manifest.json').write_text(json.dumps(dict(sha256=g.INSTALLER_SHA256, manifest=entries)))
    return g.Install(root, reader=Reader)


def string(text):
    raw = text.encode('ascii')
    return struct.pack('<i', len(raw)) + raw


def part_file(flags=0, source=0, destination=0):
    """A part whose material has render flags `flags` and blend factors (the
    0x5c bytes 00412180 reads: 17 floats, colour op and arguments, flags,
    source, destination)."""
    return string('upper') + struct.pack('<i', 0) + struct.pack('<17f', *([1.0] * 4 + [0.0] * 13)) \
        + struct.pack('<6I', 0, 0, 0, flags, source, destination) + string('item\\t.dxt') + string('item\\t.n3cskins')


def skin_file(normals):
    """One triangle per level; `normals` the three stored vertex normals."""
    origins = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    out = string('skin')
    for level in range(4):
        out += string('l%d' % level) + struct.pack('<3i', 1, 3, 3)
        out += b''.join(struct.pack('<6f', *o, *n) for o, n in zip(origins, normals))
        out += struct.pack('<3H', 0, 1, 2) + b''.join(struct.pack('<2f', u, 0) for u in (0, .5, 1))
        out += struct.pack('<3H', 0, 1, 2)
        out += b''.join(struct.pack('<3f', *o) + struct.pack('<i', 1) + b'\0' * 8 + struct.pack('<i', 2)
                        for o in origins)
    return out


class Files:
    def __init__(self, **files):
        self.files = files

    def get(self, name):
        return self.files[name]


def main():
    upper = org(258001000, 37, 'Krowaz Assassin Upper Garment', 20800100)
    helmet = org(258003000, 39, 'Krowaz Assassin Helmet', 20800300, attach=7)
    # 009b3fc0 + 0092fd30: the model + race x 1000, by part.
    assert k.resource(upper, 2, 108) == 'Item/2_0802_10_0.n3cpart'
    assert k.resource(helmet, 2, 102) == 'Item/2_0802_30_0.n3cpart'
    assert k.resource(upper, 12, 208) == 'Item/2_0812_10_0.n3cpart'
    assert k.resource(upper, 1, 105) == 'Item/2_0801_10_0.n3cpart'
    # "%.2d" first for an item / 10^9 of 1-3; the attach byte is read % 100.
    assert k.resource(org(1258001000, 37, 'x', 20800100), 2, 108) == 'Item/02_0802_10_0.n3cpart'
    assert k.resource(org(258001000, 37, 'x', 20800100, attach=105), 2, 108) == 'Item/2_0802_10_0.n3cpart'
    refused(lambda: k.resource(upper, 1, 108), 'race 1 class 108: 009b3fc0 names no armour artwork')
    refused(lambda: k.resource(upper, 3, 102), 'race 3 class 102')
    refused(lambda: k.resource(upper, 6, 113), 'race 6: 009b3fc0 gives armour an empty name')
    refused(lambda: k.resource(upper, 14, 213), 'race 14: 009b3fc0 gives armour an empty name')
    for race in (0, 20, 100, 5):
        refused(lambda: k.resource(upper, race, 108), 'names no armour artwork')
    refused(lambda: k.resource(upper, 2, 11), 'names no armour artwork')
    refused(lambda: k.resource(org(258001000, 37, 'x', 20800100, attach=1), 2, 108), 'not an armour part')
    refused(lambda: k.resource(org(258001000, 37, 'x', 0), 2, 108), 'no model')
    refused(lambda: k.resource(org(258011000, 37, 'x', 20800100), 2, 108), 'prefix branch')
    assert [k.PART_OF_ATTACH[a] for a in range(5, 10)] == [0, 1, 5, 3, 4]
    assert [k.AREA_OF_ATTACH[a] for a in range(5, 10)] == [4, 10, 1, 12, 13]
    print('PASS 009b3fc0 / 0092fd30 armour artwork: model + race x 1000, part slots 0, 1, 5, 3, 4, the races and '
          'classes that get no name; 004a1ed0 areas 4, 10, 1, 12, 13', flush=True)

    # 005e5a90 and 00930030.
    assert k.wearable(upper, 2, 108) is None and k.wearable(upper, 12, 208) is None
    assert 'need-class 8' in k.wearable(upper, 2, 102) and 'need-class 8' in k.wearable(upper, 2, 107)
    assert k.wearable(org(1, 1, 'x', 1, race=2, klass=2), 2, 102) is None
    assert 'text 3018' in k.wearable(org(1, 1, 'x', 1, race=2, klass=2), 3, 102)
    assert k.wearable(org(1, 1, 'x', 1, race=20, klass=0), 13, 202) is None
    assert 'kind 210 refused' in k.wearable(org(1, 1, 'x', 1, kind=210, klass=2), 2, 108)
    assert k.wearable(org(1, 1, 'x', 1, kind=210, klass=255), 2, 108) is None  # no kind test after 255
    assert k.wearable(org(1, 1, 'x', 1, kind=108, klass=30), 2, 108) is None  # other bytes: class == kind
    assert 'need-class 30' in k.wearable(org(1, 1, 'x', 1, kind=220, klass=30), 2, 108)
    assert 'refuses class 99' in k.wearable(org(1, 1, 'x', 1, klass=0), 2, 99)
    print('PASS 005e5a90 / 00930030 wear rule: need-race above 100 or open, need-class groups, 255 and other bytes, '
          'kinds per class', flush=True)

    # 005aa8e0: the name and its suffix.
    assert k.name(upper, ext(15, 11, 15)) == 'Krowaz Assassin Upper Garment(+15)'
    assert k.name(upper, ext(15, 11, 100)) == 'Krowaz Assassin Upper Garment'
    assert k.name(upper, ext(1003, 5, 0)) == 'Krowaz Assassin Upper Garment(+3)'
    assert k.name(upper, ext(1010, 5, 0)) == 'Krowaz Assassin Upper Garment(+10)'
    assert k.name(upper, ext(1000, 0, 0)) == 'Krowaz Assassin Upper Garment'
    assert k.name(upper, ext(1003, 8, 0)) == 'Krowaz Assassin Upper Garment'
    # Attributes 3, 4, 6 and 12 show the Item_Ext row's own name (005aad74).
    assert [k.name(upper, ext(1, a, 15, 'Own(+1)')) for a in (3, 4, 6, 12)] == ['Own(+1)'] * 4
    # PQ-350: the kind line under it (the jump tables at 005b2510 / 005b251c),
    # none for 0, 10 and above 12; a set item (need race 101-199, 005aafe3)
    # takes 6818 for attribute 11 and 6815 for the others.
    plain = org(1, 1, 'x', 1, race=2)
    assert [k.kind_text(plain, ext(1, a, 0)) for a in range(14)] == [
        None, 6808, 6809, 6810, 6811, 6812, 6814, 6819, 6820, 6820, None, 6817, 6816, None]
    assert [k.kind_text(upper, ext(1, a, 0)) for a in (0, 4, 5, 10, 11, 12)] == [None, 6815, 6815, None, 6818, 6815]
    assert [k.kind_text(org(1, 1, 'x', 1, race=r), ext(1, 11, 0)) for r in (100, 101, 199, 200)] == [
        6817, 6818, 6818, 6817]
    # PQ-354 (D-194): the label is the name; the kind line is the N3IH head's
    # line, both in the attribute's colour (005aac3c through 005b24d4, the kind
    # line's through 005b251c, the same field for every attribute; a set item:
    # +0x154 for 11, else +0x138), from 005a9160's constants.
    assert k.label(upper, ext(1, 11, 1), TEXTS) == 'Krowaz Assassin Upper Garment(+1)'
    assert k.head(upper, ext(1, 11, 1), TEXTS) == dict(name='Krowaz Assassin Upper Garment(+1)', name_color=0xff83a6,
                                                       kind_text=6818, lines=[dict(text='[kind 6818]', color=0xff83a6)])
    assert k.head(upper, ext(20, 5, 0), TEXTS) == dict(name='Krowaz Assassin Upper Garment(+10)', name_color=0xd20000,
                                                       kind_text=6815, lines=[dict(text='[kind 6815]', color=0xd20000)])
    assert k.head(plain, ext(1510, 4, 0, 'Own(+10)'), TEXTS) == dict(
        name='Own(+10)', name_color=0xdcc77c, kind_text=6811, lines=[dict(text='[kind 6811]', color=0xdcc77c)])
    assert k.head(plain, ext(1510, 12, 10, 'Own(+10)'), TEXTS) == dict(
        name='Own(+10)', name_color=0xffad4d, kind_text=6816, lines=[dict(text='[kind 6816]', color=0xffad4d)])
    assert k.head(plain, ext(1000, 0, 0), TEXTS) == dict(name='x', name_color=0xffffff, kind_text=None, lines=[])
    assert k.label(plain, ext(1000, 0, 0), TEXTS) == 'x'
    # Every attribute's colour (005a9160: +0x124 ffff00 ... +0x160 00ffcc), and
    # the kind line's is the name's wherever there is one.
    texts = {**TEXTS, 6820: '[kind 6820]'}
    assert [k.colors(plain, ext(1, a, 0)) for a in range(14)] == [
        (0xffffff, None), (0x8080ff, 0x8080ff), (0xffff00, 0xffff00), (0x80ff00, 0x80ff00), (0xdcc77c, 0xdcc77c),
        (0xc87cc7, 0xc87cc7), (0x19ffff, 0x19ffff), (0xc87cc7, 0xc87cc7), (0x00ffcc, 0x00ffcc),
        (0x00ffcc, 0x00ffcc), (0xffffff, None), (0xff83a6, 0xff83a6), (0xffad4d, 0xffad4d), (0xffffff, None)]
    assert [k.colors(upper, ext(1, a, 0)) for a in (0, 5, 10, 11, 12)] == [
        (0xd20000, None), (0xd20000, 0xd20000), (0xd20000, None), (0xff83a6, 0xff83a6), (0xd20000, 0xd20000)]
    assert all(len(k.head(plain, ext(1, a, 0), texts)['lines']) == (a in k.KIND_TEXTS) for a in range(14))
    # The coin item draws its count (005aaa91): no kind line, and no package item.
    coin = org(k.COIN, 1, 'Noah', 1, race=0)
    assert k.kind_text(coin, ext(0, 2, 0)) is None
    refused(lambda: k.head(coin, ext(0, 2, 0), TEXTS), 'is the coin item')
    refused(lambda: k.label(plain, ext(1, 8, 0), TEXTS), "no Data/Texts_us.tbl row 6820 (005aa8e0's kind line)")
    refused(lambda: k.label(plain, ext(1, 4, 0), {**TEXTS, 6811: 'x' * 65}), 'is not a tooltip line')
    # (PQ-350's refusal of a 50-character name whose kind line took the label
    # over 64 is gone: the kind line is no longer in the label, and a kind line
    # over 64 is refused above.)
    refused(lambda: k.label(org(1, 1, 'x' * 64, 1), ext(15, 11, 15), TEXTS), 'not an inventory label')
    refused(lambda: k.label(plain, ext(1, 12, 1, ''), TEXTS), 'not an inventory label')
    print('PASS 005aa8e0 item name: the Item_Org name and (+column 45 % 100) for attribute 11, (+key % 10) for '
          'the others but 7-9, the Item_Ext name for 3, 4, 6, 12; PQ-350: and its kind line (the text by attribute, '
          'a set item\'s by need race); PQ-354: the head\'s colours by attribute and set, the coin item refused, '
          'the label refused over 64 characters or without its text', flush=True)

    orgs = [upper, org(258002000, 38, 'Krowaz Assassin Lower Garment', 20800200, attach=6), helmet,
            org(248001000, 13, 'Krowaz Assassin Upper Garment', 20800100),
            org(208001000, 13, 'Krowaz Warrior Upper Garment', 20800100, kind=210, klass=6)]
    exts = {37: [ext(15, 11, 15)], 38: [ext(15, 11, 3, 'Strength')], 39: [ext(15, 11, 25, 'Agility')],
            13: [ext(15, 5, 0)]}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        inst = install(tmp / 'ok', orgs, exts)
        definition = tmp / 'armour.json'
        spec = dict(character=dict(race=2, **{'class': 108}),
                    slots=[dict(name='Head', area=1), dict(name='Lower body', area=10)],
                    items=[dict(id='demo:item/u', ko_2145_item=258001015), dict(id='demo:item/l', ko_2145_item=258002015),
                           dict(id='demo:item/h', ko_2145_item=258003015), dict(id='demo:item/plain', ko_2145_item=248001015)])
        definition.write_text(json.dumps(spec))
        base, areas = ['Right hand', 'Left hand', 'Upper body'], {'6': 0, '8': 1, '4': 2}
        got = k.rows(inst, base, areas, 2, definition)
        assert got['slots'] == ['Head', 'Lower body'] and got['areas'] == dict(areas, **{'1': 3, '10': 4}), got
        assert [(r['item'], r['slot'], r['parts'], r['part_2145'], r.get('glow_2145_item')) for r in got['rows']] == [
            ('demo:item/u', 2, [0], 'Item/2_0802_10_0.n3cpart', 258001015),
            ('demo:item/l', 4, [1], 'Item/2_0802_20_0.n3cpart', 258002015),
            ('demo:item/h', 3, [5], 'Item/2_0802_30_0.n3cpart', 258003015),
            ('demo:item/plain', 2, [0], 'Item/2_0802_10_0.n3cpart', None)], got['rows']
        assert [got['items'][i][0] for i in ('demo:item/u', 'demo:item/l', 'demo:item/plain')] == [
            'Krowaz Assassin Upper Garment(+15)', 'Krowaz Assassin Lower Garment(+3)',
            'Krowaz Assassin Upper Garment(+5)'], got['items']
        assert [got['items'][i][1]['head'] for i in ('demo:item/u', 'demo:item/plain')] == [
            dict(name_color=0xff83a6, lines=[dict(text='[kind 6818]', color=0xff83a6)]),
            dict(name_color=0xd20000, lines=[dict(text='[kind 6815]', color=0xd20000)])], got['items']
        assert got['items']['demo:item/h'][1]['glow'] == dict(wave=0, modulate=2)
        # The glow cook takes an armour row's record and checks its artwork.
        records, report = g.cook(got['rows'][:3], inst)
        assert [(r['key'], r['wave'], r['modulate']) for r in records] == [(1, 1, 2), (2, 1, 1), (3, 0, 2)], records
        assert report['glow'][0]['armour_2145'] == 'Item/2_0802_10_0.n3cpart' and report['glow'][2]['parts'] == [5]
        refused(lambda: g.cook([dict(got['rows'][0], part_2145='Item/2_0801_10_0.n3cpart')], inst),
                "is not 009b3fc0's artwork Item/2_0802_10_0.n3cpart")
        refused(lambda: g.cook([dict(got['rows'][0], ko_race=1)], inst), 'names no armour artwork')
        refused(lambda: g.cook([dict(got['rows'][0], source='Item/2_0802_10_0.n3cpart')], inst),
                'a 2145 armour row glows as its own 2145 item')
        refused(lambda: g.cook([dict(got['rows'][0], chrplug_2145='Item/x.n3chrplug')], inst),
                'a skeletal plug or an armour part')

        def variant(**change):
            path = tmp / ('v%d.json' % len(list(tmp.iterdir())))
            path.write_text(json.dumps(dict(spec, **change)))
            return path
        refused(lambda: k.rows(inst, base, areas, 1, definition), 'the package\'s player model is race 1')
        refused(lambda: k.rows(inst, base, areas, 2, variant(character=dict(race=2, **{'class': 102}))),
                'cannot wear it (005e5a90: text 3028')
        refused(lambda: k.rows(inst, base, areas, 2, variant(character=dict(race=2, **{'class': 104}))),
                'cannot wear it')
        refused(lambda: k.rows(inst, base, areas, 2, variant(slots=[dict(name='Lower body', area=10)])),
                'worn in area 1, which is no package slot')
        refused(lambda: k.rows(inst, base, areas, 2, variant(slots=[dict(name='Upper body', area=1)])),
                'is already the package\'s')
        refused(lambda: k.rows(inst, base, areas, 2, variant(slots=[dict(name='Head', area=4)])),
                'is already the package\'s')
        refused(lambda: k.rows(inst, base, areas, 2, variant(items=[dict(id='demo:item/w', ko_2145_item=208001015)])),
                'need-class 6 does not admit class 108')
        refused(lambda: k.rows(inst, base, areas, 2, variant(items=spec['items'][:1] * 2)), 'armour definition item')
        refused(lambda: k.rows(inst, base, areas, 2, variant(extra=1)), 'armour definition')
        refused(lambda: k.rows(inst, base + ['s%d' % i for i in range(12)], areas, 2, definition), 'at most 16 slots')
    print('PASS rows(): slots appended and areas merged, each part on its slot and part slot with its glow and '
          'name; the glow cook guards an armour row\'s artwork; refusals for the race, class, missing or reused '
          'slot or area, kind and duplicate item', flush=True)

    # The appearance part reader: a corner without a normal takes its
    # triangle's (PQ-281); the others keep theirs.
    real = ko_appearance.ko_tiles.mip_chains
    ko_appearance.ko_tiles.mip_chains = lambda data, skip=0: [[(1, 1, b'\0\0\0\xff')]]
    try:
        good = [(0, 0, 1), (0, 0, 1), (0, 0, 1)]
        files = Files(**{'p.n3cpart': part_file(), 'item\\t.n3cskins': skin_file(good), 'item\\t.dxt': b''})
        rebuilt = []
        levels, _ = ko_appearance.part_levels(files, 'p.n3cpart', 7, rebuilt)
        assert rebuilt == [0, 0, 0, 0] and [v[1] for v in levels[0][0]] == [[0, 0, -1]] * 3, levels[0][0]
        files.files['item\\t.n3cskins'] = skin_file([(0, 0, 1), (0, 0, 0), (0, 0, 2.9e-08)])
        rebuilt = []
        levels, _ = ko_appearance.part_levels(files, 'p.n3cpart', 7, rebuilt)
        # (b - a) x (c - a) = (0, 0, 1) in source space, -z in engine space.
        assert rebuilt == [2, 2, 2, 2] and [v[1] for v in levels[0][0]] == [[0, 0, -1]] * 3, levels[0][0]
        assert ko_appearance.part_levels(files, 'p.n3cpart', 7)[0] == levels
        # PQ-348 (D-191): a part's render state, as 00412570 draws it, in N3D3's
        # encoding: the 2145 Krowaz parts' flags 5 (blend, both faces) with
        # D3DBLEND 5/6 are blend + double-sided, src_alpha / one_minus_src_alpha
        # (indices 4/5), alpha reference 0 (0043ade0); an opaque part is (0, 0, 0, 0).
        assert ko_appearance.part_state(files, 'p.n3cpart') == (0, 0.0, 0, 0)
        files.files['k.n3cpart'] = part_file(5, 5, 6)
        assert ko_appearance.part_state(files, 'k.n3cpart') == (3, 0.0, 4, 5)
        files.files['u.n3cpart'] = part_file(0x45, 5, 6)
        refused(lambda: ko_appearance.part_state(files, 'u.n3cpart'), 'an unlit part is not drawn on the appearance path yet')
        files.files['f.n3cpart'] = part_file(2)
        refused(lambda: ko_appearance.part_state(files, 'f.n3cpart'), 'KO part render flags 0x2 unsupported')
        cut = ko_appearance.DETAIL_CUT
        assert not ko_appearance.needs_states([cut, (0, 0.0, 0, 0)]) and ko_appearance.needs_states([cut, (3, 0.0, 4, 5)])
        # The cook: a 1298 part row and a 2145 part row take their part's state,
        # a skeletal plug row (no rigid mesh) the detail draw's own cut.
        real_source, k.source = k.source, lambda install=None: files
        try:
            rows = [dict(item='demo:item/armor', slot=4, source='p.n3cpart', parts=[0]),
                    dict(item='demo:item/krowaz_upper', slot=4, part_2145='k.n3cpart', parts=[0]),
                    dict(item='demo:item/bow', slot=1, chrplug_2145='Item/b.n3chrplug')]
            textures = [[(1, 1, b'\0\0\0\xff')]]
            appearances, states, reports, weapons = ko_appearance.cook(files, rows, [[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]],
                                                                       textures, [0])
            assert states == [(0, 0.0, 0, 0), (3, 0.0, 4, 5), cut], states
            assert [r.get('render_state') for r in reports] == [[0, 0.0, 0, 0], [3, 0.0, 4, 5], None], reports
            import render_detail
            args = dict(view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100],
                        world_count=1, textures=textures, radius=1, levels=[appearances[0][1][0]] * 4,
                        appearances=appearances)
            assert render_detail.serialize(**args, states=states)[:4] == b'N3D3'
            assert render_detail.serialize(**args, states=None)[:4] == b'N3D2'
        finally:
            k.source = real_source
    finally:
        ko_appearance.ko_tiles.mip_chains = real
    print('PASS appearance parts: a corner whose normal has no direction takes its triangle\'s (PQ-281); a part '
          'without one reads as before; a part\'s render state (PQ-348: blend factors, both faces, reference 0; '
          'unlit and fog-off refused), a plug\'s detail cut, N3D3 only when a part is not opaque', flush=True)

    if '--local' in sys.argv:
        if not (g.INSTALL / 'manifest.json').is_file():
            print('SKIP --local: no 2145 install at %s' % g.INSTALL, flush=True)
            return
        import os
        os.chdir(ROOT)
        live = g.Install()
        spec = json.loads((ROOT / 'games/moradon/features.json').read_text())['equipment']['slots']
        ui = json.loads((ROOT / 'games/moradon/ui.json').read_text())['equipment_slots']
        got = k.rows(live, spec, ui, 2)
        parts = ((1, 'upper', 0), (2, 'lower', 1), (3, 'helmet', 5), (4, 'gauntlets', 3), (5, 'boots', 4))
        grades = (('normal10', 248000020), ('reverse1', 258000001), ('reverse30', 258000030))
        assert [(r['item'], r['ko_2145_item'], r['part_2145'], r['parts']) for r in got['rows']] == [
            ('demo:item/krowaz_%s_%s' % (p, grade), base + 1000 * n, 'Item/2_0802_%d0_0.n3cpart' % n, [s])
            for grade, base in grades for n, p, s in parts], got['rows']
        assert all(r.get('glow_2145_item') == (None if r['item'].endswith('normal10') else r['ko_2145_item'])
                   for r in got['rows'])
        # PQ-354: the set's heads (need race 124): the normal +10's d20000
        # "(Set item)", the reverse grades' ff83a6 "(Reverse set item)".
        assert [x['head'] for _, x in got['items'].values()] == [
            dict(name_color=0xd20000, lines=[dict(text='(Set item)', color=0xd20000)])] * 5 + [
            dict(name_color=0xff83a6, lines=[dict(text='(Reverse set item)', color=0xff83a6)])] * 10, got['items']
        source = k.source(live)
        for r in got['rows']:
            levels, _ = ko_appearance.part_levels(source, r['part_2145'], 0)
            assert len(levels) == 4 and levels[0][1], r
            # PQ-348: each part's material is blend (src_alpha / one_minus_src_alpha) and double-sided.
            assert ko_appearance.part_state(source, r['part_2145']) == (3, 0.0, 4, 5), r
        print('PASS --local: games/moradon/armour-2233.json on the player\'s 2145 install: %s, each part read '
              'from the Item pack with its render state (blend src_alpha / one_minus_src_alpha, both faces), '
              'with 005aa8e0\'s head (PQ-354)'
              % [(i, v[0], v[1]['head']['lines'][0]['text']) for i, v in got['items'].items()], flush=True)


if __name__ == '__main__':
    main()
