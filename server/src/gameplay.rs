//! Deterministic targeted combat; tick order is player commands, then NPC AI.
use crate::{movement, rules::Rules, simulation::Player, wire};
use std::collections::{BTreeMap, VecDeque};
pub fn distance(a: &wire::Entity, b: &wire::Entity) -> f32 {
    ((a.x - b.x).powi(2) + (a.y - b.y).powi(2) + (a.z - b.z).powi(2)).sqrt()
}
/// `ranged`: the selected combat profile's ranged basic attack (PQ-416,
/// D-216), whose strike limit is both radii summed plus its range, in 3-D (the
/// 1298 client's archery check `00583780`), and, PQ-467 (D-233), whose
/// target must also be within its hold (Ebenezer's casting phase passes
/// `004c1dbe` too); None keeps the melee or legacy range.
pub fn validate(
    actor: &wire::Entity,
    target: &wire::Entity,
    r: &Rules,
    tick: u64,
    next: u64,
    pending: bool,
    ranged: Option<crate::combat_animation::Ranged>,
) -> Result<(), &'static str> {
    if actor.health == 0 {
        return Err("actor_dead");
    }
    if target.health == 0 {
        return Err("target_dead");
    }
    if pending {
        return Err("reward_pending");
    }
    let (distance, range) = if let (Some(m), Some(shot)) = (&r.melee, ranged) {
        (
            crate::gameplay::distance(actor, target),
            m.actor_radius + m.target_radius + shot.range,
        )
    } else if let Some(m) = &r.melee {
        (
            ((actor.x - target.x).powi(2) + (actor.z - target.z).powi(2)).sqrt(),
            m.range(),
        )
    } else {
        (distance(actor, target), r.range)
    };
    if !distance.is_finite() || distance > range || ranged.is_some_and(|shot| !shot.holds(actor, target)) {
        return Err("out_of_range");
    }
    if tick < next {
        return Err("cooldown");
    }
    if actor.resource < r.cost {
        return Err("insufficient_resource");
    }
    Ok(())
}
/// PQ-420 (D-217): a held ranged shot's checks at its landing. Its interval
/// and sequence were checked when it was accepted and are not checked again;
/// the archer and the target must live and the strike's cost must still be
/// paid. PQ-467 (D-233): the target must be within the profile's hold
/// (`ranged`'s; none without one) from where the archer stands now, as
/// Ebenezer's effecting phase passes `004c1dbe` (`004635c8`) with both
/// sides' current positions; 1298's client does not check the range after
/// the cast starts (`00585830`, `00584b00`), and the start limit is not
/// checked again. PQ-454 (D-228): a pending reward holds a landing (the
/// caller's busy rule, bounded by `ranged_shot::DEFER`) rather than refusing
/// it, and a released shot (`paid`) paid its cost at its release, as
/// Ebenezer's flying phase takes the row's Msp (`0046f3f1` ->
/// `004a083f`) and its effecting phase does not check it again for a row
/// with a flight (`00464b43`, `0046548f` -> `004654a1`).
pub fn landing(
    actor: &wire::Entity,
    target: &wire::Entity,
    r: &Rules,
    paid: bool,
    ranged: Option<crate::combat_animation::Ranged>,
) -> Result<(), &'static str> {
    if actor.health == 0 {
        return Err("actor_dead");
    }
    if target.health == 0 {
        return Err("target_dead");
    }
    if ranged.is_some_and(|shot| !shot.holds(actor, target)) {
        return Err("out_of_range");
    }
    if !paid && actor.resource < r.cost {
        return Err("insufficient_resource");
    }
    Ok(())
}
/// Only called after session, sequence, action ID and target identity validation.
#[cfg(test)]
pub fn attack(
    actor: &mut wire::Entity,
    target: &mut wire::Entity,
    r: &Rules,
    tick: u64,
    next: &mut u64,
    pending: bool,
    rng: &mut impl crate::damage::Rolls,
) -> Result<crate::damage::Outcome, &'static str> {
    attack_with_stats(actor, target, r, tick, next, pending, rng, None)
}
#[cfg(test)]
pub fn attack_with_stats(
    actor: &mut wire::Entity,
    target: &mut wire::Entity,
    r: &Rules,
    tick: u64,
    next: &mut u64,
    pending: bool,
    rng: &mut impl crate::damage::Rolls,
    stats: Option<&wire::DerivedStats>,
) -> Result<crate::damage::Outcome, &'static str> {
    validate(actor, target, r, tick, *next, pending, None)?;

    let outcome = r
        .damage_policy
        .as_ref()
        .map(|p| p.resolve_with_player(false, stats, rng))
        .unwrap_or(crate::damage::Outcome {
            hit: true,
            damage: r.damage,
        });
    finish_attack(actor, target, r, tick, next, &outcome, false);
    Ok(outcome)
}

