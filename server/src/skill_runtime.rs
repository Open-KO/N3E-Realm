//! Simulation-owned casts; database work is polled only after completion.
use crate::{
    accounts::{Database, Owner},
    content::Result,
    damage::{Outcome, Rolls},
    gameplay::Npc,
    presentation::Events,
    simulation::{deliver, Command, CommittedHit, Player},
    skills::{Policy, Skill},
    wire::{self, envelope::Body, Envelope},
};
use std::{collections::BTreeMap, sync::Arc};
struct Cast {
    action: wire::Action,
    skill: Skill,
    entity: u64,
    life: i64,
    generation: i64,
    origin: [f32; 3],
    stage: u32,
    /// PQ-455 (D-231): the cast time ended and the cast still stood (1298's
    /// release); from then on a move or a hit no longer cancels it.
    released: bool,
    started: u64,
    end: u64,
    hit: u64,
    deadline: u64,
    job: Option<tokio::task::JoinHandle<Result<crate::skills::Gate>>>,
}

#[cfg(test)]
pub(crate) fn test_cancelled_commit(
    rt: &tokio::runtime::Runtime,
    db: &Database,
    owner: &Arc<Owner>,
    selected: &crate::accounts::Selected,
    skill: &Skill,
) -> Result<()> {
    // Each mode refuses (or lands) a released cast while its recast commit
    // waits on PostgreSQL. PQ-472 (D-236): `range` (out_of_range from the
    // hold) is a refusal Ebenezer answers before its reuse window, so the
    // commit is undone; `death` (actor_dead) is one it drops with no answer,
    // 1298 keeping its own recast, and `leave` and `timeout` are n3e's own,
    // so all three keep it; `move` lands (PQ-455); `npc` (a damage skill
    // whose NPC target dies after the release, target_dead) is refused by
    // Ebenezer's admission with a packet, so it is undone too.
    for mode in ["leave", "move", "death", "range", "timeout", "npc"] {
        let mut p = crate::simulation::test_player();
        p.s = selected.clone();
        p.s.entity.id = 44;
        p.s.entity.health = 40;
        p.s.entity.resource = 10;
        let mut replies = p.test_output();
        let mut skill = skill.clone();
        skill.id.push_str(&format!("/cancelled-{mode}"));
        skill.target = if mode == "npc" { 2 } else { 1 };
        p.inventory.level = skill.level as u64;
        // `range` heals a second player 10 m away (range 25).
        let mut friend = crate::simulation::test_player();
        friend.s.id = selected.id + 1;
        friend.s.entity.id = 45;
        friend.s.entity.health = 30;
        friend.s.entity.x = 10.;
        // `npc` strikes the legacy demo's NPC at the origin (range 25).
        let mut npcs = Vec::new();
        if mode == "npc" {
            let rules = crate::rules::Rules::load(std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"), "demo")?;
            let ground = crate::movement::Collision::soup(vec![[-4., 0., -4.], [4., 0., -4.], [4., 0., 4.], [-4., 0., -4.], [4., 0., 4.], [-4., 0., 4.]])?;
            npcs.push(Npc::new(&rules, &ground, 90));
        }
        let target = match mode {
            "range" => 45,
            "npc" => 90,
            _ => 44,
        };
        let mut c = crate::persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
        let mut blocker = crate::persistence::connect(&std::env::var("N3E_TEST_DATABASE_URL")?)?;
        let pid: i32 = blocker.query_one("SELECT pg_backend_pid()", &[])?.get(0);
        let mut lock = blocker.transaction()?;
        lock.query_one(
            "SELECT realm FROM realm_fence WHERE realm=$1 FOR UPDATE",
            &[&owner.realm],
        )?;
        let mut runtime = Runtime::default();
        runtime.casts.insert(
            p.s.id,
            Cast {
                action: wire::Action {
                    session: p.s.generation as u64,
                    seq: 1,
                    target,
                    action: skill.id.clone(),
                    ..Default::default()
                },
                skill: skill.clone(),
                entity: 44,
                life: p.s.life_revision,
                generation: p.s.generation,
                origin: [0.; 3],
                stage: 2,
                released: true,
                started: 1,
                end: 2,
                hit: 0,
                deadline: if mode == "timeout" { 2 } else { 100 },
                job: Some(rt.spawn(crate::skills::gate(
                    db.clone(),
                    owner.clone(),
                    p.s.clone(),
                    skill.clone(),
                    true,
                ))),
            },
        );
        let start = std::time::Instant::now();
        loop {
            let waiting:bool=c.query_one("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE $1=ANY(pg_blocking_pids(pid)))",&[&pid])?.get(0);
            if waiting {
                break;
            }
            assert!(
                start.elapsed().as_millis() < 500,
                "skill gate did not reach database fence"
            );
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        let mut events = Events::default();
        let policy = Policy {
            archetype: skill.class.clone(),
            label: "Audit".into(),
            reach: Default::default(),
            radii: 0.,
            skills: vec![skill.clone()],
        };
        match mode {
            "leave" => rt.block_on(async {
                runtime.cancel(p.s.id, &mut p, 3, &mut events, "interrupted", db, owner);
            }),
            // PQ-455 (D-231): a move after the release no longer cancels the
            // cast; it lands once its recast commit returns.
            "move" => p.s.entity.x = 0.1,
            "death" => p.s.entity.health = 0,
            // The target leaves the hold after the release.
            "range" => friend.s.entity.x = 40.,
            // Another player's hit killed it after the release.
            "npc" => npcs[0].entity.health = 0,
            _ => {}
        }
        let id = p.s.id;
        let mut players = BTreeMap::from([(id, p), (friend.s.id, friend)]);
        struct Roll;
        impl Rolls for Roll {
            fn roll(&mut self, _: u32) -> u32 {
                0
            }
        }
        let mut tick = |runtime: &mut Runtime, players: &mut BTreeMap<i64, Player>, npcs: &mut Vec<Npc>, at: u64| {
            rt.block_on(runtime.tick(
                players,
                npcs,
                &policy,
                at,
                db,
                owner,
                &mut events,
                &mut Roll,
                1,
                &mut Default::default(),
            ))
        };
        if mode != "leave" {
            tick(&mut runtime, &mut players, &mut npcs, 3);
        }
        lock.commit()?;
        for _ in 0..100 {
            tick(&mut runtime, &mut players, &mut npcs, 4);
            if !runtime.busy(id) && !runtime.recovery.contains_key(&id) {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        assert!(!runtime.busy(id) && !runtime.recovery.contains_key(&id), "{mode}: the cast and its recovery ended");
        let undone = matches!(mode, "range" | "npc");
        let durable: bool = c.query_one("SELECT EXISTS(SELECT 1 FROM character_skill_cooldowns WHERE character_id=$1 AND skill=$2 AND ready_at>clock_timestamp())",&[&id,&skill.id])?.get(0);
        assert_eq!(durable, !undone, "{mode}: the durable deadline");
        // The commit itself ran: an undone deadline was written, then deleted.
        let written: bool = c.query_one("SELECT EXISTS(SELECT 1 FROM character_skill_cooldowns WHERE character_id=$1 AND skill=$2)", &[&id, &skill.id])?.get(0);
        assert_eq!(written, !undone, "{mode}: an undone deadline leaves no row");
        assert_eq!(
            runtime.view(id, 4).len(),
            usize::from(!undone),
            "{mode}: the live cooldown follows the durable one without another cast/reconnect"
        );
        // PQ-455 (D-231): the moved caster's heal lands (its cost taken; no
        // stats, so its health stays at its maximum); the others drain with
        // nothing applied or spent.
        assert_eq!(
            (players[&id].s.entity.health, players[&id].s.entity.resource),
            match mode {
                "death" => (0, 10),
                "move" => (40, 10 - skill.cost),
                _ => (40, 10),
            }
        );
        assert_eq!(players[&(selected.id + 1)].s.entity.health, 30, "{mode}: the friend was not healed");
        let status = match mode {
            "death" => "actor_dead",
            "move" => "healed",
            "range" => "out_of_range",
            "npc" => "target_dead",
            "timeout" => "cast_timeout",
            _ => "interrupted",
        };
        let reply = replies.try_recv()?;
        assert!(
            matches!(&reply.body,Some(Body::ActionResult(v)) if v.status==status),
            "{mode}: {reply:?}"
        );
        assert!(replies.try_recv().is_err());
        // The same skill again at once: refused `cooldown` by the live
        // deadline where the commit was kept, accepted where it was undone
        // (its gate reads the durable deadline gone and it starts casting).
        if mode != "death" {
            let p = players.get_mut(&id).unwrap();
            let again = wire::Action { session: p.s.generation as u64, seq: 2, target, action: skill.id.clone(), ..Default::default() };
            if mode == "range" {
                players.get_mut(&(selected.id + 1)).unwrap().s.entity.x = 10.;
            }
            if mode == "npc" {
                // It respawned at full health under the same id.
                npcs[0].entity.health = 10;
            }
            let target = players
                .values()
                .map(|q| &q.s.entity)
                .chain(npcs.iter().map(|n| &n.entity))
                .find(|e| e.id == target)
                .cloned();
            let p = players.get_mut(&id).unwrap();
            let _runtime = rt.enter();
            runtime.begin(p, p.s.generation, again, &policy, target.as_ref(), 5, db, owner);
            let expect = if undone { "cast_pending" } else { "cooldown" };
            let reply = replies.try_recv()?;
            assert!(matches!(&reply.body,Some(Body::ActionResult(v)) if v.status==expect), "{mode}: {reply:?}");
            if undone {
                for _ in 0..100 {
                    tick(&mut runtime, &mut players, &mut npcs, 6);
                    if runtime.casts.get(&id).is_some_and(|c| c.stage == 1) {
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(5));
                }
                let reply = replies.try_recv()?;
                assert!(matches!(&reply.body,Some(Body::ActionResult(v)) if v.status=="casting"), "{mode}: {reply:?}");
                let p = players.get_mut(&id).unwrap();
                runtime.cancel(id, p, 7, &mut events, "interrupted", db, owner);
            }
        }
        match mode {
            "move" => println!("PASS move while recast commit waits on PostgreSQL: the released cast lands with its cost, live cooldown (PQ-455)"),
            "range" | "npc" => println!("PASS {mode} while recast commit waits on PostgreSQL: no effect/cost, the committed deadline undone durably and live, castable again (PQ-472)"),
            _ => println!("PASS {mode} while recast commit waits on PostgreSQL: no effect/cost, live cooldown reconciled, the commit kept (PQ-472)"),
        }
    }
    Ok(())
}
#[derive(Default)]
pub struct Runtime {
    casts: BTreeMap<i64, Cast>,
    cooldowns: BTreeMap<(i64, String), u64>,
    recovery: BTreeMap<i64, tokio::task::JoinHandle<Result<Vec<(String, u32)>>>>,
}
fn reply(p: &mut Player, a: &wire::Action, status: &str) {
    deliver(
        p,
        Envelope {
            body: Some(Body::ActionResult(wire::ActionResult {
                seq: a.seq,
                target: a.target,
                status: status.into(),
                damage: 0,
            })),
        },
    );
}
fn clear(p: &mut Player) {
    p.s.entity.cast_skill.clear();
    p.s.entity.cast_start = 0;
    p.s.entity.cast_end = 0;
    p.s.entity.cast_target = 0;
}
fn event(
    events: &mut Events,
    tick: u64,
    p: &wire::Entity,
    target: &wire::Entity,
    kind: u32,
    key: &str,
) {
    events.push(wire::PresentationEvent {
        tick,
        actor: p.id,
        target: target.id,
        kind,
        key: key.into(),
        x: p.x,
        y: p.y,
        z: p.z,
        target_x: target.x,
        target_y: target.y,
        target_z: target.z,
        ..Default::default()
    });
}
/// PQ-472 (D-236): whether refusing a released cast with `status` (on an NPC
/// target when `npc`) undoes its recast commit. Ebenezer's magic packet
/// `004630a6` makes every requirement refusal of an effecting before its
/// reuse window `0046dbe2` (`004637e4`), so none starts the window; what
/// differs is whether it answers, since 1298 drops its own recast only on a
/// phase-4 packet (`00586fa0`, `005870b2`-`00587126`) and otherwise keeps it
/// and refuses its own recast until it runs out (`00581c45`-`00581c80`).
/// Undone, answered with a packet: the range (`004c1dbe` at `004635c8`, -103
/// through `0046e707`) and the admission `00464b43` (`004637b0`, phase 4
/// from `00464c1b`): an NPC target in state 0 (`00464d78`), the MP
/// (`004654ba`/`004654c9`), the level and class (`004653e2`-`00465450`), and
/// n3e's target-category check, whose nearest counterpart is that
/// admission's Moral test (an inference). PQ-480 (D-244): the weapon is no
/// longer tested after the acceptance (1298 tests it only at its skill
/// start, `0057f7f0` from `005829e2`), so `weapon_required` cannot refuse a
/// released cast and is no longer named here. Kept, dropped with
/// no packet, where n3e's server stands in for 1298's client gate: a dead
/// caster (`004635a1`, `004635b4`), a dead player target (`0046e8ef`,
/// `0046e94e`, a row with Moral at most 4 such as a heal) and a target that
/// is gone (`0046e942`, `0046eaae`). Every other refusal keeps the commit
/// (D-099): n3e's own session, timeout, database and NPC-write refusals,
/// and any status not named here.
fn undoes(status: &str, npc: bool) -> bool {
    match status {
        "out_of_range" | "insufficient_resource" | "wrong_class" | "level_required" | "invalid_target" => true,
        "target_dead" => npc,
        _ => false,
    }
}
impl Runtime {
    fn cancel_gate(&mut self, c: &mut Cast, p: &Player, db: &Database, owner: &Arc<Owner>, undo: bool) {
        let Some(job) = c.job.take() else {
            return;
        };
        if c.stage != 2 {
            job.abort();
            return;
        }
        // Cancelling the async receiver cannot roll back a transaction already
        // queued on the database worker. Drain it, then recover its durable
        // recast result without ever applying the interrupted spell. PQ-472
        // (D-236): when the refusal undoes the commit (`undoes`) and the
        // commit wrote a deadline, the recovery first deletes exactly that
        // deadline, in the same fenced transaction. A new cast is refused
        // `combat_pending` until the recovery has returned, and a failed
        // commit, undo or recovery leaves the deadline as written.
        let (db, owner, selected, skill) = (db.clone(), owner.clone(), p.s.clone(), c.skill.id.clone());
        self.recovery.insert(
            p.s.id,
            tokio::spawn(async move {
                match job.await {
                    Ok(Ok(crate::skills::Gate { remaining: 0, stamp: Some(stamp) })) if undo => {
                        crate::skills::recover_undoing(db, owner, selected, skill, stamp).await
                    }
                    _ => crate::skills::recover(db, owner, selected).await,
                }
            }),
        );
    }
    pub fn join(
        &mut self,
        selected: &crate::accounts::Selected,
        db: &Database,
        owner: &Arc<Owner>,
    ) {
        if let Some(job) = self.recovery.remove(&selected.id) {
            job.abort();
        }
        self.cooldowns.retain(|(id, _), _| *id != selected.id);
        self.recovery.insert(
            selected.id,
            tokio::spawn(crate::skills::recover(
                db.clone(),
                owner.clone(),
                selected.clone(),
            )),
        );
    }
    pub fn busy(&self, id: i64) -> bool {
        self.casts.contains_key(&id)
    }
    pub fn view(&self, id: i64, tick: u64) -> Vec<wire::SkillCooldown> {
        self.cooldowns
            .iter()
            .filter(|((actor, _), ready)| *actor == id && **ready > tick)
            .map(|((_, skill), ready)| wire::SkillCooldown {
                skill: skill.clone(),
                ready_tick: *ready,
            })
            .collect()
    }
    pub fn begin(
        &mut self,
        p: &mut Player,
        g: i64,
        a: wire::Action,
        policy: &Policy,
        target: Option<&wire::Entity>,
        tick: u64,
        db: &Database,
        owner: &Arc<Owner>,
    ) {
        let skill = policy.get(&a.action).unwrap();
        let status = if p.s.generation != g || a.session != g as u64 {
            "stale_session"
        } else if a.seq == 0 || a.seq <= p.last_action || a.seq >= i64::MAX as u64 {
            "stale_action"
        } else {
            p.last_action = a.seq;
            if self.recovery.contains_key(&p.s.id) || self.busy(p.s.id) || p.skill_busy() {
                "combat_pending"
            } else if tick
                < *self
                    .cooldowns
                    .get(&(p.s.id, skill.id.clone()))
                    .unwrap_or(&0)
            {
                "cooldown"
            } else if let Some(target) = target {
                // PQ-465 (D-232): the acceptance checks 1298's client start
                // limit and Ebenezer's hold.
                policy
                    .validate(
                        skill,
                        crate::skills::Range::Start,
                        p.inventory.level as u32,
                        &p.s.entity,
                        target,
                        p.bag.as_ref(),
                    )
                    .err()
                    .unwrap_or("ready")
            } else {
                "stale_target"
            }
        };
        if status != "ready" {
            reply(p, &a, status);
            return;
        }
        p.rest.motion(&mut p.s.entity, tick);
        // A cast drops both queued movements (D-207).
        p.moves.clear();
        let job = tokio::spawn(crate::skills::gate(
            db.clone(),
            owner.clone(),
            p.s.clone(),
            skill.clone(),
            false,
        ));
        self.casts.insert(
            p.s.id,
            Cast {
                action: a.clone(),
                skill: skill.clone(),
                entity: p.s.entity.id,
                life: p.s.life_revision,
                generation: g,
                origin: [p.s.entity.x, p.s.entity.y, p.s.entity.z],
                stage: 0,
                released: false,
                started: tick,
                end: 0,
                hit: p.skill_hit,
                deadline: tick + 100,
                job: Some(job),
            },
        );
        reply(p, &a, "cast_pending");
    }
    pub fn cancel(
        &mut self,
        id: i64,
        p: &mut Player,
        tick: u64,
        events: &mut Events,
        status: &str,
        db: &Database,
        owner: &Arc<Owner>,
    ) {
        if let Some(job) = self.recovery.remove(&id) {
            job.abort();
        }
        if let Some(mut c) = self.casts.remove(&id) {
            // A leave keeps the commit (D-236): the session's own refusal.
            self.cancel_gate(&mut c, p, db, owner, false);
            clear(p);
            event(events, tick, &p.s.entity, &p.s.entity, 5, &c.skill.id);
            reply(p, &c.action, status);
        }
    }
    pub async fn tick(
        &mut self,
        players: &mut BTreeMap<i64, Player>,
        npcs: &mut [Npc],
        policy: &Policy,
        tick: u64,
        db: &Database,
        owner: &Arc<Owner>,
        events: &mut Events,
        rng: &mut impl Rolls,
        capacity: usize,
        ids: &mut std::collections::VecDeque<u64>,
    ) -> Vec<Command> {
        self.cooldowns.retain(|_, ready| *ready > tick);
        let finished: Vec<_> = self
            .recovery
            .iter()
            .filter(|(_, j)| j.is_finished())
            .map(|(id, _)| *id)
            .collect();
        for id in finished {
            match self.recovery.remove(&id).unwrap().await {
                Ok(Ok(rows)) => {
                    for (skill, remaining) in rows {
                        if policy.get(&skill).is_some() {
                            self.cooldowns.insert((id, skill), tick + remaining as u64);
                        }
                    }
                }
                _ => {
                    if let Some(p) = players.get_mut(&id) {
                        p.failed = true;
                    }
                }
            }
        }
        let mut commands = Vec::new();
        let actors: Vec<_> = self.casts.keys().copied().collect();
        for id in actors {
            let mut c = self.casts.remove(&id).unwrap();
            // PQ-184: a player target only while the caster may see it.
            let target = crate::simulation::action_target(npcs, players, id, c.action.target);
            let Some(p) = players.get_mut(&id) else {
                if let Some(j) = c.job {
                    j.abort();
                }
                continue;
            };
            // PQ-455 (D-231): the cast ends at its release, the tick its cast
            // time ended while it still stood (`released`). Before it a move
            // cancels the cast and a hit rolls its interruption; after it
            // neither does, whether the impact still waits for the stage-2
            // transition (a pending combat write), the recast commit or the
            // caster's own writes (D-227). 1298's cast tick 00585830 fails
            // the recorded cast +0xb04 on a move (+0x308, the move state in
            // the source's names, 005858e9) only while it is set, and the release 00584b00 clears it (00584b40); the
            // received attack 005cec10 rolls only on that record (005ced75).
            let moved = !c.released
                && (p.moves.moving()
                    || [p.s.entity.x, p.s.entity.y, p.s.entity.z]
                        .iter()
                        .zip(c.origin)
                        .any(|(a, b)| (*a - b).abs() > 0.01));
            let interrupted = if p.skill_hit != c.hit {
                c.hit = p.skill_hit;
                !c.released && rng.roll(100) >= c.skill.survival
            } else {
                false
            };
            let invalid = if p.failed
                || p.s.generation != c.generation
                || p.s.entity.id != c.entity
                || p.s.life_revision != c.life
            {
                "stale_session"
            } else if moved || interrupted {
                "interrupted"
            } else if tick > c.deadline {
                "cast_timeout"
            } else if let Some(t) = &target {
                // PQ-465 (D-232): between the acceptance and the release the
                // range is not checked: Ebenezer's magic packet checks it
                // (004c1dbe at 004635c8) only when a phase arrives, the
                // casting at the start and the effecting, which 1298 sends at
                // the release (00584b00), and 1298's cast tick 00585830 does
                // not call its range check 00583780. From the release to the
                // impact the hold is checked (the package's margin, Moradon's
                // Range + 15 on the ground plane, 004c1f91-004c1fbf) from
                // where the cast was released (its origin, D-231: a move
                // before it cancels the cast) to the target's current
                // position; a cast on the caster passes (004c1f73). That
                // Ebenezer's caster position at the effecting is the release
                // position is an inference (D-231): its move handler 00494beb
                // writes that position (004950a9-0049511a), and whether a
                // move packet can be handled between the release and the
                // effecting was not read. PQ-480 (D-244): the weapon is not
                // tested here (only at the acceptance, `Range::Start`), as
                // 1298 tests its need item only at its skill start.
                let at_release;
                let (actor, range) = if c.released {
                    let mut at = p.s.entity.clone();
                    [at.x, at.y, at.z] = c.origin;
                    at_release = at;
                    (&at_release, crate::skills::Range::Hold)
                } else {
                    (&p.s.entity, crate::skills::Range::Unchecked)
                };
                policy
                    .validate(
                        &c.skill,
                        range,
                        p.inventory.level as u32,
                        actor,
                        t,
                        p.bag.as_ref(),
                    )
                    .err()
                    .unwrap_or("")
            } else {
                "stale_target"
            };
            if !invalid.is_empty() {
                clear(p);
                let npc = target.as_ref().is_some_and(|t| t.npc);
                self.cancel_gate(&mut c, p, db, owner, undoes(invalid, npc));
                event(events, tick, &p.s.entity, &p.s.entity, 5, &c.skill.id);
                reply(p, &c.action, invalid);
                continue;
            }
            // PQ-447 (D-227): the impact waits (until its deadline) for the
            // caster's own arrival write or reward (`Player::impact_waits`),
            // such as an arrow's arrival that began after the recast commit
            // started; an incoming hit's write does not hold it.
            if c.stage == 2 && p.impact_waits() {
                self.casts.insert(id, c);
                continue;
            }
            if c.job.as_ref().is_some_and(|j| j.is_finished()) {
                let remaining = match c.job.take().unwrap().await {
                    Ok(Ok(gate)) => gate.remaining,
                    _ => {
                        clear(p);
                        event(events, tick, &p.s.entity, &p.s.entity, 5, &c.skill.id);
                        reply(p, &c.action, "skill_unavailable");
                        continue;
                    }
                };
                if remaining > 0 {
                    self.cooldowns
                        .insert((id, c.skill.id.clone()), tick + remaining as u64);
                    clear(p);
                    event(events, tick, &p.s.entity, &p.s.entity, 5, &c.skill.id);
                    reply(p, &c.action, "cooldown");
                    continue;
                }
                if c.stage == 0 {
                    c.stage = 1;
                    c.started = tick;
                    c.end = tick + c.skill.cast_ms.div_ceil(50) as u64;
                    c.deadline = c.end + 100;
                    p.s.entity.cast_skill = c.skill.id.clone();
                    p.s.entity.cast_start = tick;
                    p.s.entity.cast_end = c.end;
                    p.s.entity.cast_target = c.action.target;
                    event(events, tick, &p.s.entity, &p.s.entity, 3, &c.skill.id);
                    reply(p, &c.action, "casting");
                } else {
                    clear(p);
                    let target = target.unwrap();
                    if c.skill.cooldown_ms > 0 {
                        self.cooldowns.insert(
                            (id, c.skill.id.clone()),
                            tick + c.skill.cooldown_ms.div_ceil(50) as u64,
                        );
                    }
                    if c.skill.target == 1 {
                        p.s.entity.resource -= c.skill.cost;
                        let actor = p.s.entity.clone();
                        reply(p, &c.action, "healed");
                        if let Some(t) = players
                            .values_mut()
                            .find(|p| p.s.entity.id == target.id && !p.failed)
                        {
                            let max = t.stats.as_ref().map_or(t.s.entity.health, |s| s.max_health);
                            t.s.entity.health =
                                t.s.entity.health.saturating_add(c.skill.amount).min(max);
                        }
                        event(events, tick, &actor, &target, 4, &c.skill.id);
                    } else {
                        let npc = npcs.iter_mut().find(|n| n.entity.id == target.id).unwrap();
                        let admission = if npc.pending.is_some() {
                            Err("target_pending")
                        } else {
                            npc.ledger
                                .admission(id, capacity + commands.len(), ids.len())
                        };
                        if let Err(reason) = admission {
                            reply(p, &c.action, reason);
                            event(events, tick, &p.s.entity, &p.s.entity, 5, &c.skill.id);
                            continue;
                        }
                        let damage = c.skill.damage(
                            p.stats.as_ref().map_or(&[], |s| s.attributes.as_slice()),
                            rng,
                        );
                        p.s.entity.resource -= c.skill.cost;
                        npc.pending = Some(id);
                        let claim = ids.pop_front().unwrap();
                        commands.push(Command::Action(
                            id,
                            c.generation,
                            c.action,
                            Some(CommittedHit {
                                skill: Some(c.skill.id),
                                style: 0,
                                interval: 0,
                                moving: false,
                                started: tick,
                                outcome: Outcome { hit: true, damage },
                                claim,
                                cast: None,
                                paid: false,
                            }),
                        ));
                    }
                    continue;
                }
            }
            if c.stage == 1 && tick >= c.end {
                // PQ-455 (D-231): released, though the recast commit may still
                // wait for a pending combat write.
                c.released = true;
            }
            if c.stage == 1 && tick >= c.end && !p.combat_pending() {
                c.stage = 2;
                c.job = Some(tokio::spawn(crate::skills::gate(
                    db.clone(),
                    owner.clone(),
                    p.s.clone(),
                    c.skill.clone(),
                    true,
                )));
            }
            self.casts.insert(id, c);
        }
        commands
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::accounts::Owner;

    fn heal() -> Skill {
        Skill {
            id: "demo:skill/heal".into(),
            label: "Heal".into(),
            class: "demo:class/test".into(),
            level: 1,
            cost: 5,
            cast_ms: 1500,
            cooldown_ms: 2000,
            target: 1,
            amount: 15,
            survival: 80,
            attribute: 4,
            resistance: 0,
            animation: 0,
            range: 25.,
            weapons: vec![],
        }
    }
    fn shot(released: bool) -> crate::ranged_shot::Shot {
        crate::ranged_shot::Shot {
            action: wire::Action { seq: 1, target: 77, ..Default::default() },
            generation: 1,
            entity: 44,
            life: 0,
            npc: 77,
            style: 2,
            started: 1,
            land: 20,
            lead: 0,
            moved: false,
            landing: false,
            speed: 4.,
            released,
            arrive: 50,
            spend: true,
            releasing: false,
        }
    }
    /// Every interruption roll fails the heal's survival (80): a hit that is
    /// rolled at all interrupts the cast.
    struct Roll;
    impl Rolls for Roll {
        fn roll(&mut self, _: u32) -> u32 {
            99
        }
    }
    fn statuses(out: &mut tokio::sync::mpsc::Receiver<Envelope>) -> Vec<String> {
        let mut seen = vec![];
        while let Ok(e) = out.try_recv() {
            if let Some(Body::ActionResult(r)) = e.body {
                seen.push(r.status);
            }
        }
        seen
    }
    fn action(seq: u64) -> wire::Action {
        wire::Action { session: 1, seq, target: 44, action: "demo:skill/heal".into(), ..Default::default() }
    }
    const HEAL: &str = "demo:skill/heal";
    struct Fixture {
        db: Database,
        owner: Arc<Owner>,
        policy: Policy,
        me: wire::Entity,
        out: tokio::sync::mpsc::Receiver<Envelope>,
        players: BTreeMap<i64, Player>,
        runtime: Runtime,
    }
    impl Fixture {
        fn new() -> Self {
            let mut p = crate::simulation::test_player();
            p.s.entity.id = 44;
            p.s.entity.resource = 20;
            p.inventory.level = 1;
            let out = p.test_output();
            Fixture {
                db: Database::test_unavailable(),
                owner: Arc::new(Owner { realm: "test".into(), owner: "test".into(), generation: 1 }),
                policy: Policy {
                    archetype: "demo:class/test".into(),
                    label: "Test".into(),
                    reach: Default::default(),
                    radii: 0.,
                    skills: vec![heal()],
                },
                me: p.s.entity.clone(),
                out,
                players: BTreeMap::from([(1, p)]),
                runtime: Runtime::default(),
            }
        }
        fn p(&mut self) -> &mut Player {
            self.players.get_mut(&1).unwrap()
        }
        fn begin(&mut self, seq: u64, tick: u64) {
            let p = self.players.get_mut(&1).unwrap();
            self.runtime.begin(p, 1, action(seq), &self.policy, Some(&self.me), tick, &self.db, &self.owner);
        }
        /// The cast reaches its impact stage: its cast time ended at `end`
        /// and its recast commit is done (stage 2).
        async fn at_impact(&mut self, end: u64) {
            let committed = tokio::spawn(async { Ok(crate::skills::Gate { remaining: 0, stamp: Some(1) }) });
            while !committed.is_finished() {
                tokio::task::yield_now().await;
            }
            let c = self.runtime.casts.get_mut(&1).unwrap();
            if let Some(job) = c.job.replace(committed) {
                job.abort();
            }
            (c.stage, c.released, c.end, c.deadline) = (2, true, end, end + 100);
        }
        /// The cast's gate returned: it is casting (stage 1) until `end`.
        fn casting(&mut self, end: u64) {
            let c = self.runtime.casts.get_mut(&1).unwrap();
            if let Some(job) = c.job.take() {
                job.abort();
            }
            (c.stage, c.end, c.deadline) = (1, end, end + 100);
        }
        async fn tick(&mut self, tick: u64) {
            let mut events = Events::default();
            let impacts = self
                .runtime
                .tick(&mut self.players, &mut [], &self.policy, tick, &self.db, &self.owner, &mut events, &mut Roll, 0, &mut Default::default())
                .await;
            assert!(impacts.is_empty(), "a heal makes no strike");
        }
        /// An NPC hit on the caster commits: without a wear write (no wear
        /// policy, or a miss that wears nothing) `receive_hit` applies it at
        /// once through `finish_hit`, which counts it as a hit for the cast.
        fn hit(&mut self, tick: u64) {
            let mut rules = crate::rules::Rules::load(
                std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
                "demo",
            )
            .unwrap();
            rules.inventory = None;
            let mut npc = wire::Entity { id: 77, health: 50, ..Default::default() };
            let p = self.p();
            let health = p.s.entity.health;
            p.receive_hit(&mut npc, &rules, tick, crate::damage::Outcome { hit: true, damage: 1 });
            assert_eq!((p.skill_hit, p.s.entity.health), (tick, health - 1), "the hit committed");
        }
    }

    /// PQ-447 (D-227): a released arrow in flight refuses no skill (a held
    /// shot still does). An impact waits for the caster's own strike's wear
    /// write (an arrow's arrival that began after the recast commit) or its
    /// reward instead of taking its cost or landing first; an incoming hit's
    /// pending write does not hold it (attempt 2).
    #[test]
    fn a_flight_refuses_no_skill_and_an_impact_waits_for_the_casters_own_writes() {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        rt.block_on(async {
            let mut f = Fixture::new();
            // A held shot refuses the cast; once released, its arrow in
            // flight does not.
            f.p().shot = Some(shot(false));
            assert!(f.p().skill_busy());
            f.begin(1, 3);
            assert_eq!(statuses(&mut f.out), ["combat_pending"]);
            f.p().flight = f.p().shot.take().map(|_| shot(true));
            assert!(!f.p().skill_busy());
            f.begin(2, 3);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            assert!(f.runtime.busy(1));
            // The cast reaches its impact while the archer's own arrival
            // write, then its reward, is pending.
            f.at_impact(4).await;
            for (arrival, reward) in [(true, false), (false, true)] {
                f.p().test_pending(arrival, false, reward);
                for tick in 5..8 {
                    f.tick(tick).await;
                }
                assert!(f.runtime.busy(1), "the impact waits");
                assert_eq!(f.p().s.entity.resource, 20, "its cost is not taken while it waits");
                assert!(statuses(&mut f.out).is_empty());
            }
            // The write committed: the impact lands.
            f.p().test_pending(false, false, false);
            f.tick(8).await;
            assert!(!f.runtime.busy(1));
            assert_eq!(f.p().s.entity.resource, 15);
            assert_eq!(statuses(&mut f.out), ["healed"]);
            // The archer's own combat write still refuses a new cast, as
            // before (only the flight no longer does).
            f.p().test_pending(true, false, false);
            f.begin(3, 9);
            assert_eq!(statuses(&mut f.out), ["combat_pending"]);
            // An incoming hit's pending write does not hold an impact: it
            // touches only the caster's health. (It refuses a new cast, as
            // before, so the cast begins first.)
            f.p().test_pending(false, false, false);
            f.runtime.cooldowns.clear();
            f.begin(4, 10);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.at_impact(11).await;
            f.p().test_pending(false, true, false);
            f.tick(12).await;
            assert!(!f.runtime.busy(1), "an incoming hit's write does not hold the impact");
            assert_eq!(f.p().s.entity.resource, 10);
            assert_eq!(statuses(&mut f.out), ["healed"]);
        });
    }

    /// PQ-447 attempt 2 (D-227): a hit that commits while the impact waits
    /// (on the arrival's write or the reward) neither interrupts the cast nor
    /// spends its recast for nothing: the cast time ended (stage 2), as
    /// 1298's cast ends at its release. The same hit during the cast time
    /// still interrupts it, before any recast is committed.
    #[test]
    fn a_hit_while_the_impact_waits_does_not_interrupt_it() {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        rt.block_on(async {
            let mut f = Fixture::new();
            for (seq, arrival, reward) in [(1, true, false), (2, false, true)] {
                let t = seq * 20;
                f.runtime.cooldowns.clear();
                f.begin(seq, t);
                assert_eq!(statuses(&mut f.out), ["cast_pending"]);
                f.at_impact(t + 1).await;
                f.p().test_pending(arrival, false, reward);
                f.tick(t + 2).await;
                // A hit commits while the impact waits.
                f.hit(t + 3);
                f.tick(t + 3).await;
                f.tick(t + 4).await;
                assert!(f.runtime.busy(1), "the cast is not interrupted");
                assert!(f.runtime.recovery.is_empty(), "nor cancelled after its recast commit");
                assert!(statuses(&mut f.out).is_empty());
                // The wait ends: the impact lands for the recast it spent.
                f.p().test_pending(false, false, false);
                f.tick(t + 5).await;
                assert!(!f.runtime.busy(1));
                assert_eq!(statuses(&mut f.out), ["healed"]);
                assert!(f.runtime.cooldowns.contains_key(&(1, HEAL.to_string())));
            }
            assert_eq!(f.p().s.entity.resource, 10);
            // During the cast time (stage 1, before the recast commit) the
            // same hit interrupts the cast, and nothing durable is spent.
            f.runtime.cooldowns.clear();
            f.begin(3, 60);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(90);
            f.hit(61);
            f.tick(61).await;
            assert!(!f.runtime.busy(1));
            assert!(f.runtime.recovery.is_empty());
            assert_eq!(statuses(&mut f.out), ["interrupted"]);
            assert!(!f.runtime.cooldowns.contains_key(&(1, HEAL.to_string())));
            assert_eq!(f.p().s.entity.resource, 10);
        });
    }
    /// PQ-455 (D-231): the cast ends at its release, the tick its cast time
    /// ended while it stood, as 1298's cast tick (00585830) fails a cast on a
    /// move only before the release (00584b00) clears its record. Before it
    /// a move cancels the cast and a hit rolls; after it, also while the
    /// stage-2 transition waits for a pending combat write (the stage-1
    /// tail), neither does. The range is checked until the impact, from where
    /// the cast was released to the target; Ebenezer's magic packet checks
    /// the effecting's range from the caster's current server position
    /// (004c1dbe at 004635c8), inferred to be its release position; a cast on
    /// the caster passes.
    #[test]
    fn the_cast_ends_at_its_release() {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        rt.block_on(async {
            let mut f = Fixture::new();
            // A second player, the heal's target, 10 m away (range 25).
            let mut friend = crate::simulation::test_player();
            friend.s.id = 2;
            friend.s.entity.id = 45;
            friend.s.entity.health = 30;
            friend.s.entity.x = 10.;
            f.players.insert(2, friend);
            let heal = |seq| wire::Action { target: 45, ..action(seq) };
            // Before the release a move cancels the cast (PQ-465, D-232: the
            // target's range is not checked then; see
            // `the_range_is_the_start_limit_then_the_hold`).
            {
                let target = f.players[&2].s.entity.clone();
                let p = f.players.get_mut(&1).unwrap();
                f.runtime.begin(p, 1, heal(1), &f.policy, Some(&target), 20, &f.db, &f.owner);
            }
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(30);
            f.tick(21).await;
            assert!(f.runtime.busy(1));
            f.p().s.entity.x = 1.;
            f.tick(29).await;
            assert!(!f.runtime.busy(1));
            assert_eq!(statuses(&mut f.out), ["interrupted"]);
            f.p().s.entity.x = 0.;
            assert_eq!(f.p().s.entity.resource, 20, "nothing was spent");
            // The cast time ends while the caster's own arrival write is
            // pending: the cast is released though it stays at stage 1.
            {
                let target = f.players[&2].s.entity.clone();
                let p = f.players.get_mut(&1).unwrap();
                f.runtime.begin(p, 1, heal(3), &f.policy, Some(&target), 60, &f.db, &f.owner);
            }
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(70);
            f.p().test_pending(true, false, false);
            f.tick(70).await;
            let c = &f.runtime.casts[&1];
            assert_eq!((c.stage, c.released), (1, true), "released, its recast commit waiting");
            // Now a hit (rolled, it would interrupt: survival 80, roll 99)
            // and a move of the caster 40 m from the target cancel nothing:
            // the range is measured from where the cast was released.
            f.hit(71);
            f.p().s.entity.x = -30.;
            f.tick(71).await;
            f.tick(72).await;
            assert!(f.runtime.busy(1), "the released cast stands");
            assert!(statuses(&mut f.out).is_empty());
            // The write commits: the recast commit starts (stage 2), and the
            // cast lands once it returns.
            f.p().test_pending(false, false, false);
            f.tick(73).await;
            assert_eq!(f.runtime.casts[&1].stage, 2);
            f.at_impact(70).await;
            f.p().s.entity.z = 5.;
            f.tick(74).await;
            assert!(!f.runtime.busy(1));
            assert!(f.runtime.recovery.is_empty());
            assert_eq!(statuses(&mut f.out), ["healed"]);
            assert_eq!(f.p().s.entity.resource, 15);
            assert!(f.runtime.cooldowns.contains_key(&(1, HEAL.to_string())));
            // A heal on the caster itself, which moves 40 m after the
            // release, lands: the same id is in range.
            (f.p().s.entity.x, f.p().s.entity.z) = (0., 0.);
            f.runtime.cooldowns.clear();
            f.begin(4, 80);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(90);
            f.tick(90).await;
            assert!(f.runtime.casts[&1].released);
            f.p().s.entity.x = 40.;
            f.at_impact(90).await;
            f.tick(91).await;
            assert_eq!(statuses(&mut f.out), ["healed"]);
            assert_eq!(f.p().s.entity.resource, 10);
            // A target that leaves the range after the release fails the
            // impact, as Ebenezer's effecting does (its committed recast is
            // recovered; nothing applied or spent).
            f.p().s.entity.x = 0.;
            f.runtime.cooldowns.clear();
            {
                let target = f.players[&2].s.entity.clone();
                let p = f.players.get_mut(&1).unwrap();
                f.runtime.begin(p, 1, heal(5), &f.policy, Some(&target), 100, &f.db, &f.owner);
            }
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(110);
            f.tick(110).await;
            assert!(f.runtime.casts[&1].released);
            f.players.get_mut(&2).unwrap().s.entity.x = 40.;
            f.at_impact(110).await;
            f.tick(111).await;
            assert!(!f.runtime.busy(1));
            assert_eq!(statuses(&mut f.out), ["out_of_range"]);
            // PQ-472 (D-236): its commit is drained and undone in the
            // recovery (tests/skills_db.py runs it against PostgreSQL).
            assert!(!f.runtime.recovery.is_empty(), "its committed recast is undone and recovered");
            assert_eq!(f.p().s.entity.resource, 10);
        });
    }
    /// PQ-472 (D-236): which refusals of a released cast undo its recast
    /// commit: those Ebenezer answers with a phase-4 packet before its reuse
    /// window (1298 then drops its own recast). A refusal it drops with no
    /// packet (1298 keeps its recast), n3e's own refusals and any status not
    /// named keep the commit.
    #[test]
    fn which_refusals_undo_the_recast_commit() {
        for npc in [false, true] {
            for status in [
                "out_of_range",
                "insufficient_resource",
                "wrong_class",
                "level_required",
                "invalid_target",
            ] {
                assert!(undoes(status, npc), "{status} {npc}");
            }
            for status in [
                // PQ-480 (D-244): no longer raised after the acceptance.
                "weapon_required",
                "actor_dead",
                "stale_target",
                "stale_session",
                "interrupted",
                "cast_timeout",
                "skill_unavailable",
                "cooldown",
                "target_pending",
                "combat_pending",
                "settlement_capacity",
                "contributor_capacity",
                "",
                "unknown",
            ] {
                assert!(!undoes(status, npc), "{status} {npc}");
            }
        }
        // A dead NPC is refused by the admission (a packet); a dead player
        // target by the type-3 check, silently.
        assert!(undoes("target_dead", true));
        assert!(!undoes("target_dead", false));
        // Every refusal `Policy::validate` can return after the release (the
        // hold) is decided above; `weapon_required` only at the acceptance
        // (PQ-480, D-244).
        let p = Policy {
            archetype: "demo:class/test".into(),
            label: "Test".into(),
            reach: Default::default(),
            radii: 0.,
            skills: vec![heal()],
        };
        let actor = wire::Entity { id: 1, health: 10, resource: 20, ..Default::default() };
        let target = wire::Entity { id: 2, health: 10, ..Default::default() };
        let mut seen = std::collections::BTreeSet::new();
        for (class, level, a, t, weapon) in [
            ("other", 1, actor.clone(), target.clone(), false),
            ("demo:class/test", 0, actor.clone(), target.clone(), false),
            ("demo:class/test", 1, wire::Entity { health: 0, ..actor.clone() }, target.clone(), false),
            ("demo:class/test", 1, actor.clone(), wire::Entity { health: 0, ..target.clone() }, false),
            ("demo:class/test", 1, actor.clone(), wire::Entity { npc: true, ..target.clone() }, false),
            ("demo:class/test", 1, actor.clone(), wire::Entity { x: 30., ..target.clone() }, false),
            ("demo:class/test", 1, wire::Entity { resource: 1, ..actor.clone() }, target.clone(), false),
            ("demo:class/test", 1, actor.clone(), target.clone(), true),
        ] {
            let mut p = p.clone();
            p.archetype = class.into();
            if weapon {
                p.skills[0].weapons.push("demo:item/wand".into());
            }
            let held = p.validate(&p.skills[0], crate::skills::Range::Hold, level, &a, &t, None);
            if weapon {
                assert_eq!(held, Ok(()), "the hold does not test the weapon");
                assert_eq!(
                    p.validate(&p.skills[0], crate::skills::Range::Start, level, &a, &t, None),
                    Err("weapon_required")
                );
            } else {
                seen.insert(held.unwrap_err());
            }
        }
        assert_eq!(
            seen,
            [
                "actor_dead",
                "insufficient_resource",
                "invalid_target",
                "level_required",
                "out_of_range",
                "target_dead",
                "wrong_class"
            ]
            .into(),
        );
    }
    /// PQ-480 (D-244): the weapon is tested only at the acceptance. 1298
    /// tests a row's need-item kind only in `0057f7f0` (`0057fe54`), called
    /// by its skill start (`005829e2`) and not by its release `00584b00`;
    /// its item drop `0049f7c0` and Ebenezer's item move `004a1aa4` refuse
    /// no move while a cast runs, and Ebenezer's admission `00464b43` reads
    /// no hand slot. So a weapon unequipped during the cast time, or after
    /// the release, leaves the cast to land and take its cost; a press with
    /// no weapon is still refused `weapon_required`, before any database work.
    #[test]
    fn a_weapon_removed_after_the_acceptance_does_not_refuse_the_cast() {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        rt.block_on(async {
            let mut f = Fixture::new();
            f.policy.skills[0].weapons = vec!["demo:item/wand".into()];
            let armed = || wire::BagState {
                revision: 1,
                equipment: vec![wire::ItemStack { instance: 9, item: "demo:item/wand".into(), quantity: 1, durability: 1 }],
                ..Default::default()
            };
            // No weapon: refused at the acceptance, as 1298's skill start
            // refuses it (text 4005, D-243).
            f.p().bag = Some(wire::BagState { revision: 1, ..Default::default() });
            f.begin(1, 10);
            assert_eq!(statuses(&mut f.out), ["weapon_required"]);
            assert!(!f.runtime.busy(1));
            assert!(f.runtime.recovery.is_empty(), "no database work");
            // Unequipped during the cast time: the cast goes on and lands.
            f.p().bag = Some(armed());
            f.begin(2, 20);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(30);
            f.p().bag = Some(wire::BagState { revision: 2, ..Default::default() });
            for tick in 21..30 {
                f.tick(tick).await;
                assert!(f.runtime.busy(1), "tick {tick}: the cast stands");
            }
            assert!(statuses(&mut f.out).is_empty());
            f.at_impact(30).await;
            f.tick(31).await;
            assert!(!f.runtime.busy(1));
            assert_eq!(statuses(&mut f.out), ["healed"]);
            assert_eq!(f.p().s.entity.resource, 15, "its cost is taken");
            assert!(f.runtime.recovery.is_empty(), "nothing is undone");
            // Unequipped after the release: the impact lands.
            f.runtime.cooldowns.clear();
            f.p().bag = Some(armed());
            f.begin(3, 40);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.at_impact(50).await;
            f.p().bag = None;
            f.tick(51).await;
            assert!(!f.runtime.busy(1));
            assert_eq!(statuses(&mut f.out), ["healed"]);
            assert_eq!(f.p().s.entity.resource, 10);
            assert!(f.runtime.cooldowns.contains_key(&(1, HEAL.to_string())));
        });
    }
    /// PQ-473 (D-237): a press inside the cooldown is refused `cooldown`,
    /// starts no database work and leaves the deadline where the landed cast
    /// put it, however often it is repeated; the press at the deadline is
    /// accepted. Ebenezer's reuse window `0046dbe2` stores the time of a
    /// too-early effecting in the skill's slot (`0046dcab`), but n3e's
    /// refusal stands for 1298's local recast refusal (`00581c45`-`00581c80`),
    /// which sends nothing, and a release is at least (CastTime + ReCastTime)
    /// / 10 s of 50 ms ticks after the last release whose recast stands (not
    /// undone by D-236); an undone release was refused before Ebenezer's
    /// window, so it stamped no slot there either. Ebenezer's 15-slot cap
    /// (`0046dcfe`) is not modelled (PQ-475).
    #[test]
    fn a_press_inside_the_cooldown_leaves_the_deadline() {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        rt.block_on(async {
            let mut f = Fixture::new();
            f.begin(1, 10);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.at_impact(11).await;
            f.tick(12).await;
            assert_eq!(statuses(&mut f.out), ["healed"]);
            // The heal's 2000 ms are 40 ticks from its impact.
            let ready = 12 + 40;
            let key = (1, HEAL.to_string());
            assert_eq!(f.runtime.cooldowns.get(&key), Some(&ready));
            // A press on every tick of the cooldown, ticking between them.
            for (seq, tick) in (2..).zip(13..ready) {
                f.begin(seq, tick);
                assert_eq!(statuses(&mut f.out), ["cooldown"], "tick {tick}");
                assert!(!f.runtime.busy(1), "tick {tick}: no cast");
                assert!(f.runtime.recovery.is_empty(), "tick {tick}: no database work");
                assert_eq!(f.runtime.cooldowns.get(&key), Some(&ready), "tick {tick}: the deadline stays");
                f.tick(tick).await;
            }
            assert_eq!(f.p().s.entity.resource, 15, "a refused press costs nothing");
            // The press at the deadline is accepted.
            f.begin(100, ready);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            assert!(f.runtime.busy(1));
        });
    }
    /// PQ-475 (D-238): Ebenezer's reuse window `0046dbe2` keeps 15 slots per
    /// user and drops, with no packet, a skill in none of them while all 15
    /// are held by other skills inside the new skill's window (`0046dcfe`).
    /// n3e has no slot table: 16 skills cast one after another all land, the
    /// 16th while the other 15 are inside its window, and each of the 15 is
    /// still refused by its own deadline.
    #[test]
    fn sixteen_skills_inside_one_window_all_cast() {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        rt.block_on(async {
            let mut f = Fixture::new();
            let ids: Vec<String> = (0..16).map(|i| format!("demo:skill/heal-{i}")).collect();
            // A 60 s cooldown: every skill's window (cast + cooldown, 61.5 s)
            // covers all 16 casts, which take 80 ticks (4 s).
            f.policy.skills = ids
                .iter()
                .map(|id| Skill { id: id.clone(), cost: 0, cooldown_ms: 60_000, ..heal() })
                .collect();
            let press = |f: &mut Fixture, id: &str, seq: u64, tick: u64| {
                let p = f.players.get_mut(&1).unwrap();
                let a = wire::Action { action: id.to_string(), ..action(seq) };
                f.runtime.begin(p, 1, a, &f.policy, Some(&f.me), tick, &f.db, &f.owner);
            };
            let mut ready = vec![];
            for (i, id) in ids.iter().enumerate() {
                let tick = 10 + 5 * i as u64;
                press(&mut f, id, i as u64 + 1, tick);
                assert_eq!(statuses(&mut f.out), ["cast_pending"], "skill {i}");
                f.at_impact(tick + 1).await;
                f.tick(tick + 2).await;
                assert_eq!(statuses(&mut f.out), ["healed"], "skill {i}");
                // 60,000 ms are 1,200 ticks from the impact.
                ready.push(tick + 2 + 1200);
                let key = (1, id.clone());
                assert_eq!(f.runtime.cooldowns.get(&key), Some(&ready[i]), "skill {i}");
            }
            // The 16th landed while the other 15 were inside its window.
            assert!(ready[..15].iter().all(|&r| r > 10 + 5 * 15));
            assert_eq!(f.runtime.cooldowns.len(), 16);
            // Each skill is still paced by its own deadline.
            let after = 10 + 5 * 16;
            for (i, id) in ids.iter().enumerate() {
                press(&mut f, id, 100 + i as u64, after);
                assert_eq!(statuses(&mut f.out), ["cooldown"], "skill {i}");
                assert!(!f.runtime.busy(1), "skill {i}: no cast");
            }
            press(&mut f, &ids[0], 200, ready[0]);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
        });
    }
    /// PQ-465 (D-232), with Moradon's rule (range 25, start 2, hold 15 on the
    /// ground plane, 1 m radii): a cast is accepted within 29 m in 3-D (1298's
    /// client limit `00583780`, which the server enforces); the target's range
    /// is not checked until the release; from the release to the impact the
    /// target must stay below 40 m on the ground plane (Ebenezer's `004c1dbe`).
    #[test]
    fn the_range_is_the_start_limit_then_the_hold() {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        rt.block_on(async {
            let mut f = Fixture::new();
            f.policy.reach = crate::skills::Reach { start: 2., hold: 15., planar: true };
            f.policy.radii = 2.;
            let mut friend = crate::simulation::test_player();
            friend.s.id = 2;
            friend.s.entity.id = 45;
            friend.s.entity.health = 30;
            f.players.insert(2, friend);
            let heal = |seq| wire::Action { target: 45, ..action(seq) };
            let place = |f: &mut Fixture, x: f32, y: f32, z: f32| {
                let e = &mut f.players.get_mut(&2).unwrap().s.entity;
                (e.x, e.y, e.z) = (x, y, z);
            };
            let begin = |f: &mut Fixture, seq: u64, tick: u64| {
                f.runtime.cooldowns.clear();
                let target = f.players[&2].s.entity.clone();
                let p = f.players.get_mut(&1).unwrap();
                f.runtime.begin(p, 1, heal(seq), &f.policy, Some(&target), tick, &f.db, &f.owner);
            };
            // The start limit: 29 m in 3-D, the height counted.
            place(&mut f, 29.5, 0., 0.);
            begin(&mut f, 1, 10);
            place(&mut f, 28., 8., 0.);
            begin(&mut f, 2, 11);
            assert_eq!(statuses(&mut f.out), ["out_of_range", "out_of_range"]);
            assert!(!f.runtime.busy(1));
            // Accepted at 28.5 m (beyond the package's range of 25); the
            // target walks 60 m out and back to 35 m before the release, which
            // fails nothing; at the impact it is within the hold.
            place(&mut f, 28.5, 0., 0.);
            begin(&mut f, 3, 20);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(30);
            place(&mut f, 60., 0., 0.);
            f.tick(25).await;
            assert!(f.runtime.busy(1), "no range check before the release");
            place(&mut f, 0., 0., 35.);
            f.tick(30).await;
            assert!(f.runtime.casts[&1].released);
            f.at_impact(30).await;
            f.tick(31).await;
            assert_eq!(statuses(&mut f.out), ["healed"]);
            assert_eq!(f.p().s.entity.resource, 15);
            // The hold is on the ground plane: 36 m there, 47 m in 3-D.
            place(&mut f, 20., 0., 0.);
            begin(&mut f, 4, 40);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(50);
            f.tick(50).await;
            place(&mut f, 30., 30., 20.);
            f.at_impact(50).await;
            f.tick(51).await;
            assert_eq!(statuses(&mut f.out), ["healed"]);
            assert_eq!(f.p().s.entity.resource, 10);
            // A target at 40 m on the ground at the impact fails it (the
            // bound is exclusive); nothing is applied or spent.
            place(&mut f, 20., 0., 0.);
            begin(&mut f, 5, 60);
            assert_eq!(statuses(&mut f.out), ["cast_pending"]);
            f.casting(70);
            f.tick(70).await;
            place(&mut f, 0., 0., 40.);
            f.at_impact(70).await;
            f.tick(71).await;
            assert!(!f.runtime.busy(1));
            assert_eq!(statuses(&mut f.out), ["out_of_range"]);
            assert_eq!(f.p().s.entity.resource, 10);
        });
    }
}
