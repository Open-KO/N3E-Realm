"""Generic N3D1/N3D2/N3D3/N3DI/N3DJ serialization. All historical selection policy is package data."""
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
# RQ-191: the client's detail reader (client/assets/assets.cpp
# load_render_detail) reads each vertex normal's components as cooked floats
# (Reader::f: finite, magnitude at most COOKED_FLOAT_BOUND, common) and
# refuses a normal whose float length is not above 1e-10 (norm, "zero
# normal"); serialize refuses the same normal so a cook fails rather than
# n3e-asset-check. ko_detail rebuilds a KO corner without a normal first
# (D-177, ko_character.corner_normals).
ZERO_NORMAL = 1e-10


def _f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def check_normal(n):
    """A detail vertex normal the client reader accepts; returns it. Its
    length is taken in single precision as the client's norm does (each
    product and sum rounded to a float: exact for these operations, since a
    double holds more than twice a float's precision)."""
    if len(n) != 3:
        raise ValueError('detail vertex normal without three components')
    if not all(math.isfinite(x) for x in n):
        raise ValueError('detail vertex normal not finite')
    try:
        x, y, z = (_f32(c) for c in n)
    except OverflowError:
        raise ValueError('detail vertex normal past the cooked float bound') from None
    if any(abs(c) > COOKED_FLOAT_BOUND for c in (x, y, z)):
        raise ValueError('detail vertex normal past the cooked float bound')
    length = _f32(math.sqrt(_f32(_f32(_f32(x * x) + _f32(y * y)) + _f32(z * z))))
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


def further(vertex):
    """A detail vertex's influences past its four slots that carry weight, as
    (joint, weight) pairs in order (an entry of the N3DI / N3DJ table)."""
    _, _, _, joints, weights, _ = vertex
    if len(joints) != len(weights) or len(joints) < 4:
        raise ValueError('detail vertex influences')
    return [(j, w) for j, w in zip(joints[4:], weights[4:]) if w > 0]


def serialize(view, thresholds, workload, world_count, textures, radius, levels, attachments=(), appearances=(),
              states=None, influences=False):
    """`states`, when not None, is one render state per appearance entry and
    makes the file N3D3; without it the bytes are N3D2's (or N3D1's) as before.
    `influences` (ko_detail, RQ-164) admits vertices with more than four
    joint influences; when one carries weight past its four slots the file is
    N3DI (N3D2's layout) or N3DJ (N3D3's) with an influence table in every
    geometry, and without one the bytes are as before. Without `influences`
    such a vertex is refused. A vertex normal the client reader refuses (not
    finite, past the cooked float bound or without direction: check_normal)
    is refused."""
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
    magic = (b'N3DJ' if tables else b'N3D3') if states is not None else \
        (b'N3DI' if tables else b'N3D2') if appearances else b'N3D1'
    out=bytearray(magic+f(view)+f([v for row in thresholds for v in row]))
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
            for mesh in meshes:out+=geometry(mesh)
            if states is not None:
                flags, reference, source, destination = check_state(states[index])
                out+=u(flags)+f([float(reference)])+u(source)+u(destination)
    if len(out)>128*1024*1024:raise ValueError('render detail budget')
    return out
