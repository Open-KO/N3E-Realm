"""Generic N3D1/N3D2/N3D3 serialization. All historical selection policy is package data."""
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


def serialize(view, thresholds, workload, world_count, textures, radius, levels, attachments=(), appearances=(),
              states=None):
    """`states`, when not None, is one render state per appearance entry and
    makes the file N3D3; without it the bytes are N3D2's (or N3D1's) as before."""
    if states is not None and (not appearances or len(states) != len(appearances)):
        raise ValueError('appearance render state count')
    magic = b'N3D3' if states is not None else b'N3D2' if appearances else b'N3D1'
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
        for p,n,uv,joints,weights,slot in vertices:
            b+=f(p+n+uv)+b''.join(u(j) for j in joints)+f(weights)+u(slot)
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
