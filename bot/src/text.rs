//! Text the bot puts in front of people: Discord-safe echoes of user text, durations,
//! times. No I/O.

use std::time::{SystemTime, UNIX_EPOCH};

/// Discord's message content limit, in characters.
pub const MESSAGE_LIMIT: usize = 2000;

/// Seconds since the Unix epoch.
pub fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs() as i64)
}

/// User text shown as plain text: Discord markdown is backslash-escaped so a reason
/// cannot bold, link, quote or hide anything. Mentions are disarmed separately (every
/// message is sent with no allowed mentions); control characters become spaces.
pub fn escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '\\' | '*' | '_' | '~' | '`' | '|' | '>' | '#' | '-' | '[' | ']' | '(' | ')' | '<'
            | ':' | '@' => {
                out.push('\\');
                out.push(c);
            }
            c if c.is_control() => out.push(' '),
            c => out.push(c),
        }
    }
    out
}

/// At most `MESSAGE_LIMIT` characters, cut on a character boundary.
pub fn fit(text: String) -> String {
    match text.char_indices().nth(MESSAGE_LIMIT - 1) {
        Some((i, _)) => format!("{}…", &text[..i]),
        None => text,
    }
}

/// `/ban` and `/mute` durations: `perm`, or a count of minutes, hours, days or weeks
/// (`30m`, `1h`, `3d`, `2w`). `None` is permanent; `Err` names the problem.
pub fn duration(text: &str) -> Result<Option<i64>, String> {
    let t = text.trim().to_ascii_lowercase();
    if t.is_empty() || t == "perm" || t == "permanent" {
        return Ok(None);
    }
    let (count, unit) = t.split_at(t.len() - 1);
    let seconds = match unit {
        "m" => 60,
        "h" => 3600,
        "d" => 86_400,
        "w" => 604_800,
        _ => {
            return Err(format!(
                "`{}` is not a duration: use 30m, 1h, 3d, 2w or perm",
                escape(text)
            ))
        }
    };
    match count.parse::<i64>() {
        // Ten years is the longest timed sanction; past that, say perm.
        Ok(n) if n > 0 && n * seconds <= 10 * 366 * 86_400 => Ok(Some(n * seconds)),
        _ => Err(format!(
            "`{}` is not a duration: use 30m, 1h, 3d, 2w or perm",
            escape(text)
        )),
    }
}

/// (year, month, day, hour, minute, second) in UTC, proleptic Gregorian.
pub fn civil(unix: i64) -> (i64, u32, u32, u32, u32, u32) {
    let (days, secs) = (unix.div_euclid(86_400), unix.rem_euclid(86_400));
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let year = yoe + era * 400 + i64::from(month <= 2);
    let secs = secs as u32;
    (year, month, day, secs / 3600, secs / 60 % 60, secs % 60)
}

/// `YYYY-MM-DDTHH:MM:SSZ`, what the admin API takes for `until`.
pub fn rfc3339(unix: i64) -> String {
    let (y, mo, d, h, mi, s) = civil(unix);
    format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}Z")
}

/// An admin API time (`2026-10-31T00:18:28Z`) as people read it: `2026-10-31 00:18 UTC`.
pub fn when(rfc3339: &str) -> String {
    match (rfc3339.get(..10), rfc3339.get(11..16)) {
        (Some(date), Some(time)) if rfc3339.as_bytes().get(10) == Some(&b'T') => {
            format!("{date} {time} UTC")
        }
        _ => escape(rfc3339),
    }
}

/// `1d 2h`, `3h 4m`, `5m`, `12s`: the two largest units.
pub fn uptime(seconds: u64) -> String {
    let (d, h, m) = (seconds / 86_400, seconds / 3600 % 24, seconds / 60 % 60);
    match (d, h, m) {
        (0, 0, 0) => format!("{seconds}s"),
        (0, 0, m) => format!("{m}m"),
        (0, h, m) => format!("{h}h {m}m"),
        (d, h, _) => format!("{d}d {h}h"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escapes_markdown_and_controls() {
        assert_eq!(escape("**bold** _x_"), r"\*\*bold\*\* \_x\_");
        assert_eq!(escape("[link](http://x)"), r"\[link\]\(http\://x\)");
        assert_eq!(escape("@everyone <@1>"), r"\@everyone \<\@1\>");
        assert_eq!(escape("> quote\n# head"), r"\> quote \# head");
        assert_eq!(escape("Nelly"), "Nelly");
    }

    #[test]
    fn fits_the_message_limit() {
        assert_eq!(fit("short".into()), "short");
        let long = "é".repeat(3000);
        let cut = fit(long);
        assert_eq!(cut.chars().count(), MESSAGE_LIMIT);
        assert!(cut.ends_with('…'));
    }

    #[test]
    fn durations() {
        assert_eq!(duration("perm"), Ok(None));
        assert_eq!(duration(""), Ok(None));
        assert_eq!(duration("30m"), Ok(Some(1800)));
        assert_eq!(duration("1h"), Ok(Some(3600)));
        assert_eq!(duration("3D"), Ok(Some(259_200)));
        assert_eq!(duration("2w"), Ok(Some(1_209_600)));
        for bad in ["0h", "-1d", "1y", "h", "1.5h", "99999w"] {
            assert!(duration(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn times() {
        assert_eq!(rfc3339(1_793_405_908), "2026-10-31T00:18:28Z");
        assert_eq!(rfc3339(0), "1970-01-01T00:00:00Z");
        assert_eq!(rfc3339(951_782_400), "2000-02-29T00:00:00Z");
        assert_eq!(when("2026-10-31T00:18:28Z"), "2026-10-31 00:18 UTC");
        assert_eq!(when("soon"), "soon");
        assert_eq!(uptime(12), "12s");
        assert_eq!(uptime(3 * 3600 + 4 * 60), "3h 4m");
        assert_eq!(uptime(86_400 + 2 * 3600 + 59), "1d 2h");
    }
}
