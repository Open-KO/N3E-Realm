//! Authoritative, bounded cast-time abilities. Legacy IDs belong to game content.
use crate::{
    content::{bad, Reader, Result},
    wire,
};
use std::{collections::BTreeSet, path::Path};
#[derive(Clone, Debug)]
pub struct Skill {
    pub id: String,
    pub label: String,
    pub class: String,
    pub level: u32,
    pub cost: u32,
    pub cast_ms: u32,
    pub cooldown_ms: u32,
    pub target: u32,
    pub amount: u32,
    pub survival: u32,
    pub attribute: u32,
    pub resistance: u32,
    pub animation: u32,
    pub range: f32,
    pub weapons: Vec<String>,
}
/// PQ-465 (D-232): the package's range rule, margins over each skill's range.
/// `start` is added, with both actors' radii, to the 3-D limit a cast must be
/// within when it is accepted (1298's client check `00583780`, which the
/// server enforces); `hold` is added to the limit the target must stay below
/// from the release to the impact, measured on the ground (x/z) plane when
/// `planar` (Ebenezer's magic packet check `004c1dbe`, Range + 15 for Type1 3).
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Reach {
    pub start: f32,
    pub hold: f32,
    pub planar: bool,
}
/// Which range check a cast's state calls for (D-232), and so which stage
/// it is in: only the acceptance (`Start`) tests the weapon (D-244).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Range {
    /// The acceptance: the start limit and the hold, and the weapon.
    Start,
    /// From the release to the impact: the hold only.
    Hold,
    /// Between the acceptance and the release: no range check, as neither
    /// 1298's cast tick nor Ebenezer checks it before the effecting.
    Unchecked,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub archetype: String,
    pub label: String,
    pub reach: Reach,
    /// Both actors' radii summed, from the package's melee rules (0 without
    /// them), as the ranged attack's limit sums them (D-216); set when the
    /// package loads, not stored in `skills.bin`.
    pub radii: f32,
    pub skills: Vec<Skill>,
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        let (notice, failed, refusals) = match r.take(4)? {
            b"N3K2" => (false, false, false),
            b"N3K3" => (true, false, false),
            b"N3K4" => (true, true, false),
            b"N3K5" => (true, true, true),
            _ => return Err(bad("skill magic")),
        };
        let archetype = r.string()?;
        let label = r.string()?;
        let reach = Reach {
            start: r.f()?,
            hold: r.f()?,
            planar: match r.u()? {
                0 => false,
                1 => true,
                _ => return Err(bad("skill reach plane")),
            },
        };
        if !(0. ..=50.).contains(&reach.start) || !(0. ..=50.).contains(&reach.hold) {
            return Err(bad("skill reach"));
        }
        // PQ-466 (D-234): N3K3's notice is the client's line for a cast it
        // does not send; the server bounds it as the client does and keeps
        // nothing of it (its own refusal is still `out_of_range`).
        // PQ-469 (D-235): N3K4's failed line is the client's line for this
        // server's own `out_of_range` refusal of a skill, in its colour; the
        // server bounds it the same way and keeps nothing of it either.
        let line = |r: &mut Reader, what: &'static str| -> Result<()> {
            let text = r.string()?;
            let rest = text.find('%').map(|at| &text[at..]);
            if text.len() > 96
                || !text.bytes().all(|b| (b' '..=b'~').contains(&b))
                || rest.is_some_and(|rest| !rest.starts_with("%s") || rest[2..].contains('%'))
            {
                return Err(bad(what));
            }
            Ok(())
        };
        if notice {
            line(&mut r, "skill notice")?;
        }
        if failed {
            line(&mut r, "skill failed line")?;
            if r.u()? >> 24 == 0 {
                return Err(bad("skill failed colour"));
            }
        }
        // PQ-479 (D-243): N3K5's refusal lines are the client's lines for
        // this server's refusal of a skill at its acceptance, one per status
        // (never `out_of_range`, which has the failed line), each for a target
        // the client saw as any actor (0), a player (1) or an NPC (2), with
        // its colour. The server bounds them as the client does and keeps
        // nothing of them; its refusals are unchanged.
        if refusals {
            let count = r.u()?;
            if !(1..=8).contains(&count) {
                return Err(bad("skill refusal lines"));
            }
            let mut statuses = BTreeSet::new();
            for _ in 0..count {
                let status = r.string()?;
                let mut bytes = status.bytes();
                if !bytes.next().is_some_and(|b| b.is_ascii_lowercase())
                    || !bytes.all(|b| b.is_ascii_lowercase() || b == b'_')
                    || status.len() > 32
                    || status == "out_of_range"
                    || !statuses.insert(status)
                    || r.u()? > 2
                {
                    return Err(bad("skill refusal line"));
                }
                line(&mut r, "skill refusal line")?;
                if r.u()? >> 24 == 0 {
                    return Err(bad("skill refusal colour"));
                }
            }
        }
        let count = r.u()?;
        if !(1..=32).contains(&count) {
            return Err(bad("skill count"));
        }
        let mut skills = Vec::new();
        let mut seen = BTreeSet::new();
        for _ in 0..count {
            let s = Skill {
                id: r.string()?,
                label: r.string()?,
                class: r.string()?,
                level: r.u()?,
                cost: r.u()?,
                cast_ms: r.u()?,
                cooldown_ms: r.u()?,
                target: r.u()?,
                amount: r.u()?,
                survival: r.u()?,
                attribute: r.u()?,
                resistance: r.u()?,
                animation: r.u()?,
                range: r.f()?,
                weapons: {
                    let n = r.u()?;
                    if n > 64 {
                        return Err(bad("skill weapons"));
                    }
                    let mut v = Vec::new();
                    for _ in 0..n {
                        v.push(r.string()?);
                    }
                    v
                },
            };
            if !seen.insert(s.id.clone())
                || s.label.is_empty()
                || s.label.len() > 80
                || !(1..=100).contains(&s.level)
                || s.cost > 100000
                || !(50..=10000).contains(&s.cast_ms)
                || s.cooldown_ms > 60000
                || !(1..=2).contains(&s.target)
                || !(1..=5000).contains(&s.amount)
                || s.survival > 100
                || s.attribute > 4
                || s.resistance > 200
                || s.animation > 31
                || s.range <= 0.
                || s.range > 50.
            {
                return Err(bad("skill bounds"));
            }
            r.string()?;
            r.string()?;
            let n = r.u()?;
            if !(1..=2).contains(&n) {
                return Err(bad("skill attachments"));
            }
            let mut joints = BTreeSet::new();
            for _ in 0..n {
                let joint = r.u()?;
                if joint > 128 || !joints.insert(joint) {
                    return Err(bad("skill joint"));
                }
            }
            if r.u()? > 128 {
                return Err(bad("skill target joint"));
            }
            skills.push(s);
        }
        r.end()?;
        Ok(Self {
            archetype,
            label,
            reach,
            radii: 0.,
            skills,
        })
    }
    pub fn get(&self, id: &str) -> Option<&Skill> {
        self.skills.iter().find(|s| s.id == id)
    }
    /// PQ-465 (D-232): whether `target` is within `skill`'s range for the
    /// check `range`. A cast on the caster itself passes (Ebenezer's
    /// `004c1dbe` passes the same id, `004c1f73`). The hold passes while the
    /// distance, on the ground plane when `planar`, is below range + `hold`
    /// (`004c1dbe` fails at equality, `004c1fbf`); the start passes while the
    /// 3-D distance is at most range + both radii + `start` (1298's
    /// `00583780`). A non-finite distance fails both.
    pub fn reaches(&self, skill: &Skill, range: Range, actor: &wire::Entity, target: &wire::Entity) -> bool {
        if range == Range::Unchecked || actor.id == target.id {
            return true;
        }
        let (dx, dy, dz) = (actor.x - target.x, actor.y - target.y, actor.z - target.z);
        let space = dx * dx + dy * dy + dz * dz;
        let hold = skill.range + self.reach.hold;
        let held = if self.reach.planar { dx * dx + dz * dz } else { space } < hold * hold;
        held && (range == Range::Hold || space.sqrt() <= skill.range + self.radii + self.reach.start)
    }
    /// A skill's requirements against an actor and its target, with the
    /// range check the cast's state calls for (`range`). PQ-480 (D-244): the
    /// weapon is tested only at the acceptance (`Range::Start`). 1298 tests
    /// a row's need-item kind (`+0x70`) only in its usable check `0057f7f0`
    /// (`0057fe54`), which its skill start `005819e0` calls (`005829e2`)
    /// and its release `00584b00` does not; Ebenezer's admission `00464b43`
    /// reads no hand slot, and neither client nor server refuses an item
    /// move while a cast runs (`0049f7c0`, `004a1aa4`). So a weapon removed
    /// after the acceptance does not refuse the cast; the impact reads the
    /// caster's attributes as they then are, never the removed weapon's.
    pub fn validate(
        &self,
        skill: &Skill,
        range: Range,
        level: u32,
        actor: &wire::Entity,
        target: &wire::Entity,
        bag: Option<&wire::BagState>,
    ) -> std::result::Result<(), &'static str> {
        skill.validate(
            &self.archetype,
            level,
            actor,
            target,
            || self.reaches(skill, range, actor, target),
            || range != Range::Start || skill.armed(bag),
        )
    }
}
impl Skill {
    fn validate(
        &self,
        class: &str,
        level: u32,
        actor: &wire::Entity,
        target: &wire::Entity,
        reaches: impl FnOnce() -> bool,
        armed: impl FnOnce() -> bool,
    ) -> std::result::Result<(), &'static str> {
        if self.class != class {
            return Err("wrong_class");
        }
        if level < self.level {
            return Err("level_required");
        }
        if actor.health == 0 {
            return Err("actor_dead");
        }
        if target.health == 0 {
            return Err("target_dead");
        }
        if (self.target == 1 && target.npc) || (self.target == 2 && !target.npc) {
            return Err("invalid_target");
        }
        if !reaches() {
            return Err("out_of_range");
        }
        if actor.resource < self.cost {
            return Err("insufficient_resource");
        }
        if !armed() {
            return Err("weapon_required");
        }
        Ok(())
    }
    /// Whether the caster holds one of the skill's weapons (a skill that
    /// names none needs none).
    fn armed(&self, bag: Option<&wire::BagState>) -> bool {
        self.weapons.is_empty()
            || bag.is_some_and(|b| {
                b.equipment
                    .iter()
                    .any(|e| e.instance > 0 && self.weapons.contains(&e.item))
            })
    }
    // Player-to-NPC AI binary0040e7c4; the separate NPC routine differs.
    // Package bounds avoid the legacy signed-short overflow domain.
    pub fn damage(&self, attributes: &[u32], rng: &mut impl crate::damage::Rolls) -> u32 {
        let stat = attributes
            .get(self.attribute as usize)
            .copied()
            .unwrap_or(0)
            .min(1000);
        let base = self.amount as u64 * (stat as u64 + 20) / 186;
        let upper = (base * 230 / (self.resistance as u64 + 250)).min(32767) as u32;
        let roll = rng.roll(upper + 1);
        let fixed = (upper as f64 * 0.85f32 as f64).trunc();
        (fixed + roll as f64 * 0.3f32 as f64).trunc() as u32
    }
}