/// `paid`: PQ-454 (D-228), a released ranged shot's arrival, whose cost its
/// release took.
pub fn finish_attack(
    actor: &mut wire::Entity,
    target: &mut wire::Entity,
    r: &Rules,
    tick: u64,
    next: &mut u64,
    outcome: &crate::damage::Outcome,
    paid: bool,
) {
    *next = tick + r.cooldown_ticks as u64;
    if !paid {
        actor.resource -= r.cost;
    }
    actor.strike_tick = tick;
    actor.strike_target = target.id;
    actor.strike_result = outcome.status().into();
    actor.strike_damage = outcome.damage;
    target.health = target.health.saturating_sub(outcome.damage);
}

pub struct Npc {
    pub pending: Option<i64>,
    pub expires: u64,
    pub definition_revision: u64,
    pub cycle: Option<Rules>,
    pub ledger: crate::progression::Ledger,
    pub ai: crate::npc_ai::State,
    pub entity: wire::Entity,
    home: [f32; 3],
    target: Option<(i64, u64)>,
    next: u64,
    /// Slot point and slot used for reference respawns; homes vary inside the area.
    origin: [f32; 2],
    slot: Option<usize>,
    next_regen: u64,
}
impl Npc {
    /// Places a reference-slot NPC at a bounded random standable point in its area;
    /// other rules keep the fixed spawn point.
    pub fn spawn(
        r: &Rules,
        collision: &crate::movement::Collision,
        id: u64,
        rng: &mut impl crate::damage::Rolls,
    ) -> Self {
        let reference = r.npc_policy.as_ref().and_then(|p| p.reference.as_ref());
        let Some((slot, reference)) = r.npc_slot.zip(reference) else {
            return Self::new(r, collision, id);
        };
        let point = crate::npc_ai::slot_point(
            [r.spawn_x, r.spawn_z],
            &reference.slots[slot],
            reference.spawn_tries,
            collision,
            rng,
        );
        let mut placed = r.clone();
        placed.spawn_x = point[0];
        placed.spawn_z = point[1];
        let mut npc = Self::new(&placed, collision, id);
        npc.origin = [r.spawn_x, r.spawn_z];
        npc.slot = Some(slot);
        npc
    }
    pub fn new(r: &Rules, collision: &crate::movement::Collision, id: u64) -> Self {
        let home = [
            r.spawn_x,
            movement::ground(collision, r.spawn_x, r.spawn_z),
            r.spawn_z,
        ];
        Self {
            pending: None,
            expires: 0,
            definition_revision: 0,
            cycle: None,
            ledger: Default::default(),
            ai: Default::default(),
            entity: wire::Entity {
                id,
                name: r.npc.clone(),
                x: home[0],
                y: home[1],
                z: home[2],
                health: r.npc_health,
                // PQ-249: a templated NPC carries its looks key and its own
                // maximum health; untemplated packages send neither.
                looks: r.npc_looks.clone(),
                max_health: if r.npc_template.is_some() { r.npc_health } else { 0 },
                // PQ-272 (D-179): a templated NPC's drawn scale in percent, as
                // KO's NPC-in record carries sSize (AI 004221d5, Ebenezer
                // 00479e7c, client 005cd6d5); 0 (absent) means 100.
                scale: if r.npc_template.is_some() && r.npc_scale != 100 { r.npc_scale } else { 0 },
                life_state: if r.life.is_some() {
                    wire::LifeState::Alive as i32
                } else {
                    0
                },
                npc: true,
                behavior: "idle".into(),
                ..Default::default()
            },
            home,
            target: None,
            next: 0,
            origin: [r.spawn_x, r.spawn_z],
            slot: None,
            next_regen: 0,
        }
    }
    pub fn tick(
        &mut self,
        players: &mut BTreeMap<i64, Player>,
        r: &Rules,
        collision: &crate::movement::Collision,
        tick: u64,
        ids: &mut VecDeque<u64>,
        rng: &mut impl crate::damage::Rolls,
    ) {
        // Never restore an encounter until its replacement identity is reserved.
        if r.progression.is_some() && self.ledger.active() && ids.is_empty() {
            return;
        }
        let old_health = self.entity.health;
        let old_id = self.entity.id;
        self.tick_inner(players, r, collision, tick, ids, rng);
        if r.progression.is_some()
            && self.ledger.active()
            && self.entity.id == old_id
            && self.entity.health > old_health
        {
            self.entity.id = ids.pop_front().expect("reserved reset identity");
            self.ledger = Default::default();
        }
        // Periodic recovery follows the reset check so it never counts as an encounter reset.
        self.regenerate(r, tick);
    }
    fn regenerate(&mut self, r: &Rules, tick: u64) {
        let Some(reference) = r.npc_policy.as_ref().and_then(|p| p.reference.as_ref()) else {
            return;
        };
        if reference.regen_interval == 0 || self.pending.is_some() {
            return;
        }
        if self.next_regen == 0 {
            self.next_regen = tick + reference.regen_interval as u64;
            return;
        }
        if tick < self.next_regen {
            return;
        }
        // The period restarts even when nothing is healed.
        self.next_regen = tick + reference.regen_interval as u64;
        let e = &mut self.entity;
        if e.health > 0 && e.health < r.npc_health {
            e.health = (e.health + r.npc_health / reference.regen_divisor).min(r.npc_health);
        }
    }
    fn tick_inner(
        &mut self,
        players: &mut BTreeMap<i64, Player>,
        r: &Rules,
        collision: &crate::movement::Collision,
        tick: u64,
        ids: &mut VecDeque<u64>,
        rng: &mut impl crate::damage::Rolls,
    ) {
        if self.pending.is_some() {
            return;
        }
        let e = &mut self.entity;
        crate::life::refresh(e, tick);
        if e.health == 0 {
            if tick >= e.respawn_tick {
                if let Some(id) = ids.pop_front() {
                    let mut home_rules = r.clone();
                    if self.slot.is_some() {
                        home_rules.spawn_x = self.origin[0];
                        home_rules.spawn_z = self.origin[1];
                        home_rules.npc_slot = self.slot;
                        *self = Self::spawn(&home_rules, collision, id, rng);
                    } else {
                        home_rules.spawn_x = self.home[0];
                        home_rules.spawn_z = self.home[2];
                        *self = Self::new(&home_rules, collision, id);
                    }
                }
            }
            return;
        }
        if r.npc_policy.is_some() {
            self.ai.tick(e, self.home, players, r, collision, tick, rng);
            return;
        }
        let home = wire::Entity {
            x: self.home[0],
            y: self.home[1],
            z: self.home[2],
            ..Default::default()
        };
        if self.target.is_some_and(|(id, entity)| {
            players
                .get(&id)
                .map(|p| {
                    p.s.entity.health == 0
                        || p.s.entity.id != entity
                        || distance(&p.s.entity, &home) > r.leash_range
                        || p.failed
                        // PQ-193 (D-152): a session the server withholds is dropped.
                        || p.hidden()
                })
                .unwrap_or(true)
        }) {
            self.target = None;
            e.behavior = "return".into();
        }
        if e.behavior == "return" {
            if distance(e, &home) < 0.08 {
                e.x = home.x;
                e.y = home.y;
                e.z = home.z;
                e.health = r.npc_health;
                e.behavior = "idle".into();
            } else {
                walk(e, &home, r.npc_speed, collision);
            }
            return;
        }
        if self.target.is_none() {
            self.target = players
                .iter()
                .filter(|(_, p)| {
                    p.s.entity.health > 0
                        && !p.failed
                        && !p.hidden()
                        && distance(e, &p.s.entity) <= r.aggro_range
                })
                .min_by_key(|(id, _)| *id)
                .map(|(id, p)| (*id, p.s.entity.id));
        }
        if let Some(p) = self.target.and_then(|(id, _)| players.get_mut(&id)) {
            if p.combat_pending() {
                return;
            }
            if distance(e, &p.s.entity) <= r.npc_range {
                e.behavior = "attack".into();
                if tick >= self.next {
                    self.next = tick + r.npc_cooldown_ticks as u64;
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
                walk(e, &p.s.entity, r.npc_speed, collision);
            }
        } else {
            e.behavior = "idle".into();
        }
    }
}
pub(crate) fn walk(
    e: &mut wire::Entity,
    target: &wire::Entity,
    speed: f32,
    collision: &crate::movement::Collision,
) {
    let dx = target.x - e.x;
    let dz = target.z - e.z;
    let n = (dx * dx + dz * dz).sqrt().max(0.001);
    let q = movement::step(
        collision,
        [e.x, e.y, e.z],
        [dx / n * speed / 3., dz / n * speed / 3.],
    );
    e.x = q[0];
    e.y = q[1];
    e.z = q[2];
}
#[cfg(test)]
mod tests {
    use super::*;
    fn rules() -> Rules {
        Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap()
    }
    #[test]
    fn authority_rules() {
        let r = rules();
        let mut a = wire::Entity {
            health: r.health,
            resource: r.resource,
            ..Default::default()
        };
        let mut b = wire::Entity {
            health: r.npc_health,
            ..Default::default()
        };
        assert!(validate(&a, &b, &r, 10, 10, false, None).is_ok());
        b.x = r.range + 0.01;
        assert_eq!(validate(&a, &b, &r, 10, 10, false, None), Err("out_of_range"));
        b.x = 0.;
        assert_eq!(validate(&a, &b, &r, 9, 10, false, None), Err("cooldown"));
        a.resource = 0;
        assert_eq!(
            validate(&a, &b, &r, 10, 10, false, None),
            Err("insufficient_resource")
        );
        a.resource = r.resource;
        b.health = 0;
        assert_eq!(validate(&a, &b, &r, 10, 10, false, None), Err("target_dead"));
        b.health = 1;
        a.health = 0;
        assert_eq!(validate(&a, &b, &r, 10, 10, false, None), Err("actor_dead"));
        a.health = 1;
        assert_eq!(validate(&a, &b, &r, 10, 10, true, None), Err("reward_pending"));
    }
}

#[cfg(test)]
mod ai_tests {
    use super::*;
    #[test]
    fn chase_attack_return_and_unique_respawn() {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.spawn_x = -1.;
        r.spawn_z = 0.;
        r.npc_range = 0.2;
        r.aggro_range = 2.;
        r.leash_range = 3.;
        let collision = vec![
            [-4., 0., -4.],
            [4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., 4.],
        ];
        let collision = movement::Collision::soup(collision).unwrap();
        let mut n = Npc::new(&r, &collision, 10);
        let mut players = BTreeMap::new();
        players.insert(1, crate::simulation::test_player());
        let mut ids = VecDeque::from([11]);
        let mut rng = crate::damage::Random::seeded(1);
        n.tick(&mut players, &r, &collision, 1, &mut ids, &mut rng);
        assert_eq!(n.entity.behavior, "chase");
        assert!(n.entity.x > -1.);
        n.entity.x = -0.1;
        n.tick(&mut players, &r, &collision, 2, &mut ids, &mut rng);
        assert_eq!(n.entity.behavior, "attack");
        assert_eq!(players[&1].s.entity.health, 30 - r.npc_damage);
        n.tick(&mut players, &r, &collision, 3, &mut ids, &mut rng);
        assert_eq!(players[&1].s.entity.health, 30 - r.npc_damage);
        players.get_mut(&1).unwrap().s.entity.id += 1; // Same character, new life instance.
        n.tick(&mut players, &r, &collision, 4, &mut ids, &mut rng);
        assert_eq!(n.entity.behavior, "return");
        players.clear();
        for tick in 5..100 {
            n.tick(&mut players, &r, &collision, tick, &mut ids, &mut rng);
        }
        assert_eq!(n.entity.behavior, "idle");
        assert_eq!(n.entity.x, -1.);
        r.spawn_x = 2.; // Respawn must retain this instance home, not the template default.
        n.entity.health = 0;
        n.entity.respawn_tick = 120;
        n.tick(&mut players, &r, &collision, 119, &mut ids, &mut rng);
        assert_eq!(n.entity.id, 10);
        n.tick(&mut players, &r, &collision, 120, &mut ids, &mut rng);
        assert_eq!(n.entity.id, 11);
        assert_eq!(n.entity.x, -1.);
        assert_eq!(n.entity.health, r.npc_health);
    }
    #[test]
    fn hidden_sessions_are_not_targets_without_a_policy() {
        // PQ-193 (D-152): the fixed melee AI (no NPC policy) skips and drops a
        // session the server withholds, as the policy AI does.
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.npc_policy = None;
        r.spawn_x = -1.;
        r.spawn_z = 0.;
        r.npc_range = 0.2;
        r.aggro_range = 2.;
        r.leash_range = 3.;
        let collision = vec![
            [-4., 0., -4.],
            [4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., 4.],
        ];
        let collision = movement::Collision::soup(collision).unwrap();
        let mut n = Npc::new(&r, &collision, 10);
        let mut players = BTreeMap::new();
        players.insert(1, crate::simulation::test_player());
        players.get_mut(&1).unwrap().test_lease(true);
        let mut ids = VecDeque::new();
        let mut rng = crate::damage::Random::seeded(1);
        for tick in 1..5 {
            n.tick(&mut players, &r, &collision, tick, &mut ids, &mut rng);
            assert_eq!(n.entity.behavior, "idle");
        }
        players.get_mut(&1).unwrap().test_lease(false);
        for tick in 5..10 {
            n.tick(&mut players, &r, &collision, tick, &mut ids, &mut rng);
            assert_eq!(n.entity.behavior, "chase");
        }
        players.get_mut(&1).unwrap().test_lease(true);
        n.tick(&mut players, &r, &collision, 10, &mut ids, &mut rng);
        assert_eq!(n.entity.behavior, "return");
        for tick in 11..100 {
            n.tick(&mut players, &r, &collision, tick, &mut ids, &mut rng);
        }
        assert_eq!(n.entity.behavior, "idle");
        assert_eq!(players[&1].s.entity.health, 30);
    }
}

#[cfg(test)]
mod melee_tests {
    use super::*;
    #[test]
    fn horizontal_radius_boundary_and_zero_cost_do_not_bypass_authority() {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.melee = Some(crate::rules::Melee {
            actor_radius: 0.5,
            target_radius: 1.5,
            reach: 0.,
            facing_dot: 0.7,
        });
        r.cost = 0;
        let mut a = wire::Entity {
            health: 1,
            resource: 0,
            ..Default::default()
        };
        let mut b = wire::Entity {
            health: 1,
            x: 1.,
            y: 100.,
            ..Default::default()
        };
        assert!(validate(&a, &b, &r, 20, 20, false, None).is_ok());
        r.melee.as_mut().unwrap().target_radius = 2.5;
        b.x = 1.5;
        assert!(validate(&a, &b, &r, 20, 20, false, None).is_ok());
        b.x = 1.5001;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, None), Err("out_of_range"));
        r.melee.as_mut().unwrap().reach = 0.5;
        b.x = 2.;
        assert!(validate(&a, &b, &r, 20, 20, false, None).is_ok());
        r.melee.as_mut().unwrap().target_radius = 1.5;
        r.melee.as_mut().unwrap().reach = 0.;
        b.x = 1.0001;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, None), Err("out_of_range"));
        b.x = 1.;
        assert_eq!(validate(&a, &b, &r, 19, 20, false, None), Err("cooldown"));
        r.cost = 1;
        assert_eq!(
            validate(&a, &b, &r, 20, 20, false, None),
            Err("insufficient_resource")
        );
        r.cost = 0;
        assert_eq!(validate(&a, &b, &r, 20, 20, true, None), Err("reward_pending"));
        b.health = 0;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, None), Err("target_dead"));
        b.health = 1;
        a.health = 0;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, None), Err("actor_dead"));
        a.health = 1;
        b.x = f32::NAN;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, None), Err("out_of_range"));
        b.x = 1.;
        r.melee = None;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, None), Err("out_of_range"));
    }
    /// PQ-416 (D-216): a ranged profile's strike limit is both radii summed plus
    /// its range in 3-D (1298 client `00583780`), inclusive; the melee range
    /// and every other refusal stay as they are.
    #[test]
    fn ranged_profile_limit_is_summed_radii_plus_range_in_three_dimensions() {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.melee = Some(crate::rules::Melee {
            actor_radius: 1.,
            target_radius: 1.,
            reach: 0.,
            facing_dot: 0.7,
        });
        r.cost = 0;
        let bow = Some(crate::combat_animation::Ranged { reach: 6., range: 8., cast_ms: 0, land: 0, hit: None, speed: 0., hold: None });
        let a = wire::Entity { health: 1, ..Default::default() };
        let mut b = wire::Entity { health: 1, x: 5., ..Default::default() };
        // Melee refuses 5 m (half the radii, 1 m); the bow strikes it.
        assert_eq!(validate(&a, &b, &r, 20, 20, false, None), Err("out_of_range"));
        assert!(validate(&a, &b, &r, 20, 20, false, bow).is_ok());
        b.x = 10.;
        assert!(validate(&a, &b, &r, 20, 20, false, bow).is_ok());
        b.x = 10.001;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, bow), Err("out_of_range"));
        // The height counts, unlike the melee check: 8 across and 6 up is 10.
        b.x = 8.;
        b.y = 6.;
        assert!(validate(&a, &b, &r, 20, 20, false, bow).is_ok());
        b.y = 6.01;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, bow), Err("out_of_range"));
        b.y = 0.;
        // The radii are summed whole: a 3 m target radius reaches 12 m.
        r.melee.as_mut().unwrap().target_radius = 3.;
        b.x = 12.;
        assert!(validate(&a, &b, &r, 20, 20, false, bow).is_ok());
        b.x = 12.01;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, bow), Err("out_of_range"));
        b.x = 5.;
        assert_eq!(validate(&a, &b, &r, 19, 20, false, bow), Err("cooldown"));
        assert_eq!(validate(&a, &b, &r, 20, 20, true, bow), Err("reward_pending"));
        b.health = 0;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, bow), Err("target_dead"));
        b.health = 1;
        b.z = f32::NAN;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, bow), Err("out_of_range"));
    }
}

