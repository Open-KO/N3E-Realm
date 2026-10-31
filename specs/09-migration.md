# 09 — Migration: `n3e` → `N3E-Realm`

The one-time move of the engine, client, tooling and tests into the product repo.
After this, `N3E-Realm` is the only repo where code changes; `n3e` freezes as the
research/reference repo (KO catalog, binary evidence, Ghidra setup, `ref/` submodules).

## Preconditions

1. The reversing items in `KO-REVERSING-PRIORITIES.md` marked P1 are done in `n3e` and
   `architecture.md` + these specs have been refined from the findings.
2. The `n3e` parity loop is **paused** by the user. No commits land on `n3e/main` during
   the migration.
3. `N3E-Realm` exists with `README.md` only (or the M0 skeleton).

## Principles

- **Clean import, no history.** Copy the working tree at a pinned commit. Record the SHA
  in `N3E-Realm/UPSTREAM.md`. History is not carried; `n3e` is private.
- **Wholesale, then prune.** Copy everything first, delete second, fix the build third.
  Do not re-create modules selectively: the server is integrated (persistence, leases,
  realm fences, admin authority cross-cut), and `n3e/docs/implementation/STATUS.md` is a
  record of exactly the integration bugs that would come back.
- **Minimal tweaks.** The import PR changes names, defaults and dead paths. It adds no
  features. Specs 01–03 come *after*, as ordinary work in the new repo.
- **Everything the suite needs comes along.** If a test is kept, its fixtures and
  tools are kept. If a tool is dropped, its tests are dropped in the same commit.

## What moves, what doesn't

