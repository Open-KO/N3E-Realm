//! The tester kit (RQ-212, specs/03-admin-api.md `POST /v1/characters/kit`): an
//! operator maxes one named character for testing. In one transaction on the
//! account worker it raises the character to the package's level cap (the last
//! progression threshold; the class's skills open by level) and equips the
//! package's best arrangement for damage, judged by the package's own stats at
//! that level. The character must be out of the world: an online character is
//! refused, and a later entry loads what the kit committed. This module knows no
//! game's item, slot or level: every id and number is the package's.
use crate::{
    accounts::{Owner, Selected},
    content::{bad, Result},
    equipment, inventory, persistence, progression, wire,
};
use prost::Message;
use std::sync::Arc;

/// Most arrangements the exhaustive search scores; a package with more
/// combinations is searched greedily, one placement at a time.
const EXHAUSTIVE: u64 = 100_000;
/// Most greedy passes per slot.
const PASSES: usize = 4;

/// What one arrangement is worth, compared in order: attack (PvP damage), then
/// defense, then health, then resource.
type Score = (u32, u32, u32, u32);

/// What the kit needs from the loaded package, and its arrangement, chosen once.
pub struct Context {
    pub owner: Arc<Owner>,
    progression: Option<Arc<progression::Policy>>,
    inventory: Option<Arc<inventory::Policy>>,
    reward: String,
    /// The item per equipment slot (None: left empty), or None when the package
    /// has no equipment or no stats to judge it by.
    plan: Option<Vec<Option<String>>>,
}

/// Why a kit was not applied; nothing changed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Refusal {
    /// No character of that name in this realm.
    NotFound,
    /// The character is in the world (its `online` flag in this generation).
    Online,
    /// The bag has too few free slots for the gear the kit takes off.
    BagFull { needed: usize, free: usize },
}

/// What a kit did.
#[derive(Debug, Clone, PartialEq)]
pub struct Outcome {
    pub character_id: i64,
    pub account_id: i64,
    pub character: String,
    /// The character's level afterwards; None without a progression policy.
    pub level: Option<u32>,
    /// (slot name, item id, item label) of every slot the kit filled.
    pub equipped: Vec<(String, String, String)>,
    /// Gear moved from the equipment into the bag.
    pub unequipped: usize,
    /// The audit row's request id.
    pub request: String,
}

impl Context {
    pub fn new(
        owner: Arc<Owner>,
        progression: Option<Arc<progression::Policy>>,
        inventory: Option<Arc<inventory::Policy>>,
        reward: String,
    ) -> Self {
        let thresholds = progression
            .as_ref()
            .map(|p| p.thresholds)
            .or_else(|| inventory.as_ref().and_then(|i| i.thresholds));
        // The arrangement is judged at the package's level cap.
        let cap = thresholds.map_or(1, |t| t.partition_point(|v| *v <= t[t.len() - 1]) as u32);
        let plan = inventory.as_ref().and_then(|bag| {
            let (gear, stats) = (bag.equipment.as_ref()?, bag.stats.as_ref()?);
            let durability = |id: &str| {
                bag.items
                    .iter()
                    .find(|i| i.id == id)
                    .map_or(0, |i| i.durability)
            };
            let arrangement = best(gear, &durability, &|records| {
                stats
                    .calculate(gear, records, cap)
                    .ok()
                    .map(|s| (s.attack, s.defense, s.max_health, s.max_resource))
            });
            Some(
                arrangement
                    .into_iter()
                    .map(|r| (r.instance != 0).then_some(r.item))
                    .collect(),
            )
        });
        Self {
            owner,
            progression,
            inventory,
            reward,
            plan,
        }
    }

