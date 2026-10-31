# Supported gameplay vocabulary (Phase 3)

`package.json.gameplay` is required. The [source schema](package.schema.json) and
`tools/assetc/rules.py` reject unknown fields, nonfinite values, invalid namespaces
and inconsistent bounds. The cooked `gameplay.bin` is a required hashed dependency;
server startup validates it independently and requires a walkable NPC spawn.
Changing rules changes the release hash. No reference assets or code are used.

There is one player template, targeted damage action, NPC template and one default spawn, plus a
fungible item definition. `action`, `item`, and `npc` are namespaced stable IDs.
Each item occupies one slot; there are no stacks, equipment or item-use operations.
The engine has no demo ID branches. This is a bounded rule vocabulary, not scripts.

| Fields | Meaning and bounds |
|---|---|
| `health`, `resource`, `damage`, `cost`, `npc_health`, `npc_damage` | Positive integers up to 100,000; cost cannot exceed resource. Optional [melee](melee.md) permits zero cost. |
| `cooldown_ticks`, `regen_ticks`, `npc_cooldown_ticks`, `respawn_ticks` | 1–1,200 ticks at 20Hz. Regen restores one resource per global interval while alive. Respawn delay applies to both templates. |
| `speed`, `npc_speed` | 0.01–3 metres/second, using the shared conservative walkability solver. |
| `range`, `npc_range`, `aggro_range` | 0.05–10 metres, inclusive 3D Euclidean distance between authoritative origins. No line-of-sight or rewind check. |
| `leash_range` | 0.05–64 metres from NPC spawn to its target; at least aggro range. |
| `spawn_x`, `spawn_z` | NPC spawn, ±1,000,000 metres; Y comes from walkable collision. Player spawn retains the shared zone spawn query. |
| `slots` | 1–64 item capacity. Durable capacity/item identity cannot silently change on an existing character; incompatible packages fail selection. |
| `starting_items` | 0–64, no more than slots; granted exactly once on first selection, including characters created before Phase 3. |
| `reward_items` | 1–64, no more than slots. |
| `reward_xp`, `level_xp` | 1–100,000. Level is `1 + floor(xp / level_xp)`; levels currently have no stat multiplier. |

## Resolution and AI

Action requests contain session generation, increasing sequence, target runtime
instance and action ID. Actor identity comes from the authenticated connection.
Invalid action sequences never execute; higher sequences are consumed even if the
action fails. Identical/repeated packets cannot deal damage twice. Unknown IDs,
stale/dead targets, dead actors, pending rewards, range, cooldown and resource
failures have explicit results. Rejected actions consume no resource/cooldown.
Successful damage is deterministic; there is no RNG to seed. Resource/cooldown
are charged before saturating health subtraction. Player commands resolve in
queue order, then movement/regen/respawn, then NPC AI, then the snapshot. First
successful lethal action wins the single-recipient reward; no party/assist/PvP
reward policy is implied. Animation markers and client result packets cannot
cause damage or grant rewards.

NPCs acquire the lowest durable character ID among living players inside aggro
range, chase using walkability, attack on cooldown, and return when the target
leaves, dies, fails output or exceeds the leash. Returning NPCs heal on reaching
home and then reacquire. They do not navigate around complex obstacles. A dead
NPC remains a corpse until its delay expires, then receives a new instance ID.
Player death disables movement/damage; automatic respawn also replaces the runtime
ID, restores health/resource and returns to zone spawn. IDs come from bounded
Postgres sequence allocations consumed in order; gaps are harmless. NPC combat,
health/resource and cooldowns are transient and reset on reconnect/restart.

## Durable rewards

The killed NPC instance is the operation ID, unique for that encounter's single
recipient. A bounded dedicated worker checks realm/session fences, locks the
character/progress rows, updates inventory and XP, and inserts an immutable result
in one transaction. The operation primary key deduplicates a retry; different
recipient/item/quantity/XP with the same operation conflicts. Results include the
post-transaction count and XP. Inventory is represented by one constrained count
for the single fungible item; physical item identity/slot layout is not supported.

If the complete grant will not fit, the transaction records `inventory_full` and
grants **neither items nor XP**. It cannot be reclaimed by repeating the request.
The player sees `pending` until commit completes and no pending item becomes
spendable. Actions reject while a reward is pending. There is no item spending API
in this phase. The full snapshot carries current inventory/XP/level, pending ID,
and last committed operation/status, so dropped/coalesced baselines recover it.
`RewardStatus` is read-only and returns an immutable result only for its authenticated
recipient. An unknown operation cannot initiate a grant. Restart/reattach recovers
committed inventory from Postgres; status queries resolve lost acknowledgements.

A crash before commit grants nothing and may reset the transient encounter. A crash
after commit retains exactly one grant even before tick activation/acknowledgement.
Disconnect and graceful shutdown drain outstanding grants before final save.
Database failure closes admission permanently and pauses gameplay until process
restart, retaining the Phase 2 lease behavior. A restart inside the crashed
owner's lease (at most three seconds) waits for its expiry, for at most five
seconds, and never takes over a live owner (D-139). No automatic transaction retry
is needed for the single worker; ambiguous results are resolved by durable status.

