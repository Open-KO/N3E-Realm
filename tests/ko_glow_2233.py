"""PQ-315: the 2233 client's equipment glow cooked into N3E3, on original synthetic bytes.

Checks 0056ea30's mode choice from Item_Ext column 45 (% 100: 0-4 pulse at 1x,
5-10 steady at 1x, 11-20 pulse at 2x, 21 and up steady at 2x) and its pulse
timing, the 2233 item rule (MsgRecv_UserLookChange 0052f660: base num / 1000 x
1000, extension table Item_Org column 2 below 45, key (num / 10^9) x 1000 +
num % 1000 below band 4), the glow attribute (column 8 = 11 or 12), n3e's own
guards (an extension row whose column 3 names another base item is refused, the
artwork must be the item's model, no part 2, a skeletal plug only as its
own item (PQ-337), the
pinned install with each table as its manifest lists it), the glow package's
own artwork for a row (PQ-320, `artwork()`: glow_2233_source replaces the
drawn hand plug only in the --glow-2233 cook), the N3E3 serializer and the
client reader (build/client/n3e-effects-check) on the cooked file and on
malformed ones. No KO data is read; with --local the glow rows of
games/moradon/appearance.json (the Round Shield, and Durandal on the
two-hander) are cooked from the player's own 2145 install (SKIP without it).
"""
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/assetc'))
import appearance_effects  # noqa: E402
import ko_glow_2233 as g  # noqa: E402

CHECK = ROOT / 'build/client/n3e-effects-check'
ORG_TYPES = [6, 2, 7, 7, 6, 2, 6]
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


def ext_row(key, attribute, mode):
    row = [key, 'Line', 0, 'label'] + [0] * 41
    row[g.ATTRIBUTE], row[g.MODE] = attribute, mode
    return row


