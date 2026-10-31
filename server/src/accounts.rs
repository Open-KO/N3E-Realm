//! Bounded dedicated durable worker. No database or password work runs on a tick.
use crate::{
    content::{bad, Result},
    persistence,
    rules::Rules,
    wire,
};
use postgres::Client;
use std::sync::{mpsc, Arc};
use tokio::sync::oneshot;

type Job = Box<dyn FnOnce(&mut Client) + Send>;
/// Fails admission closed when the worker thread ends, including by panic.
struct Invalidate(Arc<persistence::Health>);
impl Drop for Invalidate {
    fn drop(&mut self) {
        if std::thread::panicking() {
            eprintln!("account/checkpoint worker panicked; admission closed (D-141)");
        }
        self.0.invalidate();
    }
}
#[derive(Clone)]
pub struct Database {
    tx: mpsc::SyncSender<Job>,
}
#[cfg(test)]
impl Database {
    /// Test only: a database whose worker is gone; every call fails.
    pub(crate) fn test_unavailable() -> Self {
        Database { tx: mpsc::sync_channel(1).0 }
    }
}
#[derive(Clone)]
pub struct Owner {
    pub realm: String,
    pub owner: String,
    pub generation: i64,
}
#[derive(Clone, Debug)]
pub struct Selected {
    pub id: i64,
    pub generation: i64,
    pub life_revision: i64,
    pub dead: bool,
    pub ready_ticks: u64,
    pub entity: wire::Entity,
}
impl Database {
    /// Opens the realm's one account/checkpoint connection and returns once it
    /// is open (D-141, PQ-156). Realm start-up calls this before it takes the
    /// lease, so a connection that cannot be opened ends start-up with its own
    /// error instead of leaving a ready realm whose every login, character and
    /// checkpoint call fails. Like the start-up connection it rides out
    /// Postgres recovery (57P03, D-140) and nothing else. `health` is already
    /// invalidated when that error is returned (PQ-209).
    ///
    /// `health` is invalidated whenever the worker stops serving after that:
    /// its thread ends (a job panicked, or every handle was dropped) or its
    /// connection closed. A closed `postgres::Client` never reopens, so from
    /// then on the realm could serve nothing; invalidated admission stops the
    /// realm's renewal and the process exits for restart, as on any other
    /// persistence failure.
    pub fn start(url: String, health: Arc<persistence::Health>) -> Result<Self> {
        let (tx, rx) = mpsc::sync_channel::<Job>(128);
        let (opened_tx, opened) = mpsc::sync_channel::<Result<()>>(1);
        std::thread::spawn(move || {
            let stopped = Invalidate(health);
            let mut c = match persistence::connect_within(&url, persistence::START_WAIT) {
                Ok(c) => c,
                Err(e) => {
                    // Close admission before `start` can return the error
                    // (PQ-209): dropped only at the thread's end, the guard
                    // could still run after the caller had the error.
                    drop(stopped);
                    let _ = opened_tx.send(Err(e));
                    return;
                }
            };
            let _ = opened_tx.send(Ok(()));
            while let Ok(job) = rx.recv() {
                job(&mut c);
                if c.is_closed() {
                    eprintln!(
                        "account/checkpoint worker connection closed; admission closed (D-141)"
                    );
                    return;
                }
            }
        });
        opened
            .recv()
            .map_err(|_| bad("database worker unavailable"))??;
        Ok(Self { tx })
    }
    pub async fn call<T: Send + 'static>(
        &self,
        f: impl FnOnce(&mut Client) -> Result<T> + Send + 'static,
    ) -> Result<T> {
        let (tx, rx) = oneshot::channel();
        self.tx
            .try_send(Box::new(move |c| {
                let _ = tx.send(f(c));
            }))
            .map_err(|_| bad("database queue unavailable"))?;
        // Do not time out and abandon a committed selection: postgres operations
        // have bounded statement/socket timeouts and the caller owns the result.
        rx.await.map_err(|_| bad("database worker unavailable"))?
    }
    /// The account's characters in creation order, each with its level as the
    /// HUD shows it (rewards::inventory): the progression curve's level, else
    /// 1 + xp / level_xp; 1 before the first inventory read (spec 11).
    pub async fn list(&self, account: i64, realm: String, rules: &Rules) -> Result<wire::Characters> {
        let (progression, level_xp) = (rules.progression.clone(), rules.level_xp.max(1) as u64);
        self.call(move |c| {
            let rows = c.query(
                "SELECT c.id,c.name,p.xp,q.curve_xp FROM characters c \
                 LEFT JOIN character_progress p ON p.character_id=c.id \
                 LEFT JOIN character_reward_progress q ON q.character_id=c.id \
                 WHERE c.account_id=$1 AND c.realm=$2 ORDER BY c.id LIMIT 8",
                &[&account, &realm],
            )?;
            let characters = rows
                .iter()
                .map(|r| {
                    let level = match &progression {
                        Some(p) => r.get::<_, Option<i64>>(3).map(|xp| p.level(xp as u64)).unwrap_or(1),
                        None => r.get::<_, Option<i64>>(2).map(|xp| 1 + xp as u64 / level_xp).unwrap_or(1) as u32,
                    };
                    wire::Character { id: r.get::<_, i64>(0) as u64, name: r.get(1), level }
                })
                .collect();
            Ok(wire::Characters { characters })
        })
        .await
    }
    pub async fn create(
        &self,
        account: i64,
        name: String,
        owner: Arc<Owner>,
        spawn: [f32; 3],
        limit: u32,
    ) -> Result<()> {
        if !valid_name(&name, 24) {
            return Err(bad("character name must be 1..24 ASCII letters/digits/_/-"));
        }
        self.call(move |c| {
            let mut t = c.transaction()?;
            persistence::fence(&mut t, &owner.realm, &owner.owner, owner.generation)?;
            let count: i64 = t
                .query_one(
                    "SELECT count(*) FROM characters WHERE account_id=$1 AND realm=$2",
                    &[&account, &owner.realm],
                )?
                .get(0);
            if count >= limit as i64 {
                return Err(bad("character limit"));
            }
            let id: i64 = t.query_one(
                "INSERT INTO characters(account_id,realm,name,x,y,z) VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
                &[
                    &account,
                    &owner.realm,
                    &name,
                    &spawn[0],
                    &spawn[1],
                    &spawn[2],
                ],
            )?
            .get(0);
            crate::settlements::initialize(&mut t, &owner.realm, id)?;
            t.commit()?;
            Ok(())
        })
        .await
    }
    pub async fn select(&self, account: i64, id: i64, owner: Arc<Owner>) -> Result<Selected> {
        self.call(move |c| {
            let mut t=c.transaction()?;
            persistence::fence(&mut t,&owner.realm,&owner.owner,owner.generation)?;
            let row=t.query_opt("UPDATE characters SET session_generation=session_generation+1,realm_generation=$4,online=true,movement_seq=0 WHERE id=$1 AND account_id=$2 AND realm=$3 AND (NOT online OR realm_generation<>$4) RETURNING name,x,y,z,session_generation,nextval('entity_instances'),life_revision,dead,COALESCE(GREATEST(0,ceil(extract(epoch FROM (respawn_ready_at-clock_timestamp()))*1000/$5::bigint)),0)::bigint", &[&id,&account,&owner.realm,&owner.generation,&(crate::clock::tick_ms() as i64)])?.ok_or_else(||bad("character not owned or already online"))?;
            let selected=Selected{id,generation:row.get(4),life_revision:row.get(6),dead:row.get(7),ready_ticks:row.get::<_,i64>(8) as u64,entity:wire::Entity{id:row.get::<_,i64>(5) as u64,name:row.get(0),x:row.get(1),y:row.get(2),z:row.get(3),ack:0,..Default::default()}};
            t.commit()?; Ok(selected)
        }).await
    }
    /// Commit before simulation publication. Revision CAS fences old checkpoints and
    /// duplicate transitions; session and realm fences also cover late worker results.
    pub async fn transition(
        &self,
        owner: Arc<Owner>,
        mut target: Selected,
        dead: bool,
        delay: u32,
    ) -> Result<Selected> {
        self.call(move |c| {
            let mut t = c.transaction()?;
            persistence::fence(&mut t, &owner.realm, &owner.owner, owner.generation)?;
            let row = t.query_opt("UPDATE characters SET dead=$1,respawn_ready_at=CASE WHEN $1 THEN clock_timestamp()+$2::bigint*interval '1 millisecond' ELSE NULL END,life_revision=life_revision+1,x=$3,y=$4,z=$5,movement_seq=$6,checkpoint_at=clock_timestamp() WHERE id=$7 AND realm=$8 AND session_generation=$9 AND realm_generation=$10 AND online AND life_revision=$11 AND dead<>$1 AND ($1 OR respawn_ready_at<=clock_timestamp()) RETURNING life_revision", &[&dead,&(delay as i64*crate::clock::tick_ms() as i64),&target.entity.x,&target.entity.y,&target.entity.z,&(target.entity.ack as i64),&target.id,&owner.realm,&target.generation,&owner.generation,&target.life_revision])?.ok_or_else(||bad("stale or ineligible life transition"))?;
            target.life_revision = row.get(0);
            target.dead = dead;
            target.ready_ticks = delay as u64;
            crate::life::fault(if dead { "death_before_commit" } else { "respawn_before_commit" });
            t.commit()?;
            crate::life::fault(if dead { "death_after_commit" } else { "respawn_after_commit" });
            Ok(target)
        }).await
    }
    pub async fn save(&self, owner: Arc<Owner>, positions: Vec<(Selected, bool)>) -> Result<()> {
        self.call(move |c| {
            let mut t=c.transaction()?;
            persistence::fence(&mut t,&owner.realm,&owner.owner,owner.generation)?;
            for (s,online) in positions {
                let n=t.execute("UPDATE characters SET x=$1,y=$2,z=$3,online=online AND $4,movement_seq=$9,checkpoint_at=clock_timestamp() WHERE id=$5 AND realm=$6 AND session_generation=$7 AND realm_generation=$8 AND movement_seq<=$9 AND life_revision=$10", &[&s.entity.x,&s.entity.y,&s.entity.z,&online,&s.id,&owner.realm,&s.generation,&owner.generation,&(s.entity.ack as i64),&s.life_revision])?;
                if n!=1 { let row=t.query_opt("SELECT session_generation,realm_generation FROM characters WHERE id=$1", &[&s.id])?.ok_or_else(||bad("character missing"))?; if row.get::<_,i64>(0)!=s.generation || row.get::<_,i64>(1)!=owner.generation { return Err(bad("stale character session")); } }
            }
            t.commit()?; Ok(())
        }).await
    }
}
pub fn valid_name(s: &str, max: usize) -> bool {
    !s.is_empty()
        && s.len() <= max
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}
pub fn hash(password: &str, salt: &[u8]) -> Result<[u8; 32]> { hash_bytes(password.as_bytes(),salt) }
pub(crate) fn hash_bytes(password: &[u8], salt: &[u8]) -> Result<[u8; 32]> {
    let mut result = [0; 32];
    openssl::pkcs5::scrypt(
        password,
        salt,
        131072,
        8,
        1,
        160 * 1024 * 1024,
        &mut result,
    )?;
    Ok(result)
}
pub fn provision(url: &str, name: &str, password: &str) -> Result<()> {
    if !valid_name(name, 32) || !(12..=128).contains(&password.len()) {
        return Err(bad(
            "account name 1..32 ASCII, password 12..128 bytes required",
        ));
    }
    let mut salt = [0; 16];
    openssl::rand::rand_bytes(&mut salt)?;
    let hashed = hash(password, &salt)?;
    let mut c = persistence::connect(url)?;
    persistence::verify(&mut c)?;
    c.execute(
        "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3)",
        &[&name, &&salt[..], &&hashed[..]],
    )?;
    Ok(())
}
pub async fn login(db: &Database, name: String, password: String) -> Result<i64> {
    if !valid_name(&name, 32) || password.len() > 128 {
        return Err(bad("invalid credentials"));
    }
    let row = db
        .call(move |c| {
            Ok(c.query_opt(
                "SELECT id,salt,password_hash FROM accounts WHERE name=$1",
                &[&name],
            )?)
        })
        .await?;
    tokio::task::spawn_blocking(move || {
        let (id, salt, expected) = row
            .map(|r| {
                (
                    r.get::<_, i64>(0),
                    r.get::<_, Vec<u8>>(1),
                    r.get::<_, Vec<u8>>(2),
                )
            })
            .unwrap_or((0, vec![0; 16], vec![0; 32]));
        let actual = hash(&password, &salt)?;
        if !openssl::memcmp::eq(&actual, &expected) || id == 0 {
            return Err(bad("invalid credentials"));
        }
        Ok(id)
    })
    .await?
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn password_roundtrip() {
        let a = hash("a long test password", &[1; 16]).unwrap();
        assert_eq!(a, hash("a long test password", &[1; 16]).unwrap());
        assert_ne!(a, hash("another test password", &[1; 16]).unwrap());
        assert_ne!(a, hash("a long test password", &[2; 16]).unwrap());
    }
}

