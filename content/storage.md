# Account storage (N3B1)

Engine21/wire14 requires the existing inventory, commerce, equipment, stats and
wear capabilities. N3B1 contains u32 capacity1..192, coin limit1..2,100,000,000,
service count1..64, then each service ID/label, three f32 position coordinates,
f32 radius0.5..20, u32 remote flag0/1 and u32 opening fee0..2,100,000,000.
Identifiers use the package namespace; labels are1..64 printable ASCII. Service
position coordinates are finite and within1000. No game NPC/zone/item IDs enter
engine code. The storage hash extends the composite bag definition identity.

Schema011 stores one warehouse per account and realm. Ownership comes from the
selected character's database row, never a client account selector. All transfers
lock storage before the character, then load the fenced session/bag. Opening,
item deposit/withdrawal, empty-destination storage moves and coin transfers have
immutable request IDs; both revisions and instance identity guard new mutations.
Account characters share storage revision; different accounts remain isolated.
Opening charges the package fee once per operation. Exact retry returns its original
snapshot without charging again, including after reconnect or leaving the service.
New operations require a living character, current persisted life revision and a
simulation-captured position no older than2seconds (also rechecked before commit).
Remote access is explicit package policy. Insufficient funds/weight/space, occupied
slots, stale revisions and access denials have durable original outcomes.

Whole singleton moves preserve identity, quantity and durability. Stack splitting
allocates a fresh global identity; merging retains destination identity, sums bounded
quantity and takes source durability, as in the inspected transfer leaf. A storage
move only targets an empty slot. Withdrawals obey current equipment-derived carrying
capacity and item stack limits. Coin arithmetic is checked against both container
limits. Reward-token ownership counts and progression revisions change in the same
transaction when a token moves; immutable past reward/claim results do not change.
All acknowledged bag, warehouse, counter and ledger writes commit together.

Deposits cannot start with already-frozen wear pending. At admission their requested
bag revision cannot be newer than the authoritative cache; at equal revision the
serial must already occupy the specified bag slot. Subsequent equip/unequip changes
that revision, so a transfer and an intervening equip cannot both pass the database
CAS. Combat continues during storage I/O: repeated requests cannot suppress NPC hits.
Only one storage job per character is pending, on the bounded database worker. Logout
and shutdown drain both storage and wear before releasing character ownership.
Temporary combat/storage/snapshot deferrals are not committed operation results.
Older immutable replies never replace newer bag/storage or progression revisions.

Native controls: `/bank`, `/deposit BAG BANK QTY`, `/withdraw BANK BAG QTY`,
`/bankmove SOURCE DESTINATION`, `/bankcoins QTY`, `/takecoins QTY`, `/bankretry`.
Slots are1-based in commands and0-based on wire. Brackets page the bag/storage panel.
The server rechecks service access; the client chooses the nearest package service.

Grounding: supplied server004b1c52/004b31fe; Aujard0042a090 explicitly queries
WAREHOUSE by strAccountID and loads192records. Client005dcfd0 dispatches replies;
005dd1a0 parses coins and192item/durability/quantity entries into004ac5e0.
Server opening fee10000 applies in zones11/12/201; regional3 requires NPC type31
and range11, while other branches allow remote access. These are package settings.
Warehouse password/regional access variants, rental/bound flags and exact legacy UI
presentation remain separate open catalog work. The supplied DB backup corroborates
schema vocabulary, not a matched release. Binary nonstackable serials are preserved;
stack identities in n3e additionally remain unique across splits.

Bounds correction: server004b2314/004b2585/004b2a20 compare against0xc0 and jump only
when greater, accepting index192 despite open loop004b1fe8 covering192records0..191.
The engine rejects index>=capacity. Stack additions in the legacy leaf also use
signed short arithmetic; the engine rejects overflow instead of wrapping quantities.
These are concrete record-bound/conservation corrections, not permission to simplify
unrelated behavior. Verification and remaining limits
record real database races, process crashes and both native clients.
