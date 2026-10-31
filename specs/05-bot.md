# 05 — Discord bot

Implements flow ④–⑦ and Pushback #1, #2 from `architecture.md`. Plain automation. No AI.

## Purpose

Let Discord mods operate the realm through slash commands, and relay realm events into
Discord channels.

## Scope

In: slash commands; role gating; calling the admin API; consuming `realm:events`;
triggering CD via `workflow_dispatch`; the daily `deploy:pending` reminder. Out:
moderation of Discord itself; anything that touches Postgres; any direct game-wire
connection; AI of any kind.

## Interfaces

### Configuration

| Env var | Meaning |
|---|---|
| `DISCORD_BOT_TOKEN` | Bot token. |
| `DISCORD_GUILD_ID` | The one guild the bot serves. Commands are registered as guild commands (instant propagation). |
| `DISCORD_CHANNEL_ANNOUNCE` | Channel id for player-facing announcements. |
| `DISCORD_CHANNEL_OPS` | Channel id for operator events and the deploy nag. |
| `DISCORD_ROLE_MOD` | Role id allowed `/kick /ban /mute /notice /motd /boss /kill /event`. |
| `DISCORD_ROLE_OPS` | Role id allowed `/deploy` (and everything `MOD` can). |
| `REALM_ADMIN_URL` | `http://server:7780` (compose network). |
| `REALM_ADMIN_TOKEN` | The `bot` token (spec 03). |
| `REALM_REDIS` | For the `realm:events` consumer group: `host:port` or a `redis://` URL. |
| `GITHUB_REPO` | `org/N3E-Realm`. Required when `GITHUB_DISPATCH_TOKEN` is set. |
| `GITHUB_DISPATCH_TOKEN` | Fine-grained PAT, `actions: write` on `GITHUB_REPO` only. Optional: without it `/deploy` replies that deploy is not configured. |
| `GITHUB_WORKFLOW` | `cd.yml` (the default). |
| `REALM_NAG_HOUR_UTC` | Hour of the daily reminder, `0`-`23`; default `18`. |
| `GITHUB_API` | Test-only: GitHub's API base (default `https://api.github.com`); plain `http://` only to a loopback address (Q39). |
| `DISCORD_API_PROXY`, `DISCORD_GATEWAY_PROXY` | Test-only stand-ins for Discord's REST API (`host:port`, plain http) and gateway (`ws://host:port`); refused unless they resolve to loopback (Q39). |

Every value is checked at start; a missing or malformed one exits `2` naming it.

### Slash commands

All responses are **ephemeral** to the invoker except where noted. Every command first
checks the invoker's roles against the table; a miss → "You don't have permission"
(ephemeral). **The role check is a convenience, not the security boundary** — the
admin API's token permissions are. The Bot's token must not hold permissions the Bot
does not expose.

| Command | Role | Action | Public? |
|---|---|---|---|
| `/status` | anyone | `GET /v1/realm/status` → players online, version, draining, deploy pending (since, commits behind), uptime. | No |
| `/whois <discord user>` | MOD | `GET /v1/accounts/by-discord/{id}` → account summary, online, ban state. | No |
| `/kick <user> <reason>` | MOD | `POST /v1/accounts/{id}/kick`. | Ops channel gets the event. |
| `/ban <user> <reason> [duration]` | MOD | `POST /v1/accounts/{id}/ban` with `until = now + duration` (`1h`, `3d`, `perm`). | Ops channel |
| `/unban <user>` | MOD | `POST /v1/accounts/{id}/unban`. | Ops channel |
| `/mute <user> <reason> [duration]` / `/unmute <user>` | MOD | `POST /v1/accounts/{id}/mute` / `unmute`. | Ops channel |
| `/motd <lines…>` | MOD | `PUT /v1/realm/motd`. A slash option is one line, so the lines are one string separated by `\|` (1-20 lines of ≤ 127 bytes, checked before the call; Q40). | No (spec 03 emits no event for it) |
| `/notice <text>` | MOD | `POST /v1/realm/notice {text, level: info, in_game: true}`. Players see it in game as a yellow NOTICE line; Discord sees it via the stream so that CD and mods produce identical announcements. | Announce channel (via stream) + in game |
| `/boss <name> [reason]` | MOD | `name` is an autocomplete choice from `GET /v1/world/catalog`; `POST /v1/world/spawn {name, reason}`. Reply with the request id; final result arrives via stream. | Announce channel on success, with the catalog's `announce` text |
| `/kill <entity id> <reason>` | MOD | `POST /v1/world/kill`. | Ops channel |
| `/event <preset> [reason]` | MOD | `preset` autocompletes from the catalog; `POST /v1/world/event {preset, reason}`. 409 → "an event is already running: …". | Announce (via stream) |
| `/event-stop [reason]` | MOD | `POST /v1/world/event/stop`. | Announce (via stream) |
| `/deploy [reason] [force]` | OPS | If `status.deploy_pending` is null and the user didn't pass `force: True`: reply "nothing pending". Otherwise `POST /repos/{repo}/actions/workflows/{wf}/dispatches {ref: "master", inputs: {force: "true", reason}}`. Reply with the Actions run URL once it appears (poll `GET …/runs?event=workflow_dispatch` for ≤ 30 s). | Ops channel |

