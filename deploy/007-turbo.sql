-- Durable evidence that the live simulation has observed an authority generation.
-- Session/realm fences prevent a previous process acknowledging a new session.
CREATE TABLE movement_authority_observed (
 character_id bigint PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
 session_generation bigint NOT NULL,
 realm_generation bigint NOT NULL,
 generation bigint NOT NULL CHECK(generation>=0)
);