#[cfg(test)]
mod damage_authority_tests {
    use super::*;
    struct Miss(usize);
    impl crate::damage::Rolls for Miss {
        fn roll(&mut self, n: u32) -> u32 {
            self.0 += 1;
            n - 1
        }
    }
    #[test]
    fn actual_attack_miss_spends_once_and_rejections_never_draw() {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.damage_policy = Some(crate::damage::Policy {
            player: crate::damage::Stats {
                attack: 36,
                defense: 20,
                accuracy: 50,
                evasion: 100,
            },
            npc: crate::damage::Stats {
                attack: 18,
                defense: 40,
                accuracy: 50,
                evasion: 100,
            },
        });
        r.cost = 7;
        let mut a = wire::Entity {
            health: 100,
            resource: 14,
            ..Default::default()
        };
        let mut b = wire::Entity {
            health: 100,
            ..Default::default()
        };
        let mut next = 0;
        let mut rng = Miss(0);
        let o = attack(&mut a, &mut b, &r, 20, &mut next, false, &mut rng).unwrap();
        assert!(!o.hit);
        assert_eq!((a.resource, b.health, rng.0), (7, 100, 1));
        assert_eq!((a.strike_result.as_str(), a.strike_damage), ("miss", 0));
        assert_eq!(
            attack(&mut a, &mut b, &r, 20, &mut next, false, &mut rng),
            Err("cooldown")
        );
        let tick = next;
        assert_eq!(
            attack(&mut a, &mut b, &r, tick, &mut next, true, &mut rng),
            Err("reward_pending")
        );
        b.x = r.range + 1.;
        assert_eq!(
            attack(&mut a, &mut b, &r, tick, &mut next, false, &mut rng),
            Err("out_of_range")
        );
        b.x = 0.;
        b.health = 0;
        assert_eq!(
            attack(&mut a, &mut b, &r, tick, &mut next, false, &mut rng),
            Err("target_dead")
        );
        b.health = 100;
        assert_eq!(rng.0, 1);
        attack(&mut a, &mut b, &r, tick, &mut next, false, &mut rng).unwrap();
        assert_eq!((a.resource, b.health, rng.0), (0, 100, 2));
        let tick = next;
        assert_eq!(
            attack(&mut a, &mut b, &r, tick, &mut next, false, &mut rng),
            Err("insufficient_resource")
        );
        assert_eq!(rng.0, 2);
    }
}

