"""Original synthetic NPC looks models for the PQ-253 checks. Original n3e
implementation; no imported assets.

Each model is a one-joint box standing on the ground with a solid-colour atlas
and four N3S1 clips (idle, walk, attack, death) that turn its root node, so the
checks can tell two looks apart by shape and colour in a capture."""
import math
import struct

from common import f, u

# Clip timing per state (seconds): idle and walk loop, attack and death do not.
CLIPS = [
    dict(duration=1.0, blend=0.2, loop_blend=True, markers=[-1, -1]),
    dict(duration=0.8, blend=0.2, loop_blend=True, markers=[-1, -1]),
    dict(duration=0.6, blend=0.1, loop_blend=False, markers=[0.3, -1]),
    dict(duration=1.0, blend=0.1, loop_blend=False, markers=[-1, -1]),
]
# Root rotation keys per state: (time, axis, angle).
KEYS = [
    [(0, 1, 0), (0.5, 1, 0.2), (1.0, 1, 0)],
    [(0, 1, 0), (0.4, 1, -0.3), (0.8, 1, 0)],
    [(0, 0, 0), (0.3, 0, 0.5), (0.6, 0, 0)],
    [(0, 0, 0), (1.0, 0, 1.5)],
]
SHAPES = {
    # A tall, thin pillar and a wide, low slab.
    "pillar": (0.5, 1.8, 0.5),
    "slab": (1.6, 0.7, 1.0),
}


def quaternion(axis, angle):
    q = [0.0, 0.0, 0.0, math.cos(angle / 2)]
    q[axis] = math.sin(angle / 2)
    return q


