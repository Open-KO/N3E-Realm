"""Original OPDEXT fixtures in the layout `005b4ef0` / `005b52b0` read (PQ-229).

No reference bytes are copied or required. The defaults extend
`ko_shapes_fixture.build()` (64 x 32 m, OPD cells (0, 0) and (1, 1)): one OPD cell is
re-flagged, one cell is new, and the faces sit in the second sub-cell written so
a transposed sub-cell walk is caught.
"""

from common import *
import ko_shapes


def triangle(i):
    """A tall barrier-like face, unlike any OPD fixture face."""
    x, z = 10.0 + i * 7, 3.0 + i * 4
    return [[x, -5000.0, z], [x, 5000.0, z], [x + 1.0, 5000.0, z]]


def build(version=1, name="", ignored=0, width=64.0, depth=32.0, faces=3,
          cells=((0, 0, 3, (0, 1)), (2, 1, 1, (2,))), cell_version=0, threshold=4,
          bad_index=False, name_length=None, count=None, trailing=b"", vertex=None):
    """Serialize one OPDEXT. `cells` holds (x, z, flag, faces in sub-cell x=1, z=0)."""
    out = bytearray()
    out += struct.pack("<h", version)
    raw = name.encode("latin-1")
    out += struct.pack("<i", len(raw) if name_length is None else name_length) + raw
    out += struct.pack("<h", ignored)
    out += struct.pack("<ff", width, depth)
    out += struct.pack("<i", faces)
    for i in range(max(faces, 0)):
        for p in triangle(i):
            out += struct.pack("<fff", *p)
    if vertex is not None:
        out[-4:] = struct.pack("<f", vertex)
    across = int(width // ko_shapes.CELL_MAIN_SIZE)
    down = int(depth // ko_shapes.CELL_MAIN_SIZE)
    placed = {(x, z): (flag, used) for x, z, flag, used in cells}
    for z in range(down):
        for x in range(across):
            if (x, z) not in placed:
                out += struct.pack("<i", 0)
                continue
            flag, used = placed[(x, z)]
            out += struct.pack("<i", flag) + struct.pack("<h", cell_version)
            if cell_version < 0:
                continue
            for sz in range(ko_shapes.CELL_MAIN_DIVIDE):
                for sx in range(ko_shapes.CELL_MAIN_DIVIDE):
                    if (sx, sz) != (1, 0):
                        out += struct.pack("<i", 0)
                        continue
                    out += struct.pack("<i", len(used) if count is None else count)
                    for face in used:
                        base = 9999 if bad_index else face * 3
                        out += struct.pack("<III", base, base + 1, base + 2)
    if version > 0:
        out += struct.pack("<i", threshold)
    return bytes(out + trailing)
