-- Stable lock exists even for characters with no roles. Role lock precedes realm
-- ownership, character session and revision locks in every administrative writer.
CREATE TABLE admin_authority (
 character_id bigint PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
 generation bigint NOT NULL DEFAULT 0 CHECK(generation>=0)
);
CREATE TABLE world_revisions (
 realm text NOT NULL REFERENCES realm_ownership(realm),
 revision bigint NOT NULL CHECK(revision>=0),
 base text NOT NULL CHECK(length(base)=64),
 state bytea NOT NULL CHECK(octet_length(state)<=32768),
 PRIMARY KEY(realm,revision)
);
CREATE TABLE admin_results (
 realm text NOT NULL,
 character_id bigint NOT NULL REFERENCES characters(id),
 request text NOT NULL CHECK(length(request) BETWEEN 1 AND 64),
 payload bytea NOT NULL CHECK(octet_length(payload)<=32768),
 result bytea NOT NULL CHECK(octet_length(result)<=32768),
 PRIMARY KEY(realm,character_id,request)
);
CREATE TABLE admin_audit (
 id bigserial PRIMARY KEY,
 realm text NOT NULL, account_id bigint NOT NULL, character_id bigint NOT NULL,
 request text NOT NULL, revision bigint NOT NULL,
 target text NOT NULL, reason text NOT NULL CHECK(length(reason)<=160),
 before_state bytea NOT NULL, after_state bytea NOT NULL,
 outcome text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(realm,character_id,request)
);
CREATE TABLE role_audit (
 id bigserial PRIMARY KEY, character_id bigint NOT NULL, realm text NOT NULL,
 capability text NOT NULL, granted boolean NOT NULL, generation bigint NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
