//! realm-launcher — see `specs/04-launcher.md`.
//!
//! Skeleton: argument surface and manifest types only. Fetch/verify/install, realm
//! profiles, self-update and the client hand-off are M4.

use realm_launcher::manifest;

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn usage() -> ! {
    eprintln!(
        "realm-launcher [--realm NAME] [--check] [--no-update] [--no-start] \
         [--add-realm NAME URL] [--manifest URL] [--ca PATH] [--version]"
    );
    std::process::exit(2)
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--version") {
        println!("realm-launcher {VERSION} ({})", manifest::platform());
        return;
    }
    if args.iter().any(|a| a == "-h" || a == "--help") {
        usage();
    }
    eprintln!("realm-launcher {VERSION}: not implemented yet (see specs/04-launcher.md, M4)");
    std::process::exit(10);
}
