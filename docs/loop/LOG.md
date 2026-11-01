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
