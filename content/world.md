# Static world geometry (engine 12 / wire 6)

A package may carry one static **world asset**: the visible geometry of a whole
map, with its own texture atlas. It exists because `scene.bin` means something
else — `scene.bin` is the *instanced* model a package repeats per entity and per
editable decoration, and it is shared with NPC clips, so a map expressed through
it is neither drawn as the world nor free to bring its own atlas or budget.

Engine 12 retains wire 6 and builds on the [engine 11 editing
contract](editing.md); engine 1–11 packages are unaffected and render exactly as
before. A package that names a world asset must declare `engine_version: 12`, and
engine 12 requires one. The server verifies that pairing and hashes the bytes
into release identity, but never interprets them: this is client geometry.

## Package manifest

`package.json.world` names a package file holding the cooked asset, for example
`"world": "moradon.n3world"`. It is hashed as a dependency like any other input,
so changing one pixel changes release identity. The cooker copies it to
`world.bin` after checking its magic and size; it is a produced artifact, not a
hand-authored one.

## `N3W1`

```text
"N3W1"
u32 width, u32 height        # atlas, power of two, each <= 2048
u32 cell                     # atlas grid stride, >= 8, <= atlas
u32 pad                      # wrapped border per cell, 1 .. cell/4
u8  rgba[width * height * 4]
u32 vertex count             # <= 196608
  f32 x, y, z                # package coordinates, as for collision
  f32 nx, ny, nz             # non-zero; normalized on load
  f32 u, v                   # first layer, cell-local, may tile past 1
  f32 u2, v2                 # second layer
  f32 slot, slot2            # atlas cell each layer samples
u32 index count              # <= 589824, a multiple of three
  u32 index                  # < vertex count
```

The file may be up to 32 MiB. Every other cooked file keeps the 16 MiB bound;
this one is larger because a map-sized atlas and vertex buffer do not fit in it,
and the limit is fixed rather than open-ended. Trailing bytes are rejected.

The asset is never posed, never skinned and never animated: it has no nodes,
joints or tracks. A client uploads it once into its own buffers and texture and
draws it in one pass, so it costs no per-frame CPU regardless of size.

## The atlas grid

The atlas is a grid of `cell`-wide square slots. Each slot's outer `pad` texels
are the image's opposite edge, wrapped, so bilinear filtering at a seam blends
the last texel with the first exactly as `GL_REPEAT` would.

A vertex names the slot each layer samples and carries UVs that are local to that
slot. They may leave `[0, 1]`: the renderer repeats inside the slot. That is what
lets a wall keep its brick courses or a fence its palings. Wrapping UVs into a
baked atlas coordinate at cook time cannot do this — every triangle that crosses
a tile boundary is torn, since its corners wrap to opposite ends of the image.
Sampling uses gradients from the unwrapped UV, or the mip level collapses to the
coarsest one along every seam. The wrapped border is `pad` texels wide, so the
coarsest mip levels do bleed between neighbouring slots.

## Two texture layers

Each vertex carries two UV pairs and two slots. The renderer alpha-tests the
first layer and adds the second:

```text
a = sample(slot, uv);  discard if a.a < 0.5
colour = min(1, a.rgb + sample(slot2, uv2).rgb)
```

An alpha part (`N3L4` / `N3W3`, below) is not drawn in this pass. A part
with the cut-at-zero bit (`N3L5` / `N3W4`, below) is cut only where the
texture's 8-bit alpha is 0, and an unlit one takes no light.

Geometry with only one layer points its second slot at a transparent one. This is
what a tiled terrain needs: an importer that composes two tile textures per
surface quad would otherwise have to bake a separate atlas entry per
*combination*, and combinations outnumber textures by an order of magnitude. The
alpha test gives imported foliage and fences their cutouts in the same pass.

Geometry meant to be seen from both sides carries both faces as separate
triangles. The pass has one cull state, so a source format's per-material
double-sided flag has to be resolved when the asset is built.

## Heightfield diagonals

Scene metadata's `heightfield.diagonal` gains `"alternating-mirrored"` beside
`"fixed"` and `"alternating"`. It is the alternating split with the opposite
phase, for a heightfield whose grid mirrors one axis of the source it was
imported from: mirroring an axis inverts the quad-split parity as well as the
winding. Drawn geometry and the collision bake must agree on the choice, or the
surface a player sees is not the one they stand on.

## `N3W2`: a world in chunks

