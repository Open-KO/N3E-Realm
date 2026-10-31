mod skills;
mod skill_runtime;
mod accounts;
mod inventory;
mod commerce;
mod repair;
mod equipment;
mod appearance;
mod attachments;
mod stats;
mod wear;
mod storage;
mod storage_auth;
mod friends;
mod party;
mod party_rewards;
mod party_loot;
mod drop_generation;
mod item_drops;
mod coin_loot;
#[cfg(test)] mod party_loot_tests;
#[cfg(test)]
mod coin_loot_tests;
#[cfg(test)]
mod item_drop_tests;
mod reward_upgrades;
mod administration;
mod admin_api;
mod admission;
mod cache;
mod clock;
mod content;
mod damage;
mod discord;
mod gameplay;
mod instance_ids;
mod life;
mod rest;
mod ranged_shot;
mod consumables;
mod presentation;
mod combat_animation;
mod loot;
mod collision;
mod move_queue;
mod movement;
mod network;
mod npc_ai;
mod npc_kill;
mod npc_record;
mod npc_trace;
mod persistence;
mod progression;
mod rewards;
mod rules;
mod sessions;
mod settlements;
mod simulation;
mod turbo;
mod view_frame;
mod wire {
    include!(concat!(env!("OUT_DIR"), "/n3e.rs"));
}
use content::{bad, Result};
use std::{
    path::Path,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    time::timeout,
};
/// Build identity (`N3E_BUILD_VERSION` at build time, else `dev`); reported by the
/// admin API's `status.version` (specs/03-admin-api.md).
pub const BUILD_VERSION: &str = env!("N3E_BUILD_VERSION");

