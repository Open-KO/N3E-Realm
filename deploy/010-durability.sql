-- Immutable ordinary wear outcomes. Event IDs come from the existing bounded instance allocator.
CREATE TABLE durability_operations (
 realm text NOT NULL,
 event bigint NOT NULL CHECK(event>0),
 character_id bigint NOT NULL,
 payload bytea NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 4096),
 committed boolean NOT NULL,
 state bytea NOT NULL CHECK(octet_length(state) BETWEEN 1 AND 32768),
 PRIMARY KEY(realm,event),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm)
);
CREATE TRIGGER immutable_durability_operation BEFORE UPDATE OR DELETE ON durability_operations
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
