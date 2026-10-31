-- Multiple immutable drop operations per encounter; retained singleton rows are unchanged.
ALTER TABLE realm_reward_policy DROP CONSTRAINT realm_reward_policy_mode_check;
ALTER TABLE realm_reward_policy ADD CONSTRAINT realm_reward_policy_mode_check
 CHECK(mode IN ('legacy_v1','contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4'));
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_source_mode_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_source_mode_check
 CHECK(source_mode IN ('contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4'));
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_target_mode_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_target_mode_check
 CHECK(target_mode IN ('contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4'));
ALTER TABLE loot_claim_results DROP CONSTRAINT loot_claim_results_realm_encounter_fkey;
ALTER TABLE loot_claim_results DROP CONSTRAINT loot_claim_results_realm_encounter_key;
ALTER TABLE loot_entitlements DROP CONSTRAINT loot_entitlements_pkey;
ALTER TABLE loot_entitlements ADD PRIMARY KEY(realm,encounter,claim_operation);
ALTER TABLE loot_claim_results ADD FOREIGN KEY(realm,encounter,claim_operation)
 REFERENCES loot_entitlements(realm,encounter,claim_operation);
ALTER TABLE loot_entitlements DROP CONSTRAINT loot_entitlements_quantity_check;
ALTER TABLE loot_entitlements ADD COLUMN kind integer NOT NULL DEFAULT 0 CHECK(kind IN (0,1));
ALTER TABLE loot_entitlements ADD CONSTRAINT loot_entitlements_quantity_check
 CHECK((kind=0 AND quantity=1) OR (kind=1 AND quantity BETWEEN 1 AND 32766));
CREATE TABLE coin_claim_recipients (
 realm text NOT NULL, claim_operation bigint NOT NULL, character_id bigint NOT NULL,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 24),
 nominal integer NOT NULL CHECK(nominal BETWEEN 0 AND 32766),
 added integer NOT NULL CHECK(added BETWEEN 0 AND nominal),
 balance integer NOT NULL CHECK(balance BETWEEN added AND 2100000000),
 bag_revision bigint NOT NULL CHECK(bag_revision>=0),
 PRIMARY KEY(realm,claim_operation,character_id),
 FOREIGN KEY(realm,claim_operation) REFERENCES loot_claim_results(realm,claim_operation),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm)
);
CREATE TRIGGER immutable_coin_claim_recipient BEFORE UPDATE OR DELETE ON coin_claim_recipients
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE INDEX entitlement_operation_page ON loot_entitlements(realm,owner,state,claim_operation);
CREATE OR REPLACE FUNCTION check_settlement_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.owner IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM encounter_recipients WHERE realm=NEW.realm AND encounter=NEW.encounter
   AND character_id=NEW.owner AND
   (reason=0 OR (substring(NEW.payload FROM 1 FOR 4) IN (decode('4e335334','hex'),decode('4e335335','hex')) AND credit>0))) THEN
  RAISE EXCEPTION 'settlement owner must be eligible';
 END IF;
 RETURN NULL;
END $$;
