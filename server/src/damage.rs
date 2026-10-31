//! Bounded normal melee model. See content/damage.md for provenance and deviations.
use crate::content::{bad, Reader, Result};
use std::path::Path;
/// Highest defence, hit rate and evasion an NPC template carries (PQ-252,
/// D-165): KO's sAc, sHitRate and sEvadeRate are shorts (AI binding
/// `0041737b`). The package-wide N3D1 sides stay within 1-10,000.
pub const TEMPLATE_STAT_LIMIT: u32 = 32767;
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Stats {
    pub attack: u32,
    pub defense: u32,
    pub accuracy: u32,
    pub evasion: u32,
}
#[derive(Clone, Debug)]
pub struct Policy {
    pub player: Stats,
    pub npc: Stats,
}
impl Policy {
    pub fn load(path: &Path) -> Result<Self> {
        let mut r = Reader::open(path)?;
        if r.take(4)? != b"N3D1" || r.u()? != 1 {
            return Err(bad("damage model"));
        }
        let mut stats = || -> Result<Stats> {
            let s = Stats {
                attack: r.u()?,
                defense: r.u()?,
                accuracy: r.u()?,
                evasion: r.u()?,
            };
            if s.attack > 10000
                || s.defense > 10000
                || !(1..=10000).contains(&s.accuracy)
                || !(1..=10000).contains(&s.evasion)
            {
                return Err(bad("damage stats"));
            }
            Ok(s)
        };
        let v = Self {
            player: stats()?,
            npc: stats()?,
        };
        r.end()?;
        Ok(v)
    }
    #[cfg(test)]
    pub fn resolve(&self, npc: bool, rng: &mut impl Rolls) -> Outcome {
        self.resolve_with_player(npc, None, rng)
    }
    pub fn resolve_with_player(
        &self,
        npc: bool,
        player: Option<&crate::wire::DerivedStats>,
        rng: &mut impl Rolls,
    ) -> Outcome {
        let (a, b) = if npc {
            (&self.npc, &self.player)
        } else {
            (&self.player, &self.npc)
        };
        let (attack, defense, accuracy, evasion) = match (npc, player) {
            (true, Some(p)) => (a.attack, p.defense, a.accuracy as f32, p.evasion),
            (false, Some(p)) => (p.attack, b.defense, p.accuracy, b.evasion as f32),
            _ => (a.attack, b.defense, a.accuracy as f32, b.evasion as f32),
        };
        let grade = grade_rates(accuracy, evasion, rng.roll(10000) + 1);
        if grade == 0 {
            return Outcome {
                hit: false,
                damage: 0,
            };
        }
        let base = attack * 200 / (defense + 240);
        let random = rng.roll(base + 1);
        // Exact f32 constants promoted before arithmetic, matching x87 products in
        // this bounded domain. f64 exactly holds both products and their sum.
        let steady = f64::from(0.85_f32) * f64::from(base);
        let varying = f64::from(0.30_f32) * f64::from(random);
        let damage = if npc {
            let value = steady as u32 + varying as u32;
            let value = if grade == 3 { value * 3 / 2 } else { value };
            value.min((2.6 * f64::from(attack)) as u32)
        } else {
            (steady + varying) as u32
        };
        Outcome { hit: true, damage }
    }
    /// PQ-422 (D-219): a player's strike on an NPC under a ranged profile
    /// with a type-2 skill hit (HitType 0), as KO's AI server resolves its
    /// archery (`AI Server-official.exe` `0040d471` -> `00443a34`, skill
    /// branch). The grade ratio is (hit rate / evasion) x (`hit_rate` x
    /// 0.01f) rounded to f32 (`00443bdd`-`00443bfb`); the base is
    /// trunc(`add_damage` x 0.01f x (attack x 200 / (defence + 240)))
    /// (`00443c4d`-`00443c63`); on a hit the damage is trunc(base x 0.6f +
    /// rand(0..=base) x 0.89f + 0.99) (`00443cce`-`00443ce8`), on a miss 0;
    /// `0040d471` then adds `add_damage_plus` and applies a sum above 0, so a
    /// miss with a plus still deals it; a sum of 0, a miss or a hit for 0,
    /// applies nothing and is reported alike (-104), here as a miss. The
    /// rolls and their order are the basic attack's. Inputs are bounded by
    /// the readers (hit_rate 1-1000, add_damage 0-300, add_damage_plus
    /// 0-10000, attack at most 10,000, defence at most 32,767): every
    /// product of a promoted f32 constant and an integer is exact in f64, and
    /// so is the sum of the two damage products, so the truncations are the
    /// x87 ones; adding 0.99 rounds, but no sum comes within 1e-8 of an
    /// integer, which keeps that truncation exact too.
    pub fn resolve_skill_hit(
        &self,
        player: Option<&crate::wire::DerivedStats>,
        hit: &SkillHit,
        rng: &mut impl Rolls,
    ) -> Outcome {
        let (attack, accuracy) = player.map_or((self.player.attack, self.player.accuracy as f32), |p| {
            (p.attack, p.accuracy)
        });
        let (defense, evasion) = (self.npc.defense, self.npc.evasion as f32);
        let percent = f64::from(0.01_f32);
        let ratio = (f64::from(accuracy) / f64::from(evasion) * (f64::from(hit.hit_rate) * percent)) as f32;
        let grade = grade_ratio(ratio, rng.roll(10000) + 1);
        let damage = if grade == 0 {
            0
        } else {
            let base = attack * 200 / (defense + 240);
            let base = (f64::from(hit.add_damage) * percent * f64::from(base)) as u32;
            let random = rng.roll(base + 1);
            (f64::from(0.6_f32) * f64::from(base) + f64::from(0.89_f32) * f64::from(random) + 0.99) as u32
        };
        let total = damage + hit.add_damage_plus;
        Outcome {
            hit: total > 0,
            damage: total,
        }
    }
}
/// PQ-422 (D-219): a ranged profile's type-2 skill hit (`ranged-attack.bin`
/// N3RE): KO's MAGIC_TYPE2 HitRate, AddDamage and AddDamagePlus for a HitType
/// 0 row (`AI Server-official.exe` binding `004107ab`, record `+6`, `+8`,
/// `+0xe`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SkillHit {
    pub hit_rate: u32,
    pub add_damage: u32,
    pub add_damage_plus: u32,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Outcome {
    pub hit: bool,
    pub damage: u32,
}
impl Outcome {
    pub fn status(&self) -> &'static str {
        if self.hit {
            "hit"
        } else {
            "miss"
        }
    }
}
// Grade 3 is the reference's highest normal hit grade, not a separate skill.
#[cfg(test)]
fn grade(accuracy: u32, evasion: u32, roll: u32) -> u8 {
    grade_rates(accuracy as f32, evasion as f32, roll)
}
fn grade_rates(accuracy: f32, evasion: f32, roll: u32) -> u8 {
    grade_ratio(accuracy / evasion, roll)
}
/// KO's hit grade (`AI Server-official.exe` `00444164`) for an f32 ratio and
/// a roll of 1..=10000: 3 great, 2 success, 1 normal, 0 miss.
fn grade_ratio(ratio: f32, roll: u32) -> u8 {
    let ratio = f64::from(ratio);
    let rows = [
        (5., 3500, 7500, 9800),
        (3., 2500, 6000, 9600),
        (2., 2000, 5000, 9400),
        (1.25, 1500, 4000, 9200),
        (0.8, 1000, 3000, 9000),
        (0.5, 800, 2500, 8000),
        (0.33, 600, 2000, 7000),
        (0.2, 400, 1500, 6000),
        (0., 200, 1000, 5000),
    ];
    // A NaN ratio takes the last row, as KO's FCOM/SAHF/JC treats an unordered
    // compare as below every threshold (AI `004235cf`, `00444189`). A template's 0
    // evasion gives +inf (the top row) and a 0 hit rate 0 (the last row); NaN
    // needs both sides 0, which the player's bounds rule out.
    let (_, great, success, normal) = rows
        .into_iter()
        .find(|r| ratio >= r.0)
        .unwrap_or(rows[rows.len() - 1]);
    if roll <= great {
        3
    } else if roll <= success {
        2
    } else if roll <= normal {
        1
    } else {
        0
    }
}
pub trait Rolls {
    fn roll(&mut self, exclusive: u32) -> u32;
}
// Fixed bounded work: SplitMix64, multiply-high interval mapping. Seeded once
// from OS entropy before simulation; never configurable by a network message.
pub struct Random(u64);
impl Random {
    pub fn new() -> Result<Self> {
        let mut b = [0; 8];
        openssl::rand::rand_bytes(&mut b)?;
        Ok(Self(u64::from_le_bytes(b)))
    }
    #[cfg(test)]
    pub fn seeded(seed: u64) -> Self {
        Self(seed)
    }
}
impl Rolls for Random {
    fn roll(&mut self, exclusive: u32) -> u32 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^= z >> 31;
        ((u128::from(z) * u128::from(exclusive)) >> 64) as u32
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixed {
        values: std::collections::VecDeque<u32>,
    }
    impl Rolls for Fixed {
        fn roll(&mut self, n: u32) -> u32 {
            let v = self.values.pop_front().unwrap();
            assert!(v < n);
            v
        }
    }
    fn policy(attack: u32, defense: u32) -> Policy {
        let s = Stats {
            attack,
            defense,
            accuracy: 100,
            evasion: 100,
        };
        Policy {
            player: s.clone(),
            npc: s,
        }
    }
    #[test]
    fn original_numeric_vectors_both_directions() {
        // attack, defense, random damage draw, player, NPC ordinary, NPC high grade
        for (a, d, r, p, n, g) in [
            (0, 0, 0, 0, 0, 0),
            (1, 0, 0, 0, 0, 0),
            (2, 0, 1, 1, 0, 0),
            (12, 0, 3, 9, 8, 12),
            (36, 40, 0, 21, 21, 31),
            (36, 40, 25, 28, 28, 42),
            (10000, 0, 8333, 9582, 9582, 14373),
            (10000, 10000, 195, 224, 223, 334),
            (1, 10000, 0, 0, 0, 0),
        ] {
            let policy = policy(a, d);
            for (npc, roll, expected) in [(false, 5000, p), (true, 5000, n), (true, 0, g)] {
                let mut rng = Fixed {
                    values: [roll, r].into(),
                };
                assert_eq!(
                    policy.resolve(npc, &mut rng),
                    Outcome {
                        hit: true,
                        damage: expected
                    },
                    "{a}/{d}/{r}/{npc}/{roll}"
                );
                assert!(rng.values.is_empty());
            }
            let mut rng = Fixed {
                values: [9999].into(),
            };
            assert_eq!(
                policy.resolve(false, &mut rng),
                Outcome {
                    hit: false,
                    damage: 0
                }
            );
            assert!(rng.values.is_empty());
        }
    }
    #[test]
    fn derived_player_stats_apply_in_both_combat_directions() {
        let mut p = policy(36, 40);
        p.npc.evasion = 1;
        let stats = crate::wire::DerivedStats {
            attack: 12,
            defense: 400,
            accuracy: 1.625,
            evasion: 1.625,
            ..Default::default()
        };
        // 1.625/1 uses the 1.25 band; truncating accuracy to 1 would miss.
        let mut rolls = Fixed {
            values: [9100, 0].into(),
        };
        assert_eq!(
            p.resolve_with_player(false, Some(&stats), &mut rolls),
            Outcome {
                hit: true,
                damage: 6
            }
        );
        // Incoming defense uses 400 rather than the package's fixed 40.
        let mut rolls = Fixed {
            values: [5000, 0].into(),
        };
        assert_eq!(
            p.resolve_with_player(true, Some(&stats), &mut rolls),
            Outcome {
                hit: true,
                damage: 9
            }
        );
        assert!(rolls.values.is_empty());
        assert_eq!(grade_rates(1.625, 1., 9101), 1);
        assert_eq!(grade_rates(1., 1., 9101), 0);
    }

