"""The 2233 client's armour parts from the player's 2145 Item pack (PQ-319).

A 2233/2145 addition: the pinned 1298 client names armour artwork from the
item number (006157b0) and has no 2145 item, so it stays the source of truth
for everything else. This cook runs only on request (`ko_bake.py ...
--features --glow-2233`) and reads the player's own 2145 install, unpacked by
tools/ko-reference/unpack_inno.py, through the 2145 table reader
(tools/ko-reference/tbl_2145.py) and pack reader (pack_2145.py); nothing here
is a build step. Evidence:
docs/implementation/evidence/pq-319-equipment-glow-2145-artwork.md.

The package data is games/moradon/armour-2233.json: the KO race and class of
the package's one character profile, the equipment slots the package adds and
the inventory window area each one is, and the 2145 item numbers it carries.

2233 image (static analysis, PQ-314; binary for that image only, a secondary
reference; reading 2145 data with it is an inference, the 2145 exe being
packed):

- CGameBase::MakeResrcFileNameForUPC (009b3fc0) takes the Item_Org row's attach
  byte (+0x5a) % 100; 5-9 is an armour part, its part slot 0, 1, 5, 3, 4 (the
  upper, lower, helmet, gauntlet and boot parts). The artwork is named from the
  row's model (+0x48), not from the item number as 1298's 006157b0 does: with
  the wearer's class (+0x6b0) above 11 and its race (+0x6a4) one of 1, 2, 3, 4,
  6, 11, 12, 13, 14 (not 0, 20, 30, 50, 69, 71, 73 or 100), a class the race
  allows (RACE_CLASSES) gives 0092fd30's model + race x 1000; races 6 and 14
  get no name there; any other class gives none. The name is
  "Item\\%.1d_%.4d_%.2d_%.1d%s" (00bb20d0; "%.2d" first for an item number /
  10^9 of 1-3) of model / 10^7, model / 1000 % 10000, model / 10 % 100,
  model % 10 and ".n3cpart". A non-zero (item / 10000) % 100 takes another
  format with that number first unless the row's +0x6c is 2; n3e refuses such
  a row (n3e's guard: that branch is not mapped).
- CPlayerMySelf's PartSet override (00556370) calls it with the player's class
  and race and hands the name to CPlayerBase::PartSet (00575010), which loads
  the part into that slot. 0056ea30 then glows parts 0, 1, 3, 4 and 5 by the
  extension row (ko_glow_2233).
- 005e5a90 names why an item cannot be worn (texts 3018 race, 3028 class):
  the need-race byte (+0x5b) passes at 0, 20, 30, 50, 69, 71, 73 or above
  100, else it must be the race; the need-class byte (+0x5c) passes at 0 or
  255 (no message), else by the class groups of CLASS_KINDS (1298's 004a1750
  has the same groups for 1-12 and returns 0 with text 3028), else the class
  must be the row's kind byte (+0x58); then 00930030 refuses the kind (+0x58)
  for the class (KIND_REFUSED). The level and stat tests after it are not
  carried (n3e's package profile has no level requirement).
- The tooltip (005aa8e0) names an item on its first line (005aabab-005aadd0):
  for attributes 3, 4, 6 and 12 the Item_Ext row's name (+0x04, column 2;
  005aad74), else the Item_Org name followed by "(+%d)" (00b92a78): of column
  45 % 100 for attribute 11 (none when 0), of the extension key % 10 for the
  others but 7, 8 and 9 (10 when 0, none for attribute 0). Both pass the name
  through 004aad90, which replaces each "<selfname>" (the string 00c97274
  that 00b78c60 builds from 00b8f9f0) with the player's name ([00e61920] +
  0x684); n3e's client does that with the package token (SELF_TOKEN, N3IH,
  D-194). Its second line (005aae12-005ab045) is the item's kind, a text by
  attribute (the jump tables at 005b2510 and 005b251c: KIND_TEXTS), none for
  attribute 0, 10 or above 12, and for an Item_Org need-race byte (+0x5b) of
  101-199, a set item, text 6818 for attribute 11, else 6815
  (005aafe3-005ab02f). The texts are the player's 2145 Data/Texts_us.tbl rows
  (PQ-350). Both lines are centred and coloured (PQ-354): the name by the
  attribute through the jump table at 005b24d4 (005aac3c; NAME_COLOR_FIELD),
  replaced for a set item by +0x154 for attribute 11, else +0x138
  (005aacc4-005aacea), and the kind line by the same attribute through
  005b251c (KIND_COLOR_FIELD) and the same set override (005aaffb, 005ab016),
  so a line's colour is its name's; the fields are constants the tooltip's
  constructor (005a9160) stores (COLORS). The coin item (Item_Org 900000000)
  takes another branch that draws its count (005aaa91), so it is no package
  item here; 005aae06's skip of its kind line is never reached after it.

1298 KnightOnLine.exe (binary): the inventory window's equipment area for an
attach byte (004a1ed0): 5 area 4, 6 area 10, 7 area 1, 8 area 12, 9 area 13;
the package says which of its equipment slots each area is (ui.json
`equipment_slots` and this definition's `slots`).

Mapping onto n3e: each item is a package item worn only in its area's slot,
granted at start (no shop, no payment path), weightless and without wear or
stats (presentation only), with an appearance row that draws its 2145 part on
its part slot and, when its extension has attribute 11 or 12, a glow record.
n3e has one character profile per package, so 2233's race and class rules
are applied here, at cook time, to that profile: an item it cannot wear, or
for which 009b3fc0 gives it no artwork, is refused; the server then validates
every equip against the package's slots as for any item (D-190).
"""
import json
import pathlib

