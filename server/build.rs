fn main() {
    // Build identity for /v1/realm/status and the Release manifest (specs/03, 06).
    // CD passes N3E_BUILD_VERSION; a local build is "dev".
    println!("cargo:rerun-if-env-changed=N3E_BUILD_VERSION");
    println!(
        "cargo:rustc-env=N3E_BUILD_VERSION={}",
        std::env::var("N3E_BUILD_VERSION").unwrap_or_else(|_| "dev".into())
    );
    println!("cargo:rerun-if-changed=../protocol/wire.proto");
    prost_build::compile_protos(&["../protocol/wire.proto"], &["../protocol"]).unwrap();
}
