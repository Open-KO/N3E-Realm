//! Whole equipment records. Package data owns slots, exclusions and requirements.
use crate::{
    content::{bad, Reader, Result},
    inventory, wire,
};
use std::{collections::BTreeSet, path::Path};
#[derive(Clone, Debug)]
pub struct Item {
    pub id: String,
    pub slots: u32,
    pub blocks: u32,
    pub title: u32,
    pub race: u32,
    pub attributes: [u32; 5],
    pub swappable: bool,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub title: u32,
    pub race: u32,
    pub attributes: [u32; 5],
    pub slots: Vec<String>,
    pub items: Vec<Item>,
}
impl Policy {
    pub fn load(path: &Path, bag: &inventory::Policy) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3Q1" {
            return Err(bad("equipment magic"));
        }
        let race = r.u()?;
        let title = r.u()?;
        let attributes = [r.u()?, r.u()?, r.u()?, r.u()?, r.u()?];
        let n = r.u()?;
        if title > 255
            || race > 255
            || attributes.iter().any(|v| *v > 255)
            || !(1..=16).contains(&n)
        {
            return Err(bad("equipment bounds"));
        }
        let mut slots = vec![];
        for _ in 0..n {
            let s = r.string()?;
            if s.len() > 32 || !s.bytes().all(|c| (32..=126).contains(&c)) || slots.contains(&s) {
                return Err(bad("equipment slot"));
            }
            slots.push(s);
        }
        let mask = (1u32 << n) - 1;
        let count = r.u()?;
        if !(1..=64).contains(&count) {
            return Err(bad("equipment count"));
        }
        let mut items = vec![];
        let mut ids = BTreeSet::new();
        for _ in 0..count {
            let id = r.string()?;
            let slots = r.u()?;
            let blocks = r.u()?;
            let title = r.u()?;
            let race = r.u()?;
            let attributes = [r.u()?, r.u()?, r.u()?, r.u()?, r.u()?];
            let swap = r.u()?;
            if !ids.insert(id.clone())
                || !bag.items.iter().any(|i| i.id == id && i.stack == 1)
                || slots == 0
                || (slots | blocks) & !mask != 0
                || slots & blocks != 0
                || title > 255
                || race > 255
                || attributes.iter().any(|v| *v > 255)
                || swap > 1
            {
                return Err(bad("equipment definition"));
            }
            items.push(Item {
                id,
                slots,
                blocks,
                title,
                race,
                attributes,
                swappable: swap != 0,
            });
        }
        r.end()?;
        Ok(Self {
            title,
            race,
            attributes,
            slots,
            items,
        })
    }
    fn item(&self, id: &str) -> Option<&Item> {
        self.items.iter().find(|i| i.id == id)
    }
    fn eligible(&self, i: &Item) -> bool {
        i.title <= self.title
            && (i.race == 0 || i.race == self.race)
            && i.attributes
                .iter()
                .zip(self.attributes)
                .all(|(need, base)| *need <= base)
    }
    pub fn validate(&self, s: &wire::BagState) -> Result<()> {
        if s.equipment.len() != self.slots.len() {
            return Err(bad("equipment shape"));
        }
        for (slot, record) in s
            .equipment
            .iter()
            .enumerate()
            .filter(|(_, r)| r.instance != 0)
        {
            let i = self
                .item(&record.item)
                .ok_or_else(|| bad("unknown equipped item"))?;
            if record.quantity != 1
                || i.slots & (1 << slot) == 0
                || s.equipment
                    .iter()
                    .enumerate()
                    .any(|(j, r)| r.instance != 0 && i.blocks & (1 << j) != 0)
            {
                return Err(bad("equipment placement"));
            }
        }
        Ok(())
    }
    pub fn apply(&self, s: &mut wire::BagState, q: &wire::BagRequest) -> &'static str {
        let a = q.source as usize;
        let b = q.destination as usize;
        match q.operation {
            5 => {
                if a >= s.slots.len() || b >= s.equipment.len() {
                    return "invalid_slot";
                }
                let Some(i) = self.item(&s.slots[a].item) else {
                    return "not_equippable";
                };
                if i.slots & (1 << b) == 0 {
                    return "incompatible_slot";
                }
                if !self.eligible(i) {
                    return "requirements";
                }
                let displaced: Vec<_> = s
                    .equipment
                    .iter()
                    .enumerate()
                    .filter(|(j, r)| {
                        r.instance != 0
                            && (*j == b
                                || i.blocks & (1 << j) != 0
                                || self
                                    .item(&r.item)
                                    .is_some_and(|other| other.blocks & (1 << b) != 0))
                    })
                    .map(|(j, _)| j)
                    .collect();
                if displaced.len() > 1 {
                    return "equipment_full";
                }
                let item = std::mem::take(&mut s.slots[a]);
                if let Some(j) = displaced.first() {
                    s.slots[a] = std::mem::take(&mut s.equipment[*j]);
                }
                s.equipment[b] = item;
            }
            6 => {
                if a >= s.equipment.len() || b >= s.slots.len() {
                    return "invalid_slot";
                }
                if s.slots[b].instance != 0 {
                    return "occupied_slot";
                }
                s.slots[b] = std::mem::take(&mut s.equipment[a]);
            }
            7 => {
                if a >= s.equipment.len() || b >= s.equipment.len() || a == b {
                    return "invalid_slot";
                }
                let Some(i) = self.item(&s.equipment[a].item) else {
                    return "not_equippable";
                };
                if i.slots & (1 << b) == 0 {
                    return "incompatible_slot";
                }
                if !self.eligible(i) {
                    return "requirements";
                }
                if s.equipment[b].instance != 0
                    && !self
                        .item(&s.equipment[b].item)
                        .is_some_and(|i| i.swappable && i.slots & (1 << a) != 0)
                {
                    return "occupied_slot";
                }
                // Validate the candidate before publishing either record.
                let mut next = s.clone();
                next.equipment.swap(a, b);
                if self.validate(&next).is_err() {
                    return "incompatible_slot";
                }
                *s = next;
            }
            _ => return "invalid_operation",
        }
        "committed"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        accounts::{Owner, Selected},
        persistence,
    };
    #[test]
    #[ignore = "tests/equipment_db.py supplies disposable PostgreSQL and package"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let bag = release.rules.inventory.as_deref().unwrap();
        let mut c = persistence::connect(&url)?;
        let realm = format!("equipment-test-{}", std::process::id());
        let owner = "equipment-audit";
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
        let id:i64=c.query_one("INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'Equipment') RETURNING id",&[&account,&realm])?.get(0);
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
        let state = inventory::execute(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &wire::BagRequest::default(),
        )?
        .state
        .unwrap();
        let q = wire::BagRequest {
            operation: 5,
            request: "parallel-a".into(),
            source: 0,
            destination: 0,
            instance: state.slots[0].instance,
            ..Default::default()
        };
        let mut other = q.clone();
        other.request = "parallel-b".into();
        other.destination = 1;
        let mut c2 = persistence::connect(&url)?;
        let (a, b) = std::thread::scope(|scope| {
            let job = scope
                .spawn(|| inventory::execute(&mut c2, &o, &s, bag, &release.rules.item, &other));
            let a = inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &q);
            (a, job.join().unwrap())
        });
        let (a, b) = (a?, b?);
        assert!(
            (a.status == "committed" && b.status == "revision_conflict")
                || (b.status == "committed" && a.status == "revision_conflict")
        );
        let before = inventory::execute(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &wire::BagRequest::default(),
        )?
        .state
        .unwrap();
        assert_eq!(
            before.equipment.iter().filter(|i| i.instance != 0).count(),
            1
        );
        // A later reward must preserve equipment while adding exactly one owned record.
        {
            let mut t = c.transaction()?;
            assert!(inventory::grant_existing(
                &mut t,
                &realm,
                id,
                &release.rules.item
            )?);
            t.commit()?;
        }
        let after = inventory::execute(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &wire::BagRequest::default(),
        )?
        .state
        .unwrap();
        assert_eq!(before.equipment, after.equipment);
        assert_eq!(after.revision, before.revision + 1);
        assert_eq!(
            inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &q)?,
            a
        );
        let mut conflict = q.clone();
        conflict.destination = 3;
        assert_eq!(
            inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &conflict)?.status,
            "request_conflict"
        );
        let mut stale = s.clone();
        stale.generation += 1;
        assert!(inventory::execute(&mut c, &o, &stale, bag, &release.rules.item, &q).is_err());
        // Original test stacks exercise the same durable path as a drag. Fill
        // every other slot: overflow must survive even with no spare capacity.
        let potion=bag.items.iter().find(|i|i.stack>1).unwrap();
        let mut t=c.transaction()?;
        let mut stacks=inventory::load(&mut t,&s,&o,bag,&release.rules.item)?;
        for record in &mut stacks.slots {*record=wire::ItemStack{instance:inventory::serial(&mut t)?,item:potion.id.clone(),quantity:potion.stack,durability:potion.durability};}
        stacks.slots[0].quantity=5;stacks.slots[1].quantity=potion.stack-2;
        inventory::save(&mut t,s.id,&stacks)?;t.commit()?;
        let total=stacks.slots.iter().map(|v|v.quantity).sum::<u32>();
        let merge=wire::BagRequest{operation:1,request:"stack-merge".into(),expected_revision:stacks.revision,source:0,destination:1,instance:stacks.slots[0].instance,..Default::default()};
        let merged=inventory::execute(&mut c,&o,&s,bag,&release.rules.item,&merge)?;
        assert_eq!(merged.status,"committed");let state=merged.state.as_ref().unwrap();
        assert_eq!(state.slots[0].quantity,3);assert_eq!(state.slots[1].quantity,potion.stack);
        assert_eq!(state.slots.iter().map(|v|v.quantity).sum::<u32>(),total);
        assert_eq!(inventory::execute(&mut c,&o,&s,bag,&release.rules.item,&merge)?,merged);
        let mut stale_merge=merge.clone();stale_merge.request="stack-stale".into();
        assert_eq!(inventory::execute(&mut c,&o,&s,bag,&release.rules.item,&stale_merge)?.status,"revision_conflict");
        let mut different=merge.clone();different.destination=2;
        assert_eq!(inventory::execute(&mut c,&o,&s,bag,&release.rules.item,&different)?.status,"request_conflict");
        drop(c);c=persistence::connect(&url)?;
        assert_eq!(inventory::execute(&mut c,&o,&s,bag,&release.rules.item,&wire::BagRequest::default())?.state,merged.state);
        println!("PASS durable full-bag stack overflow, quantities, identities, immutable retries, conflicts and reconnect");
        let mut absent = bag.clone();
        absent.equipment = None;
        absent.hash = vec![0; 32];
        assert!(inventory::check_start(&mut c, &realm, Some(&absent)).is_err());
        persistence::release(&mut c, &realm, owner, generation)?;
        assert!(inventory::execute(&mut c, &o, &s, bag, &release.rules.item, &q).is_err());
        Ok(())
    }
}
