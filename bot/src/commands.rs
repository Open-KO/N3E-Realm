//! Slash commands (spec 05 "Slash commands"): their Discord definitions, the role each
//! needs, and what each does through the admin API. Discord-independent: the gateway
//! glue in `main.rs` turns an interaction into an [`Invocation`] and posts the [`Reply`].

use crate::admin::{Catalog, Status};
use crate::api::{Admin, GitHub, Outcome};
use crate::config::Config;
use crate::events::Relay;
use crate::text::{duration, escape, now, rfc3339, uptime, when};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, RwLock};
use std::time::{Duration, Instant};
use twilight_model::application::command::{Command, CommandType};
use twilight_util::builder::command::{
    BooleanBuilder, CommandBuilder, IntegerBuilder, StringBuilder, UserBuilder,
};

/// Who may run a command. OPS may run everything MOD may.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role {
    Anyone,
    Mod,
    Ops,
}

pub fn role(command: &str) -> Role {
    match command {
        "status" => Role::Anyone,
        "deploy" => Role::Ops,
        _ => Role::Mod,
    }
}

/// The role check (a convenience; the admin token's permissions are the boundary).
pub fn allowed(command: &str, roles: &[u64], config: &Config) -> bool {
    let ops = roles.contains(&config.role_ops);
    match role(command) {
        Role::Anyone => true,
        Role::Mod => ops || roles.contains(&config.role_mod),
        Role::Ops => ops,
    }
}

pub const NO_PERMISSION: &str = "You don't have permission";
pub const UNAVAILABLE: &str =
    "Realm admin API unavailable — the server is probably restarting. Try again in a minute.";
pub const TOKEN_REJECTED: &str = "bot token rejected — ops needs to re-mint";
/// The autocomplete value offered when the catalog could not be fetched.
pub const NO_CATALOG: &str = "realm-catalog-unavailable";

/// The guild commands the bot registers (bulk overwrite: an upsert of the whole set).
pub fn definitions() -> Vec<Command> {
    let user = |d: &str| UserBuilder::new("user", d).required(true);
    let reason = |required: bool| {
        StringBuilder::new("reason", "Why; shown to the player and in the ops channel")
            .max_length(200)
            .required(required)
    };
    let until = || {
        StringBuilder::new(
            "duration",
            "How long: 30m, 1h, 3d, 2w or perm (default perm)",
        )
        .max_length(16)
    };
    let command = |name: &str, description: &str| {
        CommandBuilder::new(name, description, CommandType::ChatInput)
    };
    vec![
        command(
            "status",
            "Players online, version, draining, pending deploy",
        )
        .build(),
        command("whois", "A Discord user's realm account")
            .option(user("Who"))
            .build(),
        command("kick", "Disconnect a player and end their sessions")
            .option(user("Who"))
            .option(reason(true))
            .build(),
        command("ban", "Block a player's account; disconnects them")
            .option(user("Who"))
            .option(reason(true))
            .option(until())
            .build(),
        command("unban", "Lift a ban").option(user("Who")).build(),
        command("mute", "Drop a player's chat")
            .option(user("Who"))
            .option(reason(true))
            .option(until())
            .build(),
        command("unmute", "Lift a mute").option(user("Who")).build(),
        command("motd", "Set the message players see on entering the world")
            .option(
                StringBuilder::new("lines", "The lines, separated by |")
                    .max_length(2600)
                    .required(true),
            )
            .build(),
        command(
            "notice",
            "Announce in game and in the announcements channel",
        )
        .option(
            StringBuilder::new("text", "What to announce")
                .max_length(500)
                .required(true),
        )
        .build(),
        command("boss", "Spawn a named boss from the realm catalog")
            .option(
                StringBuilder::new("name", "Which spawn")
                    .autocomplete(true)
                    .required(true),
            )
            .option(reason(false))
            .build(),
        command("kill", "Remove a world entity")
            .option(
                IntegerBuilder::new("entity", "Entity id")
                    .min_value(1)
                    .required(true),
            )
            .option(reason(true))
            .build(),
        command("event", "Start an event preset from the realm catalog")
            .option(
                StringBuilder::new("preset", "Which preset")
                    .autocomplete(true)
                    .required(true),
            )
            .option(reason(false))
            .build(),
        command("event-stop", "End the running event preset")
            .option(reason(false))
            .build(),
        command(
            "deploy",
            "Run the CD workflow now (drains and restarts the realm)",
        )
        .option(reason(false))
        .option(BooleanBuilder::new(
            "force",
            "Deploy even when nothing is pending",
        ))
        .build(),
    ]
}