A world that does not fit `N3W1` can be written as `N3W2`
(D-159,
PQ-231). It keeps `N3W1`'s vertex layout, takes its textures from its own
asset (`world-textures.bin`, below) instead of an atlas, and holds the parts
that an `N3W1` world keeps in `world-lod.bin`, so it is paired with the
`exploration` policy and its manifest entry names no `lod` file. The world is a
square grid of chunks, each self-contained:

```text
"N3W2"
u32 texture count (1 .. 4096), the world-textures.bin count; every slot is below it
f32 grid origin x, z; f32 chunk size (1 .. 4096 m); u32 grid side (1 .. 64)
u32 terrain (0 or 1), then the N3L3 terrain policy when 1
u32 chunk count, then per chunk: u32 x, z; f32 box min[3], max[3]; u32 bytes
then each chunk: its vertices, its parents, its parts (N3L3 layout)
```

A chunk's indices, progressive vertex bases and parent indices are its own, and
its box holds every part sphere in it. Parts are N3L3's progressive (kind 1)
and terrain (kind 2) parts plus kind 0, plain distance levels. Terrain patches
keep their global patch coordinates and the terrain policy is in the header, so
how a patch's edges meet its neighbours does not depend on where chunks split.
`docs/implementation/CONTRACTS.md` ("N3W2 chunked world") has every bound. One
chunk may hold what one `N3W1` file may (196,608 vertices, 2,000,000 indices,
8192 parts); a whole world up to 4,194,304 vertices, 33,554,432 indices, 65,536
parts and 384 MiB, sized for a 2048 m zone.

`tools/assetc/world_chunks.py` writes it from what the `N3W1` and `N3L3` writers
already take, with the texture count in place of the atlas (vertices, parts,
parents, terrain policy): each part goes to
the chunk of its centre, a progressive part to its parent's and a terrain patch
to the chunk of its patch centre. The client gives each chunk its own buffers
and tests a chunk's box against the view before its parts; the box test never
hides a part the part's own test would draw. The server checks the magic, size
and pairing and hashes the bytes, nothing more.

### World textures (`world-textures.bin`)

An `N3W2` world's textures are their own release-hashed asset (PQ-233), named by
the manifest key `world_textures`, present exactly when the world is `N3W2`.
Each texture is an authored RGBA8 mip chain, as render detail carries them:
power-of-two sides up to 2048, each level half the one before, up to 12 levels,
no generated tail.

```text
"N3WT"
u32 texture count (1 .. 4096)
per texture: u32 level count (1 .. 12); per level u32 width, height, then
    width x height x 4 bytes
```

The client groups textures with the same top size and level count into one
array texture, as it groups render detail's textures, and splits a group into
several when it has more textures than one array holds (2048, or the GPU's
own limit if lower). Bounds, sized for a 2048 m KO zone (about 750 textures):
4096 textures, 384 MiB of decoded pixels, at most 8 arrays of 2048 layers. The
client refuses a set that needs more than 8 arrays on its GPU or a texture
larger than the GPU allows, with a message that names the limit. A world vertex
names a texture by its index; the client turns that into an array and layer
when the chunk is loaded. KO itself loads a zone's textures whole at load (its
colour-map grid, `0059eff0`), and so does the client: textures are not
streamed. The atlas is `N3W1`'s alone, and render detail's world textures
apply only to an `N3W1` world. `tools/assetc/world_textures.py` writes and
checks it; the cooker checks it as the client does and that its count is the
world's.

### Streaming

The client streams an `N3W2` world (PQ-232). At start it reads only the header
and chunk table (and the world textures, whole). A worker thread then reads and checks chunk bodies one at
a time as their boxes come within the view's reach (the far plane's corner
distance) plus 64 m of the camera; the render thread uploads at most four
finished chunks a frame and frees chunks beyond reach plus 128 m. Resident and
in-flight chunks together never exceed 1024 chunks or 256 MiB of chunk data,
whatever the map's size; a single chunk over 256 MiB is refused at start. If
more are in reach than fit, the nearest are kept up to the first that does not
fit, the rest are not drawn, and the client says so once. A chunk that fails its checks stops the client when it is
reached, as a bad package does, and none of it is drawn. Once the chunks in
reach are resident the picture is the same as with every chunk loaded. This is
an engine choice: KO loads a zone whole and bounds per-frame work instead (a
window of terrain patches re-pointed around the camera, `0059b890`; a grid of
object cells walked around it, `005b5680`). An `N3W1` world is loaded whole, as
before.

## Alpha parts: `N3L4` and `N3W3`

