"""Explicit local artwork choices; binary-grounded part/plug composition.

00467b30/00467d50 select hand joints and replace/reset parts in world and preview.
00414570 reads plug transforms/material/dependencies; 004133c0 scales translation.
Raw assets, trace meshes and provenance remain local. No legacy IDs reach runtime.
"""
import math
import pathlib
import struct
import ko_character as character
import ko
import ko_tiles


def part_levels(assets, name, slot, rebuilt=None):
    """`rebuilt`, when a list, gets each level's count of drawn vertices whose
    normal was rebuilt (ko_character.corner_normals)."""
    part = character.part(assets.get(name))
    _, skins = character.skins(assets.get(part['skin']))
    levels = []
    for skin in skins:
        vertices, indices = [], []
        # A corner whose normal has no direction takes its triangle's (PQ-281,
        # D-177; the 2145 Krowaz parts have some, PQ-319); every other corner
        # keeps its normal as read, so parts without one cook as before.
        normals, fixed = character.corner_normals(skin)
        if rebuilt is not None:
            rebuilt.append(len(fixed))
        for corner, index in enumerate(skin['indices']):
            p, n = skin['origins'][index], normals[corner]
            vertices.append(([p[0], p[1], -p[2]], [n[0], n[1], -n[2]],
                             skin['uv'][skin['uv_indices'][corner]],
                             skin['joints'][index], skin['weights'][index], slot))
        for i in range(0, len(vertices), 3):
            indices.extend([i, i+2, i+1])
        levels.append((vertices, indices))
    return levels, ko_tiles.mip_chains(assets.get(part['texture']), skip=1)[0]


# PQ-348 (D-191): an equipped part draws with its own material's render state.
# 1298 0045cd90 sets the part through CN3Chr 0041b6d0 (slot vector +0x180),
# whose load (00438c40, vtable +0xc = 00412180) reads the material, and the
# character render 004196a0 draws each part of that vector with 00412570:
# blend with the material's factors (flag 1), culling off (4), lighting off
# (0x40); the device's alpha test is GREATER against reference 0 (0043ade0).
# A hand plug carries no part state here (plug_levels refuses its flags), so it
# keeps the detail draw's own cut-out at alpha 0.5, as N3D2 draws every key.
DETAIL_CUT = (0, 0.5, 0, 0)


def part_state(assets, name):
    """The N3D3 render state (render_detail.check_state) of a part's material:
    ko_character.render_state (PQ-265's rules, failing closed on a flag or
    factor n3e does not draw) in gltf.render_state's encoding. An unlit part
    (KO flag 0x40) is refused here: no check draws one on this path yet
    (PQ-280)."""
    import gltf
    state = character.part(assets.get(name))['render_state']
    if not state['lit']:
        raise ValueError('%s: an unlit part is not drawn on the appearance path yet (PQ-280)' % name)
    return gltf.render_state(state)


def needs_states(states):
    """N3D3 only when a part's state is not the opaque one, so every package
    whose parts are all opaque keeps its N3D2 bytes (and pins)."""
    return any(flags != 0 for flags, *_ in states)


LAYOUTS = ('1298', '2145')
TRACE_NAME = 259   # 2233 uses a trace texture name of 1-259 bytes (00448c27)
TRACE_SLOTS = 5    # 2233's loop count (00448bec, 00448fa6, 00449858, 00449e92)


