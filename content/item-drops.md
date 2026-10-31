# Generated item drops

Status: bounded direct/group bundles and Moradon integration accepted and merged
through D-096. D-097 audits existing lifecycle correctness. The wider catalog
feature remains partial.

The supplied AI executable SHA256
`8715084f693f7b5c86a585c81b2e3db73accda1d4f79c174bf34d72addcd0435`
is the behavior reference. Read-only static analysis of that executable
(`AI Server-official.exe`, supplied locally, never committed) established:

- `00423e5e` evaluates nonzero drop entries in table order. Chance draws use
  `0040a9dd` inclusive1..10000, including entries whose chance is zero. Event
  scaling is trunc(chance + chance * (event * float32(0.01))), then the second
  pair subtracts100 per excess player level. Eligible premium scaling is
  trunc(chance + chance * float32(0.3)), capped10000, except the first pair or
  chances already>=10000. Both float coefficients are promoted to the confirmed
  53-bit evaluation precision; they are not decimal f64 constants.
- `004240a1`–`00424100`: the second event byte is checked only if the first is
  zero. A nonzero first event suppresses the second even in its zones. This is
  observed behavior, not corrected without evidence of intended independent
  event activation. Current realm event integration remains open.
- Pair1 uses procedural generation below100 and group lookup otherwise; pair2
  always uses group lookup; subsequent pairs use direct item IDs. Direct IDs in
  decimal391010000..391999999 receive20; other direct and all group/procedural
  results receive1. These IDs belong in the import/package adapter, not the engine.
- Group lookup `00427980` draws before resolving the group; missing groups return0.
  It samples `0042ceda` with10000, then modulo30 for the physical slot. Empty slots
  remain empty outcomes. This is not a uniform choice among nonempty entries.
- `0042ceda` wraps32-bit multiplication/addition, reduces modulo(2*bound), saves
  that reduced state, then returns state>>1. Constructor `0042ce8b` sets multiplier
  0x7059, increment0xe0b2, seed0x5b88. Independent objects004cfe50/004cfe60 are
  initialized by004177ef/00417837. Their other references0041781a/00417862 lead
  through004016f9 to destructor0042ced3, which only resets the vtable. No seed
  update outside construction and draws was found in these object references.
- Procedural leaf `00424cb4` differs from source: category draw1..6000 weapon,
  6001..8500 armor,8501..9999 accessory, zero yields no item. Grade helper00425227
  draws0..999 against9 cumulative signed-short weights; class0042530a has12,
  keyed by NPC level/10; code004253ec has4, keyed by NPC level/5. Code category2
  weapon range16..22 and armor failure differ from source. Full procedural
  package conversion is a remaining integration gate.
- Ebenezer SHA256
  `7d83cc2872c92acb776e81366b6d6451625f141dc554e1b292e5b903d2fa7bcb`
  `004a7f1b`: lookup004b464c prefers the first empty bag slot before matching
  stacks.004a8197–004a81cf appends countable quantity or forces singleton1;
  004a8293–004a8297 writes definition durability+42 for the incoming record,
  including a matching stack. Atomic capacity/weight corrections are recorded
  in BINARY-POLICY.

The new DB exports contain723 K_MONSTER,666 K_MONSTER_ITEM,474 K_NPC,
202 K_NPC_ITEM and **zero ITEM_GROUP rows**. All inspected drop rows have five
pairs. These data are supporting reference, not a proven matching binary release;
missing groups must not be fabricated. Raw exports remain ignored. Original
fixtures exercise explicit groups and direct entries.

Implemented bounded runtime: package item catalog and ordered chance rows, explicit
physical group slots, frozen generation draws/results at death, and independent
atomic claim operations. Coin occupies one of six bundle entries; overflow never
writes a seventh. Claim quantity and durability come from the frozen server record.
Procedural selection, premium entitlement state, live events, special/public zones
and shared AI random-call ordering remain open. Ground bundle meshes, both-button
click targeting and the six-slot UIF are implemented; exact corpse placement,
timing and open-range fidelity remain gaps. See the current
[presentation contract](loot-visual.md) and
lifecycle audit.


N3P5 extends the N3P4 prefix with generator multiplier/increment/seed/group bound,
event percent and float32 event/premium coefficients, an item catalog of ID,
quantity and durability, and ordered chance/group rows. Producers and both readers
bound definitions, groups and references; incoming stacks must fit their inventory
definition. Engine28/wire21 is the standalone version; engine29/wire22 composes it
with appearance. Schema018/N3S6 preserve the complete generation outcome at death.
The claim payload includes frozen quantity and durability; retries cannot reroll.
At most five items plus coins enter a bundle. Whole quantities route to the next
eligible party member with capacity and weight, or remain retryable without a
partial grant. Serial allocation, bag state, cursor, entitlement and immutable
result commit together. Acknowledged grants survive server restart.

Hostile producer/reader, PostgreSQL concurrency/rollback/weight/expiry, four
transaction crash points, preserving upgrades, real TLS and before-apply crash
checks are recorded in the batch evidence.
Moradon's blade/potion group/direct rows are original test data, not invented
historical ITEM_GROUP exports.
