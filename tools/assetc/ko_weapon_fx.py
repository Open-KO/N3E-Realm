"""KO's hand-plug weapon effect as N3E2 appearance effects (PQ-211).

Evidence: docs/implementation/evidence/pq-211-hand-item-effects.md. Client
KnightOnLine.exe (SHA-256 828ab0db...a5e5):

- 0045c6e0, the player plug setter for both hands (vtable slot +0x30), picks the
  effect id with 0045ccc0 (else Item_Ext column 5), looks up the main bundle at
  that id and its tail at id + 1 in fx.tbl ([008186e4]), picks a trace colour
  by element (0045cb5e) and calls 00415370 when either name is found.
- 00415370 loads the main bundle (+0x1a4) and gives its first part a start life
  of (rand % 1000) x 0.01 s; it loads the tail (+0x1a8) and two duplicates
  (+0x1ac, +0x1b0) whose target scale is (FX mesh y + z extent) x 0.7.
- 00415910 (drawn by 004158d0 only while Option.Ini WeaponEffect.EffectVisible,
  0064b9b0, default 1) draws only with both the main bundle and its first part;
  when that part alpha-blends (flag 1) it draws the plug's FX mesh three times
  with its texture frames i, i+1, i+2: as placed, then turned -pi/36 about the
  plug's y and moved +v, then +pi/36 and -v, with v the FX mesh's first vertex
  normal x (frac(life x 1.2) x 0.07 - 0.035); it moves each duplicate tail to
  min + interval x (0.25 + (rand % 50) x 0.01) of the FX mesh box every frame.
- 004840b0 queues each live spark of an alpha particle part (flags bit 0,
  0047def0) in the frame's alpha list (0043e690), keyed by the eye distance to
  its quad's first three corners; 00415910 keys each copy by the eye distance
  to its matrix's translation plus the FX mesh's y extent; 0043dd80 sorts the
  list far to near (PQ-373, PQ-376).

The item tables are read through the client's own record layout (loader
006113b0): Item_Org column 11 is the class (+0x40) and 26 the effect base
(+0x60); Item_Ext column 3 is the base-item restriction (+0x14), 5 the effect
id (+0x28), 8 the attribute (+0x34), 22-25 fire, ice, lightning and poison
(+0x50-+0x53).
"""
import csv
import io
import math
import ko
import ko_appearance

ORG = 'Data/Item_Org_us.tbl.csv'
EXT = 'Data/Item_Ext_{}_us.tbl.csv'
FX = 'Data/fx.tbl.csv'
STAFF = 110  # 0045ccc0: class 'n'
# 0045cb5e: fire, ice, lightning, poison; else white.
COLORS = (0xffffff00, 0xffb4c8ff, 0xff1e96f0, 0xffff00ff)
WHITE = 0xffffffff
# 00415910 constants (006a3a8c pi, 006a3b64/b68 +-1/36, 006a3b74 1.2, 006a3b70
# 0.07, 006a3b6c 0.035, 006a3b78 0.25, 006a3b60 0.01, rand % 0x32), 00415370
# (rand % 1000 x 0.01, 006a3b5c 0.7).
TURN = math.pi / 36
JITTER_RATE, JITTER_AMPLITUDE = 1.2, 0.035
TAIL_LOW, TAIL_STEPS, TAIL_STEP = 0.25, 50, 0.01
PHASE_STEPS, PHASE_STEP = 1000, 0.01
TAIL_SCALE = 0.7
TAILS = 2


def effect_id(org, ext):
    """0045ccc0, then the setter's fallback to Item_Ext column 5."""
    base = org['effect_base'] // 1000
    if base and ext['effect']:
        if org['class'] == STAFF:
            fire, ice, lightning = ext['fire'], ext['ice'], ext['lightning']
            if fire or ice or lightning:
                pick = 1 if fire < ice else 0
                if max(fire, ice) < lightning:
                    pick = 2
                return base + 10 * pick
        elif ext['restriction'] == 0:
            return base
    return ext['effect']


def trace_color(ext):
    """0045cb5e: the first element above 63, or any non-zero on an attribute 4
    or 6 item, in fire, ice, lightning, poison order."""
    for value, color in zip((ext['fire'], ext['ice'], ext['lightning'], ext['poison']), COLORS):
        if value > 63 or (ext['attribute'] in (4, 6) and value):
            return color
    return WHITE


def _table(assets, name, columns):
    rows = list(csv.reader(io.StringIO(assets.get(name).decode('utf-8-sig'))))
    header = rows[0]
    for column, kind in columns.items():
        if len(header) < column or header[column - 1] != f'{column} - {kind}':
            raise ValueError(f'{name} column {column} is not {kind}')
    return {int(r[0]): r for r in rows[1:] if r and r[0].isdigit()}


