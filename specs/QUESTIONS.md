# Open questions

Raised while writing the specs. Ordered by how much depends on the answer. Each has a
**default** — the interpretation an agent should take if the question is still open when
it reaches the relevant work — except where marked **blocking**.

## Blocking (decide before M0)

*(none — Q3 resolved below)*

## Shapes a spec (safe default exists)

### Q4 — Require Discord guild membership to log in?

Spec 02 requests only `identify`. Requiring membership needs `guilds.members.read` (or
the Bot checking membership via its own token — simpler) and a policy for players who
leave the guild mid-session.
**Default:** not required for login; the Bot can `/ban` anyone. Revisit if the realm is
invite-only.

### Q6 — What do `/drop` and `/event` do?

**Answered in spec 10, confirmed against KO (`KO-FINDINGS.md` §2):** event *presets* defined in the package (`events.json`) as
patches over revision properties with a duration; `/event <preset>` activates one via
the admin API, no restart. `/drop` is subsumed (a preset sets `rate.drop`). Remaining
engine work: registry kinds `rate.exp/drop/coin`, `event.active`, timed reversion. The
KO reversing item (P1 rate events) still informs the semantics (scope, stacking) — keep
it in the pre-phase.

### Q10 — Client exit code for "update required"

Exit `3` on `VERSION`/`CONTENT` handshake refusal, with KO-derived wording
(`KO-FINDINGS.md` §5). Engine item after migration; until then the Launcher's "any
non-zero exit within 10 s → refetch once" heuristic applies. **Default:** as stated.
**Implemented (M4):** the client exits `3` on either refusal and prints the reason and
"run the launcher to update"; the Launcher recognises only `3`, so the 10 s heuristic
was never needed.
### Q11 — Raw KO asset tarball hosting

Resolved to option C (spec 10): one immutable `.tar.zst` (~740 MB), sha256-pinned,
hosted as a Release asset of `N3E-Realm` (`content-store` Release). Remaining: confirm
GitHub's 2 GiB per-asset limit is comfortable and whether the tarball should be split by
top-level dir (`Chr/`, `Object/`, …) so partial fetches are possible. **Default:** one
file.

### Q13 — In-game notice in v1?

**Yes (resolved by `KO-FINDINGS.md` §1, §3).** KO warns in game once per minute
before shutdown and shows a notice panel on world entry. Spec 03 now has
`realm/notice {in_game}` → yellow NOTICE chat line, `realm/motd`, and the engine items
(`Chat.notice`, `Notice{lines}`). CD's force path sends one line per minute.
### Q14 — Ban model: `mute` and `attack-disable`?

**Mute in v1, attack-disable deferred (resolved by `KO-FINDINGS.md` §4).**
`accounts.muted_until`, `account.mute` permission, `/mute`. Enforced server-side by
dropping chat; the player is told once per session. Attack-disable waits for PvP.
### Q15 — Monitoring and alerting beyond the Bot

Nothing pages a human if the VPS dies at 3 a.m. (the Bot dies with it). A free external
uptime check on `7777`/`7781` posting to the ops channel via webhook is ~10 minutes of
work. **Default:** add it in M7; not a spec.

### Q16 — Hot TLS reload

Every cert renewal is a gated realm restart (spec 07). A `SIGHUP`-reloads-cert feature
in the realm process (gateway under B; n3e under A) removes that. **Default:** not v1;
renewals are ~every 60 days and gated anyway.

### Q17 — Admin API reference: generated or hand-kept?

Spec 08 publishes `/api/admin.md`. Generating it from code (OpenAPI) is extra tooling;
hand-keeping drifts. **Default:** hand-kept in spec 03 (it *is* the reference); the
docs build copies it.

### Q18 — Which `games/*` package is the realm, and does Moradon alone suffice for launch?

`games/moradon` exists and `live-ko` exercises it. Is the launch realm Moradon only, or
do other zones need to be cooked (and does `assetc` support them yet)? **Default:**
Moradon only; `games/moradon` is `realm-assets`.

### Q26 — Code signing (later)

Launching **unsigned** (Windows Q2, option a). Revisit when the repo is public: apply to
SignPath Foundation (free OSS signing; needs an OSI licence on the code); fall back to an
OV certificate signed from CD via a cloud HSM. Spec 06 keeps a no-op `sign` stage so
enabling it is configuration. Player docs carry the SmartScreen note until then.

### Q19 — Public redistribution of KO-derived content

Resolved by the user: the Open-KO org has published KO content for a long time without
issue; Releases are public. Recorded here so the risk acceptance is explicit. The
content archive should carry a `PROVENANCE.md` naming the Open-KO source and pin.

### Q20 — Custom-asset scope for v1

Spec 10 opens items, NPC looks, effects, UI textures, tables, rates, presets. Zones and
terrain from non-KO sources are closed (importers are KO-specific). Confirm, and decide
whether *modified KO-derived* assets (e.g. a retextured KO model exported from Blender)
count as contributions or as KO material. **Default:** closed to zones; derived-from-KO
assets are KO material and not accepted.

### Q21 — Boss spawn lifetime

The engine's `spawn` is a temporary NPC with a 60 s expiry and ≤ 16 concurrent (editor
semantics). A boss event needs longer. Add `duration_ticks` to the spawn authorisation,
bounded (≤ 2 h?), still non-persistent across restart. **Default:** add it, cap 2 h.

### Q22 — Licence for contributed assets

CC-BY 4.0 or CC0. CC0 is simplest for redistribution; CC-BY credits artists in
`PROVENANCE.md`, which we keep anyway. **Default:** CC-BY 4.0.

### Q23 — Software-GL preview renders in content CI

llvmpipe offscreen capture of changed assets as a PR artifact. Nice, not required.
**Default:** not v1.

### Q24 — Preset behaviour across a realm restart

A preset active at restart: resume if still within its wall-clock window, or always
revert? Resuming is friendlier for "weekend XP" spanning a Saturday deploy. The expiry
is already stored in the revision, so resuming is the natural implementation.
**Default:** resume.

### Q25 — Content store location

Release assets on a rolling `content-store` Release (per-asset limit 2 GiB; no
documented count limit but thousands of assets on one Release is untested). If it
becomes a problem, an object store behind the same `base_url`. **Default:** Release
assets; watch the count.

## Resolved

| Q | Resolution |
|---|---|
| Q1 | **In-process, in `N3E-Realm`.** The engine migrates into `N3E-Realm` (spec 09); the realm service (01–03) is implemented inside `n3e-server`/`n3e-client` there. No gateway. `n3e` freezes as reference/research. |
| Q2 | **Client runs the OAuth flow** (architecture ① stands); `discord_client_id` comes from the realm config via the manifest, not compiled in. |
| Q3 | **Windows is a v1 requirement; the client stays C++.** Port in M4b (CMake/vcpkg, POSIX audit, Windows cert-store → OpenSSL, `%APPDATA%` paths). Tested by (d2) a client-local `--self-test` CI job (named `--smoke-local` here first; Q46) on both `ubuntu-latest` and `windows-latest` plus (a) a Discord canary role for early releases; a real-GPU Windows run is manual: the maintainer runs the client on their own Windows machine periodically (2026-10-30); automating it is the upgrade path. macOS not v1. A Rust client is explicitly deferred (arguments on record: cross-compile ergonomics, shared collision crate with the server) — not before launch. |
| Q9 | `realm.restart` removed from `architecture.md`; restart is a CD/compose action. |
| Q5 | Moot (Launcher does not hold the token). |
| Q7 | Moot (no gateway). `N3E_MAX_CONNECTIONS` replaces the hardcoded 64. |
| Q8 | Moot (no gateway). Existing throttle applies per real client IP. |
| Q12 | **KO content, published publicly.** Raw KO tree as a pinned tarball (spec 10, option C); `games/moradon` is the first package. See Q11, Q18, Q19. |
| Q27 | **Kept, optional** (2026-10-30). The realm is Moradon from the client tree alone. The KO extras — installers (1097/2145/2233 zones and visuals) and the KO server database export (`tools/ko-reference/inspect_db.py`, restored for this) — stay operator-supplied inputs under ignored `build/`; the code is kept and its tests SKIP or report NOT RUN without them. |
| Q28 | **Synthetic schema states** (2026-10-30). The downgrade and pre-progression upgrade checks no longer need a server built from n3e history: `tests/schema_states.py` builds a database at migration N from `deploy/` exactly as `persistence::migrate` does, and one migration ahead of the server by adding an unknown `schema_migrations` row. `progression_db` pins the shipped 001–004 digests. The legacy-server binary and `N3E_HISTORY` are gone. |