    /// PQ-422 (D-219): the type-2 skill hit, KO's archery on an NPC (AI
    /// `0040d471` -> `00443a34`). Expected values are computed with exact
    /// rationals from the binary's f32 constants (0.01f, 0.6f, 0.89f) and
    /// the double 0.99, truncated as `__ftol` does.
    #[test]
    fn skill_hit_vectors() {
        let p = policy(36, 40); // base 36 x 200 / 280 = 25
        let hit = |hit_rate, add_damage, add_damage_plus| SkillHit { hit_rate, add_damage, add_damage_plus };
        let resolve = |p: &Policy, h: SkillHit, rolls: &[u32]| {
            let mut rng = Fixed { values: rolls.iter().copied().collect() };
            let o = p.resolve_skill_hit(None, &h, &mut rng);
            assert!(rng.values.is_empty(), "{h:?} {rolls:?}");
            o
        };
        // AddDamage 100: 100 x 0.01f x 25 = 24.9999994, so the base is 24;
        // trunc(24 x 0.6f + r x 0.89f + 0.99) is 15 at r = 0 and 36 at r = 24
        // (the basic attack: 21 to 28).
        assert_eq!(resolve(&p, hit(100, 100, 0), &[5000, 0]), Outcome { hit: true, damage: 15 });
        assert_eq!(resolve(&p, hit(100, 100, 0), &[5000, 24]), Outcome { hit: true, damage: 36 });
        // AddDamage 150: base trunc(37.4999991) = 37; 23 to 56.
        assert_eq!(resolve(&p, hit(100, 150, 0), &[0, 0]), Outcome { hit: true, damage: 23 });
        assert_eq!(resolve(&p, hit(100, 150, 0), &[0, 37]), Outcome { hit: true, damage: 56 });
        // AddDamagePlus is added to a hit, and a miss (no damage roll) deals it.
        assert_eq!(resolve(&p, hit(100, 100, 7), &[5000, 24]), Outcome { hit: true, damage: 43 });
        assert_eq!(resolve(&p, hit(100, 100, 7), &[9999]), Outcome { hit: true, damage: 7 });
        assert_eq!(resolve(&p, hit(100, 100, 0), &[9999]), Outcome { hit: false, damage: 0 });
        // A zero sum is a miss (KO applies nothing and reports -104 alike):
        // attack 1 gives base 0, then trunc(0.99) = 0.
        assert_eq!(resolve(&policy(1, 0), hit(100, 100, 0), &[0, 0]), Outcome { hit: false, damage: 0 });
        // HitRate scales the grade ratio: 100 / 100 x 100 x 0.01f rounds to
        // 1.0f (the 0.8 band: a normal hit up to 9,000); HitRate 50 gives 0.5
        // (up to 8,000).
        assert_eq!(resolve(&p, hit(100, 100, 0), &[8999, 0]).hit, true);
        assert_eq!(resolve(&p, hit(50, 100, 0), &[8999]).hit, false);
        assert_eq!(resolve(&p, hit(50, 100, 0), &[7999, 0]).hit, true);
        // Derived player stats take the player side; the NPC's defence and
        // evasion stay the policy's (the target template's).
        let stats = crate::wire::DerivedStats { attack: 12, accuracy: 1.625, evasion: 9., ..Default::default() };
        let mut rng = Fixed { values: [9100, 7].into() };
        let mut q = policy(36, 40);
        q.npc.evasion = 1;
        // 12 x 200 / 280 = 8, base 7; 1.625 / 1 x 0.99999998 is the 1.25 band.
        assert_eq!(q.resolve_skill_hit(Some(&stats), &hit(100, 100, 0), &mut rng), Outcome { hit: true, damage: 11 });
        // The bounds' extremes: attack 10,000 against defence 0, AddDamage
        // 300: base trunc(2.99999993 x 8,333) = 24,998, the top draw 37,248.
        assert_eq!(resolve(&policy(10000, 0), hit(1000, 300, 10000), &[0, 24998]), Outcome { hit: true, damage: 47248 });
    }
    #[test]
    fn exhaustive_hit_bands_and_boundaries() {
        for (a, e, g, s, h) in [
            (500, 100, 3500, 7500, 9800),
            (300, 100, 2500, 6000, 9600),
            (200, 100, 2000, 5000, 9400),
            (125, 100, 1500, 4000, 9200),
            (80, 100, 1000, 3000, 9000),
            (50, 100, 800, 2500, 8000),
            (33, 100, 600, 2000, 7000),
            (20, 100, 400, 1500, 6000),
            (1, 10000, 200, 1000, 5000),
        ] {
            let mut counts = [0; 4];
            for r in 1..=10000 {
                counts[grade(a, e, r) as usize] += 1;
            }
            assert_eq!(counts, [10000 - h, h - s, s - g, g]);
            assert_eq!(grade(a, e, g), 3);
            assert_eq!(grade(a, e, g + 1), 2);
            assert_eq!(grade(a, e, h), 1);
            assert_eq!(grade(a, e, h + 1), 0);
            if a > 1 {
                assert!(grade(a - 1, e, h) == 0);
            }
        }
    }
    #[test]
    fn fixed_seed_sequence_distribution_and_extrema() {
        let mut golden = Random::seeded(42);
        assert_eq!(
            (0..8).map(|_| golden.roll(10000)).collect::<Vec<_>>(),
            vec![7415, 1599, 2786, 3441, 380, 8682, 2184, 8006]
        );
        let mut rng = Random::seeded(42);
        let mut same = Random::seeded(42);
        let mut counts = [0; 10];
        for _ in 0..100000 {
            let v = rng.roll(10);
            assert_eq!(v, same.roll(10));
            counts[v as usize] += 1;
        }
        assert!(
            counts.iter().all(|n| (9500..10500).contains(n)),
            "{counts:?}"
        );
        for npc in [false, true] {
            let p = policy(36, 40);
            let mut rng = Random::seeded(42);
            let mut hits = 0;
            let mut min = u32::MAX;
            let mut max = 0;
            for _ in 0..10000 {
                let o = p.resolve(npc, &mut rng);
                if o.hit {
                    hits += 1;
                    min = min.min(o.damage);
                    max = max.max(o.damage);
                }
            }
            assert!((8700..9300).contains(&hits));
            assert_eq!((min, max), (21, if npc { 42 } else { 28 }));
        }
        // All bounded bases and damage draws have a stable, monotone envelope.
        for npc in [false, true] {
            for a in [0, 1, 2, 9999, 10000] {
                for d in [0, 1, 239, 240, 9999, 10000] {
                    let p = policy(a, d);
                    let b = a * 200 / (d + 240);
                    for draw in [0, b] {
                        let mut rng = Fixed {
                            values: [0, draw].into(),
                        };
                        let o = p.resolve(npc, &mut rng);
                        assert!(o.damage <= 14373);
                    }
                }
            }
        }
    }
    #[test]
    fn reference_template_stats_from_the_rows() {
        // PQ-252 (D-165): sDamage is the NPC attack, sAc its defence, sHitRate
        // and sEvadeRate its hit and evasion rates. A 0 sDamage (a camp gate)
        // makes X = 0, and every grade deals 0 (0041f535 returns 0 for X <= 0).
        let player = Stats { attack: 36, defense: 20, accuracy: 50, evasion: 100 };
        let npc = |attack, defense, accuracy, evasion| Policy {
            player: player.clone(),
            npc: Stats { attack, defense, accuracy, evasion },
        };
        for roll in [0, 5000] {
            let mut rng = Fixed { values: [roll, 0].into() };
            assert_eq!(npc(0, 0, 100, 100).resolve(true, &mut rng), Outcome { hit: true, damage: 0 });
        }
        // A 0 hit rate takes the last row (miss above 5,000), a 0 evasion
        // the first (+inf: miss only above 9,800), for both directions.
        assert_eq!(grade_rates(0., 100., 5000), 1);
        assert_eq!(grade_rates(0., 100., 5001), 0);
        assert_eq!(grade_rates(50., 0., 9800), 1);
        assert_eq!(grade_rates(50., 0., 9801), 0);
        assert_eq!(grade_rates(50., 0., 3500), 3);
        // NaN (0 / 0, which the bounds rule out) is below every row, as KO's
        // unordered FCOM sets CF: the last row.
        assert_eq!(grade_rates(0., 0., 200), 3);
        assert_eq!(grade_rates(0., 0., 5001), 0);
        let mut rng = Fixed { values: [9801].into() };
        assert_eq!(npc(18, 0, 0, 0).resolve(false, &mut rng), Outcome { hit: false, damage: 0 });
        let mut rng = Fixed { values: [5001].into() };
        assert_eq!(npc(18, 0, 0, 0).resolve(true, &mut rng), Outcome { hit: false, damage: 0 });
        // The largest sAc (32,767) against the largest player attack (10,000):
        // B = 2,000,000 / 33,007 = 60; the template bounds never overflow.
        let mut rng = Fixed { values: [0, 60].into() };
        let p = Policy { player: Stats { attack: 10000, ..player.clone() }, npc: Stats { attack: 10000, defense: 32767, accuracy: 32767, evasion: 32767 } };
        assert_eq!(p.resolve(false, &mut rng), Outcome { hit: true, damage: 69 });
        // The homeland rows' largest sDamage (5,000) against defence 0: B =
        // 4,166, highest grade (trunc(0.85 x 4,166) + trunc(0.3 x 4,166)) x 3 /
        // 2 = (3,541 + 1,249) x 3 / 2 = 7,185, under the 13,000 cap and the
        // 16-bit range KO narrows it to.
        let mut rng = Fixed { values: [0, 4166].into() };
        let p = Policy { player: Stats { defense: 0, ..player.clone() }, npc: Stats { attack: 5000, defense: 0, accuracy: 100, evasion: 100 } };
        assert_eq!(p.resolve(true, &mut rng), Outcome { hit: true, damage: 7185 });
    }
}