#[cfg(test)]
mod contribution_tests {
    use super::*;
    #[test]
    fn home_heal_abandons_credit_only_with_fresh_identity() {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.progression = Some(std::sync::Arc::new(crate::progression::Policy {
            items: None, coins: None,
            party_loot: None,
            party_rewards: None,
            equipment_stats: false,
            curve: "demo:curve/test".into(),
            item: r.item.clone(),
            author: "n3e".into(),
            revision: 1,
            thresholds: [0, 20, 50, 90, 140, 200, 270, 350, 440, 540],
            capacity: r.slots,
            starting: r.starting_items,
            npc_level: 1,
            base_xp: 10,
            radius: 50.,
            claim_radius: 3.,
            ttl: 120,
            hash: vec![0; 32],
        }));
        r.spawn_x = 0.;
        r.spawn_z = 0.;
        let ground = vec![
            [-4., 0., -4.],
            [4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., 4.],
        ];
        let ground = crate::movement::Collision::soup(ground.to_vec()).unwrap();
        let mut npc = Npc::new(&r, &ground, 20);
        npc.ledger.credit(1, 10, r.npc_health).unwrap();
        npc.entity.health = r.npc_health - 10;
        npc.entity.behavior = "return".into();
        let mut players = BTreeMap::new();
        let mut ids = VecDeque::new();
        let mut rng = crate::damage::Random::seeded(1);
        npc.tick(&mut players, &r, &ground, 1, &mut ids, &mut rng);
        assert_eq!(npc.entity.health, r.npc_health - 10);
        assert_eq!(npc.entity.id, 20);
        assert!(npc.ledger.active());
        ids.push_back(21);
        npc.tick(&mut players, &r, &ground, 2, &mut ids, &mut rng);
        assert_eq!(npc.entity.health, r.npc_health);
        assert_eq!(npc.entity.id, 21);
        assert!(!npc.ledger.active());
        assert!(npc.ledger.admits(1));
    }
}

