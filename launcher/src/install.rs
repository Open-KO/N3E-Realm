//! Installing what a manifest names (spec 04 "Behaviour" 4-7): the client archive
//! extracted into `client/<version>/`, the content package assembled from the shared
//! content-addressed store, the realm's state committed only after both, and old
//! versions pruned.

use crate::manifest::{Artifact, Content, ContentIndex, IndexFile, Manifest, Realm};
use crate::net::{sha256_file, Failure, Net};
use crate::paths::{place, write_atomic, Dirs, CLIENT};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;

/// How many client versions and content packages a realm keeps.
pub const KEEP: usize = 2;
/// Content files downloaded at once.
pub const WIDTH: usize = 4;

/// `realms/<id>/state.json`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct State {
    #[serde(default)]
    pub installed: Option<Installed>,
    #[serde(default)]
    pub etag: Option<String>,
    #[serde(default)]
    pub last_check: Option<String>,
    /// Applied client versions and content hashes, newest first (for pruning).
    #[serde(default)]
    pub clients: Vec<String>,
    #[serde(default)]
    pub contents: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Installed {
    pub client: String,
    pub content: String,
}

impl State {
    pub fn load(dirs: &Dirs, realm: &str) -> State {
        std::fs::read(dirs.realm(realm).join("state.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default()
    }

    /// The installed versions, if their files are still where they were put.
    pub fn usable(&self, dirs: &Dirs, realm: &str) -> Option<&Installed> {
        self.installed.as_ref().filter(|i| {
            dirs.client(&i.client).join(CLIENT).is_file()
                && dirs
                    .content(realm, &i.content)
                    .join("release.bin")
                    .is_file()
        })
    }
}

/// The last manifest a realm applied.
pub fn applied_manifest(dirs: &Dirs, realm: &str) -> Option<Manifest> {
    let bytes = std::fs::read(dirs.realm(realm).join("manifest.json")).ok()?;
    serde_json::from_slice(&bytes).ok()
}

fn io(path: &Path, e: std::io::Error) -> Failure {
    Failure::Verify(format!("{}: {e}", path.display()))
}

pub fn client_installed(dirs: &Dirs, version: &str) -> bool {
    dirs.client(version).join(CLIENT).is_file()
}

/// Downloads, verifies and extracts the client archive (a `.tar.zst`). Extraction goes
/// to a temporary directory renamed into place, so a failure leaves nothing behind.
pub fn install_client(
    net: &Net,
    dirs: &Dirs,
    version: &str,
    artifact: &Artifact,
) -> Result<(), Failure> {
    if !crate::manifest::valid_version(version) {
        return Err(Failure::Verify(format!(
            "`{version}` is not a client version"
        )));
    }
    let archive = dirs.downloads().join(format!("client-{}", artifact.sha256));
    println!(
        "Downloading client {version} ({:.1} MB)",
        artifact.size as f64 / 1e6
    );
    net.download(&artifact.url, artifact.size, &artifact.sha256, &archive)?;
    let target = dirs.client(version);
    let staging = dirs
        .clients()
        .join(format!(".{version}.tmp-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&staging);
    std::fs::create_dir_all(&staging).map_err(|e| io(&staging, e))?;
    let result = extract(&archive, &staging).and_then(|()| {
        if !staging.join(CLIENT).is_file() {
            return Err(Failure::Verify(format!(
                "the client archive has no {CLIENT} at its top level"
            )));
        }
        let _ = std::fs::remove_dir_all(&target);
        std::fs::rename(&staging, &target).map_err(|e| io(&target, e))
    });
    let _ = std::fs::remove_dir_all(&staging);
    let _ = std::fs::remove_file(&archive);
    result
}

/// A `.tar.zst` into `dir`: regular files and directories only, every path relative
/// and inside `dir`.
pub fn extract(archive: &Path, dir: &Path) -> Result<(), Failure> {
    let file = std::fs::File::open(archive).map_err(|e| io(archive, e))?;
    let decoder = ruzstd::decoding::StreamingDecoder::new(std::io::BufReader::new(file))
        .map_err(|e| Failure::Verify(format!("{}: not zstd: {e}", archive.display())))?;
    let mut tar = tar::Archive::new(decoder);
    let entries = tar
        .entries()
        .map_err(|e| Failure::Verify(format!("{}: {e}", archive.display())))?;
    for entry in entries {
        let mut entry = entry.map_err(|e| Failure::Verify(format!("client archive: {e}")))?;
        let path = entry
            .path()
            .map_err(|e| Failure::Verify(format!("client archive: {e}")))?
            .into_owned();
        let kind = entry.header().entry_type();
        if !(kind.is_file() || kind.is_dir()) || !safe_relative(&path) {
            return Err(Failure::Verify(format!(
                "client archive: refusing entry {} ({kind:?})",
                path.display()
            )));
        }
        let dest = dir.join(&path);
        if kind.is_dir() {
            std::fs::create_dir_all(&dest).map_err(|e| io(&dest, e))?;
            continue;
        }
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent).map_err(|e| io(parent, e))?;
        }
        let mode = entry.header().mode().unwrap_or(0o644);
        let mut out = std::fs::File::create(&dest).map_err(|e| io(&dest, e))?;
        std::io::copy(&mut entry, &mut out).map_err(|e| io(&dest, e))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = if mode & 0o111 != 0 { 0o755 } else { 0o644 };
            std::fs::set_permissions(&dest, std::fs::Permissions::from_mode(mode))
                .map_err(|e| io(&dest, e))?;
        }
        #[cfg(not(unix))]
        let _ = mode;
    }
    Ok(())
}

fn safe_relative(path: &Path) -> bool {
    let mut normal = 0;
    for c in path.components() {
        match c {
            Component::Normal(_) => normal += 1,
            Component::CurDir => {}
            _ => return false,
        }
    }
    normal > 0
}

/// Fetches and checks a content index against the manifest.
pub fn fetch_index(net: &Net, content: &Content) -> Result<ContentIndex, Failure> {
    let bytes = match net.fetch(&content.index_url, None, crate::net::INDEX_LIMIT)? {
        crate::net::Fetched::Body { bytes, .. } => bytes,
        crate::net::Fetched::NotModified => unreachable!("no etag was sent"),
    };
    let got = crate::net::sha256_hex(&bytes);
    if got != content.index_sha256 {
        return Err(Failure::Verify(format!(
            "content index sha256 {got}, the manifest says {}",
            content.index_sha256
        )));
    }
    let index: ContentIndex = serde_json::from_slice(&bytes)
        .map_err(|e| Failure::Verify(format!("content index: {e}")))?;
    index
        .validate()
        .map_err(|e| Failure::Verify(format!("content index: {e}")))?;
    if index.hash != content.hash {
        return Err(Failure::Verify(format!(
            "content index is for package {}, the manifest says {}",
            index.hash, content.hash
        )));
    }
    let release = index.files.iter().find(|f| f.path == "release.bin");
    if release.is_none_or(|f| f.sha256 != content.hash) {
        return Err(Failure::Verify(
            "content index: release.bin missing or not the package hash".into(),
        ));
    }
    let mut paths = BTreeSet::new();
    if !index.files.iter().all(|f| paths.insert(f.path.as_str())) {
        return Err(Failure::Verify(
            "content index: a path is listed twice".into(),
        ));
    }
    Ok(index)
}

/// The index's files not yet in the store, each once.
pub fn missing<'a>(dirs: &Dirs, index: &'a ContentIndex) -> Vec<&'a IndexFile> {
    let mut seen = BTreeSet::new();
    index
        .files
        .iter()
        .filter(|f| seen.insert(f.sha256.as_str()) && !dirs.store().join(&f.sha256).is_file())
        .collect()
}

