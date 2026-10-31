//! Runtime life rules; requested player transitions commit through accounts. Durable rewards belong to characters, never these instances.
use crate::{
    content::{bad, Reader, Result},
    rules::Rules,
    wire::{self, LifeState},
};
use std::path::Path;
#[derive(Clone, Copy, Debug)]
pub struct Policy {
    pub player_delay: u32,
    pub corpse: u32,
    pub npc_respawn: u32,
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3L1" || r.u()? != 1 {
            return Err(bad("life model"));
        }
        let p = Self {
            player_delay: r.u()?,
            corpse: r.u()?,
            npc_respawn: r.u()?,
        };
        if p.player_delay > 1200
            || p.corpse > 1200
            || !(1..=12000).contains(&p.npc_respawn)
            || p.corpse > p.npc_respawn
        {
            return Err(bad("life timer"));
        }
        r.end()?;
        Ok(p)
    }
}
pub fn die(e: &mut wire::Entity, r: &Rules, tick: u64) {
    e.respawn_tick = tick
        + r.life
            .map(|p| if e.npc { p.npc_respawn } else { p.player_delay })
            .unwrap_or(r.respawn_ticks) as u64;
    e.health = 0;
    e.sitting = false;
    e.movement_mode = 0;
    if let Some(p) = r.life {
        e.life_state = if e.npc {
            LifeState::Corpse
        } else {
            LifeState::DeadWaiting
        } as i32;
        e.corpse_until_tick = if e.npc { tick + p.corpse as u64 } else { 0 };
        refresh(e, tick);
    }
}
pub fn refresh(e: &mut wire::Entity, tick: u64) {
    if e.health == 0 && e.life_state != 0 {
        e.life_state = if e.npc {
            if tick >= e.corpse_until_tick {
                LifeState::Dormant
            } else {
                LifeState::Corpse
            }
        } else if tick >= e.respawn_tick {
            LifeState::DeadReady
        } else {
            LifeState::DeadWaiting
        } as i32;
    }
}
pub fn validate(
    e: &wire::Entity,
    generation: i64,
    connection: i64,
    a: &wire::Respawn,
    last: &mut u64,
    tick: u64,
    enabled: bool,
) -> std::result::Result<(), &'static str> {
    if generation != connection || a.session != generation as u64 {
        return Err("stale_session");
    }
    if a.seq == 0 || a.seq <= *last || a.seq >= i64::MAX as u64 {
        return Err("stale_request");
    }
    *last = a.seq;
    if !enabled {
        return Err("unsupported");
    }
    if a.entity != e.id {
        return Err("stale_entity");
    }
    if e.health > 0 || e.npc {
        return Err("not_dead");
    }
    if tick < e.respawn_tick {
        return Err("too_early");
    }
    Ok(())
}
pub fn revive(e: &mut wire::Entity, id: u64, spawn: [f32; 3], r: &Rules) {
    // ack and input/action sequences stay session-monotonic across replacement.
    e.id = id;
    e.strike_style = 0;
    e.strike_moving=false;
    e.sitting = false;
    e.x = spawn[0];
    e.y = spawn[1];
    e.z = spawn[2];
    e.health = r.health;
    e.resource = r.resource;
    e.respawn_tick = 0;
    e.corpse_until_tick = 0;
    e.strike_tick = 0;
    e.strike_sequence = 0;
    e.strike_damage = 0;
    e.strike_result.clear();
    e.movement_mode = 0;
    e.behavior.clear();
    e.life_state = if r.life.is_some() {
        LifeState::Alive as i32
    } else {
        0
    };
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn request_guards_are_identity_and_time_bound() {
        let mut e = wire::Entity {
            id: 10,
            health: 30,
            ..Default::default()
        };
        let mut last = 0;
        let mut a = wire::Respawn {
            session: 2,
            seq: 1,
            entity: 10,
        };
        assert_eq!(
            validate(&e, 2, 1, &a, &mut last, 100, true),
            Err("stale_session")
        );
        assert_eq!(last, 0);
        assert_eq!(
            validate(&e, 2, 2, &a, &mut last, 100, true),
            Err("not_dead")
        );
        e.health = 0;
        e.respawn_tick = 101;
        assert_eq!(
            validate(&e, 2, 2, &a, &mut last, 101, true),
            Err("stale_request")
        );
        a.seq = 2;
        assert_eq!(
            validate(&e, 2, 2, &a, &mut last, 100, true),
            Err("too_early")
        );
        a.seq = 3;
        a.entity = 9;
        assert_eq!(
            validate(&e, 2, 2, &a, &mut last, 101, true),
            Err("stale_entity")
        );
        a.seq = 4;
        a.entity = 10;
        assert!(validate(&e, 2, 2, &a, &mut last, 101, true).is_ok());
        e.id = 11;
        e.health = 30;
        a.seq = 5;
        assert_eq!(
            validate(&e, 2, 2, &a, &mut last, 102, true),
            Err("stale_entity")
        );
        a.entity = 11;
        a.seq = 6;
        assert_eq!(
            validate(&e, 2, 2, &a, &mut last, 102, true),
            Err("not_dead")
        );
    }
    #[test]
    fn separate_deadlines_and_replacement_clear_transient_state() {
        let mut r = Rules::load(Path::new("../build/packages/legacy-demo/gameplay.bin"), "demo").unwrap();
        r.life = Some(Policy {
            player_delay: 60,
            corpse: 40,
            npc_respawn: 120,
        });
        let mut e = wire::Entity {
            id: 7,
            health: 1,
            ack: 90,
            strike_tick: 10,
            strike_sequence: 129,
            ..Default::default()
        };
        die(&mut e, &r, 20);
        assert_eq!(e.respawn_tick, 80);
        refresh(&mut e, 79);
        assert_eq!(e.life_state, LifeState::DeadWaiting as i32);
        refresh(&mut e, 80);
        assert_eq!(e.life_state, LifeState::DeadReady as i32);
        revive(&mut e, 8, [1., 2., 3.], &r);
        assert_eq!((e.id, e.ack, e.strike_tick, e.respawn_tick), (8, 90, 0, 0));
        assert_eq!(e.strike_sequence, 0);
        assert_eq!(e.life_state, LifeState::Alive as i32);
        e.npc = true;
        die(&mut e, &r, 20);
        assert_eq!((e.corpse_until_tick, e.respawn_tick), (60, 140));
        refresh(&mut e, 59);
        assert_eq!(e.life_state, LifeState::Corpse as i32);
        refresh(&mut e, 60);
        assert_eq!(e.life_state, LifeState::Dormant as i32);
    }
}

// Explicit acceptance-test crash points; opt-in process environment only.
pub fn fault(point: &str) {
    if std::env::var("N3E_LIFE_FAULT").as_deref() == Ok(point) {
        std::process::exit(86);
    }
}
