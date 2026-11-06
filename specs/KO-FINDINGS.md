# KO findings for the Realm architecture

Date: 2026-10-30. Static analysis only, Ghidra 12.1.3 headless (`-readOnly -noanalysis`)
against the `ko-audit` project, output under `n3e/build/ghidra/arch/r1/` (not committed).
Binaries as pinned in `n3e/docs/ko/COVERAGE.md`. **Binary** unless marked **source**
(`ref/ko-src`) or **local-asset** (text tables). Where `n3e/docs/ko/` already had the
finding, it is cited rather than redone.

Each section ends with what it decides for us.

## 1. Server shutdown: `/serverdown N` and `/down` (P1)

| Observation | Where |
|---|---|
| `/serverdown N`: `N` parsed with `atoi`, must be ≥ 0, stored as a byte (so ≤ 255 min). Records start day/hour/minute and sets an "armed" flag. | S `004250cc` (console parser, `/serverdown` branch), fields `+0x4c950..+0x4c955` |
| A timer function recomputes minutes remaining each call. **On every minute change** it broadcasts a notice; when remaining reaches zero it sets the global down flag, logs `#### Server Down Command : serverdown ####`, `SuspendThread(main)`, runs `/down`, clears the fields, and exits the process (`FUN_005cc40d(0x115,7,0)` → terminate). | S `0043333a` |
| The per-minute notice is `thunk_FUN_00428b8c(0x13, nation=0, chat_type=7, minutes)`: message id `0xc1` = **193 `IDS_SERVER_AUTO_DOWN` "The server will shutdown after %d minutes."**, wrapped in `0x7e` = **126 `IDP_ANNOUNCEMENT` "#### NOTICE : %s ####"**, sent as `WIZ_CHAT` (`0x10`) with chat type **7 `N3_CHAT_PUBLIC`** to every in-game user (state 3), all nations. | S `00428b8c`; ids **source** `db_resources.h`; chat enum **source** `PacketDef.h` |
| `/down`: iterates all 1500 user slots, logs `KickOutAllUsers : %s / %s`, closes each socket (state := 3, `PostQueuedCompletionStatus`), **`Sleep(1000)` between users**, then logs "All User Connection Close". **No packet is sent to the user before the close.** | S `0042ade4`, `004338a5` (log), `00445f77` (close) |
| `/kill <name>` (≤ 20 chars): same silent close for one user. | S `00427587` |
| Client reaction to a dropped socket: text 1601 **`IDS_CONNECTION_CLOSED` "Disconnected from server"**, back to the login flow. | **source** `text_resources.h`, `GameProcLogIn_*.cpp` |
| Client rendering of chat type 7: yellow (`ARGB 255,255,255,0`) line in the chat window. Type 9 `N3_CHAT_TITLE` is a top-of-screen title line; type 11 `N3_CHAT_CONTINUE` a persistent notice; type 8 `N3_CHAT_WAR` a bold centred message. | **source** `GameProcMain.cpp` ~2258 |
| Reference source has `OperationMessage::ServerDown()` as `// TODO` — the binary is the only evidence. | **source** `OperationMessage.cpp` |

**Decides:** the force-deploy warning should be **in game, once per minute, in the
chat as a yellow NOTICE line**, with the exact wording above, for a configurable `N`
minutes (KO defaults are operator-chosen; our CD uses 2). The final kick is silent in
KO; we can do better (an `Error`/reason before close) without breaking expectations.
A sequential 1 s/user close is KO's way of not flooding the login server; irrelevant to
us. → **Q13: in-game notice is v1**, implemented as a `notice` admin operation that
broadcasts chat type "public notice"; the CD countdown uses it.

## 2. Rate events: `/money_add N`, `/exp_add N` (P1)

Already catalogued as **KOF-0063** (`n3e/docs/ko/FEATURES.md`, `BINARY-INDEX.md`);
re-read the game-server side to confirm:

| Observation | Where |
|---|---|
| `N` is `atoi`'d and accepted only when **0 ≤ N ≤ 15**; stored as a short (`+0x4c826` coin, `+0x4c828` XP). | S `004250cc` lines ~223–280 |
| The value is pushed to the **AI server** as packet `0x44` sub 1 (coin) / sub 2 (XP) with the short; AI applies it (coin after its 70–100 % draw; XP with per-nation bonus bytes; AI stores at `+0x3212/+0x3214`). | S `0041ea0e` send; AI `00408447` (KOF-0063) |
| If `N > 0`, an immediate broadcast: id **187 `IDS_MONEY_REPAY_EVENT` "Coin event has started. You will earn an additional %d percent of coins for killing mobs."** / **197 `IDS_EXP_REPAY_EVENT` "Experience point event Started. You will Earn %d Percent of Experience for killing Mobs."**, chat type **8** (`N3_CHAT_WAR`, bold centre) to all. `N = 0` is the "off" switch and announces nothing. | S `004250cc` → `00428b8c` cases `0x11`, `0x14` |
| **Login notice** (`2e`) appends the active event lines after the `Notice.txt` lines, so late joiners see them. (Binary quirk: the coin line is formatted with the XP value.) | S `004a9488` |
| **No duration, no expiry, no persistence** in the game server: the value lives until changed or process exit; startup reads `BONUS_EVENT` from the INI (KOF-0063). | S `004214d0` (INI) |
| "Royal" king events (`KING_UPDATE_NOAH_OR_EXP_EVENT`) write the **same AI fields** with a treasury cost (KOF-0044). | per catalog |
| Semantics are **additive percent**, realm-wide (all zones, both nations), applied at kill-reward time by the AI server. | KOF-0063 |

**Decides (Q6):** spec 10's presets are a superset: KO = one global additive percent
per resource, 0–15, no timer, announced at set time and at login. Ours: named presets,
multiplier bounds `0.1..10`, timed with auto-revert, announced at start/stop and shown
in the catalog. Keep **"announce at activation + show to late joiners"** (the login
notice / MOTD path) — it's what players expect. Note the deviation (we allow more than
+15 %) in `BALANCE.md`.

## 3. Login-time notice `2e` (P1)

| Observation | Where |
|---|---|
| Gated by a server flag (`+0x4c94e`, "notice enabled"). Up to **20 lines × 127 bytes** from `Notice.txt`, then active event lines, then nation-specific king-event lines. Packet: `2e`, u8 count, then `u8 len + bytes` per line. | S `004a9488`; file load `00426467`; reload `/reload_notice` `004c66dc` |
| Client: clears the notice window, pushes each line, lays it out **top-right** (`x = viewport width − width, y = 10`) and shows it. | **source** `GameProcMain.cpp` `MsgRecv_Notice` |

**Decides:** we want a **MOTD** equivalent: a revision property (string) shown by the
client on entering the world, plus active-preset lines appended by the server. Adds a
small wire message (`Notice { repeated string lines }`) and a client panel. → fold into
Q13's engine item.

## 4. Authority byte, bans, mute, attack-disable (P1)

Fully resolved in `n3e/docs/ko/investigations/d-moderation-interserver.md`; summary:

| KO state | Value | Semantics | Persisted |
|---|---|---|---|
| manager | 0 | all `+`/`/` commands, notices, invisibility | yes (DB) |
| user | 1 | normal | yes |
| muted | 11 | all chat silently dropped (`004989a8`) | yes, no expiry |
| attack-disabled | 12 | melee dropped (`00496169`), some magic refused | yes, no expiry |
| limited manager | 250 | packet `40` moderation subs; no notices/commands | yes |
| blocked | 255 | silent close at game start (`00492b0c`) | yes, **permanent unless a stored procedure clears it**; the timed `FORBID_USER (DATEADD hours)` exists only under one regional config and nothing reads its expiry |

One shared byte: mute and attack-disable **replace** each other, and un-muting sets 1
(can demote an operator). Sanctions are per **account authority loaded into the
character** at login; the client shows "A blocked user! Disconnecting now.." only on
the character-select path, otherwise just "Disconnected from server".

**Decides (Q14):** our model is already better (timed bans, reasons, audit, kick with a
reason). Add **`mute`** as a v1 account state (it's the most used moderation tool in
KO and trivial: drop chat server-side, tell the player once). **Attack-disable: defer**
— it exists to stop PK griefing, which our realm doesn't have yet. Both become
`account.mute` / `account.unmute` routes and `accounts.muted_until`. Enforce silently
like KO but **tell the muted player** on their first dropped message.

## 5. Client wording for failure paths (P2)

| Situation | KO client text | Source |
|---|---|---|
| Server dropped the connection | "Disconnected from server" (1601) | **local-asset/source** |
| Version mismatch at login | "This client is version %.3f. You'll need to have version %.3f in order to log in to the server." (4801); TW variant "This is an outdated version. Please install the newest client." (4803) | **local-asset/source** |
| Blocked account (char select) | "A blocked user! Disconnecting now.." | **local-asset** (investigation D) |
| Login failure (generic) | "failed logging into the game" | **local-asset** |

**Decides (Q10 wording):** client exit `3` message: *"Your client is version X; the
realm requires Y. Close this window and run the launcher to update."* Disconnect:
*"Disconnected from server."* Ban: *"Your account is blocked until … : <reason>."*
Kick: *"You were disconnected by an operator: <reason>."*

## 6. Server list / user count (P2)

`f5` carries per-server user count to the client's server-select screen (catalogued,
`identity-social.md`). We have one realm and no server-select; the count is exposed
only via the role-gated Discord `/status`. **Decides:** do not expose player count on
any unauthenticated path (it's an attack-success metric). Already the spec default.

## 7. Packet-rate sanity (P2)

Catalogued (`world-npc-ai.md`): > 10 consecutive movement packets < 0.1 s apart →
disconnect; per-packet horizontal limit 23.625 m; DB-agent packet-count timer 120 s.
Our client sends 20 Hz input (every 50 ms) by design, so KO's "< 0.1 s" heuristic is
not a bound we can reuse; n3e's own 100 frames/s per peer cap stands. **Decides:**
nothing to change in spec 01 defaults.

## 8. Character select: the character in front (RQ-066, 2026-11-01)

Ghidra 12.1.3 headless (`-readOnly -noanalysis`), `ko-audit`, `KnightOnLine.exe`
(1298), output under `N3E-Realm/build/ghidra/rq066/` (not committed). The clip
setter `0041be40(index, once, blend, freeze, upper)` and the frame tick `00418b20`
are n3e's PQ-273 reading (`n3e/docs/implementation/evidence/pq-273-ko-npc-zero-length-clips.md`):
with the once flag the tick puts the frame on the clip's end and leaves it there, and
a call naming the clip already set starts nothing.

| Observation | Where | Label |
|---|---|---|
| The later source's hover: `DoProcPreselect` sets `AniCurSet(SELECT_ANIM_PRE_SELECT, true)` (clip 0, once and freeze) on the character in front while the pointer is in the rect 0.36–0.64 × 0.44–0.86 of the viewport, and `AniCurSet(SELECT_ANIM_DUMMY, true)` (clip 2) otherwise; `PRE_SELECT` 0, `SELECTED` 1, `DUMMY` 2 | `GameProcCharacterSelect.cpp` `DoProcPreselect`, `.h` | source |
| In `ChrSelect/upc_ka_at_wa.n3anim` (the set the Moradon package cooks) the clips are `pre_select` 10–65, `selected` 65–200 and `dummy` 10–10, at 30 frames/s: `dummy` is `pre_select`'s first frame | the pinned tree | local-asset |
| 1298 has no hover. The rect's four reals (`006a402c` 0.36, `006a4024` 0.64, `006a4028` 0.44, `006a4020` 0.86) are each read once, at `005fafa1`–`005fafe2`, in the select tick `005faf10`, and only for a left click while the select state `+0x394` is 5: `PtInRect` on the click point, then start the character or (an empty slot) go to create | `005faf10` | binary |
| In state 5 (the camera at rest on a slot, `005fe5b0` case 5) `005fef90` sets, every tick, clip 1 **looping** on the character in front (`0041be40(1, 0, FLT_MIN, 0, 1)`, pushes `005fefab`–`005fefb6`) and clip 0 once on the others (`0041be40(0, 1, FLT_MIN, 0, 1)`, `005fefee`–`005feff9`), whatever the pointer does; while the camera turns (cases 1, 2, 6) every character gets clip 0 once | `005fef90`, `005fe5b0` | binary |
| Start (`005fe7c0`, state 5 only): clip 2 once with a 0.6 s blend (`0041be40(2, 1, 0x3f19999a, 0, 1)`, `005fe7e6`–`005fe7fd`), state 4; state 4 (`005fea70`) loads the world once the clip has played (`+0x1e4`, or the upper body's `+0x20c`, above 0): `IsAnimEnd` | `005fe7c0`, `005fea70` | binary |
| 1298 poses the select characters from per-race files: a Tuarek (race 2) rogue or priest (classes `0x66`, `0x6b`, `0x6c`, `0x68`, `0x6f`, `0x70`) loads `ChrSelect\upc_ka_tu.n3joint` and `upc_ka_tu.n3anim`; no `upc_ka_tu_pri` or `_wa` name is in the binary | `005fb4f0`; strings | binary |
| `ChrSelect/upc_ka_tu.n3anim`'s clips are 180–220 at 25 frames/s, 20–300 at 30 and 394–466 at 25, blend 0.25 s, no loop delay (flags 0) | the pinned tree | local-asset |

**Decides:** the Moradon package cooks the later source's set (`upc_ka_tu_pri.n3joint`,
`upc_ka_at_wa.n3anim`), so the hall plays it as that source does: the character in
front plays `pre_select` once when the pointer comes over it and holds its last frame
while the pointer stays, back to the first frame when it leaves. That is not 1298,
which loops a different clip of a different set on the character in front with no
pointer involved; which hall the realm shows is **Q71**.

### 8.1 The 1097 client's select hall (RQ-074, 2026-11-01)

The 1097 client is `build/ko-reference/installer-1097/client/KnightOnLine.exe`
(sha256 `04ab5c54…2b771d4c`, from the installer `KnightOnline_1097.exe`,
`d7571e18…`). It is packed with ASProtect: an ASPack-2.12-style stub at `006f6001`
in the last named section, an empty `.adata` section, and an SEH-driven loader in
heap memory. It was unpacked like this:

- A copy ran under Wine 11.20 (WoW64) in a throwaway `WINEPREFIX` under
  `build/rq074/`, inside `unshare -n -c` (no network) and `xvfb-run`.
  `winemenubuilder` was disabled from the second run on.
- The runner was a child subreaper, so Yama allowed it to read `/proc/<pid>/mem`.
  It copied the image (`00400000`–`00708000`) every few milliseconds.
- The kept snapshot is the one after the last code-section change and before the
  program started (0.95 s; sha256 `faaaec68…82cad191`). The process left on its own
  at about 1.2 s, after a failed display-mode change; any left over was killed.

The snapshot was rebuilt into a PE (sha256 `82abb582…ea8febaf`):

- Raw layout equals the virtual layout.
- The entry is `00575e47`, VC6's `WinMainCRTStartup`. ASProtect stole its first 38
  bytes, which stay zero.
- A new import directory sits on the original IAT, `0058c000`–`0058c380`. 204 of
  its 213 slots resolve through the export tables of the Wine DLLs in the process;
  kernel32's go through ASProtect's redirect stubs. The 9 kernel32 slots ASProtect
  emulates are named `aspr_<slot>`.
  *Corrected by RQ-096 (§9.1):* the stubs' kernel32 names are one stub late. Each
  stub's alternate code (the stolen bytes and the jump into the API) precedes it,
  where `build/rq074/tools/rebuild.py` reads the one after it, so a slot carries
  the name of the slot after it: VC6's CRT calls `GetStartupInfoA` through
  `0058c144` (named `MoveFileA`), and `0052d371` calls `GetUserDefaultLangID`
  through `0058c198` (named `GetLastError`; RQ-085's row reads it as the language
  id). The other DLLs' slots resolve directly and are unaffected. This 1097 dump
  was not rebuilt again.

It was analysed with Ghidra 12.1.3 (full analysis) in the project
`build/ghidra/rq074/` with `AuditReference.java`. The scripts are in
`build/rq074/tools/`. Nothing here is committed. Addresses are the 1097 image's
(base `00400000`).

| Observation | Where | Label |
|---|---|---|
| The select proc's vtable `0058cd10` holds Init `0043a950`, Tick `0043b550` and Render `0043b840`. Tick ends in the state switch `0043e4e0` (`CheckJobState`) on `+0x2cc`: 1 is turning (the rotate checks), 2 calls `0043f280`, 3 calls `0043ed20`. This is the source's `PROCESS_ROTATEING`/`PRESELECT`/`SELECTED` | `0058cd10`, `0043e4e0` | binary |
| **1097 has the hover.** Every tick in state 2, `0043f280` (`DoProcPreselect`) scales the rect's four reals (`0058cd6c` 0.36, `0058cd64` 0.64, `0058cd68` 0.44, `0058cd60` 0.86) by the viewport (device `GetViewport`, vtable `+0xa4`). It tests the pointer (`s_pLocalInput` `+0x1c`/`+0x20`) strictly inside. **Inside:** clip 0 (`pre_select`), once, on the character in front, `00447e30(0, 1, FLT_MIN, 0, 1)` at `0043f36a`–`0043f375`; that character is ticked; its spot theta `+0x2d0` grows by 0.02 per call up to 0.5 (nation 1) or by 0.015 up to 0.38 (nation 2); `0043f280` shows the info text (`004402a0`: UI child `text00`, string 1201, or 1202 for an empty slot). **Outside:** clip 2 (`dummy`), once, `00447e30(2, 1, FLT_MIN, 0, 1)` at `0043f425`; the character is ticked; theta shrinks by the same step down to 0; `text00` is hidden (`004405a0`). Then the front slot's spot (light index + 4) gets the theta through `SetLight`/`LightEnable` (`+0xb0`/`+0xb8`), and is disabled at 0 | `0043f280` | binary |
| The clip setter `00447e30(index, once, blend, freeze, upper)` returns without change when the index is the current clip's (`+0x1c0`). For a blend of `FLT_MIN` (`0058cf2c`) it uses the clip's own blend time (record `+0x2c`), and a blend above 0 starts from the previous frame. The frame tick `00445bb0` is called only from `CN3Chr::Tick` (`004457d0`, slot `+0x1c` of the vtable `0058cedc`). During a blend it keeps the frame on the clip's start. Past the end, a once clip holds its last frame and counts a loop (`+0x1d0`). A looping clip whose flag bit 0 is set holds its end and blends back to its start | `00447e30`, `00445bb0`, `004457d0` | binary |
| Only Tick moves a character. Render (`0043b840`) draws the three (`004466f0`, which ticks no clip). AddChr (`0043ba10`) ends by setting clip 0 once with blend 0 on all three and ticking each once (`0043cee1`–`0043cf0b`). So the characters not in front stand on the start of `pre_select`, and the one in front moves only through `0043f280`. While the camera turns (state 1) nobody is ticked | `0043b840`, `0043ba10` | binary |
| Click: Tick `0043b550` takes a left click outside state 1 when `PtInRect` finds the point in the same rect (`0043b6f7`–`0043b738`). It then starts the slot's character, or goes to create for an empty slot. Select, `0043ea30` (reached from `0043db54`, in state 2 only), moves to state 3, sets clip 1 (`selected`) once with a 0.6 s blend (`push 0x3f19999a` at `0043ea77`, the call at `0043ea8e`) and sets the spot to 0.5 or 0.38. In state 3, `0043ed20` runs until the clip's loop count reaches 1 (`+0x1f8` with an upper clip, else `+0x1d0`; this is `IsAnimEnd`). Until then it sets clip 1 again (which changes nothing), ticks and fades out. After that it releases the music and activates the main proc (`00545ae0`) | `0043b550`, `0043ea30`, `0043ed20` | binary |
| AddChr `0043ba10` loads the select models per race and class. Race 1: `upc_ka_at_wa.n3joint` and `.n3anim`, great axe. Race 2: rogue (`0x66`, `0x6b`, `0x6c`) `upc_ka_tu_rog.n3joint` with bow and quiver; priest (`0x68`, `0x6f`, `0x70`) `upc_ka_tu_pri.n3joint` with mace; both use `upc_ka_at_wa.n3anim`. Race 3: `upc_ka_wt_ma.n3joint` with the at_wa clips and staff. Race 4: `upc_el_rf_pri.n3joint` with `upc_el_rf_wa.n3anim`. El Morad uses the `upc_el_*` files. The binary has no `upc_ka_tu.n3joint`/`.n3anim` name. All this is the later source's `AddChr` | `0043ba10`; strings `005a1fb0`–`005a23b4` | binary |
| 1097's `ChrSelect/upc_ka_at_wa.n3anim` is byte-identical to the pinned tree's (`2c1d83e8…`): `pre_select` 10–65, `selected` 65–200, `dummy` 10–10, all at 30 frames/s with a 0.3 s blend; flags 1 on the first two, and `dummy`'s flag word is `0x3e99999a`, bit 0 clear. Rechecked against the record layout (RQ-075): each record is a zero word, the eight reals start, end, frames/s, two trace frames, two sound frames and blend, the flag word, two strike reals and the name, and the table parses to its last byte (183). So `dummy`'s blend is its ninth word (0.3, as the other two) and its flag word, the tenth, really holds `0x3e99999a`, the bit pattern of 0.3f: an authoring slip, not a misaligned read. `00447e30` reads the blend at `+0x2c` of the loaded record (`szName` 16 bytes, then the reals from `+0x10`); the flag word, `+0x30`, matters only to a looping clip, and every clip here plays once. `upc_ka_tu_pri.n3joint` and `upc_ka_at_wa.n3joint` match the pinned tree too. 1097 ships no `upc_ka_tu.*`. The other select tables (`pre_select`/`selected`, all `dummy` 10–10 at 30 frames/s, blend 0.3 s): `upc_ka_wt_ma` 10–46/46–290, `upc_el_ba_wa` 10–70/70–200, `upc_el_rf_wa` 10–100/100–260, `upc_el_rm_wa` and `upc_el_rm_rog` 10–60/60–200, `upc_el_rm_pri` 10–60/60–305 | `ChrSelect/*.n3anim` (`tools/assetc/ko_character.py` `animations`) | local-asset |

**Decides:** the hall the Moradon package cooks is KO's own, from 1097. It is not
only the later source's. 1097 loads the same files the package cooks and plays them
as that source does. The character in front plays `pre_select` once while the pointer
is in the centre rect and holds its last frame. When the pointer leaves, it goes back
to `dummy` (`pre_select`'s first frame). 1298 changed this later, to per-race files
and a looping clip 1. So Q71's default (a) is KO's behaviour, not a departure from it.

Within (a), three details differed from the client; RQ-075 aligned them
(`content/front-end.md`, "Moradon"):

- A 0.3 s blend goes in each direction. Going in, `pre_select` stays on its first
  frame for the blend.
- The spot widens only while the pointer is over the character in front (0.02 per
  tick to 0.5 for Karus), narrows when the pointer leaves, and is off at 0.
- The info text shows only while the pointer is over the character in front.

RQ-075 also read what the turn does to them (binary, the same image):

| Observation | Where | Label |
|---|---|---|
| Every select tick turns all eight lights off (`LightEnable(i, 0)`, vtable `+0xb8`, the loop before the hall lights' tick) and then runs `0043e4e0`; only states 2 (`0043f280`) and 3 turn the front spot on again. So while the camera turns (state 1, which moves only the eye) the spot is off and no character is ticked | `0043b550` | binary |
| The spot's theta `+0x2d0` is stored only by the constructor (`0043a4e0`, which sets the vtable `0058cd10`; the store at `0043a56c`), by Init (`0043a950`: `0043a9b8`, `0043aabf`), by Select (`0043eabc`) and by `0043f280`: a byte scan of the select proc's code (`0043a000`–`00441000`) for the displacement `0x2d0`. The turn does not reset it, so the next slot's spot comes on at the theta the last one had | `0043a4e0`, `0043a950`, `0043ea30`, `0043f280` | binary |
| The per-tick steps: KO's frame-scaled code elsewhere scales a per-frame step by `30 / s_fFrmPerSec` (the select's own fade-out, `m_fFadeOut += (30.0f / CN3Base::s_fFrmPerSec) * 1.5f`), so 30 ticks a second is the rate the steps are written for; the realm cooks the spot's 0.02 a tick as 0.6 a second | `GameProcCharacterSelect.cpp` `FadeOutProcess` | source |

RQ-076 read the start (binary, the same image) and aligned the blend into
`selected`, the rest-only start and the rect tests (`content/front-end.md`,
"Moradon"):

| Observation | Where | Label |
|---|---|---|
| Select sets clip 1 once with its own 0.6 s (`push 0x3f19999a` at `0043ea77`), not `FLT_MIN`, so the record's 0.3 s does not apply; the package cooks the start clip's blend as 0.6 (`start_blend`). During the blend the frame stays on `selected`'s start; the loop count `0043ed20` waits for (`+0x1d0`) grows only when the frame passes the clip's end (`00445bb0`), so loading follows the blend and the whole clip | `0043ea30`, `00445bb0`, `0043ed20` | binary |
| The setter keeps the frame the old clip was on (`+0x1c8`, read before it clears the frame control) as the previous frame `+0x1d4` when the blend is above 0; it keeps no previous clip or blend weight. The joints blend those two frames by `+0x1d8 / +0x1dc` (`00445e90`, the call to `0041fb30`). A blend begun during another takes the interrupted clip's held start frame, so KO's pose jumps there and blends on; the realm does the same | `00447e30`, `00445e90` | binary |
| The hover tests the pointer strictly inside the scaled reals (`0043f280`: `w·0.36 < x < w·0.64`, `h·0.44 < y < h·0.86`). The click builds a `RECT` of the same products truncated by `__ftol` (`0043b6f7`–`0043b747`) and asks `PtInRect`, which counts the left and top edges | `0043f280`, `0043b550` | binary |
| The click is taken only outside state 1 (`0043b6c4`, `+0x2cc`) and with UI operation on (`+0xac`); it calls the inlined `CharacterSelectOrCreate` (`0043f860` elsewhere): create for an empty slot, else the select request. The server's answer (`0043db30`) runs Select `0043ea30` on success, which starts the clip only in state 2, or `0043eb60` on failure (clears `+0x2d9`, shows string 6066). Either path through Select leaves UI operation off and the received flag `+0x2d9` on | `0043b550`, `0043f860`, `0043db30`, `0043ea30` | binary |
| ENTER: the select UI's key handler (`00440690`, while UI operation is on) calls `0043f860` for `DIK_RETURN` with no state check, so during the turn it goes to create or sends the select, whose answer then starts no clip. The tick's own check at its tail (`0043b550`: no UI key taken, `005471a0`, and the input's `+0x2dc`, the later source's `IsKeyPress(DIK_RETURN)` before `ProcessOnReturn`) calls `0043db70`, which, once the answer has come (`+0x2d9`) and outside the turn, goes straight to the main proc with "Loading data...": a second ENTER skips the clip | `00440690`, `0043db70` | binary |

The realm starts the clip on the press and its server answers by entering the world,
so it takes ENTER and the click at rest only and ignores them while the clip plays;
1097's start on the answer, ENTER during the turn and the skipping ENTER are not
taken (**Q72**).

### 8.2 The select camera's turn (RQ-067, 2026-11-01)

The maintainer's playtest found the arrows swinging the camera most of the way
round the hall. The cause was the realm's, not KO's: the client turned towards each
slot's absolute heading, `atan2` of its eye about `at`. In engine space (KO's z
reflected) the eyes sit on the −z side of `at`, so the centre's heading was π and
the right slot's −2.41. A turn between them went 5.55 rad the long way, about
318°, at 1.5 rad/s; the left slot's (2.42) went the short way. The realm now turns the
signed angle from the camera's own eye (`client/render/select_turn.h`), which
never wraps, and matches 1097's turn. That was read in the 1097 image of §8.1
(binary, Ghidra `-readOnly -noanalysis`, the same project; output under
`build/ghidra/rq067/`, not committed). The later source's
`GameProcCharacterSelect.cpp` (`CheckJobState`, `CheckRotate*`, `Rotate*`,
`DoJobLeft`, `DojobRight`) agrees line for line. `KARUS_THETA_MAX` and
`KARUS_INCRESE_OFFSET` are the spot's (§8.1), not the turn's.

| Observation | Where | Label |
|---|---|---|
| The select UI's key handler passes `DIK_LEFT` (`0xcb`) and `DIK_RIGHT` (`0xcd`) on as clicks from its children `+0xa8` and `+0xac` (vtable `+0x44`, message 1). Its message handler sends a click from `+0xa8` to `0043e310` (DoJobLeft) and one from `+0xac` to `0043e380` (DojobRight), both on the select proc `006e0494` (`cmp eax, [ecx+0xa8]` at `0043ff69`, the calls at `0043ff77` and `0043ff8f`). Away from their own edge each returns at once in state 1 (turning) and otherwise sets state 1. From the centre (`+0x2c4` 1) the destination `+0x2c8` becomes left (2) or right (3), and the selected index `006e04d0` becomes 1 or 2. From the other side it becomes the centre, index 0. At their own edge they change nothing. Then they play the sound object at `+0x18` when there is one (`004327d0`) | `00440690`, `0043ff77`, `0043e310`, `0043e380` | binary |
| In state 1, `0043e4e0` checks first and then turns. Centre to left: `0043dc50`, else RotationY(`s_fSecPerFrm` × 1.2) on the eye's offset from `at` (`0043f8d0` with `005a1594` × `0058cd90` 1.2). Centre to right: `0043dfb0`, else RotationY(`s_fSecPerFrm` × −1.2) (`0058cd94`). Left to centre: while the eye's x (`+0x158`) is above 0 (`0058c62c`), turn by −1.2 × `s_fSecPerFrm`; otherwise the eye is put back on its backup (`+0x164`–`+0x16c`), state 2. Right to centre: while x is below 0, `0043e880` turns by +1.2 × `s_fSecPerFrm`; otherwise the same. The arrival sets `+0x2c4` to the destination. That tick runs no state-2 proc | `0043e4e0`, `0043e880`, `0043f8d0` | binary |
| `0043dc50` and `0043dfb0` turn a copy of the eye a further step about `at` (the doubles at `0058cd78`, 0.01, and `0058cd88`, −0.01). They normalise it and the backup eye, both from `at`, and dot them (`004282f0`). The turn has ended (state 2, returns 1) when the dot is below the nation's bound: left `0058cd70` 0.75 (nation 1) or `0058cd74` 0.74, right `0058cd80` 0.77 or `0058cd84` 0.73. So with Karus's eye (0, −0.2, 7.4) and `at` (0, −0.4, 0), left ends on the first tick past 0.7130 rad and right past 0.6822 rad. The eye stays where the last step left it | `0043dc50`, `0043dfb0` | binary |
| `s_fSecPerFrm` is the last frame's time, set to 1/30 when it is at most 0.001 s or at least 1 s | `N3Base/N3Eng.cpp` `CN3Eng::Present` | source |
| **1298 differs.** It turns through recorded camera paths, `ChrSelect\Data\ka_center_left_camera.n3camera`, `ka_center_right`, `ka_left_center`, `ka_right_center`, `ka_left_right`, `ka_right_left` and `ka_lording_camera` (and `el_*`), loaded by `005fa670`. Its turning states (`005fe5b0` cases 1, 2, 6) wait until the object at `+0x1a4` has reached its last frame (`+0x110` equals `+0x10c`). Read in §8.4 (RQ-087) | `005fa670`, `005fe5b0`; strings `006d8420`–`006d85cc` | binary |

The realm follows 1097 (Q71). The Moradon package cooks each side slot's eye
where 1097's check first ends the turn (`turn_end` 0.75 and 0.77 in
`games/moradon/front-end.json`). The client (`select_turn_tick`) turns
1.2 rad a second by the frame's time (at most 0.25 s), checks before each step,
puts the eye back on the camera's own when it reaches the centre, and ignores
the arrows while it turns.

The arrows from state 3: away from their own edge, DoJobLeft and DojobRight
return early only in state 1. In state 3, while the start clip plays
(`0043ed20`), they set state 1 and start a turn (binary, `0043e310`,
`0043e380`). The realm ignores the arrows from the press of ENTER or the click
until loading, as it ignores a second start (Q72, decided: the start on the
press, at rest only). *RQ-120 (§9.10): no input reaches them then: 1097's
CharacterSelect (`0043ea30`) clears the UI flag that its select's key and message
handlers test, so its arrows start no turn during the start clip either.*

RQ-077 read the turn's sound and the front-end buttons' sounds (binary, the same
image and project, output under `build/ghidra/rq077/`, not committed; the
disassembly of code Ghidra left undefined with `objdump`):

