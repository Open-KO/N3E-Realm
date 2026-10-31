"""The 2233 client's equipment glow as N3E3 glow records (PQ-315).

A 2233/2145 addition: the pinned 1298 client has no such glow (its part draw
always zeroes the material emissive, PQ-265 B7) and stays the source of truth.
This cook runs only on request (`ko_bake.py ... --features --glow-2233`) and
reads the player's own 2145 install, unpacked by
tools/ko-reference/unpack_inno.py; nothing here is a build step.

Evidence: docs/implementation/evidence/pq-315-equipment-emissive-glow-2233.md.
2233 image (static analysis of the unpacked 2233 client, PQ-314;
binary for that image only, a secondary reference):

- CPlayerBase::Tick (0057b3a0) calls 0056ea30 for every player each tick. When
  the player byte +0x2f0 is set (its meaning is unread) it advances one timer
  per player (+0x454) and an intensity (+0x458): i = t up to 1 s, held to 3 s
  (00b96e14), 1 - (t - 3) x 0.5 from 3 to 5 s (00b91540, 00b8fab8, 00b96dd8),
  held to 5.5 s (00b96e1c), where the timer restarts.
- For each equipped part slot (+0x348, +0x34c, +0x354, +0x358, +0x35c: parts 0,
  1, 3, 4, 5) and hand plug (+0x388, +0x38c) whose item extension row has the
  byte at +0x4c equal to 11 or 12, it reads the u32 at +0x90, v = value % 100,
  and writes the emissive RGB (i when v is 0-4 or 11-20, else 1.0) and the
  stage-0 op (+0x120 / plug +0x68: MODULATE when v < 11, MODULATE2X from 11).
  A skeletal plug hands both to its inner character (0042de90 sets the colour
  and +0x354; 00430f40, from 00434980 each frame, copies the colour and the 2X
  flag to every inner part and clears their +0x11e); since PQ-337 a skeletal
  plug row (ko_chrplug_2145.rows) gets its record like any other row, and the
  client draws it on the plug's whole model.
- CN3CPart::Render (0042cf30) keeps that emissive (the part's +0x11e is
  cleared) and sets stage 0 to MODULATE or MODULATE2X from +0x120.

The item rule is 2233's (MsgRecv_UserLookChange 0052f660, lookup 004bfa20):
the base item num / 1000 x 1000 in Item_Org, the extension table Item_Org
column 2 (below 45), and the extension key (num / 10^9) x 1000 + num % 1000,
only while num / 10^9 is below 4. Struct +0x4c is Item_Ext column 8 (index 7)
and +0x90 column 45 (index 44) under the 2233 row layout (0xac bytes); the 2145
Item_Ext rows have the same size, so reading them this way is an inference (the
2145 exe is packed and unread).

n3e's own guards, not KO behaviour: an extension row whose Item_Ext column 3
(index 2; `dwBaseID` in Open-KO/KnightOnline's GameDef.h:889, source-only) is non-zero and
names a base item other than the Item_Org base belongs to that other item (for
example the '[Test]Raptor' rows 900713000.. that the Short Sword's table-22
keys reach), so it is refused; 0052f660 does not test it before 004bfa20, and
whether 2233 tests it elsewhere is unread. A mapping row's artwork must be the
2145 item's model (Item_Org column 7, the %d_%04d_%02d_%d stem), so a package
cannot claim another item's glow for its artwork; a part row may not name part 2,
which 0056ea30 reaches only through a race check n3e does not model; and the
install must be the pinned 2145 installer's unpack with every table read
matching its manifest.

Artwork of the glow package (PQ-320): an appearance row may name
`glow_2233_source`, a hand plug that only this cook draws in place of the row's
`source` (`artwork()`), so a weapon whose default artwork has no guard-passing
glowing 2145 item can carry one that has. The item, its slots and the
server's appearance key stay the row's; only the drawn mesh changes, and the
artwork guard above then checks the replacement against the 2145 item.

Name and icon of that artwork (PQ-321): such a row also names
`glow_2233_label` and `glow_2233_icon`, the name and the inventory icon of a
1298 Item_Org row whose model (column 7) is the replacement's, with that row's
name (column 3) and icon (column 8) (`presentation()`). The glow cook writes
the label into the glow package's own inventory definition (the N3I1 the
server's inventory policy and the client both read) and the icon into its own
item icon map, so the bag, tooltip and character panel show the item the hand
draws; the default cooks never read either field. 1298 binary (KnightOnLine.exe
006157b0): the icon path is UI\\ItemIcon_%.1d_%.4d_%.2d_%.1d.dxt (006d515c) of
the extension row's icon when non-zero (ext node +0x40), else the Item_Org
icon at +0x34; the model path Item\\%.1d_%.4d_%.2d_%.1d%s (006d8e28) uses +0x30.
"""
import hashlib
import json
import pathlib
import re
import sys

