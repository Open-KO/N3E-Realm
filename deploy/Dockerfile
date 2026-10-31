FROM rust:1.85.1-bookworm@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4 AS build
RUN apt-get update && apt-get install -y --no-install-recommends protobuf-compiler libssl-dev pkg-config && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY Cargo.toml Cargo.lock rust-toolchain.toml ./
COPY protocol protocol
COPY server server
# Workspace members the server image does not build, but cargo must resolve.
COPY launcher launcher
COPY bot bot
COPY deploy/*.sql deploy/
ARG N3E_BUILD_VERSION=dev
ENV N3E_BUILD_VERSION=$N3E_BUILD_VERSION
RUN cargo build --locked --release -p n3e-server
# The bot image (`--target bot`, specs/05-bot.md): rustls with bundled roots, so it needs
# no OpenSSL or CA store at run time. Stages a build skips are not built.
FROM build AS bot-build
RUN cargo build --locked --release -p realm-bot
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS bot
COPY --from=bot-build /src/target/release/realm-bot /usr/local/bin/realm-bot
USER 1000:1000
ENTRYPOINT ["realm-bot"]
# The server image: the last stage, so a plain build produces it.
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
RUN apt-get update && apt-get install -y --no-install-recommends libssl3 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/target/release/n3e-server /usr/local/bin/n3e-server
# Runtime UID matches local key owner via Compose user; no root needed.
USER 1000:1000
ENTRYPOINT ["n3e-server"]
