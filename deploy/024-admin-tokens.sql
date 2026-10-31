-- Admin API tokens (specs/03-admin-api.md). Only the SHA-256 of a token's raw bytes
-- is stored; permissions are concrete (globs are expanded by `admin mint`).
CREATE TABLE admin_tokens (
 name text PRIMARY KEY CHECK (name ~ '^[a-z][a-z0-9-]{0,31}$'),
 token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
 permissions text[] NOT NULL CHECK (array_length(permissions, 1) >= 1),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 last_used_at timestamptz
);
-- A token-authorised operation has no account or character: the token name is the
-- actor. Character rows keep both ids; token rows have neither.
ALTER TABLE admin_audit ADD COLUMN token_name text,
 ALTER COLUMN account_id DROP NOT NULL, ALTER COLUMN character_id DROP NOT NULL,
 ADD CONSTRAINT admin_audit_actor CHECK (
  (token_name IS NULL AND account_id IS NOT NULL AND character_id IS NOT NULL)
  OR (token_name IS NOT NULL AND account_id IS NULL AND character_id IS NULL));
CREATE UNIQUE INDEX admin_audit_token_request ON admin_audit(realm, token_name, request)
 WHERE token_name IS NOT NULL;
