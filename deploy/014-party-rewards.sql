-- Existing immutable outcomes and migration checksums remain intact.
ALTER TABLE realm_reward_policy DROP CONSTRAINT realm_reward_policy_mode_check;
ALTER TABLE realm_reward_policy ADD CONSTRAINT realm_reward_policy_mode_check
 CHECK(mode IN ('legacy_v1','contribution_claim_v1','contribution_party_v2'));
ALTER TABLE encounter_recipients DROP CONSTRAINT encounter_recipients_credit_check;
ALTER TABLE encounter_recipients ADD CONSTRAINT encounter_recipients_credit_check
 CHECK(credit BETWEEN 0 AND 100000);
ALTER TABLE encounter_recipients DROP CONSTRAINT encounter_recipients_awarded_xp_check;
ALTER TABLE encounter_recipients ADD CONSTRAINT encounter_recipients_awarded_xp_check
 CHECK(awarded_xp BETWEEN 0 AND 13200000);
-- The canonical N3S3 payload freezes party identities, level and contributing IDs.
-- Old N3S2 canonical validation still requires positive credit and its old XP cap.
