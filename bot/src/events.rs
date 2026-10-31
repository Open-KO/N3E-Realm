//! `realm:events` (spec 03 "Event stream") and what each entry becomes in Discord
//! (spec 05 "Event stream consumer").

use crate::text::{escape, fit, when};
use serde_json::Value;

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

/// Which Discord channel an event goes to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Channel {
    Announce,
    Ops,
}

/// One Discord message the relay wants sent.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Post {
    pub channel: Channel,
    pub text: String,
}

/// The relay's memory between stream entries: whether the realm was last seen ready
/// (so a restart loop announces "up" once), and what to tell a moderator whose command
/// finds the admin API down (spec 05 "Fail fast").
#[derive(Debug, Default)]
pub struct Relay {
    ready: Option<bool>,
    condition: Option<String>,
}

fn field(data: &Value, key: &str) -> String {
    match &data[key] {
        Value::String(s) => escape(s),
        Value::Null => String::new(),
        v => escape(&v.to_string()),
    }
}

impl Relay {
    /// Why the realm is likely away, when the stream said so last: `realm.draining`
    /// (with its reason) or `realm.unready`.
    pub fn condition(&self) -> Option<&str> {
        self.condition.as_deref()
    }

    /// The messages one stream entry becomes (spec 05 "Event stream consumer"). `by`
    /// names who acted on an `account.*` entry: the moderator, when this bot made the
    /// call, else the token name the server recorded.
    pub fn render(
        &mut self,
        kind: &str,
        data: &Value,
        by: &dyn Fn(&str, &Value) -> String,
    ) -> Vec<Post> {
        let post = |channel, text: String| Post {
            channel,
            text: fit(text),
        };
        match kind {
            "realm.ready" => {
                let was = self.ready.replace(true);
                self.condition = None;
                if was == Some(true) {
                    return vec![];
                }
                let version = data["version"].as_str().unwrap_or("?").replace('`', "'");
                vec![post(
                    Channel::Announce,
                    format!("Realm is up — version `{version}`"),
                )]
            }
            "realm.unready" => {
                self.ready = Some(false);
                self.condition = Some("The realm reported it is not ready.".into());
                vec![post(Channel::Ops, "Realm is not ready".into())]
            }
            "realm.draining" => {
                // A drain ends in a restart: the next `realm.ready` is news.
                self.ready = Some(false);
                let reason = field(data, "reason");
                self.condition = Some(format!("The realm is draining for a restart: {reason}."));
                let players = data["players"].as_u64().unwrap_or(0);
                vec![post(
                    Channel::Announce,
                    format!("Restart soon: {reason}. {players} online."),
                )]
            }
            "realm.resumed" => {
                self.ready = Some(true);
                self.condition = None;
                vec![post(Channel::Ops, "Drain cancelled".into())]
            }
            "notice" => {
                let text = field(data, "text");
                if data["level"] == "warn" {
                    let text = format!("**Warning:** {text}");
                    vec![
                        post(Channel::Announce, text.clone()),
                        post(Channel::Ops, text),
                    ]
                } else {
                    vec![post(Channel::Announce, format!("**Notice:** {text}"))]
                }
            }
            "deploy.pending" => {
                let since = data["since"].as_str().map(when).unwrap_or_default();
                let n = data["commits_behind"].as_u64().unwrap_or(0);
                let commits = if n == 1 { "commit" } else { "commits" };
                vec![post(
                    Channel::Ops,
                    format!("Deploy pending since {since} ({n} {commits}). Run `/deploy` when the realm is quiet."),
                )]
            }
            k if k.starts_with("account.") => {
                let who = by(k, data);
                let name = match data["discord_name"].as_str() {
                    Some(n) => escape(n),
                    None => format!("account {}", data["account_id"]),
                };
                let until = match data["until"].as_str() {
                    Some(t) => format!(" until {}", when(t)),
                    None => " permanently".into(),
                };
                let reason = field(data, "reason");
                let text = match k {
                    "account.kicked" => format!("{who} kicked {name}: {reason}"),
                    "account.banned" => format!("{who} banned {name}{until}: {reason}"),
                    "account.unbanned" => format!("{who} unbanned {name}"),
                    "account.muted" => format!("{who} muted {name}{until}: {reason}"),
                    "account.unmuted" => format!("{who} unmuted {name}"),
                    _ => return vec![],
                };
                vec![post(Channel::Ops, text)]
            }
            "world.spawn.result" => {
                let (status, detail) = (field(data, "status"), field(data, "detail"));
                match (data["status"].as_str(), data["announce"].as_str()) {
                    (Some("spawn_authorized"), Some(text)) if !text.is_empty() => {
                        vec![post(Channel::Announce, escape(text))]
                    }
                    (Some("spawn_authorized"), _) => {
                        vec![post(
                            Channel::Ops,
                            format!("Spawn {} done", field(data, "request_id")),
                        )]
                    }
                    _ => vec![post(
                        Channel::Ops,
                        format!("Spawn failed: {status} {detail}").trim_end().into(),
                    )],
                }
            }
            "world.kill.result" => vec![post(
                Channel::Ops,
                format!(
                    "Kill {}: {} {}",
                    field(data, "request_id"),
                    field(data, "status"),
                    field(data, "detail")
                )
                .trim_end()
                .into(),
            )],
            "world.event.started" | "world.event.stopped" => {
                let text = match data["announce"].as_str() {
                    Some(a) if !a.is_empty() => escape(a),
                    _ => {
                        let title = match data["title"].as_str() {
                            Some(t) => escape(t),
                            None => field(data, "preset"),
                        };
                        let state = if kind.ends_with("started") {
                            "started"
                        } else {
                            "ended"
                        };
                        let until = match (kind.ends_with("started"), data["until"].as_str()) {
                            (true, Some(t)) => format!(" (until {})", when(t)),
                            _ => String::new(),
                        };
                        format!("**{title}** has {state}{until}")
                    }
                };
                vec![post(Channel::Announce, text)]
            }
            _ => vec![],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_known_type_renders_or_is_consumed_quietly() {
        let mut r = Relay::default();
        for t in TYPES {
            let posts = r.render(t, &serde_json::json!({}), &by);
            assert_eq!(posts.is_empty(), t.starts_with("player."), "{t}");
        }
    }

    fn by(_: &str, data: &Value) -> String {
        field(data, "by")
    }

    fn texts(relay: &mut Relay, kind: &str, data: Value) -> Vec<(Channel, String)> {
        relay
            .render(kind, &data, &by)
            .into_iter()
            .map(|p| (p.channel, p.text))
            .collect()
    }

    #[test]
    fn realm_state_messages() {
        let mut r = Relay::default();
        let up = texts(
            &mut r,
            "realm.ready",
            serde_json::json!({"version": "v1", "content_hash": "h"}),
        );
        assert_eq!(
            up,
            vec![(Channel::Announce, "Realm is up — version `v1`".into())]
        );
        assert!(
            texts(&mut r, "realm.ready", serde_json::json!({"version": "v1"})).is_empty(),
            "restart loop"
        );
        let drain = texts(
            &mut r,
            "realm.draining",
            serde_json::json!({"reason": "deploy v2", "players": 3}),
        );
        assert_eq!(
            drain,
            vec![(
                Channel::Announce,
                "Restart soon: deploy v2. 3 online.".into()
            )]
        );
        assert_eq!(
            r.condition(),
            Some("The realm is draining for a restart: deploy v2.")
        );
        assert_eq!(
            texts(&mut r, "realm.ready", serde_json::json!({"version": "v2"})).len(),
            1,
            "back after a drain"
        );
        assert_eq!(r.condition(), None);
        texts(&mut r, "realm.unready", serde_json::json!({}));
        assert_eq!(r.condition(), Some("The realm reported it is not ready."));
        assert_eq!(
            texts(&mut r, "realm.resumed", serde_json::json!({})),
            vec![(Channel::Ops, "Drain cancelled".into())]
        );
    }

    #[test]
    fn notices_accounts_and_world() {
        let mut r = Relay::default();
        assert_eq!(
            texts(
                &mut r,
                "notice",
                serde_json::json!({"text": "hello", "level": "info", "by": "bot"})
            ),
            vec![(Channel::Announce, "**Notice:** hello".into())]
        );
        assert_eq!(
            texts(
                &mut r,
                "notice",
                serde_json::json!({"text": "fire", "level": "warn"})
            )
            .len(),
            2
        );
        let kicked = serde_json::json!({"account_id": 7, "discord_name": "Nel_ly", "reason": "**afk**", "by": "bot"});
        assert_eq!(
            texts(&mut r, "account.kicked", kicked),
            vec![(Channel::Ops, r"bot kicked Nel\_ly: \*\*afk\*\*".into())]
        );
        let banned = serde_json::json!({"account_id": 7, "discord_name": null, "reason": "spam",
                                         "until": "2026-11-01T00:00:00Z", "by": "ops"});
        assert_eq!(
            texts(&mut r, "account.banned", banned)[0].1,
            "ops banned account 7 until 2026-11-01 00:00 UTC: spam"
        );
        let perm = serde_json::json!({"account_id": 7, "discord_name": "N", "reason": "x", "until": null, "by": "bot"});
        assert_eq!(
            texts(&mut r, "account.muted", perm)[0].1,
            "bot muted N permanently: x"
        );
        let spawn = serde_json::json!({"request_id": "r1", "status": "spawn_authorized", "announce": "Ironfang has appeared!"});
        assert_eq!(
            texts(&mut r, "world.spawn.result", spawn),
            vec![(Channel::Announce, "Ironfang has appeared!".into())]
        );
        let failed = serde_json::json!({"request_id": "r2", "status": "invalid_spawn", "detail": "no such index"});
        assert_eq!(
            texts(&mut r, "world.spawn.result", failed)[0].0,
            Channel::Ops
        );
        let started = serde_json::json!({"preset": "weekend-exp", "title": "Weekend XP", "until": "2026-11-02T00:00:00Z"});
        assert_eq!(
            texts(&mut r, "world.event.started", started)[0].1,
            "**Weekend XP** has started (until 2026-11-02 00:00 UTC)"
        );
        let pending = serde_json::json!({"since": "2026-10-30T12:00:00Z", "commits_behind": 1, "head": "abc"});
        assert_eq!(
            texts(&mut r, "deploy.pending", pending)[0].1,
            "Deploy pending since 2026-10-30 12:00 UTC (1 commit). Run `/deploy` when the realm is quiet."
        );
        for quiet in ["player.joined", "player.left", "something.new"] {
            assert!(
                texts(&mut r, quiet, serde_json::json!({})).is_empty(),
                "{quiet}"
            );
        }
    }
}
