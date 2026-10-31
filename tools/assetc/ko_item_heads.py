"""1298's item tooltip head for a package item that is a KO item (PQ-361, D-196).

A package item is a KO item when its appearance rows name a KO item number
(`ko_item`, PQ-211; in games/moradon the blade, 120110048). The cook reads
that item's Item_Org, Item_Ext and Texts rows from the client data the package
is cooked from (the CSV exports beside the tables, as ko_weapon_fx reads them)
and writes its N3IH head (tools/assetc/item_heads.py, D-194): the name colour,
then the kind line and the item-type line, each centred. The label stays the
package's item name; nothing here changes the inventory.

1298 KnightOnLine.exe (binary; record
docs/implementation/evidence/pq-361-item-tooltip-head-1298.md):

- 005cfe60: an item number's Item_Org row is num / 1000 x 1000, its extension
  num % 1000 in Item_Ext_<Item_Org column 2> (PQ-210).
- The tooltip's constructor 004d5bd0 stores eight D3DCOLORs at +0xb0-+0xcc
  (COLORS). The populate 004d6320 colours line 0 by the Item_Ext attribute
  (+0x34, column 8) through the jump table at 004dad0c (004d6724; COLOR_FIELD,
  white +0xc8 for 0 and above 6). For attributes 1-6 it draws line 1, the kind
  line, through the jump table at 004dad28 (004d6876): KIND_TEXTS in the same
  field's colour, skipped when the Item_Org name (+0x08, column 3) equals text
  4533 (004086d0 at 004d6830). Unless Item_Org +0x5a (column 24) is 1 or 3
  (004d695e, COUNTABLE) the next line is the item type: 00614940's text for
  Item_Org +0x40 (column 11), TYPE_TEXTS, in white +0xc8 (004d6998). Each line
  is centred (vtable +0x74 with 0x800000: 004d6469, 004d6867, 004d6976).
- The coin: when the Item_Org name equals text 4533 the populate draws "%d %s"
  (count, name) in white and nothing else (004d649d-004d65b7); n3e refuses
  such a package item (its coins are a currency, not an item).
- 00614940 leaves the text empty for a kind it does not list (it returns 0)
  and for a Texts row the table (008186e8, Data\\Texts, loaded by 006113b0)
  lacks; the line is still drawn. N3IH cannot hold an empty line, so the cook
  refuses both by name.

The Item_Org and Item_Ext column offsets above are inferred from the tables'
column types with natural alignment (16-byte strings), which the populate's
reads agree with (the name's pointer and length at +0x0c and +0x10, the
extension name at +0x04, its attribute at +0x34).

n3e difference (BINARY-POLICY "Tooltip name colour correction"): 004d66f6
stores the name colour only when line 0's current text differs from the new
name, so a second item with the same name keeps the first's colour; n3e draws
each item's own head.
"""
import csv
import hashlib
import io

ORG, EXT, TEXTS = 'Data/Item_Org_us.tbl.csv', 'Data/Item_Ext_{}_us.tbl.csv', 'Data/Texts_us.tbl.csv'
# 004d5bd0: the tooltip's colours by field (D3DCOLOR 0xAARRGGBB, all opaque), as 0xRRGGBB.
COLORS = {0xb0: 0xffff00, 0xb4: 0x8080ff, 0xb8: 0xdcc77c, 0xbc: 0x19ffff, 0xc0: 0xc87cc7, 0xc4: 0x80ff00,
          0xc8: 0xffffff, 0xcc: 0xff3c3c}
WHITE = 0xc8
# 004dad0c (name) and 004dad28 (kind line): the colour field by attribute; any
# other attribute is WHITE and has no kind line.
COLOR_FIELD = {1: 0xb4, 2: 0xb0, 3: 0xc4, 4: 0xb8, 5: 0xc0, 6: 0xbc}
KIND_TEXTS = {1: 6808, 2: 6809, 3: 6810, 4: 6811, 5: 6812, 6: 6814}  # 0x1a98-0x1a9c, 0x1a9e
COIN_TEXT = 4533  # 0x11b5, read at 004d6471 and 004d6804
COUNTABLE = (1, 3)  # 004d695e / 004d6962: no type line
# 00614940: the item-type text for an Item_Org kind (+0x40).
TYPE_TEXTS = {11: 2514, 21: 2529, 22: 2530, 31: 2507, 32: 2508, 41: 2520, 42: 2521, 51: 2527, 52: 2522,
              60: 2526, 70: 2510, 71: 2511, 80: 2512, 91: 2515, 92: 2501, 93: 2524, 94: 2509, 95: 2513,
              96: 2518, 97: 2523, 98: 2525, 100: 2519, 110: 2528, 120: 2506, 130: 2517, 210: 2505,
              220: 2504, 230: 2502, 240: 2503}
NAME_FROM_EXT = (3, 4, 6)  # 004d6775-004d6782: the Item_Ext name (+0x04)
NO_SUFFIX = (4, 6)  # 004d6625-004d6641: no "(+%d)" (006d511c) for these or a key ending in 0
SUFFIX = '(+%d)'