import ko_glow_2233

DEFINITION = pathlib.Path('games/moradon/armour-2233.json')
# 0-based 2145 Item_Org columns for 2233's row offsets (the field-size
# inference of ko_chrplug_2145.ORG_*, 28-byte strings): name +0x08 (column 3),
# model +0x48 (7), kind +0x58 (11), attach +0x5a (13), need race +0x5b (14),
# need class +0x5c (15).
ORG_NAME, ORG_MODEL, ORG_KIND, ORG_ATTACH, ORG_RACE, ORG_CLASS = 2, 6, 10, 12, 13, 14
EXT_KEY, EXT_NAME = 0, 1
# 009b3fc0: the part slot of an armour attach byte (*param_5).
PART_OF_ATTACH = {5: 0, 6: 1, 7: 5, 8: 3, 9: 4}
# 1298 004a1ed0: the inventory window's equipment area of an attach byte.
AREA_OF_ATTACH = {5: 4, 6: 10, 7: 1, 8: 12, 9: 13}
# 009b3fc0 (009b43bd-009b4456): the classes for which a race gets artwork.
RACE_CLASSES = {1: (101, 105, 106), 2: (102, 104, 107, 108, 111, 112), 3: (103, 109, 110),
                4: (103, 104, 109, 110, 111, 112), 6: (113, 114, 115), 11: (201, 205, 206),
                12: tuple(range(201, 213)), 13: tuple(range(201, 213)), 14: (213, 214, 215)}
NO_NAME_RACES = (6, 14)  # 009b445d-009b4469: an empty name
# 009b3fc0 (009b4382-009b439d and before): races for which it names no armour.
SKIPPED_RACES = (0, 20, 30, 50, 69, 71, 73, 100)
# 0092fd30: the race's model offset.
RACE_OFFSET = {1: 1000, 2: 2000, 3: 3000, 4: 4000, 6: 6000, 11: 11000, 12: 12000, 13: 13000, 14: 14000}
# 005e5a90: need-race bytes any race passes (and every byte above 100).
OPEN_RACE = (0, 20, 30, 50, 69, 71, 73)
# 005e5a90: the classes each need-class byte admits.
CLASS_KINDS = {1: (101, 105, 106, 113, 114, 115, 201, 205, 206, 213, 214, 215),
               2: (102, 107, 108, 202, 207, 208), 3: (103, 109, 110, 203, 209, 210),
               4: (104, 111, 112, 204, 211, 212), 5: (105, 114, 205, 214), 6: (106, 115, 206, 215),
               7: (107, 207), 8: (108, 208), 9: (109, 209), 10: (110, 210), 11: (111, 211), 12: (112, 212),
               13: (113, 114, 115, 213, 214, 215), 14: (114, 214), 15: (115, 215),
               21: (106, 108, 110, 112, 115, 206, 208, 210, 212, 215)}
NO_CLASS_TEST = (0, 255)
# 00930030: the item kinds each class group may not wear.
KIND_REFUSED = [((101, 105, 106, 201, 205, 206), (200, 220, 230, 240)),
                ((102, 107, 108, 202, 207, 208), (200, 210, 230, 240)),
                ((103, 109, 110, 203, 209, 210), (200, 210, 220, 240)),
                ((104, 111, 112, 204, 211, 212), (200, 210, 220, 230)),
                ((113, 114, 115, 213, 214, 215), (11, 12, 43, 60, 70, 71, 80, 110, 120, 130, 140, 181, 220, 230,
                                                  240))]
