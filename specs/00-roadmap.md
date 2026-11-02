# 00 — Roadmap and build order

Milestones are ordered by dependency, then by risk retired per unit of work. Each
milestone ends in something a human can exercise end-to-end. Do not start a milestone
whose blocking question in [`QUESTIONS.md`](QUESTIONS.md) is unanswered.

## P — Pre-phase, in `n3e` — **done 2026-10-30**

Headless Ghidra pass over the P1/P2 rows of `KO-REVERSING-PRIORITIES.md`; results in
`KO-FINDINGS.md`. Q6 confirmed, Q13/Q14 resolved, failure wording fixed. The `n3e`
loop is paused; `n3e` is archived.

## M0 — Migration (spec 09) — **done 2026-10-30**

- Clean, pruned import of `n3e` at a pinned commit into `N3E-Realm`.
- `UPSTREAM.md` pins; raw KO assets as one sha256-pinned tarball, fetched, never committed.
- `AGENTS.md` rewritten; the user starts a **new** loop on `N3E-Realm`.

**Done when:** `make test` / `make live` pass and `make live-ko` has 0 failed from a
clean clone (spec 09 acceptance); the local stack runs Moradon; no submodules; no
parity/Ghidra remnants. Evidence in spec 09, "What the import actually found".

## M1 — Admin API and tokens (spec 03, minus world operations)

The Bot, CD and sessions all depend on it, so it goes first.

- Postgres schema for `admin_tokens`; `admin_audit.token_name`.
- `n3e-server admin mint|revoke|list` CLI.
- Loopback HTTP server, bearer auth, permission check per route.
- `GET /v1/realm/status`, `POST /v1/realm/drain`, `POST /v1/realm/resume`,
  `POST /v1/realm/notice`.
- Redis Stream `realm:events` writer.

**Done when:** `curl` with a `realm.*` token can drain/resume/status a running stack;
a `world.*` token gets `403` on those routes; `revoke` takes effect within the 10 s token
cache (spec 03; corrected from "the next request", which the cache rules out).
Evidence: `tests/admin_api_live.py` (spec 03 tests 1–5, 6b notice, 8, 9, 10).

## M2 — Connection hardening (spec 01)

- Per-IP concurrent cap, per-IP connect rate, pre-handshake idle timeout, global cap.
- Drain state honoured at accept time.
- Counters exposed on `/v1/realm/status`.

**Done when:** a load script opening 500 connections from one IP sees exactly the
configured cap admitted and the rest refused in < 10 ms each, with no TLS work spent on
the refused ones. Evidence: `tests/connections_live.py` (spec 01 tests 1–7).

## M3 — Discord login and sessions (spec 02)

- Discord OAuth2 code exchange, account upsert, session mint.
- Session presentation on reconnect, expiry, concurrency cap, revocation.
- `account.kick` / `account.ban` / `account.unban` routes.
- Client-side OAuth flow with loopback redirect; new wire messages + goldens.

**Done when:** a fresh player logs in via Discord once, reconnects without Discord for
30 days (clock-advanced in test), and a `/ban` from a `curl` ends their live connection
and refuses their token.

Evidence: `tests/discord_login_live.py` (spec 02 tests 1–9 against a loopback stand-in
for Discord, the test client's browser flow, restart and expiry; spec 03 account
routes). A real Discord application round trip is the maintainer's manual check
(README, "Discord login").

## M4 — Launcher and manifest (spec 04)

- `manifest.json` schema and a hand-written one in a test Release.
- Launcher: fetch, verify, install, self-update, start client.
- Client "update via launcher" exit path (n3e already fails the handshake on mismatch;
  the launcher must surface it).

**Done when:** on a clean machine, downloading one binary and running it ends with the
game client connected to the realm.

Evidence: `tests/launcher_live.py` (spec 04 tests 1–11 against releases on a loopback
file server; its graphical branch installs the real test client and the demo package
from a release and connects to a native server, and a realm with other content makes
the client exit 3 and the launcher 20). The client's exit 3 is in `client/network/world.cpp`
and `client/render/viewer.cpp`. Open: the done-when needs a published Release (Q45),
which M5 produces; the static musl build is unverified here (no musl C compiler).

## M4b — Windows client (spec 04 §Build, spec 06 §smoke)

- CMake: `find_package(SDL3 CONFIG)` via vcpkg on Windows; keep pkg-config on Linux.
- POSIX audit of `client/`; `%APPDATA%` paths; `ShellExecute` for the browser.
- TLS: load the Windows `ROOT` store into OpenSSL's trust store at startup.
- `n3e-client --self-test --realm realm.json` (first planned as `--smoke-local`; the
  player build carries no `smoke` string, PQ-006): load package, init SDL/GL (software
  GL ok), parse `realm.json`, build the OAuth URL, exit 0. Platform-independent; used by
  CI on both OSes.
- Launcher `x86_64-pc-windows-msvc` build; player docs with the SmartScreen note (Q26).

**Done when:** `windows-latest` and `ubuntu-latest` both produce artifacts and pass
`--self-test`; a canary player on Windows logs in end-to-end. Real-GPU Windows
testing stays manual: the maintainer runs it on their own Windows machine, periodically.

Evidence so far: CI run 41236996414 (c379da0), `client` on windows-2025 and
ubuntu-24.04: build, package, launcher install and `--self-test` on Mesa llvmpipe, all
green (Windows 25 min with a cold vcpkg cache, now saved). Open: the canary Windows
login (`docs/manual-testing.md` W1–W7).

