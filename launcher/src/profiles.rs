//! Realm profiles (spec 04 "Realm profiles"): `realms.json` names manifest URLs; a
//! profile's realm id is pinned on first use, so a hijacked URL cannot re-point it.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::Path;

/// The default profile's name and manifest. A fork builds with its own
/// (`REALM_DEFAULT_MANIFEST` at compile time).
pub const DEFAULT_NAME: &str = "n3e-realm";
pub const DEFAULT_MANIFEST: &str = match option_env!("REALM_DEFAULT_MANIFEST") {
    Some(url) => url,
    None => "https://github.com/Open-KO/N3E-Realm/releases/latest/download/manifest.json",
};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Profile {
    pub manifest: String,
    /// The manifest's `realm.id`, recorded the first time it is applied.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Profiles {
    pub default: String,
    pub realms: BTreeMap<String, Profile>,
}

impl Default for Profiles {
    fn default() -> Self {
        Self {
            default: DEFAULT_NAME.into(),
            realms: BTreeMap::from([(
                DEFAULT_NAME.into(),
                Profile {
                    manifest: DEFAULT_MANIFEST.into(),
                    id: None,
                },
            )]),
        }
    }
}

/// A realm or profile name: lower-case letters, digits and `-`, at most 64. It names
/// directories, so nothing that could leave one.
pub fn valid_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        && !name.starts_with('-')
}

impl Profiles {
    pub fn load(path: &Path) -> Result<Self, String> {
        match std::fs::read(path) {
            Ok(bytes) => serde_json::from_slice(&bytes)
                .map_err(|e| format!("{} is not a realm profile file: {e}", path.display())),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Self::default()),
            Err(e) => Err(format!("cannot read {}: {e}", path.display())),
        }
    }

    pub fn save(&self, path: &Path) -> Result<(), String> {
        let text = serde_json::to_vec_pretty(self).expect("profiles serialise");
        crate::paths::write_atomic(path, &text)
            .map_err(|e| format!("cannot write {}: {e}", path.display()))
    }

    pub fn add(&mut self, name: &str, manifest: &str) -> Result<(), String> {
        if !valid_name(name) {
            return Err(format!(
                "`{name}` is not a realm name (lower-case letters, digits, -)"
            ));
        }
        crate::net::check_url(manifest)?;
        self.realms.insert(
            name.into(),
            Profile {
                manifest: manifest.into(),
                id: None,
            },
        );
        Ok(())
    }

    /// Records `id` for `name` on first use; refuses a different one afterwards.
    pub fn pin(&mut self, name: &str, id: &str) -> Result<bool, String> {
        let profile = self
            .realms
            .get_mut(name)
            .ok_or_else(|| format!("no realm profile `{name}`"))?;
        match &profile.id {
            Some(pinned) if pinned == id => Ok(false),
            Some(pinned) => Err(format!(
                "the manifest for `{name}` now names realm `{id}`, but this profile is pinned to `{pinned}`; \
                 refusing it (if the realm really moved, remove the profile and add it again)"
            )),
            None => {
                profile.id = Some(id.into());
                Ok(true)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names() {
        for good in ["n3e-realm", "my-fork", "a", "realm2"] {
            assert!(valid_name(good), "{good}");
        }
        for bad in ["", "-x", "../x", "a/b", "A", "a b", "a.b", &"x".repeat(65)] {
            assert!(!valid_name(bad), "{bad}");
        }
    }

    #[test]
    fn default_add_and_pin() {
        let mut p = Profiles::default();
        assert_eq!(p.default, DEFAULT_NAME);
        assert!(p.realms[DEFAULT_NAME].manifest.starts_with("https://"));
        p.add("my-fork", "https://example.org/realm/manifest.json")
            .unwrap();
        assert!(p.add("../x", "https://example.org/m.json").is_err());
        assert!(p.add("plain", "http://example.org/m.json").is_err());
        assert_eq!(p.pin("my-fork", "fork-realm"), Ok(true));
        assert_eq!(p.pin("my-fork", "fork-realm"), Ok(false));
        assert!(p.pin("my-fork", "other").is_err());
        let text = serde_json::to_string(&p).unwrap();
        assert_eq!(serde_json::from_str::<Profiles>(&text).unwrap(), p);
    }
}
