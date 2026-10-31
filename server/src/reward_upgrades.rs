//! Explicit offline reward definition transitions. Earned values and history are never rebased.
use crate::{
    accounts::Owner,
    content::{Result, bad},
    persistence,
    progression::Policy,
};
use prost::Message;

fn compatible(old: &Policy, new: &Policy) -> Result<()> {
    old.validate()?;
    new.validate()?;
    if (old.items.is_some() && new.items.is_none()) || (old.coins.is_some() && new.coins.is_none())
        || (old.party_loot.is_some() && new.party_loot.is_none())
        || new.party_rewards.is_none()
        || old.hash == new.hash
        || old.thresholds != new.thresholds
        || old.curve != new.curve
        || old.item != new.item
        || old.capacity != new.capacity
        || old.starting != new.starting
    {
        return Err(bad(
            "reward upgrade requires a new party policy with unchanged curve and inventory identity",
        ));
    }
    Ok(())
}

pub fn upgrade(
    c: &mut postgres::Client,
    o: &Owner,
    old_release: &crate::content::Release,
    new_release: &crate::content::Release,
) -> Result<u64> {
    let old = old_release
        .rules
        .progression
        .as_ref()
        .ok_or_else(|| bad("source needs progression"))?;
    let new = new_release
        .rules
        .progression
        .as_ref()
        .ok_or_else(|| bad("target needs progression"))?;
    let game = &old_release.game;
    if game != &new_release.game {
        return Err(bad("reward upgrade game mismatch"));
    }
    let mut source_assets = old_release.assets.clone();
    let mut target_assets = new_release.assets.clone();
    for name in ["progression.bin", "recipe.json"] {
        source_assets.remove(name);
        target_assets.remove(name);
    }
    // The first party policy may accompany activation of grouped rewards.
    // An existing policy and every other dependency must remain identical.
    if !source_assets.contains_key("party.bin") {
        target_assets.remove("party.bin");
    }
    if source_assets != target_assets {
        return Err(bad("non-reward package dependency changed"));
    }
    compatible(old, new)?;
    let source = old.encode()?;
    let target = new.encode()?;
    let mut t = c.transaction()?;
    t.batch_execute("SET LOCAL statement_timeout='10s'; SET LOCAL transaction_timeout='15s'")?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    // Both realm rows stay locked throughout: `fence` holds the realm_fence row
    // and this expiry update holds the realm_ownership lease row (D-145). A crash
    // rolls this extension back; another owner cannot acquire while any part of
    // the transition is in flight. This offline owner runs no renewal thread.
    t.execute(
        "UPDATE realm_ownership SET expires=clock_timestamp()+interval '30 seconds' WHERE realm=$1",
        &[&o.realm],
    )?;
    let active = t
        .query_opt(
            "SELECT mode,definition,game,upgrade_revision FROM active_reward_policy WHERE realm=$1",
            &[&o.realm],
        )?
        .ok_or_else(|| bad("reward realm is not converted"))?;
    let current: Vec<u8> = active.get(1);
    let revision: i64 = active.get(3);
    if active.get::<_, String>(2) != game.as_str()
        || !old.curve.starts_with(&format!("{game}:"))
        || !new.curve.starts_with(&format!("{game}:"))
    {
        return Err(bad("reward upgrade game mismatch"));
    }
    if current == new.hash && active.get::<_, String>(0) == new.mode() {
        let retry=t.query_opt("SELECT source_policy,target_policy,source_base,target_base FROM reward_policy_upgrades WHERE realm=$1 AND revision=$2 AND source_definition=$3 AND target_definition=$4",&[&o.realm,&revision,&old.hash,&new.hash])?;
        if retry.is_some_and(|r| {
            r.get::<_, Vec<u8>>(0) == source
                && r.get::<_, Vec<u8>>(1) == target
                && r.get::<_, String>(2) == old_release.hash
                && r.get::<_, String>(3) == new_release.hash
        }) {
            t.commit()?;
            return Ok(revision as u64);
        }
        return Err(bad("reward upgrade retry conflict"));
    }
    if current != old.hash || active.get::<_, String>(0) != old.mode() || revision >= 64 {
        return Err(bad("reward upgrade source/revision conflict"));
    }
    if t.query_opt("SELECT realm FROM reward_policy_upgrades WHERE realm=$1 AND (source_definition=$2 OR target_definition=$2)",&[&o.realm,&new.hash])?.is_some() {
        return Err(bad("reward definition rollback forbidden"));
    }
    let actors = t.query(
        "SELECT id,online,realm_generation FROM characters WHERE realm=$1 ORDER BY id FOR UPDATE",
        &[&o.realm],
    )?;
    if actors
        .iter()
        .any(|r| r.get::<_, bool>(1) && r.get::<_, i64>(2) == o.generation)
    {
        return Err(bad("reward upgrade requires offline characters"));
    }
    for row in &actors {
        let id: i64 = row.get(0);
        let r=t.query_opt("SELECT r.definition,p.item,p.capacity FROM character_reward_progress r JOIN character_progress p USING(character_id) WHERE r.character_id=$1 AND r.realm=$2 FOR UPDATE OF r,p",&[&id,&o.realm])?.ok_or_else(||bad("reward upgrade character progress missing"))?;
        if r.get::<_, Vec<u8>>(0) != old.hash
            || r.get::<_, String>(1) != old.item
            || r.get::<_, i32>(2) != old.capacity as i32
        {
            return Err(bad("reward upgrade character definition conflict"));
        }
    }
    let world_row = t.query_opt(
        "SELECT state FROM world_revisions WHERE realm=$1 ORDER BY revision DESC LIMIT 1",
        &[&o.realm],
    )?;
    let world = if let Some(row) = &world_row {
        crate::wire::Revision::decode(row.get::<_, Vec<u8>>(0).as_slice())?
    } else {
        crate::administration::baseline(old_release)
    };
    crate::administration::validate(old_release, &world)?;
    let mut next_world = world.clone();
    next_world.base = new_release.hash.clone();
    next_world.tick = 0;
    next_world.revision = next_world
        .revision
        .checked_add(1)
        .filter(|&v| v < i64::MAX as u64)
        .ok_or_else(|| bad("world revision exhausted"))?;
    crate::administration::validate(new_release, &next_world)?;
    let before = world.encode_to_vec();
    let after = next_world.encode_to_vec();
    fault("before_mutation");
    let revision = revision + 1;
    t.execute("INSERT INTO reward_policy_upgrades(realm,revision,source_definition,target_definition,source_mode,target_mode,source_policy,target_policy,source_generation,source_base,target_base,world_before,world_after) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
        &[&o.realm,&revision,&old.hash,&new.hash,&old.mode(),&new.mode(),&source,&target,&o.generation,&old_release.hash,&new_release.hash,&before,&after])?;
    if world_row.is_none() {
        t.execute(
            "INSERT INTO world_revisions VALUES($1,$2,$3,$4)",
            &[
                &o.realm,
                &(world.revision as i64),
                &old_release.hash,
                &before,
            ],
        )?;
    }
    t.execute(
        "INSERT INTO world_revisions VALUES($1,$2,$3,$4)",
        &[
            &o.realm,
            &(next_world.revision as i64),
            &new_release.hash,
            &after,
        ],
    )?;
    // XP, curve XP, original baselines, inventory and all encounter/claim rows stay byte-for-byte intact.
    t.execute(
        "UPDATE character_reward_progress SET definition=$2,revision=revision+1 WHERE realm=$1",
        &[&o.realm, &new.hash],
    )?;
    fault("during_mutation");
    t.execute("INSERT INTO active_reward_upgrade VALUES($1,$2) ON CONFLICT(realm) DO UPDATE SET revision=excluded.revision",&[&o.realm,&revision])?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    fault("before_commit");
    t.commit()?;
    fault("after_commit");
    Ok(revision as u64)
}

