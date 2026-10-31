# Selected-actor presentation (N3TM)

Optional `presentation["target-marker.bin"]` adds package-owned terrain and
upright camera-facing meshes. It requires engine33 or later, melee and complete
player presentation; engine33/wire26 remain unchanged. Previous readers reject
unknown files. Assetc authenticates the file in release identity; the server
checks its hash and dependencies, while the native reader validates geometry.
There is no change to targeting authority, attacks, persistence or packets.

Little-endian layout:

- Four-byte magic `N3TM`; f32 diameter multiplier and height multiplier `(0,10]`,
  f32 ground lift `[0,1]`.
- Two radius/height f32 pairs (player, NPC), each value `(.001,100]`.
- u32 part count `[1,8]`; for each part: u32 mode (0 terrain,1 upright), f32[3]
  pivot bounded to±10, u32 width/height `[1,512]`, tightly packed RGBA8 pixels.
- u32 vertex count `[3,1024]`, then position/normal/UV f32[8] records bounded to
  ±10 with squared normal length greater than.5; u32 index count `[3,3072]`,
  divisible by three, followed by in-range u32 indices.

The file is bounded to8MiB; all floats must be finite; truncation/trailing bytes
are errors. Materials use additive ONE/ONE blending, ordinary depth test/write,
back-face culling and the engine's existing lighting/fog. Each part is a draw
of the frame's one far-to-near alpha pass, the effect pass, sorted with the
effect draws and the world's alpha parts by the linear eye distance to the
selected actor's position plus the part's pivot at the horizontal (X/Z) and
vertical (Y) scale: the part matrix's translation, as 1298 keys a shape part it
queues (`005c4e20` → `004442e0` → `00443090`, flushed at `005c4d98`; PQ-380,
D-214,
evidence).
A ground part's conformed vertices do not move its key. Ties keep their order.
Base textures generate mipmaps locally.

The marker follows the selected actor's displayed/interpolated position. A clear
selection, absent actor or disconnected session removes it. An actor still in
the snapshot remains eligible while dying, matching the binary's lookup without
its live-only flag. Existing local death/session handling clears selection.
Current input selects ordinary NPCs; adding player/object targeting is separate.

Horizontal scale is radius×diameter multiplier; vertical scale is height×height
multiplier, each times the selected actor's own drawn scale (PQ-296): a
templated NPC's scale / 100 (`Entity.scale`, PQ-272), 1 for a player or an
untemplated NPC. KO's symbol (`005c4e20`) scales by the selected actor's
radius and height getters (`0045a1d0`, `00459ff0`), which multiply the
character's joint-bound radius `+0x168` and box top `+0x17c` by its scale
`+0x90`, the NPC-in's `sSize` × 0.01 (binary; evidence).
A package whose untemplated NPC set is drawn at an instance scale cooks its
NPC pair at that size: the Moradon feature cook multiplies the worm
skeleton's pair by its `sSize` / 100 (1.2), as it does the nameplate style's
NPC height (D-181, D-182). Upright parts rotate about Y toward the camera. Ground parts sample
the highest triangle in the full-detail terrain surface, excluding object meshes.
With a streamed `N3W2` world (never resident whole) that surface is the
package's native collision heightfield (`N3C2`, which the cooker always writes
beside an N3W2 world) without its object triangles; the client refuses a target
marker on an N3W2 world whose collision has no heightfield (PQ-235, D-160).
As confirmed in005c4e20, sample X/Z spacing uses the **vertical** scale even though
the displayed footprint uses horizontal scale. Ground Y is sampled height plus
lift and scaled pivot Y. No drawable ground is emitted outside terrain. An `N3W1`
world uses its full-detail terrain parts; packages without world geometry use
their collision surface. The renderer keeps no KO IDs,
resource paths or historical class/race values.

Moradon imports the original two static quads and green textures from its local
reference assets. The importer rejects animated/collision/event shapes or material
variants outside the audited subset. Model dimensions come from frame-zero joint
bounds (`0041c300`, which poses the joints at the character's frame `+0x1dc`;
frame 0 is inference from KO's call order, the reused-character path not
traced): the radius is half the padded box's diagonal and
the height the padded box's top above the character's origin, as `00459ff0`
returns it, not the box's Y span (PQ-301; Tuarek 1.7985 m, the worm 0.5256 m
before its scale; evidence). Name labels can overlap the small arrow. Exact historical name/alpha layering,
lighting/fog/mip pixels, more model profiles (one pair per looks model,
PQ-300) and world object targets remain gaps. KO's other symbol
branch, for the scene object the left press picked (`+0xb14`, no actor
selected), takes that object's box corners `+0x11c`/`+0x128` through its
matrix `+0x54`; n3e has no object targets. Evidence.
