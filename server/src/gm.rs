//! In-game GM commands (RQ-213, specs/03-admin-api.md "In-game GM commands").
//!
//! A game master types a command in game chat; the server reads it only from a
//! character holding a GM capability (`HOLDER`, leased in turbo.rs, so the tick
//! decides whether a `+` line is a command without database I/O), then
//! authorises each command again here, off the tick, for its own capability
//! under the role lock, as `administration::execute` does. KO's `+` parser
//! (Ebenezer `0042c1ba`) answers its game master nothing; the realm answers the
//! issuer with one line (`Chat{notice: 3}`, Q128 (e)).
//!
//! This module knows no game's item or name: items are the package's, named by
//! their ids with the package's game prefix optional.
use crate::{
    accounts::{Owner, Selected},
    content::{bad, Release, Result},
    inventory, persistence, wire,
};
use prost::Message;

/// The capabilities that make a character's `+` line a command (spec 03's
/// command table): holding any one of them, the line is never relayed.
pub const HOLDER: [&str; 8] = [
    "gm.item",
    "gm.character",
    "gm.move",
    "gm.moderate",
    "gm.notice",
    "server.inspect",
    "entity.spawn",
    "entity.kill",
];

/// The longest verb a reply repeats, so every reply stays within the chat bound.
const VERB_ECHO: usize = 32;
/// `admin_audit.reason`'s bound.
const REASON: usize = 160;

/// A line this module reads as a command: a chat line whose first byte is `+`
/// (KO's chat handler `004989a8`).
pub fn is_command(text: &str) -> bool {
    text.as_bytes().first() == Some(&b'+')
}

/// What a command that passed its capability check did, for the `gm.command`
/// event (spec 03 "Event stream") and the ops relay.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Event {
    pub character_id: i64,
    pub character: String,
    pub account_id: i64,
    pub verb: &'static str,
    /// The named character's name, or empty when none was resolved.
    pub target: String,
    /// A machine word: `given`, or why nothing changed.
    pub result: &'static str,
}

/// One command's answer.
#[derive(Debug, Clone, PartialEq)]
pub struct Outcome {
    /// The issuer's one line; empty when the session is no longer the one that
    /// typed it (nothing is answered then).
    pub reply: String,
    pub event: Option<Event>,
    /// The bag a give changed: (character id, its state), for the simulation to
    /// hand to that character's session when it is in the world.
    pub bag: Option<(i64, wire::BagState)>,
}

impl Outcome {
    fn reply(reply: String) -> Self {
        Self {
            reply,
            event: None,
            bag: None,
        }
    }
}

/// `+give_item NAME ITEM [COUNT]`, parsed; or the usage line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Give<'a> {
    pub name: &'a str,
    pub item: &'a str,
    /// None: the default, 1.
    pub count: Option<u32>,
}

pub const GIVE_USAGE: &str = "Usage: +give_item NAME ITEM [COUNT]";

pub fn parse_give<'a>(args: &[&'a str]) -> Option<Give<'a>> {
    match args {
        [name, item] => Some(Give {
            name,
            item,
            count: None,
        }),
        [name, item, count] => count.parse().ok().map(|c| Give {
            name,
            item,
            count: Some(c),
        }),
        _ => None,
    }
}

/// The package item `item` names: its id, or its id without the `game:` prefix.
/// The reward token is not among them: its count is the progression's
/// (`character_progress.count`), which a bag record alone would not move.
pub fn item<'a>(
    policy: &'a inventory::Policy,
    game: &str,
    reward: &str,
    item: &str,
) -> Option<&'a inventory::Item> {
    let id = if item.contains(':') {
        item.to_string()
    } else {
        format!("{game}:{item}")
    };
    policy.items.iter().find(|i| i.id == id && i.id != reward)
}

/// The character of this realm `name` names, as a whisper's recipient: its exact
/// name, else the one name equal without regard to case. (id, account, name).
fn character(
    t: &mut postgres::Transaction<'_>,
    realm: &str,
    name: &str,
) -> Result<Option<(i64, i64, String)>> {
    if !crate::accounts::valid_name(name, 24) {
        return Ok(None);
    }
    let rows: Vec<(i64, i64, String)> = t
        .query(
            "SELECT id,account_id,name FROM characters WHERE realm=$1 AND lower(name)=lower($2) ORDER BY id LIMIT 8",
            &[&realm, &name],
        )?
        .iter()
        .map(|r| (r.get(0), r.get(1), r.get(2)))
        .collect();
    if let Some(exact) = rows.iter().find(|r| r.2 == name) {
        return Ok(Some(exact.clone()));
    }
    Ok(if rows.len() == 1 {
        rows.into_iter().next()
    } else {
        None
    })
}

