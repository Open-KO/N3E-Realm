//! The package's character-create rules (`create.bin`, RQ-002): which races and
//! specialties a create may name, each race's nation, faces and hairs, each
//! specialty's base stats and bonus points, the name rule, the refusal wording,
//! and the fixed choice a create without a race takes (Q52). The server checks a
//! `CreateCharacter` against them and never trusts the client's fields
//! (content/character-create.md, "The realm's create"; Q95). Version 2 (RQ-154,
//! Q96) adds the realm owner's start for a new character and the bag items each
//! specialty starts with. This module knows no game's race, specialty, stat or
//! item: every number and id is the package's.
use crate::{
    content::{bad, Reader, Result},
    wire,
};
use std::path::Path;

/// Most stats, races, specialties a race offers, and reserved words a file holds.
pub const MAX_STATS: u32 = 8;
pub const MAX_RACES: u32 = 32;
pub const MAX_SPECIALTIES: u32 = 16;
pub const MAX_RESERVED: u32 = 256;
/// The longest name `characters.name` holds (deploy/002-multiplayer.sql).
pub const MAX_NAME: u32 = 24;
/// The longest refusal text and reserved word.
pub const MAX_TEXT: usize = 200;
pub const MAX_WORD: usize = 24;
/// The file's version: 2 adds the start and the starting items (RQ-154).
pub const VERSION: u32 = 2;
/// Most stacks a specialty starts with, the most of one stack, the longest
/// item id (the bag holds at most 64 stacks of 9999), and a start's bound in
/// engine metres.
pub const MAX_KIT: u32 = 64;
pub const MAX_COUNT: u32 = 9999;
pub const MAX_ITEM: usize = 128;
pub const MAX_METRES: f32 = 1e6;
/// Without create rules: today's rule, 1..24 ASCII letters, digits, `_` and `-`.
pub const LEGACY_NAME: usize = 24;

/// Why a create is refused, numbered as the wire's `CreateCharacter.Result`
/// (KO's create results).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Refusal {
    Limit,
    Mismatch,
    Taken,
    Failed,
    Name,
    Stats,
}
impl Refusal {
    pub const ALL: [Refusal; 6] = [
        Refusal::Limit,
        Refusal::Mismatch,
        Refusal::Taken,
        Refusal::Failed,
        Refusal::Name,
        Refusal::Stats,
    ];
    pub fn result(self) -> wire::create_character::Result {
        use wire::create_character::Result as R;
        match self {
            Refusal::Limit => R::CreateLimit,
            Refusal::Mismatch => R::CreateMismatch,
            Refusal::Taken => R::CreateTaken,
            Refusal::Failed => R::CreateFailed,
            Refusal::Name => R::CreateName,
            Refusal::Stats => R::CreateStats,
        }
    }
    /// The engine's wording, for a package without create rules or one that
    /// words none.
    pub fn engine_text(self) -> &'static str {
        match self {
            Refusal::Limit => "character limit reached",
            Refusal::Mismatch => "race, specialty or nation not offered",
            Refusal::Taken => "character name taken",
            Refusal::Failed => "character could not be created",
            Refusal::Name => "character name invalid",
            Refusal::Stats => "character stats, face or hair invalid",
        }
    }
    fn index(self) -> usize {
        Refusal::ALL.iter().position(|r| *r == self).unwrap()
    }
}
impl std::fmt::Display for Refusal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.engine_text())
    }
}
impl std::error::Error for Refusal {}