**Catalog.** The Bot fetches `GET /v1/world/catalog` on startup and whenever it sees
`realm.ready` on the stream (a new package may have new names), and serves slash-command
autocomplete from it. No Bot-side mapping files: names, indexes, presets and announce
texts are content (spec 10).

### Event stream consumer

Consumer group `bot` (created at `$`, so a new group does not replay history), consumer
name = hostname. `XREADGROUP … BLOCK 5000 COUNT 32`. Acknowledge after the Discord message
is sent (or after deciding not to send). On startup, first take over every entry the
group left pending (`XAUTOCLAIM … 0`: one bot per realm, and a recreated container has a
new hostname, Q37), drain pending entries (`0`), then tail (`>`). A message Discord does
not take leaves its entry unacknowledged and stops the batch, so order holds; pending is
read again after 5 s, and the messages still owed for an entry are kept so a retry
neither re-renders it nor resends what went out. Dedupe: none — at-least-once delivery
is acceptable; a rare duplicate announcement is fine.

Every relayed text that is not the bot's own (reasons, names, notice text, announce
texts) has its Discord markdown escaped, and every message the bot sends — channel
posts and replies — goes out with no allowed mentions, so nothing it relays can ping.
`account.*` messages name the moderator when the bot made the call (remembered in
memory for 2 minutes), else the token name in `by` (Q38).

| Event | Channel | Message |
|---|---|---|
| `realm.ready` | announce | "Realm is up — version `v`" (only if the previous state was not ready, to avoid chatter on restart loops; `realm.draining` and `realm.unready` make the next one news) |
| `realm.unready` | ops | "Realm is not ready" |
| `realm.draining` | announce | "Restart soon: `reason`. `players` online." |
| `realm.resumed` | ops | "Drain cancelled" |
| `notice` | announce (`warn` → also ops) | `text`, prefixed by level: "**Notice:** …" / "**Warning:** …" |
| `deploy.pending` | ops | "Deploy pending since `since` (`commits_behind` commits). Run `/deploy` when the realm is quiet." |
| `account.*` | ops | "`by` kicked/banned `discord_name`: `reason`" |
| `world.spawn.result` | announce on `spawn_authorized` with the event's `announce` text; ops on failure | |
| `world.event.started` / `stopped` | announce: `announce` text or "`title` has started/ended" | |
| `player.joined/left` | **nowhere** by default. Optional ops-channel counter edit later. Consume and ack. |

### Daily reminder

Once per day at 18:00 UTC (configurable `REALM_NAG_HOUR_UTC`), if
`status.deploy_pending` is non-null, post the `deploy.pending` message to ops. Also
mention it in every `/status`.

## Behaviour

- **Fail fast.** Any admin API call that fails to connect, times out (5 s), or returns
  5xx gets the reply: "Realm admin API unavailable — the server is probably
  restarting. Try again in a minute." If the last stream event was `realm.draining`
  or `realm.unready`, say so explicitly. No retries, no queueing (architecture.md,
  Flows › Bot).
