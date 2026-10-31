//! Wall-clock length of one simulation tick (PQ-115).
//!
//! Every rule counts ticks, and one tick is 50 ms of game time: package
//! milliseconds become ticks at 50 ms each (combat intervals, skill casts and
//! cooldowns) and movement advances 0.05 s of speed per tick. Production runs one
//! tick every 50 ms of wall time and has no way to change that.
//!
//! A disposable test realm may shorten the wall-clock tick so live suites spend
//! less real time waiting on game timers. It needs all three of
//! `N3E_TEST_TICK_MS` (10 to 50), `N3E_TEST_REALM=disposable` and a realm named
//! `test-...`; the server refuses to start when the first is set without the
//! other two. `compose.yaml` and `deploy/` never pass these variables.
//!
//! Only the conversions between ticks and wall time read [`tick_ms`]: the
//! simulation interval and the durable deadlines that store a tick count as a
//! timestamp (respawn readiness, skill cooldowns). Everything that bounds wall
//! time for correctness (realm lease, health deadline, network deadlines,
//! admission windows, checkpoint cadence, statement timeouts, retry budgets) stays
//! in wall time and is unaffected.
use std::sync::OnceLock;

/// Game time per tick, and the production wall-clock tick.
pub const TICK_MS: u64 = 50;
/// Shortest test tick: five times production speed.
pub const MIN_TEST_TICK_MS: u64 = 10;

static WALL_TICK_MS: OnceLock<u64> = OnceLock::new();

/// Wall-clock milliseconds per tick: 50 unless a disposable test realm set it.
pub fn tick_ms() -> u64 {
    WALL_TICK_MS.get().copied().unwrap_or(TICK_MS)
}

/// Validates the test tick from the server's environment. `None` (or an empty
/// value) is production. Anything else must be an integer from 10 to 50 and needs
/// `disposable == "disposable"` and a `test-` realm; otherwise it is refused.
pub fn parse(value: Option<&str>, disposable: Option<&str>, realm: &str) -> Result<Option<u64>, String> {
    let Some(value) = value.filter(|v| !v.is_empty()) else {
        return Ok(None);
    };
    if disposable != Some("disposable") || !realm.starts_with("test-") {
        return Err(format!(
            "N3E_TEST_TICK_MS refused: a test tick needs N3E_TEST_REALM=disposable and a realm named test-... (realm {realm:?}); production ticks every {TICK_MS} ms"
        ));
    }
    match value.parse::<u64>() {
        Ok(ms) if (MIN_TEST_TICK_MS..=TICK_MS).contains(&ms) => Ok(Some(ms)),
        _ => Err(format!(
            "N3E_TEST_TICK_MS refused: {value:?} is not an integer from {MIN_TEST_TICK_MS} to {TICK_MS}"
        )),
    }
}

/// Reads and applies the test tick once, before the simulation starts. Returns the
/// test tick when one is active so the caller can announce it.
pub fn configure(realm: &str) -> Result<Option<u64>, String> {
    let value = std::env::var("N3E_TEST_TICK_MS").ok();
    let disposable = std::env::var("N3E_TEST_REALM").ok();
    let parsed = parse(value.as_deref(), disposable.as_deref(), realm)?;
    if let Some(ms) = parsed {
        WALL_TICK_MS
            .set(ms)
            .map_err(|_| "N3E_TEST_TICK_MS configured twice".to_string())?;
    }
    Ok(parsed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn production_and_refusals() {
        // Unset or empty: production, whatever else is set.
        assert_eq!(parse(None, Some("disposable"), "test-a"), Ok(None));
        assert_eq!(parse(Some(""), None, "local"), Ok(None));
        // Set without both guards: refused, never silently ignored.
        for (disposable, realm) in [
            (None, "test-a"),
            (Some("yes"), "test-a"),
            (Some(""), "test-a"),
            (Some("disposable"), "local"),
            (Some("disposable"), "n3e-ko06-x"),
            (Some("disposable"), "Test-a"),
            (None, "local"),
        ] {
            let error = parse(Some("25"), disposable, realm).unwrap_err();
            assert!(error.contains("N3E_TEST_REALM=disposable"), "{error}");
        }
        // Guards present but the value is out of range or not an integer.
        for value in ["9", "0", "51", "1000", "-25", "25.0", " 25", "x"] {
            let error = parse(Some(value), Some("disposable"), "test-a").unwrap_err();
            assert!(error.contains("not an integer from 10 to 50"), "{error}");
        }
        assert_eq!(parse(Some("10"), Some("disposable"), "test-a"), Ok(Some(10)));
        assert_eq!(parse(Some("25"), Some("disposable"), "test-a"), Ok(Some(25)));
        assert_eq!(parse(Some("50"), Some("disposable"), "test-a"), Ok(Some(50)));
    }

    #[test]
    fn unconfigured_is_production() {
        // No test in this binary calls configure(), so every conversion that reads
        // tick_ms() (simulation interval, respawn and skill deadlines) is production.
        assert_eq!(tick_ms(), TICK_MS);
    }
}
