"""Offline reader for local KO GTD terrain. Original n3e implementation.

Structure follows the pinned OpenKO tree (`Client/WarFare/N3Terrain.cpp`
`CN3Terrain::Load` / `LoadTileInfo`, `N3TerrainDef.h`). Nothing here runs at
runtime: this converts a locally supplied file into package data. Reference
bytes are never bundled and no reference code is copied.

Two decode details are deliberately explicit rather than inherited:

* `MAPDATA` is a float height plus a 32-bit bitfield. The reference declares it
  as compiler bitfields; the bit ranges are unpacked by hand here so the result
  does not depend on a compiler's field layout.
* `CN3Terrain::GetHeight` indexes `m_pMapData[ix * mapSize + iz]`, which is
  x-major. n3e heightfields are z-major (`heights[z * width + x]`), so samples
  are transposed on import. The same function splits each quad by
  `(ix + iz) % 2`, so the diagonal alternates; see `alternating` in the cooker.
  Both are confirmed in the client binary at `FUN_0059d330`, whose parity test
  is `and edx, 0x80000001` at `0059d3a2`.
"""

from common import *

TILE_SIZE = 4.0  # N3TerrainDef.h: metres per tile
PATCH_TILE_SIZE = 8  # tiles per patch
MAX_VERSION = 2
MAX_NAME = 30
MAX_MAP = 4096  # (mapSize - 1) upper bound
MAX_PATH = 260
MAX_TILE_TEX = 4096
MAX_GTT = 1024
# n3e's own bounds. A world that fits N3W1 (and N3C1 collision) is limited to
# 129 samples per side, so `load` rejects a larger map by default rather than
# silently truncating it. The chunked bake (N3W2 world, N3WT textures, N3C2
# collision; PQ-234) passes CHUNKED_MAX_SAMPLES, the N3C2 heightfield bound
# (tools/assetc/main.py COLLISION_MAX_SAMPLES, PQ-215).
MAX_SUPPORTED_SAMPLES = 129
CHUNKED_MAX_SAMPLES = 513


class Reader:
    """Bounds-checked sequential reader over an in-memory buffer."""

    def __init__(self, data):
        self.data = data
        self.at = 0

    def take(self, n):
        if n < 0 or self.at + n > len(self.data):
            raise ValueError("GTD truncated")
        out = self.data[self.at : self.at + n]
        self.at += n
        return out

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def i16(self):
        return struct.unpack("<h", self.take(2))[0]

    def f32(self):
        v = struct.unpack("<f", self.take(4))[0]
        if not math.isfinite(v):
            raise ValueError("nonfinite GTD value")
        return v

    def text(self, n):
        raw = self.take(n)
        cut = raw.find(b"\0")
        if cut >= 0:
            raw = raw[:cut]
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError:
            raise ValueError("non-ASCII GTD name")


def unpack_tile(word):
    """Decode the MAPDATA bitfield explicitly (LSB first, as MSVC lays it out).

    bIsTileFull:1, Tex1Dir:5, Tex2Dir:5, Tex1Idx:10, Tex2Idx:10 occupies bits
    0..30. Bit 31 is not part of any field and carries no decoded meaning.
    Real local data does set it on a small number of records, so it is ignored
    for decoding and counted instead of rejected; the count is reported in the
    provenance manifest rather than hidden.
    """
    return {
        "full": bool(word & 1),
        "dir1": (word >> 1) & 0x1F,
        "dir2": (word >> 6) & 0x1F,
        "tex1": (word >> 11) & 0x3FF,
        "tex2": (word >> 21) & 0x3FF,
    }


def pack_tile(full, dir1, dir2, tex1, tex2):
    """Inverse of unpack_tile; used by the original fixtures."""
    for value, limit in [(dir1, 32), (dir2, 32), (tex1, 1024), (tex2, 1024)]:
        if not 0 <= value < limit:
            raise ValueError("tile field out of range")
    return (
        (1 if full else 0)
        | (dir1 << 1)
        | (dir2 << 6)
        | (tex1 << 11)
        | (tex2 << 21)
    )


# The 1453 client's zone files (PQ-214, local-asset) start with an int32 n, then
# n name bytes in an encoding n3e has not decoded, then a zero int32, then the
# map. n is the zone name's length (7 for moradon, 12 for moradon_xmas). n3e
# refuses that layout by name rather than misreading it.
ENCODED_HEADER = "encoded-name zone header (the 1453 layout) is not supported"
HAS_HEADER = "file starts with a version header, so it is not headerless (pre-1264)"


