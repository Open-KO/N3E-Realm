# Overhead names (N3H9)

N3H9 retains the complete N3H8 payload and appends 828 bytes:

- Four finite f32 values: camera distance cutoff (0,1000], height padding [0,1],
  screen gap [0,32] pixels, seated height fraction [0,1].
- Three u32 RGB colors: local player, other players, NPCs.
- Two font records (regular player, bold NPC): u32 texture index, line height,
  atlas top; 95 finite f32 advances for printable ASCII32–126. Each texture is a
  512×192 RGBA atlas, separate from the ordinary HUD font. Cells are32×32 in16
  columns, with glyph origin x=2 and baseline y=22. Line height is1–32;
  top+height≤32; advances are(0,28].
- Two model profiles (player, NPC): finite f32 positive height≤100 and u32 root
  node<64. Each root must exist, have no parent and be a joint in player-idle.bin
  or scene.bin respectively.

Integers are little-endian; no native structure layout is serialized. Native
loading rejects invalid references, metrics, roots, truncation and trailing data.
The existing release digest covers the HUD. Engine33/wire26 and storage remain
unchanged; older clients reject H9, and current clients still accept H1–H8.

Names follow the displayed actor position (prediction/interpolation), use model
height×(1+padding), and, while sitting, add the current animated root Y minus
height×seated_fraction. Screen placement is integer projected X minus half the
rounded measured advance sum, and integer projected Y minus line height and gap.
Names retain case, draw black copies at(-1,-1)/(+1,+1), then foreground, before
HUD panels. Fonts keep their pixel size at different window sizes. Names must be
in front of the camera, inside the camera clip range, within the distance cutoff,
and at least partially inside the viewport. Character LOD rejection also rejects
the name. Ordinary local-player names are enabled. H1–H8 keep the prior fallback.

Moradon settings live in games/moradon/nameplates.json. Offline ko_nameplates.py
cooks 16px Liberation Sans regular/bold as explicit substitutes for the binary's
Arial12-point at96DPI. It records font file hashes and each skeleton's height:
the top of its joint box, an axis shorter than 0.5 m grown by 0.25 m at each
end, as KO's joint bounds routine `0041c300` stores it (character `+0x12c`) and
the name callbacks read it (actor `+0x17c` × scale): the NPC callback
`00459820`, and the self (`0046b5a0`) and other-player (`0046ea90`) callbacks
through `00459fa0` (PQ-301, binary). The joints are taken at frame 0, which is
inference from KO's call order (the constructor and release zero the frame
`+0x1dc` and the looks set runs the joint set before it starts a clip; the
reused-character path is not traced;
evidence).
Tuarek height is 1.7985 m, worm 0.5256 m before runtime scale (until PQ-301 the
cook took the box's Y span, 1.9377 m and 0.7385 m).
This package uses unit scale. No installed font is required at runtime.

Name display toggle (PQ-014): the package's `names_toggle` action flips a
session flag; while it is off, names of the classes the package's input table
lists under `names.hides` are not drawn (also in the H1–H8 fallback labels). The
start state is `names.shown`; nothing saves it. Moradon binds O, starts shown and
hides `self` and `players`: KO's O flips `006d42e4` (a static 1), which the self
(`0046b5a0`) and other-player (`0046ea90`) name callbacks read and the NPC callback
(`00459820`) does not. KO still draws a hidden player's label in two cases (PQ-164,
evidence).
The first is a balloon (`+0x2f4`), for self and others: chat of type 1, 5 or 14
spoken within 4 m sets it (`005cac80` → `00456d90`) for length × 0.2 s. The
second is party membership on other players (`+0x7dc`, set on each tick of
the party window, `0051c5b0`: 1 for the first member, 2 for the rest). The same
marker draws party names yellow (`0046e840`), keeps their label fonts at any
range (`00470900`) and lifts the 48 m draw limit outside Zones.tbl keys 320 and 330 (`dungeon_b1th`, `dungeon_b2th`)
(Zones.tbl column 23). n3e has no balloons (PQ-168); the party rules are
package data since PQ-166 (below).

