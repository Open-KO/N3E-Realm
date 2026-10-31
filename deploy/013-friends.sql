CREATE TABLE friend_lists (
 character_id bigint PRIMARY KEY REFERENCES characters(id),
 definition bytea NOT NULL CHECK(octet_length(definition)=32),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0)
);
CREATE TABLE friend_links (
 character_id bigint NOT NULL REFERENCES friend_lists(character_id),
 slot integer NOT NULL CHECK(slot BETWEEN 0 AND 23),
 target_id bigint NOT NULL REFERENCES characters(id),
 PRIMARY KEY(character_id,slot), UNIQUE(character_id,target_id)
);
CREATE TABLE friend_operations (
 character_id bigint NOT NULL REFERENCES friend_lists(character_id),
 request text NOT NULL CHECK(length(request) BETWEEN 1 AND 64),
 payload bytea NOT NULL CHECK(octet_length(payload)<=256),
 result bytea NOT NULL CHECK(octet_length(result)<=8192),
 PRIMARY KEY(character_id,request)
);
CREATE TRIGGER immutable_friend_operation BEFORE UPDATE OR DELETE ON friend_operations
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
