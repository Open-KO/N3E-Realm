//! realm-launcher — see `specs/04-launcher.md`.

use realm_launcher::{manifest, run, VERSION};

fn usage() -> ! {
    eprintln!(
        "realm-launcher [--realm NAME] [--check] [--no-update] [--no-start] \
         [--add-realm NAME URL] [--manifest URL] [--ca PATH] [--version]"
    );
    std::process::exit(run::USAGE)
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
    let options = match run::parse(&args) {
        Ok(o) => o,
        Err(e) => {
            eprintln!("realm-launcher: {e}");
            usage();
        }
    };
    std::process::exit(run::run(options));
}
