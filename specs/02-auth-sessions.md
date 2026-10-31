# 02 — Discord login, sessions, accounts, bans

Implements O9 (Sessions) and flow ①②③ from `architecture.md`. Lives in the game server
and the game client (after migration, spec 09).

## Purpose

Replace account/password login with Discord identity, issue a long-lived revocable
session token, and give operators a kick/ban that actually ends a live connection.

## Scope

In: OAuth2 code exchange (server), account record keyed by Discord user id, session
mint / verify / revoke, concurrency cap, bans, the client-side OAuth flow and token
storage. Out: Discord role sync into the game; guild-membership enforcement (Q4);
character management (`Characters` / `CreateCharacter` / `SelectCharacter` are
unchanged after login); attack-disable (deferred, Q14). Mute is in scope (spec 03 routes; `muted_until` below).

## Interfaces

### Configuration (server)

| Env var | Meaning |
|---|---|
| `DISCORD_CLIENT_ID` | OAuth2 application id. |
| `DISCORD_CLIENT_SECRET` | OAuth2 secret. Never leaves the server. |
| `N3E_SESSION_TTL_DAYS` | Default `30`. |
| `N3E_SESSION_MAX_PER_ACCOUNT` | Default `5`. |
| `N3E_LEGACY_LOGIN` | Default unset. When `1`, the old `Login{account,password}` is accepted (test fixtures only; refuse to start with it set when `N3E_REALM=prod`). |

### Postgres (new migration)

```sql
ALTER TABLE accounts
  ADD COLUMN discord_id    text UNIQUE,
  ADD COLUMN discord_name  text,
  ADD COLUMN last_login_at timestamptz,
  ADD COLUMN banned_at     timestamptz,
  ADD COLUMN banned_until  timestamptz,          -- NULL with banned_at set = permanent
  ADD COLUMN ban_reason    text CHECK (length(ban_reason) <= 200),
  ADD COLUMN muted_until   timestamptz,          -- NULL = not muted; set in the past = expired
  ADD COLUMN mute_reason   text CHECK (length(mute_reason) <= 200),
  ALTER COLUMN salt          DROP NOT NULL,
  ALTER COLUMN password_hash DROP NOT NULL;
-- An account has exactly one credential kind:
ALTER TABLE accounts ADD CONSTRAINT accounts_one_credential
  CHECK ((discord_id IS NOT NULL) <> (password_hash IS NOT NULL));
-- Discord accounts get a synthetic unique name so existing FKs/uniques keep working:
-- name = 'd' || discord_id, set at insert.

CREATE TABLE sessions (
  token_hash   bytea PRIMARY KEY CHECK (octet_length(token_hash) = 32),  -- sha256(raw 32 bytes)
  account_id   bigint NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at   timestamptz NOT NULL,
  last_seen_at timestamptz,
  client_label text CHECK (length(client_label) <= 64)
);
CREATE INDEX sessions_account ON sessions(account_id, created_at);
```

Existing password accounts keep working under `N3E_LEGACY_LOGIN=1` (dev/test). There is
no migration of players from passwords to Discord: the realm launches with Discord.

### Wire (additions to `wire.proto`)

```proto
message DiscordLogin { string code = 1; string code_verifier = 2; string redirect_uri = 3; string client_label = 4; }
message SessionLogin { bytes token = 1; string client_label = 2; }
message LoginResult  { bytes token = 1; uint64 expires_at_unix = 2; string discord_id = 3; string discord_name = 4; }
```

Add to `Envelope.body` at the next free field numbers. Both login messages are accepted
exactly where `Login` is today. On success the server sends `LoginResult` **then**
`Characters`, and the flow continues unchanged. Failures use the existing
`Error{UNAUTHENTICATED, detail, request}` with `detail` ∈ `expired`, `revoked`,
`banned:<until|perm>:<reason>`, `discord:<reason>`, `dependency`. Goldens for the three
new messages are added to `protocol/` and regenerated in both languages per n3e's
existing convention.

### Logical operations (server)

**`discord_login(code, code_verifier, redirect_uri, client_label)`**

1. `POST https://discord.com/api/oauth2/token` — `grant_type=authorization_code`,
   `code`, `redirect_uri`, `code_verifier`, client id + secret. Timeout 10 s. Runs on the
   blocking/IO pool, never on a tick (n3e rule).
2. `GET https://discord.com/api/users/@me` → `id`, `username`, `global_name`. Discard the
   access token immediately; never store it.
3. Upsert `accounts` by `discord_id` (`name = 'd' || id`); refresh `discord_name`,
   `last_login_at`.
4. Banned and (`banned_until` is NULL or future) → `banned:…`.
5. If the account has `N3E_SESSION_MAX_PER_ACCOUNT` live sessions, delete the oldest by
   `created_at`.
6. Mint 32 CSPRNG bytes; store `sha256`; `expires_at = now() + TTL`.
7. Reply `LoginResult` with the raw token bytes, then proceed as after `Login`.

**`session_login(token, client_label)`**

1. `sha256(token)` lookup. Missing → `revoked`. `expires_at <= now()` → `expired` and
   delete the row.
2. Account banned → `banned:…`; delete all its sessions.
3. `last_seen_at = now()`, update `client_label`. Proceed as after `Login`.

