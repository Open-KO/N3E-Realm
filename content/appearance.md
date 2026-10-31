# Equipped appearance

Engine29/wire22 adds package-defined cosmetic keys. `appearance.bin` (`N3V1`)
contains a uint32 count (1..128), followed by length-prefixed item IDs and uint32
equipment slots. Keys are one-based record indices. Every mapping must name a
permitted item/slot pair in equipment policy; duplicates are rejected. Gear and
render detail are required. Appearance does not change durable bag identity.
Engine29 chooses progression capabilities from N3P1–N3P5, independently of cosmetics.
Earlier engine/wire pairs retain their previous compatibility rules.

Entity field20 carries equipped keys from the server's committed bag snapshot.
It carries no bag contents, instance serials, balances or durability. Clients
cannot set it. Client validation rejects unknown keys, duplicate equipment slots,
more than16 keys, or keys on NPCs. Unmapped equipment keeps the default artwork.

`N3D2` extends N3D1 after attachment records with an appearance count matching
N3V1. Each entry has a uint32 replacement count (0..16), that many native body
texture IDs, then four ordinary detail geometries. Existing vertex, index, joint,
weight, texture and aggregate budgets apply. Level0 cannot be empty. Triangle
corners must agree on material. Selected entries suppress the named default-body
triangles; removing gear restores them. An empty lower level uses level0.
World and inventory preview use the same composition and animated skeleton.
The server validates cosmetic metadata and hashes; rendering geometry is checked
by the native reader.

The KO adapter explicitly maps local part/plug artwork in
`games/moradon/appearance.json`. Legacy paths, hand joints and default-part IDs
stay out of engine code. Plug positions use the selected bind joint and rigid
skinning; armor retains authored skin weights and four levels. The demo supplies
ordinary blades, shield and torso armor. Equipped-plug progressive LOD, weapon
trails, special materials, robes and other races/items remain fidelity gaps.
Missing mappings fall back to the base body; a missing declared asset fails cook.

Binary grounding and verification.


D-081 re-audits ordinary plug rotations: binary004133c0 builds scale×rotation with
scaled translation;004137d0 applies plug×current joint×character in legacy row
order. The adapter reflects Z once and folds the bind joint into rigid vertices;
current-joint×inverse-bind skinning cancels that bind. No arbitrary rotation offset
is justified by this audit. Original asymmetric fixtures and24 local animation
samples cover right/left blade, shield and two-hand mappings. Weapon-specific
ready/attack clip selection and progressive plug LOD remain separate gaps.
Audit evidence.

## Equipped-item effects (N3E2, PQ-211)

