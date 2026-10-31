//! Sessions, bans and mutes (specs/02-auth-sessions.md). A Discord login upserts the
//! account and mints a session token; the token logs in again until it expires or
//! is revoked. Only `sha256(raw token)` is stored. Every database step runs on the
//! account worker (accounts::Database), never on a tick. `Live` is the registry of
//! logged-in sockets an operator's kick, ban or mute reaches.
use crate::{
    accounts::Database,
    content::{bad, Result},
    discord,
};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

pub const DEFAULT_TTL_DAYS: i64 = 30;
pub const DEFAULT_MAX_PER_ACCOUNT: i64 = 5;
pub const LABEL_LIMIT: usize = 64;
pub const REASON_LIMIT: usize = 200;
/// Discord exchanges in flight at once; more are refused, not queued.
pub const EXCHANGES: usize = 16;

/// How logins are accepted on this realm.
pub struct Config {
    /// None: `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` unset; Discord login is refused.
    pub discord: Option<Arc<discord::Config>>,
    pub ttl_days: i64,
    pub max_per_account: i64,
    /// `N3E_LEGACY_LOGIN=1`: account/password `Login` (test fixtures only).
    pub legacy: bool,
    pub exchanges: Arc<tokio::sync::Semaphore>,
}
impl Config {
    /// From the environment; refuses what spec 02 forbids on `N3E_REALM=prod`.
    pub fn from_env(realm: &str) -> Result<Self> {
        let var = |k: &str| std::env::var(k).ok().filter(|v| !v.is_empty());
        let prod = realm == "prod";
        let legacy = match var("N3E_LEGACY_LOGIN").as_deref() {
            None | Some("0") => false,
            Some("1") => true,
            Some(_) => return Err(bad("N3E_LEGACY_LOGIN must be 1 or unset")),
        };
        if legacy && prod {
            return Err(bad(
                "N3E_LEGACY_LOGIN=1 is refused with N3E_REALM=prod; refusing to start",
            ));
        }
        let api = var("N3E_DISCORD_API");
        if api.is_some() && prod {
            return Err(bad(
                "N3E_DISCORD_API is a test setting, refused with N3E_REALM=prod",
            ));
        }
        let api = discord::Api::parse(api.as_deref().unwrap_or(discord::DEFAULT_API))?;
        let discord = match (var("DISCORD_CLIENT_ID"), var("DISCORD_CLIENT_SECRET")) {
            (Some(id), Some(secret)) => {
                if id.len() > 20 || !id.bytes().all(|b| b.is_ascii_digit()) {
                    return Err(bad("DISCORD_CLIENT_ID must be a Discord application id"));
                }
                Some(Arc::new(discord::Config::new(id, secret, api)?))
            }
            (None, None) if !prod => None,
            _ => {
                return Err(bad(
                    "set both DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET (required with N3E_REALM=prod)",
                ))
            }
        };
        let number = |k: &str, default: i64, max: i64| -> Result<i64> {
            match var(k) {
                None => Ok(default),
                Some(v) => v
                    .parse::<i64>()
                    .ok()
                    .filter(|n| (1..=max).contains(n))
                    .ok_or_else(|| bad(&format!("{k} must be 1..={max}"))),
            }
        };
        Ok(Self {
            discord,
            ttl_days: number("N3E_SESSION_TTL_DAYS", DEFAULT_TTL_DAYS, 3650)?,
            max_per_account: number("N3E_SESSION_MAX_PER_ACCOUNT", DEFAULT_MAX_PER_ACCOUNT, 100)?,
            legacy,
            exchanges: Arc::new(tokio::sync::Semaphore::new(EXCHANGES)),
        })
    }
}

/// A ban or a mute: until when (None: permanent) and why.
#[derive(Debug, Clone, PartialEq)]
pub struct Sanction {
    pub until: Option<i64>,
    pub reason: String,
}
impl Sanction {
    /// `<until|perm>:<reason>`, the tail of a `banned:` / `muted:` detail.
    pub fn detail(&self) -> String {
        let until = self.until.map_or("perm".into(), |u| {
            crate::admin_api::rfc3339(UNIX_EPOCH + std::time::Duration::from_secs(u.max(0) as u64))
        });
        format!("{until}:{}", self.reason)
    }
    pub fn active(&self, now: i64) -> bool {
        self.until.is_none_or(|u| u > now)
    }
}
pub fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs() as i64)
}

