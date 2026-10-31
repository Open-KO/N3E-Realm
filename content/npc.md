# Optional normal hostile NPC policy (N3N1)

The manifest's optional `npc` object requires engine **6**. Wire stays 1 or 2
according to movement. `npc.bin` is hashed into the release; producer and both
readers reject malformed/unknown models, timer bounds, trailing data and incompatible
releases. Older packages retain legacy NPC behavior. No DB migration or spawn API.

The object has `model: "hostile_melee_v1"` plus exactly these integer fields.
N3N1 contains magic, little-endian u32 model=1, then these six u32 values in order:

| Field | Bounds, ticks at 20 Hz | Lab |
|---|---|---|
| scan_ticks | 1–1200 | 10 |
| acquire_ticks | 0–1200 | 10 |
| stuck_ticks | 1–1200 | 40 |
| chase_ticks | 1–12000 | 400 |
| return_ticks | 1–12000 | 200 |
| recovery_ticks | 1–1200 | 40 |

Existing gameplay fields own spawn/home, HP, speed, aggro/leash/attack range,
attack cooldown and damage. N3D1 is independent and optional. Timers use server ticks;
template numbers are synthetic, not recovered historical database rows.

| State | Work and transitions |
|---|---|
| idle | Scan at `scan_ticks`; choose farthest eligible actor inside inclusive 3D aggro range; equal distances choose lowest durable character ID. Start chase budget and acquisition delay. |
| chase | After acquisition delay, take at most one collision step/tick. Inclusive horizontal attack range enters attack. No movement for `stuck_ticks`, or `chase_ticks` outside attack range, enters return and suppresses that target. |
| attack | Attack only after server cooldown; miss still consumes cooldown. In-range ticks refresh pursuit deadline; out-of-range resumes chase. |
| return | Clear target; walk directly home, ignoring retaliation. Reaching within .08m or exhausting `return_ticks` snaps to validated home, fully heals and enters recover. |
| recover | Remain at home for `recovery_ticks`; then scan again. Incoming attacks still damage/kill, but do not interrupt recovery. |
| dead | Existing corpse/respawn timer, replacement runtime ID and pending reward handling. No KO-06 lifetime changes. |

Eligible actors are connected, nonfailed, living players in this zone within the
inclusive horizontal home leash. Both actor and NPC leash violations trigger return.
Target binding includes runtime ID: reconnect/respawn never silently inherits it.
The bounded realm contains at most 64 players and 32 NPCs. One O(players) scan,
one collision step and one actual attack maximum per NPC/tick; no path search/I/O.
A failed target stays suppressed until it leaves home acquisition range, dies,
disconnects or changes identity. Suppression has 64 slots. Hits do not bypass it.

Only accepted positive damage to a surviving NPC invokes retaliation, after normal
authentication, sequence, cooldown, cost and range checks. Same-target hits retain
state/timers. A different live attacker immediately becomes a candidate: server
roll 0–100 selects fresh player damage comparison (0–49), closer/equal distance
(50–79), fresh NPC damage comparison (80–94), or unconditional switch (95–100).
For forecast bands, evaluate old target then challenger using package damage/RNG;
equal rolls switch. Forecasts apply no damage. Without N3D1, equal template fixed
damage switches. Switching never resets attack cooldown or an active pursuit budget.
The next AI tick validates candidate identity/life/leash before acting.

Reference versus adaptations: binary farthest-first acquisition and reaction bands
are traced; equal-distance stable-ID ordering is ours because binary qsort equality
does not specify stable order. n3e RNG retains KO-04's deliberate difference. The
single hostile template has no factions, GM exemptions, invisibility, guards, pets,
social aggro or magic. Direct collision walking, fixed tick pacing, home leash,
full heal/reset and timeout teleport are explicit navigation/recovery adaptations.
No claim of historical return immunity or heal-on-arrival. Damage remains possible
during return/recovery. The reference has periodic HP recovery; it is not copied here.

## Reference policy (N3N2, engine 36 / wire 29)