SUFFIX = '(+%d)'  # 00b92a78
# 005aa8e0's kind line: the text id for each Item_Ext attribute (005aae12-
# 005aafd8 through the jump tables at 005b2510 and 005b251c); for a set item
# (need race 101-199) SET_TEXTS: attribute 11's, the others' (005aafe3).
KIND_TEXTS = {1: 6808, 2: 6809, 3: 6810, 4: 6811, 5: 6812, 6: 6814, 7: 6819, 8: 6820, 9: 6820, 11: 6817, 12: 6816}
SET_RACES = range(101, 200)
SET_TEXTS = (6818, 6815)
NAME_FROM_EXT = (3, 4, 6, 12)  # 005aacef-005aad08: the Item_Ext row's own name
TEXTS = 'Data/Texts_us.tbl'
# PQ-354: 2233's tooltip colours (005a9160 stores them at these offsets of the
# tooltip, D3DCOLOR 0xAARRGGBB, all opaque), as 0xRRGGBB.
COLORS = {0x124: 0xffff00, 0x128: 0x8080ff, 0x12c: 0xdcc77c, 0x130: 0x19ffff, 0x134: 0xc87cc7, 0x138: 0xd20000,
          0x13c: 0x80ff00, 0x140: 0xffffff, 0x144: 0xff3c3c, 0x148: 0x969696, 0x14c: 0xeaf50c, 0x150: 0xcdc300,
          0x154: 0xff83a6, 0x158: 0xffad4d, 0x15c: 0xe4156b, 0x160: 0x00ffcc}
# 005aac3c: the name's colour field by attribute (the jump table at 005b24d4;
# above 12, 0x140); 005aae12: the kind line's (005b251c, the attributes that
# have one). A set item's: SET_COLOR_FIELDS (attribute 11's, the others').
NAME_COLOR_FIELD = {0: 0x140, 1: 0x128, 2: 0x124, 3: 0x13c, 4: 0x12c, 5: 0x134, 6: 0x130, 7: 0x134, 8: 0x160,
                    9: 0x160, 10: 0x140, 11: 0x154, 12: 0x158}
KIND_COLOR_FIELD = {1: 0x128, 2: 0x124, 3: 0x13c, 4: 0x12c, 5: 0x134, 6: 0x130, 7: 0x134, 8: 0x160, 9: 0x160,
                    11: 0x154, 12: 0x158}
SET_COLOR_FIELDS = (0x154, 0x138)
COIN = 900000000  # 005aaa91: the coin item's tooltip draws its count
# 2233's player-name token (00c97274, built by 00b78c60 from 00b8f9f0); the
# glow package names it as its N3IH token (D-194).
SELF_TOKEN = '<selfname>'