def item(assets, number):
    """The Item_Org and Item_Ext rows of a KO item number (005cfe60: base
    num / 1000 x 1000, extension num % 1000 in Item_Ext_<Item_Org column 2>)."""
    if type(number) is not int or not 0 < number <= 0xffffffff:
        raise ValueError('KO item number')
    orgs = _table(assets, ORG, {1: 'UInt32', 2: 'Byte', 11: 'Byte', 26: 'UInt32'})
    org = orgs.get(number // 1000 * 1000)
    if org is None:
        raise ValueError(f'KO item {number}: no Item_Org row')
    exts = _table(assets, EXT.format(int(org[1])), {1: 'UInt32', 3: 'UInt32', 5: 'UInt32', 8: 'Byte',
                                                       22: 'Byte', 23: 'Byte', 24: 'Byte', 25: 'Byte'})
    ext = exts.get(number % 1000)
    if ext is None:
        raise ValueError(f'KO item {number}: no Item_Ext_{org[1]} row')
    return (dict(name=org[2], **{'class': int(org[10])}, effect_base=int(org[25]), extension=int(org[1])),
            dict(name=ext[1], restriction=int(ext[2]), effect=int(ext[4]), attribute=int(ext[7]),
                 fire=int(ext[21]), ice=int(ext[22]), lightning=int(ext[23]), poison=int(ext[24])))


def effect(assets, number):
    """The effect a KO item number attaches: fx.tbl main and tail files (None
    when the table has no row) and its trace colour."""
    org, ext = item(assets, number)
    main = effect_id(org, ext)
    rows = {int(r[0]): r for r in csv.reader(io.StringIO(assets.get(FX).decode('utf-8-sig'))) if r and r[0].isdigit()}
    found = lambda i: rows[i][2].replace('\\', '/') if i in rows else None
    return dict(item=number, org=org['name'], ext=ext['name'], main_id=main, main=found(main),
                tail_id=main + 1, tail=found(main + 1), trace_color=trace_color(ext))


def _ko(v):
    """Engine (Z-reflected) to KO space and back: the same reflection."""
    return [v[0], v[1], -v[2]]


def geometry(assets, plug_name, joint, bind, height, layout='1298'):
    """The plug's FX mesh as three copies and the reference points, in model
    space, or None when the plug has no FX mesh (00415910 then draws nothing).
    layout '2145' reads a 2145 plug as 2233's CN3CPlug does (PQ-334,
    ko_appearance.read_plug), refusing one that names a trace texture."""
    plug = ko_appearance.read_plug(assets, plug_name, layout)
    if layout != '1298':
        ko_appearance.default_traces(plug['textures'], plug_name)
    if plug['fx_data'] is None:
        return None
    return placed(plug, ko.import_mesh(None, 1.0, data=plug['fx_data']), bind, height)


def placed(plug, mesh, bind, height):
    """geometry() for a plug already read: its FX mesh (`mesh`, as
    ko.import_mesh reads it) at the plug's placement (position, rotation,
    scale) on the bind joint. 2233 draws a CN3ChrTypePlug's FX mesh by the same
    rule (00433af0 -> 004304c0, PQ-339), so ko_chrplug_2145 passes its
    .n3chrplug here."""
    transform, _ = ko_appearance.plug_transform(plug, bind, height)
    corners = [_ko(v[:3]) for v in mesh['vertices']]
    low = [min(c[k] for c in corners) for k in range(3)]
    high = [max(c[k] for c in corners) for k in range(3)]
    extent = [high[k] - low[k] for k in range(3)]

    def turned(p, angle):
        # __Matrix44::RotationY (0041d6f0): x' = x cos + z sin, z' = -x sin + z cos.
        c, s = math.cos(angle), math.sin(angle)
        return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c]
    copies = []
    for jitter, angle, offset in ((0, 0, 0), (1, -TURN, 1), (-1, TURN, 2)):
        vertices = []
        for i in mesh['indices']:
            v = mesh['vertices'][i]
            vertices.append(transform(_ko(turned(_ko(v[:3]), angle)), True) + list(v[6:8]))
        copies.append(dict(jitter=jitter, frame_offset=offset, vertices=vertices))
    normal = _ko(mesh['vertices'][0][3:6])
    point = lambda p: transform(_ko(p), True)
    box = [point(low)] + [point([low[k] + (extent[k] if k == axis else 0) for k in range(3)]) for axis in range(3)]
    # PQ-376 (D-200): 00415910 keys each copy by the eye distance to its
    # matrix's translation plus the FX mesh's y extent in mesh units
    # (004159e8-00415a23; added at 00416839, 00416a0d, 00416b72): the sort
    # origin is the plug origin, the jitter axis's origin, and the bias that
    # extent, scaled by neither the plug nor the character.
    return dict(copies=copies, jitter=[point([0, 0, 0]), point(normal)], tail_box=box, sort_bias=extent[1],
                tail_scale=(extent[1] + extent[2]) * TAIL_SCALE, fx_vertices=len(mesh['vertices']),
                fx_triangles=len(mesh['indices']) // 3, trace=plug['trace'])
