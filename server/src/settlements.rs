//! Atomic all-recipient settlement. Invoked only on the bounded DB worker.
use crate::{
    accounts::{Database, Owner},
    content::{bad, Result},
    persistence,
    progression::{add, Policy, Settlement},
};
use std::sync::Arc;

#[derive(Clone, Debug, PartialEq)]
pub struct Outcome {
    pub id: i64,
    pub xp: u64,
    pub curve: u64,
    pub level: u32,
    pub revision: u64,
    pub awarded: u64,
    pub reason: u32,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Committed {
    pub encounter: u64,
    pub outcome: String,
    pub recipients: Vec<Outcome>,
}
fn stored(t: &mut postgres::Transaction<'_>, realm: &str, encounter: u64) -> Result<Committed> {
    let outcome = t
        .query_one(
            "SELECT outcome FROM encounter_settlements WHERE realm=$1 AND encounter=$2",
            &[&realm, &(encounter as i64)],
        )?
        .get(0);
    let recipients=t.query("SELECT character_id,result_xp,result_curve_xp,result_level,revision,awarded_xp,reason FROM encounter_recipients WHERE realm=$1 AND encounter=$2 ORDER BY character_id", &[&realm,&(encounter as i64)])?.iter().map(|r|Outcome{id:r.get(0),xp:r.get::<_,i64>(1) as u64,curve:r.get::<_,i64>(2) as u64,level:r.get::<_,i32>(3) as u32,revision:r.get::<_,i64>(4) as u64,awarded:r.get::<_,i64>(5) as u64,reason:r.get::<_,i32>(6) as u32}).collect();
    Ok(Committed {
        encounter,
        outcome,
        recipients,
    })
}
pub(crate) fn policy(t: &mut postgres::Transaction<'_>, o: &Owner, p: &Policy) -> Result<()> {
    let row = t
        .query_opt(
            "SELECT mode,definition FROM active_reward_policy WHERE realm=$1",
            &[&o.realm],
        )?
        .ok_or_else(|| bad("realm not converted"))?;
    if row.get::<_, String>(0) != p.mode() || row.get::<_, Vec<u8>>(1) != p.hash {
        return Err(bad("durable reward definition conflict"));
    }
    Ok(())
}
pub fn convert(
    c: &mut postgres::Client,
    o: &Owner,
    p: &Policy,
    game: &str,
    divisor: u32,
) -> Result<()> {
    p.validate()?;
    if divisor == 0 {
        return Err(bad("legacy divisor"));
    }
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if let Some(row)=t.query_opt("SELECT mode,definition,game,legacy_divisor FROM active_reward_policy WHERE realm=$1", &[&o.realm])? {
        if row.get::<_,String>(0)==p.mode() && row.get::<_,Vec<u8>>(1)==p.hash && row.get::<_,String>(2)==game && row.get::<_,i32>(3)==divisor as i32 {return Ok(());}
        return Err(bad("conversion definition conflict"));
    }
    // This function is reachable only via the offline test conversion command.
    // Refuse active current-generation sessions as a second admission barrier.
    let rows = t.query(
        "SELECT id,online,realm_generation FROM characters WHERE realm=$1 ORDER BY id FOR UPDATE",
        &[&o.realm],
    )?;
    if rows
        .iter()
        .any(|r| r.get::<_, bool>(1) && r.get::<_, i64>(2) == o.generation)
    {
        return Err(bad("conversion requires offline realm"));
    }
    t.execute(
        "INSERT INTO realm_reward_policy VALUES($1,$8,$2,$3,1,$4,$5,$6,$7)",
        &[
            &o.realm,
            &game,
            &p.hash,
            &(divisor as i32),
            &p.item,
            &(p.capacity as i32),
            &(p.starting as i32),
            &p.mode(),
        ],
    )?;
    for row in rows {
        let id: i64 = row.get(0);
        t.execute("INSERT INTO character_progress(character_id,item,count,capacity) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING", &[&id,&p.item,&(p.starting as i32),&(p.capacity as i32)])?;
        let v = t.query_one(
            "SELECT item,capacity,xp FROM character_progress WHERE character_id=$1 FOR UPDATE",
            &[&id],
        )?;
        if v.get::<_, String>(0) != p.item || v.get::<_, i32>(1) != p.capacity as i32 {
            return Err(bad("conversion inventory incompatible"));
        }
        let xp = v.get::<_, i64>(2);
        let (curve, level, rem) = p
            .convert(xp as u64, divisor)
            .map_err(|e| bad(&format!("character {id}: {e}")))?;
        t.execute(
            "INSERT INTO character_reward_progress VALUES($1,$2,$3,$4,0,$5,$6,$7)",
            &[
                &id,
                &o.realm,
                &p.hash,
                &(curve as i64),
                &xp,
                &(level as i32),
                &(rem as i64),
            ],
        )?;
    }
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    t.commit()?;
    Ok(())
}
pub fn settle(
    c: &mut postgres::Client,
    o: &Owner,
    p: &Policy,
    s: &Settlement,
) -> Result<Committed> {
    let start = std::time::Instant::now();
    for attempt in 0..=3 {
        let remaining = 2000u64.saturating_sub(start.elapsed().as_millis() as u64);
        if remaining == 0 {
            return Err(bad("settlement worker deadline"));
        }
        match settle_once(c, o, p, s, remaining) {
            Ok(v) => return Ok(v),
            Err(e) => {
                // Only known aborted transactions can be retried. Connection/commit
                // ambiguity fails closed and is recovered by immutable status.
                let rollback = persistence::retryable(e.as_ref());
                let backoff = 50u64 << attempt;
                if !rollback || attempt == 3 || start.elapsed().as_millis() as u64 + backoff >= 2000
                {
                    return Err(e);
                }
                std::thread::sleep(std::time::Duration::from_millis(backoff));
            }
        }
    }
    unreachable!()
}
fn settle_once(
    c: &mut postgres::Client,
    o: &Owner,
    p: &Policy,
    s: &Settlement,
    remaining_ms: u64,
) -> Result<Committed> {
    p.validate()?;
    s.validate(p)?;
    if s.generation != o.generation {
        return Err(bad("stale settlement source"));
    }
    let payload = s.canonical()?;
    let digest = openssl::sha::sha256(&payload).to_vec();
    let mut t = c.transaction()?;
    t.query_one(
        "SELECT set_config('transaction_timeout',$1,true)",
        &[&format!("{remaining_ms}ms")],
    )?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    policy(&mut t, o, p)?;
    // Realm lock serializes creation and duplicate checks; history is immutable.
    if let Some(row) = t.query_opt(
        "SELECT payload,digest FROM encounter_settlements WHERE realm=$1 AND encounter=$2",
        &[&o.realm, &(s.encounter as i64)],
    )? {
        if row.get::<_, Vec<u8>>(0) != payload || row.get::<_, Vec<u8>>(1) != digest {
            return Err(bad("settlement payload conflict"));
        }
        let v = stored(&mut t, &o.realm, s.encounter)?;
        t.commit()?;
        return Ok(v);
    }
    for r in &s.recipients {
        if t.query_opt(
            "SELECT id FROM characters WHERE id=$1 AND realm=$2 FOR UPDATE",
            &[&r.id, &o.realm],
        )?
        .is_none()
        {
            return Err(bad("settlement character missing/cross-realm"));
        }
    }
    let mut results = Vec::new();
    for r in &s.recipients {
        let row=t.query_opt("SELECT p.xp,r.curve_xp,r.revision,r.definition,p.item,p.capacity FROM character_progress p JOIN character_reward_progress r ON p.character_id=r.character_id WHERE p.character_id=$1 AND r.realm=$2 FOR UPDATE OF p,r", &[&r.id,&o.realm])?.ok_or_else(||bad("settlement progress missing"))?;
        if row.get::<_, Vec<u8>>(3) != p.hash
            || row.get::<_, String>(4) != p.item
            || row.get::<_, i32>(5) != p.capacity as i32
        {
            return Err(bad("settlement progress definition conflict"));
        }
        let xp = add(row.get::<_, i64>(0) as u64, r.xp)?;
        let curve = add(row.get::<_, i64>(1) as u64, r.xp)?;
        let revision = add(
            row.get::<_, i64>(2) as u64,
            if r.reason == 0 { 1 } else { 0 },
        )?;
        results.push(Outcome {
            id: r.id,
            xp,
            curve,
            level: p.level(curve),
            revision,
            awarded: r.xp,
            reason: r.reason,
        });
    }
    let owner = s.owner();
    let capacity = if let Some(id) = owner {
        t.query_one("SELECT count(*) FROM loot_entitlements WHERE realm=$1 AND owner=$2 AND state='available' AND expires_at>clock_timestamp()", &[&o.realm,&id])?.get::<_,i64>(0)+(s.items.as_ref().map_or(1,|i|i.entries.len())+usize::from(s.coins.as_ref().is_some_and(|v|v.amount>0))) as i64>64
    } else {
        false
    };
    let outcome = if owner.is_none() {
        "no_recipient"
    } else if capacity {
        "loot_capacity"
    } else {
        "entitled"
    };
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    fault("before_mutation");
    t.execute("INSERT INTO encounter_settlements(realm,encounter,source_generation,release,definition,payload,digest,zone,x,y,z,tick,outcome,owner) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)", &[&o.realm,&(s.encounter as i64),&s.generation,&s.release,&s.definition,&payload,&digest,&s.zone,&s.position[0],&s.position[1],&s.position[2],&(s.tick as i64),&outcome,&owner])?;
    for (r, v) in s.recipients.iter().zip(&results) {
        if r.reason == 0 {
            t.execute(
                "UPDATE character_progress SET xp=$2 WHERE character_id=$1",
                &[&v.id, &(v.xp as i64)],
            )?;
            t.execute("UPDATE character_reward_progress SET curve_xp=$2,revision=$3 WHERE character_id=$1", &[&v.id,&(v.curve as i64),&(v.revision as i64)])?;
        }
        t.execute(
            "INSERT INTO encounter_recipients(realm,encounter,character_id,credit,reason,frozen_level,awarded_xp,result_xp,result_curve_xp,result_level,revision) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
            &[
                &o.realm,
                &(s.encounter as i64),
                &r.id,
                &(r.credit as i64),
                &(r.reason as i32),
                &(r.level as i32),
                &(r.xp as i64),
                &(v.xp as i64),
                &(v.curve as i64),
                &(v.level as i32),
                &(v.revision as i64),
            ],
        )?;
        fault("during_mutation");
    }
    if let Some(id) = owner.filter(|_| !capacity) {
        let mut operations=Vec::new();
        if s.items.is_none() {
        t.execute("INSERT INTO loot_entitlements(realm,encounter,owner,item,quantity,zone,x,y,z,claim_operation,definition,created_at,expires_at) SELECT realm,encounter,$3,$4,1,zone,x,y,z,$5,definition,committed_at,committed_at+$6::bigint*interval '1 second' FROM encounter_settlements WHERE realm=$1 AND encounter=$2", &[&o.realm,&(s.encounter as i64),&id,&p.item,&(s.claim as i64),&(p.ttl as i64)])?;
        operations.push(s.claim as i64);
        }
        if let (Some(outcome),Some(policy))=(&s.items,&p.items) {
            for entry in &outcome.entries {
                let item=&policy.items[entry.item as usize];
                let op:i64=t.query_one("SELECT nextval('entity_instances')",&[])?.get(0);
                t.execute("INSERT INTO loot_entitlements(realm,encounter,owner,item,quantity,zone,x,y,z,claim_operation,definition,created_at,expires_at,kind,durability) SELECT realm,encounter,$3,$4,$5,zone,x,y,z,$6,definition,committed_at,committed_at+$7::bigint*interval '1 second',2,$8 FROM encounter_settlements WHERE realm=$1 AND encounter=$2", &[&o.realm,&(s.encounter as i64),&id,&item.id,&(item.quantity as i32),&op,&(p.ttl as i64),&(item.durability as i32)])?;
                operations.push(op);
            }
        }
        if let (Some(coins),Some(policy))=(&s.coins,&p.coins) {
            if coins.amount>0 {
                let op:i64=t.query_one("SELECT nextval('entity_instances')",&[])?.get(0);
                t.execute("INSERT INTO loot_entitlements(realm,encounter,owner,item,quantity,zone,x,y,z,claim_operation,definition,created_at,expires_at,kind) SELECT realm,encounter,$3,$4,$5,zone,x,y,z,$6,definition,committed_at,committed_at+$7::bigint*interval '1 second',1 FROM encounter_settlements WHERE realm=$1 AND encounter=$2", &[&o.realm,&(s.encounter as i64),&id,&policy.currency,&(coins.amount as i32),&op,&(p.ttl as i64)])?;
                operations.push(op);
            }
        }
        if p.party_loot.is_some() {
            let audience=s.parties.as_ref().and_then(|groups|groups.iter().find(|g|g.members.contains(&id))).map_or_else(||vec![id],|g|g.members.clone());
            for op in operations {for member in &audience {
                t.execute("INSERT INTO loot_audience VALUES($1,$2,$3)",&[&o.realm,&op,member])?;
            }}
        }
    }
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    fault("before_commit");
    t.commit()?;
    fault("after_commit");
    Ok(Committed {
        encounter: s.encounter,
        outcome: outcome.into(),
        recipients: results,
    })
}
impl Database {
    pub async fn settle(&self, o: Arc<Owner>, p: Policy, s: Settlement) -> Result<Committed> {
        self.call(move |c| settle(c, &o, &p, &s)).await
    }
}
pub fn fault(point: &str) {
    if std::env::var("N3E_SETTLEMENT_FAULT").as_deref() == Ok(point) {
        eprintln!("settlement fault {point}");
        std::process::exit(86);
    }
}

pub fn check_start(c: &mut postgres::Client, realm: &str, p: Option<&Policy>) -> Result<()> {
    let row = c.query_opt(
        "SELECT mode,definition FROM active_reward_policy WHERE realm=$1",
        &[&realm],
    )?;
    match (p, row) {
        (None, None) => Ok(()),
        (None, Some(r)) if r.get::<_, String>(0) == "legacy_v1" => Ok(()),
        (Some(p), Some(r))
            if r.get::<_, String>(0) == p.mode()
                && r.get::<_, Vec<u8>>(1) == p.hash =>
        {
            Ok(())
        }
        _ => Err(bad(
            "reward policy requires explicit offline conversion; rollback forbidden",
        )),
    }
}
/// Called in the same transaction that creates a new character, never on login.
pub fn initialize(t: &mut postgres::Transaction<'_>, realm: &str, id: i64) -> Result<()> {
    if let Some(r)=t.query_opt("SELECT definition,item,capacity,starting FROM active_reward_policy WHERE realm=$1 AND mode IN ('contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5')", &[&realm])? {
        t.execute("INSERT INTO character_progress(character_id,item,count,capacity) VALUES($1,$2,$3,$4)", &[&id,&r.get::<_,String>(1),&r.get::<_,i32>(3),&r.get::<_,i32>(2)])?;
        t.execute("INSERT INTO character_reward_progress VALUES($1,$2,$3,0,0,0,1,0)", &[&id,&realm,&r.get::<_,Vec<u8>>(0)])?;
    }
    Ok(())
}

impl Database {
    pub async fn settlement_status(
        &self,
        s: crate::accounts::Selected,
        o: Arc<Owner>,
        encounter: u64,
    ) -> Result<crate::wire::SettlementResult> {
        if encounter == 0 || encounter > i64::MAX as u64 {
            return Err(bad("settlement identity"));
        }
        self.call(move |c| {
            let mut t=c.transaction()?;
            let current=t.query_opt("SELECT id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online", &[&s.id,&o.realm,&s.generation,&o.generation])?;
            if current.is_none() {return Err(bad("stale settlement status session"));}
            let row=t.query_opt("SELECT s.outcome,r.awarded_xp,r.result_xp,r.result_curve_xp,r.result_level,r.revision,r.reason FROM encounter_settlements s JOIN encounter_recipients r USING(realm,encounter) WHERE s.realm=$1 AND s.encounter=$2 AND r.character_id=$3", &[&o.realm,&(encounter as i64),&s.id])?;
            let result=if let Some(r)=row {crate::wire::SettlementResult{encounter,status:r.get(0),awarded_xp:r.get::<_,i64>(1) as u64,xp:r.get::<_,i64>(2) as u64,curve_xp:r.get::<_,i64>(3) as u64,level:r.get::<_,i32>(4) as u32,revision:r.get::<_,i64>(5) as u64,reason:r.get::<_,i32>(6) as u32}} else {crate::wire::SettlementResult{encounter,status:"unknown".into(),..Default::default()}};
            t.commit()?;Ok(result)
        }).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::progression::Recipient;
    fn package() -> Policy {
        Policy::load(std::path::Path::new(
            "../build/packages/progression-lab/progression.bin",
        ))
        .unwrap()
    }
    fn next(c: &mut postgres::Client) -> u64 {
        c.query_one("SELECT nextval('entity_instances')", &[])
            .unwrap()
            .get::<_, i64>(0) as u64
    }
    fn frozen(c: &mut postgres::Client, o: &Owner, p: &Policy, a: i64, b: i64) -> Settlement {
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
            tick: 10,
            claim: next(c),
            recipients: vec![
                Recipient {
                    id: a,
                    credit: 60,
                    reason: 0,
                    level: 1,
                    xp: 6,
                },
                Recipient {
                    id: b,
                    credit: 40,
                    reason: 0,
                    level: 1,
                    xp: 4,
                },
            ],
        }
    }
    fn sum(c: &mut postgres::Client, realm: &str) -> i64 {
        c.query_one("SELECT COALESCE(sum(xp),0)::bigint FROM character_progress p JOIN characters c ON c.id=p.character_id WHERE realm=$1",&[&realm]).unwrap().get(0)
    }
    #[test]
    #[ignore = "child process of real_database_contract"]
    fn fault_worker() -> Result<()> {
        let mut c = persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
        let o = Owner {
            realm: std::env::var("N3E_TEST_REALM")?,
            owner: "test".into(),
            generation: std::env::var("N3E_TEST_GENERATION")?.parse()?,
        };
        let p = package();
        let a = std::env::var("N3E_TEST_A")?.parse()?;
        let b = std::env::var("N3E_TEST_B")?.parse()?;
        let mut s = frozen(&mut c, &o, &p, a, b);
        s.encounter = std::env::var("N3E_TEST_ENCOUNTER")?.parse()?;
        s.claim = std::env::var("N3E_TEST_CLAIM")?.parse()?;
        settle(&mut c, &o, &p, &s)?;
        fault("after_response");
        Ok(())
    }
    #[test]
    #[ignore = "tests/progression_db.py supplies isolated Postgres"]
    fn real_database_contract() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let mut c = persistence::connect(&url)?;
        persistence::verify(&mut c)?;
        let realm = format!("test-progression-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "test")?;
        let o = Arc::new(Owner {
            realm: realm.clone(),
            owner: "test".into(),
            generation,
        });
        let p = package();
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let a: i64 = c
            .query_one(
                "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'A') RETURNING id",
                &[&account, &realm],
            )?
            .get(0);
        let b: i64 = c
            .query_one(
                "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'B') RETURNING id",
                &[&account, &realm],
            )?
            .get(0);
        for id in [a, b] {
            c.execute(
                "INSERT INTO character_progress VALUES($1,$2,2,2,45)",
                &[&id, &p.item],
            )?;
        }
        let legacy = next(&mut c) as i64;
        c.execute("INSERT INTO reward_operations(operation,character_id,realm,item,quantity,xp_grant,status,result_count,result_xp) VALUES($1,$2,$3,$4,1,10,'inventory_full',2,45)", &[&legacy,&a,&realm,&p.item])?;
        let historical: String = c
            .query_one(
                "SELECT row_to_json(r)::text FROM reward_operations r WHERE operation=$1",
                &[&legacy],
            )?
            .get(0);
        // Whole conversion must roll back if even one character is unsupported.
        c.execute(
            "UPDATE character_progress SET xp=200 WHERE character_id=$1",
            &[&b],
        )?;
        assert!(convert(&mut c, &o, &p, "demo", 20).is_err());
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM realm_reward_policy WHERE realm=$1",
                &[&realm]
            )?
            .get::<_, i64>(0),
            0
        );
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM character_reward_progress WHERE realm=$1",
                &[&realm]
            )?
            .get::<_, i64>(0),
            0
        );
        c.execute(
            "UPDATE character_progress SET xp=45 WHERE character_id=$1",
            &[&b],
        )?;
        convert(&mut c, &o, &p, "demo", 20)?;
        convert(&mut c, &o, &p, "demo", 20)?;
        assert_eq!(
            c.query_one(
                "SELECT curve_xp FROM character_reward_progress WHERE character_id=$1",
                &[&a]
            )?
            .get::<_, i64>(0),
            60
        );
        let mut incompatible = p.clone();
        incompatible.hash[0] ^= 1;
        assert!(convert(&mut c, &o, &incompatible, "demo", 20).is_err());
        assert!(check_start(&mut c, &realm, None).is_err());
        check_start(&mut c, &realm, Some(&p))?;
        let db = Database::start(url.clone(), Default::default())?;
        let db2 = Database::start(url.clone(), Default::default())?;
        let rt = tokio::runtime::Runtime::new()?;
        let s = frozen(&mut c, &o, &p, a, b);
        let (v, w) = rt.block_on(async {
            tokio::join!(
                db.settle(o.clone(), p.clone(), s.clone()),
                db2.settle(o.clone(), p.clone(), s.clone())
            )
        });
        let v = v?;
        assert_eq!(v, w?);
        assert_eq!((v.recipients[0].xp, v.recipients[1].xp), (51, 49));
        assert_eq!(v.outcome, "entitled");
        assert_eq!(sum(&mut c, &realm), 100);
        assert_eq!(
            c.query_one(
                "SELECT count FROM character_progress WHERE character_id=$1",
                &[&a]
            )?
            .get::<_, i32>(0),
            2
        );
        let mut conflict = s.clone();
        conflict.release[0] ^= 1;
        assert!(settle(&mut c, &o, &p, &conflict).is_err());
        // Captured sessions are not semantic identity. Concurrent checkpoint/login
        // changes cannot revoke earned credit or write either progression counter.
        let selected = rt.block_on(db.select(account, a, o.clone()))?;
        let s2 = frozen(&mut c, &o, &p, a, b);
        let (earned, saved) = rt.block_on(async {
            tokio::join!(
                db.settle(o.clone(), p.clone(), s2.clone()),
                db2.save(o.clone(), vec![(selected.clone(), false)])
            )
        });
        earned?;
        saved?;
        let new = rt.block_on(db.select(account, a, o.clone()))?;
        assert_ne!(new.generation, selected.generation);
        assert_eq!(
            rt.block_on(db.settlement_status(new.clone(), o.clone(), s.encounter))?
                .xp,
            51
        );
        assert!(rt
            .block_on(db.settlement_status(selected, o.clone(), s.encounter))
            .is_err());
        let mut rules = crate::rules::Rules::load(
            std::path::Path::new("../build/packages/progression-lab/gameplay.bin"),
            "demo",
        )?;
        rules.progression = Some(std::sync::Arc::new(p.clone()));
        let inventory = rt.block_on(db.inventory(new.clone(), o.clone(), rules.clone()))?;
        assert_eq!(
            (inventory.xp, inventory.curve_xp, inventory.count),
            (57, 72, 2)
        );
        assert!(rt
            .block_on(db.reward(new.clone(), o.clone(), rules, s.encounter))
            .is_err());
        // A frozen grant survives a durable death and session replacement.
        let mut dead = new.clone();
        dead.entity.health = 0;
        rt.block_on(db.transition(o.clone(), dead, true, 0))?;
        let s3 = frozen(&mut c, &o, &p, a, b);
        settle(&mut c, &o, &p, &s3)?;
        assert!(c
            .query_one("SELECT dead FROM characters WHERE id=$1", &[&a])?
            .get::<_, bool>(0));
        let original: i64 = c
            .query_one(
                "SELECT xp FROM character_progress WHERE character_id=$1",
                &[&a],
            )?
            .get(0);
        c.execute(
            "UPDATE character_progress SET xp=$2 WHERE character_id=$1",
            &[&a, &(i64::MAX - 1)],
        )?;
        let overflow = frozen(&mut c, &o, &p, a, b);
        assert!(settle(&mut c, &o, &p, &overflow).is_err());
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM encounter_settlements WHERE realm=$1 AND encounter=$2",
                &[&realm, &(overflow.encounter as i64)]
            )?
            .get::<_, i64>(0),
            0
        );
        c.execute(
            "UPDATE character_progress SET xp=$2 WHERE character_id=$1",
            &[&a, &original],
        )?;
        let before = sum(&mut c, &realm);
        for point in [
            "before_mutation",
            "during_mutation",
            "before_commit",
            "after_commit",
            "after_response",
        ] {
            persistence::renew(&mut c, &realm, "test", generation)?;
            let f = frozen(&mut c, &o, &p, a, b);
            let old = sum(&mut c, &realm);
            let output = std::process::Command::new(std::env::current_exe()?)
                .args([
                    "--ignored",
                    "--exact",
                    "settlements::tests::fault_worker",
                    "--nocapture",
                ])
                .env("N3E_TEST_DATABASE_URL", &url)
                .env("N3E_TEST_REALM", &realm)
                .env("N3E_TEST_GENERATION", generation.to_string())
                .env("N3E_TEST_A", a.to_string())
                .env("N3E_TEST_B", b.to_string())
                .env("N3E_TEST_ENCOUNTER", f.encounter.to_string())
                .env("N3E_TEST_CLAIM", f.claim.to_string())
                .env("N3E_SETTLEMENT_FAULT", point)
                .output()?;
            assert_eq!(
                output.status.code(),
                Some(86),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            let committed = point == "after_commit" || point == "after_response";
            assert_eq!(sum(&mut c, &realm), old + if committed { 10 } else { 0 });
            assert_eq!(
                c.query_one(
                    "SELECT count(*) FROM loot_entitlements WHERE realm=$1 AND encounter=$2",
                    &[&realm, &(f.encounter as i64)]
                )?
                .get::<_, i64>(0),
                if committed { 1 } else { 0 }
            );
            if committed {
                let result = settle(&mut c, &o, &p, &f)?;
                assert_eq!(result.outcome, "entitled");
                assert_eq!(sum(&mut c, &realm), old + 10);
            }
            println!("process exit {point}: atomic/recovered");
        }
        assert_eq!(sum(&mut c, &realm), before + 20);
        // No eligible recipients, deterministic tie, unknown character atomic abort.
        let mut empty = frozen(&mut c, &o, &p, a, b);
        for r in &mut empty.recipients {
            r.reason = 1;
            r.xp = 0;
        }
        assert_eq!(settle(&mut c, &o, &p, &empty)?.outcome, "no_recipient");
        let mut tie = frozen(&mut c, &o, &p, a, b);
        for r in &mut tie.recipients {
            r.credit = 50;
            r.xp = 5;
        }
        settle(&mut c, &o, &p, &tie)?;
        assert_eq!(
            c.query_one(
                "SELECT owner FROM loot_entitlements WHERE realm=$1 AND encounter=$2",
                &[&realm, &(tie.encounter as i64)]
            )?
            .get::<_, i64>(0),
            a
        );
        let old = sum(&mut c, &realm);
        let mut missing = frozen(&mut c, &o, &p, a, b);
        missing.recipients[1].id = i64::MAX;
        assert!(settle(&mut c, &o, &p, &missing).is_err());
        assert_eq!(sum(&mut c, &realm), old);
        let mut stale = (*o).clone();
        stale.generation += 1;
        assert!(settle(&mut c, &stale, &p, &s).is_err());
        // A known lock timeout rolls back, backs off and retries the same payload.
        for (delay, success) in [(950u64, true), (2300, false)] {
            persistence::renew(&mut c, &realm, "test", generation)?;
            let f = frozen(&mut c, &o, &p, a, b);
            let old = sum(&mut c, &realm);
            // PQ-294: connect before the hold and the timer, so the bound
            // times the worker's 2 s deadline alone (as loot.rs's case does)
            // and the hold starts with the worker, whatever a connect costs.
            let mut worker = persistence::connect(&url)?;
            let (tx, rx) = std::sync::mpsc::channel();
            let lock_url = url.clone();
            let lock_realm = realm.clone();
            let blocker = std::thread::spawn(move || -> Result<()> {
                let mut c = persistence::connect(&lock_url)?;
                let mut t = c.transaction()?;
                t.query_one(
                    "SELECT realm FROM realm_fence WHERE realm=$1 FOR UPDATE",
                    &[&lock_realm],
                )?;
                tx.send(()).unwrap();
                std::thread::sleep(std::time::Duration::from_millis(delay));
                t.commit()?;
                Ok(())
            });
            rx.recv().unwrap();
            let start = std::time::Instant::now();
            let result = settle(&mut worker, &o, &p, &f);
            let elapsed = start.elapsed();
            assert_eq!(result.is_ok(), success, "{delay} ms hold: {elapsed:?}");
            assert!(
                elapsed < std::time::Duration::from_millis(2250),
                "{delay} ms hold: {elapsed:?}"
            );
            println!("lock hold {delay} ms: ok={} in {elapsed:?}", result.is_ok());
            blocker.join().unwrap()?;
            assert_eq!(sum(&mut c, &realm), old + if success { 10 } else { 0 });
        }
        // D-137: behind two fence holders the first attempt's fence wait ends
        // in a statement timeout (57014) before either wait reaches the lock
        // timeout. No single statement waits past 1 s, so success after more
        // than 1 s means a retry inside the same 2 s deadline committed it.
        persistence::renew(&mut c, &realm, "test", generation)?;
        let f = frozen(&mut c, &o, &p, a, b);
        let old = sum(&mut c, &realm);
        let mut worker = persistence::connect(&url)?;
        let stack = persistence::fence_stack::stack(
            &url,
            &realm,
            std::time::Duration::from_millis(500),
            std::time::Duration::from_millis(900),
        )?;
        let result = settle(&mut worker, &o, &p, &f);
        let elapsed = stack.started.elapsed();
        stack.join()?;
        result?;
        assert!(elapsed > std::time::Duration::from_millis(1000), "{elapsed:?}");
        assert!(elapsed < std::time::Duration::from_millis(2250), "{elapsed:?}");
        assert_eq!(sum(&mut c, &realm), old + 10);
        // All 64 outstanding entitlements may coexist with a full inventory.
        loop {
            persistence::renew(&mut c, &realm, "test", generation)?;
            let count = c
                .query_one(
                    "SELECT count(*) FROM loot_entitlements WHERE realm=$1 AND owner=$2",
                    &[&realm, &a],
                )?
                .get::<_, i64>(0);
            if count >= 64 {
                break;
            }
            let f = frozen(&mut c, &o, &p, a, b);
            settle(&mut c, &o, &p, &f)?;
        }
        let f = frozen(&mut c, &o, &p, a, b);
        let old = sum(&mut c, &realm);
        assert_eq!(settle(&mut c, &o, &p, &f)?.outcome, "loot_capacity");
        assert_eq!(sum(&mut c, &realm), old + 10);
        assert_eq!(
            c.query_one(
                "SELECT row_to_json(r)::text FROM reward_operations r WHERE operation=$1",
                &[&legacy]
            )?
            .get::<_, String>(0),
            historical
        );
        assert!(c
            .execute(
                "UPDATE encounter_recipients SET awarded_xp=0 WHERE realm=$1",
                &[&realm]
            )
            .is_err());
        assert!(c
            .execute(
                "DELETE FROM encounter_settlements WHERE realm=$1",
                &[&realm]
            )
            .is_err());
        // New characters get both counters and the original inventory once.
        rt.block_on(db.create(account, "New".into(), o.clone(), [0.; 3], 8))?;
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM character_reward_progress WHERE realm=$1",
                &[&realm]
            )?
            .get::<_, i64>(0),
            3
        );
        // Old binaries reject the additional migration; no historical checksum changed.
        assert_eq!(
            c.query_one("SELECT count(*) FROM schema_migrations", &[])?
                .get::<_, i64>(0),
            persistence::MIGRATIONS.len() as i64
        );
        persistence::release(&mut c, &realm, "test", generation)?;
        let newer = persistence::acquire(&mut c, &realm, "replacement")?;
        assert!(newer > generation);
        assert!(settle(&mut c, &o, &p, &f).is_err());
        println!("conversion, concurrency, full bag, immutable retry, session/life changes, caps, fencing: pass; realm={realm}");
        Ok(())
    }
}
