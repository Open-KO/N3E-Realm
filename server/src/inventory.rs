//! Durable inventory moves, compatible stack merges and whole-record swaps. Database work stays off the simulation tick.
use crate::{
    accounts::{Database, Owner, Selected},
    content::{bad, Reader, Result},
    persistence, wire,
};
use prost::Message;
use std::{collections::BTreeSet, path::Path, sync::Arc};
#[derive(Clone, Debug)]
pub struct Item {
    pub id: String,
    pub label: String,
    pub stack: u32,
    pub durability: u32,
    pub starting: u32,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub storage: Option<crate::storage::Policy>,
    pub wear: Option<crate::wear::Policy>,
    pub stats: Option<crate::stats::Policy>,
    pub thresholds: Option<[u64;10]>,
    pub equipment: Option<crate::equipment::Policy>,
    pub capacity: u32,
    pub currency: String,
    pub limit: u32,
    pub coins: u32,
    pub items: Vec<Item>,
    pub hash: Vec<u8>,
}
pub(crate) fn id(s: &str, game: &str) -> bool {
    s.strip_prefix(&format!("{game}:")).is_some_and(|v| {
        !v.is_empty()
            && v.len() <= 96
            && v.as_bytes()[0].is_ascii_lowercase()
            && v.bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"_/-".contains(&c))
    })
}
impl Policy {
    pub fn load(path: &Path, game: &str) -> Result<Self> {
        let mut r = Reader::open(path)?;
        let hash = openssl::sha::sha256(&r.bytes).to_vec();
        if r.take(4)? != b"N3I1" {
            return Err(bad("inventory magic"));
        }
        let capacity = r.u()?;
        let currency = r.string()?;
        let limit = r.u()?;
        let coins = r.u()?;
        let n = r.u()?;
        if !(1..=64).contains(&capacity)
            || !id(&currency, game)
            || !(1..=i32::MAX as u32).contains(&limit)
            || coins > limit
            || !(1..=64).contains(&n)
        {
            return Err(bad("inventory bounds"));
        }
        let mut items = Vec::new();
        let mut seen = BTreeSet::new();
        for _ in 0..n {
            let item = Item {
                id: r.string()?,
                label: r.string()?,
                stack: r.u()?,
                durability: r.u()?,
                starting: r.u()?,
            };
            if !id(&item.id, game)
                || !seen.insert(item.id.clone())
                || item.label.is_empty()
                || item.label.len() > 64
                || !item.label.bytes().all(|c| (32..=126).contains(&c))
                || !(1..=9999).contains(&item.stack)
                || item.durability > 65535
                || item.starting > item.stack
            {
                return Err(bad("item definition"));
            }
            items.push(item);
        }
        r.end()?;
        if items.iter().filter(|i| i.starting > 0).count() >= capacity as usize {
            return Err(bad("inventory starting capacity"));
        }
        Ok(Self {
            storage: None,
            wear: None, stats: None, thresholds: None,
            equipment: None,
            capacity,
            currency,
            limit,
            coins,
            items,
            hash,
        })
    }
    pub fn validate_reward(&self, reward: &str, count: u32) -> Result<()> {
        if !self
            .items
            .iter()
            .any(|i| i.id == reward && i.stack == 1 && i.starting == 0 && i.durability == 0)
            || self.items.iter().filter(|i| i.starting > 0).count() + count as usize
                > self.capacity as usize
        {
            return Err(bad("inventory reward compatibility"));
        }
        Ok(())
    }
    pub(crate) fn validate(&self, s: &wire::BagState) -> Result<()> {
        basic(s)?;
        if s.capacity != self.capacity || s.currency != self.currency || s.coins > self.limit {
            return Err(bad("durable inventory policy conflict"));
        }
        if let Some(p) = &self.equipment {
            p.validate(s)?;
            if let Some(stats)=&self.stats {for level in 1..=10 {stats.calculate(p,&s.equipment,level)?;}}
        } else if !s.equipment.is_empty() {
            return Err(bad("unexpected equipment"));
        }
        for slot in s
            .slots
            .iter()
            .chain(&s.equipment)
            .filter(|s| s.instance != 0)
        {
            if !self.items.iter().any(|i| {
                i.id == slot.item && slot.quantity <= i.stack && slot.durability <= i.durability
            }) {
                return Err(bad("durable item definition conflict"));
            }
        }
        Ok(())
    }
}
fn basic(s: &wire::BagState) -> Result<()> {
    let mut serials = BTreeSet::new();
    if !(1..=64).contains(&s.capacity)
        || s.slots.len() != s.capacity as usize
        || s.revision > i64::MAX as u64
        || s.currency.is_empty()
        || s.currency.len() > 129
        || s.coins > i32::MAX as u32
    {
        return Err(bad("bag state bounds"));
    }
    if s.equipment.len() > 16 {
        return Err(bad("equipment bound"));
    }
    for slot in s.slots.iter().chain(&s.equipment) {
        if slot.instance == 0 {
            if !slot.item.is_empty() || slot.quantity != 0 || slot.durability != 0 {
                return Err(bad("nonempty vacant slot"));
            }
        } else if slot.instance > i64::MAX as u64
            || !serials.insert(slot.instance)
            || slot.item.is_empty()
            || slot.item.len() > 129
            || !(1..=9999).contains(&slot.quantity)
            || slot.durability > 65535
        {
            return Err(bad("item state bounds"));
        }
    }
    Ok(())
}
pub(crate) fn serial(t: &mut postgres::Transaction<'_>) -> Result<u64> {
    Ok(t.query_one("SELECT nextval('item_instances')", &[])?
        .get::<_, i64>(0) as u64)
}
pub(crate) fn save(t: &mut postgres::Transaction<'_>, actor: i64, state: &wire::BagState) -> Result<()> {
    basic(state)?;
    let bytes = state.encode_to_vec();
    t.execute(
        "UPDATE character_bags SET state=$2 WHERE character_id=$1",
        &[&actor, &bytes],
    )?;
    Ok(())
}
pub(crate) fn load(
    t: &mut postgres::Transaction<'_>,
    s: &Selected,
    o: &Owner,
    p: &Policy,
    reward: &str,
) -> Result<wire::BagState> {
    if let Some(row) = t.query_opt(
        "SELECT definition,state FROM character_bags WHERE character_id=$1 AND realm=$2 FOR UPDATE",
        &[&s.id, &o.realm],
    )? {
        if row.get::<_, Vec<u8>>(0) != p.hash {
            return Err(bad("durable inventory definition conflict"));
        }
        let state = wire::BagState::decode(row.get::<_, Vec<u8>>(1).as_slice())?;
        p.validate(&state)?;
        return Ok(state);
    }
    let row = t.query_one(
        "SELECT item,count FROM character_progress WHERE character_id=$1 FOR UPDATE",
        &[&s.id],
    )?;
    let count = row.get::<_, i32>(1) as u32;
    if row.get::<_, String>(0) != reward {
        return Err(bad("inventory reward identity"));
    }
    p.validate_reward(reward, count)?;
    let mut slots = Vec::new();
    for item in &p.items {
        if item.starting > 0 {
            slots.push(wire::ItemStack {
                instance: serial(t)?,
                item: item.id.clone(),
                quantity: item.starting,
                durability: item.durability,
            });
        }
    }
    let durability = p.items.iter().find(|i| i.id == reward).unwrap().durability;
    for _ in 0..count {
        slots.push(wire::ItemStack {
            instance: serial(t)?,
            item: reward.into(),
            quantity: 1,
            durability,
        });
    }
    slots.resize(p.capacity as usize, wire::ItemStack::default());
    let state = wire::BagState {
        revision: 0,
        capacity: p.capacity,
        currency: p.currency.clone(),
        coins: p.coins,
        slots,
        equipment: vec![
            wire::ItemStack::default();
            p.equipment.as_ref().map_or(0, |p| p.slots.len())
        ],
    };
    p.validate(&state)?;
    t.execute(
        "INSERT INTO character_bags(character_id,realm,definition,state) VALUES($1,$2,$3,$4)",
        &[&s.id, &o.realm, &p.hash, &state.encode_to_vec()],
    )?;
    Ok(state)
}
pub fn check_start(c: &mut postgres::Client, realm: &str, p: Option<&Policy>) -> Result<()> {
    crate::storage::check_start(c, realm, p)?;
    let hashes = c.query(
        "SELECT DISTINCT definition FROM character_bags WHERE realm=$1",
        &[&realm],
    )?;
    if hashes
        .iter()
        .any(|r| p.is_none_or(|p| r.get::<_, Vec<u8>>(0) != p.hash))
    {
        return Err(bad(
            "incompatible durable inventory; explicit migration required",
        ));
    }
    Ok(())
}
/// A claim and its item record commit together. Uninitialized bags are materialized
/// later from the already-durable aggregate, so no acknowledged item can be lost.
pub fn grant_existing(
    t: &mut postgres::Transaction<'_>,
    realm: &str,
    actor: i64,
    item: &str,
) -> Result<bool> {
    let Some(row) = t.query_opt(
        "SELECT state FROM character_bags WHERE character_id=$1 AND realm=$2 FOR UPDATE",
        &[&actor, &realm],
    )?
    else {
        return Ok(true);
    };
    let mut state = wire::BagState::decode(row.get::<_, Vec<u8>>(0).as_slice())?;
    basic(&state)?;
    let Some(slot) = state.slots.iter_mut().find(|i| i.instance == 0) else {
        return Ok(false);
    };
    // Reward item policy is constrained to singleton zero-durability tokens until
    // general drop definitions carry their own frozen durability metadata.
    *slot = wire::ItemStack {
        instance: serial(t)?,
        item: item.into(),
        quantity: 1,
        durability: 0,
    };
    state.revision = state
        .revision
        .checked_add(1)
        .ok_or_else(|| bad("bag revision overflow"))?;
    save(t, actor, &state)?;
    Ok(true)
}
pub fn execute(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    p: &Policy,
    reward: &str,
    q: &wire::BagRequest,
) -> Result<wire::BagResult> {
    execute_inner(c, o, s, p, reward, q, None)
}
/// Merge identical stackable records without changing their durability or minting
/// identities. The consumed source slot guarantees capacity for any remainder.
/// Nonmatching records retain the ordinary swap behavior.
pub fn move_or_merge(slots: &mut [wire::ItemStack], source: usize, destination: usize, policy: &Policy) {
    let a = &slots[source];
    let b = &slots[destination];
    let limit = policy.items.iter().find(|i| i.id == a.item).map_or(1, |i| i.stack);
    if source != destination && a.instance != 0 && b.instance != 0 && limit > 1
        && a.item == b.item && a.durability == b.durability {
        let mut remainder = std::mem::take(&mut slots[source]);
        let total = slots[destination].quantity + remainder.quantity;
        slots[destination].quantity = total.min(limit);
        if total > limit {
            remainder.quantity = total - limit;
            let empty = slots.iter().position(|i| i.instance == 0).unwrap();
            slots[empty] = remainder;
        }
    } else {
        slots.swap(source, destination);
    }
}

