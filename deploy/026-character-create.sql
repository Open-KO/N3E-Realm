-- RQ-002 (content/character-create.md, "The realm's create"): what a create
-- chose, kept with the character. Nation, race, specialty, face, hair and stats
-- are all set or all NULL: NULL for a character created before this migration or
-- under a package without create rules. The slot is backfilled in creation
-- order; a row a test fixture inserts without one stays NULL.
ALTER TABLE characters
 ADD COLUMN slot smallint CHECK (slot BETWEEN 0 AND 255),
 ADD COLUMN nation smallint CHECK (nation BETWEEN 1 AND 255),
 ADD COLUMN race integer CHECK (race BETWEEN 1 AND 65535),
 ADD COLUMN specialty integer CHECK (specialty BETWEEN 1 AND 65535),
 ADD COLUMN face smallint CHECK (face BETWEEN 0 AND 255),
 ADD COLUMN hair smallint CHECK (hair BETWEEN 0 AND 255),
 ADD COLUMN stats integer[] CHECK (array_ndims(stats) = 1 AND cardinality(stats) BETWEEN 1 AND 8
  AND 0 <= ALL(stats) AND 1000000 >= ALL(stats)),
 -- Q99: a new name is unique in its realm without regard to case. An existing
 -- name keeps its row as it is (NULL here); the create checks it too.
 ADD COLUMN name_folded text CHECK (name_folded = lower(name)),
 ADD CONSTRAINT characters_create_whole CHECK (num_nulls(nation, race, specialty, face, hair, stats) IN (0, 6));
UPDATE characters c SET slot = n.slot
 FROM (SELECT id, row_number() OVER (PARTITION BY account_id, realm ORDER BY id) - 1 AS slot FROM characters) n
 WHERE c.id = n.id AND n.slot <= 255;
CREATE UNIQUE INDEX characters_slot ON characters(account_id, realm, slot);
CREATE UNIQUE INDEX characters_name_folded ON characters(realm, name_folded);
