//! realm-edge — see `specs/12-edge.md`. Accepts WebSocket upgrades on `/v1/wire` from
//! `cloudflared` only, opens a TCP connection to the server, writes a PROXY v2 header
//! naming the player (`CF-Connecting-IP`), then copies the inner TLS stream both ways
//! as binary frames. It does no TLS and parses nothing past the upgrade.

pub mod config;
pub mod frame;
pub mod handshake;
pub mod proxy;

use config::Config;
use handshake::Head;
use std::io::Cursor;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::tcp::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{mpsc, OwnedSemaphorePermit, Semaphore};
use tokio::time::{timeout, timeout_at, Instant};

/// Spec 12: an upgrade completes within 5 s of accept, upstream connect included.
pub const HANDSHAKE: Duration = Duration::from_secs(5);
/// Connections still in their handshake; past it, accepting waits (the kernel's backlog
/// holds the rest), so slow request heads cannot pile up unbounded.
const HANDSHAKES: usize = 64;
/// Bytes of the server's stream per binary frame sent to the client.
const FRAME_OUT: usize = 16 * 1024;
/// A client's buffered reader.
const READ_BUFFER: usize = 16 * 1024;
/// Pongs and the close queued from the client's reader to its writer.
const CONTROLS: usize = 4;
/// After one direction ends, how long the other may take to finish its close.
const GRACE: Duration = Duration::from_secs(2);
/// A refusal response is small; the peer gets this long to take it.
const RESPONSE: Duration = Duration::from_secs(2);

/// The close log's line (spec 12): the player's address when known, else the TCP peer's;
/// bytes are the inner stream's, frame payloads only.
#[derive(Clone, Debug, PartialEq)]
pub struct Closed {
    pub src: String,
    pub bytes_in: u64,
    pub bytes_out: u64,
    pub secs: u64,
    pub reason: &'static str,
}
impl std::fmt::Display for Closed {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(
            f,
            "edge close src={} bytes_in={} bytes_out={} secs={} reason={}",
            self.src, self.bytes_in, self.bytes_out, self.secs, self.reason
        )
    }
}

/// Where close lines go: stderr in the binary, a list in tests.
pub type Log = Arc<dyn Fn(&Closed) + Send + Sync>;

/// Serves the listener until it fails for good.
pub async fn serve(listener: TcpListener, config: Arc<Config>, log: Log) -> std::io::Result<()> {
    let handshakes = Arc::new(Semaphore::new(HANDSHAKES));
    let open = Arc::new(Semaphore::new(config.max_connections));
    loop {
        let permit = handshakes
            .clone()
            .acquire_owned()
            .await
            .expect("never closed");
        let (t, peer) = match listener.accept().await {
            Ok(a) => a,
            Err(e) => {
                // Out of descriptors and the like: back off, never spin.
                eprintln!("realm-edge: accept failed ({e})");
                tokio::time::sleep(Duration::from_millis(100)).await;
                continue;
            }
        };
        let (config, open, log) = (config.clone(), open.clone(), log.clone());
        tokio::spawn(async move {
            if let Some(closed) = connection(t, peer, permit, &config, &open).await {
                log(&closed);
            }
        });
    }
}

/// Loopback may ask `/live` (the compose healthcheck runs in the container) and nothing else.
fn loopback(ip: IpAddr) -> bool {
    ip == IpAddr::V4(Ipv4Addr::LOCALHOST) || ip == IpAddr::V6(Ipv6Addr::LOCALHOST)
}