pub fn execute_inner(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    p: &Policy,
    reward: &str,
    q: &wire::BagRequest,
    commerce: Option<(&crate::commerce::Policy, &crate::commerce::Admission)>,
) -> Result<wire::BagResult> {
    execute_inner_at(c, o, s, p, reward, q, commerce, &std::time::Instant::now)
}
/// `execute_inner` with the clock that ages a merchant admission, read at the admission
/// check and again just before COMMIT. Production passes `Instant::now`; tests pass a
/// fixed clock so the window, not database speed, decides fresh and expired (PQ-291).
#[allow(clippy::too_many_arguments)]
pub(crate) fn execute_inner_at(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    p: &Policy,
    reward: &str,
    q: &wire::BagRequest,
    commerce: Option<(&crate::commerce::Policy, &crate::commerce::Admission)>,
    now: &dyn Fn() -> std::time::Instant,
) -> Result<wire::BagResult> {
    let gear = (5..=7).contains(&q.operation);
    let repairing = matches!(q.operation, 4 | 8);
    if q.operation > 8
        || (q.operation == 8 && p.equipment.is_none())
        || (gear && p.equipment.is_none())
        || (gear && (!q.service.is_empty() || !q.item.is_empty() || q.quantity != 0))
        || (((2..=4).contains(&q.operation) || q.operation == 8) && commerce.is_none())
        || (q.operation <= 1 && (!q.service.is_empty() || !q.item.is_empty() || q.quantity != 0))
        || (((2..=4).contains(&q.operation) || q.operation == 8)
            && (q.destination != 0
                || q.service.len() > 129
                || q.item.len() > 129
                || (!repairing && q.quantity == 0)))
        || (repairing && (!q.service.is_empty() || q.quantity != 0))
        || (q.operation == 0
            && (!q.request.is_empty()
                || q.expected_revision != 0
                || q.source != 0
                || q.destination != 0
                || q.instance != 0))
        || (q.operation != 0
            && (!crate::accounts::valid_name(&q.request, 64)
                || q.expected_revision > i64::MAX as u64
                || (q.operation != 2 && q.instance == 0)
                || q.instance > i64::MAX as u64))
    {
        return Err(bad("invalid bag request"));
    }
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if t.query_opt("SELECT id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE", &[&s.id,&o.realm,&s.generation,&o.generation])?.is_none() {return Err(bad("stale bag session"));}
    let mut state = load(&mut t, s, o, p, reward)?;
    let payload = q.encode_to_vec();
    if q.operation != 0 {
        if let Some(row) = t.query_opt(
            "SELECT payload,result FROM bag_operations WHERE character_id=$1 AND request=$2",
            &[&s.id, &q.request],
        )? {
            return if row.get::<_, Vec<u8>>(0) == payload {
                Ok(wire::BagResult::decode(
                    row.get::<_, Vec<u8>>(1).as_slice(),
                )?)
            } else {
                Ok(wire::BagResult {
                    request: q.request.clone(),
                    status: "request_conflict".into(),
                    state: Some(state),
                })
            };
        }
    }
    if let Some((policy, admission)) = commerce {
        if now().saturating_duration_since(admission.issued) > crate::commerce::ADMISSION_WINDOW
            || !policy.admit(&admission.selected, q)
            || admission.selected.id != s.id
            || admission.selected.generation != s.generation
        {
            return Err(bad("expired merchant admission"));
        }
        let row = t.query_one(
            "SELECT dead,life_revision FROM characters WHERE id=$1",
            &[&s.id],
        )?;
        if !repairing
            && (row.get::<_, bool>(0) || row.get::<_, i64>(1) != admission.selected.life_revision)
        {
            return Err(bad("stale merchant life"));
        }
    }
    let source = if matches!(q.operation, 6 | 7 | 8) {
        state.equipment.get(q.source as usize)
    } else {
        state.slots.get(q.source as usize)
    };
    let status = if q.operation == 0 {
        "ok"
    } else if q.expected_revision != state.revision {
        "revision_conflict"
    } else if source.is_none()
        || (q.operation == 1 && (q.destination >= state.capacity || q.source == q.destination))
    {
        "invalid_slot"
    } else if source.unwrap().instance != q.instance {
        "instance_conflict"
    } else {
        let result = if gear {
            p.equipment.as_ref().unwrap().apply(&mut state, q)
        } else if q.operation == 1 {
            move_or_merge(&mut state.slots, q.source as usize, q.destination as usize, p);
            "committed"
        } else {
            let policy=commerce.unwrap().0;
            let mut current=policy.clone();
            if let Some(stats)=&p.stats {
                let xp=t.query_one("SELECT curve_xp FROM character_reward_progress WHERE character_id=$1",&[&s.id])?.get::<_,i64>(0) as u64;
                let level=p.thresholds.as_ref().unwrap().partition_point(|t|*t<=xp) as u32;
                current.weight_limit=stats.calculate(p.equipment.as_ref().unwrap(),&state.equipment,level)?.carry_limit;
            }
            current.apply(&mut t, p, &mut state, q)?
        };
        if result == "committed" {
            state.revision = state
                .revision
                .checked_add(1)
                .ok_or_else(|| bad("bag revision overflow"))?;
            p.validate(&state)?;
            save(&mut t, s.id, &state)?;
        }
        result
    };
    let result = wire::BagResult {
        request: q.request.clone(),
        status: status.into(),
        state: Some(state),
    };
    if q.operation != 0 {
        t.execute(
            "INSERT INTO bag_operations(character_id,request,payload,result) VALUES($1,$2,$3,$4)",
            &[&s.id, &q.request, &payload, &result.encode_to_vec()],
        )?;
    }
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if commerce.is_some_and(|(_, a)| now().saturating_duration_since(a.issued) > crate::commerce::ADMISSION_WINDOW) {
        return Err(bad("expired merchant commit"));
    }
    t.commit()?;
    Ok(result)
}
impl Database {
    pub async fn commerce(
        &self,
        o: Arc<Owner>,
        p: Policy,
        reward: String,
        q: wire::BagRequest,
        policy: crate::commerce::Policy,
        admission: crate::commerce::Admission,
    ) -> Result<wire::BagResult> {
        self.call(move |c| {
            execute_inner(
                c,
                &o,
                &admission.selected,
                &p,
                &reward,
                &q,
                Some((&policy, &admission)),
            )
        })
        .await
    }

