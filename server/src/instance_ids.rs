//! Runtime entity ids for a zone's whole NPC population (PQ-250).
//!
//! Every NPC instance, respawn, encounter reset, player revive, wear event,
//! claim and temporary spawn takes one id from a noncycling Postgres sequence
//! (`entity_instances`), fetched in batches off the tick. KO's spawn load
//! numbers each NPC once (AI `0043893e`); whether its respawn keeps that number
//! was not read (D-163). n3e gives each instance a new id so a client never
//! confuses a respawn with its predecessor (protocol/wire.proto, `World`). The pool here sizes those batches
//! by the population so startup never runs short and respawn churn cannot take
//! the ids player work needs.
use std::collections::VecDeque;

/// Most ids one `Database::instances` call returns (server/src/rewards.rs).
pub const MAX_BATCH: usize = 1024;
/// Ids left after the startup population, and the smallest refill batch: the
/// pre-PQ-250 pool (one batch of 256, refilled below 128).
pub const BASE: usize = 256;
/// Ids an NPC respawn never takes: player-driven work (revives, wear events,
/// claims, operator spawns) may use them, so a respawn wave cannot refuse it.
pub const PLAYER_RESERVE: usize = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Plan {
    /// Ids reserved before the first tick: one per spawn plus `BASE`.
    pub startup: usize,
    /// Refill when the pool holds fewer than this.
    pub low: usize,
    /// Ids one refill asks for.
    pub batch: usize,
}

pub fn plan(spawns: usize) -> Plan {
    Plan {
        startup: spawns + BASE,
        low: (spawns / 4).max(BASE / 2),
        batch: (spawns / 2).clamp(BASE, MAX_BATCH),
    }
}

/// The batch sizes that make up `total`, each at most `MAX_BATCH`.
pub fn batches(total: usize) -> Vec<i64> {
    let mut out = Vec::new();
    let mut left = total;
    while left > 0 {
        let n = left.min(MAX_BATCH);
        out.push(n as i64);
        left -= n;
    }
    out
}

/// Whether an NPC respawn (or a dead NPC's fallback respawn) may take an id now.
pub fn respawn_allowed(ids: &VecDeque<u64>) -> bool {
    ids.len() > PLAYER_RESERVE
}

/// Whether to start a refill: below the low mark and none in flight.
pub fn needs_refill(plan: &Plan, ids: &VecDeque<u64>, in_flight: bool) -> bool {
    !in_flight && ids.len() < plan.low
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_covers_the_population_and_scales_refills() {
        // The pre-PQ-250 pool for a small package.
        assert_eq!(plan(2), Plan { startup: 258, low: 128, batch: 256 });
        // Zone 1's population in the local OpenKO rows (local-asset): 1,238.
        assert_eq!(plan(1238), Plan { startup: 1494, low: 309, batch: 619 });
        assert_eq!(plan(2048), Plan { startup: 2304, low: 512, batch: 1024 });
        assert_eq!(batches(2304), vec![1024, 1024, 256]);
        assert_eq!(batches(258), vec![258]);
        assert!(batches(0).is_empty());
        assert!(batches(2304).iter().all(|&n| (1..=MAX_BATCH as i64).contains(&n)));
    }

    /// The pool under a respawn wave: every NPC of a full zone dies at once and
    /// all come due on the same tick, while players keep taking ids. Refills
    /// complete `latency` ticks after they start, one at a time.
    fn churn(spawns: usize, latency: u64, player_rate: usize) -> (u64, usize) {
        let plan = plan(spawns);
        let mut next = 1u64;
        let mut take = |n: usize| -> Vec<u64> {
            let v = (next..next + n as u64).collect();
            next += n as u64;
            v
        };
        let mut ids: VecDeque<u64> = batches(plan.startup).into_iter().flat_map(|n| take(n as usize)).collect();
        // Startup: one id per spawn.
        let mut alive: Vec<bool> = (0..spawns).map(|_| ids.pop_front().is_some()).collect();
        assert!(alive.iter().all(|&a| a));
        assert_eq!(ids.len(), BASE);
        let mut refill: Option<u64> = None;
        let mut refused = 0;
        alive.iter_mut().for_each(|a| *a = false);
        let mut tick = 0;
        while alive.iter().any(|a| !a) {
            tick += 1;
            assert!(tick < 1000, "respawn wave never finished");
            if refill.is_some_and(|t| t <= tick) {
                ids.extend(take(plan.batch));
                refill = None;
            }
            if needs_refill(&plan, &ids, refill.is_some()) {
                refill = Some(tick + latency);
            }
            // Player work first in the tick, as in the simulation's command drain.
            for _ in 0..player_rate {
                if ids.pop_front().is_none() {
                    refused += 1;
                }
            }
            for a in alive.iter_mut().filter(|a| !**a) {
                if respawn_allowed(&ids) {
                    ids.pop_front().unwrap();
                    *a = true;
                }
            }
        }
        (tick, refused)
    }

    #[test]
    fn a_full_zone_respawns_under_churn_without_starving_players() {
        for (spawns, latency) in [(1238, 1), (1238, 5), (2048, 1), (2048, 10), (32, 1)] {
            let (ticks, refused) = churn(spawns, latency, 4);
            // Players never find the pool empty: respawns stop at the reserve.
            assert_eq!(refused, 0, "spawns {spawns} latency {latency}");
            // The wave finishes within a bounded number of refills.
            let refills = spawns.div_ceil(plan(spawns).batch) as u64 + 2;
            assert!(ticks <= refills * (latency + 1) + 2, "spawns {spawns} latency {latency}: {ticks} ticks");
        }
    }

    #[test]
    fn respawns_leave_the_player_reserve() {
        let mut ids: VecDeque<u64> = (0..PLAYER_RESERVE as u64 + 3).collect();
        let mut taken = 0;
        while respawn_allowed(&ids) {
            ids.pop_front();
            taken += 1;
        }
        assert_eq!(taken, 3);
        assert_eq!(ids.len(), PLAYER_RESERVE);
    }
}