def install(root, orgs, exts, types=None, tamper=None):
    """A synthetic unpack: Data/Item_Org_us.tbl and Item_Ext_<n>_us.tbl stand-ins
    and a manifest listing their hashes."""
    files = {g.ORG: dict(types=types or ORG_TYPES, rows=orgs)}
    for table, rows in exts.items():
        files[g.EXT.format(table)] = dict(types=EXT_TYPES, rows=rows)
    entries = []
    for name, data in files.items():
        path = root / 'client' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        entries.append(dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    if tamper:
        (root / 'client' / tamper).write_text((root / 'client' / tamper).read_text() + ' ')
    (root / "manifest.json").write_text(json.dumps(dict(sha256=g.INSTALLER_SHA256, manifest=entries)))
    return g.Install(root, reader=Reader)


def main():
    # 0056ea30: column 45 % 100 chooses the wave and the modulate.
    assert [g.mode(v) for v in (0, 4, 5, 10, 11, 20, 21, 30, 99, 100, 115, 125)] == [
        (1, 1), (1, 1), (0, 1), (0, 1), (1, 2), (1, 2), (0, 2), (0, 2), (0, 2), (1, 1), (1, 2), (0, 2)]
    refused(lambda: g.mode(-1), 'glow mode value')
    assert g.record(3, 15) == dict(key=3, color=[1.0, 1.0, 1.0], modulate=2, wave=1, rise=1.0, hold=3.0,
                                   fall=5.0, period=5.5)
    assert g.record(1, 7) == dict(key=1, color=[1.0, 1.0, 1.0], modulate=1, wave=0, rise=0, hold=0, fall=0, period=0)
    assert g.stem(17025000) == '1_7025_00_0' and g.stem(24102100) == '2_4102_10_0'
    refused(lambda: g.stem(0), 'KO model id')
    print('PASS 0056ea30 mode choice (pulse/steady at 1x/2x from column 45 % 100), pulse timing 1, 3, 5, 5.5 s, '
          'model stems', flush=True)

    orgs = [[170251000, 36, 'Round Shield', '', 0, 0, 17025000],
            [126311000, 26, 'Durandal', '', 0, 0, 12631000],
            [1170251000, 36, 'Round Shield', '', 0, 0, 17025000],
            [120110000, 1, 'Short Blade', '', 0, 0, 12011000],
            [130000000, 45, 'Past the tables', '', 0, 0, 12011000],
            [4170251000, 36, 'Band four', '', 0, 0, 17025000],
            [210010000, 37, 'Armour', '', 0, 0, 22010100]]
    other = ext_row(16, 11, 7)
    other[g.BASE] = 900713000  # a row of another base item ('[Test]Raptor' in 2145)
    own = ext_row(17, 11, 7)
    own[g.BASE] = 170251000
    exts = {36: [ext_row(15, 11, 15), ext_row(1015, 12, 25), ext_row(3, 4, 15), other, own],
            1: [ext_row(48, 0, 0)], 37: [ext_row(2, 11, 3)], 26: [ext_row(11, 11, 11)]}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        inst = install(tmp / 'ok', orgs, exts)
        org, ext = g.item(inst, 170251015)
        assert org[0] == 170251000 and ext[0] == 15
        org, ext = g.item(inst, 1170251015)  # band 1: key 1000 + 15
        assert org[0] == 1170251000 and ext[0] == 1015
        refused(lambda: g.item(inst, 170251018), 'no Item_Ext_36 row 18')
        # n3e's column-3 guard: row 16 names base 900713000; row 17 names its own base.
        refused(lambda: g.item(inst, 170251016), 'belongs to base item 900713000, not 170251000 (column 3)')
        assert g.item(inst, 170251017)[1][0] == 17
        refused(lambda: g.cook([dict(item='demo:item/shield', slot=1, source='Item/1_7025_00_0.n3cplug',
                                     glow_2145_item=170251016)], inst), '(column 3)')
        refused(lambda: g.item(inst, 999000), 'no Item_Org row')
        refused(lambda: g.item(inst, 130000001), 'has no extension')
        refused(lambda: g.item(inst, 4170251015), 'has no extension')
        refused(lambda: g.item(inst, 2 ** 32), 'KO item number')
        row = dict(item='demo:item/shield', slot=1, source='Item/1_7025_00_0.n3cplug', joint=5)
        records, report = g.cook([dict(item='demo:item/blade', slot=0, source='Item/1_2011_00_0.n3cplug'),
                                  dict(row, glow_2145_item=170251015),
                                  dict(row, slot=0, glow_2145_item=1170251015)], inst)
        assert [(r['key'], r['wave'], r['modulate']) for r in records] == [(2, 1, 2), (3, 0, 2)], records
        assert report['glow'][0]['column_45'] == 15 and set(report['tables']) == {g.ORG, g.EXT.format(36)}, report
        refused(lambda: g.cook([dict(item='x', slot=0, source='Item/1_2011_00_0.n3cplug')], inst),
                'no appearance row names glow_2145_item')
        refused(lambda: g.cook([dict(row, source='Item/1_2011_00_0.n3cplug', glow_2145_item=170251015)], inst),
                "is not 2145 item 170251015's model 1_7025_00_0")
        refused(lambda: g.cook([dict(row, glow_2145_item=170251003)], inst), 'has attribute 4, not a glow')
        # PQ-350: N3E3 carries at most 16 glow records; a 17th is refused here.
        assert len(g.cook([dict(row, slot=n % 2, glow_2145_item=170251015) for n in range(16)], inst)[0]) == 16
        refused(lambda: g.cook([dict(row, slot=n % 2, glow_2145_item=170251015) for n in range(17)], inst),
                '17 appearance rows glow; the package carries at most 16 glow records')
        # PQ-337: a skeletal plug row (ko_chrplug_2145.rows: chrplug_2145, no
        # source) glows as its own 2145 item, its record drawn on the plug's
        # model (0042de90, 00430f40); a .n3chrplug named as a rigid source, a
        # skeletal row glowing as another item, and the wrong model are refused.
        skeletal = dict(item='demo:item/bow', slot=1, joint=7, group=0, chrplug_2145='Item/1_7025_00_0.n3chrplug',
                        ko_2145_item=170251015, glow_2145_item=170251015)
        records, report = g.cook([skeletal], inst)
        assert records == [g.record(1, 15)] and report['glow'][0]['skeletal_plug'] == skeletal['chrplug_2145'], report
        refused(lambda: g.cook([dict(row, source='Item/1_7025_00_0.n3chrplug', glow_2145_item=170251015)], inst),
                'a .n3chrplug is drawn only by a chrplug_2145 row')
        refused(lambda: g.cook([dict(skeletal, ko_2145_item=170251017)], inst), 'glows as its own 2145 item')
        refused(lambda: g.cook([dict(skeletal, source='Item/1_7025_00_0.n3cplug')], inst), 'glows as its own 2145 item')
        refused(lambda: g.cook([dict(skeletal, chrplug_2145='Item/1_2011_00_0.n3chrplug')], inst),
                "is not 2145 item 170251015's model 1_7025_00_0")
        part = dict(item='demo:item/armor', slot=4, source='Item/01_2_2010_10_0.n3cpart')
        records, _ = g.cook([dict(part, parts=[0], glow_2145_item=210010002)], inst)
        assert records == [g.record(1, 3)], records  # a race-prefixed part file of the model's stem
        refused(lambda: g.cook([dict(part, parts=[2], glow_2145_item=210010002)], inst), 'drives parts')
        # PQ-320: the glow package's own artwork for a row. Only artwork() puts
        # it in `source`; the row's own artwork is not the item's model.
        twohand = dict(item='demo:item/twohand', slot=0, source='Item/1_2531_00_0.n3cplug', joint=12,
                       glow_2233_source='Item/1_2631_00_0.n3cplug', glow_2233_label='Durandal',
                       glow_2233_icon=12631000, glow_2145_item=126311011)
        plain = dict(item='demo:item/blade', slot=0, source='Item/1_2011_00_0.n3cplug', joint=12)
        drawn = g.artwork([plain, twohand])
        assert drawn[0] is plain and drawn[1] == dict(
            item='demo:item/twohand', slot=0, source='Item/1_2631_00_0.n3cplug', joint=12,
            glow_2145_item=126311011, default_source='Item/1_2531_00_0.n3cplug', label='Durandal',
            icon=12631000), drawn
        assert g.artwork([plain]) == [plain] and 'glow_2233_source' in twohand  # the input is not changed
        records, report = g.cook(drawn, inst)
        assert records == [g.record(2, 11)] and records[0]['wave'] == 1 and records[0]['modulate'] == 2, records
        assert (report['glow'][0]['artwork'], report['glow'][0]['default_artwork']) == (
            'Item/1_2631_00_0.n3cplug', 'Item/1_2531_00_0.n3cplug'), report
        refused(lambda: g.cook([plain, twohand], inst), 'apply ko_glow_2233.artwork()')
        bare = {k: v for k, v in twohand.items() if k != 'glow_2233_source'}
        refused(lambda: g.cook([bare], inst), "is not 2145 item 126311011's model 1_2631_00_0")
        for bad, text in [(dict(twohand, glow_2233_source='Item/1_2631_00_0.n3cpart'), 'hand plug of a KO model'),
                          (dict(twohand, glow_2233_source='../Item/1_2631_00_0.n3cplug'), 'hand plug of a KO model'),
                          (dict(twohand, glow_2233_source=7), 'hand plug of a KO model'),
                          ({k: v for k, v in twohand.items() if k != 'glow_2145_item'}, 'needs a hand plug row'),
                          ({k: v for k, v in twohand.items() if k != 'joint'}, 'needs a hand plug row'),
                          (dict(twohand, ko_item=120110048), 'needs a hand plug row'),
                          ({k: v for k, v in twohand.items() if k != 'glow_2233_label'}, 'its name and icon'),
                          ({k: v for k, v in twohand.items() if k != 'glow_2233_icon'}, 'its name and icon'),
                          (dict(twohand, glow_2233_label=''), 'printable ASCII'),
                          (dict(twohand, glow_2233_label='x' * 65), 'printable ASCII'),
                          (dict(twohand, glow_2233_label='Durand\u00e1l'), 'printable ASCII'),
                          (dict(twohand, glow_2233_icon='12631000'), 'KO icon id'),
                          (dict(twohand, glow_2233_icon=0), 'KO icon id'),
                          (dict(twohand, glow_2233_icon=2 ** 32), 'KO icon id'),
                          (dict(plain, glow_2233_label='Durandal'), 'name the glow_2233_source artwork'),
                          (dict(plain, glow_2233_icon=12631000), 'name the glow_2233_source artwork')]:
            refused(lambda: g.artwork([bad]), text)
        # PQ-321: the replaced artwork's item is named and drawn as that artwork
        # in the glow package's own inventory and icon map, checked against a
        # 1298 Item_Org row of the artwork's model (synthetic rows: id, kind,
        # name, description, 0, 0, model, icon).
        org_1298 = [['1 - UInt32'], ['125310000', '2', 'Two-Handed Sword', '', '0', '0', '12531000', '12531000'],
                    ['126310000', '2', 'Durandal', '', '0', '0', '12631000', '12631000'],
                    ['126410000', '2', 'Mirage', '', '0', '0', '12641000', '12641000'], ['short']]
        items = [dict(id='demo:item/blade', label='Practice blade', stack_limit=1, durability=80, starting=1),
                 dict(id='demo:item/twohand', label='Two hand blade', stack_limit=1, durability=80, starting=1)]
        icons = {'demo:item/blade': dict(base=12011000, extension=0),
                 'demo:item/twohand': dict(base=12531000, extension=0)}
        named, drawn_icons, shown = g.presentation(drawn, items, icons, org_1298)
        assert named[0] == items[0] and named[1] == dict(items[1], label='Durandal'), named
        assert drawn_icons == dict(icons, **{'demo:item/twohand': dict(base=12631000, extension=0)}), drawn_icons
        assert items[1]['label'] == 'Two hand blade' and icons['demo:item/twohand']['base'] == 12531000  # copies
        assert shown == [dict(item='demo:item/twohand', label='Durandal', icon=12631000, item_org=126310000,
                              artwork='Item/1_2631_00_0.n3cplug', default_label='Two hand blade',
                              default_icon=dict(base=12531000, extension=0))], shown
        assert g.presentation([plain], items, icons, org_1298) == (items, icons, [])
        for bad, text in [(dict(twohand, glow_2233_label='Mirage'), "is named 'Mirage' with icon 12631000"),
                          (dict(twohand, glow_2233_icon=12641000), 'with icon 12641000'),
                          (dict(twohand, glow_2233_label='Two-Handed Sword', glow_2233_icon=12531000),
                           'no 1298 Item_Org row with model 1_2631_00_0'),
                          (dict(twohand, glow_2233_source='Item/1_9999_00_0.n3cplug'), 'model 1_9999_00_0')]:
            refused(lambda: g.presentation(g.artwork([bad]), items, icons, org_1298), text)
        refused(lambda: g.presentation(g.artwork([twohand]), items[:1], icons, org_1298),
                'no inventory definition or item icon')
        refused(lambda: g.presentation(g.artwork([twohand]), items, {'demo:item/blade': icons['demo:item/blade']},
                                       org_1298), 'no inventory definition or item icon')
        mirage = dict(twohand, slot=1, glow_2233_source='Item/1_2641_00_0.n3cplug', glow_2233_label='Mirage',
                      glow_2233_icon=12641000)
        refused(lambda: g.presentation(g.artwork([twohand, mirage]), items, icons, org_1298),
                'already named and drawn otherwise')
        unlabelled = {k: v for k, v in drawn[1].items() if k != 'label'}
        refused(lambda: g.presentation([unlabelled], items, icons, org_1298), 'apply ko_glow_2233.artwork() first')
        # The install: missing, another installer, a table not as its manifest
        # lists it, and a table whose layout is not the expected one.
        refused(lambda: g.Install(tmp / 'none', reader=Reader), 'no 2145 install')
        (tmp / 'other').mkdir()
        (tmp / 'other' / 'manifest.json').write_text(json.dumps(dict(sha256='0' * 64, manifest=[])))
        refused(lambda: g.Install(tmp / 'other', reader=Reader), "not the pinned 2145 installer's unpack")
        tampered = install(tmp / 'tampered', orgs, exts, tamper=g.EXT.format(36))
        refused(lambda: g.item(tampered, 170251015), "differs from the 2145 installer's")
        typed = install(tmp / 'typed', orgs, exts, types=[6, 6, 7, 7, 6, 2, 6])
        refused(lambda: g.item(typed, 170251015), 'Item_Org columns 1, 2 and 7')
    print('PASS 2233 item rule (base, extension table < 45, band key, band < 4), glow attribute 11/12, n3e\'s '
          'column-3 base, artwork and part guards, a skeletal plug row glowing as its own item (PQ-337), '
          'pinned install with manifest-checked tables, the glow '
          'package\'s own artwork for a row (glow_2233_source), its name and icon from a 1298 Item_Org row of '
          'that model (glow_2233_label, glow_2233_icon) and their refusals', flush=True)

    # The N3E3 serializer and the client reader.
    sys.path.insert(0, str(ROOT / 'tests'))
    from appearance_effects_live import n3ef as synthetic
    n3ef = synthetic()  # PQ-211's original synthetic textures and clips
    good = appearance_effects.n3e3(n3ef, [], [g.record(1, 15), g.record(2, 25)], 2)
    for bad, text in [(dict(g.record(1, 15), key=3), 'appearance glow key'),
                      (dict(g.record(1, 15), modulate=3), 'appearance glow modulate'),
                      (dict(g.record(1, 15), color=[1, 1, 2]), 'appearance glow colour'),
                      (dict(g.record(1, 15), hold=.5), 'appearance glow timing'),
                      (dict(g.record(1, 7), period=1.0), 'appearance glow timing'),
                      (dict(g.record(1, 15), wave=2), 'appearance glow wave')]:
        refused(lambda: appearance_effects.n3e3(n3ef, [], [bad], 2), text)
    refused(lambda: appearance_effects.n3e3(n3ef, [], [g.record(1, 15)] * 2, 2), 'appearance glow key')
    refused(lambda: appearance_effects.n3e3(n3ef, [], [], 2), 'count out of bounds')
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / 'effects.bin'
        path.write_bytes(good)
        p = subprocess.run([str(CHECK), str(path)], capture_output=True, text=True)
        assert p.returncode == 0 and 'PASS effects' in p.stdout, (p.stdout, p.stderr)
        record = good[-40:]
        malformed = [good + b'\0', good[:-1], good[:-84] + struct.pack('<I', 0),
                     good[:-84] + struct.pack('<I', 17) + record * 2,
                     good[:-40] + record[:4] + struct.pack('<f', 1.5) + record[8:],
                     good[:-40] + record[:16] + struct.pack('<f', 3) + record[20:],
                     good[:-40] + record[:20] + struct.pack('<I', 2) + record[24:],
                     good[:-40] + record[:24] + struct.pack('<f', 1) + record[28:],  # steady with a rise
                     good[:-80] + good[-40:] * 2, b'N3E2' + good[4:]]
        reasons = ['cooked trailing bytes', 'truncated cooked data', 'cooked count', 'cooked count',
                   'appearance glow colour', 'appearance glow modulate', 'cooked count', 'appearance glow timing',
                   'duplicate appearance glow', 'cooked count']
        for i, (data, reason) in enumerate(zip(malformed, reasons, strict=True)):
            path.write_bytes(data)
            p = subprocess.run([str(CHECK), str(path)], capture_output=True, text=True)
            assert p.returncode != 0 and reason in p.stderr, (i, reason, p.stdout, p.stderr)
    print(f'PASS N3E3 serializer refusals and the client reader on the cooked file and {len(malformed)} '
          'malformed ones', flush=True)

    if '--local' in sys.argv:
        if not (g.INSTALL / 'manifest.json').is_file():
            print('SKIP --local: no 2145 install at %s' % g.INSTALL, flush=True)
            return
        mappings = json.loads((ROOT / 'games/moradon/appearance.json').read_text())
        records, report = g.cook(g.artwork(mappings))
        assert [(r['key'], r['wave'], r['modulate']) for r in records] == [(3, 1, 2), (4, 1, 2)], records
        assert [(x['glow_2145_item'], x['model'], x.get('artwork')) for x in report['glow']] == [
            (170251015, '1_7025_00_0', None), (126311011, '1_2631_00_0', 'Item/1_2631_00_0.n3cplug')], report
        # The two-hander's own artwork is not Durandal's model: without artwork()
        # the row is refused, so the default cooks' artwork cannot carry the glow.
        refused(lambda: g.cook(mappings), 'apply ko_glow_2233.artwork()')
        bare = [{k: v for k, v in r.items() if k not in ('glow_2233_source', g.LABEL, g.ICON)} for r in mappings]
        refused(lambda: g.cook(bare), "is not 2145 item 126311011's model 1_2631_00_0")
        # PQ-321: the name and icon come from the 1298 client's Item_Org row of
        # Durandal's model (126310000: model and icon 12631000), and that icon is
        # in the 1298 client data the Moradon cook reads.
        import csv
        client = ROOT / 'assets/ko'
        org_rows = list(csv.reader((client / 'Data/Item_Org_us.tbl.csv').open(encoding='utf-8-sig')))
        features = json.loads((ROOT / 'games/moradon/features.json').read_text())
        ui = json.loads((ROOT / 'games/moradon/ui.json').read_text())
        named, icons, shown = g.presentation(g.artwork(mappings), features['inventory']['items'], ui['item_icons'],
                                             org_rows)
        assert [(x['item'], x['label'], x['icon'], x['item_org'], x['default_label'], x['default_icon']['base'])
                for x in shown] == [('demo:item/twohand', 'Durandal', 12631000, 126310000, 'Two hand blade',
                                     12531000)], shown
        sys.path.insert(0, str(ROOT / 'tools/assetc'))
        import ko_item_icons
        icon = client / ko_item_icons.path(icons['demo:item/twohand']['base'])
        found = [f for f in icon.parent.iterdir() if f.name.lower() == icon.name.lower()]
        assert len(found) == 1 and hashlib.sha256(found[0].read_bytes()).hexdigest() == (
            '9d629793814528b089e2b06bd18e1d9e35f1a8e92e638279e3463301aaf80f91'), icon
        assert [i['label'] for i in named if i['id'] == 'demo:item/twohand'] == ['Durandal']
        # The Short Sword's Item_Ext_22 row 884 glows (attribute 11) but names
        # '[Test]Raptor' (900713000) in column 3: n3e's guard refuses it.
        blade = dict(next(r for r in mappings if r['item'] == 'demo:item/blade'), glow_2145_item=120010884)
        refused(lambda: g.cook([blade]), 'belongs to base item 900713000, not 120010000 (column 3)')
        print('PASS --local: %s; 120010884 on the blade refused by the column-3 guard; the glow package names the '
              'two-hander Durandal with icon %s (1298 Item_Org 126310000)' % (json.dumps(report['glow']), found[0].name),
              flush=True)


if __name__ == '__main__':
    import os
    os.chdir(ROOT)
    main()
