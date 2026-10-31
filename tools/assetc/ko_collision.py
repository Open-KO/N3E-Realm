"""KX-03: one collision bake from a local KO map's terrain and object data.

Moved from ko_bake.py (PQ-234) so the map bake (`ko_scene.bake_world`) does not
import the package assembly; ko_bake re-exports `bake`.

Both runtimes already consume a single `collision.bin` (`N3C1`) that is part of
the hashed release index — `client/assets/assets.cpp` and
`server/src/content.rs` read the same bytes — so this does not invent a second
artifact or a second identity. It produces the triangles that bake feeds on.

Coordinates follow the accepted scale-1 adoption with `(x, y, z) -> (x, y, -z)`,
plus a translation that centres the 512 m map on the origin. Terrain expresses
the z flip by reversing sample order, which leaves the generated grid winding
untouched; object triangles negate z directly and therefore reverse their vertex
order to keep their facing. The two agree: terrain row `z` sits at world
`-half + z * spacing`, and an object vertex at KO `z` sits at `half - z`, which
is the same line.

Real local data carries three classes of unusable collision face. Each is
resolved explicitly here and counted in the provenance rather than silently
dropped, because the cooker rejects degenerate collision outright and would
otherwise fail at cook time with no explanation.
"""

from common import *
import ko_shapes
import ko_terrain


# Vertical clamp for barrier geometry. The reference builds map walls as spans
# to +/-5000 m, which is far outside anything reachable; keeping them unbounded
# would bloat the collision extent for no gain, so they are clamped to a margin
# around the terrain.
BARRIER_MARGIN = 40.0


def _transform(x, y, z, half):
    """KO metres to n3e world coordinates: centre the map and negate z."""
    return [x - half, y, half - z]


