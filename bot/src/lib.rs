//! realm-bot library. The Discord and HTTP plumbing arrive in M6; what lives here now
//! is the **contract** with the realm's admin API (spec 03) so the bot and the server
//! can be built against the same table.
pub mod admin;
pub mod events;
