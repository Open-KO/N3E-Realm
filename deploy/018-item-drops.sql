-- General frozen item operations; existing singleton and currency records remain immutable.
ALTER TABLE realm_reward_policy DROP CONSTRAINT realm_reward_policy_mode_check;
ALTER TABLE realm_reward_policy ADD CONSTRAINT realm_reward_policy_mode_check
 CHECK(mode IN ('legacy_v1','contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5'));
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_source_mode_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_source_mode_check
 CHECK(source_mode IN ('contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5'));
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_target_mode_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_target_mode_check
 CHECK(target_mode IN ('contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5'));
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_source_policy_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_source_policy_check CHECK(octet_length(source_policy) BETWEEN 1 AND 16384);
ALTER TABLE reward_policy_upgrades DROP CONSTRAINT reward_policy_upgrades_target_policy_check;
ALTER TABLE reward_policy_upgrades ADD CONSTRAINT reward_policy_upgrades_target_policy_check CHECK(octet_length(target_policy) BETWEEN 1 AND 16384);
ALTER TABLE loot_entitlements DROP CONSTRAINT loot_entitlements_kind_check;
ALTER TABLE loot_entitlements ADD CONSTRAINT loot_entitlements_kind_check CHECK(kind IN (0,1,2));
ALTER TABLE loot_entitlements DROP CONSTRAINT loot_entitlements_quantity_check;
ALTER TABLE loot_entitlements ADD CONSTRAINT loot_entitlements_quantity_check
 CHECK((kind=0 AND quantity=1) OR (kind=1 AND quantity BETWEEN 1 AND 32766) OR (kind=2 AND quantity BETWEEN 1 AND 9999));
ALTER TABLE loot_entitlements ADD COLUMN durability integer NOT NULL DEFAULT 0 CHECK(durability BETWEEN 0 AND 65535);
CREATE OR REPLACE FUNCTION check_settlement_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.owner IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM encounter_recipients WHERE realm=NEW.realm AND encounter=NEW.encounter
   AND character_id=NEW.owner AND
   (reason=0 OR (substring(NEW.payload FROM 1 FOR 4) IN (decode('4e335334','hex'),decode('4e335335','hex'),decode('4e335336','hex')) AND credit>0))) THEN
  RAISE EXCEPTION 'settlement owner must be eligible';
 END IF;
 RETURN NULL;
END $$;
