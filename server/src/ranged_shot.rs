//! Held ranged shots (PQ-420, D-217).
//!
//! A ranged profile with a cast time (`ranged-attack.bin` N3RC) does not
//! resolve its strike when the server accepts it. The shot is held on the
//! archer, the strike fields show the cast from the acceptance tick, and the
//! strike lands `land` ticks later through the ordinary hit path, unless the
//! archer moves, dies, changes weapon or session, or the target goes. 1298's
//! cast tick (`KnightOnLine.exe` `00585830`) ends the cast when the stretched
//! clip passes its first marker (`004689f0`) and cancels it once the caster's
//! action state leaves 6 or its move state is set, as a walk does (`0045a950`).
//! The server decides all of it from its own state; the client only asks.
//!
//! PQ-439 (D-223): under a profile with a flight the landing tick is the
//! release. The shot then flies for the 3-D distance between the archer and
//! the target over the flight's speed and resolves when it arrives, as
//! 1298's NPC loses HP only when the shooter's client reports its arrow's
//! collision (`0047a8d0` -> the effecting phase, which Ebenezer's
//! `004630a6` forwards and the AI server's `0040d471` applies at once). A
//! movement no longer cancels a released shot; the rest of D-217's rules do.
//!
//! PQ-444 (D-224): a shot with a flight that spends ammunition is released
//! only once a durable write of its own has removed the arrow, as Ebenezer's
//! flying phase (`004630a6` -> `0046f3f1` -> `004b0792`) spends it at the
//! release; the arrival then commits only the wear.
use crate::wire;

/// One held shot. Only the simulation creates it, at the acceptance tick.
#[derive(Clone, Debug)]
pub(crate) struct Shot {
    pub(crate) action: wire::Action,
    pub(crate) generation: i64,
    /// The archer's entity id and life revision at the acceptance.
    pub(crate) entity: u64,
    pub(crate) life: i64,
    /// The target NPC's entity id (the action's target).
    pub(crate) npc: u64,
    /// The profile the committed equipment selected.
    pub(crate) style: u32,
    /// The acceptance tick (the cast start) and the landing tick.
    pub(crate) started: u64,
    pub(crate) land: u64,
    /// PQ-421 (D-218): how many ticks before `land` the landing starts: 1
    /// for a profile without a flight that spends ammunition, whose landing
    /// always makes a durable commit that publishes the hit a tick later, so
    /// the hit still comes at `land` (1298's cadence); 0 otherwise (PQ-444:
    /// also with a flight, whose arrival no longer spends it).
    pub(crate) lead: u64,
    /// A movement input that moves was admitted after the acceptance.
    pub(crate) moved: bool,
    /// The landing has been queued for the next command drain.
    pub(crate) landing: bool,
    /// PQ-439 (D-223): the profile's flight speed (m/s), 0 without a
    /// flight: the shot is then released at `land` and lands at `arrive`.
    pub(crate) speed: f32,
    /// The shot has been released (its arrow flies).
    pub(crate) released: bool,
    /// The arrival tick, set at the release (`land` until then).
    pub(crate) arrive: u64,
    /// PQ-444 (D-224): the release spends the profile's ammunition in a
    /// durable write of its own (a profile with a flight and ammunition).
    pub(crate) spend: bool,
    /// That write is pending: the shot is neither released nor cancelled
    /// until it ends.
    pub(crate) releasing: bool,
}

/// What a held shot's archer and target look like this tick.
pub(crate) struct Seen<'a> {
    pub(crate) failed: bool,
    pub(crate) generation: i64,
    pub(crate) entity: u64,
    pub(crate) life: i64,
    pub(crate) health: u32,
    /// The profile the committed equipment selects now.
    pub(crate) style: u32,
    /// The NPC with the shot's target id, if it is still there.
    pub(crate) target: Option<&'a wire::Entity>,
    /// The landing must wait: the archer's durable combat write (wear, an
    /// incoming hit) or another player's commit on the target is pending.
    pub(crate) busy: bool,
    /// PQ-439 (D-223): the archer's previous shot is still in flight, so
    /// this one's release waits.
    pub(crate) flying: bool,
    /// PQ-444 (D-224): a durable combat write of the archer's own (an
    /// arrival's wear, an incoming hit's) is pending, so a release that
    /// spends ammunition waits for it.
    pub(crate) writing: bool,
    /// PQ-454 (D-228): the archer holds less resource than the basic
    /// attack's cost, which a shot with a flight pays at its release.
    pub(crate) short: bool,
    /// PQ-467 (D-233): the target is within the profile's hold from where
    /// the archer stands now (true without a hold or a target).
    pub(crate) held: bool,
}