| Observation | Where | Label |
|---|---|---|
| **1097 has the rotate sound.** The select Init releases the proc's sound object `+0x18` (`0042e9c0`) and creates it again as sound 2501, `0042e430(0x9c5, 1)` (`push 0x9c5` at `0043a9ea`, the store at `0043a9f9`), on the sound manager `005adce0` (`mov ecx, 0x5adce0`). That is the later source's `m_pSnd_Rotate = s_SndMgr.CreateObj(ID_SOUND_CHR_SELECT_ROTATE)` (`GameDef.h`: 2501) | `0043a950` | binary |
| `0042e430` creates nothing unless the manager's `+0x28` and `+0x29` are set. It looks the id up in the table that `0042e180` reads from `Data\sound.tbl` (string `005a1aa8`) and creates the object from the row's file (`0042e4c0`, which tests the same two flags). `+0x28` is the device's (`0042e180` stores `00431b70`'s result at `0042e1c0`). `+0x29` is set to 1 by the constructor (`0042dea9`); no other write to it was found (a byte scan for stores to `+0x29` and to `005add09`). The second argument, 1, is the source's `SNDTYPE_3D` (`N3SndDef.h`, source) | `0042e430`, `0042e180`, `0042e4c0`, `0042dea9` | binary |
| 1097's Option.ini switch is `[Sound] Enable` (default 1), stored at `005ade68` by the reader at `0054ec5e`–`0054ec84`. Only when it is set does `00544600` call `0042e180` (the test at `00544a50`, the call at `00544a5f`), which opens the device. `[Sound] Duplicate` (`005ade69`) goes to `005add0a`; `[Sound] Distance` defaults to 48, clamped 20–48. 1097 has no `[Sound] Effect` key: `Effect` is a section there, `[Effect] Count`, default 2000, clamped 1000–2000 | `0054eb97`–`0054ecab`, `00544600` | binary |
| 1097's `Data/sound.tbl` (decrypted with `tools/assetc/ko_tbl.py`, 188 rows) has row 2501 `Snd\char_select_turn.wav`, 0, 9, as the pinned tree's has. The two `char_select_turn.wav` files are byte-identical (sha256 `5f693df7…`; 8-bit mono, 22,050 Hz, 13,961 frames, 0.63 s) | `Data/sound.tbl`, `Snd/char_select_turn.wav` | local-asset |
| DoJobLeft and DojobRight play the sound after they set the destination. The play runs when `+0x18` is not null and the camera is not at their own edge (`+0x2c4` not 2, or not 3). The call is `004327d0(none, 0, 0, 1)` at `0043e373` and in `0043e380`; in state 1 they have returned before it. With its last argument 1, `004327d0` stops the buffer `+0x4` if it is playing (`IDirectSoundBuffer::Stop`, vtable `+0x48`). It then plays the buffer once (`Play`, vtable `+0x30`, flags 0: the looping flag `+0xc` is clear), when the object has a 3D buffer `+0x8`. No position is passed, so `SetPosition` (the 3D buffer's `+0x4c`) is not called. So each turn the arrows start plays the sound once, and an arrow at the end of the row plays nothing. Whether a play that stops one still sounding starts again at the first sample was not read: `004327d0` does not call `SetCurrentPosition` | `0043e310`, `0043e380`, `004327d0` | binary |
| `0042e430`'s other callers are not the select's. They pass ids from tables (`0044d0c0`, `0044d480`, `00452b60`) or the constants 100, 200, 201, 1000, 2000–2003 and 3000 (`0044d0c0`, `004e8c10`, `004fab60`, `00493a80`). `0042e7e0` (the other user of the table lookup `0042fd00`, first taken here for a play-once creator; §9 finds it creating the login's BGM stream) is called with 20003, 606 and a caller's id, from `00525b70`, `0052ccf0` and `0052a870`. Neither group was read further | the callers of `0042e430`, `0042e7e0` | binary |
| The front-end buttons play nothing. 1097's button loader reads two sound names and creates each (`0042e4c0`, into `+0xc8` and `+0xdc`) only when its length is above 0 (`00403b65`, `00403c8d`) | `00403ac0` | binary |
| 1097's `Data/UIs.tbl` (decrypted, two rows by nation) names the Karus screens `UI\co_login.uif`, `UI\Ka_CharacterSelect.uif`, `UI\Ka_CharacterCreate.uif`, `UI\Ka_MessageBox.uif`, `UI\Co_Loading.uif` and `ui\\ka_loading.uif`. In those files, in their `_tw` copies and in `Co_nationselect.uif`, every length-prefixed string that names a file is a `.dxt`; none names a sound. El Morad's `el_characterselect.uif` does name sounds: `snd\ui_button.wav` on `bt_delete` and `bt_exit`, `snd\ui_button4.wav` on `bt_left9` and `bt_right`. Which of a button's two names (hover, click) each fills was not read: 1097's UIF layout is older than the one `ko_hud.parse` reads | the 1097 install's `UI/`, `Data/UIs.tbl` | local-asset |

**Decides (RQ-077, Q70):** the select arrows play 1097's turn sound. The Moradon package
binds sound 2501 (`front-end.json` `select.turn_sound`) to `front:select-turn` in
`audio.bin`. The client plays it once for each turn an arrow starts, as one voice:
a new turn stops the last play and starts again at the first sample. It plays nothing at the end of the row, nothing while the
camera turns and nothing while the start clip plays. It is unpositioned, at the
voices' gain. KO creates it as a 3D sound and passes no position; the gain and pan
that gives were not read. The realm draws the Karus hall, and 1097's Karus
front-end layouts name no button sounds, so the screens gain none. The realm keeps
reading 1298's `[Sound] Effect`, not 1097's `[Sound] Enable` (Q70).

### 8.3 1298's select hall at rest (RQ-086, 2026-11-02)

Ghidra 12.1.3 headless (`-readOnly -noanalysis`), `ko-audit`, `KnightOnLine.exe`
(1298, sha256 `828ab0db…43a5e5`), output under `build/ghidra/rq086/` (not
committed), with §8's decompiles of `005fef90`, `005fe5b0`, `005fe7c0`, `005fea70`,
`005fb4f0` and `005faf10` (`build/ghidra/rq066/`). `0041be40` and `00418700` are
§8's clip setter and frame tick; `00418700` is passed `FLT_MIN` (`006a93b0`), the
character's own frame time.

| Observation | Where | Label |
|---|---|---|
| AddChr sets each body part through `005fc6f0(chr, looks row, part, item, durability, record)` for parts 0, 1, 3 and 4 (the record's items at `+0x28`, `+0x30`, `+0x48`, `+0x50`). With no item (id 0) its item row is null; when the name `006157b0` builds from that row is empty (`006157b0` not read: taken as empty for a null row), the part is the race's looks row's own (`row + 0x34 + part × 0x10`, the table `00818758` keyed by race `+0x10`): `UPC_DefaultLooks`. The face (part 2) is the row's face file with the character's face number (`+0x1c`) inserted, `"%s%s%.2d%s"` (`006d4280`); the hair (part 5) is an item's (`+0x38`) or the row's hair file with the hair number (`+0x20`) | `005fb4f0`, `005fc6f0` | binary |
| The hands' plugs go through `005fca40(chr, row, hand, item, …)` (items `+0x58`, `+0x60`), which returns before creating anything when the item's row is not found: a slot with no item holds no plug | `005fb4f0`, `005fca40` | binary |
| AddChr ends by setting clip 1 **looping** with no blend on all three characters and ticking each (`0041be40(1, 0, 0, 0, 1)`, `00418700`), after placing them at 1298's own positions, not the 1097 hall's: Karus slot 0 at (128, 0, 91) turned π about y, slot 1 at (108.7, 0.2, 62.9) turned 1.92, slot 2 at (141.3, 0.3, 68.5) turned 4.28 (each character's vtable `+0x24` with three reals, taken as its position, and a rotation built by `0064d306`; neither read further) | `005fb4f0` (its last loop and the calls before it) | binary |
| At rest (state 5), every tick, `005fef90` sets clip 1 looping on the character in front and clip 0 once on the others, each with `FLT_MIN` (its record's blend), and **ticks every character**. It then calls the select UI's info setter `006074c0` (`this` the UI at `+0x384`, `005fefd6`) with the front slot's record (`+0x38 + slot × 0x68`): for a record whose name is empty (`+0x8` 0) it sets the UI's three texts (`+0xcc`, `+0xd0`, `+0xd4`) to the empty string (`006dfe28`, a zero byte), otherwise to the name, the class (`00613ea0`) and the level (`"%d"`, `006d3a54`). The pointer plays no part | `005fef90`, `006074c0` | binary |
| The spot: in state 5 the theta `+0x398` grows by 0.02 a tick (`006a93bc` Karus, `006a93c0` El Morad) up to 0.5 (`006a93b4`, `006a93b8`) and never shrinks there; the three slot lights' theta (`+0x258`, Theta of the D3DLIGHT9 at `+0x1f8`) are set to 0 and the front's to `+0x398`; light slot + 4 is enabled and set when the theta is not 0 (`006a37dc`, 0.0) and disabled otherwise. The start (`005fe7c0`) sets the theta to 0.5; the turns (`005fe3c0`, `005fe450`) do not write it | `005fef90`, `005fe7c0`, `005fe3c0`, `005fe450` | binary |
| Every select tick turns lights 0–7 off (`LightEnable(i, 0)`, vtable `+0xb8`), applies the two hall lights at `+0x1a8` and `+0x1ac`, then runs the state switch `005fe5b0`: the spot is lit only in states 5 and 4 (`005fea70` lights it). While the camera turns (states 1, 2, 6) every character gets clip 0 once and is ticked | `005faf10`, `005fe5b0` | binary |
| A turn hides the select UI: DoJobLeft and DojobRight (`005fe3c0`, `005fe450`) set state 2, call `+0x384`'s vtable `+0x3c` with 0 and start a camera path (`005fa670`); the arrival (`005fe5b0` cases 1 and 2) calls it with 1 and sets state 5. The click on an empty slot (`005faf10`) calls it with 0 and `+0x388`'s with 1 (create) | `005fe3c0`, `005fe450`, `005fe5b0`, `005faf10` | binary |
| During the start (state 4) `005fea70` sets and ticks only the chosen character | `005fea70` | binary |
| `ChrSelect/upc_ka_tu.n3joint` has 24 joints with 228 keys at 15 a second, so its keys cover frames below 458; `upc_ka_tu.n3anim`'s clip 2 runs to 466. 1298's sampler (`00427640`, PQ-266) takes the key index up to the count and past it leaves the joint unchanged: the last 8 frames hold the pose the last key set | the pinned tree; `00427640` | local-asset; binary |

**Decides (RQ-086):** N3FE version 6 carries the hall's front-clip mode, and
`games/moradon/front-end-1298.json` (not offered, `content/front-end.md`, "1298")
cooks 1298's select character with it: `upc_ka_tu` with the default looks and no
plug, clips 1, 2 and 0 as the front, start and rest clips, the loop mode (the
front clip looping, the others' rest clip once, every character ticked, the spot
widening and staying, the info text at rest, empty for an empty slot), no turn
sound. The realm hides only the info text while the camera turns, not the whole
select UI as 1298 does, and keeps 1097's hall, slots and turn: those come with
1298's camera paths (proposed as their own item). *RQ-087 (§8.4):* the camera
paths, the UI hidden while they play, and 1298's slots and spots are data now;
1298's hall, the `karus_intro` zone, is not.

### 8.4 1298's select camera paths (RQ-087, 2026-11-02)

Ghidra 12.1.3 headless (`-readOnly -noanalysis`), `ko-audit`, `KnightOnLine.exe`
(1298, sha256 `828ab0db…43a5e5`), output under `build/ghidra/rq087/` (not
committed), with §8's and §8.3's decompiles (`005fe5b0`, `005fb4f0`, `005faf10`,
`005fe3c0`, `005fe450`). The 14 `ChrSelect/Data/*.n3camera` of the pinned tree
were read with a throwaway parser against that layout (each parses to its last
byte), then with `tools/assetc/ko_front_end.py` `camera_path`.

| Observation | Where | Label |
|---|---|---|
| **The `.n3camera` format** is CN3Camera::Load (`00439540`, camera vtable `006a3cdc` slot 3): the transform load `0043b480` (the base name; the eye, `+0x48`, 12 bytes; a rotation `+0x2c`, 16; the up vector, the transform's scale `+0x3c`, 12; three key sets read by `00411950`, each a count and, when above 0, a type, a rate and the keys), then the at `+0x118` (12 bytes), `__CameraData` `+0x124` (`0x16c` bytes), the fog's use `+0x290` and colour `+0x294` (4 each). The load sets the frame `+0x110` to 0 and the last frame `+0x10c` to the largest count × rate × 1/30 (`006a3c44`, 0.033333335) of the three sets | `00439540`, `0043b480` | binary |
| The pinned tree's 14 paths (Karus `ka_`, El Morad `el_`): `center_left`, `center_right`, `left_center`, `right_center` 120 keys, `left_right`, `right_left` 90, `lording` 180, each in both the first set and the second, type 0 (vectors), 30 a second, so 4, 3 and 6 seconds; no third set; identity rotation, up (0, 1, 0); the file's camera data a field of view of 0.96, near 0.7, far 512; fog on. The first set is the eye's path, the second the at's: `ka_center_left` takes the eye from (128.03, 0.53, 85.93) to (113.55, 1.11, 61.00) and the at from (128.07, 4.09, 105.85) to (103.11, 2.44, 65.04); `ka_lording` the eye from (186.16, 41.10, 6.79) down to (128.01, 0.53, 85.92) | `ChrSelect/Data/*.n3camera` | local-asset |
| The transform tick `0043b5a0`, given `FLT_MIN` (its callers here push `006a93b0`, `005faa5c`; the tick tests its argument against its own copy, `006a3d70`; both hold `0x00800000`), adds 30 / `s_fFrmPerSec` (`006a3c48` 30.0 over `006d3aac`) to the frame, at least 0; at or past the last frame it holds the frame there when `+0x114` is 1, else it puts it back to 0. Then `0043b710` sets the eye from the first set when it is vectors (`+0xac` 0), the rotation from the second only when it is quaternions (`+0xd4` 1) and the up from the third: key i = the truncated frame × rate / 30 (`__ftol`; its operand is not in the decompile, the source's `CN3AnimKey::DataGet` form), the last key at the count, nothing past it, below it key i blended toward key i + 1 by the frame's fraction of a key (`1 − t`, `006a3a64`). The camera's tick `004396c0` (vtable slot 7) runs that, then sets the at `+0x118` from the second set the same way when it is vectors (`+0xd4` 0), then builds the view from eye, at and up and the projection from `+0x148`, `+0x150` and `+0x154` | `0043b5a0`, `0043b710`, `004396c0` | binary |
| `005fa670(n)` picks the path by `n` and the nation (`+0x490`): 1 `lording`, 2 `center_left`, 3 `center_right`, 4 `left_center`, 5 `right_center`, 6 `left_right`, 7 `right_left`, `ChrSelect\Data\ka_*` for Karus and `el_*` for El Morad. It loads it into the proc's camera `+0x1a4` (vtable `+0xc`), sets `+0x114` to 1, ticks it once (vtable `+0x1c` with `FLT_MIN`, `006a93b0`) and applies it (`004395c0`) | `005fa670` | binary |
| Its callers: Init `005f98c0` (state `+0x394` 1, slot `+0x38c` 0, the select UI hidden: `+0x384`'s vtable `+0x3c` with 0, then `005fa670(1)`); DoJobLeft `005fe3c0` (from the centre path 2 to slot 1, from slot 2 path 5 to the centre) and DojobRight `005fe450` (from the centre 3 to slot 2, from slot 1 4 to the centre), both nothing in states 1 and 2 or at their own edge; and `005ff920` (create with a character in front: the camera to the first empty slot by 2–7, state 6, the create UI shown). Paths 6 and 7 are only that move | `005f98c0`, `005fe3c0`, `005fe450`, `005ff920` | binary |
| The arrival: `005fe5b0` cases 1 (the entry) and 2 (a turn) give every character clip 0 once and tick it, then, when `+0x110` equals `+0x10c`, set state 5, show the UI (`+0x3c` with 1) and set the slot to the destination (case 1: 0). Every tick `005faf10` runs the state switch first and ticks the camera last (vtable `+0x1c` with `FLT_MIN`), so the path's last frame shows a tick before the arrival | `005fe5b0`, `005faf10` | binary |
| **ENTER and ESC skip a path.** ENTER (the input's `+0x2dc`, `005fe280`) in state 1 or 2 puts the frame on the last (`+0x110` = `+0x10c`), the slot on the destination, state 5, and shows the UI when it is hidden (its `+0xa0` byte 0); outside them it starts the load (with `+0x3a1` set). The tick does the same for the input's `+0x270` in every state but 6 and 7. In the later source's `CLocalInput` (`LocalInput.h`) `m_bKeyPresses`, 256 `BOOL`s, is at `+0x26c` (after the three drag `RECT`s and the two 256-byte key arrays), where `+0x2dc` is `DIK_RETURN`, as §8.1 reads it, and `+0x270` `DIK_ESCAPE`; 1298's class layout was not read | `005fe280`, `005faf10`; `LocalInput.h` | binary; source |
| Render `005fb1c0` sets the camera's eye and at to the proc's `+0x1c8` and `+0x1e0` every frame (Karus (128.011, 0.534, 85.922) and (128.077, 4.087, 105.862), `005f98c0`), up (0, 1, 0), near 0.1, far 500 (`0x43fa0000`) and field of view 0.96 (`0x3f75c28f`), then applies what the tick built (`004395c0`: the view and projection `+0x170`, `+0x1f0`). So the eye and at shown are the path's (the next tick's key sets overwrite Render's), and the field of view, near and far Render's from the second frame. Apply also sets the file's fog (`+0x290`, `+0x294`, linear range fog); not read further | `005fb1c0`, `004395c0` | binary |
| **1298's select hall is a zone.** Init calls `00600950` (0 Karus, 1 El Morad), which sets the zone `+0x89c` to 1000 and `+0x8a0` to 1 (Karus) or 0, takes the zone `0046c9d0` = `+0x89c` × 10 + `+0x8a0` (10001) and loads its data (birds, sky, …; "can't find zone data"). `Data/Zones.tbl` 10001 is `karus_intro` (`Zones/karus_intro.gtd`, `.opd`, `Misc/Sky/Karus.N3Sky`), 10000 `elmorad_intro`. Render draws the world manager's (`0081878c`, `+0x1c`, vtable `+0x9c` to `+0xb4`, not read one by one) before the characters. This answers §9's open question (RQ-012): 1298 draws neither `ka_chairs` nor `ka_cave` | `005f98c0`, `00600950`, `0046c9d0`, `005fb1c0`; `Data/Zones.tbl.csv` | binary; local-asset |
| The slots (`005fb4f0`, Karus): (128, 0, 91), (108.7, 0.2, 62.9), (141.3, 0.3, 68.5), each turned about (0, 1, 0) (`0064d306`'s axis argument) by π (`0x40490fdb`), 1.9198623 (`0x3ff5be0c`) and 4.2760568 (`0x4088d575`): 180°, 110° and 245°, each facing the camera at rest there | `005fb4f0` | binary |
| The spots (`005f98c0`, Karus): three D3DLIGHT9 at `+0x1f8` (`0x68` each), spot, diffuse 1, range 6, falloff 20, attenuation 0.1, 0, 0, phi 1.5 (`0x3fc00000`); slot 0's at (128, 2, 85.5), slot 1's (112.7, 1.7, 58.9), slot 2's (137.3, 1.8, 64.5), each pointing at its character (the direction is the character's position less the light's: `006a93f4`–`006a9404`, `006a3bec` 2, `006a7a44` 5.5, `006a4108` 4, `006a4034` 1.5) | `005f98c0` | binary |
| *RQ-095 (2026-11-02; Ghidra as above, output under `build/ghidra/rq095/`, not committed):* **what Render draws, in order.** The world (`0081878c` `+0x1c`) is a CN3TerrainManager: InitWorld (`005c0de0`) creates one (`005a2f30`, vtable `006a8330`; terrain `+0x44`, shapes `+0x48`, sky `+0x4c`, birds `+0x50`, named by the later source's member order, `N3TerrainManager.h`, the constructor allocating `0x4c34`, `0x40084`, `0x124` and `0x20` bytes for them) for any zone but 2000. Render clears to its `+0x70` (`005a3a90`: the sky's `+0x2c` `+0x30`, a colour, to `0043ad40`), applies the camera, then calls `+0xa4` (`005a3760`: the sky's `005ae7a0`), `+0x9c` (`005a3720`: the terrain's render `0059cd90`), `+0xa0` (`005a3740`: the shape manager `005b5870`, each shape's vtable `+0x48`, then `+0x54`'s `005bda00`), `+0xb4` (`005a3730`: the terrain's `0059d300`, which calls `+0x4c18`'s `005c01a0` and `+0x4c1c`'s `005befe0`), `+0xa8` (`0047dee0`, a bare return), `0047be30`, `+0xac` (`005a3770`: the birds' `005ba580`) and `+0xb0` (`005a3780`: the sky's `005aea40`); then the three characters (`004196a0`), the select UI between `00578db0` and `00578f50` (z test and fog off, blend 5/6, restored after: CUIManager's RenderStateSet/Restore), the other windows (`005286e0`, each between the same pair), and then `0043dd80`, the alpha flush (PQ-379). So a zone's alpha parts draw after the UI. `005ae7a0`, `005aea40`, `0059d300`'s callees, `005bda00`, `005ba580` and `0047be30` were not read further | `005fb1c0`, `005c0de0`, `005a2f30`, `006a8330` (its words at `+0x70`–`+0xb4`), `005a3720`–`005a3780`, `005a3a90`, `005b5870`, `0059d300`, `00578db0`, `00578f50`, `005286e0`; `N3TerrainManager.h` | binary; source |
| The terrain's render (`0059cd90`) sets the world transform to the identity and the material to Diffuse (1, 1, 1, 1), Ambient (0.5, 0.5, 0.5, 1), the rest 0 (`SetMaterial`, device vtable `+0xa8`), the fill and shade modes from `+0x8c` and `+0x88`, culling CCW and the z test on; it does not touch lighting, so the select's lights (the next row) light it. Every one of `karus_intro.opd`'s 313 shape parts carries the same material (Diffuse 1, Ambient 0.5) | `0059cd90`; `Zones/karus_intro.opd` | binary; local-asset |
| **The select's lights are the light manager's.** Init (`005f98c0`) resets the proc's `+0x2c`, a light manager (vtable `006a872c`; source `CLightMgr`, `LightMgr.cpp`): its first virtual, Release (`005ba7a0`), makes light 0 directional (type 3) down (0, −1, 0), diffuse 0.8 (`0x3f4ccccd`), ambient 0.56 (`0x3f0f5c29`); light 1 directional up (0, 1, 0), diffuse 0.5, ambient 0.35 (`0x3eb33333`); light 2 a point light (type 1) at its transform's position (0, 0, 0), diffuse 0.3 (`0x3e99999a`), ambient 0.21 (`0x3e570a3e`), range 128 (`0x43000000`), falloff 1, attenuation 0.5, 1/64 (`0x3c800000`), 1/2048 (`0x3a000000`), each on with its number (`+0x184`) 0, 1, 2; then `0063cce0` takes the three (as `GameProcMain::Init`'s `SetDefaultLight`). `00600950` does the same before it loads the zone, and passes the zone row's column 12 (`+0xa0`, between the N3Sky name and two ints and the GEV at `+0xb0`) to `005bacd0` (source `LoadZoneLight`; `karus_intro.glo` is not in the 1298 tree, local-asset). Every select tick (`005faf10`) turns lights 0–7 off, ticks and applies the hall lights (`ka_light_0/1`: point lights numbered 0 and 1 at (±6, 1, 0), range 7), then, with `+0x2c` set (`005fb0ea`: ECX = `[ESI + 0x2c]`), the manager's tick (`005baae0`), which ticks and applies each of its lights (`CN3Light::Tick` puts the transform's position in the light, source `N3Light.cpp`), so lights 0 and 1 end the tick as the manager's. Without them the zone and the characters (at (128, 0, 91), 150 m from the hall lights) would have only the front slot's spot | `005f98c0`, `005ba7a0`, `00600950`, `005faf10`, `005baae0`; `CLightMgr::Release`, `CN3Light::Tick` | binary; source; local-asset |
| **The fog.** Apply (`004395c0`) sets FOGENABLE (`0x1c`) to `+0x290`, FOGCOLOR (`0x22`) to `+0x294`, FOGTABLEMODE (`0x23`) 0, FOGVERTEXMODE (`0x8c`) 3 (linear), RANGEFOGENABLE (`0x30`) 1, FOGSTART (`0x24`) to `+0x154` × 0.1 (`006a3d1c`) and FOGEND (`0x25`) to `+0x154` itself (`0043966f`–`004396ad`): linear range fog from a tenth of the far to the far, 50 to 500 m under Render's far. The later source's Apply sets EXP2 with a density of 1 / (0.37 far) instead; 1298's is linear. Each of the 14 `ChrSelect/Data/*.n3camera` carries fog on and the colour `0xffffffff` (white); no function read here writes the camera's `+0x290` or `+0x294` but its Load (`00439540`) | `004395c0`; `N3Camera.cpp` `Apply`; `ChrSelect/Data/*.n3camera` | binary; source; local-asset |
| `karus_intro` (65 samples, 256 m): 4,096 tiles, one tile layer each (no tex2 below the 11 tile textures), 20 drawn from the colour map; 100 shapes, of which 89 static and 11 the world bake leaves out (10 `animated_material`, 1 `animated`); 282 placed parts, 19 of them alpha parts (`RF_ALPHABLENDING`, source 5, destination 6) and 17 `RF_NOTUSELIGHT` | `Zones/karus_intro.gtd`, `.opd` (`ko_terrain`, `ko_shapes`, `ko_scene.expand`) | local-asset |

**Decides (RQ-095, Q79):** N3FE version 8 carries a zone as the select hall and
the select camera's fog: `games/moradon/front-end-1298.json`'s `select.zone` 10001
cooks `karus_intro`'s terrain and static shapes, lit by the light manager's lights
(`select.light_manager`, which replace the hall lights of their number) with
the terrain's material, its alpha parts drawn after the UI far to near, under the
camera files' fog (white, 50 to 500 m). Not data yet: the zone's sky, its light
maps, grass and birds, and its animated shapes (Q79: the background stays black
meanwhile).

**Decides (RQ-087, Q77, Q78):** N3FE version 7 carries the select camera's turn
mode, `rotate` (1097's, `games/moradon/front-end.json`, unchanged) or `path`, and the
path mode's paths; the hall may have no parts. `games/moradon/front-end-1298.json`
turns through the four Karus turn paths and flies in on `ka_lording_camera` as the
hall opens, plays each at 30 frames a second to its last frame, arrives a tick
later, hides the whole select UI meanwhile and skips to the end on ENTER or ESC;
its slots, yaws, spots (phi 1.5) and camera are 1298's. Not data yet: the
`karus_intro` zone 1298 draws as the hall (the recipe has none), and its fog.
The realm flies in only from the realm list, not on a return from create (1298's
create is a state of the select, `005ff920`) or after a created character; ESC at
rest stays the realm's back, and ESC while the start clip plays does nothing
(1298 puts it back to rest); a path the arrows start takes its load's step with
the frame's own time (Q78). *RQ-117 (§9.9): 1298's ESC at rest does nothing (the bar's
OnKeyPress runs the same skip); the 1298 recipe's stays Back.* *RQ-119: the 1298
recipe's ESC now does nothing but skip a path (N3FE version 16, `select.escape`
`none`, §9.9).*

### 8.5 Each select character by race and class, and its class name (RQ-005, 2026-11-05)

Read in the 1097 image (`ko1097-unpacked.exe`, RQ-074's Ghidra project; output under
`build/ghidra/rq005/`, not committed) and the 1298 binary (RQ-109's decompile of
`00613ea0`), with the later source's `AddChr` and `GetTextByClass`.

| Observation | Where | Label |
|---|---|---|
| AddChr picks the joint, animation and plugs by race, and for the Tuarek, the El Morad man and woman by class too (§8.1's 1097 row; §8.3's 1298 per-race files). The source's switch returns without a character for a race or class it does not name (`default: return;`). The parts are the race's `UPC_DefaultLooks` row's, an item's where the slot holds one, the face and hair the row's file with the character's number | `GameProcCharacterSelect.cpp` `AddChr`; 1097 `0043ba10`; 1298 `005fb4f0` | source; binary |
| **1097's face and hair (RQ-198).** After the body parts (0, 1, 3 and 4 through `0043d0f0` with the record's items `+0x28`–`+0x54`), when the race's looks row names a face (its string's length at row `+0x5c` not 0), AddChr splits that name (`00575121`, `_splitpath`) and formats `"%s%s%.2d%s"` (`005a1fa4`; `00574aef`) of its directory, name, the record's face number (`+0x1c`) and extension, and sets it as part 2 (`00447a70(2, …)`). Part 5 is the helmet item's (`+0x38`, through `0043d0f0`) when the record holds one; otherwise an empty part when the row names no hair (length at `+0x8c` 0), else the row's hair name formatted the same way with the record's hair number (`+0x20`). The face and hair are not read from a range: a number past the files the tree holds names a file that is not there (what KO then draws was not read) | 1097 `0043ba10` (decompiled in RQ-074's project; output under `build/ghidra/rq198/`, not committed) | binary |
| **1097's class text.** The info text (`004402a0`, string 1201 "Level : %d \nSpecialty : %s \nID : %s") takes the class from `0052e3e0(record + 0x14, out)`: a switch on the class code that loads a string resource (`LoadStringA`): 101 and 201 → 0x58c (1420), 102 and 202 → 0x58a (1418), 103 and 203 → 0x58d (1421), 104 and 204 → 0x589 (1417), 105 → 0x581, 106 → 0x583, 107 → 0x584, 108 → 0x586 (and through `004840d0`) 109 → 0x588, 110 → 0x585, 111 → 0x587, 112 → 0x582, 205 → 0x57a, 206 → 0x57f, 207 → 0x580, 208 → 0x579, 209 → 0x57e, 210 → 0x57d, 211 → 0x57b, 212 → 0x57c; 1–12 → 0x518–0x523 (1304–1315, KO's class kinds); any other the literal "Unknown Class" (`005a4cfc`) | 1097 `004402a0`, `0052e3e0` | binary |
| **1298's is the same map.** `00613ea0` (from the bar's `006074c0`) maps the same codes to the same row numbers through the text table (`00616a90` for 1–12, `00615080` for the others), and any other to "Unknown Class" (`006d8e08`) | 1298 `00613ea0` | binary |
| The pinned tree's and the 1264 install's `Texts_us.tbl` hold the same texts at those rows: 1417 "Priest", 1418 "Rogue", 1420 "Warrior", 1421 "Magician", 1401–1416 the sixteen advanced classes (eight per nation) ("Kasar Hood" … "Sorcerer"; 1410 "Shadow Knight" with four trailing spaces), 1419 "Unconfirmed Specialty " (no code names it), 1304–1315 the class kinds | the pinned tree's and `installer-1264`'s `Data/Texts_us.tbl` | local-asset |

**Decides (RQ-005):** `front-end.bin` version 31 carries the select characters per race
and class (item 17) and each specialty's class name from those rows; the client draws
each listed character with its race and class's select character and shows its class
name. The 1097 choice gives the Tuarek rogue (102, 107, 108) 1097's
`upc_ka_tu_rog.n3joint` with the bow and quiver; the priest stays the select model. The
1298 recipe needs none (one file per race). A character the switch would not draw stands
as the select model (Q118). Not yet then: its own face and hair (RQ-198, below) and items
(RQ-197).

**Decides (RQ-198):** `front-end.bin` version 33 carries the select model's and each
select character's face and hair parts by number, as the create models carry theirs
(item 8): the model holds the looks parts but the face and the hair, and its parts
`00` up to `create.bin`'s face and hair counts follow (a created character's numbers
are within them; the server's create refuses any other, `content/character-create.md`).
The hall draws each listed character's own face and hair by its numbers, as 1097's
`0043ba10` and 1298's `005fb4f0` set them, none for a number past the parts (a
character from before the package's rules, or a row without that part, as the
Wrinkle Tuarek's hair). A helmet in the hair's slot is RQ-197's (visible equipment).

### 8.6 Each select character's visible equipment (RQ-197, 2026-11-05)

Read in the 1298 binary (`KnightOnLine.exe`, sha256 `828ab0db…43a5e5`, n3e's
`audit-2026-09-19` project; output under `build/ghidra/rq197/`, not committed) and the
1097 image (`ko1097-unpacked.exe`, sha256 `82abb582…febaf`, RQ-074's project), with
RQ-086's decompiles of `005fc6f0` and `005fca40`, RQ-066's of `005fb4f0` and RQ-198's
of `0043ba10`, and the later source's `MsgRecv_AllCharacterInfo` and `AddChr`.

| Observation | Where | Label |
|---|---|---|
| **1298's list parse.** A result byte; 1 goes on. Three records, at `this+0x38`, `+0xa0` and `+0x108`, each 0x68 bytes, read in order: the name (i16 length, then the bytes), race (u8, `+0x10`), class (i16, `+0x14`), level (u8, `+0x18`), face (u8, `+0x1c`), hair (u8, `+0x20`), zone (u8, `+0x24`), then per item a u32 id and an i16 durability: helmet (`+0x38`/`+0x3c`), upper (`+0x28`/`+0x2c`), cloak (`+0x40`/`+0x44`), right hand (`+0x58`/`+0x5c`), left hand (`+0x60`/`+0x64`), lower (`+0x30`/`+0x34`), gloves (`+0x48`/`+0x4c`), shoes (`+0x50`/`+0x54`). AddChr (`005fb4f0`) is called for slots 0, 1 and 2 when the record's name pointer (`+0x8`) is set. The order is the source's | 1298 `005ff2a0`; `GameProcCharacterSelect.cpp` `MsgRecv_AllCharacterInfo` | binary; source |
| **The parts.** AddChr sets the upper, lower, gloves and shoes as part slots 0, 1, 3 and 4 from the record's items (1097 through `0043d0f0` with `+0x28`, `+0x30`, `+0x48`, `+0x50`; 1298 through `005fc6f0`), the looks row's part for a slot with no item; the helmet (`+0x38`) is set in slot 5 when its item resource has art (1097 `0043f990`'s lookup; 1298 the row's `+0x30` resource), else the hair by number. No function reads the cloak (`+0x40`) | 1097 `0043ba10`, `0043d0f0`; 1298 `005fb4f0`, `005fc6f0` | binary |
| **A robe.** For the lower (part 1) when the upper's `Item_Org` robe byte is set (1298 `+0x41`, 1097 `+0x39`), AddChrPart names no file (`""`); with a name of length 0 it sets the looks row's own part (row `+0x34` + part × 0x10). So a robe draws the looks lower, not a bare one. 1298 exempts the El Morad races 11, 12 and 13 with an upper of kind 266 (upper / 10⁶); 1097 has no exemption (`0043d200`–`0043d277`). The source sets the lower to `""` and no part, unlike both binaries | 1298 `005fc6f0`; 1097 `0043d0f0`; `GameProcCharacterSelect.cpp` `AddChr` | binary; source |
| **1097's plugs.** AddChr sets its class plugs from `ChrSelect` files (`00447b30(0)`, `(1)`) and never reads the hand items (`+0x58`, `+0x60`) | 1097 `0043ba10` | binary |
| **1298's plugs.** AddChr sets no class plug; `005fca40` adds a hand's item as a plug when its `Item_Org` and `Item_Ext` rows exist (else returns), naming the file with `006157b0` and setting it with `0041b790` (`PlugSet`, no height scale): joint 12 for the right hand; for the left, 5 when the item's `Item_Org` class (`+0x40`) is 60 (a shield), else 7. The joint is written into the plug (`+0x34`, at `005fce0b`) only when the `Item_Org` max-durability field (`+0x4e`) is above 0; otherwise the branch at `005fcc73` jumps past it to `005fce0e` and the plug file's own joint stays. It also adds the item's dust overlay and weapon effect (`0045ccc0`, `00415370`) | 1298 `005fca40` | binary |

**Decides (RQ-197):** `front-end.bin` version 35 carries, per select model, the looks
parts a key may take and what each of the package's appearance keys draws (item 7):
a part in its KO part slot (0, 1, 3, 4, or 5 for a helmet in the hair's place), with a
robe flag on an upper that makes the lower draw its looks part, or a hand plug on its
row's joint. The recipe's `select.item_plugs` is `none` for the 1097 choice (its AddChr
draws class plugs and no hand item) and `draw` for the 1298 recipe. The client draws a
listed character's `Character.appearance` keys: the first key per slot, the robe's
looks lower, a helmet in place of the hair, each plug key once. Keys draw on the player
race's select models only (Q122). Not drawn: 1298's dust overlay and weapon effect
(Q120); a plug with durability 0 keeps the row's joint (Q121).

## 9. The front end per client (RQ-078, 2026-11-02)

Which KO client a realm's front end looks and behaves like is the realm owner's
choice (spec 11 "The client choice", `content/front-end.md` "Choosing the
client"). This is what differs on the five screens between the four installs the
realm has, and what the engine can already express as `front-end.bin` data. The
installs: 1097 (`build/ko-reference/installer-1097`, §8.1's unpack of its exe),
1298 (the pinned tree, `assets/ko`), 2145 (`build/ko-reference/installer-2145`,
Inno installer `7da88158…`) and the Steam client (`build/ko-reference/steam-install`,
client build 2026-10-22, protected exe `71ac1b63…`; its analysis dump
`build/ko-reference/steam-rea/analysis/KnightOnLine.unpacked.exe`, `7c038847…`,
whose OEP is unresolved and imports partial). Ghidra 12.1.3 headless
(`-readOnly -noanalysis`) on §8.1's 1097 project, output under
`build/ghidra/rq078/` (not committed); `objdump` for code Ghidra left undefined.
The 2145 exe is packed (no readable strings) and was not unpacked; the Steam dump
was read only for its strings. Nothing here is committed from those trees.
RQ-083's rows (2026-11-02) read the same 1097 project the same way, output under
`build/ghidra/rq083/` (not committed), with `objdump` for the code Ghidra left
undefined, and both trees' `Data/sound.tbl` through `tools/assetc/ko_tbl.py`.
RQ-085's rows (2026-11-02) read the same project the same way, output under
`build/ghidra/rq085/` (not committed), `objdump` for `0040ad10` and `0052d340`–`0052d6a0`,
the 1097 install's `Data/UIs.tbl` through `tools/assetc/ko_tbl.py`, and the six
layouts with a throwaway reader (`ko_hud.parse` with the two differences below; not
committed). Their textures were decoded (`ko_hud.texture`, `ko_front_end.texture`)
and looked at; nothing from them is committed.

| Observation | Where | Label |
|---|---|---|
| The four `Intro/` folders are byte-identical (61 files each: the orc `Intro.N3Chr` with its parts and axe, `0–2.N3Light`, `Moon.dxt`) | `Intro/` in each install (sha256 of every file) | local-asset |
| **1097 draws the 1098 login scene.** The login Init (code from `00523c80`, not a defined function) loads `Intro\Moon.dxt`, `Intro\Intro.N3Chr` (clip 0 looping, `00447e30(0, 0, FLT_MIN, 0, 1)` at `00523e2e`) and `Intro\0–2.N3Light` (`00523cf6`–`0052405b`), the source's `CGameProcLogIn_1098::Init`. Its layout is `UI\co_login.uif` (`Data/UIs.tbl`, both nations) | `00523cf6`–`0052405b`; `Data/UIs.tbl` | binary; local-asset |
| **1298 does not.** No `Intro\` string is in `KnightOnLine.exe`; its login is the source's `CGameProcLogIn_1298`: a UIF intro, `UIs_us.tbl`'s `ka_login_intro_us.uif` or `el_login_intro_us.uif` (a random nation), under `co_login_us.uif`. *Corrected by RQ-110 (§9.5, binary): not under it; 1298's login Init loads only the intro layout, which is the login UI itself* | strings of `KnightOnLine.exe`; `GameProcLogIn_1298.cpp` `Init`; `Data/UIs_us.tbl` | binary (strings); source; local-asset |
| **1097's login music is sound 35, `Snd\bgm_login.wav`.** The Init releases the BGM stream `006e045c` (`0042e860`, at `0052409d`) and creates it again from sound 35 (`push 0x23` at `005240a2`, `0042e7e0`, the store at `005240b3`); 1097's `Data/sound.tbl` row 35 is `Snd\bgm_login.wav` (the pinned tree's file, byte for byte: 22,050 Hz stereo 16-bit, 477,749 frames, 21.67 s). The tick plays it (`004327d0` at `0052491d`) when its timer `006e0344` is 0, adds the frame time, and past 21.66 s (`0058fc74`) puts the timer back to 0 and calls `004328e0` (the source's `Stop`): the track restarts about every 21.66 s, its own length. That is the source's 1098 login (`CreateStreamObj(35)`, the 21.66 s timer). 1298's row 35 is `bgm_login.mp3`; its login names no sound id but the file `Snd\Intro_Sound.mp3` (next row) | `0052409d`–`005240b3`, `005248f5`–`00524957`; `Data/sound.tbl`; `Snd/bgm_login.wav` | binary; local-asset |
| 1097's select Init `0043a950` and Tick `0043b550` (the range `0043a950`–`0043b550`) call neither `0042e7e0` nor `0042e860` and do not name `006e045c`; the select releases the music only after the start clip (§8.1, `0043ed20`). *Corrected by RQ-083 (next rows):* by then the login has already replaced sound 35 with sound 20003, so the select never plays `bgm_login.wav` | `objdump` of `0043a950`–`0043b550` | binary |
| **RQ-083: a 1097 stream plays its file once unless its loop byte is set.** `0042e7e0` creates the stream through `0042e6e0`: a `0xcc`-byte object (`004329e0`, vtable `0058cc48`) whose base constructor `00431950` clears the loop byte `+0xc`. Its Create (`00432ae0`) opens the WAV with `mmio` and makes a two-block DirectSound buffer, a block one second (`nBlockAlign` × `nSamplesPerSec`), counting the data's whole blocks (`+0x3c`). The sound manager's tick (`0042e8d0`) ticks each stream (`00433000`, at `0042e99f`): on a play request (state 1) it seeks back to the data (`mmioSeek(…, 0x2c, …)`, `push 0x2c` at `00433041`), fills both blocks and plays the buffer circularly from 0 (`00432f60`). At each block boundary `00432f60` counts down and refills the block just played (`00432e60`: the next second, then the last part block, then silence); past the count it calls Stop (`004328e0(0)`, at `00432fcd`) when the loop byte is 0, or Play (`004327d0(0,0,0,1)`, at `00432fe2`) when it is 1, which seeks back on the next tick. The login sets no loop byte on sound 35 (`0052409d`–`005240b3`), so its stream would stop after one pass (21.67 s of data and silence to the next second); the login's tick restarts it first, at 21.66 s (`0058fc74` holds 21.66f) | `00431950`, `004329e0`, `00432ae0`, `00432e60`, `00432f60`, `00433000`, `0042e6e0`, `0042e8d0` | binary |
| **RQ-083: 1097's game-server login answer switches the music to sound 20003, looping, before select.** `00525b70`, the login's answer to the game server's login (the source's `MsgRecv_GameServerLogIn` in `CGameProcLogIn_1098`), releases `006e045c` (`0042e860`), creates sound `0x4e23` = 20003 (`push 0x4e23` at `00525e93` and `00525ee4`), sets its loop byte (`mov byte [eax+0xc], 1` at `00525eaf` and `00525f00`) and plays it (`004327d0` at `00525ebd` and `00525f0e`), for a character without a nation and for Karus or El Morad alike, then activates the nation select (`006e048c`) or the character select (`006e0494`) (`00545ae0`, `00525f19`). 1097's `Data/sound.tbl` row 20003 is `Snd\bgm_el_battle.wav`: the pinned tree's `Snd/bgm_El_battle.wav`, byte for byte (sha256 `d45bf054…`; 22,050 Hz stereo 16-bit, 3,995,263 frames, 181.19 s). 1298's row 20003 is `Snd\bgm_el_battle.mp3`, row 35 `Snd\bgm_login.mp3`. The source does the same (`CreateStreamObj(ID_SOUND_BGM_EL_BATTLE)`, `Looping(true)`, `Play()`) | `00525b70` (`00525e84`–`00525f19`); `Data/sound.tbl` of both trees (`tools/assetc/ko_tbl.py`); `Snd/bgm_El_battle.wav` | binary; local-asset; source |
| Every instruction that names `006e045c` in 1097: `0043dc15` (the select's `0043db70`) and `0043ee47` (the select's `0043ed20`) release it before loading; `00507bdb` (`00507b10`, the entry at `0058f280` of a procedure vtable, not read further) releases it; `00524093`–`005240b3` (the login Init) and `00525e84`–`00525f04` (above) create it. The create procedure names none, so create leaves sound 20003 running. The login's timer `006e0344` is written only by the login tick (`005248f5`–`00524957`): no Init resets it (the source's function-static `fTmp`), so a return to the login, whose Init creates sound 35 again, plays it only when that timer next passes 21.66 s | `objdump` of the 1097 image (every operand `0x6e045c`, `0x6e0344`) | binary |
| 1298's login music is `Snd\Intro_Sound.mp3`, looped from login to the select's start (`content/front-end.md`, "Moradon", `005f68e0`) | `005f68e0`, `005f98c0`, `005fea70` | binary |
| **1097's layouts are another UIF version.** `UI\co_login.uif`, `Ka_CharacterSelect.uif`, `Ka_CharacterCreate.uif`, `Ka_MessageBox.uif`, `Co_Loading.uif` and `ka_loading.uif` are not in the pinned tree, and `tools/assetc/ko_hud.parse` refuses them (`count out of bounds`, `UI version header`). They name no label text in ASCII: the login's labels are in its art, `ui\ui_login.dxt`, which is byte-identical to the pinned tree's `UI/ui_login.dxt` | the 1097 install's `UI/`; `ko_hud.parse` | local-asset |
| **RQ-085: 1097 reads the Korean `Data\UIs.tbl` on an English or Korean Windows.** It builds the table name from `"Data\UIs"` and a tail: `".tbl"` (`0052d349`–`0052d361`), replaced by `"_TW.tbl"`, `"_ch.tbl"` or `"_jp.tbl"` when the low word of the user's language id (the call at `0052d371`) is `0x404`, `0x804` or `0x411` (`0052d37c`–`0052d3cc`), then joins them (`push 0x5a4cc0` at `0052d64d`). The install has `UIs.tbl`, `UIs_tw.tbl` and `UIs_ch.tbl` and no `_us` table or layout. `UIs.tbl`'s two rows (Karus, El Morad) name the login `UI\co_login.uif` (both), create `UI\Ka_CharacterCreate.uif`, select `UI\Ka_CharacterSelect.uif`, the message box `UI\Ka_MessageBox.uif`, and the loading layouts `UI\Co_Loading.uif`, `ui\\el_loading.uif` and `ui\\ka_loading.uif` (the files on disk are `ka_characterselect.uif`, `ka_messagebox.uif`, `co_loading.uif`) | `0052d340`–`0052d6a0`; `Data/UIs.tbl` | binary; local-asset |
| **RQ-085: 1097's UIF is 1298's with two differences.** The base loader `00401840` (vtable `0058c380` slot 3) reads the child count as one 32-bit word (`push 4` at `00401876`), where 1298 reads a 16-bit count and a 16-bit header word (`ko_hud.parse`'s `reserved_header`); each child's type is a 32-bit word (`004018a5`) dispatched through the table at `00401f70` (types 0–9 and 14; 10–13 take the default branch `00401a9c`, not read further); after the children it reads the id, the region and movable rects (16 bytes each, `00401c06`, `00401c19`), style and reserved (`00401c29`, `00401c39`), the tooltip and the open and close sound names (`00401c4a`–`00401e53`), as 1298 does. The string (type 6) loader `0040ad10` (vtable `0058c708` slot 3) reads the base, the font name, height and flags, the colour (`+0xc4`, `0040ae4b`) and the text, and ends there: 1298's reads one more word (the line spacing). Read that way, all six layouts parse to their last byte; the source's `N3FORMAT_VER_1098` path is the same (`N3UIBase.cpp` `Load`, `N3UIString.cpp` `Load`) | `00401840`, `00401f70`, `0040ad10`; the six layouts | binary; local-asset; source |
| **RQ-085: 1097's login, create and message box draw Korean labels; its select and loading draw none.** Login (`co_login.uif`, sha256 `183e23ec…`): `Btn_Connect`, `Btn_Login`, `Btn_Cancel`, `Btn_Option` and `btn_join` draw 접속, 로그인, 취소, 옵션 and 회원가입 from `ui\ui_login.dxt` (`86a37f99…`, the pinned tree's `UI/ui_login.DXT` byte for byte, which 1298's US layouts do not draw); the strips `login00`/`login01` draw English "ID" and "Password" with the Korean buttons baked in; `Img_Grade` draws the Korean all-ages mark 전체 이용가 from `ui\service_logos.dxt` (`53c8dfdf…`, also in the pinned tree), which also holds the MGAME and Daum logos the install has and the pinned tree's `ui_us\service_logos.dxt` path lacks. Its tree: `Group_ServerList` (`img_server_00–02`, `Btn_Connect`, `List_Server`), `Group_LogIn` (`login00`, `login01`, `Edit_ID`, `Edit_PW`, `Btn_Login`, `Btn_Cancel`, `Btn_Option`, `btn_join`, `Img_Grade`), `Img_Daum`, `Img_MGame`, `Text_Rights` (English copyright, font 돋움); no `premium` and no notice groups. Create (`Ka_CharacterCreate.uif`, `1feb3e4a…`): every race and class button, create and cancel, and the stat, face and hair labels are Korean (`ui\ui_ka_charcreate02.dxt` `1b68cc9c…`, `ui\ui_el_charcreate01.dxt` `d64e5982…`, both the pinned tree's `UI/` files); only the name label reads "Name". Message box (`ka_messagebox.uif`, `b5484e55…`): `btn_ok`/`btn_yes` draw 확인 and `btn_cancel`/`btn_no` 취소 from `ui\ui_message.dxt` (`435eafce…`, not the pinned tree's `UI/ui_Message.DXT`); its English OK/Cancel tiles are not drawn by it; nodes `Text_title`, `Text_Message`, `Edit_Common`, `btn_yes`, `btn_no`, `btn_ok`, `btn_cancel` (OK and Cancel share one rect). Select (`ka_characterselect.uif`, `3ca8679f…`): `text00`, `bt_delete` ("Delete"), `bt_exit` ("Exit"), `bt_left`, `bt_right` from `ui\ui_login.dxt`, all English or unlabelled; it has **no back button**. Loading: `co_loading.uif` (`1d9cd4b3…`) and `ka_loading.uif` (`fbc6f9eb…`) draw pictures and the "www.knightonline.co.kr" logo, no Korean; their texts are English ("Ver", "Loading..."); `ui_ka_loding_01.dxt` is DXT1. Every text names a Korean font (굴림, 굴림체, 돋움) | the 1097 install's `UI/` (sha256, decoded and viewed) | local-asset |
| Which loading layout 1097 draws: the source picks by the last war's victor, none `Co_Loading`, El Morad `el_loading`, Karus `ka_loading` (`CGameProcedure::LoadingUIChange`: the `szLoading`/`szElLoading`/`szKaLoading` columns of the table's El Morad row; 1097's two rows name the same three files); 1097's choice was not read | `GameProcedure.cpp` | source |
| 1298's layouts, the ones the package cooks today: `UIs_us.tbl` names `UI_us\co_login_us.uif`, `Ka_CharacterSelect_us.uif`, `Ka_CharacterCreate_us.uif`, `Ka_MessageBox_us.uif`, `Co_Loading_us.uif` and `ka_loading_us.uif` (the package draws `co_MsgBoxOk_us.uif` for the message box, also in the tree) | `Data/UIs_us.tbl` | local-asset |
| 1298's select: per-race `upc_ka_<race>` joints and clips, clip 1 looping on the character in front without the pointer, start clip 2 once with 0.6 s, the turns through recorded `.n3camera` paths, no rotate sound (§8, §8.2). Its lights are `ChrSelect\ka_light_0–2.n3light` (strings); no `ka_chairs` or `ka_cave` name is in the binary, so which hall mesh it draws was not read (RQ-012). *RQ-087 (§8.4):* it draws the `karus_intro` zone (10001) | §8, §8.2; strings of `KnightOnLine.exe` | binary |
| 1097's select: `ka_chairs.n3shape`, `ka_light_0–2`, the `upc_ka_*_<class>` files and their hover, rest and start clips, the turn about `at`, sound 2501 on each turn (§8.1, §8.2). These are the files and behaviour the package cooks today | §8.1, §8.2 | binary |
| `ChrSelect/`: 246 files are identical in all four installs. 1298 adds the per-race `upc_ka_<race>.n3joint`/`.n3anim` and the `Data/ka_*_camera.n3camera` paths. 2145 and Steam keep those, rewrite every `.n3anim` (other bytes: the 2145 clip format, `tools/ko-reference/anim_2145.py`) and add `Data/camera1–13.n3camera`, `ka_light_3.n3light` and `choice_upc_kurian` (the Kurian race); Steam adds further clips (`upc_ka_wt_ma_destan1`, `upc_ka_wt_ma_zion`, `upc_ban_zion`, `hotkey_zion_kyran`, …) and drops `char_select.uif` | `ChrSelect/` in each install (sha256 of every file) | local-asset |
| 2145 keeps `UI/` in its pack (`UI/ui.hdr`, 5,788 entries; `tools/ko-reference/pack_2145.py`). Its `UIs_us.tbl` (row 1) names `ui\co_login.uif`, `UI\re_CharacterCreate.uif`, `ui\ka_CharacterSelect.uif`, `ui\co_Loading.uif`, `ui\ka_loading.uif`, `ui\co_MsgBoxOk.uif`, `ui\re_login_intro.uif`, `ui\co_login_intro_sub.uif`, `ui\re_characterselect.uif`, `ui\re_nation_Select.uif` and `ui\co_introduction.uif`. Its `co_login_us.uif` and `ka_characterselect_us.uif` are byte-identical to 1298's; `ka_charactercreate_us.uif`, `ka_loading_us.uif` and `co_msgboxok_us.uif` differ, and `ko_hud.parse` refuses `ka_loading.uif` and `co_msgboxok_us.uif` (`UI version header`) | the 2145 install's `UI/ui.*`, `Data/UIs_us.tbl` (`tools/ko-reference/tbl_2145.py`) | local-asset |
| 2145's sounds are Ogg Vorbis: `Snd/bgm_login.ogg`, `intro_sound.ogg`, `Intro_Old_Sound.ogg` (and an `Intro_Old_Sound.mp3`), `char_select_turn.ogg`. Which its screens play was not read (the exe is packed) | the 2145 install's `Snd/` | local-asset |
| Steam keeps `UI/` and `Snd/` in packs that are not 2145's: each `.hdr` starts with the word 200,000 (`40 0d 03 00`) and a second word before the first name, which the 2145 reader refuses | `UI/ui.hdr`, `Snd/snd.hdr` | local-asset |
| The Steam dump names `CGameProcIntro`, `CGameProcIntroChrSelect`, `CUILoginIntro`, `CN3OggDecoder`, `CBGMManager`, `Snd\Intro_Sound.mp3`, `Snd\Intro_Old_Sound.ogg`, `ChrSelect\Data\camera1–13.n3camera` and `ChrSelect\ka_light_%d.n3light`; its login runs through `Launcher.exe` (WebView2) and Steam (`steam-rea/README.md`). Nothing of its behaviour was read | strings of `KnightOnLine.unpacked.exe` | binary (strings) |

What the engine expresses as data today (N3FE version 4; version 5, RQ-083, adds the
PCM tracks and the restart period; version 6, RQ-086, the front-clip mode; version 7,
RQ-087, the turn mode; version 8, RQ-095, a zone hall and its fog) and what it lacks,
per screen. A choice can be offered only when every row it needs is data:

| | Data today | Not yet |
|---|---|---|
| Login scene | the 1098 scene (1097's): camera, lights, the model's one clip and plugs, the moon quad | 1298's UIF intro (`ka_login_intro_us.uif`, wrapped UVs; spec 11 left it out), 2145's `re_login_intro`, Steam's intro procs |
| Layouts | UIF trees `ko_hud.parse` reads (1298's and 1264's, the same files; 2145's `co_login`, `ka_characterselect`), bindings, moves, hidden, states, a string's text; a state image's own children (1264's message box labels, §9.2; client behaviour, no format change); since version 13 (RQ-109, §9.6) 1298's select bar, `co_CharacterSelect_us.uif`, with its start, create and delete buttons and three info texts; since version 14 (RQ-111, §9.7) the message box's Yes and No, shown for the select's exit question | 1097's UIF version; the 2145 versions it refuses; Steam's pack; a loading layout chosen at run time by the last war's victor (Q80) |
| Select hall | meshes, lights, slots, the turn about `at` with per-slot ends, the spot's rate, front/start/rest clips with blend times, plugs; since version 6 (RQ-086) the front-clip mode, 1097's hover or 1298's loop, and as recipe data 1298's per-race joint and clips with the default looks (§8.3); since version 7 (RQ-087) the path turn mode with 1298's recorded `.n3camera` paths, its select UI hidden while they play, and as recipe data its slots and spots (§8.4); since version 8 (RQ-095) a zone as the hall, 1298's `karus_intro` (its terrain, static shapes and alpha parts), and the camera's fog | the zone's sky, light maps, grass, birds and animated shapes (Q79); each slot's own looks (RQ-005); 2145's `.n3anim` format (convertible: `anim_2145.to_1298`) |
| Music | MPEG-1/2 Layer III tracks per screen, looping or once (1298's `Intro_Sound.mp3`); since version 5 (RQ-083) 16-bit PCM tracks and a restart period (1097's `bgm_login.wav` every 21.66 s, `bgm_el_battle.wav` looping); RQ-096 carried the period's clock for the process, 1097's and 1264's login timer (Q75, §9.1; client behaviour, no format change), off by default since RQ-105 (Q75 (a): every entry starts the track at once) | Ogg Vorbis (2145, Steam) |
| Sounds | a sound-table id bound in `audio.bin` (1097's turn sound 2501) | 2145's Ogg `char_select_turn.ogg` |
| Text | six strings, KO's UIF texts as they are | KO's text tables for them (RQ-013) |

**Decides (RQ-078):** today's package is the "1097" choice: 1097's login scene and
select hall, with two parts still 1298's. Its layouts are 1298's `UI_US` files,
because `ko_hud` cannot read 1097's UIF version. Its music is 1298's
`Intro_Sound.mp3`, because the format carries only MPEG frames and 1097's track is a
WAV. *RQ-083:* the music is now 1097's (N3FE version 5): `bgm_login.wav` on the
login and the realm list, restarted every 21.66 s, and `bgm_el_battle.wav`, looping,
on select and create, as the rows above read them. A "1298" choice needs the front-clip mode, the camera paths, 1298's UIF intro
and 1298's looks. *RQ-086:* the front-clip mode and 1298's select character with its
default looks are data (§8.3, `games/moradon/front-end-1298.json`, not offered);
the camera paths, 1298's hall and slots and its UIF intro are not. *RQ-087:* the
camera paths, the UI hidden while they play, and 1298's slots and spots are data
(N3FE version 7, §8.4); 1298's hall (the `karus_intro` zone) and its UIF intro are
not. *RQ-095:* the `karus_intro` zone and the camera's fog are data (N3FE version
8, §8.4), its sky not yet (Q79); the UIF intro is not. *RQ-109:* 1298's own select
bar is data (N3FE version 13, §9.6). *RQ-111:* its Exit's yes/no box is data
(N3FE version 14, §9.7). A "2145" choice needs a reader for its UIF versions and an Ogg
decision. Steam is not cookable yet: the packs are not readable, the exe is protected,
and the install changes with every Steam update. The follow-up items are filed under
RQ-078.

**RQ-085 (closed by the maintainer's answer, §9.2):** 1097's layouts are readable (one
32-bit child count, no string line spacing), but as 1097 draws them on an English or
Korean Windows, the login, create and message box carry Korean labels in their art,
and 1097 has no English layouts to draw instead. Its select and loading carry none,
but its select has no back button, which the realm's select requires (`back`). The
"1097" choice therefore keeps 1298's English `UI_US` layouts until the maintainer
decides whether to ship 1097's art as it is. *Maintainer (2026-11-02):* the 1097
choice draws 1264's English `UI_US` layouts. §9.1 (RQ-096) finds them the pinned
tree's own files, which `ko_hud` reads. §9.2 (RQ-085) compares what 1264 draws with
what the choice drew, and the choice now reads its screens from the 1264 install.

### 9.1 The 1264 client: login music and layouts (RQ-096, 2026-11-02)

The 1264 client is `build/ko-reference/installer-1264/client/KnightOnLine.exe`
(sha256 `75481f77…36de69e163`), unpacked from the installer
`knightonlinesetup_1264.exe` (`eb4e1a35…`) by `tools/ko-reference/unpack_installer.py`.
It is packed with ASProtect like 1097's (§8.1): nameless sections at entropy 8.0, an
empty `.adata`, one import per DLL, and the entry `push 007b7001; call; ret` into a
stub in the fifth section. It was unpacked as §8.1's was, with `build/rq074/tools/`'s
scripts copied to `build/rq-1264/tools/`:

- A copy of the exe and the install's `mss32.dll` (Miles, `7855b8fb…`, which it
  imports) ran under Wine 11.20 (WoW64) in a new throwaway `WINEPREFIX` under
  `build/rq-1264/`, inside `unshare -n -c` (no network) and `xvfb-run`, with
  `WINEDLLOVERRIDES` disabling `winemenubuilder` from the first command (`wineboot`
  included). The desktop entries, MIME and icon trees were unchanged afterwards.
- The runner, a child subreaper, copied the image (`00400000`–`007ca000`) every few
  milliseconds. Without `mss32.dll` beside it Wine did not start it (the import
  was not found). With it, three of four runs ended in ASProtect's loader: it
  picks random kernel32
  exports and reads the three bytes before each, looking for a `ret`
  (`018b1ab4`–`018b1aef`), and one read fell before kernel32's base
  (`018b1ac8`). The fourth ran on to the display-mode change and was stopped.
- The kept snapshot is the one after the last code-section change and before the
  program wrote its data (0.939 s; sha256 `0078c302…dfc7aefb38`).

The snapshot was rebuilt into a PE (sha256 `61e9a086…99e136471`):

- Raw layout equals the virtual layout.
- The entry is `006296bb`, VC6's `WinMainCRTStartup`; its first 38 bytes were stolen
  and stay zero (the first kept instruction, `006296e1`, calls `GetVersion`).
- A new import directory sits on the original IAT, `00648000`–`00648468`: 262 of its
  269 slots resolve, 40 of them to `mss32.dll`. The 7 kernel32 slots ASProtect
  emulates are named `aspr_<slot>`. The other kernel32 slots go through redirect
  stubs whose alternate code precedes them (`alt = stub - 0x0c`). Checked at the CRT
  entry (`00648154`, `GetStartupInfoA`) and the UIF loader (`0064818c`,
  `ReadFile`); the 1097 rebuild has the same offset (§8.1, corrected).

It was analysed with Ghidra 12.1.3 (full analysis) in `build/ghidra/rq096/` with
`AuditReference.java`, and with `objdump` for code Ghidra left undefined. Nothing here
is committed. Addresses are the 1264 image's (base `00400000`). The tables were read
with `tools/assetc/ko_tbl.py` and the layouts with `tools/assetc/ko_hud.parse`.

| Observation | Where | Label |
|---|---|---|
| **1264 draws the 1098 login scene too.** The login Init `005bd9b0` loads `Intro\Moon.dxt`, `Intro\Intro.N3Chr` and `Intro\0–2.N3Light` (strings `0066df28`–`0066df6c`; pushed at `005bda15`–`005bdd21`). Its select names `ChrSelect\ka_chairs.n3shape` and `el_chairs.n3shape` (`0043fcde`, `0043f921`): 1097's hall | `005bd9b0`; strings | binary |
| **The login music is sound 35, a looping Miles stream.** The login Init releases the BGM `007ad084` (`004347a0` at `005bdd80`) and creates sound 35 as a stream (`00434540(0x23, 2)` at `005bdd8f`, the store at `005bdd99`); it does not play it. Kind 2 opens a stream (`00436990`: `AIL_open_stream` at `00436c2f`) and sets its loop count to 0 (`AIL_set_stream_loop_count` at `00436c3f`), which Miles plays without end. So unlike 1097's (§9, `00432f60`), 1264's stream would loop by itself. 1264's `Data/sound.tbl` (`b123c238…`) row 35 is `Snd\bgm_login.mp3`, the pinned tree's `Snd/bgm_login.MP3` byte for byte (`9616c423…`; MPEG-2 Layer III, 22,050 Hz mono, 829 frames, 21.66 s). 1264 also ships 1097's `bgm_login.wav` (`c4cc37c9…`), which its table does not name | `005bd9b0`, `00434540`, `004345d0`, `00436990`; `Data/sound.tbl`; `Snd/` | binary; local-asset |
| **The login tick keeps 1097's timer.** The login tick `005be500` (procedure vtable entry `0064dc60`) plays the BGM (`00437090(0,0,0)`: `AIL_set_stream_position(…, 0)`, then `AIL_start_stream`) when its timer `007ac9d0` equals 0.0 (`0064875c`). It then adds the frame time (`006699a0`), and past 21.66 (`0064dc6c`, `ae47ad41`) sets the timer to 0 and calls Stop (`004371a0(0)`: `AIL_pause_stream(…, 1)`). The next tick plays from the first sample. Only this tick reads or writes `007ac9d0` (`005be538`, `005be56f`, `005be575`, `005be58a`): the timer counts only while the login shows, and no Init resets it | `005be500`, `00437090`, `004371a0`; refs of `007ac9d0` | binary |
| **The game-server login answer** `005bf910` reads the nation (`+0x39c`, `005bfc35`). With none, it releases the BGM (`005bfc4a`) and opens the nation select silent. For 1 or 2, it releases it, creates sound 20003 (`push 0x4e23` at `005bfc80`, `00434540` at `005bfc85`), sets it looping (`00437380(1)` at `005bfc97`: loop count 0), plays it (`005bfca5`) and opens the character select. 1264's row 20003 is `Snd\bgm_el_battle.mp3`, the pinned tree's file byte for byte (`331a3f6f…`; 22,050 Hz mono, 362 s). 1097 starts 20003 for a character without a nation too (§9) | `005bf910` | binary; local-asset |
| **A return from select to the login:** the Init runs again. It releases sound 20003 and creates sound 35, unplayed. The tick plays it only when `007ac9d0` next passes 21.66 s, so the login is silent for the rest of that 21.66 s, as in 1097 (§9). The first login of a process plays at once (the timer starts at 0). The BGM is also released before loading (`004426d0` at `00442774`, `00443810` at `00443901`, both ending in "Loading data...") | `005bd9b0`, `005be500`, `004426d0`, `00443810` | binary |
| **The login character restarts at each Init and keeps the frame clock (RQ-104).** The login Init `005bd9b0` makes the character anew (`operator new(0x220)`, `0044b380`, kept at `+0x18`), loads `Intro\Intro.N3Chr` and sets clip 0 (`0044fa20(0, 0, FLT_MIN, 0, 1)` at `005bdb3c`: pushed `1, 0, 0x800000, 0, 0`, the first argument last, as 1097's `00447e30(0, 0, FLT_MIN, 0, 1)`), which puts its frame (`+0x1d8`) at the clip record's start (`+0x10`). The login tick ticks it before the music's timer (`0044c330(FLT_MIN, 0, 0)` at `005be533`; `0064dc3c` holds `00800000`), and with `FLT_MIN` `0044c750` adds the frame time (`006699a0`) times the clip's rate (record `+0x18`) and loops by the clip's length. `Intro/intro.n3anim`'s clip 0 runs frames 0–650 at 30 a second: 21.667 s, the track's length. So on a process's first login the character and the track start on the same tick and keep time (they part by about a frame a period: the track restarts a frame past 21.66 s); on a return the character starts at its first frame while the track waits for the carried timer, out of step by that timer. 1097 is the same: its tick (`005248c0`) ticks the character (`call *0x1c(%eax)` at `005248f2`, argument `0058fc44`, `00800000`) before the timer (`005248f5`), and its Init sets clip 0 (§9, `00523e2e`) | `005bd9b0`, `0044fa20`, `005be500`, `0044c330`, `0044c750`; 1097 `005248c0`; `Intro/intro.n3anim` | binary; local-asset |
| A logo procedure (Init `005fa500`, Tick `005fa7c0`, vtable entries `0064e080`/`0064e084`) loads `co_usa_logo_us.uif` (column 130, `+0x824` of the table node). It creates the BGM stream (`Snd\bless.wav`, set to play once: `00437380(0)`), plays it 1 s after the first tick (`006489e4`) and stops it with a 4 s fade on its UI's state 2. The login Init releases it. When it runs, its fades, its sound and what skips it: §9.2 (RQ-101) | `005fa500`, `005fa7c0` | binary |
| **1264 reads `Data\UIs_us.tbl` whatever the Windows language.** Its table tail is set to `".tbl"` and then `"_us.tbl"` with no test between (`005ceef8`–`005cef29`, the string assignment `004071b0`; the same at `005f6d34`–`005f6dbd`) and joined to `"Data\UIs"` (`0066e738`, `005cf4b9`). The image imports no language-id call. 1264's `UIs_us.tbl` (`04d2abd3…`) has two rows (1 Karus, 2 El Morad) of 130 strings; the pinned tree's (`c91c3579…`) has 144, the first 130 of them the same names (letter case aside) | `005ce7c0`, `005f6850`; `Data/UIs_us.tbl` | binary; local-asset |
| **The five screens' layouts.** A row's string `k` is at `+4 + 16(k − 1)` of the row (`+0x10` of its map node). Login (`005bd9b0`): the first row's column 1, `UI_us\co_login_us.uif`. Select (`0043f530`, vtable entry `00648ea0`): the player's nation's row (`+0x39c`), `+0x174` (`0043f71e`), column 24, `Ka_CharacterSelect_us.uif` or `El_CharacterSelect_us.uif`. Create (`00439550`, `00648dd8`): the nation's row, `+0x164` (`004398be`), column 23, `Ka_CharacterCreate_us.uif` or `El_CharacterCreate_us.uif`. Message box: `MessageBoxPost` (`005f7f80`, the source's name; called from the login's `005bdf00`, `005bf010`, `005bf910` and `005c1d10`, among others) runs `0050c730`, which makes a box (`0050b060`) and loads row 2's column 26 (`+0x194`, `0050c817`), `El_MessageBox_us.uif`, for either nation. Loading (`005f9a30`): row 2, by its argument (kept at `+0x7a8` of `007acf84`; the source's `LoadingUIChange` passes the last war's victor): 1 column 54 `ka_loading_us.uif`, 2 column 53 `el_loading_us.uif`, else column 27 `Co_Loading_us.uif` (node `+0x364`, `+0x354`, `+0x1b4`) | `005bd9b0`, `0043f530`, `00439550`, `0050c730`, `005f9a30`; `Data/UIs_us.tbl`; `GameProcedure.cpp` | binary; local-asset; source (the victor) |
| **They are the pinned tree's files, and `ko_hud.parse` reads them.** `co_login_us.uif` (`e4b10e58…`), `ka_characterselect_us.uif` (`29e3d930…`), `el_characterselect_us.uif` (`2925fc33…`), `Ka_CharacterCreate_us.uif` (`4a1b072a…`), `El_CharacterCreate_us.uif` (`d99738e8…`), `ka_messagebox_us.uif` (`db400aae…`), `el_messagebox_us.uif` (`8f7773d5…`), `co_loading_us.uif` (`19c594d1…`), `el_loading_us.uif` (`284d998a…`), `ka_loading_us.uif` (`32fa6749…`) and `co_MsgBoxOk_us.uif` (`afc88d54…`) in 1264's `UI_US/` match the pinned tree's byte for byte. `ko_hud.parse` reads all ten 1264 screens' files | 1264's and the pinned tree's `UI_US/` (sha256); `ko_hud.parse` | local-asset |
| **1264's UIF loader is 1298's version.** The base loader `00401860` (vtable `00648470` slot 3) reads the child count as 16 bits (`push 2` at `0040189e`), then a 16-bit header word (`004018b5`), then each child's 32-bit type (`004018d7`), through `ReadFile` (`0064818c`). That is `ko_hud.parse`'s layout (`reserved_header`), not 1097's 32-bit count (§9, `00401840`). Its string loader (the line spacing) was not read; the files above are 1298's byte for byte, which the same reader parses to their last byte | `00401860` | binary |

**Decides:** Q75 (b). 1264 keeps 1097's login timer, so the realm follows both: the
restart period's clock is the process's (content/front-end.md section 9). (RQ-105,
maintainer: Q75 is now (a); the carried clock is kept off by default.) RQ-104: the
login scene's clock starts at each entry and keeps the login track's heard time
(`client/render/scene_clock.h`; Q83 records KO's own drift on a return). For RQ-085,
1264 draws the pinned tree's own English `UI_US` login, select, create, loading and
message box layouts, which `ko_hud` already reads, so no reader (RQ-094) is needed for
them. Two of 1264's choices differ from what the package draws today, and they are
RQ-085's to take:

- the message box is `El_MessageBox_us.uif` for both nations; the package draws
  `co_MsgBoxOk_us.uif`;
- loading is chosen by the last war's victor.

### 9.2 The 1097 choice draws 1264's screens (RQ-085, 2026-11-02)

The maintainer's answer to RQ-085 (2026-11-02): the 1097 front end draws the 1264
client's screens, "the orc login, select and the rest in English". §9.1 found
1264's layouts to be the files the choice already drew, so this compares, file by
file (sha256), the 1264 install (`build/ko-reference/installer-1264`, its
`manifest.json` naming the installer `eb4e1a35…`) with the pinned tree the choice
read, decodes the textures that differ (`ko_hud.texture`) and looks at them, and
reads §9.1's 1264 image further in the same Ghidra project (output under
`build/ghidra/rq085b/`, not committed), with `objdump` for code Ghidra left
undefined. Nothing from the install is committed.

| Observation | Where | Label |
|---|---|---|
| **The login scene is the one the choice draws.** 1264's `Intro/` (61 files) is the pinned tree's byte for byte, and its login Init loads that 1098 scene (§9.1, `005bd9b0`): the orc with the axe under the moon. The login layout is the same file over it | `Intro/` (sha256); `005bd9b0` | local-asset; binary |
| **So is the select hall.** 266 of 1264's 267 `ChrSelect/` files are the pinned tree's; the one that differs, `upc_el_ba.n3joint`, is an El Morad race's, which the Karus hall does not read. 1264 names `ka_chairs.n3shape` (§9.1), the choice's hall | `ChrSelect/` (sha256) | local-asset |
| **Two textures differ.** Of 1264's 246 `UI_US/` files, 220 are the pinned tree's; of the textures the five screens' layouts name, two are not: `ui_login_01_us.dxt`, which only `co_login_us.uif`'s `Group_Notice_1–3` draw (hidden by the realm, Q61; in 1264 a grey notice frame and English "Back" buttons, in 1298 a gold login and server frame), and `ui_message_us.dxt`. `ui_login_us`, `ui_el_charcreate01_us`, `ui_ka_charcreate02_us`, `ui_loding_us`, `ui_ka_loding_01/02_us`, `ui_el_loding_01/02_us` and `ui_warfare_us` are the same bytes. Every label the five screens draw is English: UIF strings in Arial over unlabelled button art. Neither tree's `UI_US/` has the `service_logos.dxt` the login's `Img_Daum` and `Img_MGame` name (1264's `UI/Service_Logos.DXT` is another path) | both trees' `UI_US/` (sha256, decoded and viewed) | local-asset |
| **1264's message box is `el_messagebox_us.uif` with 1264's `ui_message_us.dxt`.** The box (327 × 156) draws its frame from the texture's block at u 330–459, v 2–131, black in 1264's file and dark grey in the pinned tree's; its buttons are blue bars (u 332–429, v 134–309), each state image holding its own label (`O  K`, `Cancel`, Arial strings) as a child. Its nodes: `Text_title` (text "111"), `Text_Message`, `Edit_Common`, `btn_yes`, `btn_no`, `btn_cancel`, `btn_ok` (OK and Cancel share one rect). The package drew `co_MsgBoxOk_us.uif` (212 × 111, `ui_warfare_us.dxt`) | `UI_US/el_messagebox_us.uif`, `ui_Message_us.DXT` of both trees | local-asset |
| What an OK box shows: `MessageBoxPost` loads the El Morad row's message box (1264: row 2, column 26, `0050c730`, §9.1) and centres it; `SetBoxStyle(MB_OK)` hides Yes, No and Cancel and shows OK; the edit shows only for a character delete; the text and title come from the call, the title empty for the connection-closed and character-select failures. 1264's button handling was not read further. *RQ-115 read it (§9.8): SetBoxStyle `0050bfb0`, ReceiveMessage `0050b510`, OnKeyPress `0050c1d0`, as 1298's* | `UIMessageBoxManager.cpp` `MessageBoxPost`, `UIMessageBox.cpp` `SetBoxStyle`, `GameProcedure.cpp` `ReportServerConnectionClosed`; `0050c730` | source; binary |
| **The loading layout follows a byte the game server sends.** `005f9a30` (the source's `LoadingUIChange`) returns when its argument equals the value kept at `+0x7a8` of `007acf84`; otherwise it keeps it, releases the loading UI `007ad0a0` (which only it creates) and loads row 2's column 54 `ka_loading_us.uif` for 1, column 53 `el_loading_us.uif` for 2 and column 27 `Co_Loading_us.uif` for anything else. Its three callers pass a byte read from a packet: `005f85c0` (opcode `0x46`, the server change: address, port, two zones, then the byte), `005f9440` and `005a4dd0`. In the source the character-select answer and the server change read it (`iVictoryNation`: 0 no victor, 1 Karus, 2 El Morad) and the kept value starts at -1, so the first answer always loads a layout. `Co_Loading_us.uif` draws `ui_loding_us.dxt`'s half-orc, half-human knight and the Knight Online logo; the package drew `ka_loading_us.uif`, Karus's picture | `005f9a30`, `005f85c0`, `005f9440`, `005a4dd0`; `GameProcedure.cpp` `LoadingUIChange`, `MsgRecv_CharacterSelect`, `MsgRecv_ServerChange`; `GameDef.h` | binary; source |
| 1264's login Load names `Btn_Option`, `Img_MGame`, `Text_Rights` and `Group_Notice_` (strings `0066e048`–`0066e08c`, read at `005c101f`–`005c12a2`), not `Img_Daum` or `premium`; what it does with them was not read. The realm's hidden login nodes stay as Q61 decided. *RQ-108 read what it does with `Text_Rights`, `Img_MGame` and `Img_Daum` (§9.4)* | strings of the 1264 image; `objdump` of `005c0fd0`–`005c1320` | binary |
| 1264 has a logo procedure (§9.1, `005fa500`) whose layout, `co_usa_logo_us.uif` with `ui_usa_logo_us.dxt` (both the pinned tree's files too), draws "K2 Network presents Knight Online" in three groups. RQ-101 read it (below) | `UI_US/co_usa_logo_us.uif`, `ui_usa_logo_us.DXT` (decoded and viewed) | local-asset |

**Decides (RQ-085):** what a player sees of 1264 that the choice did not draw is
the message box and the loading picture; the login scene, the select hall and the
login, select and create layouts are the same. The 1097 choice
(`games/moradon/front-end.json`) now reads all five screens' layouts, and the
textures they name, from the 1264 install (`installer-1264`, pinned in
`tools/assetc/ko_installs.py`, each file checked against its manifest):

- message: `el_messagebox_us.uif` as an OK box: `Text_Message` bound to the
  message, `btn_ok` to OK, `btn_yes`, `btn_no`, `btn_cancel` and `Edit_Common`
  hidden, `Text_title` empty (Q81). The client draws a state image's children
  only with it, as `CN3UIBase::Render` does, so each button shows one label;
- loading: `co_loading_us.uif`, 1264's layout for no war victor (Q80), with the
  moves and bindings the choice had for `ka_loading_us.uif` (the source's
  `CUILoading::Load`: centred, `Text_Version` at 10, 10).

1097's behaviour (the hover, the turn and its sound, the music) is unchanged.

**The logo screen (RQ-101, 2026-11-02).** The maintainer, asked whether the 1097
choice shows 1264's logo screen: "lets keep it looking and feeling as close to
the original as possible." So it shows it as 1264 does. Read in §9.1's 1264 image
(`ko1264-unpacked.exe`, sha256 `61e9a086…99e136471`) in the same Ghidra project
(`build/ghidra/rq096`, `-readOnly`, `AuditReference.java` `decompile`, `recover`
for the UI's undefined methods, `refs` and `strings`; output under
`build/ghidra/rq101/`, not committed), with `objdump` for `006024c0`–`00602530`
and `005bd820`–`005bd880` and a byte scan for the logo procedure's pointer;
the layout through `ko_hud.parse` and its texture through `ko_hud.texture`
(nothing committed from either):

| Observation | Where | Label |
|---|---|---|
| **The logo is the process's first procedure, before the login, once.** WinMain calls `StaticMemberInit` (`005f6850`) and, when it succeeds, `ProcActiveSet` (`005f7f30`) with the logo procedure `007ad0d4` (`00602506`–`0060250c`), with no other test between. `005f6850` makes it (`005fa4b0` at `005f71e5`, vtable `0064e064`: Init `005fa500`, Tick `005fa7c0`, Render `005fa850`, ProcessUIKeyInput the base's `005f97a0`); the only other uses of `007ad0d4` are its release (`005f782f`, `005f784c`), so nothing returns to it | `00602506`, `005f6850`, `005fa4b0`; a scan for `d4 d0 7a 00` | binary |
| **Its Init** creates `Snd\bless.wav` (string `0066e9f0`) as the BGM stream (`004345d0(…, 2)` at `005fa5e8`/`005fa615`, releasing a BGM already held first, `004347a0`), sets it to play once (`00437380(0)`: `AIL_set_stream_loop_count(…, 1)`) and does not play it. It loads row 1's column 130 of `UIs_us.tbl` (`+0x824`, `co_usa_logo_us.uif`) into its UI (`00601090`, 0xdc bytes, vtable `0064e1b8`), centres it on the screen (`+0x1c` with half the screen's size less the UI's) and gives it the focus (`00532640`) | `005fa500`, `00601090`, `00437380` | binary |
| **Its UI's Load** (`00601140`, vtable slot 3) finds `group_k2`, `group_presents` and `group_knight` (strings `0066eb1c`, `0066eb0c`, `0066eafc`), shows the first, hides the others, and hides the system cursor (`SetCursor(NULL)`) | `00601140` | binary |
| **Its Tick** (`00601360`, slot 21) raises a fade value (`+0xb4`) by the frame time (`006699a0`) over 1.5 s (`00648f10`; over 1.0 s, `006489e4`, while group 1 shows) until it reaches 1.5 (`00648f10`), then lowers it the same way; once it is below 0 (`0064875c`) it shows the next group alone (`+0x3c` with 0 on each, then 1). After the third it stops ticking and starts the login (`005f7f30(007ad0b0)`; `007ad0b0` is the login, vtable `0064dc40`, Init `005bd9b0`) | `00601360`, `005bd820` | binary |
| **Its Render** (`00600ce0`, slot 22) draws nothing while the value is below 0, the UI as it is from 1 up, and otherwise the UI with `D3DRS_TEXTUREFACTOR` alpha `trunc(value × 255)` (`00648a00`) modulating the texture's alpha (`D3DTSS_ALPHAOP` `MODULATE` of `TEXTURE` and `TFACTOR`), blended source alpha over its inverse. The procedure's Render (`005fa850`) clears the frame (`00422bd0(0, 0)`) before the UI. So each group fades in over its time, holds as long and fades out as long: `group_k2` 1.5, 1.5 and 1.5 s, `group_presents` 1, 1 and 1 s, `group_knight` 1.5, 1.5 and 1.5 s; 12 s in all, then the login | `00600ce0`, `005fa850` | binary |
| **The layout** (`co_usa_logo_us.uif`, `6786b7f1…`, and `ui_usa_logo_us.dxt`, `8f975546…`, the pinned tree's bytes too): a 1024 × 768 root with the three groups, each a full-canvas image of a black block of the texture (texels `000000ff`) and its art: "K2 Network" at (371, 290)–(648, 443), "presents" at (350, 341)–(676, 405), "Knight Online" at (258, 291)–(753, 458). So the screen is black around the art, which fades from and to black | `UI_US/co_usa_logo_us.uif`, `UI_US/ui_usa_logo_us.DXT` (sha256, parsed, decoded) | local-asset |
| **The music.** The procedure's Tick (`005fa7c0`) keeps its first tick's time (`00414cd0`, the performance counter) and, once 1.0 s (`006489e4`) has passed, plays the BGM from its start (`00437090(0, 0, 0)`), once (flag `007ad151`); when the UI's group is 2 (`+0xb8`) it stops it with a 4 s fade (`004371a0(4.0)`, flag `007ad152`). The sound's tick (`00436cd0`) runs the fade as the volume times the time left over the fade (`timeGetTime` ms × 0.001, `00648abc`), so linearly to 0, and then stops it (`00437260`). `Snd/bless.wav` (`16f4c501…`, the pinned tree's file too) is 22,050 Hz mono 16-bit, 305,280 frames, 13.84 s: it plays from 1 s and is silent from 11.5 s (group 2 starts at 7.5 s). The login Init releases it and creates sound 35, which its tick plays at once on the first login (§9.1) | `005fa7c0`, `004371a0`, `00436cd0`; `Snd/bless.wav` | binary; local-asset |
| **What skips it: any key, not a click.** The UI's OnKeyPress (`00601480`, slot 24, `0064e218`) stops its tick and starts the login (`005f7f30(007ad0b0)`), returning 1. ProcessUIKeyInput (`005f97a0`, called with 1 by the base Tick `005f7990`) calls the focused UI's slot 24 for each of the 256 DirectInput keys whose press state (input `+0x26c`) is set; that state is the frame's edge, up at the last poll and down at this one (source `LocalInput.cpp`, `m_bKeyPresses`), and `007ad12e` only pairs a press with its release (`s_bKeyPress`), it does not wait for every key to be up. So a key skips it only when pressed while it shows. The UI keeps the base class's slot 20 (`00402080`, MouseProc in the source's CN3UIBase order, before Tick and Render, slots 21 and 22) and overrides no other input method, so a click does nothing. A skip ends the music at once: the login Init's release, with no fade | `00601480`, `005f97a0`, `005f7990`; `N3UIBase.h` (the slot order), `LocalInput.cpp` | binary; source |
| **The login connects; the logo does not.** The login procedure's Init connects to the login server (`CGameProcLogIn::Init`, `s_pSocket->Connect`); nothing in the logo procedure's Init or Tick above opens a socket | `GameProcLogIn_1098.cpp` (`Init`); `005fa500`, `005fa7c0` | source; binary |

**Decides (RQ-101):** the 1097 choice shows the logo screen first, as 1264 does
(QUESTIONS Q82): `front-end.bin` version 9's logo section, cooked from
`front-end.json`'s `logo` (`co_usa_logo_us.uif` and `Snd/bless.wav` from the 1264
install), with its groups' fades, its music's delay and fade-out, a key skipping
it and the cursor hidden (`content/front-end.md` section 10). The login track's
restart clock (Q75) is untouched: the logo plays its own track, and the login's
first entry starts `bgm_login.wav` at once, as 1264's first login does. Only a
key pressed during the screen skips it (not one queued before its first frame or
a modifier SDL reports held on a focus gain), the realm connection starts with
the login, and a message raised during the logo shows on the login (Q82).

**The message titles (RQ-102, 2026-11-02).** The maintainer: "as close to the
original as possible"; Q81 had left every realm message untitled. Read in §9.1's
1264 image (`ko1264-unpacked.exe`) in the same Ghidra project (`build/ghidra/rq096`,
`-readOnly`, `AuditReference.java` `strings`, `refs` and `decompile`; output under
`build/ghidra/rq102/`, not committed), with `objdump` for the text-id pushes and
the argument order at each call, the same pushes in 1298's `KnightOnLine.exe`
(`objdump`), and the 1264 install's and the pinned tree's `Data/Texts_us.tbl`
through `ko_tbl` (nothing committed from either):

| Observation | Where | Label |
|---|---|---|
| **1264 reads every text from `Data\Texts`.** Its text lookup (`005d2350`) starts the result as the empty string (`00674f68`, zero bytes) and finds the row by id in the table `007aced8` holds; the image has no string-table resource. `005f7f80` is CGameProcedure::MessageBoxPost: it passes (result, message, title, style, behaviour) to the manager's (`0050c730`) | `005d2350`, `005f7f80`, `00674f68`; the image's resources | binary |
| **A login server it cannot reach is posted untitled.** The login Init (`005bdf00`) posts row 6609 ("Connecting.  Please wait.") untitled, tries each `Server.ini` address in a random order on port 15100 (`0x3afc`) and, when none answers, calls ReportServerConnectionFailed (`005f8ab0`) with "LogIn Server": row 2905 formatted with the name and the error, the title `00674f68` (empty). With no address it posts "No server list" under "LogIn Server fail". The OpenKO source's "Failed to connect to login server" title is its `_DEBUG` build's only (`GameProcLogIn_1098.cpp` `Init`); 1264 has no such string | `005bdf00`, `005f8ab0`; strings `0066df7c`–`0066df9c` | binary; source |
| **A closed connection and a refused select are untitled.** ReportServerConnectionClosed (`005f8cd0`: row 1601) and CharacterSelectFailed (`004436a0`: row 6066) copy `00674f68` as the title | `005f8cd0`, `004436a0` | binary |
| **The login answer's failures are titled row 2909.** MsgRecv_AccountLogIn (`005bf010`) posts, by the answer's result byte, row 2903 or 2904 (2), 6120 (3), 2907 (4, `005bf30c`), 2902 (5), 2910 (11), 2911 (12) and 2908 for any other (`005bf7a2`), each under row 2909 (`005bf31b` and the like); the message is the call's second argument and the title its third. 1298's binary asks for the same rows (`5f7e6f` row 2907, `5f7e82` title 2909, `5f81f1` row 2908) | `005bf010`; 1298 `KnightOnLine.exe` | binary |
| **The 1264 install's table does not hold those rows' login wording.** Its `Data/Texts_us.tbl` (1,160 rows) has a stat's description at 2909, "Karus" at 2907, "Unconfirmed nation" at 2908 and no "Connection failed." anywhere; the pinned tree's (1298's, 1,557 rows) has "Connection failed." at 2909, "Your account is currently blocked. Please contact customer support." at 2907 and "There is an error in the selected server. " at 2908, as the source's `text_resources.h` names them | both `Data/Texts_us.tbl` (decrypted, `ko_tbl`) | local-asset |
| **The create failures are titled row 1901.** ReportErrorCharacterCreate (`0043a820`) maps the code to row 1911 (1), 1907 (2), 1912 (3), 1902 (4), 1906 (5), 1905 (6), 1908 (7), 1910 (8), 1904 (9), 1913 (10) and 1915 otherwise, under row 1901; its caller MsgSendCharacterCreate (`0043a340`) passes 6 for an empty name and 5 for a forbidden letter, and the server's create answer passes its code (`0043aa9c`). The 1264 install's rows 1901, 1905, 1906, 1911 and 1912 are the source's English ("Failed creating character", "Please enter your character ID. ") | `0043a820`, `0043a340`; the 1264 install's `Data/Texts_us.tbl` | binary; local-asset |

**Decides (RQ-102):** the 1097 choice titles and words, from KO's own rows, the
realm messages that stand for a box 1264 titles: a banned login (2909 over 2907)
and one the realm cannot serve (2909 over 2908, KO's catch-all), from the pinned
tree's table; an empty name (1901 over 1905) and a refused create (1901 over the
server's wording, which names none of KO's reasons), from the 1264 install's. The
rest stay untitled in the realm's words (`content/front-end.md`, "Moradon";
QUESTIONS Q81). `front-end.bin` version 10's message section carries them.

### 9.3 Where KO draws its front end on a larger screen (RQ-106, 2026-11-02)

The maintainer's playtest: "it looks like we are scaling the UI for the login /
select / create screens. we shouldnt do that I dont think because it looks
strange." Read in §9.1's 1264 image (`ko1264-unpacked.exe`, Ghidra project
`build/ghidra/rq096`), §8.1's 1097 image (`ko1097-unpacked.exe`, `build/ghidra/rq074`)
and n3e's 1298 `KnightOnLine.exe` (`build/ghidra/audit-2026-09-19`), each
`-readOnly -noanalysis` with `AuditReference.java` (`decompile`, `recover`,
`refs`, `strings`, `floats`; output under `build/ghidra/rq106/`, not committed),
with `objdump` for code Ghidra left undefined; the 1264 layouts' rects through
`ko_hud.parse` (nothing committed from them). Addresses are each image's own.

| Observation | Where | Label |
|---|---|---|
| **KO's front end is drawn on the screen's own pixels, never scaled.** The device init sets the viewport to the back buffer, `(0, 0, width, height)`, and copies it to `00677e64` (X, Y, then the width `00677e6c` and the height `00677e70`), which every layout placement below reads; the size is `Option.ini`'s, and in full screen KO changes the display mode to it (source `GameProcedure.cpp`, `ChangeDisplaySettings` with `iViewWidth`, `iViewHeight`; `WarFareMain.cpp` reads `[ViewPort] Width` and pairs 1024 with 768, 1280 with 1024, 1600 with 1200). No front-end layout is scaled: a 1024 × 768 layout on a larger screen is placed, at its own size | 1264 `004223c0` (`SetViewport` at `+0xa0`, the copy at `004229c5`); source `GameProcedure.cpp`, `WarFareMain.cpp` | binary; source |
| **The 3D scenes fill the whole screen.** The login's moon is a screen quad at `(100, 50)` × the viewport over 1024 × 768, `Moon.dxt`'s size × 1.3 × the same ratios (each axis apart); the camera's aspect is the viewport's width over its height, its field of view vertical (`CN3Camera::Tick`: `fAspect = vp.Width / vp.Height`, `PerspectiveFovLH`), so the orc and the select hall keep their projection and fill the screen whatever its size, the UI over them. The select's centre rect is 0.36–0.64 × 0.44–0.86 of the viewport (§8). Create draws the character in `area_character`'s rect, clipped to the viewport (1264 `0043aad0`) | source `GameProcLogIn_1098.cpp` `Render`, `N3Camera.cpp`; 1264 `0043aad0` | source; binary |
| **The login: its root centred on the bottom edge.** 1264's login Init sets the root at `((W − w) >> 1, H − h)` from its region (`005bde22`–`005bde3b`), places the grade logo (`005c2a70`: `(W − w − 10, 10)`, a node 1264's Load never sets, `+0xe8`) and sets the region to the whole screen (`005bde46`–`005bde6e`). 1097's does the same (`00524147`–`0052419a`, then `005289f0`). The 1264 root is 984 × 506, so on a 1280 × 1024 screen the login bar sits on the bottom edge, 148 px from each side | 1264 `005bd9b0`; 1097 `00523c80`… | binary |
| **The server list at the screen's top-left.** 1264's login tick (`005c25b0`) slides `Group_ServerList` (`+0xd0`) down to y 0 (`5000 × s_fSecPerFrm`, `006491f0`) at x = the width of a group `+0xd4`, which 1264's Load never sets (only the constructor clears it, `005c0714`), so 0: the group rests at `(0, 0)`, whatever the screen's size, as the source's `OpenServerList` `SetPos(0, −h)` | 1264 `005c25b0`, `005c0714` | binary |
| **The copyright line shows only while a login waits.** 1264's Load hides `Text_Rights` (`+0xdc`), `Img_MGame` (`+0xe0`) and `Img_Daum` (`+0xe4`) (`005c1411`–`005c1441`, `SetVisible(0)` through `+0x3c`); SetVisibleLogInUIs (`005c2820`) hides them again and, with the login group hidden (a login sent, until its answer), shows `Text_Rights` at `((W − w) / 2, H − h − 20)`, beside the MGAME or Daum logo for those classifications. The realm drew it always, where the layout puts it (Q61); RQ-108 takes 1264's (§9.4) | 1264 `005c0fd0`, `005c2820` | binary |
| **1264's select: its buttons on the bottom edge, the arrows spread by the width.** CUICharacterSelect::Load (`004448f0`) takes r = W / the root's width as a float (`00444bdb`–`00444bf5`), then: `bt_left` at x = trunc((W >> 1) − w − 100 − 26 r) (`00444c30`–`00444c5a`; 100.0 at `00648f88`, 26.0 at `00648f84`), `bt_right` at trunc((W >> 1) + 26 r + 100) (`00444c94`–`00444cba`), both at y = H − 10 − h; `bt_delete` at `((W − w) >> 1, 20)` (`00444cf8`–`00444d2a`); `bt_exit` at `((W − w) >> 1, H − 10 − h)` (`00444d41`–`00444d8a`); `bt_back` at `((W − w) >> 1, H − 20 − h_exit − h)`, 10 px above exit (`00444da9`–`00444e06`); the region the whole screen (`00444e09`–`00444e2c`). The root (1024 × 768) and `text00` stay where the layout has them. At 1024 × 768 that puts `bt_right` at 638, exit and back at 412 and back's top at 676, where the layout has 644, 418 and 419, and 635 (names: strings `0066a840`, `0066a834`, `0066a82c`, `0066a820`, `0066a818`) | 1264 `004448f0` | binary |
| **1097's select scales its buttons' x instead.** 1097's CUICharacterSelect::Load (`0043faf0`) sets each of left, right, exit and delete at x = trunc(x × W / the root's width), left, right and exit at y = H − 10 − h, delete at 20, the region the whole screen (`0043fd5a`–`0043fecb`); its layout has no back button (§9). The source's (`UICharacterSelect.cpp`) is 1097's with back 15 px above exit | 1097 `0043faf0`; source `UICharacterSelect.cpp` | binary; source |
| **Create, loading, the message box and the logo are centred.** 1264's create Load centres its root with C's signed division (`0043cd00`, `0043dbcd`–`0043dbf0`: `((W − w) / 2, (H − h) / 2)`; 1097 the same, `00438170`); CUILoading::Load calls SetPosCenter (`00401670`: `(W − w) / 2`, signed) and puts `Text_Version` at `(10, 10)` (`00531c7c`–`00531c8d`; 1097 `004ae25c`–`004ae26d`); the message box manager (`0050c730`) puts each box at `((W − w) >> 1, (H − h) >> 1)` (`0050c88a`–`0050c8f5`); the logo Init (`005fa500`) centres its layout's root with signed division (`005fa71a`–`005fa73a`) and sets its region to the whole screen (from `005fa73d`). Their roots are 1025 × 788 (create), 678 × 433 (loading, at −12, −20), 327 × 156 and 1024 × 768; around them the screen is the clear's black | 1264 `0043cd00`, `00401670`, `00531c7c`, `0050c730`, `005fa500`; 1097 `00438170`, `00401650`, `004ae25c` | binary |
| **1298 places its own layouts the same way, by the screen's edges; it never places the layout the realm's 1298 recipe cooks.** 1298's select is `co_CharacterSelect_us.uif` (a 1024 × 113 bar: `btn_create`, `btn_start`, `btn_delete`, `btn_back`, `btn_exit`, `btn_left`, `btn_right`, `str_id`, `str_lev`, `str_job`; `Data/UIs_us.tbl` names it beside `Ka_CharacterSelect_us.uif`). Its Load (`00606c10`) finds those nodes by name and puts the root at `((W − w) >> 1, H − 10 − h)` (`006070bd`–`0060710a`, from the region's left, top, right and bottom at `+0x80`–`+0x8c`; SHR, so unsigned), the region the whole screen; its in-select create (`00603850`) puts its panels on the bottom edge and slides others in from the screen's sides (`W`, `H − 30 − h`). The exe holds none of `ka_characterselect_us.uif`'s names (`bt_left`, `bt_right`, `bt_exit`, `bt_back`; `strings` finds `btn_left`, `btn_exit`, `str_job`, `text00` and no `bt_*`), so no 1298 code places that layout, which the pinned tree carries byte for byte as 1264's (sha256 `29e3d930…` in both) | 1298 `00606c10`, `00603850`; strings of `KnightOnLine.exe`; the pinned tree's and the 1264 install's `UI_US/` | binary; local-asset |

**Decides (RQ-106):** the client draws every KO front-end layout unscaled, on the
window's own pixels, each placed by its own client's rules at the window's size;
the 3D scenes fill the window with their own projection, as they did. The 1097
choice draws the 1264 install's layouts, so it places them by 1264's code (the
select's arrows by `004448f0`, Q84). The 1298 recipe (not offered) cooks the
pinned tree's layouts, its select byte for byte 1264's, which 1298's code never
places, so it takes 1264's placements too; drawing 1298's own
`co_CharacterSelect_us.uif` bar at 1298's placement is a layout change (a new
item; *RQ-109 (§9.6): drawn now*). The placements are package data (`front-end.bin`
version 11, the recipe's `place` and `moves`): each layout's moves, evaluated at the
window's size by the client and at 1024 × 768 by the cook for the canvas rects.
The realm's earlier scaling of the canvas to fit the window stays as the recipe's
`ui_scale` `window` (RQ-103's option, off by default) and for a window smaller than
the canvas. KO's hiding of `Text_Rights` at the login was left to RQ-108 (§9.4).

### 9.4 When 1264 shows the login's copyright line (RQ-108, 2026-11-02)

The maintainer: "as close to the original as possible". Read in §9.1's 1264 image
(`ko1264-unpacked.exe`, Ghidra project `build/ghidra/rq096`, `-readOnly
-noanalysis`, `AuditReference.java` `decompile` and `refs`; output under
`build/ghidra/rq108/`, not committed), with `objdump` for the login UI's
message handler Ghidra left undefined; the 1264 login layout through
`ko_hud.parse` (nothing committed from it). The source agrees where named.

| Observation | Where | Label |
|---|---|---|
| **SetVisibleLogInUIs(show) is the only code that shows the line.** It shows or hides `Group_LogIn` (`+0xd8`) by its argument and hides `Text_Rights` (`+0xdc`), `Img_MGame` (`+0xe0`) and `Img_Daum` (`+0xe4`); with the argument false it then places and shows the line by the login classification `007ad118`: 1, the line at `((W − w − w_MGame) / 2, H − h − 20)` and the MGAME logo at its right edge, only the line shown (the source shows both); 2, the same with the Daum logo, both shown; anything else, the line alone at `((W − w) / 2, H − h − 20)` (signed division, `00677e6c` and `00677e70` the viewport's width and height). Load hides the three at once (`005c1411`–`005c1441`), so a login that loads shows neither the line nor the logos | 1264 `005c2820`, `005c0fd0`; source `UILogin_1098.cpp` `SetVisibleLogInUIs`, `Load` | binary; source |
| **1264's classification is always 0, so it shows the line alone and never the logos.** `007ad118` has two references, both reads (`005bdedb` in the login Init, `005c2878` above); nothing writes it, so it keeps its static 0 (`LIC_KNIGHTONLINE`) | refs of `007ad118` | binary |
| **A login press hides the bar and shows the line until the answer.** SetVisibleLogInUIs has three callers. The account login send (`005be860`; the source's `MsgSend_AccountLogIn`) connects to the login server (`005bdf00`), then calls it with false, sets the requested-login flags and sends `0xf3` (`0xf4` for MGAME); the Login button's click (`005c0a35`: the sender `+0xb8`, both edits present), the edit's ENTER (`005c0d6d`, unless a message box has the focus) and a message box behaviour (`0050b948`) call it. `005bea20` is the same send for an auto-login from Init (`005bdee7`), only for a classification other than 0, so never in 1264 | 1264 `005be860`, `005bea20`, `005bd9b0`; `objdump` of `005c0a00`–`005c0a3f`, `005c0d40`–`005c0d74` | binary |
| **The answer: a failure shows the bar again, a success keeps the line into the server list.** The login answer (`005bf010`, opcodes `0xf3`/`0xf4` from `005bfce0`) on result 1 closes every message box (`005f7fe0(−1)`) and asks for the server list (`0xf5`), without SetVisibleLogInUIs; on any other result it posts the failure's box (`005f7f80`, the rows of §9.2) and calls SetVisibleLogInUIs(true) and clears the flags, so the box shows over the restored bar, the line hidden. The server list's answer (`005beba0`) fills the list and opens it (`005c2770`: shows `Group_ServerList` `+0xd0` and starts its slide from `(0, −h)`), touching neither the bar nor the line, so the server list shows with the line and without the bar | 1264 `005bf010`, `005bfce0`, `005beba0`, `005c2770`; source `GameProcLogIn_1098.cpp` `MsgRecv_AccountLogIn`, `UILogin_1098.cpp` `OpenServerList` | binary; source |
| **A login server that cannot be reached: the box over the line, and its OK quits.** `005bdf00` reports the failure (`005f8ab0` with quit set) before `005be860` calls SetVisibleLogInUIs(false), so the box shows over the line, the bar hidden, and its OK ends the process (source `ReportServerConnectionFailed`, `BEHAVIOR_EXIT`) | 1264 `005bdf00`, `005f8ab0`; source `GameProcedure.cpp` | binary; source |
| **The line sits inside the bar's strip, so KO never shows both.** `Text_Rights` is a direct child of the login root: 601 × 25 (UIF rect 213, 307–814, 332), white Arial 12, vertically centred, "Copyright MGAME & Noahsystem all right reserved." At its place on a 1024 × 768 screen it is at (211, 723)–(812, 748); the bar's `login00` and `login01` strips are at y 713–766 there, 22–1000 across | the 1264 install's `UI_US/co_login_us.uif` | local-asset |

The realm's login is a Discord flow, not an ID and a password, so each of its
states takes the 1264 state it stands for (`content/front-end.md`, "Moradon"):

| Realm state | 1264's | Bar | Line |
|---|---|---|---|
| The login at rest: after the logo, a return from select, a dropped or kicked connection | the login loaded (Load) | shown | hidden |
| A login press held while the realm connection comes up | the press, after its connect | hidden | shown |
| A stored session's login, with no press | Init's auto-login (`005bea20`; never in 1264) | hidden | shown |
| The browser step (waiting for Discord) and its code sent to the realm | the press until the answer (Q85: KO's wait is one round trip, the realm's up to 5 minutes) | hidden | shown |
| A message box during that wait (the address to open when no browser starts) | none | hidden | shown |
| The login answered while a message box still shows | result 1, before the server list | hidden | shown |
| The realm list | the server list after result 1 | hidden | shown |
| A failed login (Discord denied, timed out, a callback or port failure, the realm's refusal, a ban), its box over the login | a failed answer: its box, SetVisibleLogInUIs(true) | shown | hidden |
| The realm unreachable after a press, its box over the login | the login server unreachable: its box over the line, OK quits (the realm's OK returns to the login, so it takes a failed answer's look) | shown | hidden |

**Decides (RQ-108):** the 1097 choice takes 1264's: the line is drawn only while
the login bar is not, at 1264's place, and the bar is hidden from a login press
until the answer. The engine's new action `login_closed` (`front-end.bin`
version 12) is a login node drawn only while the login group is not, which the
recipe binds to `Text_Rights`; its place is a move of the recipe's (`x`
`centre`, `bottom` 20). The MGAME and Daum logos stay hidden: 1264 never shows
them. Only a layout that binds `login_closed` hides its login group during a login;
the 1298 recipe (not offered) binds none, so it keeps the line where its layout
puts it, always drawn, and its bar up through a login, as before (1298's binary
was not read for it).
*RQ-110 (§9.5) read it: 1298's login has no line and hides its bar the same way, so
the 1298 recipe hides `Text_Rights` and every layout hides its login group during a
login.*

### 9.5 1298's login: no copyright line, its bar hidden while a login waits (RQ-110, 2026-11-02)

Read statically in n3e's 1298 `KnightOnLine.exe` (sha256 `828ab0db…`, Ghidra project
`build/ghidra/audit-2026-09-19`, `-readOnly -noanalysis`, `AuditReference.java`
`strings` and `decompile`; output under `build/ghidra/rq110/`, not committed), with
`objdump` for the login UI's Load, which Ghidra left undefined; the pinned tree's
login layouts through `ko_hud.parse` and `strings` (nothing committed from them).
Not run (Wine is approved for 1097 and 1264 only). The source agrees where named.

| Observation | Where | Label |
|---|---|---|
| **1298's login loads one layout, the nation's intro.** Init (`005f68e0`) makes the login UI (`0x698` bytes, constructor `00607ba0`), picks the nation by `rand() & 1` (`005f6aa3`–`005f6ab8`: 0 Karus, else El Morad), finds its `UIs_us.tbl` row (`004531c0`) and loads that row's string at `+0x754` (`005f6b20`–`005f6b2b`, LoadFromFile through `+0x8`): the 118th string, column 119, the source's `szLoginIntro` (`GameDef.h`), `UI_us\ka_login_intro_us.uif` or `UI_us\el_login_intro_us.uif`; it centres the root with unsigned shifts (`005f6b2e`–`005f6b71`). No other layout is loaded there, so `co_login_us.uif` (column 2, `szLogIn`) is not drawn at the login | 1298 `005f68e0`; source `GameProcLogIn_1298.cpp` `Init`; `Data/UIs_us.tbl` | binary; source; local-asset |
| **Its Load names the intro's nodes, not `co_login_us.uif`'s.** The login UI's Load (`00608030`) finds `Group_LogIn` (`+0xd0`) and in it `btn_homepage`, `Btn_Cancel`, `Btn_Option`, `btn_ok` (the login button), `Edit_ID` and `Edit_PW`; then `Group_ServerList_01` (`+0xd4`) with 20 `server_%d`/`img_arrow` entries, `List_Server` and `Btn_Connect`, hidden at once (`00608648`–`00608652`); then `Group_Notice_1`–`3`. `btn_ok`, `btn_homepage` and `Group_ServerList_01` are in both intro layouts and not in `co_login_us.uif` | `objdump` of `00608030`–`006089cc`; the pinned tree's `UI_US/` | binary; local-asset |
| **1298 draws no copyright line at its login.** Neither intro layout has a `Text_Rights` node or any copyright text; of the pinned tree's `UI_US/` layouts only `co_login_us.uif` (1264's, byte for byte) has the line. The image has no `Text_Rights` string (its only "Rights" strings are PKWARE's), so no 1298 code finds, hides or places such a node; `Img_MGame` and `Img_Daum` are not named either | strings of `KnightOnLine.exe`; the pinned tree's `UI_US/*.uif` | binary (strings); local-asset |
| **The bar hides from a login press until a failed answer, as 1264's.** The account login send (`005f74c0`, the source's `MsgSend_AccountLogIn`) connects (`005f6e20`), hides `Group_LogIn` (`005f75b3`–`005f75c4`, SetVisible(0) through `+0x3c`; the source's SetVisibleLogInUIs(false), which in 1298 touches only that group), sets the requested-login flags (`+0x680`, `+0x20`) and sends `0xf3` (`0xf4` for MGAME); the auto-login send (`005f7690`) does the same (`005f775c`–`005f776d`). The answer (`005f7b50`) on result 1 closes the message boxes (`00646c30(−1)`) and asks for the server list (`0xf5`), the bar left hidden; on any other result it posts the failure's box and shows the bar again (`005f82af`–`005f82c0`), clearing the flags. `005f9040`, case `0x23` of a dispatcher `00526d00` not read further, shows it again too and clears the flags. Init shows it (`005f6bb6`–`005f6bc7`) and, with the procedure's byte `+0x21` set (not read further), connects, asks for the server list and hides it (`005f6bca`–`005f6c05`) | 1298 `005f74c0`, `005f7690`, `005f7b50`, `005f9040`, `005f68e0`; source `GameProcLogIn_1298.cpp`, `UILogin_1298.cpp` `SetVisibleLogInUIs` | binary; source |

**Decides (RQ-110):** the 1298 recipe (not offered) cooks `co_login_us.uif`, which
1298 never draws, as its login until 1298's intro layout is data (RQ-088); it takes
1298's visibility for the line, none: `Text_Rights` is in the recipe's `hidden`, with
no move. The bar takes 1298's, which is 1264's: hidden from a login press until the
answer. The client's login rule no longer depends on a `login_closed` node
(`client/render/front_login.h`): every layout's login group is hidden while a login
is under way, so the 1298 recipe shows neither the bar nor a line then, as 1298 does
(Q86). No format change; the 1097 choice is unchanged.

### 9.6 1298's select bar (RQ-109, 2026-11-02)

Read statically in n3e's 1298 `KnightOnLine.exe` (sha256 `828ab0db…`, Ghidra project
`build/ghidra/audit-2026-09-19`, `-readOnly -noanalysis`, `AuditReference.java`
`decompile`; output under `build/ghidra/rq109/`, not committed), with `objdump` for the
select bar class's field uses and a PE reader for its vtable and strings; RQ-106's
decompile of the bar's Load (`build/ghidra/rq106/`) and RQ-066's and RQ-087's of the
select tick and ENTER; the pinned tree's `co_CharacterSelect_us.uif` through
`ko_hud.parse` and its `Data/Texts_us.tbl` through `ko_tbl` (nothing committed from
them). Not run (Wine is approved for 1097 and 1264 only). The source agrees where named.

| Observation | Where | Label |
|---|---|---|
| **The bar's layout.** `co_CharacterSelect_us.uif` is a 1024 × 113 root: three backdrop images (`ui_characterCreate_03_us.dxt`), the buttons `btn_create` "Create Character" (28, 57)–(178, 91), `btn_start` "Start" (233, 57), `btn_delete` "Delete Character" (435, 56), `btn_back` "Back" (645, 56), `btn_exit` "Exit" (846, 56), each 150 × 34 with its labels drawn in its state images (`ui_login_02_us.dxt`), the arrows `btn_left` (27, 23) and `btn_right` (958, 23), the labels "Level :", "I D :" and "Class :", and the empty strings `str_lev` (158, 24)–(184, 40), `str_id` (431, 23)–(629, 40) and `str_job` (760, 25)–(918, 41) | the pinned tree's `UI_US/co_CharacterSelect_us.uif` | local-asset |
| **Its Load finds ten nodes and places the root.** The vtable at `006a94c8` (Load `00606c10` at slot 3, ReceiveMessage `00607160` at slot 19) finds `btn_start` (`+0xb0`), `btn_create` (`+0xb4`), `btn_delete` (`+0xb8`), `btn_back` (`+0xbc`), `btn_exit` (`+0xc0`), `btn_right` (`+0xc4`), `btn_left` (`+0xc8`), `str_id` (`+0xcc`), `str_job` (`+0xd0`) and `str_lev` (`+0xd4`) by name, then puts the root at `((W − w) >> 1, H − 10 − h)` and the region the whole screen (`006070bd`–`0060710a`, §9.3) | 1298 `00606c10`; vtable `006a94c8`; strings `006d5afc`, `006d58fc`, `006d4fc8`, `006d671c`, `006d4fe8`, `006d564c`, `006d5658`, `006d8b2c`, `006d8b24`, `006d8b1c` | binary |
| **No code hides an arrow or any other one button.** The bar's arrow fields are written by its constructor, Release and Load and read only by ReceiveMessage's compares (`objdump` of `00606a90`–`00608100`); the select procedure touches the bar (`+0x384`) only whole: shown, hidden, ticked and rendered (`objdump` of `005f9000`–`00608200`). Both arrows stay drawn at the ends of the row, where DoJobLeft (`005fe3c0`) and DojobRight do nothing | 1298 `00606a90`–`00608100`, `005f9000`–`00608200` | binary |
| **ReceiveMessage: a click (message 1) on each button.** `btn_exit` posts a box of row 1502 ("Are you sure you want to exit? ") untitled, style 4 and behaviour 1 (the source's `MB_YESNO`, `BEHAVIOR_EXIT`); `btn_delete`, for a slot 0–2 holding a character with the select at rest (`+0x394` 5), posts row 1501 ("Character deletion has been disabled currently") untitled, style 0; `btn_back` calls `004512f0` on `00818984`, activates the login procedure (`00646b50(008189a8)`) and sets its byte `+0x21`, which makes its Init connect, ask for the server list and hide the bar (§9.5), so Back returns to the server list; `btn_start` calls `005ff870`, `btn_create` `005ff920`, `btn_right` DojobRight (`005fe450`) and `btn_left` DoJobLeft (`005fe3c0`), each on the select procedure (`008189b4`). Nothing runs unless the UI flag `00818994 + 0xb4` is set | 1298 `00607160`; source `UICharacterSelect.cpp` `ReceiveMessage` (exit and delete the same) | binary; source |
| **Start is the centre click.** `005ff870` closes the message boxes (`00646c30(−1)`); for an empty slot in focus (`00818a20`) it sets the select state 6, hides the bar and shows the in-select create UI (`+0x388`); otherwise it sets the main procedure's zone fields and the character's name and calls the procedure's `+0x18`, the same body as the select tick's left click in the centre rect (`005faf10`, §8), without that click's state-5 test (the bar is hidden while the camera moves) | 1298 `005ff870`, `005faf10` | binary |
| **Create takes the slot in focus, or the first empty one, or says none.** `005ff920` closes the boxes; for an empty slot in focus it opens create as Start does; otherwise it takes the first of slots 0–2 that is empty as the focus (`00818a20`, `+0x390`), flies the camera there by the path from the current slot (`005fa670`: 2–7, `ka_left_right` and `ka_right_left` among them), sets state 6, hides the bar and shows create; with every slot taken it posts row 7675 ("Cannot create additional characters.") untitled | 1298 `005ff920`; the pinned tree's `Data/Texts_us.tbl` rows 7675, 1501, 1502 | binary; local-asset |
| **The info texts.** `006074c0`, from the front-clip tick at rest (`005fef90`) with the slot in focus, sets `str_id`, `str_job` and `str_lev` to the empty string (`006dfe28`, in the zero-filled tail of the data section) for an empty slot; otherwise `str_id` to the character's name, `str_job` to its class's text (`00613ea0`: a class code's row, the priest's 1417 "Priest"; *corrected by RQ-005, §8.5: rows 1304–1315 are its cases 1–12, KO's class kinds, not a character's class*) and `str_lev` to its level by `"%d"` (`006d3a54`) | 1298 `006074c0`, `00613ea0`, `005fef90` | binary |

**Decides (RQ-109):** the 1298 recipe (not offered) cooks 1298's own select,
`co_CharacterSelect_us.uif`, in place of the pinned tree's `ka_characterselect_us.uif`
(1264's), with 1298's placement (`place` `{"bottom": 10}`) and every node drawn. N3FE
version 13 adds the select actions `select_start`, `select_create`, `select_delete`
and the info texts `char_name`, `char_level`, `char_class` (a select binds `char_info`
or any of them), and the messages `create_full` and `delete_disabled`, which the
recipe words with rows 7675 and 1501. Start is the realm's centre click; Create opens
the realm's create screen for the slot 1298 picks, the camera put on that slot rather
than flown there (the realm's create is a screen of its own); Delete shows row 1501
for a character at rest. Not 1298's (Q87): Exit leaves at once, with no yes/no box
(the realm's message box has one button); Back returns to the login, not the server
list; the arrows hide at the ends of the row, as every realm select's do. The 1097
choice changes by the version word only. *RQ-111 (§9.7): Exit now asks, as 1298's
does.* *RQ-112 (§9.12): Back now lands on the realm list, the bar hidden from the
click, as 1298's does.* *RQ-113 (§9.13): both arrows now draw at the ends of the row, as
1298's do (`select.arrows` `draw`).*

### 9.7 1298's message box and its Exit question (RQ-111, 2026-11-02)

Read statically in n3e's 1298 `KnightOnLine.exe` (sha256 `828ab0db…`, Ghidra project
`build/ghidra/audit-2026-09-19`, `-readOnly -noanalysis`, `AuditReference.java`
`decompile`; output under `build/ghidra/rq111/`, not committed), with `objdump` for
the two functions the project has not marked (the box's Load and OnKeyPress) and a
PE reader for the box's vtable and strings; the pinned tree's
`UI_US/el_messagebox_us.uif` through `ko_hud.parse` and its `Data/UIs_us.tbl`
through `ko_tbl` (nothing committed from them). Not run (Wine is approved for 1097
and 1264 only). The source agrees where named.

| Observation | Where | Label |
|---|---|---|
| **The select's Exit posts a yes/no box.** ReceiveMessage's `btn_exit` branch (§9.6) calls `00646ba0` (the source's `CGameProcedure::MessageBoxPost`) with row 1502's text, an empty title, style 4 and behaviour 1; `00646ba0` passes all five to the box manager's `005282a0` | 1298 `00607160`, `00646ba0` | binary |
| **The manager loads El_MessageBox_us.uif and centres it.** `005282a0` looks the text up among its boxes (`005293b0`); for a new one it makes a box (`005267d0`, vtable `006a6710`) and loads row 2's column 26 (`+0x194` of the table's row-2 node) of the client's `Data\UIs_us.tbl`: in the pinned tree, row 2 column 26 is `UI_us\El_MessageBox_us.uif` (row 1's `Ka_MessageBox_us.uif`), for either nation. It then sets the style (`00527a40`), shows the edit only for behaviour 10 (`00527b00`), keeps the behaviour at `+0xd0`, sets the text and title (`00526cc0`, `00526ce0`), moves the box to `((W − w) >> 1, (H − h) >> 1)` and shows it | 1298 `005282a0`; the pinned tree's `Data/UIs_us.tbl` | binary; local-asset |
| **Its Load finds seven nodes.** `Btn_OK` (`+0xb0`), `Btn_Yes` (`+0xb4`), `Btn_No` (`+0xb8`), `Btn_Cancel` (`+0xbc`), `Text_Message` (`+0xc0`), `Text_Title` (`+0xc4`) and `Edit_Common` (`+0xc8`), by name (vtable slot 3) | 1298 `005268c0` (objdump); strings `006d5ba4`, `006d63f8`, `006d63f0`, `006d586c`, `006d4cac`, `006d4f44`, `006d63e4` | binary |
| **SetBoxStyle shows Yes and No for style 4.** `00527a40` hides all four buttons, keeps the style at `+0xd4`, then shows `Btn_Yes` and `Btn_No` for 4 (`MB_YESNO`), `Btn_Cancel` for 6 (`MB_CANCEL`) and `Btn_OK` otherwise | 1298 `00527a40`; source `UIMessageBox.cpp` `SetBoxStyle` | binary; source |
| **Yes on BEHAVIOR_EXIT quits; No closes.** ReceiveMessage (`00526d00`, vtable slot 19), on a click: for `Btn_OK` or `Btn_Yes` it calls the parent's callback with 1, then by behaviour; behaviour 1 releases the sound (`00670b70`, `00670c00`, and `005dd790` when the main procedure is active) and calls `PostQuitMessage(0)`. For `Btn_No` or `Btn_Cancel` it calls the callback with 2, hides the box and empties its text and title, then by behaviour (no case for 1). Either way it hides the edit and resets the behaviour to 0 | 1298 `00526d00`; source `UIMessageBox.cpp` `ReceiveMessage` | binary; source |
| **ENTER is Yes, ESC is No.** OnKeyPress (`00527c60`, vtable slot 24), with the box shown: in a style-4 box `DIK_ESCAPE` (1) presses `Btn_No` and `DIK_RETURN` (`0x1c`) or `DIK_NUMPADENTER` (`0x9c`) presses `Btn_Yes`; in a style-6 box any of the three presses `Btn_Cancel`; in a style-0 box, unless the behaviour is 3, any of the three presses `Btn_OK` | 1298 `00527c60` (objdump); source `UIMessageBox.cpp` `OnKeyPress` | binary; source |
| **The box's Yes and No are labelled OK and Cancel.** The pinned tree's `el_messagebox_us.uif` (`8f7773d5…`, the 1264 install's byte for byte, §9.1) puts `btn_yes` at (9, 116)–(106, 145), each state image labelled `O  K`, and `btn_no` at (220, 116)–(317, 145), labelled `Cancel`; `btn_ok` and `btn_cancel` share the centre, (115, 116)–(212, 145); `Text_title` (12, 10)–(309, 24) holds "111" in the file; `Text_Message` (21, 28)–(304, 86). Its texture is the pinned tree's `ui_message_us.dxt` (the grey frame, §9.2) | the pinned tree's `UI_US/el_messagebox_us.uif` | local-asset |
| Row 1502 of the pinned tree's `Data/Texts_us.tbl` is "Are you sure you want to exit? " | the pinned tree's `Data/Texts_us.tbl` | local-asset |
| 1298's login Cancel quits at once, without a box (`PostQuitMessage(0)`); only its Option asks yes or no (`BEHAVIOR_EXECUTE_OPTION`). Not read in the binary | source `UILogin_1298.cpp` `ReceiveMessage` | source |

**Decides (RQ-111):** N3FE version 14 adds the message box's actions `yes` and
`no` (message screen only) and the message `exit_confirm`, the engine's one
yes/no question. A package that names `exit_confirm` makes the select's `exit`
ask in the message box instead of leaving: the box shows the nodes bound to `yes`
and `no` and hides the one bound to `ok` (an OK box the reverse), ENTER and the
keypad's ENTER press Yes, ESC presses No, and Yes leaves the game while No only
closes the box. The cook and the loader refuse `exit_confirm` without both
buttons bound. The 1298 recipe (not offered) now draws 1298's box,
`UI_US/el_messagebox_us.uif` of the pinned tree, for every message (it drew
`co_MsgBoxOk_us.uif`, which 1298's MessageBoxPost never loads), binds its Yes and
No, hides `Edit_Common` and `btn_cancel`, binds `Text_title` to `title`, and words
`exit_confirm` with row 1502, untitled, as 00607160 posts it. The login's Cancel
still leaves at once (1298's does, by the source). The 1097 choice names no
`exit_confirm`: its exit leaves at once, and it changes by the version word only.
*RQ-115 (§9.8): 1264's select asks the same, so the 1097 choice now names it.*

### 9.8 1264's select Exit asks yes or no (RQ-115, 2026-11-02)

Read statically in §9.1's 1264 image (`ko1264-unpacked.exe`, sha256 `61e9a086…99e136471`,
Ghidra project `build/ghidra/rq096`, `-readOnly -noanalysis`, `AuditReference.java`
`recover` and `decompile`; the functions the project has not marked recovered in
memory only; output under `build/ghidra/rq115/`, not committed), with a PE reader for
the two classes' vtables and strings; the 1264 install's `Data/Texts_us.tbl` through
`ko_tbl` and its `UI_US/el_messagebox_us.uif` as §9.2 read it (nothing committed from
them). Not run: the static reading answers it. The source agrees where named.

| Observation | Where | Label |
|---|---|---|
| **The select's handlers.** CUICharacterSelect's vtable is at `00648f14` (Load `004448f0` at slot 3, §9.3; ReceiveMessage `00444e60` at slot 19; OnKeyPress `004454e0` at slot 24). Load keeps `bt_left` at `+0xb0`, `bt_right` `+0xb4`, `bt_exit` `+0xb8`, `bt_delete` `+0xbc` and `bt_back` `+0xc0` (strings `0066a840`, `0066a834`, `0066a82c`, `0066a820`, `0066a818`) | 1264 vtable `00648f14`, `004448f0` | binary |
| **Exit posts a yes/no box of row 1502, untitled.** ReceiveMessage, on a click (message 1) and with the UI flag `007ad09c + 0xb4` set: `bt_exit` looks up row `0x5de` (1502, `005d2350`), makes an empty title (`00674f68`) and calls MessageBoxPost (`005f7f80`) with style 4 and behaviour 1, the source's `MB_YESNO` and `BEHAVIOR_EXIT`. `bt_left` and `bt_right` call `00442e60` and `00442ed0` (DoJobLeft, DojobRight); `bt_back` calls `00438010`, then `005f7f30` with the procedure `007ad0b0`, and sets that procedure's byte `+0x35` (the source's Disconnect and ProcActiveSet(s_pProcLogIn); the flag, read in §9.12, makes the login's Init ask for the server list) | 1264 `00444e60`; source `UICharacterSelect.cpp` `ReceiveMessage` | binary; source |
| **It is the box every message uses, as 1298's.** MessageBoxPost passes (text, title, style, behaviour) to the manager (`0050c730`, §9.2), which loads `El_MessageBox_us.uif` (row 2, column 26) and centres it, keeps the behaviour at `+0xd0` and calls SetBoxStyle (`0050bfb0`): it hides `Btn_OK` (`+0xb0`), `Btn_Yes` (`+0xb4`), `Btn_No` (`+0xb8`) and `Btn_Cancel` (`+0xbc`), keeps the style at `+0xd4`, then shows Yes and No for 4, Cancel for 6 and OK otherwise. The box's Load (`0050b0e0`, vtable `0064b49c` slot 3) finds those four and `Text_Message`, `Text_Title`, `Edit_Common` by name | 1264 `0050c730`, `0050bfb0`, `0050b0e0`; strings `0066bf5c`, `0066c7f4`, `0066c7ec`, `0066b9bc`, `0066b988`, `0066b504`, `0066c7e0` | binary |
| **Yes on BEHAVIOR_EXIT quits; No closes.** The box's ReceiveMessage (`0050b510`, slot 19), on a click: `Btn_OK` or `Btn_Yes` calls the parent's callback with 1, then by behaviour; behaviour 1 calls `005aacd0` when the main procedure is the active one and `PostQuitMessage(0)`. `Btn_No` or `Btn_Cancel` calls the callback with 2, hides the box and empties its texts, then by behaviour (no case for 1). Either way it then hides the box, empties `Text_Message` and `Text_Title`, empties and hides the edit and resets the behaviour to 0 | 1264 `0050b510`; source `UIMessageBox.cpp` `ReceiveMessage` | binary; source |
| **ENTER is Yes, ESC is No.** The box's OnKeyPress (`0050c1d0`, slot 24), with the box shown: in a style-4 box `DIK_ESCAPE` presses `Btn_No` and `DIK_RETURN` or `DIK_NUMPADENTER` presses `Btn_Yes`; in a style-6 box any of the three presses `Btn_Cancel`; in a style-0 box, unless the behaviour is 3, `Btn_OK`. The same as 1298's `00527c60` | 1264 `0050c1d0` | binary |
| Row 1502 of the 1264 install's `Data/Texts_us.tbl` is "Are you sure you want to exit? ", as the pinned tree's is. The box is 1264's `el_messagebox_us.uif` (§9.2), whose `btn_yes` and `btn_no` state images are labelled `O  K` and `Cancel` (§9.7) | the 1264 install's `Data/Texts_us.tbl`, `UI_US/el_messagebox_us.uif` | local-asset |
| **The select's keys.** OnKeyPress (`004454e0`, slot 24), only with the UI flag `007ad09c + 0xb4` set (the one ReceiveMessage tests): `DIK_ESCAPE` (1) calls the select's own ReceiveMessage (vtable `+0x4c`, slot 19) with `bt_exit` (`+0xb8`) and message 1, a click, so ESC asks the same question as the Exit button; `DIK_LEFT` (`0xcb`) does the same with `bt_left` (`+0xb0`) and `DIK_RIGHT` (`0xcd`) with `bt_right` (`+0xb4`); `DIK_RETURN` (`0x1c`) and `DIK_NUMPADENTER` (`0x9c`) call `00444520` (the source's CharacterSelectOrCreate, not read); each returns 1, any other key 0. *RQ-116 takes the ESC (below)* | 1264 `004454e0` (Ghidra `decompile`, output under `build/ghidra/rq115/`) | binary |
| **Not taken here: Delete.** `bt_delete`, for a slot 0–2 holding a character, posts row 1501 (the 1264 install's "You'll need to enter your ID number in order to erase your character. …") with style 4 and behaviour 10, which shows the edit (`0050c070`); Yes passes the edit's text to `00442f40`. The realm hides Delete (Q53) | 1264 `004454e0`, `00444e60`, `0050b510`; the 1264 install's `Data/Texts_us.tbl` | binary; local-asset |

**Decides (RQ-115):** the 1097 choice's select Exit asks, as 1264's does: its recipe
binds 1264's `el_messagebox_us.uif`'s `btn_yes` to `yes` and `btn_no` to `no` (no
longer hidden; `Edit_Common` and `btn_cancel` stay hidden) and words `exit_confirm`
with the 1264 install's row 1502, untitled, as `00444e60` posts it. The client and
the format already carry it (N3FE version 14, §9.7): Yes ("O  K") or ENTER leaves,
No ("Cancel") or ESC closes the box, and every other message is still an OK box.
1264's ESC on the select, which asks too, and its Delete question stay as they were
(proposed as their own items).
*RQ-116 (below): the 1097 choice's ESC on the select now asks too.*

**Decides (RQ-116, the maintainer, 2026-11-02: "Ask to exit, as 1264"):** N3FE
version 15 carries what ESC presses on the select at rest, `back` (the realm's, the
default) or `exit`, as a click on it (the recipe's `select.escape`). The 1097
recipe names `exit`, so ESC on its select asks row 1502 yes or no as its Exit button
does, 1264's OnKeyPress pressing `bt_exit`; its Back stays on `bt_back`. The 1298
recipe keeps `back` (1298's select key handling was not read). ESC while a path
plays (the path mode) still skips it. Not run: the static reading answers it.
*RQ-117 (§9.9): 1298's ESC presses neither Exit nor Back; the 1298 recipe keeps
`back` as a known difference. The realm's select ESC is not only "at rest": it
presses `back` or `exit` in every select state but a playing path's (§9.9).*
*RQ-119 (§9.9): the 1298 recipe now names `none` (N3FE version 16).*

### 9.9 1298's select keys (RQ-117, 2026-11-02)

Read statically in n3e's 1298 `KnightOnLine.exe` (sha256 `828ab0db…43a5e5`, Ghidra
project `build/ghidra/audit-2026-09-19`, `-readOnly -noanalysis`, `AuditReference.java`
`recover` and `decompile`; the functions the project has not marked recovered in
memory only; output under `build/ghidra/rq117/`, not committed), with a PE reader for
the bar's vtable and OnKeyPress's jump tables; §9.6's reading of the bar and §8.4's
of the select tick. Not run (Wine is approved for 1097 and 1264 only): the static
reading answers it. The source differs where named.

| Observation | Where | Label |
|---|---|---|
| **The bar's OnKeyPress is `00607810`**, slot 24 (`+0x60`) of its vtable `006a94c8` (slot 19 ReceiveMessage `00607160`, §9.6), as the message box's OnKeyPress is its slot 24 (§9.7) | 1298 vtable `006a94c8` | binary |
| **ESC skips, it presses no button.** With the UI flag `00818994 + 0xb4` set (the one ReceiveMessage tests), OnKeyPress switches on the key through the byte table `00607898` (key − 1, up to `0xcc`) and the jump table `00607884`: `DIK_ESCAPE` (1) calls `005faad0` on the select procedure (`008189b4`); `DIK_RETURN` (`0x1c`) and `DIK_NUMPADENTER` (`0x9c`) call its own ReceiveMessage (vtable `+0x4c`) with `btn_start` (`+0xb0`) and message 1, a click on Start (`005ff870`, §9.6); `DIK_LEFT` (`0xcb`) calls DoJobLeft (`005fe3c0`) and `DIK_RIGHT` (`0xcd`) DojobRight (`005fe450`) directly; each returns 1, any other key (or the flag clear) 0. No key presses `btn_exit` or `btn_back` | 1298 `00607810` (its jump tables decoded from the image) | binary |
| **`005faad0` is the tick's ESC body.** Unless the select state (`+0x394`) is 6 or 7 (the in-select create), it puts the camera's frame (`+0x1a4`'s `+0x110`) on its last (`+0x10c`), the slot (`+0x38c`) on the destination (`+0x390`), the state on 5 and shows the bar (`+0x384`'s vtable `+0x3c` with 1) when it is hidden (its `+0xa0` byte 0). OnKeyPress is its only caller. The select tick (`005faf10`) runs the same body inline for the input's `+0x270` (ESC, §8.4) when `00648ce0` returns 0: both bytes `00818a26` and `00818a27` clear, the source's `s_bKeyPress` and `s_bKeyPressed` (a UI took no key this frame, `IsUIKeyOperated`) | 1298 `005faad0`, `005faf10`, `00648ce0`; source `GameProcedure.h` | binary; source |
| So ESC on 1298's select skips a playing path (§8.4) and at rest (state 5, the frame already on the last, the slot on the destination, the bar shown) changes nothing; it asks no question and does not return to the server list. With the exit box shown the box takes the keys first (its ESC is No, §9.7; the source's `ProcessUIKeyInput` gives the message box precedence over the focused UI) | `005faad0`; source `GameProcedure.cpp` `ProcessUIKeyInput` | binary; source |
| The later source's `CUICharacterSelect::OnKeyPress` presses `m_pBtnExit` for ESC and `m_pBtnLeft`, `m_pBtnRight` for the arrows, and calls `CharacterSelectOrCreate` for ENTER: 1264's (`004454e0`, §9.8), not 1298's | source `UICharacterSelect.cpp` `OnKeyPress` | source |

**Decides (RQ-117):** 1298's select ESC presses neither Exit nor Back: it only puts
the select at rest, skipping a path, and at rest does nothing. The 1298 recipe (not
offered) keeps `select.escape` `back`, a known difference from 1298 (Q87): N3FE
version 15 has no value for "nothing at rest", and which the realm owner wants is a
look-and-feel choice for the maintainer (proposed as its own item). Its ENTER (Start,
the realm's primary) and arrows (a turn) already match. The realm's select ESC
(`client/render/front_end.h` `escape`) presses `back` or `exit` in every select state
but while a path plays in the path mode, which it skips: in the rotate mode also while
the camera turns, and in both modes while the start clip plays, where `back` does
nothing (the realm's back needs no character chosen) and `exit` asks. The later
source disables the select's UI as a character is chosen
(`GameProcCharacterSelect.cpp`: `MsgSend_CharacterSelect` and `CharacterSelect`,
`EnableOperationSet(false)`), which would make KO's select OnKeyPress, and so its ESC,
do nothing then; 1264's binary was not read for it (proposed as its own item).

**Decides (RQ-119, the maintainer, 2026-11-02: "Do nothing, as 1298"):** N3FE version
16 adds a third `select.escape` value, `none`: ESC on the select presses nothing, so it
only skips a playing path in the path mode, as the realm's ESC does whatever the value
(`front_end.h`'s key handler), and otherwise does nothing, as 1298's `005faad0` does at
rest. The 1298 recipe names it; Back and Exit stay on their buttons. While the start
clip plays it does nothing too, as the realm's `back` does then. No new reading: §9.9's
static reading of the 1298 binary is its evidence (not run; Wine is approved for 1097
and 1264 only).
*RQ-120 (§9.10): 1264's binary clears the flag as §9.9 supposed, and 1097's too: from
the select request until the main procedure, neither select takes ESC, the arrows or
a button. RQ-121 (the maintainer, 2026-11-03) makes the realm's ESC and Exit do
nothing then too, so the 1097 choice's `exit` asks only at rest or while the camera
turns.*

### 9.10 1264's select takes no input once a character is chosen (RQ-120, 2026-11-03)

Read statically in §9.1's 1264 image (`ko1264-unpacked.exe`, sha256
`61e9a086…99e136471`, Ghidra project `build/ghidra/rq096`, `-readOnly -noanalysis`,
`AuditReference.java` `recover` and `decompile`; the functions the project has not
marked recovered in memory only; output under `build/ghidra/rq120/`, not committed),
with `objdump` for the flag's writers and a PE reader for the select procedure's
vtable; and in §8.1's 1097 dump (`ko1097-unpacked.exe`, sha256 `82abb582…ea8febaf`)
with `objdump` alone. Not run (no Wine): the static reading answers it. The source
agrees where named.

| Observation | Where | Label |
|---|---|---|
| **The UI flag is the UI manager's operation switch.** `007ad09c` is the UI manager (the source's `s_pUIMgr`), and its byte `+0xb4`, which the select's OnKeyPress (`004454e0`) and ReceiveMessage (`00444e60`) test (§9.8) and the select tick (`00440120`) tests with `+0xbc` before it takes the centre click, is the source's `m_bEnableOperation` (`EnableOperation()`, `EnableOperationSet()`), which the source's `CUICharacterSelect::OnKeyPress` and `ReceiveMessage` test | 1264 `004454e0`, `00444e60`, `00440120`; source `UIManager.h`, `UICharacterSelect.cpp` | binary; source |
| **Its writers.** Every byte store to `+0xb4` within six instructions of a load of `007ad09c`: the select's Init (`0043f530`, slot 7 of its vtable `00648e84`; 0, after creating sound 2501 at `0043f5d4`), the all-character answer in its ProcessPacket (`004443f0`, slot 2; 1, for `0x0c` after `00444060`), MsgSend_CharacterSelect (`004443d0`, slot 6; 0), CharacterSelect (`00443570`; 0), CharacterSelectFailed (`004436a0`; 1), create's send (`0043a340`; 0) and answer (`0043aa10`), a send at `005bb730` (0; the source's nation select, not read further) and ProcActiveSet (`005f7f30`; 1). They are the source's `EnableOperationSet` calls one for one | 1264 `0043a7f6`, `0043aaa7`, `0043aab3`, `0043f5eb`, `00443654`–`0044368e`, `004437c2`, `004443da`, `0044445d`, `005bb756`, `005f7f4a`; source `GameProcCharacterSelect.cpp`, `GameProcCharacterCreate.cpp`, `GameProcNationSelect.cpp`, `GameProcedure.cpp` | binary; source |
| **ENTER clears it as it sends.** CharacterSelectOrCreate (`00444520`, ENTER from OnKeyPress; the tick runs the same body inline for the centre click) closes any box (`005f7fe0(-1)`), activates create for an empty slot (`005f7f30(007ad0b8)`), else fills the request and calls the procedure's slot 6, `004443d0`: the base's send (`005f90d0`), then the flag 0. The source's `MsgSend_CharacterSelect` (`EnableOperationSet(false)`) | 1264 `00444520`, `004443d0`, `00440120`; vtable `00648e84` | binary; source |
| **The answer keeps it clear and starts the clip.** The select answer (slot 5, `00442690`: the base's `005f9440`) calls CharacterSelect (`00443570`) on success: from state 2 with a character in the slot it sets state 3, clip 1 with 0.6 s (`0x3f19999a`, as 1097's `0043ea30`) and the spot; on every path it sets `+0x2d9` (the source's `m_bReceivedCharacterSelect`) and the flag 0. On failure `004436a0` posts a box (`005f7f80`) and sets the flag 1 | 1264 `00442690`, `00443570`, `004436a0` | binary |
| **Nothing sets it again in the select.** State 3's tick (`00443810`, from `00443020`) plays the clip until its loop count (`+0x1e0` or `+0x208`) reaches 1, then releases the BGM (`004347a0(007ad084)`) and activates the main procedure (`005f7f30(007ad0c0)`); ProcActiveSet sets the flag 1 and calls `0050cba0` (the source's `MessageBoxClose(-1)`, not read) as it changes the procedure | 1264 `00443810`, `00443020`, `005f7f30` | binary |
| **So no select input reaches it meanwhile.** The key pass (`005f97a0`, the procedure's slot 10, called by the base tick `005f7990` with 1) gives a shown box the keys first and otherwise the focused UI (the manager's `+0xb8`), each through OnKeyPress (vtable `+0x60`), over the input's key-press words from `+0x26c` (so ESC's is `+0x270`, as in 1298, §9.9); nothing else takes a key it leaves. With the flag clear the select's OnKeyPress returns 0 for every key and its ReceiveMessage does nothing, so from the request until the main procedure ESC asks nothing, the arrows turn nothing, Exit, Back, Delete and the arrow buttons do nothing and the centre click is not taken | 1264 `005f97a0`, `005f7990`, `004454e0`, `00444e60` | binary |
| **The one key that works then is the tick's ENTER.** After the key pass, with no UI key taken (`005f9a10`: `007ad12e` and `007ad12f` clear) and the input's `+0x2dc` (ENTER) pressed, the tick calls `004426d0` (the source's ProcessOnReturn), which once the answer has come (`+0x2d9`) and outside a turn (state not 1) releases the BGM and goes to the main procedure with "Loading data...": a second ENTER skips the clip, as 1097's `0043db70` does (§8.1) | 1264 `00440120`, `005f9a10`, `004426d0`; source `GameProcCharacterSelect.cpp` `Tick` | binary; source |
| **1097 is the same.** Its UI manager's flag is `006e0474 + 0xac`: the select's key handler (`00440690`) and message handler (`0043ff00`, `0043ff37`–`0043ff43`) return 0 with it clear; its CharacterSelect (`0043ea30`) clears it on each of its three paths after setting `+0x2d9` (`0043eb1c`, `0043eb35`, `0043eb4d`), its send (`0043f7d0`) after calling the base's (`00546b30`), as 1264's do; its failure sets it (`0043eccd`) and ProcActiveSet (`00545afa`). Its key handler's table (`0044070c`, bytes from `00440720`) sends ESC to a click on its child `+0xb0` (not named here), ENTER and keypad ENTER to `0043f860`, LEFT to `+0xa8` and RIGHT to `+0xac`. So 1097's arrows cannot start a turn while the start clip plays: DoJobLeft and DojobRight would (§8.2), but their only direct callers (`0043ff77`, `0043ff8f`; 1264's `00442e60` and `00442ed0` likewise only `00444ed7`, `00444eef`) are the message handlers, which the flag stops | 1097 `00440690`, `0043ff00`, `0043ea30`, `0043f7d0`, `0043eccd`, `00545afa`; `objdump` of both images | binary |
| **1298 is the same (RQ-121).** Read with `objdump` and a PE reader in §9.9's 1298 image (output under `build/rq121/`, not committed): the byte stores to `00818994 + 0xb4` after a load of `00818994` include the select procedure's slot 6 (`005ff690`, vtable `006a93c8`, whose slot 2 is its ProcessPacket `005ff6b0` and slot 10 the tick `005faf10`): the base's send (`00648240`), then 0; it is what `btn_start` (`005ff870`, §9.6) calls for an occupied slot. Its CharacterSelect (`005fe7c0`, called by the answer, slot 5 `005fe240`, on success): from state 5 with a character, state 4 and clip 1 with 0.6 s (`0x3f19999a`); on each of its three paths `+0x3a1` set (`005fe8a4`, `005fe8ba`, `005fe8d0`), then the flag 0. The failure (`005fe8f0`) sets it (`005fea1b`), as ProcActiveSet (`00646b50`, `00646b6a`) does; two other ProcessPacket cases (`005ff71d`, `005ff7ad`) were not read. So with the flag clear the bar's ReceiveMessage (`00607160`, §9.6) and OnKeyPress (`00607810`, §9.9) take nothing while the start clip plays | 1298 `005ff690`, `005ff870`, `005fe240`, `005fe7c0`, `005fea1b`, `00646b50`; vtable `006a93c8` | binary |

**The realm (`client/render/front_end.h`).** The realm starts the clip on the press
(Q72), so its start clip spans KO's request, answer and clip. While it plays
(`choosing` set) the arrows, Create, Back and a second start already did nothing, as
KO's. Until RQ-121, ESC (`escape()`) and a click on Exit (`act(FrontAction::exit)`)
did not check it: with the 1097 choice's `select.escape` `exit` and its
`exit_confirm`, either asked row 1502 then, and Yes quit during world entry; with the
1298 recipe's `none` ESC did nothing but its bar's Exit still asked. RQ-121 makes both
do nothing while it plays, whatever the package names.

**Decides (RQ-120):** 1264 (and 1097) take no select input from the select request
until the main procedure: ESC, the arrows and every select button do nothing while
the start clip plays, which the later source's `EnableOperationSet(false)` in
`MsgSend_CharacterSelect` and `CharacterSelect` says too. The realm's ESC and Exit
asking then is a known difference, unchanged here: making them do nothing is a
look-and-feel change to the offered front end, proposed as its own item for the
maintainer. The 1097 reading also qualifies §8.2's arrows from state 3. The tick's
second-ENTER skip (Q72, option (b)) stays as Q72 decided.

**Decides (RQ-121, the maintainer, 2026-11-03: "Match KO: ignore them"):** while the
start clip plays the realm's select ESC and a click on its Exit do nothing, whatever
the package's `select.escape` and `exit_confirm` say, as 1264's, 1097's and (the row
above) 1298's select take no input then; no package data changes. The realm's ENTER
does not skip the clip (Q72's start on the press, at rest only, unchanged).

### 9.11 ESC on 1264's loading screen does nothing (RQ-122, 2026-11-03)

Read statically in §9.1's 1264 image (`ko1264-unpacked.exe`, as §9.10; Ghidra project
`build/ghidra/rq096`, `-readOnly -noanalysis`, `AuditReference.java` `recover`, the
functions in memory only; output under `build/ghidra/rq122/`, not committed), with
`objdump` for the main loop, the procedure change and the main procedure's load flag,
a PE reader for its vtable and the image's import slots (`build/rq-1264/ko1264-imports.json`).
Not run (no Wine): the static reading answers it. The source agrees where named,
except where a row says otherwise.

| Observation | Where | Label |
|---|---|---|
| **The procedure change waits a frame.** ProcActiveSet (`005f7f30`), which the select's state-3 tick calls when the start clip has played (`00443810`, §9.10) and ProcessOnReturn after the second ENTER (`004426d0`, which then draws "Loading data..." through `005f7d50`), sets the UI flag (`007ad09c + 0xb4`) 1, closes any box (`0050cba0`), keeps the select as the previous procedure (`007ad0a8`) and makes the main procedure (`007ad0c0`) active (`007ad0ac`); it calls no Init | 1264 `005f7f30`, `00443810`, `004426d0` | binary |
| **The main procedure's Init runs inside a tick, with no message pump.** The game loop (`0060253e`–`00602572`) takes a window message with PeekMessageA (slot `006482c4`, `PM_REMOVE`), translating and dispatching it, and otherwise calls TickActive (`005f7cf0`) and RenderActive (`005f7d30`), until `WM_QUIT`; PeekMessageA and DispatchMessageA are named nowhere else in the image. TickActive, with the active procedure not the previous one, calls the previous one's slot 0 (Release), the active one's slot 7 (Init) and makes it the previous one, then calls its slot 8 (Tick); RenderActive calls slot 9 (Render) only when the two are the same | 1264 `00602564`, `005f7cf0`, `005f7d30`; `ko1264-imports.json` | binary |
| **That Init draws the loading screen as it loads.** The main procedure's vtable (`0064d1d0`, stored by its constructor `00590b60` at `00590d22`): slot 2 ProcessPacket `00593f40`, 7 Init `005929b0`, 8 Tick `00592db0`, 9 Render `00593a30`, 10 the key pass `005b1010`. Init loads the UI (`005a0270`), the zone (`005a3580`, which clears the load flag `+0x184` and draws the loading UI `007ad0a0` through `005f7d50`) and the characters (`005b21e0`: "Loading Character Data..." to "... 100 %", through `005f7d50`), then sends `0x0d` (the source's `WIZ_GAMESTART`) and returns. While it runs no key, click or window message is handled, and the keyboard is read as a state (the input tick `005fd7f0`: GetActiveWindow, the device's GetDeviceState for 256 keys, Acquire on failure; the source's `CLocalInput::Tick` takes a press as a key down now and up on the last tick), so an ESC pressed and released during the load is never seen | 1264 `00590b60`, `005929b0`, `005a3580`, `005b21e0`, `005f7d50`, `005fd7f0`; source `LocalInput.cpp` | binary; source (the press edge) |
| **After Init, until the server answers, the screen stays as the load left it.** The load flag `+0x184` is set only by ProcessPacket's `0x0d` case (`0059451e`: `005a3b30(0)` sends `0x0d` again, then the flag 1) and by one of `0x27`'s (`005948d4`); the constructor (`00590d34`), the Release (`005926e1`), the zone load and another `0x27` case (`00594866`) clear it. Render returns at once with it clear, so the last loading frame stays shown. Tick runs the base tick (`005f7990`: the input tick, the key pass with 1, the UI manager's mouse pass) and returns with it clear, before any of the main procedure's own input | 1264 `00593f40`, `005a3b30`, `00593a30`, `00592db0`, `005f7990` | binary |
| **ESC then reaches only a focused UI.** The key pass (`005b1010`), with the chat window (`+0x40`) out of chat mode (`005240e0`), runs the base pass (`005f97a0(1)`, §9.10): a shown box takes the keys, else the UI manager's focused, visible UI (`+0xb8`) through OnKeyPress; then an ENTER no UI took focuses the chat (`00523ea0`). ProcActiveSet has closed every box, and the main procedure's HUD windows, in the source, take ESC only to close an open window (`CUIStateBar`, `CUIChat`, `CUIHotKeyDlg`, `CUICmd`: `ReFocusUI` and pass it on; `CUICmdList`: Close): none asks or quits. Which UI 1264 focuses then, and its OnKeyPress, were not read. The source's window procedure (`WarFareMain.cpp`) does not handle `WM_KEYDOWN` | 1264 `005b1010`, `005f97a0`; source `UIStateBar.cpp`, `UIChat.cpp`, `UICmdList.cpp`, `WarFareMain.cpp` | binary; source |

**The realm (`client/render/front_end.h`).** The realm's loading screen spans KO's
procedure change, Init and wait: it shows from the start clip's end until the first
`World`, then `0.4` s with the bar full. Every event reaches the front end then
(`viewer.cpp`: the KO screens take every event while they are active), and its
`event()` returns before the key dispatch on `Screen::loading`, so ESC there does
nothing: `escape()`'s last line, `act(FrontAction::exit)` (quit at once), is reached
only from the login and the server list. A box showing then would take ESC as OK or
No, as KO's box manager does, but nothing shows one on loading (a drop returns to the
login first, a refusal to the select). Clicks do nothing too; only the engine's F12
reconnect (`viewer.cpp`, before the front end's `event()`) and the window close act.

**Decides (RQ-122):** ESC on 1264's loading screen neither asks nor quits: during the
load nothing reads input, and after it, until the game-start answer, ESC reaches only
the main procedure's focused UI. The realm does the same, nothing, so there is no
difference to change; the item's premise (that `escape()` quits from loading) was
`escape()` read alone. The window's close button during loading (the source's
`WM_CLOSE`, RequestExit once the main procedure is active) was not read.

### 9.12 Back on 1298's and 1264's select returns to the server list (RQ-112, 2026-11-03)

Read statically in n3e's 1298 `KnightOnLine.exe` (sha256 `828ab0db…43a5e5`, Ghidra
project `build/ghidra/audit-2026-09-19`, `-readOnly -noanalysis`, `AuditReference.java`
`recover`, the functions in memory only; output under `build/ghidra/rq112/`, not
committed) and §9.1's 1264 image (`ko1264-unpacked.exe`, sha256 `61e9a086…99e136471`,
Ghidra project `build/ghidra/rq096`, the same way), with `objdump` of both images
for the flag's writers and readers. Not run (Wine is approved for 1097 and 1264 only;
the static reading answers it). The source differs where named.

| Observation | Where | Label |
|---|---|---|
| **1298's Back disconnects, changes the procedure and sets a flag.** The bar's ReceiveMessage (`00607160`, §9.6) for `btn_back` (`+0xbc`) calls `004512f0` on `00818984`, which closes the socket (ws2_32 ordinal 3, `closesocket`) and empties its buffers; then ProcActiveSet (`00646b50`) with the login procedure `008189a8`, which sets the UI flag, closes the message boxes (`00528790`), keeps the select as the previous procedure and makes the login active, calling no Init; then sets the login procedure's byte `+0x21` to 1. The later source's Back only disconnects and changes the procedure (no flag) | 1298 `00607160`, `004512f0`, `00646b50` | binary; source `UICharacterSelect.cpp` `ReceiveMessage` |
| **With `+0x21` set, the login's Init asks for the server list, the bar hidden.** Init (`005f68e0`, which runs on the next tick, as 1264's procedure change does, §9.11) makes and places the login UI and shows `Group_LogIn` (`+0xd0`, §9.5); then with `+0x21` clear it calls the auto-login send (`005f7690`) when `00818a10` is set, and otherwise waits for the player; with it set it connects to the login server (`005f6e20`: `Server.ini`'s list, "LogIn Server fail" when none), sends `0xf5` (the server list request; no account login, `0xf3`, is sent), hides `Group_LogIn` again (SetVisible(0) through `+0x3c`) and sets the UI's requested-login byte `+0x680` | 1298 `005f68e0`, `005f6e20` | binary |
| **The flag stays until a server is chosen.** Its writers are the procedure's constructor (`005f6768`, 0), the bar's Back (`00607447`, 1), another UI's button that does the same three steps (`0060c880`–`0060c89f`, not identified here; the source's nation select Back changes the procedure only) and the login UI's ENTER (`00609100`, message `0x1000`): with `+0x21` or `+0x680` set it sends no account login and, with the server list shown and no box over it, connects to the chosen game server (`005f8880`) and clears the flag (`006093c9`) | 1298 `005f6768`, `00607447`, `0060c89f`, `00609100`, `005f8880` | binary |
| **1264 is the same.** `bt_back` (`00444e60`, §9.8) calls `00438010` on `007ad08c` (`closesocket`), ProcActiveSet (`005f7f30`, no Init, §9.11) with the login procedure `007ad0b0`, then sets its byte `+0x35` (`00445145`). The login's Init (`005bd9b0`) recreates its music (sound 35), makes and places the login UI and, with `+0x35` set, connects to the login server (`005bdf00`, `Server.ini`), sends `0xf5`, hides `Group_LogIn` (`+0xd8`) alone through its SetVisible (`+0x3c`) and sets the UI's `+0x12c`; with it clear it calls `005bea20` when `007ad118` is set (not read). The constructor (`005bd83b`) and the login UI's ENTER on the shown list (`005c0db3`, after `005bfe80`) clear it; two buttons of another UI (`005bc332`, `005bc4eb`, not identified) set it as Back does | 1264 `00444e60`, `00438010`, `00445145`, `005bd9b0`, `005bdf00`, `005bd83b`, `005c0db3` | binary |
| **So 1264 shows neither the bar nor the line from Back to its list.** Its Init hides the group directly, not through SetVisibleLogInUIs (`005c2820`), the only code that shows `Text_Rights`, which Load hides (§9.4); the server list's answer (`005beba0`) opens the list touching neither (§9.4). After a Back 1264's server list shows without the copyright line that a login press leaves on it | 1264 `005bd9b0`, `005c2820`, `005beba0` | binary |

**The realm (`client/render/viewer.cpp`, `client/network/discord_login.cpp`).** Back
(`Command::back`) drops the connection and resets the front end to the login, where
the client connects again at once (the connection starts on every frame but the
logo's). The Discord flow, reset with it, logs in with a stored session as soon as the
connection is up, as at start (`Flow::update`, phase `start` → `session`), without a
press; its answer (`done`) opens the realm list (`logged_in`). So with a stored
session the realm's Back already lands on the realm list after one round trip, as
KO's does; the item's premise ("the realm Back returns to the login") holds only for a
player without one, whose login then waits for a Discord login (KO keeps the account
in memory and never meets that case). The realm's own way (`login`, below) shows the
login bar while the client connects (no login is under way until the session's is
sent) and hides it from the session's login to its answer; the 1097 choice draws its
copyright line meanwhile and on the list, as after a login press (RQ-108). The flow test's return after a kick
shows that re-login (`tests/front_end_flow_live.py`).

**Decides (RQ-112):** N3FE version 17 carries where the select's Back lands
(`select.back`): `login` (the realm's, the default) or `realms`, 1298's: the viewer
then holds a login from the click, the bar hidden through the connection until the
flow has started (the stored session's login, which keeps it hidden to the answer and
the list, or none, where the bar shows again), and a connection that fails meanwhile
shows its `connect_failed` box, as after a login press. The 1298 recipe (not offered)
names `realms`. The 1097 choice keeps `login`: 1264's Back lands on its server list
too, its bar and its line hidden from the click (above), a look-and-feel difference
for the maintainer, proposed as its own item; `realms` alone would still draw a
layout's `login_closed` line while the bar is hidden and on the list, which 1264 does
not after a Back.
*RQ-123 (the maintainer, 2026-11-03: "Match 1264"): the 1097 choice names `realms`,
and `realms` now hides the `login_closed` line too, from the click through the
session's login and on the realm list after it, until the list is left
(`client/render/front_login.h` `BackHold`). Re-read for it with `objdump` of §9.1's
1264 image: `00445145` is `bt_back`'s store (`movb $0x1,0x35(%edx)` after the call to
ProcActiveSet `005f7f30`), and Init's branch on `+0x35` (`005bde80`) calls `005bdf00`,
sends `0xf5`, calls `Group_LogIn`'s (`+0xd8`) SetVisible (`+0x3c`) with 0 and sets the
UI's `+0x12c`, with no call to `005c2820` in Init (binary).*

### 9.13 No KO select hides an arrow at the end of the row (RQ-113, 2026-11-03)

§9.6 found 1298's bar never hiding an arrow; the realm hid the arrow with no
neighbour for every layout, a rule of its own since M4c with no KO reading behind it.
1264's and 1097's own rules were read statically here: §9.1's 1264 image
(`ko1264-unpacked.exe`, sha256 `61e9a086…99e136471`) and §8.1's 1097 dump
(`ko1097-unpacked.exe`, sha256 `82abb582…ea8febaf`), with `objdump` of each `.text`
and a PE reader for the vtables and strings (output under `build/`, not committed). Not
run (the static reading answers it; 1298 is never run). The source agrees: its
`CUICharacterSelect` touches `m_pBtnLeft` and `m_pBtnRight` only in the constructor,
Release, Load (`SetPos`), ReceiveMessage's compares and OnKeyPress's clicks, and
`CGameProcCharacterSelect` touches the UI whole (`UICharacterSelect.cpp`,
`GameProcCharacterSelect.cpp`, source).

| Observation | Where | Label |
|---|---|---|
| **1264: the arrows are found by name in Load alone.** The only references to the strings `bt_left` (`0066a840`) and `bt_right` (`0066a834`) in the image are Load's (`0044492b`–`004449d8`), which keep them at `+0xb0` and `+0xb4` | 1264 `004448f0`; strings `0066a840`, `0066a834` | binary |
| **1264: its arrow fields are read only to place, compare and click them.** In the class's code (`00444400`–`00445800`: the constructor `00444800`, Release `004448c0`, Load, ReceiveMessage `00444e60`, the info texts `00445160` and `004453f0`, OnKeyPress `004454e0`; vtable `00648f14`) `+0xb0` and `+0xb4` are written by the constructor and Release, set by Load, read by Load for GetPos and SetPos (vtable `+0x1c`, `00444be5`–`00444cdf`), compared by ReceiveMessage (`00444ec9`, `00444ee1`) and passed by OnKeyPress to ReceiveMessage as a click (`0044551f`, `00445532`); nothing calls SetVisible on either | 1264 `00444800`, `004448c0`, `004448f0`, `00444e60`, `004454e0` | binary |
| **1264: the select procedure touches its UI whole.** It keeps the UI at `+0x2c0` (allocated `0xc4` bytes, made by `00444800` at `0043f6f0`) and only deletes it (vtable `+0x4`), inits, loads and places it (`+0x5c`, `+0x8`, `+0x1c`), focuses it (`00532640`), renders it (`+0x58`, `0044054c`) and fills or clears its info texts (`00445160` at `00443e94`, `004453f0` at `00443f36`) | 1264 `0043f6f0`–`0043f744`, `004401f6`, `0044054c`, `00443e8e`, `00443f30` | binary |
| **1264: an arrow at its own edge does nothing.** DoJobLeft (`00442e60`) and DojobRight (`00442ed0`) set no state, no destination and play no sound when the camera rests at their edge (`+0x2c4` 1 and 2 in this image) | 1264 `00442e60`, `00442ed0` | binary |
| **1097: the same.** `bt_left` (`005a244c`) and `bt_right` (`005a2440`) are referenced only by Load (`0043faf0`, `0043fb2b`–`0043fbd8`), which keeps them at `+0xa8` and `+0xac`; in the class's code (`0043f000`–`00441000`, vtable `0058cd9c`) those fields are written by the constructor (`0043fa20`) and Release (`0043fad0`), read by Load for GetPos and SetPos (`0043fd64`–`0043fe13`), compared by the message handler (`0043ff69`, `0043ff81`) and clicked by the key handler (`004406cf`, `004406e2`); the select procedure keeps the UI at `+0x2c0` (made at `0043ab20`) and only deletes, loads, places, focuses and renders it (`+0x50`, `0043b9be`) and fills its info texts (`004402a0`, `004405a0`). At their own edge DoJobLeft and DojobRight change nothing (§8.2) | 1097 `0043fa20`, `0043fad0`, `0043faf0`, `0043ff00`, `00440690`, `0043ab20`, `0043b9be`; strings `005a244c`, `005a2440` | binary |

So no KO select hides an arrow: 1097, 1264 and 1298 all draw both at the ends of the
row, where a click does nothing. The realm's rule is its own.

**Decides (RQ-113):** N3FE version 18 carries the end-of-row arrow rule
(`select.arrows`): `hide` (the realm's, the default), the arrow with no neighbour to
turn to hidden; or `draw`, KO's, both drawn at every slot, a click at the end of the
row doing nothing. The 1298 recipe (not offered) names `draw`. The 1097 choice keeps
`hide`: 1264's select draws both too (above), a look-and-feel difference to the
offered front end for the maintainer, proposed as its own item.
*RQ-124 (the maintainer, 2026-11-03: "Draw both, as 1264"): the 1097 choice names
`draw`, so its select draws both arrows at the ends of the row, as 1264's does
(`004448f0`, `00444e60`, `004454e0`, above; binary). No format change.*

### 9.14 1298's Create from an occupied slot flies the camera (RQ-114, 2026-11-03)

Read statically in n3e's 1298 `KnightOnLine.exe` (sha256 `828ab0db…`): RQ-109's
decompile of `005ff920` (`build/ghidra/rq109/`), RQ-066's of the state switch
`005fe5b0` and the state-7 tick `005ff190` (`build/ghidra/rq066/`) and RQ-087's of
Render `005fb1c0` (`build/ghidra/rq087/`), all from n3e's Ghidra project
`audit-2026-09-19` (`-readOnly -noanalysis`, not committed); the pinned tree's
`ChrSelect/Data/ka_left_right_camera.n3camera` and `ka_right_left_camera.n3camera`
through `tools/assetc/ko_front_end.py` `camera_path`; 1264's select layout through
`ko_hud.parse`. Not run (1298 is never run).

| Observation | Where | Label |
|---|---|---|
| **The path is chosen by the camera's slot and the destination.** With the slot in focus (`00818a20`) taken, `005ff920` takes the first empty slot of 0–2 as the focus and the destination `+0x390`, sets state 6 and calls `005fa670` with: from the camera's slot `+0x38c` 0, 2 to slot 1 or 3 to slot 2; from 1, 4 to slot 0 or 6 to slot 2; from 2, 5 to slot 0 or 7 to slot 1. It then hides the bar (`+0x384`'s vtable `+0x3c` with 0) and shows the in-select create (`+0x388`'s with 1) at once, before the camera moves | 1298 `005ff920` | binary |
| **The arrival.** State 6 in `005fe5b0` gives every character clip 0 once and ticks it until the camera's frame equals its last (`+0x110` = `+0x10c`), then sets state 7 and the camera's slot to the destination; with the destination already the camera's slot it sets state 7 at once. State 7 runs `005ff190` with that slot, which widens the spot's theta (`+0x398`) to its limit and lights only that slot's spot. Render (`005fb1c0`) draws the zone and the three characters in every state, the bar, then in state 7 one more character (`004196a0` on `00818794 + 0x50`, taken as the player's; not read further), then the other windows (`005286e0`), the create among them | 1298 `005fe5b0`, `005ff190`, `005fb1c0` | binary |
| **Neither key skips it.** ENTER skips a path in states 1 and 2 only (`005fe280`), the tick's ESC in every state but 6 and 7 (§8.4) | 1298 `005fe280`, `005faf10` | binary |
| **Paths 6 and 7 go between the side slots.** `ka_left_right` takes the eye from (113.53, 1.10, 61.01), within 0.05 of where `ka_center_left` and `ka_right_left` end, to (136.60, 1.22, 66.62), within 0.05 of where `ka_center_right` ends, the at to (147.87, 2.00, 71.03); `ka_right_left` the reverse, to (113.54, 1.12, 60.97) and the at (103.12, 2.44, 65.03); 90 keys each at 30 a second (3 s) | the pinned tree's `ChrSelect/Data/ka_*_camera.n3camera` | local-asset |
| **1264's select has no Create button.** `ka_characterselect_us.uif`'s named nodes are `text00`, `bt_back`, `bt_exit`, `bt_left`, `bt_right` and `bt_delete`; 1264 opens create from an empty slot only, which the 1097 choice already does | the 1264 install's (and pinned tree's) `UI_US/ka_characterselect_us.uif` | local-asset |

**Decides (RQ-114, Q87):** the 1298 recipe (not offered) cooks paths 6 and 7 as
`{"from": 1, "to": 2}` and `{"from": 2, "to": 1}`, so it carries all seven of 1298's
paths; no format change (any from and to pair was already data). In the path mode,
`select_create` from an occupied slot plays the package's path from the slot in focus
to the first empty one, the bar hidden and neither ENTER nor ESC skipping it, and
opens create on the tick after the path's last frame (state 6's arrival); the camera
stays on that frame behind create and on a return from it. A rotate-mode package, or
one without that path, puts the camera on the slot and opens create at once, as
before. **Default taken:** create opens on the arrival, not with the click: 1298
shows its in-select create at once over the flying hall, but the realm's create is a
screen of its own that draws no hall, so opening it at once would hide the fly
(QUESTIONS Q87). The 1097 choice is unchanged (1264 has no Create button).
*Superseded by RQ-125 (§9.15): the 1298 recipe's create draws over the hall and
opens with the click, the camera flying behind it.*

### 9.15 1298's create is a window of its select, drawn over the hall (RQ-125, 2026-11-03)

Read statically in n3e's 1298 `KnightOnLine.exe` (sha256 `828ab0db…`) with n3e's
Ghidra project `audit-2026-09-19` (`-readOnly -noanalysis`; output under
`build/ghidra/rq125/`, not committed): `005fab40` (RQ-087's decompile), the create's
constructor `00603570`, Load `00603850`, SetVisible `00606650`, Tick `00606450`,
ReceiveMessage `00604f90`, the key handler `00605920`, the character build `005fd120`
and Cancel `005ffb90` (the last six recovered at their entries, `recover`), its vtable
`006a9454` and the reals it reads (`floats`); RQ-066's and RQ-087's `005fe5b0`,
`005ff190` and `005fb1c0`. The layout through `ko_hud.parse` and the pinned tree's
`Data/UIs_us.tbl` through its CSV. Not run (1298 is never run).

| Observation | Where | Label |
|---|---|---|
| **`+0x388` is a window the select makes once.** `005fab40` (the end of Init `005f98c0`) allocates `0x184` bytes, constructs them (`00603570`, vtable `006a9454`), inits them on the UI manager (`+0x5c`), finds `UIs_us.tbl`'s row 2 (`004531c0`) and loads its string at `+0x794` of the row's map node (`+0x8`, LoadFromFile, which calls Load, vtable `+0xc`), puts the root at (0, 0) (`+0x1c`), hides it (`+0x3c` with 0) and gives it the whole screen as its region (`+0x28`). The bar's layout is the string at `+0x774` of the row (the node's `+0x10`, Init), so the create's is the next (16 bytes on, `+0x794` of the node against the bar's `+0x10 + 0x774`): the row's 121st string beside the bar's 120th, `UI_us\co_characterCreate_us.uif` in both rows of the pinned tree's table | 1298 `005fab40`, `005f98c0`; `Data/UIs_us.tbl` | binary; local-asset |
| **The layout is three panels.** `co_characterCreate_us.uif`'s root is 291 × 705 at (0, 0) and holds `Group_race` (0, 1)–(214, 705): the seven race buttons, `text_desc`, `btn_create` and `btn_cancel`; `Group_class` (−1, 0)–(215, 702): the four class buttons and images, the stats and their arrows, face and hair; and `Group_name` (0, 0)–(363, 72): `edit_name`. It has no `area_character` | the pinned tree's `UI_US/co_characterCreate_us.uif` | local-asset |
| **Load puts the panels off the screen.** Load (`00603850`) finds `Group_name` (`+0xc0`, with `edit_name` at `+0x180`) and puts it at ((W − w) / 2, H) (C's signed division); `Group_class` (`+0xc4`) at (−w, H − 30 − h); `Group_race` (`+0xc8`) at (W, H − 30 − h). For a Karus player (`00818794 + 0x490` 1) it shows the four Karus race buttons (`+0xdc`–`+0xe8`) and hides El Morad's (`+0xcc`–`+0xd8`), for El Morad the reverse, and sets `text_desc` (`+0x15c`) to text 6124 (Karus) or 6125 | 1298 `00603850` | binary |
| **Shown, the panels slide in.** SetVisible (`00606650`, vtable `+0x3c`) with 1 sets the slide flag `+0xbc` and its distance `+0xb8` to 0. Each Tick (`00606450`) while the flag is set adds max(t × 1300 × (w − d) / w, 2) to the distance d, w `Group_race`'s width and t the real at `006d3ab0` (1/30 in the image, written by `0043ac60`; taken as the frame time), then puts `Group_race` at max(W − d, W − w − 50), clearing the flag there, `Group_class` at min(d − its width, 50) and `Group_name` at max(H − trunc((h + 30) d / (`Group_class`'s width + 50)), H − 30 − h), each keeping its other coordinate. The clamps are `Group_class` 50 from the left, `Group_race` 50 from the right, `Group_name` centred, each bottom 30 above the screen's; where the slide ends is read in the RQ-126 rows below | 1298 `00606650`, `00606450`; reals `006a94c4` (1300), `006a3bec` (2), `006a4470` (50), `006d3ab0` | binary |
| **It opens with the click.** `005ff920` (§9.14) hides the bar and shows `+0x388` before the camera moves: in the path branch it loads the path first (`005fa670`, called at `005ffad1`) and then shows the window (`005ffaec`), and the tick moves the camera (`005fe5b0` case 6); Render (`005fb1c0`) draws the zone and the characters in every state, then the bar, then in state 7 the player's character (`00818794 + 0x50`), then the other windows (`005286e0`), the create among them, then the alpha flush (§8.4) | 1298 `005ff920`, `005fb1c0` | binary |
| **The new character stands at the camera's slot, once a race is chosen.** `005fab40` sets the player's race (`+0x48c`) and class (`+0x494`) to −1 and releases its character (`+0x50`'s first virtual). A race button (ReceiveMessage `00604f90`: Karus 1–4, El Morad 11–13) or a class button sets them and calls `005fd120`, which builds the character from them and, by the camera's slot `+0x38c`, puts it (`+0x50`'s `+0x28`, taken as its position) at the select slot's position turned about (0, 1, 0) (`0064d306`, applied by `+0x30`): Karus (128, 0, 91) by `0x406dec5d` (213°), (108.7, 0.2, 62.9) by `0x401fbb88` (143°), (141.3, 0.3, 68.5) by `0x409e0e99` (283°); El Morad its own three. Those two calls (`0060505c`, `0060521d`) are the only callers the project shows. So until a race is clicked state 7 draws no character, and one clicked during the flight is placed at the slot the flight left | 1298 `005fab40`, `00604f90`, `005fd120` | binary |
| **ESC presses Cancel; Cancel returns to the select at once.** The key handler (`00605920`, vtable `+0x60`) sends key 1 (DIK_ESCAPE) to ReceiveMessage as a click on `btn_cancel` (`+0x178`); Cancel (`005ffb90`) sets state 5, shows the bar, hides the create and releases the character, whatever the camera is doing; Create (`btn_create`, `+0x174`) calls `005fffd0`, which sends the create (read in RQ-127, below) | 1298 `00605920`, `00604f90`, `005ffb90` | binary |

RQ-126 (2026-11-03) read Tick (`00606450`) again instruction by instruction from
RQ-125's listing (`build/ghidra/rq125/`, `-readOnly -noanalysis`, not committed) for
where the slide ends:

| Observation | Where | Label |
|---|---|---|
| **The distance is a float; the positions truncate it.** The step is worked on the x87 stack (`FILD` w, `FSUB` d, `FDIV`, `FMUL` the frame time and 1300, `FCOM` 2 and the floor taken when below), added to d and stored back as a float (`FST float ptr [ESI + 0xb8]`, `006064f7`); each position takes `__ftol` (`00674278`, toward zero) of d, or of (h + 30) · d / (w_c + 50) for `Group_name` (`006065ff`–`00606615`). Group_race's `__ftol` takes the x87 sum (`FST` keeps it on the stack), not the float stored, so its arrival test can differ from one on the stored float by a frame where the sum's rounding to a float crosses a whole number; the realm tests the stored float | 1298 `006064bc`–`00606615` | binary |
| **The flag clears on Group_race's arrival alone.** Group_race's x is W − trunc(d); when that is at most W − w − 50 (`0060651a`, `JG`) the x is W − w − 50 and `+0xbc` is cleared (`00606524`); `Group_class` and `Group_name` are placed in the same tick by their own clamps and are not moved again. With w 214 and w_c 216 (`co_characterCreate_us.uif`) the flag clears once trunc(d) ≥ 264, Group_race's travel, while Group_class reaches 50 only at 266 and Group_name H − 102 only at 266 | 1298 `0060651a`–`00606524`, `0060659a`–`006065a8`, `0060661c`–`00606626` | binary; local-asset |
| **So at a frame time under about 0.2 s the panels end short.** Below d = 214 the step is t · 1300 · (w − d) / w, past it the floor 2 (w − d < 0); unless one step carries d from below 214 past 266 (t ≥ about 0.2 s), the last steps are 2, d ends in [264, 266), `Group_class` at 48 or 49 (worked from the code as read: 30 fps, 44 ticks, 48; 60 fps, 58 ticks, 49) and `Group_name` at H − 101, its bottom 29 above the screen's; `Group_race` at W − w − 50 | 1298 `00606450` as read; reals `006a94c4`, `006a3bec` | binary |
| **The first tick runs before the first frame draws.** The procedure's tick passes the mouse to the UI manager (`MouseProc`, where the bar's Create shows the window) and then ticks it (`s_pUIMgr->Tick()`) before Render, so the frame the window first draws is one step in | `ref/ko-src` `src/Client/WarFare/GameProcedure.cpp` (`CGameProcedure::Tick`) | source |

**Decides (RQ-126, Q87):** N3FE version 20 carries create's slide as package data
(item 13, `content/front-end.md`): a rate, a floor and nodes, the first the lead,
each from a start rule toward where its moves put it by trunc(num · d / den), the
lead's arrival ending it. The 1298 recipe slides `Group_race` from x = W,
`Group_class` from x = −w and `Group_name` from y = H with `Group_class`'s pace
(102 / 266), rate 1300 and floor 2, so in play its panels end where 1298's do (48
or 49 and 29 above, not RQ-125's 50 and 30). The client steps it each frame by the
frame's seconds as 1298 steps by its frame time (`006d3ab0`, s_fSecPerFrm). The
1097 choice has no slide (1264's create is a procedure of its own, §9.1).

**Decides (RQ-125, Q87):** N3FE version 19 says where create draws
(`select.create`): `screen`, the realm's and the default, a screen of its own with
its `char_view`; or `hall`, 1298's: create is a window over the select's hall, its
layout binding no `char_view`, the hall drawn behind it and the zone's blend meshes
after it; `select_create` opens it with the click, from an occupied slot in the path
mode the camera flying to the empty slot behind it, and once the camera is on the slot
the new character (the create model) stands there under its spot, turned by the slot's
`create_yaw` (version 19's per-slot real; the recipe's degrees). Cancel and ESC
return to the select at rest on the slot. The 1298 recipe (not offered) names `hall`,
draws `co_characterCreate_us.uif` with its panels where the slides end (`place`
`origin`; `Group_class` `x` 50, `Group_race` `right` 50, a new move key, and
`Group_name` `x` `centre`, each `bottom` 30), El Morad's race buttons hidden, and the
yaws 213, 143 and 283. The 1097 choice keeps `screen` (1264's create is a procedure
of its own, §9.1). **Defaults taken:** the panels stand where the slides end from the
first frame (the slides, `00606450`, are proposed as their own item; RQ-126, above,
plays them); the new
character stands from the arrival, the realm's race and class being always chosen
(1298 draws none until a race is clicked); a Cancel during the flight puts the camera
on the slot at once (1298's camera after a Cancel mid-flight was not read). *RQ-127,
below, read both.*

RQ-127 (2026-11-03) read the create's Create (`005fffd0`, from RQ-125's decompile,
`build/ghidra/rq125/`) and, decompiled for it (`build/ghidra/rq127/`, n3e's project
`audit-2026-09-19`, `-readOnly -noanalysis`, not committed), its error box
`00600750`, the select's create answer `005ff6b0` and the arrows DoJobLeft `005fe3c0`
and DojobRight `005fe450`, with RQ-066's state switch `005fe5b0`, rest tick `005fef90`
and select tick `005faf10`, RQ-109's Start `005ff870` and RQ-125's Cancel `005ffb90`.
Not run (1298 is never run).

| Observation | Where | Label |
|---|---|---|
| **Create checks as the source's MsgSendCharacterCreate, in its order.** An empty name (the ID string's length, `00818794 + 0x480`, below 1) posts code 6; the race (`+0x48c`) −1 code 7; the class (`+0x494`) −1 code 9; bonus points left (the create's `+0xb0` above 0) code 10; a name holding one of the source's forbidden letters (`~` … `'`, the space, `\n`) or one of a set of double-byte symbols code 5. Each returns 0, sending nothing | 1298 `005fffd0`; source `GameProcCharacterCreate.cpp` (`MsgSendCharacterCreate`) | binary; source |
| **Then it sends the source's `WIZ_NEW_CHAR`.** `0x02`, the slot in focus (`00818a20`), the name's length (2 bytes) and the name, the race (1 byte), the class (2 bytes), the face (`+0x7d8`), the hair (`+0x7dc`) and the five stats (`+0x830`–`+0x850`, 1 byte each), through `00451b80`; then clears the UI flag `00818994 + 0xb4` (the source's `EnableOperationSet(false)`) | 1298 `005fffd0` | binary |
| **The codes are 1264's rows.** `00600750(n)` posts an OK box (`00646ba0`, style 0) titled row 1901 (`0x76d`) holding row 1911 (1), 1907 (2), 1912 (3), 1902 (4), 1906 (5), 1905 (6), 1908 (7), 1910 (8), 1904 (9), 1913 (10), else 1915, the same map as 1264's ReportErrorCharacterCreate (`0043a820`, §9.2). So a Create before a race is clicked says row 1908, before a class row 1904 | 1298 `00600750` | binary |
| **The answer.** The select's ProcessPacket (`005ff6b0`, vtable `006a93d0`) for `0x02` reads a code: not 0, it posts `00600750(code)` and sets the UI flag; 0, it runs Cancel (`005ffb90`) and the create's reset (`006066b0`), asks for the character list (`0x0c`) and clears the flag until it comes | 1298 `005ff6b0` | binary |
| **After a Cancel mid-flight the camera flies on.** Cancel touches neither the camera (`+0x1a4`) nor its slot (`+0x38c`) nor the destination (`+0x390`); it sets state 5, shows the bar and hides the create (§9.15). The select tick ticks the camera last in every state (`005faf10`, §8.4), and a path loaded by `005fa670` holds its last frame (`+0x114` 1), so the path plays on to the empty slot with the bar shown. The slot is set to the destination only by state 6's arrival (`005fe5b0`), which state 5 no longer runs, so it stays the slot the flight left: state 5's `005fef90` gives that slot's character its front clip, lights that slot's spot and fills the bar's info texts from it (`006074c0`), while the focus (`00818a20`) stays the empty destination | 1298 `005ffb90`, `005faf10`, `005fe5b0`, `005fef90` | binary |
| **And then.** The tick's ESC (`005faad0`'s body, inline in `005faf10`) in state 5 puts the camera's frame on its last and the slot on the destination, the select then at rest there; Start and Create (`005ff870`, `005ff920`) take the focus, empty, and open create at once (state 6), which arrives when the camera's frame is its last; an arrow (`005fe3c0`, `005fe450`) turns from the slot the flight left (`+0x38c`), loading the path from it (`005fa670`, its frame 0), so the camera jumps to that path's start | 1298 `005faf10`, `005ff870`, `005ff920`, `005fe3c0`, `005fe450`, `005fa670` | binary |
| **1264's create starts with no race too (source).** The source's `CGameProcCharacterCreate::Init` sets race and class unknown, and SetChr builds the character from the race; the 1264 binary's create Init was not read | source `GameProcCharacterCreate.cpp` | source |

**Decides (RQ-127, Q87):** the 1298 recipe keeps the realm's race and class
chosen from the open, the new character standing from the camera's arrival. 1298's
wait for a race click rests on a create where race, class, face, hair and stats are
the player's to pick, Create refusing it until a race and a class are clicked and the
bonus points spent (rows 1908, 1904, 1913); the realm shows race and class fixed and hides face, hair and
stats on every create (Q52, the maintainer's, 2026-10-31), so the 1298 recipe's
Tuarek and priest stand on from the open and its Create can never meet rows 1908
or 1904. Waiting would need a format change (race and class off at the open, a click
that turns them on, two more create messages) for a look 1298 shows only before a
click the realm's create does not ask for; whether to make it is the maintainer's
(Q87). The Cancel mid-flight stays the realm's (the camera put on the slot at once,
the select at rest there); 1298's, read above (the camera flying on, the select at
rest on the slot it left until ESC or a turn), is proposed as its own item. No format
change; the 1097 choice is unchanged. *RQ-130, below, takes the wait (Q87 (b), the
maintainer's).*

RQ-130 (2026-11-03) read the race and class clicks further, from RQ-125's decompile
(`build/ghidra/rq125/`, n3e's project `audit-2026-09-19`, `-readOnly -noanalysis`,
not committed): ReceiveMessage `00604f90`, the character build `005fd120`, the button
states `006060f0` and `006062d0`, the panel texts `00605950` and the reset `006066b0`,
with the source's button and the pinned layout's button styles. Not run (1298 is
never run).

| Observation | Where | Label |
|---|---|---|
| **A race click sets the race, unsets the class, and builds only on a change.** For a race button ReceiveMessage keeps the old race, sets the race (`+0x48c`, word `0x123` of `00818794`: 1–4 Karus, 11–13 El Morad), sets the class (`0x125`) to −1 on every race click, calls `005fd120` only when the race differs from the old, then `006060f0(race)`. A class click sets the class (101–104 or 201–204 by nation), calls `006062d0(class)` and `005fd120` only when the class changed | 1298 `00604f90` | binary |
| **The build needs a race and stands at the camera's slot.** `005fd120` with the class −1 takes a default class for the race's stat row; it looks the race up in its default-looks map (`00453230`) and returns, building nothing, when the race has no row (−1 has none); otherwise it builds the character, calls `00605950`, `006060f0(race)`, `006062d0(class)` and places it by the camera's slot `+0x38c` as it is at that call, so a race clicked while the camera flies (the slot still the one the flight left, §9.15 RQ-127) stands there | 1298 `005fd120` | binary |
| **The chosen race and class draw down.** `006060f0(race)` sets the race buttons (`+0xdc`…) to 2 (`UI_STATE_BUTTON_NORMAL`) and the chosen one to 3 (`UI_STATE_BUTTON_DOWN`), the class buttons to 7 (`UI_STATE_BUTTON_DISABLE`) but the race's classes to 2 (the Tuarek's rogue and priest), hiding each disabled class button and showing its `img_*` (`+0xfc`…); `006062d0(class)` sets the class buttons to 2 and the chosen one to 3 and shows the class's stat labels (`+0x10c`…) | 1298 `006060f0`, `006062d0` | binary |
| **Down holds under the pointer.** The values are the source's `eUI_STATE` (2 NORMAL, 3 DOWN, 6 ON, 7 DISABLE); a check-style button (`UISTYLE_BTN_CHECK`, `0x00020000`) in DOWN stays DOWN while the pointer moves over and off it, a click on it going DOWN_2CHECKUP (ReceiveMessage then sets it DOWN again) | source `N3UIDef.h`, `N3UIButton.cpp` (`MouseProc`) | source |
| **1298's race and class buttons are check buttons.** Every `btn_race_*` and `btn_class_*` in the pinned `co_characterCreate_us.uif` has style `0x00020000` | `UI_US/co_characterCreate_us.uif` | local-asset |
| **Each open starts again.** Init (`005fab40`) and Cancel (`005ffb90`) set the race and class to −1 (§9.15, RQ-125); the reset (`006066b0`, which Cancel calls, as does the answer to a create the server accepts, `005ff6b0`) hides the window, calls `00605950` and sets every race and class button to NORMAL | 1298 `005fab40`, `005ffb90`, `006066b0` | binary |
| **Each build rewrites the panel texts.** `00605950` shows the class buttons and their images, sets the stat texts, and sets `text_desc` (`+0x15c`) and `edit_name` (`+0x180`) from the string at `006dfe28`, a zero-initialised global whose writers were not read (so whether a race click clears a typed name is open) | 1298 `00605950` | binary |

**Decides (RQ-130, Q87 option (b), the maintainer's 2026-11-03, "Match 1298: wait
for a race"):** the 1298 recipe waits for the race and class clicks as package data
(N3FE version 21: `create_race` and `create_class` bound to `btn_race_ka_tu` and
`btn_class_priest`, the messages `create_no_race` row 1908 and `create_no_class` row
1904, each titled 1901, `content/front-end.md`): each open has neither chosen and no
new character; a Tuarek click chooses the Tuarek and unchooses the priest, and the
new character stands at the camera's slot from that click (from a flight, the slot
the flight left); a chosen button draws its down image, under the pointer too;
Create refuses an empty name, then no race, then no class, as `005fffd0`. The server
still makes the character it makes (Q52); the choice gates only the client's Create.
The 1097 choice binds neither, its race and class chosen from the open as before.
Not carried: the class buttons a race cannot take hidden for their `img_*` after the
click (the recipe draws them fixed disabled, their images hidden), the stat texts and
`006dfe28`'s text, each proposed. *RQ-133, below, carries the first.*

RQ-133 (2026-11-03) read the class buttons' and images' visibility from RQ-125's
decompile (`build/ghidra/rq125/`, n3e's project `audit-2026-09-19`, `-readOnly
-noanalysis`, not committed): the button states `006060f0` and `006062d0`, the panel
texts `00605950`, the reset `006066b0`, Load `00603850` and the build `005fd120`'s
calls, with the source's `CN3UIBase` and the pinned layout. Not run (1298 is never
run).

| Observation | Where | Label |
|---|---|---|
| **The race click swaps the classes it cannot take for their images.** Load finds the class buttons `btn_class_warrior`, `_rogue`, `_mage` and `_priest` (`+0xec`–`+0xf8`) and their images `img_warrior`, `img_rogue`, `img_mage` and `img_priest` (`+0xfc`–`+0x108`). `006060f0(race)` sets each class button to its state (`+0x34`) and then shows (`+0x3c`) its image only when that state is 7 (`UI_STATE_BUTTON_DISABLE`) and the button only when it is not; for the Tuarek (race 2) the warrior and mage are 7 and the rogue and priest 2, so the warrior and mage buttons hide and their images show, and the rogue and priest images hide | 1298 `006060f0`, `00603850` | binary |
| **Before a race click every class button and image shows.** `00605950` shows the four class buttons and the four images (`+0x3c` with 1); the reset `006066b0` (Cancel `005ffb90` and the accepted create `005ff6b0` call it) calls it and sets the class buttons NORMAL; Load sets neither's visibility, and a UIF node loads visible (`CN3UIBase`'s constructor sets `m_bVisible` true), so the first open shows them too. A build (`005fd120`) calls `00605950`, then `006060f0(race)` and `006062d0(class)`, so it ends as the race click leaves them | 1298 `00605950`, `006066b0`, `00603850`, `005fd120`; source `N3UIBase.cpp` | binary; source |
| **A class click leaves them.** `006062d0` sets the four class buttons' states (2, the chosen one 3) and the stat labels' visibility (`+0x10c`…), never a class button's or image's | 1298 `006062d0` | binary |
| **Each image lies under its button.** In `Group_class` the four images (150 × 35, the greyed tile of `ui_login_02_us.dxt` at v 0.207–0.275 with the class name, white over `0xff262626`) come before the four buttons (149 × 34 at the same origins), so each button draws over its image, a pixel of the image past its right and bottom edges (`CN3UIBase::Load` adds each child at the front and Render walks the list backwards: file order). A class button's disabled image is its normal one (the same tile, the same label colours) | `UI_US/co_characterCreate_us.uif`; source `N3UIBase.cpp` | local-asset; source |

**Decides (RQ-133, Q87):** N3FE version 22 adds node flag 8, a create node drawn only
until the race is chosen (the recipe's create `until_race`, in a create that binds
`create_race`, `content/front-end.md`, "Actions"). The 1298 recipe no longer hides
the four images and names `img_rogue`, `img_priest`, `btn_class_warrior` and
`btn_class_mage` until the race: each open draws the four class buttons over their
images, and the Tuarek click leaves the warrior and mage images where their buttons
were, beside the rogue and priest buttons. Still the realm's: the warrior, rogue and
mage buttons stay fixed disabled (Q52), taking no pointer where 1298's take it (the
warrior and mage before the race click, the rogue after); at rest they look as
1298's, the disabled image being the normal one. No look is added: the images and
buttons are the layout's own. The 1097 choice names none and is unchanged.

**The stat labels after a priest click (RQ-143, 2026-11-04).** Read from RQ-125's
decompile (`build/ghidra/rq125/`, n3e's project `audit-2026-09-19`, `-readOnly
-noanalysis`, the client `KnightOnLine.exe` sha256 `828ab0db…0e643a5e5`, not
committed): the class click's `006062d0`, the panel texts `00605950`, the reset
`006066b0`, Load `00603850` (its listing for the stack slots), the build `005fd120`
and ReceiveMessage `00604f90`; the label names read from the image's `.rdata`; with
the pinned layout and the realm's capture of the 1298 recipe's create (`make
live-ko`, `build/live-ko/front-end/1298-1024x768.create.ppm`, sha256
`c7cd4123…0f6935d8`, and the 1280×1024 and 1600×1200 shots, not committed). Not run
(1298 is never run). The source has neither name.

| Observation | Where | Label |
|---|---|---|
| **Load keeps two label sets in the order str, dex, sta, int, map.** One loop of five finds `str_01`, `dex_01`, `sta_01`, `int_01`, `map_01` (strings `006d8968`–`006d8948`) at `+0x10c`–`+0x11c`, `str_02` … `map_02` (`006d8940`–`006d8920`) at `+0x120`–`+0x130`, the `text_*` values at `+0x134`–`+0x144` and the `area_*` tooltips at `+0x148`–`+0x158` (rows `0xc93`, `0xc82`, `0xc94`, `0xc8a`, `0xc81`) | 1298 `00603850` (`00603e94`–`00604479`) | binary |
| **Each pair is a cream label over a cyan copy.** In `Group_class` each `*_02` (Arial 12 bold, 0xff80ffff) comes right before its `*_01` (the same font and text, 0xfffdf8d0) in the same rect: "STR", "DEX", "HP", "INT", "MP" at x 32–89, y 320, 354, 390, 424, 458 (22 high). Drawn in file order, so a shown `*_01` covers its `*_02`'s glyphs; a hidden one leaves the cyan | `UI_US/co_characterCreate_us.uif` (`f918867a…3868d2e4`); source `N3UIBase.cpp` | local-asset; source |
| **A class click hides its class's two cream labels.** `006062d0(class)` sets each `+0x10c`… node visible when its flag is clear (`SETZ`, vtable `+0x3c`): flags 0 and 2 for the warrior (101, 201), 1 and 2 for the rogue, 3 and 4 for the mage, 0 and 3 for the priest (104, 204), none for −1. So after a priest click `str_01` and `int_01` hide and "STR" and "INT" read cyan, "DEX", "HP" and "MP" cream. It never touches the `*_02` set | 1298 `006062d0` (`006063aa`–`006063b0`) | binary |
| **Each open and each build show all ten.** `00605950` shows `+0x10c`–`+0x130` (vtable `+0x3c` with 1) and writes the five values (`+0x134`…, vtable `+0x7c`, from the player's `+0x830`…); the reset `006066b0` calls it, then writes the five values and `text_bonus` (`+0x160`) empty (`006dfe28`). The build `005fd120` calls `00605950`, `006060f0(race)` and `006062d0` with the player's class as it stands (`+0x494`, which it never writes), so a race click (class −1) leaves all five cream. A class click runs `006062d0(class)` and, on a change, the build, which ends with the same call; a build with no race (a class clicked first) returns before `00605950`. `006060f0` touches no label | 1298 `00605950`, `006066b0`, `005fd120`, `00604f90`, `006060f0` | binary |
| **A race click on the same race keeps the cyan.** ReceiveMessage sets the class to −1 on every race click but builds only when the race changes, so after Tuarek, priest, Tuarek the priest button is NORMAL again (`006060f0`) and "STR" and "INT" stay cyan until the next build or open | 1298 `00604f90` | binary |
| **The realm draws all five cream throughout.** The 1298 recipe hides none of the ten and has no state that changes them. In the open shot (no race, no class) each rect's text is cream: 175, 194, 136, 139 and 159 near-cream pixels in the STR, DEX, HP, INT and MP rects and at most one cyan-leaning pixel at 1024×768, within three pixels of that at the other two sizes; no live suite shoots the create after a class click (since RQ-153 one does: `create-class`) | `build/live-ko/front-end/1298-*.create.ppm`; `games/moradon/front-end-1298.json` | local-asset |

So at each open and after the race click 1298 and the realm both read five cream
labels; after the priest click 1298 reads "STR" and "INT" cyan (0x80ffff), where the
realm stays cream. Side by side: `build/ghidra/rq143/create-stat-labels-1298.png` (not
committed; left the 1024×768 capture, right the same with each STR and INT text pixel
redrawn cyan at a coverage fitted against the cream over a local background, as
1298's `str_02` and `int_02` alone would draw). Also on this frame, not this item:
1298's build fills the five values (`00605950`), which the realm leaves empty (Q52;
RQ-135 reads that function's texts). **Decided nothing at RQ-143 (Q93):** a
look-and-feel difference, put to the maintainer.

**Decides (RQ-145, Q93 (b), the maintainer's "Match 1298", 2026-11-04):** N3FE
version 23 adds node flag 16, a create node drawn until a class is clicked and again
from each open and each race click that builds the character (the recipe's create
`until_class`, in a create that binds `create_class`, none of its nodes also until
the race; `content/front-end.md`, "Actions"). The 1298 recipe names `str_01` and
`int_01`: each open draws all ten labels cream, the priest click (`006062d0(104)`)
hides the two cream copies so "STR" and "INT" read in their cyan `str_02` and
`int_02`, the Tuarek click that builds the character (`005fd120`'s `00605950`)
draws them cream again, a second click on the chosen Tuarek, which unchooses the
priest and builds nothing (`00604f90`), leaves them cyan, and a Cancel and a new
open draw them cream. A priest click before the race hides them as well, and the
Tuarek click then draws them again, as 1298's build does. The realm's create binds
one class, so the flag stands for the priest's pair; the rogue's, warrior's and
mage's pairs (flags 1 and 2, 0 and 2, 3 and 4) are never clicked (Q52). Checked by
the client's choice state (`tests/front_end.cpp`) and the 1298 recipe's create in
`make live-ko` (`tests/front_end_live.py`, the ids drawn after each click), and
(RQ-153) by its frames: the shot `create-class`, taken after the race and the priest
click, holds cyan text in the STR and INT rects and cream in DEX, HP and MP at each
window size, and the open's `create` shot cream in all five. The stat values stay empty (Q52) and the
1097 choice is unchanged (Q92).

### 9.16 1264's chosen race and class draw down (RQ-134, 2026-11-03)

The realm's fixed `on` draws a button's `BS_ON` image; 1298's chosen race and class
draw `UI_STATE_BUTTON_DOWN` (RQ-130, above). The 1097 choice draws 1264's create
(§9.2), its Tuarek and priest fixed `on` (Q52), so this reads 1264's. Read in §9.1's
1264 image (`ko1264-unpacked.exe`, sha256 `61e9a086…99e136471`) in the same Ghidra
project (`build/ghidra/rq096`, `-readOnly -noanalysis`, output under
`build/ghidra/rq134/`, not committed; `objdump` for the button class), with the 1264
install's `Ka_CharacterCreate_us.uif` (`4a1b072a…`), `ui_ka_charcreate02_us.dxt`
(`6f0ef999…`, the pinned tree's byte for byte) and `ui_el_charcreate01_us.dxt`
(`e5a83809…`), decoded by `ko_hud`, and the realm's own capture of the 1097 choice's
create (`make live-ko`, `build/live-ko/front-end/1024x768.create.ppm`, not committed).
Not run: 1264 reaches create only from a game server's select, and the static read
leaves nothing open.

| Observation | Where | Label |
|---|---|---|
| **1264's button draws one image per state, as the source's.** The button (vtable `006484e8`, constructor `00403820`: state `+0x74` 2, style `+0x78` `0x10000`) keeps its state images at `+0xb4`–`+0xc0` by each image's reserved index (Load `00403e70`: an image child whose `+0x7c` is under 4 goes to `+0xb4` + 4 × index, `00403ed5`–`00403ee6`; `ko_hud`'s slot). Render (`00403a70`, a jump table at `00403b0c` on the state − 2) draws state 2 with index 0 (`BS_NORMAL`), 3, 4 and 5 with index 1 (`BS_DOWN`), 6 with index 2 (`BS_ON`) and 7 with index 3 (`BS_DISABLE`), each only when present; SetState (`+0x34`, `00403710`) stores the state. MouseProc (`00403b30`) turns a NORMAL button under the pointer ON (`00403d42`–`00403d51`) | 1264 `00403820`, `00403e70`, `00403a70`, `00403710`, `00403b30`; source `N3UIButton.cpp` `Render`, `MouseProc` | binary; source |
| **The chosen race and class draw down.** `0043ec90` (the source's `UpdateRaceAndClassButtons`) starts the race buttons (`+0xb8`–`+0xc4`) at 2 and the class buttons (`+0xc8`–`+0xd4`) at 7, then sets the chosen race to 3 (`UI_STATE_BUTTON_DOWN`) and its classes to 2 (Karus 1 the warrior, 2 the rogue and priest, 3 the mage, 4 the priest; El Morad 11 the warrior, 12 and 13 all four), stores the race at the player's `+0x398` and −1 at its class `+0x3a0`, sets each button's state, and shows each class's `img_*` (`+0xd8`–`+0xe4`) only when its state is 7 and the button only when it is not. `0043ee10` (`UpdateClassButtons`) sets the class buttons to 2 and the chosen class (101–104, 201–204) to 3, and shows its stat labels (`+0xe8`…). Neither sets 6 (ON) | 1264 `0043ec90`, `0043ee10` | binary |
| **The clicks call them; each open starts with none.** ReceiveMessage (`0043dfc0`) sets the race for a race button by nation (`+0x39c`), calls SetChr (`00439970`) only when the race changed, then `0043ec90(race)`; a class button sets the class and calls `0043ee10(class)` (`0043e310`). SetChr calls Reset (`0043ea10`), `0043ec90` and `0043ee10` (`0043a077`–`0043a093`). The create Init (`00439550`) sets race and class to −1 each time; Load (`0043cd00`) calls Reset (`0043dbf9`), which shows the four class images and hides the four class buttons, and the race buttons keep the constructor's 2: 1264's create opens with no race or class chosen | 1264 `0043dfc0`, `00439970`, `0043ea10`, `00439550`, `0043cd00` | binary |
| **The down and on images differ: sunken against raised.** The layout's race and class buttons are check buttons (style `0x00020000`). The Tuarek's states 0 and 3 are the grey tile at (0, 74) of `ui_ka_charcreate02_us.dxt`, its on (2) the pink tile at (195, 74), its down (1) the pink tile at (0, 404); the priest's on is at (195, 222) and its down at (195, 369) (194 × 36 each, unlabelled; the labels are root strings drawn over the buttons in every state). Both pinks are the same colour; the on tile has the normal tile's raised bevel (light top and left, dark bottom and right), the down tile a sunken one (a dark inner shadow along the top and left). A third of the pixels (0.32) differ by more than 32 in a channel between on and down, a mean of 37.6 of 255 | `UI_US/Ka_CharacterCreate_us.uif`, `ui_ka_charcreate02_us.dxt` (decoded and viewed) | local-asset |
| **The realm draws the on tiles.** In the 1097 choice's create at 1024 × 768 (the root at (0, −10)), 6,507 of the Tuarek button's 6,984 pixels are its on tile's (the rest under its label), 6,567 of the priest's; the down tiles match 2,823 and 2,879 at best | `build/live-ko/front-end/1024x768.create.ppm` against the tiles | local-asset |
| **Two more differences on the same buttons.** The Puri Tuarek (`btn_race_ka_pt`, style `0x10000`) has no texture on its disabled image, so the realm's fixed disabled draws only its label where 1264, which never disables a race button, draws its normal tile (`ui_el_charcreate01_us.dxt`, v 0.703–0.773). And after a Tuarek click 1264 hides the warrior and mage buttons for their `img_*` (darker grey tiles of `ui_el_charcreate01_us.dxt`, v 0.414–0.484 and 0.559–0.629), where the 1097 choice draws those buttons fixed disabled, their normal grey tile (RQ-133 carried 1298's for the 1298 recipe) | `0043ec90`; the layout and textures above | binary; local-asset |

**Decided nothing at RQ-134 (Q89):** 1264 never draws a chosen race or class with
its on image; the on image is only a NORMAL button's under the pointer. The realm's
chosen Tuarek and priest looked raised where 1264's look pressed in, the same pink.
Changing it is look and feel, put to the maintainer one by one (Q89). The Puri
Tuarek and the class images are proposed as their own items.

**Decides (RQ-138, Q89 (b), the maintainer's 2026-11-03, "Sunken, as 1264"):** the
1097 choice's Tuarek and priest are the recipe state `down` (the cook's fixed on with
the down image in the on state, `content/front-end.md`), so they draw their `BS_DOWN`
tiles as 1264's chosen race and class; they stay chosen from the open (Q52).

**Decides (RQ-139, Q90, the maintainer's 2026-11-03, "Grey button, as 1264"):** the
1097 choice's Puri Tuarek takes no fixed state and no action, so it draws its
`BS_NORMAL` tile, as 1264's race buttons at rest (`0043ec90` sets them 2, which
Render `00403a70` draws with index 0), where its fixed disabled drew only its label.
Like the fixed disabled Arch and Wrinkle Tuarek (their disabled images are their
normal tiles) it never lights under the pointer (the client lights only a bound
button) and a click does nothing: the race stays Tuarek (Q52). `make live-ko`
matches the drawn rect to the normal tile at each size. The 1298 recipe's layout
textures every race button's disabled image and is unchanged.

**The class column after a Tuarek and a priest click (RQ-140, 2026-11-03).** The 1097
choice's create is chosen from the open (Q52), so it stands for 1264's create after a
Tuarek click and a priest click. Re-read in the same image and project (`0043ec90`,
`0043ee10` and `0043ea10` decompiled again, `-readOnly -noanalysis`, output under
`build/ghidra/rq140/`, not committed, identical to RQ-134's), with the layout and
textures above and the realm's capture of the 1097 choice's create after RQ-139
(`make live-ko`, `build/live-ko/front-end/1024x768.create.ppm`, sha256 `4f2407f3…`,
not committed). Not run, as above.

| Observation | Where | Label |
|---|---|---|
| **Load pairs each class button with its image.** The loop that ends Load (`0043cd00`, from `param_1 + 0x32`) stores `btn_class_warrior`, `_rogue`, `_mage`, `_priest` at `+0xc8`–`+0xd4` and `img_warrior`, `img_rogue`, `img_mage`, `img_priest` at `+0xd8`–`+0xe4`, four steps of one each; the stat labels `img_str`, `img_sta`, `img_dex`, `img_int`, `img_map` go to `+0xe8`–`+0xf8` | 1264 `0043cd00` | binary |
| **After the Tuarek: warrior and mage images, rogue and priest buttons.** `0043ec90(2)` (case 2, the Karus Tuarek) sets the race buttons 2 but the Tuarek 3, and the class states to 7, 2, 7, 2: it hides `btn_class_warrior` and `btn_class_mage` and shows `img_warrior` and `img_mage`, and shows the rogue and priest buttons with `img_rogue` and `img_priest` hidden. The source's `UpdateRaceAndClassButtons` does the same | 1264 `0043ec90`; source `UICharacterCreate.cpp` | binary; source |
| **After the priest: the priest down, the rogue a live button, the images kept.** `0043ee10(104)` (`0x68`) sets all four class buttons to 2 and the priest to 3 and changes no button's or image's visibility, so the warrior and mage stay hidden behind their images; it shows stat labels 0 and 3, `img_str` and `img_int` (the layout's pink 0xff8080 "Strength" and "Intelligence" over the grey ones). The rogue is a NORMAL button: under the pointer MouseProc (`00403b30`) turns it ON (its raised pink tile) and a click would choose the rogue. The images are image nodes: no pointer, no click | 1264 `0043ee10`, `00403b30` | binary |
| **The images are darker grey tiles under the same labels.** `img_warrior` and `img_mage` (root children 165 and 163) have the buttons' rects and draw before them (171–174) and before the labels (root strings 221–228: a light 0xc0c0c0 copy and the dark 0x382e14 one), so the labels draw over the images as over the buttons. Their tiles are `ui_el_charcreate01_us.dxt` (512 × 512) at (201, 212) and (201, 286), 194 × 36, opaque but for 16 corner pixels. Blended over the panel, their mean grey is 91 and 88 against the realm's drawn 131 and 129, and 70 % of their pixels differ from the realm's by more than 32 in a channel (a mean of 44 of 255) | `UI_US/Ka_CharacterCreate_us.uif`, `ui_el_charcreate01_us.dxt` (decoded and viewed) | local-asset |
| **The realm's column today.** In the capture the warrior, rogue and mage draw their fixed disabled image, which in this layout is the normal tile (6,467, 6,506 and 6,302 of 6,984 pixels equal it; the rest under the labels or at the corners), the priest its down tile (6,433); the recipe hides `img_warrior`, `img_rogue` and `img_mage` but not `img_priest`, which draws under the priest: the down tile's 155 edge pixels (alpha 238 and below) all match a blend over `img_priest`, not over the panel, up to 17 of 255 apart. 1264 hides it after the Tuarek. The recipe also hides all five stat labels, where 1264 shows the priest's two | `build/live-ko/front-end/1024x768.create.ppm`; `games/moradon/front-end.json` | local-asset |

So in the same frame 1264's warrior and mage are darker grey (their images) where the
realm's are the normal grey of the rogue; the rogue and the priest look the same. Side
by side, built from the layout's own textures: `build/ghidra/rq140/create-class-column.png`
(not committed; left the capture, right the same frame with `img_warrior` and
`img_mage` blended over the panel in the warrior and mage rects, the label pixels
re-blended by their estimated coverage, and the priest's edge over the panel). What a
still does not show: 1264's rogue lights and takes a click, where the realm's three
are inert. **Decided nothing at RQ-140 (Q91):** a look-and-feel difference, put to the
maintainer. The stat labels are proposed as their own item.

**Decides (RQ-142, Q91 (b), the maintainer's 2026-11-03, "Match 1264, Rogue
inert"):** the 1097 choice's create hides the warrior and mage buttons, so
`img_warrior` and `img_mage` draw in their rects, as 1264's after `0043ec90(2)`; it
hides `img_rogue` and `img_priest`, so the priest's down tile's edge blends over
the panel; the rogue stays fixed disabled, its normal grey tile, inert where 1264's
is a live NORMAL button (`0043ee10`, `00403b30`): race and class stay chosen from
the open (Q52). `make live-ko` matches the warrior and mage rects to their image
tiles at each size. The stat labels remain hidden (their own item).

**The stat labels after a priest click (RQ-141, 2026-11-03).** Re-read in the same
image and project (`0043ee10`, `0043ea10` and `0043ec90` decompiled again,
`-readOnly -noanalysis`, output under `build/ghidra/rq141/`, not committed; Load
`0043cd00` from RQ-134's output), with the layout above and the realm's capture of
the 1097 choice's create after RQ-142 (`make live-ko`,
`build/live-ko/front-end/1024x768.create.ppm`, sha256 `b0e081eb…`, not committed).
Not run, as above.

| Observation | Where | Label |
|---|---|---|
| **Load keeps the five labels in stat order.** Load builds the names `img_str`, `img_sta`, `img_dex`, `img_int`, `img_map` in turn and stores their nodes at `+0xe8`–`+0xf8`, the `text_*` values at `+0xfc`–`+0x10c` and the `area_*` tooltips at `+0x110`–`+0x120`, one loop of five | 1264 `0043cd00` | binary |
| **Each open hides all five.** Reset (`0043ea10`, from Load and SetChr) hides `+0xe8`–`+0xf8` (vtable `+0x3c` with 0) and writes the five `text_*` values (vtable `+0x7c`) from the player's `+0x734`, `+0x73c`, `+0x744`, `+0x74c` and `+0x754`, and `text_bonus` (`+0x128`) from `+0xb0`. The source's Reset calls UpdateStats, which does the same (`SetVisible(false)`, `SetStringAsInt` of strength, stamina, dexterity, intelligence, magic power and the bonus) | 1264 `0043ea10`; source `UICharacterCreate.cpp` `Reset`, `UpdateStats` | binary; source |
| **A class click shows its class's two.** `0043ee10` sets the visibility of `+0xe8`–`+0xf8` from five flags, all off but two per class: the warrior (101, 201) `img_str` and `img_sta`; the rogue (102, 202) `img_sta` and `img_dex`; the mage (103, 203) `img_int` and `img_map`; the priest (104, 204) `img_str` and `img_int`. `0043ec90` touches none of them, so after a Tuarek click and before a class click none shows. The source's `UpdateClassButtons` sets the same pairs (it also calls `SetStats`, which the 1264 binary's does not) | 1264 `0043ee10`, `0043ec90`; source `UpdateClassButtons` | binary; source |
| **Each label is a pink copy over a light one.** The five `img_*` are root strings (children 239–247 by twos), Arial 12 bold, colour 0xff8080, each drawn right after an unnamed light (0xe6e6e6) string with the same text ("Strength", "Health", "Dexterity", "Intelligence", "Magic Power") in the same rect (`img_sta`'s is one pixel shorter at the bottom, 135–156 against 135–157). So a shown label draws the same glyphs pink over the light ones; a hidden one leaves the light label | `UI_US/Ka_CharacterCreate_us.uif` (`4a1b072a…`) | local-asset |
| **The realm draws the light labels only.** The 1097 recipe hides all five `img_*`. In the capture the "Strength" and "Intelligence" rects (layout (690, 109) and (690, 191), the root at (0, −10)) are the light label blended over the panel tiles (`ui_el_charcreate01_us.dxt`, opaque): 471 and 629 pixels carry text, each fitting light 0xe6e6e6 over its panel texel by one coverage within 0.63 of 255, and all but 4 and 6 of the rest equal the panel within 2. The `text_*` values are empty (the layout's text) and `text_bonus` hidden | `build/live-ko/front-end/1024x768.create.ppm`; `games/moradon/front-end.json` | local-asset |

So in the same frame 1264 reads "Strength" and "Intelligence" in pink (0xff8080 at
full coverage: green and blue 102 below the light label's) and the other three light,
where the realm's five are all light. Side by side:
`build/ghidra/rq141/create-stat-labels.png` (not committed; top the capture, bottom
the same frame with pink blended over each text pixel of the two rects by the light
label's fitted coverage, as 1264's string drawn second would). Also on this frame,
not this item: 1264's Reset writes the five stat values and the bonus, which the
realm leaves empty and hidden (Q52, "stats hidden"). **Decided nothing at RQ-141
(Q92):** a look-and-feel difference, put to the maintainer.

**Decides (RQ-144, Q92 (b), the maintainer's 2026-11-03, "Pink Str/Int, as
1264"):** the 1097 choice's create draws `img_str` and `img_int`, so "Strength" and
"Intelligence" read pink over their light labels, as 1264's after `0043ee10(104)`,
and still hides `img_sta`, `img_dex` and `img_map`, as that call does; the stat
values stay empty and `text_bonus` hidden (Q52). `make live-ko` finds pink text in
the two rects and none in the other three at each size.

**1264's Create checks in 1298's order (RQ-172, 2026-11-04).** Read in the same
image (`0043a340` decompiled again, `-readOnly -noanalysis`, output under
`build/ghidra/rq172/`, not committed), for the 1097 choice's create, whose race
click now unchooses the class:

| Observation | Where | Label |
|---|---|---|
| **No class is code 9, row 1904.** MsgSendCharacterCreate (`0043a340`) posts, through ReportErrorCharacterCreate (`0043a820`, row 1904 for 9 under row 1901, §9.2), code 6 for an empty name (the length at the player's `+0x38c` under 1), 7 for no race (`+0x398` −1), 9 for no class (`+0x3a0` −1) and 10 for points left (`[this + 0x18] + 0xb0` above 0, taken as the bonus left, 1298's `+0xb0`), in that order, before its name letters (code 5); 1298's `005fffd0` has the same order (§9.15). `0043ec90` sets the class −1 on every race click (above), so after a Tuarek click and before a class click 1264's Create says row 1904 | 1264 `0043a340`, `0043a820`, `0043ec90` | binary |

**Decides (RQ-172):** the 1097 choice names `create_no_class` as row 1904 under
1901, the box its Create shows after a click on the chosen Tuarek; the realm checks
the empty name, the race, the class and the name's letters in that order, its points
still the fixed choice's (Q110).

## 10. Character create, end to end (RQ-001, 2026-11-04)

KO's whole create flow is written down as the character lane's contract in
`content/character-create.md`, with the evidence labelled and addressed there. It
covers:
- the login's nation byte and nation select (1298 `005f8340`, `005ed910`–`005edbc0`,
  `0060c830`);
- the race/class matrix, which no version uses to disable a race button (1298
  `006060f0`, 1264 `0043ec90`, 1097 `0043a190`);
- face 0..3 and hair 0..2;
- `NewChrValue`'s bases and the 10 bonus points per version;
- the client's checks and its refusal rows (`005fffd0`, `00600750`);
- Ebenezer's validation (`00491a02`, `IsValidName` `004a77eb`) and Aujard's call;
- the operator procedure's slots, nation check, Moradon start and empty inventory.

The decisions it needs are Q94–Q99.

### 10.1 A joint's rotation keys of length 0 (RQ-156, 2026-11-04)

Read statically in 1298's `KnightOnLine.exe` (`build/ghidra/audit-2026-09-19`,
`-readOnly -noanalysis`, `AuditReference.java recover`; sha256 `828ab0db…43a5e5`).

| Observation | Where | Label |
|---|---|---|
| The key load reads the count, then (above 0) the type and the rate, and the keys as they are (12 bytes each for type 0, 16 for type 1), copying the last key one past the end. It normalizes nothing | `00411950` | binary |
| The sampler takes i = trunc(frame / (30 / rate)) (`006a3c48`, 30.0), refuses nothing up to the count (i = count is key count − 1), and for the rotation (type 1 at `+0xd4`) copies key i when the blend `(frame − i × span) / span` equals 0.0 (`006a37dc`), and otherwise calls `0064d002(+0x2c, key i, key i + 1, blend)` | `00427640` | binary |
| `0064d002` is the slerp: the dot (`0064ce6e`) is negated with a sign of −1 below 0.0 (`006aaad8`, `006aaae0`); when 1 − dot ≤ 1e-5 (`006aaab8`) the weights are 1 − t and t; otherwise θ = atan2(√(1 − dot²), dot) and the weights sin((1 − t)θ)/sin θ and sin(tθ)/sin θ. For two zero keys it gives zero; for one zero key, dot 0 and θ = π/2, `sin((1 − t)π/2)·a + sin(tπ/2)·b`, of length below 1 | `0064d002`, `0064ce6e` | binary |
| The joint matrix builds the rotation from `+0x2c` with `0064cad6` when the joint has no orientation keys (`+0x144` < 1), the unnormalized quaternion matrix (2.0, `006aaad0`): 1 − 2(y² + z²) on the diagonal and so on, the identity for a zero quaternion | `00427a50`, `0064cad6` | binary |
| Every non-unit rotation key in the pinned tree is exactly (0, 0, 0, 0): `Chr/upc_ka_at.n3joint` 2185 (115 on each of 19 joints: clips 28–31, 93 and 94 whole, and the last key), `Chr/upc_el_ba.n3joint` 19 (the last key of each), no clip of either blending toward one | the pinned tree | local-asset |

**Decides (RQ-156):** a frame on or between zero keys converts as the identity
rotation, as KO draws it; a blend toward or from one is refused by name
(`tools/assetc/KO-CHARACTER.md`, "Rotation keys of length 0").

### 10.2 A clip at 0 frames a second (RQ-157, 2026-11-04)

Read statically in 1298's `KnightOnLine.exe` (`build/ghidra/audit-2026-09-19`,
`-readOnly -noanalysis`, `AuditReference.java decompile`; sha256 `828ab0db…43a5e5`).

| Observation | Where | Label |
|---|---|---|
| The clip-table load presets each clip's third field to 30.0 (`0x41f00000`) and reads the file's value over it with the other ten, checking none, then appends the 0x3c-byte record | `00410c00` | binary |
| The clip start sets the current frame (`+0x1dc`) to the record's start (`+0x10`) and the blend time from the record (`+0x2c`) or the caller | `0041be40` | binary |
| With no blend running, the frame tick adds the frame time (`006d3ab0`, §9.15) × the speed (`+0x220`) × the record's rate (`+0x18`) to the frame, raises it to the start, and only once it passes the end (`+0x14`) holds it on the end for the freeze time (`+0x1f4`, the clip start's `freeze` argument) or, that done, counts the clip played (`+0x1e4`) and stops it on the end (once), marks it for a re-blend to the start (flag bit 0: `+0x1d9`, which the next tick turns into a blend from `+0x2c` with the frame back on the start, only once the clip has been counted played) or wraps it by its length. The upper-body controller (`+0x1f8`) ticks the same way | `00418b20` | binary |
| So at rate 0 the frame stays on the start: the joints hold the start frame while the clip is current, and the clip is never counted played | `00410c00`, `0041be40`, `00418b20` | inference from the three |
| The pinned tree's one clip at rate 0 is `Chr/upc_el_rm.n3anim` clip 93, `breath_CrossBow0` (frames 4972–5012, strikes −4979.4 and 0, sound frames −4980 and 0); the 1298 tree has no other clip whose rate is outside 0 < rate ≤ 120 | the pinned tree | local-asset |

**Decides (RQ-157):** the clip table reads a clip at rate 0; a selected one converts
as its start frame held, as PQ-273's one-frame clips (n3e's held clip loops, KO's
never ends); a strike frame inside it, and a sound frame inside it where `ko_audio`
times sounds, is refused by name (`tools/assetc/KO-CHARACTER.md`, "Clips at 0 frames
a second"). The El Morad male
cooks.

### 10.3 A specialty's create dress (RQ-159, 2026-11-04)

Read statically in 1298's `KnightOnLine.exe` (`build/ghidra/audit-2026-09-19`,
`-readOnly -noanalysis`, `AuditReference.java decompile` and `recover`; sha256
`828ab0db…43a5e5`) and the 1264 client (`ko1264-unpacked.exe`, `build/ghidra/rq096`;
sha256 `61e9a086…136471`). The string literals were read from the files' bytes.

| Observation | Where | Label |
|---|---|---|
| The build looks each part slot's item (row `+0x34 + 4i`, i = 0..9, slot 2 the face through vtable `+0x28`) up as Item_Org item / 1000 × 1000 (`DAT_008186f4`) and, for an extension index below 24, Item_Ext item % 1000; it names the file with `006157b0(row, item, …, class, race)` and sets the part (vtable `+0x2c`). Without an Item_Org row it sets the looks row's part (slot 5: the hair, vtable `+0x24`). It clears both plugs, then attaches the row's `+0x2c` to plug 0 and `+0x30` to plug 1 (vtable `+0x30`), looking a plug's Item_Ext up with no bound on the index (`DAT_008186f8[index]`). The `< 24` test covers only the build's own lookup of a part's extension: every part and plug goes to `006157b0` with a name to fill, which indexes the 24 tables with the row's extension unbounded (below), so an index of 24 or more reads past them for either. The class is the build's (the chosen class, or the race's default before one), the race the player's | 1298 `005fd120` (arguments pushed at `005fd4ab`–`005fd4d2`) | binary |
| 1264's build does the same with its row by race, naming every item with the race's default class (`[ESP + 0x14]`, set from the race at `00439a23`–`00439a90`) | 1264 `00439970` (calls at `00439cd3`, `00439e5f`, `00439fa9`) | binary |
| The name: attach (`+0x42`) 0–4 is a plug (0, 1, 3 right; 2, 4 left; `".n3cplug"` at `006d8e70`), 5–9 a part (slots 0, 1, 5, 3, 4; `".n3cpart"` at `006d8e64`), 10–17 an icon (`".dxt"`). With a name to fill it first indexes the 24 Item_Ext tables with the row's extension (`+0x04`), unbounded, for every item (`DAT_008186f8[(byte)row[1]]`), and again for an icon to fill. A resource (`+0x30`) of 0 names nothing. A plug (or icon) needs an Item_Ext row and takes its resource (`+0x2c`) unless 0, else the Item_Org one, printed `"Item\%.1d_%.4d_%.2d_%.1d%s"` (`006d8e28`). A part takes Item_Org number / 10, and with class > 11 and race not −1, 0, 100 or 20 the switch at `00615be4` adds race × 1000 below the thousands (race 1: classes 101, 105, 106; 2: 102, 104, 107, 108, 111, 112; 3: 103, 109, 110; 4: 104, 111, 112; 11: 201, 205, 206; 12 and 13: 201–212); any other race or class loads the out string's pointer as the number (`00615e2a`). Number / 10000 % 100, unless `+0x54` is 2, is printed first with `"Item\%.2d_%.1d_%.4d_%.2d_%.1d%s"` (`006d8e44`) | 1298 `006157b0` | binary |
| 1264's name function is the same (its unbounded index `DAT_007acee8[(byte)row[1]]`), with the same strings (`0066e7d8`, `0066e7cc`, `0066e790`, `0066e7ac`) | 1264 `005d2a80` | binary |
| The player's part set, slot 1 (lower): while the current upper item is a robe it stores the item and sets the lower part to `""` directly, loading nothing; slot 0 with a robe clears a lower already set. A robe is the item's `+0x41`, except, at nation 2, an item whose number / 10^6 is 266 or 969 (1298) or 266 (1264) | 1298 `00467d50` (vtable `0x6a4198` + `0x2c`), `00462bd0`; 1264 `004680e0` (vtable `0x64926c` + `0x2c`), `00463350` | binary |
| The plug set puts a left-hand item of class (`+0x40`) 60 on the joint at `+0x110`, any other on `+0x10c`, the right hand on `+0x108` | 1298 `00467b30` (vtable `+0x30`) | binary |
| 1298's and 1264's rows resolve to files present in their trees, except the Wrinkle Tuarek's lower `2_6603_20_0.n3cpart`, which neither has and its robe upper (266001000, robe 1) leaves unloaded | the pinned tree, the 1264 install | local-asset |

**Decides (RQ-159):** each specialty's create dress is the chosen table's item
columns, resolved and checked by the cook as these functions draw them
(`content/character-create.md`, "How each item is drawn"); RQ-004 and RQ-005 draw it.

### 10.4 The create's stat arrows (RQ-173, 2026-11-04)

Read statically in 1298's `KnightOnLine.exe` (`build/ghidra/audit-2026-09-19`,
`-readOnly -noanalysis`, `AuditReference.java recover`; sha256 `828ab0db…43a5e5`)
and the 1264 client (`ko1264-unpacked.exe`, `build/ghidra/rq096`; sha256
`61e9a086…136471`); output under `build/ghidra/rq173/`, not committed. The source's
`UICharacterCreate.cpp` (`ReceiveMessage`, `UpdateStats`) matches what is read here.

| Observation | Where | Label |
|---|---|---|
| **Each arrow is found by its id.** After the race, class, face and hair buttons, ReceiveMessage compares the clicked node's id (`+0x30`, length `+0x34`) with `btn_str_right`, `btn_dex_right`, `btn_sta_right`, `btn_int_right` and `btn_map_right` (`006d8b0c`–`006d8acc`), then `btn_str_left` … `btn_map_left` (`006d8abc`–`006d8a7c`); a disabled or hidden state is never tested | 1298 `00604f90` | binary |
| **A right arrow spends a point while any is left, with or without a race or class.** With the points left (the create's `+0xb0`) at least 1 it adds 1 to the player's stat (`+0x830` str, `+0x838` sta, `+0x840` dex, `+0x848` int, `+0x850` MAP), takes 1 from `+0xb0`, and writes the stat's value text (`+0x134` str, `+0x138` dex, `+0x13c` sta, `+0x140` int, `+0x144` MAP) and `text_bonus` (`+0x160`) with vtable `+0x7c` (`CN3UIString::SetStringAsInt`, `std::to_string`, source `N3UIString.cpp`) | 1298 `00604f90` | binary; source |
| **A left arrow takes one back above the row's base, and needs the row.** It looks NewChrValue up by race × 10000 + class (`+0x48c`, `+0x494`; `00606950` at `006054fd`); with no row, as for class −1, no left arrow does anything. With a row, while the points left are below the bonus the last build gave (`+0xb4`) and the stat is above the row's (row `+0x24`.. str, sta, dex, int, MAP), it takes 1 from the stat, gives the point back and writes the two texts | 1298 `00604f90` | binary |
| **Every build resets the points.** The build looks the row up by race × 10000 + class, the class −1 taken as the race's default (1→101, 2→102, 3→103, 4→104, 11→201, 12→202, 13→204); with a row it copies the five stats to the player and the row's bonus (`+0x28`) to both `+0xb0` and `+0xb4`, before it returns for a race without looks; with looks it ends with `00605950`, which writes the five values (`SetStringAsInt`) and `text_bonus` from `+0xb0`. A race click builds when the race changes, a class click when the class changes | 1298 `005fd120`, `00605950`, `00604f90` | binary |
| **Each open writes them empty; the points are not reset.** The reset (`006066b0`, from Cancel `005ffb90`) runs `00605950` and then writes the five values and `text_bonus` empty. The constructor (`00603570`) zeroes `+0xb0` and `+0xb4`; neither Init (`005fab40`, which builds a new window) nor Cancel writes them otherwise, so points left at a Cancel stay for the next open, until a build | 1298 `006066b0`, `005ffb90`, `00603570`, `005fab40` | binary |
| **Create sends the values; points left are code 10.** After an empty name (6), no race (7) and no class (9), Create posts code 10 (row 1913 under 1901, `00600750`) while `+0xb0` is above 0, then checks the letters (5); the packet carries the five stats from `+0x830`, `+0x838`, `+0x840`, `+0x848` and `+0x850`, a byte each | 1298 `005fffd0` (the check `00600047`–`0060005f`, the stats `006006d5`–`0060070e`, sent at `0060071d`) | binary |
| **1264's arrows are the same, its row by race.** ReceiveMessage compares the same ids (`0066a270`–`0066a1e0`) with the same right-arrow rule; its left arrows look the row up by the race alone (`+0x398`, `0043ef80`), so they work without a class. Its SetChr (`00439970`, on a race change) copies the race's row's stats and bonus to the player (`+0x734` … `+0x754`) and `+0xb0`/`+0xb4`, then Reset (`0043ea10`) writes the values (`+0xfc` str, `+0x100` sta, `+0x104` dex, `+0x108` int, `+0x10c` MAP) and `text_bonus` (`+0x128`); a class click only marks its labels (`0043ee10`) and builds nothing | 1264 `0043dfc0`, `00439970`, `0043ea10` | binary |
| **The layouts.** 1298's `co_characterCreate_us.uif` has the ten arrows as plain buttons beside `text_str` … `text_map` (empty) and `text_bonus` (empty) in `Group_class`; 1264's `Ka_CharacterCreate_us.uif` the same, its `text_bonus` holding "20" and pink (0xffff7d81). Each table's rows give 10 bonus points ("Stats and bonus points", `content/character-create.md`); row 1913 is "There are stat points still remaining. " in both text tables | the pinned tree, the 1264 install | local-asset |

**Decides (RQ-173):** N3FE version 26 carries the arrows, the value texts, the
points text and the row's key (1298's race and class, 1264's race) as item 15; the
client keeps the points as these functions do and Create refuses points left with
`create_points_left` (row 1913 under 1901 in both recipes), then sends the values.
One edge differs: each open of the realm's create starts with no points (Q111).

### 10.5 The create's face and hair arrows (RQ-174, 2026-11-04)

Read statically in 1298's `KnightOnLine.exe` and the 1264 client as §10.4 does
(same projects and hashes); the new output (the player's constructor, Release and
the world's MyInfo handler) is under `build/ghidra/rq174/`, not committed. The
source's `PlayerMySelf.cpp` (`InitFace`, `InitHair`) matches what is read here.

| Observation | Where | Label |
|---|---|---|
| **The four arrows are found by their ids.** Init looks up `btn_face_left`, `btn_face_right`, `btn_hair_left` and `btn_hair_right` (`006d89dc`–`006d89ac`) into `+0x164`, `+0x168`, `+0x16c` and `+0x170`; ReceiveMessage compares the clicked node with them after the race and class buttons, Cancel and Create, and tests no disabled or hidden state | 1298 `00603850`, `00604f90` | binary |
| **Each arrow steps by one and clamps, no wrap, with or without a race or class.** The face (the player's `+0x7d8`) goes down to 0 and up to 3; the hair (`+0x7dc`) down to 0 and up to 2; neither the race (`+0x48c`) nor the class is read on the way. A changed face calls the player's vtable `+0x28`, a changed hair `+0x24` (InitFace and InitHair) | 1298 `00604f90` | binary |
| **The part is the looks' name with the index as two digits.** InitFace and InitHair build `{dir}{name}{index:02}{ext}` from the race's looks and set the face or hair part; a race whose looks name no hair sets an empty hair part | `ref/ko-src/src/Client/WarFare/PlayerMySelf.cpp` (`InitFace`, `InitHair`) | source |
| **They start at 0 and stay across opens.** The player's constructor (`00465410`, from `006113b0`) and its Release (`00465740`) write 0 to both; the world's MyInfo handler (`005c87c0`) sets them from the server. Init (`005fab40`), Cancel (`005ffb90`), the reset (`006066b0`) and the build (`005fd120`) never write them, and the build calls `+0x28` and `+0x24` with the current values, so a face or hair chosen before a Cancel is the next open's | 1298 `00465410`, `00465740`, `005c87c0`, `005fab40`, `005ffb90`, `006066b0`, `005fd120` | binary |
| **Create sends them.** The packet carries `+0x7d8` and `+0x7dc`, a byte each, after the class | 1298 `005fffd0` (beside the race and class, before the stats at `006006d5`) | binary |
| **1264's arrows are the same.** ReceiveMessage compares its four arrows (`+300`, `+0x130`, `+0x134`, `+0x138`) with the same steps and clamps (face 0..3 at the player's `+0x6e0`, hair 0..2 at `+0x6e4`) | 1264 `0043dfc0` | binary |
| **The parts.** The pinned tree has the face parts `…00` … `…03` and the hair parts `…00` … `…02` for each Moradon race's looks (the package's `faces` 4 and `hairs` 3); the Wrinkle Tuarek's looks name no hair part | the pinned tree, cooked by `tests/ko_player_races.py` (`content/character-create.md`) | local-asset |

**Decides (RQ-174):** N3FE version 27 binds the four arrows (`create_face_down`,
`create_face_up`, `create_hair_down`, `create_hair_up`) and carries each create
model's face and hair parts by index (item 8). The client steps and clamps as
`00604f90` does, keeps the values from open to open, draws the indexed parts and
sends the values. The range is `create.bin`'s per race rather than a constant; with
KO's one range for every race this is KO's behaviour (Q112).

### 10.6 The create's description text (RQ-175, 2026-11-05)

Read statically in 1298's `KnightOnLine.exe` and the 1264 client as §10.4 does
(same projects and hashes; Load `00603850` and MouseProc `00605bf0` recovered again,
1264's Load `0043cd00` and its MouseProc `0043eb00`, the create vtable `00648e00`'s
slot 20; output under `build/ghidra/rq175/`, not committed), with `objdump` for the
1298 UI manager's mouse pass (`005789c0`–`00578c4d`), `IsIn` (`004017b0`, 1264
`00401790`) and the references to `006dfe28`, and both clients' `Texts_us.tbl`
(decrypted, `ko_tbl`). The source's `CUICharacterCreate::Load` and `MouseProc`
match 1264. Not run (1298 is never run; 1264 reaches create only from a game
server's select).

| Observation | Where | Label |
|---|---|---|
| **Load sets the tooltips and the open text.** 1298's Load gives each stat area (`area_str`, `area_dex`, `area_sta`, `area_int`, `area_map` at `+0x148`–`+0x158`) rows 3219, 3202, 3220, 3210, 3201; the class buttons (`+0xec`–`+0xf8`, warrior, rogue, mage, priest) Karus rows 3217, 3215, 3212, 3213 (El Morad 3209, 3208, 3205, 3207); the Karus race buttons (`+0xdc`–`+0xe8`, `ka_at`, `ka_tu`, `ka_wt`, `ka_pt`) 3211, 3216, 3218, 3214 and El Morad's (`+0xcc`–`+0xd4`) 3203, 3206, 3204; and `text_desc` (`+0x15c`) row 6124 for Karus, 6125 for El Morad. 1264's Load gives the same rows, its areas in the order str, sta, dex, int, map (`+0x110`–`+0x120`), its four race buttons at `+0xb8`, its class buttons at `+0xc8`, `text_desc` at `+0x124` (pushes `0x17ec`, `0x17ed`) | 1298 `00603850` (`00603c5a`–`00603c9b`, `006043cf`–`006043ef`, `00604b25`–`00604c5e`, `00604dfe`, `00604e6b`); 1264 `0043cd00` (`0043d348`–`0043d3cf`, `0043cea5`, `0043cef8`) | binary |
| **Both MouseProcs colour the text and take the tooltip under the pointer.** Each sets `text_desc`'s colour (`+0xcc`) to `0xffffff00`, then runs three loops, the stat areas, the class buttons, the race buttons (1298: the player's nation's, `00818794 + 0x490` 2 the El Morad four), each stopping at the first node whose rect holds the pointer and taking its tooltip (`+0x3c`); a later loop's hit replaces an earlier's. `IsIn` compares the rect only (left ≤ x ≤ right, top ≤ y ≤ bottom, `+0x80`–`+0x8c`), so a disabled, hidden or covered button still gives its tooltip | 1298 `00605bf0` (`00605c90`–`00605da4`), `004017b0`; 1264 `0043eb00`, `00401790` | binary |
| **1264 writes the text only on a hit.** Each hit calls the string's SetString (vtable `+0x78`) at once; off every node nothing is written, so the text stays the last tooltip, or Load's row 6124 from the open on. Its create Init (`00439550`) builds and loads a new UI each time (`operator new(0x144)`, vtable `+0x5c`, `+0x8`), so each open starts from row 6124 | 1264 `0043eb00`, `00439550`; source `CUICharacterCreate::MouseProc` | binary; source |
| **1298 writes it every pass: the hover, else the chosen class, else the chosen race, else nothing.** It builds a local string from `006dfe28` (empty), assigns the hit's tooltip, and when the string is still empty assigns the tooltip of the race button in state 3 (DOWN), then that of the class button in state 3 (an assign, not an append: `_Grow` to the tooltip's length and a copy to the start, `00605f09`–`00605f2e` and `00606039`–`0060606e`), so the chosen class's text wins over the race's and there is no join. It then sets `text_desc` to the string (`00606073`, vtable `+0x78`) whatever it holds | 1298 `00605bf0` (`00605da9`–`00606080`) | binary |
| **So 1298 never shows Load's row.** The UI manager's mouse pass (`005789c0`) calls each child's MouseProc (`00578b96`) without testing its visibility (only a focused window of style `0x100` takes the pass alone, `00578a16`–`00578a39`), and 1298's MouseProc tests only that `text_desc` exists, so from the select's first tick after Load (`005fab40`) the hidden create writes an empty text; while it shows, the pass runs before the frame draws (§9.15). Load's 6124 could last at most until that first pass | 1298 `005789c0`–`00578c4d`, `00605c76`–`00605c86` | binary |
| **`006dfe28` is the empty string.** It lies past the raw data of its section (`0x6dfe28` − `0x6d3000` = `0xce28` > `0xce00`), so it is zero at load; 1,658 references read it (string copies, pushes, `mov al`) and none stores to it. So 1298's build (`00605950`), which sets `text_desc` and `edit_name` from it, empties both: a race or class click that builds clears a typed name (RQ-135's question) | the 1298 image's section table and references | binary |
| **The rows.** Both tables hold row 6124 "\n\nKarus Character Window." and 6125 "\n\nEl Morad Character Window. ". The pinned (1298) table's Karus race row 3214 (the Puri Tuarek) is Korean (CP949); its others are English. The 1264 install's table holds "Unconfirmed nation" at 3201 (the MP area's row in both clients, 1298's table "This is the stat that affects the character's power for magic attacks.  "), English at 3214, "Arch Tearek" at 3211, and CP949's right single quotation mark (`A1 AF`) in "ally's" in 3207, 3209 and 3217 | `Data/Texts_us.tbl`, the pinned tree and the 1264 install | local-asset |
| **The layouts.** 1298's `text_desc` is in `Group_race` (33, 268)–(178, 554), Batang 11, colour `0xfffdf8d0`, style 0 (wrapped); 1264's (754, 357)–(952, 630), Arial 11, `0xffc0c0c0`, centred. Neither colour is drawn: MouseProc sets yellow before the first frame | the pinned tree's `co_characterCreate_us.uif`, the 1264 install's `Ka_CharacterCreate_us.uif` | local-asset |

**Decides (RQ-175):** N3FE version 28 carries the description text as item 16: the
colour, the rest (`keep`, 1264's: the text stays as the last hover left it, row 6124
from each open; `chosen`, 1298's: the chosen class's tooltip, else the chosen race's,
else nothing, every frame, so no open text) and each stat area's, class button's and
race button's tooltip in KO's loop order, from that client's table. The client runs
the pass each frame create shows, with the rects where that frame draws them. The
earlier reading in `content/character-create.md` (the race's text joined with the
class's) was wrong: 1298 shows one or the other, the class's first. Two texts the
realm's fonts cannot draw: CP949's apostrophe is drawn as ASCII's (Q113), and the
1298 recipe gives the Puri Tuarek no tooltip (Q114).

### 10.7 The create model's dress: the hand joints and the plug scale (RQ-176, 2026-11-05)

Read statically in 1298's `KnightOnLine.exe` as §10.3 does (same project and hash;
the table reader `00635be0` decompiled again, output under `build/ghidra/rq176/`,
not committed), with the source's `CPlayerBase::PlugSet` and `CN3Chr`. Not run.

| Observation | Where | Label |
|---|---|---|
| **The looks row's joint columns.** The table reader sizes each column by its type: 1 and 2 one byte, 3 and 4 two, 5, 6 and 8 four, 7 (a string) `0x10`, the string object's size. UPC_DefaultLooks's row (the player's looks at `+0x274`) is a u32 key and 16 strings (`+0x04`–`+0x103`), then the columns from 17 on, four bytes each: column 17 at `+0x104`, so the plug set's `+0x108`, `+0x10c` and `+0x110` (§10.3) are columns 18, 19 and 20, the source's `iJointRH`, `iJointLH` and `iJointLH2` (a shield's, "the left forearm") | 1298 `00635be0`, `00467b30`; source `GameDef.h` `__TABLE_PLAYER_LOOKS` | binary; source |
| **The plug's scale is its own scale y × the character's height / 1.8.** `PlugSet` scales a plug uniformly by `Height() / 1.8 × plug.Scale().y / chr.Scale().y`, `Height()` being `m_vMax.y × m_vScale.y`, so the character's scale cancels; `FindMinMax` sets `m_vMax` from the joint positions alone (the largest joint y), not the meshes | 1298 `00467b30` (vtable `+0x30`); source `PlayerBase.cpp` `CPlayerBase::PlugSet`, `N3Chr.h` `Height`, `N3Chr.cpp` `CN3Chr::FindMinMax` | binary; source |
| **The rows.** The pinned tree's and the 1264 install's looks rows for races 1–4 and 11–13 hold 12, 7 and 5 in columns 18, 19 and 20, joints of each race's `Chr/` skeleton; the 1298 Puri Tuarek priest's mace hangs on joint 12 and its shield (Item_Org class 60) on joint 5 | the pinned tree's and the 1264 install's `UPC_DefaultLooks` | local-asset |

**Decides (RQ-176):** N3FE version 29 carries each create model's dresses (item 8,
`content/front-end.md`): the parts and plugs `ko_create.dress` resolves (§10.3), the
right hand's plug on column 18's joint, the left's on column 19's, a class-60 left
item on column 20's, each scaled by the model's height as `PlugSet` scales it (the
largest joint y of the bind pose, as `ko_appearance` takes `Height()`; `FindMinMax`
ticks the current frame, which the breath clip's first frame barely moves). A dress
with a helmet is refused until the order of 1298's build and `InitHair` is read
(Q115).

## Not re-derived here

Scheduled events (national war, monster challenge), launcher/patcher UX, hack-tool
checks — catalogued; no architectural impact beyond what the priorities file already
notes.

## Questions this closes or changes

| Q | Outcome |
|---|---|
| Q6 | Presets stand; KO = additive 0–15 % global, untimed, announced at set + login. Add late-joiner display of active presets. |
| Q13 | **In-game notice is v1**: `notice` admin operation → chat-type-public yellow line; CD countdown uses it once per minute; plus a MOTD/notice panel on world entry. |
| Q14 | **Add `mute` (timed) in v1**; defer attack-disable. |
| Q10 | Wording fixed (above). |
| Q21 | Unchanged (KO's `+monsummon` is untimed; ours gets a bounded duration). |
| Q71 | §8.1: 1097, the client whose files the package cooks, plays the hall as (a) does, so (a) is KO's behaviour; its three remaining details aligned (RQ-075). §8.3 (RQ-086): 1298's (b) read further (its default looks, every character ticked, the spot and info without the pointer) and carried as data, the loop front-clip mode. |
| Q70 | §8.2 (RQ-077): 1097's select arrows play sound 2501 (`char_select_turn.wav`) for each turn they start; the realm plays it. 1097's Karus front-end layouts name no button sounds; its sound switch is `[Sound] Enable`. |
| Q57 | §9 (RQ-078): 1097's login plays sound 35, `bgm_login.wav` (21.67 s), restarted every 21.66 s; 1298's plays `Intro_Sound.mp3`. RQ-083: 1097's game-server login answer replaces it with sound 20003, `bgm_el_battle.wav`, looping, before select; create leaves it; the 1097 choice plays both (N3FE version 5). |
| Q73 | §9 (RQ-078): what differs per client on the five screens, and which of it the format expresses; the realm owner's choice is package data the cook checks. §9.2 (RQ-085): the 1097 choice's layouts are the 1264 install's, its message box and loading 1264's. |
| Q85 | §9.4 (RQ-108): 1264 shows the login's copyright line, at `((W − w) / 2, H − h − 20)`, only while its login bar is hidden: from a login press until a failed answer, and with the server list after a success; the 1097 choice does the same (N3FE version 12's `login_closed`), the bar hidden while the Discord flow runs. |
| Q87 | §9.6 (RQ-109): 1298's select is the `co_CharacterSelect_us.uif` bar, centred 10 px above the bottom edge: Start is the centre click, Create opens create in the slot in focus or the first empty one (row 7675 when none), Delete says row 1501, Exit asks row 1502 yes or no, Back returns to the server list, and both arrows always draw; the 1298 recipe draws the bar (N3FE version 13) and keeps the realm's Exit, Back and arrows. §9.7 (RQ-111): 1298's Exit box is `El_MessageBox_us.uif` with Yes and No (labelled OK and Cancel), ENTER Yes and ESC No, Yes quitting; the 1298 recipe asks so (N3FE version 14). §9.8 (RQ-115): 1264's select Exit (`bt_exit`, `00444e60`) asks the same, row 1502 yes or no in its `El_MessageBox_us.uif`; the 1097 choice asks so too. RQ-116: 1264's select presses `bt_exit` for ESC (`004454e0`), and the 1097 choice's ESC asks so (N3FE version 15, `select.escape`). §9.9 (RQ-117): 1298's select ESC presses no button (`00607810` → `005faad0`): it skips a path and at rest does nothing; RQ-119: the 1298 recipe's ESC does the same (N3FE version 16, `select.escape` `none`), the maintainer's choice. §9.12 (RQ-112): 1298's Back sets its login procedure's `+0x21`, whose Init connects, asks for the server list and hides the bar (`005f68e0`), 1264's the same (`+0x35`, `005bd9b0`, its line hidden too); the realm's Back, with a stored session, already reaches the realm list through the session's login; the 1298 recipe hides the bar from the click (N3FE version 17, `select.back` `realms`), and the 1097 choice keeps the realm's; RQ-123: the 1097 choice names `realms` too, its line hidden with the bar after a Back, as 1264's. §9.13 (RQ-113): no KO select hides an arrow (1298, 1264 and 1097 draw both at the ends of the row); the 1298 recipe draws both (N3FE version 18, `select.arrows` `draw`), and the 1097 choice keeps the realm's `hide`; RQ-124: the 1097 choice names `draw` too, as 1264's draws both, the maintainer's choice. §9.14 (RQ-114): 1298's Create from an occupied slot flies the camera to the first empty slot by paths 2–7 (`005ff920`), its create shown at once; the 1298 recipe cooks paths 6 and 7 and plays the fly, opening the realm's create on the arrival. §9.15 (RQ-125): 1298's create is the select's window `+0x388`, `co_characterCreate_us.uif` (row 2's 121st string, `005fab40`), three panels that slide in over the hall (`00606450`), the new character at the camera's slot turned 213°, 143° or 283° once a race is chosen (`005fd120`); the 1298 recipe draws it over the hall from the click, the fly behind it (N3FE version 19, `select.create` `hall`), its panels where the slides end. RQ-126: the panels slide in as `00606450` moves them (N3FE version 20, create's `slide`), the slide ending on Group_race's arrival, which at a frame time under about 0.2 s leaves Group_class at 48 or 49 and Group_name 29 above the bottom. RQ-127: 1298's Create (`005fffd0`) refuses a create with no race (row 1908) or class (row 1904) and sends the source's `WIZ_NEW_CHAR`; after a Cancel mid-flight its camera flies on to the empty slot, the select at rest on the slot it left; the 1298 recipe keeps race and class chosen from the open (Q52) and its Cancel's camera put on the slot. RQ-130 (option (b), the maintainer's): a race click unsets the class and builds the character at the camera's slot only on a change (`00604f90`, `005fd120`), the chosen race and class drawing down (`006060f0`, `006062d0`); the 1298 recipe waits for both clicks (N3FE version 21), Create saying rows 1908 and 1904, and the 1097 choice keeps them chosen. RQ-133: 1298's race click hides the class buttons the race cannot take for their images, which lie under the buttons, and the images of the classes it can (`006060f0`), every one shown again at each open (`00605950`, `006066b0`); the 1298 recipe draws the images and marks those four nodes drawn until the race (N3FE version 22, `until_race`). |
| Q86 | §9.5 (RQ-110): 1298's login draws no copyright line (its login is the intro layout, no `Text_Rights`) and hides its bar from a press until a failed answer; the 1298 recipe hides the line and, like every layout now, its bar while a login is under way. |
| Q82 | §9.2 (RQ-101): 1264's logo procedure runs first, once a process: three groups fading in, holding and fading out on black over 12 s, `Snd\bless.wav` from 1 s faded out over 4 s from the third, any key skipping to the login, the cursor hidden; the 1097 choice shows it (N3FE version 9). §9.3 (RQ-106): KO draws every front-end layout unscaled, placed by the screen's size (the login on the bottom edge, the server list at the top-left, the select's buttons on the bottom edge, create, loading, the message box and the logo centred), the 3D scenes filling the screen; the realm does the same (N3FE version 11). |
| Q80, Q81 | §9.2 (RQ-085): 1264 picks the loading layout by the server's war-victor byte (`005f9a30`) and shows each message with the caller's title; the realm has neither, so it draws the no-victor layout and an empty title. §9.2 (RQ-102): 1264 titles its login answer's and its create failures; the 1097 choice gives the realm's matching messages KO's title and wording (N3FE version 10) and leaves the rest untitled. |
| Q75 | §9.1 (RQ-096): 1264's login tick keeps 1097's timer (`007ac9d0`, written only by the tick), so in both a return to the login is silent until it passes 21.66 s. RQ-096 made the realm do the same; RQ-105 (maintainer) starts the track at once on every entry instead and keeps the carried clock off by default. |
| Q89 | §9.16 (RQ-134): 1264's chosen race and class draw `UI_STATE_BUTTON_DOWN` (`0043ec90`, `0043ee10`), the layout's sunken pink tile; the 1097 choice's fixed `on` drew the raised pink on tile. RQ-138 (option (b), the maintainer's): the 1097 choice's Tuarek and priest are the recipe state `down` and draw their `BS_DOWN` tiles, still chosen from the open. |
| Q90 | §9.16 (RQ-134): the 1264 layout's Puri Tuarek has an untextured `BS_DISABLE` image, so the realm's fixed disabled drew only its label; 1264 never disables a race button (`0043ec90`). RQ-139 (the maintainer's): the 1097 choice leaves it unfixed and unbound, drawing its `BS_NORMAL` grey tile, inert as the other race buttons. |
| Q91 | §9.16 (RQ-140): after a Tuarek and a priest click 1264 shows `img_warrior` and `img_mage` (darker grey tiles) for the warrior and mage buttons, the rogue a live NORMAL button and the priest down (`0043ec90`, `0043ee10`); the 1097 choice drew the warrior, rogue and mage fixed disabled in their normal grey tile. RQ-142 (option (b), the maintainer's): the 1097 choice hides the warrior and mage buttons for their images and hides `img_rogue` and `img_priest`, the rogue still inert, race and class still chosen from the open. |
| Q92 | §9.16 (RQ-141): after a priest click 1264 shows `img_str` and `img_int` (`0043ee10(104)`), pink copies drawn over the light "Strength" and "Intelligence"; each open hides all five (`0043ea10`). The 1097 choice hid all five, so its labels were all light. RQ-144 (option (b), the maintainer's): the 1097 choice draws `img_str` and `img_int` and hides the other three, the stat values still empty. |
| Q93 | §9.15 (RQ-143): 1298's create has a cream (`*_01`) and a cyan (`*_02`) copy of each stat label in one rect, cream drawn last; each open and build shows all ten (`00605950`), and a class click hides its class's two cream ones (`006062d0`), so after the priest click "STR" and "INT" read cyan; a click on the same race keeps them so (no build). The 1298 recipe drew all five cream throughout. RQ-145 (option (b), the maintainer's): the 1298 recipe names `str_01` and `int_01` until a class is clicked (N3FE version 23, `until_class`), cream again at each open and on the race click that builds, cyan kept on a click on the chosen race. |
| Q72 | §9.10 (RQ-120, correcting §8.2): 1097 and 1264 (and 1298, RQ-121) clear the UI flag from the select request until the main procedure, so no arrow, ESC or button reaches the select during the start clip; only the tick's ENTER skips it. RQ-121 (the maintainer) makes the realm's ESC and Exit do nothing then too. §8.1 (RQ-076): 1097 starts the clip on the server's answer and takes ENTER in any state; the realm starts on the press, at rest only. §8.2 (RQ-077), as RQ-120 corrects it: DoJobLeft and DojobRight would start a turn from state 3, but no arrow reaches them during the clip; the realm ignores them then too. |