INSTALL = pathlib.Path('build/ko-reference/installer-2145')
INSTALLER_SHA256 = '7da88158e1ddb9c689c22d8e3cb1e8b2655d973ac21596d798104c81c30a1edf'
ORG, EXT = 'Data/Item_Org_us.tbl', 'Data/Item_Ext_{}_us.tbl'
TABLES = 45          # s_pTbl_Items_Exts[45] (00e61758); column 2 must be below it
BANDS = 4            # num / 10^9 below 4 has an extension (0052f660)
ATTRIBUTES = (11, 12)  # Item_Ext column 8 (+0x4c) values that glow
ATTRIBUTE, MODE = 7, 44  # 0-based columns 8 and 45
BASE = 2  # 0-based column 3, the extension row's own base item (dwBaseID, source-only)
# 0056ea30's timer, in seconds: rise, hold, fall, period.
RISE, HOLD, FALL, PERIOD = 1.0, 3.0, 5.0, 5.5
PARTS = (0, 1, 3, 4, 5)  # the part slots 0056ea30 drives (part 2 only by race)
GLOWS = 16  # N3E3 / N3E4 carry at most 16 glow records (appearance_effects)
MAX_MANIFEST = 64 * 1024 * 1024
ARTWORK = 'glow_2233_source'  # the glow package's artwork for a row (PQ-320)
LABEL, ICON = 'glow_2233_label', 'glow_2233_icon'  # that artwork's name and icon (PQ-321)
# 1298 Item_Org_us.tbl.csv, 0-based: id, name (column 3), model (7), icon (8).
ORG_ID, ORG_NAME, ORG_MODEL, ORG_ICON = 0, 2, 6, 7


def mode(value):
    """0056ea30's choice from Item_Ext column 45: (wave, modulate), wave 0
    steady (emissive 1.0) or 1 pulse (emissive i); modulate 1 (MODULATE) or 2
    (MODULATE2X)."""
    if type(value) is not int or value < 0:
        raise ValueError('glow mode value')
    v = value % 100
    return (1, 1) if v < 5 else (0, 1) if v < 11 else (1, 2) if v < 21 else (0, 2)


def record(key, value):
    """The N3E3 glow record of an appearance key whose item has this column 45."""
    wave, modulate = mode(value)
    timing = (RISE, HOLD, FALL, PERIOD) if wave else (0.0, 0.0, 0.0, 0.0)
    return dict(key=key, color=[1.0, 1.0, 1.0], modulate=modulate, wave=wave,
                rise=timing[0], hold=timing[1], fall=timing[2], period=timing[3])


