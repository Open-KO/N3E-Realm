use crate::content::{bad, Result};
use postgres::{Client, NoTls};
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    time::{Duration, Instant},
};
pub struct Health {
    deadline: Mutex<Option<Instant>>,
    failed: AtomicBool,
    pub redis: AtomicBool,
    pub stopped: AtomicBool,
    /// Set once the game listener is bound. Readiness implies a client can
    /// connect: /ready must never answer 200 before the TLS port accepts.
    pub listening: AtomicBool,
}
impl Default for Health {
    fn default() -> Self {
        Self::new()
    }
}
impl Health {
    pub fn new() -> Self {
        Self {
            deadline: Mutex::new(None),
            failed: AtomicBool::new(false),
            redis: AtomicBool::new(false),
            stopped: AtomicBool::new(false),
            listening: AtomicBool::new(false),
        }
    }
    pub fn ready(&self) -> bool {
        self.unready().is_none()
    }
    pub fn owned(&self) -> bool {
        !self.stopped.load(Ordering::Relaxed)
            && !self.failed.load(Ordering::Relaxed)
            && self
                .deadline
                .lock()
                .unwrap()
                .map(|d| Instant::now() < d)
                .unwrap_or(false)
    }
    /// Why `ready` is false, for the log line a refused handshake writes
    /// (PQ-368); `None` while ready.
    pub fn unready(&self) -> Option<String> {
        if self.stopped.load(Ordering::Relaxed) {
            return Some("realm stopping".into());
        }
        if self.failed.load(Ordering::Relaxed) {
            return Some("realm lease lost".into());
        }
        match *self.deadline.lock().unwrap() {
            None => return Some("realm lease not yet held".into()),
            Some(d) if Instant::now() >= d => {
                return Some(format!(
                    "admission expired {} ms ago (no lease renewal)",
                    (Instant::now() - d).as_millis()
                ))
            }
            Some(_) => {}
        }
        if !self.redis.load(Ordering::Relaxed) {
            return Some("redis unreachable".into());
        }
        if !self.listening.load(Ordering::Relaxed) {
            return Some("listener not bound".into());
        }
        None
    }
    pub fn renew(&self, start: Instant) {
        *self.deadline.lock().unwrap() = Some(start + ADMISSION);
    }
    /// What is left of admission now: zero once it has ended or before the
    /// lease is held. Stopping does not shorten it (`owned` checks that); a
    /// lost lease (`invalidate`) clears it to zero (PQ-415).
    pub fn admission_left(&self) -> Duration {
        self.deadline
            .lock()
            .unwrap()
            .map(|d| d.saturating_duration_since(Instant::now()))
            .unwrap_or_default()
    }
    pub fn invalidate(&self) {
        self.failed.store(true, Ordering::Relaxed);
        *self.deadline.lock().unwrap() = None;
    }
}
/// Admission lasts this long from the start of the attempt that took or last
/// renewed the lease, 1 s inside the 3 s database lease (D-142).
pub const ADMISSION: Duration = Duration::from_secs(2);
/// The usual pause between lease renewals (D-142).
pub const RENEWAL_PAUSE: Duration = Duration::from_millis(400);
/// The pause before the next renewal attempt, from what is left of admission
/// (PQ-415, D-215): `RENEWAL_PAUSE`, cut so that the attempt starts no later
/// than `RENEWAL_PAUSE` before admission ends, and zero when that much or
/// less is left. A renewal that landed late (after admission had closed, which
/// its success reopened until 2 s after its own start) is then followed by the
/// next one instead of by the check that ends the realm. The admission bound is
/// unchanged: no attempt starts once admission has ended. A zero pause follows
/// only an attempt that itself took at least 2 s less `RENEWAL_PAUSE`, so the
/// loop cannot spin.
pub fn renewal_pause(left: Duration) -> Duration {
    RENEWAL_PAUSE.min(left.saturating_sub(RENEWAL_PAUSE))
}
/// Consecutive failed Redis probes that close admission (PQ-368, D-198).
pub const REDIS_FAILURES: u32 = 2;
/// Redis readiness from the probe results (PQ-368, D-198). Admission opens on a
/// successful probe and closes after `REDIS_FAILURES` failed probes in a row, so
/// one probe that missed its 700 ms bound (a slow name lookup or connect) does
/// not refuse handshakes while Redis serves. Login still runs its own Redis
/// check and fails closed, so no login is admitted without its rate limit.
#[derive(Default)]
pub struct RedisReadiness {
    up: bool,
    failures: u32,
}
/// What one probe changed, for the log (only changes are logged).
#[derive(Debug, PartialEq, Eq)]
pub enum RedisChange {
    None,
    Up,
    /// A failed probe that left admission open.
    Missed,
    Down,
}
impl RedisReadiness {
    pub fn probe(&mut self, ok: bool) -> RedisChange {
        if ok {
            self.failures = 0;
            return if std::mem::replace(&mut self.up, true) { RedisChange::None } else { RedisChange::Up };
        }
        self.failures = self.failures.saturating_add(1);
        if !self.up {
            RedisChange::None
        } else if self.failures >= REDIS_FAILURES {
            self.up = false;
            RedisChange::Down
        } else {
            RedisChange::Missed
        }
    }
    pub fn up(&self) -> bool {
        self.up
    }
}
fn config(url: &str) -> Result<postgres::Config> {
    let mut c: postgres::Config = url.parse()?;
    c.connect_timeout(Duration::from_secs(1));
    c.tcp_user_timeout(Duration::from_secs(2));
    c.keepalives_idle(Duration::from_secs(1));
    c.keepalives_interval(Duration::from_secs(1));
    c.keepalives_retries(2);
    c.options("-c statement_timeout=1000 -c lock_timeout=800");
    Ok(c)
}
pub fn connect(url: &str) -> Result<Client> {
    Ok(config(url)?.connect(NoTls)?)
}
/// Pause between start-up connection attempts that Postgres refused with
/// SQLSTATE 57P03 (D-140).
pub const CONNECT_RETRY: Duration = Duration::from_millis(100);
/// Realm start-up connection (D-140, PQ-155). Postgres answers SQLSTATE 57P03
/// (`cannot_connect_now`: "the database system is starting up", "... is in
/// recovery mode", "... is shutting down") while it starts or replays WAL after
/// a crash, and a realm started inside that window used to exit at its first
/// connection. This retries that one refusal, every 100 ms, until `wait` runs
/// out. Nothing durable happens before a connection exists, so a retry cannot
/// repeat an effect. Every other failure (refused socket, timeout, bad
/// credentials, unknown database) is returned at once, as from `connect`.
pub fn connect_within(url: &str, wait: Duration) -> Result<Client> {
    let config = config(url)?;
    let deadline = Instant::now() + wait;
    let mut announced = false;
    loop {
        match config.connect(NoTls) {
            Ok(c) => return Ok(c),
            Err(e)
                if e.code() == Some(&postgres::error::SqlState::CANNOT_CONNECT_NOW)
                    && Instant::now() + CONNECT_RETRY < deadline =>
            {
                if !announced {
                    announced = true;
                    eprintln!(
                        "postgres is not accepting connections yet (57P03: {}); retrying for up to {} ms",
                        e.as_db_error().map(|d| d.message()).unwrap_or_default(),
                        wait.as_millis()
                    );
                }
                std::thread::sleep(CONNECT_RETRY);
            }
            Err(e) => return Err(e.into()),
        }
    }
}
pub const MIGRATIONS: &[(i32, &str)] = &[
    (1, include_str!("../../deploy/001-foundation.sql")),
    (2, include_str!("../../deploy/002-multiplayer.sql")),
    (3, include_str!("../../deploy/003-gameplay.sql")),
    (4, include_str!("../../deploy/004-life.sql")),
    (5, include_str!("../../deploy/005-progression.sql")),
    (6, include_str!("../../deploy/006-administration.sql")),
    (7, include_str!("../../deploy/007-turbo.sql")),
    (8, include_str!("../../deploy/008-inventory.sql")),
    (9, include_str!("../../deploy/009-equipment.sql")),
    (10, include_str!("../../deploy/010-durability.sql")),
    (11, include_str!("../../deploy/011-storage.sql")),
    (12, include_str!("../../deploy/012-storage-auth.sql")),
    (13, include_str!("../../deploy/013-friends.sql")),
    (14, include_str!("../../deploy/014-party-rewards.sql")),
    (15, include_str!("../../deploy/015-reward-upgrades.sql")),
    (16, include_str!("../../deploy/016-party-loot.sql")),
    (17, include_str!("../../deploy/017-coin-drops.sql")),
    (18, include_str!("../../deploy/018-item-drops.sql")),
    (19, include_str!("../../deploy/019-consumables.sql")),
    (20, include_str!("../../deploy/020-skills.sql")),
    (21, include_str!("../../deploy/021-realm-fence.sql")),
    (22, include_str!("../../deploy/022-npc-credit.sql")),
    (23, include_str!("../../deploy/023-npc-xp.sql")),
    (24, include_str!("../../deploy/024-admin-tokens.sql")),
    (25, include_str!("../../deploy/025-discord-sessions.sql")),
];
pub fn migrate(url: &str, migrations: &[(i32, &str)]) -> Result<()> {
    let mut c = connect(url)?;
    let mut t = c.transaction()?;
    t.batch_execute("SELECT pg_advisory_xact_lock(731001); CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY, digest text NOT NULL)")?;
    for (index, &(version, sql)) in migrations.iter().enumerate() {
        if version != index as i32 + 1 {
            return Err(bad("migration order"));
        }
        let hash = digest(sql);
        if let Some(row) = t.query_opt(
            "SELECT digest FROM schema_migrations WHERE version=$1",
            &[&version],
        )? {
            if row.get::<_, String>(0) != hash {
                return Err(bad("migration checksum mismatch"));
            }
        } else {
            t.batch_execute(sql)?;
            t.execute(
                "INSERT INTO schema_migrations VALUES($1,$2)",
                &[&version, &hash],
            )?;
        }
    }
    t.commit()?;
    Ok(())
}
fn digest(sql: &str) -> String {
    openssl::sha::sha256(sql.as_bytes())
        .iter()
        .map(|x| format!("{x:02x}"))
        .collect()
}
pub fn verify(c: &mut Client) -> Result<()> {
    let rows = c.query(
        "SELECT version,digest FROM schema_migrations ORDER BY version",
        &[],
    )?;
    if rows.len() != MIGRATIONS.len() {
        return Err(bad("migration version mismatch"));
    }
    for (row, &(version, sql)) in rows.iter().zip(MIGRATIONS) {
        if row.get::<_, i32>(0) != version || row.get::<_, String>(1) != digest(sql) {
            return Err(bad("migration mismatch"));
        }
    }
    Ok(())
}
/// One takeover attempt: the new generation, or `None` while another owner's
/// lease is live. It first takes the realm's fence row (D-145), so it waits for
/// every open fenced transaction and none can commit after it; the conditional
/// upsert's conflict path then locks the lease row even when it refuses, which
/// is the only wait a renewal can have behind another process.
fn try_acquire(c: &mut Client, realm: &str, owner: &str) -> Result<Option<i64>> {
    let mut t = c.transaction()?;
    t.execute(
        "INSERT INTO realm_fence VALUES($1) ON CONFLICT(realm) DO NOTHING",
        &[&realm],
    )?;
    t.query_one("SELECT realm FROM realm_fence WHERE realm=$1 FOR UPDATE", &[&realm])?;
    let row=t.query_opt("INSERT INTO realm_ownership VALUES($1,$2,1,clock_timestamp()+interval '3 seconds') ON CONFLICT(realm) DO UPDATE SET owner=$2,generation=realm_ownership.generation+1,expires=clock_timestamp()+interval '3 seconds' WHERE realm_ownership.expires<=clock_timestamp() RETURNING generation",&[&realm,&owner])?;
    t.commit()?;
    Ok(row.map(|r| r.get(0)))
}
pub fn acquire(c: &mut Client, realm: &str, owner: &str) -> Result<i64> {
    try_acquire(c, realm, owner)?.ok_or_else(|| bad("realm already owned"))
}
/// How long realm start-up waits for a previous owner's lease (3 s, renewed
/// every 400 ms) to run out: a full lease plus 2 s for a renewal of a process
/// that already died landing late (D-139, PQ-153).
pub const START_WAIT: Duration = Duration::from_secs(5);
/// Realm start-up acquisition (D-139). A process that died without releasing
/// (crash, SIGKILL, a database restart that dropped its release) leaves its
/// lease live for up to 3 s, and a restart inside that window used to exit
/// with "realm already owned". This retries the takeover until `wait` runs
/// out, sleeping until the lease's database expiry between attempts. It never
/// takes over a live lease: each attempt is `acquire`'s conditional takeover,
/// so a live owner that keeps renewing still refuses every attempt and this
/// fails with "realm already owned". Errors are not retried (a lock timeout
/// behind a former owner's open transaction is PQ-151's). Returns the
/// generation and when the successful attempt started, from which admission
/// is measured.
pub fn acquire_within(
    c: &mut Client,
    realm: &str,
    owner: &str,
    wait: Duration,
) -> Result<(i64, Instant)> {
    let deadline = Instant::now() + wait;
    let mut announced = false;
    loop {
        let start = Instant::now();
        if let Some(generation) = try_acquire(c, realm, owner)? {
            return Ok((generation, start));
        }
        let now = Instant::now();
        if now >= deadline {
            return Err(bad("realm already owned"));
        }
        let left: f64 = c
            .query_opt(
                "SELECT extract(epoch FROM expires-clock_timestamp())::float8 FROM realm_ownership WHERE realm=$1",
                &[&realm],
            )?
            .map(|r| r.get(0))
            .unwrap_or(0.0);
        let left = if left.is_finite() { left.clamp(0.0, 3.0) } else { 0.0 };
        if !announced {
            announced = true;
            eprintln!(
                "realm {realm} is owned by another process; waiting up to {} ms for its lease to expire",
                wait.as_millis()
            );
        }
        let pause = Duration::from_secs_f64(left) + Duration::from_millis(25);
        std::thread::sleep(pause.min(deadline - now));
    }
}
pub fn renew(c: &mut Client, realm: &str, owner: &str, generation: i64) -> Result<()> {
    let n=c.execute("UPDATE realm_ownership SET expires=clock_timestamp()+interval '3 seconds' WHERE realm=$1 AND owner=$2 AND generation=$3 AND expires>clock_timestamp()",&[&realm,&owner,&generation])?;
    if n != 1 {
        return Err(bad("realm fenced"));
    }
    Ok(())
}
/// A renewal attempt that ended waiting for the realm row: lock timeout
/// (55P03), statement timeout (57014) or deadlock (40P01). Each is an ERROR
/// that aborted only this statement, so nothing was renewed and the session
/// survives (D-142).
fn renewal_wait(e: &(dyn std::error::Error + Send + Sync + 'static)) -> bool {
    e.downcast_ref::<postgres::Error>()
        .and_then(|e| e.code())
        .is_some_and(|code| ["55P03", "57014", "40P01"].contains(&code.code()))
}
/// One lease renewal, retried while it only waited for the lease row and
/// `owned` (the local admission deadline) still holds (D-142, PQ-154). Durable
/// mutations lock the separate fence row (D-145, PQ-149), so a renewal never
/// waits behind one; it can wait behind another process's takeover attempt,
/// whose upsert locks the lease row even when it refuses. Each attempt is
/// the conditional `renew`, so a lease that ran out, a takeover or a new
/// generation still fails at once ("realm fenced"), and so does every other
/// error. Admission is unchanged: it ends 2 s after the start of the last
/// successful attempt, before the database lease (3 s from that attempt's
/// commit) can run out, and no attempt starts once it has ended. Returns when
/// the successful attempt started, from which admission is measured.
pub fn renew_within(
    c: &mut Client,
    realm: &str,
    owner: &str,
    generation: i64,
    owned: impl Fn() -> bool,
) -> Result<Instant> {
    let mut announced = false;
    loop {
        let start = Instant::now();
        match renew(c, realm, owner, generation) {
            Ok(()) => return Ok(start),
            Err(e) if renewal_wait(e.as_ref()) && owned() => {
                if !announced {
                    announced = true;
                    eprintln!("lease renewal timed out waiting for the realm row ({e}); retrying while admission lasts");
                }
            }
            Err(e) => return Err(e),
        }
    }
}
/// The realm-fence row lock statement was cancelled by `statement_timeout`
/// (SQLSTATE 57014). Postgres restarts `lock_timeout` each time a queued waiter
/// is handed from the tuple lock to the next holder's transaction, but not
/// `statement_timeout`, so a waiter behind two or more holders can get 57014
/// where a waiter behind one gets 55P03. The statement ended with an ERROR,
/// not a FATAL: the transaction is aborted and the session survives (D-137).
#[derive(Debug)]
pub struct FenceWait(pub postgres::Error);
impl std::fmt::Display for FenceWait {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "realm fence wait timed out: {}", self.0)
    }
}
impl std::error::Error for FenceWait {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.0)
    }
}
/// Whether a failed claim or settlement attempt is a known rollback that may
/// be retried inside the caller's deadline: serialization failure, deadlock,
/// lock timeout, or a statement timeout on the realm-fence lock (D-137). A
/// transaction timeout (25P04) is not: it terminates the session, and the
/// callers set it to the remaining budget, so it fires only at the deadline.
pub fn retryable(e: &(dyn std::error::Error + Send + Sync + 'static)) -> bool {
    e.is::<FenceWait>()
        || e.downcast_ref::<postgres::Error>()
            .and_then(|e| e.code())
            .is_some_and(|code| ["40001", "40P01", "55P03"].contains(&code.code()))
}
/// Call inside every future durable mutation transaction, after any role lock.
/// Locks the realm's fence row until the transaction ends, so no takeover can
/// commit meanwhile, then checks owner, generation and DB-clock expiry on the
/// lease row without locking it: renewal never waits behind a fence (D-145).
pub fn fence(
    t: &mut postgres::Transaction<'_>,
    realm: &str,
    owner: &str,
    generation: i64,
) -> Result<()> {
    t.query_opt("SELECT realm FROM realm_fence WHERE realm=$1 FOR UPDATE", &[&realm])
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> {
            if e.code() == Some(&postgres::error::SqlState::QUERY_CANCELED) {
                Box::new(FenceWait(e))
            } else {
                e.into()
            }
        })?
        .ok_or_else(|| bad("realm missing"))?;
    let r = t
        .query_opt(
            "SELECT owner,generation,expires>clock_timestamp() FROM realm_ownership WHERE realm=$1",
            &[&realm],
        )?
        .ok_or_else(|| bad("realm missing"))?;
    if r.get::<_, String>(0) != owner || r.get::<_, i64>(1) != generation || !r.get::<_, bool>(2) {
        return Err(bad("stale realm generation"));
    }
    Ok(())
}
pub fn release(c: &mut Client, realm: &str, owner: &str, generation: i64) -> Result<()> {
    c.execute("UPDATE realm_ownership SET expires=clock_timestamp() WHERE realm=$1 AND owner=$2 AND generation=$3",&[&realm,&owner,&generation])?;
    Ok(())
}

