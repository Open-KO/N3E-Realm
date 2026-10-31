# 03 — Admin API, admin tokens, event stream

Implements O7 (Admin tokens), flow ⑤⑥, and the realm side of O8 (Deploy gating) from
`architecture.md`. Lives in the game server (after migration, spec 09).

## Purpose

One loopback HTTP API that the Bot and CD call, authenticated by permission-scoped
tokens, plus a Redis Stream the server writes to and the Bot reads from.

## Scope

In: token model and CLI; HTTP routes for realm, account and world operations; the
`realm:events` stream; the `deploy:pending` record. Out: anything player-facing; any
path that bypasses the server's existing authorisation and audit for world mutations.

## Where it lives

A second HTTP listener in `n3e-server` next to the existing health listener
(`main.rs` `/live` `/ready`), on its own task, off the tick. World routes call the same
internal functions `AdminRequest` handlers use (`administration::execute`), with the
acting identity recorded in `admin_audit` as the token name (see "Audit identity").

## Interfaces

### Configuration

| Env var | Default | Meaning |
|---|---|---|
| `N3E_ADMIN_LISTEN` | `127.0.0.1:7780` | Must resolve to a loopback or RFC 1918 address; refuse to start otherwise. |
| `REDIS_ADDRESS` | *(existing)* | Also used for `realm:events` and `realm:deploy:pending`. |

### Permissions

Flat strings. Each route requires exactly one. Globs are accepted **only** by `mint` and
expanded there; a stored token holds concrete permissions.

| Permission | Route(s) |
|---|---|
| `realm.status` | `GET /v1/realm/status` |
| `realm.drain` | `POST /v1/realm/drain`, `POST /v1/realm/resume` |
| `realm.notice` | `POST /v1/realm/notice` |
| `realm.deploy` | `GET/PUT/DELETE /v1/realm/deploy-pending` |
| `account.lookup` | `GET /v1/accounts/by-discord/{discord_id}`, `GET /v1/accounts/{id}` |
| `account.kick` | `POST /v1/accounts/{id}/kick` |
| `account.ban` | `POST /v1/accounts/{id}/ban`, `POST /v1/accounts/{id}/unban` |
| `account.mute` | `POST /v1/accounts/{id}/mute`, `POST /v1/accounts/{id}/unmute` |
| `world.catalog` | `GET /v1/world/catalog` |
| `world.spawn` | `POST /v1/world/spawn` |
| `world.kill` | `POST /v1/world/kill` |
| `world.event` | `POST /v1/world/event`, `POST /v1/world/event/stop` |
| `world.set` | `POST /v1/world/set` — direct revision patch (power-user; the Bot does not expose it in v1) |
| `token.mint`, `token.revoke` | Reserved; no routes in this version. Minting is CLI-only. |

There is deliberately no `realm.restart`: restarting is a compose action CD performs
over ssh.

Today's tokens: `bot` = `world.catalog`, `world.spawn`, `world.kill`, `world.event`,
`account.*`, `realm.status`, `realm.notice` (not `world.set`); `ops` = `realm.*`.

### In-game notice (engine side)

A new internal broadcast: `Chat{ text, notice: 1|2 }` to every in-world session, drawn
by the client as a yellow notice line (1) or a bold centre banner (2) (new `Chat.notice`
uint32; additive wire field, 0 = ordinary chat). Used by `realm/notice` and by the server itself for preset start/stop and
drain. World-entry notice: a new `Notice { repeated string lines }` message sent after
`SelectCharacter` succeeds, drawn in a dismissible panel top-right (KO placement).

### Postgres (new migration)

```sql
CREATE TABLE admin_tokens (
  name         text PRIMARY KEY CHECK (name ~ '^[a-z][a-z0-9-]{0,31}$'),
  token_hash   bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  permissions  text[] NOT NULL CHECK (array_length(permissions, 1) >= 1),
  created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_used_at timestamptz
);
```

### CLI (subcommands of `n3e-server`, like `migrate` / `account-create`)

```
n3e-server admin mint   --name NAME --perm PERM [--perm PERM ...]   # prints the token once
n3e-server admin revoke --name NAME                                  # exit 0 even if absent
n3e-server admin list                                                # name, perms, created, last_used; never hashes
```

Talks to Postgres directly; needs no token. `mint` on an existing name → exit 2
("exists; revoke first"). Token: 32 CSPRNG bytes → base64url, no padding. Stored:
`sha256(raw bytes)`.

### HTTP conventions

- `Authorization: Bearer <token>`. Missing/unknown → `401 {"error":"unauthenticated"}`.
  Lacking the permission → `403 {"error":"forbidden","detail":"needs realm.drain"}`.
- `last_used_at` updated at most once per minute per token.
- JSON both ways. Mutations return `200` with resulting state, or `202` when async
  (world operations run on the next tick).
