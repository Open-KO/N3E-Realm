//! Bounded directed rosters. Durable membership and live presence are separate.
use crate::{
    accounts::{Owner, Selected},
    content::{bad, Reader, Result},
    persistence, wire,
};
use prost::Message;
use std::{
    path::Path,
    time::{Duration, Instant},
};
#[derive(Clone, Debug)]
pub struct Policy {
    pub capacity: u32,
    pub name_bytes: usize,
    pub refresh_ticks: u64,
    pub hash: Vec<u8>,
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3F1" {
            return Err(bad("friend policy magic"));
        }
        let p = Self {
            capacity: r.u()?,
            name_bytes: r.u()? as usize,
            refresh_ticks: r.u()? as u64,
            hash: openssl::sha::sha256(&std::fs::read(path)?).to_vec(),
        };
        if !(1..=24).contains(&p.capacity)
            || !(1..=24).contains(&p.name_bytes)
            || !(1..=1200).contains(&p.refresh_ticks)
        {
            return Err(bad("friend policy bounds"));
        }
        r.end()?;
        Ok(p)
    }
    pub fn name(&self, name: &str) -> bool {
        crate::accounts::valid_name(name, self.name_bytes)
    }
}
#[derive(Clone)]
pub struct Admission {
    pub target: Selected,
    pub issued: Instant,
}
pub fn check_start(c: &mut postgres::Client, realm: &str, p: Option<&Policy>) -> Result<()> {
    for row in c.query("SELECT DISTINCT f.definition FROM friend_lists f JOIN characters c ON c.id=f.character_id WHERE c.realm=$1",&[&realm])?{if p.is_none_or(|p|p.hash!=row.get::<_,Vec<u8>>(0)){return Err(bad("incompatible durable friends; explicit migration required"));}}
    Ok(())
}
fn snapshot(
    t: &mut postgres::Transaction<'_>,
    s: &Selected,
    o: &Owner,
    p: &Policy,
    q: &wire::FriendRequest,
    revision: i64,
    status: &str,
) -> Result<wire::FriendResult> {
    let mut entries = vec![];
    for row in t.query("SELECT f.slot,c.id,c.name,c.realm FROM friend_links f JOIN characters c ON c.id=f.target_id WHERE f.character_id=$1 ORDER BY f.slot",&[&s.id])? {
  let slot:i32=row.get(0);let name:String=row.get(2);if slot<0||slot as u32>=p.capacity||!p.name(&name)||row.get::<_,String>(3)!=o.realm{return Err(bad("durable friend record"));}
  entries.push(wire::FriendEntry{slot:slot as u32,character:row.get::<_,i64>(1) as u64,name});
 }
    if entries.len() > p.capacity as usize {
        return Err(bad("friend capacity"));
    }
    Ok(wire::FriendResult {
        request: q.request.clone(),
        status: status.into(),
        revision: revision as u64,
        capacity: p.capacity,
        entries,
    })
}
/// How long a simulation admission stays valid until its add commits (D-068). n3e's own
/// freshness bound: the binary game server queues the add to its DB agent with no time
/// check (`004c59fa`, response `004c5bbc`; PQ-289 evidence).
pub const ADMISSION_WINDOW: Duration = Duration::from_secs(2);
pub fn execute(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    p: &Policy,
    q: &wire::FriendRequest,
    admission: Option<&Admission>,
) -> Result<wire::FriendResult> {
    execute_at(c, o, s, p, q, admission, Instant::now)
}
/// `execute` with the clock that ages the admission, read at admission check and again
/// just before COMMIT. Production passes `Instant::now`; tests pass a fixed clock so the
/// window, not database speed, decides fresh and expired (PQ-289).
fn execute_at(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    p: &Policy,
    q: &wire::FriendRequest,
    admission: Option<&Admission>,
    now: impl Fn() -> Instant,
) -> Result<wire::FriendResult> {
    let fresh = |a: &Admission| now().saturating_duration_since(a.issued) <= ADMISSION_WINDOW;
    if q.operation > 2
        || q.expected_revision > i64::MAX as u64
        || (q.operation == 0
            && (!q.request.is_empty() || !q.name.is_empty() || q.expected_revision != 0))
        || (q.operation > 0 && (!crate::accounts::valid_name(&q.request, 64) || !p.name(&q.name)))
    {
        return Err(bad("invalid friend request"));
    }
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if t.query_opt("SELECT 1 FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE",&[&s.id,&o.realm,&s.generation,&o.generation])?.is_none(){return Err(bad("stale friend session"));}
    t.execute(
        "INSERT INTO friend_lists(character_id,definition) VALUES($1,$2) ON CONFLICT DO NOTHING",
        &[&s.id, &p.hash],
    )?;
    let row = t.query_one(
        "SELECT definition,revision FROM friend_lists WHERE character_id=$1 FOR UPDATE",
        &[&s.id],
    )?;
    if row.get::<_, Vec<u8>>(0) != p.hash {
        return Err(bad("friend definition conflict"));
    }
    let mut revision: i64 = row.get(1);
    let mut result = snapshot(&mut t, s, o, p, q, revision, "ok")?;
    let payload = q.encode_to_vec();
    if q.operation == 0 {
        t.commit()?;
        return Ok(result);
    }
    if let Some(row) = t.query_opt(
        "SELECT payload,result FROM friend_operations WHERE character_id=$1 AND request=$2",
        &[&s.id, &q.request],
    )? {
        if row.get::<_, Vec<u8>>(0) == payload {
            return Ok(wire::FriendResult::decode(
                row.get::<_, Vec<u8>>(1).as_slice(),
            )?);
        }
        result.status = "request_conflict".into();
        return Ok(result);
    }
    let status = if q.expected_revision != revision as u64 {
        "revision_conflict"
    } else if q.operation == 1 {
        let valid = admission.filter(|a| {
            fresh(a)
                && !a.target.dead
                && a.target.entity.health > 0
                && a.target.entity.name.eq_ignore_ascii_case(&q.name)
        });
        let Some(admission) = valid else {
            result.status = "unavailable".into();
            return Ok(result);
        };
        let target = &admission.target;
        // The server's fresh admission captures online/alive eligibility, as the legacy
        // server does before its asynchronous DB-agent request. Membership survives logout.
        let name: String = t
            .query_opt(
                "SELECT name FROM characters WHERE id=$1 AND realm=$2",
                &[&target.id, &o.realm],
            )?
            .ok_or_else(|| bad("friend target missing"))?
            .get(0);
        if !p.name(&name) {
            return Err(bad("friend target name"));
        }
        if result
            .entries
            .iter()
            .any(|e| e.character == target.id as u64)
        {
            "already_friend"
        } else if result.entries.len() >= p.capacity as usize {
            "full"
        } else {
            let slot = (0..p.capacity)
                .find(|slot| !result.entries.iter().any(|e| e.slot == *slot))
                .unwrap();
            t.execute(
                "INSERT INTO friend_links(character_id,slot,target_id) VALUES($1,$2,$3)",
                &[&s.id, &(slot as i32), &target.id],
            )?;
            "committed"
        }
    } else {
        let exact = result.entries.iter().find(|e| e.name == q.name);
        let mut folded = result
            .entries
            .iter()
            .filter(|e| e.name.eq_ignore_ascii_case(&q.name));
        let first = folded.next();
        let entry = exact.or_else(|| if folded.next().is_none() { first } else { None });
        if let Some(entry) = entry {
            t.execute(
                "DELETE FROM friend_links WHERE character_id=$1 AND target_id=$2",
                &[&s.id, &(entry.character as i64)],
            )?;
            "committed"
        } else {
            "not_found"
        }
    };
    if status == "committed" {
        revision = revision
            .checked_add(1)
            .ok_or_else(|| bad("friend revision overflow"))?;
        t.execute(
            "UPDATE friend_lists SET revision=$2 WHERE character_id=$1",
            &[&s.id, &revision],
        )?;
    }
    result = snapshot(&mut t, s, o, p, q, revision, status)?;
    t.execute(
        "INSERT INTO friend_operations(character_id,request,payload,result) VALUES($1,$2,$3,$4)",
        &[&s.id, &q.request, &payload, &result.encode_to_vec()],
    )?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    if q.operation == 1 && status == "committed" && !admission.is_some_and(fresh) {
        return Err(bad("expired friend commit"));
    }
    fault("before_commit");
    t.commit()?;
    fault("after_commit");
    Ok(result)
}
fn fault(point: &str) {
    if std::env::var("N3E_FRIEND_FAULT").as_deref() == Ok(point) {
        eprintln!("FRIEND_FAULT {point}");
        std::process::exit(97);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "tests/friends_db.py supplies disposable PostgreSQL and package"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let p = release.rules.friends.as_deref().unwrap();
        let mut c = persistence::connect(&url)?;
        let realm = format!("friends-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "audit")?;
        persistence::acquire(&mut c,&format!("{realm}-foreign"),"foreign-fixture")?;
        let o = Owner {
            realm: realm.clone(),
            owner: "audit".into(),
            generation,
        };
        let mut actors = vec![];
        for i in 0..28 {
            let account: i64 = c
                .query_one(
                    "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                    &[
                        &format!("fr{}_{i}", std::process::id()),
                        &&[0u8; 16][..],
                        &&[0u8; 32][..],
                    ],
                )?
                .get(0);
            let target_realm = if i == 27 {
                format!("{realm}-foreign")
            } else {
                realm.clone()
            };
            let name = format!("Peer{i}");
            let id=c.query_one("INSERT INTO characters(account_id,realm,name,online,session_generation,realm_generation) VALUES($1,$2,$3,true,1,$4) RETURNING id",&[&account,&target_realm,&name,&generation])?.get(0);
            actors.push(Selected {
                id,
                generation: 1,
                life_revision: 0,
                dead: false,
                ready_ticks: 0,
                entity: wire::Entity {
                    name,
                    health: 100,
                    ..Default::default()
                },
            });
        }
        let a = &actors[0];
        let b = &actors[1];
        let read = |c: &mut postgres::Client, s: &Selected| {
            execute(c, &o, s, p, &wire::FriendRequest::default(), None)
        };
        let request = |op, id: &str, revision, name: &str| wire::FriendRequest {
            operation: op,
            request: id.into(),
            expected_revision: revision,
            name: name.into(),
        };
        // Admissions are aged by a fixed clock, never by how long PostgreSQL takes: the
        // gate's loaded disposable cluster once pushed a fresh add past the window (PQ-289).
        let issued = Instant::now();
        let admit = |s: &Selected| Admission {
            target: s.clone(),
            issued,
        };
        let aged = |c: &mut postgres::Client,
                    q: &wire::FriendRequest,
                    target: Option<&Selected>,
                    now: &dyn Fn() -> Instant|
         -> Result<wire::FriendResult> {
            persistence::renew(c, &o.realm, &o.owner, o.generation)?;
            execute_at(c, &o, a, p, q, target.map(admit).as_ref(), now)
        };
        let call = |c: &mut postgres::Client,
                    q: &wire::FriendRequest,
                    target: Option<&Selected>|
         -> Result<wire::FriendResult> { aged(c, q, target, &|| issued) };
        let late = issued + ADMISSION_WINDOW + Duration::from_nanos(1);
        let mut state = read(&mut c, a)?;
        assert_eq!(
            (state.revision, state.capacity, state.entries.len()),
            (0, 24, 0)
        );
        assert!(read(&mut c, b)?.entries.is_empty());
        let add = request(1, "first", 0, "peer2");
        let first = call(&mut c, &add, Some(&actors[2]))?;
        assert_eq!(first.status, "committed");
        assert_eq!(
            (
                first.entries[0].character,
                first.entries[0].name.as_str(),
                first.entries[0].slot
            ),
            (actors[2].id as u64, "Peer2", 0)
        );
        assert!(read(&mut c, b)?.entries.is_empty());
        assert_eq!(call(&mut c, &add, None)?, first);
        let mut altered = add.clone();
        altered.name = "Peer3".into();
        assert_eq!(
            call(&mut c, &altered, Some(&actors[3]))?.status,
            "request_conflict"
        );
        assert_eq!(
            call(
                &mut c,
                &request(1, "duplicate", 1, "Peer2"),
                Some(&actors[2])
            )?
            .status,
            "already_friend"
        );
        assert_eq!(
            call(&mut c, &request(1, "offline", 1, "Peer3"), None)?.status,
            "unavailable"
        );
        let mut dead = actors[3].clone();
        dead.dead = true;
        dead.entity.health = 0;
        assert_eq!(
            call(&mut c, &request(1, "dead", 1, "Peer3"), Some(&dead))?.status,
            "unavailable"
        );
        // Past the window at admission check: transient, nothing durable.
        assert_eq!(
            aged(
                &mut c,
                &request(1, "expired", 1, "Peer3"),
                Some(&actors[3]),
                &|| late
            )?
            .status,
            "unavailable"
        );
        // Fresh at admission check, past the window at COMMIT: refused and rolled back,
        // so the request ID stays unclaimed and the roster unchanged.
        let reads = std::cell::Cell::new(0);
        let error = aged(
            &mut c,
            &request(1, "late-commit", 1, "Peer3"),
            Some(&actors[3]),
            &|| {
                reads.set(reads.get() + 1);
                if reads.get() == 1 {
                    issued
                } else {
                    late
                }
            },
        )
        .unwrap_err();
        assert_eq!(
            (error.to_string().as_str(), reads.get()),
            ("expired friend commit", 2)
        );
        state = read(&mut c, a)?;
        assert_eq!((state.revision, state.entries.len()), (1, 1));
        let claimed: i64 = c
            .query_one(
                "SELECT count(*) FROM friend_operations WHERE character_id=$1 AND request IN ('expired','late-commit')",
                &[&a.id],
            )?
            .get(0);
        assert_eq!(claimed, 0);
        // Eligibility is captured before the DB request. Later logout does not cancel it.
        c.execute(
            "UPDATE characters SET online=false WHERE id=$1",
            &[&actors[3].id],
        )?;
        // The window is inclusive: an admission exactly at its end still commits.
        state = aged(
            &mut c,
            &request(1, "logout-race", 1, "Peer3"),
            Some(&actors[3]),
            &|| issued + ADMISSION_WINDOW,
        )?;
        assert_eq!(state.status, "committed");
        for i in 4..26 {
            state = call(
                &mut c,
                &request(
                    1,
                    &format!("fill{i}"),
                    state.revision,
                    &actors[i].entity.name,
                ),
                Some(&actors[i]),
            )?;
            assert_eq!(state.status, "committed");
        }
        assert_eq!(state.entries.len(), 24);
        assert_eq!(state.entries.last().unwrap().slot, 23);
        assert_eq!(
            call(
                &mut c,
                &request(1, "full", state.revision, "Peer26"),
                Some(&actors[26])
            )?
            .status,
            "full"
        );
        let old = state.clone();
        let remove = request(2, "remove-offline", state.revision, "pEeR3");
        state = call(&mut c, &remove, None)?;
        assert_eq!(state.status, "committed");
        assert!(!state
            .entries
            .iter()
            .any(|e| e.character == actors[3].id as u64));
        assert_eq!(call(&mut c, &remove, None)?, state);
        assert_eq!(
            call(
                &mut c,
                &request(2, "absent", state.revision, "Nobody"),
                None
            )?
            .status,
            "not_found"
        );
        state = call(
            &mut c,
            &request(1, "reuse-slot", state.revision, "Peer26"),
            Some(&actors[26]),
        )?;
        assert_eq!(
            state
                .entries
                .iter()
                .find(|e| e.character == actors[26].id as u64)
                .unwrap()
                .slot,
            1
        );
        assert_eq!(
            call(
                &mut c,
                &request(2, "old-revision", old.revision, "Peer2"),
                None
            )?
            .status,
            "revision_conflict"
        );
        let before = state.clone();
        c.batch_execute("CREATE FUNCTION fail_friend_history() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic friend failure'; END $$;CREATE TRIGGER fail_friend_history BEFORE INSERT ON friend_operations FOR EACH ROW EXECUTE FUNCTION fail_friend_history()")?;
        let rollback = request(2, "rollback", before.revision, "Peer2");
        assert!(call(&mut c, &rollback, None).is_err());
        let current = read(&mut c, a)?;
        assert_eq!(current.revision, before.revision);
        assert_eq!(current.entries, before.entries);
        c.batch_execute("DROP TRIGGER fail_friend_history ON friend_operations;DROP FUNCTION fail_friend_history()")?;
        state = call(&mut c, &rollback, None)?;
        assert_eq!(state.status, "committed");
        // Ordinary self addition is allowed by the binary server's target lookup.
        state = call(
            &mut c,
            &request(1, "self", state.revision, "Peer0"),
            Some(a),
        )?;
        assert_eq!(state.status, "committed");
        let barrier = std::sync::Arc::new(std::sync::Barrier::new(3));
        let mut workers = vec![];
        persistence::renew(&mut c, &realm, &o.owner, o.generation)?;
        for (i, name) in ["Peer4", "Peer5"].iter().enumerate() {
            let (url, o, a, p, barrier) = (
                url.clone(),
                o.clone(),
                a.clone(),
                p.clone(),
                barrier.clone(),
            );
            let q = request(2, &format!("race{i}"), state.revision, name);
            workers.push(std::thread::spawn(move || {
                let mut c = persistence::connect(&url).unwrap();
                barrier.wait();
                execute(&mut c, &o, &a, &p, &q, None).unwrap()
            }));
        }
        barrier.wait();
        let mut results: Vec<_> = workers
            .into_iter()
            .map(|w| w.join().unwrap().status)
            .collect();
        results.sort();
        assert_eq!(results, vec!["committed", "revision_conflict"]);
        state = read(&mut c, a)?;
        assert!(call(
            &mut c,
            &request(1, "foreign", state.revision, "Peer27"),
            Some(&actors[27])
        )
        .is_err());
        let mut stale = a.clone();
        stale.generation += 1;
        assert!(read(&mut c, &stale).is_err());
        assert!(read(&mut c, &actors[27]).is_err());
        let mut old_owner = o.clone();
        old_owner.generation += 1;
        assert!(execute(
            &mut c,
            &old_owner,
            a,
            p,
            &wire::FriendRequest::default(),
            None
        )
        .is_err());
        check_start(&mut c, &realm, Some(p))?;
        assert!(check_start(&mut c, &realm, None).is_err());
        let mut changed = p.clone();
        changed.hash[0] ^= 1;
        assert!(check_start(&mut c, &realm, Some(&changed)).is_err());
        for q in [
            request(1, "", state.revision, "Peer2"),
            request(1, "malformed", state.revision, "../Peer2"),
            request(2, "large", u64::MAX, "Peer2"),
        ] {
            assert!(call(&mut c, &q, None).is_err());
        }
        assert!(c
            .execute(
                "DELETE FROM friend_operations WHERE character_id=$1",
                &[&a.id]
            )
            .is_err());
        assert_eq!(call(&mut c, &add, None)?, first);
        println!("PASS durable friends: directed ownership, live admission/dead/expiry at check and commit, offline removal, 24 slots/full/reuse, self, immutable retries, revision race, rollback, session/realm fences and downgrade policy");
        Ok(())
    }
}