    pub async fn bag(
        &self,
        o: Arc<Owner>,
        s: Selected,
        p: Policy,
        reward: String,
        q: wire::BagRequest,
    ) -> Result<wire::BagResult> {
        self.call(move |c| execute(c, &o, &s, &p, &reward, &q))
            .await
    }
}

/// Reference pickup searches empty physical slots before existing matching stacks.
/// Refuse a partial grant; callers consume the drop only with the whole quantity.
pub(crate) fn drop_slot(state:&wire::BagState,item:&str,quantity:u32,limit:u32)->Option<usize> {
    if quantity==0 || quantity>limit {return None;}
    state.slots.iter().position(|s|s.instance==0).or_else(|| {
        state.slots.iter().position(|s|s.item==item&&limit>1&&s.quantity.checked_add(quantity).is_some_and(|n|n<=limit))
    })
}
pub(crate) fn grant_drop(t:&mut postgres::Transaction<'_>,realm:&str,actor:i64,item:&str,quantity:u32,durability:u32,limit:u32)->Result<bool> {
    let row=t.query_one("SELECT state FROM character_bags WHERE character_id=$1 AND realm=$2 FOR UPDATE",&[&actor,&realm])?;
    let mut state=wire::BagState::decode(row.get::<_,Vec<u8>>(0).as_slice())?;basic(&state)?;
    let Some(index)=drop_slot(&state,item,quantity,limit)else{return Ok(false);};
    let slot=&mut state.slots[index];
    if slot.instance==0 {*slot=wire::ItemStack{instance:serial(t)?,item:item.into(),quantity,durability};}
    else {slot.quantity+=quantity;slot.durability=durability;}
    state.revision=state.revision.checked_add(1).ok_or_else(||bad("drop bag revision overflow"))?;
    save(t,actor,&state)?;Ok(true)
}

