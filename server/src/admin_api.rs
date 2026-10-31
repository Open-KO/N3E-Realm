//! Admin API (specs/03-admin-api.md): permission-scoped tokens, a loopback HTTP
//! listener the Bot and CD call, and the `realm:events` Redis stream. Everything
//! here runs off the tick: requests reach the simulation only through its
//! bounded command queue, and Postgres only on blocking threads.
use crate::cache::{self, Endpoint};
use crate::content::{bad, Result};
use crate::persistence::{self, Health};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    net::{IpAddr, SocketAddr},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::{mpsc, Semaphore},
    time::timeout,
};

/// Every permission a token can hold. A route needs exactly one; `token.*` are
/// reserved (minting is CLI-only).
pub const PERMISSIONS: &[&str] = &[
    "realm.status",
    "realm.drain",
    "realm.notice",
    "realm.deploy",
    "account.lookup",
    "account.kick",
    "account.ban",
    "account.mute",
    "world.catalog",
    "world.spawn",
    "world.kill",
    "world.event",
    "world.set",
    "token.mint",
    "token.revoke",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Method {
    Get,
    Post,
    Put,
    Delete,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Handler {
    Status,
    Drain,
    Resume,
    Notice,
    DeployGet,
    DeployPut,
    DeployDelete,
    /// In the contract, not served yet: answers 501 after the permission check.
    Later,
}

/// Every route in spec 03 with the one permission it needs.
const ROUTES: &[(Method, &str, &str, Handler)] = &[
    (
        Method::Get,
        "/v1/realm/status",
        "realm.status",
        Handler::Status,
    ),
    (
        Method::Post,
        "/v1/realm/drain",
        "realm.drain",
        Handler::Drain,
    ),
    (
        Method::Post,
        "/v1/realm/resume",
        "realm.drain",
        Handler::Resume,
    ),
    (
        Method::Post,
        "/v1/realm/notice",
        "realm.notice",
        Handler::Notice,
    ),
    (
        Method::Get,
        "/v1/realm/motd",
        "realm.notice",
        Handler::Later,
    ),
    (
        Method::Put,
        "/v1/realm/motd",
        "realm.notice",
        Handler::Later,
    ),
    (
        Method::Get,
        "/v1/realm/deploy-pending",
        "realm.deploy",
        Handler::DeployGet,
    ),
    (
        Method::Put,
        "/v1/realm/deploy-pending",
        "realm.deploy",
        Handler::DeployPut,
    ),
    (
        Method::Delete,
        "/v1/realm/deploy-pending",
        "realm.deploy",
        Handler::DeployDelete,
    ),
    (
        Method::Get,
        "/v1/accounts/by-discord/{discord_id}",
        "account.lookup",
        Handler::Later,
    ),
    (
        Method::Get,
        "/v1/accounts/{id}",
        "account.lookup",
        Handler::Later,
    ),
    (
        Method::Post,
        "/v1/accounts/{id}/kick",
        "account.kick",
        Handler::Later,
    ),
    (
        Method::Post,
        "/v1/accounts/{id}/ban",
        "account.ban",
        Handler::Later,
    ),
    (
        Method::Post,
        "/v1/accounts/{id}/unban",
        "account.ban",
        Handler::Later,
    ),
    (
        Method::Post,
        "/v1/accounts/{id}/mute",
        "account.mute",
        Handler::Later,
    ),
    (
        Method::Post,
        "/v1/accounts/{id}/unmute",
        "account.mute",
        Handler::Later,
    ),
    (
        Method::Get,
        "/v1/world/catalog",
        "world.catalog",
        Handler::Later,
    ),
    (
        Method::Post,
        "/v1/world/spawn",
        "world.spawn",
        Handler::Later,
    ),
    (Method::Post, "/v1/world/kill", "world.kill", Handler::Later),
    (
        Method::Post,
        "/v1/world/event",
        "world.event",
        Handler::Later,
    ),
    (
        Method::Post,
        "/v1/world/event/stop",
        "world.event",
        Handler::Later,
    ),
    (Method::Post, "/v1/world/set", "world.set", Handler::Later),
];

pub const DEFAULT_LISTEN: &str = "127.0.0.1:7780";
const EVENTS: &str = "realm:events";
const DEPLOY_PENDING: &str = "realm:deploy:pending";
/// Verified tokens are trusted this long, so `revoke` bites within it.
const TOKEN_CACHE: Duration = Duration::from_secs(10);
/// `last_used_at` is written at most this often per token.
const LAST_USED_EVERY: Duration = Duration::from_secs(60);
/// An uncached token not found within this is refused. One lookup runs at a time,
/// so a database that stops answering holds at most one blocking thread.
const LOOKUP: Duration = Duration::from_secs(2);
const HEAD_LIMIT: usize = 8 * 1024;
const BODY_LIMIT: usize = 16 * 1024;
const READ_TIMEOUT: Duration = Duration::from_secs(5);
/// Admin connections served at once; more are closed unanswered.
const CONNECTIONS: usize = 16;
const EVENT_QUEUE: usize = 256;
const NOTICE_TEXT: usize = 500;
/// The in-game copy fits the chat bound (simulation.rs Command::Chat).
const NOTICE_IN_GAME: usize = 256;
const DEPLOY_PENDING_BYTES: usize = 4096;

/// The realm-wide state the admin API reads and changes. Drain is memory-only:
/// a restart clears it, which is what CD wants.
pub struct Realm {
    pub draining: AtomicBool,
    /// Sockets past login, character select included.
    pub players: AtomicU64,
    started: Instant,
    events: Events,
    deploy: Mutex<Option<(Instant, Option<Value>)>>,
    /// The public listener's admission counters (spec 01).
    pub connections: Arc<crate::admission::Counters>,
}
impl Realm {
    pub fn new(events: Events) -> Self {
        Self {
            draining: AtomicBool::new(false),
            players: AtomicU64::new(0),
            started: Instant::now(),
            events,
            deploy: Mutex::new(None),
            connections: Arc::default(),
        }
    }
}

/// Counts one logged-in socket for as long as it lives.
pub struct Player(Arc<Realm>);
impl Player {
    pub fn new(realm: Arc<Realm>) -> Self {
        realm.players.fetch_add(1, Ordering::Relaxed);
        Self(realm)
    }
}
impl Drop for Player {
    fn drop(&mut self) {
        self.0.players.fetch_sub(1, Ordering::Relaxed);
    }
}

/// Fire-and-forget writer for `realm:events`: a bounded queue drained by one
/// task, so emitting never blocks a caller; overflow and Redis failures are
/// counted and dropped.
pub struct Events {
    tx: mpsc::Sender<(String, String, String)>,
    pub dropped: Arc<AtomicU64>,
}
impl Events {
    pub fn start(redis: Arc<Endpoint>) -> Self {
        let (tx, mut rx) = mpsc::channel::<(String, String, String)>(EVENT_QUEUE);
        let dropped = Arc::new(AtomicU64::new(0));
        let lost = dropped.clone();
        tokio::spawn(async move {
            while let Some((kind, ts, data)) = rx.recv().await {
                let added = cache::command(
                    &redis,
                    &[
                        "XADD", EVENTS, "MAXLEN", "~", "10000", "*", "type", &kind, "ts", &ts,
                        "data", &data,
                    ],
                )
                .await;
                if added.is_err() {
                    lost.fetch_add(1, Ordering::Relaxed);
                }
            }
        });
        Self { tx, dropped }
    }
    pub fn emit(&self, kind: &str, data: Value) {
        if self
            .tx
            .try_send((kind.into(), rfc3339(SystemTime::now()), data.to_string()))
            .is_err()
        {
            self.dropped.fetch_add(1, Ordering::Relaxed);
        }
    }
}

/// `YYYY-MM-DDTHH:MM:SSZ` in UTC (days-from-civil inverse, proleptic Gregorian).
pub fn rfc3339(t: SystemTime) -> String {
    let s = t.duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs()) as i64;
    let (days, secs) = (s.div_euclid(86_400), s.rem_euclid(86_400));
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        secs / 3600,
        secs / 60 % 60,
        secs % 60
    )
}

