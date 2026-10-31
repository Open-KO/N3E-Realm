//! Bounded drop generation. Binary leaves and open integration: content/party-loot.md.
use crate::content::{Result, bad};

#[derive(Clone, Debug)]
pub struct Policy {
    pub currency: String,
    pub generation: Coins,
    pub pickup_bonus_percent: u32,
    pub bonus_cap: u32,
}
impl Policy {
    pub fn read(r: &mut crate::content::Reader) -> Result<Self> {
        let p = Self {
            currency: r.string()?,
            generation: Coins {
                base: r.u()?,
                minimum_percent: r.u()?,
                maximum_percent: r.u()?,
                event_percent: r.u()?,
                party_bonus_percent: r.u()?,
                maximum: r.u()?,
                overflow: r.u()?,
            },
            pickup_bonus_percent: r.u()?,
            bonus_cap: r.u()?,
        };
        p.validate()?;
        Ok(p)
    }
    pub fn encode(&self, b: &mut Vec<u8>) {
        b.extend((self.currency.len() as u32).to_le_bytes());
        b.extend(self.currency.as_bytes());
        let g = &self.generation;
        for v in [
            g.base,
            g.minimum_percent,
            g.maximum_percent,
            g.event_percent,
            g.party_bonus_percent,
            g.maximum,
            g.overflow,
            self.pickup_bonus_percent,
            self.bonus_cap,
        ] {
            b.extend(v.to_le_bytes());
        }
    }
    pub fn validate(&self) -> Result<()> {
        self.generation.validate()?;
        if self.currency.is_empty()
            || self.currency.len() > 129
            || self.pickup_bonus_percent > 100
            || !(1..=32766).contains(&self.bonus_cap)
        {
            return Err(bad("coin drop policy"));
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct Outcome {
    pub draw: u32,
    pub amount: u32,
}

pub fn eligible(s: &crate::progression::Settlement) -> Option<u32> {
    let owner = s.owner()?;
    let group = s
        .parties
        .as_ref()?
        .iter()
        .find(|g| g.members.contains(&owner))?;
    Some(
        s.recipients
            .iter()
            .filter(|r| r.reason == 0 && group.members.contains(&r.id))
            .count() as u32,
    )
}

/// Reference interval mapping includes modulo bias and bounded repeat avoidance.
#[derive(Default)]
pub struct Intervals {
    previous: u32,
}
impl Intervals {
    pub fn draw(
        &mut self,
        minimum: u32,
        maximum: u32,
        allow_repeat: bool,
        raw: &mut impl FnMut() -> u32,
    ) -> Result<u32> {
        if minimum > maximum || maximum > 32767 {
            return Err(bad("drop random interval"));
        }
        // The binary returns before reading or changing either random state.
        if minimum == maximum {
            return Ok(minimum);
        }
        let mut value = minimum;
        for _ in 0..10 {
            let sample = raw();
            if sample > 32767 {
                return Err(bad("drop random sample"));
            }
            value = sample % (maximum - minimum + 1) + minimum;
            if allow_repeat {
                return Ok(value);
            }
            if value != self.previous {
                self.previous = value;
                return Ok(value);
            }
        }
        Ok(value)
    }
}

/// AI0045b30e's wrapping CRT recurrence, owned by one simulation.
pub struct Random {
    state: u32,
    intervals: Intervals,
}
impl Random {
    pub fn new() -> Result<Self> {
        let mut seed = [0; 4];
        openssl::rand::rand_bytes(&mut seed)?;
        Ok(Self {
            state: u32::from_le_bytes(seed),
            intervals: Intervals::default(),
        })
    }
    fn next(state: &mut u32) -> u32 {
        *state = state.wrapping_mul(0x343fd).wrapping_add(0x269ec3);
        (*state >> 16) & 0x7fff
    }
    pub fn draw(&mut self, minimum: u32, maximum: u32) -> Result<u32> {
        self.intervals
            .draw(minimum, maximum, false, &mut || Self::next(&mut self.state))
    }
}

#[derive(Clone, Debug)]
pub struct Coins {
    pub base: u32,
    pub minimum_percent: u32,
    pub maximum_percent: u32,
    pub event_percent: u32,
    pub party_bonus_percent: u32,
    pub maximum: u32,
    pub overflow: u32,
}
impl Coins {
    pub fn validate(&self) -> Result<()> {
        if self.base > i32::MAX as u32 / 100
            || self.minimum_percent > self.maximum_percent
            || self.maximum_percent > 100
            || self.event_percent > 32767
            || self.party_bonus_percent > 100
            || !(1..=32766).contains(&self.maximum)
            || !(1..=self.maximum).contains(&self.overflow)
        {
            return Err(bad("coin generation policy"));
        }
        // Refuse definitions whose legacy signed intermediate would overflow.
        let largest = self.base as f64
            * (1. + self.event_percent as f64 * 0.01)
            * (1. + 7. * (self.party_bonus_percent as f64 / 100.));
        if largest > i32::MAX as f64 {
            return Err(bad("coin generation intermediate bound"));
        }
        Ok(())
    }
    /// None means solo; a party with zero eligible members still applies its factor.
    pub fn amount(&self, draw: u32, eligible_party: Option<u32>) -> Result<u32> {
        self.validate()?;
        if !(self.minimum_percent..=self.maximum_percent).contains(&draw)
            || eligible_party.is_some_and(|n| n > 8)
        {
            return Err(bad("coin generation input"));
        }
        let mut amount = self.base * draw / 100;
        if self.event_percent > 0 {
            let percent = self.event_percent as f64 * 0.01;
            amount = (amount as f64 + amount as f64 * percent).trunc() as u32;
        }
        if let Some(members) = eligible_party {
            let factor = 1. + (members as f64 - 1.) * (self.party_bonus_percent as f64 / 100.);
            amount = (amount as f64 * factor).trunc() as u32;
        }
        Ok(if amount > self.maximum {
            self.overflow
        } else {
            amount
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crt_sequence_and_bounded_repeat_mapping() -> Result<()> {
        let mut state = 1;
        assert_eq!(
            (0..6).map(|_| Random::next(&mut state)).collect::<Vec<_>>(),
            [41, 18467, 6334, 26500, 19169, 15724]
        );
        let mut intervals = Intervals::default();
        let mut calls = 0;
        let mut raw = || {
            calls += 1;
            0
        };
        assert_eq!(intervals.draw(70, 100, false, &mut raw)?, 70);
        assert_eq!(intervals.draw(70, 100, false, &mut raw)?, 70);
        assert_eq!(calls, 11); // First draw succeeds; duplicate exhausts ten attempts.
        let mut none = || panic!("fixed/invalid intervals must not consume randomness");
        assert_eq!(intervals.draw(15, 15, false, &mut none)?, 15);
        assert!(intervals.draw(2, 1, false, &mut none).is_err());
        assert!(intervals.draw(0, 32768, false, &mut none).is_err());
        assert!(intervals.draw(0, 2, false, &mut || 32768).is_err());
        // Allow-repeat returns without changing the helper's previous value.
        assert_eq!(intervals.draw(1, 2, true, &mut || 0)?, 1);
        calls = 0;
        assert_eq!(
            intervals.draw(70, 100, false, &mut || {
                calls += 1;
                0
            })?,
            70
        );
        assert_eq!(calls, 10);
        let mut buckets = [0u32; 31];
        for raw in 0..32768 {
            buckets[(intervals.draw(70, 100, true, &mut || raw)? - 70) as usize] += 1;
        }
        assert_eq!(buckets.iter().sum::<u32>(), 32768);
        assert_eq!(buckets.iter().min(), Some(&1057));
        assert_eq!(buckets.iter().max(), Some(&1058));
        Ok(())
    }

    #[test]
    fn generation_order_zero_members_and_receiver_boundary() -> Result<()> {
        let mut p = Coins {
            base: 1000,
            minimum_percent: 70,
            maximum_percent: 100,
            event_percent: 10,
            party_bonus_percent: 20,
            maximum: 32766,
            overflow: 32000,
        };
        assert_eq!(p.amount(75, None)?, 825);
        assert_eq!(p.amount(75, Some(0))?, 660);
        assert_eq!(p.amount(75, Some(1))?, 825);
        assert_eq!(p.amount(75, Some(3))?, 1155);
        assert_eq!(p.amount(75, Some(8))?, 1980);
        p.event_percent = 0;
        for (base, want) in [
            (0, 0),
            (32766, 32766),
            (32767, 32000),
            (32768, 32000),
            (279618, 32000),
        ] {
            p.base = base;
            assert_eq!(p.amount(100, None)?, want);
        }
        p.base = 1;
        assert_eq!(p.amount(70, Some(8))?, 0); // Integer base scaling happens first.
        assert!(p.amount(69, None).is_err());
        assert!(p.amount(100, Some(9)).is_err());
        p.base = i32::MAX as u32;
        assert!(p.validate().is_err());
        p.base = 1_000_000;
        p.event_percent = 32767;
        assert!(p.validate().is_ok());
        p.party_bonus_percent = 100;
        assert!(p.validate().is_err());
        Ok(())
    }
}