/// A login the server accepted.
#[derive(Debug)]
pub struct Accepted {
    pub account: i64,
    /// The raw token, for a Discord login only: sent once in LoginResult.
    pub token: Option<[u8; 32]>,
    pub expires_at: i64,
    pub discord_id: String,
    pub discord_name: String,
    pub mute: Option<Sanction>,
}

/// Why a login was refused: the `Error.detail` after `UNAUTHENTICATED`.
pub type Refused = String;

/// `active` ban/mute columns read back as a Sanction.
const SANCTIONS: &str =
    "banned_at IS NOT NULL AND (banned_until IS NULL OR banned_until>clock_timestamp()),\
 extract(epoch FROM banned_until)::bigint, coalesce(ban_reason,''),\
 muted_at IS NOT NULL AND (muted_until IS NULL OR muted_until>clock_timestamp()),\
 extract(epoch FROM muted_until)::bigint, coalesce(mute_reason,'')";
fn sanctions(row: &postgres::Row, at: usize) -> (Option<Sanction>, Option<Sanction>) {
    let ban = row.get::<_, bool>(at).then(|| Sanction {
        until: row.get(at + 1),
        reason: row.get(at + 2),
    });
    let mute = row.get::<_, bool>(at + 3).then(|| Sanction {
        until: row.get(at + 4),
        reason: row.get(at + 5),
    });
    (ban, mute)
}

/// Spec 02 `discord_login` steps 3-7, after the exchange named `who`.
pub async fn discord_login(
    db: &Database,
    who: discord::Identity,
    label: String,
    ttl_days: i64,
    max: i64,
) -> Result<std::result::Result<Accepted, Refused>> {
    let mut raw = [0u8; 32];
    openssl::rand::rand_bytes(&mut raw)?;
    let hash = openssl::sha::sha256(&raw);
    db.call(move |c| {
        let mut t = c.transaction()?;
        // The account row stays locked to the end, so two logins of one
        // account apply the cap one after the other.
        let row = t.query_one(
            &format!(
                "INSERT INTO accounts(name,discord_id,discord_name,last_login_at) VALUES('d'||$1,$1,$2,clock_timestamp()) \
                 ON CONFLICT(discord_id) DO UPDATE SET discord_name=EXCLUDED.discord_name,last_login_at=EXCLUDED.last_login_at \
                 RETURNING id,{SANCTIONS}"
            ),
            &[&who.id, &who.name],
        )?;
        let account: i64 = row.get(0);
        let (ban, mute) = sanctions(&row, 1);
        if let Some(ban) = ban {
            t.commit()?;
            return Ok(Err(format!("banned:{}", ban.detail())));
        }
        t.execute(
            "DELETE FROM sessions WHERE account_id=$1 AND (expires_at<=clock_timestamp() OR token_hash IN \
             (SELECT token_hash FROM sessions WHERE account_id=$1 AND expires_at>clock_timestamp() \
              ORDER BY created_at DESC,token_hash OFFSET $2))",
            &[&account, &(max - 1)],
        )?;
        let expires: i64 = t
            .query_one(
                "INSERT INTO sessions(token_hash,account_id,expires_at,last_seen_at,client_label) \
                 VALUES($1,$2,clock_timestamp()+$3::float8*interval '1 day',clock_timestamp(),$4) \
                 RETURNING extract(epoch FROM expires_at)::bigint",
                &[&&hash[..], &account, &(ttl_days as f64), &label],
            )?
            .get(0);
        t.commit()?;
        Ok(Ok(Accepted {
            account,
            token: Some(raw),
            expires_at: expires,
            discord_id: who.id,
            discord_name: who.name,
            mute,
        }))
    })
    .await
}

