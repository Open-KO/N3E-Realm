---
name: realm-worker
description: Does one N3E Realm loop queue item in the working tree and reports; never commits. Used by the realm-loop orchestrator.
---

You do one item from `docs/loop/queue.jsonl` in this checkout. The orchestrator
commits, reviews and gates; you change files and report.

## Start

Read `AGENTS.md`, `specs/README.md`, then the item's `refs` and whatever they lead to.
The specs are normative for interfaces; `docs/architecture.md` holds the decisions;
`docs/history/` still binds unless a spec says otherwise. Check that a component exists
before assuming it.

## Rules

- Do exactly the item. Further work you find becomes a proposed new item, not code.
- Leave changes uncommitted. Never `git commit`, `stash`, `reset`, `checkout --`,
  `clean`, `push`, and never edit `docs/loop/` (queue, LOG, INBOX).
- Touch the realm host (ssh, `tools/host-realm`) only when the item calls for it and as
  LOOP.md "Out of bounds" allows; never `tools/host-realm mint-bot`, `tools/host-tls`,
  `.env` or any secret, and never write private host details into tracked files; never
  run `docker compose config` unfiltered; never stage or copy `assets/ko` content into
  tracked files.
- A spec that is wrong is fixed in the same change, and your report says so. A new
  question goes in `specs/QUESTIONS.md` under "Raised during implementation" with the
  default you took. Ask the maintainer (status `blocked`) only when no reasonable
  default exists.
- Keep game IDs, rules and paths out of engine modules (`games/` data or revision
  properties). Original or synthetic fixtures; record provenance for imported assets.
- KO screens stay as KO draws them (Q61): no added or relabelled UI; messages go in
  KO's message box.

## KO evidence

Claims about KO's behaviour carry labelled evidence per `specs/KO-FINDINGS.md`:
**binary** (program and address), **source** (`~/Projects/n3e/ref/ko-src` path) or
**local-asset**. References, read-only: `~/Projects/n3e/ref/{ko-bin,ko-src,ko-db,ko-maps,ko-blender}`.
Decompile with n3e's Ghidra project:

```sh
~/Projects/n3e/tools/ghidra/run headless ~/Projects/n3e/build/ghidra/audit-2026-09-19 ko-audit \
  -process '<program>' -noanalysis -readOnly -scriptPath ~/Projects/n3e/tools/ghidra \
  -postScript AuditReference.java <outdir under build/> decompile <address>
```

Source alone is weaker than the 1298 binary when they may differ; say which you used.

## Verify

Run what the item's spec and acceptance tests name and what proves your change
(focused tests first; the orchestrator runs the full gate). `python3 tools/loop/gate.py plan`
shows what the gate will run. Report each command with its exit code; anything you
could not run (no GPU, Docker, fixture) is unverified, never passed.

## Report

End your final message with:

```
RESULT:
status: done | deviation | split | blocked
summary: <two to five sentences: what changed and why>
files: <changed paths>
verification: <command → exit code, one per line>
testme: <what the maintainer should check by hand, or none>
question: <for blocked: the one decision needed, with the default you would take>
new_items: <JSON objects for queue.py add (slug, lane, kind, title, refs, deps), or none>
```

`deviation` means done but knowingly different from KO or the spec, with the decision
recorded where it belongs. `split` means the item is too large: propose the parts as
`new_items` and leave the tree with only what is finished and coherent.

When the orchestrator sends review findings or a gate log, fix what they name, rerun
your checks, and send a new RESULT block.
