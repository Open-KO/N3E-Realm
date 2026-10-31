//! Bounded optional hostile melee policy. No navigation search or durable rewards.
use crate::{
    content::{bad, Reader, Result},
    damage::Rolls,
    gameplay,
    rules::Rules,
    simulation::Player,
    wire,
};
use std::{collections::BTreeMap, path::Path};
#[derive(Clone, Debug)]
pub struct Policy {
    pub scan: u32,
    pub acquire: u32,
    pub stuck: u32,
    pub chase: u32,
    pub returning: u32,
    pub recovery: u32,
    /// N3N2 package-selected behavior; absent for N3N1 releases.
    pub reference: Option<Reference>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Acquisition {
    Aggressive,
    /// Never scans; only accepted damage acquires a target.
    Passive,
}
/// One NPC spawn slot, aligned with the gameplay spawn point of the same index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Slot {
    /// Integer offsets from the slot point: min x, min z, max x, max z.
    pub area: [i32; 4],
    pub respawn: u32,
    /// N3N3 (PQ-249): index into `Reference::templates`; None for N3N2.
    pub template: Option<usize>,
}
/// Most templates one N3N3 policy carries (PQ-249). A KO homeland zone uses
/// 108 (PQ-069 evidence); the table is bounded package data.
pub const MAX_TEMPLATES: u32 = 256;
/// One NPC template (PQ-249, N3N3). KO keeps one record per K_MONSTER /
/// K_NPC row (AI `00437fb4`, `00438479`) and copies it into every NPC its spawn
/// row names (`0043893e`); n3e keeps the table in the package and applies the
/// slot's template to that NPC's instance rules (`Rules::apply_template`).
#[derive(Clone, Debug, PartialEq)]
pub struct Template {
    /// Entity name; a package rule ID like the gameplay `npc`.
    pub name: String,
    /// Presentation key the entity carries on the wire; a package rule ID.
    pub looks: String,
    pub health: u32,
    pub level: u32,
    pub xp: u32,
    /// Fixed damage when the package has no N3D1 damage policy.
    pub damage: u32,
    /// The NPC side of N3D1 when the package has one.
    pub stats: crate::damage::Stats,
    pub attack_ticks: u32,
    pub speed: f32,
    pub attack_range: f32,
    pub search_range: f32,
    pub tracing_range: f32,
    pub acquisition: Acquisition,
    /// Drawn size in percent (PQ-272, D-179; N3N4, 1-1000; 100 for N3N3).
    /// Presentation only: sent as `Entity.scale`, never read by the AI. KO's
    /// spawn load copies sSize to record +0x24 (AI `00438c42`) and the NPC-in
    /// record carries it to the client (`004221d5`; Ebenezer `00479e7c`).
    pub scale: u32,
}
/// Template scale bounds in percent (PQ-272): the reference rows hold 20-600.
pub const SCALE: std::ops::RangeInclusive<u32> = 1..=1000;
#[derive(Clone, Debug)]
pub struct Reference {
    pub acquisition: Acquisition,
    pub renew_on_hit: bool,
    pub return_heal: bool,
    pub retaliate_returning: bool,
    pub return_speed_percent: u32,
    pub regen_interval: u32,
    pub regen_divisor: u32,
    pub spawn_tries: u32,
    /// Shared by every NPC's instance rules (PQ-250).
    pub slots: std::sync::Arc<Vec<Slot>>,
    /// N3N3 (PQ-249): the template table; empty for N3N2.
    pub templates: std::sync::Arc<Vec<Template>>,
    /// N3N4 (PQ-272): the templates carry a drawn scale (engine 41).
    pub scaled: bool,
}
fn template(r: &mut Reader, scaled: bool) -> Result<Template> {
    let name = r.string()?;
    let looks = r.string()?;
    let mut bounded = |lo: u32, hi: u32| -> Result<u32> {
        let value = r.u()?;
        if (lo..=hi).contains(&value) {
            Ok(value)
        } else {
            Err(bad("npc template bound"))
        }
    };
    // PQ-251 (D-164): the reference rows' health and level (AI `0043893e`
    // copies iHpPoint and sLevel; `0042214c` sends the level as one byte).
    let health = bounded(1, 2_000_000)?;
    let level = bounded(1, 255)?;
    // PQ-252 (D-165): the reference rows' combat columns. iExp (record +0x3c,
    // the kill reward 004209da) is 0 for some templates and reaches 39,438,375;
    // sDamage (+0x52) is both the fixed damage and the N3D1 attack, 0 for a
    // camp gate; attack stays within n3e's N3D1 bound of 10,000 (KO's short
    // result in 0041f535 wraps only above about 22,800, PQ-260). sAc, sHitRate and sEvadeRate (+0x4c, +0x4e, +0x50)
    // are shorts and may be 0: a 0 hit rate takes the lowest grade row, a 0
    // evasion the highest (00444164, 004235aa).
    let xp = bounded(0, crate::progression::TEMPLATE_XP_LIMIT)?;
    let damage = bounded(0, 100000)?;
    let stats = crate::damage::Stats {
        attack: bounded(0, 10000)?,
        defense: bounded(0, crate::damage::TEMPLATE_STAT_LIMIT)?,
        accuracy: bounded(0, crate::damage::TEMPLATE_STAT_LIMIT)?,
        evasion: bounded(0, crate::damage::TEMPLATE_STAT_LIMIT)?,
    };
    let attack_ticks = bounded(1, 1200)?;
    let acquisition = match bounded(0, 1)? {
        0 => Acquisition::Aggressive,
        _ => Acquisition::Passive,
    };
    let mut ranged = |lo: f32, hi: f32| -> Result<f32> {
        let value = r.f()?;
        if (lo..=hi).contains(&value) {
            Ok(value)
        } else {
            Err(bad("npc template range"))
        }
    };
    // Speed 0 never moves (KO bySpeed2 0); faster chases take solver substeps.
    let speed = ranged(0.0, 12.0)?;
    let attack_range = ranged(0.05, 64.0)?;
    let search_range = ranged(0.05, 64.0)?;
    let tracing_range = ranged(0.05, 64.0)?;
    if search_range > tracing_range {
        return Err(bad("npc template ranges"));
    }
    let scale = if scaled { r.u()? } else { 100 };
    if !SCALE.contains(&scale) {
        return Err(bad("npc template scale"));
    }
    Ok(Template {
        name,
        looks,
        health,
        level,
        xp,
        damage,
        stats,
        attack_ticks,
        speed,
        attack_range,
        search_range,
        tracing_range,
        acquisition,
        scale,
    })
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        let magic = r.take(4)?.to_vec();
        let model = r.u()?;
        // N3N3 (PQ-249) is N3N2 with a template table: the acquisition moves
        // into each template and each slot names its template. N3N4 (PQ-272)
        // is N3N3 with a drawn scale after each template.
        let (reference, templated, scaled) = match (magic.as_slice(), model) {
            (b"N3N1", 1) => (false, false, false),
            (b"N3N2", 2) => (true, false, false),
            (b"N3N3", 3) => (true, true, false),
            (b"N3N4", 4) => (true, true, true),
            _ => return Err(bad("npc model")),
        };
        let mut v = [0; 6];
        for (i, value) in v.iter_mut().enumerate() {
            *value = r.u()?;
            if *value < if i == 1 { 0 } else { 1 }
                || *value > if i == 3 || i == 4 { 12000 } else { 1200 }
            {
                return Err(bad("npc timer"));
            }
        }
        let reference = if reference {
            let acquisition = if templated {
                // Replaced per instance by the slot's template.
                Acquisition::Aggressive
            } else {
                match r.u()? {
                    0 => Acquisition::Aggressive,
                    1 => Acquisition::Passive,
                    _ => return Err(bad("npc acquisition")),
                }
            };
            let mut flag = || -> Result<bool> {
                match r.u()? {
                    0 => Ok(false),
                    1 => Ok(true),
                    _ => Err(bad("npc flag")),
                }
            };
            let (renew_on_hit, return_heal, retaliate_returning) = (flag()?, flag()?, flag()?);
            let mut bounded = |lo: u32, hi: u32| -> Result<u32> {
                let value = r.u()?;
                if (lo..=hi).contains(&value) {
                    Ok(value)
                } else {
                    Err(bad("npc reference bound"))
                }
            };
            let return_speed_percent = bounded(100, 300)?;
            let regen_interval = bounded(0, 12000)?;
            let regen_divisor = bounded(1, 1000)?;
            let spawn_tries = bounded(1, 500)?;
            let mut templates = Vec::new();
            if templated {
                let count = r.u()?;
                if !(1..=MAX_TEMPLATES).contains(&count) {
                    return Err(bad("npc templates"));
                }
                for _ in 0..count {
                    templates.push(template(&mut r, scaled)?);
                }
                if templates
                    .iter()
                    .enumerate()
                    .any(|(i, t)| templates[..i].iter().any(|o| o.name == t.name))
                {
                    return Err(bad("npc template names"));
                }
            }
            let count = r.u()?;
            // One slot per spawn point (content.rs checks the counts match).
            if !(1..=crate::rules::MAX_SPAWNS).contains(&count) {
                return Err(bad("npc slots"));
            }
            let mut slots = Vec::with_capacity(count as usize);
            for _ in 0..count {
                let mut area = [0i32; 4];
                for value in area.iter_mut() {
                    *value = r.u()? as i32;
                    if !(-256..=256).contains(value) {
                        return Err(bad("npc slot area"));
                    }
                }
                if area[0] > 0 || area[1] > 0 || area[2] < 0 || area[3] < 0 {
                    return Err(bad("npc slot area"));
                }
                let respawn = r.u()?;
                if !(1..=12000).contains(&respawn) {
                    return Err(bad("npc slot respawn"));
                }
                let template = if templated {
                    let index = r.u()? as usize;
                    if index >= templates.len() {
                        return Err(bad("npc slot template"));
                    }
                    Some(index)
                } else {
                    None
                };
                slots.push(Slot { area, respawn, template });
            }
            Some(Reference {
                acquisition,
                renew_on_hit,
                return_heal,
                retaliate_returning,
                return_speed_percent,
                regen_interval,
                regen_divisor,
                spawn_tries,
                slots: std::sync::Arc::new(slots),
                templates: std::sync::Arc::new(templates),
                scaled,
            })
        } else {
            None
        };
        r.end()?;
        Ok(Self {
            scan: v[0],
            acquire: v[1],
            stuck: v[2],
            chase: v[3],
            returning: v[4],
            recovery: v[5],
            reference,
        })
    }
    fn passive(&self) -> bool {
        self.reference
            .as_ref()
            .is_some_and(|p| p.acquisition == Acquisition::Passive)
    }
}
/// Uniform integer offset in an inclusive range; spans narrower than two keep the low bound.
fn offset(lo: i32, hi: i32, rng: &mut impl Rolls) -> i32 {
    if hi - lo < 2 {
        lo
    } else {
        lo + rng.roll((hi - lo + 1) as u32) as i32
    }
}
/// Bounded random standable point in a slot area, falling back to the slot point itself.
pub fn slot_point(
    origin: [f32; 2],
    slot: &Slot,
    tries: u32,
    collision: &crate::movement::Collision,
    rng: &mut impl Rolls,
) -> [f32; 2] {
    for _ in 0..tries {
        let x = origin[0] + offset(slot.area[0], slot.area[2], rng) as f32;
        let z = origin[1] + offset(slot.area[1], slot.area[3], rng) as f32;
        if crate::movement::standable(collision, x, z) {
            return [x, z];
        }
    }
    origin
}
#[derive(Default)]
pub struct State {
    pub target: Option<(i64, u64)>,
    ready: u64,
    next_attack: u64,
    deadline: u64,
    stalled: u32,
    // A failed target stays suppressed until it leaves acquisition range, dies,
    // disconnects or changes runtime identity. Fixed capacity follows peer bound.
    blocked: BTreeMap<i64, u64>,
}
fn horizontal(a: &wire::Entity, b: &wire::Entity) -> f32 {
    ((a.x - b.x).powi(2) + (a.z - b.z).powi(2)).sqrt()
}
/// Collision solver substeps for one tick at `speed` m/s: each moves at most
/// 3 m/s (0.15 m), the largest step a template could take before PQ-251, so a
/// speed of 3 or less walks exactly as before.
fn substeps(speed: f32) -> u32 {
    (speed / 3.).ceil().max(1.) as u32
}
fn eligible(p: &Player, home: &wire::Entity, r: &Rules) -> bool {
    !p.failed && p.s.entity.health > 0 && horizontal(&p.s.entity, home) <= r.leash_range
}
/// PQ-193 (D-152): an NPC neither picks nor keeps a session the server withholds
/// (`Player::hidden`), as KO's AI skips an operator (`0041c21e`, `0041de51`,
/// `0041e628`, `0041e9fd`). The blocked list keeps using `eligible`.
fn targetable(p: &Player, home: &wire::Entity, r: &Rules) -> bool {
    eligible(p, home, r) && !p.hidden()
}
impl State {
    /// Called only for authenticated, accepted, positive damage to a surviving NPC.
    /// Prediction rolls compare the current template stats, never grant damage.
    #[cfg(test)]
    pub fn hit(
        &mut self,
        e: &mut wire::Entity,
        actor: (i64, &wire::Entity),
        previous: Option<&wire::Entity>,
        r: &Rules,
        tick: u64,
        rng: &mut impl Rolls,
    ) {
        self.hit_with_stats(e, actor, previous, r, tick, rng, None, None)
    }
    pub fn hit_with_stats(
        &mut self,
        e: &mut wire::Entity,
        actor: (i64, &wire::Entity),
        previous: Option<&wire::Entity>,
        r: &Rules,
        tick: u64,
        rng: &mut impl Rolls,
        actor_stats: Option<&wire::DerivedStats>,
        previous_stats: Option<&wire::DerivedStats>,
    ) {
        let Some(policy) = &r.npc_policy else { return };
        let reference = policy.reference.as_ref();
        let returning = e.behavior == "return" || e.behavior == "recover";
        if e.health == 0
            || (returning && !reference.is_some_and(|p| p.retaliate_returning))
            || self.blocked.contains_key(&actor.0)
        {
            return;
        }
        if returning {
            // Reference policy: a hit while walking home or standing re-acquires at once.
            self.target = None;
            self.stalled = 0;
        }
        // Reference policy renews the pursuit budget on every accepted hit, before
        // the same-target test, so the current target's hits count too.
        if reference.is_some_and(|p| p.renew_on_hit) && self.target.is_some() {
            self.deadline = tick + policy.chase as u64;
        }
        if self.target == Some((actor.0, actor.1.id)) {
            return;
        }
        if let Some(old) = previous.filter(|p| p.health > 0) {
            let roll = rng.roll(101);
            let keep = if roll < 50 || (80..95).contains(&roll) {
                let npc = roll >= 80;
                let mut forecast = |stats| {
                    r.damage_policy
                        .as_ref()
                        .map(|p| p.resolve_with_player(npc, stats, rng).damage)
                        .unwrap_or(if npc { r.npc_damage } else { r.damage })
                };
                let before = forecast(previous_stats);
                let after = forecast(actor_stats);
                before > after
            } else if roll < 80 {
                gameplay::distance(e, actor.1) > gameplay::distance(e, old)
            } else {
                false
            };
            if keep {
                return;
            }
        }
        let was_idle = self.target.is_none();
        self.target = Some((actor.0, actor.1.id));
        // Switching targets or repeated damage cannot renew the pursuit budget.
        if was_idle {
            self.deadline = tick + policy.chase as u64;
        }
        self.ready = tick;
        e.behavior = "chase".into();
    }
    fn returning(&mut self, e: &mut wire::Entity, policy: &Policy, tick: u64, suppress: bool) {
        if suppress {
            if let Some((id, entity)) = self.target {
                if self.blocked.len() < 64 {
                    self.blocked.insert(id, entity);
                }
            }
        }
        self.target = None;
        self.stalled = 0;
        self.deadline = tick + policy.returning as u64;
        e.behavior = "return".into();
    }
    pub fn tick(
        &mut self,
        e: &mut wire::Entity,
        home: [f32; 3],
        players: &mut BTreeMap<i64, Player>,
        r: &Rules,
        collision: &crate::movement::Collision,
        tick: u64,
        rng: &mut impl Rolls,
    ) {
        let policy = r.npc_policy.as_ref().unwrap();
        let home = wire::Entity {
            x: home[0],
            y: home[1],
            z: home[2],
            ..Default::default()
        };
        self.blocked.retain(|id, entity| {
            players.get(id).is_some_and(|p| {
                p.s.entity.id == *entity
                    && eligible(p, &home, r)
                    && gameplay::distance(&p.s.entity, &home) <= r.aggro_range
            })
        });
        if e.behavior == "recover" {
            if tick < self.ready {
                return;
            }
            e.behavior = "idle".into();
        }
        if let Some((id, entity)) = self.target {
            if !players
                .get(&id)
                .is_some_and(|p| targetable(p, &home, r) && p.s.entity.id == entity)
                || horizontal(e, &home) > r.leash_range
            {
                self.returning(e, policy, tick, false);
            }
        }
        if e.behavior == "return" {
            // Bounded fallback returns to the validated home if direct walkability fails.
            if horizontal(e, &home) <= 0.08 || tick >= self.deadline {
                e.x = home.x;
                e.y = home.y;
                e.z = home.z;
                if policy.reference.as_ref().is_none_or(|p| p.return_heal) {
                    e.health = r.npc_health;
                }
                e.behavior = "recover".into();
                self.ready = tick + policy.recovery as u64;
                self.stalled = 0;
            } else {
                // Faster returns take whole solver substeps no longer than the chase step.
                let percent = policy
                    .reference
                    .as_ref()
                    .map_or(100, |p| p.return_speed_percent);
                let total = r.npc_speed * percent as f32 / 100.;
                let steps = percent.div_ceil(100).max(substeps(total));
                let speed = total / steps as f32;
                for _ in 0..steps {
                    let remaining = horizontal(e, &home);
                    if remaining <= 0.08 {
                        break;
                    }
                    gameplay::walk(e, &home, speed.min(remaining * 20.), collision);
                }
            }
            return;
        }
        if self.target.is_none() {
            if tick < self.ready {
                return;
            }
            if policy.passive() {
                e.behavior = "idle".into();
                return;
            }
            self.ready = tick + policy.scan as u64;
            self.target = players
                .iter()
                .filter(|(id, p)| {
                    targetable(p, &home, r)
                        && !self.blocked.contains_key(id)
                        && gameplay::distance(e, &p.s.entity) <= r.aggro_range
                })
                .min_by(|(ia, a), (ib, b)| {
                    gameplay::distance(e, &b.s.entity)
                        .total_cmp(&gameplay::distance(e, &a.s.entity))
                        .then(ia.cmp(ib))
                })
                .map(|(id, p)| (*id, p.s.entity.id));
            if self.target.is_none() {
                e.behavior = "idle".into();
                return;
            }
            self.ready = tick + policy.acquire as u64;
            self.deadline = tick + policy.chase as u64;
            e.behavior = "chase".into();
        }
        if tick < self.ready {
            return;
        }
        let p = players.get_mut(&self.target.unwrap().0).unwrap();
        if p.combat_pending() {
            return;
        }
        if horizontal(e, &p.s.entity) <= r.npc_range {
            e.behavior = "attack".into();
            self.stalled = 0;
            // Time spent successfully in range does not exhaust the chase budget.
            self.deadline = tick + policy.chase as u64;
            if tick >= self.next_attack {
                self.next_attack = tick + r.npc_cooldown_ticks as u64;
                let outcome = r
                    .damage_policy
                    .as_ref()
                    .map(|policy| policy.resolve_with_player(true, p.stats.as_ref(), rng))
                    .unwrap_or(crate::damage::Outcome {
                        hit: true,
                        damage: r.npc_damage,
                    });
                p.receive_hit(e, r, tick, outcome);
            }
        } else {
            e.behavior = "chase".into();
            let before = (e.x, e.z);
            let steps = substeps(r.npc_speed);
            let speed = r.npc_speed / steps as f32;
            for _ in 0..steps {
                // A fast chase stops at the substep that brings it into range
                // (the first substep never does: this branch starts outside).
                if horizontal(e, &p.s.entity) <= r.npc_range {
                    break;
                }
                gameplay::walk(
                    e,
                    &p.s.entity,
                    speed.min(horizontal(e, &p.s.entity) * 20.),
                    collision,
                );
            }
            self.stalled = if (e.x - before.0).hypot(e.z - before.1) < 0.0001 {
                self.stalled + 1
            } else {
                0
            };
            if self.stalled >= policy.stuck || tick >= self.deadline {
                self.returning(e, policy, tick, true);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;
    struct Fixed(u32);
    impl Rolls for Fixed {
        fn roll(&mut self, n: u32) -> u32 {
            self.0.min(n - 1)
        }
    }
    fn soup(c: &[[f32; 3]]) -> crate::movement::Collision {
        crate::movement::Collision::soup(c.to_vec()).unwrap()
    }
    fn setup() -> (Rules, Vec<[f32; 3]>, gameplay::Npc, BTreeMap<i64, Player>) {
        let mut r = Rules::load(
            Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.npc_policy = Some(Policy {
            scan: 2,
            acquire: 3,
            stuck: 3,
            chase: 30,
            returning: 8,
            recovery: 4,
            reference: None,
        });
        r.spawn_x = 0.;
        r.spawn_z = 0.;
        r.npc_range = 0.2;
        r.aggro_range = 5.;
        r.leash_range = 6.;
        r.npc_speed = 3.;
        let c = vec![
            [-10., 0., -10.],
            [10., 0., -10.],
            [10., 0., 10.],
            [-10., 0., -10.],
            [10., 0., 10.],
            [-10., 0., 10.],
        ];
        let n = gameplay::Npc::new(&r, &soup(&c), 100);
        let mut ps = BTreeMap::new();
        for (id, x) in [(1, 1.), (2, 2.)] {
            let mut p = crate::simulation::test_player();
            p.s.entity.id = id as u64;
            p.s.entity.x = x;
            ps.insert(id, p);
        }
        (r, c, n, ps)
    }
    fn tick(
        n: &mut gameplay::Npc,
        ps: &mut BTreeMap<i64, Player>,
        r: &Rules,
        c: &[[f32; 3]],
        t: u64,
    ) {
        n.tick(ps, r, &soup(c), t, &mut VecDeque::from([101]), &mut Fixed(100));
    }
    #[test]
    fn farthest_tie_delay_and_authoritative_cooldown() {
        let (r, c, mut n, mut ps) = setup();
        tick(&mut n, &mut ps, &r, &c, 1);
        assert_eq!(n.ai.target, Some((2, 2)));
        assert_eq!(n.entity.x, 0.);
        tick(&mut n, &mut ps, &r, &c, 3);
        assert_eq!(n.entity.x, 0.);
        tick(&mut n, &mut ps, &r, &c, 4);
        assert!(n.entity.x > 0.);
        ps.get_mut(&2).unwrap().s.entity.x = n.entity.x;
        tick(&mut n, &mut ps, &r, &c, 5);
        let hp = ps[&2].s.entity.health;
        assert_eq!(hp, 30 - r.npc_damage);
        // Damage from a different actor switches targets without resetting attack timer.
        let old = ps[&2].s.entity.clone();
        ps.get_mut(&1).unwrap().s.entity.x = n.entity.x;
        n.ai.hit(
            &mut n.entity,
            (1, &ps[&1].s.entity),
            Some(&old),
            &r,
            6,
            &mut Fixed(100),
        );
        tick(&mut n, &mut ps, &r, &c, 6);
        assert_eq!(ps[&1].s.entity.health, 30);
        let (r, c, mut n, mut ps) = setup();
        ps.get_mut(&1).unwrap().s.entity.x = 2.;
        tick(&mut n, &mut ps, &r, &c, 1);
        assert_eq!(n.ai.target, Some((1, 1)));
    }
    #[test]
    fn retaliation_bands_repeated_hits_and_no_budget_refresh() {
        let (r, c, mut n, mut ps) = setup();
        tick(&mut n, &mut ps, &r, &c, 1);
        let old = ps[&2].s.entity.clone();
        ps.get_mut(&1).unwrap().s.entity.x = 3.;
        n.ai.hit(
            &mut n.entity,
            (1, &ps[&1].s.entity),
            Some(&old),
            &r,
            2,
            &mut Fixed(60),
        );
        assert_eq!(n.ai.target, Some((2, 2))); // farther challenger loses distance band
        ps.get_mut(&1).unwrap().s.entity.x = 1.;
        let deadline = n.ai.deadline;
        n.ai.hit(
            &mut n.entity,
            (1, &ps[&1].s.entity),
            Some(&old),
            &r,
            3,
            &mut Fixed(60),
        );
        assert_eq!(n.ai.target, Some((1, 1)));
        assert_eq!(n.ai.deadline, deadline);
        let ready = n.ai.ready;
        n.ai.hit(
            &mut n.entity,
            (1, &ps[&1].s.entity),
            None,
            &r,
            9,
            &mut Fixed(100),
        );
        assert_eq!((n.ai.ready, n.ai.deadline), (ready, deadline));
        // Equal fixed template damage switches on both forecast bands and final band.
        for roll in [0, 49, 80, 94, 95, 100] {
            n.ai.target = Some((2, 2));
            n.ai.hit(
                &mut n.entity,
                (1, &ps[&1].s.entity),
                Some(&old),
                &r,
                10,
                &mut Fixed(roll),
            );
            assert_eq!(n.ai.target, Some((1, 1)));
        }
    }
    #[test]
    fn loss_death_disconnect_runtime_replacement_and_leash_return() {
        for mode in 0..5 {
            let (r, c, mut n, mut ps) = setup();
            tick(&mut n, &mut ps, &r, &c, 1);
            n.entity.health = 1;
            n.entity.x = 1.;
            match mode {
                0 => {
                    ps.remove(&2);
                }
                1 => ps.get_mut(&2).unwrap().s.entity.health = 0,
                2 => ps.get_mut(&2).unwrap().failed = true,
                3 => ps.get_mut(&2).unwrap().s.entity.id = 22,
                _ => ps.get_mut(&2).unwrap().s.entity.x = 6.01,
            }
            tick(&mut n, &mut ps, &r, &c, 2);
            assert_eq!(n.entity.behavior, "return");
            assert_eq!(n.entity.health, 1);
            let pos = n.entity.clone();
            n.ai.hit(
                &mut n.entity,
                (1, &ps[&1].s.entity),
                None,
                &r,
                3,
                &mut Fixed(100),
            );
            assert!(n.ai.target.is_none());
            assert_eq!(n.entity.x, pos.x);
            for t in 3..=10 {
                tick(&mut n, &mut ps, &r, &c, t);
            }
            assert_eq!(n.entity.behavior, "recover");
            assert_eq!(n.entity.health, r.npc_health);
            assert_eq!(n.entity.x, 0.);
            let ready = n.ai.ready;
            tick(&mut n, &mut ps, &r, &c, ready - 1);
            assert!(n.ai.target.is_none());
            tick(&mut n, &mut ps, &r, &c, ready);
            assert!(n.ai.target.is_some());
        }
    }
    #[test]
    fn real_wall_stalls_once_and_moving_pursuit_has_deadline() {
        let (mut r, mut c, mut n, mut ps) = setup();
        r.npc_policy.as_mut().unwrap().acquire = 0;
        ps.remove(&1);
        c.extend([
            [0.6, 0., -5.],
            [0.6, 2., -5.],
            [0.6, 2., 5.],
            [0.6, 0., -5.],
            [0.6, 2., 5.],
            [0.6, 0., 5.],
        ]);
        let mut returns = 0;
        let mut previous = String::new();
        for t in 1..200 {
            tick(&mut n, &mut ps, &r, &c, t);
            if n.entity.behavior == "return" && previous != "return" {
                returns += 1;
            }
            previous = n.entity.behavior.clone();
        }
        assert_eq!(returns, 1);
        assert_eq!(n.entity.behavior, "idle");
        let (mut r, c, mut n, mut ps) = setup();
        r.npc_policy.as_mut().unwrap().chase = 5;
        r.npc_policy.as_mut().unwrap().acquire = 0;
        for t in 1..=6 {
            tick(&mut n, &mut ps, &r, &c, t);
        }
        assert_eq!(n.entity.behavior, "return");
        assert!(n.entity.x > 0.); // timeout despite continuing physical progress
    }

    fn reference(acquisition: Acquisition) -> Reference {
        Reference {
            acquisition,
            renew_on_hit: true,
            return_heal: false,
            retaliate_returning: true,
            return_speed_percent: 200,
            regen_interval: 10,
            regen_divisor: 20,
            spawn_tries: 500,
            slots: vec![Slot { area: [-3, -2, 3, 2], respawn: 60, template: None }].into(),
            templates: Vec::new().into(),
            scaled: false,
        }
    }
    fn reference_setup(acquisition: Acquisition) -> (Rules, Vec<[f32; 3]>, gameplay::Npc, BTreeMap<i64, Player>) {
        let (mut r, c, _, ps) = setup();
        r.npc_policy.as_mut().unwrap().reference = Some(reference(acquisition));
        r.npc_policy.as_mut().unwrap().acquire = 0;
        let n = gameplay::Npc::new(&r, &soup(&c), 100);
        (r, c, n, ps)
    }
    #[test]
    fn reference_policy_golden_matches_cooker() {
        let hex = include_str!("../../tests/fixtures/npc-reference.hex");
        let bytes: Vec<u8> = (0..hex.trim().len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex.trim()[i..i + 2], 16).unwrap())
            .collect();
        let path = std::env::temp_dir().join(format!("n3e-npc-reference-{}.bin", std::process::id()));
        std::fs::write(&path, &bytes).unwrap();
        let p = Policy::load(&path).unwrap();
        let q = p.reference.as_ref().unwrap();
        assert_eq!((p.scan, p.acquire, p.stuck, p.chase, p.returning, p.recovery), (10, 10, 40, 200, 200, 20));
        assert_eq!(q.acquisition, Acquisition::Passive);
        assert!(q.renew_on_hit && !q.return_heal && q.retaliate_returning);
        assert_eq!((q.return_speed_percent, q.regen_interval, q.regen_divisor, q.spawn_tries), (200, 200, 20, 500));
        assert_eq!(*q.slots, vec![Slot { area: [-8, -8, 7, 8], respawn: 600, template: None }, Slot { area: [-12, -12, 9, 10], respawn: 400, template: None }]);
        // Truncation, trailing bytes, a wrong model and an out-of-range slot all fail closed.
        for bad in [bytes[..bytes.len() - 1].to_vec(), [bytes.clone(), vec![0]].concat()] {
            std::fs::write(&path, &bad).unwrap();
            assert!(Policy::load(&path).is_err());
        }
        let mut bad = bytes.clone();
        bad[4] = 1;
        std::fs::write(&path, &bad).unwrap();
        assert!(Policy::load(&path).is_err());
        let mut bad = bytes.clone();
        let slot = bytes.len() - 20;
        bad[slot..slot + 4].copy_from_slice(&1i32.to_le_bytes());
        std::fs::write(&path, &bad).unwrap();
        assert!(Policy::load(&path).is_err());
        std::fs::remove_file(&path).unwrap();
    }
    fn golden(name: &str) -> (Vec<u8>, std::path::PathBuf) {
        let hex = std::fs::read_to_string(format!("../tests/fixtures/{name}.hex")).unwrap();
        let hex = hex.trim();
        let bytes = (0..hex.len()).step_by(2).map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap()).collect();
        let path = std::env::temp_dir().join(format!("n3e-{name}-{}-{:?}.bin", std::process::id(), std::thread::current().id()));
        (bytes, path)
    }
    #[test]
    fn template_policy_golden_matches_cooker() {
        // PQ-249: tests/npc_reference.py cooks the same N3N3 bytes.
        let (bytes, path) = golden("npc-templates");
        std::fs::write(&path, &bytes).unwrap();
        let p = Policy::load(&path).unwrap();
        let q = p.reference.as_ref().unwrap();
        assert!(q.renew_on_hit && !q.return_heal && q.retaliate_returning);
        assert_eq!(q.templates.len(), 2);
        let (worm, bandit) = (&q.templates[0], &q.templates[1]);
        assert_eq!((worm.name.as_str(), worm.looks.as_str()), ("demo:creature/worm", "demo:looks/worm"));
        assert_eq!((worm.health, worm.level, worm.xp, worm.damage, worm.attack_ticks), (7, 1, 10, 2, 40));
        assert_eq!(worm.stats, crate::damage::Stats { attack: 18, defense: 40, accuracy: 50, evasion: 100 });
        assert_eq!((worm.speed, worm.attack_range, worm.search_range, worm.tracing_range), (3., 1., 3., 40.));
        assert_eq!(worm.acquisition, Acquisition::Passive);
        assert_eq!((bandit.health, bandit.level, bandit.xp, bandit.acquisition), (90, 5, 40, Acquisition::Aggressive));
        assert_eq!(q.slots.iter().map(|s| s.template).collect::<Vec<_>>(), vec![Some(1), Some(0)]);
        // Truncation, trailing bytes, the N3N2 model number, a slot naming a
        // missing template, a repeated name and a search range beyond the
        // tracing range all fail closed.
        let mut bad = vec![
            (bytes[..bytes.len() - 1].to_vec(), "truncated"),
            ([bytes.clone(), vec![0]].concat(), "trailing"),
        ];
        let mut model = bytes.clone();
        model[4] = 2;
        bad.push((model, "npc model"));
        let mut index = bytes.clone();
        let at = bytes.len() - 4;
        index[at..].copy_from_slice(&2u32.to_le_bytes());
        bad.push((index, "npc slot template"));
        let find = |needle: &[u8]| bytes.windows(needle.len()).position(|w| w == needle).unwrap();
        let bandit_at = find(b"demo:creature/bandit");
        let worm_at = find(b"demo:creature/worm");
        // The bandit renamed to the worm's name (two bytes shorter).
        let mut twin = bytes.clone();
        twin[bandit_at..bandit_at + 18].copy_from_slice(b"demo:creature/worm");
        twin[bandit_at - 4..bandit_at].copy_from_slice(&18u32.to_le_bytes());
        twin.drain(bandit_at + 18..bandit_at + 20);
        bad.push((twin, "npc template names"));
        let mut ranges = bytes.clone();
        // The worm's search range (3 m) beyond its tracing range: tracing = 1 m.
        let tracing = worm_at + 18 + 4 + 15 + 10 * 4 + 3 * 4;
        assert_eq!(&ranges[tracing..tracing + 4], &40f32.to_le_bytes());
        ranges[tracing..tracing + 4].copy_from_slice(&1f32.to_le_bytes());
        bad.push((ranges, "npc template ranges"));
        let mut count = bytes.clone();
        let templates_at = 4 + 4 + 6 * 4 + 3 * 4 + 4 * 4;
        assert_eq!(&count[templates_at..templates_at + 4], &2u32.to_le_bytes());
        count[templates_at..templates_at + 4].copy_from_slice(&(MAX_TEMPLATES + 1).to_le_bytes());
        bad.push((count, "npc templates"));
        for (data, reason) in bad {
            std::fs::write(&path, &data).unwrap();
            let error = Policy::load(&path).unwrap_err().to_string();
            assert!(error.contains(reason), "{reason}: {error}");
        }
        std::fs::remove_file(&path).unwrap();
    }
    #[test]
    fn scaled_template_golden_matches_cooker() {
        // PQ-272 (D-179): tests/npc_reference.py cooks the same N3N4 bytes: the
        // N3N3 golden with a u32 scale after each template, the worm at 55 %
        // and the bandit at the default 100 %.
        let (plain, _) = golden("npc-templates");
        let (bytes, path) = golden("npc-templates-scaled");
        assert_eq!((&bytes[..4], bytes.len()), (&b"N3N4"[..], plain.len() + 8));
        std::fs::write(&path, &bytes).unwrap();
        let q = Policy::load(&path).unwrap().reference.unwrap();
        assert!(q.scaled);
        assert_eq!(q.templates.iter().map(|t| t.scale).collect::<Vec<_>>(), vec![55, 100]);
        std::fs::write(&path, &plain).unwrap();
        let p = Policy::load(&path).unwrap().reference.unwrap();
        assert!(!p.scaled && p.templates.iter().all(|t| t.scale == 100));
        // The worm's scale follows its tracing range (the first 55 in the file).
        let at = bytes.windows(4).position(|w| w == 55u32.to_le_bytes()).unwrap();
        let mut bad = Vec::new();
        for value in [0u32, 1001, u32::MAX] {
            let mut forged = bytes.clone();
            forged[at..at + 4].copy_from_slice(&value.to_le_bytes());
            bad.push((forged, "npc template scale"));
        }
        // N3N3's model number on N3N4 bytes (and the reverse) misreads the
        // layout and fails closed; so does N3N4 with model 3.
        let mut model = bytes.clone();
        model[..4].copy_from_slice(b"N3N3");
        model[4] = 3;
        bad.push((model, ""));
        let mut mixed = bytes.clone();
        mixed[4] = 3;
        bad.push((mixed, "npc model"));
        let mut reverse = plain.clone();
        reverse[..4].copy_from_slice(b"N3N4");
        reverse[4] = 4;
        bad.push((reverse, ""));
        for (data, reason) in bad {
            std::fs::write(&path, &data).unwrap();
            let error = Policy::load(&path).unwrap_err().to_string();
            assert!(error.contains(reason), "{reason}: {error}");
        }
        std::fs::remove_file(&path).unwrap();
    }
    #[test]
    fn scaled_npcs_send_their_scale() {
        // PQ-272: a templated NPC sends its template's scale as Entity.scale
        // when it is not 100; at 100, from N3N3 and untemplated, it sends 0.
        let (bytes, path) = golden("npc-templates-scaled");
        std::fs::write(&path, &bytes).unwrap();
        let loaded = Policy::load(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        let (base, c, _, _) = setup();
        let templates = loaded.reference.unwrap().templates;
        let scales: Vec<u32> = templates
            .iter()
            .enumerate()
            .map(|(i, t)| {
                let mut r = base.clone();
                r.apply_template(i, t);
                gameplay::Npc::new(&r, &soup(&c), 100 + i as u64).entity.scale
            })
            .collect();
        assert_eq!(scales, vec![55, 0]);
        assert_eq!(gameplay::Npc::new(&base, &soup(&c), 99).entity.scale, 0);
        // A 55 % worm still strikes, chases and is struck by its template's
        // numbers: the scale changes no rule.
        let mut r = base.clone();
        r.apply_template(0, &templates[0]);
        let mut unscaled = templates[0].clone();
        unscaled.scale = 100;
        let mut q = base.clone();
        q.apply_template(0, &unscaled);
        assert_eq!(
            (r.npc_health, r.npc_damage, r.npc_speed, r.npc_range, r.aggro_range, r.leash_range),
            (q.npc_health, q.npc_damage, q.npc_speed, q.npc_range, q.aggro_range, q.leash_range)
        );
    }
    #[test]
    fn each_npc_follows_its_own_template() {
        let (bytes, path) = golden("npc-templates");
        std::fs::write(&path, &bytes).unwrap();
        let loaded = Policy::load(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        let (mut base, c, _, mut ps) = setup();
        base.npc_policy.as_mut().unwrap().reference = loaded.reference.clone();
        base.npc_policy.as_mut().unwrap().acquire = 0;
        base.npc_policy.as_mut().unwrap().reference.as_mut().unwrap().regen_interval = 0;
        let templates = loaded.reference.unwrap().templates;
        let rules: Vec<Rules> = templates
            .iter()
            .enumerate()
            .map(|(i, t)| {
                let mut r = base.clone();
                r.apply_template(i, t);
                r
            })
            .collect();
        // Both templates in one view: their own name, looks key, health and maximum.
        let mut npcs: Vec<_> = rules.iter().enumerate().map(|(i, r)| gameplay::Npc::new(r, &soup(&c), 100 + i as u64)).collect();
        for (n, t) in npcs.iter().zip(templates.iter()) {
            assert_eq!((n.entity.name.as_str(), n.entity.looks.as_str()), (t.name.as_str(), t.looks.as_str()));
            assert_eq!((n.entity.health, n.entity.max_health), (t.health, t.health));
        }
        // An untemplated NPC sends neither field (wire stays as before).
        let plain = gameplay::Npc::new(&base, &soup(&c), 99);
        assert_eq!((plain.entity.looks.as_str(), plain.entity.max_health), ("", 0));
        // The passive worm ignores a player beside it; the aggressive bandit
        // (search range 6 m) picks one 2 m away and strikes with its own damage.
        ps.remove(&1);
        ps.get_mut(&2).unwrap().s.entity.x = 0.5;
        for t in 1..30 {
            tick(&mut npcs[0], &mut ps, &rules[0], &c, t);
        }
        assert!(npcs[0].ai.target.is_none());
        assert_eq!(ps[&2].s.entity.health, 30);
        let mut strikes = Vec::new();
        for t in 30..120 {
            let before = ps[&2].s.entity.health;
            tick(&mut npcs[1], &mut ps, &rules[1], &c, t);
            if ps[&2].s.entity.health < before {
                strikes.push((t, before - ps[&2].s.entity.health));
            }
        }
        assert!(strikes.len() >= 2, "{strikes:?}");
        assert!(strikes.iter().all(|s| s.1 == templates[1].damage), "{strikes:?}");
        // The template's attack delay (30 ticks), not the package's.
        assert_eq!(strikes[1].0 - strikes[0].0, templates[1].attack_ticks as u64);
        // Accepted damage makes the passive worm retaliate with its 2 damage.
        ps.get_mut(&2).unwrap().s.entity.health = 30;
        let worm = &mut npcs[0];
        worm.ai.hit(&mut worm.entity, (2, &ps[&2].s.entity), None, &rules[0], 200, &mut Fixed(100));
        let before = ps[&2].s.entity.health;
        for t in 200..260 {
            tick(&mut npcs[0], &mut ps, &rules[0], &c, t);
        }
        assert_eq!((before - ps[&2].s.entity.health) % templates[0].damage, 0);
        assert!(ps[&2].s.entity.health < before);
        // Regeneration and return-heal read the template's maximum health.
        let mut r = rules[1].clone();
        r.npc_policy.as_mut().unwrap().reference.as_mut().unwrap().regen_interval = 10;
        let mut n = gameplay::Npc::new(&r, &soup(&c), 300);
        ps.clear();
        n.entity.health = 10;
        tick(&mut n, &mut ps, &r, &c, 1);
        tick(&mut n, &mut ps, &r, &c, 11);
        assert_eq!(n.entity.health, 10 + 90 / 20);
    }
    #[test]
    fn zero_damage_template_strikes_without_harm() {
        // PQ-252 (D-165): a reference row with sDamage 0 (the homeland camp
        // gates) cooks to fixed damage 0 and N3D1 attack 0. KO's 0041f535
        // returns 0 for X <= 0 and 0041de51 then changes no health; n3e's
        // strikes keep their cadence and deal 0 with or without N3D1.
        let (bytes, path) = golden("npc-templates");
        std::fs::write(&path, &bytes).unwrap();
        let loaded = Policy::load(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        let (mut base, c, _, mut ps) = setup();
        base.npc_policy.as_mut().unwrap().reference = loaded.reference.clone();
        base.npc_policy.as_mut().unwrap().acquire = 0;
        let mut gate = loaded.reference.unwrap().templates[1].clone();
        gate.damage = 0;
        gate.stats.attack = 0;
        gate.xp = 0;
        for n3d1 in [false, true] {
            let mut r = base.clone();
            r.damage_policy = n3d1.then(|| crate::damage::Policy {
                player: crate::damage::Stats { attack: 36, defense: 20, accuracy: 50, evasion: 100 },
                npc: crate::damage::Stats { attack: 18, defense: 40, accuracy: 50, evasion: 100 },
            });
            r.apply_template(1, &gate);
            assert_eq!(r.npc_reward, Some(crate::progression::NpcReward { level: gate.level, xp: 0 }));
            let mut npc = gameplay::Npc::new(&r, &soup(&c), 400);
            ps.remove(&1);
            let player = ps.get_mut(&2).unwrap();
            player.s.entity.x = 0.5;
            player.s.entity.health = 30;
            let mut strikes = Vec::new();
            for t in 1..120 {
                tick(&mut npc, &mut ps, &r, &c, t);
                if npc.entity.strike_tick == t {
                    strikes.push((t, npc.entity.strike_damage));
                }
            }
            assert!(strikes.len() >= 2, "{n3d1}: {strikes:?}");
            assert!(strikes.iter().all(|s| s.1 == 0), "{n3d1}: {strikes:?}");
            assert_eq!(strikes[1].0 - strikes[0].0, gate.attack_ticks as u64);
            assert_eq!(ps[&2].s.entity.health, 30);
        }
    }
    #[test]
    fn reference_speeds_chase_in_bounded_substeps() {
        // PQ-251: KO's run speeds reach 10 m/s (bySpeed2); a 9 m/s chase covers
        // 0.45 m a tick in three 0.15 m solver steps, a 3 m/s one walks as
        // before (one step), and speed 0 (a gate) never leaves its point.
        for (speed, per_tick) in [(9f32, 0.45f32), (3., 0.15), (0., 0.)] {
            let (mut r, c, _, mut ps) = reference_setup(Acquisition::Aggressive);
            r.npc_speed = speed;
            r.aggro_range = 9.;
            r.leash_range = 20.;
            r.npc_range = 0.2;
            r.npc_policy.as_mut().unwrap().chase = 400;
            ps.remove(&1);
            ps.get_mut(&2).unwrap().s.entity.x = 8.;
            let mut n = gameplay::Npc::new(&r, &soup(&c), 100);
            tick(&mut n, &mut ps, &r, &c, 1);
            assert_eq!(n.ai.target, Some((2, 2)), "speed {speed}");
            let mut xs = vec![n.entity.x];
            for t in 2..8 {
                tick(&mut n, &mut ps, &r, &c, t);
                xs.push(n.entity.x);
            }
            for w in xs.windows(2) {
                assert!((w[1] - w[0] - per_tick).abs() < 1e-4, "speed {speed}: {xs:?}");
            }
            if speed > 0. {
                // It stops at the substep that enters its range, not up to a
                // whole tick's travel inside it.
                for t in 8..60 {
                    tick(&mut n, &mut ps, &r, &c, t);
                }
                let gap = ps[&2].s.entity.x - n.entity.x;
                assert!(gap <= r.npc_range && gap > r.npc_range - 0.15, "speed {speed}: {gap}");
                assert_eq!(n.entity.behavior, "attack");
            }
        }
        assert_eq!((substeps(0.), substeps(3.), substeps(3.01), substeps(12.)), (1, 1, 2, 4));
    }
    #[test]
    fn passive_npc_ignores_proximity_until_accepted_damage() {
        let (r, c, mut n, mut ps) = reference_setup(Acquisition::Passive);
        for t in 1..20 {
            tick(&mut n, &mut ps, &r, &c, t);
        }
        assert!(n.ai.target.is_none());
        assert_eq!(n.entity.behavior, "idle");
        n.ai.hit(&mut n.entity, (1, &ps[&1].s.entity), None, &r, 20, &mut Fixed(100));
        assert_eq!(n.ai.target, Some((1, 1)));
        assert_eq!(n.ai.deadline, 20 + r.npc_policy.as_ref().unwrap().chase as u64);
        // The aggressive variant of the same policy scans as before.
        let (r, c, mut n, mut ps) = reference_setup(Acquisition::Aggressive);
        tick(&mut n, &mut ps, &r, &c, 1);
        assert!(n.ai.target.is_some());
    }
    #[test]
    fn reference_hits_renew_pursuit_and_retaliate_while_returning() {
        let (r, _, mut n, ps) = reference_setup(Acquisition::Passive);
        let chase = r.npc_policy.as_ref().unwrap().chase as u64;
        n.ai.hit(&mut n.entity, (2, &ps[&2].s.entity), None, &r, 5, &mut Fixed(100));
        // Same-target hits renew the budget (N3N1 deliberately does not).
        n.ai.hit(&mut n.entity, (2, &ps[&2].s.entity), None, &r, 17, &mut Fixed(100));
        assert_eq!(n.ai.deadline, 17 + chase);
        // Return starts, then damage re-acquires instead of being ignored.
        n.entity.behavior = "return".into();
        n.ai.target = None;
        n.ai.hit(&mut n.entity, (1, &ps[&1].s.entity), None, &r, 30, &mut Fixed(100));
        assert_eq!((n.ai.target, n.entity.behavior.as_str()), (Some((1, 1)), "chase"));
        n.entity.behavior = "recover".into();
        n.ai.target = None;
        n.ai.hit(&mut n.entity, (2, &ps[&2].s.entity), None, &r, 31, &mut Fixed(100));
        assert_eq!(n.ai.target, Some((2, 2)));
    }
    #[test]
    fn reference_return_is_faster_and_does_not_heal() {
        let (mut r, c, mut n, mut ps) = reference_setup(Acquisition::Passive);
        // Isolate arrival: periodic regeneration is covered separately.
        r.npc_policy.as_mut().unwrap().reference.as_mut().unwrap().regen_interval = 0;
        ps.clear();
        n.entity.x = 4.;
        n.entity.health = 1;
        n.entity.behavior = "return".into();
        n.ai.deadline = 1000;
        tick(&mut n, &mut ps, &r, &c, 1);
        // 200% of 3 m/s is two solver substeps of 0.15 m in one 50 ms tick.
        assert!((n.entity.x - 3.7).abs() < 1e-4, "{}", n.entity.x);
        for t in 2..40 {
            tick(&mut n, &mut ps, &r, &c, t);
        }
        assert_eq!(n.entity.behavior, "idle");
        assert_eq!((n.entity.x, n.entity.health), (0., 1));
    }
    #[test]
    fn reference_fast_return_takes_bounded_substeps_without_overshoot() {
        // PQ-251: a 9 m/s template walking home at 200% covers 0.9 m a tick in
        // six 0.15 m solver steps (the percent alone would give two of 0.45 m),
        // never passes its home and then recovers there.
        let (mut r, c, mut n, mut ps) = reference_setup(Acquisition::Passive);
        r.npc_policy.as_mut().unwrap().reference.as_mut().unwrap().regen_interval = 0;
        r.npc_speed = 9.;
        assert_eq!(substeps(9. * 200. / 100.), 6);
        ps.clear();
        n.entity.x = 8.;
        n.entity.behavior = "return".into();
        n.ai.deadline = 1000;
        let mut xs = vec![n.entity.x];
        let mut t = 1;
        while n.entity.behavior == "return" && t < 40 {
            tick(&mut n, &mut ps, &r, &c, t);
            xs.push(n.entity.x);
            t += 1;
        }
        for w in xs.windows(2).take(8) {
            assert!((w[0] - w[1] - 0.9).abs() < 1e-4, "{xs:?}");
        }
        assert!(xs.iter().all(|x| *x >= 0.), "{xs:?}");
        assert_eq!((n.entity.x, n.entity.z, n.entity.behavior.as_str()), (0., 0., "recover"), "{xs:?}");
        // Nine ticks bring it within the 0.08 m arrival tolerance (8 m at 0.9 m,
        // the last substeps stopping there); the tenth snaps it home.
        assert_eq!(t - 1, 10, "{xs:?}");
        assert!(xs[9] > 0. && xs[9] <= 0.08, "{xs:?}");
    }
    #[test]
    fn reference_regeneration_is_periodic_integer_and_bounded() {
        let (mut r, c, mut n, mut ps) = reference_setup(Acquisition::Passive);
        ps.clear();
        r.npc_health = 100;
        n.entity.health = 50;
        tick(&mut n, &mut ps, &r, &c, 1);
        assert_eq!(n.entity.health, 50); // first period starts at spawn
        tick(&mut n, &mut ps, &r, &c, 10);
        assert_eq!(n.entity.health, 50);
        tick(&mut n, &mut ps, &r, &c, 11);
        assert_eq!(n.entity.health, 55); // 100 / 20
        n.entity.health = 98;
        tick(&mut n, &mut ps, &r, &c, 21);
        assert_eq!(n.entity.health, 100);
        // Below the divisor, integer recovery is zero, as for the 7 HP reference worm.
        r.npc_health = 7;
        n.entity.health = 3;
        tick(&mut n, &mut ps, &r, &c, 31);
        assert_eq!(n.entity.health, 3);
    }
    #[test]
    fn slot_points_stay_in_area_and_fall_back_to_the_slot_point() {
        struct Seq(Vec<u32>, usize);
        impl Rolls for Seq {
            fn roll(&mut self, n: u32) -> u32 {
                self.1 += 1;
                self.0[(self.1 - 1) % self.0.len()] % n
            }
        }
        let (_, c, _, _) = setup();
        let slot = Slot { area: [-3, -2, 3, 2], respawn: 60, template: None };
        let mut seen = std::collections::BTreeSet::new();
        let mut rng = Seq((0..50).collect(), 0);
        for _ in 0..50 {
            let p = slot_point([1., 1.], &slot, 500, &soup(&c), &mut rng);
            assert!((-2.0..=4.0).contains(&p[0]) && (-1.0..=3.0).contains(&p[1]), "{p:?}");
            assert_eq!((p[0].fract(), p[1].fract()), (0., 0.));
            seen.insert((p[0] as i32, p[1] as i32));
        }
        assert!(seen.len() > 10);
        // Narrow spans keep the low bound; no standable point falls back to the slot point.
        let narrow = Slot { area: [0, -1, 1, 0], respawn: 60, template: None };
        assert_eq!(slot_point([2., 2.], &narrow, 5, &soup(&c), &mut rng), [2., 1.]);
        assert_eq!(slot_point([2., 2.], &slot, 5, &soup(&[]), &mut rng), [2., 2.]);
    }
    #[test]
    fn unreachable_suppression_and_bounded_return_cannot_oscillate() {
        let (mut r, c, mut n, mut ps) = setup();
        r.npc_policy.as_mut().unwrap().acquire = 0;
        ps.remove(&1);
        // Empty walkability makes both outward movement and return impossible.
        n.entity.x = 0.5;
        for t in 1..10000 {
            tick(&mut n, &mut ps, &r, &[], t);
        }
        assert_eq!(n.entity.behavior, "idle");
        assert_eq!(n.entity.x, 0.);
        assert!(n.ai.target.is_none());
        assert_eq!(n.ai.blocked.len(), 1);
        // Remaining nearby and repeatedly hitting cannot restart failed pursuit.
        n.ai.hit(
            &mut n.entity,
            (2, &ps[&2].s.entity),
            None,
            &r,
            10000,
            &mut Fixed(100),
        );
        assert!(n.ai.target.is_none());
        ps.get_mut(&2).unwrap().s.entity.x = 7.;
        tick(&mut n, &mut ps, &r, &c, 10001);
        ps.get_mut(&2).unwrap().s.entity.x = 2.;
        tick(&mut n, &mut ps, &r, &c, 10003);
        assert!(n.ai.target.is_some());
        n.entity.health = 0;
        n.entity.respawn_tick = 10005;
        tick(&mut n, &mut ps, &r, &c, 10004);
        assert_eq!(n.entity.id, 100);
        tick(&mut n, &mut ps, &r, &c, 10005);
        assert_eq!(n.entity.id, 101);
        assert!(n.ai.target.is_none());
        assert!(n.ai.blocked.is_empty());
    }
    #[test]
    fn hidden_sessions_are_not_picked_chased_or_struck() {
        // PQ-193 (D-152): KO's AI skips an operator when it looks for an enemy
        // (AI 0041c21e) and drops one it attacks or chases (0041de51, 0041e628,
        // 0041e9fd). n3e skips a session the server withholds (Player::hidden).
        let (r, c, mut n, mut ps) = setup();
        ps.get_mut(&2).unwrap().test_lease(true);
        tick(&mut n, &mut ps, &r, &c, 1);
        assert_eq!(n.ai.target, Some((1, 1)), "the ordinary player, not the farther hidden one");
        // A hidden session alone in range is never picked or struck.
        let (r, c, mut n, mut ps) = setup();
        ps.remove(&1);
        ps.get_mut(&2).unwrap().test_lease(true);
        ps.get_mut(&2).unwrap().s.entity.x = 0.1;
        for t in 1..40 {
            tick(&mut n, &mut ps, &r, &c, t);
            assert!(n.ai.target.is_none() && n.entity.behavior == "idle", "tick {t}");
        }
        assert_eq!((ps[&2].s.entity.health, n.entity.strike_target), (30, 0));
        // A target that becomes hidden is dropped at the NPC's next tick: it
        // walks home as for any lost target and strikes it no more.
        let (r, c, mut n, mut ps) = setup();
        ps.remove(&1);
        tick(&mut n, &mut ps, &r, &c, 1);
        assert_eq!(n.ai.target, Some((2, 2)));
        tick(&mut n, &mut ps, &r, &c, 4);
        ps.get_mut(&2).unwrap().s.entity.x = n.entity.x;
        tick(&mut n, &mut ps, &r, &c, 5);
        assert_eq!(n.entity.behavior, "attack");
        let struck = ps[&2].s.entity.health;
        assert_eq!(struck, 30 - r.npc_damage);
        ps.get_mut(&2).unwrap().test_lease(true);
        tick(&mut n, &mut ps, &r, &c, 6);
        assert!(n.ai.target.is_none());
        assert_eq!(n.entity.behavior, "return");
        assert!(n.ai.blocked.is_empty(), "dropping a hidden target does not block it");
        for t in 7..200 {
            tick(&mut n, &mut ps, &r, &c, t);
            assert!(n.ai.target.is_none(), "tick {t}");
        }
        assert_eq!(n.entity.behavior, "idle");
        assert_eq!(ps[&2].s.entity.health, struck);
        // A revocation's read shows it again: the next scan picks it.
        ps.get_mut(&2).unwrap().test_lease(false);
        for t in 200..204 {
            tick(&mut n, &mut ps, &r, &c, t);
        }
        assert_eq!(n.ai.target, Some((2, 2)));
        assert_eq!(n.entity.behavior, "chase");
    }
}
