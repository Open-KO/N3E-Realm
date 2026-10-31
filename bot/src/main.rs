//! realm-bot — see `specs/05-bot.md`. Start-up order: check the admin token, join the
//! `bot` consumer group, start the catalog and reminder timers, then the gateway (which
//! registers the guild commands on READY). SIGTERM stops reading the stream, lets the
//! entry in hand finish, and exits within 5 s.

use realm_bot::api::Outcome;
use realm_bot::commands::Bot;
use realm_bot::config::Config;
use realm_bot::discord::{gateway, Discord};
use realm_bot::events::Channel;
use realm_bot::stream::consume;
use realm_bot::text::{civil, now};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{watch, Notify};

/// The catalog: fetched at start and on every `realm.ready`; every 30 s while the realm
/// cannot give one.
async fn catalog(bot: Arc<Bot>, stale: Arc<Notify>) {
    loop {
        let ok = bot.refresh_catalog().await;
        let wait = if ok {
            Duration::from_secs(3600)
        } else {
            Duration::from_secs(30)
        };
        tokio::select! {
            _ = stale.notified() => {}
            _ = tokio::time::sleep(wait) => {}
        }
    }
}

/// The daily reminder: once per UTC day, in the hour `REALM_NAG_HOUR_UTC`.
async fn reminder(bot: Arc<Bot>, discord: Arc<Discord>) {
    let mut done: Option<(i64, u32, u32)> = None;
    loop {
        let (y, m, d, h, _, _) = civil(now());
        if h == bot.config.nag_hour_utc && done != Some((y, m, d)) {
            match bot.nag().await {
                Some(Some(text)) => {
                    if discord.post(Channel::Ops, &text).await {
                        done = Some((y, m, d));
                    }
                }
                Some(None) => done = Some((y, m, d)),
                None => {}
            }
        }
        tokio::time::sleep(Duration::from_secs(60)).await;
    }
}

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

#[tokio::main]
async fn main() {
    let config = match Config::from_env() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("realm-bot: {e}");
            std::process::exit(2);
        }
    };
    eprintln!(
        "realm-bot {} for guild {}, admin API {}",
        env!("CARGO_PKG_VERSION"),
        config.guild,
        config.admin_url
    );
    let discord = Arc::new(Discord::new(&config));
    let bot = Arc::new(Bot::new(config));
    match bot.admin.get("/v1/realm/status").await {
        Outcome::Ok(..) => eprintln!("admin API: token accepted"),
        Outcome::Rejected => {
            eprintln!("warning: the admin API rejected REALM_ADMIN_TOKEN; commands will say so")
        }
        _ => eprintln!("warning: the admin API is not answering yet; commands will say so"),
    }
    let (stop, stopped) = watch::channel(false);
    let stale = Arc::new(Notify::new());
    let consumer = tokio::spawn(consume(
        bot.clone(),
        discord.clone(),
        stale.clone(),
        stopped,
    ));
    tokio::spawn(catalog(bot.clone(), stale));
    tokio::spawn(reminder(bot.clone(), discord.clone()));
    let code = tokio::select! {
        _ = terminated() => 0,
        _ = gateway(bot, discord) => 1,
    };
    let _ = stop.send(true);
    if tokio::time::timeout(Duration::from_millis(4500), consumer)
        .await
        .is_err()
    {
        eprintln!("realm-bot: the stream consumer did not stop in time");
    }
    eprintln!("realm-bot: exiting");
    std::process::exit(code);
}
