//! Optional account-storage credentials. Secrets never enter operation payloads or logs.
//! Password work runs outside transactions and simulation, behind the shared hash limit.
use crate::{
    accounts::{self, Database, Owner, Selected},
    content::{bad, Reader, Result},
    inventory, persistence, wire,
};
use prost::Message;
use std::{
    collections::BTreeSet,
    path::Path,
    sync::Arc,
    time::{Duration, Instant},
};
#[derive(Clone, Debug)]
pub struct Policy {
    minimum: usize,
    maximum: usize,
    fold_ascii: bool,
    alphabet: String,
    forbidden: Vec<String>,
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3K1" {
            return Err(bad("storage credential magic"));
        }
        let minimum = r.u()? as usize;
        let maximum = r.u()? as usize;
        let comparison = r.u()?;
        let alphabet = r.string()?;
        let n = r.u()?;
        if minimum == 0
            || minimum > maximum
            || maximum > 128
            || comparison > 1
            || alphabet.is_empty()
            || alphabet.len() > 94
            || !alphabet.bytes().all(|c| (33..=126).contains(&c))
            || alphabet.as_bytes().windows(2).any(|w| w[0] >= w[1])
            || n > 400
        {
            return Err(bad("storage credential bounds"));
        }
        let mut forbidden = Vec::new();
        let mut seen = BTreeSet::new();
        for _ in 0..n {
            let w = r.string()?;
            if w.is_empty()
                || w.len() > 64
                || !w.bytes().all(|c| (32..=126).contains(&c))
                || w != w.to_ascii_uppercase()
                || !seen.insert(w.clone())
            {
                return Err(bad("storage credential word"));
            }
            forbidden.push(w);
        }
        r.end()?;
        Ok(Self {
            minimum,
            maximum,
            fold_ascii: comparison == 1,
            alphabet,
            forbidden,
        })
    }
    fn normalize(&self, value: &str) -> String {
        if self.fold_ascii {
            value.to_ascii_lowercase()
        } else {
            value.to_owned()
        }
    }
    pub fn valid(&self, value: &str) -> bool {
        (self.minimum..=self.maximum).contains(&value.len())
            && value.bytes().all(|c| self.alphabet.as_bytes().contains(&c))
            && !self
                .forbidden
                .iter()
                .any(|w| value.to_ascii_uppercase().contains(w))
    }
}
pub fn check_start(
    c: &mut postgres::Client,
    realm: &str,
    p: Option<&inventory::Policy>,
) -> Result<()> {
    for row in c.query(
        "SELECT DISTINCT definition FROM storage_credentials WHERE realm=$1",
        &[&realm],
    )? {
        if p.is_none_or(|p| {
            p.storage.as_ref().is_none_or(|s| s.credential.is_none())
                || row.get::<_, Vec<u8>>(0) != p.hash
        }) {
            return Err(bad(
                "incompatible storage credential; explicit migration required",
            ));
        }
    }
    Ok(())
}
fn account(t: &mut postgres::Transaction<'_>, o: &Owner, s: &Selected, lock: bool) -> Result<i64> {
    let query = if lock {
        "SELECT account_id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE"
    } else {
        "SELECT account_id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online"
    };
    Ok(
        t.query_opt(query, &[&s.id, &o.realm, &s.generation, &o.generation])?
            .ok_or_else(|| bad("stale storage credential session"))?
            .get(0),
    )
}
fn granted(
    t: &mut postgres::Transaction<'_>,
    o: &Owner,
    s: &Selected,
    revision: i64,
    account: i64,
) -> Result<bool> {
    Ok(t.query_opt("SELECT 1 FROM storage_authorizations WHERE character_id=$1 AND session_generation=$2 AND realm_generation=$3 AND credential_revision=$4 AND account_id=$5 AND realm=$6",&[&s.id,&s.generation,&o.generation,&revision,&account,&o.realm])?.is_some())
}
/// Lock credential before storage/character and hold through the transfer commit.
pub fn authorize(
    t: &mut postgres::Transaction<'_>,
    o: &Owner,
    s: &Selected,
    p: &inventory::Policy,
    account: i64,
) -> Result<Option<&'static str>> {
    if p.storage.as_ref().is_none_or(|v| v.credential.is_none()) {
        return Ok(None);
    }
    let Some(row)=t.query_opt("SELECT definition,revision FROM storage_credentials WHERE account_id=$1 AND realm=$2 FOR SHARE",&[&account,&o.realm])? else{return Ok(Some("unprovisioned"));};
    if row.get::<_, Vec<u8>>(0) != p.hash {
        return Err(bad("storage credential definition"));
    }
    Ok(if granted(t, o, s, row.get(1), account)? {
        None
    } else {
        Some("locked")
    })
}
struct Snapshot {
    account: i64,
    revision: i64,
    salt: Vec<u8>,
    verifier: Vec<u8>,
    history: Option<(Vec<u8>, Vec<u8>)>,
}
struct Proof {
    valid: bool,
    salt: [u8; 16],
    verifier: [u8; 32],
    replacement: Option<([u8; 16], [u8; 32])>,
}
fn salt() -> Result<[u8; 16]> {
    let mut v = [0; 16];
    openssl::rand::rand_bytes(&mut v)?;
    Ok(v)
}
fn payload(q: &wire::StorageAuthRequest, s: &Selected, o: &Owner) -> Vec<u8> {
    let mut v = b"n3e storage credential request v1\0".to_vec();
    v.extend_from_slice(&s.id.to_le_bytes());
    v.extend_from_slice(&(o.realm.len() as u32).to_le_bytes());
    v.extend_from_slice(o.realm.as_bytes());
    v.extend_from_slice(&q.encode_to_vec());
    v
}
fn response(
    q: &wire::StorageAuthRequest,
    status: &str,
    revision: i64,
    authorized: i64,
) -> wire::StorageAuthResult {
    wire::StorageAuthResult {
        request: q.request.clone(),
        status: status.into(),
        revision: revision as u64,
        authorized_revision: authorized as u64,
    }
}
/// How long a storage credential admission stays valid until its commit (D-132 lists it
/// among the wall-time admission windows). It spans both database round trips and the
/// password hash between them.
pub const ADMISSION_WINDOW: Duration = Duration::from_secs(2);
pub async fn execute(
    db: &Database,
    o: Arc<Owner>,
    s: Selected,
    p: inventory::Policy,
    q: wire::StorageAuthRequest,
    issued: Instant,
) -> Result<wire::StorageAuthResult> {
    execute_at(db, o, s, p, q, issued, Instant::now).await
}
/// `execute` with the clock that ages the admission, read at the eligibility check and
/// again just before COMMIT. Production passes `Instant::now`; tests pass a fixed clock
/// so the window, not database or hash speed, decides fresh and expired (PQ-291).
pub(crate) async fn execute_at(
    db: &Database,
    o: Arc<Owner>,
    s: Selected,
    p: inventory::Policy,
    q: wire::StorageAuthRequest,
    issued: Instant,
    clock: impl Fn() -> Instant + Send + 'static,
) -> Result<wire::StorageAuthResult> {
    let storage = p
        .storage
        .as_ref()
        .ok_or_else(|| bad("storage unavailable"))?;
    let policy = storage
        .credential
        .as_ref()
        .ok_or_else(|| bad("storage credential unavailable"))?;
    if q.operation > 2
        || q.service.len() > 129
        || q.password.len() > 128
        || q.replacement.len() > 128
        || (q.operation == 0
            && (!q.request.is_empty() || !q.password.is_empty() || !q.replacement.is_empty()))
        || (q.operation > 0
            && (!accounts::valid_name(&q.request, 64)
                || !(policy.minimum..=policy.maximum).contains(&q.password.len())))
        || (q.operation == 1 && !q.replacement.is_empty())
        || (q.operation == 2 && !policy.valid(&q.replacement))
    {
        return Err(bad("invalid storage credential request"));
    }
    let comparison = policy.clone();
    let (oo, ss, pp, qq) = (o.clone(), s.clone(), p.clone(), q.clone());
    let snapshot=db.call(move|c|{
  let mut t=c.transaction()?;persistence::fence(&mut t,&oo.realm,&oo.owner,oo.generation)?;let a=account(&mut t,&oo,&ss,false)?;
  let Some(row)=t.query_opt("SELECT definition,revision,salt,verifier FROM storage_credentials WHERE account_id=$1 AND realm=$2",&[&a,&oo.realm])? else{return Ok(None);};
  if row.get::<_,Vec<u8>>(0)!=pp.hash{return Err(bad("storage credential definition"));}
  let history=t.query_opt("SELECT salt,verifier FROM storage_credential_operations WHERE account_id=$1 AND realm=$2 AND request=$3",&[&a,&oo.realm,&qq.request])?.map(|r|(r.get(0),r.get(1)));
  Ok(Some(Snapshot{account:a,revision:row.get(1),salt:row.get(2),verifier:row.get(3),history}))
 }).await?;
    let Some(snapshot) = snapshot else {
        return Ok(response(&q, "unprovisioned", 0, 0));
    };
    let data = payload(&q, &s, &o);
    let (qq, ssalt, expected, history) = (
        q.clone(),
        snapshot.salt.clone(),
        snapshot.verifier.clone(),
        snapshot.history.clone(),
    );
    let proof = if q.operation == 0 {
        None
    } else {
        Some(
            tokio::task::spawn_blocking(move || -> Result<Proof> {
                if let Some((salt, expected)) = history {
                    let actual = accounts::hash_bytes(&data, &salt)?;
                    return Ok(Proof {
                        valid: openssl::memcmp::eq(&actual, &expected),
                        salt: salt.try_into().map_err(|_| bad("credential salt"))?,
                        verifier: actual,
                        replacement: None,
                    });
                }
                let valid = openssl::memcmp::eq(
                    &accounts::hash(&comparison.normalize(&qq.password), &ssalt)?,
                    &expected,
                );
                let rsalt = salt()?;
                let verifier = accounts::hash_bytes(&data, &rsalt)?;
                let replacement = if valid && qq.operation == 2 {
                    let s = salt()?;
                    Some((
                        s,
                        accounts::hash(&comparison.normalize(&qq.replacement), &s)?,
                    ))
                } else {
                    None
                };
                Ok(Proof {
                    valid,
                    salt: rsalt,
                    verifier,
                    replacement,
                })
            })
            .await??,
        )
    };
    db.call(move|c|{
  let mut t=c.transaction()?;persistence::fence(&mut t,&o.realm,&o.owner,o.generation)?;
  let row=t.query_one("SELECT definition,revision FROM storage_credentials WHERE account_id=$1 AND realm=$2 FOR UPDATE",&[&snapshot.account,&o.realm])?;
  if row.get::<_,Vec<u8>>(0)!=p.hash||account(&mut t,&o,&s,true)?!=snapshot.account{return Err(bad("storage credential fence"));}
  let current:i64=row.get(1);let authorized=if granted(&mut t,&o,&s,current,snapshot.account)?{current}else{0};
  if q.operation==0 {return Ok(response(&q,if authorized>0{"unlocked"}else{"locked"},current,authorized));}
  let proof=proof.unwrap();let old=t.query_opt("SELECT salt,verifier,status,revision FROM storage_credential_operations WHERE account_id=$1 AND realm=$2 AND request=$3",&[&snapshot.account,&o.realm,&q.request])?;
  if let Some(row)=&old {
   // A concurrent first request cannot be compared using an unrelated random salt.
   if snapshot.history.is_none()||row.get::<_,Vec<u8>>(0)!=proof.salt||!proof.valid||row.get::<_,Vec<u8>>(1)!=proof.verifier{return Ok(response(&q,"request_conflict",current,authorized));}
  }
  let life=t.query_one("SELECT dead,life_revision FROM characters WHERE id=$1",&[&s.id])?;
  let eligible=clock().saturating_duration_since(issued)<=ADMISSION_WINDOW&&!life.get::<_,bool>(0)&&life.get::<_,i64>(1)==s.life_revision&&p.storage.as_ref().unwrap().service(&s,&q.service).is_some();
  if !eligible{return Ok(response(&q,"unavailable",current,authorized));}
  let (status,revision)=if let Some(row)=old {(row.get::<_,String>(2),row.get::<_,i64>(3))} else {
   let (status,revision)=if current!=snapshot.revision {("credential_changed",current)}else if !proof.valid {("invalid_credentials",current)}else if q.operation==2 {
    let revision=current.checked_add(1).ok_or_else(||bad("credential revision overflow"))?;let (salt,verifier)=proof.replacement.ok_or_else(||bad("missing replacement proof"))?;
    t.execute("UPDATE storage_credentials SET revision=$3,salt=$4,verifier=$5 WHERE account_id=$1 AND realm=$2",&[&snapshot.account,&o.realm,&revision,&&salt[..],&&verifier[..]])?;("changed",revision)
   }else{("unlocked",current)};
   t.execute("INSERT INTO storage_credential_operations(account_id,realm,request,salt,verifier,status,revision) VALUES($1,$2,$3,$4,$5,$6,$7)",&[&snapshot.account,&o.realm,&q.request,&&proof.salt[..],&&proof.verifier[..],&status,&revision])?;(status.into(),revision)
  };
  let now:i64=t.query_one("SELECT revision FROM storage_credentials WHERE account_id=$1 AND realm=$2",&[&snapshot.account,&o.realm])?.get(0);
  let mut authorized=if granted(&mut t,&o,&s,now,snapshot.account)?{now}else{0};
  if matches!(status.as_str(),"unlocked"|"changed")&&revision==now {
   t.execute("INSERT INTO storage_authorizations(character_id,session_generation,realm_generation,credential_revision,account_id,realm) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(character_id) DO UPDATE SET session_generation=$2,realm_generation=$3,credential_revision=$4,account_id=$5,realm=$6",&[&s.id,&s.generation,&o.generation,&now,&snapshot.account,&o.realm])?;authorized=now;
  }
  persistence::fence(&mut t,&o.realm,&o.owner,o.generation)?;
  if clock().saturating_duration_since(issued)>ADMISSION_WINDOW{return Err(bad("expired credential commit"));}
  fault("before_commit");t.commit()?;fault("after_commit");Ok(response(&q,&status,revision,authorized))
 }).await
}
fn fault(point: &str) {
    if std::env::var("N3E_STORAGE_AUTH_FAULT").as_deref() == Ok(point) {
        eprintln!("STORAGE_AUTH_FAULT {point}");
        std::process::exit(96);
    }
}
pub fn provision(
    url: &str,
    name: &str,
    realm: &str,
    p: &inventory::Policy,
    password: &str,
) -> Result<()> {
    if !accounts::valid_name(name, 32)
        || !p
            .storage
            .as_ref()
            .and_then(|v| v.credential.as_ref())
            .is_some_and(|v| v.valid(password))
    {
        return Err(bad("invalid storage credential provisioning"));
    }
    let salt = salt()?;
    let normalized = p
        .storage
        .as_ref()
        .unwrap()
        .credential
        .as_ref()
        .unwrap()
        .normalize(password);
    let verifier = accounts::hash(&normalized, &salt)?;
    let mut c = persistence::connect(url)?;
    persistence::verify(&mut c)?;
    let n=c.execute("INSERT INTO storage_credentials(account_id,realm,definition,revision,salt,verifier) SELECT id,$2,$3,1,$4,$5 FROM accounts WHERE name=$1",&[&name,&realm,&p.hash,&&salt[..],&&verifier[..]])?;
    if n != 1 {
        return Err(bad("storage account missing"));
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn policy() {
        let p = Policy {
            minimum: 6,
            maximum: 16,
            fold_ascii: true,
            alphabet: "0123456789:;ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz".into(),
            forbidden: vec!["DENIED".into()],
        };
        assert_eq!(p.normalize("MiXeD_123"), "mixed_123");
        let mut exact = p.clone();
        exact.fold_ascii = false;
        assert_eq!(exact.normalize("MiXeD_123"), "MiXeD_123");
        for v in ["Six_12", "Old:Password;1"] {
            assert!(p.valid(v));
        }
        for v in [
            "short",
            "a".repeat(17).as_str(),
            "abcdef!",
            "éabcde",
            "xDenIedX",
            "space here",
        ] {
            assert!(!p.valid(v));
        }
    }
    #[test]
    #[ignore = "tests/storage_auth_db.py supplies disposable PostgreSQL and package"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let r = &release.rules;
        let p = r.inventory.as_deref().unwrap();
        let mut c = persistence::connect(&url)?;
        let realm = format!("storage-auth-{}", std::process::id());
        let owner = "audit";
        let generation = persistence::acquire(&mut c, &realm, owner)?;
        let o = Arc::new(Owner {
            realm: realm.clone(),
            owner: owner.into(),
            generation,
        });
        struct Heartbeat(
            std::sync::Arc<std::sync::atomic::AtomicBool>,
            Option<std::thread::JoinHandle<()>>,
        );
        impl Drop for Heartbeat {
            fn drop(&mut self) {
                self.0.store(true, std::sync::atomic::Ordering::Relaxed);
                if let Some(t) = self.1.take() {
                    t.join().unwrap();
                }
            }
        }
        let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let (done, uu, oo) = (stop.clone(), url.clone(), o.clone());
        let _heartbeat = Heartbeat(
            stop,
            Some(std::thread::spawn(move || {
                let mut c = persistence::connect(&uu).unwrap();
                while !done.load(std::sync::atomic::Ordering::Relaxed) {
                    persistence::renew(&mut c, &oo.realm, &oo.owner, oo.generation).unwrap();
                    std::thread::sleep(Duration::from_millis(300));
                }
            })),
        );
        let name = format!("auth{}", std::process::id());
        let a: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&name, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let mut actors = vec![];
        for i in 0..2 {
            let id=c.query_one("INSERT INTO characters(account_id,realm,name,online,session_generation,realm_generation) VALUES($1,$2,$3,false,1,$4) RETURNING id",&[&a,&realm,&format!("Protected{i}"),&generation])?.get(0);
            actors.push(Selected {
                id,
                generation: 1,
                life_revision: 0,
                dead: false,
                ready_ticks: 0,
                entity: wire::Entity {
                    health: 100,
                    ..Default::default()
                },
            });
        }
        crate::settlements::convert(
            &mut c,
            &o,
            r.progression.as_ref().unwrap(),
            &release.game,
            20,
        )?;
        c.execute(
            "UPDATE characters SET online=true WHERE realm=$1",
            &[&realm],
        )?;
        let db = Database::start(url.clone(), Default::default())?;
        let rt = tokio::runtime::Runtime::new()?;
        let q = |op, name: &str, old: &str, new: &str| wire::StorageAuthRequest {
            operation: op,
            request: name.into(),
            service: "demo:bank/test".into(),
            password: old.into(),
            replacement: new.into(),
        };
        // Admissions are aged by a fixed clock, never by how long PostgreSQL or the
        // password hash takes: a loaded host can hold one past the window (PQ-289, PQ-291).
        let issued = Instant::now();
        let late = issued + ADMISSION_WINDOW + Duration::from_nanos(1);
        let auth_at = |s: &Selected,
                       q: wire::StorageAuthRequest,
                       now: Box<dyn Fn() -> Instant + Send>| {
            rt.block_on(execute_at(
                &db,
                o.clone(),
                s.clone(),
                p.clone(),
                q,
                issued,
                now,
            ))
        };
        let auth =
            |s: &Selected, q: wire::StorageAuthRequest| auth_at(s, q, Box::new(move || issued));
        let status = || wire::StorageAuthRequest::default();
        let open =
            |c: &mut postgres::Client, s: &Selected, name: &str| -> Result<wire::StorageResult> {
                let b = inventory::execute(c, &o, s, p, &r.item, &wire::BagRequest::default())?
                    .state
                    .unwrap();
                crate::storage::execute_at(
                    c,
                    &o,
                    s,
                    r,
                    &wire::StorageRequest {
                        request: name.into(),
                        service: "demo:bank/test".into(),
                        bag_revision: b.revision,
                        ..Default::default()
                    },
                    issued,
                    &|| issued,
                )
            };
        assert_eq!(auth(&actors[0], status())?.status, "unprovisioned");
        assert_eq!(open(&mut c, &actors[0], "missing")?.status, "unprovisioned");
        provision(&url, &name, &realm, p, "Original_123")?;
        assert!(provision(&url, &name, &realm, p, "Overwrite_123").is_err());
        assert!(check_start(&mut c, &realm, None).is_err());
        let mut removed = p.clone();
        removed.storage.as_mut().unwrap().credential = None;
        assert!(check_start(&mut c, &realm, Some(&removed)).is_err());
        check_start(&mut c, &realm, Some(p))?;
        assert_eq!(auth(&actors[0], status())?.status, "locked");
        for op in 0..=5 {
            let reply = crate::storage::execute_at(
                &mut c,
                &o,
                &actors[0],
                r,
                &wire::StorageRequest {
                    operation: op,
                    request: format!("blocked{op}"),
                    service: "demo:bank/test".into(),
                    instance: if (1..=3).contains(&op) { 1 } else { 0 },
                    quantity: if matches!(op, 1 | 2 | 4 | 5) { 1 } else { 0 },
                    ..Default::default()
                },
                issued,
                &|| issued,
            )?;
            assert_eq!(reply.status, "locked");
            assert!(reply.storage.is_none() && reply.bag.is_none());
        }
        let wrong = q(1, "wrong", "Incorrect_123", "");
        let failed = auth(&actors[0], wrong.clone())?;
        assert_eq!(failed.status, "invalid_credentials");
        assert_eq!(auth(&actors[0], wrong)?, failed);
        assert_eq!(
            auth(&actors[0], q(1, "wrong", "Original_123", ""))?.status,
            "request_conflict"
        );
        let unlock = q(1, "unlock", "oRiGiNaL_123", "");
        let first = auth(&actors[0], unlock.clone())?;
        assert_eq!(first.authorized_revision, 1);
        assert_eq!(auth(&actors[0], unlock.clone())?, first);
        assert_eq!(auth(&actors[0],q(1,"unlock","ORIGINAL_123",""))?.status,"request_conflict");
        assert_eq!(open(&mut c, &actors[0], "open")?.status, "committed");
        assert_eq!(open(&mut c, &actors[1], "other")?.status, "locked");
        assert_eq!(
            auth(&actors[1], q(1, "other-unlock", "Original_123", ""))?.authorized_revision,
            1
        );
        // A grant cannot migrate to a different account even if its revision happens to match.
        let other_name = format!("foreign{}", std::process::id());
        let other: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&other_name, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        provision(&url, &other_name, &realm, p, "Foreign_123")?;
        c.execute(
            "UPDATE characters SET account_id=$2 WHERE id=$1",
            &[&actors[1].id, &other],
        )?;
        assert_eq!(
            open(&mut c, &actors[1], "foreign-account")?.status,
            "locked"
        );
        c.execute(
            "UPDATE characters SET account_id=$2 WHERE id=$1",
            &[&actors[1].id, &a],
        )?;
        let change = q(2, "change", "ORIGINAL_123", "Replacement_123");
        let changed = auth(&actors[0], change.clone())?;
        assert_eq!(
            (
                changed.status.as_str(),
                changed.revision,
                changed.authorized_revision
            ),
            ("changed", 2, 2)
        );
        assert_eq!(auth(&actors[0], change.clone())?, changed);
        assert_eq!(auth(&actors[1], status())?.authorized_revision, 0);
        assert_eq!(open(&mut c, &actors[1], "other")?.status, "locked");
        // Previously acknowledged storage replies are gated, too.
        c.execute(
            "DELETE FROM storage_authorizations WHERE character_id=$1",
            &[&actors[0].id],
        )?;
        assert_eq!(open(&mut c, &actors[0], "open")?.status, "locked");
        let historical = auth(&actors[0], unlock.clone())?;
        assert_eq!(historical.status, "unlocked");
        assert_eq!(historical.revision, 1);
        assert_eq!(historical.authorized_revision, 0);
        assert_eq!(auth(&actors[0], change.clone())?.authorized_revision, 2);
        // Session generation replacement loses grants; exact successful credential retry may regrant the current revision.
        c.execute(
            "UPDATE characters SET session_generation=2 WHERE id=$1",
            &[&actors[0].id],
        )?;
        assert!(auth(&actors[0], status()).is_err());
        let mut reconnect = actors[0].clone();
        reconnect.generation = 2;
        assert_eq!(open(&mut c, &reconnect, "reconnect")?.status, "locked");
        assert_eq!(auth(&reconnect, change.clone())?.authorized_revision, 2);
        let mut far = reconnect.clone();
        far.entity.x = 100.;
        assert_eq!(
            auth(&far, q(1, "far", "Replacement_123", ""))?.status,
            "unavailable"
        );
        // Past the window at the eligibility check: transient, nothing durable.
        let history = |c: &mut postgres::Client, request: &str| -> Result<i64> {
            Ok(c.query_one(
                "SELECT count(*) FROM storage_credential_operations WHERE account_id=$1 AND realm=$2 AND request=$3",
                &[&a, &realm, &request],
            )?
            .get(0))
        };
        let expired = auth_at(
            &reconnect,
            q(1, "expired", "Replacement_123", ""),
            Box::new(move || late),
        )?;
        assert_eq!(expired.status, "unavailable");
        // Fresh at the eligibility check, past the window at COMMIT: refused and rolled
        // back, so no grant is written and the request ID stays unclaimed.
        c.execute(
            "DELETE FROM storage_authorizations WHERE character_id=$1",
            &[&reconnect.id],
        )?;
        let reads = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let counter = reads.clone();
        let error = auth_at(
            &reconnect,
            q(1, "late-commit", "Replacement_123", ""),
            Box::new(move || {
                if counter.fetch_add(1, std::sync::atomic::Ordering::SeqCst) == 0 {
                    issued
                } else {
                    late
                }
            }),
        )
        .unwrap_err();
        assert_eq!(
            (
                error.to_string().as_str(),
                reads.load(std::sync::atomic::Ordering::SeqCst)
            ),
            ("expired credential commit", 2)
        );
        assert_eq!(
            (history(&mut c, "expired")?, history(&mut c, "late-commit")?),
            (0, 0)
        );
        assert_eq!(auth(&reconnect, status())?.authorized_revision, 0);
        // The window is inclusive: an admission exactly at its end still commits.
        let edge = auth_at(
            &reconnect,
            q(1, "late-commit", "Replacement_123", ""),
            Box::new(move || issued + ADMISSION_WINDOW),
        )?;
        assert_eq!((edge.status.as_str(), edge.authorized_revision), ("unlocked", 2));
        assert_eq!(history(&mut c, "late-commit")?, 1);
        c.execute(
            "UPDATE characters SET dead=true,life_revision=1,respawn_ready_at=clock_timestamp() WHERE id=$1",
            &[&reconnect.id],
        )?;
        assert_eq!(
            auth(&reconnect, q(1, "dead", "Replacement_123", ""))?.status,
            "unavailable"
        );
        c.execute(
            "UPDATE characters SET dead=false,life_revision=0,respawn_ready_at=NULL WHERE id=$1",
            &[&reconnect.id],
        )?;
        // Ledger failure rolls back both credential rotation and grant, with no leaked replacement.
        c.batch_execute("CREATE FUNCTION fail_auth_history() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic failure'; END $$;CREATE TRIGGER fail_auth_history BEFORE INSERT ON storage_credential_operations FOR EACH ROW EXECUTE FUNCTION fail_auth_history()")?;
        let rollback = q(2, "rollback", "Replacement_123", "Rollback_123");
        assert!(auth(&reconnect, rollback.clone()).is_err());
        assert_eq!(
            c.query_one(
                "SELECT revision FROM storage_credentials WHERE account_id=$1 AND realm=$2",
                &[&a, &realm]
            )?
            .get::<_, i64>(0),
            2
        );
        c.batch_execute("DROP TRIGGER fail_auth_history ON storage_credential_operations;DROP FUNCTION fail_auth_history()")?;
        assert_eq!(auth(&reconnect, rollback.clone())?.authorized_revision, 3);
        // Two hash computations admit against one snapshot: only one replacement can commit.
        let x = q(2, "race-a", "Rollback_123", "Concurrent_A12");
        let y = q(2, "race-b", "Rollback_123", "Concurrent_B12");
        let (x, y) = rt.block_on(async {
            tokio::join!(
                execute_at(
                    &db,
                    o.clone(),
                    reconnect.clone(),
                    p.clone(),
                    x,
                    issued,
                    move || issued
                ),
                execute_at(
                    &db,
                    o.clone(),
                    actors[1].clone(),
                    p.clone(),
                    y,
                    issued,
                    move || issued
                )
            )
        });
        let (x, y) = (x?, y?);
        let mut statuses = vec![x.status.as_str(), y.status.as_str()];
        statuses.sort();
        assert_eq!(statuses, vec!["changed", "credential_changed"]);
        assert_eq!(
            c.query_one(
                "SELECT revision FROM storage_credentials WHERE account_id=$1 AND realm=$2",
                &[&a, &realm]
            )?
            .get::<_, i64>(0),
            4
        );
        let rows = c.query(
            "SELECT row_to_json(x)::text FROM storage_credential_operations x WHERE account_id=$1",
            &[&a],
        )?;
        for row in rows {
            let text: String = row.get(0);
            for secret in [
                "Original_123",
                "Replacement_123",
                "Rollback_123",
                "Concurrent_A12",
                "Concurrent_B12",
                "Incorrect_123",
            ] {
                assert!(!text.contains(secret));
            }
        }
        assert!(c
            .execute(
                "DELETE FROM storage_credential_operations WHERE account_id=$1",
                &[&a]
            )
            .is_err());
        println!("PASS protected storage: all operations gated, shared account revocation, immutable slow-hash retries, session fences, range/life/deadline, rollback, concurrent rotation, no plaintext ledger");
        Ok(())
    }
}