An effect can be drawn on an equipped appearance key: KO's hand-plug weapon
effect, which the plug setter `0045c6e0` attaches for both hands (weapon or
shield) when the item's extension names an fx.tbl effect. The effect lives in
`effects.bin` as an [N3E2](presentation-events.md#appearance-effects-n3e2) record
for the key; N3V1, N3D2, the wire and the server are unchanged, because the
server already projects the public key from committed equipment only. The
client draws the record for every player it draws with render detail, itself
and others alike, so equipping, unequipping or another player's gear change
starts or ends the effect with the key. A client-local `Option.ini`
(`$XDG_CONFIG_HOME/n3e/Option.ini`, `[WeaponEffect] EffectVisible`, default 1;
KO's switch read by `0064b9b0`) turns all of it off; it is read once at start,
as KO reads it, and grants nothing.

The KO adapter fills the record from a mapping row's `ko_item`, a KO item
number (`games/moradon/appearance.json`): the cook reads the item's Item_Org and
Item_Ext rows, chooses the effect id as `0045ccc0` and the setter do, looks up
the main bundle (id) and its tail (id + 1) in fx.tbl, picks the trace colour by
element (`0045cb5e`) and turns the plug file's own FX mesh into three copies
(`00415910`). A row whose item has no effect id, or whose plug has no FX mesh,
draws nothing, as in KO; an armour part row may not name one (`0045cd90` has no
effect path). The Moradon blade is KO item 120110048, the Short Blade on the
Burning line at +8, so it glows with `fire_sword0_1.fxb`; a +7 row (120110047)
would not. Evidence.

Since PQ-376 (D-200) the effect is drawn in 1298's order. KO queues every FX
mesh copy and every tail spark in one alpha list that it sorts far to near
(`0043dd80`): a copy at the eye distance to its matrix's translation plus the
FX mesh's y extent (`00415910`), a spark at the eye distance to its quad's
first three corners (`004840b0`). The cook writes each 1298 effect an
[N3E5](presentation-events.md#alpha-sort-records-n3e5) sort record (the plug
origin and that extent), and the client then sorts each copy and each spark on
its own. Of the four 1298 weapon effects only poison shows it (the others
blend with destination ONE); the Moradon blade is fire. The 2233 skeletal-plug
effects keep n3e's order.
Evidence.

## Equipment glow (N3E3, PQ-315)

A 2233/2145 addition: the 2233 client (PQ-314, a secondary reference) makes an
equipped part or hand plug glow when its item extension asks for it, and the
pinned 1298 client has nothing of the kind. Each tick `0056ea30` (from
`CPlayerBase::Tick` `0057b3a0`) advances one timer per player and, for an
extension whose Item_Ext column 8 is 11 or 12, writes the material emissive
(a pulse or 1.0) and MODULATE or MODULATE2X from column 45 % 100: 0-4 pulse at
1x, 5-10 steady at 1x, 11-20 pulse at 2x, 21 and up steady at 2x; the pulse
rises to 1 over 1 s, holds to 3 s, falls to 0 by 5 s and restarts past 5.5 s.
`CN3CPart::Render` (`0042cf30`) keeps that emissive and doubles the texture
product at 2x. In n3e the glow is an
[N3E3](presentation-events.md#equipment-glow-n3e3) record on the appearance key
(colour, modulate, wave and timing); the server and the wire are unchanged, so
the server stays authoritative for the key, and the client draws it the same
for itself and for other players. `Option.ini` `[Addition2233]
EquipmentGlow=0` turns it off (default 1).

KO's rules stay in the cook (`tools/assetc/ko_glow_2233.py`), which runs only
with `ko_bake.py 210 --features --glow-2233` (`tools/play-moradon --glow-2233`)
and reads the player's own 2145 tables through the pinned unpack. A mapping
row names a 2145 item (`glow_2145_item`); the cook applies 2233's item rule,
refuses an extension row whose Item_Ext column 3 names another base item (n3e's
own mapping guard: the column is `dwBaseID` in the source, source-only; no
2233 path that tests it was found, an inference within the scans' limits; the
guard keeps a demo row from claiming a 2145 item number whose extension row
belongs to another base, such as 120010884, since which item numbers a
2145-era server issues is unread;
PQ-318),
refuses the row unless its artwork is that item's model,
and refuses part 2 and a `.n3chrplug` named as a rigid source (a skeletal plug row, below, glows as its
own 2145 item since PQ-337). The Moradon Round Shield is 2145 item 170251015 (Item_Ext_36
row 15: attribute 11, column 45 = 15), a pulse at 2x. The 1298 items have no
glow attribute; the demo's blade and two-hander artwork reach glowing rows only
through rows of another base item (`[Test]Raptor`), which the guard refuses, and
its armour has none (2145 armour has its own artwork, below). Evidence.

A mapping row may also name `glow_2233_source`, a hand plug that only the
`--glow-2233` cook draws in place of the row's `source`
(`ko_glow_2233.artwork()`; PQ-320). The item, its slots and the server's
appearance key stay the row's, so the server still decides what is equipped and
sends the same key; only the glow package's mesh for that key changes, and the
artwork guard then checks the replacement against the 2145 item. The row must
be a hand plug row with `glow_2145_item` and no `ko_item` (a weapon effect
belongs to the default artwork's item). Moradon's two-hander uses it: the glow
package draws it as Durandal (`Item/1_2631_00_0.n3cplug`), 2145 item 126311011
(Item_Org 126311000, Item_Ext_26 row 11: attribute 11, column 45 = 11), a pulse
at 2x. Durandal is class 22 like the Two-Handed Sword it replaces, so 1298's
ready-pose choice (`0045bfe0`: class 22 gives 50) is the same. The default
cooks never read the field.
Evidence.

Such a row also names `glow_2233_label` and `glow_2233_icon`, the replacement's
name and inventory icon (`ko_glow_2233.presentation()`; PQ-321). They must be
those of a 1298 Item_Org row whose model is the replacement's (column 7 the
model, column 3 the name, column 8 the icon), so a row cannot give its artwork
another item's name or icon. The glow cook alone writes the label into the glow
package's own inventory definition (`inventory.bin`, which the server's
inventory policy loads and the client's inventory slots and tooltips read)
and the icon into its own item icon map, so the server stays the authority for
the item and only that package's copy of the data changes. Moradon's two-hander
is named Durandal there and drawn with `UI/ItemIcon_1_2631_00_0.dxt`, the icon
of 1298 Item_Org 126310000 (model and icon 12631000). The 1298 client builds
that path in `006157b0` (KnightOnLine.exe, binary): `UI\ItemIcon_%.1d_%.4d_%.2d_%.1d.dxt`
from the extension row's icon when it is non-zero, else the Item_Org icon; every
1298 Item_Ext_2 row (Durandal's extension table) has a zero icon (local-asset).
The default packages keep "Two hand blade" and the Two-Handed Sword's icon.
Evidence.

### 2145 armour parts (PQ-319, D-190)

The same cook carries 2145 armour from `games/moradon/armour-2233.json`
(`tools/assetc/ko_armour_2145.py`): the KO race and class of the package's one
character profile, the equipment slots the package adds and the inventory
window area each one is, and the 2145 item numbers. Each part is drawn as the
2233 client names it (`009b3fc0` with `0092fd30`: the Item_Org model column
plus race × 1000, for a class the race allows, so `Item/2_0802_10_0.n3cpart`
for a race-2 upper garment of model 20800100; 1298's `006157b0` names armour
from the item number, which no 2145 file matches), read from the player's 2145
Item pack, on the part slot its attach byte gives (5–9: upper 0, lower 1,
helmet 5, gauntlets 3, boots 4), hiding that body part as any part row does;
a part whose extension has attribute 11 or 12 gets its glow record. The cook
refuses an item the profile may not wear by 2233's rule (`005e5a90`: need-race
and need-class bytes; `00930030`: the item kind per class; 1298's `004a1750`
has the same class groups), an item for which `009b3fc0` names no artwork, a
definition whose race is not the player model's, and an item whose inventory
area (1298 `004a1ed0`: attach 5 area 4, 6 area 10, 7 area 1, 8 area 12, 9 area
13) is no package slot. Each part is a package item worn only in that slot,
granted at start (no shop, no payment path), weightless, without wear or stats;
the server validates each equip against the slots as for any item, and since
every character of the package shares the one profile no runtime class rule is
needed. Its label is 2233's tooltip name (`005aa8e0`: the Item_Org name and
"(+column 45 % 100)" for attribute 11, "(+key % 10)" for 5; the Item_Ext name
for 3, 4, 6 and 12); the kind line under it (a text by attribute from the
player's 2145 `Texts_us.tbl`, a set item's for a need-race byte of 101–199:
"(Set item)", "(Reverse set item)"; PQ-350 joined it to the label) is since
PQ-354 its own centred tooltip line, both in the colour 2233 gives the
attribute (a set item's: ff83a6 for attribute 11, else d20000), carried as the
item's [tooltip head](inventory.md#item-tooltip-heads-n3ih-pq-354-d-194); its
icon is the PQ-338 rule's.
Moradon's glow package carries the rogue Krowaz Assassin set on both upgrade
paths (PQ-346, PQ-350): normal +10 (2145 items 248001020–248005020, Item_Ext
13–17 key 20, attribute 5: no glow record), reverse +1 (258001001–258005001,
Item_Ext 37–41 key 1, attribute 11, column 45 = 1: a pulse at 1x) and reverse
+30 (258001030–258005030, key 30: a steady light at 2x), as
`demo:item/krowaz_<part>_normal10`, `_reverse1` and `_reverse30`, for
KO race 2 (the male Tuarek model) and class 108, in four slots it adds (head,
lower body, hands, feet). The normal line (Item_Ext 13–17) has no glow row.
The 20 items of the package's two 2145 definition files, all granted at
start, need more than features.json's 32-slot bag beside the progression's
reward slots, so its bag has 56 slots (two pages of the HUD's 28-slot window). A part whose skin has a corner without a normal takes
its triangle's normal (PQ-281's rule). Since PQ-348 the parts draw with their
own render state (below).
Evidence.

### Part render states (N3D3, PQ-348, D-191)

KO draws an equipped armour part with its own material's render state. The
1298 armour setter `0045cd90` loads the part into the character's part vector
(`CN3Chr` `0041b6d0`; the file load `00438c40` calls the part's `00412180`,
which reads the material), and the character render `004196a0` draws each
part of that vector, in slot order, through `00412570`: alpha blending with
the material's source and destination factors (render flag 1), culling off
(flag 4), lighting off (`0x40`), with the device's alpha test on (GREATER,
reference 0: `0043ade0`), so a texel of alpha 0 is never drawn and every
other texel blends by its alpha (PQ-265's reading of the same functions). The
2233 part draw `0042cf30` sets the same states and then, for a glowing part,
the emissive and the 2x modulate in the same draw; the colour op changes, the
alpha does not.

In n3e an appearance key may carry a render state in `render-detail.bin`
`N3D3` (N3D2 with, after each entry's four geometries, flags 1 blend and 2
double-sided, the alpha reference and the two blend factors). The client draws
that key's triangles with it, in the same order as before and with depth
writes on, for itself and for other players, together with its N3E3 glow: the
alpha test against the reference, the blend with the factors, both faces when
double-sided; a key that does not blend writes alpha 1, as every N3D2 key
does. The KO cook writes N3D3 only when a part row's state is not opaque: a
1298 or 2145 part row takes its part's state (`ko_appearance.part_state`,
reference 0), a hand plug and a skeletal plug row the detail draw's own
cut-out at alpha 0.5 (`DETAIL_CUT`: what N3D2 draws for every key), and an
unlit part is refused on this path until a check draws one (PQ-280). Every
default package is N3D2 and cooks as before; the opt-in `--glow-2233`
package's five Krowaz parts carry blend src_alpha / one_minus_src_alpha and
both faces, so the helmet's crest and the lower garment's fringes blend by
their texture alpha. Not carried yet: the inventory preview (KO draws it
through the same character render, `00457420`; PQ-352) and KO's draw order
inside a character, parts in slot order and then the plugs (PQ-353).
Evidence.

## Attached characters (N3AT, PQ-328)

A 2233/2145 addition: the 2233 client (PQ-314, a secondary reference) draws
wings, fairies and emblems as whole animated characters attached to a player
(its `CPlayerWing`, PQ-325); the pinned 1298 client has none. Each tick
`0056a710` places each of the two attached characters on its player joint and
picks its clip from the player's state, and `00569590` lights it with a pulse
at 2x on one timer per player that each attached slot advances; `00568f30`
draws slot 0 only while `[Effect] Wing` is on.

What a character wears stays the server's: a cospre slot is one more
[equipment](equipment.md) slot and its items fit only there, so the server
validates each equip against the package (`incompatible_slot` otherwise),
commits the bag in Postgres and projects the public appearance key from
committed equipment, as for every key. What a key attaches is package
presentation, `attachments.bin` (`N3AT`), cooked from the manifest's
`attachments` record (`tools/assetc/attachments.py`):

```json
"attachments": {
  "clock": {"per_attachment": true, "rise": 1.0, "hold": 3.0, "fall": 5.0, "period": 5.5},
  "color": [1, 1, 1],
  "entries": [{"item": "demo:item/wing", "slot": 4, "joint": 1, "scale": 1.0, "group": 0,
               "optional": true, "emissive": true, "modulate": 2, "lit": "all",
               "clips": [{"source": "wing-idle.bin", "duration": 1.0, "blend": 0, "loop_blend": false,
                          "markers": [-1, -1]}, "... walk, attack, death"]}]
}
```

- `item`/`slot` name an appearance row, so the entry is that key's (1–16
  entries, each key once).
- `joint` is the wearer's skin joint the model is placed on (the wearer's
  frame times the joint's posed matrix, then `scale`); the client refuses a
  joint the player skeleton lacks.
- `group` (0–15): a wearer draws at most one entry per group, the one whose
  key comes last in its key list (2233 replaces the character in an occupied
  slot).
- `optional`: drawn only while `Option.ini [Effect] Wing` is on (default 1).
- `lit`: `"all"` or a count of leading indices drawn with the shade (a whole
  number of render runs); `emissive` adds colour × intensity there, then
  `modulate` (1, 2 or 4) scales the texture product, as the equipment glow does.
  Since PQ-359 (D-195) the model takes its wearer's equipped-part light (n3e's
  `0.35 + light × max(N·n(0.35, 0.85, 0.4), 0)`), as 1298's `004196a0` lights
  a character's parts and plugs with the same device lights; before, it took
  the looks models' light (0.15 floor, 0.35 for the parts). The light terms are n3e's own. KO's three-light rule (PQ-360) is queued for the KO packages as PQ-363.
