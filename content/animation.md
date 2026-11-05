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

### Influence tables on the player path (N3SI, engine 43)

RQ-163 carries a KO skin vertex with more than four joint influences on the player
path, as PQ-283 (D-176) does for NPC looks models. KO draws a player with the same
character class as an NPC (source `src/Client/WarFare/PlayerBase.h`: `CPlayerBase`'s
`m_Chr` is a `CN3Chr`), whose skin load `004286f0` reads any number of influences and
whose CPU skinning `00419f00` sums every one with its weight as read (binary, 1298
`KnightOnLine.exe`, D-176's evidence). The Arch Tuarek's lower part
(`upc_ka_at_lower.n3cskins`) has 49 drawn vertices with five (local-asset,
`tests/ko_player_races.py`). This replaces D-176's rule that the player path refuses
such a vertex.

- `tools/assetc/ko_character.py` keeps every influence on the player path, as on the
  looks path (`JOINTS_0`/`WEIGHTS_0`, then `JOINTS_1`/`WEIGHTS_1` and on; at most 64).
- A player clip with a vertex whose further sets carry weight cooks as `N3SI`: N3S1
  with D-176's influence table between the vertices and the indices
  ([NPC influence tables](npc.md#influence-tables-n3si-n3sj-n3ni-n3mi-engine-40)). The
  player clips are `player-<state>.bin`, `combat-<i>.bin` and `player-skill-<i>.bin`.
  `ko_player` and `ko_skills` cook with `main.cook(..., influences=True)`; any other
  scene (`scene.bin`, `npc-<state>.bin`, the loot model) stays N3S1, and the plain
  cook still refuses further sets.
- The player clips share one mesh, so they are all N3S1 or all N3SI; the cooker
  refuses a mix. A package with N3SI player clips is engine 43 (wire 30). It must
  already be engine 38 or later; the cooker refuses it otherwise. A package without
  them cooks byte for byte as before.
- Both readers take engine 43. The client reads N3SI only for player clips and only
  at engine 43, checks the table as it checks a looks model's, and `Scene::skin` adds
  each further influence after the four slots, in order. The server only hashes the
  clips, as before.

The render-detail levels (`render-detail.bin`, cooked by `ko_detail`) and the 1298
appearance parts carry such vertices too since RQ-164: N3DI / N3DJ render detail,
engine 44 ([influence tables in render detail](appearance.md#influence-tables-in-render-detail-n3di--n3dj-engine-44-rq-164)).
The front end's models and parts carry them since RQ-165: N3SI / N3SJ records in
N3FE version 30, engine 45 ([front end](front-end.md#influence-tables-version-30-engine-45-rq-165)).
No package ships that race yet (Q102). Its 512 x 512 lower texture doubles its
atlas, so its 19 combat clips are 49,919,260 bytes, past the 32 MiB combat clip
budget the three readers held until RQ-166 raised it to 64 MiB
([clip byte budget](combat-animation.md#clip-byte-budget-rq-166)).

### Track-only player clips (N3ST, engine 46, RQ-188)

Every player clip above is a whole scene, and the client already requires the atlas,
skeleton and mesh to be the same in all of them (`Scene::compatible`), so all but the
first repeat them. The atlas is uncompressed, so it is most of every clip
([clip byte budget](combat-animation.md#clip-byte-budget-rq-166)). A package may store
them once, as the looks models already do (N3NM, [npc.md](npc.md)):

- The manifest opts in with top-level `"player_clips": "tracks"` (the only value). A
  manifest without the key cooks byte for byte as before, at its engine.
- `player-idle.bin`, the first player scene, stays a whole N3S1 / N3SI scene. Every
  other player clip (`player-<state>.bin`, `combat-<i>.bin`, `player-skill-<i>.bin`)
  cooks as `N3ST`: the magic, then N3S1's track list unchanged (u32 track count 0–384;
  per track u32 node, u32 path 0 translation / 1 rotation / 2 scale, u32 key count
  2–4096, per key f32 time and four f32 values), and no trailing bytes.
- The sources stay whole scenes (`ko_player`, `ko_skills`, any glTF cook). The cooker
  (`tools/assetc/player_clips.py`) refuses a source whose atlas, nodes, joints, mesh
  (with any influence table), instance scale or attachment node is not
  `player-idle.bin`'s byte for byte, and records each source's digest as before.
- A package with N3ST clips is engine 46 (wire 30). It must already be engine 38 or
  later; the cooker refuses it otherwise. It combines with N3SI (engine 43): the
  influence table is `player-idle.bin`'s.
- The client reads N3ST only from engine 46 and only for a player clip other than
  `player-idle.bin`; it takes everything but the tracks from `player-idle.bin` and
  bounds the tracks by its nodes, so the compatibility check holds by construction.
  The server only hashes the clips; the combat clip budget counts the files as
  shipped.

Measured on the pinned 1298 tree's races (local-asset, `tests/ko_player_races.py`
cooks; `player_clips.tracks_only` against each race's `player-idle.bin`): the Arch
Tuarek's 19 combat clips go from 49,919,260 bytes to 570,712, and Moradon's (Tuarek)
from 27,009,388 to 580,312, with all 31 of its player clips from 44,566,812 to
2,836,692; every one of those clips has `player-idle.bin`'s atlas and mesh byte for
byte. Runtime memory per clip is unchanged: the client still gives each clip its own
parsed copy of `player-idle.bin`'s atlas and mesh. So with N3ST the 64 MiB combat clip
budget no longer bounds that memory: up to 64 combat clips, each with a copy, come to
roughly 218 MB at the 1024 x 1024 atlas bound (64 x 3,403,796 bytes,
[clip byte budget](combat-animation.md#clip-byte-budget-rq-166)), until the client
shares one parse across the player clips (queued as `player-clips-share-parse`).

Moradon opts in (RQ-190): `games/moradon/features.json` carries the key, so every
`ko_bake.py --features` cook (the realm's package, the classic and 1097 Moradons, the
2233 glow and `--des` cooks) ships player-idle.bin whole, its other 30 player clips
as N3ST (about 41.7 MB less) and is engine 46, which every client must read before it
joins; `ko_bake` raises the engine as it does for the other opt-in formats. Its
plain cooks (engine 14) carry no feature set and ship their clips whole. The client
skins every clip to the same vertices as before (`tests/ko_bake_pin.py`, its pins
moved for it).

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
