CREATE TABLE storage_credentials (
 account_id bigint NOT NULL REFERENCES accounts(id),realm text NOT NULL,
 definition bytea NOT NULL CHECK(octet_length(definition)=32),
 revision bigint NOT NULL CHECK(revision>0),
 salt bytea NOT NULL CHECK(octet_length(salt)=16),
 verifier bytea NOT NULL CHECK(octet_length(verifier)=32),
 PRIMARY KEY(account_id,realm)
);
CREATE TABLE storage_authorizations (
 character_id bigint PRIMARY KEY REFERENCES characters(id),
 account_id bigint NOT NULL,realm text NOT NULL,
 FOREIGN KEY(account_id,realm) REFERENCES storage_credentials(account_id,realm),
 session_generation bigint NOT NULL CHECK(session_generation>0),
 realm_generation bigint NOT NULL CHECK(realm_generation>0),
 credential_revision bigint NOT NULL CHECK(credential_revision>0)
);
-- The request verifier is deliberately a slow salted hash, not a raw payload or fast digest.
CREATE TABLE storage_credential_operations (
 account_id bigint NOT NULL REFERENCES accounts(id),realm text NOT NULL,
 request text NOT NULL CHECK(length(request) BETWEEN 1 AND 64),
 salt bytea NOT NULL CHECK(octet_length(salt)=16),
 verifier bytea NOT NULL CHECK(octet_length(verifier)=32),
 status text NOT NULL CHECK(status IN ('unlocked','changed','invalid_credentials','credential_changed')),
 revision bigint NOT NULL CHECK(revision>0),
 PRIMARY KEY(account_id,realm,request)
);
CREATE TRIGGER immutable_storage_credential_operation BEFORE UPDATE OR DELETE ON storage_credential_operations
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
