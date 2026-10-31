//! Package-owned merchant rules; simulation admission supplies current actor state.
use crate::{
    accounts::Selected,
    content::{bad, Reader, Result},
    inventory, wire,
};
use std::{collections::BTreeSet, path::Path, time::Instant};
#[derive(Clone, Debug)]
pub struct Price {
    pub item: String,
    pub weight: u32,
    pub price: u32,
    pub divisor: u32,
}
#[derive(Clone, Debug)]
pub struct Shop {
    pub id: String,
    pub _label: String,
    pub position: [f32; 3],
    pub radius: f32,
    pub remote_sell: bool,
    pub items: Vec<String>,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub repair: Option<crate::repair::Policy>,
    pub weight_limit: u32,
    pub max_quantity: u32,
    pub bulk_price: u32,
    pub bulk_quantity: u32,
    pub items: Vec<Price>,
    pub shops: Vec<Shop>,
}
#[derive(Clone)]
pub struct Admission {
    pub selected: Selected,
    pub issued: Instant,
}
/// How long a merchant admission stays valid until its bag commit (D-132 lists it among
/// the wall-time admission windows). Checked at admission and again before COMMIT
/// (`inventory::execute_inner_at`).
pub const ADMISSION_WINDOW: std::time::Duration = std::time::Duration::from_secs(2);
impl Policy {
    pub fn load(path: &Path, game: &str, bag: &inventory::Policy, reward: &str) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3O1" {
            return Err(bad("commerce magic"));
        }
        let mut p = Self {
            repair: None,
            weight_limit: r.u()?,
            max_quantity: r.u()?,
            bulk_price: r.u()?,
            bulk_quantity: r.u()?,
            items: vec![],
            shops: vec![],
        };
        if !(1..=i32::MAX as u32).contains(&p.weight_limit)
            || !(1..=9999).contains(&p.max_quantity)
            || p.bulk_price > i32::MAX as u32
            || !(1..=p.max_quantity).contains(&p.bulk_quantity)
        {
            return Err(bad("commerce bounds"));
        }
        let n = r.u()?;
        if n as usize != bag.items.len() {
            return Err(bad("commerce definition coverage"));
        }
        let mut ids = BTreeSet::new();
        for _ in 0..n {
            let i = Price {
                item: r.string()?,
                weight: r.u()?,
                price: r.u()?,
                divisor: r.u()?,
            };
            if !ids.insert(i.item.clone())
                || !bag.items.iter().any(|d| d.id == i.item)
                || i.weight > 1000000
                || !(1..=i32::MAX as u32).contains(&i.price)
                || !(1..=10000).contains(&i.divisor)
            {
                return Err(bad("commerce item"));
            }
            p.items.push(i);
        }
        let n = r.u()?;
        if !(1..=64).contains(&n) {
            return Err(bad("shop count"));
        }
        ids.clear();
        for _ in 0..n {
            let id = r.string()?;
            let label = r.string()?;
            let position = [r.f()?, r.f()?, r.f()?];
            let radius = r.f()?;
            let remote = r.u()?;
            let n = r.u()?;
            if !inventory::id(&id, game)
                || !ids.insert(id.clone())
                || label.len() > 64
                || !label.bytes().all(|c| (32..=126).contains(&c))
                || position.iter().any(|v| v.abs() > 1000.)
                || !(0.5..=20.).contains(&radius)
                || remote > 1
                || !(1..=64).contains(&n)
            {
                return Err(bad("shop bounds"));
            }
            let mut items = Vec::new();
            for _ in 0..n {
                let item = r.string()?;
                if item == reward
                    || items.contains(&item)
                    || !bag.items.iter().any(|i| i.id == item)
                {
                    return Err(bad("shop offer"));
                }
                items.push(item);
            }
            p.shops.push(Shop {
                id,
                _label: label,
                position,
                radius,
                remote_sell: remote != 0,
                items,
            });
        }
        r.end()?;
        Ok(p)
    }
    pub fn admit(&self, s: &Selected, q: &wire::BagRequest) -> bool {
        // The confirmed repair leaf and receiver have no merchant range check.
        // Session/realm fences still apply; unlike a purchase this is not proximity admission.
        if matches!(q.operation,4|8) {
            return self.repair.is_some();
        }
        if s.dead || s.entity.health == 0 {
            return false;
        }
        self.shops.iter().any(|shop| {
            shop.id == q.service
                && shop.items.contains(&q.item)
                && ((q.operation == 3 && shop.remote_sell)
                    || ((s.entity.x - shop.position[0]).powi(2)
                        + (s.entity.z - shop.position[2]).powi(2)
                        <= shop.radius * shop.radius))
        })
    }
    pub fn apply(
        &self,
        t: &mut postgres::Transaction<'_>,
        bag: &inventory::Policy,
        state: &mut wire::BagState,
        q: &wire::BagRequest,
    ) -> Result<&'static str> {
        let Some(def) = bag.items.iter().find(|i| i.id == q.item) else {
            return Ok("unknown_item");
        };
        let Some(price) = self.items.iter().find(|i| i.item == q.item) else {
            return Ok("unknown_item");
        };
        if matches!(q.operation,4|8) {
            return Ok(self.repair.as_ref().map_or("repair_unavailable", |r| {
                r.apply(bag, state, q, price.price)
            }));
        }
        if !(1..=self.max_quantity).contains(&q.quantity) || q.quantity > def.stack {
            return Ok("quantity_limit");
        }
        let slot = &state.slots[q.source as usize];
        if q.operation == 2 {
            if price.price > self.bulk_price && q.quantity > self.bulk_quantity {
                return Ok("quantity_limit");
            }
            if slot.instance != 0 && (slot.item != q.item || def.stack == 1) {
                return Ok("occupied_slot");
            }
            if slot.quantity + q.quantity > def.stack {
                return Ok("stack_full");
            }
            let cost = price.price as u64 * q.quantity as u64;
            if cost > state.coins as u64 {
                return Ok("insufficient_currency");
            }
            let weight: u64 = state
                .slots
                .iter().chain(&state.equipment)
                .map(|s| {
                    self.items
                        .iter()
                        .find(|i| i.item == s.item)
                        .map_or(0, |i| i.weight as u64 * s.quantity as u64)
                })
                .sum();
            if weight + price.weight as u64 * q.quantity as u64 > self.weight_limit as u64 {
                return Ok("weight_limit");
            }
            let slot = &mut state.slots[q.source as usize];
            if slot.instance == 0 {
                slot.instance = inventory::serial(t)?;
                slot.item = q.item.clone();
            }
            slot.quantity += q.quantity;
            slot.durability = def.durability;
            state.coins -= cost as u32;
        } else {
            if slot.item != q.item || q.quantity > slot.quantity {
                return Ok("insufficient_items");
            }
            let credit = (price.price as u64 * q.quantity as u64) / (price.divisor as u64);
            if state.coins as u64 + credit > bag.limit as u64 {
                return Ok("currency_limit");
            }
            state.coins += credit as u32;
            let slot = &mut state.slots[q.source as usize];
            slot.quantity -= q.quantity;
            if slot.quantity == 0 {
                *slot = wire::ItemStack::default();
            }
        }
        Ok("committed")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{accounts::Owner, persistence};
    #[test]
    #[ignore = "tests/commerce_db.py supplies disposable PostgreSQL and package"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let policy = release.rules.commerce.as_ref().unwrap();
        let bag = release.rules.inventory.as_ref().unwrap();
        let mut c = persistence::connect(&url)?;
        let realm = format!("test-commerce-{}", std::process::id());
        let owner = "commerce-audit";
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
        let id:i64=c.query_one("INSERT INTO characters(account_id,realm,name) VALUES($1,$2,'Shopper') RETURNING id", &[&account,&realm])?.get(0);
        crate::settlements::convert(
            &mut c,
            &o,
            release.rules.progression.as_ref().unwrap(),
            &release.game,
            20,
        )?;
        c.execute("UPDATE characters SET online=true,session_generation=1,realm_generation=$2 WHERE id=$1", &[&id,&generation])?;
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
        let baseline = inventory::execute(
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
            operation: 2,
            request: "parallel-a".into(),
            source: 2,
            service: policy.shops[0].id.clone(),
            item: policy.shops[0].items[1].clone(),
            quantity: 1,
            ..Default::default()
        };
        let a = Admission {
            selected: s.clone(),
            issued: Instant::now(),
        };
        // Admissions are aged by a fixed clock, never by how long PostgreSQL takes: a
        // loaded disposable cluster can hold one commit past the window (PQ-289, PQ-291).
        let issued = a.issued;
        let late = issued + ADMISSION_WINDOW + std::time::Duration::from_nanos(1);
        let claimed = |c: &mut postgres::Client| -> Result<i64> {
            Ok(c.query_one(
                "SELECT count(*) FROM bag_operations WHERE character_id=$1",
                &[&id],
            )?
            .get(0))
        };
        // Past the window at the admission check: refused, nothing durable.
        let mut expired = a.clone();
        expired.issued -= std::time::Duration::from_secs(3);
        assert_eq!(
            inventory::execute_inner_at(
                &mut c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &q,
                Some((policy, &expired)),
                &|| issued,
            )
            .unwrap_err()
            .to_string(),
            "expired merchant admission"
        );
        // Fresh at the admission check, past the window at COMMIT: refused and rolled
        // back, so the bag is unchanged and the request ID stays unclaimed.
        let reads = std::cell::Cell::new(0);
        let error = inventory::execute_inner_at(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &q,
            Some((policy, &a)),
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
            ("expired merchant commit", 2)
        );
        assert_eq!(claimed(&mut c)?, 0);
        assert_eq!(
            inventory::execute(
                &mut c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &wire::BagRequest::default()
            )?
            .state
            .unwrap(),
            baseline
        );
        let mut remote = a.clone();
        remote.selected.entity.x = 100.;
        assert!(inventory::execute_inner_at(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &q,
            Some((policy, &remote)),
            &|| issued,
        )
        .is_err());
        c.execute(
            "UPDATE characters SET life_revision=life_revision+1 WHERE id=$1",
            &[&id],
        )?;
        assert!(inventory::execute_inner_at(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &q,
            Some((policy, &a)),
            &|| issued,
        )
        .is_err());
        c.execute(
            "UPDATE characters SET life_revision=life_revision-1 WHERE id=$1",
            &[&id],
        )?;
        assert_eq!(
            inventory::execute(
                &mut c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &wire::BagRequest::default()
            )?
            .state
            .unwrap(),
            baseline
        );
        let mut c2 = persistence::connect(&url)?;
        let mut other = q.clone();
        other.request = "parallel-b".into();
        // Both run exactly at the window's end, which is still inside it (inclusive).
        let (x, y) = std::thread::scope(|scope| {
            let job = scope.spawn(|| {
                inventory::execute_inner_at(
                    &mut c2,
                    &o,
                    &s,
                    bag,
                    &release.rules.item,
                    &other,
                    Some((policy, &a)),
                    &|| issued + ADMISSION_WINDOW,
                )
            });
            let x = inventory::execute_inner_at(
                &mut c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &q,
                Some((policy, &a)),
                &|| issued + ADMISSION_WINDOW,
            );
            (x, job.join().unwrap())
        });
        let x = x?;
        let y = y?;
        assert!(
            (x.status == "committed" && y.status == "revision_conflict")
                || (y.status == "committed" && x.status == "revision_conflict")
        );
        let current = inventory::execute(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &wire::BagRequest::default(),
        )?
        .state
        .unwrap();
        assert_eq!(current.revision, 1);
        assert_eq!(current.coins, 87);
        assert_eq!(current.slots[2].quantity, 1);
        // Original outcome remains queryable after admission expires and after moving.
        assert_eq!(
            inventory::execute_inner_at(
                &mut c,
                &o,
                &s,
                bag,
                &release.rules.item,
                &q,
                Some((policy, &expired)),
                &|| issued,
            )?,
            x
        );
        let mut stale = s.clone();
        stale.generation += 1;
        assert!(inventory::execute_inner_at(
            &mut c,
            &o,
            &stale,
            bag,
            &release.rules.item,
            &q,
            Some((policy, &a)),
            &|| issued,
        )
        .is_err());
        assert!(c
            .execute(
                "UPDATE bag_operations SET request='rewrite' WHERE character_id=$1",
                &[&id]
            )
            .is_err());
        persistence::release(&mut c, &o.realm, &o.owner, generation)?;
        assert!(inventory::execute_inner_at(
            &mut c,
            &o,
            &s,
            bag,
            &release.rules.item,
            &q,
            Some((policy, &a)),
            &|| issued,
        )
        .is_err());
        println!("PASS merchant expired admission, stale life/session/realm, concurrent revision conservation and immutable original results");
        Ok(())
    }
}