/// Refuse a listen address that is not loopback or RFC 1918 (spec 03).
pub async fn check_listen(address: &str) -> Result<()> {
    let resolved: Vec<SocketAddr> = tokio::net::lookup_host(address).await?.collect();
    if resolved.is_empty() {
        return Err(bad("N3E_ADMIN_LISTEN resolves to nothing"));
    }
    for a in resolved {
        let private = match a.ip() {
            IpAddr::V4(v) => v.is_loopback() || v.is_private(),
            IpAddr::V6(v) => v.is_loopback(),
        };
        if !private {
            return Err(bad(&format!(
                "N3E_ADMIN_LISTEN {address} resolves to {}, which is not loopback or RFC 1918; refusing to start",
                a.ip()
            )));
        }
    }
    Ok(())
}

/// Expand `mint`'s permission arguments: a concrete name, or `prefix.*`.
pub fn expand(requested: &[String]) -> Result<Vec<String>> {
    let mut out: Vec<String> = Vec::new();
    for p in requested {
        let matched: Vec<&str> = match p.strip_suffix(".*") {
            Some(prefix) => PERMISSIONS
                .iter()
                .copied()
                .filter(|q| q.split('.').next() == Some(prefix))
                .collect(),
            None => PERMISSIONS.iter().copied().filter(|q| q == p).collect(),
        };
        if matched.is_empty() {
            return Err(bad(&format!("unknown permission {p}")));
        }
        for m in matched {
            if !out.iter().any(|o| o == m) {
                out.push(m.into());
            }
        }
    }
    if out.is_empty() {
        return Err(bad("a token needs at least one --perm"));
    }
    Ok(out)
}

