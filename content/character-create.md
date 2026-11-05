# Character create: KO's flow, the realm's contract (RQ-001)

This is KO's whole character-create flow, from a new account's nation choice to the
character's first entry in the world, read statically from KO's client and server. It
is the contract for the character lane: RQ-002 (wire and server), RQ-003 (content per
race and class), RQ-004 (the create screen), RQ-005 (the select hall per character),
RQ-006 (nation select), RQ-007 (in-world play) and RQ-008 (delete). Where 1097, 1264
and 1298 differ, each version is recorded and a realm-owner setting is proposed;
the decisions it needs are Q94–Q99 (`specs/QUESTIONS.md`). RQ-001 changed no code or
package data; the realm before RQ-002 is under "The realm today (before RQ-002)",
RQ-002's wire, package rules and server checks under "The realm's create (RQ-002)", and
each race's model under "The realm's races (RQ-003)".

## Sources

Labels as `specs/KO-FINDINGS.md` defines them. Every program was read statically with
Ghidra 12.1.3 headless (`AuditReference.java`, `-readOnly -noanalysis`; `recover`
where a function had no entry). Nothing was run: 1298 and Ebenezer are never run. The
output is under `build/ghidra/rq001/`, which is not committed.

| Name here | Program or file | Identity | Project |
|---|---|---|---|
| 1298 | n3e's `KnightOnLine.exe`, the 1298 client | sha256 `828ab0db…43a5e5` | n3e `audit-2026-09-19` |
| Ebenezer | n3e's `Ebenezer-official.exe`, the game server (undated; its race floors match 1264's and 1298's table, below) | sha256 `7d83cc28…fa7bcb` | n3e `audit-2026-09-19` |
| Aujard | n3e's `Aujard-official.exe`, the database agent | sha256 `5f5a3a71…128fc` | n3e `audit-2026-09-19` |
| 1264 | the 1264 install's client, unpacked (`ko1264-unpacked.exe`, §9.1) | sha256 `61e9a086…136471` | `build/ghidra/rq096` |
| 1097 | the 1097 install's client, unpacked (`ko1097-unpacked.exe`, RQ-074) | sha256 `82abb582…ebaf` | `build/ghidra/rq074` |
| operator DB | `ref/ko-db/OpenKO-v0.1.2.bak`, its procedures exported by n3e's PQ-276 | sha256 `db11af06…`; export `procedures.json` `d88e694f…` | local-asset |
| ko4life DB | n3e's PQ-276 secondary schema (`ref/kodb`) | sha256 `fabd5034…` | local-asset, secondary |
| source | `$N3E_HOME/ref/ko-src`: `src/Client/WarFare/GameProcCharacterCreate.cpp`, `UICharacterCreate.cpp`, `GameProcNationSelect.cpp`, `UINationSelectDlg.cpp`, `GameProcLogIn_1298.cpp`, `GameProcCharacterSelect.cpp`; `src/Server/Ebenezer/User.cpp`; Aujard's `DBAgent.cpp`; `shared/globals.h`; `src/N3Base/N3UIEdit.cpp` | — | source |

Tables, decoded with n3e's `ko_tbl` (key `0x0816`/`0x6081`/`0x1608`):

| Table | 1298 (pinned tree) | 1264 install | 1097 install |
|---|---|---|---|
| `Data/NewChrValue.tbl` | `65b2868a…` | `5ab78987…` | `7fc52dc3…` |
| `Data/UPC_DefaultLooks.tbl` | the pinned tree's | `9c4ad1d7…` | `0d95da40…` |
| `Data/Texts_us.tbl` | `3f62f1fb…` | — | — |
| `UI_US/co_characterCreate_us.uif` | `f918867a…` | — | — |
| `UI_US/co_nation_Select_us.uif` | `351b94ed…` | — | — |

Text rows are cited by id. The short English strings beside some of them are quoted
from the pinned `Texts_us.tbl` as citations, so the refusals can be told apart; the
package itself refers to rows by id only (`games/moradon/front-end-1298.json` names
1901, 1904, 1908 and 7675), and the cook reads the text from the pinned tree.

## The flow end to end

1. **Login.** If the login answer's nation byte is 0xff, the client shows login error
   row 2906. If it is 0, the account has no nation and the client goes to nation
   select. If it is 1 (Karus) or 2 (El Morad), it writes the registry's
   `SelectServer` and goes to character select. (1298 `005f8340`, the login vtable
   `0x6a9380` slot `+0x10`; source `GameProcLogIn_1298.cpp`; binary.)
2. **Nation select** (below) sends `[0x05, nation]`. Its answer sets the nation, and
   the next tick moves to select.
3. **Select.** Create opens the create window in the focused slot or the first empty
   one. When all three slots are full it shows row 7675 instead ("Cannot create
   additional characters.", untitled; 1298 `005ff920`, §9.14; binary).
4. **Create.** The player picks a race, a class, a face and a hair, spends the bonus
   points and types a name. Create checks these locally and sends `WIZ_NEW_CHAR`
   (0x02). There is no confirm dialog.
5. **Answer.**
   - On 0 the client cancels the create, resets it and asks for the character list
     again (`0x0c`).
   - On anything else it shows the error box and the create stays open.

   (1298 `005ff6b0`, binary.)
6. **Game start** places the character at its stored position if that is inside the
   map, otherwise at the zone's home (Ebenezer `004c66dc`, n3e's BINARY-INDEX; binary).

**Deleting the last character** sends the account back to nation select (source
`GameProcCharacterSelect.cpp`; not re-read in 1298: RQ-006/RQ-008 read it).

## Nation select

**1298** (binary, `005ed910`, `005edb00`, `005edbc0`, `005edb80`, the dialog
`0060c390`/`0060c830`/`0060ca60`, vtable `0x6a9618`):

- **Layout.** Init loads `UIs_us.tbl` row 2, column 129, which is
  `UI_us\co_nation_Select_us.uif`, and sets the nation to 0.
- **Dialog members.**

  | Member | Name | Content |
  |---|---|---|
  | `+0xb0` | `text_elmo_notice` | text 10422 |
  | `+0xb4` | `text_karus_notice` | text 10421 |
  | `+0xb8` | `btn_elmo_selection` | nation 2 |
  | `+0xbc` | `btn_karus_selection` | nation 1 |
  | `+0xc0` | `btn_back` | — |
  | `+0xc8` | an OK/Cancel box | `UIs` column 99, `UI_us\co_MsgBoxOkCancel_us.uif` |

- **The confirmation.** A nation button stores the choice at `+0xc4` and asks text
  10420: "You must delete all your characters in this nation if you wish to create a
  character in the opposite nation. Will you proceed?". On OK the client:
  - posts 6609, "Connecting. Please wait.";
  - sends `[0x05, nation]` (`005edb80`);
  - clears the UI flag until the answer.
- **The answer** (`005edbc0`, opcode 0x05). Its byte sets the nation: 0 leaves the
  client waiting, and 1 or 2 move it to select at the next tick (`005edb00`).
- **Back** disconnects (`004512f0` on the socket `00818984`), activates the login
  procedure `008189a8` and sets its `+0x21` to 1, the same server-list return as
  §9.12.

**1264** has the same question and notices: it pushes 0x28b4–0x28b6 (10420–10422) at
`005bc39d`, `005bc459`, `005bcae7` and `005bcb56` (binary).

**1097** loads `UI\Co_NationSelect.uif` (`bt_karus`, `bt_elmo`; Init `00522b00`,
Load `00522e40`) and pushes none of 10420–10422. Its click path was not read (binary,
partial; RQ-006 reads it).

**Ebenezer** (`0049212b`, binary) forwards a nation under 3 to Aujard as 0x05 and
otherwise answers `[5, 0]`. **Aujard** (`0040bbc0` → `00427c40`, binary) calls
`NATION_SELECT` and answers `[5, sid, nation or 0]`.

**The operator's `NATION_SELECT`** (local-asset) upserts the account's `bNation` and
creates its `WAREHOUSE` row. Its character-count check is commented out, so the
"delete all your characters" rule is only the client's flow.

**Nation is per account in KO** (`ACCOUNT_CHAR.bNation`, operator DB, local-asset).
Q98 takes it for the realm.

## Races and classes

Codes are `shared/globals.h`'s (source). Button names are the 1298 layout's
(local-asset), and the member offsets are 1298 ReceiveMessage `00604f90`'s (binary).

| Nation | Race | Code | Button (member) | Model (`UPC_DefaultLooks`) | Classes offered (1298 `006060f0`) |
|---|---|---|---|---|---|
| Karus | Arch Tuarek | 1 | `btn_race_ka_at` (`+0xdc`) | `upc_ka_at` | warrior 101 |
| Karus | Tuarek | 2 | `btn_race_ka_tu` (`+0xe0`) | `upc_ka_tu` | rogue 102, priest 104 |
| Karus | Wrinkle Tuarek | 3 | `btn_race_ka_wt` (`+0xe4`) | `upc_ka_wt` | mage 103 |
| Karus | Puri Tuarek | 4 | `btn_race_ka_pt` (`+0xe8`) | `Chr\upc_el_rf.n3joint` with `item\upc_ka_pu_*` parts | priest 104 |
| El Morad | Barbarian | 11 | `btn_race_el_ba` (`+0xcc`) | `upc_el_ba` | warrior 201 |
| El Morad | El Morad male | 12 | `btn_race_el_rm` (`+0xd0`) | `upc_el_rm` | warrior, rogue, mage, priest (201–204) |
| El Morad | El Morad female | 13 | `btn_race_el_rf` (`+0xd4`) | `upc_el_rf` | warrior, rogue, mage, priest (201–204) |

