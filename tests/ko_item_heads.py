"""PQ-361 (D-196): 1298's item tooltip head for a package's KO items.

tools/assetc/ko_item_heads.py writes an N3IH head (D-194) for each package item
whose appearance rows name a KO item, from that item's Item_Org, Item_Ext and
Texts rows, as 1298's tooltip 004d6320 draws its first lines. On synthetic
tables this checks: the name colour for every attribute 0-7 (the constructor
004d5bd0's constants through the jump table 004dad0c; white for 0 and above 6),
the kind line for attributes 1-6 only (texts 6808-6812 and 6814 through
004dad28, in the name's colour), the type line (00614940's text for Item_Org
column 11) in white unless column 24 is 1 or 3, the line 0 text 1298 would
print, and the refusals: the coin (an Item_Org name equal to text 4533), a kind
00614940 has no text for, a missing or unprintable Texts row, a missing
Item_Org or Item_Ext row, a table column of another type, and an item whose
rows name two KO items. The expected colours and texts are written here from
the binary reading, not taken from the module.

With the local KO client data (assets/ko; SKIP without it) the
Moradon blade, KO item 120110048, gets c87cc7 "(Upgrade Item)" c87cc7 and
"One-handed Sword" ffffff, and the pair the correction names (BINARY-POLICY
"Tooltip name colour correction") is real: 120110048 and 120110068 print the
same name "Short Blade(+8)" with different colours. The cooked packages are
pinned by tests/ko_bake_pin.py and drawn by the opt-in
tests/moradon_weapon_effects_live.py.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/assetc'))
import item_heads  # noqa: E402
import ko_item_heads as k  # noqa: E402

ORG_TYPES = {1: 'UInt32', 2: 'Byte', 3: 'String', 11: 'Byte', 24: 'Byte'}
EXT_TYPES = {1: 'UInt32', 2: 'String', 8: 'Byte'}
TEXT_ROWS = {4533: 'Coin', 6808: '(Magic Item)', 6809: '(Rare Item)', 6810: '(Craft Item)', 6811: '(Unique Item)',
             6812: '(Upgrade Item)', 6813: 'Clan Co-Leader', 6814: '(Event Item)', 2529: 'One-handed Sword',
             2526: 'Shield', 2523: 'Potion'}


def table(types, width, rows):
    head = ','.join('"%d - %s"' % (c, types.get(c, 'Byte')) for c in range(1, width + 1))
    body = [','.join('"%s"' % v for v in r) for r in rows]
    return ('﻿' + '\n'.join([head] + body) + '\n').encode('utf-8')


def org_row(number, name, kind=21, countable=0, ext=1):
    row = ['0'] * 24
    row[0], row[1], row[2], row[10], row[23] = str(number), str(ext), name, str(kind), str(countable)
    return row


class Assets:
    def __init__(self, orgs, exts, texts=TEXT_ROWS, org_types=ORG_TYPES):
        self.files = {k.ORG: table(org_types, 24, orgs), k.EXT.format(1): table(EXT_TYPES, 8, exts),
                      k.TEXTS: table({1: 'UInt32', 2: 'String'}, 2, [(n, t) for n, t in texts.items()])}

    def get(self, name):
        if name not in self.files:
            raise ValueError('missing/ambiguous KO dependency: ' + name)
        return self.files[name]


def ext_row(key, attribute, name=''):
    return [str(key), name, '0', '', '0', '0', '0', str(attribute)]


def refused(call, words):
    try:
        call()
    except ValueError as error:
        assert words in str(error), (words, str(error))
        return
    raise AssertionError('not refused: ' + words)


# 004d5bd0 / 004dad0c / 004dad28, written from the binary reading.
NAME = {0: 0xffffff, 1: 0x8080ff, 2: 0xffff00, 3: 0x80ff00, 4: 0xdcc77c, 5: 0xc87cc7, 6: 0x19ffff, 7: 0xffffff}
KIND = {1: '(Magic Item)', 2: '(Rare Item)', 3: '(Craft Item)', 4: '(Unique Item)', 5: '(Upgrade Item)',
        6: '(Event Item)'}
exts = [ext_row(10 + a, a, 'Ext%d' % a) for a in range(8)]
assets = Assets([org_row(120110000, 'Short Blade')], exts)
for a in range(8):
    top, report = k.head(assets, 120110010 + a)
    want = ([dict(text=KIND[a], color=NAME[a])] if a in KIND else []) + [dict(text='One-handed Sword', color=0xffffff)]
    assert top == dict(name_color=NAME[a], lines=want), (a, top)
    # Line 0: the extension name for 3, 4 and 6; else the org name and "(+n)"
    # of the key % 10 (none for 4 and 6, or 0).
    assert report['ko_name'] == ('Ext%d' % a if a in (3, 4, 6) else 'Short Blade' + ('(+%d)' % a if a else '')), report
    # Every head is one N3IH accepts.
    item_heads.cook(dict(items=[dict(item='demo:item/blade', **top)]), 'demo', dict(items=[dict(id='demo:item/blade')]))
print('PASS 1298 tooltip head: name colour for attributes 0-7 (white at 0 and 7), kind line for 1-6 in that '
      'colour, type line in white, line 0 text by 004d6320')

for countable, drawn in ((0, True), (1, False), (2, True), (3, False)):
    a = Assets([org_row(389011000, 'Water of life', kind=97, countable=countable)], [ext_row(0, 0)])
    top, _ = k.head(a, 389011000)
    assert top['lines'] == ([dict(text='Potion', color=0xffffff)] if drawn else []), (countable, top)
print('PASS 1298 tooltip head: no type line when Item_Org column 24 is 1 or 3 (004d695e)')

refused(lambda: k.head(Assets([org_row(900000000, 'Coin', kind=0, countable=2)], [ext_row(0, 0)]), 900000000),
        'draws its count and name alone')
refused(lambda: k.head(Assets([org_row(120110000, 'Short Blade', kind=99)], exts), 120110010), 'no 00614940 type text')
refused(lambda: k.head(Assets([org_row(120110000, 'Short Blade', kind=93)], exts), 120110010), 'Texts row 2524')
missing = dict(TEXT_ROWS)
del missing[6812]
refused(lambda: k.head(Assets([org_row(120110000, 'Short Blade')], exts, missing), 120110015), 'Texts row 6812')
wide = {**TEXT_ROWS, 2529: 'One-handed\u00e9'}
refused(lambda: k.head(Assets([org_row(120110000, 'Short Blade')], exts, wide), 120110010), 'Texts row 2529')
refused(lambda: k.head(assets, 120120010), 'no Item_Org row')
refused(lambda: k.head(assets, 120110099), 'no Item_Ext_1 row 99')
refused(lambda: k.head(Assets([org_row(120110000, 'Short Blade')], exts, org_types={**ORG_TYPES, 24: 'Int16'}),
                       120110010), 'column 24 is not Byte')
refused(lambda: k.cook(assets, [dict(item='demo:item/blade', ko_item=120110015),
                                dict(item='demo:item/blade', ko_item=120110014)]), 'name KO items')
assert k.cook(assets, [dict(item='demo:item/shield')]) == (None, [])
heads, report = k.cook(assets, [dict(item='demo:item/blade', ko_item=120110015), dict(item='demo:item/shield'),
                                dict(item='demo:item/blade', ko_item=120110015)])
assert heads == dict(items=[dict(item='demo:item/blade', name_color=0xc87cc7, lines=[
    dict(text='(Upgrade Item)', color=0xc87cc7), dict(text='One-handed Sword', color=0xffffff)])]), heads
assert [r['ko_item'] for r in report] == [120110015], report
print('PASS 1298 tooltip head: refuses the coin, an unlisted kind, missing and unprintable texts, missing rows, '
      'a retyped column and two KO items for one package item; items without a KO item get no head')

CLIENT = ROOT / 'assets/ko'
if not (CLIENT / k.ORG).is_file():
    print('SKIP 1298 tooltip head of the Moradon blade: local KO client data absent')
    sys.exit(0)
import ko_character  # noqa: E402
local = ko_character.Assets(CLIENT)
rows = json.loads((ROOT / 'games/moradon/appearance.json').read_text())
heads, report = k.cook(local, rows)
assert heads == dict(items=[dict(item='demo:item/blade', name_color=0xc87cc7, lines=[
    dict(text='(Upgrade Item)', color=0xc87cc7), dict(text='One-handed Sword', color=0xffffff)])]), heads
assert report[0]['ko_name'] == 'Short Blade(+8)' and report[0]['attribute'] == 5, report
strong, record = k.head(local, 120110068)
assert record['ko_name'] == 'Short Blade(+8)' and strong['name_color'] == 0x8080ff, (strong, record)
print('PASS 1298 tooltip head of the Moradon blade (120110048, Short Blade(+8), attribute 5): c87cc7, '
      '"(Upgrade Item)" c87cc7, "One-handed Sword" ffffff; 120110068 has the same name in 8080ff')
