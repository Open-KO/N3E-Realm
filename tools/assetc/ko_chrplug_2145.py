"""The 2233 client's skeletal weapon plugs (.n3chrplug) from the player's 2145
install, as N3AT plug entries (PQ-317, D-187, D-188).

A 2233/2145 addition: the pinned 1298 client has no skeletal plug and stays
the source of truth. This cook runs only on request (`ko_bake.py ... --features
--glow-2233`) and reads the player's own 2145 install, unpacked by
tools/ko-reference/unpack_inno.py, through the 2145 pack reader
(tools/ko-reference/pack_2145.py, PQ-308) and clip-table reader
(tools/ko-reference/anim_2145.py, PQ-330); nothing here is a build step.
Evidence: docs/implementation/evidence/pq-317-skeletal-weapon-plugs-2233.md.

2233 image (static analysis, PQ-314; binary for that image only, a secondary
reference; reading 2145 data with it is an inference):

- The plug file (`CN3ChrTypePlug` loads 004499e0 and 004493a0, header
  00448650): name; a u32 read and dropped; the joint (u32, +0x6c); position
  (3 f32, +0x70); a 16-f32 rotation matrix (+0x164); scale (3 f32, +0x7c); the
  92-byte material; mesh and texture names; the trace step count and, when
  above 0, three 4-byte values (the count then set to 30, 00449b3e); a mesh
  flag and, when set, an embedded progressive mesh (the FX mesh, read with the
  mesh's own load); the inner character's .n3chr name; then, only while bytes
  remain, a texture block: a u32 count and, when 1 or more, 4 bytes and five
  names (00449e43-00449e8e).
- PlugSet (00574830) makes this plug for a hand item whose Item_Org row has
  +0x90 set (CN3Chr::PlugSetNew 0043fd30), gives it a uniform scale of its
  scale y x the player's height / 1.8 (00550ab0; the double at 00b907b8) and
  the looks row's hand joint (00574b70); 0042d800 makes the plug matrix scale
  x rotation with the position times the scale.
- Each frame 00431060 copies the parent's joint matrix for that joint and
  00434980 places the inner character at plug matrix x +0x124 (identity) x
  joint x its own transform, then sets its clip (00432760 with the clip
  0042df00 maps the parent's clip index to, D-188) and ticks it on its own
  clock (00433b30 with FLT_MIN, 0042e070).

What this cook writes: the inner character's four model slots (the plug clips
the map reaches, slot 0 the plug's clip 0, which it starts on load, 00449d78),
each converted as an NPC looks clip (ko_character.convert with player=False,
so the part's render state is kept); the placement, the plug matrix at the
hand joint in engine space; and the clip map, 0042df00 applied to the KO clip
index each of the package's player clips and skill animations was cooked from.
The inner .n3chr is read to its eighth field as both 2233 character loads do;
its trailing copy of the plug record is not read (PQ-302). The FX mesh is read
(strictly, so the layout is checked) and drawn only by an item's weapon effect
(weapon_effects, PQ-339), and the texture block is
read with the rigid plug's reader (ko_appearance.texture_block, PQ-334); a
plug that names a trace texture is refused until PQ-335 draws them.

n3e's own guards, not KO behaviour: the install must be the pinned 2145
installer's unpack, and every file read (the Item pack's .hdr and .src, the
loose Chr/ files) must match its manifest; names and counts are bounded; a
collision name, plug or FX plug in the inner character is refused (n3e does
not draw them for a skeletal plug); a byte after the texture block is refused.

Glow and weapon effect (PQ-337): a row whose 2145 extension has attribute 11
or 12 glows like any other key (ko_glow_2233.cook), which 2233 hands to the
inner character (0056ea30 -> 0042de90 -> 00430f40) and the client draws on the
plug's whole model. 2233 draws a skeletal plug's weapon effect as an ordinary
plug's: CN3Chr::Render (00435440) calls the plug's vtable +0x20, 00433af0 for
CN3CPlug and CN3ChrTypePlug alike, which after the plug mesh (0042d8b0) runs
RenderFX (004304c0) on the embedded FX mesh while [WeaponEffect] EffectVisible
is set, rigid at plug matrix x joint x parent; PlugSet (00574830) sets it
through InitFX (00437510). effect() resolves it for the report;
weapon_effects() (PQ-339) gives each such row the N3E2 effect on its key: the
main bundle (the Azagai's 32120, FX bundle version 6, read by ko_fx's 2233
layout) drawn on the plug's FX mesh at the plug placement on the hand joint
(ko_weapon_fx.placed, the rigid plug's rule), with its textures from the 2145
fx pack, and its tail (32121, version 4: two mesh parts, four particle parts)
as the effect's tail clip (ko_fx_tail_2233, PQ-341). Several package items
may name one plug file (the Azagai's upgrade grades): they share one cooked
model.

The item icon (PQ-338): the 1298 client has none for a 2145-only item, so
icons() gives each skeletal plug item the 2145 icon 2233's 009b3fc0 names
(ko_item_icons.path_2233), read from the 2145 UI pack (checked against the
manifest like the Item pack), in the glow package's own icon map.
"""
import hashlib
import math
import pathlib
import shutil
import struct
import sys

import ko
import ko_appearance
import ko_character
import ko_glow_2233
import main

REFERENCE = pathlib.Path(__file__).resolve().parents[1] / 'ko-reference'
MAX_NAME = 259           # 2233 uses a name of 1-259 bytes (00448650)
SLOTS = 4                # an N3AT model's clips
HASH_CHUNK = 1 << 20
# The player clip files in the client's order (pose states 0-9,
# client/render/viewer.cpp) and ko_player's names for them.
POSE_STATES = ['idle', 'walk', 'attack', 'death', 'run', 'backward', 'ready', 'sit-down', 'sit-idle', 'stand-up']
# 2233 CPlayerBase::PlugSet (00574830): the plug's scale is its scale y times
# the player's height over this (the double at 00b907b8), as 1298's 00467b30.
HEIGHT = 1.8


def reference(name):
    if str(REFERENCE) not in sys.path:
        sys.path.insert(0, str(REFERENCE))
    return __import__(name)


def plug_clip(parent):
    """2233 0042df00: the plug clip and its once flag for the parent's clip
    index (its unsigned ranges; a negative index leaves the plug's clip as it
    was, None). Clip 4 is unreachable for an index of 0 or more."""
    if type(parent) is not int:
        raise ValueError('KO clip index')
    if parent < 0:
        return None
    if parent < 14 or 104 <= parent < 107 or 112 <= parent < 136:
        return 0, False
    if 16 <= parent < 26:
        return 5, True
    return 1, True  # 14-15, 26-103, 107-111, 136 and up


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, n):
        if n < 0 or self.at + n > len(self.data):
            raise ValueError('2145 skeletal plug truncated')
        self.at += n
        return self.data[self.at - n:self.at]

    def unpack(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))

    def name(self, empty=True):
        n = self.unpack('i')[0]
        if not (0 if empty else 1) <= n <= MAX_NAME:
            raise ValueError('2145 skeletal plug name length %d' % n)
        raw = self.take(n)
        if any(b < 32 or b > 126 for b in raw):
            raise ValueError('2145 skeletal plug name is not printable ASCII')
        return raw.decode('ascii')

    def floats(self, n):
        v = list(self.unpack('%df' % n))
        if not all(math.isfinite(x) for x in v):
            raise ValueError('2145 skeletal plug value')
        return v


# The FX mesh's extent and the texture block are the rigid plug's (PQ-334).
pmesh_length = ko_appearance.pmesh_length


def read(data):
    """The fields of a 2233 .n3chrplug (004499e0), to its last byte."""
    r = Reader(data)
    plug = dict(name=r.name())
    r.unpack('I')  # read and dropped (00448725)
    plug['stored_joint'] = r.unpack('I')[0]
    plug['position'], plug['rotation'], plug['scale'] = r.floats(3), r.floats(16), r.floats(3)
    plug['material'] = r.floats(17) + list(r.unpack('6I'))
    plug['mesh'], plug['texture'] = r.name(), r.name()
    steps = r.unpack('i')[0]
    plug['trace'] = dict(read_steps=steps, color=r.unpack('I')[0], positions=r.floats(2)) if steps > 0 else None
    flag = r.unpack('i')[0]
    plug['fx_mesh'] = None
    if flag:
        size = pmesh_length(data, r.at)
        plug['fx_mesh'] = ko.import_mesh(None, 1.0, data=r.take(size))
        plug['fx_mesh_bytes'] = size
    plug['chr'] = r.name(empty=False)
    plug['textures'], r.at = ko_appearance.texture_block(data, r.at)
    if r.at != len(data):
        raise ValueError('2145 skeletal plug: %d bytes after the texture block' % (len(data) - r.at))
    return plug


