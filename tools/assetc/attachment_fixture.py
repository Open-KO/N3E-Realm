"""Original synthetic attached-character models for the PQ-328 checks. Original
n3e implementation; no imported assets.

A "wing" is one wide upright quad standing on a one-joint skeleton, drawn
both ways, with its normal pointing down so that the fixture's light leaves it
at the ambient term and only an attachment's emissive and modulate brighten
it. A "fairy" adds a second part, a small box, so a lit prefix can cover the
first part only. Four N3S1 clips (idle, walk, attack, death) turn the root,
so the checks can tell the clip and the placement apart."""
import math
import struct

from common import f, u

CLIPS = [
    dict(duration=1.0, blend=0.0, loop_blend=False, markers=[-1, -1]),
    dict(duration=0.5, blend=0.0, loop_blend=False, markers=[-1, -1]),
    dict(duration=0.6, blend=0.0, loop_blend=False, markers=[-1, -1]),
    dict(duration=1.0, blend=0.0, loop_blend=False, markers=[-1, -1]),
]
# Root rotation keys per state (time, axis, angle): a slow beat at rest, a fast
# one while walking, a lift on attack, a fold on death.
KEYS = [
    [(0, 1, 0), (0.5, 1, 0.12), (1.0, 1, 0)],
    [(0, 1, 0), (0.25, 1, 0.25), (0.5, 1, 0)],
    [(0, 0, 0), (0.3, 0, -0.3), (0.6, 0, 0)],
    [(0, 0, 0), (1.0, 0, 1.2)],
]
GREY = 128


def quaternion(axis, angle):
    q = [0.0, 0.0, 0.0, math.cos(angle / 2)]
    q[axis] = math.sin(angle / 2)
    return q


def wing(span=1.4, low=0.1, high=0.9, z=-0.15):
    """The wing quad, both windings, its normal pointing down."""
    corners = [(-span / 2, low), (span / 2, low), (span / 2, high), (-span / 2, high)]
    vertices = [((x, y, z), (0, -1, 0), ((x + span / 2) / span, (y - low) / (high - low))) for x, y in corners]
    return vertices, [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]


def box(size=0.2, height=0.3):
    """A small box above the joint, both windings, normals pointing down."""
    s = size / 2
    vertices, indices = [], []
    for x0, x1, z0, z1 in [(-s, s, -s, -s), (-s, s, s, s), (-s, -s, -s, s), (s, s, -s, s)]:
        base = len(vertices)
        for x, y, z in [(x0, height, z0), (x1, height, z1), (x1, height + size, z1), (x0, height + size, z0)]:
            vertices.append(((x, y, z), (0, -1, 0), (0.5, 0.5)))
        indices += [base, base + 1, base + 2, base, base + 2, base + 3, base, base + 2, base + 1, base, base + 3, base + 2]
    return vertices, indices


def mesh(shape):
    if shape == "wing":
        return wing()
    vertices, indices = wing(span=0.5, low=0.0, high=0.3, z=0.0)
    extra, more = box()
    return vertices + extra, indices + [len(vertices) + i for i in more]


def clip(state, shape="wing", grey=GREY, atlas=4):
    """One N3S1 clip of the model in `state` (0 idle .. 3 death)."""
    data = b"N3S1" + u(atlas) + u(atlas) + bytes([grey] * 3) * (atlas * atlas)
    data += u(1) + struct.pack("<i", -1) + f([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])
    data += u(1) + u(0) + f([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    keys = KEYS[state]
    data += u(1) + u(0) + u(1) + u(len(keys))
    for time, axis, angle in keys:
        data += f([time] + quaternion(axis, angle))
    vertices, indices = mesh(shape)
    data += u(len(vertices))
    for position, normal, uv in vertices:
        data += f(list(position) + list(normal) + list(uv)) + u(0) * 4 + f([1, 0, 0, 0])
    data += u(len(indices)) + b"".join(u(i) for i in indices)
    return data + f([1, 1, 1]) + u(0)


def write(root, name, shape="wing", grey=GREY):
    """Writes `<name>-<state>.bin` for the four states under `root`; returns
    the manifest's clip list (sources relative to `root`)."""
    out = []
    for state, timing in enumerate(CLIPS):
        source = f"{name}-{('idle', 'walk', 'attack', 'death')[state]}.bin"
        (root / source).write_bytes(clip(state, shape, grey))
        out.append(dict(source=source, **timing))
    return out


def indices(shape):
    """The model's index count and its first part's (the wing quad's)."""
    return len(mesh(shape)[1]), len(wing()[1])