fn echo(verb: &str) -> String {
    verb.chars().take(VERB_ECHO).collect()
}

/// Runs one command line typed by the session `s` (on the database worker,
/// never on the tick). The capability check, the change, its audit row and the
/// realm fence are one transaction; a refusal changes nothing.
pub fn execute(
    c: &mut postgres::Client,
    o: &Owner,
    s: &Selected,
    r: &Release,
    line: &str,
) -> Result<Outcome> {
    let mut words = line.split_whitespace();
    let typed = words.next().unwrap_or("+");
    let args: Vec<&str> = words.collect();
    let mut t = c.transaction()?;
    crate::administration::lock_role(&mut t, s.id)?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    let Some(actor) = t.query_opt(
        "SELECT account_id,name FROM characters WHERE id=$1 AND realm=$2 AND session_generation=$3 AND realm_generation=$4 AND online FOR UPDATE",
        &[&s.id, &o.realm, &s.generation, &o.generation],
    )?
    else {
        return Ok(Outcome::reply(String::new()));
    };
    let (account, issuer): (i64, String) = (actor.get(0), actor.get(1));
    let (verb, capability) = match typed {
        "+give_item" => ("give_item", "gm.item"),
        _ => {
            eprintln!("gm by={issuer} verb=unknown target=- result=unknown");
            return Ok(Outcome::reply(format!("Unknown command {}.", echo(typed))));
        }
    };
    let held = t
        .query_opt(
            "SELECT 1 FROM character_roles WHERE character_id=$1 AND realm=$2 AND zone='*' AND capability=$3",
            &[&s.id, &o.realm, &capability],
        )?
        .is_some();
    if !held {
        // As a denied `kill`: no audit row, only the log line.
        eprintln!("gm by={issuer} verb={verb} target=- result=denied");
        return Ok(Outcome::reply(format!("You may not use +{verb}.")));
    }
    let event = |target: &str, result| Event {
        character_id: s.id,
        character: issuer.clone(),
        account_id: account,
        verb,
        target: target.to_string(),
        result,
    };
    let refuse = |target: &str, result: &'static str, reply: String| {
        eprintln!(
            "gm by={issuer} verb={verb} target={} result={result}",
            if target.is_empty() { "-" } else { target }
        );
        Ok(Outcome {
            reply,
            event: Some(event(target, result)),
            bag: None,
        })
    };
    let Some(give) = parse_give(&args) else {
        return refuse("", "usage", GIVE_USAGE.into());
    };
    let Some((target, _, name)) = character(&mut t, &o.realm, give.name)? else {
        return refuse(
            "",
            "no_character",
            format!("No character named {}.", echo(give.name)),
        );
    };
    let found = r
        .rules
        .inventory
        .as_deref()
        .and_then(|p| item(p, &r.game, &r.rules.item, give.item).map(|i| (p, i)));
    let Some((policy, definition)) = found else {
        return refuse(&name, "no_item", format!("No item {}.", echo(give.item)));
    };
    let count = give.count.unwrap_or(1);
    if !(1..=definition.stack).contains(&count) {
        return refuse(
            &name,
            "bad_count",
            format!(
                "COUNT for {} is 1 to {}.",
                definition.label, definition.stack
            ),
        );
    }
    // A character that never entered the world has no bag and no progression
    // row to make one from (its first entry makes both).
    let materialized: bool = t
        .query_one(
            "SELECT EXISTS(SELECT 1 FROM character_bags WHERE character_id=$1 AND realm=$2) \
             OR EXISTS(SELECT 1 FROM character_progress WHERE character_id=$1)",
            &[&target, &o.realm],
        )?
        .get(0);
    if !materialized {
        return refuse(&name, "no_bag", format!("{name} has no bag yet."));
    }
    let selected = Selected {
        id: target,
        generation: 0,
        life_revision: 0,
        dead: false,
        ready_ticks: 0,
        specialty: None,
        entity: Default::default(),
    };
    let mut state = inventory::load(&mut t, &selected, o, policy, &r.rules.item)?;
    let before = state.encode_to_vec();
    let Some(slot) = state.slots.iter().position(|v| v.instance == 0) else {
        return refuse(&name, "bag_full", format!("{name}'s bag is full."));
    };
    state.slots[slot] = wire::ItemStack {
        instance: inventory::serial(&mut t)?,
        item: definition.id.clone(),
        quantity: count,
        durability: definition.durability,
    };
    state.revision = state
        .revision
        .checked_add(1)
        .ok_or_else(|| bad("bag revision overflow"))?;
    policy.validate(&state)?;
    inventory::save(&mut t, target, &state)?;
    let revision: i64 = t
        .query_one(
            "SELECT revision FROM world_revisions WHERE realm=$1 ORDER BY revision DESC LIMIT 1",
            &[&o.realm],
        )?
        .get(0);
    let mut serial = [0u8; 8];
    openssl::rand::rand_bytes(&mut serial)?;
    let request = format!("gm-{:016x}", u64::from_le_bytes(serial));
    let reason: String = line.chars().take(REASON).collect();
    t.execute(
        "INSERT INTO admin_audit(realm,account_id,character_id,request,revision,target,reason,before_state,after_state,outcome) \
         VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
        &[
            &o.realm,
            &account,
            &s.id,
            &request,
            &revision,
            &format!("character:{target}"),
            &reason,
            &before,
            &state.encode_to_vec(),
            &format!("gm_{verb}"),
        ],
    )?;
    persistence::fence(&mut t, &o.realm, &o.owner, o.generation)?;
    t.commit()?;
    eprintln!("gm by={issuer} verb={verb} target=character:{target} result=given");
    Ok(Outcome {
        reply: format!("Gave {name} {count} x {}.", definition.label),
        event: Some(event(&name, "given")),
        bag: Some((target, state)),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy() -> inventory::Policy {
        let item = |id: &str, label: &str, stack| inventory::Item {
            id: id.into(),
            label: label.into(),
            stack,
            durability: 0,
            starting: 0,
        };
        inventory::Policy {
            storage: None,
            wear: None,
            stats: None,
            thresholds: None,
            equipment: None,
            capacity: 4,
            currency: "test:coin".into(),
            limit: 10,
            coins: 0,
            items: vec![
                item("test:token", "Token", 1),
                item("test:item/potion", "Potion", 20),
            ],
            hash: vec![],
            kits: None,
        }
    }

    #[test]
    fn a_command_is_a_plus_line() {
        assert!(is_command("+give_item A b"));
        assert!(is_command("+"));
        assert!(
            !is_command(" +give_item A b"),
            "the first byte, as KO reads it"
        );
        assert!(!is_command("hello +give_item"));
        assert!(!is_command(""));
    }

    #[test]
    fn give_arguments() {
        assert_eq!(
            parse_give(&["Aria", "potion"]),
            Some(Give {
                name: "Aria",
                item: "potion",
                count: None
            })
        );
        assert_eq!(
            parse_give(&["Aria", "potion", "5"]),
            Some(Give {
                name: "Aria",
                item: "potion",
                count: Some(5)
            })
        );
        // A count that is not a number, too few or too many words: the usage line.
        for args in [
            &["Aria", "potion", "five"][..],
            &["Aria"],
            &[],
            &["Aria", "potion", "1", "2"],
            &["Aria", "potion", "-1"],
        ] {
            assert_eq!(parse_give(args), None, "{args:?}");
        }
        // 0 parses; the range check refuses it with the item's limit.
        assert_eq!(parse_give(&["Aria", "potion", "0"]).unwrap().count, Some(0));
    }

    #[test]
    fn items_by_id_with_the_prefix_optional() {
        let p = policy();
        assert_eq!(
            item(&p, "test", "test:token", "item/potion").map(|i| i.stack),
            Some(20)
        );
        assert_eq!(
            item(&p, "test", "test:token", "test:item/potion").map(|i| i.stack),
            Some(20)
        );
        assert!(
            item(&p, "test", "test:token", "other:item/potion").is_none(),
            "another game's prefix"
        );
        assert!(
            item(&p, "test", "test:token", "potion").is_none(),
            "a label word is not an id"
        );
        assert!(
            item(&p, "test", "test:token", "token").is_none(),
            "the reward token"
        );
        assert!(
            item(&p, "test", "test:token", "test:token").is_none(),
            "the reward token"
        );
    }
}
