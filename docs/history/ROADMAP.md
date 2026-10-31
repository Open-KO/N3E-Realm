# Roadmap

## Current state (2026-09-30)

On 2026-09-25 the user dropped the remaining numbered phases (5 and 6) and deleted
every phase-spec file. New work starts from a user request and is recorded in
STATUS, DECISIONS, the
evidence files and the [gap register](GAPS.md).

On 2026-09-30 the user asked for a standing parity loop (D-128)
that closes the gap register against the KO binaries from an ordered
queue. The design and the reference-rig spike (D-129) are
merged; the loop starts when the user runs `/loop /parity`.

What remains authoritative after the cleanup:

- **Architecture:** [design](n3e-v0.1-design.md) and CONTRACTS.
- **Package and format contracts:** `content/*.md`.
- **KO catalog and evidence policy:** docs/ko.
- **What is missing:** [GAPS](GAPS.md).
- **Completed work:** the history table below. The evidence files are dated
  records of each checkpoint.

Under discussion: product goals and design direction ([DISCUSSIONS](DISCUSSIONS.md)).

## History

All rows below were user accepted and merged. Decision IDs refer to DECISIONS.md;
evidence lives in `docs/implementation/evidence/`. The KO-NN numbers are their own
series: KO-04 is damage, not editor Phase 4.

### Engine phases 0–4

| Phase | Delivered | Decisions | Evidence |
|---|---|---|---|
| 0 Feasibility | Spikes:<br>- SDL3/GL 3.3/ImGui rendering with a tools toggle<br>- original glTF/collision cook path<br>- C++/Rust Protobuf over verified TLS<br>- Postgres revision/fencing/dedup under fault injection | D-004–D-009 | p0-01-environment … p0-05-revisions, p0-06-synthesis |
| 1 Foundation | - Make/CMake and Rust workspace; production protocol with goldens<br>- hashed package schemas; `games/demo`; cooker with its support matrix<br>- Compose with health checks, migrations and realm lease | D-012, D-013 | p1-foundation |
| 2 Multiplayer | - accounts and character selection<br>- session generations and fenced checkpoints<br>- 20 Hz tick with 10 Hz interest baselines, prediction/reconciliation<br>- chat, Redis/Postgres outage policy, metrics | D-014 | p2-multiplayer |
| 3 Gameplay | - data-defined stats, one targeted action<br>- NPC AI and respawn without ID aliasing<br>- transactional deduplicated rewards, death/respawn<br>- crash-boundary tests | D-015, D-017 | p3-gameplay |
| 4 Tools (merge `0fa5ac6`) | - hashed N3T1 edit registry; tools editor with drafts/undo<br>- transactional revisions, audit and results with revocation ordering<br>- terminal, role CLI, revert/export/rebase, temporary spawns<br>- I1–I17 impact closure matrix | D-041, D-042 | p4-preparation, p4-tools |

### KO grounding track KO-00–13

Planned in D-022 (evidence ko-phase-plan). Each merge SHA is listed in its acceptance
evidence, and KO-ACCEPTANCE holds the integrated
closure matrix.

| ID | Delivered | Decision | Evidence |
|---|---|---|---|
| KO-00 | Reference profile: hashes, units, radius uncertainty ledger | D-023 | ko-00-reference-profile |
| KO-01 | Walk/run with shared C++/Rust static collision; calibration deviation; controls fixes | D-024 | ko-01-movement (+ calibration, controls, feel) |
| KO-02 | Package camera profile, 2–10 zoom, obstruction and picking | D-025 | ko-02-camera-controls |
| KO-03 | N3M1 continuous melee, approach, radius range | D-026 | ko-03-melee-interaction, ko-03-target-ready |
| KO-04 | Directional damage and hit/miss formulas with server RNG | D-027 | ko-04-damage |
| KO-05 | N3N1 hostile NPC acquire/retaliate/chase/return | D-028 | ko-05-npc |
| KO-06 | N3L1 requested respawn, independent NPC timers, durable death | D-029, D-030 | ko-06-life-cycle, ko-06-durable-life |
| KO-07 | Player/NPC clips, blends and markers | D-031 | ko-07-animation |
| KO-08 | Reward settlement and claim design | D-032 | ko-08-reward-contract |
| KO-09 | N3P1 contribution settlement and ten-level curve | D-033 | ko-09-progression |
| KO-10 | Durable single-item claim and expiry | D-034 | ko-10-loot |
| KO-11 | Coherent `games/demo`; demo-alt package boundary check | D-035 | ko-11-demo |
| KO-12 | Login/create/select/chat comparison; remote life and visibility resets | D-036 | ko-12-session-lifecycle |
| KO-13 | Integrated acceptance, `play-demo --ko` | D-037 | ko-13-acceptance, ko-13-merge |

### KO catalog, Moradon and feature work