/// One accepted socket, through to its close line (None: a health check, not logged).
async fn connection(
    mut t: TcpStream,
    peer: SocketAddr,
    handshake: OwnedSemaphorePermit,
    config: &Config,
    open: &Arc<Semaphore>,
) -> Option<Closed> {
    let started = Instant::now();
    let peer_ip = config::canonical(peer.ip());
    let mut closed = Closed {
        src: peer_ip.to_string(),
        bytes_in: 0,
        bytes_out: 0,
        secs: 0,
        reason: "",
    };
    let finish = |mut c: Closed, reason| {
        c.secs = started.elapsed().as_secs();
        c.reason = reason;
        Some(c)
    };
    let trusted = config.trusts(peer_ip);
    if !trusted && !loopback(peer_ip) {
        return finish(closed, "untrusted");
    }
    let deadline = started + HANDSHAKE;
    let mut buf = vec![0u8; handshake::HEAD_MAX];
    let (request, head, filled) = match timeout_at(deadline, read_head(&mut t, &mut buf)).await {
        Err(_) => {
            refuse(&mut t, 408).await;
            return finish(closed, "timeout");
        }
        Ok(Err((status, reason))) => {
            refuse(&mut t, status).await;
            return finish(closed, reason);
        }
        Ok(Ok(r)) => r,
    };
    let (status, reason) = match request.path.as_str() {
        "/live" if request.method == "GET" => {
            refuse(&mut t, 200).await;
            return None;
        }
        _ if !trusted => (403, "untrusted"),
        "/live" | "/v1/wire" if request.method != "GET" => (405, "method"),
        "/v1/wire" => (0, ""),
        _ => (404, "path"),
    };
    if status != 0 {
        refuse(&mut t, status).await;
        return finish(closed, reason);
    }
    let upgrade = match handshake::upgrade(&request) {
        Ok(u) => u,
        Err((status, reason)) => {
            refuse(&mut t, status).await;
            return finish(closed, reason);
        }
    };
    closed.src = upgrade.source.to_string();
    let Ok(slot) = open.clone().try_acquire_owned() else {
        refuse(&mut t, 503).await;
        return finish(closed, "full");
    };
    // Spec 12 lets a failed upstream either refuse the upgrade or close 1011 after it;
    // refusing (502) tells the client plainly that the realm cannot be reached.
    let upstream = match timeout_at(deadline, reach(&config.upstream, upgrade.source)).await {
        Ok(Ok(u)) => u,
        _ => {
            refuse(&mut t, 502).await;
            return finish(closed, "upstream");
        }
    };
    let reply = handshake::switching(&upgrade.accept);
    if !matches!(
        timeout_at(deadline, t.write_all(reply.as_bytes())).await,
        Ok(Ok(()))
    ) {
        return finish(closed, "dropped");
    }
    drop(handshake);
    let _ = t.set_nodelay(true);
    // A client may not send frames before the 101, but whatever followed the head is
    // the start of its stream, not discarded.
    let early = buf[head..filled].to_vec();
    drop(buf);
    let (bytes_in, bytes_out) = (AtomicU64::new(0), AtomicU64::new(0));
    let reason = bridge(t, upstream, early, config, &bytes_in, &bytes_out).await;
    drop(slot);
    closed.bytes_in = bytes_in.load(Relaxed);
    closed.bytes_out = bytes_out.load(Relaxed);
    finish(closed, reason)
}

/// Reads one request head of at most `HEAD_MAX` bytes: (request, head length, bytes read).
async fn read_head(
    t: &mut TcpStream,
    buf: &mut [u8],
) -> Result<(handshake::Request, usize, usize), (u16, &'static str)> {
    let mut filled = 0;
    loop {
        let n = t
            .read(&mut buf[filled..])
            .await
            .map_err(|_| (0, "dropped"))?;
        if n == 0 {
            return Err((0, "dropped"));
        }
        filled += n;
        match handshake::parse(&buf[..filled]) {
            Head::Complete(r, head) => return Ok((r, head, filled)),
            Head::Bad(status, reason) => return Err((status, reason)),
            Head::Partial if filled == buf.len() => return Err((431, "oversize")),
            Head::Partial => {}
        }
    }
}

/// Answers with a body-less response and closes; status 0 closes without one. Unread
/// input (an oversize head) is drained, a bounded amount, so closing does not reset
/// the connection before the peer reads the response.
async fn refuse(t: &mut TcpStream, status: u16) {
    if status != 0 {
        let _ = timeout(RESPONSE, async {
            t.write_all(handshake::response(status).as_bytes()).await?;
            t.shutdown().await?;
            let mut sink = [0u8; 4096];
            let mut drained = 0;
            while drained < 64 * 1024 {
                match t.read(&mut sink).await? {
                    0 => break,
                    n => drained += n,
                }
            }
            Ok::<_, std::io::Error>(())
        })
        .await;
    }
}

/// Connects to the server (resolving its name now) and names the player to it.
async fn reach(upstream: &str, source: IpAddr) -> std::io::Result<TcpStream> {
    let mut u = TcpStream::connect(upstream).await?;
    u.set_nodelay(true)?;
    let destination = u.peer_addr()?;
    u.write_all(&proxy::header(source, destination)).await?;
    Ok(u)
}

/// What the client's reader asks its writer to send.
enum Control {
    Pong(Vec<u8>),
    /// A close frame (None: empty), after which the writer stops.
    Close(Option<u16>),
}

/// Copies both ways until either side ends; returns the close log's reason.
async fn bridge(
    client: TcpStream,
    upstream: TcpStream,
    early: Vec<u8>,
    config: &Config,
    bytes_in: &AtomicU64,
    bytes_out: &AtomicU64,
) -> &'static str {
    let (cr, cw) = client.into_split();
    let (ur, uw) = upstream.into_split();
    let (tx, rx) = mpsc::channel(CONTROLS);
    let reader = BufReader::with_capacity(READ_BUFFER, Cursor::new(early).chain(cr));
    let inbound = inbound(reader, uw, tx, config.idle, bytes_in);
    let outbound = outbound(ur, cw, rx, config, bytes_out);
    tokio::pin!(inbound, outbound);
    tokio::select! {
        why = &mut inbound => {
            // The writer sends the queued close, then sees the channel end.
            let _ = timeout(GRACE, &mut outbound).await;
            why
        }
        why = &mut outbound => match why {
            Some(why) => {
                // Read the client's reply to our close, if it comes soon.
                let _ = timeout(GRACE, &mut inbound).await;
                why
            }
            None => timeout(GRACE, &mut inbound).await.unwrap_or("closed"),
        },
    }
}

