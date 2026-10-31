# Equipment-selected combat animation (N3A4)

Engine31/wire24 adds `combat_animation` to the package manifest. It requires the
complete engine30 rest/appearance/equipment presentation set. Earlier packages
retain their existing playback. N3A3 still describes ten player and four NPC
clips; N3A4 adds independent player clips rather than changing that ordering.

`combat-animation.bin` is little-endian:

| Field | Bound / meaning |
|---|---|
| Magic | `N3A4` |
| Clip count | u32,1–64 |
| Each clip | f32 duration (.001–3600s), f32 entry blend (0–2s), u32 loop-blend flag (0/1), two f32 marker times (-1 or0–duration) |
| Profile count | u32,1–32 |
| Each profile | u32 ready clip index, u32 attack count1–4, distinct u32 attack indices |
| Selector count | u32,1–4 |
| Selectors | distinct u32 equipment slot indices |
| Row count | u32,1–256 |
| Each row | one u32 inventory-definition index+1 per selector (0 means empty), then u32 profile number1–profile count |

Every clip must be referenced. Attacks must have loop-blend disabled. All indices
are checked; every nonempty item must be allowed in that equipment slot. Row keys
must be unique and an all-empty fallback is mandatory. Unlisted combinations use
that fallback. Extra clips are hashed canonical `combat-0.bin` through
`combat-(count-1).bin` N3S1 files, at most32MiB combined. The client verifies their
skeleton/mesh/atlas compatibility and durations before entering the world.
Truncation, trailing data, missing files and unexpected release files fail closed.
Manifest clips also carry a `source` path; profiles contain `ready`/`attacks`,
selectors use `slots`, and rows contain `items` (definition IDs or null)/`profile`.

The server derives `Entity.combat_style` (field22) from committed equipment,
including on remote snapshots. An accepted strike freezes `strike_style` (field23)
with its existing strike tick; queued durability writes retain the initiating
profile. Bags, instance serials and currency are not disclosed. NPCs and older
packages use zero. Neither field is an intent or changes combat outcomes.

The renderer selects a deterministic cosmetic variant from entity ID and strike
tick, so observers agree. It does not consume gameplay RNG or claim to reproduce
the historical random stream. A gear change updates ready posture but preserves
an in-progress attack. Playback separates logical action from clip index, uses
the chosen duration/blend/markers, and retains interruption, death and session
reset behavior. Engine31 retains full-body playback. The N3A5 extension below adds moving layers
and equipment timing; general playback-rate modifiers remain open.

Binary and local-asset evidence.

## Timed profiles and moving attacks (N3A5)

Engine32/wire25 extends this file to `N3A5`. Each profile appends u32
`interval_ms` (50–60000) and u32 `moving` (a nonlooping clip index). After all
selector rows comes u32 upper-joint count1–63 and distinct u32 node indices1–63.
The root is excluded; the client verifies every index is a joint in the actual
player skeleton. Manifest fields have the same names, plus top-level `upper_nodes`.
Every stationary or moving clip participates in the existing reference/byte bounds.

The server freezes the selected interval and moving flag with the admitted hit,
including across a pending wear commit. Deadlines use ceiling(interval_ms/50)
simulation ticks; the local repeat intent uses the same quantization and retains
its deadline across target cancellation or equipment changes. The interval does
not rescale clip playback: the binary distinguishes item delay from animation-rate
modifiers. Buff/movement rate modifiers remain outside this batch.

`Entity.strike_moving` (field24) is an output-only frozen flag. Nonzero pending
movement, or recent authoritative displacement when no newer input supersedes it,
selects the moving clip. Observers use that same selection. Moving attacks blend
only the mask's local TRS over an independent locomotion controller; the root and
legs keep their walk/run/backward phase. Stopping movement changes the base while
the upper action finishes. Upper exit blends toward the current base. Death/rest,
replacement entities, despawn and session changes clear or interrupt the tracks.

Moradon imports source clips14/15 and upper joints1–15; root0 and lower joints16–23
retain locomotion. Nineteen extra clips cover six profiles. Interval values are
1000ms unarmed/shield,1140ms blade/dual,1390ms two-hand sword and 1450ms bow; the tick
deadlines are20/23/28/29ticks. These game-specific indices and values live in the game package.
Audit and verification.

