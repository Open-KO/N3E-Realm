# Loop log

One row per attempt and per INBOX entry handled, newest last (docs/loop/LOOP.md).
Result is `done`, `deviation`, `split`, `blocked`, `failed` or `inbox`; the commit is
found with `git log --grep RQ-NNN`.

| When (UTC) | Item | Result | Gate | Notes |
|---|---|---|---|---|
| 2026-11-01 15:14 | RQ-000 | done | queue 0 (docs-only) | Review at docs/loop/reviews/2026-11-01.md; Q67, Q68 added; RQ-036 retitled and moved up (security: mapped CIDR wrap); RQ-030, RQ-031, RQ-033 rewritten for the home host; RQ-037..RQ-062 filed. Reviewer pass, round 1; notes applied (RQ-044 after RQ-021; RQ-049 cross-refs RQ-013/RQ-017; RQ-052 states deploy.json authentication; RQ-042 tests release-mode wrap). Gate blind spots (review section 6) left for INBOX. |
| 2026-11-01 15:16 | RQ-020 | inbox | - | Maintainer (in session): the 1097 install is available; unpacked to build/ko-reference/installer-1097 by tools/ko-reference/unpack_installer.py (hash matches the pin); status ready. |
| 2026-11-01 15:32 | RQ-036 | held | make-test 2 (ko_bake_pin: RQ-020 pin) | Reviewer pass. Gate: queue, server test, edge fmt/clippy/test 0; make test 2 on the stale 1097 --features pin, which SKIPped before the install was unpacked. No attempt spent; stashed as "RQ-036 held for RQ-020", RQ-020 moved first, RQ-036 deps RQ-020. make live not reached. |
| 2026-11-01 15:52 | RQ-020 | done | queue 0, make-test 0 | 1097 --features pin dc494e1f -> 2fb34600; a pre-M4c cook (854c5f5^) still gives dc494e1f and the diff is only the M4c front end (front-end.bin, engine 42, wire 30, recipe/provenance). Reviewer pass round 1, reproduced; note: the older M4c comment in ko_bake_pin.py still reads "fails until recut". |
| 2026-11-01 16:05 | - | inbox | - | Maintainer (in session): the loop may ssh to the realm host to monitor and deploy (AGENTS.md, LOOP.md, the skill and the worker rules amended; no mint-bot, host-tls, secrets or TLS/tunnel/firewall changes); releases are published by CI only. Q67 decided (ssh from the host's network); RQ-031 ready. |
| 2026-11-01 16:05 | - | inbox | - | Maintainer: no off-box backups for now (Q68 decided); RQ-033 ready. |
| 2026-11-01 16:05 | RQ-063 | inbox | - | Maintainer: private setup details stay out of the public repo (AGENTS.md working agreement); RQ-063 audits current files (no history rewrite). The daily push is held until RQ-063 lands. |
| 2026-11-01 16:05 | RQ-064 | inbox | - | Maintainer: the loop may fix its gate's blind spots (review 2026-11-01 section 6); RQ-064 filed. |
| 2026-11-01 16:05 | RQ-065 | inbox | - | Maintainer: research a deploy path self-hosting operators can use; RQ-065 filed after RQ-031. |
| 2026-11-01 17:10 | RQ-036 | done | queue, cargo-test-server, fmt/clippy/test edge, make-test, make-live all 0 | Mapped trusted-proxy CIDRs: prefix - 96, under /96 refused at start, over-wide prefix matches nothing, in server and edge; specs 01 and 12 state the rule. Reviewer pass round 1. Re-gated after RQ-020 from stash; an earlier run failed make live at once because the shell lacked tools/env.sh (not the change; RQ-064 now covers it). |
| 2026-11-01 17:14 | RQ-018 | inbox | - | Feedback: no music or sound on the login and select screens; RQ-018 moved to the top. |
| 2026-11-01 17:14 | RQ-066 | inbox | - | Feedback: select-screen hover loops the animation, 1298 plays it once and holds; RQ-066 filed at the top. |
| 2026-11-01 17:14 | RQ-067 | inbox | - | Feedback: select-screen arrows swing the camera around the pillar; RQ-067 filed at the top. |
| 2026-11-01 17:14 | RQ-068 | inbox | - | Feedback: no way to log out of Discord; RQ-068 filed at the top (KO screens stay original, Q61). |
| 2026-11-01 17:14 | RQ-001 | inbox | - | Feedback: full character creation (every class, stat points); RQ-001..RQ-007 moved up as a block. |
| 2026-11-01 17:14 | RQ-069 | inbox | - | Maintainer (in session): play the game here while the loop runs; RQ-069 filed after the feedback fixes. |
| 2026-11-01 17:14 | RQ-064 | inbox | - | Maintainer (in session): split the gate (affected live suites per item, full make live and live-ko once a day before the push) and load tools/env.sh; folded into RQ-064, moved up. Rule recorded in LOOP.md: feedback goes to the top of the queue. |
