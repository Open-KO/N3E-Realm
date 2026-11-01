//! One launcher run (spec 04 "Behaviour"): pick the realm, fetch its manifest,
//! update the launcher (re-exec) or the client and content, commit, prune, start the
//! client and map its exit code.

use crate::install::{self, applied_manifest, State};
use crate::manifest::{newer, platform, schema_of, valid_version, Manifest, SCHEMA};
use crate::net::{Failure, Fetched, Net, MANIFEST_LIMIT};
use crate::paths::{Dirs, CLIENT, LAUNCHER};
use crate::profiles::{valid_name, Profiles};
use crate::VERSION;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Exit codes (spec 04 "CLI").
pub const OK: i32 = 0;
pub const USAGE: i32 = 2;
pub const NETWORK: i32 = 10;
pub const VERIFY: i32 = 11;
pub const SCHEMA_UNSUPPORTED: i32 = 12;
pub const REALM_AHEAD: i32 = 20;
/// The client's "update required" (spec 04, Q10).
pub const CLIENT_UPDATE: i32 = 3;

/// Set on the process a self-update re-executes, so it never updates itself twice.
const REEXEC: &str = "N3E_LAUNCHER_REEXEC";
/// Set where a re-exec is a child process (Windows): the parent holds the lock.
const LOCK_HELD: &str = "N3E_LAUNCHER_LOCK_HELD";

#[derive(Debug, Default, Clone, PartialEq)]
pub struct Options {
    pub realm: Option<String>,
    pub check: bool,
    pub no_update: bool,
    pub no_start: bool,
    pub add_realm: Option<(String, String)>,
    pub manifest: Option<String>,
    pub ca: Option<PathBuf>,
    /// KO's window sizes (spec 04); the client opens at 1280x1024 without one.
    pub window: Option<String>,
    pub fullscreen: bool,
}

/// The window sizes KO is drawn for.
pub const WINDOW_SIZES: [&str; 3] = ["1024x768", "1280x1024", "1600x1200"];

pub fn parse(args: &[String]) -> Result<Options, String> {
    let mut o = Options::default();
    let mut i = 0;
    let value = |i: usize, flag: &str| {
        args.get(i + 1)
            .cloned()
            .ok_or_else(|| format!("{flag} needs a value"))
    };
    while i < args.len() {
        match args[i].as_str() {
            "--realm" => {
                o.realm = Some(value(i, "--realm")?);
                i += 1;
            }
            "--check" => o.check = true,
            "--no-update" => o.no_update = true,
            "--no-start" => o.no_start = true,
            "--add-realm" => {
                let name = value(i, "--add-realm")?;
                let url = value(i + 1, "--add-realm NAME")?;
                o.add_realm = Some((name, url));
                i += 2;
            }
            "--manifest" => {
                o.manifest = Some(value(i, "--manifest")?);
                i += 1;
            }
            "--ca" => {
                o.ca = Some(PathBuf::from(value(i, "--ca")?));
                i += 1;
            }
            "--fixed-window" => {
                let size = value(i, "--fixed-window")?;
                if !WINDOW_SIZES.contains(&size.as_str()) {
                    return Err(format!(
                        "--fixed-window is one of {}",
                        WINDOW_SIZES.join(", ")
                    ));
                }
                o.window = Some(size);
                i += 1;
            }
            "--fullscreen" => o.fullscreen = true,
            other => return Err(format!("unknown argument `{other}`")),
        }
        i += 1;
    }
    if o.realm.is_some() && o.manifest.is_some() {
        return Err("--realm and --manifest are alternatives".into());
    }
    Ok(o)
}

/// Where a player downloads the launcher by hand: the Releases page of a GitHub
/// manifest URL, else the manifest URL itself.
pub fn releases_url(manifest: &str) -> String {
    match manifest.find("/releases/") {
        Some(i) => format!("{}/releases/latest", &manifest[..i]),
        None => manifest.to_string(),
    }
}