fn base64url(bytes: &[u8]) -> String {
    openssl::base64::encode_block(bytes)
        .trim_end_matches('=')
        .replace('+', "-")
        .replace('/', "_")
}
fn unbase64url(text: &str) -> Option<Vec<u8>> {
    if text.is_empty()
        || text.len() > 64
        || !text
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return None;
    }
    let mut s = text.replace('-', "+").replace('_', "/");
    while s.len() % 4 != 0 {
        s.push('=');
    }
    openssl::base64::decode_block(&s).ok()
}
fn valid_name(name: &str) -> bool {
    let b = name.as_bytes();
    !b.is_empty()
        && b.len() <= 32
        && b[0].is_ascii_lowercase()
        && b.iter()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'-')
}

/// `n3e-server admin mint|revoke|list` (spec 03 CLI). Talks to Postgres directly.
/// Returns the process exit status: 2 for `mint` on an existing name.
pub fn cli(db: &str, args: &[String]) -> Result<i32> {
    let usage = "admin mint --name NAME --perm PERM [--perm PERM ...] | admin revoke --name NAME | admin list";
    let flag = |name: &str| -> Vec<String> {
        args.windows(2)
            .filter(|w| w[0] == name)
            .map(|w| w[1].clone())
            .collect()
    };
    let mut c = persistence::connect(db)?;
    persistence::verify(&mut c)?;
    match args.first().map(String::as_str) {
        Some("mint") => {
            let name = flag("--name").pop().ok_or_else(|| bad(usage))?;
            if !valid_name(&name) {
                return Err(bad("token name must match ^[a-z][a-z0-9-]{0,31}$"));
            }
            let permissions = expand(&flag("--perm"))?;
            let mut raw = [0u8; 32];
            openssl::rand::rand_bytes(&mut raw)?;
            let hash = openssl::sha::sha256(&raw);
            let inserted = c.execute(
                "INSERT INTO admin_tokens(name,token_hash,permissions) VALUES($1,$2,$3) ON CONFLICT(name) DO NOTHING",
                &[&name, &&hash[..], &permissions],
            )?;
            if inserted == 0 {
                eprintln!("admin token {name} exists; revoke first");
                return Ok(2);
            }
            println!("{}", base64url(&raw));
            eprintln!("minted {name}: {}", permissions.join(","));
            Ok(0)
        }
        Some("revoke") => {
            let name = flag("--name").pop().ok_or_else(|| bad(usage))?;
            let n = c.execute("DELETE FROM admin_tokens WHERE name=$1", &[&name])?;
            eprintln!(
                "{}",
                if n == 0 {
                    format!("no token {name}")
                } else {
                    format!("revoked {name}")
                }
            );
            Ok(0)
        }
        Some("list") => {
            for row in c.query(
                "SELECT name,array_to_string(permissions,','),created_at::text,coalesce(last_used_at::text,'-') FROM admin_tokens ORDER BY name",
                &[],
            )? {
                let (name, perms, created, used): (String, String, String, String) =
                    (row.get(0), row.get(1), row.get(2), row.get(3));
                println!("{name}\t{perms}\tcreated {created}\tlast_used {used}");
            }
            Ok(0)
        }
        _ => Err(bad(usage)),
    }
}

