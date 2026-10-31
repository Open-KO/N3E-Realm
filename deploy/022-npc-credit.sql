-- PQ-251 (D-164): NPC templates reach 2,000,000 health, so an encounter's
-- credit (damage dealt) is bounded by the server's CREDIT_LIMIT (100,000,000)
-- instead of 100,000. Widening only: every stored row stays valid.
ALTER TABLE encounter_recipients DROP CONSTRAINT encounter_recipients_credit_check;
ALTER TABLE encounter_recipients ADD CONSTRAINT encounter_recipients_credit_check
 CHECK(credit BETWEEN 0 AND 100000000);