- `clock`: the pulse (intensity t / rise up to rise, kept, falling from 1 at
  hold to 0 at fall, kept, restart past period) on one clock per wearer from
  its first draw; `per_attachment` advances it once for each of the wearer's
  attachments every frame (2233: two attachments pulse twice as fast), else
  once. A hidden optional attachment still advances it, as in 2233.
- `clips`: four N3S1, N3SM, N3SI or N3SJ clips sharing atlas, skeleton and mesh
  (as an [NPC looks](npc.md) entry), played for the wearer's state: idle
  (standing, ready, sitting), walk (any movement), attack, death. The model is
  `attachment-<i>.bin` in the looks model format, so the package is engine 38
  at least (39, 40 for the other kinds).

Both readers check the table and the model headers; the client also checks the
joint and the lit count against the skeleton and mesh. KO's two quirks, the
double rate with two attachments and the first part lit at 2x with no emissive
when the table's column 3 is 0, are reproduced as package choices (D-186), not
corrected. No KO wing is cooked yet: the 2145 parts sit in its Item pack,
which `tools/ko-reference/pack_2145.py` reads (PQ-308), and
`tools/ko-reference/anim_2145.py` reads its enciphered clip tables (PQ-330).
The opt-in 2145 cook is PQ-331 and NPC attachments PQ-332. KO sells these items; a package grants them
(the fixture's are starting items, offered by no shop) and no payment path
exists. Evidence.

## Skeletal plugs (N3AT plug entries, PQ-317)

A 2233/2145 addition: in the 2233 client (PQ-314, a secondary reference) a
hand item whose Item_Org row has `+0x90` set (2145's column 40, by inference)
loads a `.n3chrplug` instead of a `.n3cplug`: a whole animated character on
the hand joint (`CN3ChrTypePlug`; the 2145 Azagai bow is one). `00574830`
gives it a uniform scale of its scale y × the player's height / 1.8 and the
looks row's hand joint; each frame `00434980` places the inner character at
the plug matrix (`0042d800`) × that joint's matrix and plays its clip on its
own clock, the clip `0042df00` maps the wearer's clip to (0–13 → clip 0
looped, 14–15 and 26–103 → 1 once, 16–25 → 5 once, …; `00432760` keeps the
playing clip for the same index). The pinned 1298 client has none.

In n3e a skeletal plug is an N3AT entry with `plug` in place of `optional`,
`emissive`, `modulate` and `lit` (tools/assetc/attachments.py):

```json
{"item": "demo:item/bow", "slot": 1, "joint": 1, "scale": 1.0, "group": 2,
 "plug": {"placement": [0, -0.8, 0, 0.05,  0.8, 0, 0, 0.1,  0, 0, 0.8, -0.05],
          "clips": [{"kind": "state", "id": 0, "slot": 0, "once": false},
                    {"kind": "state", "id": 2, "slot": 1, "once": true},
                    {"kind": "combat", "id": 0, "slot": 1, "once": true},
                    {"kind": "skill", "id": 0, "slot": 2, "once": true}]},
 "clips": ["... four clips: the model's slots 0-3"]}
```

- `placement`: rows of the 3×4 matrix taking the model's frame into the
  joint's (column vectors); the model is drawn at the wearer's frame × the
  joint's posed matrix × placement × `scale`.
- `clips` (the map, 1–64 rows): `kind` `state` (a wearer pose state, 0–9:
  idle, run, attack, death, walk, backward, ready, sit-down, sitting,
  stand-up), `combat` (a combat-animation clip) or `skill` (a skill
  animation); `slot` the model clip it plays; `once` plays it once and holds
  its end, else it loops. The wearer's drawn clip is its casting skill's
  animation while it casts, else its combat clip, else its pose state. A row
  naming another slot than the playing one restarts there; the same slot, or a
  clip with no row, keeps playing. The model starts on slot 0, looped. A slot
  plays at its own clip's rate: a wearer's stretched cast clip (N3RC) does not
  stretch it, as 2233's plug tick `00434980` sets its inner speed to 1.0 and
  2233's cast stretch `005719a0` rewrites only the wearer's clip (PQ-424). The map
  is applied to every wearer: 2233 applies it to the local player only and
  leaves other players to an uninitialised byte (correction, D-188).
- A plug entry is always drawn, never lit or emissive, and neither takes nor
  advances the wearer's pulse clock. ("Lit" here is the N3AT pulse's `lit` indices. The
  model is drawn with lighting: since PQ-359 (D-195) with the wearer's part
  light, as every N3AT model is. PQ-358 found that 1298 lights rigid plugs with its parts'
  light set-up and 2233 lights other players' plugs and bodies with one shader
  light; for 2233's local player the two take different paths, and whether
  their lights match is still unread (PQ-360 read the shader light only).) Its key's N3D2 appearance mesh may be
  empty (a skeletal plug has no rigid mesh); any other key's may not.