`model: "reference_melee_v2"` keeps the six N3N1 timers and state machine and adds
package-selected, game-neutral switches. `npc.bin` is ASCII `N3N2`, u32 model=2, the six
timers, then u32 acquisition (0 aggressive, 1 passive), u32 flags `renew_on_hit`,
`return_heal`, `retaliate_returning` (0/1), u32 `return_speed_percent` (100–300),
`regen_interval_ticks` (0–12000, 0 disables), `regen_divisor` (1–1000),
`spawn_tries` (1–500), u32 slot count (1–2,048 since PQ-250), then per slot four i32 area offsets
(min x, min z, max x, max z; −256..256, min ≤ 0 ≤ max) and u32 `respawn_ticks`
(1–12000). No trailing bytes. The cooker, the Rust server and the C++ client all
validate the layout; the server also requires engine ≥ 36, one slot per gameplay spawn
point in order, a life policy whose corpse duration does not exceed any slot respawn
(the client checks the same), and a standable slot point. N3N1 packages are unchanged.

```json
"npc": {"model": "reference_melee_v2", "scan_ticks": 10, "acquire_ticks": 10,
  "stuck_ticks": 40, "chase_ticks": 200, "return_ticks": 200, "recovery_ticks": 20,
  "acquisition": "passive", "renew_on_hit": true, "return_heal": false,
  "retaliate_returning": true, "return_speed_percent": 200,
  "regen_interval_ticks": 200, "regen_divisor": 20, "spawn_tries": 500,
  "slots": [{"area": [-8, -8, 7, 8], "respawn_ticks": 600}]}
```

| Switch | Behavior |
|---|---|
| passive | Idle NPCs never scan. Only accepted positive damage acquires (the retaliation path). |
| `renew_on_hit` | Every accepted hit renews the pursuit budget, before the same-target test. |
| `return_speed_percent` | Return walks at this percentage of `npc_speed`, split into whole collision substeps no longer than the chase step. |
| `return_heal` | When false, arrival (or the timeout snap) does not restore health. |
| `retaliate_returning` | Damage during return or recovery re-acquires immediately instead of being ignored. |
| regeneration | Every `regen_interval_ticks`, a live NPC gains `npc_health / regen_divisor` (integer), clamped, in any state. The period starts at spawn and restarts even when nothing is healed. It is applied after the encounter-reset check, so it never replaces the runtime identity or clears contributions. |
| slots | Slot *i* belongs to gameplay spawn point *i*. Each spawn or respawn picks up to `spawn_tries` uniform integer offsets inside the area (spans narrower than two keep the low bound) and takes the first point where the actor capsule is standable (`movement::standable`); otherwise the slot point. That point becomes the NPC's home. |
| slot respawn | A slot NPC's respawn delay is its slot value, replacing `life.npc_respawn_ticks`. The editor offers no global respawn property for these packages; spawn-point edits translate the slot area. |

Adaptations kept from N3N1: direct collision walking at fixed tick pacing, the home
leash, the return timeout snap and the recovery state (used as stand time). Spawn
facing is not replicated (the entity has no heading field). Area rectangles are
integer package data; KO-derived values and their binary references are recorded in
games/moradon.

## Template table (N3N3, engine 37 / wire 30)

`model: "reference_templates_v3"` (PQ-249, D-162)
is N3N2 with a bounded table of NPC templates: the acquisition moves from the policy
into each template, and every slot names its template. KO keeps one record per
K_MONSTER or K_NPC row (AI `00437fb4`, `00438479`) and its spawn load copies the
row a spawn names into that NPC's own record (`0043893e`); n3e applies the slot's
template to the NPC's instance rules, so its AI, damage both ways, regeneration,
death and respawn, kill reward, party reward, item drop level, the operator
`record` line and editor spawns all read the template. Packages without N3N3 keep
the package-wide `npc_*` gameplay rules.

`npc.bin` is ASCII `N3N3`, u32 model=3, the six timers, the three N3N2 flags
(`renew_on_hit`, `return_heal`, `retaliate_returning`), the four N3N2 limits, u32
template count (1–256), the templates, u32 slot count (1–2,048, one per gameplay spawn
point), then per slot the N3N2 area and `respawn_ticks` and a u32 template index.
No trailing bytes. A template is:

| Field | Encoding and bounds | Replaces |
|---|---|---|
| `name` | string, package rule ID (`game:…`), unique in the table | gameplay `npc` (the entity name) |
| `looks` | string, package rule ID | — (wire `Entity.looks`) |
| `health` | u32 1–2,000,000 | `npc_health` (spawn, return heal, regeneration, operator record, wire `Entity.max_health`) |
| `level` | u32 1–255 | progression `npc_level` (solo, party and item-drop rules) |
| `xp` | u32 0–50,000,000 | progression `base_xp` (0 awards nothing) |
| `damage` | u32 0–100,000 | `npc_damage` (without N3D1) |
| `attack` | u32 0–10,000 | the N3D1 NPC side (with N3D1) |
| `defense`, `accuracy`, `evasion` | u32 0–32,767 | the N3D1 NPC side (with N3D1) |
| `attack_ticks` | u32 1–1,200 | `npc_cooldown_ticks` |
| `acquisition` | u32 0 aggressive, 1 passive | the N3N2 policy acquisition |
| `speed` | f32 0–12, m/s (0 never moves) | `npc_speed` (chase; return at `return_speed_percent` of it) |
| `attack_range` | f32 0.05–64 | `npc_range` |
| `search_range` | f32 0.05–64, ≤ `tracing_range` | `aggro_range` |
| `tracing_range` | f32 0.05–64 | `leash_range` (the home leash) |

PQ-251 (D-164)
lifted health, level, speed and the attack and search ranges to the bounds above
so they cover every row of the reference K_MONSTER and K_NPC tables (OpenKO
homelands: level 22–110, health up to 150,000, run speed up to 9 m/s); the layout
is unchanged, and an older reader refuses a package past its bounds. A chase or
return faster than 3 m/s takes ⌈speed / 3⌉ collision solver substeps of at most
0.15 m, and a chase stops at the substep that enters its attack range; up to
3 m/s nothing changed. An encounter's credit (damage dealt, which shares the kill
reward) is bounded at 100,000,000 instead of 100,000, so killing a template above
100,000 health settles (migration 022).

PQ-252 (D-165)
lifted the combat bounds the same way: `xp` and `damage` may be 0 (KO's camp
gates have `sDamage` 0, some templates `iExp` 0), `xp` reaches 50,000,000 (the
reference rows reach 39,438,375), and `defense`, `accuracy` and `evasion` reach
32,767 (KO's shorts; a 0 evasion takes the top N3D1 grade row and a 0 accuracy
the last, [content/damage.md](damage.md)). `attack` stays 0–10,000. A settlement
row carries at most 90,000,000 XP solo and 214,748,364 in a party (was
1,800,000 and 13,200,000), and `encounter_recipients.awarded_xp` is widened to
match (migration 023).

The cooker, the Rust server and the C++ client validate the layout; both readers
also require engine 37 and names and looks keys in the package namespace, and the
server keeps the N3N2 checks (slot per spawn point, corpse ≤ slot respawn,
standable slot points). A slot naming a missing template, a repeated name or a
search range beyond the tracing range fails closed. For a missing template this
matches KO: its spawn load logs the error and abandons the whole load (AI
`0043893e` returns 0 through `00439633`), and its caller `00436a34` then does not
start the AI server.

```json
"npc": {"model": "reference_templates_v3", "scan_ticks": 5, "acquire_ticks": 5,
  "stuck_ticks": 40, "chase_ticks": 400, "return_ticks": 200, "recovery_ticks": 20,
  "renew_on_hit": true, "return_heal": true, "retaliate_returning": true,
  "return_speed_percent": 100, "regen_interval_ticks": 0, "regen_divisor": 1,
  "spawn_tries": 1,
  "templates": [{"name": "demo:creature/drudge", "looks": "demo:looks/drudge",
    "acquisition": "passive", "health": 4, "level": 1, "xp": 10, "damage": 1,
    "attack": 4, "defense": 0, "accuracy": 100, "evasion": 1, "attack_ticks": 20,
    "speed": 3, "attack_range": 1, "search_range": 3, "tracing_range": 8}],
  "slots": [{"area": [0, 0, 0, 0], "respawn_ticks": 60, "template": "demo:creature/drudge"}]}
```