/// An option value as the handlers need it.
#[derive(Debug, Clone, PartialEq)]
pub enum Opt {
    Text(String),
    User(u64),
    Integer(i64),
    Bool(bool),
}

/// One slash command as the handlers see it.
#[derive(Debug, Clone)]
pub struct Invocation {
    pub name: String,
    pub options: HashMap<String, Opt>,
    /// The invoker's Discord id and display name.
    pub user: u64,
    pub user_name: String,
}

impl Invocation {
    fn text(&self, name: &str) -> Option<&str> {
        match self.options.get(name) {
            Some(Opt::Text(t)) if !t.trim().is_empty() => Some(t.trim()),
            _ => None,
        }
    }
}

/// The invoker's (ephemeral) reply, and a message for the ops channel if the outcome
/// is one operators must hear about.
#[derive(Debug, Clone, PartialEq)]
pub struct Reply {
    pub text: String,
    pub ops: Option<String>,
}

impl From<String> for Reply {
    fn from(text: String) -> Self {
        Reply { text, ops: None }
    }
}

impl From<&str> for Reply {
    fn from(text: &str) -> Self {
        Reply::from(text.to_string())
    }
}

/// A moderator's account call, remembered until its stream entry is rendered so the ops
/// channel names the person rather than the bot's token.
struct Attribution {
    kind: &'static str,
    account: i64,
    moderator: String,
    at: Instant,
}

const ATTRIBUTION_TTL: Duration = Duration::from_secs(120);

pub struct Bot {
    pub config: Config,
    pub admin: Admin,
    pub github: Option<GitHub>,
    pub relay: Mutex<Relay>,
    pub catalog: RwLock<Option<Catalog>>,
    attributions: Mutex<Vec<Attribution>>,
    /// Whether ops has been told the token was rejected (once until it works again).
    rejection_reported: AtomicBool,
}

impl Bot {
    pub fn new(config: Config) -> Self {
        Self {
            admin: Admin::new(&config.admin_url, &config.admin_token),
            github: config.github.clone().map(GitHub::new),
            relay: Mutex::new(Relay::default()),
            catalog: RwLock::new(None),
            attributions: Mutex::new(Vec::new()),
            rejection_reported: AtomicBool::new(false),
            config,
        }
    }

    /// Who acted on an `account.*` stream entry, for the ops channel.
    pub fn by(&self, kind: &str, data: &Value) -> String {
        let account = data["account_id"].as_i64().unwrap_or(-1);
        let mut list = self.attributions.lock().unwrap();
        list.retain(|a| a.at.elapsed() < ATTRIBUTION_TTL);
        if let Some(i) = list
            .iter()
            .position(|a| a.kind == kind && a.account == account)
        {
            return list.remove(i).moderator;
        }
        escape(data["by"].as_str().unwrap_or("?"))
    }

    fn attribute(&self, kind: &'static str, account: i64, moderator: &str) {
        let mut list = self.attributions.lock().unwrap();
        list.retain(|a| a.at.elapsed() < ATTRIBUTION_TTL);
        if list.len() < 256 {
            list.push(Attribution {
                kind,
                account,
                moderator: escape(moderator),
                at: Instant::now(),
            });
        }
    }