## Raised during implementation

*(Agents append here. Format: `### Qnn — title`, context, options, default taken.)*

### Q29 — Admin listen address inside compose

Spec 03 refuses any `N3E_ADMIN_LISTEN` that is not loopback or RFC 1918 (test 8 names
`0.0.0.0:7780`); spec 07 set `0.0.0.0:7780` in compose so the Bot and the host publish
could reach it. Options: allow `0.0.0.0` behind a flag; bind the container's address
discovered at start; give the server a static compose-network address. **Default taken
(M1):** the static address — compose network subnet `172.31.77.0/24`, `server` at
`172.31.77.10`, `N3E_ADMIN_LISTEN=172.31.77.10:7780`. The rule stays one line with no
escape hatch; spec 07 updated. Revisit if the subnet collides on the VPS.

### Q30 — Motd and account routes in M1

M1 is spec 03 minus world operations, but the motd route needs the revision property
store (M5) and the account routes need sessions and moderation (M3/M6). **Default
taken:** M1 ships status, drain, resume, notice and deploy-pending; every other route is
routed and permission-checked and answers `501 not_implemented` until its milestone.

### Q31 — Per-source limits in tests and the local stack

Spec 01's defaults (3 sockets, 10 connects a minute per source) cannot hold for the live
suites, which all connect from one address (loopback, or the Compose gateway through
Docker's loopback publish), nor for several local clients on the local stack. Options:
exempt loopback in the server; lift the limits where every client shares an address.
**Default taken (M2):** no exemption in the server. `tests/live.py` gives every suite
`N3E_IP_MAX_CONCURRENT`/`N3E_IP_CONNECT_RATE` of 1,000,000 unless it sets them;
`compose.yaml` (local) defaults them to 64 and 600; production keeps spec 01's
defaults. `tests/connections_live.py` tests the real limits from distinct `127.0.0.x`
sources. Spec 01 test 8 reworded to match.

### Q32 — The cost budget's rate and build

Spec 01 test 7 gave a CPU budget (5 %) but no connect rate or build. **Default taken
(M2):** 500 connects/s from each of 4 addresses, 5 % above idle for the release binary,
15 % for the debug build the live run uses; figures recorded in spec 01.

### Q33 — Testing the Discord exchange without Discord

Spec 02 hardcodes `https://discord.com/api`, and test 1 needs a real Discord
application and a browser, so nothing automated could exercise the exchange. **Default
taken (M3):** `N3E_DISCORD_API` overrides the base (https, or plain http to loopback
only) and is refused on `N3E_REALM=prod`. `tests/discord_login_live.py` runs a stand-in
that issues codes bound to a PKCE challenge and checks the secret and verifier. The
real-application round trip stays a manual check by the maintainer.

### Q34 — Throttling a Discord login before its account is known

Spec 02 keys `DiscordLogin`'s account throttle on `sha256(discord_id)`, which is known
only after the exchange; counting nothing until then would let one IP make unbounded
Discord calls with junk codes. **Default taken (M3):** the IP is counted before the
exchange, the Discord id after it; at most 16 exchanges run at once.

### Q35 — Columns spec 02's migration lacked

Spec 03's account lookup reports `created_at`, which `accounts` did not have, and a
permanent mute (`until: null`) could not be told from no mute with `muted_until`
alone. **Default taken (M3):** migration 025 adds `created_at` (existing rows get the
migration's time) and `muted_at` (set = muted; `muted_until` NULL = permanent), the
pattern bans already use.

### Q36 — What LoginResult carries after a SessionLogin

Spec 02 sends `LoginResult` on success of either login message but only mints a token
for `DiscordLogin`. **Default taken (M3):** a `SessionLogin`'s `LoginResult` has an
empty `token`, the session's `expires_at_unix`, and the account's Discord id and name;
the client keeps the token it holds.

### Q37 — Pending stream entries when the bot's host name changes

Spec 05 names the consumer after the host name and drains its own pending entries at
start; a recreated container gets a new host name, so entries it left unacknowledged
would sit in the old consumer's list forever. **Default taken (M6):** at start the bot
takes over every pending entry of the `bot` group (`XAUTOCLAIM … 0`) before reading its
own; there is one bot per realm. The production compose file also fixes `hostname`.

### Q38 — Who an `account.*` message names

The stream's `by` is the admin token's name, so every moderator action taken through
Discord would read "bot kicked Nelly". **Default taken (M6):** the bot remembers, for 2
minutes and in memory only, which moderator it called each account route for, and
names them; anything else (curl, a restart in between) shows the token name.

### Q39 — Testing the bot without Discord or GitHub

Spec 05 asks for Discord "mocked at the library boundary where practical". **Default
taken (M6):** the bot takes test-only stand-in addresses for Discord's REST API and
gateway (`DISCORD_API_PROXY`, `DISCORD_GATEWAY_PROXY`, through the library's own proxy
settings) and for GitHub (`GITHUB_API`), all refused unless they are on loopback.
`tests/bot_live.py` runs a minimal gateway (HELLO, IDENTIFY, READY, INTERACTION_CREATE)
and REST API, so the real library code parses the interactions and sends the replies.

### Q40 — `/motd`'s lines in a slash command

A slash command's string option is a single line. **Default taken (M6):** `/motd` takes
one string and splits it on `|`; 1-20 lines of at most 127 bytes are checked before the
call.

### Q41 — Discord library and the pinned toolchain

`rust-toolchain.toml` pins Rust 1.85.1; twilight 0.17 needs 1.89. **Default taken
(M6):** twilight 0.16 (gateway, HTTP, model, util), pinned exactly, with the lock
resolved for 1.85 (`CARGO_RESOLVER_INCOMPATIBLE_RUST_VERSIONS=fallback`). Moving to 0.17
waits for a toolchain bump.

### Q42 — An old launcher run by hand after a self-update

A self-update installs the new binary under `launcher/<v>/` and swaps `current`, but
the player's shortcut may still point at the binary they downloaded. **Default taken
(M4):** every run first checks `current`; if it names a newer version, the old binary
execs it with the same argv (spec 04 "Behaviour" step 0). `--check` hands over too, so
it reports for the launcher that will actually run.

### Q43 — Plain http for test realms

Spec 04 says TLS; the suites need a file server they can stop and corrupt. **Default
taken (M4):** manifest, index and artifact URLs must be `https://`, except plain
`http://` to a host that resolves to loopback. There is no test-only switch, so a
release build cannot be talked into plain http off the machine.

### Q44 — `--check` when the releases cannot be reached

`--check` "exits 0/1"; acceptance test 8 wants it to fail offline. **Default taken
(M4):** `0` nothing to change, `1` something to change, `10` (the network code) when the
manifest or a needed index cannot be fetched. It never falls back to what is installed.

### Q45 — The roadmap's "test Release"

M4 lists "a hand-written manifest in a test Release". Publishing a GitHub Release is
outward-facing and the default manifest URL is `releases/latest`, which a test Release
would become. **Default taken (M4):** the suite publishes its releases on a loopback
file server; a GitHub test Release (a pre-release, so `latest` is untouched) waits for
the maintainer's go-ahead. The roadmap's done-when (a clean machine downloads one
binary and connects) needs a real Release, so it closes with M5's first publish.

### Q46 — `--smoke-local` in the player build

Spec 06's smoke runs the player `n3e-client --smoke-local`, but PQ-006
(`tests/player_build.py`) forbids `-smoke` in the player binary, so a smoke mode there
would have to move the rule. **Default taken (M4b):** the player's install check is
`--self-test --realm realm.json` (package and scene, realm.json, the authorize address
on a loopback callback port, the system CA certificates, the settings directory, a
hidden OpenGL 3.3 core window with every loaded function). It prints no harness marker.

### Q47 — The Windows client's form

Spec 06 had `n3e-client-windows-x86_64.zip` (exe + DLLs). **Default taken (M4b):** one
static `n3e-client.exe` (vcpkg `x64-windows-static`, static C runtime: nothing for a
player to install), in a `.tar.zst` like Linux's, so the Launcher has one extractor.
Console subsystem: the Discord address it prints stays visible.

### Q48 — The client without `--ca`

Spec 07 and O1 say the client trusts the system CA store, but the client required
`--ca` ("CA failed" without it), so a player client could not have connected to a
Let's Encrypt realm. **Default taken (M4b):** without `--ca`, OpenSSL's default paths on
Linux, the Windows `ROOT` store on Windows; `--ca` still replaces them for dev realms.

### Q49 — Which Linux systems the client archive runs on

The Linux client links the build system's glibc and libstdc++. **Default taken (M4b):**
the archive bundles SDL3, protobuf and abseil (`tools/package_client.py`), and is built
on Ubuntu 24.04, so it runs on distributions at least that new. An older baseline would
need the builder image (spec 06) on an older base.

### Q50 — Where the demo goes

The maintainer asked to drop the demo for KO assets. **Default taken (spec 11), accepted by the maintainer 2026-10-31:**
the demo leaves every player-facing path (local release, Windows kit, `tools/local-realm`,
README, manual test round), which serve Moradon instead. `games/demo` and the synthetic
packages stay as test fixtures: CI has no KO tree, and the CPU suite and release smoke
need content it can build. Deleting them repo-wide would remove most of `make test`.

### Q51 — Nation select

KO asks a new account for Karus or El Morad. The realm draws every player as the male
Tuarek (`ko_player.py` `RACE = 2`, Karus). **Default taken (spec 11), accepted by the maintainer 2026-10-31:** no nation
screen; the realm is Karus, so the Karus select hall and loading art. Two nations need
El Morad player models, nation on the wire and in `characters`, and the server's rules
for it: a later milestone.

### Q52 — Character create choices

KO's create screen picks race, class, face, hair and stat points. The realm has one
model and one class. **Default taken (spec 11), accepted by the maintainer 2026-10-31:** the KO screen with the name field
working and race and class shown fixed; face, hair and stats hidden. More races and
classes come with the content that supports them.

### Q53 — Deleting a character

KO's select screen has Delete; the server has no character deletion. **Default taken (spec 11), accepted by
the maintainer 2026-10-31:** the button is hidden. Deletion needs a durable, auditable path
(soft delete, a grace period, what happens to items), which is its own change.

### Q54 — More than one realm in the server list

The client gets one realm from `realm.json` (the Launcher's choice, spec 04), and logs
in over that realm's own connection. **Default taken (spec 11), accepted by the maintainer 2026-10-31:** the server list
shows that one realm, after login, to keep KO's order. A real list (several realms, their
population) needs a public status endpoint and is deferred.

### Q55 — `demo:` ids inside the Moradon content

Moradon's items, skills and classes carry `demo:` ids (`games/moradon/*.json`). Players
don't see ids, but contributors do. **Default taken (spec 11), accepted by the maintainer 2026-10-31:** not changed by
the front end; renaming them is a content migration (spec 10, M5b) with a revision bump.

### Q56 — The KO copyright line and service logos

*Superseded by Q61: KO's copyright line is kept.* *RQ-101 (the maintainer,
2026-11-02, "lets keep it looking and feeling as close to the original as
possible"): the realm no longer avoids KO's publisher branding where KO shows it:
the 1097 choice shows 1264's "K2 Network presents Knight Online" logo screen (Q82).*

`co_login_us.uif` carries "Copyright MGAME & Noahsystem all right reserved." and the
Daum/MGame logos. **Default taken (spec 11), accepted by the maintainer 2026-10-31:** hide the logos; replace the line with
"N3E Realm, a community project. Not affiliated with MGAME or Noahsystem." The realm
should not look like an official service.

### Q57 — Front-end music

KO plays its intro and select music on these screens. The front end has no audio of
its own yet, and `audio.bin` binds in-game sounds only. **Default taken (M4c):** the
screens are silent. Music needs a bounded stream (the tracks are minutes long), which
is its own change.

*Done (RQ-018, 2026-11-01):* the maintainer's playtest asked for it. `front-end.bin`
version 3 carries KO 1298's track, `Snd/Intro_Sound.mp3`, looping on login, the
realm list, select and create and stopped before loading, as `KnightOnLine.exe` plays
it (content/front-end.md, "Moradon"); the client streams it one frame at a time.
Its form in the package is Q69.
*RQ-071:* Option.ini `[Sound] Effect=0` silences it, as KO 1298 does; the front end
has no other sounds in 1298 (Q70).
*RQ-078 (KO-FINDINGS §9, binary):* 1097's login plays another track: sound 35,
`Snd\bgm_login.wav` (21.67 s, in the pinned tree too), restarted every 21.66 s by
its tick, and its select leaves it running. The 1097 front end (Q73) keeps 1298's
track until `front-end.bin` carries a PCM track (filed under RQ-078).
*Done (RQ-083, KO-FINDINGS §9, binary):* `front-end.bin` version 5 carries 16-bit
PCM tracks and a restart period, and the 1097 front end plays 1097's music. One
correction to RQ-078: the select does not inherit sound 35. 1097's answer to the
game server's login (`00525b70`) releases it and starts sound 20003,
`Snd\bgm_el_battle.wav` (181 s, in the pinned tree too), looping, before it opens
select; create leaves it; the select releases it after the start clip. So login and
the realm list play `bgm_login.wav`, restarted every 21.66 s (its stream alone would
stop after one pass: the login never sets its loop byte), and select and create play
`bgm_el_battle.wav`. Both are carried as the WAVs' samples (about 1.9 and 16 MB; Q69
kept MP3 frames to avoid decoding at cook time, which a WAV does not need). Returning
to the login is Q75.

### Q58 — Option and Registration in the login bar

*Superseded by Q61: Option and Registration are shown, unbound.*

KO's login bar art (`co_login_us.uif`'s background) has its four buttons painted in.
Hiding Option and Registration (no account registration here; options are in game)
leaves two blank painted buttons beside **Discord** and **Cancel**. **Default taken
(M4c):** leave them blank. Covering them needs new art or a cropped copy of KO's, which
is a content decision.