/// Downloads the missing files into the store (4 at a time), assembles
/// `content/<hash>/` from it and checks `sha256(release.bin)`.
pub fn install_content(
    net: &Net,
    dirs: &Dirs,
    realm: &str,
    content: &Content,
    index: &ContentIndex,
) -> Result<usize, Failure> {
    let todo = missing(dirs, index);
    let total: u64 = todo.iter().map(|f| f.size).sum();
    println!(
        "Downloading content {}: {} of {} files ({:.1} MB)",
        &content.hash[..12],
        todo.len(),
        index.files.len(),
        total as f64 / 1e6
    );
    let store = dirs.store();
    std::fs::create_dir_all(&store).map_err(|e| io(&store, e))?;
    let queue = Mutex::new(todo.clone());
    let failure: Mutex<Option<Failure>> = Mutex::new(None);
    std::thread::scope(|scope| {
        for _ in 0..WIDTH {
            scope.spawn(|| loop {
                if failure.lock().unwrap().is_some() {
                    return;
                }
                let Some(file) = queue.lock().unwrap().pop() else {
                    return;
                };
                let url = format!("{}{}", content.base_url, file.sha256);
                let part = dirs.downloads().join(&file.sha256);
                let result = net
                    .download(&url, file.size, &file.sha256, &part)
                    .and_then(|()| {
                        place(&part, &store.join(&file.sha256))
                            .map_err(|e| io(&store.join(&file.sha256), e))
                    });
                if let Err(e) = result {
                    failure.lock().unwrap().get_or_insert(e);
                }
            });
        }
    });
    if let Some(e) = failure.into_inner().unwrap() {
        return Err(e);
    }
    assemble(dirs, realm, content, index)?;
    Ok(todo.len())
}