- Its key's equipment glow (N3E3), when it has one, shades the whole model on
  the wearer's glow clock, behind `[Addition2233] EquipmentGlow` (PQ-337): in
  2233 `0056ea30` writes the plug's emissive and 2X flag and, for a skeletal
  plug, `0042de90` keeps the colour, which `00430f40` copies with the 2X flag
  into every inner part each frame (`00434980`).

What a character wears stays the server's (equipment slots, validated equips,
committed bags, projected keys). The KO cook is opt-in: `ko_bake.py 210
--features --glow-2233` (`tools/play-moradon --glow-2233`) adds the rows of
`games/moradon/skeletal-plugs-2233.json`, each checked against the player's
2145 Item_Org (column 40 set, the plug file named for its model, the hand slot
its attach point gives), as package items worn only in that hand
(`tools/assetc/ko_chrplug_2145.py`): the `<selfname>'s Azagai` (2145 item
1110532000) as `demo:item/azagai`, left hand, joint 7. It reads the plug from
the 2145 Item pack (PQ-308), its inner character to the eighth field as 2233
does (the trailing copy of the plug record is ignored), and its enciphered
clip table through `anim_2145.to_1298` (PQ-330); the model's slots are the
plug clips the map reaches (breath, attackbreath, magic, breath again), each a
looks clip with the part's render state (the bow's alpha blend and double
side); the placement is the plug matrix at the joint with the height / 1.8
factor n3e's rigid plugs use; the map is `0042df00` of the KO clip each
player clip and skill animation was cooked from. That package is engine 39,
wire 30. Evidence.
Since PQ-347 each grade worn alone in the left hand also selects the combat
profile 1298 gives a kind 70 bow (Item_Org column 11): ready clip 92, the
archery row's clip 26 as the attack, 1450 ms
([combat animation](combat-animation.md#timed-profiles-and-moving-attacks-n3a5)).

Since PQ-337 the file also names upgrade grades of the bow on the same plug
and one cooked model; since PQ-350 on both paths (PQ-346): the normal +10
`demo:item/azagai_normal10` (2145 item 1110432510, its own Item_Org row
1110432000, whose column 40 is also 1 and whose model is the same) and the
reverse +1, +10 and +30 `demo:item/azagai_reverse1`, `_reverse10` and
`_reverse30` (1110532501, 1110532510, 1110532600). 2233 reaches an item
number's extension row by key (`0052f660`: num / 10⁹ × 1000 + num % 1000 in the
base row's table), so the normal +10 reaches Item_Ext_9 row 1510 (attribute 4:
no glow) and the reverse grades Item_Ext_33 rows 1501, 1510 and 1600:
attribute 12, column 45 = 1, 10 and 30, so a pulse at 1x and a steady light at
1x and at 2x (the plain row 1000 has neither glow nor effect). The cook gives a
row of attribute 11 or 12 its own item as `glow_2145_item`, and labels a grade
as 2233's tooltip head does (`005aa8e0`: the Item_Ext name for attributes 4
and 12, which a normal and a reverse grade share, then the kind line "(Unique
Item)" or "(Reverse unique item)" that tells them apart; PQ-350), since PQ-354
as the item's [tooltip head](inventory.md#item-tooltip-heads-n3ih-pq-354-d-194):
the name gold (dcc77c, normal +10) or orange (ffad4d, reverse grades) with
"<selfname>" replaced by the viewer's character name, the kind line under it
in the same colour, the plain bow's name white. It also
resolves each row's weapon effect by 2233's rule (`0056bb50`, else Item_Ext
column 5; fx.tbl id and id + 1): 32120 and 32121 for all four grades. 2233 draws that effect on a skeletal plug
as on any plug (`CN3Chr::Render` → vtable `+0x20` `00433af0` → RenderFX
`004304c0` on the embedded FX mesh at the plug matrix on the hand joint).
Evidence.

