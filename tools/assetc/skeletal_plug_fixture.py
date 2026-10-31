"""An original synthetic skeletal plug for the PQ-317 checks: a "bow" on a
two-joint skeleton. Original n3e implementation; no imported assets.

The bow is a thin upright strip in two halves, drawn both ways: the lower half
on joint 0 (the root) and the upper half, from 0.25 up, on joint 1, which
stands 0.25 above the root and turns about z. Its four N3S1 clips stand for a
2233 plug character's clips in model slots 0-3: slot 0 a looping sway (the
plug's breath), slot 1 a bend (attackbreath, played once), slot 2 a deeper
bend (magic, once) and slot 3 the sway again. Its normals point along +z
(PQ-359), which the placement's quarter turn, the sway and the wearer joint's
turn, all about z, leave unchanged, so the bow takes one light at every clip
time and a check can set it beside a wearer's part with the same normal.

PLACEMENT is the plug matrix the entries carry (rows of a 3x4: a quarter turn
about z, 0.8 scale, a small offset), so a check can tell it from the joint's own
frame; CLIP_MAP is the clip map of the fixture's player."""
import math
import struct

from common import f, u

CLIPS = [
    dict(duration=1.0, blend=0.0, loop_blend=False, markers=[-1, -1]),
    dict(duration=0.6, blend=0.0, loop_blend=False, markers=[-1, -1]),
    dict(duration=0.8, blend=0.0, loop_blend=False, markers=[-1, -1]),
    dict(duration=1.0, blend=0.0, loop_blend=False, markers=[-1, -1]),
]
# Joint 1's rotation about z per slot (time, angle): a sway out and back.
KEYS = [
    [(0, 0.0), (0.25, 0.6), (0.5, 0.0), (0.75, -0.6), (1.0, 0.0)],
    [(0, 0.0), (0.6, 0.9)],
    [(0, 0.0), (0.8, 1.4)],
    [(0, 0.0), (0.25, 0.6), (0.5, 0.0), (0.75, -0.6), (1.0, 0.0)],
]
MID, TOP, HALF = 0.25, 0.75, 0.08
# A quarter turn about z at 0.8 scale, then an offset: x' = -0.8 y + 0.05,
# y' = 0.8 x + 0.1, z' = 0.8 z - 0.05.
PLACEMENT = [0.0, -0.8, 0.0, 0.05,
             0.8, 0.0, 0.0, 0.1,
             0.0, 0.0, 0.8, -0.05]
# The wearer's pose states (client/render/player_pose.h) to slots: the sway
# while idle, moving, dead or sitting, the bend once when attacking or ready.
CLIP_MAP = ([dict(kind="state", id=s, slot=0, once=False) for s in (0, 1, 3, 4, 5, 7, 8, 9)]
            + [dict(kind="state", id=s, slot=1, once=True) for s in (2, 6)])
GREY = 128


def quaternion_z(angle):
    return [0.0, 0.0, math.sin(angle / 2), math.cos(angle / 2)]


def mesh():
    """Two strips, each both ways: the lower on joint 0, the upper on joint 1."""
    vertices, indices = [], []
    for joint, low, high in ((0, -MID, MID), (1, MID, TOP)):
        base = len(vertices)
        for x, y in ((-HALF, low), (HALF, low), (HALF, high), (-HALF, high)):
            vertices.append(((x, y, 0.0), (0, 0, 1), ((x + HALF) / (2 * HALF), (y + MID) / (TOP + MID)), joint))
        indices += [base + i for i in (0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2)]
    return vertices, indices


def clip(slot, grey=GREY, atlas=4):
    """One N3S1 clip of the bow in model slot `slot`."""
    data = b"N3S1" + u(atlas) + u(atlas) + bytes([grey] * 3) * (atlas * atlas)
    data += u(2) + struct.pack("<i", -1) + f([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])
    data += struct.pack("<i", 0) + f([0, MID, 0, 0, 0, 0, 1, 1, 1, 1])
    data += u(2) + u(0) + f([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    data += u(1) + f([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -MID, 0, 1])
    keys = KEYS[slot]
    data += u(1) + u(1) + u(1) + u(len(keys))
    for time, angle in keys:
        data += f([time] + quaternion_z(angle))
    vertices, indices = mesh()
    data += u(len(vertices))
    for position, normal, uv, joint in vertices:
        data += f(list(position) + list(normal) + list(uv)) + u(joint) + u(0) * 3 + f([1, 0, 0, 0])
    data += u(len(indices)) + b"".join(u(i) for i in indices)
    return data + f([1, 1, 1]) + u(0)


def write(root, name="bow", grey=GREY):
    """Writes `<name>-<slot>.bin` for the four slots under `root`; returns the
    manifest's clip list (sources relative to `root`)."""
    out = []
    for slot, timing in enumerate(CLIPS):
        source = f"{name}-{slot}.bin"
        (root / source).write_bytes(clip(slot, grey))
        out.append(dict(source=source, **timing))
    return out


def centre(slot, time):
    """The centre of the bow's skinned vertices at `time` in `slot`, in its own
    frame: the lower strip's centre is (0, 0) and the upper strip's turns about
    joint 1, so the centre is the mean of the two."""
    keys = KEYS[slot]
    time = min(max(time, 0.0), keys[-1][0])
    k = next(i for i in range(len(keys) - 1) if time <= keys[i + 1][0])
    (t0, a0), (t1, a1) = keys[k], keys[k + 1]
    angle = a0 + (a1 - a0) * (time - t0) / (t1 - t0)
    cy = (TOP - MID) / 2
    upper = (-math.sin(angle) * cy, MID + math.cos(angle) * cy, 0.0)
    return [(0.0 + upper[0]) / 2, (0.0 + upper[1]) / 2, 0.0]
