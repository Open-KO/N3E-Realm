# Effects, sound and presentation events

Engine34/wire27 adds sequenced cosmetic events and cast/cooldown snapshots.
No presentation field authorizes gameplay. Game IDs, sounds, clips and attachments
belong to the package. Existing packages retain their prior protocol versions.

`PresentationEvent` carries sequence, tick, actor/target runtime IDs, kind, package
key, attack style/moving/hit/NPC flags and source/target positions. Kinds1–5 mean
consumed item, weapon strike, cast start, spell impact and cast cancellation;
kind 6 is a held ranged shot's landing (PQ-420) and kind 7 its release (PQ-439).
The server keeps at most128 events for40 ticks, filtered to the observer's3×3
interest cells. Consumables emit after the durable debit and never on exact retry.
Strikes emit once per authoritative strike tick, including misses for swing audio.
A newly connected client establishes the current cursor without replaying history;
subsequent snapshots deduplicate by sequence. Disconnect clears playback.

N3EF (or N3E2, N3E3 or N3E4, below) and N3AU are optional hashed package files, available from engine33. They
use little-endian u32/f32 and length-prefixed UTF-8 strings. Readers reject trailing
bytes, nonfinite numbers, invalid references and excessive counts. Imported bytes
remain ignored local outputs, never a normal build dependency.

N3EF contains RGBA8 textures (≤256, dimensions≤512, total≤4M pixels), named clips
(≤64), and effect bindings. Each clip has scale-dependence, sample rate≤60 and
≤600 frames, at most 20 s (10 s before PQ-341). Each frame has≤128 batches; each batch identifies triangle/quad
geometry, texture, blend factors1–10 and render flags. Records contain world-relative
position, UV/size/rotation, RGBA and, for quads, particle birth time; cumulative
geometry is capped at500K records. Bindings select event kind, package key,
attack variant, root/center/joint anchor and a list of clip keys. Runtime instances
are capped at64, retain bounded position history and permit stopped particles to
finish their tails. The Moradon cooker samples supported original effects at30Hz;
unsupported bundle motion, emitter orientation, part type and render flags fail.

### Appearance effects (N3E2)