def placement(plug, height):
    """The plug matrix at the hand joint (0042d800 with 00574830's uniform
    scale), as the rows of a 3x4 in engine space (Z reflected), the frame n3e's
    rigid plugs use (ko_appearance.plug_transform: 004133c0, 004137d0)."""
    rotation, position, scale = plug['rotation'], plug['position'], plug['scale']
    if min(scale) <= 0 or not 0 < height <= 100:
        raise ValueError('2145 skeletal plug scale')
    factor = height / HEIGHT * scale[1]
    z = (1, 1, -1)
    rows = []
    for i in range(3):
        # Row-vector rotation (v' = v R) as a column-vector matrix: R transposed.
        rows += [factor * z[i] * rotation[j * 4 + i] * z[j] for j in range(3)] + [factor * z[i] * position[i]]
    return rows, factor


class Source:
    """The files a skeletal plug's inner character names: `item\\...` from the
    2145 Item pack and `chr\\...` from the loose Chr/ folder, each checked
    against the install's manifest; a clip table is opened by anim_2145 and
    handed on in the 1298 layout. With `pack='UI'` it reads `ui\\...` from the
    2145 UI pack instead (the item icons, PQ-338), with `pack='fx'` `fx\\...`
    from the 2145 fx pack (the weapon effect bundles, PQ-337). Records each
    file read (`sources`)."""

    namespace = '2145'  # ko_hud keeps its textures apart from the 1298 client's

    def __init__(self, install, pack='Item'):
        if pack not in ('Item', 'UI', 'fx'):
            raise ValueError('2145 pack %r' % pack)
        self.install = install
        self.client = install.root / 'client'
        self.sources, self.last = {}, None
        self.name, self.folder = pack, pack.lower()
        for name in ('%s/%s.hdr' % (pack, self.folder), '%s/%s.src' % (pack, self.folder)):
            self.checked(name)
        self.pack = reference('pack_2145').Pack(self.client / ('%s/%s.hdr' % (pack, self.folder)))

    def checked(self, name):
        path = self.client / name
        if not path.is_file():
            raise ValueError('2145 file %s is missing' % path)
        digest = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(HASH_CHUNK), b''):
                digest.update(block)
        if self.install.hashes.get(name.lower()) != digest.hexdigest():
            raise ValueError('%s differs from the 2145 installer\'s (manifest)' % path)
        self.sources[name] = digest.hexdigest()
        return path

    def get(self, name):
        self.last = name
        parts = name.replace('/', '\\').split('\\')
        # The fx pack keeps its textures in folders (fx\\billboard\\...\\x.dxt,
        # PQ-339); the other packs and Chr/ are one level deep.
        deep = self.folder == 'fx' and parts[0].lower() == 'fx'
        if (len(parts) != 2 and not (deep and len(parts) > 2)) or any(not p or p in ('.', '..') for p in parts[1:]):
            raise ValueError('2145 dependency %r' % name)
        folder, file = parts[0].lower(), '\\'.join(parts[1:])
        if folder == self.folder:
            if self.pack.find(file) is None:
                raise ValueError('the 2145 %s pack has no %s' % (folder, file))
            data = self.pack.read(file)
            self.sources['%s/%s' % (self.name, file.lower())] = hashlib.sha256(data).hexdigest()
        elif folder == 'chr' and self.folder == 'item':
            found = [p for p in (self.client / 'Chr').iterdir() if p.name.casefold() == file.casefold()]
            if len(found) != 1:
                raise ValueError('missing/ambiguous 2145 file Chr/%s' % file)
            data = self.checked('Chr/' + found[0].name).read_bytes()
        else:
            raise ValueError('2145 dependency %r outside %s' % (name, 'Item and Chr' if self.folder == 'item' else self.name))
        if file.lower().endswith('.n3anim'):
            anim = reference('anim_2145')
            data = anim.to_1298(anim.parse(data)[1])
        return data


def clip_map(clips, player, skills):
    """The plug's clip map rows and model slots for the package's player clips
    (`player`: {'states': {pose state name: KO clip index}, 'combat': [KO clip
    index of each combat-animation clip]}) and skill animations (`skills`:
    {package animation id: KO clip index}), through 0042df00. `clips` is the
    plug character's clip count. Returns (rows, slots: the plug clip index each
    model slot plays)."""
    slots = [0]  # the plug starts its clip 0 (00449d78)
    rows = []

    def row(kind, ident, parent):
        mapped = plug_clip(parent)
        if mapped is None:
            return
        clip, once = mapped
        if clip >= clips:
            return  # 00432760 ignores an index past the table
        if clip not in slots:
            slots.append(clip)
        rows.append(dict(kind=kind, id=ident, slot=slots.index(clip), once=once))
    for state, name in enumerate(POSE_STATES):
        if name in player['states']:
            row('state', state, player['states'][name])
    for i, parent in enumerate(player['combat']):
        row('combat', i, parent)
    for animation, parent in sorted(skills.items()):
        row('skill', animation, parent)
    if len(slots) > SLOTS:
        raise ValueError('a skeletal plug reaches %d clips; an N3AT model has %d' % (len(slots), SLOTS))
    return rows, slots + [slots[0]] * (SLOTS - len(slots))


def cook(row, player, skills, height, root, work, install=None):
    """One N3AT plug entry for an appearance row naming `chrplug_2145` (an Item
    pack .n3chrplug). `player` and `skills` as clip_map takes them; `height` is
    the player's height (ko_detail's maximum bind joint y); the model's four
    clip sources are written under `root` (attachment-src/), work files under
    `work`. Returns (entry, report)."""
    install = install or ko_glow_2233.Install()
    source = Source(install)
    name = row['chrplug_2145'].replace('/', '\\')
    if not name.lower().startswith('item\\') or not name.lower().endswith('.n3chrplug'):
        raise ValueError('chrplug_2145 must name an Item pack .n3chrplug')
    data = source.get(name)
    plug = read(data)
    if plug['mesh'] or plug['texture']:
        raise ValueError('2145 skeletal plug %s: a plug mesh or texture n3e does not draw' % name)
    ko_appearance.default_traces(plug['textures'], '2145 skeletal plug ' + name)
    inner = ko_character.character(source.get(plug['chr']), strict=False, trailing=True)
    if any(inner['collision']) or any(inner['extras']):
        raise ValueError('2145 skeletal plug %s: collision or FX names in %s' % (name, plug['chr']))
    clips = ko_character.animations(source.get(inner['animation']))
    rows, slots = clip_map(len(clips), player, skills)
    entry_clips, records = [], []
    for slot, index in enumerate(slots):
        target = work / ('slot-%d' % slot)
        if target.exists():
            shutil.rmtree(target)
        report = ko_character.convert(source.client, plug['chr'], target, index, 1.0, definition=inner,
                                      player=False, assets=source)
        main.cook(target, target / 'cooked', materials=True)
        clip = ko_character.animation_metadata(report)
        # 00434980 sets the clip with a FLT_MIN blend (00b906d4): no blend.
        clip.update(blend=0.0, loop_blend=False)
        out = root / 'attachment-src' / ('%s-%d.bin' % (pathlib.PurePath(name.replace('\\', '/')).stem, slot))
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target / 'cooked' / 'scene.bin', out)
        entry_clips.append(dict(source=out.relative_to(root).as_posix(), **clip))
        records.append(dict(slot=slot, ko_clip=index, name=clips[index]['name'], start=clips[index]['start'],
                            end=clips[index]['end'], fps=clips[index]['fps'], duration=clip['duration']))
    rows_placed, factor = placement(plug, height)
    entry = dict(item=row['item'], slot=row['slot'], joint=row['joint'], scale=1.0, group=row['group'],
                 plug=dict(placement=rows_placed, clips=rows), clips=entry_clips)
    report = dict(
        plug=name, plug_sha256=hashlib.sha256(data).hexdigest(), character=plug['chr'],
        stored_joint=plug['stored_joint'], joint=row['joint'], position=plug['position'], scale=plug['scale'],
        factor=factor, height=height, trace=plug['trace'], textures=plug['textures'],
        fx_mesh=None if plug['fx_mesh'] is None else dict(vertices=len(plug['fx_mesh']['vertices']),
                                                          indices=len(plug['fx_mesh']['indices']),
                                                          drawn='by an item weapon effect (PQ-339)'),
        inner_unread_bytes=inner['unread'], inner=dict(joint=inner['joint'], parts=inner['parts'],
                                                       animation=inner['animation']),
        clips=[dict(name=c['name'], start=c['start'], end=c['end'], fps=c['fps']) for c in clips],
        slots=records, clip_map=rows, sources=source.sources, install_manifest_sha256=install.manifest_sha256,
        rule='0042df00 for every wearer (D-188)')
    return entry, report


