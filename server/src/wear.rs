//! Ordinary durability loss, frozen before database work. No client-origin wear commands.
//! PQ-421 (D-218): a strike's event can also remove a ranged profile's
//! ammunition from the first bag slot holding it, in the same transaction.
use crate::{
    accounts::{Owner, Selected},
    content::{bad, Reader, Result},
    equipment, inventory, persistence, wire,
};
use prost::Message;
use std::{collections::BTreeSet, path::Path};
#[derive(Clone, Debug)]
pub struct Item {
    id: String,
    attack: u32,
    defense: u32,
}
#[derive(Clone, Debug)]
pub struct Policy {
    scale: f64,
    items: Vec<Item>,
}
#[derive(Clone, Debug)]
pub struct Event {
    pub id: u64,
    pub revision: u64,
    pub source: u64,
    pub tick: u64,
    pub mode: u32,
    pub damage: u32,
    pub records: Vec<(u32, wire::ItemStack)>,
    /// D-218: the ammunition the strike removes (item, count), if any.
    pub ammo: Option<(String, u32)>,
}
#[derive(Clone, Debug)]
pub struct Outcome {
    pub committed: bool,
    pub state: wire::BagState,
}
impl Policy {
    pub fn load(path: &Path, gear: &equipment::Policy) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3U1" {
            return Err(bad("wear magic"));
        }
        let scale = f64::from_le_bytes(r.take(8)?.try_into()?);
        let n = r.u()?;
        if !scale.is_finite() || scale <= 0. || scale > 1. || n as usize != gear.items.len() {
            return Err(bad("wear bounds"));
        }
        let mut items = vec![];
        let mut seen = BTreeSet::new();
        for _ in 0..n {
            let id = r.string()?;
            let attack = r.u()?;
            let defense = r.u()?;
            let def = gear
                .items
                .iter()
                .find(|i| i.id == id)
                .ok_or_else(|| bad("wear reference"))?;
            if !seen.insert(id.clone()) || (attack | defense) & !def.slots != 0 {
                return Err(bad("wear masks"));
            }
            items.push(Item {
                id,
                attack,
                defense,
            });
        }
        r.end()?;
        Ok(Self { scale, items })
    }
    pub fn amount(&self, damage: u32) -> Result<u32> {
        if damage > 1_000_000 {
            return Err(bad("wear damage bound"));
        }
        Ok((damage as f64 * self.scale).sqrt().trunc() as u32)
    }
    pub fn freeze(
        &self,
        state: &wire::BagState,
        id: u64,
        source: u64,
        tick: u64,
        mode: u32,
        damage: u32,
        ammo: Option<(&str, u32)>,
    ) -> Result<Option<Event>> {
        if state.equipment.len() > 16 {
            return Err(bad("wear equipment bound"));
        }
        if !(1..=2).contains(&mode) || (ammo.is_some() && mode != 1) {
            return Err(bad("wear mode"));
        }
        let worn = self.amount(damage)? > 0;
        let mut records = vec![];
        for (slot, record) in state
            .equipment
            .iter()
            .enumerate()
            .filter(|(_, r)| worn && r.instance != 0 && r.durability > 0)
        {
            let rule = self
                .items
                .iter()
                .find(|i| i.id == record.item)
                .ok_or_else(|| bad("wear item"))?;
            if (if mode == 1 { rule.attack } else { rule.defense }) & (1 << slot) != 0 {
                records.push((slot as u32, record.clone()));
            }
        }
        // A shot that needs ammunition always commits (a miss spends it too).
        if records.is_empty() && ammo.is_none() {
            return Ok(None);
        }
        let event = Event {
            id,
            revision: state.revision,
            source,
            tick,
            mode,
            damage,
            records,
            ammo: ammo.map(|(item, count)| (item.to_owned(), count)),
        };
        event.canonical()?;
        Ok(Some(event))
    }
    /// Applies the event to the locked durable bag. `false` (nothing applied,
    /// neither wear nor ammunition) when the first bag slot holding the
    /// event's ammunition holds fewer than its count, or none does (D-218,
    /// as Ebenezer's `004b0792` takes the first slot holding the item).
    fn apply(&self, state: &mut wire::BagState, event: &Event) -> Result<bool> {
        if state.revision < event.revision {
            return Err(bad("wear future revision"));
        }
        let ammo = match &event.ammo {
            None => None,
            Some((item, count)) => match ammo_slot(state, item, *count) {
                Some(slot) => Some((slot, *count)),
                None => return Ok(false),
            },
        };
        let amount = self.amount(event.damage)?;
        let mut changed = false;
        for (slot, frozen) in &event.records {
            let rule = self
                .items
                .iter()
                .find(|r| r.id == frozen.item)
                .ok_or_else(|| bad("wear definition"))?;
            if (if event.mode == 1 {
                rule.attack
            } else {
                rule.defense
            }) & (1 << slot)
                == 0
            {
                return Err(bad("wear frozen slot"));
            }
            // A hit retains the item it struck. Concurrent moves/repairs cannot
            // cancel the hit or redirect loss to newly equipped replacements.
            // Sold/consumed records are already gone; no other owner's bag is touched.
            if let Some(record) = state
                .slots
                .iter_mut()
                .chain(&mut state.equipment)
                .find(|r| r.instance == frozen.instance)
            {
                if record.item != frozen.item || record.quantity != 1 {
                    return Err(bad("wear instance identity"));
                }
                let durability = record.durability.saturating_sub(amount);
                changed |= durability != record.durability;
                record.durability = durability;
            }
        }
        if let Some((slot, count)) = ammo {
            let record = &mut state.slots[slot];
            record.quantity -= count;
            if record.quantity == 0 {
                *record = Default::default();
            }
            changed = true;
        }
        if changed {
            state.revision = state
                .revision
                .checked_add(1)
                .filter(|r| *r <= i64::MAX as u64)
                .ok_or_else(|| bad("wear revision overflow"))?;
        }
        Ok(true)
    }
}
impl Event {
    fn canonical(&self) -> Result<Vec<u8>> {
        if self.id == 0
            || self.id > i64::MAX as u64
            || self.revision > i64::MAX as u64
            || self.source == 0
            || self.source > i64::MAX as u64
            || self.tick > i64::MAX as u64
            || !(1..=2).contains(&self.mode)
            || self.damage > 1_000_000
            || (self.records.is_empty() && self.ammo.is_none())
            || self.ammo.as_ref().is_some_and(|(item, count)| self.mode != 1 || item.is_empty() || item.len() > 129 || !(1..=9999).contains(count))
            || self.records.len() > 16
            || self.records.windows(2).any(|w| w[0].0 >= w[1].0)
        {
            return Err(bad("wear event bounds"));
        }
        let mut b = b"N3WE".to_vec();
        for v in [self.id, self.revision, self.source, self.tick] {
            b.extend(v.to_le_bytes());
        }
        for v in [self.mode, self.damage, self.records.len() as u32] {
            b.extend(v.to_le_bytes());
        }
        let mut seen = BTreeSet::new();
        for (slot, item) in &self.records {
            if *slot >= 16
                || item.instance == 0
                || item.instance > i64::MAX as u64
                || !seen.insert(item.instance)
                || item.quantity != 1
                || !(1..=65535).contains(&item.durability)
                || item.item.is_empty()
                || item.item.len() > 129
            {
                return Err(bad("wear record bounds"));
            }
            let data = item.encode_to_vec();
            b.extend(slot.to_le_bytes());
            b.extend((data.len() as u32).to_le_bytes());
            b.extend(data);
        }
        // D-218: appended only when present, so an event without ammunition
        // keeps PQ-420's payload (a replayed one still matches its row).
        if let Some((item, count)) = &self.ammo {
            b.extend(b"AMMO");
            b.extend((item.len() as u32).to_le_bytes());
            b.extend(item.as_bytes());
            b.extend(count.to_le_bytes());
        }
        Ok(b)
    }
}
/// D-218: the index of the first bag slot (in slot order) holding `item`, if
/// it holds at least `count`; equipment and storage never count. Both KO
/// programs read that slot only (`KnightOnLine.exe` `004a29e0`,
/// `Ebenezer-official.exe` `004b0792`).
pub fn ammo_slot(state: &wire::BagState, item: &str, count: u32) -> Option<usize> {
    let slot = state.slots.iter().position(|s| s.instance != 0 && s.item == item)?;
    (state.slots[slot].quantity >= count).then_some(slot)
}
pub fn execute(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    bag: &inventory::Policy,
    policy: &Policy,
    reward: &str,
    event: &Event,
) -> Result<Outcome> {
    let payload = event.canonical()?;
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if t.query_opt("SELECT id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE",&[&s.id,&o.realm,&s.generation,&o.generation])?.is_none(){return Err(bad("stale wear session"));}
    let mut state = inventory::load(&mut t, s, o, bag, reward)?;
    if let Some(row)=t.query_opt("SELECT character_id,payload,committed,state FROM durability_operations WHERE realm=$1 AND event=$2",&[&o.realm,&(event.id as i64)])?{
  if row.get::<_,i64>(0)!=s.id||row.get::<_,Vec<u8>>(1)!=payload{return Err(bad("wear event conflict"));}
  return Ok(Outcome{committed:row.get(2),state:wire::BagState::decode(row.get::<_,Vec<u8>>(3).as_slice())?});
 }
    let committed = policy.apply(&mut state, event)?;
    if committed {
        bag.validate(&state)?;
        inventory::save(&mut t, s.id, &state)?;
    }
    t.execute("INSERT INTO durability_operations(realm,event,character_id,payload,committed,state) VALUES($1,$2,$3,$4,$5,$6)",&[&o.realm,&(event.id as i64),&s.id,&payload,&committed,&state.encode_to_vec()])?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    fault("before_commit");
    t.commit()?;
    fault("after_commit");
    Ok(Outcome { committed, state })
}
impl crate::accounts::Database {
    pub async fn wear(
        &self,
        o: std::sync::Arc<Owner>,
        s: Selected,
        bag: inventory::Policy,
        reward: String,
        event: Event,
    ) -> Result<Outcome> {
        self.call(move |c| {
            execute(
                c,
                &o,
                &s,
                &bag,
                bag.wear.as_ref().ok_or_else(|| bad("wear unavailable"))?,
                &reward,
                &event,
            )
        })
        .await
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn policy() -> Policy {
        Policy {
            scale: 0.1,
            items: vec![
                Item {
                    id: "test:blade".into(),
                    attack: 3,
                    defense: 0,
                },
                Item {
                    id: "test:shield".into(),
                    attack: 0,
                    defense: 2,
                },
                Item {
                    id: "test:ring".into(),
                    attack: 0,
                    defense: 0,
                },
            ],
        }
    }
    fn bag() -> wire::BagState {
        wire::BagState {
            revision: 7,
            equipment: vec![
                wire::ItemStack {
                    instance: 1,
                    item: "test:blade".into(),
                    quantity: 1,
                    durability: 2,
                },
                wire::ItemStack {
                    instance: 2,
                    item: "test:shield".into(),
                    quantity: 1,
                    durability: 80,
                },
                wire::ItemStack {
                    instance: 3,
                    item: "test:ring".into(),
                    quantity: 1,
                    durability: 10,
                },
            ],
            ..Default::default()
        }
    }
    #[test]
    fn ordinary_boundaries_instance_freeze_break_and_conflict() {
        let p = policy();
        for (d, n) in [
            (0, 0),
            (9, 0),
            (10, 1),
            (39, 1),
            (40, 2),
            (89, 2),
            (90, 3),
            (999, 9),
            (1000, 10),
            (1_000_000, 316),
        ] {
            assert_eq!(p.amount(d).unwrap(), n);
        }
        let mut expected = 0;
        for damage in 0..=1_000_000 {
            if damage >= 10 * (expected + 1) * (expected + 1) {
                expected += 1;
            }
            assert_eq!(p.amount(damage).unwrap(), expected);
        }
        assert!(p.amount(1_000_001).is_err());
        let mut s = bag();
        assert!(p.freeze(&s, 4, 5, 6, 1, 9, None).unwrap().is_none());
        let q = p.freeze(&s, 4, 5, 6, 1, 90, None).unwrap().unwrap();
        assert_eq!(q.records.len(), 1);
        assert_eq!(q.records[0].1.instance, 1);
        let before = s.clone();
        let mut changed = s.clone();
        changed.revision += 1;
        assert!(p.apply(&mut changed, &q).unwrap());
        assert_eq!(changed.equipment[0].durability, 0);
        assert_eq!(changed.equipment[1], before.equipment[1]);
        assert!(p.apply(&mut s, &q).unwrap());
        assert_eq!(s.equipment[0].durability, 0);
        assert_eq!(s.equipment[1].durability, 80);
        assert_eq!(s.equipment[2].durability, 10);
        assert_eq!(s.revision, 8);
        assert!(p.freeze(&s, 4, 5, 6, 1, 90, None).unwrap().is_none());
        let q = p.freeze(&s, 4, 5, 6, 2, 40, None).unwrap().unwrap();
        assert_eq!(q.records[0].1.instance, 2);
        assert!(p.apply(&mut s, &q).unwrap());
        assert_eq!(s.equipment[1].durability, 78);
        let mut q = p.freeze(&s, 4, 5, 6, 2, 40, None).unwrap().unwrap();
        q.records[0].1.item = "test:blade".into();
        assert!(p.apply(&mut s, &q).is_err());
    }
    #[test]
    fn loss_follows_the_struck_instance_across_moves_and_repairs() {
        let p = policy();
        let mut state = bag();
        let event = p.freeze(&state, 4, 5, 6, 1, 10, None).unwrap().unwrap();
        state.slots.push(state.equipment[0].clone());
        state.equipment[0].instance = 99;
        state.revision += 1;
        assert!(p.apply(&mut state, &event).unwrap());
        assert_eq!(state.slots[0].durability, 1);
        assert_eq!(state.equipment[0].durability, 2);
        state.slots.clear();
        let revision = state.revision;
        assert!(p.apply(&mut state, &event).unwrap());
        assert_eq!(state.revision, revision);
        assert_eq!(state.equipment[0].durability, 2);
        state.equipment[1].durability = 10;
        let event = p.freeze(&state, 7, 5, 8, 2, 40, None).unwrap().unwrap();
        state.equipment[1].durability = 80;
        state.revision += 1;
        assert!(p.apply(&mut state, &event).unwrap());
        assert_eq!(state.equipment[1].durability, 78);
    }

    /// PQ-421 (D-218): a shot's ammunition comes from the first bag slot
    /// holding it (equipment never counts); too few there and the event
    /// applies nothing, its wear included. A miss still commits it.
    #[test]
    fn ammunition_from_the_first_bag_slot() {
        let p = policy();
        let arrow = |instance, quantity| wire::ItemStack { instance, item: "test:arrow".into(), quantity, durability: 0 };
        let mut s = bag();
        s.slots = vec![Default::default(), arrow(10, 2), arrow(11, 50)];
        // A miss (no wear) with ammunition is still an event; without, none.
        assert!(p.freeze(&s, 4, 5, 6, 1, 0, None).unwrap().is_none());
        let miss = p.freeze(&s, 4, 5, 6, 1, 0, Some(("test:arrow", 1))).unwrap().unwrap();
        assert!(miss.records.is_empty());
        assert!(p.freeze(&s, 4, 5, 6, 2, 40, Some(("test:arrow", 1))).is_err(), "an incoming hit spends none");
        let mut t = s.clone();
        assert!(p.apply(&mut t, &miss).unwrap());
        assert_eq!((t.slots[1].quantity, t.slots[2].quantity, t.revision), (1, 50, 8));
        assert_eq!(t.equipment, s.equipment);
        assert!(p.apply(&mut t, &miss).unwrap());
        assert_eq!((t.slots[1].clone(), t.slots[2].quantity, t.revision), (wire::ItemStack::default(), 50, 9), "the emptied slot is vacant");
        // The next shot takes the next stack.
        assert!(p.apply(&mut t, &miss).unwrap());
        assert_eq!(t.slots[2].quantity, 49);
        // The first stack holding it is the one counted, as KO's: 2 there is
        // not enough for 3, although 52 are carried; nothing applies.
        let hit = p.freeze(&s, 4, 5, 6, 1, 90, Some(("test:arrow", 3))).unwrap().unwrap();
        assert_eq!(hit.records.len(), 1);
        let mut u = s.clone();
        assert!(!p.apply(&mut u, &hit).unwrap());
        assert_eq!(u, s, "neither wear nor ammunition");
        u.slots[1].quantity = 3;
        assert!(p.apply(&mut u, &hit).unwrap());
        assert_eq!((u.slots[1].clone(), u.equipment[0].durability), (wire::ItemStack::default(), 0));
        // None carried, or only an equipped one: refused.
        let mut v = s.clone();
        v.slots = vec![Default::default(); 3];
        v.equipment.push(arrow(12, 9));
        assert!(!p.apply(&mut v, &miss).unwrap());
        assert_eq!(ammo_slot(&s, "test:arrow", 2), Some(1));
        assert_eq!(ammo_slot(&s, "test:arrow", 3), None);
        assert_eq!(ammo_slot(&v, "test:arrow", 1), None);
        // The payload without ammunition is PQ-420's; with it, distinct.
        let plain = p.freeze(&s, 4, 5, 6, 1, 90, None).unwrap().unwrap();
        assert!(hit.canonical().unwrap().starts_with(&plain.canonical().unwrap()));
        assert_ne!(hit.canonical().unwrap(), plain.canonical().unwrap());
        assert!(!plain.canonical().unwrap().windows(4).any(|w| w == b"AMMO"));
        for bad in [("", 1), ("test:arrow", 0), ("test:arrow", 10000)] {
            let mut e = miss.clone();
            e.ammo = Some((bad.0.into(), bad.1));
            assert!(e.canonical().is_err(), "{bad:?}");
        }
    }

    #[test]
    #[ignore = "tests/wear_db.py supplies disposable PostgreSQL and package"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let bag = release.rules.inventory.as_ref().unwrap();
        let policy = bag.wear.as_ref().unwrap();
        let mut c = persistence::connect(&url)?;
        let realm = format!("wear-test-{}", std::process::id());
        let owner = "wear-audit";
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
                "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'Wear') RETURNING id",
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
        let mut state = read(&mut c)?;
        let equip = wire::BagRequest {
            operation: 5,
            request: "equip".into(),
            instance: state.slots[0].instance,
            ..Default::default()
        };
        state = inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &equip)?
            .state
            .unwrap();
        let event = policy.freeze(&state, 100, 101, 20, 1, 40, None)?.unwrap();
        c.batch_execute("CREATE FUNCTION fail_wear() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'rollback wear'; END $$; CREATE TRIGGER fail_wear BEFORE INSERT ON durability_operations FOR EACH ROW EXECUTE FUNCTION fail_wear()")?;
        assert!(execute(&mut c, &o, &s, bag, policy, &release.rules.item, &event).is_err());
        assert_eq!(read(&mut c)?, state);
        c.batch_execute(
            "DROP TRIGGER fail_wear ON durability_operations; DROP FUNCTION fail_wear()",
        )?;
        let mut forged = event.clone();
        forged.records[0].1.instance = state.slots[1].instance;
        assert!(execute(&mut c, &o, &s, bag, policy, &release.rules.item, &forged).is_err());
        assert_eq!(read(&mut c)?, state);
        let q = wire::BagRequest {
            operation: 1,
            request: "race-swap".into(),
            expected_revision: state.revision,
            source: 3,
            destination: 4,
            instance: state.slots[3].instance,
            ..Default::default()
        };
        let mut c2 = persistence::connect(&url)?;
        let (a, b) = std::thread::scope(|scope| {
            let job =
                scope.spawn(|| inventory::execute(&mut c2, &o, &s, bag, &release.rules.item, &q));
            let a = execute(&mut c, &o, &s, bag, policy, &release.rules.item, &event);
            (a, job.join().unwrap())
        });
        let (a, b) = (a?, b?);
        assert!(a.committed);
        assert!(b.status == "committed" || b.status == "revision_conflict");
        assert_eq!(
            read(&mut c)?.revision,
            state.revision + 1 + u64::from(b.status == "committed")
        );
        let original = a.clone();
        state = read(&mut c)?;
        let event2 = policy.freeze(&state, 102, 101, 21, 1, 90, None)?.unwrap();
        let takeoff = wire::BagRequest {
            operation: 6,
            request: "move-struck".into(),
            expected_revision: state.revision,
            instance: state.equipment[0].instance,
            ..Default::default()
        };
        state = inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &takeoff)?
            .state
            .unwrap();
        let slot = state
            .slots
            .iter()
            .position(|v| v.item.ends_with("/twohand"))
            .unwrap();
        let replace = wire::BagRequest {
            operation: 5,
            request: "replace-struck".into(),
            expected_revision: state.revision,
            source: slot as u32,
            instance: state.slots[slot].instance,
            ..Default::default()
        };
        state = inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &replace)?
            .state
            .unwrap();
        let replacement = state.equipment[0].clone();
        let mut event3 = event2.clone();
        event3.id = 103;
        let (a, b) = std::thread::scope(|scope| {
            let job =
                scope.spawn(|| execute(&mut c2, &o, &s, bag, policy, &release.rules.item, &event3));
            let a = execute(&mut c, &o, &s, bag, policy, &release.rules.item, &event2);
            (a, job.join().unwrap())
        });
        let (a, b) = (a?, b?);
        assert!(a.committed && b.committed);
        let latest = read(&mut c)?;
        assert_eq!(latest.slots[0].durability, 0);
        assert_eq!(latest.equipment[0], replacement);
        assert_eq!(latest.revision, state.revision + 1);
        drop(c);
        let mut c = persistence::connect(&url)?;
        let retry = execute(&mut c, &o, &s, bag, policy, &release.rules.item, &event)?;
        assert_eq!(retry.committed, original.committed);
        assert_eq!(retry.state, original.state);
        assert_eq!(read(&mut c)?, latest);
        let mut conflict = event.clone();
        conflict.damage += 1;
        assert!(execute(&mut c, &o, &s, bag, policy, &release.rules.item, &conflict).is_err());
        let mut stale = s.clone();
        stale.generation += 1;
        assert!(execute(&mut c, &o, &stale, bag, policy, &release.rules.item, &event).is_err());
        stale.id += 1000;
        assert!(execute(&mut c, &o, &stale, bag, policy, &release.rules.item, &event).is_err());
        let mut stale = o.clone();
        stale.generation += 1;
        assert!(execute(&mut c, &stale, &s, bag, policy, &release.rules.item, &event).is_err());
        assert!(c
            .execute(
                "UPDATE durability_operations SET committed=false WHERE realm=$1",
                &[&realm]
            )
            .is_err());
        assert_eq!(read(&mut c)?, latest);
        // PQ-421 (D-218): a shot's ammunition (here a stackable consumable of
        // the package) leaves in the same fenced transaction; a replay
        // returns the stored result; too few in the first slot holding it
        // commits nothing; the last one empties the slot.
        let stack = bag.items.iter().find(|i| i.stack > 1 && i.durability == 0).unwrap();
        let slot = latest.slots.iter().position(|v| v.item == stack.id).unwrap();
        let carried = latest.slots[slot].quantity;
        assert!(carried >= 2, "{carried}");
        let mut shot = policy.freeze(&latest, 104, 101, 22, 1, 0, Some((&stack.id, 1)))?.unwrap();
        shot.id = 104;
        let spent = execute(&mut c, &o, &s, bag, policy, &release.rules.item, &shot)?;
        assert!(spent.committed);
        let after = read(&mut c)?;
        assert_eq!((after.slots[slot].quantity, after.revision), (carried - 1, latest.revision + 1));
        let again = execute(&mut c, &o, &s, bag, policy, &release.rules.item, &shot)?;
        assert_eq!((again.committed, again.state.clone()), (true, spent.state.clone()));
        assert_eq!(read(&mut c)?, after, "a replay spends nothing");
        let mut greedy = policy.freeze(&after, 105, 101, 23, 1, 0, Some((&stack.id, carried)))?.unwrap();
        greedy.id = 105;
        let refused = execute(&mut c, &o, &s, bag, policy, &release.rules.item, &greedy)?;
        assert!(!refused.committed);
        assert_eq!(read(&mut c)?, after, "too few: nothing applied");
        let mut last = policy.freeze(&after, 106, 101, 24, 1, 0, Some((&stack.id, carried - 1)))?.unwrap();
        last.id = 106;
        assert!(execute(&mut c, &o, &s, bag, policy, &release.rules.item, &last)?.committed);
        let empty = read(&mut c)?;
        assert_eq!(empty.slots[slot], wire::ItemStack::default());
        println!("PASS ammunition leaves the first bag slot holding it in the strike's durable commit (PQ-421): {carried} -> {} -> 0, replay idempotent, too few commits nothing", carried - 1);
        Ok(())
    }
}

fn fault(phase: &str) {
    if std::env::var("N3E_WEAR_FAULT").ok().as_deref() == Some(phase) {
        eprintln!("WEAR_FAULT {phase}");
        std::process::exit(94);
    }
}
