//! The HTTP/1.1 request head and the WebSocket upgrade (RFC 6455 section 4.2) that
//! `cloudflared` sends; nothing else is spoken on the listener.

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use std::net::IpAddr;

/// Spec 12: at most 8 KiB of request head.
pub const HEAD_MAX: usize = 8 * 1024;
const HEADERS: usize = 64;
pub const SUBPROTOCOL: &str = "n3e-wire.1";
const GUID: &str = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

#[derive(Debug)]
pub struct Request {
    pub method: String,
    /// Without any query.
    pub path: String,
    /// The minor HTTP/1 version.
    pub version: u8,
    /// Lower-case names, trimmed values; only ever read, never logged.
    headers: Vec<(String, String)>,
}

#[derive(Debug)]
pub enum Head {
    /// The request and the length of its head.
    Complete(Request, usize),
    Partial,
    /// A response status and the close log's reason.
    Bad(u16, &'static str),
}

pub fn parse(buf: &[u8]) -> Head {
    let mut headers = [httparse::EMPTY_HEADER; HEADERS];
    let mut r = httparse::Request::new(&mut headers);
    match r.parse(buf) {
        Ok(httparse::Status::Partial) => Head::Partial,
        Err(httparse::Error::TooManyHeaders) => Head::Bad(431, "oversize"),
        Err(_) => Head::Bad(400, "malformed"),
        Ok(httparse::Status::Complete(n)) => {
            let path = r.path.unwrap_or("");
            Head::Complete(
                Request {
                    method: r.method.unwrap_or("").to_string(),
                    path: path.split('?').next().unwrap_or("").to_string(),
                    version: r.version.unwrap_or(0),
                    headers: r
                        .headers
                        .iter()
                        .map(|h| {
                            let value = String::from_utf8_lossy(h.value);
                            (h.name.to_ascii_lowercase(), value.trim().to_string())
                        })
                        .collect(),
                },
                n,
            )
        }
    }
}

impl Request {
    fn all<'a>(&'a self, name: &'a str) -> impl Iterator<Item = &'a str> + 'a {
        self.headers
            .iter()
            .filter(move |(n, _)| n == name)
            .map(|(_, v)| v.as_str())
    }
    /// The value of a header that appears exactly once.
    fn one<'a>(&'a self, name: &'a str) -> Option<&'a str> {
        let mut values = self.all(name);
        let first = values.next()?;
        values.next().is_none().then_some(first)
    }
    /// The comma-separated tokens of every occurrence of a header.
    fn tokens<'a>(&'a self, name: &'a str) -> impl Iterator<Item = &'a str> + 'a {
        self.all(name).flat_map(|v| v.split(',')).map(str::trim)
    }
}

/// An accepted upgrade: the `Sec-WebSocket-Accept` value and the player's address.
#[derive(Debug, PartialEq)]
pub struct Upgrade {
    pub accept: String,
    pub source: IpAddr,
}

/// Checks an upgrade on `/v1/wire` (method and path already matched). Err: a response
/// status and the close log's reason.
pub fn upgrade(r: &Request) -> Result<Upgrade, (u16, &'static str)> {
    let key = r.one("sec-websocket-key");
    let valid = r.version >= 1
        && r.tokens("upgrade")
            .any(|t| t.eq_ignore_ascii_case("websocket"))
        && r.tokens("connection")
            .any(|t| t.eq_ignore_ascii_case("upgrade"))
        && r.one("sec-websocket-version") == Some("13")
        && key.is_some_and(|k| STANDARD.decode(k).is_ok_and(|b| b.len() == 16));
    if !valid {
        return Err((400, "upgrade"));
    }
    if !r.tokens("sec-websocket-protocol").any(|t| t == SUBPROTOCOL) {
        return Err((400, "protocol"));
    }
    let source = r
        .one("cf-connecting-ip")
        .and_then(|v| v.parse::<IpAddr>().ok())
        .map(crate::config::canonical)
        .ok_or((400, "no_source"))?;
    Ok(Upgrade {
        accept: accept(key.unwrap_or("")),
        source,
    })
}

/// `Sec-WebSocket-Accept` for a `Sec-WebSocket-Key`.
pub fn accept(key: &str) -> String {
    let mut sha = sha1_smol::Sha1::new();
    sha.update(key.as_bytes());
    sha.update(GUID.as_bytes());
    STANDARD.encode(sha.digest().bytes())
}