Label lifetime by range (PQ-167,
evidence):
KO keeps another player's label only near the local player. The player-manager
tick (`00470900`) measures the 3-D distance from the local player's position
(`[00818794]+0x98`, not the camera). Below 10 m it builds the name font and, when the
player has a clan (`+0x4d0`), the clan font (`0046e840`); above 20 m it frees them with the info line and balloon
(`00456b40`); from 10 to 20 m it keeps them. Without the name font the name is
not drawn, so the 48 m camera limit matters only on top of this. Exempt (built
on every tick, never freed by range): party members, clan duty (`+0x4f0`) 1 or
100, and two clan-ID comparisons (`00616770`, `006167c0`). The user-in handler
builds the name at once only for those duties or flag byte `+0x4f4`; others wait
for the next tick.

n3e applies the rule from package data (PQ-169,
evidence):
the input table's `names.lifetime` (`N3I3`, CONTRACTS "Package input map") gives
the measuring point (`self`, the local player's displayed position, or `camera`,
the eye), the acquire and release radii and the exempt classes (`party`). Every
frame the client measures each other player's displayed position in 3-D; it makes
the label once that distance is below `acquire` (or not a number, as KO's
comparison does), drops it once it is above `release`, and leaves it alone in
between. Party members keep it at any range. A player who leaves view or a new
session forgets it. The label is a gate on top of the toggle and the camera
`distance` limit, for the N3H9+ names and the H1–H8 fallback labels alike.
Moradon: `self`, 10, 20, `party`. A package without a lifetime (the demo) keeps
every other player's label. Self and NPC names are not affected (NPC range:
PQ-170, below). Not mapped: the clan duty and clan-ID exemptions (n3e has no clans),
and the clan font, info line and balloon KO frees with the name (n3e has none of
them).

NPC label lifetime (PQ-170,
evidence): the same
tick (`00470900`) walks the NPC map (`+0x2c`, filled by NPC-in `005cd620`, which
builds no label). It builds an NPC's name font below 10 m of the local player's
position (3-D, or a NaN distance), frees it while the distance is at least 10 m
but under 20 m, and leaves it alone at 20 m or more. The release test is the
reverse of the player loop's, so there is no 10–20 m hysteresis: in ordinary
movement an NPC's name shows only within 10 m (an inference: it needs a tick
for every 10 m of relative movement, and the tick rate is not decoded). It survives beyond 20 m only when
no tick samples the 10–20 m band on the way out (a jump), and is then drawn up
to the 48 m camera limit; that case is a BINARY-POLICY correction candidate.
An NPC in state 5 (death, a source name) moves to the corpse map and loses its label. NPCs
whose `NPC_Looks.tbl` column 36 (looks row `+0x14c`) is 1 (town service NPCs,
guardian stones and a few others; 30 of 163 rows) are refreshed on every tick
and skip the 48 m limit (`00459856`), so their names show at any range.