| Path in `n3e` | Action | Notes |
|---|---|---|
| `client/`, `server/`, `protocol/` | **Keep** | The engine. |
| `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `CMakeLists.txt`, `Makefile`, `build.rs` | **Keep** | Trim Makefile targets per the prune list. |
| `tools/assetc/`, `tools/bootstrap.sh`, `tools/env.sh` | **Keep** | Content cooker incl. every `ko_*.py` importer — the realm ships KO content (Q12 → yes). |
| `tools/blender`, `tools/install-blender.sh`, `tools/install-mpfb.sh` | **Keep** if any kept test or cook step needs Blender; otherwise drop. Check `assetc` imports first. |
| `tools/play-*`, `tools/*_session.py`, `tools/play_*.py` | **Keep** | Developer launch scripts; cheap. |
| `tools/ghidra/`, `tools/d3d8-probe/`, `tools/ko_showcase_*`, `tools/ko-reference/rig` | **Drop** | Research tooling. |
| `tools/ko-reference/{unpack_installer,unpack_inno,pack_2145,tbl_2145,anim_2145,inspect_db}.py` | **Keep** | Found during the import: these are KO-format importers for later client releases that `assetc` and 11 CPU tests use; the tests SKIP without the player's installers. Not research. See Q27. |
| `tools/parity/` and the pre-push gate hook | **Drop** | The parity loop is re-created fresh on `N3E-Realm` (the user starts a new loop); its policy files are rewritten for the new repo rather than carried. |
| `tests/` | **Keep**, minus tests whose only purpose is parity-loop plumbing or Ghidra evidence | Both CPU (`make test`) and live (`make live`, `live-ko`) suites. |
| `games/demo`, `games/moradon` | **Keep** | `moradon` is the realm's first package (Q12). `demo` stays as the synthetic fixture the CPU suite uses. |
| `content/*.md`, `content/*.schema.json` | **Keep** | Package schema docs — the agent's contract for content. |
| `deploy/*.sql`, `deploy/Dockerfile`, `deploy/local-ca.sh`, `deploy/local/` | **Keep** | Migrations are the realm's schema. Spec 07 adds the prod compose next to the local one. |
| `compose.yaml` | **Keep** as `compose.local.yaml`? **No — keep the name**; spec 07's prod file is `deploy/compose.prod.yaml`. | n3e's tests reference `compose.yaml` and `tests/compose-disposable.yaml`. |
| `spikes/` | **Drop** | Experiments; recorded in `n3e` decisions. |
| `ref/` (submodules) | **Drop** the submodules | The raw KO client tree becomes one immutable tarball (~740 MB, sha256-pinned in `UPSTREAM.md`, stored as a Release asset of `N3E-Realm`), fetched by `tools/fetch-ko-assets.sh` into **ignored** `assets/ko/` (spec 10). `ko-blender` only if a kept tool needs it. |
| `docs/ko/` | **Drop** | Reference material; not linked from here (tweak 9). |
| `docs/parity/` | **Drop** | New loop, new files. |
| `docs/implementation/CONTRACTS.md`, `DECISIONS.md`, `GAPS.md`, `n3e-v0.1-design.md`, `ROADMAP.md` | **Keep** under `docs/history/` read-only | Decisions still bind the code. `STATUS.md` is **not** carried — a fresh one starts empty. |
| `docs/implementation/KO-*.md`, `evidence/` | **Drop** | Evidence chain belongs with the binaries, in `n3e`. |
| `AGENTS.md`, `CLAUDE.md` | **Rewrite** | Keep the working agreements (server authority, PG owns durable state, no blocking I/O on ticks, fixtures/provenance, branch rules). Remove: KO roadmap, Ghidra-before-implementing, parity loop section, `ref/` layout notes. Add: pointer to `specs/`, pointer to `n3e` as reference. |
| `README.md` | **Rewrite** | Product README. |
| `build/`, `target/`, `.cache/` | n/a | Ignored. |

## The tweaks (complete list — anything else is a feature and waits)

1. **Realm name default.** `N3E_REALM` default `local` stays for dev; `tests/` unchanged.
   Prod sets `prod` via compose (spec 07). No code change; listed so nobody "fixes" it.
2. **Default game.** `Makefile` `GAME ?= demo` → stays `demo` for the CPU suite;
   `make assets GAME=moradon` is the realm cook. Add `make realm-assets` as an alias.
3. **KO asset input.** Maintainer creates `ko-client-assets-<sha256>.tar.zst` from the
   current `assets/ko` once and uploads it as a Release asset
   (`content-store` Release, spec 06). New `tools/fetch-ko-assets.sh` downloads and
   verifies it into `assets/ko/` (ignored). Rename the hardcoded `assets/ko`
   in `tools/assetc/*.py` and `tests/live_ko.py` (≈ 9 sites) to `assets/ko`, and add the
   `ko:` source prefix in `assetc` (spec 10) with the existing bare-path form still
   accepted for one release. `make live-ko` and `make realm-assets` depend on the fetch;
   `live-ko`'s "NOT RUN when input missing" behaviour stays.
4. **Makefile prune.** Remove `tools/parity` references, the Ghidra targets if any, and
   the pre-push gate. `make test`, `make live`, `make live-ko`, `make graphical` remain
   and must pass.
5. **Build version string.** Server and client embed `N3E_BUILD_VERSION` (env at build
   time, default `dev`) so spec 03's `status.version` and spec 06's manifest agree. The
   only new code in the import.
6. **Dockerfile.** Unchanged except `ARG N3E_BUILD_VERSION`.
7. **Cargo root.** n3e's root `Cargo.toml` is a workspace; after the import add
   `launcher` and `bot` as members (they are standalone crates in the skeleton so the
   import cannot clobber them). Keep their own `Cargo.lock`s until then; one workspace
   lock afterwards.
8. **Skeleton files that survive the import untouched:** `LICENSE`, `CONTRIBUTING.md`,
   `CODEOWNERS`, `.github/`, `specs/`, `docs/architecture.md`, `launcher/`, `bot/`.
   Files the import **replaces**: `README.md`, `AGENTS.md`, `.gitignore` (merge the
   skeleton's entries in).
9. **Doc links.** Any kept doc that links into a dropped path loses the link and keeps
   its text. Nothing links to the `n3e` repository, which is private. The docs build
   (spec 08) will fail on broken relative links, so do this properly.

## Procedure

1. In `n3e`: confirm the loop is paused; note `git rev-parse HEAD` → `PIN`.
2. In `N3E-Realm`: `git rm -r` the skeleton except `README.md`/`specs/`; `rsync -a
   --exclude .git --exclude target --exclude build --exclude .cache --exclude ref
   n3e/ ./`.
3. Apply the "Drop" rows. Apply the tweaks. Write `UPSTREAM.md`:
   ```
   n3e:        <PIN>
   KO assets:  ko-client-assets-<sha256>.tar.zst  (assets/ko/, fetched, ignored)
   imgui:      v1.91.9b @ f5befd2d                 (tools/bootstrap.sh)
   ```
4. `tools/bootstrap.sh`; `make test` green; `make live` green on a GPU host;
   `make live-ko` green with the fetched assets.
5. `docker compose up` the local stack from the imported `compose.yaml`; a client logs
   in with the legacy password path (spec 02 is not in yet) and walks around Moradon.
6. Rewrite `AGENTS.md`, `README.md`. Commit as **one** commit: `Import n3e @ <PIN>
   (clean, pruned)`. Push. This is the base of every later branch.
7. In `n3e`: add a line to its `README.md`: "Engine development moved to `N3E-Realm` at
   `<PIN>`; this repo is reference and research." Nothing else changes there.

## What the import actually found (2026-10-30)

- Pin `aaefdab4182abc8f83b092dc23c29edc6f860316`. Source tree 27 MB; the 3.8 GB was
  build output.
- **The realm package is the bake, not `assetc/main.py`:** `tools/assetc/ko_bake.py
  210 --features --into=build` produces `build/packages/moradon` from `games/moradon/`
  feature JSON plus the client tree only. `make realm-assets` wraps it. Other bake
  variants (1097 homelands, classic layout) also need unpacked KO *installers* under
  `build/ko-reference/` — Q27.
- Raw KO tree: 738 MiB → 279 MiB `.tar.zst`, sha256 in `UPSTREAM.md`, created
  deterministically from `Open-KO/KnightOnline`'s `assets/Client`. 29 files referenced
  the old submodule path; one `sed`.
- `tests/live.py` imported `tools/parity/gate` for its input-coverage audit; made a
  no-op at import, then removed with the rest of the gate plumbing (`N3E_PARITY_GATE`,
  `N3E_GATE_RUN`, `harness_files()`, UNCOVERED lines) when M0 was finished. The read
  hook stays: it records kept logs and refuses non-disposable Postgres starts.
- Latent bug fixed: `ko_bake.py --client=1097` failed on `Zones.tbl` before reporting
  "no 1097 install" on a machine without the unpack (`tests/ko_bake_pin.py` expected
  the latter; n3e always had the unpack present).
- `Cargo.lock`: regenerating it pulled crates needing Rust > 1.85.1; restored n3e's
  lock and let `cargo build` add only the launcher/bot entries.
- `make test` green in 5½ min on the GPU host.
- 889 relative links into dropped n3e paths (`docs/implementation/…`, `docs/ko/…`,
  `ref/…`) unlinked to plain text per tweak 9 (2026-10-30). Path citations in code
  comments stay; `docs/history/README.md` says what they are.
- Finishing M0 (2026-10-30): the eight schema-downgrade/upgrade checks rebuilt on
  synthetic schema states instead of n3e builds (Q28); `tools/ko-reference/inspect_db.py`
  restored so the optional KO database exports can be produced here (Q27); Ghidra
  and `ref/` citations reworded to name the analysis or the public Open-KO source.
- Clean-clone acceptance at `7196c43` (2026-10-30, GPU host): bootstrap 12 s; fetch from
  the local tarball cache (the Release URL was not public yet); `make test` exit 0
  (474 s); `make live` LIVE_OK 68/68 (684 s); `make live-ko` 14 passed, 0 failed, 11
  NOT RUN, all for operator-supplied KO inputs (518 s).

## Acceptance

- `make test` and `make live` pass on a GPU host from a clean clone with only
  `tools/bootstrap.sh` and `tools/fetch-ko-assets.sh` run first; `make live-ko` there
  has 0 failed, with only the suites that need operator-supplied KO inputs (Q27)
  NOT RUN. (Originally "`make live-ko` passes", which Q27 makes impossible from a clean
  clone; corrected when M0 was finished.)
- `rg -il "tools/parity|docs/parity|N3E_PARITY_GATE|N3E_HISTORY|ghidra|ref/ko-src|ref/ko-blender|legacy-server"`
  over the repo (excluding `docs/history/` and `specs/`) returns nothing. (The first
  version also matched `Open-KO`, which is this repository's own org and the named
  source of the KO assets; corrected when M0 was finished.)
- `git submodule status` prints nothing.
- The repo size (without `target/`, `build/`, `ref/`) is below `n3e`'s 3.8 GiB —
  record the number; large fixtures that are KO-derived should come from the fetch,
  not the repo, if that is what dominates (check with `du` before committing).
- `UPSTREAM.md` exists and every pin resolves.
- A new agent, given only `N3E-Realm` and these specs, can run the local stack by
  following `README.md` without consulting `n3e`.

## Open questions

Q11, Q18, Q19.
