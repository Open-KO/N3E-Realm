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
2. **Daily gate and push.** When the last push (`build/loop/pushed-at`) is over 24 h
   old, `master` is ahead of `origin/master` and no `daily-*` fix item is open: fetch;
   stop the loop if `origin/master` is not an ancestor of `master`; run the daily gate
   (below) on `master`. On `DAILY_OK` or `DAILY_FLAKE` (a `flake` item per suite),
   `git push origin master` (never forced). On `DAILY_FAIL` nothing is pushed: each
   `DAILY_BLAME` line becomes a `fix` item (slug `daily-...`) at the top of the queue,
   naming the failed step or suite and the commits it blames; the next daily run
   waits until they are done. A red CI run on the previously pushed head becomes a
   `fix` item at the top of the queue.
3. **Pick** `tools/loop/queue.py next`. `LOOP_QUEUE_EMPTY` ends the loop.
4. **Work.** The worker gets the item and, on a retry, the item's `note`.
5. **Review.** Blocking findings go back to the worker; at most two review rounds.
6. **Gate.** `tools/loop/gate.py run`. A `GATE_FAIL` goes back to the worker once with
   the failing log; the gate then runs again. `GATE_FLAKE` passes and files a `flake`
   item per suite. The `GATE_TIMES` line (each step, its exit code and seconds) goes
   into the LOG row.
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

Two gates, both `tools/loop/gate.py`, so the loop waits minutes per item and runs the
long suites once a day. Each logs every step to `build/loop/gate/<stamp>/` (daily:
`build/loop/daily/<stamp>/`) with its exit code and seconds in `timings.tsv`, and prints
them on a `GATE_TIMES` / `DAILY_TIMES` line for the LOG row. Each sources
`tools/env.sh` (the pinned toolchain and ImGui) and removes `LIVE_SUITES`,
`LIVE_KO_SUITES`, `LIVE_TICK_MS`, `LIVE_DISPLAY` and the other knobs in `CLEARED` from
the environment it passes on. A missing GPU, Docker or fixture fails a gate; it is
never a pass. A `SKIP` line in a make test log fails the step unless `SKIP_ALLOWED`
names it: only inputs the maintainer alone holds (today the 1264 install and the 2145
installer).

**Per item** (`gate.py run`; `gate.py plan [FILE...]` shows the steps). Picked from the
changed files:

- the queue check, always; nothing more when only docs change (`docs/`, `specs/`,
  `.claude/`, `README.md`, `AGENTS.md`, any `.md`). `content/` and `tools/loop/` are not
  docs.
- `cargo fmt --check`, `clippy -D warnings` and `test` for each crate whose inputs the
  change touches: its directory, `Cargo.*` and `rust-toolchain.toml`, and for
  n3e-server also `protocol/`, `deploy/*.sql`, `tests/fixtures/*.hex` and realm-bot's
  library and admin routes. n3e-server's fmt and clippy wait for RQ-021.
- `make test-fast` (`make test` without the Makefile's `SLOW_TESTS`) for any other
  change, and `make test-slow` for each slow test whose script, or a helper it
  imports, the change touches.
- the `make live` and `make live-ko` suites whose covers the change touches: a
  suite's `covers` in `tests/live.py` or `tests/live_ko.py`, with the `tests/` and
  `tools/` scripts they import or name. A change to a runner's own files (the runner,
  the modules it imports, `tests/live_reads/`) runs that runner whole, and so does a
  new `*_live.py` or `*_db.py` that no runner owns. A server, client, engine or
  content change outside every suite's covers runs no live suite per item; the daily
  gate runs them.

A failed live suite whose covers the change does not touch is rerun alone once;
passing alone is a flake (`GATE_FLAKE`, filed), not a pass of the original run.

**Daily** (`gate.py daily`, on a clean `master`, before the push): every crate's fmt,
clippy and test, the whole of `make test` (the slow tests too), and the whole of
`make live` and `make live-ko`. Every step runs even after one fails. A failed live
suite is rerun alone once; passing alone is a flake (filed; it does not block the
push). Any other failure is `DAILY_FAIL`: it blocks the push, and its `DAILY_BLAME`
line names the commits since `origin/master` that touch it (the failed suite's covers
or the failed test's script), or all of them when none does. It is fixed by a new
commit from a `fix` item, never a reset or a revert.

What is slow and catches little per item moves to the daily gate by the same rule: a
make test script into `SLOW_TESTS`, a live suite by keeping its covers to what it
exercises.

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
firewall, publishes a release by hand (except the hosted release below), force-pushes, rewrites history, reads or writes `.env` or any
secret, runs `docker compose config` unfiltered, commits `assets/ko`, or adds items
about its own machinery unless INBOX asks. Reverse engineering uses n3e's Ghidra
setup and `~/Projects/n3e/ref/` read-only.

Until CI publishes releases (RQ-030), the loop may build and copy the hosted release
by `deploy/HOST.md`'s Releases steps (the maintainer allowed it, 2026-11-01), under the same deploy conditions.
A new package starts a new realm (Q63): say so in the LOG row, and deploy the server, the
package and the release together so the hosted client always matches the package.

## LOG

[`LOG.md`](LOG.md): one row per attempt and per INBOX entry handled, newest last.
