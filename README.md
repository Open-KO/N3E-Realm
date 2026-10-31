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
`tools/play-*` scripts cover the demo and feature scenes. The login path is still
account/password (`n3e-server account-create`) until spec 02 lands.

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

## Status

The engine arrived by a one-time, history-free import of the n3e engine at the commit
pinned in `UPSTREAM.md` (spec 09); this repository is now its only home. The realm-specific work follows the roadmap: the admin API
(M1) is in; connection hardening, Discord login, launcher, bot, CD and deploy follow.

## Licence

Code: [MIT](LICENSE). Contributed content: CC-BY 4.0 (see `CONTRIBUTING.md`). Raw KO
client assets are a pinned input and are not part of this repository.