    /// Applies the kit to the character named `name` (its exact name first,
    /// else without regard to case) in one fenced transaction, audited under
    /// the token `by` with `reason`.
    pub fn apply(
        &self,
        c: &mut postgres::Client,
        name: &str,
        by: &str,
        reason: &str,
    ) -> Result<std::result::Result<Outcome, Refusal>> {
        let o = &self.owner;
        let mut t = c.transaction()?;
        persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
        let Some(row) = t.query_opt(
            "SELECT id,account_id,name,online AND realm_generation=$3 FROM characters \
             WHERE realm=$1 AND lower(name)=lower($2) ORDER BY name=$2 DESC,id LIMIT 1 FOR UPDATE",
            &[&o.realm, &name, &o.generation],
        )?
        else {
            return Ok(Err(Refusal::NotFound));
        };
        let (id, account, character): (i64, i64, String) = (row.get(0), row.get(1), row.get(2));
        if row.get::<_, bool>(3) {
            return Ok(Err(Refusal::Online));
        }
        let mut level = None;
        if let Some(p) = &self.progression {
            if let Some(r) = t.query_opt(
                "SELECT p.xp,r.curve_xp,r.revision,r.definition FROM character_progress p \
                 JOIN character_reward_progress r USING(character_id) \
                 WHERE p.character_id=$1 AND r.realm=$2 FOR UPDATE OF p,r",
                &[&id, &o.realm],
            )? {
                if r.get::<_, Vec<u8>>(3) != p.hash {
                    return Err(bad("tester kit: progression definition conflict"));
                }
                let (xp, curve, revision) = (
                    r.get::<_, i64>(0) as u64,
                    r.get::<_, i64>(1) as u64,
                    r.get::<_, i64>(2),
                );
                let top = p.thresholds[p.thresholds.len() - 1];
                if curve < top {
                    // As a settlement does: lifetime XP grows by what the curve gains.
                    let xp = progression::add(xp, top - curve)?;
                    t.execute(
                        "UPDATE character_progress SET xp=$2 WHERE character_id=$1",
                        &[&id, &(xp as i64)],
                    )?;
                    t.execute(
                        "UPDATE character_reward_progress SET curve_xp=$2,revision=$3 WHERE character_id=$1",
                        &[&id, &(top as i64), &(revision + 1)],
                    )?;
                }
                level = Some(p.level(curve.max(top)));
            }
        }
        let (mut equipped, mut unequipped, mut before, mut after, mut revision) =
            (vec![], 0, vec![], vec![], 0);
        if let (Some(bag), Some(plan)) = (&self.inventory, &self.plan) {
            let gear = bag
                .equipment
                .as_ref()
                .ok_or_else(|| bad("tester kit: no equipment"))?;
            let selected = Selected {
                id,
                generation: 0,
                life_revision: 0,
                dead: false,
                ready_ticks: 0,
                specialty: None,
                entity: Default::default(),
            };
            let mut state = inventory::load(&mut t, &selected, o, bag, &self.reward)?;
            before = state.encode_to_vec();
            let mut worn: Vec<wire::ItemStack> = std::mem::take(&mut state.equipment);
            let mut next = Vec::with_capacity(plan.len());
            for (slot, want) in plan.iter().enumerate() {
                let Some(item) = want else {
                    next.push(wire::ItemStack::default());
                    continue;
                };
                let definition = bag
                    .items
                    .iter()
                    .find(|i| i.id == *item)
                    .ok_or_else(|| bad("tester kit: item not in the bag policy"))?;
                // The same item already worn anywhere is kept (repaired), so a
                // second kit changes nothing.
                let record = match worn.iter().position(|r| r.instance != 0 && r.item == *item) {
                    Some(i) => wire::ItemStack {
                        durability: definition.durability,
                        ..std::mem::take(&mut worn[i])
                    },
                    None => wire::ItemStack {
                        instance: inventory::serial(&mut t)?,
                        item: item.clone(),
                        quantity: 1,
                        durability: definition.durability,
                    },
                };
                equipped.push((
                    gear.slots[slot].clone(),
                    item.clone(),
                    definition.label.clone(),
                ));
                next.push(record);
            }
            let off: Vec<wire::ItemStack> = worn.into_iter().filter(|r| r.instance != 0).collect();
            let free: Vec<usize> = (0..state.slots.len())
                .filter(|i| state.slots[*i].instance == 0)
                .collect();
            if off.len() > free.len() {
                return Ok(Err(Refusal::BagFull {
                    needed: off.len(),
                    free: free.len(),
                }));
            }
            unequipped = off.len();
            for (record, slot) in off.into_iter().zip(free) {
                state.slots[slot] = record;
            }
            state.equipment = next;
            state.revision = state
                .revision
                .checked_add(1)
                .ok_or_else(|| bad("bag revision overflow"))?;
            bag.validate(&state)?;
            inventory::save(&mut t, id, &state)?;
            after = state.encode_to_vec();
            revision = state.revision as i64;
        }
        let mut serial = [0u8; 8];
        openssl::rand::rand_bytes(&mut serial)?;
        let request = format!("kit-{:016x}", u64::from_le_bytes(serial));
        let reason: String = reason.chars().take(160).collect();
        t.execute(
            "INSERT INTO admin_audit(realm,token_name,request,revision,target,reason,before_state,after_state,outcome) \
             VALUES($1,$2,$3,$4,$5,$6,$7,$8,'kit_applied')",
            &[&o.realm, &by, &request, &revision, &format!("character:{id}"), &reason, &before, &after],
        )?;
        persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
        t.commit()?;
        Ok(Ok(Outcome {
            character_id: id,
            account_id: account,
            character,
            level,
            equipped,
            unequipped,
            request,
        }))
    }
}

