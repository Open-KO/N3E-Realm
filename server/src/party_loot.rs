//! Party loot arithmetic and physical-slot routing.
//! Binary grounding and scoped corrections: content/party-loot.md.
use crate::content::{Result, bad};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug)]
pub struct Policy {
    pub radius: u32,
}
impl Policy {
    pub fn validate(&self) -> Result<()> {
        if !(1..=100).contains(&self.radius) {
            return Err(bad("party loot radius"));
        }
        Ok(())
    }
}

/// Positions subtract as f32, then square/sum/sqrt as f64; altitude is ignored.
pub fn in_range(a: [f32; 3], b: [f32; 3], radius: u32) -> bool {
    let x = (a[0] - b[0]) as f64;
    let z = (a[2] - b[2]) as f64;
    let distance = (x * x + z * z).sqrt();
    distance.is_finite() && distance.trunc() <= radius as f64
}

#[derive(Clone, Copy, Debug)]
pub struct Credit {
    pub id: i64,
    pub amount: u64,
    /// Independently resolved identity/range, not recipient life eligibility.
    pub valid: bool,
    pub group: Option<u64>,
}

/// The first valid contributor to the greatest-credit party/solo receives notice.
/// Strict greater-than retains the first damage entry on equal totals.
pub fn winner(ordered: &[Credit]) -> Result<Option<i64>> {
    let mut seen = BTreeSet::new();
    let mut groups = BTreeMap::<u64, (usize, u64)>::new();
    let mut total = 0u64;
    if ordered.len() > 64 {
        return Err(bad("loot contribution count"));
    }
    for c in ordered {
        if c.id <= 0 || c.amount == 0 || c.group == Some(0) || !seen.insert(c.id) {
            return Err(bad("loot contribution identity"));
        }
        total = total
            .checked_add(c.amount)
            .ok_or_else(|| bad("loot credit overflow"))?;
        if total > crate::progression::CREDIT_LIMIT {
            return Err(bad("loot credit bound"));
        }
        if let Some(group) = c.group {
            if group > i64::MAX as u64 {
                return Err(bad("loot party identity"));
            }
            let (members, credit) = groups.entry(group).or_default();
            *members += 1;
            if *members > 8 {
                return Err(bad("loot party size"));
            }
            if c.valid {
                *credit += c.amount;
            }
        }
    }
    let mut maximum = 0;
    let mut owner = None;
    for c in ordered.iter().filter(|c| c.valid) {
        let credit = c.group.map_or(c.amount, |g| groups[&g].1);
        if credit > maximum {
            maximum = credit;
            owner = Some(c.id);
        }
    }
    Ok(owner)
}

pub fn settlement_owner(
    rows: &[crate::progression::Recipient],
    groups: &[crate::party_rewards::Group],
    order: &[i64],
) -> Result<Option<i64>> {
    let positive: BTreeSet<_> = rows.iter().filter(|r| r.credit > 0).map(|r| r.id).collect();
    if order.len() != positive.len() || order.iter().copied().collect::<BTreeSet<_>>() != positive {
        return Err(bad("loot contribution order"));
    }
    let index: BTreeMap<_, _> = rows.iter().map(|r| (r.id, r)).collect();
    let mut membership = BTreeMap::new();
    for g in groups {
        for id in &g.members {
            if membership.insert(*id, g).is_some() {
                return Err(bad("loot duplicate membership"));
            }
        }
    }
    let credits: Vec<_> = order
        .iter()
        .map(|id| {
            let r = index[id];
            let group = membership.get(id);
            Credit {
                id: *id,
                amount: r.credit,
                valid: group.map_or(r.reason == 0, |g| g.credited.contains(id)),
                group: group.map(|g| g.id),
            }
        })
        .collect();
    winner(&credits)
}

