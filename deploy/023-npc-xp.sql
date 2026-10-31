-- PQ-252 (D-165): an NPC template's base XP is the reference row's iExp, up
-- to the server's TEMPLATE_XP_LIMIT (50,000,000), so one recipient's award
-- reaches PARTY_XP_LIMIT (214,748,364: a party member's award stops at its
-- level's XP / 10, at most 2^31 - 1 over 10; a solo award at 9/5 of the base).
-- Widening only: every stored row stays valid.
ALTER TABLE encounter_recipients DROP CONSTRAINT encounter_recipients_awarded_xp_check;
ALTER TABLE encounter_recipients ADD CONSTRAINT encounter_recipients_awarded_xp_check
 CHECK(awarded_xp BETWEEN 0 AND 214748364);