/// Spec 02 `session_login`. Expiry is checked only here.
pub async fn session_login(
    db: &Database,
    token: Vec<u8>,
    label: String,
) -> Result<std::result::Result<Accepted, Refused>> {
    if token.len() != 32 {
        return Ok(Err("revoked".into()));
    }
    let hash = openssl::sha::sha256(&token);
    db.call(move |c| {
        let mut t = c.transaction()?;
        let Some(row) = t.query_opt(
            &format!(
                "SELECT s.account_id,s.expires_at<=clock_timestamp(),extract(epoch FROM s.expires_at)::bigint,\
                 coalesce(a.discord_id,''),coalesce(a.discord_name,''),{SANCTIONS} \
                 FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=$1 FOR UPDATE OF s"
            ),
            &[&&hash[..]],
        )?
        else {
            return Ok(Err("revoked".into()));
        };
        let account: i64 = row.get(0);
        let (ban, mute) = sanctions(&row, 5);
        if row.get::<_, bool>(1) {
            t.execute("DELETE FROM sessions WHERE token_hash=$1", &[&&hash[..]])?;
            t.commit()?;
            return Ok(Err("expired".into()));
        }
        if let Some(ban) = ban {
            t.execute("DELETE FROM sessions WHERE account_id=$1", &[&account])?;
            t.commit()?;
            return Ok(Err(format!("banned:{}", ban.detail())));
        }
        t.execute(
            "UPDATE sessions SET last_seen_at=clock_timestamp(),client_label=$2 WHERE token_hash=$1",
            &[&&hash[..], &label],
        )?;
        t.execute("UPDATE accounts SET last_login_at=clock_timestamp() WHERE id=$1", &[&account])?;
        t.commit()?;
        Ok(Ok(Accepted {
            account,
            token: None,
            expires_at: row.get(2),
            discord_id: row.get(3),
            discord_name: row.get(4),
            mute,
        }))
    })
    .await
}

/// An account's mute, read at a legacy login (a Discord or session login reads it
/// with the session).
pub async fn mute(db: &Database, account: i64) -> Result<Option<Sanction>> {
    db.call(move |c| {
        let row = c.query_one(
            &format!("SELECT {SANCTIONS} FROM accounts WHERE id=$1"),
            &[&account],
        )?;
        Ok(sanctions(&row, 0).1)
    })
    .await
}

/// What the admin API says about an account (spec 03 `GET /v1/accounts/{id}`).
#[derive(Debug)]
pub struct Account {
    pub id: i64,
    pub discord_id: Option<String>,
    pub discord_name: Option<String>,
    pub created_at: i64,
    pub last_login_at: Option<i64>,
    pub banned_at: Option<i64>,
    pub banned_until: Option<i64>,
    pub ban_reason: Option<String>,
    pub muted_at: Option<i64>,
    pub muted_until: Option<i64>,
    pub mute_reason: Option<String>,
    pub sessions: i64,
    pub characters: Vec<(i64, String)>,
}
pub enum Key {
    Id(i64),
    Discord(String),
}
pub async fn account(db: &Database, key: Key, realm: String) -> Result<Option<Account>> {
    db.call(move |c| {
        let columns = "id,discord_id,discord_name,extract(epoch FROM created_at)::bigint,\
            extract(epoch FROM last_login_at)::bigint,extract(epoch FROM banned_at)::bigint,\
            extract(epoch FROM banned_until)::bigint,ban_reason,extract(epoch FROM muted_at)::bigint,\
            extract(epoch FROM muted_until)::bigint,mute_reason,\
            (SELECT count(*) FROM sessions s WHERE s.account_id=accounts.id AND s.expires_at>clock_timestamp())";
        let row = match &key {
            Key::Id(id) => c.query_opt(&format!("SELECT {columns} FROM accounts WHERE id=$1"), &[id])?,
            Key::Discord(d) => c.query_opt(&format!("SELECT {columns} FROM accounts WHERE discord_id=$1"), &[d])?,
        };
        let Some(r) = row else { return Ok(None) };
        let id: i64 = r.get(0);
        let characters = c
            .query(
                "SELECT id,name FROM characters WHERE account_id=$1 AND realm=$2 ORDER BY id LIMIT 8",
                &[&id, &realm],
            )?
            .iter()
            .map(|r| (r.get(0), r.get(1)))
            .collect();
        Ok(Some(Account {
            id,
            discord_id: r.get(1),
            discord_name: r.get(2),
            created_at: r.get(3),
            last_login_at: r.get(4),
            banned_at: r.get(5),
            banned_until: r.get(6),
            ban_reason: r.get(7),
            muted_at: r.get(8),
            muted_until: r.get(9),
            mute_reason: r.get(10),
            sessions: r.get(11),
            characters,
        }))
    })
    .await
}