/// The tick's decision for a held shot.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Verdict {
    /// Keep holding it.
    Hold,
    /// Resolve the strike now.
    Land,
    /// PQ-439 (D-223): release the shot now; it lands when its arrow arrives.
    Release,
    /// Drop it with no effect; the archer's result is this status.
    Cancel(&'static str),
}

/// How long past its landing tick a shot may wait for a pending write or for
/// combat capacity before it is dropped (`combat_pending`): 1 s.
pub(crate) const DEFER: u64 = 20;

/// The longest flight: 200 ticks (10 s, the client's flight clip bound and
/// 1298's arrow bundle life).
pub(crate) const MAX_FLIGHT: u64 = 200;

/// PQ-439 (D-223): the ticks an arrow flies `distance` metres at `speed` m/s,
/// rounded up to the 50 ms tick, at most `MAX_FLIGHT`.
pub(crate) fn flight_ticks(distance: f32, speed: f32) -> u64 {
    let ticks = (f64::from(distance) / f64::from(speed) * 20.).ceil();
    if ticks.is_finite() && ticks >= 0. { (ticks as u64).min(MAX_FLIGHT) } else { MAX_FLIGHT }
}

/// Releases a shot at `tick`: its arrow flies `distance` metres.
pub(crate) fn release(shot: &mut Shot, distance: f32, tick: u64) {
    shot.released = true;
    shot.arrive = tick + flight_ticks(distance, shot.speed);
}

/// D-217's rules, in order: the session, the archer's life, a movement after
/// the acceptance (before the release only, D-223), the weapon, the target;
/// then the landing tick (the arrival tick of a released shot), deferred
/// while a durable combat write is pending on the archer or the target (as a
/// skill's impact is), the archer's reward is pending (PQ-454, D-228; both
/// are `busy`) or the landing found no combat capacity, for at most `DEFER`
/// ticks. A shot with a flight is released at its landing tick instead, once
/// the archer's previous flight has landed (and, when the release spends
/// ammunition, no durable write of the archer's own is pending, D-224), at
/// most `DEFER` ticks late, and fails `out_of_range` there when the target
/// is out of the profile's hold (PQ-467, D-233), then `insufficient_resource`
/// when the archer cannot pay the basic attack's cost (`short`, D-228). The
/// hold at a landing or an arrival is `gameplay::landing`'s.
pub(crate) fn verdict(shot: &Shot, seen: &Seen, tick: u64) -> Verdict {
    if seen.failed || seen.generation != shot.generation || seen.entity != shot.entity || seen.life != shot.life {
        return Verdict::Cancel("stale_session");
    }
    if seen.health == 0 {
        return Verdict::Cancel("actor_dead");
    }
    if shot.moved && !shot.released {
        return Verdict::Cancel("interrupted");
    }
    if seen.style != shot.style {
        return Verdict::Cancel("equipment_changed");
    }
    match seen.target {
        None => return Verdict::Cancel("stale_target"),
        Some(t) if t.health == 0 => return Verdict::Cancel("target_dead"),
        _ => {}
    }
    if shot.speed > 0. && !shot.released {
        return if tick < shot.land {
            Verdict::Hold
        } else if tick > shot.land + DEFER {
            Verdict::Cancel("combat_pending")
        } else if seen.flying || (shot.spend && seen.writing) {
            Verdict::Hold
        } else if !seen.held {
            // PQ-467 (D-233): the release is Ebenezer's flying phase, which
            // the magic packet range-checks (004c1dbe at 004635c8) before
            // 0046f3f1 takes the Msp and the arrow: out of the hold, the
            // shot fails with neither spent.
            Verdict::Cancel("out_of_range")
        } else if seen.short {
            // PQ-454 (D-228): the release pays the basic attack's cost, as
            // Ebenezer's flying phase fails (phase 4) a user whose MP is
            // below the row's Msp before the arrow (0046f48a-0046f49b).
            Verdict::Cancel("insufficient_resource")
        } else {
            Verdict::Release
        };
    }
    let due = if shot.released { shot.arrive } else { shot.land };
    if tick + shot.lead < due {
        Verdict::Hold
    } else if tick > due + DEFER {
        Verdict::Cancel("combat_pending")
    } else if seen.busy {
        Verdict::Hold
    } else {
        Verdict::Land
    }
}