fn check_manifest(m: &Manifest) -> Result<(), String> {
    if !valid_name(&m.realm.id) {
        return Err(format!("realm id `{}` is not a valid name", m.realm.id));
    }
    if !valid_version(&m.client.version) || !valid_version(&m.launcher.version) {
        return Err("a version in the manifest is not a valid name".into());
    }
    let hex64 = |h: &str| h.len() == 64 && h.bytes().all(|b| b.is_ascii_hexdigit());
    if !hex64(&m.content.hash) || !hex64(&m.content.index_sha256) {
        return Err("content.hash and content.index_sha256 must be sha256 hex".into());
    }
    if !m.client.artifacts.contains_key(platform()) {
        return Err(format!("the release has no client for {}", platform()));
    }
    for url in [&m.content.index_url, &m.content.base_url] {
        crate::net::check_url(url)?;
    }
    Ok(())
}

/// The installed launcher `current` points at: (version, executable).
pub fn installed_launcher(dirs: &Dirs) -> Option<(String, PathBuf)> {
    let current = dirs.launchers().join("current");
    let version = if cfg!(unix) {
        let target = std::fs::read_link(&current).ok()?;
        target.parent()?.file_name()?.to_str()?.to_string()
    } else {
        std::fs::read_to_string(&current).ok()?.trim().to_string()
    };
    let exe = dirs.launchers().join(&version).join(LAUNCHER);
    (valid_version(&version) && exe.is_file()).then_some((version, exe))
}

/// Replaces this process with `exe` and the same arguments (a new process on Windows,
/// whose exit code becomes ours). Returns only if that failed.
fn reexec(exe: &Path) -> Result<i32, String> {
    let mut cmd = Command::new(exe);
    cmd.args(std::env::args_os().skip(1)).env(REEXEC, "1");
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        let e = cmd.exec();
        Err(format!("cannot start {}: {e}", exe.display()))
    }
    #[cfg(not(unix))]
    {
        cmd.env(LOCK_HELD, "1");
        let status = cmd
            .status()
            .map_err(|e| format!("cannot start {}: {e}", exe.display()))?;
        Ok(status.code().unwrap_or(1))
    }
}

/// Step 3: the manifest's launcher into `launcher/<version>/`, checked with
/// `--version`, then `current` swapped to it.
fn self_update(net: &Net, dirs: &Dirs, m: &Manifest) -> Result<PathBuf, Failure> {
    let v = &m.launcher.version;
    let artifact = m.launcher.artifacts.get(platform()).ok_or_else(|| {
        Failure::Verify(format!("the release has no launcher for {}", platform()))
    })?;
    let dir = dirs.launchers().join(v);
    let exe = dir.join(LAUNCHER);
    if !exe.is_file() {
        println!("Updating the launcher to {v}");
        let download = dirs
            .downloads()
            .join(format!("launcher-{}", artifact.sha256));
        net.download(&artifact.url, artifact.size, &artifact.sha256, &download)?;
        let staging = dirs
            .launchers()
            .join(format!(".{v}.tmp-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&staging);
        let placed = std::fs::create_dir_all(&staging)
            .and_then(|()| crate::paths::place(&download, &staging.join(LAUNCHER)))
            .and_then(|()| executable(&staging.join(LAUNCHER)))
            .and_then(|()| std::fs::rename(&staging, &dir));
        let _ = std::fs::remove_dir_all(&staging);
        placed.map_err(|e| Failure::Verify(format!("{}: {e}", dir.display())))?;
    }
    let runs = Command::new(&exe)
        .arg("--version")
        .env_remove(REEXEC)
        .output()
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .is_some_and(|out| out.starts_with(&format!("realm-launcher {v} ")));
    if !runs {
        let _ = std::fs::remove_dir_all(&dir);
        return Err(Failure::Verify(format!(
            "the downloaded launcher {v} does not run"
        )));
    }
    swap_current(dirs, v).map_err(|e| Failure::Verify(format!("launcher/current: {e}")))?;
    Ok(exe)
}

fn executable(path: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755))
    }
    #[cfg(not(unix))]
    {
        let _ = path;
        Ok(())
    }
}

