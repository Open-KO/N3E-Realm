//! Durable owner-exclusive one-item C/E operations. All SQL runs on the DB worker.
use crate::{
    accounts::{Database, Owner, Selected},
    content::{bad, Result},
    persistence,
    progression::Policy,
    rules::Rules,
    wire,
};
use std::sync::Arc;

fn identity(v: u64) -> Result<i64> {
    if v == 0 || v > i64::MAX as u64 {
        Err(bad("loot identity"))
    } else {
        Ok(v as i64)
    }
}
pub fn canonical(
    operation: u64,
    encounter: u64,
    owner: i64,
    item: &str,
    quantity: u32,
) -> Result<Vec<u8>> {
    identity(operation)?;
    identity(encounter)?;
    if owner <= 0 || item.is_empty() || item.len() > 128 || quantity != 1 {
        return Err(bad("claim payload"));
    }
    let mut b = b"N3C1".to_vec();
    for v in [operation, encounter, owner as u64] {
        b.extend(v.to_le_bytes());
    }
    b.extend((item.len() as u32).to_le_bytes());
    b.extend(item.as_bytes());
    b.extend(quantity.to_le_bytes());
    Ok(b)
}
pub(crate) fn session(t: &mut postgres::Transaction<'_>, s: &Selected, o: &Owner) -> Result<bool> {
    Ok(t.query_opt("SELECT id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online", &[&s.id,&o.realm,&s.generation,&o.generation])?.is_some())
}
pub(crate) fn stored(
    t: &mut postgres::Transaction<'_>,
    o: &Owner,
    owner: i64,
    operation: i64,
) -> Result<wire::ClaimResult> {
    Ok(match t.query_opt("SELECT r.status,r.result_count,r.revision,coalesce(g.recipient,0),coalesce(g.recipient_name,'') FROM loot_claim_results r LEFT JOIN party_loot_claims g USING(realm,claim_operation) WHERE r.realm=$1 AND r.claim_operation=$2 AND (r.owner=$3 OR g.recipient=$3 OR EXISTS(SELECT 1 FROM coin_claim_recipients c WHERE c.realm=r.realm AND c.claim_operation=r.claim_operation AND c.character_id=$3) OR EXISTS(SELECT 1 FROM loot_audience a WHERE a.realm=r.realm AND a.claim_operation=r.claim_operation AND a.character_id=$3))", &[&o.realm,&operation,&owner])? {
        Some(r) => wire::ClaimResult{operation:operation as u64,status:r.get(0),count:r.get::<_,i32>(1) as u32,revision:r.get::<_,i64>(2) as u64,recipient:r.get::<_,i64>(3) as u64,recipient_name:r.get(4),coins:crate::coin_loot::stored(t,o,operation)?},
        None => response(operation as u64,"unknown")
    })
}
pub fn response(operation: u64, status: &str) -> wire::ClaimResult {
    wire::ClaimResult {
        operation,
        status: status.into(),
        ..Default::default()
    }
}
pub fn fault(point: &str) {
    if std::env::var("N3E_CLAIM_FAULT").as_deref() == Ok(point) {
        eprintln!("claim fault {point}");
        std::process::exit(86);
    }
}

