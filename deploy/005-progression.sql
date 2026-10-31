-- Forward-only contribution history. Existing grants and migration checksums stay intact.
CREATE TABLE realm_reward_policy (
 realm text PRIMARY KEY REFERENCES realm_ownership(realm),
 mode text NOT NULL CHECK(mode IN ('legacy_v1','contribution_claim_v1')),
 game text NOT NULL,
 definition bytea NOT NULL CHECK(octet_length(definition)=32),
 migration_revision integer NOT NULL CHECK(migration_revision=1),
 legacy_divisor integer NOT NULL CHECK(legacy_divisor>0),
 item text NOT NULL, capacity integer NOT NULL CHECK(capacity BETWEEN 1 AND 64),
 starting integer NOT NULL CHECK(starting BETWEEN 0 AND capacity)
);
CREATE TABLE character_reward_progress (
 character_id bigint PRIMARY KEY,
 realm text NOT NULL,
 definition bytea NOT NULL CHECK(octet_length(definition)=32),
 curve_xp bigint NOT NULL CHECK(curve_xp>=0),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0),
 baseline_xp bigint NOT NULL CHECK(baseline_xp>=0),
 baseline_level integer NOT NULL CHECK(baseline_level BETWEEN 1 AND 10),
 baseline_remainder bigint NOT NULL CHECK(baseline_remainder>=0),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm),
 FOREIGN KEY(realm) REFERENCES realm_reward_policy(realm)
);
CREATE TABLE encounter_settlements (
 realm text NOT NULL REFERENCES realm_reward_policy(realm), encounter bigint NOT NULL CHECK(encounter>0),
 source_generation bigint NOT NULL CHECK(source_generation>0),
 release bytea NOT NULL CHECK(octet_length(release)=32), definition bytea NOT NULL CHECK(octet_length(definition)=32),
 payload bytea NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 32768),
 digest bytea NOT NULL CHECK(octet_length(digest)=32),
 zone text NOT NULL CHECK(length(zone) BETWEEN 1 AND 128),
 x real NOT NULL, y real NOT NULL, z real NOT NULL,
 tick bigint NOT NULL CHECK(tick>=0),
 outcome text NOT NULL CHECK(outcome IN ('entitled','no_recipient','loot_capacity')),
 owner bigint,
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(realm,encounter),
 CHECK(x BETWEEN -1000000 AND 1000000 AND y BETWEEN -1000000 AND 1000000 AND z BETWEEN -1000000 AND 1000000),
 CHECK((outcome='no_recipient')=(owner IS NULL))
);
CREATE TABLE encounter_recipients (
 realm text NOT NULL, encounter bigint NOT NULL, character_id bigint NOT NULL,
 credit bigint NOT NULL CHECK(credit BETWEEN 1 AND 100000),
 reason integer NOT NULL CHECK(reason BETWEEN 0 AND 4),
 frozen_level integer NOT NULL CHECK(frozen_level BETWEEN 1 AND 10),
 awarded_xp bigint NOT NULL CHECK(awarded_xp BETWEEN 0 AND 1800000),
 result_xp bigint NOT NULL CHECK(result_xp>=0), result_curve_xp bigint NOT NULL CHECK(result_curve_xp>=0),
 result_level integer NOT NULL CHECK(result_level BETWEEN 1 AND 10), revision bigint NOT NULL CHECK(revision>=0),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(realm,encounter,character_id),
 FOREIGN KEY(realm,encounter) REFERENCES encounter_settlements(realm,encounter),
 FOREIGN KEY(character_id,realm) REFERENCES characters(id,realm),
 CHECK(reason=0 OR awarded_xp=0)
);
ALTER TABLE encounter_settlements ADD FOREIGN KEY(realm,encounter,owner)
 REFERENCES encounter_recipients(realm,encounter,character_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE loot_entitlements (
 realm text NOT NULL, encounter bigint NOT NULL, owner bigint NOT NULL,
 item text NOT NULL, quantity integer NOT NULL CHECK(quantity=1),
 zone text NOT NULL, x real NOT NULL, y real NOT NULL, z real NOT NULL,
 claim_operation bigint NOT NULL CHECK(claim_operation>0), definition bytea NOT NULL CHECK(octet_length(definition)=32),
 created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL CHECK(expires_at>created_at),
 state text NOT NULL DEFAULT 'available' CHECK(state IN ('available','claimed','expired')),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0), result_operation bigint,
 PRIMARY KEY(realm,encounter), UNIQUE(realm,claim_operation),
 FOREIGN KEY(realm,encounter) REFERENCES encounter_settlements(realm,encounter),
 FOREIGN KEY(realm,encounter,owner) REFERENCES encounter_recipients(realm,encounter,character_id),
 FOREIGN KEY(owner,realm) REFERENCES characters(id,realm),
 CHECK((state='available')=(result_operation IS NULL)),
 CHECK(result_operation IS NULL OR result_operation=claim_operation)
);
CREATE TABLE loot_claim_results (
 realm text NOT NULL, claim_operation bigint NOT NULL, encounter bigint NOT NULL,
 owner bigint NOT NULL, payload bytea NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 32768),
 digest bytea NOT NULL CHECK(octet_length(digest)=32), status text NOT NULL CHECK(status IN ('claimed','expired')),
 result_count integer NOT NULL CHECK(result_count BETWEEN 0 AND 64), revision bigint NOT NULL CHECK(revision>=0),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(realm,claim_operation), UNIQUE(realm,encounter),
 FOREIGN KEY(realm,claim_operation) REFERENCES loot_entitlements(realm,claim_operation),
 FOREIGN KEY(realm,encounter) REFERENCES loot_entitlements(realm,encounter),
 FOREIGN KEY(owner,realm) REFERENCES characters(id,realm)
);
ALTER TABLE loot_entitlements ADD FOREIGN KEY(realm,result_operation)
 REFERENCES loot_claim_results(realm,claim_operation) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX entitlement_owner_page ON loot_entitlements(realm,owner,state,expires_at,encounter);