/// Resolve immutable rules for a drop earned before an explicit compatible upgrade.
/// The current active policy and progress definition must already have been checked.
pub fn earned_policy(
    t: &mut postgres::Transaction<'_>,
    realm: &str,
    current: &Policy,
    definition: &[u8],
) -> Result<Policy> {
    if definition == current.hash {
        return Ok(current.clone());
    }
    let row=t.query_opt("SELECT source_policy FROM reward_policy_upgrades WHERE realm=$1 AND source_definition=$2",&[&realm,&definition])?.ok_or_else(||bad("unknown earned reward definition"))?;
    let old = Policy::decode(row.get(0))?;
    if old.hash != definition {
        return Err(bad("earned reward definition digest"));
    }
    compatible(&old, current)?;
    Ok(old)
}

fn fault(point: &str) {
    if std::env::var("N3E_REWARD_UPGRADE_FAULT").as_deref() == Ok(point) {
        eprintln!("reward upgrade fault {point}");
        std::process::exit(98);
    }
}

/// An authorized editor may revert old values across proven reward-only transitions.
/// History itself is never rewritten; the caller will append a fresh current-base revision.
pub fn rebase_world(
    t: &mut postgres::Transaction<'_>,
    realm: &str,
    r: &crate::content::Release,
    state: &mut crate::wire::Revision,
) -> Result<()> {
    if state.base == r.hash {
        return Ok(());
    }
    let known=t.query_opt("SELECT u.realm FROM reward_policy_upgrades u JOIN active_reward_upgrade a ON a.realm=u.realm JOIN reward_policy_upgrades head ON head.realm=a.realm AND head.revision=a.revision WHERE u.realm=$1 AND u.source_base=$2 AND head.target_base=$3",&[&realm,&state.base,&r.hash])?;
    if known.is_none() {
        return Err(bad("incompatible world revision base"));
    }
    state.base = r.hash.clone();
    crate::administration::validate(r, state)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        accounts::Selected,
        loot,
        progression::{Recipient, Settlement},
        settlements, wire,
    };
    fn releases() -> (
        crate::content::Release,
        crate::content::Release,
        crate::content::Release,
    ) {
        let root = std::path::PathBuf::from(std::env::var("N3E_UPGRADE_FIXTURES").unwrap());
        let load = |name| crate::content::load(&root.join(name).join("package")).unwrap();
        (load("source"), load("target"), load("next"))
    }
    fn upgrade(
        c: &mut postgres::Client,
        o: &Owner,
        old: &Policy,
        new: &Policy,
        game: &str,
    ) -> Result<u64> {
        compatible(old, new)?;
        old.encode()?;
        new.encode()?;
        let (a, b, d) = releases();
        let all = [a, b, d];
        let source = all
            .iter()
            .find(|r| r.rules.progression.as_ref().unwrap().hash == old.hash)
            .ok_or_else(|| bad("source fixture"))?;
        let target = all
            .iter()
            .find(|r| r.rules.progression.as_ref().unwrap().hash == new.hash)
            .ok_or_else(|| bad("target fixture"))?;
        if source.game != game {
            return Err(bad("game mismatch"));
        }
        super::upgrade(c, o, source, target)
    }
    fn policies() -> (Policy, Policy, Policy) {
        let root = std::path::PathBuf::from(std::env::var("N3E_UPGRADE_FIXTURES").unwrap());
        let load = |name| Policy::load(&root.join(name).join("package/progression.bin")).unwrap();
        (load("source"), load("target"), load("next"))
    }
    fn event(c: &mut postgres::Client, o: &Owner, p: &Policy, id: i64) -> Settlement {
        let next = |c: &mut postgres::Client| {
            c.query_one("SELECT nextval('entity_instances')", &[])
                .unwrap()
                .get::<_, i64>(0) as u64
        };
        let level = 3;
        let xp = if p.party_rewards.is_some() {
            crate::party_rewards::solo(p.base_xp as f64, p.npc_level, level)
        } else {
            p.award(60, 60, level).unwrap()
        };
        Settlement {
            npc: None,
            items: None, coins: None,
            loot_order: p.party_loot.as_ref().map(|_| vec![id]),
            parties: p.party_rewards.as_ref().map(|_| vec![]),
            encounter: next(c),
            generation: o.generation,
            release: vec![3; 32],
            definition: p.hash.clone(),
            zone: "demo".into(),
            position: [0.; 3],
            tick: 1,
            claim: next(c),
            recipients: vec![Recipient {
                id,
                credit: 60,
                reason: 0,
                level,
                xp,
            }],
        }
    }
    fn selected(c: &mut postgres::Client, o: &Owner, id: i64) -> Result<Selected> {
        c.execute("UPDATE characters SET online=true,realm_generation=$2,session_generation=1 WHERE id=$1",&[&id,&o.generation])?;
        Ok(Selected {
            id,
            generation: 1,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            entity: wire::Entity {
                id: 9,
                name: "Saved".into(),
                health: 100,
                x: 2.,
                ..Default::default()
            },
        })
    }
    #[test]
    #[ignore = "child process of durable_contract"]
    fn fault_worker() -> Result<()> {
        let mut c = persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
        let realm = std::env::var("N3E_UPGRADE_REALM")?;
        let row = c.query_one(
            "SELECT owner,generation FROM realm_ownership WHERE realm=$1",
            &[&realm],
        )?;
        let o = Owner {
            realm,
            owner: row.get(0),
            generation: row.get(1),
        };
        let (_, old, new) = policies();
        upgrade(&mut c, &o, &old, &new, "demo")?;
        Ok(())
    }
    #[test]
    #[ignore = "tests/reward_upgrades_db.py supplies disposable PostgreSQL"]
    fn durable_contract() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let mut c = persistence::connect(&url)?;
        let (old, new, next) = policies();
        for p in [&old, &new, &next] {
            assert_eq!(Policy::decode(p.encode()?)?.hash, p.hash);
        }
        let realm = format!("test-reward-upgrade-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "test")?;
        let o = Owner {
            realm: realm.clone(),
            owner: "test".into(),
            generation,
        };
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let id: i64 = c
            .query_one(
                "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'Saved') RETURNING id",
                &[&account, &realm],
            )?
            .get(0);
        c.execute("INSERT INTO character_progress(character_id,item,count,capacity,xp) VALUES($1,$2,2,$3,45)",&[&id,&old.item,&(old.capacity as i32)])?;
        settlements::convert(&mut c, &o, &old, "demo", 20)?;
        let first = event(&mut c, &o, &old, id);
        settlements::settle(&mut c, &o, &old, &first)?;
        let pending = event(&mut c, &o, &old, id);
        settlements::settle(&mut c, &o, &old, &pending)?;
        let s = selected(&mut c, &o, id)?;
        let claim = |e: &Settlement| wire::Claim {
            operation: e.claim,
            encounter: e.encounter,
            item: old.item.clone(),
            quantity: 1,
            session: 1,
            seq: 1,
            entity: 9,
        };
        let original = loot::decide(
            &mut c,
            &o,
            &old,
            first.claim,
            Some((&s, &claim(&first), "demo")),
        )?;
        assert_eq!(original.status, "claimed");
        assert!(upgrade(&mut c, &o, &old, &new, "demo").is_err()); // authenticated current session
        c.execute("UPDATE characters SET online=false WHERE id=$1", &[&id])?;
        let snapshot = |c: &mut postgres::Client| -> Result<(i64, i64, i64, i32, i64, i32)> {
            let r=c.query_one("SELECT p.xp,r.curve_xp,r.baseline_xp,r.baseline_level,r.baseline_remainder,p.count FROM character_reward_progress r JOIN character_progress p USING(character_id) WHERE r.character_id=$1",&[&id])?;
            Ok((r.get(0), r.get(1), r.get(2), r.get(3), r.get(4), r.get(5)))
        };
        let before = snapshot(&mut c)?;
        let history = |c: &mut postgres::Client| -> Result<String> {
            Ok(c.query_one("SELECT md5(string_agg(row_to_json(r)::text,'' ORDER BY encounter)) FROM encounter_settlements r WHERE realm=$1",&[&realm])?.get(0))
        };
        let old_history = history(&mut c)?;
        let (source_release, target_release, next_release) = releases();
        let mut edited = crate::administration::startup(&mut c, &o, &source_release)?;
        edited.revision = 1;
        let light = source_release
            .properties
            .iter()
            .position(|p| p.kind == 0)
            .unwrap();
        edited.values[light].value = 0.23;
        crate::administration::validate(&source_release, &edited)?;
        c.execute(
            "INSERT INTO world_revisions VALUES($1,1,$2,$3)",
            &[&realm, &source_release.hash, &edited.encode_to_vec()],
        )?;
        let mut changed_assets = target_release.clone();
        changed_assets
            .assets
            .insert("collision.bin".into(), vec![0; 32]);
        assert!(super::upgrade(&mut c, &o, &source_release, &changed_assets).is_err());
        let mut changed_curve = new.clone();
        changed_curve.thresholds[1] += 1;
        changed_curve.party_rewards.as_mut().unwrap().level_xp[0] += 1;
        changed_curve.party_rewards.as_mut().unwrap().level_xp[1] -= 1;
        assert!(upgrade(&mut c, &o, &old, &changed_curve, "demo").is_err());
        let mut changed_item = new.clone();
        changed_item.item = "demo:item/different".into();
        assert!(upgrade(&mut c, &o, &old, &changed_item, "demo").is_err());
        let mut invalid_bytes = old.clone();
        invalid_bytes.author.push('!');
        assert!(upgrade(&mut c, &o, &invalid_bytes, &new, "demo").is_err());
        assert!(upgrade(&mut c, &o, &old, &new, "different").is_err());
        assert_eq!(upgrade(&mut c, &o, &old, &new, "demo")?, 1);
        assert_eq!(snapshot(&mut c)?, before);
        assert_eq!(history(&mut c)?, old_history);
        let activated = crate::administration::startup(&mut c, &o, &target_release)?;
        assert_eq!(activated.values, edited.values);
        assert_eq!(activated.revision, 2);
        assert_eq!(
            c.query_one(
                "SELECT state FROM world_revisions WHERE realm=$1 AND revision=1",
                &[&realm]
            )?
            .get::<_, Vec<u8>>(0),
            edited.encode_to_vec()
        );
        assert_eq!(upgrade(&mut c, &o, &old, &new, "demo")?, 1);
        assert!(settlements::check_start(&mut c, &realm, Some(&old)).is_err());
        settlements::check_start(&mut c, &realm, Some(&new))?;
        assert_eq!(
            c.query_one(
                "SELECT definition FROM realm_reward_policy WHERE realm=$1",
                &[&realm]
            )?
            .get::<_, Vec<u8>>(0),
            old.hash
        );
        assert!(
            c.execute(
                "UPDATE reward_policy_upgrades SET source_generation=2 WHERE realm=$1",
                &[&realm]
            )
            .is_err()
        );
        assert!(
            c.execute(
                "DELETE FROM active_reward_upgrade WHERE realm=$1",
                &[&realm]
            )
            .is_err()
        );
        // Pending and already-claimed old drops retain their exact outcomes and original radius3.
        let s = selected(&mut c, &o, id)?;
        c.execute(
            "INSERT INTO character_roles VALUES($1,$2,'*','world.edit')",
            &[&id, &realm],
        )?;
        let request = wire::AdminRequest {
            session: 1,
            id: "upgrade-revert".into(),
            operation: "revert".into(),
            base: target_release.hash.clone(),
            expected: 2,
            revision: 1,
            reason: "restore prior compatible values".into(),
            ..Default::default()
        };
        let (admin_result, _) =
            crate::administration::execute(&mut c, &o, &s, &target_release, &request)?;
        assert_eq!(admin_result.status, "committed");
        assert_eq!(admin_result.state.as_ref().unwrap().values, edited.values);
        assert_eq!(
            loot::decide(
                &mut c,
                &o,
                &new,
                first.claim,
                Some((&s, &claim(&first), "demo"))
            )?,
            original
        );
        assert_eq!(
            loot::decide(
                &mut c,
                &o,
                &new,
                pending.claim,
                Some((&s, &claim(&pending), "demo"))
            )?
            .status,
            "claimed"
        );
        let current = event(&mut c, &o, &new, id);
        settlements::settle(&mut c, &o, &new, &current)?;
        assert_eq!(
            loot::decide(
                &mut c,
                &o,
                &new,
                current.claim,
                Some((&s, &claim(&current), "demo"))
            )?
            .status,
            "out_of_range"
        );
        c.execute("UPDATE characters SET online=false WHERE id=$1", &[&id])?;
        let before = snapshot(&mut c)?;
        let world_before = crate::administration::startup(&mut c, &o, &target_release)?;
        let revision: i64 = c
            .query_one(
                "SELECT revision FROM character_reward_progress WHERE character_id=$1",
                &[&id],
            )?
            .get(0);
        for point in ["during_mutation", "before_commit", "after_commit"] {
            let output = std::process::Command::new(std::env::current_exe()?)
                .args([
                    "reward_upgrades::tests::fault_worker",
                    "--ignored",
                    "--exact",
                    "--nocapture",
                ])
                .env("N3E_UPGRADE_REALM", &realm)
                .env("N3E_REWARD_UPGRADE_FAULT", point)
                .output()?;
            assert_eq!(
                output.status.code(),
                Some(98),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            assert_eq!(snapshot(&mut c)?, before);
            let world=wire::Revision::decode(c.query_one("SELECT state FROM world_revisions WHERE realm=$1 ORDER BY revision DESC LIMIT 1",&[&realm])?.get::<_,Vec<u8>>(0).as_slice())?;
            assert_eq!(world.values, edited.values);
            assert_eq!(
                world.revision,
                world_before.revision + if point == "after_commit" { 1 } else { 0 }
            );
            let expected = if point == "after_commit" {
                next.hash.clone()
            } else {
                new.hash.clone()
            };
            assert_eq!(
                c.query_one(
                    "SELECT definition FROM active_reward_policy WHERE realm=$1",
                    &[&realm]
                )?
                .get::<_, Vec<u8>>(0),
                expected
            );
        }
        assert_eq!(upgrade(&mut c, &o, &new, &next, "demo")?, 2);
        assert_eq!(
            c.query_one(
                "SELECT revision FROM character_reward_progress WHERE character_id=$1",
                &[&id]
            )?
            .get::<_, i64>(0),
            revision + 1
        );
        assert!(upgrade(&mut c, &o, &next, &new, "demo").is_err());
        assert!(upgrade(&mut c, &o, &old, &next, "demo").is_err());
        let current_world = crate::administration::startup(&mut c, &o, &next_release)?;
        assert_eq!(current_world.values, edited.values);
        let s = selected(&mut c, &o, id)?;
        assert_eq!(
            crate::administration::execute(&mut c, &o, &s, &next_release, &request)?.0,
            admin_result
        );
        c.execute("UPDATE characters SET online=false WHERE id=$1", &[&id])?;
        let mut t = c.transaction()?;
        assert_eq!(
            earned_policy(&mut t, &realm, &next, &old.hash)?.claim_radius,
            3.
        );
        assert!(earned_policy(&mut t, &realm, &next, &[0; 32]).is_err());
        t.rollback()?;
        // New characters initialize from the active definition, not the immutable baseline.
        let mut t = c.transaction()?;
        persistence::fence(&mut t, &realm, &o.owner, o.generation)?;
        let extra: i64 = t
            .query_one(
                "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'New') RETURNING id",
                &[&account, &realm],
            )?
            .get(0);
        settlements::initialize(&mut t, &realm, extra)?;
        t.commit()?;
        assert_eq!(
            c.query_one(
                "SELECT definition FROM character_reward_progress WHERE character_id=$1",
                &[&extra]
            )?
            .get::<_, Vec<u8>>(0),
            next.hash
        );
        // Activate routed loot without reinterpreting an existing N3P2 drop.
        let pending_v2 = event(&mut c, &o, &next, id);
        settlements::settle(&mut c, &o, &next, &pending_v2)?;
        let root = std::path::PathBuf::from(std::env::var("N3E_UPGRADE_FIXTURES")?);
        let loot_release = crate::content::load(&root.join("loot/package"))?;
        let routed = loot_release.rules.progression.as_ref().unwrap();
        let before_loot = snapshot(&mut c)?;
        assert_eq!(super::upgrade(&mut c, &o, &next_release, &loot_release)?, 3);
        assert_eq!(snapshot(&mut c)?, before_loot);
        assert_eq!(super::upgrade(&mut c, &o, &next_release, &loot_release)?, 3);
        assert!(compatible(routed, &next).is_err());
        let mut actor = selected(&mut c, &o, id)?;
        actor.entity.x = 0.;
        let admission = crate::party_loot::Admission {
            issued: std::time::Instant::now(),
            group: 0,
            slots: vec![Some(actor.clone())],
        };
        // Admissions are aged by a fixed clock, never by how long PostgreSQL takes
        // (PQ-291).
        let fresh = || admission.issued;
        let old_drop = loot::decide_at(
            &mut c,
            &o,
            routed,
            pending_v2.claim,
            Some((&actor, &claim(&pending_v2), "demo")),
            Some((&loot_release.rules, &admission)),
            &fresh,
        )?;
        assert_eq!(old_drop.status, "claimed");
        assert_eq!(old_drop.recipient, 0); // The earned solo claim format is retained.
        let v3 = event(&mut c, &o, routed, id);
        settlements::settle(&mut c, &o, routed, &v3)?;
        // Past the window at either check the party-routed claim refuses.
        let late = crate::party_loot_tests::late(&admission);
        let reads = std::cell::Cell::new(0);
        for (first, read) in [(late, 1), (admission.issued, 2)] {
            reads.set(0);
            let stale = loot::decide_at(
                &mut c,
                &o,
                routed,
                v3.claim,
                Some((&actor, &claim(&v3), "demo")),
                Some((&loot_release.rules, &admission)),
                &crate::party_loot_tests::stepped(&reads, first, late),
            )?;
            assert_eq!((stale.status.as_str(), reads.get()), ("stale_admission", read));
        }
        let new_drop = loot::decide_at(
            &mut c,
            &o,
            routed,
            v3.claim,
            Some((&actor, &claim(&v3), "demo")),
            Some((&loot_release.rules, &admission)),
            &fresh,
        )?;
        assert_eq!(new_drop.status, "claimed");
        assert_eq!(new_drop.recipient, id as u64);
        assert_eq!(
            loot::decide_at(
                &mut c,
                &o,
                routed,
                v3.claim,
                Some((&actor, &claim(&v3), "demo")),
                Some((&loot_release.rules, &admission)),
                &fresh,
            )?,
            new_drop
        );
        c.execute("UPDATE characters SET online=false WHERE id=$1", &[&id])?;
        persistence::release(&mut c, &realm, &o.owner, o.generation)?;
        assert!(upgrade(&mut c, &o, &new, &next, "demo").is_err());
        // Competing destination definitions cannot both activate from one source.
        let race_realm = format!("{realm}-race");
        let race_generation = persistence::acquire(&mut c, &race_realm, "race")?;
        let race_owner = Owner {
            realm: race_realm.clone(),
            owner: "race".into(),
            generation: race_generation,
        };
        settlements::convert(&mut c, &race_owner, &old, "demo", 20)?;
        let jobs = [new.clone(), next.clone()]
            .into_iter()
            .map(|target| {
                let (url, o, source) = (url.clone(), race_owner.clone(), old.clone());
                std::thread::spawn(move || {
                    upgrade(
                        &mut persistence::connect(&url).unwrap(),
                        &o,
                        &source,
                        &target,
                        "demo",
                    )
                })
            })
            .collect::<Vec<_>>();
        assert_eq!(
            jobs.into_iter()
                .map(|job| job.join().unwrap().is_ok() as usize)
                .sum::<usize>(),
            1
        );
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM reward_policy_upgrades WHERE realm=$1",
                &[&race_realm]
            )?
            .get::<_, i64>(0),
            1
        );
        persistence::release(
            &mut c,
            &race_realm,
            &race_owner.owner,
            race_owner.generation,
        )?;
        println!(
            "PASS immutable reward upgrades preserve earned values/history and pending/claimed loot; active-session/definition/rollback/lease fences; new character initialization; three real process-crash points"
        );
        Ok(())
    }
}
