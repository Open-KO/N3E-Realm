//! The `realm:events` consumer (spec 05 "Event stream consumer"): consumer group `bot`,
//! pending entries first, then new ones; an entry is acknowledged once its Discord
//! messages are sent (or it was decided to send none). At-least-once: a rare duplicate
//! announcement is acceptable, a lost one is not.

use crate::commands::Bot;
use crate::discord::Discord;
use crate::events::Post;
use redis::aio::MultiplexedConnection;
use redis::streams::StreamReadReply;
use redis::AsyncConnectionConfig;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{watch, Notify};

pub const STREAM: &str = "realm:events";
pub const GROUP: &str = "bot";
/// Entries per read.
const COUNT: usize = 32;
/// How long a read waits for new entries, in milliseconds.
const BLOCK_MS: u64 = 5000;
/// After a message Discord did not take, wait this long before reading pending again.
const RETRY: Duration = Duration::from_secs(5);

async fn connect(url: &str) -> redis::RedisResult<MultiplexedConnection> {
    let client = redis::Client::open(url)?;
    let config = AsyncConnectionConfig::new()
        .set_connection_timeout(Duration::from_secs(2))
        // A blocking read holds the connection for BLOCK_MS.
        .set_response_timeout(Duration::from_millis(BLOCK_MS + 3000));
    let mut con = client
        .get_multiplexed_async_connection_with_config(&config)
        .await?;
    let created: redis::RedisResult<()> = redis::cmd("XGROUP")
        .arg("CREATE")
        .arg(STREAM)
        .arg(GROUP)
        .arg("$")
        .arg("MKSTREAM")
        .query_async(&mut con)
        .await;
    if let Err(e) = created {
        if e.code() != Some("BUSYGROUP") {
            return Err(e);
        }
    }
    Ok(con)
}

/// Takes over every entry another consumer of the group left unacknowledged: there is
/// one bot per realm, and a recreated container has a new host name.
async fn adopt(con: &mut MultiplexedConnection, consumer: &str) -> redis::RedisResult<()> {
    let mut cursor = "0-0".to_string();
    for _ in 0..100 {
        let reply: redis::Value = redis::cmd("XAUTOCLAIM")
            .arg(STREAM)
            .arg(GROUP)
            .arg(consumer)
            .arg(0)
            .arg(&cursor)
            .arg("COUNT")
            .arg(100)
            .arg("JUSTID")
            .query_async(con)
            .await?;
        let next = match &reply {
            redis::Value::Array(items) => items
                .first()
                .and_then(|v| redis::from_redis_value::<String>(v).ok()),
            _ => None,
        };
        match next {
            Some(n) if n != "0-0" => cursor = n,
            _ => break,
        }
    }
    Ok(())
}

pub async fn consume(
    bot: Arc<Bot>,
    discord: Arc<Discord>,
    catalog_stale: Arc<Notify>,
    mut stop: watch::Receiver<bool>,
) {
    let mut con: Option<MultiplexedConnection> = None;
    // Read our own pending entries (id 0) before new ones (>).
    let mut pending = true;
    let mut last_complaint: Option<Instant> = None;
    // Messages still owed for entries already rendered: a retry must not render twice
    // (the relay's state would move twice) nor resend what already went out.
    let mut owed: HashMap<String, Vec<Post>> = HashMap::new();
    while !*stop.borrow() {
        if con.is_none() {
            match connect(&bot.config.redis).await {
                Ok(mut c) => match adopt(&mut c, &bot.config.consumer).await {
                    Ok(()) => {
                        eprintln!(
                            "stream: reading {STREAM} as {GROUP}/{}",
                            bot.config.consumer
                        );
                        con = Some(c);
                        pending = true;
                        last_complaint = None;
                    }
                    Err(e) => complain(&mut last_complaint, &e),
                },
                Err(e) => complain(&mut last_complaint, &e),
            }
            if con.is_none() {
                tokio::select! {
                    _ = stop.changed() => break,
                    _ = tokio::time::sleep(Duration::from_secs(1)) => continue,
                }
            }
        }
        let c = con.as_mut().unwrap();
        let id = if pending { "0" } else { ">" };
        let mut read = redis::cmd("XREADGROUP");
        read.arg("GROUP")
            .arg(GROUP)
            .arg(&bot.config.consumer)
            .arg("COUNT")
            .arg(COUNT);
        if !pending {
            read.arg("BLOCK").arg(BLOCK_MS);
        }
        read.arg("STREAMS").arg(STREAM).arg(id);
        let reply: redis::RedisResult<Option<StreamReadReply>> = tokio::select! {
            _ = stop.changed() => break,
            r = read.query_async(c) => r,
        };
        let entries = match reply {
            Ok(r) => r
                .map(|r| r.keys.into_iter().flat_map(|k| k.ids).collect::<Vec<_>>())
                .unwrap_or_default(),
            Err(e) => {
                complain(&mut last_complaint, &e);
                con = None;
                continue;
            }
        };
        if pending && entries.is_empty() {
            pending = false;
            continue;
        }
        let mut failed = false;
        for entry in entries {
            if *stop.borrow() {
                break;
            }
            let posts = match owed.remove(&entry.id) {
                Some(p) => p,
                None => {
                    let kind: String = entry.get("type").unwrap_or_default();
                    let data: Value = entry
                        .get::<String>("data")
                        .and_then(|d| serde_json::from_str(&d).ok())
                        .unwrap_or(Value::Null);
                    if kind == "realm.ready" {
                        catalog_stale.notify_one();
                    }
                    let by = |k: &str, d: &Value| bot.by(k, d);
                    let posts = bot.relay.lock().unwrap().render(&kind, &data, &by);
                    posts
                }
            };
            let mut left = posts.into_iter();
            while let Some(post) = left.next() {
                if !discord.post(post.channel, &post.text).await {
                    let mut rest = vec![post];
                    rest.extend(left);
                    if owed.len() < 1024 {
                        owed.insert(entry.id.clone(), rest);
                    }
                    failed = true;
                    break;
                }
            }
            if failed {
                // Keep order: the rest of this read stays pending and comes back first.
                break;
            }
            let acked: redis::RedisResult<i64> = redis::cmd("XACK")
                .arg(STREAM)
                .arg(GROUP)
                .arg(&entry.id)
                .query_async(c)
                .await;
            if let Err(e) = acked {
                complain(&mut last_complaint, &e);
                con = None;
                break;
            }
        }
        if failed {
            pending = true;
            tokio::select! {
                _ = stop.changed() => break,
                _ = tokio::time::sleep(RETRY) => {}
            }
        }
    }
    eprintln!("stream: stopped");
}

/// Redis trouble, logged at most once a minute.
fn complain(last: &mut Option<Instant>, e: &redis::RedisError) {
    if last.is_none_or(|t| t.elapsed() >= Duration::from_secs(60)) {
        eprintln!("stream: redis unavailable ({e}); commands still work, events wait");
        *last = Some(Instant::now());
    }
}
