use crate::{
    accounts::{Owner, Selected},
    content::Result,
    loot,
    party_loot::Admission,
    persistence,
    progression::{Ledger, Presence, Settlement},
    settlements, wire,
};
pub(super) fn release() -> crate::content::Release {
    crate::content::load(std::path::Path::new(&std::env::var("N3E_PACKAGE").unwrap())).unwrap()
}
pub(super) fn next(c: &mut postgres::Client) -> u64 {
    c.query_one("SELECT nextval('entity_instances')", &[])
        .unwrap()
        .get::<_, i64>(0) as u64
}
pub(super) fn selected(c: &mut postgres::Client, id: i64) -> Selected {
    let row = c
        .query_one(
            "SELECT name,session_generation,life_revision,dead FROM characters WHERE id=$1",
            &[&id],
        )
        .unwrap();
    Selected {
        id,
        generation: row.get(1),
        life_revision: row.get(2),
        dead: row.get(3),
        ready_ticks: 0,
        entity: wire::Entity {
            id: id as u64,
            name: row.get(0),
            health: 100,
            ..Default::default()
        },
    }
}
pub(super) fn admission(a: &Selected, b: &Selected) -> Admission {
    let mut slots = vec![None; 8];
    slots[0] = Some(a.clone());
    slots[7] = Some(b.clone());
    Admission {
        issued: std::time::Instant::now(),
        group: 2,
        slots,
    }
}
pub(super) fn frozen(
    c: &mut postgres::Client,
    o: &Owner,
    r: &crate::content::Release,
    ids: &[i64],
) -> Settlement {
    let p = r.rules.progression.as_ref().unwrap();
    let mut ledger = Ledger::default();
    ledger.credit(ids[0], 60, 100).unwrap();
    ledger.credit(ids[2], 40, 40).unwrap();
    let (recipients, parties) = ledger
        .freeze_parties(
            p,
            &r.game,
            [0.; 3],
            |_| {
                Some(Presence {
                    alive: true,
                    zone: r.game.clone(),
                    position: [0.; 3],
                    level: 1,
                })
            },
            |id| {
                if id == ids[2] {
                    None
                } else {
                    Some(crate::party_rewards::Group {
                        id: 2,
                        leader_level: 1,
                        members: ids[..2].to_vec(),
                        credited: vec![],
                    })
                }
            },
        )
        .unwrap();
    Settlement {
        npc: None,
        items: None, coins: None,
            loot_order: Some(ledger.order()),
        parties,
        encounter: next(c),
        generation: o.generation,
        release: vec![3; 32],
        definition: p.hash.clone(),
        zone: r.game.clone(),
        position: [0.; 3],
        tick: 1,
        claim: next(c),
        recipients,
    }
}
fn request(s: &Settlement, p: &crate::progression::Policy) -> wire::Claim {
    wire::Claim {
        operation: s.claim,
        encounter: s.encounter,
        item: p.item.clone(),
        quantity: 1,
        ..Default::default()
    }
}
/// A routed claim whose admission is aged by a fixed clock reading its own issue time,
/// so how long PostgreSQL takes never expires it (PQ-289, PQ-291). Expiry cases use
/// [`claim_at`].
pub(super) fn claim(
    c: &mut postgres::Client,
    o: &Owner,
    r: &crate::content::Release,
    s: &Selected,
    q: &wire::Claim,
    a: &Admission,
) -> Result<wire::ClaimResult> {
    claim_at(c, o, r, s, q, a, &|| a.issued)
}
pub(super) fn claim_at(
    c: &mut postgres::Client,
    o: &Owner,
    r: &crate::content::Release,
    s: &Selected,
    q: &wire::Claim,
    a: &Admission,
    now: &dyn Fn() -> std::time::Instant,
) -> Result<wire::ClaimResult> {
    loot::decide_at(
        c,
        o,
        r.rules.progression.as_ref().unwrap(),
        q.operation,
        Some((s, q, &r.game)),
        Some((&r.rules, a)),
        now,
    )
}
/// Just past the window. The claim checks compare the age as `f32` seconds, which cannot
/// tell 2 s + 1 ns from 2 s, so the step is 1 ms.
pub(super) fn late(a: &Admission) -> std::time::Instant {
    a.issued + crate::party_loot::ADMISSION_WINDOW + std::time::Duration::from_millis(1)
}
/// A clock that reads `first` once and `then` from the second read on, counting reads.
pub(super) fn stepped(
    reads: &std::cell::Cell<u32>,
    first: std::time::Instant,
    then: std::time::Instant,
) -> impl Fn() -> std::time::Instant + '_ {
    move || {
        reads.set(reads.get() + 1);
        if reads.get() == 1 {
            first
        } else {
            then
        }
    }
}
#[test]
#[ignore = "child process of durable_contract"]
fn fault_worker() -> Result<()> {
    let mut c = persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
    let r = release();
    let realm = std::env::var("N3E_PARTY_LOOT_REALM")?;
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
    let op: i64 = std::env::var("N3E_PARTY_LOOT_OPERATION")?.parse()?;
    let row = c.query_one(
        "SELECT encounter,item FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",
        &[&o.realm, &op],
    )?;
    let q = wire::Claim {
        operation: op as u64,
        encounter: row.get::<_, i64>(0) as u64,
        item: row.get(1),
        quantity: 1,
        ..Default::default()
    };
    claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?;
    Ok(())
}
#[test]
#[ignore = "tests/party_loot_db.py supplies isolated PostgreSQL"]
fn durable_contract() -> Result<()> {
    let url = std::env::var("N3E_TEST_DATABASE_URL")?;
    persistence::migrate(&url, persistence::MIGRATIONS)?;
    let mut c = persistence::connect(&url)?;
    let r = release();
    let p = r.rules.progression.as_ref().unwrap();
    let realm = format!("test-party-loot-{}", std::process::id());
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
    settlements::convert(&mut c, &o, p, &r.game, 20)?;
    c.execute("UPDATE characters SET online=true WHERE realm=$1",&[&realm])?;
    let a = selected(&mut c, ids[0]);
    let b = selected(&mut c, ids[1]);
    let outsider = selected(&mut c, ids[2]);
    let event = frozen(&mut c, &o, &r, &ids);
    settlements::settle(&mut c, &o, p, &event)?;
    let q = request(&event, p);
    assert_eq!(
        claim(
            &mut c,
            &o,
            &r,
            &outsider,
            &q,
            &Admission {
                issued: std::time::Instant::now(),
                group: 0,
                slots: vec![Some(outsider.clone())]
            }
        )?
        .status,
        "unknown"
    );
    assert_eq!(
        c.query_one(
            "SELECT count(*) FROM loot_audience WHERE realm=$1 AND claim_operation=$2",
            &[&realm, &(event.claim as i64)]
        )?
        .get::<_, i64>(0),
        2
    );
    let mut threads = vec![];
    for requester in [a.clone(), b.clone(), a.clone(), b.clone()] {
        let (url, o, r, q, a, b) = (
            url.clone(),
            o.clone(),
            r.clone(),
            q.clone(),
            a.clone(),
            b.clone(),
        );
        threads.push(std::thread::spawn(move || {
            claim(
                &mut persistence::connect(&url).unwrap(),
                &o,
                &r,
                &requester,
                &q,
                &admission(&a, &b),
            )
            .unwrap()
        }));
    }
    let first = threads.remove(0).join().unwrap();
    for t in threads {
        assert_eq!(t.join().unwrap(), first);
    }
    assert_eq!(first.recipient, a.id as u64);
    assert_eq!(first.recipient_name, "Leader");
    let counts = |c: &mut postgres::Client| {
        c.query(
            "SELECT count FROM character_progress WHERE character_id=ANY($1) ORDER BY character_id",
            &[&ids],
        )
        .unwrap()
        .iter()
        .map(|r| r.get::<_, i32>(0))
        .collect::<Vec<_>>()
    };
    let cursor = |c: &mut postgres::Client| {
        let row = c
            .query_one(
                "SELECT cursor,revision FROM party_loot_cursors WHERE realm=$1",
                &[&realm],
            )
            .unwrap();
        (row.get::<_, i32>(0), row.get::<_, i64>(1))
    };
    assert_eq!(counts(&mut c), vec![1, 0, 0]);
    assert_eq!(cursor(&mut c), (1, 1));
    let mut bad_q = q.clone();
    bad_q.quantity = 2;
    assert_eq!(
        claim(&mut c, &o, &r, &a, &bad_q, &admission(&a, &b))?.status,
        "conflict"
    );
    let event = frozen(&mut c, &o, &r, &ids);
    settlements::settle(&mut c, &o, p, &event)?;
    let q = request(&event, p);
    // Empty physical slots are skipped; the eighth slot receives the whole item.
    let second = claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?;
    assert_eq!(second.recipient, b.id as u64);
    assert_eq!(cursor(&mut c), (0, 2));
    assert_eq!(counts(&mut c), vec![1, 1, 0]);
    let event = frozen(&mut c, &o, &r, &ids);
    settlements::settle(&mut c, &o, p, &event)?;
    let q = request(&event, p);
    c.execute(
        "UPDATE character_progress SET count=capacity WHERE character_id=ANY($1)",
        &[&ids[..2].to_vec()],
    )?;
    let before = cursor(&mut c);
    assert_eq!(
        claim(&mut c, &o, &r, &a, &q, &admission(&a, &b))?.status,
        "inventory_full_not_committed"
    );
    assert_eq!(cursor(&mut c), before);
    assert_eq!(
        c.query_one(
            "SELECT state FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",
            &[&realm, &(event.claim as i64)]
        )?
        .get::<_, String>(0),
        "available"
    );
    c.execute(
        "UPDATE character_progress SET count=1 WHERE character_id=ANY($1)",
        &[&ids[..2].to_vec()],
    )?;
    c.execute("UPDATE character_progress SET count=capacity WHERE character_id=$1",&[&a.id])?;
    for kind in ["far","dead","session"] {
        let mut candidate=b.clone();
        match kind {"far"=>candidate.entity.x=51.,"dead"=>candidate.entity.health=0,_=>candidate.generation+=1};
        assert_eq!(claim(&mut c,&o,&r,&a,&q,&admission(&a,&candidate))?.status,"inventory_full_not_committed", "{kind}");
        assert_eq!(cursor(&mut c),before);
    }
    c.execute("UPDATE character_progress SET count=1 WHERE character_id=$1",&[&a.id])?;
    let mut stale_actor=a.clone();stale_actor.generation+=1;
    assert_eq!(claim(&mut c,&o,&r,&stale_actor,&q,&admission(&stale_actor,&b))?.status,"unknown");
    stale_actor=a.clone();stale_actor.life_revision+=1;
    assert_eq!(claim(&mut c,&o,&r,&stale_actor,&q,&admission(&stale_actor,&b))?.status,"not_alive");
    // Past the window when the claim starts, and fresh then but past it before the
    // claim mutates: both refuse with nothing routed, counted or claimed.
    let unclaimed = |c: &mut postgres::Client| -> Result<bool> {
        Ok(c.query_one(
            "SELECT state='available' AND NOT EXISTS(SELECT 1 FROM loot_claim_results WHERE realm=$1 AND claim_operation=$2) FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",
            &[&realm, &(q.operation as i64)],
        )?
        .get(0))
    };
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
    assert_eq!((counts(&mut c), cursor(&mut c)), (vec![1, 1, 0], before));
    assert!(unclaimed(&mut c)?);
    c.batch_execute("CREATE FUNCTION reject_party_loot_result() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test party loot rollback'; END $$; CREATE TRIGGER reject_party_loot_result BEFORE INSERT ON party_loot_claims FOR EACH ROW EXECUTE FUNCTION reject_party_loot_result()")?;
    assert!(claim(&mut c, &o, &r, &a, &q, &admission(&a, &b)).is_err());
    assert_eq!(counts(&mut c), vec![1, 1, 0]);
    assert_eq!(cursor(&mut c), before);
    c.batch_execute("DROP TRIGGER reject_party_loot_result ON party_loot_claims; DROP FUNCTION reject_party_loot_result()")?;
    for point in [
        "before_mutation",
        "during_mutation",
        "before_commit",
        "after_commit",
    ] {
        let event = frozen(&mut c, &o, &r, &ids);
        settlements::settle(&mut c, &o, p, &event)?;
        let q = request(&event, p);
        let old = counts(&mut c);
        let route = cursor(&mut c);
        let output = std::process::Command::new(std::env::current_exe()?)
            .args([
                "party_loot_tests::fault_worker",
                "--ignored",
                "--exact",
                "--nocapture",
            ])
            .env("N3E_PARTY_LOOT_REALM", &realm)
            .env("N3E_PARTY_LOOT_OPERATION", event.claim.to_string())
            .env("N3E_CLAIM_FAULT", point)
            .output()?;
        assert_eq!(output.status.code(), Some(86), "{:?}", output);
        if point != "after_commit" {
            assert_eq!(counts(&mut c), old);
            assert_eq!(cursor(&mut c), route);
        }
        // The window is inclusive: an admission exactly at its end still claims.
        let edge = admission(&a, &b);
        let result = claim_at(&mut c, &o, &r, &a, &q, &edge, &|| {
            edge.issued + crate::party_loot::ADMISSION_WINDOW
        })?;
        assert_eq!(result.status, "claimed");
        let expected = old
            .iter()
            .enumerate()
            .map(|(i, n)| {
                n + if ids[i] as u64 == result.recipient {
                    1
                } else {
                    0
                }
            })
            .collect::<Vec<_>>();
        assert_eq!(counts(&mut c), expected);
        assert_eq!(cursor(&mut c).1, route.1 + 1);
        assert_eq!(claim(&mut c, &o, &r, &b, &q, &admission(&a, &b))?, result);
    }
    if let Some(inventory)=&r.rules.inventory {
        let mut t=c.transaction()?;
        let mut originals=Vec::new();
        for s in [&a,&b] {
            let original=crate::inventory::load(&mut t,s,&o,inventory,&p.item)?;
            let mut full=original.clone();
            let filler=inventory.items.iter().find(|i|i.id.ends_with("/potion")).unwrap();
            for slot in full.slots.iter_mut().filter(|s|s.instance==0) {
                *slot=wire::ItemStack{instance:crate::inventory::serial(&mut t)?,item:filler.id.clone(),quantity:1,durability:filler.durability};
            }
            full.revision+=1;crate::inventory::save(&mut t,s.id,&full)?;originals.push((s.id,original));
        }
        t.commit()?;
        let event=frozen(&mut c,&o,&r,&ids);settlements::settle(&mut c,&o,p,&event)?;let q=request(&event,p);
        let before=cursor(&mut c);
        assert_eq!(claim(&mut c,&o,&r,&a,&q,&admission(&a,&b))?.status,"inventory_full_not_committed");assert_eq!(cursor(&mut c),before);
        let mut t=c.transaction()?;
        for (id,mut state) in originals {state.revision+=2;crate::inventory::save(&mut t,id,&state)?;}
        t.commit()?;
        let mut heavy=r.clone();
        std::sync::Arc::make_mut(heavy.rules.commerce.as_mut().unwrap()).items.iter_mut().find(|i|i.item==p.item).unwrap().weight=1_000_000;
        assert_eq!(claim(&mut c,&o,&heavy,&a,&q,&admission(&a,&b))?.status,"inventory_full_not_committed");assert_eq!(cursor(&mut c),before);
        assert_eq!(claim(&mut c,&o,&r,&a,&q,&admission(&a,&b))?.status,"claimed");
        let mut t=c.transaction()?;
        for s in [&a,&b] {
            let state=crate::inventory::load(&mut t,s,&o,inventory,&p.item)?;
            let tokens:u32=state.slots.iter().filter(|s|s.item==p.item).map(|s|s.quantity).sum();
            assert_eq!(tokens,t.query_one("SELECT count FROM character_progress WHERE character_id=$1",&[&s.id])?.get::<_,i32>(0) as u32);
        }
        t.commit()?;
        println!("PASS full item policy: real bag exhaustion, carrying rejection, retry after capacity recovery and atomic materialized token counts");
    }
    let mut event=frozen(&mut c,&o,&r,&ids);
    event.recipients.iter_mut().find(|r|r.id==a.id).unwrap().reason=2;
    let awards=crate::party_rewards::calculate(p,&event.recipients,event.parties.as_deref().unwrap())?;
    for (row,xp) in event.recipients.iter_mut().zip(awards) {row.xp=xp;}
    assert_eq!(event.owner(),Some(a.id));
    settlements::settle(&mut c,&o,p,&event)?;
    let mut dead=a.clone();dead.dead=true;dead.entity.health=0;
    let dead_owner=claim(&mut c,&o,&r,&b,&request(&event,p),&admission(&dead,&b))?;
    assert_eq!(dead_owner.recipient,b.id as u64);
    // Actual database clock expiry, using the fixture's validated ten-second TTL.
    assert_eq!(p.ttl,10,"use tests/party_loot_db.py for the bounded expiry fixture");
    let event=frozen(&mut c,&o,&r,&ids);settlements::settle(&mut c,&o,p,&event)?;
    let old=counts(&mut c);let route=cursor(&mut c);
    std::thread::sleep(std::time::Duration::from_secs(p.ttl as u64+1));
    let expired=claim(&mut c,&o,&r,&b,&request(&event,p),&admission(&a,&b))?;
    assert_eq!(expired.status,"expired");assert_eq!(counts(&mut c),old);assert_eq!(cursor(&mut c),route);
    assert_eq!(claim(&mut c,&o,&r,&a,&request(&event,p),&admission(&a,&b))?,expired);
    println!("PASS independently valid dead contributor ownership, live member delivery, actual database-clock expiry and immutable expired retry");
    for table in ["party_loot_claims", "loot_audience"] {
        assert!(
            c.execute(&format!("DELETE FROM {table} WHERE realm=$1"), &[&realm])
                .is_err()
        );
    }
    let mut stale_owner = o.clone();
    stale_owner.generation += 1;
    assert!(claim(&mut c, &stale_owner, &r, &a, &q, &admission(&a, &b)).is_err());
    println!(
        "PASS party loot audience, sparse eight-slot routing, concurrent exact retry, full-party retry, revision/cursor preservation, injected rollback, four process crash boundaries and immutable history"
    );
    Ok(())
}
