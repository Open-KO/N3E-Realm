//! Only committed equipment can select public, package-defined cosmetic keys.
use crate::{
    content::{bad, Reader, Result},
    equipment, wire,
};
use std::{collections::BTreeMap, path::Path};
#[derive(Clone, Default)]
pub struct Policy(pub BTreeMap<(String, u32), u32>);
impl Policy {
    pub fn load(path: &Path, gear: &equipment::Policy) -> Result<Self> {
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
        Ok(Self(rows))
    }
    pub fn project(&self, bag: Option<&wire::BagState>) -> Vec<u32> {
        bag.into_iter()
            .flat_map(|b| b.equipment.iter().enumerate())
            .filter_map(|(slot, i)| {
                if i.quantity != 1 {
                    return None;
                }
                self.0.get(&(i.item.clone(), slot as u32)).copied()
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_projection_excludes_private_bags_and_clears_removed_gear() {
        let p = Policy(BTreeMap::from([
            (("test:item/sword".into(), 0), 1),
            (("test:item/shield".into(), 1), 2),
        ]));
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
        bag.equipment[0].durability = 0;
        assert_eq!(p.project(Some(&bag)), [1]);
        bag.equipment[0] = wire::ItemStack::default();
        bag.equipment[1] = sword;
        assert!(p.project(Some(&bag)).is_empty());
        assert!(p.project(None).is_empty());
    }
}