struct Token {
    name: String,
    permissions: Vec<String>,
    checked: Instant,
    written: Instant,
}

/// Token verification against Postgres on a blocking thread, with the 10 s cache.
struct Tokens {
    db: String,
    cache: Mutex<HashMap<[u8; 32], Token>>,
    connection: Arc<Mutex<Option<postgres::Client>>>,
    lookup: Arc<tokio::sync::Semaphore>,
}
impl Tokens {
    async fn verify(&self, bearer: &str) -> Option<(String, Vec<String>)> {
        let raw = unbase64url(bearer).filter(|r| r.len() == 32)?;
        let hash = openssl::sha::sha256(&raw);
        let mut write_used = false;
        {
            let mut cache = self.cache.lock().unwrap_or_else(|e| e.into_inner());
            cache.retain(|_, t| t.checked.elapsed() < TOKEN_CACHE);
            if let Some(t) = cache.get_mut(&hash) {
                if t.written.elapsed() >= LAST_USED_EVERY {
                    t.written = Instant::now();
                    write_used = true;
                }
                let found = (t.name.clone(), t.permissions.clone());
                drop(cache);
                if write_used {
                    self.touch(found.0.clone());
                }
                return Some(found);
            }
        }
        let (db, connection, lookup) = (
            self.db.clone(),
            self.connection.clone(),
            self.lookup.clone(),
        );
        let row = timeout(LOOKUP, async move {
            let permit = lookup.acquire_owned().await?;
            tokio::task::spawn_blocking(move || -> Result<Option<(String, Vec<String>)>> {
            let _permit = permit;
            let mut slot = connection.lock().unwrap_or_else(|e| e.into_inner());
            if slot.is_none() {
                *slot = Some(persistence::connect(&db)?);
            }
            let c = slot.as_mut().unwrap();
            // last_used_at moves at most once a minute, whoever asks (spec 03).
            let found = c.query_opt(
                "WITH used AS (UPDATE admin_tokens SET last_used_at=clock_timestamp() WHERE token_hash=$1 \
                 AND (last_used_at IS NULL OR last_used_at<clock_timestamp()-interval '60 seconds')) \
                 SELECT name,permissions FROM admin_tokens WHERE token_hash=$1",
                &[&&hash[..]],
            );
            match found {
                Ok(r) => Ok(r.map(|r| (r.get(0), r.get(1)))),
                Err(e) => {
                    *slot = None;
                    Err(e.into())
                }
            }
        })
        .await?
        })
        .await
        .ok()?
        .ok()??;
        let now = Instant::now();
        self.cache.lock().unwrap_or_else(|e| e.into_inner()).insert(
            hash,
            Token {
                name: row.0.clone(),
                permissions: row.1.clone(),
                checked: now,
                written: now,
            },
        );
        Some(row)
    }
    /// Best effort: skipped while a lookup holds the connection.
    fn touch(&self, name: String) {
        let Ok(permit) = self.lookup.clone().try_acquire_owned() else {
            return;
        };
        let (db, connection) = (self.db.clone(), self.connection.clone());
        tokio::task::spawn_blocking(move || {
            let _permit = permit;
            let mut slot = connection.lock().unwrap_or_else(|e| e.into_inner());
            if slot.is_none() {
                *slot = persistence::connect(&db).ok();
            }
            if let Some(c) = slot.as_mut() {
                let used = "UPDATE admin_tokens SET last_used_at=clock_timestamp() WHERE name=$1 \
                            AND (last_used_at IS NULL OR last_used_at<clock_timestamp()-interval '60 seconds')";
                if c.execute(used, &[&name]).is_err() {
                    *slot = None;
                }
            }
        });
    }
}
// The sync client runs its own runtime and panics if dropped on a tokio worker,
// which is where the last Service reference goes at shutdown.
impl Drop for Tokens {
    fn drop(&mut self) {
        let mut slot = self.connection.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(c) = slot.take() {
            std::thread::spawn(move || drop(c));
        }
    }
}