    /// The reply for an outcome every command treats the same way, or `None` to let
    /// the command interpret it.
    fn trouble(&self, outcome: &Outcome) -> Option<Reply> {
        if !matches!(outcome, Outcome::Rejected) {
            self.rejection_reported.store(false, Ordering::Relaxed);
        }
        match outcome {
            Outcome::Unavailable => {
                let mut text = UNAVAILABLE.to_string();
                if let Some(why) = self.relay.lock().unwrap().condition() {
                    text = format!("{text} {why}");
                }
                Some(text.into())
            }
            Outcome::Rejected => Some(Reply {
                text: TOKEN_REJECTED.into(),
                ops: (!self.rejection_reported.swap(true, Ordering::Relaxed)).then(|| {
                    "The realm's admin API rejected the bot's token: ops needs to mint a new `bot` token and restart the bot.".into()
                }),
            }),
            Outcome::NotImplemented => {
                Some("This realm does not support that yet (the admin API route has not landed).".into())
            }
            Outcome::Refused(403, _, detail) => Some(
                format!(
                    "The bot's admin token is not allowed to do that ({}).",
                    escape(detail.as_deref().unwrap_or("forbidden"))
                )
                .into(),
            ),
            _ => None,
        }
    }

    pub async fn run(&self, inv: &Invocation) -> Reply {
        match inv.name.as_str() {
            "status" => self.status().await,
            "whois" => self.whois(inv).await,
            "kick" | "ban" | "unban" | "mute" | "unmute" => self.account(inv).await,
            "motd" => self.motd(inv).await,
            "notice" => {
                let body = json!({"text": inv.text("text").unwrap_or(""), "level": "info", "in_game": true});
                self.world(
                    self.admin.post("/v1/realm/notice", body).await,
                    "Notice sent: players see it in game, and the announcements channel gets it from the realm's event stream.",
                )
            }
            "boss" => self.boss(inv).await,
            "kill" => {
                let entity = match inv.options.get("entity") {
                    Some(Opt::Integer(n)) => *n,
                    _ => return "Which entity?".into(),
                };
                let body = json!({"entity": entity, "reason": inv.text("reason").unwrap_or("")});
                self.world(
                    self.admin.post("/v1/world/kill", body).await,
                    "Kill requested",
                )
            }
            "event" => self.event(inv).await,
            "event-stop" => {
                let body = json!({"reason": inv.text("reason").unwrap_or("via Discord")});
                self.world(
                    self.admin.post("/v1/world/event/stop", body).await,
                    "Event stop requested; the announcements channel will say when it has ended.",
                )
            }
            "deploy" => self.deploy(inv).await,
            other => format!("Unknown command `{}`", escape(other)).into(),
        }
    }

    async fn status(&self) -> Reply {
        let outcome = self.admin.get("/v1/realm/status").await;
        if let Some(r) = self.trouble(&outcome) {
            return r;
        }
        let Outcome::Ok(_, v) = outcome else {
            return UNAVAILABLE.into();
        };
        let Ok(s) = serde_json::from_value::<Status>(v) else {
            return "The realm answered with a status the bot cannot read.".into();
        };
        let yes = |b: bool| if b { "yes" } else { "no" };
        let mut lines = vec![
            "**Realm status**".to_string(),
            format!("Players online: {}", s.players),
            format!("Version: `{}`", s.version.replace('`', "'")),
            format!("Uptime: {}", uptime(s.uptime_s)),
            format!("Ready: {} · Draining: {}", yes(s.ready), yes(s.draining)),
        ];
        lines.push(match &s.deploy_pending {
            Some(p) => format!(
                "Deploy pending since {} ({} commits behind). Run `/deploy` when the realm is quiet.",
                when(&p.since),
                p.commits_behind
            ),
            None => "Deploy pending: none".into(),
        });
        if !s.redis {
            lines.push("Redis: down (realm events are not reaching Discord)".into());
        }
        lines.join("\n").into()
    }

