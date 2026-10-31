//! Frozen party award arithmetic. Binary provenance and corrections: content/party-rewards.md.
use crate::content::{Reader, Result, bad};
use crate::progression::Recipient;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq)]
pub struct Group {
    pub id: u64,
    pub leader_level: u32,
    pub members: Vec<i64>,
    // Positive contributors whose identity and distance were valid at death.
    // This differs from recipient life/zone eligibility, as in the binary helpers.
    pub credited: Vec<i64>,
}

pub fn calculate(
    p: &crate::progression::Policy,
    rows: &[Recipient],
    groups: &[Group],
) -> Result<Vec<u64>> {
    let policy = p
        .party_rewards
        .as_ref()
        .ok_or_else(|| bad("missing party reward policy"))?;
    if groups.len() > 64 || groups.windows(2).any(|g| g[0].id >= g[1].id) {
        return Err(bad("party snapshot order/count"));
    }
    let total: u64 = rows.iter().map(|r| r.credit).sum();
    if total == 0 || total > crate::progression::CREDIT_LIMIT || rows.iter().filter(|r| r.credit > 0).count() > 64 {
        return Err(bad("party contribution total/count"));
    }
    let indices: BTreeMap<_, _> = rows.iter().enumerate().map(|(i, r)| (r.id, i)).collect();
    let mut assigned = BTreeSet::new();
    let mut xp = vec![0; rows.len()];
    for g in groups {
        if g.id == 0
            || g.id > i64::MAX as u64
            || !(1..=10).contains(&g.leader_level)
            || g.members.is_empty()
            || g.members.len() > 8
            || g.credited.len() > 8
            || g.members.windows(2).any(|v| v[0] >= v[1])
            || g.credited.windows(2).any(|v| v[0] >= v[1])
            || g.members
                .iter()
                .any(|id| !indices.contains_key(id) || !assigned.insert(*id))
            || g.credited
                .iter()
                .any(|id| !g.members.contains(id) || rows[indices[id]].credit == 0)
            || !g.members.iter().any(|id| rows[indices[id]].credit > 0)
        {
            return Err(bad("party snapshot members/credit"));
        }
        let credit: u64 = g.credited.iter().map(|id| rows[indices[id]].credit).sum();
        let eligible: Vec<_> = g
            .members
            .iter()
            .map(|id| indices[id])
            .filter(|&i| rows[i].reason == 0)
            .collect();
        let levels: Vec<_> = eligible.iter().map(|&i| rows[i].level).collect();
        for (i, award) in eligible.into_iter().zip(policy.awards(
            p.base_xp,
            p.npc_level,
            credit,
            total,
            g.leader_level,
            &levels,
        )?) {
            xp[i] = award;
        }
    }
    for (i, r) in rows
        .iter()
        .enumerate()
        .filter(|(_, r)| !assigned.contains(&r.id))
    {
        if r.credit == 0 {
            return Err(bad("unaffiliated zero contributor"));
        }
        if r.reason == 0 {
            xp[i] = solo(
                ((r.credit as f64 / total as f64) * p.base_xp as f64).ceil(),
                p.npc_level,
                r.level,
            );
        }
    }
    Ok(xp)
}