N3E2 (PQ-211) is N3EF followed by effects on equipped appearance keys, at most
16. Each names an N3V1 key (at most once) and one skeleton joint every point is
rigid to, and carries, in the player's bind space: a texture frame sequence
(1–64 effect textures, a rate, and a start phase of (rand % steps) × step
seconds, at most 10 s), blend factors and render flags; up to four textured
triangle-list copies (at most 8,192 vertices in all), each with a frame offset
and a weight for a shared jitter offset (frac(t × rate) × 2 − 1) × amplitude
along a unit axis given by two points; a tail box (an origin and three edge
ends), the fraction range a tail point takes on each edge, up to four tail
links of a named clip, and an ARGB trace colour that nothing draws yet. Readers
reject a key past N3V1, a joint past the skeleton, an unknown frame texture or
tail clip, bad counts and trailing bytes. The client restarts each tail link's
clip every half clip (the old link stops emitting and its particles finish), so
the cook refuses a tail whose particles outlive half its clip; each link takes
one random box point per sample interval
([appearance](appearance.md#equipped-item-effects-n3e2-pq-211)). An effect with
no tail links names an empty tail clip. The key may be one an N3AT plug entry
draws (PQ-339: the 2233 weapon effect on a skeletal plug's FX mesh, the points
on the parent's hand joint as for a rigid plug; PQ-341: with its tail, a 20 s
clip of two 10 s links whose first half also holds triangle batches, the
tail's turning meshes at the link's newest point, which two keys may share).

### Equipment glow (N3E3)

N3E3 (PQ-315, D-184) is N3E2 whose effect list may be empty (0..16), followed
by up to 16 glow records, each on one N3V1 key (at most once): an emissive RGB
colour (0..1), a texture modulate of 1, 2 or 4, and a wave, steady (intensity 1;
rise, hold, fall and period all 0) or pulse (0 < rise <= hold <= fall <= period
<= 60 s: t / rise, then 1, then falling to 0 at fall, then 0, restarting at the
period). The client adds colour x intensity to the key's lighting, clamps at 1
and multiplies the texture product by the modulate, on one clock per actor
from its first draw, for every player it draws with render detail. On a key
that an N3AT plug entry draws (an empty appearance mesh) the same shade covers
the plug's whole model (PQ-337; 2233's `0042de90` / `00430f40` hand-off). Readers
reject a key past N3V1, a duplicate key, values out of range and trailing
bytes. The KO adapter writes the 2233 client's equipment glow, a 2233/2145
addition ([appearance](appearance.md#equipment-glow-n3e3-pq-315)). The client's
switch (`[Addition2233] EquipmentGlow`) and start line name the 2233 addition
whatever package carries the N3E3; a label supplied by the package is not
modelled.

### Tail particle distance rules (N3E4)

N3E4 (PQ-342, D-189) is N3E3 whose glow list may be empty (0..16), followed by
1–64 rules, each on one appearance effect's tail clip that no binding plays
(n3e's guard; a player effect that names the clip is decided as its own
one-link chain) and one particle batch material of it
(texture, blend factors and render flags, at most one rule per clip and
material, at least one such batch in the clip): a pool of 1–1024 particles and
a near and far distance (0 < x ≤ 1000 m). In the batches a rule covers, every
record is an emission candidate whose birth is a sample time, at most one per
birth sample in a frame. Each sample a link reaches, it takes the candidate
born then if the candidates it took that were alive at the previous sample
(with those the earlier link of its tail chain still draws: one live list per
tail copy) are at most the target and fewer than the pool, and it draws the
ones it took;
the target is the pool within `near` metres of the camera, else
trunc(pool × (far − d) / far) at the camera's distance d to the link's newest
tail point (negative past far, so none are taken while the taken ones live
on), and at a target of 0 nothing is drawn. Readers reject a clip that is no
tail clip or is bound, an unknown material, counts and distances out of range,
a duplicate rule, a candidate with no birth sample or two of one birth, and
trailing bytes. The KO adapter writes the 2233 particle tick's camera-distance
thinning (`00592900`), a 2233/2145 addition
([appearance](appearance.md#equipped-item-effects-n3e2-pq-211)).

### Alpha sort records (N3E5)

N3E5 (PQ-376, D-200) is N3E4 whose rule list may be empty (0..64), followed by
1–16 sort records, each on one appearance effect of the file (at most once): an
origin in bind space, rigid to the effect's joint, and a bias (0..1000 m). For
an effect with a record the client sorts each copy by the linear eye distance
to the origin moved by that copy's jitter, plus the bias, and each
camera-facing quad of its tail links on its own, by the linear eye distance to
the centroid of its first three corners (UV (0, 0), (1, 0), (1, 1)). Every
draw of the effect pass (player effects, tail links and quads, copies) is
sorted together far to near by linear eye distance; ties keep their order. An
effect without a record keeps each copy at its vertex centroid and each tail
link at its newest point. Readers reject a record on a key with no effect, a
duplicate, an origin or bias out of range and trailing bytes. The KO adapter
writes 1298's alpha-list keys (`00415910`, `004840b0`, sorted by `0043dd80`):
the plug origin and the FX mesh's y extent in mesh units, for every 1298
weapon effect and none of the 2233 ones
([appearance](appearance.md#equipped-item-effects-n3e2-pq-211)).

### Screen post-process (N3PF)

A package may carry `postprocess` (PQ-316, D-185), cooked by
`tools/assetc/postprocess.py` to `postprocess.bin`: `N3PF` and seven f32,
`threshold` (0..1), `bloom` (0..4), `exposure` (0..16), `saturation` (0..4),
`lift` (0..4), `adapt_rate` (0..100 per second) and `blur_variance` (above 0,
at most 16, in eighth-size texels). It needs the presentation assets and
engine 33. All three readers (cooker, client, server) refuse a missing or extra
field, a value out of range, a non-finite value and trailing bytes; the server
hashes it with the release and otherwise ignores it.

When the player sets `Option.ini [Addition2233] HDR=1` (default 0), the client
draws the world into an 8-bit scene target and, before the HUD, runs a fixed
chain over it (`client/render/postprocess.h`): a half-size bright pass that
keeps the 2×2 average whose luminance (0.299, 0.587, 0.114) is at least
`threshold`; a luminance reduction (geometric mean of each 2×2 block, then
3×3 means, maxima and minima down 81, 27, 9, 3 and 1 texels) read back
without waiting and adapted toward the measured values by at most
`adapt_rate` × frame time; a 4×4 downscale of the bright pass to an eighth;
a nine-tap blur across and then down whose normalised Gaussian weights are
multiplied by `bloom` in each pass; and a composite of scene plus bloom with
`k = Lm (1 + Lm / W²) / (1 + Lm) + lift`, `Lm = L / average × exposure`,
`W = maximum × (1 + bloom)`, then `saturation` around the result's luminance.
The average and maximum are floored at 1/255. Without the record, with the
option off or when the driver refuses a target, the scene draws straight to the
window as before. The chain is the 2233 client's CN3PostProcess, a 2233/2145
addition; the KO adapter fills the record for the zone from the player's own
2145 `Zones/hdr.n3pp` in the `--glow-2233` package only
(evidence).

N3AU contains48kHz mono signed16-bit PCM clips (≤128, ≤10s each, ≤60s total),
per-clip voice limits1–16, named bindings (≤1024) and attack sound-marker lists.
The runtime mixes at most64 voices to stereo, clamps output, and queues bounded
chunks through SDL3. Missing audio hardware leaves gameplay available. Weapon
swing audio follows authored sound markers; successful impact audio follows the
strike marker. UI sounds are used only when the original UIF names a sound.
Original local buttons currently have empty paths. Item/loot bindings remain
package-owned. No synthesized replacement click is added.

`N3A2` (PQ-013, D-144) is `N3AU` followed by a positional policy: `u32 listener`
(0 camera, 1 controlled character, camera while there is none), `f32
effect_distance`, `effect_distance_min`, `effect_distance_max` (all 0, or
1 ≤ min ≤ distance ≤ max ≤ 512), `cutoff` (5–512) and `reference` (0.1–32, below
the cut-off), in displayed metres; the cooker is `tools/assetc/audio_spatial.py`.
Effect-bundle sounds (`effect:` keys) start only while the camera eye is strictly
nearer than `effect_distance`, tested once in the audio chunk where the voice
begins, and then play with no cut-off; a sound that fails never starts. Other
positional voices fade over the last 5m before the listener cut-off. Gain is
full within `reference` and inverse distance beyond it; pan is equal-power
against the listener's right vector. A voice keeps the position it started at,
as KO's 3-D samples do. `N3AU` means camera listener, no start test and a 30m
cut-off for every positional voice. The KO package (`games/moradon/audio.json`)
carries KO's `Sound.Distance` default 48 with its 20–48 option range and the
player listener; `AudioSpatial::start_distance` clamps a player value to that
range, though no local option passes one yet (PQ-162).

Known fidelity gaps:30Hz sampled random FX, original mip/lighting details, exact
collision-point impacts and Miles provider mixing: KO's "Miles Fast 2D Positional
Audio" curves are not in the supplied inputs, so the gain and pan curves above
are generic. Character sounds (swing, struck, blow) keep the 30m cut-off; KO
loads a character's sounds under 16m of the player and releases them over 32m
(PQ-171), which
PQ-161 will implement. Cast animation survives late joining via
snapshot state; already-started cast effects are not replayed to a new observer.

PQ-423 (D-220): a ranged profile's
cast effect (`ranged-attack.bin` N3RF,
[combat animation](combat-animation.md#cast-effect-n3rf)) starts from the
held shot's kind-2 start event on the caster's joints, its records turned
with the caster's drawn facing, with its `effect:` sound, and ends at once
when the caster's strike fields stop showing the cast; the KO cook samples
such a clip (`self`) with its bundle velocity unused (move type -1) and, since
PQ-430, every FX mesh part's shape offset by the part's own file position, not
the shape file's (1298's part init `0048ea70` replaces the shape file's
position with the bundle's at the clone, 0, plus the part's), so the archery
arrow is drawn in the hand, as the rig shows
(PQ-429,
PQ-430);
since PQ-431 it refuses an FX mesh part whose x and z scale differ, which 1298
scales after the turn to the bundle direction
(evidence).
PQ-417 (D-222): a ranged profile's
flight (`ranged-attack.bin` N3RG, [combat animation](combat-animation.md#flight-n3rg))
launches at the held shot's kind-6 landing event, hit or miss, flies its clip
from the shooter's joint to the target's box (the pick box) at its speed,
turned to its pitched direction, ends where it enters the box and starts the
hit clip on the target; the KO cook samples such a clip (`flying`) in the
bundle's frame, its velocity the flight's speed. PQ-439
(D-223) adds kind 7, a held ranged
shot's release under a profile with a flight (a player actor, its target,
style and request sequence, both positions, no hit): the flight launches at
it, and the kind-6 landing comes when the arrow arrives, the 3-D distance
over the flight's speed later. The client refuses a kind 7 under any other
profile. PQ-445 (D-226): the archer's
own client launches its own shot's flight at its predicted release (the
shot's local start plus the stretched clip's blend and marker) and its kind 7
(matched by request sequence) confirms that flight instead of launching a
second; a predicted flight's hit waits for that event, and a shot the server
does not release ends its predicted flight. Observers launch at the event.
Target clips are drawn unturned; 1298 turns them about y toward the target
(PQ-432).
See binary evidence.

Engine35/wire28 adds `Entity.strike_sequence` (30) and
`PresentationEvent.request_sequence` (17). These are output-only copies of the
accepted ordinary Action sequence, assigned after successful admission and wear
commit. Skills/NPC attacks do not invent request identities. Respawn clears the
identity. `protocol/golden-strike.hex` independently pins both new fields.

The local client predicts only its ordinary swing and authored swing sound at
eligible send. It uses committed equipment style, current movement intent and a
cosmetic hash of actor/request identity, shared with observers once confirmed.
World snapshots remain immutable. No damage, hit flag, wear, resource change,
loot or reward is inferred from playback. Server validation remains unchanged.

A bounded 16-entry/10-second history matches result/snapshot/event ordering.
Unconfirmed attempts time out after two seconds; rejection, casting, death and
session/runtime replacement cancel speculative playback and tagged swing voices.
Stopping attack intent or changing target does not undo an already-sent strike.
Server confirmation preserves the original animation identity/start and suppresses
repeat swing audio. Confirmed impact FX/audio use that swing's strike marker;
when confirmation arrives after the marker, they start on receipt. Remote actors
use the authoritative strike tick and accepted request's cosmetic variant.
Authoritative style/moving corrections may change a clip without changing its
start. This is reconciliation, not client authority or exact legacy latency behavior.