    /// The account of the `user` option: `Ok((id, name))`, or the reply to give.
    async fn resolve(&self, inv: &Invocation) -> Result<(i64, String, Value), Reply> {
        let Some(Opt::User(user)) = inv.options.get("user") else {
            return Err("Which user?".into());
        };
        let outcome = self
            .admin
            .get(&format!("/v1/accounts/by-discord/{user}"))
            .await;
        if let Some(r) = self.trouble(&outcome) {
            return Err(r);
        }
        match outcome {
            Outcome::Ok(_, v) => {
                let id = v["id"].as_i64().unwrap_or(0);
                let name = match v["discord_name"].as_str() {
                    Some(n) => escape(n),
                    None => format!("account {id}"),
                };
                Ok((id, name, v))
            }
            Outcome::Refused(404, ..) => Err(format!(
                "<@{user}> has no account on this realm (they have never logged in with Discord)."
            )
            .into()),
            other => Err(self.refused(&other)),
        }
    }

    fn refused(&self, outcome: &Outcome) -> Reply {
        match outcome {
            Outcome::Refused(_, error, detail) => format!(
                "The realm refused it: {}{}",
                escape(error),
                detail
                    .as_deref()
                    .map(|d| format!(" ({})", escape(d)))
                    .unwrap_or_default()
            )
            .into(),
            _ => UNAVAILABLE.into(),
        }
    }

    async fn whois(&self, inv: &Invocation) -> Reply {
        let (id, name, v) = match self.resolve(inv).await {
            Ok(found) => found,
            Err(reply) => return reply,
        };
        let time = |key: &str| v[key].as_str().map(when);
        let sanction = |at: &str, until: &str, reason: &str, verb: &str| match time(at) {
            None => format!("Not {verb}"),
            Some(_) => format!(
                "{} {}: {}",
                capitalised(verb),
                time(until).map_or("permanently".into(), |t| format!("until {t}")),
                escape(v[reason].as_str().unwrap_or(""))
            ),
        };
        let characters: Vec<String> = v["characters"]
            .as_array()
            .map(|c| {
                c.iter()
                    .filter_map(|c| c["name"].as_str().map(escape))
                    .collect()
            })
            .unwrap_or_default();
        let yes = |b: bool| if b { "yes" } else { "no" };
        [
            format!("**{name}** — account {id}"),
            format!(
                "Online: {} · Sessions: {}",
                yes(v["online"].as_bool().unwrap_or(false)),
                v["sessions"].as_i64().unwrap_or(0)
            ),
            format!(
                "Created {} · Last login {}",
                time("created_at").unwrap_or_else(|| "?".into()),
                time("last_login_at").unwrap_or_else(|| "never".into())
            ),
            sanction("banned_at", "banned_until", "ban_reason", "banned"),
            sanction("muted_at", "muted_until", "mute_reason", "muted"),
            format!(
                "Characters: {}",
                if characters.is_empty() {
                    "none".into()
                } else {
                    characters.join(", ")
                }
            ),
        ]
        .join("\n")
        .into()
    }