#[derive(Clone, Debug)]
pub struct Policy {
    pub bonus_tenths: u32,
    pub minimum: f64,
    pub maximum: f64,
    pub gap: u32,
    pub level_xp: [u32; 10],
}
impl Policy {
    pub fn read(r: &mut Reader) -> Result<Self> {
        let mut p = Self {
            bonus_tenths: r.u()?,
            minimum: f64::from_le_bytes(r.take(8)?.try_into()?),
            maximum: f64::from_le_bytes(r.take(8)?.try_into()?),
            gap: r.u()?,
            level_xp: [0; 10],
        };
        for v in &mut p.level_xp {
            *v = r.u()?;
        }
        Ok(p)
    }
    pub fn validate(&self, thresholds: &[u64; 10]) -> Result<()> {
        if self.bonus_tenths > 8
            || !self.minimum.is_finite()
            || !self.maximum.is_finite()
            || !(0.0..=1.0).contains(&self.minimum)
            || !(1.0..=10.0).contains(&self.maximum)
            || self.gap > 100
            || self.level_xp.iter().any(|&v| v == 0 || v > i32::MAX as u32)
            || thresholds
                .windows(2)
                .zip(self.level_xp)
                .any(|(w, v)| w[1] - w[0] != v as u64)
        {
            return Err(bad("party reward policy"));
        }
        Ok(())
    }
    pub fn qualified(&self, leader: u32, member: u32) -> bool {
        leader.abs_diff(member) <= self.gap
            || (member as f64 >= leader as f64 * self.minimum
                && member as f64 <= leader as f64 * self.maximum)
    }
    pub fn awards(
        &self,
        base_xp: u32,
        npc_level: u32,
        credit: u64,
        total: u64,
        leader: u32,
        levels: &[u32],
    ) -> Result<Vec<u64>> {
        if total == 0
            || total > crate::progression::CREDIT_LIMIT
            || credit > total
            // PQ-252: a template's base XP (the row's iExp) may pass the
            // definition's 1,000,000.
            || base_xp > crate::progression::TEMPLATE_XP_LIMIT
            || !(1..=10).contains(&leader)
            || levels.len() > 8
            || levels.iter().any(|l| !(1..=10).contains(l))
            // A template's level (PQ-251) may pass the members' 1-10.
            || !(1..=255).contains(&npc_level)
        {
            return Err(bad("party award inputs"));
        }
        if levels.is_empty() {
            return Ok(Vec::new());
        }
        let share = ((credit as f64 / total as f64) * base_xp as f64).ceil();
        if levels.len() == 1 {
            return Ok(vec![solo(share, npc_level, levels[0])]);
        }
        // The binary uses absolute NPC level here, unlike its solo difference rule.
        let base = match npc_level {
            0..=1 => share,
            2..=4 => (share * 1.2).ceil(),
            5..=7 => (share * 1.5).ceil(),
            _ => share * 2.0,
        };
        let qualified = levels
            .iter()
            .filter(|&&l| self.qualified(leader, l))
            .count();
        let bonus = self.bonus_tenths as f64 * 0.1;
        let multiplier = if qualified < 2 {
            1.0
        } else {
            1.0 + (qualified - 1) as f64 * bonus
        };
        let sum: u32 = levels.iter().sum();
        Ok(levels
            .iter()
            .map(|&level| {
                let weighted = (multiplier * base * level as f64 / sum as f64).ceil() as u64;
                weighted.min(self.level_xp[level as usize - 1] as u64 / 10)
            })
            .collect())
    }
}

pub fn solo(share: f64, npc: u32, level: u32) -> u64 {
    match npc as i32 - level as i32 {
        d if d < 2 => share as u64,
        2..=4 => (share * 1.2).ceil() as u64,
        5..=7 => (share * 1.5).ceil() as u64,
        _ => (share * 1.8) as u64,
    }
}

