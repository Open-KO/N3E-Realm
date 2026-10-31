"""Original asymmetric GTD fixtures. No reference bytes are copied or required.

The fixture is deliberately asymmetric in both axes so a transposed or mirrored
import cannot pass, and every tile field carries a distinct value so a bitfield
decoded by the wrong bit range is visible.
"""

from common import *
import ko_terrain


def height(x, z):
    """Asymmetric, finite, and different under transpose or either mirror.

    Every coefficient is a negative power of two and the inputs are small
    integers, so each value is exact in float32 and the round trip is an
    equality check rather than a tolerance.
    """
    return 0.5 * x + 0.125 * z * z - 0.03125 * x * z


def tile(x, z, samples):
    i = z * samples + x
    return dict(
        full=(x + z) % 2 == 0,
        dir1=(x + 2 * z) % 32,
        dir2=(3 * x + z) % 32,
        tex1=i % 1024,
        tex2=(1023 - i) % 1024,
    )


def build(
    samples=17,
    version=2,
    name="fixture_terrain",
    sources=("Tile/original_a.gtt", "Tile/original_b.gtt"),
    references=((0, 0), (1, 3), (0, 7)),
    lightmap=0,
    reserved=False,
    grass="Grass/original.n3pmesh",
    surface=height,
    headerless=False,
):
    """Serialize one GTD image in the reference layout, x-major MAPDATA.

    `surface(x, z)` gives the sample heights (default `height`). `headerless`
    leaves out the version and name, as the pre-1264 (1097) files do.
    A version of 0 or below writes no name length or name (`name` is unused),
    as the 1298 client reads none then (PQ-275)."""
    out = bytearray()
    if not headerless:
        out += struct.pack("<i", version)
        if version > 0:
            out += struct.pack("<i", len(name)) + name.encode("ascii")
    out += struct.pack("<i", samples)
    for x in range(samples):
        for z in range(samples):
            t = tile(x, z, samples)
            word = ko_terrain.pack_tile(
                t["full"], t["dir1"], t["dir2"], t["tex1"], t["tex2"]
            )
            if reserved:
                word |= 1 << 31
            out += struct.pack("<fI", surface(x, z), word)
    patches = (samples - 1) // ko_terrain.PATCH_TILE_SIZE
    for x in range(patches):
        for z in range(patches):
            out += struct.pack("<ff", 1.0 + x, 2.0 + z)
    out += bytes(samples * samples)  # grass attributes
    out += grass.encode("ascii").ljust(ko_terrain.MAX_PATH, b"\0")
    if references:
        out += struct.pack("<i", len(references))
        out += struct.pack("<i", len(sources))
        for s in sources:
            out += s.encode("ascii").ljust(ko_terrain.MAX_PATH, b"\0")
        for source, index in references:
            out += struct.pack("<hh", source, index)
    else:
        out += struct.pack("<i", 0)
    out += struct.pack("<i", lightmap)
    return bytes(out)


def expected_heights(samples):
    """The same surface in n3e's z-major order."""
    return [height(x, z) for z in range(samples) for x in range(samples)]