fn swap_current(dirs: &Dirs, version: &str) -> std::io::Result<()> {
    let current = dirs.launchers().join("current");
    #[cfg(unix)]
    {
        let tmp = dirs
            .launchers()
            .join(format!(".current.tmp-{}", std::process::id()));
        let _ = std::fs::remove_file(&tmp);
        std::os::unix::fs::symlink(Path::new(version).join(LAUNCHER), &tmp)?;
        std::fs::rename(&tmp, &current)
    }
    #[cfg(not(unix))]
    {
        crate::paths::write_atomic(&current, version.as_bytes())
    }
}

/// Steps 4-5: whatever of the client and content is not installed yet.
fn apply(net: &Net, dirs: &Dirs, m: &Manifest) -> Result<(), Failure> {
    if !install::client_installed(dirs, &m.client.version) {
        install::install_client(
            net,
            dirs,
            &m.client.version,
            &m.client.artifacts[platform()],
        )?;
    }
    if !dirs
        .content(&m.realm.id, &m.content.hash)
        .join("release.bin")
        .is_file()
    {
        let index = install::fetch_index(net, &m.content)?;
        install::install_content(net, dirs, &m.realm.id, &m.content, &index)?;
    }
    Ok(())
}

/// `--check`: what a run would change; 0 when nothing.
fn plan(net: &Net, dirs: &Dirs, m: &Manifest) -> i32 {
    let mut changes = 0;
    if newer(&m.launcher.version, VERSION) {
        println!("launcher: {VERSION} -> {}", m.launcher.version);
        changes += 1;
    } else {
        println!("launcher: {VERSION}, up to date");
    }
    if install::client_installed(dirs, &m.client.version) {
        println!("client: {}, installed", m.client.version);
    } else {
        let a = &m.client.artifacts[platform()];
        println!(
            "client: {} to download ({:.1} MB)",
            m.client.version,
            a.size as f64 / 1e6
        );
        changes += 1;
    }
    if dirs
        .content(&m.realm.id, &m.content.hash)
        .join("release.bin")
        .is_file()
    {
        println!("content: {}, installed", &m.content.hash[..12]);
    } else {
        match install::fetch_index(net, &m.content) {
            Ok(index) => {
                let todo = install::missing(dirs, &index);
                let bytes: u64 = todo.iter().map(|f| f.size).sum();
                println!(
                    "content: {}, {} of {} files to download ({:.1} MB)",
                    &m.content.hash[..12],
                    todo.len(),
                    index.files.len(),
                    bytes as f64 / 1e6
                );
            }
            Err(Failure::Network(e)) => {
                eprintln!("content: cannot fetch the index: {e}");
                return NETWORK;
            }
            Err(Failure::Verify(e)) => {
                eprintln!("content: {e}");
                return VERIFY;
            }
        }
        changes += 1;
    }
    i32::from(changes > 0)
}

/// Step 8: the client, with the content directory, realm config and window.
fn start(dirs: &Dirs, m: &Manifest, o: &Options) -> i32 {
    let exe = dirs.client(&m.client.version).join(CLIENT);
    let mut cmd = Command::new(&exe);
    cmd.arg(dirs.content(&m.realm.id, &m.content.hash))
        .arg("--realm")
        .arg(install::realm_json(dirs, m))
        .env_remove(REEXEC)
        .env_remove(LOCK_HELD);
    if let Some(ca) = &o.ca {
        cmd.arg("--ca").arg(ca);
    }
    if o.window.is_some() || o.fullscreen {
        cmd.arg("--fixed-window")
            .arg(o.window.as_deref().unwrap_or(WINDOW_SIZES[1]));
    }
    if o.fullscreen {
        cmd.arg("--fullscreen");
    }
    println!("Starting {} (client {})", m.realm.name, m.client.version);
    match cmd.status() {
        Ok(status) => match status.code() {
            Some(code) => code,
            None => {
                #[cfg(unix)]
                {
                    use std::os::unix::process::ExitStatusExt;
                    128 + status.signal().unwrap_or(0)
                }
                #[cfg(not(unix))]
                1
            }
        },
        Err(e) => {
            eprintln!("cannot start the client {}: {e}", exe.display());
            VERIFY
        }
    }
}