/// Binary vector subtraction stores f32 components before double products/sqrt.
pub fn in_range(a: [f32; 3], b: [f32; 3], radius: f32) -> bool {
    let d = [a[0] - b[0], a[1] - b[1], a[2] - b[2]].map(f64::from);
    let distance = ((d[0] * d[0] + d[1] * d[1]) + d[2] * d[2]).sqrt();
    distance.is_finite() && distance.trunc() <= radius as f64
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{accounts::Owner, persistence, progression, settlements};
    fn policy() -> Policy {
        Policy {
            bonus_tenths: 8,
            minimum: 2.0 / 3.0,
            maximum: 1.5,
            gap: 8,
            level_xp: [100_000; 10],
        }
    }
    #[test]
    fn weighted_bonus_absolute_npc_level_and_single_member_fallback() -> Result<()> {
        let mut p = policy();
        // 100 base, NPC5 ->150; qualified leader1/member1, member10 unqualified.
        // Qualified bonus1.8 gives270 split1:1:10, each independently rounded up.
        assert_eq!(
            p.awards(100, 5, 100, 100, 1, &[1, 1, 10])?,
            vec![23, 23, 225]
        );
        assert_eq!(
            p.awards(100, 5, 100, 100, 1, &[10, 1, 1])?,
            vec![225, 23, 23]
        );
        // Only one eligible member takes the SOLO level-difference rule and no cap.
        p.level_xp = [10; 10];
        assert_eq!(p.awards(100, 5, 100, 100, 1, &[1])?, vec![120]);
        assert_eq!(p.awards(100, 5, 100, 100, 1, &[1, 1])?, vec![1, 1]);
        p = policy();
        p.bonus_tenths = 0;
        assert_eq!(
            p.awards(100, 5, 100, 100, 1, &[1, 1, 10])?,
            vec![13, 13, 125]
        );
        assert_eq!(p.awards(100, 1, 100, 100, 1, &[1, 1])?, vec![50, 50]);
        assert_eq!(p.awards(100, 2, 100, 100, 1, &[1, 1])?, vec![60, 60]);
        assert_eq!(p.awards(100, 8, 100, 100, 1, &[1, 1])?, vec![100, 100]);
        assert_eq!(p.awards(100, 8, 0, 100, 1, &[1, 1])?, vec![0, 0]);
        // 7/100 rounds to a double whose product with100 is just above7.
        // The observed divide-then-multiply order therefore awards8, not exact rational7.
        assert_eq!(p.awards(100, 1, 7, 100, 1, &[1])?, vec![8]);
        assert_eq!(p.awards(100, 1, 14, 100, 1, &[1])?, vec![15]);
        assert!(p.awards(100, 8, 101, 100, 1, &[1, 1]).is_err());
        assert!(p.awards(100, 8, 1, 0, 1, &[1, 1]).is_err());
        // PQ-251: a reference template's level (22-110 in KO's homelands, at
        // most 255) takes the top band in both rules; 0 and 256 are refused.
        assert_eq!(p.awards(100, 110, 100, 100, 1, &[1, 1])?, vec![100, 100]);
        assert_eq!(p.awards(100, 255, 100, 100, 1, &[1])?, vec![180]);
        assert!(p.awards(100, 0, 100, 100, 1, &[1, 1]).is_err());
        assert!(p.awards(100, 256, 100, 100, 1, &[1, 1]).is_err());
        Ok(())
    }
    #[test]
    fn truncated_distance_boundary_and_nonfinite_rejection() {
        assert!(in_range([50.999, 0., 0.], [0.; 3], 50.));
        assert!(!in_range([51., 0., 0.], [0.; 3], 50.));
        assert!(in_range([30., 40., 0.], [0.; 3], 50.));
        assert!(!in_range([30., 40., 11.], [0.; 3], 50.));
        assert!(!in_range([f32::NAN, 0., 0.], [0.; 3], 50.));
    }
    fn package() -> progression::Policy {
        progression::Policy::load(
            &std::path::PathBuf::from(std::env::var("N3E_PACKAGE").unwrap())
                .join("progression.bin"),
        )
        .unwrap()
    }
    fn frozen(
        o: &Owner,
        p: &progression::Policy,
        ids: &[i64],
        encounter: u64,
        claim: u64,
    ) -> progression::Settlement {
        let mut ledger = progression::Ledger::default();
        ledger.credit(ids[0], 60, 100).unwrap();
        ledger.credit(ids[2], 40, 40).unwrap();
        let (recipients, parties) = ledger
            .freeze_parties(
                p,
                "demo",
                [0.; 3],
                |id| {
                    if id == ids[2] {
                        None
                    } else {
                        Some(progression::Presence {
                            alive: true,
                            zone: "demo".into(),
                            position: [0.; 3],
                            level: 1,
                        })
                    }
                },
                |id| {
                    if id == ids[0] {
                        Some(Group {
                            id: 19,
                            leader_level: 1,
                            members: ids[..2].to_vec(),
                            credited: vec![],
                        })
                    } else {
                        None
                    }
                },
            )
            .unwrap();
        progression::Settlement {
            npc: None,
            items: None, coins: None,
            loot_order: None,
            parties,
            encounter,
            generation: o.generation,
            release: vec![3; 32],
            definition: p.hash.clone(),
            zone: "demo".into(),
            position: [0.; 3],
            tick: 10,
            claim,
            recipients,
        }
    }
    #[test]
    #[ignore = "child process of durable_contract"]
    fn fault_worker() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        let mut c = persistence::connect(&url)?;
        let realm = std::env::var("N3E_PARTY_REALM")?;
        let row = c.query_one(
            "SELECT owner,generation FROM realm_ownership WHERE realm=$1",
            &[&realm],
        )?;
        let o = Owner {
            realm: realm.clone(),
            owner: row.get(0),
            generation: row.get(1),
        };
        let ids = c
            .query(
                "SELECT id FROM characters WHERE realm=$1 ORDER BY id",
                &[&realm],
            )?
            .iter()
            .map(|r| r.get(0))
            .collect::<Vec<i64>>();
        let p = package();
        let s = frozen(
            &o,
            &p,
            &ids,
            std::env::var("N3E_PARTY_ENCOUNTER")?.parse()?,
            std::env::var("N3E_PARTY_CLAIM")?.parse()?,
        );
        settlements::settle(&mut c, &o, &p, &s)?;
        Ok(())
    }
    #[test]
    #[ignore = "tests/party_rewards_db.py supplies isolated PostgreSQL"]
    fn durable_contract() -> Result<()> {
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let mut c = persistence::connect(&url)?;
        let realm = format!("test-party-rewards-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "test")?;
        let o = Owner {
            realm: realm.clone(),
            owner: "test".into(),
            generation,
        };
        let p = package();
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let mut ids = Vec::new();
        for name in ["Leader", "Member", "Absent"] {
            ids.push(
                c.query_one(
                    "INSERT INTO characters(account_id,realm,name) VALUES($1,$2,$3) RETURNING id",
                    &[&account, &realm, &name],
                )?
                .get::<_, i64>(0),
            );
        }
        settlements::convert(&mut c, &o, &p, "demo", 20)?;
        settlements::check_start(&mut c, &realm, Some(&p))?;
        let mut downgraded = p.clone();
        downgraded.party_rewards = None;
        assert!(settlements::check_start(&mut c, &realm, Some(&downgraded)).is_err());
        assert!(settlements::convert(&mut c, &o, &downgraded, "demo", 20).is_err());
        let next = |c: &mut postgres::Client| {
            c.query_one("SELECT nextval('entity_instances')", &[])
                .unwrap()
                .get::<_, i64>(0) as u64
        };
        let s = frozen(&o, &p, &ids, next(&mut c), next(&mut c));
        assert_eq!(
            s.recipients.iter().map(|r| r.xp).collect::<Vec<_>>(),
            vec![20, 20, 0]
        );
        let mut threads = Vec::new();
        for _ in 0..4 {
            let (url, o, p, s) = (url.clone(), o.clone(), p.clone(), s.clone());
            threads.push(std::thread::spawn(move || {
                settlements::settle(&mut persistence::connect(&url).unwrap(), &o, &p, &s).unwrap()
            }));
        }
        let result = threads.remove(0).join().unwrap();
        for t in threads {
            assert_eq!(t.join().unwrap(), result);
        }
        let progress = |c: &mut postgres::Client| {
            c.query("SELECT p.xp,r.revision FROM character_progress p JOIN character_reward_progress r USING(character_id) WHERE r.realm=$1 ORDER BY p.character_id",&[&realm]).unwrap().iter().map(|r|(r.get::<_,i64>(0),r.get::<_,i64>(1))).collect::<Vec<_>>()
        };
        assert_eq!(progress(&mut c), vec![(20, 1), (20, 1), (0, 0)]);
        let mut changed = s.clone();
        changed.parties.as_mut().unwrap()[0].id += 1;
        assert!(settlements::settle(&mut c, &o, &p, &changed).is_err());
        assert!(
            c.execute(
                "UPDATE encounter_recipients SET awarded_xp=0 WHERE realm=$1",
                &[&realm]
            )
            .is_err()
        );
        // Force failure after the first recipient mutation: the entire transaction rolls back.
        c.batch_execute("CREATE FUNCTION reject_second_party_recipient() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.credit=0 THEN RAISE EXCEPTION 'injected recipient failure'; END IF; RETURN NEW; END $$; CREATE TRIGGER reject_second_party_recipient BEFORE INSERT ON encounter_recipients FOR EACH ROW EXECUTE FUNCTION reject_second_party_recipient();")?;
        let rejected = frozen(&o, &p, &ids, next(&mut c), next(&mut c));
        assert!(settlements::settle(&mut c, &o, &p, &rejected).is_err());
        assert_eq!(progress(&mut c), vec![(20, 1), (20, 1), (0, 0)]);
        c.batch_execute("DROP TRIGGER reject_second_party_recipient ON encounter_recipients; DROP FUNCTION reject_second_party_recipient();")?;
        for (index, point) in ["before_commit", "after_commit"].iter().enumerate() {
            let event = frozen(&o, &p, &ids, next(&mut c), next(&mut c));
            let output = std::process::Command::new(std::env::current_exe()?)
                .args([
                    "party_rewards::tests::fault_worker",
                    "--ignored",
                    "--exact",
                    "--nocapture",
                ])
                .env("N3E_PARTY_REALM", &realm)
                .env("N3E_PARTY_ENCOUNTER", event.encounter.to_string())
                .env("N3E_PARTY_CLAIM", event.claim.to_string())
                .env("N3E_SETTLEMENT_FAULT", point)
                .output()?;
            assert_eq!(
                output.status.code(),
                Some(86),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            let count: i64 = c
                .query_one(
                    "SELECT count(*) FROM encounter_settlements WHERE realm=$1 AND encounter=$2",
                    &[&realm, &(event.encounter as i64)],
                )?
                .get(0);
            assert_eq!(count, if index == 0 { 0 } else { 1 });
            let committed = settlements::settle(&mut c, &o, &p, &event)?;
            assert_eq!(settlements::settle(&mut c, &o, &p, &event)?, committed);
            let total = 40 + index as i64 * 20;
            assert_eq!(
                progress(&mut c),
                vec![(total, 2 + index as i64), (total, 2 + index as i64), (0, 0)]
            );
        }
        let stale = frozen(&o, &p, &ids, next(&mut c), next(&mut c));
        c.execute(
            "UPDATE realm_ownership SET generation=generation+1 WHERE realm=$1",
            &[&realm],
        )?;
        assert!(settlements::settle(&mut c, &o, &p, &stale).is_err());
        println!(
            "PASS grouped XP zero-credit recipient, atomic rollback, concurrent immutable retries, policy/realm fences and before/after-COMMIT process crashes"
        );
        Ok(())
    }
}