/// PQ-439 (D-223): the archer's strike fields, kept for a newer held cast
/// while an older shot's arrow lands, so observers neither restart the old
/// clip nor stop the new one.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Strike {
    tick: u64,
    target: u64,
    result: String,
    damage: u32,
    style: u32,
    moving: bool,
    sequence: u64,
}
impl Strike {
    pub(crate) fn of(e: &wire::Entity) -> Self {
        Strike {
            tick: e.strike_tick,
            target: e.strike_target,
            result: e.strike_result.clone(),
            damage: e.strike_damage,
            style: e.strike_style,
            moving: e.strike_moving,
            sequence: e.strike_sequence,
        }
    }
    pub(crate) fn put(self, e: &mut wire::Entity) {
        e.strike_tick = self.tick;
        e.strike_target = self.target;
        e.strike_result = self.result;
        e.strike_damage = self.damage;
        e.strike_style = self.style;
        e.strike_moving = self.moving;
        e.strike_sequence = self.sequence;
    }
}

/// Marks the cast that started at `started` as released (D-223): the cast
/// effect ends, the clip plays on and the strike fields keep the cast start.
pub(crate) fn released(e: &mut wire::Entity, started: u64) {
    if e.strike_tick == started {
        e.strike_result = "released".into();
        e.strike_damage = 0;
    }
}

