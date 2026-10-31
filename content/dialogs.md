# UIF-backed feature dialogs

`N3H4` extends the existing cooked HUD with package-selected feature dialogs.
The client reads `hud.bin`; the importer reads local KO UIF/NTF files. Reference
assets are unchanged and are not a required download or a Git payload.
`games/moradon/ui.json` supplies the original n3e binding/placement adapter.

H4 retains the H3 field order and font metrics. Texture count is bounded to64,
control count to512 and record count to4096. Each record appends a uint32 panel:
0 always,1 inventory,2 character,3 merchant,4 account storage,5 friends,6 party,
7 help,8 modal input. H1–H3 limits and interpretation remain unchanged. Older
clients reject H4 by magic. The server hashes presentation without interpreting
its widgets; no wire, gameplay or durable schema change is needed.

Three additional bindings are admitted only in H4: `value` on text records,
`meter` on images and `action` on hit regions. Their `text` field is a nonempty
1–64-byte key limited to lowercase ASCII letters, digits, underscores and colons.
Keys are data/action identifiers, never executable scripts or arbitrary commands.
The native adapter supplies values and an explicit action allowlist. Unknown
values are empty and unknown actions do nothing. Item IDs and UIF node names
remain outside the engine adapter.

Visibility governs drawing and hit testing. Panel bounds consume world clicks;
modal input admits only its own controls. A hidden panel cannot dispatch a hit.
Button state subtrees retain normal/pressed/hover/disabled behavior. Unsupported
original actions, including stat allocation, quests and guilds, are disabled.

Inventory uses28 visible source areas per page; storage uses24 and friends8.
NPC stock uses24 areas and12 pages, including empty pages. `offer_prev` /
`offer_next` page stock independently of the embedded bag; `offer_page` displays
the one-based page. Opening Shop resets both pages. Empty slots, page changes and
merchant changes invalidate the selected offer before a purchase can be prepared.
These are bounded presentation pages over the package's actual capacities, not a
change to durable slot counts. The Moradon adapter maps four supported equipment
slots into the original hand/ring areas. Empty unsupported equipment areas have
no action. H5 displays package-selected item icons in these areas, with stack
counts over the artwork. The inventory character preview was added later (D-079).

Click a source and destination to prepare a transfer/equip/move. Buy, Sell,
Repair, coin transfer and social controls prepare explicit confirmation/input.
The original trade-count UIF supplies the prompt artwork. Confirmed intents use
the existing native command parsers and authenticated request builders. A prompt
captures bag/storage revisions; changed state cancels it before submission. A
selected item also retains its serial, preventing selection of a replacement.
The server still owns range, life, permissions, capacity, balances and commit.
Opening/selecting a slot never mutates durable state.

Warehouse prompts reuse the protected credential flow. Plaintext is not copied
into HUD values or chat; only masked characters reach the dialog renderer.
Escape clears pending prompt data. Friend presence uses authoritative colors;
party bars use server member HP/resource maxima. No synthetic privilege, premium
entitlement, class progression or unsupported stat value is implied by artwork.

Character uses one window with a remembered Stats/Friends page. The bottom
Character action toggles that window; `tab:state` / `tab:friends` select pages
without toggling. Inventory is independent. `close:N` closes its owning panel
(the two Character pages share their window). Equipping does not open Character.
Viewport anchors place Character at the left and bag/service dialogs at the right;
quantity prompts are centered. See the binary audit
for coordinates, evidence, scaling policy and remaining fidelity gaps.

The Moradon NPC Shop uses `Ka_Transaction_us.uif`, normalized to right edge,y10
with a370x578 reference rectangle. Its stock areas (district3), bag areas
(district11), close/page buttons, coin balance and weight bind to live values.
The original fixture merchant uses the Store heading; overlapping Inn and
Blacksmith headings are omitted by package data. Supplemental Bag prev/next and
Buy/Sell/Repair controls sit below the root. `co_tradeinventory_us.uif` belongs to
the separate centered player merchant window and is no longer imported here.
See the shop audit.


## H5 item artwork

`N3H5` retains the H4 layout and appends an icon table after all records: uint32
count (0..256), then for each entry a length-prefixed item ID, uint32 texture index
and four float UV coordinates. IDs must be unique and belong to the release's
game namespace, using the inventory ID grammar. UVs must be finite, in0..1 and
have positive area. Texture indices must exist and cannot name the font atlas.
The existing64-texture and16MiB file bounds apply. The table may include unused
presentation entries; it does not define or grant gameplay items.

H5 and later admit `item` on image records and `item_label` on text records. Both
use their `text` field as a slot key (such as `bag:0`); the existing feature-key
syntax still applies. Runtime snapshots map slot keys to item IDs. An `item`
record resolves that ID through the icon table; empty or unmapped slots draw no
image. `item_label` is blank for empty slots, draws the quantity when greater
than one over a known icon, and keeps the previous text label for unmapped items.
Counts use the lower-left of the authored slot; selected item details remain
below the panel. Image and label records do not replace the existing hit regions.

