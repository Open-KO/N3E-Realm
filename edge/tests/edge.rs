//! `realm-edge` end to end on loopback: a hand-written WebSocket client (independent of
//! the crate's framing), the bridge, and a TCP stand-in for the server that reads the
//! PROXY v2 header and echoes.

use realm_edge::config::Config;
use realm_edge::{serve, Closed, Log};
use std::net::{IpAddr, SocketAddr};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpSocket, TcpStream};
use tokio::sync::mpsc;
use tokio::time::timeout;

const WAIT: Duration = Duration::from_secs(5);

struct Edge {
    addr: SocketAddr,
    log: Arc<Mutex<Vec<Closed>>>,
}
impl Edge {
    async fn start(trusted: &str, upstream: &str, tune: impl FnOnce(&mut Config)) -> Edge {
        let mut c = Config::from_lookup(|k| match k {
            "REALM_EDGE_TRUSTED_CIDRS" => Some(trusted.to_string()),
            "REALM_EDGE_UPSTREAM" => Some(upstream.to_string()),
            _ => None,
        })
        .unwrap();
        tune(&mut c);
        let l = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = l.local_addr().unwrap();
        let log = Arc::new(Mutex::new(Vec::new()));
        let sink = log.clone();
        let log_fn: Log = Arc::new(move |c: &Closed| sink.lock().unwrap().push(c.clone()));
        tokio::spawn(serve(l, Arc::new(c), log_fn));
        Edge { addr, log }
    }
    /// The close lines once there are `n` of them.
    async fn lines(&self, n: usize) -> Vec<Closed> {
        timeout(WAIT, async {
            loop {
                let l = self.log.lock().unwrap().clone();
                if l.len() >= n {
                    return l;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("close lines")
    }
}

/// A stand-in server: each connection's PROXY header goes to the channel, then it echoes.
async fn upstream() -> (String, mpsc::Receiver<Vec<u8>>) {
    let l = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = l.local_addr().unwrap().to_string();
    let (tx, rx) = mpsc::channel(8);
    tokio::spawn(async move {
        loop {
            let (mut s, _) = l.accept().await.unwrap();
            let tx = tx.clone();
            tokio::spawn(async move {
                let mut head = vec![0u8; 16];
                s.read_exact(&mut head).await.unwrap();
                let n = u16::from_be_bytes([head[14], head[15]]) as usize;
                head.resize(16 + n, 0);
                s.read_exact(&mut head[16..]).await.unwrap();
                tx.send(head).await.unwrap();
                let (mut r, mut w) = s.into_split();
                let _ = tokio::io::copy(&mut r, &mut w).await;
            });
        }
    });
    (addr, rx)
}

const KEY: &str = "dGhlIHNhbXBsZSBub25jZQ==";
fn request(path: &str, extra: &str) -> String {
    format!(
        "GET {path} HTTP/1.1\r\nHost: edge\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\
         Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {KEY}\r\n{extra}\r\n"
    )
}
const GOOD: &str = "Sec-WebSocket-Protocol: n3e-wire.1\r\nCF-Connecting-IP: 198.51.100.4\r\n";

/// Sends a request and reads the response head.
async fn ask(addr: SocketAddr, text: &str) -> (TcpStream, String) {
    let mut s = TcpStream::connect(addr).await.unwrap();
    s.write_all(text.as_bytes()).await.unwrap();
    let head = response(&mut s).await;
    (s, head)
}
async fn response(s: &mut TcpStream) -> String {
    let mut head = Vec::new();
    timeout(WAIT, async {
        while !head.ends_with(b"\r\n\r\n") {
            let mut b = [0u8; 1];
            if s.read(&mut b).await.unwrap_or(0) == 0 {
                break;
            }
            head.push(b[0]);
        }
    })
    .await
    .expect("a response");
    String::from_utf8(head).unwrap()
}
async fn status(addr: SocketAddr, text: &str) -> String {
    let (_, head) = ask(addr, text).await;
    head.lines().next().unwrap_or("").to_string()
}
async fn open(addr: SocketAddr) -> TcpStream {
    let (s, head) = ask(addr, &request("/v1/wire", GOOD)).await;
    assert!(head.starts_with("HTTP/1.1 101 "), "{head}");
    assert!(
        head.contains("Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n"),
        "{head}"
    );
    assert!(
        head.contains("Sec-WebSocket-Protocol: n3e-wire.1\r\n"),
        "{head}"
    );
    s
}

/// A client frame: masked unless `masked` is false.
fn client_frame(first: u8, payload: &[u8], masked: bool) -> Vec<u8> {
    let mask = [0xA1, 0xB2, 0xC3, 0xD4];
    let bit = if masked { 0x80 } else { 0 };
    let mut f = vec![first];
    match payload.len() {
        n @ 0..=125 => f.push(bit | n as u8),
        n @ 126..=65535 => {
            f.push(bit | 126);
            f.extend_from_slice(&(n as u16).to_be_bytes());
        }
        n => {
            f.push(bit | 127);
            f.extend_from_slice(&(n as u64).to_be_bytes());
        }
    }
    if masked {
        f.extend_from_slice(&mask);
        f.extend(payload.iter().enumerate().map(|(i, b)| b ^ mask[i % 4]));
    } else {
        f.extend_from_slice(payload);
    }
    f
}
/// One server frame: (first byte, payload); server frames are never masked.
async fn server_frame(s: &mut TcpStream) -> (u8, Vec<u8>) {
    timeout(WAIT, async {
        let mut h = [0u8; 2];
        s.read_exact(&mut h).await.unwrap();
        assert_eq!(h[1] & 0x80, 0, "server frames are unmasked");
        let n = match h[1] & 0x7F {
            126 => {
                let mut n = [0u8; 2];
                s.read_exact(&mut n).await.unwrap();
                u16::from_be_bytes(n) as usize
            }
            127 => {
                let mut n = [0u8; 8];
                s.read_exact(&mut n).await.unwrap();
                u64::from_be_bytes(n) as usize
            }
            n => n as usize,
        };
        assert!(n <= 64 * 1024);
        let mut p = vec![0u8; n];
        s.read_exact(&mut p).await.unwrap();
        (h[0], p)
    })
    .await
    .expect("a frame")
}
/// The close a misbehaving client gets.
async fn closed_with(s: &mut TcpStream) -> u16 {
    loop {
        let (first, p) = server_frame(s).await;
        if first == 0x88 {
            return u16::from_be_bytes([p[0], p[1]]);
        }
    }
}

#[tokio::test]
async fn untrusted_peers_are_closed_and_loopback_only_sees_live() {
    let edge = Edge::start("10.9.0.0/16", "127.0.0.1:9", |_| {}).await;
    // 127.0.0.2: outside the trusted range, and not the loopback health check.
    let socket = TcpSocket::new_v4().unwrap();
    socket.bind("127.0.0.2:0".parse().unwrap()).unwrap();
    let mut s = socket.connect(edge.addr).await.unwrap();
    let _ = s.write_all(request("/v1/wire", GOOD).as_bytes()).await;
    let mut b = [0u8; 16];
    let n = timeout(WAIT, s.read(&mut b)).await.unwrap().unwrap_or(0);
    assert_eq!(n, 0, "closed without a response");
    let l = edge.lines(1).await;
    assert_eq!((l[0].src.as_str(), l[0].reason), ("127.0.0.2", "untrusted"));
    assert_eq!(
        status(edge.addr, "GET /live HTTP/1.1\r\nHost: x\r\n\r\n").await,
        "HTTP/1.1 200 OK"
    );
    assert_eq!(
        status(edge.addr, &request("/v1/wire", GOOD)).await,
        "HTTP/1.1 403 Forbidden"
    );
    assert_eq!(edge.lines(2).await[1].reason, "untrusted");
}

#[tokio::test]
async fn routes_and_refused_upgrades() {
    let edge = Edge::start("127.0.0.0/8", "127.0.0.1:9", |_| {}).await;
    assert_eq!(
        status(edge.addr, "GET /live HTTP/1.1\r\nHost: x\r\n\r\n").await,
        "HTTP/1.1 200 OK"
    );
    // Each refusal is logged once its socket closes; take them one at a time.
    let post = request("/v1/wire", GOOD).replacen("GET", "POST", 1);
    let big = request("/v1/wire", &format!("X-Pad: {}\r\n", "a".repeat(9000)));
    for (n, (text, want, reason)) in [
        (request("/v2/wire", GOOD), "404 Not Found", "path"),
        (post, "405 Method Not Allowed", "method"),
        (
            request("/v1/wire", "CF-Connecting-IP: 198.51.100.4\r\n"),
            "400 Bad Request",
            "protocol",
        ),
        (
            request("/v1/wire", "Sec-WebSocket-Protocol: n3e-wire.1\r\n"),
            "400 Bad Request",
            "no_source",
        ),
        (
            request(
                "/v1/wire",
                "Sec-WebSocket-Protocol: n3e-wire.1\r\nCF-Connecting-IP: 198.51.100.4, 10.0.0.1\r\n",
            ),
            "400 Bad Request",
            "no_source",
        ),
        // 8 KiB of head at most.
        (big, "431 Request Header Fields Too Large", "oversize"),
        // Nothing listens on the upstream port: the upgrade is refused, not taken.
        (request("/v1/wire", GOOD), "502 Bad Gateway", "upstream"),
    ]
    .into_iter()
    .enumerate()
    {
        assert_eq!(status(edge.addr, &text).await, format!("HTTP/1.1 {want}"));
        let l = edge.lines(n + 1).await;
        assert_eq!(l[n].reason, reason, "{want}");
    }
    let l = edge.lines(7).await;
    assert_eq!(l[6].src, "198.51.100.4", "the player, once named");
    assert_eq!(l[0].src, "127.0.0.1", "else the peer");
}

#[tokio::test]
async fn bytes_round_trip_behind_a_proxy_header() {
    let (up, mut headers) = upstream().await;
    let edge = Edge::start("127.0.0.1", &up, |_| {}).await;
    let mut s = open(edge.addr).await;
    let head = timeout(WAIT, headers.recv()).await.unwrap().unwrap();
    // The server's parser (admission.rs): signature, PROXY over TCP4, the player first.
    assert_eq!(&head[..12], b"\r\n\r\n\0\r\nQUIT\n");
    assert_eq!(&head[12..16], &[0x21, 0x11, 0, 12]);
    assert_eq!(&head[16..20], &[198, 51, 100, 4]);
    assert_eq!(&head[20..24], &[127, 0, 0, 1]);
    assert_eq!(&head[24..26], &[0, 0], "CF-Connecting-IP names no port");
    // A fragmented message, then a large one: the stream is reassembled in order.
    s.write_all(&client_frame(0x02, b"hel", true))
        .await
        .unwrap();
    s.write_all(&client_frame(0x80, b"lo", true)).await.unwrap();
    let big: Vec<u8> = (0..60_000u32).map(|i| i as u8).collect();
    s.write_all(&client_frame(0x82, &big, true)).await.unwrap();
    let mut echoed = Vec::new();
    while echoed.len() < 5 + big.len() {
        let (first, p) = server_frame(&mut s).await;
        assert_eq!(first, 0x82, "binary, final");
        echoed.extend_from_slice(&p);
    }
    assert_eq!(&echoed[..5], b"hello");
    assert_eq!(&echoed[5..], &big[..]);
    // The client closes: echoed, and the server's side ends.
    s.write_all(&client_frame(0x88, &1000u16.to_be_bytes(), true))
        .await
        .unwrap();
    assert_eq!(closed_with(&mut s).await, 1000);
    let l = edge.lines(1).await;
    assert_eq!(l[0].src, "198.51.100.4");
    assert_eq!(
        (l[0].bytes_in, l[0].bytes_out, l[0].reason),
        (60_005, 60_005, "closed")
    );
}

#[tokio::test]
async fn the_server_closing_closes_the_socket() {
    let l = TcpListener::bind("[::1]:0").await.unwrap();
    let up = l.local_addr().unwrap().to_string();
    let edge = Edge::start("127.0.0.1", &up, |_| {}).await;
    let mut s = open(edge.addr).await;
    let (mut u, _) = l.accept().await.unwrap();
    // An IPv4 player over an IPv6 upstream: the header keeps the player's family.
    let mut head = [0u8; 28];
    u.read_exact(&mut head).await.unwrap();
    assert_eq!((head[13], &head[16..20]), (0x11, &[198, 51, 100, 4][..]));
    u.write_all(b"bye").await.unwrap();
    drop(u);
    assert_eq!(server_frame(&mut s).await, (0x82, b"bye".to_vec()));
    assert_eq!(closed_with(&mut s).await, 1000);
    // The client answers the close, so the bridge need not wait out its grace.
    s.write_all(&client_frame(0x88, &1000u16.to_be_bytes(), true))
        .await
        .unwrap();
    let l = edge.lines(1).await;
    assert_eq!((l[0].bytes_out, l[0].reason), (3, "upstream_closed"));
}

#[tokio::test]
async fn upgrades_past_the_cap_get_503() {
    let (up, _headers) = upstream().await;
    let edge = Edge::start("127.0.0.1", &up, |c| c.max_connections = 1).await;
    let mut first = open(edge.addr).await;
    assert_eq!(
        status(edge.addr, &request("/v1/wire", GOOD)).await,
        "HTTP/1.1 503 Service Unavailable"
    );
    assert_eq!(edge.lines(1).await[0].reason, "full");
    first
        .write_all(&client_frame(0x88, &[], true))
        .await
        .unwrap();
    assert_eq!(
        server_frame(&mut first).await,
        (0x88, vec![]),
        "an empty close is echoed empty"
    );
    edge.lines(2).await;
    let _again = open(edge.addr).await;
}

#[tokio::test]
async fn frame_rules() {
    let (up, _headers) = upstream().await;
    let edge = Edge::start("127.0.0.1", &up, |_| {}).await;
    // Ping is answered with its payload; pong is ignored.
    let mut s = open(edge.addr).await;
    s.write_all(&client_frame(0x8A, b"ignored", true))
        .await
        .unwrap();
    s.write_all(&client_frame(0x89, b"are you there", true))
        .await
        .unwrap();
    assert_eq!(
        server_frame(&mut s).await,
        (0x8A, b"are you there".to_vec())
    );
    for (frame, code, reason) in [
        (client_frame(0x82, b"plain", false), 1002, "unmasked"),
        (client_frame(0x81, b"text", true), 1003, "text"),
        (client_frame(0x89, &[0; 126], true), 1002, "protocol"),
        (client_frame(0x09, b"x", true), 1002, "protocol"),
        (client_frame(0x80, b"x", true), 1002, "protocol"),
    ] {
        let mut s = open(edge.addr).await;
        s.write_all(&frame).await.unwrap();
        assert_eq!(closed_with(&mut s).await, code, "{reason}");
    }
    // Over 64 KiB + 1 KiB: refused on its header alone.
    let mut s = open(edge.addr).await;
    let mut h = vec![0x82, 0x80 | 127];
    h.extend_from_slice(&(64 * 1024 + 1025u64).to_be_bytes());
    s.write_all(&h).await.unwrap();
    assert_eq!(closed_with(&mut s).await, 1009);
    drop(s);
    let mut reasons: Vec<_> = edge.lines(6).await.iter().map(|c| c.reason).collect();
    reasons.sort();
    assert_eq!(
        reasons,
        ["oversize", "protocol", "protocol", "protocol", "text", "unmasked"]
    );
}

#[tokio::test]
async fn pings_and_the_idle_close() {
    let (up, _headers) = upstream().await;
    let edge = Edge::start("127.0.0.1", &up, |c| {
        c.ping_every = Duration::from_millis(100);
        c.idle = Duration::from_millis(400);
    })
    .await;
    let mut s = open(edge.addr).await;
    assert_eq!(server_frame(&mut s).await, (0x89, vec![]));
    // A pong is a frame: it holds the idle close off.
    s.write_all(&client_frame(0x8A, &[], true)).await.unwrap();
    assert_eq!(closed_with(&mut s).await, 1001);
    let l = edge.lines(1).await;
    assert_eq!(l[0].reason, "idle");
    assert!(l[0].src.parse::<IpAddr>().is_ok());
}
