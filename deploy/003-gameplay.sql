-- One nonstacking item vocabulary in P3. Each count consumes a slot.
CREATE TABLE character_progress (
 character_id bigint PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
 item text NOT NULL,
 count integer NOT NULL CHECK(count BETWEEN 0 AND 64),
 capacity integer NOT NULL CHECK(capacity BETWEEN 1 AND 64),
 xp bigint NOT NULL DEFAULT 0 CHECK(xp>=0),
 CHECK(count<=capacity)
);
CREATE TABLE reward_operations (
 operation bigint PRIMARY KEY CHECK(operation>0),
 character_id bigint NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
 realm text NOT NULL,
 item text NOT NULL,
 quantity integer NOT NULL CHECK(quantity BETWEEN 1 AND 64),
 xp_grant integer NOT NULL CHECK(xp_grant>0),
 status text NOT NULL CHECK(status IN ('committed','inventory_full')),
 result_count integer NOT NULL CHECK(result_count BETWEEN 0 AND 64),
 result_xp bigint NOT NULL CHECK(result_xp>=0),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm) ON DELETE CASCADE
);
CREATE INDEX reward_recipient ON reward_operations(character_id,operation DESC);
