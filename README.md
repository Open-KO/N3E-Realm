# N3E Realm

A community Knight Online-style realm on the n3e engine: authoritative Rust server,
native OpenGL client (Linux now, Windows in v1), Discord login, Discord-driven
operations, and a tiny launcher that keeps players current.

| Read this | For |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | The decisions: runtime, delivery, auth, deploy gating, DDoS, content, trade-offs |
| [`specs/README.md`](specs/README.md) | How it is built — one spec per component, with acceptance tests |
| [`specs/00-roadmap.md`](specs/00-roadmap.md) | Build order and milestones |
| [`specs/QUESTIONS.md`](specs/QUESTIONS.md) | Open questions and their defaults |
| [`UPSTREAM.md`](UPSTREAM.md) | Every pinned external input |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Content and code contributions |
| [`docs/history/`](docs/history/) | The engine's design, contracts and decision log, carried from n3e |

## Layout

```
client/      native C++20 / SDL3 / OpenGL client (player build + test build)
server/      Rust authoritative server (n3e-server)
protocol/    wire.proto and goldens — the game wire
tools/       assetc (cooker + KO importers), bootstrap, play scripts, fetch-ko-assets.sh
games/       package sources: moradon (the realm), demo (synthetic fixture)
content/     package format documentation and schemas
tests/       CPU suite (make test) and live suites (make live, make live-ko)
deploy/      SQL migrations, Dockerfile, local TLS helper; prod compose arrives with spec 07
launcher/    realm-launcher (Rust)
bot/         realm-bot (Rust)
specs/       implementation specs
```

## Linux setup

Install a C++20 compiler, GNU Make, pkg-config, SDL3 (≥ 3.2), OpenGL
and OpenSSL development headers, the Protobuf compiler and C++ library, Python ≥ 3.11
with venv, Git, curl, zstd, Docker Engine and Compose v2.

```bash
bash tools/bootstrap.sh        # local CMake, Rust 1.85.1, Black, ImGui into .cache/tools
source tools/env.sh            # in every new shell
make                           # player client
make server
make test                      # CPU suite, ~6 min
```

Bootstrap touches nothing outside `.cache/tools`. Cargo builds use `--locked`.

### Windows client