A part may be an **alpha part**
(D-201,
PQ-379): it is left out of the world pass and drawn blended in the frame's
one far-to-near alpha pass, the effect pass, at its place among the effect
draws. `world-lod.bin` `N3L4` is `N3L3` whose kind 1 parts may set flag bit 4
(16); `world.bin` `N3W3` is `N3W2` whose kind 0 and kind 1 parts may. After the
part's kind fields an alpha part carries:

```text
u32 source blend, destination blend   # 1 .. 10, Direct3D numbering, as effects.bin
u32 state                             # bit 0 (blend) set; else only 0x40 unlit,
                                      # 0x80 diffuse alpha, 0x100 no depth write,
                                      # 0x400 no depth test
f32 sort point[3]                     # finite, within 1e6
```

Fog and culling stay the part's flag bits 0 and 3. The pass sorts the part by
the linear eye distance to its sort point, together with every effect draw
(ties keep the effects first), and draws it with the world shader: its
factors, depth writes and tests unless its state turns them off, no light for
`0x40`, fragments cut where the texture's 8-bit alpha is 0, and the texture's
alpha to the blend. The level of detail is chosen in the world pass as for any
part. The writers (`ko_lod.serialize`, `world_chunks.serialize`) write the new
magic only when a part is an alpha part, so other worlds keep their bytes;
older readers refuse the magic, and the client refuses a record out of its
bounds, the flag on a terrain patch or in `N3L3` / `N3W2`. An `N3W1` world
without `world-lod.bin` has no parts and keeps the alpha test.

The KO bake gives every drawn part whose material has `RF_ALPHABLENDING` an
alpha record: its material's factors, its flags masked to the state bits, and
the part matrix's translation (the pivot through the placement) as the sort
point, as 1298 queues such a part (`00443090`). It refuses one that needs point
sampling (`0x10`) or clamped addressing (`0x200`); no local zone has one.

## Opaque part bits: `N3L5` and `N3W4`

A part that is not an alpha part may carry two more flag bits
(D-202,
PQ-382). `world-lod.bin` `N3L5` is `N3L4` whose kind 0 and kind 1 parts may set
them, and `world.bin` `N3W4` is `N3W3` whose kind 0 and kind 1 parts may:

```text
flag bit 5 (32)   cut at zero: fragments are cut only where the texture's
                  8-bit alpha is 0 (Direct3D's GREATER against reference 0),
                  not below one half
flag bit 6 (64)   unlit: the part's colour is its texture's, without light
```

Neither may be set on an alpha part (its record states both) or a terrain
patch (its flags stay exactly 2). The part is drawn in the world pass as
before. The writers choose the lowest magic that holds the parts (`N3L5` /
`N3W4` with either bit, else `N3L4` / `N3W3` with an alpha part, else `N3L3` /
`N3W2`), so other worlds keep their bytes; older readers refuse the magic.

The KO bake sets bit 5 on every drawn part whose material has render flag 1
clear, as 1298 draws such a part at once alpha-tested as its device set-up
leaves the test (`00443090`, `0043ade0`), and bit 6 on those with
`RF_NOTUSELIGHT` (`0x40`, `004432da`). Moradon key 210: 754 opaque parts, 18
of them unlit.

## Single-layer unlit vertices: `N3W5`

`world.bin` `N3W5` is `N3W4` whose vertices may set the second-layer slot to
-1
(D-203,
PQ-388): a **single-layer unlit vertex**. The fragment is the first layer's
texel, cut on its alpha as before, with no second layer added and no light;
fog still applies. Every other slot names a texture below the world's count,
and -1 in the first slot is refused. The writer chooses `N3W5` only when a
vertex carries -1, so every other world keeps its bytes; older readers refuse
the magic. `N3W1` cannot carry it (its reader refuses a negative slot): the
KO bake writes a map with such vertices chunked, with `n3w1_refused` "single-layer
unlit vertices need N3W5". The KO bake marks the near colour-map tiles below
that never take 1298's multiplying pass; only `karus2004` (key 10) has any.

A terrain patch keeps the one-half cut (PQ-383). 1298 draws terrain
(`0059cd90`, `005a2640`) without setting an alpha-test state, so its fragments
are tested as the device set-up leaves the test (GREATER against 0) on stage
0's texture: the tile, or the colour map for a tile without one. Every local
1298 and 1097 tile and colour-map texel has alpha 255, so the two cuts keep the
same fragments.