def pmesh_length(data, at):
    """The byte length of a progressive mesh embedded at `at` (the 1298 layout
    ko.import_mesh reads): name, six counts, vertices, indices, collapses,
    index changes, LOD controls. ko.import_mesh then reads it strictly; this
    only finds where it ends, so the bytes after it can be read."""
    def word(offset):
        if at + offset + 4 > len(data):
            raise ValueError('2145 plug FX mesh truncated')
        return struct.unpack_from('<i', data, at + offset)[0]
    name = word(0)
    if not 0 <= name <= 255:
        raise ValueError('2145 plug FX mesh name')
    head = 4 + name
    collapses, changes, vertices, indices = (word(head + 4 * i) for i in range(4))
    if min(collapses, changes, vertices, indices) < 0 or vertices > 65536 or indices > 196608 \
            or collapses > 65536 or changes > 196608:
        raise ValueError('2145 plug FX mesh counts')
    body = head + 24 + vertices * 32 + indices * 2 + collapses * 24 + changes * 4
    lods = word(body)
    if not 0 <= lods <= 4096:
        raise ValueError('2145 plug FX mesh LOD count')
    if at + body + 4 + lods * 8 > len(data):
        raise ValueError('2145 plug FX mesh truncated')
    return body + 4 + lods * 8


def texture_block(data, at):
    """2233's plug texture block (CN3CPlug 004489c0 / 00448d80, CN3ChrTypePlug
    004493a0 / 004499e0), read only while bytes remain: a count (+0x2c4); when
    it is 1 or more, 4 bytes (+0x2cc) and five length-prefixed trace texture
    names (+0x2b0..+0x2c0). Returns (block or None at the end of the data, the
    offset after it). n3e's guards, not KO's: 1-3 bytes left, a name longer
    than 259 bytes (2233 then skips its bytes unread and reads the rest out of
    step) or a name that is not printable ASCII are refused."""
    if at == len(data):
        return None, at  # 0045b400 / ReadFile at the end: count 0, +0x2cc 0.0

    def take(n):
        nonlocal at
        if n < 0 or at + n > len(data):
            raise ValueError('2145 plug texture block truncated')
        at += n
        return data[at - n:at]
    count = struct.unpack('<i', take(4))[0]
    block = dict(count=count)
    if count >= 1:  # CMP [count],1 / JL (00448bc1)
        block['value'] = struct.unpack('<I', take(4))[0]
        names = []
        for _ in range(TRACE_SLOTS):
            n = struct.unpack('<i', take(4))[0]
            if not 0 <= n <= TRACE_NAME:
                raise ValueError('2145 plug trace texture name length %d' % n)
            raw = take(n)
            if any(b < 32 or b > 126 for b in raw):
                raise ValueError('2145 plug trace texture name is not printable ASCII')
            names.append(raw.decode('ascii'))
        block['names'] = names
    return block, at


def default_traces(textures, name):
    """n3e keeps a plug's trace textures out of packages until PQ-335 draws
    them: a block that names one, or whose +0x2cc is not 0 (what it holds is
    unread), is refused. Every 2145 plug leaves all five empty (PQ-302), so
    2233 would use its five defaults (00b76af0)."""
    if textures is None:
        return
    if any(textures.get('names', ())) or textures.get('value', 0) != 0:
        raise ValueError('%s: a trace texture or +0x2cc value n3e does not draw yet (PQ-335)' % name)