/// What a recast gate read, and what its commit wrote.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Gate {
    /// The skill's remaining durable cooldown in ticks (0: ready).
    pub remaining: u32,
    /// PQ-472 (D-236): the deadline this commit wrote, as microseconds since
    /// the epoch, or `None` when it wrote nothing (a read, or a cooldown that
    /// still ran). Only `recover_undoing` uses it, to delete exactly that row.
    pub stamp: Option<i64>,
}

pub async fn gate(
    db: crate::accounts::Database,
    owner: std::sync::Arc<crate::accounts::Owner>,
    selected: crate::accounts::Selected,
    skill: Skill,
    commit: bool,
) -> Result<Gate> {
    gate_at(db, owner, selected, skill, commit, crate::clock::tick_ms()).await
}

// The durable cooldown is a wall-clock deadline for a tick count: cooldown_ms of
// game time is cooldown_ms x tick_ms / 50 of wall time, and the remaining wall time
// reads back as ticks at tick_ms each (the identity at the production 50 ms).
async fn gate_at(
    db: crate::accounts::Database,
    owner: std::sync::Arc<crate::accounts::Owner>,
    selected: crate::accounts::Selected,
    skill: Skill,
    commit: bool,
    tick_ms: u64,
) -> Result<Gate> {
    db.call(move |c|{
        let mut t=c.transaction()?;
        crate::persistence::fence(&mut t,&owner.realm,&owner.owner,owner.generation)?;
        let row=t.query_opt("SELECT dead,life_revision FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE",&[&selected.id,&owner.realm,&selected.generation,&owner.generation])?.ok_or_else(||bad("stale skill session"))?;
        if row.get::<_,bool>(0)||row.get::<_,i64>(1)!=selected.life_revision{return Err(bad("stale skill life"));}
        let remaining=t.query_opt("SELECT GREATEST(0,ceil(extract(epoch FROM (ready_at-clock_timestamp()))*1000/$3::bigint))::bigint FROM character_skill_cooldowns WHERE character_id=$1 AND skill=$2",&[&selected.id,&skill.id,&(tick_ms as i64)])?.map_or(0,|r|r.get::<_,i64>(0).clamp(0,1200) as u32);
        let mut stamp=None;
        if remaining==0&&commit {
            // PostgreSQL 17's extract returns numeric, so the microsecond
            // stamp is exact and names this write alone.
            stamp=Some(t.query_one("INSERT INTO character_skill_cooldowns(character_id,skill,ready_at) VALUES($1,$2,clock_timestamp()+$3::bigint*interval '1 millisecond') ON CONFLICT(character_id,skill) DO UPDATE SET ready_at=EXCLUDED.ready_at RETURNING (extract(epoch FROM ready_at)*1000000)::bigint",&[&selected.id,&skill.id,&((u64::from(skill.cooldown_ms)*tick_ms/crate::clock::TICK_MS) as i64)])?.get::<_,i64>(0));
        }
        t.commit()?;Ok(Gate{remaining,stamp})
    }).await
}

