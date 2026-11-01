---
name: realm-loop
description: One iteration of the N3E Realm agent loop - preflight, the next queue item through worker, reviewer and gate, then commit or stash. Run as `/loop /realm-loop` at the repository root; the policy is docs/loop/LOOP.md.
---

# realm-loop: one item

You are the orchestrator. Read `docs/loop/LOOP.md` once per session; it is the policy
and wins over this page. You write no product code: the `realm-worker` subagent does
the work, `realm-reviewer` reviews, `tools/loop/gate.py` gates. Do one item per
invocation, then hand back to `/loop` (a short wakeup, about 60 s) unless a stop
condition ended the loop (`ScheduleWakeup` with `stop: true`, and say why).

## 1. Preflight

```sh
git rev-parse --abbrev-ref HEAD                         # master
git status --porcelain=v1 -uall                         # empty, or only docs/loop/INBOX.md
df -BG --output=avail . | tail -1                       # >= 20G
tail -n 3 docs/loop/LOG.md                              # not three failed rows
```

Any miss, or a `HALT` line under INBOX's HALT heading: stop the loop and report it.

Handle INBOX entries (Feedback, Answers, Accepted) per LOOP.md with
`tools/loop/queue.py set`/`add`, clear them from INBOX, add a LOG row each (`inbox`),
then commit just those files: `git add docs/loop && git commit -s -m "loop: inbox"`
plus the attribution lines below.

## 2. Daily push

```sh
cat build/loop/pushed-at 2>/dev/null                    # epoch seconds of the last push
git fetch -q origin && git rev-list --count origin/master..master
```

Over 86400 s since the last push (or no file) and ahead: if
`git merge-base --is-ancestor origin/master master` fails, stop the loop and report.
Else `git push origin master` and `date +%s > build/loop/pushed-at`. Check the
previous push's CI (`gh run list --branch master --limit 3`); a failed run on a
loop-pushed head becomes a `fix` item via `queue.py add --top`.

## 3. Pick

`python3 tools/loop/queue.py next --json`. `LOOP_QUEUE_EMPTY`: stop the loop.

## 4. Work, review, gate

Spawn `realm-worker` (Agent, `subagent_type: realm-worker`) with the item's JSON, its
`note` when retrying, and nothing else of yours. It returns a report ending in a
`RESULT:` block (status, summary, verification, testme, question, new items).

- `blocked`: stash (5b) without spending an attempt, set `status=blocked`,
  `blocked_on`, `question`; next item.
- otherwise spawn `realm-reviewer` with the item JSON and the worker's report. It
  returns `VERDICT: pass` or `VERDICT: block` with numbered blocking findings.
  On `block`, send the findings to the same worker (SendMessage) and review again;
  a second `block` fails the attempt.
- Run `python3 tools/loop/gate.py run` (long: make live is about 15 min; run it in the
  background and wait for its notification). `GATE_FAIL`: send the step's log path to
  the worker once, review its fix if it changed product code, gate again; a second
  fail fails the attempt. `GATE_FLAKE <suites>`: pass; add one `flake` item per suite
  (`lane: flake, kind: fix`) at the end of the queue.

## 5a. Commit

Update the item (`queue.py set RQ-NNN status=<done|deviation|split> testme=…`), add
the worker's new items (`queue.py add --after RQ-NNN '<json>'`), append the LOG row,
then:

```sh
git add -A -- . ':!docs/loop/INBOX.md'
git commit -s -F <message file>
```

Message: `RQ-NNN: <title, under 72 chars>`, a short body (what changed, what the gate
ran with exit codes, notes), then exactly:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <this session's URL, from the attribution reminder>
```

## 5b. Fail

```sh
git stash push -u -m "RQ-NNN attempt N" -- . ':!docs/loop/INBOX.md'
```

`queue.py set RQ-NNN attempts=N note="<why, in a sentence or two>" stash="RQ-NNN attempt N"`;
at N = 2 also `status=blocked blocked_on=budget`. LOG row `failed`; commit queue and
LOG as `RQ-NNN: attempt N failed`. Never `git reset`, `checkout --`, or `clean`.

## Never

Deploy or ssh to gn100, run `tools/host-realm` or `tools/host-tls`, publish a release,
force-push, read `.env` or secrets, run `docker compose config` unfiltered, commit
`assets/ko`, or file items about the loop itself unless INBOX asks.