def read_plug(assets, name, layout='1298'):
    """An ordinary plug file: 00414570 (base) then 00415020 (trace and FX mesh).

    layout '2145' (PQ-334, a 2233/2145 addition) reads 2233's CN3CPlug
    (004489c0, loose 00448d80) instead: the same fields, the FX mesh measured
    to its end, then the texture block while bytes remain (texture_block), and
    nothing after it. The 1298 loader reads no block (00415020 ends with the
    FX mesh), so the '1298' layout is unchanged and stays the default. The
    2145 trace keeps the step count as read (`read_steps`); 2233 then uses 30
    (00448a86), which is PQ-335's."""
    if layout not in LAYOUTS:
        raise ValueError('plug layout %r' % (layout,))
    r = character.Reader(assets.get(name))
    r.string()
    if r.integer() != 0:
        raise ValueError('only ordinary plug artwork supported')
    plug = dict(stored_joint=r.integer())
    plug.update(position=r.floats(3), rotation=r.floats(16), scale=r.floats(3))
    plug['material'] = r.floats(17) + r.unpack('6I')
    plug['mesh'], plug['texture'] = r.string(), r.string()
    # 00415020: the trace step count (+0x168), then, when positive, its colour
    # (+0x16c) and two positions (+0x170, +0x174); then a flag and an embedded
    # FX mesh (+0x1a0) loaded with the mesh's own Load.
    # Older plug files end before either: ReadFile at the end of the file
    # leaves both at their initial 0 (00415020 sets the flag to 0 first).
    plug['fx_bytes'] = len(r.data) - r.at
    if layout == '2145':
        # 004489c0: the step count and, when above 0, three 4-byte values;
        # the mesh flag; the FX mesh; the texture block while bytes remain.
        # A file may end before the trace or the flag, as in 1298: the pack
        # read (0047c6f0) past the entry's end copies nothing, the flag stays
        # 0 and 0045b400 then finds no block.
        steps = r.integer() if r.at < len(r.data) else 0
        plug['trace'] = dict(read_steps=steps, color=r.unpack('I')[0], positions=r.floats(2)) if steps > 0 else None
        flag = r.integer() if r.at < len(r.data) else 0
        plug['fx_data'] = r.take(pmesh_length(r.data, r.at)) if flag else None
        plug['textures'], r.at = texture_block(r.data, r.at)
        if r.at != len(r.data):
            raise ValueError('2145 plug: %d bytes after the texture block' % (len(r.data) - r.at))
        return plug
    steps = r.unpack('i')[0] if r.at < len(r.data) else 0
    plug['trace'] = dict(steps=steps, color=r.unpack('I')[0], positions=r.floats(2)) if steps > 0 else None
    flag = r.unpack('i')[0] if r.at < len(r.data) else 0
    # The embedded mesh is read only where an effect draws on it (ko_weapon_fx).
    plug['fx_data'] = bytes(r.data[r.at:]) if flag else None
    if not flag and r.at != len(r.data):
        raise ValueError('plug trailing data')
    return plug


def plug_transform(plug, bind, height):
    """The plug's placement on its bind joint, for engine-space (Z-reflected)
    points. 004133c0 builds scale x rotation and scales the translation;
    004137d0 applies plug x joint x character."""
    position, rotation, scale = plug['position'], plug['rotation'], plug['scale']
    factor = height / 1.8 * scale[1]

    def transform(v, translation):
        # PMesh reader already reflected Z; plug matrix is still legacy row-major.
        v = [v[0], v[1], -v[2]]
        local = [sum(v[j]*rotation[j*4+i] for j in range(3)) for i in range(3)]
        if translation:
            local = [(local[i]+position[i])*factor for i in range(3)]
        local[2] *= -1
        result = [sum(bind[i][j]*local[j] for j in range(3)) + (bind[i][3] if translation else 0) for i in range(3)]
        if not translation:
            length = math.sqrt(sum(v*v for v in result))
            if length < 1e-8:raise ValueError('plug normal')
            result = [v/length for v in result]
        return result
    return transform, factor


def plug_levels(assets, name, joint, bind, height, slot):
    plug = read_plug(assets, name)
    material, scale = plug['material'], plug['scale']
    if material[:4] != [1, 1, 1, 1] or material[20] != 0 or min(scale) <= 0:
        raise ValueError('plug material/scale unsupported')
    mesh_name, texture_name = plug['mesh'], plug['texture']
    # The trace and FX mesh do not take part in the ordinary opaque equipped
    # mesh; an item's weapon effect draws on the FX mesh (ko_weapon_fx, PQ-211).
    tail_bytes = plug['fx_bytes']
    assets.get(mesh_name)
    normalized = mesh_name.replace('\\', '/')
    path = next(p for p in assets.root.rglob('*.n3pmesh')
                if p.relative_to(assets.root).as_posix().casefold() == normalized.casefold())
    mesh = ko.import_mesh(path, 1.0)
    transform, factor = plug_transform(plug, bind, height)
    vertices = []
    for v in mesh['vertices']:
        vertices.append((transform(v[:3], True), transform(v[3:6], False), v[6:8],
                         [joint, 0, 0, 0], [1, 0, 0, 0], slot))
    geometry = (vertices, mesh['indices'])
    return [geometry]*4, ko_tiles.mip_chains(assets.get(texture_name), skip=1)[0], dict(
        stored_joint=plug['stored_joint'], joint=joint, scale=factor, ignored_fx_bytes=tail_bytes,
        lod='highest refined plug mesh; progressive equipped-plug selection remains open')


