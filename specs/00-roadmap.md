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
a `world.*` token gets `403` on those routes; `revoke` takes effect on the next request.

## M2 — Connection hardening (spec 01)

- Per-IP concurrent cap, per-IP connect rate, pre-handshake idle timeout, global cap.
- Drain state honoured at accept time.
- Counters exposed on `/v1/realm/status`.

**Done when:** a load script opening 500 connections from one IP sees exactly the
configured cap admitted and the rest refused in < 10 ms each, with no TLS work spent on
the refused ones.

## M3 — Discord login and sessions (spec 02)

- Discord OAuth2 code exchange, account upsert, session mint.
- Session presentation on reconnect, expiry, concurrency cap, revocation.
- `account.kick` / `account.ban` / `account.unban` routes.
- Client-side OAuth flow with loopback redirect; new wire messages + goldens.

**Done when:** a fresh player logs in via Discord once, reconnects without Discord for
30 days (clock-advanced in test), and a `/ban` from a `curl` ends their live connection
and refuses their token.

## M4 — Launcher and manifest (spec 04)

- `manifest.json` schema and a hand-written one in a test Release.
- Launcher: fetch, verify, install, self-update, start client.
- Client "update via launcher" exit path (n3e already fails the handshake on mismatch;
  the launcher must surface it).

**Done when:** on a clean machine, downloading one binary and running it ends with the
game client connected to the realm.

## M4b — Windows client (spec 04 §Build, spec 06 §smoke)

- CMake: `find_package(SDL3 CONFIG)` via vcpkg on Windows; keep pkg-config on Linux.
- POSIX audit of `client/`; `%APPDATA%` paths; `ShellExecute` for the browser.
- TLS: load the Windows `ROOT` store into OpenSSL's trust store at startup.
- `n3e-client --smoke-local`: load package, init SDL/GL (software GL ok), parse
  `realm.json`, build the OAuth URL, exit 0. Platform-independent; used by CI on both OSes.
- Launcher `x86_64-pc-windows-msvc` build; player docs with the SmartScreen note (Q26).

**Done when:** `windows-latest` and `ubuntu-latest` both produce artifacts and pass
`--smoke-local`; a canary player on Windows logs in end-to-end.

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

## M7 — Production cutover (spec 07)

- VPS provisioned at a provider with always-on L3/L4 scrubbing.
- Real domain, Let's Encrypt, cert renewal → server restart hook.
- Secrets laid down per O5; ops token as a root-only file.
- Nightly `pg_dump` off-box; one restore rehearsal.
- Rebuild runbook executed once on a scratch VPS.

**Done when:** a stranger with the Discord invite can download the launcher, log in,
and play, and the rebuild runbook has been followed successfully once.

## M8 — Docs on Pages (spec 08)

Small and independent; can be done any time after M5 exists. Listed last because
nothing depends on it.

## Explicitly deferred

Rotation of session tokens, JWTs, TCP relay tier, multi-region, macOS client, code
signing (Q26), a Rust client rewrite (deferred until the C++ client is the live
reference; recorded arguments: cross-compilation, shared collision crate), in-game
Discord role sync, anything the Bot does with AI.