**Upgrade paths and glow grades (PQ-346, research).** KO 2145 data has two
upgrade paths. A normal grade is a row of a 10-row block on Item_Ext 0–21
(attribute 5, or 4 on a unique's own line), its grade the key % 10 (10 at 0);
the 1298 game server steps the item number by its recipe's GiveItem, keyed by
the number % 1000 (`004bdd8d`, binary; +1 per grade in the OpenKO recipes). A
reverse grade belongs to a separate Item_Org row on a reverse table (Item_Ext
24–41): 30-row lines whose column 45 is the grade 1–30, attribute 11 (a generic
line) or 12 (a unique's own line). Reverse +1, +5, +11 and +21 carry the stats
of normal +7, +8, +9 and +10, and +22 to +30 go beyond (local-asset). 2233's
`0056ea30` glows only attributes 11 and 12, and its four bands (1–4 pulse 1x,
5–10 steady 1x, 11–20 pulse 2x, 21+ steady 2x) are those four normal grades,
so a normal +10 does not glow there and the steady 2x starts at reverse +21.
For the Azagai's own lines (attribute 4 / 12) 2233 draws the same weapon
effect, hit effect and trail colour at a normal grade and its reverse
equivalent (effect 32120 from normal +6 and reverse +1; poison above 63 on the
rows compared, a magenta trail), and for the Azagai and Krowaz rows compared
the same durability dust (column 13 and Item_Org column 20 equal). Other lines
can differ: the trail-colour test in `00574830` (PlugSet; the hit effect
`00571520`, the dust `005756b0`) is attribute-dependent (an element of 1–63
colours only attributes 4, 6, 11 and 12), and the generic Viper bow line's
reverse +1 to +4 carry effect 12120 where normal +7 has none (Item_Ext_33 keys
31–34 against Item_Ext_9 key 47, local-asset).
The Azagai's normal +10 is 1110432510 (Item_Ext_9 key 1510), the Krowaz
set's 248001020–248005020; the glow package carries them, and reverse +1
and +30, since PQ-350 (15 glow records within N3E3's 16; the cook refuses a
17th). Evidence,
PQ-350.

Since PQ-339 the cook draws it. Both bundles are FX bundle versions 6 and 4,
which the 1298 reader refuses, so `ko_fx.bundle(data, '2233')` reads them as
2233's bundle and part loads do (`0057f0b0`, `00589370`, the particle,
billboard, mesh and fourth part loads), and `weapon_effects` gives each grade's
key an N3E2 record: 32120's billboard frames (15 DXT5 textures from the
player's 2145 fx pack, decoded only on this path) on three copies of the
`.n3chrplug`'s FX mesh at the plug placement on joint 7, as PQ-211 draws a
rigid plug's. A field 2233 added is drawn only at the value that leaves
RenderFX's path as 1298's, else refused; `[WeaponEffect] EffectVisible=0`
hides the effect as for any weapon.
Evidence.

Since PQ-341 the tail 32121 is drawn too, as the effect's N3E2 tail clip
(`ko_fx_tail_2233`; 1298's tail path unchanged). RenderFX moves the two tail
copies InitFX (`00437510`) made to FX mesh box points every frame and ticks and
draws them; the cook samples the bundle's parts at 30 Hz as 2233 ticks them:
two mesh parts, each a CN3FXShape (a small ball with a blinking scale track,
its texture found in the shape's folder) turned at -9 or +9 rad/s about x, y
and z (`004674c0`, Rx × Ry × Rz), scaled by the part's scale, its keys (the
frames wrapping, `0059a6f0`) and the bundle's target scale; and four particle
parts, two emitting toward points 3 and 2 m below (emitter kind 2, `005915e0`:
the velocity points from the particle to the turned target and takes no scale)
and two spreading (kind 1, as 1298's). A link is 10 s, the shortest that holds
whole frame cycles of both meshes, so the clip is 20 s (the client's clip bound
is now 20 s); both grades share the clip. Fields the cook cannot confirm are
refused by name.
Evidence.

Since PQ-342 the tail's particles thin with the camera's distance as 2233's
particle tick (`00592900`) thins them, unless a part's version-6 byte is set:
each tick it sets the live count to the part's pool within the near distance,
else trunc(pool × (far − d) / far) (negative past far), and emits (`00592740`)
only while the live particles are at most that count; live ones are never cut,
and none are drawn at a count of 0 (`0058e880`). The near and far distances
are the version-9 values, 40 and 70 m for the puffs (pool 20) and 20 and 50 m
for the sparks (pool 11; at 30 m 2233 keeps 4), or 10 and 30 m when zero. The
cook writes every emission of such a part as a candidate and an N3E4 rule on
its batch
([N3E4](presentation-events.md#tail-particle-distance-rules-n3e4)); the client
takes each sample's candidate by that count at the camera's distance to the
link's newest tail point, counting the taken live ones the link before it in
the chain still draws (one 2233 tail copy, one live list), and draws the ones
it took. Within near a chain's first link draws exactly the PQ-341
particles; after a 10 s link handover a part that fills its pool (the puffs'
texture-193 part) takes other candidates for the rest of that link's
emission, within one particle of PQ-341's count once the older link's
particles are gone. The local player's camera (at most 10 m in Moradon) is always within both nears, another player past 20 m loses sparks.
The cook refuses a ruled part with a batch above 1, a distance past 1000 m or
not finite, or a texture and render state another particle part shares.
Evidence.

The 1298 client has no icon for a 2145-only item, so since PQ-338 the same cook
adds each skeletal plug item to that package's own HUD item icon map with its
2145 icon by the 2233 rule (`009b3fc0`: the Item_Ext row's icon when non-zero,
else the Item_Org row's, the first field printed `%.2d` for an item / 10⁹ of
1–3), read from the player's 2145 UI pack: the Azagai's is
`UI/ItemIcon_11_1043_20_0.dxt` (Item_Org column 8, 111043200), drawn in the
equipment and bag slots as any icon. It is client presentation only; the
server's item and rules are unchanged. Evidence.

The cook's plug reader has a 2145 layout since PQ-334
(`ko_appearance.read_plug(..., '2145')`). It reads 2233's `CN3CPlug` (`004489c0`,
`00448d80`): after the FX mesh, while bytes remain, a texture block (a count;
when it is 1 or more, 4 bytes and five trail texture names of 0–259 bytes). The
skeletal plug reader shares it. The 1298 layout stays the default, because
1298's `00415020` reads nothing after the FX mesh. All 397 2145 Item-pack
`.n3cplug` read in this layout, 54 of them with the block, and their FX meshes
now reach the mesh reader. A block that names a trail texture or sets its 4
bytes is refused until PQ-335 draws them. Nothing new is drawn and no package
changes. Evidence.

Not drawn yet: the coloured swing trail the trace colour is for (`00419060`),
the hit spark (fx.tbl id + 2), the inventory preview's effect, and the unique,
bow and Viper effects, whose bundles n3e's FX reader refuses (queue items after
PQ-211).