def bake(gtd_path, opd_path, max_samples=ko_terrain.MAX_SUPPORTED_SAMPLES, headerless=False):
    """Return the heightfield, collision triangles and a provenance record.

    `max_samples` is ko_terrain's 129-sample cap unless the caller bakes the
    chunked world (PQ-234), whose package cooks N3C2 collision of up to 513.
    `headerless` reads the pre-1264 (1097) GTD and OPD (PQ-222, PQ-274); the
    caller says which layout it has."""
    terrain = ko_terrain.load(gtd_path, max_samples, headerless=headerless)
    shapes = ko_shapes.load_collision(opd_path, headerless=headerless)

    samples, spacing = terrain["samples"], terrain["spacing"]
    extent = (samples - 1) * spacing
    if abs(shapes["width"] - extent) > 0.5 or abs(shapes["depth"] - extent) > 0.5:
        raise ValueError(
            "terrain extent %g does not match object extent %g x %g"
            % (extent, shapes["width"], shapes["depth"]))
    half = extent / 2.0

    # Reversing sample order along z applies the z flip to the surface without
    # disturbing the grid the cooker triangulates, so winding stays upward.
    heights = [
        terrain["heights"][(samples - 1 - z) * samples + x]
        for z in range(samples)
        for x in range(samples)
    ]
    low, high = min(heights), max(heights)
    floor, ceiling = low - BARRIER_MARGIN, high + BARRIER_MARGIN

    vertices = shapes["vertices"]
    kept, dropped, clamped = [], 0, 0
    for face in range(shapes["faces"]):
        points = vertices[face * 3:face * 3 + 3]
        if any(abs(c) > ko_shapes.SENTINEL_LIMIT for p in points for c in p):
            continue  # replaced by a barrier below
        a, b, c = points
        ab = [b[i] - a[i] for i in range(3)]
        ac = [c[i] - a[i] for i in range(3)]
        cross = [ab[1] * ac[2] - ab[2] * ac[1],
                 ab[2] * ac[0] - ab[0] * ac[2],
                 ab[0] * ac[1] - ab[1] * ac[0]]
        if sum(v * v for v in cross) < 1e-12:
            dropped += 1  # zero area: nothing to stand on or block
            continue
        out = []
        for px, py, pz in points:
            if py < floor or py > ceiling:
                py = floor if py < floor else ceiling
                clamped += 1
            out.append(_transform(px, py, pz, half))
        out.reverse()  # negating z mirrors handedness; restore the facing
        kept.append(out)

    # Conservative barriers where collision is unknown. The sentinel faces share
    # one small footprint with no usable height, so the area is closed off
    # rather than left open: blocking an unknown is the safe direction.
    barriers = []
    footprints = _sentinel_footprints(shapes)
    for x0, z0, x1, z1 in footprints:
        barriers.extend(_box(x0, z0, x1, z1, floor, ceiling, half))
    kept.extend(barriers)

    provenance = {
        "terrain": ko_terrain.provenance(gtd_path, terrain),
        "objects": ko_shapes.provenance(opd_path, shapes),
        "extent_metres": extent,
        "world_origin": [-half, 0.0, -half],
        "coordinates": "scale 1, (x,y,z) -> (x,y,-z), map centred on the origin",
        "barrier_clamp": [floor, ceiling],
        "faces_dropped_degenerate": dropped,
        "vertices_clamped": clamped,
        "sentinel_footprints": len(footprints),
        "barrier_faces": len(barriers),
        "collision_faces": len(kept),
        "collision_points": len(kept) * 3,
        "terrain_points": (samples - 1) ** 2 * 6,
        "policy": [
            "degenerate faces are dropped; zero area blocks nothing and the "
            "cooker rejects them",
            "faces with a placeholder coordinate are replaced by a closed "
            "barrier over their footprint",
            "barrier spans beyond the terrain margin are clamped, not removed",
        ],
    }
    heightfield = {
        "width": samples,
        "depth": samples,
        "origin": [-half, 0.0, -half],
        "spacing": spacing,
        # Mirroring z inverts the quad-diagonal parity as well as the winding:
        # the reference splits tile (x, z) on `(x + z) % 2` over its own grid
        # (`CN3Terrain::GetHeight` FUN_0059d330, `CN3TerrainPatch::Tick`
        # FUN_005a0410), and this grid's z runs the other way.
        "diagonal": "alternating-mirrored",
        "heights": heights,
    }
    return heightfield, kept, provenance


def _sentinel_footprints(shapes):
    """Axis-aligned footprints of the faces that carry a placeholder height."""
    groups = []
    for face in range(shapes["faces"]):
        points = shapes["vertices"][face * 3:face * 3 + 3]
        if not any(abs(c) > ko_shapes.SENTINEL_LIMIT for p in points for c in p):
            continue
        xs = [p[0] for p in points]
        zs = [p[2] for p in points]
        box = [min(xs), min(zs), max(xs), max(zs)]
        for existing in groups:
            if (box[0] <= existing[2] and box[2] >= existing[0]
                    and box[1] <= existing[3] and box[3] >= existing[1]):
                existing[0] = min(existing[0], box[0])
                existing[1] = min(existing[1], box[1])
                existing[2] = max(existing[2], box[2])
                existing[3] = max(existing[3], box[3])
                break
        else:
            groups.append(box)
    return [g for g in groups if g[2] - g[0] > 1e-3 and g[3] - g[1] > 1e-3]


def _box(x0, z0, x1, z1, floor, ceiling, half):
    """Four closed walls over a footprint, wound outward after the z flip."""
    corners = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    out = []
    for i in range(4):
        ax, az = corners[i]
        bx, bz = corners[(i + 1) % 4]
        p0 = _transform(ax, floor, az, half)
        p1 = _transform(bx, floor, bz, half)
        p2 = _transform(bx, ceiling, bz, half)
        p3 = _transform(ax, ceiling, az, half)
        out.append([p0, p1, p2])
        out.append([p0, p2, p3])
    return out