#[derive(Clone, Copy, Debug)]
pub struct Candidate {
    pub id: i64,
    /// Live accepted same-group member, alive, in zone/range, inventory accessible.
    pub eligible: bool,
    /// Whole incoming quantity fits actual stack, bag and carry limits.
    pub fits: bool,
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Route {
    pub recipient: Option<i64>,
    pub next: usize,
}
/// A bounded scan over physical slots, including the eighth slot and holes.
/// Callers publish the cursor only with the corresponding committed transaction.
pub fn route(slots: &[Option<Candidate>], cursor: usize) -> Result<Route> {
    if !(2..=8).contains(&slots.len()) || cursor >= slots.len() {
        return Err(bad("loot routing bounds"));
    }
    let mut seen = BTreeSet::new();
    if slots
        .iter()
        .flatten()
        .any(|c| c.id <= 0 || !seen.insert(c.id))
    {
        return Err(bad("loot routing identities"));
    }
    let mut next = cursor;
    for _ in 0..slots.len() * 2 {
        let candidate = slots[next];
        next = (next + 1) % slots.len();
        if let Some(c) = candidate.filter(|c| c.eligible && c.fits) {
            return Ok(Route {
                recipient: Some(c.id),
                next,
            });
        }
    }
    Ok(Route {
        recipient: None,
        next,
    })
}

#[derive(Clone, Copy, Debug)]
pub struct CoinPolicy {
    pub bonus: f64,
    pub bonus_cap: u32,
    pub wallet_cap: u32,
}
impl CoinPolicy {
    pub fn validate(&self) -> Result<()> {
        if !self.bonus.is_finite()
            || !(0.0..=1.0).contains(&self.bonus)
            || !(1..=32766).contains(&self.bonus_cap)
            || !(1..=i32::MAX as u32).contains(&self.wallet_cap)
        {
            return Err(bad("loot coin policy bounds"));
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug)]
pub struct CoinMember {
    pub id: i64,
    pub level: u32,
    pub wallet: u32,
    pub bonus: bool,
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CoinAward {
    pub id: i64,
    pub nominal: u32,
    pub added: u32,
    pub wallet: u32,
}
/// Input contains only alive, accepted, same-zone members within pickup-party range.
/// Trade/inventory UI blocks do not exclude coin recipients in the reference.
pub fn coins(amount: u32, members: &[CoinMember], policy: CoinPolicy) -> Result<Vec<CoinAward>> {
    policy.validate()?;
    if !(1..=32766).contains(&amount) || members.len() > 8 {
        return Err(bad("loot coin amount/party size"));
    }
    let mut seen = BTreeSet::new();
    if members.iter().any(|m| {
        m.id <= 0
            || !seen.insert(m.id)
            || !(1..=255).contains(&m.level)
            || m.wallet > policy.wallet_cap
    }) {
        return Err(bad("loot coin member bounds"));
    }
    let levels: u32 = members.iter().map(|m| m.level).sum();
    Ok(members
        .iter()
        .map(|m| {
            // Preserve binary divide-then-multiply and truncation before the bonus.
            let share = ((m.level as f64 / levels as f64) * amount as f64).trunc();
            let nominal = if m.bonus {
                ((share + share * policy.bonus).trunc() as u32).min(policy.bonus_cap)
            } else {
                share as u32
            };
            let added = nominal.min(policy.wallet_cap - m.wallet);
            CoinAward {
                id: m.id,
                nominal,
                added,
                wallet: m.wallet + added,
            }
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn physical_slots_capacity_and_altitude() -> Result<()> {
        let mut slots = vec![None; 8];
        slots[0] = Some(Candidate {
            id: 1,
            eligible: true,
            fits: false,
        });
        slots[3] = Some(Candidate {
            id: 2,
            eligible: false,
            fits: true,
        });
        slots[7] = Some(Candidate {
            id: 3,
            eligible: true,
            fits: true,
        });
        assert_eq!(
            route(&slots, 0)?,
            Route {
                recipient: Some(3),
                next: 0
            }
        );
        slots[7].as_mut().unwrap().fits = false;
        assert_eq!(
            route(&slots, 5)?,
            Route {
                recipient: None,
                next: 5
            }
        );
        assert!(route(&slots, 8).is_err());
        slots[7].as_mut().unwrap().id = 1;
        assert!(route(&slots, 0).is_err());
        assert!(in_range([0., -1e6, 0.], [50.9, 1e6, 0.], 50));
        assert!(!in_range([0.; 3], [51., 0., 0.], 50));
        assert!(!in_range([0.; 3], [f32::NAN, 0., 0.], 50));
        assert!(!in_range([f32::MAX, 0., 0.], [-f32::MAX, 0., 0.], 50));
        Ok(())
    }
    #[test]
    fn greatest_group_first_credit_and_invalid_identity() -> Result<()> {
        let mut credits = vec![
            Credit {
                id: 9,
                amount: 40,
                valid: true,
                group: None,
            },
            Credit {
                id: 7,
                amount: 20,
                valid: true,
                group: Some(2),
            },
            Credit {
                id: 3,
                amount: 30,
                valid: true,
                group: Some(2),
            },
        ];
        assert_eq!(winner(&credits)?, Some(7));
        credits[2].amount = 20;
        assert_eq!(winner(&credits)?, Some(9));
        credits.swap(0, 1);
        assert_eq!(winner(&credits)?, Some(7));
        credits[0].valid = false;
        assert_eq!(winner(&credits)?, Some(9));
        credits[2].valid = false;
        credits[1].valid = false;
        assert_eq!(winner(&credits)?, None);
        credits[0].id = credits[1].id;
        assert!(winner(&credits).is_err());
        Ok(())
    }
    #[test]
    fn coin_rounding_bonus_cap_and_wallet_saturation() -> Result<()> {
        let policy = CoinPolicy {
            bonus: 0.3,
            bonus_cap: 32700,
            wallet_cap: 2_100_000_000,
        };
        let mut members = [
            CoinMember {
                id: 1,
                level: 1,
                wallet: 0,
                bonus: false,
            },
            CoinMember {
                id: 2,
                level: 2,
                wallet: 0,
                bonus: true,
            },
        ];
        let award = coins(10, &members, policy)?;
        assert_eq!(award[0].added, 3);
        assert_eq!(award[1].added, 7); // trunc(6 + 6*0.3), not trunc(10*2/3*1.3)
        members[1].wallet = 2_099_999_999;
        assert_eq!(
            coins(10, &members, policy)?[1],
            CoinAward {
                id: 2,
                nominal: 7,
                added: 1,
                wallet: 2_100_000_000
            }
        );
        assert_eq!(coins(32766, &members[1..], policy)?[0].nominal, 32700);
        assert!(coins(10, &[], policy)?.is_empty());
        assert!(coins(32767, &members, policy).is_err());
        assert!(
            coins(
                10,
                &members,
                CoinPolicy {
                    bonus: f64::NAN,
                    ..policy
                }
            )
            .is_err()
        );
        // Binary f64 division/multiplication rounds this share below its exact integer.
        members[0].level = 29;
        members[1].level = 71;
        assert_eq!(coins(100, &members, policy)?[0].nominal, 28);
        Ok(())
    }
}

/// How long a routed claim's party admission stays valid: checked when the claim starts
/// and again before it mutates (D-132 lists it among the wall-time admission windows).
/// Coin claims use the same window (`coin_loot::claim`).
pub const ADMISSION_WINDOW: std::time::Duration = std::time::Duration::from_secs(2);
/// Captured on the simulation tick; never constructed from network member IDs.
#[derive(Clone)]
pub struct Admission {
    pub issued: std::time::Instant,
    pub group: u64,
    pub slots: Vec<Option<crate::accounts::Selected>>,
}

#[allow(clippy::too_many_arguments)]
pub fn claim(
    t: &mut postgres::Transaction<'_>,
    o: &crate::accounts::Owner,
    rules: &crate::rules::Rules,
    current: &crate::progression::Policy,
    earned: &crate::progression::Policy,
    actor: &crate::accounts::Selected,
    q: &crate::wire::Claim,
    zone: &str,
    admission: &Admission,
    now: &dyn Fn() -> std::time::Instant,
) -> Result<crate::wire::ClaimResult> {
    use crate::{inventory, loot};
    let op = q.operation as i64;
    let response = |status| loot::response(q.operation, status);
    if now().saturating_duration_since(admission.issued).as_secs_f32() > ADMISSION_WINDOW.as_secs_f32() {
        return Ok(response("stale_admission"));
    }
    if admission.group > i64::MAX as u64
        || (admission.group == 0
            && (admission.slots.len() != 1
                || admission.slots[0].as_ref().map(|s| s.id) != Some(actor.id)))
        || (admission.group > 0
            && (!(2..=8).contains(&admission.slots.len())
                || !admission.slots.iter().flatten().any(|s| s.id == actor.id)))
    {
        return Err(bad("party loot admission bounds"));
    }
    let mut ids = BTreeSet::new();
    if admission
        .slots
        .iter()
        .flatten()
        .any(|s| s.id <= 0 || !ids.insert(s.id))
    {
        return Err(bad("party loot admission identities"));
    }
    if !loot::session(t,actor,o)? || t.query_opt("SELECT character_id FROM loot_audience WHERE realm=$1 AND claim_operation=$2 AND character_id=$3",&[&o.realm,&op,&actor.id])?.is_none() {
        return Ok(response("unknown"));
    }
    let drop=t.query_one("SELECT owner,encounter,item,zone,x,y,z,state,revision,kind,quantity,durability FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2 FOR UPDATE",&[&o.realm,&op])?;
    let owner: i64 = drop.get(0);
    let encounter: i64 = drop.get(1);
    let item: String = drop.get(2);
    let general=drop.get::<_,i32>(9)==2;
    let quantity=drop.get::<_,i32>(10) as u32;
    let durability=drop.get::<_,i32>(11) as u32;
    if general && earned.items.as_ref().is_none_or(|p|p.items.iter().all(|i|i.id!=item||i.quantity!=quantity||i.durability!=durability)) {return Err(bad("earned item drop definition"));}
    let payload_for=|operation,encounter,item:&str,quantity|if general {crate::item_drops::claim_payload(operation,encounter,owner,item,quantity,durability)} else {loot::canonical(operation,encounter,owner,item,quantity)};
    let payload=payload_for(q.operation,encounter as u64,&item,quantity)?;
    if payload_for(q.operation, q.encounter, &q.item, q.quantity)
        .ok()
        .as_ref()
        != Some(&payload)
    {
        return Ok(response("conflict"));
    }
    if drop.get::<_, String>(7) != "available" {
        let history = t.query_one(
            "SELECT payload,digest FROM loot_claim_results WHERE realm=$1 AND claim_operation=$2",
            &[&o.realm, &op],
        )?;
        if history.get::<_, Vec<u8>>(0) != payload
            || history.get::<_, Vec<u8>>(1) != openssl::sha::sha256(&payload)
        {
            return Err(bad("party claim history payload conflict"));
        }
        return loot::stored(t, o, actor.id, op);
    }
    ids.insert(owner);
    ids.insert(actor.id);
    let ids: Vec<_> = ids.into_iter().collect();
    let saved=t.query("SELECT id,session_generation,realm_generation,online,life_revision,dead FROM characters WHERE realm=$1 AND id=ANY($2) ORDER BY id FOR UPDATE",&[&o.realm,&ids])?;
    let live = |s: &crate::accounts::Selected| {
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
        .map(|(i, v)| (*v as f64 - drop.get::<_, f32>(i + 4) as f64).powi(2))
        .sum();
    if drop.get::<_, String>(3) != zone
        || !distance.is_finite()
        || distance > (earned.claim_radius as f64).powi(2)
    {
        return Ok(response("out_of_range"));
    }
    let mut expired:bool=t.query_one("SELECT clock_timestamp()>=expires_at FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])?.get(0);
    let progress=t.query("SELECT p.character_id,p.count,p.capacity,p.item,r.revision,r.definition,r.curve_xp FROM character_progress p JOIN character_reward_progress r USING(character_id) WHERE r.realm=$1 AND p.character_id=ANY($2) ORDER BY p.character_id FOR UPDATE OF p,r",&[&o.realm,&ids])?;
    if progress.len() != ids.len()
        || progress.iter().any(|r| {
            r.get::<_, Vec<u8>>(5) != current.hash
                || r.get::<_, String>(3) != current.item
                || r.get::<_, i32>(2) != current.capacity as i32
        })
    {
        return Err(bad("party loot progress definition"));
    }
    let mut cursor = 0usize;
    let mut next = 0usize;
    let mut recipient = owner;
    if !expired {
        if admission.group > 0 {
            t.execute(
                "INSERT INTO party_loot_cursors VALUES($1,$2,$3,0,0) ON CONFLICT DO NOTHING",
                &[&o.realm, &o.generation, &(admission.group as i64)],
            )?;
            cursor=t.query_one("SELECT cursor FROM party_loot_cursors WHERE realm=$1 AND generation=$2 AND party=$3 FOR UPDATE",&[&o.realm,&o.generation,&(admission.group as i64)])?.get::<_,i32>(0) as usize;
        }
        let mut candidates = Vec::new();
        for member in &admission.slots {
            let Some(s) = member else {
                candidates.push(None);
                continue;
            };
            let eligible = live(s)
                && in_range(
                    origin,
                    [s.entity.x, s.entity.y, s.entity.z],
                    earned.party_loot.as_ref().unwrap().radius,
                );
            let row = progress
                .iter()
                .find(|r| r.get::<_, i64>(0) == s.id)
                .unwrap();
            let mut fits = item!=current.item || row.get::<_,i32>(1).checked_add(quantity as i32).is_some_and(|n|n<=row.get::<_,i32>(2));
            if eligible && fits {
                if let Some(p) = &rules.inventory {
                    let bag = inventory::load(t, s, o, p, &current.item)?;
                    fits = if general {let definition=p.items.iter().find(|d|d.id==item).ok_or_else(||bad("drop bag definition"))?;
                        inventory::drop_slot(&bag,&item,quantity,definition.stack).is_some()
                    }else{bag.slots.iter().any(|s| s.instance==0)};
                    if let Some(commerce) = &rules.commerce {
                        let weight: u64 = bag
                            .slots
                            .iter()
                            .chain(&bag.equipment)
                            .map(|s| {
                                commerce
                                    .items
                                    .iter()
                                    .find(|i| i.item == s.item)
                                    .map_or(0, |i| i.weight as u64 * s.quantity as u64)
                            })
                            .sum();
                        let added = commerce
                            .items
                            .iter()
                            .find(|i| i.item == item)
                            .ok_or_else(|| bad("loot weight definition"))?
                            .weight as u64 * quantity as u64;
                        let limit = if let Some(stats) = &p.stats {
                            stats
                                .calculate(
                                    p.equipment.as_ref().unwrap(),
                                    &bag.equipment,
                                    current.level(row.get::<_, i64>(6) as u64),
                                )?
                                .carry_limit
                        } else {
                            commerce.weight_limit
                        };
                        fits &= weight + added <= limit as u64;
                    }
                }
            }
            candidates.push(Some(Candidate {
                id: s.id,
                eligible,
                fits,
            }));
        }
        let selected = if admission.group == 0 {
            candidates[0]
                .filter(|c| c.eligible && c.fits)
                .map(|c| Route {
                    recipient: Some(c.id),
                    next: 0,
                })
                .unwrap_or(Route {
                    recipient: None,
                    next: 0,
                })
        } else {
            route(&candidates, cursor)?
        };
        let Some(id) = selected.recipient else {
            return Ok(response("inventory_full_not_committed"));
        };
        recipient = id;
        next = selected.next;
    }
    if now().saturating_duration_since(admission.issued).as_secs_f32() > ADMISSION_WINDOW.as_secs_f32() {
        return Ok(response("stale_admission"));
    }
    if !expired {
        expired=t.query_one("SELECT clock_timestamp()>=expires_at FROM loot_entitlements WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op])?.get(0);
    }
    if expired {
        recipient = owner;
    }
    let row = progress
        .iter()
        .find(|r| r.get::<_, i64>(0) == recipient)
        .unwrap();
    let count = row.get::<_, i32>(1) + if expired || item!=current.item { 0 } else { quantity as i32 };
    let revision = row
        .get::<_, i64>(4)
        .checked_add(if expired { 0 } else { 1 })
        .ok_or_else(|| bad("party loot revision exhausted"))?;
    loot::fault("before_mutation");
    if !expired {
        let granted=if general {
            let definition=rules.inventory.as_ref().ok_or_else(||bad("drop bag missing"))?.items.iter().find(|d|d.id==item).ok_or_else(||bad("drop item missing"))?;
            inventory::grant_drop(t,&o.realm,recipient,&item,quantity,durability,definition.stack)?
        }else{inventory::grant_existing(t, &o.realm, recipient, &item)?};
        if !granted {
            return Err(bad("party loot admitted bag changed"));
        }
        t.execute(
            "UPDATE character_progress SET count=$2 WHERE character_id=$1",
            &[&recipient, &count],
        )?;
        t.execute(
            "UPDATE character_reward_progress SET revision=$2 WHERE character_id=$1",
            &[&recipient, &revision],
        )?;
    }
    loot::fault("during_mutation");
    let status = if expired { "expired" } else { "claimed" };
    t.execute("INSERT INTO loot_claim_results(realm,claim_operation,encounter,owner,payload,digest,status,result_count,revision) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",&[&o.realm,&op,&encounter,&owner,&payload,&&openssl::sha::sha256(&payload)[..],&status,&count,&revision])?;
    let entitlement_revision = drop
        .get::<_, i64>(8)
        .checked_add(1)
        .ok_or_else(|| bad("party entitlement revision exhausted"))?;
    t.execute("UPDATE loot_entitlements SET state=$3,revision=$4,result_operation=claim_operation WHERE realm=$1 AND claim_operation=$2",&[&o.realm,&op,&status,&entitlement_revision])?;
    if !expired {
        let name = admission
            .slots
            .iter()
            .flatten()
            .find(|s| s.id == recipient)
            .unwrap()
            .entity
            .name
            .clone();
        t.execute(
            "INSERT INTO party_loot_claims VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            &[
                &o.realm,
                &op,
                &actor.id,
                &recipient,
                &o.generation,
                &(admission.group as i64),
                &(cursor as i32),
                &(next as i32),
                &name,
            ],
        )?;
        if admission.group > 0 {
            t.execute("UPDATE party_loot_cursors SET cursor=$4,revision=revision+1 WHERE realm=$1 AND generation=$2 AND party=$3",&[&o.realm,&o.generation,&(admission.group as i64),&(next as i32)])?;
        }
    }
    loot::stored(t, o, actor.id, op)
}
