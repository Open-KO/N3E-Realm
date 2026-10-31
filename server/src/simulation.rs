//! One task owns world state. All commands bounded, no database/network waits in tick.
use crate::{
    accounts::{Database, Owner, Selected},
    content::Release,
    movement,
    persistence::Health,
    wire::{self, envelope::Body, Envelope},
};
use prost::Message;
use std::{
    collections::{BTreeMap, VecDeque},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::Instant,
};
use tokio::sync::{mpsc, oneshot, watch};
pub struct Metrics {
    pub sessions: AtomicU64,
    pub rejected: AtomicU64,
    pub queue: AtomicU64,
    pub tick_us: AtomicU64,
    pub checkpoints: AtomicU64,
    /// PQ-250: the largest tick time and command queue depth of the last
    /// complete window of `WINDOW` ticks, the NPCs simulated, the runtime ids
    /// held, and views trimmed to the frame or not sent (view_frame.rs).
    pub tick_max_us: AtomicU64,
    pub queue_max: AtomicU64,
    pub npcs: AtomicU64,
    pub ids: AtomicU64,
    pub views_trimmed: AtomicU64,
    pub views_over: AtomicU64,
}
/// Ticks per `tick_max_us` / `queue_max` window: five seconds at 50 ms.
pub const WINDOW: u64 = 100;
impl Metrics {
    pub fn new() -> Self {
        Self {
            sessions: 0.into(),
            rejected: 0.into(),
            queue: 0.into(),
            tick_us: 0.into(),
            checkpoints: 0.into(),
            tick_max_us: 0.into(),
            queue_max: 0.into(),
            npcs: 0.into(),
            ids: 0.into(),
            views_trimmed: 0.into(),
            views_over: 0.into(),
        }
    }
}
pub enum Command {
    Join(
        Selected,
        wire::Inventory,
        Option<wire::BagState>,
        /// PQ-184: the session's first authority read, taken before it joins.
        Option<(Instant, crate::turbo::Authority)>,
        mpsc::Sender<Envelope>,
        watch::Sender<Option<wire::World>>,
        oneshot::Sender<bool>,
    ),
    Equipment(i64, i64, wire::BagState),
    Storage(i64, i64, wire::StorageRequest),
    Consume(i64,i64,wire::BagRequest),
    FriendTarget(i64,i64,String,oneshot::Sender<Option<crate::friends::Admission>>),
    FriendPresence(i64,i64,wire::FriendPresenceQuery),
    Party(i64,i64,wire::PartyRequest),
    Rest(i64,i64,wire::Rest),
    Move(i64, i64, wire::Move),
    Action(i64, i64, wire::Action, Option<CommittedHit>),
    /// PQ-420 (D-217): the landing of a session's held ranged shot, queued by
    /// the simulation itself (never from the network); it re-enters the
    /// action path as the shot's own action.
    Land(i64, i64),
    Respawn(i64, i64, wire::Respawn),
    Claim(i64, i64, wire::Claim),
    Admin(i64, i64, wire::AdminRequest),
    Commerce(
        i64,
        i64,
        oneshot::Sender<Option<crate::commerce::Admission>>,
    ),
    Chat(i64, i64, String, Option<String>),
    Leave(i64, i64, oneshot::Sender<Option<Selected>>),
    Shutdown(oneshot::Sender<Vec<Selected>>),
}
pub(crate) struct CommittedHit {
    pub(crate) skill: Option<String>,
    pub(crate) style: u32,
    pub(crate) interval: u32,
    pub(crate) moving: bool,
    pub(crate) started: u64,
    pub(crate) outcome: crate::damage::Outcome,
    pub(crate) claim: u64,
    /// D-217: a held shot's cast start, which its strike keeps as `strike_tick`.
    pub(crate) cast: Option<u64>,
    /// PQ-454 (D-228): a released shot's arrival, whose basic attack cost its
    /// release took; the strike takes none.
    pub(crate) paid: bool,
}
struct WearJob {
    /// D-218: the event removes ammunition, so an uncommitted one is `no_ammo`.
    ammo: bool,
    /// PQ-444 (D-224): the event only removes a held shot's ammunition at its
    /// release; its commit releases the shot (`Player.shot`, `releasing`).
    release: bool,
    style: u32,
    interval: u32,
    moving: bool,
    started: u64,
    cast: Option<u64>,
    /// PQ-454 (D-228): the strike is a released shot's arrival (`CommittedHit::paid`).
    paid: bool,
    npc: u64,
    action: Option<wire::Action>,
    outcome: crate::damage::Outcome,
    claim: u64,
    job: tokio::task::JoinHandle<crate::content::Result<crate::wear::Outcome>>,
}
struct ClaimJob {
    request: wire::Claim,
    audience: Vec<i64>,
    job: tokio::task::JoinHandle<crate::content::Result<(wire::ClaimResult, Vec<(i64,wire::Inventory,Option<wire::BagState>)>)>>,
    _permit: tokio::sync::OwnedSemaphorePermit,
}
pub(crate) struct Player {
    pub(crate) rest: crate::rest::State,
    pub(crate) s: Selected,
    pub(crate) inventory: wire::Inventory,
    wear: Option<WearJob>,
    storage: Option<tokio::task::JoinHandle<crate::content::Result<wire::StorageResult>>>,
    consume: Option<tokio::task::JoinHandle<crate::content::Result<crate::consumables::Outcome>>>,
    incoming: Option<(u64, crate::damage::Outcome, crate::wear::Event)>,
    leaving: Option<oneshot::Sender<Option<Selected>>>,
    pub(crate) bag: Option<wire::BagState>,
    pub(crate) stats: Option<wire::DerivedStats>,
    reward: Option<tokio::task::JoinHandle<crate::content::Result<wire::Inventory>>>,
    life_job: Option<(
        u64,
        tokio::task::JoinHandle<crate::content::Result<Selected>>,
    )>,
    pub(crate) last_action: u64,
    pub(crate) skill_hit: u64,
    last_respawn: u64,
    last_claim: u64,
    claim: Option<ClaimJob>,
    next_action: u64,
    out: mpsc::Sender<Envelope>,
    view: watch::Sender<Option<wire::World>>,
    /// The admitted movements not yet applied (PQ-404, D-207).
    pub(crate) moves: crate::move_queue::MoveQueue,
    last_seq: u64,
    last_motion: u64,
    turbo: crate::turbo::State,
    last_chat: u64,
    /// Tick of this session's last NPC record (PQ-189), 0 when none.
    last_record: u64,
    // PQ-194: tick of the session's last operator kill (npc_kill::INTERVAL).
    last_kill: u64,
    last_friend_presence:u64,
    last_friend_sequence:u64,
    last_party_sequence:u64,
    party_view:Option<wire::PartyState>,
    /// PQ-420 (D-217): a ranged shot held until it lands or is cancelled.
    pub(crate) shot: Option<crate::ranged_shot::Shot>,
    /// PQ-439 (D-223): a released ranged shot whose arrow is in flight,
    /// until it lands or is cancelled; the next shot may be held meanwhile.
    pub(crate) flight: Option<crate::ranged_shot::Shot>,
    pub(crate) failed: bool,
}
/// A name lookup over the sessions `visible` admits (PQ-184: a hidden operator
/// is not online for an observer that may not see it, and makes no case-folded
/// name ambiguous in this lookup).
fn friend_target<'a>(players:&'a std::collections::BTreeMap<i64,Player>,name:&str,visible:impl Fn(&Player)->bool)->Option<&'a Player>{
    if let Some(p)=players.values().find(|p|!p.failed&&visible(p)&&p.s.entity.name==name){return Some(p);}
    let mut matching=players.values().filter(|p|!p.failed&&visible(p)&&p.s.entity.name.eq_ignore_ascii_case(name));let first=matching.next();if matching.next().is_none(){first}else{None}
}
fn party_actors(players:&BTreeMap<i64,Player>)->BTreeMap<i64,crate::party::Actor>{
    players.iter().filter(|(_,p)|!p.failed&&p.leaving.is_none()).map(|(&id,p)|(id,crate::party::Actor{session:p.s.generation,name:p.s.entity.name.clone(),level:p.inventory.level as u32,alive:!p.s.dead&&p.s.entity.health>0&&p.life_job.is_none()})).collect()
}
fn party_view(parties:&crate::party::Parties,players:&BTreeMap<i64,Player>,id:i64,rules:&crate::rules::Rules)->wire::PartyState{
    let mut state=wire::PartyState::default();
    if let Some(g)=parties.group(id){state.group=g.id;state.leader=g.leader as u64;
        state.members=g.slots.iter().enumerate().filter_map(|(slot,id)|id.and_then(|id|players.get(&id).map(|p|wire::PartyMember{slot:slot as u32,character:id as u64,entity:p.s.entity.id,name:p.s.entity.name.clone(),level:p.inventory.level as u32,health:p.s.entity.health,max_health:p.stats.as_ref().map_or(rules.health,|s|s.max_health),resource:p.s.entity.resource,max_resource:p.stats.as_ref().map_or(rules.resource,|s|s.max_resource)}))).collect();
    }
    if let Some(v)=parties.invitation(id){if let Some(p)=players.get(&v.inviter){state.invitation=v.token;state.inviter=v.inviter as u64;state.inviter_name=p.s.entity.name.clone();}}
    state
}
impl Player {
    #[cfg(test)]
    pub(crate) fn test_output(&mut self)->mpsc::Receiver<Envelope>{
        let(out,receive)=mpsc::channel(32);self.out=out;receive
    }
    /// PQ-184 (D-152): this session may be sent `other` (turbo::sees).
    pub(crate) fn sees(&self, other: &Player) -> bool {
        crate::turbo::sees(&self.turbo, self.s.id == other.s.id, &other.turbo)
    }
    /// PQ-193 (D-152): the server withholds this session (`turbo::State::hidden`),
    /// so NPCs neither pick, chase nor strike it, nor turn on it when it strikes
    /// them. In-memory lease only: no database I/O in the tick.
    pub(crate) fn hidden(&self) -> bool {
        self.turbo.hidden()
    }
    /// Test only: apply an authority read that holds `server.inspect` or not.
    /// The read is dated an hour ahead, so a stalled test thread cannot see
    /// the 500 ms lease lapse and the session's visibility change under it.
    #[cfg(test)]
    pub(crate) fn test_lease(&mut self, inspect: bool) {
        let generation = self.turbo.generation + 1;
        self.turbo.apply(
            &crate::turbo::Authority { id: self.s.id, session: self.s.generation, generation, allowed: false, inspect },
            Instant::now() + std::time::Duration::from_secs(3600),
        );
    }
    pub(crate) fn combat_pending(&self) -> bool {
        self.wear.is_some() || self.incoming.is_some()
    }
    /// A skill may not start. PQ-447 (D-227): a released shot's arrow in
    /// flight (`flight`) does not refuse one, as 1298's skill start
    /// (`005819e0`) and Ebenezer's magic packet (`004630a6`) do not test it;
    /// a held shot (`shot`) still does, as 1298's cast does until its release.
    pub(crate) fn skill_busy(&self)->bool{self.combat_pending()||self.shot.is_some()||self.reward.is_some()||self.life_job.is_some()||self.leaving.is_some()||self.failed}
    /// PQ-447 (D-227): a skill's impact waits for the caster's own strike's
    /// pending wear write (during a cast, only an arrow's arrival: a new
    /// strike is refused while casting) and its reward: an arrow may now
    /// arrive during the cast, and its commit must not be overtaken by a
    /// second reward. (PQ-454, D-228: the arrival no longer takes the basic
    /// attack's cost, which its release took, so the impact's cost cannot
    /// overtake it.) An incoming hit's write does not hold the impact
    /// (attempt 2): it applies only the caster's health.
    pub(crate) fn impact_waits(&self)->bool{self.wear.as_ref().is_some_and(|w|w.action.is_some())||self.reward.is_some()}
    /// PQ-439 (D-223): takes the shot whose landing was queued (a held shot
    /// without a flight, or a flight at its arrival).
    fn take_landing(&mut self)->Option<crate::ranged_shot::Shot>{
        if self.flight.as_ref().is_some_and(|s|s.landing){self.flight.take()}else if self.shot.as_ref().is_some_and(|s|s.landing){self.shot.take()}else{None}
    }
    /// Puts a shot whose landing must wait back where it was, to be tried
    /// again next tick (D-217).
    fn hold_landing(&mut self,held:&crate::ranged_shot::Shot){
        let back=Some(crate::ranged_shot::Shot{landing:false,..held.clone()});
        if held.released{self.flight=back}else{self.shot=back}
    }
    fn durable_pending(&self)->bool {self.combat_pending()||self.storage.is_some()||self.claim.is_some()||self.consume.is_some()}
    pub(crate) fn receive_hit(
        &mut self,
        npc: &mut wire::Entity,
        r: &crate::rules::Rules,
        tick: u64,
        outcome: crate::damage::Outcome,
    ) {
        if let Some(policy) = r.inventory.as_ref().and_then(|p| p.wear.as_ref()) {
            match self
                .bag
                .as_ref()
                .ok_or_else(|| crate::content::bad("missing wear bag"))
                .and_then(|bag| policy.freeze(bag, 1, npc.id, tick, 2, outcome.damage, None))
            {
                Ok(Some(event)) => {
                    self.incoming = Some((npc.id, outcome, event));
                    return;
                }
                Err(_) => {
                    self.failed = true;
                    return;
                }
                _ => {}
            }
        }
        self.finish_hit(npc, r, tick, &outcome);
    }
    fn finish_hit(
        &mut self,
        npc: &mut wire::Entity,
        r: &crate::rules::Rules,
        tick: u64,
        outcome: &crate::damage::Outcome,
    ) {
        self.skill_hit=tick;
        npc.strike_tick = tick;
        npc.strike_target = self.s.entity.id;
        npc.strike_result = outcome.status().into();
        npc.strike_damage = outcome.damage;
        self.rest.motion(&mut self.s.entity,tick);
        self.s.entity.health = self.s.entity.health.saturating_sub(outcome.damage);
        if self.s.entity.health == 0 {
            crate::life::die(&mut self.s.entity, r, tick);
        }
    }

