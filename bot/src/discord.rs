//! Discord: the gateway (interactions only, no intents), command registration,
//! interaction replies and channel posts. Every message goes out with no allowed
//! mentions, so no text the bot relays can ping anyone.

use crate::commands::{allowed, definitions, Bot, Invocation, Opt, NO_PERMISSION};
use crate::config::Config;
use crate::events::Channel;
use crate::text::fit;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use twilight_gateway::{
    error::ReceiveMessageErrorType, CloseFrame, ConfigBuilder, Event, EventTypeFlags, Intents,
    Shard, ShardId, StreamExt as _,
};
use twilight_http::Client;
use twilight_model::application::command::{CommandOptionChoice, CommandOptionChoiceValue};
use twilight_model::application::interaction::application_command::{
    CommandData, CommandOptionValue,
};
use twilight_model::application::interaction::{Interaction, InteractionData, InteractionType};
use twilight_model::channel::message::{AllowedMentions, MessageFlags};
use twilight_model::http::interaction::{
    InteractionResponse, InteractionResponseData, InteractionResponseType,
};
use twilight_model::id::marker::{ApplicationMarker, ChannelMarker};
use twilight_model::id::Id;

pub struct Discord {
    http: Client,
    announce: Id<ChannelMarker>,
    ops: Id<ChannelMarker>,
}

fn quiet() -> AllowedMentions {
    AllowedMentions::default()
}

impl Discord {
    pub fn new(config: &Config) -> Self {
        let mut http = Client::builder()
            .token(config.discord_token.clone())
            .timeout(Duration::from_secs(4));
        if let Some(proxy) = &config.discord_api_proxy {
            http = http.proxy(proxy.clone(), true);
        }
        Self {
            http: http.build(),
            announce: Id::new(config.channel_announce),
            ops: Id::new(config.channel_ops),
        }
    }

    /// Sends `text` to a channel; false if Discord did not take it.
    pub async fn post(&self, channel: Channel, text: &str) -> bool {
        let id = match channel {
            Channel::Announce => self.announce,
            Channel::Ops => self.ops,
        };
        let mentions = quiet();
        match self
            .http
            .create_message(id)
            .content(text)
            .allowed_mentions(Some(&mentions))
            .await
        {
            Ok(_) => true,
            Err(e) => {
                eprintln!("discord: posting to the {channel:?} channel failed: {e}");
                false
            }
        }
    }

    async fn respond(
        &self,
        app: Id<ApplicationMarker>,
        i: &Interaction,
        response: InteractionResponse,
    ) -> bool {
        match self
            .http
            .interaction(app)
            .create_response(i.id, &i.token, &response)
            .await
        {
            Ok(_) => true,
            Err(e) => {
                eprintln!("discord: answering an interaction failed: {e}");
                false
            }
        }
    }

    async fn ephemeral(&self, app: Id<ApplicationMarker>, i: &Interaction, text: &str) {
        let response = InteractionResponse {
            kind: InteractionResponseType::ChannelMessageWithSource,
            data: Some(InteractionResponseData {
                content: Some(fit(text.to_string())),
                flags: Some(MessageFlags::EPHEMERAL),
                allowed_mentions: Some(quiet()),
                ..Default::default()
            }),
        };
        self.respond(app, i, response).await;
    }

    /// Replaces the deferred "thinking…" reply with the command's answer.
    async fn finish(&self, app: Id<ApplicationMarker>, token: &str, text: &str) {
        let mentions = quiet();
        let text = fit(text.to_string());
        if let Err(e) = self
            .http
            .interaction(app)
            .update_response(token)
            .content(Some(&text))
            .allowed_mentions(Some(&mentions))
            .await
        {
            eprintln!("discord: editing an interaction reply failed: {e}");
        }
    }

    async fn register(&self, app: Id<ApplicationMarker>, guild: u64) -> bool {
        match self
            .http
            .interaction(app)
            .set_guild_commands(Id::new(guild), &definitions())
            .await
        {
            Ok(_) => true,
            Err(e) => {
                eprintln!("discord: registering the guild commands failed: {e}");
                false
            }
        }
    }
}

fn invocation(data: &CommandData, i: &Interaction) -> Invocation {
    let options: HashMap<String, Opt> = data
        .options
        .iter()
        .filter_map(|o| {
            let value = match &o.value {
                CommandOptionValue::String(s) => Opt::Text(s.clone()),
                CommandOptionValue::User(u) => Opt::User(u.get()),
                CommandOptionValue::Integer(n) => Opt::Integer(*n),
                CommandOptionValue::Boolean(b) => Opt::Bool(*b),
                _ => return None,
            };
            Some((o.name.clone(), value))
        })
        .collect();
    let (user, user_name) = match i.author() {
        Some(u) => (
            u.id.get(),
            u.global_name.clone().unwrap_or_else(|| u.name.clone()),
        ),
        None => (0, "?".into()),
    };
    let user_name = i
        .member
        .as_ref()
        .and_then(|m| m.nick.clone())
        .unwrap_or(user_name);
    Invocation {
        name: data.name.clone(),
        options,
        user,
        user_name,
    }
}

