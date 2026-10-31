//! Ephemeral, session-scoped party membership. Rewards remain a separate durable flow.
use crate::content::{Reader, Result, bad};
use std::{collections::BTreeMap, path::Path};

#[derive(Clone, Debug)]
pub struct Policy {
    pub capacity: usize,
    pub name_bytes: usize,
    pub minimum: f64,
    pub maximum: f64,
    pub gap: u32,
    pub repeat_ticks: u64,
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3Z1" {
            return Err(bad("party magic"));
        }
        let p = Self {
            capacity: r.u()? as usize,
            name_bytes: r.u()? as usize,
            minimum: f64::from_le_bytes(r.take(8)?.try_into()?),
            maximum: f64::from_le_bytes(r.take(8)?.try_into()?),
            gap: r.u()?,
            repeat_ticks: r.u()? as u64,
        };
        r.end()?;
        if !(2..=8).contains(&p.capacity)
            || !(1..=24).contains(&p.name_bytes)
            || !p.minimum.is_finite()
            || !p.maximum.is_finite()
            || !(0.0..=1.0).contains(&p.minimum)
            || !(1.0..=10.0).contains(&p.maximum)
            || p.gap > 100
            || p.repeat_ticks > 1200
        {
            return Err(bad("party policy bounds"));
        }
        Ok(p)
    }
    pub fn levels(&self, inviter: u32, target: u32) -> bool {
        inviter > 0
            && target > 0
            && ((target >= (inviter as f64 * self.minimum) as u32
                && target <= (inviter as f64 * self.maximum) as u32)
                || inviter.abs_diff(target) <= self.gap)
    }
}
#[derive(Clone, Debug)]
pub struct Actor {
    pub session: i64,
    pub name: String,
    pub level: u32,
    pub alive: bool,
}
#[derive(Clone, Debug)]
pub struct Group {
    pub id: u64,
    pub leader: i64,
    pub slots: Vec<Option<i64>>,
}
#[derive(Clone, Debug)]
pub struct Invitation {
    pub token: u64,
    pub group: u64,
    pub inviter: i64,
    pub inviter_session: i64,
    pub target_session: i64,
}
#[derive(Default)]
pub struct Parties {
    groups: BTreeMap<u64, Group>,
    members: BTreeMap<i64, u64>,
    invitations: BTreeMap<i64, Invitation>,
    repeated: BTreeMap<i64, (i64, u64)>,
    next: u64,
}
impl Parties {
    fn allocate(&mut self) -> Option<u64> {
        self.next = self.next.checked_add(1).filter(|v| *v <= i64::MAX as u64)?;
        Some(self.next)
    }
    pub fn group(&self, id: i64) -> Option<&Group> {
        self.members.get(&id).and_then(|g| self.groups.get(g))
    }
    pub fn invitation(&self, id: i64) -> Option<&Invitation> {
        self.invitations.get(&id)
    }
    // The reference friend flag sees a pending group index as well as accepted membership.
    pub fn affiliated(&self, id: i64) -> bool {
        self.members.contains_key(&id) || self.invitations.contains_key(&id)
    }
    pub fn invite(
        &mut self,
        p: &Policy,
        actors: &BTreeMap<i64, Actor>,
        id: i64,
        target: i64,
        tick: u64,
    ) -> &'static str {
        let (Some(a), Some(b)) = (actors.get(&id), actors.get(&target)) else {
            return "unavailable";
        };
        if !crate::accounts::valid_name(&a.name, p.name_bytes)
            || !crate::accounts::valid_name(&b.name, p.name_bytes)
        {
            return "unavailable";
        }
        if id == target
            || !a.alive
            || !b.alive
            || self.affiliated(target)
            || self.invitations.contains_key(&id)
        {
            return "unavailable";
        }
        if !p.levels(a.level, b.level) {
            return "level_range";
        }
        if self
            .repeated
            .get(&id)
            .is_some_and(|&(old, t)| old == target && tick.saturating_sub(t) < p.repeat_ticks)
        {
            return "rate_limited";
        }
        if let Some(g) = self.group(id) {
            if g.leader != id {
                return "not_leader";
            }
            if g.slots.iter().flatten().count() >= p.capacity {
                return "full";
            }
        }
        if actors.len() > 64 || self.invitations.len() >= 64 {
            return "capacity";
        }
        let Some(token) = self.allocate() else {
            return "capacity";
        };
        let group = if let Some(g) = self.members.get(&id) {
            *g
        } else {
            let Some(group) = self.allocate() else {
                return "capacity";
            };
            let mut slots = vec![None; p.capacity];
            slots[0] = Some(id);
            self.groups.insert(
                group,
                Group {
                    id: group,
                    leader: id,
                    slots,
                },
            );
            self.members.insert(id, group);
            group
        };
        self.repeated.insert(id, (target, tick));
        self.invitations.insert(
            target,
            Invitation {
                token,
                group,
                inviter: id,
                inviter_session: a.session,
                target_session: b.session,
            },
        );
        "invited"
    }
    fn end(&mut self, group: u64) {
        if let Some(g) = self.groups.remove(&group) {
            for id in g.slots.into_iter().flatten() {
                self.members.remove(&id);
            }
        }
        self.invitations.retain(|_, v| v.group != group);
    }
    pub fn answer(
        &mut self,
        actors: &BTreeMap<i64, Actor>,
        id: i64,
        token: u64,
        accept: bool,
    ) -> &'static str {
        let Some(v) = self.invitations.get(&id).cloned() else {
            return "no_invitation";
        };
        if v.token != token {
            return "stale_invitation";
        }
        if !actors
            .get(&id)
            .is_some_and(|p| p.session == v.target_session)
            || !actors
                .get(&v.inviter)
                .is_some_and(|p| p.session == v.inviter_session)
            || !self
                .groups
                .get(&v.group)
                .is_some_and(|g| g.leader == v.inviter)
        {
            self.invitations.remove(&id);
            return "stale_invitation";
        }
        self.invitations.remove(&id);
        if !accept {
            if self.groups[&v.group].slots.iter().flatten().count() == 1 {
                self.end(v.group);
            }
            return "declined";
        }
        // Eligibility was checked at invitation. The binary accept path does not
        // reject a later death or level change; only membership/capacity is authoritative here.
        let g = self.groups.get_mut(&v.group).unwrap();
        let Some(slot) = g.slots.iter_mut().find(|s| s.is_none()) else {
            return "full";
        };
        *slot = Some(id);
        self.members.insert(id, v.group);
        "joined"
    }
    pub fn remove(&mut self, id: i64, target: i64) -> &'static str {
        let Some(g) = self.group(id) else {
            return "not_member";
        };
        if id != target && g.leader != id {
            return "not_leader";
        }
        if !g.slots.contains(&Some(target)) {
            return "not_member";
        }
        let group = g.id;
        if g.slots.iter().flatten().count() <= 2 {
            self.end(group);
            return "disbanded";
        }
        let g = self.groups.get_mut(&group).unwrap();
        *g.slots.iter_mut().find(|v| **v == Some(target)).unwrap() = None;
        self.members.remove(&target);
        if g.leader == target {
            g.leader = *g.slots.iter().flatten().next().unwrap();
            // Pending invitations were issued by the previous leader's session.
            self.invitations.retain(|_, v| v.group != group);
        }
        "removed"
    }
    pub fn disband(&mut self, id: i64) -> &'static str {
        let Some(g) = self.group(id) else {
            return "not_member";
        };
        if g.leader != id {
            return "not_leader";
        }
        let group = g.id;
        self.end(group);
        "disbanded"
    }
    pub fn leave(&mut self, id: i64) {
        if let Some(v) = self.invitations.remove(&id) {
            if self
                .groups
                .get(&v.group)
                .is_some_and(|g| g.slots.iter().flatten().count() == 1)
            {
                self.end(v.group);
            }
        }
        self.remove(id, id);
        self.invitations.retain(|_, v| v.inviter != id);
        self.repeated.remove(&id);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn policy() -> Policy {
        Policy {
            capacity: 8,
            name_bytes: 20,
            minimum: 2.0 / 3.0,
            maximum: 1.5,
            gap: 8,
            repeat_ticks: 60,
        }
    }
    fn actors() -> BTreeMap<i64, Actor> {
        (1..=12)
            .map(|id| {
                (
                    id,
                    Actor {
                        session: 1,
                        name: format!("Peer{id}"),
                        level: 30,
                        alive: true,
                    },
                )
            })
            .collect()
    }
    fn join(
        h: &mut Parties,
        p: &Policy,
        a: &BTreeMap<i64, Actor>,
        leader: i64,
        target: i64,
        t: u64,
    ) {
        assert_eq!(h.invite(p, a, leader, target, t), "invited");
        let token = h.invitation(target).unwrap().token;
        assert_eq!(h.answer(a, target, token, true), "joined");
    }
    #[test]
    fn authority_slots_pending_and_leader_lifecycle() {
        let p = policy();
        let a = actors();
        let mut h = Parties::default();
        join(&mut h, &p, &a, 1, 2, 1);
        join(&mut h, &p, &a, 1, 3, 2);
        assert_eq!(h.invite(&p, &a, 2, 4, 3), "not_leader");
        assert_eq!(h.disband(2), "not_leader");
        assert_eq!(h.remove(2, 3), "not_leader");
        assert_eq!(h.remove(1, 12), "not_member");
        assert_eq!(h.invite(&p, &a, 1, 4, 3), "invited");
        let old = h.invitation(4).unwrap().token;
        assert!(h.affiliated(4));
        assert!(h.group(4).is_none());
        assert_eq!(h.answer(&a, 3, old, false), "no_invitation");
        assert_eq!(h.remove(1, 1), "removed");
        assert_eq!(h.group(2).unwrap().leader, 2);
        assert!(h.invitation(4).is_none());
        assert_eq!(h.answer(&a, 4, old, true), "no_invitation");
        join(&mut h, &p, &a, 2, 4, 4);
        assert_eq!(h.group(4).unwrap().slots[0], Some(4));
        h.leave(2);
        assert_eq!(h.group(3).unwrap().leader, 4);
        h.leave(3);
        assert!(!h.affiliated(4));
        for id in 1..=12 {
            assert!(!h.affiliated(id));
        }
    }
    #[test]
    fn pending_capacity_rejection_reconnect_and_decline() {
        let p = policy();
        let mut a = actors();
        let mut h = Parties::default();
        assert_eq!(h.invite(&p, &a, 1, 2, 1), "invited");
        let old = h.invitation(2).unwrap().token;
        assert_eq!(h.answer(&a, 2, old + 1, true), "stale_invitation");
        assert_eq!(h.answer(&a, 2, old, false), "declined");
        assert!(!h.affiliated(1));
        assert_eq!(h.invite(&p, &a, 1, 2, 59), "rate_limited");
        join(&mut h, &p, &a, 1, 2, 61);
        for id in 3..=9 {
            assert_eq!(h.invite(&p, &a, 1, id, 62 + id as u64), "invited");
        }
        for id in 3..=8 {
            let t = h.invitation(id).unwrap().token;
            assert_eq!(h.answer(&a, id, t, true), "joined");
        }
        let t = h.invitation(9).unwrap().token;
        assert_eq!(h.answer(&a, 9, t, true), "full");
        assert!(!h.affiliated(9));
        assert_eq!(h.invite(&p, &a, 1, 10, 100), "full");
        assert_eq!(h.remove(1, 4), "removed");
        assert_eq!(h.invite(&p, &a, 1, 10, 101), "invited");
        let t = h.invitation(10).unwrap().token;
        a.get_mut(&10).unwrap().session += 1;
        assert_eq!(h.answer(&a, 10, t, true), "stale_invitation");
        assert_eq!(h.invite(&p, &a, 1, 11, 102), "invited");
        h.disband(1);
        assert!(!h.affiliated(11));
        assert!(h.groups.is_empty());
    }
    #[test]
    fn level_boundary_and_invitation_capture() {
        let p = policy();
        assert!(p.levels(30, 20));
        assert!(p.levels(30, 45));
        assert!(!p.levels(30, 19));
        assert!(!p.levels(30, 46));
        assert!(p.levels(10, 2));
        assert!(!p.levels(10, 1));
        assert!(!p.levels(0, 1));
        let mut a = actors();
        let mut h = Parties::default();
        a.get_mut(&2).unwrap().alive = false;
        assert_eq!(h.invite(&p, &a, 1, 2, 1), "unavailable");
        a.get_mut(&2).unwrap().alive = true;
        assert_eq!(h.invite(&p, &a, 1, 2, 1), "invited");
        let t = h.invitation(2).unwrap().token;
        a.get_mut(&2).unwrap().alive = false;
        a.get_mut(&2).unwrap().level = 90;
        assert_eq!(h.answer(&a, 2, t, true), "joined");
        assert_eq!(h.invite(&p, &a, 1, 1, 2), "unavailable");
    }
}
