//! PQ-194 (D-157): the operator `kill`. The admin worker authorizes and audits
//! it against the authenticated character's `entity.kill`; the simulation then
//! calls `strike` on its tick, which checks the target and, if it may die,
//! applies the lethal blow so the caller can run the ordinary death path
//! (settlement with progression, the legacy reward without).
use crate::{gameplay::Npc, rules::Rules, wire};

/// Ticks between one session's kills (1 s at the 50 ms tick).
pub const INTERVAL: u64 = 20;

/// Checks the target and applies the lethal blow; a refusal (`Err`) changes
/// nothing, and does not spend the session's interval.
pub fn strike(
    npc: &mut Npc,
    actor: i64,
    rules: &Rules,
    last: &mut u64,
    // With progression: settlements outstanding and identities left, as a
    // strike's ledger admission counts them. None: the legacy reward path.
    admission: Option<(usize, usize)>,
    reward_pending: bool,
    tick: u64,
) -> Result<(), &'static str> {
    if npc.entity.life_state == wire::LifeState::Dormant as i32 {
        return Err("unknown_target");
    }
    if npc.entity.health == 0 {
        return Err("target_dead");
    }
    if npc.pending.is_some() {
        return Err("target_pending");
    }
    match admission {
        Some((outstanding, identities)) => npc.ledger.admission(actor, outstanding, identities)?,
        None if reward_pending => return Err("reward_pending"),
        None => {}
    }
    if *last != 0 && tick.saturating_sub(*last) < INTERVAL {
        return Err("kill_limit");
    }
    *last = tick;
    let remaining = npc.entity.health;
    if admission.is_some() {
        // The operator is credited what the blow takes, as any strike is.
        npc.ledger
            .credit(actor, remaining, remaining)
            .expect("ledger admitted before the blow");
    }
    crate::life::die(&mut npc.entity, npc.cycle.as_ref().unwrap_or(rules), tick);
    npc.entity.behavior = "dead".into();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rules(progression: bool) -> Rules {
        let mut r = Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        if progression {
            r.progression = Some(std::sync::Arc::new(crate::progression::Policy {
                items: None,
                coins: None,
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
        }
        r.spawn_x = 0.;
        r.spawn_z = 0.;
        r
    }
    fn npc(r: &Rules) -> Npc {
        let ground = [
            [-4., 0., -4.],
            [4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., -4.],
            [4., 0., 4.],
            [-4., 0., 4.],
        ];
        let ground = crate::movement::Collision::soup(ground.to_vec()).unwrap();
        Npc::new(r, &ground, 20)
    }

    #[test]
    fn kill_credits_the_operator_and_dies_by_the_package_rules() {
        let r = rules(true);
        let mut n = npc(&r);
        // Another player's earlier damage stays in the ledger beside the kill.
        n.ledger.credit(7, 3, n.entity.health).unwrap();
        n.entity.health -= 3;
        let remaining = n.entity.health;
        let mut last = 0;
        assert_eq!(strike(&mut n, 1, &r, &mut last, Some((0, 4)), false, 100), Ok(()));
        assert_eq!(n.entity.health, 0);
        assert_eq!(n.entity.behavior, "dead");
        assert_eq!(last, 100);
        let delay = r.life.map_or(r.respawn_ticks, |p| p.npc_respawn) as u64;
        assert_eq!(n.entity.respawn_tick, 100 + delay);
        let p = r.progression.clone().unwrap();
        let near = |_| {
            Some(crate::progression::Presence {
                alive: true,
                zone: "demo".into(),
                position: [0., 0., 0.],
                level: 1,
            })
        };
        let recipients = n.ledger.freeze(&p, "demo", [0., 0., 0.], near).unwrap();
        let credit = |id| recipients.iter().find(|x| x.id == id).map(|x| x.credit);
        assert_eq!(credit(1), Some(remaining as u64));
        assert_eq!(credit(7), Some(3));
        assert_eq!(n.ledger.order(), vec![7, 1]);
    }

    #[test]
    fn refusals_change_nothing() {
        let r = rules(true);
        let mut last = 0;
        // Already dead, dormant, or awaiting a strike's durable commit.
        let mut dead = npc(&r);
        crate::life::die(&mut dead.entity, &r, 5);
        let before = dead.entity.clone();
        assert_eq!(strike(&mut dead, 1, &r, &mut last, Some((0, 4)), false, 10), Err("target_dead"));
        dead.entity.life_state = wire::LifeState::Dormant as i32;
        assert_eq!(strike(&mut dead, 1, &r, &mut last, Some((0, 4)), false, 10), Err("unknown_target"));
        assert_eq!(dead.entity.health, before.health);
        let mut pending = npc(&r);
        pending.pending = Some(9);
        assert_eq!(strike(&mut pending, 1, &r, &mut last, Some((0, 4)), false, 10), Err("target_pending"));
        // The ledger's own capacity answers, as for a strike.
        let mut full = npc(&r);
        assert_eq!(strike(&mut full, 1, &r, &mut last, Some((64, 4)), false, 10), Err("settlement_capacity"));
        assert_eq!(strike(&mut full, 1, &r, &mut last, Some((0, 0)), false, 10), Err("settlement_capacity"));
        for id in 100..164 {
            full.ledger.credit(id, 1, 1000).unwrap();
        }
        assert_eq!(strike(&mut full, 1, &r, &mut last, Some((0, 4)), false, 10), Err("contributor_capacity"));
        for n in [&pending, &full] {
            assert!(n.entity.health > 0 && n.entity.behavior != "dead");
        }
        assert!(!full.ledger.order().contains(&1));
        assert_eq!(last, 0, "a refusal spent the interval");
    }

    #[test]
    fn one_kill_per_interval_and_legacy_reward_gate() {
        let r = rules(false);
        let mut last = 0;
        let mut a = npc(&r);
        let mut b = npc(&r);
        assert_eq!(strike(&mut a, 1, &r, &mut last, None, true, 40), Err("reward_pending"));
        assert_eq!(strike(&mut a, 1, &r, &mut last, None, false, 40), Ok(()));
        assert!(!a.ledger.active(), "no ledger without progression");
        assert_eq!(strike(&mut b, 1, &r, &mut last, None, false, 40 + INTERVAL - 1), Err("kill_limit"));
        assert!(b.entity.health > 0);
        assert_eq!(strike(&mut b, 1, &r, &mut last, None, false, 40 + INTERVAL), Ok(()));
        assert_eq!(b.entity.health, 0);
    }
}