The sixth profile, `bow` (PQ-347), is 1298's bow: ready clip 92 (1298 client `0045bfe0`, an
empty right hand with a left-hand kind 70), and clip 26 as the attack and the
moving attack at 1450ms, the archery cast the 1298 attack tick `004659b0` makes instead
of a swing (the class's archery row: start animation 26, cast time 1.3s, plus
0.15s). Only the opt-in `--glow-2233` cook adds rows for it: each grade of the
`<selfname>'s Azagai` alone in the left hand, checked against the player's 1298
skill table (`tools/assetc/ko_chrplug_2145.py` `combat_rows`). Since PQ-416 the
glow cook also makes it a ranged basic attack (below), and since PQ-420 its
shot is held for the cast and the clip stretched over it; arrows and the cast
FX remain open
(evidence).

## Ranged basic attacks (N3RB)

PQ-416 (D-216) adds the optional
`ranged-attack.bin`. It names N3A5 profiles that are ranged basic attacks and
needs the N3A5 combat animation and the melee policy (the radii); no engine or
wire version changes, and both readers bound it. Manifest key `ranged_attack`:
`{"profiles": [{"profile": n, "reach": r, "range": d}], "notice": "text"}`.

| Field | Bound / meaning |
|---|---|
| Magic | `N3RB` |
| Count | u32, 1–32 |
| Each entry | u32 profile (1-based, distinct), f32 `reach` (0–`range`), f32 `range` (0.5–100) |
| Notice | u32 length 0–96, then that many printable ASCII bytes |

The server checks a strike under a ranged profile (the one committed equipment
selects) against the actor's and the target's radii summed plus `range`, as a
3-D distance, inclusive, and refuses `out_of_range` beyond it; a melee profile's
check is unchanged. A ranged strike is never a moving one (`strike_moving`
false). The client never chases under a ranged profile: an armed attack whose
target is beyond the strike range neither walks nor sends; it posts `notice` and
tries again one interval later. A Ctrl or double click walks to half the summed
radii plus `reach`. The client does not shoot while the keys move the player and
otherwise stops its walk and faces the target when it shoots.

