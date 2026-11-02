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

*Superseded by Q61: KO's copyright line is kept.*

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

The maintainer chose on 2026-11-01 to host on their own machine (`gn100`) rather than
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
