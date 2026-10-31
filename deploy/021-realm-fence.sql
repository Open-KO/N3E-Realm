-- D-145 (PQ-149): the realm fence lock moves off the lease row. Durable
-- transactions lock this row (FOR UPDATE) and then read owner, generation and
-- DB-clock expiry from realm_ownership; a takeover locks it before its
-- conditional upsert. Lease renewal and release update realm_ownership only, so
-- they never wait behind a durable write. Roles lock before this row.
CREATE TABLE realm_fence (
 realm text PRIMARY KEY
);
INSERT INTO realm_fence SELECT realm FROM realm_ownership;
