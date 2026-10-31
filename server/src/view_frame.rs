//! The view frame bound for a crowded interest window (PQ-250, D-163).
//!
//! A `World` is one atomic interest baseline in one frame, and every frame is
//! at most `LIMIT` bytes (server/src/network.rs, client/network/world.cpp). A
//! zone's whole population can put more entities in one 3 x 3 interest window
//! than fit. Rule, applied per session per view:
//!
//! 1. A view that fits is sent whole.
//! 2. Otherwise the viewer itself and every non-entity field stay; the other
//!    entities are kept nearest first (planar distance, then id) while the frame
//!    fits; an event stays only when its actor and target are the viewer or
//!    kept entities; traces follow the kept entities. Order within the kept set
//!    is the view's own.
//! 3. If the viewer alone does not fit, nothing is sent and the session is
//!    closed (the caller marks it failed), as a session whose view can never
//!    be delivered.
//!
//! KO reference (Ebenezer `7d83cc28...`): the region NPC-in list `00423be6`
//! gathers the nine cells `004241dd` fills (each stops adding past 16,300
//! bytes, `0x3fac`), and when the whole list reaches 49,100 bytes (`0xbfcc`,
//! `00424000`) it logs `NpcInOutForMe - buffer overflow` and sends no list at
//! all. n3e keeps the nearest entities instead of none (BINARY-POLICY, "View
//! frame overflow correction").
use crate::wire::{self, envelope::Body, Envelope};
use prost::Message;

/// Largest frame either side accepts (server/src/network.rs `LIMIT`).
pub const LIMIT: usize = 65536;

#[derive(Debug, PartialEq, Eq)]
pub enum Fit {
    Whole,
    Trimmed { kept: usize, dropped: usize },
    Over,
}

/// Bytes of `world` sent as one envelope.
pub fn frame_len(world: &mut wire::World) -> usize {
    let envelope = Envelope {
        body: Some(Body::World(std::mem::take(world))),
    };
    let n = envelope.encoded_len();
    if let Some(Body::World(w)) = envelope.body {
        *world = w;
    }
    n
}

/// One repeated-field element's bytes: key (fields 4, 14 and 17 take one byte),
/// length prefix and body.
pub fn element(len: usize) -> usize {
    1 + prost::encoding::encoded_len_varint(len as u64) + len
}

/// Bytes a `World` of `world_len` bytes takes as one envelope.
fn framed(world_len: usize) -> usize {
    1 + prost::encoding::encoded_len_varint(world_len as u64) + world_len
}

/// The most bytes `NpcTrace` reports add to a view after `plan` (an id and a
/// state of at most `npc_trace::MAX_STATE` bytes, for each of `MAX_MARKS`).
pub const TRACE_RESERVE: usize = crate::npc_trace::MAX_MARKS * (2 + 1 + 10 + 2 + crate::npc_trace::MAX_STATE);

/// One other entity a view may carry: planar distance from the viewer, id,
/// and its bytes as a view element (an upper bound is enough).
pub type Candidate = (f32, u64, usize);

/// Chooses the other entities a view keeps, before any is copied (PQ-250).
/// `world` holds everything but the other entities: the viewer's own entity,
/// the events and every other field; `reserve` is what the caller adds after
/// (trace reports). Under trimming, `world.events` keeps only the events whose
/// actor and target are the viewer or kept. Returns the fit and the kept ids
/// (the viewer's among them); `Over` empties the events and keeps nothing.
pub fn plan(
    world: &mut wire::World,
    viewer: u64,
    others: &mut [Candidate],
    reserve: usize,
) -> (Fit, std::collections::HashSet<u64>) {
    let base = world.encoded_len() + reserve;
    let all: usize = others.iter().map(|o| o.2).sum();
    if framed(base + all) <= LIMIT {
        return (Fit::Whole, others.iter().map(|o| o.1).chain([viewer]).collect());
    }
    // Nearest first, then by id, so equal distances keep a stable order.
    others.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
    let ranks: std::collections::HashMap<u64, usize> =
        others.iter().enumerate().map(|(i, o)| (o.1, i + 1)).chain([(viewer, 0)]).collect();
    // An event naming an entity outside the view never fits a trimmed view.
    let rank = |id: u64| ranks.get(&id).copied().unwrap_or(usize::MAX);
    // Each event needs both of its parties; its cost lands at that rank.
    let mut event_cost = vec![0usize; others.len() + 1];
    let mut event_bytes = 0;
    let event_ranks: Vec<usize> = world
        .events
        .iter()
        .map(|e| {
            let r = rank(e.actor).max(rank(e.target));
            let bytes = element(e.encoded_len());
            event_bytes += bytes;
            if r < event_cost.len() {
                event_cost[r] += bytes;
            }
            r
        })
        .collect();
    // The envelope adds a one-byte key and a length prefix of at most three
    // bytes for a frame of LIMIT; count the largest.
    let budget = LIMIT - 4;
    let mut used = base - event_bytes + event_cost[0];
    let mut kept = 0;
    if used <= budget {
        for (i, o) in others.iter().enumerate() {
            let next = used + o.2 + event_cost[i + 1];
            if next > budget {
                break;
            }
            used = next;
            kept = i + 1;
        }
    }
    if used > budget {
        world.events.clear();
        return (Fit::Over, Default::default());
    }
    let mut event_rank = event_ranks.into_iter();
    world.events.retain(|_| event_rank.next().is_some_and(|r| r <= kept));
    let keep = others[..kept].iter().map(|o| o.1).chain([viewer]).collect();
    (
        Fit::Trimmed {
            kept,
            dropped: others.len() - kept,
        },
        keep,
    )
}

