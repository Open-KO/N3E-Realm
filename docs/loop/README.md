# Agent loop queue

`queue.jsonl` is the backlog for the realm's agent loop: one JSON object per line,
the format n3e's parity queue used (`n3e/docs/parity/queue.jsonl`). The loop's
procedure is [`LOOP.md`](LOOP.md), its authorization AGENTS.md "Agent loop";
`tools/loop/queue.py` reads and edits the file (`check` before every commit).

| Field | Meaning |
|---|---|
| `id` | `RQ-nnn`, never reused |
| `slug` | short name for records, `[a-z0-9-]` |
| `lane` | `review`, `character`, `front-end`, `engine`, `roadmap`, `flake` |
| `kind` | `review` and `research` (findings and new items only), `verify` (check against KO, fix what differs), `fix`, `feature` |
| `status` | `ready`, `blocked` (with `blocked_on`), `done`, `deviation` (with a decision), `split` (replaced by the items after it) |
| `title` | what to do and how to know it is done |
| `refs` | files, specs and questions to start from |
| `deps` | items that must be `done` (or `deviation`, `split`) first |

Optional, kept by the loop: `attempts` (failed attempts, two at most), `note` (why the
last attempt failed, or the maintainer's answer), `question` (what a blocked item
needs decided), `stash` (the `git stash` message holding a failed attempt's work),
`testme` (what the maintainer should check by hand), `accepted` (they did).

Evidence for KO behaviour follows specs/KO-FINDINGS.md: binary (with addresses),
source (`ref/ko-src`) or local-asset, labelled. The KO screens stay as KO draws them
(Q61): no added or relabelled UI.
