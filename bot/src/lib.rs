//! realm-bot (specs/05-bot.md): Discord slash commands call the realm's admin API
//! (spec 03); `realm:events` entries become Discord messages. Plain automation.
pub mod admin;
pub mod api;
pub mod commands;
pub mod config;
pub mod discord;
pub mod events;
pub mod stream;
pub mod text;