/// `plan` applied to an assembled view, as the simulation applies it (it plans
/// from references and copies only the kept entities): keeps the view's own
/// entity order and the traces of kept entities, and checks the real size.
#[cfg(test)]
pub fn fit(world: &mut wire::World, viewer: &wire::Entity) -> Fit {
    let distance = |e: &wire::Entity| {
        let (dx, dz) = (e.x - viewer.x, e.z - viewer.z);
        dx * dx + dz * dz
    };
    let entities = std::mem::take(&mut world.entities);
    let mut others: Vec<Candidate> = entities
        .iter()
        .filter(|e| e.id != viewer.id)
        .map(|e| (distance(e), e.id, element(e.encoded_len())))
        .collect();
    let traces = std::mem::take(&mut world.traces);
    let reserve: usize = traces.iter().map(|t| element(t.encoded_len())).sum();
    world.entities = entities.iter().filter(|e| e.id == viewer.id).cloned().collect();
    let (fit, keep) = plan(world, viewer.id, &mut others, reserve);
    world.entities = entities.into_iter().filter(|e| keep.contains(&e.id)).collect();
    world.traces = traces.into_iter().filter(|t| keep.contains(&t.entity)).collect();
    if fit == Fit::Over || frame_len(world) > LIMIT {
        world.entities.clear();
        world.events.clear();
        world.traces.clear();
        return Fit::Over;
    }
    fit
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entity(id: u64, x: f32, z: f32, name: usize) -> wire::Entity {
        wire::Entity {
            id,
            name: format!("demo:creature/{}", "n".repeat(name)),
            looks: format!("demo:looks/{}", "l".repeat(name)),
            x,
            z,
            y: 1.,
            health: 150000,
            max_health: 150000,
            npc: true,
            behavior: "idle".into(),
            life_state: wire::LifeState::Alive as i32,
            definition_revision: 7,
            ..Default::default()
        }
    }

    fn world(viewer: &wire::Entity, others: &[wire::Entity]) -> wire::World {
        let mut entities = others.to_vec();
        entities.insert(entities.len() / 2, viewer.clone());
        wire::World {
            tick: 1,
            session: 1,
            self_: viewer.id,
            entities,
            revision: Some(wire::Revision {
                base: "h".repeat(64),
                revision: 3,
                tick: 9,
                values: (0..128)
                    .map(|i| wire::PropertyValue { key: format!("demo:spawn.{i}.x{}", "k".repeat(100)), value: 1. })
                    .collect(),
            }),
            ..Default::default()
        }
    }

    #[test]
    fn a_view_that_fits_is_sent_whole() {
        // KO's densest window (about 85 NPCs, local-asset, PQ-069) with names as
        // long as KO's (29 bytes) after a package prefix, beside 63 other
        // sessions (the connection cap is 64) and a full 128-property revision.
        let viewer = wire::Entity { id: 1, ..Default::default() };
        let mut others: Vec<_> = (0..85).map(|i| entity(100 + i, i as f32, 0., 25)).collect();
        others.extend((0..63).map(|i| wire::Entity {
            id: 1000 + i,
            name: "p".repeat(24),
            x: i as f32,
            appearance: vec![123456; 16],
            health: 9999,
            behavior: "idle".into(),
            ..Default::default()
        }));
        let mut w = world(&viewer, &others);
        let before = w.clone();
        let size = frame_len(&mut w);
        assert!(size < LIMIT / 2, "{size}");
        assert_eq!(fit(&mut w, &viewer), Fit::Whole);
        assert_eq!(w, before);
    }

    #[test]
    fn a_crowded_view_keeps_the_nearest_within_the_frame() {
        let viewer = wire::Entity { id: 1, x: 10., z: 10., ..Default::default() };
        // 1,300 entities with 100-character names in one window, ids against distance.
        let others: Vec<_> = (0..1300u64)
            .map(|i| entity(10_000 - i, 10. + (i % 37) as f32 * 0.5, 10. + (i / 37) as f32 * 0.5, 100))
            .collect();
        let mut w = world(&viewer, &others);
        // Events: one between the viewer and its nearest neighbour, one between two far ones.
        let near = others.iter().min_by(|a, b| {
            let d = |e: &wire::Entity| (e.x - 10.).powi(2) + (e.z - 10.).powi(2);
            d(a).total_cmp(&d(b)).then(a.id.cmp(&b.id))
        }).unwrap().id;
        w.events = vec![
            wire::PresentationEvent { sequence: 1, actor: near, target: 1, kind: 2, ..Default::default() },
            wire::PresentationEvent { sequence: 2, actor: others[1299].id, target: others[1298].id, kind: 2, ..Default::default() },
            wire::PresentationEvent { sequence: 3, actor: 1, target: 1, kind: 1, key: "demo:item/potion".into(), ..Default::default() },
        ];
        w.traces = vec![
            wire::NpcTrace { entity: near, state: "idle".into() },
            wire::NpcTrace { entity: others[1299].id, state: "idle".into() },
        ];
        let Fit::Trimmed { kept, dropped } = fit(&mut w, &viewer) else { panic!("not trimmed") };
        assert_eq!(kept + dropped, 1300);
        assert!(kept > 50 && dropped > 0, "{kept} {dropped}");
        assert!(frame_len(&mut w) <= LIMIT);
        // The viewer is kept, and every kept entity is at least as near as every dropped one.
        assert!(w.entities.iter().any(|e| e.id == 1));
        let d = |e: &wire::Entity| ((e.x - 10.).powi(2) + (e.z - 10.).powi(2), e.id);
        let far_kept = w.entities.iter().filter(|e| e.id != 1).map(d).max_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1))).unwrap();
        let ids: std::collections::BTreeSet<_> = w.entities.iter().map(|e| e.id).collect();
        for e in others.iter().filter(|e| !ids.contains(&e.id)) {
            let (dist, id) = d(e);
            assert!(dist > far_kept.0 || (dist == far_kept.0 && id > far_kept.1));
        }
        // One more entity would not fit.
        let next = others.iter().filter(|e| !ids.contains(&e.id)).min_by(|a, b| d(a).0.total_cmp(&d(b).0).then(a.id.cmp(&b.id))).unwrap();
        let mut grown = w.clone();
        grown.entities.push(next.clone());
        assert!(frame_len(&mut grown) > LIMIT);
        // Events keep both parties; traces follow kept entities.
        assert_eq!(w.events.iter().map(|e| e.sequence).collect::<Vec<_>>(), vec![1, 3]);
        assert_eq!(w.traces.len(), 1);
        assert_eq!(w.traces[0].entity, near);
        // The rest of the view is untouched.
        assert_eq!(w.revision.as_ref().unwrap().values.len(), 128);
    }

    #[test]
    fn a_view_whose_viewer_alone_does_not_fit_is_not_sent() {
        let viewer = wire::Entity { id: 1, ..Default::default() };
        let mut w = world(&viewer, &[entity(2, 1., 1., 10)]);
        w.skill_cooldowns = (0..600)
            .map(|i| wire::SkillCooldown { skill: format!("demo:skill/{i}{}", "s".repeat(100)), ready_tick: 1 })
            .collect();
        assert!(frame_len(&mut w) > LIMIT);
        assert_eq!(fit(&mut w, &viewer), Fit::Over);
        assert!(w.entities.is_empty());
    }
}
