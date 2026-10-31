//! Operator NPC snapshot record (PQ-189). A session holding `server.inspect` asks,
//! through the authorized `record` admin operation, for one NPC's state to be
//! written to the server log; the operator's result carries a status only.
//!
//! KO reference (evidence/pq-188-npc-pursue-snapshot.md, D-148): the operator
//! command `+pursue <id>` (Ebenezer `0042c1ba`) asks the AI server (`004074d7`) for
//! the NPC's state byte, `HP` pair and position, and Ebenezer `0040b24e` appends
//! them beside its own copy of the NPC to its region log file. No client receives
//! them and neither packet names the operator. n3e has one authoritative
//! simulation, so the record has one side: the simulation's own NPC, in the
//! engine's behavior words, written to the server's log (stderr) off the tick.
use crate::wire;

/// Ticks between two records of one session (one a second at 50 ms ticks, as a
/// chat line), so an operator cannot flood the log.
pub const INTERVAL: u64 = 20;

/// Admits one record for a session whose last record was at tick `last` (0 when
/// it has none) and stores `tick` when admitted.
pub fn admit(last: &mut u64, tick: u64) -> bool {
    if *last != 0 && tick.saturating_sub(*last) < INTERVAL {
        return false;
    }
    *last = tick;
    true
}

/// The record line. Strings are quoted and escaped, so package names cannot add
/// lines or fields to the log.
pub fn line(npc: &wire::Entity, max_health: u32, tick: u64) -> String {
    format!(
        "npc record tick={tick} entity={} name={:?} behavior={:?} health={} max_health={max_health} x={:.2} y={:.2} z={:.2}",
        npc.id, npc.name, npc.behavior, npc.health, npc.x, npc.y, npc.z
    )
}

/// Writes the line on the blocking pool, so a slow or full stderr never stalls
/// the tick. The line is lost if the process ends first, as any log line.
pub fn write(line: String) {
    tokio::task::spawn_blocking(move || {
        use std::io::Write;
        let _ = writeln!(std::io::stderr().lock(), "{line}");
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn one_record_per_interval_per_session() {
        let mut last = 0;
        assert!(admit(&mut last, 5));
        assert!(!admit(&mut last, 5));
        assert!(!admit(&mut last, 5 + INTERVAL - 1));
        assert!(admit(&mut last, 5 + INTERVAL));
        assert_eq!(last, 5 + INTERVAL);
    }
    #[test]
    fn line_holds_the_fields_on_one_escaped_line() {
        let npc = wire::Entity {
            id: 42,
            name: "Bad\nnpc record entity=1".into(),
            behavior: "chase".into(),
            health: 7,
            x: 1.234,
            y: -0.5,
            z: 10.,
            npc: true,
            ..Default::default()
        };
        let l = line(&npc, 10, 99);
        assert_eq!(
            l,
            "npc record tick=99 entity=42 name=\"Bad\\nnpc record entity=1\" behavior=\"chase\" health=7 max_health=10 x=1.23 y=-0.50 z=10.00"
        );
        assert!(!l.contains('\n'));
    }
}