| Work | Delivered | Decisions | Evidence |
|---|---|---|---|
| KO-CAT catalog survey | Evidence-backed KO feature catalog and the Phase 4 impact review | D-038–D-040 | ko-catalog |
| KX Moradon exploration and hold-Q turbo | Moradon map import, collision, LOD, player skins, server-authorized turbo. Remaining KX gates are in [GAPS](GAPS.md). | D-041, D-043–D-060 | kx-merge and the kx-* records |
| KO feature completion (Moradon checkpoints) | Among others:<br>- inventory, equipment, shops, warehouse, party and friends<br>- loot, coins, hotbar, rest, potions<br>- effects, audio and two Priest skills<br>- target marker, swing prediction | D-061–D-100 | ko-feature-completion, ko-combat-potions, ko-effects-skills, ko-loot-lifecycle, ko-existing-feature-audits |
| KO catalog refresh and parity deep dive | Binary parity survey, investigations A–I, reference database | D-101–D-105 | ko-parity-deep-dive, ko-parity-investigations |
| Moradon reference worm | N3N2 reference NPC policy from database rows | D-106 | ko-moradon-npc-data |
| Frame-rate fix | Skinning cost and frame pacing | D-107 | client-frame-pacing |
| HUD pixel scale | N3HA fit/pixel policy | D-109 | ko-hud-pixel-scale |
| HUD gaps | N3HB/N3HC/N3HD: binary panel origins, draggable/saved panels, minimap, fullscreen (investigation J) | D-111 | ko-hud-gaps |
| KO installer provenance | The player-supplied `KnightOnLineSetup_1298.exe`, a research unpacker, reference and server-patch provenance, and a related-games survey | D-118, D-119 | ko-installer-provenance, related-games-survey |
| Asset rights and next steps | Abandonware/licensing research for KO and related games; proposed next steps (DISCUSSIONS) | D-120, D-121 | DISCUSSIONS |
| Parity loop and reference rig | The `/loop /parity` setup (queue, gate, guard, skill, agents) and a network-isolated rig running the pinned servers and the archive client into Moradon | D-128, D-129 | parity-loop-design, pq-002-ref-rig |

Decision-range attributions in the last table are approximate. DECISIONS.md is
authoritative.

## Dropped goals

These phases were planned but never started. They are kept here so their intent is
not lost if the goals return.

### Phase 5: prove reuse across games

Goal: distinct games run on identical client and server artifacts. "Same binaries"
means identical normal-client, tools-client and server-image hashes across games.

- **Second game:** author `games/variant` with a different layout, visuals,
  characters/NPCs, starting items, progression and combat parameters, using only the
  published schema. KO-11's small demo-alt package (D-035) is the only precursor.
- **Engine audit:** remove game-specific assumptions from engine modules and record
  missing generic features instead of adding game-ID branches.
  - Known leftovers: test harnesses in the production client hard-code
    `demo:item/*` IDs and the Moradon warehouse password (`client/render/viewer.cpp`
    replay modes). Closed 2026-10-01 by PQ-006 (test client only, suite-supplied
    data); the server's test-fixture commands are PQ-131.
- **Authoring guide:** namespaces, required assets, validation errors, the
  rule/property vocabulary, and a content-only "author a new archetype/action"
  walkthrough. Today `content/*.md` covers this only partly.
- **Two realms:** run two Compose realms side by side, with isolated Redis keys,
  Postgres ownership, character IDs and admin targets, and configurable ports and
  project names. Clients must negotiate the selected package, and a package mismatch
  must be rejected before world entry (already true). An authorized edit in one realm
  must not affect the other.
- **Single-build proof:** build once, record the hashes, run both loops and the
  editor/admin paths, and show the hashes unchanged.
- **Out of scope:** cross-game migration, native plugins, hot-swapping games in a
  realm.

### Phase 6: validation and v0.1 release

- **Clean machines:** build and run on other Linux distributions, GPUs and display
  servers, including native Xorg and real minimize/restore transitions.
- **Failure matrix:** every row has been exercised piecemeal in earlier phases but
  never as one run on a single build:
  - Redis restart and Postgres outage;
  - kill at transaction boundaries;
  - lease takeover and stale-session writes;
  - slow and malformed peers;
  - failed migration, and an incompatible package or base;
  - edit/revocation races, and export-plus-override rebase.
- **Load:**
  - Scenario: 100 headless players and 200 NPCs for 30 minutes on 4 vCPU / 8 GiB,
    including distributed and shared-interest cases, plus a 100 ms RTT / 1% loss run.
  - Record: p50/95/99 tick time, queues, bytes per player, CPU, RSS and corrections.
  - Target: p95 tick below 40 ms at 20 Hz.
  - Client target: 1080p at 60 FPS, also with tools enabled and an editor panel open.
  - Method rules:
    - fault injection stays inside test containers and namespaces, never on the
      user's interfaces;
    - a missed target needs a documented bottleneck plus a verified fix or a recorded
      target revision;
    - optimizations keep their correctness evidence.
  - D-010's capacity figures are still provisional.
- **Runbooks:**
  - Backup/restore, verifying characters, inventory, roles, command results and
    world/config revisions. Only reward and progression restores have been verified.
  - Migration-failure recovery, graceful shutdown, content deployment/override rebase,
    and observability (`/live`, `/ready` and metrics exist).
- **Release:** trace every design acceptance criterion to evidence, and publish a
  v0.1 release summary: build IDs, tested environments, supported asset subset,
  limits and open issues.
