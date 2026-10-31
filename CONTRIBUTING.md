# Contributing

Two kinds of contribution, two paths. Both go through pull requests with CI.

## Content (after the engine import)

Items, NPC looks, effects, UI textures, tables, rates, event presets, spawn names and
announcements — anything that fills an existing asset slot or table row in
`games/<game>/`. Zones and terrain from non-KO sources are not yet supported.

- Put assets under `games/<game>/assets/<name>/` (glTF 2.0 + PNG, ≤ 8 MB per file).
- Add a row to `games/<game>/PROVENANCE.md`: path, author, licence, tool, derivation.
- Never add Knight Online native files (`.n3*`, `.gtd`, `.opd`, `.tbl`, …). The raw KO
  tree is a pinned build input, fetched by `tools/fetch-ko-assets.sh`; it is not in
  git and must not be uploaded in a PR. A retextured or re-exported KO asset is still
  KO material.
- Balance changes: say why in the PR; read `games/<game>/BALANCE.md` first. Changes to
  `progression` are labelled `balance` and need the upgrade path on deploy.
- Contributed assets are licensed **CC-BY 4.0**. Sign off your commits (DCO, `git
  commit -s`).

Details: [`specs/10-content.md`](specs/10-content.md).

## Code

- Rust: `cargo fmt`, `cargo clippy -D warnings`, `cargo test`. C++: `make test` (after
  the import). CI runs the same.
- Follow the spec for the component you touch; if the spec is wrong, fix the spec in
  the same PR.
- New questions go into `specs/QUESTIONS.md` under "Raised during implementation".
- Code is MIT. Sign off your commits.

## Code owners

`CODEOWNERS` routes `games/**` to content maintainers and everything else to engine
maintainers; a PR touching both needs both.
