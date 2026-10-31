//! Admin API routes and permissions — normative source is `specs/03-admin-api.md`.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Method {
    Get,
    Post,
    Put,
    Delete,
}

/// One admin route and the single permission it requires.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Route {
    pub method: Method,
    /// Path template; `{id}` / `{discord_id}` are placeholders.
    pub path: &'static str,
    pub permission: &'static str,
}

/// Every route in spec 03, in spec order.
pub const ROUTES: &[Route] = &[
    Route {
        method: Method::Get,
        path: "/v1/realm/status",
        permission: "realm.status",
    },
    Route {
        method: Method::Post,
        path: "/v1/realm/drain",
        permission: "realm.drain",
    },
    Route {
        method: Method::Post,
        path: "/v1/realm/resume",
        permission: "realm.drain",
    },
    Route {
        method: Method::Post,
        path: "/v1/realm/notice",
        permission: "realm.notice",
    },
    Route {
        method: Method::Get,
        path: "/v1/realm/motd",
        permission: "realm.notice",
    },
    Route {
        method: Method::Put,
        path: "/v1/realm/motd",
        permission: "realm.notice",
    },
    Route {
        method: Method::Get,
        path: "/v1/realm/deploy-pending",
        permission: "realm.deploy",
    },
    Route {
        method: Method::Put,
        path: "/v1/realm/deploy-pending",
        permission: "realm.deploy",
    },
    Route {
        method: Method::Delete,
        path: "/v1/realm/deploy-pending",
        permission: "realm.deploy",
    },
    Route {
        method: Method::Get,
        path: "/v1/accounts/by-discord/{discord_id}",
        permission: "account.lookup",
    },
    Route {
        method: Method::Get,
        path: "/v1/accounts/{id}",
        permission: "account.lookup",
    },
    Route {
        method: Method::Post,
        path: "/v1/accounts/{id}/kick",
        permission: "account.kick",
    },
    Route {
        method: Method::Post,
        path: "/v1/accounts/{id}/ban",
        permission: "account.ban",
    },
    Route {
        method: Method::Post,
        path: "/v1/accounts/{id}/unban",
        permission: "account.ban",
    },
    Route {
        method: Method::Post,
        path: "/v1/accounts/{id}/mute",
        permission: "account.mute",
    },
    Route {
        method: Method::Post,
        path: "/v1/accounts/{id}/unmute",
        permission: "account.mute",
    },
    Route {
        method: Method::Get,
        path: "/v1/world/catalog",
        permission: "world.catalog",
    },
    Route {
        method: Method::Post,
        path: "/v1/world/spawn",
        permission: "world.spawn",
    },
    Route {
        method: Method::Post,
        path: "/v1/world/kill",
        permission: "world.kill",
    },
    Route {
        method: Method::Post,
        path: "/v1/world/event",
        permission: "world.event",
    },
    Route {
        method: Method::Post,
        path: "/v1/world/event/stop",
        permission: "world.event",
    },
    Route {
        method: Method::Post,
        path: "/v1/world/set",
        permission: "world.set",
    },
];

/// Permissions the `bot` token is minted with (spec 03 "Today's tokens").
pub const BOT_PERMISSIONS: &[&str] = &[
    "world.catalog",
    "world.spawn",
    "world.kill",
    "world.event",
    "account.lookup",
    "account.kick",
    "account.ban",
    "account.mute",
    "realm.status",
    "realm.notice",
];

/// `GET /v1/realm/status` response (subset the bot renders).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Status {
    pub version: String,
    pub content_hash: String,
    pub players: u32,
    pub draining: bool,
    pub ready: bool,
    pub uptime_s: u64,
    #[serde(default)]
    pub deploy_pending: Option<DeployPending>,
    #[serde(default = "default_true")]
    pub redis: bool,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DeployPending {
    pub since: String,
    pub commits_behind: u32,
    pub head: String,
}

/// `GET /v1/world/catalog` — what the bot builds slash-command choices from.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Catalog {
    pub content_hash: String,
    pub spawns: Vec<SpawnEntry>,
    pub presets: Vec<Preset>,
    #[serde(default)]
    pub active_event: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpawnEntry {
    pub index: u32,
    pub name: String,
    #[serde(default)]
    pub announce: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Preset {
    pub id: String,
    pub title: String,
    pub duration_s: u64,
}

/// Error body every route returns on failure.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ApiError {
    pub error: String,
    #[serde(default)]
    pub detail: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    #[test]
    fn bot_token_covers_every_route_it_exposes_and_nothing_more() {
        let needed: BTreeSet<&str> = ROUTES
            .iter()
            .filter(|r| !r.permission.starts_with("realm.d")) // drain/deploy are ops-only
            .filter(|r| r.permission != "world.set") // power-user, not exposed by the bot
            .map(|r| r.permission)
            .collect();
        let held: BTreeSet<&str> = BOT_PERMISSIONS.iter().copied().collect();
        assert_eq!(needed, held);
    }

    #[test]
    fn routes_are_unique() {
        let mut seen = BTreeSet::new();
        for r in ROUTES {
            assert!(seen.insert((r.method, r.path)), "duplicate route {:?}", r);
        }
    }

    #[test]
    fn status_parses_with_defaults() {
        let s: Status = serde_json::from_str(
            r#"{"version":"v1","content_hash":"h","players":3,"draining":false,"ready":true,"uptime_s":5}"#,
        )
        .unwrap();
        assert!(s.redis);
        assert!(s.deploy_pending.is_none());
    }
}
