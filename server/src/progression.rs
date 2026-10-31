//! Contribution policy and frozen settlement arithmetic. No I/O or session authority.
use crate::content::{Reader, Result, bad};
use std::{collections::BTreeMap, path::Path};

#[derive(Clone, Debug)]
pub struct Policy {
    pub items: Option<crate::item_drops::Policy>,
    pub coins: Option<crate::drop_generation::Policy>,
    pub party_loot: Option<crate::party_loot::Policy>,
    pub party_rewards: Option<crate::party_rewards::Policy>,
    pub equipment_stats: bool,
    pub curve: String,
    pub item: String,
    pub author: String,
    pub revision: u32,
    pub thresholds: [u64; 10],
    pub capacity: u32,
    pub starting: u32,
    pub npc_level: u32,
    pub base_xp: u32,
    pub radius: f32,
    pub claim_radius: f32,
    pub ttl: u32,
    pub hash: Vec<u8>,
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        Self::decode(Reader::open_bounded(path, 16384)?.bytes)
    }
    pub fn decode(bytes: Vec<u8>) -> Result<Self> {
        if bytes.len() > 16384 {
            return Err(bad("progression byte bound"));
        }
        let mut r = Reader::from_bytes(bytes);
        let hash = openssl::sha::sha256(&r.bytes).to_vec();
        let magic = r.take(4)?.to_vec();
        if (magic != b"N3P1" && magic != b"N3P2" && magic != b"N3P3" && magic != b"N3P4" && magic != b"N3P5")
            || r.u()? != 1
        {
            return Err(bad("progression policy/fixed stats"));
        }
        let mode = r.u()?;
        if !(1..=2).contains(&mode) {
            return Err(bad("stat policy"));
        }
        let curve = r.string()?;
        let item = r.string()?;
        if r.string()? != "original synthetic" {
            return Err(bad("progression origin"));
        }
        let author = r.string()?;
        let revision = r.u()?;
        let mut thresholds = [0; 10];
        for x in &mut thresholds {
            *x = u64::from_le_bytes(r.take(8)?.try_into()?);
        }
        let mut p = Self {
            items: None, coins: None,
            party_loot: None,
            party_rewards: None,
            equipment_stats: mode == 2,
            curve,
            item,
            author,
            revision,
            thresholds,
            capacity: r.u()?,
            starting: r.u()?,
            npc_level: r.u()?,
            base_xp: r.u()?,
            radius: r.f()?,
            claim_radius: r.f()?,
            ttl: r.u()?,
            hash,
        };
        if magic == b"N3P2" || magic == b"N3P3" || magic == b"N3P4" || magic == b"N3P5" {
            p.party_rewards = Some(crate::party_rewards::Policy::read(&mut r)?);
        }
        if magic == b"N3P3" || magic == b"N3P4" || magic == b"N3P5" {
            p.party_loot = Some(crate::party_loot::Policy { radius: r.u()? });
        }
        if magic == b"N3P4" || magic == b"N3P5" {
            p.coins = Some(crate::drop_generation::Policy::read(&mut r)?);
        }
        if magic == b"N3P5" { p.items=Some(crate::item_drops::Policy::read(&mut r)?); }
        r.end()?;
        p.validate()?;
        Ok(p)
    }
    pub fn encode(&self) -> Result<Vec<u8>> {
        self.validate()?;
        let mut b = if self.items.is_some() { b"N3P5" } else if self.coins.is_some() {
            b"N3P4"
        } else if self.party_loot.is_some() {
            b"N3P3"
        } else if self.party_rewards.is_some() {
            b"N3P2"
        } else {
            b"N3P1"
        }
        .to_vec();
        b.extend(1u32.to_le_bytes());
        b.extend((if self.equipment_stats { 2u32 } else { 1 }).to_le_bytes());
        for v in [&self.curve, &self.item, "original synthetic", &self.author] {
            b.extend((v.len() as u32).to_le_bytes());
            b.extend(v.as_bytes());
        }
        b.extend(self.revision.to_le_bytes());
        for v in self.thresholds {
            b.extend(v.to_le_bytes());
        }
        for v in [self.capacity, self.starting, self.npc_level, self.base_xp] {
            b.extend(v.to_le_bytes());
        }
        for v in [self.radius, self.claim_radius] {
            b.extend(v.to_le_bytes());
        }
        b.extend(self.ttl.to_le_bytes());
        if let Some(p) = &self.party_rewards {
            b.extend(p.bonus_tenths.to_le_bytes());
            b.extend(p.minimum.to_le_bytes());
            b.extend(p.maximum.to_le_bytes());
            b.extend(p.gap.to_le_bytes());
            for v in p.level_xp {
                b.extend(v.to_le_bytes());
            }
        }
        if let Some(p) = &self.party_loot {
            b.extend(p.radius.to_le_bytes());
        }
        if let Some(p) = &self.coins {
            p.encode(&mut b);
        }
        if let Some(p)=&self.items {p.encode(&mut b);}
        if b.len() > 16384 || openssl::sha::sha256(&b).as_slice() != self.hash {
            return Err(bad("reward definition bytes/hash mismatch"));
        }
        Ok(b)
    }
    pub fn validate(&self) -> Result<()> {
        if let Some(p)=&self.items {p.validate()?;if self.coins.is_none(){return Err(bad("item drops require currency-capable bundles"));}}
        if let Some(p) = &self.coins {
            p.validate()?;
            if self.party_loot.is_none() {
                return Err(bad("coin drops require party loot"));
            }
        }
        if let Some(p) = &self.party_loot {
            p.validate()?;
            if self.party_rewards.is_none() {
                return Err(bad("party loot requires grouped rewards"));
            }
        }
        if self.thresholds[0] != 0
            || self.thresholds.windows(2).any(|w| w[0] >= w[1])
            || self.thresholds[9] > i64::MAX as u64
            || self.revision == 0
            || self.curve.len() > 128
            || self.item.len() > 128
            || self.author.is_empty()
            || !(1..=64).contains(&self.capacity)
            || self.starting > self.capacity
            || !(1..=10).contains(&self.npc_level)
            || !(1..=1_000_000).contains(&self.base_xp)
            || !(1.0..=100.).contains(&self.radius)
            || !(0.5..=10.).contains(&self.claim_radius)
            || !(10..=600).contains(&self.ttl)
            || self.hash.len() != 32
        {
            return Err(bad("progression bounds"));
        }
        if let Some(p) = &self.party_rewards {
            p.validate(&self.thresholds)?;
            if self.radius.fract() != 0.0 {
                return Err(bad("party reward integer radius"));
            }
        }
        Ok(())
    }
    pub fn mode(&self) -> &'static str {
        if self.items.is_some() {"contribution_items_v5"} else if self.coins.is_some() {
            "contribution_drops_v4"
        } else if self.party_loot.is_some() {
            "contribution_party_loot_v3"
        } else if self.party_rewards.is_some() {
            "contribution_party_v2"
        } else {
            "contribution_claim_v1"
        }
    }
    pub fn level(&self, xp: u64) -> u32 {
        self.thresholds.partition_point(|t| *t <= xp) as u32
    }
    pub fn convert(&self, xp: u64, divisor: u32) -> Result<(u64, u32, u64)> {
        if divisor == 0 || xp > i64::MAX as u64 {
            return Err(bad("legacy XP bounds"));
        }
        let q = 1 + xp / divisor as u64;
        let rem = xp % divisor as u64;
        if q > 10 {
            return Err(bad("unsupported legacy level"));
        }
        let base = self.thresholds[q as usize - 1];
        let fraction = if q == 10 {
            rem
        } else {
            // u128 avoids overflow while retaining exact integer fraction.
            ((rem as u128 * (self.thresholds[q as usize] - base) as u128) / divisor as u128) as u64
        };
        Ok((add(base, fraction)?, q as u32, rem))
    }
    pub fn award(&self, credit: u64, total: u64, level: u32) -> Result<u64> {
        if total == 0 || credit > total || !(1..=10).contains(&level) {
            return Err(bad("award bounds"));
        }
        let numerator = (self.base_xp as u64)
            .checked_mul(credit)
            .ok_or_else(|| bad("award overflow"))?;
        let share = numerator.div_ceil(total);
        let d = self.npc_level as i32 - level as i32;
        Ok(if d < 2 {
            share
        } else if d < 5 {
            (share * 6).div_ceil(5)
        } else if d < 8 {
            (share * 3).div_ceil(2)
        } else {
            share * 9 / 5
        })
    }
}
/// The most credit (damage dealt) one encounter records, per recipient and in
/// total (PQ-251, D-164). Template health reaches 2,000,000 and regeneration can
/// heal an NPC while it is fought, so it is fifty times that; `Ledger::credit`
/// stops counting there. Durable: `encounter_recipients.credit` (migration 022).
pub const CREDIT_LIMIT: u64 = 100_000_000;
/// The most base XP one NPC template carries (PQ-252, D-165). KO's iExp is a
/// four-byte int (AI binding `0041737b`) copied to the NPC's record `+0x3c`
/// (`0043893e`), which the kill reward `004209da` shares; the reference rows
/// reach 39,438,375, and 0 (a template that awards nothing) is allowed.
pub const TEMPLATE_XP_LIMIT: u32 = 50_000_000;
/// The most XP one solo settlement row carries: the base at most, times the
/// top level-difference factor 9/5 (`award`, `party_rewards::solo`).
pub const SOLO_XP_LIMIT: u64 = TEMPLATE_XP_LIMIT as u64 * 9 / 5;
/// The most XP one party settlement row carries: a grouped member's award
/// stops at its level's `level_xp` / 10 (AI `004438fa`), at most `i32::MAX`
/// / 10, and a single eligible member or an unaffiliated contributor takes
/// the solo rule. Durable: `encounter_recipients.awarded_xp` (migration 023).
pub const PARTY_XP_LIMIT: u64 = i32::MAX as u64 / 10;
/// One NPC template's kill reward (PQ-249): the level and base XP that replace
/// the definition's `npc_level` and `base_xp` for that NPC's encounter. KO reads
/// both from the NPC's own record (AI `0043893e` copies `sLevel` and `iExp`;
/// the kill reward `004209da` reads `iExp` there).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NpcReward {
    pub level: u32,
    pub xp: u32,
}
impl NpcReward {
    fn valid(&self) -> bool {
        // PQ-251: a template's level is the reference row's (1-255); PQ-252:
        // its XP the row's iExp (0-TEMPLATE_XP_LIMIT).
        (1..=255).contains(&self.level) && self.xp <= TEMPLATE_XP_LIMIT
    }
}
impl Policy {
    /// The definition as one NPC rewards it: its level and base XP replaced by
    /// the template's. The hash and every other rule stay the realm's, so the
    /// durable definition checks are unchanged.
    pub fn for_npc(&self, npc: Option<NpcReward>) -> std::borrow::Cow<'_, Self> {
        match npc {
            Some(t) => {
                let mut p = self.clone();
                p.npc_level = t.level;
                p.base_xp = t.xp;
                std::borrow::Cow::Owned(p)
            }
            None => std::borrow::Cow::Borrowed(self),
        }
    }
}
pub fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b)
        .filter(|x| *x <= i64::MAX as u64)
        .ok_or_else(|| bad("progression overflow"))
}
#[derive(Clone, Debug, Default)]
pub struct Ledger {
    credits: BTreeMap<i64, u64>,
    order: Vec<i64>,
    frozen: bool,
}
impl Ledger {
    pub fn admits(&self, id: i64) -> bool {
        !self.frozen && id > 0 && (self.credits.contains_key(&id) || self.credits.len() < 64)
    }
    pub fn credit(&mut self, id: i64, damage: u32, hp: u32) -> Result<()> {
        if damage == 0 || hp == 0 {
            return Ok(());
        }
        if !self.admits(id) {
            return Err(bad("contributor limit/frozen"));
        }
        // PQ-251: an encounter's credit never passes CREDIT_LIMIT, so a settlement
        // can always be written; past it further damage earns nothing.
        let total = self.credits.values().try_fold(0, |sum, v| add(sum, *v))?;
        let earned = (damage.min(hp) as u64).min(CREDIT_LIMIT.saturating_sub(total));
        if earned == 0 {
            return Ok(());
        }
        if !self.credits.contains_key(&id) {
            self.order.push(id);
        }
        let v = self.credits.entry(id).or_default();
        *v = add(*v, earned)?;
        Ok(())
    }
    pub fn admission(
        &self,
        id: i64,
        outstanding: usize,
        identities: usize,
    ) -> std::result::Result<(), &'static str> {
        if outstanding >= 64 || identities == 0 {
            return Err("settlement_capacity");
        }
        if !self.admits(id) {
            return Err("contributor_capacity");
        }
        Ok(())
    }
    pub fn order(&self) -> Vec<i64> {
        self.order.clone()
    }
    pub fn active(&self) -> bool {
        !self.credits.is_empty()
    }
    pub fn freeze_parties(
        &mut self,
        p: &Policy,
        zone: &str,
        position: [f32; 3],
        mut lookup: impl FnMut(i64) -> Option<Presence>,
        mut membership: impl FnMut(i64) -> Option<crate::party_rewards::Group>,
    ) -> Result<(Vec<Recipient>, Option<Vec<crate::party_rewards::Group>>)> {
        if p.party_rewards.is_none() {
            return Ok((self.freeze(p, zone, position, lookup)?, None));
        }
        if self.frozen {
            return Err(bad("encounter already frozen"));
        }
        let mut groups = BTreeMap::new();
        let mut ids: std::collections::BTreeSet<_> = self.credits.keys().copied().collect();
        for &id in self.credits.keys() {
            if let Some(mut g) = membership(id) {
                g.members.sort_unstable();
                g.credited.clear();
                ids.extend(&g.members);
                groups.entry(g.id).or_insert(g);
            }
        }
        if ids.len() > 512 || groups.len() > 64 {
            return Err(bad("party snapshot capacity"));
        }
        let grouped: std::collections::BTreeSet<_> = groups
            .values()
            .flat_map(|g| g.members.iter().copied())
            .collect();
        let mut valid_credit = std::collections::BTreeSet::new();
        let mut rows = Vec::new();
        for id in ids {
            let credit = *self.credits.get(&id).unwrap_or(&0);
            let (reason, level) = match lookup(id) {
                None => (1, 1),
                Some(v) => {
                    if !(1..=10).contains(&v.level) {
                        return Err(bad("snapshot level"));
                    }
                    let range = crate::party_rewards::in_range(v.position, position, p.radius);
                    if range && credit > 0 {
                        valid_credit.insert(id);
                    }
                    let reason = if grouped.contains(&id) && !v.alive {
                        2
                    } else if grouped.contains(&id) && v.zone != zone {
                        3
                    } else if !range {
                        4
                    } else {
                        0
                    };
                    (reason, v.level)
                }
            };
            rows.push(Recipient {
                id,
                credit,
                reason,
                level,
                xp: 0,
            });
        }
        let groups: Vec<_> = groups
            .into_values()
            .map(|mut g| {
                g.credited = g
                    .members
                    .iter()
                    .copied()
                    .filter(|id| valid_credit.contains(id))
                    .collect();
                g
            })
            .collect();
        let awards = crate::party_rewards::calculate(p, &rows, &groups)?;
        for (r, xp) in rows.iter_mut().zip(awards) {
            r.xp = xp;
        }
        self.frozen = true;
        Ok((rows, Some(groups)))
    }
    pub fn freeze(
        &mut self,
        p: &Policy,
        zone: &str,
        position: [f32; 3],
        mut lookup: impl FnMut(i64) -> Option<Presence>,
    ) -> Result<Vec<Recipient>> {
        if self.frozen {
            return Err(bad("encounter already frozen"));
        }
        let total = self.credits.values().try_fold(0, |sum, v| add(sum, *v))?;
        let mut out = Vec::new();
        for (&id, &credit) in &self.credits {
            let current = lookup(id);
            let (reason, level) = match current {
                None => (1, 1),
                Some(v) => {
                    if !(1..=10).contains(&v.level) {
                        return Err(bad("snapshot level"));
                    }
                    let dist = v
                        .position
                        .iter()
                        .zip(position)
                        .map(|(a, b)| (*a as f64 - b as f64).powi(2))
                        .sum::<f64>();
                    (
                        if !v.alive {
                            2
                        } else if v.zone != zone {
                            3
                        } else if !dist.is_finite() || dist > (p.radius as f64).powi(2) {
                            4
                        } else {
                            0
                        },
                        v.level,
                    )
                }
            };
            out.push(Recipient {
                id,
                credit,
                reason,
                level,
                xp: if reason == 0 {
                    p.award(credit, total, level)?
                } else {
                    0
                },
            });
        }
        self.frozen = true;
        Ok(out)
    }
}
pub struct Presence {
    pub alive: bool,
    pub zone: String,
    pub position: [f32; 3],
    pub level: u32,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Recipient {
    pub id: i64,
    pub credit: u64,
    pub reason: u32,
    pub level: u32,
    pub xp: u64,
}
#[derive(Clone, Debug)]
pub struct Settlement {
    pub items: Option<crate::item_drops::Outcome>,
    pub coins: Option<crate::drop_generation::Outcome>,
    pub loot_order: Option<Vec<i64>>,
    pub parties: Option<Vec<crate::party_rewards::Group>>,
    pub encounter: u64,
    pub generation: i64,
    pub release: Vec<u8>,
    pub definition: Vec<u8>,
    pub zone: String,
    pub position: [f32; 3],
    pub tick: u64,
    pub claim: u64,
    pub recipients: Vec<Recipient>,
    /// The killed NPC's template reward (PQ-249); None for a package without
    /// templates, whose payload bytes are unchanged.
    pub npc: Option<NpcReward>,
}
impl Settlement {
    pub fn owner(&self) -> Option<i64> {
        if let Some(order) = &self.loot_order {
            return crate::party_loot::settlement_owner(
                &self.recipients,
                self.parties.as_deref().unwrap_or(&[]),
                order,
            )
            .ok()
            .flatten();
        }
        self.recipients
            .iter()
            .filter(|r| r.reason == 0 && r.credit > 0)
            .min_by_key(|r| (std::cmp::Reverse(r.credit), r.id))
            .map(|r| r.id)
    }
    pub fn canonical(&self) -> Result<Vec<u8>> {
        if self.encounter == 0
            || self.encounter > i64::MAX as u64
            || self.claim == 0
            || self.claim > i64::MAX as u64
            || self.generation <= 0
            || self.tick > i64::MAX as u64
            || self.release.len() != 32
            || self.definition.len() != 32
            || self.zone.is_empty()
            || self.zone.len() > 128
            || self.recipients.len() > if self.parties.is_some() { 512 } else { 64 }
            || self
                .position
                .iter()
                .any(|f| !f.is_finite() || f.abs() > 1e6)
            || self.recipients.windows(2).any(|r| r[0].id >= r[1].id)
            || self.recipients.iter().any(|r| {
                r.id <= 0
                    || (r.credit == 0 && self.parties.is_none())
                    || r.credit > CREDIT_LIMIT
                    || r.reason > 4
                    || !(1..=10).contains(&r.level)
                    || r.xp
                        > if self.parties.is_some() {
                            PARTY_XP_LIMIT
                        } else {
                            SOLO_XP_LIMIT
                        }
                    || (r.reason != 0 && r.xp != 0)
            })
        {
            return Err(bad("settlement canonical bounds/order"));
        }
        if let Some(order) = &self.loot_order {
            if self.parties.is_none() {
                return Err(bad("loot requires party snapshot"));
            }
            crate::party_loot::settlement_owner(
                &self.recipients,
                self.parties.as_deref().unwrap(),
                order,
            )?;
        }
        let mut b = if self.items.is_some() { b"N3S6" } else if self.coins.is_some() {
            b"N3S5"
        } else if self.loot_order.is_some() {
            b"N3S4"
        } else if self.parties.is_some() {
            b"N3S3"
        } else {
            b"N3S2"
        }
        .to_vec();
        for v in [
            self.encounter,
            self.generation as u64,
            self.tick,
            self.claim,
        ] {
            b.extend(v.to_le_bytes());
        }
        b.extend(&self.release);
        b.extend(&self.definition);
        b.extend((self.zone.len() as u32).to_le_bytes());
        b.extend(self.zone.as_bytes());
        for v in self.position {
            b.extend(v.to_le_bytes());
        }
        b.push(self.owner().is_some() as u8);
        b.extend(self.owner().unwrap_or(0).to_le_bytes());
        b.extend((self.recipients.len() as u32).to_le_bytes());
        for r in &self.recipients {
            b.extend(r.id.to_le_bytes());
            b.extend(r.credit.to_le_bytes());
            b.extend(r.reason.to_le_bytes());
            b.extend(r.level.to_le_bytes());
            b.extend(r.xp.to_le_bytes());
        }
        if let Some(groups) = &self.parties {
            if groups.len() > 64 {
                return Err(bad("party snapshot count"));
            }
            b.extend((groups.len() as u32).to_le_bytes());
            for g in groups {
                if g.members.len() > 8 || g.credited.len() > 8 {
                    return Err(bad("party member count"));
                }
                b.extend(g.id.to_le_bytes());
                b.extend(g.leader_level.to_le_bytes());
                for ids in [&g.members, &g.credited] {
                    b.extend((ids.len() as u32).to_le_bytes());
                    for id in ids {
                        b.extend(id.to_le_bytes());
                    }
                }
            }
        }
        if let Some(order) = &self.loot_order {
            b.extend((order.len() as u32).to_le_bytes());
            for id in order {
                b.extend(id.to_le_bytes());
            }
        }
        if let Some(c) = &self.coins {
            if self.loot_order.is_none() || c.draw > 100 || c.amount > 32766 {
                return Err(bad("coin outcome bounds"));
            }
            b.extend(c.draw.to_le_bytes());
            b.extend(c.amount.to_le_bytes());
        }
        if let Some(i)=&self.items {if self.coins.is_none(){return Err(bad("item outcome version"));}i.encode(&mut b)?;}
        if let Some(t) = &self.npc {
            // A trailer only a templated encounter carries: every section before
            // it is fixed by the magic or length-prefixed, so payloads stay distinct.
            if !t.valid() {
                return Err(bad("settlement npc reward bounds"));
            }
            b.extend(b"N3T1");
            b.extend(t.level.to_le_bytes());
            b.extend(t.xp.to_le_bytes());
        }
        if b.len() > 32768 {
            return Err(bad("settlement payload size"));
        }
        Ok(b)
    }
    pub fn validate(&self, p: &Policy) -> Result<()> {
        self.canonical()?;
        // The template's level and XP replace the definition's (PQ-249).
        let effective = p.for_npc(self.npc);
        let p = &*effective;
        if self.items.is_some() != p.items.is_some() || self.coins.is_some() != p.coins.is_some()
            || self.parties.is_some() != p.party_rewards.is_some()
            || self.loot_order.is_some() != p.party_loot.is_some()
            || self.definition != p.hash
        {
            return Err(bad("settlement policy version"));
        }
        if let (Some(c), Some(policy)) = (&self.coins, &p.coins) {
            if policy
                .generation
                .amount(c.draw, crate::drop_generation::eligible(self))?
                != c.amount
            {
                return Err(bad("coin outcome mismatch"));
            }
        }
        if let (Some(outcome),Some(policy))=(&self.items,&p.items) {
            let level=self.owner().and_then(|id|self.recipients.iter().find(|r|r.id==id)).map_or(1,|r|r.level);
            if outcome.player_level!=level || outcome.premium || policy.replay(&outcome.rolls,p.npc_level,level,false,self.coins.as_ref().is_some_and(|c|c.amount>0))?!=outcome.entries {return Err(bad("item outcome mismatch"));}
        }
        if let Some(groups) = &self.parties {
            let xp = crate::party_rewards::calculate(p, &self.recipients, groups)?;
            if self.recipients.iter().zip(xp).any(|(r, x)| r.xp != x) {
                return Err(bad("party award mismatch"));
            }
            return Ok(());
        }
        let total = self
            .recipients
            .iter()
            .try_fold(0, |sum, r| add(sum, r.credit))?;
        if self.definition != p.hash
            || total > CREDIT_LIMIT
            || self
                .recipients
                .iter()
                .any(|r| r.reason == 0 && p.award(r.credit, total, r.level).ok() != Some(r.xp))
        {
            return Err(bad("settlement definition/award"));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn loot_order_is_frozen_and_changes_only_new_ownership() -> Result<()> {
        let mut ledger = Ledger::default();
        ledger.credit(9, 40, 100)?;
        ledger.credit(7, 20, 100)?;
        ledger.credit(3, 20, 100)?;
        ledger.credit(7, 1, 100)?;
        assert_eq!(ledger.order(), vec![9, 7, 3]);
        let mut p = policy();
        p.party_rewards = Some(crate::party_rewards::Policy {
            bonus_tenths: 0,
            minimum: 2.0 / 3.0,
            maximum: 1.5,
            gap: 8,
            level_xp: std::array::from_fn(|i| {
                if i < 9 {
                    (p.thresholds[i + 1] - p.thresholds[i]) as u32
                } else {
                    100
                }
            }),
        });
        p.party_loot = Some(crate::party_loot::Policy { radius: 50 });
        let (rows, groups) = ledger.freeze_parties(
            &p,
            "test",
            [0.; 3],
            |_| {
                Some(Presence {
                    alive: true,
                    zone: "test".into(),
                    position: [0.; 3],
                    level: 1,
                })
            },
            |id| {
                if id == 9 {
                    None
                } else {
                    Some(crate::party_rewards::Group {
                        id: 2,
                        leader_level: 1,
                        members: vec![3, 7],
                        credited: Vec::new(),
                    })
                }
            },
        )?;
        let mut s = Settlement {
            npc: None,
            items: None, coins: None,
            loot_order: Some(ledger.order()),
            parties: groups,
            encounter: 1,
            generation: 1,
            release: vec![1; 32],
            definition: p.hash.clone(),
            zone: "test".into(),
            position: [0.; 3],
            tick: 1,
            claim: 2,
            recipients: rows,
        };
        s.validate(&p)?;
        assert_eq!(s.owner(), Some(7));
        assert_eq!(&s.canonical()?[..4], b"N3S4");
        let bytes = s.canonical()?;
        s.loot_order.as_mut().unwrap().swap(1, 2);
        s.validate(&p)?;
        assert_eq!(s.owner(), Some(3));
        assert_ne!(s.canonical()?, bytes);
        s.loot_order = Some(vec![9, 7, 7]);
        assert!(s.validate(&p).is_err());
        Ok(())
    }
    fn policy() -> Policy {
        Policy {
            items: None, coins: None,
            party_loot: None,
            party_rewards: None,
            equipment_stats: false,
            curve: "test:curve".into(),
            item: "test:item".into(),
            author: "n3e".into(),
            revision: 1,
            thresholds: [0, 20, 50, 90, 140, 200, 270, 350, 440, 540],
            capacity: 2,
            starting: 0,
            npc_level: 1,
            base_xp: 10,
            radius: 50.,
            claim_radius: 3.,
            ttl: 120,
            hash: vec![1; 32],
        }
    }
    fn present() -> Presence {
        Presence {
            alive: true,
            zone: "zone".into(),
            position: [0.; 3],
            level: 1,
        }
    }
    #[test]
    fn party_members_share_frozen_credit_and_invalid_entries_never_inherit_identity() -> Result<()>
    {
        let mut p = policy();
        p.thresholds = [0, 200, 500, 900, 1400, 2000, 2700, 3500, 4400, 5400];
        p.base_xp = 100;
        p.npc_level = 5;
        p.party_rewards = Some(crate::party_rewards::Policy {
            bonus_tenths: 8,
            minimum: 2.0 / 3.0,
            maximum: 1.5,
            gap: 8,
            level_xp: [200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100],
        });
        p.validate()?;
        let group = crate::party_rewards::Group {
            id: 7,
            leader_level: 1,
            members: vec![1, 2, 3],
            credited: vec![],
        };
        let mut ledger = Ledger::default();
        ledger.credit(1, 40, 100)?;
        ledger.credit(4, 60, 60)?;
        let (rows, groups) = ledger.freeze_parties(
            &p,
            "zone",
            [0.; 3],
            |id| {
                if id == 4 { None } else { Some(present()) }
            },
            |id| if id == 1 { Some(group.clone()) } else { None },
        )?;
        assert_eq!(
            rows.iter()
                .map(|r| (r.id, r.credit, r.xp, r.reason))
                .collect::<Vec<_>>(),
            vec![(1, 40, 20, 0), (2, 0, 20, 0), (3, 0, 20, 0), (4, 60, 0, 1)]
        );
        assert!(!ledger.admits(1));
        let mut s = Settlement {
            npc: None,
            items: None, coins: None,
            loot_order: None,
            parties: groups,
            encounter: 1,
            generation: 1,
            release: vec![1; 32],
            definition: p.hash.clone(),
            zone: "zone".into(),
            position: [0.; 3],
            tick: 1,
            claim: 2,
            recipients: rows,
        };
        s.validate(&p)?;
        assert!(s.canonical()?.starts_with(b"N3S3"));
        assert_eq!(s.owner(), Some(1));
        let frozen = s.canonical()?;
        // A zero-credit party member is a real recipient, but cannot take the old exclusive entitlement.
        s.recipients[1].xp += 1;
        assert!(s.validate(&p).is_err());
        s.recipients[1].xp -= 1;
        s.parties.as_mut().unwrap()[0].credited.push(4);
        assert!(s.validate(&p).is_err());
        s.parties.as_mut().unwrap()[0].credited.pop();
        assert_eq!(s.canonical()?, frozen);
        s.parties = None;
        assert!(s.validate(&p).is_err());
        // Dead contributors' valid credit can support live members; dead members receive none.
        let mut ledger = Ledger::default();
        ledger.credit(1, 100, 100)?;
        let (rows, groups) = ledger.freeze_parties(
            &p,
            "zone",
            [0.; 3],
            |id| {
                let mut v = present();
                if id == 1 {
                    v.alive = false;
                }
                if id == 3 {
                    v.position = [51., 0., 0.];
                }
                Some(v)
            },
            |_| Some(group.clone()),
        )?;
        assert_eq!(
            rows.iter()
                .map(|r| (r.id, r.reason, r.xp))
                .collect::<Vec<_>>(),
            vec![(1, 2, 0), (2, 0, 120), (3, 4, 0)]
        );
        assert_eq!(groups.unwrap()[0].credited, vec![1]);
        // The separate solo binary helper checks identity/range, not party life/zone.
        let mut solo_ledger = Ledger::default();
        solo_ledger.credit(1, 100, 100)?;
        let (solo_rows, _) = solo_ledger.freeze_parties(
            &p,
            "zone",
            [0.; 3],
            |_| {
                let mut v = present();
                v.alive = false;
                v.zone = "other".into();
                v.position = [50.9, 0., 0.];
                Some(v)
            },
            |_| None,
        )?;
        assert_eq!((solo_rows[0].reason, solo_rows[0].xp), (0, 120));
        p.base_xp = 10;
        let mut ledger = Ledger::default();
        ledger.credit(1, 40, 100)?;
        ledger.credit(2, 60, 60)?;
        let (rows, groups) = ledger.freeze_parties(
            &p,
            "zone",
            [0.; 3],
            |id| if id == 2 { None } else { Some(present()) },
            |_| Some(group.clone()),
        )?;
        assert_eq!(rows.iter().map(|r| r.xp).collect::<Vec<_>>(), vec![6, 0, 6]);
        assert_eq!(groups.unwrap()[0].credited, vec![1]);
        // The maximum captured expansion stays within the durable payload bound.
        let mut forward = Ledger::default();
        let mut reverse = Ledger::default();
        for i in 0..64 {
            forward.credit(i * 8 + 1, 1, 100)?;
            reverse.credit((63 - i) * 8 + 1, 1, 100)?;
        }
        let capture = |id| {
            Some(crate::party_rewards::Group {
                id: id as u64,
                leader_level: 1,
                members: (id..id + 8).rev().collect(),
                credited: vec![],
            })
        };
        let (rows, groups) =
            forward.freeze_parties(&p, "zone", [0.; 3], |_| Some(present()), capture)?;
        let other = reverse.freeze_parties(&p, "zone", [0.; 3], |_| Some(present()), capture)?;
        assert_eq!(rows.len(), 512);
        assert_eq!((rows.clone(), groups.clone()), other);
        let maximum = Settlement {
            npc: None,
            items: None, coins: None,
            loot_order: None,
            parties: groups,
            recipients: rows,
            ..s
        };
        maximum.validate(&p)?;
        assert!(maximum.canonical()?.len() <= 32768);
        Ok(())
    }
    #[test]
    fn curve_conversion_and_multipliers() -> Result<()> {
        let mut p = policy();
        p.validate()?;
        for (xp, level) in [
            (19, 1),
            (20, 2),
            (49, 2),
            (50, 3),
            (539, 9),
            (540, 10),
            (550, 10),
        ] {
            assert_eq!(p.level(xp), level);
        }
        assert_eq!(p.convert(45, 20)?, (60, 3, 5));
        assert!(p.convert(200, 20).is_err());
        assert!(add(i64::MAX as u64, 1).is_err());
        p.base_xp = 3;
        for (d, xp) in [(1, 3), (2, 4), (4, 4), (5, 5), (7, 5), (8, 5)] {
            p.npc_level = 1 + d;
            assert_eq!(p.award(1, 1, 1)?, xp);
        }
        p.thresholds[2] = 20;
        assert!(p.validate().is_err());
        Ok(())
    }
    #[test]
    fn capped_ledger_eligibility_freeze_and_capacity() -> Result<()> {
        let p = policy();
        let mut ledger = Ledger::default();
        ledger.credit(1, 60, 100)?;
        ledger.credit(2, 100, 40)?;
        let rows = ledger.freeze(&p, "zone", [0.; 3], |_| Some(present()))?;
        assert_eq!(
            (rows[0].credit, rows[1].credit, rows[0].xp, rows[1].xp),
            (60, 40, 6, 4)
        );
        assert!(!ledger.admits(1));
        assert!(ledger.freeze(&p, "zone", [0.; 3], |_| None).is_err());
        for reason in 0..5 {
            let mut l = Ledger::default();
            l.credit(1, 60, 100)?;
            l.credit(2, 40, 40)?;
            let rows = l.freeze(&p, "zone", [0.; 3], |id| {
                if id == 2 {
                    return Some(present());
                }
                let mut v = present();
                match reason {
                    1 => return None,
                    2 => v.alive = false,
                    3 => v.zone = "other".into(),
                    4 => v.position[1] = 50.001,
                    _ => v.position[1] = 50.,
                };
                Some(v)
            })?;
            assert_eq!(rows[0].reason, reason);
            assert_eq!(rows[1].xp, 4);
        }
        let mut l = Ledger::default();
        l.credit(1, 0, 100)?;
        assert!(!l.active());
        for id in 1..=64 {
            l.credit(id, 1, 100)?;
        }
        assert_eq!(l.admission(1, 64, 1), Err("settlement_capacity"));
        assert_eq!(l.admission(1, 0, 0), Err("settlement_capacity"));
        assert_eq!(l.admission(65, 0, 1), Err("contributor_capacity"));
        assert!(l.admission(1, 63, 1).is_ok());
        assert!(!l.admits(65));
        assert!(l.admits(1));
        assert!(l.credit(65, 1, 100).is_err());
        assert_eq!(p.award(1, 3, 1)?, 4);
        assert_eq!(p.award(2, 3, 1)?, 7);
        Ok(())
    }
    #[test]
    fn template_reward_is_recorded_and_validated() -> Result<()> {
        // PQ-249: a templated NPC's level and XP replace the definition's for
        // its encounter; the realm definition (hash) is unchanged.
        let p = policy();
        let reward = NpcReward { level: 5, xp: 40 };
        let effective = p.for_npc(Some(reward));
        assert_eq!((effective.npc_level, effective.base_xp, &effective.hash), (5, 40, &p.hash));
        assert!(matches!(p.for_npc(None), std::borrow::Cow::Borrowed(_)));
        let mut ledger = Ledger::default();
        ledger.credit(7, 30, 90)?;
        ledger.credit(9, 60, 90)?;
        let recipients = ledger.freeze(&effective, "zone", [0.; 3], |_| Some(present()))?;
        // Level 1 players against a level 5 template: ceil(40 × credit / 90) × 6/5.
        assert_eq!(recipients.iter().map(|r| r.xp).collect::<Vec<_>>(), vec![17, 33]);
        let mut s = Settlement {
            npc: Some(reward),
            items: None,
            coins: None,
            loot_order: None,
            parties: None,
            encounter: 1,
            generation: 2,
            release: vec![1; 32],
            definition: p.hash.clone(),
            zone: "zone".into(),
            position: [0.; 3],
            tick: 3,
            claim: 4,
            recipients,
        };
        s.validate(&p)?;
        let bytes = s.canonical()?;
        let mut trailer = b"N3T1".to_vec();
        trailer.extend(5u32.to_le_bytes());
        trailer.extend(40u32.to_le_bytes());
        assert!(bytes.ends_with(&trailer));
        // Without the template the same awards are wrong, and the payload differs.
        let mut plain = s.clone();
        plain.npc = None;
        assert!(plain.validate(&p).is_err());
        assert_eq!(plain.canonical()?, bytes[..bytes.len() - 12]);
        // A forged reward fails validation; one out of bounds fails the payload.
        s.npc = Some(NpcReward { level: 5, xp: 41 });
        assert!(s.validate(&p).is_err());
        for bad in [NpcReward { level: 0, xp: 40 }, NpcReward { level: 256, xp: 40 }, NpcReward { level: 5, xp: TEMPLATE_XP_LIMIT + 1 }] {
            s.npc = Some(bad);
            assert!(s.canonical().is_err());
        }
        Ok(())
    }
    #[test]
    fn reference_template_health_settles_solo_and_party() -> Result<()> {
        // PQ-251: a 150,000 HP homeland template killed from full health gives
        // more than the old 100,000 credit bound, solo and in a party, and the
        // settlement must still be written (a refused one stops the realm).
        let mut p = policy();
        let reward = NpcReward { level: 110, xp: 40 };
        let effective = p.for_npc(Some(reward));
        let mut ledger = Ledger::default();
        let mut hp = 150_000u32;
        while hp > 0 {
            let blow = hp.min(9_000);
            ledger.credit(7, blow, hp)?;
            hp -= blow;
        }
        let recipients = ledger.freeze(&effective, "zone", [0.; 3], |_| Some(present()))?;
        assert_eq!(recipients.iter().map(|r| (r.credit, r.xp)).collect::<Vec<_>>(), vec![(150_000, 72)]);
        let solo = Settlement {
            npc: Some(reward),
            items: None,
            coins: None,
            loot_order: None,
            parties: None,
            encounter: 1,
            generation: 2,
            release: vec![1; 32],
            definition: p.hash.clone(),
            zone: "zone".into(),
            position: [0.; 3],
            tick: 3,
            claim: 4,
            recipients,
        };
        solo.validate(&p)?;
        solo.canonical()?;
        // Two party members split 150,000 + a regenerated 7,500.
        p.thresholds = [0, 200, 500, 900, 1400, 2000, 2700, 3500, 4400, 5400];
        p.party_rewards = Some(crate::party_rewards::Policy {
            bonus_tenths: 8,
            minimum: 2.0 / 3.0,
            maximum: 1.5,
            gap: 8,
            level_xp: [200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100],
        });
        p.validate()?;
        let effective = p.for_npc(Some(reward));
        let group = crate::party_rewards::Group { id: 7, leader_level: 1, members: vec![1, 2], credited: vec![] };
        let mut ledger = Ledger::default();
        ledger.credit(1, 100_000, 150_000)?;
        ledger.credit(2, 57_500, 57_500)?;
        let (rows, groups) =
            ledger.freeze_parties(&effective, "zone", [0.; 3], |_| Some(present()), |_| Some(group.clone()))?;
        assert_eq!(rows.iter().map(|r| r.credit).sum::<u64>(), 157_500);
        let party = Settlement { recipients: rows, parties: groups, ..solo.clone() };
        party.validate(&p)?;
        party.canonical()?;
        // The party loot winner reads the same totals.
        let credits: Vec<_> = party
            .recipients
            .iter()
            .map(|r| crate::party_loot::Credit { id: r.id, amount: r.credit, valid: true, group: Some(7) })
            .collect();
        assert_eq!(crate::party_loot::winner(&credits)?, Some(1));
        Ok(())
    }
    #[test]
    fn reference_template_xp_settles_solo_and_party() -> Result<()> {
        // PQ-252 (D-165): a template's XP is the row's iExp. The largest
        // reference row (39,438,375) at level 110 gives a level 1 player 9/5
        // of it, past the old 1,800,000 solo and 13,200,000 party payload
        // caps; a row's 0 gives nothing; both settlements must be written.
        let mut p = policy();
        for (xp, solo_award) in [(39_438_375, 70_989_075u64), (0, 0), (TEMPLATE_XP_LIMIT, SOLO_XP_LIMIT)] {
            let reward = NpcReward { level: 110, xp };
            let effective = p.for_npc(Some(reward));
            let mut ledger = Ledger::default();
            ledger.credit(7, 150_000, 150_000)?;
            let recipients = ledger.freeze(&effective, "zone", [0.; 3], |_| Some(present()))?;
            assert_eq!(recipients.iter().map(|r| r.xp).collect::<Vec<_>>(), vec![solo_award]);
            let s = Settlement {
                npc: Some(reward),
                items: None,
                coins: None,
                loot_order: None,
                parties: None,
                encounter: 1,
                generation: 2,
                release: vec![1; 32],
                definition: p.hash.clone(),
                zone: "zone".into(),
                position: [0.; 3],
                tick: 3,
                claim: 4,
                recipients,
            };
            s.validate(&p)?;
            let mut trailer = b"N3T1".to_vec();
            trailer.extend(110u32.to_le_bytes());
            trailer.extend(xp.to_le_bytes());
            assert!(s.canonical()?.ends_with(&trailer));
            let mut over = s.clone();
            over.recipients[0].xp = SOLO_XP_LIMIT + 1;
            assert!(over.canonical().is_err());
        }
        // Two qualified level 1 members of one party: ceil(share) x 2 (an NPC
        // level of 8 or more) x 1.8 (two qualified at 0.8) x 1/2 each.
        p.thresholds = std::array::from_fn(|i| i as u64 * 2_000_000_000);
        p.party_rewards = Some(crate::party_rewards::Policy {
            bonus_tenths: 8,
            minimum: 2.0 / 3.0,
            maximum: 1.5,
            gap: 8,
            level_xp: [2_000_000_000; 10],
        });
        p.validate()?;
        for (xp, each) in [(39_438_375, 70_989_075u64), (0, 0)] {
            let reward = NpcReward { level: 110, xp };
            let effective = p.for_npc(Some(reward));
            let group = crate::party_rewards::Group { id: 7, leader_level: 1, members: vec![1, 2], credited: vec![] };
            let mut ledger = Ledger::default();
            ledger.credit(1, 75_000, 150_000)?;
            ledger.credit(2, 75_000, 75_000)?;
            let (rows, groups) =
                ledger.freeze_parties(&effective, "zone", [0.; 3], |_| Some(present()), |_| Some(group.clone()))?;
            assert_eq!(rows.iter().map(|r| r.xp).collect::<Vec<_>>(), vec![each, each]);
            let party = Settlement {
                npc: Some(reward),
                items: None,
                coins: None,
                loot_order: None,
                parties: groups,
                encounter: 1,
                generation: 2,
                release: vec![1; 32],
                definition: p.hash.clone(),
                zone: "zone".into(),
                position: [0.; 3],
                tick: 3,
                claim: 4,
                recipients: rows,
            };
            party.validate(&p)?;
            let mut over = party.clone();
            over.recipients[0].xp = PARTY_XP_LIMIT + 1;
            assert!(over.canonical().is_err());
        }
        // Party awards refuse a base past the template bound.
        let policy = p.party_rewards.clone().unwrap();
        assert!(policy.awards(TEMPLATE_XP_LIMIT, 110, 1, 1, 1, &[1, 1]).is_ok());
        assert!(policy.awards(TEMPLATE_XP_LIMIT + 1, 110, 1, 1, 1, &[1, 1]).is_err());
        Ok(())
    }
    #[test]
    fn encounter_credit_stops_at_the_limit() -> Result<()> {
        let mut ledger = Ledger::default();
        for _ in 0..60 {
            ledger.credit(7, 2_000_000, 2_000_000)?;
        }
        ledger.credit(8, 5, 5)?; // past the limit: no credit and no recipient
        assert_eq!(ledger.credits.values().sum::<u64>(), CREDIT_LIMIT);
        assert_eq!(ledger.order(), vec![7]);
        let recipients = ledger.freeze(&policy(), "zone", [0.; 3], |_| Some(present()))?;
        assert_eq!(recipients.iter().map(|r| r.credit).collect::<Vec<_>>(), vec![CREDIT_LIMIT]);
        let mut s = Settlement {
            npc: None,
            items: None,
            coins: None,
            loot_order: None,
            parties: None,
            encounter: 1,
            generation: 2,
            release: vec![1; 32],
            definition: policy().hash.clone(),
            zone: "zone".into(),
            position: [0.; 3],
            tick: 3,
            claim: 4,
            recipients,
        };
        s.validate(&policy())?;
        s.recipients[0].credit += 1;
        assert!(s.canonical().is_err());
        Ok(())
    }
    #[test]
    fn reference_template_level_is_rewarded_and_recorded() -> Result<()> {
        // PQ-251: a reference template's level (KO's homeland rows: 22-110) is
        // above every member level (1-10); the reward takes the top multiplier
        // and the settlement records and validates that level.
        let p = policy();
        let reward = NpcReward { level: 110, xp: 40 };
        let effective = p.for_npc(Some(reward));
        let mut ledger = Ledger::default();
        ledger.credit(7, 90, 90)?;
        let recipients = ledger.freeze(&effective, "zone", [0.; 3], |_| Some(present()))?;
        // Level 1 player against a level 110 template: 40 × 9/5.
        assert_eq!(recipients.iter().map(|r| r.xp).collect::<Vec<_>>(), vec![72]);
        let s = Settlement {
            npc: Some(reward),
            items: None,
            coins: None,
            loot_order: None,
            parties: None,
            encounter: 1,
            generation: 2,
            release: vec![1; 32],
            definition: p.hash.clone(),
            zone: "zone".into(),
            position: [0.; 3],
            tick: 3,
            claim: 4,
            recipients,
        };
        s.validate(&p)?;
        let mut trailer = b"N3T1".to_vec();
        trailer.extend(110u32.to_le_bytes());
        trailer.extend(40u32.to_le_bytes());
        assert!(s.canonical()?.ends_with(&trailer));
        // A level 255 template is in bounds for the payload; 256 is not.
        let mut top = s.clone();
        top.npc = Some(NpcReward { level: 255, xp: 40 });
        assert!(top.canonical().is_ok());
        Ok(())
    }
    #[test]
    fn canonical_and_owner() -> Result<()> {
        let p = policy();
        let s = Settlement {
            npc: None,
            items: None, coins: None,
            loot_order: None,
            parties: None,
            encounter: 1,
            generation: 2,
            release: vec![3; 32],
            definition: p.hash.clone(),
            zone: "zone".into(),
            position: [0., 1., -2.],
            tick: 3,
            claim: 4,
            recipients: vec![
                Recipient {
                    id: 7,
                    credit: 50,
                    reason: 0,
                    level: 1,
                    xp: 5,
                },
                Recipient {
                    id: 9,
                    credit: 50,
                    reason: 0,
                    level: 1,
                    xp: 5,
                },
            ],
        };
        s.validate(&p)?;
        assert_eq!(s.owner(), Some(7));
        assert_eq!(s.canonical()?.len(), 197);
        let golden = include_str!("../../protocol/golden-settlement-payload.hex").trim();
        let expected: Vec<u8> = (0..golden.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&golden[i..i + 2], 16).unwrap())
            .collect();
        assert_eq!(s.canonical()?, expected);
        let mut bad = s.clone();
        bad.recipients.reverse();
        assert!(bad.canonical().is_err());
        let mut bad = s.clone();
        bad.recipients[0].xp = 6;
        assert!(bad.validate(&p).is_err());
        let mut bad = s;
        bad.position[0] = f32::NAN;
        assert!(bad.canonical().is_err());
        Ok(())
    }
}
