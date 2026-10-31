-- Opt-in N3P3/N3S4 party item routing; prior outcomes retain their old encodings.
ALTER TABLE realm_reward_policy DROP CONSTRAINT realm_reward_policy_mode_check;
ALTER TABLE realm_reward_policy ADD CONSTRAINT realm_reward_policy_mode_check
 CHECK(mode IN ('legacy_v1','contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3'));
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_source_mode_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_source_mode_check
 CHECK(source_mode IN ('contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3'));
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_target_mode_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_target_mode_check
 CHECK(target_mode IN ('contribution_party_v2','contribution_party_loot_v3'));
CREATE TABLE loot_audience (
 realm text NOT NULL, claim_operation bigint NOT NULL, character_id bigint NOT NULL,
 PRIMARY KEY(realm,claim_operation,character_id),
 FOREIGN KEY(realm,claim_operation) REFERENCES loot_entitlements(realm,claim_operation),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm)
);
CREATE INDEX loot_audience_character ON loot_audience(realm,character_id,claim_operation);
CREATE TRIGGER immutable_loot_audience BEFORE UPDATE OR DELETE ON loot_audience
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE TABLE party_loot_cursors (
 realm text NOT NULL REFERENCES realm_ownership(realm),
 generation bigint NOT NULL CHECK(generation>0), party bigint NOT NULL CHECK(party>0),
 cursor integer NOT NULL CHECK(cursor BETWEEN 0 AND 7), revision bigint NOT NULL CHECK(revision>=0),
 PRIMARY KEY(realm,generation,party)
);
CREATE TABLE party_loot_claims (
 realm text NOT NULL, claim_operation bigint NOT NULL,
 claimant bigint NOT NULL, recipient bigint NOT NULL,
 generation bigint NOT NULL CHECK(generation>0), party bigint NOT NULL CHECK(party>=0),
 cursor_before integer NOT NULL CHECK(cursor_before BETWEEN 0 AND 7),
 cursor_after integer NOT NULL CHECK(cursor_after BETWEEN 0 AND 7),
 recipient_name text NOT NULL CHECK(length(recipient_name) BETWEEN 1 AND 24),
 PRIMARY KEY(realm,claim_operation),
 FOREIGN KEY(realm,claim_operation) REFERENCES loot_claim_results(realm,claim_operation),
 FOREIGN KEY(claimant,realm) REFERENCES characters(id,realm),
 FOREIGN KEY(recipient,realm) REFERENCES characters(id,realm)
);
CREATE TRIGGER immutable_party_loot_claim BEFORE UPDATE OR DELETE ON party_loot_claims
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE OR REPLACE FUNCTION check_settlement_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.owner IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM encounter_recipients WHERE realm=NEW.realm AND encounter=NEW.encounter
   AND character_id=NEW.owner AND
   (reason=0 OR (substring(NEW.payload FROM 1 FOR 4)=decode('4e335334','hex') AND credit>0))) THEN
  RAISE EXCEPTION 'settlement owner must be eligible';
 END IF;
 RETURN NULL;
END $$;
