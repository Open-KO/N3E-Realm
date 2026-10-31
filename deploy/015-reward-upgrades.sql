-- Keep the original realm definition and every earned outcome immutable.
CREATE TABLE reward_policy_upgrades (
 realm text NOT NULL REFERENCES realm_reward_policy(realm),
 revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 64),
 source_definition bytea NOT NULL CHECK(octet_length(source_definition)=32),
 target_definition bytea NOT NULL CHECK(octet_length(target_definition)=32),
 source_mode text NOT NULL CHECK(source_mode IN ('contribution_claim_v1','contribution_party_v2')),
 target_mode text NOT NULL CHECK(target_mode='contribution_party_v2'),
 source_policy bytea NOT NULL CHECK(octet_length(source_policy) BETWEEN 1 AND 4096),
 target_policy bytea NOT NULL CHECK(octet_length(target_policy) BETWEEN 1 AND 4096),
 source_base text NOT NULL CHECK(length(source_base)=64),
 target_base text NOT NULL CHECK(length(target_base)=64),
 world_before bytea NOT NULL CHECK(octet_length(world_before) BETWEEN 1 AND 32768),
 world_after bytea NOT NULL CHECK(octet_length(world_after) BETWEEN 1 AND 32768),
 source_generation bigint NOT NULL CHECK(source_generation>0),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(realm,revision), UNIQUE(realm,source_definition), UNIQUE(realm,target_definition),
 CHECK(source_definition<>target_definition)
);
CREATE TRIGGER immutable_reward_upgrade BEFORE UPDATE OR DELETE ON reward_policy_upgrades
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE TABLE active_reward_upgrade (
 realm text PRIMARY KEY REFERENCES realm_reward_policy(realm), revision bigint NOT NULL,
 FOREIGN KEY(realm,revision) REFERENCES reward_policy_upgrades(realm,revision)
);
CREATE FUNCTION advance_reward_upgrade() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.realm<>OLD.realm OR NEW.revision<>OLD.revision+1 THEN
  RAISE EXCEPTION 'reward upgrade must advance once';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER advance_reward_upgrade BEFORE UPDATE ON active_reward_upgrade
 FOR EACH ROW EXECUTE FUNCTION advance_reward_upgrade();
CREATE TRIGGER retain_reward_upgrade BEFORE DELETE ON active_reward_upgrade
 FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE VIEW active_reward_policy AS
 SELECT b.realm,coalesce(u.target_mode,b.mode) AS mode,b.game,
        coalesce(u.target_definition,b.definition) AS definition,
        b.migration_revision,b.legacy_divisor,b.item,b.capacity,b.starting,
        coalesce(a.revision,0) AS upgrade_revision
 FROM realm_reward_policy b LEFT JOIN active_reward_upgrade a USING(realm)
 LEFT JOIN reward_policy_upgrades u ON u.realm=a.realm AND u.revision=a.revision;
CREATE FUNCTION check_reward_upgrade_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE current_policy record;
BEGIN
 SELECT * INTO current_policy FROM active_reward_policy WHERE realm=NEW.realm;
 IF NOT FOUND OR NEW.revision<>current_policy.upgrade_revision+1
    OR NEW.source_definition<>current_policy.definition OR NEW.source_mode<>current_policy.mode THEN
  RAISE EXCEPTION 'reward upgrade source does not match active policy';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER check_reward_upgrade_source BEFORE INSERT ON reward_policy_upgrades
 FOR EACH ROW EXECUTE FUNCTION check_reward_upgrade_source();
