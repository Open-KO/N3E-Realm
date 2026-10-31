"""PQ-234: an original synthetic KO zone for the chunked bake. No reference bytes.

`write(root, samples=513, ...)` writes a GTD, its colour map (TCT), an OPD
with static placements, two DTex tile files and the Object meshes and
textures they name, laid out as `ko_scene` reads a client tree (`DTex/`,
`Object/`). At 513 samples (2048 m) the terrain alone is beyond N3W1's
196,608 vertices, so the bake writes N3W2 with N3WT textures; at 33 samples
with `object_textures` above the atlas's 323 free slots it is the same small
map whose objects overflow N3W1.

The terrain is a gentle rolling surface, the colour map has one distinct
texture per 128 m region, and the placements are textured pyramids (some
double-sided) on a 128 m lattice, so a capture from anywhere shows terrain,
colour-map regions and objects.
"""
import math
import pathlib
import shutil
import struct

import ko_shapes
import ko_shapes_fixture
import ko_terrain
import ko_terrain_fixture
import ko_tiles
import ko_tiles_fixture

TILE_FILES = ("orig_ground_a.gtt", "orig_ground_b.gtt")
# Every MAPDATA tile index resolves, cycling over the eight (file, ordinal)
# pairs the two tile files hold (as tests/ko_terrain.py's drawn-map fixture).
REFERENCES = tuple((i % 2, (i // 2) % 4) for i in range(1024))
LATTICE = 128.0


def surface(x, z):
    """Sample height in metres at reference sample (x, z)."""
    return round(5 * math.sin(x / 23) * math.cos(z / 31) + 0.01 * x + 4, 3)


def pmesh(points, triangles):
    """One progressive-mesh image with no collapses (stored at full detail):
    `points` are (x, y, z, u, v), `triangles` index them."""
    body = struct.pack("<i", 0)  # empty name
    body += struct.pack("<6i", 0, 0, len(points), len(triangles) * 3, len(points), len(triangles) * 3)
    for x, y, z, tu, tv in points:
        body += struct.pack("<8f", x, y, z, 0.0, 1.0, 0.0, tu, tv)
    body += b"".join(struct.pack("<3H", *t) for t in triangles)
    return body + struct.pack("<i", 0)  # no LOD controls


def pyramid():
    """A unit square pyramid, 2 m wide and 3 m tall, its UVs tiling twice."""
    points = [(-1, 0, -1, 0, 0), (1, 0, -1, 2, 0), (1, 0, 1, 2, 2), (-1, 0, 1, 0, 2), (0, 3, 0, 1, 1)]
    triangles = [(0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0), (0, 1, 2), (0, 2, 3)]
    return pmesh(points, triangles)


def write(root, samples=513, object_textures=2, name="orig_large_zone"):
    """Write the zone under `root`; returns dict(gtd, tct, opd, assets, ...)."""
    root = pathlib.Path(root)
    shutil.rmtree(root, ignore_errors=True)
    for sub in ("DTex", "Object", "Zones"):
        (root / sub).mkdir(parents=True)
    extent = (samples - 1) * ko_terrain.TILE_SIZE
    gtd = root / "Zones" / (name + ".gtd")
    gtd.write_bytes(ko_terrain_fixture.build(
        samples=samples, name=name, sources=tuple("DTex/" + f for f in TILE_FILES),
        references=REFERENCES, surface=surface))
    for i, tile_file in enumerate(TILE_FILES):
        (root / "DTex" / tile_file).write_bytes(
            b"".join(ko_tiles_fixture.texture(16, 16, ko_tiles_fixture.DXT1, 1, "t%d" % k, seed=16 * i + 2 * k)
                     for k in range(4)))
    # Colour map: (patches / 4)^2 textures (0059eff0), each its own colour.
    patches = (samples - 1) // ko_terrain.PATCH_TILE_SIZE
    count = ko_tiles.color_map_side(patches) ** 2
    tct = root / "Zones" / (name + ".tct")
    tct.write_bytes(b"".join(ko_tiles_fixture.texture(16, 16, ko_tiles_fixture.DXT1, 1, "c%d" % k,
                                                      seed=(37 * k) & 0xFE)
                             for k in range(count)))
    (root / "Object" / "orig_pyramid.n3pmesh").write_bytes(pyramid())
    textures = ["orig_stone_%d.dxt" % k for k in range(object_textures)]
    for k, texture in enumerate(textures):
        (root / "Object" / texture).write_bytes(ko_tiles_fixture.texture(16, 16, seed=(3 * k) & 0xFE))
    shapes, k = [], 0
    steps = max(1, int(extent // LATTICE))
    for i in range(steps):
        for j in range(steps):
            x, z = (i + 0.5) * extent / steps, (j + 0.5) * extent / steps
            flags = ko_shapes.RF_DOUBLESIDED if (i + j) % 3 == 0 else 0
            shapes.append(dict(label="pyramid%d" % k, position=(x, surface(int(x // 4), int(z // 4)), z),
                               scale=(4.0, 4.0, 4.0),
                               parts=(("orig_pyramid.n3pmesh", (textures[k % len(textures)],), 0.0, flags),)))
            k += 1
    while k < object_textures:  # one more placement per remaining texture
        x = z = extent / 2 + (k % 8)
        shapes.append(dict(label="extra%d" % k, position=(x, 0.0, z),
                           parts=(("orig_pyramid.n3pmesh", (textures[k],), 0.0),)))
        k += 1
    opd = root / "Zones" / (name + ".opd")
    opd.write_bytes(ko_shapes_fixture.build(name=name, width=extent, depth=extent, shapes=shapes))
    return dict(gtd=gtd, tct=tct, opd=opd, assets=root, samples=samples, extent=extent,
                shapes=len(shapes), tile_textures=8, color_textures=count, object_textures=object_textures)