- Unknown route `404`; method mismatch `405`; body limit 16 KiB; read timeout 5 s.
- Token cache: verified tokens are cached in memory for 10 s so `status` polling is not
  a DB query per call; `revoke` therefore takes ≤ 10 s to bite (acceptable; documented).

### Routes

**`GET /v1/realm/status`** → `200`
```json
{
  "version": "v2026.10.30-abc1234",
  "content_hash": "…64 hex…",
  "players": 12,
  "draining": false,
  "ready": true,
  "uptime_s": 86400,
  "connections": { "...": "spec 01" },
  "deploy_pending": null,
  "redis": true
}
```
`players` = sockets past login (including character select). `ready` = the same
predicate as `/ready`. `version` = build version baked at compile time (`git describe`,
spec 06). `content_hash` = loaded package hash (`sha256(release.bin)`).

**`POST /v1/realm/drain`** `{"reason": "deploy v…"}` → `200 {draining:true, players:N}`.
Idempotent. Emits `realm.draining`.

**`POST /v1/realm/resume`** → `200 {draining:false}`. Idempotent. Emits `realm.resumed`.

**`POST /v1/realm/notice`** `{"text": "Restart in 2 minutes", "level": "info|warn", "in_game": true}` → `202`.
Emits `notice` (Discord via the Bot). With `in_game: true` (default) the server also
broadcasts the text to every in-world session. `level` selects KO's two presentations
(`KO-FINDINGS.md` §1–2): `info` → yellow **public notice** chat line (`#### NOTICE : %s
####`, the shutdown-countdown style); `warn` → bold **centre-screen banner** (the
event-start style). The engine carries this as `Chat.notice` = 1 (line) or 2 (banner). `text` ≤ 500 chars (in-game
copy truncated to 256 to fit the chat bound), no control characters. The CD countdown
calls this once per minute (spec 06).

**`PUT /v1/realm/motd`** `{"lines": ["Welcome…", "…"]}` (≤ 20 lines × 127 bytes, KO's
bound) → `200`; **`GET`** → current. Stored as a revision property; shown to each
player on world entry together with the active preset's `announce` line (KO's login
notice `2e`, `KO-FINDINGS.md` §3). Permission `realm.notice`.

**`GET /v1/realm/deploy-pending`** → `200 {since, commits_behind, head}` or `204`.
**`PUT /v1/realm/deploy-pending`** `{since, commits_behind, head}` → `200`. Emits
`deploy.pending` only if absent before or `head` changed.
**`DELETE /v1/realm/deploy-pending`** → `204`.
Stored in Redis `realm:deploy:pending` (JSON). Redis is acceptable: losing it costs one
skipped deploy.

**`GET /v1/accounts/by-discord/{discord_id}`**, **`GET /v1/accounts/{id}`** → `200`
`{id, discord_id, discord_name, created_at, last_login_at, banned_at, banned_until,
ban_reason, sessions, online, characters: [{id, name}]}` or `404`.

**`POST /v1/accounts/{id}/kick`** `{"reason"}` → `200 {connections_closed}`. Emits `account.kicked`.
**`POST /v1/accounts/{id}/ban`** `{"reason", "until": "<rfc3339>|null"}` → `200 {banned_until}`. Emits `account.banned`.
**`POST /v1/accounts/{id}/unban`** → `200`. Emits `account.unbanned`.
**`POST /v1/accounts/{id}/mute`** `{"reason", "until": "<rfc3339>|null"}` → `200 {muted_until}`.
**`POST /v1/accounts/{id}/unmute`** → `200`. Emit `account.muted` / `account.unmuted`.
Mute drops the player's chat server-side (KO authority 11 semantics) but, unlike KO,
tells the player once per session on their first dropped message.

**`GET /v1/world/catalog`** → `200`
```json
{
  "content_hash": "…",
  "spawns":  [ { "index": 3, "name": "ironfang", "announce": "Ironfang has appeared…" } ],
  "presets": [ { "id": "weekend-exp", "title": "Weekend XP", "duration_s": 172800, "set": {"rate.exp": 1.5} } ],
  "properties": [ { "key": "rate.exp", "value": 1.0, "min": 0.1, "max": 10 } ],
  "active_event": null
}
```
Everything the Bot needs to build its command choices, straight from the loaded package
and the current revision (spec 10). Cached in memory; refreshed on revision change.

**`POST /v1/world/spawn`** `{"name": "ironfang" | "spawn": 3, "reason": "Saturday boss", "duration_s": 3600}` → `202 {request_id}`.
Resolves `name` via the catalog; `spawn` is the index into the package's spawn table —
what the existing `spawn` operation takes. `base` is filled with the loaded content
hash. `duration_s` is bounded by the engine (Q21). Result → `world.spawn.result` on the
stream, carrying the `announce` text.