def resource(org, race, klass):
    """009b3fc0's armour artwork for an Item_Org row worn by race / class: the
    Item pack path ('Item/<stem>.n3cpart'). Refused when 009b3fc0 gives no
    name or takes a branch n3e does not map."""
    attach = org[ORG_ATTACH] % 100
    if attach not in PART_OF_ATTACH:
        raise ValueError('2145 item %d: attach %d is not an armour part (009b3fc0 5-9)' % (org[0], org[ORG_ATTACH]))
    model = org[ORG_MODEL]
    if type(model) is not int or not 0 < model < 10 ** 9:
        raise ValueError('2145 item %d: no model (009b3fc0 names nothing)' % org[0])
    if org[0] // 10000 % 100:
        raise ValueError('2145 item %d: the "%%.2d" prefix branch of 009b3fc0 is not mapped' % org[0])
    if type(klass) is not int or klass <= 11 or race in SKIPPED_RACES or race not in RACE_CLASSES:
        raise ValueError('race %r class %r: 009b3fc0 names no armour artwork' % (race, klass))
    if race in NO_NAME_RACES:
        raise ValueError('race %d: 009b3fc0 gives armour an empty name' % race)
    if klass not in RACE_CLASSES[race]:
        raise ValueError('race %d class %d: 009b3fc0 names no armour artwork' % (race, klass))
    m = model + RACE_OFFSET[race]
    first = '%02d' % (m // 10 ** 7) if 1 <= org[0] // 10 ** 9 <= 3 else '%d' % (m // 10 ** 7)
    return 'Item/%s_%04d_%02d_%d.n3cpart' % (first, m // 1000 % 10000, m // 10 % 100, m % 10)


def wearable(org, race, klass):
    """None when 2233's 005e5a90 and 00930030 let race / class wear the row,
    else the reason (its text id)."""
    need = org[ORG_RACE]
    if not (need in OPEN_RACE or need > 100 or need == race):
        return 'text 3018: the item is for race %d' % need
    need = org[ORG_CLASS]
    if need not in NO_CLASS_TEST:
        allowed = klass in CLASS_KINDS[need] if need in CLASS_KINDS else klass == org[ORG_KIND]
        if not allowed:
            return 'text 3028: need-class %d does not admit class %d' % (need, klass)
    if need == 255:
        return None  # 005e5a90 returns before 00930030
    for classes, kinds in KIND_REFUSED:
        if klass in classes:
            return 'text 3028: kind %d refused for class %d (00930030)' % (org[ORG_KIND], klass) \
                if org[ORG_KIND] in kinds else None
    return 'text 3028: 00930030 refuses class %d' % klass


def name(org, ext):
    """005aa8e0's first tooltip line: the Item_Ext name for attributes 3, 4, 6
    and 12, else the Item_Org name and the "(+%d)" suffix."""
    attribute = ext[ko_glow_2233.ATTRIBUTE]
    if attribute in NAME_FROM_EXT:
        return ext[EXT_NAME]
    suffix = ''
    if attribute not in (7, 8, 9):
        if attribute == 11:
            n = ext[ko_glow_2233.MODE] % 100
            suffix = SUFFIX % n if n else ''
        else:
            n = ext[EXT_KEY] % 10
            suffix = '' if n == 0 and attribute == 0 else SUFFIX % (n or 10)
    return org[ORG_NAME] + suffix


def kind_text(org, ext):
    """005aa8e0's second tooltip line, as a Texts_us.tbl id, or None (also
    for the coin item, 005aae06)."""
    attribute = ext[ko_glow_2233.ATTRIBUTE]
    if attribute not in KIND_TEXTS or org[0] == COIN:
        return None
    if org[ORG_RACE] in SET_RACES:
        return SET_TEXTS[0] if attribute == 11 else SET_TEXTS[1]
    return KIND_TEXTS[attribute]


def texts(install):
    """{id: text} of the player's 2145 Texts_us.tbl (manifest-checked)."""
    types, rows = install.table(TEXTS)
    if len(types) < 2 or types[0] != 6 or types[1] != 7:
        raise ValueError('2145 %s columns 1 and 2 are not u32 and a string' % TEXTS)
    return {k: r[1] for k, r in rows.items()}


def colors(org, ext):
    """(name colour, kind line colour or None) of 005aa8e0's head, 0xRRGGBB."""
    attribute = ext[ko_glow_2233.ATTRIBUTE]
    name_field, kind_field = NAME_COLOR_FIELD.get(attribute, 0x140), KIND_COLOR_FIELD.get(attribute)
    if org[ORG_RACE] in SET_RACES:
        name_field = SET_COLOR_FIELDS[0] if attribute == 11 else SET_COLOR_FIELDS[1]
        kind_field = kind_field and name_field
    return COLORS[name_field], kind_field and COLORS[kind_field]


def head(org, ext, kinds):
    """005aa8e0's tooltip head of a 2145 item, for the package (D-194): its
    name (the inventory label) and the N3IH head, dict(name, name_color,
    kind_text (a Texts_us.tbl id or None), lines: [dict(text, color)]);
    `kinds` is texts()."""
    if org[0] == COIN:
        raise ValueError('2145 item %d is the coin item: 005aa8e0 draws its count (005aaa91)' % org[0])
    text = name(org, ext)
    if not ko_glow_2233.label_valid(text):
        raise ValueError('2145 item %d: name %r is not an inventory label' % (org[0], text))
    kind = kind_text(org, ext)
    name_color, kind_color = colors(org, ext)
    lines = []
    if kind is not None:
        if kind not in kinds:
            raise ValueError('2145 item %d: no %s row %d (005aa8e0\'s kind line)' % (org[0], TEXTS, kind))
        if not ko_glow_2233.label_valid(kinds[kind]):
            raise ValueError('2145 item %d: kind line %r is not a tooltip line' % (org[0], kinds[kind]))
        lines.append(dict(text=kinds[kind], color=kind_color))
    return dict(name=text, name_color=name_color, kind_text=kind, lines=lines)


def label(org, ext, kinds):
    """The package label of a 2145 item: 005aa8e0's name (its kind line is the
    item's N3IH head line, head())."""
    return head(org, ext, kinds)['name']


def load(definition=DEFINITION):
    spec = json.loads(pathlib.Path(definition).read_text())
    if set(spec) != {'character', 'slots', 'items'} or set(spec['character']) != {'race', 'class'}:
        raise ValueError('armour definition')
    if not isinstance(spec['slots'], list) or not isinstance(spec['items'], list) or not 1 <= len(spec['items']) <= 16:
        raise ValueError('armour definition')
    return spec


def rows(install, slots, areas, race, definition=DEFINITION):
    """The package's 2145 armour from `definition` for a package whose
    equipment slots are `slots` (names) and whose inventory window areas are
    `areas` ({area id: slot index}, ui.json `equipment_slots`); `race` is the
    KO race of the package's player model (ko_player.RACE), which the
    definition's character must be. Returns dict(rows: appearance rows,
    items: {id: (label, report)} as ko_chrplug_2145.add_items and icons take
    them, slots: the slot names to append, areas: the merged area map,
    character)."""
    spec = load(definition)
    character = spec['character']
    if character['race'] != race:
        raise ValueError('the armour character is race %r; the package\'s player model is race %d'
                         % (character['race'], race))
    names, merged = list(slots), {str(k): v for k, v in areas.items()}
    added = []
    for slot in spec['slots']:
        if set(slot) != {'name', 'area'} or type(slot['area']) is not int or not 0 <= slot['area'] <= 13:
            raise ValueError('armour definition slot')
        if slot['name'] in names or str(slot['area']) in merged:
            raise ValueError('armour slot %r or area %d is already the package\'s' % (slot['name'], slot['area']))
        merged[str(slot['area'])] = len(names)
        names.append(slot['name'])
        added.append(slot['name'])
    if len(names) > 16:
        raise ValueError('an equipment policy has at most 16 slots')
    out, items, kinds = [], {}, texts(install)
    for entry in spec['items']:
        if set(entry) != {'id', 'ko_2145_item'} or entry['id'] in items:
            raise ValueError('armour definition item')
        number = entry['ko_2145_item']
        org, ext = ko_glow_2233.item(install, number)
        types, _ = install.table(ko_glow_2233.ORG)
        if len(types) <= ORG_CLASS or any(types[c] != 2 for c in (ORG_KIND, ORG_ATTACH, ORG_RACE, ORG_CLASS)):
            raise ValueError('2145 Item_Org columns 11, 13, 14 and 15 are not bytes')
        source = resource(org, character['race'], character['class'])
        why = wearable(org, character['race'], character['class'])
        if why:
            raise ValueError('2145 item %d: race %d class %d cannot wear it (005e5a90: %s)'
                             % (number, character['race'], character['class'], why))
        attach = org[ORG_ATTACH] % 100
        area = AREA_OF_ATTACH[attach]
        if str(area) not in merged:
            raise ValueError('2145 item %d is worn in area %d, which is no package slot' % (number, area))
        part = PART_OF_ATTACH[attach]
        row = dict(item=entry['id'], slot=merged[str(area)], parts=[part], part_2145=source, ko_2145_item=number,
                   ko_race=character['race'], ko_class=character['class'])
        glows = ext[ko_glow_2233.ATTRIBUTE] in ko_glow_2233.ATTRIBUTES
        if glows:
            row['glow_2145_item'] = number
        top = head(org, ext, kinds)
        out.append(row)
        items[entry['id']] = (top['name'], dict(
            id=org[0], name=top['name'], kind_text=top['kind_text'], head=dict(name_color=top['name_color'],
                                                                              lines=top['lines']),
            model=org[ORG_MODEL], kind=org[ORG_KIND],
            attach=org[ORG_ATTACH], need_race=org[ORG_RACE], need_class=org[ORG_CLASS], item_2145=number,
            extension_table=org[1], extension_key=ext[0], extension_name=ext[1],
            attribute=ext[ko_glow_2233.ATTRIBUTE],
            column_45=ext[ko_glow_2233.MODE], part=part, area=area, slot=names[merged[str(area)]], artwork=source,
            glow=dict(zip(('wave', 'modulate'), ko_glow_2233.mode(ext[ko_glow_2233.MODE]))) if glows else None))
    return dict(rows=out, items=items, slots=added, areas=merged, character=dict(character))


_SOURCES = {}


def source(install=None):
    """The 2145 Item pack as ko_appearance reads a part row's artwork
    (ko_chrplug_2145.Source, checked against the install's manifest)."""
    import ko_chrplug_2145
    install = install or ko_glow_2233.Install()
    key = str(install.root.resolve())
    if key not in _SOURCES:
        _SOURCES[key] = ko_chrplug_2145.Source(install)
    return _SOURCES[key]
