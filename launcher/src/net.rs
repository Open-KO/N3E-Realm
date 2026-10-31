//! HTTPS fetches (spec 04 "Behaviour" and "Security"): the operating system's trust
//! store, no pinning; every artifact checked against its size and sha256 before use;
//! downloads resumed with `Range`, retried 3 times with backoff.

use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::net::{IpAddr, ToSocketAddrs};
use std::path::Path;
use std::time::Duration;
use ureq::tls::{RootCerts, TlsConfig};
use ureq::Agent;

/// The largest manifest or content index the Launcher reads.
pub const MANIFEST_LIMIT: u64 = 1 << 20;
pub const INDEX_LIMIT: u64 = 16 << 20;

/// Why a fetch failed: the network (try again later, or run what is installed), or the
/// bytes themselves (never use them).
#[derive(Debug, Clone, PartialEq)]
pub enum Failure {
    Network(String),
    Verify(String),
}

impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Failure::Network(m) | Failure::Verify(m) => f.write_str(m),
        }
    }
}

/// A manifest or index address must be https; plain http is accepted only to this
/// machine (test realms and the suites' file servers).
pub fn check_url(url: &str) -> Result<(), String> {
    if url.starts_with("https://") {
        return Ok(());
    }
    let rest = url
        .strip_prefix("http://")
        .ok_or_else(|| format!("{url}: only https:// addresses are fetched"))?;
    let host_port = rest.split('/').next().unwrap_or("");
    let with_port = if host_port.contains(':') {
        host_port.to_string()
    } else {
        format!("{host_port}:80")
    };
    let loopback = with_port
        .to_socket_addrs()
        .map(|a| a.map(|a| a.ip()).collect::<Vec<IpAddr>>())
        .is_ok_and(|a| !a.is_empty() && a.iter().all(IpAddr::is_loopback));
    if loopback {
        Ok(())
    } else {
        Err(format!(
            "{url}: plain http is accepted only on this machine; use https://"
        ))
    }
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

pub fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    bytes
        .iter()
        .flat_map(|b| [DIGITS[usize::from(b >> 4)], DIGITS[usize::from(b & 15)]])
        .map(char::from)
        .collect()
}

/// sha256 of a file, hex.
pub fn sha256_file(path: &Path) -> std::io::Result<String> {
    let mut file = std::fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 1 << 16];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            return Ok(hex(&hasher.finalize()));
        }
        hasher.update(&buf[..n]);
    }
}

pub enum Fetched {
    NotModified,
    Body {
        bytes: Vec<u8>,
        etag: Option<String>,
    },
}

pub struct Net {
    agent: Agent,
}

impl Default for Net {
    fn default() -> Self {
        Self::new()
    }
}

impl Net {
    pub fn new() -> Self {
        let config = Agent::config_builder()
            .tls_config(
                TlsConfig::builder()
                    .root_certs(RootCerts::PlatformVerifier)
                    .build(),
            )
            .http_status_as_error(false)
            .timeout_connect(Some(Duration::from_secs(10)))
            .timeout_recv_response(Some(Duration::from_secs(30)))
            // A stalled transfer fails; a slow one does not.
            .timeout_per_read(Some(Duration::from_secs(30)))
            .user_agent(concat!("realm-launcher/", env!("CARGO_PKG_VERSION")))
            .build();
        Self {
            agent: config.into(),
        }
    }

    /// `GET url` into memory, at most `limit` bytes; with `etag`, a 304 is `NotModified`.
    pub fn fetch(&self, url: &str, etag: Option<&str>, limit: u64) -> Result<Fetched, Failure> {
        check_url(url).map_err(Failure::Verify)?;
        let mut request = self.agent.get(url);
        if let Some(tag) = etag {
            request = request.header("If-None-Match", tag);
        }
        let response = request
            .call()
            .map_err(|e| Failure::Network(format!("{url}: {e}")))?;
        let status = response.status().as_u16();
        if status == 304 && etag.is_some() {
            return Ok(Fetched::NotModified);
        }
        if status != 200 {
            return Err(Failure::Network(format!("{url}: HTTP {status}")));
        }
        let etag = response
            .headers()
            .get("etag")
            .and_then(|v| v.to_str().ok())
            .map(str::to_string);
        let bytes = response
            .into_body()
            .with_config()
            .limit(limit)
            .read_to_vec()
            .map_err(|e| Failure::Network(format!("{url}: {e}")))?;
        Ok(Fetched::Body { bytes, etag })
    }

