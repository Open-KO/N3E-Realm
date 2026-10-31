use crate::{
    accounts::{Owner, Selected},
    content::{Release, Result},
    party_loot_tests::{admission, claim, claim_at, frozen, late, next, release, selected, stepped},
    persistence, settlements, wire,
};
fn bundle(
    c: &mut postgres::Client,
    o: &Owner,
    r: &Release,
    ids: &[i64],
) -> Result<Vec<wire::Claim>> {
    let p = r.rules.progression.as_ref().unwrap();
    let mut s = frozen(c, o, r, ids);
    s.coins = Some(crate::drop_generation::Outcome {
        draw: 100,
        amount: p
            .coins
            .as_ref()
            .unwrap()
            .generation
            .amount(100, crate::drop_generation::eligible(&s))?,
    });
    let policy = p.items.as_ref().unwrap();
    let rolls = vec![
        crate::item_drops::Roll {
            chance: 1,
            group: Some(0),
        },
        crate::item_drops::Roll {
            chance: 1,
            group: None,
        },
        crate::item_drops::Roll {
            chance: 10000,
            group: None,
        },
    ];
    let entries = policy.replay(&rolls, p.npc_level, 1, false, true)?;
    s.items = Some(crate::item_drops::Outcome {
        player_level: 1,
        premium: false,
        rolls,
        entries,
    });
    settlements::settle(c, o, p, &s)?;
    settlements::settle(c, o, p, &s)?;
    let rows=c.query("SELECT claim_operation,item,quantity FROM loot_entitlements WHERE realm=$1 AND encounter=$2 ORDER BY claim_operation",&[&o.realm,&(s.encounter as i64)])?;
    assert_eq!(rows.len(), 3);
    Ok(rows
        .iter()
        .map(|row| wire::Claim {
            operation: row.get::<_, i64>(0) as u64,
            encounter: s.encounter,
            item: row.get(1),
            quantity: row.get::<_, i32>(2) as u32,
            ..Default::default()
        })
        .collect())
}
fn bag(c: &mut postgres::Client, o: &Owner, r: &Release, a: &Selected) -> Result<wire::BagState> {
    let mut t = c.transaction()?;
    let b = crate::inventory::load(
        &mut t,
        a,
        o,
        r.rules.inventory.as_ref().unwrap(),
        &r.rules.progression.as_ref().unwrap().item,
    )?;
    t.commit()?;
    Ok(b)
}
fn set_bag(c: &mut postgres::Client, a: &Selected, b: &wire::BagState) -> Result<()> {
    let mut t = c.transaction()?;
    crate::inventory::save(&mut t, a.id, b)?;
    t.commit()?;
    Ok(())
}
fn total(b: &wire::BagState, item: &str) -> u32 {
    b.slots
        .iter()
        .filter(|i| i.item == item)
        .map(|i| i.quantity)
        .sum()
}
#[test]
#[ignore = "subprocess of durable_contract"]
fn fault_worker() -> Result<()> {
    let mut c = persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
    let r = release();
    let realm = std::env::var("N3E_ITEM_REALM")?;
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
    let op: i64 = std::env::var("N3E_ITEM_OPERATION")?.parse()?;
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
/// Queue party claimants A and B and the expiry worker for one entitlement on
/// the realm fence before it expires, release them after, and return their
/// results in that order.
///
/// Every claimant keeps connect()'s production deadlines (800 ms lock wait,
/// 1000 ms statement) and decide_routed's 2 s claim deadline. Those are sized
/// for one durable worker per realm process (accounts::Database), while here
/// the claimants of a round queue on the one realm fence row together: the last
/// waits for the gate and every claim transaction ahead of it. The round keeps
/// that stack short. Its claimants and the gate connect before the window, the
/// gate is taken only GATE_LEAD before expiry and released by a rollback, which
/// waits for no WAL flush, and a round queues three claimants, not nine. Before
/// PQ-011 attempt 3 all nine claimants of three kinds queued at once behind a
/// gate taken 0.5 s before expiry while their backends were still starting, and
/// released by a commit; under parallel `make live` load the queue missed the
/// expiry or the last fence wait hit the statement timeout.
fn expiry_round(
    c: &mut postgres::Client,
    url: &str,
    o: &Owner,
    r: &Release,
    a: &Selected,
    b: &Selected,
    request: &wire::Claim,
) -> Result<Vec<wire::ClaimResult>> {
    const GATE_LEAD: f64 = 0.15;
    let op = request.operation as i64;
    let remaining = |c: &mut postgres::Client| -> Result<f64> {
        Ok(c.query_one("SELECT extract(epoch FROM expires_at-clock_timestamp())::float8 FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2", &[&o.realm, &op])?.get(0))
    };
    let mut blocker = persistence::connect(url)?;
    let (ready, waiting) = std::sync::mpsc::channel();
    let requesters = [Some(a.clone()), Some(b.clone()), None];
    let go = std::sync::Arc::new(std::sync::Barrier::new(requesters.len() + 1));
    let threads: Vec<_> = requesters
        .into_iter()
        .map(|requester| {
            let (url, o, r, request, a, b, ready, go) = (url.to_owned(), o.clone(), r.clone(), request.clone(), a.clone(), b.clone(), ready.clone(), go.clone());
            std::thread::spawn(move || {
                let mut c = persistence::connect(&url).unwrap();
                let pid: i32 = c.query_one("SELECT pg_backend_pid()", &[]).unwrap().get(0);
                ready.send(pid).unwrap();
                go.wait();
                // A party admission proof is fresh for 2 s; issue it at the gate.
                let proof = admission(&a, &b);
                let result = if let Some(actor) = requester {
                    claim(&mut c, &o, &r, &actor, &request, &proof).unwrap()
                } else {
                    crate::loot::decide(&mut c, &o, r.rules.progression.as_ref().unwrap(), request.operation, None).unwrap()
                };
                (result, std::time::Instant::now())
            })
        })
        .collect();
    let pids: Vec<i32> = (0..threads.len()).map(|_| waiting.recv_timeout(std::time::Duration::from_secs(10)).unwrap()).collect();
    let lead = remaining(c)? - GATE_LEAD;
    assert!(lead > 0.0, "round started after its gate window opened");
    std::thread::sleep(std::time::Duration::from_secs_f64(lead));
    let mut gate = blocker.transaction()?;
    gate.query_one("SELECT realm FROM realm_fence WHERE realm=$1 FOR UPDATE", &[&o.realm])?;
    let held = std::time::Instant::now();
    go.wait();
    loop {
        let locked: i64 = c.query_one("SELECT count(*) FROM unnest($1::int[]) p WHERE cardinality(pg_blocking_pids(p))>0", &[&pids])?.get(0);
        if locked == pids.len() as i64 {
            break;
        }
        assert!(remaining(c)? > 0.0, "all requests must be queued before expiry");
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
    let queued = held.elapsed();
    let left = remaining(c)?;
    assert!(left > 0.0, "all requests must be queued before expiry");
    std::thread::sleep(std::time::Duration::from_secs_f64(left + 0.05));
    // The gate changed nothing; a rollback releases the fence without a flush.
    gate.rollback()?;
    let released = std::time::Instant::now();
    let (results, finished): (Vec<_>, Vec<_>) = threads.into_iter().map(|t| t.join().unwrap()).unzip();
    println!(
        "expiry round {}: {} claimants queued {} ms after the gate, gate held {} ms, queue drained {} ms after release",
        request.operation,
        pids.len(),
        queued.as_millis(),
        released.duration_since(held).as_millis(),
        finished.iter().max().unwrap().duration_since(released).as_millis()
    );
    Ok(results)
}
#[test]
#[ignore = "tests/item_drops_db.py supplies disposable PostgreSQL"]
fn durable_contract() -> Result<()> {
    let url = std::env::var("N3E_TEST_DATABASE_URL")?;
    persistence::migrate(&url, persistence::MIGRATIONS)?;
    let mut c = persistence::connect(&url)?;
    let r = release();
    let p = r.rules.progression.as_ref().unwrap();
    let realm = format!("test-item-drops-{}", std::process::id());
    let generation = persistence::acquire(&mut c, &realm, "test")?;
    let o = Owner {
        realm: realm.clone(),
        owner: "test".into(),
        generation,
    };
    c.execute("UPDATE realm_ownership SET expires=clock_timestamp()+interval '120 seconds' WHERE realm=$1",&[&realm])?;
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
    let path = std::path::PathBuf::from(std::env::var("N3E_PACKAGE")?);
    let old = crate::content::load(&path.parent().unwrap().join("old/package"))?;
    settlements::convert(
        &mut c,
        &o,
        old.rules.progression.as_ref().unwrap(),
        &r.game,
        20,
    )?;
    let mut old_pending = frozen(&mut c, &o, &old, &ids);
    old_pending.coins = Some(crate::drop_generation::Outcome {
        draw: 100,
        amount: 1200,
    });
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
    let initial = [bag(&mut c, &o, &r, &a)?, bag(&mut c, &o, &r, &b)?];
    let stack = p.items.as_ref().unwrap().items[0].id.clone();
    let blade = p.items.as_ref().unwrap().items[1].id.clone();
    // Empty test bags let every later assertion measure the exact grant delta.
    let mut empty = initial[0].clone();
    for s in &mut empty.slots {
        *s = wire::ItemStack::default();
    }
    set_bag(&mut c, &a, &empty)?;
    set_bag(&mut c, &b, &empty)?;
    let q = bundle(&mut c, &o, &r, &ids)?;
    assert_eq!(
        claim(
            &mut c,
            &o,
            &r,
            &outsider,
            &q[0],
            &crate::party_loot::Admission {
                issued: std::time::Instant::now(),
                group: 0,
                slots: vec![Some(outsider.clone())]
            }
        )?
        .status,
        "unknown"
    );
    let mut wrong = q[0].clone();
    wrong.quantity += 1;
    assert_eq!(
        claim(&mut c, &o, &r, &a, &wrong, &admission(&a, &b))?.status,
        "conflict"
    );
    // Admissions are aged by a fixed clock (PQ-291). Past the window when the claim
    // starts, and fresh then but past it before the grant: both refuse, no item moves.
    let held = [bag(&mut c, &o, &r, &a)?, bag(&mut c, &o, &r, &b)?];
    let stale = admission(&a, &b);
    let reads = std::cell::Cell::new(0);
    assert_eq!(
        claim_at(&mut c, &o, &r, &a, &q[0], &stale, &stepped(&reads, late(&stale), late(&stale)))?.status,
        "stale_admission"
    );
    assert_eq!(reads.get(), 1);
    reads.set(0);
    assert_eq!(
        claim_at(&mut c, &o, &r, &a, &q[0], &stale, &stepped(&reads, stale.issued, late(&stale)))?.status,
        "stale_admission"
    );
    assert_eq!(reads.get(), 2);
    assert_eq!([bag(&mut c, &o, &r, &a)?, bag(&mut c, &o, &r, &b)?], held);
    let jobs: Vec<_> = [a.clone(), b.clone(), a.clone(), b.clone()]
        .into_iter()
        .map(|actor| {
            let (url, o, r, q, a, b) = (
                url.clone(),
                o.clone(),
                r.clone(),
                q[0].clone(),
                a.clone(),
                b.clone(),
            );
            std::thread::spawn(move || {
                let mut c = persistence::connect(&url).unwrap();
                claim(&mut c, &o, &r, &actor, &q, &admission(&a, &b)).unwrap()
            })
        })
        .collect();
    let results: Vec<_> = jobs.into_iter().map(|j| j.join().unwrap()).collect();
    assert!(results.iter().all(|x| x == &results[0]));
    assert_eq!(results[0].status, "claimed");
    let first = bag(&mut c, &o, &r, &a)?;
    assert_eq!(total(&first, &blade), 1);
    assert_eq!(total(&bag(&mut c, &o, &r, &b)?, &blade), 0);
    let sword = first.slots.iter().find(|i| i.item == blade).unwrap();
    assert_eq!(
        sword.durability,
        p.items.as_ref().unwrap().items[1].durability
    );
    assert!(sword.instance > 0);
    let second = claim(&mut c, &o, &r, &a, &q[1], &admission(&a, &b))?;
    assert_eq!(second.recipient, b.id as u64);
    assert_eq!(total(&bag(&mut c, &o, &r, &b)?, &stack), 20);
    assert_eq!(
        claim(&mut c, &o, &r, &b, &q[1], &admission(&a, &b))?,
        second
    );
    assert_eq!(
        claim(&mut c, &o, &r, &a, &q[2], &admission(&a, &b))?
            .coins
            .len(),
        2
    );
    // Fill every slot, then permit one whole stack in exactly one candidate.
    let mut full = empty.clone();
    for slot in &mut full.slots {
        *slot = wire::ItemStack {
            instance: next(&mut c),
            item: blade.clone(),
            quantity: 1,
            durability: p.items.as_ref().unwrap().items[1].durability,
        };
    }
    set_bag(&mut c, &a, &full)?;
    for slot in &mut full.slots {
        slot.instance = next(&mut c);
    }
    set_bag(&mut c, &b, &full)?;
    let q = bundle(&mut c, &o, &r, &ids)?;
    assert_eq!(
        claim(&mut c, &o, &r, &a, &q[1], &admission(&a, &b))?.status,
        "inventory_full_not_committed"
    );
    assert_eq!(
        c.query_one(
            "SELECT count(*) FROM loot_claim_results WHERE realm=$1 AND claim_operation=$2",
            &[&realm, &(q[1].operation as i64)]
        )?
        .get::<_, i64>(0),
        0
    );
    // A nearly-full stack cannot accept a partial reward. Empty slots take precedence.
    let limit = r
        .rules
        .inventory
        .as_ref()
        .unwrap()
        .items
        .iter()
        .find(|i| i.id == stack)
        .unwrap()
        .stack;
    full.slots[0] = wire::ItemStack {
        instance: next(&mut c),
        item: stack.clone(),
        quantity: limit - 1,
        durability: 0,
    };
    set_bag(&mut c, &b, &full)?;
    assert_eq!(
        claim(&mut c, &o, &r, &a, &q[1], &admission(&a, &b))?.status,
        "inventory_full_not_committed"
    );
    set_bag(&mut c, &b, &empty)?;
    let delivered = claim(&mut c, &o, &r, &a, &q[1], &admission(&a, &b))?;
    assert_eq!(delivered.recipient, b.id as u64);
    assert_eq!(total(&bag(&mut c, &o, &r, &b)?, &stack), 20);
    set_bag(&mut c, &a, &empty)?;
    set_bag(&mut c, &b, &empty)?;
    // Free slots are insufficient when the whole incoming stack exceeds weight.
    let inventory = r.rules.inventory.as_ref().unwrap();
    let commerce = r.rules.commerce.as_ref().unwrap();
    let carry = inventory
        .stats
        .as_ref()
        .unwrap()
        .calculate(inventory.equipment.as_ref().unwrap(), &empty.equipment, 1)?
        .carry_limit;
    let unit = commerce
        .items
        .iter()
        .find(|i| i.item == blade)
        .unwrap()
        .weight;
    let added = commerce
        .items
        .iter()
        .find(|i| i.item == stack)
        .unwrap()
        .weight
        * 20;
    let count = (carry - added) / unit + 1;
    assert!(count < empty.slots.len() as u32 && count * unit <= carry);
    let mut heavy = empty.clone();
    for slot in heavy.slots.iter_mut().take(count as usize) {
        *slot = wire::ItemStack {
            instance: next(&mut c),
            item: blade.clone(),
            quantity: 1,
            durability: p.items.as_ref().unwrap().items[1].durability,
        };
    }
    set_bag(&mut c, &a, &heavy)?;
    for slot in heavy.slots.iter_mut().filter(|s| s.instance > 0) {
        slot.instance = next(&mut c);
    }
    set_bag(&mut c, &b, &heavy)?;
    let weighted = bundle(&mut c, &o, &r, &ids)?;
    assert_eq!(
        claim(&mut c, &o, &r, &a, &weighted[1], &admission(&a, &b))?.status,
        "inventory_full_not_committed"
    );
    set_bag(&mut c, &b, &empty)?;
    assert_eq!(
        claim(&mut c, &o, &r, &a, &weighted[1], &admission(&a, &b))?.recipient,
        b.id as u64
    );
    set_bag(&mut c, &a, &empty)?;
    set_bag(&mut c, &b, &empty)?;
    // Trigger failure must roll back bag, serial ownership, cursor and entitlement.
    let q = bundle(&mut c, &o, &r, &ids)?;
    let before = [bag(&mut c, &o, &r, &a)?, bag(&mut c, &o, &r, &b)?];
    c.batch_execute("CREATE FUNCTION fail_item() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'rollback item'; END $$; CREATE TRIGGER fail_item BEFORE INSERT ON loot_claim_results FOR EACH ROW EXECUTE FUNCTION fail_item()")?;
    assert!(claim(&mut c, &o, &r, &a, &q[0], &admission(&a, &b)).is_err());
    assert_eq!([bag(&mut c, &o, &r, &a)?, bag(&mut c, &o, &r, &b)?], before);
    c.batch_execute("DROP TRIGGER fail_item ON loot_claim_results; DROP FUNCTION fail_item()")?;
    for point in [
        "before_mutation",
        "during_mutation",
        "before_commit",
        "after_commit",
    ] {
        set_bag(&mut c, &a, &empty)?;
        set_bag(&mut c, &b, &empty)?;
        let q = bundle(&mut c, &o, &r, &ids)?;
        let child = std::process::Command::new(std::env::current_exe()?)
            .args([
                "item_drop_tests::fault_worker",
                "--ignored",
                "--exact",
                "--nocapture",
            ])
            .env("N3E_ITEM_REALM", &realm)
            .env("N3E_ITEM_OPERATION", q[0].operation.to_string())
            .env("N3E_CLAIM_FAULT", point)
            .output()?;
        assert_eq!(
            child.status.code(),
            Some(86),
            "{}",
            String::from_utf8_lossy(&child.stderr)
        );
        assert_eq!(
            total(&bag(&mut c, &o, &r, &a)?, &blade) + total(&bag(&mut c, &o, &r, &b)?, &blade),
            u32::from(point == "after_commit")
        );
        let done = claim(&mut c, &o, &r, &a, &q[0], &admission(&a, &b))?;
        assert_eq!(done.status, "claimed");
        assert_eq!(claim(&mut c, &o, &r, &b, &q[0], &admission(&a, &b))?, done);
        assert_eq!(
            total(&bag(&mut c, &o, &r, &a)?, &blade) + total(&bag(&mut c, &o, &r, &b)?, &blade),
            1
        );
    }
    // New claims and old earned claims survive a preserving policy upgrade.
    c.execute(
        "UPDATE characters SET online=false WHERE realm=$1",
        &[&realm],
    )?;
    let next_release = crate::content::load(&path.parent().unwrap().join("next/package"))?;
    assert_eq!(
        crate::reward_upgrades::upgrade(&mut c, &o, &r, &next_release)?,
        2
    );
    c.execute(
        "UPDATE characters SET online=true WHERE realm=$1",
        &[&realm],
    )?;
    let old_q = wire::Claim {
        operation: old_pending.claim,
        encounter: old_pending.encounter,
        item: p.item.clone(),
        quantity: 1,
        ..Default::default()
    };
    assert_eq!(
        claim(&mut c, &o, &next_release, &a, &old_q, &admission(&a, &b))?.status,
        "claimed"
    );
    let boundary = bundle(&mut c, &o, &next_release, &ids)?;
    let radius = next_release.rules.progression.as_ref().unwrap().claim_radius;
    let mut at_edge = a.clone();
    at_edge.entity.y = radius;
    for q in &boundary {
        let mut outside = at_edge.clone();
        outside.entity.y += 0.01;
        assert_eq!(claim(&mut c, &o, &next_release, &outside, q, &admission(&outside, &b))?.status, "out_of_range");
        assert_eq!(claim(&mut c, &o, &next_release, &at_edge, q, &admission(&at_edge, &b))?.status, "claimed");
    }
    println!("PASS item and coin claims reject outside 3D range and accept the inclusive boundary");

    // Real database time, no modified timestamps or mocked clock. For each
    // item/coin kind, two party claimants and the expiry worker queue behind the
    // production realm fence before the entitlement expires and are processed
    // after it. Each round settles its own bundle just before it runs, so its
    // entitlement expires on its own and the round has the bundle's whole
    // lifetime to set up in (PQ-205): rounds settled ahead of time 3 s apart
    // left the first round only the lifetime minus every earlier settlement,
    // and a round started after its gate window opened once commits took up to
    // 1.7 s under parallel `make live` load (PQ-011 attempt 3; see expiry_round).
    let cursor = |c: &mut postgres::Client| -> Result<(i32, i64)> {
        let row = c.query_one("SELECT cursor,revision FROM party_loot_cursors WHERE realm=$1", &[&realm])?;
        Ok((row.get(0), row.get(1)))
    };
    // The policy upgrade above left the test's lease 30 s (reward_upgrades);
    // the three rounds wait out three bundle lifetimes, so extend it again as
    // at the start (this test owns the realm and runs no renewal).
    c.execute("UPDATE realm_ownership SET expires=clock_timestamp()+interval '120 seconds' WHERE realm=$1",&[&realm])?;
    for kind in 0..3 {
        let request = &bundle(&mut c, &o, &next_release, &ids)?.swap_remove(kind);
        let before = [bag(&mut c, &o, &next_release, &a)?, bag(&mut c, &o, &next_release, &b)?];
        let route = cursor(&mut c)?;
        let outcomes = expiry_round(&mut c, &url, &o, &next_release, &a, &b, request)?;
        assert_eq!(outcomes[0].status, "expired");
        assert!(outcomes.iter().all(|v| v == &outcomes[0]));
        assert_eq!(claim(&mut c, &o, &next_release, &b, request, &admission(&a, &b))?, outcomes[0]);
        assert_eq!(c.query_one("SELECT count(*) FROM loot_claim_results WHERE realm=$1 AND claim_operation=$2", &[&realm, &(request.operation as i64)])?.get::<_, i64>(0), 1);
        assert_eq!([bag(&mut c, &o, &next_release, &a)?, bag(&mut c, &o, &next_release, &b)?], before);
        assert_eq!(cursor(&mut c)?, route);
    }
    println!("PASS two party claimants plus expiry for each item/coin queued before deadline, processed after: one immutable expired result, no bag/wallet/cursor mutation");
    println!("PASS N3P5 frozen direct/group bundles, authorized whole-stack routing, concurrent duplicate claims, durability/serials, rollback, four process crashes, preserving upgrades and DB expiry");
    Ok(())
}
