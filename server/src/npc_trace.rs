//! Operator NPC state trace (PQ-186). A session holding `server.inspect` marks an
//! NPC through the authorized `trace` admin operation; while the mark lasts, every
//! World snapshot of a session whose `server.inspect` lease is current carries the
//! state of each marked NPC inside that session's interest area.
//!
//! KO reference (evidence/pq-186-npc-state-trace.md): the operator command
//! `+actpursue <id>` (Ebenezer `0042c1ba`) makes the AI server set the NPC's mark
//! (`00407651`, `+0xc54` = 1), which only the NPC constructor clears; each AI step
//! of a marked NPC then reports its state byte, and Ebenezer `0040b4d4` forwards it
//! as client opcode `0x5d` to the in-game users of the NPC's 3x3 regions whose
//! authority byte is 0 (`0041e454`). n3e keeps the shape (a mark on the NPC seen by
//! every operator in range) and moves the authority to the server: the mark is
//! authorized against Postgres, the reports follow a server-side lease, and the
//! state is the engine's own NPC behavior, never KO's numbering.
use crate::wire;
use std::collections::BTreeMap;

/// Marks alive at once, across all sessions.
pub const MAX_MARKS: usize = 32;
/// Marks one session may hold alive at once.
pub const MAX_PER_SESSION: usize = 8;
/// Longest state string a report carries; the engine's behaviors are shorter.
pub const MAX_STATE: usize = 16;

#[derive(Default)]
pub struct Marks {
    /// NPC entity id -> the (character, session generation) that marked it.
    marks: BTreeMap<u64, (i64, i64)>,
}

impl Marks {
    /// Applies an authorized mark. `exists` says whether `entity` is an NPC the
    /// simulation currently holds. Marking an already marked NPC succeeds and keeps
    /// the first owner, as KO's flag is set once.
    pub fn mark(&mut self, owner: (i64, i64), entity: u64, exists: bool) -> &'static str {
        if !exists {
            return "unknown_target";
        }
        if self.marks.contains_key(&entity) {
            return "traced";
        }
        if self.marks.len() >= MAX_MARKS
            || self.marks.values().filter(|o| **o == owner).count() >= MAX_PER_SESSION
        {
            return "trace_limit";
        }
        self.marks.insert(entity, owner);
        "traced"
    }
    /// Moves a mark to the NPC's new entity id. KO keeps the flag on the AI
    /// server's NPC object for its life: only the constructor `00417873` clears
    /// it, and the dispatcher `0042b86c` turns state 0 into 1 on the same object.
    /// An n3e NPC changes its entity id on an encounter reset (a damaged NPC's
    /// health rising in its step, as when healed at home) and on respawn; the
    /// mark follows it.
    pub fn follow(&mut self, before: u64, after: u64) {
        if before != after {
            if let Some(owner) = self.marks.remove(&before) {
                self.marks.insert(after, owner);
            }
        }
    }
    /// Drops marks whose NPC left the simulation (a temporary NPC that expired).
    pub fn retain(&mut self, live: impl Fn(u64) -> bool) {
        self.marks.retain(|entity, _| live(*entity));
    }
    pub fn is_empty(&self) -> bool {
        self.marks.is_empty()
    }
    #[cfg(test)]
    pub fn len(&self) -> usize {
        self.marks.len()
    }
    /// The reports for one snapshot: the marked NPCs among the entities the
    /// session already sees, in entity order. The caller sends them only to a
    /// session whose server.inspect lease is current.
    pub fn report(&self, view: &[wire::Entity]) -> Vec<wire::NpcTrace> {
        if self.marks.is_empty() {
            return vec![];
        }
        let mut out: Vec<_> = view
            .iter()
            .filter(|e| e.npc && self.marks.contains_key(&e.id))
            .map(|e| wire::NpcTrace {
                entity: e.id,
                state: e.behavior.chars().take(MAX_STATE).collect(),
            })
            .collect();
        out.sort_by_key(|t| t.entity);
        out.dedup_by_key(|t| t.entity);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn npc(id: u64, behavior: &str) -> wire::Entity {
        wire::Entity {
            id,
            npc: true,
            behavior: behavior.into(),
            ..Default::default()
        }
    }
    #[test]
    fn marks_are_bounded_per_session_and_overall() {
        let mut m = Marks::default();
        assert_eq!(m.mark((1, 1), 99, false), "unknown_target");
        for e in 0..MAX_PER_SESSION as u64 {
            assert_eq!(m.mark((1, 1), 100 + e, true), "traced");
        }
        assert_eq!(m.mark((1, 1), 200, true), "trace_limit");
        // Remarking an NPC is idempotent and does not count again.
        assert_eq!(m.mark((1, 1), 100, true), "traced");
        // A new session of the same character has its own allowance.
        assert_eq!(m.mark((1, 2), 200, true), "traced");
        let mut owner = 10;
        while m.len() < MAX_MARKS {
            for e in 0..MAX_PER_SESSION as u64 {
                if m.len() < MAX_MARKS {
                    assert_eq!(m.mark((owner, 1), 1000 * owner as u64 + e, true), "traced");
                }
            }
            owner += 1;
        }
        assert_eq!(m.mark((owner + 1, 1), 5, true), "trace_limit");
        // A re-identified NPC keeps its mark under the new id, without counting twice.
        m.follow(100, 300);
        assert_eq!(m.len(), MAX_MARKS);
        assert_eq!(m.mark((1, 1), 300, true), "traced");
        m.follow(300, 100);
        m.follow(999, 998);
        assert_eq!(m.len(), MAX_MARKS);
        // An NPC leaving the simulation frees its mark.
        m.retain(|e| e != 100);
        assert_eq!(m.len(), MAX_MARKS - 1);
        assert_eq!(m.mark((owner + 1, 1), 5, true), "traced");
    }
    #[test]
    fn reports_cover_marked_npcs_in_view_only() {
        let mut m = Marks::default();
        assert!(m.report(&[npc(1, "idle")]).is_empty());
        m.mark((1, 1), 1, true);
        m.mark((1, 1), 3, true);
        let player = wire::Entity {
            id: 3,
            npc: false,
            behavior: "idle".into(),
            ..Default::default()
        };
        let view = [npc(2, "chase"), npc(1, "attack"), player, npc(1, "attack")];
        let r = m.report(&view);
        assert_eq!(r.len(), 1);
        assert_eq!((r[0].entity, r[0].state.as_str()), (1, "attack"));
        let long = "x".repeat(40);
        assert_eq!(m.report(&[npc(1, &long)])[0].state.len(), MAX_STATE);
    }
}
