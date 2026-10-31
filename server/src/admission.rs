//! Connection admission on the public listener (specs/01-connection-hardening.md).
//!
//! Every accepted socket passes drain, the global cap, the per-source concurrent
//! cap, the per-source connect rate and the pre-auth slots, in that order, before
//! a byte is read or TLS starts. A refused socket is dropped with nothing
//! written. Counters are process-lifetime atomics; the per-source table is an
//! in-memory LRU, never Redis.
use crate::content::{bad, Result};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, HashMap},
    net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr},
    sync::{
        atomic::{AtomicU64, Ordering::Relaxed},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tokio::{io::AsyncReadExt, net::TcpStream};

/// Sources remembered at once; the least recently seen goes first.
const SOURCES: usize = 65_536;
/// The rate window is this many buckets of `BUCKET` (60 s, ±5 s).
const BUCKETS: usize = 12;
const BUCKET: Duration = Duration::from_secs(5);
/// Refusals are summarised at most this often (spec 01, "Logging").
pub const SUMMARY_EVERY: Duration = Duration::from_secs(60);
/// PROXY protocol v2 signature, and the largest header accepted after it.
const PROXY_SIGNATURE: &[u8; 12] = b"\r\n\r\n\0\r\nQUIT\n";
const PROXY_BODY: usize = 216;

#[derive(Clone, Debug, PartialEq)]
pub struct Limits {
    pub max_connections: u64,
    pub ip_max_concurrent: u32,
    pub ip_connect_rate: u32,
    pub preauth_idle: Duration,
    pub preauth_slots: u64,
    pub trusted_proxies: Vec<(IpAddr, u8)>,
}
impl Limits {
    pub fn from_env() -> Result<Self> {
        fn number(key: &str, default: u64) -> Result<u64> {
            match std::env::var(key) {
                Err(_) => Ok(default),
                Ok(v) => v
                    .parse::<u64>()
                    .ok()
                    .filter(|n| *n >= 1 && *n <= u32::MAX as u64)
                    .ok_or_else(|| bad(&format!("{key}={v:?} is not a whole number from 1"))),
            }
        }
        Ok(Self {
            max_connections: number("N3E_MAX_CONNECTIONS", 64)?,
            ip_max_concurrent: number("N3E_IP_MAX_CONCURRENT", 3)? as u32,
            ip_connect_rate: number("N3E_IP_CONNECT_RATE", 10)? as u32,
            preauth_idle: Duration::from_millis(number("N3E_PREAUTH_IDLE_MS", 2000)?),
            preauth_slots: number("N3E_PREAUTH_MAX_SLOTS", 16)?,
            trusted_proxies: cidrs(&std::env::var("N3E_TRUSTED_PROXY_CIDRS").unwrap_or_default())?,
        })
    }
    pub fn trusts(&self, peer: IpAddr) -> bool {
        let peer = canonical(peer);
        self.trusted_proxies
            .iter()
            .any(|(net, bits)| within(peer, *net, *bits))
    }
}

/// `a.b.c.d/n, x::/n`; a bare address is a single host.
pub fn cidrs(text: &str) -> Result<Vec<(IpAddr, u8)>> {
    text.split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| {
            let (address, bits) = s.split_once('/').unwrap_or((s, ""));
            let address: IpAddr = address
                .parse()
                .map_err(|_| bad(&format!("N3E_TRUSTED_PROXY_CIDRS: {s:?} is not an address")))?;
            let most = if address.is_ipv4() { 32 } else { 128 };
            let bits = if bits.is_empty() {
                most
            } else {
                bits.parse::<u8>()
                    .ok()
                    .filter(|b| *b <= most)
                    .ok_or_else(|| {
                        bad(&format!("N3E_TRUSTED_PROXY_CIDRS: {s:?} has a bad prefix"))
                    })?
            };
            Ok((canonical(address), bits))
        })
        .collect()
}
fn canonical(ip: IpAddr) -> IpAddr {
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
/// The bucket a source is limited by: its IPv4 address, or its IPv6 /64.
pub fn source_key(ip: IpAddr) -> IpAddr {
    match canonical(ip) {
        IpAddr::V6(v6) => IpAddr::V6(Ipv6Addr::from(u128::from(v6) & !((1u128 << 64) - 1))),
        v4 => v4,
    }
}

#[derive(Default)]
pub struct Counters {
    pub open: AtomicU64,
    pub preauth: AtomicU64,
    pub authenticated: AtomicU64,
    pub refused_ip_concurrent: AtomicU64,
    pub refused_ip_rate: AtomicU64,
    pub refused_global: AtomicU64,
    pub refused_preauth_slots: AtomicU64,
    pub refused_draining: AtomicU64,
    pub refused_proxy: AtomicU64,
    pub preauth_timeouts: AtomicU64,
}
impl Counters {
    pub fn json(&self) -> Value {
        json!({
            "open": self.open.load(Relaxed),
            "preauth": self.preauth.load(Relaxed),
            "authenticated": self.authenticated.load(Relaxed),
            "refused_ip_concurrent": self.refused_ip_concurrent.load(Relaxed),
            "refused_ip_rate": self.refused_ip_rate.load(Relaxed),
            "refused_global": self.refused_global.load(Relaxed),
            "refused_preauth_slots": self.refused_preauth_slots.load(Relaxed),
            "refused_draining": self.refused_draining.load(Relaxed),
            "refused_proxy": self.refused_proxy.load(Relaxed),
            "preauth_timeouts": self.preauth_timeouts.load(Relaxed),
        })
    }
    fn refusals(&self) -> [u64; 7] {
        [
            self.refused_ip_concurrent.load(Relaxed),
            self.refused_ip_rate.load(Relaxed),
            self.refused_global.load(Relaxed),
            self.refused_preauth_slots.load(Relaxed),
            self.refused_draining.load(Relaxed),
            self.refused_proxy.load(Relaxed),
            self.preauth_timeouts.load(Relaxed),
        ]
    }
}
/// The once-a-minute refusal line, or None if nothing was refused since `last`.
pub fn summary(c: &Counters, last: &mut [u64; 7]) -> Option<String> {
    let now = c.refusals();
    let d: Vec<u64> = now.iter().zip(last.iter()).map(|(n, l)| n - l).collect();
    *last = now;
    d.iter().any(|n| *n > 0).then(|| {
        format!(
            "connections refused ip_concurrent={} ip_rate={} global={} preauth_slots={} draining={} proxy={} preauth_timeouts={}",
            d[0], d[1], d[2], d[3], d[4], d[5], d[6]
        )
    })
}

/// One source's open sockets and its connects per bucket.
struct Source {
    open: u32,
    bucket: u64,
    connects: [u32; BUCKETS],
    seen: u64,
}
impl Source {
    fn connects(&mut self, bucket: u64) -> u32 {
        let gap = bucket.saturating_sub(self.bucket);
        if gap as usize >= BUCKETS {
            self.connects = [0; BUCKETS];
        } else {
            for b in self.bucket + 1..=bucket {
                self.connects[b as usize % BUCKETS] = 0;
            }
        }
        self.bucket = self.bucket.max(bucket);
        self.connects.iter().sum()
    }
}
/// Per-source state, least recently seen evicted first.
#[derive(Default)]
struct Sources {
    map: HashMap<IpAddr, Source>,
    order: BTreeMap<u64, IpAddr>,
    seen: u64,
}
impl Sources {
    fn get(&mut self, key: IpAddr, bucket: u64) -> &mut Source {
        self.seen += 1;
        let seen = self.seen;
        if let Some(s) = self.map.get_mut(&key) {
            self.order.remove(&s.seen);
        } else {
            if self.map.len() >= SOURCES {
                if let Some((_, old)) = self.order.pop_first() {
                    self.map.remove(&old);
                }
            }
            self.map.insert(
                key,
                Source {
                    open: 0,
                    bucket,
                    connects: [0; BUCKETS],
                    seen,
                },
            );
        }
        self.order.insert(seen, key);
        let s = self.map.get_mut(&key).unwrap();
        s.seen = seen;
        s
    }
}

pub enum Refusal {
    Draining,
    Global,
    IpConcurrent,
    IpRate,
    PreauthSlots,
}

pub struct Gate {
    pub limits: Limits,
    pub counters: Arc<Counters>,
    sources: Mutex<Sources>,
    epoch: Instant,
}
impl Gate {
    pub fn new(limits: Limits, counters: Arc<Counters>) -> Arc<Self> {
        Arc::new(Self {
            limits,
            counters,
            sources: Mutex::new(Sources::default()),
            epoch: Instant::now(),
        })
    }
    fn bucket(&self) -> u64 {
        (self.epoch.elapsed().as_millis() / BUCKET.as_millis()) as u64
    }
    /// Steps 1-2: before the source is known (a trusted proxy names it later).
    pub fn open(self: &Arc<Self>, draining: bool) -> std::result::Result<Open, Refusal> {
        let c = &self.counters;
        if draining {
            c.refused_draining.fetch_add(1, Relaxed);
            return Err(Refusal::Draining);
        }
        if c.open.load(Relaxed) >= self.limits.max_connections {
            c.refused_global.fetch_add(1, Relaxed);
            return Err(Refusal::Global);
        }
        c.open.fetch_add(1, Relaxed);
        Ok(Open {
            gate: self.clone(),
            source: None,
            preauth: false,
            authenticated: false,
        })
    }
    /// Steps 3-5 for `source`; on success the socket holds a pre-auth slot.
    pub fn admit(&self, open: &mut Open, source: IpAddr) -> std::result::Result<(), Refusal> {
        let c = &self.counters;
        let key = source_key(source);
        let bucket = self.bucket();
        let mut sources = self.sources.lock().unwrap_or_else(|e| e.into_inner());
        let s = sources.get(key, bucket);
        if s.open >= self.limits.ip_max_concurrent {
            c.refused_ip_concurrent.fetch_add(1, Relaxed);
            return Err(Refusal::IpConcurrent);
        }
        let connects = s.connects(bucket);
        s.connects[bucket as usize % BUCKETS] =
            s.connects[bucket as usize % BUCKETS].saturating_add(1);
        if connects >= self.limits.ip_connect_rate {
            c.refused_ip_rate.fetch_add(1, Relaxed);
            return Err(Refusal::IpRate);
        }
        if c.preauth.load(Relaxed) >= self.limits.preauth_slots {
            c.refused_preauth_slots.fetch_add(1, Relaxed);
            return Err(Refusal::PreauthSlots);
        }
        s.open += 1;
        open.source = Some(key);
        c.preauth.fetch_add(1, Relaxed);
        open.preauth = true;
        Ok(())
    }
}

/// An admitted socket: holds its share of `open`, its source's count and, until
/// login, a pre-auth slot. Dropping it releases all three.
pub struct Open {
    gate: Arc<Gate>,
    source: Option<IpAddr>,
    preauth: bool,
    authenticated: bool,
}
impl Open {
    /// Login completed (spec 02): the pre-auth slot goes back.
    pub fn authenticated(&mut self) {
        let c = &self.gate.counters;
        if self.preauth {
            self.preauth = false;
            c.preauth.fetch_sub(1, Relaxed);
        }
        if !self.authenticated {
            self.authenticated = true;
            c.authenticated.fetch_add(1, Relaxed);
        }
    }
}
impl Drop for Open {
    fn drop(&mut self) {
        let c = &self.gate.counters;
        if self.preauth {
            c.preauth.fetch_sub(1, Relaxed);
        }
        if self.authenticated {
            c.authenticated.fetch_sub(1, Relaxed);
        }
        c.open.fetch_sub(1, Relaxed);
        if let Some(key) = self.source {
            let mut sources = self.gate.sources.lock().unwrap_or_else(|e| e.into_inner());
            // An evicted source has nothing left to release.
            if let Some(s) = sources.map.get_mut(&key) {
                s.open = s.open.saturating_sub(1);
            }
        }
    }
}

/// What the first bytes of an admitted socket say about its source.
pub enum Origin {
    /// A direct client, or a trusted proxy's LOCAL command: the TCP peer.
    Peer,
    /// A trusted proxy relaying for this client.
    Relayed(IpAddr),
    /// A PROXY header from a peer outside N3E_TRUSTED_PROXY_CIDRS.
    Untrusted,
}
/// Reads a PROXY v2 header if one starts the stream. TLS starts with 0x16, so a
/// direct client is told apart by its first byte; only that is peeked.
pub async fn origin(t: &mut TcpStream, peer: SocketAddr, limits: &Limits) -> Result<Origin> {
    let mut first = [0u8; 1];
    if t.peek(&mut first).await? == 0 || first[0] != PROXY_SIGNATURE[0] {
        return Ok(Origin::Peer);
    }
    if !limits.trusts(peer.ip()) {
        return Ok(Origin::Untrusted);
    }
    let mut head = [0u8; 16];
    t.read_exact(&mut head).await?;
    let length = u16::from_be_bytes([head[14], head[15]]) as usize;
    if &head[..12] != PROXY_SIGNATURE || length > PROXY_BODY {
        return Err(bad("malformed PROXY header"));
    }
    let mut body = vec![0u8; length];
    t.read_exact(&mut body).await?;
    proxied(&head, &body)
}
/// The client address in a PROXY v2 header (`head` the fixed 16 bytes).
pub fn proxied(head: &[u8; 16], body: &[u8]) -> Result<Origin> {
    match (head[12], head[13] >> 4) {
        (0x20, _) => Ok(Origin::Peer),
        (0x21, 1) if body.len() >= 12 => Ok(Origin::Relayed(IpAddr::V4(Ipv4Addr::new(
            body[0], body[1], body[2], body[3],
        )))),
        (0x21, 2) if body.len() >= 36 => {
            let mut a = [0u8; 16];
            a.copy_from_slice(&body[..16]);
            Ok(Origin::Relayed(IpAddr::V6(Ipv6Addr::from(a))))
        }
        _ => Err(bad("unsupported PROXY header")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limits(concurrent: u32, rate: u32, slots: u64) -> Limits {
        Limits {
            max_connections: 100,
            ip_max_concurrent: concurrent,
            ip_connect_rate: rate,
            preauth_idle: Duration::from_millis(2000),
            preauth_slots: slots,
            trusted_proxies: vec![],
        }
    }
    fn ip(s: &str) -> IpAddr {
        s.parse().unwrap()
    }

    #[test]
    fn checks_run_in_the_spec_order_and_release_on_drop() {
        let gate = Gate::new(limits(2, 100, 3), Arc::new(Counters::default()));
        assert!(matches!(gate.open(true), Err(Refusal::Draining)));
        let mut held = vec![];
        for _ in 0..2 {
            let mut o = gate.open(false).ok().unwrap();
            assert!(gate.admit(&mut o, ip("10.0.0.1")).is_ok());
            held.push(o);
        }
        let mut third = gate.open(false).ok().unwrap();
        assert!(matches!(
            gate.admit(&mut third, ip("10.0.0.1")),
            Err(Refusal::IpConcurrent)
        ));
        drop(third);
        let mut other = gate.open(false).ok().unwrap();
        assert!(gate.admit(&mut other, ip("10.0.0.2")).is_ok());
        let mut slotless = gate.open(false).ok().unwrap();
        assert!(matches!(
            gate.admit(&mut slotless, ip("10.0.0.3")),
            Err(Refusal::PreauthSlots)
        ));
        drop(slotless);
        held[0].authenticated();
        let c = &gate.counters;
        assert_eq!(
            (
                c.open.load(Relaxed),
                c.preauth.load(Relaxed),
                c.authenticated.load(Relaxed)
            ),
            (3, 2, 1)
        );
        let mut fourth = gate.open(false).ok().unwrap();
        assert!(gate.admit(&mut fourth, ip("10.0.0.3")).is_ok());
        drop((held, other, fourth));
        assert_eq!(
            (
                c.open.load(Relaxed),
                c.preauth.load(Relaxed),
                c.authenticated.load(Relaxed)
            ),
            (0, 0, 0)
        );
        let refused = [
            &c.refused_draining,
            &c.refused_ip_concurrent,
            &c.refused_preauth_slots,
        ];
        assert_eq!(refused.map(|r| r.load(Relaxed)), [1, 1, 1]);
        let mut again = gate.open(false).ok().unwrap();
        assert!(
            gate.admit(&mut again, ip("10.0.0.1")).is_ok(),
            "released sources admit again"
        );
    }

    #[test]
    fn the_rate_counts_refused_attempts_and_forgets_after_the_window() {
        let gate = Gate::new(limits(100, 3, 100), Arc::new(Counters::default()));
        let mut s = Source {
            open: 0,
            bucket: 0,
            connects: [0; BUCKETS],
            seen: 0,
        };
        let admitted = (0..5)
            .filter(|_| {
                let mut o = gate.open(false).ok().unwrap();
                gate.admit(&mut o, ip("192.0.2.9")).is_ok()
            })
            .count();
        assert_eq!(admitted, 3);
        assert_eq!(gate.counters.refused_ip_rate.load(Relaxed), 2);
        // The ring: counts fall out once their bucket is a window old.
        s.connects[0] = 7;
        assert_eq!(s.connects(BUCKETS as u64 - 1), 7);
        assert_eq!(s.connects(BUCKETS as u64), 0);
        s.connects[3] = 2;
        assert_eq!(s.connects(1000), 0);
    }

    #[test]
    fn the_global_cap_comes_before_the_source() {
        let mut l = limits(10, 10, 10);
        l.max_connections = 1;
        let gate = Gate::new(l, Arc::new(Counters::default()));
        let first = gate.open(false).ok().unwrap();
        assert!(matches!(gate.open(false), Err(Refusal::Global)));
        drop(first);
        assert!(gate.open(false).is_ok());
    }

    #[test]
    fn sources_bucket_ipv6_by_64_and_evict_the_least_recently_seen() {
        assert_eq!(source_key(ip("2001:db8:1:2:aaaa::1")), ip("2001:db8:1:2::"));
        assert_eq!(source_key(ip("::ffff:192.0.2.1")), ip("192.0.2.1"));
        let mut s = Sources::default();
        for i in 0..SOURCES as u32 + 1 {
            s.get(IpAddr::V4(Ipv4Addr::from(i)), 0).open = 1;
        }
        assert_eq!(s.map.len(), SOURCES);
        assert!(!s.map.contains_key(&IpAddr::V4(Ipv4Addr::from(0))));
        assert!(s.map.contains_key(&IpAddr::V4(Ipv4Addr::from(1))));
    }

    #[test]
    fn trusted_proxies_and_proxy_headers() {
        let l = Limits {
            trusted_proxies: cidrs("10.1.0.0/16, 2001:db8::/32 ,127.0.0.1").unwrap(),
            ..limits(1, 1, 1)
        };
        assert!(
            l.trusts(ip("10.1.200.3"))
                && l.trusts(ip("::ffff:10.1.0.1"))
                && l.trusts(ip("2001:db8::5"))
        );
        assert!(
            l.trusts(ip("127.0.0.1")) && !l.trusts(ip("127.0.0.2")) && !l.trusts(ip("10.2.0.1"))
        );
        assert!(cidrs("10.0.0.0/33").is_err() && cidrs("nope").is_err());
        assert!(cidrs("").unwrap().is_empty());
        let mut head = [0u8; 16];
        head[..12].copy_from_slice(PROXY_SIGNATURE);
        head[12] = 0x21;
        head[13] = 0x11;
        let v4 = [203, 0, 113, 7, 10, 1, 0, 1, 0x30, 0x39, 0x1e, 0x61];
        assert!(matches!(proxied(&head, &v4), Ok(Origin::Relayed(a)) if a == ip("203.0.113.7")));
        head[13] = 0x21;
        let mut v6 = [0u8; 36];
        v6[..16].copy_from_slice(
            &ip("2001:db8::9")
                .to_string()
                .parse::<Ipv6Addr>()
                .unwrap()
                .octets(),
        );
        assert!(matches!(proxied(&head, &v6), Ok(Origin::Relayed(a)) if a == ip("2001:db8::9")));
        head[12] = 0x20;
        assert!(matches!(proxied(&head, &[]), Ok(Origin::Peer)));
        head[12] = 0x21;
        head[13] = 0x31; // AF_UNIX
        assert!(proxied(&head, &v4).is_err());
    }

    #[test]
    fn refusals_are_summarised_by_class() {
        let c = Counters::default();
        let mut last = [0; 7];
        assert_eq!(summary(&c, &mut last), None);
        c.refused_ip_concurrent.fetch_add(1203, Relaxed);
        c.refused_draining.fetch_add(3, Relaxed);
        assert_eq!(
            summary(&c, &mut last).unwrap(),
            "connections refused ip_concurrent=1203 ip_rate=0 global=0 preauth_slots=0 draining=3 proxy=0 preauth_timeouts=0"
        );
        assert_eq!(summary(&c, &mut last), None);
    }
}
