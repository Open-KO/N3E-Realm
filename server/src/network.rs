use crate::{
    content::{bad, Release, Result},
    wire::{self, envelope::Body, Envelope},
};
use openssl::ssl::{Ssl, SslAcceptor, SslFiletype, SslMethod};
use prost::Message;
use std::{pin::Pin, sync::Arc, time::Duration};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::Semaphore,
    time::{timeout, Instant},
};
use tokio_openssl::SslStream;
const LIMIT: usize = 65536;
const DEADLINE: Duration = Duration::from_secs(2);
/// The Envelope body field numbers of the client requests an Error can refuse
/// (PQ-405, D-208): `Error.request` names the one a refusal answers, so a client
/// shows it on that feature only. `request_tags_match_the_wire` pins them.
pub mod request {
    pub const CHAT: u32 = 11;
    pub const MOVE: u32 = 9;
    pub const ADMIN: u32 = 28;
    pub const PRIVATE_MESSAGE: u32 = 31;
    pub const BAG: u32 = 32;
    pub const STORAGE: u32 = 34;
    pub const STORAGE_AUTH: u32 = 36;
    pub const FRIEND: u32 = 38;
    pub const FRIEND_PRESENCE: u32 = 40;
    pub const PARTY: u32 = 42;
    pub const REST: u32 = 45;
}
/// An Error that answers no single request: handshake, login and connection
/// limits (`request` 0).
pub fn error(code: i32, detail: &str) -> Envelope {
    refusal(code, 0, detail)
}
/// An Error refusing the client request whose Envelope field number is `request`.
pub fn refusal(code: i32, request: u32, detail: &str) -> Envelope {
    Envelope {
        body: Some(Body::Error(wire::Error {
            code,
            detail: detail.into(),
            request,
        })),
    }
}
async fn read(s: &mut (impl tokio::io::AsyncRead + Unpin)) -> Result<(Envelope, usize)> {
    timeout(DEADLINE, async {
        let n = s.read_u32().await? as usize;
        if n == 0 || n > LIMIT {
            return Err(bad("inbound frame bound"));
        }
        let mut b = vec![0; n];
        s.read_exact(&mut b).await?;
        Ok((Envelope::decode(b.as_slice())?, n))
    })
    .await?
}
async fn send(s: &mut (impl tokio::io::AsyncWrite + Unpin), e: Envelope) -> Result<()> {
    let b = e.encode_to_vec();
    if b.is_empty() || b.len() > LIMIT {
        return Err(bad("outbound frame bound"));
    }
    timeout(DEADLINE, async {
        s.write_u32(b.len() as u32).await?;
        s.write_all(&b).await?;
        Ok::<_, std::io::Error>(())
    })
    .await??;
    Ok(())
}
/// One stderr line per refused handshake (PQ-368), with the reason the client
/// is not told in detail (`realm not ready` names the failed readiness part),
/// and one per session the server ends itself (PQ-427). At most
/// `REFUSALS_PER_SECOND` lines of each kind a second, so a client cannot flood
/// the log; the next line written counts the ones left out.
const REFUSALS_PER_SECOND: u32 = 10;
#[derive(Default)]
struct Lines {
    window: Option<std::time::Instant>,
    lines: u32,
    skipped: u64,
}
impl Lines {
    /// `text`, or None when this second's lines are spent; `left_out` names
    /// what the count of skipped lines counts.
    fn line(&mut self, now: std::time::Instant, text: String, left_out: &str) -> Option<String> {
        if self.window.is_none_or(|w| now.duration_since(w) >= Duration::from_secs(1)) {
            (self.window, self.lines) = (Some(now), 0);
        }
        if self.lines >= REFUSALS_PER_SECOND {
            self.skipped += 1;
            return None;
        }
        self.lines += 1;
        Some(match std::mem::take(&mut self.skipped) {
            0 => text,
            n => format!("{text} ({n} earlier {left_out} not logged)"),
        })
    }
}
fn bounded(lines: &std::sync::Mutex<Lines>, text: String, left_out: &str) {
    let line = lines.lock().unwrap_or_else(|e| e.into_inner()).line(std::time::Instant::now(), text, left_out);
    if let Some(line) = line {
        eprintln!("{line}");
    }
}
fn refused(ip: &str, why: &str) {
    static REFUSALS: std::sync::Mutex<Lines> = std::sync::Mutex::new(Lines { window: None, lines: 0, skipped: 0 });
    bounded(&REFUSALS, refusal_line(ip, why), "refusals");
}
fn refusal_line(ip: &str, why: &str) -> String {
    format!("handshake refused from {ip}: {why}")
}
/// PQ-427: a session the server ended itself was closed without a line, so a
/// test peer met only EOF. `closed_by_server` names why (None when the client
/// ended it).
fn ended(ip: &str, character: Option<i64>, why: &str) {
    static ENDED: std::sync::Mutex<Lines> = std::sync::Mutex::new(Lines { window: None, lines: 0, skipped: 0 });
    bounded(&ENDED, ended_line(ip, character, why), "closes");
}
fn ended_line(ip: &str, character: Option<i64>, why: &str) -> String {
    let who = character.map(|c| format!(" (character {c})")).unwrap_or_default();
    format!("session from {ip}{who} closed by the server: {why}")
}
/// Why a session's reader or writer error ended it, when the server ended it:
/// a deadline, a full queue, a failed save or another server decision. None
/// when the client did: its stream ended, reset or broke, or its TLS failed.
fn closed_by_server(e: &(dyn std::error::Error + 'static)) -> Option<String> {
    use std::io::ErrorKind::*;
    if e.is::<tokio::time::error::Elapsed>() {
        return Some(format!("a frame not read or written within {} s", DEADLINE.as_secs()));
    }
    if e.is::<tokio::sync::mpsc::error::TrySendError<crate::simulation::Command>>() {
        return Some(format!("the world command queue was full ({e})"));
    }
    if e.is::<tokio::sync::mpsc::error::TrySendError<Envelope>>() {
        return Some(format!("the session's reply queue was full ({e})"));
    }
    if let Some(io) = e.downcast_ref::<std::io::Error>() {
        if matches!(io.kind(), UnexpectedEof | ConnectionReset | ConnectionAborted | BrokenPipe | NotConnected)
            || io.get_ref().is_some_and(|i| i.is::<openssl::ssl::Error>() || i.is::<openssl::error::ErrorStack>())
        {
            return None;
        }
    }
    Some(e.to_string())
}
#[cfg(test)]
mod refusal_tests {
    use super::*;
    #[test]
    fn refusal_lines_are_bounded_per_second_and_count_what_they_left_out() {
        let mut r = Lines::default();
        let mut line = |t, ip, why| r.line(t, refusal_line(ip, why), "refusals");
        let t = std::time::Instant::now();
        for i in 0..REFUSALS_PER_SECOND {
            assert_eq!(line(t, "10.0.0.1", "content release mismatch").as_deref(),
                       Some("handshake refused from 10.0.0.1: content release mismatch"), "{i}");
        }
        assert_eq!(line(t + Duration::from_millis(999), "10.0.0.1", "x"), None);
        assert_eq!(line(t + Duration::from_millis(999), "10.0.0.1", "x"), None);
        assert_eq!(line(t + Duration::from_secs(1), "10.0.0.2", "realm not ready: redis unreachable").as_deref(),
                   Some("handshake refused from 10.0.0.2: realm not ready: redis unreachable (2 earlier refusals not logged)"));
        assert_eq!(line(t + Duration::from_secs(1), "10.0.0.2", "y").as_deref(), Some("handshake refused from 10.0.0.2: y"));
    }
    #[test]
    fn session_close_lines_are_bounded_apart_from_refusals() {
        // PQ-427: a burst of closes spends its own lines, never the refusals'.
        let (mut closes, mut refusals) = (Lines::default(), Lines::default());
        let t = std::time::Instant::now();
        for _ in 0..REFUSALS_PER_SECOND + 3 {
            closes.line(t, ended_line("10.0.0.3", Some(7), "x"), "closes");
        }
        assert_eq!(refusals.line(t, refusal_line("10.0.0.3", "y"), "refusals").as_deref(),
                   Some("handshake refused from 10.0.0.3: y"));
        assert_eq!(closes.line(t + Duration::from_secs(1), ended_line("10.0.0.3", Some(7), "session rate limit"), "closes").as_deref(),
                   Some("session from 10.0.0.3 (character 7) closed by the server: session rate limit (3 earlier closes not logged)"));
        assert_eq!(ended_line("10.0.0.4", None, "z"), "session from 10.0.0.4 closed by the server: z");
    }
    #[tokio::test]
    async fn a_close_is_named_only_when_the_server_chose_it() {
        // PQ-427: the server's own reasons are named; the client's end of the
        // stream (EOF, reset, broken pipe, a TLS failure) is not.
        let elapsed = timeout(Duration::ZERO, std::future::pending::<()>()).await.unwrap_err();
        let named = |e: Box<dyn std::error::Error + Send + Sync>| closed_by_server(e.as_ref());
        assert_eq!(named(elapsed.into()).as_deref(), Some("a frame not read or written within 2 s"));
        assert_eq!(named(bad("realm ownership unavailable")).as_deref(), Some("realm ownership unavailable"));
        assert_eq!(named(bad("reliable queue overflow")).as_deref(), Some("reliable queue overflow"));
        let (tx, _rx) = tokio::sync::mpsc::channel::<Envelope>(1);
        tx.try_send(error(0, "a")).unwrap();
        let full = tx.try_send(error(0, "b")).unwrap_err();
        assert_eq!(named(full.into()).as_deref(), Some("the session's reply queue was full (no available capacity)"));
        for kind in [std::io::ErrorKind::UnexpectedEof, std::io::ErrorKind::ConnectionReset,
                     std::io::ErrorKind::ConnectionAborted, std::io::ErrorKind::BrokenPipe] {
            assert_eq!(named(std::io::Error::from(kind).into()), None, "{kind:?}");
        }
        let tls = std::io::Error::other(openssl::error::ErrorStack::get());
        assert_eq!(named(tls.into()), None);
    }
    #[test]
    fn request_tags_match_the_wire() {
        // PQ-405 (D-208): each constant is the field number its request is
        // encoded under, read back from an encoded Envelope (prost names none).
        let tag = |body: Body| {
            let b = Envelope { body: Some(body) }.encode_to_vec();
            let (mut key, mut shift) = (0u32, 0);
            for byte in b {
                key |= u32::from(byte & 0x7f) << shift;
                if byte & 0x80 == 0 {
                    break;
                }
                shift += 7;
            }
            key >> 3
        };
        for (want, body) in [
            (request::MOVE, Body::Move(Default::default())),
            (request::CHAT, Body::Chat(Default::default())),
            (request::ADMIN, Body::AdminRequest(Default::default())),
            (request::PRIVATE_MESSAGE, Body::PrivateMessage(Default::default())),
            (request::BAG, Body::BagRequest(Default::default())),
            (request::STORAGE, Body::StorageRequest(Default::default())),
            (request::STORAGE_AUTH, Body::StorageAuthRequest(Default::default())),
            (request::FRIEND, Body::FriendRequest(Default::default())),
            (request::FRIEND_PRESENCE, Body::FriendPresenceQuery(Default::default())),
            (request::PARTY, Body::PartyRequest(Default::default())),
            (request::REST, Body::Rest(Default::default())),
        ] {
            assert_eq!(tag(body.clone()), want, "{body:?}");
        }
        let Some(Body::Error(e)) = refusal(4, request::BAG, "inventory rate limit").body else { unreachable!() };
        assert_eq!((e.code, e.request, e.detail.as_str()), (4, 32, "inventory rate limit"));
        let Some(Body::Error(e)) = error(1, "unsupported protocol version").body else { unreachable!() };
        assert_eq!(e.request, 0, "a handshake refusal answers no request");
    }
}
#[derive(Clone)]
pub struct WorldService {
    pub db: crate::accounts::Database,
    pub owner: Arc<crate::accounts::Owner>,
    pub commands: tokio::sync::mpsc::Sender<crate::simulation::Command>,
    pub cache: Arc<crate::cache::Endpoint>,
    pub hashing: Arc<Semaphore>,
    /// Drain state and the logged-in count the admin API reports (spec 03).
    pub realm: Arc<crate::admin_api::Realm>,
}
async fn peer(
    t: TcpStream,
    a: Arc<SslAcceptor>,
    r: Arc<Release>,
    ready: Arc<crate::persistence::Health>,
    world: WorldService,
) -> Result<()> {
    use crate::{accounts, simulation::Command};
    use tokio::sync::{mpsc, oneshot, watch};
    let ip = t.peer_addr()?.ip().to_string();
    t.set_nodelay(true)?;
    socket2::SockRef::from(&t).set_send_buffer_size(8192)?;
    let mut s = SslStream::new(Ssl::new(a.context())?, t)?;
    timeout(DEADLINE, Pin::new(&mut s).accept()).await??;
    let (h, _) = read(&mut s).await?;
    let rejection = match h.body {
        Some(Body::Handshake(h)) if h.version != r.protocol => {
            Some(error(1, "unsupported protocol version"))
        }
        Some(Body::Handshake(h)) if h.game != r.game || h.content != r.hash.as_bytes() => {
            Some(error(2, "content release mismatch"))
        }
        Some(Body::Handshake(_)) => None,
        _ => Some(error(0, "handshake required")),
    };
    if let Some(e) = rejection {
        if let Some(Body::Error(ref x)) = e.body {
            refused(&ip, &x.detail);
        }
        send(&mut s, e).await?;
        return Ok(());
    }
    if let Some(why) = ready.unready() {
        refused(&ip, &format!("realm not ready: {why}"));
        send(&mut s, error(6, "realm not ready")).await?;
        return Ok(());
    }
    send(
        &mut s,
        Envelope {
            body: Some(Body::Snapshot(wire::Snapshot {
                tick: 0,
                echo: None,
            })),
        },
    )
    .await?;
    let (mut input, mut output) = tokio::io::split(s);
    let (out, mut reliable) = mpsc::channel::<Envelope>(32);
    let (view, mut latest) = watch::channel::<Option<wire::World>>(None);
    let writer = tokio::spawn(async move {
        loop {
            tokio::select! {
                biased;
                e=reliable.recv()=>match e {Some(e)=>send(&mut output,e).await?,None=>return Ok::<_,Box<dyn std::error::Error+Send+Sync>>(()),},
                changed=latest.changed()=>{if changed.is_err(){continue;} let value=latest.borrow_and_update().clone(); if let Some(v)=value{send(&mut output,Envelope{body:Some(Body::World(v))}).await?;}else{return Err(bad("reliable queue overflow"));}},
            }
        }
    });
    let mut account = None;
    // Counted in status.players from login until the socket ends.
    let mut _counted: Option<crate::admin_api::Player> = None;
    let mut selected: Option<accounts::Selected> = None;
    let mut window = Instant::now();
    let mut frames = 0;
    let mut bag_requests = 0;
    let mut bytes = 0;
    // PQ-427: the reason a session the server ends cleanly was ended, for its line.
    let mut kicked: Option<String> = None;
    let mut result: Result<()> = async {
        loop {
            if writer.is_finished() {
                return Err(bad("output peer closed"));
            }
            let (e, n) = read(&mut input).await?;
            if !ready.owned() {
                return Err(bad("realm ownership unavailable"));
            }
            if window.elapsed() >= Duration::from_secs(1) {
                window = Instant::now();
                frames = 0;
                bag_requests = 0;
                bytes = 0;
            }
            frames += 1;
            bytes += n;
            if frames > 100 || bytes > 1024 * 1024 {
                kicked = Some(format!(
                    "session rate limit: {frames} frames and {bytes} bytes read in {} ms (at most 100 frames or 1 MiB a second)",
                    window.elapsed().as_millis()
                ));
                out.try_send(error(4, "session rate limit"))?;
                break;
            }
            let response = match e.body {
                Some(Body::Login(l)) if account.is_none() => {
                    if !ready.ready() {
                        Some(error(6, "login dependencies unavailable"))
                    } else {
                        match crate::cache::login_allowed(
                            &world.cache,
                            &world.owner.realm,
                            &l.account,
                            &ip,
                        )
                        .await
                        {
                            Err(_) => Some(error(6, "login protections unavailable")),
                            Ok(false) => Some(error(4, "login rate limit")),
                            Ok(true) => match world.hashing.clone().try_acquire_owned() {
                                Err(_) => Some(error(4, "password worker busy")),
                                Ok(_permit) => {
                                    match accounts::login(&world.db, l.account, l.password).await {
                                        Ok(id) => {
                                            account = Some(id);
                                            _counted = Some(crate::admin_api::Player::new(world.realm.clone()));
                                            Some(Envelope {
                                                body: Some(Body::Characters(
                                                    world
                                                        .db
                                                        .list(id, world.owner.realm.clone())
                                                        .await?,
                                                )),
                                            })
                                        }
                                        Err(_) => Some(error(5, "invalid credentials")),
                                    }
                                }
                            },
                        }
                    }
                }
                Some(Body::CreateCharacter(c)) if account.is_some() && selected.is_none() => {
                    match world
                        .db
                        .create(
                            account.unwrap(),
                            c.name,
                            world.owner.clone(),
                            r.player_spawn()?,
                        )
                        .await
                    {
                        Ok(()) => Some(Envelope {
                            body: Some(Body::Characters(
                                world
                                    .db
                                    .list(account.unwrap(), world.owner.realm.clone())
                                    .await?,
                            )),
                        }),
                        Err(_) => Some(error(8, "character name invalid/taken or limit reached")),
                    }
                }
                Some(Body::SelectCharacter(c)) if account.is_some() && selected.is_none() => {
                    match world
                        .db
                        .select(account.unwrap(), c.id as i64, world.owner.clone())
                        .await
                    {
                        Err(_) => Some(error(7, "character not owned or already online")),
                        Ok(s) => {
                            selected = Some(s.clone());
                            let (tx, rx) = oneshot::channel();
                            let inventory = world
                                .db
                                .inventory(s.clone(), world.owner.clone(), r.rules.clone())
                                .await?;
                            let bag=if r.rules.inventory.as_ref().is_some_and(|p|p.stats.is_some()) {
                                world.db.bag(world.owner.clone(),s.clone(),r.rules.inventory.as_deref().cloned().unwrap(),r.rules.item.clone(),wire::BagRequest::default()).await?.state
                            } else {None};
                            // PQ-184 (D-152): the session's first authority read,
                            // off the tick, so a login does not show an operator
                            // unless this read's 500 ms lease lapses before the
                            // simulation admits the session (D-152).
                            let started = std::time::Instant::now();
                            let authority = {
                                let owner = world.owner.clone();
                                let id = s.id;
                                world.db.call(move |c| crate::turbo::read(c, &owner, &[id])).await?
                            }
                            .into_iter()
                            .next()
                            .map(|a| (started, a));
                            world.commands.try_send(Command::Join(
                                s,
                                inventory, bag, authority,
                                out.clone(),
                                view.clone(),
                                tx,
                            ))?;
                            if !rx.await? {
                                return Err(bad("world admission failed"));
                            }
                            None
                        }
                    }
                }
                Some(Body::Rest(q)) if selected.is_some() && r.rules.rest.is_some() => {
                    let s=selected.as_ref().unwrap();
                    world.commands.try_send(Command::Rest(s.id,s.generation,q))?;
                    None
                }
                Some(Body::Respawn(a)) if selected.is_some() => {
                    let s = selected.as_ref().unwrap();
                    world
                        .commands
                        .try_send(Command::Respawn(s.id, s.generation, a))?;
                    None
                }
                Some(Body::Action(a)) if selected.is_some() => {
                    let s = selected.as_ref().unwrap();
                    world
                        .commands
                        .try_send(Command::Action(s.id, s.generation, a, None))?;
                    None
                }
                Some(Body::AdminRequest(q)) if selected.is_some() && r.protocol >= 6 => {
                    let selected = selected.as_ref().unwrap().clone();
                    world
                        .commands
                        .try_send(Command::Admin(selected.id, selected.generation, q))?;
                    None
                }
                Some(Body::Claim(a)) if selected.is_some() && r.protocol >= 5 => {
                    let s = selected.as_ref().unwrap();
                    world
                        .commands
                        .try_send(Command::Claim(s.id, s.generation, a))?;
                    None
                }
                Some(Body::LootList(q)) if selected.is_some() && r.protocol >= 5 => {
                    Some(Envelope {
                        body: Some(Body::LootPage(
                            world
                                .db
                                .loot_page(
                                    world.owner.clone(),
                                    selected.as_ref().unwrap().clone(),
                                    q.after,
                                    r.protocol>=20,
                                )
                                .await?,
                        )),
                    })
                }
                Some(Body::ClaimStatus(q)) if selected.is_some() && r.protocol >= 5 => {
                    Some(Envelope {
                        body: Some(Body::ClaimResult(
                            world
                                .db
                                .claim_status(
                                    world.owner.clone(),
                                    selected.as_ref().unwrap().clone(),
                                    q.operation,
                                )
                                .await?,
                        )),
                    })
                }
                Some(Body::SettlementStatus(q)) if selected.is_some() && r.protocol >= 4 => {
                    let s = selected.as_ref().unwrap();
                    Some(Envelope {
                        body: Some(Body::SettlementResult(
                            world
                                .db
                                .settlement_status(s.clone(), world.owner.clone(), q.encounter)
                                .await?,
                        )),
                    })
                }
                Some(Body::RewardStatus(q)) if selected.is_some() => {
                    let s = selected.as_ref().unwrap();
                    Some(Envelope {
                        body: Some(Body::RewardResult(
                            world
                                .db
                                .reward_status(s.clone(), world.owner.clone(), q.operation)
                                .await?,
                        )),
                    })
                }
                Some(Body::Move(m)) if selected.is_some() => {
                    let s = selected.as_ref().unwrap();
                    world
                        .commands
                        .try_send(Command::Move(s.id, s.generation, m))?;
                    None
                }
                Some(Body::Chat(c)) if selected.is_some() => {
                    let s = selected.as_ref().unwrap();
                    world
                        .commands
                        .try_send(Command::Chat(s.id, s.generation, c.text, None))?;
                    None
                }
                Some(Body::PartyRequest(q)) if selected.is_some() && r.rules.party.is_some() => {
                    bag_requests+=1;if bag_requests>10{out.try_send(refusal(4,request::PARTY,"social rate limit"))?;continue;}
                    let s=selected.as_ref().unwrap();world.commands.try_send(Command::Party(s.id,s.generation,q))?;None
                }
                Some(Body::FriendRequest(q)) if selected.is_some() && r.rules.friends.is_some() => {
                    bag_requests+=1;if bag_requests>10{out.try_send(refusal(4,request::FRIEND,"social rate limit"))?;continue;}
                    let selected=selected.as_ref().unwrap().clone();
                    let admission=if q.operation==1 {let(reply,wait)=oneshot::channel();world.commands.try_send(Command::FriendTarget(selected.id,selected.generation,q.name.clone(),reply))?;timeout(DEADLINE,wait).await.ok().and_then(|v|v.ok()).flatten()}else{None};
                    let(owner,policy)=(world.owner.clone(),r.rules.friends.as_deref().cloned().unwrap());
                    match world.db.call(move|c|crate::friends::execute(c,&owner,&selected,&policy,&q,admission.as_ref())).await {
                        Ok(result)=>Some(Envelope{body:Some(Body::FriendResult(result))}),
                        Err(_)=>Some(refusal(4,request::FRIEND,"friend request unavailable or invalid")),
                    }
                }
                Some(Body::FriendPresenceQuery(q)) if selected.is_some() && r.rules.friends.is_some() => {
                    bag_requests+=1;if bag_requests>10{out.try_send(refusal(4,request::FRIEND_PRESENCE,"social rate limit"))?;continue;}
                    let s=selected.as_ref().unwrap();world.commands.try_send(Command::FriendPresence(s.id,s.generation,q))?;None
                }
                Some(Body::StorageAuthRequest(q)) if selected.is_some() && r.rules.inventory.as_ref().is_some_and(|p|p.storage.as_ref().is_some_and(|s|s.credential.is_some())) => {
                    bag_requests+=1;
                    if bag_requests>10 {out.try_send(refusal(4,request::STORAGE_AUTH,"inventory rate limit"))?;continue;}
                    let key=format!("warehouse:{}",account.unwrap());
                    if q.operation!=0 && !crate::cache::login_allowed(&world.cache,&world.owner.realm,&key,&ip).await.unwrap_or(false) {out.try_send(refusal(4,request::STORAGE_AUTH,"storage password rate limit"))?;continue;}
                    let Ok(_permit)=world.hashing.clone().try_acquire_owned() else {out.try_send(refusal(4,request::STORAGE_AUTH,"password worker busy"))?;continue;};
                    let s=selected.as_ref().unwrap();let(reply,wait)=oneshot::channel();
                    world.commands.try_send(Command::Commerce(s.id,s.generation,reply))?;
                    match timeout(DEADLINE,wait).await {
                        Ok(Ok(Some(admission)))=>match crate::storage_auth::execute(&world.db,world.owner.clone(),admission.selected,r.rules.inventory.as_deref().cloned().unwrap(),q,admission.issued).await {
                            Ok(result)=>Some(Envelope{body:Some(Body::StorageAuthResult(result))}),
                            Err(_)=>Some(refusal(4,request::STORAGE_AUTH,"storage credential unavailable or invalid request")),
                        },
                        _=>Some(refusal(4,request::STORAGE_AUTH,"storage credential unavailable")),
                    }
                }
                Some(Body::StorageRequest(q)) if selected.is_some() && r.rules.inventory.as_ref().is_some_and(|p|p.storage.is_some()) => {
                    bag_requests+=1;
                    if bag_requests>10{out.try_send(refusal(4,request::STORAGE,"inventory rate limit"))?;continue;}
                    let s=selected.as_ref().unwrap();world.commands.try_send(Command::Storage(s.id,s.generation,q))?;None
                }
                Some(Body::BagRequest(q)) if selected.is_some() && r.protocol >= 8 && r.rules.inventory.is_some() => {
                    bag_requests += 1;
                    if bag_requests > 10 { out.try_send(refusal(4,request::BAG,"inventory rate limit"))?; continue; }
                    if q.operation==9 && r.rules.consumables.is_some(){
                        let s=selected.as_ref().unwrap();world.commands.try_send(Command::Consume(s.id,s.generation,q))?;continue;
                    }
                    let result=if (2..=4).contains(&q.operation)||q.operation==8 {
                        let Some(policy)=r.rules.commerce.as_deref().cloned() else {out.try_send(refusal(4,request::BAG,"commerce unavailable"))?;continue;};
                        let s=selected.as_ref().unwrap();let (reply,wait)=oneshot::channel();
                        world.commands.try_send(Command::Commerce(s.id,s.generation,reply))?;
                        match timeout(DEADLINE,wait).await {
                            Ok(Ok(Some(admission)))=>world.db.commerce(world.owner.clone(),r.rules.inventory.as_deref().cloned().unwrap(),r.rules.item.clone(),q,policy,admission).await,
                            _=>Err(bad("merchant unavailable, out of range or not alive")),
                        }
                    } else {world.db.bag(world.owner.clone(), selected.as_ref().unwrap().clone(), r.rules.inventory.as_deref().cloned().unwrap(), r.rules.item.clone(), q).await};
                    match result {
                        Ok(result) => {
                            if r.protocol>=12 {if let Some(state)=&result.state {let s=selected.as_ref().unwrap();world.commands.try_send(Command::Equipment(s.id,s.generation,state.clone()))?;}}
                            Some(Envelope{body:Some(Body::BagResult(result))})
                        },
                        Err(_) => Some(refusal(4,request::BAG,"inventory unavailable or invalid request")),
                    }
                }
                Some(Body::PrivateMessage(c)) if selected.is_some() => {
                    let s = selected.as_ref().unwrap();
                    world.commands.try_send(Command::Chat(
                        s.id,
                        s.generation,
                        c.text,
                        Some(c.recipient),
                    ))?;
                    None
                }
                Some(Body::Ping(_)) => {
                    if let Some(s) = &selected {
                        let _ = crate::cache::presence(
                            &world.cache,
                            &world.owner.realm,
                            s.id,
                            s.generation,
                        )
                        .await;
                    }
                    None
                }
                Some(Body::Logout(_)) => break,
                _ => Some(error(5, "authenticate and select character first")),
            };
            if let Some(e) = response {
                out.try_send(e)?;
            }
        }
        Ok(())
    }
    .await;
    let character = selected.as_ref().map(|s| s.id);
    // Always detach and persist, including malformed frames, EOF and queue overflow.
    if let Some(s) = selected {
        let (tx, rx) = oneshot::channel();
        // Bounded wait is outside tick. If admission worker died, lease fences writes.
        if world
            .commands
            .send(Command::Leave(s.id, s.generation, tx))
            .await
            .is_ok()
        {
            let final_state = rx.await?.unwrap_or(s);
            if world
                .db
                .save(world.owner.clone(), vec![(final_state, false)])
                .await
                .is_err()
            {
                ready.invalidate();
                result = Err(bad("final position save failed"));
            }
        } else {
            result = Err(bad("world stopped before final save"));
        }
    }
    if result.is_ok() {
        let _ = out
            .send(Envelope {
                body: Some(Body::LoggedOut(wire::LoggedOut {})),
            })
            .await;
    }
    drop(out);
    let written = timeout(DEADLINE, writer).await;
    // PQ-427: one line when the server ended the session. A writer that failed
    // explains a reader that found it finished ("output peer closed"); a writer
    // that met the client's own close names nothing, nor does a reader that did.
    let why = match (kicked, &written, &result) {
        (Some(k), _, _) => Some(k),
        (None, Ok(Ok(Err(w))), _) => closed_by_server(w.as_ref()).map(|w| format!("writer: {w}")),
        (None, _, Err(e)) => closed_by_server(e.as_ref()),
        (None, _, Ok(())) => None,
    };
    if let Some(why) = why {
        ended(&ip, character, &why);
    }
    result
}
pub async fn serve(
    address: &str,
    cert: &str,
    key: &str,
    r: Arc<Release>,
    health: Arc<crate::persistence::Health>,
    world: WorldService,
) -> Result<()> {
    let mut a = SslAcceptor::mozilla_intermediate(SslMethod::tls_server())?;
    a.set_private_key_file(key, SslFiletype::PEM)?;
    a.set_certificate_chain_file(cert)?;
    a.check_private_key()?;
    let a = Arc::new(a.build());
    let listener = TcpListener::bind(address).await?;
    println!("LISTEN {}", listener.local_addr()?);
    health.listening.store(true, std::sync::atomic::Ordering::Relaxed);
    let slots = Arc::new(Semaphore::new(64));
    loop {
        let (t, _) = listener.accept().await?;
        let permit = match slots.clone().try_acquire_owned() {
            Ok(p) => p,
            Err(_) => continue,
        };
        let (a, r, h, w) = (a.clone(), r.clone(), health.clone(), world.clone());
        tokio::spawn(async move {
            let _permit = permit;
            let _ = peer(t, a, r, h, w).await;
        });
    }
}