#[cfg(test)]
mod landing_tests {
    use super::*;
    /// PQ-454 (D-228): a released shot's arrival neither checks nor takes the
    /// basic attack's cost, which its release took (Ebenezer's flying phase
    /// `0046f3f1` takes the Msp, the effecting phase skips the check for a
    /// row with a flight, `00464b43`); a landing without a release still
    /// checks and takes it. A pending reward is no refusal here: the caller
    /// holds the landing (ranged_shot::verdict's busy rule).
    #[test]
    fn a_released_arrival_neither_checks_nor_takes_the_cost() {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.cost = 7;
        let mut a = wire::Entity { health: 100, resource: 3, ..Default::default() };
        let mut b = wire::Entity { id: 9, health: 100, ..Default::default() };
        // A skill's impact during the flight left the archer below the cost.
        assert_eq!(landing(&a, &b, &r, false, None), Err("insufficient_resource"));
        assert_eq!(landing(&a, &b, &r, true, None), Ok(()));
        let hit = crate::damage::Outcome { hit: true, damage: 4 };
        let mut next = 0;
        finish_attack(&mut a, &mut b, &r, 50, &mut next, &hit, true);
        assert_eq!((a.resource, b.health, a.strike_target, next), (3, 96, 9, 50 + r.cooldown_ticks as u64));
        // Without a release the landing pays as every strike does.
        a.resource = 7;
        assert_eq!(landing(&a, &b, &r, false, None), Ok(()));
        finish_attack(&mut a, &mut b, &r, 60, &mut next, &hit, false);
        assert_eq!((a.resource, b.health), (0, 92));
        // The archer's and the target's lives are still checked.
        a.health = 0;
        assert_eq!(landing(&a, &b, &r, true, None), Err("actor_dead"));
        a.health = 1;
        b.health = 0;
        assert_eq!(landing(&a, &b, &r, true, None), Err("target_dead"));
    }
    /// PQ-467 (D-233): a ranged profile's hold. At the acceptance the target
    /// must be within both the start limit (radii + range, 3-D) and the
    /// hold; at the landing (or arrival) only the hold is checked, from where
    /// the archer stands then, as Ebenezer's effecting phase passes
    /// `004c1dbe` (`004635c8`), whose Type1 2 test passes while dx^2 + dz^2
    /// is at most the limit (`JA` at `004c203d`: inclusive). The glow bow's
    /// hold: sqrt(40^2 + 1000) on the ground plane.
    #[test]
    fn ranged_hold_at_the_acceptance_and_the_landing() {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        r.melee = Some(crate::rules::Melee { actor_radius: 1., target_radius: 1., reach: 0., facing_dot: 0.7 });
        r.cost = 0;
        let glow = crate::combat_animation::Hold { distance: 2600f32.sqrt(), planar: true };
        let bow = |hold| Some(crate::combat_animation::Ranged { reach: 40., range: 42., cast_ms: 1300, land: 27, hit: None, speed: 77., hold });
        let a = wire::Entity { health: 1, ..Default::default() };
        let mut b = wire::Entity { health: 1, x: 44., ..Default::default() };
        // The start limit (44 m, 3-D) binds at the acceptance; the hold (51 m)
        // does not refuse inside it.
        assert!(validate(&a, &b, &r, 20, 20, false, bow(Some(glow))).is_ok());
        b.x = 44.01;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, bow(Some(glow))), Err("out_of_range"));
        // A hold tighter than the start limit refuses at the acceptance too.
        let tight = Some(crate::combat_animation::Hold { distance: 30., planar: true });
        b.x = 30.;
        assert!(validate(&a, &b, &r, 20, 20, false, bow(tight)).is_ok());
        b.x = 30.01;
        assert_eq!(validate(&a, &b, &r, 20, 20, false, bow(tight)), Err("out_of_range"));
        assert!(validate(&a, &b, &r, 20, 20, false, bow(None)).is_ok());
        // The landing: no start limit, the hold on the ground plane, the height
        // ignored, inclusive; without a hold nothing is checked.
        b.x = 50.;
        assert_eq!(landing(&a, &b, &r, true, bow(Some(glow))), Ok(()));
        b.y = 30.;
        assert_eq!(landing(&a, &b, &r, true, bow(Some(glow))), Ok(()), "the height is not measured");
        b.x = 30.;
        b.z = 40.;
        assert_eq!(landing(&a, &b, &r, true, bow(Some(glow))), Ok(()), "50 m on the ground plane");
        b.z = 42.;
        assert_eq!(landing(&a, &b, &r, true, bow(Some(glow))), Err("out_of_range"));
        assert_eq!(landing(&a, &b, &r, true, bow(None)), Ok(()));
        assert_eq!(landing(&a, &b, &r, true, None), Ok(()));
        // In 3-D the height counts.
        let space = Some(crate::combat_animation::Hold { distance: 50., planar: false });
        b.x = 30.;
        b.y = 0.;
        b.z = 40.;
        assert_eq!(landing(&a, &b, &r, true, bow(space)), Ok(()));
        b.y = 1.;
        assert_eq!(landing(&a, &b, &r, true, bow(space)), Err("out_of_range"));
        // Equality passes (JA fails only above it).
        let exact = Some(crate::combat_animation::Hold { distance: 5., planar: true });
        b.x = 3.;
        b.y = 0.;
        b.z = 4.;
        assert_eq!(landing(&a, &b, &r, true, bow(exact)), Ok(()));
        b.z = 4.001;
        assert_eq!(landing(&a, &b, &r, true, bow(exact)), Err("out_of_range"));
        // Measured from where the archer stands now.
        let moved = wire::Entity { health: 1, x: 0.5, ..Default::default() };
        assert_eq!(landing(&moved, &b, &r, true, bow(exact)), Ok(()));
        // Life comes first; a non-finite position fails.
        b.health = 0;
        assert_eq!(landing(&a, &b, &r, true, bow(exact)), Err("target_dead"));
        b.health = 1;
        b.x = f32::NAN;
        assert_eq!(landing(&a, &b, &r, true, bow(exact)), Err("out_of_range"));
    }
}
