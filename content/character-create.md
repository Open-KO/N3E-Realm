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
- 1264 and 1097 have the same ranges (binary).

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
  runs. The reset `006066b0` writes them empty (§9.15).

**The build** (`005fd120`, binary):
- With no class chosen it takes the race's default class to look up the row: 1→101,
  2→102, 3→103, 4→104, 11→201, 12→202, 13→204. So the race click alone fills in
  the stats and the bonus.
- It copies the row's five stats (`+0x14`..`+0x24`) and its bonus into both `+0xb0`
  and `+0xb4` (`+0x28`). **Every build resets the points spent.**
- It returns early if the race has no `UPC_DefaultLooks` row.

**The create dress.** With a row, the build dresses the model in the row's items:
- parts 0..9 from `+0x34 + 4i` (`dwIDK[2..11]`; the five armour pieces);
- the face through vtable `+0x28`;
- the right- and left-hand plugs from `+0x2c`/`+0x30` (`dwIDK[0]`, `[1]`), looked up
  in the item table (`DAT_008186f4`) and attached by `FUN_006157b0`.

Without a row it uses the looks parts. Each 1298 class row names its own weapon and
armour set; 1264's rows name one set per race (a weapon and five armour pieces). 1097
has no item columns: its SetChr (`004359f0`) draws the looks parts.
(Local-asset; binary.)

The dress is only the create screen's: the server does not create those items (below).

**The server's floors** are Ebenezer's own, not the table's (below). They equal
1264's and 1298's bases.

## Descriptions

1298 Load `00603850` and MouseProc `00605bf0`, binary. Text rows (the pinned
`Texts_us.tbl`; the US rows for the four Karus race tooltips are Korean text,
local-asset):

| What | Karus | El Morad |
|---|---|---|
| Panel text at open (`text_desc`, `+0x15c`) | 6124 | 6125 |
| Warrior | 3217 | 3209 |
| Rogue | 3215 | 3208 |
| Mage | 3212 | 3205 |
| Priest | 3213 | 3207 |
| Races | ka_at 3211, ka_tu 3216, ka_wt 3218, ka_pt 3214 | el_ba 3203, el_rm 3206, el_rf 3204 |
| Stat areas | str 3219, dex 3202, sta 3220, int 3210, map 3201 | the same |

**Hover.** MouseProc sets `text_desc`'s colour to `0xffffff00` and its text to the
tooltip of the stat area, class button or race button under the pointer. Off them it
shows the chosen race's text joined with the chosen class's, or nothing when none is
chosen. The join was read loosely: RQ-004 confirms its order and separator.

**What a build writes.** `00605950`, run by each build, also sets `text_desc` and
`edit_name` from the global `006dfe28`, which is empty in the image. So a build
probably clears a typed name. Its writers are RQ-135's (binary, open).

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
| Starting zone | the server's, not the client's | the server's | the server's | `create.start` (Q96) |

The settings are a proposal for RQ-002 to land in `games/moradon/realm-config.json`
(today `{"front_end": "1097"}`). The cook checks them against the package. No engine
module names a race, class or zone.

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
| `content` | the races the package has a player model for (Moradon: the Tuarek, 2; RQ-003, below) |
| `player` | the race of the package's player scenes, one of `content` (Moradon: 2; RQ-003) |
| `tables` | the stat tables a realm validates against, by id: each a KO `values` table (`Data/NewChrValue.tbl`) read from the front end's inputs (a `<name>:` prefix as the recipe's paths), its row `key` (row id = race × `race` + specialty × `specialty`: 1264's `{1, 0}`, 1298's `{10000, 1}`) and the `texts` table its refusals are worded from |
| `columns` | the values table's stat columns and bonus column (KO's 2..6 and 7) |
| `front_ends` | the table each front-end client draws by default (Q97 (b): 1264's for the 1097 choice, 1298's for the 1298 recipe) |
| `refusals` | the text row of each refusal: `limit` 1911, `mismatch` 1907, `taken` 1912, `failed` 1902, `name` 1906, `stats` 1915 |
| `name` | the name rule: `min` 1, `max` 20, `punctuation` `_:;` beside ASCII letters and digits (Q99) |
| `fixed` | the choice a create without a race takes (Q100): race, specialty, face, hair and the bonus `points` per stat; Moradon's the Tuarek priest, face 0, hair 0, the ten points in MP |

The realm owner's `realm-config.json` may add `create`: `table` (Q97, default the
front end's), `races` (Q94, default `content`; only races in `content`) and
`reserved` (Q99, words no name may contain, compared without regard to case;
default none). `create.start` and `create.items` are not settings yet (Q101).