**Class buttons.** The four class buttons (`+0xec` warrior, `+0xf0` rogue, `+0xf4`
mage, `+0xf8` priest) map to 101–104 for a Karus player and 201–204 for El Morad.

**The race buttons.** No KO version disables a race button.
- `006060f0` sets every race button to 2 (NORMAL) and the chosen one to 3 (DOWN).
- It sets every class button to 7 (DISABLE), then the chosen race's classes to 2.
- A disabled class button is hidden and its `img_*` shown under it (§9.15 RQ-133).
- The same matrix is in 1264 (`0043ec90`, §9.16) and 1097 (`0043a190`) (binary).
- Load (`00603850`) shows the player's nation's race buttons and hides the other's
  (§9.15).

**The Puri Tuarek is a live race in 1298.**
- Its button has style `0x20000` (a check button, like the other six) and textured
  tiles in `co_characterCreate_us.uif` (local-asset).
- The code treats it like any race (binary).
- It has a `NewChrValue` row (40104) and its own looks (local-asset).
- The 1264 layout's Puri button is a plain button (`0x10000`) with an untextured
  disabled image (§9.16).
- A source comment shows the Wrinkle Tuarek was once refused with error 8 (source
  `GameProcCharacterCreate.cpp`, commented out). No version read here refuses a race.

**The class sent is the nation's code.** The client never sends a Karus class for an
El Morad race, but Ebenezer checks only that the class exists (below).

**What a click does** (1298 `00604f90`, binary).
- A race click sets the class to −1 and builds the character (`005fd120`) only when
  the race changed, then calls `006060f0(race)`.
- A class click builds only when the class changed, then calls `006062d0(class)`.
- A click on the chosen race builds nothing and leaves the class unchosen (§9.15
  RQ-130, Q93).

## Face and hair

1298, binary (`00604f90`):

| | Member | Range | Arrows | A change calls |
|---|---|---|---|---|
| Face | `+0x7d8` | 0..3 | `btn_face_left` `+0x164`, `btn_face_right` `+0x168` | the character's vtable `+0x28` |
| Hair | `+0x7dc` | 0..2 | `btn_hair_left` `+0x16c`, `btn_hair_right` `+0x170` | vtable `+0x24` |

- Each arrow steps by one and stops at the end of the range; it does not wrap.
- The range is the same for every race.
- A change calls the vtable function once; nothing tests a race or class
  first, so the arrows work before a race is clicked (RQ-174).
- No open writes them: the player's constructor (`00465410`) and its Release
  (`00465740`) zero `+0x7d8` and `+0x7dc`, the world's own-character packet
  (`005c87c0`) sets them, and neither Init (`005fab40`), Cancel (`005ffb90`),
  the reset (`006066b0`) nor the build (`005fd120`, which calls `+0x28` and
  `+0x24` with the values as they are) writes them. A create keeps the face
  and hair of the last one (RQ-174, binary).
- 1264's (`0043dfc0`) are the same: the face `+0x6e0` and hair `+0x6e4`,
  0..3 and 0..2, clamped, `+0x28` and `+0x24` on a change (binary). 1097 has
  the same ranges (binary).

The files are named by the looks path plus `%02d` (source `PlayerMySelf.cpp`
`InitHair`).

**The pinned tree's looks** (local-asset):

| Race | Faces | Hairs |
|---|---|---|
| Wrinkle Tuarek | 00..03 | none: its looks have no hair or lower part, so the hair arrow changes the value and draws nothing new |
| Puri Tuarek | 00..03 | 00..03; the client reaches only 00..02 |
| Every other race | 00..03 | 00..02 |

## Stats and bonus points

**Tables.** 1298 reads `NewChrValue` by race × 10000 + class; 1264 and 1097 read it
by race. The row format is the source's `__TABLE_NEW_CHR`: `dwID`, `szName`, `iStr`,
`iSta`, `iDex`, `iInt`, `iMAP`, `iBonus`, then 12 item ids. 1097's table has only the
first eight columns. (Local-asset; 1264 lookup `0043ae40`, binary.)

| Race | 1298 rows | Str / Sta / Dex / Int / MAP | 1264 | 1097 |
|---|---|---|---|---|
| Arch Tuarek | 10101 | 65 / 65 / 60 / 50 / 50 | the same (row 1) | the same |
| Tuarek | 20102, 20104 | 60 / 60 / 70 / 50 / 50 | the same (row 2) | **65 / 65 / 60 / 50 / 50** |
| Wrinkle Tuarek | 30103 | 50 / 50 / 70 / 70 / 50 | the same | the same |
| Puri Tuarek | 40104 | 50 / 60 / 60 / 70 / 50 | the same | the same |
| Barbarian | 110201 | 65 / 65 / 60 / 50 / 50 | the same | the same |
| El Morad male | 120201–120204 | 60 / 60 / 70 / 50 / 50 | the same | the same |
| El Morad female | 130201–130204 | 50 / 50 / 70 / 70 / 50 | the same | the same |

- Every row's bonus is 10, and every row's base sums to 290, so a finished character
  has 300 (local-asset).
- The stats depend on race alone; the class changes only the dress (below).
- MAP is "Magic Power", which 1298's labels call "MP" (§9.15 Q93).

**The arrows** (1298 `00604f90`; stats at `+0x830` str, `+0x838` sta, `+0x840` dex,
`+0x848` int, `+0x850` MAP; bonus left `+0xb0`, bonus total `+0xb4`; binary):
- `btn_*_right` adds 1 to the stat and takes 1 from the bonus while the bonus is
  above 0.
- `btn_*_left` takes 1 from the stat and gives it back while the bonus is below the
  total and the stat is above the row's base.
- So each stat runs from its base to base + 10, and the points left run from 10 to 0.
- With no class chosen (class −1) the key race × 10000 − 1 has no row, so the left
  arrows do nothing.
- The values and `text_bonus` (`+0x160`) are written by `00605950`, which every build
  runs. The reset `006066b0` writes them empty (§9.15) but leaves `+0xb0` and `+0xb4`
  (Q111).
- 1264's (`0043dfc0`, binary) are the same, but its left arrows look the row up by the
  race alone, so they work without a class, and only a race change builds (SetChr
  `00439970`, then Reset `0043ea10` writes the values and `text_bonus`;
  KO-FINDINGS §10.4).

**The build** (`005fd120`, binary):
- With no class chosen it takes the race's default class to look up the row: 1→101,
  2→102, 3→103, 4→104, 11→201, 12→202, 13→204. So the race click alone fills in
  the stats and the bonus.
- It copies the row's five stats (`+0x14`..`+0x24`) and its bonus into both `+0xb0`
  and `+0xb4` (`+0x28`). **Every build resets the points spent.**
- It returns early if the race has no `UPC_DefaultLooks` row.

**The create dress.** With a row, the build dresses the model in the row's items:
- parts 0..9 from `+0x34 + 4i` (`dwIDK[2..11]`; the five armour slots: upper 0,
  lower 1, gauntlets 3, boots 4 and helmet 5);
- the face through vtable `+0x28`;
- the right- and left-hand plugs from `+0x2c`/`+0x30` (`dwIDK[0]`, `[1]`), looked up
  in the item table (`DAT_008186f4`) and attached by `FUN_006157b0`.

Without a row it uses the looks parts. Each 1298 class row names its own weapon and
armour set; 1264's rows name one set per race (a weapon and four armour pieces, no
helmet). 1097 has no item columns: its SetChr (`004359f0`) draws the looks parts.
(Local-asset; binary.)

The dress is only the create screen's: the server does not create those items (below).

**How each item is drawn (RQ-159).** Read statically in 1298 (`005fd120`,
`006157b0`, `00467d50`, `00462bd0`, `00467b30`) and 1264 (`00439970`, `005d2a80`,
`004680e0`, `00463350`); binary, `specs/KO-FINDINGS.md` §10.3:
- **Slots.** Part slot i takes column `dwIDK[2 + i]` in slot order 0..9; slot 2 is
  always the race's face. An item is looked up as Item_Org row item / 1000 × 1000 and
  Item_Ext row item % 1000 of table `Item_Ext_<Item_Org column 2>`. An item of 0, or
  one Item_Org lacks, leaves the slot the looks row's part (slot 5 its hair). The
  plugs are cleared, then each hand's column is attached to that hand (plug 0 the
  right, 1 the left) whatever hand the item's row names (1298's El Morad male
  warrior holds two swords, its rogue a bow in the left hand).
