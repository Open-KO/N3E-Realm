//! Validated immutable package rules. No game IDs in engine logic.
use crate::content::{bad, Reader, Result};
use std::{path::Path, sync::Arc};
/// Every NPC holds its own instance rules (`administration::cycle_rules`,
/// PQ-249), so the package tables are shared, never copied (PQ-250): a clone
/// copies the scalar rules and bumps the tables' reference counts.
#[derive(Clone, Debug)]
pub struct Rules {
    pub skills: Option<Arc<crate::skills::Policy>>,
    pub combat_animation: Option<Arc<crate::combat_animation::Policy>>,
    pub consumables: Option<Arc<crate::consumables::Policy>>,
    pub rest: Option<Arc<crate::rest::Policy>>,
    pub friends: Option<Arc<crate::friends::Policy>>,
    pub party: Option<Arc<crate::party::Policy>>,
    pub commerce: Option<Arc<crate::commerce::Policy>>,
    pub inventory: Option<Arc<crate::inventory::Policy>>,
    pub progression: Option<Arc<crate::progression::Policy>>,
    pub life: Option<crate::life::Policy>,
    pub npc_policy: Option<crate::npc_ai::Policy>,
    pub damage_policy: Option<crate::damage::Policy>,
    pub melee: Option<Melee>,
    pub movement: Option<crate::movement::Config>,
    pub action: String,
    pub item: String,
    pub npc: String,
    pub health: u32,
    pub resource: u32,
    pub damage: u32,
    pub cost: u32,
    pub cooldown_ticks: u32,
    pub regen_ticks: u32,
    pub npc_health: u32,
    pub npc_damage: u32,
    pub npc_cooldown_ticks: u32,
    pub respawn_ticks: u32,
    pub slots: u32,
    pub starting_items: u32,
    pub reward_items: u32,
    pub reward_xp: u32,
    pub level_xp: u32,
    pub speed: f32,
    pub range: f32,
    pub npc_speed: f32,
    pub npc_range: f32,
    pub aggro_range: f32,
    pub leash_range: f32,
    pub spawns: Arc<Vec<[f32; 2]>>,
    pub interest_cell: f32,
    pub spawn_x: f32,
    pub spawn_z: f32,
    /// Reference NPC slot for per-instance rules; set only by cycle rules.
    pub npc_slot: Option<usize>,
    /// N3N3 template applied to these instance rules (PQ-249); set only by
    /// cycle rules. None: the package-wide `npc_*` rules.
    pub npc_template: Option<usize>,
    /// The applied template's presentation key; empty without a template.
    pub npc_looks: String,
    /// The applied template's drawn scale in percent (PQ-272); 100 without a
    /// template or for an N3N3 one. Presentation only (`Entity.scale`).
    pub npc_scale: u32,
    /// The applied template's kill reward level and XP; None: the progression
    /// definition's own `npc_level` and `base_xp`.
    pub npc_reward: Option<crate::progression::NpcReward>,
}
/// Most spawn points (N3G2/N3G3) and reference NPC slots (N3N2/N3N3) one
/// package carries (PQ-250). KO's spawn load numbers NPCs without a fixed cap
/// (AI `0043893e`); the largest zone in the local OpenKO rows has 1,238 NPCs
/// (zone 1), so the engine bound leaves room for about 1.6 times that.
pub const MAX_SPAWNS: u32 = 2048;
/// A package rule ID: `game:` prefix, at most 128 bytes, `[a-z0-9_:/-]`.
pub fn rule_id(v: &str, game: &str) -> bool {
    v.starts_with(&format!("{game}:"))
        && v.len() <= 128
        && v
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"_:/-".contains(&b))
}
#[derive(Clone, Debug)]
pub struct Melee {
    pub actor_radius: f32,
    pub target_radius: f32,
    pub reach: f32,
    pub facing_dot: f32,
}
impl Melee {
    pub fn range(&self) -> f32 {
        (self.actor_radius + self.target_radius) * 0.5 + self.reach
    }
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3M1" {
            return Err(bad("melee magic"));
        }
        let v = Self {
            actor_radius: r.f()?,
            target_radius: r.f()?,
            reach: r.f()?,
            facing_dot: r.f()?,
        };
        r.end()?;
        if !(0.1..=5.).contains(&v.actor_radius)
            || !(0.1..=5.).contains(&v.target_radius)
            || !(0.0..=5.).contains(&v.reach)
            || !(0.0..=0.99).contains(&v.facing_dot)
        {
            return Err(bad("melee bounds"));
        }
        Ok(v)
    }
}
impl Rules {
    /// Makes these instance rules one NPC template's (PQ-249): every consumer
    /// that reads an NPC's rules (AI, damage, regeneration, death and respawn,
    /// rewards, drops, the operator record) then reads the template, as KO's
    /// spawn load copies the template into each NPC's record (AI `0043893e`).
    /// The progression definition stays the realm's: the template's level and
    /// XP travel as `npc_reward`, which a settlement records and validates.
    pub fn apply_template(&mut self, index: usize, t: &crate::npc_ai::Template) {
        self.npc_template = Some(index);
        self.npc = t.name.clone();
        self.npc_looks = t.looks.clone();
        self.npc_scale = t.scale;
        self.npc_health = t.health;
        self.npc_damage = t.damage;
        self.npc_cooldown_ticks = t.attack_ticks;
        self.npc_speed = t.speed;
        self.npc_range = t.attack_range;
        self.aggro_range = t.search_range;
        self.leash_range = t.tracing_range;
        if let Some(p) = self.damage_policy.as_mut() {
            p.npc = t.stats.clone();
        }
        self.npc_reward = Some(crate::progression::NpcReward {
            level: t.level,
            xp: t.xp,
        });
        if let Some(p) = self.npc_policy.as_mut().and_then(|p| p.reference.as_mut()) {
            p.acquisition = t.acquisition;
        }
    }
    pub fn load(path: &Path, game: &str) -> Result<Self> {
        let mut r = Reader::open(path)?;
        let magic = r.take(4)?.to_vec();
        if magic != b"N3G1" && magic != b"N3G2" && magic != b"N3G3" {
            return Err(bad("gameplay magic"));
        }
        let mut v = Self {
            skills: None,
            rest: None,
            consumables: None,
            combat_animation: None,
            friends: None,
            party: None,
            inventory: None,
            commerce: None,
            progression: None,
            npc_policy: None,
            life: None,
            damage_policy: None,
            melee: None,
            movement: None,
            spawns: Arc::new(Vec::new()),
            npc_slot: None,
            npc_template: None,
            npc_looks: String::new(),
            npc_scale: 100,
            npc_reward: None,
            interest_cell: 1.,
            action: r.string()?,
            item: r.string()?,
            npc: r.string()?,
            health: r.u()?,
            resource: r.u()?,
            damage: r.u()?,
            cost: r.u()?,
            cooldown_ticks: r.u()?,
            regen_ticks: r.u()?,
            npc_health: r.u()?,
            npc_damage: r.u()?,
            npc_cooldown_ticks: r.u()?,
            respawn_ticks: r.u()?,
            slots: r.u()?,
            starting_items: r.u()?,
            reward_items: r.u()?,
            reward_xp: r.u()?,
            level_xp: r.u()?,
            speed: r.f()?,
            range: r.f()?,
            npc_speed: r.f()?,
            npc_range: r.f()?,
            aggro_range: r.f()?,
            leash_range: r.f()?,
            spawn_x: r.f()?,
            spawn_z: r.f()?,
        };
        if magic != b"N3G1" {
            v.interest_cell = r.f()?;
            let count = r.u()?;
            if !(1.0..=64.0).contains(&v.interest_cell) || !(1..=MAX_SPAWNS).contains(&count) {
                return Err(bad("spawn/interest bounds"));
            }
            let mut spawns = Vec::with_capacity(count as usize);
            for _ in 0..count {
                let point = [r.f()?, r.f()?];
                if point.iter().any(|x| !(-1000000.0..=1000000.0).contains(x)) {
                    return Err(bad("spawn bounds"));
                }
                spawns.push(point);
            }
            v.spawns = Arc::new(spawns);
        } else {
            v.spawns = Arc::new(vec![[v.spawn_x, v.spawn_z]]);
        }
        if magic == b"N3G3" {
            v.movement = Some(
                crate::movement::Config {
                    walk: v.speed,
                    run: r.f()?,
                    backward: r.f()?,
                    radius: r.f()?,
                    height: r.f()?,
                    step_height: r.f()?,
                }
                .validate()?,
            );
        }
        r.end()?;
        if !rule_id(&v.action, game) || !rule_id(&v.item, game) || !rule_id(&v.npc, game) {
            return Err(bad("rule ID"));
        }
        if !(1..=100000).contains(&v.health) {
            return Err(bad("rule health"));
        }
        if !(1..=100000).contains(&v.resource) {
            return Err(bad("rule resource"));
        }
        if !(1..=100000).contains(&v.damage) {
            return Err(bad("rule damage"));
        }
        if !(0..=100000).contains(&v.cost) {
            return Err(bad("rule cost"));
        }
        if !(1..=1200).contains(&v.cooldown_ticks) {
            return Err(bad("rule cooldown_ticks"));
        }
        if !(1..=1200).contains(&v.regen_ticks) {
            return Err(bad("rule regen_ticks"));
        }
        if !(1..=100000).contains(&v.npc_health) {
            return Err(bad("rule npc_health"));
        }
        if !(1..=100000).contains(&v.npc_damage) {
            return Err(bad("rule npc_damage"));
        }
        if !(1..=1200).contains(&v.npc_cooldown_ticks) {
            return Err(bad("rule npc_cooldown_ticks"));
        }
        if !(1..=1200).contains(&v.respawn_ticks) {
            return Err(bad("rule respawn_ticks"));
        }
        if !(1..=64).contains(&v.slots) {
            return Err(bad("rule slots"));
        }
        if !(0..=64).contains(&v.starting_items) {
            return Err(bad("rule starting_items"));
        }
        if !(1..=64).contains(&v.reward_items) {
            return Err(bad("rule reward_items"));
        }
        if !(1..=100000).contains(&v.reward_xp) {
            return Err(bad("rule reward_xp"));
        }
        if !(1..=100000).contains(&v.level_xp) {
            return Err(bad("rule level_xp"));
        }
        if !(0.01..=if v.movement.is_some() { 6.0 } else { 3.0 }).contains(&v.speed) {
            return Err(bad("rule speed"));
        }
        if !(0.05..=10.0).contains(&v.range) {
            return Err(bad("rule range"));
        }
        if !(0.01..=3.0).contains(&v.npc_speed) {
            return Err(bad("rule npc_speed"));
        }
        if !(0.05..=10.0).contains(&v.npc_range) {
            return Err(bad("rule npc_range"));
        }
        if !(0.05..=10.0).contains(&v.aggro_range) {
            return Err(bad("rule aggro_range"));
        }
        if !(0.05..=64.0).contains(&v.leash_range) {
            return Err(bad("rule leash_range"));
        }
        if !(-1000000.0..=1000000.0).contains(&v.spawn_x) {
            return Err(bad("rule spawn_x"));
        }
        if !(-1000000.0..=1000000.0).contains(&v.spawn_z) {
            return Err(bad("rule spawn_z"));
        }
        if v.cost > v.resource
            || v.starting_items > v.slots
            || v.reward_items > v.slots
            || v.aggro_range > v.leash_range
        {
            return Err(bad("rule cross-field bounds"));
        }
        Ok(v)
    }
}

