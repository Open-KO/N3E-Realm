# Merchants (N3O1)

Engine16/wire9 adds required hashed `commerce.bin` to engine15's bag contract.
No durable schema changes are needed: the bag's currency/items and append-only
operation results share migration008's transaction. Engine15 releases retain
N3I1 and cannot admit commerce operations. Definitions are original package data;
this is not an automatic import of the supplied SQL Server ITEM table.

`N3O1` consists of little-endian u32 carrying-weight limit (1–2^31−1), maximum
request quantity (1–9999), high-price threshold (0–2^31−1), high-price quantity
limit (1–maximum), item count, and item price/weight records. Each record has a
length-prefixed item ID, unit weight (0–1000000), purchase price (1–2^31−1), sale
divisor (1–10000). Records cover every inventory definition exactly once.

Then a shop count (1–64) and records: namespaced ID, printable ASCII label
(1–64 bytes), position (3 finite f32 in ±1000), interaction radius (f32 .5–20),
remote-sale boolean (u32), offer count (1–64), unique offered item IDs. Shops
must lie on the package map. Offers must exist in N3I1; the legacy progression
reward is currently excluded to preserve its aggregate ownership contract.

BagRequest adds service ID7, item ID8, quantity9; operation2 buys and operation3
sells. Source is the zero-based bag slot for both operations; destination is zero.
Instance is the current slot identity, including zero for an empty purchase slot.
Revision/request IDs and original retry semantics match [bags](inventory.md).
All non-commerce requests require these additional fields empty. Prices, money,
weight and player coordinates supplied by clients are never authoritative.

The simulation captures current selected-character state using its bounded command
queue. The database worker checks the captured range/alive state, persisted life
revision and session/realm fences. Captures expire after two seconds and are
checked again before commitment. Movement after capture does not move the point
at which the interaction was submitted. Every new purchase requires range;
remote sale is explicit package policy because supplied binary variants differ.
Original immutable retries are resolved before new range/life/deadline checks,
while still requiring a current authenticated selected character and realm owner.

Buy: require an empty or matching stackable slot, bounded quantity, sufficient
currency, total stack capacity and carrying weight. A new stack gets a durable
instance ID; merging preserves its ID. Quantity and currency change together.
Purchased durability is reset to the definition maximum, as observed in the binary.
Sell: require matching owned item/instance and sufficient quantity; credit is
`floor(price * quantity / divisor)`, not unit rounding followed by multiplication.
An exhausted stack clears completely. Credit cannot exceed the currency limit.
Wide intermediate arithmetic protects amount and weight calculations. Denied
business outcomes are recorded for exact retry; unavailable authority/DB never
acknowledges commitment.

Normal/tools UI: Enter `/shop` displays the nearest shop and numbered offers;
`/buy OFFER SLOT QUANTITY` and `/sell SLOT QUANTITY` transact; `/retry` repeats the
last operation. Slots/offers are numbered from1 in the UI. The inventory page keys
also page offers. Labels mark package merchant locations in the world.

Remaining fidelity: animated merchant actors, historical shop artwork, prices/
weights/classes from matched reference definitions, dynamic taxes/premium rates,
repair, loot weight, equipment-derived capacity, tradability/rental flags, ordinary
item consumption and full reward-item spending. Fixed package limits and synthetic
fixtures exercise the reusable transaction path without claiming those systems.
