//! The environment (spec 12, "`realm-edge`"). A set but empty variable reads as unset,
//! except `REALM_EDGE_TRUSTED_CIDRS`, which is required.

use std::net::{IpAddr, SocketAddr};
use std::time::Duration;

#[derive(Clone, Debug, PartialEq)]
pub struct Config {
    pub listen: SocketAddr,
    /// `host:port`, resolved at each connect so a restarted server's new address is found.
    pub upstream: String,
    pub max_connections: usize,
    pub trusted: Vec<(IpAddr, u8)>,
    /// Spec 12's 30 s ping and 75 s idle close; not settable, tests shorten them.
    pub ping_every: Duration,
    pub idle: Duration,
}

pub const LISTEN: &str = "0.0.0.0:8443";
pub const UPSTREAM: &str = "server:7777";
pub const MAX_CONNECTIONS: usize = 256;

impl Config {
    pub fn from_env() -> Result<Self, String> {
        Self::from_lookup(|k| std::env::var(k).ok())
    }
    pub fn from_lookup(get: impl Fn(&str) -> Option<String>) -> Result<Self, String> {
        let set = |k: &str| get(k).filter(|v| !v.trim().is_empty());
        let listen = listen(set("REALM_EDGE_LISTEN"))?;
        let upstream = match set("REALM_EDGE_UPSTREAM") {
            None => UPSTREAM.to_string(),
            Some(v) => {
                let v = v.trim();
                let ok = v.rsplit_once(':').is_some_and(|(host, port)| {
                    !host.is_empty() && port.parse::<u16>().is_ok_and(|p| p > 0)
                });
                if !ok {
                    return Err(format!("REALM_EDGE_UPSTREAM={v:?} is not host:port"));
                }
                v.to_string()
            }
        };
        let max_connections = match set("REALM_EDGE_MAX_CONNECTIONS") {
            None => MAX_CONNECTIONS,
            Some(v) => v
                .trim()
                .parse::<usize>()
                .ok()
                .filter(|n| (1..=u32::MAX as usize).contains(n))
                .ok_or_else(|| {
                    format!("REALM_EDGE_MAX_CONNECTIONS={v:?} is not a whole number from 1")
                })?,
        };
        let trusted = match get("REALM_EDGE_TRUSTED_CIDRS") {
            Some(v) if !v.trim().is_empty() => cidrs(&v)?,
            _ => return Err("REALM_EDGE_TRUSTED_CIDRS is required (cloudflared's network)".into()),
        };
        Ok(Self {
            listen,
            upstream,
            max_connections,
            trusted,
            ping_every: Duration::from_secs(30),
            idle: Duration::from_secs(75),
        })
    }
    pub fn trusts(&self, peer: IpAddr) -> bool {
        let peer = canonical(peer);
        self.trusted
            .iter()
            .any(|(net, bits)| within(peer, *net, *bits))
    }
}

/// `REALM_EDGE_LISTEN`, alone: `realm-edge health` needs nothing else.
pub fn listen(value: Option<String>) -> Result<SocketAddr, String> {
    match value {
        None => Ok(LISTEN.parse().expect("a socket address")),
        Some(v) => v
            .trim()
            .parse()
            .map_err(|_| format!("REALM_EDGE_LISTEN={v:?} is not address:port")),
    }
}

/// `a.b.c.d/n x::/n`, separated by commas or spaces; a bare address is a single host.
pub fn cidrs(text: &str) -> Result<Vec<(IpAddr, u8)>, String> {
    text.split(|c: char| c == ',' || c.is_whitespace())
        .filter(|s| !s.is_empty())
        .map(|s| {
            let (address, bits) = s.split_once('/').unwrap_or((s, ""));
            let address: IpAddr = address
                .parse()
                .map_err(|_| format!("REALM_EDGE_TRUSTED_CIDRS: {s:?} is not an address"))?;
            let most = if address.is_ipv4() { 32 } else { 128 };
            let bits = if bits.is_empty() {
                most
            } else {
                bits.parse::<u8>()
                    .ok()
                    .filter(|b| *b <= most)
                    .ok_or_else(|| format!("REALM_EDGE_TRUSTED_CIDRS: {s:?} has a bad prefix"))?
            };
            // A mapped IPv6 range is matched as the IPv4 range it maps.
            match (address, canonical(address)) {
                (IpAddr::V6(_), v4 @ IpAddr::V4(_)) => Ok((v4, bits.saturating_sub(96))),
                (_, a) => Ok((a, bits)),
            }
        })
        .collect()
}