#[cfg(test)]
mod extension_tests {
    use super::*;
    #[test]
    fn bounded_extended_rules_and_legacy() {
        let mut bytes = std::fs::read("../build/packages/legacy-demo/gameplay.bin").unwrap();
        let legacy = Rules::load(Path::new("../build/packages/legacy-demo/gameplay.bin"), "demo").unwrap();
        assert_eq!(*legacy.spawns, vec![[legacy.spawn_x, legacy.spawn_z]]);
        bytes[..4].copy_from_slice(b"N3G2");
        let base = bytes.len();
        bytes.extend(24f32.to_le_bytes());
        bytes.extend(2u32.to_le_bytes());
        for x in [-4f32, -4., 5., -5.] {
            bytes.extend(x.to_le_bytes());
        }
        let path = std::env::temp_dir().join(format!("n3e-rules-{}.bin", std::process::id()));
        let read = |data: &[u8]| {
            std::fs::write(&path, data).unwrap();
            Rules::load(&path, "demo")
        };
        let loaded = read(&bytes).unwrap();
        assert_eq!(*loaded.spawns, vec![[-4., -4.], [5., -5.]]);
        assert_eq!(loaded.interest_cell, 24.);
        let mut invalid = bytes.clone();
        invalid[base + 4..base + 8].copy_from_slice(&(MAX_SPAWNS + 1).to_le_bytes());
        assert!(read(&invalid).is_err());
        // PQ-250: a zone's whole population, up to the bound, loads.
        let mut many = bytes[..base].to_vec();
        many.extend(24f32.to_le_bytes());
        many.extend(MAX_SPAWNS.to_le_bytes());
        for i in 0..MAX_SPAWNS {
            many.extend((i as f32 / 8.).to_le_bytes());
            many.extend((-(i as f32) / 8.).to_le_bytes());
        }
        let loaded = read(&many).unwrap();
        assert_eq!(loaded.spawns.len(), MAX_SPAWNS as usize);
        assert_eq!(loaded.spawns[2047], [2047. / 8., -2047. / 8.]);
        let mut over = many.clone();
        over[base + 4..base + 8].copy_from_slice(&(MAX_SPAWNS + 1).to_le_bytes());
        over.extend([0u8; 8]);
        assert!(read(&over).is_err());
        invalid = bytes.clone();
        invalid[base..base + 4].copy_from_slice(&f32::NAN.to_le_bytes());
        assert!(read(&invalid).is_err());
        invalid = bytes.clone();
        invalid[base + 8..base + 12].copy_from_slice(&1000001f32.to_le_bytes());
        assert!(read(&invalid).is_err());
        assert!(read(&bytes[..bytes.len() - 1]).is_err());
        bytes.push(0);
        assert!(read(&bytes).is_err());
        std::fs::remove_file(path).unwrap();
    }
}
