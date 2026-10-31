# Equipment records (N3Q1)

Optional engine18/wire11 `equipment` requires inventory, commerce and repair.
The original shared archetype specifies `race`, `title` (u8 each), five base
`attributes` (u8), 1..16 unique printable ASCII slot labels (1..32 bytes), and
1..64 item rules. IDs reference singleton inventory definitions. Each rule has
`id`, nonempty zero-based `slots`, disjoint `blocks`, `title`, `race` (0 unrestricted),
five required base `attributes`, and Boolean `swappable`. All values are package
data; the engine contains no historical item, race, class or slot IDs.

N3Q1: magic, u32 race/title, five u32 base attributes, u32 slot count and strings,
u32 item count; each item is string ID, u32 allowed/blocked bitmasks, u32 required
title/race, five u32 attributes, u32 swap flag. All integers little endian; reject
unknown bits, duplicates, overflows, unknown IDs, countable items and trailing bytes.
The initial archetype is shared package data, not character creation or allocated
stat points. Those features remain open. No attack/defense/visual gear changes are
claimed by this container capability.

BagState field6 contains one complete ItemStack per equipment slot. One revision
covers bag, equipment and coins. IDs must be unique across both containers;
quantity is1 in equipped slots. Migration009 is a downgrade barrier: older servers
reject the schema before they can decode and silently drop field6. The durable
inventory identity is SHA256(inventory SHA256 bytes || equipment SHA256 bytes).
Enabling/disabling/changing equipment on existing bags requires an explicit
migration; no silent reset or best-effort conversion is performed.

BagRequest operations5/6/7 equip, unequip, and move/swap equipment. Fields are
request ID, expected revision, source, destination, instance; commerce fields must
be empty. Equip verifies package base attributes, title, race and allowed slot.
At most one displaced item (destination or exclusive opposite slot) returns to
the source bag slot. Two occupied conflicting slots reject atomically. Unequip
requires an empty destination bag slot. Equipment-to-equipment moves check the
source's requirements and destination; an occupied destination permits a swap
only if its rule is swappable and both resulting positions remain valid.

Realm/session fencing, bounded database worker, rate limits and immutable original
outcomes are shared with inventory. A successful transfer preserves the complete
instance/quantity/durability record. Loot additions and merchant weight computation
retain/count equipped items. No database work runs in simulation ticks.

Native client: `/equipment` opens the named slot display; `/equip BAG SLOT`,
`/unequip SLOT BAG`, `/gearswap A B`, `/retry`. UI numbers start at1. The client
checks shape, definitions, cross-container serial uniqueness and slot exclusions;
older result snapshots cannot roll state back. Subsequent [wear](wear.md),
[stats](stats.md) and [appearance](appearance.md) capabilities supply combat wear,
stat refresh and supported equipment meshes. Character archetype choice/point
allocation, broader class/level checks and unmodeled legacy flags remain gaps.
Pending operation matching and retries follow the [bag contract](inventory.md).

Binary grounding: supplied Ebenezer `004a1aa4` performs these transfers,
`004a51c0` tests item slot types, `004ad9d9` compares item+5b and five base fields.
Loader `0044729b` maps `[ReqTitle]` to record+14f, and population `0041f077`
copies that byte to item+5b. Level/max-level/rank are loaded at adjacent offsets
but not read by the inspected requirement helper. Do not label item+5b as level.
See the evidence report
for addresses, hashes, source disagreement and verification.

Operation8 repairs an owned equipped instance in place through N3J1. It shares
all bag-repair ownership/revision/currency/immutable-result rules and requires
empty service/destination/quantity fields. `/repairgear SLOT` quotes/restores the
equipped slot without moving it through the bag. This extends the still-unreleased
wire11 capability on the active completion branch. Optional engine19/wire12
[N3Y1](stats.md) recalculates ordinary combat stats and vitals after committed
equipment/repair changes. Buff/mastery/transform variants remain open.