`N3E_REWARD_FAULT=before_commit|after_commit|before_response` deliberately exits the
server at those boundaries for isolated acceptance. It is an operator environment
setting, never a wire command, and must remain unset for normal use.

## Cooked layout and future properties

`N3G1`, followed by length-prefixed UTF-8 strings `action,item,npc`, then little-endian
u32 values in `rules.py:INTEGERS` order, then IEEE binary32 values in `FLOATS` order.
No padding or trailing bytes. The exact ordered fields are mirrored in
`server/src/rules.rs`; canonical recipe and binary both participate in release
identity. The client uses the server's action ID, speed and maxima, and displays
server-authored combat state.

Current Phase 4 candidates retain
NPC spawn/next-cycle respawn overrides as future work. Template health/damage/
range/cooldown remain release/restart-only for the initial registry. All are
currently immutable package data; no live mutation or privilege is implemented.
Converted N3P1 reward definitions (including item/capacity) require a reviewed
forward migration, not automatic reinterpretation or an ordinary config revision.

## Optional field extension (N3G2)

`spawns` optionally replaces the single `spawn_x`/`spawn_z` location with 1–2,048
`[x,z]` pairs (32 before PQ-250; older readers refuse more), each finite and
within ±1,000,000 metres. Every spawn must resolve to walkable collision at
server startup. All share the same NPC template; each
has independent life, aggro, cooldown, reward operation and preserved respawn home.
`interest_cell` optionally chooses a 1–64 metre grid cell size. Snapshots and chat
cover the surrounding 3×3 cells. Defaults are the original single spawn and 1m cells.
The server still bounds connection counts and snapshot size: a crowded window keeps
the nearest entities that fit one 65,536-byte frame (PQ-250, D-163). The PQ-250
evidence measures 1,300 NPCs with 49 sessions; that is a measurement, not a
capacity guarantee.

With neither field present, the cooker emits byte-identical `N3G1`. With either
present, it emits `N3G2`: the same ordered fields after the four-byte magic,
followed by float32 cell size, uint32 spawn count and that many float32 x/z pairs.
All are little-endian. New readers accept both versions and reject trailing bytes,
nonfinite/out-of-range values, invalid counts and truncated data. Old readers reject
N3G2 explicitly; protocol fields are unchanged. Release hashes bind the extension.

## Optional movement extension (N3G3)

An optional complete `gameplay.movement` object selects mode-aware player movement.
It requires `engine_version=2` (or 3 with optional [camera data](camera.md)),
`protocol_version=2`, `content_schema_version=1`.
Packages without it retain protocol 1 and the unchanged N3G1/N3G2 layouts
(engine 1, or 3 with camera data).
Readers support these declared combinations and reject unsupported pairs or a movement
record with version 1. The release index writes the declared pair, so old engines
reject new movement releases before world entry. No database migration is needed.

`gameplay.speed` is walk speed (0.01–6m/s when this extension is present; legacy
0.01–3). Required fields, serialized in this exact order, are:

| Field | Bounds |
|---|---|
| `run_speed` | 0.01–6m/s |
| `backward_speed` | 0.01–6m/s |
| `radius` | 0.1–1m horizontal wall radius |
| `height` | 0.5–3m wall vertical overlap height |
| `step_height` | 0.05–0.5m maximum adjacent support-height change |

Require `backward_speed <= speed <= run_speed` and `step_height < height`.
All values must be finite; unknown/missing fields and booleans are rejected.
N3G3 consists of the N3G1 base (magic replaced by `N3G3`), the complete N3G2
interest/spawn extension, then the five little-endian float32 fields above.
Omitted spawns/interest use the same defaults as N3G2. No trailing bytes are valid.
All producer/cooked/recipe bytes participate in release identity. Both C++ and
Rust independently validate the movement record; neither derives physics from
visual mesh bounds. NPC speed retains its previous maximum and solver.

Each authenticated input advances one 50ms step at the package-selected speed.
Intent components are finite in [-1,1], normalized if their length exceeds one;
analog magnitudes below one are retained. Stop is zero intent. Each new-policy
step uses `ceil(speed*0.05/min(radius*0.5,0.05))` substeps (1–6 within the bounds).
Each tries the full displacement, then X and Z separately for conservative sliding.
Support must exist with an adjacent height difference no greater than `step_height`.
The retained slope test is `abs(normal.y) >= 0.707107 * length(normal)`;
wall vertical overlap excludes triangles wholly below feet+0.05 or above feet+height.
This is bounded static collision, not a general capsule/ceiling/physics solver.

[KO-01's test recipe](../tools/assetc/movement_fixture.py) supplies the approved
comparison values without changing the demo or existing KO field releases.
Calibration decision
separates adopted units/synthetic collision dimensions from reference observations.

## Optional melee interaction

[Engine 4 / N3M1](melee.md) adds client continuous intent, horizontal size-aware
player range and supported zero cost. NPC rules, damage and durable rewards remain
unchanged. Existing packages retain their legacy interaction/range behavior.