# 0-based 2145 Item_Org columns (PQ-302; the mapping of 2233's row offsets onto
# them is an inference: 2233's row is 0x98 bytes, 2145's 0x94): the name
# (column 3), the model (7), the attach point (13, 2233 +0x5a) and the
# skeletal-plug selector (40, 2233 +0x90).
ORG_NAME, ORG_MODEL, ORG_ATTACH, ORG_SKELETAL = 2, 6, 12, 39
# The range (column 18, a short): the field 1298's client reads at item +0x4a
# for the archery range (00583780) and the melee reach (00468620), on 1298's
# Item_Org layout, which 2145's matches up to column 20 by field sizes (an
# inference, as for ORG_*; PQ-416).
ORG_RANGE = 17
# PQ-422 (D-219): the damage (column 16) and the durability (column 20),
# shorts: on the 11 kind-70 bows both 1298's Item_Org and the OpenKO ITEM
# table hold, columns 16, 17, 18 and 20 are ITEM's Damage, Delay, Range and
# Duration (local-asset), the fields Ebenezer's item sum 0049e11c and weapon
# attack 004a0d2a read at item +0x3a and the slot's durability.
ORG_DAMAGE, ORG_DURABILITY = 15, 19
# PQ-434 (D-221): the upgrade's bonuses, Item_Ext columns 9 and 13 (shorts),
# which both clients' tooltips add to Item_Org columns 16 and 20 (1298
# 004d6320: Item_Org +0x46 + Item_Ext +0x36, +0x4e + +0x3e; 2233 005aa8e0:
# +0x5e + +0x4e at 005abbed, +0x66 + +0x56 at 005ac37e) and that 1298's
# per-number ITEM row carries in Damage and Duration (Ebenezer 0041f077 ->
# record +0x3a; OpenKO ITEM, local-asset). The column mapping is PQ-314's
# row-layout inference.
EXT_DAMAGE, EXT_DURABILITY = 8, 12
DEFINITION = pathlib.Path('games/moradon/skeletal-plugs-2233.json')


def hand_slot(attach):
    """2233 MakeResrcFileNameForUPC (009b3fc0): a hand item's plug slot from
    its attach byte % 100: 0, 1 and 3 slot 0, 2 and 4 slot 1 (009b411e,
    009b4116); None otherwise."""
    attach %= 100
    return 0 if attach in (0, 1, 3) else 1 if attach in (2, 4) else None


