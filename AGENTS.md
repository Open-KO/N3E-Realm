# N3E Realm — agent instructions

## Start here

Read `specs/README.md`, then `specs/00-roadmap.md` and `specs/QUESTIONS.md`.
`docs/architecture.md` holds the decisions; the specs are normative for interfaces
(HTTP paths, JSON, Redis keys, env vars, CLI verbs, SQL) and leave structure to you.
`docs/history/` is the engine's design, contracts and decision log carried from n3e —
decisions there still bind the code unless a spec says otherwise.

The repository carries the context. Do not assume a planned component exists; check.

## Scope and layout

Engine (`client/`, `server/`, `protocol/`, `tools/assetc`, `tests/`), realm components
(`launcher/`, `bot/`), content (`games/`, `content/`), ops (`deploy/`, `.github/`).
The raw KO client tree is a pinned input in git-ignored `assets/ko/`
(`tools/fetch-ko-assets.sh`); never commit or publish it uncooked
("cooked" as `specs/10-content.md` defines it).

## Working agreements

- Implement the requested task with its verification and documentation; do not start
  further work automatically.
- Postgres owns acknowledged durable state. Redis is never the only copy of a reward,
  revision, role, token or command result.
- Server authority: a tools build grants UI access, never privileges; the admin API's
  token permissions, not Discord roles, are the security boundary.
- Keep blocking I/O off simulation ticks. Bound every network frame, queue and retry.
- Keep game-specific IDs, rules and paths out of engine modules; express game
  differences as package data (`games/`) or revision properties.
- Original or synthetic fixtures by default; record provenance for imported assets.
- The repository is public: keep the maintainer's private setup (private-network
  hostnames and addresses, local paths, account names) out of tracked files and commit
  messages. Say "the realm host"; tools read host specifics from the environment or a
  git-ignored local file.
- Interfaces in specs are contracts. If the spec is wrong, fix the spec in the same
  change and say so.
- New questions go in `specs/QUESTIONS.md` under "Raised during implementation", with
  the default you took.

## Branches and commits

Branch per task from `master`; sign off commits (DCO); commit only task-owned files;
never force-push. Run `cargo fmt`, `cargo clippy -D warnings`, `cargo test` for Rust,
`make test` for anything touching the engine, `make live` on a GPU host for anything
touching the server's runtime behaviour. Report what ran, with exit codes; a missing
GPU, Docker or fixture is an unverified gate, not a pass.

## Agent loop

Standing authorization for the loop (`/loop /realm-loop`, `docs/loop/LOOP.md`): it may
pick items from `docs/loop/queue.jsonl`, commit each gated item straight to `master`
(no task branch), and push `master` at most once a day, never forced. Per item it runs
only the checks and live suites the change covers (`tools/loop/gate.py run`); the full
`make test`, `make live` and `make live-ko` run on master once a day before the push
(`gate.py daily`), and a failure there holds the push. It may ssh to the
realm host to read logs and status, and deploy and restart the realm there with
`tools/host-realm`: only with no player online or after the drain notice, after a
backup, and it stops the loop if the realm does not come back healthy. It may not run
`tools/host-realm mint-bot` or `tools/host-tls`, change the host's TLS, tunnel or
firewall, publish a release by hand (except the hosted release below), rewrite history, read or write secrets (the host's
`.env` included), or work on its own machinery unless `docs/loop/INBOX.md` asks. While it runs, nobody
else edits this checkout; `docs/loop/INBOX.md` is the maintainer's channel to it.
Until CI publishes releases (RQ-030), the loop may build and copy the hosted release
by `deploy/HOST.md`'s Releases steps (the maintainer allowed it, 2026-11-01), under the same deploy conditions.

## Verification evidence

Planned commands in specs are plans until run. Mark work complete only when its
acceptance tests (listed in each spec) have been executed; keep partial work explicit.
