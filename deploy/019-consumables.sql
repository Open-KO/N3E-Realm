-- Recovery lockout survives disconnect and process restart. Bag operations hold
-- the immutable request/result; this row stores only the shared next-use time.
CREATE TABLE character_consumable_cooldowns (
 character_id bigint PRIMARY KEY REFERENCES characters(id),
 ready_at timestamptz NOT NULL
);
