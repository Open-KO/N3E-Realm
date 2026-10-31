//! Bounded equipment-derived polynomial stats. All tuning and category IDs are package data.
use crate::{
    content::{bad, Reader, Result},
    equipment, wire,
};
use std::{collections::BTreeSet, path::Path};
#[derive(Clone, Debug)]
pub struct Polynomial {
    coefficient: f64,
    linear: f64,
    divisor: u32,
    base: u32,
    attribute: usize,
    offset: u32,
}
#[derive(Clone, Debug)]
pub struct Category {
    id: String,
    coefficient: f64,
    dexterity: bool,
    offhand: u32,
}
#[derive(Clone, Debug)]
pub struct Item {
    id: String,
    category: usize,
    attack: u32,
    defense: u32,
    health: u32,
    resource: u32,
    accuracy: u32,
    evasion: u32,
    attributes: [u32; 5],
}
#[derive(Clone, Debug)]
pub struct Policy {
    primary: usize,
    secondary: usize,
    dual: bool,
    dexterity: bool,
    floor: u32,
    base: u32,
    offset: u32,
    broken: u32,
    raw_broken: u32,
    strength_threshold: u32,
    stamina_threshold: u32,
    weight: u32,
    rate_initial: u32,
    secondary_scale: f64,
    linear: f64,
    defense: f64,
    accuracy: f64,
    evasion: f64,
    strength_attack: f64,
    stamina_defense: f64,
    rate_scale: f64,
    rate_base: f64,
    health: Polynomial,
    mana: Polynomial,
    stamina: Polynomial,
    categories: Vec<Category>,
    items: Vec<Item>,
}
impl Policy {
    pub fn load(path: &Path, gear: &equipment::Policy, game: &str) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3Y1" {
            return Err(bad("stats magic"));
        }
        let mut ints = [0; 13];
        for (i, hi) in ints
            .iter_mut()
            .zip([15, 15, 1, 1, 100, 100, 255, 100, 100, 255, 255, 1000, 10000])
        {
            *i = r.u()?;
            if *i > hi {
                return Err(bad("stats integer"));
            }
        }
        if ints[0] == ints[1]
            || ints[0] as usize >= gear.slots.len()
            || ints[1] as usize >= gear.slots.len()
            || ints[7] == 0
            || ints[8] == 0
        {
            return Err(bad("stats slots/divisor"));
        }
        let mut floats = [0.; 9];
        for (v, hi) in floats
            .iter_mut()
            .zip([1., 1., 10., 1., 1., 10., 10., 1., 100.])
        {
            *v = r.f()? as f64;
            if !(0. ..=hi).contains(v) {
                return Err(bad("stats coefficient"));
            }
        }
        let mut polynomial = |double: bool| -> Result<Polynomial> {
            let coefficient = r.f()? as f64;
            let linear = if double {
                f64::from_le_bytes(r.take(8)?.try_into()?)
            } else {
                r.f()? as f64
            };
            let divisor = r.u()?;
            let base = r.u()?;
            let attribute = r.u()? as usize;
            let offset = r.u()?;
            if !(0. ..=1.).contains(&coefficient)
                || !linear.is_finite()
                || !(0. ..=1.).contains(&linear)
                || !(1..=100).contains(&divisor)
                || base > 10000
                || attribute > 4
                || offset > 255
            {
                return Err(bad("stats polynomial"));
            }
            Ok(Polynomial {
                coefficient,
                linear,
                divisor,
                base,
                attribute,
                offset,
            })
        };
        let health = polynomial(true)?;
        let mana = polynomial(false)?;
        let stamina = polynomial(false)?;
        if mana.coefficient == 0. && stamina.coefficient == 0. {
            return Err(bad("resource polynomial missing"));
        }
        let n = r.u()?;
        if !(1..=32).contains(&n) {
            return Err(bad("stats category count"));
        }
        let mut categories = vec![];
        let mut ids = BTreeSet::new();
        for _ in 0..n {
            let id = r.string()?;
            let coefficient = r.f()? as f64;
            let dexterity = r.u()?;
            let offhand = r.u()?;
            if !ids.insert(id.clone())
                || !crate::inventory::id(&id, game)
                || !(0. ..=1.).contains(&coefficient)
                || dexterity > 1
                || offhand > 2
            {
                return Err(bad("stats category"));
            }
            categories.push(Category {
                id,
                coefficient,
                dexterity: dexterity != 0,
                offhand,
            });
        }
        let n = r.u()?;
        if n as usize != gear.items.len() {
            return Err(bad("stats coverage"));
        }
        ids.clear();
        let mut items = vec![];
        for _ in 0..n {
            let id = r.string()?;
            let category = r.string()?;
            let category = categories
                .iter()
                .position(|c| c.id == category)
                .ok_or_else(|| bad("stats category reference"))?;
            if !ids.insert(id.clone()) || !gear.items.iter().any(|i| i.id == id) {
                return Err(bad("stats item reference"));
            }
            let mut values = [0; 11];
            for (v, hi) in values.iter_mut().zip([
                10000, 10000, 10000, 10000, 1000, 1000, 255, 255, 255, 255, 255,
            ]) {
                *v = r.u()?;
                if *v > hi {
                    return Err(bad("stats bonus"));
                }
            }
            items.push(Item {
                id,
                category,
                attack: values[0],
                defense: values[1],
                health: values[2],
                resource: values[3],
                accuracy: values[4],
                evasion: values[5],
                attributes: values[6..].try_into().unwrap(),
            });
        }
        r.end()?;
        Ok(Self {
            primary: ints[0] as usize,
            secondary: ints[1] as usize,
            dual: ints[2] != 0,
            dexterity: ints[3] != 0,
            floor: ints[4],
            base: ints[5],
            offset: ints[6],
            broken: ints[7],
            raw_broken: ints[8],
            strength_threshold: ints[9],
            stamina_threshold: ints[10],
            weight: ints[11],
            rate_initial: ints[12],
            secondary_scale: floats[0],
            linear: floats[1],
            defense: floats[2],
            accuracy: floats[3],
            evasion: floats[4],
            strength_attack: floats[5],
            stamina_defense: floats[6],
            rate_scale: floats[7],
            rate_base: floats[8],
            health,
            mana,
            stamina,
            categories,
            items,
        })
    }
    pub fn calculate(
        &self,
        gear: &equipment::Policy,
        records: &[wire::ItemStack],
        level: u32,
    ) -> Result<wire::DerivedStats> {
        if records.len() != gear.slots.len() || !(1..=255).contains(&level) {
            return Err(bad("stats input"));
        }
        let mut attributes = gear.attributes;
        let (mut attack, mut defense, mut hp, mut mp, mut accuracy, mut evasion) =
            (0u32, 0u32, 0u32, 0u32, self.rate_initial, self.rate_initial);
        let item = |r: &wire::ItemStack| self.items.iter().find(|i| i.id == r.item);
        for (slot, record) in records.iter().enumerate().filter(|(_, r)| r.instance != 0) {
            let i = item(record).ok_or_else(|| bad("stats item"))?;
            let damage = if record.durability == 0 {
                i.attack / self.broken
            } else {
                i.attack
            };
            if slot == self.primary {
                attack += damage;
            }
            if slot == self.secondary && self.dual {
                attack = (attack as f64 + damage as f64 * self.secondary_scale).trunc() as u32;
            }
            hp += i.health;
            mp += i.resource;
            if record.durability != 0 {
                defense += i.defense;
                accuracy += i.accuracy;
                evasion += i.evasion;
                for (a, b) in attributes.iter_mut().zip(i.attributes) {
                    *a += b;
                }
            }
        }
        attack = attack.max(self.floor);
        let primary = &records[self.primary];
        let secondary = &records[self.secondary];
        let (mut raw, mut coefficient, mut dexterity) = (0., 0., false);
        if let Some(i) = item(primary) {
            let c = &self.categories[i.category];
            raw = i.attack as f64;
            coefficient = c.coefficient;
            dexterity = c.dexterity;
        }
        if coefficient == 0. || dexterity {
            if let Some(i) = item(secondary) {
                let c = &self.categories[i.category];
                if c.offhand != 0 {
                    raw += if c.offhand == 1 {
                        (i.attack as f64 * self.secondary_scale).trunc()
                    } else {
                        i.attack as f64
                    };
                    coefficient = c.coefficient;
                    dexterity = true;
                }
            }
        }
        let precise = dexterity || self.dexterity;
        let a = attributes[if precise { 2 } else { 0 }] as f64;
        let weapon = if precise { raw } else { attack as f64 };
        let mut total = (level as f64 * a * weapon * coefficient
            + (a + self.offset as f64) * weapon * self.linear
            + self.base as f64)
            .trunc();
        if precise {
            if (dexterity && primary.durability == 0 && secondary.durability == 0)
                || (!dexterity && primary.instance != 0 && primary.durability == 0)
            {
                total = (total / self.raw_broken as f64).trunc();
            }
        } else {
            total += gear.attributes[0].saturating_sub(self.strength_threshold) as f64
                * self.strength_attack;
        }
        let defense = ((level + defense) as f64 * self.defense).trunc()
            + gear.attributes[1].saturating_sub(self.stamina_threshold) as f64
                * self.stamina_defense;
        let polynomial = |p: &Polynomial| {
            let a = attributes[p.attribute] + p.offset;
            (a as f64 * p.coefficient * level as f64 * level as f64
                + level as f64 * a as f64 * p.linear
                + (a / p.divisor) as f64)
                .trunc()
                + p.base as f64
        };
        let health = polynomial(&self.health) + hp as f64;
        let resource = polynomial(if self.mana.coefficient != 0. {
            &self.mana
        } else {
            &self.stamina
        }) + mp as f64;
        // Assignment rounds the final rate to f32, as in the binary. Multiplication
        // occurs in f64 so the exact f32 coefficients retain their original value.
        let accuracy = ((level as f64 * self.accuracy * attributes[2] as f64 + self.rate_base)
            * accuracy as f64
            * self.rate_scale) as f32;
        let evasion = ((level as f64 * self.evasion * attributes[2] as f64 + self.rate_base)
            * evasion as f64
            * self.rate_scale) as f32;
        if !(0. ..=10000.).contains(&total)
            || !(0. ..=10000.).contains(&defense)
            || !(1. ..=32767.).contains(&health)
            || !(1. ..=32767.).contains(&resource)
            || !accuracy.is_finite()
            || !evasion.is_finite()
            || !(0.000001..=1000000.).contains(&accuracy)
            || !(0.000001..=1000000.).contains(&evasion)
        {
            return Err(bad("derived stats bounds"));
        }
        Ok(wire::DerivedStats {
            attack: total as u32,
            defense: defense as u32,
            accuracy,
            evasion,
            max_health: health as u32,
            max_resource: resource as u32,
            carry_limit: (attributes[0] + level) * self.weight,
            attributes: attributes.to_vec(),
            equipment_revision: 0,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use prost::Message;
    #[test]
    #[ignore = "original package vectors supplied by tests/stats.py"]
    fn vectors() {
        let release =
            crate::content::load(Path::new(&std::env::var("N3E_PACKAGE").unwrap())).unwrap();
        let bag = release.rules.inventory.unwrap();
        let gear = bag.equipment.as_ref().unwrap();
        let stats = bag.stats.as_ref().unwrap();
        for level in [1, 5, 10] {
            for case in 0..16 {
                let mut records = vec![wire::ItemStack::default(); gear.slots.len()];
                for (slot, index) in [(0, 0), (1, 1), (2, 3)] {
                    if case & (1 << slot) != 0 {
                        let def = &gear.items[index];
                        records[slot] = wire::ItemStack {
                            instance: slot as u64 + 1,
                            item: def.id.clone(),
                            quantity: 1,
                            durability: if case & 8 != 0 { 0 } else { 80 },
                        };
                    }
                }
                let out = stats
                    .calculate(gear, &records, level)
                    .unwrap()
                    .encode_to_vec();
                println!(
                    "VECTOR {level} {case} {}",
                    out.iter().map(|b| format!("{b:02x}")).collect::<String>()
                );
            }
        }
    }
}