    fn refresh_stats(&mut self, r: &crate::rules::Rules) -> crate::content::Result<()> {
        if let Some(p) = r.inventory.as_ref().filter(|p| p.stats.is_some()) {
            let bag = self
                .bag
                .as_ref()
                .ok_or_else(|| crate::content::bad("missing equipment state"))?;
            let mut stats = p.stats.as_ref().unwrap().calculate(
                p.equipment.as_ref().unwrap(),
                &bag.equipment,
                self.inventory.level.try_into()?,
            )?;
            stats.equipment_revision = bag.revision;
            self.s.entity.health = self.s.entity.health.min(stats.max_health);
            self.s.entity.resource = self.s.entity.resource.min(stats.max_resource);
            self.stats = Some(stats);
        }
        Ok(())
    }
    fn fill_vitals(&mut self, r: &crate::rules::Rules) {
        self.s.entity.health = self.stats.as_ref().map_or(r.health, |p| p.max_health);
        self.s.entity.resource = self.stats.as_ref().map_or(r.resource, |p| p.max_resource);
    }
}
fn near(a: &wire::Entity, b: &wire::Entity, cell: f32) -> bool {
    ((a.x / cell).floor() as i32 - (b.x / cell).floor() as i32).abs() <= 1
        && ((a.z / cell).floor() as i32 - (b.z / cell).floor() as i32).abs() <= 1
}
/// PQ-178: a chat line is marked as an operator's when the sender's
/// `server.inspect` lease is current (KO's chat handler `005cac80` colours a
/// line whose sender has authority 0, `005cb2af`-`005cb2f5`). Local chat goes
/// only to the sender's interest area; a private line is marked only when the
/// sender is in the recipient's, as KO finds the sender in the other-player map.
/// PQ-184 (D-152): a private line is never marked when the recipient may not see
/// the sender (`visible` false), so the mark tells it neither the sender's role
/// nor whether the sender is in its interest area.
fn operator_line(
    inspecting: bool,
    actor: &wire::Entity,
    recipient: Option<&wire::Entity>,
    visible: bool,
    cell: f32,
) -> bool {
    inspecting && recipient.map_or(true, |r| visible && near(actor, r, cell))
}
/// The character a party request names (PQ-184, D-152): a session the requester
/// may see, or a member of the requester's own group, so a leader can still
/// remove a hidden member while a hidden operator outside the group answers as
/// an absent name (and cannot make a case-folded name ambiguous).
fn party_target(
    parties: &crate::party::Parties,
    players: &BTreeMap<i64, Player>,
    id: i64,
    name: &str,
) -> Option<i64> {
    let requester = players.get(&id);
    let group = parties.group(id);
    friend_target(players, name, |o| {
        requester.is_some_and(|r| r.sees(o)) || group.is_some_and(|g| g.slots.contains(&Some(o.s.id)))
    })
    .map(|p| p.s.id)
}
/// PQ-184 (D-152): take a withheld operator's entity, and its id as another
/// entity's strike or cast target, out of one observer's snapshot unless the
/// observer's own `server.inspect` lease is current. `hidden` holds the entity
/// ids of the sessions `turbo::State::hidden` withholds; the observer itself is
/// never withheld. Events are filtered by `presentation::Events::view`.
fn conceal(
    observer: &wire::Entity,
    sees_hidden: bool,
    hidden: &[u64],
    entities: &mut Vec<wire::Entity>,
) {
    if sees_hidden || hidden.is_empty() {
        return;
    }
    let concealed = |id: u64| id != 0 && id != observer.id && hidden.contains(&id);
    entities.retain(|e| !concealed(e.id));
    for e in entities.iter_mut() {
        clear_targets(observer, sees_hidden, hidden, e);
    }
}
/// The target half of `conceal` for one entity the observer keeps: a strike or
/// cast target naming a withheld session is cleared.
fn clear_targets(observer: &wire::Entity, sees_hidden: bool, hidden: &[u64], e: &mut wire::Entity) {
    if sees_hidden || hidden.is_empty() {
        return;
    }
    let concealed = |id: u64| id != 0 && id != observer.id && hidden.contains(&id);
    if concealed(e.strike_target) {
        e.strike_target = 0;
    }
    if concealed(e.cast_target) {
        e.cast_target = 0;
    }
}
/// PQ-184 (D-152), once per tick before any snapshot: record the entity ids
/// withheld now in the presentation history (which marks the events naming
/// them), and clear every strike or cast target that still names an id that was
/// withheld at the previous tick and no longer belongs to any session (it left,
/// or took a new entity id at a respawn), so no later view names it. Returns
/// the ids withheld now.
fn withhold<'a>(
    presentation: &mut crate::presentation::Events,
    players: &mut BTreeMap<i64, Player>,
    npcs: impl Iterator<Item = &'a mut wire::Entity>,
) -> Vec<u64> {
    let hidden: Vec<u64> = players.values().filter(|q| q.turbo.hidden()).map(|q| q.s.entity.id).collect();
    let mut gone = presentation.withhold(&hidden);
    gone.retain(|id| !players.values().any(|q| q.s.entity.id == *id));
    if !gone.is_empty() {
        let forget = |e: &mut wire::Entity| {
            if gone.contains(&e.strike_target) {
                e.strike_target = 0;
            }
            if gone.contains(&e.cast_target) {
                e.cast_target = 0;
            }
        };
        npcs.for_each(forget);
        players.values_mut().for_each(|p| forget(&mut p.s.entity));
    }
    hidden
}
/// The entity a player's action names: an NPC, or a player the actor may see
/// (PQ-184: a withheld operator is no target, as an absent entity is not).
pub(crate) fn action_target(
    npcs: &[crate::gameplay::Npc],
    players: &BTreeMap<i64, Player>,
    actor: i64,
    entity: u64,
) -> Option<wire::Entity> {
    let actor = players.get(&actor);
    npcs.iter()
        .map(|n| &n.entity)
        .chain(
            players
                .values()
                .filter(|p| !p.failed && actor.is_some_and(|a| a.sees(p)))
                .map(|p| &p.s.entity),
        )
        .find(|e| e.id == entity)
        .cloned()
}
/// One NPC's step of the tick. An NPC that leaves it under a new entity id (an
/// encounter reset after damage, a respawn) keeps its trace mark (PQ-186).
fn step_traced(
    npc: &mut crate::gameplay::Npc,
    traces: &mut crate::npc_trace::Marks,
    step: impl FnOnce(&mut crate::gameplay::Npc),
) {
    let before = npc.entity.id;
    step(npc);
    traces.follow(before, npc.entity.id);
}
/// The settlement of a killed NPC's encounter: freezes its contribution ledger
/// over the players present and draws its coins and items. Shared by a
/// strike's lethal blow and the operator kill (PQ-194). `Err` means the
/// simulation stops owning the realm (`health.invalidate()`), as before.
#[allow(clippy::too_many_arguments)]
fn encounter_settlement(
    npc: &mut crate::gameplay::Npc,
    r: &crate::content::Release,
    policy: &crate::progression::Policy,
    players: &BTreeMap<i64, Player>,
    parties: &crate::party::Parties,
    generation: i64,
    tick: u64,
    claim: u64,
    drop_random: &mut crate::drop_generation::Random,
    group_random: &mut Option<crate::item_drops::GroupRandom>,
) -> Result<crate::progression::Settlement, ()> {
    // One zone per realm currently; game namespace is the stable zone key.
    let position = [npc.entity.x, npc.entity.y, npc.entity.z];
    // PQ-249: the NPC's template level and XP, recorded in the settlement.
    let reward = npc.cycle.as_ref().and_then(|c| c.npc_reward);
    let effective = policy.for_npc(reward);
    let policy = &*effective;
    let (recipients, groups) = npc
        .ledger
        .freeze_parties(policy, &r.game, position, |id| {
            players.get(&id).filter(|p| !p.failed).map(|p| crate::progression::Presence {
                alive: p.s.entity.health > 0,
                zone: r.game.clone(),
                position: [p.s.entity.x, p.s.entity.y, p.s.entity.z],
                level: p.inventory.level as u32,
            })
        }, |id| {
            parties.group(id).map(|g| crate::party_rewards::Group {
                id: g.id,
                leader_level: players.get(&g.leader).map_or(1, |p| p.inventory.level as u32),
                members: g.slots.iter().flatten().copied().collect(),
                credited: Vec::new(),
            })
        })
        .map_err(|_| ())?;
    let mut settlement = crate::progression::Settlement {
        npc: reward,
        items: None,
        coins: None,
        loot_order: policy.party_loot.as_ref().map(|_| npc.ledger.order()),
        parties: groups,
        encounter: npc.entity.id,
        generation,
        release: (0..32)
            .map(|i| u8::from_str_radix(&r.hash[i * 2..i * 2 + 2], 16).unwrap())
            .collect(),
        definition: policy.hash.clone(),
        zone: r.game.clone(),
        position,
        tick,
        claim,
        recipients,
    };
    if let Some(p) = &policy.coins {
        let draw = drop_random
            .draw(p.generation.minimum_percent, p.generation.maximum_percent)
            .map_err(|_| ())?;
        let amount = p
            .generation
            .amount(draw, crate::drop_generation::eligible(&settlement))
            .map_err(|_| ())?;
        settlement.coins = Some(crate::drop_generation::Outcome { draw, amount });
    }
    if let Some(p) = &policy.items {
        let level = settlement
            .owner()
            .and_then(|id| settlement.recipients.iter().find(|r| r.id == id))
            .map_or(1, |r| r.level);
        let coins = settlement.coins.as_ref().is_some_and(|c| c.amount > 0);
        settlement.items = Some(
            p.generate(drop_random, group_random.as_mut().unwrap(), policy.npc_level, level, false, coins)
                .map_err(|_| ())?,
        );
    }
    Ok(settlement)
}
/// Refuse one client request: `request` is its Envelope field number
/// (`crate::network::request`), carried in `Error.request` (PQ-405, D-208).
fn reject(p: &mut Player, metrics: &Metrics, request: u32, code: i32, detail: &str) {
    metrics.rejected.fetch_add(1, Ordering::Relaxed);
    deliver(p, crate::network::refusal(code, request, detail));
}
pub(crate) fn deliver(p: &mut Player, e: Envelope) {
    if p.out.try_send(e).is_err() {
        p.failed = true;
        p.view.send_replace(None);
    }
}
/// Admit one movement request (PQ-404, D-207, amending D-014). Invalid or stale
/// requests are refused with code 3 and consume no seq. A valid one is queued:
/// the next tick applies the first, one more is held for the tick after, and a
/// third that arrives while both wait is refused with code 4 without recording
/// its seq. A held movement consumes its seq.
fn admit_movement(p: &mut Player, metrics: &Metrics, r: &Release, g: i64, m: wire::Move, tick: u64) {
    if p.s.generation != g
        || m.session != g as u64
        || (r.protocol >= 7 && m.entity != p.s.entity.id)
        || (r.protocol < 7 && m.turbo)
        || m.seq == 0
        || m.seq <= p.last_seq
        || m.seq >= i64::MAX as u64
        || movement::direction(m.x, m.z).is_err()
        || m.mode > if r.rules.movement.is_some() { 2 } else { 0 }
    {
        reject(p, metrics, crate::network::request::MOVE, 3, "invalid/stale movement or session");
        return;
    }
    let seq = m.seq;
    let moving = m.x != 0. || m.z != 0.;
    if !p.moves.admit(m) {
        reject(p, metrics, crate::network::request::MOVE, 4, "one movement per tick");
        return;
    }
    p.last_seq = seq;
    if moving {
        p.rest.motion(&mut p.s.entity, tick);
        // D-217: a move admitted after a shot's acceptance cancels it; the
        // inputs already queued then may drain (the honest client's last step).
        if let Some(shot) = p.shot.as_mut() {
            shot.moved = true;
        }
    }
}
/// Apply this tick's movement, at most one per session (D-014, D-207), and
/// acknowledge its seq. A held movement moves up for the next tick.
fn apply_movement(p: &mut Player, r: &Release, tick: u64) {
    if let Some(m) = p.moves.take() {
        let turbo = r.protocol >= 7
            && m.turbo
            && m.entity == p.s.entity.id
            && m.permission_generation == p.turbo.generation
            && p.turbo.permitted()
            && p.s.entity.health > 0;
        p.turbo.input_tick = tick;
        p.turbo.active = turbo;
        p.s.entity.turbo = turbo;
        let d = movement::direction(m.x, m.z).unwrap();
        if m.x!=0.||m.z!=0. {p.rest.motion(&mut p.s.entity,tick);}
        let e = &mut p.s.entity;
        let q = if e.health == 0 {
            [e.x, e.y, e.z]
        } else if let Some(cfg) = r.rules.movement {
            let multiplier = if turbo { r.turbo_multiplier } else { 1. };
            // Protocol 7 added turbo; earlier packages always move at 1x.
            if r.protocol >= 7 {
                movement::advance_scaled(
                    &r.collision,
                    [e.x, e.y, e.z],
                    m.x,
                    m.z,
                    m.mode,
                    cfg,
                    multiplier,
                )
                .unwrap()
            } else {
                movement::advance(&r.collision, [e.x, e.y, e.z], m.x, m.z, m.mode, cfg)
                    .unwrap()
            }
        } else {
            let scale = r.rules.speed / 3.;
            movement::step(&r.collision, [e.x, e.y, e.z], [d[0] * scale, d[1] * scale])
        };
        if (e.x-q[0]).abs()+(e.z-q[2]).abs()>0.00001 {p.last_motion=tick;}
        e.x = q[0];
        e.y = q[1];
        e.z = q[2];
        e.ack = m.seq;
        e.movement_mode = m.mode;
    }
}
/// PQ-439 (D-223): releases a held shot at `tick`: its arrow flies the 3-D
/// distance between the archer and `target` at the profile's speed; the
/// archer's strike fields show it `released`, the release event (kind 7) is
/// published and the shot waits for its arrival in `Player.flight`.
fn fly(p:&mut Player,mut shot:crate::ranged_shot::Shot,target:&wire::Entity,tick:u64,protocol:u32,presentation:&mut crate::presentation::Events){
    let e=&p.s.entity;
    let distance=((target.x-e.x).powi(2)+(target.y-e.y).powi(2)+(target.z-e.z).powi(2)).sqrt();
    crate::ranged_shot::release(&mut shot,distance,tick);
    shot.releasing=false;
    crate::ranged_shot::released(&mut p.s.entity,shot.started);
    let e=&p.s.entity;
    presentation.push(wire::PresentationEvent{tick,request_sequence:if protocol >= 28 {shot.action.seq} else {0},actor:e.id,target:target.id,kind:7,
        style:shot.style,x:e.x,y:e.y,z:e.z,target_x:target.x,target_y:target.y,target_z:target.z,..Default::default()});
    p.flight=Some(shot);
}
pub async fn run(
    health: Arc<Health>,
    ticks: Arc<AtomicU64>,
    metrics: Arc<Metrics>,
    r: Arc<Release>,
    db: Database,
    owner: Arc<Owner>,
    mut revision: wire::Revision,
    mut rx: mpsc::Receiver<Command>,
) {
    let mut authority_job: Option<(
        Instant,
        tokio::task::JoinHandle<crate::content::Result<Vec<crate::turbo::Authority>>>,
    )> = None;
    let mut authority_ack: Option<tokio::task::JoinHandle<crate::content::Result<()>>> = None;
    let mut rng = match crate::damage::Random::new() {
        Ok(rng) => rng,
        Err(_) => {
            health.invalidate();
            return;
        }
    };
    let mut group_random=r.rules.progression.as_ref().and_then(|p|p.items.as_ref()).map(crate::item_drops::GroupRandom::new);
    let mut drop_random=match crate::drop_generation::Random::new() {Ok(r)=>r,Err(_)=>{health.invalidate();return;}};
    let mut admin_jobs: VecDeque<(
        i64,
        i64,
        Vec<u8>,
        tokio::task::JoinHandle<crate::content::Result<(wire::AdminResult, wire::Registry)>>,
    )> = VecDeque::new();
    let mut temporary_results: BTreeMap<(i64, String), (Vec<u8>, wire::AdminResult)> =
        BTreeMap::new();
    // PQ-186: NPCs an operator traced; reports follow each session's inspect lease.
    let mut traces = crate::npc_trace::Marks::default();
    let claim_slots = Arc::new(tokio::sync::Semaphore::new(64));
    let mut players: BTreeMap<i64, Player> = BTreeMap::new();
    let mut skill_runtime=crate::skill_runtime::Runtime::default();
    let mut presentation=crate::presentation::Events::default();
    let mut parties=crate::party::Parties::default();
    // 50 ms in production; a disposable test realm may shorten it (clock.rs, PQ-115).
    let mut timer = tokio::time::interval(std::time::Duration::from_millis(crate::clock::tick_ms()));
    timer.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut checkpoint: Option<tokio::task::JoinHandle<crate::content::Result<()>>> = None;
    let mut saved_at = Instant::now();
    let mut durable_at = saved_at;
    // PQ-250: one id per spawn plus the base pool, in bounded batches, before
    // the first tick; refills scale with the population (instance_ids.rs).
    let id_plan = crate::instance_ids::plan(r.rules.spawns.len());
    let mut ids: VecDeque<u64> = VecDeque::with_capacity(id_plan.startup + id_plan.batch);
    for n in crate::instance_ids::batches(id_plan.startup) {
        match db.instances(n).await {
            Ok(v) if v.len() == n as usize => ids.extend(v),
            _ => {
                health.invalidate();
                return;
            }
        }
    }
    let mut npcs: Vec<_> = r
        .rules
        .spawns
        .iter()
        .enumerate()
        .map(|(i, _)| {
            let rules = crate::administration::cycle_rules(&r, &revision, i);
            let mut npc = crate::gameplay::Npc::spawn(&rules, &r.collision, ids.pop_front().unwrap(), &mut rng);
            npc.definition_revision = revision.revision;
            npc.entity.definition_revision = revision.revision;
            npc.cycle = Some(rules);
            npc
        })
        .collect();
    let mut settlements: VecDeque<
        tokio::task::JoinHandle<crate::content::Result<crate::settlements::Committed>>,
    > = VecDeque::new();
    let mut refill: Option<tokio::task::JoinHandle<crate::content::Result<Vec<u64>>>> = None;
    let mut expiry: Option<tokio::task::JoinHandle<crate::content::Result<()>>> = None;
    let mut deferred = VecDeque::new();
    let mut reserved_combat = 0usize;
    let mut shutting_down: Option<oneshot::Sender<Vec<Selected>>> = None;
    // PQ-250: (largest tick us, deepest queue, ticks) of the current window.
    let mut window = (0u64, 0u64, 0u64);
    loop {
        timer.tick().await;
        let start = Instant::now();
        let queued = rx.len() as u64;
        metrics.queue.store(queued, Ordering::Relaxed);
        // Only await already-finished tasks. Durable wear precedes any published hit.
        for (&id, p) in players.iter_mut() {
            if p.consume.as_ref().is_some_and(|j|j.is_finished()) {
                match p.consume.take().unwrap().await {
                    Ok(Ok(outcome))=>{
                        if let Some(bag)=&outcome.result.state {if p.bag.as_ref().is_none_or(|v|bag.revision>=v.revision){p.bag=Some(bag.clone());}}
                        if p.refresh_stats(&r.rules).is_err(){p.failed=true;health.invalidate();}
                        if outcome.entity==p.s.entity.id&&outcome.life==p.s.life_revision&&!p.failed {
                            if let Some(effect)=outcome.effect {
                                effect.apply(&mut p.s.entity,p.stats.as_ref().map_or(r.rules.health,|s|s.max_health),p.stats.as_ref().map_or(r.rules.resource,|s|s.max_resource));
                                if p.s.entity.health>0 {presentation.consumed(ticks.load(Ordering::Relaxed),&p.s.entity,effect.item);}
                            }
                        }
                        deliver(p,Envelope{body:Some(Body::BagResult(outcome.result))});
                    },
                    _=>reject(p,&metrics,crate::network::request::BAG,4,"consumable unavailable or invalid request"),
                }
                if let Some(reply)=p.leaving.take(){deferred.push_back(Command::Leave(id,p.s.generation,reply));}
            }
            if p.storage.as_ref().is_some_and(|j|j.is_finished()) {
                match p.storage.take().unwrap().await {
                    Ok(Ok(result))=>{
                        if let Some(bag)=&result.bag {if p.bag.as_ref().is_none_or(|v|bag.revision>=v.revision){p.bag=Some(bag.clone());}}
                        if let Some(v)=&result.inventory {if v.revision>=p.inventory.revision{p.inventory=v.clone();}}
                        if p.refresh_stats(&r.rules).is_err(){p.failed=true;health.invalidate();}
                        if p.out.try_send(Envelope{body:Some(Body::StorageResult(result))}).is_err(){p.failed=true;}
                    },
                    _=>{reject(p,&metrics,crate::network::request::STORAGE,4,"storage unavailable or invalid request");}
                }
                if let Some(reply)=p.leaving.take(){deferred.push_back(Command::Leave(id,p.s.generation,reply));}
            }
            if !health.owned() && p.incoming.take().is_some() {
                for npc in &mut npcs {
                    if npc.pending == Some(id) {
                        npc.pending = None;
                    }
                }
                p.failed = true;
                if let Some(reply) = p.leaving.take() {
                    deferred.push_back(Command::Leave(id, p.s.generation, reply));
                }
            }
            if p.wear.is_none() && p.incoming.is_some() && !ids.is_empty() {
                let (npc, outcome, mut event) = p.incoming.take().unwrap();
                event.id = ids.pop_front().unwrap();
                let db = db.clone();
                let owner = owner.clone();
                let selected = p.s.clone();
                let bag = r.rules.inventory.as_deref().cloned().unwrap();
                let reward = r.rules.item.clone();
                p.wear = Some(WearJob {
                    ammo: false,
                    release: false,
                    style: 0,
                    interval: 0,
                    moving: false,
                    started: event.tick,
                    cast: None,
                    paid: false,
                    npc,
                    action: None,
                    outcome,
                    claim: 0,
                    job: tokio::spawn(
                        async move { db.wear(owner, selected, bag, reward, event).await },
                    ),
                });
            }
            // PQ-444 (D-224): a release's ammunition write ended. Committed,
            // the arrow is spent and the shot flies (or, if it can no longer
            // fly, fails as a cancel in flight would); not committed, the
            // locked bag held too few and the shot fails `no_ammo`, as 1298's
            // flying phase fails (0046f3f1 returns 4).
            if p.wear.as_ref().is_some_and(|v| v.release && v.job.is_finished()) {
                let pending = p.wear.take().unwrap();
                let shot = p.shot.take().filter(|s| s.releasing && s.started == pending.started);
                match pending.job.await {
                    Ok(Ok(result)) => {
                        if p.bag.as_ref().is_none_or(|old| old.revision <= result.state.revision) {
                            p.bag = Some(result.state.clone());
                        }
                        if p.refresh_stats(&r.rules).is_err() {
                            p.failed = true;
                            health.invalidate();
                        }
                        deliver(p, Envelope { body: Some(Body::BagResult(wire::BagResult {
                            request: String::new(),
                            status: if result.committed { "worn" } else { "no_ammo" }.into(),
                            state: Some(result.state),
                        })) });
                        if let Some(shot) = shot {
                            let tick = ticks.load(Ordering::Relaxed);
                            let target = npcs.iter().find(|n| n.entity.id == shot.npc).map(|n| n.entity.clone());
                            let verdict = result.committed.then(|| {
                                let seen = crate::ranged_shot::Seen {
                                    failed: p.failed, generation: p.s.generation, entity: p.s.entity.id,
                                    life: p.s.life_revision, health: p.s.entity.health,
                                    style: r.rules.combat_animation.as_ref().map_or(0, |policy| policy.select(p.bag.as_ref())),
                                    target: target.as_ref(), busy: false, flying: false, writing: false, short: false, held: true,
                                };
                                let probe = crate::ranged_shot::Shot { released: true, arrive: u64::MAX, ..shot.clone() };
                                crate::ranged_shot::verdict(&probe, &seen, tick)
                            });
                            match verdict {
                                None => {
                                    crate::ranged_shot::clear(&mut p.s.entity, shot.started);
                                    deliver(p, Envelope { body: Some(Body::ActionResult(wire::ActionResult {
                                        seq: shot.action.seq, status: "no_ammo".into(), target: shot.action.target, damage: 0,
                                    })) });
                                }
                                Some(crate::ranged_shot::Verdict::Cancel(status)) => {
                                    crate::ranged_shot::released(&mut p.s.entity, shot.started);
                                    deliver(p, Envelope { body: Some(Body::ActionResult(wire::ActionResult {
                                        seq: shot.action.seq, status: status.into(), target: shot.action.target, damage: 0,
                                    })) });
                                }
                                Some(_) => fly(p, shot, target.as_ref().unwrap(), tick, r.protocol, &mut presentation),
                            }
                        }
                    }
                    _ => {
                        p.failed = true;
                        health.invalidate();
                    }
                }
                if let Some(reply) = p.leaving.take() {
                    deferred.push_back(Command::Leave(id, p.s.generation, reply));
                }
            }
            // PQ-444 review: a release write that finishes after the check
            // above (the job runs on another worker thread) waits for the
            // next tick's release check; it is never taken as a strike's wear.
            if p.wear.as_ref().is_some_and(|v| !v.release && v.job.is_finished()) {
                let pending = p.wear.take().unwrap();
                let npc = npcs.iter_mut().find(|n| n.entity.id == pending.npc);
                let result = pending.job.await;
                match (result, npc) {
                    (Ok(Ok(result)), Some(npc)) => {
                        if p.bag
                            .as_ref()
                            .is_none_or(|old| old.revision <= result.state.revision)
                        {
                            p.bag = Some(result.state.clone());
                        }
                        if p.refresh_stats(&r.rules).is_err() {
                            p.failed = true;
                            health.invalidate();
                        }
                        deliver(
                            p,
                            Envelope {
                                body: Some(Body::BagResult(wire::BagResult {
                                    request: String::new(),
                                    status: if result.committed {
                                        "worn"
                                    } else if pending.ammo {
                                        "no_ammo"
                                    } else {
                                        "revision_conflict"
                                    }
                                    .into(),
                                    state: Some(result.state),
                                })),
                            },
                        );
                        if let Some(a) = pending.action {
                            if result.committed {
                                deferred.push_back(Command::Action(
                                    id,
                                    p.s.generation,
                                    a,
                                    Some(CommittedHit {
                                        skill: None,
                                        style: pending.style,
                                        interval: pending.interval,
                                        moving: pending.moving,
                                        started: pending.started,
                                        outcome: pending.outcome,
                                        claim: pending.claim,
                                        cast: pending.cast,
                                        paid: pending.paid,
                                    }),
                                ));
                            } else {
                                npc.pending = None;
                                reserved_combat -= 1;
                                // D-217: a held shot that does not land leaves no cast behind.
                                if let Some(started) = pending.cast {
                                    crate::ranged_shot::clear(&mut p.s.entity, started);
                                }
                                deliver(
                                    p,
                                    Envelope {
                                        body: Some(Body::ActionResult(wire::ActionResult {
                                            seq: a.seq,
                                            // D-218: the locked bag had too little ammunition.
                                            status: if pending.ammo { "no_ammo" } else { "equipment_changed" }.into(),
                                            target: a.target,
                                            damage: 0,
                                        })),
                                    },
                                );
                            }
                        } else {
                            npc.pending = None;
                            if result.committed {
                                p.finish_hit(
                                    &mut npc.entity,
                                    &r.rules,
                                    ticks.load(Ordering::Relaxed),
                                    &pending.outcome,
                                );
                            }
                        }
                    }
                    _ => {
                        if pending.action.is_some() {
                            reserved_combat -= 1;
                        }
                        for npc in &mut npcs {
                            if npc.entity.id == pending.npc {
                                npc.pending = None;
                            }
                        }
                        p.failed = true;
                        health.invalidate();
                    }
                }
                if let Some(reply) = p.leaving.take() {
                    deferred.push_back(Command::Leave(id, p.s.generation, reply));
                }
            }
        }
        if shutting_down.is_some() && players.values().all(|p| !p.durable_pending()) {
            deferred.push_back(Command::Shutdown(shutting_down.take().unwrap()));
        }
        // Shutdown/leave still drain after admission closes, enabling final fenced saves.
        for _ in 0..256 {
            let Some(mut command) = deferred.pop_front().or_else(|| rx.try_recv().ok()) else {
                break;
            };
            // PQ-420 (D-217): a held shot's landing re-enters the action path
            // as the shot's own action, marked here and nowhere else.
            let mut landing = false;
            if let Command::Land(id, g) = command {
                let Some(shot) = players.get(&id).and_then(|p| p.flight.as_ref().filter(|s| s.landing).or(p.shot.as_ref())).filter(|s| s.landing && s.generation == g) else {
                    continue;
                };
                command = Command::Action(id, g, shot.action.clone(), None);
                landing = true;
            }
            match command {
                Command::Land(..) => {}
                Command::Join(mut s, inventory, bag, authority, out, view, reply) => {
                    let ok = health.owned()
                        && !players.contains_key(&s.id)
                        && !(s.dead && r.rules.life.is_none());
                    if ok {
                        s.entity.life_state = if r.rules.life.is_some() {
                            wire::LifeState::Alive as i32
                        } else {
                            0
                        };
                        s.entity.health = if s.dead { 0 } else { r.rules.health };
                        if s.dead {
                            s.entity.life_state = wire::LifeState::DeadWaiting as i32;
                            s.entity.respawn_tick = ticks.load(Ordering::Relaxed) + s.ready_ticks;
                            crate::life::refresh(&mut s.entity, ticks.load(Ordering::Relaxed));
                        }
                        s.entity.resource = r.rules.resource;
                        let reward = if r.rules.progression.is_some() {
                            let db = db.clone();
                            let selected = s.clone();
                            let owner = owner.clone();
                            let rules = r.rules.clone();
                            Some(tokio::spawn(async move {
                                db.inventory(selected, owner, rules).await
                            }))
                        } else {
                            None
                        };
                        let id = s.id;
                        let generation = s.generation;
                        if r.rules.skills.is_some(){skill_runtime.join(&s,&db,&owner);}
                        players.insert(
                            s.id,
                            Player {
                                rest: Default::default(),
                                s,
                                inventory,
                                bag,
                                stats: None,
                                wear: None,
                                storage: None, consume: None,
                                incoming: None,
                                leaving: None,
                                reward,
                                life_job: None,
                                last_action: 0, skill_hit: 0,
                                last_respawn: 0,
                                last_claim: 0,
                                claim: None,
                                next_action: 0,
                                out,
                                view,
                                moves: Default::default(),
                                last_seq: 0,
                                last_motion: 0,
                                // PQ-184 (D-152): leased from the read taken before
                                // the join, so an operator is withheld from its first
                                // snapshot on; a read of another session is ignored.
                                turbo: {
                                    let mut lease = crate::turbo::State::default();
                                    if let Some((started, a)) = authority.as_ref().filter(|(_, a)| a.id == id && a.session == generation) {
                                        lease.apply(a, *started);
                                    }
                                    lease
                                },
                                last_chat: 0, last_record: 0, last_kill: 0,
                                last_friend_presence:0,
                                last_friend_sequence:0,
                                last_party_sequence:0,party_view:None,
                                shot: None, flight: None,
                                failed: false,
                            },
                        );
                        let p = players.get_mut(&id).unwrap();
                        if p.refresh_stats(&r.rules).is_err() {
                            players.remove(&id);
                            let _ = reply.send(false);
                            continue;
                        }
                        if !p.s.dead {
                            p.fill_vitals(&r.rules);
                        }
                        // PQ-184: marked from admission, before the tick's withhold.
                        if p.turbo.hidden() {
                            presentation.hide(p.s.entity.id);
                        }
                    }
                    let _ = reply.send(ok);
                }
                Command::Party(id,g,q)=>{
                    let Some(policy)=&r.rules.party else{continue;};
                    let Some(p)=players.get_mut(&id).filter(|p|p.s.generation==g&&!p.failed&&p.leaving.is_none()&&health.owned()&&shutting_down.is_none())else{continue;};
                    if q.sequence==0||q.sequence>i64::MAX as u64||q.sequence<=p.last_party_sequence||q.operation>5||
                        (matches!(q.operation,2|3)!=(q.invitation>0))||q.invitation>i64::MAX as u64||
                        (q.operation==1&&!crate::accounts::valid_name(&q.name,policy.name_bytes))||
                        (q.operation==4&&!q.name.is_empty()&&!crate::accounts::valid_name(&q.name,policy.name_bytes))||
                        (!matches!(q.operation,1|4)&&!q.name.is_empty()) {reject(p,&metrics,crate::network::request::PARTY,4,"party request bounds/sequence");continue;}
                    p.last_party_sequence=q.sequence;p.party_view=None;
                    let actors=party_actors(&players);
                    let target=if q.name.is_empty(){Some(id)}else{party_target(&parties,&players,id,&q.name)};
                    let status=match q.operation {
                        0=>"ok",
                        1=>target.map_or("unavailable",|target|parties.invite(policy,&actors,id,target,ticks.load(Ordering::Relaxed))),
                        2|3=>parties.answer(&actors,id,q.invitation,q.operation==2),
                        4=>target.map_or("not_member",|target|parties.remove(id,target)),
                        5=>parties.disband(id),_=>unreachable!(),
                    };
                    deliver(players.get_mut(&id).unwrap(),Envelope{body:Some(Body::PartyResult(wire::PartyResult{sequence:q.sequence,status:status.into()}))});
                }
                Command::FriendTarget(id,g,name,reply)=>{
                    let target=if health.owned()&&r.rules.friends.as_ref().is_some_and(|p|p.name(&name))&&players.get(&id).is_some_and(|p|p.s.generation==g&&!p.failed){
                        friend_target(&players,&name,|o|players.get(&id).is_some_and(|r|r.sees(o))).filter(|p|p.s.entity.health>0&&!p.s.dead&&p.life_job.is_none()).map(|p|crate::friends::Admission{target:p.s.clone(),issued:Instant::now()})
                    }else{None};let _=reply.send(target);
                }
                Command::FriendPresence(id,g,q)=>{
                    let Some(policy)=&r.rules.friends else{continue;};let tick=ticks.load(Ordering::Relaxed);
                    let Some(p)=players.get_mut(&id).filter(|p|p.s.generation==g&&!p.failed&&health.owned())else{continue;};
                    if q.sequence==0||q.sequence<=p.last_friend_sequence||q.sequence>i64::MAX as u64||q.names.len()>policy.capacity as usize||q.names.iter().any(|n|!policy.name(n))||(p.last_friend_presence!=0&&tick.saturating_sub(p.last_friend_presence)<policy.refresh_ticks){reject(p,&metrics,crate::network::request::FRIEND_PRESENCE,4,"friend presence bounds/rate");continue;}
                    p.last_friend_sequence=q.sequence;p.last_friend_presence=tick;
                    let viewer=players.get(&id).unwrap();
                    let entries=q.names.iter().map(|name|{
                        let target=friend_target(&players,name,|o|viewer.sees(o));wire::FriendOnline{name:name.clone(),character:target.map_or(0,|p|p.s.id as u64),entity:target.map_or(0,|p|p.s.entity.id),online:target.is_some(),in_party:target.is_some_and(|p|parties.affiliated(p.s.id))}
                    }).collect();
                    deliver(players.get_mut(&id).unwrap(),Envelope{body:Some(Body::FriendPresence(wire::FriendPresence{sequence:q.sequence,tick,entries}))});
                }
                Command::Consume(id,g,q)=>{
                    if let Some(p)=players.get_mut(&id).filter(|p|p.s.generation==g){
                        if p.failed||!health.owned()||shutting_down.is_some()||p.leaving.is_some(){reject(p,&metrics,crate::network::request::BAG,4,"consumable unavailable");continue;}
                        if p.consume.is_some(){deliver(p,Envelope{body:Some(Body::BagResult(wire::BagResult{request:q.request,status:"use_pending".into(),state:p.bag.clone()}))});continue;}
                        let Some(policy)=r.rules.consumables.as_deref().cloned()else{continue;};
                        let delay=policy.effect(p.bag.as_ref(),&q).map_or(0,|e|e.delay_ms);
                        let db=db.clone();let owner=owner.clone();let selected=p.s.clone();let bag=r.rules.inventory.as_deref().cloned().unwrap();let reward=r.rules.item.clone();let issued=Instant::now();
                        p.consume=Some(tokio::spawn(async move{db.consume(owner,selected,bag,reward,policy,q,issued,delay).await}));
                    }
                }
                Command::Storage(id,g,q)=>{
                    if let Some(p)=players.get_mut(&id).filter(|p|p.s.generation==g){
                        if p.failed||!health.owned()||shutting_down.is_some()||p.life_job.is_some(){reject(p,&metrics,crate::network::request::STORAGE,4,"storage unavailable");continue;}
                        // A deposit starts only with no already-frozen wear, using a bag
                        // revision no newer than this authoritative cache. At equal revision,
                        // its serial must already be in that bag slot. Subsequent equipping
                        // changes the bag CAS, so it cannot both equip and deposit this serial.
                        // New combat stays enabled while the database works.
                        let status=if p.storage.is_some(){Some("storage_pending")}
                        else if q.operation==1&&p.combat_pending(){Some("combat_pending")}
                        else if q.operation==1&&p.bag.as_ref().is_none_or(|b|q.bag_revision>b.revision||(q.bag_revision==b.revision&&b.slots.get(q.source as usize).is_none_or(|v|v.instance!=q.instance))){Some("stale_snapshot")}
                        else{None};
                        if let Some(status)=status{
                            let _=p.out.try_send(Envelope{body:Some(Body::StorageResult(wire::StorageResult{request:q.request,status:status.into(),..Default::default()}))});continue;
                        }
                        let db=db.clone();let owner=owner.clone();let selected=p.s.clone();let rules=r.rules.clone();let issued=Instant::now();
                        p.storage=Some(tokio::spawn(async move{db.storage(owner,selected,rules,q,issued).await}));
                    }
                }
                Command::Equipment(id, g, bag) => {
                    if let Some(p) = players.get_mut(&id).filter(|p| p.s.generation == g) {
                        if p.bag
                            .as_ref()
                            .is_none_or(|old| bag.revision >= old.revision)
                        {
                            p.bag = Some(bag);
                            if p.refresh_stats(&r.rules).is_err() {
                                p.failed = true;
                                health.invalidate();
                            }
                        }
                    }
                }
                Command::Leave(id, g, reply) => {
                    if let Some(p)=players.get_mut(&id).filter(|p|p.s.generation==g){skill_runtime.cancel(id,p,ticks.load(Ordering::Relaxed),&mut presentation,"interrupted",&db,&owner);}
                    if let Some(p) = players
                        .get_mut(&id)
                        .filter(|p| p.s.generation == g && p.durable_pending())
                    {
                        p.leaving = Some(reply);
                        continue;
                    }
                    if players.get(&id).map(|p| p.s.generation) == Some(g) {
                        parties.leave(id);
                        let mut p = players.remove(&id).unwrap();
                        let health = health.clone();
                        tokio::spawn(async move {
                            if let Some((_, job)) = p.life_job.take() {
                                match job.await {
                                    Ok(Ok(s)) => p.s = s,
                                    _ => health.invalidate(),
                                }
                            }
                            if let Some(job) = p.claim.take() {
                                if !matches!(job.job.await, Ok(Ok(_))) {
                                    health.invalidate();
                                }
                            }
                            if let Some(job) = p.reward {
                                if !matches!(job.await, Ok(Ok(_))) {
                                    health.invalidate();
                                }
                            }
                            let _ = reply.send(Some(p.s));
                        });
                    } else {
                        let _ = reply.send(None);
                    }
                }
                Command::Shutdown(reply) => {
                    if players.values().any(|p| p.durable_pending()) {
                        shutting_down = Some(reply);
                        continue;
                    }

                    if let Some(job) = expiry.take() {
                        if !matches!(job.await, Ok(Ok(_))) {
                            health.invalidate();
                        }
                    }
                    while let Some(job) = settlements.pop_front() {
                        if !matches!(job.await, Ok(Ok(_))) {
                            health.invalidate();
                        }
                    }
                    if let Some(task) = checkpoint.take() {
                        let _ = task.await;
                    }
                    let mut states = Vec::new();
                    for mut p in players.into_values() {
                        if let Some((_, job)) = p.life_job.take() {
                            match job.await {
                                Ok(Ok(s)) => p.s = s,
                                _ => health.invalidate(),
                            }
                        }
                        if let Some(job) = p.reward {
                            if !matches!(job.await, Ok(Ok(_))) {
                                health.invalidate();
                            }
                        }
                        if let Some(job) = p.claim.take() {
                            if !matches!(job.job.await, Ok(Ok(_))) {
                                health.invalidate();
                            }
                        }
                        states.push(p.s);
                    }
                    let _ = reply.send(states);
                    return;
                }
                Command::Rest(id,g,q) => {
                    if !health.owned(){continue;}
                    if let (Some(p),Some(policy))=(players.get_mut(&id),r.rules.rest.as_ref()) {
                        if p.s.generation!=g{continue;}
                        // PQ-447 (D-227): an arrow in flight does not refuse rest
                        // (Ebenezer's posture packet 004a8ad1 does not test it);
                        // a held shot still does.
                        let busy=skill_runtime.busy(id)||p.combat_pending()||p.shot.is_some()||p.failed||p.leaving.is_some()||shutting_down.is_some()
                            ||p.moves.moving();
                        let status=p.rest.request(&mut p.s.entity,&q,g,ticks.load(Ordering::Relaxed),policy,busy);
                        if status!="ok"{reject(p,&metrics,crate::network::request::REST,8,status);}
                    }
                }
                Command::Move(id, g, m) => {
                    if !health.owned() {
                        continue;
                    }
                    if let Some(p) = players.get_mut(&id) {
                        admit_movement(p, &metrics, &r, g, m, ticks.load(Ordering::Relaxed));
                    }
                }
                Command::Commerce(id, g, reply) => {
                    let admission = players
                        .get(&id)
                        .filter(|p| {
                            p.s.generation == g
                                && !p.failed
                                && p.life_job.is_none()
                                && health.owned()
                        })
                        .map(|p| crate::commerce::Admission {
                            selected: p.s.clone(),
                            issued: Instant::now(),
                        });
                    let _ = reply.send(admission);
                }
                Command::Admin(id, g, q) => {
                    if let Some(p) = players.get_mut(&id) {
                        if p.s.generation != g || q.session != g as u64 {
                            reject(p, &metrics, crate::network::request::ADMIN, 5, "stale_session");
                        } else if admin_jobs.len() >= 16 {
                            reject(p, &metrics, crate::network::request::ADMIN, 4, "admin queue full");
                        } else {
                            let db = db.clone();
                            let owner = owner.clone();
                            let release = r.clone();
                            let selected = p.s.clone();
                            deliver(
                                p,
                                Envelope {
                                    body: Some(Body::AdminResult(crate::administration::response(
                                        &q, "pending", None,
                                    ))),
                                },
                            );
                            let mut canonical = q.clone();
                            canonical.session = 0;
                            admin_jobs.push_back((
                                id,
                                g,
                                canonical.encode_to_vec(),
                                tokio::spawn(async move {
                                    db.call(move |c| {
                                        crate::administration::execute(
                                            c, &owner, &selected, &release, &q,
                                        )
                                    })
                                    .await
                                }),
                            ));
                        }
                    }
                }
                Command::Claim(id, g, a) => {
                    let routing=r.rules.progression.as_ref().filter(|p|p.party_loot.is_some()).and_then(|_|players.get(&id).map(|actor| {
                        let (group,slots)=if let Some(party)=parties.group(id) {
                            (party.id,party.slots.iter().map(|id|id.and_then(|id|players.get(&id).filter(|p|!p.failed&&p.leaving.is_none()&&p.life_job.is_none()).map(|p|p.s.clone()))).collect())
                        }else{(0,vec![Some(actor.s.clone())])};
                        crate::party_loot::Admission{issued:Instant::now(),group,slots}
                    }));
                    if !health.owned() {
                        continue;
                    }
                    if let Some(p) = players.get_mut(&id) {
                        let status = if p.failed || p.leaving.is_some() || shutting_down.is_some() {
                            "unavailable"
                        } else if g != p.s.generation || a.session != g as u64 {
                            "stale_session"
                        } else if a.seq == 0 || a.seq <= p.last_claim || a.seq >= i64::MAX as u64 {
                            "stale_request"
                        } else {
                            p.last_claim = a.seq;
                            if a.operation == 0 || a.operation > i64::MAX as u64 {
                                "unknown"
                            } else if let Some(job) = &p.claim {
                                let op = &job.request;
                                if op.operation == a.operation {
                                    if op.encounter == a.encounter
                                        && op.item == a.item
                                        && op.quantity == a.quantity
                                    {
                                        "pending"
                                    } else {
                                        "conflict"
                                    }
                                } else {
                                    "busy"
                                }
                            } else if a.entity != p.s.entity.id {
                                "stale_entity"
                            } else if p.s.entity.health == 0 || p.life_job.is_some() {
                                "not_alive"
                            } else if r.protocol < 5 {
                                "unsupported"
                            } else {
                                let Ok(permit) = claim_slots.clone().try_acquire_owned() else {
                                    deliver(
                                        p,
                                        Envelope {
                                            body: Some(Body::ClaimResult(crate::loot::response(
                                                a.operation,
                                                "busy",
                                            ))),
                                        },
                                    );
                                    continue;
                                };
                                let db = db.clone();
                                let owner = owner.clone();
                                let rules = r.rules.clone();
                                let selected = p.s.clone();
                                let zone = r.game.clone();
                                let op = a.operation;
                                p.claim = Some(ClaimJob {
                                    request: a.clone(),
                                    audience: routing.as_ref().map_or_else(Vec::new,|r|r.slots.iter().flatten().map(|s|s.id).collect()),
                                    _permit: permit,
                                    job: tokio::spawn(async move {
                                        db.claim(owner, rules, selected, a, zone, routing).await
                                    }),
                                });
                                deliver(
                                    p,
                                    Envelope {
                                        body: Some(Body::ClaimResult(crate::loot::response(
                                            op, "pending",
                                        ))),
                                    },
                                );
                                continue;
                            }
                        };
                        deliver(
                            p,
                            Envelope {
                                body: Some(Body::ClaimResult(crate::loot::response(
                                    a.operation,
                                    status,
                                ))),
                            },
                        );
                    }
                }
                Command::Respawn(id, g, a) => {
                    if !health.owned() {
                        continue;
                    }
                    if let Some(p) = players.get_mut(&id) {
                        let status = match crate::life::validate(
                            &p.s.entity,
                            p.s.generation,
                            g,
                            &a,
                            &mut p.last_respawn,
                            ticks.load(Ordering::Relaxed),
                            r.rules.life.is_some(),
                        ) {
                            Err(status) => status,
                            Ok(()) => {
                                if p.life_job.is_some() {
                                    "pending"
                                } else if let Some(id) = ids.pop_front() {
                                    let mut target = p.s.clone();
                                    crate::life::revive(
                                        &mut target.entity,
                                        id,
                                        r.player_spawn().unwrap(),
                                        &r.rules,
                                    );
                                    if let Some(stats) = &p.stats {
                                        target.entity.health = stats.max_health;
                                        target.entity.resource = stats.max_resource;
                                    }
                                    // Both queued inputs end here (D-207); the
                                    // newest admitted seq is acknowledged.
                                    if let Some(seq) = p.moves.clear() {
                                        target.entity.ack = seq;
                                    }
                                    let db = db.clone();
                                    let owner = owner.clone();
                                    p.life_job = Some((
                                        a.seq,
                                        tokio::spawn(async move {
                                            db.transition(owner, target, false, 0).await
                                        }),
                                    ));
                                    continue;
                                } else {
                                    "unavailable"
                                }
                            }
                        };
                        if status != "respawned" {
                            metrics.rejected.fetch_add(1, Ordering::Relaxed);
                        }
                        deliver(
                            p,
                            Envelope {
                                body: Some(Body::RespawnResult(wire::RespawnResult {
                                    seq: a.seq,
                                    status: status.into(),
                                    entity: p.s.entity.id,
                                })),
                            },
                        );
                    }
                }
                Command::Action(id, g, a, ready) => {
                    if !landing&&ready.is_none()&&r.rules.skills.as_ref().is_some_and(|policy|policy.get(&a.action).is_some()) {
                        if health.owned()&&shutting_down.is_none(){
                            let target=action_target(&npcs,&players,id,a.target);
                            if let Some(p)=players.get_mut(&id){skill_runtime.begin(p,g,a,r.rules.skills.as_ref().unwrap(),target.as_ref(),ticks.load(Ordering::Relaxed),&db,&owner);}
                        }
                        continue;
                    }

                    if !health.owned() {
                        if ready.is_some() {
                            reserved_combat -= 1;
                            for n in &mut npcs {
                                if n.entity.id == a.target && n.pending == Some(id) {
                                    n.pending = None;
                                }
                            }
                        }
                        if landing {
                            if let Some(p) = players.get_mut(&id) {
                                p.take_landing();
                            }
                        }
                        continue;
                    }
                    let tick = ticks.load(Ordering::Relaxed);
                    let selected_npc = npcs.iter_mut().find(|n| n.entity.id == a.target);
                    if ready.is_some() {
                        reserved_combat -= 1;
                    }
                    let previous = selected_npc
                        .as_ref()
                        .and_then(|n| n.ai.target)
                        .and_then(|(id, entity)| {
                            // PQ-193: a hidden target is about to be dropped.
                            players
                                .get(&id)
                                .filter(|p| !p.failed && p.s.entity.id == entity && !p.hidden())
                        })
                        .map(|p| (p.s.entity.clone(), p.stats.clone()));
                    let mut frozen_npc = None;
                    if let Some(p) = players.get_mut(&id) {
                        // PQ-420 (D-217): the held shot this landing resolves.
                        // PQ-439 (D-223): or the flight that arrives.
                        let shot = if landing { p.take_landing() } else { None };
                        let target_pending = selected_npc.as_ref().is_some_and(|n| n.pending.is_some());
                        if let Some(held) = shot.as_ref().filter(|_| (p.combat_pending() || p.reward.is_some() || target_pending) && shutting_down.is_none()) {
                            // A durable combat write on the archer or on the
                            // target (another player's wear commit) began since the
                            // landing was queued: hold the shot and try again next
                            // tick (D-217); its interval is already spent.
                            // PQ-454 (D-228): so does the archer's pending reward
                            // (a skill kill's, during a flight), which before
                            // refused it `reward_pending` after its arrow was spent.
                            p.hold_landing(held);
                            continue;
                        }
                        let mut status = if p.s.generation != g || a.session != g as u64 {
                            "stale_session"
                        } else if ready.is_some() {
                            if selected_npc.as_ref().is_some_and(|n| n.pending == Some(id)) {
                                "hit"
                            } else {
                                "stale_target"
                            }
                        } else if let Some(held) = &shot {
                            // The shot was checked when accepted; at its landing no
                            // sequence, cooldown or start-limit check repeats (1298's
                            // 00585830 / 00584b00 do not check the range again).
                            // PQ-467 (D-233): the hold does, as Ebenezer's effecting
                            // phase passes 004c1dbe (004635c8).
                            if shutting_down.is_some() {
                                "combat_pending"
                            } else if selected_npc.is_none() {
                                "stale_target"
                            } else if r.rules.combat_animation.as_ref().map_or(0, |policy| policy.select(p.bag.as_ref())) != held.style {
                                "equipment_changed"
                            } else {
                                crate::gameplay::landing(
                                    &p.s.entity,
                                    &selected_npc.as_ref().unwrap().entity,
                                    &r.rules,
                                    held.released,
                                    r.rules.combat_animation.as_ref().and_then(|policy| policy.ranged(held.style)),
                                )
                                .err()
                                .unwrap_or("hit")
                            }
                        } else if a.seq == 0 || a.seq <= p.last_action || a.seq >= i64::MAX as u64 {
                            "stale_action"
                        } else {
                            p.last_action = a.seq;
                            p.rest.motion(&mut p.s.entity,tick);
                            // PQ-439 (D-223): a held cast writes nothing at its
                            // acceptance, so the archer's own pending arrival
                            // write (a cast's wear commit, and the target it
                            // reserves) does not refuse it; its own landing
                            // waits for that write (D-217's busy rule). So the
                            // next shot keeps 1298's interval while the
                            // previous arrow lands.
                            let held_cast = r.rules.combat_animation.as_ref()
                                .and_then(|policy| policy.ranged(policy.select(p.bag.as_ref())))
                                .is_some_and(|v| v.land > 0);
                            let own_arrival = held_cast && p.incoming.is_none() && p.wear.as_ref().is_some_and(|w| w.cast.is_some() && !w.release);
                            if (p.combat_pending() && !own_arrival) || p.shot.is_some() || skill_runtime.busy(id) || shutting_down.is_some() {
                                "combat_pending"
                            } else if a.action != r.rules.action {
                                "unknown_action"
                            } else if selected_npc.as_ref().is_some_and(|n| n.pending.is_some_and(|owner| !(own_arrival && owner == id))) {
                                "target_pending"
                            } else if selected_npc.is_none() {
                                "stale_target"
                            } else {
                                // PQ-416 (D-216): the profile the committed
                                // equipment selects may be a ranged basic attack.
                                let ranged = r.rules.combat_animation.as_ref().and_then(|policy| policy.ranged(policy.select(p.bag.as_ref())));
                                crate::gameplay::validate(
                                    &p.s.entity,
                                    &selected_npc.as_ref().unwrap().entity,
                                    &r.rules,
                                    tick,
                                    p.next_action,
                                    p.reward.is_some(),
                                    ranged,
                                )
                                .err()
                                .unwrap_or("hit")
                            }
                        };
                        // PQ-421 (D-218): a ranged profile's shot needs its
                        // ammunition in the first bag slot holding it, at the
                        // acceptance and again at a held shot's landing (1298's
                        // client 0057f7f0 refuses the cast, Ebenezer's flying
                        // phase 0046f3f1 fails it); the strike's durable commit
                        // removes it.
                        // PQ-444 (D-224): a released shot spent its ammunition at
                        // its release; its arrival neither checks nor removes it.
                        if status == "hit" && ready.is_none() && !shot.as_ref().is_some_and(|held| held.released) {
                            let style = r.rules.combat_animation.as_ref().map_or(0, |policy| policy.select(p.bag.as_ref()));
                            if let Some((item, count)) = r.rules.combat_animation.as_ref().and_then(|policy| policy.ammo(style)) {
                                if p.bag.as_ref().is_none_or(|bag| crate::wear::ammo_slot(bag, item, count).is_none()) {
                                    status = "no_ammo";
                                }
                            }
                        }
                        if status == "hit" && ready.is_none() && r.rules.progression.is_some() {
                            if let Err(reason) = selected_npc.as_ref().unwrap().ledger.admission(
                                id,
                                settlements.len() + reserved_combat,
                                ids.len(),
                            ) {
                                if let Some(held) = &shot {
                                    // D-217: no capacity at the landing: hold and
                                    // retry next tick, at most DEFER ticks.
                                    p.hold_landing(held);
                                    continue;
                                }
                                status = reason;
                            }
                        }
                        let mut damage = 0;
                        if status == "hit" && ready.is_none() && shot.is_none() {
                            // PQ-420 (D-217): a ranged profile with a cast time holds
                            // the shot. The strike fields show the cast from now (so
                            // observers start the stretched clip), the interval runs
                            // from now, and the strike lands `land` ticks later
                            // (the tick below queues it) unless it is cancelled.
                            let style=r.rules.combat_animation.as_ref().map_or(0,|policy|policy.select(p.bag.as_ref()));
                            if let Some(cast)=r.rules.combat_animation.as_ref().and_then(|policy|policy.ranged(style)).filter(|v|v.land>0) {
                                let interval=r.rules.combat_animation.as_ref().unwrap().ticks(style,r.rules.cooldown_ticks);
                                p.shot=Some(crate::ranged_shot::Shot{
                                    action:a.clone(),generation:g,entity:p.s.entity.id,life:p.s.life_revision,npc:a.target,
                                    style,started:tick,land:tick+cast.land as u64,moved:false,landing:false,
                                    // D-218: an ammunition profile's landing always commits, a tick
                                    // before its hit; PQ-444 (D-224): with a flight the release
                                    // spends it instead, and the arrival commits only the wear.
                                    lead:u64::from(r.rules.combat_animation.as_ref().unwrap().ammo(style).is_some()&&cast.speed<=0.),
                                    // D-223: a profile with a flight is released at `land`.
                                    speed:cast.speed,released:false,arrive:tick+cast.land as u64,
                                    spend:r.rules.combat_animation.as_ref().unwrap().ammo(style).is_some()&&cast.speed>0.,
                                    releasing:false,
                                });
                                let e=&mut p.s.entity;
                                e.strike_tick=tick;e.strike_target=a.target;e.strike_style=style;e.strike_moving=false;
                                e.strike_sequence=if r.protocol >= 28 { a.seq } else { 0 };
                                e.strike_result="casting".into();e.strike_damage=0;
                                p.next_action=tick+interval as u64;
                                continue;
                            }
                        }
                        if status == "hit" {
                            let npc = selected_npc.unwrap();
                            let hp_before = npc.entity.health;
                            let style=r.rules.combat_animation.as_ref().map_or(0,|policy|policy.select(p.bag.as_ref()));
                            // PQ-422 (D-219): a ranged profile with a type-2 skill
                            // hit resolves as KO's archery (AI 0040d471).
                            let skill_hit=r.rules.combat_animation.as_ref().and_then(|policy|policy.ranged(style)).and_then(|v|v.hit);
                            let outcome =
                                ready
                                    .as_ref()
                                    .map(|v| v.outcome.clone())
                                    .unwrap_or_else(|| {
                                        // PQ-249: the target's template defence and evasion.
                                        npc.cycle
                                            .as_ref()
                                            .unwrap_or(&r.rules)
                                            .damage_policy
                                            .as_ref()
                                            .map(|d| match &skill_hit {
                                                Some(hit) => d.resolve_skill_hit(p.stats.as_ref(), hit, &mut rng),
                                                None => d.resolve_with_player(
                                                    false,
                                                    p.stats.as_ref(),
                                                    &mut rng,
                                                ),
                                            })
                                            .unwrap_or(crate::damage::Outcome {
                                                hit: true,
                                                damage: r.rules.damage,
                                            })
                                    });
                            let interval=r.rules.combat_animation.as_ref().map_or(r.rules.cooldown_ticks,|policy|policy.ticks(style,r.rules.cooldown_ticks));
                            // A ranged strike is never a moving one: KO's cast stops the walk (PQ-416).
                            let moving=r.rules.combat_animation.as_ref().is_some_and(|policy|policy.layered&&policy.ranged(style).is_none()) && p.moves.next().map_or(p.last_motion>0&&tick.saturating_sub(p.last_motion)<=2,|m|m.x!=0.||m.z!=0.);
                            if ready.is_none() {
                                if let Some(policy) =
                                    r.rules.inventory.as_ref().and_then(|b| b.wear.as_ref())
                                {
                                    // PQ-444 (D-224): not again for a released shot.
                                    let ammo = r.rules.combat_animation.as_ref().and_then(|policy| policy.ammo(style))
                                        .filter(|_| !shot.as_ref().is_some_and(|held| held.released));
                                    match policy.freeze(
                                        p.bag.as_ref().unwrap(),
                                        1,
                                        p.s.entity.id,
                                        tick,
                                        1,
                                        outcome.damage,
                                        ammo,
                                    ) {
                                        Ok(Some(mut event)) => {
                                            if ids.len() < 2 {
                                                if let Some(held) = &shot {
                                                    // D-217: hold and retry next tick.
                                                    p.hold_landing(held);
                                                    continue;
                                                }
                                                deliver(
                                                    p,
                                                    Envelope {
                                                        body: Some(Body::ActionResult(
                                                            wire::ActionResult {
                                                                seq: a.seq,
                                                                status: "combat_capacity".into(),
                                                                target: a.target,
                                                                damage: 0,
                                                            },
                                                        )),
                                                    },
                                                );
                                                continue;
                                            }
                                            event.id = ids.pop_front().unwrap();
                                            let claim = ids.pop_front().unwrap();
                                            let db = db.clone();
                                            let owner = owner.clone();
                                            let selected = p.s.clone();
                                            let bag = r.rules.inventory.as_deref().cloned().unwrap();
                                            let reward = r.rules.item.clone();
                                            p.wear = Some(WearJob {
                                                style, interval, moving,
                                                ammo: event.ammo.is_some(),
                                                release: false,
                                                // D-217: a landed shot's interval ran from its cast start.
                                                started: shot.as_ref().map_or(tick, |held| held.started),
                                                cast: shot.as_ref().map(|held| held.started),
                                                paid: shot.as_ref().is_some_and(|held| held.released),
                                                npc: a.target,
                                                action: Some(a),
                                                outcome,
                                                claim,
                                                job: tokio::spawn(async move {
                                                    db.wear(owner, selected, bag, reward, event)
                                                        .await
                                                }),
                                            });
                                            npc.pending = Some(id);
                                            reserved_combat += 1;
                                            continue;
                                        }
                                        Err(_) => {
                                            p.failed = true;
                                            health.invalidate();
                                            continue;
                                        }
                                        _ => {}
                                    }
                                }
                            }
                            npc.pending = None;
                            let cast=shot.as_ref().map(|held|held.started).or(ready.as_ref().and_then(|hit|hit.cast));
                            // PQ-439 (D-223): an arrow that lands while the archer
                            // holds (or has released) a newer cast leaves the
                            // archer's strike fields and interval to that cast.
                            let newer=(cast.is_some()&&(p.shot.is_some()||p.flight.is_some())).then(||(crate::ranged_shot::Strike::of(&p.s.entity),p.next_action));
                            let shot_style=ready.as_ref().map_or(style,|hit|hit.style);
                            if ready.as_ref().is_none_or(|hit|hit.skill.is_none()){
                                p.s.entity.strike_style=shot_style;
                                p.s.entity.strike_moving=ready.as_ref().map_or(moving,|hit|hit.moving);
                            }
                            if let Some(skill)=ready.as_ref().and_then(|hit|hit.skill.as_ref()) {
                                npc.entity.health=npc.entity.health.saturating_sub(outcome.damage);
                                presentation.push(wire::PresentationEvent{tick,actor:p.s.entity.id,target:npc.entity.id,kind:4,key:skill.clone(),x:p.s.entity.x,y:p.s.entity.y,z:p.s.entity.z,target_x:npc.entity.x,target_y:npc.entity.y,target_z:npc.entity.z,..Default::default()});
                            }else{
                                // PQ-454 (D-228): a released shot's arrival paid at its release.
                                let paid=shot.as_ref().map_or(ready.as_ref().is_some_and(|hit|hit.paid),|held|held.released);
                                crate::gameplay::finish_attack(&mut p.s.entity,&mut npc.entity,&r.rules,tick,&mut p.next_action,&outcome,paid);
                                // Output-only correlation, after authoritative completion/wear.
                                p.s.entity.strike_sequence = if r.protocol >= 28 { a.seq } else { 0 };
                                p.next_action=ready.as_ref().map_or(cast.unwrap_or(tick)+interval as u64,|hit|hit.started+hit.interval as u64);
                                if let Some(started)=cast {
                                    // D-217: the strike keeps its cast start (observers
                                    // started the clip then); the landing is its own
                                    // event, which draws the hit with no marker delay.
                                    p.s.entity.strike_tick=started;
                                    let e=&p.s.entity;
                                    presentation.push(wire::PresentationEvent{tick,request_sequence:e.strike_sequence,actor:e.id,target:npc.entity.id,kind:6,
                                        style:shot_style,hit:outcome.hit,x:e.x,y:e.y,z:e.z,target_x:npc.entity.x,target_y:npc.entity.y,target_z:npc.entity.z,..Default::default()});
                                }
                                if let Some((kept,next))=newer {
                                    kept.put(&mut p.s.entity);
                                    p.next_action=p.next_action.max(next);
                                }
                            }
                            status = outcome.status();
                            damage = outcome.damage;
                            if r.rules.progression.is_some() {
                                npc.ledger
                                    .credit(id, damage, hp_before)
                                    .expect("ledger reserved before damage");
                            }
                            // PQ-193: a hidden attacker's damage counts, but the NPC
                            // does not turn on it (KO AI 0041f715 skips authority 0).
                            if damage > 0 && npc.entity.health > 0 && !p.hidden() {
                                npc.ai.hit_with_stats(
                                    &mut npc.entity,
                                    (id, &p.s.entity),
                                    previous.as_ref().map(|p| &p.0),
                                    npc.cycle.as_ref().unwrap_or(&r.rules),
                                    tick,
                                    &mut rng,
                                    p.stats.as_ref(),
                                    previous.as_ref().and_then(|p| p.1.as_ref()),
                                );
                            }
                            if npc.entity.health == 0 {
                                crate::life::die(
                                    &mut npc.entity,
                                    npc.cycle.as_ref().unwrap_or(&r.rules),
                                    tick,
                                );
                                npc.entity.behavior = "dead".into();
                                if r.rules.progression.is_some() {
                                    frozen_npc = Some(npc);
                                } else {
                                    let op = npc.entity.id;
                                    p.inventory.pending = op;
                                    p.inventory.reward_status = "pending".into();
                                    let db = db.clone();
                                    let owner = owner.clone();
                                    let rules = npc.cycle.as_ref().unwrap_or(&r.rules).clone();
                                    let selected = p.s.clone();
                                    p.reward = Some(tokio::spawn(async move {
                                        db.reward(selected, owner, rules, op).await
                                    }));
                                }
                            }
                        } else {
                            metrics.rejected.fetch_add(1, Ordering::Relaxed);
                            // D-217: a held shot that does not land leaves no cast behind.
                            if let Some(started) = shot.as_ref().map(|held| held.started).or(ready.as_ref().and_then(|hit| hit.cast)) {
                                crate::ranged_shot::clear(&mut p.s.entity, started);
                            }
                        }
                        deliver(
                            p,
                            Envelope {
                                body: Some(Body::ActionResult(wire::ActionResult {
                                    seq: a.seq,
                                    status: status.into(),
                                    target: a.target,
                                    damage,
                                })),
                            },
                        );
                    }
                    if let Some(npc) = frozen_npc {
                        let policy = r.rules.progression.as_deref().unwrap().clone();
                        let claim = ready
                            .as_ref()
                            .map_or_else(|| ids.pop_front().unwrap(), |v| v.claim);
                        match encounter_settlement(npc, &r, &policy, &players, &parties, owner.generation, tick, claim, &mut drop_random, &mut group_random) {
                            Ok(settlement) => {
                                let db = db.clone();
                                let owner = owner.clone();
                                settlements.push_back(tokio::spawn(async move {
                                    db.settle(owner, policy, settlement).await
                                }));
                            }
                            Err(()) => health.invalidate(),
                        }
                    }
                }
                Command::Chat(id, g, text, recipient) => {
                    if !health.owned() {
                        continue;
                    }
                    let tick = ticks.load(Ordering::Relaxed);
                    let chat = if recipient.is_some() {
                        crate::network::request::PRIVATE_MESSAGE
                    } else {
                        crate::network::request::CHAT
                    };
                    if let Some(p) = players.get_mut(&id) {
                        if p.s.generation != g {
                            continue;
                        }
                        if text.is_empty()
                            || text.len() > 256
                            || text.chars().any(char::is_control)
                            || (p.last_chat != 0 && tick - p.last_chat < 20)
                        {
                            reject(p, &metrics, chat, 4, "chat length/rate");
                            continue;
                        }
                        // Every admitted attempt spends the shared rate budget, including
                        // nonexistent recipients. Identity and realm come from the session.
                        p.last_chat = tick;
                        let actor = p.s.entity.clone();
                        let inspecting = p.turbo.inspecting();
                        let destination = if let Some(name) = &recipient {
                            if !crate::accounts::valid_name(name, 24) {
                                reject(p, &metrics, chat, 4, "invalid private message recipient");
                                continue;
                            }
                            // Existing realms permit case-distinct names. Prefer exact
                            // identity; a case-folded lookup must be unambiguous.
                            // PQ-184: a hidden operator the sender may not see is
                            // absent, so the line is refused as to an absent name.
                            let viewer = players.get(&id).unwrap();
                            let exact = players
                                .iter()
                                .find(|(_, other)| !other.failed && viewer.sees(other) && other.s.entity.name == *name)
                                .map(|(id, _)| *id);
                            let mut matching = players.iter().filter(|(_, other)| {
                                !other.failed && viewer.sees(other) && other.s.entity.name.eq_ignore_ascii_case(name)
                            });
                            let first = matching.next().map(|(id, _)| *id);
                            let target = exact.or_else(|| {
                                if matching.next().is_none() {
                                    first
                                } else {
                                    None
                                }
                            });
                            match target {
                                Some(target) if target != id => Some(target),
                                _ => {
                                    reject(
                                        players.get_mut(&id).unwrap(),
                                        &metrics,
                                        chat,
                                        4,
                                        "private message recipient unavailable",
                                    );
                                    continue;
                                }
                            }
                        } else {
                            None
                        };
                        let visible = destination
                            .and_then(|t| players.get(&t))
                            .zip(players.get(&id))
                            .map_or(true, |(recipient, sender)| recipient.sees(sender));
                        let from_operator = operator_line(
                            inspecting,
                            &actor,
                            destination.and_then(|t| players.get(&t)).map(|o| &o.s.entity),
                            visible,
                            r.rules.interest_cell,
                        );
                        let message = Envelope {
                            body: Some(Body::Chat(wire::Chat {
                                text,
                                sender: actor.id,
                                sender_name: actor.name.clone(),
                                private_message: destination.is_some(),
                                from_operator,
                            })),
                        };
                        for (other_id, other) in players.iter_mut() {
                            let addressed = match destination {
                                Some(target) => *other_id == target,
                                None => near(&actor, &other.s.entity, r.rules.interest_cell),
                            };
                            if addressed && !other.failed {
                                deliver(other, message.clone());
                            }
                        }
                    }
                }
            }
        }
        if !health.owned() {
            continue;
        }
        let tick = ticks.fetch_add(1, Ordering::Relaxed) + 1;
        // Resolve worker observations before admitting this tick's movement.
        if authority_ack.as_ref().is_some_and(|j| j.is_finished()) {
            if !matches!(authority_ack.take().unwrap().await, Ok(Ok(()))) {
                health.invalidate();
            }
        }
        if authority_ack.is_none() && authority_job.as_ref().is_some_and(|(_, j)| j.is_finished()) {
            let (started, job) = authority_job.take().unwrap();
            match job.await {
                Ok(Ok(rows)) => {
                    let mut applied = Vec::new();
                    for a in rows {
                        if let Some(p) = players
                            .get_mut(&a.id)
                            .filter(|p| p.s.generation == a.session)
                        {
                            p.turbo.apply(&a, started);
                            if !p.turbo.permitted() || !p.turbo.active {
                                p.s.entity.turbo = false;
                            }
                            applied.push(a);
                        }
                    }
                    let db = db.clone();
                    let owner = owner.clone();
                    authority_ack = Some(tokio::spawn(async move {
                        db.call(move |c| crate::turbo::observed(c, &owner, &applied))
                            .await
                    }));
                }
                _ => health.invalidate(),
            }
        }
        if tick % 2 == 0
            && authority_job.is_none()
            && authority_ack.is_none()
            && !players.is_empty()
        {
            let ids: Vec<i64> = players.keys().copied().collect();
            let db = db.clone();
            let owner = owner.clone();
            authority_job = Some((
                Instant::now(),
                tokio::spawn(
                    async move { db.call(move |c| crate::turbo::read(c, &owner, &ids)).await },
                ),
            ));
        }

        if refill.as_ref().is_some_and(|t| t.is_finished()) {
            match refill.take().unwrap().await {
                Ok(Ok(v)) => ids.extend(v),
                _ => health.invalidate(),
            }
        }
        if crate::instance_ids::needs_refill(&id_plan, &ids, refill.is_some()) {
            let db = db.clone();
            let n = id_plan.batch as i64;
            refill = Some(tokio::spawn(async move { db.instances(n).await }));
        }
        let mut reward_applications = 0;
        for _ in 0..8 {
            if !settlements.front().is_some_and(|job| job.is_finished()) {
                break;
            }
            reward_applications += 1;
            match settlements.pop_front().unwrap().await {
                Ok(Ok(result)) => {
                    crate::settlements::fault("before_apply");
                    for v in result.recipients {
                        if let Some(p) = players.get_mut(&v.id) {
                            if v.revision > p.inventory.revision {
                                p.inventory.xp = v.xp;
                                p.inventory.curve_xp = v.curve;
                                p.inventory.level = v.level as u64;
                                p.inventory.revision = v.revision;
                                p.inventory.latest_settlement = result.encounter;
                                p.inventory.settlement_status = result.outcome.clone();
                            }
                        }
                    }
                }
                _ => health.invalidate(),
            }
        }
        if expiry.as_ref().is_some_and(|job| job.is_finished()) {
            if !matches!(expiry.take().unwrap().await, Ok(Ok(()))) {
                health.invalidate();
            }
        }
        if r.protocol >= 5 && tick % 20 == 0 && expiry.is_none() {
            let db = db.clone();
            let owner = owner.clone();
            let policy = r.rules.progression.as_deref().cloned().unwrap();
            expiry = Some(tokio::spawn(
                async move { db.expire_page(owner, policy).await },
            ));
        }
        let mut claimed_inventories=Vec::new();
        let mut claim_notices=Vec::new();
        for p in players.values_mut() {
            if reward_applications < 8 && p.claim.as_ref().is_some_and(|job| job.job.is_finished())
            {
                reward_applications += 1;
                let job=p.claim.take().unwrap();
                match job.job.await {
                    Ok(Ok((result, inventories))) => {
                        crate::loot::fault("before_apply");
                        for (id,v,bag) in inventories {
                            claimed_inventories.push((id,v,bag,(id!=p.s.id).then(||result.clone())));
                        }
                        if result.status=="claimed" && (result.recipient>0 || !result.coins.is_empty()) {
                            for id in job.audience.into_iter().filter(|id|*id!=p.s.id&&*id as u64!=result.recipient&&!result.coins.iter().any(|c|c.character==*id as u64)) {
                                claim_notices.push((id,result.clone()));
                            }
                        }
                        deliver(
                            p,
                            Envelope {
                                body: Some(Body::ClaimResult(result)),
                            },
                        );
                    }
                    _ => health.invalidate(),
                }
                if let Some(reply) = p.leaving.take() {
                    deferred.push_back(Command::Leave(p.s.id, p.s.generation, reply));
                }
            }
            if p.life_job.as_ref().is_some_and(|(_, t)| t.is_finished()) {
                let (seq, job) = p.life_job.take().unwrap();
                match job.await {
                    Ok(Ok(mut s)) => {
                        // Preserve movement acknowledgement accumulated while dead.
                        s.entity.ack = s.entity.ack.max(p.s.entity.ack);
                        if s.dead {
                            s.entity.respawn_tick = tick + s.ready_ticks;
                        }
                        p.s = s;
                        if seq != 0 {
                            p.moves.clear();
                            p.next_action = 0;
                            p.last_motion = 0;
                            deliver(
                                p,
                                Envelope {
                                    body: Some(Body::RespawnResult(wire::RespawnResult {
                                        seq,
                                        status: "respawned".into(),
                                        entity: p.s.entity.id,
                                    })),
                                },
                            );
                        }
                    }
                    _ => health.invalidate(),
                }
            }
            if p.reward.as_ref().is_some_and(|t| t.is_finished()) {
                match p.reward.take().unwrap().await {
                    Ok(Ok(v)) => {
                        crate::rewards::fault("before_response");
                        if r.rules.progression.is_none() || v.revision >= p.inventory.revision {
                            p.inventory = v;
                        }
                    }
                    _ => {
                        p.inventory.reward_status = "unavailable".into();
                        health.invalidate();
                    }
                }
            }
            if p.refresh_stats(&r.rules).is_err() {
                p.failed = true;
                health.invalidate();
            }
            crate::life::refresh(&mut p.s.entity, tick);
            if r.rules.life.is_none() && p.s.entity.health == 0 && tick >= p.s.entity.respawn_tick {
                if let Some(id) = ids.pop_front() {
                    crate::life::revive(
                        &mut p.s.entity,
                        id,
                        r.player_spawn().unwrap(),
                        &r.rules,
                    );
                }
            }
            if let Some(policy)=&r.rules.rest {
                if p.s.entity.sitting && tick>=p.rest.next_recovery && !p.combat_pending() {
                    policy.recover(&mut p.s.entity,p.inventory.level,p.stats.as_ref().map_or(r.rules.health,|s|s.max_health),p.stats.as_ref().map_or(r.rules.resource,|s|s.max_resource));
                    p.rest.next_recovery=tick+policy.interval;
                }
            }
            if tick % r.rules.regen_ticks as u64 == 0 && p.s.entity.health > 0 && !p.s.entity.sitting {
                p.s.entity.resource = (p.s.entity.resource + 1).min(
                    p.stats
                        .as_ref()
                        .map_or(r.rules.resource, |s| s.max_resource),
                );
            }
            if tick.saturating_sub(p.turbo.input_tick) >= 3
                || !p.turbo.permitted()
                || p.s.entity.health == 0
            {
                p.turbo.active = false;
                p.s.entity.turbo = false;
            }
            apply_movement(p, &r, tick);
        }
        for (id,inventory,bag,notice) in claimed_inventories {
            if let Some(p)=players.get_mut(&id) {
                if inventory.revision>=p.inventory.revision {p.inventory=inventory;}
                if let Some(bag)=bag {if p.bag.as_ref().is_none_or(|v|bag.revision>=v.revision){p.bag=Some(bag);}}
                if let Some(result)=notice {deliver(p,Envelope{body:Some(Body::ClaimResult(result))});}
            }
        }
        for (id,result) in claim_notices {
            if let Some(p)=players.get_mut(&id) {deliver(p,Envelope{body:Some(Body::ClaimResult(result))});}
        }
        if !health.owned() {
            continue;
        }
        for _ in 0..8 {
            if !admin_jobs
                .front()
                .is_some_and(|(_, _, _, j)| j.is_finished())
            {
                break;
            }
            let (id, g, payload, job) = admin_jobs.pop_front().unwrap();
            let status_lookup = wire::AdminRequest::decode(payload.as_slice())
                .is_ok_and(|q| q.operation == "status");
            match job.await {
                Ok(Ok((mut result, registry))) => {
                    if result.status == "denied" {
                        metrics.rejected.fetch_add(1, Ordering::Relaxed);
                        if tick % 20 == 0 {
                            eprintln!("admin denied actor={id} tick={tick}");
                        }
                    }
                    if result.status == "spawn_authorized" {
                        let (authorized_generation, spawn) = result
                            .detail
                            .split_once(':')
                            .expect("server authored temporary identity");
                        let authorized_generation: i64 = authorized_generation.parse().unwrap();
                        let index: usize = spawn.parse().unwrap();
                        let key = (id, result.id.clone());
                        if authorized_generation != owner.generation {
                            result.status = "temporary_expired".into();
                        } else if let Some((previous_payload, previous)) =
                            temporary_results.get(&key)
                        {
                            if status_lookup || previous_payload == &payload {
                                result = previous.clone();
                            } else {
                                result.status = "payload_conflict".into();
                            }
                        } else if status_lookup {
                            result.status = "temporary_pending".into();
                        } else if npcs.iter().filter(|n| n.expires != 0).count() >= 16
                            || temporary_results.len() >= 128
                            || ids.len() < 2
                        {
                            result.status = "temporary_limit".into();
                        } else {
                            let rules = crate::administration::cycle_rules(&r, &revision, index);
                            let mut npc = crate::gameplay::Npc::new(
                                &rules,
                                &r.collision,
                                ids.pop_front().unwrap(),
                            );
                            npc.cycle = Some(rules);
                            npc.definition_revision = revision.revision;
                            npc.entity.definition_revision = revision.revision;
                            npc.expires = tick + 1200;
                            result.status = "temporary_applied".into();
                            result.tick = tick;
                            result.detail = format!(
                                "instance={} expires_tick={} session_only",
                                npc.entity.id, npc.expires
                            );
                            npcs.push(npc);
                            temporary_results.insert(key, (payload, result.clone()));
                        }
                    }
                    if result.status == "trace_authorized" {
                        let entity: u64 = result.detail.parse().expect("server authored trace target");
                        let exists = npcs.iter().any(|n| {
                            n.entity.id == entity
                                && n.entity.life_state != wire::LifeState::Dormant as i32
                        });
                        let live_session = players.get(&id).is_some_and(|p| p.s.generation == g);
                        result.status = if live_session {
                            traces.mark((id, g), entity, exists)
                        } else {
                            "stale_session"
                        }
                        .into();
                        result.tick = tick;
                    }
                    if result.status == "record_authorized" {
                        // PQ-189: the snapshot is taken here, from the NPC this
                        // simulation holds; the line is written off the tick and
                        // the operator gets a status only, never the values.
                        let entity: u64 = result.detail.parse().expect("server authored record target");
                        result.detail.clear();
                        let npc = npcs.iter().find(|n| {
                            n.entity.id == entity
                                && n.entity.life_state != wire::LifeState::Dormant as i32
                        });
                        result.status = match (players.get_mut(&id).filter(|p| p.s.generation == g), npc) {
                            (None, _) => "stale_session",
                            (Some(_), None) => "unknown_target",
                            (Some(p), Some(n)) => {
                                if crate::npc_record::admit(&mut p.last_record, tick) {
                                    crate::npc_record::write(crate::npc_record::line(&n.entity, n.cycle.as_ref().unwrap_or(&r.rules).npc_health, tick));
                                    "recorded"
                                } else {
                                    "record_limit"
                                }
                            }
                        }
                        .into();
                    }
                    if result.status == "kill_authorized" {
                        // PQ-194 (D-157): freshly authorized and audited by the
                        // admin worker against entity.kill (a replayed or
                        // looked-up row arrives as kill_replayed and is only
                        // reported); the NPC dies here through the ordinary
                        // death path.
                        let entity: u64 = result.detail.parse().expect("server authored kill target");
                        result.detail.clear();
                        result.tick = tick;
                        let progression = r.rules.progression.is_some();
                        let outstanding = settlements.len() + reserved_combat;
                        let identities = ids.len();
                        let mut frozen = None;
                        result.status = match players.get_mut(&id).filter(|p| p.s.generation == g && !p.failed) {
                            None => "stale_session",
                            // As a strike is refused while the realm drains or the session leaves.
                            Some(p) if shutting_down.is_some() || p.leaving.is_some() => "unavailable",
                            Some(p) => match npcs.iter_mut().find(|n| n.entity.id == entity) {
                                None => "unknown_target",
                                Some(npc) => match crate::npc_kill::strike(
                                    npc,
                                    id,
                                    &r.rules,
                                    &mut p.last_kill,
                                    progression.then_some((outstanding, identities)),
                                    p.reward.is_some(),
                                    tick,
                                ) {
                                    Err(reason) => reason,
                                    Ok(()) if progression => {
                                        frozen = Some(npc.entity.id);
                                        "killed"
                                    }
                                    Ok(()) => {
                                        // The legacy kill reward, as a strike's lethal blow starts it.
                                        let op = npc.entity.id;
                                        p.inventory.pending = op;
                                        p.inventory.reward_status = "pending".into();
                                        let db = db.clone();
                                        let owner = owner.clone();
                                        let rules = npc.cycle.as_ref().unwrap_or(&r.rules).clone();
                                        let selected = p.s.clone();
                                        p.reward = Some(tokio::spawn(async move {
                                            db.reward(selected, owner, rules, op).await
                                        }));
                                        "killed"
                                    }
                                },
                            },
                        }
                        .into();
                        if let Some(entity) = frozen {
                            let policy = r.rules.progression.as_deref().unwrap().clone();
                            let claim = ids.pop_front().expect("admitted with an identity");
                            let npc = npcs.iter_mut().find(|n| n.entity.id == entity).unwrap();
                            match encounter_settlement(npc, &r, &policy, &players, &parties, owner.generation, tick, claim, &mut drop_random, &mut group_random) {
                                Ok(settlement) => {
                                    let db = db.clone();
                                    let owner = owner.clone();
                                    settlements.push_back(tokio::spawn(async move {
                                        db.settle(owner, policy, settlement).await
                                    }));
                                }
                                Err(()) => health.invalidate(),
                            }
                        }
                    }
                    if result.status == "show_authorized" || result.status == "hide_authorized" {
                        // PQ-192 (D-153): the holder's show switch, applied
                        // to this session generation only while its
                        // server.inspect lease is current (a revocation since
                        // the authorization, or a stalled read, refuses it).
                        let shown = result.status == "show_authorized";
                        result.status = match players.get_mut(&id).filter(|p| p.s.generation == g) {
                            None => "stale_session",
                            Some(p) => {
                                if !p.turbo.show(shown) {
                                    "denied"
                                } else {
                                    if p.turbo.hidden() {
                                        // Marked at once, as a hidden login is.
                                        presentation.hide(p.s.entity.id);
                                    }
                                    if shown { "shown" } else { "hidden" }
                                }
                            }
                        }
                        .into();
                        result.tick = tick;
                    }
                    if result.status == "committed" {
                        if let Some(ref state) = result.state {
                            if state.revision > revision.revision {
                                revision = state.clone();
                                revision.tick = tick;
                            }
                        }
                        result.status = "applied".into();
                        result.tick = tick;
                    }
                    if let Some(p) = players.get_mut(&id).filter(|p| p.s.generation == g) {
                        deliver(
                            p,
                            Envelope {
                                body: Some(Body::Registry(registry)),
                            },
                        );
                        deliver(
                            p,
                            Envelope {
                                body: Some(Body::AdminResult(result)),
                            },
                        );
                    }
                }
                _ => {
                    health.invalidate();
                    break;
                }
            }
        }
        npcs.retain(|n| {
            n.pending.is_some()
                || n.expires == 0
                || (tick < n.expires && !(n.entity.health == 0 && tick >= n.entity.respawn_tick))
        });
        for (i, npc) in npcs.iter_mut().enumerate() {
            if npc.pending.is_some() {
                continue;
            }
            step_traced(npc, &mut traces, |npc| {
                // PQ-250: a respawn never takes the ids player work keeps.
                let respawn = crate::instance_ids::respawn_allowed(&ids);
                if npc.expires == 0
                    && npc.entity.health == 0
                    && tick >= npc.entity.respawn_tick
                    && respawn
                {
                    let rules = crate::administration::cycle_rules(&r, &revision, i);
                    *npc = crate::gameplay::Npc::spawn(&rules, &r.collision, ids.pop_front().unwrap(), &mut rng);
                    npc.definition_revision = revision.revision;
                    npc.entity.definition_revision = revision.revision;
                    npc.cycle = Some(rules);
                }
                // PQ-249: the NPC's own (template) rules drive its AI, attacks,
                // regeneration and fallback respawn.
                let cycle = npc.cycle.take();
                // PQ-250: a dead NPC waiting on the reserve sees no ids, so its
                // fallback respawn (gameplay.rs) waits too; its corpse still ages.
                let mut waiting = VecDeque::new();
                let starved = npc.entity.health == 0 && !respawn;
                if starved {
                    crate::life::refresh(&mut npc.entity, tick);
                }
                npc.tick(
                    &mut players,
                    cycle.as_ref().unwrap_or(&r.rules),
                    &r.collision,
                    tick,
                    if starved { &mut waiting } else { &mut ids },
                    &mut rng,
                );
                if npc.cycle.is_none() {
                    npc.cycle = cycle;
                }
            });
            if let Some((id, _)) = players
                .iter()
                .find(|(_, p)| p.incoming.as_ref().is_some_and(|v| v.0 == npc.entity.id))
            {
                npc.pending = Some(*id);
            }
        }
        for p in players.values_mut() {
            if let Some(policy) = r.rules.life {
                if p.s.entity.health == 0 && !p.s.dead && p.life_job.is_none() {
                    let target = p.s.clone();
                    let db = db.clone();
                    let owner = owner.clone();
                    p.life_job = Some((
                        0,
                        tokio::spawn(async move {
                            db.transition(owner, target, true, policy.player_delay)
                                .await
                        }),
                    ));
                }
            }
        }
        // PQ-420 (D-217): each held ranged shot lands, holds or is cancelled,
        // after this tick's movement; a landing re-enters the action path at
        // the next command drain, before any network command.
        if health.owned()&&shutting_down.is_none(){
            if let Some(policy)=r.rules.combat_animation.as_ref(){
                for (&id,p) in players.iter_mut(){
                    // PQ-439 (D-223): the arrow in flight first (it may land and
                    // free the slot a newer shot's release waits for), then the
                    // held shot.
                    for flying in [true,false]{
                        let slot=if flying {&p.flight} else {&p.shot};
                        // PQ-444 (D-224): a shot whose release write is pending
                        // waits for it.
                        let Some(shot)=slot.as_ref().filter(|s|!s.landing&&!s.releasing) else {continue};
                        let target=npcs.iter().find(|n|n.entity.id==shot.npc).map(|n|&n.entity);
                        let seen=crate::ranged_shot::Seen{failed:p.failed,generation:p.s.generation,entity:p.s.entity.id,
                            life:p.s.life_revision,health:p.s.entity.health,style:policy.select(p.bag.as_ref()),
                            target,
                            // PQ-467 (D-233): the profile's hold, from where the archer stands.
                            held:target.is_none_or(|t|policy.ranged(shot.style).is_none_or(|v|v.holds(&p.s.entity,t))),
                            // PQ-454 (D-228): a pending reward holds a landing as a write does.
                            busy:p.combat_pending()||p.reward.is_some()||npcs.iter().any(|n|n.entity.id==shot.npc&&n.pending.is_some()),
                            flying:!flying&&p.flight.is_some(),writing:p.combat_pending(),
                            short:p.s.entity.resource<r.rules.cost};
                        match crate::ranged_shot::verdict(shot,&seen,tick){
                            crate::ranged_shot::Verdict::Hold=>{}
                            crate::ranged_shot::Verdict::Land=>{
                                deferred.push_back(Command::Land(id,shot.generation));
                                if flying {p.flight.as_mut()} else {p.shot.as_mut()}.unwrap().landing=true;
                            }
                            crate::ranged_shot::Verdict::Release if shot.spend=>{
                                // PQ-444 (D-224): the release spends the arrow first, in
                                // a durable write of its own (no roll, no wear), as
                                // Ebenezer's flying phase 0046f3f1 removes it through
                                // 004b0792; the shot is released when it commits.
                                let ammo=policy.ammo(shot.style);
                                let (Some((item,count)),Some(wear))=(ammo,r.rules.inventory.as_ref().and_then(|b|b.wear.as_ref())) else {
                                    p.failed=true;health.invalidate();continue;
                                };
                                if ids.is_empty() {continue;} // no event id yet: try next tick (DEFER bounds it)
                                // PQ-454 (D-228): the release pays the basic attack's
                                // cost (verdict checked it), before the arrow, as the
                                // flying phase takes the Msp (0046f4a3) before it
                                // removes the arrow (0046f4b9) and keeps it when the
                                // arrow fails (0046f4c0 -> 0046f509).
                                p.s.entity.resource-=r.rules.cost;
                                if p.bag.as_ref().is_none_or(|bag|crate::wear::ammo_slot(bag,item,count).is_none()) {
                                    // The bag the server holds is already short: refuse it
                                    // without a write (1298's flying phase fails, phase 4).
                                    let shot=p.shot.take().unwrap();
                                    crate::ranged_shot::clear(&mut p.s.entity,shot.started);
                                    deliver(p,Envelope{body:Some(Body::ActionResult(wire::ActionResult{seq:shot.action.seq,status:"no_ammo".into(),target:shot.action.target,damage:0}))});
                                    continue;
                                }
                                match wear.freeze(p.bag.as_ref().unwrap(),ids[0],p.s.entity.id,tick,1,0,Some((item,count))) {
                                    Ok(Some(mut event))=>{
                                        event.id=ids.pop_front().unwrap();
                                        let db=db.clone();let owner=owner.clone();let selected=p.s.clone();
                                        let bag=r.rules.inventory.as_deref().cloned().unwrap();let reward=r.rules.item.clone();
                                        let held=p.shot.as_mut().unwrap();
                                        held.releasing=true;
                                        p.wear=Some(WearJob{ammo:true,release:true,style:held.style,interval:0,moving:false,started:held.started,
                                            cast:Some(held.started),paid:false,npc:held.npc,action:None,outcome:crate::damage::Outcome{hit:false,damage:0},claim:0,
                                            job:tokio::spawn(async move{db.wear(owner,selected,bag,reward,event).await})});
                                    }
                                    _=>{p.failed=true;health.invalidate();}
                                }
                            }
                            crate::ranged_shot::Verdict::Release=>{
                                // No roll and no durable write: the arrow leaves,
                                // paying the basic attack's cost (PQ-454, D-228).
                                p.s.entity.resource-=r.rules.cost;
                                let shot=p.shot.take().unwrap();
                                let target=npcs.iter().find(|n|n.entity.id==shot.npc).map(|n|n.entity.clone()).unwrap();
                                fly(p,shot,&target,tick,r.protocol,&mut presentation);
                            }
                            crate::ranged_shot::Verdict::Cancel(status)=>{
                                let shot=if flying {p.flight.take()} else {p.shot.take()}.unwrap();
                                // A cast that never left is cleared; a released
                                // one keeps its strike fields (its clip played).
                                if !shot.released {crate::ranged_shot::clear(&mut p.s.entity,shot.started);}
                                deliver(p,Envelope{body:Some(Body::ActionResult(wire::ActionResult{seq:shot.action.seq,status:status.into(),target:shot.action.target,damage:0}))});
                            }
                        }
                    }
                }
            }
        }
        if health.owned()&&shutting_down.is_none(){
            if let Some(policy)=&r.rules.skills{
                let impacts=skill_runtime.tick(&mut players,&mut npcs,policy,tick,&db,&owner,&mut presentation,&mut rng,settlements.len()+reserved_combat,&mut ids).await;
                reserved_combat+=impacts.len();deferred.extend(impacts);
            }
        }
        // PQ-184 (D-152): every tick, so the history marks a withheld session's
        // events and drops its old ids from targets before it can leave unmarked.
        let hidden = withhold(&mut presentation, &mut players, npcs.iter_mut().map(|n| &mut n.entity));
        // Do not publish a lethal hit or replacement before its transaction commits.
        // The worker is bounded; an unavailable database closes realm admission.
        if tick % 2 == 0 && health.owned() && players.values().all(|p| p.life_job.is_none()) {
            let actors:Vec<_>=players.values().filter(|p|!p.failed).map(|p|p.s.entity.clone()).chain(npcs.iter().map(|n|n.entity.clone())).collect();
            presentation.observe(tick,&actors);
            if r.rules.party.is_some(){
                for (&id,p) in &players{if p.failed{parties.leave(id);}}
                let snapshots:Vec<_>=players.keys().map(|&id|(id,party_view(&parties,&players,id,&r.rules))).collect();
                for (id,state) in snapshots {let p=players.get_mut(&id).unwrap();if !p.failed&&p.party_view.as_ref()!=Some(&state){p.party_view=Some(state.clone());let mut sent=state;sent.tick=tick;deliver(p,Envelope{body:Some(Body::PartyState(sent))});}}
            }
            if !traces.is_empty() {
                traces.retain(|e| npcs.iter().any(|n| n.entity.id == e));
            }
            // PQ-250: the NPCs of each interest cell and each one's view bytes,
            // once per view; a session plans its view from these and copies
            // only what it keeps (view_frame.rs, D-163).
            let cell = r.rules.interest_cell;
            let cell_of = |e: &wire::Entity| ((e.x / cell).floor() as i32, (e.z / cell).floor() as i32);
            let mut by_cell: std::collections::HashMap<(i32, i32), Vec<usize>> = Default::default();
            let mut npc_bytes = vec![0usize; npcs.len()];
            for (i, npc) in npcs.iter().enumerate() {
                if npc.entity.life_state != wire::LifeState::Dormant as i32 {
                    by_cell.entry(cell_of(&npc.entity)).or_default().push(i);
                    npc_bytes[i] = crate::view_frame::element(npc.entity.encoded_len());
                }
            }
            let mut unsendable = Vec::new();
            for p in players.values() {
                if p.failed {
                    continue;
                }
                let viewer = &p.s.entity;
                let mut seen: Vec<wire::Entity> = players
                    .values()
                    .filter(|q| near(viewer, &q.s.entity, cell))
                    .map(|q| { let mut e=q.s.entity.clone(); e.appearance=r.appearance.project(q.bag.as_ref()); e.combat_style=r.rules.combat_animation.as_ref().map_or(0,|policy|policy.select(q.bag.as_ref())); e })
                    .collect();
                conceal(viewer, p.turbo.inspecting(), &hidden, &mut seen);
                // The nine cells around the viewer, in the simulation's NPC order.
                let (cx, cz) = cell_of(viewer);
                let mut nearby: Vec<usize> = (-1..=1)
                    .flat_map(|dx| (-1..=1).map(move |dz| (cx + dx, cz + dz)))
                    .filter_map(|c| by_cell.get(&c))
                    .flatten()
                    .copied()
                    .collect();
                nearby.sort_unstable();
                let distance = |e: &wire::Entity| (e.x - viewer.x).powi(2) + (e.z - viewer.z).powi(2);
                let mut others: Vec<crate::view_frame::Candidate> = seen
                    .iter()
                    .filter(|e| e.id != viewer.id)
                    .map(|e| (distance(e), e.id, crate::view_frame::element(e.encoded_len())))
                    .chain(nearby.iter().map(|&i| (distance(&npcs[i].entity), npcs[i].entity.id, npc_bytes[i])))
                    .collect();
                let events = presentation.view(viewer, cell, p.turbo.inspecting());
                let mut world = wire::World {
                    traces: vec![],
                    events,event_cursor:presentation.cursor,
                    skill_cooldowns:skill_runtime.view(p.s.id,tick),
                    inventory: Some(p.inventory.clone()),
                    action: r.rules.action.clone(),
                    speed: if r.protocol >= 7 {
                        r.rules
                            .movement
                            .unwrap()
                            .speed(p.s.entity.movement_mode)
                            .unwrap()
                            * if p.turbo.active {
                                r.turbo_multiplier
                            } else {
                                1.
                            }
                    } else {
                        r.rules.speed
                    },
                    turbo_allowed: p.turbo.permitted(),
                    permission_generation: p.turbo.generation,
                    stats: p.stats.clone(),
                    max_health: p.stats.as_ref().map_or(r.rules.health, |s| s.max_health),
                    max_resource: p
                        .stats
                        .as_ref()
                        .map_or(r.rules.resource, |s| s.max_resource),
                    tick,
                    session: p.s.generation as u64,
                    self_: p.s.entity.id,
                    entities: seen.iter().filter(|e| e.id == viewer.id).cloned().collect(),
                    revision: Some(revision.clone()),
                };
                // PQ-250 (D-163): a crowded window keeps the nearest entities
                // that fit one frame; a view that cannot fit closes the session.
                let inspecting = p.turbo.inspecting();
                let reserve = if inspecting { crate::view_frame::TRACE_RESERVE } else { 0 };
                let (fit, keep) = crate::view_frame::plan(&mut world, viewer.id, &mut others, reserve);
                if fit != crate::view_frame::Fit::Over {
                    let mut entities: Vec<wire::Entity> = seen.into_iter().filter(|e| keep.contains(&e.id)).collect();
                    for &i in &nearby {
                        if keep.contains(&npcs[i].entity.id) {
                            let mut e = npcs[i].entity.clone();
                            clear_targets(viewer, inspecting, &hidden, &mut e);
                            entities.push(e);
                        }
                    }
                    world.entities = entities;
                    // PQ-186: only a session whose server.inspect lease is current
                    // gets the state of traced NPCs, and only of those it sees.
                    world.traces = if inspecting { traces.report(&world.entities) } else { vec![] };
                }
                // The plan counts upper bounds; the real frame is checked too.
                if fit == crate::view_frame::Fit::Over
                    || crate::view_frame::frame_len(&mut world) > crate::view_frame::LIMIT
                {
                    metrics.views_over.fetch_add(1, Ordering::Relaxed);
                    unsendable.push(p.s.id);
                    continue;
                }
                if matches!(fit, crate::view_frame::Fit::Trimmed { .. }) {
                    metrics.views_trimmed.fetch_add(1, Ordering::Relaxed);
                }
                p.view.send_replace(Some(world));
            }
            for id in unsendable.drain(..) {
                let p = players.get_mut(&id).unwrap();
                p.failed = true;
                p.view.send_replace(None);
            }
        }
        if checkpoint.as_ref().is_some_and(|t| t.is_finished()) {
            let result = checkpoint.take().unwrap().await;
            if !matches!(result, Ok(Ok(()))) {
                health.invalidate();
            } else {
                durable_at = saved_at;
                metrics.checkpoints.fetch_add(1, Ordering::Relaxed);
            }
        }
        // Track the age of the last committed snapshot, including slow consecutive
        // writes, rather than assuming every previous checkpoint committed instantly.
        if durable_at.elapsed().as_secs_f32() > 4.
            || (checkpoint.is_some() && saved_at.elapsed().as_secs_f32() > 2.5)
        {
            health.invalidate();
        }
        if checkpoint.is_none() && saved_at.elapsed().as_secs_f32() >= 2. {
            saved_at = Instant::now();
            let positions = players
                .values()
                .filter(|p| p.life_job.is_none())
                .map(|p| (p.s.clone(), true))
                .collect();
            let db = db.clone();
            let owner = owner.clone();
            checkpoint = Some(tokio::spawn(async move { db.save(owner, positions).await }));
        }
        metrics
            .sessions
            .store(players.len() as u64, Ordering::Relaxed);
        let elapsed = start.elapsed().as_micros() as u64;
        metrics.tick_us.store(elapsed, Ordering::Relaxed);
        metrics.npcs.store(npcs.len() as u64, Ordering::Relaxed);
        metrics.ids.store(ids.len() as u64, Ordering::Relaxed);
        window = (window.0.max(elapsed), window.1.max(queued), window.2 + 1);
        if window.2 >= WINDOW {
            metrics.tick_max_us.store(window.0, Ordering::Relaxed);
            metrics.queue_max.store(window.1, Ordering::Relaxed);
            window = (0, 0, 0);
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reliable_overflow_disconnects_and_snapshot_slot_coalesces() {
        let (out, _rx) = mpsc::channel(1);
        let (view, rx) = watch::channel(None);
        let mut p = Player {
            rest: Default::default(),
            wear: None,
            storage: None, consume: None,
            incoming: None,
            leaving: None,
            bag: None,
            stats: None,
            s: Selected {
                id: 1,
                generation: 1,
                life_revision: 0,
                dead: false,
                ready_ticks: 0,
                entity: wire::Entity::default(),
            },
            inventory: Default::default(),
            reward: None,
            life_job: None,
            last_action: 0, skill_hit: 0,
            last_respawn: 0,
            last_claim: 0,
            claim: None,
            next_action: 0,
            out,
            view,
            moves: Default::default(),
            last_seq: 0,
            last_motion: 0,
            turbo: Default::default(),
            last_chat: 0, last_record: 0, last_kill: 0,
            last_friend_presence:0, last_friend_sequence:0, last_party_sequence:0, party_view:None,
            shot: None, flight: None,
            failed: false,
        };
        for tick in 1..1000 {
            p.view.send_replace(Some(wire::World {
                tick,
                ..Default::default()
            }));
        }
        assert_eq!(rx.borrow().as_ref().unwrap().tick, 999);
        deliver(&mut p, crate::network::error(4, "test"));
        deliver(&mut p, crate::network::error(4, "test"));
        assert!(p.failed);
        assert!(rx.borrow().is_none());
    }
    #[test]
    fn operator_chat_mark_follows_lease_and_view() {
        // PQ-178: only a sender whose server.inspect lease is current is marked;
        // a private line also needs the sender in the recipient's interest area.
        let read = |generation, inspect| crate::turbo::Authority {
            id: 1,
            session: 1,
            generation,
            allowed: false,
            inspect,
        };
        let sender = wire::Entity::default();
        let beside = sender.clone();
        let mut far = sender.clone();
        far.x = 5.;
        let mut lease = crate::turbo::State::default();
        assert!(!operator_line(lease.inspecting(), &sender, None, true, 1.), "no read yet");
        lease.apply(&read(1, false), Instant::now());
        assert!(!operator_line(lease.inspecting(), &sender, None, true, 1.), "a player");
        lease.apply(&read(2, true), Instant::now());
        assert!(operator_line(lease.inspecting(), &sender, None, true, 1.));
        assert!(operator_line(lease.inspecting(), &sender, Some(&beside), true, 1.));
        assert!(!operator_line(lease.inspecting(), &sender, Some(&far), true, 1.), "out of view");
        // PQ-184: never marked for a recipient that may not see the sender.
        assert!(!operator_line(lease.inspecting(), &sender, Some(&beside), false, 1.), "hidden sender");
        assert!(operator_line(lease.inspecting(), &sender, None, false, 1.), "a local line");
        // A revocation's read unmarks the next line; an older read never re-marks.
        lease.apply(&read(3, false), Instant::now());
        assert!(!operator_line(lease.inspecting(), &sender, None, true, 1.));
        lease.apply(&read(2, true), Instant::now());
        assert!(!operator_line(lease.inspecting(), &sender, None, true, 1.));
        // A lease the authority read stops renewing lapses (a stalled database).
        lease.apply(&read(4, true), Instant::now() - crate::turbo::LEASE);
        assert!(!operator_line(lease.inspecting(), &sender, None, true, 1.));
    }
    #[test]
    fn hidden_operator_is_concealed_from_ordinary_observers() {
        // PQ-184: the World an observer gets, built from the authority leases.
        let read = |id, inspect| crate::turbo::Authority { id, session: 1, generation: 1, allowed: false, inspect };
        let player = |id: i64, inspect: Option<bool>| {
            let mut p = test_player();
            p.s.id = id;
            p.s.entity.id = 100 + id as u64;
            p.s.entity.name = format!("P{id}");
            match inspect {
                Some(inspect) => p.turbo.apply(&read(id, inspect), Instant::now()),
                None => p.turbo = Default::default(),
            }
            p
        };
        let mut players = BTreeMap::new();
        for (id, inspect) in [(1, Some(true)), (2, Some(false)), (3, Some(true)), (4, None)] {
            players.insert(id, player(id, inspect));
        }
        let mut history = crate::presentation::Events::default();
        history.push(wire::PresentationEvent { actor: 7, target: 101, kind: 2, ..Default::default() });
        history.push(wire::PresentationEvent { actor: 101, target: 101, kind: 1, ..Default::default() });
        history.push(wire::PresentationEvent { actor: 7, target: 102, kind: 2, ..Default::default() });
        let hidden = withhold(&mut history, &mut players, std::iter::empty());
        assert_eq!(hidden, vec![101, 103, 104], "operators and an unread session");
        let npc = wire::Entity { id: 7, npc: true, strike_target: 101, cast_target: 0, ..Default::default() };
        let caster = wire::Entity { id: 102, cast_target: 101, ..Default::default() };
        let view = |observer: i64| {
            let p = &players[&observer];
            let mut entities: Vec<_> = players.values().map(|q| q.s.entity.clone()).collect();
            entities[1] = caster.clone();
            entities.push(npc.clone());
            conceal(&p.s.entity, p.turbo.inspecting(), &hidden, &mut entities);
            (entities, history.view(&p.s.entity, 1., p.turbo.inspecting()))
        };
        // An ordinary observer: no operator, no unread session, no id or event naming one.
        let (entities, events) = view(2);
        assert_eq!(entities.iter().map(|e| e.id).collect::<Vec<_>>(), vec![102, 7]);
        assert!(entities.iter().all(|e| e.strike_target == 0 && e.cast_target == 0));
        assert_eq!(events.iter().map(|e| e.target).collect::<Vec<_>>(), vec![102]);
        // An operator sees the other operator and everyone else, ids and events intact.
        let (entities, events) = view(1);
        assert_eq!(entities.iter().map(|e| e.id).collect::<Vec<_>>(), vec![101, 102, 103, 104, 7]);
        assert_eq!((entities[4].strike_target, entities[1].cast_target, events.len()), (101, 101, 3));
        // An unread session sees itself only among the withheld ones.
        let (entities, _) = view(4);
        assert_eq!(entities.iter().map(|e| e.id).collect::<Vec<_>>(), vec![102, 104, 7]);
        // Name lookups: the ordinary observer finds no operator, even case-folded;
        // the operator finds both.
        let viewer = &players[&2];
        assert!(friend_target(&players, "P1", |o| viewer.sees(o)).is_none());
        assert!(friend_target(&players, "p3", |o| viewer.sees(o)).is_none());
        assert_eq!(friend_target(&players, "p2", |o| viewer.sees(o)).map(|p| p.s.id), Some(2));
        let operator = &players[&1];
        assert_eq!(friend_target(&players, "P3", |o| operator.sees(o)).map(|p| p.s.id), Some(3));
        assert_eq!(friend_target(&players, "P2", |o| operator.sees(o)).map(|p| p.s.id), Some(2));
        // A hidden operator cannot make a case-folded name ambiguous for the observer.
        let mut twin = player(5, Some(true));
        twin.s.entity.name = "p2".into();
        players.insert(5, twin);
        let viewer = &players[&2];
        assert_eq!(friend_target(&players, "P2", |o| viewer.sees(o)).map(|p| p.s.id), Some(2));
        let mut other = player(6, Some(false));
        other.s.entity.name = "P6".into();
        players.insert(6, other);
        let viewer = &players[&6];
        assert_eq!(friend_target(&players, "P2", |o| viewer.sees(o)).map(|p| p.s.id), Some(2));
        // A skill aimed at the operator's entity finds nothing for the observer,
        // the operator's own entity for the second holder, and the observer for both.
        assert!(action_target(&[], &players, 2, 101).is_none());
        assert_eq!(action_target(&[], &players, 3, 101).map(|e| e.id), Some(101));
        assert_eq!(action_target(&[], &players, 1, 102).map(|e| e.id), Some(102));
        assert!(action_target(&[], &players, 9, 102).is_none(), "no such actor");
        // A revocation's read makes the operator visible to the ordinary observer.
        players.get_mut(&1).unwrap().turbo.apply(&crate::turbo::Authority { generation: 2, ..read(1, false) }, Instant::now());
        let viewer = &players[&2];
        assert!(viewer.sees(&players[&1]));
        assert_eq!(friend_target(&players, "P1", |o| viewer.sees(o)).map(|p| p.s.id), Some(1));
        assert_eq!(action_target(&[], &players, 2, 101).map(|e| e.id), Some(101));
    }
    #[test]
    fn departed_hidden_operator_leaves_no_trace() {
        // PQ-184 (attempt 2): the presentation history (40 ticks) and an NPC's
        // strike target outlive the snapshot in which a session was withheld.
        // After it leaves, takes a new entity id, or is revealed, an ordinary
        // observer's next view must still name none of its withheld ids.
        use crate::presentation::Events;
        let read = |id, generation, inspect| crate::turbo::Authority { id, session: 1, generation, allowed: false, inspect };
        let player = |id: i64, inspect: bool| {
            let mut p = test_player();
            p.s.id = id;
            p.s.entity.id = 100 + id as u64;
            p.turbo.apply(&read(id, 1, inspect), Instant::now());
            p
        };
        let mut players: BTreeMap<i64, Player> =
            [(1, player(1, true)), (2, player(2, false)), (3, player(3, true))].into_iter().collect();
        let mut npc = wire::Entity { id: 7, npc: true, ..Default::default() };
        let mut history = Events::default();
        let names = |events: &[wire::PresentationEvent], id: u64| events.iter().any(|e| e.actor == id || e.target == id);
        // The observer's next World: what conceal and the history leave it.
        let world = |history: &Events, players: &BTreeMap<i64, Player>, npc: &wire::Entity, hidden: &[u64], id: i64| {
            let p = &players[&id];
            let mut entities: Vec<_> = players.values().map(|q| q.s.entity.clone()).collect();
            entities.push(npc.clone());
            conceal(&p.s.entity, p.turbo.inspecting(), hidden, &mut entities);
            (entities, history.view(&p.s.entity, 1., p.turbo.inspecting()))
        };
        assert_eq!(withhold(&mut history, &mut players, std::iter::once(&mut npc)), vec![101, 103]);
        // The hidden operator 1 consumes an item and the NPC strikes it.
        history.consumed(10, &players[&1].s.entity, "demo:item/test".into());
        npc.strike_target = 101;
        npc.strike_tick = 10;
        history.observe(10, &[players[&1].s.entity.clone(), npc.clone()]);
        // On its way out its cast is cancelled (kind 5) between two ticks; then it leaves.
        history.push(wire::PresentationEvent { tick: 11, actor: 101, target: 101, kind: 5, ..Default::default() });
        players.remove(&1);
        let hidden = withhold(&mut history, &mut players, std::iter::once(&mut npc));
        assert_eq!(hidden, vec![103]);
        assert_eq!(npc.strike_target, 0, "the departed id is cleared from the NPC");
        let (entities, events) = world(&history, &players, &npc, &hidden, 2);
        assert!(!names(&events, 101) && events.is_empty());
        assert!(entities.iter().all(|e| e.id != 101 && e.strike_target != 101 && e.cast_target != 101));
        // A holder still gets the three events the operator left in the history.
        assert_eq!(world(&history, &players, &npc, &hidden, 3).1.len(), 3);
        // The hidden operator 3 is struck, then respawns under a new entity id.
        npc.strike_target = 103;
        npc.strike_tick = 12;
        history.observe(12, &[players[&3].s.entity.clone(), npc.clone()]);
        players.get_mut(&2).unwrap().s.entity.cast_target = 103;
        players.get_mut(&3).unwrap().s.entity.id = 203;
        let hidden = withhold(&mut history, &mut players, std::iter::once(&mut npc));
        assert_eq!(hidden, vec![203]);
        assert_eq!((npc.strike_target, players[&2].s.entity.cast_target), (0, 0));
        let (entities, events) = world(&history, &players, &npc, &hidden, 2);
        assert!(events.is_empty() && entities.iter().all(|e| ![103, 203].contains(&e.id)));
        // A hidden session admitted, acting and leaving between two ticks.
        players.insert(4, player(4, true));
        history.hide(104);
        history.consumed(13, &players[&4].s.entity, "demo:item/test".into());
        players.remove(&4);
        let hidden = withhold(&mut history, &mut players, std::iter::once(&mut npc));
        assert!(world(&history, &players, &npc, &hidden, 2).1.is_empty());
        // A revealed operator: what it did while withheld stays withheld; what it
        // does once visible is shown.
        players.insert(5, player(5, true));
        withhold(&mut history, &mut players, std::iter::once(&mut npc));
        history.consumed(14, &players[&5].s.entity, "demo:item/before".into());
        players.get_mut(&5).unwrap().turbo.apply(&read(5, 2, false), Instant::now());
        let hidden = withhold(&mut history, &mut players, std::iter::once(&mut npc));
        assert_eq!(hidden, vec![203]);
        history.consumed(15, &players[&5].s.entity, "demo:item/after".into());
        let (entities, events) = world(&history, &players, &npc, &hidden, 2);
        assert!(entities.iter().any(|e| e.id == 105));
        assert_eq!(events.iter().map(|e| e.key.as_str()).collect::<Vec<_>>(), vec!["demo:item/after"]);
        // The history drops events after 40 ticks; the withheld ids it keeps are
        // only the sessions withheld now.
        history.observe(60, &[]);
        assert!(world(&history, &players, &npc, &hidden, 3).1.is_empty());
        assert!(history.withhold(&[]).iter().eq([203].iter()));
        assert!(history.withhold(&[]).is_empty());
    }
    #[test]
    fn shown_operator_is_an_ordinary_player_until_hidden() {
        // PQ-192 (D-153): a holder that chose `show` passes every PQ-184 filter
        // as a player does; `hide` withholds it and its kept events again.
        use crate::presentation::Events;
        let player = |id: i64, inspect: bool| {
            let mut p = test_player();
            p.s.id = id;
            p.s.entity.id = 100 + id as u64;
            p.s.entity.name = format!("P{id}");
            p.test_lease(inspect);
            p
        };
        let mut players: BTreeMap<i64, Player> = [(1, player(1, true)), (2, player(2, false))].into_iter().collect();
        let mut history = Events::default();
        let world = |history: &Events, players: &BTreeMap<i64, Player>, hidden: &[u64]| {
            let p = &players[&2];
            let mut entities: Vec<_> = players.values().map(|q| q.s.entity.clone()).collect();
            conceal(&p.s.entity, p.turbo.inspecting(), hidden, &mut entities);
            (entities.iter().any(|e| e.id == 101), history.view(&p.s.entity, 1., false).len())
        };
        assert_eq!(withhold(&mut history, &mut players, std::iter::empty()), vec![101], "hidden by default");
        // A non-holder cannot use the switch.
        assert!(!players.get_mut(&2).unwrap().turbo.show(true));
        // Shown: in the observer's World and lookups, an NPC may pick it, and it
        // still sees hidden actors.
        assert!(players.get_mut(&1).unwrap().turbo.show(true));
        let hidden = withhold(&mut history, &mut players, std::iter::empty());
        assert!(hidden.is_empty() && !players[&1].hidden());
        history.consumed(10, &players[&1].s.entity, "demo:item/shown".into());
        assert_eq!(world(&history, &players, &hidden), (true, 1));
        assert!(players[&2].sees(&players[&1]));
        assert_eq!(friend_target(&players, "P1", |o| players[&2].sees(o)).map(|p| p.s.id), Some(1));
        assert_eq!(action_target(&[], &players, 2, 101).map(|e| e.id), Some(101));
        players.insert(3, player(3, true));
        assert!(players[&1].sees(&players[&3]) && !players[&2].sees(&players[&3]));
        players.remove(&3);
        // Hidden again: withheld from the observer, with the events it made while
        // shown (marked at once by `hide`, as the simulation does).
        let operator = players.get_mut(&1).unwrap();
        assert!(operator.turbo.show(false) && operator.hidden());
        history.hide(101);
        assert_eq!(world(&history, &players, &[101]).1, 0, "the shown period's event");
        let hidden = withhold(&mut history, &mut players, std::iter::empty());
        assert_eq!(hidden, vec![101]);
        assert_eq!(world(&history, &players, &hidden), (false, 0));
        assert!(friend_target(&players, "P1", |o| players[&2].sees(o)).is_none());
        // A revocation resets the switch: the regrant hides it again.
        let operator = players.get_mut(&1).unwrap();
        assert!(operator.turbo.show(true));
        operator.test_lease(false);
        assert!(!operator.turbo.shown && !operator.hidden());
        operator.test_lease(true);
        assert!(operator.hidden(), "the regrant hides the operator");
    }
    #[test]
    fn party_names_skip_hidden_operators_outside_the_group() {
        // PQ-184: a non-leader's removal of a hidden operator's name must answer
        // as for an absent name (not_member), not not_leader; a leader still
        // removes a hidden member; a hidden namesake makes no name ambiguous.
        let read = |id, inspect| crate::turbo::Authority { id, session: 1, generation: 1, allowed: false, inspect };
        let mut players = BTreeMap::new();
        for (id, name, inspect) in [(1, "Op", true), (2, "Lead", false), (3, "Mem", false), (4, "mem", true), (5, "Hid", true), (6, "Vis", false)] {
            let mut p = test_player();
            p.s.id = id;
            p.s.entity.id = 100 + id as u64;
            p.s.entity.name = name.into();
            p.inventory.level = 30;
            p.turbo.apply(&read(id, inspect), Instant::now());
            players.insert(id, p);
        }
        let policy = crate::party::Policy { capacity: 8, name_bytes: 20, minimum: 2.0 / 3.0, maximum: 1.5, gap: 8, repeat_ticks: 60 };
        let mut parties = crate::party::Parties::default();
        let actors = party_actors(&players);
        for member in [3, 5] {
            assert_eq!(parties.invite(&policy, &actors, 2, member, 1), "invited");
            let token = parties.invitation(member).unwrap().token;
            assert_eq!(parties.answer(&actors, member, token, true), "joined");
        }
        let remove = |parties: &mut crate::party::Parties, id, name: &str| {
            party_target(parties, &players, id, name).map_or("not_member", |t| parties.remove(id, t))
        };
        // The non-leader 3 asks about the hidden Op: as for an absent name.
        assert_eq!(remove(&mut parties, 3, "Op"), "not_member");
        assert_eq!(remove(&mut parties, 3, "Nobody"), "not_member");
        assert_eq!(remove(&mut parties, 3, "Vis"), "not_leader", "a visible non-member");
        assert_eq!(remove(&mut parties, 3, "Lead"), "not_leader", "a visible member (the leader)");
        // The hidden "mem" outside the group makes "MEM" no ambiguity for the leader.
        assert_eq!(party_target(&parties, &players, 2, "MEM"), Some(3));
        // The leader still removes its hidden member.
        assert_eq!(party_target(&parties, &players, 2, "Hid"), Some(5));
        assert_eq!(remove(&mut parties, 2, "Hid"), "removed");
        assert_eq!(party_target(&parties, &players, 2, "Hid"), None);
    }
    #[test]
    fn grid_negative_and_boundary() {
        let a = wire::Entity::default();
        let mut b = a.clone();
        b.x = 1.99;
        assert!(near(&a, &b, 1.));
        b.x = 2.;
        assert!(!near(&a, &b, 1.));
        b.x = 30.;
        assert!(near(&a, &b, 24.));
        b.x = 48.;
        assert!(!near(&a, &b, 24.));
        b.x = -1.01;
        assert!(!near(&a, &b, 1.));
    }
    /// PQ-186: a traced NPC that a player damaged keeps its trace when the
    /// encounter reset gives it a new entity id at home, and again when it
    /// respawns after death (KO's mark lasts for the NPC object's life).
    #[test]
    fn trace_follows_a_reidentified_npc() {
        let mut r = crate::rules::Rules::load(
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
        let mut npc = crate::gameplay::Npc::new(&r, &ground, 20);
        let mut traces = crate::npc_trace::Marks::default();
        assert_eq!(traces.mark((1, 1), 20, true), "traced");
        // Damaged by a player, then back home: the reset heals it under id 21.
        npc.ledger.credit(1, 10, r.npc_health).unwrap();
        npc.entity.health = r.npc_health - 10;
        npc.entity.behavior = "return".into();
        let mut players = BTreeMap::new();
        let mut ids: VecDeque<u64> = [21, 22].into();
        let mut rng = crate::damage::Random::seeded(1);
        step_traced(&mut npc, &mut traces, |npc| {
            npc.tick(&mut players, &r, &ground, 2, &mut ids, &mut rng)
        });
        assert_eq!((npc.entity.id, npc.entity.health), (21, r.npc_health));
        let report = traces.report(std::slice::from_ref(&npc.entity));
        assert_eq!(report.len(), 1, "the reset dropped the trace");
        assert_eq!((report[0].entity, report[0].state.as_str()), (21, npc.entity.behavior.as_str()));
        assert!(traces.report(&[wire::Entity { id: 20, npc: true, ..Default::default() }]).is_empty());
        // Killed, then respawned under id 22: still traced.
        npc.entity.health = 0;
        npc.entity.respawn_tick = 3;
        step_traced(&mut npc, &mut traces, |npc| {
            npc.tick(&mut players, &r, &ground, 3, &mut ids, &mut rng)
        });
        assert_eq!(npc.entity.id, 22);
        assert_eq!(traces.report(std::slice::from_ref(&npc.entity)).len(), 1, "the respawn dropped the trace");
    }
    /// PQ-404 (D-207, amending D-014): one command drain admits two valid
    /// movements and refuses a third with code 4 without consuming its seq;
    /// each tick applies one, so the held movement applies on the next tick
    /// with its ack, and no tick moves a session farther than one step.
    #[test]
    fn a_held_movement_applies_next_tick_and_a_third_is_refused() {
        let mut rules = crate::rules::Rules::load(
            std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"),
            "demo",
        )
        .unwrap();
        rules.movement = Some(crate::movement::Config {
            walk: 1.5,
            run: 4.5,
            backward: 1.5,
            ..Default::default()
        });
        let ground = [
            [-20., 0., -20.],
            [20., 0., -20.],
            [20., 0., 20.],
            [-20., 0., -20.],
            [20., 0., 20.],
            [-20., 0., 20.],
        ];
        let r = Release {
            appearance: Default::default(),
            assets: BTreeMap::new(),
            properties: Vec::new(),
            turbo_multiplier: 1.,
            protocol: 2,
            game: "demo".into(),
            hash: String::new(),
            collision: crate::movement::Collision::soup(ground.to_vec()).unwrap(),
            rules,
        };
        let metrics = Metrics::new();
        let mut p = test_player();
        let mut out = p.test_output();
        let mv = |seq: u64| wire::Move { session: 1, seq, z: -1., ..Default::default() };
        // PQ-405 (D-208): every movement refusal names the Move it answers.
        let refused = |out: &mut mpsc::Receiver<Envelope>| -> Vec<(i32, String)> {
            std::iter::from_fn(|| out.try_recv().ok())
                .filter_map(|e| match e.body {
                    Some(Body::Error(e)) => {
                        assert_eq!(e.request, crate::network::request::MOVE, "{e:?}");
                        Some((e.code, e.detail))
                    }
                    _ => None,
                })
                .collect()
        };
        let step = 1.5 * 0.05;
        let at = |p: &Player| (p.s.entity.ack, p.s.entity.z);
        let near = |(ack, z): (u64, f32), (want_ack, steps): (u64, f32)| {
            ack == want_ack && (z + steps * step).abs() < 1e-5
        };
        // Tick 1's drain: three valid movements; the third is refused.
        for seq in 1..=3 {
            admit_movement(&mut p, &metrics, &r, 1, mv(seq), 1);
        }
        assert_eq!(refused(&mut out), vec![(4, "one movement per tick".to_string())]);
        assert_eq!(metrics.rejected.load(Ordering::Relaxed), 1);
        assert_eq!(p.last_seq, 2, "the held movement consumed its seq, the refused one did not");
        apply_movement(&mut p, &r, 1);
        assert!(near(at(&p), (1, 1.)), "{:?}", at(&p));
        // Tick 2's drain: the refused seq is still free and is held behind seq 2.
        admit_movement(&mut p, &metrics, &r, 1, mv(3), 2);
        assert!(refused(&mut out).is_empty());
        apply_movement(&mut p, &r, 2);
        assert!(near(at(&p), (2, 2.)), "{:?}", at(&p));
        // Tick 3's drain brings nothing: the held movement applies with its ack.
        apply_movement(&mut p, &r, 3);
        assert!(near(at(&p), (3, 3.)), "{:?}", at(&p));
        // The queue is empty: no movement and no ack change.
        apply_movement(&mut p, &r, 4);
        assert!(near(at(&p), (3, 3.)), "{:?}", at(&p));
        // A seq at or below the last admitted one is stale (code 3) and queues nothing.
        admit_movement(&mut p, &metrics, &r, 1, mv(3), 5);
        assert_eq!(refused(&mut out), vec![(3, "invalid/stale movement or session".to_string())]);
        apply_movement(&mut p, &r, 5);
        assert!(near(at(&p), (3, 3.)), "{:?}", at(&p));
        // A respawn or a cast drops both queued inputs; the held one never applies.
        admit_movement(&mut p, &metrics, &r, 1, mv(4), 6);
        admit_movement(&mut p, &metrics, &r, 1, mv(5), 6);
        assert!(refused(&mut out).is_empty());
        assert_eq!(p.moves.clear(), Some(5));
        apply_movement(&mut p, &r, 6);
        apply_movement(&mut p, &r, 7);
        assert!(near(at(&p), (3, 3.)), "{:?}", at(&p));
        assert!(!p.failed);
    }
}

impl Player {
    /// Test only (PQ-447): this session's own strike's pending wear write (an
    /// arrow's arrival), a pending incoming hit's write and a pending reward,
    /// each or none.
    #[cfg(test)]
    pub(crate) fn test_pending(&mut self, arrival: bool, incoming: bool, reward: bool) {
        let outcome = crate::damage::Outcome { hit: true, damage: 0 };
        self.wear = arrival.then(|| WearJob {
            ammo: true, release: false, style: 2, interval: 0, moving: false, started: 0, cast: Some(0), paid: true, npc: 77,
            action: Some(wire::Action { seq: 1, target: 77, ..Default::default() }), outcome: outcome.clone(), claim: 0,
            job: tokio::spawn(std::future::pending()),
        });
        self.incoming = incoming.then(|| (0, outcome,
            crate::wear::Event { id: 0, revision: 0, source: 0, tick: 0, mode: 0, damage: 0, records: vec![], ammo: None }));
        self.reward = reward.then(|| tokio::spawn(std::future::pending()));
    }
}

#[cfg(test)]
pub(crate) fn test_player() -> Player {
    let (out, _) = mpsc::channel(32);
    let (view, _) = watch::channel(None);
    Player {
        rest: Default::default(),
        wear: None,
        storage: None, consume: None,
        incoming: None,
        leaving: None,
        bag: None,
        stats: None,
        s: Selected {
            id: 1,
            generation: 1,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            entity: wire::Entity {
                health: 30,
                ..Default::default()
            },
        },
        out,
        view,
        moves: Default::default(),
        last_seq: 0,
        last_motion: 0,
        // An ordinary session with an applied read: visible (PQ-184) and
        // targetable by NPCs (PQ-193). Its lease lapses, which keeps it visible.
        turbo: {
            let mut lease = crate::turbo::State::default();
            lease.apply(&crate::turbo::Authority { id: 1, session: 1, generation: 0, allowed: false, inspect: false }, Instant::now());
            lease
        },
        last_chat: 0, last_record: 0, last_kill: 0,
        last_friend_presence:0, last_friend_sequence:0, last_party_sequence:0, party_view:None,
        shot: None, flight: None,
        failed: false,
        inventory: Default::default(),
        reward: None,
        life_job: None,
        last_action: 0, skill_hit: 0,
        last_respawn: 0,
        last_claim: 0,
        claim: None,
        next_action: 0,
    }
}
