# N3E Realm — implementation specs

These specs turn [`../docs/architecture.md`](../docs/architecture.md) into buildable work. They are
written for an agent working in **`N3E-Realm`**, the product repo. `N3E-Realm` starts as
a clean, pruned import of `n3e` (spec 09); after that, `n3e` is archived and private, nothing
here depends on it, and all code changes happen in `N3E-Realm`.
Before the import, the only work in `n3e` is the reversing pre-phase in
[`KO-REVERSING-PRIORITIES.md`](KO-REVERSING-PRIORITIES.md).

## How to use these specs

1. Read `../docs/architecture.md` first. It holds the decisions; the specs hold the detail.
   Where they disagree, the spec is wrong — fix the spec, do not silently reinterpret.
2. Read [`00-roadmap.md`](00-roadmap.md) for build order and milestones.
3. Each component spec is self-contained: purpose, scope, interfaces, behaviour,
   failure modes, security, acceptance tests, and a pointer to its open questions.
4. Interfaces (HTTP paths, JSON fields, Redis keys, env vars, CLI verbs, SQL tables) are
   **normative**. Internal structure, crate choice, and file layout are the agent's.
5. "Reference" callouts name existing files in this repo (imported from `n3e`) to read
   for the matching behaviour.
6. When something is underspecified, check `QUESTIONS.md`. If it's not there, add it
   under "Raised during implementation" and pick the most conservative interpretation.

## Components

| # | Spec | Component | Lives in |
|---|---|---|---|
| 09 | [`09-migration.md`](09-migration.md) | One-time import of `n3e` into `N3E-Realm`; prune list; pins | — (first) |
| 01 | [`01-connection-hardening.md`](01-connection-hardening.md) | Accept-time limits in front of the game wire | `server/` (accept loop) |
| 02 | [`02-auth-sessions.md`](02-auth-sessions.md) | Discord login, session tokens, accounts, bans | `server/`, `client/`, `protocol/` |
| 03 | [`03-admin-api.md`](03-admin-api.md) | Loopback admin API, permission-scoped tokens, event stream | `server/` (second HTTP listener) |
| 04 | [`04-launcher.md`](04-launcher.md) | Player-side launcher + Release manifest | `N3E-Realm/launcher` |
| 05 | [`05-bot.md`](05-bot.md) | Discord bot | `N3E-Realm/bot` |
| 06 | [`06-cd.md`](06-cd.md) | GitHub Actions CD: build, publish, gated deploy | `N3E-Realm/.github` |
| 07 | [`07-deploy.md`](07-deploy.md) | VPS: compose, TLS, secrets, backups, rollback, rebuild runbook | `N3E-Realm/deploy` |
| 08 | [`08-docs.md`](08-docs.md) | AI-friendly docs on Pages | `N3E-Realm/docs` |
| 10 | [`10-content.md`](10-content.md) | Package vs. live tunables, raw KO input, event presets, contributions, forks | `games/`, `tools/assetc`, `server/` (registry kinds) |
| 11 | [`11-front-end.md`](11-front-end.md) | KO front end: intro and login, server list, character select and create, loading; the player path moves to Moradon | `tools/assetc`, `client/`, `games/moradon` |
| 12 | [`12-edge.md`](12-edge.md) | The game wire as a WebSocket through Cloudflare, for a host that must stay private (proposed) | `edge/`, `client/`, `deploy/` |
| — | [`QUESTIONS.md`](QUESTIONS.md) | Open questions with defaults; Q1–Q3 block M1 | — |
| — | [`KO-FINDINGS.md`](KO-FINDINGS.md) | Binary-confirmed KO behaviour the specs rely on (shutdown countdown, rate events, notices, sanctions, wording) | — |
| — | [`KO-REVERSING-PRIORITIES.md`](KO-REVERSING-PRIORITIES.md) | Which KO operator surfaces the architecture depends on, and what still needs binary confirmation | — |

## Conventions

- **Names.** The product is "N3E Realm". New binaries/images are `realm-bot`,
  `realm-launcher`. The engine binaries stay `n3e-server`, `n3e-client`.
- **Config** is environment variables: `N3E_*` for the engine (existing convention),
  `REALM_*` for bot/launcher, `DISCORD_*` for Discord. Secrets are never in argv.
- **Ports.** `7777` game wire (public). `7780` admin API (loopback). `8080` health
  (compose network only).
- **Time** is UTC everywhere; timestamps are RFC 3339 in JSON, `timestamptz` in SQL.
- **IDs.** Discord IDs are strings (snowflakes exceed JS integer range). Internal IDs are
  `bigint`.
- **Errors.** HTTP APIs return `{"error": "<machine_code>", "detail": "<human>"}`.
- **Logging.** One line per event, key=value, no secrets, no tokens (not even hashed —
  use the token *name*).
- **Tests.** Each spec lists acceptance tests. They are the definition of done. Unit
  tests beyond that are the agent's call; prefer tests of behaviour across a boundary
  over tests that mirror code.
- **Postgres owns durable state. Redis is never the only copy of anything that matters.**
  (Same rule as `n3e`; it applies here too.)

## Glossary

| Term | Meaning |
|---|---|
| Realm | One running game server process = one world. There is exactly one. |
| Game wire | The length-prefixed protobuf-over-TLS protocol on `:7777` (`n3e/protocol/wire.proto`). |
| Content package | A cooked asset directory produced by `tools/assetc`. Identity is `sha256(release.bin)`, hex, 64 chars. |
| Revision | The engine's live, Postgres-backed property layer (`content/editing.md`); where rates, presets and placements change without a restart. |
| Preset | A named revision patch with a duration, defined in the package (`events.json`); activated by operators. |
| Realm profile | A Launcher entry: name + manifest URL. One Launcher, many realms (forks). |
| Release | A GitHub Release carrying a `manifest.json`, client binaries, a launcher binary, and a content package archive. |
| Manifest | `manifest.json` in a Release; what "latest" means to the Launcher (spec 04). |
| Session token | The player's credential after first login (spec 02). |
| Admin token | A permission-scoped credential for the admin API (spec 03). |
| Drain | Admissions closed, existing connections allowed to finish; precedes a restart. |

## Reference map

Read these before the matching spec. Paths are relative to the repo root.

| Topic | Files |
|---|---|
| Wire protocol, framing, handshake | `protocol/README.md`, `protocol/wire.proto` |
| Accept loop, deadlines, 64-socket cap | `server/src/network.rs` |
| Login, scrypt, Redis throttle | `server/src/accounts.rs`, `server/src/cache.rs` |
| In-game admin operations and capabilities | `server/src/administration.rs`, `deploy/006-administration.sql` |
| Accounts / characters / roles schema | `deploy/002-multiplayer.sql` |
| Health endpoint | `server/src/main.rs` (`/live`, `/ready`) |
| Server CLI (`migrate`, `account-create`, `role`) | `server/src/main.rs` |
| Content cooking and hash | `tools/assetc/main.py`, `server/src/content.rs`, `content/README.md` |
| Revision layer / editor | `content/editing.md`, `administration.rs` (`publish`/`revert`/`spawn`), `deploy/006-administration.sql` |
| glTF import, provenance convention | `tools/assetc/gltf.py`, `games/demo/PROVENANCE.md` |
| Client CLI (`PACKAGE_DIR --connect --ca`) | `client/render/viewer.cpp` |
| Compose, Dockerfile, TLS mounts | `compose.yaml`, `deploy/Dockerfile`, `deploy/local-ca.sh` |
| Build tooling | `Makefile`, `CMakeLists.txt`, `tools/bootstrap.sh` |
