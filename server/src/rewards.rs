//! Atomic grants and immutable results. Only the tick can submit a qualifying kill.
use crate::{
    accounts::{Database, Owner, Selected},
    content::{bad, Result},
    persistence,
    rules::Rules,
    wire,
};
use std::sync::Arc;
pub(crate) fn inventory(
    t: &mut postgres::Transaction<'_>,
    id: i64,
    rules: &Rules,
) -> Result<wire::Inventory> {
    if rules.progression.is_none() {
        if t.query_opt("SELECT r.realm FROM characters c JOIN active_reward_policy r ON c.realm=r.realm WHERE c.id=$1 AND r.mode IN ('contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5')", &[&id])?.is_some() {
            return Err(bad("legacy progression forbidden after conversion"));
        }
        t.execute("INSERT INTO character_progress(character_id,item,count,capacity) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING", &[&id,&rules.item,&(rules.starting_items as i32),&(rules.slots as i32)])?;
    }
    let row = t.query_one(
        "SELECT item,count,capacity,xp FROM character_progress WHERE character_id=$1 FOR UPDATE",
        &[&id],
    )?;
    let xp = row.get::<_, i64>(3) as u64;
    if row.get::<_, String>(0) != rules.item || row.get::<_, i32>(2) != rules.slots as i32 {
        return Err(bad("durable inventory incompatible with package"));
    }
    let progress = if let Some(policy) = &rules.progression {
        let r=t.query_opt("SELECT curve_xp,revision,definition FROM character_reward_progress WHERE character_id=$1", &[&id])?.ok_or_else(||bad("missing converted progress"))?;
        if r.get::<_, Vec<u8>>(2) != policy.hash {
            return Err(bad("progress definition conflict"));
        }
        Some((r.get::<_, i64>(0) as u64, r.get::<_, i64>(1) as u64))
    } else {
        None
    };
    let last=t.query_opt("SELECT operation,status FROM reward_operations WHERE character_id=$1 ORDER BY operation DESC LIMIT 1", &[&id])?;
    let settlement = if rules.progression.is_some() {
        t.query_opt("SELECT s.encounter,s.outcome FROM encounter_settlements s JOIN encounter_recipients r USING(realm,encounter) WHERE r.character_id=$1 ORDER BY r.committed_at DESC,r.encounter DESC LIMIT 1", &[&id])?
    } else {
        None
    };
    Ok(wire::Inventory {
        latest_settlement: settlement
            .as_ref()
            .map(|r| r.get::<_, i64>(0) as u64)
            .unwrap_or(0),
        settlement_status: settlement.map(|r| r.get(1)).unwrap_or_default(),
        item: rules.item.clone(),
        count: row.get::<_, i32>(1) as u32,
        capacity: rules.slots,
        xp,
        level: progress
            .map(|v| rules.progression.as_ref().unwrap().level(v.0) as u64)
            .unwrap_or(1 + xp / rules.level_xp as u64),
        curve_xp: progress.map(|v| v.0).unwrap_or(0),
        revision: progress.map(|v| v.1).unwrap_or(0),
        pending: 0,
        last_operation: last
            .as_ref()
            .map(|r| r.get::<_, i64>(0) as u64)
            .unwrap_or(0),
        reward_status: last.map(|r| r.get(1)).unwrap_or_default(),
    })
}
fn session(t: &mut postgres::Transaction<'_>, s: &Selected, o: &Owner) -> Result<()> {
    persistence::fence(t, &o.realm, &o.owner, o.generation)?;
    if t.query_opt("SELECT id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 FOR UPDATE", &[&s.id,&o.realm,&s.generation,&o.generation])?.is_none(){return Err(bad("stale reward session"));}
    Ok(())
}
impl Database {
    pub async fn inventory(&self, s: Selected, o: Arc<Owner>, r: Rules) -> Result<wire::Inventory> {
        self.call(move |c| {
            let mut t = c.transaction()?;
            session(&mut t, &s, &o)?;
            let v = inventory(&mut t, s.id, &r)?;
            t.commit()?;
            Ok(v)
        })
        .await
    }
    pub async fn instances(&self, n: i64) -> Result<Vec<u64>> {
        if !(1..=1024).contains(&n) {
            return Err(bad("instance allocation bound"));
        }
        self.call(move |c| {
            Ok(c.query(
                "SELECT nextval('entity_instances') FROM generate_series(1,$1::bigint)",
                &[&n],
            )?
            .iter()
            .map(|r| r.get::<_, i64>(0) as u64)
            .collect())
        })
        .await
    }
    pub async fn reward(
        &self,
        s: Selected,
        o: Arc<Owner>,
        r: Rules,
        operation: u64,
    ) -> Result<wire::Inventory> {
        self.call(move|c|{
            if r.progression.is_some() {return Err(bad("legacy grant forbidden for contribution policy"));}
            let mut t=c.transaction()?;session(&mut t,&s,&o)?;
            let mut v=inventory(&mut t,s.id,&r)?;
            if let Some(row)=t.query_opt("SELECT character_id,item,quantity,xp_grant,status FROM reward_operations WHERE operation=$1", &[&(operation as i64)])? {
                if row.get::<_,i64>(0)!=s.id || row.get::<_,String>(1)!=r.item || row.get::<_,i32>(2)!=r.reward_items as i32 || row.get::<_,i32>(3)!=r.reward_xp as i32 {return Err(bad("reward operation payload conflict"));}
                v.last_operation=operation;v.reward_status=row.get(4);t.commit()?;return Ok(v);
            }
            let full=v.count+r.reward_items>v.capacity;
            if !full {v.count+=r.reward_items;v.xp+=r.reward_xp as u64;v.level=1+v.xp/r.level_xp as u64;
                t.execute("UPDATE character_progress SET count=$2,xp=$3 WHERE character_id=$1", &[&s.id,&(v.count as i32),&(v.xp as i64)])?;
            }
            v.last_operation=operation;v.reward_status=if full{"inventory_full"}else{"committed"}.into();
            t.execute("INSERT INTO reward_operations(operation,character_id,realm,item,quantity,xp_grant,status,result_count,result_xp) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)", &[&(operation as i64),&s.id,&o.realm,&r.item,&(r.reward_items as i32),&(r.reward_xp as i32),&v.reward_status,&(v.count as i32),&(v.xp as i64)])?;
            fault("before_commit");
            t.commit()?;
            fault("after_commit");
            Ok(v)
        }).await
    }
    pub async fn reward_status(
        &self,
        s: Selected,
        o: Arc<Owner>,
        operation: u64,
    ) -> Result<wire::RewardResult> {
        self.call(move|c|{let mut t=c.transaction()?;session(&mut t,&s,&o)?;
            let row=t.query_opt("SELECT status,result_count,result_xp FROM reward_operations WHERE operation=$1 AND character_id=$2 AND realm=$3", &[&(operation as i64),&s.id,&o.realm])?;
            let v=match row {Some(r)=>wire::RewardResult{operation,status:r.get(0),count:r.get::<_,i32>(1) as u32,xp:r.get::<_,i64>(2) as u64},None=>wire::RewardResult{operation,status:"unknown".into(),..Default::default()}};t.commit()?;Ok(v)
        }).await
    }
}
// Opt-in isolated acceptance runs only; no wire-accessible fault control.
pub fn fault(point: &str) {
    if std::env::var("N3E_REWARD_FAULT").as_deref() == Ok(point) {
        eprintln!("reward fault {point}");
        std::process::exit(86);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "isolated Postgres supplied by tests/gameplay.py"]
    fn atomic_rewards_and_conflicts() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = persistence::connect(&url)?;
        let realm = format!("reward-test-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "test")?;
        let o = Arc::new(Owner {
            realm: realm.clone(),
            owner: "test".into(),
            generation,
        });
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let rt = tokio::runtime::Runtime::new()?;
        let db = Database::start(url.clone(), Default::default())?;
        let db2 = Database::start(url, Default::default())?;
        let mut rules = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )?;
        rules.slots = 3;
        rules.starting_items = 1;
        rules.reward_items = 1;
        rt.block_on(db.create(account, "Test".into(), o.clone(), [0., 0., 0.], 8))?;
        let id = rt.block_on(db.list(account, realm.clone(), &rules))?.characters[0].id as i64;
        let selected = rt.block_on(db.select(account, id, o.clone()))?;
        let ids = rt.block_on(db.instances(4))?;
        let (a, b) = rt.block_on(async {
            tokio::join!(
                db.reward(selected.clone(), o.clone(), rules.clone(), ids[0]),
                db2.reward(selected.clone(), o.clone(), rules.clone(), ids[0])
            )
        });
        assert_eq!(a?.count, 2);
        assert_eq!(b?.count, 2);
        let mut conflict = rules.clone();
        conflict.reward_xp += 1;
        assert!(rt
            .block_on(db.reward(selected.clone(), o.clone(), conflict, ids[0]))
            .is_err());
        let (a, b) = rt.block_on(async {
            tokio::join!(
                db.reward(selected.clone(), o.clone(), rules.clone(), ids[1]),
                db2.reward(selected.clone(), o.clone(), rules.clone(), ids[2])
            )
        });
        let a = a?;
        let b = b?;
        assert_eq!(a.count, 3);
        assert_eq!(b.count, 3);
        assert_ne!(a.reward_status, b.reward_status);
        assert_eq!(a.xp, 2 * rules.reward_xp as u64);
        assert_eq!(a.xp, b.xp);
        let result = rt.block_on(db.reward_status(selected.clone(), o.clone(), ids[0]))?;
        assert_eq!(result.count, 2);
        assert_eq!(result.xp, rules.reward_xp as u64);
        let mut stale = selected.clone();
        stale.generation += 1;
        assert!(rt
            .block_on(db.reward(stale, o.clone(), rules.clone(), ids[3]))
            .is_err());
        rt.block_on(db.save(o.clone(), vec![(selected.clone(), false)]))?;
        let new = rt.block_on(db.select(account, id, o.clone()))?;
        assert!(rt
            .block_on(db.reward(selected, o.clone(), rules.clone(), ids[3]))
            .is_err());
        assert_eq!(rt.block_on(db.inventory(new, o.clone(), rules))?.count, 3);
        c.execute("DELETE FROM characters WHERE realm=$1", &[&realm])?;
        c.execute("DELETE FROM accounts WHERE id=$1", &[&account])?;
        c.execute("DELETE FROM realm_ownership WHERE realm=$1", &[&realm])?;
        Ok(())
    }
}