/// Test scaffolding for stacked realm-fence waiters (D-137). Not under test:
/// its connections use 30 s timeouts so the scaffold itself never times out,
/// and both scaffold transactions end with a rollback (no WAL flush).
#[cfg(test)]
pub(crate) mod fence_stack {
    use super::*;
    use std::{sync::mpsc, thread::JoinHandle};
    pub(crate) struct Stack {
        /// When `stack` returned; the holder releases `first` after this.
        pub started: Instant,
        holder: JoinHandle<Result<()>>,
        waiter: JoinHandle<Result<()>>,
        stop: mpsc::Sender<()>,
    }
    fn scaffold(url: &str) -> Result<Client> {
        let mut c = connect(url)?;
        c.batch_execute("SET statement_timeout='30s'; SET lock_timeout='30s'")?;
        Ok(c)
    }
    /// A holder takes the realm's fence row, a scaffold waiter queues behind
    /// it, and this returns once the waiter is blocked. The holder releases
    /// `first` after return, or earlier at `Stack::release`; the waiter then
    /// holds the row for `second`. A
    /// production waiter that queues at once waits about `first` on the tuple
    /// lock, then on the waiter's transaction with `lock_timeout` restarted.
    pub(crate) fn stack(url: &str, realm: &str, first: Duration, second: Duration) -> Result<Stack> {
        stack_on(url, "realm_fence", realm, first, second)
    }
    /// `stack` on the realm's row of `table` (`realm_fence` or the lease row
    /// `realm_ownership`).
    pub(crate) fn stack_on(url: &str, table: &'static str, realm: &str, first: Duration, second: Duration) -> Result<Stack> {
        let lock = format!("SELECT realm FROM {table} WHERE realm=$1 FOR UPDATE");
        let (held_tx, held) = mpsc::channel();
        let (go_tx, go) = mpsc::channel::<Instant>();
        let (stop, stopped) = mpsc::channel::<()>();
        let (u, r) = (url.to_string(), realm.to_string());
        let holder = std::thread::spawn(move || -> Result<()> {
            let mut c = scaffold(&u)?;
            let mut t = c.transaction()?;
            t.query_one(lock.as_str(), &[&r])?;
            held_tx.send(()).ok();
            let start = go.recv()?;
            let _ = stopped.recv_timeout((start + first).saturating_duration_since(Instant::now()));
            t.rollback()?;
            Ok(())
        });
        held.recv_timeout(Duration::from_secs(5))?;
        let (pid_tx, pid) = mpsc::channel();
        let (u, r) = (url.to_string(), realm.to_string());
        let lock = format!("SELECT realm FROM {table} WHERE realm=$1 FOR UPDATE");
        let waiter = std::thread::spawn(move || -> Result<()> {
            let mut c = scaffold(&u)?;
            pid_tx.send(c.query_one("SELECT pg_backend_pid()", &[])?.get::<_, i32>(0)).ok();
            let mut t = c.transaction()?;
            t.query_one(lock.as_str(), &[&r])?;
            std::thread::sleep(second);
            t.rollback()?;
            Ok(())
        });
        let pid: i32 = pid.recv_timeout(Duration::from_secs(5))?;
        let mut observer = scaffold(url)?;
        let deadline = Instant::now() + Duration::from_secs(5);
        while !observer
            .query_one(
                "SELECT coalesce(bool_or(wait_event_type='Lock'),false) FROM pg_stat_activity WHERE pid=$1",
                &[&pid],
            )?
            .get::<_, bool>(0)
        {
            if Instant::now() > deadline {
                return Err(bad("fence stack waiter never queued"));
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        let started = Instant::now();
        go_tx.send(started)?;
        Ok(Stack { started, holder, waiter, stop })
    }
    impl Stack {
        /// Ends the holder's transaction now instead of at `first` (PQ-196):
        /// a test that must not race the holder's own release holds it open
        /// for a long `first` and releases it once it has observed the wait.
        pub(crate) fn release(&self) {
            self.stop.send(()).ok();
        }
        pub(crate) fn join(self) -> Result<()> {
            self.holder.join().map_err(|_| bad("fence stack holder panicked"))??;
            self.waiter.join().map_err(|_| bad("fence stack waiter panicked"))??;
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires an isolated PostgreSQL URL; run by tests/compose.py"]
    fn ownership_generation_and_atomic_fence() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = connect(&url)?;
        let realm = format!("ownership-test-{}", std::process::id());
        let first = acquire(&mut c, &realm, "first")?;
        assert!(acquire(&mut c, &realm, "second").is_err());
        let mut t = c.transaction()?;
        fence(&mut t, &realm, "first", first)?;
        t.rollback()?;
        renew(&mut c, &realm, "first", first)?;
        std::thread::sleep(Duration::from_millis(3100));
        assert!(renew(&mut c, &realm, "first", first).is_err());
        let second = acquire(&mut c, &realm, "second")?;
        assert!(second > first);
        let mut t = c.transaction()?;
        assert!(fence(&mut t, &realm, "first", first).is_err());
        fence(&mut t, &realm, "second", second)?;
        t.rollback()?;
        release(&mut c, &realm, "first", first)?;
        let mut t = c.transaction()?;
        fence(&mut t, &realm, "second", second)?;
        t.rollback()?;
        // D-137. Behind one long holder the fence wait ends in a lock timeout
        // (55P03), retried by claims and settlements.
        let s = fence_stack::stack(&url, &realm, Duration::from_millis(1200), Duration::ZERO)?;
        let mut t = c.transaction()?;
        let e = fence(&mut t, &realm, "second", second).unwrap_err();
        drop(t);
        s.join()?;
        assert!(!e.is::<FenceWait>(), "{e}");
        assert_eq!(
            e.downcast_ref::<postgres::Error>().and_then(|e| e.code()),
            Some(&postgres::error::SqlState::LOCK_NOT_AVAILABLE),
            "{e}"
        );
        assert!(retryable(e.as_ref()));
        // Behind two holders, each wait stays under lock_timeout (800 ms) but
        // the statement passes statement_timeout (1000 ms): 57014, reported as
        // a FenceWait, also retried. The session survives the cancel.
        let s = fence_stack::stack(&url, &realm, Duration::from_millis(500), Duration::from_millis(900))?;
        let mut t = c.transaction()?;
        let e = fence(&mut t, &realm, "second", second).unwrap_err();
        let waited = s.started.elapsed();
        drop(t);
        s.join()?;
        let wait = e.downcast_ref::<FenceWait>().unwrap_or_else(|| panic!("{e}"));
        assert_eq!(wait.0.code(), Some(&postgres::error::SqlState::QUERY_CANCELED));
        assert!(waited < Duration::from_millis(1400), "{waited:?}");
        assert!(retryable(e.as_ref()));
        assert_eq!(c.query_one("SELECT 1", &[])?.get::<_, i32>(0), 1);
        // A transaction timeout (25P04) terminates the session, so no attempt
        // can be retried on that connection; it is never retryable.
        let mut t = c.transaction()?;
        t.query_one("SELECT set_config('transaction_timeout','200ms',true)", &[])?;
        std::thread::sleep(Duration::from_millis(400));
        let e: Box<dyn std::error::Error + Send + Sync> =
            t.query_one("SELECT 1", &[]).unwrap_err().into();
        drop(t);
        assert!(!retryable(e.as_ref()), "{e}");
        assert!(c.query_one("SELECT 1", &[]).is_err() && c.is_closed());
        let mut c = connect(&url)?;
        release(&mut c, &realm, "second", second)?;
        c.execute("DELETE FROM realm_ownership WHERE realm=$1", &[&realm])?;
        c.execute("DELETE FROM realm_fence WHERE realm=$1", &[&realm])?;
        Ok(())
    }
    /// D-139 (PQ-153): a start-up inside a dead owner's lease waits it out; a
    /// live owner that keeps renewing is never taken over.
    #[test]
    #[ignore = "requires an isolated PostgreSQL URL; run by tests/gameplay.py and tests/multiplayer.py"]
    fn start_waits_out_a_dead_owner_and_never_takes_a_live_one() -> Result<()> {
        use std::sync::Arc;
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = connect(&url)?;
        let realm = format!("start-wait-test-{}", std::process::id());
        // A process that died without releasing (SIGKILL, or a database
        // restart that dropped its release): the lease stays live for 3 s.
        // Taken before the acquire, so the bounds below never charge its round
        // trip to the wait (PQ-153 review, PQ-155).
        let killed = Instant::now();
        let dead = acquire(&mut c, &realm, "dead")?;
        // The pre-D-139 start-up: refused at once inside the lease.
        let e = acquire(&mut c, &realm, "fast").unwrap_err();
        assert!(e.to_string().contains("realm already owned"), "{e}");
        let (new, start) = acquire_within(&mut c, &realm, "new", START_WAIT)?;
        let waited = killed.elapsed();
        assert!(new > dead);
        assert!(
            waited >= Duration::from_millis(2800) && waited < START_WAIT,
            "{waited:?}"
        );
        // Admission is measured from the attempt that took ownership.
        assert!(start.duration_since(killed) >= Duration::from_millis(2800));
        assert!(renew(&mut c, &realm, "dead", dead).is_err());
        let mut t = c.transaction()?;
        assert!(fence(&mut t, &realm, "dead", dead).is_err());
        drop(t);
        renew(&mut c, &realm, "new", new)?;
        // A live owner renewing every 400 ms (the server's cadence) refuses
        // every attempt for longer than one lease.
        let stop = Arc::new(AtomicBool::new(false));
        let renewer = {
            let (url, realm, stop) = (url.clone(), realm.clone(), stop.clone());
            std::thread::spawn(move || -> Result<u32> {
                let mut r = connect(&url)?;
                let mut renewals = 0;
                while !stop.load(Ordering::Relaxed) {
                    std::thread::sleep(Duration::from_millis(400));
                    renew(&mut r, &realm, "new", new)?;
                    renewals += 1;
                }
                Ok(renewals)
            })
        };
        let tried = Instant::now();
        let e = acquire_within(&mut c, &realm, "intruder", Duration::from_secs(4)).unwrap_err();
        let refused = tried.elapsed();
        stop.store(true, Ordering::Relaxed);
        let renewals = renewer.join().map_err(|_| bad("renewer panicked"))??;
        assert!(e.to_string().contains("realm already owned"), "{e}");
        assert!(refused >= Duration::from_secs(4), "{refused:?}");
        assert!(renewals >= 5, "{renewals}");
        let row = c.query_one(
            "SELECT owner,generation FROM realm_ownership WHERE realm=$1",
            &[&realm],
        )?;
        assert_eq!((row.get::<_, String>(0), row.get::<_, i64>(1)), ("new".into(), new));
        renew(&mut c, &realm, "new", new)?;
        // A released lease is taken at the first attempt.
        release(&mut c, &realm, "new", new)?;
        let tried = Instant::now();
        let (next, _) = acquire_within(&mut c, &realm, "next", START_WAIT)?;
        assert!(next > new && tried.elapsed() < Duration::from_secs(1));
        release(&mut c, &realm, "next", next)?;
        c.execute("DELETE FROM realm_ownership WHERE realm=$1", &[&realm])?;
        c.execute("DELETE FROM realm_fence WHERE realm=$1", &[&realm])?;
        Ok(())
    }
    /// D-142 (PQ-154): a renewal queued behind a holder of the lease row past
    /// `lock_timeout` is retried while admission lasts; it is never retried
    /// past admission, and a fenced renewal is never retried. Since D-145 a
    /// durable write never holds the lease row (the holder here stands for
    /// another process's takeover attempt or an operator's lock).
    #[test]
    #[ignore = "requires an isolated PostgreSQL URL; run by tests/gameplay.py and tests/multiplayer.py"]
    fn renewal_rides_out_a_realm_row_wait_inside_admission() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = connect(&url)?;
        let realm = format!("renew-wait-test-{}", std::process::id());
        let g = acquire(&mut c, &realm, "owner")?;
        // The pre-D-142 renewal: one attempt behind a 1.2 s holder ends in a
        // lock timeout, which ended the realm process (PQ-154).
        let lease = |first| fence_stack::stack_on(&url, "realm_ownership", &realm, first, Duration::ZERO);
        let s = lease(Duration::from_millis(1200))?;
        let e = renew(&mut c, &realm, "owner", g).unwrap_err();
        s.join()?;
        assert_eq!(
            e.downcast_ref::<postgres::Error>().and_then(|e| e.code()),
            Some(&postgres::error::SqlState::LOCK_NOT_AVAILABLE),
            "{e}"
        );
        renew(&mut c, &realm, "owner", g)?;
        // PQ-196: what each step claims is read from the lease row and from
        // the admission callback (asked only after an attempt ended waiting),
        // not from how long a commit took: under the gate's 4-job load one
        // commit took 345 ms and 625 ms.
        let expires = |c: &mut Client| -> Result<f64> {
            Ok(c.query_one("SELECT extract(epoch FROM expires)::float8 FROM realm_ownership WHERE realm=$1", &[&realm])?
                .get(0))
        };
        let before = expires(&mut c)?;
        // The same wait inside a 2 s admission: the retry renews, and admission
        // is measured from the retry, not from the attempt that timed out.
        let s = lease(Duration::from_millis(1200))?;
        let admitted = s.started + Duration::from_secs(2);
        let asked = std::cell::Cell::new(0u32);
        let start = renew_within(&mut c, &realm, "owner", g, || {
            asked.set(asked.get() + 1);
            Instant::now() < admitted
        })?;
        let (started, renewed) = (s.started, s.started.elapsed());
        s.join()?;
        assert!(asked.get() >= 1, "no attempt waited");
        assert!(start.duration_since(started) >= Duration::from_millis(700), "{:?}", start.duration_since(started));
        assert!(start < admitted, "{:?}", start.duration_since(started));
        assert!(renewed >= Duration::from_millis(1150), "{renewed:?}");
        // The retry wrote the lease: it ends later than the one written before
        // the wait by at least the attempt that timed out (database clock).
        let written = expires(&mut c)? - before;
        assert!(written >= 0.7, "{written}");
        // Admission (2 s from the successful attempt's start) ends before the
        // database lease (3 s from that attempt's statement). Admission's rest
        // is read first, so any delay before the query only shortens the
        // lease's rest.
        let admission_left = (start + Duration::from_secs(2)).saturating_duration_since(Instant::now());
        let lease_left: f64 = c
            .query_one(
                "SELECT extract(epoch FROM expires-clock_timestamp())::float8 FROM realm_ownership WHERE realm=$1",
                &[&realm],
            )?
            .get(0);
        assert!(lease_left > admission_left.as_secs_f64(), "{lease_left} {admission_left:?}");
        // A holder that outlasts admission (it holds until released below, so
        // no attempt can outrun it): every retry was asked while admission was
        // open, the first closed answer ended the retries, and the last lock
        // timeout is returned.
        let s = lease(Duration::from_secs(30))?;
        let admitted = s.started + Duration::from_secs(1);
        let answers = std::cell::RefCell::new(Vec::new());
        let e = renew_within(&mut c, &realm, "owner", g, || {
            let open = Instant::now() < admitted;
            answers.borrow_mut().push(open);
            open
        })
        .unwrap_err();
        let failed = s.started.elapsed();
        s.release();
        s.join()?;
        assert!(renewal_wait(e.as_ref()), "{e}");
        let answers = answers.into_inner();
        assert_eq!(answers.last(), Some(&false), "{answers:?}");
        assert!(answers[..answers.len() - 1].iter().all(|open| *open), "{answers:?}");
        assert!(failed >= Duration::from_secs(1), "{failed:?}");
        // A fenced renewal (stale generation) fails at once, even with
        // admission open: no attempt waits, so admission is never asked.
        renew(&mut c, &realm, "owner", g)?;
        let asked = std::cell::Cell::new(0u32);
        let e = renew_within(&mut c, &realm, "owner", g - 1, || {
            asked.set(asked.get() + 1);
            true
        })
        .unwrap_err();
        assert!(e.to_string().contains("realm fenced"), "{e}");
        assert_eq!(asked.get(), 0);
        release(&mut c, &realm, "owner", g)?;
        let e = renew_within(&mut c, &realm, "owner", g, || true).unwrap_err();
        assert!(e.to_string().contains("realm fenced"), "{e}");
        c.execute("DELETE FROM realm_ownership WHERE realm=$1", &[&realm])?;
        c.execute("DELETE FROM realm_fence WHERE realm=$1", &[&realm])?;
        Ok(())
    }
    /// D-145 (PQ-149): a durable transaction that holds the fence longer than
    /// admission (2 s) makes no renewal wait, while a takeover still waits for it
    /// and the old generation stays fenced once a takeover commits.
    #[test]
    #[ignore = "requires an isolated PostgreSQL URL; run by tests/gameplay.py and tests/multiplayer.py"]
    fn renewal_never_waits_behind_a_fenced_write() -> Result<()> {
        use std::sync::mpsc;
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = connect(&url)?;
        let realm = format!("renew-fence-test-{}", std::process::id());
        let g = acquire(&mut c, &realm, "owner")?;
        // A fenced transaction of the owner that also takes FOR KEY SHARE on
        // the lease row, as a foreign-key check does, and holds both until it
        // is told to commit: far past lock_timeout (800 ms), so anything that
        // waited behind it would end in a lock timeout (PQ-196).
        let (held_tx, held) = mpsc::channel();
        let (commit_tx, commit) = mpsc::channel::<()>();
        let holder = {
            let (url, realm) = (url.clone(), realm.clone());
            std::thread::spawn(move || -> Result<()> {
                let mut h = connect(&url)?;
                h.batch_execute("SET statement_timeout='60s'")?;
                let mut t = h.transaction()?;
                fence(&mut t, &realm, "owner", g)?;
                t.query_one("SELECT 1 FROM realm_ownership WHERE realm=$1 FOR KEY SHARE", &[&realm])?;
                held_tx.send(Instant::now()).ok();
                let _ = commit.recv_timeout(Duration::from_secs(30));
                t.commit()?;
                Ok(())
            })
        };
        let since = held.recv_timeout(Duration::from_secs(5))?;
        // Renewals every 400 ms for longer than admission, through the
        // production retry path. Admission is asked only after an attempt
        // ended waiting; it is never asked, so no renewal waited behind the
        // fenced write. How long each commit took is not the claim: under the
        // gate's 4-job load one took 345 ms and 625 ms (PQ-196).
        let mut admitted = since + Duration::from_secs(2);
        let asked = std::cell::Cell::new(0u32);
        while since.elapsed() < Duration::from_millis(2600) {
            std::thread::sleep(Duration::from_millis(400));
            let start = renew_within(&mut c, &realm, "owner", g, || {
                asked.set(asked.get() + 1);
                Instant::now() < admitted
            })?;
            admitted = start + Duration::from_secs(2);
        }
        assert_eq!(asked.get(), 0, "a renewal waited behind the fenced write");
        // Release does not wait either (a wait would end in a lock timeout,
        // an error), but a takeover of the released lease waits for the open
        // fenced transaction and times out behind it.
        release(&mut c, &realm, "owner", g)?;
        let mut other = connect(&url)?;
        let e = acquire(&mut other, &realm, "next").unwrap_err();
        assert_eq!(
            e.downcast_ref::<postgres::Error>().and_then(|e| e.code()),
            Some(&postgres::error::SqlState::LOCK_NOT_AVAILABLE),
            "{e}"
        );
        commit_tx.send(()).ok();
        holder.join().map_err(|_| bad("fenced holder panicked"))??;
        // After the fenced transaction commits the takeover succeeds, and the
        // old generation can neither renew nor fence.
        let next = acquire(&mut other, &realm, "next")?;
        assert!(next > g);
        assert!(renew(&mut c, &realm, "owner", g).unwrap_err().to_string().contains("realm fenced"));
        let mut t = c.transaction()?;
        let e = fence(&mut t, &realm, "owner", g).unwrap_err();
        assert!(e.to_string().contains("stale realm generation"), "{e}");
        drop(t);
        let mut t = c.transaction()?;
        fence(&mut t, &realm, "next", next)?;
        t.rollback()?;
        release(&mut c, &realm, "next", next)?;
        c.execute("DELETE FROM realm_ownership WHERE realm=$1", &[&realm])?;
        c.execute("DELETE FROM realm_fence WHERE realm=$1", &[&realm])?;
        Ok(())
    }
    /// What a scripted Postgres listener answers to one startup packet.
    #[derive(Clone, Copy)]
    enum Answer {
        /// FATAL with this SQLSTATE, then close (as Postgres refuses a login).
        Fatal(&'static str),
        /// AuthenticationOk and ReadyForQuery: a usable session.
        Accept,
        /// A usable session that the server then drops (a terminated
        /// backend): the client sees its connection close.
        AcceptThenHangUp,
    }
    /// A listener that plays Postgres's side of the startup handshake from a
    /// script, one answer per connection (the last repeats), and counts the
    /// connections it saw. Postgres's own refusal during crash recovery is the
    /// same message: FATAL 57P03 to the startup packet, then close.
    fn scripted_postgres(script: Vec<Answer>) -> (String, std::sync::Arc<std::sync::atomic::AtomicUsize>) {
        use std::io::{Read, Write};
        use std::sync::atomic::AtomicUsize;
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let seen = std::sync::Arc::new(AtomicUsize::new(0));
        let count = seen.clone();
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut s) = stream else { return };
                let n = count.fetch_add(1, Ordering::SeqCst);
                let answer = script[n.min(script.len() - 1)];
                let mut len = [0u8; 4];
                if s.read_exact(&mut len).is_err() {
                    continue;
                }
                let mut body = vec![0u8; u32::from_be_bytes(len) as usize - 4];
                if s.read_exact(&mut body).is_err() {
                    continue;
                }
                let reply = match answer {
                    Answer::Fatal(code) => {
                        let mut fields = Vec::new();
                        for (tag, value) in [
                            (b'S', "FATAL"),
                            (b'V', "FATAL"),
                            (b'C', code),
                            (b'M', "scripted refusal"),
                        ] {
                            fields.push(tag);
                            fields.extend_from_slice(value.as_bytes());
                            fields.push(0);
                        }
                        fields.push(0);
                        let mut m = vec![b'E'];
                        m.extend_from_slice(&(fields.len() as u32 + 4).to_be_bytes());
                        m.extend_from_slice(&fields);
                        m
                    }
                    Answer::Accept | Answer::AcceptThenHangUp => {
                        let mut m = vec![b'R', 0, 0, 0, 8, 0, 0, 0, 0];
                        m.extend_from_slice(&[b'Z', 0, 0, 0, 5, b'I']);
                        m
                    }
                };
                let _ = s.write_all(&reply);
                match answer {
                    // Hold the session until the client hangs up.
                    Answer::Accept => {
                        let _ = s.read_to_end(&mut Vec::new());
                    }
                    // Wait for the first query, then drop the session.
                    Answer::AcceptThenHangUp => {
                        let _ = s.read(&mut [0u8; 64]);
                    }
                    Answer::Fatal(_) => {}
                }
            }
        });
        (format!("host=127.0.0.1 port={port} user=n3e dbname=n3e"), seen)
    }
    fn refusal(r: Result<Client>) -> Box<dyn std::error::Error + Send + Sync> {
        match r {
            Ok(_) => panic!("connected through a refusal"),
            Err(e) => e,
        }
    }
    fn sqlstate(e: &(dyn std::error::Error + Send + Sync + 'static)) -> Option<String> {
        e.downcast_ref::<postgres::Error>()
            .and_then(|e| e.code())
            .map(|c| c.code().to_string())
    }
    /// D-140 (PQ-155): start-up rides out Postgres's recovery window. A
    /// realm restarted while Postgres answers 57P03 connects once it accepts.
    #[test]
    fn start_connect_retries_while_postgres_is_in_recovery() -> Result<()> {
        let (url, seen) = scripted_postgres(vec![
            Answer::Fatal("57P03"),
            Answer::Fatal("57P03"),
            Answer::Fatal("57P03"),
            Answer::Accept,
        ]);
        let tried = Instant::now();
        let c = connect_within(&url, START_WAIT)?;
        assert!(!c.is_closed());
        assert_eq!(seen.load(Ordering::SeqCst), 4);
        // Three pauses of CONNECT_RETRY, far inside the window.
        let took = tried.elapsed();
        assert!(took >= CONNECT_RETRY * 3 && took < Duration::from_secs(3), "{took:?}");
        // The pre-D-140 start-up (and every connection after start-up)
        // takes the first refusal as final.
        let (url, seen) = scripted_postgres(vec![Answer::Fatal("57P03"), Answer::Accept]);
        let e = refusal(connect(&url));
        assert_eq!(sqlstate(e.as_ref()).as_deref(), Some("57P03"));
        assert_eq!(seen.load(Ordering::SeqCst), 1);
        Ok(())
    }
    /// The retry is bounded and covers 57P03 alone.
    #[test]
    fn start_connect_gives_up_at_the_deadline_and_never_retries_other_refusals() {
        // Postgres that never leaves recovery: the window's last refusal is
        // returned once the next attempt would land past the deadline.
        let (url, seen) = scripted_postgres(vec![Answer::Fatal("57P03")]);
        let wait = Duration::from_millis(700);
        let tried = Instant::now();
        let e = refusal(connect_within(&url, wait));
        let took = tried.elapsed();
        assert_eq!(sqlstate(e.as_ref()).as_deref(), Some("57P03"));
        assert!(took >= wait - CONNECT_RETRY && took < wait + Duration::from_secs(1), "{took:?}");
        assert!(seen.load(Ordering::SeqCst) >= 4);
        // A refusal that is not 57P03 ends start-up at once, even mid-window:
        // here 28P01 (bad password) after two recovery refusals.
        let (url, seen) = scripted_postgres(vec![
            Answer::Fatal("57P03"),
            Answer::Fatal("57P03"),
            Answer::Fatal("28P01"),
            Answer::Accept,
        ]);
        let e = refusal(connect_within(&url, START_WAIT));
        assert_eq!(sqlstate(e.as_ref()).as_deref(), Some("28P01"));
        assert_eq!(seen.load(Ordering::SeqCst), 3);
        // Nothing listening: refused at once, no retry.
        let port = {
            let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            l.local_addr().unwrap().port()
        };
        let tried = Instant::now();
        let e = refusal(connect_within(
            &format!("host=127.0.0.1 port={port} user=n3e dbname=n3e"),
            START_WAIT,
        ));
        assert!(sqlstate(e.as_ref()).is_none(), "{e}");
        assert!(tried.elapsed() < Duration::from_secs(2));
    }
    /// A realm whose start-up passed and whose admission is open.
    fn admitted() -> std::sync::Arc<Health> {
        let h = std::sync::Arc::new(Health::new());
        h.redis.store(true, Ordering::Relaxed);
        h.listening.store(true, Ordering::Relaxed);
        h.renew(Instant::now() + Duration::from_secs(3600));
        assert!(h.ready());
        h
    }
    fn closes_admission(h: &Health) -> bool {
        let deadline = Instant::now() + Duration::from_secs(5);
        while h.ready() {
            if Instant::now() > deadline {
                return false;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        true
    }
    /// D-141 (PQ-156): the account/checkpoint worker reports its connection
    /// before start-up goes on. Before, it ended silently and the realm took
    /// the lease and admitted logins that all failed with "database queue
    /// unavailable".
    #[test]
    fn worker_start_returns_its_connect_error() {
        // Only the worker's connection is refused (53300: too many
        // connections, as when the start-up connection took the last slot).
        let (url, seen) = scripted_postgres(vec![Answer::Fatal("53300")]);
        let h = admitted();
        let tried = Instant::now();
        let e = match crate::accounts::Database::start(url, h.clone()) {
            Ok(_) => panic!("worker started without a connection"),
            Err(e) => e,
        };
        assert_eq!(sqlstate(e.as_ref()).as_deref(), Some("53300"), "{e}");
        assert_eq!(seen.load(Ordering::SeqCst), 1);
        assert!(tried.elapsed() < Duration::from_secs(2));
        assert!(!h.ready());
        // Recovery refusals are still ridden out (D-140), then it serves.
        let (url, seen) = scripted_postgres(vec![
            Answer::Fatal("57P03"),
            Answer::Fatal("57P03"),
            Answer::Accept,
        ]);
        let h = admitted();
        let db = crate::accounts::Database::start(url, h.clone()).expect("worker connects");
        assert_eq!(seen.load(Ordering::SeqCst), 3);
        let rt = tokio::runtime::Builder::new_current_thread().build().unwrap();
        assert_eq!(rt.block_on(db.call(|c| Ok(c.is_closed()))).unwrap(), false);
        assert!(h.ready());
    }
    /// A worker that stops serving after start-up closes admission: the
    /// renewal thread then ends the process for restart (main.rs).
    #[test]
    fn worker_that_stops_serving_closes_admission() {
        let rt = tokio::runtime::Builder::new_current_thread().build().unwrap();
        // Its thread ends: a job panicked.
        let (url, _) = scripted_postgres(vec![Answer::Accept]);
        let h = admitted();
        let db = crate::accounts::Database::start(url, h.clone()).expect("worker connects");
        let r: Result<()> = rt.block_on(db.call(|_| panic!("scripted job panic")));
        assert!(r.is_err());
        assert!(closes_admission(&h), "admission stayed open after the worker died");
        let r = rt.block_on(db.call(|_| Ok(())));
        assert_eq!(r.unwrap_err().to_string(), "database queue unavailable");
        // Its connection closes (the backend was terminated): a closed
        // client never reopens, so the worker stops instead of failing every
        // later call while the realm reports ready.
        let (url, _) = scripted_postgres(vec![Answer::AcceptThenHangUp]);
        let h = admitted();
        let db = crate::accounts::Database::start(url, h.clone()).expect("worker connects");
        assert!(rt
            .block_on(db.call(|c| Ok(c.simple_query("SELECT 1")?.len())))
            .is_err());
        assert!(closes_admission(&h), "admission stayed open on a closed worker connection");
        // A failed statement on a live connection is the caller's error only.
        let (url, _) = scripted_postgres(vec![Answer::Accept]);
        let h = admitted();
        let db = crate::accounts::Database::start(url, h.clone()).expect("worker connects");
        assert!(rt.block_on(db.call(|_| -> Result<()> { Err(bad("refused")) })).is_err());
        assert!(rt.block_on(db.call(|_| Ok(()))).is_ok());
        assert!(h.ready());
    }
    #[test]
    fn admission_expires_before_database_lease() {
        let h = Health::new();
        h.redis.store(true, Ordering::Relaxed);
        h.renew(Instant::now());
        // Lease and Redis alone are not readiness: the game port must be bound.
        assert!(!h.ready());
        h.listening.store(true, Ordering::Relaxed);
        assert!(h.ready());
        h.renew(Instant::now() - Duration::from_millis(2100));
        assert!(!h.ready());
        h.renew(Instant::now());
        assert!(h.ready());
        h.invalidate();
        assert!(!h.ready());
        // A concurrent lease renewal must never reopen failed persistence admission.
        h.renew(Instant::now());
        assert!(!h.ready());
    }
}

#[cfg(test)]
mod readiness_tests {
    use super::*;
    // PQ-368 (D-198): one failed probe leaves admission open, two in a row close
    // it, one success reopens it; no admission before Redis has answered once.
    #[test]
    fn redis_readiness_closes_after_consecutive_failures_only() {
        let mut r = RedisReadiness::default();
        assert!(!r.up());
        assert_eq!(r.probe(false), RedisChange::None);
        assert_eq!(r.probe(false), RedisChange::None);
        assert!(!r.up(), "never up before a successful probe");
        assert_eq!(r.probe(true), RedisChange::Up);
        assert_eq!(r.probe(true), RedisChange::None);
        assert_eq!(r.probe(false), RedisChange::Missed);
        assert!(r.up(), "one missed probe keeps admission");
        assert_eq!(r.probe(true), RedisChange::None);
        assert_eq!(r.probe(false), RedisChange::Missed);
        assert!(r.up(), "a success in between restarts the count");
        assert_eq!(r.probe(false), RedisChange::Down);
        assert!(!r.up());
        assert_eq!(r.probe(false), RedisChange::None);
        assert_eq!(r.probe(true), RedisChange::Up);
        assert!(r.up());
    }
    // PQ-368: a refused handshake logs which part of readiness failed; the
    // reason and `ready` come from the same checks.
    #[test]
    fn unready_names_the_failed_part_and_agrees_with_ready() {
        let h = Health::new();
        let says = |h: &Health| {
            assert_eq!(h.ready(), h.unready().is_none());
            h.unready()
        };
        assert_eq!(says(&h).as_deref(), Some("realm lease not yet held"));
        h.renew(Instant::now());
        assert_eq!(says(&h).as_deref(), Some("redis unreachable"));
        h.redis.store(true, Ordering::Relaxed);
        assert_eq!(says(&h).as_deref(), Some("listener not bound"));
        h.listening.store(true, Ordering::Relaxed);
        assert_eq!(says(&h), None);
        h.redis.store(false, Ordering::Relaxed);
        assert_eq!(says(&h).as_deref(), Some("redis unreachable"));
        h.redis.store(true, Ordering::Relaxed);
        h.renew(Instant::now() - Duration::from_millis(2500));
        let late = says(&h).unwrap();
        assert!(late.starts_with("admission expired ") && late.ends_with(" ms ago (no lease renewal)"), "{late}");
        h.renew(Instant::now());
        h.invalidate();
        assert_eq!(says(&h).as_deref(), Some("realm lease lost"));
        h.stopped.store(true, Ordering::Relaxed);
        assert_eq!(says(&h).as_deref(), Some("realm stopping"));
    }
    // PQ-415 (D-215): the pause before a renewal never outlasts admission. While
    // 800 ms (two pauses) or more is left it is the usual 400 ms; below
    // that the next attempt starts 400 ms before admission ends, and at once
    // when 400 ms or less is left. Before, the pause was always 400 ms, so a
    // renewal that took 1.6-2 s reopened admission and the next check ended it.
    #[test]
    fn renewal_pause_starts_the_next_attempt_inside_admission() {
        let ms = Duration::from_millis;
        for (left, pause) in [(2000, 400), (1500, 400), (800, 400), (700, 300), (450, 50), (400, 0), (198, 0), (1, 0), (0, 0)] {
            assert_eq!(renewal_pause(ms(left)), ms(pause), "{left} ms left");
        }
        for left in (1..=2000).map(ms) {
            let pause = renewal_pause(left);
            assert!(pause < left, "the attempt after a {left:?} pause starts once admission has ended");
            assert!(pause <= RENEWAL_PAUSE);
            assert!(pause.is_zero() || pause + RENEWAL_PAUSE <= left, "{left:?}");
            // Bounded: a zero pause only after an attempt of 1.6 s or more.
            assert!(!pause.is_zero() || ADMISSION - left >= ADMISSION - RENEWAL_PAUSE, "{left:?}");
        }
    }
    // PQ-415: the pause is taken from Health's own admission deadline, which
    // only a successful renewal moves, and the check after it still ends a
    // realm whose last successful attempt started 2 s or more ago.
    #[test]
    fn admission_left_follows_the_last_successful_start() {
        let h = Health::new();
        assert_eq!(h.admission_left(), Duration::ZERO, "no admission before the lease");
        h.renew(Instant::now());
        assert!(h.admission_left() > Duration::from_millis(1900));
        assert_eq!(renewal_pause(h.admission_left()), RENEWAL_PAUSE);
        // The PQ-414 observation: an attempt held 1.8 s lands with about 200 ms
        // left. The next attempt now starts at once, while admission holds.
        h.renew(Instant::now() - Duration::from_millis(1800));
        let left = h.admission_left();
        assert!(left > Duration::ZERO && left <= Duration::from_millis(200), "{left:?}");
        assert_eq!(renewal_pause(left), Duration::ZERO);
        assert!(h.owned(), "a landing that reopened admission still owns the realm");
        // An attempt of 2 s or more reopens nothing: the check ends the realm.
        h.renew(Instant::now() - ADMISSION);
        assert_eq!(h.admission_left(), Duration::ZERO);
        assert!(!h.owned());
        h.renew(Instant::now());
        h.invalidate();
        assert_eq!(h.admission_left(), Duration::ZERO, "a lost lease leaves no admission");
        assert!(!h.owned());
    }
}
#[cfg(test)]
mod migration_tests {
    use super::*;
    #[test]
    #[ignore = "isolated postgres supplied by tests/multiplayer.py"]
    fn fresh_upgrade_and_failed_second_migration_rollback() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut admin = connect(&url)?;
        // Scaffolding only: CREATE and DROP DATABASE are not under test. DROP ...
        // WITH (FORCE) waits for the backends this test just closed to exit, and
        // under the 1 s production statement timeout it failed twice while other
        // live suites loaded the machine (PQ-114). Every migrate() call below
        // keeps connect()'s production timeouts.
        admin.batch_execute("SET statement_timeout = '30s'; SET lock_timeout = '30s'")?;
        let name = format!("n3e_migrations_{}", std::process::id());
        admin.batch_execute(&format!("CREATE DATABASE {name}"))?;
        let target = format!("{url} dbname={name}");
        let result = (|| -> Result<()> {
            migrate(&target, &MIGRATIONS[..1])?;
            let broken = "CREATE TABLE should_rollback(id integer); SELECT 1/0;";
            assert!(migrate(&target, &[(1, MIGRATIONS[0].1), (2, broken)]).is_err());
            let mut c = connect(&target)?;
            assert!(c
                .query_one("SELECT to_regclass('public.should_rollback') IS NULL", &[])?
                .get::<_, bool>(0));
            assert_eq!(
                c.query_one("SELECT count(*) FROM schema_migrations", &[])?
                    .get::<_, i64>(0),
                1
            );
            migrate(&target, MIGRATIONS)?;
            migrate(&target, MIGRATIONS)?;
            verify(&mut c)?;
            c.batch_execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")?;
            migrate(&target, MIGRATIONS)?;
            verify(&mut c)?;
            Ok(())
        })();
        admin.batch_execute(&format!("DROP DATABASE {name} WITH (FORCE)"))?;
        result
    }
}