/// The arrangement of eligible items (`equipment::Policy::eligible`, placed as
/// `equipment::Policy::validate` allows) with the highest `score`: every
/// combination when there are at most `EXHAUSTIVE`, else a greedy ascent from
/// empty. Ties keep the first found (package item order, then slot order), so
/// the choice is stable for a package. Records carry placeholder instances.
pub fn best(
    gear: &equipment::Policy,
    durability: &dyn Fn(&str) -> u32,
    score: &dyn Fn(&[wire::ItemStack]) -> Option<Score>,
) -> Vec<wire::ItemStack> {
    let n = gear.slots.len();
    let record = |slot: usize, item: &equipment::Item| wire::ItemStack {
        instance: slot as u64 + 1,
        item: item.id.clone(),
        quantity: 1,
        durability: durability(&item.id),
    };
    let options: Vec<Vec<&equipment::Item>> = (0..n)
        .map(|slot| {
            gear.items
                .iter()
                .filter(|i| gear.eligible(i) && i.slots & (1 << slot) != 0)
                .collect()
        })
        .collect();
    let empty = vec![wire::ItemStack::default(); n];
    let combinations = options
        .iter()
        .try_fold(1u64, |a, o| a.checked_mul(o.len() as u64 + 1))
        .filter(|c| *c <= EXHAUSTIVE);
    // Whether no placed item blocks a slot another occupies.
    let placed = |records: &[wire::ItemStack]| {
        records
            .iter()
            .enumerate()
            .filter(|(_, r)| r.instance != 0)
            .all(|(slot, r)| {
                let blocks = gear.item(&r.item).map_or(0, |i| i.blocks);
                records
                    .iter()
                    .enumerate()
                    .all(|(j, other)| j == slot || other.instance == 0 || blocks & (1 << j) == 0)
            })
    };
    let mut top = (score(&empty), empty.clone());
    if combinations.is_some() {
        let mut current = empty.clone();
        let mut digits = vec![0usize; n];
        loop {
            for (slot, (record_at, digit)) in current.iter_mut().zip(&digits).enumerate() {
                *record_at = match digit {
                    0 => wire::ItemStack::default(),
                    d => record(slot, options[slot][d - 1]),
                };
            }
            if placed(&current) {
                let s = score(&current);
                if s.is_some() && s > top.0 {
                    top = (s, current.clone());
                }
            }
            // The next combination, the first slot fastest.
            let mut slot = 0;
            while slot < n {
                digits[slot] += 1;
                if digits[slot] <= options[slot].len() {
                    break;
                }
                digits[slot] = 0;
                slot += 1;
            }
            if slot == n {
                break;
            }
        }
        return top.1;
    }
    for _ in 0..PASSES * n.max(1) {
        let mut step: Option<(Option<Score>, Vec<wire::ItemStack>)> = None;
        for (slot, items) in options.iter().enumerate() {
            for item in items {
                let mut next = top.1.clone();
                for (j, other) in next.iter_mut().enumerate() {
                    let clashes = other.instance != 0
                        && (j == slot
                            || item.blocks & (1 << j) != 0
                            || gear
                                .item(&other.item)
                                .is_some_and(|i| i.blocks & (1 << slot) != 0));
                    if clashes {
                        *other = wire::ItemStack::default();
                    }
                }
                next[slot] = record(slot, item);
                let s = score(&next);
                if s.is_some() && s > step.as_ref().map_or(top.0, |b| b.0) {
                    step = Some((s, next));
                }
            }
        }
        match step {
            Some(found) => top = found,
            None => break,
        }
    }
    top.1
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Two hands, two rings: a one-hander for either hand, a two-hander that
    /// blocks the left hand, a shield, a ring, and an item the package's race
    /// may not wear.
    fn gear() -> equipment::Policy {
        let item = |id: &str, slots: u32, blocks: u32, race: u32| equipment::Item {
            id: id.into(),
            slots,
            blocks,
            title: 0,
            race,
            attributes: [0; 5],
            swappable: false,
        };
        equipment::Policy {
            title: 0,
            race: 1,
            attributes: [0; 5],
            slots: vec![
                "Right hand".into(),
                "Left hand".into(),
                "Right ring".into(),
                "Left ring".into(),
            ],
            items: vec![
                item("blade", 0b0011, 0, 0),
                item("twohand", 0b0001, 0b0010, 0),
                item("shield", 0b0010, 0, 0),
                item("ring", 0b1100, 0, 0),
                item("foreign", 0b0001, 0, 2),
            ],
        }
    }

    /// A synthetic damage rule: right hand counts in full, the left hand half
    /// (a shield none, but defense), each ring a point; a foreign item would
    /// be best if it were eligible.
    fn score(records: &[wire::ItemStack]) -> Option<Score> {
        let at = |slot: usize| records[slot].item.as_str();
        let hand = |id: &str| match id {
            "blade" => 20,
            "twohand" => 35,
            "foreign" => 99,
            _ => 0,
        };
        let attack =
            hand(at(0)) + hand(at(1)) / 2 + (2..4).filter(|s| at(*s) == "ring").count() as u32;
        let defense = if at(1) == "shield" { 5 } else { 0 };
        Some((attack, defense, 100, 50))
    }

    fn names(records: &[wire::ItemStack]) -> Vec<&str> {
        records.iter().map(|r| r.item.as_str()).collect()
    }

    #[test]
    fn the_best_arrangement_for_damage() {
        let g = gear();
        let arrangement = best(&g, &|_| 80, &score);
        // Blade + blade (20 + 10) loses to the two-hander (35); both rings add.
        assert_eq!(names(&arrangement), ["twohand", "", "ring", "ring"]);
        assert!(arrangement
            .iter()
            .filter(|r| r.instance != 0)
            .all(|r| r.durability == 80 && r.quantity == 1));
        // A dual-wield rule turns it round: two blades beat one two-hander.
        let dual = |r: &[wire::ItemStack]| {
            score(r).map(|(a, d, h, m)| (a + if r[1].item == "blade" { 10 } else { 0 }, d, h, m))
        };
        assert_eq!(
            names(&best(&g, &|_| 80, &dual)),
            ["blade", "blade", "ring", "ring"]
        );
        // Equal attack: the shield's defense decides the left hand.
        let flat = |r: &[wire::ItemStack]| {
            let attack = if r[0].item == "blade" { 20 } else { 0 };
            Some((attack, if r[1].item == "shield" { 5 } else { 0 }, 0, 0))
        };
        assert_eq!(
            names(&best(&g, &|_| 80, &flat)),
            ["blade", "shield", "", ""]
        );
    }

    #[test]
    fn the_greedy_search_agrees_on_a_simple_package() {
        // Enough rings that the combinations pass the exhaustive bound.
        let mut g = gear();
        g.slots = (0..12).map(|i| format!("Slot {i}")).collect();
        g.items = (0..12)
            .map(|i| equipment::Item {
                id: format!("piece{i}"),
                slots: 0xfff,
                blocks: 0,
                title: 0,
                race: 0,
                attributes: [0; 5],
                swappable: false,
            })
            .collect();
        let value = |r: &[wire::ItemStack]| {
            Some((
                r.iter()
                    .map(|r| {
                        r.item
                            .strip_prefix("piece")
                            .map_or(0, |n| n.parse::<u32>().unwrap())
                    })
                    .sum(),
                0,
                0,
                0,
            ))
        };
        let arrangement = best(&g, &|_| 1, &value);
        assert_eq!(names(&arrangement), vec!["piece11"; 12]);
    }

    /// RQ-212 against a disposable PostgreSQL and the stats fixture
    /// (tests/tester_kit_db.py): refusals, the kit, a second kit, a full bag.
    #[test]
    #[ignore = "tests/tester_kit_db.py supplies disposable PostgreSQL and package"]
    fn durable_kit() -> Result<()> {
        use crate::accounts::Database;
        let url = std::env::var("N3E_TEST_DATABASE_URL")?;
        persistence::migrate(&url, persistence::MIGRATIONS)?;
        let release = crate::content::load(std::path::Path::new(&std::env::var("N3E_PACKAGE")?))?;
        let rules = &release.rules;
        let p = rules
            .progression
            .clone()
            .ok_or_else(|| bad("the package has no progression"))?;
        let bag = rules
            .inventory
            .clone()
            .ok_or_else(|| bad("the package has no inventory"))?;
        let gear = bag
            .equipment
            .as_ref()
            .ok_or_else(|| bad("the package has no equipment"))?;
        let stats = bag
            .stats
            .as_ref()
            .ok_or_else(|| bad("the package has no stats"))?;
        let mut c = persistence::connect(&url)?;
        let realm = format!("rq212-{}", std::process::id());
        let generation = persistence::acquire(&mut c, &realm, "kit")?;
        let o = Arc::new(Owner {
            realm: realm.clone(),
            owner: "kit".into(),
            generation,
        });
        crate::settlements::convert(&mut c, &o, &p, &release.game, 20)?;
        let account: i64 = c
            .query_one(
                "INSERT INTO accounts(name,salt,password_hash) VALUES($1,$2,$3) RETURNING id",
                &[&realm, &&[0u8; 16][..], &&[0u8; 32][..]],
            )?
            .get(0);
        let runtime = tokio::runtime::Runtime::new()?;
        let db = Database::start(url, Default::default())?;
        for name in ["Tester", "Full"] {
            let valid = crate::create::Valid::named(name);
            runtime.block_on(db.create(account, valid, o.clone(), release.create_spawn()?, 8))?;
        }
        let kit = Context::new(
            o.clone(),
            Some(p.clone()),
            Some(bag.clone()),
            rules.item.clone(),
        );
        let id = |c: &mut postgres::Client, name: &str| -> Result<i64> {
            Ok(c.query_one(
                "SELECT id FROM characters WHERE realm=$1 AND name=$2",
                &[&realm, &name],
            )?
            .get(0))
        };
        let progress = |c: &mut postgres::Client, id: i64| -> Result<(i64, i64, i64)> {
            let r = c.query_one(
                "SELECT p.xp,r.curve_xp,r.revision FROM character_progress p JOIN character_reward_progress r \
                 USING(character_id) WHERE character_id=$1",
                &[&id],
            )?;
            Ok((r.get(0), r.get(1), r.get(2)))
        };
        let state = |c: &mut postgres::Client, id: i64| -> Result<wire::BagState> {
            let row = c.query_one(
                "SELECT state FROM character_bags WHERE character_id=$1",
                &[&id],
            )?;
            Ok(wire::BagState::decode(row.get::<_, Vec<u8>>(0).as_slice())?)
        };
        let tester = id(&mut c, "Tester")?;
        assert_eq!(
            kit.apply(&mut c, "Nobody", "bot", "test")?,
            Err(Refusal::NotFound)
        );
        // In the world in this generation: refused, nothing changed.
        c.execute(
            "UPDATE characters SET online=true,realm_generation=$2 WHERE id=$1",
            &[&tester, &generation],
        )?;
        assert_eq!(
            kit.apply(&mut c, "Tester", "bot", "test")?,
            Err(Refusal::Online)
        );
        assert_eq!(progress(&mut c, tester)?, (0, 0, 0));
        // A flag a previous generation left is no session.
        c.execute(
            "UPDATE characters SET realm_generation=$2 WHERE id=$1",
            &[&tester, &(generation - 1)],
        )?;
        let done = kit
            .apply(&mut c, "tester", "bot", "PvP test")?
            .map_err(|r| bad(&format!("{r:?}")))?;
        let top = p.thresholds[p.thresholds.len() - 1] as i64;
        assert_eq!(
            (done.character_id, done.account_id, done.character.as_str()),
            (tester, account, "Tester")
        );
        assert_eq!(done.level, Some(p.level(top as u64)));
        assert_eq!(
            progress(&mut c, tester)?,
            (top, top, 1),
            "lifetime and curve XP at the cap, one revision"
        );
        let kitted = state(&mut c, tester)?;
        bag.validate(&kitted)?;
        let worn: Vec<&str> = kitted.equipment.iter().map(|r| r.item.as_str()).collect();
        println!("kit arrangement {worn:?}");
        assert_eq!(
            done.equipped
                .iter()
                .map(|e| e.1.as_str())
                .collect::<Vec<_>>(),
            worn.iter()
                .copied()
                .filter(|i| !i.is_empty())
                .collect::<Vec<_>>()
        );
        for r in kitted.equipment.iter().filter(|r| r.instance != 0) {
            let item = gear.item(&r.item).unwrap();
            assert!(gear.eligible(item), "{} is eligible", r.item);
            assert_eq!(
                r.durability,
                bag.items
                    .iter()
                    .find(|i| i.id == r.item)
                    .unwrap()
                    .durability
            );
        }
        // No single eligible item in any slot beats the arrangement's attack.
        let level = p.level(top as u64);
        let attack = stats.calculate(gear, &kitted.equipment, level)?.attack;
        for item in gear.items.iter().filter(|i| gear.eligible(i)) {
            for slot in (0..gear.slots.len()).filter(|s| item.slots & (1 << s) != 0) {
                let mut alone = vec![wire::ItemStack::default(); gear.slots.len()];
                alone[slot] = wire::ItemStack {
                    instance: 1,
                    item: item.id.clone(),
                    quantity: 1,
                    durability: 1,
                };
                assert!(
                    stats.calculate(gear, &alone, level)?.attack <= attack,
                    "{} in {slot}",
                    item.id
                );
            }
        }
        let audit = c.query_one(
            "SELECT token_name,account_id IS NULL AND character_id IS NULL,target,reason,outcome,revision \
             FROM admin_audit WHERE realm=$1 AND request=$2",
            &[&realm, &done.request],
        )?;
        assert_eq!(
            (
                audit.get::<_, String>(0),
                audit.get::<_, bool>(1),
                audit.get::<_, String>(2),
                audit.get::<_, String>(3)
            ),
            (
                "bot".into(),
                true,
                format!("character:{tester}"),
                "PvP test".into()
            )
        );
        assert_eq!(
            (audit.get::<_, String>(4), audit.get::<_, i64>(5)),
            ("kit_applied".into(), kitted.revision as i64)
        );
        // A second kit keeps the same records and the same level.
        let again = kit
            .apply(&mut c, "Tester", "ops", "again")?
            .map_err(|r| bad(&format!("{r:?}")))?;
        assert_eq!((again.level, again.unequipped), (done.level, 0));
        assert_eq!(progress(&mut c, tester)?, (top, top, 1));
        let second = state(&mut c, tester)?;
        assert_eq!(
            (second.equipment.clone(), second.slots.clone()),
            (kitted.equipment.clone(), kitted.slots.clone())
        );
        assert_eq!(second.revision, kitted.revision + 1);
        // A full bag with gear the kit would take off: refused, nothing changed.
        let full = id(&mut c, "Full")?;
        let mut t = c.transaction()?;
        let selected = Selected {
            id: full,
            generation: 0,
            life_revision: 0,
            dead: false,
            ready_ticks: 0,
            specialty: None,
            entity: Default::default(),
        };
        let mut s = inventory::load(&mut t, &selected, &o, &bag, &rules.item)?;
        t.commit()?;
        let (slot, other) = (0..gear.slots.len())
            .find_map(|slot| {
                gear.items
                    .iter()
                    .find(|i| {
                        gear.eligible(i)
                            && i.slots & (1 << slot) != 0
                            && i.id != kitted.equipment[slot].item
                            && i.blocks == 0
                    })
                    .map(|i| (slot, i.id.clone()))
            })
            .ok_or_else(|| bad("the fixture has no second choice for a slot"))?;
        let mut serial = 1_000_000_000u64;
        let mut fresh = |item: &str| {
            serial += 1;
            wire::ItemStack {
                instance: serial,
                item: item.into(),
                quantity: 1,
                durability: bag.items.iter().find(|i| i.id == item).unwrap().durability,
            }
        };
        s.equipment[slot] = fresh(&other);
        for record in s.slots.iter_mut().filter(|r| r.instance == 0) {
            *record = fresh(&other);
        }
        bag.validate(&s)?;
        c.execute(
            "UPDATE character_bags SET state=$2 WHERE character_id=$1",
            &[&full, &s.encode_to_vec()],
        )?;
        assert_eq!(
            kit.apply(&mut c, "Full", "bot", "test")?,
            Err(Refusal::BagFull { needed: 1, free: 0 })
        );
        assert_eq!(
            progress(&mut c, full)?,
            (0, 0, 0),
            "the refused kit's XP rolled back"
        );
        assert_eq!(state(&mut c, full)?, s);
        // A free slot: the worn item goes to the bag.
        s.slots[0] = wire::ItemStack::default();
        c.execute(
            "UPDATE character_bags SET state=$2 WHERE character_id=$1",
            &[&full, &s.encode_to_vec()],
        )?;
        let moved = kit
            .apply(&mut c, "Full", "bot", "test")?
            .map_err(|r| bad(&format!("{r:?}")))?;
        assert_eq!(moved.unequipped, 1);
        let after = state(&mut c, full)?;
        assert_eq!(
            after.slots[0].instance, s.equipment[slot].instance,
            "the worn record, unchanged, in the bag"
        );
        assert_eq!(
            after
                .equipment
                .iter()
                .map(|r| r.item.as_str())
                .collect::<Vec<_>>(),
            worn,
            "the same arrangement"
        );
        println!("PASS tester kit: refusals (unknown, online, full bag) change nothing; the kit sets the level cap and the best gear once, a second kit keeps it; audited by token");
        Ok(())
    }

    #[test]
    fn nothing_scored_leaves_the_equipment_empty() {
        let g = gear();
        let arrangement = best(&g, &|_| 80, &|_| None);
        assert!(arrangement.iter().all(|r| r.instance == 0));
    }
}
