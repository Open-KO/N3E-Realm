CREATE TABLE accounts (
 id bigserial PRIMARY KEY,
 name text NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 32),
 salt bytea NOT NULL CHECK (octet_length(salt)=16),
 password_hash bytea NOT NULL CHECK (octet_length(password_hash)=32),
 password_scheme text NOT NULL DEFAULT 'scrypt-131072-8-1' CHECK(password_scheme='scrypt-131072-8-1')
);
CREATE TABLE characters (
 id bigserial PRIMARY KEY,
 account_id bigint NOT NULL REFERENCES accounts(id),
 realm text NOT NULL REFERENCES realm_ownership(realm),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 24),
 x real NOT NULL DEFAULT 0, y real NOT NULL DEFAULT 0, z real NOT NULL DEFAULT 0,
 session_generation bigint NOT NULL DEFAULT 0 CHECK(session_generation>=0),
 realm_generation bigint NOT NULL DEFAULT 0,
 movement_seq bigint NOT NULL DEFAULT 0,
 online boolean NOT NULL DEFAULT false,
 checkpoint_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(realm,name), UNIQUE(id,realm),
 CHECK(x BETWEEN -1000000 AND 1000000 AND y BETWEEN -1000000 AND 1000000 AND z BETWEEN -1000000 AND 1000000)
);
CREATE INDEX characters_account ON characters(account_id,realm);
CREATE TABLE character_roles (
 character_id bigint NOT NULL,
 realm text NOT NULL,
 zone text NOT NULL,
 capability text NOT NULL,
 PRIMARY KEY(character_id,realm,zone,capability),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm) ON DELETE CASCADE
);
-- Runtime instances never alias after reconnect/restart; sequence gaps are harmless.
CREATE SEQUENCE entity_instances AS bigint NO CYCLE;