**The cook.** `make realm-assets` (`ko_bake.py --features`) checks both files with
the front-end choice, before the survey (`tools/assetc/ko_create.py` `plan`, through
`front_end_choice.choose`), then reads the chosen table and text rows from the front
end's inputs (`build`). It refuses a malformed file or setting, a table the package
lacks, a race without a player model, a table row whose race or specialty the
package lacks, a missing row the offered races need, and a fixed choice the rules
refuse. The package's manifest gets a `create` section, which
`tools/assetc/create.py` cooks into `create.bin` (N3CC version 1, little-endian u32s
and u32-length ASCII strings):

```
"N3CC" 1 stats nation race_count
  per race: race nation faces hairs specialty_count
    per specialty: specialty bonus base[stats]
name_min name_max punctuation reserved_count reserved[...]
refusal text × 6 (limit, mismatch, taken, failed, name, stats; empty keeps the engine's)
fixed (0 or 1) [race specialty face hair stats[stats]]
```

Bounds: 1..8 stats, nation 1..255, 1..32 races of 1..16 specialties, ids 1..65535,
1..256 faces and hairs, bonus and base 0..1000, name 1..24 bytes, up to 256 reserved
words (lower-case printable ASCII, 1..24 bytes), refusal texts printable ASCII up to
200 bytes. The server (`server/src/create.rs`) and the client
(`client/assets/assets.cpp`, magic and version only until RQ-004 reads it) refuse
any other file; the server's `--check-content` prints `create races=… specialties=…
stats=… nation=… fixed=…`. A package without `create.bin` creates by name alone, as
before. The Moradon package is the only one with rules; its table is 1264's for the
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

**What stays.** A new character starts at the package's spawn with its `starting`
items (Q96 (b)); the stats are kept but play does not read them yet (RQ-007); the
screen still sends a name alone (RQ-004); one nation (RQ-006).

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
| 1 Arch Tuarek | all six | 00..03, 00..02 | yes: its 49 lower-part vertices with five joint influences keep all five, as KO sums them, in N3SI player scenes (engine 43, RQ-163); its 2185 rotation keys of length 0 read (RQ-156) |
| 2 Tuarek | all six | 00..03, 00..02 | yes (the package's player) |
| 3 Wrinkle Tuarek | upper, face, hands, feet | 00..03, none | yes |
| 4 Puri Tuarek | all six, on the El Morad female joint | 00..03, 00..02 (03 unreached) | yes |
| 11 Barbarian | all six | 00..03, 00..02 | yes (its 19 rotation keys of length 0 read as KO draws them, RQ-156) |
| 12 El Morad male | all six | 00..03, 00..02 | no: clip 93, `breath_CrossBow0`, has 0 frames a second ("animation metadata") |
| 13 El Morad female | all six | 00..03, 00..02 | yes |

Every face and hair the screen reaches is opaque, as the player path draws. Every clip
table has 136 clips, and each one the reader reads (all but the El Morad male's) has
the clips the player cook converts. KO draws a joint on or between rotation keys
of length 0 unrotated (RQ-156, binary: `00411950`, `00427640`, `0064d002`,
`0064cad6`; `specs/KO-FINDINGS.md` §10.1), and the reader converts that frame as
the identity rotation. How KO draws a clip at 0 frames a second is unread; the
reader keeps refusing it.

**Not in the package yet** (Q102). Only the player race's model is cooked into the
package. `content` stays the Tuarek: a race joins it with the item that ships its
model in the form its first consumer draws (the create screen RQ-004, the select hall
RQ-005, the world RQ-007). The class data (the create dress, starting items and
weapons, skills, class rules) is open too.

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

  For each class: the create dress (by the chosen table), the starting items (Q96),
  and the skills and class rules RQ-007 needs. All of it is package data under
  `games/moradon`.
- **RQ-004 (screen).** As 1298 draws it:
  - the nation's race buttons, all live;
  - the class buttons enabled per race, the others hidden for their images;
  - the default class on a race click;
  - face and hair arrows that clamp;
  - the stat arrows, with every build resetting the points;
  - the description texts and the hover;
  - the client checks in order, with no confirm dialog;
  - errors in KO's titled box (Q61).
- **RQ-005 (select).** Each character drawn from its race's looks, face, hair and
  visible items.
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
| `006dfe28`'s writers: whether a build clears a typed name | RQ-135 |
| The hover text's join order and separator | RQ-004 |
| 1097's nation-select click path | RQ-006 |
| 1298's delete-last-character return | RQ-006/RQ-008 |
| The 1298 list parse | RQ-005 |
| The game-start stat recompute (HP, MP, SP) | RQ-007 |
| Ebenezer's word-list loader | Q99 takes a realm-owner list instead |
| Whether the layout's `edit_name` carries a length limit | RQ-004 |