A near tile whose first index is not below the tile-texture count, or whose
full bit is clear, is drawn from its patch's colour map (PQ-384), as 1298's
patch render does (`005a2640`: tex1 at or above the count `+0x4188`, or the
full bit clear, takes the colour-map path at `005a29e1`). The KO cook gives
its first layer the colour-map slot of its 32-tile region (`0059b890`) with
the UVs the tick gives it (`005a0410`: (126 t + 1) / 128 at the near edge, the
far edge converted twice, as KO does), and its second layer the transparent
slot: that path draws no tex2. A tile at exactly the count keeps its
direction UVs, because the tick tests `count < tex1`. In 1298 stage 1 then
MODULATEs TEXTURE (COLORARG1, `005a2a46`) with a texture that `005a2a1e` sets
to null (it first sets terrain `+0x41e0`, the Direct3D texture of the
`Misc\Terrain_Base.bmp` object at `+0x4198`, which never reaches the draw).
Since PQ-388
(D-203)
n3e draws such a tile as the colour-map texel alone, without the light: its
four vertices are single-layer unlit vertices (`N3W5`, above). The DirectX 8.1
SDK's own help for `IDirect3DDevice8`, like Direct3D 9's documentation, says
that a stage whose COLORARG1 is TEXTURE with a null texture stops processing
at that stage and all after it, so stage 2's MODULATE of DIFFUSE (the vertex
light) is not applied. The 8.0 SDK help is silent, and 1298 was built against
the 8.0 SDK (PQ-389), so this is the documented Direct3D 8 rule applied to
1298 by inference, not a KO observation. It departs from wined3d (Wine 8.0
passes such a stage through and keeps stage 2's light), which the rig keeps,
so the rig draws these tiles lit. A Windows driver's output is open (PQ-390)
(approximation; PQ-386, PQ-389, PQ-388). Neither source gives black. A tile
sent there only by a clear full bit, with tex1 and tex2 both valid, also takes
1298's multiplying pass (`005a2acb`–`005a2b05` test `+0x4c20` and the two
indices, not the full bit), which multiplies it by the vertex light; n3e draws
no such pass, so it keeps that tile lit (the colour map times its light) and
marks unlit only the tiles that never take the pass (tex1 or tex2 not a tile
texture). No local tile has a clear full bit. The colour-map slots
stay after every tile and object slot, so the other slots keep their order.
Without a colour map (the tests' terrain-only expand) a tile keeps its tex1.
`karus2004` (key 10) has six such tiles at its east edge; no other cooked map
has any. They sample the colour map's white last column, so they now draw
white. With n3e's light they were white only where its shade reaches 1 (a
normal within about 40° of its light direction) and dimmer elsewhere.

## Texture sequences: `N3W6`

`world.bin` `N3W6` is `N3W5` whose kind 0 and kind 1 parts may set part flag
bit 7 (128)
(D-212,
PQ-394): a **texture sequence**. After the part's alpha record (if it has one)
it carries

```text
u32 frames          2..64
f32 fps             finite, 0 < fps <= 1000
u32 slot[frames]    each below the world's texture count
```

Frame k draws `slot[k]` in place of the first-layer slot of every vertex the
part draws; the second layer, the part bits and the alpha record are
unchanged. The writer requires every vertex the part names to carry frame 0's
slot, refuses the bit on a terrain patch, and chooses `N3W6` only when a part
sets it, so every other world keeps its bytes; older readers refuse the magic
and the bit. `N3W1` and the `N3L` files cannot carry it: the KO bake writes a
map with sequences chunked, with `n3w1_refused` "texture sequences need N3W6
(D-212)".

The client keeps each sequence part's index, 0 when its chunk is loaded. Each
frame in which its world pass draws the part (chunk resident, chunk box,
parent and part sphere in view) the index grows by the frame time × fps in
float32, and once it reaches the frame count it restarts at 0, the remainder
dropped; the part draws frame `trunc(index)`, in the world pass or, for an
alpha part, in the alpha pass. Both passes of a matched capture draw the same
frame. The frame time is the time between world passes, bounded to
(0.001, 1.0) s with 1/30 s outside. The test client can fix it
(`N3E_TEST_SEQUENCE_SECONDS`) and print every drawn sequence part's state per
frame (`N3E_TEST_SEQUENCE_LOG`, read by `tests/world_sequence_log.py`).

