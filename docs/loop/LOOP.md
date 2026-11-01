# The realm loop

An agent session works `queue.jsonl` one item at a time in this checkout, commits each
gated item to `master`, and pushes once a day. Started by the maintainer with
`/loop /realm-loop` in a Claude session at the repository root; the procedure is
[`.claude/skills/realm-loop/SKILL.md`](../../.claude/skills/realm-loop/SKILL.md). This
page is the policy it follows; AGENTS.md "Agent loop" is the standing authorization.

## Roles

- **Orchestrator** (the `/loop` session): preflight, picks the item, runs the worker,
  reviewer and gate, commits, keeps the queue and LOG. It writes no product code.
- **Worker** (`realm-worker`): does one item in the working tree and reports. Never
  commits, stashes, pushes or edits the queue.
- **Reviewer** (`realm-reviewer`): reads the item and the uncommitted change and
  returns findings. Changes nothing.

## One item

1. **Preflight.** Stop the loop on any of: `HALT` in INBOX; a dirty tree other than
   `docs/loop/INBOX.md` (someone is working here); under 20 GB free; not on `master`;
   the last three LOG rows are failures. Then apply INBOX (below).
2. **Push, at most daily.** When the last push (`build/loop/pushed-at`) is over 24 h
   old and `master` is ahead of `origin/master`: fetch; stop the loop if
   `origin/master` is not an ancestor of `master`; else `git push origin master`
   (never forced). A red CI run on the previously pushed head becomes a `fix` item at
   the top of the queue.
3. **Pick** `tools/loop/queue.py next`. `LOOP_QUEUE_EMPTY` ends the loop.
4. **Work.** The worker gets the item and, on a retry, the item's `note`.
5. **Review.** Blocking findings go back to the worker; at most two review rounds.
6. **Gate.** `tools/loop/gate.py run`. A `GATE_FAIL` goes back to the worker once with
   the failing log; the gate then runs again. `GATE_FLAKE` passes and files a `flake`
   item per suite.
7. **Commit** the change and the queue/LOG update together: `RQ-NNN: <short title>`,
   signed off, with the session's attribution lines. INBOX is never staged with an
   item.
8. **Or fail the attempt:** `git stash push -u -m "RQ-NNN attempt N"` (never a reset);
   `attempts`+1, the reason in `note`, the stash message in `stash`; after the second
   failed attempt the item is `blocked` with `blocked_on: "budget"`. Commit the queue
   and LOG update (`RQ-NNN: attempt N failed`).

A worker that cannot proceed without the maintainer returns `blocked` with a
`question`; the orchestrator stashes any change as in 8 without spending an attempt
and goes on to the next item. `split` replaces an item with smaller ones inserted
after it.

## Gate

`gate.py` picks the steps from the changed files: the queue check always; nothing more
for docs-only changes; `cargo fmt`, `clippy -D warnings` and `test` for each touched
crate (n3e-server's fmt and clippy wait for RQ-021); `make test` for anything else;
`make live` (graphical) when the change touches the server, client, protocol, deploy,
build files, Rust crates, assetc, games or live suites; `make live-ko` (last line
`LIVE_KO_OK`) when it touches Moradon, KO importers or the front end. A failed live
suite whose script the change does not touch is rerun alone once; passing alone is a
flake, not a pass of the original run, and is filed. A missing GPU, Docker or fixture
fails the gate; it is never a pass.

## Review

Only these block: a correctness bug; a broken contract (a spec interface changed
without the spec, or a spec not updated with the change); security (secrets, trust
boundaries, unbounded input); KO claims without labelled evidence (binary with
addresses, source, local-asset; specs/KO-FINDINGS.md) or a KO screen given UI KO does
not draw (Q61); a broken working agreement in AGENTS.md (raw KO assets committed,
blocking I/O on a tick, game rules in engine modules). Everything else is a note in
the LOG row, not a round.

## INBOX

[`INBOX.md`](INBOX.md) is the maintainer's channel, read at every preflight and
committed by the loop after handling (`loop: inbox`):

- **HALT**: a line `HALT` stops the loop before the next item; the maintainer deletes it.
- **Feedback**: guidance for the loop or an item, or playtest notes; the loop applies it
  (a queue edit, a new item) and moves the entry to LOG. Feedback goes to the top of the
  queue, in the order written, and is worked next; only the item in progress finishes
  first. Feedback given in the session is handled the same way.
- **Answers**: `RQ-NNN: <answer>` unblocks a blocked item: the answer goes into its
  `note` (and specs/QUESTIONS.md when it decides a question), status `ready`.
- **Accepted**: `RQ-NNN` marks a `testme` item checked by hand (`accepted: true`).

`tools/loop/queue.py questions` lists what waits on the maintainer and `testme` what
waits for a hand check.

## Out of bounds

The loop may ssh to the realm host to read logs and status, and deploy and restart the
realm with `tools/host-realm`: only with no player online or after the drain notice,
after a backup, and it stops the loop if the realm does not come back healthy. It never
runs `tools/host-realm mint-bot` or `tools/host-tls`, changes the host's TLS, tunnel or
firewall, publishes a release by hand, force-pushes, rewrites history, reads or writes `.env` or any
secret, runs `docker compose config` unfiltered, commits `assets/ko`, or adds items
about its own machinery unless INBOX asks. Reverse engineering uses n3e's Ghidra
setup and `~/Projects/n3e/ref/` read-only.

## LOG

[`LOG.md`](LOG.md): one row per attempt and per INBOX entry handled, newest last.