#[cfg(test)]
mod database_tests {
    use super::*;
    #[test]
    #[ignore = "isolated postgres supplied by tests/multiplayer.py"]
    fn character_and_realm_fences() -> Result<()> {
        let runtime = tokio::runtime::Runtime::new()?;
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = persistence::connect(&url)?;
        let realm = format!("p2-fence-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "old")?;
        let owner = Arc::new(Owner {
            realm: realm.clone(),
            owner: "old".into(),
            generation,
        });
        let name = format!("p2-test-{}", std::process::id());
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&name, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let db = Database::start(url, Default::default())?;
        let rules = Rules::load(std::path::Path::new("../build/packages/legacy-demo/gameplay.bin"), "demo")?;
        runtime.block_on(db.create(account, "Fenced".into(), owner.clone(), [0., 0., 0.], 8))?;
        let id = runtime
            .block_on(db.list(account, realm.clone(), &rules))?
            .characters[0]
            .id as i64;
        assert!(runtime
            .block_on(db.select(account + 1, id, owner.clone()))
            .is_err());
        let mut first = runtime.block_on(db.select(account, id, owner.clone()))?;
        assert!(runtime
            .block_on(db.select(account, id, owner.clone()))
            .is_err());
        first.entity.x = 1.;
        first.entity.ack = 2;
        runtime.block_on(db.save(owner.clone(), vec![(first.clone(), false)]))?;
        let mut second = runtime.block_on(db.select(account, id, owner.clone()))?;
        assert!(second.generation > first.generation);
        second.entity.x = 2.;
        second.entity.ack = 1;
        runtime.block_on(db.save(owner.clone(), vec![(second.clone(), true)]))?;
        assert!(runtime
            .block_on(db.save(owner.clone(), vec![(first, false)]))
            .is_err());
        let x: f32 = c
            .query_one("SELECT x FROM characters WHERE id=$1", &[&id])?
            .get(0);
        assert_eq!(x, 2.);
        // An older checkpoint must not move a committed corpse or replacement,
        // even when no new movement sequence was consumed.
        let stale = second.clone();
        second.entity.x = 7.;
        second = runtime.block_on(db.transition(owner.clone(), second, true, 1200))?;
        assert!(runtime
            .block_on(db.transition(owner.clone(), stale.clone(), true, 0))
            .is_err());
        assert!(runtime
            .block_on(db.transition(owner.clone(), second.clone(), false, 0))
            .is_err());
        runtime.block_on(db.save(owner.clone(), vec![(stale, true)]))?;
        assert_eq!(
            c.query_one("SELECT x FROM characters WHERE id=$1", &[&id])?
                .get::<_, f32>(0),
            7.
        );
        runtime.block_on(db.save(owner.clone(), vec![(second.clone(), false)]))?;
        let old_dead = second.clone();
        second = runtime.block_on(db.select(account, id, owner.clone()))?;
        assert!(second.dead && second.ready_ticks > 0 && second.ready_ticks <= 1200);
        assert_eq!(second.entity.x, 7.);
        assert!(runtime
            .block_on(db.transition(owner.clone(), old_dead, false, 0))
            .is_err());
        c.execute("UPDATE characters SET respawn_ready_at=clock_timestamp()-interval '1 second' WHERE id=$1", &[&id])?;
        let stale = second.clone();
        second.entity.x = 0.;
        second = runtime.block_on(db.transition(owner.clone(), second, false, 0))?;
        runtime.block_on(db.save(owner.clone(), vec![(stale.clone(), true)]))?;
        assert!(runtime
            .block_on(db.transition(owner.clone(), stale, false, 0))
            .is_err());
        assert_eq!(
            c.query_one("SELECT x FROM characters WHERE id=$1", &[&id])?
                .get::<_, f32>(0),
            0.
        );
        std::thread::sleep(std::time::Duration::from_millis(3100));
        let new_generation = persistence::acquire(&mut c, &realm, "new")?;
        assert!(new_generation > generation);
        assert!(runtime
            .block_on(db.save(owner, vec![(second, false)]))
            .is_err());
        c.execute("DELETE FROM characters WHERE realm=$1", &[&realm])?;
        c.execute("DELETE FROM accounts WHERE id=$1", &[&account])?;
        c.execute("DELETE FROM realm_ownership WHERE realm=$1", &[&realm])?;
        Ok(())
    }
}