n3e applies the NPC rule from package data (PQ-174,
evidence): the
input table's `names.npc_lifetime` (`N3I6`, CONTRACTS "Package input map") gives
the measuring point, the acquire and release radii, the release `rule` (`band`:
dropped only while `acquire` <= d < `release`, kept at `release` or more;
`beyond`: the other-player rule), `always` (every NPC of the package keeps its
name at any range and skips the camera `distance`) and `drop_dead`. Every frame
the client measures each NPC's displayed position in 3-D from the measuring
point, so an NPC entering view has no name until a frame finds it under
`acquire`. With `rule` `band` the stale far name of KO's jump case is reproduced:
a name kept at 20 m or more stays until a frame finds the NPC in the band again.
With `drop_dead` an NPC loses its name once its death clip has played (the n3e
counterpart of KO's state 5, which KO enters when the dying clip that starts at
the death packet ends: `005cf620` → `0045acc0` sets state 4, and the
animation tick `00457d90` applies the next state 5 at `00457e57`); while it dies
the name follows the range rule, as in KO. A package without the clip (the
stand-in model) drops it as soon as the NPC is dead. The KO bake sets `always`
from the `NPC_Looks.tbl` row of the package's template (`K_MONSTER` `sPid`; the
looks key NPC-in reads at `005cd699`, which the servers fill from `sPid` for
`K_MONSTER` and `K_NPC` rows, PQ-176,
evidence): the Moradon worm (`sPid` 700, local-asset
OpenKO row; row 700 is `chr\mob_worm.n3joint`) has column 36 = 0, so Moradon is
`self`, 10, 20, `band`, `always` false, `drop_dead` true and worm names appear
only within about 10 m of the player. The demo has no NPC lifetime and keeps
every NPC name. `always` marks every NPC of the package; since PQ-253 (engine
38, [content/npc.md](npc.md#per-template-presentation-n3lk-engine-38--wire-30))
a looks entry's `name_always` flag marks the NPCs drawn with that entry, as
KO's flag is per looks row (read through the actor's row pointer `+0x274`).
An NPC keeps its name at any range and past the camera limit when either flag
is set; the looks flag lifts the camera limit even without `npc_lifetime`.

Operator NPC info line (PQ-175,
evidence): KO's
NPC label refresh (`00465070`, slot `+0x14`) adds a green (`0xff00ff00`) line
`ID(<wire ID>) : TYPE(<byte +0x7c0>)` (`006d44f0`) when the local player's
`+0x4a4` is 0. Of the instructions that address that field directly, only
`MsgRecv_MyInfo_All` writes it from the server (`005c96f7`); the base
constructor and release set 1. The source calls 0 `AUTHORITY_MANAGER`. The NPC
callback (`00459820`) draws the line above the name and clan lines, with the
same black outline. So only an operator's own client shows it, above NPCs
whose name is drawn. `TYPE` is 0 unless opcode `0x5d` sets the byte. PQ-179
(evidence)
found its producer. The only trigger found (the search is not exhaustive) is an
operator's chat command `+actpursue <NPC ID>`. It makes the AI server mark
the NPC and report its state byte at each step of its state routines (mostly
the state current when the step starts; the dispatcher is `0042b86c`). PQ-186
(evidence)
confirmed that the link is the AI-server connections and that only the NPC
constructor clears the mark, and corrected the audience: Ebenezer forwards each
report as `0x5d` only to the in-game users of the NPC's 3x3 regions whose
authority byte is 0 (`0040b4d4` → `0041e454`), so players never receive it.
States 16 and 17 are the open/close cycle of NPCs of type `0x34` (source name
`NPC_SPECIAL_GATE`).

n3e draws it from package data (PQ-177,
evidence,
D-146):
the input table's `names.npc_info` (`N3I7`, CONTRACTS "Package input map")
gives the colour and the text, whose one `{id}` the client replaces with the
NPC's entity id. The line is set at each label refresh (KO slot `+0x14`: every
frame that finds the NPC under `acquire`, or every frame for `always` and
without an NPC lifetime) while the capability set the server last projected
holds `server.inspect`; nothing on the client, a tools build included, can
enable it, and it shows the entity id every client already receives (and,
since PQ-186, a traced NPC's state, which only `server.inspect` sessions
receive; below). It is drawn after the name in the NPC font, the style's gap
plus the font's height above the name and centred on it, with the same black
outline (`00459820` stacks each line its own height plus 5 px above the one
before; n3e has no clan line between). A later refresh without the capability does not clear it: it
goes with the label (range, death, leaving view, a new session), as KO keeps it
until `00456b40` frees it. The projection reaches a session at its start and
with each admin result; a revocation therefore stops new lines at the next one.
The KO table sets green (`0x00FF00`) and `ID({id}) : TYPE({state:0})`.

