//! Data-defined durability restoration curve with truncation before the discount.
use crate::{
    content::{bad, Reader, Result},
    inventory, wire,
};
use std::path::Path;
#[derive(Clone, Debug)]
pub struct Policy {
    pub power: f64,
    pub linear: f32,
    pub offset: u32,
    pub multiplier: f32,
    pub items: Vec<String>,
}
impl Policy {
    pub fn load(path: &Path, bag: &inventory::Policy) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3J1" {
            return Err(bad("repair magic"));
        }
        let power = f64::from_le_bytes(r.take(8)?.try_into()?);
        let linear = r.f()?;
        let offset = r.u()?;
        let multiplier = r.f()?;
        let n = r.u()?;
        if !power.is_finite()
            || !(0.01..=1.).contains(&power)
            || !(0. ..=1.).contains(&linear)
            || offset > 1000000
            || !(0. ..=1.).contains(&multiplier)
            || !(1..=64).contains(&n)
        {
            return Err(bad("repair bounds"));
        }
        let mut items = Vec::new();
        for _ in 0..n {
            let id = r.string()?;
            if items.contains(&id) || !bag.items.iter().any(|i| i.id == id && i.durability > 1) {
                return Err(bad("repair item"));
            }
            items.push(id);
        }
        r.end()?;
        Ok(Self {
            power,
            linear,
            offset,
            multiplier,
            items,
        })
    }
    pub fn cost(&self, price: u32, current: u32, maximum: u32) -> Option<u32> {
        if maximum <= 1 || current > maximum {
            return None;
        }
        let value = ((price as f64 - self.offset as f64) * self.linear as f64
            + (price as f64).powf(self.power))
            * (maximum - current) as f64
            / maximum as f64;
        if !value.is_finite() || value < 0. || value > i32::MAX as f64 {
            return None;
        }
        Some(((value.trunc() as u32) as f64 * self.multiplier as f64).trunc() as u32)
    }
    pub fn apply(
        &self,
        bag: &inventory::Policy,
        state: &mut wire::BagState,
        q: &wire::BagRequest,
        price: u32,
    ) -> &'static str {
        if !self.items.contains(&q.item) {
            return "not_repairable";
        }
        let slot = if q.operation == 8 {
            &mut state.equipment[q.source as usize]
        } else {
            &mut state.slots[q.source as usize]
        };
        if slot.item != q.item {
            return "item_conflict";
        }
        let Some(def) = bag.items.iter().find(|i| i.id == q.item) else {
            return "unknown_item";
        };
        let Some(cost) = self.cost(price, slot.durability, def.durability) else {
            return "repair_price_invalid";
        };
        if cost > state.coins {
            return "insufficient_currency";
        }
        state.coins -= cost;
        slot.durability = def.durability;
        "committed"
    }
}
