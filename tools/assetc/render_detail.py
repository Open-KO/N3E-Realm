"""Generic N3D1/N3D2/N3D3/N3DI/N3DJ/N3DH serialization. All historical selection policy is package data."""
import math
import struct
from common import *

# N3D3 (PQ-348, D-191): N3D2 whose appearance entries each end with a render
# state, the N3SM run's fields (gltf.render_state) without its unlit flag:
# flags (1 blend, 2 double-sided), the alpha reference (drawn where the
# texture's 8-bit alpha is above it), the source and destination blend factor
# indices. An unlit part is refused until a check draws it (PQ-280).
STATE_FLAGS = 3
BLEND_FACTOR_COUNT = 10
# N3DI / N3DJ (RQ-164, content/appearance.md): N3D2 / N3D3 whose every
# geometry (the four levels, each attachment, each appearance entry's four)
# carries an influence table between its vertices and its indices, as N3SI
# does (D-176): u32 count of vertices with further influences, then per
# vertex, in strictly increasing order, u32 vertex, u32 n (1-60) and n pairs
# of u32 joint and f32 weight (above 0). KO's skinning 00419f00 sums every
# influence of a vertex. A package with one is engine 44.
INFLUENCE_ENGINE = 44
MAX_FURTHER = 60
# N3DH (RQ-207, content/appearance.md): an appearance entry may hide other
# worn keys. The projection (the view floats) is followed by u32 layout
# flags: HIDE_STATES the N3D3 render state per entry, HIDE_TABLES the N3DI
# influence tables (engine 44), HIDE_KEYS the hidden keys, which every N3DH
# sets (a file that hides nothing keeps N3D2, N3D3, N3DI or N3DJ). The rest is the layout those flags name,
# each appearance entry carrying, after its replacements, u32 count (0-16) and
# that many N3V1 keys it hides while worn: such a key draws no mesh and hides
# no default-body part. A key hides neither itself nor a key twice, and a key
# that hides is hidden by none.
HIDE_STATES, HIDE_TABLES, HIDE_KEYS = 1, 2, 4
MAX_HIDDEN = 16
# RQ-191: the client's detail reader (client/assets/assets.cpp
# load_render_detail) reads each vertex normal's components as cooked floats
# (Reader::f: finite, magnitude at most COOKED_FLOAT_BOUND, common) and
# refuses a normal whose float length is not above ZERO_NORMAL (1e-10; norm,
# "zero normal"; common); serialize refuses the same normal so a cook fails
# rather than n3e-asset-check. ko_detail rebuilds a KO corner without a
# normal first (D-177, ko_character.corner_normals).


def check_normal(n):
    """A detail vertex normal the client reader accepts; returns it. Its
    length is taken in single precision as the client's norm does
    (common.normal_length)."""
    if len(n) != 3:
        raise ValueError('detail vertex normal without three components')
    if not all(math.isfinite(x) for x in n):
        raise ValueError('detail vertex normal not finite')
    try:
        x, y, z = (f32(c) for c in n)
    except OverflowError:
        raise ValueError('detail vertex normal past the cooked float bound') from None
    if any(abs(c) > COOKED_FLOAT_BOUND for c in (x, y, z)):
        raise ValueError('detail vertex normal past the cooked float bound')
    length = normal_length(x, y, z)
    if not length > ZERO_NORMAL:
        raise ValueError('detail vertex normal without direction (length at most %g)' % ZERO_NORMAL)
    return n


def check_state(state):
    """A state tuple (flags, alpha reference, source, destination) within the
    bounds both the cook and the client reader apply; returns it."""
    if not (isinstance(state, tuple) and len(state) == 4):
        raise ValueError('appearance render state')
    flags, reference, source, destination = state
    if not (type(flags) is int and 0 <= flags <= STATE_FLAGS and type(reference) in (int, float)
            and math.isfinite(reference) and 0 <= struct.unpack('<f', struct.pack('<f', reference))[0] < 1
            and type(source) is int and type(destination) is int
            and ((0 <= source < BLEND_FACTOR_COUNT and 0 <= destination < BLEND_FACTOR_COUNT) if flags & 1
                 else source == destination == 0)):
        raise ValueError('appearance render state')
    return state


def check_hides(hides, count):
    """`hides`, one list of N3V1 keys (1-based) per appearance entry, within
    the bounds both the cook and the client reader apply; returns it."""
    if type(hides) is not list or len(hides) != count:
        raise ValueError('appearance hidden key count')
    for key, keys in enumerate(hides, 1):
        if type(keys) is not list or len(keys) > MAX_HIDDEN or len(set(keys)) != len(keys) or any(
                type(k) is not int or not 1 <= k <= count or k == key for k in keys):
            raise ValueError('appearance key %d hidden keys' % key)
    hidden = {k for keys in hides for k in keys}
    for key, keys in enumerate(hides, 1):
        if keys and key in hidden:
            raise ValueError('appearance key %d hides keys and is hidden' % key)
    return hides


HEAD_BYTES = 20  # the magic, the projection and N3DH's layout flags


def layout(head):
    """N3DH's layout flags from render detail beginning with `head` (its
    first HEAD_BYTES bytes), or None for another magic or a short head."""
    head = bytes(head or b'')
    return struct.unpack_from('<I', head, 16)[0] if head[:4] == b'N3DH' and len(head) >= HEAD_BYTES else None