## M4c — KO front end (spec 11) — **implemented; the manual round is open**

- `ko_front_end` cook: intro scene, select hall, the login, server list, select, create
  and loading layouts and the OK box, into an optional `front-end.bin` (N3FE, engine
  42, `content/front-end.md`).
- Client front-end module drawing it; panels stay for packages without it.
- `Character.level` on the wire; the character limit from the package.
- The player path (local release, Windows kit, `tools/local-realm`, docs) moves from
  `demo` to `moradon`.

**Done when:** a player starts on KO's login scene, logs in with Discord, picks the
realm, creates and selects a character in the Karus hall, and loads into Moradon,
on Linux and Windows; spec 11 tests 1–7 pass.

Evidence so far (the maintainer's GPU workstation, offscreen): spec 11 tests 1–2
(`tests/front_end.py`) and 4 (`tests/check.py`) in `make test`, exit 0; test 3 is the
existing suites (`make live`, LIVE_OK 73/73, graphical); tests 5–7
(`tests/front_end_live.py`, `tests/front_end_flow_live.py`) pass on the Moradon
package. The 1097 `--features` bake pin, not recut at M4c (no 1097 install there),
was recut by RQ-020 once the install was unpacked (`tests/ko_bake_pin.py`). Open: the
manual round on Linux and Windows (`docs/manual-testing.md` L1–L12, W1–W7), Q57–Q60.

## M5 — CD (spec 06)

- Workflow: cron + `workflow_dispatch(force)`.
- Build server/bot images, build client, cook Moradon content from fetched KO assets,
  write manifest, publish Release + Pages.
- Headless `make test` gate.
- Gated deploy over ssh: migrate, players-online check, drain, restart, tag.
- `deploy:pending` record on skip.

**Done when:** a commit to `master` reaches the VPS on the next cron with nobody online,
and is skipped (with `deploy:pending` set) when a test client is connected.

## M5b — Content layer (spec 10)

- Raw KO tarball + `fetch-ko-assets.sh` (done in M0); `ko:` prefix; per-file content
  index and store in CD; Launcher per-file download (M4 dependency — do the index first).
- Registry kinds `rate.*`, `event.active`, timed reversion; `events.json`; spawn names.
- `GET /v1/world/catalog`, `POST /v1/world/event[/stop]`, named spawn.
- `CONTRIBUTING.md`, `BALANCE.md`, PR template, CODEOWNERS, content CI checks.

**Done when:** a content PR adding a glTF asset and a preset passes CI, deploys, the
Launcher downloads only the new files, and `/event` activates the preset live.

## M6 — Bot (spec 05)

- Gateway connection, slash command registration, role gating.
- `/status`, `/deploy`, `/kick`, `/ban`, `/notice`.
- `realm:events` consumer group → announcements channel.
- Daily `deploy:pending` nag; fail-fast when the admin API is down.
- `/boss`, `/event`, `/event-stop` driven by the realm catalog (M5b).

**Done when:** `/deploy` from Discord triggers a CD run that announces, drains, restarts,
and posts "realm is back" from the event stream.

Evidence: `tests/bot_live.py` (spec 05 tests 1-4 and 6-10 against stand-ins for Discord
and GitHub; 5/5b partial until M5b) and a session against a real test guild (commands
registered, events posted). The done-when needs CD (M5, spec 06): `/deploy` dispatches
the workflow and "Realm is up" is posted after a drain, but the CD run between them
does not exist yet.

## M7 — Production cutover (spec 07)

- VPS provisioned at a provider with always-on L3/L4 scrubbing.
- Real domain, Let's Encrypt, cert renewal → server restart hook.
- Secrets laid down per O5; ops token as a root-only file.
- Nightly `pg_dump` off-box; one restore rehearsal.
- Rebuild runbook executed once on a scratch VPS.

**Done when:** a stranger with the Discord invite can download the launcher, log in,
and play, and the rebuild runbook has been followed successfully once.

## M7a — Home host behind Cloudflare (spec 12) — **done 2026-11-01**

The realm runs on the maintainer's machine (the realm host) instead of a VPS (Q64).

- Done first, LAN only: `deploy/compose.prod.yaml` (spec 07's production stack) and
  `tools/host-realm` on the host; `deploy/HOST.md`.
- `realm-edge` bridge, the client's WebSocket transport, `edge` in the realm profile.
- The realm's Cloudflare Tunnel; Let's Encrypt via DNS-01 on Cloudflare DNS; releases
  through the tunnel until M5 publishes GitHub Releases.

**Done when:** spec 12 tests 1–6 pass: a player outside the home network downloads the
launcher, logs in and plays through `wss://play.openko.net`, and the host has no
forwarded port and no public DNS record naming it.

Evidence so far (this workstation): `tests/edge_live.py --graphical` (tests 1–4),
`cargo test -p realm-edge`, `make test`, and `discord_login_live`, `launcher_live` and
`front_end_flow_live` graphical (test 5); test 6 by the maintainer on 2026-11-01, from
outside the home network on Linux and Windows through `wss://play.openko.net`.

## M8 — Docs on Pages (spec 08)

Small and independent; can be done any time after M5 exists. Listed last because
nothing depends on it.

## Explicitly deferred

Rotation of session tokens, JWTs, TCP relay tier, multi-region, macOS client, code
signing (Q26), a Rust client rewrite (deferred until the C++ client is the live
reference; recorded arguments: cross-compilation, shared collision crate), in-game
Discord role sync, anything the Bot does with AI.