    async fn account(&self, inv: &Invocation) -> Reply {
        let command = inv.name.as_str();
        let until = match command {
            "ban" | "mute" => match duration(inv.text("duration").unwrap_or("perm")) {
                Ok(d) => d.map(|s| rfc3339(now() + s)),
                Err(e) => return e.into(),
            },
            _ => None,
        };
        let reason = inv.text("reason").unwrap_or("");
        let (id, name, _) = match self.resolve(inv).await {
            Ok(found) => found,
            Err(reply) => return reply,
        };
        let (kind, body) = match command {
            "kick" => ("account.kicked", json!({"reason": reason})),
            "ban" => ("account.banned", json!({"reason": reason, "until": until})),
            "unban" => ("account.unbanned", json!({})),
            "mute" => ("account.muted", json!({"reason": reason, "until": until})),
            _ => ("account.unmuted", json!({})),
        };
        // Before the call: the stream entry can be rendered before the reply arrives.
        self.attribute(kind, id, &inv.user_name);
        let outcome = self
            .admin
            .post(&format!("/v1/accounts/{id}/{command}"), body)
            .await;
        if let Some(r) = self.trouble(&outcome) {
            return r;
        }
        let Outcome::Ok(_, v) = outcome else {
            return self.refused(&outcome);
        };
        let closed = v["connections_closed"].as_u64().unwrap_or(0);
        let connections = if closed == 1 {
            "connection"
        } else {
            "connections"
        };
        let span = match &until {
            Some(t) => format!("until {}", when(t)),
            None => "permanently".into(),
        };
        match command {
            "kick" => format!("Kicked {name}: {closed} {connections} closed."),
            "ban" => format!("Banned {name} {span}; {closed} {connections} closed."),
            "unban" => format!("Unbanned {name}."),
            "mute" => format!("Muted {name} {span}."),
            _ => format!("Unmuted {name}."),
        }
        .into()
    }

    async fn motd(&self, inv: &Invocation) -> Reply {
        let lines: Vec<&str> = inv
            .text("lines")
            .unwrap_or("")
            .split('|')
            .map(str::trim)
            .filter(|l| !l.is_empty())
            .collect();
        if lines.is_empty() || lines.len() > 20 || lines.iter().any(|l| l.len() > 127) {
            return "A message of the day is 1-20 lines of at most 127 bytes, separated by |."
                .into();
        }
        let n = lines.len();
        let outcome = self
            .admin
            .put("/v1/realm/motd", json!({"lines": lines}))
            .await;
        self.world(outcome, &format!("Message of the day set ({n} lines)."))
    }

    /// A command whose only interesting answer is success.
    fn world(&self, outcome: Outcome, done: &str) -> Reply {
        if let Some(r) = self.trouble(&outcome) {
            return r;
        }
        match outcome {
            Outcome::Ok(_, v) => match v["request_id"].as_str() {
                Some(id) => format!("{done} (request `{}`).", escape(id)).into(),
                None => done.into(),
            },
            other => self.refused(&other),
        }
    }

    async fn boss(&self, inv: &Invocation) -> Reply {
        let name = inv.text("name").unwrap_or("");
        if name == NO_CATALOG {
            return "The realm catalog is unavailable; try again in a minute.".into();
        }
        let mut body = json!({"name": name});
        if let Some(reason) = inv.text("reason") {
            body["reason"] = reason.into();
        }
        let outcome = self.admin.post("/v1/world/spawn", body).await;
        if let Outcome::Refused(404, ..) = outcome {
            return format!("No spawn named `{}` in the realm catalog.", escape(name)).into();
        }
        self.world(
            outcome,
            "Spawn requested; the announcements channel gets the result",
        )
    }

    async fn event(&self, inv: &Invocation) -> Reply {
        let preset = inv.text("preset").unwrap_or("");
        if preset == NO_CATALOG {
            return "The realm catalog is unavailable; try again in a minute.".into();
        }
        let body = json!({"preset": preset, "reason": inv.text("reason").unwrap_or("via Discord")});
        let outcome = self.admin.post("/v1/world/event", body).await;
        if let Outcome::Refused(409, _, detail) = &outcome {
            let active = self
                .catalog
                .read()
                .unwrap()
                .as_ref()
                .and_then(|c| c.active_event.clone())
                .or_else(|| detail.clone())
                .unwrap_or_else(|| "another preset".into());
            return format!("An event is already running: {}", escape(&active)).into();
        }
        self.world(
            outcome,
            "Event requested; the announcements channel will say when it has started",
        )
    }

