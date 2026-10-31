"""Original OPD collision fixtures. No reference bytes are copied or required.

The fixture is asymmetric in width and depth and places distinct geometry per
cell, so a swapped cell iteration order or a mixed-up sub-cell order fails.
"""

from common import *
import ko_shapes

SENTINEL = -3.4028234663852886e38


def triangle(i):
    """Distinct, non-degenerate, upward-facing triangle for face index i."""
    x, z = 1.0 + i * 3, 2.0 + i * 5
    return [[x, 0.5 * i, z], [x, 0.5 * i, z + 2.0], [x + 2.0, 0.5 * i, z]]


def build(
    version=1,
    name="fixture_shapes",
    width=64.0,
    depth=32.0,
    faces=6,
    cells=((0, 0, (0, 1)), (1, 1, (2,))),
    shape_count=3,
    degenerate=(),
    sentinel=(),
    tall=(),
    bad_index=False,
    shapes=(),
    headerless=False,
):
    """Serialize one OPD header plus collision block in the reference layout.

    `headerless` leaves out the version and name, as the pre-1264 (1097) files do.
    A version of 0 or below writes no name length or name (`name` is unused),
    as the 1298 client reads none then (PQ-275)."""
    out = bytearray()
    if not headerless:
        out += struct.pack("<i", version)
        if version > 0:
            out += struct.pack("<i", len(name)) + name.encode("ascii")
    out += struct.pack("<ff", width, depth)
    out += struct.pack("<i", faces)
    for i in range(faces):
        tri = triangle(i)
        if i in degenerate:
            tri[2] = list(tri[0])  # zero area
        if i in sentinel:
            tri[1][1] = SENTINEL
        if i in tall:
            tri[1][1] = 5000.0
        for p in tri:
            out += struct.pack("<fff", *p)

    across = int(width // ko_shapes.CELL_MAIN_SIZE)
    down = int(depth // ko_shapes.CELL_MAIN_SIZE)
    placed = {(x, z): used for x, z, used in cells}
    for z in range(down):
        for x in range(across):
            used = placed.get((x, z))
            if used is None:
                out += struct.pack("<i", 0)
                continue
            out += struct.pack("<i", 1)
            out += struct.pack("<i", 1) + struct.pack("<H", x * 16 + z)
            for sz in range(ko_shapes.CELL_MAIN_DIVIDE):
                for sx in range(ko_shapes.CELL_MAIN_DIVIDE):
                    # Only sub-cell (0,0) carries this cell's faces, so a
                    # transposed sub-cell walk lands on the wrong entry.
                    if (sx, sz) != (0, 0):
                        out += struct.pack("<i", 0)
                        continue
                    out += struct.pack("<i", len(used))
                    for face in used:
                        base = 9999 if bad_index else face * 3
                        out += struct.pack("<III", base, base + 1, base + 2)
    out += struct.pack("<i", len(shapes) if shapes else shape_count)
    for spec in shapes:
        out += shape_record(**spec)
    return bytes(out)


def name(text):
    return struct.pack("<i", len(text)) + text.encode("ascii")


def shape_record(kind=0x400, label="prop", position=(1.0, 2.0, 3.0),
                 rotation=(0.0, 0.0, 0.0, 1.0), scale=(1.0, 1.0, 1.0),
                 parts=(("mesh.n3pmesh", ("skin.dxt",), 0.0),),
                 anim_keys=0, event_id=0, event_type=0, npc_id=0,
                 npc_status=0, collision_mesh="", climb_mesh=""):
    """One CN3Shape record in the reference layout."""
    out = bytearray()
    out += struct.pack("<I", kind)
    out += name(label)
    out += struct.pack("<fff", *position)
    out += struct.pack("<ffff", *rotation)
    out += struct.pack("<fff", *scale)
    for i in range(3):
        if anim_keys and i == 0:
            out += struct.pack("<i", anim_keys)      # count
            out += struct.pack("<i", 0)              # KEY_VECTOR3
            out += struct.pack("<f", 30.0)           # sampling rate
            out += b"\0" * (12 * anim_keys)
        else:
            out += struct.pack("<i", 0)
    out += name(collision_mesh)
    out += name(climb_mesh)
    out += struct.pack("<i", len(parts))
    for part in parts:
        # (mesh, textures, texture fps[, render flags[, diffuse alpha[,
        # (source blend, destination blend)]]])
        mesh, textures, fps = part[0], part[1], part[2]
        flags = part[3] if len(part) > 3 else 0
        alpha = part[4] if len(part) > 4 else 1.0
        blend = part[5] if len(part) > 5 else (5, 6)
        out += struct.pack("<fff", 0.5, 0.25, 0.125)  # pivot
        out += name(mesh)
        # __Material: _D3DMATERIAL9 (17 floats, diffuse alpha fourth) then
        # dwColorOp, dwColorArg1, dwColorArg2, nRenderFlags, dwSrcBlend,
        # dwDestBlend.
        out += struct.pack("<4f", 1.0, 1.0, 1.0, alpha)
        out += struct.pack("<13f", *([0.0] * 13))
        out += struct.pack("<6I", 4, 2, 1, flags, *blend)
        out += struct.pack("<i", len(textures)) + struct.pack("<f", fps)
        for t in textures:
            out += name(t)
    out += struct.pack("<iiiii", 7, event_id, event_type, npc_id, npc_status)
    return bytes(out)