/// Client frames to the server: payloads of binary and continuation frames, in order.
async fn inbound<R: AsyncRead + Unpin>(
    mut r: R,
    mut uw: OwnedWriteHalf,
    tx: mpsc::Sender<Control>,
    idle: Duration,
    count: &AtomicU64,
) -> &'static str {
    let mut payload = Vec::with_capacity(READ_BUFFER);
    let mut fragmented = false;
    loop {
        // The idle limit bounds a whole frame, so a trickled frame cannot hold the socket.
        let (fin, opcode) = match timeout(idle, frame::read(&mut r, &mut payload)).await {
            Err(_) => {
                let _ = tx.send(Control::Close(Some(frame::GOING_AWAY))).await;
                return "idle";
            }
            Ok(Err(_)) => return "dropped",
            Ok(Ok(frame::Read::Refuse(code, why))) => {
                let _ = tx.send(Control::Close(Some(code))).await;
                return why;
            }
            Ok(Ok(frame::Read::Frame { fin, opcode })) => (fin, opcode),
        };
        match opcode {
            frame::BINARY | frame::CONTINUATION => {
                // A new message inside a fragmented one, or a continuation of nothing.
                if fragmented == (opcode == frame::BINARY) {
                    let _ = tx.send(Control::Close(Some(frame::PROTOCOL_ERROR))).await;
                    return "protocol";
                }
                fragmented = !fin;
                if !payload.is_empty() {
                    if !matches!(timeout(idle, uw.write_all(&payload)).await, Ok(Ok(()))) {
                        let _ = tx.send(Control::Close(Some(frame::INTERNAL))).await;
                        return "upstream";
                    }
                    count.fetch_add(payload.len() as u64, Relaxed);
                }
            }
            frame::PING => {
                if tx.send(Control::Pong(payload.clone())).await.is_err() {
                    return "closed";
                }
            }
            frame::PONG => {}
            _ => {
                // A close: answer it and end the server's side.
                let _ = tx.send(Control::Close(frame::close_reply(&payload))).await;
                let _ = timeout(GRACE, uw.shutdown()).await;
                return "closed";
            }
        }
    }
}

/// The server's bytes to the client as binary frames, the reader's pongs and close, and
/// a ping every `ping_every`. None: ended because the reader did (its reason stands).
async fn outbound(
    mut ur: OwnedReadHalf,
    mut cw: OwnedWriteHalf,
    mut rx: mpsc::Receiver<Control>,
    config: &Config,
    count: &AtomicU64,
) -> Option<&'static str> {
    // Room for the largest header in front of each read.
    let mut buf = vec![0u8; 10 + FRAME_OUT];
    let mut ping = tokio::time::interval_at(Instant::now() + config.ping_every, config.ping_every);
    ping.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    // A client that stops reading for the idle time is gone.
    let stall = config.idle;
    loop {
        tokio::select! {
            n = ur.read(&mut buf[10..]) => {
                let n = match n {
                    Ok(0) => {
                        send(&mut cw, frame::CLOSE, &frame::NORMAL.to_be_bytes(), stall).await;
                        return Some("upstream_closed");
                    }
                    Ok(n) => n,
                    Err(_) => {
                        send(&mut cw, frame::CLOSE, &frame::INTERNAL.to_be_bytes(), stall).await;
                        return Some("upstream_error");
                    }
                };
                let (h, used) = frame::header(frame::BINARY, n);
                buf[10 - used..10].copy_from_slice(&h[..used]);
                if !matches!(timeout(stall, cw.write_all(&buf[10 - used..10 + n])).await, Ok(Ok(()))) {
                    return Some("stalled");
                }
                count.fetch_add(n as u64, Relaxed);
            }
            c = rx.recv() => match c {
                None => return None,
                Some(Control::Pong(p)) => {
                    if !send(&mut cw, frame::PONG, &p, stall).await {
                        return Some("stalled");
                    }
                }
                Some(Control::Close(code)) => {
                    let code = code.map(u16::to_be_bytes);
                    send(&mut cw, frame::CLOSE, code.as_ref().map_or(&[][..], |c| &c[..]), stall).await;
                    let _ = timeout(GRACE, cw.shutdown()).await;
                    return None;
                }
            },
            _ = ping.tick() => {
                if !send(&mut cw, frame::PING, &[], stall).await {
                    return Some("stalled");
                }
            }
        }
    }
}

/// Writes one small unmasked frame; false if the client did not take it in time.
async fn send(cw: &mut OwnedWriteHalf, opcode: u8, payload: &[u8], stall: Duration) -> bool {
    let (h, used) = frame::header(opcode, payload.len());
    let mut f = Vec::with_capacity(used + payload.len());
    f.extend_from_slice(&h[..used]);
    f.extend_from_slice(payload);
    matches!(timeout(stall, cw.write_all(&f)).await, Ok(Ok(())))
}