/// Clears the cast that started at `started` from the archer's strike
/// fields, so observers stop its clip (a `strike_tick` of 0 starts none) and
/// late joiners never start it.
pub(crate) fn clear(e: &mut wire::Entity, started: u64) {
    // PQ-439 (D-223): a released cast keeps its fields (its clip played on),
    // whether it is cancelled in flight or refused at its arrival.
    if e.strike_tick == started && e.strike_result == "casting" {
        e.strike_tick = 0;
        e.strike_sequence = 0;
        e.strike_target = 0;
        e.strike_result.clear();
        e.strike_damage = 0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn shot() -> Shot {
        Shot {
            action: wire::Action { seq: 9, target: 77, ..Default::default() },
            generation: 3,
            entity: 5,
            life: 1,
            npc: 77,
            style: 6,
            started: 100,
            land: 127,
            lead: 0,
            moved: false,
            landing: false,
            speed: 0.,
            released: false,
            arrive: 127,
            spend: false,
            releasing: false,
        }
    }
    #[test]
    fn holds_until_the_landing_and_cancels_on_each_rule() {
        let target = wire::Entity { id: 77, health: 30, npc: true, ..Default::default() };
        let dead = wire::Entity { health: 0, ..target.clone() };
        let seen = |t| Seen { failed: false, generation: 3, entity: 5, life: 1, health: 40, style: 6, target: t, busy: false, flying: false, writing: false, short: false, held: true };
        let s = shot();
        assert_eq!(verdict(&s, &seen(Some(&target)), 100), Verdict::Hold);
        assert_eq!(verdict(&s, &seen(Some(&target)), 126), Verdict::Hold);
        assert_eq!(verdict(&s, &seen(Some(&target)), 127), Verdict::Land);
        // D-218: a shot that spends ammunition starts its landing (its
        // durable commit) a tick early, so its hit is published at 127.
        let ammo = Shot { lead: 1, ..shot() };
        assert_eq!(verdict(&ammo, &seen(Some(&target)), 125), Verdict::Hold);
        assert_eq!(verdict(&ammo, &seen(Some(&target)), 126), Verdict::Land);
        assert_eq!(verdict(&Shot { moved: true, ..ammo.clone() }, &seen(Some(&target)), 126), Verdict::Cancel("interrupted"));
        assert_eq!(verdict(&ammo, &seen(Some(&target)), 127 + DEFER + 1), Verdict::Cancel("combat_pending"));
        // A pending durable write defers the landing a tick at a time.
        assert_eq!(verdict(&s, &Seen { busy: true, ..seen(Some(&target)) }, 127), Verdict::Hold);
        assert_eq!(verdict(&s, &Seen { busy: true, ..seen(Some(&target)) }, 127 + DEFER), Verdict::Hold);
        // A deferred landing (a pending write, or no capacity at the landing)
        // is retried each tick and dropped after DEFER ticks.
        assert_eq!(verdict(&s, &seen(Some(&target)), 127 + DEFER), Verdict::Land);
        assert_eq!(verdict(&s, &Seen { busy: true, ..seen(Some(&target)) }, 128 + DEFER), Verdict::Cancel("combat_pending"));
        assert_eq!(verdict(&s, &seen(Some(&target)), 128 + DEFER), Verdict::Cancel("combat_pending"));
        let moved = Shot { moved: true, ..shot() };
        assert_eq!(verdict(&moved, &seen(Some(&target)), 101), Verdict::Cancel("interrupted"));
        assert_eq!(verdict(&moved, &seen(Some(&target)), 127), Verdict::Cancel("interrupted"), "a move wins over the landing");
        assert_eq!(verdict(&s, &Seen { health: 0, ..seen(Some(&target)) }, 110), Verdict::Cancel("actor_dead"));
        for stale in [
            Seen { failed: true, ..seen(Some(&target)) },
            Seen { generation: 4, ..seen(Some(&target)) },
            Seen { entity: 6, ..seen(Some(&target)) },
            Seen { life: 2, ..seen(Some(&target)) },
        ] {
            assert_eq!(verdict(&s, &stale, 127), Verdict::Cancel("stale_session"));
        }
        assert_eq!(verdict(&s, &Seen { style: 1, ..seen(Some(&target)) }, 127), Verdict::Cancel("equipment_changed"));
        assert_eq!(verdict(&s, &seen(None), 110), Verdict::Cancel("stale_target"));
        assert_eq!(verdict(&s, &seen(Some(&dead)), 127), Verdict::Cancel("target_dead"));
    }
    /// PQ-439 (D-223): a shot with a flight is released at its landing tick
    /// (after the archer's previous flight), flies distance / speed rounded
    /// up to the tick, and lands at its arrival (a tick early with
    /// ammunition), deferred as D-217's landing; once released a movement no
    /// longer cancels it, and the rest of D-217's rules still do.
    #[test]
    fn a_flight_releases_at_the_landing_and_lands_at_the_arrival() {
        let target = wire::Entity { id: 77, health: 30, npc: true, ..Default::default() };
        let seen = |t| Seen { failed: false, generation: 3, entity: 5, life: 1, health: 40, style: 6, target: t, busy: false, flying: false, writing: false, short: false, held: true };
        // The glow bow's arrow (77 m/s): 6 m in 2 ticks, 42 m in 11 (0.55 s);
        // the fixture's (20 m/s) 6 m in 6; a whole tick is not rounded up.
        assert_eq!((flight_ticks(6., 77.), flight_ticks(42., 77.), flight_ticks(6., 20.), flight_ticks(5., 20.)), (2, 11, 6, 5));
        assert_eq!((flight_ticks(0., 77.), flight_ticks(1e6, 1.), flight_ticks(f32::NAN, 1.)), (0, MAX_FLIGHT, MAX_FLIGHT));
        let s = Shot { speed: 20., lead: 1, ..shot() };
        assert_eq!(verdict(&s, &seen(Some(&target)), 126), Verdict::Hold);
        // The release needs no durable write: busy does not hold it, and the
        // ammunition lead does not move it.
        assert_eq!(verdict(&s, &Seen { busy: true, ..seen(Some(&target)) }, 127), Verdict::Release);
        // A previous flight still in the air holds it, at most DEFER ticks.
        assert_eq!(verdict(&s, &Seen { flying: true, ..seen(Some(&target)) }, 127 + DEFER), Verdict::Hold);
        assert_eq!(verdict(&s, &Seen { flying: true, ..seen(Some(&target)) }, 128 + DEFER), Verdict::Cancel("combat_pending"));
        assert_eq!(verdict(&Shot { moved: true, ..s.clone() }, &seen(Some(&target)), 127), Verdict::Cancel("interrupted"));
        let mut r = s.clone();
        release(&mut r, 6., 127);
        assert_eq!((r.released, r.arrive), (true, 133));
        assert_eq!(verdict(&r, &seen(Some(&target)), 131), Verdict::Hold);
        assert_eq!(verdict(&r, &seen(Some(&target)), 132), Verdict::Land, "the arrow's commit a tick early");
        assert_eq!(verdict(&Shot { lead: 0, ..r.clone() }, &seen(Some(&target)), 132), Verdict::Hold);
        assert_eq!(verdict(&Shot { lead: 0, ..r.clone() }, &seen(Some(&target)), 133), Verdict::Land);
        assert_eq!(verdict(&r, &Seen { busy: true, ..seen(Some(&target)) }, 133 + DEFER), Verdict::Hold);
        assert_eq!(verdict(&r, &seen(Some(&target)), 134 + DEFER), Verdict::Cancel("combat_pending"));
        // Released, a movement does not cancel it (1298's arrow flies on).
        assert_eq!(verdict(&Shot { moved: true, ..r.clone() }, &seen(Some(&target)), 132), Verdict::Land);
        assert_eq!(verdict(&Shot { moved: true, ..r.clone() }, &seen(Some(&target)), 130), Verdict::Hold);
        // The archer's death, a session change, another profile or the
        // target's death or departure still do.
        assert_eq!(verdict(&r, &Seen { health: 0, ..seen(Some(&target)) }, 130), Verdict::Cancel("actor_dead"));
        assert_eq!(verdict(&r, &Seen { life: 2, ..seen(Some(&target)) }, 130), Verdict::Cancel("stale_session"));
        assert_eq!(verdict(&r, &Seen { style: 1, ..seen(Some(&target)) }, 130), Verdict::Cancel("equipment_changed"));
        let dead = wire::Entity { health: 0, ..target.clone() };
        assert_eq!(verdict(&r, &seen(Some(&dead)), 130), Verdict::Cancel("target_dead"));
        assert_eq!(verdict(&r, &seen(None), 130), Verdict::Cancel("stale_target"));
        // A flight of 0 ticks (the target at the archer) lands next tick.
        let mut z = s.clone();
        release(&mut z, 0., 127);
        assert_eq!(verdict(&z, &seen(Some(&target)), 128), Verdict::Land);
        // Without a flight nothing changes: the shot lands at its landing tick.
        assert_eq!(verdict(&Shot { lead: 1, ..shot() }, &seen(Some(&target)), 126), Verdict::Land);
    }
    /// PQ-444 (D-224): a release that spends ammunition makes a durable
    /// write, so it waits for the archer's own pending write (an arrival's
    /// wear, an incoming hit's), at most DEFER ticks; a write pending on the
    /// target does not hold it, and a release that spends nothing ignores
    /// both. Once released, the arrival's busy rule is unchanged.
    #[test]
    fn a_release_that_spends_waits_for_the_archers_own_write() {
        let target = wire::Entity { id: 77, health: 30, npc: true, ..Default::default() };
        let seen = |t| Seen { failed: false, generation: 3, entity: 5, life: 1, health: 40, style: 6, target: t, busy: false, flying: false, writing: false, short: false, held: true };
        let s = Shot { speed: 20., spend: true, ..shot() };
        assert_eq!(verdict(&s, &seen(Some(&target)), 126), Verdict::Hold);
        assert_eq!(verdict(&s, &seen(Some(&target)), 127), Verdict::Release);
        let own = Seen { writing: true, busy: true, ..seen(Some(&target)) };
        assert_eq!(verdict(&s, &own, 127), Verdict::Hold);
        assert_eq!(verdict(&s, &own, 127 + DEFER), Verdict::Hold);
        assert_eq!(verdict(&s, &own, 128 + DEFER), Verdict::Cancel("combat_pending"));
        assert_eq!(verdict(&s, &Seen { busy: true, ..seen(Some(&target)) }, 127), Verdict::Release, "the target's write");
        assert_eq!(verdict(&Shot { spend: false, ..s.clone() }, &own, 127), Verdict::Release);
        // A late write still releases inside the window; the previous arrow
        // holds it as before.
        assert_eq!(verdict(&s, &seen(Some(&target)), 127 + DEFER), Verdict::Release);
        assert_eq!(verdict(&s, &Seen { flying: true, ..seen(Some(&target)) }, 127), Verdict::Hold);
        // A move before the write starts still cancels it, as do the rest of
        // D-217's rules.
        assert_eq!(verdict(&Shot { moved: true, ..s.clone() }, &seen(Some(&target)), 127), Verdict::Cancel("interrupted"));
        assert_eq!(verdict(&s, &Seen { style: 1, ..seen(Some(&target)) }, 127), Verdict::Cancel("equipment_changed"));
        // Released (its arrow spent), the arrival lands at once without a
        // lead and waits for a pending write as any landing does.
        let mut r = s.clone();
        release(&mut r, 6., 127);
        assert_eq!(verdict(&r, &seen(Some(&target)), 132), Verdict::Hold);
        assert_eq!(verdict(&r, &seen(Some(&target)), 133), Verdict::Land);
        assert_eq!(verdict(&r, &own, 133), Verdict::Hold);
        let dead = wire::Entity { health: 0, ..target.clone() };
        assert_eq!(verdict(&r, &seen(Some(&dead)), 130), Verdict::Cancel("target_dead"));
    }
    /// PQ-454 (D-228): a shot with a flight pays the basic attack's cost at
    /// its release, so the release, not the arrival, is refused when the
    /// archer cannot pay it (after the holds, as Ebenezer's flying phase
    /// checks the MP once the shot reaches it); a released arrival is no
    /// longer refused for it, and a pending reward (`busy`) holds the arrival
    /// for at most DEFER ticks instead of refusing it.
    #[test]
    fn the_release_pays_the_cost_and_a_reward_holds_the_arrival() {
        let target = wire::Entity { id: 77, health: 30, npc: true, ..Default::default() };
        let seen = |t| Seen { failed: false, generation: 3, entity: 5, life: 1, health: 40, style: 6, target: t, busy: false, flying: false, writing: false, short: false, held: true };
        for spend in [false, true] {
            let s = Shot { speed: 20., spend, ..shot() };
            let short = Seen { short: true, ..seen(Some(&target)) };
            assert_eq!(verdict(&s, &short, 126), Verdict::Hold, "not before the release tick");
            assert_eq!(verdict(&s, &short, 127), Verdict::Cancel("insufficient_resource"));
            // The previous arrow (or, when it spends, the archer's own write)
            // holds it first; the cost is checked when it would leave.
            assert_eq!(verdict(&s, &Seen { flying: true, ..short }, 127), Verdict::Hold);
            assert_eq!(verdict(&s, &Seen { writing: true, short: true, ..seen(Some(&target)) }, 127),
                if spend { Verdict::Hold } else { Verdict::Cancel("insufficient_resource") });
            assert_eq!(verdict(&s, &seen(Some(&target)), 127), Verdict::Release);
            // Released, the arrival is never refused for the cost: a skill's
            // impact during the flight may leave the archer short.
            let mut r = s.clone();
            release(&mut r, 6., 127);
            let short = Seen { short: true, ..seen(Some(&target)) };
            assert_eq!(verdict(&r, &short, 133), Verdict::Land);
            // A skill kill's pending reward is `busy`: the arrival waits, at
            // most DEFER ticks, and lands once the reward settles.
            let reward = Seen { busy: true, ..seen(Some(&target)) };
            assert_eq!(verdict(&r, &reward, 133), Verdict::Hold);
            assert_eq!(verdict(&r, &reward, 133 + DEFER), Verdict::Hold);
            assert_eq!(verdict(&r, &seen(Some(&target)), 134), Verdict::Land);
            assert_eq!(verdict(&r, &reward, 134 + DEFER), Verdict::Cancel("combat_pending"));
        }
        // Without a flight the landing keeps its own cost check (the strike
        // pays at its landing); `short` does not refuse it here.
        assert_eq!(verdict(&shot(), &Seen { short: true, ..seen(Some(&target)) }, 127), Verdict::Land);
    }
    /// PQ-467 (D-233): the release is Ebenezer's flying phase, which the
    /// magic packet range-checks (`004c1dbe` at `004635c8`) before
    /// `0046f3f1` takes the Msp and the arrow: a target out of the hold
    /// (`held` false) fails the shot `out_of_range` when it would leave,
    /// after the waits for the previous arrow and the archer's own write and
    /// before the cost, so neither is spent. Before the release tick the
    /// hold is not checked (no phase reaches Ebenezer during the cast), and
    /// a released arrow's arrival leaves it to `gameplay::landing`.
    #[test]
    fn the_release_checks_the_hold_before_the_cost() {
        let target = wire::Entity { id: 77, health: 30, npc: true, ..Default::default() };
        let seen = |t| Seen { failed: false, generation: 3, entity: 5, life: 1, health: 40, style: 6, target: t, busy: false, flying: false, writing: false, short: false, held: true };
        for spend in [false, true] {
            let s = Shot { speed: 20., spend, ..shot() };
            let out = Seen { held: false, ..seen(Some(&target)) };
            assert_eq!(verdict(&s, &out, 100), Verdict::Hold, "not during the cast");
            assert_eq!(verdict(&s, &out, 126), Verdict::Hold);
            assert_eq!(verdict(&s, &out, 127), Verdict::Cancel("out_of_range"));
            assert_eq!(verdict(&s, &Seen { short: true, ..out }, 127), Verdict::Cancel("out_of_range"), "before the cost");
            assert_eq!(verdict(&s, &Seen { flying: true, ..out }, 127), Verdict::Hold, "the previous arrow first");
            assert_eq!(verdict(&s, &Seen { writing: true, held: false, ..seen(Some(&target)) }, 127),
                if spend { Verdict::Hold } else { Verdict::Cancel("out_of_range") });
            // Back within the hold before its release tick, it leaves.
            assert_eq!(verdict(&s, &seen(Some(&target)), 127), Verdict::Release);
            // Released: the verdict lands it; the hold is the landing's check.
            let mut r = s.clone();
            release(&mut r, 6., 127);
            assert_eq!(verdict(&r, &Seen { held: false, ..seen(Some(&target)) }, 133), Verdict::Land);
        }
        // Without a flight the landing is the release and the effecting at
        // once (gameplay::landing checks the hold).
        assert_eq!(verdict(&shot(), &Seen { held: false, ..seen(Some(&target)) }, 127), Verdict::Land);
    }
    #[test]
    fn clear_drops_only_this_casts_strike_fields() {
        let s = shot();
        let mut e = wire::Entity {
            strike_tick: 100,
            strike_sequence: 9,
            strike_target: 77,
            strike_result: "casting".into(),
            strike_style: 6,
            ..Default::default()
        };
        clear(&mut e, s.started);
        assert_eq!((e.strike_tick, e.strike_sequence, e.strike_target, e.strike_result.as_str()), (0, 0, 0, ""));
        // A newer strike (not this cast's) is left alone.
        let mut later = wire::Entity { strike_tick: 130, strike_sequence: 10, ..Default::default() };
        clear(&mut later, s.started);
        assert_eq!((later.strike_tick, later.strike_sequence), (130, 10));
        // PQ-439 (D-223): the release marks only this cast, and a newer
        // cast's fields survive an older arrow's landing.
        let mut cast = wire::Entity { strike_tick: 100, strike_sequence: 9, strike_result: "casting".into(), ..Default::default() };
        released(&mut cast, 100);
        assert_eq!((cast.strike_tick, cast.strike_sequence, cast.strike_result.as_str()), (100, 9, "released"));
        released(&mut later, 100);
        assert_eq!(later.strike_result, "");
        // A released cast refused at its arrival (no_ammo, equipment_changed,
        // stale_target) or cancelled in flight keeps its strike fields.
        clear(&mut cast, 100);
        assert_eq!((cast.strike_tick, cast.strike_sequence, cast.strike_result.as_str()), (100, 9, "released"));
        let mut newer = wire::Entity { strike_tick: 130, strike_target: 77, strike_result: "casting".into(), strike_style: 6, strike_sequence: 10, ..Default::default() };
        let kept = Strike::of(&newer);
        (newer.strike_tick, newer.strike_result, newer.strike_damage, newer.strike_sequence) = (133, "hit".into(), 40, 9);
        kept.clone().put(&mut newer);
        assert_eq!(Strike::of(&newer), kept);
    }
}