- **Idempotent commands.** `/ban` on a banned user updates `until`/`reason`.
- **Resolve users** via the Discord user option (snowflake), never by name string.
- **Startup.** Verify the admin token with `GET /v1/realm/status` (log a warning on 401
  but keep running), join the consumer group (create with `MKSTREAM` if absent), start
  the catalog and nag timers, connect the gateway with no intents (interactions arrive
  without any), and register the guild commands (one bulk overwrite: an upsert of the
  whole set) on the first READY, which carries the application id.
- **Shutdown.** SIGTERM → stop reading the stream, finish in-flight acks, exit within 5 s.

## Failure modes

| Situation | Behaviour |
|---|---|
| Discord gateway disconnect | Library reconnect with backoff; stream reading continues; messages that fail to send are **not** acked and are retried on the next read of pending. |
| Redis down | Commands still work (they don't need Redis); stream consumption resumes when Redis returns. Log once per minute. |
| Admin API 401 | Reply "bot token rejected — ops needs to re-mint"; post once to ops channel (again only after a call has worked since). |
| Admin API 501 | The route's milestone has not landed on this realm: reply "This realm does not support that yet". |
| Discord rejects the bot token | The gateway ends the session for good; log it and exit `1` (compose restarts it). |
| `workflow_dispatch` 4xx | Reply with the GitHub error body (it's usually "workflow not found" or token scope). |
| Catalog unavailable at startup | Register commands without choices; refetch every 30 s; autocomplete says "realm catalog unavailable". |

## Security

- The Bot never sees a session token, a Discord OAuth secret, or the ops admin token.
- `GITHUB_DISPATCH_TOKEN` can only dispatch workflows; it cannot read code or secrets.
  Fine-grained, single-repo, 90-day expiry — put the renewal date in the ops runbook.
- Role ids, not role names.
- Command handlers must not interpolate user text into anything but the admin API JSON
  body and Discord messages (escape Discord markdown in `reason` echoes).

## Acceptance tests

Against a stack with the admin API and Redis, Discord mocked at the library boundary
where practical, plus one manual run against a test guild:

1. `/status` renders players, version, draining, pending.
2. Non-MOD runs `/kick` → permission reply; no API call.
3. MOD runs `/kick` → API called; ops channel receives the `account.kicked` message from
   the stream (not from the command handler).
4. `/notice hello` → announce channel gets "hello" exactly once, via the stream.
5. `/boss ironfang` → `POST /world/spawn {name: "ironfang"}`; result event → announce
   text. Autocomplete offers only catalog names. After `realm.ready` with a new content
   hash, the catalog is refetched.
5b. `/event weekend-exp` → started message; second `/event` → "already running"; `/event-stop`
   → ended message.
6. Admin API stopped → every mutating command replies with the fail-fast text within 6 s.
7. Bot killed while 3 events are unacked → on restart, the 3 are delivered once each.
8. `deploy.pending` set → ops message; nag timer fires (set `REALM_NAG_HOUR_UTC` to now).
9. `/deploy` by OPS → `workflow_dispatch` called with `force: "true"`; by MOD → denied.
10. Grep logs for the bot token, admin token, PAT: zero hits.

Evidence (M6): `tests/bot_live.py` runs tests 1-4 and 6-10 against the real admin API
and event stream, with stand-ins for Discord's gateway and REST API and for GitHub
(Q39): the role table, every account command, the relay with escaped text and no
allowed mentions, the moderator named in the ops channel, the reminder, `/deploy`,
three unacknowledged entries delivered once each after a SIGKILL and a host-name change,
a revoked token, and all 11 mutating commands failing fast with the drain reason
(5.0 s with the API hung, 0.01 s with it gone). Tests 5 and 5b are partial: the world
routes answer 501 until M5/M5b, so the suite checks only that the commands reach them
and that autocomplete says the catalog is unavailable. Against the maintainer's real
test guild: the gateway session, the 14 guild commands registered, and stream entries
posted to the announcements channel and acknowledged.

## Open questions

None.