#[derive(Clone, Debug, PartialEq)]
pub struct Specialty {
    pub id: u32,
    pub bonus: u32,
    pub base: Vec<u32>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Race {
    pub id: u32,
    pub nation: u32,
    pub faces: u32,
    pub hairs: u32,
    pub specialties: Vec<Specialty>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Fixed {
    pub race: u32,
    pub specialty: u32,
    pub face: u32,
    pub hair: u32,
    pub stats: Vec<u32>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Policy {
    pub stats: u32,
    /// The account's nation until the realm keeps one per account (RQ-006).
    pub nation: u32,
    pub races: Vec<Race>,
    pub name_min: u32,
    pub name_max: u32,
    /// The punctuation a name may hold beside ASCII letters and digits.
    pub punctuation: Vec<u8>,
    /// Lower-case words no name may contain, compared without regard to case.
    pub reserved: Vec<String>,
    /// The package's wording of each refusal, in `Refusal::ALL`'s order; empty
    /// keeps the engine's.
    pub refusals: Vec<String>,
    pub fixed: Option<Fixed>,
    /// Where a new character starts (engine x, z), the realm owner's
    /// `create.start`; None starts it at the package's spawn.
    pub start: Option<[f32; 2]>,
    /// The bag items (id, count) each specialty starts with, by specialty; a
    /// specialty without a set starts with the package's `starting` items.
    pub kits: std::collections::BTreeMap<u32, Vec<(String, u32)>>,
}

/// A create the rules accept, as the server stores it. Without create rules only
/// the name is set; `slot` None takes the first free slot.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Valid {
    pub name: String,
    pub slot: Option<u32>,
    pub chosen: Option<Chosen>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Chosen {
    pub nation: u32,
    pub race: u32,
    pub specialty: u32,
    pub face: u32,
    pub hair: u32,
    pub stats: Vec<u32>,
}
impl Valid {
    /// A create of `name` only, in the first free slot (a package without create
    /// rules, and the tests' fixtures).
    pub fn named(name: &str) -> Self {
        Valid {
            name: name.into(),
            ..Default::default()
        }
    }
}

fn text(r: &mut Reader, limit: usize, what: &str) -> Result<String> {
    let n = r.u()? as usize;
    if n > limit {
        return Err(bad(what));
    }
    let s = std::str::from_utf8(r.take(n)?)?.to_owned();
    if !s.bytes().all(|b| (b' '..=b'~').contains(&b) || b == b'\n') {
        return Err(bad(what));
    }
    Ok(s)
}

impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        Self::read(Reader::open(path)?)
    }
    pub fn read(mut r: Reader) -> Result<Self> {
        if r.take(4)? != b"N3CC" || r.u()? != VERSION {
            return Err(bad("create magic/version"));
        }
        let stats = r.u()?;
        let nation = r.u()?;
        let count = r.u()?;
        if !(1..=MAX_STATS).contains(&stats)
            || !(1..=255).contains(&nation)
            || !(1..=MAX_RACES).contains(&count)
        {
            return Err(bad("create bounds"));
        }
        let mut races: Vec<Race> = Vec::new();
        for _ in 0..count {
            let (id, race_nation, faces, hairs, n) = (r.u()?, r.u()?, r.u()?, r.u()?, r.u()?);
            if !(1..=65535).contains(&id)
                || races.iter().any(|x| x.id == id)
                || !(1..=255).contains(&race_nation)
                || !(1..=256).contains(&faces)
                || !(1..=256).contains(&hairs)
                || !(1..=MAX_SPECIALTIES).contains(&n)
            {
                return Err(bad("create race"));
            }
            let mut specialties: Vec<Specialty> = Vec::new();
            for _ in 0..n {
                let (sid, bonus) = (r.u()?, r.u()?);
                let base = (0..stats).map(|_| r.u()).collect::<Result<Vec<_>>>()?;
                if !(1..=65535).contains(&sid)
                    || specialties.iter().any(|x| x.id == sid)
                    || bonus > 1000
                    || base.iter().any(|v| *v > 1000)
                {
                    return Err(bad("create specialty"));
                }
                specialties.push(Specialty {
                    id: sid,
                    bonus,
                    base,
                });
            }
            races.push(Race {
                id,
                nation: race_nation,
                faces,
                hairs,
                specialties,
            });
        }
        let (name_min, name_max) = (r.u()?, r.u()?);
        let punctuation = text(&mut r, 32, "create punctuation")?.into_bytes();
        if !(1..=name_max).contains(&name_min)
            || name_max > MAX_NAME
            || punctuation
                .iter()
                .any(|b| b.is_ascii_alphanumeric() || !b.is_ascii_graphic())
        {
            return Err(bad("create name rule"));
        }
        let n = r.u()?;
        if n > MAX_RESERVED {
            return Err(bad("create reserved count"));
        }
        let mut reserved = Vec::new();
        for _ in 0..n {
            let word = text(&mut r, MAX_WORD, "create reserved word")?;
            if word.is_empty()
                || word
                    .bytes()
                    .any(|b| b.is_ascii_uppercase() || !b.is_ascii_graphic())
            {
                return Err(bad("create reserved word"));
            }
            reserved.push(word);
        }
        let refusals = Refusal::ALL
            .iter()
            .map(|_| text(&mut r, MAX_TEXT, "create refusal text"))
            .collect::<Result<Vec<_>>>()?;
        let fixed = match r.u()? {
            0 => None,
            1 => Some(Fixed {
                race: r.u()?,
                specialty: r.u()?,
                face: r.u()?,
                hair: r.u()?,
                stats: (0..stats).map(|_| r.u()).collect::<Result<Vec<_>>>()?,
            }),
            _ => return Err(bad("create fixed flag")),
        };
        let start = match r.u()? {
            0 => None,
            1 => {
                let p = [r.f()?, r.f()?];
                if p.iter().any(|v| !v.is_finite() || v.abs() > MAX_METRES) {
                    return Err(bad("create start"));
                }
                Some(p)
            }
            _ => return Err(bad("create start flag")),
        };
        let offered: Vec<u32> = races
            .iter()
            .flat_map(|r| r.specialties.iter().map(|s| s.id))
            .collect();
        let n = r.u()?;
        if n as usize > offered.len() {
            return Err(bad("create items count"));
        }
        let mut kits = std::collections::BTreeMap::new();
        for _ in 0..n {
            let (specialty, stacks) = (r.u()?, r.u()?);
            if !offered.contains(&specialty) || kits.contains_key(&specialty) || stacks > MAX_KIT {
                return Err(bad("create items specialty"));
            }
            let mut kit: Vec<(String, u32)> = Vec::new();
            for _ in 0..stacks {
                let item = text(&mut r, MAX_ITEM, "create item")?;
                let count = r.u()?;
                if item.is_empty()
                    || !item.bytes().all(|b| b.is_ascii_graphic())
                    || kit.iter().any(|(i, _)| *i == item)
                    || !(1..=MAX_COUNT).contains(&count)
                {
                    return Err(bad("create item"));
                }
                kit.push((item, count));
            }
            kits.insert(specialty, kit);
        }
        r.end()?;
        let policy = Policy {
            stats,
            nation,
            races,
            name_min,
            name_max,
            punctuation,
            reserved,
            refusals,
            fixed,
            start,
            kits,
        };
        if let Some(f) = &policy.fixed {
            // The fixed choice is one the rules accept, in the default nation.
            let q = wire::CreateCharacter {
                race: f.race,
                specialty: f.specialty,
                face: f.face,
                hair: f.hair,
                stats: f.stats.clone(),
                ..Default::default()
            };
            if policy.choice(&q, policy.nation).is_err() {
                return Err(bad("create fixed choice"));
            }
        }
        Ok(policy)
    }
    /// The wording of a refusal: the package's, else the engine's.
    pub fn text(&self, refusal: Refusal) -> &str {
        match self.refusals[refusal.index()].as_str() {
            "" => refusal.engine_text(),
            worded => worded,
        }
    }
    /// The name rule: its length, ASCII letters and digits and the package's
    /// punctuation, and no reserved word (Q99).
    pub fn name(&self, name: &str) -> bool {
        let folded = name.to_ascii_lowercase();
        (self.name_min as usize..=self.name_max as usize).contains(&name.len())
            && name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || self.punctuation.contains(&b))
            && !self.reserved.iter().any(|w| folded.contains(w.as_str()))
    }
    /// The race, specialty, face, hair and stats a create names, checked
    /// (Q95): the race offered and of `nation`, the specialty one of the
    /// race's, the face and hair in range, each stat at least its base and the
    /// stats summing to the base's sum plus the bonus.
    pub fn choice(
        &self,
        q: &wire::CreateCharacter,
        nation: u32,
    ) -> std::result::Result<Chosen, Refusal> {
        let race = self
            .races
            .iter()
            .find(|r| r.id == q.race)
            .ok_or(Refusal::Mismatch)?;
        if race.nation != nation {
            return Err(Refusal::Mismatch);
        }
        let specialty = race
            .specialties
            .iter()
            .find(|s| s.id == q.specialty)
            .ok_or(Refusal::Mismatch)?;
        if q.face >= race.faces || q.hair >= race.hairs || q.stats.len() != self.stats as usize {
            return Err(Refusal::Stats);
        }
        let base: u64 = specialty.base.iter().map(|v| u64::from(*v)).sum();
        let sum: u64 = q.stats.iter().map(|v| u64::from(*v)).sum();
        if q.stats.iter().zip(&specialty.base).any(|(v, b)| v < b)
            || sum != base + u64::from(specialty.bonus)
        {
            return Err(Refusal::Stats);
        }
        Ok(Chosen {
            nation,
            race: race.id,
            specialty: specialty.id,
            face: q.face,
            hair: q.hair,
            stats: q.stats.clone(),
        })
    }
}