/// IPv4-mapped IPv6 addresses compare, and are forwarded, as IPv4.
pub fn canonical(ip: IpAddr) -> IpAddr {
    match ip {
        IpAddr::V6(v6) => v6.to_ipv4_mapped().map(IpAddr::V4).unwrap_or(ip),
        v4 => v4,
    }
}

fn within(ip: IpAddr, net: IpAddr, bits: u8) -> bool {
    match (ip, net) {
        (IpAddr::V4(a), IpAddr::V4(n)) => {
            let mask = u32::MAX.checked_shl(32 - bits as u32).unwrap_or(0);
            u32::from(a) & mask == u32::from(n) & mask
        }
        (IpAddr::V6(a), IpAddr::V6(n)) => {
            let mask = u128::MAX.checked_shl(128 - bits as u32).unwrap_or(0);
            u128::from(a) & mask == u128::from(n) & mask
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env<'a>(pairs: &'a [(&'a str, &'a str)]) -> impl Fn(&str) -> Option<String> + 'a {
        move |k| {
            pairs
                .iter()
                .find(|(n, _)| *n == k)
                .map(|(_, v)| v.to_string())
        }
    }
    fn ip(s: &str) -> IpAddr {
        s.parse().unwrap()
    }

    #[test]
    fn defaults_and_the_required_cidrs() {
        let c = Config::from_lookup(env(&[("REALM_EDGE_TRUSTED_CIDRS", "172.18.0.0/16")])).unwrap();
        assert_eq!(c.listen, "0.0.0.0:8443".parse().unwrap());
        assert_eq!(
            (c.upstream.as_str(), c.max_connections),
            ("server:7777", 256)
        );
        let missing = Config::from_lookup(env(&[])).unwrap_err();
        assert!(missing.contains("REALM_EDGE_TRUSTED_CIDRS"), "{missing}");
        assert!(Config::from_lookup(env(&[("REALM_EDGE_TRUSTED_CIDRS", " ")])).is_err());
        assert!(Config::from_lookup(env(&[("REALM_EDGE_TRUSTED_CIDRS", "nope")])).is_err());
    }

    #[test]
    fn bad_values_name_their_variable() {
        for (key, value) in [
            ("REALM_EDGE_MAX_CONNECTIONS", "0"),
            ("REALM_EDGE_MAX_CONNECTIONS", "-3"),
            ("REALM_EDGE_MAX_CONNECTIONS", "1.5"),
            ("REALM_EDGE_LISTEN", "8443"),
            ("REALM_EDGE_UPSTREAM", "server"),
            ("REALM_EDGE_UPSTREAM", ":7777"),
            ("REALM_EDGE_UPSTREAM", "server:0"),
        ] {
            let e = Config::from_lookup(env(&[
                (key, value),
                ("REALM_EDGE_TRUSTED_CIDRS", "10.0.0.1"),
            ]))
            .unwrap_err();
            assert!(e.starts_with(key), "{key}={value}: {e}");
        }
        let c = Config::from_lookup(env(&[
            ("REALM_EDGE_MAX_CONNECTIONS", "1"),
            ("REALM_EDGE_UPSTREAM", "[::1]:7777"),
            ("REALM_EDGE_LISTEN", "[::]:9000"),
            ("REALM_EDGE_TRUSTED_CIDRS", "10.0.0.1"),
        ]))
        .unwrap();
        assert_eq!((c.max_connections, c.upstream.as_str()), (1, "[::1]:7777"));
    }

    #[test]
    fn cidrs_split_on_commas_and_spaces() {
        let c = Config {
            trusted: cidrs("10.1.0.0/16, 2001:db8::/32  127.0.0.1,::ffff:192.168.0.0/112").unwrap(),
            ..Config::from_lookup(env(&[("REALM_EDGE_TRUSTED_CIDRS", "10.0.0.1")])).unwrap()
        };
        assert!(
            c.trusts(ip("10.1.200.3"))
                && c.trusts(ip("::ffff:10.1.0.1"))
                && c.trusts(ip("2001:db8::5"))
        );
        assert!(
            c.trusts(ip("127.0.0.1")) && !c.trusts(ip("127.0.0.2")) && !c.trusts(ip("10.2.0.1"))
        );
        assert!(c.trusts(ip("192.168.4.5")) && !c.trusts(ip("192.169.0.1")));
        assert!(
            cidrs("10.0.0.0/33").is_err()
                && cidrs("::/129").is_err()
                && cidrs("10.0.0.0/x").is_err()
        );
    }
}