- **The file** (`006157b0`, 1264 `005d2a80`, the same code): a plug is
  `Item\%.1d_%.4d_%.2d_%.1d.n3cplug` of its Item_Ext resource (column 6) when that is
  not 0, else its Item_Org resource (column 7), and no file without an Item_Ext row;
  a part is `Item\%.1d_%.4d_%.2d_%.1d.n3cpart` of its Item_Org number / 10 with the
  race × 1000 added to the four-digit field, for a race and class the client's switch
  accepts (every race and class the tables name), `%.2d_` first when number / 10000 %
  100 is not 0. A resource of 0 names no file. The class 1298 names a part with is
  the chosen class, or the race's default (above) before one; 1264's is always the
  race's default.
- **Robes.** The part set (`00467d50`, 1264 `004680e0`) draws the lower slot bare
  (no part at all) while the upper's item is a robe: its Item_Org column 12 is not 0,
  except, for an El Morad character, an item whose number / 10^6 is 266 (and, in
  1298, 969). So the Wrinkle Tuarek's Complete Robe (266001000) leaves its lower bare
  (its lower's file, `2_6603_20_0.n3cpart`, is in neither tree), and the El Morad
  mage's lower is drawn.
- **Shields.** A left-hand plug whose Item_Org class (column 11) is 60 hangs on the
  joint at `+0x110` instead of the left hand's `+0x10c` (`00467b30`).

**Package data and the cook.** `columns.plugs` and `columns.parts` name each hand's
and each part slot's column (KO's 8, 9 and 10..19 counted from 0, the face's slot
null); each table's `dress` names its `items` and `extensions` tables (one input's,
`{}` the extension index) and its client's `robe_exempt` pairs ([nation, item /
10^6]: 1264's `[2, 266]`, 1298's also `[2, 969]`), or is null for a table without
item columns. `ko_create.dress` resolves each specialty's dress, as
`tools/assetc/ko_item_files.py` names KO's files: parts `{slot, item, file}` (a bare
lower's file null) and plugs `{slot, item, kind, file}`, each file with its input's
prefix. `build` checks it for the races offered and the races with a create model,
refusing an item Item_Org lacks, one whose form (part or plug) or part slot is not
its column's, an icon-only item, an item whose Item_Ext table is 24 or more (KO's
name function indexes its 24 tables with it unbounded for every item, `006157b0`,
`005d2a80`), one that names no file or a file its input lacks,
a race and class the switch would name from a stack address, and malformed item
tables. `create.bin` and the provenance of a package on 1264's table are as before
(a package on 1298's table records the 1298 item tables it read). Since RQ-176 the
front-end cook writes it into `front-end.bin` for the create screen ("The create
dress (RQ-176)" below); RQ-005 draws it in the hall.

**Moradon's dress** (both tables, all races; local-asset), the files the parts and
plugs name:

| Race, class | 1264's table (`installer-1264:`, the 1097 choice's) | 1298's table |
|---|---|---|
| 1 Arch Tuarek 101 | `2_0601_*` chitin, sword `1_2151_00_0` | `2_0601_*`, `1_5621_00_0` |
| 2 Tuarek 102 | `2_4602_*` rogue chitin, crossbow `1_6821_00_0` | the same |
| 2 Tuarek 104 | the 102 set (one per race) | `2_8602_*` priest chitin, `1_4621_00_0` |
| 3 Wrinkle Tuarek 103 | `2_6603_*` robe, lower bare, `1_8051_00_0` | the same set, `1_8031_00_0` |
| 4 Puri Tuarek 104 | `2_8604_*`, `1_4025_00_0` | `2_8604_*`, `1_9061_00_0` and shield `1_7157_00_0` (its Item_Ext resource) |
| 11 Barbarian 201 | `2_0611_*`, `1_2151_00_0` | `2_0611_*`, `1_2641_00_0` |
| 12 El Morad male | `2_4612_*`, bow `1_6211_00_0` in the left hand, every class | 201 `2_0612_*` two `1_2151_00_0`; 202 `2_4612_*` left `1_6841_00_0`; 203 `2_6612_*` (lower drawn) `1_8031_00_0`; 204 `2_8612_*` `1_4111_00_0` |
| 13 El Morad female | `2_4613_*`, `1_4025_00_0`, every class | 201 `2_0613_*`, `1_2151_00_0` and shield `1_7153_00_0`; 202 `2_4613_*`, two `1_1121_00_0`; 203 `2_6613_*`, `1_8031_00_0`; 204 `2_8613_*`, `1_4021_00_0` and shield `1_7155_00_0` |

`*` is the upper, lower, gauntlets and boots (`_10`, `_20`, `_40`, `_50`). So the
1097 choice dresses its fixed Tuarek priest as 1264 does, in the rogue's set.

**The server's floors** are Ebenezer's own, not the table's (below). They equal
1264's and 1298's bases.

## Descriptions

1298 Load `00603850` and MouseProc `00605bf0`, 1264 Load `0043cd00` and MouseProc
`0043eb00`, binary (KO-FINDINGS §10.6). Text rows, the same in both clients (in each
client's `Texts_us.tbl`; the pinned 1298 table's Puri Tuarek row 3214 is Korean,
the 1264 install's English, local-asset):

| What | Karus | El Morad |
|---|---|---|
| Panel text at open (`text_desc`, `+0x15c`) | 6124 | 6125 |
| Warrior | 3217 | 3209 |
| Rogue | 3215 | 3208 |
| Mage | 3212 | 3205 |
| Priest | 3213 | 3207 |
| Races | ka_at 3211, ka_tu 3216, ka_wt 3218, ka_pt 3214 | el_ba 3203, el_rm 3206, el_rf 3204 |
| Stat areas | str 3219, dex 3202, sta 3220, int 3210, map 3201 (1264's Load: str, sta, dex, int, map) | the same |

**Hover.** Both MouseProcs set `text_desc`'s colour to `0xffffff00` and take the
tooltip of the stat area, class button or race button whose rect holds the pointer,
in that order, a later group's over an earlier's, whatever the button's state or
visibility. Off them the two clients differ:
- **1264** writes nothing, so the text stays the last tooltip, or row 6124 from the
  open on (each open loads the layout again).
- **1298** writes, every tick, the chosen class's tooltip, else the chosen race's,
  else nothing. There is no join: the class's text replaces the race's (an earlier
  reading here said "joined"; RQ-175 read it as an assign). Its Load's row 6124 is
  written over by the first pass, which runs while the create is still hidden, so it
  is never drawn.

**What a build writes.** `00605950`, run by each build, also sets `text_desc` and
`edit_name` from `006dfe28`, the image's empty string (no instruction writes it,
KO-FINDINGS §10.6). So in 1298 a build clears a typed name, which is RQ-135's to
carry; the description text it empties is written again by the next pass.

## Names

| Rule | 1298 client (`005fffd0`, binary) | Ebenezer (`00491a02`, `IsValidName` `004a77eb`, binary) |
|---|---|---|
| Empty | refused, code 6 (row 1905) | length < 1 → 5 |
| Maximum length | none found: the source's create never calls `SetMaxString`, whose default is `DEFAULT_MAX_LENGTH` (source `N3UIEdit.cpp`); the layout's edit was not checked for a limit | length > 20 (`MAX_ID_SIZE`) → 5 |
| ASCII punctuation | refuses `` ~ ` ! @ # $ % ^ & * ( ) - + = \| \ < > , . ? / { [ } ] " ' ``, space and `\n` → 5 (row 1906) | refuses the same, plus tab → 5; **allows `_`, `:` and `;`**, and passes the control bytes below 0x20 other than tab and `\n` (no check refuses them) |
| Bytes ≥ 0x80 | allowed, except some double-byte symbols → 5 | every byte ≥ 0x80 refused → 5 |
| Reserved words | none | when the flag `+0x38828` is 1, refuses names containing 운영자, 나이트, 도우미, Knight, Noahsystem, Wizgate, Mgame, 노아시스템, 위즈게이트, 엠게임, 트라이나 or 카리브디스 → 5 |
| Word list | none | a 100 × 21-byte list at `+0x8748 + 0xb04`, compared case-folded → 5; its loader was not read, and the reference tree's `BlockWord.txt` is empty |
| Already taken | — | the procedure's `strUserId` lookup → 3 (row 1912); case-insensitive under SQL Server's default collation, which was not read from the backup (local-asset) |

## The create packet

**1298 → Ebenezer** (`005fffd0`, binary; the same fields as the source's
`MsgSendCharacterCreate`):

| Field | Type | Notes |
|---|---|---|
| opcode | u8 | 0x02 `WIZ_NEW_CHAR` |
| slot | u8 | the select's slot, `00818a20` |
| name | u16 length + bytes | |
| race | u8 | |
| class | u16 | |
| face | u8 | |
| hair | u8 | |
| str, sta, dex, int, MAP | u8 each | |

Nation is not in the packet: it is the account's. The client clears the UI flag after
sending and sets it again on a failure.

**Ebenezer's validation, in order** (`00491a02`, binary):

1. Name length outside 1..20 → 5.
2. Slot outside 0..4 → 1.
3. `IsValidName` fails → 5.
4. The class not in the class map (`004cd2a9`, the source's `CoefficientTable`), or
   str + sta + dex + int + MAP > 300 → 2.
5. Any stat < 50 → 0x11 (17).
6. The race's floors, failure → 0x11:

   | Race | Floors |
   |---|---|
   | 1, 11 | str ≥ 65, sta ≥ 65, dex ≥ 60 |
   | 2, 12 | str ≥ 60, sta ≥ 60, dex ≥ 70 |
   | 3, 13 | dex ≥ 70, int ≥ 70 |
   | 4 | sta ≥ 60, dex ≥ 60, int ≥ 70 |
   | any other race | none |

**Ebenezer does not check:**
- the race/class matrix, or that the class is the race's nation's;
- that the race exists;
- face or hair;
- that the sum is exactly 300 (a sum under 300 with every floor met passes).

So a 1097 Tuarek (base 65 / 65 / 60) passes only with all ten points in dex.

**Forwarding.** On a pass it forwards to Aujard: 0x02, the socket id, the account,
slot, name, race, class, face, hair and the five stats. On a failure it answers
`[0x02, code]`. If the queue send fails it logs "NewChar Send Fail : %d" and answers
**0, success**. That is a KO bug the realm does not copy (binary).

**Aujard** (`0040bdf0` → `00427e70`, binary) formats
`{call CREATE_NEW_CHAR ( ?, '%s', %d, '%s', %d,…)}` (`005d5644`; hair before face)
and answers `[0x02, sid, result]`. If its retries fail it logs
"New Char Packet Drop!!!".

**The operator's `CREATE_NEW_CHAR`** (operator DB, script 2006, local-asset):

| Check | Result |
|---|---|
| the account already has 3 characters (`ACCOUNT_CHAR.bCharNum` ≥ 3) | 1 |
| the account's nation and the race's nation disagree, or nation not 1 or 2 (tested after the count, so it overrides a 1) | 2 |
| the name exists | 3 |
| the slot taken: the `UPDATE` of `strCharID1`..`3` for slot 0..2 requires the column NULL, so a taken slot, or a slot index of 3 or more (no branch), changes no row and the `bCharNum` recheck fails | 4 |
| the insert fails (`@@ERROR`) | 4 |

- On a pass it sets the zone to 21 at `ZONE_INFO`'s `InitX`/`InitZ`. Zone 21 is
  `moradon_0826.smd`, at 31200/40200, which is (312, 402) in KO units (`ZONE_INFO`
  sha256 `31c3c5d2…`).
- It inserts the row with no item columns and fills the slot.
- The operator's `ACCOUNT_CHAR` has 3 slots.

The **ko4life** procedure (secondary) has 5 slots and sets the zone to the nation's.

## Refusals

1298's error box (`00600750`, binary) is an OK box titled 1901, "Failed creating
character". The source's enum is in `GameProcCharacterCreate.h`.

| Code | Set by | Row | Text |
|---|---|---|---|
| 1 | Ebenezer (slot outside 0..4), procedure (3 characters already) | 1911 | "You cannot create anymore characters." |
| 2 | Ebenezer (class or sum), procedure (nation) | 1907 | "The selected nation and the race does not match." |
| 3 | procedure | 1912 | "This ID is already used on another character." |
| 4 | procedure (slot taken, slot index ≥ 3, or the insert failed) | 1902 | "Failed creating Database" |
| 5 | client, Ebenezer | 1906 | "You cannot use this character ID." |
| 6 | client (empty name) | 1905 | "Please enter your character ID." |
| 7 | client (no race) | 1908 | "Please select a race." |
| 8 | nobody in 1298 (the source's commented-out race check) | 1910 | "This race is not available yet." |
| 9 | client (no class) | 1904 | "Please select a specialty." |
| 10 | client (points left) | 1913 | "There are stat points still remaining." |
| 17 and any other | Ebenezer (stat floors) | 1915 | "Unknown error." |

- The client checks, in order: empty name 6, no race 7, no class 9, points left 10,
  then the name's letters 5 (1298 `005fffd0`; 1264 `0043a340` and 1097 `00435d10` the
  same, binary).
- The select's "no free slot" is row 7675, untitled, before create opens.

## Starting state

| What | KO | Evidence |
|---|---|---|
| Level, experience, gold | 1, 0, 0 | ko4life schema defaults (local-asset, secondary); the operator INSERT leaves them to the table's defaults |
| Stats | as sent | procedure (local-asset) |
| HP, MP, SP | ko4life defaults 100; recomputed at game start | secondary; the recompute was not read |
| Items | none: the procedure writes no item columns | operator DB (local-asset) |
| Zone and position | operator: zone 21 Moradon at (312, 402); ko4life: the nation's home zone | local-asset |
| First entry | the stored position if inside the map, otherwise the zone's home | Ebenezer `004c66dc` (binary) |

## The character list (for RQ-002, RQ-005)

- **Fields.** Aujard's `LoadCharInfo` sends, per character, the name, race, class
  (u16), level, face, hair, zone and its eight visible slots' item id and durability
  (source `DBAgent.cpp`). The 1298 parse of the list was not re-read (RQ-005).
- **Default looks.** The select draws each character from `UPC_DefaultLooks` by race
  and its visible items (source `GameProcCharacterSelect.cpp`, `AddChr`).

## Version differences, and proposed realm-owner settings

| Difference | 1097 | 1264 | 1298 | Proposed setting (realm-config, `create`) |
|---|---|---|---|---|
| `NewChrValue` key and Tuarek base | by race; Tuarek 65/65/60 | by race; Tuarek 60/60/70 | by race and class; Tuarek 60/60/70 | `create.table`: which install's table the realm validates against. Default: the client whose create screen the front end draws (Q97) |
| Create dress | the looks parts | one set per race | one set per class | follows `create.table` |
| Puri Tuarek button | live in code (`0043a190`); its own layout not read, the 1097 choice draws 1264's (§9.2) | a plain button with an untextured disabled image; live in code | a live check button | `create.races`: the races offered (Q94) |
| Race/class matrix, face 0..3, hair 0..2, 10 bonus points, client checks | the same | the same | the same | none; package data (RQ-003) |
| Nation select | `Co_NationSelect.uif`, no question read | asks 10420 | asks 10420 | none; the layout follows the front end (RQ-006) |
| Starting zone | the server's, not the client's | the server's | the server's | `create.start` (Q96; RQ-154) |
| Starting items | the server's: none from the operator's procedure | the same | the same | `create.items` (Q96; RQ-154) |

RQ-002 landed `create.table`, `create.races` and `create.reserved`, RQ-154
`create.start` and `create.items`, in `games/<game>/realm-config.json` (Moradon's
`{"front_end": "1097"}`, with no `create`). The cook checks them against the package.
No engine module names a race, class, zone or item.

## The realm today (before RQ-002)

- **Wire.** `CreateCharacter` carries only `name` (`protocol/wire.proto`), and the
  `Character` list only `id`, `name` and `level`.
- **Server.** `accounts::create` accepts 1..24 ASCII letters, digits, `_` and `-`. It
  refuses at the package's slot limit (3, `games/moradon/front-end.json`), inserts
  the name and the spawn, and gives the package's `starting` items
  (`server/src/accounts.rs`, `server/src/inventory.rs`).
- **Database.** `characters` keeps `UNIQUE(realm, name)`, case-sensitive, length
  1..24 (`deploy/002-multiplayer.sql`).
- **Refusals.** Every create failure is error 8, "character name invalid/taken or
  limit reached" (`server/src/network.rs`).
- **The screen.** The create screen shows race and class fixed: Tuarek priest, Karus
  (Q51, Q52).

Q99 replaces those name rules with KO's.

## The realm's create (RQ-002)

**Package data.** `games/<game>/character-create.json` holds the package's create
rules; KO's are Moradon's, from the tables above:

| Key | Meaning |
|---|---|
| `stats` | how many stats a character has (Moradon: 5, KO's order str, sta, dex, int, MAP) |
| `nation` | the account's nation until the realm keeps one per account (RQ-006): Moradon's 1, Karus (Q94, Q101) |
| `faces`, `hairs` | how many faces and hairs every race offers: KO's 4 and 3 (1298 `00604f90`) |
| `races` | each race's `race` code, `nation` and `specialties` (KO's classes), as 1298's race click offers them (`006060f0`), and its `looks`, the stem of its `UPC_DefaultLooks` parts (RQ-003, below) |
| `content` | the races the package has a player model for, every screen and the world drawing it: the races create may offer (Moradon: the Tuarek, 2; RQ-003, Q105, below) |
| `player` | the race of the package's player scenes, one of `content` (Moradon: 2; RQ-003) |
| `models` | the races whose model the package ships in each form a screen draws: `create`, the create screen's (`front-end.bin` N3FE version 24; Moradon: 1, 2, 3, 4), which has every race of `content` (RQ-158, below) |
| `tables` | the stat tables a realm validates against, by id: each a KO `values` table (`Data/NewChrValue.tbl`) read from the front end's inputs (a `<name>:` prefix as the recipe's paths), its row `key` (row id = race × `race` + specialty × `specialty`: 1264's `{1, 0}`, 1298's `{10000, 1}`), the `texts` table its refusals are worded from and its `dress` (RQ-159, above): the `items` and `extensions` tables and `robe_exempt`, or null for a table without item columns |
| `columns` | the values table's stat columns and bonus column (KO's 2..6 and 7), and the item columns of each hand plug (`plugs`, 8 and 9) and each part slot (`parts`, 10..19, the face's null; RQ-159) |
| `front_ends` | the table each front-end client draws by default (Q97 (b): 1264's for the 1097 choice, 1298's for the 1298 recipe) |
| `refusals` | the text row of each refusal: `limit` 1911, `mismatch` 1907, `taken` 1912, `failed` 1902, `name` 1906, `stats` 1915 |
| `name` | the name rule: `min` 1, `max` 20, `punctuation` `_:;` beside ASCII letters and digits (Q99) |
| `fixed` | the choice a create without a race takes (Q100): race, specialty, face, hair and the bonus `points` per stat; Moradon's the Tuarek priest, face 0, hair 0, the ten points in MP |
| `starting` | each specialty's starting set (RQ-160, below): groups of `specialties` sharing `items` (`[item, count]` pairs of the package's bag items) and the `weapon` among them it can use, every specialty of `races` in one group; or null, every specialty starting with the package's `starting` items |

The realm owner's `realm-config.json` may add `create`: `table` (Q97, default the
front end's), `races` (Q94, default `content`; only races in `content`),
`reserved` (Q99, words no name may contain, compared without regard to case;
default none), `start` (Q96, where a new character starts; default the package's
spawn) and `items` (Q96, what some specialties start with; default `starting`).
The last two are RQ-154's, "Start and starting items" below.

**The cook.** `make realm-assets` (`ko_bake.py --features`) checks both files with
the front-end choice, before the survey (`tools/assetc/ko_create.py` `plan`, through
`front_end_choice.choose`), then reads the chosen table and text rows from the front
end's inputs (`build`). It refuses a malformed file or setting, a table the package
lacks, a race without a player model, a `content` race without a create model
(`models.create`, RQ-158), a table row whose race or specialty the
package lacks, a missing row the offered races need, a fixed choice the rules
refuse, a create dress that does not resolve (RQ-159, above), a starting set
that does not fit the package (RQ-160, below), and a start in another zone or off the
map (RQ-154, below). The package's manifest gets a `create` section, which
`tools/assetc/create.py` cooks into `create.bin` (N3CC version 2, little-endian u32s,
f32s and u32-length ASCII strings; version 1, RQ-002's, ended after `fixed`):

```
"N3CC" 2 stats nation race_count
  per race: race nation faces hairs specialty_count
    per specialty: specialty bonus base[stats]
name_min name_max punctuation reserved_count reserved[...]
refusal text × 6 (limit, mismatch, taken, failed, name, stats; empty keeps the engine's)
fixed (0 or 1) [race specialty face hair stats[stats]]
start (0 or 1) [x z]                       (f32 engine metres; 0: the package's spawn)
kit_count, per kit: specialty item_count, per item: item count
```

Bounds: 1..8 stats, nation 1..255, 1..32 races of 1..16 specialties, ids 1..65535,
1..256 faces and hairs, bonus and base 0..1000, name 1..24 bytes, up to 256 reserved
words (lower-case printable ASCII, 1..24 bytes), refusal texts printable ASCII up to
200 bytes; a start finite and within 10^6 m; at most one kit per specialty the races
offer, each up to 64 distinct items (printable ASCII ids of 1..128 bytes), counts
1..9999. The server (`server/src/create.rs`) and the client
(`client/assets/assets.cpp` `load_create`, which reads it whole since RQ-004) refuse
any other file; the server's `--check-content` prints `create races=… specialties=…
stats=… nation=… fixed=… start=<x,z or none> items=<kits>`. A package without
`create.bin` creates by name alone, as before. The Moradon package is the only one with rules; its table is 1264's for the
1097 choice, the same bases as 1298's (above), so the fixed Tuarek priest's stats are
60 / 60 / 70 / 50 / 60.

**Wire** (`protocol/wire.proto`, no version change; goldens `create-character`,
`create-refusal`, `characters`):
- `CreateCharacter` gains `slot`, `race`, `specialty`, `face`, `hair` and `stats`
  (the package's order): KO's packet's fields. The nation is the account's.
- `Character` gains `slot`, `nation`, `race`, `specialty`, `face`, `hair` (0 for a
  character created without create rules) and `appearance`, the public keys of its
  committed equipment as `Entity.appearance` projects them.
- A refused create is `Error` code 8 (CONFLICT), `request` 7, and `create_result`
  (`CreateCharacter.Result`: KO's 1 limit, 2 mismatch, 3 taken, 4 failed, 5 name,
  17 stats), its `detail` the package's text for that result (KO's row, cooked) or
  the engine's wording.

**The server's checks**, in order (Q95, Q99):
1. The name: `name.min`..`name.max` bytes of ASCII letters, digits and the
   punctuation, no reserved word → 5.
2. A create whose race is 0 takes the fixed choice in the first free slot (Q100);
   otherwise the slot must be under the package's slot count → 1.
3. The race offered and of the account's nation, the specialty one of the race's →
   2.
4. Face and hair under the race's counts, as many stats as the package's, each at
   least the specialty's base and all summing to the base's sum plus the bonus → 17.
5. In the database: the account under the slot count → 1; no character in the realm
   with the name in any case → 3; the slot free → 4. A create that loses a race
   for the name or slot to another at the insert gets the index's answer, 3 or 4.
6. Any other failure → 4, logged, never success.

Without create rules only the name is checked, against today's rule (1..24 ASCII
letters, digits, `_`, `-`), with the database's checks; every new name is unique
without regard to case.

**Database** (`deploy/026-character-create.sql`): `characters` gains `slot` (unique
per account and realm, backfilled in creation order), `nation`, `race`, `specialty`,
`face`, `hair` and `stats` (all set or all NULL: NULL for a character created
before or without rules), and `name_folded` (`lower(name)`, unique per realm, NULL
for a name kept from before). The list is in slot order; a character whose bag does
not decode is listed without `appearance` (logged), not dropped. Spec 03's account view lists
each character's `slot`, `nation`, `race` and `specialty`.

**What stays.** A new character starts at the package's spawn, or the realm owner's
`create.start`, with its specialty's starting items (Q96 (b); RQ-154, below); the stats
are kept but play does not read them yet (RQ-007); one nation (RQ-006). Since RQ-004 the
KO screens send the package's fixed choice whole (below); the panels' create still sends
a name alone, which the server fills from the same fixed choice (Q100).

## The realm's races (RQ-003)

**Looks.** KO draws a race from the `UPC_DefaultLooks` row whose key is the race code.
It sets the row's six parts in part-position order: upper, lower, face, hands, feet,
hair. The face and hair files are the row's names with the face or hair number as two
digits before the extension, and an empty name sets no part. (Source
`GameProcCharacterCreate.cpp` `SetChr`, `PlayerMySelf.cpp` `InitFace` and `InitHair`;
the 1298 build `005fd120` returns without a row, binary, above.)

**Package data.** Each race in `character-create.json` names its `looks`, the stem of
its parts (`upc_ka_at`, `upc_ka_tu`, `upc_ka_wt`, `upc_ka_pu`, `upc_el_ba`, `upc_el_rm`,
`upc_el_rf`). `player` names the race of the package's player scenes
(`player-<state>.bin`): Moradon's 2, the Tuarek, until RQ-007 draws each race's own.
`tools/assetc/ko_player.py` cooks any race from its row and refuses a row whose face part
is not the race's `looks`. The skills' clips (`ko_skills`), the swing-sound timings
(`ko_audio`) and the 2145 armour (`ko_armour_2145`) take the player race from the
same entry. No engine module names a race. The Moradon package is byte for byte what
it was.

**Each race's model** from the pinned tree (local-asset; `tests/ko_player_races.py`):

| Race | Parts KO sets | Faces, hairs | Converts on the player path |
|---|---|---|---|
| 1 Arch Tuarek | all six | 00..03, 00..02 | yes: its 49 lower-part vertices with five joint influences keep all five, as KO sums them, in N3SI player scenes (engine 43, RQ-163) and in N3DI render detail with its parts worn (engine 44, RQ-164); its 2185 rotation keys of length 0 read (RQ-156) |
| 2 Tuarek | all six | 00..03, 00..02 | yes (the package's player) |
| 3 Wrinkle Tuarek | upper, face, hands, feet | 00..03, none | yes |
| 4 Puri Tuarek | all six, on the El Morad female joint | 00..03, 00..02 (03 unreached) | yes |
| 11 Barbarian | all six | 00..03, 00..02 | yes (its 19 rotation keys of length 0 read as KO draws them, RQ-156) |
| 12 El Morad male | all six | 00..03, 00..02 | yes: its clip 93, `breath_CrossBow0`, at 0 frames a second reads as KO plays it, its start frame held (RQ-157); its 57 drawn vertices past four joint influences (at most five) keep every influence, in N3SI player scenes and N3DI render detail with its parts worn (RQ-163, RQ-164) |
| 13 El Morad female | all six | 00..03, 00..02 | yes |

Every face and hair the screen reaches is opaque, as the player path draws. Every clip
table has 136 clips, and each has the clips the player cook converts. KO draws a joint on or between rotation keys
of length 0 unrotated (RQ-156, binary: `00411950`, `00427640`, `0064d002`,
`0064cad6`; `specs/KO-FINDINGS.md` §10.1), and the reader converts that frame as
the identity rotation. KO holds a clip at 0 frames a second on its start frame
(RQ-157, binary: the clip-table load `00410c00` keeps the rate as read, the clip
start `0041be40` sets the frame to the start and the tick `00418b20` adds rate ×
time to it; `specs/KO-FINDINGS.md` §10.2), and the reader reads it so, a selected
one converting as that frame held.

**Shipped (RQ-158, Q102, Q105).** Each race of `models.create` has its create model
in `front-end.bin` (N3FE version 24, `content/front-end.md` item 8): KO's `InitChr`
for the race, its looks row's joint, animation and parts (face 0, hair 0, an empty
name setting no part), breathing. The create screen is the models' first consumer:
since RQ-172 a race click draws the chosen race's (a create without race buttons
draws the first, the select character's race). Moradon ships the Karus races that convert on the front-end path
(local-asset; `tests/ko_player_races.py` cooks each):

| Race | Create model | Bytes it adds to `front-end.bin` |
|---|---|---|
| 2 Tuarek | N3S1, the bytes of the one create model before (1,014,644) | 8: the count and its race code |
| 3 Wrinkle Tuarek | N3S1, four parts | 1,405,656 |
| 4 Puri Tuarek | N3S1 | 1,139,064 |
| 1 Arch Tuarek | shipped since RQ-169: in its create dress, on either table, N3SM with no influence table, so Moradon's `front-end.bin` stays without tables (version 31 since RQ-005; 29 before); undressed (its looks parts) it would be N3SI, which a front-end record holds since RQ-165 (N3FE's tables version, 32 since RQ-005 and 30 before, engine 45) | 2,605,024 (1097 choice) and 2,603,428 (1298 recipe): its dressed record, 2,342,872 and 2,341,276 with its race code, and its plug's texture |
| 11 Barbarian, 13 El Morad female | not shipped: they cook, but the realm's create is Karus until nation select (RQ-006) | (1,042,195 and 1,034,220) |
| 12 El Morad male | not shipped: El Morad (RQ-006); its create model in its looks parts is N3SI (RQ-165), in its create dress N3S1 (1264's table) or N3SM (1298's), no influence table | — |

Moradon's `front-end.bin` grows from 53,802,688 to 56,347,416 bytes, under its 64 MiB
bound; the package hash changes, so the hosted
realm's next deploy is a new realm (Q63). A create model is not the select hall's:
KO's select draws its `ChrSelect/` joints and clips (the 1097 choice's
`upc_ka_tu_pri`, 1298's `upc_ka_tu`), its create the looks row's `Chr/` ones, so
RQ-005 ships each race's select model as its own record; nor the world's, whose
player scenes (`player-<state>.bin`, `combat-<i>.bin`) RQ-007 ships per race.

**What create offers** (Q105). `content` stays the Tuarek: a race joins it, and so
`create.races`' default, only when the select hall (RQ-005) and the world (RQ-007)
draw it too, so no character is created that the hall or the world draws as a
Tuarek. The cook refuses a `content` race outside `models.create`, and (as before) a
`create.races` race outside `content`. Since RQ-005 the front-end cook also refuses a
`content` race and class that no `select.characters` entry draws, unless the race
is the default select model's (Q118). The create dress is checked package data
(RQ-159, above), and so are each specialty's starting items and weapon (RQ-160,
below); skills and class rules are open.

**Starting items (RQ-160, Q96, Q107).** KO grants a new character nothing (the
operator's `CREATE_NEW_CHAR`, local-asset, "Starting state" above); the realm grants
the package's (Q96 (b)). What KO says about a weapon a class can use:

| Observation | Where | Label |
|---|---|---|
| An item names the race (Item_Org column 14) and class kind (column 15: warrior, rogue, mage or priest, or 0 for any) that may wear it, and its rank, title and stat floors (columns 29–35); the client refuses another race or class kind before it moves an item to a slot | `src/Client/WarFare/UIInventory.cpp` `CUIInventory::IsValidRaceAndClass`, `src/Client/WarFare/GameDef.h` `__TABLE_ITEM_BASIC` | source |
| The server's item move refuses another race, then `ItemEquipAvailable`'s rank, title and stat floors; it reads no class | `src/Server/Ebenezer/User.cpp` (the item move, `CUser::ItemEquipAvailable`) | source |
| Of the pinned tree's 197 hand items (attach 0–4), 20 name a class. The Short Blade (120110000) and the Two-Handed Sword (125310000), the practice blade's and the two-hand blade's art (`games/moradon/appearance.json`), name none and need 62 and 72 strength | the pinned `Data/Item_Org_us.tbl` (sha256 `fe48c0df…07b2a`) | local-asset |
| Each class's create dress weapon is of its kind (1298: swords and spears for warriors, daggers and bows for rogues, staffs for mages, maces for priests; 1264 one per race), each needing 106 to 200 of a stat, above a new character's; only the bows name a class (rogue) | 1264's and 1298's dress (RQ-159, above) through their Item_Org | local-asset |

The 1298 binary's equip checks were not read; the source is the evidence here.

`starting` in `character-create.json` gives each specialty its set. `ko_create.starting`
checks it, in the `--features` cook, against the package's inventory, equipment and wear
(`features.json` and the items the cook adds). It refuses:
- an item the bag lacks, or a count over its stack limit;
- a set the bag cannot hold beside the progression's reward slots (the inventory
  cook's rule for the package's own `starting`);
- a weapon that is not an equipment item that attacks (a wear item with attack slots);
- a weapon the package's player may not wear by the server's rule
  (`server/src/equipment.rs`): its race 0 or the package's, its title and attributes
  at most the package's.

Moradon's set is the package's `starting` items for every specialty, its weapon the
practice blade (Q107 (a)). The package has no weapon of a rogue's, mage's or priest's
kind, and the realm's equipment rule has no class (RQ-162, RQ-007). RQ-154 cooks each
offered specialty's set into `create.bin` (below); the weapon is checked, not cooked,
and stays in the bag as the package's starting blade does.

Items the cook itself adds to the package's `starting` items (the opt-in
`--glow-2233` cook's Azagai and its grades, its arrows and its 2145 armour, granted at
start: `tools/assetc/ko_chrplug_2145.py`) join each of the package's `starting` sets
after the set's own items, an item the set already names keeping the set's count, and
are checked with them (RQ-178). Moradon's set so still holds every starting item the
cooked package grants, as before RQ-160. A realm owner's `create.items` group replaces
the package's set and gets none of them.

## Start and starting items (RQ-154, Q96)

KO's operator procedure starts every character in zone 21, Moradon, at (312, 402),
with no items (`CREATE_NEW_CHAR`, local-asset; "Starting state" above). The realm
starts it where the package or the realm owner says, with its specialty's set (Q96
(b)). Two realm-owner settings in `realm-config.json`'s `create`:

| Setting | Form | Default |
|---|---|---|
| `start` | `{"zone": <KO zone id>, "position": [x, z]}`: KO's map position in metres from the map's corner, as `START_POSITION` and `CREATE_NEW_CHAR` name it (KO's operator: `{"zone": 21, "position": [312, 402]}`) | the package's spawn (the surveyed start) |
| `items` | groups as `starting`'s: `specialties`, `items` (`[item, count]` pairs of the package's bag items, none allowed: KO's operator gives none) and `weapon` (one of them, or null); each specialty in one group at most | `starting` for every specialty a group does not name |

**The cook** (`tools/assetc/ko_create.py`: `plan` checks the shapes before the survey,
`starting` and `complete` the rest in the `--features` cook) refuses:
- a malformed `start` or `items`; a group naming a specialty no race has, or one
  another group names;
- a start whose zone is not the package's (the realm is one zone; Moradon's is 21), or
  whose position leaves the map;
- a set that `starting` refuses (RQ-160, above), and one naming the progression's
  reward item, which no bag may start with.

It cooks the start as engine metres (`x - half`, `half - z`, as `ko_start` maps a start
area; Moradon's map is 512 m, so KO's (312, 402) is (56, -146)), recorded in the
provenance's `create.start`, and each specialty the offered races have that has a set
(the realm owner's group, else `starting`'s) as a kit in `create.bin` (above).

**The server** refuses a package whose start is not on the ground
(`movement::ground`, as the package's spawn), and one with kits but no inventory or a
kit that is not the bag's: an item the bag lacks or twice, the reward item, a count
past its stack, or a set that with the reward slots does not leave the bag a free slot
(`inventory::Policy::validate_kit`). `accounts::create` stores the new character at the
start (`content::Release::create_spawn`: the start on the ground, else the package's
spawn) with its specialty. The bag is built when the character is first loaded
(`inventory::load`, as before): with its specialty's kit when it has one, otherwise
(a specialty without a set, or a character created without the package's rules) the
items' own `starting` counts. An empty kit starts the bag with only the reward slots.

Moradon names neither setting: a new character starts at the package's spawn with the
package's `starting` items, as before RQ-154, now cooked as specialties 102 and 104's
kits (`create.bin` 384 → 842 bytes; the package hash changes, so the hosted realm's
next deploy is a new realm, Q63). `tests/character_create.py` checks the cook and the
readers; `tests/character_create_db.py` creates characters against Postgres and checks
where each stands and what its bag starts with.

## The create screen (RQ-004)

RQ-004 is the screen with every option working, as 1298 draws it. Its first part (this
section) gives the client the package's rules and makes the screen send KO's whole
create packet; the buttons that choose race, class, face, hair and points, KO's
description texts, the chosen race's model and its dress are its later parts
(`docs/loop/queue.jsonl`), each changing the screen only to match 1298.

**The rules in the client.** `load_create` (`client/assets/assets.cpp`) reads
`create.bin` whole with the server's bounds, so the client and the server refuse the
same files, and checks the fixed choice as the server's `Policy::choice` does
(`create_choice_refusal`, Q95). The front end takes the rules from the release
(`client/render/viewer.cpp`); `client/render/create_choice.h` holds the screen's use of
them, GL-free (`tests/front_end.cpp`).

**The name** (Q99; KO 1298 `005fffd0`, binary; `CN3UIEdit::Load`, source):
- The edit takes any printable ASCII (the realm's fonts draw ASCII 32–126) up to the
  rule's longest name (Moradon: 20; 24 without rules). KO's `edit_name` takes what is
  typed: its layout carries no length (the edit's record is the static's and a typing
  sound, source `N3UIEdit.cpp`) and the source's create never calls `SetMaxString`
  (the 1298 binary's edit was not read). The stop at the longest name is the realm's
  bound; a longer name is one KO's server refuses with the same code 5.
- Create refuses, in 1298's order, an empty name (`create_name`; the client's wording,
  now from the rule: "Enter a name: 1 to 20 letters, digits, _, : or ;." for Moradon's,
  which the 1097 recipe replaces with KO's row 1905), no race and no class (RQ-130), then
  a name the rule refuses: the box a refused create shows (`create_refused`, titled
  1901 by the 1097 recipe) in the package's wording of the server's name refusal (KO's
  row 1906, "You cannot use this character ID."), else the engine's. Nothing is sent.
  KO's client refuses the same letters with code 5 and row 1906 under 1901 (§ Names,
  Refusals); the realm's rule is the server's (Q99), so the client refuses what the
  server would.
- Without rules the rule is the server's legacy one (1..24 ASCII letters, digits, `_`
  and `-`), checked the same way.

**What Create sends.** `CreateCharacter` with the name, from the rules, the
chosen race and specialty (below; a create without race and class buttons, the
package's fixed choice: `fixed`, race and specialty), the face and hair the
face and hair arrows chose (RQ-174, below; a create without them: the fixed
choice's, Q110), and the stats the stat arrows chose
(RQ-173, below; a create without arrows: the chosen specialty's base with the
fixed choice's points spent as it spends them, Moradon's ten in the fifth stat,
MP: the Tuarek rogue or priest at 60 / 60 / 70 / 50 / 60; Q110), in the first
slot the list leaves free
(`Character.slot`). The hall draws the list in slot order, so the new character
stands where it is drawn; KO's 1298 creates in the slot in focus when it is empty
(`005ff920`), which differs only when an empty slot in focus is not the first, and
waits for RQ-005's hall by slot (RQ-177). A package without rules sends race 0 and
the name, as before. The server checks the choice as any create (Q95); its race-0
path (Q100) stays for the panels' create.

Moradon's cooked bytes were unchanged by this first part.

**The race and class buttons (RQ-172; N3FE version 25, `content/front-end.md` item
14 and "Actions").** Each race button carries its KO race code and the race's
default class, and each class button the specialty codes it stands for (one per
nation), the image 1298 and 1264 show in its place and the stat labels its click
marks; the recipe names them in the create screen's `races` and `classes`, and the
cook checks them against `character-create.json`. As 1298 (binary, "Races and
classes" above):
- A race click chooses the race, unchooses the class and, when the race changed,
  builds the new character from the race's create model (`models.create`; none
  drawn for a race without one) and clears the class's marks (`00604f90`,
  `005fd120`). With no class chosen the build takes the race's default class for its
  stat row (`005fd120`: 1→101, 2→102, 3→103, 4→104, 11→201, 12→202, 13→204), which
  RQ-173 shows.
- Once a race is chosen, the class buttons it cannot take (the races of
  `create.bin`: a race the package does not offer takes none) are hidden for their
  images and the images of those it can are hidden (`006060f0`; 1264 `0043ec90`).
  Before a race every class button draws over its image (the reset `006066b0`).
- A class click chooses, for the chosen race, the one of the button's specialties
  the race has, and marks its own labels: 1298's cream pair hidden (`006062d0`),
  1264's pink pair shown (`0043ee10`).
- Create refuses, after the name, no race and no class, the choice as the server's
  `Policy::choice` would (`create_choice_refusal`, Q95), in the server's words of
  that refusal, so a create the screen sends is one the server takes.

The 1298 recipe waits for both clicks (RQ-130); the 1097 choice chooses the Tuarek
and the priest at each open (Q52), its look at the open what Q89 to Q92 decided, its
rogue now a live button as 1264's (Q91). Moradon offers the Tuarek's rogue (102) and
priest (104), so both screens make either. The race buttons of races the package does
not offer stay as they drew (Q109 (a): fixed disabled; the 1097 choice's Puri Tuarek
unbound, Q90). The 1097 choice's `front-end.bin` grows from 56,347,416 to 56,348,696
bytes (the class column's nodes and pink labels it no longer hides, and item 14); the
package hash changes, so the hosted realm's next deploy is a new realm (Q63).

**The stat arrows (RQ-173; N3FE version 26, `content/front-end.md` item 15 and
"Actions").** The recipe names each stat's value text and its two arrows in the
create screen's `stats` (in `character-create.json`'s stat order), the points text
in `points` and the row's key in `stat_row`: `class` for 1298's race × 10000 + class,
`race` for 1264's race. As KO's ("The arrows" and "The build" above; KO-FINDINGS
§10.4, binary):
- Every build writes the row's five stats as the values and its bonus as the points
  left, so it resets the points spent: an open with the race chosen, a race click
  that changes the race and, with the `class` row, a class click that changes the
  class.
- A right arrow spends a point while any is left; a left arrow gives one back while
  the stat is above the row's and points have been spent, with the `class` row only
  once a class is chosen.
- The values and the points text are empty from each open until a build writes them.
  Each open starts with no points (Q111: KO keeps the points left at a Cancel).
- Create refuses points left with `create_points_left` (code 10, row 1913 under
  1901, a new message) after no race and no class, then sends the five stats.

Both recipes' `text_bonus`, hidden until now (Q52), shows the points left, and the
arrows are no longer fixed disabled; the face and hair stay the fixed choice's until RQ-174. The 1097 choice's
`front-end.bin` grows from 56,348,696 to 56,348,916 bytes (item 15 and the message);
the package hash changes (Q63).

**The face and hair arrows (RQ-174; N3FE version 27, `content/front-end.md` item
8 and "Actions").** Both recipes bind KO's `btn_face_left`, `btn_face_right`,
`btn_hair_left` and `btn_hair_right` (no longer fixed disabled). As KO's ("Face
and hair" above; KO-FINDINGS §10.5, binary):
- Each arrow steps its value by one, from 0 to `create.bin`'s last face or
  hair for the race (Moradon's 3 and 2, KO's), no wrap, with or without a race
  or class. With no race chosen the range is the fewest of `create.bin`'s
  races, and a race click takes a value past its range into it (Q112).
- The face and hair are kept from one open to the next, as no KO open writes
  them.
- The new character draws its face and hair parts by number: each create
  model in `front-end.bin` carries its parts without its face and hair, then
  its `faces` face parts and `hairs` hair parts (KO's `InitFace` and
  `InitHair` file names), the Wrinkle Tuarek none for hair; so its hair arrow
  moves the value and draws nothing new, as KO's.
- Create sends them; the server checks them under the race's counts (Q95).

The parts weighed against `front-end.bin`'s 64 MiB bound, which RQ-183 has
since raised to 256 MiB (local-asset, the pinned tree; `tests/ko_player_races.py`
cooks each):

| Race | Create model record before (bytes) | With its faces and hairs | Faces, hairs |
|---|---|---|---|
| 2 Tuarek | 1,014,644 | 1,303,588 | 4, 3 |
| 3 Wrinkle Tuarek | 1,405,652 | 1,508,788 | 4, none |
| 4 Puri Tuarek | 1,139,060 | 1,816,036 | 4, 3 |

Each part's scene repeats the model's nodes and joints (about 2.7 KB) but not
its clip; its texture is its own (128 × 128 for most, 256 × 256 for the
Wrinkle Tuarek's face 00 and the Puri Tuarek's hairs). The 1097 choice's
`front-end.bin` grows from 56,348,916 to 57,417,972 bytes and the 1298
recipe's is 59,297,737, both under 67,108,864, leaving the 1097 choice about
9.7 MB for the races RQ-165 and RQ-006 add (each about 1.3 to 1.8 MB with its
parts). The package hash changes, so the hosted realm's next deploy is a new
realm (Q63).

**The description text (RQ-175; N3FE version 28, `content/front-end.md` item 16
and "Actions").** The authored `class_desc` string is gone: the node bound to
`class_desc` (KO's `text_desc`) draws the create screen's `descriptions`, KO's own
rows from the recipe's client's table, in KO's yellow (`0xffffff00`). Each frame the
client takes the tooltip of the stat area, class button or race button whose rect
holds the pointer, in KO's loop order ("Descriptions" above; KO-FINDINGS §10.6).
Off them:
- the 1097 choice (`rest` `keep`, 1264's): the text stays the last tooltip, row 6124
  ("Karus Character Window.") from each open;
- the 1298 recipe (`rest` `chosen`, 1298's): the chosen class's tooltip, else the
  chosen race's, else nothing.

Two texts the realm's fonts cannot draw: the 1264 table's "ally's" in CP949 is drawn
with ASCII's apostrophe (Q113), and the 1298 recipe names no tooltip for the Puri
Tuarek, whose 1298 row is Korean (Q114). The 1264 table's MP-area row 3201 reads
"Unconfirmed nation", as 1264 shows it. The recipes name Karus's rows; El Morad's
(6125 and the El Morad column above) wait for RQ-006 to give an account a nation.
The 1097 choice's `front-end.bin` grows from 57,417,972 to 57,419,400 bytes, the
1298 recipe's from 59,297,737 to 59,299,044. The package hash changes, so the hosted
realm's next deploy is a new realm (Q63).

**The create dress (RQ-176; N3FE version 29, `content/front-end.md` item 8 and
"Actions").** KO's build dresses the new character in its stat row's items (1298
`005fd120`, 1264 `00439970`; above): the cook writes each create model's
specialties in the dress `ko_create.dress` resolves from the realm's
`create.table` (Q106, default (a)), so the 1097 choice, on 1264's table, draws
1264's one set per race, and the 1298 recipe 1298's set per class. Per model the
parts most of its specialties wear are the model's own; the others' parts follow
once each and are drawn in place of the model's (the 1298 Tuarek's priest set over
its rogue's body; on 1264's table both Tuarek specialties wear the rogue set). The
robe's lower is bare (the Wrinkle Tuarek mage draws three parts, `ko_create.dress`'s
null file), and the hand plugs hang on the looks row's joints: right hand column 18,
left hand column 19, a class-60 shield column 20 (KO-FINDINGS §10.7), each scaled
by the model's height as `PlugSet` scales it (the Puri priest's mace on joint 12 and
shield on joint 5). The client dresses the model as the specialty of the last build:
the chosen class's on 1298's rows, the race's on 1264's, kept while a second click
on the race unchooses the class (no build). A create without race buttons dresses
its fixed race's model as the fixed specialty. A dress with a helmet is refused at
the cook (Q115). The 1097 choice's `front-end.bin` grows from 57,419,400 to
58,460,464 bytes, the 1298 recipe's from 59,299,044 to 61,843,732 (within the
64 MiB bound, 5.2 MiB to spare for the races RQ-165 and RQ-006 add, whose dress
parts take room too; RQ-183 raised the bound to 256 MiB). The package hash changes, so the hosted realm's next deploy is
a new realm (Q63). RQ-169 adds the Arch Tuarek's dressed create model: the 1097
choice's file grows to 61,065,488 bytes, the 1298 recipe's to 64,447,160
(local-asset), both still version 29 then (31 since RQ-005, which grows them again: 62,338,435 and 64,447,563).

**The size of every race's create model (RQ-182; local-asset, the pinned tree).**
Cooked as RQ-165 and RQ-170 would add them (`content/front-end.md`, the bound):

| Race | 1097 choice (1264's table) | 1298 recipe (1298's table) |
|---|---|---|
| 1 Arch Tuarek | 2,342,872 | 2,341,276 |
| 2 Tuarek | 1,589,064 | 2,569,280 (4 dress parts) |
| 3 Wrinkle Tuarek | 1,175,838 | 1,171,694 |
| 4 Puri Tuarek | 2,118,130 | 2,121,378 |
| 11 Barbarian | 1,665,772 | 1,658,380, one plug refused |
| 12 El Morad male | 1,644,968 | 4,678,215 (12 dress parts) |
| 13 El Morad female | 1,660,456 | 4,164,940 (12 dress parts) |

Each record's bytes with its race code; the textures its plugs add to the table
come on top (0.26 MB a 256 × 256 texture). RQ-165: none holds an influence table
(each N3S1, but the Arch Tuarek's N3SM on both tables and the El Morad male's on
1298's; RQ-169 checked it): every dress here replaces the looks lower part, whose vertices past four joint
influences (the Arch Tuarek's 49, the El Morad male's 57) are then not drawn.
Undressed (looks parts, four faces, three hairs) the two are N3SI, 2,780,584 and
1,341,684 bytes, which front-end records hold since RQ-165 (N3FE's tables version, 32 since RQ-005,
engine 45; `content/front-end.md` "Influence tables").
Found on the way, for RQ-170 and RQ-006: on 1298's table the Barbarian's plug
`Item/1_2641_00_0.n3cplug` is refused by the mesh reader ("KO normal"), as are
the 1097 choice's El Morad halls `ChrSelect/el_chairs.n3shape` and
`el_elmo_chairs.n3shape`, and 1298's El Morad select zone (10000) names four
object files the pinned tree lacks (`Object/obj_war_duntree01_ip00`–`ip02`,
`_po.n3pmesh`).

## What each item needs

- **RQ-002 (wire and server).**
  - `CreateCharacter` gains slot, race, class, face, hair and the five stats. Nation
    is the account's, set by RQ-006; until then it is Karus.
  - The character list gains race, class, face, hair, nation and the visible items.
  - The server validates as Q95 takes it, from package rules (RQ-003):
    - the race is offered and its nation is the account's;
    - the class is in the race's set;
    - face 0..3 and hair 0..2;
    - each stat ≥ the base, the sum exactly base + bonus;
    - the name as Q99;
    - the slot free and under the limit.
  - It answers with KO's codes (1–5, 17), each a distinct wire error the client maps
    to its row, never "success" on an internal failure.
  - A migration adds the columns, and Postgres keeps them.
- **RQ-003 (content).** For each race:
  - its looks row and model;
  - its faces and hairs (the Wrinkle Tuarek without hair);
  - its base stats and bonus, and its class set.

  For each class: the create dress (by the chosen table; RQ-159, checked, drawn by
  RQ-004 and RQ-005), the starting items and a weapon it can use (Q96; RQ-160,
  checked; RQ-154 grants them),
  and the skills and class rules RQ-007 needs. All of it is package data under
  `games/moradon`.
- **RQ-004 (screen).** As 1298 draws it:
  - the nation's race buttons, all live (RQ-172; Q109 for races not offered);
  - the class buttons enabled per race, the others hidden for their images (RQ-172);
  - the default class on a race click (RQ-172);
  - face and hair arrows that clamp;
  - the stat arrows, with every build resetting the points;
  - the description texts and the hover;
  - the create model in its specialty's create dress (RQ-176);
  - the client checks in order, with no confirm dialog;
  - errors in KO's titled box (Q61).
- **RQ-005 (select).** Each character drawn from its race's looks, face, hair and
  visible items.
  - Done in RQ-005: each character gets its race and class's select joint, clips and
    plugs (`select.characters`, content/front-end.md item 17).
  - Done in RQ-005: the info bar shows the class from KO's class-name map
    (`select.class_names`; KO-FINDINGS §8.5).
  - Not yet: face, hair and visible equipment per character. These are RQ-005's
    follow-ups.
- **RQ-006 (nation).**
  - The login answer's nation 0 opens nation select. The question is 10420, with OK
    and Cancel; Back returns to the server list.
  - The nation is set per account (Q98).
  - Read the 1097 click path and 1298's delete-last-character return.
- **RQ-007 (play).** Per race and class: the model in the world, class weapons,
  skills and the server's class stat rules. The stats sent at create are the
  character's base.
- **RQ-008 (delete).** Deleting the last character returns the account to nation
  select (source). Whether the realm resets the account's nation then is RQ-008's
  question with Q98's default.

## Not read (open)

| What | Where it goes |
|---|---|
| ~~`006dfe28`'s writers~~: read in RQ-175, none (KO-FINDINGS §10.6); a 1298 build clears a typed name | RQ-135 carries it |
| ~~The hover text's join order and separator~~: read in RQ-175, no join (above) | — |
| 1097's nation-select click path | RQ-006 |
| 1298's delete-last-character return | RQ-006/RQ-008 |
| The 1298 list parse | RQ-005's equipment follow-up (RQ-005 drew race and class only) |
| The game-start stat recompute (HP, MP, SP) | RQ-007 |
| Ebenezer's word-list loader | Q99 takes a realm-owner list instead |
| Whether the 1298 binary's create sets `edit_name`'s length (the layout carries none, source) | RQ-004's later parts |
