CREATE TABLE realm_ownership (
 realm text PRIMARY KEY,
 owner text NOT NULL,
 generation bigint NOT NULL CHECK (generation > 0),
 expires timestamptz NOT NULL
);
-- Future durable transactions must take this row lock and verify owner,
-- generation and DB-clock expiry before mutation. Roles lock before this row.
