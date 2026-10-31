//! The bot's environment (spec 05 "Configuration"). Values are checked at start so a
//! typo stops the bot with a message instead of failing on the first command.

use std::collections::HashMap;
use std::net::{IpAddr, ToSocketAddrs};

/// The GitHub side of `/deploy`; absent when `GITHUB_DISPATCH_TOKEN` is unset.
#[derive(Clone)]
pub struct GitHub {
    pub api: String,
    pub repo: String,
    pub workflow: String,
    pub token: String,
}

#[derive(Clone)]
pub struct Config {
    pub discord_token: String,
    pub guild: u64,
    pub channel_announce: u64,
    pub channel_ops: u64,
    pub role_mod: u64,
    pub role_ops: u64,
    pub admin_url: String,
    pub admin_token: String,
    /// `redis://host:port`.
    pub redis: String,
    pub github: Option<GitHub>,
    pub nag_hour_utc: u32,
    /// Test-only stand-ins for Discord, both on loopback: the REST host (`host:port`,
    /// plain http) and the gateway (`ws://host:port`).
    pub discord_api_proxy: Option<String>,
    pub discord_gateway_proxy: Option<String>,
    /// The consumer name in the `bot` group: the host name.
    pub consumer: String,
}

impl std::fmt::Debug for Config {
    // Never prints a token.
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Config")
            .field("guild", &self.guild)
            .field("admin_url", &self.admin_url)
            .field("redis", &self.redis)
            .field("github", &self.github.as_ref().map(|g| &g.repo))
            .field("nag_hour_utc", &self.nag_hour_utc)
            .finish_non_exhaustive()
    }
}

fn snowflake(env: &HashMap<String, String>, name: &str) -> Result<u64, String> {
    let v = required(env, name)?;
    match v.parse::<u64>() {
        Ok(n) if n > 0 && v.len() <= 20 => Ok(n),
        _ => Err(format!("{name} must be a Discord id (digits)")),
    }
}

fn required(env: &HashMap<String, String>, name: &str) -> Result<String, String> {
    match env.get(name).map(|v| v.trim()) {
        Some(v) if !v.is_empty() => Ok(v.to_string()),
        _ => Err(format!("{name} is required")),
    }
}

fn optional(env: &HashMap<String, String>, name: &str) -> Option<String> {
    env.get(name)
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())
}

/// A test stand-in must be on this machine: `host:port` resolving to loopback only.
fn loopback(name: &str, host_port: &str) -> Result<(), String> {
    let addresses: Vec<IpAddr> = host_port
        .to_socket_addrs()
        .map_err(|_| format!("{name}: `{host_port}` is not host:port"))?
        .map(|a| a.ip())
        .collect();
    if addresses.is_empty() || !addresses.iter().all(IpAddr::is_loopback) {
        return Err(format!(
            "{name} is a test setting and must name a loopback address"
        ));
    }
    Ok(())
}

impl Config {
    pub fn from_env() -> Result<Self, String> {
        Self::from(&std::env::vars().collect())
    }