/// What a handler needs from the rest of the server.
pub struct Service {
    pub realm: Arc<Realm>,
    pub health: Arc<Health>,
    pub redis: Arc<Endpoint>,
    pub commands: mpsc::Sender<crate::simulation::Command>,
    pub content_hash: String,
    tokens: Tokens,
}
impl Service {
    pub fn new(
        db: String,
        realm: Arc<Realm>,
        health: Arc<Health>,
        redis: Arc<Endpoint>,
        commands: mpsc::Sender<crate::simulation::Command>,
        content_hash: String,
    ) -> Self {
        let tokens = Tokens {
            db,
            cache: Mutex::new(HashMap::new()),
            connection: Arc::new(Mutex::new(None)),
            lookup: Arc::new(tokio::sync::Semaphore::new(1)),
        };
        Self {
            realm,
            health,
            redis,
            commands,
            content_hash,
            tokens,
        }
    }
}

/// Emit `realm.ready` / `realm.unready` on each readiness transition.
pub async fn watch_readiness(service: Arc<Service>) {
    let mut was = false;
    loop {
        let now = service.health.ready();
        if now != was {
            if now {
                service.realm.events.emit(
                    "realm.ready",
                    json!({"version": crate::BUILD_VERSION, "content_hash": service.content_hash}),
                );
            } else {
                service.realm.events.emit("realm.unready", json!({}));
            }
            was = now;
        }
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
}

/// The admin listener: one request per connection, at most `CONNECTIONS` at once.
pub async fn serve(listener: TcpListener, service: Arc<Service>) -> Result<()> {
    eprintln!("admin API listening on {}", listener.local_addr()?);
    let slots = Arc::new(Semaphore::new(CONNECTIONS));
    loop {
        let (s, _) = listener.accept().await?;
        let Ok(permit) = slots.clone().try_acquire_owned() else {
            continue;
        };
        let service = service.clone();
        tokio::spawn(async move {
            let _permit = permit;
            let _ = connection(s, service).await;
        });
    }
}

struct Request {
    method: String,
    path: String,
    bearer: Option<String>,
    body: Vec<u8>,
}

enum Read {
    Request(Request),
    Refuse(u16, Value),
}

async fn read_request(s: &mut TcpStream) -> Result<Read> {
    let mut buf = Vec::with_capacity(1024);
    let end = loop {
        if let Some(i) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
            break i;
        }
        if buf.len() > HEAD_LIMIT {
            return Ok(Read::Refuse(431, json!({"error": "headers too large"})));
        }
        let mut chunk = [0u8; 1024];
        let n = s.read(&mut chunk).await?;
        if n == 0 {
            return Err(bad("closed before the request ended"));
        }
        buf.extend_from_slice(&chunk[..n]);
    };
    let head = std::str::from_utf8(&buf[..end]).map_err(|_| bad("request head is not UTF-8"))?;
    let mut lines = head.split("\r\n");
    let mut first = lines.next().unwrap_or("").split(' ');
    let (method, path) = (
        first.next().unwrap_or("").to_string(),
        first.next().unwrap_or("").to_string(),
    );
    let (mut length, mut bearer) = (0usize, None);
    for line in lines {
        let Some((k, v)) = line.split_once(':') else {
            continue;
        };
        let v = v.trim();
        match k.trim().to_ascii_lowercase().as_str() {
            "content-length" => length = v.parse().map_err(|_| bad("content-length"))?,
            "authorization" => bearer = v.strip_prefix("Bearer ").map(|t| t.trim().to_string()),
            "transfer-encoding" => {
                return Ok(Read::Refuse(
                    411,
                    json!({"error": "content-length required"}),
                ))
            }
            _ => {}
        }
    }
    if length > BODY_LIMIT {
        return Ok(Read::Refuse(
            413,
            json!({"error": "body too large", "limit": BODY_LIMIT}),
        ));
    }
    let mut body = buf[end + 4..].to_vec();
    while body.len() < length {
        let mut chunk = [0u8; 4096];
        let n = s.read(&mut chunk).await?;
        if n == 0 {
            return Err(bad("closed before the body ended"));
        }
        body.extend_from_slice(&chunk[..n]);
    }
    body.truncate(length);
    Ok(Read::Request(Request {
        method,
        path,
        bearer,
        body,
    }))
}

