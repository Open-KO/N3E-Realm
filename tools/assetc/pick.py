"""Package actor pick policy (PQ-146, D-138). Original n3e code.

Source form (package manifest key ``pick``)::

    {"box": "joints", "min_extent": 0.5, "pad": 0.25, "mesh_lod": 1}

The client casts the cursor ray at each drawn actor's box, the axis-aligned box
of the actor model's joint positions (``box: "joints"``, KO ``0041c300``) or of
its skinned vertices (``"vertices"``). An axis shorter than ``min_extent`` metres
grows by ``pad`` metres on each side (KO: 0.5 and 0.25). When the ray hits
several boxes, actors at LOD ``mesh_lod`` or finer are tested against their drawn
triangles and coarser ones against their box (KO ``0041c7d0``: LOD 0-1 mesh, 2-3
box). Cooked as ``pick.bin``: ``N3PK``, u32 box (0 vertices, 1 joints), f32
min_extent, f32 pad, u32 mesh_lod.
"""
import math

from common import f, u

FIELDS = ("box", "min_extent", "pad", "mesh_lod")
BOXES = ("vertices", "joints")


def cook(c):
    if not isinstance(c, dict) or set(c) != set(FIELDS):
        raise ValueError("pick fields")
    for key in ("min_extent", "pad"):
        if type(c[key]) not in (int, float) or not math.isfinite(c[key]) or not 0 <= c[key] <= 4:
            raise ValueError("pick box bounds")
    if type(c["mesh_lod"]) is not int or not 0 <= c["mesh_lod"] <= 3:
        raise ValueError("pick mesh LOD")
    if c["box"] not in BOXES:
        raise ValueError("pick box source")
    return b"N3PK" + u(BOXES.index(c["box"])) + f([c["min_extent"], c["pad"]]) + u(c["mesh_lod"])