def box(size):
    """Vertices (position, normal, uv) and indices of a box on the ground."""
    sx, sy, sz = size[0] / 2, size[1], size[2] / 2
    faces = [
        ((1, 0, 0), [(sx, 0, -sz), (sx, sy, -sz), (sx, sy, sz), (sx, 0, sz)]),
        ((-1, 0, 0), [(-sx, 0, sz), (-sx, sy, sz), (-sx, sy, -sz), (-sx, 0, -sz)]),
        ((0, 1, 0), [(-sx, sy, -sz), (-sx, sy, sz), (sx, sy, sz), (sx, sy, -sz)]),
        ((0, -1, 0), [(-sx, 0, sz), (-sx, 0, -sz), (sx, 0, -sz), (sx, 0, sz)]),
        ((0, 0, 1), [(sx, 0, sz), (sx, sy, sz), (-sx, sy, sz), (-sx, 0, sz)]),
        ((0, 0, -1), [(-sx, 0, -sz), (-sx, sy, -sz), (sx, sy, -sz), (sx, 0, -sz)]),
    ]
    vertices, indices = [], []
    for normal, corners in faces:
        base = len(vertices)
        for i, p in enumerate(corners):
            vertices.append((p, normal, (i % 2, i // 2)))
        # Both windings, so the box draws whichever way the cull test faces.
        indices += [base, base + 1, base + 2, base, base + 2, base + 3,
                    base, base + 2, base + 1, base, base + 3, base + 2]
    return vertices, indices


def clip(state, size, color, atlas=4, still=False):
    """One N3S1 clip of the box model in `state` (0 idle .. 3 death); `still`
    holds the idle clip's root unturned."""
    data = b"N3S1" + u(atlas) + u(atlas) + bytes(color) * (atlas * atlas)
    data += u(1) + struct.pack("<i", -1) + f([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])
    data += u(1) + u(0) + f([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    keys = [(time, axis, 0) for time, axis, _ in KEYS[state]] if still and state == 0 else KEYS[state]
    data += u(1) + u(0) + u(1) + u(len(keys))
    for time, axis, angle in keys:
        data += f([time] + quaternion(axis, angle))
    vertices, indices = box(size)
    data += u(len(vertices))
    for position, normal, uv in vertices:
        data += f(list(position) + list(normal) + list(uv)) + u(0) * 4 + f([1, 0, 0, 0])
    data += u(len(indices)) + b"".join(u(i) for i in indices)
    return data + f([1, 1, 1]) + u(0)


def write(root, name, shape, color, atlas=4, still=False):
    """Writes `<name>-<state>.bin` for the four states under `root`; returns the
    manifest's looks clip list (sources relative to `root`). `still` keeps the
    idle clip's timing but not its turn, so a capture of an idle model does not
    depend on the idle phase it was taken at (PQ-375)."""
    out = []
    for state, timing in enumerate(CLIPS):
        source = f"{name}-{('idle', 'walk', 'attack', 'death')[state]}.bin"
        (root / source).write_bytes(clip(state, SHAPES[shape], color, atlas, still))
        out.append(dict(source=source, **timing))
    return out


# PQ-265 (D-173): N3SM clips, a looks model whose parts draw with their own
# render states. Run fields as tools/assetc/gltf.py writes them.
BLEND, DOUBLE_SIDED, UNLIT = 1, 2, 4
SRC_ALPHA, ONE_MINUS_SRC_ALPHA = 4, 5


def shell(size, u0, u1, inward=False):
    """Vertices and indices of a box on the ground with one winding (outward
    unless `inward`), each face mapping u0 .. u1 by 0 .. 1 of the atlas."""
    sx, sy, sz = size[0] / 2, size[1], size[2] / 2
    faces = [
        ((1, 0, 0), [(sx, 0, sz), (sx, 0, -sz), (sx, sy, -sz), (sx, sy, sz)]),
        ((-1, 0, 0), [(-sx, 0, -sz), (-sx, 0, sz), (-sx, sy, sz), (-sx, sy, -sz)]),
        ((0, 1, 0), [(-sx, sy, sz), (sx, sy, sz), (sx, sy, -sz), (-sx, sy, -sz)]),
        ((0, -1, 0), [(-sx, 0, -sz), (sx, 0, -sz), (sx, 0, sz), (-sx, 0, sz)]),
        ((0, 0, 1), [(-sx, 0, sz), (sx, 0, sz), (sx, sy, sz), (-sx, sy, sz)]),
        ((0, 0, -1), [(sx, 0, -sz), (-sx, 0, -sz), (-sx, sy, -sz), (sx, sy, -sz)]),
    ]
    vertices, indices = [], []
    for normal, corners in faces:
        base = len(vertices)
        for p, (u, v) in zip(corners, ((u0, 1), (u1, 1), (u1, 0), (u0, 0))):
            vertices.append((p, normal, (u, v)))
        quad = [base, base + 1, base + 2, base, base + 2, base + 3]  # counter-clockwise from outside
        indices += quad[::-1] if inward else quad
    return vertices, indices


def roof(size, height, u0, u1):
    """One horizontal quad at `height` facing down (seen from above it is a
    back face), mapping u0 .. u1 of the atlas."""
    sx, sz = size[0] / 2, size[2] / 2
    corners = [(-sx, height, -sz), (sx, height, -sz), (sx, height, sz), (-sx, height, sz)]
    vertices = [(p, (0, -1, 0), uv) for p, uv in zip(corners, ((u0, 1), (u1, 1), (u1, 0), (u0, 0)))]
    return vertices, [0, 1, 2, 0, 2, 3]


def material_clip(state, parts, width, height, rgba):
    """One N3SM clip in `state` (0 idle .. 3 death): `parts` are (vertices,
    indices, flags, alpha reference, source, destination), one run each, in
    draw order; `rgba` the width x height atlas."""
    data = b"N3SM" + u(width) + u(height) + bytes(rgba)
    data += u(1) + struct.pack("<i", -1) + f([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])
    data += u(1) + u(0) + f([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    keys = KEYS[state]
    data += u(1) + u(0) + u(1) + u(len(keys))
    for time, axis, angle in keys:
        data += f([time] + quaternion(axis, angle))
    vertices, indices, runs = [], [], []
    for part_vertices, part_indices, *state_fields in parts:
        runs.append((len(indices), len(part_indices), *state_fields))
        indices += [len(vertices) + i for i in part_indices]
        vertices += part_vertices
    data += u(len(vertices))
    for position, normal, uv in vertices:
        data += f(list(position) + list(normal) + list(uv)) + u(0) * 4 + f([1, 0, 0, 0])
    data += u(len(indices)) + b"".join(u(i) for i in indices)
    data += u(len(runs))
    for first, n, flags, reference, source, destination in runs:
        data += u(first) + u(n) + u(flags) + f([reference]) + u(source) + u(destination)
    return data + f([1, 1, 1]) + u(0)


def write_materials(root, name, parts, width, height, rgba):
    """Writes `<name>-<state>.bin` (N3SM) for the four states; returns the
    manifest's looks clip list."""
    out = []
    for state, timing in enumerate(CLIPS):
        source = f"{name}-{('idle', 'walk', 'attack', 'death')[state]}.bin"
        (root / source).write_bytes(material_clip(state, parts, width, height, rgba))
        out.append(dict(source=source, **timing))
    return out