This is 1298's part rule (binary, `KnightOnLine.exe`): the part constructor
`00442490` sets the index `+0x124` to 0 (`004425d5`), the part load `00443440`
reads the fps into `+0xd8`, the part tick `004429b0` adds the frame time
`[006d3ab0]` × fps when the part has more than one texture and resets the
index to 0 at the count (`00442c65`–`00442cb2`), returning before the advance
when the part fails its distance or plane test, and the part render `00443090`
draws texture `ftol(index)`. The KO bake gives a sequence to every part it
places with more than one texture and an fps above 0: the frame textures in
file order, the file's fps (`ko_scene.object_geometry`; report
`sequence_parts`). Cooked today: the bind points' and warp gates' magic parts
(16 or 17 frames at 10 or 6 fps), the Moradon magic anvil's two fx parts (5
and 10 frames at 8 fps) and, since PQ-412
(D-213),
the cycling parts of the static shapes the bake now places because none of
their cycling parts Y-billboards or wobbles (`material_cycle`, report
`material_shapes`: waterfalls, fog, pond drops, a dungeon gate's fire, a
bridge). A part whose frame textures are not all present keeps
its first texture (`first_frame_parts`). Approximations: the advance follows
n3e's culling rather than 1298's part tests, a streamed chunk loaded again
restarts at 0, and the Karus magic parts' Y billboard (`0x8`) stays frozen.

## Terrain overlay maps: `world-overlay.bin` (`N3WO`)

A package with a world may name `world_overlay` in its manifest: maps blended
over the near terrain around the eye
(D-204, PQ-387). The cooker copies the file to `world-overlay.bin`
after checking it (`tools/assetc/world_overlay.py`) and refuses it without a
world and an exploration policy, or when its block grid does not cover the
world's terrain policy. The client checks the same and the server checks its
magic (`N3WO`) and size (at most 256 MiB of pixels), hashes it with the
release and otherwise ignores it. `world.bin` is unchanged by it, and a package
without one keeps its bytes.

The file holds the grid (`patch_tiles` tiles a terrain patch side, from the
terrain policy's origin, x along +x and z along −z; `block_tiles` a block
side), the `window` radius in patches around the eye's patch, the texel
layout of a block's map (`side` texels, `cell` texels a tile, `inset`), and
one authored RGBA8 mip chain per block that has a map, in block order. Right
after a terrain patch drawn at its near level whose patch lies within the
window of the eye's patch (the patch the terrain level of detail takes), the
client draws the patch's near level again with each fragment's block map at
u = ((tx mod B)·C + I + (C − 2I)·fx) / S and v = ((B − tz mod B)·C − I −
(C − 2I)·fz) / S (tile (tx, tz), fraction (fx, fz)), mirrored repeat and
trilinear, the UV gradient taken from the position so a tile seam keeps its
mip level. Colour is the texel times the terrain light, alpha the texel's,
blended source alpha over one minus source alpha with the depth test
less-or-equal; texel alpha 0 is dropped. Only the window's maps are on the
GPU: one array of (2·window + 1)² · (patch_tiles / block_tiles)² layers,
rewritten when the eye's patch changes.

