# Engine history

The engine's design, contracts and decision log, carried from n3e when it was imported
without its git history (`specs/09-migration.md`). Decisions here still bind the code
unless a spec says otherwise.

| File | What it holds |
|---|---|
| `n3e-v0.1-design.md` | The original engine design |
| `CONTRACTS.md` | Runtime contracts the code keeps |
| `DECISIONS.md` | The decision log, by `D-nnn` and the `PQ-nnn` item that made it |
| `GAPS.md` | Known gaps, open and closed |
| `ROADMAP.md` | The engine roadmap before the realm work |
| `DISCUSSIONS.md` | Longer discussions behind some decisions |

## Citations to records that were not carried

Code comments, content docs and these files cite research records by path:
`docs/implementation/evidence/*.md`, `docs/implementation/KO-*.md`, `docs/ko/*`,
`docs/implementation/STATUS.md`. Those records (per-item evidence, the KO binary catalog,
static-analysis notes on KO executables) were part of the engine's research process and
were deliberately not imported. Treat such a path as a citation, not a link: the
decision it supports is in `DECISIONS.md` under the same `PQ-nnn` or `D-nnn`, and the
code and tests in this repository are the authority for current behaviour.
