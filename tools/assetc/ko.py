"""Independent bounded legacy adapter: highest LOD of the documented PMesh layout.
Only original synthetic files are approved fixtures. Explicit meter calibration
is mandatory. Character/shape/material formats fail rather than lose metadata.
"""

import pathlib, struct

# Measured against the local meshes; see the KX spec's level-of-detail section.
EDGE_COLLAPSE_BYTES = 24  # five ints plus a bool, padded
LOD_CONTROL_BYTES = 8     # float distance plus int vertex count
from common import *


def import_mesh(path, meters_per_unit, detail=False, data=None):
    """A KO progressive mesh: an isolated .n3pmesh file at `path`, or, with
    `data`, the same layout embedded in another file (a plug's FX mesh,
    PQ-211: 00415020 loads it with the mesh's own Load)."""
    if data is None and path.suffix.lower() != ".n3pmesh":
        raise ValueError("unsupported KO variant: only isolated n3pmesh")
    if not 0 < meters_per_unit <= 100:
        raise ValueError("explicit unit calibration required")
    if data is None:
        data = read(path)
    at = 0

    def take(fmt):
        nonlocal at
        n = struct.calcsize("<" + fmt)
        if at + n > len(data):
            raise ValueError("truncated KO mesh")
        v = struct.unpack_from("<" + fmt, data, at)
        at += n
        return v

    length = take("i")[0]
    count(length, 255, 0)
    for _ in range(length):
        take("B")
    collapses, changes, nv, ni, minv, mini = take("6i")
    count(collapses, 65536, 0)
    count(changes, 196608, 0)
    count(nv, 65536)
    count(ni, 196608)
    if not 0 <= minv <= nv or not 0 <= mini <= ni or ni % 3:
        raise ValueError("KO counts")
    vertices = []
    for _ in range(nv):
        p = list(take("8f"))
        finite(p)
        if sum(x * x for x in p[3:6]) < 1e-12:
            raise ValueError("KO normal")
        # Reflect Z, reverse winding: source left-handed Y-up -> engine RH Y-up.
        vertices.append(
            [
                p[0] * meters_per_unit,
                p[1] * meters_per_unit,
                -p[2] * meters_per_unit,
                p[3],
                p[4],
                -p[5],
                p[6],
                p[7],
            ]
        )
    ix = [take("H")[0] for _ in range(ni)]
    if max(ix) >= nv:
        raise ValueError("KO index")
    # A progressive mesh is stored at its LOWEST level of detail, not its
    # highest: `CN3PMeshInstance::Create` (`FUN_00441820`) copies this index
    # array and then starts the instance at `m_iMinNumVertices` /
    # `m_iMinNumIndices`, and `SplitOne` (`FUN_00441b20`) walks the collapse
    # list forwards, growing both counts and **rewriting index values** to
    # `m_iNumVertices - 1` at the positions the change list names. Reading the
    # array as it lies gives the maximum triangle count wired to the collapsed
    # vertices, which is why the meshes came out as torn, hole-ridden geometry.
    #
    # __EdgeCollapse is five ints plus a bool padded to 24 bytes; the binary
    # confirms the stride (`ADD EAX,0x18` at 00441b99) and the field order used
    # below (`[0]` indices to lose, `[1]` indices to change, `[2]` vertices to
    # lose, `[3]` first index change).
    progressive = bool(collapses or changes)
    splits = []
    for _ in range(collapses):
        lose_i, change_i, lose_v, first_change, collapse_to = take("5i")
        should_split = take("B")[0]
        take("3B")  # padding to 24 bytes
        if min(lose_i, change_i, lose_v, first_change) < 0:
            raise ValueError("KO collapse record")
        if not 0 <= collapse_to < nv or should_split not in (0, 1) or lose_i % 3:
            raise ValueError("KO collapse target/group")
        splits.append((lose_i, change_i, lose_v, first_change, should_split, collapse_to))
    index_changes = [take("i")[0] for _ in range(changes)]
    if any(not 0 <= c < ni for c in index_changes):
        raise ValueError("KO index change position")
    stored = ix.copy()
    # Apply every split, in order, exactly as SplitOne does.
    live_v, live_i = minv, mini
    for lose_i, change_i, lose_v, first_change, _, _target in splits:
        live_i += lose_i
        live_v += lose_v
        if live_v > nv or live_i > ni:
            raise ValueError("KO split exceeds the declared maximum")
        if first_change + change_i > changes:
            raise ValueError("KO collapse change range")
        for position in index_changes[first_change:first_change + change_i]:
            ix[position] = live_v - 1
    # Reaching exactly the declared maxima is the check that the collapse
    # records were read with the right stride and field order: a wrong layout
    # cannot land on both totals.
    if (live_v, live_i) != (nv, ni):
        raise ValueError(
            "KO splits reached %d/%d, not the declared %d/%d"
            % (live_v, live_i, nv, ni))
    lods = take("i")[0]
    count(lods, 4096, 0)
    controls = [take("fi") for _ in range(lods)]
    finite([d for d, _ in controls])
    if any(d < 0 or not minv <= v <= nv for d, v in controls):
        raise ValueError("KO LOD control bounds")
    if at != len(data):
        raise ValueError("KO trailing variant")
    for i in range(0, ni, 3):
        ix[i + 1], ix[i + 2] = ix[i + 2], ix[i + 1]
    if any(b[0] <= a[0] for a, b in zip(controls, controls[1:])):
        raise ValueError("KO LOD control order")
    # Preserve the progressive program, not samples of its curve. Reflect both
    # the stored winding and edit positions; runtime budgets follow 00441a50.
    for i in range(0, ni, 3):
        stored[i+1], stored[i+2] = stored[i+2], stored[i+1]
    edits = [i//3*3 + (0,2,1)[i%3] for i in index_changes]
    return {
        "levels": [],  # legacy callers; N3L3 uses progressive_data
        "progressive_data": dict(min_vertices=minv, min_indices=mini,
                                 stored=stored, splits=splits, edits=edits,
                                 controls=controls) if detail else None,
        "vertices": vertices,
        "indices": ix,
        "source_sha256": digest(data).hex(),
        "meters_per_unit": meters_per_unit,
        "adapter_version": 2,
        "progressive": progressive,
        "lod_control_values": lods,
        "warnings": [
            "synthetic-calibrated static mesh only; collision/material/parts/markers require explicit sidecar"
        ] + ([
            "progressive mesh refined from its stored minimum level of detail "
            "to its maximum by replaying every edge-collapse split"
        ] if progressive or lods else []),
    }


if __name__ == "__main__":
    import sys

    try:
        print(
            canonical(
                import_mesh(pathlib.Path(sys.argv[1]), float(sys.argv[2]))
            ).decode()
        )
    except (ValueError, OSError, struct.error) as e:
        sys.exit("KO rejected: " + str(e))