def rows(install, definition=DEFINITION):
    """The package's skeletal plug rows (games/moradon/skeletal-plugs-2233.json),
    each checked against its 2145 Item_Org row: the selector set (column 40),
    the model the plug file is named for (column 7), and the hand slot its
    attach point gives (column 13). Its Item_Ext row is the one 2233's item
    rule reaches (ko_glow_2233.item: num / 10^9 x 1000 + num % 1000, with n3e's
    column-3 guard), so one plug can stand for several item numbers, such as
    the Azagai's upgrade grades (PQ-337). A row whose extension has attribute 11
    or 12 names its own item as `glow_2145_item`, for ko_glow_2233.cook (2233
    0056ea30 drives the plug for whatever item number is worn); its weapon
    effect is resolved by the 2233 rule (effect()). The label is 2233's
    tooltip name (005aa8e0, ko_armour_2145.head): the Item_Ext name for
    attributes 4 and 12 (a normal and a reverse unique grade carry the same
    one); the kind line, "(Unique Item)" or "(Reverse unique item)", that tells
    them apart is the item's N3IH head line, in its colour (PQ-354, D-194).
    Returns (appearance rows, items: {id: (label, the row)})."""
    spec = __import__('json').loads(pathlib.Path(definition).read_text())
    if set(spec) != {'items'} or not isinstance(spec['items'], list) or not 1 <= len(spec['items']) <= 16:
        raise ValueError('skeletal plug definition')
    import ko_armour_2145
    out, items, kinds = [], {}, ko_armour_2145.texts(install)
    types, _ = install.table(ko_glow_2233.ORG)
    if len(types) <= ko_armour_2145.ORG_RACE or types[ko_armour_2145.ORG_RACE] != 2:
        raise ValueError('2145 Item_Org column 14 is not a byte')
    if types[ko_armour_2145.ORG_KIND] != 2:
        raise ValueError('2145 Item_Org column 11 (the kind) is not a byte')
    for item in spec['items']:
        if set(item) != {'id', 'ko_2145_item', 'source', 'slot', 'joint', 'group'} or item['id'] in items:
            raise ValueError('skeletal plug definition item')
        number = item['ko_2145_item']
        if type(number) is not int or not 0 < number <= 0xffffffff:
            raise ValueError('skeletal plug definition item number')
        _, orgs = install.table(ko_glow_2233.ORG)
        org = orgs.get(number // 1000 * 1000)
        if org is None or len(org) <= ORG_SKELETAL:
            raise ValueError('2145 item %d: no Item_Org row with column 40' % number)
        stem = ko_glow_2233.stem(org[ORG_MODEL])
        expected = 'Item/%s.n3chrplug' % stem
        if org[ORG_SKELETAL] != 1:
            raise ValueError('2145 item %d: column 40 is %r, so 2233 draws its .n3cplug' % (number, org[ORG_SKELETAL]))
        if item['source'] != expected:
            raise ValueError('2145 item %d draws %s, not %s' % (number, expected, item['source']))
        if hand_slot(org[ORG_ATTACH]) != item['slot']:
            raise ValueError('2145 item %d is a plug slot %r item, not slot %r' % (
                number, hand_slot(org[ORG_ATTACH]), item['slot']))
        _, ext = ko_glow_2233.item(install, number)
        ext_types, _ = install.table(ko_glow_2233.EXT.format(org[1]))
        if len(ext_types) <= EXT_DURABILITY or ext_types[EXT_DAMAGE] != 3 or ext_types[EXT_DURABILITY] != 3:
            raise ValueError('2145 Item_Ext_%d columns 9 and 13 (the attack and durability bonuses) are not shorts'
                             % org[1])
        top = ko_armour_2145.head(org, ext, kinds)
        label = top['name']
        row = dict(item=item['id'], slot=item['slot'], joint=item['joint'], group=item['group'],
                   chrplug_2145=item['source'], ko_2145_item=number)
        glows = ext[ko_glow_2233.ATTRIBUTE] in ko_glow_2233.ATTRIBUTES
        if glows:
            row['glow_2145_item'] = number
        out.append(row)
        if types[ORG_RANGE] != 3:
            raise ValueError('2145 Item_Org column 18 (the range) is not a short')
        if types[ORG_DAMAGE] != 3 or types[ORG_DURABILITY] != 3:
            raise ValueError('2145 Item_Org columns 16 and 20 (the damage, the durability) are not shorts')
        items[item['id']] = (label, dict(
            id=org[0], name=label, kind_text=top['kind_text'], range=org[ORG_RANGE],
            damage=org[ORG_DAMAGE], durability=org[ORG_DURABILITY],
            damage_bonus=ext[EXT_DAMAGE], durability_bonus=ext[EXT_DURABILITY],
            head=dict(name_color=top['name_color'], lines=top['lines']), model=org[ORG_MODEL],
            kind=org[ko_armour_2145.ORG_KIND], attach=org[ORG_ATTACH], skeletal=org[ORG_SKELETAL], item_2145=number, extension_table=org[1], extension_key=ext[0], attribute=ext[ko_glow_2233.ATTRIBUTE],
            column_45=ext[ko_glow_2233.MODE],
            glow=dict(zip(('wave', 'modulate'), ko_glow_2233.mode(ext[ko_glow_2233.MODE]))) if glows else None,
            effect=effect(install, number)))
    return out, items


# 2233's weapon effect rule (0056bb50, then CPlayerBase::PlugSet 00574830) on
# the 2145 columns, 0-based: Item_Org +0x58 column 11 (the class) and +0x78
# column 26 (the effect base); Item_Ext +0x20 column 3, +0x40 column 5 (the
# effect id) and +0x6a-+0x6c columns 23-25 (fire, ice, lightning). The mapping
# of 2233's row offsets onto the 2145 columns is the field-size inference of
# ORG_* and EXT_* (28-byte strings), as for ko_glow_2233's +0x4c and +0x90.
ORG_CLASS, ORG_EFFECT = 10, 25
EXT_NAME, EXT_BASE, EXT_EFFECT, EXT_FIRE = 1, 2, 4, 22
FX_TABLE = 'Data/fx.tbl'
# CPlayerBase::PlugSet (00574830): the trace colour when either bundle is found,
# by Item_Ext +0x4c (column 8) and +0x6a-+0x6d (columns 23-26): fire, ice,
# lightning, poison, the first that is non-zero on an attribute 4, 6, 11 or 12
# item or above 63, else white. Carried for the swing trail (not drawn, PQ-335).
TRACE_ATTRIBUTES = (4, 6, 11, 12)
TRACE_COLORS = (0xffffff00, 0xffb4c8ff, 0xff1e96f0, 0xffff00ff)


def trace_color(attribute, elements):
    for value, color in zip(elements, TRACE_COLORS):
        if (attribute in TRACE_ATTRIBUTES and value) or value > 63:
            return color
    return 0xffffffff


def effect(install, number):
    """The weapon effect 2233 gives a hand plug of 2145 item `number`, for the
    report (PQ-337): PlugSet (00574830) takes 0056bb50's id (Item_Org column 26
    / 1000, for a staff plus 0, 10 or 20 by its largest element, for another
    class only when Item_Ext column 3 is 0), else Item_Ext column 5, looks the
    id and id + 1 up in fx.tbl (004c9800) and calls InitFX (00437510) when either
    is found. The bundles are named and their version read from the player's
    2145 fx pack; weapon_effects() draws them (PQ-339, PQ-341). None when no
    row is found."""
    import ko_fx
    import ko_weapon_fx
    org, ext = ko_glow_2233.item(install, number)
    types, _ = install.table(ko_glow_2233.ORG)
    ext_types, _ = install.table(ko_glow_2233.EXT.format(org[1]))
    if (len(types) <= ORG_EFFECT or types[ORG_CLASS] != 2 or types[ORG_EFFECT] != 6
            or len(ext_types) <= EXT_FIRE + 3 or ext_types[EXT_BASE] != 6 or ext_types[EXT_EFFECT] != 6
            or any(ext_types[EXT_FIRE + k] != 2 for k in range(4))):
        raise ValueError('2145 item %d: the weapon effect columns are not u32 and bytes' % number)
    main = ko_weapon_fx.effect_id(
        {'class': org[ORG_CLASS], 'effect_base': org[ORG_EFFECT]},
        dict(effect=ext[EXT_EFFECT], restriction=ext[EXT_BASE], fire=ext[EXT_FIRE], ice=ext[EXT_FIRE + 1],
             lightning=ext[EXT_FIRE + 2]))
    fx_types, fx = install.table(FX_TABLE)
    if len(fx_types) < 3 or fx_types[0] != 6 or fx_types[2] != 7:
        raise ValueError('2145 fx.tbl columns 1 and 3 are not u32 and a string')
    found = {i: fx[i][2] for i in (main, main + 1) if i in fx}
    if not found:
        return None
    pack = Source(install, pack='fx')
    bundles = {}
    for i, name in found.items():
        data = pack.get(name)
        # PQ-339: 2233's bundle load (0057f0b0) and part loads (ko_fx 2233 layout).
        bundle = ko_fx.bundle(data, '2233')
        bundles[i] = dict(file=name, version=bundle['version'], sha256=hashlib.sha256(data).hexdigest(),
                          parts=[[k, p['kind'], p['version'], p['base']] for k, p in zip(bundle['part_slots'],
                                                                                         bundle['parts'])],
                          unread=bundle['unread'])
    return dict(rule='0056bb50 (2233), else Item_Ext column 5; fx.tbl id and id + 1 (004c9800)', main_id=main,
                main=bundles.get(main), tail_id=main + 1, tail=bundles.get(main + 1),
                trace_color='%08x' % trace_color(ext[ko_glow_2233.ATTRIBUTE], ext[EXT_FIRE:EXT_FIRE + 4]),
                drawn=False, reason='weapon_effects() decides')


def weapon_effects(mappings, items, world, height, install):
    """PQ-339: the N3E2 weapon effect of each skeletal plug row whose item has
    one (effect(), in `items` as rows() returns them), for ko_fx_bake.cook:
    2233 draws it rigid on the hand joint at the plug matrix (CN3Chr::Render
    00435440 -> vtable +0x20 00433af0 -> RenderFX 004304c0 on the embedded FX
    mesh), so its geometry is ko_weapon_fx.placed on the .n3chrplug's FX mesh
    at the plug's placement on the bind joint (`world`, ko_detail.bind_world;
    `height`, its largest y). A row's key is its 1-based place in `mappings`.
    The main bundle is drawn (ko_fx_bake.main_2233 refuses fields it does not
    draw) and so is the tail (PQ-341: ko_fx_tail_2233 refuses what it does not
    draw, which fails the cook). Each item's report `effect` is updated with
    what was drawn. Returns (specs, report)."""
    import ko_weapon_fx
    specs, report, plugs, fx = [], [], {}, None
    for key, row in enumerate(mappings, 1):
        if 'chrplug_2145' not in row:
            continue
        resolved = items[row['item']][1]['effect']
        if resolved is None or resolved['main'] is None:
            continue
        name = row['chrplug_2145']
        if name not in plugs:
            plugs[name] = read(Source(install).get(name.replace('/', '\\')))
        plug = plugs[name]
        if plug['fx_mesh'] is None:
            # 004304c0 draws nothing without the FX mesh (00466680 returns 0).
            resolved.update(drawn=False, reason='the plug has no FX mesh (004304c0 draws nothing)')
            continue
        if not 0 <= row['joint'] < len(world):
            raise ValueError('skeletal plug joint %d' % row['joint'])
        fx = fx or Source(install, pack='fx')
        geometry = ko_weapon_fx.placed(plug, plug['fx_mesh'], world[row['joint']], height)
        specs.append(dict(key=key, joint=row['joint'], ko_item=row['ko_2145_item'], layout='2233', assets=fx,
                          main=resolved['main']['file'], main_id=resolved['main_id'],
                          tail=(resolved['tail'] or {}).get('file'),
                          tail_id=resolved['tail_id'], trace_color=int(resolved['trace_color'], 16),
                          geometry=geometry))
        resolved.update(drawn=dict(main=True, tail=bool(resolved['tail'])), reason=None)
        report.append(dict(item=row['item'], key=key, ko_2145_item=row['ko_2145_item'], plug=name,
                           main=resolved['main']['file'], tail=(resolved['tail'] or {}).get('file'),
                           fx_vertices=geometry['fx_vertices'], fx_triangles=geometry['fx_triangles'],
                           tail_box=geometry['tail_box'], tail_drawn=bool(resolved['tail'])))
    return specs, dict(effects=report, sources=fx.sources if fx else {},
                       rule='00433af0 -> 004304c0 at plug matrix x joint x parent (ko_weapon_fx.placed)')


def add_items(manifest, items, slot_of):
    """Adds each skeletal plug item to the package: a starting item (granted
    by the package; no shop offers it, no payment path), worn only in its hand
    slot, weightless, with no wear and no stats (presentation only). The
    server validates every equip against this policy as for any item. Its
    2233 tooltip head (the name's colour and the kind line, PQ-354) goes into
    the package's N3IH heads, whose token is 2233's "<selfname>"
    (ko_armour_2145.SELF_TOKEN): client presentation only (D-194)."""
    import ko_armour_2145
    heads = manifest.setdefault('item_heads', dict(self_token=ko_armour_2145.SELF_TOKEN, items=[]))
    for item, (label, row) in items.items():
        manifest['inventory']['items'].append(dict(id=item, label=label, stack_limit=1, durability=0, starting=1))
        heads['items'].append(dict(item=item, name_color=row['head']['name_color'], lines=row['head']['lines']))
        manifest['equipment']['items'].append(dict(id=item, slots=[slot_of[item]], blocks=[], race=0, title=0,
                                                   attributes=[0] * 5, swappable=False))
        manifest['commerce']['items'].append(dict(id=item, weight=0, price=1, sell_divisor=10000))
        manifest['wear']['items'].append(dict(id=item, attack_slots=[], defense_slots=[]))
        manifest['stats']['items'].append(dict(id=item, category='demo:weapon/none', attack=0, defense=0, health=0,
                                               resource=0, accuracy=0, evasion=0, attributes=[0] * 5))


# PQ-347: the combat profile 1298 gives a bow in the left hand (KnightOnLine.exe,
# SHA-256 828ab0db...). The ready clip (0045bfe0): with the right hand empty
# (kind -1) a left-hand kind 70 is clip 92 (a kind 80 long bow there is the
# shield's 98, a right-hand kind 71 crossbow 93: kinds this package does not
# carry, so refused). The basic attack: the player tick's attack tick
# (004659b0, 00465fd5) casts the archery skill of the player's class instead of
# swinging (00466010-00466052: class 102, 107, 108, 202, 207, 208 -> class x
# 1000 + 3; any other class finds no skill and never attacks), due when the
# skill row's cast time (+0x78) x 0.1 (006a40d8) + 0.15 (006a41e0) seconds
# have passed since the last (004660b4-004660d9; divided by an attack speed
# above 0, which n3e does not model); the cast (005819e0 -> 00583f20) plays the
# row's start animation (+0x34, 005844cd) and stops the walk (005844c2). The
# rows are 1298's Skill_Magic_Main_us.tbl, columns 5 (+0x34) and 22 (+0x78).
BOW_KIND, BOW_READY = 70, 92
ARCHERY_CLASSES = (102, 107, 108, 202, 207, 208)
SKILL_TABLE = 'Data/Skill_Magic_Main_us.tbl.csv'
SKILL_ANIMATION, SKILL_CAST = 4, 21


def combat_rows(config, equipment_slots, items, slot_of, skill_csv, character_class):
    """The combat-animation rows (games/moradon/combat-animation.json's `rows`
    form) that select the profile named 'bow' for each skeletal plug item
    (`items`, as rows() returns them) worn alone in the left hand, checked
    against 1298's rules above: the item's 2145 Item_Org kind (column 11) must
    be 70, its slot the left hand with the right hand a selector, and the
    profile must be 1298's 0045bfe0 ready clip 92 with the class's archery row's
    start animation as its attack (and its moving attack: the cast stops the
    walk, so KO has no moving variant) and cast time x 100 + 150 ms as its
    interval. `skill_csv` is the 1298 client's Skill_Magic_Main_us.tbl.csv
    text, `character_class` the package character's KO class. Returns (rows,
    report)."""
    import csv
    import io
    if character_class not in ARCHERY_CLASSES:
        raise ValueError('KO class %r has no archery skill in 1298 (004659b0 casts nothing)' % (character_class,))
    skill = character_class * 1000 + 3
    table = {r[0]: r for r in csv.reader(io.StringIO(skill_csv)) if r and r[0].isdigit()}
    row = table.get(str(skill))
    if row is None or len(row) <= SKILL_CAST:
        raise ValueError('1298 %s has no archery row %d' % (SKILL_TABLE, skill))
    # The package's bows are kind 70 with the right hand empty (checked
    # below), so 00583f20 plays the row's start animation (PQ-423).
    animation, cast = cast_animation(row, {BOW_KIND}), int(row[SKILL_CAST])
    bows = [i for i, p in enumerate(config['profiles']) if p.get('name') == 'bow']
    if len(bows) != 1:
        raise ValueError("combat-animation.json needs one profile named 'bow'")
    profile = config['profiles'][bows[0]]
    expected = dict(ready=BOW_READY, attacks=[animation], moving=animation, interval_ms=cast * 100 + 150)
    if {k: profile.get(k) for k in expected} != expected:
        raise ValueError('the bow profile %r is not 1298\'s %r (archery row %d)' % (profile, expected, skill))
    try:
        right, left = equipment_slots.index('Right hand'), equipment_slots.index('Left hand')
        config['slots'].index(right)
        at_left = config['slots'].index(left)
    except ValueError:
        raise ValueError('the bow rule needs both hands as combat selectors') from None
    out, report = [], []
    for item, (_, about) in sorted(items.items()):
        if about['kind'] != BOW_KIND:
            raise ValueError('%s is 2145 kind %r: only a kind %d bow has its 1298 combat profile here'
                             % (item, about['kind'], BOW_KIND))
        if slot_of[item] != left:
            raise ValueError('%s is worn in slot %r, not the left hand' % (item, slot_of[item]))
        # The right hand stays empty: with a right-hand weapon 0045bfe0 gives
        # that weapon's clip, a row this package does not add.
        key = [None] * len(config['slots'])
        key[at_left] = item
        out.append(dict(items=key, profile=bows[0] + 1))
        report.append(dict(item=item, kind=about['kind'], right=None, profile=bows[0] + 1))
    return out, dict(rows=report, skill=skill, animation=animation, cast_tenths=cast, profile=dict(profile),
                     rule='1298 client 0045bfe0 ready 92; 004659b0 archery class x 1000 + 3, interval +0x78 x 0.1 + '
                          '0.15 s; 00583f20 plays +0x34 and stops the walk')


# PQ-423 (D-220): the cast start 00583f20 plays, for a type-2 row (+0x8c or
# +0x90 == 2), clip 0x1c instead of the row's start animation (+0x34) when
# either hand item's kind byte (+0x40 of +0x2c8 or +0x2cc) is 0x47, a
# crossbow (005844c7-0058451f; an observed caster's own hands in 00585a90,
# 00585e7d-00585ea9). The package's bows are kind 70, so its profile keeps
# the row's animation; the rule is checked here so a crossbow row cannot
# take the bow's.
CROSSBOW_KIND, CROSSBOW_CAST = 71, 0x1c


def cast_animation(row, kinds):
    """The clip 1298's cast start plays for the skill `row` (a
    Skill_Magic_Main_us.tbl CSV row) with hand items of `kinds`."""
    if '2' in (str(row[SKILL_TYPES[0]]), str(row[SKILL_TYPES[1]])) and CROSSBOW_KIND in kinds:
        return CROSSBOW_CAST
    return int(row[SKILL_ANIMATION])


# PQ-423 (D-220): the cast start 00583f20 triggers the row's self FX (+0x40,
# column 8) on the caster at part +0x44 % 1000 (column 9), and at
# |+0x44 / 1000| as well when that is not 0 (00479de0 at 0058447f, 0058449a;
# observers 00585a90 at 00585e30, 00585e4b), as a self FX (move type -1);
# the flying phase 00584b00 stops it (0047a710 at 00584f6f, 00584f84) when the
# row has a flying FX (+0x50, column 12). The bundle lives at most 10 s
# (00478bc0), the clip's length here.
SKILL_SELF_FX, SKILL_SELF_PART, SKILL_FLYING_FX = 7, 8, 11
FX_TABLE_1298 = 'Data/fx.tbl.csv'


def cast_effect(skill, skill_csv, fx_csv, joints):
    """The bow profile's `cast_effect` from the class archery row `skill`:
    its self FX as a self clip of the effects definition and its parts as
    joints (each below `joints`, the player skeleton's joint count). The row
    must name a self FX that fx.tbl holds and a flying FX (so 1298 ends the
    self FX at the shot's release). Returns (key, clip spec, cast_effect,
    report)."""
    import csv
    import io
    row = {r[0]: r for r in csv.reader(io.StringIO(skill_csv)) if r and r[0].isdigit()}.get(str(skill))
    if row is None or len(row) <= SKILL_FLYING_FX:
        raise ValueError('1298 %s has no archery row %d' % (SKILL_TABLE, skill))
    fx, part, flying = int(row[SKILL_SELF_FX]), int(row[SKILL_SELF_PART]), int(row[SKILL_FLYING_FX])
    if fx <= 0 or flying == 0:
        raise ValueError('1298 archery row %d has self FX %d and flying FX %d: 00584b00 ends the self FX only '
                         'with a flying FX' % (skill, fx, flying))
    if fx not in {int(r[0]) for r in csv.reader(io.StringIO(fx_csv)) if r and r[0].isdigit()}:
        raise ValueError('1298 %s has no FX %d (archery row %d)' % (FX_TABLE_1298, fx, skill))
    # C's int division and remainder truncate toward zero.
    first, second = abs(part) % 1000 * (1 if part >= 0 else -1), abs(int(part / 1000))
    parts = [first] + ([second] if second else [])
    if any(not 0 <= j < joints for j in parts) or len(set(parts)) != len(parts):
        raise ValueError('1298 archery row %d parts %r do not fit the %d-joint player skeleton' % (skill, parts, joints))
    key = 'ranged-cast-%d' % fx
    return key, dict(fx=fx, duration=10, self=True), dict(clip=key, joints=parts), dict(
        skill=skill, self_fx=fx, part=part, joints=parts, flying_fx=flying, clip=key,
        rule='1298 client 00583f20 -> 00479de0(caster, +0x44 % 1000, +0x40, caster, part, -1, -1), second part '
             '|+0x44 / 1000| when not 0; 00584b00 -> 0047a710(..., 1) at the release when +0x50 != 0; 00477590 '
             'move type -1: at the joint, facing the caster\'s +Z')


# PQ-417 (D-222): the release (00584b00, at 005855bc) and an observer's
# flying receive (00585f20, at 00586677) call 00587ac0 for a type-2 row. For
# MAGIC_TYPE2 HitType (record +4, Skill_Magic_2 column 2) 0 it flies the
# row's flying FX (+0x50, column 12) from the shooter's part +0x44 % 1000
# (column 9) toward the target's box centre with move type 0 (0047a2d0 ->
# 004770c0; the tick 00477590 moves it at the bundle's velocity +0x44, read
# by 00478bc0), plus (NumArrow (record +0x14, column 6) - 1) >> 1 pairs of
# arrows spread about y; it plays sound 0x157c at the shooter when its +0x2cc
# (left hand, PQ-011) item's kind / 10 is 7. Where the arrow meets the
# target's box (0047a8d0), the -101 fail receive (00586fa0) triggers the
# row's target FX (+0x54, column 13) at the target's part (+0x58, column 14)
# through 00479de0 (move type -1).
SKILL_TARGET_FX, SKILL_TARGET_PART = 12, 13
RELEASE_SOUND = 0x157c


def flight(skill, skill_csv, type2_csv, fx_csv, bundle_of, joints, left_kind):
    """The bow profile's `flight` from the class archery row `skill`: its
    flying FX as a flight clip at the bundle's velocity, from the row's
    first part (each below `joints`), its target FX as the hit clip at the
    row's target part, and the release sound for a kind 70-79 left-hand item
    (`left_kind`). `bundle_of(path)` returns an FX bundle read by
    ko_fx.bundle. Refuses a
    row whose MAGIC_TYPE2 HitType is not 0 (a homing flight, 00479de0 with
    move type HitType) or whose NumArrow is not 1 (a spread), a missing FX,
    a bundle without a velocity or with no parts, and a part past the
    skeleton. Returns (clips {key: spec}, flight, release sound or None,
    report)."""
    import csv
    import io
    row = {r[0]: r for r in csv.reader(io.StringIO(skill_csv)) if r and r[0].isdigit()}.get(str(skill))
    if row is None or len(row) <= SKILL_TARGET_PART:
        raise ValueError('1298 %s has no archery row %d' % (SKILL_TABLE, skill))
    type2 = {r[0]: r for r in csv.reader(io.StringIO(type2_csv)) if r and r[0].isdigit()}.get(str(skill))
    if type2 is None or len(type2) <= TYPE2_ARROWS:
        raise ValueError('1298 %s has no row %d' % (TYPE2_TABLE, skill))
    hit_type, arrows = int(type2[TYPE2_HIT_TYPE]), int(type2[TYPE2_ARROWS])
    if hit_type != 0:
        raise ValueError('1298 %s %d has HitType %d: 00587ac0 flies it homing (move type %d), not supported'
                         % (TYPE2_TABLE, skill, hit_type, hit_type))
    if arrows != 1:
        raise ValueError('1298 %s %d has NumArrow %d: 00587ac0 adds %d spread pairs, not supported'
                         % (TYPE2_TABLE, skill, arrows, (arrows - 1) >> 1))
    fx_rows = {int(r[0]): r for r in csv.reader(io.StringIO(fx_csv)) if r and r[0].isdigit()}
    flying, target_fx, part, target_part = (int(row[k]) for k in (SKILL_FLYING_FX, SKILL_TARGET_FX, SKILL_SELF_PART,
                                                                  SKILL_TARGET_PART))
    for fx in (flying, target_fx):
        if fx not in fx_rows:
            raise ValueError('1298 %s has no FX %d (archery row %d)' % (FX_TABLE_1298, fx, skill))
    source = abs(part) % 1000 * (1 if part >= 0 else -1)
    for j in (source, target_part):
        if not 0 <= j < joints:
            raise ValueError('1298 archery row %d part %d does not fit the %d-joint player skeleton' % (skill, j, joints))
    bundle = bundle_of(fx_rows[flying][2])
    if not 1 <= bundle['velocity'] <= 1000:
        raise ValueError('1298 FX %d (%s) has velocity %r: not a flight' % (flying, fx_rows[flying][2], bundle['velocity']))
    hit = bundle_of(fx_rows[target_fx][2])
    if not hit['parts']:
        raise ValueError('1298 FX %d has no parts' % target_fx)
    # The hit clip lasts as long as its parts draw (the bundle ends then).
    hit_life = min(10, max(p['start'] + p['life'] + p.get('fadeout', 0) for p in hit['parts']))
    key, hit_key = 'ranged-flight-%d' % flying, 'ranged-hit-%d' % target_fx
    clips = {key: dict(fx=flying, duration=10, flying=True), hit_key: dict(fx=target_fx, duration=round(hit_life, 3))}
    release = RELEASE_SOUND if left_kind // 10 == 7 else None
    spec = dict(clip=key, joint=source, speed=bundle['velocity'], hit_clip=hit_key, hit_joint=target_part,
                **({'release': 'ranged-release'} if release else {}))
    return clips, spec, release, dict(
        skill=skill, flying_fx=flying, target_fx=target_fx, part=part, target_part=target_part, hit_type=hit_type,
        arrows=arrows, velocity=bundle['velocity'], hit_life=hit_life, release_sound=release, flight=spec,
        rule='1298 client 00587ac0 (HitType 0): 0047a2d0(shooter, +0x44 % 1000, +0x50, target box centre 00460bd0, '
             'index, 0) at the bundle velocity (00477590 case 0); 0x157c at the shooter for a left kind / 10 == 7; '
             '0047a8d0 stops it at the target box; 00586fa0 (-101) -> 00479de0(+0x54 at +0x58, move type -1)')


# PQ-416 (D-216): the bow profile is 1298's archery as a ranged basic attack
# (KnightOnLine.exe, SHA-256 828ab0db...). The range check 00583780 limits a
# type-2 skill (row +0x8c or +0x90 == 2) to (the hand item's +0x4a x 0.1 + the
# radii 005819e0 passes, both actors' plus 1.0, + 1.0) x the type-2 add range
# (+0x10) x 0.01, in 3-D, and posts text 0xfa9 (4009) when it fails; a Ctrl or
# double click walks to 00468620, half the radii plus the bow's +0x4a x 0.1.
# n3e's N3RB adds `range` to the radii summed and `reach` to half of them, so
# with an add range of 100 the bow's range is +0x4a x 0.1 + 2.0 and its reach
# +0x4a x 0.1. Skill_Magic_Main_us.tbl columns 27-28 (0-based 26-27) are the
# types (+0x8c, +0x90) and column 29 (0-based 28) the row's own range (+0x94),
# which 00583780 tries first when above 0; Skill_Magic_2.tbl column 5 (0-based
# 4) is the add range.
SKILL_TYPES, SKILL_RANGE = (26, 27), 28
TYPE2_TABLE = 'Data/Skill_Magic_2.tbl.csv'
TYPE2_ADD_RANGE = 4
TEXTS_TABLE = 'Data/Texts_us.tbl.csv'
TOO_FAR = 0xfa9
# PQ-467 (D-233): Ebenezer-official.exe (SHA-256 7d83cc28...) checks the
# range on each phase of a user's archery row, the flying and effecting
# phases included: the magic packet 004630a6 calls 004c1dbe at 004635c8, and
# for a Type1 2 row (Moral 7 reaches it) that passes while dx^2 + dz^2 is at
# most (the ITEM record's Range +0x3e / 10, integer division)^2 + 1000.0
# (float 00634b84; 004c1fcd-004c203d, JA) for the item number in equipment
# slot 8, else slot 6 (+0x150, +0x120; 004a1aa4 indexes the item array at
# slot x 0x18 + 0x90). The two coordinates are x and z (source-aided). The
# bow's hold is that bound as a distance on the ground plane, from the same
# range column the client limit uses (an inference: the server ITEM Range of
# a 2145-only bow is not in the local export; for the 15 kind 70/71/80 rows
# of the 1298 Item_Org whose number is an OpenKO ITEM row, column 17 equals
# its Range).
HOLD_SQUARED = 1000.0


def archery_hold(item_range):
    """D-233: the archery row's hold on the ground plane for a bow of range
    column `item_range` (Ebenezer's +0x3e): sqrt((range // 10)^2 + 1000)."""
    return dict(distance=math.sqrt((item_range // 10) ** 2 + HOLD_SQUARED), plane='xz')


def ranged_attack(items, profile, skill, skill_csv, type2_csv, texts_csv):
    """The package's `ranged_attack` for the bow profile (1-based `profile`):
    one range for every bow item (`items`, as rows() returns them; refused
    when the grades differ), the class's archery row (`skill`) a type-2 row
    whose add range is 100, its cast time (+0x78, tenths of a second) x 100
    as the profile's `cast_ms` (PQ-420, D-217: 00461ab0 stretches the start
    clip over it only above 0.1 s, so a row with 1 or less is refused), and
    the 1298 client's text 4009 as the notice. Returns (ranged_attack,
    report)."""
    import csv
    import io
    ranges = {about['range'] for _, about in items.values()}
    if len(ranges) != 1 or not 1 <= next(iter(ranges)) <= 980:
        raise ValueError('the bow items do not share one range in 1..980: %r' % sorted(ranges))
    item_range = next(iter(ranges))
    rows = {r[0]: r for r in csv.reader(io.StringIO(skill_csv)) if r and r[0].isdigit()}
    row = rows.get(str(skill))
    if row is None or len(row) <= SKILL_RANGE or '2' not in (row[SKILL_TYPES[0]], row[SKILL_TYPES[1]]):
        raise ValueError('1298 archery row %d is not a type-2 skill' % skill)
    if row[SKILL_RANGE] != '0':
        raise ValueError('1298 archery row %d has its own range %r, which 00583780 tries first' % (skill, row[SKILL_RANGE]))
    cast = int(row[SKILL_CAST])
    if not 1 < cast <= 100:
        raise ValueError('1298 archery row %d has cast time %d tenths: 00461ab0 stretches only above 1, '
                         'and N3RC holds at most 10 s' % (skill, cast))
    type2 = {r[0]: r for r in csv.reader(io.StringIO(type2_csv)) if r and r[0].isdigit()}.get(str(skill))
    if type2 is None or len(type2) <= TYPE2_ADD_RANGE or type2[TYPE2_ADD_RANGE] != '100':
        raise ValueError('1298 %s row %d has no add range of 100 (%r)' % (TYPE2_TABLE, skill, type2))
    texts = {r[0]: r for r in csv.reader(io.StringIO(texts_csv)) if r and r[0].isdigit()}
    notice = texts.get(str(TOO_FAR))
    if notice is None or len(notice) < 2 or '%' in notice[1]:
        raise ValueError('1298 %s has no plain text %d' % (TEXTS_TABLE, TOO_FAR))
    reach = item_range / 10
    value = dict(profiles=[dict(profile=profile, reach=reach, range=reach + 2.0, cast_ms=cast * 100,
                                hold=archery_hold(item_range))], notice=notice[1])
    return value, dict(skill=skill, item_range=item_range, add_range=100, text=TOO_FAR, cast_tenths=cast,
                       ranged_attack=value,
                       rule='1298 client 00583780: (item +0x4a x 0.1 + both radii + 1.0 + 1.0) x add range / 100, '
                            '3-D, text 0xfa9; 00468620: half the radii + item +0x4a x 0.1; 00461ab0: the start clip '
                            'over +0x78 x 0.1 s, landing at its first marker (004689f0); Ebenezer 004c1dbe (Type1 2, '
                            'every phase from 004635c8): dx^2 + dz^2 <= (item +0x3e / 10)^2 + 1000.0')


# PQ-422 (D-219): the bow's own attack (Ebenezer-official.exe, SHA-256
# 7d83cc28...): the weapon attack 004a0d2a takes a left-hand item whose kind /
# 10 is 7, 8 or 10 in full, on the dexterity path, with the class's bow
# coefficient (+0x3c); the item sum 0049e11c divides a zero-durability item's
# damage by 10. n3e's stats category with dexterity 1 and offhand mode 2 (in
# full) is that rule; an item with durability 0 counts as broken there too.
# PQ-434 (D-221, amending D-219): an upgraded grade's attack and durability
# are its Item_Org value plus its Item_Ext bonus (EXT_DAMAGE, EXT_DURABILITY).
def bow_stats(manifest, items, category):
    """Gives each bow item (`items`, as rows() returns them; kind 70) the
    package's stats `category` (which must be a dexterity, full off-hand
    category), its 2145 Item_Org damage (column 16) plus its Item_Ext attack
    bonus (column 9) as its attack, and that Item_Org row's durability
    (column 20) plus its Item_Ext durability bonus (column 13) as its initial
    durability, so it is not counted as broken. A negative bonus or a sum
    outside the bounds is refused. Their shots wear nothing only because the
    package's wear policy gives them no attack slots (add_items); a ranged
    basic attack wears attack-slot items as a melee one does. Returns the
    report."""
    found = [c for c in manifest['stats']['categories'] if c['id'] == category]
    if len(found) != 1 or found[0]['dexterity'] != 1 or found[0]['offhand'] != 2:
        raise ValueError('stats category %r is not a dexterity, full off-hand category (004a0d2a\'s bow rule)'
                         % category)
    report = []
    for item, (_, about) in sorted(items.items()):
        if about['kind'] != BOW_KIND:
            raise ValueError('%s is 2145 kind %r, not a kind %d bow' % (item, about['kind'], BOW_KIND))
        base, base_durability = about['damage'], about['durability']
        bonus, durability_bonus = about['damage_bonus'], about['durability_bonus']
        for name, value in (('Item_Org damage', base), ('Item_Org durability', base_durability),
                            ('Item_Ext attack bonus', bonus), ('Item_Ext durability bonus', durability_bonus)):
            if type(value) is not int or value < 0:
                raise ValueError('%s: 2145 %s %r is not a non-negative integer' % (item, name, value))
        damage, durability = base + bonus, base_durability + durability_bonus
        if not damage <= 10000:
            raise ValueError('%s: 2145 attack %d + %d is outside 0..10000' % (item, base, bonus))
        if not 1 <= durability <= 65535:
            raise ValueError('%s: 2145 durability %d + %d is outside 1..65535' % (item, base_durability,
                                                                                 durability_bonus))
        stats = [s for s in manifest['stats']['items'] if s['id'] == item]
        inventory = [i for i in manifest['inventory']['items'] if i['id'] == item]
        if len(stats) != 1 or len(inventory) != 1:
            raise ValueError('%s is not one package item' % item)
        stats[0].update(category=category, attack=damage)
        inventory[0]['durability'] = durability
        report.append(dict(item=item, ko_2145_item=about['item_2145'], attack=damage, durability=durability,
                           item_org_damage=base, item_ext_damage=bonus, item_org_durability=base_durability,
                           item_ext_durability=durability_bonus))
    return dict(items=report, category=category,
                rule='Ebenezer 004a0d2a: a left-hand kind / 10 of 7, 8 or 10 in full on the dexterity path; '
                     '0049e11c: damage / 10 at durability 0; 0041f077: one ITEM row per number; 2145 Item_Org '
                     'columns 16 and 20 + Item_Ext columns 9 and 13 (1298 004d6320, 2233 005aa8e0)')


# PQ-422 (D-219): the archery shot's damage on an NPC (AI Server-official.exe,
# SHA-256 8715084f...): the type-2 leaf 0040d471 deals 00443a34's skill
# branch, for HitType 0 with HitRate scaling the grade ratio and AddDamage the
# base, plus AddDamagePlus. The terms are the server's MAGIC_TYPE2 row (the
# operator's own export, ko_tables), which the 1298 client's Skill_Magic_2
# mirrors in column order apart from AddDamage (0 there for every archery
# row, a column the client does not use for damage) and AddDamagePlus (not in
# the client's table): columns 2, 3, 5 and 6 (0-based 1, 2, 4, 5) are HitType,
# HitRate, AddRange and NeedArrow (the last two the +0x10 and +0x14 PQ-416 and
# PQ-421 read).
TYPE2_HIT_TYPE, TYPE2_HIT_RATE = 1, 2


def ko_tables_export():
    """Where the operator's reference-table exports are (ko_tables.EXPORT)."""
    import ko_tables
    return ko_tables.EXPORT


def archery_hit(skill, type2_csv, export=None):
    """The ranged entry's `skill_hit` for the class archery row `skill`, from
    the operator's MAGIC_TYPE2 export (ko_tables; `export` its folder,
    default ko_tables.EXPORT), refused when the export or the row is missing,
    the row's HitType is not 0, its HitType, HitRate, AddRange or NeedArrow
    disagree with the 1298 client's Skill_Magic_2 row, or a value is outside
    N3RE's bounds. Returns (skill_hit, report)."""
    import csv
    import io
    import ko_tables
    table = ko_tables.load('MAGIC_TYPE2', *(() if export is None else (export,)))
    if table is None:
        raise ValueError('the archery damage needs the operator\'s MAGIC_TYPE2 export (%s/MAGIC_TYPE2.json): run '
                         'python3 -I tools/ko-reference/inspect_db.py <backup> --output %s --table MAGIC_TYPE2'
                         % (export or ko_tables.EXPORT, export or ko_tables.EXPORT))
    row = next((r for r in ko_tables.rows_as_dicts(table) if r['iNum'] == skill), None)
    if row is None:
        raise ValueError('MAGIC_TYPE2 has no row %d' % skill)
    if row['HitType'] != 0:
        raise ValueError('MAGIC_TYPE2 %d has HitType %d: only HitType 0 (00443a34\'s grade ratio) is supported'
                         % (skill, row['HitType']))
    client = {r[0]: r for r in csv.reader(io.StringIO(type2_csv)) if r and r[0].isdigit()}.get(str(skill))
    mirrored = (row['HitType'], row['HitRate'], row['AddRange'], row['NeedArrow'])
    if client is None or len(client) <= TYPE2_ARROWS or tuple(
            int(client[i]) for i in (TYPE2_HIT_TYPE, TYPE2_HIT_RATE, TYPE2_ADD_RANGE, TYPE2_ARROWS)) != mirrored:
        raise ValueError('MAGIC_TYPE2 %d %r disagrees with the 1298 %s row %r' % (skill, mirrored, TYPE2_TABLE, client))
    import ranged_attack
    hit = dict(hit_rate=row['HitRate'], add_damage=row['AddDamage'], add_damage_plus=row['AddDamagePlus'])
    for key, (low, high) in ranged_attack.SKILL_HIT.items():
        if not low <= hit[key] <= high:
            raise ValueError('MAGIC_TYPE2 %d: %s %d is outside %d..%d' % (skill, key, hit[key], low, high))
    return hit, dict(skill=skill, magic_type2=row, table_digest=table['digest'], source=table['source'],
                     sha256=table['sha256'], client_add_damage=int(client[3]), skill_hit=hit,
                     rule='AI 0040d471: 00443a34(skill) + type-2 +0xe; 00443a34 HitType 0: grade 00444164((hit / '
                          'evasion) x +6 x 0.01f), base ftol(+8 x 0.01f x attack x 200 / (defence + 240)), damage '
                          'ftol(base x 0.6f + rand(0..base) x 0.89f + 0.99)')


# PQ-421 (D-218): the archery shot needs and uses arrows (KnightOnLine.exe,
# SHA-256 828ab0db...; Ebenezer-official.exe, SHA-256 7d83cc28...). The skill
# start 005819e0 runs the usable check 0057f7f0 before the range check: the
# row's need item (+0x70) must be 0, 9 or a hand item's kind / 10 (text 0xfa5),
# and with an exhaust item (+0x74) on a type-2 row the first inventory slot
# holding it (004a29e0) must hold the type-2 row's arrow count (+0x14), or
# text 0xfa7 (4007) and no cast. Ebenezer's flying phase 0046f3f1 removes that
# count from the first inventory slot holding the item (004b0792) or fails the
# cast. On the 1298 tables (0-based): Skill_Magic_Main columns 19 and 20 are
# +0x70 and +0x74 (column 21 is +0x78, the cast time); Skill_Magic_2 column 5
# is +0x14; Item_Org columns 2 (name), 7 (icon), 10 (kind), 18 (weight), 20
# (price) and 23 (countable).
SKILL_NEED_ITEM, SKILL_EXHAUST_ITEM = 19, 20
TYPE2_ARROWS = 5
ARROW_ITEM, ARROW_KIND = 391010000, 120
ORG_ICON_1298, ORG_KIND_1298, ORG_WEIGHT, ORG_PRICE, ORG_COUNTABLE = 7, 10, 18, 20, 23
NOT_ENOUGH = 0xfa7
# KO's pickup clamps a stack at 9999 (Ebenezer 004a7f1b, BINARY-POLICY).
ARROW_STACK = 9999


def arrows(item_id, skill, skill_csv, type2_csv, org_rows, texts_csv, starting):
    """The arrow the bow profile's shot needs, from the player's 1298 tables:
    the archery row (`skill`) must need a bow (need item 7 = kind 70 / 10)
    and exhaust Item_Org 391010000, a countable kind 120 item; its type-2
    row's arrow count is the count per shot. Returns (the inventory item
    definition named `item_id`, granted `starting` at start, the commerce
    item, the icon, the ranged entry's `ammo`, the ammo notice (text 4007),
    report)."""
    import csv
    import io
    rows = {r[0]: r for r in csv.reader(io.StringIO(skill_csv)) if r and r[0].isdigit()}
    row = rows.get(str(skill))
    if row is None or len(row) <= SKILL_EXHAUST_ITEM:
        raise ValueError('1298 %s has no archery row %d' % (SKILL_TABLE, skill))
    if int(row[SKILL_NEED_ITEM]) != BOW_KIND // 10:
        raise ValueError('1298 archery row %d needs item kind %r / 10, not a bow (%d)' % (skill, row[SKILL_NEED_ITEM], BOW_KIND))
    if int(row[SKILL_EXHAUST_ITEM]) != ARROW_ITEM:
        raise ValueError('1298 archery row %d exhausts item %r, not the arrow %d' % (skill, row[SKILL_EXHAUST_ITEM], ARROW_ITEM))
    type2 = {r[0]: r for r in csv.reader(io.StringIO(type2_csv)) if r and r[0].isdigit()}.get(str(skill))
    if type2 is None or len(type2) <= TYPE2_ARROWS or not type2[TYPE2_ARROWS].isdigit() or not 1 <= int(type2[TYPE2_ARROWS]) <= 99:
        raise ValueError('1298 %s row %d has no arrow count in 1..99 (%r)' % (TYPE2_TABLE, skill, type2))
    count = int(type2[TYPE2_ARROWS])
    org = next((r for r in org_rows if r and r[0] == str(ARROW_ITEM)), None)
    if org is None or len(org) <= ORG_COUNTABLE:
        raise ValueError('1298 Item_Org has no row %d' % ARROW_ITEM)
    if int(org[ORG_KIND_1298]) != ARROW_KIND or org[ORG_COUNTABLE] != '1':
        raise ValueError('1298 Item_Org %d is kind %r, countable %r: not a countable kind %d arrow'
                         % (ARROW_ITEM, org[ORG_KIND_1298], org[ORG_COUNTABLE], ARROW_KIND))
    label, price, weight = org[2], int(org[ORG_PRICE]), int(org[ORG_WEIGHT])
    # n3e's commerce weight is not KO's tenths (siWeight); the arrow weighs 0
    # in both, and another weight is refused rather than converted.
    if not 1 <= len(label) <= 64 or not all(' ' <= c <= '~' for c in label) or price < 1 or weight != 0:
        raise ValueError('1298 Item_Org %d: label %r, price %r, weight %r' % (ARROW_ITEM, label, price, weight))
    if not 0 <= starting <= ARROW_STACK:
        raise ValueError('starting arrows %r' % starting)
    texts = {r[0]: r for r in csv.reader(io.StringIO(texts_csv)) if r and r[0].isdigit()}
    notice = texts.get(str(NOT_ENOUGH))
    if notice is None or len(notice) < 2 or '%' in notice[1]:
        raise ValueError('1298 %s has no plain text %d' % (TEXTS_TABLE, NOT_ENOUGH))
    item = dict(id=item_id, label=label, stack_limit=ARROW_STACK, durability=0, starting=starting)
    # The sell divisor is the package's (features.json's 6 for every item).
    commerce = dict(id=item_id, weight=0, price=price, sell_divisor=6)
    icon = dict(base=int(org[ORG_ICON_1298]), extension=0)
    ammo = dict(item=item_id, count=count)
    return item, commerce, icon, ammo, notice[1], dict(
        skill=skill, need_item=int(row[SKILL_NEED_ITEM]), exhaust_item=ARROW_ITEM, arrows_per_shot=count,
        item_org=dict(label=label, kind=ARROW_KIND, countable=1, price=price, weight=weight, icon=icon['base']),
        stack=ARROW_STACK, starting=starting, text=NOT_ENOUGH, notice=notice[1],
        rule='1298 client 0057f7f0: need item +0x70 vs hand kind / 10 (0xfa5), the first inventory slot holding '
             '+0x74 (004a29e0) below type-2 +0x14 (0xfa7); Ebenezer 0046f3f1 -> 004b0792(+0x14 item, bag 1, '
             'type-2 +0xc) or the cast fails')

# 2233 009b3fc0 takes the icon from the Item_Ext row's +0x48 when non-zero,
# else the Item_Org row's +0x4c (PQ-338). On 2145's columns (0-based) these are
# Item_Ext column 6 and Item_Org column 7, the u32 after each model column (5
# and 6; the org model column is PQ-302's), by the rows' field sizes with
# 28-byte strings (an inference, as ORG_* above).
ORG_ICON, EXT_MODEL, EXT_ICON = 7, 5, 6


def icons(icons, items, install):
    """The package's item icon map (`icons`, the glow package's own, PQ-321)
    with an icon for each skeletal plug item (`items`, as rows() returns them)
    by the 2233 rule (009b3fc0; ko_item_icons.path_2233) from its 2145 rows,
    read from the player's 2145 UI pack. An item already in the map, an item
    with no Item_Ext row (009b3fc0 then makes no icon) or no icon file is
    refused. Returns (the new map, report)."""
    out = {k: dict(v) for k, v in icons.items()}
    source, report = None, []
    for item, (label, row) in sorted(items.items()):
        if item in out:
            raise ValueError('%s already has an item icon' % item)
        number = row['item_2145']
        org, ext = ko_glow_2233.item(install, number)
        types, _ = install.table(ko_glow_2233.ORG)
        ext_types, _ = install.table(ko_glow_2233.EXT.format(org[1]))
        if len(org) <= ORG_ICON or types[ORG_ICON] != 6 or len(ext) <= EXT_ICON or ext_types[EXT_ICON] != 6:
            raise ValueError('2145 item %d: Item_Org column 8 or Item_Ext column 7 is not a u32' % number)
        source = source or Source(install, pack='UI')
        out[item] = dict(base=org[ORG_ICON], extension=ext[EXT_ICON], item_2233=number, assets=source)
        import ko_item_icons
        report.append(dict(item=item, ko_2145_item=number, item_org_icon=org[ORG_ICON], item_ext=ext[0],
                           item_ext_icon=ext[EXT_ICON],
                           path=ko_item_icons.path_2233(number, org[ORG_ICON], ext[EXT_ICON])))
    return out, dict(items=report, sources=source.sources if source else {},
                     rule='009b3fc0 (2233): the Item_Ext icon, else the Item_Org icon; "%.2d" for item / 10^9 of 1-3')


def package(manifest, mappings, height, root, work, install=None):
    """The N3AT table of the package's skeletal plug rows (those naming
    `chrplug_2145`) into `manifest['attachments']`, after the player and skill
    clips are cooked (their KO clip indices give the clip map). Returns the
    report."""
    import ko_player
    import json
    install = install or ko_glow_2233.Install()
    clips = ko_player.clip_indices(True, True, True, True)
    player = dict(states={n: i for n, i in clips if not n.startswith('combat-')},
                  combat=[i for n, i in clips if n.startswith('combat-')])
    cooked = [c['source'] for c in manifest['combat_animation']['clips']]
    if cooked != ['player-combat-%d.bin' % i for i in player['combat']]:
        raise ValueError('the package\'s combat clips are not ko_player\'s')
    # ko_skills renumbers games/moradon/skills.json's animations 0, 1, ...;
    # the file keeps each one's KO clip index.
    spec = json.loads(pathlib.Path('games/moradon/skills.json').read_text())['skills']
    if [s['animation'] for s in manifest['skills']['skills']] != list(range(len(spec))):
        raise ValueError('the package\'s skill animations are not ko_skills\'s')
    skills = {i: s['animation'] for i, s in enumerate(spec)}
    entries, reports, cooked = [], [], {}
    for row in (r for r in mappings if 'chrplug_2145' in r):
        # Rows of one plug file (the Azagai's grades, PQ-337) share its model:
        # the plug, its character and clips depend on the file alone.
        if row['chrplug_2145'] not in cooked:
            cooked[row['chrplug_2145']] = cook(row, player, skills, height, root, work / str(len(cooked)), install)
        entry, report = cooked[row['chrplug_2145']]
        entries.append(dict(entry, item=row['item'], slot=row['slot'], joint=row['joint'], group=row['group']))
        reports.append(dict(report, joint=row['joint'], ko_2145_item=row['ko_2145_item']))
    # The pulse is the CPlayerWing's (2233 00569590, PQ-328); a plug entry
    # neither takes nor advances it.
    manifest['attachments'] = dict(clock=dict(per_attachment=True, rise=1.0, hold=3.0, fall=5.0, period=5.5),
                                   color=[1.0, 1.0, 1.0], entries=entries)
    return dict(entries=reports, rule='0042df00 for every wearer (D-188)', player_clips=clips, skills=skills)
