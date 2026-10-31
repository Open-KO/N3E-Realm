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