pub fn switching(accept: &str) -> String {
    format!(
        "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\
         Sec-WebSocket-Accept: {accept}\r\nSec-WebSocket-Protocol: {SUBPROTOCOL}\r\n\r\n"
    )
}

/// A body-less response that ends the connection.
pub fn response(status: u16) -> String {
    let (text, extra) = match status {
        200 => ("OK", ""),
        400 => ("Bad Request", ""),
        403 => ("Forbidden", ""),
        404 => ("Not Found", ""),
        405 => ("Method Not Allowed", "Allow: GET\r\n"),
        408 => ("Request Timeout", ""),
        431 => ("Request Header Fields Too Large", ""),
        502 => ("Bad Gateway", ""),
        503 => ("Service Unavailable", ""),
        _ => ("Error", ""),
    };
    format!("HTTP/1.1 {status} {text}\r\n{extra}Content-Length: 0\r\nConnection: close\r\n\r\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    const KEY: &str = "dGhlIHNhbXBsZSBub25jZQ==";

    fn request(extra: &str) -> Request {
        let text = format!("GET /v1/wire?x=1 HTTP/1.1\r\nHost: edge\r\n{extra}\r\n");
        match parse(text.as_bytes()) {
            Head::Complete(r, n) => {
                assert_eq!(n, text.len());
                r
            }
            other => panic!("{other:?}"),
        }
    }
    const GOOD: &str =
        "Upgrade: WebSocket\r\nConnection: keep-alive, Upgrade\r\nSec-WebSocket-Version: 13\r\n\
                        Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n";

    #[test]
    fn the_rfc_accept_example() {
        assert_eq!(accept(KEY), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=");
    }

    #[test]
    fn upgrades() {
        let r = request(&format!(
            "{GOOD}Sec-WebSocket-Protocol: other, n3e-wire.1\r\nCF-Connecting-IP: 203.0.113.9\r\n"
        ));
        assert_eq!(r.path, "/v1/wire");
        assert_eq!(
            upgrade(&r),
            Ok(Upgrade {
                accept: accept(KEY),
                source: "203.0.113.9".parse().unwrap()
            })
        );
        let r = request(&format!(
            "{GOOD}Sec-WebSocket-Protocol: n3e-wire.1\r\nCF-Connecting-IP: ::ffff:203.0.113.9\r\n"
        ));
        assert_eq!(
            upgrade(&r).unwrap().source,
            "203.0.113.9".parse::<IpAddr>().unwrap()
        );
    }

    #[test]
    fn refusals() {
        let ip = "CF-Connecting-IP: 2001:db8::1\r\n";
        let proto = "Sec-WebSocket-Protocol: n3e-wire.1\r\n";
        for (extra, want) in [
            (format!("{GOOD}{ip}"), (400, "protocol")),
            (
                format!("{GOOD}Sec-WebSocket-Protocol: n3e-wire.2\r\n{ip}"),
                (400, "protocol"),
            ),
            (format!("{GOOD}{proto}"), (400, "no_source")),
            (
                format!("{GOOD}{proto}CF-Connecting-IP: 1.2.3.4, 5.6.7.8\r\n"),
                (400, "no_source"),
            ),
            (
                format!("{GOOD}{proto}CF-Connecting-IP: 1.2.3.4\r\nCF-Connecting-IP: 1.2.3.4\r\n"),
                (400, "no_source"),
            ),
            (
                format!("{GOOD}{proto}CF-Connecting-IP: example.com\r\n"),
                (400, "no_source"),
            ),
            (
                format!("{}{proto}{ip}", GOOD.replace("13", "8")),
                (400, "upgrade"),
            ),
            (
                format!(
                    "{}{proto}{ip}",
                    GOOD.replace("keep-alive, Upgrade", "keep-alive")
                ),
                (400, "upgrade"),
            ),
            (
                format!("{}{proto}{ip}", GOOD.replace(KEY, "c2hvcnQ=")),
                (400, "upgrade"),
            ),
        ] {
            assert_eq!(upgrade(&request(&extra)), Err(want), "{extra}");
        }
    }

    #[test]
    fn heads() {
        assert!(matches!(
            parse(b"GET /live HTTP/1.1\r\nHost: x\r\n"),
            Head::Partial
        ));
        assert!(matches!(
            parse(b"GET /live HTTP/1.1\r\n\0\r\n\r\n"),
            Head::Bad(400, _)
        ));
        let many = format!("GET / HTTP/1.1\r\n{}\r\n", "A: b\r\n".repeat(HEADERS + 1));
        assert!(matches!(parse(many.as_bytes()), Head::Bad(431, _)));
    }
}