What stays as before: respawn is per slot, as KO reads it from the spawn row
(`RegTime`, AI `0041b89c`), not the template. The template carries one speed, the
run speed: KO's chase and path step takes the record's run speed (AI `0041d5d1`,
`0041d61b`) and its return twice that (`0042890f`, `0042891e`), as n3e's chase and
`return_speed_percent` do; the walk speed `bySpeed1` is read for the step speed
only by the wander routine (`00419fd9`, `00419fef`), which n3e does not have. The
walk speed joins the template with wander (PQ-070). The kill reward of a templated
NPC's encounter uses the template's level and XP in place of the progression
definition's; the settlement records them (an `N3T1` trailer: magic, u32 level,
u32 XP, after every other payload section) and is validated against them, while
the realm's durable reward definition stays the package's progression policy. An
entity spawned from a template carries `Entity.looks` (31) and `Entity.max_health`
(32); no other entity does. The client validates the table and uses `max_health`
for the target health bar, and since engine 38 draws the model its looks key
names ([below](#per-template-presentation-n3lk-engine-38--wire-30)).

## Per-template presentation (N3LK, engine 38 / wire 30)

PQ-253 (D-166)
gives each looks key its own model. KO keeps one `NPC_Looks.tbl` row per NPC:
NPC-in (client `005cd620`) looks the record's resource ID up in the looks table
(`005cdc58`) and hands the row to `0045dda0`, which stores it on the actor,
passes two of the row's files to resource managers that create an object only
when the name's lookup finds none (`0041d740`, `0041e540`) and rebuilds the
actor's box (`0041b000`). The row's byte `+0x14c` (column 36) keeps the NPC's
name at any range and past the camera limit (`00470baa`, `00459856`). Those
steps are binary, client. Inferences: the column meanings (row layout and the
installer's rows), and that the managers share one loaded object per file name
(objects are reference-counted and freed at 0, so a file can load again
later).

A package with N3N3 templates carries, at engine 38 (wire stays 30):

- `npc-looks.bin`, ASCII `N3LK`, u32 entry count (1–128), then per entry the
  key (string, package rule ID, unique), u32 flags (bit 0 `name_always`; no
  other bit) and four clip records for idle, walk, attack and death, each f32
  duration (0.001–3,600 s), f32 blend (0–2 s), u32 loop blend (0 or 1; never 1
  for attack or death) and two f32 markers (−1 or within the duration). No
  trailing bytes. The keys must be exactly the templates' looks keys.
- `npc-looks-<i>.bin` for entry *i*, ASCII `N3NM`: an N3S1 scene (atlas,
  nodes, joints, vertices, indices, instance scale, attachment) whose track list
  appears four times, once per clip in the table's order; each clip's longest
  track must last its record's duration (± 1 ms; the cooker and the client's
  model load check it, the server does not read models).

Bounds: 16 MiB per model, 96 MiB of atlas texels (width × height × 3) and
192 MiB of model files per package; both readers check them from the model
headers before parsing or uploading any model (`load_npc_looks`); the release
index has already read and hashed each file, each at most 16 MiB.

```json
"npc_looks": [{"key": "demo:looks/pillar", "name_always": false, "clips": [
  {"source": "pillar-idle.bin", "duration": 1.0, "blend": 0.2, "loop_blend": true, "markers": [-1, -1]},
  {"source": "pillar-walk.bin", "duration": 0.8, "blend": 0.2, "loop_blend": true, "markers": [-1, -1]},
  {"source": "pillar-attack.bin", "duration": 0.6, "blend": 0.1, "loop_blend": false, "markers": [0.3, -1]},
  {"source": "pillar-death.bin", "duration": 1.0, "blend": 0.1, "loop_blend": false, "markers": [-1, -1]}]}]
```

The cooker (`tools/assetc/npc_looks.py`) reads four N3S1 clips per entry that
must share atlas, skeleton and mesh, and stores them once with the four track
lists. The client parses every model once at start (after the release index
has read and hashed each file), keeps one texture per atlas
on the GPU and one mesh per looks, and draws an NPC with the entry its
`Entity.looks` names: its clips and timing, its pick boxes (standing, and in
the death clip's last frame once that has played), and its name flag, OR-ed
with the package-wide `names.npc_lifetime` flag; the operator info line follows
the name. A key the table lacks takes entry 0, as KO takes the table's first
node (`005cdc73`, `00473b10`; the lowest key, by inference); a valid package
cannot send one. Packages before engine 38
keep the package's single NPC scene (`npc-*.bin`).

### Render runs (N3SM, N3MM, engine 39)

PQ-265 (D-173)
lets a looks model draw its parts with their own render states, as KO's part
renderer does (the binary reading and its labels are in the
evidence).
A looks clip may be ASCII `N3SM` instead of `N3S1`: the same scene with an RGBA
atlas (width × height × 4 bytes) and, between the indices and the instance
scale, u32 run count (1–16) and per run u32 first index, u32 index count (a
positive multiple of 3), u32 flags (1 blend, 2 double-sided, 4 unlit; no
other bit), f32 alpha reference (0 ≤ r < 1: a fragment is drawn only where the
texel's 8-bit alpha is above r × 255) and u32 source and destination blend
factors (0 zero, 1 one, 2 source colour, 3 one minus source colour, 4 source
alpha, 5 one minus source alpha, 6 destination alpha, 7 one minus destination
alpha, 8 destination colour, 9 one minus destination colour; both 0 when the
run does not blend). The runs follow one another from index 0 and cover every
index. The cooker makes four N3SM clips of one entry an `N3MM` model: `N3NM`
with the RGBA atlas and the runs in the shared tail. A package with an `N3MM`
model is engine 39 (wire 30); one with `N3NM` models only stays engine 38.
The atlas budget counts 4 bytes a texel for `N3MM`. Both readers take `N3MM`
only at engine 39, and the client checks the runs.

The glTF source of such a clip carries one primitive per run over shared
attributes, each with a material extension `N3E_render_state`
(`alpha_reference`, `blend`: null or two factor names, `double_sided`, `lit`);
`gltf.cook` accepts it only for looks clips (`main.cook(...,
materials=True)`). The client draws an `N3MM` looks NPC by NPC, each NPC's runs
in order, each with its state, and draws other looks in one call as before.

### Influence tables (N3SI, N3SJ, N3NI, N3MI, engine 40)

PQ-283 (D-176)
lets a looks model's vertex have more than four joint influences, as KO's
client allows: its skin load reads any number and its CPU skinning sums every
one (the binary reading and its labels are in the
evidence).
A looks clip may be ASCII `N3SI` (from `N3S1`) or `N3SJ` (from `N3SM`): the
same scene with an influence table between the vertices and the indices. The
table is u32 count (1 to the vertex count) of vertices with further
influences, then per vertex, in strictly increasing order, u32 vertex, u32 n
(1–60) and n pairs of u32 skin joint and f32 weight (above 0). A vertex's
four slots and further weights sum to 1. The cooker makes four `N3SI` clips
an `N3NI` model and four `N3SJ` clips an `N3MI` model (`N3NM` and `N3MM` with
the table in the shared tail). A package with such a model is engine 40 (wire
30); otherwise it stays engine 39 or 38, byte for byte. Both readers take
`N3NI` and `N3MI` only at engine 40; the atlas budget counts them as `N3NM`
(3 bytes a texel) and `N3MM` (4). The client checks the table (order, range,
counts, joints, weights, every vertex's sum) and its skinning adds each
further influence after the four slots, in order.

| Clip | Model | Atlas | Render runs | Influence table | Engine |
|---|---|---|---|---|---|
| `N3S1` | `N3NM` | RGB | no | no | 38 |
| `N3SM` | `N3MM` | RGBA | yes | no | 39 |
| `N3SI` | `N3NI` | RGB | no | yes | 40 |
| `N3SJ` | `N3MI` | RGBA | yes | yes | 40 |

The glTF source of such a clip carries `JOINTS_1`/`WEIGHTS_1` and on (at most
16 sets, numbered from 0 with no gap); a vertex's further influences are its
pairs in sets 1 and on with a weight above 0, in set order. `gltf.cook`
accepts more than one set only for looks clips (`main.cook(...,
materials=True)`); a glTF whose further sets carry no weight cooks as with
`JOINTS_0`/`WEIGHTS_0` alone.

### Drawn scale (N3N4, engine 41)

PQ-272 (D-179)
draws each NPC at its template's size, as KO's servers carry `sSize` to the
client (the binary reading and its labels are in the
evidence):
the AI spawn load copies template `+0x28` to the record's `+0x24`
(`00438c42`), the NPC info record sends it as its fourth short (`004221d5`),
Ebenezer stores it at NPC `+0x22` and writes it into every NPC-in record after
the looks key, the type byte and a u32 (`00479e7c`), and the client's NPC-in
multiplies it by 0.01 (`005cdd82`) and hands it three times to the
character's scale (`0041f800`), which puts it on the diagonal of the
character's matrix (`0043b650`); the character render passes that matrix to
device slot `+0x94` with 256 (`004197e0`; that this is the world transform is
inference: slot `+0x94` as Direct3D 8 `SetTransform`, 256 as `D3DTS_WORLD`),
and the actor pick tests the box with it (PQ-146; its
part-mesh tie-break is the D-138 correction, which n3e runs on the drawn,
scaled triangles). The name callback raises the name by the scale too
(`00459820`).

A template may carry `scale`, an integer percent 1–1000 (the reference rows
hold 20–600). A policy with any `scale` cooks `npc.bin` as ASCII `N3N4`, u32
model=4: N3N3 with a u32 scale after each template's `tracing_range` (100 for a
template without the key). Such a package is engine 41 and needs a looks
table; without any `scale` the policy stays N3N3, byte for byte. Both readers
take N3N4 only at engine 41, refuse N3N3 there, and refuse a scale outside
1–1000. The server sends the scale of a templated NPC as `Entity.scale` when it
is not 100 (0 otherwise); no rule reads it (KO's AI uses `sSize` only in the
radius, which the cook folds into `attack_range`). The client multiplies the
NPC's drawn vertices, its standing and death-pose pick boxes, its effect joint
positions and its name height (the nameplate style's NPC height and padding,
or the demo HUD's fixed 0.65 m label) by scale / 100.

Not carried: the scale's other client uses, KO's walk/run clip threshold
(`004647a0`, PQ-269) and its character LOD distance (`004196a0`); n3e has no
NPC LOD. The name height is the style's one NPC height times the scale, not
the model's own height (PQ-262). Since PQ-296 the target marker follows the
scale too: KO's symbol (`005c4e20`) sizes itself from the selected actor's
radius and height getters (`0045a1d0`, `00459ff0`), which multiply them by the
scale `+0x90` (binary), so the client multiplies the marker's NPC pair by
scale / 100 (D-182; the pair itself is the package's one NPC pair, PQ-300).

An untemplated package (N3N2) has no scale on the wire. Since PQ-288
(D-181)
the Moradon feature cook draws its one NPC, the worm, at its K_MONSTER `sSize`
(120 for row 750, committed in `games/moradon/ko-reference.json`) as package
data the readers already take: the four NPC clip scenes
(`npc-{idle,walk,attack,death}.bin`) carry `sSize` / 100 as their instance
scale, so the worm's vertices, effect joints and pick boxes are drawn at that
size, and the feature HUD's nameplate style takes the NPC height (the worm
skeleton's) times the same factor, so the name sits at h × s × 1.1 as
`00459820` places it. The worm's `Entity.scale` stays 0. Its pick box is padded
after the scale, where KO pads and then scales (0.10 m lower; PQ-297).

```json
"templates": [{"name": "demo:creature/giant", "looks": "demo:looks/pillar", "scale": 200, "...": "..."}]
```

### KO looks import (PQ-254)

`tools/assetc/ko_npc_looks.py` turns each looks key a zone's templates use
(`<game>:looks/<sPid>`) into one entry of the table above, from the operator's
own decoded `Data/NPC_Looks.tbl.csv` and the files it names (never committed;
outputs under `build/`)
(evidence,
D-167).
The row is built as the client builds the actor (client `KnightOnLine.exe`,
binary unless marked):

| Row column | Use (client address) |
|---|---|
| 16 (`+0xe4`), a `.n3chr` (local-asset) | when not empty, the character object loads it (`0045dda0`: slot `+8` of actor `+0x50`; that slot being the load is inference); its joint, clip table and parts are used |
| 3, 4 (`+0x14`, `+0x24`) | when column 16 is empty: the skeleton (`0041b260`) and clip table (`0041bd30`) |
| 5–10 (`+0x34` + 16 i) | NPC-in sets part i = 0–5 (`005cdfd5`–`005ce035`); a non-empty name replaces part i only below the character's part count (`0041b6d0`; ten on the column 3/4 path, `004554e0` → `0041b4d0(10)`; positions 0 and 1 also test actor `+0x278`, not traced for NPCs); an empty one leaves it (`0045cd90`, `004465e0`) |
| 11–15 | not read by either path |
| 17 (`+0xf4`) | passed to `0041cb80` when column 16 is empty (an effect plug, local-asset `.n3fxplug` names; the load is inference); not imported |
| 35 (`+0x148`) | 0: the NPC never turns (`0045dda0` clears `+0x45b`; `00457910`); not imported |
| 36 (`+0x14c`) | `name_always` (PQ-253) |

Clips: idle 0 (`0045bfe0`), walk 2 (KO's run clip, `0045a950`; n3e's NPCs
move only at chase or return speed; KO walks on clip 1 below a size-dependent
speed, `004647a0`), attack 4 (`0045bf70`; KO alternates 4 and 5) and death 10
(`005cf620` → `0045acc0`). Entries are ordered by resource ID, so entry 0 is
the lowest (KO's fallback node, by inference). A row converts or fails closed
with the file and reason (no row, a missing or unreadable file, no parts, a
clip the table lacks, a format the converter refuses); `cook` refuses a zone
with any failed key. `python3 tools/assetc/ko_npc_looks.py ZONE` prints one
line per key. The Moradon worm's model is its looks row (sPid 700) through
the same rules, and cooks to the same release. KO also scales each NPC's model
by a record value × 0.01 (`005cdd82`–`005cdda9` → `0041f800` → `0043b650`);
n3e does not yet (PQ-272).

Parts whose UVs leave 0..1 convert since PQ-264: KO draws a part with wrap
texture addressing (the part renderer `00412570` sets no stage-0 address state
and the client's other stage-0 address writes are written back; the wrap
default is Direct3D 8's, so this is inference from the binary), and the
converter moves each such triangle by whole repeats and gives the part an
atlas region that repeats its texture, so the model samples what KO's wrap
samples; parts inside 0..1 convert as before
(evidence,
D-168).
Resource IDs are bounded at 32,767, since NPC-in sign-extends the record's
ID (`005cd68f`).

A clip that starts and ends on one frame (the shop and smith looks' attack,
struck, guard and spell clips) converts since PQ-273 as that frame's pose
held: KO's clip start `0041be40` never compares the two frames, its tick
`00418b20` keeps the frame on that one value, and `00418e00` poses the
joints there. The converted clip is two equal keys 1/60 s apart (one sample
of the converter's 60 Hz grid; with no freeze time, as the NPC clip set
`0045a950` starts its clips at `0045ac88`, KO counts the clip played one frame
tick after its blend); a clip that ends before it starts is refused
(evidence,
D-169).

Parts with non-opaque materials convert since PQ-265: the converter reads a
part's render flags (blend with the material's factors, double-sided, unlit)
and its texture's alpha (DXT1 and DXT3) into the render runs above,
with the alpha test KO applies to every part; a model with neither converts
as before. Other flags (KO's fog-off flag 2 among them: no homeland part uses
it and no check shows its draw), a diffuse other than opaque white and blend
factors past D3DBLEND 10 are refused by name, and the player path refuses render
states (PQ-280)
(evidence,
D-173).

Skeletons with joint scale convert since PQ-266: KO's joint matrix rotates
and then scales along the parent's axes, with the scale static or from a
linear scale track and the bind at frame 0 with its scale; the converter gives
each scaled joint a parent node for its translation and scale, so the pair
poses as KO's matrix does; a skeleton without a scale converts as before
(evidence,
D-174).

Skins past n3e's bounds convert since PQ-267: KO's client has no bound on a
vertex's joint influences or a skeleton's joints. A skeleton past 64 joints
(up to 127) skins with the joints that carry weight in the drawn skin, which
is exact
(evidence,
D-175).
Since PQ-283 a vertex past four influences keeps every influence, up to 64,
and draws with all of them (N3SI/N3SJ clips, N3NI/N3MI models, engine 40;
[influence tables](#influence-tables-n3si-n3sj-n3ni-n3mi-engine-40)). This
replaces PQ-267's four largest within a bound; the player path refuses such a
vertex by name
(evidence,
D-176).
Skin vertex normals without a direction convert since PQ-281: KO lights a
part vertex with its normal as loaded (not turned by the joints, not
normalised), so a zero normal gets ambient light only; n3e's lighting uses a
normal's direction, so a drawn corner whose normal is non-finite or shorter
than 10⁻⁶ takes its own triangle's unit normal, a fidelity gap that PQ-285
retires
(evidence,
D-177).
A state whose clip index is at or past its looks row's clip table converts
since PQ-268 as the clip KO keeps playing: KO's clip starts (`0041be40`,
`0041c160`, `0041c000`) start nothing for such an index and leave the clip
already playing. On a table without clips (`chr\default.n3anim`: the
monuments and camp gates 14000, 14002, 24001, 30091, 30092, 30100) KO never
starts a clip and poses the joints at frame 0, so every state converts as
that pose held (two keys 1/60 s apart, no blend, no loop; every joint's
rotation is written as a track, so a skeleton without keys still has a
duration). On a table of one or two clips (24000, 24002, 14001) the missing
walk, attack and death states take clip 0, converted as idle is. A table that
has the walk clip but lacks attack or death (three to ten clips) is refused by
name: the clip KO keeps there depends on the state before (no row has one).
KO lets the kept clip run on through a state change, where n3e restarts the
reused clip; n3e ends the death clip in its corpse state, where KO's
animation tick `00457d90`, by inference, never requests state 5 for a dying
NPC on a table without clips (other state-5 paths not read; PQ-287 confirms)
(evidence,
D-178).
Zone 1 converts 52 of its 52 looks keys and zone 2 52 of 52.

## KO reference templates (PQ-251)

`tools/assetc/ko_npc.py` builds a zone's N3N3 templates from the operator's own
K_MONSTER, K_NPC and K_NPCPOS rows, read through `tools/assetc/ko_tables.py`
(checked, canonical, never committed). `zone_templates(tables, zone, game,
nation)` returns one template per table row the zone's used spawn rows
name (rows the AI's spawn load skips, or with NumNPC 0, are not used), ordered
K_MONSTER then K_NPC by `sSid`, and each used spawn row with its template's name.
Each column is mapped as the AI server reads it
(evidence,
combat evidence,
D-164):

| Template field | Row columns | Mapping (AI address) |
|---|---|---|
| `name` | table, `sSid`, `strName` | `<game>:monster/<sSid>-<slug>` or `<game>:npc/<sSid>-<slug>`; the name is a rule ID, not a display label |
| `looks` | `sPid` | `<game>:looks/<sPid>` (`0042214c` sends it after the id) |
| `health` | `iHpPoint` | as is (`0043893e`, `0042214c`, `004248e5`) |
| `level` | `sLevel` | as is (`004209da`, `00423e5e`; sent as one byte by `0042214c`) |
| `attack_ticks` | `sAttackDelay` | ⌈ms / 50⌉ (`0041de51` returns it as the next delay) |
| `speed` | `bySpeed2` | m/s: 1.5 m a step, one step per 1,500 ms (`0043893e`, `004184cb`) |
| `attack_range` | `byAttackRange` A, `byDirectAttack`, radius r = `sSize` × `sBulk` / 10⁴ | the distance below which `0041d266` lets it strike: min(2r + 3, A + r + 1); `byDirectAttack` 1 min(r + 30, A + r + 1); 2 A + r + 1 |
| `search_range` | `bySearchRange` | as is (`0041c21e`: 3-D distance from the NPC) |
| `tracing_range` | `byTracingRange` | as is, n3e's home leash (KO bounds the path to a damaging target, `0041d5d1`; D-106) |
| `acquisition` | `byActType`, `byGroup` | passive for act type 1–4 (`0042476d`, `0041c21e`) or a group equal to the package's `nation`; else aggressive |
| `xp` | `iExp` | as is, 0–50,000,000 (record `+0x3c`; the kill reward `004209da` shares it by damage dealt) |
| `damage`, `attack` | `sDamage` | as is, 0–10,000 (record `+0x52`; the strike on a user `0041f535`: X = `sDamage` × 200 / (user `+0x94` + 240), capped at 2.6 × `sDamage`; user `+0x94`/`+0x90` read as defence/evasion by use: inference); above 10,000 is past n3e's N3D1 attack bound; KO's short result wraps only above about 22,800 (defence 0, PQ-260), so the cook refuses it |
| `defense` | `sAc` | as is (record `+0x4c`; the user's strike `00443a34` divides by it) |
| `accuracy` | `sHitRate` | as is (record `+0x4e`; over user `+0x90` it picks the grade row, `004235aa`) |
| `evasion` | `sEvadeRate` | as is (record `+0x50`; user `+0x8c` over it picks the row, `00444164`) |
| `scale` | `sSize` | as is, 1–1000 % (record `+0x24`, `00438c42`; sent by `004221d5`; the client's drawn scale, PQ-272: [drawn scale](#drawn-scale-n3n4-engine-41)); left out with `drawn_scale=False`, for a package without a looks table |

Not carried: `bySpeed1` and `sStandtime`, which pace wander (PQ-070); the spawn
row's own act type (ActType − 100 for K_NPC rows: path and spawn behaviour);
`sAtk` (record `+0x4a`), which neither strike reads. KO's NPC types and ids a
user's strike cannot damage (`00443a34`: `+0xc69` 0 or 1 from `0042476d`,
`sSid` 10401 and 20401, `byType` 2 a fixed 20) and type 14's strike from the
user's `+0x70` (`0041f535`) are not modelled (PQ-258, PQ-070). A
row the bounds cannot carry is refused by name. KO also keeps own-nation NPCs from
being attacked or retaliating; that is PQ-258. `python3 tools/assetc/ko_npc.py
<zone> [--nation 1|2]` prints a zone's summary from the export; no package uses
the cook yet (PQ-219).
