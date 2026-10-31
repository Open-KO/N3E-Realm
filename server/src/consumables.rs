//! Recovery is simulation-owned; item consumption and lockout are one fenced
//! PostgreSQL operation. Replays return the original result without a new effect.
use crate::{
    accounts::{Database, Owner, Selected},
    content::{bad, Reader, Result},
    inventory, persistence, wire,
};
use prost::Message;
use std::{
    collections::BTreeSet,
    path::Path,
    sync::Arc,
    time::{Duration, Instant},
};
#[derive(Clone, Debug)]
pub struct Effect {
    pub item: String,
    pub health: u32,
    pub resource: u32,
    pub delay_ms: u32,
    pub cooldown_ms: u32,
}
impl Effect {
    pub fn apply(&self, e: &mut wire::Entity, max_health: u32, max_resource: u32) {
        if e.health == 0 || e.npc {
            return;
        }
        e.health = e.health.saturating_add(self.health).min(max_health);
        e.resource = e.resource.saturating_add(self.resource).min(max_resource);
    }
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub items: Vec<Effect>,
}
impl Policy {
    pub fn load(path: &Path, bag: &inventory::Policy) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3X1" {
            return Err(bad("consumable magic"));
        }
        let n = r.u()?;
        if !(1..=64).contains(&n) {
            return Err(bad("consumable count"));
        }
        let mut items = Vec::new();
        let mut seen = BTreeSet::new();
        for _ in 0..n {
            let i = r.u()?;
            let def = bag
                .items
                .get(i.wrapping_sub(1) as usize)
                .ok_or_else(|| bad("consumable item"))?;
            let e = Effect {
                item: def.id.clone(),
                health: r.u()?,
                resource: r.u()?,
                delay_ms: r.u()?,
                cooldown_ms: r.u()?,
            };
            if !seen.insert(i)
                || def.durability != 0
                || e.health > 100000
                || e.resource > 100000
                || e.health + e.resource == 0
                || e.delay_ms > 2000
                || !(50..=60000).contains(&e.cooldown_ms)
            {
                return Err(bad("consumable bounds"));
            }
            items.push(e);
        }
        r.end()?;
        Ok(Self { items })
    }
    pub fn effect(&self, bag: Option<&wire::BagState>, q: &wire::BagRequest) -> Option<Effect> {
        let item = bag?.slots.get(q.source as usize)?;
        self.items.iter().find(|e| e.item == item.item).cloned()
    }
}
pub struct Outcome {
    pub result: wire::BagResult,
    pub effect: Option<Effect>,
    pub entity: u64,
    pub life: i64,
}
/// How long a use admission stays valid until its commit, activation delay included
/// (D-132 lists it among the wall-time admission windows).
pub const ADMISSION_WINDOW: Duration = Duration::from_secs(4);
#[allow(clippy::too_many_arguments)]
pub fn execute(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    p: &inventory::Policy,
    reward: &str,
    policy: &Policy,
    q: &wire::BagRequest,
    issued: Instant,
) -> Result<Outcome> {
    execute_at(c, o, s, p, reward, policy, q, issued, &Instant::now)
}
/// `execute` with the clock that ages the admission, read once for the use checks
/// (window, activation delay, cooldown at issue) and again just before COMMIT.
/// Production passes `Instant::now`; tests pass a fixed clock so the window, not
/// database speed, decides fresh and expired (PQ-291).
#[allow(clippy::too_many_arguments)]
fn execute_at(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    p: &inventory::Policy,
    reward: &str,
    policy: &Policy,
    q: &wire::BagRequest,
    issued: Instant,
    now: &dyn Fn() -> Instant,
) -> Result<Outcome> {
    if q.operation != 9
        || !crate::accounts::valid_name(&q.request, 64)
        || q.expected_revision > i64::MAX as u64
        || q.instance == 0
        || q.instance > i64::MAX as u64
        || q.destination != 0
        || q.quantity != 0
        || !q.service.is_empty()
        || !q.item.is_empty()
    {
        return Err(bad("invalid consumable request"));
    }
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    let row=t.query_opt("SELECT dead,life_revision FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE",&[&s.id,&o.realm,&s.generation,&o.generation])?.ok_or_else(||bad("stale consumable session"))?;
    let mut state = inventory::load(&mut t, s, o, p, reward)?;
    let payload = q.encode_to_vec();
    if let Some(row) = t.query_opt(
        "SELECT payload,result FROM bag_operations WHERE character_id=$1 AND request=$2",
        &[&s.id, &q.request],
    )? {
        let result = if row.get::<_, Vec<u8>>(0) == payload {
            wire::BagResult::decode(row.get::<_, Vec<u8>>(1).as_slice())?
        } else {
            wire::BagResult {
                request: q.request.clone(),
                status: "request_conflict".into(),
                state: Some(state),
            }
        };
        return Ok(Outcome {
            result,
            effect: None,
            entity: s.entity.id,
            life: s.life_revision,
        });
    }
    let effect = policy.effect(Some(&state), q);
    let elapsed = now().saturating_duration_since(issued).as_secs_f64();
    let ready=t.query_opt("SELECT ready_at <= clock_timestamp()-make_interval(secs => $2) FROM character_consumable_cooldowns WHERE character_id=$1",&[&s.id,&elapsed])?.is_none_or(|r|r.get::<_,bool>(0));
    let status = if elapsed > ADMISSION_WINDOW.as_secs_f64() {
        "expired_use"
    } else if s.dead
        || s.entity.health == 0
        || row.get::<_, bool>(0)
        || row.get::<_, i64>(1) != s.life_revision
    {
        "not_alive"
    // Wear and other unrelated bag commits can occur during activation. The
    // locked source slot plus immutable instance identify the intended stack;
    // a whole-bag equality check incorrectly interrupts ordinary combat use.
    } else if state.revision < q.expected_revision {
        "revision_conflict"
    } else if state.slots.get(q.source as usize).is_none() {
        "invalid_slot"
    } else if state.slots[q.source as usize].instance != q.instance {
        "instance_conflict"
    } else if effect.is_none() {
        "not_usable"
    } else if !ready {
        "cooldown"
    } else if elapsed < f64::from(effect.as_ref().unwrap().delay_ms) / 1000. {
        "use_pending"
    } else {
        "consumed"
    };
    let fresh = if status == "consumed" {
        let e = effect.unwrap();
        let slot = &mut state.slots[q.source as usize];
        slot.quantity -= 1;
        if slot.quantity == 0 {
            *slot = Default::default();
        }
        state.revision = state
            .revision
            .checked_add(1)
            .filter(|v| *v <= i64::MAX as u64)
            .ok_or_else(|| bad("bag revision overflow"))?;
        p.validate(&state)?;
        inventory::save(&mut t, s.id, &state)?;
        let seconds = f64::from(e.cooldown_ms) / 1000.;
        t.execute("INSERT INTO character_consumable_cooldowns(character_id,ready_at) VALUES($1,clock_timestamp()+make_interval(secs => $2)) ON CONFLICT(character_id) DO UPDATE SET ready_at=excluded.ready_at",&[&s.id,&seconds])?;
        Some(e)
    } else {
        None
    };
    let result = wire::BagResult {
        request: q.request.clone(),
        status: status.into(),
        state: Some(state),
    };
    t.execute(
        "INSERT INTO bag_operations(character_id,request,payload,result) VALUES($1,$2,$3,$4)",
        &[&s.id, &q.request, &payload, &result.encode_to_vec()],
    )?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if now().saturating_duration_since(issued) > ADMISSION_WINDOW {
        return Err(bad("expired consumable commit"));
    }
    t.commit()?;
    Ok(Outcome {
        result,
        effect: fresh,
        entity: s.entity.id,
        life: s.life_revision,
    })
}
impl Database {
    pub async fn consume(
        &self,
        o: Arc<Owner>,
        s: Selected,
        p: inventory::Policy,
        reward: String,
        policy: Policy,
        q: wire::BagRequest,
        issued: Instant,
        delay: u32,
    ) -> Result<Outcome> {
        tokio::time::sleep(Duration::from_millis(delay.into())).await;
        self.call(move |c| execute(c, &o, &s, &p, &reward, &policy, &q, issued))
            .await
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn recovery_caps_and_never_revives() {
        let e = Effect {
            item: "test:potion".into(),
            health: 90,
            resource: 120,
            delay_ms: 500,
            cooldown_ms: 2000,
        };
        let mut p = wire::Entity {
            health: 50,
            resource: 2,
            ..Default::default()
        };
        e.apply(&mut p, 100, 80);
        assert_eq!((p.health, p.resource), (100, 80));
        p.health = 0;
        e.apply(&mut p, 100, 80);
        assert_eq!(p.health, 0);
    }
    #[test]
    #[ignore = "tests/consumables_db.py supplies disposable PostgreSQL and original package"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let bag = release.rules.inventory.as_ref().unwrap();
        let mut c = persistence::connect(&url)?;
        let realm = format!("consume-test-{}", std::process::id());
        let owner = "consume-audit";
        let generation = persistence::acquire(&mut c, &realm, owner)?;
        let o = Owner {
            realm: realm.clone(),
            owner: owner.into(),
            generation,
        };
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let id: i64 = c
            .query_one(
                "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'Consume') RETURNING id",
                &[&account, &realm],
            )?
            .get(0);
        crate::settlements::convert(
            &mut c,
            &o,
            release.rules.progression.as_ref().unwrap(),
            &release.game,
            20,
        )?;
        c.execute("UPDATE characters SET online=true,session_generation=1,realm_generation=$2 WHERE id=$1",&[&id,&generation])?;
        let s = Selected {
            id,
            generation: 1,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            entity: wire::Entity {
                health: 100,
                ..Default::default()
            },
        };
        let read = |c: &mut postgres::Client| -> Result<wire::BagState> {
            Ok(inventory::execute(
                c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &wire::BagRequest::default(),
            )?
            .state
            .unwrap())
        };
        let initial = read(&mut c)?;
        let equip = wire::BagRequest {
            operation: 5, request: "equip".into(),
            expected_revision: initial.revision, instance: initial.slots[0].instance,
            ..Default::default()
        };
        let state = inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &equip)?.state.unwrap();
        assert!(state.equipment[0].instance != 0);

