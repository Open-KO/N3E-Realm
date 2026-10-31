-- Discord login and sessions (specs/02-auth-sessions.md). An account holds exactly one
-- credential: a Discord id, or a legacy scrypt password (test fixtures only). A Discord
-- account's name is 'd' || discord_id, so existing name keys keep working.
ALTER TABLE accounts
 ADD COLUMN created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 ADD COLUMN discord_id text UNIQUE CHECK (discord_id ~ '^[0-9]{1,20}$'),
 ADD COLUMN discord_name text CHECK (length(discord_name) <= 64),
 ADD COLUMN last_login_at timestamptz,
 ADD COLUMN banned_at timestamptz,
 ADD COLUMN banned_until timestamptz,
 ADD COLUMN ban_reason text CHECK (length(ban_reason) <= 200),
 ADD COLUMN muted_until timestamptz,
 ADD COLUMN muted_at timestamptz,
 ADD COLUMN mute_reason text CHECK (length(mute_reason) <= 200),
 ALTER COLUMN salt DROP NOT NULL,
 ALTER COLUMN password_hash DROP NOT NULL,
 ADD CONSTRAINT accounts_one_credential
  CHECK ((discord_id IS NOT NULL) <> (password_hash IS NOT NULL));
-- Only the SHA-256 of a token's 32 raw bytes is stored.
CREATE TABLE sessions (
 token_hash bytea PRIMARY KEY CHECK (octet_length(token_hash) = 32),
 account_id bigint NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL,
 last_seen_at timestamptz,
 client_label text CHECK (length(client_label) <= 64)
);
CREATE INDEX sessions_account ON sessions(account_id, created_at);
