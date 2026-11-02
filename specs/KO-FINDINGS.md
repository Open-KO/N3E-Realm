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
the arrows while it turns. It plays no rotate sound. 1097 plays its sound object
`+0x18` there. Whether one is loaded, and which, was not read (1298 plays none;
`content/front-end.md`).

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
| Q72 | §8.1 (RQ-076): 1097 starts the clip on the server's answer and takes ENTER in any state; the realm starts on the press, at rest only. |
