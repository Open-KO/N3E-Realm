//! Where the Launcher keeps things (spec 04 "Install layout"): XDG directories on
//! Linux, `%LOCALAPPDATA%` / `%APPDATA%` on Windows. Every path is under `n3e-realm/`.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct Dirs {
    /// `$XDG_DATA_HOME/n3e-realm`: launcher, clients, store, realms.
    pub data: PathBuf,
    /// `$XDG_CONFIG_HOME/n3e-realm`: `realms.json` (the client keeps `<realm>/session.json`).
    pub config: PathBuf,
    /// `$XDG_CACHE_HOME/n3e-realm`: partial downloads.
    pub cache: PathBuf,
}

fn var(name: &str) -> Option<PathBuf> {
    std::env::var_os(name)
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
}

impl Dirs {
    pub fn from_env() -> Result<Self, String> {
        if cfg!(windows) {
            let local = var("LOCALAPPDATA").ok_or("LOCALAPPDATA is not set")?;
            let roaming = var("APPDATA").ok_or("APPDATA is not set")?;
            let data = local.join("n3e-realm");
            return Ok(Self {
                cache: data.join("cache"),
                data,
                config: roaming.join("n3e-realm"),
            });
        }
        let home = var("HOME");
        let base = |xdg: &str, fallback: &str| {
            var(xdg)
                .or_else(|| home.as_ref().map(|h| h.join(fallback)))
                .map(|p| p.join("n3e-realm"))
                .ok_or_else(|| format!("neither {xdg} nor HOME is set"))
        };
        Ok(Self {
            data: base("XDG_DATA_HOME", ".local/share")?,
            config: base("XDG_CONFIG_HOME", ".config")?,
            cache: base("XDG_CACHE_HOME", ".cache")?,
        })
    }

    pub fn downloads(&self) -> PathBuf {
        self.cache.join("downloads")
    }
    pub fn store(&self) -> PathBuf {
        self.data.join("store")
    }
    pub fn clients(&self) -> PathBuf {
        self.data.join("client")
    }
    pub fn client(&self, version: &str) -> PathBuf {
        self.clients().join(version)
    }
    pub fn launchers(&self) -> PathBuf {
        self.data.join("launcher")
    }
    pub fn realms(&self) -> PathBuf {
        self.data.join("realms")
    }
    pub fn realm(&self, id: &str) -> PathBuf {
        self.realms().join(id)
    }
    pub fn content(&self, realm: &str, hash: &str) -> PathBuf {
        self.realm(realm).join("content").join(hash)
    }
    pub fn lock(&self) -> PathBuf {
        self.data.join("lock")
    }
    pub fn profiles(&self) -> PathBuf {
        self.config.join("realms.json")
    }
}

/// The client executable's name inside `client/<version>/`.
pub const CLIENT: &str = if cfg!(windows) {
    "n3e-client.exe"
} else {
    "n3e-client"
};

/// The launcher executable's name inside `launcher/<version>/`.
pub const LAUNCHER: &str = if cfg!(windows) {
    "realm-launcher.exe"
} else {
    "realm-launcher"
};

/// Moves `from` to `to`, copying when they are on different file systems.
pub fn place(from: &Path, to: &Path) -> std::io::Result<()> {
    if std::fs::rename(from, to).is_ok() {
        return Ok(());
    }
    let staging = to.with_extension(format!("part-{}", std::process::id()));
    std::fs::copy(from, &staging)?;
    std::fs::rename(&staging, to)?;
    std::fs::remove_file(from)
}

/// Writes `bytes` to `path` through a temporary file in the same directory.
pub fn write_atomic(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let tmp = path.with_extension(format!("tmp-{}", std::process::id()));
    std::fs::write(&tmp, bytes)?;
    std::fs::rename(&tmp, path)
}
