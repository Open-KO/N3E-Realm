//! RESP requests have bounded replies and absolute deadlines. No credentials in keys.
use crate::content::{bad, Result};
use std::{
    net::SocketAddr,
    sync::{
        atomic::{AtomicU8, Ordering},
        Mutex,
    },
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
    time::{timeout, Duration},
};
/// Every Redis request's deadline, name lookup and connect included.
pub const DEADLINE: Duration = Duration::from_millis(700);
/// The Redis address and the socket address its name last resolved to
/// (PQ-368, D-198). A request connects to the resolved address and looks the
/// name up again only after a request failed, so a slow name service (Docker's
/// embedded resolver is the Compose stack's, and it stalled for over 700 ms
/// under the parallel `make live` load) does not fail a request while Redis
/// serves; a Redis that moved fails one request, and the next one finds it.
pub struct Endpoint {
    name: String,
    resolved: Mutex<Option<SocketAddr>>,
}
impl Endpoint {
    pub fn new(name: impl Into<String>) -> Self {
        Self { name: name.into(), resolved: Mutex::new(None) }
    }
    pub fn name(&self) -> &str {
        &self.name
    }
    fn cached(&self) -> Option<SocketAddr> {
        *self.resolved.lock().unwrap_or_else(|e| e.into_inner())
    }
    fn remember(&self, a: Option<SocketAddr>) {
        *self.resolved.lock().unwrap_or_else(|e| e.into_inner()) = a;
    }
    async fn connect(&self, stage: &AtomicU8) -> std::io::Result<TcpStream> {
        // Every resolved address in turn, as a connect by name does; the one
        // that answered is remembered.
        let addresses: Vec<SocketAddr> = match self.cached() {
            Some(a) => vec![a],
            None => {
                stage.store(LOOKUP, Ordering::Relaxed);
                tokio::net::lookup_host(self.name.as_str()).await?.collect()
            }
        };
        stage.store(CONNECT, Ordering::Relaxed);
        let mut last = std::io::Error::new(std::io::ErrorKind::NotFound, "no address for the Redis name");
        for address in addresses {
            match TcpStream::connect(address).await {
                Ok(s) => {
                    self.remember(Some(address));
                    stage.store(REPLY, Ordering::Relaxed);
                    return Ok(s);
                }
                Err(e) => last = e,
            }
        }
        Err(last)
    }
    /// One request within `DEADLINE`; any failure forgets the resolved
    /// address. A missed deadline names the step it was in (PQ-368).
    async fn request<T>(&self, f: impl AsyncFnOnce(&AtomicU8) -> Result<T>) -> Result<T> {
        let stage = AtomicU8::new(REPLY);
        let r = match timeout(DEADLINE, f(&stage)).await {
            Ok(r) => r,
            Err(_) => Err(bad(&format!(
                "no Redis reply within {} ms (at the {})",
                DEADLINE.as_millis(),
                ["name lookup", "connect", "reply"][stage.load(Ordering::Relaxed) as usize]
            ))),
        };
        if r.is_err() {
            self.remember(None);
        }
        r
    }
}
const LOOKUP: u8 = 0;
const CONNECT: u8 = 1;
const REPLY: u8 = 2;
/// One readiness probe: PING answered by PONG (main.rs, D-198).
pub async fn ping(e: &Endpoint) -> Result<()> {
    e.request(async |stage| {
        let mut s = e.connect(stage).await?;
        s.write_all(b"*1\r\n$4\r\nPING\r\n").await?;
        let mut b = [0; 7];
        s.read_exact(&mut b).await?;
        if &b != b"+PONG\r\n" {
            return Err(bad("unexpected PING reply"));
        }
        Ok(())
    })
    .await
}
pub async fn command(e: &Endpoint, args: &[&str]) -> Result<String> {
    e.request(async |stage| {
        let mut s = e.connect(stage).await?;
        let mut request = format!("*{}\r\n", args.len());
        for a in args {
            request.push_str(&format!("${}\r\n{}\r\n", a.len(), a));
        }
        s.write_all(request.as_bytes()).await?;
        let mut b = Vec::new();
        while !b.ends_with(b"\r\n") {
            if b.len() >= 256 {
                return Err(bad("cache response bound"));
            }
            b.push(s.read_u8().await?);
        }
        let response = String::from_utf8(b)?;
        if response.starts_with('-') {
            return Err(bad("cache command failed"));
        }
        Ok(response)
    })
    .await
}
/// GET of a key whose value is at most `limit` bytes; None when it is absent.
pub async fn get(e: &Endpoint, key: &str, limit: usize) -> Result<Option<String>> {
    e.request(async |stage| {
        let mut s = e.connect(stage).await?;
        s.write_all(format!("*2\r\n$3\r\nGET\r\n${}\r\n{}\r\n", key.len(), key).as_bytes()).await?;
        let mut head = Vec::new();
        while !head.ends_with(b"\r\n") {
            if head.len() >= 32 {
                return Err(bad("cache response bound"));
            }
            head.push(s.read_u8().await?);
        }
        let head = String::from_utf8(head)?;
        let length: i64 = head.strip_prefix('$').ok_or_else(|| bad("cache GET reply"))?.trim_end().parse()?;
        if length < 0 {
            return Ok(None);
        }
        let length = usize::try_from(length)?;
        if length > limit {
            return Err(bad("cache value bound"));
        }
        let mut value = vec![0; length + 2];
        s.read_exact(&mut value).await?;
        value.truncate(length);
        Ok(Some(String::from_utf8(value)?))
    })
    .await
}
pub async fn login_allowed(address: &Endpoint, realm: &str, account: &str, ip: &str) -> Result<bool> {
    throttle(address, realm, Some(account.as_bytes()), Some(ip)).await
}
/// The login throttle (10 a minute per account key, 30 per IP): counts each key
/// given and answers whether all are within their limit. The account key is
/// stored as its SHA-256. A Discord login counts its IP before the code exchange
/// and the Discord account after it (specs/02-auth-sessions.md).
pub async fn throttle(address: &Endpoint, realm: &str, account: Option<&[u8]>, ip: Option<&str>) -> Result<bool> {
    let script="local ok=1; for i,k in ipairs(KEYS) do local n=redis.call('INCR',k); if n==1 then redis.call('EXPIRE',k,60) end; if n>tonumber(ARGV[i]) then ok=0 end end; return ok";
    let (mut keys, mut limits) = (Vec::new(), Vec::new());
    if let Some(account) = account {
        let digest: String = openssl::sha::sha256(account)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        keys.push(format!("n3e:{realm}:login:{digest}"));
        limits.push("10");
    }
    if let Some(ip) = ip {
        keys.push(format!("n3e:{realm}:ip:{ip}"));
        limits.push("30");
    }
    let count = keys.len().to_string();
    let mut args = vec!["EVAL", script, &count];
    args.extend(keys.iter().map(String::as_str));
    args.extend(limits);
    Ok(command(address, &args).await? == ":1\r\n")
}
pub async fn presence(address: &Endpoint, realm: &str, id: i64, session: i64) -> Result<()> {
    command(
        address,
        &[
            "SET",
            &format!("n3e:{realm}:presence:{id}"),
            &session.to_string(),
            "EX",
            "10",
        ],
    )
    .await?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    // PQ-368 (D-198): a request reuses the address it resolved and forgets it
    // after any failure; a missed deadline names its step.
    #[tokio::test]
    async fn endpoint_keeps_its_resolved_address_until_a_request_fails() -> Result<()> {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
        let port = listener.local_addr()?.port();
        let server = tokio::spawn(async move {
            for reply in [&b"+PONG\r\n"[..], b"+PONG\r\n", b"-ERR no\r\n"] {
                let (mut s, _) = listener.accept().await?;
                let mut b = [0; 14];
                s.read_exact(&mut b).await?;
                s.write_all(reply).await?;
            }
            // Accept and never answer: the deadline expires at the reply.
            let (_silent, _) = listener.accept().await?;
            tokio::time::sleep(DEADLINE * 2).await;
            Ok::<_, std::io::Error>(())
        });
        let e = Endpoint::new(format!("localhost:{port}"));
        assert_eq!(e.cached(), None);
        ping(&e).await?;
        let first = e.cached().expect("resolved after a success");
        assert_eq!(first.port(), port);
        ping(&e).await?;
        assert_eq!(e.cached(), Some(first));
        assert!(ping(&e).await.is_err(), "an error reply fails the probe");
        assert_eq!(e.cached(), None, "a failure forgets the address");
        let late = ping(&e).await.unwrap_err().to_string();
        assert_eq!(late, "no Redis reply within 700 ms (at the reply)");
        assert_eq!(e.cached(), None);
        server.abort();
        // Nothing listens there any more: the connect is refused at once.
        assert!(ping(&e).await.is_err());
        Ok(())
    }
}