CREATE INDEX entitlement_expiry_page ON loot_entitlements(realm,state,expires_at,encounter);
-- Immutable outcome history cannot accidentally be rewritten by later workers.
CREATE FUNCTION reject_reward_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable reward history'; END $$;
CREATE TRIGGER immutable_settlement BEFORE UPDATE OR DELETE ON encounter_settlements FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE TRIGGER immutable_recipient BEFORE UPDATE OR DELETE ON encounter_recipients FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE TRIGGER immutable_claim_result BEFORE UPDATE OR DELETE ON loot_claim_results FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE TRIGGER immutable_realm_reward_policy BEFORE UPDATE OR DELETE ON realm_reward_policy FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE FUNCTION protect_entitlement_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-'state'-'revision'-'result_operation') IS DISTINCT FROM
    (to_jsonb(OLD)-'state'-'revision'-'result_operation') OR OLD.state<>'available'
    OR NEW.state='available' OR NEW.revision<>OLD.revision+1 THEN
   RAISE EXCEPTION 'immutable entitlement identity/terminal state';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER entitlement_identity BEFORE UPDATE ON loot_entitlements FOR EACH ROW EXECUTE FUNCTION protect_entitlement_identity();
CREATE TRIGGER retain_entitlement BEFORE DELETE ON loot_entitlements FOR EACH ROW EXECUTE FUNCTION reject_reward_history_change();
CREATE INDEX settlement_recipient_history ON encounter_recipients(character_id,committed_at DESC,encounter DESC);
CREATE FUNCTION check_settlement_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.owner IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM encounter_recipients WHERE realm=NEW.realm AND encounter=NEW.encounter
   AND character_id=NEW.owner AND reason=0) THEN
   RAISE EXCEPTION 'settlement owner must be eligible';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER eligible_settlement_owner AFTER INSERT ON encounter_settlements
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_settlement_owner();
