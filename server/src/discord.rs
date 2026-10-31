//! Discord OAuth2 code exchange (specs/02-auth-sessions.md): `POST /oauth2/token`
//! with the client's PKCE verifier, then `GET /users/@me`. A minimal HTTP/1.1
//! client over the server's own OpenSSL; it runs on the connection's task, never
//! on a tick, and the whole exchange is bounded by `EXCHANGE`. The access token
//! lives only inside `exchange` and is never stored or logged.
use crate::content::{bad, Result};
use openssl::ssl::{SslConnector, SslMethod};
use serde_json::Value;
use std::{pin::Pin, sync::Arc, time::Duration};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    net::TcpStream,
    time::timeout,
};
use tokio_openssl::SslStream;

pub const DEFAULT_API: &str = "https://discord.com/api";
/// Both requests together, connect and TLS included.
const EXCHANGE: Duration = Duration::from_secs(10);
const RESPONSE_LIMIT: usize = 64 * 1024;
const NAME_LIMIT: usize = 64;

/// Where the API is: `https://host[:port]/prefix`, or plain `http://` to a
/// loopback address (a test's stand-in for Discord).
#[derive(Debug, Clone, PartialEq)]
pub struct Api {
    tls: bool,
    host: String,
    port: u16,
    prefix: String,
}
impl Api {
    pub fn parse(url: &str) -> Result<Self> {
        let (tls, rest) = if let Some(r) = url.strip_prefix("https://") {
            (true, r)
        } else if let Some(r) = url.strip_prefix("http://") {
            (false, r)
        } else {
            return Err(bad("N3E_DISCORD_API must start with https://"));
        };
        let (authority, path) = rest.split_at(rest.find('/').unwrap_or(rest.len()));
        let (host, port) = match authority.rsplit_once(':') {
            Some((h, p)) => (h, p.parse().map_err(|_| bad("N3E_DISCORD_API port"))?),
            None => (authority, if tls { 443 } else { 80 }),
        };
        if host.is_empty() || host.contains(['@', '[', ']', ' ']) {
            return Err(bad("N3E_DISCORD_API host"));
        }
        let loopback = host
            .parse::<std::net::IpAddr>()
            .is_ok_and(|a| a.is_loopback());
        if !tls && !loopback {
            return Err(bad(
                "N3E_DISCORD_API: plain http only to a loopback address",
            ));
        }
        Ok(Self {
            tls,
            host: host.into(),
            port,
            prefix: path.trim_end_matches('/').into(),
        })
    }
}

/// The server's Discord application. The secret never leaves the server.
pub struct Config {
    pub client_id: String,
    secret: String,
    api: Api,
    connector: SslConnector,
}
impl Config {
    pub fn new(client_id: String, secret: String, api: Api) -> Result<Self> {
        Ok(Self {
            client_id,
            secret,
            api,
            connector: SslConnector::builder(SslMethod::tls_client())?.build(),
        })
    }
}

/// Who Discord says logged in.
#[derive(Debug, Clone, PartialEq)]
pub struct Identity {
    pub id: String,
    pub name: String,
}

/// Why an exchange failed, as the `discord:<reason>` login detail.
#[derive(Debug, Clone, PartialEq)]
pub struct Failure(pub String);
impl Failure {
    fn unavailable() -> Self {
        Self("unavailable".into())
    }
}