The client and launcher build on Windows with Visual Studio 2022, CMake and
[vcpkg](https://github.com/microsoft/vcpkg) at the commit `vcpkg.json` pins
(`builtin-baseline`); the libraries link statically, so `n3e-client.exe` needs nothing
installed. From Git Bash, as CI's `client` job does:

```bash
cmake -S . -B build/client -A x64 -DCMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" \
  -DVCPKG_TARGET_TRIPLET=x64-windows-static
cmake --build build/client --config Release --target n3e-client n3e-test-client
cargo build --release --locked -p realm-launcher
build/client/Release/n3e-client.exe build/packages/moradon --self-test --realm realm.json
```

`--self-test` checks an install without a server: the package, `realm.json`, the
Discord login address, the system certificates and an OpenGL 3.3 window. Settings and
the session token are under `%APPDATA%`, hotbars and panels under `%LOCALAPPDATA%\n3e`.
Only the client runs on Windows; the server, tests and tools are Linux.

### The realm package

```bash
make realm-assets              # fetches the pinned KO client tree (~280 MB, once), bakes Moradon
```

The raw Knight Online client assets are a **pinned build input**, not repository
content: `tools/fetch-ko-assets.sh` downloads one immutable tarball whose sha256 is in
`UPSTREAM.md` into git-ignored `assets/ko/`. Nothing from it is committed or published
uncooked. `N3E_KO_TARBALL=/path/to/the/file` uses a local copy instead of downloading.

### Live suites (GPU + Docker)

```bash
make live                      # every disposable live/database suite
make live-ko                   # the KO-content suites (need assets/ko)
```

### Local KO live suites

With only `assets/ko`, `make live-ko` runs 14 of its 25 suites and ends
`LIVE_KO_INCOMPLETE` (exit 2): the other 11 cook zones and visuals the realm does not
ship, from inputs only an operator can supply (`specs/QUESTIONS.md` Q27). Each
`NOT RUN` line names the files it needs, all under ignored `build/`:

- **KO installers** (1097 zones, 2145/2233 item visuals): your own installer
  executables under `ref/ko-bin/installer/`, unpacked with
  `tools/ko-reference/unpack_installer.py` (1097) or `unpack_inno.py` (2145) into
  `build/ko-reference/installer-<version>/` (`tools/ko-reference/README.md`).
- **KO server database exports** (`START_POSITION`, `MAGIC_TYPE2`, `K_MONSTER`, …):
  `python3 -I tools/ko-reference/inspect_db.py <your .bak> --output
  build/ko-completion/database-parity --table START_POSITION --table MAGIC_TYPE2`
  restores your own SQL Server backup into a disposable offline container and writes
  the tables as JSON.

`LIVE_KO_OK` needs all of them; without them, 0 failed is the result to check.

### Play locally

`./tools/play-moradon` opens clients against a fresh disposable stack. Other
`tools/play-*` scripts cover the demo and feature scenes. They log in with
account/password fixtures (`n3e-server account-create`), which the local stack keeps
with `N3E_LEGACY_LOGIN=1`; production accepts Discord logins only.

### Discord login

Players log in with Discord (spec 02); the server mints a 30-day session token the
client keeps in `$XDG_CONFIG_HOME/n3e-realm/<realm id>/session.json`. To try it with
your own Discord application:

1. At <https://discord.com/developers/applications> create an application. Under
   OAuth2, add the redirects `http://127.0.0.1:49152/callback` through
   `http://127.0.0.1:49155/callback`, and copy the client ID and secret.
2. Start the server with `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` set (for the
   local Compose stack, in `.env`).
3. Give the client a realm config instead of `--connect`:

   ```sh
   echo '{"id": "local", "name": "Local", "host": "localhost", "port": 7777,
          "discord_client_id": "<client id>"}' > /tmp/realm.json
   build/client/n3e-client build/packages/moradon --realm /tmp/realm.json --ca deploy/local/ca.pem
   ```

   The Moradon package (`make realm-assets`) opens on KO's login screen (spec 11);
   **Login** or ENTER opens the browser for Discord; after Discord, the game logs in and later starts skip
   the browser until the token expires or an operator revokes it.
4. Operators act through the admin API: `n3e-server admin mint --name mod --perm
   'account.*'`, then `POST /v1/accounts/{id}/kick|ban|unban|mute|unmute` (spec 03).

### Discord bot

`realm-bot` (spec 05) gives moderators slash commands (`/status`, `/whois`, `/kick`,
`/ban`, `/mute`, `/notice`, `/deploy`, …) that call the admin API, and posts realm
events (restarts, notices, moderation, pending deploys) to two channels. To run it
against your own Discord server:

1. In the Developer Portal, open (or create) an application. Under **Installation** set
   the install link to **None**; under **Bot** reset and copy the token, leave the
   privileged intents off and turn **Public Bot** off.
2. Invite it with scopes `bot` and `applications.commands` and permissions View
   Channels, Send Messages and Embed Links:
   `https://discord.com/oauth2/authorize?client_id=<application id>&scope=bot+applications.commands&permissions=19456`.
3. With Developer Mode on (User Settings → Advanced), copy the ids of the server, an
   announcements channel, an ops channel, a moderator role and an ops role into `.env`:
   `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_CHANNEL_ANNOUNCE`,
   `DISCORD_CHANNEL_OPS`, `DISCORD_ROLE_MOD`, `DISCORD_ROLE_OPS`.
4. Mint the bot's admin token and add it to `.env` as `REALM_ADMIN_TOKEN`, then start
   the bot (Compose profile `bot`):

   ```sh
   docker compose exec server n3e-server admin mint --name bot --perm world.catalog \
     --perm world.spawn --perm world.kill --perm world.event --perm 'account.*' \
     --perm realm.status --perm realm.notice
   docker compose --profile bot up -d bot
   ```

   Natively, `cargo run -p realm-bot` with the same variables plus `REALM_ADMIN_URL`
   (`http://127.0.0.1:7780`) and `REALM_REDIS` (`127.0.0.1:6379`).

`/deploy` also needs `GITHUB_REPO` and `GITHUB_DISPATCH_TOKEN` (a fine-grained token with
Actions write on this repository only); without them it says deploy is not configured.

### Manual test round

[docs/manual-testing.md](docs/manual-testing.md) is the maintainer's periodic check of
what the suites cannot do: a real Discord login, the bot in a real server, and the
Windows client on a real GPU, playing the local realm over the LAN (`tools/local-realm`,
`tools/local_release.py`, `tools/windows_kit.py`).

### Launcher

`realm-launcher` (spec 04) is the one binary a player downloads. It reads the realm's
`manifest.json` from GitHub Releases, installs the client and the content package
under `~/.local/share/n3e-realm/`, updates itself, and starts the client. A realm other
than the default:

```
cargo build --release -p realm-launcher
target/release/realm-launcher --add-realm my-fork https://example.org/realm/manifest.json
target/release/realm-launcher --realm my-fork
```

`--check` lists what would change; `--no-update` starts what is installed. CD publishes
the releases it reads (M5); until then `tests/launcher_live.py` serves its own.

### Admin API

A running server also listens on `N3E_ADMIN_LISTEN` (default `127.0.0.1:7780`; loopback or
RFC 1918 only) for the Bot and CD (spec 03). Tokens are minted against the realm's
database and printed once:

```sh
n3e-server admin mint --name ops --perm 'realm.*'    # prints the token; keep it
n3e-server admin list                                 # names and permissions, never secrets
n3e-server admin revoke --name ops                    # bites within 10 s
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:7780/v1/realm/status
```

### Connection limits

The public listener refuses, before any TLS work, sockets past `N3E_MAX_CONNECTIONS`
(64), a source's `N3E_IP_MAX_CONCURRENT` (3) or `N3E_IP_CONNECT_RATE` (10 a minute), or
the `N3E_PREAUTH_MAX_SLOTS` (16) between accept and login, and closes a socket that has
not sent its first frame in `N3E_PREAUTH_IDLE_MS` (2000) (spec 01). The local Compose
stack, `tools/demo_session.py` and the live suites widen the per-source limits, since
every local client shares one address. Counters are under `connections` in
`/v1/realm/status`.

## Status

The engine arrived by a one-time, history-free import of the n3e engine at the commit
pinned in `UPSTREAM.md` (spec 09); this repository is now its only home. The realm-specific work follows the roadmap: the admin API
(M1), connection hardening (M2), Discord login with sessions (M3) and the Discord bot
(M6, minus the world commands that wait for M5b's catalog) and the launcher (M4,
Linux; Windows is M4b) are in; CD and deploy follow.

## Licence

Code: [MIT](LICENSE). Contributed content: CC-BY 4.0 (see `CONTRIBUTING.md`). Raw KO
client assets are a pinned input and are not part of this repository.
