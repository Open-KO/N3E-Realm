//! Only committed equipment can select public, package-defined cosmetic keys.
use crate::{
    content::{bad, Reader, Result},
    equipment, inventory, wire,
};
use std::{collections::BTreeMap, path::Path};
/// The keys by (item, equipment slot), and (RQ-201) each keyed item's
/// definition durability, its maximum (0 for an item without durability).
#[derive(Clone, Default)]
pub struct Policy(pub BTreeMap<(String, u32), u32>, pub BTreeMap<String, u32>);
impl Policy {
    pub fn load(path: &Path, gear: &equipment::Policy, bag: &inventory::Policy) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3V1" {
            return Err(bad("appearance magic"));
        }
        let n = r.u()?;
        if !(1..=128).contains(&n) {
            return Err(bad("appearance count"));
        }
        let mut rows = BTreeMap::new();
        for key in 1..=n {
            let item = r.string()?;
            let slot = r.u()?;
            if slot >= gear.slots.len() as u32
                || !gear
                    .items
                    .iter()
                    .any(|i| i.id == item && i.slots & (1 << slot) != 0)
                || rows.insert((item, slot), key).is_some()
            {
                return Err(bad("appearance mapping"));
            }
        }
        r.end()?;
        let maxima = rows
            .keys()
            .map(|(item, _)| {
                let max = bag
                    .items
                    .iter()
                    .find(|i| &i.id == item)
                    .map_or(0, |i| i.durability);
                (item.clone(), max)
            })
            .collect();
        Ok(Self(rows, maxima))
    }
    /// The worn records' keys and (RQ-201) their durability percents, in
    /// equipment slot order.
    fn worn<'a>(
        &'a self,
        bag: Option<&'a wire::BagState>,
    ) -> impl Iterator<Item = (u32, u32)> + 'a {
        bag.into_iter()
            .flat_map(|b| b.equipment.iter().enumerate())
            .filter_map(|(slot, i)| {
                if i.quantity != 1 {
                    return None;
                }
                let key = *self.0.get(&(i.item.clone(), slot as u32))?;
                Some((
                    key,
                    percent(i.durability, self.1.get(&i.item).copied().unwrap_or(0)),
                ))
            })
    }
    pub fn project(&self, bag: Option<&wire::BagState>) -> Vec<u32> {
        self.worn(bag).map(|(key, _)| key).collect()
    }
    /// RQ-201 (Q120): per projected key, in its order, the worn item's
    /// durability as a whole percent of its definition's maximum (the
    /// character list's `appearance_durability`).
    pub fn durability(&self, bag: Option<&wire::BagState>) -> Vec<u32> {
        self.worn(bag).map(|(_, percent)| percent).collect()
    }
}

/// RQ-201 (Q120): `durability` x 100 / `maximum`, rounded down, as 1298's
/// select hall takes an item's (005fca40); 100 for an item without a maximum,
/// which KO gives no overlay, and never above 100.
pub fn percent(durability: u32, maximum: u32) -> u32 {
    if maximum == 0 {
        return 100;
    }
    (u64::from(durability) * 100 / u64::from(maximum)).min(100) as u32
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_projection_excludes_private_bags_and_clears_removed_gear() {
        let p = Policy(
            BTreeMap::from([
                (("test:item/sword".into(), 0), 1),
                (("test:item/shield".into(), 1), 2),
            ]),
            BTreeMap::from([
                ("test:item/sword".into(), 80),
                ("test:item/shield".into(), 0),
            ]),
        );
        let sword = wire::ItemStack {
            item: "test:item/sword".into(),
            quantity: 1,
            instance: 999,
            durability: 50,
        };
        let mut bag = wire::BagState {
            coins: 123,
            slots: vec![sword.clone()],
            equipment: vec![wire::ItemStack::default(); 2],
            ..Default::default()
        };
        assert!(p.project(Some(&bag)).is_empty());
        bag.equipment[0] = sword.clone();
        assert_eq!(p.project(Some(&bag)), [1]);
        // RQ-201: 50 of the sword's 80, rounded down.
        assert_eq!(p.durability(Some(&bag)), [62]);
        bag.equipment[0].durability = 0;
        assert_eq!(p.project(Some(&bag)), [1]);
        assert_eq!(p.durability(Some(&bag)), [0]);
        bag.equipment[0] = wire::ItemStack::default();
        bag.equipment[1] = sword;
        assert!(p.project(Some(&bag)).is_empty());
        assert!(p.durability(Some(&bag)).is_empty());
        assert!(p.project(None).is_empty());
        assert!(p.durability(None).is_empty());
    }

    #[test]
    fn durability_is_parallel_to_the_keys() {
        let p = Policy(
            BTreeMap::from([
                (("test:item/sword".into(), 0), 1),
                (("test:item/shield".into(), 1), 2),
            ]),
            BTreeMap::from([
                ("test:item/sword".into(), 80),
                ("test:item/shield".into(), 0),
            ]),
        );
        let worn = |item: &str, durability| wire::ItemStack {
            item: item.into(),
            quantity: 1,
            instance: 1,
            durability,
        };
        let bag = wire::BagState {
            equipment: vec![worn("test:item/sword", 24), worn("test:item/shield", 7)],
            ..Default::default()
        };
        assert_eq!(p.project(Some(&bag)), [1, 2]);
        // 24 of 80 is 30 %; the shield's definition has no durability: 100.
        assert_eq!(p.durability(Some(&bag)), [30, 100]);
        assert_eq!(percent(80, 80), 100);
        assert_eq!(percent(56, 80), 70);
        assert_eq!(percent(57, 80), 71);
        assert_eq!(percent(90, 80), 100);
        assert_eq!(percent(u32::MAX, 1), 100);
        assert_eq!(percent(5, 0), 100);
    }
}
