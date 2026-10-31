# Requested respawn and NPC lifetime (N3L1)

Optional `life` package policy requires engine 7 and protocol 3. Old releases
(engine 1–6, wire 1/2) retain automatic player/NPC respawn using the original
`gameplay.respawn_ticks`. Server migration 004 adds durable requested player life.
Movement policy is independently optional under wire 3; its wire fields and bounds are unchanged.

```json
"life": {
  "model": "requested_v1",
  "player_delay_ticks": 60,
  "npc_corpse_ticks": 40,
  "npc_respawn_ticks": 120
}
```

All values are integer 50ms server ticks. The original lab numbers are synthetic.
`life.bin` is ASCII `N3L1`, little-endian u32 model=1, then the three u32 fields
above, with no trailing bytes. Player delay and corpse duration are 0–1200;
NPC respawn delay is 1–12000 and must be at least corpse duration. The producer
and both readers validate these bounds, file presence and engine/wire compatibility.
The recipe and dependency hashes bind all values to release identity.

| State | Wire value | Transition |
|---|---|---|
| Legacy | 0 | Only packages without N3L1; existing HP/timer semantics |
| Alive | 1 | Committed player death → waiting; NPC death → corpse |
| Dead waiting | 2 | Server reaches player eligibility tick → dead ready |
| Dead ready | 3 | Valid request, reserved ID and committed respawn → new alive instance |
| Corpse | 4 | NPC corpse deadline → dormant; respawn deadline → new alive instance |
| Dormant | 5 | Omitted from snapshots; NPC respawn deadline → new alive instance |

`Entity.life_state` is field 16; `corpse_until_tick` is field 17. `respawn_tick`
(field 11) means player *earliest request eligibility*, or NPC automatic respawn
deadline; the two are independent. Dead players remain visible indefinitely.
Zero corpse duration hides the dead NPC at the next baseline; equal corpse and
respawn delays replace it without an intermediate absent baseline. ID exhaustion
leaves the player dead (request result `unavailable`) or the NPC dormant for retry.
NPC timers advance with simulation ticks. Player eligibility uses a Postgres deadline
and a conservative local tick deadline; offline time counts, and client timestamps
never determine eligibility. The configured wait begins when death commits.

`Envelope.respawn` (19) contains session, monotonically increasing nonzero request
sequence (<2^63), and expected dead runtime entity ID. Server derives character
identity from authentication. Validation order: session/connection generation,
sequence, enabled policy, expected instance, dead player, deadline, pending job,
reserved ID. The transaction rechecks session, realm, revision and eligibility.
Results (`Envelope.respawn_result`, 20) contain sequence, status and current instance.
Statuses: `stale_session`, `stale_request`, `unsupported`, `stale_entity`, `not_dead`,
`too_early`, `pending`, `unavailable`, `respawned`. A session-valid sequence is consumed even
on rejection; retry with a fresh sequence. Repeated successful requests cannot heal
or replace again. A lost reply is resolved by the atomic owner snapshot or reconnect
to the committed character state. Lifecycle revision compare-and-swap prevents a
second mutation; there is no separate cross-session respawn receipt endpoint.
A new request while a transition is in flight returns `pending`. Success is sent
only after commit and activation.
Existing frame/rate/queue bounds apply; at most one successful request per death.

Revival uses the existing deterministic walkable zone spawn (origin if supported,
otherwise the first walkable triangle centroid), full package HP/resource, a new
Postgres-reserved runtime ID and cleared strike/mode/behavior state. Movement/action/
respawn sequences stay session-monotonic; pending pre-replacement movement is dropped
and acknowledged. Client death stops approach, continuous melee and held walking,
and clears selection. Replacement clears selection, pending prediction, old baseline,
visual motion and camera focus smoothing through existing identity reset paths. E submits an
ordinary request only when the replicated prompt is ready and gameplay has focus.
Both original and optional imported HUDs show the same prompt. No new animation
assets, blending, resurrection spells, location selector, protection or penalty.

## Reconnect, restart and pending rewards

Migration 004 stores a character's dead flag, lifecycle revision and absolute
Postgres eligibility deadline. Death and validated respawn atomically commit their
location and movement acknowledgement with those fields. Checkpoints are fenced by
lifecycle revision as well as session/realm/sequence, so old saves cannot move a
corpse or overwrite a replacement at the same input sequence.

Reconnect/restart loads a fresh session/runtime instance but preserves committed
death, exact death location and remaining eligibility. A ready corpse stays ready;
only a validated, committed request restores full HP/resource at zone spawn. The
server refuses to load a saved dead character into a package without requested life.
Existing alive characters in older packages retain their automatic/transient policy.
Nonlethal HP/resource and NPC state still reset on reconnect/restart. Living movement
keeps the existing five-second rollback bound; committed death/respawn locations do
not. No death penalty or post-respawn protection is added.

While a life transaction is pending the player cannot move/attack, and world
snapshots pause until committed state can be published. Database work stays off the
simulation tick on the bounded worker, with existing statement/lease deadlines.
A crash before commit can lose an unpublished lethal hit or respawn request; a crash
after commit restores its result even if the response was lost. Failure closes
admission; it never reports a durable success or silently revives the player.

Respawn neither cancels nor reissues a pending grant. The existing async reward job
binds to durable character/session and the killed NPC's encounter ID. Its completion
updates inventory only, so it cannot copy an old player entity over the new instance.
Pending inventory is never spendable. Life and reward jobs share the bounded worker, so a blocked reward may delay life
publication; it does not change the eventual life result. Disconnect/shutdown drains
both jobs before final save;
restart reloads committed inventory/results. Uncommitted kills may be lost under
the existing transient-combat contract. Repeated status queries never grant items.
PG/lease failure still closes admission and requires restart; respawn cannot bypass
that gate. No blocking I/O is introduced into simulation ticks.