def stem(model):
    """Item_Org column 7 as a model file stem (1298's %.1d_%.4d_%.2d_%.1d split, 006157b0)."""
    if type(model) is not int or not 0 < model < 10 ** 9:
        raise ValueError('KO model id')
    return '%d_%04d_%02d_%d' % (model // 10000000, model // 1000 % 10000, model // 10 % 100, model % 10)


class Install:
    """The player's 2145 unpack: the manifest must name the pinned installer, and
    each table read must be the file it lists."""

    def __init__(self, root=INSTALL, reader=None):
        self.root = pathlib.Path(root)
        path = self.root / 'manifest.json'
        if not path.is_file():
            raise ValueError('no 2145 install at %s: run python3 -I tools/ko-reference/unpack_inno.py '
                             'ref/ko-bin/installer/KnightOnlineSetup_v2145.exe' % self.root)
        if path.stat().st_size > MAX_MANIFEST:
            raise ValueError('%s is over the bound' % path)
        data = path.read_bytes()
        manifest = json.loads(data)
        if manifest.get('sha256') != INSTALLER_SHA256:
            raise ValueError('%s is not the pinned 2145 installer\'s unpack' % path)
        self.manifest_sha256 = hashlib.sha256(data).hexdigest()
        self.hashes = {e['path'].lower(): e['sha256'] for e in manifest['manifest']}
        if reader is None:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'ko-reference'))
            import tbl_2145 as reader
        self.reader = reader
        self.read, self._tables = {}, {}

    def table(self, name):
        """{key: row} of one 2145 table, checked against the manifest."""
        if name not in self._tables:
            path = self.root / 'client' / name
            if not path.is_file():
                raise ValueError('2145 table %s is missing' % path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if self.hashes.get(name.lower()) != digest:
                raise ValueError('%s differs from the 2145 installer\'s (manifest)' % path)
            _, _, types, rows = self.reader.load(path)
            rows_by_key = {}
            for row in rows:
                if row[0] in rows_by_key:
                    raise ValueError('%s: duplicate key %d' % (name, row[0]))
                rows_by_key[row[0]] = row
            self._tables[name] = (types, rows_by_key)
            self.read[name] = digest
        return self._tables[name]


def item(install, number):
    """The Item_Org and Item_Ext rows of a 2145 item number under 2233's rule."""
    if type(number) is not int or not 0 < number <= 0xffffffff:
        raise ValueError('KO item number')
    types, orgs = install.table(ORG)
    if len(types) < 7 or types[0] != 6 or types[1] != 2 or types[6] != 6:
        raise ValueError('2145 Item_Org columns 1, 2 and 7 are not u32, byte, u32')
    org = orgs.get(number // 1000 * 1000)
    if org is None:
        raise ValueError('2145 item %d: no Item_Org row' % number)
    table, band = org[1], number // 10 ** 9
    if not 0 <= table < TABLES or band >= BANDS:
        raise ValueError('2145 item %d has no extension (table %d, band %d)' % (number, table, band))
    types, exts = install.table(EXT.format(table))
    if len(types) <= MODE or types[0] != 6 or types[BASE] != 6 or types[ATTRIBUTE] != 2 or types[MODE] != 6:
        raise ValueError('2145 Item_Ext_%d columns 1, 3, 8 and 45 are not u32, u32, byte, u32' % table)
    ext = exts.get(band * 1000 + number % 1000)
    if ext is None:
        raise ValueError('2145 item %d: no Item_Ext_%d row %d' % (number, table, band * 1000 + number % 1000))
    # n3e's guard (not 0052f660's): a row naming another base item is that item's.
    if ext[BASE] and ext[BASE] != org[0]:
        raise ValueError('2145 item %d: Item_Ext_%d row %d belongs to base item %d, not %d (column 3)'
                         % (number, table, ext[0], ext[BASE], org[0]))
    return org, ext


def label_valid(label):
    """An inventory label as tools/assetc/inventory.py and the server accept it."""
    return type(label) is str and 1 <= len(label) <= 64 and all(32 <= ord(c) <= 126 for c in label)


def artwork(mappings):
    """The appearance rows as the --glow-2233 cook draws them (PQ-320): a row that
    names `glow_2233_source` takes that hand plug as its `source` and keeps its
    default artwork as `default_source`. Refused unless the row is a hand plug
    row (`joint`) that names `glow_2145_item` and no `ko_item` (a weapon effect
    belongs to the default artwork's item, PQ-211), and the replacement is an
    `Item/` plug of a KO model stem. Such a row must also name the replacement's
    `glow_2233_label` and `glow_2233_icon` (PQ-321), kept as `label` and `icon`
    for `presentation()`; a row without the replacement may name neither. The
    other rows are returned unchanged."""
    rows = []
    for key, row in enumerate(mappings, 1):
        if ARTWORK not in row:
            if LABEL in row or ICON in row:
                raise ValueError('appearance row %d: %s and %s name the %s artwork' % (key, LABEL, ICON, ARTWORK))
            rows.append(row)
            continue
        source = row[ARTWORK]
        if type(source) is not str or not re.fullmatch(r'Item/\d_\d{4}_\d{2}_\d\.n3cplug', source):
            raise ValueError('appearance row %d: %s must be an Item/ hand plug of a KO model stem' % (key, ARTWORK))
        if 'joint' not in row or 'glow_2145_item' not in row or 'ko_item' in row:
            raise ValueError('appearance row %d: %s needs a hand plug row with glow_2145_item and no ko_item'
                             % (key, ARTWORK))
        if LABEL not in row or ICON not in row:
            raise ValueError('appearance row %d: %s needs %s and %s (its name and icon)' % (key, ARTWORK, LABEL, ICON))
        if not label_valid(row[LABEL]):
            raise ValueError('appearance row %d: %s must be 1-64 printable ASCII characters' % (key, LABEL))
        if type(row[ICON]) is not int or not 0 < row[ICON] <= 0xffffffff:
            raise ValueError('appearance row %d: %s must be a KO icon id' % (key, ICON))
        rows.append(dict({k: v for k, v in row.items() if k not in (ARTWORK, LABEL, ICON)}, source=source,
                         default_source=row['source'], label=row[LABEL], icon=row[ICON]))
    return rows


def presentation(rows, items, icons, org_rows):
    """The glow package's inventory labels and item icons for the rows `artwork()`
    returned (PQ-321): (items, icons, report). `items` is the package's
    inventory item list (features.json `inventory.items`) and `icons` its item
    icon map (ui.json `item_icons`); both come back as new copies in which each
    replaced row's item is named and drawn as its artwork. `org_rows` are the
    1298 client's Item_Org rows (Data/Item_Org_us.tbl.csv, header first): a
    row's label and icon must be those of an Item_Org row whose model is the
    replacement's, so the name and the icon cannot claim another item. One item
    drawn by two replaced rows must name the same label and icon."""
    by_model = {}
    for org in org_rows[1:]:
        if len(org) > ORG_ICON and org[ORG_MODEL].isdigit() and org[ORG_ICON].isdigit():
            by_model.setdefault(int(org[ORG_MODEL]), []).append(org)
    chosen = {}
    for key, row in enumerate(rows, 1):
        if 'default_source' not in row:
            continue
        if 'label' not in row or 'icon' not in row:
            raise ValueError('appearance row %d: apply ko_glow_2233.artwork() first' % key)
        model = pathlib.PurePosixPath(row['source']).stem
        number = int(model.replace('_', ''))
        match = [o for o in by_model.get(number, []) if o[ORG_NAME] == row['label'] and int(o[ORG_ICON]) == row['icon']]
        if stem(number) != model or not match:
            raise ValueError('appearance row %d: no 1298 Item_Org row with model %s is named %r with icon %d'
                             % (key, model, row['label'], row['icon']))
        entry = dict(item=row['item'], label=row['label'], icon=row['icon'], item_org=int(match[0][ORG_ID]),
                     artwork=row['source'])
        if chosen.setdefault(row['item'], entry)['label'] != row['label'] or chosen[row['item']]['icon'] != row['icon']:
            raise ValueError('appearance row %d: %s is already named and drawn otherwise' % (key, row['item']))
    items = [dict(i) for i in items]
    icons = {k: dict(v) for k, v in icons.items()}
    for item, entry in chosen.items():
        definition = [i for i in items if i['id'] == item]
        if len(definition) != 1 or item not in icons:
            raise ValueError('%s has no inventory definition or item icon to replace' % item)
        entry.update(default_label=definition[0]['label'], default_icon=icons[item])
        definition[0]['label'] = entry['label']
        icons[item] = dict(base=entry['icon'], extension=0)
    return items, icons, list(chosen.values())


def cook(mappings, install=None):
    """N3E3 glow records for the appearance rows (`games/moradon/appearance.json`
    order: key = index + 1, after `artwork()`) that name `glow_2145_item`, and
    their report."""
    if any(ARTWORK in r for r in mappings):
        raise ValueError('--glow-2233: apply ko_glow_2233.artwork() to the appearance rows first')
    rows = [(i + 1, r) for i, r in enumerate(mappings) if 'glow_2145_item' in r]
    if not rows:
        raise ValueError('--glow-2233: no appearance row names glow_2145_item')
    if len(rows) > GLOWS:
        raise ValueError('--glow-2233: %d appearance rows glow; the package carries at most %d glow records'
                         % (len(rows), GLOWS))
    install = Install() if install is None else install
    records, report = [], []
    for key, row in rows:
        number = row['glow_2145_item']
        org, ext = item(install, number)
        # A skeletal plug row (PQ-337, ko_chrplug_2145.rows) draws its
        # .n3chrplug; its glow reaches the plug's inner character (0042de90,
        # 00430f40), which the client draws with the key's record.
        skeletal = 'chrplug_2145' in row
        # A 2145 armour row (PQ-319, ko_armour_2145.rows) draws the part
        # 009b3fc0 names for the item and the package's KO race and class.
        armour = 'part_2145' in row
        if skeletal and armour:
            raise ValueError('appearance row %d: a row is a skeletal plug or an armour part' % key)
        source = row['chrplug_2145'] if skeletal else row['part_2145'] if armour else row['source']
        if (skeletal or armour) and (row.get('ko_2145_item') != number or 'source' in row):
            raise ValueError('appearance row %d: a %s row glows as its own 2145 item'
                             % (key, 'skeletal plug' if skeletal else '2145 armour'))
        if not skeletal and source.lower().endswith('.n3chrplug'):
            raise ValueError('appearance row %d: a .n3chrplug is drawn only by a chrplug_2145 row' % key)
        name = pathlib.PurePosixPath(source.replace('\\', '/')).stem.lower()
        model = stem(org[6])
        if armour:
            import ko_armour_2145
            named = ko_armour_2145.resource(org, row.get('ko_race'), row.get('ko_class'))
            if source != named:
                raise ValueError('appearance row %d: %s is not 009b3fc0\'s artwork %s of 2145 item %d'
                                 % (key, source, named, number))
        elif name != model and not name.endswith('_' + model):
            raise ValueError('appearance row %d: %s is not 2145 item %d\'s model %s' % (key, source, number, model))
        if 'parts' in row and any(p not in PARTS for p in row['parts']):
            raise ValueError('appearance row %d: 0056ea30 drives parts %s only' % (key, list(PARTS)))
        if ext[ATTRIBUTE] not in ATTRIBUTES:
            raise ValueError('appearance row %d: 2145 item %d has attribute %d, not a glow (11 or 12)'
                             % (key, number, ext[ATTRIBUTE]))
        rec = record(key, ext[MODE])
        records.append(rec)
        report.append(dict(key=key, item=row['item'], slot=row['slot'], glow_2145_item=number, org=org[2],
                           **({'artwork': row['source'], 'default_artwork': row['default_source']}
                              if 'default_source' in row else {}),
                           **({'skeletal_plug': source, 'handed_to': '0042de90, 00430f40'} if skeletal else {}),
                           **({'armour_2145': source, 'parts': row['parts'], 'ko_race': row['ko_race'],
                               'ko_class': row['ko_class']} if armour else {}),
                           ext=ext[1], extension_table=org[1], extension_key=ext[0], model=model,
                           attribute=ext[ATTRIBUTE], column_45=ext[MODE], wave='pulse' if rec['wave'] else 'steady',
                           modulate=rec['modulate']))
    return records, dict(addition='2233 code (0056ea30), 2145 data', install=str(install.root),
                         installer_sha256=INSTALLER_SHA256, manifest_sha256=install.manifest_sha256,
                         tables=dict(sorted(install.read.items())), glow=report)
