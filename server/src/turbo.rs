//! Fail-closed permission leases and durable revocation-observation barriers.
//! The same read also leases `server.inspect` for the NPC state trace (PQ-186):
//! reports reach a session only while its lease is current. It also decides
//! operator visibility (PQ-184, D-152): `hidden` and `sees` below, and the
//! holder's own show switch (PQ-192, D-153): `show`.
use crate::{
    accounts::Owner,
    content::{bad, Result},
    persistence,
};
use postgres::Client;
use std::time::{Duration, Instant};
pub const LEASE: Duration = Duration::from_millis(500);
#[derive(Clone, Debug)]
pub struct Authority {
    pub id: i64,
    pub session: i64,
    pub generation: u64,
    pub allowed: bool,
    /// The character holds `server.inspect` (PQ-186).
    pub inspect: bool,
}
pub fn read(c: &mut Client, o: &Owner, ids: &[i64]) -> Result<Vec<Authority>> {
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    let rows=t.query("SELECT c.id,c.session_generation,COALESCE(a.generation,0),EXISTS(SELECT 1 FROM character_roles r WHERE r.character_id=c.id AND r.realm=c.realm AND r.zone='*' AND r.capability='movement.turbo'),EXISTS(SELECT 1 FROM character_roles r WHERE r.character_id=c.id AND r.realm=c.realm AND r.zone='*' AND r.capability='server.inspect') FROM characters c LEFT JOIN admin_authority a ON a.character_id=c.id WHERE c.realm=$1 AND c.realm_generation=$2 AND c.online AND c.id=ANY($3)",&[&o.realm,&o.generation,&ids])?;
    Ok(rows
        .iter()
        .map(|r| Authority {
            id: r.get(0),
            session: r.get(1),
            generation: r.get::<_, i64>(2) as u64,
            allowed: r.get(3),
            inspect: r.get(4),
        })
        .collect())
}
pub fn observed(c: &mut Client, o: &Owner, rows: &[Authority]) -> Result<()> {
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    for a in rows {
        t.execute("INSERT INTO movement_authority_observed VALUES($1,$2,$3,$4) ON CONFLICT(character_id) DO UPDATE SET session_generation=EXCLUDED.session_generation,realm_generation=EXCLUDED.realm_generation,generation=EXCLUDED.generation WHERE movement_authority_observed.realm_generation<EXCLUDED.realm_generation OR (movement_authority_observed.realm_generation=EXCLUDED.realm_generation AND movement_authority_observed.session_generation<=EXCLUDED.session_generation AND movement_authority_observed.generation<=EXCLUDED.generation)",&[&a.id,&a.session,&o.generation,&(a.generation as i64)])?;
    }
    t.commit()?;
    Ok(())
}
pub fn await_revocation(c: &mut Client, id: i64, generation: i64) -> Result<()> {
    let until = Instant::now() + Duration::from_secs(6);
    loop {
        let row=c.query_one("SELECT NOT c.online OR NOT EXISTS(SELECT 1 FROM realm_ownership r WHERE r.realm=c.realm AND r.generation=c.realm_generation AND r.expires>clock_timestamp()) OR EXISTS(SELECT 1 FROM movement_authority_observed o WHERE o.character_id=c.id AND o.session_generation=c.session_generation AND o.realm_generation=c.realm_generation AND o.generation >= $2) FROM characters c WHERE c.id=$1",&[&id,&generation])?;
        if row.get::<_, bool>(0) {
            return Ok(());
        }
        if Instant::now() >= until {
            return Err(bad(
                "role revoked durably; simulation invalidation not yet confirmed",
            ));
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}
#[derive(Default)]
pub struct State {
    pub generation: u64,
    pub allowed: bool,
    pub expires: Option<Instant>,
    pub active: bool,
    pub input_tick: u64,
    /// The last read found `server.inspect`; honoured only within the lease.
    pub inspect: bool,
    /// PQ-192 (D-153): the holder chose to be shown (KO's operator command
    /// `VIEW`). Per session and in memory only: a session starts hidden, and a
    /// read that finds no `server.inspect` clears it.
    pub shown: bool,
}
impl State {
    pub fn permitted(&self) -> bool {
        self.allowed && self.expires.is_some_and(|t| Instant::now() < t)
    }
    /// The session may receive NPC trace reports (PQ-186): the last authority
    /// read found `server.inspect` and its lease has not expired, so a revoked
    /// role or a stalled database read stops the reports within one lease.
    pub fn inspecting(&self) -> bool {
        self.inspect && self.expires.is_some_and(|t| Instant::now() < t)
    }
    /// PQ-184 (D-152): the session is withheld from observers that may not see
    /// hidden actors while its `server.inspect` lease is current, and before its
    /// first authority read; the first is taken before the join (network.rs), so a
    /// login does not show an operator unless that read's lease lapses before
    /// the simulation admits the session. A revocation's
    /// read or a lapsed lease (a stalled read) makes it visible again, and so
    /// does the holder's own `show` (PQ-192, D-153) until it hides again.
    pub fn hidden(&self) -> bool {
        self.expires.is_none() || (self.inspecting() && !self.shown)
    }
    /// PQ-192 (D-153): the holder's show switch. Applied only while the
    /// session's `server.inspect` lease is current; returns whether it was.
    pub fn show(&mut self, shown: bool) -> bool {
        if !self.inspecting() {
            return false;
        }
        self.shown = shown;
        true
    }
    pub fn apply(&mut self, a: &Authority, started: Instant) {
        if a.generation < self.generation {
            return;
        }
        if a.generation != self.generation || !a.allowed {
            self.active = false;
        }
        self.generation = a.generation;
        self.allowed = a.allowed;
        self.inspect = a.inspect;
        // PQ-192: a revocation resets the switch, so a regrant hides again.
        if !a.inspect {
            self.shown = false;
        }
        self.expires = Some(started + LEASE);
    }
}
/// PQ-184 (D-152): whether an observer may be sent an actor. Every session sees
/// itself; a hidden actor reaches only an observer whose own `server.inspect`
/// lease is current, so operators see each other and a lapsed lease sees none.
pub fn sees(observer: &State, itself: bool, actor: &State) -> bool {
    itself || observer.inspecting() || !actor.hidden()
}
#[cfg(test)]
mod tests {
    use super::*;
    fn read(generation: u64, inspect: bool) -> Authority {
        Authority { id: 1, session: 1, generation, allowed: false, inspect }
    }
    #[test]
    fn inspect_lease_fails_closed() {
        let mut s = State::default();
        assert!(!s.inspecting(), "no read yet");
        s.apply(&read(1, true), Instant::now());
        assert!(s.inspecting());
        // An older read never restores a revoked role.
        s.apply(&read(2, false), Instant::now());
        assert!(!s.inspecting());
        s.apply(&read(1, true), Instant::now());
        assert!(!s.inspecting());
        // A lease that is not renewed lapses.
        s.apply(&read(3, true), Instant::now() - LEASE);
        assert!(!s.inspecting());
    }
    #[test]
    fn operator_hidden_until_revoked_or_lapsed() {
        let (mut operator, mut player, mut other) =
            (State::default(), State::default(), State::default());
        // Before any read every session is withheld from ordinary observers.
        assert!(operator.hidden() && player.hidden());
        assert!(!sees(&other, false, &operator) && sees(&operator, true, &operator));
        operator.apply(&read(1, true), Instant::now());
        player.apply(&read(1, false), Instant::now());
        other.apply(&read(1, false), Instant::now());
        assert!(operator.hidden() && !player.hidden());
        assert!(!sees(&player, false, &operator), "an ordinary observer");
        assert!(sees(&player, false, &other) && sees(&operator, false, &player));
        assert!(sees(&operator, true, &operator), "itself");
        // A second holder sees the first, and the first sees it.
        let mut second = State::default();
        second.apply(&read(1, true), Instant::now());
        assert!(sees(&second, false, &operator) && sees(&operator, false, &second));
        // A revocation's read shows the operator; an older read never hides it again.
        operator.apply(&read(2, false), Instant::now());
        assert!(!operator.hidden() && sees(&player, false, &operator));
        operator.apply(&read(1, true), Instant::now());
        assert!(!operator.hidden());
        // A lapsed lease (no read for LEASE) shows the operator and stops the
        // holder seeing hidden ones.
        operator.apply(&read(3, true), Instant::now() - LEASE);
        second.apply(&read(1, true), Instant::now() - LEASE);
        assert!(!operator.hidden() && sees(&player, false, &operator));
        let mut hidden = State::default();
        hidden.apply(&read(1, true), Instant::now());
        assert!(!sees(&second, false, &hidden));
    }
    #[test]
    fn shown_operator_until_hidden_or_revoked() {
        // PQ-192 (D-153): the holder's show switch.
        let (mut operator, mut player) = (State::default(), State::default());
        // A non-holder (and a session with no read) cannot use it.
        assert!(!player.show(true) && !player.shown);
        player.apply(&read(1, false), Instant::now());
        assert!(!player.show(true) && !player.shown, "a non-holder");
        operator.apply(&read(1, true), Instant::now());
        assert!(operator.hidden() && !sees(&player, false, &operator), "hidden by default");
        // Shown: visible to an ordinary observer, and still sees hidden actors.
        assert!(operator.show(true));
        assert!(!operator.hidden() && sees(&player, false, &operator));
        let mut other = State::default();
        other.apply(&read(1, true), Instant::now());
        assert!(other.hidden() && sees(&operator, false, &other), "a shown holder sees hidden actors");
        // A renewed read that still finds the role keeps the choice.
        operator.apply(&read(1, true), Instant::now());
        assert!(!operator.hidden());
        // Hiding again withholds it.
        assert!(operator.show(false));
        assert!(operator.hidden() && !sees(&player, false, &operator));
        // A revocation resets the switch: the regrant hides the operator again.
        assert!(operator.show(true) && !operator.hidden());
        operator.apply(&read(2, false), Instant::now());
        assert!(!operator.shown && !operator.hidden());
        operator.apply(&read(3, true), Instant::now());
        assert!(operator.hidden() && !sees(&player, false, &operator), "the regrant hides it");
        // An older read neither resets nor restores anything.
        assert!(operator.show(true));
        operator.apply(&read(2, false), Instant::now());
        assert!(operator.shown && !operator.hidden());
        // A lapsed lease refuses the switch, shows the operator and keeps the choice.
        operator.apply(&read(4, true), Instant::now() - LEASE);
        assert!(!operator.show(false) && operator.shown && !operator.hidden());
        // A new session (a new login) starts hidden.
        let mut login = State::default();
        login.apply(&read(4, true), Instant::now());
        assert!(login.hidden() && !login.shown);
    }
}