/// What an operator changes on an account (spec 03 account routes).
#[derive(Debug, Clone)]
pub enum Change {
    /// Delete every session (`revoke_account`); the caller kicks.
    Revoke,
    Ban(Sanction),
    Unban,
    Mute(Sanction),
    Unmute,
}
/// Apply `change`; None when the account does not exist, else its Discord name.
/// A ban also deletes every session, like a kick.
pub async fn change(db: &Database, account: i64, change: Change) -> Result<Option<Option<String>>> {
    db.call(move |c| {
        let mut t = c.transaction()?;
        let name = match &change {
            Change::Revoke => t.query_opt("SELECT discord_name FROM accounts WHERE id=$1", &[&account])?,
            Change::Ban(s) => t.query_opt(
                "UPDATE accounts SET banned_at=clock_timestamp(),banned_until=to_timestamp($2::bigint),ban_reason=$3 \
                 WHERE id=$1 RETURNING discord_name",
                &[&account, &s.until, &s.reason],
            )?,
            Change::Unban => t.query_opt(
                "UPDATE accounts SET banned_at=NULL,banned_until=NULL,ban_reason=NULL WHERE id=$1 RETURNING discord_name",
                &[&account],
            )?,
            Change::Mute(s) => t.query_opt(
                "UPDATE accounts SET muted_at=clock_timestamp(),muted_until=to_timestamp($2::bigint),mute_reason=$3 \
                 WHERE id=$1 RETURNING discord_name",
                &[&account, &s.until, &s.reason],
            )?,
            Change::Unmute => t.query_opt(
                "UPDATE accounts SET muted_at=NULL,muted_until=NULL,mute_reason=NULL WHERE id=$1 RETURNING discord_name",
                &[&account],
            )?,
        };
        let Some(row) = name else { return Ok(None) };
        if matches!(change, Change::Revoke | Change::Ban(_)) {
            t.execute("DELETE FROM sessions WHERE account_id=$1", &[&account])?;
        }
        t.commit()?;
        Ok(Some(row.get(0)))
    })
    .await
}

/// One logged-in socket, as the admin API reaches it.
pub struct Connection {
    kick: Mutex<Option<String>>,
    kicked: tokio::sync::Notify,
    mute: Mutex<Option<Sanction>>,
}
impl Connection {
    /// Resolves once an operator kicked this socket, with the reason.
    pub async fn kicked(&self) -> String {
        loop {
            if let Some(r) = self.kick.lock().unwrap_or_else(|e| e.into_inner()).clone() {
                return r;
            }
            self.kicked.notified().await;
        }
    }
    /// The mute in force now, if any.
    pub fn muted(&self) -> Option<Sanction> {
        self.mute
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
            .filter(|m| m.active(now()))
    }
}

/// Every logged-in socket by account.
#[derive(Default)]
pub struct Live {
    accounts: Mutex<HashMap<i64, Vec<Arc<Connection>>>>,
}
impl Live {
    pub fn register(self: &Arc<Self>, account: i64, mute: Option<Sanction>) -> Registration {
        let connection = Arc::new(Connection {
            kick: Mutex::new(None),
            kicked: tokio::sync::Notify::new(),
            mute: Mutex::new(mute),
        });
        self.accounts
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .entry(account)
            .or_default()
            .push(connection.clone());
        Registration {
            live: self.clone(),
            account,
            connection,
        }
    }
    /// Ends every socket of `account`; how many there were.
    pub fn kick(&self, account: i64, reason: &str) -> usize {
        let all = self.of(account);
        for c in &all {
            *c.kick.lock().unwrap_or_else(|e| e.into_inner()) = Some(reason.into());
            c.kicked.notify_one();
        }
        all.len()
    }
    pub fn mute(&self, account: i64, mute: Option<Sanction>) {
        for c in self.of(account) {
            *c.mute.lock().unwrap_or_else(|e| e.into_inner()) = mute.clone();
        }
    }
    pub fn online(&self, account: i64) -> usize {
        self.of(account).len()
    }
    fn of(&self, account: i64) -> Vec<Arc<Connection>> {
        self.accounts
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .get(&account)
            .cloned()
            .unwrap_or_default()
    }
}

/// A socket's place in `Live`, removed when the socket ends.
pub struct Registration {
    live: Arc<Live>,
    account: i64,
    pub connection: Arc<Connection>,
}
impl Drop for Registration {
    fn drop(&mut self) {
        let mut accounts = self.live.accounts.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(list) = accounts.get_mut(&self.account) {
            list.retain(|c| !Arc::ptr_eq(c, &self.connection));
            if list.is_empty() {
                accounts.remove(&self.account);
            }
        }
    }
}