### Q59 — Engine 42 and the NPC table

PQ-272 tied engine 41 to N3N4 templates both ways ("an engine 41 package's templates
are N3N4"), so a package that needs a later engine for something else could not keep
reference NPCs. Moradon has reference NPCs (N3N2, engine 36). **Default taken (M4c):**
engine 42 keeps whichever NPC table the package has; N3N4 still needs engine 41 or
later, and an engine 41 package still has N3N4. Both readers say so
(`server/src/content.rs`, `client/assets/assets.cpp`).

### Q60 — The ID and password fields on the login screen

Spec 11 first hid them, since login is Discord. The maintainer asked on 2026-10-31 to
keep them for KO's look. **Default taken (M4c):** they are drawn as KO draws them,
with their labels, and bound to no action: they take no clicks or typing, so nobody
types a password into a field that goes nowhere. Login stays the Login button
and ENTER.

### Q61 — The login screen stays KO's original

The maintainer asked on 2026-10-31 that the login screen stay original, without the
UI M4c added. **Default taken (M4c), superseding Q56 and Q58:** the login bar keeps
KO's labels (**Login**, **Cancel**, **Option**, **Registration**) and `Text_Rights`
keeps KO's "Copyright MGAME & Noahsystem all right reserved."; Option and
Registration are shown, unbound, like ID and Password (Q60). The added `notice` line
is gone (`notice` is now optional in the format); the Discord flow's failures, the
address to open when no browser starts, and a server that cannot be reached after a
login press show in KO's message box. Still hidden: the Daum/MGame logos (the UIF
names `ui_us\service_logos.dxt`, absent from the pinned tree, which has
`Service_Logos_us.DXT`) and `premium` and the three notice groups (KO's news panels,
which draw as empty frames with no news to fill them).
*RQ-101 (Q82):* that keeps the login itself as KO draws it; it is not a stance
against KO's other screens. Before the login, the 1097 choice now shows 1264's logo
screen, as the maintainer asked (2026-11-02: "lets keep it looking and feeling as
close to the original as possible"). The login's Daum/MGame images stay hidden for
their missing texture.
*RQ-108 (Q85, KO-FINDINGS §9.4):* `Text_Rights` keeps KO's text and is drawn as
1264 draws it: only while the login bar is hidden (a login under way, and the realm
list), centred 20 px above the bottom edge. 1264 never shows the Daum/MGame images
either.

### Q62 — The realm client's window size

The maintainer asked on 2026-10-31 for KO's fixed window sizes, as `tools/play-moradon`
has. **Default taken (spec 04):** with `--realm` the client opens a fixed window of
1280x1024 (`play-moradon`'s default), or 1024x768 or 1600x1200 with
`--fixed-window`, and refuses other sizes; `--fullscreen` uses an exclusive mode of
that size. `realm-launcher --fixed-window SIZE [--fullscreen]` and the Windows kit's
`play.bat` pass them through. The size is not saved between starts.

### Q63 — The hosted realm is a `test-` realm

The server converts a package's progression only on a `test-` realm with
`N3E_TEST_PROGRESSION=disposable` (`server/src/main.rs`), and refuses a realm whose
reward policy was never converted, so `N3E_REALM=prod` (spec 07) cannot run Moradon
today. **Default taken (2026-11-01):** the hosted realm is
`<N3E_REALM_PREFIX>-<package hash[:12]>` (`test-openko-…`), as `tools/local-realm`
does; every other production setting stands (Discord only, no legacy login, spec 01's
limits). A new package with changed progression starts a new realm, so characters do
not carry over. Revisit with a production conversion path for progression packages.

### Q64 — The realm's host: a home machine behind Cloudflare, not a VPS

The maintainer chose on 2026-11-01 to host on their own machine (the realm host) rather than
pay for a VPS with scrubbing (spec 07's requirement), and to carry the game wire as a
WebSocket through Cloudflare's free proxy and a Tunnel so the home address is never
public. The reasoning and the providers checked are in `architecture.md`, "DDoS". Spec
12 is the design (milestone M7a), approved and built on 2026-11-01. No port is
forwarded; the realm is public only through the tunnel.

### Q65 — Cloudflare's free-plan WebSocket limits

Cloudflare supports WebSockets on all plans but publishes no concurrent-connection
figure for the free plan, and says long-lived sockets can be closed when its edge
restarts. **Default taken:** assume a community realm's tens of players fit; the client
reconnects with its session token after a close (spec 02). If the realm is throttled,
the fallback is the relay VPS of `architecture.md`'s ladder.

### Q66 — The launcher's default realm

The maintainer asked on 2026-11-01 that a launcher downloaded and run with no arguments
connect to OpenKO. **Default taken (spec 04):** the compiled-in default profile is
`openko` at `https://releases.openko.net/manifest.json` (the realm's tunnel,
deploy/HOST.md), replacing `n3e-realm` at a GitHub Releases URL that never served a
manifest. A `realms.json` from an older launcher drops that profile while it is unpinned
and gains the new default; a default the player chose stays. Players' `realms.json`
stores the URL, so it is permanent: when CD (M5) publishes Releases, it publishes the
manifest at this URL (or redirects it there), and keeps `realm.id` `openko`, which
every profile pins.

### Q67 — How CD reaches a host with no inbound port

Spec 06's deploy job ssh-es into a VPS; the home host (Q64) has no forwarded port and
no public address, and is aarch64 (`deploy/HOST.md`). Options: (a) pull: CD publishes a
`deploy.json` (sha, image digests, content hash, force, reason) beside the manifest and
a timer on the host polls it and runs the gated `remote.sh` locally; (b) a self-hosted
Actions runner on the host for the deploy job only (fork-PR workflows need approval;
the runner has Docker on a personal machine); (c) ssh through the tunnel behind a
Cloudflare Access service token. **Decided by the maintainer, 2026-11-01:** keep it
simple for now: CI builds and publishes, and the deploy runs over ssh from a machine on
the host's own network (the loop may run it, AGENTS.md "Agent loop"), with images built
for `linux/arm64`. A deploy path other self-hosting operators can use is researched
later (the queue's `self-host-deploy-research`).

### Q68 — Where off-box backups go from the home host

Spec 07 sends the nightly `pg_dump` to an object store; `deploy/HOST.md` has none yet
and plans the workstation, which is in the same house. RQ-000 proposed Cloudflare R2 via
`rclone` with the workstation as a second copy. **Decided by the maintainer,
2026-11-01:** no off-box backups for now. The nightly `pg_dump` and the pre-deploy dump
stay on the host, with one restore rehearsal; an off-box copy is revisited later.

### Q69 — Front-end music: KO's MPEG frames in the package, decoded by the client

RQ-018 streams KO's front-end track. Every other KO asset is decoded at cook time into
an engine format (textures to RGBA, `ko_audio` WAVs to PCM). The track is MP3, and the
cook has no MP3 decoder: a pure-Python one is too slow for a 107 s track, and a system
`ffmpeg`/`mpg123` would make the package bytes, and so the release pins, depend on the
cooking machine's decoder. Decoded PCM would also be about 19 MB (44.1 kHz stereo).
**Default taken (RQ-018):** the cook carries the track's MPEG-1/2 Layer III frames
unchanged inside `front-end.bin` (tags and the file's cut-short last frame dropped,
every frame checked by the cook and again by the loader; 1.7 MB), and the client
decodes them while streaming with minimp3 (CC0), vendored at a pinned commit in
`client/third_party/minimp3/` (`UPSTREAM.md`) because the player build has no system
package for it on Linux. Nothing raw is published as a file, but the frames are KO's
bytes; if the maintainer reads "only cooked output ships" (spec 10) as excluding
them, the alternative is a cook-time decode to PCM or ADPCM with a pinned decoder.
**Decided by the maintainer, 2026-11-01:** the default (KO's frames inside
`front-end.bin`, decoded by the client); spec 10 now defines "cooked" as validated and
repackaged into an engine container, not necessarily re-encoded.

### Q70 — The front-end screens' other sounds, and the switch that silences them

The maintainer's 2026-11-01 playtest asked that the login and select screens get sound;
RQ-018 added KO's front-end music, the sound 1298 plays there. RQ-071, filed by the loop after RQ-018 and not asked for by
the maintainer, proposed the select hall's rotate sound
(`ID_SOUND_CHR_SELECT_ROTATE`, `char_select_turn.wav`), the UIF buttons' hover and
click sounds on login, select, create and the message box, and KO's Option.ini
`[Sound] Bgm` switch, each to be confirmed against the 1298 binary. The binary does
not confirm them (binary, `KnightOnLine.exe`; local-asset, the pinned UIFs):

- The rotate sound is the later source's. 1298's select left and right (`005fe3c0`,
  `005fe450`) play no sound, and no function of the select proc, its UI class
  (`00606a90`) or any caller of the sound-table creator `0044d1b0` names id 2501.
- The UIF buttons play only the sounds their file names (`00403fc0` reads both names
  and creates each with `0044d240`, which returns none for an empty one), and the
  five front-end layouts name none: every hover, click, typing, open and close sound
  string in them is empty.
- `[Sound] Bgm` (`0064b9b0`, default 1) is read by the zone music alone (`00640b10`
  sets the stream's audible flag `+0x38` from it). The front end's track is created
  through `0044d240` (`005f68e0`), which, like every other sound object (and the
  play-once path `0044d660`), is inaudible while `[Sound] Effect` is 0 (`006453b0`
  clears the manager's `+0x29`; `004501b0` and `0044fdf0` start nothing inaudible);
  with both 0 the device is never opened.

**Default taken (RQ-071):** follow 1298. The front end gains no rotate or UI sounds
(`content/front-end.md`, "Moradon"), and the client reads `[Sound] Effect` (default 1):
at 0 it opens no audio device, so the front end's music and every in-world sound are
silent, as in KO. `[Sound] Bgm` is not read, since n3e plays no zone music. If the
maintainer ever wants the later source's rotate sound or a music-only switch, each
is a small addition (a sound-table id bound in `audio.bin`; an Option.ini key) that
departs from 1298 and is recorded as such.

*RQ-077 (maintainer, 2026-11-01: add a sound on the select arrows or the buttons
only where KO itself plays one).* The select hall follows 1097 (Q71), so the
1097 image was read (KO-FINDINGS §8.2, binary and local-asset):

- **The rotate sound is 1097's.** Its select Init (`0043a950`) creates sound 2501
  (`0x9c5`) as the proc's sound object `+0x18`. 1097's `Data/sound.tbl` maps 2501
  to `Snd\char_select_turn.wav` (the pinned tree's file, byte for byte).
  DoJobLeft and DojobRight (`0043e310`, `0043e380`) play it through `004327d0`
  for each turn they start: not during a turn, not at the end of the row.
- **No button sounds.** 1097's button loader (`00403ac0`) creates a sound only for
  a non-empty name. Its Karus front-end layouts (`Data/UIs.tbl`: `co_login`,
  `Ka_CharacterSelect`, `Ka_CharacterCreate`, `Ka_MessageBox`, `Co_Loading`,
  `ka_loading`) name none. El Morad's `el_characterselect.uif` does name button
  sounds, but the realm draws the Karus hall.
- 1097's sound switch is `[Sound] Enable` (default 1): at 0 no device is opened.
  1298's `[Sound] Effect` does the same, so the realm keeps reading 1298's key.

**Default taken (RQ-077):** bind and play the rotate sound. `front-end.json`
`select.turn_sound` (2501) is cooked into `audio.bin` as `front:select-turn`
(`content/front-end.md`, "Moradon"). The client plays it unpositioned, as one
voice that a new turn restarts, for each turn an arrow starts. KO creates it as a
3D sound with no position; that gain and pan were not read. The screens gain no
UI sounds, as in 1097 and 1298. This departs from 1298, which plays no rotate
sound, as the 1097 hall does elsewhere (Q71).

### Q71 — The select hall's character in front: the later source's hover, or 1298's loop

The 2026-11-01 playtest (RQ-066) found the character in front cycling its clip while the
pointer was on it, and asked for KO's once-and-hold. Read against the 1298 binary
(KO-FINDINGS §8), the hold is the later source's: its `DoProcPreselect` plays
`pre_select` once and freezes on the last frame while the pointer is in the centre
rect, the asset set the Moradon package cooks (`upc_ka_tu_pri.n3joint`,
`upc_ka_at_wa.n3anim`: `pre_select`, `selected`, `dummy`) is that source's, and
neither name is in 1298. 1298 has no hover: with the camera at rest it loops clip 1
of the per-race `upc_ka_tu.n3anim` (frames 20–300, 9.3 s) on the character in front
and plays clip 0 once on the others, whatever the pointer does; the centre rect is
only its click; start plays clip 2 once.

Options: (a) keep the cooked set and play it as its source does (hover, once and hold);
(b) follow 1298: cook `upc_ka_<race>.n3joint`/`.n3anim` with clips 0, 1 and 2 and
their roles, loop clip 1 on the character in front without the pointer, and leave the
rect to the click.

**Default taken (RQ-066):** (a), what the maintainer asked for and coherent with the
assets the hall draws; spec 11 and `content/front-end.md` say it is not 1298's. (b) is
a separate change to the cook and the hall (proposed as its own queue item), and would
also need 1298's looks for those joints.

**1097 (RQ-074, KO-FINDINGS §8.1, binary from an unpacked image):** the 1097 client
has the hover. In state 2 its `DoProcPreselect` (`0043f280`) sets `pre_select` once on
the character in front while the pointer is strictly inside the 0.36–0.64 ×
0.44–0.86 rect, and `dummy` once when it is outside. The setter (`00447e30`) ignores
a call that names the current clip, so `pre_select` plays once and holds its last
frame. 1097 loads exactly the cooked set (`upc_ka_tu_pri.n3joint`, `upc_ka_at_wa.n3anim`,
whose files match the pinned tree's) and has no `upc_ka_tu` name. Its click and start
match (a)'s source: start sets clip 1 once with a 0.6 s blend and waits for
`IsAnimEnd`. So (a) is KO's own 1097 behaviour for this asset set; 1298's loop came
later, with the per-race files.

**Recommendation:** close Q71 as (a). Align three details with 1097:

- the clip's own 0.3 s blend in each direction, with `pre_select` held on its first
  frame during the blend;
- the front slot's spot theta, which grows only while the pointer is over the
  character (0.02 per tick up to 0.5, Karus), shrinks when it leaves and is off at 0;
- the info text, shown only while the pointer is over the character.

These are proposed as a separate front-end item. (b) is needed only if the realm
should look like 1298 rather than like the client its files come from.

**RQ-075:** the three details are aligned (`content/front-end.md`, "Moradon";
KO-FINDINGS §8.1). N3FE version 4 carries each clip's blend time from its record
and the spot's growth rate; the select model gains clip 2 (`dummy`). The per-tick
spot step (0.02, Karus) is cooked as 0.6 a second, at the 30 ticks a second KO's
frame-scaled code is written for (`30 / s_fFrmPerSec`). The turn keeps the spot's
theta and turns the spot off while it runs, as 1097 does. Still not 1097's: the
0.6 s blend into `selected` at start (proposed as its own item).

**RQ-076:** the start blends into `selected` over 1097's 0.6 s (the package's start
clip blend, `start_blend`), and loading follows the blend and the clip. How the start
is triggered is Q72.

**Decided (maintainer, 2026-11-01):** closed as (a). 1097's hover is the default select hall;
1298's loop (b) becomes one of the per-client front ends a realm owner can choose (RQ-078).

**RQ-086:** (b) is data. N3FE version 6 names the hall's front-clip mode
(`select.front_clip`: `hover`, the 1097 recipe's, or `loop`), and
`games/moradon/front-end-1298.json` cooks 1298's select character with the loop
(KO-FINDINGS §8.3, binary): `upc_ka_tu` with the default looks and no plug, its
clip 1 looping on the character in front, clip 0 once on the others and while
the camera turns, every character ticked, start clip 2 with 0.6 s, the spot
widening without the pointer and staying, the info text at rest (empty for an
empty slot), no turn sound. Moradon does not offer it yet: 1298's camera paths,
hall and slots, its UIF login intro and its select UI hidden during the turn
are not data (`content/front-end.md`, "1298"). The 1097 front end is unchanged
but for the mode field.

### Q72 — The select start: on the press, or on the server's answer as 1097

1097 (KO-FINDINGS §8.1, binary) sends the select request on ENTER or the click and
starts `selected` only when the server's answer says yes (`0043db30` → `0043ea30`),
and only if the camera is at rest then (state 2). Its click is taken outside the turn,
but its ENTER (`00440690` → `0043f860`) is taken in any state, so ENTER during the
turn goes to create or sends the select; the answer then starts no clip, and the next
ENTER outside the turn loads at once (`0043db70`). Once the answer has come, ENTER
during `selected` skips it the same way.

The realm starts `selected` on the press and sends `SelectCharacter` with it; its
server answers by entering the world (or a refusal, which returns the hall to rest).

Options: (a) keep the start on the press, taking ENTER and the click at rest only and
ignoring them while `selected` plays; (b) start on the server's answer and take
1097's ENTER paths, including the turn and the skip.

**Default taken (RQ-076):** (a). The realm's answer is world entry, not a separate
select result, and 1097's ENTER-during-turn path ends in a hall that waits for a
second ENTER with no clip played, which reads as a fault rather than a feature.
The visible start (blend, clip, spot, loading after the clip) is 1097's either way.

**Decided (maintainer, 2026-11-01):** (a), the start on the press, at rest only.

*Part of that decision (RQ-077, KO-FINDINGS §8.2, binary):* 1097's arrows also
start a turn from state 3, while the start clip plays. DoJobLeft and DojobRight
(`0043e310`, `0043e380`) return early only in state 1. Elsewhere they set state 1,
turn the camera and play the rotate sound. The realm ignores the arrows from the
start until loading, as it ignores a second start.

### Q73 — Where the realm owner chooses the front end's client, and who refuses

The maintainer (2026-11-01, RQ-078) asked that realm owners choose, "in a
server-side config file", which KO client the front end looks and behaves like
(1097, 1298, a 2xxx one), that the choice be package data or a revision property,
and that "the server" refuse a choice whose inputs are missing. The front end is
cooked assets, not a tunable, so it cannot be a revision property; and the realm's
server runs a cooked package and never has the KO inputs (spec 07,
`deploy/HOST.md`: the package is cooked on the workstation).
**Default taken (RQ-078):** the choice is tracked package data the realm owner
edits: `games/<game>/realm-config.json` (`front_end`), one of the clients
`games/<game>/front-ends.json` offers (`content/front-end.md`, "Choosing the
client"). The cook (`make realm-assets`) is the server side that refuses: an
unoffered client, missing inputs or a malformed file stop it before the survey,
with a message naming what to change. No environment override (the package would
then depend on the cooking shell, and CD's cook would not reproduce it), and no
check in `n3e-server` (it would compare the package with itself). The cooked
`front-end.bin` carries no client id; the client is in the package's
`provenance.json`. Moradon offers only `1097` (KO-FINDINGS §9 lists what each
other client needs); its music is 1097's since RQ-083 (Q57).
RQ-085's question (draw 1097's own layouts, whose login, create and message-box art
is Korean, or keep 1298's English ones) is **decided by the maintainer
(2026-11-02):** neither; the 1097 choice draws the 1264 client's English screens.
They are the pinned tree's layouts byte for byte; the choice now reads them, and
1264's message box and loading screen, from the pinned 1264 install
(`installer-1264`, KO-FINDINGS §9.2), so a cook of the realm's package needs that
install as well as the pinned tree.


### Q74 — Where the player logs out, and what a logout ends

The maintainer's playtest (2026-11-01, RQ-068): once logged in with Discord there is
no way to log out. The KO screens stay as KO draws them (Q61), so the logout cannot
be a new button, and the login bar's unbound Option and Registration cannot be
relabelled into one. Options: bind an existing KO button (Registration, or the
select screen's Back) to a logout, which changes what KO's button does without
saying so; an in-game menu entry; a command-line logout off the KO screens.
**Default taken (RQ-068):** off the KO screens. `realm-launcher --logout` starts
the client with `--logout` (spec 04); the client, which owns `session.json`,
deletes it at once, sends `SessionLogout` (wire 49, spec 02) once connected, and
waits on KO's login screen. The next Discord login in that process asks with
`prompt=consent`, so Discord's authorize page shows which Discord account the
browser is logged in as and lets the player switch. KO's select screen Back keeps
its meaning (return to login; the stored session logs in again). A logout ends only
this computer's session, not the account's others (the architecture's "Player
logout → delete that one row"); ending all of them stays an operator's kick. The
token is forgotten before the realm answers, so a logout that cannot reach the
realm (offline, refused, or an update that exits 3 first) still logs this computer
out; the realm's row then lapses at its expiry, a kick or the account's cap, and
no copy of its token remains here. Revisit for an in-game logout once the game has
a menu that could carry it without changing a KO screen.

### Q75 — The 1097 login music on a return to the login screen

KO 1097's login tick restarts sound 35 off a timer (`006e0344`) that no Init resets
and that runs only while the login shows (KO-FINDINGS §9, RQ-083, binary). A player
who goes back from select to the login (KO's Back, which the realm keeps, Q74) hears
the login Init's new sound 35 only when that timer next passes 21.66 s: up to 21.66 s
of silence, depending on how long the login showed before. Options: (a) start the
login track at its first sample on every entry to the login screen; (b) keep a
per-process timer for the track, as 1097 does.
**Default taken (RQ-083):** (a). The engine's restart period is the track's own
(`front-end.bin` version 5, content/front-end.md section 9), counted from the
track's start; a phase carried across screens would be a second, KO-specific timer
for a silence that reads as a fault. The first login of a process is the same either
way (the timer starts at 0, so 1097 plays at once).
**Decided (RQ-096, maintainer 2026-11-02: "use 1264's approach"):** (b). KO 1264
keeps the same timer (KO-FINDINGS §9.1, binary: the login tick `005be500` plays
sound 35 when `007ac9d0` is 0 and stops it past 21.66 s; only that tick writes it),
so 1097 and 1264 agree. The client keeps each restarting track's clock for the
process (`client/render/audio.h`, content/front-end.md section 9): it runs only
while a screen naming the track shows, the first entry plays at once, and a return
to the login is silent until the clock next reaches 21.66 s, then starts the track
at its first sample. No format change: the restart period's bytes are as before,
its clock is now the process's.
**Decided (RQ-105, maintainer 2026-11-02 playtest, on the silent return: "we should
fix that, seems like a bug to me"):** (a), superseding RQ-096's (b). Every entry to
the login starts `bgm_login.wav` at once from its first sample, and its 21.66 s
restart period counts from that start (`client/render/audio.h`, content/front-end.md
section 9). 1097's and 1264's carried clock stays in the client behind one switch,
`AudioMixer::carry_music_clock`, off by default and set by nothing yet: RQ-103 offers
it as a realm-owner option. Turning it on needs no format change in the mixer;
RQ-103 decides where the option is carried to the client (a `front-end.bin` field
would be a format change of its own).

### Q76 — How a front-end recipe names its input trees, and when an install's files are checked

RQ-084 lets a front-end choice read more than one tree (the pinned tree, a reference
install). A recipe path could name its tree by the input's position, by its tree
path, or by a name; and a reference install could be checked file by file before the
cook (every file the recipe reaches, including those its KO files name, known only by
reading them) or at each read.
**Default taken (RQ-084):** by a `name` front-ends.json gives every input after the
first (`<name>:<path>`; unprefixed is the first input), since positions shift when an
input is added and tree paths are long and machine-shaped. The pinned installs are
`tools/assetc/ko_installs.py`'s (1097 and 2145, the ones the cook already checked;
any other tree under `build/ko-reference/`, the Steam install included, is refused
until it is pinned). The install's manifest is checked before anything is written;
each file is checked when the cook reads it, so a file that differs stops the cook
part way, with the source package directory partly written and nothing published
(`main.cook` never runs). Hashing the whole install up front (about 9,000 files for
1097) on every cook was judged too slow for what it adds.

### Q77 — 1298's select hall while the camera turns: hide its UI, or only the info text

1298 hides the whole select UI while the camera turns (KO-FINDINGS §8.3, binary:
DoJobLeft and DojobRight `005fe3c0`, `005fe450` call the UI's `+0x3c` with 0, the
arrival in `005fe5b0` with 1) and turns through recorded camera paths. The realm's
loop front-clip mode (RQ-086) turns about `at` as 1097 does and keeps the select
screen shown. Options: (a) hide only the info text while the camera turns, which
the loop mode would otherwise show for the slot just left; (b) hide the select
screen's UI while the camera turns in the loop mode, as 1298 does, now.
**Default taken (RQ-086):** (a). The UI hidden during the turn is part of 1298's
turn, with the camera paths that time it (their last frame is the arrival), and
goes into front-end data with them, as their own item; the 1298 recipe is not
offered until then.
**Decided (RQ-087):** (b), in the path turn mode (N3FE version 7): while a
recorded camera path plays, the entry path's fly-in included, the client hides the
whole select UI and shows it again on the path's arrival, as 1298 does
(KO-FINDINGS §8.4). The rotate mode (1097's) keeps the select screen shown, as
1097 does; the loop front-clip mode still hides the info text during any turn.

### Q78 — 1298's camera paths where the realm's screens are not 1298's

1298 flies the select camera in on `ka_lording_camera` in every select Init, and
its ENTER and ESC skip a path (`005fe280`; the tick's `+0x270`, ESC by the later
source's input layout) in every state but create's (KO-FINDINGS §8.4, binary).
1298's create is a state of the select (`005ff920`, states 6 and 7, the camera
turned to the first empty slot by paths 2–7); the realm's create is its own screen,
and the realm ignores ESC and the arrows while the start clip plays (Q72). Options
for the path mode: (a) fly in only when the hall opens from the realm list; back
from create, after a created character and after a refused start, the camera is at
rest on the slot in focus (the last frame of the path into it); ESC skips only while
a path plays, stays the realm's back at rest and does nothing while the start clip
plays; (b) fly in on every return to the hall, as 1298 does on each Init.
**Default taken (RQ-087):** (a). The realm's create and start are not 1298's states,
so where the realm returns to the hall from them it keeps the camera at rest, as it
did before; 1298's ESC during the start clip (back to state 5 after the select was
sent) has no realm equivalent. The load's extra step, which 1298 takes with the
last frame's time when a path starts, the client takes with the frame's own.

### Q79 — 1298's select zone: what the hall draws before its sky is data

1298's select draws zone 10001 `karus_intro` as its hall (KO-FINDINGS §8.4,
binary): Render (`005fb1c0`) clears to the sky manager's colour, then draws the
world's sky, terrain, shapes, grass and birds, the characters, the select UI and
the other windows, and last the alpha flush (`0043dd80`), all under the camera
file's fog. RQ-095 carries the terrain, the static shapes, their alpha parts and the
fog (N3FE version 8); the sky (`Misc/Sky/Karus.N3Sky`, a dome, clouds, sun and moon
keyed by the game time), the terrain's light maps (`karus_intro.tlt`), its grass,
the birds and the animated shapes (11 of 100) are not data yet. Options: (a) draw
what is data and leave the background black (the clear colour the RQ-087 hall
had) until the sky is its own item; (b) clear to a fixed colour, the fog's white,
meanwhile; (c) hold the zone back until the sky is data.
**Default taken (RQ-095):** (a). The 1298 recipe is not offered (RQ-088), so no
player sees it before the sky item lands; a colour 1298 never clears to (b) would be
the realm's own, and holding the terrain back (c) leaves the characters on black
for longer. The fog fades the far shapes toward white against that black until
then. The approximations recorded in `content/front-end.md` ("1298") stand: the
near tiles everywhere, the shapes' full-detail meshes, the client's mip chains,
the fog per pixel.

### Q80 — Which loading screen the 1097 choice draws, with no war victor

1264, whose screens the 1097 choice draws (RQ-085), loads `ka_loading_us.uif` when
the game server's war-victor byte is 1 (Karus), `el_loading_us.uif` when it is 2
(El Morad) and `Co_Loading_us.uif` otherwise (KO-FINDINGS §9.2, binary `005f9a30`;
the byte comes in the character-select answer and the server change). The realm
has no national war, so no victor, and the server sends no such byte. Options: (a)
draw `Co_Loading_us.uif`, what 1264 draws when no nation has won; (b) keep
`ka_loading_us.uif`, the Karus picture the choice drew before (every realm
character is a Karus Tuarek); (c) carry all three layouts in `front-end.bin` and a
victor on the wire now.
**Default taken (RQ-085):** (a). It is KO's own choice for the realm's state (no war
won); (b) would show a victory the realm never had, and (c) is a format and wire
change for a war the realm does not have. When the realm gets a war and a victor,
the loading screen by victor becomes its own item.

### Q81 — The title in 1264's message box

1264's message box (`el_messagebox_us.uif`, RQ-085) has a title string
(`Text_title`, "111" in the layout) that `MessageBoxPost` sets from its caller: empty
for the connection-closed and character-select failures, "Failed to connect to
login server" and the like for others (KO-FINDINGS §9.2, source). The realm's
messages (Discord flow failures, refusals, kicks) are its own text in KO's box (Q61)
and come without a title. Options: (a) an empty title, as KO's untitled messages;
(b) a title per message, which needs a new front-end binding and a title from every
caller.
**Default taken (RQ-085):** (a): `front-end.json` sets `Text_title` to the empty
string. A title per message would be wording the realm adds to a KO screen; revisit
if a message needs one.
**Revised (RQ-102):** the maintainer (2026-11-02): "as close to the original as
possible". So (b), from KO's own callers: N3FE version 10 binds `Text_title` to a
`title` action and carries, per kind of message (a closed engine set), a title and
a text that replaces the realm's; `front-end.json`'s `messages` names each as a row
of a KO text table, so a realm-config option (RQ-103) only swaps that data. Read in
the 1264 binary (`specs/KO-FINDINGS.md` §9.2, RQ-102): 1264 titles its login
answer's failures ("Connection failed.", row 2909) and its create failures
("Failed creating character", row 1901), and posts a connection failure, a closed
connection and a refused select untitled. The 1097 choice gives a banned login
(row 2907), a login the realm cannot serve (row 2908, KO's catch-all) and an empty
name (row 1905) KO's title and text, and a refused create KO's title over the
server's wording, which does not say which of KO's reasons (rows 1911, 1912,
1906) it is; every other message (the Discord flow's own, a failed or closed
connection, a kick, a refused select) shows untitled in the realm's words
(`content/front-end.md`, "Moradon", lists each beside its KO box). Three details:
- the item's example, "Failed to connect to login server", is the OpenKO source's
  `_DEBUG` build's title; the 1264 binary has no such string and posts a login
  server it cannot reach untitled (`005bdf00` → `005f8ab0`, title `00674f68`, an
  empty string), so the realm's `connect_failed` stays untitled;
- the 1264 install's `Data/Texts_us.tbl` holds other texts at rows 2907–2909 (a
  stat's description at 2909) than the rows 1264's login answer asks for; the
  login titles and texts are the pinned tree's (1298's) rows, whose binary asks for
  the same rows and whose table holds the login wording;
- a ban in KO's box loses spec 02's end and reason ("Your account is blocked until
  …: …"), KO's text naming neither; taken as KO's (the maintainer's guidance:
  KO's look and feel, a question raised), so the KO screens no longer tell a
  banned player when the ban ends or why. The panels keep spec 02's wording.
  The maintainer, having seen it in a playtest (2026-11-02): "what you have now
  for the ban message is fine", so KO's wording stands (spec 02 and spec 11 say
  a KO front end's package wording may replace spec 02's).

### Q82 — 1264's logo screen before the login

1264's WinMain starts the process on a logo procedure (KO-FINDINGS §9.2, binary
`00602506`): "K2 Network", "presents" and "Knight Online" (`co_usa_logo_us.uif`), each
fading in, holding and fading out on black, 12 s in all, `Snd\bless.wav` from 1 s
faded out over 4 s, any key skipping it, the cursor hidden; then the login. Q56 and
Q61 kept the realm's screens free of KO's service branding, and RQ-085 recorded "the
realm shows no logo screen". The maintainer (2026-11-02), asked whether the 1097
choice shows it: "lets keep it looking and feeling as close to the original as
possible." **Default taken (RQ-101):** the 1097 choice shows it as 1264 does, cooked
from the 1264 install (N3FE version 9's logo section; `content/front-end.md` section
10). Whether a package has the screen is one value, the recipe's `logo` (absent: no
section, the client starts on the login), so a realm-config switch (RQ-103) only has
to drop or keep it. Two details are the realm's, neither changing what a player sees
or hears: the music's 1 s delay counts the client's frame time, as the fades do,
where 1264's procedure reads the performance counter (they part only on a frame
longer than the client's 0.25 s step); and the realm's fade-out sets the stream's
gain each frame, mixed up to 128 ms ahead, where Miles sets the volume each sound
tick. RQ-101 scaled the screen to the window with the canvas, as every realm screen
then was (1264 draws its UI unscaled, centred); since RQ-106 it is drawn unscaled and
centred, as 1264 draws it (below). A version 9 package is a new package, so a new
realm (Q63).

**Decided (maintainer, 2026-11-02), RQ-106:** the front-end screens are not scaled.
The maintainer's playtest: "it looks like we are scaling the UI for the login /
select / create screens. we shouldnt do that I dont think because it looks strange".
Asked whether that should be fixed or a realm owner's choice, the maintainer chose a
realm-owner option, whose default is 1264's look, unscaled. KO 1097, 1264 and
1298 draw their UI on the screen's own pixels and place each screen by the
viewport's size when it loads, never scaling it, and their 3D scenes (the login
orc, the select hall, the create figure) take the viewport's aspect
(KO-FINDINGS §9.3, binary). So the client draws the logo, login, server list,
select, create, loading and message box unscaled where 1264's code places them on
the window (centred, or by the screen edges where KO anchors a node), with black
where no node draws, and hit-tests and draws the cursor on those same pixels; the
3D views are unchanged. N3FE version 11 carries the placements as data
(`content/front-end.md` item 12), so no KO rule is in the client. The realm's
earlier scaling of the canvas to the window is kept behind one switch, the recipe's
`ui_scale` (`"native"`, the default, or `"window"`), which N3FE carries as the
placement section's flag for RQ-103's realm-owner option to set. One robustness
choice: a window smaller than the canvas (1024x768) scales down as before, since
KO's placements would cut the screens off there (the launcher offers 1024x768,
1280x1024 and 1600x1200, Q62). A version 11 package is a new package, so a new
realm (Q63). Where the 1097 choice's select puts its buttons is Q84.

Three robustness choices (RQ-101 review), each keeping 1264's behaviour where the
realm's platform differs from DirectInput's:
- **Which key skips it.** 1264 calls the logo UI's OnKeyPress for each key whose
  press state is set (ProcessUIKeyInput, binary `005f97a0`: the array at input
  `+0x26c`), and that state is the frame's DirectInput edge, up at the last poll and
  down at this one (source `LocalInput.cpp`, `m_bKeyPresses`); its `007ad12e` flag
  only pairs a press with its release, it does not wait for every key to be up. So
  only a press during the screen skips it. The realm drops a key-down stamped before
  the screen's first frame (queued while the client loaded) and a modifier key-down
  (Shift, Ctrl, Alt, GUI, Mode, Level 5) within 100 ms after a focus gain: SDL 3.4's
  Wayland keyboard enter reports each modifier held as the window gains focus as a
  key-down (often the compositor's Super as the window maps), which is no press
  during the screen. Any other key, a modifier included, skips it as in 1264
  (`client/render/front_logo.h`, `logo_key_skips`).
- **When the realm connection starts.** 1264 connects from its login procedure
  (source `GameProcLogIn_1098.cpp`, `CGameProcLogIn::Init`), after the logo; the
  client with a KO front end starts its connection on the first frame that is not
  the logo screen (`WorldClient`'s deferred start), so nothing about the realm
  happens during the logo.
- **Messages.** A message box raised during the logo (a reset connection, a Discord
  alert) waits and shows on the login, the latest one, since 1264 has nothing to
  report before its login runs.

### Q83 — The login scene's clock on a return (KO's own drift)

The maintainer's playtest (2026-11-02): the login's orc and its music (the roars in
`bgm_login.wav`) were out of step, worst after a ban returned the client to the
login. Cause (RQ-104): the client posed the orc on the process's clock, never reset,
so it was out of step on the first entry (by the time the logo screen and the start
took) and on every return, whatever the music did; RQ-105's music start did not
change it. KO 1097 and 1264 make the orc again in each login Init and start its
21.667 s clip at its first frame, ticked by the frame time, and their login track
starts on the same tick on a process's first login (KO-FINDINGS §9.1, binary), so
those two keep time; on a return KO's track waits for its carried timer while the
orc starts again, so KO itself is out of step there. Options: (a) restart the scene
at each entry and keep it on the music's clock; (b) KO's: restart the scene at each
entry on the frame clock, the track on its own timer.
**Default taken (RQ-104):** (a), the robust behaviour that keeps them in step. The
scene's clock (`client/render/scene_clock.h`) starts at 0 on each entry to the login
(the login or the realm list after any other screen) and, while a device plays the
screen's restarting track, is held to the listener's position in that track's period
(within the block the device has taken and plays, whose end is the frames mixed less
those still queued for the device, running on the frame time inside it), so the orc
and the track restart together and keep time through a stall the device runs dry
over; otherwise it runs on the frame time, from where it was if the device closes. With RQ-105's default (the track starts at once)
the orc starts at its first frame on every entry, as KO's. With
`AudioMixer::carry_music_clock` on (RQ-103's option, KO's carried timer) the orc
follows the carried period instead of restarting at its first frame, so it is in step
when the track starts; KO would restart the orc and leave the track behind. No format
change.

### Q84 — Where the 1097 choice's select puts its buttons

RQ-106 places each screen as KO's code does at the window's size (Q82). The 1097
choice draws 1264's layouts (RQ-085), and three codes place the select's buttons
differently (KO-FINDINGS §9.3, binary and source): 1264's select Init (`004448f0`)
puts the previous and next buttons at `(W/2) ∓ 100 ∓ W·26/1024` (the previous one by
its right edge), the exit button centred 10 px above the bottom and the back button
centred 10 px above the exit; 1097's (`0043faf0`) and the source scale the buttons'
x by the window's width over 1024 and put the exit 10 px above the bottom (the source
the back 15 px above it; 1097's layout has none). At 1024x768
the two part by a few pixels (the next button at 638 rather than 644, the exit and
back at 412 rather than 418 and 419). Options: (a) 1264's code for 1264's layouts;
(b) 1097's code on 1264's layouts. **Default taken (RQ-106):** (a), since the layout
was drawn for the code that places it and the choice already shows 1264's screens;
the recipe's `moves` say it, so (b) is a recipe change.
**Decided (maintainer, 2026-11-02):** (a), "Use 1264's placement". The 1298 recipe
(not offered) takes the same placements: its select layout is the same file, which
1298's own code never places (KO-FINDINGS §9.3).

### Q85 — The login bar while the Discord login waits

RQ-108 takes 1264's SetVisibleLogInUIs for the 1097 choice (KO-FINDINGS §9.4):
1264 hides its login bar from a login press until the login's answer and shows its
copyright line instead; a failure shows the bar again and a success keeps the line
into the server list. The realm's login is the Discord flow, so its wait is the
browser step (up to 5 minutes) and the code, where 1264's is one round trip to the
login server. KO has no Discord step, so it does not settle what the bar does during
that wait. Options: (a) hide the bar, as 1264 does from the press, for the whole
wait, the line shown; the bar's Cancel cannot be clicked then, and ESC cancels the
browser step as before; (b) keep the bar during the browser step (Cancel clickable,
no line) and hide it only once the code goes to the realm. **Default taken
(RQ-108):** (a), as close to 1264 as the flow allows: a press always hides the bar
until the flow ends; a stored session's login, which sends no press, does the same,
as 1264's auto-login would. A login server 1264 cannot reach shows its box over the
line and quits on OK; the realm's box over an unreachable realm returns to the
login, so it takes a failed answer's look (the bar, no line). (b) is a client change
in `client/render/viewer.cpp`'s login_waiting, not package data.
**Decided (maintainer, 2026-11-02):** (a), "Hide the bar, as 1264": the bar is
hidden for the whole Discord wait and the copyright line shown, ESC cancelling the
browser step. Only a layout that binds `login_closed` does this; one without it
(the 1298 recipe) keeps its bar, as before.
*RQ-110 (KO-FINDINGS §9.5):* 1298 hides its bar the same way, so every layout now
does; see Q86.

### Q86 — The 1298 recipe's login while a login waits

RQ-110 read 1298's binary (KO-FINDINGS §9.5): its login is the nation's intro
layout, which has no copyright line, and it hides its login bar from a login press
until a failed answer (`005f74c0`, `005f7b50`), as 1264 does. The 1298 recipe (not
offered) still cooks 1264's `co_login_us.uif` as its login until 1298's intro is data
(RQ-088). Taking 1298's look, the recipe hides `Text_Rights`, and the client hides
the login group while a login is under way whether the layout binds `login_closed`
or not, so the 1298 recipe shows neither the bar nor a line for the whole Discord
wait (up to 5 minutes; ESC cancels, and the realm's message boxes still show), where
1298's own wait is one round trip. Options: (a) as 1298: nothing in the bar's place;
(b) keep RQ-108's rule for a layout without a line, its bar up through a login (not
1298's); (c) bind 1264's line there as the 1097 choice does (1264's look, not
1298's). **Default taken (RQ-110):** (a), "as close to the original as possible"
(Q85's decision for the wait applied to 1298). (b) is the old `closes` argument of
`client/render/front_login.h`; (c) is the recipe's binding and move, as
`games/moradon/front-end.json` has them.
**Decided (maintainer, 2026-11-02):** (a), "Hide the bar, as 1298": under the 1298
recipe the bar is hidden for the whole login and nothing takes its place, ESC
cancelling; one rule for every front end.

### Q87 — The 1298 recipe's select bar where the realm differs from 1298

RQ-109 read 1298's select bar (KO-FINDINGS §9.6) and the 1298 recipe (not offered)
now draws it at 1298's place with its Start, Create and Delete buttons and its info
texts (N3FE version 13). Three of its buttons and its arrows do what the realm's
other selects do, not what 1298 does:
- **Exit.** 1298 asks "Are you sure you want to exit?" (row 1502) with Yes and No
  (`MB_YESNO`, `BEHAVIOR_EXIT`); the realm's message box has one button, so Exit
  leaves at once, as the 1097 choice's does.
- **Back.** 1298 disconnects and returns to its login with the flag that connects
  and opens the server list at once (`005f6bca`–`005f6c05`), so its Back lands on the
  server list; the realm's Back drops the connection and returns to the login.
- **The arrows.** 1298 never hides one arrow; at the end of the row its click does
  nothing. The realm hides the arrow with no neighbour, for every layout.
- **Create from an occupied slot.** 1298 flies the camera to the first empty slot
  (`ka_left_right`, `ka_right_left` among its paths) while its in-select create
  opens; the realm puts the camera on that slot and opens its own create screen.
**Default taken (RQ-109):** keep the realm's behaviour for all four, as package data
cannot yet say otherwise; each 1298 behaviour is a client change (a yes/no message
box, a Back that opens the realm list, an arrow rule per layout, the two uncooked
paths) and is proposed as its own item.
**Exit decided (RQ-111, KO-FINDINGS §9.7):** N3FE version 14 carries a yes/no box: a
package that names the message `exit_confirm` makes the select's Exit ask in the
message box with its `yes` and `no` buttons (ENTER Yes, ESC No; Yes leaves). The 1298
recipe draws 1298's own box, `El_MessageBox_us.uif`, and asks row 1502 untitled, as
1298 does; its Yes and No are KO's buttons as KO labels them, "O  K" and "Cancel"
(Q61). The 1097 choice names no `exit_confirm`, so its Exit still leaves at once;
whether 1264's select Exit (the screens the 1097 choice draws) asks too was not read
(the source's `UICharacterSelect.cpp` posts the same box) and is proposed as its own
item. Back, the arrows and Create from an occupied slot stay as above.