def cook(assets, mappings, world, textures, body_slots):
    """Appearance meshes, their N3D3 render states and reports; with them the
    weapon effects of rows that name a KO item number (`ko_item`, PQ-211) for
    ko_fx_bake."""
    import ko_weapon_fx
    appearances, states, reports, weapons = [], [], [], []
    # Binary Height() is maximum joint Y, not max-minus-min or mesh bounds.
    height = max(m[1][3] for m in world)
    for key, row in enumerate(mappings, 1):
        slot = len(textures)
        if 'chrplug_2145' in row:
            # PQ-317 (D-187): a skeletal plug is an N3AT plug entry; its key
            # draws no rigid mesh (2233's CN3ChrTypePlug names none).
            appearances.append(([], [([], [])] * 4))
            states.append(DETAIL_CUT)
            reports.append(dict(item=row['item'], slot=row['slot'], source=row['chrplug_2145'], skeletal=True))
            continue
        if 'part_2145' in row:
            # PQ-319 (D-190): a 2145 armour part (ko_armour_2145.rows), read
            # from the player's 2145 Item pack and drawn on its part slot, as
            # 009b3fc0 names it and 00575010 sets it.
            import ko_armour_2145
            rebuilt = []
            levels, texture = part_levels(ko_armour_2145.source(), row['part_2145'], slot, rebuilt)
            textures.append(texture)
            appearances.append(([body_slots[i] for i in row['parts']], levels))
            states.append(part_state(ko_armour_2145.source(), row['part_2145']))
            reports.append(dict(item=row['item'], slot=row['slot'], source=row['part_2145'], parts=row['parts'],
                                armour_2145=True, triangles=[len(level[1]) // 3 for level in levels],
                                rebuilt_normals=rebuilt, render_state=list(states[-1])))
            continue
        if 'joint' in row:
            joint = row['joint']
            if not 0 <= joint < len(world):raise ValueError('appearance joint')
            levels, texture, report = plug_levels(assets, row['source'], joint, world[joint], height, slot)
            replaces = []
            states.append(DETAIL_CUT)
        else:
            # 0045cd90, the armour-part setter, has no effect path (PQ-210).
            if 'ko_item' in row:raise ValueError('a KO item effect needs a hand plug')
            levels, texture = part_levels(assets, row['source'], slot)
            replaces = [body_slots[i] for i in row['parts']]
            states.append(part_state(assets, row['source']))
            report = dict(parts=row['parts'], render_state=list(states[-1]))
        textures.append(texture)
        appearances.append((replaces, levels))
        if 'ko_item' in row:
            fx = ko_weapon_fx.effect(assets, row['ko_item'])
            geometry = ko_weapon_fx.geometry(assets, row['source'], joint, world[joint], height) if fx['main'] else None
            report['weapon_effect'] = dict(fx, fx_mesh=bool(geometry), drawn=bool(fx['main'] and geometry))
            # 00415910 draws nothing without the main bundle or the FX mesh.
            if fx['main'] and geometry:
                weapons.append(dict(fx, key=key, joint=joint, ko_item=row['ko_item'], geometry=geometry))
        reports.append(dict(item=row['item'], slot=row['slot'], source=row['source'], **report))
    return appearances, states, reports, weapons
