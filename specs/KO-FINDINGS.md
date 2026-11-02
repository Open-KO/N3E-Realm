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
| **1298 differs.** It turns through recorded camera paths, `ChrSelect\Data\ka_center_left_camera.n3camera`, `ka_center_right`, `ka_left_center`, `ka_right_center`, `ka_left_right`, `ka_right_left` and `ka_lording_camera` (and `el_*`), loaded by `005fa670`. Its turning states (`005fe5b0` cases 1, 2, 6) wait until the object at `+0x1a4` has reached its last frame (`+0x110` equals `+0x10c`). Not read further | `005fa670`, `005fe5b0`; strings `006d8420`–`006d85cc` | binary |

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
press, at rest only).

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
| **1298 does not.** No `Intro\` string is in `KnightOnLine.exe`; its login is the source's `CGameProcLogIn_1298`: a UIF intro, `UIs_us.tbl`'s `ka_login_intro_us.uif` or `el_login_intro_us.uif` (a random nation), under `co_login_us.uif` | strings of `KnightOnLine.exe`; `GameProcLogIn_1298.cpp` `Init`; `Data/UIs_us.tbl` | binary (strings); source; local-asset |
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
| 1298's select: per-race `upc_ka_<race>` joints and clips, clip 1 looping on the character in front without the pointer, start clip 2 once with 0.6 s, the turns through recorded `.n3camera` paths, no rotate sound (§8, §8.2). Its lights are `ChrSelect\ka_light_0–2.n3light` (strings); no `ka_chairs` or `ka_cave` name is in the binary, so which hall mesh it draws was not read (RQ-012) | §8, §8.2; strings of `KnightOnLine.exe` | binary |
| 1097's select: `ka_chairs.n3shape`, `ka_light_0–2`, the `upc_ka_*_<class>` files and their hover, rest and start clips, the turn about `at`, sound 2501 on each turn (§8.1, §8.2). These are the files and behaviour the package cooks today | §8.1, §8.2 | binary |
| `ChrSelect/`: 246 files are identical in all four installs. 1298 adds the per-race `upc_ka_<race>.n3joint`/`.n3anim` and the `Data/ka_*_camera.n3camera` paths. 2145 and Steam keep those, rewrite every `.n3anim` (other bytes: the 2145 clip format, `tools/ko-reference/anim_2145.py`) and add `Data/camera1–13.n3camera`, `ka_light_3.n3light` and `choice_upc_kurian` (the Kurian race); Steam adds further clips (`upc_ka_wt_ma_destan1`, `upc_ka_wt_ma_zion`, `upc_ban_zion`, `hotkey_zion_kyran`, …) and drops `char_select.uif` | `ChrSelect/` in each install (sha256 of every file) | local-asset |
| 2145 keeps `UI/` in its pack (`UI/ui.hdr`, 5,788 entries; `tools/ko-reference/pack_2145.py`). Its `UIs_us.tbl` (row 1) names `ui\co_login.uif`, `UI\re_CharacterCreate.uif`, `ui\ka_CharacterSelect.uif`, `ui\co_Loading.uif`, `ui\ka_loading.uif`, `ui\co_MsgBoxOk.uif`, `ui\re_login_intro.uif`, `ui\co_login_intro_sub.uif`, `ui\re_characterselect.uif`, `ui\re_nation_Select.uif` and `ui\co_introduction.uif`. Its `co_login_us.uif` and `ka_characterselect_us.uif` are byte-identical to 1298's; `ka_charactercreate_us.uif`, `ka_loading_us.uif` and `co_msgboxok_us.uif` differ, and `ko_hud.parse` refuses `ka_loading.uif` and `co_msgboxok_us.uif` (`UI version header`) | the 2145 install's `UI/ui.*`, `Data/UIs_us.tbl` (`tools/ko-reference/tbl_2145.py`) | local-asset |
| 2145's sounds are Ogg Vorbis: `Snd/bgm_login.ogg`, `intro_sound.ogg`, `Intro_Old_Sound.ogg` (and an `Intro_Old_Sound.mp3`), `char_select_turn.ogg`. Which its screens play was not read (the exe is packed) | the 2145 install's `Snd/` | local-asset |
| Steam keeps `UI/` and `Snd/` in packs that are not 2145's: each `.hdr` starts with the word 200,000 (`40 0d 03 00`) and a second word before the first name, which the 2145 reader refuses | `UI/ui.hdr`, `Snd/snd.hdr` | local-asset |
| The Steam dump names `CGameProcIntro`, `CGameProcIntroChrSelect`, `CUILoginIntro`, `CN3OggDecoder`, `CBGMManager`, `Snd\Intro_Sound.mp3`, `Snd\Intro_Old_Sound.ogg`, `ChrSelect\Data\camera1–13.n3camera` and `ChrSelect\ka_light_%d.n3light`; its login runs through `Launcher.exe` (WebView2) and Steam (`steam-rea/README.md`). Nothing of its behaviour was read | strings of `KnightOnLine.unpacked.exe` | binary (strings) |

What the engine expresses as data today (N3FE version 4; version 5, RQ-083, adds the
PCM tracks and the restart period) and what it lacks,
per screen. A choice can be offered only when every row it needs is data:

| | Data today | Not yet |
|---|---|---|
| Login scene | the 1098 scene (1097's): camera, lights, the model's one clip and plugs, the moon quad | 1298's UIF intro (`ka_login_intro_us.uif`, wrapped UVs; spec 11 left it out), 2145's `re_login_intro`, Steam's intro procs |
| Layouts | UIF trees `ko_hud.parse` reads (1298's; 2145's `co_login`, `ka_characterselect`), bindings, moves, hidden, states | 1097's UIF version; the 2145 versions it refuses; Steam's pack |
| Select hall | meshes, lights, slots, the turn about `at` with per-slot ends, the spot's rate, hover/start/rest clips with blend times, plugs | 1298's loop on the character in front (a front-clip mode), recorded camera paths (`.n3camera`), per-race default looks (RQ-005); 2145's `.n3anim` format (convertible: `anim_2145.to_1298`) |
| Music | MPEG-1/2 Layer III tracks per screen, looping or once (1298's `Intro_Sound.mp3`); since version 5 (RQ-083) 16-bit PCM tracks and a restart period (1097's `bgm_login.wav` every 21.66 s, `bgm_el_battle.wav` looping) | Ogg Vorbis (2145, Steam); 1097's process-lifetime login timer (Q75) |
| Sounds | a sound-table id bound in `audio.bin` (1097's turn sound 2501) | 2145's Ogg `char_select_turn.ogg` |
| Text | six strings, KO's UIF texts as they are | KO's text tables for them (RQ-013) |

**Decides (RQ-078):** today's package is the "1097" choice: 1097's login scene and
select hall, with two parts still 1298's. Its layouts are 1298's `UI_US` files,
because `ko_hud` cannot read 1097's UIF version. Its music is 1298's
`Intro_Sound.mp3`, because the format carries only MPEG frames and 1097's track is a
WAV. *RQ-083:* the music is now 1097's (N3FE version 5): `bgm_login.wav` on the
login and the realm list, restarted every 21.66 s, and `bgm_el_battle.wav`, looping,
on select and create, as the rows above read them. A "1298" choice needs the front-clip mode, the camera paths, 1298's UIF intro
and 1298's looks. A "2145" choice needs a reader for its UIF versions and an Ogg
decision. Steam is not cookable yet: the packs are not readable, the exe is protected,
and the install changes with every Steam update. The follow-up items are filed under
RQ-078.

**RQ-085 (open, maintainer's question):** 1097's layouts are readable (one
32-bit child count, no string line spacing), but as 1097 draws them on an English or
Korean Windows, the login, create and message box carry Korean labels in their art,
and 1097 has no English layouts to draw instead. Its select and loading carry none,
but its select has no back button, which the realm's select requires (`back`). The
"1097" choice therefore keeps 1298's English `UI_US` layouts until the maintainer
decides whether to ship 1097's art as it is.

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
| Q71 | §8.1: 1097, the client whose files the package cooks, plays the hall as (a) does, so (a) is KO's behaviour; its three remaining details aligned (RQ-075). |
| Q70 | §8.2 (RQ-077): 1097's select arrows play sound 2501 (`char_select_turn.wav`) for each turn they start; the realm plays it. 1097's Karus front-end layouts name no button sounds; its sound switch is `[Sound] Enable`. |
| Q57 | §9 (RQ-078): 1097's login plays sound 35, `bgm_login.wav` (21.67 s), restarted every 21.66 s; 1298's plays `Intro_Sound.mp3`. RQ-083: 1097's game-server login answer replaces it with sound 20003, `bgm_el_battle.wav`, looping, before select; create leaves it; the 1097 choice plays both (N3FE version 5). |
| Q73 | §9 (RQ-078): what differs per client on the five screens, and which of it the format expresses; the realm owner's choice is package data the cook checks. |
| Q72 | §8.1 (RQ-076): 1097 starts the clip on the server's answer and takes ENTER in any state; the realm starts on the press, at rest only. §8.2 (RQ-077): 1097's arrows also start a turn from state 3, during the start clip; the realm ignores them then. |