/// Holds `data/lock` for the life of the process; `None` if another launcher has it.
fn lock(dirs: &Dirs) -> Result<bool, String> {
    if std::env::var_os(LOCK_HELD).is_some() {
        return Ok(true);
    }
    std::fs::create_dir_all(&dirs.data).map_err(|e| format!("{}: {e}", dirs.data.display()))?;
    let file = std::fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(dirs.lock())
        .map_err(|e| format!("{}: {e}", dirs.lock().display()))?;
    let lock: &'static mut fd_lock::RwLock<std::fs::File> =
        Box::leak(Box::new(fd_lock::RwLock::new(file)));
    match lock.try_write() {
        Ok(guard) => {
            // Released when the process exits (or execs: the descriptor is close-on-exec).
            std::mem::forget(guard);
            Ok(true)
        }
        Err(_) => Ok(false),
    }
}

pub fn run(o: Options) -> i32 {
    let dirs = match Dirs::from_env() {
        Ok(d) => d,
        Err(e) => {
            eprintln!("realm-launcher: {e}");
            return USAGE;
        }
    };
    let mut profiles = match Profiles::load(&dirs.profiles()) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("realm-launcher: {e}");
            return USAGE;
        }
    };
    if let Some((name, url)) = &o.add_realm {
        if let Err(e) = profiles
            .add(name, url)
            .and_then(|()| profiles.save(&dirs.profiles()))
        {
            eprintln!("realm-launcher: {e}");
            return USAGE;
        }
        println!("Added realm `{name}`: realm-launcher --realm {name}");
        return OK;
    }
    if !o.check {
        match lock(&dirs) {
            Ok(true) => {}
            Ok(false) => {
                println!("realm-launcher is already running");
                return OK;
            }
            Err(e) => {
                eprintln!("realm-launcher: {e}");
                return VERIFY;
            }
        }
    }
    let reexecuted = std::env::var_os(REEXEC).is_some();
    // A newer launcher installed earlier takes over from an older copy run by hand.
    if !reexecuted {
        if let Some((v, exe)) = installed_launcher(&dirs) {
            if newer(&v, VERSION) {
                match reexec(&exe) {
                    Ok(code) => return code,
                    Err(e) => eprintln!("warning: {e}; carrying on with {VERSION}"),
                }
            }
        }
    }
    let (profile, url) = match &o.manifest {
        Some(url) => (None, url.clone()),
        None => {
            let name = o.realm.clone().unwrap_or_else(|| profiles.default.clone());
            match profiles.realms.get(&name) {
                Some(p) => (Some(name), p.manifest.clone()),
                None => {
                    eprintln!("realm-launcher: no realm profile `{name}` (add one with --add-realm NAME URL)");
                    return USAGE;
                }
            }
        }
    };
    let releases = releases_url(&url);
    // What is installed is known for a profile pinned to a realm id.
    let known = profile.as_ref().and_then(|p| profiles.realms[p].id.clone());
    let state = known
        .as_ref()
        .map(|id| State::load(&dirs, id))
        .unwrap_or_default();
    let saved = known
        .as_ref()
        .filter(|id| state.usable(&dirs, id).is_some())
        .and_then(|id| applied_manifest(&dirs, id));
    let net = Net::new();

    let (manifest, etag) = if o.no_update {
        match saved {
            Some(m) => (m, state.etag.clone()),
            None => {
                eprintln!("realm-launcher: nothing is installed for this realm yet; run without --no-update");
                return NETWORK;
            }
        }
    } else {
        let etag = saved.as_ref().and(state.etag.as_deref());
        match net.fetch(&url, etag, MANIFEST_LIMIT) {
            Ok(Fetched::NotModified) => (
                saved
                    .clone()
                    .expect("an etag is sent only with a saved manifest"),
                state.etag.clone(),
            ),
            Ok(Fetched::Body { bytes, etag }) => match read_manifest(&bytes, &releases) {
                Ok(m) => (m, etag),
                Err(code) => return code,
            },
            Err(Failure::Network(e)) => match saved {
                Some(m) if !o.check => {
                    eprintln!("warning: cannot reach the realm's releases ({e}); starting what is installed");
                    (m, state.etag.clone())
                }
                _ => {
                    eprintln!("realm-launcher: cannot reach the realm's releases: {e}\nDownloads: {releases}");
                    return NETWORK;
                }
            },
            Err(Failure::Verify(e)) => {
                eprintln!("realm-launcher: {e}");
                return VERIFY;
            }
        }
    };
    if let Some(name) = &profile {
        match profiles.pin(name, &manifest.realm.id) {
            Ok(true) if !o.check => {
                if let Err(e) = profiles.save(&dirs.profiles()) {
                    eprintln!("realm-launcher: {e}");
                    return VERIFY;
                }
            }
            Ok(_) => {}
            Err(e) => {
                eprintln!("realm-launcher: {e}");
                return VERIFY;
            }
        }
    }
    if o.check {
        return plan(&net, &dirs, &manifest);
    }

    // Steps 1 and 3: the launcher first, then a fresh process for everything else.
    let too_old = newer(&manifest.launcher.min_version, VERSION);
    if newer(&manifest.launcher.version, VERSION) && !reexecuted && !o.no_update {
        let failed = match self_update(&net, &dirs, &manifest) {
            Ok(exe) => match reexec(&exe) {
                Ok(code) => return code,
                Err(e) => e,
            },
            Err(e) => e.to_string(),
        };
        if too_old {
            eprintln!(
                "realm-launcher: this launcher ({VERSION}) is older than the realm allows ({}) and could not update itself: {failed}\n\
                 Download the launcher again: {releases}",
                manifest.launcher.min_version
            );
            return VERIFY;
        }
        eprintln!(
            "warning: the launcher could not update itself ({failed}); carrying on with {VERSION}"
        );
    } else if too_old {
        eprintln!(
            "realm-launcher: this launcher ({VERSION}) is older than the realm allows ({}).\n\
             Download the launcher again: {releases}",
            manifest.launcher.min_version
        );
        return VERIFY;
    }

    let mut manifest = manifest;
    let mut etag = etag;
    let mut state = State::load(&dirs, &manifest.realm.id);
    let mut retried = false;
    loop {
        if !o.no_update {
            match apply(&net, &dirs, &manifest) {
                Ok(()) => {}
                Err(Failure::Network(e)) => {
                    let Some(m) = applied_manifest(&dirs, &manifest.realm.id)
                        .filter(|_| state.usable(&dirs, &manifest.realm.id).is_some())
                    else {
                        eprintln!("realm-launcher: {e}\nDownloads: {releases}");
                        return NETWORK;
                    };
                    eprintln!(
                        "warning: could not download the update ({e}); starting what is installed"
                    );
                    manifest = m;
                    etag = state.etag.clone();
                }
                Err(Failure::Verify(e)) => {
                    eprintln!("realm-launcher: verification failed: {e}\nNothing was changed.");
                    return VERIFY;
                }
            }
            if let Err(e) = install::commit(&dirs, &manifest, &mut state, etag.clone()) {
                eprintln!("realm-launcher: {e}");
                return VERIFY;
            }
            if let Err(e) = install::prune(&dirs) {
                eprintln!("warning: pruning old versions: {e}");
            }
        }
        if o.no_start {
            return OK;
        }
        let code = start(&dirs, &manifest, &o);
        if code != CLIENT_UPDATE || retried {
            if code == CLIENT_UPDATE {
                eprintln!("realm-launcher: the client still does not match the realm after updating. {AHEAD}");
                return REALM_AHEAD;
            }
            return code;
        }
        // The realm wants another release: fetch the manifest once more.
        retried = true;
        let fresh = match net.fetch(&url, None, MANIFEST_LIMIT) {
            Ok(Fetched::Body { bytes, etag: tag }) => {
                read_manifest(&bytes, &releases).ok().map(|m| (m, tag))
            }
            _ => None,
        };
        match fresh {
            Some((m, tag))
                if m.realm.id == manifest.realm.id
                    && (m.client.version != manifest.client.version
                        || m.content.hash != manifest.content.hash) =>
            {
                if newer(&m.launcher.version, VERSION) && !reexecuted {
                    if let Ok(exe) = self_update(&net, &dirs, &m) {
                        if let Ok(code) = reexec(&exe) {
                            return code;
                        }
                    }
                }
                println!("The realm has a new release ({}); updating", m.release);
                manifest = m;
                etag = tag;
            }
            _ => {
                eprintln!("realm-launcher: the realm refused this client and no newer release is published. {AHEAD}");
                return REALM_AHEAD;
            }
        }
    }
}