        let source = state.slots.iter().position(|i| i.quantity > 1).unwrap();
        let policy = Policy {
            items: vec![Effect {
                item: state.slots[source].item.clone(),
                health: 90,
                resource: 0,
                delay_ms: 500,
                // Policy::load's longest cooldown (60 s), far longer than the test runs,
                // so the cooldown checks below never depend on how long the database
                // takes between commits (PQ-291, PQ-292).
                cooldown_ms: 60_000,
            }],
        };
        let q = wire::BagRequest {
            operation: 9,
            request: "consume".into(),
            source: source as u32,
            instance: state.slots[source].instance,
            expected_revision: state.revision,
            ..Default::default()
        };
        // Admissions are aged by a fixed clock, never by how long PostgreSQL takes: a
        // loaded disposable cluster can hold one commit past the window (PQ-289, PQ-291).
        // `ready` is 600 ms after issue, past the 500 ms activation delay.
        let issued = Instant::now();
        let ready = issued + Duration::from_millis(600);
        let late = issued + ADMISSION_WINDOW + Duration::from_nanos(1);
        c.batch_execute("CREATE FUNCTION fail_consume() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'consume rollback'; END $$; CREATE TRIGGER fail_consume BEFORE INSERT ON bag_operations FOR EACH ROW EXECUTE FUNCTION fail_consume()")?;
        assert!(execute_at(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &policy,
            &q,
            issued,
            &|| ready
        )
        .is_err());
        assert_eq!(read(&mut c)?, state);
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM character_consumable_cooldowns WHERE character_id=$1",
                &[&id]
            )?
            .get::<_, i64>(0),
            0
        );
        c.batch_execute(
            "DROP TRIGGER fail_consume ON bag_operations; DROP FUNCTION fail_consume()",
        )?;
        // Combat wear commits during activation, after the potion request took
        // its snapshot. The potion's exact slot/instance is still unchanged.
        let wear = bag.wear.as_ref().unwrap();
        let event = wear.freeze(&state, 100, 101, 20, 1, 10, None)?.unwrap();
        let worn = crate::wear::execute(&mut c, &o, &s, bag, wear, &release.rules.item, &event)?.state;
        assert_eq!(worn.revision, state.revision + 1);
        assert_eq!(worn.slots[source], state.slots[source]);
        assert!(worn.equipment[0].durability < state.equipment[0].durability);
        // Two concurrent workers with the same key commit one decrement/effect.
        persistence::renew(&mut c, &realm, owner, generation)?;
        let handles = (0..2)
            .map(|_| {
                let (url, o, s, bag, reward, policy, q) = (
                    url.clone(),
                    o.clone(),
                    s.clone(),
                    bag.clone(),
                    release.rules.item.clone(),
                    policy.clone(),
                    q.clone(),
                );
                std::thread::spawn(move || {
                    let mut c = persistence::connect(&url).unwrap();
                    execute_at(
                        &mut c,
                        &o,
                        &s,
                        &bag,
                        &reward,
                        &policy,
                        &q,
                        issued,
                        &|| issued + ADMISSION_WINDOW,
                    )
                    .unwrap()
                })
            })
            .collect::<Vec<_>>();
        let outcomes = handles
            .into_iter()
            .map(|h| h.join().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(outcomes.iter().filter(|r| r.effect.is_some()).count(), 1);
        assert_eq!(outcomes[0].result, outcomes[1].result);
        assert_eq!(outcomes[0].result.status, "consumed");
        let changed = read(&mut c)?;
        assert_eq!(
            changed.slots[source].quantity,
            state.slots[source].quantity - 1
        );
        assert_eq!(changed.revision, worn.revision + 1);
        assert_eq!(changed.equipment, worn.equipment);
        let retry = execute_at(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &policy,
            &q,
            issued,
            &|| ready,
        )?;
        assert!(retry.effect.is_none());
        assert_eq!(retry.result, outcomes[0].result);
        let mut conflict = q.clone();
        conflict.source += 1;
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &policy,
                &conflict,
                issued,
                &|| ready
            )?
            .result
            .status,
            "request_conflict"
        );
        let mut next = q.clone();
        next.request = "next".into();
        next.expected_revision = changed.revision;
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &policy,
                &next,
                issued,
                &|| ready
            )?
            .result
            .status,
            "cooldown"
        );
        assert_eq!(read(&mut c)?, changed);
        // Reconnect and a new database connection retain the lockout and replay ledger.
        c.execute(
            "UPDATE characters SET session_generation=2 WHERE id=$1",
            &[&id],
        )?;
        let mut reconnected = s.clone();
        reconnected.generation = 2;
        let mut connection = persistence::connect(&url)?;
        assert!(execute_at(
            &mut connection,
            &o,
            &reconnected,
            bag,
            &release.rules.item,
            &policy,
            &q,
            issued,
            &|| ready
        )?
        .effect
        .is_none());
        next.request = "reconnect".into();
        assert_eq!(
            execute_at(
                &mut connection,
                &o,
                &reconnected,
                bag,
                &release.rules.item,
                &policy,
                &next,
                issued,
                &|| ready
            )?
            .result
            .status,
            "cooldown"
        );
        assert!(execute_at(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &policy,
            &next,
            issued,
            &|| ready
        )
        .is_err());
        c.execute("UPDATE character_consumable_cooldowns SET ready_at=clock_timestamp()-interval '1 hour' WHERE character_id=$1",&[&id])?;
        next.request = "early".into();
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                &reconnected,
                bag,
                &release.rules.item,
                &policy,
                &next,
                issued,
                &|| issued
            )?
            .result
            .status,
            "use_pending"
        );
        // The cooldown is over, so a fresh use from here would consume. Past the window
        // the use is refused and rolled back whichever check sees it: nothing is spent,
        // no cooldown starts, and the request ID stays unclaimed.
        let durable = |c: &mut postgres::Client| -> Result<(wire::BagState, bool, i64)> {
            let past: bool = c
                .query_one(
                    "SELECT ready_at < clock_timestamp()-interval '30 minutes' FROM character_consumable_cooldowns WHERE character_id=$1",
                    &[&id],
                )?
                .get(0);
            let claimed: i64 = c
                .query_one(
                    "SELECT count(*) FROM bag_operations WHERE character_id=$1 AND request IN ('expired','late-commit')",
                    &[&id],
                )?
                .get(0);
            let bag = inventory::execute(
                c,
                &o,
                &reconnected,
                bag,
                &release.rules.item,
                &wire::BagRequest::default(),
            )?
            .state
            .unwrap();
            Ok((bag, past, claimed))
        };
        let before = durable(&mut c)?;
        assert_eq!((before.1, before.2), (true, 0));
        let mut expired = next.clone();
        expired.request = "expired".into();
        let reads = std::cell::Cell::new(0);
        let error = execute_at(
            &mut c,
            &o,
            &reconnected,
            bag,
            &release.rules.item,
            &policy,
            &expired,
            issued,
            &|| {
                reads.set(reads.get() + 1);
                late
            },
        )
        .err()
        .unwrap();
        assert_eq!(
            (error.to_string().as_str(), reads.get()),
            ("expired consumable commit", 2)
        );
        assert_eq!(durable(&mut c)?, before);
        // Fresh at the use checks, past the window at COMMIT.
        expired.request = "late-commit".into();
        reads.set(0);
        let error = execute_at(
            &mut c,
            &o,
            &reconnected,
            bag,
            &release.rules.item,
            &policy,
            &expired,
            issued,
            &|| {
                reads.set(reads.get() + 1);
                if reads.get() == 1 {
                    ready
                } else {
                    late
                }
            },
        )
        .err()
        .unwrap();
        assert_eq!(
            (error.to_string().as_str(), reads.get()),
            ("expired consumable commit", 2)
        );
        assert_eq!(durable(&mut c)?, before);
        next.request = "foreign".into();
        next.instance += 100000;
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                &reconnected,
                bag,
                &release.rules.item,
                &policy,
                &next,
                issued,
                &|| ready
            )?
            .result
            .status,
            "instance_conflict"
        );
        next.instance = q.instance;
        next.request = "future".into();
        next.expected_revision = changed.revision + 1;
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                &reconnected,
                bag,
                &release.rules.item,
                &policy,
                &next,
                issued,
                &|| ready
            )?
            .result
            .status,
            "revision_conflict"
        );
        next.expected_revision = changed.revision;
        // A stale revision must never redirect use after the source is moved.
        let destination = changed.slots.iter().position(|r| r.instance == 0).unwrap();
        let move_item = wire::BagRequest {
            operation: 1, request: "move-potion".into(),
            expected_revision: changed.revision, source: source as u32,
            destination: destination as u32, instance: q.instance,
            ..Default::default()
        };
        let moved = inventory::execute(&mut c, &o, &reconnected, bag, &release.rules.item, &move_item)?.state.unwrap();
        assert_eq!(moved.slots[destination].instance, q.instance);
        next.request = "moved-source".into();
        let rejected = execute_at(&mut c, &o, &reconnected, bag, &release.rules.item, &policy, &next, issued, &|| ready)?;
        assert_eq!(rejected.result.status, "instance_conflict");
        assert!(rejected.effect.is_none());
        assert_eq!(rejected.result.state.as_ref(), Some(&moved));
        c.execute("UPDATE characters SET dead=true,life_revision=1,respawn_ready_at=clock_timestamp() WHERE id=$1",&[&id])?;
        next.request = "dead".into();
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                &reconnected,
                bag,
                &release.rules.item,
                &policy,
                &next,
                issued,
                &|| ready
            )?
            .result
            .status,
            "not_alive"
        );
        c.execute(
            "UPDATE characters SET dead=false,respawn_ready_at=NULL WHERE id=$1",
            &[&id],
        )?;
        next.request = "old-life".into();
        assert_eq!(
            execute_at(
                &mut c,
                &o,
                &reconnected,
                bag,
                &release.rules.item,
                &policy,
                &next,
                issued,
                &|| ready
            )?
            .result
            .status,
            "not_alive"
        );
        assert_eq!(read(&mut c).is_err(), true); // old session is fenced
        println!("PASS consumable rollback, activation across committed combat wear, concurrent exact retry, immutable result, shared cooldown/reconnect, timing, identity and life fences");
        Ok(())
    }
}