The glow cook gives the bow profile `reach` = the Azagai's 2145 Item_Org range
column (400) × 0.1 and `range` = that + 2.0 (40 and 42 m: the 1298 client's
`00583780` and `00468620`, with the archery rows' add range 100), and 1298's
text 4009 "Skill Failed - Too far" as the notice
(evidence).

### Cast time (N3RC)

PQ-420 (D-217) adds the `N3RC` layout:
each entry appends u32 `cast_ms`, 0 (the strike resolves when accepted, as
`N3RB`, which both readers still accept) or 101–10000. Manifest: an optional
`cast_ms` per entry; the cook writes `N3RC`.

| Rule | Bound / meaning |
|---|---|
| Clip | the profile has exactly one attack clip; no other profile uses it (as ready, attack or moving) and its own ready is another clip; it has a first marker |
| Stretch | both readers scale that clip's key times, duration and markers by `cast / duration` (1298 `00461ab0`); the entry blend stays; a skeletal plug's clip is not stretched (2233 `005719a0`, `00434980`; PQ-424) |
| Landing | ceiling((blend + first marker × cast / duration) / 50 ms) ticks after the acceptance, 1 to the profile's interval ticks (1298 `004689f0`, the frame waiting out the blend, `00418b20`) |

The server holds such a shot from its acceptance: the archer's strike fields
show it (`strike_result` `casting`, no damage), the interval runs from then and
no other strike, skill or rest starts. At the landing tick the strike resolves
through the ordinary path (after its wear commit, as every strike) with
`strike_tick` kept at the cast start, and the hit is presentation event kind 6.
A movement input that moves, admitted after the acceptance, cancels it
(`interrupted`), as do death (`actor_dead`), a session or life change, another
profile (`equipment_changed`) and a lost or dead target; a cancel clears the
strike fields, so observers stop the clip. The start limit is not checked
again (since PQ-467 a profile's hold is, below). The
landing waits, a tick at a time, while a durable combat write is pending on the
archer or the target (another player's wear commit) or there is no combat or
settlement capacity (the interval is already spent), and a shot still waiting
20 ticks past its landing tick is dropped (`combat_pending`). The
client keeps the attack on after `interrupted`, waits for the result 2 s past
the cast time, stops its predicted clip when the keys move it during a held
shot, and draws the hit on the kind 6 event; a stretched clip's swing sounds
scale with it. Under a profile with a flight (N3RG, below) the landing tick is
the release and the strike resolves when the arrow arrives (PQ-439).

The glow cook sets the bow's `cast_ms` to the archery row's cast time × 100
(1300 ms): clip 26 (1.6 s, blend 0.2 s, marker 1.3737 s) lands 27 ticks after
the shot, inside its 29-tick interval
(evidence).

### Ammunition (N3RD)

PQ-421 (D-218) adds the `N3RD` layout:
each entry appends u32 `ammo` (0, or a 1-based index into the inventory items)
and u32 `ammo_count`, and a second notice (u32 length 0–96 and printable ASCII
bytes) follows the first. Manifest: an optional `"ammo": {"item": id, "count":
n}` per entry and an optional top-level `ammo_notice`; with either the cook
writes `N3RD`, else `N3RC`. Both readers take all three layouts.

| Rule | Bound / meaning |
|---|---|
| Item | an inventory item with durability 0 (it never wears) |
| Count | 0 with no item, else 1 to the item's stack limit |
| Package | names ammo only with the wear policy (`wear.bin`), whose commit removes it |
| Carried | the first bag slot (in slot order) holding the item holds at least the count; equipment and storage never count (1298 `004a29e0`, Ebenezer `004b0792`) |

The server refuses a strike under such a profile without its ammunition
(`no_ammo`, no effect) at the acceptance, spending no interval, and again at a
held shot's landing, whose interval its cast start already began. A shot that
lands removes the count from that slot in the same transaction as its wear
(made for every such shot, a miss too), clearing the slot at 0; when the
locked bag no longer holds enough, the transaction applies nothing and the
strike fails `no_ammo` (its interval likewise begun). A cancelled held shot
spends nothing. A held shot under such a profile starts its landing, and so
its commit, one tick before its landing tick, so the hit is still published at
the landing tick, when the commit completes within a tick (a slower database
delays it), and the result comes inside the interval; a move in that last
tick no longer cancels it. The client counts the same slot in its last bag state; without enough
it sends no shot and posts `ammo_notice` once an interval, before the range
test, and keeps the attack on after a `no_ammo` result.

PQ-444 (D-224): under a profile that
also has a flight (N3RG, below) the ammunition goes at the release, not in the
strike's commit, and its landing has no lead tick; the rules above (the
acceptance check, the first slot, the locked bag) apply to the release's
write.

The glow cook adds 1298's arrow (Item_Org 391010000: "Arrow", countable kind
120, price 1, weight 0, icon 39101000) as `demo:item/arrow` (stack 9999, 100
granted at start, sold by the supplies shop) and gives the bow profile `ammo`
= that arrow with the archery row's type-2 arrow count (1), refusing a row
whose need item is not the bow's kind / 10 (7) or whose exhaust item is not
that arrow; the ammo notice is 1298's text 4007 "Skill Failed - Not enough
item" (evidence).

### Skill hit (N3RE)

PQ-422 (D-219) adds the `N3RE` layout:
`N3RD` with, per entry after `ammo_count`, u32 `hit` (0: the basic attack's
damage; 1: a type-2 skill hit) and u32 `hit_rate`, `add_damage` and
`add_damage_plus`, all 0 when `hit` is 0. Manifest: an optional `"skill_hit":
{"hit_rate": n, "add_damage": n, "add_damage_plus": n}` per entry; with one on
any entry the cook writes `N3RE`. Both readers take all four layouts; only the
server uses the terms.

| Field | Bound / meaning |
|---|---|
| `hit_rate` | 1–1000: KO's MAGIC_TYPE2 HitRate (record `+6`), a percentage of the grade ratio |
| `add_damage` | 0–300: AddDamage (`+8`), a percentage of the damage base (300 is the backup's largest) |
| `add_damage_plus` | 0–10000: AddDamagePlus (`+0xe`), added to every landed strike, a miss included |

A player's strike on an NPC under such a profile resolves as KO's archery
(`AI Server-official.exe` `0040d471` -> `00443a34`, skill branch, HitType 0):
the grade is the basic attack's (`00444164`) of (hit rate / evasion) ×
(`hit_rate` × 0.01f) rounded to f32; the base is trunc(`add_damage` × 0.01f ×
(attack × 200 / (defence + 240))); a hit deals trunc(base × 0.6f +
rand(0..=base) × 0.89f + 0.99), a miss 0; `add_damage_plus` is added, and a
sum of 0 is a miss (KO applies nothing and reports it as a zero strike). The
rolls and their order are the basic attack's; profiles without the hit, and
NPC strikes, are unchanged.

The glow cook gives the bow entry the class archery row's terms from the
operator's own MAGIC_TYPE2 export (`tools/ko-reference/inspect_db.py --table
MAGIC_TYPE2`, checked by `tools/assetc/ko_tables.py` against the AI server's
binding `004107ab`): for 108003, HitRate 100, AddDamage 100, AddDamagePlus 0.
It refuses a missing export or row, a HitType other than 0, a row whose
HitType, HitRate, AddRange or NeedArrow disagree with the 1298 client's
`Skill_Magic_2` row, and values outside the bounds. It also gives the Azagai
items the package's bow stats category (dexterity path, off hand in full) with
their 2145 Item_Org attack (column 16, 116) and initial durability (column 20,
8000), so the bow is not counted as broken
(evidence).
Since PQ-434 (D-221) each upgrade
grade adds its Item_Ext row's bonuses, as both clients' tooltips do (1298
`004d6320`, 2233 `005aa8e0`) and 1298's per-number ITEM rows hold (Ebenezer
`0041f077`): attack Item_Org column 16 + Item_Ext column 9 and durability
column 20 + Item_Ext column 13, so 116 / 8000 for the plain bow and 182,
148, 163, 200 / 17000, 14000, 15000, 17000 for the normal +10 and the
reverse +1, +10 and +30
(evidence).

### Cast effect (N3RF)

PQ-423 (D-220) adds the `N3RF`
layout: `N3RE` with, per entry after the skill-hit fields, the cast effect:
u32 key length (0–64) and the key (printable ASCII; empty: none), then u32
joint count (0 without a key, 1–2 with one) and the joints, u32 each, a
skeleton joint index + 1 (0: the actor's position; at most 128; distinct).
Manifest: an optional `"cast_effect": {"clip": key, "joints": [j, ...]}` per
entry (joints 0-based, -1 for the actor), which needs a `cast_ms`; with one
on any entry the cook writes `N3RF`. Both readers take all five layouts; the
server checks the bounds only; the client also requires the key to be a clip
of the package's `effects.bin` with only triangle records.

The client draws the clip from the held shot's start (the kind-2 strike event
under the profile: the local start of its own predicted shot, else the event
tick) at each joint of the caster, for the archer and every observer that
receives the event, turning every record about the joint by the caster's
drawn facing each frame, and plays the clip's `effect:` sound once per joint
at the start. It ends the clip at once when the caster's strike fields stop
showing that cast (`strike_result` `casting` with that `strike_tick`): the
landing, a cancel, death or a session change. An observer that arrives
during a cast does not see it; KO probably does the same (an inference from
the callers of `00479de0`: only the own casts `00583f20`, `00583b90` and the
casting receive `00585a90` trigger a row's self FX), not yet confirmed.

1298 (`KnightOnLine.exe`): the cast start `00583f20` triggers the row's self
FX (`+0x40`) on the caster at part `+0x44` % 1000 and, when not 0, at
|`+0x44` / 1000| (`00479de0`, `0058447f`/`0058449a`; observers `00585a90`);
the flying phase stops it with `0047a710`(…, 1) (`00584b00`), the fail
receive `00586fa0` on a cancel; with move type -1 the bundle sits on the
joint and faces the caster's +Z (`00477590`), and its mesh part turns from
+Z to that direction (`0048f700`). For a type-2 row the cast start plays
clip `0x1c` (28) instead of the row's start animation when either hand holds
a kind-71 crossbow (`005844c7`–`0058451f`); a package expresses that as the
profile's attack clip.

The glow cook gives the bow entry the class archery row's self FX 500
(`fx/arrow.fxb`: the arrow mesh, sound 311 `bspear_pull_0.wav`) as a 10 s
self clip (`ranged-cast-500`) on joint 12, checks the bow profile's attack
clip against the crossbow rule (the package has no crossbow, so it stays 26)
and refuses a row with no self or flying FX, an FX `fx.tbl` lacks or a part
past the player skeleton
(evidence). The
arrow's shape file carries a position (1.782, 3.721, -0.409) that 1298 never
draws: the FX mesh part's init (`0048ea70`), which ends its load and the clone
each trigger makes, sets the shape's position to the bundle's (0 in a fresh
clone) plus the part's own file position ((0, 0, 0) in `arrow.fxb`), and the
rig shows the arrow in the drawing hand
(PQ-429).
Since PQ-430 the cook does the same: an FX mesh part's shape is offset by the
part's position, turned and scaled with the vertices, and the part's current
position (that position plus its motion) is added after, so the arrow sits on
joint 12 and reaches about 0.9 m ahead along the facing
(evidence).
The arrow in flight (FX 590, the same file, PQ-417, below) cooks by the same
rule.
1298 scales a mesh part after turning it to the bundle direction, which for a
self FX is a turn about y to the caster's facing; the cook scales before its
own y turn, the client's facing turn after, and the two agree only when a
part's x and z scale are equal, so since PQ-431 the cook refuses any other
mesh part (evidence).

### Flight (N3RG)

PQ-417 (D-222) adds the `N3RG`
layout: `N3RF` with, per entry after the cast effect, the flight.

| Field | Bound / meaning |
|---|---|
| Key | u32 length 0–64 and the clip key (printable ASCII; empty: no flight). The client requires an effects clip with only triangle records |
| Source joint | u32, a skeleton joint index + 1 (0: the actor's position), at most 128 |
| Speed | f32, 1–1000 m/s |
| Hit key | u32 length 0–64 and a clip key (empty: none); the client requires an effects clip |
| Hit joint | u32, index + 1 as above; 0 without a hit key |
| Release | u32 length 0–64 and an audio key (empty: none) |

Without a flight key every field is 0 or empty, and a flight needs a cast
time. Manifest: an optional `"flight": {"clip": key, "joint": j, "speed": s,
"hit_clip": key, "hit_joint": j, "release": key}` per entry (joints 0-based,
-1 for the actor; the last three optional, the hit's two together); with one
on any entry the cook writes `N3RG`. Both readers take all six layouts; the
server checks the bounds and, since PQ-439, keeps the speed, which times the
shot's arrival.

PQ-439 (D-223): the server releases a
held shot under a profile with a flight at its landing tick (D-217's cancel
rules apply until then), with no roll and no durable write: the archer's
`strike_result` becomes `released` (its cast effect ends; the clip plays on)
and the server publishes a release event, kind 7 (actor, target, style,
request sequence and both positions). The arrow then flies ceiling(3-D
distance between the archer's and the target's positions at the release /
speed × 20) ticks, at most 200 (10 s), and the shot resolves at the arrival
through the landing path (the roll, wear, damage, ledger, AI, death, the
kind-6 event and the archer's result). In flight a movement no longer
cancels it; the archer's death, a session or life change, another profile
and a lost or dead target still do, with no effect (the strike fields keep
`released`). The
archer's next shot may be accepted while the arrow flies, also while the
archer's own arrival write is pending (a held cast writes nothing at its
acceptance; its landing waits for that write); its release waits for the
previous arrow to land, at most 20 ticks past its landing tick
(`combat_pending`). An arrival under a newer cast leaves the archer's strike
fields and interval to that cast. A released shot refused at its arrival
(`equipment_changed`, `stale_target`) also keeps `released`.

PQ-444 (D-224): under a profile that
names ammunition the release spends it, as Ebenezer's flying phase does
(`004630a6` → `0046f3f1` → `004b0792`). At the release tick, once the
previous arrow has landed and no durable combat write of the archer's own is
pending (an arrival's wear, an incoming hit's; at most 20 ticks past the
landing tick, then `combat_pending` with nothing spent), the server checks the
first bag slot holding the item in its bag (too few: `no_ammo` at once) and
starts a durable write of its own, D-218's event with no wear records and no
roll, that removes the count from that slot. The release follows its commit,
in the same tick when the database answers within it (a slower one delays
the release; a move admitted meanwhile no longer cancels the shot). A write
that finds too few in the locked bag fails the shot `no_ammo` at the
release: no kind-7 event, no flight or damage, the cast cleared, its
interval begun. A shot cancelled after its write committed (in flight, or
because the target or archer changed during the write) has spent its arrow.
The arrival then neither checks nor removes ammunition and starts with no
lead tick; it commits only when the hit wears equipment, so an unworn hit is
published at the arrival tick and a worn one a tick after it.
PQ-450 (D-225): the flying phase's
other checks (a sitting user, a per-skill reuse window, a quest, the MP cost
and a master-skill stone) change nothing for the class archery rows, so the
release checks only the ammunition; an archery skill will take its MP and
reuse window there too.
PQ-447 (D-227): a skill or rest may start once the shot is
released, while its arrow flies, as 1298's skill start (`005819e0`) and sit command (`005d91f0`) test
the cast, not the arrow; a held shot still refuses both. The arrow lands during the cast or under the
seated archer, who stays seated, and a skill's impact waits for the archer's own pending arrival write
or reward (not an incoming hit's), so it neither takes its cost before that commit nor starts a second
reward; a hit that commits once the cast reached its impact stage (cast time over and recast commit
started) does not interrupt the cast, as 1298 rolls the interruption only before the release
(`005cec10`). Since PQ-455 (D-231) the cast ends at its release (its cast
time over), also while the transition to the impact stage waits for a pending combat write: after it neither a
hit nor a move cancels it, as 1298's cast tick (`00585830`) fails a cast on a move only before the release
(`00584b00`); its range is measured from where it was released (Ebenezer's effecting check `004c1dbe` measures current server
positions; the caster's then is inferred to be its release position).
PQ-454 (D-228): a shot with a flight pays the basic attack's
cost at its release, before its arrow, as Ebenezer's flying phase takes the Msp (`0046f3f1` ->
`004a083f`) and its effecting phase checks none for a row with a flight (`00464b43`): an archer that
cannot pay fails `insufficient_resource` at the release (no arrow spent), and the arrival neither
checks nor takes it, so a skill's impact during the flight cannot leave it unpaid. A pending reward
holds a landing, at most 1 s, instead of refusing it. The client's auto-attack takes its shot's `released` strike
fields as the end of its wait for the result, so the next shot goes out once
the interval has run, and retries a ranged shot refused as `combat_pending`
or `target_pending` (the arrival's write) without spending an interval.

At the release (the kind-7 event; the kind-6 event before PQ-439) the client
launches the flight at the event's time, for every observer that receives
the event, and (PQ-445, D-226) the archer's own client at its predicted
release, described below: from the shooter's source joint as drawn,
toward the centre of the target's box as last drawn (the pick box), else the
target's drawn position, its direction keeping its pitch (the shooter's
facing when the two points meet). The clip's anchor is the start plus the
direction × speed × age, and every record turns from the model's forward
(n3e's -z, KO's +Z) to the direction by the shortest turn. The flight ends at
once where the ray from its start first enters the target's current box, or
at the launch distance when the ray no longer meets the box; the hit clip
then starts on the target's hit joint with its `effect:` sound at the target.
At the launch the client plays the flight clip's `effect:` sound and the
release key at the shooter. The drawn flight is presentation; the server
times the arrival from its own positions and the speed.

The archer's own client (PQ-445, D-226) does not wait for its release event:
it launches the flight of its own held shot on the first frame at or after
its drawn clip passes the marker, the time it sent the shot plus the
stretched clip's entry blend and first marker (the server's landing ticks
before their rounding up), starting it at that frame (so that frame draws it
at its start), toward
the target as drawn then, plays the flight and release sounds and ends its
cast effect there. That flight is pending until the server's release event
for the shot's request sequence confirms it (no second flight launches); a
pending flight that reaches the target's box holds its hit clip until then.
A shot the server does not release (a refusal such as `no_ammo` at the
release or `combat_pending`, a cancel, death, a skill cast, a session
change) ends the pending flight where it is and drops its held hit and
sounds; a hit or miss result confirms one whose release event was not seen;
a release event with no pending flight (the target was not drawn at the
prediction) launches it as an observer's would. 1298's cast tick `00585830`
calls the release `00584b00` when `004689f0` sees the player's own clip pass
its marker, and the release sends the flying phase (`00451b80`), stops the
self FX and flies the arrow at once (`005855bc` -> `00587ac0`); an
observer's flying receive `00585f20` flies it only for another caster
(`00585fd6`).

1298 (`KnightOnLine.exe`): the release `00584b00` and an observer's flying
receive `00585f20` call `00587ac0` for a type-2 row, which plays sound
`0x157c` at a shooter whose left-hand item is kind 70–79 and, for MAGIC_TYPE2
HitType 0, flies the row's flying FX through `0047a2d0` from the shooter's
part `+0x44` % 1000 toward the target's box centre (`00460bd0`) with move
type 0: `004770c0` sets its direction with the pitch, the tick `00477590`
moves it at the bundle's velocity, `0048f700` turns the arrow to it. The FX
manager's tick `0047a8d0` stops it on the target's box (`0045c2c0`) on the
shooter's client, which reports the hit; the -101 fail receive `00586fa0`
stops it elsewhere and triggers the row's target FX `+0x54` at the target's
part `+0x58` for every receiver. The effecting phase is the hit: Ebenezer's
`004630a6` forwards it for an NPC target to the AI server at once
(`00464027`), whose `0040cd1d` acts on phase 3 only and whose type-2 leaf
`0040d471` rolls and applies the damage then; nothing compares it with the
flying phase's time or distance, and a dead source's effecting is dropped
(`004635a1`). n3e keeps the hit on the server, timed from its own positions,
and lets every client find the drawn arrival itself.

The glow cook gives the bow entry the class archery row's flying FX 590
(`fx/arrow.fxb`, 77 m/s) as the 10 s flight clip `ranged-flight-590` from
part 12, its target FX 550 (`fx/blow.fxb`, a 0.5 s billboard, sound 5500) as
the hit clip `ranged-hit-550` at part 0, and the release key
`ranged-release` (sound 5500, `arrow_pull_0.wav`) for its kind-70 bow. It
refuses a row whose MAGIC_TYPE2 HitType is not 0 (a homing flight) or whose
NumArrow is not 1 (a spread), both queued (PQ-440). Before PQ-445 a flight
shorter than about 4 m had ended within the release event's ~0.05 s snapshot
delay, before any frame drew it, on the archer's client too; since PQ-445 the
archer's own arrow leaves on the frame of its predicted release, starting
there, so at least that frame draws it however short the flight (unless it
starts inside the target's box), and only an observer's may still end
undrawn, as an
observer's in 1298 waits for the relayed flying packet
(evidence,
PQ-445). The
glow bow's shot at 6 to 42 m lands 2 to 11 ticks after its release
(evidence).

### Hold (N3RH)

PQ-467 (D-233) adds the `N3RH`
layout: `N3RG` with, per entry after the flight, the hold.

| Field | Bound / meaning |
|---|---|
| Distance | f32: 0 (no hold) or 0.5–200 m |
| Plane | u32: 0 the 3-D distance, 1 the ground (x/z) plane; 0 without a hold |

Manifest: an optional `"hold": {"distance": d, "plane": "3d" | "xz"}` per
entry; with one on any entry the cook writes `N3RH`. Both readers take all
seven layouts and bound the hold; only the server uses it. The target must
be within the hold (inclusive) from where the archer stands at three
moments: the acceptance (besides the start limit, the radii plus `range` in
3-D), the release of a shot with a flight, and the landing, which is the
arrow's arrival for a shot with a flight and the release and impact at once
without one. Between the acceptance and the release nothing measures the
range. Out of the hold at the release, the shot fails `out_of_range` with
neither its ammunition nor its cost spent (that check comes after the waits
for the previous arrow and the archer's own write, before the cost); at the
landing it fails `out_of_range` with no hit, its arrow and cost already
spent at the release.

Ebenezer (`Ebenezer-official.exe`): the magic packet `004630a6`, for a user
source and a row whose Type1 is below 4, calls `004c1dbe` at `004635c8`
before it dispatches the phase, so the casting, flying (`0046f3f1` comes
after) and effecting phases of the class archery rows all pass through it;
those rows' Moral 7 (local asset, the OpenKO MAGIC export) does not take the
pass for Morals above 4 (`004c1f63`–`004c1f71`), and Type1 2 passes while
dx² + dz² (x and z by the source's names) is at most (the ITEM record's Range `+0x3e` / 10, integer
division)² + 1000.0 (`004c1fcd`–`004c203d`, the float `00634b84`) for the
item number in equipment slot 8, else slot 6 (the left and right hand by
the source's names). The glow cook gives the bow
that bound as its hold: √((range column // 10)² + 1000) on the ground plane,
√2600 ≈ 50.99 m for its 400, beyond its 44 m start limit, so with n3e's
positions a glow shot fails it only when the target or the archer has
moved apart since the acceptance
(evidence).