    async fn deploy(&self, inv: &Invocation) -> Reply {
        let Some(github) = &self.github else {
            return "Deploy is not configured on this bot (GITHUB_DISPATCH_TOKEN is unset).".into();
        };
        let force = matches!(inv.options.get("force"), Some(Opt::Bool(true)));
        let outcome = self.admin.get("/v1/realm/status").await;
        if let Some(r) = self.trouble(&outcome) {
            return r;
        }
        let Outcome::Ok(_, v) = outcome else {
            return self.refused(&outcome);
        };
        if v["deploy_pending"].is_null() && !force {
            return "Nothing pending. Pass `force: True` to deploy anyway.".into();
        }
        let reason = inv
            .text("reason")
            .map(str::to_string)
            .unwrap_or_else(|| format!("/deploy by {}", inv.user_name));
        // GitHub's clock and ours may differ a little.
        let since = rfc3339(now() - 10);
        if let Err(e) = github.dispatch(&reason).await {
            return e.into();
        }
        match github.run_after(&since).await {
            Some(url) => format!("Deploy started: {url}").into(),
            None => {
                "Deploy dispatched; the run did not appear within 30 s, so check the repository's Actions tab.".into()
            }
        }
    }

    /// Autocomplete choices (name, value) for a focused option, at most 25.
    pub fn complete(&self, command: &str, typed: &str) -> Vec<(String, String)> {
        let catalog = self.catalog.read().unwrap();
        let Some(catalog) = catalog.as_ref() else {
            return vec![("realm catalog unavailable".into(), NO_CATALOG.into())];
        };
        let typed = typed.to_lowercase();
        let choices: Vec<(String, String)> = match command {
            "boss" => catalog
                .spawns
                .iter()
                .filter(|s| s.name.to_lowercase().contains(&typed))
                .map(|s| (s.name.clone(), s.name.clone()))
                .collect(),
            "event" => catalog
                .presets
                .iter()
                .filter(|p| {
                    p.id.to_lowercase().contains(&typed) || p.title.to_lowercase().contains(&typed)
                })
                .map(|p| (format!("{} ({})", p.title, p.id), p.id.clone()))
                .collect(),
            _ => vec![],
        };
        choices
            .into_iter()
            .take(25)
            .map(|(n, v)| (n.chars().take(100).collect(), v))
            .collect()
    }

    /// Fetches the catalog; false when the realm could not give one.
    pub async fn refresh_catalog(&self) -> bool {
        let fetched = match self.admin.get("/v1/world/catalog").await {
            Outcome::Ok(_, v) => serde_json::from_value::<Catalog>(v).ok(),
            _ => None,
        };
        let ok = fetched.is_some();
        *self.catalog.write().unwrap() = fetched;
        ok
    }

    /// The daily reminder's text when a deploy is pending (spec 05 "Daily reminder");
    /// `None` when the realm did not answer.
    pub async fn nag(&self) -> Option<Option<String>> {
        match self.admin.get("/v1/realm/status").await {
            Outcome::Ok(_, v) => {
                let p = &v["deploy_pending"];
                if p.is_null() {
                    return Some(None);
                }
                let mut relay = Relay::default();
                Some(
                    relay
                        .render("deploy.pending", p, &|_, _| String::new())
                        .pop()
                        .map(|post| post.text),
                )
            }
            _ => None,
        }
    }
}

