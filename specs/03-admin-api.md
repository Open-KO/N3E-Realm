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
| `N3E_ADMIN_LISTEN` | `127.0.0.1:7780` | Must resolve to a loopback or RFC 1918 address; refuse to start otherwise (`0.0.0.0` included; in compose, the server's static network address, spec 07, Q29). |
| `REDIS_ADDRESS` | *(existing)* | Also used for `realm:events` and `realm:deploy:pending`. |

### Permissions

Flat strings. Each route requires exactly one. Globs are accepted **only** by the CLI
(`mint`, `grant`, `revoke-perm`) and expanded there; a stored token holds concrete
permissions.

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
| `character.kit` | `POST /v1/characters/kit` — the tester kit (RQ-212) |
| `token.mint`, `token.revoke` | Reserved; no routes in this version. Minting is CLI-only. |

There is deliberately no `realm.restart`: restarting is a compose action CD performs
over ssh.

Today's tokens: `bot` = `world.catalog`, `world.spawn`, `world.kill`, `world.event`,
`account.*`, `realm.status`, `realm.notice`, `character.kit` (not `world.set`); `ops` =
`realm.*`, `character.kit`. A token minted before `character.kit` existed lacks it:
`admin grant --name bot --perm character.kit` adds it to the same token, so `.env` keeps
its `REALM_ADMIN_TOKEN` (`/kit` answers that the bot's token is not allowed until then).

### In-game notice (engine side)

A new internal broadcast: `Chat{ text, notice: 1|2 }` to every in-world session, drawn
by the client as a yellow notice line (1) or a bold centre banner (2) (new `Chat.notice`
uint32; additive wire field, 0 = ordinary chat; 3 is the answer to a game master's own
command, below, sent to that session alone). Used by `realm/notice` and by the server itself for preset start/stop and
drain. World-entry notice: a new `Notice { repeated string lines }` message sent after
`SelectCharacter` succeeds, drawn in a dismissible panel top-right (KO placement).

### In-game GM commands (engine side, RQ-213)

Commands a game master types in game chat. They are not admin-API calls and need no
admin token: the server authorises each one against the typing character's
**capabilities** in `character_roles` (Postgres; granted and revoked with
`n3e-server role grant|revoke ACCOUNT CHARACTER_ID REALM CAPABILITY`). The client
never decides who is a game master, and a tools build grants nothing. KO's own command
set, read in `KO-FINDINGS.md` §11, has no item, level or gold command; those three are
the realm's own, in KO's `+` form (Q128). The status of each row is its queue item;
nothing here is implemented until that item lands.

**Capabilities.** Individually granted, none implying another (D-154: KO's authority
0 is roughly all of them, its limited manager 250 roughly `gm.move` and
`gm.moderate`). New: `gm.item`, `gm.character`, `gm.move`, `gm.moderate`,
`gm.notice` (added to `administration::CAPS`). Reused: `server.inspect`,
`entity.spawn`, `entity.kill`.

**Which lines are commands.** As KO's chat handler (`004989a8`): a chat line whose
first byte is `+`, from a character that holds any capability in the table below, is
a command and is never relayed; from anyone else it is ordinary chat. KO's client
commands (the `/` names in the table, matched without regard to case as 1097 does)
are sent by the client as the chat line typed; the server takes such a line as a
command from a holder and drops it from anyone else (KO's server ignores the packet).
Whether the sender holds a capability is the server's read of `character_roles`,
fail-closed as the movement lease is (`turbo.rs`: a lapsed or unread lease holds
none). Each command is then authorised again for its own capability, off the tick,
against the authenticated, session-fenced character under the role lock, as
`administration::execute` does; a revoked capability refuses the next command.
Arguments are split on whitespace; `NAME` is a character of this realm, exact or
else without regard to case and unambiguous (≤ 24 characters), as a whisper's
recipient. Commands share the chat rate bound (one line per 20 ticks).

Settled in RQ-228: the command line is an ordinary chat line; a whisper whose text
begins with `+` is a whisper. A **muted** holder's lines are dropped before they are
read, commands included (with the once-a-session mute line of spec 02), as KO drops a
muted sender's lines first (`004989a8`, `KO-FINDINGS.md` §11); an unmute restores its
commands. A holder whose lease is **unread** (from select until the first authority
read, normally under 500 ms, or after a stalled read lapses it) holds none, so its `+`
line is relayed as chat; a holder whose capability was just revoked may have one more
`+` line taken as a command within the lease, and that command is refused by its own
check. At most 16 commands await the database at once; a further one is answered "The
realm is busy; try again." and not run.

**Replies.** KO answers its game master nothing (§11); the realm answers the issuer
alone with one line in its own chat: `Chat{notice: 3}`, drawn as a yellow line like
notice 1 but never framed or broadcast (KO's `MsgOutput` yellow, the colour of its own
command answers; an older client draws it as a notice line). A success names what
changed ("Gave Aria 5 x Healing potion.", "Aria is now level 9."; ASCII, for the chat
font); a refusal says why in one line: `Usage: +give_item NAME ITEM [COUNT]`,
`No character named Aria.`, `No item ITEM.`, `COUNT for Healing potion is 1 to 20.`,
`Aria has no bag yet.` (a character with neither a bag nor the progression row a first
bag is made from; a character that has not yet entered the world but has that row gets
its bag made, as the tester kit does), `Aria's bag is
full.`, `You may not use +give_item.`, `Unknown command +verb.` (a verb or name repeated
in a reply is cut to 32 characters). The target is told nothing beyond what it sees (its
bag, its level, its position), as KO.

**Audit.** A command that passes its capability check writes, in the transaction that
applies it, an `admin_audit` row: the issuer's `account_id` and `character_id`, a
server-made `request` (`gm-…`), the current world revision, `target`
(`character:<id>`, `account:<id>` or `entity:<id>`), `reason` the line as typed (cut
to 160 characters), the before and after state where there is one (the bag, the
progress) and outcome `gm_<verb>`; one log line `gm by=<character> verb=<verb>
target=<…> result=<…>`; and a `gm.command` event. A refused capability check writes no
audit row (as a denied `kill`), only the log line. Moderation commands also emit the
`account.*` event the admin route emits, `by` the character's name. The `gm.command`
event follows every command that passed its capability check, whether or not it
changed anything: `target` the named character's name (empty when none was resolved),
`result` one word (`given`; else why nothing changed: `usage`, `no_character`,
`no_item`, `bad_count`, `no_bag`, `bag_full`), `detail` the issuer's reply line. An
unknown verb or a refused capability emits none.

| Command | KO origin (§11) | Capability | Effect | Item |
|---|---|---|---|---|
| `+give_item NAME ITEM [COUNT]` | none (the realm's) | `gm.item` | A new record of the package item `ITEM` (its id, `game:` prefix optional; not the package's reward token, whose count is the progression's) in the named character's bag, at the item's full durability: `COUNT` 1 to the item's stack limit (1 for one that does not stack), default 1; a full bag refuses with nothing changed | gm-chat-give-item (RQ-228, landed) |
| `+level NAME LEVEL` | none (the realm's) | `gm.character` | Curve XP to `LEVEL`'s threshold, lifetime XP up by the same amount, as the tester kit does; `LEVEL` above the character's own, at most the curve's cap (a lower one refuses) | gm-chat-level-gold |
| `+gold NAME AMOUNT` | none (the realm's) | `gm.character` | `AMOUNT` coins (≥ 1) into the named character's bag, the balance within the bag's coin limit (refused otherwise) | gm-chat-level-gold |
| `/goto X Z` | 1097 `0x1e` | `gm.move` | The issuer moves to (X, Z) in its zone when standable there | gm-chat-move |
| `/ARREST NAME` | 1097 `0x40`/1 | `gm.move` | The issuer moves to the named character in the world | gm-chat-move |
| `/SUMMONUSER NAME` | later source `0x40`/7 | `gm.move` | The named character in the world moves to the issuer | gm-chat-move |
| `+monpursue ID` | server `0042c1ba` | `gm.move` | The issuer moves to the NPC entity `ID` | gm-chat-move |
| `/FORBIDCHAT NAME` | 1097 `0x40`/3 | `gm.moderate` | The account's mute (as `account.mute`), permanent; reason "in game by <issuer>" | gm-chat-moderation |
| `/PERMITCHAT NAME` | 1097 `0x40`/4 | `gm.moderate` | Unmute (as `account.unmute`) | gm-chat-moderation |
| `/CUTOFF NAME` | later source `0x40`/5 | `gm.moderate` | Kick (as `account.kick`) | gm-chat-moderation |
| `/FORBIDCONNECT NAME` | 1097 `0x40`/2 | `gm.moderate` | Permanent ban and kick (as `account.ban`) | gm-chat-moderation |
| `/NOTICE TEXT` | 1097 chat type 7 | `gm.notice` | The realm notice, `level` `info` (the yellow line to every session in the world, and the `notice` event) | gm-chat-world |
| `/COUNT` | 1097 `0x36` | `server.inspect` | Answers "\*\*\* Current concurrent user : N \*\*\*" (text 2101), N the characters in the world | gm-chat-world |
| `/VISIBLE`, `/INVISIBLE` | 1097 state change | `server.inspect` | The issuer's show switch, the operations `show` and `hide` (PQ-192, KO's later `VIEW`/`UNVIEW`) | gm-chat-world |
| `+monsummon INDEX` | server `0042c1ba` | `entity.spawn` | The `spawn` operation for the package's spawn `INDEX`; reason the line | gm-chat-world |
| `+monkill ID` | server `0042c1ba` | `entity.kill` | The `kill` operation on NPC entity `ID`; reason the line | gm-chat-world |

A character named by `+give_item`, `+level` or `+gold` that is in the world gets the
change through its own session, as a claim's bag result or a settlement's progress
reaches it (the live path RQ-226 also needs; for a bag, RQ-228: the committed bag
becomes the session's when its revision is not older, and the client is sent it as
an unrequested `BagResult{request: "", status: "ok"}`, as a listing); one that is not gets it committed for
its next entry (one transaction with the audit, as the tester kit). Not offered, for
want of the feature (each is its own item when the realm gains it): KO's weather and
time (`CLEAN`, `RAINING`, `SNOWING`, `TIME`), `+zonechange` (one zone), the war, siege,
discount, santa, rental, king, challenge and battle verbs, `+money_add`/`+exp_add`
(the realm's rate events are presets, Discord `/event`), `+down` (CD restarts),
`FORBIDUSER` (Discord `/ban` with a duration), `ATTACKDISABLE`/`ATTACKENABLE`
(deferred with PvP), and `+pursue`/`+actpursue` (the tools terminal's `record` and
`trace`).

A Discord route to grant these capabilities (an ops-only `character.role` permission)
does not exist yet; until it does, granting is the CLI above on the realm host.

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
n3e-server admin mint        --name NAME --perm PERM [--perm PERM ...]   # prints the token once
n3e-server admin grant       --name NAME --perm PERM [--perm PERM ...]   # adds to an existing token
n3e-server admin revoke-perm --name NAME --perm PERM [--perm PERM ...]   # removes from an existing token
n3e-server admin revoke      --name NAME                                  # exit 0 even if absent
n3e-server admin list                                                     # name, perms, created, last_used; never hashes
```

Talks to Postgres directly; needs no token. `mint` on an existing name → exit 2
("exists; revoke first"). Token: 32 CSPRNG bytes → base64url, no padding. Stored:
`sha256(raw bytes)`.

`grant` and `revoke-perm` change an existing token's permissions in place (RQ-227): its
hash, `created_at` and `last_used_at` stay and nothing is printed on stdout, so the
caller's copy of the token keeps working. Granting a held permission or removing one not
held is a no-op (exit 0); the resulting set goes to stderr. An absent name → exit 2 ("no
admin token; mint first"); a `revoke-perm` that would leave no permission → exit 2
("revoke the token instead"); an unknown permission → exit 1, nothing changed. Like
`revoke`, a change takes ≤ 10 s to reach a cached token.

### HTTP conventions

- `Authorization: Bearer <token>`. Missing/unknown → `401 {"error":"unauthenticated"}`.
  Lacking the permission → `403 {"error":"forbidden","detail":"needs realm.drain"}`.
- `last_used_at` updated at most once per minute per token.
- JSON both ways. Mutations return `200` with resulting state, or `202` when async
  (world operations run on the next tick).
- Unknown route `404`; method mismatch `405`; body limit 16 KiB; read timeout 5 s.
- Token cache: verified tokens are cached in memory for 10 s so `status` polling is not
  a DB query per call; `revoke` therefore takes ≤ 10 s to bite (acceptable; documented).
  An uncached token is looked up one at a time, bounded at 2 s; past that it is `401`, so
  a database that stops answering holds one blocking thread, not one per request.
- A route in this contract whose milestone has not landed (world routes and `motd`: M5)
  answers `501 {"error":"not_implemented"}` after the permission check, so the Bot can
  be written against the full table. The account routes landed in M3.

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
  "redis": true,
  "events_dropped": 0
}
```
`players` = sockets past login (including character select). `events_dropped` = events
not written to `realm:events` (queue full or Redis down) since start. `ready` = the same
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
event-start style). The engine carries this as `Chat.notice` = 1 (line) or 2 (banner).
The client draws the text as sent: a notice line in yellow on the HUD's message line
(or above the chat panel without a package HUD), and for 2 also a centre banner for 6 s;
KO's `####` framing would be package data and is not drawn yet. `text` ≤ 500 chars (in-game
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
ban_reason, muted_at, muted_until, mute_reason, sessions, online, characters: [{id,
name, slot, nation, race, specialty}]}` or `404`. Times are RFC 3339 UTC or `null`; `sessions` counts unexpired
sessions; `online` is whether the account has a logged-in socket on this realm;
`characters` are this realm's, in slot order, each with what its create chose
(RQ-002, `content/character-create.md`: `nation`, `race` and `specialty` are `null`
for a character created without the package's create rules, `slot` for a row
inserted without one). A legacy (password) account has `discord_id` `null`.

**`POST /v1/accounts/{id}/kick`** `{"reason"}` → `200 {connections_closed}`. Deletes every session (spec 02 `revoke_account(kick)`). Emits `account.kicked`.
**`POST /v1/accounts/{id}/ban`** `{"reason", "until": "<rfc3339>|null"}` → `200 {banned_until, connections_closed}`. Deletes every session and kicks. Emits `account.banned`.
**`POST /v1/accounts/{id}/unban`** → `200 {banned: false}`. Emits `account.unbanned`.
**`POST /v1/accounts/{id}/mute`** `{"reason", "until": "<rfc3339>|null"}` → `200 {muted_until}`.
**`POST /v1/accounts/{id}/unmute`** → `200 {muted: false}`. Emit `account.muted` / `account.unmuted`.
`reason` is required for kick, ban and mute (≤ 200 characters, no control characters);
`until` is RFC 3339 in the future, or `null`/absent for permanent; otherwise `400`. An
unknown account is `404`; a database that does not answer within 2 s, `503`.
Mute drops the player's chat server-side (KO authority 11 semantics) but, unlike KO,
tells the player once per session on their first dropped message (spec 02).

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

**`POST /v1/characters/kit`** `{"character": "Name", "reason": "PvP test"}` → `200`
```json
{
  "character_id": 42, "character": "Name", "account_id": 7, "level": 10,
  "equipped": [ { "slot": "Right hand", "item": "demo:item/blade", "label": "Practice blade" } ],
  "unequipped": 0, "request_id": "kit-…"
}
```
The tester kit (RQ-212), for testers: it maxes one character of this realm, named
exactly or else without regard to case (≤ 24 characters), in one transaction:

- **Level:** curve XP to the package's last progression threshold (its level cap),
  lifetime XP up by the same amount, the progress revision up by one, as a settlement
  would. Class skills open by level, so the cap opens every skill the character's
  class policy holds (RQ-211). `level` is `null` for a character without
  progression rows (a realm without a curve).
- **Gear:** the package's best arrangement for damage, chosen once at start-up from
  the items its equipment policy holds and the package may wear (title, race and
  attribute requirements, as equip checks them): the highest attack the package's
  stats give at the cap, then defense, health and resource. Each slot gets a new
  record at full durability, or keeps a record of the same item it already wears
  (repaired), so a second kit changes nothing; gear it takes off goes to free bag
  slots. `equipped` is empty when the package has no equipment or no stats.
- **Stat and skill points:** none; the engine has no allocated points yet (Q127).

Refusals change nothing: an unknown name → `404`; a character in the world
(`characters.online` in this realm generation) → `409 {"error":"character_online"}`,
since a session's bag and progress are its own until it leaves (the kit applies to
the character's next entry when called after it leaves); gear to take off with too
few free bag slots → `409 {"error":"bag_full"}`; `reason` (≤ 160 characters, the
audit's bound) and `character` are required (`400`). A database that does not answer
within 5 s → `503`; as with the account routes' bound, the transaction may still commit
after that answer (then `character.kitted` is not emitted, but the audit row stands). Audited in `admin_audit` (`token_name`, `target`
`character:<id>`, the bag before and after, outcome `kit_applied`) and emitted as
`character.kitted`.

### Audit identity

`administration::execute` today authorises against an authenticated **character**'s
roles and writes `admin_audit(account_id, character_id, …)`. Admin-token calls have no
character and no account. Add a nullable `token_name text` column to `admin_audit` and
make `account_id` and `character_id` null **exactly for rows with `token_name` set**
(CHECK; migration 024), with `(realm, token_name, request)` unique among them. Authorisation
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
| `player.joined` / `player.left` | `{account_id, discord_name[, seconds]}` — at login and when that socket ends; `discord_name` is `null` for a legacy account |
| `account.kicked` / `account.banned` / `account.unbanned` / `account.muted` / `account.unmuted` | `{account_id, discord_name, reason, until?, by}` |
| `notice` | `{text, level, by}` |
| `deploy.pending` | `{since, commits_behind, head}` |
| `world.spawn.result` / `world.kill.result` | `{request_id, status, detail, by, announce?}` |
| `world.event.started` / `world.event.stopped` | `{preset, title, until?, announce?, by}` |
| `character.kitted` | `{character_id, character, account_id, level, equipped, reason, by}` |
| `gm.command` | `{character_id, character, account_id, verb, target, result, detail}` — an in-game GM command that passed its capability check (RQ-213; `character` is the issuer) |

`by` is the token **name**. Emission is fire-and-forget from a dedicated task with a
bounded queue (256); overflow drops with a counter, never blocks a tick.

## Behaviour notes

- Drain is memory-only; a restart clears it, which is what CD wants.
- `status` does no DB query (atomics + one cached Redis `GET`).
- Every mutation logs `admin by=<name> route=<route> result=<code>`.

## Failure modes

| Situation | Behaviour |
|---|---|
| Postgres down | Tokens not in the 10 s cache → `401` within the 2 s lookup bound. CD treats non-200 `status` as "do not deploy". The realm itself fences once its 3 s lease lapses (D-142) and exits, so a cached token never outlives a real outage by much. |
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
3b. `grant` a permission to a minted token → the same token is allowed that route within
   10 s; `revoke-perm` it → `403` again within 10 s. `revoke-perm` of the last permission,
   `grant`/`revoke-perm` on an absent name → exit 2; an unknown permission → exit 1.
4. Drain → `status.draining`, `realm.draining{reason}`; resume → `realm.resumed`.
5. `deploy-pending` PUT/GET/DELETE round-trip; same-head PUT emits nothing.
6. Kick/ban/unban/mute/unmute with a live client (shared with spec 02 tests 5–6);
   `admin_audit` row has `token_name`, null `character_id`. Muted client's chat is not
   relayed; the client receives one notice line explaining it.
6b. `realm/notice` with `in_game: true` → every connected test client receives a
   `Chat{notice: 1|2}` with the text; `motd` PUT → a freshly selected character
   receives `Notice{lines}` including the active preset's announce line.
7. `spawn` by name → `202`, `world.spawn.result{status:"spawn_authorized", announce}`,
   NPC visible to a test client. Unknown name → `404`. Invalid index → `invalid_spawn`.
7b. `catalog` lists the package's named spawns and presets; `event` activates one,
   `catalog.active_event` reflects it, a second `event` → 409, `stop` reverts.
8. `N3E_ADMIN_LISTEN=0.0.0.0:7780` → refuses to start.
9. Stop Postgres → an uncached token gets 401 within the lookup bound; the realm fences
   and exits without a panic. Stop Redis → 200 with `redis:false`.
10. Tick time under 1,000 `status` calls/s is unchanged (admin listener is off-tick).
11. `characters/kit` (RQ-212): `403` without `character.kit`; `404` for an unknown
   name; `409 character_online` for a character in the world; after it leaves, `200`
   at the curve's cap and `character.kitted` on the stream (`tests/admin_api_live.py`).
   Against PostgreSQL and the stats fixture (`tests/tester_kit_db.py`): the fixture's
   best arrangement, a second kit keeps it, a full bag refuses and rolls back.
12. In-game GM commands (RQ-213; each command's test lands with its item): a `+` line
   from a character without any GM capability reaches nearby players as chat; from a
   holder it is never relayed. A command without its own capability answers "You may
   not use …" and writes no audit row; with it, the effect, one `admin_audit` row
   (outcome `gm_<verb>`), the `gm.command` event and the issuer's `Chat{notice: 3}`
   line. A revoked capability refuses the next command. `+give_item` to a character in
   the world shows in its bag without leaving; to one not in the world, at its next
   entry; a full bag refuses with nothing changed; a muted holder's command is dropped
   unread. `+give_item`: `tests/gm_commands_live.py` (RQ-228).

## Open questions

Q21, Q127, Q128.
