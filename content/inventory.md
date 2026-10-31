# Item bags (N3I1)

Engine 15 / wire 8 adds required hashed `inventory.bin` to the editing/life/
progression contract. Static world, exploration/LOD and render detail remain
optional capabilities; exploration requires world+LOD, detail requires exploration.
Both readers enforce the same compatibility and item constraints. Older releases
keep their existing version rules. A realm with durable bags rejects a changed
inventory definition hash or a package without inventory; an explicit forward
migration is required before changing those definitions.

All integers below are little-endian u32; strings are u32 byte length plus UTF-8.
The file is `N3I1`, capacity (1–64), currency ID, currency limit (1–2^31−1),
starting balance (0–limit), definition count (1–64), then each definition:
ID, display label (1–64 printable ASCII bytes), stack limit (1–9999), maximum
and initial durability (0–65535), starting quantity (0–stack limit).
IDs are package-namespaced. Starting quantities create one stack each, never
one slot per unit. Definitions are unique. The existing progression reward must
be defined with stack limit 1, starting quantity 0 and durability 0; progression
owns its starting/reward count. Capacity reserves space for all nonzero initial
stacks plus the existing progression reward capacity. This prevents acknowledged
legacy rewards from becoming impossible to materialize.

D-081 extends the reference-backed whole-record swap: dropping identical stackable
item definitions with equal durability together fills the destination to its
package stack limit. Overflow keeps the source identity and moves to the first
empty bag slot, including the freed source slot when the bag is full. Destination
identity is retained; a fully consumed source disappears. Different items,
durability or nonstackable records still swap whole records. No quantity is lost
and no identity is minted. This user-requested extension differs from the original
binary's whole-record bag swap; warehouse operations retain their existing rules.
Instance identity, item definition, quantity and durability otherwise travel together.
Each nonempty record receives a positive PostgreSQL sequence identity. Empty
slots have all fields zero/empty. All definitions, capacities and initial balances
are package data; the engine contains no KO item IDs or paths.

`BagRequest` envelope 32 has operation 0 (list) or 1 (move/merge-or-swap). A list has all other
fields empty/zero. A move carries a 1–64 character request ID, expected bag
revision, zero-based source/destination slots, and the source instance identity.
Character and realm identity come only from the authenticated selected connection.
The server accepts at most ten bag requests per second per connection, under the
existing frame/byte bounds and bounded database worker queue.

`BagResult` envelope 33 returns the request ID, status, and complete bounded bag.
Successful moves return `committed`; queries return `ok`. Revision, source identity,
slot and reused-request conflicts return named outcomes without moving anything.
The original canonical request and result commit atomically with a swap. An exact
retry returns that original result even after later moves; clients never replace
newer state with its older snapshot. Reusing a request ID for a different payload
returns `request_conflict`. Database errors do not acknowledge commitment. Realm
and selected-session generation fences protect every operation.

Migration 008 adds bags and immutable operation results. Bags are materialized
lazily under a character lock from durable progression state and package initial
items/balance. Loot claims add the item instance in the same transaction as the
existing aggregate count and immutable claim result. Before materialization,
acknowledged rewards remain in progression state. Redis is not involved. Subsequent capabilities add [commerce](commerce.md), [equipment](equipment.md),
[warehouse transfers](storage.md) and [multi-item drops](item-drops.md); their
contracts define current bounds rather than the original bag-only checkpoint.

Client controls: `I` toggles the paginated inventory; `[` and `]` change pages.
Enter `/bag` refreshes, `/swap 1 2` swaps the whole records in visible numbered
slots (UI numbers start at 1), and `/retry` repeats the last move with its original
request ID. These are ordinary authenticated operations in both client builds.
The server refreshes the client bag after acknowledged claims. The original
fixture is produced by `tests/inventory_live.py:prepare`; it uses synthetic item
names, quantities and currency, not values attributed to KO.

D-099 tracks the pending mutation by its exact request ID and bag/storage result
family, accepting only replies observed after that send. Warehouse opening also
uses this tracking because it can charge a fee. Bag lists, unrelated replies
and intermediate `use_pending`/`storage_pending` statuses cannot clear the wait.
Panel closure does not stop reconciliation; disconnect or session/entity replacement
clears local tracking. At three-second intervals the client resends the identical
envelope, at most three times. If its result is still unknown at twelve seconds,
it releases the local UI wait, displays an unavailable-result notice and requests
a fresh bag. This is not a success, rollback or permission to reapply an operation:
`/retry` or `/bankretry` retains the original immutable request, and every new
operation remains revision/identity checked. The result observation queue is bounded
at32 entries. Audit.

## Item tooltip heads (N3IH, PQ-354, D-194)

A package may describe the head of an item's tooltip in `item-heads.bin`,
cooked by `tools/assetc/item_heads.py` from the manifest's `item_heads` record:

```json
{"self_token": "<selfname>",
 "items": [{"item": "demo:item/azagai_reverse1", "name_color": 16755021,
            "lines": [{"text": "(Reverse unique item)", "color": 16755021}]}]}
```

The file is `N3IH`, the token (u32 length and 0–32 bytes; empty is none,
otherwise printable ASCII 33–126), the head count (0–64; zero only with a
token), then per head the item id (a defined N3I1 item, each once), the u32
name colour (0xRRGGBB, at most 0xffffff), the u32 line count (0–4) and each
line's text (1–64 printable ASCII 32–126) and u32 colour. It needs engine 33,
the presentation assets and the inventory. The cooker, the client loader and
the server's content check refuse the same faults; the server otherwise
ignores the file, which is hashed with the release.

The client draws a tooltip's first line, the item's label, in the head's name
colour (yellow without a head), with each occurrence of the token replaced by
the viewer's own character name: only a name the server accepts (1–24 ASCII
letters, digits, `_` or `-`) is used, otherwise the label keeps the token; the
replacement goes left to right, never searches inside an inserted name, and
the line is cut at 128 bytes. The head's lines follow, centred like the name,
in their colours; the tooltip's other rows are unchanged. The rule is the 2233
client's tooltip head (`005aa8e0`: the name's and the kind line's colour by
the item's attribute, `004aad90`: "<selfname>" replaced by the player's name;
evidence);
which colours, lines and token a package uses is its own data. The opt-in
`--glow-2233` KO package carries a file for its 2145 items. Since PQ-361
(D-196) the default Moradon feature packages carry one for the KO item among
their items (an item whose appearance rows name a `ko_item`: the blade,
120110048), cooked by `tools/assetc/ko_item_heads.py` under the 1298 client's
head (`004d6320`, evidence):
the name in the Item_Ext attribute's colour (0 and above 6 white, 1 `8080ff`,
2 `ffff00`, 3 `80ff00`, 4 `dcc77c`, 5 `c87cc7`, 6 `19ffff`), a kind line for
attributes 1–6 (texts 6808–6812 and 6814) in that colour, and the item type
(text by Item_Org kind) in white unless the item is countable; the blade is
`c87cc7`, "(Upgrade Item)", "One-handed Sword". The label stays the package's
item name. Without a file every package reads and draws as before.
