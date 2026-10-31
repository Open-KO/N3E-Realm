# Optional normal melee damage (N3D1)

An optional manifest `damage` object requires engine **5**. It adds hashed
`damage.bin`; engine 5 requires that file. Older releases remain supported and
use their existing fixed `gameplay.damage`/`npc_damage`. Camera, melee and movement
are independently optional; protocol remains 1 without N3G3 movement and 2 with
it. The producer and both readers reject incompatible releases before admission.
No database migration. This policy does not derive stats from equipment or level.

```json
"damage": {
  "model": "contested_melee_v1",
  "player": {"attack": 36, "defense": 20, "accuracy": 50, "evasion": 100},
  "npc": {"attack": 18, "defense": 40, "accuracy": 50, "evasion": 100}
}
```

These are synthetic laboratory values, not authenticated historical stat rows.
Engine modules contain no game IDs. The model selects a bounded arithmetic policy;
its coefficients/grade table are versioned semantics, not configurable scripts.

Binary layout: `N3D1`, little-endian u32 model `1`, then player and NPC stats, each
four u32 in order `attack`, `defense`, `accuracy`, `evasion`. Exactly 40 bytes.
Attack/defense: **0–10000**; accuracy/evasion: **1–10000**. Unknown keys/models,
booleans, fractions, extra/truncated bytes and out-of-range values are rejected.
Fixed-damage fields remain required/validated for legacy schema consistency but
are unused when this policy is enabled. Zero resource cost still requires melee.

## Arithmetic

Let `A` be attacker attack, `D` defender defense; `B = floor(A*200/(D+240))`.
Maximum B is 8333; no signed-short overflow or negative defense is supported.
Accuracy/evasion division rounds to binary32, then compares against the binary64
thresholds below, preserving the inspected reference's float-argument ABI.
Draw `H` in **1–10000**. Each row's inclusive endpoints split highest, successful,
ordinary and miss outcomes; the first applicable ratio row wins.

| Ratio at least | Highest through | Successful through | Ordinary through | Miss above |
|---|---:|---:|---:|---:|
| 5 | 3500 | 7500 | 9800 | 9800 |
| 3 | 2500 | 6000 | 9600 | 9600 |
| 2 | 2000 | 5000 | 9400 | 9400 |
| 1.25 | 1500 | 4000 | 9200 | 9200 |
| .8 | 1000 | 3000 | 9000 | 9000 |
| .5 | 800 | 2500 | 8000 | 8000 |
| .33 | 600 | 2000 | 7000 | 7000 |
| .2 | 400 | 1500 | 6000 | 6000 |
| otherwise | 200 | 1000 | 5000 | 5000 |

Miss does zero damage and draws no damage roll. On a hit draw `R` in **0–B**.
`c=.85000002384185791015625` and `v=.300000011920928955078125` are the exact
binary32 coefficients promoted to binary64. Bounded products and sums are exactly
representable in binary64, giving the inspected x87/truncation result here.

- Player → NPC: `trunc(c*B + v*R)` for all three successful grades.
- NPC → player: `trunc(c*B) + trunc(v*R)`; highest grade then multiplies by 3 and
  integer-divides by 2. Cap at `trunc(2.6*A)` (unreachable under current nonnegative
  defense bounds, retained as model semantics).

No minimum-one rule: a successful roll may cause zero damage. `hit 0` is distinct
from `miss 0`.

NPC templates (N3N3, [content/npc.md](npc.md#template-table-n3n3-engine-37--wire-30))
replace the NPC side with their own values, cooked from KO rows by PQ-252
(D-165): attack 0–10,000 (`sDamage`), defence, accuracy and evasion 0–32,767
(`sAc`, `sHitRate`, `sEvadeRate`). A 0 evasion makes the ratio +inf (the first
row) and a 0 accuracy makes it 0 (the last row); a NaN ratio takes the last row,
as the reference's `FCOM`/`SAHF`/`JC` chain does for an unordered compare (AI
`004235aa`, `00444164`). Attack 0 makes B = 0, so every grade deals 0, as the
reference returns 0 for B ≤ 0 (`0041f535`); n3e still reports such a strike as
`hit 0`, where the reference reports result 0 and changes no health
(`0041de51`). Supported maximum player/NPC damage is 9582/14373. Example B=10,
R=3 gives player 9, ordinary NPC 8 and highest NPC 12. This distinction is tested.
The existing highest NPC grade is part of normal attack resolution; no equipment,
critical skill, combo or additional action system is introduced.

Since PQ-422 (D-219) a ranged profile
may carry a type-2 skill hit ([N3RE](combat-animation.md#skill-hit-n3re)); a
player's strike on an NPC under it uses the reference's skill branch instead
(AI `0040d471` -> `00443a34`, HitType 0): the grade ratio is multiplied by
HitRate × 0.01f (rounded to f32), the base B' = trunc(AddDamage × 0.01f × B),
and a hit deals trunc(B' × 0.6f + R' × 0.89f + 0.99) for R' in 0..=B', plus
AddDamagePlus; a sum of 0 is a miss there (the reference applies nothing and
reports both alike). With KO's archery terms (100, 100, 0) and B = 25: B' = 24
(100 × 0.01f is just below 1), 15 to 36 against the basic 21 to 28.

## RNG, authority and presentation

Simulation owns one SplitMix64 stream, seeded once with 64 OS-random bits before
its loop. There is no client/package seed or runtime seed override. Tests inject
bounded rolls or a fixed seed through the same resolution API. A draw uses the
high 64 bits of `random_u64 * interval_size`: fixed work, no rejection loop,
probability error below 2^-64 per bucket. This is a reproducible gameplay PRNG,
not a cryptographic generator. Consecutive equal results are allowed. These are
intentional differences from the reference's 15-bit CRT/modulo/retry RNG; matching
historical sequences or exact historical distribution is not claimed.

Session/sequence/action/target, life/range, cooldown, resource and pending-reward
checks precede RNG. A valid attempt spends cost and cooldown on **hit or miss**;
rejected/duplicate/stale attempts never reroll damage. Animation has no damage
callback. NPCs use their existing server scheduler with the same policy stream.

`ActionResult.status` now permits `miss`, damage 0; `hit` carries rolled damage
(before overkill clamping). `Entity.strike_result` (tag 14, string hit/miss) and
`strike_damage` (tag 15, u32) accompany `strike_tick` for the latest attempted
strike. They are server-only additive snapshot fields; unset means no recorded
attempt. Old Protobuf readers ignore them; old engine readers reject engine-5
packages. This does not add a new request or weaken handshake/session checks.
Snapshots are latest state, not a guaranteed combat-event history. The owner HUD
shows its action result/amount; selected-target HUD shows that NPC's latest
outgoing result/amount (possibly against another player). Continuous melee treats
miss as a completed attempt and retains pacing.

Death, automatic respawn, last-lethal reward ownership and atomic inventory/XP
remain the existing Phase 3 behavior. KO-05 onward own later corrections.
Formula provenance and verification.
