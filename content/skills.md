# Bounded direct skills (N3K2, N3K3, N3K4, N3K5)

Engine34/wire27 requires `skills.bin`, referenced `player-skill-N.bin` scenes,
and effects. Older engines reject these additions. Skill policy defines one
package archetype and1–32 skills. This bounded capability supports cast-time
friendly healing and hostile NPC direct damage. It does not implement a talent
point system, class selection, buffs, projectiles, areas or PvP.

N3K2 uses little-endian u32/f32 and length-prefixed strings. Header fields are
archetype, display label, the reach (f32 `start`, f32 `hold`, each 0–50, and
u32 plane: 0 3-D, 1 the ground plane x/z; PQ-465) and count. N3K1, the
layout without a reach, is refused. N3K3 (PQ-466,
D-234) adds the client's too-far
notice after the reach: a string of 1–96 printable ASCII bytes with at most
one `%s` (the skill's label) and no other `%`; the manifest key is the
policy's optional `notice`, and the cook writes N3K2 without it. N3K4
(PQ-469, D-235) adds, after the
notice, the client's failed line, bounded as the notice is, and its colour
(u32 ARGB, alpha not 0); the manifest key is the optional `failed`
(`text`, `color`), which needs a `notice`. N3K5 (PQ-479,
D-243) adds, after the failed line,
1–8 refusal lines: a status (`[a-z][a-z_]{0,31}`, one line per status, not
`out_of_range`), a target kind (0 any, 1 a player, 2 an NPC), a text bounded
as the notice is and its colour (alpha not 0); the manifest key is the
optional `refusals` (a list of `status`, `target` `any`/`player`/`npc`,
`text`, `color`), which needs a `failed` line. Each entry stores ID, label, class, level,
MP cost, cast milliseconds, cooldown milliseconds, target kind, amount,
interruption-survival percentage, attribute index, resistance, animation index,
range, allowed equipped-item IDs, cast/target effect keys, cast joints and target
joint. Encoded joints are index+1, zero meaning actor root. Bounds include:
level1–100, cast50–10000ms, cooldown0–60000ms, amount1–5000, range(0,50],
attribute0–4, resistance0–200, at most64 allowed items and two unique cast joints.
Content identities and weapon references must belong to the package. Readers
reject duplicate skills/joints, nonfinite values, bad references and trailing data.

The authenticated Action channel selects the skill and target. The server checks
session/sequence, class, level, alive state, target category, range, MP, equipment,
cast occupancy and cooldown. Database work runs on the existing bounded worker.
Casting freezes the action/target, publishes start/end ticks and stops sitting.
Movement, invalid target/session/life and incoming-attack interruption cancel it.
Every completed attack packet can roll interruption, including a miss, matching
the client binary. Since PQ-455 (D-231) the
cast ends at its release, the tick its cast time ends while it still stands, as
1298's cast tick fails a cast on a move only before its release (`00585830`,
`00584b00`) and its received attack rolls only until then (`005cec10`): after it
a move no longer cancels the cast and a hit no longer rolls, while the recast
commit and the impact may still wait. The range is still checked until the
impact, from where the cast was released to the target (a cast on the caster
passes): Ebenezer's magic packet checks the effecting's range between the
caster's and target's current server positions (`004c1dbe`), and the
caster's position then is inferred to be its release position. Since PQ-465
(D-232) the range has two forms, both
from the package's reach. At the acceptance the 3-D distance must be at most
the skill's range + both melee radii + `start`, 1298's client limit
(`005819e0` -> `00583780`), which the server enforces, and the hold must
pass. Between the acceptance and the release the range is not checked, as
neither binary is inferred to check it before the effecting. From the release to the
impact the distance on the hold's plane must stay below the range + `hold`,
Ebenezer's Type1 3 rule (`004c1dbe`: Range + 15 on the ground plane). Since
PQ-466 (D-234) the client tests the
same start limit before it sends a skill on another actor in its view, from
its own position, as 1298's skill start does (`005819e0` -> `00583780`):
beyond it the client sends nothing and posts the policy's notice (an N3K2
policy has none, so it refuses silently; 1298 posts
text `0xfa9` formatted with the row's `+0x18` string, the name by the
source's layout, in `0xffffff00` through `005d7250`). The test is a hint; the server's check stands. When the server refuses a skill the cast ends for everyone. Since PQ-469 (D-235), when the refusal is `out_of_range`, the caster's client also posts the policy's failed line, its `%s` the skill's label, in the policy's colour, for the skill action it sent with that sequence number, as 1298 answers Ebenezer's refusal (phase 4, -103, `0046e707`) with text 4004 ("%s failed", the name) in `0xffff3b3b` (`00586fa0`); other statuses still show only in the combat record. Since PQ-471 (D-242) that is read to be the only match: `0046e707`'s other callers refuse states n3e has no counterpart for (over-time effects, buffs, transformation, warp, stealth, area skills, name targets, room spectators, authority 250), and Ebenezer answers n3e's other refusals -100 (its admission `00464b43` on a casting phase; 1298 posts text 4002 "Casting failed"), 0 (an effecting's class, level, target and MP refusals; 1298 posts nothing) or not at all (D-236's silent drops) (binary within linear-sweep scans; evidence). Since PQ-479 (D-243) an N3K5 policy also carries refusal lines, and the caster's client posts the line for a status when that is the server's first answer (its acceptance) to a skill it sent, on a matching target kind, once per action. 1298 makes the class, MP and need-item tests itself before it sends anything (`0057f7f0` from `005819e0`), with its own texts in `0xffffff00`. It has no level test, and it sends a cast on an NPC it still sees alive, so a low level or an NPC that died on the server first meets Ebenezer's -100 and "Casting failed" in `0xffff3b3b` (`00586fa0`). Moradon's lines are the player's texts 4003 (`wrong_class`), 3004 (`insufficient_resource`, a priest's MP text) and 4005 (`weapon_required`), and 4002 (`level_required`, `target_dead` on an NPC). The client sends no NPC skill on a target it sees dead, as 1298 returns for a type-7 row on a target in state 4 or 5 (`00582ea3`, `00582eac`; a row whose `+0x38` is 113 casts with target -1 before that test, `00582e0f`–`00582e89`). `target_dead` on a player, `invalid_target`, `actor_dead`, `stale_target`, `cooldown` and refusals after the acceptance post no line, as in 1298. Since PQ-480 (D-244) n3e's server tests a skill's weapon only at the acceptance, as nothing in KO refuses a weapon removed mid-cast: 1298 tests its need item only at its skill start (`0057f7f0` from `005829e2`, not from the release `00584b00`), its item drop `0049f7c0` and Ebenezer's item move `004a1aa4` refuse no move while a cast runs, and Ebenezer's admission `00464b43` reads no hand slot (binary within operand and direct-call scans, no rig; evidence). A cast whose weapon is unequipped lands and takes its cost; the impact reads the caster's attributes as they then are. Since PQ-481 (D-245) the client picks a skill's recipient as 1298's skill start `005819e0` does, and has no notice of its own there. A player or self skill (1298's type 2) goes to a player the client sees, whatever its health (`00582bdf`), and otherwise to the caster (`00582b7b`, `00582c16`). An NPC skill (type 7) with no target is held back with no packet and no line (`00582e97`). So is a hinted press on a target the client does not see, sees dead or sees is not an NPC (`00582ea3`, `00582eac`, `006164c0` at `00582ebc`). The client has no level test, as 1298 has none before it sends (`005819e0`, `0057f7f0`); the server's `level_required` posts the policy's line (Moradon: 4002). Instead a skill above the player's level does not go on the hotbar, by drop or by the right button, as 1298's skill tree gives a basic skill above the player's level the enigma icon (`004e7320` -> `004ea6f0`) and refuses that icon on both paths (`004e3120`); a skill bound earlier stays pressable (`004de6f0`, `004e2ca0`). Still open: the local check order (PQ-482), the skill window's locked icon and double-click cast (PQ-483), and what 1298 shows for a heal on a dead player (PQ-484) (binary within the named functions' listings and call lists, no rig; evidence). 1298 also drops its client recast (PQ-468), and Ebenezer starts its reuse window (`0046dbe2`) only after the checks that refuse -103, so in KO such a skill keeps no cooldown and can be cast again at once, unless the window of its last accepted use (or of its last too-early try) still runs (an inference from the binary, no rig; PQ-470). Since PQ-472 (D-236) n3e's server deletes the recast it committed at the release (D-099) when it refuses the impact with one of the refusals Ebenezer answers with a phase-4 packet before its window (`out_of_range`, `insufficient_resource`, `wrong_class`, `level_required`, `invalid_target`, `target_dead` on an NPC; `weapon_required` until PQ-480, after which it no longer refuses a released cast), so the skill can be cast again at once; it keeps it for the refusals Ebenezer drops with no answer, after which 1298's client keeps its own recast (`actor_dead`, `target_dead` on a player, `stale_target`), and for its own session, timeout, database and NPC-write refusals (an inference from the binary, no rig; evidence). Admission and completion recheck requirements. MP and impact
apply after the database cooldown gate succeeds. Magic damage uses the existing
NPC contribution, kill, settlement and reward path.

Migration20 stores recast deadlines in Postgres. Character row locks serialize
concurrent commits; realm lease, session, online and life revisions fence requests.
Session entry recovers active deadlines for both admission and hotbar presentation.
Cooldown never depends on Redis or a client timer. Cancellation racing a committed
DB gate can conservatively retain the cooldown without an impact. D-099 drains
that in-flight commit off the simulation tick and recovers the actual PostgreSQL
deadline into the live cooldown snapshot; since D-236, for a refusal Ebenezer
answers before its reuse window, the same fenced transaction first deletes the
deadline that commit wrote, and only that one. New casts wait for recovery; interruption
never applies the cancelled spell or spends its MP. Database-blocked death, timeout and
logout cancellation (kept) and a target leaving the hold or an NPC target dying (undone)
are regression tested; a database-blocked move, which came
after the release, lands the cast once the commit returns (PQ-455).
Audit. Existing HP/MP
remain ephemeral; this is not durable-vitals support. A disconnect cannot duplicate
an acknowledged reward or bypass a positive skill cooldown.

A press inside the cooldown is refused `cooldown` at the acceptance, writes
nothing and leaves the deadline, however often it is repeated; the press at
the deadline is accepted. Ebenezer's reuse window (`0046dbe2`) instead stores
the time of a too-early effecting (`0046dcab`): it refuses while now + 0.1 s
(`[00633eb4]`) is at most the last effecting + ⌊(CastTime + ReCastTime) / 10⌋
s. Since PQ-473 (D-237) n3e
deliberately keeps its rule. Its server gate stands in for 1298's local
recast refusal (`00581c45`), which sends nothing and restarts nothing. A
release in n3e is at least (CastTime + ReCastTime) / 10 s after the last
release whose recast stands (one not undone by D-236); a release undone by
D-236 was refused where Ebenezer refuses before its window, so it stamps no
slot there either. So the window's test against the skill's own slot never
refuses a cast n3e accepts, while Ebenezer's float32 clock is precise enough
(below 2^20 s of counter time; D-237 Limits). Ebenezer's other refusal there,
with all 15 of a user's slots held by other skills inside the new skill's
window (`0046dcfe`), is not reproduced: since PQ-475
(D-238) that is a correction of a logic
bug, because the refusal follows from a full 15-entry table, not from the
skill's own reuse, and is silent. n3e refuses a skill for reuse only by its
own deadline, and no slot count is package data. Ebenezer empties those slots
at a new connection and at the close (`0048ff43`; binary, within the limits
of its scans and of the accept pool's unscanned writers), and 1298 empties
its own recast list whenever it enters the world (the manager reset
`0057e520`, run by MyInfo `005c87c0`, which answers every game start), so in
KO a relog, through the exit menu's character selection or a client restart
after a disconnect, ends every recast early (binary at each step of the
exit-menu path; the restart path also rests on four inferences, D-239
Limits; no rig). n3e's deadline survives a
logout, a reconnect and character selection, and is read again at session
entry for both admission and the recast display: since PQ-476
(D-239) that is a correction of the
exploit, not a gap. KO's room system also sends MyInfo during a session
(Ebenezer `004970cb(1)`: leaving or being expelled from a room, a spectator's
join and the room's end, and the second room tick after a start), which
empties 1298's recast list while Ebenezer keeps its slots. A skill whose slot
another skill took (a skill in no slot takes the first slot past the *new*
skill's window, `0046dcc8`–`0046dcfc`) is then cast again before its own reuse
has run. Since PQ-477 (D-240) n3e's
per-skill deadline, which no other skill's cast touches, is the correction of
that exploit too (binary at each step of the server path and of the client's
sends and reset; inferences and the missing type-42 NPC placement in D-240
Limits; no rig;
evidence).
n3e has no room system; one built later keeps every deadline across its
transitions. The restart is
reached in KO by a client that sends past its own recast gate, or whose
recast list was emptied (a relayed fail, PQ-468, or a room's MyInfo, PQ-477),
and also by an unmodified client whose frame clock runs fast (PQ-478, below)
(binary for
the window and the gate;
evidence).
PQ-474 read 1298's recast timer. Each recast starts at ReCastTime × 0.1 s
when the cast is released, and the skill tick subtracts each frame's
`QueryPerformanceCounter` time until it drops below zero. Frames of 1 ms or
less, or 1 s or more, count 1/30 s, and while the graphics device is lost
(`Present` fails) the frame time is not updated and the tick keeps
subtracting the last one. So, while the device presents and between those
bounds, 1298's recast lasts ReCastTime / 10 s of wall time from the release, as n3e's `cooldown_ms` does (binary; the
column mapping is local-asset with ko-src's field order). The recast also
survives the client's own death and respawn, whose handlers never touch the
list, and so does n3e's deadline, so D-236's `actor_dead` keep stands
(binary within the erase helpers' caller lists; no rig;
evidence).
PQ-478 read those routes. At ordinary frame times, with even delivery, the
next cast keeps an unmodified client outside the window. It releases at its
clip's first marker, which lies 0.867–0.926 of the way through Light
Strike's clip and 0.857–0.911 through Tiny Healing's, after a 0.2 s blend
(local-asset). That puts two Light Strike effectings at least 6.90 s apart
against Ebenezer's 5.9 s, and two Tiny Healings at least 2.1 s apart against
0.9 s (binary chain: `0046be20`, `00457d90`, `00461ab0`, `004689f0`,
`00410c00`). No frame cap was found that holds 1298's frame clock to wall
time, though (within the import-reference scan):

- its device is always windowed (`006453b0`), and no wait was found on the
  frame path within that scan, so a frame of 1 ms or less, counted 1/30 s,
  is not excluded;
- a deactivated client keeps ticking (`0064acf0`), so a lost device keeps
  subtracting the last frame time;
- uneven delivery also shortens the gap Ebenezer sees (inference).

Through these, KO's restart can punish a player for a client clock bug or a
network delay. So since PQ-478 (D-241)
n3e's rule is recorded as a correction of those logic bugs, not as a mapping.
The rule itself is unchanged. No machine was shown to reach the fast routes,
and the routes are not known to be complete (no rig;
evidence).

The Moradon package fixes the demo archetype to Priest and offers Tiny Healing
(level1,15HP,5MP,1.9s cast) and Light Strike (level2,5MP,1.5s cast,5.4s recast).
Local table rows supply these values. Its reach is start 2, hold 15 on the
ground plane (`games/moradon/skills.json`): with its 1 m melee radii a spell
starts within 29 m (3-D) and lands while the target stays below 40 m on the
ground. Its notice is the player's 1298 text 4009 and its failed line the
player's text 4004 in `0xffff3b3b`, cooked from their
`Texts_us.tbl` (`tools/assetc/ko_skills.py`), never committed. Light Strike uses the package magic attribute
and zero NPC magic resistance. The synthetic demo pursuit leash is30m so
spells, which start within the range + both melee radii + `start` (27m for the synthetic policy, PQ-465), do not trigger an immediate target reset; acquisition remains2.5m. The **player** AI binary0040e7c4 formula is:

```
base = floor(amount * (attribute + 20) / 186)
upper = floor(base * 230 / (resistance + 250))
damage = floor(floor(upper * float32(0.85)) + random(0..upper) * float32(0.3))
```

The supplied binary differs from the source and its NPC-caster routine0042a642.
Current items have no staff spell bonus; the binary's staff and special-user bonus
branches remain unsupported. Attribute≤1000 and package amount bounds avoid the
legacy signed-short overflow domain. Current NPC resistance and starting attributes
are demo data, not a reconstruction of the historical server database.

K or the bottom Skill button toggles the original skill-tree UIF. The public pane
shows the two skills; unsupported talent tabs/point controls are hidden. Drag or
right-click to register on the current hotbar page; double-click a skill or use
its hotbar shortcut to cast. Original clips are stretched to the cast duration;
hand/target effects follow model joints. Positive recast deadlines drive the shared
hotbar sweep/flash. Panel slide easing and animation transition blends remain
fidelity gaps. Evidence.