const AHEAD: &str = "The realm is ahead of its Releases: a CD ordering bug (the realm restarted before the release was published). Try again later.";

fn read_manifest(bytes: &[u8], releases: &str) -> Result<Manifest, i32> {
    match schema_of(bytes) {
        Some(s) if s == u64::from(SCHEMA) => {}
        Some(s) => {
            eprintln!("realm-launcher: the realm's manifest is schema {s}; this launcher reads {SCHEMA}. Update the launcher manually: {releases}");
            return Err(SCHEMA_UNSUPPORTED);
        }
        None => {
            eprintln!("realm-launcher: the realm's manifest is not a manifest");
            return Err(VERIFY);
        }
    }
    let m: Manifest = serde_json::from_slice(bytes).map_err(|e| {
        eprintln!("realm-launcher: the realm's manifest: {e}");
        VERIFY
    })?;
    check_manifest(&m).map_err(|e| {
        eprintln!("realm-launcher: the realm's manifest: {e}");
        VERIFY
    })?;
    Ok(m)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(a: &[&str]) -> Vec<String> {
        a.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn cli() {
        assert_eq!(parse(&[]).unwrap(), Options::default());
        let o = parse(&args(&[
            "--realm",
            "my-fork",
            "--no-start",
            "--ca",
            "/x/ca.pem",
        ]))
        .unwrap();
        assert_eq!(o.realm.as_deref(), Some("my-fork"));
        assert!(o.no_start && o.ca == Some(PathBuf::from("/x/ca.pem")));
        let o = parse(&args(&["--add-realm", "f", "https://e/m.json"])).unwrap();
        assert_eq!(o.add_realm, Some(("f".into(), "https://e/m.json".into())));
        assert!(parse(&args(&["--realm"])).is_err());
        assert!(parse(&args(&["--bogus"])).is_err());
        assert!(parse(&args(&["--realm", "a", "--manifest", "https://e/m.json"])).is_err());
        let o = parse(&args(&["--fixed-window", "1024x768", "--fullscreen"])).unwrap();
        assert!(o.window.as_deref() == Some("1024x768") && o.fullscreen);
        assert!(parse(&args(&["--fixed-window", "1280x800"])).is_err());
        assert!(parse(&args(&["--fixed-window"])).is_err());
    }

    #[test]
    fn releases_page() {
        assert_eq!(
            releases_url(
                "https://github.com/Open-KO/N3E-Realm/releases/latest/download/manifest.json"
            ),
            "https://github.com/Open-KO/N3E-Realm/releases/latest"
        );
        assert_eq!(releases_url("https://e.org/m.json"), "https://e.org/m.json");
    }
}