def encoded_name_header(data, legal):
    """True when `data` starts with the 1453 encoded-name header.

    `legal(n)` says whether the leading int32 is a valid value of the field the
    caller's layout expects there; such a value is never taken for the 1453
    header, so the check only ever replaces a refusal, never a valid read.
    """
    if len(data) < 8:
        return False
    n = struct.unpack_from("<i", data, 0)[0]
    if legal(n) or not 0 < n <= MAX_NAME or len(data) < 8 + n:
        return False
    return struct.unpack_from("<i", data, 4 + n)[0] == 0


def _legal_samples(n):
    return 0 < n and (n - 1) <= MAX_MAP and (n - 1) % PATCH_TILE_SIZE == 0


def _header(r, headerless=False):
    """The GTD's version and name, as (version, name).

    The pinned 1298 client reads an int32 version and, only when it is
    positive, an int32 name length and the name (`0059a010`: version read
    `0059a09c`, signed `> 0` test `0059a09e`-`0059a0a2` whose `JLE` goes to the
    map-size block `0059a243`, length `0059a118`, name `0059a176`), then the map
    size (`0059a262`) (binary). So a version-0 file has no name length: n3e
    reads the map size next and returns (0, "") (PQ-275). The client leaves its
    name field `+0x4c24` as it was in that case (binary: every access to it in
    this function lies in the skipped block `0059a0a8`-`0059a241`, and
    `00599930`, called at `0059a064`, uses no `+0x4c24`-`+0x4c2c` offset); n3e's
    empty name is its own value (inference that a fresh terrain's field is
    empty). The client has no upper version bound and also skips the name for
    a negative version (binary); n3e refuses both, its own stricter bound. The
    1097 client's files have no such fields: the file starts with the map size
    (local-asset), and the 1298 client has no branch for that (it would take
    the map size for a version; inference). No headerless GTD n3e accepts
    starts with 0 (its sample count is 8k + 1), but the caller still says which
    layout it has, never the data: `headerless=True` reads the pre-1264 layout
    and returns (None, "").
    """
    if headerless:
        if encoded_name_header(r.data, _legal_samples):
            raise ValueError("GTD " + ENCODED_HEADER)
        if len(r.data) >= 4 and 0 <= struct.unpack_from("<i", r.data, 0)[0] <= MAX_VERSION:
            raise ValueError("GTD " + HAS_HEADER)
        return None, ""
    if encoded_name_header(r.data, lambda n: 0 <= n <= MAX_VERSION):
        raise ValueError("GTD " + ENCODED_HEADER)
    version = r.i32()
    if not 0 <= version <= MAX_VERSION:
        raise ValueError("GTD version")
    if version == 0:
        return 0, ""
    length = r.i32()
    if not 0 <= length <= MAX_NAME:
        raise ValueError("GTD name length")
    return version, (r.text(length) if length else "")


def header_name(path):
    """The GTD's internal name, without reading the map behind it.

    The client reads the same length-prefixed field into terrain `+0x4c24`
    (`0059a010`, `0059a10d`-`0059a1a0`) and `005a3110` compares it with the zone's
    Zones.tbl column 3 (`ko_zone.check_names`). Reading only the header lets that
    check run before the sample cap refuses a larger map.
    """
    return _header(Reader(read(pathlib.Path(path))))[1]


def header_samples(path, headerless=False):
    """The GTD's sample count, without reading the map behind it (PQ-234).

    The client reads it after the name into its map size at `+0x40c4`
    (`0059a010`) and sizes MAPDATA (`size * size * 8` bytes) and the patch count
    (`+0x40c8`, `(size - 1) / 8`) from it; the bake chooses N3W1 or N3W2 by it.
    `headerless` is as for `load`.
    """
    r = Reader(read(pathlib.Path(path)))
    _header(r, headerless)
    samples = r.i32()
    if samples <= 0 or (samples - 1) > MAX_MAP or (samples - 1) % PATCH_TILE_SIZE:
        raise ValueError("GTD map size")
    return samples


