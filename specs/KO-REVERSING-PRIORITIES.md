# KO reversing priorities for the Realm architecture

Scope: only what the **architecture** (ops, auth, admin, deploy, Bot) depends on. Gameplay
fidelity is the parity loop's ordinary backlog and is not listed here.

**This is the pre-phase (roadmap "P").** The existing `n3e` parity loop takes the P1 rows,
then P2, as queue items (`docs/parity/queue.jsonl`), records evidence in `n3e/docs/ko/`
per that repo's rules, and the findings feed back into `architecture.md` and these specs
before the migration (spec 09). Each row's "Needs" column is the queue item's acceptance
criterion. Most of this is already catalogued in
`n3e/docs/ko/` — the column "Catalogued" points there. "Needs" says what's still missing
for us: binary confirmation, a decision, or an n3e feature.

Priority: **P1** blocks a spec decision; **P2** shapes a spec but has a safe default;
**P3** nice to have.

| P | KO surface | Why the architecture cares | Catalogued in n3e | Needs |
|---|---|---|---|---|
| P1 | **Rate events** — `/money_add N`, `/exp_add N`, `+user_bonus` → AI opcode `44`; issuer premium flag | Defines what `/drop` and `/event` in the Bot (spec 05) and `world.drop` / `world.event` (spec 03) actually do. **Q6.** | `operations-persistence.md` "Operator command mapping" (`absent` in n3e) | (a) confirm in Ebenezer/AI binaries the exact multiplier semantics: scope (realm-wide vs zone), duration (until `/off`? until restart?), stacking, whether premium is additive; (b) decide whether n3e implements a live `rate.set` admin operation, or whether `/drop` is dropped from the Bot. |
| P1 | **Notices** — console plain text → broadcast; `/permanent`, `/offpermanent`; `Notice.txt` ≤ 20 × 127 sent as `2e` at game start; `/reload_notice` | `realm.notice` today goes **only** to Discord. KO players expect restart warnings **in game**. Decides whether `POST /v1/realm/notice` also needs an in-game broadcast path (an n3e `AdminRequest` operation `notice`) and whether a login-time notice (MOTD) exists. | `identity-social.md` §"King, rename, rankings, notices"; KOF-0058 | Confirm the `2e` payload shape and the client's display (scrolling banner vs chat line) so the n3e client renders restart warnings where KO players look. Decide: in-game notice in v1 or not. |
| P1 | **`/serverdown N`** — per-minute countdown notices then `/down`; `/down` closes ≤ 1500 sessions at 1 s each | This *is* our drain + restart (spec 03 drain, spec 06 force path with a 2-minute warning). KO's UX is the baseline mods will compare against. | `operations-persistence.md` (`/down` partial, `/serverdown` absent) | Confirm the notice text/cadence and what the client shows at the final close (does it return to login with a message, or hard-disconnect?). Feeds the "update via launcher" exit path (spec 04, Q10). |
| P1 | **Account authority byte** — 0 manager, 1 user, 11 muted, 12 attack-disabled, 250 limited manager, 255 blocked; operator packet `40` subs 1–9 (go-to, forbid-connect, mute, cut-off, forbid-user timed, summon, attack-disable); `+forbiduser`, `+forbidconnect` → DB `4f` | Our ban model (spec 02: `banned_at`, `banned_until`, kick) should map onto what KO mods already understand: **timed forbid**, **mute**, **attack-disable** are distinct states. Today spec 02 has only ban/kick. | `operations-persistence.md` "Operator surfaces"; investigation D (moderation inter-server) | Decide whether `mute` and `attack-disable` are v1 account states (they'd be `account.mute` permissions + n3e support) or deferred. Confirm whether KO's forbid is by account or by character (affects whether our ban cascades to all characters — it should). |
| P2 | **`/kill <name>`** (close session), kick-out logout `51` | Our `account.kick`. Confirm KO's client-side behaviour on kick (message shown?) so n3e's client can mirror it. | `DISPATCH.md` `51`; `operations-persistence.md` | Low effort: one decompile for the client's handling of `51`. |
| P2 | **Server list `f5`** (address, name, user count), **news `f6`**, **version `2b`** | We have one realm, so `f5` is moot — but **user count** and **news** are exactly what the Launcher (spec 04) could show, and `/status` (spec 05) shows. Decides whether the manifest carries a "news" field and whether `status.players` is exposed publicly (DDoS consideration: it's a free attack-success metric). | `identity-social.md` | Decision only: expose player count publicly or not. Recommend **not** on the public path; Discord `/status` is role-gated anyway. |
| P2 | **Login/version handshake** — `2b` version 0x512, 8-byte key, opcode offset | Irrelevant to our wire (TLS), but KO's **version-mismatch UX** ("Please run the patcher") is the model for our `CONTENT`/`VERSION` exit (spec 04 exit 3 / Q10). | `identity-social.md`, `operations-persistence.md` "Configuration, timers and shutdown" | Confirm the client string/dialog on version mismatch; mirror the wording. |
| P2 | **Speed/warp checks, packet-count timers** (DB-agent timer 400 = 120 s packet count; >10 packets < 0.1 s apart → disconnect) | Calibrates spec 01 defaults (`REALM_IP_CONNECT_RATE`, pre-auth idle) and n3e's existing per-frame caps. Tells us what a *legit* KO-style client's packet rate is so limits are not too tight. | `world-npc-ai.md` "Speed/warp checks"; `operations-persistence.md` timers | Record one number: typical and peak frames/s of the KO client in combat. n3e's own client is what connects, so this is a sanity bound, not a requirement. |
| P2 | **Scheduled events** — national war opens on INI weekdays/hour with a 5-minute notice; monster challenge hourly with notices at :55/:59; Santa/Angel broadcasts | Deploy gating (O8) assumes "players online" is the only signal. If the realm later runs scheduled events, CD should also refuse to restart inside an event window even with zero players (people are about to arrive). | `quests-events.md` | Decision: add an `events.next_start` field to `/v1/realm/status` later. Not v1. |
| P2 | **CONCURRENT / population reports** (DB-agent timer 200 = 300 s) | Our `player.joined/left` events + `status.players` replace this. Nothing to reverse; note the 5-minute cadence as a sane default if we ever persist population history. | `operations-persistence.md` | None. |
| P3 | **Character slots / nation / account attributes** (`TB_USER`, `ACCOUNT_CHAR`, premium) | Discord-linked accounts (spec 02) carry nothing but `discord_id`. If premium/nation-lock semantics are wanted later, the account table grows. n3e already has 8 chars/account/realm. | `identity-social.md`, `DATABASE.md` | None for v1. |
| P3 | **Hack-tool kicks, `/reload_hacktool`, NATION_ID = 3 behaviours** | Not in our arch (server authority replaces client integrity checks). Listed so nobody asks later. | `operations-persistence.md` | None. |
| P3 | **Launcher.exe / patcher** (version table, patch download, news pane) | We own the Launcher (spec 04). Only the *feel* (news pane, progress) is reference material. | not catalogued (client-side tooling, outside the four programs) | Optional: screenshot-level reference for the Launcher UI. No binary work. |

## What this implies for the specs

1. **The P1 rate-event item shapes spec 10's presets.** `/event` is now defined as
   activating a package preset over revision properties; the KO findings decide the
   semantics of `rate.*` (realm-wide vs zone, stacking with premium, what happens at
   expiry) before the registry kinds are implemented.
2. **In-game notice is probably a v1 requirement**, not a nice-to-have: without it, the
   force-deploy path (spec 06) warns players only in Discord, which is worse than KO. If
   accepted, it adds an n3e `AdminRequest{operation:"notice"}` and a client banner —
   both engine-side work in `N3E-Realm` after migration. Logged as **Q13**.
3. **Ban model may need `mute` and `attack-disable`** to match what mods expect from KO.
   Logged as **Q14**; default is to defer.
4. The P2 UX items (kick message, version-mismatch wording, serverdown countdown) are
   cheap decompiles that make the client's failure messages match what the community
   already recognises. They are the right first tasks for anyone touching the client.

## Working method

Same rules as n3e's `AGENTS.md`: confirm in the binaries via the project Ghidra setup
before implementing, record the address beside the claim, state binary vs source vs
local-asset evidence. New findings go into `n3e/docs/ko/` through n3e's own process
(that repo's rules apply); this file only tracks *which* findings the Realm needs.
