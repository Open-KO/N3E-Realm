# Agent loop queue

`queue.jsonl` is the backlog for the realm's agent loop: one JSON object per line,
the format n3e's parity queue used (`n3e/docs/parity/queue.jsonl`). The loop's own
procedure and standing authorization are not written yet; until they are, items are
worked only when the maintainer asks (AGENTS.md).

| Field | Meaning |
|---|---|
| `id` | `RQ-nnn`, never reused |
| `slug` | short name for branches and records |
| `lane` | `character`, `front-end`, `engine`, `roadmap` |
| `kind` | `research` (findings only), `verify` (check against KO, fix what differs), `fix`, `feature` |
| `status` | `ready`, `blocked` (with `blocked_on`), `done`, `deviation` (with a decision) |
| `title` | what to do and how to know it is done |
| `refs` | files, specs and questions to start from |
| `deps` | items that must be `done` first |

Evidence for KO behaviour follows specs/KO-FINDINGS.md: binary (with addresses),
source (`ref/ko-src`) or local-asset, labelled. The KO screens stay as KO draws them
(Q61): no added or relabelled UI.