def load(path, max_samples=MAX_SUPPORTED_SAMPLES, headerless=False):
    """Read one GTD file into a bounded, portable dictionary.

    `max_samples` is MAX_SUPPORTED_SAMPLES unless the caller bakes the chunked
    world (CHUNKED_MAX_SAMPLES). `headerless=True` reads the pre-1264 (1097)
    layout, which has no version or name before the map size; the result's
    `version` is then None and its `name` empty. The flag is never guessed from
    the data (`_header`).

    Parsing continues through the deprecated lightmap count, whose value must be
    zero. Reaching that field with the expected value confirms every preceding
    offset, so a misparsed record cannot pass silently.
    """
    data = read(pathlib.Path(path))
    r = Reader(data)

    version, name = _header(r, headerless)

    samples = r.i32()
    if samples <= 0 or (samples - 1) > MAX_MAP:
        raise ValueError("GTD map size")
    if (samples - 1) % PATCH_TILE_SIZE:
        raise ValueError("GTD map size is not a whole number of patches")
    if max_samples not in (MAX_SUPPORTED_SAMPLES, CHUNKED_MAX_SAMPLES):
        raise ValueError("GTD sample bound")
    if samples > max_samples:
        raise ValueError(
            "GTD map exceeds the supported %d-sample heightfield" % max_samples
        )

    # MAPDATA is stored x-major; transpose into n3e's z-major layout.
    heights = [0.0] * (samples * samples)
    tiles = [None] * (samples * samples)
    unused_bit = 0
    for x in range(samples):
        for z in range(samples):
            height = r.f32()
            word = struct.unpack("<I", r.take(4))[0]
            unused_bit += word >> 31
            heights[z * samples + x] = height
            tiles[z * samples + x] = unpack_tile(word)

    patches = (samples - 1) // PATCH_TILE_SIZE
    patch = []
    for x in range(patches):
        for z in range(patches):
            patch.append({"x": x, "z": z, "middle_y": r.f32(), "radius": r.f32()})

    r.take(samples * samples)  # grass attribute byte per sample
    grass = r.text(MAX_PATH)  # grass mesh filename

    sources, references = [], []
    count_tex = r.i32()
    if count_tex:
        if not 0 < count_tex <= MAX_TILE_TEX:
            raise ValueError("GTD tile texture count")
        count_src = r.i32()
        if count_src:
            if not 0 < count_src <= MAX_GTT:
                raise ValueError("GTD GTT count")
            sources = [r.text(MAX_PATH) for _ in range(count_src)]
            for _ in range(count_tex):
                source, index = r.i16(), r.i16()
                if source < 0 or index < 0:
                    raise ValueError("GTD tile reference")
                if source >= count_src:
                    raise ValueError("GTD tile reference outside GTT table")
                references.append({"source": source, "tile": index})

    if r.i32() != 0:
        raise ValueError("GTD lightmap data is deprecated and must be absent")

    lo, hi = min(heights), max(heights)
    return {
        "version": version,
        "name": name,
        "samples": samples,
        "spacing": TILE_SIZE,
        "heights": heights,
        "tiles": tiles,
        "patches": patch,
        "grass": grass,
        "tile_sources": sources,
        "tile_references": references,
        "height_range": [lo, hi],
        "unused_bit_records": unused_bit,
        "parsed_bytes": r.at,
        "total_bytes": len(data),
    }


def provenance(path, parsed):
    """Reproducible manifest describing one imported terrain file."""
    return {
        "source": str(path),
        "sha256": digest(read(pathlib.Path(path))).hex(),
        "format": ("N3 GTD headerless (pre-1264)" if parsed["version"] is None
                   else "N3 GTD version %d" % parsed["version"]),
        "name": parsed["name"],
        "samples": parsed["samples"],
        "spacing": parsed["spacing"],
        "height_range": parsed["height_range"],
        "tile_sources": len(parsed["tile_sources"]),
        "tile_references": len(parsed["tile_references"]),
        "unused_bit_records": parsed["unused_bit_records"],
        "parsed_bytes": parsed["parsed_bytes"],
        "total_bytes": parsed["total_bytes"],
        "notes": [
            "Samples transposed from the reference x-major layout to z-major.",
            "Tile bitfields decoded by explicit bit range, not compiler layout.",
            "River, pond and colour map data are not parsed by this importer.",
            "Parsing verified alignment through the deprecated lightmap count.",
            "MAPDATA bit 31 belongs to no field; occurrences are counted, not decoded.",
        ],
    }