**`POST /v1/world/event`** `{"preset": "weekend-exp", "reason": "…"}` → `202 {request_id}`.
Publishes the preset's patch as a revision with an expiry (spec 10). Only one preset
active at a time; a second → `409 {"error":"event_active"}`. Emits `world.event.started`.
**`POST /v1/world/event/stop`** `{"reason"}` → `202`. Reverts; emits `world.event.stopped`.

**`POST /v1/world/kill`** `{"entity": 12345, "reason"}` → `202 {request_id}`. Existing
`kill` operation.

**`POST /v1/world/set`** `{"patch": {"rate.exp": 1.2}, "reason": "…"}` → `202`. Direct
revision publish, bounds-checked by the registry. Exists so an operator can act without
a preset; not exposed by the Bot in v1.

### Audit identity

`administration::execute` today authorises against an authenticated **character**'s
roles and writes `admin_audit(account_id, character_id, …)`. Admin-token calls have no
character. Add a nullable `token_name text` column to `admin_audit` and make
`character_id` nullable **only for rows with `token_name` set** (CHECK). Authorisation
for token calls is the permission check at the route; the existing role check is
bypassed, the existing audit and result-idempotency (`admin_results`) are **not**.

### Event stream

Redis Stream `realm:events`, `MAXLEN ~ 10000`. Fields: `type`, `ts` (RFC 3339), `data`
(JSON). Consumers use a consumer group (`bot`).

| `type` | `data` |
|---|---|
| `realm.ready` | `{version, content_hash}` — on readiness transition false→true |
| `realm.unready` | `{}` — true→false |
| `realm.draining` | `{reason, players}` |
| `realm.resumed` | `{}` |
| `player.joined` / `player.left` | `{account_id, discord_name[, seconds]}` |
| `account.kicked` / `account.banned` / `account.unbanned` / `account.muted` / `account.unmuted` | `{account_id, discord_name, reason, until?, by}` |
| `notice` | `{text, level, by}` |
| `deploy.pending` | `{since, commits_behind, head}` |
| `world.spawn.result` / `world.kill.result` | `{request_id, status, detail, by, announce?}` |
| `world.event.started` / `world.event.stopped` | `{preset, title, until?, announce?, by}` |

`by` is the token **name**. Emission is fire-and-forget from a dedicated task with a
bounded queue (256); overflow drops with a counter, never blocks a tick.

## Behaviour notes

- Drain is memory-only; a restart clears it, which is what CD wants.
- `status` does no DB query (atomics + one cached Redis `GET`).
- Every mutation logs `admin by=<name> route=<route> result=<code>`.

## Failure modes

| Situation | Behaviour |
|---|---|
| Postgres down | Tokens not in the 10 s cache → `401`. CD treats non-200 `status` as "do not deploy". |
| Redis down | `status` `200` with `redis:false`, `deploy_pending:null`; events dropped with a counter; mutations still succeed. |
| `N3E_ADMIN_LISTEN` public | Refuse to start. |
| World op while draining | Allowed (a mod may want to clear a boss before restart). |

## Security

- Plaintext tokens exist only in the caller's env and `mint` output.
- Ops token: `/etc/n3e-realm/ops.token`, root-only, read by CD via ssh (spec 06). Never
  in `.env` or GitHub Secrets.
- Permission constants per route, never derived from the body.
- The listener is a separate task; a slow admin client cannot stall the tick.

## Acceptance tests

1. `mint --name t --perm realm.status`; `GET /status` → 200; `POST /drain` → 403 naming
   `realm.drain`.
2. Unknown / missing token → 401. Revoked → 401 within 10 s.
3. `mint` twice → exit 2; `revoke` then `mint` → ok. `list` shows no hash/token.
4. Drain → `status.draining`, `realm.draining{reason}`; resume → `realm.resumed`.
5. `deploy-pending` PUT/GET/DELETE round-trip; same-head PUT emits nothing.
6. Kick/ban/unban/mute/unmute with a live client (shared with spec 02 tests 5–6);
   `admin_audit` row has `token_name`, null `character_id`. Muted client's chat is not
   relayed; the client receives one notice line explaining it.
6b. `realm/notice` with `in_game: true` → every connected test client receives a
   `Chat{notice:true}` with the text; `motd` PUT → a freshly selected character
   receives `Notice{lines}` including the active preset's announce line.
7. `spawn` by name → `202`, `world.spawn.result{status:"spawn_authorized", announce}`,
   NPC visible to a test client. Unknown name → `404`. Invalid index → `invalid_spawn`.
7b. `catalog` lists the package's named spawns and presets; `event` activates one,
   `catalog.active_event` reflects it, a second `event` → 409, `stop` reverts.
8. `N3E_ADMIN_LISTEN=0.0.0.0:7780` → refuses to start.
9. Stop Postgres → 401 after cache expiry. Stop Redis → 200 with `redis:false`.
10. Tick time under 1,000 `status` calls/s is unchanged (admin listener is off-tick).

## Open questions

Q21.
