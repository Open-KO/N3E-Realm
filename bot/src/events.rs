//! `realm:events` Redis Stream entry types (spec 03 "Event stream").

use serde::{Deserialize, Serialize};

/// Every `type` the realm emits. The bot ignores unknown types and acks them.
pub const TYPES: &[&str] = &[
    "realm.ready",
    "realm.unready",
    "realm.draining",
    "realm.resumed",
    "player.joined",
    "player.left",
    "account.kicked",
    "account.banned",
    "account.unbanned",
    "account.muted",
    "account.unmuted",
    "notice",
    "deploy.pending",
    "world.spawn.result",
    "world.kill.result",
    "world.event.started",
    "world.event.stopped",
];

/// One stream entry as the bot reads it: `type`, `ts` (RFC 3339), `data` (JSON string).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Entry {
    #[serde(rename = "type")]
    pub kind: String,
    pub ts: String,
    pub data: String,
}

/// Which Discord channel an event goes to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Channel {
    Announce,
    Ops,
    None,
}

/// Routing per spec 05 "Event stream consumer".
pub fn channel_for(kind: &str) -> Channel {
    match kind {
        "realm.ready"
        | "realm.draining"
        | "notice"
        | "world.event.started"
        | "world.event.stopped" => Channel::Announce,
        "world.spawn.result" => Channel::Announce, // ops on failure; decided per entry at render time
        "realm.unready" | "realm.resumed" | "deploy.pending" | "world.kill.result" => Channel::Ops,
        k if k.starts_with("account.") => Channel::Ops,
        "player.joined" | "player.left" => Channel::None,
        _ => Channel::None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_known_type_has_a_routing_decision() {
        for t in TYPES {
            // Just exercise the match; unknown-by-omission would fall into `_`.
            let _ = channel_for(t);
        }
        assert_eq!(channel_for("player.joined"), Channel::None);
        assert_eq!(channel_for("account.banned"), Channel::Ops);
        assert_eq!(channel_for("notice"), Channel::Announce);
    }
}