async fn connection(mut s: TcpStream, service: Arc<Service>) -> Result<()> {
    let (code, body) = match timeout(READ_TIMEOUT, read_request(&mut s)).await {
        Err(_) => (408, json!({"error": "request timeout"})),
        Ok(Err(e)) => return Err(e),
        Ok(Ok(Read::Refuse(code, body))) => (code, body),
        Ok(Ok(Read::Request(r))) => respond(&service, r).await,
    };
    let text = if code == 204 {
        String::new()
    } else {
        body.to_string()
    };
    let reason = match code {
        200 => "OK",
        202 => "Accepted",
        204 => "No Content",
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        408 => "Request Timeout",
        411 => "Length Required",
        413 => "Payload Too Large",
        431 => "Request Header Fields Too Large",
        501 => "Not Implemented",
        _ => "Service Unavailable",
    };
    let response = format!(
        "HTTP/1.1 {code} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{text}",
        text.len()
    );
    timeout(READ_TIMEOUT, s.write_all(response.as_bytes())).await??;
    Ok(())
}

fn matches(template: &str, path: &str) -> bool {
    let (mut t, mut p) = (template.split('/'), path.split('/'));
    loop {
        match (t.next(), p.next()) {
            (None, None) => return true,
            (Some(a), Some(b)) if a.starts_with('{') && a.ends_with('}') => {
                if b.is_empty() {
                    return false;
                }
            }
            (Some(a), Some(b)) if a == b => {}
            _ => return false,
        }
    }
}

fn method(text: &str) -> Option<Method> {
    Some(match text {
        "GET" => Method::Get,
        "POST" => Method::Post,
        "PUT" => Method::Put,
        "DELETE" => Method::Delete,
        _ => return None,
    })
}

async fn respond(service: &Service, r: Request) -> (u16, Value) {
    let path = r.path.split('?').next().unwrap_or("");
    let candidates: Vec<_> = ROUTES
        .iter()
        .filter(|(_, t, _, _)| matches(t, path))
        .collect();
    if candidates.is_empty() {
        return (404, json!({"error": "not_found"}));
    }
    let m = method(&r.method);
    let Some(&&(_, template, permission, handler)) =
        candidates.iter().find(|(rm, _, _, _)| Some(*rm) == m)
    else {
        return (405, json!({"error": "method_not_allowed"}));
    };
    let Some(bearer) = r.bearer.as_deref() else {
        return (401, json!({"error": "unauthenticated"}));
    };
    let Some((name, permissions)) = service.tokens.verify(bearer).await else {
        return (401, json!({"error": "unauthenticated"}));
    };
    if !permissions.iter().any(|p| p == permission) {
        return (
            403,
            json!({"error": "forbidden", "detail": format!("needs {permission}")}),
        );
    }
    let body: Value = if r.body.is_empty() {
        json!({})
    } else {
        match serde_json::from_slice(&r.body) {
            Ok(v @ Value::Object(_)) => v,
            _ => {
                return (
                    400,
                    json!({"error": "bad_request", "detail": "body must be a JSON object"}),
                )
            }
        }
    };
    let (code, out) = handle(service, handler, &name, &body).await;
    if m != Some(Method::Get) {
        eprintln!(
            "admin by={name} route={} {template} result={code}",
            r.method
        );
    }
    (code, out)
}

fn text_field(
    body: &Value,
    key: &str,
    limit: usize,
) -> std::result::Result<Option<String>, (u16, Value)> {
    match body.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(s))
            if s.chars().count() <= limit && !s.chars().any(char::is_control) =>
        {
            Ok(Some(s.clone()))
        }
        Some(_) => Err((
            400,
            json!({"error": "bad_request", "detail": format!("{key}: a string of at most {limit} characters, no control characters")}),
        )),
    }
}

