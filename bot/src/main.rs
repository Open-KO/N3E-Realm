//! realm-bot — see `specs/05-bot.md`. Skeleton: contract types only; Discord gateway,
//! slash commands and the stream consumer are M6.

fn main() {
    eprintln!(
        "realm-bot {}: not implemented yet (see specs/05-bot.md, M6). Routes known: {}",
        env!("CARGO_PKG_VERSION"),
        realm_bot::admin::ROUTES.len()
    );
    std::process::exit(10);
}
