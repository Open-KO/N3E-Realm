//! Typed, bounded operations. Authentication precedes lookup; role lock precedes
//! realm and session fencing. Nothing here exposes arbitrary database fields.
use crate::{
    accounts::{Owner, Selected},
    content::{bad, Reader, Release, Result},
    persistence, wire,
};
use postgres::Client;
use prost::Message;
use std::{collections::BTreeSet, path::Path};
pub const CAPS: [&str; 6] = [
    "world.edit",
    "config.edit",
    "entity.spawn",
    "server.inspect",
    "movement.turbo",
    // PQ-194 (D-157): the operator `kill` of a named NPC.
    "entity.kill",
];
pub fn load(path: &Path, game: &str) -> Result<Vec<wire::Property>> {
    let mut r = Reader::open(path)?;
    if r.take(4)? != b"N3T1" {
        return Err(bad("editing magic"));
    }
    let n = r.u()?;
    if n == 0 || n > 128 {
        return Err(bad("property bound"));
    }
    let mut out = vec![];
    let mut keys = BTreeSet::new();
    let mut slots = BTreeSet::new();
    for _ in 0..n {
        let key = r.string()?;
        let kind = r.u()?;
        let target = r.u()?;
        let initial = r.f()?;
        let min = r.f()?;
        let max = r.f()?;
        let (lo, hi) = match kind {
            0 => (0., 1.),
            1..=3 | 7..=8 => (-1000., 1000.),
            4 => (-3.141593, 3.141593),
            5 => (0.05, 10.),
            6 => (0., 0.),
            9 => (0., 1200.),
            10 => (1., 12000.),
            _ => return Err(bad("unsupported property kind")),
        };
        if !key.starts_with(&format!("{game}:"))
            || key.len() > 128
            || !key
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_:.-".contains(&b))
            || !keys.insert(key.clone())
            || !slots.insert((kind, target))
            // PQ-250: a spawn property may name any spawn; the table stays at
            // 128 properties, so a large population edits a chosen few.
            || target >= crate::rules::MAX_SPAWNS
            || ((kind == 0 || kind >= 9) && target != 0)
            || ((1..=6).contains(&kind) && target >= 8)
            || min != lo
            || max != hi
            || initial < lo
            || initial > hi
            || (kind >= 6 && kind != 7 && kind != 8 && initial.fract() != 0.)
        {
            return Err(bad("property policy"));
        }
        out.push(wire::Property {
            key,
            kind,
            target,
            initial,
            min,
            max,
            r#type: if kind == 6 || kind >= 9 {
                "integer"
            } else {
                "number"
            }
            .into(),
            scope: "zone".into(),
            capability: "world.edit".into(),
            persistence: "durable".into(),
            activation: if kind >= 7 { "next_spawn" } else { "next_tick" }.into(),
            schema: 1,
        });
    }
    r.end()?;
    if !slots.contains(&(0, 0)) {
        return Err(bad("lighting required"));
    }
    for &(kind, target) in &slots {
        if (1..=6).contains(&kind) && (1..=6).any(|k| !slots.contains(&(k, target))) {
            return Err(bad("incomplete decoration"));
        }
    }
    Ok(out)
}
pub fn baseline(r: &Release) -> wire::Revision {
    wire::Revision {
        base: r.hash.clone(),
        revision: 0,
        tick: 0,
        values: r
            .properties
            .iter()
            .map(|p| wire::PropertyValue {
                key: p.key.clone(),
                value: p.initial,
            })
            .collect(),
    }
}
pub fn validate(r: &Release, s: &wire::Revision) -> Result<()> {
    if s.base != r.hash || s.values.len() != r.properties.len() {
        return Err(bad("incompatible_base"));
    }
    for (p, v) in r.properties.iter().zip(&s.values) {
        if p.key != v.key
            || !v.value.is_finite()
            || v.value < p.min
            || v.value > p.max
            || (p.r#type == "integer" && v.value.fract() != 0.)
        {
            return Err(bad("invalid_property"));
        }
    }
    // PQ-250: one pass over the properties, then one over the spawns, so a
    // zone's whole population costs O(spawns + properties) per validation.
    let mut points = r.rules.spawns.to_vec();
    for (p, v) in r.properties.iter().zip(&s.values) {
        if let Some(point) = points.get_mut(p.target as usize) {
            match p.kind {
                7 => point[0] = v.value,
                8 => point[1] = v.value,
                _ => {}
            }
        }
    }
    for point in points {
        if !r.height(point[0], point[1]).is_finite() {
            return Err(bad("spawn_not_walkable"));
        }
        // A reference slot point is also the fallback placement: an actor must fit there.
        if r.rules.npc_policy.as_ref().is_some_and(|p| p.reference.is_some())
            && !crate::movement::standable(&r.collision, point[0], point[1])
        {
            return Err(bad("spawn_not_walkable"));
        }
    }
    if r.properties
        .iter()
        .any(|p| (p.kind == 7 || p.kind == 8) && p.target as usize >= r.rules.spawns.len())
    {
        return Err(bad("spawn index"));
    }
    let corpse = value(r, s, 9, 0, 0.);
    // Reference slots own their respawn delays and offer no global respawn property.
    let slot_respawn = r
        .rules
        .npc_policy
        .as_ref()
        .and_then(|p| p.reference.as_ref())
        .and_then(|p| p.slots.iter().map(|s| s.respawn).min());
    let respawn = value(r, s, 10, 0, slot_respawn.map_or(1., |v| v as f32));
    if corpse > respawn {
        return Err(bad("corpse exceeds respawn"));
    }
    Ok(())
}
pub fn value(r: &Release, s: &wire::Revision, kind: u32, target: u32, fallback: f32) -> f32 {
    r.properties
        .iter()
        .zip(&s.values)
        .find(|(p, _)| p.kind == kind && p.target == target)
        .map(|(_, v)| v.value)
        .unwrap_or(fallback)
}
pub fn cycle_rules(r: &Release, s: &wire::Revision, index: usize) -> crate::rules::Rules {
    let mut rules = r.rules.clone();
    let point = rules.spawns[index];
    rules.spawn_x = value(r, s, 7, index as u32, point[0]);
    rules.spawn_z = value(r, s, 8, index as u32, point[1]);
    if let Some(ref mut p) = rules.life {
        p.corpse = value(r, s, 9, 0, p.corpse as f32) as u32;
        p.npc_respawn = value(r, s, 10, 0, p.npc_respawn as f32) as u32;
    }
    if let Some(slot) = r
        .rules
        .npc_policy
        .as_ref()
        .and_then(|p| p.reference.as_ref())
        .and_then(|p| p.slots.get(index))
    {
        rules.npc_slot = Some(index);
        if let Some(ref mut p) = rules.life {
            p.npc_respawn = slot.respawn;
        }
        // PQ-249: the slot's template becomes this NPC's rules.
        if let Some(t) = slot.template {
            let template = r.rules.npc_policy.as_ref().and_then(|p| p.reference.as_ref()).map(|p| &p.templates[t]);
            rules.apply_template(t, template.expect("loaded slot template"));
        }
    }
    rules
}
pub fn startup(c: &mut Client, o: &Owner, r: &Release) -> Result<wire::Revision> {
    let mut t = c.transaction()?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    let state = if let Some(row) = t.query_opt(
        "SELECT state FROM world_revisions WHERE realm=$1 ORDER BY revision DESC LIMIT 1",
        &[&o.realm],
    )? {
        wire::Revision::decode(row.get::<_, Vec<u8>>(0).as_slice())?
    } else {
        let s = baseline(r);
        t.execute(
            "INSERT INTO world_revisions VALUES($1,0,$2,$3)",
            &[&o.realm, &r.hash, &s.encode_to_vec()],
        )?;
        s
    };
    validate(r, &state)?;
    t.commit()?;
    Ok(state)
}
fn lock_role(t: &mut postgres::Transaction<'_>, id: i64) -> Result<i64> {
    t.execute(
        "INSERT INTO admin_authority(character_id) VALUES($1) ON CONFLICT DO NOTHING",
        &[&id],
    )?;
    Ok(t.query_one(
        "SELECT generation FROM admin_authority WHERE character_id=$1 FOR UPDATE",
        &[&id],
    )?
    .get(0))
}
pub fn role(
    c: &mut Client,
    account: &str,
    id: i64,
    realm: &str,
    cap: &str,
    grant: bool,
) -> Result<()> {
    if !CAPS.contains(&cap) {
        return Err(bad("unknown capability"));
    }
    let mut t = c.transaction()?;
    let g = lock_role(&mut t, id)?;
    if t.query_opt("SELECT c.id FROM characters c JOIN accounts a ON a.id=c.account_id WHERE c.id=$1 AND c.realm=$2 AND a.name=$3",&[&id,&realm,&account])?.is_none(){return Err(bad("character/account/realm mismatch"));}
    if grant {
        t.execute(
            "INSERT INTO character_roles VALUES($1,$2,'*',$3) ON CONFLICT DO NOTHING",
            &[&id, &realm, &cap],
        )?;
    } else {
        t.execute(
            "DELETE FROM character_roles WHERE character_id=$1 AND realm=$2 AND capability=$3",
            &[&id, &realm, &cap],
        )?;
    }
    t.execute(
        "UPDATE admin_authority SET generation=generation+1 WHERE character_id=$1",
        &[&id],
    )?;
    t.execute("INSERT INTO role_audit(character_id,realm,capability,granted,generation) VALUES($1,$2,$3,$4,$5)",&[&id,&realm,&cap,&grant,&(g+1)])?;
    t.commit()?;
    // Both capabilities the simulation leases (turbo, and server.inspect for
    // the NPC trace and the operator chat mark, PQ-178) return from a revoke
    // only once the simulation has applied it, so a later line is unmarked.
    if (cap == "movement.turbo" || cap == "server.inspect") && !grant {
        crate::turbo::await_revocation(c, id, g + 1)?;
    }
    Ok(())
}
pub fn response(
    q: &wire::AdminRequest,
    status: &str,
    state: Option<wire::Revision>,
) -> wire::AdminResult {
    wire::AdminResult {
        id: q.id.clone(),
        status: status.into(),
        revision: state.as_ref().map(|s| s.revision).unwrap_or(0),
        state,
        ..Default::default()
    }
}
fn fault(point: &str) {
    if std::env::var("N3E_ADMIN_FAULT").as_deref() == Ok(point) {
        std::process::exit(86);
    }
}
pub fn execute(
    c: &mut Client,
    o: &Owner,
    s: &Selected,
    r: &Release,
    q: &wire::AdminRequest,
) -> Result<(wire::AdminResult, wire::Registry)> {
    if q.session != s.generation as u64 {
        return Ok((response(q, "stale_session", None), Default::default()));
    }
    let mut t = c.transaction()?;
    let generation = lock_role(&mut t, s.id)?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    let Some(actor)=t.query_opt("SELECT account_id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE",&[&s.id,&o.realm,&s.generation,&o.generation])? else {return Ok((response(q,"stale_session",None),Default::default()));};
    let account: i64 = actor.get(0);
    let capabilities:Vec<String>=t.query("SELECT capability FROM character_roles WHERE character_id=$1 AND realm=$2 AND zone='*' ORDER BY capability",&[&s.id,&o.realm])?.iter().map(|x|x.get(0)).collect();
    let registry = wire::Registry {
        properties: r.properties.clone(),
        capabilities: capabilities.clone(),
        generation: generation as u64,
        base: r.hash.clone(),
    };
    let state = wire::Revision::decode(
        t.query_one(
            "SELECT state FROM world_revisions WHERE realm=$1 ORDER BY revision DESC LIMIT 1",
            &[&o.realm],
        )?
        .get::<_, Vec<u8>>(0)
        .as_slice(),
    )?;
    if q.operation == "registry" {
        return Ok((response(q, "inspected", Some(state)), registry));
    }
    if q.id.is_empty()
        || q.id.len() > 64
        || !q
            .id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
        || q.patch.len() > 128
        || q.reason.len() > 160
        || q.encode_to_vec().len() > 32768
    {
        return Ok((response(q, "invalid_request", None), registry));
    }
    let mut canonical = q.clone();
    canonical.session = 0;
    let payload = canonical.encode_to_vec();
    if let Some(row)=t.query_opt("SELECT payload,result FROM admin_results WHERE realm=$1 AND character_id=$2 AND request=$3",&[&o.realm,&s.id,&q.id])? {
  let mut result=if q.operation=="status" || row.get::<_,Vec<u8>>(0)==payload {wire::AdminResult::decode(row.get::<_,Vec<u8>>(1).as_slice())?}else{response(q,"payload_conflict",None)};
  // PQ-194 (D-157): a stored kill authorization is never acted on again. A
  // retry or status lookup answers kill_replayed, which the simulation does
  // not strike on, so only a fresh request (checked against entity.kill above
  // the result table) can kill.
  if result.status=="kill_authorized" {result.status="kill_replayed".into();result.detail.clear();}
  return Ok((result,registry));
 }
    if q.operation == "status" {
        return Ok((response(q, "unknown", None), registry));
    }
    let cap = match q.operation.as_str() {
        "publish" | "revert" => "world.edit",
        "spawn" => "entity.spawn",
        "kill" => "entity.kill",
        "inspect" | "trace" | "record" | "show" | "hide" => "server.inspect",
        _ => return Ok((response(q, "unsupported", None), registry)),
    };
    if !capabilities.iter().any(|x| x == cap) {
        return Ok((response(q, "denied", None), registry));
    }
    if q.operation == "inspect" {
        return Ok((response(q, "inspected", Some(state)), registry));
    }
    if q.operation == "show" || q.operation == "hide" {
        // PQ-192 (D-153): the holder's show switch (KO's operator commands
        // VIEW and UNVIEW). Authorized here against the authenticated
        // character's roles; the simulation applies it on the session's tick
        // only while its server.inspect lease is current. Read-only like
        // trace: no durable result, so status lookups say unknown.
        let status = if q.operation == "show" { "show_authorized" } else { "hide_authorized" };
        return Ok((response(q, status, None), registry));
    }
    if q.operation == "trace" || q.operation == "record" {
        // PQ-186 (trace) and PQ-189 (record): authorized here against the
        // authenticated character's roles; the simulation applies the mark or
        // writes the record (or refuses) on the session's tick. Read-only like
        // inspect: no durable result, so status lookups say unknown.
        if q.entity == 0 || q.entity > i64::MAX as u64 {
            return Ok((response(q, "invalid_target", None), registry));
        }
        let status = if q.operation == "trace" {
            "trace_authorized"
        } else {
            "record_authorized"
        };
        let mut result = response(q, status, None);
        result.detail = q.entity.to_string();
        return Ok((result, registry));
    }
    if q.operation == "kill" {
        // PQ-194 (D-157): authorized here against the authenticated character's
        // roles and audited in this transaction, as spawn is; the simulation
        // kills the NPC (or refuses) on the session's tick. Entity ids never
        // repeat, so a replay of this stored authorization kills at most once.
        if q.entity == 0 || q.entity > i64::MAX as u64 {
            return Ok((response(q, "invalid_target", None), registry));
        }
        if q.reason.trim().is_empty() || q.reason.chars().any(char::is_control) {
            return Ok((response(q, "invalid_reason", None), registry));
        }
        let mut result = response(q, "kill_authorized", None);
        result.detail = q.entity.to_string();
        let target = format!("kill:{}", q.entity);
        t.execute(
            "INSERT INTO admin_results VALUES($1,$2,$3,$4,$5)",
            &[&o.realm, &s.id, &q.id, &payload, &result.encode_to_vec()],
        )?;
        t.execute("INSERT INTO admin_audit(realm,account_id,character_id,request,revision,target,reason,before_state,after_state,outcome) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$8,'kill_authorized')",&[&o.realm,&account,&s.id,&q.id,&(state.revision as i64),&target,&q.reason,&state.encode_to_vec()])?;
        t.commit()?;
        return Ok((result, registry));
    }
    if q.operation == "spawn" {
        if q.base != r.hash || q.spawn as usize >= r.rules.spawns.len() {
            return Ok((response(q, "invalid_spawn", None), registry));
        }
        if q.reason.trim().is_empty() || q.reason.chars().any(char::is_control) {
            return Ok((response(q, "invalid_reason", None), registry));
        }
        let mut result = response(q, "spawn_authorized", None);
        result.detail = format!("{}:{}", o.generation, q.spawn);
        t.execute(
            "INSERT INTO admin_results VALUES($1,$2,$3,$4,$5)",
            &[&o.realm, &s.id, &q.id, &payload, &result.encode_to_vec()],
        )?;
        t.execute("INSERT INTO admin_audit(realm,account_id,character_id,request,revision,target,reason,before_state,after_state,outcome) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$8,'temporary_authorized')",&[&o.realm,&account,&s.id,&q.id,&(state.revision as i64),&q.operation,&q.reason,&state.encode_to_vec()])?;
        t.commit()?;
        return Ok((result, registry));
    }
    if q.base != r.hash {
        return Ok((response(q, "incompatible_base", Some(state)), registry));
    }
    if q.expected != state.revision {
        return Ok((response(q, "conflict", Some(state)), registry));
    }
    if q.reason.trim().is_empty() || q.reason.chars().any(char::is_control) {
        return Ok((response(q, "invalid_reason", None), registry));
    }
    let mut next = state.clone();
    if q.operation == "revert" {
        let Some(row) = t.query_opt(
            "SELECT state FROM world_revisions WHERE realm=$1 AND revision=$2",
            &[&o.realm, &(q.revision as i64)],
        )?
        else {
            return Ok((response(q, "unknown_revision", None), registry));
        };
        next = wire::Revision::decode(row.get::<_, Vec<u8>>(0).as_slice())?;
        if let Err(e)=crate::reward_upgrades::rebase_world(&mut t,&o.realm,r,&mut next) {
            let mut result=response(q,"invalid_property",None);result.detail=e.to_string();return Ok((result,registry));
        }
    } else {
        if q.patch.is_empty() {
            return Ok((response(q, "invalid_property", None), registry));
        }
        let mut seen = BTreeSet::new();
        for v in &q.patch {
            if !seen.insert(&v.key) {
                return Ok((response(q, "invalid_property", None), registry));
            }
            let Some(slot) = next.values.iter_mut().find(|s| s.key == v.key) else {
                return Ok((
                    response(
                        q,
                        if ["collision", "stats", "movement", "assets", "tick_rate"]
                            .iter()
                            .any(|k| v.key.contains(k))
                        {
                            "restart_required"
                        } else {
                            "invalid_property"
                        },
                        None,
                    ),
                    registry,
                ));
            };
            slot.value = v.value;
        }
    }
    if let Err(e) = validate(r, &next) {
        let mut result = response(q, "invalid_property", None);
        result.detail = e.to_string();
        return Ok((result, registry));
    }
    next.revision = state
        .revision
        .checked_add(1)
        .filter(|v| *v < i64::MAX as u64)
        .ok_or_else(|| bad("revision exhausted"))?;
    next.tick = 0;
    let result = response(q, "committed", Some(next.clone()));
    t.execute(
        "INSERT INTO world_revisions VALUES($1,$2,$3,$4)",
        &[
            &o.realm,
            &(next.revision as i64),
            &r.hash,
            &next.encode_to_vec(),
        ],
    )?;
    t.execute(
        "INSERT INTO admin_results VALUES($1,$2,$3,$4,$5)",
        &[&o.realm, &s.id, &q.id, &payload, &result.encode_to_vec()],
    )?;
    t.execute("INSERT INTO admin_audit(realm,account_id,character_id,request,revision,target,reason,before_state,after_state,outcome) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'committed')",&[&o.realm,&account,&s.id,&q.id,&(next.revision as i64),&q.operation,&q.reason,&state.encode_to_vec(),&next.encode_to_vec()])?;
    fault("before_commit");
    t.commit()?;
    fault("after_commit");
    Ok((result, registry))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "disposable PostgreSQL supplied by tests/administration.py"]
    fn transaction_races_and_audit_rollback() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = persistence::connect(&url)?;
        let r = std::sync::Arc::new(crate::content::load(Path::new(&std::env::var(
            "N3E_PACKAGE",
        )?))?);
        let realm = format!("p4-race-{}", std::process::id());
        let g = persistence::acquire(&mut c, &realm, "test")?;
        let o = Owner {
            realm: realm.clone(),
            owner: "test".into(),
            generation: g,
        };
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let id:i64=c.query_one("INSERT INTO characters(account_id,realm,name,online,session_generation,realm_generation) VALUES($1,$2,'Race',true,1,$3) RETURNING id",&[&account,&realm,&g])?.get(0);
        let s = Selected {
            id,
            generation: 1,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            entity: Default::default(),
        };
        startup(&mut c, &o, &r)?;
        let key = r.properties[0].key.clone();
        let mut revision = 0;
        for i in 0..12 {
            persistence::renew(&mut c, &realm, "test", g)?;
            role(&mut c, &realm, id, &realm, "world.edit", true)?;
            let q = wire::AdminRequest {
                session: 1,
                id: format!("race-{i}"),
                operation: "publish".into(),
                expected: revision,
                base: r.hash.clone(),
                patch: vec![wire::PropertyValue {
                    key: key.clone(),
                    value: 0.4,
                }],
                reason: "race".into(),
                ..Default::default()
            };
            let mut other = persistence::connect(&url)?;
            let barrier = std::sync::Barrier::new(2);
            let result = std::thread::scope(|scope| -> Result<_> {
                let b = &barrier;
                let realm = &realm;
                let revoke = scope.spawn(move || {
                    b.wait();
                    role(&mut other, realm, id, realm, "world.edit", false)
                });
                barrier.wait();
                let result = execute(&mut c, &o, &s, &r, &q)?;
                revoke.join().unwrap()?;
                Ok(result.0)
            })?;
            assert!(["committed", "denied"].contains(&result.status.as_str()));
            if result.status == "committed" {
                revision += 1;
                assert_eq!(execute(&mut c, &o, &s, &r, &q)?.0.status, "committed");
            }
            let mut later = q;
            later.id = format!("later-{i}");
            later.expected = revision;
            assert_eq!(execute(&mut c, &o, &s, &r, &later)?.0.status, "denied");
        }
        // An audit insert failure must roll back the revision and immutable result too.
        role(&mut c, &realm, id, &realm, "world.edit", true)?;
        c.batch_execute("CREATE FUNCTION pg_temp.reject_admin_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test audit unavailable'; END $$; CREATE TRIGGER test_audit_failure BEFORE INSERT ON admin_audit FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_admin_audit()")?;
        let q = wire::AdminRequest {
            session: 1,
            id: "audit-failure".into(),
            operation: "publish".into(),
            expected: revision,
            base: r.hash.clone(),
            patch: vec![wire::PropertyValue { key, value: 0.2 }],
            reason: "audit failure".into(),
            ..Default::default()
        };
        assert!(execute(&mut c, &o, &s, &r, &q).is_err());
        c.batch_execute("DROP TRIGGER test_audit_failure ON admin_audit")?;
        assert_eq!(
            c.query_one(
                "SELECT max(revision) FROM world_revisions WHERE realm=$1",
                &[&realm]
            )?
            .get::<_, i64>(0),
            revision as i64
        );
        assert_eq!(
            c.query_one(
                "SELECT count(*) FROM admin_results WHERE realm=$1 AND request='audit-failure'",
                &[&realm]
            )?
            .get::<_, i64>(0),
            0
        );
        let mut stale = s.clone();
        stale.generation = 2;
        let mut stale_q = q.clone();
        stale_q.session = 2;
        assert_eq!(
            execute(&mut c, &o, &stale, &r, &stale_q)?.0.status,
            "stale_session"
        );
        let mut wrong = o.clone();
        wrong.generation += 1;
        assert!(execute(&mut c, &wrong, &s, &r, &q).is_err());
        // PQ-194 (D-157): the operator kill needs entity.kill on the
        // authenticated character; an authorized request is audited with its
        // durable result in one transaction, a refused one writes nothing.
        let kill = |id: &str, entity: u64, reason: &str| wire::AdminRequest {
            session: 1,
            id: id.into(),
            operation: "kill".into(),
            entity,
            reason: reason.into(),
            ..Default::default()
        };
        let audits = |c: &mut Client, request: &str| -> Result<Vec<(String, String, String)>> {
            Ok(c.query("SELECT target,reason,outcome FROM admin_audit WHERE realm=$1 AND character_id=$2 AND request=$3",&[&realm,&id,&request])?
                .iter().map(|x| (x.get(0), x.get(1), x.get(2))).collect())
        };
        let results = |c: &mut Client, request: &str| -> Result<i64> {
            Ok(c.query_one("SELECT count(*) FROM admin_results WHERE realm=$1 AND character_id=$2 AND request=$3",&[&realm,&id,&request])?.get(0))
        };
        // world.edit (held) and every other capability do not grant it.
        for cap in ["entity.spawn", "server.inspect", "movement.turbo", "config.edit"] {
            role(&mut c, &realm, id, &realm, cap, true)?;
        }
        assert_eq!(execute(&mut c, &o, &s, &r, &kill("kill-denied", 42, "test"))?.0.status, "denied");
        assert!(audits(&mut c, "kill-denied")?.is_empty() && results(&mut c, "kill-denied")? == 0);
        role(&mut c, &realm, id, &realm, "entity.kill", true)?;
        let (granted, registry) = execute(&mut c, &o, &s, &r, &kill("kill-zero", 0, "test"))?;
        assert_eq!(granted.status, "invalid_target");
        assert!(registry.capabilities.contains(&"entity.kill".to_string()));
        assert_eq!(execute(&mut c, &o, &s, &r, &kill("kill-high", 1 << 63, "test"))?.0.status, "invalid_target");
        assert_eq!(execute(&mut c, &o, &s, &r, &kill("kill-blank", 42, " "))?.0.status, "invalid_reason");
        assert_eq!(execute(&mut c, &o, &s, &r, &kill("kill-control", 42, "a\nb"))?.0.status, "invalid_reason");
        for refused in ["kill-zero", "kill-high", "kill-blank", "kill-control"] {
            assert!(audits(&mut c, refused)?.is_empty() && results(&mut c, refused)? == 0, "{refused}");
        }
        let authorized = execute(&mut c, &o, &s, &r, &kill("kill-1", 42, "test kill"))?.0;
        assert_eq!((authorized.status.as_str(), authorized.detail.as_str()), ("kill_authorized", "42"));
        assert_eq!(audits(&mut c, "kill-1")?, vec![("kill:42".into(), "test kill".into(), "kill_authorized".into())]);
        // A retry and a status lookup answer kill_replayed (the simulation never
        // strikes on it); another payload under the same id conflicts; nothing
        // is audited twice.
        let replay = execute(&mut c, &o, &s, &r, &kill("kill-1", 42, "test kill"))?.0;
        assert_eq!((replay.status.as_str(), replay.detail.as_str()), ("kill_replayed", ""));
        assert_eq!(execute(&mut c, &o, &s, &r, &kill("kill-1", 43, "test kill"))?.0.status, "payload_conflict");
        let lookup = wire::AdminRequest { session: 1, id: "kill-1".into(), operation: "status".into(), ..Default::default() };
        assert_eq!(execute(&mut c, &o, &s, &r, &lookup)?.0.status, "kill_replayed");
        assert_eq!(audits(&mut c, "kill-1")?.len(), 1);
        // A revocation refuses the next request, and a stored authorization
        // replayed after it still never answers kill_authorized; a stale
        // session never reaches the check.
        role(&mut c, &realm, id, &realm, "entity.kill", false)?;
        assert_eq!(execute(&mut c, &o, &s, &r, &kill("kill-2", 42, "test"))?.0.status, "denied");
        assert_eq!(execute(&mut c, &o, &s, &r, &kill("kill-1", 42, "test kill"))?.0.status, "kill_replayed");
        let mut stale_kill = kill("kill-3", 42, "test");
        stale_kill.session = 2;
        assert_eq!(execute(&mut c, &o, &stale, &r, &stale_kill)?.0.status, "stale_session");
        assert!(audits(&mut c, "kill-2")?.is_empty() && audits(&mut c, "kill-3")?.is_empty());
        Ok(())
    }
}