pub async fn exchange(
    config: Arc<Config>,
    code: &str,
    verifier: &str,
    redirect: &str,
) -> std::result::Result<Identity, Failure> {
    let form = [
        ("grant_type", "authorization_code"),
        ("code", code),
        ("redirect_uri", redirect),
        ("code_verifier", verifier),
        ("client_id", config.client_id.as_str()),
        ("client_secret", config.secret.as_str()),
    ]
    .iter()
    .map(|(k, v)| format!("{k}={}", form_encode(v)))
    .collect::<Vec<_>>()
    .join("&");
    let flow = async {
        let (status, body) = request(
            &config,
            "POST",
            "/oauth2/token",
            "Content-Type: application/x-www-form-urlencoded\r\n",
            form.as_bytes(),
        )
        .await
        .map_err(|_| Failure::unavailable())?;
        let token = match (status, serde_json::from_slice::<Value>(&body)) {
            (200, Ok(v)) => v
                .get("access_token")
                .and_then(Value::as_str)
                .filter(|t| {
                    !t.is_empty() && t.len() <= 512 && t.bytes().all(|b| b.is_ascii_graphic())
                })
                .map(str::to_string)
                .ok_or_else(|| Failure("bad_response".into()))?,
            (400..=403, Ok(v)) => return Err(Failure(reason(&v))),
            (400..=403, Err(_)) => return Err(Failure("rejected".into())),
            _ => return Err(Failure::unavailable()),
        };
        let (status, body) = request(
            &config,
            "GET",
            "/users/@me",
            &format!("Authorization: Bearer {token}\r\n"),
            b"",
        )
        .await
        .map_err(|_| Failure::unavailable())?;
        drop(token);
        match (status, serde_json::from_slice::<Value>(&body)) {
            (200, Ok(v)) => identity(&v).ok_or_else(|| Failure("bad_response".into())),
            (401 | 403, _) => Err(Failure("rejected".into())),
            _ => Err(Failure::unavailable()),
        }
    };
    timeout(EXCHANGE, flow)
        .await
        .unwrap_or_else(|_| Err(Failure::unavailable()))
}

/// Discord's OAuth error code (`invalid_grant`, ...), never its free text.
fn reason(v: &Value) -> String {
    v.get("error")
        .and_then(Value::as_str)
        .filter(|e| {
            !e.is_empty() && e.len() <= 32 && e.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
        })
        .unwrap_or("rejected")
        .to_string()
}

fn identity(v: &Value) -> Option<Identity> {
    let id = v
        .get("id")
        .and_then(Value::as_str)
        .filter(|i| !i.is_empty() && i.len() <= 20 && i.bytes().all(|b| b.is_ascii_digit()))?;
    let name = v
        .get("global_name")
        .and_then(Value::as_str)
        .filter(|n| !n.trim().is_empty())
        .or_else(|| v.get("username").and_then(Value::as_str))?;
    Some(Identity {
        id: id.into(),
        name: label(name, NAME_LIMIT),
    })
}

/// Control characters stripped, then cut to at most `limit` bytes on a
/// character boundary: display names and client labels.
pub fn label(text: &str, limit: usize) -> String {
    let mut out = String::new();
    for c in text.chars().filter(|c| !c.is_control()) {
        if out.len() + c.len_utf8() > limit {
            break;
        }
        out.push(c);
    }
    out
}

fn form_encode(v: &str) -> String {
    let mut out = String::with_capacity(v.len());
    for b in v.bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'.' | b'_' | b'~') {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

async fn request(
    config: &Config,
    method: &str,
    path: &str,
    headers: &str,
    body: &[u8],
) -> Result<(u16, Vec<u8>)> {
    let api = &config.api;
    let tcp = TcpStream::connect((api.host.as_str(), api.port)).await?;
    tcp.set_nodelay(true)?;
    let head = format!(
        "{method} {}{path} HTTP/1.1\r\nHost: {}\r\nUser-Agent: n3e-server\r\nAccept: application/json\r\n{headers}Content-Length: {}\r\nConnection: close\r\n\r\n",
        api.prefix,
        api.host,
        body.len()
    );
    if api.tls {
        let ssl = config.connector.configure()?.into_ssl(&api.host)?;
        let mut s = SslStream::new(ssl, tcp)?;
        Pin::new(&mut s)
            .connect()
            .await
            .map_err(|e| bad(&format!("tls: {e}")))?;
        exchange_on(&mut s, head.as_bytes(), body).await
    } else {
        let mut s = tcp;
        exchange_on(&mut s, head.as_bytes(), body).await
    }
}

async fn exchange_on(
    s: &mut (impl AsyncRead + AsyncWrite + Unpin),
    head: &[u8],
    body: &[u8],
) -> Result<(u16, Vec<u8>)> {
    s.write_all(head).await?;
    s.write_all(body).await?;
    s.flush().await?;
    let mut response = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        // A TLS peer that closes without close_notify is the end of the response.
        let n = match s.read(&mut chunk).await {
            Ok(n) => n,
            Err(_) if !response.is_empty() => 0,
            Err(e) => return Err(e.into()),
        };
        if n == 0 {
            break;
        }
        if response.len() + n > RESPONSE_LIMIT {
            return Err(bad("discord response bound"));
        }
        response.extend_from_slice(&chunk[..n]);
    }
    parse(&response)
}

