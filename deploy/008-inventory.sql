-- Whole item records and original transaction outcomes; no legacy history rewrite.
CREATE SEQUENCE item_instances AS bigint NO CYCLE;
CREATE TABLE character_bags (
 character_id bigint PRIMARY KEY,
 realm text NOT NULL,
 definition bytea NOT NULL CHECK(octet_length(definition)=32),
 state bytea NOT NULL CHECK(octet_length(state) BETWEEN 1 AND 32768),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm)
);
CREATE TABLE bag_operations (
 character_id bigint NOT NULL REFERENCES character_bags(character_id),
 request text NOT NULL CHECK(length(request) BETWEEN 1 AND 64),
 payload bytea NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 512),
 result bytea NOT NULL CHECK(octet_length(result) BETWEEN 1 AND 32768),
 PRIMARY KEY(character_id,request)
);
CREATE TRIGGER immutable_bag_operation BEFORE UPDATE OR DELETE ON bag_operations
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
