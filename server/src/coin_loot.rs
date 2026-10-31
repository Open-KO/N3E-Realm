//! Atomic generated currency pickup. No database work runs on the simulation tick.
use crate::{
    accounts::{Owner, Selected},
    content::{Result, bad},
    progression::Policy,
    wire,
};
use std::collections::BTreeSet;

pub fn stored(
    t: &mut postgres::Transaction<'_>,
    o: &Owner,
    operation: i64,
) -> Result<Vec<wire::CoinAward>> {
    Ok(t.query("SELECT character_id,name,nominal,added,balance,bag_revision FROM coin_claim_recipients WHERE realm=$1 AND claim_operation=$2 ORDER BY character_id",&[&o.realm,&operation])?.iter().map(|r|wire::CoinAward{
        character:r.get::<_,i64>(0) as u64,name:r.get(1),nominal:r.get::<_,i32>(2) as u32,
        added:r.get::<_,i32>(3) as u32,balance:r.get::<_,i32>(4) as u32,bag_revision:r.get::<_,i64>(5) as u64,
    }).collect())
}

fn canonical(
    operation: u64,
    encounter: u64,
    owner: i64,
    item: &str,
    quantity: u32,
) -> Result<Vec<u8>> {
    if operation == 0
        || operation > i64::MAX as u64
        || encounter == 0
        || encounter > i64::MAX as u64
        || owner <= 0
        || item.is_empty()
        || item.len() > 129
        || !(1..=32766).contains(&quantity)
    {
        return Err(bad("coin claim payload"));
    }
    let mut b = b"N3C2".to_vec();
    for v in [operation, encounter, owner as u64] {
        b.extend(v.to_le_bytes());
    }
    b.extend((item.len() as u32).to_le_bytes());
    b.extend(item.as_bytes());
    b.extend(quantity.to_le_bytes());
    Ok(b)
}

