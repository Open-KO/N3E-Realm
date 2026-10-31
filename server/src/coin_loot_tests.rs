use crate::{
    accounts::Owner,
    content::Result,
    party_loot_tests::{admission, claim, claim_at, frozen, late, release, selected, stepped},
    persistence, settlements, wire,
};
use prost::Message;
fn drop(
    c: &mut postgres::Client,
    o: &Owner,
    r: &crate::content::Release,
    ids: &[i64],
) -> Result<wire::Claim> {
    let p = r.rules.progression.as_ref().unwrap();
    let mut s = frozen(c, o, r, ids);
    let draw = 100;
    let amount = p
        .coins
        .as_ref()
        .unwrap()
        .generation
        .amount(draw, crate::drop_generation::eligible(&s))?;
    s.coins = Some(crate::drop_generation::Outcome { draw, amount });
    settlements::settle(c, o, p, &s)?;
    settlements::settle(c, o, p, &s)?;
    let rows=c.query("SELECT claim_operation,item,quantity FROM loot_entitlements WHERE realm=$1 AND encounter=$2 AND kind=1",&[&o.realm,&(s.encounter as i64)])?;
    assert_eq!(rows.len(), 1);
    Ok(wire::Claim {
        operation: rows[0].get::<_, i64>(0) as u64,
        encounter: s.encounter,
        item: rows[0].get(1),
        quantity: rows[0].get::<_, i32>(2) as u32,
        ..Default::default()
    })
}
fn balance(c: &mut postgres::Client, id: i64) -> Result<wire::BagState> {
    Ok(wire::BagState::decode(
        c.query_one(
            "SELECT state FROM character_bags WHERE character_id=$1",
            &[&id],
        )?
        .get::<_, Vec<u8>>(0)
        .as_slice(),
    )?)
}
#[test]
#[ignore = "child process of durable_contract"]
fn fault_worker() -> Result<()> {
    let mut c = persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
    let r = release();
    let realm = std::env::var("N3E_COIN_REALM")?;
    let row = c.query_one(
        "SELECT owner,generation FROM realm_ownership WHERE realm=$1",
        &[&realm],
    )?;
    let o = Owner {
        realm,
        owner: row.get(0),
        generation: row.get(1),
    };
    let ids: Vec<i64> = c
        .query(
            "SELECT id FROM characters WHERE realm=$1 ORDER BY id",
            &[&o.realm],
        )?
        .iter()
        .map(|r| r.get(0))
        .collect();
    let a = selected(&mut c, ids[0]);
    let b = selected(&mut c, ids[1]);
    let op: i64 = std::env::var("N3E_COIN_OPERATION")?.parse()?;
    let row=c.query_one("SELECT encounter,item,quantity FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])?;
    let q = wire::Claim {
        operation: op as u64,
        encounter: row.get::<_, i64>(0) as u64,
        item: row.get(1),
        quantity: row.get::<_, i32>(2) as u32,
        ..Default::default()
    };
    claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?;
    Ok(())
}
#[test]
#[ignore = "tests/coin_loot_db.py supplies disposable PostgreSQL"]
fn durable_contract() -> Result<()> {
    let url = std::env::var("N3E_TEST_DATABASE_URL")?;
    persistence::migrate(&url, persistence::MIGRATIONS)?;
    let mut c = persistence::connect(&url)?;
    let r = release();
    let p = r.rules.progression.as_ref().unwrap();
    assert_eq!(
        crate::progression::Policy::decode(p.encode()?)?.hash,
        p.hash
    );
    let realm = format!("test-coin-loot-{}", std::process::id());
    let generation = persistence::acquire(&mut c, &realm, "test")?;
    let o = Owner {
        realm: realm.clone(),
        owner: "test".into(),
        generation,
    };
    c.execute(
        "UPDATE realm_ownership SET expires=clock_timestamp()+interval '60 seconds' WHERE realm=$1",
        &[&realm],
    )?;
    let account: i64 = c
        .query_one(
            "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
            &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
        )?
        .get(0);
    let mut ids = vec![];
    for name in ["Leader", "Member", "Outsider"] {
        ids.push(c.query_one("INSERT INTO characters(account_id,realm,name,online,session_generation,realm_generation) VALUES($1,$2,$3,false,1,$4) RETURNING id",&[&account,&realm,&name,&generation])?.get::<_,i64>(0));
    }
    let fixture = std::path::PathBuf::from(std::env::var("N3E_PACKAGE")?);
    let old = crate::content::load(&fixture.parent().unwrap().join("old/package"))?;
    settlements::convert(
        &mut c,
        &o,
        old.rules.progression.as_ref().unwrap(),
        &r.game,
        20,
    )?;
    let old_pending = frozen(&mut c, &o, &old, &ids);
    settlements::settle(
        &mut c,
        &o,
        old.rules.progression.as_ref().unwrap(),
        &old_pending,
    )?;
    assert_eq!(crate::reward_upgrades::upgrade(&mut c, &o, &old, &r)?, 1);
    assert_eq!(crate::reward_upgrades::upgrade(&mut c, &o, &old, &r)?, 1);
    c.execute(
        "UPDATE characters SET online=true WHERE realm=$1",
        &[&realm],
    )?;
    let a = selected(&mut c, ids[0]);
    let b = selected(&mut c, ids[1]);
    let outsider = selected(&mut c, ids[2]);
    let old_request = wire::Claim {
        operation: old_pending.claim,
        encounter: old_pending.encounter,
        item: p.item.clone(),
        quantity: 1,
        ..Default::default()
    };
    let old_result = claim(&mut c, &o, &r, &a, &old_request, &admission(&a, &b))?;
    assert_eq!(old_result.status, "claimed");
    assert!(old_result.coins.is_empty());
    let q = drop(&mut c, &o, &r, &ids)?;
    assert_eq!(q.quantity, 1200);
    let denied = claim(
        &mut c,
        &o,
        &r,
        &outsider,
        &q,
        &crate::party_loot::Admission {
            issued: std::time::Instant::now(),
            group: 0,
            slots: vec![Some(outsider.clone())],
        },
    )?;
    assert_eq!(denied.status, "unknown");
    let mut wrong = q.clone();
    wrong.quantity -= 1;
    assert_eq!(
        claim(&mut c, &o, &r, &a, &wrong, &admission(&a, &b))?.status,
        "conflict"
    );
    let threads: Vec<_> = [a.clone(), b.clone(), a.clone(), b.clone()]
        .into_iter()
        .map(|actor| {
            let (url, o, r, q, a, b) = (
                url.clone(),
                o.clone(),
                r.clone(),
                q.clone(),
                a.clone(),
                b.clone(),
            );
            std::thread::spawn(move || {
                let mut c = persistence::connect(&url).unwrap();
                claim(&mut c, &o, &r, &actor, &q, &admission(&a, &b)).unwrap()
            })
        })
        .collect();
    let outcomes: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    assert!(outcomes.iter().all(|v| v == &outcomes[0]));
    let first = &outcomes[0];
    assert_eq!(first.status, "claimed");
    assert_eq!(first.coins.len(), 2);
    for v in &first.coins {
        assert_eq!(v.nominal, 600);
        assert_eq!(v.added, 600);
        assert_eq!(v.balance, r.rules.inventory.as_ref().unwrap().coins + 600);
    }
    assert_eq!(
        c.query_one(
            "SELECT coalesce(sum(revision),0)::bigint FROM party_loot_cursors WHERE realm=$1",
            &[&realm]
        )?
        .get::<_, i64>(0),
        1
    );
    assert_eq!(claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?, *first);
    // A newly joined recipient can recover its own committed result, without
    // gaining permission to initiate pickup of the previously private drop.
    let changed_party_drop = drop(&mut c, &o, &r, &ids)?;
    let changed_party = claim(
        &mut c,
        &o,
        &r,
        &a,
        &changed_party_drop,
        &admission(&a, &outsider),
    )?;
    assert!(
        changed_party
            .coins
            .iter()
            .any(|v| v.character == outsider.id as u64)
    );
    let mut t = c.transaction()?;
    assert_eq!(
        crate::loot::stored(&mut t, &o, outsider.id, changed_party_drop.operation as i64)?,
        changed_party
    );
    t.rollback()?;
    assert_eq!(
        claim(
            &mut c,
            &o,
            &r,
            &outsider,
            &changed_party_drop,
            &admission(&a, &outsider)
        )?
        .status,
        "unknown"
    );
    let q = drop(&mut c, &o, &r, &ids)?;
    let before = [balance(&mut c, a.id)?, balance(&mut c, b.id)?];
    // Past the window when the claim starts, and fresh then but past it before the
    // wallets change: both refuse with no wallet touched and the drop still available.
    let stale = admission(&a, &b);
    let reads = std::cell::Cell::new(0);
    assert_eq!(
        claim_at(&mut c, &o, &r, &a, &q, &stale, &stepped(&reads, late(&stale), late(&stale)))?.status,
        "stale_admission"
    );
    assert_eq!(reads.get(), 1);
    reads.set(0);
    assert_eq!(
        claim_at(&mut c, &o, &r, &a, &q, &stale, &stepped(&reads, stale.issued, late(&stale)))?.status,
        "stale_admission"
    );
    assert_eq!(reads.get(), 2);
    assert_eq!([balance(&mut c, a.id)?, balance(&mut c, b.id)?], before);
    assert_eq!(
        c.query_one(
            "SELECT state FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",
            &[&realm, &(q.operation as i64)],
        )?
        .get::<_, String>(0),
        "available"
    );
    let mut changed_life = a.clone();
    changed_life.life_revision += 1;
    assert_eq!(
        claim(
            &mut c,
            &o,
            &r,
            &changed_life,
            &q,
            &admission(&changed_life, &b)
        )?
        .status,
        "not_alive"
    );
    let mut distant = a.clone();
    distant.entity.x = 20.;
    assert_eq!(
        claim(&mut c, &o, &r, &distant, &q, &admission(&distant, &b))?.status,
        "out_of_range"
    );
    assert_eq!([balance(&mut c, a.id)?, balance(&mut c, b.id)?], before);
    c.batch_execute("CREATE FUNCTION fail_coin() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'rollback all wallets'; END $$; CREATE TRIGGER fail_coin BEFORE INSERT ON coin_claim_recipients FOR EACH ROW EXECUTE FUNCTION fail_coin()")?;
    assert!(claim(&mut c, &o, &r, &a, &q, &admission(&a, &b)).is_err());
    assert_eq!([balance(&mut c, a.id)?, balance(&mut c, b.id)?], before);
    c.batch_execute("DROP TRIGGER fail_coin ON coin_claim_recipients; DROP FUNCTION fail_coin()")?;
    // Skipping a dead/far member changes the live recipient set, never the frozen drop amount.
    let mut far = b.clone();
    far.entity.x = 51.;
    // The window is inclusive: an admission exactly at its end still claims.
    let edge = admission(&a, &far);
    let v = claim_at(&mut c, &o, &r, &a, &q, &edge, &|| {
        edge.issued + crate::party_loot::ADMISSION_WINDOW
    })?;
    assert_eq!(v.status, "claimed");
    assert_eq!(v.coins.len(), 1);
    assert_eq!(v.coins[0].added, 1200);
    assert_eq!(balance(&mut c, b.id)?, before[1]);
    for point in [
        "before_mutation",
        "during_mutation",
        "before_commit",
        "after_commit",
    ] {
        let q = drop(&mut c, &o, &r, &ids)?;
        let before = [balance(&mut c, a.id)?.coins, balance(&mut c, b.id)?.coins];
        let child = std::process::Command::new(std::env::current_exe()?)
            .args([
                "coin_loot_tests::fault_worker",
                "--ignored",
                "--exact",
                "--nocapture",
            ])
            .env("N3E_COIN_REALM", &realm)
            .env("N3E_COIN_OPERATION", q.operation.to_string())
            .env("N3E_CLAIM_FAULT", point)
            .output()?;
        assert_eq!(
            child.status.code(),
            Some(86),
            "{}",
            String::from_utf8_lossy(&child.stderr)
        );
        for (i, id) in [a.id, b.id].iter().enumerate() {
            assert_eq!(
                balance(&mut c, *id)?.coins,
                before[i] + if point == "after_commit" { 600 } else { 0 }
            );
        }
        let done = claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?;
        assert_eq!(done.coins.len(), 2);
        assert_eq!(claim(&mut c, &o, &r, &b, &q, &admission(&a, &b))?, done);
        for (i, id) in [a.id, b.id].iter().enumerate() {
            assert_eq!(balance(&mut c, *id)?.coins, before[i] + 600);
        }
    }
    let q = drop(&mut c, &o, &r, &ids)?;
    let mut t = c.transaction()?;
    let mut bag =
        crate::inventory::load(&mut t, &a, &o, r.rules.inventory.as_ref().unwrap(), &p.item)?;
    bag.coins = r.rules.inventory.as_ref().unwrap().limit - 5;
    crate::inventory::save(&mut t, a.id, &bag)?;
    t.commit()?;
    let done = claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?;
    assert_eq!(done.coins[0].added, 5);
    assert_eq!(done.coins[0].nominal, 600);
    assert!(
        c.execute(
            "UPDATE coin_claim_recipients SET added=0 WHERE realm=$1",
            &[&realm]
        )
        .is_err()
    );
    let bag_policy = r.rules.inventory.as_ref().unwrap();
    let filler = bag_policy.items.iter().find(|i| i.id != p.item).unwrap();
    let mut t = c.transaction()?;
    for actor in [&a, &b] {
        let mut bag = crate::inventory::load(&mut t, actor, &o, bag_policy, &p.item)?;
        for slot in &mut bag.slots {
            if slot.instance == 0 {
                *slot = wire::ItemStack {
                    instance: crate::inventory::serial(&mut t)?,
                    item: filler.id.clone(),
                    quantity: 1,
                    durability: filler.durability,
                };
            }
        }
        bag_policy.validate(&bag)?;
        crate::inventory::save(&mut t, actor.id, &bag)?;
    }
    t.commit()?;
    let full_bags_drop = drop(&mut c, &o, &r, &ids)?;
    let full_bags = claim(&mut c, &o, &r, &a, &full_bags_drop, &admission(&a, &b))?;
    assert_eq!(full_bags.status, "claimed");
    assert_eq!(full_bags.coins.len(), 2);
    assert_eq!(full_bags.coins[1].added, 600);
    let q = drop(&mut c, &o, &r, &ids)?;
    let before = [balance(&mut c, a.id)?, balance(&mut c, b.id)?];
    assert_eq!(p.ttl, 10);
    std::thread::sleep(std::time::Duration::from_secs(11));
    let expired = crate::loot::decide(&mut c, &o, p, q.operation, None)?;
    assert_eq!(expired.status, "expired");
    assert!(expired.coins.is_empty());
    assert_eq!([balance(&mut c, a.id)?, balance(&mut c, b.id)?], before);
    assert_eq!(claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?, expired);
    // A subsequent generation change cannot reroll an already-earned coin amount.
    let pending = drop(&mut c, &o, &r, &ids)?;
    let next_release = crate::content::load(&fixture.parent().unwrap().join("next/package"))?;
    c.execute(
        "UPDATE characters SET online=false WHERE realm=$1",
        &[&realm],
    )?;
    let saved = [balance(&mut c, a.id)?, balance(&mut c, b.id)?];
    assert_eq!(
        crate::reward_upgrades::upgrade(&mut c, &o, &r, &next_release)?,
        2
    );
    assert_eq!([balance(&mut c, a.id)?, balance(&mut c, b.id)?], saved);
    assert!(crate::reward_upgrades::upgrade(&mut c, &o, &next_release, &old).is_err());
    c.execute(
        "UPDATE characters SET online=true WHERE realm=$1",
        &[&realm],
    )?;
    let earned = claim(&mut c, &o, &next_release, &a, &pending, &admission(&a, &b))?;
    assert_eq!(earned.coins.iter().map(|v| v.nominal).sum::<u32>(), 1200);
    assert_eq!(
        claim(&mut c, &o, &next_release, &a, &pending, &admission(&a, &b))?,
        earned
    );
    let new_drop = drop(&mut c, &o, &next_release, &ids)?;
    assert_eq!(new_drop.quantity, 1201);
    println!(
        "PASS frozen generated amounts, atomic concurrent party wallets, outsider/quantity rejection, full-wallet saturation, immutable retry, rollback, four real process crashes and database-clock expiry"
    );
    Ok(())
}
