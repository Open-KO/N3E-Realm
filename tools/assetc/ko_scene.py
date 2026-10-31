"""KX-02 visuals: expand a KO map into one static world asset (`N3W1`, or
`N3W2` with `N3WT` textures when the map does not fit N3W1; PQ-234).

The world asset is the package's visible geometry: the tiled terrain surface
plus every static object placement, in the same coordinates as the collision
bake, with one texture atlas. It is separate from `scene.bin`, which stays the
small instanced model a package repeats per entity, so a map does not have to
share an atlas with characters or fit an animated scene's budget.

Terrain follows the reference tile pipeline, confirmed in the client binary:

* `CN3TerrainPatch::Tick` (`FUN_005a0410`) unpacks MAPDATA as
  `full:1, dir1:5, dir2:5, tex1:10, tex2:10`, emits **four unshared vertices per
  4 m tile** at a 40-byte stride and takes each corner's UV from the direction
  tables at terrain `+0x41e8` (U) and `+0x4268` (V) in the permutation
  `[2, 0, 1, 3]`. It picks the quad's diagonal from `(x + z) & 0x80000001`, the
  same parity `CN3Terrain::GetHeight` (`FUN_0059d330`) uses, and falls back to
  the colour map when a tile is not full.
* `CN3TerrainPatch::Render` composes the two layers additively
  (`D3DTOP_ADD` over stage 1) when a tile has a second texture, and modulates a
  single layer by diffuse otherwise. The partial tiles are black where they
  contribute nothing, which is why they must be added rather than replaced.

So each terrain vertex carries two UV sets and the shader adds the two samples.
Object vertices point their second set at a transparent slot and are unaffected.

`CN3Terrain::GetNormal` (`FUN_0059add0`) shows the binary's terrain vertices
carry real per-sample normals from an array at `+0x40cc`, not the constant
`(0, 1, 0)` the published source writes. `ko_normals` reproduces binary
`0059a690` construction, including its parity and upright border rules.

A map that does not fit N3W1 (above 129 samples a side, or terrain and objects
past its vertex, index, atlas or N3L3 bounds) is expanded with `chunked=True`:
the same terrain, LOD and object records, with a `Slots` table in place of the
atlas, written by `world2_bytes` as N3W2 (`world_chunks`, PQ-231) whose textures
`world_textures_bytes` writes as N3WT (`world_textures`, PQ-233). Nothing in
that path depends on the map size: the client builds every map from the size in
its GTD (`0059a010` map size `+0x40c4`, patch count `+0x40c8`; `005a0410` bounds
tiles by size - 1; `0059eff0` reads `(patches * 32 / 128)^2` colour-map
textures).
"""

from common import *
import re

import ko
import ko_shapes
import ko_terrain
import ko_tiles
import ko_collision
import ko_lod
import ko_normals
import world_chunks
import world_textures
from ko_lod import WorldTooLarge

# World asset budget. These are the caps the client enforces for `world.bin`;
# they are deliberately larger than an animated scene's because a map is static,
# uploaded once and never skinned.
MAX_VERTICES = 196608
MAX_INDICES = 589824
MAX_UV = 1024.0  # how far a mesh may tile inside one atlas cell

ATLAS = 2048
CELL = 112          # padded cell stride: 18 cells per row, 324 slots
PAD = 4             # replicated border so filtering cannot cross a cell
INNER = CELL - 2 * PAD
PER_ROW = ATLAS // CELL
SLOTS = PER_ROW * PER_ROW
CLEAR = 0           # slot 0 is transparent black: the "no second layer" source
# N3W2 chunk side in metres: a 2048 m (513-sample) map is 16 x 16 chunks of
# 4 x 4 terrain patches (PQ-234).
CHUNK_SIZE = 128.0

# Reference tile UV direction tables (client `+0x41e8` / `+0x4268`), indexed
# [direction][LT, RT, LB, RB]. Only the low three bits of the 5-bit field
# select a row.
TILE_DIR_U = [
    [0.0, 1.0, 0.0, 1.0],  # up
    [0.0, 0.0, 1.0, 1.0],  # right
    [1.0, 0.0, 1.0, 0.0],  # left
    [1.0, 1.0, 0.0, 0.0],  # bottom
    [1.0, 0.0, 1.0, 0.0],  # up mirrored
    [0.0, 0.0, 1.0, 1.0],  # right mirrored
    [0.0, 1.0, 0.0, 1.0],  # left mirrored
    [1.0, 1.0, 0.0, 0.0],  # bottom mirrored
]
TILE_DIR_V = [
    [0.0, 0.0, 1.0, 1.0],
    [1.0, 0.0, 1.0, 0.0],
    [1.0, 1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 1.0],
    [0.0, 0.0, 1.0, 1.0],
    [0.0, 1.0, 0.0, 1.0],
    [1.0, 1.0, 0.0, 0.0],
    [1.0, 0.0, 1.0, 0.0],
]
# The patch builder reads the table entry for corner k as [2, 0, 1, 3][k] with
# corners ordered (x,z), (x,z+1), (x+1,z+1), (x+1,z).
DIR_PERMUTATION = [2, 0, 1, 3]


