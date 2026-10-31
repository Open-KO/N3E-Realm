-- Account/realm ownership. Bag and storage state plus immutable operation commit together.
CREATE TABLE account_storage (
 account_id bigint NOT NULL REFERENCES accounts(id),
 realm text NOT NULL,
 definition bytea NOT NULL CHECK(octet_length(definition)=32),
 state bytea NOT NULL CHECK(octet_length(state) BETWEEN 1 AND 49152),
 PRIMARY KEY(account_id,realm)
);
CREATE TABLE storage_operations (
 character_id bigint NOT NULL REFERENCES characters(id),
 request text NOT NULL CHECK(length(request) BETWEEN 1 AND 64),
 payload bytea NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 1024),
 result bytea NOT NULL CHECK(octet_length(result) BETWEEN 1 AND 65536),
 PRIMARY KEY(character_id,request)
);
CREATE TRIGGER immutable_storage_operation BEFORE UPDATE OR DELETE ON storage_operations
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