The KO bake writes the zone's terrain light maps this way. 1298 ends each near
patch (`005a2640` at `005a2c62`) with an alpha-blended pass (SRCALPHA,
INVSRCALPHA, stage 0 MODULATE of TEXTURE and DIFFUSE). It draws one fan per
tile whose 4 × 4-tile block has a texture in the zone's `.tlt`, the file
`Zones.tbl` column 5 names (`0059ba90`, `0059c450`, looked up by `0059c720`,
loaded for the 3 × 3 patches around the eye's patch, `0059b6f0` / `0059b890`).
Each tile samples the 6 × 6 interior of its own 8-texel cell of that 32 × 32
texture (`005a0410`): `N3WO` patch 8, block 4, window 1, side 32, cell 8,
inset 1 (`tools/assetc/ko_light_maps.py`). The local light maps reach alpha
204. Most are black wherever their alpha is above 0, so they only darken:
`karus2004` and the Moradon maps are all black. In `elmo2004`, 251 of 4,062
maps also carry near-white or yellow texels (they light the ground around its
lamps). The cooked maps carry 530 (`Moradon_xmas`, the default Moradon), 519
(classic), 394 (1097 Moradon), 3,649 (key 10) and 4,062 (key 20); the 1097
homelands' files hold none and write no file. Approximations: the texel is
multiplied by n3e's terrain light where 1298 multiplies it by Direct3D's
vertex light with the terrain material (that lighting is on there is
inference); equal depth passes because 1298 never writes ZFUNC (Direct3D's
default LESSEQUAL) and n3e draws the same vertices again; a fragment on a tile
seam takes the tile its position falls in. The cook refuses a version other
than 0, a block index outside 0..1, a block named twice and a map that is not
32 × 32 or whose chain differs from the others; none occurs locally. The GTD's
own light-map block is a different thing: 1298 reads it and drops it
(`0059a010`). The importer refuses a non-zero count, which no local GTD has.

## Limits

One world asset per package. An `N3W2` world streams its chunks; a chunk
entering reach appears once it has loaded, so a camera faster than loading can
see distant chunks arrive. A target marker on an `N3W2` world follows the
package's native collision heightfield (`N3C2`, always cooked beside N3W2), not
the resident chunks (PQ-235, D-160; content/target-marker.md).
Culling
stops at chunk boxes and the parts within them, and level of detail is limited to
the variants cooked into them (per-part levels, progressive object meshes, terrain
patch variants). An `N3W1` world has one atlas, so the number of distinct
textures it may reference is bounded by how many fit in it (or by render
detail's world textures, which override it); an `N3W2` world references up to
4096 textures in its own asset, all resident from the start.

### The KO bake (PQ-234)

`ko_scene.bake_world` (called by `ko_bake.package`) writes `N3W1` (with `N3L3`
as `world-lod.bin`, `N3L4` since PQ-379 when a part alpha-blends, as Moradon's
1,931 do, and `N3L5` since PQ-382 when a part is opaque) for every KO map that fits it. A map above 129 samples a side, or one whose terrain and
objects overflow an `N3W1` or `N3L3` bound (vertices, indices, the 324-slot
atlas, the LOD budget), is written as `N3W2` (`N3W3` with alpha parts, `N3W4` with opaque part bits, `N3W5` with single-layer unlit vertices) in 128 m chunks with its textures
as `world-textures.bin` (each slot's authored mip chain at its native size:
tile, colour-map and object textures), no `world-lod.bin`, and collision as
`N3C2`. The terrain, LOD and object records are the same ones the `N3W1` bake
writes; the GTD is read up to 513 samples (the
`N3C2` bound). KO builds every map from the size in its GTD (`0059a010`, map
size `+0x40c4`, patch count `+0x40c8`; `005a0410` bounds tiles by size - 1;
`0059eff0` reads the `(patches / 4)²` colour-map grid). The local 2048 m
homelands (Zones.tbl keys 10 and 20) bake this way through `ko_bake.package`.

Since PQ-217 `tools/assetc/ko_bake.py KEY` cooks such a map end to end. Its
start comes from the zone's START_POSITION row in the operator's own export
of their reference database (`build/ko-completion/database-parity/START_POSITION.json`
or `--start-positions=PATH`; never committed; the provenance records the file's
SHA-256 and, since PQ-051, `start.row_sha256`, the digest of the read columns
spelled one way (`ko_start.row_digest`), which the release hashes in
`tests/ko_bake_pin.py` are pinned by: the release depends on the row's values,
not on how it was exported, D-161; zone = key / 10): the server
places a player at `start + rand(0, range)` on each axis (Ebenezer `004c6523`,
`00422261`), so each nation's area is the KO rectangle `[X, X + bRangeX] x
[Z, Z + bRangeZ]` (`tools/assetc/ko_start.py`). Each area is surveyed with the
engine's solver on a crop of the map (the triangles within 32 m of it, under the
walk check's 196,608-point bound; `ko_survey.survey_starts`), every area must
hold a point the engine moves away from and back to in all four directions, or
the bake stops, and the package starts at the zone's own nation's point
(`ko_start.PACKAGE_NATION`). A map above 129 samples is refused without the
export or without its row. Every zone but Moradon cooks under
its own key (`build/ko-zone-KEY`, `build/packages/ko-zone-KEY`) with its overview
map on the basic HUD (`N3HE`); Moradon's names, survey and pinned hashes are
unchanged, and `--features` / `--des` (Moradon's data) are refused for other
zones. Population and warps are PQ-219 and PQ-220.

Since PQ-218 the provenance's `start.walk` also records a walk target: lattice
points of the package nation's start area grown by 24 m (every 8 m), farthest
from the start first and at least 8 m from it, the first one the engine verifies open
(`ko_survey.verify`) and reaches from the start with its solver at the copied
demo rules' run speed and capsule (`ko_survey.route`), with the solver's end
point (`ko_survey.walk_target`; the walk stays 8 m inside the 32 m crop). The
bake stops when none of the first 24 is reachable. `tools/play-ko-zone karus` /
`elmorad` (`tools/ko_zone_session.py`) plays the package on a persistent stack of
its own, and `tests/homeland_live.py` walks a new character there and back
through the server (`make live-ko`).

### The 1097 homelands (PQ-274, D-170)

`tools/assetc/ko_bake.py 1` or `2 --client=1097` cooks the 1097 client's own
`karus_start` or `elmorad_start` from the player's unpacked 1097 install
(`build/ko-reference/installer-1097/client`, PQ-221). The install's manifest
must name the pinned installer, and the five files the zone uses (the table,
GTD, colour map, OPD and overview map) must match it.

- **Table.** The 1097 `Data/Zones.tbl` has no CSV export. `ko_tbl` decrypts and
  parses it as the 1298 client parses its own (`006113b0`, `0044f670`,
  `006264d0`, `006359b0`; binary for 1298). `ko_zone.select(..., layout="1097")`
  accepts only its 15 column types, the 1298 table's columns 1, 2, 4, 5, 6 and
  8-17. Columns 2, 3, 5 and 6 name the GTD, colour map, OPD and overview map
  (inferred: the packed 1097 exe cannot confirm it).
- **Zone files.** The keys are the zone ids (1, 2). The GTD and OPD must be
  headerless (PQ-222). Neither they nor the table carry a name, so there is no
  name check. There is no OPDEXT column.
- **Bake.** The headerless readers are threaded through `ko_collision.bake`,
  `ko_scene.bake_world` (N3W2, N3WT, N3C2) and `ko_survey.survey_starts`. A
  headed and a headerless copy of one map bake byte-identically.
- **Referenced files.** Before anything is written, `ko_scene.references`
  checks every GTT the GTD names and every mesh and part texture of every OPD
  shape. A missing file refuses the cook by name. A mesh n3e cannot read is
  listed by name in the provenance and skipped as for every map: El Morad's
  two castle meshes, refused as `KO normal` in 1264 and 1298 too.
- **Package.** The map, objects and overview map are the 1097 install's. The
  player, HUD and render detail are the 2004 client's (`assets/ko`,
  `character_assets`).
- **Corrections (PQ-290, D-180).** `ko_bake.CORRECTIONS_1097` names 1097 files
  that KO itself replaced by the 1264 install, each pinned by SHA-256 on both
  sides; a zone whose OPD names one reads the 2004 client's file instead
  (`ko_scene.object_files` substitutes) and records it in the provenance
  (`zone.corrections`), and a changed or missing file refuses the cook. One
  entry: `obj_ka_tree_bra_post.n3pmesh`, the trunk of `obj_ka_tree_brA` in
  `karus_start`, whose 1097 mesh is centred on its box under a pivot every OPD
  keeps at y 0.018 (the trunk sank 3.4 m below its crown). El Morad and the 1097
  Moradon name no corrected file.
- **Start.** The start comes from the operator's START_POSITION rows for zones
  1 and 2 (ZoneID = key, `ko_start.row(..., zone=)`), surveyed with the engine
  on the 1097 collision, failing closed, with the walk target as above. The rows
  are the 2004-era server's.
  - PQ-276 found a start source that is probably 2003-era (inference: ko-db
    states no provenance; its server maps carry the 1097 heights), and it
    differs. The public ko-db (secondary, local-asset) starts a new character
    at its zone's ZONE_INFO init point: KO 371,1573 by Breth's bind point and
    1637,418 by Piana's.
  - The 1298 binaries leave that position to the database (Aujard `00427e70`,
    `00424ac0`; binary). Game start keeps it while it lies inside the map and
    otherwise uses the nation's HOME point (`004970cb`; binary); the ko-db
    points lie inside the map (inference for this data).
  - Today's start lies 99.6 m and 38.0 m away. PQ-278 is to move the start to
    the ko-db point.

The packages are `build/packages/ko-1097-zone-1` and `-2`.
`tools/play-ko-zone karus-1097` / `elmorad-1097` plays them on Compose
projects `n3e-ko-1097-zone-1` / `-2` (ports 7797 / 7798), and `make live-ko`
walks them (`homeland_karus_1097_live`, `homeland_elmorad_1097_live`).

### The classic Moradon (PQ-223, D-171)

The pinned 1298 install ships a second Moradon, `Zones\moradon.*` (no Christmas
decoration), beside the `Zones\Moradon_xmas.*` its Zones.tbl key 210 names. The
1298 loader `005a3110` reads its files from the row, and the exe holds no zone
file string (binary). The inference is that the client reaches maps only
through a row, so it never loads this one; a path assembled at run time is not
ruled out. The 1264 client's own key 210 row names
it.

- **Row.** `ko_zone.select(CLIENT, 210, stem="Moradon")` rewrites key 210's row
  before resolving it (`ko_zone.restem`): column 3 becomes `Moradon`, and each
  column naming `Zones\Moradon_xmas.<ext>` names `Zones\Moradon.<ext>`. Every
  path column must have that form, or the rewrite is refused. The files, the
  `005a3110` name check (the files' internal names are `moradon`) and the
  provenance (`zone.variant`, with each rewritten column) follow the rewritten
  row. Less its column 7, that row is the 1264 client's own row 210, value for
  value (local-asset).
- **Bake.** `tools/assetc/ko_bake.py 210 --layout=classic [--features]`. The four
  selected files must have the pinned installer's SHA-256
  (`ko_bake.MORADON_LAYOUTS`), and every file the map refers to must be
  present (`ko_scene.references`: 69 GTT, 327 meshes, 184 textures). Otherwise
  the cook is refused by name. The map does not fit N3W1, so it cooks to N3W2
  with N3WT textures and N3C2 collision. Its overview map is `moradon.dxt`.
- **Feature data.** It is Moradon's, unchanged where the engine proves it on
  this ground: the START_POSITION zone 21 start (the same surveyed point, KO
  316,354), the two worm rows' spawn points, the services beside the start and
  the combat points. The demo route to the second worm area turns at (2, -24)
  instead of (4, -28) (`moradon_features.LAYOUT_ROUTES`), because the default
  leg is blocked on this map.

The packages are `build/packages/moradon-classic` (source `build/ko-moradon-classic`),
never `moradon`. `tools/play-moradon --layout classic` plays it on Compose
project `n3e-moradon-classic` (port 7799), and `make live-ko` walks it
(`moradon_classic_live`).

### The 2003 Moradon (PQ-224, D-172)

The player's 1097 installer (a 2003 Chinese Sohu client) carries the oldest
Moradon layout. Its exe is packed (no section names, entropy 7.9 to 8.0, no
zone file string; local-asset), so none of its loaders can be read; what it did
with these files is inferred from the 1298 client and the files themselves.

- **Row.** The 1097 `Data/Zones.tbl` key 21 names `Zones\Moradon.gtd`, `.tct`,
  `.opd` and `.dxt` (local-asset), read through PQ-274's
  `ko_zone.select(..., layout="1097")`. That its columns mean what the 1298
  columns 2, 4, 6 and 8 mean is PQ-274's inference. That key 21 is the zone 21
  of the 1298 server's START_POSITION and K_NPCPOS rows is inference too.
- **Bake.** `tools/assetc/ko_bake.py 21 --client=1097 [--features]`. Both zone
  files are read headerless (PQ-222), the table and the four files must match
  the pinned installer's manifest (`ko_bake.install_1097`), and every file the
  map names must be present in the 1097 install (`ko_scene.references`: 72 GTT,
  289 meshes, 184 textures). Otherwise the cook is refused by name. The
  terrain, objects, GTT files, meshes, textures and overview map are the 1097
  install's: 157 of those 545 files differ in content from the 2004 client's
  file of the same name (13 GTT, 144 meshes and textures; local-asset). The map
  cooks to N3W2 with N3WT textures and N3C2 collision.
- **Player and rules.** The player, HUD, keys, worm model, effects, skills and
  audio are the 2004 client's (`character_assets`), and so are the zone name
  rules: its own Moradon row, key 210 (`client_row`), which `0046ea90` reads for
  the runtime key (binary, 1298). No 1097 text is imported.
- **Feature data.** It is Moradon's where the engine proves it on this ground:
  the START_POSITION zone 21 start (the same surveyed point, KO 316,354), the two
  worm rows' spawn points, the services beside the start and the combat points.
  The demo route to the second worm area is the classic map's
  (`moradon_features.LAYOUT_ROUTES["1097"]`): the 1097 objects place the same
  `obj_el_trans_stone4` as the classic map, and the default leg is blocked
  beside it.

The packages are `build/packages/moradon-1097` (source `build/ko-moradon-1097`).
`tools/play-moradon --layout 1097` plays it on Compose project
`n3e-moradon-1097` (port 7801), and `make live-ko` walks it
(`moradon_1097_live`).