def _basename(path):
    """Last component of a reference path, which uses either separator."""
    return re.split(r"[\\/]", path)[-1].lower()


def object_files(assets, substitutes=None):
    """The zone's `Object` files by lower-case base name, as the bake looks them
    up, with `substitutes` ({name: path}) read in place of those names.

    `substitutes` is the caller's pinned file corrections (`ko_bake`'s
    `CORRECTIONS_1097`, PQ-290, D-180): a file of one install that KO itself
    replaced in a later one. Nothing here decides which files those are."""
    files = {f.name.lower(): f for f in (assets / "Object").iterdir() if f.is_file()}
    files.update({name.lower(): pathlib.Path(path) for name, path in (substitutes or {}).items()})
    return files


class Atlas:
    """Fixed-grid RGBA atlas. Slot 0 stays transparent for the empty layer."""

    draws = True

    def __init__(self):
        self.pixels = bytearray(ATLAS * ATLAS * 4)
        self.slots = {}
        self.next = 1  # slot 0 is the transparent source
        self.decoded = 0

    def _blit(self, slot, width, height, rgba):
        """Draw one texture into its cell, with a replicated border.

        The client samples texel centres, so the border is never sampled
        directly; it exists so a mip level averages this cell's own edge
        instead of its neighbour's.
        """
        cx, cy = (slot % PER_ROW) * CELL, (slot // PER_ROW) * CELL
        rows = []
        for y in range(INNER):
            sy = min(height - 1, y * height // INNER)
            row = bytearray(INNER * 4)
            for x in range(INNER):
                sx = min(width - 1, x * width // INNER)
                at = (sy * width + sx) * 4
                row[x * 4:x * 4 + 4] = rgba[at:at + 4]
            rows.append(row)
        for y in range(CELL):
            row = rows[min(INNER - 1, max(0, y - PAD))]
            line = bytearray(CELL * 4)
            for x in range(CELL):
                sx = min(INNER - 1, max(0, x - PAD))
                line[x * 4:x * 4 + 4] = row[sx * 4:sx * 4 + 4]
            at = ((cy + y) * ATLAS + cx) * 4
            self.pixels[at:at + CELL * 4] = line

    def add(self, key, decode):
        """Return the slot for `key`, decoding it on first use."""
        if key in self.slots:
            return self.slots[key]
        if self.next >= SLOTS:
            raise WorldTooLarge("world atlas overflow at %d slots" % SLOTS)
        slot = self.next
        self.next += 1
        width, height, rgba = decode()
        self._blit(slot, width, height, rgba)
        self.decoded += 1
        self.slots[key] = slot
        return slot


class Slots:
    """The texture table of an N3W2 world: `Atlas`'s keys and slot order, no
    pixels. Slot 0 is the transparent texture; `world_textures_bytes`
    writes every slot's native mip chain to N3WT."""

    draws = False

    def __init__(self):
        self.slots = {}
        self.next = 1
        self.decoded = 0

    def add(self, key, decode):
        if key not in self.slots:
            if self.next >= world_textures.MAX_TEXTURES:
                raise ValueError("world texture table overflow at %d" % world_textures.MAX_TEXTURES)
            self.slots[key] = self.next
            self.next += 1
        return self.slots[key]




def tile_loader(gtd, assets):
    """Resolve a tile-texture index to its GTT file and ordinal, and decode it.

    `CN3Terrain::LoadTileInfo` stores one `(source, ordinal)` pair per tile
    texture in file order; the index in MAPDATA is the position in that list.
    Two indices may name the same pair, so the atlas is keyed by the resolved
    `(file, ordinal)` and not by the index.
    """
    sources = gtd["tile_sources"]
    references = gtd["tile_references"]
    files = {f.name.lower(): f for f in (assets / "DTex").iterdir() if f.is_file()}

    def resolve(index):
        reference = references[index]
        name = _basename(sources[reference["source"]])
        path = files.get(name)
        if path is None:
            raise KeyError(name)
        ordinal = reference["tile"]
        return ("tile", name, ordinal), (
            lambda: ko_tiles.load_tiles(path, {ordinal}, INNER)[ordinal])

    return resolve


def terrain_geometry(gtd, height, atlas, resolve_tile, colour_tiles=None):
    """Four unshared vertices per tile, two UV layers, KO's alternating diagonal.

    The heightfield has already been mirrored along z by the bake, so n3e grid
    sample (x, z) is reference sample (x, samples - 1 - z) and the quad between
    rows z and z+1 is reference tile (x, samples - 2 - z). Mirroring one axis
    inverts both the winding and the diagonal parity, which is why the emitted
    triangles are reversed and the parity is taken on `x + z + 1`.

    PQ-384: `005a2640` draws a near tile from its patch's colour map when tex1
    is not below the tile-texture count `+0x4188` or its full bit is clear
    (`005a2825`, `005a2832` -> `005a29e1`), and draws no tex2 there. With a
    list in `colour_tiles`, such a tile's first layer takes the colour-map UVs
    `005a0410` gives it (`ko_lod.near_color_uv`; the tick tests tex1 above the
    count, so a tile at exactly the count keeps its direction UVs) and its
    second layer the transparent slot, and `(first vertex, colour-map region)`
    is appended: the caller points those four vertices at the region's slot
    once `ko_lod.terrain` has placed the colour map. Without a list (no colour
    map, only the tests' terrain-only expand) a tile keeps its tex1 and tex2
    whatever its full bit, and a tex1 that is not a tile texture keeps the
    transparent slot and is counted missing, as before PQ-384.

    PQ-388 (D-203): on that path stage 1 has COLORARG1 TEXTURE (`005a2a46`)
    and a null texture (`005a2a1e`), which the DirectX 8.1 SDK's text says
    stops processing there, so stage 2's MODULATE of DIFFUSE (the light) is
    not applied (applied to 1298, an 8.0-SDK build, by inference). Such a
    tile's vertices name `world_chunks.UNLIT_VERTEX` as their second slot,
    a single-layer unlit vertex, unless the tile takes the multiplying pass
    after the draw (`005a2acb`-`005a2b05`: tex1 and tex2 both tile textures,
    and terrain `+0x4c20` 0), which multiplies it by DIFFUSE again; such a
    tile (sent there only by a clear full bit) keeps the lit draw.
    """
    samples = height["width"]
    spacing = height["spacing"]
    ox, oy, oz = height["origin"]
    heights = height["heights"]
    tiles = [gtd["tiles"][(samples - 1 - z) * samples + x]
             for z in range(samples) for x in range(samples)]
    # The tile-texture count `+0x4188` (`0059b140` reads it from the GTD); n3e
    # keeps one reference per counted texture whenever the GTT count is not 0.
    references = len(gtd["tile_references"])

    normals = ko_normals.normals(height)
    vertices, indices = [], []
    missing = colour = blended = unlit = 0
    for z in range(samples - 1):
        for x in range(samples - 1):
            tile = tiles[(z + 1) * samples + x]  # reference tile (x, samples-2-z)
            tz = samples - 2 - z
            first = tile["tex1"]
            second = tile["tex2"]
            du, dv = TILE_DIR_U[tile["dir1"] & 7], TILE_DIR_V[tile["dir1"] & 7]
            eu, ev = TILE_DIR_U[tile["dir2"] & 7], TILE_DIR_V[tile["dir2"] & 7]
            uv1 = [(du[DIR_PERMUTATION[k]], dv[DIR_PERMUTATION[k]]) for k in range(4)]
            slot1 = slot2 = CLEAR
            single = False
            if colour_tiles is not None and (first >= references or not tile["full"]):
                # 005a2640's colour-map path (11c): no tile layer, no tex2.
                colour += 1
                colour_tiles.append((len(vertices), ko_lod.color_map_region(x, tz, samples - 1)))
                if first > references or not tile["full"]:
                    uv1 = ko_lod.near_color_uv(x, tz)
                # PQ-388 (D-203): the null stage-1 texture ends the cascade;
                # only the multiplying pass (both indices tile textures) would
                # light the tile again.
                if not (first < references and second < references):
                    single = True
                    unlit += 1
            else:
                if first >= references:
                    missing += 1
                else:
                    try:
                        slot1 = atlas.add(*resolve_tile(first))
                    except KeyError:
                        missing += 1
                if second < references:
                    try:
                        slot2 = atlas.add(*resolve_tile(second))
                        blended += 1
                    except KeyError:
                        missing += 1
            # Grid corners, in the reference's corner order.
            corners = [(x, z + 1), (x, z), (x + 1, z), (x + 1, z + 1)]
            base = len(vertices)
            for k, (gx, gz) in enumerate(corners):
                p = DIR_PERMUTATION[k]
                second = (eu[p], ev[p]) if slot2 else (0.5, 0.5)
                n = normals[gz * samples + gx]
                vertices.append([ox + gx * spacing,
                                 oy + heights[gz * samples + gx],
                                 oz + gz * spacing, n[0], n[1], n[2],
                                 uv1[k][0], uv1[k][1], second[0], second[1],
                                 float(slot1), world_chunks.UNLIT_VERTEX if single else float(slot2)])
            # corners[0..3] are grid A'=(x,z+1), B'=(x,z), C'=(x+1,z),
            # D'=(x+1,z+1). Reference parity 0 fans from (x, z+1); mirroring z
            # moves that parity onto odd (x + z) here, and reverses winding.
            if (x + z) % 2:
                indices += [base + 0, base + 2, base + 1,
                            base + 0, base + 3, base + 2]
            else:
                indices += [base + 1, base + 3, base + 2,
                            base + 1, base + 0, base + 3]
    return vertices, indices, {"tiles": (samples - 1) ** 2,
                               "tiles_blended": blended,
                               "tiles_colour_map": colour,
                               "tiles_unlit": unlit,
                               "tile_textures_missing": missing}


def object_geometry(opd_path, assets, atlas, half, chunks=None, parents=None, headerless=False, substitutes=None):
    """Every placement of a `ko_shapes.BAKED` class (the static shapes, the
    event shapes 1298 shows at load, PQ-392, the ones it shows while their
    object NPC is in, PQ-395, and the static shapes whose cycling parts do not
    billboard, `material_cycle`, PQ-412), expanded into the bake's coordinates. Every part
    draws its first texture. A part with more than one texture and an fps
    above 0 cycles them in 1298 (the part tick `004429b0` advances the index
    `+0x124` by frame time x fps and resets it to 0 at the count; the render
    `00443090` draws texture `ftol(index)`; PQ-394): in a chunked build its
    record carries that sequence, the frame textures in file order at the
    part's fps (`world_chunks.SEQUENCE`, N3W6, D-212), counted as
    `sequence_parts`. Among the baked classes only an `event_shown`,
    `event_npc_shown` or `material_cycle` shape has such a part (the last
    counted as `material_shapes`, D-213). A sequence part whose frame textures are not all
    present, or one in a build without LOD records, keeps its first texture as
    a static stand-in (D-205) and is counted as `first_frame_parts`; an N3W1
    build (an atlas) with one is refused with `WorldTooLarge`, so the bake
    writes it chunked.

    A part is drawn as the client draws it: `CN3Shape::Load` (`004445a0`) sets
    each part's matrix (part `+0x38`) to the identity translated by the pivot
    `CN3SPart::Load` (`00443440`) read into `+0x2c`, times the shape's matrix
    (`0041dda0`), and `CN3SPart::Render` (`00443090`) draws the mesh's own
    vertices under that matrix (`D3DTS_WORLD`, `00441bb0`); so a vertex lands at
    `((v + pivot) * scale) * rotation + position` (PQ-290)."""
    objects = object_files(assets, substitutes)
    shapes = ko_shapes.load_shapes(opd_path, headerless=headerless)["shapes"]
    meshes = {}
    vertices, indices = [], []
    placed = skipped = placeholder = untextured = two_sided = alpha = unlit = 0
    event_shapes = npc_shown = first_frame = sequences = material = 0
    for shape in shapes:
        kind = ko_shapes.classify(shape)
        if kind not in ko_shapes.BAKED:
            continue
        # The placeholder shape the bake closes with a barrier also carries a
        # sentinel transform; drawing it would span the float range.
        if any(abs(c) > ko_shapes.SENTINEL_LIMIT
               for c in list(shape["position"]) + list(shape["scale"])):
            placeholder += 1
            continue
        if kind == "event_shown":
            event_shapes += 1
        elif kind == "event_npc_shown":
            npc_shown += 1
        elif kind == "material_cycle":
            material += 1
        qx, qy, qz, qw = shape["rotation"]
        q = [-qx, -qy, qz, qw]  # reflecting z conjugates the rotation
        sx, sy, sz = shape["scale"]
        px, py, pz = shape["position"]
        origin = [px - half, py, half - pz]
        parent_points = []
        parent_index = len(parents) if parents is not None else 0
        shape_chunk_start = len(chunks) if chunks is not None else 0
        for part in shape["parts"]:
            key = _basename(part["mesh"]) if part["mesh"] else None
            if key and key not in meshes:
                try:
                    meshes[key] = ko.import_mesh(objects[key], 1.0, detail=chunks is not None)
                except (KeyError, ValueError):
                    meshes[key] = None
            mesh = meshes.get(key)
            if not mesh:
                skipped += 1
                continue
            ax, ay, az = part["pivot"]
            parent_points.extend([[v[0]+ax,v[1]+ay,v[2]-az] for v in mesh['vertices']])
            slot = CLEAR
            if part["textures"]:
                name = _basename(part["textures"][0])
                path = objects.get(name)
                if path is not None:
                    slot = atlas.add(("object", name),
                                     lambda p=path: ko_tiles.texture(read(p), INNER))
            if slot == CLEAR:
                untextured += 1
                skipped += 1
                continue
            ax, ay, az = part["pivot"]
            base = len(vertices)
            for v in mesh["vertices"]:
                local = [(v[0] + ax) * sx, (v[1] + ay) * sy, (v[2] - az) * sz]
                wx, wy, wz = _rotate(q, local)
                n = _rotate(q, v[3:6])
                # The mesh's own UVs are kept, including the ones outside
                # [0, 1]: a brick wall or a fence tiles its texture, and
                # wrapping per vertex would tear every triangle that crosses a
                # tile boundary. The client repeats inside the atlas cell.
                # Objects have no second layer, so it points at the reserved
                # transparent slot and the shader's add contributes nothing.
                vertices.append([origin[0] + wx, origin[1] + wy, origin[2] + wz,
                                 n[0], n[1], n[2], v[6], v[7], 0.5, 0.5,
                                 float(slot), float(CLEAR)])
            triangles = [base + i for i in mesh["indices"]]
            indices.extend(triangles)
            if part["double_sided"]:
                # `CN3SPart::Render` (`FUN_00443090`) sets D3DCULL_NONE for a
                # material with RF_DOUBLESIDED, so these parts are meant to be
                # seen from behind. The world draw culls backfaces like any
                # other geometry, so the back face is emitted as its own
                # triangle. Normals are left alone, which is what the reference
                # does too: it disables culling without flipping them.
                for t in range(0, len(triangles), 3):
                    indices.extend(triangles[t:t + 3][::-1])
                two_sided += 1
            if chunks is not None:
                center, radius = ko_lod.bounds([v[:3] for v in mesh['vertices']])
                center = _rotate(q,[(center[0]+ax)*sx,(center[1]+ay)*sy,(center[2]-az)*sz])
                center = [a+b for a,b in zip(origin,center)]
                scale = max(sx,sy,sz)
                if scale <= 0: raise ValueError('nonpositive parent LOD scale')
                pm = mesh['progressive_data']
                record = dict(center=center,radius=radius*scale,scale=scale,
                              flags=int(bool(part['render_flags'] & 2)) | 4 | (8 if part['double_sided'] else 0),
                              levels=[(0.,[base+i for i in pm['stored']])],
                              kind=1,parent=parent_index,base=base,
                              max_vertices=len(mesh['vertices']),progressive=pm)
                if part['render_flags'] & ko_shapes.RF_ALPHABLENDING:
                    record['flags'] |= world_chunks.ALPHA
                    record['alpha'] = alpha_record(part, origin, q, (sx, sy, sz))
                    alpha += 1
                else:
                    # PQ-382 (D-202): `00443090` draws an opaque part at once
                    # (`0044327f`), alpha-tested as the device set-up leaves it
                    # (`0043ade0`: GREATER against reference 0), and turns
                    # lighting off for RF_NOTUSELIGHT (`004432da`).
                    record['flags'] |= world_chunks.CUT_ZERO
                    if part['render_flags'] & ko_shapes.RF_NOTUSELIGHT:
                        record['flags'] |= world_chunks.UNLIT
                        unlit += 1
                chunks.append(record)
            if len(part["textures"]) > 1 and part["texture_fps"] > 0:
                frames = None
                if chunks is not None:
                    if atlas.draws:
                        # D-212: only N3W6 carries a sequence; bake_world
                        # writes the map chunked.
                        raise WorldTooLarge("texture sequences need N3W6 (D-212)")
                    names = [_basename(t) for t in part["textures"]]
                    if all(n in objects for n in names):
                        frames = [atlas.add(("object", n), None) for n in names]
                if frames is None:
                    first_frame += 1
                else:
                    assert frames[0] == slot
                    chunks[-1]['flags'] |= world_chunks.SEQUENCE
                    chunks[-1]['sequence'] = dict(slots=frames, fps=part["texture_fps"])
                    sequences += 1
            placed += 1
        if parents is not None and len(chunks) > shape_chunk_start:
            pc, pr = ko_lod.bounds(parent_points)
            pc = [a+b for a,b in zip(origin,_rotate(q,[pc[0]*sx,pc[1]*sy,pc[2]*sz]))]
            # Binary 00443f40 uses 3*max(scale) for its position gate,
            # then 2*scale.y for the center sphere. 00444890 derives local bounds.
            if sy <= 0: raise ValueError('nonpositive parent visibility radius')
            parents.append([*origin,pr*max(sx,sy,sz)*3,*pc,pr*sy*2])
    return vertices, indices, {"placements": placed, "skipped_parts": skipped,
                               "placeholder_shapes": placeholder,
                               "untextured_parts": untextured,
                               "double_sided_parts": two_sided,
                               "alpha_parts": alpha,
                               "unlit_parts": unlit,
                               "event_shapes": event_shapes,
                               "npc_shown_shapes": npc_shown,
                               "material_shapes": material,
                               "first_frame_parts": first_frame,
                               "sequence_parts": sequences,
                               "meshes": len(meshes)}


# The flush `0043dd80` sets these states from an alpha primitive's flags; n3e's
# world pass samples with linear mips and wrap or mirror, so a part needing
# RF_POINTSAMPLING (0x10) or RF_UV_CLAMP (0x200) is refused (none in the local
# 1298 and 1097 zones). Fog (2) and culling (4) stay the part's flags.
ALPHA_REFUSED = 0x10 | 0x200


def alpha_record(part, origin, q, scale):
    """The alpha record of a part whose material has RF_ALPHABLENDING (PQ-379,
    D-201). `00443090` queues it into the frame alpha list keyed by the eye
    distance to its matrix's translation (`+0x68`), with the blend
    `+0xd0`/`+0xd4` and the flags `+0xcc`; `004445a0` sets that matrix to the
    pivot times the shape's (`0041dda0`), so the translation is where
    `object_geometry` puts the pivot."""
    flags = part["render_flags"]
    if flags & ALPHA_REFUSED:
        raise ValueError("world alpha part with render flags 0x%x: point sampling and clamped "
                         "addressing are not drawn" % flags)
    ax, ay, az = part["pivot"]
    sx, sy, sz = scale
    point = [a + b for a, b in zip(origin, _rotate(q, [ax * sx, ay * sy, -az * sz]))]
    return dict(source=part["source_blend"], destination=part["destination_blend"],
                state=flags & world_chunks.ALPHA_STATES, point=point)


def _rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return [vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx)]


def expand(gtd_path, opd_path, assets, heightfield, detail=False, color_map=None, chunked=False,
           headerless=False, substitutes=None):
    """Terrain plus placements in one vertex/index buffer and one atlas.

    `detail` needs `color_map`, the zone's TCT path (Zones.tbl column 4, `ko_zone`).
    `chunked` (with `detail`) builds the N3W2 world instead: a texture table in
    place of the atlas, no whole-world caps, maps up to 513 samples a side.
    `substitutes` is `object_files`'s.
    """
    if chunked and not detail:
        raise ValueError("a chunked world needs its LOD records (detail)")
    gtd = ko_terrain.load(gtd_path, ko_terrain.CHUNKED_MAX_SAMPLES if chunked
                          else ko_terrain.MAX_SUPPORTED_SAMPLES, headerless=headerless)
    atlas = Slots() if chunked else Atlas()
    # PQ-384: the tiles 005a2640 draws from the colour map, pointed at their
    # region's slot once ko_lod.terrain has placed the colour map (so every
    # other slot keeps its number).
    colour_tiles = [] if detail and color_map is not None else None
    terrain_v, terrain_i, terrain_report = terrain_geometry(
        gtd, heightfield, atlas, tile_loader(gtd, assets), colour_tiles)
    half = (heightfield["width"] - 1) * heightfield["spacing"] / 2.0
    chunks = [] if detail else None
    parents = []
    object_v, object_i, object_report = object_geometry(
        opd_path, assets, atlas, half, chunks, parents if detail else None, headerless, substitutes)

    vertices = terrain_v + object_v
    indices = terrain_i + [len(terrain_v) + i for i in object_i]
    if not chunked and (len(vertices) > MAX_VERTICES or len(indices) > MAX_INDICES):
        raise WorldTooLarge("world exceeds %d vertices / %d indices: %d / %d"
                         % (MAX_VERTICES, MAX_INDICES, len(vertices), len(indices)))
    for v in vertices:
        if any(abs(c) > MAX_UV for c in v[6:10]):
            raise ValueError("world UV beyond the %g-tile repeat bound" % MAX_UV)
    report = {
        "atlas": {"size": ATLAS, "cell": CELL, "slots": SLOTS,
                  "used": atlas.next, "decoded": atlas.decoded},
        "terrain": terrain_report,
        "objects": object_report,
        "terrain_vertices": len(terrain_v),
        "terrain_triangles": len(terrain_i) // 3,
        "vertices": len(vertices),
        "triangles": len(indices) // 3,
        "binary": {
            "patch_vertices": "CN3TerrainPatch::Tick FUN_005a0410",
            "tile_table": "CN3Terrain::LoadTileInfo FUN_0059b140",
            "texture_stride": "CN3Texture::SkipFileHandle FUN_0043f7e0",
            "height_diagonal": "CN3Terrain::GetHeight FUN_0059d330",
            "vertex_normals": "CN3Terrain::GetNormal FUN_0059add0",
        },
        "approximations": [
            "the two tile layers are added, matching D3DTOP_ADD, but without "
            "the reference's per-tile diffuse modulation",
            "RF_ALPHABLENDING parts are blended and sorted with the frame's other alpha draws "
            "only through world-lod.bin or N3W3 parts; a world without parts alpha-tests them",
            "RF_BOARD_Y parts are frozen in place; a static asset cannot "
            "billboard toward the camera",
            "a multi-texture part with an fps above 0 (the bind points' and warp gates' "
            "magic parts, PQ-392, D-205, the magic anvil's, D-206, and those of the static "
            "shapes whose cycling parts do not billboard, D-213) cycles its "
            "textures as 004429b0 does (index += frame time x fps, 0 at the count; "
            "00443090 draws ftol(index); N3W6 sequences, PQ-394, D-212), advanced "
            "while n3e's world pass draws it rather than under 1298's distance and "
            "plane tests, and from 0 again when its chunk is streamed in again; one "
            "whose frame textures are not all present draws its first texture",
            "an event shape 1298 shows only while its object NPC is in (event type 8, "
            "the magic anvil; 005cd620 at 005ce447, PQ-395, D-206) is drawn always, in "
            "that state, where 1298 hides it outside the nine 48 m server cells around "
            "it (00423be6, 00472ebf; inference)",
            "a fine-level tile without a tile texture (tex1 not below the count, "
            "or the full bit clear) draws its colour-map texel unlit: 1298 sets "
            "stage 1 COLORARG1 TEXTURE with a null texture there (005a2a46, "
            "005a2a1e), which the DirectX 8.1 SDK's text says ends the cascade "
            "before stage 2's light; applied to 1298, an 8.0-SDK build, by "
            "inference, and the Windows-driver output is open (PQ-388, PQ-390). "
            "A tile sent there only by a clear full bit, with both indices valid, "
            "keeps the light, which 1298's multiplying pass applies",
            "legacy world.bin embeds a 104-square atlas; N3D1 packages override "
            "it with native texture dimensions and authored mip chains",
        ],
    }
    terrain_lod = None
    if chunks is not None:
        for p in chunks:
            p['base'] += len(terrain_v)
            p['levels'] = [(d,[len(terrain_v)+i for i in ix]) for d,ix in p['levels']]
        if color_map is None: raise ValueError('world detail needs the zone colour map')
        terrain_chunks, terrain_lod = ko_lod.terrain(color_map,heightfield,atlas,vertices,terrain_i,CLEAR)
        chunks.extend(terrain_chunks)
        for base, region in colour_tiles:
            for vertex in terrain_v[base:base + 4]:
                vertex[10] = float(atlas.slots[('color-map', region)])
        if not chunked and len(vertices)>MAX_VERTICES: raise WorldTooLarge('world LOD vertices bound')
        report['atlas'].update(used=atlas.next,decoded=atlas.decoded)
        report['vertices']=len(vertices)
        report['color_map_sha256']=digest(read(pathlib.Path(color_map),ko_tiles.color_map_limit(
            ko_tiles.color_map_side((heightfield['width']-1)//8)**2))).hex()
    if chunked:
        # No atlas: the slot table's textures go to N3WT at their native size.
        report["atlas"] = None
        report["textures"] = {"slots": atlas.next, "format": "N3WT"}
        report["approximations"][-1] = ("N3W2 world textures are the native authored mip "
                                        "chains in N3WT; no atlas")
    return {"color_map": color_map, "chunks": chunks, "parents":parents,"terrain_lod":terrain_lod,
            "atlas": None if chunked else bytes(atlas.pixels), "texture_slots": atlas.slots,
            "texture_count": atlas.next, "vertices": vertices,
            "indices": indices, "report": report, "substitutes": dict(substitutes or {})}



def has_unlit_vertices(built):
    """Whether a vertex is a single-layer unlit vertex (D-203), which only the
    chunked N3W5 layout carries."""
    return any(v[11] == world_chunks.UNLIT_VERTEX for v in built["vertices"])


def world_bytes(built):
    """Serialise to N3W1: atlas grid, two-layer vertices, indices.

    The cell stride and padding are part of the asset because the client tiles
    inside a cell; it cannot do that without knowing the grid. N3W1 cannot
    carry a single-layer unlit vertex (D-203): `bake_world` writes such a
    world chunked.
    """
    if has_unlit_vertices(built):
        raise ValueError("N3W1 cannot carry single-layer unlit vertices (N3W5, D-203)")
    out = bytearray(b"N3W1" + u(ATLAS) + u(ATLAS) + u(CELL) + u(PAD)
                    + built["atlas"])
    out += u(len(built["vertices"]))
    out += b"".join(f(v) for v in built["vertices"])
    out += u(len(built["indices"])) + b"".join(u(i) for i in built["indices"])
    return bytes(out)


def lod_bytes(built):
    return ko_lod.serialize(built)


def world2_bytes(built, size=CHUNK_SIZE):
    """Serialise a chunked build to N3W2 (`world_chunks`): `size`-metre chunks
    aligned to multiples of `size`, the texture count of its slot table."""
    if built["atlas"] is not None:
        raise ValueError("N3W2 takes a chunked build")
    ox, oz, side = world_chunks.grid(built, size)
    return world_chunks.serialize(built["texture_count"], built["vertices"], built, (ox, oz), size, side)


# Slot 0's texture in N3WT and render detail: 4 x 4 transparent black.
CLEAR_TEXTURE = [(4, 4, bytes(64))]


def world_chains(assets_root,built):
    """Every world texture slot's native mip chain, slot 0 the transparent one:
    render detail's world subset for N3W1, N3WT for N3W2. (chains, sources)"""
    textures=[CLEAR_TEXTURE];sources={};cache={}
    objects=object_files(assets_root,built.get('substitutes'))
    tiles={p.name.lower():p for p in (assets_root/'DTex').iterdir() if p.is_file()}
    for key,slot in sorted(built['texture_slots'].items(),key=lambda p:p[1]):
        assert slot==len(textures)
        if key[0]=='tile':path=tiles[key[1]];ordinal=key[2]
        elif key[0]=='object':path=objects[key[1]];ordinal=0
        elif key[0]=='color-map':path=pathlib.Path(built['color_map']);ordinal=key[1]
        else:raise ValueError('unknown world texture role')
        if path not in cache:
            if key[0]=='color-map':
                # The zone's TCT (ko_zone column 4): exactly the grid ko_lod placed.
                count=sum(1 for k in built['texture_slots'] if k[0]=='color-map')
                data=read(path,ko_tiles.color_map_limit(count));cache[path]=ko_tiles.mip_chains(data,count=count)
            else:data=read(path);cache[path]=ko_tiles.mip_chains(data)
            sources[str(path)]=digest(data).hex()
        textures.append(cache[path][ordinal])
    return textures,sources


def world_textures_bytes(assets_root,built):
    """N3WT bytes of a chunked build's slot table (PQ-233, PQ-234), and a report."""
    chains,sources=world_chains(assets_root,built)
    if len(chains)!=built['texture_count']:raise ValueError('world texture table')
    data=world_textures.serialize(chains);count,banks,pixels=world_textures.check(data)
    return data,dict(textures=count,banks=banks,pixel_bytes=pixels,bytes=len(data),
                     native_mip_levels=sum(len(c) for c in chains),world_sources=sources)


def references(gtd_path, opd_path, assets, headerless=False, substitutes=None):
    """Every file a zone's GTD and OPD name, checked before a bake (PQ-274, D-170).

    The GTT files of the GTD's tile table (`tile_sources`, each under `DTex`),
    and the mesh and texture of every part of every OPD shape (under `Object`),
    looked up by base name ignoring case as the bake looks them up. Returns
    counts, the `missing` files by relative name, and `unreadable_meshes`: the
    present meshes n3e's mesh reader refuses, by name with the reason (the bake
    skips such a part, `object_geometry`). `substitutes` is `object_files`'s: a
    substituted name is looked up, and its mesh read, at the substitute."""
    gtd = ko_terrain.load(gtd_path, ko_terrain.CHUNKED_MAX_SAMPLES, headerless=headerless)
    shapes = ko_shapes.load_shapes(opd_path, headerless=headerless)["shapes"]
    tiles = {f.name.lower() for f in (assets / "DTex").iterdir() if f.is_file()}
    objects = object_files(assets, substitutes)
    gtt = sorted({_basename(s) for s in gtd["tile_sources"]})
    meshes, textures = set(), set()
    for shape in shapes:
        for part in shape["parts"]:
            if part["mesh"]:
                meshes.add(_basename(part["mesh"]))
            textures.update(_basename(t) for t in part["textures"] if t)
    missing = ["DTex/" + n for n in gtt if n not in tiles]
    missing += ["Object/" + n for n in sorted(meshes | textures) if n not in objects]
    unreadable = {}
    for name in sorted(meshes):
        if name in objects:
            try:
                ko.import_mesh(objects[name], 1.0, detail=True)
            except ValueError as error:
                unreadable[name] = str(error)
    return {"gtt": len(gtt), "meshes": len(meshes), "textures": len(textures), "shapes": len(shapes),
            "missing": missing, "unreadable_meshes": unreadable}


def bake_world(gtd_path, opd_path, assets, color_map, headerless=False, substitutes=None):
    """Collision and world presentation of one map (PQ-234).

    N3W1 (with N3L3) for every map that fits it, N3W2 with N3WT textures
    otherwise: the sample count decides first (above ko_terrain's 129-sample
    cap the GTD is read up to 513 samples and the package's collision cooks to
    N3C2), and a map within the cap whose terrain and objects overflow an
    N3W1 / N3L3 bound or have a texture sequence (`WorldTooLarge`; PQ-394,
    D-212: only N3W6 carries one), or that has single-layer unlit
    vertices only N3W5 carries (PQ-388, D-203), is rebuilt chunked, the refusal
    kept in the report. Returns heightfield, triangles, report, built, chunked,
    world (bytes), lod (N3L3 bytes or None) and textures (N3WT bytes or None).
    `headerless` reads the pre-1264 (1097) GTD and OPD (PQ-274); `substitutes`
    is `object_files`'s (PQ-290).
    """
    chunked = ko_terrain.header_samples(gtd_path, headerless) > ko_terrain.MAX_SUPPORTED_SAMPLES
    heightfield, triangles, report = ko_collision.bake(
        gtd_path, opd_path, ko_terrain.CHUNKED_MAX_SAMPLES if chunked else ko_terrain.MAX_SUPPORTED_SAMPLES,
        headerless)
    textures = None
    if not chunked:
        try:
            built = expand(gtd_path, opd_path, assets, heightfield, detail=True, color_map=color_map,
                           headerless=headerless, substitutes=substitutes)
            if has_unlit_vertices(built):
                # PQ-388 (D-203): only N3W5 carries the unlit colour-map tiles.
                report["n3w1_refused"] = "single-layer unlit vertices need N3W5"
                chunked = True
            else:
                world, lod = world_bytes(built), lod_bytes(built)
        except WorldTooLarge as error:
            report["n3w1_refused"] = str(error)
            chunked = True
    if chunked:
        built = expand(gtd_path, opd_path, assets, heightfield, detail=True, color_map=color_map, chunked=True,
                       headerless=headerless, substitutes=substitutes)
        world, lod = world2_bytes(built), None
        textures, report["world_textures"] = world_textures_bytes(assets, built)
    return dict(heightfield=heightfield, triangles=triangles, report=report, built=built, chunked=chunked,
                world=world, lod=lod, textures=textures)
