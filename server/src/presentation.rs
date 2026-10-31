//! Cosmetic events only. No event can award an item, damage or consume a resource.
use crate::wire;
use std::collections::{BTreeMap, VecDeque};
/// A retained event and whether its actor and its target were withheld
/// (PQ-184, D-152) when it was pushed or at any tick since.
struct Held {
    event: wire::PresentationEvent,
    hidden: [bool; 2],
}
#[derive(Default)]
pub struct Events {
    pub cursor: u64,
    events: VecDeque<Held>,
    strikes: BTreeMap<u64, u64>,
    /// PQ-184 (D-152): the entity ids withheld at the last `withhold` or `hide`,
    /// bounded by the session count.
    hidden: Vec<u64>,
}
impl Events {
    pub fn push(&mut self, mut event: wire::PresentationEvent) {
        self.cursor = self
            .cursor
            .checked_add(1)
            .expect("presentation sequence exhausted");
        event.sequence = self.cursor;
        if self.events.len() == 128 {
            self.events.pop_front();
        }
        // PQ-184: an event a withheld session makes or receives between two
        // `withhold` calls (on its way out, say) is marked as it is pushed.
        let hidden = [self.hidden.contains(&event.actor), self.hidden.contains(&event.target)];
        self.events.push_back(Held { event, hidden });
    }
    /// PQ-184 (D-152), once per tick before any view: `hidden` are the entity ids
    /// withheld now. Every retained event naming one is marked for good, so it
    /// stays withheld after the session leaves, takes a new entity id or is
    /// revealed, until the event leaves the history. Returns the ids withheld at
    /// the previous call that `hidden` no longer lists.
    pub fn withhold(&mut self, hidden: &[u64]) -> Vec<u64> {
        let previous = std::mem::replace(&mut self.hidden, hidden.to_vec());
        self.mark();
        previous
            .into_iter()
            .filter(|id| !self.hidden.contains(id))
            .collect()
    }
    /// PQ-184: a session admitted withheld between two `withhold` calls.
    pub fn hide(&mut self, id: u64) {
        if !self.hidden.contains(&id) {
            self.hidden.push(id);
        }
        self.mark();
    }
    fn mark(&mut self) {
        for h in &mut self.events {
            h.hidden[0] |= self.hidden.contains(&h.event.actor);
            h.hidden[1] |= self.hidden.contains(&h.event.target);
        }
    }
    pub fn consumed(&mut self, tick: u64, actor: &wire::Entity, item: String) {
        self.push(wire::PresentationEvent {
            tick,
            actor: actor.id,
            target: actor.id,
            kind: 1,
            key: item,
            x: actor.x,
            y: actor.y,
            z: actor.z,
            target_x: actor.x,
            target_y: actor.y,
            target_z: actor.z,
            ..Default::default()
        });
    }
    pub fn observe(&mut self, tick: u64, actors: &[wire::Entity]) {
        // PQ-250: indexed by id, so a zone's whole population costs
        // O(n log n) per view rather than O(n^2).
        let index: std::collections::HashMap<u64, usize> =
            actors.iter().enumerate().map(|(i, e)| (e.id, i)).collect();
        self.strikes.retain(|id, _| index.contains_key(id));
        for actor in actors {
            let previous = self
                .strikes
                .insert(actor.id, actor.strike_tick)
                .unwrap_or(0);
            if actor.strike_tick == 0 || actor.strike_tick == previous {
                continue;
            }
            let Some(target) = index.get(&actor.strike_target).map(|&i| &actors[i]) else {
                continue;
            };
            self.push(wire::PresentationEvent {
                tick: actor.strike_tick,
                request_sequence: actor.strike_sequence,
                actor: actor.id,
                target: target.id,
                kind: 2,
                key: String::new(),
                style: actor.strike_style,
                moving: actor.strike_moving,
                hit: actor.strike_result == "hit",
                npc: actor.npc,
                x: actor.x,
                y: actor.y,
                z: actor.z,
                target_x: target.x,
                target_y: target.y,
                target_z: target.z,
                ..Default::default()
            });
        }
        self.events.retain(|h| tick.saturating_sub(h.event.tick) <= 40);
    }
    /// The events near `actor`. PQ-184 (D-152): unless `sees_hidden` (the
    /// observer's own `server.inspect` lease is current), an event whose actor or
    /// target was withheld is left out, except where that withheld party is the
    /// observer itself.
    pub fn view(&self, actor: &wire::Entity, cell: f32, sees_hidden: bool) -> Vec<wire::PresentationEvent> {
        self.events
            .iter()
            .filter(|h| {
                sees_hidden
                    || !((h.hidden[0] && h.event.actor != actor.id)
                        || (h.hidden[1] && h.event.target != actor.id))
            })
            .map(|h| &h.event)
            .filter(|e| {
                ((e.x / cell).floor() - (actor.x / cell).floor()).abs() <= 1.
                    && ((e.z / cell).floor() - (actor.z / cell).floor()).abs() <= 1.
            })
            .cloned()
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounds_and_strike_dedup() {
        let mut events = Events::default();
        let actor = wire::Entity {
            id: 1,
            strike_tick: 10,
            strike_sequence: 129,
            strike_target: 2,
            strike_result: "miss".into(),
            ..Default::default()
        };
        let target = wire::Entity {
            id: 2,
            ..Default::default()
        };
        events.observe(10, &[actor.clone(), target.clone()]);
        assert_eq!(events.cursor, 1);
        assert!(!events.events[0].event.hit);
        assert_eq!(events.events[0].event.request_sequence,129);
        events.observe(11, &[actor.clone(), target.clone()]);
        assert_eq!(events.cursor, 1);
        let mut far = actor.clone();
        far.x = 1000.;
        assert!(events.view(&far, 32., false).is_empty());
        for tick in 11..200 {
            events.consumed(tick, &actor, "demo:item/test".into());
        }
        assert_eq!(events.events.len(), 128);
        events.observe(240, &[actor, target]);
        assert!(events.events.is_empty());
    }
}
