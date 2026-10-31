//! realm-launcher library (spec 04): manifest and index types, realm profiles, the
//! install layout, fetching and installing, and one launcher run.
pub mod install;
pub mod manifest;
pub mod net;
pub mod paths;
pub mod profiles;
pub mod run;

/// This launcher's version: CD stamps the release's (`REALM_LAUNCHER_VERSION` at
/// compile time); a local build is the crate's.
pub const VERSION: &str = match option_env!("REALM_LAUNCHER_VERSION") {
    Some(v) => v,
    None => env!("CARGO_PKG_VERSION"),
};

/// Now as `YYYY-MM-DDTHH:MM:SSZ`.
pub fn rfc3339_now() -> String {
    let s = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |d| d.as_secs() as i64);
    let (days, secs) = (s.div_euclid(86_400), s.rem_euclid(86_400));
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        secs / 3600,
        secs / 60 % 60,
        secs % 60
    )
}