/// Status and body of a whole `Connection: close` response.
fn parse(response: &[u8]) -> Result<(u16, Vec<u8>)> {
    let end = response
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .ok_or_else(|| bad("discord response head"))?;
    let head = std::str::from_utf8(&response[..end]).map_err(|_| bad("discord response head"))?;
    let mut lines = head.split("\r\n");
    let status: u16 = lines
        .next()
        .and_then(|l| l.split(' ').nth(1))
        .and_then(|s| s.parse().ok())
        .ok_or_else(|| bad("discord status line"))?;
    let (mut chunked, mut length) = (false, None);
    for line in lines {
        let Some((k, v)) = line.split_once(':') else {
            continue;
        };
        match k.trim().to_ascii_lowercase().as_str() {
            "transfer-encoding" => chunked = v.trim().eq_ignore_ascii_case("chunked"),
            "content-length" => length = v.trim().parse::<usize>().ok(),
            _ => {}
        }
    }
    let rest = &response[end + 4..];
    if chunked {
        return Ok((status, dechunk(rest)?));
    }
    Ok((
        status,
        rest[..length.unwrap_or(rest.len()).min(rest.len())].to_vec(),
    ))
}

fn dechunk(mut rest: &[u8]) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    loop {
        let line = rest
            .windows(2)
            .position(|w| w == b"\r\n")
            .ok_or_else(|| bad("discord chunk"))?;
        let size = std::str::from_utf8(&rest[..line])
            .ok()
            .and_then(|s| usize::from_str_radix(s.split(';').next()?.trim(), 16).ok())
            .ok_or_else(|| bad("discord chunk size"))?;
        rest = &rest[line + 2..];
        if size == 0 {
            return Ok(out);
        }
        if rest.len() < size + 2 {
            return Err(bad("discord chunk truncated"));
        }
        out.extend_from_slice(&rest[..size]);
        rest = &rest[size + 2..];
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn api_addresses() {
        let a = Api::parse(DEFAULT_API).unwrap();
        assert_eq!(
            (a.tls, a.host.as_str(), a.port, a.prefix.as_str()),
            (true, "discord.com", 443, "/api")
        );
        let a = Api::parse("http://127.0.0.1:4711/api/").unwrap();
        assert_eq!((a.tls, a.port, a.prefix.as_str()), (false, 4711, "/api"));
        assert!(Api::parse("http://discord.com/api").is_err());
        assert!(Api::parse("ftp://127.0.0.1/").is_err());
        assert!(Api::parse("https://user@host/").is_err());
    }

    #[test]
    fn responses_whole_and_chunked() {
        let (s, b) = parse(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}").unwrap();
        assert_eq!((s, b.as_slice()), (200, &b"{}"[..]));
        let (s, b) = parse(b"HTTP/1.1 400 Bad\r\nTransfer-Encoding: chunked\r\n\r\n3\r\n{\"a\r\n4;x=y\r\n\":1}\r\n0\r\n\r\n").unwrap();
        assert_eq!((s, b.as_slice()), (400, &b"{\"a\":1}"[..]));
        assert!(parse(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n9\r\nshort").is_err());
        assert!(parse(b"garbage").is_err());
    }

    #[test]
    fn identities_and_reasons() {
        let v = serde_json::json!({"id": "80351110224678912", "username": "nelly", "global_name": "Nelly\u{7}"});
        assert_eq!(
            identity(&v),
            Some(Identity {
                id: "80351110224678912".into(),
                name: "Nelly".into()
            })
        );
        let v = serde_json::json!({"id": "1", "username": "nelly", "global_name": null});
        assert_eq!(identity(&v).unwrap().name, "nelly");
        assert!(identity(&serde_json::json!({"id": "12a", "username": "x"})).is_none());
        assert_eq!(
            reason(
                &serde_json::json!({"error": "invalid_grant", "error_description": "Invalid \"code\""})
            ),
            "invalid_grant"
        );
        assert_eq!(
            reason(&serde_json::json!({"error": "Weird Text"})),
            "rejected"
        );
        assert_eq!(label(&"é".repeat(40), 64).len(), 64);
        assert_eq!(form_encode("a b&c=/"), "a%20b%26c%3D%2F");
    }
}
