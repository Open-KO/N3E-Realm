//! realm-edge — see `specs/12-edge.md` and `lib.rs`. `realm-edge health` asks the
//! running bridge's `/live` over loopback, for the compose healthcheck (the image has no
//! curl); SIGTERM stops it at once, and players reconnect with their session token.

use realm_edge::config::{self, Config};
use realm_edge::{serve, Closed, Log};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::time::timeout;

async fn terminated() {
    #[cfg(unix)]
    {
        let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("a SIGTERM handler");
        tokio::select! {
            _ = term.recv() => {}
            _ = tokio::signal::ctrl_c() => {}
        }
    }
    #[cfg(not(unix))]
    let _ = tokio::signal::ctrl_c().await;
}

/// `GET /live` on the listener's port over loopback (an unspecified listen address), or
/// on the listen address itself.
async fn health() -> Result<(), String> {
    let listen = config::listen(
        std::env::var("REALM_EDGE_LISTEN")
            .ok()
            .filter(|v| !v.trim().is_empty()),
    )?;
    let ip = match listen.ip() {
        IpAddr::V4(a) if a.is_unspecified() => IpAddr::V4(Ipv4Addr::LOCALHOST),
        IpAddr::V6(a) if a.is_unspecified() => IpAddr::V6(Ipv6Addr::LOCALHOST),
        a => a,
    };
    let probe = async {
        let mut s = TcpStream::connect(SocketAddr::new(ip, listen.port())).await?;
        s.write_all(b"GET /live HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            .await?;
        let mut b = [0u8; 64];
        let n = s.read(&mut b).await?;
        Ok::<_, std::io::Error>(b[..n].starts_with(b"HTTP/1.1 200"))
    };
    match timeout(Duration::from_secs(2), probe).await {
        Ok(Ok(true)) => Ok(()),
        Ok(Ok(false)) => Err("not live".into()),
        Ok(Err(e)) => Err(e.to_string()),
        Err(_) => Err("timed out".into()),
    }
}

#[tokio::main]
async fn main() {
    if std::env::args().nth(1).as_deref() == Some("health") {
        if let Err(e) = health().await {
            eprintln!("realm-edge health: {e}");
            std::process::exit(1);
        }
        return;
    }
    let config = match Config::from_env() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("realm-edge: {e}");
            std::process::exit(2);
        }
    };
    let listener = match TcpListener::bind(config.listen).await {
        Ok(l) => l,
        Err(e) => {
            eprintln!("realm-edge: cannot listen on {}: {e}", config.listen);
            std::process::exit(1);
        }
    };
    eprintln!(
        "realm-edge {} on {}, upstream {}, at most {} connections",
        env!("CARGO_PKG_VERSION"),
        config.listen,
        config.upstream,
        config.max_connections
    );
    let log: Log = Arc::new(|c: &Closed| eprintln!("{c}"));
    tokio::select! {
        r = serve(listener, Arc::new(config), log) => {
            if let Err(e) = r {
                eprintln!("realm-edge: {e}");
                std::process::exit(1);
            }
        }
        _ = terminated() => eprintln!("realm-edge: stopping"),
    }
}
