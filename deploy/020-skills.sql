-- Successful spell recast gates survive new sessions and zone restarts.
CREATE TABLE character_skill_cooldowns (
 character_id bigint NOT NULL REFERENCES characters(id),
 skill text NOT NULL CHECK (length(skill) BETWEEN 1 AND 96),
 ready_at timestamptz NOT NULL,
 PRIMARY KEY(character_id,skill)
);
