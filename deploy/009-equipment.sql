-- Compatibility barrier: BagState now retains durable equipment records.
-- Earlier binaries must fail schema verification instead of discarding unknown
-- protobuf fields when saving a bag after a purchase, move, or loot claim.
COMMENT ON COLUMN character_bags.state IS 'Versioned BagState including equipment; requires schema 9 readers';