Expiry is checked **only here**. A live connection whose token ages out is not kicked.

**`revoke_account(account_id, kick)`** — delete all sessions; if `kick`, close every
live connection for the account (any character) within one tick, with
`Error{UNAUTHENTICATED, detail: "kicked:<reason>"}` sent first if output permits.

**`ban(account_id, until, reason)`** / **`unban(account_id)`** — set/clear the ban
columns; `ban` calls `revoke_account(kick=true)`. Exposed via spec 03.

The existing Redis login throttle (`10/account/min`, `30/IP/min`, `cache.rs`) applies
to both new messages: the "account" key is `sha256(discord_id)` for `DiscordLogin` and
`sha256(token_hash)` for `SessionLogin`.

### Client-side OAuth flow

In the game client's login screen, replacing the account/password fields with one
"Log in with Discord" button (the fields remain in harness builds for the test suite).
The Discord `client_id` comes from the realm config the Launcher passes (`--realm
realm.json`, spec 04) — never compiled in, because a fork runs its own Discord
application.

1. If `session.json` exists for this realm host and is not expired: send `SessionLogin`.
   On `expired`/`revoked`: delete the file, fall through. On `banned`: show the reason
   and until-time; stop.
2. Generate PKCE `code_verifier` (43–128 chars) and `S256` challenge; random `state`.
3. Bind `127.0.0.1` on the first free port of a fixed list (`49152–49155`; each
   `http://127.0.0.1:<port>/callback` is registered in the Discord application).
4. Open the system browser at `https://discord.com/oauth2/authorize?client_id=…&response_type=code&scope=identify&redirect_uri=…&state=…&code_challenge=…&code_challenge_method=S256&prompt=none`.
   Show "Waiting for Discord…" with a Cancel button; 5-minute timeout.
5. Serve one request; verify `state`; respond with a tiny "You can close this tab" page;
   close the listener.
6. Send `DiscordLogin`. On `LoginResult`, write `session.json`.

Token storage: `$XDG_CONFIG_HOME/n3e-realm/<realm.id>/session.json`, mode `0600`,
`{"token": "<base64url>", "expires_at": "<rfc3339>", "discord_name": "…"}`.

`client_label` = hostname, truncated to 64 bytes, control characters stripped.

## Behaviour notes

- A session token never appears in a log, Discord message, URL, or crash report. Logs
  use `account_id` / `discord_name`.
- When the handshake is refused with `VERSION`/`CONTENT` (flow ⑧) the client exits with
  code `3` ("update via launcher", Q10). Sessions are not involved.
- Player-facing wording follows KO's where it exists (`KO-FINDINGS.md` §5): disconnect →
  "Disconnected from server."; kick → "You were disconnected by an operator: <reason>.";
  ban → "Your account is blocked until <when|further notice>: <reason>."; version/content
  mismatch → "Your client is version X; the realm requires Y. Close this window and run
  the launcher to update."
- `prompt=none` means a player already logged into Discord in their browser sees no
  consent screen on re-login; Discord still shows it the first time.

## Failure modes

| Situation | Behaviour |
|---|---|
| Discord API down/slow | `discord:unavailable` after 10 s. Token holders are unaffected. |
| Postgres down | Login fails closed (`dependency`). Matches the server's existing admission rule. |
| Token file unreadable | Fall back to the Discord flow. |
| Player revokes the app in Discord settings | Nothing until expiry; then re-prompt. |
| Two first logins race | Upsert on `discord_id` is idempotent. |
| Browser fails to open | Show the URL for copy-paste. |

## Security

- `DISCORD_CLIENT_SECRET` server-side only. PKCE is used anyway.
- `identify` is the only scope. Do not add `email`/`guilds` without Q4.
- The token is 32 CSPRNG bytes; the stored hash is SHA-256 of the raw bytes, not of the
  base64 string.
- scrypt leaves the production login path entirely (its 160 MiB / two-permit cost was
  the CPU-exhaustion vector noted in `architecture.md`).

## Acceptance tests

1. **First login.** Against a Discord test application: token issued; one `accounts` row
   with `discord_id`, one `sessions` row; `Characters` follows `LoginResult`.
2. **Reconnect.** Restart the client: no browser; `Characters` arrives; `last_seen_at`
   advanced.
3. **Expiry.** Set `expires_at` in the past → `expired`; row gone; browser flow runs.
4. **Cap.** Six sessions → the oldest is gone; five work.
5. **Ban.** Live connection + `account.ban` (spec 03) → closed within 1 s with
   `kicked:`; old token → `banned:…`; fresh Discord login → `banned:…`; `unban` →
   succeeds.
6. **Kick.** As ban, but the next Discord login succeeds and the old token is `revoked`.
7. **Legacy refused.** `Login{account,password}` without `N3E_LEGACY_LOGIN` →
   `UNAUTHENTICATED`. With it set and `N3E_REALM=prod` → server refuses to start.
8. **Throttle.** 31 `SessionLogin`s from one IP in a minute → the 31st is `RATE_LIMITED`.
9. **No secrets in logs.** Grep for the token, the Discord access token: zero hits.
10. **Goldens.** New message goldens round-trip in C++ and Rust.

## Open questions

Q4.