fn env(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.into())
}
async fn health_http(
    address: &str,
    h: Arc<persistence::Health>,
    ticks: Arc<AtomicU64>,
    metrics: Arc<simulation::Metrics>,
) -> Result<()> {
    let l = TcpListener::bind(address).await?;
    loop {
        let (mut s, _) = l.accept().await?;
        let mut b = [0; 512];
        let n = match timeout(Duration::from_millis(100), s.read(&mut b)).await {
            Ok(Ok(n)) => n,
            _ => continue,
        };
        let request = std::str::from_utf8(&b[..n]).unwrap_or("");
        let ok = if request.starts_with("GET /live ") {
            true
        } else if request.starts_with("GET /ready ") {
            h.ready()
        } else {
            false
        };
        let body = format!(
            "ready={} ticks={} sessions={} rejected={} queue={} tick_us={} checkpoints={} tick_ms={} tick_max_us={} queue_max={} npcs={} ids={} views_trimmed={} views_over={}\n",
            h.ready(),
            ticks.load(Ordering::Relaxed),
            metrics.sessions.load(Ordering::Relaxed),
            metrics.rejected.load(Ordering::Relaxed),
            metrics.queue.load(Ordering::Relaxed),
            metrics.tick_us.load(Ordering::Relaxed),
            metrics.checkpoints.load(Ordering::Relaxed),
            clock::tick_ms(),
            metrics.tick_max_us.load(Ordering::Relaxed),
            metrics.queue_max.load(Ordering::Relaxed),
            metrics.npcs.load(Ordering::Relaxed),
            metrics.ids.load(Ordering::Relaxed),
            metrics.views_trimmed.load(Ordering::Relaxed),
            metrics.views_over.load(Ordering::Relaxed)
        );
        let response = format!(
            "HTTP/1.1 {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            if ok { "200 OK" } else { "503 Unavailable" },
            body.len(),
            body
        );
        let _ = timeout(Duration::from_millis(100), s.write_all(response.as_bytes())).await;
    }
}
/// PQ-215 collision tools, off the server path:
/// `--collision-probe FILE QUERIES` prints the decode identity, memory, load
/// time and, per `x z dx dz mode multiplier` line, the walkable ground and
/// one advance, for comparison with `n3e-collision-check`.
/// `--collision-compare FILE SAMPLES` checks the gathered answers against the
/// full scan of every triangle at deterministic sample points.
fn collision_tool(args: &[String]) -> Result<()> {
    if args.len() != 4 {
        return Err(bad("collision tool arguments"));
    }
    let start = Instant::now();
    let c = movement::Collision::read(Path::new(&args[2]))?;
    let load = start.elapsed();
    let (mut hash, mut lo, mut hi) = (0xcbf2_9ce4_8422_2325u64, [f32::INFINITY; 2], [f32::NEG_INFINITY; 2]);
    let mut all = Vec::new();
    let full = args[1] == "--collision-compare";
    c.each(|t| {
        for p in t {
            for v in p {
                for b in v.to_le_bytes() {
                    hash = (hash ^ u64::from(b)).wrapping_mul(0x100_0000_01b3);
                }
            }
            lo = [lo[0].min(p[0]), lo[1].min(p[2])];
            hi = [hi[0].max(p[0]), hi[1].max(p[2])];
        }
        if full {
            all.extend_from_slice(t);
        }
        true
    });
    println!(
        "collision triangles {} terrain {} hash {hash:016x} memory {} load_ms {:.1}",
        c.triangles(),
        u8::from(c.has_terrain()),
        c.memory(),
        load.as_secs_f64() * 1000.
    );
    let cfg = movement::Config { walk: 3., run: 6., backward: 1.5, radius: 0.35, height: 1.8, step_height: 0.4 };
    if full {
        let samples: u32 = args[3].parse()?;
        let mut seed = 0x2545_f491_4f6c_dd1du64;
        let mut f = || {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            (seed >> 40) as f32 / (1u64 << 24) as f32
        };
        let (mut supported, mut mismatches) = (0, 0);
        for _ in 0..samples {
            let x = lo[0] + (hi[0] - lo[0]) * f();
            let z = lo[1] + (hi[1] - lo[1]) * f();
            let g = movement::ground(&c, x, z);
            let mut same = g.to_bits() == movement::ground_soup(&all, x, z).to_bits()
                && movement::standable(&c, x, z) == movement::standable_soup(&all, x, z);
            let d = movement::direction(f() * 2. - 1., f() * 2. - 1.)?;
            if g.is_finite() {
                supported += 1;
                let p = [x, g, z];
                let (mode, m) = ((f() * 3.) as u32, 1. + 9. * f());
                same &= movement::advance_scaled(&c, p, d[0], d[1], mode, cfg, m)?
                    == movement::advance_soup(&all, p, d[0], d[1], mode, cfg, m)?;
                same &= movement::step(&c, p, d) == movement::step_soup(&all, p, d);
            }
            if !same {
                mismatches += 1;
                eprintln!("mismatch at {x} {z}");
            }
        }
        println!("compare samples {samples} supported {supported} mismatches {mismatches}");
        return if mismatches == 0 { Ok(()) } else { Err(bad("gathered collision differs from the full scan")) };
    }
    for line in std::fs::read_to_string(&args[3])?.lines() {
        let v: Vec<f32> = line.split_whitespace().map(str::parse).collect::<std::result::Result<_, _>>()?;
        if v.len() != 6 {
            return Err(bad("collision query line"));
        }
        let g = movement::ground(&c, v[0], v[1]);
        if g.is_finite() {
            let a = movement::advance_scaled(&c, [v[0], g, v[1]], v[2], v[3], v[4] as u32, cfg, v[5])?;
            println!("{g:.9} {:.9} {:.9} {:.9}", a[0], a[1], a[2]);
        } else {
            println!("none");
        }
    }
    Ok(())
}
#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    // PQ-115: a test tick is refused before anything else runs unless the realm
    // is disposable (clock.rs); every subcommand fails closed the same way.
    let test_tick = clock::configure(&env("N3E_REALM", "local")).map_err(|e| bad(&e))?;
    if args.get(1).map(String::as_str) == Some("health") {
        let mut s = TcpStream::connect("127.0.0.1:8080").await?;
        s.write_all(b"GET /ready HTTP/1.1\r\nHost: localhost\r\n\r\n")
            .await?;
        let mut b = [0; 128];
        let n = timeout(Duration::from_secs(2), s.read(&mut b)).await??;
        if !b[..n].starts_with(b"HTTP/1.1 200") {
            return Err(bad("not ready"));
        }
        return Ok(());
    }
    if args.get(1).map(String::as_str) == Some("--golden") {
        use prost::Message;
        for present in [false, true] {
            let e = wire::Envelope {
                body: Some(wire::envelope::Body::Input(wire::Input {
                    id: u64::MAX,
                    text: "雪🙂".into(),
                    movement: 0.,
                    optional_id: present.then_some(0),
                })),
            };
            std::fs::write(
                format!(
                    "{}-{}.bin",
                    args[2],
                    if present { "present" } else { "absent" }
                ),
                e.encode_to_vec(),
            )?;
        }
        let e = wire::Envelope {
            body: Some(wire::envelope::Body::Move(wire::Move {
                session: 63,
                seq: 127,
                mode: 0,
                x: -0.5,
                z: 1.,
                ..Default::default()
            })),
        };
        std::fs::write(format!("{}-move.bin", args[2]), e.encode_to_vec())?;
        let mut mode_message = e.clone();
        if let Some(wire::envelope::Body::Move(ref mut m)) = mode_message.body {
            m.mode = 1;
        }
        std::fs::write(
            format!("{}-move-mode.bin", args[2]),
            mode_message.encode_to_vec(),
        )?;
        let e = wire::Envelope {
            body: Some(wire::envelope::Body::Action(wire::Action {
                session: 63,
                seq: 127,
                target: 9223372036854775807,
                action: "fixture:action/strike".into(),
            })),
        };
        std::fs::write(format!("{}-action.bin", args[2]), e.encode_to_vec())?;
        let e = wire::Envelope {
            body: Some(wire::envelope::Body::Respawn(wire::Respawn {
                session: 63,
                seq: 127,
                entity: 9223372036854775807,
            })),
        };
        std::fs::write(format!("{}-respawn.bin", args[2]), e.encode_to_vec())?;
        let e = wire::Envelope {
            body: Some(wire::envelope::Body::World(wire::World {
                tick: 128,
                session: 63,
                self_: 127,
                entities: vec![wire::Entity {
                    id: 127,
                    respawn_tick: 129,
                    life_state: wire::LifeState::DeadReady as i32,
                    ..Default::default()
                }],
                ..Default::default()
            })),
        };
        std::fs::write(format!("{}-life.bin", args[2]), e.encode_to_vec())?;
        let e = wire::Envelope {
            body: Some(wire::envelope::Body::SettlementResult(
                wire::SettlementResult {
                    encounter: 127,
                    status: "entitled".into(),
                    awarded_xp: 6,
                    xp: 51,
                    curve_xp: 66,
                    level: 3,
                    revision: 1,
                    reason: 0,
                },
            )),
        };
        std::fs::write(format!("{}-settlement.bin", args[2]), e.encode_to_vec())?;
        let purchase=wire::Envelope{body:Some(wire::envelope::Body::BagRequest(wire::BagRequest{
            operation:2,request:"buy-1".into(),expected_revision:127,source:2,service:"fixture:shop/supplies".into(),item:"fixture:item/potion".into(),quantity:3,..Default::default()
        }))};
        std::fs::write(format!("{}-commerce.bin",args[2]),purchase.encode_to_vec())?;
        let bag = wire::Envelope { body: Some(wire::envelope::Body::BagRequest(wire::BagRequest {
            operation: 1, request: "move-1".into(), expected_revision: 127, source: 0, destination: 41, instance: 9223372036854775807, ..Default::default()
        })) };
        std::fs::write(format!("{}-bag.bin", args[2]), bag.encode_to_vec())?;
        let bag_state = wire::Envelope { body: Some(wire::envelope::Body::BagResult(wire::BagResult {
            request: "move-1".into(), status:"committed".into(), state:Some(wire::BagState {
                equipment:vec![],revision:128,capacity:2,currency:"fixture:currency/coin".into(),coins:100,slots:vec![wire::ItemStack::default(),wire::ItemStack{instance:9223372036854775807,item:"fixture:item/blade".into(),quantity:1,durability:80}],
            }),
        })) };
        std::fs::write(format!("{}-bag-state.bin", args[2]), bag_state.encode_to_vec())?;
        let gear=wire::Envelope{body:Some(wire::envelope::Body::BagResult(wire::BagResult{
            request:"equip-1".into(),status:"committed".into(),state:Some(wire::BagState{revision:129,capacity:1,currency:"fixture:currency/coin".into(),coins:100,slots:vec![wire::ItemStack::default()],equipment:vec![wire::ItemStack{instance:9223372036854775807,item:"fixture:item/blade".into(),quantity:1,durability:80},wire::ItemStack::default()]}),
        }))};
        std::fs::write(format!("{}-equipment.bin",args[2]),gear.encode_to_vec())?;
        let storage=wire::Envelope{body:Some(wire::envelope::Body::StorageRequest(wire::StorageRequest{operation:2,request:"bank-1".into(),bag_revision:128,storage_revision:129,service:"fixture:bank/main".into(),source:191,destination:63,instance:9223372036854775807,quantity:9999}))};
        std::fs::write(format!("{}-storage.bin",args[2]),storage.encode_to_vec())?;
        let storage=wire::Envelope{body:Some(wire::envelope::Body::StorageResult(wire::StorageResult{request:"bank-1".into(),status:"committed".into(),bag:Some(wire::BagState{revision:130,capacity:1,currency:"fixture:currency/coin".into(),coins:17,slots:vec![wire::ItemStack::default()],equipment:vec![]}),storage:Some(wire::StorageState{revision:131,capacity:2,coins:2100000000,slots:vec![wire::ItemStack{instance:9223372036854775807,item:"fixture:item/blade".into(),quantity:1,durability:80},wire::ItemStack::default()]}),inventory:None}))};
        std::fs::write(format!("{}-storage-state.bin",args[2]),storage.encode_to_vec())?;
        let credential=wire::Envelope{body:Some(wire::envelope::Body::StorageAuthRequest(wire::StorageAuthRequest{operation:2,request:"credential-1".into(),service:"fixture:bank/main".into(),password:"Original_123".into(),replacement:"Replacement_123".into()}))};
        std::fs::write(format!("{}-storage-auth.bin",args[2]),credential.encode_to_vec())?;
        let credential=wire::Envelope{body:Some(wire::envelope::Body::StorageAuthResult(wire::StorageAuthResult{request:"credential-1".into(),status:"changed".into(),revision:128,authorized_revision:129}))};
        std::fs::write(format!("{}-storage-auth-state.bin",args[2]),credential.encode_to_vec())?;
        let friend=wire::Envelope{body:Some(wire::envelope::Body::FriendRequest(wire::FriendRequest{operation:1,request:"friend-1".into(),expected_revision:129,name:"Peer".into()}))};
        std::fs::write(format!("{}-friends.bin",args[2]),friend.encode_to_vec())?;
        let friend=wire::Envelope{body:Some(wire::envelope::Body::FriendResult(wire::FriendResult{request:"friend-1".into(),status:"committed".into(),revision:130,capacity:24,entries:vec![wire::FriendEntry{slot:23,character:9223372036854775807,name:"Peer".into()}]}))};
        std::fs::write(format!("{}-friends-state.bin",args[2]),friend.encode_to_vec())?;
        let friend=wire::Envelope{body:Some(wire::envelope::Body::FriendPresence(wire::FriendPresence{sequence:63,tick:127,entries:vec![wire::FriendOnline{name:"Peer".into(),character:9223372036854775807,entity:128,online:true,in_party:true},wire::FriendOnline{name:"Missing".into(),..Default::default()}]}))};
        std::fs::write(format!("{}-friends-presence.bin",args[2]),friend.encode_to_vec())?;
        let party=wire::Envelope{body:Some(wire::envelope::Body::PartyRequest(wire::PartyRequest{sequence:63,operation:2,invitation:128,..Default::default()}))};
        std::fs::write(format!("{}-party.bin",args[2]),party.encode_to_vec())?;
        let party=wire::Envelope{body:Some(wire::envelope::Body::PartyState(wire::PartyState{tick:127,group:129,leader:9223372036854775807,members:vec![wire::PartyMember{slot:7,character:9223372036854775807,entity:128,name:"Peer".into(),level:30,health:70,max_health:100,resource:4,max_resource:20}],..Default::default()}))};
        std::fs::write(format!("{}-party-state.bin",args[2]),party.encode_to_vec())?;
        let party=wire::Envelope{body:Some(wire::envelope::Body::PartyState(wire::PartyState{tick:130,invitation:129,inviter:9223372036854775807,inviter_name:"Peer".into(),..Default::default()}))};
        std::fs::write(format!("{}-party-invitation.bin",args[2]),party.encode_to_vec())?;
        let party=wire::Envelope{body:Some(wire::envelope::Body::PartyResult(wire::PartyResult{sequence:63,status:"joined".into()}))};
        std::fs::write(format!("{}-party-result.bin",args[2]),party.encode_to_vec())?;
        // PQ-405 (D-208): a refusal names the request it answers (32 BagRequest).
        let refusal=wire::Envelope{body:Some(wire::envelope::Body::Error(wire::Error{code:4,detail:"inventory rate limit".into(),request:32}))};
        std::fs::write(format!("{}-error.bin",args[2]),refusal.encode_to_vec())?;
        // specs/02-auth-sessions.md: the Discord and session logins and their result.
        let token:Vec<u8>=(0u8..32).collect();
        let login=wire::Envelope{body:Some(wire::envelope::Body::DiscordLogin(wire::DiscordLogin{code:"c0de".into(),code_verifier:"verifier-0123456789abcdefghijklmnopqrstuvwxyzAB".into(),redirect_uri:"http://127.0.0.1:49152/callback".into(),client_label:"host".into()}))};
        std::fs::write(format!("{}-discord-login.bin",args[2]),login.encode_to_vec())?;
        let login=wire::Envelope{body:Some(wire::envelope::Body::SessionLogin(wire::SessionLogin{token:token.clone(),client_label:"host".into()}))};
        std::fs::write(format!("{}-session-login.bin",args[2]),login.encode_to_vec())?;
        let login=wire::Envelope{body:Some(wire::envelope::Body::LoginResult(wire::LoginResult{token,expires_at_unix:1_795_996_800,discord_id:"80351110224678912".into(),discord_name:"Nelly".into()}))};
        std::fs::write(format!("{}-login-result.bin",args[2]),login.encode_to_vec())?;
        // Spec 11: the character list with levels.
        let characters=wire::Envelope{body:Some(wire::envelope::Body::Characters(wire::Characters{characters:vec![wire::Character{id:129,name:"Nelly".into(),level:30},wire::Character{id:7,name:"Peer".into(),level:1}]}))};
        std::fs::write(format!("{}-characters.bin",args[2]),characters.encode_to_vec())?;
        let strike=wire::Envelope{body:Some(wire::envelope::Body::World(wire::World{self_:7,entities:vec![wire::Entity{id:7,strike_tick:100,strike_sequence:129,..Default::default()}],events:vec![wire::PresentationEvent{sequence:1,tick:100,actor:7,target:8,kind:2,style:2,request_sequence:129,..Default::default()}],..Default::default()}))};
        std::fs::write(format!("{}-strike.bin",args[2]),strike.encode_to_vec())?;
        // Wire30 (PQ-249): a templated NPC's looks key and maximum health.
        let template=wire::Envelope{body:Some(wire::envelope::Body::World(wire::World{self_:7,entities:vec![wire::Entity{id:129,name:"demo:creature/brute".into(),health:6,npc:true,looks:"demo:looks/brute".into(),max_health:100000,..Default::default()}],..Default::default()}))};
        std::fs::write(format!("{}-template.bin",args[2]),template.encode_to_vec())?;
        let stats=wire::Envelope{body:Some(wire::envelope::Body::World(wire::World{stats:Some(wire::DerivedStats{attack:129,defense:17,accuracy:1.625,evasion:2.25,max_health:32767,max_resource:1024,carry_limit:3050,attributes:vec![60,70,80,90,100],equipment_revision:129}),..Default::default()}))};
        std::fs::write(format!("{}-stats.bin",args[2]),stats.encode_to_vec())?;
        let private_request = wire::Envelope {
            body: Some(wire::envelope::Body::PrivateMessage(wire::PrivateMessage {
                recipient: "Peer".into(), text: "secret".into(),
            })),
        };
        std::fs::write(format!("{}-private.bin", args[2]), private_request.encode_to_vec())?;
        let e = wire::Envelope {
            body: Some(wire::envelope::Body::Claim(wire::Claim {
                session: 63,
                seq: 127,
                entity: 128,
                operation: 9223372036854775807,
                encounter: 129,
                item: "fixture:item/token".into(),
                quantity: 1,
            })),
        };
        std::fs::write(format!("{}-claim.bin", args[2]), e.encode_to_vec())?;
        let e = wire::Envelope {
            body: Some(wire::envelope::Body::AdminRequest(wire::AdminRequest {
                session: 63,
                id: "request-1".into(),
                operation: "publish".into(),
                expected: 127,
                base: "a".repeat(64),
                patch: vec![wire::PropertyValue {
                    key: "fixture:lighting.intensity".into(),
                    value: 0.5,
                }],
                reason: "golden".into(),
                ..Default::default()
            })),
        };
        std::fs::write(format!("{}-admin.bin", args[2]), e.encode_to_vec())?;
        return Ok(());
    }
    if matches!(args.get(1).map(String::as_str), Some("--collision-probe" | "--collision-compare")) {
        return collision_tool(&args);
    }
    if args.get(1).map(String::as_str) == Some("--walk-fixture") {
        let text = std::fs::read_to_string(&args[2])?;
        let mut fields = text.split_whitespace();
        let n: usize = fields.next().ok_or_else(|| bad("count"))?.parse()?;
        // The cooker's collision vertex cap, so a real map bake can be
        // compared against the C++ solver rather than a subset of it.
        if n > 196608 || n % 3 != 0 {
            return Err(bad("triangle bound"));
        }
        let values: Vec<f32> = fields
            .map(str::parse)
            .collect::<std::result::Result<_, _>>()?;
        if values.len() < n * 3 + 3 {
            return Err(bad("truncated fixture"));
        }
        let triangles: Vec<_> = values[..n * 3]
            .chunks_exact(3)
            .map(|v| [v[0], v[1], v[2]])
            .collect();
        let triangles = movement::Collision::soup(triangles)?;
        let mut p = [values[n * 3], values[n * 3 + 1], values[n * 3 + 2]];
        let cfg = if args.len() == 9 || args.len() == 10 {
            Some(
                movement::Config {
                    walk: args[3].parse()?,
                    run: args[4].parse()?,
                    backward: args[5].parse()?,
                    radius: args[6].parse()?,
                    height: args[7].parse()?,
                    step_height: args.get(8).ok_or_else(|| bad("policy args"))?.parse()?,
                }
                .validate()?,
            )
        } else {
            None
        };
        for d in values[n * 3 + 3..].chunks_exact(if cfg.is_some() { 3 } else { 2 }) {
            p = if let Some(cfg) = cfg {
                if !d[2].is_finite() || d[2] < 0. || d[2].fract() != 0. {
                    return Err(bad("mode"));
                }
                movement::advance_scaled(
                    &triangles,
                    p,
                    d[0],
                    d[1],
                    d[2] as u32,
                    cfg,
                    if args.len() == 10 {
                        args[9].parse()?
                    } else {
                        1.
                    },
                )?
            } else {
                movement::step(&triangles, p, movement::direction(d[0], d[1])?)
            };
            println!("{:.9} {:.9} {:.9}", p[0], p[1], p[2]);
        }
        return Ok(());
    }
    let db = env(
        "DATABASE_URL",
        "host=127.0.0.1 user=n3e password=n3e-local dbname=n3e",
    );
    if args.get(1).map(String::as_str) == Some("migrate") {
        return tokio::task::spawn_blocking(move || {
            if let Some(path) = args.get(2) {
                let sql = std::fs::read_to_string(path)?;
                persistence::migrate(&db, &[(1, &sql)])
            } else {
                persistence::migrate(&db, persistence::MIGRATIONS)
            }
        })
        .await?;
    }
    if args.get(1).map(String::as_str) == Some("account-create") {
        use std::io::{self, BufRead, Read};
        let name = args
            .get(2)
            .ok_or_else(|| bad("account-create NAME; password from stdin"))?
            .clone();
        let mut password = String::new();
        io::stdin().lock().take(130).read_line(&mut password)?;
        let password = password.trim_end_matches(['\r', '\n']).to_string();
        return tokio::task::spawn_blocking(move || accounts::provision(&db, &name, &password))
            .await?;
    }
    if args.get(1).map(String::as_str) == Some("admin") {
        let rest = args[2..].to_vec();
        let code = tokio::task::spawn_blocking(move || admin_api::cli(&db, &rest)).await??;
        std::process::exit(code);
    }
    if args.get(1).map(String::as_str) == Some("role") {
        if args.len() != 7 || !["grant", "revoke"].contains(&args[2].as_str()) {
            return Err(bad(
                "role grant|revoke ACCOUNT CHARACTER_ID REALM CAPABILITY",
            ));
        }
        return tokio::task::spawn_blocking(move || {
            let mut c = persistence::connect(&db)?;
            persistence::verify(&mut c)?;
            administration::role(
                &mut c,
                &args[3],
                args[4].parse()?,
                &args[5],
                &args[6],
                args[2] == "grant",
            )
        })
        .await?;
    }
    let package = std::env::var("N3E_PACKAGE")
        .map_err(|_| bad("set N3E_PACKAGE to a cooked release directory"))?;
    let r = Arc::new(content::load(Path::new(&package))?);
    if args.get(1).map(String::as_str)==Some("--repair-cost") {
        if args.len()!=5{return Err(bad("repair quote arguments"));}
        let policy=r.rules.commerce.as_ref().and_then(|p|p.repair.as_ref()).ok_or_else(||bad("repair policy unavailable"))?;
        println!("{}",policy.cost(args[2].parse()?,args[3].parse()?,args[4].parse()?).ok_or_else(||bad("invalid repair quote"))?);return Ok(());
    }
    if args.get(1).map(String::as_str) == Some("--check-content") {
        println!("{}", r.hash);
        for (x, z) in [(0., 0.), (1., 1.), (-1., 0.5)] {
            println!("height {x} {z} {}", r.height(x, z));
        }
        // PQ-465 (D-232): the skill range rule as the server applies it.
        if let Some(s) = &r.rules.skills {
            let plane = if s.reach.planar { "xz" } else { "3d" };
            println!("skills reach start={} hold={} plane={plane} radii={}", s.reach.start, s.reach.hold, s.radii);
        }
        return Ok(());
    }
    let realm = env("N3E_REALM", "local");
    if args.get(1).map(String::as_str)==Some("storage-password-init") {
        use std::io::{self,BufRead,Read};
        let name=args.get(2).ok_or_else(||bad("storage-password-init ACCOUNT; password from stdin"))?.clone();
        let mut password=String::new();io::stdin().lock().take(130).read_line(&mut password)?;
        let password=password.trim_end_matches(['\r','\n']).to_string();
        let policy=r.rules.inventory.as_deref().cloned().ok_or_else(||bad("storage unavailable"))?;
        return tokio::task::spawn_blocking(move||storage_auth::provision(&db,&name,&realm,&policy,&password)).await?;
    }
    if args.get(1).map(String::as_str)==Some("upgrade-progression") {
        if args.len()!=3 {return Err(bad("upgrade-progression OLD_PACKAGE; N3E_PACKAGE selects the destination"));}
        let old=content::load(Path::new(&args[2]))?;
        if old.game!=r.game {return Err(bad("reward upgrade game mismatch"));}

        return tokio::task::spawn_blocking(move|| {
            let mut c=persistence::connect(&db)?;persistence::verify(&mut c)?;
            let generation=persistence::acquire(&mut c,&realm,"offline-reward-upgrade")?;
            let o=accounts::Owner{realm,owner:"offline-reward-upgrade".into(),generation};
            let result=reward_upgrades::upgrade(&mut c,&o,&old,&r);
            persistence::release(&mut c,&o.realm,&o.owner,o.generation)?;
            println!("reward upgrade revision {}",result?);Ok(())
        }).await?;
    }
    if r.rules.progression.is_some()
        && (r.protocol == 4 || args.get(1).map(String::as_str) == Some("convert-progression"))
        && (env("N3E_TEST_PROGRESSION", "") != "disposable" || !realm.starts_with("test-"))
    {
        return Err(bad("contribution policy inactive: requires N3E_TEST_PROGRESSION=disposable and test- realm"));
    }
    if args.get(1).map(String::as_str) == Some("convert-progression") {
        let p = r
            .rules
            .progression
            .clone()
            .ok_or_else(|| bad("conversion needs progression package"))?;
        let game = r.game.clone();
        let divisor = r.rules.level_xp;
        return tokio::task::spawn_blocking(move || {
            let mut c = persistence::connect(&db)?;
            persistence::verify(&mut c)?;
            let generation = persistence::acquire(&mut c, &realm, "offline-conversion")?;
            let o = accounts::Owner {
                realm,
                owner: "offline-conversion".into(),
                generation,
            };
            let result = settlements::convert(&mut c, &o, &p, &game, divisor);
            persistence::release(&mut c, &o.realm, &o.owner, o.generation)?;
            result
        })
        .await?;
    }
    if let Some(ms) = test_tick {
        eprintln!(
            "WARNING: TEST-ONLY TICK SCALE ACTIVE: one simulation tick every {ms} ms of wall time instead of {} ms (N3E_TEST_TICK_MS, N3E_TEST_REALM=disposable, realm {realm}). Never a production configuration.",
            clock::TICK_MS
        );
    }
    // Refuse a public admin listener before taking anything (spec 03).
    let admin_address = env("N3E_ADMIN_LISTEN", admin_api::DEFAULT_LISTEN);
    admin_api::check_listen(&admin_address).await?;
    let limits = admission::Limits::from_env()?;
    // Spec 02: Discord, session and (test-only) legacy logins; refused on prod
    // before anything is taken.
    let login = Arc::new(sessions::Config::from_env(&env("N3E_REALM", "local"))?);
    let admin_db = db.clone();
    let h = Arc::new(persistence::Health::new());
    let ticks = Arc::new(AtomicU64::new(0));
    let metrics = Arc::new(simulation::Metrics::new());
    let realm = env("N3E_REALM", "local");
    let owner = format!(
        "{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos()
    );
    let health_address = env("N3E_HEALTH", "127.0.0.1:8080");
    let hh = h.clone();
    let tt = ticks.clone();
    let mm = metrics.clone();
    let health_task = tokio::spawn(async move { health_http(&health_address, hh, tt, mm).await });
    // Acquisition is outside simulation. Dedicated renewal thread remains independent
    // of bounded account/checkpoint worker load.
    let db_acquire = db;
    let realm_acquire = realm.clone();
    let owner_acquire = owner.clone();
    let policy_acquire = r.rules.progression.as_deref().cloned();
    let release_acquire = r.clone();
    let health_worker = h.clone();
    let (database, renewal, generation, lease_start, revision) = tokio::task::spawn_blocking(move || -> Result<_> {
        // Ride out Postgres starting or recovering (57P03, D-140).
        let mut c = persistence::connect_within(&db_acquire, persistence::START_WAIT)?;
        persistence::verify(&mut c)?;
        // The account/checkpoint worker's connection is open before the lease
        // is taken: if it cannot be opened, start-up fails here with its
        // error and takes nothing (D-141, PQ-156).
        let database = accounts::Database::start(db_acquire.clone(), health_worker)?;
        // The lease-renewal connection is open before the lease too: admission
        // (2 s from the attempt that took the lease) must not pay for a slow
        // name lookup, TCP connect or handshake, or the first renewal lands
        // after admission has ended and the realm exits once it has reported
        // ready (PQ-369, D-199). Like the worker it rides out 57P03 only.
        let renewal = persistence::connect_within(&db_acquire, persistence::START_WAIT)?;
        // Wait out a previous owner's lease (D-139); admission is measured
        // from the attempt that took ownership, not from the first attempt.
        let (generation, start) = persistence::acquire_within(
            &mut c,
            &realm_acquire,
            &owner_acquire,
            persistence::START_WAIT,
        )?;
        // Check policy only after acquisition, so an offline converter cannot
        // change it between validation and this process taking ownership.
        if let Err(error) =
            settlements::check_start(&mut c, &realm_acquire, policy_acquire.as_ref())
        {
            persistence::release(&mut c, &realm_acquire, &owner_acquire, generation)?;
            return Err(error);
        }
        if let Err(error)=inventory::check_start(&mut c, &realm_acquire, release_acquire.rules.inventory.as_deref()) {
            let _=persistence::release(&mut c,&realm_acquire,&owner_acquire,generation);
            return Err(error);
        }
        if let Err(error)=friends::check_start(&mut c,&realm_acquire,release_acquire.rules.friends.as_deref()) {
            let _=persistence::release(&mut c,&realm_acquire,&owner_acquire,generation);return Err(error);
        }
        let initial_owner = accounts::Owner {
            realm: realm_acquire.clone(),
            owner: owner_acquire.clone(),
            generation,
        };
        let revision = match administration::startup(&mut c, &initial_owner, &release_acquire) {
            Ok(s) => s,
            Err(e) => {
                persistence::release(&mut c, &realm_acquire, &owner_acquire, generation)?;
                return Err(e);
            }
        };
        Ok((database, renewal, generation, start, revision))
    })
    .await??;
    h.renew(lease_start);
    // PQ-368: how much of the first admission window start-up used.
    eprintln!(
        "realm {realm} generation {generation} acquired; start-up took {} ms of its 2000 ms admission",
        lease_start.elapsed().as_millis()
    );
    let owner = Arc::new(accounts::Owner {
        realm,
        owner,
        generation,
    });
    let wh = h.clone();
    let wo = owner.clone();
    let (worker_tx, worker) = tokio::sync::oneshot::channel();
    std::thread::spawn(move || {
        let outcome = (|| -> Result<()> {
            // Opened by start-up before the lease (PQ-369, D-199).
            let mut c = renewal;
            let mut last = lease_start;
            while !wh.stopped.load(Ordering::Relaxed) {
                // PQ-415 (D-215): the pause is cut to what is left of
                // admission, so a renewal that landed late (and reopened it)
                // is followed by the next one before admission ends.
                std::thread::sleep(persistence::renewal_pause(wh.admission_left()));
                if !wh.owned() {
                    eprintln!("lease renewal stopped: {}", wh.unready().unwrap_or_default());
                    return Err(bad("admission expired; restart required"));
                }
                // A renewal that only timed out on the lease row (behind
                // another process's takeover attempt; durable writes lock
                // realm_fence, D-145) is retried while admission lasts (D-142).
                let start = persistence::renew_within(&mut c, &wo.realm, &wo.owner, wo.generation, || wh.owned())
                    .map_err(|e| {
                        eprintln!("lease renewal failed: {e}");
                        wh.invalidate();
                        e
                    })?;
                // PQ-368: a renewal that came late in the 2 s admission is named.
                // PQ-414: so is one that started on time and landed late
                // (`landed` is never less than `gap`). One that landed after
                // admission closed (2 s from the previous successful start)
                // reopens it until 2 s after its own start; the next attempt
                // then starts after the pause `renewal_pause` gives for what
                // is left (PQ-415). One that took 2 s or more reopens nothing,
                // and the next loop ends the realm. The line names how long
                // admission was closed, how long it is open and the next pause.
                let gap = start - last;
                let landed = last.elapsed();
                if landed >= Duration::from_millis(1200) {
                    let closed = landed.saturating_sub(persistence::ADMISSION);
                    let left = (start + persistence::ADMISSION).saturating_duration_since(Instant::now());
                    let state = if left.is_zero() {
                        format!(
                            "; admission was closed for {} ms before it landed and stays closed \
                             (the attempt took 2000 ms or more), so the next loop ends the realm",
                            closed.as_millis()
                        )
                    } else {
                        let open = format!(
                            "is open for {} ms more; the next renewal starts in {} ms",
                            left.as_millis(),
                            persistence::renewal_pause(left).as_millis()
                        );
                        if closed.is_zero() {
                            format!("; admission {open}")
                        } else {
                            format!("; admission was closed for {} ms until it landed and {open}", closed.as_millis())
                        }
                    };
                    eprintln!(
                        "lease renewal started {} ms after the previous one and took {} ms (admission lasts 2000 ms){state}",
                        gap.as_millis(),
                        start.elapsed().as_millis(),
                    );
                }
                last = start;
                wh.renew(start);
            }
            Ok(())
        })();
        let _ = worker_tx.send(outcome);
    });
    let rh = h.clone();
    // One Redis endpoint for the probe and every request: its resolved address
    // is shared, so a slow name lookup fails none of them while Redis serves (D-198).
    let redis_endpoint = Arc::new(cache::Endpoint::new(env("REDIS_ADDRESS", "127.0.0.1:6379")));
    let probe_endpoint = redis_endpoint.clone();
    tokio::spawn(async move {
        let redis_address = probe_endpoint.name();
        // One missed probe keeps admission; two in a row close it (D-198).
        // Only changes are logged, so the line count stays bounded (PQ-368).
        let mut readiness = persistence::RedisReadiness::default();
        loop {
            let probe = cache::ping(&probe_endpoint).await;
            match (readiness.probe(probe.is_ok()), &probe) {
                (persistence::RedisChange::Up, _) => eprintln!("redis {redis_address} reachable"),
                (persistence::RedisChange::Missed, Err(e)) => eprintln!(
                    "redis {redis_address} probe failed: {e}; admission stays open until {} failures in a row",
                    persistence::REDIS_FAILURES
                ),
                (persistence::RedisChange::Down, Err(e)) => eprintln!("redis {redis_address} unreachable: {e}"),
                _ => {}
            }
            rh.redis.store(readiness.up(), Ordering::Relaxed);
            tokio::time::sleep(Duration::from_millis(300)).await;
        }
    });
    let admin_realm = Arc::new(admin_api::Realm::new(admin_api::Events::start(redis_endpoint.clone())));
    let gate = admission::Gate::new(limits, admin_realm.connections.clone());
    let (commands, rx) = tokio::sync::mpsc::channel(256);
    tokio::spawn(simulation::run(
        h.clone(),
        ticks,
        metrics,
        r.clone(),
        database.clone(),
        owner.clone(),
        revision,
        rx,
    ));
    let world = network::WorldService {
        db: database.clone(),
        owner: owner.clone(),
        commands: commands.clone(),
        cache: redis_endpoint,
        hashing: Arc::new(tokio::sync::Semaphore::new(2)),
        realm: admin_realm.clone(),
        login,
    };
    let admin = Arc::new(admin_api::Service::new(
        admin_db,
        admin_realm,
        h.clone(),
        world.cache.clone(),
        commands.clone(),
        r.hash.clone(),
        database.clone(),
        owner.realm.clone(),
    ));
    let admin_listener = TcpListener::bind(&admin_address).await?;
    tokio::spawn(admin_api::watch_readiness(admin.clone()));
    let admin_task = tokio::spawn(admin_api::serve(admin_listener, admin));
    let address = env("N3E_LISTEN", "127.0.0.1:7777");
    let cert = env("N3E_CERT", "deploy/local/server.pem");
    let key = env("N3E_KEY", "deploy/local/server.key");
    // A lease failure stops admission immediately and terminates for operator restart.
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    let outcome = tokio::select! {r=network::serve(&address,&cert,&key,r,h.clone(),world,gate)=>r,r=worker=>r?,r=health_task=>r?,r=admin_task=>r?,_=tokio::signal::ctrl_c()=>Ok(()),_=terminate.recv()=>Ok(())};
    // Drain tick state and commit final positions while renewal remains alive.
    let (tx, rx) = tokio::sync::oneshot::channel();
    if commands
        .send(simulation::Command::Shutdown(tx))
        .await
        .is_ok()
    {
        if let Ok(Ok(states)) = timeout(Duration::from_secs(3), rx).await {
            let positions = states.into_iter().map(|s| (s, false)).collect();
            let _ = timeout(
                Duration::from_secs(2),
                database.save(owner.clone(), positions),
            )
            .await;
        }
    }
    h.stopped.store(true, Ordering::Relaxed);
    h.invalidate();
    let release_owner = owner.clone();
    let _ = timeout(
        Duration::from_secs(2),
        database.call(move |c| {
            persistence::release(
                c,
                &release_owner.realm,
                &release_owner.owner,
                release_owner.generation,
            )
        }),
    )
    .await;
    outcome
}