/// `YYYY-MM-DDTHH:MM:SS[.frac](Z|±HH:MM)` as Unix seconds (the admin API's `until`).
pub fn parse_rfc3339(text: &str) -> Option<i64> {
    let b = text.as_bytes();
    if b.len() < 20
        || b.len() > 40
        || b[4] != b'-'
        || b[7] != b'-'
        || !matches!(b[10], b'T' | b't')
        || b[13] != b':'
        || b[16] != b':'
    {
        return None;
    }
    let num = |r: std::ops::Range<usize>| -> Option<i64> {
        let s = text.get(r)?;
        s.bytes()
            .all(|c| c.is_ascii_digit())
            .then(|| s.parse().ok())?
    };
    let (y, mo, d, h, mi, s) = (
        num(0..4)?,
        num(5..7)?,
        num(8..10)?,
        num(11..13)?,
        num(14..16)?,
        num(17..19)?,
    );
    if !(1..=12).contains(&mo) || !(1..=31).contains(&d) || h > 23 || mi > 59 || s > 60 {
        return None;
    }
    let mut rest = &text[19..];
    if let Some(r) = rest.strip_prefix('.') {
        let digits = r.bytes().take_while(u8::is_ascii_digit).count();
        if digits == 0 {
            return None;
        }
        rest = &r[digits..];
    }
    let offset = match rest {
        "Z" | "z" => 0,
        _ if rest.len() == 6 && rest.as_bytes()[3] == b':' => {
            let sign = match rest.as_bytes()[0] {
                b'+' => 1,
                b'-' => -1,
                _ => return None,
            };
            let (oh, om) = (num_at(rest, 1)?, num_at(rest, 4)?);
            if oh > 23 || om > 59 {
                return None;
            }
            sign * (oh * 3600 + om * 60)
        }
        _ => return None,
    };
    // days from civil (proleptic Gregorian)
    let yy = if mo <= 2 { y - 1 } else { y };
    let era = yy.div_euclid(400);
    let yoe = yy - era * 400;
    let mp = (mo + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;
    Some(days * 86_400 + h * 3600 + mi * 60 + s - offset)
}
fn num_at(s: &str, at: usize) -> Option<i64> {
    let t = s.get(at..at + 2)?;
    t.bytes()
        .all(|c| c.is_ascii_digit())
        .then(|| t.parse().ok())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rfc3339_round_trips_the_admin_format() {
        for t in [0u64, 951_782_400, 1_793_405_908] {
            let text = crate::admin_api::rfc3339(UNIX_EPOCH + std::time::Duration::from_secs(t));
            assert_eq!(parse_rfc3339(&text), Some(t as i64), "{text}");
        }
        assert_eq!(
            parse_rfc3339("2026-10-31T02:18:28+02:00"),
            Some(1_793_405_908)
        );
        assert_eq!(
            parse_rfc3339("2026-10-31T00:18:28.250Z"),
            Some(1_793_405_908)
        );
        for bad in [
            "2026-10-31",
            "2026-13-01T00:00:00Z",
            "2026-10-31T00:18:28",
            "2026-10-31T00:18:28+2:00",
            "x026-10-31T00:18:28Z",
        ] {
            assert_eq!(parse_rfc3339(bad), None, "{bad}");
        }
    }

    #[test]
    fn sanction_details() {
        let s = Sanction {
            until: Some(1_793_405_908),
            reason: "spam".into(),
        };
        assert_eq!(s.detail(), "2026-10-31T00:18:28Z:spam");
        assert!(s.active(1_793_405_907) && !s.active(1_793_405_908));
        let p = Sanction {
            until: None,
            reason: "cheating".into(),
        };
        assert_eq!(p.detail(), "perm:cheating");
        assert!(p.active(i64::MAX));
    }

    #[tokio::test]
    async fn kicks_reach_every_socket_of_the_account_and_end_with_it() {
        let live = Arc::new(Live::default());
        let (a, b, other) = (
            live.register(7, None),
            live.register(7, None),
            live.register(8, None),
        );
        assert_eq!(live.online(7), 2);
        assert_eq!(live.kick(7, "spam"), 2);
        assert_eq!(a.connection.kicked().await, "spam");
        assert_eq!(b.connection.kicked().await, "spam");
        let quiet = tokio::time::timeout(
            std::time::Duration::from_millis(20),
            other.connection.kicked(),
        )
        .await;
        assert!(quiet.is_err());
        live.mute(
            8,
            Some(Sanction {
                until: None,
                reason: "x".into(),
            }),
        );
        assert!(other.connection.muted().is_some() && a.connection.muted().is_none());
        drop((a, b));
        assert_eq!(live.online(7), 0);
        assert_eq!(live.kick(7, "gone"), 0);
    }
}
