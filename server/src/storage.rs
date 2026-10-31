//! Account-owned storage, atomic with the selected character's bag and currency.
use crate::{
    accounts::{Owner, Selected},
    content::{bad, Reader, Result},
    inventory, persistence,
    rules::Rules,
    wire,
};
use prost::Message;
use std::{
    collections::BTreeSet,
    path::Path,
    time::{Duration, Instant},
};
#[derive(Clone, Debug)]
pub struct Service {
    pub id: String,
    pub position: [f32; 3],
    pub radius: f32,
    pub remote: bool,
    pub fee: u32,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub credential: Option<crate::storage_auth::Policy>,
    pub capacity: u32,
    pub coin_limit: u32,
    pub services: Vec<Service>,
}
impl Policy {
    pub fn load(path: &Path, game: &str) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3B1" {
            return Err(bad("storage magic"));
        }
        let mut p = Self {
            credential: None,
            capacity: r.u()?,
            coin_limit: r.u()?,
            services: vec![],
        };
        let n = r.u()?;
        if !(1..=192).contains(&p.capacity)
            || !(1..=2_100_000_000).contains(&p.coin_limit)
            || !(1..=64).contains(&n)
        {
            return Err(bad("storage bounds"));
        }
        let mut seen = BTreeSet::new();
        for _ in 0..n {
            let id = r.string()?;
            let label = r.string()?;
            let position = [r.f()?, r.f()?, r.f()?];
            let radius = r.f()?;
            let remote = r.u()?;
            let fee = r.u()?;
            if !inventory::id(&id, game)
                || !seen.insert(id.clone())
                || label.len() > 64
                || !label.bytes().all(|c| (32..=126).contains(&c))
                || position.iter().any(|v| v.abs() > 1000.)
                || !(0.5..=20.).contains(&radius)
                || remote > 1
                || fee > 2_100_000_000
            {
                return Err(bad("storage service"));
            }
            p.services.push(Service {
                id,
                position,
                radius,
                remote: remote != 0,
                fee,
            });
        }
        r.end()?;
        Ok(p)
    }
    fn validate(
        &self,
        p: &inventory::Policy,
        s: &wire::StorageState,
        b: &wire::BagState,
    ) -> Result<()> {
        if s.capacity != self.capacity
            || s.slots.len() != self.capacity as usize
            || s.coins > self.coin_limit
            || s.revision > i64::MAX as u64
        {
            return Err(bad("storage state bounds"));
        }
        let mut seen: BTreeSet<_> = b
            .slots
            .iter()
            .chain(&b.equipment)
            .filter(|i| i.instance != 0)
            .map(|i| i.instance)
            .collect();
        for i in &s.slots {
            if i.instance == 0 {
                if !i.item.is_empty() || i.quantity != 0 || i.durability != 0 {
                    return Err(bad("storage vacant slot"));
                }
            } else if i.instance > i64::MAX as u64
                || !seen.insert(i.instance)
                || i.quantity == 0
                || !p.items.iter().any(|d| {
                    d.id == i.item && i.quantity <= d.stack && i.durability <= d.durability
                })
            {
                return Err(bad("storage record"));
            }
        }
        Ok(())
    }
    pub(crate) fn service(&self, s: &Selected, id: &str) -> Option<&Service> {
        if s.dead || s.entity.health == 0 {
            return None;
        }
        self.services.iter().find(|v| {
            v.id == id
                && (v.remote
                    || (s.entity.x - v.position[0]).powi(2) + (s.entity.z - v.position[2]).powi(2)
                        <= v.radius * v.radius)
        })
    }
}
pub fn check_start(
    c: &mut postgres::Client,
    realm: &str,
    p: Option<&inventory::Policy>,
) -> Result<()> {
    crate::storage_auth::check_start(c, realm, p)?;
    for r in c.query(
        "SELECT DISTINCT definition FROM account_storage WHERE realm=$1",
        &[&realm],
    )? {
        if p.is_none_or(|p| p.storage.is_none() || r.get::<_, Vec<u8>>(0) != p.hash) {
            return Err(bad(
                "incompatible durable storage; explicit migration required",
            ));
        }
    }
    Ok(())
}
fn request(q: &wire::StorageRequest) -> Result<()> {
    if q.operation > 5
        || !crate::accounts::valid_name(&q.request, 64)
        || q.service.is_empty()
        || q.service.len() > 129
        || q.bag_revision > i64::MAX as u64
        || q.storage_revision > i64::MAX as u64
        || q.instance > i64::MAX as u64
        || (q.operation == 0
            && (q.source != 0 || q.destination != 0 || q.instance != 0 || q.quantity != 0))
        || ((1..=3).contains(&q.operation) && q.instance == 0)
        || ((1..=2).contains(&q.operation) && !(1..=9999).contains(&q.quantity))
        || (q.operation == 3 && q.quantity != 0)
        || (q.operation >= 4
            && (q.instance != 0
                || q.source != 0
                || q.destination != 0
                || q.quantity == 0
                || q.quantity > 2_100_000_000))
    {
        return Err(bad("invalid storage request"));
    }
    Ok(())
}
fn bump(v: &mut u64) -> Result<()> {
    *v = v
        .checked_add(1)
        .filter(|v| *v <= i64::MAX as u64)
        .ok_or_else(|| bad("storage revision overflow"))?;
    Ok(())
}
fn transfer(
    t: &mut postgres::Transaction<'_>,
    p: &inventory::Policy,
    from: &mut wire::ItemStack,
    to: &mut wire::ItemStack,
    quantity: u32,
) -> Result<&'static str> {
    let d = p
        .items
        .iter()
        .find(|d| d.id == from.item)
        .ok_or_else(|| bad("storage definition"))?;
    if quantity > from.quantity {
        return Ok("insufficient_items");
    }
    if to.instance != 0 && (to.item != from.item || d.stack == 1) {
        return Ok("occupied_slot");
    }
    if to.quantity as u64 + quantity as u64 > d.stack as u64 {
        return Ok("stack_full");
    }
    if to.instance == 0 {
        *to = from.clone();
        to.quantity = quantity;
        if quantity < from.quantity {
            to.instance = inventory::serial(t)?;
        }
    } else {
        to.quantity += quantity;
        to.durability = from.durability;
    }
    from.quantity -= quantity;
    if from.quantity == 0 {
        *from = wire::ItemStack::default();
    }
    Ok("committed")
}
/// How long a storage admission stays valid until its commit (D-132 lists it among the
/// wall-time admission windows).
pub const ADMISSION_WINDOW: Duration = Duration::from_secs(2);
pub fn execute(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    r: &Rules,
    q: &wire::StorageRequest,
    issued: Instant,
) -> Result<wire::StorageResult> {
    execute_at(c, o, s, r, q, issued, &Instant::now)
}
/// `execute` with the clock that ages the admission, read at the admission check and
/// again just before COMMIT. Production passes `Instant::now`; tests pass a fixed clock
/// so the window, not database speed, decides fresh and expired (PQ-291).
pub(crate) fn execute_at(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    r: &Rules,
    q: &wire::StorageRequest,
    issued: Instant,
    now: &dyn Fn() -> Instant,
) -> Result<wire::StorageResult> {
    request(q)?;
    let p = r
        .inventory
        .as_ref()
        .ok_or_else(|| bad("storage unavailable"))?;
    let policy = p
        .storage
        .as_ref()
        .ok_or_else(|| bad("storage unavailable"))?;
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    // Derive ownership from the fenced character; never accept an account selector.
    let account:i64=t.query_opt("SELECT account_id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online",&[&s.id,&o.realm,&s.generation,&o.generation])?.ok_or_else(||bad("stale storage session"))?.get(0);
    if let Some(status)=crate::storage_auth::authorize(&mut t,o,s,p,account)? {
        return Ok(wire::StorageResult{request:q.request.clone(),status:status.into(),..Default::default()});
    }
    // Credential -> storage -> character lock order, including first creation.
    let empty = wire::StorageState {
        capacity: policy.capacity,
        slots: vec![wire::ItemStack::default(); policy.capacity as usize],
        ..Default::default()
    };
    t.execute("INSERT INTO account_storage(account_id,realm,definition,state) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",&[&account,&o.realm,&p.hash,&empty.encode_to_vec()])?;
    let row = t.query_one(
        "SELECT definition,state FROM account_storage WHERE account_id=$1 AND realm=$2 FOR UPDATE",
        &[&account, &o.realm],
    )?;
    if row.get::<_, Vec<u8>>(0) != p.hash {
        return Err(bad("storage definition conflict"));
    }
    let mut storage = wire::StorageState::decode(row.get::<_, Vec<u8>>(1).as_slice())?;
    let life=t.query_opt("SELECT dead,life_revision FROM characters WHERE id=$1 AND realm=$2 AND account_id=$5 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE",&[&s.id,&o.realm,&s.generation,&o.generation,&account])?.ok_or_else(||bad("stale storage session"))?;
    let mut bag = inventory::load(&mut t, s, o, p, &r.item)?;
    policy.validate(p, &storage, &bag)?;
    let payload = q.encode_to_vec();
    if let Some(row) = t.query_opt(
        "SELECT payload,result FROM storage_operations WHERE character_id=$1 AND request=$2",
        &[&s.id, &q.request],
    )? {
        if row.get::<_, Vec<u8>>(0) == payload {
            return Ok(wire::StorageResult::decode(
                row.get::<_, Vec<u8>>(1).as_slice(),
            )?);
        }
        return Ok(wire::StorageResult {
            request: q.request.clone(),
            status: "request_conflict".into(),
            bag: Some(bag),
            storage: Some(storage),
            inventory: None,
        });
    }
    let mut counts = crate::rewards::inventory(&mut t, s.id, r)?;
    let service = policy.service(s, &q.service);
    let status = if now().saturating_duration_since(issued) > ADMISSION_WINDOW {
        return Err(bad("expired storage admission"));
    } else if life.get::<_, bool>(0)
        || life.get::<_, i64>(1) != s.life_revision
        || service.is_none()
    {
        "access_denied"
    } else if q.bag_revision != bag.revision
        || (q.operation != 0 && q.storage_revision != storage.revision)
    {
        "revision_conflict"
    } else if q.operation == 0 {
        let fee = service.unwrap().fee;
        if bag.coins < fee {
            "insufficient_funds"
        } else {
            bag.coins -= fee;
            if fee > 0 {
                bump(&mut bag.revision)?;
            }
            "committed"
        }
    } else if q.operation >= 4 {
        let (from, to, limit) = if q.operation == 4 {
            (&mut bag.coins, &mut storage.coins, policy.coin_limit)
        } else {
            (&mut storage.coins, &mut bag.coins, p.limit)
        };
        if *from < q.quantity {
            "insufficient_funds"
        } else if *to as u64 + q.quantity as u64 > limit as u64 {
            "currency_limit"
        } else {
            *from -= q.quantity;
            *to += q.quantity;
            bump(&mut bag.revision)?;
            bump(&mut storage.revision)?;
            "committed"
        }
    } else {
        let from = if q.operation == 1 {
            bag.slots.get(q.source as usize)
        } else {
            storage.slots.get(q.source as usize)
        };
        let dest_ok = if q.operation == 2 {
            q.destination < bag.capacity
        } else {
            q.destination < storage.capacity
        };
        if from.is_none() || !dest_ok || (q.operation == 3 && q.source == q.destination) {
            "invalid_slot"
        } else if from.unwrap().instance != q.instance {
            "instance_conflict"
        } else if q.operation == 3 {
            if storage.slots[q.destination as usize].instance != 0 {
                "occupied_slot"
            } else {
                storage
                    .slots
                    .swap(q.source as usize, q.destination as usize);
                bump(&mut storage.revision)?;
                "committed"
            }
        } else {
            let record = from.unwrap();
            let reward = record.item == r.item;
            let commerce = r.commerce.as_ref().unwrap();
            let weight: u64 = bag
                .slots
                .iter()
                .filter(|v| v.instance != 0)
                .map(|v| {
                    commerce
                        .items
                        .iter()
                        .find(|d| d.item == v.item)
                        .unwrap()
                        .weight as u64
                        * v.quantity as u64
                })
                .sum();
            let extra = commerce
                .items
                .iter()
                .find(|d| d.item == record.item)
                .unwrap()
                .weight as u64
                * q.quantity as u64;
            let limit = p
                .stats
                .as_ref()
                .unwrap()
                .calculate(
                    p.equipment.as_ref().unwrap(),
                    &bag.equipment,
                    counts.level as u32,
                )?
                .carry_limit;
            if reward && q.operation == 1 && counts.count < q.quantity {
                return Err(bad("reward bag count disagreement"));
            }
            if q.operation == 2 && weight + extra > limit as u64 {
                "weight_limit"
            } else if reward
                && q.operation == 2
                && counts.count as u64 + q.quantity as u64 > counts.capacity as u64
            {
                "reward_capacity"
            } else {
                let result = if q.operation == 1 {
                    transfer(
                        &mut t,
                        p,
                        &mut bag.slots[q.source as usize],
                        &mut storage.slots[q.destination as usize],
                        q.quantity,
                    )?
                } else {
                    transfer(
                        &mut t,
                        p,
                        &mut storage.slots[q.source as usize],
                        &mut bag.slots[q.destination as usize],
                        q.quantity,
                    )?
                };
                if result == "committed" {
                    bump(&mut bag.revision)?;
                    bump(&mut storage.revision)?;
                    if reward {
                        counts.count = if q.operation == 1 {
                            counts.count - q.quantity
                        } else {
                            counts.count + q.quantity
                        };
                        bump(&mut counts.revision)?;
                        t.execute(
                            "UPDATE character_progress SET count=$2 WHERE character_id=$1",
                            &[&s.id, &(counts.count as i32)],
                        )?;
                        t.execute("UPDATE character_reward_progress SET revision=$2 WHERE character_id=$1",&[&s.id,&(counts.revision as i64)])?;
                    }
                }
                result
            }
        }
    };
    p.validate(&bag)?;
    policy.validate(p, &storage, &bag)?;
    if status == "committed" {
        inventory::save(&mut t, s.id, &bag)?;
        t.execute(
            "UPDATE account_storage SET state=$3 WHERE account_id=$1 AND realm=$2",
            &[&account, &o.realm, &storage.encode_to_vec()],
        )?;
    }
    let result = wire::StorageResult {
        request: q.request.clone(),
        status: status.into(),
        bag: Some(bag),
        storage: Some(storage),
        inventory: Some(counts),
    };
    t.execute(
        "INSERT INTO storage_operations(character_id,request,payload,result) VALUES($1,$2,$3,$4)",
        &[&s.id, &q.request, &payload, &result.encode_to_vec()],
    )?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if now().saturating_duration_since(issued) > ADMISSION_WINDOW {
        return Err(bad("expired storage commit"));
    }
    fault("before_commit");
    t.commit()?;
    fault("after_commit");
    Ok(result)
}
fn fault(phase: &str) {
    if std::env::var("N3E_STORAGE_FAULT").ok().as_deref() == Some(phase) {
        eprintln!("STORAGE_FAULT {phase}");
        std::process::exit(95);
    }
}
impl crate::accounts::Database {
    pub async fn storage(
        &self,
        o: std::sync::Arc<Owner>,
        s: Selected,
        r: Rules,
        q: wire::StorageRequest,
        issued: Instant,
    ) -> Result<wire::StorageResult> {
        self.call(move |c| execute(c, &o, &s, &r, &q, issued)).await
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "tests/storage_db.py supplies disposable PostgreSQL and package"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let r = &release.rules;
        let p = r.inventory.as_ref().unwrap();
        let mut c = persistence::connect(&url)?;
        let realm = format!("storage-{}", std::process::id());
        let owner = "audit";
        let generation = persistence::acquire(&mut c, &realm, owner)?;
        let o = Owner {
            realm: realm.clone(),
            owner: owner.into(),
            generation,
        };
        let mut actors = vec![];
        let mut account: i64 = 0;
        for i in 0..3 {
            if i != 1 {
                account=c.query_one("INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",&[&format!("{realm}-{i}"),&&[0u8;16][..],&&[0u8;32][..]])?.get(0);
            }
            let id=c.query_one("INSERT INTO characters(account_id,realm,name,online,session_generation,realm_generation) VALUES($1,$2,$3,false,1,$4) RETURNING id",&[&account,&realm,&format!("Storage{i}"),&generation])?.get(0);
            actors.push(Selected {
                id,
                generation: 1,
                life_revision: 0,
                dead: false,
                ready_ticks: 0,
                entity: wire::Entity {
                    health: 100,
                    ..Default::default()
                },
            });
        }
        crate::settlements::convert(
            &mut c,
            &o,
            r.progression.as_ref().unwrap(),
            &release.game,
            20,
        )?;
        c.execute(
            "UPDATE characters SET online=true WHERE realm=$1",
            &[&realm],
        )?;
        let a = &actors[0];
        let b = &actors[1];
        let foreign = &actors[2];
        let read = |c: &mut postgres::Client, s: &Selected| -> Result<wire::BagState> {
            Ok(
                inventory::execute(c, &o, s, p, &r.item, &wire::BagRequest::default())?
                    .state
                    .unwrap(),
            )
        };
        let open = |name: &str, bag: &wire::BagState| wire::StorageRequest {
            request: name.into(),
            service: "demo:bank/test".into(),
            bag_revision: bag.revision,
            ..Default::default()
        };
        // Admissions are aged by a fixed clock, never by how long PostgreSQL takes: a
        // loaded disposable cluster can hold one commit past the window (PQ-289, PQ-291).
        let issued = Instant::now();
        let late = issued + ADMISSION_WINDOW + Duration::from_nanos(1);
        let call = |c: &mut postgres::Client, s: &Selected, q: &wire::StorageRequest| {
            execute_at(c, &o, s, r, q, issued, &|| issued)
        };
        let bag = read(&mut c, a)?;
        let original = open("open", &bag);
        let first = call(&mut c, a, &original)?;
        assert_eq!(first.status, "committed");
        assert_eq!(first.bag.as_ref().unwrap().coins, 90);
        assert_eq!(first.storage.as_ref().unwrap().slots.len(), 192);
        let mut current = first.clone();
        let query =
            |name: &str, op: u32, from: u32, to: u32, qty: u32, state: &wire::StorageResult| {
                let bag = state.bag.as_ref().unwrap();
                let storage = state.storage.as_ref().unwrap();
                let instance = if op == 1 {
                    bag.slots[from as usize].instance
                } else if (2..=3).contains(&op) {
                    storage.slots[from as usize].instance
                } else {
                    0
                };
                wire::StorageRequest {
                    request: name.into(),
                    operation: op,
                    source: from,
                    destination: to,
                    quantity: qty,
                    instance,
                    bag_revision: bag.revision,
                    storage_revision: storage.revision,
                    service: "demo:bank/test".into(),
                }
            };
        let blade = current.bag.as_ref().unwrap().slots[0].clone();
        current = call(&mut c, a, &query("deposit-blade", 1, 0, 191, 1, &current))?;
        assert_eq!(current.status, "committed");
        assert_eq!(current.storage.as_ref().unwrap().slots[191], blade);
        let mut forged = query("outside-source", 3, 191, 0, 0, &current);
        forged.source = 192;
        assert_eq!(call(&mut c, a, &forged)?.status, "invalid_slot");
        let mut excessive = query("overflow-count", 1, 1, 10, 1, &current);
        excessive.quantity = u32::MAX;
        assert!(call(&mut c, a, &excessive).is_err());
        let denied = call(&mut c, a, &query("bad-slot", 3, 191, 192, 0, &current))?;
        assert_eq!(denied.status, "invalid_slot");
        assert_eq!(denied.bag, current.bag);
        assert_eq!(denied.storage, current.storage);
        current = call(&mut c, a, &query("move", 3, 191, 4, 0, &current))?;
        assert_eq!(current.status, "committed");
        let bag_b = read(&mut c, b)?;
        let mut second = call(&mut c, b, &open("b-open", &bag_b))?;
        assert_eq!(second.storage, current.storage);
        let heavy = call(&mut c, b, &query("b-heavy", 2, 4, 8, 1, &second))?;
        assert_eq!(heavy.status, "weight_limit");
        second = call(&mut c, b, &query("b-store-shield", 1, 2, 5, 1, &second))?;
        assert_eq!(second.status, "committed");
        second = call(&mut c, b, &query("b-withdraw", 2, 4, 8, 1, &second))?;
        assert_eq!(second.status, "committed");
        assert_eq!(second.bag.as_ref().unwrap().slots[8], blade);
        current.storage = second.storage.clone();
        let mut source = current.bag.as_ref().unwrap().slots[1].clone();
        let mut destination = source.clone();
        destination.instance += 1000;
        destination.quantity = p.items.iter().find(|d| d.id == source.item).unwrap().stack;
        let originals = (source.clone(), destination.clone());
        let mut t = c.transaction()?;
        assert_eq!(
            transfer(&mut t, p, &mut source, &mut destination, 1)?,
            "stack_full"
        );
        assert_eq!((source, destination), originals);
        t.rollback()?;
        let potion = current.bag.as_ref().unwrap().slots[1].clone();
        current = call(&mut c, a, &query("split", 1, 1, 10, 2, &current))?;
        assert_eq!(current.status, "committed");
        let split = current.storage.as_ref().unwrap().slots[10].instance;
        assert_ne!(split, potion.instance);
        assert_eq!(current.bag.as_ref().unwrap().slots[1].quantity, 3);
        current = call(&mut c, a, &query("merge", 1, 1, 10, 3, &current))?;
        assert_eq!(current.storage.as_ref().unwrap().slots[10].quantity, 5);
        assert_eq!(current.storage.as_ref().unwrap().slots[10].instance, split);
        current = call(&mut c, a, &query("take-split", 2, 10, 1, 2, &current))?;
        assert_eq!(current.status, "committed");
        let bag_split = current.bag.as_ref().unwrap().slots[1].instance;
        assert_ne!(bag_split, split);
        current = call(&mut c, a, &query("take-rest", 2, 10, 1, 3, &current))?;
        assert_eq!(current.bag.as_ref().unwrap().slots[1].quantity, 5);
        assert_eq!(current.bag.as_ref().unwrap().slots[1].instance, bag_split);
        assert_eq!(current.storage.as_ref().unwrap().slots[10].instance, 0);
        current = call(&mut c, a, &query("put-coins", 4, 0, 0, 50, &current))?;
        assert_eq!(current.status, "committed");
        assert_eq!(current.bag.as_ref().unwrap().coins, 40);
        second.storage = current.storage.clone();
        assert_eq!(
            call(&mut c, b, &query("coin-cap", 5, 0, 0, 30, &second))?.status,
            "currency_limit"
        );
        for i in 0..3 {
            second = call(
                &mut c,
                b,
                &open(&format!("b-fee-{i}"), second.bag.as_ref().unwrap()),
            )?;
        }
        second = call(&mut c, b, &query("take-coins", 5, 0, 0, 30, &second))?;
        assert_eq!(second.status, "committed");
        assert_eq!(second.bag.as_ref().unwrap().coins, 90);
        assert_eq!(second.storage.as_ref().unwrap().coins, 20);
        current.storage = second.storage.clone();
        // Two characters compete for the same account revision: one mutation wins.
        let qa = query("race-a", 5, 0, 0, 10, &current);
        let qb = query("race-b", 5, 0, 0, 10, &second);
        let mut c2 = persistence::connect(&url)?;
        let (x, y) = std::thread::scope(|scope| {
            let job = scope.spawn(|| call(&mut c2, b, &qb));
            let x = call(&mut c, a, &qa);
            (x, job.join().unwrap())
        });
        let (x, y) = (x?, y?);
        assert_eq!(
            u32::from(x.status == "committed") + u32::from(y.status == "committed"),
            1
        );
        assert!(x.status == "committed" || x.status == "revision_conflict");
        assert!(y.status == "committed" || y.status == "revision_conflict");
        // Read latest state with a fresh, legitimately charged open.
        let bag = read(&mut c, a)?;
        current = call(&mut c, a, &open("refresh", &bag))?;
        let before = current.clone();
        let q = query("rollback", 4, 0, 0, 1, &current);
        c.batch_execute("CREATE FUNCTION fail_storage() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'rollback storage'; END $$; CREATE TRIGGER fail_storage BEFORE INSERT ON storage_operations FOR EACH ROW EXECUTE FUNCTION fail_storage()")?;
        assert!(call(&mut c, a, &q).is_err());
        assert_eq!(read(&mut c, a)?, before.bag.clone().unwrap());
        c.batch_execute(
            "DROP TRIGGER fail_storage ON storage_operations;DROP FUNCTION fail_storage()",
        )?;
        current = call(&mut c, a, &q)?;
        assert_eq!(current.status, "committed");
        assert_eq!(
            current.storage.as_ref().unwrap().coins,
            before.storage.as_ref().unwrap().coins + 1
        );
        // Historical results survive new connections and never revert either container.
        drop(c);
        let mut c = persistence::connect(&url)?;
        assert_eq!(call(&mut c, a, &original)?, first);
        assert_eq!(read(&mut c, a)?, current.bag.clone().unwrap());
        let mut conflict = original.clone();
        conflict.quantity = 1;
        assert!(call(&mut c, a, &conflict).is_err());
        conflict = original.clone();
        conflict.service = "demo:bank/other".into();
        assert_eq!(call(&mut c, a, &conflict)?.status, "request_conflict");
        let bag = read(&mut c, foreign)?;
        let isolated = call(&mut c, foreign, &open("foreign", &bag))?;
        assert_eq!(isolated.storage.as_ref().unwrap().coins, 0);
        assert!(isolated
            .storage
            .as_ref()
            .unwrap()
            .slots
            .iter()
            .all(|i| i.instance == 0));
        let mut forged = query("steal", 2, 4, 8, 1, &isolated);
        forged.instance = blade.instance;
        assert_eq!(call(&mut c, foreign, &forged)?.status, "instance_conflict");
        let mut stale = a.clone();
        stale.generation += 1;
        assert!(call(&mut c, &stale, &original).is_err());
        let mut stale_o = o.clone();
        stale_o.generation += 1;
        assert!(execute_at(&mut c, &stale_o, a, r, &original, issued, &|| issued).is_err());
        let mut far = a.clone();
        far.entity.x = 100.;
        assert_eq!(
            call(&mut c, &far, &open("far", current.bag.as_ref().unwrap()))?.status,
            "access_denied"
        );
        let mut dead = a.clone();
        dead.dead = true;
        assert_eq!(
            call(&mut c, &dead, &open("dead", current.bag.as_ref().unwrap()))?.status,
            "access_denied"
        );
        // Past the window at the admission check: refused, nothing durable.
        let operations = |c: &mut postgres::Client, request: &str| -> Result<i64> {
            Ok(c.query_one(
                "SELECT count(*) FROM storage_operations WHERE character_id=$1 AND request=$2",
                &[&a.id, &request],
            )?
            .get(0))
        };
        let durable = |c: &mut postgres::Client| -> Result<(wire::BagState, Vec<u8>)> {
            let storage = c
                .query_one(
                    "SELECT s.state FROM account_storage s JOIN characters c ON c.account_id=s.account_id AND c.realm=s.realm WHERE c.id=$1",
                    &[&a.id],
                )?
                .get(0);
            Ok((read(c, a)?, storage))
        };
        let before = durable(&mut c)?;
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                a,
                r,
                &open("expired", current.bag.as_ref().unwrap()),
                issued,
                &|| late
            )
            .unwrap_err()
            .to_string(),
            "expired storage admission"
        );
        // Fresh at the admission check, past the window at COMMIT: refused and rolled
        // back, so bag and storage are unchanged and the request ID stays unclaimed.
        let reads = std::cell::Cell::new(0);
        let error = execute_at(
            &mut c,
            &o,
            a,
            r,
            &open("late-commit", current.bag.as_ref().unwrap()),
            issued,
            &|| {
                reads.set(reads.get() + 1);
                if reads.get() == 1 {
                    issued
                } else {
                    late
                }
            },
        )
        .unwrap_err();
        assert_eq!(
            (error.to_string().as_str(), reads.get()),
            ("expired storage commit", 2)
        );
        assert_eq!(
            (operations(&mut c, "expired")?, operations(&mut c, "late-commit")?),
            (0, 0)
        );
        assert_eq!(durable(&mut c)?, before);
        // Reward ownership count follows the physical token; old claim history is immutable.
        let mut t = c.transaction()?;
        assert!(inventory::grant_existing(&mut t, &realm, a.id, &r.item)?);
        t.execute(
            "UPDATE character_progress SET count=count+1 WHERE character_id=$1",
            &[&a.id],
        )?;
        t.commit()?;
        let bag = read(&mut c, a)?;
        // The window is inclusive: an admission exactly at its end still commits.
        current = execute_at(
            &mut c,
            &o,
            a,
            r,
            &open("reward-open", &bag),
            issued,
            &|| issued + ADMISSION_WINDOW,
        )?;
        assert_eq!(current.status, "committed");
        let slot = current
            .bag
            .as_ref()
            .unwrap()
            .slots
            .iter()
            .position(|i| i.item == r.item)
            .unwrap() as u32;
        current = call(&mut c, a, &query("reward-deposit", 1, slot, 2, 1, &current))?;
        assert_eq!(current.status, "committed");
        assert_eq!(current.inventory.as_ref().unwrap().count, 0);
        let bag = read(&mut c, b)?;
        second = call(&mut c, b, &open("reward-b-open", &bag))?;
        second = call(&mut c, b, &query("reward-withdraw", 2, 2, 9, 1, &second))?;
        assert_eq!(second.status, "committed");
        assert_eq!(second.inventory.as_ref().unwrap().count, 1);
        assert!(c
            .execute(
                "UPDATE storage_operations SET request='changed' WHERE character_id=$1",
                &[&a.id]
            )
            .is_err());
        Ok(())
    }
}