/// Checks one `CreateCharacter` against the package's rules (`policy`, None
/// for a package without them) and the realm's slot count. The database then
/// checks the account's count, the name's uniqueness and the slot
/// (accounts::Database::create). Order: the name, the slot, the race and
/// specialty, then face, hair and stats, as Ebenezer checks the name, slot,
/// class and stats before its database's count, nation, name and slot.
pub fn check(
    policy: Option<&Policy>,
    q: &wire::CreateCharacter,
    slots: u32,
) -> std::result::Result<Valid, Refusal> {
    let Some(policy) = policy else {
        // No create rules: the name alone, in the first free slot.
        if !crate::accounts::valid_name(&q.name, LEGACY_NAME) {
            return Err(Refusal::Name);
        }
        return Ok(Valid::named(&q.name));
    };
    if !policy.name(&q.name) {
        return Err(Refusal::Name);
    }
    if q.race == 0 {
        // Q52 until the create screen sends a choice (RQ-004): the package's
        // fixed choice, in the first free slot; nothing else of the request.
        let f = policy.fixed.as_ref().ok_or(Refusal::Mismatch)?;
        let fixed = wire::CreateCharacter {
            race: f.race,
            specialty: f.specialty,
            face: f.face,
            hair: f.hair,
            stats: f.stats.clone(),
            ..Default::default()
        };
        return Ok(Valid {
            name: q.name.clone(),
            slot: None,
            chosen: Some(policy.choice(&fixed, policy.nation)?),
        });
    }
    if q.slot >= slots {
        return Err(Refusal::Limit);
    }
    Ok(Valid {
        name: q.name.clone(),
        slot: Some(q.slot),
        chosen: Some(policy.choice(q, policy.nation)?),
    })
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub(crate) fn u(v: u32) -> Vec<u8> {
        v.to_le_bytes().to_vec()
    }
    pub(crate) fn s(v: &str) -> Vec<u8> {
        [u(v.len() as u32), v.as_bytes().to_vec()].concat()
    }
    /// A synthetic two-nation rule set: race 7 (nation 1) with specialties 70
    /// and 71, race 8 (nation 2) with 80; three stats; no start, no items.
    pub(crate) fn bytes(fixed: Option<[u32; 7]>) -> Vec<u8> {
        with(fixed, None, &[])
    }
    /// The same rules with a start and starting items (RQ-154).
    pub(crate) fn with(
        fixed: Option<[u32; 7]>,
        start: Option<[f32; 2]>,
        kits: &[(u32, &[(&str, u32)])],
    ) -> Vec<u8> {
        let mut b = b"N3CC".to_vec();
        for v in [VERSION, 3, 1, 2] {
            b.extend(u(v));
        }
        for v in [7, 1, 4, 3, 2, 70, 5, 40, 30, 20, 71, 5, 20, 30, 40] {
            b.extend(u(v));
        }
        for v in [8, 2, 2, 1, 1, 80, 0, 10, 10, 10] {
            b.extend(u(v));
        }
        b.extend(u(1));
        b.extend(u(20));
        b.extend(s("_:;"));
        b.extend(u(1));
        b.extend(s("staff"));
        for t in ["No more.", "", "Taken.", "", "Bad name.", ""] {
            b.extend(s(t));
        }
        match fixed {
            None => b.extend(u(0)),
            Some(f) => {
                b.extend(u(1));
                for v in f {
                    b.extend(u(v));
                }
            }
        }
        match start {
            None => b.extend(u(0)),
            Some([x, z]) => {
                b.extend(u(1));
                b.extend(x.to_le_bytes());
                b.extend(z.to_le_bytes());
            }
        }
        b.extend(u(kits.len() as u32));
        for (specialty, items) in kits {
            b.extend(u(*specialty));
            b.extend(u(items.len() as u32));
            for (item, count) in *items {
                b.extend(s(item));
                b.extend(u(*count));
            }
        }
        b
    }
    /// The synthetic rules with a start and two specialties' sets, one empty.
    pub(crate) fn kitted() -> Vec<u8> {
        with(
            Some([7, 71, 0, 0, 20, 30, 45]),
            Some([1.5, -2.25]),
            &[
                (70, &[("demo:item/blade", 1), ("demo:item/potion", 5)]),
                (80, &[]),
            ],
        )
    }
    pub(crate) fn policy() -> Policy {
        Policy::read(Reader::from_bytes(bytes(Some([7, 71, 0, 0, 20, 30, 45])))).unwrap()
    }
    fn q(
        name: &str,
        slot: u32,
        race: u32,
        specialty: u32,
        face: u32,
        hair: u32,
        stats: &[u32],
    ) -> wire::CreateCharacter {
        wire::CreateCharacter {
            name: name.into(),
            slot,
            race,
            specialty,
            face,
            hair,
            stats: stats.to_vec(),
        }
    }

    /// tests/character_create.py cooks the same rules with tools/assetc/create.py
    /// and checks these digests (without and with a start and items), so the
    /// cook and this reader share one layout.
    pub(crate) const SYNTHETIC_SHA256: &str =
        "7d7b89d81e821be5a03de5ceb9247a82ab786c253e0480c7fcef6d534b68adb5";
    pub(crate) const KITTED_SHA256: &str =
        "47b6e87f8be6d055d833e78e8272879c214ff3011145d74eef5db70f147acbb1";
    fn hex(b: &[u8]) -> String {
        openssl::sha::sha256(b)
            .iter()
            .fold(String::new(), |mut s, x| {
                use std::fmt::Write;
                let _ = write!(s, "{x:02x}");
                s
            })
    }

    #[test]
    fn reads_the_rules_and_refuses_malformed_files() {
        assert_eq!(
            hex(&bytes(Some([7, 71, 0, 0, 20, 30, 45]))),
            SYNTHETIC_SHA256
        );
        assert_eq!(hex(&kitted()), KITTED_SHA256);
        let p = policy();
        assert_eq!((p.start, p.kits.len()), (None, 0));
        assert_eq!((p.stats, p.nation, p.races.len()), (3, 1, 2));
        assert_eq!(
            p.races[0].specialties[1],
            Specialty {
                id: 71,
                bonus: 5,
                base: vec![20, 30, 40]
            }
        );
        assert_eq!(p.text(Refusal::Limit), "No more.");
        assert_eq!(p.text(Refusal::Mismatch), Refusal::Mismatch.engine_text());
        assert_eq!(p.fixed.as_ref().unwrap().stats, [20, 30, 45]);
        assert!(Policy::read(Reader::from_bytes(bytes(None)))
            .unwrap()
            .fixed
            .is_none());
        // The fixed choice must pass the rules (a stat below its base, the sum
        // off, the other nation's race, an unknown specialty).
        for f in [
            [7, 71, 0, 0, 19, 30, 46],
            [7, 71, 0, 0, 20, 30, 44],
            [8, 80, 0, 0, 10, 10, 10],
            [7, 80, 0, 0, 20, 30, 45],
        ] {
            assert!(
                Policy::read(Reader::from_bytes(bytes(Some(f)))).is_err(),
                "{f:?}"
            );
        }
        let good = bytes(None);
        // Magic, version (1 is RQ-002's, without the start and items),
        // truncation and trailing bytes.
        for (at, v) in [(0, b'X'), (4, 1), (4, 3)] {
            let mut b = good.clone();
            b[at] = v;
            assert!(Policy::read(Reader::from_bytes(b)).is_err());
        }
        assert!(Policy::read(Reader::from_bytes(good[..good.len() - 1].to_vec())).is_err());
        assert!(Policy::read(Reader::from_bytes([good.clone(), vec![0]].concat())).is_err());
        // Zero stats, a nation over 255, a duplicate race.
        for (at, v) in [(8, 0), (8, MAX_STATS + 1), (12, 256), (16, 0)] {
            let mut b = good.clone();
            b[at..at + 4].copy_from_slice(&v.to_le_bytes());
            assert!(Policy::read(Reader::from_bytes(b)).is_err(), "{at} {v}");
        }
        let mut b = good.clone();
        b[80..84].copy_from_slice(&7u32.to_le_bytes());
        assert!(
            Policy::read(Reader::from_bytes(b)).is_err(),
            "duplicate race"
        );
        // RQ-154: the start and each specialty's set, in the file's order.
        let k = Policy::read(Reader::from_bytes(kitted())).unwrap();
        assert_eq!(k.start, Some([1.5, -2.25]));
        assert_eq!(
            k.kits.get(&70).unwrap(),
            &[
                ("demo:item/blade".to_string(), 1),
                ("demo:item/potion".to_string(), 5)
            ]
        );
        assert_eq!(k.kits.get(&80).map(Vec::len), Some(0));
        assert!(!k.kits.contains_key(&71));
        // A start off the bound or not finite, a specialty no race offers or
        // named twice, a stack count of 0 or past 9999, an item twice or
        // empty, a set past 64 stacks.
        type Sets = Vec<(u32, Vec<(&'static str, u32)>)>;
        let bad_kits: [(Option<[f32; 2]>, Sets); 9] = [
            (Some([f32::NAN, 0.]), vec![]),
            (Some([0., 2e6]), vec![]),
            (None, vec![(72, vec![])]),
            (None, vec![(70, vec![]), (70, vec![])]),
            (None, vec![(70, vec![("a:b", 0)])]),
            (None, vec![(70, vec![("a:b", 10000)])]),
            (None, vec![(70, vec![("a:b", 1), ("a:b", 2)])]),
            (None, vec![(70, vec![("", 1)])]),
            (
                None,
                vec![(
                    70,
                    (0..65)
                        .map(|i| (&*Box::leak(format!("a:{i}").into_boxed_str()), 1))
                        .collect(),
                )],
            ),
        ];
        for (start, kits) in bad_kits {
            let kits: Vec<(u32, &[(&str, u32)])> =
                kits.iter().map(|(s, k)| (*s, k.as_slice())).collect();
            let b = with(None, start, &kits);
            assert!(
                Policy::read(Reader::from_bytes(b)).is_err(),
                "{start:?} {kits:?}"
            );
        }
        let mut b = with(None, None, &[]);
        let at = b.len() - 8;
        b[at..at + 4].copy_from_slice(&2u32.to_le_bytes());
        assert!(Policy::read(Reader::from_bytes(b)).is_err(), "start flag");
    }

    #[test]
    fn checks_names_choices_and_stats() {
        let p = policy();
        let ok = q("Ab_:;9", 2, 7, 70, 3, 2, &[45, 30, 20]);
        let v = check(Some(&p), &ok, 3).unwrap();
        assert_eq!(v.slot, Some(2));
        assert_eq!(
            v.chosen.unwrap(),
            Chosen {
                nation: 1,
                race: 7,
                specialty: 70,
                face: 3,
                hair: 2,
                stats: vec![45, 30, 20]
            }
        );
        let refused = |c: wire::CreateCharacter| check(Some(&p), &c, 3).unwrap_err();
        // Names: empty, too long, a letter KO refuses, a reserved word in any case.
        for name in [
            "",
            "abcdefghijklmnopqrstu",
            "a-b",
            "a b",
            "caf\u{e9}",
            "MyStaffer",
        ] {
            assert_eq!(
                refused(wire::CreateCharacter {
                    name: name.into(),
                    ..ok.clone()
                }),
                Refusal::Name,
                "{name}"
            );
        }
        assert_eq!(
            refused(wire::CreateCharacter {
                slot: 3,
                ..ok.clone()
            }),
            Refusal::Limit
        );
        // Race, specialty and nation.
        assert_eq!(
            refused(wire::CreateCharacter {
                race: 9,
                ..ok.clone()
            }),
            Refusal::Mismatch
        );
        assert_eq!(
            refused(wire::CreateCharacter {
                specialty: 80,
                ..ok.clone()
            }),
            Refusal::Mismatch
        );
        assert_eq!(
            refused(q("Ab", 0, 8, 80, 0, 0, &[10, 10, 10])),
            Refusal::Mismatch
        );
        // Face, hair and stats: range, count, below base, over or under the sum.
        assert_eq!(
            refused(wire::CreateCharacter {
                face: 4,
                ..ok.clone()
            }),
            Refusal::Stats
        );
        assert_eq!(
            refused(wire::CreateCharacter {
                hair: 3,
                ..ok.clone()
            }),
            Refusal::Stats
        );
        for stats in [
            &[45, 30][..],
            &[45, 30, 20, 0],
            &[46, 29, 20],
            &[45, 30, 21],
            &[44, 30, 20],
        ] {
            assert_eq!(
                refused(wire::CreateCharacter {
                    stats: stats.to_vec(),
                    ..ok.clone()
                }),
                Refusal::Stats,
                "{stats:?}"
            );
        }
        // Race 0: the fixed choice in the first free slot, whatever else is sent.
        let fixed = check(Some(&p), &q("Fixed", 9, 0, 1, 9, 9, &[1]), 3).unwrap();
        assert_eq!(fixed.slot, None);
        assert_eq!(fixed.chosen.unwrap().stats, [20, 30, 45]);
        let none = Policy::read(Reader::from_bytes(bytes(None))).unwrap();
        assert_eq!(
            check(Some(&none), &q("Fixed", 0, 0, 0, 0, 0, &[]), 3).unwrap_err(),
            Refusal::Mismatch
        );
        // No rules: the name alone (today's rule), every other field ignored.
        assert_eq!(
            check(None, &q("Old-name_1", 7, 3, 3, 3, 3, &[]), 3).unwrap(),
            Valid::named("Old-name_1")
        );
        assert_eq!(
            check(None, &q("a:b", 0, 0, 0, 0, 0, &[]), 3).unwrap_err(),
            Refusal::Name
        );
    }

    #[test]
    fn results_are_kos_create_codes() {
        let codes: Vec<i32> = Refusal::ALL.iter().map(|r| r.result() as i32).collect();
        assert_eq!(codes, [1, 2, 3, 4, 5, 17]);
    }
}
