//! A session's movement admission (PQ-404, D-207, amending D-014).
//!
//! The simulation applies at most one movement per session per tick. A valid
//! movement that arrives while one is already waiting for the next tick is held
//! for the tick after it, so arrival jitter that puts two of a client's 50 ms
//! sends into one command drain costs no refused step. A third is refused. The
//! hold depends only on how many movements the server has admitted and not yet
//! applied, never on a client's timing.
//!
//! Both slots live in this one type so that no path can clear the waiting
//! movement and leave the held one behind (or the reverse).
use crate::wire;

#[derive(Default)]
pub(crate) struct MoveQueue {
    /// The movement the next tick applies.
    next: Option<wire::Move>,
    /// One more, admitted after `next` (its seq is higher), for the tick after.
    held: Option<wire::Move>,
}

impl MoveQueue {
    /// Queue an already validated movement. Returns false, and keeps nothing,
    /// when both slots are full: the caller refuses it and does not record its
    /// seq.
    pub(crate) fn admit(&mut self, m: wire::Move) -> bool {
        if self.next.is_none() {
            self.next = Some(m);
        } else if self.held.is_none() {
            self.held = Some(m);
        } else {
            return false;
        }
        true
    }
    /// The movement this tick applies; the held one becomes the next.
    pub(crate) fn take(&mut self) -> Option<wire::Move> {
        let m = self.next.take();
        self.next = self.held.take();
        m
    }
    /// The movement the coming tick applies, if any.
    pub(crate) fn next(&self) -> Option<&wire::Move> {
        self.next.as_ref()
    }
    /// Drop both slots. Returns the newest admitted seq, so a caller that
    /// acknowledges the dropped inputs acknowledges all of them.
    pub(crate) fn clear(&mut self) -> Option<u64> {
        let newest = self.held.take().or(self.next.take()).map(|m| m.seq);
        self.next = None;
        newest
    }
    /// A queued input (either slot) asks to move.
    pub(crate) fn moving(&self) -> bool {
        [&self.next, &self.held]
            .into_iter()
            .flatten()
            .any(|m| m.x != 0. || m.z != 0.)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn mv(seq: u64, z: f32) -> wire::Move {
        wire::Move { seq, z, ..Default::default() }
    }
    #[test]
    fn holds_one_refuses_a_third_and_releases_one_per_take_in_order() {
        let mut q = MoveQueue::default();
        assert!(q.take().is_none());
        assert!(q.admit(mv(1, -1.)));
        assert!(q.admit(mv(2, 0.)));
        assert!(!q.admit(mv(3, 1.)), "a third waits for no slot");
        assert_eq!(q.next().map(|m| m.seq), Some(1));
        assert_eq!(q.take().map(|m| m.seq), Some(1));
        // The held one moved up: one more fits again, then the queue is full.
        assert_eq!(q.next().map(|m| m.seq), Some(2));
        assert!(q.admit(mv(4, 0.)));
        assert!(!q.admit(mv(5, 0.)));
        assert_eq!(q.take().map(|m| m.seq), Some(2));
        assert_eq!(q.take().map(|m| m.seq), Some(4));
        assert!(q.take().is_none() && q.next().is_none());
    }
    #[test]
    fn clear_drops_both_slots_and_names_the_newest_seq() {
        let mut q = MoveQueue::default();
        assert_eq!(q.clear(), None);
        q.admit(mv(7, 0.));
        assert_eq!(q.clear(), Some(7));
        assert!(q.next().is_none());
        q.admit(mv(8, 0.));
        q.admit(mv(9, -1.));
        assert!(q.moving(), "the held input moves");
        assert_eq!(q.clear(), Some(9));
        assert!(q.take().is_none() && !q.moving());
        // After a clear both slots are free again.
        assert!(q.admit(mv(10, 0.)) && q.admit(mv(11, 0.)) && !q.admit(mv(12, 0.)));
        assert!(!q.moving());
    }
}
