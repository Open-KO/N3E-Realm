-- Life transitions and their location are committed together. Runtime IDs stay transient.
ALTER TABLE characters
 ADD COLUMN life_revision bigint NOT NULL DEFAULT 0 CHECK(life_revision>=0),
 ADD COLUMN dead boolean NOT NULL DEFAULT false,
 ADD COLUMN respawn_ready_at timestamptz,
 ADD CONSTRAINT life_deadline CHECK(dead = (respawn_ready_at IS NOT NULL));