def _table(assets, name, columns):
    data = assets.get(name)
    rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig', errors='replace'))))
    header = rows[0] if rows else []
    for column, kind in columns.items():
        if len(header) < column or header[column - 1] != '%d - %s' % (column, kind):
            raise ValueError('%s column %d is not %s' % (name, column, kind))
    width = max(columns)
    table = {}
    for r in rows[1:]:
        if not r:
            continue
        if len(r) < width or not r[0].isdigit():
            raise ValueError('%s row %r' % (name, r[:2]))
        table[int(r[0])] = r
    return table, hashlib.sha256(data).hexdigest()


def text(texts, number, what):
    row = texts.get(number)
    t = row[1] if row else ''
    if not t or len(t) > 64 or not all(32 <= ord(c) <= 126 for c in t):
        raise ValueError('%s: Texts row %d is %r, not a tooltip line (00614940 / 00615080 would draw it empty)'
                         % (what, number, t))
    return t


def name(org, ext):
    """004d6320's line 0 for the rows: the Item_Ext name for attributes 3, 4
    and 6, else the Item_Org name and "(+%d)" of the extension key % 10 (none
    for attributes 4 and 6 or a key ending in 0)."""
    attribute = int(ext[7])
    if attribute in NAME_FROM_EXT:
        return ext[1]
    n = int(ext[0]) % 10
    return org[2] + (SUFFIX % n if n and attribute not in NO_SUFFIX else '')


def head(assets, number):
    """The 1298 tooltip head of KO item `number`: dict(name_color, lines:
    [dict(text, color)]) for N3IH, and a report of the rows it came from."""
    if type(number) is not int or not 0 < number <= 0xffffffff:
        raise ValueError('KO item number')
    orgs, org_sha = _table(assets, ORG, {1: 'UInt32', 2: 'Byte', 3: 'String', 11: 'Byte', 24: 'Byte'})
    org = orgs.get(number // 1000 * 1000)
    if org is None:
        raise ValueError('KO item %d: no Item_Org row %d' % (number, number // 1000 * 1000))
    table = int(org[1])
    exts, ext_sha = _table(assets, EXT.format(table), {1: 'UInt32', 2: 'String', 8: 'Byte'})
    ext = exts.get(number % 1000)
    if ext is None:
        raise ValueError('KO item %d: no Item_Ext_%d row %d' % (number, table, number % 1000))
    texts, texts_sha = _table(assets, TEXTS, {1: 'UInt32', 2: 'String'})
    coin = texts.get(COIN_TEXT)
    if coin and org[2] == coin[1]:
        raise ValueError('KO item %d is named %r, text %d: 004d6320 draws its count and name alone (004d649d)'
                         % (number, org[2], COIN_TEXT))
    attribute, kind, countable = int(ext[7]), int(org[10]), int(org[23])
    field = COLOR_FIELD.get(attribute, WHITE)
    lines, used = [], []
    if attribute in KIND_TEXTS:
        lines.append(dict(text=text(texts, KIND_TEXTS[attribute], 'KO item %d kind line' % number),
                          color=COLORS[field]))
        used.append(KIND_TEXTS[attribute])
    if countable not in COUNTABLE:
        if kind not in TYPE_TEXTS:
            raise ValueError('KO item %d: Item_Org kind %d has no 00614940 type text (the line would be empty)'
                             % (number, kind))
        lines.append(dict(text=text(texts, TYPE_TEXTS[kind], 'KO item %d type line' % number), color=COLORS[WHITE]))
        used.append(TYPE_TEXTS[kind])
    report = dict(ko_item=number, item_org=int(org[0]), item_ext='Item_Ext_%d row %d' % (table, number % 1000),
                  attribute=attribute, kind=kind, countable=countable, ko_name=name(org, ext), texts=used,
                  sha256={ORG: org_sha, EXT.format(table): ext_sha, TEXTS: texts_sha})
    return dict(name_color=COLORS[field], lines=lines), report


def cook(assets, rows):
    """The ``item_heads`` manifest entry for the package items whose
    appearance `rows` name a KO item (`ko_item`), in first-row order, and its
    report; None and [] when no row names one. An item's rows that name
    different KO items are refused."""
    numbers = {}
    for row in rows:
        if 'ko_item' in row:
            if numbers.setdefault(row['item'], row['ko_item']) != row['ko_item']:
                raise ValueError('%s: appearance rows name KO items %d and %d'
                                 % (row['item'], numbers[row['item']], row['ko_item']))
    items, report = [], []
    for item, number in numbers.items():
        top, record = head(assets, number)
        items.append(dict(item=item, name_color=top['name_color'], lines=top['lines']))
        report.append(dict(item=item, rule='1298 004d6320', **record, name_color='%06x' % top['name_color'],
                           lines=[(line['text'], '%06x' % line['color']) for line in top['lines']]))
    return (dict(items=items) if items else None), report