def has_tables(head):
    """Whether render detail beginning with `head` (its first HEAD_BYTES
    bytes, or fewer) carries influence tables: N3DI, N3DJ or an N3DH with
    HIDE_TABLES (RQ-164, RQ-207), which needs engine 44."""
    head = bytes(head or b'')
    return head[:4] in (b'N3DI', b'N3DJ') or bool((layout(head) or 0) & HIDE_TABLES)


def further(vertex):
    """A detail vertex's influences past its four slots that carry weight, as
    (joint, weight) pairs in order (an entry of the N3DI / N3DJ table)."""
    _, _, _, joints, weights, _ = vertex
    if len(joints) != len(weights) or len(joints) < 4:
        raise ValueError('detail vertex influences')
    return [(j, w) for j, w in zip(joints[4:], weights[4:]) if w > 0]


def serialize(view, thresholds, workload, world_count, textures, radius, levels, attachments=(), appearances=(),
              states=None, influences=False, hides=None):
    """`states`, when not None, is one render state per appearance entry and
    makes the file N3D3; without it the bytes are N3D2's (or N3D1's) as before.
    `influences` (ko_detail, RQ-164) admits vertices with more than four
    joint influences; when one carries weight past its four slots the file is
    N3DI (N3D2's layout) or N3DJ (N3D3's) with an influence table in every
    geometry, and without one the bytes are as before. Without `influences`
    such a vertex is refused. A vertex normal the client reader refuses (not
    finite, past the cooked float bound or without direction: check_normal)
    is refused. `hides` (RQ-207), when not None, is one list of N3V1 keys per
    appearance entry that the entry hides while worn (check_hides); when one
    is not empty the file is N3DH, with the flags of the layout above, and
    otherwise the bytes are as before."""
    if hides is not None:
        check_hides(hides, len(appearances))
    hiding = hides is not None and any(hides)
    if states is not None and (not appearances or len(states) != len(appearances)):
        raise ValueError('appearance render state count')
    meshes = list(levels) + [g for g, _ in attachments] + [m for _, ms in appearances for m in ms]
    extra = [further(v) for vertices, _ in meshes for v in vertices if len(v[3]) > 4]
    if extra and not influences:
        raise ValueError('detail vertex past four joint influences')
    tables = any(extra)
    if tables and not appearances:
        raise ValueError('detail influence tables need appearance entries (N3DI / N3DJ)')
    if any(len(x) > MAX_FURTHER for x in extra):
        raise ValueError('detail vertex past %d joint influences' % (4 + MAX_FURTHER))
    if hiding:
        magic, flags = b'N3DH', u(HIDE_KEYS | (HIDE_STATES if states is not None else 0) | (HIDE_TABLES if tables else 0))
    else:
        magic, flags = (b'N3DJ' if tables else b'N3D3') if states is not None else \
            (b'N3DI' if tables else b'N3D2') if appearances else b'N3D1', b''
    out=bytearray(magic+f(view)+flags+f([v for row in thresholds for v in row]))
    out+=b''.join(u(v) for v in workload)+u(world_count)+u(len(textures))
    for chain in textures:
        out+=u(len(chain))
        for w,h,pixels in chain:
            if len(pixels)!=w*h*4:raise ValueError('texture byte count')
            out+=u(w)+u(h)+pixels
    out+=f([radius])+u(len(levels))
    def geometry(g):
        vertices,indices=g
        b=bytearray(u(len(vertices))+u(len(indices)))
        table=[]
        for k,(p,n,uv,joints,weights,slot) in enumerate(vertices):
            check_normal(n)
            b+=f(p+n+uv)+b''.join(u(j) for j in joints[:4])+f(weights[:4])+u(slot)
            pairs=further((p,n,uv,joints,weights,slot)) if len(joints)>4 else []
            if pairs:table.append((k,pairs))
        if tables:
            b+=u(len(table))
            for k,pairs in table:b+=u(k)+u(len(pairs))+b''.join(u(j)+f([w]) for j,w in pairs)
        b+=b''.join(u(i) for i in indices)
        return b
    for level in levels:out+=geometry(level)
    out+=u(len(attachments))
    for g,pm in attachments:
        out+=geometry(g)+u(pm['min_vertices'])+u(pm['min_indices'])
        out+=u(len(pm['controls']))
        for d,v in pm['controls']:out+=f([d])+u(v)
        out+=u(len(pm['splits']))
        for split in pm['splits']:out+=b''.join(u(i) for i in split)
        out+=u(len(pm['edits']))+b''.join(u(i) for i in pm['edits'])
    if appearances:
        out+=u(len(appearances))
        for index, (replaces, meshes) in enumerate(appearances):
            out+=u(len(replaces))+b''.join(u(v) for v in replaces)
            if hiding:
                out+=u(len(hides[index]))+b''.join(u(k) for k in hides[index])
            for mesh in meshes:out+=geometry(mesh)
            if states is not None:
                flags, reference, source, destination = check_state(states[index])
                out+=u(flags)+f([float(reference)])+u(source)+u(destination)
    if len(out)>128*1024*1024:raise ValueError('render detail budget')
    return out
