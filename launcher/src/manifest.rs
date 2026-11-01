//! Release manifest — the normative shape is in `specs/04-launcher.md`.
//!
//! Everything the Launcher knows about "latest" comes from one `manifest.json` on a
//! GitHub Release. Content is delivered per file from a content-addressed store.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Manifest schema version this launcher understands.
pub const SCHEMA: u32 = 1;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Manifest {
    pub schema: u32,
    pub release: String,
    pub published_at: String,
    pub realm: Realm,
    pub launcher: Launcher,
    pub client: Client,
    pub content: Content,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Realm {
    pub id: String,
    pub name: String,
    pub host: String,
    pub port: u16,
    /// Discord OAuth2 application id. Per realm; never compiled into the client.
    pub discord_client_id: String,
    #[serde(default)]
    pub news_url: Option<String>,
    /// Spec 12: the WebSocket edge the game wire goes through (`wss://…`); absent
    /// for TCP to `host:port`. Passed to the client in `realm.json`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub edge: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Launcher {
    pub version: String,
    /// A launcher older than this must self-update before doing anything else.
    pub min_version: String,
    pub artifacts: BTreeMap<String, Artifact>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Client {
    pub version: String,
    pub artifacts: BTreeMap<String, Artifact>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Artifact {
    pub url: String,
    pub sha256: String,
    pub size: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Content {
    pub game: String,
    /// Package identity: `sha256(release.bin)`, hex. What the game-wire `Handshake` carries.
    pub hash: String,
    pub index_url: String,
    pub index_sha256: String,
    /// Files are fetched from `base_url + sha256`.
    pub base_url: String,
}

/// `content-<hash>.index.json`: the per-file list of one immutable package.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ContentIndex {
    pub schema: u32,
    pub hash: String,
    pub files: Vec<IndexFile>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IndexFile {
    pub path: String,
    pub sha256: String,
    pub size: u64,
}

/// Platform key for this build, matching the manifest's artifact maps.
pub const fn platform() -> &'static str {
    if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
        "linux-x86_64"
    } else if cfg!(all(target_os = "windows", target_arch = "x86_64")) {
        "windows-x86_64"
    } else {
        "unsupported"
    }
}

/// A version names a directory: letters, digits, `.`, `-`, `_`, at most 64, not
/// starting with `.`.
pub fn valid_version(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 64
        && !v.starts_with('.')
        && v.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-' || b == b'_')
}

/// Whether version `a` is newer than `b`: dot-separated numeric parts compared as
/// numbers (`0.10.0` > `0.9.1`), anything after a `-` compared as text.
pub fn newer(a: &str, b: &str) -> bool {
    fn key(v: &str) -> (Vec<u64>, &str) {
        let (numbers, rest) = v.split_once('-').unwrap_or((v, ""));
        let parts = numbers
            .split('.')
            .map(|p| p.parse::<u64>().unwrap_or(0))
            .collect();
        (parts, rest)
    }
    let (na, ra) = key(a);
    let (nb, rb) = key(b);
    let len = na.len().max(nb.len());
    let pad = |n: &Vec<u64>| {
        let mut n = n.clone();
        n.resize(len, 0);
        n
    };
    (pad(&na), ra) > (pad(&nb), rb)
}

/// The schema a manifest declares, read before the rest is trusted to parse.
pub fn schema_of(bytes: &[u8]) -> Option<u64> {
    serde_json::from_slice::<serde_json::Value>(bytes)
        .ok()?
        .get("schema")?
        .as_u64()
}

#[derive(Debug, PartialEq)]
pub enum IndexError {
    UnsafePath(String),
    BadHash(String),
}

impl std::fmt::Display for IndexError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnsafePath(p) => write!(f, "path is not relative or escapes the package: {p}"),
            Self::BadHash(h) => write!(f, "sha256 is not 64 hex chars: {h}"),
        }
    }
}

impl std::error::Error for IndexError {}

impl ContentIndex {
    /// Reject anything that could write outside the assembled package directory.
    pub fn validate(&self) -> Result<(), IndexError> {
        if self.hash.len() != 64 || !self.hash.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err(IndexError::BadHash(self.hash.clone()));
        }
        for f in &self.files {
            let p = std::path::Path::new(&f.path);
            let unsafe_component = p
                .components()
                .any(|c| !matches!(c, std::path::Component::Normal(_)));
            if f.path.is_empty() || f.path.contains('\\') || unsafe_component {
                return Err(IndexError::UnsafePath(f.path.clone()));
            }
            if f.sha256.len() != 64 || !f.sha256.chars().all(|c| c.is_ascii_hexdigit()) {
                return Err(IndexError::BadHash(f.sha256.clone()));
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const EXAMPLE: &str = r#"{
      "schema": 1,
      "release": "2026.10.30-abc1234",
      "published_at": "2026-10-30T05:00:00Z",
      "realm": { "id": "n3e-realm", "name": "N3E Realm", "host": "play.example.org",
                 "port": 7777, "discord_client_id": "123456789012345678" },
      "launcher": { "version": "0.3.1", "min_version": "0.3.0",
        "artifacts": { "linux-x86_64": { "url": "u", "sha256": "s", "size": 4194304 } } },
      "client": { "version": "2026.10.30-abc1234",
        "artifacts": { "linux-x86_64": { "url": "u", "sha256": "s", "size": 0 } } },
      "content": { "game": "moradon",
        "hash": "0000000000000000000000000000000000000000000000000000000000000000",
        "index_url": "i", "index_sha256": "s", "base_url": "b/" }
    }"#;

    #[test]
    fn parses_spec_example() {
        let m: Manifest = serde_json::from_str(EXAMPLE).unwrap();
        assert_eq!(m.schema, SCHEMA);
        assert_eq!(m.realm.port, 7777);
        assert!(m.client.artifacts.contains_key("linux-x86_64"));
        assert!(m.realm.news_url.is_none());
        assert!(m.realm.edge.is_none());
    }

    fn index(path: &str) -> ContentIndex {
        ContentIndex {
            schema: 1,
            hash: "a".repeat(64),
            files: vec![IndexFile {
                path: path.into(),
                sha256: "b".repeat(64),
                size: 1,
            }],
        }
    }

    #[test]
    fn versions() {
        assert!(newer("0.3.1", "0.3.0"));
        assert!(newer("0.10.0", "0.9.9"));
        assert!(newer("1.0", "0.99.99"));
        assert!(!newer("0.3.0", "0.3.0"));
        assert!(!newer("0.3", "0.3.0"));
        assert!(newer("2026.10.31-a", "2026.10.30-z"));
        assert!(valid_version("2026.10.30-abc1234"));
        for bad in ["", ".hidden", "a/b", "../x", "a b"] {
            assert!(!valid_version(bad), "{bad}");
        }
        assert_eq!(schema_of(br#"{"schema": 2, "anything": []}"#), Some(2));
        assert_eq!(schema_of(b"[]"), None);
    }

    #[test]
    fn index_rejects_escapes() {
        assert!(index("release.bin").validate().is_ok());
        assert!(index("assets/x.bin").validate().is_ok());
        assert!(index("../x").validate().is_err());
        assert!(index("/abs").validate().is_err());
        assert!(index("a\\b").validate().is_err());
        assert!(index("").validate().is_err());
    }
}