#[allow(clippy::too_many_arguments)]
pub fn claim(
    t: &mut postgres::Transaction<'_>,
    o: &Owner,
    current: &Policy,
    earned: &Policy,
    operation: u64,
    admission: Option<(&Selected, &wire::Claim, &str)>,
    routing: Option<(&crate::rules::Rules, &crate::party_loot::Admission)>,
    now: &dyn Fn() -> std::time::Instant,
) -> Result<wire::ClaimResult> {
    let op = operation as i64;
    let response = |status| crate::loot::response(operation, status);
    let drop=t.query_one("SELECT owner,encounter,item,quantity,zone,x,y,z,state,revision FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2 AND kind=1 FOR UPDATE",&[&o.realm,&op])?;
    let owner: i64 = drop.get(0);
    let encounter: i64 = drop.get(1);
    let item: String = drop.get(2);
    let amount = drop.get::<_, i32>(3) as u32;
    let policy = earned
        .coins
        .as_ref()
        .ok_or_else(|| bad("coin earned policy"))?;
    if policy.currency != item {
        return Err(bad("coin currency mismatch"));
    }
    let payload = canonical(operation, encounter as u64, owner, &item, amount)?;
    let requester = admission.map_or(owner, |a| a.0.id);
    if let Some((actor, q, _)) = admission {
        if !crate::loot::session(t,actor,o)? || t.query_opt("SELECT character_id FROM loot_audience WHERE realm=$1 AND claim_operation=$2 AND character_id=$3",&[&o.realm,&op,&actor.id])?.is_none() {return Ok(response("unknown"));}
        if canonical(q.operation, q.encounter, owner, &q.item, q.quantity)
            .ok()
            .as_ref()
            != Some(&payload)
        {
            return Ok(response("conflict"));
        }
    }
    if drop.get::<_, String>(8) != "available" {
        let old = t.query_one(
            "SELECT payload,digest FROM loot_claim_results WHERE realm=$1 AND claim_operation=$2",
            &[&o.realm, &op],
        )?;
        if old.get::<_, Vec<u8>>(0) != payload
            || old.get::<_, Vec<u8>>(1) != openssl::sha::sha256(&payload)
        {
            return Err(bad("coin claim history conflict"));
        }
        return crate::loot::stored(t, o, requester, op);
    }
    let mut expired:bool=t.query_one("SELECT clock_timestamp()>=expires_at FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])?.get(0);
    if admission.is_none() && !expired {
        return Ok(response("available"));
    }
    let mut wallets = Vec::new();
    let mut awards = Vec::new();
    if let Some((actor, _, zone)) = admission {
        let (rules, capture) = routing.ok_or_else(|| bad("coin admission missing"))?;
        let bag_policy = rules
            .inventory
            .as_ref()
            .ok_or_else(|| bad("coin inventory missing"))?;
        if bag_policy.currency != item {
            return Err(bad("coin inventory identity"));
        }
        if now().saturating_duration_since(capture.issued).as_secs_f32() > crate::party_loot::ADMISSION_WINDOW.as_secs_f32() {
            return Ok(response("stale_admission"));
        }
        if capture.group > i64::MAX as u64
            || (capture.group == 0
                && (capture.slots.len() != 1
                    || capture.slots[0].as_ref().map(|s| s.id) != Some(actor.id)))
            || (capture.group > 0 && !(2..=8).contains(&capture.slots.len()))
        {
            return Err(bad("coin party shape"));
        }
        let mut ids = BTreeSet::new();
        if capture
            .slots
            .iter()
            .flatten()
            .any(|s| s.id <= 0 || !ids.insert(s.id))
            || !ids.contains(&actor.id)
        {
            return Err(bad("coin party identities"));
        }
        let ids: Vec<_> = ids.into_iter().collect();
        let saved=t.query("SELECT id,session_generation,realm_generation,online,life_revision,dead FROM characters WHERE realm=$1 AND id=ANY($2) ORDER BY id FOR UPDATE",&[&o.realm,&ids])?;
        let live = |s: &Selected| {
            saved
                .iter()
                .find(|r| r.get::<_, i64>(0) == s.id)
                .is_some_and(|r| {
                    r.get::<_, i64>(1) == s.generation
                        && r.get::<_, i64>(2) == o.generation
                        && r.get::<_, bool>(3)
                        && r.get::<_, i64>(4) == s.life_revision
                        && !r.get::<_, bool>(5)
                        && !s.dead
                        && s.entity.health > 0
                })
        };
        if !live(actor) {
            return Ok(response("not_alive"));
        }
        let origin = [actor.entity.x, actor.entity.y, actor.entity.z];
        let distance: f64 = origin
            .iter()
            .enumerate()
            .map(|(i, x)| (*x as f64 - drop.get::<_, f32>(i + 5) as f64).powi(2))
            .sum();
        if drop.get::<_, String>(4) != zone
            || !distance.is_finite()
            || distance > (earned.claim_radius as f64).powi(2)
        {
            return Ok(response("out_of_range"));
        }
        if !expired {
            let rows=t.query("SELECT character_id,definition,curve_xp FROM character_reward_progress WHERE realm=$1 AND character_id=ANY($2) ORDER BY character_id FOR UPDATE",&[&o.realm,&ids])?;
            if rows.len() != ids.len()
                || rows.iter().any(|r| r.get::<_, Vec<u8>>(1) != current.hash)
            {
                return Err(bad("coin progress definition"));
            }
            let mut members = Vec::new();
            // ID order matches bag lock and immutable award order; physical slots do not rotate coins.
            for id in ids {
                let s = capture.slots.iter().flatten().find(|s| s.id == id).unwrap();
                if !live(s)
                    || !crate::party_loot::in_range(
                        origin,
                        [s.entity.x, s.entity.y, s.entity.z],
                        earned.party_loot.as_ref().unwrap().radius,
                    )
                {
                    continue;
                }
                let row = rows.iter().find(|r| r.get::<_, i64>(0) == id).unwrap();
                let bag = crate::inventory::load(t, s, o, bag_policy, &current.item)?;
                members.push(crate::party_loot::CoinMember {
                    id,
                    level: current.level(row.get::<_, i64>(2) as u64),
                    wallet: bag.coins,
                    bonus: false,
                });
                wallets.push((id, s.entity.name.clone(), bag));
            }
            if members.is_empty() {
                return Ok(response("not_alive"));
            }
            awards = crate::party_loot::coins(
                amount,
                &members,
                crate::party_loot::CoinPolicy {
                    bonus: policy.pickup_bonus_percent as f64 / 100.,
                    bonus_cap: policy.bonus_cap,
                    wallet_cap: bag_policy.limit,
                },
            )?;
        }
        if now().saturating_duration_since(capture.issued).as_secs_f32() > crate::party_loot::ADMISSION_WINDOW.as_secs_f32() {
            return Ok(response("stale_admission"));
        }
        expired=t.query_one("SELECT clock_timestamp()>=expires_at FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])?.get(0);
    }
    crate::loot::fault("before_mutation");
    if !expired {
        for ((id, _, bag), award) in wallets.iter_mut().zip(&awards) {
            bag.coins = award.wallet;
            bag.revision = bag
                .revision
                .checked_add(1)
                .ok_or_else(|| bad("coin bag revision exhausted"))?;
            crate::inventory::save(t, *id, bag)?;
        }
    }
    crate::loot::fault("during_mutation");
    let status = if expired { "expired" } else { "claimed" };
    t.execute("INSERT INTO loot_claim_results(realm,claim_operation,encounter,owner,payload,digest,status,result_count,revision) VALUES($1,$2,$3,$4,$5,$6,$7,0,0)",&[&o.realm,&op,&encounter,&owner,&payload,&&openssl::sha::sha256(&payload)[..],&status])?;
    if !expired {
        for ((id, name, bag), award) in wallets.iter().zip(&awards) {
            t.execute(
                "INSERT INTO coin_claim_recipients VALUES($1,$2,$3,$4,$5,$6,$7,$8)",
                &[
                    &o.realm,
                    &op,
                    id,
                    name,
                    &(award.nominal as i32),
                    &(award.added as i32),
                    &(award.wallet as i32),
                    &(bag.revision as i64),
                ],
            )?;
        }
    }
    let revision = drop
        .get::<_, i64>(9)
        .checked_add(1)
        .ok_or_else(|| bad("coin entitlement revision exhausted"))?;
    t.execute("UPDATE loot_entitlements SET state=$3,revision=$4,result_operation=claim_operation WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op,&status,&revision])?;
    crate::loot::stored(t, o, requester, op)
}