The NPC state trace (PQ-186,
D-147):
a `server.inspect` holder marks an NPC with the admin operation `trace` (the
tools terminal's `trace NPC_ID`); the server checks the role against the
authenticated character, marks the NPC (32 marks at most, 8 per session, for
the NPC's life: the mark follows it through an encounter reset or a respawn,
which give it a new entity id) and then sends its behavior (`idle`, `chase`, `attack`,
`return`, `recover`, `dead`) in each World snapshot of every session it
currently leases `server.inspect` and that sees the NPC. The text's optional
state placeholder shows the last reported state of a traced NPC and the
package's fallback for any other (`{state:0}` shows `0`, `{state}` nothing), so a traced worm that is chasing someone reads `ID(5) : TYPE(chase)`. KO's numbers for these states are
not mapped: the user chose to keep the words on this staff-only line (PQ-187,
deviation D-151). The demo sets no line. Without H9
nameplates (the H1–H8 fallback labels) the line is drawn in the fallback
alphabet, which has no parentheses, one text line above the label.

Party names (PQ-166,
evidence): the
input table's `names.party` (`N3I4`, CONTRACTS "Package input map") says how
the names of other players in the local player's party differ. `while_hidden`
keeps them drawn while the toggle hides other players (KO `0046ea90` returns
early only while the party marker `+0x7dc` is 0; the local player's own name
has no such exception, `0046b5a0`). `beyond_distance` lifts the style's camera
`distance` for them (`0046ea90` skips the 48 m test for the marker unless the
zone's Zones.tbl column 23 is 0). `color` replaces the other-player colour
(`0046e840` sets `0xffffff00`). The colour is taken when the label is refreshed,
as KO's slot `+0x14` does: every frame for a party member (exempt from the
lifetime) and for anyone inside `acquire`. A member removed from the party keeps
the party colour between the radii until a refresh (`0051bf60` clears the marker
without one); the end of the local player's own party refreshes every label
(`0051c030`, from the leave, disband and zone-entry paths). Being drawn under the
toggle and beyond the limit follow membership at once, as the marker test in
`0046ea90` does. A party member's name still needs its body drawn (character LOD
and the camera clip range; KO calls the name callback from the body's render,
`00458ef0`, only at a valid LOD). The KO bake reads the column from the package's
zone row (Moradon `Zones\Moradon_xmas.gtd`, key 210, inferred as zone 21 × 10; column 23 = 1),
so Moradon: `while_hidden`, `beyond_distance`, `color` `0xFFFF00`. The demo has no
party policy. Not mapped: the clan duty 1/100 skip of the limit (no clans).

Camera limit by class (PQ-173,
evidence): the
input table's `names.distance` (`N3I5`, CONTRACTS "Package input map") replaces
the style's camera `distance` for the classes it lists (`self`, `players`,
`npcs`); party members with `beyond_distance` still skip it. KO's other-player
callback `0046ea90` compares with 33.0 (`006a4250`) instead of 48.0
(`006a40dc`) when the zone key (`0046c9d0`) is `0x140`; the self (`0046b5a0`)
and NPC (`00459820`) callbacks never read the key and always use 48.0. The KO
bake sets the limits from the package's zone key through
`games/moradon/nameplates.json` `zone_distance` (`{"320": {"players": 33}}`).
Key 320 is Zones.tbl `dungeon_b1th`, where column 23 is 0, so party members
obey 33 m there too. That the bake's row key (column 1) is KO's runtime key is
an inference, as for Moradon's 210 above. Moradon (key 210) gets no per-class
limit, so every class keeps 48 m; the demo has none. Only Moradon is baked
today, so the 33 m case is covered by the cooker, reader and bake-mapping
checks, not by a running package.

This is bounded ordinary Tuarek/worm presentation. Windows GDI raster/kerning,
full faction/level colors, multiple model profiles, alternate character shapes,
clan/emblems/titles and balloons remain gaps. Current foreground retains the earlier neutral near-white appearance.
ASCII character naming is the existing server constraint; unsupported glyphs use
'?'. Binary audit,
implementation evidence.