    /// Downloads `url` to `dest`, which on success holds exactly `size` bytes hashing
    /// to `sha256`. A partial file at `dest.part` is resumed with `Range`; three
    /// attempts with backoff; a wrong hash is never kept.
    pub fn download(&self, url: &str, size: u64, sha256: &str, dest: &Path) -> Result<(), Failure> {
        check_url(url).map_err(Failure::Verify)?;
        let part = dest.with_extension("part");
        if let Some(dir) = dest.parent() {
            std::fs::create_dir_all(dir)
                .map_err(|e| Failure::Verify(format!("{}: {e}", dir.display())))?;
        }
        let mut last = Failure::Network(format!("{url}: not attempted"));
        for attempt in 0..3 {
            if attempt > 0 {
                std::thread::sleep(Duration::from_millis(500 << attempt));
            }
            match self.attempt(url, size, &part) {
                Ok(()) => {
                    let got = sha256_file(&part)
                        .map_err(|e| Failure::Verify(format!("{}: {e}", part.display())))?;
                    if got == sha256 {
                        return std::fs::rename(&part, dest)
                            .map_err(|e| Failure::Verify(format!("{}: {e}", dest.display())));
                    }
                    let _ = std::fs::remove_file(&part);
                    last =
                        Failure::Verify(format!("{url}: sha256 {got}, the manifest says {sha256}"));
                }
                Err(e @ Failure::Verify(_)) => {
                    let _ = std::fs::remove_file(&part);
                    last = e;
                }
                Err(e) => last = e,
            }
        }
        Err(last)
    }

    fn attempt(&self, url: &str, size: u64, part: &Path) -> Result<(), Failure> {
        let have = std::fs::metadata(part).map_or(0, |m| m.len());
        if have > size {
            let _ = std::fs::remove_file(part);
            return self.attempt(url, size, part);
        }
        if have == size {
            return Ok(());
        }
        let mut request = self.agent.get(url);
        if have > 0 {
            request = request.header("Range", format!("bytes={have}-"));
        }
        let response = request
            .call()
            .map_err(|e| Failure::Network(format!("{url}: {e}")))?;
        let (mut file, mut written) = match response.status().as_u16() {
            206 if have > 0 => {
                let f = std::fs::OpenOptions::new()
                    .append(true)
                    .open(part)
                    .map_err(|e| Failure::Verify(format!("{}: {e}", part.display())))?;
                (f, have)
            }
            200 => {
                let f = std::fs::File::create(part)
                    .map_err(|e| Failure::Verify(format!("{}: {e}", part.display())))?;
                (f, 0)
            }
            status => return Err(Failure::Network(format!("{url}: HTTP {status}"))),
        };
        let mut reader = response.into_body().into_reader();
        let mut buf = vec![0u8; 1 << 16];
        loop {
            let n = reader
                .read(&mut buf)
                .map_err(|e| Failure::Network(format!("{url}: {e}")))?;
            if n == 0 {
                break;
            }
            written += n as u64;
            if written > size {
                return Err(Failure::Verify(format!(
                    "{url}: more than the manifest's {size} bytes"
                )));
            }
            file.write_all(&buf[..n])
                .map_err(|e| Failure::Verify(format!("{}: {e}", part.display())))?;
        }
        if written != size {
            return Err(Failure::Network(format!(
                "{url}: {written} of {size} bytes"
            )));
        }
        file.sync_all()
            .map_err(|e| Failure::Verify(format!("{}: {e}", part.display())))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn urls() {
        assert!(check_url("https://github.com/o/r/releases/latest/download/manifest.json").is_ok());
        assert!(check_url("http://127.0.0.1:8000/manifest.json").is_ok());
        assert!(check_url("http://localhost:8000/m.json").is_ok());
        assert!(check_url("http://10.0.0.1/m.json").is_err());
        assert!(check_url("ftp://x/m.json").is_err());
        assert!(check_url("file:///etc/passwd").is_err());
    }

    #[test]
    fn hashes() {
        assert_eq!(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
}