#[cfg(test)] mod stack_tests {
    use super::*;
    #[test] fn merge_conserves_quantities_and_identities(){
        let policy=Policy{storage:None,wear:None,stats:None,thresholds:None,equipment:None,capacity:4,currency:"x".into(),limit:100,coins:0,hash:vec![],items:vec![Item{id:"stack".into(),label:"Stack".into(),stack:20,durability:5,starting:0}]};
        for a in 1..=20 {for b in 1..=20 {for full in [false,true] {
            let item=|id,qty|wire::ItemStack{instance:id,item:"stack".into(),quantity:qty,durability:5};
            let mut slots=vec![if full {item(3,20)}else{Default::default()},item(1,a),item(2,b)];
            move_or_merge(&mut slots,1,2,&policy);
            assert_eq!(slots.iter().map(|s|s.quantity).sum::<u32>(),a+b+if full{20}else{0});
            assert_eq!(slots[2].quantity,(a+b).min(20));assert_eq!(slots[2].instance,2);
            let ids:Vec<_>=slots.iter().filter(|s|s.instance>0).map(|s|s.instance).collect();
            assert_eq!(ids.len(),ids.iter().collect::<BTreeSet<_>>().len());
            assert_eq!(ids.contains(&1),a+b>20);
            assert!(slots.iter().all(|s|s.quantity<=20));
        }}}
        let mut slots=vec![wire::ItemStack{instance:1,item:"stack".into(),quantity:4,durability:4},wire::ItemStack{instance:2,item:"stack".into(),quantity:4,durability:5}];
        let original=slots.clone();move_or_merge(&mut slots,0,1,&policy);assert_eq!(slots[0],original[1]);assert_eq!(slots[1],original[0]);
    }
}