Bag/equipment/storage updates and stock paging rebuild these mappings each frame,
so moved, removed and off-page items leave no stale icon. Art uses the existing
straight-alpha, nearest-sampled HUD renderer. H1–H4 retain their old interpretation;
older clients reject H5. The server continues to hash presentation without
interpreting it. No gameplay, wire protocol or durable schema change is involved.

The Moradon package maps its nine original fixture item IDs to local KO artwork;
these are authored cosmetic choices, not imported historical item definitions.
The importer follows binary-confirmed icon filename selection/extension override
and UV crop. Binary evidence, mappings and verification.


## H6 character previews and item dragging

`N3H6` retains H5 and appends a uint32 preview count (0..8). Each entry is a
length-prefixed unique key (1..64 lowercase ASCII letters/digits/underscores),
then three finite floats: yaw degrees (-180..180), camera pitch degrees
(-80..80), framing multiplier (1..4). The `portrait` image binding references
one of these keys; missing keys, wrong record kinds, malformed counts and trailing
bytes are rejected. H1–H5 retain their prior interpretation.

The renderer poses the package's player idle mesh independently inside the
record's rectangle. Orthographic framing fits its rest-pose rendered vertices;
collision/debug geometry is excluded. The idle animation loops, alpha cutouts and
local depth are retained, and drawing is clipped to the authored area. HUD record
order allows later controls and modal dialogs to cover it. This does not introduce
character customization or equipment-dependent meshes.

Occupied item slots capture on left press and carry a centered icon until release.
The source icon/count is suppressed during capture, with no snapshot mutation.
A release on a compatible slot in the same panel dispatches the existing
server-authorized operation: bag swap, equip/unequip/equipment swap, buy/sell,
storage deposit/withdraw/move. Stock-to-bag uses the dropped destination; bag-to-
stock sells the source item. Multi-item stack transfers/sales and stackable
purchases use the existing quantity prompt; singleton operations send directly.
A short stationary click retains the existing source/destination click adapter.

Drag capture pins source instance/item, absolute indices, pages, bag/storage
revisions, session/self identity and shop identity. Invalid/outside/same-slot
releases restore the source. Revision/identity/page/panel changes, disconnect,
death, focus loss, window leave/resize, keyboard input, right click, modal or
editor capture cancel dragging. World movement is suppressed during capture.
Quantity confirmation rechecks revisions and a captured shop identity; the shared
command dispatcher retains request IDs, retries and server checks. Pending item
requests block new drags until a response. Server snapshots alone move the item.
No ground destruction, player trading, skill/hotbar dragging or preview rotation
controls are implemented by this follow-up.

Binary audit and verification.

## N3H7 tooltips and pickup

H7 retains H6 and adds panel9 for a six-slot pickup window. It appends tooltip
background texture/UV, three finite float layout values (width padding16..100,
height padding8..100, cursor gap0..100), and a uint32 row count1..30. Each row has
top/bottom float offsets within768; tops strictly increase and bottoms exceed
tops. The texture must exist and cannot be the font texture. Malformed and
trailing data fail loading. Older versions retain their existing layout and F
pickup behavior.

Hover reads the current item and instance data for bag, gear, stock, warehouse
and pickup slots. It shows supported stats/requirements, durability, quantity,
weight and applicable buy/sell/repair prices. Unknown flags/bonuses are omitted.
The imported item-info background and row positions size to the content; the
rectangle stays inside the viewport. Active dragging, held clicks and modal
input suppress tooltips. Paging rebinds the item beneath the pointer.

F opens the nearest eligible bundle within the package claim radius, at the
pointer with the binary's150-unit upward offset and viewport clamp; F
closes it. Esc leaves it open: KO's loot window keeps the base key handler
(`0049de00`, PQ-010). Six stable slots hold individual server claim operations. Refreshes
leave holes, so an item cannot move underneath a held pointer. Release must
match the captured operation. Pending claims block another click; terminal
responses permit retries and periodic status queries recover delayed replies.
Range loss, death, disconnect or an empty bundle closes the window. Modal prompts
hide it. All grants still pass authoritative audience/range/life/capacity/weight
and durable claim checks. A ground bundle mesh and click target were added later ([loot visual](loot-visual.md), D-089).

With N3D2, the paperdoll also displays the equipped appearance described in
[the appearance contract](appearance.md). Evidence.


D-081 adds right-click bag equipment: choose the first compatible empty slot, or
replace the first compatible occupied slot. A two-handed blocker is replaced in
its compatible slot. Equipped-item right-click uses the first empty bag slot.
All paths reuse authoritative equip/unequip validation, revisions and operation
IDs; pending actions, prompts and drag capture prevent another right-click.
Bag-to-bag drops use [compatible merging/overflow](inventory.md). Engine30 rest
adds the `rest` action and visibility4/5 to H7 for the original Sit/Stand icons;
[rest](rest.md) defines their replicated state and input behavior.