async fn handle(service: &Service, handler: Handler, by: &str, body: &Value) -> (u16, Value) {
    let realm = &service.realm;
    match handler {
        Handler::Status => (200, status(service).await),
        Handler::Drain => {
            let reason = match text_field(body, "reason", 160) {
                Ok(r) => r.unwrap_or_default(),
                Err(e) => return e,
            };
            let players = realm.players.load(Ordering::Relaxed);
            if !realm.draining.swap(true, Ordering::Relaxed) {
                realm.events.emit(
                    "realm.draining",
                    json!({"reason": reason, "players": players, "by": by}),
                );
            }
            (200, json!({"draining": true, "players": players}))
        }
        Handler::Resume => {
            if realm.draining.swap(false, Ordering::Relaxed) {
                realm.events.emit("realm.resumed", json!({"by": by}));
            }
            (200, json!({"draining": false}))
        }
        Handler::Notice => {
            let text = match text_field(body, "text", NOTICE_TEXT) {
                Ok(Some(t)) if !t.trim().is_empty() => t,
                Ok(_) => {
                    return (
                        400,
                        json!({"error": "bad_request", "detail": "text is required"}),
                    )
                }
                Err(e) => return e,
            };
            let level = match body.get("level").and_then(Value::as_str).unwrap_or("info") {
                "info" => 1,
                "warn" => 2,
                _ => {
                    return (
                        400,
                        json!({"error": "bad_request", "detail": "level: info or warn"}),
                    )
                }
            };
            let in_game = match body.get("in_game") {
                None | Some(Value::Null) => true,
                Some(Value::Bool(b)) => *b,
                Some(_) => {
                    return (
                        400,
                        json!({"error": "bad_request", "detail": "in_game: a boolean"}),
                    )
                }
            };
            if in_game {
                let copy: String = text.chars().take(NOTICE_IN_GAME).collect();
                let queued = timeout(
                    Duration::from_secs(1),
                    service
                        .commands
                        .send(crate::simulation::Command::Notice(copy, level)),
                )
                .await;
                if !matches!(queued, Ok(Ok(()))) {
                    return (
                        503,
                        json!({"error": "unavailable", "detail": "the simulation did not take the notice"}),
                    );
                }
            }
            let level_name = if level == 1 { "info" } else { "warn" };
            realm.events.emit(
                "notice",
                json!({"text": text, "level": level_name, "by": by}),
            );
            (202, json!({"in_game": in_game}))
        }
        Handler::DeployGet => match deploy_pending(service).await {
            Ok(Some(v)) => (200, v),
            Ok(None) => (204, Value::Null),
            Err(_) => (503, json!({"error": "unavailable", "detail": "redis"})),
        },
        Handler::DeployPut => {
            let since = match text_field(body, "since", 64) {
                Ok(Some(s)) => s,
                Ok(None) => {
                    return (
                        400,
                        json!({"error": "bad_request", "detail": "since is required"}),
                    )
                }
                Err(e) => return e,
            };
            let head = match text_field(body, "head", 64) {
                Ok(Some(s)) => s,
                Ok(None) => {
                    return (
                        400,
                        json!({"error": "bad_request", "detail": "head is required"}),
                    )
                }
                Err(e) => return e,
            };
            let Some(behind) = body
                .get("commits_behind")
                .and_then(Value::as_u64)
                .filter(|n| *n <= u64::from(u32::MAX))
            else {
                return (
                    400,
                    json!({"error": "bad_request", "detail": "commits_behind: a non-negative integer"}),
                );
            };
            let record = json!({"since": since, "commits_behind": behind, "head": head});
            let before = match deploy_pending(service).await {
                Ok(v) => v,
                Err(_) => return (503, json!({"error": "unavailable", "detail": "redis"})),
            };
            if cache::command(
                &service.redis,
                &["SET", DEPLOY_PENDING, &record.to_string()],
            )
            .await
            .is_err()
            {
                return (503, json!({"error": "unavailable", "detail": "redis"}));
            }
            *realm.deploy.lock().unwrap_or_else(|e| e.into_inner()) = None;
            if before.as_ref().and_then(|b| b.get("head")) != Some(&json!(head)) {
                realm.events.emit("deploy.pending", record.clone());
            }
            (200, record)
        }
        Handler::DeployDelete => {
            if cache::command(&service.redis, &["DEL", DEPLOY_PENDING])
                .await
                .is_err()
            {
                return (503, json!({"error": "unavailable", "detail": "redis"}));
            }
            *realm.deploy.lock().unwrap_or_else(|e| e.into_inner()) = None;
            (204, Value::Null)
        }
        Handler::Later => (501, json!({"error": "not_implemented"})),
    }
}

/// `realm:deploy:pending`, or None when absent. Read through a one-second cache
/// so `status` polling costs at most one Redis GET a second.
async fn deploy_pending(service: &Service) -> Result<Option<Value>> {
    if let Some((at, v)) = service
        .realm
        .deploy
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .as_ref()
    {
        if at.elapsed() < Duration::from_secs(1) {
            return Ok(v.clone());
        }
    }
    let v = cache::get(&service.redis, DEPLOY_PENDING, DEPLOY_PENDING_BYTES)
        .await?
        .and_then(|text| serde_json::from_str::<Value>(&text).ok());
    *service
        .realm
        .deploy
        .lock()
        .unwrap_or_else(|e| e.into_inner()) = Some((Instant::now(), v.clone()));
    Ok(v)
}