// Read on session entry, so the UI and admission recover recast gates together.
pub async fn recover(
    db: crate::accounts::Database,
    owner: std::sync::Arc<crate::accounts::Owner>,
    selected: crate::accounts::Selected,
) -> Result<Vec<(String, u32)>> {
    recover_at(db, owner, selected, None, crate::clock::tick_ms()).await
}

/// PQ-472 (D-236): undo a recast commit whose impact was refused before
/// Ebenezer's reuse window would have started (`Gate::stamp` of the cast's
/// commit), then recover, in one fenced transaction. Only the row holding
/// exactly that deadline is deleted: a deadline another write left stays.
/// The commit required the skill's previous deadline to have passed, so
/// deleting the row restores what the gate reads. A stale session or realm
/// fence fails the whole transaction and the deadline stays.
pub async fn recover_undoing(
    db: crate::accounts::Database,
    owner: std::sync::Arc<crate::accounts::Owner>,
    selected: crate::accounts::Selected,
    skill: String,
    stamp: i64,
) -> Result<Vec<(String, u32)>> {
    recover_at(db, owner, selected, Some((skill, stamp)), crate::clock::tick_ms()).await
}

async fn recover_at(
    db: crate::accounts::Database,
    owner: std::sync::Arc<crate::accounts::Owner>,
    selected: crate::accounts::Selected,
    undo: Option<(String, i64)>,
    tick_ms: u64,
) -> Result<Vec<(String, u32)>> {
    db.call(move |c| {
        let mut t=c.transaction()?;
        crate::persistence::fence(&mut t,&owner.realm,&owner.owner,owner.generation)?;
        // An undo locks the character row as the gate does, so it is ordered
        // with any gate of the same character.
        let lock=if undo.is_some(){" FOR UPDATE"}else{""};
        if t.query_opt(&format!("SELECT id FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online{lock}"),&[&selected.id,&owner.realm,&selected.generation,&owner.generation])?.is_none(){return Err(bad("stale skill session"));}
        if let Some((skill,stamp))=&undo{
            t.execute("DELETE FROM character_skill_cooldowns WHERE character_id=$1 AND skill=$2 AND (extract(epoch FROM ready_at)*1000000)::bigint=$3",&[&selected.id,skill,stamp])?;
        }
        let rows=t.query("SELECT skill,LEAST(1200,ceil(extract(epoch FROM (ready_at-clock_timestamp()))*1000/$2::bigint))::bigint FROM character_skill_cooldowns WHERE character_id=$1 AND ready_at>clock_timestamp() ORDER BY skill LIMIT 32",&[&selected.id,&(tick_ms as i64)])?;
        let result=rows.iter().map(|r|(r.get(0),r.get::<_,i64>(1).max(0) as u32)).collect();t.commit()?;Ok(result)
    }).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        accounts::{Database, Owner, Selected},
        persistence,
    };
    use std::sync::Arc;
    fn sample() -> Skill {
        Skill {
            id: "demo:skill/test".into(),
            label: "Test".into(),
            class: "demo:class/test".into(),
            level: 2,
            cost: 5,
            cast_ms: 1500,
            cooldown_ms: 5400,
            target: 2,
            amount: 29,
            survival: 50,
            attribute: 4,
            resistance: 0,
            animation: 0,
            range: 25.,
            weapons: vec![],
        }
    }
    fn policy(skill: &Skill, reach: Reach, radii: f32) -> Policy {
        Policy {
            archetype: skill.class.clone(),
            label: "Test".into(),
            reach,
            radii,
            skills: vec![skill.clone()],
        }
    }
    #[test]
    fn authority_requirements() {
        let mut s = sample();
        let p = policy(&s, Reach::default(), 0.);
        let mut actor = wire::Entity {
            id: 1,
            health: 100,
            resource: 5,
            ..Default::default()
        };
        let mut target = wire::Entity {
            id: 2,
            npc: true,
            health: 40,
            x: 24.99,
            ..Default::default()
        };
        let check = |p: &Policy, s: &Skill, level, a: &wire::Entity, t: &wire::Entity| {
            p.validate(s, Range::Start, level, a, t, None)
        };
        assert_eq!(check(&p, &s, 2, &actor, &target), Ok(()));
        let mut other = p.clone();
        other.archetype = "other".into();
        assert_eq!(check(&other, &s, 2, &actor, &target), Err("wrong_class"));
        assert_eq!(check(&p, &s, 1, &actor, &target), Err("level_required"));
        // With no margins the start limit is the range itself, inclusive, and
        // the hold (exclusive) refuses its boundary.
        target.x = 25.;
        assert_eq!(check(&p, &s, 2, &actor, &target), Err("out_of_range"));
        assert_eq!(p.validate(&s, Range::Unchecked, 2, &actor, &target, None), Ok(()));
        target.x = 0.;
        actor.resource = 4;
        assert_eq!(check(&p, &s, 2, &actor, &target), Err("insufficient_resource"));
        actor.resource = 5;
        actor.health = 0;
        assert_eq!(check(&p, &s, 2, &actor, &target), Err("actor_dead"));
        actor.health = 100;
        target.health = 0;
        assert_eq!(check(&p, &s, 2, &actor, &target), Err("target_dead"));
        target.health = 40;
        target.npc = false;
        assert_eq!(check(&p, &s, 2, &actor, &target), Err("invalid_target"));
        s.target = 1;
        assert_eq!(check(&p, &s, 2, &actor, &target), Ok(()));
        s.weapons.push("demo:item/wand".into());
        assert_eq!(check(&p, &s, 2, &actor, &target), Err("weapon_required"));
        // PQ-480 (D-244): only the acceptance tests the weapon.
        for range in [Range::Unchecked, Range::Hold] {
            assert_eq!(p.validate(&s, range, 2, &actor, &target, None), Ok(()), "{range:?}");
        }
        let bag = wire::BagState {
            equipment: vec![wire::ItemStack { instance: 1, item: "demo:item/wand".into(), ..Default::default() }],
            ..Default::default()
        };
        assert_eq!(p.validate(&s, Range::Start, 2, &actor, &target, Some(&bag)), Ok(()));
        let unsaved = wire::BagState {
            equipment: vec![wire::ItemStack { instance: 0, item: "demo:item/wand".into(), ..Default::default() }],
            ..Default::default()
        };
        assert_eq!(p.validate(&s, Range::Start, 2, &actor, &target, Some(&unsaved)), Err("weapon_required"));
    }
    /// PQ-465 (D-232): Moradon's rule (start 2, hold 15 on the ground plane,
    /// 1 m radii): a cast is accepted within 25 + 2 + 2 = 29 m in 3-D and holds
    /// while the target stays below 40 m on the ground, whatever its height.
    #[test]
    fn start_limit_and_ground_plane_hold() {
        let s = sample();
        let p = policy(&s, Reach { start: 2., hold: 15., planar: true }, 2.);
        let actor = wire::Entity { id: 1, health: 100, resource: 5, ..Default::default() };
        let at = |x: f32, y: f32, z: f32| wire::Entity { id: 2, npc: true, health: 40, x, y, z, ..Default::default() };
        let ok = |range, t: &wire::Entity| p.validate(&s, range, 2, &actor, t, None);
        // The start: 3-D, inclusive, the radii and the margin added.
        assert_eq!(ok(Range::Start, &at(29., 0., 0.)), Ok(()));
        assert_eq!(ok(Range::Start, &at(0., 0., 29.01)), Err("out_of_range"));
        assert_eq!(ok(Range::Start, &at(28., 8., 0.)), Err("out_of_range"), "height counts at the start");
        // The hold: the ground plane, exclusive.
        assert_eq!(ok(Range::Hold, &at(39.99, 0., 0.)), Ok(()));
        assert_eq!(ok(Range::Hold, &at(0., 0., 40.)), Err("out_of_range"));
        assert_eq!(ok(Range::Hold, &at(30., 30., 20.)), Ok(()), "height does not count in the hold");
        assert_eq!(ok(Range::Hold, &at(30., 0., 30.)), Err("out_of_range"));
        assert_eq!(ok(Range::Unchecked, &at(300., 0., 0.)), Ok(()));
        // A 3-D hold measures the height too.
        let mut space = p.clone();
        space.reach.planar = false;
        assert_eq!(space.validate(&s, Range::Hold, 2, &actor, &at(30., 30., 20.), None), Err("out_of_range"));
        // The start also requires the hold, so a hold below the start limit
        // bounds it.
        let mut short = p.clone();
        short.reach.hold = 0.;
        assert_eq!(short.validate(&s, Range::Start, 2, &actor, &at(26., 0., 0.), None), Err("out_of_range"));
        // A cast on the caster passes wherever it stands; a non-finite
        // position fails.
        let mut me = at(1000., 0., 0.);
        me.id = actor.id;
        assert!(p.reaches(&s, Range::Hold, &actor, &me) && p.reaches(&s, Range::Start, &actor, &me));
        assert!(!p.reaches(&s, Range::Hold, &actor, &at(f32::NAN, 0., 0.)));
        assert!(!p.reaches(&s, Range::Start, &actor, &at(0., f32::INFINITY, 0.)));
    }
    /// The N3K2 header the cooker writes (tools/assetc/skills.py): the reach
    /// after the label, bounded on load.
    #[test]
    fn reach_header_bounds() {
        let dir = std::env::temp_dir().join(format!("n3e-skills-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("skills.bin");
        let string = |v: &str| [&(v.len() as u32).to_le_bytes()[..], v.as_bytes()].concat();
        // `tail`: the raw bytes after the reach (N3K3's notice, N3K4's
        // notice, failed line and colour).
        let raw = |magic: &[u8], start: f32, hold: f32, plane: u32, tail: &[u8]| {
            let mut b = magic.to_vec();
            b.extend(string("demo:class/test"));
            b.extend(string("Test"));
            b.extend(start.to_le_bytes());
            b.extend(hold.to_le_bytes());
            b.extend(plane.to_le_bytes());
            b.extend(tail);
            b.extend(1u32.to_le_bytes());
            for v in ["demo:skill/test", "Test", "demo:class/test"] {
                b.extend(string(v));
            }
            for v in [2u32, 5, 1500, 5400, 2, 29, 50, 4, 0, 0] {
                b.extend(v.to_le_bytes());
            }
            b.extend(25f32.to_le_bytes());
            b.extend(0u32.to_le_bytes());
            b.extend(string("cast"));
            b.extend(string("hit"));
            for v in [1u32, 13, 0] {
                b.extend(v.to_le_bytes());
            }
            std::fs::write(&path, b).unwrap();
            Policy::load(&path)
        };
        let with = |magic: &[u8], start: f32, hold: f32, plane: u32, notice: Option<&str>| {
            raw(magic, start, hold, plane, &notice.map(string).unwrap_or_default())
        };
        let file = |magic: &[u8], start: f32, hold: f32, plane: u32| with(magic, start, hold, plane, None);
        let p = file(b"N3K2", 2., 15., 1).unwrap();
        assert_eq!(p.reach, Reach { start: 2., hold: 15., planar: true });
        assert_eq!(p.radii, 0.);
        assert!(file(b"N3K1", 2., 15., 1).is_err(), "the old layout has no reach");
        for (start, hold, plane) in [(-0.5, 15., 1), (2., 50.5, 1), (f32::NAN, 15., 1), (2., f32::INFINITY, 0), (2., 15., 2)] {
            assert!(file(b"N3K2", start, hold, plane).is_err(), "{start} {hold} {plane}");
        }
        // PQ-466 (D-234): N3K3 carries the client's too-far line after the
        // reach; the server bounds it as the client does and keeps nothing.
        for notice in ["Skill Failed - Too far", "%s is too far", &"x".repeat(96)] {
            let p = with(b"N3K3", 2., 15., 1, Some(notice)).unwrap();
            assert_eq!((p.reach.start, p.skills.len()), (2., 1), "{notice}");
        }
        for notice in ["", "%d too far", "%s and %s", "100%", "%", "tab\there", "caf\u{e9}", &"x".repeat(97)] {
            assert!(with(b"N3K3", 2., 15., 1, Some(notice)).is_err(), "{notice:?}");
        }
        assert!(with(b"N3K2", 2., 15., 1, Some("Too far")).is_err(), "N3K2 has no notice");
        assert!(file(b"N3K3", 2., 15., 1).is_err(), "N3K3 needs its notice");
        // PQ-469 (D-235): N3K4 carries, after the notice, the client's line
        // for this server's `out_of_range` and its colour, bounded as the
        // notice is, the colour's alpha not 0; the server keeps nothing.
        let failed = |text: &str, color: Option<u32>| {
            let mut tail = string("Too far");
            tail.extend(string(text));
            if let Some(color) = color {
                tail.extend(color.to_le_bytes());
            }
            raw(b"N3K4", 2., 15., 1, &tail)
        };
        for (text, color) in [("%s failed", 0xffff3b3b), ("Failed", 0x01000000), (&*"x".repeat(96), 0xffffffff)] {
            let p = failed(text, Some(color)).unwrap();
            assert_eq!((p.reach.start, p.skills.len()), (2., 1), "{text}");
        }
        for text in ["", "%d failed", "%s and %s", "100%", "tab\there", "caf\u{e9}", &"x".repeat(97)] {
            assert!(failed(text, Some(0xffff3b3b)).is_err(), "{text:?}");
        }
        assert!(failed("%s failed", Some(0x00ff3b3b)).is_err(), "a transparent colour");
        assert!(failed("%s failed", None).is_err(), "N3K4 needs its colour");
        assert!(with(b"N3K4", 2., 15., 1, Some("Too far")).is_err(), "N3K4 needs its failed line");
        let mut tail = string("Too far");
        tail.extend(string("%s failed"));
        tail.extend(0xffff3b3bu32.to_le_bytes());
        assert!(raw(b"N3K3", 2., 15., 1, &tail).is_err(), "N3K3 has no failed line");
        // PQ-479 (D-243): N3K5 carries, after the failed line, the client's
        // lines for this server's refusals at the acceptance: 1-8 of them,
        // one per status (not `out_of_range`), a target kind 0-2, a text
        // bounded as the notice is and a colour whose alpha is not 0.
        let lines = |lines: &[(&str, u32, &str, u32)], count: Option<u32>| {
            let mut five = tail.clone();
            five.extend(count.unwrap_or(lines.len() as u32).to_le_bytes());
            for (status, target, text, color) in lines {
                five.extend(string(status));
                five.extend(target.to_le_bytes());
                five.extend(string(text));
                five.extend(color.to_le_bytes());
            }
            raw(b"N3K5", 2., 15., 1, &five)
        };
        let good = [
            ("level_required", 0, "Casting failed", 0xffff3b3b),
            ("insufficient_resource", 0, "Skill Failed - Not enough MP", 0xffffff00),
            ("target_dead", 2, "Casting failed", 0xffff3b3b),
            ("wrong_class", 1, "%s: you cannot use this", 0xffffff00),
        ];
        assert_eq!(lines(&good, None).unwrap().skills.len(), 1);
        let eight: Vec<_> = ["a", "b", "c", "d", "e", "f", "g", "h"].iter().map(|s| (*s, 0, "x", 0xff000000)).collect();
        assert!(lines(&eight, None).is_ok(), "eight lines");
        let nine: Vec<_> = ["a", "b", "c", "d", "e", "f", "g", "h", "i"].iter().map(|s| (*s, 0, "x", 0xff000000)).collect();
        for (bad, why) in [
            (vec![], "no line"),
            (nine, "nine lines"),
            (vec![("out_of_range", 0, "x", 0xff000000)], "out_of_range has the failed line"),
            (vec![("level_required", 0, "x", 0xff000000), ("level_required", 2, "y", 0xff000000)], "a status twice"),
            (vec![("level_required", 3, "x", 0xff000000)], "a fourth target kind"),
            (vec![("Level", 0, "x", 0xff000000)], "an upper-case status"),
            (vec![("_level", 0, "x", 0xff000000)], "a status that starts with _"),
            (vec![("", 0, "x", 0xff000000)], "an empty status"),
            (vec![(&*"a".repeat(33), 0, "x", 0xff000000)], "a status of 33 bytes"),
            (vec![("level_required", 0, "", 0xff000000)], "an empty text"),
            (vec![("level_required", 0, "%d", 0xff000000)], "a %d"),
            (vec![("level_required", 0, "caf\u{e9}", 0xff000000)], "a non-ASCII text"),
            (vec![("level_required", 0, "x", 0x00ffffff)], "a transparent colour"),
        ] {
            assert!(lines(&bad, None).is_err(), "{why}");
        }
        assert!(lines(&good, Some(5)).is_err(), "a count past the lines");
        assert!(raw(b"N3K5", 2., 15., 1, &tail).is_err(), "N3K5 needs its lines");
        let mut five = tail.clone();
        five.extend(1u32.to_le_bytes());
        five.extend(string("level_required"));
        five.extend(0u32.to_le_bytes());
        five.extend(string("Casting failed"));
        five.extend(0xffff3b3bu32.to_le_bytes());
        assert!(raw(b"N3K4", 2., 15., 1, &five).is_err(), "N3K4 has no refusal lines");
        assert!(raw(b"N3K5", 2., 15., 1, &five).is_ok());
        std::fs::remove_dir_all(&dir).unwrap();
    }
    struct Roll(u32);
    impl crate::damage::Rolls for Roll {
        fn roll(&mut self, bound: u32) -> u32 {
            assert!(self.0 < bound);
            self.0
        }
    }
    #[test]
    fn player_binary_damage() {
        let mut s = sample(); // 29*(150+20)/186=26; 26*230/250=23; floor(.85*23)=19
        assert_eq!(s.damage(&[0, 0, 0, 0, 150], &mut Roll(0)), 19);
        assert_eq!(s.damage(&[0, 0, 0, 0, 150], &mut Roll(23)), 25);
        s.resistance = 200;
        assert_eq!(s.damage(&[0, 0, 0, 0, 150], &mut Roll(0)), 11);
        // No numeric wrap in the accepted content/stat domain.
        s.amount = 5000;
        s.resistance = 0;
        assert!(s.damage(&[0, 0, 0, 0, u32::MAX], &mut Roll(0)) < 32768);
    }
    #[test]
    #[ignore = "tests/skills_db.py supplies disposable PostgreSQL"]
    fn durable_authority() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let mut c = persistence::connect(&url)?;
        let realm = format!("skill-test-{}", std::process::id());
        let owner = Arc::new(Owner {
            generation: persistence::acquire(&mut c, &realm, "skill-audit")?,
            realm: realm.clone(),
            owner: "skill-audit".into(),
        });
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let id:i64=c.query_one("INSERT INTO characters(account_id,realm,name,online,session_generation,realm_generation) VALUES($1,$2,'Skill',true,1,$3) RETURNING id",&[&account,&realm,&owner.generation])?.get(0);
        let selected = Selected {
            id,
            generation: 1,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            entity: wire::Entity::default(),
        };
        let rt = tokio::runtime::Runtime::new()?;
        let db = Database::start(url.clone(), Default::default())?;
        let skill = sample();
        rt.block_on(async {
            assert_eq!(
                gate(
                    db.clone(),
                    owner.clone(),
                    selected.clone(),
                    skill.clone(),
                    false
                )
                .await?,
                Gate { remaining: 0, stamp: None }
            );
            let (a, b) = tokio::join!(
                gate(
                    db.clone(),
                    owner.clone(),
                    selected.clone(),
                    skill.clone(),
                    true
                ),
                gate(
                    Database::start(url.clone(), Default::default())?,
                    owner.clone(),
                    selected.clone(),
                    skill.clone(),
                    true
                )
            );
            let (a, b) = (a?, b?);
            // One commit wins and names its deadline; the other reads it and
            // writes nothing.
            assert!(
                (a.remaining == 0 && a.stamp.is_some() && b.remaining > 0 && b.stamp.is_none())
                    || (b.remaining == 0 && b.stamp.is_some() && a.remaining > 0 && a.stamp.is_none()),
                "{a:?} {b:?}"
            );
            let won = a.stamp.or(b.stamp).unwrap();
            let recovered = recover(
                Database::start(url.clone(), Default::default())?,
                owner.clone(),
                selected.clone(),
            )
            .await?;
            assert_eq!(recovered.len(), 1);
            assert_eq!(recovered[0].0, skill.id);
            assert!(recovered[0].1 > 0 && recovered[0].1 <= 108);
            // PQ-472 (D-236): an undo is fenced like the gate: a stale session
            // fails it and the deadline stays.
            let mut stale = selected.clone();
            stale.generation += 1;
            assert!(recover_undoing(db.clone(), owner.clone(), stale, skill.id.clone(), won).await.is_err());
            // An undo naming another deadline deletes nothing: the row a
            // later write left stays.
            let recovered = recover_undoing(db.clone(), owner.clone(), selected.clone(), skill.id.clone(), won - 1).await?;
            assert!(recovered.iter().any(|(id, ticks)| id == &skill.id && *ticks > 0), "{recovered:?}");
            // The commit's own stamp deletes its row, in the same transaction
            // as the recovery: the gate reads the skill ready again.
            let recovered = recover_undoing(db.clone(), owner.clone(), selected.clone(), skill.id.clone(), won).await?;
            assert!(!recovered.iter().any(|(id, _)| id == &skill.id), "{recovered:?}");
            assert_eq!(gate(db.clone(), owner.clone(), selected.clone(), skill.clone(), false).await?.remaining, 0);
            let again = gate(db.clone(), owner.clone(), selected.clone(), skill.clone(), true).await?;
            assert!(again.remaining == 0 && again.stamp.is_some_and(|s| s != won), "{again:?}");
            println!("PASS recast undo: fenced by the session, only the commit's own deadline deleted, the skill ready again (PQ-472)");
            // PQ-115: at a 25 ms test tick the 5400 ms cooldown (108 ticks) is
            // 2700 ms of wall time and still reads back as 108 ticks at that tick;
            // read at 50 ms the same deadline is 54 ticks, so both conversions
            // use the tick the deadline was written with.
            let mut scaled = skill.clone();
            scaled.id = "demo:skill/scaled".into();
            assert_eq!(gate_at(db.clone(), owner.clone(), selected.clone(), scaled.clone(), true, 25).await?.remaining, 0);
            let at25 = gate_at(db.clone(), owner.clone(), selected.clone(), scaled.clone(), false, 25).await?.remaining;
            let at50 = gate_at(db.clone(), owner.clone(), selected.clone(), scaled.clone(), false, 50).await?.remaining;
            assert!((100..=108).contains(&at25) && (50..=54).contains(&at50), "{at25} {at50}");
            let recovered = recover_at(Database::start(url.clone(), Default::default())?, owner.clone(), selected.clone(), None, 25).await?;
            assert!(recovered.iter().any(|(id, ticks)| id == &scaled.id && (100..=108).contains(ticks)), "{recovered:?}");
            let wall: f64 = db.call({let id = selected.id; move |c| Ok(c.query_one("SELECT extract(epoch FROM (ready_at-clock_timestamp()))::float8 FROM character_skill_cooldowns WHERE character_id=$1 AND skill='demo:skill/scaled'", &[&id])?.get(0))}).await?;
            assert!(wall > 2.3 && wall <= 2.7, "{wall}");
            let mut stale = selected.clone();
            stale.generation += 1;
            assert!(gate(db.clone(), owner.clone(), stale, skill.clone(), false)
                .await
                .is_err());
            let mut stale = selected.clone();
            stale.life_revision += 1;
            assert!(gate(db.clone(), owner.clone(), stale, skill.clone(), false)
                .await
                .is_err());
            Ok::<_, Box<dyn std::error::Error + Send + Sync>>(())
        })?;
        crate::skill_runtime::test_cancelled_commit(&rt,&db,&owner,&selected,&skill)?;
        c.execute(
            "UPDATE characters SET dead=true,respawn_ready_at=clock_timestamp() WHERE id=$1",
            &[&id],
        )?;
        assert!(rt
            .block_on(gate(
                db.clone(),
                owner.clone(),
                selected.clone(),
                skill.clone(),
                false
            ))
            .is_err());
        c.execute(
            "UPDATE characters SET dead=false,respawn_ready_at=NULL WHERE id=$1",
            &[&id],
        )?;
        c.execute("UPDATE realm_ownership SET expires=clock_timestamp()-interval '1 second' WHERE realm=$1",&[&realm])?;
        assert!(rt
            .block_on(gate(db, owner, selected, skill, false))
            .is_err());
        Ok(())
    }
}