// Frozen ordered-admission position, life and session are proofs, never semantic identity.
// Expiry supplies no session; both paths lock in S's realm/policy/character/progress order.
pub fn decide(
    c: &mut postgres::Client,
    o: &Owner,
    p: &Policy,
    operation: u64,
    admission: Option<(&Selected, &wire::Claim, &str)>,
) -> Result<wire::ClaimResult> {
    decide_routed(c,o,p,operation,admission,None)
}
pub(crate) fn decide_routed(
    c: &mut postgres::Client, o: &Owner, p: &Policy, operation:u64,
    admission:Option<(&Selected,&wire::Claim,&str)>, routing:Option<(&Rules,&crate::party_loot::Admission)>,
) -> Result<wire::ClaimResult> {
    decide_at(c,o,p,operation,admission,routing,&std::time::Instant::now)
}
/// `decide_routed` with the clock that ages a routed claim's party admission
/// (`party_loot::ADMISSION_WINDOW`), read by the coin and party claim checks. Production
/// passes `Instant::now`; tests pass a fixed clock so the window, not database speed,
/// decides fresh and expired (PQ-291). The worker deadline below stays on the wall clock.
pub(crate) fn decide_at(
    c: &mut postgres::Client, o: &Owner, p: &Policy, operation:u64,
    admission:Option<(&Selected,&wire::Claim,&str)>, routing:Option<(&Rules,&crate::party_loot::Admission)>,
    now: &dyn Fn() -> std::time::Instant,
) -> Result<wire::ClaimResult> {
    let start = std::time::Instant::now();
    for attempt in 0..=3 {
        let remaining = 2000u64.saturating_sub(start.elapsed().as_millis() as u64);
        if remaining == 0 {
            return Err(bad("claim worker deadline"));
        }
        match once(c, o, p, operation, admission, remaining, routing, now) {
            Ok(v) => return Ok(v),
            Err(e) => {
                let rollback = persistence::retryable(e.as_ref());
                let delay = 50u64 << attempt;
                if !rollback || attempt == 3 || start.elapsed().as_millis() as u64 + delay >= 2000 {
                    return Err(e);
                }
                std::thread::sleep(std::time::Duration::from_millis(delay));
            }
        }
    }
    unreachable!()
}
#[allow(clippy::too_many_arguments)]
fn once(
    c: &mut postgres::Client,
    o: &Owner,
    p: &Policy,
    operation: u64,
    admission: Option<(&Selected, &wire::Claim, &str)>,
    remaining: u64,
    routing: Option<(&Rules,&crate::party_loot::Admission)>,
    now: &dyn Fn() -> std::time::Instant,
) -> Result<wire::ClaimResult> {
    let op = identity(operation)?;
    let mut t = c.transaction()?;
    t.query_one(
        "SELECT set_config('transaction_timeout',$1,true)",
        &[&format!("{remaining}ms")],
    )?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    crate::settlements::policy(&mut t, o, p)?;
    // Immutable identity read is safe before locks; the realm lock serializes all C/E writers.
    let Some(drop)=t.query_opt("SELECT owner,encounter,item,quantity,definition,x,y,z,zone,kind FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])? else {return Ok(response(operation,"unknown"));};
    let owner: i64 = drop.get(0);
    let encounter: i64 = drop.get(1);
    let item: String = drop.get(2);
    let earned=crate::reward_upgrades::earned_policy(&mut t,&o.realm,p,&drop.get::<_,Vec<u8>>(4))?;
    if drop.get::<_,i32>(9)==1 {
        let result=crate::coin_loot::claim(&mut t,o,p,&earned,operation,admission,routing,now)?;
        persistence::fence(&mut t,&o.realm,&o.owner,o.generation)?;
        fault("before_commit");t.commit()?;fault("after_commit");return Ok(result);
    }
    if drop.get::<_,i32>(9)==2 && admission.is_none() {
        let result=crate::item_drops::expire(&mut t,o,op)?;
        persistence::fence(&mut t,&o.realm,&o.owner,o.generation)?;
        fault("before_commit");t.commit()?;fault("after_commit");return Ok(result);
    }
    if earned.party_loot.is_some() {
        if let Some((s,a,zone))=admission {
            let (rules,routing)=routing.ok_or_else(||bad("missing party loot admission"))?;
            let result=crate::party_loot::claim(&mut t,o,rules,p,&earned,s,a,zone,routing,now)?;
            persistence::fence(&mut t,&o.realm,&o.owner,o.generation)?;
            fault("before_commit");t.commit()?;fault("after_commit");return Ok(result);
        }
    }
    if let Some((s, _, _)) = admission {
        if s.id != owner || !session(&mut t, s, o)? {
            return Ok(response(operation, "unknown"));
        }
    }
    let actor=t.query_one("SELECT life_revision,dead,session_generation,realm_generation,online FROM characters WHERE id=$1 AND realm=$2 FOR UPDATE",&[&owner,&o.realm])?;
    let progress=t.query_one("SELECT p.count,p.capacity,p.item,r.revision,r.definition FROM character_progress p JOIN character_reward_progress r USING(character_id) WHERE p.character_id=$1 AND r.realm=$2 FOR UPDATE OF p,r",&[&owner,&o.realm])?;
    if progress.get::<_, Vec<u8>>(4) != p.hash
        || item != p.item
        || progress.get::<_, String>(2) != p.item
        || progress.get::<_, i32>(1) != p.capacity as i32
    {
        return Err(bad("claim definition conflict"));
    }
    t.query_one(
        "SELECT encounter FROM encounter_settlements WHERE realm=$1 AND encounter=$2 FOR UPDATE",
        &[&o.realm, &encounter],
    )?;
    let entitlement=t.query_one("SELECT state,revision FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2 FOR UPDATE",&[&o.realm,&op])?;
    let payload = canonical(operation, encounter as u64, owner, &item, 1)?;
    if let Some((_, a, _)) = admission {
        if a.operation != operation
            || canonical(a.operation, a.encounter, owner, &a.item, a.quantity)
                .ok()
                .as_ref()
                != Some(&payload)
        {
            return Ok(response(operation, "conflict"));
        }
    }
    if entitlement.get::<_, String>(0) != "available" {
        let history=t.query_one("SELECT payload,digest FROM loot_claim_results WHERE realm=$1 AND claim_operation=$2 FOR UPDATE",&[&o.realm,&op])?;
        if history.get::<_, Vec<u8>>(0) != payload
            || history.get::<_, Vec<u8>>(1) != openssl::sha::sha256(&payload)
        {
            return Err(bad("claim history payload conflict"));
        }
        return stored(&mut t, o, owner, op);
    }
    if let Some((s, _, zone)) = admission {
        if actor.get::<_, i64>(2) != s.generation
            || actor.get::<_, i64>(3) != o.generation
            || !actor.get::<_, bool>(4)
        {
            return Ok(response(operation, "stale_session"));
        }
        if s.entity.health == 0
            || s.dead
            || actor.get::<_, bool>(1)
            || actor.get::<_, i64>(0) != s.life_revision
        {
            return Ok(response(operation, "not_alive"));
        }
        let position = [s.entity.x, s.entity.y, s.entity.z];
        let distance: f64 = position
            .iter()
            .enumerate()
            .map(|(i, x)| (*x as f64 - drop.get::<_, f32>(5 + i) as f64).powi(2))
            .sum();
        if drop.get::<_, String>(8) != zone
            || !distance.is_finite()
            || distance > (earned.claim_radius as f64).powi(2)
        {
            return Ok(response(operation, "out_of_range"));
        }
    }
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    // Final locked database-clock decision: equality belongs to expiry.
    let expired:bool=t.query_one("SELECT clock_timestamp()>=expires_at FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])?.get(0);
    if !expired && admission.is_none() {
        return Ok(response(operation, "available"));
    }
    let count: i32 = progress.get(0);
    let revision: i64 = progress.get(3);
    if !expired && count >= progress.get::<_, i32>(1) {
        return Ok(response(operation, "inventory_full_not_committed"));
    }
    let status = if expired { "expired" } else { "claimed" };
    let next_count = count + if expired { 0 } else { 1 };
    let next_revision = revision
        .checked_add(if expired { 0 } else { 1 })
        .ok_or_else(|| bad("claim revision overflow"))?;
    let entitlement_revision = entitlement
        .get::<_, i64>(1)
        .checked_add(1)
        .ok_or_else(|| bad("entitlement revision overflow"))?;
    if !expired && !crate::inventory::grant_existing(&mut t, &o.realm, owner, &item)? {
        return Ok(response(operation, "inventory_full_not_committed"));
    }
    fault("before_mutation");
    if !expired {
        t.execute(
            "UPDATE character_progress SET count=$2 WHERE character_id=$1",
            &[&owner, &next_count],
        )?;
        t.execute(
            "UPDATE character_reward_progress SET revision=$2 WHERE character_id=$1",
            &[&owner, &next_revision],
        )?;
    }
    fault("during_mutation");
    t.execute("INSERT INTO loot_claim_results(realm,claim_operation,encounter,owner,payload,digest,status,result_count,revision) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",&[&o.realm,&op,&encounter,&owner,&payload,&&openssl::sha::sha256(&payload)[..],&status,&next_count,&next_revision])?;
    t.execute("UPDATE loot_entitlements SET state=$3,revision=$4,result_operation=claim_operation WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op,&status,&entitlement_revision])?;
    fault("before_commit");
    t.commit()?;
    fault("after_commit");
    Ok(wire::ClaimResult {
        operation,
        status: status.into(),
        count: next_count as u32,
        revision: next_revision as u64,
        ..Default::default()
    })
}
impl Database {
    pub async fn claim(
        &self,
        o: Arc<Owner>,
        r: Rules,
        s: Selected,
        a: wire::Claim,
        zone: String,
        routing: Option<crate::party_loot::Admission>,
    ) -> Result<(wire::ClaimResult, Vec<(i64,wire::Inventory,Option<wire::BagState>)>)> {
        self.call(move |c| {
            let result = decide_routed(
                c,
                &o,
                r.progression
                    .as_ref()
                    .ok_or_else(|| bad("claim unsupported"))?,
                a.operation,
                Some((&s, &a, &zone)),
                routing.as_ref().map(|v|(&r,v)),
            )?;
            let mut t = c.transaction()?;
            // Reading current bags can lazily materialize a legacy inventory.
            // Keep that write under the same realm ownership fence as the claim.
            persistence::fence(&mut t,&o.realm,&o.owner,o.generation)?;
            let mut recipients=std::collections::BTreeSet::from([s.id]);
            if result.recipient>0 {recipients.insert(result.recipient as i64);}
            recipients.extend(result.coins.iter().map(|v|v.character as i64));
            let mut inventories=Vec::new();
            for id in recipients {
                let inventory=crate::rewards::inventory(&mut t,id,&r)?;
                let bag=if let Some(p)=&r.inventory {
                    let mut selected=s.clone();selected.id=id;
                    Some(crate::inventory::load(&mut t,&selected,&o,p,&r.item)?)
                }else{None};
                inventories.push((id,inventory,bag));
            }
            t.commit()?;
            Ok((result, inventories))
        })
        .await
    }
    pub async fn claim_status(
        &self,
        o: Arc<Owner>,
        s: Selected,
        operation: u64,
    ) -> Result<wire::ClaimResult> {
        let op = identity(operation)?;
        self.call(move |c| {
            let mut t = c.transaction()?;
            if !session(&mut t, &s, &o)? {
                return Err(bad("stale loot session"));
            }
            stored(&mut t, &o, s.id, op)
        })
        .await
    }
    pub async fn loot_page(
        &self,
        o: Arc<Owner>,
        s: Selected,
        after: u64,
        multiple: bool,
    ) -> Result<wire::LootPage> {
        if after > i64::MAX as u64 {
            return Err(bad("loot cursor"));
        }
        self.call(move|c|{let mut t=c.transaction()?;if !session(&mut t,&s,&o)? {return Err(bad("stale loot session"));}
            let cursor=if multiple {"claim_operation"}else{"encounter"};
            let query=format!("SELECT claim_operation,encounter,item,zone,x,y,z,(extract(epoch FROM expires_at)*1000)::bigint,quantity,kind FROM loot_entitlements WHERE realm=$1 AND (owner=$2 OR EXISTS(SELECT 1 FROM loot_audience a WHERE a.realm=loot_entitlements.realm AND a.claim_operation=loot_entitlements.claim_operation AND a.character_id=$2)) AND state='available' AND expires_at>clock_timestamp() AND {cursor}>$3 ORDER BY {cursor} LIMIT 64");
            let rows=t.query(&query,&[&o.realm,&s.id,&(after as i64)])?;
            let drops:Vec<_>=rows.iter().map(|r|wire::LootDrop{operation:r.get::<_,i64>(0) as u64,encounter:r.get::<_,i64>(1) as u64,item:r.get(2),zone:r.get(3),x:r.get(4),y:r.get(5),z:r.get(6),expires_ms:r.get::<_,i64>(7) as u64,quantity:if multiple{r.get::<_,i32>(8) as u32}else{0},kind:r.get::<_,i32>(9) as u32}).collect();
            let next=if drops.len()==64 {if multiple{drops.last().unwrap().operation}else{drops.last().unwrap().encounter}}else{0};Ok(wire::LootPage{drops,next})
        }).await
    }
    pub async fn expire_page(&self, o: Arc<Owner>, p: Policy) -> Result<()> {
        // One bounded page of IDs, each C/E has its own lock/deadline. No history retained.
        let ids=self.call({let o=o.clone();move|c|Ok(c.query("SELECT claim_operation FROM loot_entitlements WHERE realm=$1 AND state='available' AND expires_at<=clock_timestamp() ORDER BY expires_at,encounter LIMIT 64",&[&o.realm])?.iter().map(|r|r.get::<_,i64>(0) as u64).collect::<Vec<_>>())}).await?;
        for id in ids {
            let o = o.clone();
            let p = p.clone();
            self.call(move |c| decide(c, &o, &p, id, None)).await?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::progression::{Recipient, Settlement};
    fn package() -> Policy {
        Policy::load(std::path::Path::new(
            "../build/packages/loot-lab/progression.bin",
        ))
        .unwrap()
    }
    fn next(c: &mut postgres::Client) -> u64 {
        c.query_one("SELECT nextval('entity_instances')", &[])
            .unwrap()
            .get::<_, i64>(0) as u64
    }
    fn frozen(c: &mut postgres::Client, o: &Owner, p: &Policy, id: i64) -> Settlement {
        Settlement {
            npc: None,
            items: None, coins: None,
            loot_order: None,
            parties: None,
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
                credit: 100,
                reason: 0,
                level: 1,
                xp: 10,
            }],
        }
    }
    fn request(s: &Selected, f: &Settlement, p: &Policy) -> wire::Claim {
        wire::Claim {
            session: s.generation as u64,
            seq: 1,
            entity: s.entity.id,
            operation: f.claim,
            encounter: f.encounter,
            item: p.item.clone(),
            quantity: 1,
        }
    }
    #[test]
    fn canonical_bounds_and_family() {
        let b = canonical(1, 2, 3, "demo:item/token", 1).unwrap();
        assert_eq!(&b[..4], b"N3C1");
        let fixture = include_str!("../../protocol/golden-claim-payload.hex").trim();
        let expected: Vec<u8> = (0..fixture.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&fixture[i..i + 2], 16).unwrap())
            .collect();
        assert_eq!(b, expected);
        assert!(canonical(0, 2, 3, "x", 1).is_err());
        assert!(canonical(u64::MAX, 2, 3, "x", 1).is_err());
        assert!(canonical(1, 2, 3, "x", 2).is_err());
        assert_ne!(b, canonical(2, 1, 3, "demo:item/token", 1).unwrap());
    }
    #[test]
    #[ignore = "child of loot real_database_contract"]
    fn fault_worker() -> Result<()> {
        let mut c = persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
        let o = Owner {
            realm: std::env::var("N3E_TEST_REALM")?,
            owner: "loot-test".into(),
            generation: std::env::var("N3E_TEST_GENERATION")?.parse()?,
        };
        let id: i64 = std::env::var("N3E_TEST_A")?.parse()?;
        let op: u64 = std::env::var("N3E_TEST_CLAIM")?.parse()?;
        let encounter: u64 = std::env::var("N3E_TEST_ENCOUNTER")?.parse()?;
        let p = package();
        let s = Selected {
            id,
            generation: 1,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            entity: wire::Entity {
                id: 1,
                health: 10,
                ..Default::default()
            },
        };
        let a = wire::Claim {
            session: 1,
            seq: 1,
            entity: 1,
            operation: op,
            encounter,
            item: p.item.clone(),
            quantity: 1,
        };
        let expiry = std::env::var("N3E_TEST_EXPIRE").as_deref() == Ok("1");
        decide(
            &mut c,
            &o,
            &p,
            op,
            if expiry { None } else { Some((&s, &a, "demo")) },
        )?;
        fault("after_response");
        Ok(())
    }
    #[test]
    #[ignore = "tests/loot_db.py supplies disposable PG"]
    fn real_database_contract() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let mut c = persistence::connect(&url)?;
        let realm = format!("test-loot-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "loot-test")?;
        let o = Owner {
            realm: realm.clone(),
            owner: "loot-test".into(),
            generation,
        };
        let p = package();
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let id: i64 = c
            .query_one(
                "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'Owner') RETURNING id",
                &[&account, &realm],
            )?
            .get(0);
        crate::settlements::convert(&mut c, &o, &p, "demo", 20)?;
        c.execute("UPDATE characters SET online=true,session_generation=1,realm_generation=$2 WHERE id=$1",&[&id,&generation])?;
        let s = Selected {
            id,
            generation: 1,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            entity: wire::Entity {
                id: 1,
                health: 10,
                ..Default::default()
            },
        };
        let bag_policy = crate::inventory::Policy {
            storage: None,
            wear:None, stats:None, thresholds:None,
            equipment:None,
            capacity:64,currency:"demo:currency/coin".into(),limit:1000,coins:10,
            items:vec![crate::inventory::Item{id:p.item.clone(),label:"Token".into(),stack:1,durability:0,starting:0}],hash:vec![7;32],
        };
        let initial_bag=crate::inventory::execute(&mut c,&o,&s,&bag_policy,&p.item,&wire::BagRequest::default())?.state.unwrap();
        // Dedicated lease renewer keeps long fault/deadline tests authoritative.
        let alive = Arc::new(std::sync::atomic::AtomicBool::new(true));
        let stop = alive.clone();
        let heartbeat_url = url.clone();
        let heartbeat_o = o.clone();
        let heartbeat = std::thread::spawn(move || {
            let mut c = persistence::connect(&heartbeat_url).unwrap();
            while stop.load(std::sync::atomic::Ordering::Relaxed) {
                let _ = persistence::renew(
                    &mut c,
                    &heartbeat_o.realm,
                    &heartbeat_o.owner,
                    heartbeat_o.generation,
                );
                std::thread::sleep(std::time::Duration::from_millis(200));
            }
        });
        let f = frozen(&mut c, &o, &p, id);
        crate::settlements::settle(&mut c, &o, &p, &f)?;
        let a = request(&s, &f, &p);
        let mut outsider = s.clone();
        outsider.id += 999;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&outsider, &a, "demo")))?.status,
            "unknown"
        );
        let mut stale = s.clone();
        stale.generation += 1;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&stale, &a, "demo")))?.status,
            "unknown"
        );
        stale = s.clone();
        stale.life_revision += 1;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&stale, &a, "demo")))?.status,
            "not_alive"
        );
        stale = s.clone();
        stale.entity.health = 0;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&stale, &a, "demo")))?.status,
            "not_alive"
        );
        stale = s.clone();
        stale.entity.y = 3.001;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&stale, &a, "demo")))?.status,
            "out_of_range"
        );
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&s, &a, "other")))?.status,
            "out_of_range"
        );
        let mut forged = a.clone();
        forged.item += "x";
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&s, &forged, "demo")))?.status,
            "conflict"
        );
        let mut boundary = s.clone();
        boundary.entity.y = 3.;
        c.batch_execute("CREATE FUNCTION fail_bag_claim() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test atomic bag claim'; END $$; CREATE TRIGGER test_bag_claim BEFORE INSERT ON loot_claim_results FOR EACH ROW EXECUTE FUNCTION fail_bag_claim()")?;
        assert!(decide(&mut c,&o,&p,f.claim,Some((&boundary,&a,"demo"))).is_err());
        c.batch_execute("DROP TRIGGER test_bag_claim ON loot_claim_results; DROP FUNCTION fail_bag_claim()")?;
        assert_eq!(crate::inventory::execute(&mut c,&o,&s,&bag_policy,&p.item,&wire::BagRequest::default())?.state.unwrap(),initial_bag);
        let mut c2 = persistence::connect(&url)?;
        let (x, y) = std::thread::scope(|scope| {
            let job =
                scope.spawn(|| decide(&mut c2, &o, &p, f.claim, Some((&boundary, &a, "demo"))));
            let x = decide(&mut c, &o, &p, f.claim, Some((&boundary, &a, "demo")));
            (x, job.join().unwrap())
        });
        assert_eq!(x?, y?);
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&s, &a, "demo")))?.count,
            1
        );
        let claimed_bag=crate::inventory::execute(&mut c,&o,&s,&bag_policy,&p.item,&wire::BagRequest::default())?.state.unwrap();
        assert_eq!(claimed_bag.revision,1);
        assert_eq!(claimed_bag.slots.iter().filter(|i|i.instance!=0).count(),1);
        assert_eq!(claimed_bag.slots[0].item,p.item);
        assert_eq!(claimed_bag.slots[0].quantity,1);
        // Remaining legacy recovery cases deliberately mutate aggregate count;
        // remove only this fixture bag before those synthetic count alterations.
        c.execute("DELETE FROM character_bags WHERE character_id=$1", &[&id])?;
        // History remains queryable after death, movement and a later session.
        c.execute(
            "UPDATE characters SET dead=true,respawn_ready_at=clock_timestamp(),life_revision=1,session_generation=2 WHERE id=$1",
            &[&id],
        )?;
        let mut reconnect = s.clone();
        reconnect.generation = 2;
        reconnect.dead = true;
        reconnect.entity.health = 0;
        reconnect.entity.y = 100.;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&reconnect, &a, "demo")))?.status,
            "claimed"
        );
        c.execute(
            "UPDATE characters SET dead=false,respawn_ready_at=NULL,life_revision=0,session_generation=1 WHERE id=$1",
            &[&id],
        )?;
        // Full bag rejects without a result; XP remains from S. Retrying same ID works.
        let f = frozen(&mut c, &o, &p, id);
        crate::settlements::settle(&mut c, &o, &p, &f)?;
        let a = request(&s, &f, &p);
        c.execute(
            "UPDATE character_progress SET count=capacity WHERE character_id=$1",
            &[&id],
        )?;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&s, &a, "demo")))?.status,
            "inventory_full_not_committed"
        );
        assert_eq!(
            c.query_one(
                "SELECT xp FROM character_progress WHERE character_id=$1",
                &[&id]
            )?
            .get::<_, i64>(0),
            20
        );
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM loot_claim_results WHERE claim_operation=$1",
                &[&(f.claim as i64)]
            )?
            .get::<_, i64>(0),
            0
        );
        c.execute(
            "UPDATE character_progress SET count=0 WHERE character_id=$1",
            &[&id],
        )?;
        assert_eq!(
            decide(&mut c, &o, &p, f.claim, Some((&s, &a, "demo")))?.status,
            "claimed"
        );
        // Every process-exit boundary rolls back or recovers one immutable outcome.
        for point in [
            "before_mutation",
            "during_mutation",
            "before_commit",
            "after_commit",
            "after_response",
        ] {
            c.execute(
                "UPDATE character_progress SET count=0 WHERE character_id=$1",
                &[&id],
            )?;
            let f = frozen(&mut c, &o, &p, id);
            crate::settlements::settle(&mut c, &o, &p, &f)?;
            let status = std::process::Command::new(std::env::current_exe()?)
                .args([
                    "loot::tests::fault_worker",
                    "--ignored",
                    "--exact",
                    "--nocapture",
                ])
                .env("N3E_TEST_REALM", &realm)
                .env("N3E_TEST_GENERATION", generation.to_string())
                .env("N3E_TEST_A", id.to_string())
                .env("N3E_TEST_CLAIM", f.claim.to_string())
                .env("N3E_TEST_ENCOUNTER", f.encounter.to_string())
                .env("N3E_CLAIM_FAULT", point)
                .status()?;
            assert_eq!(status.code(), Some(86));
            let expected = if point == "after_commit" || point == "after_response" {
                1
            } else {
                0
            };
            assert_eq!(
                c.query_one(
                    "SELECT count FROM character_progress WHERE character_id=$1",
                    &[&id]
                )?
                .get::<_, i32>(0),
                expected
            );
            let a = request(&s, &f, &p);
            assert_eq!(
                decide(&mut c, &o, &p, f.claim, Some((&s, &a, "demo")))?.count,
                1
            );
        }
        // Known lock rollback retries and absolute worker deadline against real locks.
        for (hold, success) in [(200u64, true), (2200, false)] {
            let f = frozen(&mut c, &o, &p, id);
            crate::settlements::settle(&mut c, &o, &p, &f)?;
            let a = request(&s, &f, &p);
            let lock_url = url.clone();
            let (tx, rx) = std::sync::mpsc::channel();
            let blocker = std::thread::spawn(move || -> Result<()> {
                let mut c = persistence::connect(&lock_url)?;
                let mut t = c.transaction()?;
                t.query_one("SELECT id FROM characters WHERE id=$1 FOR UPDATE", &[&id])?;
                tx.send(()).unwrap();
                std::thread::sleep(std::time::Duration::from_millis(hold));
                t.commit()?;
                Ok(())
            });
            rx.recv().unwrap();
            let start = std::time::Instant::now();
            let result = decide(&mut c, &o, &p, f.claim, Some((&s, &a, "demo")));
            assert_eq!(result.is_ok(), success);
            assert!(start.elapsed() < std::time::Duration::from_millis(2250));
            blocker.join().unwrap()?;
            if !success {
                c = persistence::connect(&url)?;
            }
        }
        // D-137: a claim queued behind two fence holders gets a statement
        // timeout (57014) on its first fence wait and retries inside the same
        // 2 s deadline. No single statement waits past 1 s, so success after
        // more than 1 s means a retry claimed it.
        {
            let f = frozen(&mut c, &o, &p, id);
            crate::settlements::settle(&mut c, &o, &p, &f)?;
            let a = request(&s, &f, &p);
            c.execute("UPDATE character_progress SET count=0 WHERE character_id=$1", &[&id])?;
            let stack = persistence::fence_stack::stack(
                &url,
                &realm,
                std::time::Duration::from_millis(500),
                std::time::Duration::from_millis(900),
            )?;
            let result = decide(&mut c, &o, &p, f.claim, Some((&s, &a, "demo")));
            let elapsed = stack.started.elapsed();
            stack.join()?;
            assert_eq!(result?.status, "claimed");
            assert!(elapsed > std::time::Duration::from_millis(1000), "{elapsed:?}");
            assert!(elapsed < std::time::Duration::from_millis(2250), "{elapsed:?}");
            assert_eq!(
                c.query_one("SELECT count FROM character_progress WHERE character_id=$1", &[&id])?
                    .get::<_, i32>(0),
                1
            );
        }
        // E process exits use five separate saved entitlements and actual DB wall time.
        let mut short = p.clone();
        short.ttl = 10;
        let mut expiring = Vec::new();
        for _ in 0..5 {
            let f = frozen(&mut c, &o, &short, id);
            crate::settlements::settle(&mut c, &o, &short, &f)?;
            expiring.push(f);
        }
        std::thread::sleep(std::time::Duration::from_millis(10100));
        for (f, point) in expiring.iter().zip([
            "before_mutation",
            "during_mutation",
            "before_commit",
            "after_commit",
            "after_response",
        ]) {
            let before: i32 = c
                .query_one(
                    "SELECT count FROM character_progress WHERE character_id=$1",
                    &[&id],
                )?
                .get(0);
            let status = std::process::Command::new(std::env::current_exe()?)
                .args([
                    "loot::tests::fault_worker",
                    "--ignored",
                    "--exact",
                    "--nocapture",
                ])
                .env("N3E_TEST_REALM", &realm)
                .env("N3E_TEST_GENERATION", generation.to_string())
                .env("N3E_TEST_A", id.to_string())
                .env("N3E_TEST_CLAIM", f.claim.to_string())
                .env("N3E_TEST_ENCOUNTER", f.encounter.to_string())
                .env("N3E_CLAIM_FAULT", point)
                .env("N3E_TEST_EXPIRE", "1")
                .status()?;
            assert_eq!(status.code(), Some(86));
            let expected = if point == "after_commit" || point == "after_response" {
                "expired"
            } else {
                "available"
            };
            assert_eq!(
                c.query_one(
                    "SELECT state FROM loot_entitlements WHERE claim_operation=$1",
                    &[&(f.claim as i64)]
                )?
                .get::<_, String>(0),
                expected
            );
            assert_eq!(decide(&mut c, &o, &p, f.claim, None)?.status, "expired");
            assert_eq!(
                c.query_one(
                    "SELECT count FROM character_progress WHERE character_id=$1",
                    &[&id]
                )?
                .get::<_, i32>(0),
                before
            );
        }
        // Actual clock expiry, offline interval and concurrent C/E produce one result.
        let mut short = p.clone();
        short.ttl = 10;
        let f = frozen(&mut c, &o, &short, id);
        crate::settlements::settle(&mut c, &o, &short, &f)?;
        let a = request(&s, &f, &p);
        assert_eq!(decide(&mut c, &o, &p, f.claim, None)?.status, "available");
        std::thread::sleep(std::time::Duration::from_millis(10100));
        let mut c2 = persistence::connect(&url)?;
        let (x, y) = std::thread::scope(|scope| {
            let job = scope.spawn(|| decide(&mut c2, &o, &p, f.claim, None));
            let x = decide(&mut c, &o, &p, f.claim, Some((&s, &a, "demo")));
            (x, job.join().unwrap())
        });
        assert_eq!(x?.status, "expired");
        assert_eq!(y?.status, "expired");
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM loot_claim_results WHERE claim_operation=$1",
                &[&(f.claim as i64)]
            )?
            .get::<_, i64>(0),
            1
        );
        assert!(c
            .execute(
                "UPDATE loot_claim_results SET result_count=0 WHERE realm=$1",
                &[&realm]
            )
            .is_err());
        alive.store(false, std::sync::atomic::Ordering::Relaxed);
        heartbeat.join().unwrap();
        persistence::release(&mut c, &realm, "loot-test", generation)?;
        persistence::acquire(&mut c, &realm, "replacement")?;
        assert!(decide(&mut c, &o, &p, f.claim, None).is_err());
        println!("KO-10 PG authority, full-bag retry, immutable conflict, concurrent claim/expiry, C crash boundaries and stale realm: pass");
        Ok(())
    }
}