fn capitalised(word: &str) -> String {
    let mut c = word.chars();
    c.next()
        .map(|f| f.to_uppercase().chain(c).collect())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> Config {
        let env: HashMap<String, String> = [
            ("DISCORD_BOT_TOKEN", "t"),
            ("DISCORD_GUILD_ID", "1"),
            ("DISCORD_CHANNEL_ANNOUNCE", "2"),
            ("DISCORD_CHANNEL_OPS", "3"),
            ("DISCORD_ROLE_MOD", "40"),
            ("DISCORD_ROLE_OPS", "50"),
            ("REALM_ADMIN_URL", "http://127.0.0.1:9"),
            ("REALM_ADMIN_TOKEN", "a"),
            ("REALM_REDIS", "127.0.0.1:9"),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect();
        Config::from(&env).unwrap()
    }

    #[test]
    fn role_gating() {
        let c = config();
        let (none, moderator, ops) = (vec![7], vec![7, 40], vec![50]);
        assert!(allowed("status", &none, &c));
        for command in [
            "kick",
            "ban",
            "notice",
            "boss",
            "event",
            "event-stop",
            "whois",
            "motd",
            "kill",
        ] {
            assert!(!allowed(command, &none, &c), "{command}");
            assert!(allowed(command, &moderator, &c), "{command}");
            assert!(
                allowed(command, &ops, &c),
                "OPS can do what MOD can: {command}"
            );
        }
        assert!(!allowed("deploy", &moderator, &c));
        assert!(allowed("deploy", &ops, &c));
    }

    #[test]
    fn definitions_match_the_spec_table() {
        let names: Vec<String> = definitions().into_iter().map(|c| c.name).collect();
        assert_eq!(
            names,
            [
                "status",
                "whois",
                "kick",
                "ban",
                "unban",
                "mute",
                "unmute",
                "motd",
                "notice",
                "boss",
                "kill",
                "event",
                "event-stop",
                "deploy"
            ]
        );
        for c in definitions() {
            twilight_validate::command::command(&c).unwrap();
        }
    }

    #[test]
    fn attribution_names_the_moderator_once() {
        let bot = Bot::new(config());
        bot.attribute("account.kicked", 7, "mod_alice");
        let data = json!({"account_id": 7, "by": "bot"});
        assert_eq!(bot.by("account.banned", &data), "bot");
        assert_eq!(bot.by("account.kicked", &data), r"mod\_alice");
        assert_eq!(bot.by("account.kicked", &data), "bot");
    }

    #[test]
    fn autocomplete_from_the_catalog() {
        let bot = Bot::new(config());
        assert_eq!(
            bot.complete("boss", "x"),
            vec![(
                "realm catalog unavailable".to_string(),
                NO_CATALOG.to_string()
            )]
        );
        *bot.catalog.write().unwrap() = Some(
            serde_json::from_value(json!({
                "content_hash": "h",
                "spawns": [{"index": 3, "name": "ironfang", "announce": "Ironfang!"}, {"index": 4, "name": "dread"}],
                "presets": [{"id": "weekend-exp", "title": "Weekend XP", "duration_s": 60}],
                "active_event": null
            }))
            .unwrap(),
        );
        assert_eq!(
            bot.complete("boss", "IRON"),
            vec![("ironfang".to_string(), "ironfang".to_string())]
        );
        assert_eq!(bot.complete("boss", "").len(), 2);
        assert_eq!(
            bot.complete("event", "weekend"),
            vec![(
                "Weekend XP (weekend-exp)".to_string(),
                "weekend-exp".to_string()
            )]
        );
    }

    #[test]
    fn rejection_is_reported_to_ops_once() {
        let bot = Bot::new(config());
        let first = bot.trouble(&Outcome::Rejected).unwrap();
        assert_eq!(first.text, TOKEN_REJECTED);
        assert!(first.ops.is_some());
        assert!(bot.trouble(&Outcome::Rejected).unwrap().ops.is_none());
        assert!(bot.trouble(&Outcome::Ok(200, Value::Null)).is_none());
        assert!(
            bot.trouble(&Outcome::Rejected).unwrap().ops.is_some(),
            "again after it worked"
        );
    }

    #[test]
    fn unavailable_says_why_when_the_stream_did() {
        let bot = Bot::new(config());
        assert_eq!(
            bot.trouble(&Outcome::Unavailable).unwrap().text,
            UNAVAILABLE
        );
        bot.relay.lock().unwrap().render(
            "realm.draining",
            &json!({"reason": "deploy v2", "players": 0}),
            &|_, _| String::new(),
        );
        assert_eq!(
            bot.trouble(&Outcome::Unavailable).unwrap().text,
            format!("{UNAVAILABLE} The realm is draining for a restart: deploy v2.")
        );
    }
}