async fn interaction(bot: Arc<Bot>, discord: Arc<Discord>, i: Interaction) {
    let app = i.application_id;
    let Some(InteractionData::ApplicationCommand(data)) = i.data.as_ref() else {
        return;
    };
    match i.kind {
        InteractionType::ApplicationCommandAutocomplete => {
            let typed = data.options.iter().find_map(|o| match &o.value {
                CommandOptionValue::Focused(text, _) => Some(text.as_str()),
                _ => None,
            });
            let choices = bot
                .complete(&data.name, typed.unwrap_or(""))
                .into_iter()
                .map(|(name, value)| CommandOptionChoice {
                    name,
                    name_localizations: None,
                    value: CommandOptionChoiceValue::String(value),
                })
                .collect();
            let response = InteractionResponse {
                kind: InteractionResponseType::ApplicationCommandAutocompleteResult,
                data: Some(InteractionResponseData {
                    choices: Some(choices),
                    ..Default::default()
                }),
            };
            discord.respond(app, &i, response).await;
        }
        InteractionType::ApplicationCommand => {
            let inv = invocation(data, &i);
            if i.guild_id.map(|g| g.get()) != Some(bot.config.guild) {
                return discord
                    .ephemeral(app, &i, "This bot serves its realm's Discord server only.")
                    .await;
            }
            let roles: Vec<u64> = i
                .member
                .as_ref()
                .map(|m| m.roles.iter().map(|r| r.get()).collect())
                .unwrap_or_default();
            if !allowed(&inv.name, &roles, &bot.config) {
                eprintln!("command /{} by {}: no permission", inv.name, inv.user);
                return discord.ephemeral(app, &i, NO_PERMISSION).await;
            }
            // Admin calls may take up to 5 s; Discord wants an answer within 3.
            let deferred = InteractionResponse {
                kind: InteractionResponseType::DeferredChannelMessageWithSource,
                data: Some(InteractionResponseData {
                    flags: Some(MessageFlags::EPHEMERAL),
                    ..Default::default()
                }),
            };
            if !discord.respond(app, &i, deferred).await {
                return;
            }
            let reply = bot.run(&inv).await;
            let summary: String = reply
                .text
                .lines()
                .next()
                .unwrap_or("")
                .chars()
                .take(120)
                .collect();
            eprintln!("command /{} by {}: {summary}", inv.name, inv.user);
            discord.finish(app, &i.token, &reply.text).await;
            if let Some(text) = reply.ops {
                discord.post(Channel::Ops, &text).await;
            }
        }
        _ => {}
    }
}

/// The gateway session: registers the guild commands on the first READY and serves
/// interactions until Discord ends the session for good (a rejected token, say).
pub async fn gateway(bot: Arc<Bot>, discord: Arc<Discord>) {
    let mut config = ConfigBuilder::new(bot.config.discord_token.clone(), Intents::empty());
    if let Some(proxy) = &bot.config.discord_gateway_proxy {
        config = config.proxy_url(proxy.clone());
    }
    let mut shard = Shard::with_config(ShardId::ONE, config.build());
    let mut registered = false;
    let mut errors = 0u32;
    while let Some(item) = shard
        .next_event(EventTypeFlags::READY | EventTypeFlags::INTERACTION_CREATE)
        .await
    {
        match item {
            Ok(Event::Ready(ready)) => {
                eprintln!("discord: gateway ready as {}", ready.user.name);
                if !registered {
                    registered = discord
                        .register(ready.application.id, bot.config.guild)
                        .await;
                    if registered {
                        eprintln!("discord: {} guild commands registered", definitions().len());
                    }
                }
            }
            Ok(Event::InteractionCreate(i)) => {
                tokio::spawn(interaction(bot.clone(), discord.clone(), i.0));
            }
            Ok(Event::GatewayClose(frame)) => {
                eprintln!(
                    "discord: gateway closed ({})",
                    frame.map_or("no code".into(), |f| f.code.to_string())
                );
            }
            Ok(_) => {}
            Err(e) => {
                // Bounded: a flood of undecodable frames must not flood the log.
                errors += 1;
                // The event itself is not logged: it carries the interaction's token.
                if errors <= 20 {
                    let what = match e.kind() {
                        ReceiveMessageErrorType::Deserializing { .. } => {
                            "an event could not be read"
                        }
                        ReceiveMessageErrorType::Reconnect => "reconnecting failed",
                        _ => "receiving failed",
                    };
                    match std::error::Error::source(&e) {
                        Some(cause) => eprintln!("discord: gateway: {what}: {cause}"),
                        None => eprintln!("discord: gateway: {what}"),
                    }
                }
            }
        }
    }
    shard.close(CloseFrame::NORMAL);
    eprintln!("discord: the gateway ended the session for good (is DISCORD_BOT_TOKEN right?)");
}