fn assemble(
    dirs: &Dirs,
    realm: &str,
    content: &Content,
    index: &ContentIndex,
) -> Result<(), Failure> {
    let target = dirs.content(realm, &content.hash);
    let staging = target.with_extension(format!("tmp-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&staging);
    let result = (|| {
        for f in &index.files {
            let dest = staging.join(&f.path);
            if let Some(parent) = dest.parent() {
                std::fs::create_dir_all(parent).map_err(|e| io(parent, e))?;
            }
            let source = dirs.store().join(&f.sha256);
            if std::fs::hard_link(&source, &dest).is_err() {
                std::fs::copy(&source, &dest).map_err(|e| io(&dest, e))?;
            }
        }
        let got = sha256_file(&staging.join("release.bin"))
            .map_err(|e| io(&staging.join("release.bin"), e))?;
        if got != content.hash {
            return Err(Failure::Verify(format!(
                "assembled release.bin hashes to {got}, the manifest says {}",
                content.hash
            )));
        }
        let _ = std::fs::remove_dir_all(&target);
        std::fs::rename(&staging, &target).map_err(|e| io(&target, e))?;
        let text = serde_json::to_vec(index).expect("index serialises");
        write_atomic(&index_path(dirs, realm, &content.hash), &text).map_err(|e| io(&target, e))
    })();
    let _ = std::fs::remove_dir_all(&staging);
    result
}

fn index_path(dirs: &Dirs, realm: &str, hash: &str) -> PathBuf {
    dirs.realm(realm)
        .join("content")
        .join(format!("{hash}.index.json"))
}

/// The realm config the client reads (spec 02/04): `{id, name, host, port,
/// discord_client_id}`, and `edge` when the realm names one (spec 12).
pub fn realm_config(realm: &Realm) -> serde_json::Value {
    let mut config = serde_json::json!({
        "id": realm.id, "name": realm.name, "host": realm.host, "port": realm.port,
        "discord_client_id": realm.discord_client_id,
    });
    if let Some(edge) = &realm.edge {
        config["edge"] = edge.clone().into();
    }
    config
}

pub fn realm_json(dirs: &Dirs, manifest: &Manifest) -> PathBuf {
    dirs.realm(&manifest.realm.id).join("realm.json")
}

/// Step 6: `manifest.json`, `realm.json` and `state.json`, only after the client and
/// content are in place.
pub fn commit(
    dirs: &Dirs,
    manifest: &Manifest,
    state: &mut State,
    etag: Option<String>,
) -> Result<(), Failure> {
    let realm = &manifest.realm;
    let dir = dirs.realm(&realm.id);
    let config = realm_config(realm);
    let installed = Installed {
        client: manifest.client.version.clone(),
        content: manifest.content.hash.clone(),
    };
    for (list, value) in [
        (&mut state.clients, &installed.client),
        (&mut state.contents, &installed.content),
    ] {
        list.retain(|v| v != value);
        list.insert(0, value.clone());
    }
    state.installed = Some(installed);
    state.etag = etag;
    state.last_check = Some(crate::rfc3339_now());
    for (name, bytes) in [
        (
            "manifest.json",
            serde_json::to_vec_pretty(manifest).expect("manifest serialises"),
        ),
        (
            "realm.json",
            serde_json::to_vec_pretty(&config).expect("config serialises"),
        ),
        (
            "state.json",
            serde_json::to_vec_pretty(&*state).expect("state serialises"),
        ),
    ] {
        write_atomic(&dir.join(name), &bytes).map_err(|e| io(&dir.join(name), e))?;
    }
    Ok(())
}

/// Step 7: each realm keeps its two newest client versions and content packages; the
/// store keeps what a kept package lists; anything else goes.
pub fn prune(dirs: &Dirs) -> Result<Vec<PathBuf>, Failure> {
    let mut removed = Vec::new();
    let mut clients = BTreeSet::new();
    let mut files = BTreeSet::new();
    let realms = std::fs::read_dir(dirs.realms()).map_err(|e| io(&dirs.realms(), e))?;
    for realm in realms.flatten() {
        let Some(id) = realm.file_name().to_str().map(str::to_string) else {
            continue;
        };
        let mut state = State::load(dirs, &id);
        if state.installed.is_none() {
            continue;
        }
        state.clients.truncate(KEEP);
        state.contents.truncate(KEEP);
        clients.extend(state.clients.iter().cloned());
        let content_dir = dirs.realm(&id).join("content");
        for entry in std::fs::read_dir(&content_dir)
            .into_iter()
            .flatten()
            .flatten()
        {
            let name = entry.file_name().to_string_lossy().into_owned();
            let hash = name.trim_end_matches(".index.json");
            if !state.contents.iter().any(|c| c == hash) {
                let path = entry.path();
                let gone = if path.is_dir() {
                    std::fs::remove_dir_all(&path)
                } else {
                    std::fs::remove_file(&path)
                };
                if gone.is_ok() {
                    removed.push(path);
                }
            }
        }
        for hash in &state.contents {
            let index: Option<ContentIndex> = std::fs::read(index_path(dirs, &id, hash))
                .ok()
                .and_then(|b| serde_json::from_slice(&b).ok());
            match index {
                Some(index) => files.extend(index.files.into_iter().map(|f| f.sha256)),
                // Without its index a package's files cannot be told apart: keep the store.
                None => return Ok(removed),
            }
        }
        let text = serde_json::to_vec_pretty(&state).expect("state serialises");
        write_atomic(&dirs.realm(&id).join("state.json"), &text)
            .map_err(|e| io(&dirs.realm(&id), e))?;
    }
    for entry in std::fs::read_dir(dirs.clients())
        .into_iter()
        .flatten()
        .flatten()
    {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !clients.contains(&name)
            && !name.starts_with('.')
            && std::fs::remove_dir_all(entry.path()).is_ok()
        {
            removed.push(entry.path());
        }
    }
    for entry in std::fs::read_dir(dirs.store())
        .into_iter()
        .flatten()
        .flatten()
    {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !files.contains(&name) && std::fs::remove_file(entry.path()).is_ok() {
            removed.push(entry.path());
        }
    }
    Ok(removed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn relative_paths_only() {
        assert!(safe_relative(Path::new("n3e-client")));
        assert!(safe_relative(Path::new("./lib/x.so")));
        assert!(!safe_relative(Path::new("../x")));
        assert!(!safe_relative(Path::new("/etc/passwd")));
        assert!(!safe_relative(Path::new("a/../../x")));
        assert!(!safe_relative(Path::new(".")));
    }

    #[test]
    fn realm_config_carries_the_edge_only_when_named() {
        let mut realm = Realm {
            id: "openko".into(),
            name: "OpenKO".into(),
            host: "play.openko.net".into(),
            port: 7777,
            discord_client_id: "1".into(),
            news_url: None,
            edge: None,
        };
        assert!(realm_config(&realm).get("edge").is_none());
        realm.edge = Some("wss://play.openko.net/v1/wire".into());
        assert_eq!(
            realm_config(&realm)["edge"],
            "wss://play.openko.net/v1/wire"
        );
        assert_eq!(realm_config(&realm)["host"], "play.openko.net");
    }
}
