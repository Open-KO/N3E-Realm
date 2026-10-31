# Whole-body animation presentation (N3A1 / N3A2 / N3A3)

KO-07 adds optional `animation` recipe metadata with engine 8. Wire remains 3
with life policy, otherwise 2; the complete player set requires existing movement
and melee support. No migration,
message, server tick, cooldown, damage or reward rule changes. Older releases
retain their existing presentation. All files and source recipe participate in
the release hash. C++ and Rust validate metadata, completeness and compatibility;
C++ additionally loads and validates visual structure, shared geometry/skeletons,
atlases and clip durations before rendering. Rust hashes visual payloads, as before.

`animation.bin` is little endian: `N3A1`, then exactly eleven 20-byte records,
or `N3A2`, then exactly seven player records with no NPC clip files. Recipe
`animation` accepts the corresponding list of eleven or seven records. A2
retains player blending on packages without NPC presentation; NPC entities, if
present, use the existing non-animated fallback. Other record counts, partial
clip sets and surplus NPC files fail closed. Older readers reject A2 by magic.
Engine/wire versions and simulation rules are unchanged.
Each record is `f32 duration_seconds`, `f32 entry_blend_seconds`, `u32 loop_blend`,
then two `f32 strike_marker_seconds`. No trailing bytes. Duration is .001..3600,
blend 0..2, loop flag 0/1. Each marker is -1 (absent/invalid source marker) or
0..duration. All floats must be finite. Attack/death must have loop flag zero.
Track times already include source clip FPS; no runtime rate multiplier is applied.
Duration must match the maximum track time within .001 seconds.

Record order and required N3S1 files:

| Index | File | Playback |
|---|---|---|
| 0–6 | `player-{idle,walk,attack,death,run,backward,ready}.bin` | loop except attack/death |
| 7–10 | `npc-{idle,walk,attack,death}.bin` | loop except attack/death |

Existing `hud.bin` remains required with the complete player set. The NPC `walk`
slot means generic locomotion; the local KO fixture uses its run clip. Each role
shares identical bind nodes, joints/inverse binds, vertices/weights, indices, scale
and texture atlas across its clips. NPC atlas must match `scene.bin` because it
uses the existing world draw batch. The format retains N3S1 weights/parts and
introduces no arbitrary graph, attachment or authoring format.

## Runtime state and time

Priority: authoritative zero HP → death; recent nonzero replicated strike tick →
attack; local movement intent or remote displacement → locomotion; selected local
target → ready; otherwise idle. Hit and miss both animate an accepted strike.
Rejected actions never invent a strike. The server remains the sole outcome owner.

Entry blends freeze the incoming clip at its first pose. The outgoing pose is
sampled at the transition instant; an interrupted blend captures its evaluated
pose, preserving continuity. Translation/scale use linear interpolation and
rotation shortest-arc quaternion slerp, before hierarchy composition and skinning.
For these blended packages, the local rendered position also retains its existing
spring while movement intent stops, matching camera settling instead of snapping
the actor forward by the remaining tracking lag. Simulation input stops normally;
idle begins immediately and position converges during its entry blend. Legacy
packages without animation metadata retain the earlier immediate visual stop.

After entry blending the new clip advances in seconds. Loops use bounded modulo;
optional loop blending interpolates the endpoint to the start during an added
blend interval. Attack plays once, then releases to locomotion/idle. A new strike
restarts an ongoing attack. Its origin accounts for replicated tick age (20 Hz),
so late snapshots do not add a whole extra attack duration.

Death interrupts attack and holds the last frame indefinitely; subsequent strike
changes while dead cannot restart it. First sight of an already dead instance,
including reconnect, holds the endpoint directly. Replacement IDs create fresh
controllers; session changes clear all controllers. Despawn removes their storage.
A long frame gap advances arithmetically without a catch-up loop; gaps over .5s
suppress marker pulses. Clock rollback resets the controller.

Markers expose at most two one-frame cosmetic bits per attack crossing. They do
not send network messages, authorize damage, delay HP updates, or trigger reward
operations. No FX/audio consumer is supplied in this phase. Missing/out-of-range
source markers remain explicit in provenance; no timing is fabricated for them.

## Reference adaptations

The reference supports upper/lower body splits, animation queues, freeze delays,
random attack variants and speed modifiers. The base subset is full-body, one selected
attack/death per role, fixed baked rates and no extra hold delay.
[N3A4](combat-animation.md) extends player ready/attack selection with equipment
profiles and multiple attack variants; layering and rate modifiers remain gaps. Attack source
loop-delay flags are retained in provenance but overridden by one-shot playback.
Interrupted blends start from the displayed pose rather than jumping back to a
single source frame. Bounded modulo handles arbitrarily long gaps, unlike the
reference's single-period subtraction. See the research/evidence.


## N3A3 rest presentation

Engine30/wire23 requires fourteen records with the same20-byte layout: player
indexes0–6 unchanged,7 sit-down,8 sit-idle,9 stand-up, then NPC idle/walk/attack/death
at10–13. New files are `player-sit-down.bin`, `player-sit-idle.bin` and
`player-stand-up.bin`. Indexes2,3,7,9,12,13 must not loop. Complete compatible
geometry/skeleton/texture sets and matching durations remain required. Earlier
versions retain their original record order. [Posture/recovery](rest.md).