    pub fn from(env: &HashMap<String, String>) -> Result<Self, String> {
        let admin_url = required(env, "REALM_ADMIN_URL")?
            .trim_end_matches('/')
            .to_string();
        if !admin_url.starts_with("http://") && !admin_url.starts_with("https://") {
            return Err("REALM_ADMIN_URL must be an http:// address".into());
        }
        let redis = required(env, "REALM_REDIS")?;
        let redis = if redis.contains("://") {
            redis
        } else {
            format!("redis://{redis}")
        };
        let github = match optional(env, "GITHUB_DISPATCH_TOKEN") {
            None => None,
            Some(token) => {
                let api = optional(env, "GITHUB_API")
                    .unwrap_or_else(|| "https://api.github.com".into())
                    .trim_end_matches('/')
                    .to_string();
                if let Some(rest) = api.strip_prefix("http://") {
                    loopback("GITHUB_API", rest)?;
                } else if !api.starts_with("https://") {
                    return Err("GITHUB_API must be an https:// address".into());
                }
                let repo = required(env, "GITHUB_REPO")?;
                if repo.split('/').count() != 2 || repo.contains(char::is_whitespace) {
                    return Err("GITHUB_REPO must be owner/name".into());
                }
                Some(GitHub {
                    api,
                    repo,
                    workflow: optional(env, "GITHUB_WORKFLOW").unwrap_or_else(|| "cd.yml".into()),
                    token,
                })
            }
        };
        let nag_hour_utc = match optional(env, "REALM_NAG_HOUR_UTC") {
            None => 18,
            Some(v) => match v.parse::<u32>() {
                Ok(h) if h < 24 => h,
                _ => return Err("REALM_NAG_HOUR_UTC must be an hour, 0-23".into()),
            },
        };
        let discord_api_proxy = optional(env, "DISCORD_API_PROXY");
        if let Some(p) = &discord_api_proxy {
            loopback("DISCORD_API_PROXY", p)?;
        }
        let discord_gateway_proxy = optional(env, "DISCORD_GATEWAY_PROXY");
        if let Some(p) = &discord_gateway_proxy {
            let rest = p
                .strip_prefix("ws://")
                .ok_or("DISCORD_GATEWAY_PROXY must be a ws:// address")?;
            loopback("DISCORD_GATEWAY_PROXY", rest)?;
        }
        let consumer = optional(env, "HOSTNAME")
            .or_else(|| {
                std::fs::read_to_string("/etc/hostname")
                    .ok()
                    .map(|h| h.trim().to_string())
            })
            .filter(|h| !h.is_empty())
            .unwrap_or_else(|| "realm-bot".into());
        Ok(Self {
            discord_token: required(env, "DISCORD_BOT_TOKEN")?,
            guild: snowflake(env, "DISCORD_GUILD_ID")?,
            channel_announce: snowflake(env, "DISCORD_CHANNEL_ANNOUNCE")?,
            channel_ops: snowflake(env, "DISCORD_CHANNEL_OPS")?,
            role_mod: snowflake(env, "DISCORD_ROLE_MOD")?,
            role_ops: snowflake(env, "DISCORD_ROLE_OPS")?,
            admin_url,
            admin_token: required(env, "REALM_ADMIN_TOKEN")?,
            redis,
            github,
            nag_hour_utc,
            discord_api_proxy,
            discord_gateway_proxy,
            consumer,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> HashMap<String, String> {
        [
            ("DISCORD_BOT_TOKEN", "bot-token"),
            ("DISCORD_GUILD_ID", "100000000000000001"),
            ("DISCORD_CHANNEL_ANNOUNCE", "100000000000000002"),
            ("DISCORD_CHANNEL_OPS", "100000000000000003"),
            ("DISCORD_ROLE_MOD", "100000000000000004"),
            ("DISCORD_ROLE_OPS", "100000000000000005"),
            ("REALM_ADMIN_URL", "http://server:7780/"),
            ("REALM_ADMIN_TOKEN", "admin-token"),
            ("REALM_REDIS", "redis:6379"),
            ("HOSTNAME", "bot-1"),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
    }

    fn with(pairs: &[(&str, &str)]) -> Result<Config, String> {
        let mut env = base();
        for (k, v) in pairs {
            env.insert(k.to_string(), v.to_string());
        }
        Config::from(&env)
    }

    #[test]
    fn reads_the_spec_table() {
        let c = with(&[]).unwrap();
        assert_eq!(c.guild, 100000000000000001);
        assert_eq!(c.admin_url, "http://server:7780");
        assert_eq!(c.redis, "redis://redis:6379");
        assert_eq!(c.nag_hour_utc, 18);
        assert_eq!(c.consumer, "bot-1");
        assert!(c.github.is_none());
        assert!(!format!("{c:?}").contains("token"));
    }

    #[test]
    fn github_is_optional_but_whole() {
        let c = with(&[("GITHUB_DISPATCH_TOKEN", "pat"), ("GITHUB_REPO", "o/r")]).unwrap();
        let g = c.github.unwrap();
        assert_eq!(
            (g.api.as_str(), g.workflow.as_str()),
            ("https://api.github.com", "cd.yml")
        );
        assert!(with(&[("GITHUB_DISPATCH_TOKEN", "pat")]).is_err());
        assert!(with(&[("GITHUB_DISPATCH_TOKEN", "pat"), ("GITHUB_REPO", "nope")]).is_err());
    }

    #[test]
    fn refuses_bad_values() {
        for bad in [
            ("DISCORD_GUILD_ID", "general"),
            ("DISCORD_ROLE_MOD", ""),
            ("REALM_ADMIN_URL", "server:7780"),
            ("REALM_NAG_HOUR_UTC", "24"),
            ("DISCORD_API_PROXY", "10.0.0.1:443"),
            ("DISCORD_GATEWAY_PROXY", "wss://gateway.discord.gg"),
            ("DISCORD_GATEWAY_PROXY", "ws://8.8.8.8:80"),
        ] {
            assert!(with(&[bad]).is_err(), "{bad:?}");
        }
        assert!(with(&[
            ("DISCORD_API_PROXY", "127.0.0.1:9"),
            ("DISCORD_GATEWAY_PROXY", "ws://127.0.0.1:9")
        ])
        .is_ok());
        let github = [("GITHUB_DISPATCH_TOKEN", "pat"), ("GITHUB_REPO", "o/r")];
        assert!(with(&[github[0], github[1], ("GITHUB_API", "http://example.com")]).is_err());
        assert!(with(&[github[0], github[1], ("GITHUB_API", "http://127.0.0.1:9")]).is_ok());
    }
}