async fn status(service: &Service) -> Value {
    let redis = service.health.redis.load(Ordering::Relaxed);
    let pending = if redis {
        deploy_pending(service).await.ok().flatten()
    } else {
        None
    };
    json!({
        "version": crate::BUILD_VERSION,
        "content_hash": service.content_hash,
        "players": service.realm.players.load(Ordering::Relaxed),
        "draining": service.realm.draining.load(Ordering::Relaxed),
        "ready": service.health.ready(),
        "uptime_s": service.realm.started.elapsed().as_secs(),
        "connections": service.realm.connections.json(),
        "deploy_pending": pending,
        "redis": redis,
        "events_dropped": service.realm.events.dropped.load(Ordering::Relaxed),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn routes_match_the_bot_contract() {
        let bot: Vec<(String, &str, &str)> = realm_bot::admin::ROUTES
            .iter()
            .map(|r| (format!("{:?}", r.method), r.path, r.permission))
            .collect();
        let ours: Vec<(String, &str, &str)> = ROUTES
            .iter()
            .map(|(m, p, perm, _)| (format!("{m:?}"), *p, *perm))
            .collect();
        assert_eq!(ours, bot);
        for (_, _, perm, _) in ROUTES {
            assert!(PERMISSIONS.contains(perm), "{perm}");
        }
        for p in realm_bot::admin::BOT_PERMISSIONS {
            assert!(PERMISSIONS.contains(p), "{p}");
        }
    }

    #[test]
    fn mint_expands_globs_and_refuses_unknown_permissions() {
        let s = |v: &[&str]| v.iter().map(|x| x.to_string()).collect::<Vec<_>>();
        assert_eq!(
            expand(&s(&["realm.*"])).unwrap(),
            s(&[
                "realm.status",
                "realm.drain",
                "realm.notice",
                "realm.deploy"
            ])
        );
        assert_eq!(expand(&s(&["realm.status", "realm.*"])).unwrap().len(), 4);
        assert!(expand(&s(&["realm.restart"])).is_err());
        assert!(expand(&s(&["*"])).is_err());
        assert!(expand(&[]).is_err());
    }

    #[test]
    fn tokens_round_trip_as_unpadded_base64url() {
        let raw: Vec<u8> = (0u8..32)
            .map(|i| i.wrapping_mul(37).wrapping_add(250))
            .collect();
        let text = base64url(&raw);
        assert_eq!(text.len(), 43);
        assert!(!text.contains(['=', '+', '/']));
        assert_eq!(unbase64url(&text).unwrap(), raw);
        assert!(unbase64url("not a token").is_none());
        assert!(unbase64url("").is_none());
    }

    #[test]
    fn route_templates_match_whole_segments() {
        assert!(matches("/v1/accounts/{id}/kick", "/v1/accounts/12/kick"));
        assert!(!matches("/v1/accounts/{id}/kick", "/v1/accounts//kick"));
        assert!(!matches("/v1/accounts/{id}", "/v1/accounts/12/kick"));
        assert!(!matches("/v1/realm/status", "/v1/realm/status/x"));
    }

    #[test]
    fn names_and_timestamps() {
        assert!(
            valid_name("ops")
                && valid_name("bot-2")
                && !valid_name("Bot")
                && !valid_name("2x")
                && !valid_name("")
        );
        assert_eq!(rfc3339(UNIX_EPOCH), "1970-01-01T00:00:00Z");
        assert_eq!(
            rfc3339(UNIX_EPOCH + Duration::from_secs(1_793_405_908)),
            "2026-10-31T00:18:28Z"
        );
        assert_eq!(
            rfc3339(UNIX_EPOCH + Duration::from_secs(951_782_400)),
            "2000-02-29T00:00:00Z"
        );
    }

    #[tokio::test]
    async fn public_listen_addresses_are_refused() {
        assert!(check_listen("127.0.0.1:7780").await.is_ok());
        assert!(check_listen("10.1.2.3:7780").await.is_ok());
        assert!(check_listen("172.20.0.5:7780").await.is_ok());
        assert!(check_listen("0.0.0.0:7780").await.is_err());
        assert!(check_listen("8.8.8.8:7780").await.is_err());
        assert!(check_listen("[::]:7780").await.is_err());
    }
}
