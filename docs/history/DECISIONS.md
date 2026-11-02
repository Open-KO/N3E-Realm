# Decision register

User requirements are constraints; candidate technologies remain proposals until tested. “Accepted direction” does not mean implemented or verified.

| ID | Decision | State | Evidence / revisit point |
|---|---|---|---|
| D-001 | Linux/OpenGL client via make; Rust server via Compose; Postgres + Redis | Required | User brief |
| D-002 | Reusable engine with data-driven games; small playable v0.1 | Accepted direction | Design discussion; prove in Phase 5 |
| D-003 | Optional tools build; character permissions control server mutation | Required | User brief; enforce in Phases 2/4 |
| D-004 | C++20 + SDL3 + GL 3.3 core + Dear ImGui | Retained after spike | P0-02; broader platform coverage P6-01 |
| D-005 | Original fixtures, KO converter outside runtime, glTF interchange subset | Adapted after spike | P0-03; KO conversion/reuse still unverified |
| D-006 | TLS/TCP + generated Protobuf; bounded framing | Retained after spike | P0-04 |
| D-007 | One Rust realm process, tick-owned simulation, Postgres authority | Mechanism retained | P0-05; production integration P1/P2 |
| D-008 | Redis only for disposable/recoverable state | Accepted direction | Design; outage checks in Phases 2/6 |
| D-009 | Revision commit before tick activation; durable request deduplication | Retained after spike | P0-05 |
| D-010 | 20 Hz simulation / 10 Hz snapshots; 100-player initial load target | Provisional target | Phases 2/6 measurements |
| D-011 | Decoration/spawns/config live; collision/binary releases require restart | Accepted scope default | Phase 4; revise if user changes scope |

## Recording a decision

Append a section with ID, date, status, question, considered alternatives, selected option, evidence paths, consequences, and affected tasks/contracts. Mark replaced decisions superseded rather than deleting their history. A failed spike should produce a useful decision, not a fabricated pass.

Technical decisions within the requested scope can be made from evidence. Material product changes (for example dropping Linux, changing server language, or eliminating persistence) require user direction. Missing measurement is a reason to keep a default provisional, not a reason to repeatedly ask the user to choose implementation details.

## D-004 — 2026-09-18: retain native rendering/tools stack

Question: can the candidate render and edit on real Linux hardware? C++20/SDL3/GL 3.3 core/Dear ImGui passed both variants, shader/texture/animation, analytic pixels and editor input/focus on the reference NVIDIA GPU, Wayland and XWayland. No alternative renderer/client language was needed or tested. Exact library/tool versions are in P0-01; results in P0-02.

Retain the stack; dispose of experimental viewer/Make structure. SDL accepts minimize/restore on this compositor without observable transitions. P0 records healthy behavior under those requests; P6-01 must test actual transitions on a supporting compositor, other GPUs and native Xorg. This adapts platform coverage without claiming missing observations. P1-01/P1-05 implement production CMake/modules; no performance conclusion follows from 51-frame smoke runs.

## D-005 — 2026-09-18: adapt asset subset to measured evidence

Original glTF fixtures passed repeated deterministic cooking, five analytic animated poses, slanted normals/nonuniform scale, attachments, winding/UVs, malformed files, real rendering and C++/Rust plane contacts. P0-03 fixes C-02 conventions. Tested limits: 1MiB source/dependency files, 4,096 accessor elements; two-bone rigid weighting/Z rotation and 2x2 PNG only. These bound an experiment, not the production feature set.

Retain glTF as interchange and the independent legacy-adapter boundary. Retain original fixtures/tests; replace baked-pose runtime format and plane-only collision when implementing P1-04/P1-05. Richer glTF and actual KO conversions were not tested; direct reference reuse/license and legacy units remain unresolved. Compared alternatives: mandatory proprietary fixtures or direct reference-code reuse versus original data; original data answered the current questions without either dependency. P1-04 must publish a real support matrix and explicitly handle metadata the addon drops.

## D-006 — 2026-09-18: retain verified TLS and generated Protobuf

P0-04 establishes cross-language exchange and hostile-peer bounds; no QUIC/alternate schema experiment was needed. C-03 framing is u32 network order plus 1..65,536-byte payload. Golden optional/default/Unicode/max-ID cases and strict certificate/hostname verification pass. Keep two-second inactivity and bounded per-frame/session work as starting points, subject to production measurements.

The spike's serial admission, 10,000-message cap and eight-second whole-connection watchdog are disposable test controls, not production session semantics. P1-02 must implement bounded async admission/per-frame deadlines/rates and retain negative/golden tests. No schema-generated field or tools flag is authorization.

## D-007 / D-009 — 2026-09-18: retain durable commit/apply and fencing

P0-05 proves real process/DB recovery, deduplication, revocation ordering, generations, conservative admission expiry and failed-migration readiness. The alternative of Redis-only results or in-memory deduplication is excluded by the durability requirement, not offered as an untested substitute.

Use role-row then realm-row locking; compare/recheck inside the mutation transaction; commit mutation/result/audit atomically; activate via bounded worker-result queues on a later tick. Matching actor/payload retries read existing results even after permission revocation and never regress active state. Lease expiry uses Postgres wall clock, with a conservative local monotonic deadline measured from renewal attempt start. Test lease/renewal/admission values are 3s/400ms/2s; production values must be retested. Database and output I/O stay off the tick.

The tested DB client is postgres 0.19.10 in a worker, not SQLx. Keep SQLx provisional until production integration evidence or explicitly choose the proven worker API in P1-06. Retain transaction invariants, SQL constraints and fault cases, dispose of fixed-actor/one-realm CLI harness. C-04 and P1-06 carry the semantics; authenticated actor/session boundaries remain P2/P4.

## D-012 — 2026-09-18: bounded foundation content and explicit KO scope

Status: selected and verified for Phase 1. Question: which asset support can be
published with original/provenance-approved fixtures? Alternatives were promoting
P0's baked poses, depending on official KO assets, or implementing portable tracks
and an explicitly bounded legacy adapter. Selected runtime TRS tracks, four-weight
skinning, arbitrary-axis quaternion interpolation, bounded RGB PNG decoding and
shared heightfield/static triangles. Machine-readable schemas and binary layouts
are in content; P1 evidence
retains analytic original fixture coverage and adds richer animation/texture tests.

Release identity is SHA-256 over a deterministic little-endian release index;
that index includes hashes of canonical source recipe and cooked dependencies.
Only the Python cooker serializes canonical JSON, avoiding independent serializer
mismatch. Runtimes validate the same bytes/hashes. Limits and exact compatibility
are published, including the one-scene/mesh/skin/clip subset. These are explicit
foundation support boundaries, not claims of full glTF support.

Real local KO asset provenance/redistribution approval and character unit/metadata
calibration remain absent. Select an independently implemented **synthetic-only**
static `.n3pmesh` no-collapse/no-LOD-control adapter with explicit meter conversion,
reflection/winding and source hashes. Reject `.n3shape`, character/joint/part/plug/
animation and NTF/DXT variants rather than discard unverified metadata. The
[support matrix](../../tools/assetc/SUPPORT.md) separates this from real coverage.
This is the explicit P1-04 scope decision permitted by its acceptance gate; no real
KO conversion is marked passed. Supporting a real variant later requires approved
fixtures and separate coordinate/metadata evidence. No reference revision changed.
Affected: C-01/02, P1-03/04/05; expands P0's feature ceiling without making the
original demo depend on proprietary data. General KO compatibility remains future
adapter work; no gameplay/product requirement is removed.

## D-013 — 2026-09-18: production async admission and dedicated PG worker

Status: selected and verified for Phase 1. Retain OpenSSL/prost with Tokio and a
pinned Tokio/OpenSSL adapter. Replace P0's serial/eight-second session model with
64 admitted async sockets, absolute two-second handshake/read/write deadlines,
100 frames and 1 MiB actual inbound payload bytes per fixed one-second window,
and no application request queue. Unknown fields count toward byte limits.
Diagnostic echoes have bounded outputs; snapshots will use a latest-value slot
before gameplay admission. This is a foundation bound, not a performance claim.
See wire policy and evidence.

Choose the proven postgres 0.19.10 client on a dedicated OS worker over untested
SQLx. Keep 3s DB leases, 400ms renewals and a 2s monotonic admission deadline measured
from attempt start. Lock the realm row before evaluating database-clock expiry;
owner+generation fence renewals/releases and future transaction writes. The worker
uses no simulation-tick I/O and cannot keep process shutdown indefinitely blocked
by a frozen DB. PG failure stops admission and exits for explicit restart; Redis
failure closes readiness but lease-owned shell ticks continue. Transactions/checksums
and Compose dependency conditions prevent failed migrations from creating readiness.

Tests cover the actual library's expiry/takeover/stale-owner rejection, actual
fresh SQL failure/rollback, persistent restart, duplicate process, dependency loss,
separate health endpoints and verified cross-language TLS. Role ordering,
authenticated sessions, durable mutation/result/audit transactions and tick activation
remain C-04 obligations for the phases implementing those operations; the foundation
does not invent actors or provision a default administrator. Affected C-03/04,
P1-02/06; SQLx is no longer the selected Phase 1 production API.

## D-014 — 2026-09-18: bounded authenticated multiplayer defaults

Status: selected for Phase 2; verification and remaining user testing in
P2 evidence. Implements P2-01–06, C-03/C-04.

Select 20Hz fixed simulation, 10Hz full interest baselines, one-metre grid cells
with a one-cell subscription radius, 100ms remote interpolation, and 3m/s horizontal
walking. The four-metre original scene could not exercise interest departure with
2m cells; 1m cells demonstrate disappearance/reentry without changing the package.
Movement sequences strictly increase below signed 64-bit MAX, never wrap, and reset
only on a new session. No peer-provided clock or absolute position grants motion.
At most one queued movement is accepted per character per tick (amended by
D-207, 2026-10-24: one more is held for the next tick and a third refused; still
one applied per tick); diagonal direction normalizes. The original flag is instanced as each character's visible fixture.

Choose atomic full baselines over lifecycle deltas: the 64-peer admission bound
keeps the worst view below the existing frame limit, and coalescing cannot drop a
required spawn/despawn. Every missing entity is removed before presentation; runtime
IDs are allocated by a noncycling Postgres sequence across reconnects/restarts.
This trades some bandwidth for a simpler provable baseline/lifecycle contract.
No bandwidth or 100-player performance claim follows. D-010's rates are selected;
its capacity target remains unmeasured.

Reject a duplicate active character session rather than replacing it. Login binds
account identity; selection derives ownership from Postgres, increments generation,
and returns a fresh baseline. Position writes fence both realm and session and use
acknowledged movement sequence to prevent delayed same-session regression. Capture
checkpoints every 2s, fail closed after 2.5s pending persistence or 4s since the last committed snapshot, and retain the
3s/400ms/2s ownership policy. This leaves margin inside the five-second rollback
window; clean logout acknowledges only committed final position. Migration 1 stays
byte-identical; ordered transactional migration 2 adds the durable schema.

Use [OpenSSL scrypt](https://docs.rs/openssl/0.10.72/openssl/pkcs5/fn.scrypt.html)
through the already pinned maintained library, rather than a custom password scheme
implementation or a new cryptographic dependency. Parameters are N=131072/r=8/p=1,
random 16-byte salt and 32-byte hash, with two concurrent hashing permits. The
parameter/version label is stored durably. Redis Lua atomically increments expiring
account/source-IP counters (10/30 attempts per minute), and Ping refreshes disposable
presence/session lookup. Redis failure closes new login but keeps existing sessions.
Roles remain scoped Postgres rows, with no automatic admin or privilege grant.

The dedicated account/checkpoint worker has 128 bounded jobs, separate from the
lease-renewal thread. World input is 256 commands; reliable output is 32 messages
and snapshots use one latest-value slot. Overflow disconnects/fails closed. Every
socket retains frame/rate/deadline checks; its requested send buffer is 8KiB (Linux
reports doubled allocation). DB/password/socket/cache I/O stays outside ticks.
Shutdown can drain persistence after stopping world advancement.

The client keeps the offline renderer and normal/tools separation. Its background
TLS worker feeds selection, prediction/reconciliation and full interest state;
rendering remains independent. An original minimal ASCII HUD avoids introducing
an editor dependency into the normal build. Non-ASCII wire chat is valid but has
placeholder glyphs. R is a deliberate reconnect/relogin, with no automatic retry
loop. Account provisioning reads stdin; there is no public registration/recovery.
Collision supports bounded slopes and conservative static-wall sliding, not jumping,
layered navigation or character/character physics. Combat, editor publication and
real KO variants remain outside this phase.

## D-015 — 2026-09-19: bounded combat vocabulary and transactional rewards

Phase 3 implements one targeted deterministic damage action, one NPC template/spawn,
one fungible nonstacking inventory item and linear XP levels. Package data selects
IDs, health/resource, speeds, damage, range, timings, spawn and grants. The strict
[vocabulary](../../content/gameplay.md) and source schema publish supported bounds;
no game ID appears in engine behavior. This chooses a small declarative vocabulary
over arbitrary scripts, multiple action/equipment systems or probabilistic damage.

Use 3D origin distance, tick cooldowns, command-order lethal-hit recipient, automatic
respawn with a fresh runtime ID, and idle/chase/attack/return AI over existing
walkability. Transient combat resets on reconnect/restart; acknowledged inventory
and XP do not. No PvP, assists/party sharing, line-of-sight, item use/drop or pathfinding
around complex obstacles is claimed. Levels currently display progression without
modifying stats. Phase 4 property candidates are documented but remain immutable.

The NPC encounter instance is its one reward operation ID. A realm/session-fenced
transaction locks character/progress, grants the entire reward or records
`inventory_full` without items/XP, and stores an immutable result. A constrained
aggregate inventory count represents identical fungible items; per-item identities
and physical slot layouts would add unused complexity in this vocabulary. Capacity
and item identity mismatches on an existing character fail selection and require a
future explicit migration policy. Starting inventory initializes once on selection,
including existing Phase 2 characters. Migrations 1 and 2 are unchanged.

Pending grants never update spendable inventory; actions pause for that character
until completion. Bounded workers keep SQL off the tick. Read-only authenticated
status lookup resolves a lost response; it cannot create a grant. Graceful leave
and shutdown drain grants. PG failure retains fail-closed/restart behavior. Runtime
instance pools consume durable sequence values in allocation order, with no aliases.

Phase 3 evidence records focused authority/AI tests,
cross-language action vectors, real Postgres concurrency/full-inventory/fencing,
process exits before/after commit and before response, and graphical playback.
An early graphical run exposed decreasing pool consumption, which concealed newer
reward IDs; consuming IDs in sequence order fixed it. Early crash-driver restart
also needed to wait for the previous owner's existing three-second lease to expire.
These findings changed implementation/tests, not the persistence or ownership gates.
Affected contracts: C-01/C-03/C-04/C-06; tasks P3-01–06 and Phase 4 candidate properties.

## D-016 — 2026-09-19: local KO monster experiment before Phase 4

The user accepted/merged Phase 3, explicitly paused Phase 4, and requested local
KO character/monster assets with textures and animations. This supplies the local
fixture authorization absent in D-012; it does not authorize asset redistribution
or imply that all previously unsupported formats now work.

Select the existing worm fixture: two opaque textured parts, 25 joints and four-or-
fewer influences. The bandicoot exceeds the engine's weight limit and is rejected,
not silently reduced (influence rule replaced by D-175, 2026-10-16, and that by D-176). Implement an independent bounded local converter to the
existing single-mesh/skin/texture/clip glTF subset. Atlas the two diffuse textures,
retain source metadata/hashes, and provide separate walk/attack releases. Runtime
binaries, synthetic demo, server authority and collision stay unchanged. Imported
animations remain looping presentation, without automatic action-state switching.

Alternatives were changing the runtime to a full multi-visual/multi-clip model or
using a static prop. The former broadens this test into an engine feature phase;
the latter does not meet the user's animation preference. The selected subset
exercises existing skinning/rendering and combat/durability without starting Phase 4.

[Support/launch guide](../../tools/assetc/KO-CHARACTER.md) records exact omissions,
unit assumption and source-layout references; evidence
records real and original-synthetic validation. Real source/derived bytes and
captures remain in ignored build directories. No reference revisions changed.
Affected: D-012 local-fixture availability; C-01/C-02 provenance; post-Phase-3 testing.

## D-017 — 2026-09-19: playable local field before tools phase

The user explicitly authorized publishing the KO branch and requested in-game UI,
login-to-map, several mobs, movement and KO-like camera controls. Extend this task
on `test/ko-character-assets`; Phase 4 remains paused. Publication of the earlier
asset commits succeeded after this explicit authorization.

Use original 48m field collision/terrain and a block player figure around the local
worm conversion. A full KO zone/material/UI importer would substantially broaden
the task. The basic HUD and input are original implementation informed by KO's
right-drag camera and click movement, with no copied reference code or UI payload.
The previous D-016 unchanged-runtime/shared-player-visual limit applies to the
historical asset experiment; this requested follow-up intentionally changes it.

N3G2 adds optional bounded spawn lists (1–32) and interest cell size (1–64m), with
independent NPC homes/runtime IDs and existing authoritative reward resolution.
Legacy packages remain byte-identical N3G1. Both formats are independently checked
by the server; all spawn locations must be walkable. No privileged spawn API or
editable property is introduced. The wire schema and database schema are unchanged.

Network play uses perspective orbit/terrain camera boom, camera-relative WASD,
click destinations and picking. Offline fixture projection remains for retained
pixel checks. A separate Compose project/realm/port retains field test progress.
See launch guide and evidence.
Affected contracts: C-01/C-02/C-03/C-06; extension of P3-02/P3-05, not Phase 4.

## D-018 — 2026-09-19: actual Karus HUD and animated male Tuarek

The user explicitly rejected the placeholder HUD/player and requested actual KO
HUD assets and a male orc, excluding the barbarian. Use race 2 (Tuarek) from the
local default-looks table, face/hair 00, with full weighted body parts and source
idle/run/punch/death clips. Race 11 is the distinct El Morad barbarian and is not
selected. Import the actual Karus UIF panel geometry and NTF alpha textures.
This supersedes D-017's placeholder-art choice, without starting Phase 4.

Add an optional complete five-file player/HUD presentation set to release identity.
Four clips reuse N3S1 and share their atlas; N3H1 stores bounded textured HUD records,
semantic bindings, normal button hit regions and a local substitute font atlas.
C++/Rust retain legacy four-file packages and reject partial/new unknown file sets.
No game ID, KO source path, race selection or UIF ID is embedded in engine modules.

Read existing source formats independently: bounded longer key tracks, exact 60Hz
player samples, and a repeat gutter for the observed subpixel hand UV overshoot.
Do not discard skin weights/parts or substitute a static character. Real source
bytes/full provenance and derived outputs remain local. Publish converter/runtime code,
original synthetic tests and text/hash evidence only; no proprietary payloads.

Use actual HUD normal-state artwork. Substitute installed Liberation Mono for
Windows text fonts; retain source rectangle/alignment/colour. Bind existing
HP/resource/XP/chat/attack behaviors; other menu actions provide availability
feedback. Minimap stays closed without an imported zone overview. Player transitions
are immediate; equipment, blending, full dialogs and source FX/audio remain outside
this requested basic testing task. Server authority, wire and DB schemas unchanged.

Evidence, current launch guide,
format.
Affected contracts C-01/C-02/C-06; phase remains paused before tools/admin work.

## D-019 — Smooth local presentation independently of fixed movement steps

Accepted 2026-09-19 after the user reported jitter in the KO field. Keep existing
20 Hz prediction and server reconciliation; apply a critically damped spring only
to the local rendered model and camera focus. Use local movement intent for facing
and locomotion so reconciliation cannot reverse the character or start a run at
rest. Approximate 67ms visual tracking lag is the explicit tradeoff. Reset on
session/entity/life changes, corrections over 2m and frame gaps over 250ms.
Collision, destinations and authoritative actions never use the smoothed position.
No wire, package or server change; remote snapshot interpolation is unchanged.
See movement evidence. Phase 4 remains paused.

## D-020 — 2026-09-19: local Ghidra reference tooling

The user added local client/server binaries and requested Ghidra plus Ghidra MCP.
Select pinned Ghidra 12.1.3, project-local Temurin Java 21, and the upstream
LaurieWired/GhidraMCP 1.4 bridge/extension. Build the extension against this Ghidra
instead of using its older precompiled release jar. Inspection found the upstream
HTTP listener binds all interfaces; change it to loopback and default port 18080.
The Codex side uses stdio. Keep setup, pins, original verification helpers and
usage documentation in `tools/ghidra`; keep tool binaries, dependencies, preferences,
analysis databases and input executables ignored. This avoids a system-wide Java
installation or introducing reverse-engineering tools into engine builds.

The user's corrected Blender location supersedes the earlier intentional nested
path; submodule revisions stay unchanged and historical evidence keeps its original
paths. The local source and binary references may describe different KO versions.
Successful import/decompilation does not establish semantic equivalence, full
analysis, or redistribution rights. Publish original behavior notes with input
hashes, addresses and uncertainty rather than bulk derived code.

Status: setup and live MCP verified, awaiting user testing. Evidence
records the four imports and warnings. No engine/authority/protocol contract changes,
no merging of the test branch, and no start of Phase 4.

## D-021 — 2026-09-19: binary-grounded v0.1 behavior before Phase 4

The user requested auditing existing components against the local KO executables
before Phase 4: a similar underlying implementation, with `games/demo` as close
to KO as practical inside v0.1. This makes behavioral fidelity an explicit review
gate, beyond the earlier functional and asset-import acceptance evidence.

Compare binary behavior, reference source and current n3e separately. Record
hashes/addresses and uncertainty; local filenames do not establish a canonical
release or a matched client/server/source set. The first pass finds real
source/binary mismatches and material differences in n3e's synthetic combat,
rewards, progression, movement and respawn behavior. See
audit and evidence.

Retain native Linux/OpenGL, Rust, n3e protocol, server authority, bounded workers
and Postgres durability. Put KO-specific definitions/presentation in packages;
add only the generic operations needed by the selected v0.1 behavior. Preserve
original default fixtures and optional local proprietary assets. Full KO protocol,
equipment/trade/party/skill systems and terrain import are not new prerequisites.

KA-01–07 are proposed correction/research gates, not implemented replacements for
D-014/D-015 or C-01–06. Changes to authoritative rules, packages, wire messages
or durable state require their own migration/verification evidence. Phase 4's
registry remains provisional until these gaps are resolved or explicit scoped
deviations are reviewed. No merge or engine change occurs in this audit session.

## D-022 — 2026-09-19: bounded KO phases for fresh chat sessions

The user requested separate Codex chats to keep the KO grounding work within
manageable context. The KO-00–13 plan splits the coarse
KA-01–07 audit recommendations into fourteen phases, each with a narrow outcome,
entry points, stable task IDs, verification gates and a copyable kickoff prompt.
Original Phases 4–6 keep their numbering and scope.

KO-00 continues the existing audit as research only and establishes a bounded
reference profile; subsystem-specific research stays with its implementation
phase. KO-08 resolves reward durability/migration semantics before KO-09/10
implement settlement/XP and claims separately. The new reward profile cannot
activate until both halves are verified. KO-11 assembles the demo, KO-12 closes
lifecycle coverage and KO-13 validates the integrated result.

The normal testing/merge workflow remains: before KO-01, the current unmerged KO
test/audit/profile work requires acceptance and explicit merge authorization.
Subsequent implementation phases use `phase/ko-NN-short-name` from freshly fetched
`origin/main` after prerequisites merge. Planning is not acceptance, merge
authorization, implementation or permission to start original Phase 4.

Each phase gets a fresh chat and ends at its review/testing handoff. If it cannot
fit safely, publish an explicitly incomplete checkpoint and resume that same
phase in another chat, preserving open gates. STATUS and evidence, not chat
history, carry the next session's context. No new product features or changes to
C-01–06 are established by this documentation-only scheduling decision.

## D-023 — 2026-09-19: bounded reference profile with explicit calibration gate

KO-00 selects profile revision 1: ordinary untransformed,
unbuffed, unarmed player versus a normal hostile melee NPC, with the existing
Tuarek/worm pair as optional local visuals and original default fixtures.
This is a research target awaiting user review, not a matched historical release
or activated package. Each subsystem names its reference executable; missing
server table values remain unknown. All K-rows have later-phase ownership.

Imported coordinates at explicit scale 1 and original asymmetric fixture sizes
are measured. They do not establish physical metres or gameplay radius. The
binary target-radius getter is confirmed; source joint-bound reconstructions
produce different candidate radii at different sample frames. Keep KO-01's
world-scale/radius-initialization/collision-dimension prerequisite open until a
narrow trace/measurement or explicit reviewed deviation resolves it. Do not use
mesh extents, inventory-preview normalization or these candidates as defaults.

C-01–06, current runtime rules and schemas remain unchanged. The stronger n3e
authority/durability and proprietary-free default build remain required.
Evidence records the checks and limits.
No merge, deployment or later-phase implementation is authorized by this record.

## D-024 — 2026-09-19: approved KO-01 calibration deviation and bounded movement

The user explicitly approved the concrete calibration deviation:
adopt one source-world unit as one metre, test 1.5m/s walk, 4.5m/s run and 1.5m/s
backward, retain synthetic 0.2m wall radius/1.6m height/0.25m support step limit.
Exact reference physical scale and the selected pair's runtime radius initialization
remain unresolved. The newly recovered `0041c300` supports the source joint-bound
radius formula; it does not justify substituting that sphere for n3e collision.

Choose generic optional N3G3 data and explicit engine/protocol 2/2 negotiation;
retain old 1/1 packages and their legacy movement path. Both readers validate the
new policy. The server validates mode alongside sequence/session/intent; it alone
selects the speed and elapsed step. C++ prediction replays the same modes/policy.
Movement uses 1–6 collision substeps, each at most half the smallest supported wall
radius. Retain n3e's slope/step/sliding solver, documenting its differences from
KO's raised-ray and frame-dependent climb checks rather than copying those checks.

An original laboratory and optional existing KO visuals exercise the change without
activating a new demo profile. V toggles walk/run; S requests backward speed;
full input/camera/facing and animation work remains with KO-02/07. NPC/combat,
wire authority and database durability stay unchanged. No proprietary dependency
or reference checkout changes. A live test exposed Nagle-delayed client input;
TCP_NODELAY and a fixed input deadline prevent that avoidable cadence loss.

Affected: KO-01-01–03, K-01, C-01/02/03/06; evidence,
[package format](../../content/gameplay.md#optional-movement-extension-n3g3),
manual testing. This acceptance of a deviation does not mark
KO-01 user-tested/merged or resolve KO-03's size-aware melee range contract.

KO-01 testing follow-up: the user requested movement feel/backward/stop fixes,
then explicitly chose to retain 1.5/4.5/1.5m/s until those fixes are tested. Use
the source login run default, distinct source clip indices 1/2/3, and reversed
facing for backward travel. Add only a paired optional locomotion presentation
extension to 2/2 packages and authoritative movement-mode reporting. Local input
release settles the visual spring at prediction immediately. Full animation
graphs, camera/turn controls and exact calibration remain deferred. See
follow-up evidence.

Further KO-01 user testing explicitly requested the stop camera correction,
facing-relative A/D+W/S controls and held-left cursor following. These narrow
input corrections are authorized on the existing branch despite originally
being deferred with KO-02. Match the ordinary source/binary 60-degree/second
turn, independent third-person camera yaw and 0.1s held-click gate; preserve
approved speeds and server movement authority. Separate camera smoothing from
actor settling. This does not start/complete KO-02 or resolve its package camera
profile, zoom and obstruction work. Evidence.

## D-025 — 2026-09-19: bounded camera/input package and ordinary zoom trace

KO-02 identifies `0063e2e0` as the ordinary right-drag zoom callee, distinct from
`0063e270`. The former's normal third-person branch clamps to 2–10, matching source;
the latter's below-10/write-9 anomaly is not evidence for normal zoom defaults.
Select 10°–70° pitch, 25° initial pitch, 7m initial distance and .8×body-height focus.
The accepted KO-01 physical-scale/synthetic-height deviation still applies.

Keep the existing drag-yaw/pitch plus wheel-zoom mapping and frame-independent
pixel sensitivity as a labeled adaptation awaiting user testing. Do not add
first-person, screen-edge turning, combat automation or a full terrain importer.
The renderer's 60° FOV/.05m near plane and separate follow spring remain.

Partly superseded on 2026-10-02 by
[D-143](#d-143--2026-10-02-mode-3-camera-input-right-drag-yaw-and-distance-homeend-pitch-and-screen-edge-yaw-as-package-data)
(PQ-012): for the KO package, KO's mode-3 right-drag yaw + distance replaces
the drag-pitch adaptation, the "frame-independent pixel sensitivity" label
becomes D-143's frame-time correction, and screen-edge turning (with Home/End
pitch) is added. The demo package and the KO-02 laboratory keep this
decision's mapping; the rest of it stands.

Add optional generic N3V1 presentation/input data with explicit engine 3 compatibility;
retain wire 1/2 according to gameplay, unchanged C-03/04 authority and durable state.
Both readers validate the exact hashed camera asset. Legacy packages retain their
profile defaults, while corrected capture and collision safety apply to all play.

Use a bounded conservative sphere sweep over existing N3C1 triangles (expanded
triangular prisms), immediate retraction and desired-zoom recovery. Conservative
corner retraction, zero boom for embedded focus, and lack of full KO terrain/runtime
verification remain explicit. Nearest-surface picking cannot select ground through
walls. These original algorithms use geometric observations, not copied reference
code. Evidence, [format](../../content/camera.md).

## D-026 — 2026-09-19: client melee intent, authoritative radius range

KO-03 uses the client as the repeat/approach owner, following the reference's
ordinary interaction structure. The server continues to validate individual
requests with authenticated identity, independent action sequences, server ticks,
live entities, resource and reward state. No persistent intent or wire change is
needed. Stop cannot retract an already-sent request; at most that request can
resolve afterward. Repeat pacing survives stop/start, and reconnect starts stopped.

Optional hashed N3M1 policy requires engine 4, retaining protocol 1/2 according to
movement. Both readers and the producer enforce the policy and compatibility.
Zero cost is supported only with this explicit policy; positive-cost actions keep
their checks. Existing packages retain their behavior. No database migration.

Client binary `00468750` uses horizontal inclusive range and strict dot > .7;
`00468620` half-sums scaled radii and adds applicable weapon reach. `005e1490`
and tick fallback use a 3D approach comparison after horizontal attackability
fails. The unarmed client interval is 1s. Ebenezer `00496169` validates interval
and elapsed time but only calls `004c1dbe` in the inspected equipped branch;
that helper is horizontal and strict at its distance boundary. These are distinct
checks, not proof that the historical server enforced the client radius formula.

n3e deliberately enforces package-owned horizontal size-aware range on every
player melee request and retains a strict server cooldown without the reference's
half-second allowance. Facing is a client approach/presentation policy, not a
server security claim. Direct horizontal approach with a 5% stopping inset avoids
copying inconsistent 3D fallback behavior. No vertical/LOS or pathfinding gate is
added. NPC AI and fixed damage remain unchanged.

The original laboratory uses synthetic 1m gameplay radii, zero extra reach,
.7 facing dot and 20-tick interval. These exercise the generic policy, do not
activate a coherent demo profile, and do not claim measured Tuarek/worm dimensions.
The accepted unit deviation and unresolved exact radius calibration remain.
[Contract](../../content/melee.md), evidence,
walkthrough. Affected C-01/02/03/06; durability C-04 is retained.


KO-03 testing correction: the user explicitly requested Tab-time facing and a
combat-ready pose. Source nearest-target commands rotate after selection;
`TargetSelect` refreshes the basic stationary pose, and `JudgeAnimationBreath`
selects unarmed ready (86) for a hostile target. Binary `005d9ce0` confirms the
stationary basic-action refresh; nearest-target wrappers call rotation `004579d0`.
Implement local selection-time yaw and an optional hashed ready clip, with
movement/strike/death priority. No attack request or damage follows from selection.
The old immediate animation transitions and local-only facing remain; this does
not start KO-07. Evidence.

## D-027 — 2026-09-19 bounded normal damage and server RNG

KO-04 implements optional engine-5 N3D1 `contested_melee_v1` with independent
player/NPC attack, defense, accuracy and evasion. Preserve distinct binary rounding
and normal NPC highest-grade multiplier; support only nonnegative bounded stats,
unmodified ordinary actors and a normal hostile NPC. No game IDs or stat tables
enter engine code. The original lab selects synthetic 36/20/50/100 player and
18/40/50/100 NPC stats; the coherent demo remains KO-11's scope.

Use a once-OS-seeded server SplitMix64 stream with bounded multiply-high mapping,
not the binary CRT's modulo bias and up-to-ten attempts to avoid equal draws.
This intentional RNG difference precludes claims of identical sequences or exact
historical distribution. A fixed model version binds coefficients and hit bands;
test-only injection proves numeric/authority boundaries without exposing a client
seed. Miss consumes the normal cost/cooldown and does not stop continuous melee.
Zero-damage successful rolls remain hits. Old packages keep fixed damage.

Add server-authored latest strike result/amount to snapshots and `miss` to action
feedback; retain wire framing, session authority and durable reward transactions.
The [damage contract](../../content/damage.md) specifies compatibility and bounds.
Evidence distinguishes binary findings, source comparison,
synthetic policy and unverified dynamic reference fidelity. No later phase started.

## D-028 — 2026-09-19: bounded normal hostile NPC policy

KO-05 traces binary farthest-first acquisition (`0041bc5a` → `0041c21e`,
comparator `00427706`), despite the source's nearest-target comment. Preserve the
binary ordering with a deterministic lowest-character-ID tie-break; binary equality
has no stable tie guarantee. Retaliation `0041f715` compares fresh damage rolls,
not cumulative contribution, in the 0–49 branch. Implement the observed 0–49,
50–79, 80–94 and 95–100 bands using KO-04's bounded server RNG and current template
stats. The source differs and is not substituted for this binary observation.

Optional N3N1 `hostile_melee_v1` requires engine 6; wire remains 1/2 by movement.
Producer and both readers enforce bounds and compatibility. Old packages keep their
AI. No database, reward, spawn/admin API or corpse/respawn-policy change.

Preserve simple collision walking; choose bounded pursuit/stall/return deadlines,
failed-target suppression, a home leash, full home heal and recovery delay. A return
that cannot finish teleports to its validated spawn after its deadline. These are
explicit n3e adaptations: the traced binary return helpers do not establish
heal-on-arrival or identical leash behavior. Attacks can still damage/kill during
return, but cannot interrupt it. No special NPC, social aggro, faction/GM exemption,
magic, random roaming or general pathfinding is introduced.

Timers, ranges and high lab HP are synthetic comparison data. Target binding includes
runtime identity; target changes and repeated hits never reset attack cooldown or
active pursuit budget. The state table and precise fields are in the
[NPC contract](../../content/npc.md); evidence records
static findings, verification and remaining subjective review. No matched release
or dynamic execution of reference binaries is claimed. KO-06 remains unstarted.

## D-029 — 2026-09-19: requested life policy (recovery superseded by D-030)

KO-06 implements optional N3L1 `requested_v1`, engine 7/wire 3, preserving older
packages' automatic respawn. The chosen binary requires dead state and the client
sends a guarded normal regeneration request. The normal handler has no elapsed
death-delay comparison; the three-second lab delay is synthetic server policy.
Source blinking protection differs from the selected binary's ordinary handler;
no full protection trace or matched release is claimed. Choose no protection,
penalty, resurrection spells or location selection. Retain full HP/resource at
the existing deterministic walkable zone spawn. See research/evidence.

Separate player eligibility, NPC corpse visibility and NPC respawn deadlines.
Explicit states and atomic snapshots preserve replacement IDs; dormant NPCs are
absent until a fresh instance spawns. Authenticated session, monotonic request
sequence and expected dead instance fence duplicate/stale healing requests.
The client clears death/approach/selection intent and prediction on replacement.
Existing animation assets and controller behavior remain for KO-07.

Retain C-04 transient combat recovery: reconnect/restart restores full life at saved
position with fresh session/runtime identity. This can bypass the death wait and
heal via reconnect, an explicit v0.1 limitation. Persisting death and penalties
would require a different durable policy; it is not silently introduced here.
Respawn may occur while a reward is pending: grant completion updates only durable
inventory, never a captured old entity. Existing disconnect drain, immutable
encounter result, fenced transaction and fail-closed PG/lease behavior remain.
[Life/wire contract](../../content/life.md), walkthrough.

## D-030 — 2026-09-19: preserve requested player death across reconnect

The user rejected D-029's reconnect revival limitation and authorized fixing it
within KO-06. Ghidra confirms the supplied official Ebenezer login path reconstructs
death from saved City/HP, and Aujard saves both fields. See the
correction evidence for addresses and boundaries.

Migration 004 stores dead state, revision and database eligibility deadline. Death
and requested respawn commit location and state before snapshots/success. Offline
time counts; reconnect uses a fresh identity without healing a dead character.
A lifecycle revision fences older checkpoints even when movement sequence is equal.
The bounded async worker and realm/session fences remain; life and reward jobs drain
on disconnect/shutdown. In-flight life commits pause snapshots, and a pending reward
can delay them. Unknown commits recover through durable state on restart, never a
second heal. A saved dead character cannot be loaded under a policy lacking requested
respawn. NPCs, nonlethal HP/resource, fixed spawn, synthetic timers and no penalties/
protection remain as specified in D-029. No KO-07/08 work is included.

## D-031 — 2026-09-19: bounded whole-body animation presentation

KO-07 adds optional engine-8 N3A1 metadata and complete player/NPC clip sets.
Wire compatibility remains selected by life/movement; no durable schema changes.
The binary frame controller and joint blender confirm frozen incoming entry
frames, per-clip blend times and once-and-hold. Source rates are already baked
into cooked seconds. See [contract](../../content/animation.md) and
research/evidence.

Use full-body TRS blending, one selected attack/death per role, explicit one-shot
attacks driven only by replicated strike ticks and authoritative death holding.
Retain existing walk/run/backward/ready selection. Deliberately capture the
currently evaluated pose on interruption; use modulo across long gaps and suppress
old cosmetic marker pulses. First sight of a corpse holds the endpoint; session,
despawn and replacement identities reset presentation. Local intent alone may
select locomotion/ready, never hit/death outcomes. No marker can authorize damage.

Upper-body attacks, animation queues, additional freeze delays, random variants,
modifier-driven clip speeds and FX/audio remain unsupported. Original fixtures
are mandatory; optional local imports retain raw metadata/hashes, including the
punch loop flag overridden by one-shot playback and worm attack trace frames
outside its selected clip. No matched reference release or dynamic binary run.

KO-07 testing correction: the user reported a walk→idle pop. The pre-animation
KO-01 stop policy snapped the rendered actor to prediction while the camera kept
smoothing. For N3A1 packages, retain the actor's spring through the idle blend;
input/prediction/server movement still stop normally. This supersedes the immediate
visual-stop part of D-024 only for blended animation packages. Identity/life,
large correction and long-gap resets remain immediate. See
stop correction evidence.

## D-032 — 2026-09-19: reward settlement and claim design

Status: KO-08 design user accepted and merged. KO-09 settlement/progression is
implemented under the isolated gate in D-033; ordinary activation remains closed.
Acceptance.
Question: separate contribution XP and loot without weakening C-04 or re-awarding
legacy operations. Select one all-recipient XP+entitlement transaction, then
independent single-item claim/expiry transactions. Reject per-recipient partial
commits, in-memory-only entitlements and reinterpretation of legacy full-bag results.
Contract, research/evidence.

Use capped contribution, ceiling shares and observed low-level binary multipliers;
explicit exact 3D/alive/same-zone eligibility and lowest-character-ID ownership ties
replace ambiguous/stale legacy behavior. Keep one aggregate inventory item, owner
exclusive 120s entitlement and nonterminal full-bag claim rejection. A ten-level
original curve with fixed stats and no level-up heal bounds progression while
authentic table rows remain unverified. These are deliberate reviewable deviations,
not claims of historical table fidelity.

Migration 005 and explicit offline conversion preserve lifetime XP, inventory,
legacy level/fraction and immutable results; unsupported old levels reject the
conversion instead of resetting progress. No rollback to legacy after conversion.
KO-09 owns settlement/migration and isolated test-only activation, KO-10 claims and
end-to-end activation gates. Affects C-01/03/04/06, KO-09/10 and later KO-11 assembly;
no production schema/runtime/package changed during KO-08.


## D-033 — 2026-09-19: isolated contribution settlement implementation

KO-09 implements D-032's S transaction and migration 005, with engine 9/wire 4,
N3P1 independently hashed reward definitions and N3S2 canonical frozen payloads.
The original ten-level lab follows the approved fixed-stat/no-heal policy. Exact
[encoding and operational bounds](../../content/progression.md),
evidence.

Keep legacy operation IDs/status fields separate from the new settlement family.
Progression applies only newer revisions, and admission reloads cover commit/join
races. Home recovery reserves a fresh identity before abandoning credit. Reserve
queue capacity conservatively before every otherwise-valid attack, rather than
rolling damage and consuming RNG before knowing whether a lethal result fits.
At saturation this can also reject nonlethal hits/misses; no resource or damage is
spent. Eight completed all-recipient settlement results may apply per tick.

Use the pinned PostgreSQL 17 transaction timeout for the remaining two-second
worker budget, bounded retries only for known rollbacks, and fail-closed recovery
for ambiguous commits. Conversion is an explicit offline command restricted to
`test-` realms and `N3E_TEST_PROGRESSION=disposable`; absence of a policy row means
legacy. Its retained gameplay divisor must match the old realm, and is recorded
along with each baseline. No live conversion, claim/expiry mutation or new demo
activation occurs. Claim tables/IDs are reserved for KO-10, which has not started.

## D-034 — 2026-09-20: durable single-item claim and expiry

KO-10 implements the accepted C/E transactions on migration005's reserved tables,
with no new migration and no edits to prior checksums/history. Opt-in engine10/wire5
adds owner-only bounded discovery, semantic claim requests and historical status.
Require the existing requested-life policy for engine10 so concurrent death
participates in the durable life-revision fence. Engine9/wire4 retains isolated settlement-only operation; old releases keep legacy
rewards. Normal startup now permits an explicitly converted engine10 lab after
its C/E and two-client end-to-end verification. Offline conversion remains test-
realm restricted; no existing live realm is converted or deployed.

Freeze the authoritative actor position/life at ordered tick admission and compare
against the durable drop in the worker. This preserves the approved range timing
without a competing cached entitlement authority. Use one per-character claim and
64 realm permits retained through disconnected drains. C/E serialize under the
existing realm/policy/character/progress locks; the DB clock decides expiry. Full
bags are nonterminal, and item claims never mutate earned XP. The no-spending
inventory allows monotonic count application independently of newer XP revisions.

The minimal shared overlay and F binding show saved drop locations, pending and
terminal results. A default original two-slot/120-second lab and a ten-second
fault-test variant remain separate from games/demo. See the
[contract](../../content/loot.md), evidence and
walkthrough. Reference bundle lookup/removal/slot behavior is reused
from KO-08's verified static artifacts; owner exclusivity, exact range and durable
transactions are deliberate n3e adaptations. No historical table or dynamic
reference fidelity claim, inventory spending or KO-11 implementation is added.


## D-035 — 2026-09-20: coherent original demo and cosmetic variants

KO-11 selects the accepted KO-01–10 generic policies in `games/demo` under
engine10/wire5 and package 0.2.0. No schema, wire or production server logic changes.
[Exact selected values and provenance](../../games/demo/PROVENANCE.md) distinguish
binary findings, accepted deviations and original playable balance. No authentic
stat/XP/drop table or matched historical release is claimed.

Keep the original foundation fixture byte-identical under
`tests/fixtures/legacy-demo`, with its own cooked output, so historical legacy
protocol/reward tests do not silently test new semantics. Default cooking remains
standard-library-only and distributable. Original closed-box animated actors and
bitmap HUD replace the earlier flat diagnostic flag for usable camera views.

The only generic client change exposes already-validated N3P1 thresholds to the
XP HUD: use curve XP for progress and lifetime XP for the total, with MAX at cap.
Retain linear display for old releases and existing authenticated action/loot/life
bindings. Unavailable imported buttons report that their feature is not implemented.

Optional ignored KO artwork changes presentation only; every authoritative policy
and collision file is checked byte-for-byte. A small original alternate package
changes namespace, running speed, HP, base XP, camera and colours with identical
engine executables. This is the scoped boundary check, not Phase 5.

The demo launcher creates disposable local test realms, explicitly converts their
empty reward policy offline and starts the ordinary server. It does not authorize
or implement existing live-realm conversion, deployment or a persistent launcher.
No later phase started. Evidence.

## D-036 — 2026-09-20: bounded session comparison and remote lifecycle resets

KO-12 retains the accepted TLS/authentication/interest/durability architecture
as explicit deviations from the newly traced reference login/create/select/chat
and region paths. Comparison records per-path evidence,
version disagreements and absent dynamic testing. No protocol, package version,
storage migration or server authority changes are needed.

Remote positions still interpolate over 100ms, clamped without extrapolation.
A different session, missing instance, life/alive transition, nonadvancing tick
or baseline gap above four 20Hz ticks snaps to current position. Two missing
10Hz intervals are the tolerated continuity window; this synthetic presentation
choice prevents replaying stale travel after a stall and is not KO calibration.
Existing visibility/session pose and animation eviction is retained. F5 status
text now matches the actual reconnect binding.

A disposable original demo clone changes only interest-cell size from 32m to 4m
for leave/reentry verification; the normal demo covers its whole ±24m field.
The retained Phase 2 driver selects its own four serialized DB tests, excluding
KO-09/10's independently orchestrated fault entry points. This corrects stale test
discovery, not a production persistence defect. Evidence.


## D-037 — 2026-09-20: KO-13 integration and Phase 4 property boundaries

KO-13 reconciles all K/KA findings in the acceptance matrix.
Previously accepted deviations remain explicit; integrated user acceptance and
merge are now recorded in the KO-13 merge evidence. No new historical fidelity, deployment or editor pass follows
from retained static findings or automated n3e tests.

The Phase 4 registry must respect engine10/wire5, durable requested life and the
immutable N3P1 reward definition. Supersede the original design's live XP-multiplier
example: no such property exists, and changing reward semantics on a converted
realm requires a reviewed forward migration, not a live config setter. Current
model/stat/movement/collision/asset policy stays release/restart-only. Saved
outcomes, XP/inventory and life deadlines are not generic editable properties.
Decoration/lighting and next-cycle spawn overrides remain proposed Phase 4 work;
weather/time needs a bounded design before an implementation claim. C-05's
transactional authorization and C-04's commit/application/recovery gates still apply.

Only verification tooling and documentation change in KO-13. The demo driver's
`--restart-check` uses the actual package and its own disposable database/process,
verifying acknowledged XP/claim and saved death after SIGKILL and lease takeover.
Evidence. No wire, package, schema or runtime changes.


## D-038 — 2026-09-20: bounded KO catalog before completing v0.1

The user approved a broad feature inventory before original Phase 4, followed by
completion of original Phases 4–6 and incremental support for additional features.
KO-CAT is research-only: catalog breadth first, deepen only
architecture-sensitive findings before editor/admin implementation. This does not
reopen accepted KO-00–13 gates or add all discovered features to v0.1.

Track evidence confidence independently from n3e support. Record reference
identity, disagreements, unknowns, dependencies and engine/package ownership.
The available inputs are not a verified matching historical release. Survey
coverage and explicit gaps define completion, not exhaustive reverse engineering.
Each potential Phase 4 impact needs a disposition; material scope/architecture
changes need user review rather than an incidental implementation. After catalog
review and explicit merge, resume Phase 4 on separate request.

This session prepares instructions/specs only; catalog research is not started.
Planning evidence.


D-038 follow-up: the user prioritized an actual recognizable KO map to run around
and requested the moderator Q-speed feature. KO-CAT begins with map dependency/
collision feasibility and source/binary turbo research, then proposes a bounded
implementation slice and scheduling relative to Phase 4. A narrow source check
identifies manager-only held-Q and a 10× multiplier; binary/server enforcement
is unverified. n3e turbo must use authenticated character authority on the server,
not client flags or the tools build. No noclip behavior is implied. These are
explicit implementation intentions, not delivered features or permission to turn
KO-CAT into runtime work; review the concrete plan before changing phase order.


## D-039 — 2026-09-20: KO-CAT research dispositions and proposed exploration slice

Research conclusions awaiting user review; this record does not accept a new
implementation phase or merge. Catalog,
impact review, evidence.

Select local Moradon Christmas for the proposed exploration slice: smaller terrain,
table-selected variant and available scanned dependencies. Its server SMD is not
height-identical, so propose one shared validated collision bake with explicit
blocked areas. Full dependency parsing, spawn, landmarks and performance remain
implementation gates. Static client 10× turbo and legacy authority exemptions do
not establish secure server authorization or dynamic behavior. Proposed n3e held-Q
must use server character capabilities, expiry/revocation resets and bounded
collision; no noclip or generic live-speed setter.

All 13 architecture concerns are dispositioned against C-01–06/D-037. No material
unresolved architecture decision blocks the existing Phase 4 scope after catalog
review/merge. I9 proposes deferring weather entirely, retaining lighting for its
publication gate. I13 recommends a separately approved exploration/turbo phase
between Phase 4 and Phase 5, reusing production permissions. Neither proposal is
accepted by this research record. Default Phases 4–6 and their gates remain.
No engine, wire, schema, package or reference changes. Future features deepen
research separately; enum/UI/packet names do not prove complete historical systems.


## D-040 — 2026-09-20: binary-first catalog and fidelity target

The user requires the binaries to be the behavioral source of truth, including
features absent or stubbed in the available source. Deliberate deviations require
a demonstrated logic bug or player exploit. Policy
records the distinction between historical acceptance, current support gaps and
future fidelity; D-038/039's implementation sequence and C-01–06 remain intact.
Existing simplified behaviors are not automatically permanent exceptions.

KO-CAT's revised research handoff has 57 stable feature records, a per-role
binary index and 256 explicit dispatcher cases. Missing
client/server counterparts and untraced leaves remain explicit. Binary source-of-
truth does not imply that these four executables match each other or the assets.
No dynamic reference fidelity, complete whole-program recovery or new bug/exploit
exception is certified.

Ghidra MCP worked after the user opened programs with the plugin. Active AI
string/xref/decompile/assembly and client merchant decompilation were exercised.
Interactive navigation is easier; reproducible multi-program collection still
uses the separate read-only headless project. No program-selection tool is exposed
by this MCP version. Phase 4 impact I14–I17 covers newly discovered authority,
economy, persistence and fidelity boundaries; no implementation/merge is authorized
by this record. Awaiting review on the existing `phase/ko-catalog` branch.


## D-041 — 2026-09-20: accept KO-CAT, weather deferral and exploration order

The user accepted the binary-first catalog, explicitly approved both recommended
scope/order decisions and requested merge/push. I9 removes weather/time from
Phase 4; lighting satisfies its visual publication gate. I13 fixes the sequence:
Phase 4 -> bounded Moradon exploration/hold-Q turbo -> Phase 5 -> Phase 6.
The map report supplies exploration bounds, dependencies and acceptance criteria;
a detailed task spec is prepared at its separate implementation kickoff.

KO-CAT's 57 records, 256 dispatcher cases, binary-first policy and 17 impact
dispositions are accepted within documented research limits. This does not
certify dynamic fidelity, fill missing binary counterparts or approve behavioral
exceptions. It starts no engine implementation. Phase 4 is the next separate
implementation request after the catalog merge. Merge evidence.

## D-042 — 2026-09-20: typed tools registry and durable revision implementation

Phase 4 implements engine11/wire6 and migration006 without changing prior
migration checksums, reward definitions or KO gameplay algorithms. The optional
hashed N3T1 package projection has a closed typed vocabulary: non-collidable
prepackaged decoration transforms, lighting, and next-cycle spawn/life definitions.
The demo opts in; engine1–10 packages remain supported. C-05 excludes all generic
role/secret/gameplay-state and live balance setters; weather/time stays deferred.

A stable per-character authority row provides a lock even when a character has no
roles. Administrative transactions lock authority before realm ownership and
current character session, recover authenticated immutable results before checking
new capability, and atomically append revision/result/before-after audit. Role
revocation uses the same authority lock and increments a durable generation.
Existing bounded database workers perform I/O; at most 16 outstanding admin jobs
and eight completed activations per tick are admitted. Full revision snapshots
replace delta chains and naturally resynchronize coalesced/missing deliveries.
Startup validates/replays committed overrides before readiness. No optimistic
publication or Redis-only state exists.

Temporary NPC operations have durable authorization/result/audit but explicitly
transient effects: 16 simultaneous, 60-second expiry, 128 applied identities per
process. Realm-generation binding prevents a retry from resurrecting a temporary
NPC after restart. A status lookup cannot create a temporary NPC. Existing spawn
cycles retain captured position/timer definitions and their contributions; future
cycles capture the new revision. Saved player life and reward outcomes are untouched.

The supported local prefab is scene.bin, with uniform scale/yaw and positional
handles. This is a bounded original-fixture editor, not a general asset importer.
Draft/release export bakes absolute values. Explicit cosmetic-only draft rebase
requires unchanged authoritative dependencies; existing realms fail on an
incompatible base. Export/redeploy verification uses a fresh disposable realm;
in-place populated-realm content adoption remains a separate migration/release
operation, never deletion of overrides. These are conservative implementation
choices within C-01–06, not changes to approved I1–I17 deferrals.

[Registry/operations/review guide](../../content/editing.md),
Phase 4 evidence and impact closure. No KO fidelity claim
or new behavioral exception is inferred from engine tests. Accepted sequence:
Phase 4 -> separately requested exploration/turbo -> Phase 5 -> Phase 6.

### D-042 user-testing UI follow-up — 2026-09-20

At the user's request, the terminal is an independent top dropdown toggled by the
backtick/tilde key. Shift + left-click on registered decoration geometry opens a
self-contained object inspector; F2 retains world settings/hierarchy. The object
inspector supplies its own editing, preview, draft and publication controls. One
object inspector is open at a time. All views retain the same typed local draft,
undo history and durable publication path; controls explicitly label whole-draft
operations. Closing a view preserves the local preview. No authority, registry,
wire, database, gameplay or accepted deferral changes.

Superseded on 2026-09-20 by the revision below; the terminal decision stands.

### D-042 terminal-first editing surface — 2026-09-20

At the user's request the Shift-click object inspector is withdrawn until the
intended edit surface is decided, so editing is driven from the terminal and the
retained F2 world editor. Removing it deletes only client UI: no registry entry,
capability, wire message, validation bound or publication path changed, and the
P4-02 picking/gizmo/inspector deliverable is still met by the F2 window and its
screen markers.

The terminal gains a bounded 512-line scrollback that echoes each command, keeps
its output, appends each asynchronous typed result once, and survives closing the
window. It also gains read-only `list`, `scene`, `get` and `draft` commands over
the existing registry and local draft, plus `clear`. These project package-owned
descriptors the client already holds; they add no server operation, expose no
gameplay or account state, and `scene` lists editable objects only. Deliberately
minimal while the edit surface is undecided: no new editable property, no scene
graph beyond the registry, and no free-camera or terrain selection.

## D-043 — 2026-09-20: KX kickoff and server-authority direction

Status: accepted direction; no runtime implementation. Question: how should the
bounded Moradon exploration and hold-Q turbo phase resolve its open authority
choices? The user requested the phase after the Phase 4 merge and directed that it
be **server authoritative as much as possible**.

Selected: one validated terrain/OPD-derived collision bake consumed by both the
C++ client and the Rust server with a compared identity, never a client-only or
client-first walkability path; a bounded boolean hold-Q intent carrying session,
life and input sequence, with the server choosing the effective speed from
immutable package policy and publishing effective mode plus a permission
generation; `movement.turbo` provisioned through Phase 4's operator path and
validated against the authenticated character, realm and zone; bounded server-side
expiry of held intent; and a bounded authorization lease that fails closed.
Revocation is acknowledged only after simulation invalidation is known applied,
never on Redis Pub/Sub alone.

Rejected: the legacy trust boundary. `GameProcMain::MsgSend_Move` sends a
client-scaled speed with no authenticated turbo field, and `CUser::MoveProcess`
consumes it with its speed check commented out. The binary's `00494beb` timing and
distance guards are not authenticated grants and do not establish that forged
turbo is rejected. Client GM gating is not server authorization evidence. The
unrecovered binary key-array base, the extra `+0x7f4 < 5` guard and authority
0/250 remain unresolved, so n3e implements its own contract rather than encoding
unverified legacy semantics.

Consequence: client prediction remains for playability but is correction-bound,
and a forged ordinary-player request must be corrected without granting speed as
an acceptance gate. The 10x default (demo run 4.5 -> 45 m/s) needs 45 substeps at
20 Hz against a current maximum of 6, so the phase must budget per-actor/per-tick
work and indexed local collision queries and reject unsupported speed/package
combinations rather than enlarge substeps and tunnel. Existing 6 m/s readers
require a versioned extension with explicit compatibility rejection. Where full
server authority proves impractical, the residual risk is recorded explicitly
instead of widening client trust. Affected: KX spec,
kickoff, C-01/C-02/C-04/C-06 and the reused Phase 4
C-05 registry. D-041's accepted order and weather deferral are unchanged.

## D-044 — 2026-09-20: engine 12 static world asset and the corrected tile diagonal

Status: implemented on `phase/ko-exploration`. Question: how should a package
carry a whole imported map's visible geometry, and which quad diagonal does the
cooked surface owe the reference?

Context. The first KX visual pass expanded Moradon into `scene.bin` through a
`prebuilt_scene` hook. That was wrong in three ways at once. `scene.bin` is the
*instanced* model the client repeats per entity and per editable decoration, so
in gameplay the map was never drawn as the world at all: the network path drew
the collision hull with the demo's procedural meadow shader and used the map mesh
as the per-entity model. The scene's single atlas is also the NPC atlas, which is
why the KO player presentation had been dropped. And an animated scene's budget
(65,536 vertices) forced 2,260 of 2,688 static placements to be discarded.

Selected: a separate optional cooked asset, `world.bin` (`N3W1`), holding a
package's static visible geometry and its own RGBA atlas — position, normal and
**two** UV layers per vertex, indexed, never posed and never skinned. It is
uploaded once into its own buffers and drawn in its own pass, so it costs no
per-frame CPU. It requires engine 12, retains wire 6, and builds on the engine 11
editing contract. Its bounds are its own (2048² atlas, 196,608 vertices, 589,824
indices, 32 MiB file); every other cooked asset keeps the 16 MiB bound. The
server checks its presence and hashes it into release identity but never
interprets it. `prebuilt_scene` is removed; nothing used it any more.

Two UV layers rather than baked composites: `CN3TerrainPatch::Render` adds the
two tile textures (`D3DTOP_ADD`) when a tile has a second layer, and the partial
tiles are black where they contribute nothing. Moradon has 2,232 distinct
`(tex1, dir1, tex2, dir2)` combinations but only 308 distinct textures, so
blending at draw time costs one atlas rather than an unaffordable one.

Selected: the cooked heightfield gains `"alternating-mirrored"`, and the KO bake
uses it. `CN3Terrain::GetHeight` (`FUN_0059d330`) and `CN3TerrainPatch::Tick`
(`FUN_005a0410`) both split quad `(x, z)` on `(x + z) & 0x80000001` over the
reference grid. The bake mirrors z, and mirroring one axis inverts that parity as
well as the winding, so the previously shipped `"alternating"` phase split every
quad along the wrong diagonal. Visuals and collision agreed with each other but
not with the reference surface. The corrected phase is checked against a direct
transcription of `GetHeight`, not against a restatement of our own rule.

Consequence: a map package keeps its full gameplay sections and its real KO
player presentation; only `npc`/`animation` are dropped, because NPC clips must
share the instanced scene's atlas. Release identity changes, so existing Moradon
realms are replaced rather than migrated — they are disposable test realms. The
atlas budget (324 slots of 104²) is the current ceiling on how many distinct
textures one map may reference; a larger map needs a packer or a second atlas,
recorded as a limit rather than raised speculatively. Affected:
KX spec, [contracts](CONTRACTS.md),
evidence.


## D-045 — 2026-09-20: double-sided parts and in-cell texture repeat

Status: implemented on `phase/ko-exploration`. Question: why did imported object
meshes still look like they were missing triangles once the map was drawn?

Two independent causes, both found by measuring the real data rather than by
eye.

**Double-sided materials were discarded.** The OPD shape reader skipped each
part's 92-byte `__Material` block wholesale. `CN3SPart::Render` (`FUN_00443090`)
tests that material's `nRenderFlags` and, for `RF_DOUBLESIDED` (bit 2), issues
`SetRenderState(D3DRS_CULLMODE, D3DCULL_NONE)` before drawing and restores it
after — binary-confirmed at `004432aa`/`004433ea`, with the material's location
fixed by `CN3SPart::Load` (`FUN_00443440`) reading `0x5c` bytes into part offset
`0x7c` and the flags then being tested at `0xcc` = `0x7c + 0x50`. **1,293 of
2,688 Moradon static parts are double-sided.** Their back faces were culled and
simply missing.

Selected: decode the material and emit both faces for such a part. The world
pass has one cull state, and flipping it mid-pass would mean splitting the asset
into draw ranges for a property that is already known at cook time. Normals are
left alone, which is what the reference does too: it drops culling without
flipping them, so a back face is lit identically either way. Cost is 13,246
extra triangles on Moradon, 11% of the map.

**Texture repeat was destroyed by baking UVs.** Atlas UVs were baked per vertex
as `origin + (uv % 1) * size`. That silently breaks two things: a surface meant
to tile (a brick wall, a fence, a castle post) shows one stretched sample
instead of its courses, and any triangle whose corners straddle a tile boundary
has them wrapped to opposite ends of the image, so it samples backwards across
the whole texture. On Moradon that is **20.2% of placed object triangles** —
which, on a mostly transparent foliage or trim texture, reads as a missing
triangle.

Selected: keep the authored UVs and repeat inside the atlas cell at draw time. A
vertex carries cell-local UVs plus the slot each layer samples; the atlas
becomes a declared grid (cell stride and padding are part of the asset); each
cell's border holds the **wrapped** opposite edge rather than a clamped copy, so
filtering across a seam is what `GL_REPEAT` would give; and sampling uses
`textureGrad` with gradients from the unwrapped UV, because `fract` alone
collapses the mip level to a stripe along every seam.

Rejected: rebasing UVs per triangle and unsharing the vertices that need it. It
fixes tearing but not tiling — a wall still gets one stretched brick — and on
Moradon it would have pushed the vertex count past the asset's own cap for a
strictly worse result.

Consequence: `N3W1` vertices are 12 floats, the header declares the atlas grid,
and the asset's bounds now include a UV repeat limit and integral in-range
slots. Atlas cells bleed into each other at the coarsest mip levels, since the
wrapped border is only `pad` texels wide; that is recorded as a limit. The
reference's `RF_ALPHABLENDING` sorting is still approximated by an alpha test,
and `RF_BOARD_Y` parts stay frozen because a static asset cannot billboard.
Affected: [contracts](CONTRACTS.md#engine-12-static-world-asset),
[world asset](../../content/world.md), KX spec,
evidence.


## D-046 — 2026-09-20: progressive meshes are stored at minimum detail

Status: implemented on `phase/ko-exploration`. Question: why did imported rocks
and trees keep losing individual triangles after the draw path, the
double-sided materials and the texture repeat were all fixed?

Because the mesh reader had been wrong since KX-02, and the wrongness was
disguised by a check that could not detect it. `ko.py` read a `.n3pmesh`'s
vertex and index arrays and skipped the edge-collapse records, on the stated
assumption that "the base vertices and indices are stored first at **maximum**
detail, with the collapse data appended". The evidence offered for that was
that the file parses to exact EOF with a 24-byte `__EdgeCollapse`. That proves
the **stride**. It says nothing about what the index values mean.

They mean the opposite. `N3PMesh.h` states it in a comment — "The mesh is saved
in its lowest level of detail" — and the binary confirms the mechanism.
`CN3PMeshInstance::Create` (`FUN_00441820`) copies the stored index array and
then sets the instance to `m_iMinNumVertices` / `m_iMinNumIndices`;
`SplitOne` (`FUN_00441b20`) walks the collapse list forwards, adding
`NumIndicesToLose` and `NumVerticesToLose` and **rewriting index values** to
`m_iNumVertices - 1` at each position the change table names, then advancing by
`0x18`. The stored array therefore holds the maximum *count* of indices wired
to the *collapsed* vertices. Rendering it as-is gives the right number of
triangles pointing at the wrong vertices: shards, holes and spikes. Isolating a
single "stone" mesh and rendering it from eight angles made that obvious in one
image, which no aggregate statistic had.

Selected: replay every split in order at import, exactly as `SplitOne` does,
and assert that the result lands on **both** declared maxima. That assertion is
the check the old one should have been — a wrong stride or field order cannot
hit two independent totals — and all 3,379 local `.n3pmesh` files satisfy it.
On Moradon, triangles whose winding disagrees with their own vertex normals
fall from 4,093 to 185, and to zero inside double-sided parts.

Consequence: the KX-02 "level of detail" finding is corrected rather than
amended; its stride measurement stands and its semantic conclusion does not.
The earlier double-sided and texture-repeat fixes (D-045) remain correct and
independent — they were simply not the whole story. Runtime LOD selection stays
out of scope: the bake picks one level and nothing reconstructs a reduced mesh.
This is a standing reminder that "parses to exact EOF" validates sizes only;
geometry needs to be looked at. Affected: KX spec,
evidence.

## D-047 — 2026-09-21 preview fog, object LOD and authorized turbo

The user requested fixes to the accepted Moradon preview audit. Selected:
independent repeating texture-array mip chains; engine 13 exploration policy
and object LOD sidecar; wire 7 server-authorized hold-Q turbo, retaining the
existing normal movement bounds. See [contracts](CONTRACTS.md#engine-13-exploration-and-wire-7)
and verification/evidence.

Binary camera Apply `004395c0` uses linear range vertex fog, with start equal
to far times the **0.1** constant at `006a3d1c`; it disagrees with the source
checkout's EXP2 fog. Use that confirmed mode and ratio, with explicit preview
far distance/colour rather than asserting unknown historical Moradon values.
Object LOD is sampled from binary-confirmed PMesh controls, with conservative
sphere culling. Terrain simplification and continuous vertex budgets remain
fidelity gaps; D-046's maximum-detail-only scope is superseded for this task.

Turbo uses the binary-confirmed 10x multiplier but generic authenticated
`movement.turbo` permission and collision enforcement. A bounded lease alone
would allow revoked authority briefly after a successful operator response, so
revocation success also requires a durable simulation-observation barrier.
The local launcher grants the preview character explicitly; a normal client
and tools client receive exactly the same authority. Larger KX acceptance
and research gates are not declared complete by these focused fixes.

## D-048 — 2026-09-22: HUD controls preserve visibility and button state

The user requested correction of the HUD audit.
Use independently versioned `N3H2` presentation data with a bounded acyclic
control table and per-record ownership/state masks. Both images and labels share
selection, and hidden ancestors suppress drawing and hit testing. Retain `N3H1`
compatibility. Engine/wire versions do not change: HUD bytes remain a hashed
opaque server presentation dependency; old clients fail closed on new HUD magic.
Exact format.

Binary `00548980` hides Stand; `005d6260` selects Walk/Run inversely. The missing
party gate is now confirmed: `00549730` selects Invite for a nonleader outside a
party, otherwise uses membership/leader/target state, with Disband inverse.
`00403bc0` selects normal/down/hover/disabled images with null checks; no invented
normal-image fallback is used. `005429b0` selects chat checkboxes by default.
The converter retains standing, ungrouped, non-Knights defaults until those
systems exist. These are explicit support gaps, not permanent fidelity exceptions.
Unsupported buttons retain unavailable feedback rather than inventing a KO
rule disabling them. Generic disabled-state drawing/input is supported and tested.
No party, sitting, guild or chat-filter gameplay is introduced.

Walk/Run buttons select the existing local input mode; server movement validation
is unchanged. Other control capture is local presentation, cancelled on release,
focus/input capture, identity loss or a mode change. Original fixtures and actual
HUD replay verify selection. Evidence.

## D-049 — 2026-09-22: terrain sampling and empty hotbar corrections

User testing authorized correction of seams and hotbar artifacts. `N3L2` extends
hashed world presentation flags with independent mirrored sampling and radial
sphere culling; retain `N3L1` reading. The KO cooker selects mirror on terrain
(binary `0059cd90`, both stages) and radial culling on objects (`004429b0`).
Object repeat, authored indices and collision remain unchanged. Continuous LOD,
terrain simplification and recovered fog environment values remain open support
gates; the corrections do not establish full historical settings parity.

Remove the demo attack assignment from the empty hotbar. The known local UIF's
page-button rectangles disagree with its background artwork: move each complete
button subtree and hit region by (+1,-3) pixels, gated by the exact UIF SHA-256.
This is a documented local-asset repair of visibly duplicated glyphs, **not** a
claim that the binary applies that offset. Binary button Load `00403fc0` preserves
the authored positions. All four states and both controls remain available;
real saved assignments/paging are still unsupported. Reference assets are not
modified. Evidence.

## D-050 — 2026-09-22: point-filter HUD artwork

The user authorized correction of the HUD seam audit.
HUD artwork now uses NEAREST min/mag without mipmaps, matching binary UI state
setup `00578db0` (POINT/POINT/NONE); image Render `00409070` retains that state.
The designated substitute font texture keeps linear filtering. No layout offsets,
UV insets, overlapping geometry, content format or authority changes are needed.
The original D3D half-pixel adjustment (`00408c20`) is not copied into OpenGL.
GPU verification covers bleed-sensitive synthetic pixels and the actual
Character/Skill controls at three scales/five states with matched filter A/B.
Evidence. Native pixel-art edges become sharper;
full historical HUD/font/scaling fidelity is not implied.

## D-051 — 2026-09-22: measured integer HUD text layout; no invented arrow mask

User requested correction according to binary behavior and investigation of
masking. `N3H3` retains single-line/vertical alignment, measured fixed-cell font
advance/height/padding, integer layout before viewport scaling, and single-line
overflow truncation. Binary `0040def0` measures via `0042bcd0` (GDI text extent)
and uses integer positions. Keep H1/H2 compatibility. Our font remains an explicit
monospaced substitute; do not claim matching Windows Arial metrics, exact glyphs,
or eliminate authored state offsets by silently sharing normal-state rectangles.

The traced UI setup/base/button/image/hotbar paths show texture-alpha blending,
not a separate normal-image mask. The opaque hover top row lies inside the same
image quad. Source-only cooldown scissoring is a different path, not evidence of
a page-button mask in the supplied D3D8 binary. No new mask, crop or hover offset
is introduced. Previous local-asset arrow registration remains documented D-049,
not a binary-derived positioning rule. Evidence.

## D-052 — 2026-09-22: independent player animation metadata

The requested Moradon stopping correction retains source player clip metadata
without fabricating NPC presentation. N3A2 stores seven player records using the
existing N3A1 record encoding; eleven-record N3A1 remains supported. This enables
existing entry blending and smooth position settling. The binary setter
`0041be40` and retained KO-07 controller evidence ground blending; this is a
package capability correction, not a new animation algorithm or movement rule.
Evidence and window-size comparison.

## D-053 — 2026-09-22: fixed Moradon viewport presets

Use binary startup `0064b9b0` modes in the Moradon launcher: fixed 1024x768 by
default, 1280x1024/1600x1200 via N3E_WINDOW_SIZE. Generic engine --fixed-window
support enforces bounded dimensions through SDL sizing constraints. Correct
HUD reference width to 1024; retain authored rectangles. Fullscreen and complete
historical panel scaling remain outside this correction. Known fractional chat
gap at 1280x1024 remains open. Evidence.

## D-054 — 2026-09-22: height-anchored movement support under gate roofs

Both Moradon castle bridges stopped where an overhead gate roof entered the
ground query. The highest surface at any height is unsuitable for a moving
character's support: it selected ~20.1m instead of ~8.7m. Ghidra `005b8850`,
located through the 5000.0 ray-origin constant, confirms a nearest-hit comparison
against a position reference, distinct from the maximum-height `005b8d10`.

Select the highest surface reachable within the existing package step limit,
retaining higher surfaces for body-height clearance rejection. Apply identically
to client prediction and authoritative server movement. Keep existing step/drop,
slope, wall, speed, substep and query limits. This corrects layer selection within
the existing solver; synthetic dimensions and exact legacy nearest/bias/slope
semantics remain fidelity gaps, not newly asserted historical calibration.
Unanchored spawn/ground helpers retain their previous semantics. No asset repair,
permission bypass, wire/data migration or collision recook is needed.
Evidence; user testing remains pending.

## D-055 — 2026-09-22: use the step limit for low-riser clearance

User testing confirmed both bridges work after D-054 and isolated the remaining
defect to the two interior stair landings. Both have ~10cm lips; the support solver
allows 25cm steps, while its wall check used a separate 5cm margin. A character's
body radius therefore hit the riser before its centre reached upper support.

Use package `step_height` instead of 0.05m for the vertical-triangle lower
clearance. Keep the support step/drop bound, full-height walls, ceilings, substeps
and server authority unchanged. `00468ad0` raised-ray binary evidence was
rechecked in assembly (`0046996d`, `00469975`, `004699ad`); this establishes
separate foot clearance, not n3e's synthetic 25cm calibration. Exact KO raised-ray
and frame-dependent climb semantics remain a fidelity gap under D-024.

Add closed risers (the old step fixtures had only horizontal treads), over-limit
and reduced-policy rejection, both real stair round trips and complete bridge
approaches. Evidence. Awaiting user testing, no merge.

## D-056 — 2026-09-22: progressive object and three-level terrain LOD

The user requested correction of all findings in the bounded world LOD audit.
Replace sampled object ranges with bounded progressive programs in N3L3,
evaluating authored budgets at runtime with binary signed-delta truncation,
stateful collapse/refinement, grouped splits and endpoint behavior. Preserve
transformed local-box centers, mesh radii, signed maximum parent scale and both
parent visibility gates. The binary parent position gate uses radius times
maximum scale times **3**, unlike the source's 2 (`00443f40`, `006a3bf0`).

Implement the binary's three terrain patch levels and neighbor-dependent fan
edges, with the supplied TCT color maps at coarse levels. Cook all 32 coarse
edge variants into immutable ranges. Package data supplies patch layout,
distance bias, near/middle bands and far-plane factor. Character selection's
forced near-band radius 10 is outside gameplay: the compared global is assigned
constructor `005f91b0` in `006453b0`; its initializer `005f98c0` loads ChrSelect
assets. Ordinary world rendering uses `0059b6f0`'s far-plane rule.

N3L3 retains engine 13/wire 7; previous LOD formats remain readable. Validate
progressive programs once during asset loading and bound their total work.
Rendering changes only presentation; collision and movement remain full-detail
and authoritative. No binary bug/exploit exception is asserted. Shader/material,
character LOD and historical camera/environment gaps remain separately scoped.
Verification and user-test commands.

## D-057 — 2026-09-22: native texture and character detail, shared projection

The user requested fixes for the follow-up LOD audit and texture/camera checks,
then deferred direct original-client performance comparison in favor of FPS.
Add optional hashed N3D1 at engine14/wire7: four skinned levels, binary-grounded
package thresholds/workload rows, independently reversible attachment programs,
native authored texture chains and a shared camera projection. Existing packages
retain their defaults. Terrain normals now use binary parity averaging and
upright borders, including the odd-parity repeated-height arithmetic; source's
commented algorithm is not authoritative. Full-detail diagnostics restore state.

Use the supplied executable's 65°/.5m projection and local Moradon's 256m
clear-weather far plane; the source's 70° is not the target. Default texture
profile skips one character mip and zero shape/terrain mips. GPU banks preserve
authored sizes/levels, with bounded counts/bytes; no runtime resampling.
FPS is an n3e presentation-rate indicator, not a performance-parity claim.
Equipment import, mixed NPC crowds, exact historical controls and full rendering
fidelity remain open; they are support gaps, not accepted permanent exceptions.
Evidence and test instructions.

## D-058 — 2026-09-22: categorical texture IDs must not interpolate

User testing found a see-through face and similar map artifacts after D-057.
The face's authored mip alpha is opaque; its GPU ID 2048 lies at a bank boundary.
A synthetic GPU test reproduces perspective interpolation rounding this ID into
the transparent previous bank. Use flat varyings for per-triangle texture IDs in
both shader stages; retain interpolated UVs and authored alpha. This fixes n3e's
own logic bug, with no historical behavior deviation or package change.
Retain the failing-before/passing-after production-shader regression in the
normal/tools Wayland/XWayland graphics suite. Evidence.

## D-059 — 2026-09-22: continuous KO completion and local database reference

The user requests a branch from main and continuous implementation of the missing
KO features, with user testing once at final integration. This request supersedes
separate feature kickoffs and intermediate user-test/merge gates for the active
`phase/ko-feature-completion` branch. It does not authorize merging main or live
server deployment. Automated tests and honest incomplete checkpoints remain
required. Scope and task ledger.

The supplied `ref/ko-db/OpenKO-v0.1.2.bak` is inspected in a disposable isolated
SQL Server container, read-only after restore. It is supporting local-reference
data, not evidence that all executables, source and tables form a matching release.
Game-definition exports remain ignored and engine builds do not require SQL Server
or this backup. Original fixture packages remain the verification baseline.

Private messages use a distinct additive envelope (31), not optional routing
fields on the existing local-chat request. Older servers reject an unfamiliar
body instead of broadcasting the text. Server identity and recipient routing
are authenticated, realm-local and bounded. Supplied Ebenezer `004989a8` sends
private messages only to the destination; current source's sender echo is not
copied. Existing local chat byte/rate limits and character naming are retained
and remain explicit historical fidelity gaps. No party/guild/shout/moderation
completion is implied by this first implementation.

## D-060 — Versioned item records and durable whole-slot moves

2026-09-22, KFC-04. Supplied Ebenezer `004a1aa4`, direction 3, swaps complete
inventory records rather than merging stacks. Introduce opt-in N3I1 under engine
15/wire8, positive durable instance identities and revision-checked moves. Keep
package definitions/currency/capacity out of engine rules. Migration008 persists
bags and append-only canonical request/results with the existing owner/session
fences. An exact retry returns its original snapshot; clients reject state rollback
by revision. Loot count, instance and claim result share a transaction. Reserve
capacity for legacy aggregate rewards; do not rewrite their immutable history.
Definition hash changes require explicit migrations. This is an incremental
foundation, not closure of equipment, shops, stacking or full currency accounting.
[Contract](../../content/inventory.md), evidence.

## D-061 — Merchant prices and simulation-authorized durable exchange

2026-09-22, KFC-04. N3O1 under engine16/wire9 supplies bounded package prices,
weights and merchant positions/offer lists. Extend the bag transaction rather than
introduce a second currency owner. Simulation snapshots establish interaction
position/life; new transactions require a fresh capture and persisted life/session/
realm fences. Exact original retries remain readable after leaving the shop.
Reference `004a5b8e` establishes buy/sell quantity, stack, balance and weight paths;
remote selling varies with a binary regional branch, so it is package policy.
Sale rounding occurs after multiplication. Dynamic tax/premium/rental rules remain
open. [Contract](../../content/commerce.md), evidence.

## D-062 — Binary-grounded, package-defined repair curve

2026-09-22, KFC-04. Supplied server `004afd8d` uses power0.82, not current source's
0.75. N3J1 engine17/wire10 preserves the exponent as f64 and linear/multiplier
parameters as f32. Truncate before applying the final multiplier, then truncate
again. Extend the existing durable bag ledger with operation4; a selected actor
repairs an owned bag instance without adding a merchant/HP requirement absent in
the inspected leaf and `00490919` receiver. The same transaction deducts money and
restores durability. Current multipliers are package constants; premium eligibility,
equipment-derived stat refresh and combat wear remain open. [Contract](../../content/repair.md).

## D-063 — Equipment records and verified requirement fields

2026-09-22, KFC-04, incomplete. N3Q1 engine18/wire11 adds named equipment slots,
package-owned exclusions and base-attribute/race/title requirements. Reuse the
bag revision/transaction/result ledger; migration009 fences older decoders that
would discard the new durable protobuf field. Composite definition identity
prevents silent equipment-policy changes. The initial archetype remains shared
package data until character creation and stat allocation are implemented.

The first draft mislabeled item+5b as level. Before publication, database exchange
`0044729b` and table population `0041f077` proved it is ReqTitle; the implementation
and tests were corrected. `004ad9d9` does not read loaded level/max/rank/class fields.
Do not infer their server enforcement from source or table names. Empty-slot
unequip and single-item displacement follow `004a1aa4`; preserve full records.
[Contract](../../content/equipment.md). Combat stats, wear and meshes remain open.

The same unreleased wire11 capability adds operation8 for equipped-item repair,
reusing binary004afd8d selector1 and the existing exact curve/transaction ledger.
No item movement or new durable field is required; stat refresh remains open.

## D-064 — Authoritative equipment-derived ordinary stats

2026-09-22, KFC-04, incomplete. N3Y1 engine19/wire12 pairs with explicit N3P1
`equipment_v1` mode. Keep formula constants/category assignments in package data,
retain a shared archetype until character allocation is implemented, and use
committed gear for combat, maxima and purchase weight. Queue committed gear before
later actions; immutable old replies cannot roll the simulation back. Recalculate
on gear/level changes, clamp current vitals without granting a heal, and reload
gear before world admission. The composite bag hash includes the stat policy.

Binary coefficient exchange0040d211 and population00420b44 establish table-to-runtime
field mapping; ordinary aggregation0049e11c and ability004a0d2a establish consumers.
MP00499595 uses f32 0.2 and stamina resource f32 0.1; HP00499422 uses f64 0.1.
The preliminary resource-formula notes were corrected against the instructions
and exact constant bytes before implementing reference fixture values. Masteries,
buffs, transforms, special zones, signed bonuses and resistance/effect branches
remain support gaps. [Contract](../../content/stats.md).

## D-065 — Durable ordinary wear follows the struck item instance

2026-09-22, KFC-04, incomplete catalog checkpoint. N3U1 engine20/wire13 and migration010 add
internal frozen wear events, durable original outcomes and deferred combat
publication. No network operation can submit a wear event. Reserve the affected
exchange until the database worker completes, without waiting inside a tick.

The first transaction draft rejected an event when the bag revision changed.
Concurrency review found this could let inventory traffic cancel a pending hit.
Corrected before publication: wear follows the struck instance across the current
bag/equipment record, preserving the accepted hit and leaving replacement gear
untouched. Repairs already committed affect current durability; removed/consumed
records are gone. Future storage/transfer must extend instance routing. All current
client-requested bag operations retain their own revision CAS and immutable retries.
[Contract and remaining binary branches](../../content/wear.md).

## D-066 — Account storage with atomic transfers and continued combat

2026-09-22, KFC-04, incomplete catalog checkpoint. N3B1 engine21/wire14 and schema011 add
account/realm storage, derived from authenticated character ownership. Atomic bag,
warehouse, token-count and immutable-operation writes preserve serials and money.
Shared storage revision orders different characters; exact replies remain immutable.
Package services carry range/remote policy and opening fees. Existing realms require
explicit migration because the storage policy extends the composite bag identity.

Storage cannot deposit an already-struck record while wear is pending. Its deposit
admission validates the cached bag revision/serial; later equip/unequip changes the
transaction CAS. Combat continues while storage I/O runs. An initial draft paused
combat for all storage requests; review identified potential request-spam protection
from NPC attacks, so that draft was replaced before publication. The live audit
shows NPC damage and world updates during delayed storage commits. Logout/shutdown
drain both kinds of durable work. [Contract](../../content/storage.md).

## D-067 — Protected warehouse sessions without plaintext retry records

2026-09-22, KFC-04/KOF-0048, incomplete catalog checkpoint. N3K1 engine22/wire15 and
schema012 add package credential constraints, explicit one-time operator provisioning,
account/realm credential revisions, character/account/session grants and immutable
credential operation outcomes. Every storage read/transfer/retry checks the grant.
Rotation invalidates older grants. Historical result revision is separate from the
current authorization revision, so a retry cannot restore a superseded credential.

Password request payloads contain secrets and cannot use the ordinary raw-payload
operation ledger. They use independent salted scrypt request verifiers. Password
hashing runs outside SQL locks and ticks with the bounded account-login hash workers;
Redis account/IP limits bound attempts. Final transactions CAS the credential revision
and recheck current fences/life/range/deadline. Before/after-COMMIT crash tests cover
both credential changes and regrant on exact retry. Native prompts mask input and
collect confirmation without putting passwords in chat.

The supplied binaries expose passwords to diagnostics and omit the unlock flag from
transfer paths; correction traces justify fixing both.
The backup lacks the password column, so explicit provisioning is not a claim about
a historical default. Initial-creation and full keypad/regional fidelity stay open.
[Operator, data and retry contract](../../content/storage-auth.md).

D-067 follow-up: server comparator005007a0, shared by warehouse verify/change and
friend-name lookup, folds ASCII A..Z. The initial case-sensitive implementation at
e577e93 was incomplete. N3K1 now carries an explicit exact/ASCII-insensitive package
comparison mode and normalizes before credential hashing. Request verifiers retain
original bytes for exact operation identity. The original reference fixture selects
ASCII-insensitive behavior; the alternative package exercises exact comparison.

## D-068 — Directed durable friends and independent item capabilities

2026-09-22, KFC-07/KOF-0027, incomplete catalog checkpoint. Binary server004c59fa
requires an online/alive add target, permits offline removal, and has no target
consent/self/faction rejection. Schema013 stores owner-only directed links, stable
target IDs, revision CAS and immutable outcomes. Simulation captures bounded fresh
eligibility before database work; logout after admission does not undo that capture.
Live presence is a separate bounded tick query.

Engine23/wire16 N3F1 retains the durable world foundation while making the item
capability chain optional. Otherwise a social feature would require every package
to configure warehouse passwords. Producer and both readers validate dependencies,
and client/server behavior checks actual capabilities. Legacy engine1..22 file sets
are unchanged. Friend policy identity is independent of bags. Party presence and
finder remain open; the new panel is original presentation. [Contract](../../content/friends.md).

## D-069 — Session-scoped parties with server-enforced consent and leadership

2026-09-23, KFC-07/KOF-0004, incomplete catalog checkpoint. N3Z1 engine24/wire17
adds live party membership, session-bound invitation tokens, ordered physical slots,
leader replacement, disconnect cleanup, independent party vitals and friend presence.
Party state is ephemeral; reconnect/restart does not restore membership. The durable
reward system is not changed by this membership step. Party sharing is the next
settlement extension, with frozen inputs and atomic multi-recipient outcomes.

Client005c7df0/005c80b0 restrict invite/disband to the leader, while server004a9d1e/
004ab38d omit those checks. New authenticated server checks close that demonstrated
authority gap. Pending invites are separate from accepted members and are cleared
when a group ends or its leader changes. Historical special-zone/faction/guild
branches and class labels remain open; the current realm has one zone and no faction
or guild model. [Contract](../../content/party.md).


## D-070 — Versioned frozen party XP and preserved settlement history

2026-09-23, KFC-05/07, incomplete catalog checkpoint. N3P2 engine25/wire18 adds
`contribution_party_v2` with package bonus/qualification/level costs. Captured
N3S3 parties carry current membership, leader level and independently valid credit;
zero-damage eligible members receive their weighted, capped share in the same
transaction. Schema014 leaves old immutable history and migration checksums intact.
N3P1 remains unchanged; a prior durable definition cannot be silently replaced.

AI0042670d uses absolute NPC level,004438fa applies the per-level cap, and0043c413
loads PARTYEXP rather than a hardcoded source bonus. Startup precision trace confirms
53-bit arithmetic. The qualified-member count consistently determines the bonus,
correcting a demonstrated first-damage-entry branch discrepancy; independently
resolved identities correct stale contributor-pointer attribution. Both exceptions
are recorded before implementation in BINARY-POLICY.

Grouped loot, high-level progression, events/loyalty and a preserving upgrade path
for already-converted realms remain open. [Contract](../../content/party-rewards.md).


## D-071 — Explicit preserving reward-definition transitions

2026-09-23, KFC-05/10, incomplete catalog checkpoint. Schema015 records
complete immutable source/target definitions and a monotonic activation pointer,
leaving the original realm policy and earned outcome rows unchanged. The offline
`upgrade-progression OLD_PACKAGE` command requires exclusive realm ownership and
matching curve/inventory identity. It advances current character definition and
revision without rebasing earned XP, levels or conversion baselines.

A live restart exposed the existing whole-package world-revision gate. The
transition therefore also appends a destination-base world revision with unchanged
published values, and records both release hashes/snapshots. All other asset hashes
must match, apart from adding first-time party membership. Authorized historical
reverts may cross only this verified reward-only chain; old revisions and admin
results remain immutable.

Pending claims resolve the rules stored for their earned definition; an upgrade
may not invalidate them or silently change pickup range. Old final claim results
remain retryable. This is generic lifecycle support, with no client-facing
authority grant or live deployment. Initial conversion guards remain unchanged.
[Operator contract and verification gates](../../content/reward-upgrades.md).


## D-072 — Frozen loot audience and transactional party item routing

2026-09-23, KFC-04/05/07, incomplete catalog checkpoint. N3P3 engine26/wire19
retains first-contribution order in N3S4 for strict-greater party/solo ownership.
Schema016 saves the winning accepted audience independently of XP eligibility.
Current accepted physical slots determine the recipient at pickup; position/life/
session proofs are captured by the simulation and revalidated before committing.
The recipient item, count/revisions, claim outcome and party cursor commit together.
Logout waits for result application, including another member's live inventory.

Ebenezer004a7f1b removes a drop before capacity checks;004b48de uses the wrong
quantity for routing weight.004099b6/00473a82/004c6a4f establish private notices
with guessable bundle access. The preimplementation BINARY-POLICY record justifies
atomic consumption, actual quantity checks and saved audience authorization.

Old formats and immutable claims retain their semantics. Explicit reward upgrades
may activate N3P3 and cannot remove it. This step routes the existing singleton
reward item; coin arithmetic alone does not implement currency drops. General
bundles, premium entitlement predicates, special zones and original dialogs remain
open. [Contract and addresses](../../content/party-loot.md).

## D-073 — Frozen generated currency and atomic party wallets

2026-09-23, KFC-04/05/07, incomplete catalog checkpoint. N3P4 engine27/wire20
freezes the generated coin amount alongside contribution-order ownership in N3S5.
Schema017 permits multiple independently claimable entries per encounter while
retaining previous immutable payloads. Currency recipients are chosen from fresh
current-party server state; all wallet changes and recipient outcomes commit with
consumption in one transaction. Item rotation and capacity do not govern currency.

AI00423e5e's integer/event/party order and0040a9dd/0045b30e's random leaves are
confirmed. The exact32767 sender/receiver mismatch is corrected with the existing
32000 overflow fallback, as recorded before implementation. Shared combat/AI random
ordering, active premium predicates, live events and general bundles remain open.
A tested arithmetic coefficient does not grant an entitlement. Older earned drops
retain their definition through explicit upgrades. [Contract](../../content/coin-loot.md).

## D-074 — Moradon feature integration checkpoint

2026-09-23. The user requested an inventory, a commit of unfinished work, and
connection of implemented features to KO assets/HUD for a Moradon test. This
supersedes D-059's final-only user-testing boundary for this checkpoint. The
57-feature catalog remains incomplete; N3P5 direct/group drops are checkpointed
incomplete in `1c157ca` and disabled in the demo.

Original `games/moradon/features.json` composes the verified engine27/wire20
capabilities with local map, Tuarek, worm and HUD imports. Existing binary-grounded
rules and asset evidence are reused; item balance and service/NPC placement are
original demo data, not a historical population reconstruction. Collision walks
select reachable placements. The native feature panels use existing authoritative
APIs; full original dialogs and equipped meshes remain open.

Exploration packages' declared, grounded spawn now governs new characters and
respawn. Previously the server used its generic origin search despite the
package's surveyed spawn. Existing saved character positions remain durable.
An isolated persistent `n3e-moradon` Compose project uses port7780, a distinct
image/volume and a realm bound to the cooked hash. Explicit local provisioning
creates Explorer/Companion and insert-only warehouse credentials; only Explorer
receives the server-authorized turbo role. Tools builds confer no privileges.
Inventory, test guide.

## D-075 — Bind implemented features to original UIF dialog layouts

2026-09-23. The user requested wiring the Moradon capabilities into the UIF files
used by the client. Extend the existing UIF-to-HUD conversion rather than adding
legacy file paths or IDs to the engine. Original inventory, character, merchant,
warehouse, friends, party, Help and quantity-prompt artwork is imported locally. The
package owns bindings, placements and supplemental controls copied from an
original UIF button. Reference checkouts remain unchanged.

N3H4 adds bounded panel ownership and named value/meter/action bindings. Native
selection and confirmation feed the existing authoritative request builders.
Unimplemented original buttons remain disabled; no new gameplay rule is inferred
from their appearance. Existing H1–H3 packages retain their text-panel fallback.
The importer adds the binary-confirmed type14 list payload. Local UIF geometry,
binary loader behavior and original n3e interaction adapters are distinguished in
[the contract](../../content/dialogs.md) and the cumulative evidence.

The existing Moradon launch path now cooks this presentation. Its changed release
hash selects a separate test realm, preserving previous demo progress. Item icons,
inventory character preview, full drag/drop fidelity and deferred catalog systems
remain open. This follow-up stays on `phase/ko-feature-completion` for user testing.

## D-076 — Correct dialog window semantics from the client binary

2026-09-23. User testing exposed inferred placements and conflated Character,
Inventory and tab actions in D-075. The binary audit
separates window toggling, tab selection and panel-owned close actions. Character
retains its selected Stats/Friends page and never implicitly opens Inventory.
The importer uses viewport anchors and the binary's settled placements, including
party y40 where the supplied source instead says y0. Existing HUD scaling and
remaining slide/focus/dragging/catalog fidelity gaps are recorded explicitly.
No file-format, protocol or schema change is required.

D-076 shop clarification (2026-09-23): the follow-up audit
found that the imported `co_tradeinventory_us` is the centered trading window,
while the right-edge position belongs to the distinct NPC transaction window.
The prior demo pairing is an open mismatch. The NPC Shop needs its transaction
UIF; moving the borrowed trading artwork alone would not resolve its identity.
This follow-up records research only and does not change the running demo.


## D-077 — Use the NPC transaction UIF for the Moradon shop

2026-09-23. The user authorized fixing D-076's audited asset mismatch, followed
by a Moradon test. Replace the borrowed player trading UIF with
`Ka_Transaction_us.uif`, retaining the NPC object's confirmed right-edge,y10
placement. Bind24 stock and28 bag areas, stock arrows, close, gold and weight;
only the fixture's Store heading is drawn. Binary004c4bf0 confirms12 stock pages,
including empty ones;004c1600 resets the page on opening. The existing generic
selection/confirmation adapter now maps page-local stock slots to absolute
catalog indices and cancels stale/empty offer selection. Supplemental actions
remain below the taller root. No protocol, schema, server or reference changes.

Evidence and limits distinguish binary,
local asset and original n3e behavior. Existing icon/drag/drop/preview and broader
catalog gaps remain open. This correction awaits user testing on the same branch;
it does not implement player merchant trading or authorize merging.


## D-078 — Package-defined item icons in UIF slots

2026-09-23. The user accepted the shop correction and requested missing item
icons. Add N3H5's bounded item-ID/texture/UV table and dynamic image/count bindings.
Snapshots select artwork by the actual bag/equipment/storage/stock item ID;
updates and paging clear previous mappings. Missing artwork retains text fallback,
while empty slots draw neither an icon nor a label. All prior HUD versions remain
readable; old clients reject H5. The server only hashes this cosmetic payload.

The Moradon package explicitly maps its nine fixture items to supplied local KO
icons without importing their historical gameplay definitions. Binary006157b0
confirms extension-over-base icon selection and filename splitting;004c1430
confirms the45/64 UV crop. Evidence pins the claims,
assets and native tests. The existing alpha decoder/renderer handles the assets;
no external download or reference edit is introduced. Character preview, equipped
world meshes, drag/drop and wider catalog work remain open. This change stays on
the existing branch for user testing; no merge is authorized.


## D-079 — Inventory paperdoll and item drag/drop

2026-09-23. The user requested the inventory player preview and icon drag/drop,
with binary/source review. N3H6 adds package-defined portrait rectangles/camera
parameters, drawing the existing animated player mesh inside the imported
inventory's `area_char`. Binary0049e750 →004671d0 confirms the separate preview;
00465410 initializes20 degrees, unlike the source's18. The package follows the
binary angle after coordinate conversion. Mesh framing/lighting remain bounded
n3e approximations of the traced renderer, with explicit fidelity limits.

Left press captures an item; release resolves compatible slots and routes through
the same authoritative command path used by text and click controls. Binary
004a09f0/0049fee0,004c3270 and004aa320 ground inventory, NPC stock and warehouse
interaction. Simple operations send directly; multi-item stack transfers/sales
and stackable purchases use quantity entry. Invalid drops cancel without moving
or destroying an item. Capture pins revisions/identity/pages and is canceled on
input ownership/state changes. No optimistic durable state or new protocol is
introduced. The old click adapter remains available.

Evidence records remaining equipped-mesh,
rotation-control, historical special-item and other-window gaps. This user-directed
follow-up remains on the existing branch awaiting Moradon testing, with no merge
or claim of catalog completion.

## D-080 — 2026-09-23 Accepted appearance, tooltip and pickup work

The user accepted all three recommendations in the feature inventory. Implement
in that order on the existing branch, with binary evidence, package-owned data,
authoritative state and the listed verification gates. No merge is authorized.
Public equipment presentation must derive only from committed equipment; bags,
serials and balances remain private. The previous demo remains the verified
checkpoint until this batch passes. N3P5 must pass its open gates before activation.


D-080 implementation: engine29/wire22 adds only public equipped cosmetic keys;
N3D2 composes native body/part/plug geometry in world and portrait. N3H7 carries
original tooltip background/rows and the six-slot pickup panel. Binary004d5f70
checks a tooltip's right edge before adding26 pixels, allowing an offscreen edge;
the new rectangle clamps both axes (demonstrable layout bug correction). Historical
style/conditional rows outside implemented item policies remain gaps.

Moradon uses original blade/potion N3P5 rows and carrying scale2 after its previous
scale1 rejected a fresh blade reward despite free slots. This is synthetic demo
balance, not a claimed historical rule. The release-hash realm transition preserves
older demo characters; it does not migrate them into the new item definition.
Evidence and remaining fidelity limits.


## D-081 — 2026-09-23 Rest, attachment audit and item conveniences

The user accepted D-080 and requested C/HUD rest with animation/recovery, an audit
of weapon attachment rotation, right-click equipment and drag stack merging with
overflow. Continue the same branch; no merge is authorized. Engine30/wire23 adds
N3E1 package recovery and N3A3 complete posture clips. The supplied server's
ordinary seated recovery formula/timer governs the demo; its effect-gated standing
health path supersedes contradictory source. Premium/class/effect variants remain
gaps. Positive and missed incoming attack outcomes end rest as in client005cec10.

The rigid plug transform audit agrees with the existing conversion; retain authored
rotations and add independent regressions. Right-click shares existing equip/swap
transactions. Bag merge/overflow is an explicit user-requested extension over
Ebenezer004a1aa4's whole-record swap, not a historical fidelity claim or an inferred
exception to binary policy. Destination identity remains, source identity survives
only for overflow, and the freed source slot guarantees room even with a full bag.
Evidence and test handoff.


## D-082 — 2026-09-23 Accepted Moradon feature checkpoint merge

The user accepted D-081 with “Looks good! let's merge it” and explicitly authorized
merging `phase/ko-feature-completion` through tested commit `08a7496` into main.
Fetched origin/main remains `470d9db`, an ancestor, so no runtime reconciliation
is needed. The merge retains all phase commits and adds acceptance/status records plus a
test-helper correction: the standalone asset checker now visits all N3A3 rest
clips and uses the correct NPC metadata offset. Game runtime and package are unchanged. Remaining KO catalog and P5/P6 gates are not marked complete. No later
feature batch or external deployment is started. Merge evidence.

## D-083 — 2026-09-23 Weapon-dependent ready and attack clips

After the accepted D-082 merge, the user requested auditing weapon-dependent
attacks, then authorized the fix. Branch `phase/ko-weapon-animations` starts from
fetched main44ff71d. Client binary0045bf70 forces the equipment family through
0045bfe0(1), then chooses its first or second attack (staff has an exception).
This supersedes the fixed unarmed attack in the current demo.

Engine31/wire24 adds bounded package-owned N3A4 profiles and committed public
current/frozen-strike profile numbers. Cosmetic variants derive from public strike
identity so observers agree; combat RNG, damage, authority and persistence remain
unchanged. Moradon imports five families covering its usable gear. Source clip
IDs and KO class/weight logic stay in offline game data. Whole-body playback and
baked rates remain explicit fidelity gaps, not permanent exceptions.
[Contract](../../content/combat-animation.md), evidence.
Awaiting user testing after verification/publication; no merge is authorized.


## D-084 — 2026-09-23 Accepted weapon-animation merge

The user accepted tested commit `b463c58` with “Looks good! let's merge” and
explicitly authorized merging `phase/ko-weapon-animations` into main. Fetched
origin/main remains44ff71d, an ancestor, so no runtime reconciliation is needed.
The merge retains the tested implementation and adds acceptance/status records.
Focused animation/content checks pass; prior full, live server and normal/tools
verification remains applicable. Remaining layering, speed and catalog gaps stay
open. No later feature batch or external deployment is started.
Merge evidence.

## D-085 — 2026-09-23 Weapon timing, moving layers and ordinary consumables

The user accepted the next three recommendations after D-084. Branch
`phase/ko-combat-potions` starts from fetched origin/main1c9db1e. CP-01–05 adds
engine32/wire25 N3A5 equipment intervals and masked moving attack clips, then
engine33/wire26 N3X1 ordinary HP/MP recovery and migration019 durable cooldowns.
Package data owns all KO values, clip indices and joint masks.

Client004659b0 and00457d90 distinguish weapon delay from animation rate; do not
speed up clips merely to fill the attack interval. The server freezes the accepted
interval across queued wear. Client0046be20/0045dda0/00418e00 confirms moving
upper clips14/15, upper joints1–15 and base/root/lower sampling. Input005c6990 and
movement005d6430 distinguish initial W/S press cancellation from continued held
movement: re-enabling R while holding movement must preserve manual steering.

Potion005819e0/005845d0 establishes activation followed by shared recovery lockout;
00464b43/004b0792 and00466da0/004a035a/004a083f establish decrement and capped
vitals. Atomic cooldown-before-consumption corrects the specific legacy order
that can consume before a failed cooldown check. Existing ephemeral HP/MP is
explicit; only item, cooldown and operation result are durable. No general spells,
hotbar, FX or durable-vitals system is implied. Evidence,
[contract](../../content/consumables.md), spec.
Verification complete; awaiting user testing. Merge requires a subsequent explicit request.


## D-086 — 2026-09-23 Potion hotbar and timed icon presentation

The user requested implementation after the binary audit. Continue on
`phase/ko-combat-potions`; no merge authorization. N3H8 adds package-owned action
icons, overlay colour and completion frames to existing UIF layout. Eight pages
of eight shortcuts resolve supported consumables by item ID, independent of bag
slot or instance. Local preferences are character scoped; server operation9
retains all inventory, activation and cooldown authority. No wire/database change.

Preserve the executable's recast-only visual clock and three rendered completion
frames rather than invent a combined cast/recast animation. Server rejection
reconciles tentative presentation; a flash grants no permission to consume.
004de6f0 pins the completion textures;004df3c0 saves8x8 bindings;004dfa30/004dfa50
clamp page arrows;004dde20 activates on release, replaces a destination shortcut
or removes a shortcut dragged outside. The source-only modern fan is not imported.
[Contract](../../content/hotbar.md), audit.
Implementation and verification passed; awaiting user
testing. General spells/audio remain gaps.


## D-087 — 2026-09-23 Potion inventory behavior audit and correction

User testing prompted an audit of inventory cooldowns, right-click registration
and potion player effects on the same branch. Binary004a09f0 and004df6e0 confirm
first-empty/current-page registration on matching right release, including
duplicates and full-page no-op. This supersedes D-085's direct right-click use.
Keep use on the hotbar or explicit command, and update inventory tooltips.

Inventory0049e750 and shared icon004dd4f0/00409070 do not render a recast sweep;
retain the binary's hotbar-only presentation.00583f20 and00586690 confirm
casting/target FX dispatch; local assets identify the HP/MP bundles. World FX
remain a support gap, not an intentional deviation or an implemented feature.
No content/wire/storage change; this follow-up audits FX, it does not deliver
the missing general effect importer, renderer or observer events.
Evidence. Awaiting user testing; no merge.

## D-088 — 2026-09-23 Ordinary player and mob nameplate correction

User requested implementation after the binary audit on phase/ko-combat-potions.
N3H9 stores proportional regular/bold atlases, measured advances, model-height
profiles and placement constants in game content. The renderer retains case,
centers measured names above displayed actors, follows the animated sitting root,
draws black edging and includes the local player. HUD panels draw over names.
Binary00456830/00429700 establishes Arial12-point at96DPI (16px character height),
00459820/0046b5a0 establishes placement/self behavior. Existing0041c300 evidence
supplies frame-zero joint bounds. No copied legacy source or reference changes.

Arial is absent locally; Liberation Sans is an explicit hashed regular/bold
substitute, not a claim of Windows GDI raster/kerning equality. Foreground retains
neutral prior colors; faction/level colors and the exact display-toggle key are
open. Do not invent the key or expand this task into clan/emblem/balloon support.
Current model profiles are bounded to the demo's Tuarek and worm. Engine33/wire26,
server authority and storage are unchanged. Audit,
[contract](../../content/nameplates.md), verification.

D-088 verification passed; awaiting user testing on the existing branch.

User-testing preference (2026-09-23): increase the Moradon launcher default from
1024×768 to the next supported mode,1280×1024, including preview mode. This
supersedes the earlier default only; N3E_WINDOW_SIZE overrides remain supported.

## D-089 — 2026-09-23 Chat pixel alignment and ground loot container

The user reported the chat seam at the new1280×1024 default and requested the
original loot interaction. Binary00408c20 and the local atlas expose fractional
screen edges as the join cause. Floor final HUD rectangles consistently for
artwork/hits; retain point sampling and OpenGL's pixel-center convention.

Binary004564f0/00458580 identifies the static chest and1.5 scale;
005e16f0/005e3580/00471990/005c7c60 confirms both click paths. Add an optional hashed
static N3S1 presentation model; keep the path and scale in Moradon content. Render
one per authoritative eligible encounter, pick its visible geometry and open the
existing six-slot UIF at the cursor. Claims retain server authority and retries.
No lid animation is invented. Engine33/wire26 and database remain unchanged.

Binary open range is10m, differing from source's radius×2+6. Existing n3e3m
open/claim range, drop-center placement, visible-mesh picking and corpse lifecycle
remain explicit support gaps. They are not permanent intentional deviations.
Evidence, [contract](../../content/loot-visual.md).
CL-01–04 verified; awaiting user testing on the same branch, no merge authorized.

## D-090 — 2026-09-23 Pickup dismissal and combat potion correction

User testing requested four checks and clarified shield clipping occurs standing.
Binary005d6430→005794c0 and005c6990 establish pickup dismissal on movement/turning;
close it on admitted navigation, not snapshot correction. n3e's delayed potion
transaction incorrectly required the old whole-bag revision after combat wear.
Keep future-revision rejection but validate the locked source slot/instance and
usable item for stale requests; unchanged potion stacks remain usable during
combat. Cooldown, life/session, atomic decrement/result and exact retry stay
mandatory. No change to other inventory revision policies or durable schemas.

Independent legacy/raw geometry reproduces standing hand/shield intersection;
retain binary-grounded joint5/transform instead of inventing an offset. The
binary005c4e20 and local shape confirm green ground/upper target symbols; their
renderer is a missing capability, not delivered by this audit. Same branch,
engine33/wire26/release/realm. Evidence.
TF-01–04 verified; awaiting user testing, no merge authorized.


## D-091 — Shield eligibility and package-owned target symbol (2026-09-23)

User requested checking whether the shield excluded male Tuarek, then implementing
the target circle. Binary004a1750 accepts zero race/class requirements; local
Round Shield170250000 supplies both as zero. Item type60 is not a class restriction.
Synthetic demo race IDs are not KO IDs; retain existing rules and attachment.
D-090's raw geometry overlap remains unresolved, not a model-eligibility failure.

Import the two original static target quads/textures into optional N3TM cosmetic
presentation. Retain binary005c4e20 bounds/scales/terrain sample spacing and
004429b0 upright camera facing, with additive material factors grounded through
00443090/0043dd80. Keep paths, model bounds and scale constants in game data.
Use displayed positions and full-detail terrain, and preserve current authority.
Engine33/wire26 stay unchanged; the new content hash creates an isolated local
realm. Exact light/mip pixels, additional model profiles and player/object input
remain gaps. Evidence.

TM-01–04 verified; awaiting user testing on the existing branch, not merged.

## D-092 — 2026-09-24 Effects, audio and two starter Priest skills

User accepted the next three priorities after D-091. Add package-owned sampled
N3EF effects, N3AU audio and N3K1 direct skills on the existing branch. Engine34/
wire27 carries sequenced cosmetic events, cast state and recovered cooldowns.
Postgres migration20 owns positive skill recast deadlines; the existing combat
contribution/settlement path owns all spell kills. Retain durable inventory/lease/
session/life fences and bounded workers; rendering cannot grant results.

Binary player-magic AI0040d88e→0040e7c4 differs from the source and NPC spell
routine0042a642. Use the player formula and magic/charisma attribute supplied by
Ebenezer004630a6. Record that correction rather than promoting the first matching
NPC routine. Tiny Healing204001 and Light Strike204002 use verified local table
values and original clips/icons; all demo players use a fixed Priest archetype.
Full class selection/talent trees and other spell families remain separate.

The synthetic seven-meter demo leash immediately reset ranged spell targets.
Set the Moradon pursuit leash to30m, preserving the2.5m acquisition radius and
existing pursuit/return time limits. Extend the generic validated leash ceiling
from20m to64m to accommodate the25m skill range. This is demo integration data,
not a historical KO worm-range claim. Existing package values are unchanged.

Use actual UIF sound paths; empty local paths remain silent. Original Miles
provider attenuation, complete FX formats, exact impact points/mips, full talent
UI and transition easing remain explicit fidelity gaps. No unsupported historical
rule is inferred from modern source alone.
Evidence,
[skills](../../content/skills.md),
[presentation](../../content/presentation-events.md).

## D-093 — Chest lifetime and attack-start findings (2026-09-24)

The user requested an audit, not a new behavior implementation. Keep runtime and
the prepared D-092 release unchanged while recording two confirmed gaps.
Client corpse/container removal uses 20 seconds (`00470900`, float `006a4264`),
not the modern source's 90 seconds; opening advances a younger corpse to its
final 10 seconds (`005c7c60` → `00471d10`). Server empty-bundle removal
`00473b42` and client empty-panel closure `004d46a0` are confirmed separately.
Do not equate that visual timer with an unconfirmed server reward-expiry policy.
The current demo removes fully claimed chests correctly but retains unclaimed
ones according to its 600-second reward TTL.

Native tracing reproduces two 1.247/1.309-second delays after an early predicted-
range request is rejected. n3e waits its full weapon interval before retrying and
does not start the local pose until the authoritative strike snapshot. Binary
`004659b0` starts a local swing on eligible send; `005d6850` does not reset a
special arrival timer. Its ordinary last-send cooldown still applies, including
after a send later rejected by the server; do not claim otherwise.

Follow-up should address visual lifecycle and premature request/pose timing while
retaining legitimate weapon cooldowns, durable claims and authoritative damage.
Audit, limits and measurement. Awaiting review
on `phase/ko-combat-potions`; no implementation or merge in this audit.

## D-094 — Twenty-second loot expiry and confirmed melee range (2026-09-24)

The user accepted D-093 and requested a 20-second disappearance and correction of
the Z/R pause. Set Moradon's existing progression TTL from 600 to 20 seconds so
the visible chest and unclaimed rewards expire together under server authority.
The binary confirms the visual lifetime; its server reward-expiry timer remains
unconfirmed. This is a synthetic demo policy choice implementing the requested
disappearance, not a claim that both original timers have been matched. Keep
existing durable settlement/expiry/claim transactions and immutable retries.
No other package, wire version or database migration changes.

Before an attack send, require both predicted range/facing and the latest
authoritative actor-to-target range. Waiting for movement confirmation consumes
no weapon interval. Keep ordinary last-send pacing, server cooldowns and pending
request bounds; neither misses nor stop/start may bypass the legitimate interval.
This removes the reproduced premature-send pause without changing damage timing.
Local swing prediction and the binary's corpse fade/open-triggered aging remain
separate fidelity gaps. Verification.

## D-095 — Local swing prediction with authoritative reconciliation (2026-09-24)

User authorized selecting one of the recommended accuracy audits and correcting
it while retaining server authority. Select the ordinary combat sequence on the
existing branch. Fresh Ghidra client004659b0 sends then starts a local action;
005cec10's received-attack animation branch excludes the local actor.0045ad70
checks animation strike markers. Reuse00458110 authored audio markers. The
supplied Ebenezer00496169 independently checks ordinary attack admission.

Engine35/wire28 adds output-only Entity.strike_sequence30 and
PresentationEvent.request_sequence17. New skill-bearing packages select this
version; existing releases remain readable. The authenticated Action.seq is
copied only after successful ordinary attack completion (including durable wear)
and survives snapshot/event duplication. No input fields or storage schema change.
Use that identity for the existing cosmetic variant seed; no gameplay RNG change.

The local client may start a bounded swing and swing sound at eligible send, while
retaining D-094's confirmed-range admission and ordinary request cooldown. Server
hit/miss confirmation supplies all impacts and authoritative state. Match accepted
request IDs without restarting or replaying the swing; use the same cosmetic
variant remotely. Reject/timeout/cast/death/reconnect cancels pending cosmetics.
Late confirmed impacts display on receipt if their marker has passed. That is an
explicit reconciliation policy, not a claim of original network-latency pixels.
CS-01–04 verified; awaiting user testing, no merge authorized.
Evidence and remaining limits.


## D-096 — Accepted KO branch merge and Android spike deletion (2026-09-24)

The user accepted tested`8d38e2b` and explicitly requested merging all current KO
work into main. Merge all14 commits on`phase/ko-combat-potions` from fetched
main`1c9db1e`, preserving the tested runtime exactly and updating acceptance docs.
Focused merge checks pass; prior full/native/TLS/DB evidence remains applicable.
No new gameplay, reference revision, content release or production deployment.

The branch audit found only parked`spike/android-client` outside that history.
The user then explicitly requested deletion; local and origin branches at`5ba2d97`
were deleted without merging their11 unique commits. No other local/remote branch
has unmerged work, and there are no stashes or unrelated working changes. Leave
ignored build outputs untouched. The catalog remains incomplete; no later phase
starts automatically. Evidence.

## D-097 — Existing loot lifecycle and pickup correctness (2026-09-24)

User authorized cleanup/verification of existing features with no new gameplay.
Start `phase/ko-loot-lifecycle` from fetched main `1ed58f2`. Fresh binary tracing
separates client20-second lifetime/10-meter opening from server regional lookup,
stored creation timestamp and empty-bundle deletion. Server expiry timing remains
an open confirmation gate; retain the user's20-second Moradon reward policy and
record the current3-meter opening/claim mismatch explicitly.

Fix `LootUI::close` abandoning pending-claim status recovery. Window lifetime no
longer owns the in-flight operation; matching result resolves it, disconnect or
changed session/entity invalidates stale tracking. Server authority, durable
results, expiry policy, package identity and wire/storage formats are unchanged.
Real PostgreSQL races test two party claimants against expiry for each item/coin,
including admission before and processing after the database deadline. This is
reliability verification, not an assertion of original server TTL fidelity.
Scope, evidence.

## D-098 — Accepted loot lifecycle merge (2026-09-24)

User accepted tested `27d2996` and explicitly requested merging into main, then
recommendations for similar existing-feature checks. Merge the one-commit
`phase/ko-loot-lifecycle` branch from fetched main `1ed58f2`, without conflicts or
runtime changes beyond the tested tip. Normal/tools loot/HUD and54 Rust checks
pass; prior native/DB evidence remains valid. No new release, schema, deployment,
reference mutation or branch deletion. Retained branches are all included; no
stash or unrelated working changes. Recommend a bounded inventory-operation
completion audit next, with potion/skill completion races and remaining loot
presentation fidelity as alternatives. These are proposals, not started phases.
Merge evidence.

## D-099 — Existing item, skill completion and chest accuracy audits (2026-09-24)

User authorized all three D-098 recommendations. Branch from fetched main7ee146c;
no new gameplay family, durable-vitals capability or production deployment.

Replace response-counter item completion with exact request ID/family/send-relative
observation matching. Warehouse opening is tracked because it can charge a fee.
Retain panel-independent completion and session reset. Resend the identical envelope
at3s intervals at most three times; at12s without an outcome, release only the UI
wait, show an unknown-result notice and refresh the bag. Immutable server results,
revision/instance/authorization checks remain authoritative.

A real blocked-PostgreSQL regression proves that cancelled skill recast commits can
outlive the async receiver. Drain stage2 work asynchronously and recover the durable
cooldown into live snapshots, without applying the cancelled spell or spending MP.
Keep the already documented conservative cooldown-on-commit behavior; do not claim
historic DB fidelity or durable vitals. Verify existing potion completion fences.

Fresh client005c7c60 confirms strict10m opening. Add optional hashed N3LP radius
with model dependency, bounds and C++/Rust/producer parity. Moradon keeps3m server
pickup and the user's20-second durable TTL. Client00458ef0/004196a0 distinguish
corpse alpha from the separately rendered chest; no guessed chest fade is added.
00458580's rotated offset needs corpse orientation missing from durable drops;
exact placement/lifecycle and original server TTL remain gaps. Existing packages
retain prior opening behavior; old readers reject the new optional file.

EA-01–04 pass within scope, awaiting user testing. Engine35/wire28/schema unchanged;
new package hash selects a new local demo realm. No merge authorized.
Verification and remaining limits.

## D-100 — Accepted existing-feature audit merge (2026-09-24)

User accepted tested `787acc0` and explicitly requested merging
`phase/ko-existing-feature-audits`. Merge from freshly fetched main `7ee146c`
without conflicts; runtime, content and tests exactly match the tested tip.
Only acceptance documentation is added. Normal/tools HUD and loot checks plus
54 Rust unit tests pass (28 external-service tests ignored); prior database,
native X11, TLS and full-suite evidence remains applicable.

No new package, wire/schema change, production deployment or branch deletion.
All retained local/remote branches are included, with no stash or unrelated work.
Existing corpse placement/lifecycle, server TTL confirmation and ephemeral-vitals
limits remain recorded; no later phase starts automatically.
Merge evidence.


## D-101 — 2026-09-24 Binary gap survey checkpoint

User requested the stale catalog corrections and a deeper binary survey for
features missing from the documentation. Branch `phase/ko-catalog-refresh`.
Five read-only headless surveys (client, two Ebenezer, AI, Aujard) on separate
project copies resolved every previously unresolved dispatcher route and
corrected wrong mappings; the coordinating session re-read the surprising claims
from exported decompilation. Evidence.

DISPATCH routes without a matching record are marked "uncatalogued" with the
closest existing record rather than linked to unwritten IDs. Writing the
candidate records, expansions, anchor manifest and weakness-class entries is
deferred to a follow-up (CR-04). Weaknesses confirmed in the reference servers
are never n3e behavior and certify no other deviation. No runtime change.

## D-102 — 2026-09-24 Binary parity deep dive

User requested a deep dive on feature parity with the supplied binaries and
documentation of missing features and further investigation targets. Continued on
`phase/ko-catalog-refresh` as CR-04 (the open D-101 catalog write-up) plus CR-05.

Whole-program read-only decompilation of all four executables and seven domain
surveys produced 24 new records (KOF-0058–0081), dated expansions for existing
records, a parity matrix (PARITY), the event-script reference
(EVENT-SCRIPT), source/binary disagreements and legacy
weakness classes. Every dispatcher route now links a record. The KOF-0030 server
anchor `004323f2` was wrong (EVENT_TRIGGER loader) and is corrected to `004ad387`.
Evidence.

Gaps found inside shipped n3e features (key bindings, NPC regen/give-up timing,
dialog range, bag size, chat reach, name policy, sound range and others) are
**fidelity gaps under D-040**, not approved deviations; correcting any of them needs
a separate kickoff. Legacy weaknesses remain never-n3e behavior and certify nothing.
Priorities in the new records are research recommendations only. No runtime,
package, wire or schema change.

## D-103 — 2026-09-24 Parity follow-up investigations

User asked that all deep-dive findings be documented in `docs/` (reorganizing as
needed) and that the suggested investigations be kicked off. Findings previously held
only in ignored build reports now live in `docs/ko/domains/` (one page per area,
with the event-script reference moved beside them) and the KO README is an index.

The twelve ranked leads were run as eight bounded, static investigations
(`docs/ko/investigations/` A–H). About 35 earlier statements were corrected; new
disagreements and weakness classes are recorded in BINARY-POLICY. Loot-by-F is settled
as a fidelity gap (corpses open by click only). Research only: no runtime, package,
wire or schema change, and no correction is authorized by these findings.
Evidence.

## D-104 — 2026-09-24 Close parity gates from the local reference database

The user pointed out that inputs recorded as "not available locally" by investigations
C, D, F, G and H are in `ref/ko-db/OpenKO-v0.1.2.bak`. With approval, the isolated
reference tool gained a metadata listing of every procedure name and an allowlisted,
never-executed procedure-text export (`--procedure`), then exported Moradon-relevant
definition tables and 15 procedures. Investigation I
closes most gates as **local-asset** evidence: Moradon monster templates, warp-gate
event rows, the message catalogue, the login procedure and the rank producers. The
backup is OpenKO's database, not a binary-matched release, and lacks the official ban
procedures, so official ban expiry stays open. No runtime, package, wire or schema
change; adopting rows into packages needs its own kickoff.

## D-105 — 2026-09-25 Merge the KO catalog refresh

User requested merging the research branch first and chose, for the next phase: worm
fidelity only (one archetype made to match the KO Moradon Worm), a small committed
extract of the reference rows with provenance, and a fresh phase branch from main.
Merge `99cb4b2` is conflict-free and equals the reviewed tip `a561115`.

## D-106 — 2026-09-25 Moradon worm from reference rows

User requested using the local reference database rows in the game package, choosing
worm fidelity only, a committed extract and a fresh branch (D-105). Branch
`phase/ko-moradon-npc-data` from main `ccb0107`.

- `games/moradon/ko-reference.json` commits only the adopted Worm (K_MONSTER 750),
  its two zone-21 spawn rows and the zone-21 start position, with backup hash and
  binary references. Rows are local-asset; each adopted column's meaning was
  binary-confirmed in the AI loader chain before use.
- New optional, game-neutral npc model `reference_melee_v2` (N3N2), engine 36 / wire 29:
  passive acquisition, pursuit renewal on hits, return speed/heal/retaliation switches,
  periodic integer regeneration, and per-slot spawn areas with bounded standable
  placement and per-slot respawn. N3N1 packages are unchanged. Both readers and the
  cooker validate it; the server also checks slot/spawn alignment, corpse ≤ respawn
  and slot standability. `movement::standable` is the n3e analogue of KO's walkable cell.
- Moradon: passive 7 HP level-1 worms with 3 m/s chase, 2000 ms attacks, search 3 m,
  tracing 40 m as the home leash (adaptation), ten slots in the two KO rectangles
  (30 s / 20 s), and the player spawn surveyed inside the KO start rectangle. Damage,
  XP and drops stay synthetic; wander, faint, NPC magic, pathfinding, attack-range
  semantics and spawn facing remain gaps. Random spawn facing is not replicated.
- The KO start is the walled town square and worms are outside the walls, so every
  build proves engine-solver routes to both areas (original demo waypoints) and
  records them; headless and native live tests follow them. Tests also adapt to
  passive, 7 HP worms (unarmed hits to draw retaliation). The live armed-interval
  cooldown audit can no longer run on Moradon (a 7 HP worm does not survive an armed
  hit) and is reported as skipped; server admission tests keep that coverage.

## D-107 — 2026-09-25 Client skinning cost and frame pacing
User testing of D-106 reported about 70 fps in town and about 40 fps near the worms.
Profiling (`N3E_PROFILE=1`) found that `Scene::skin` appended the 41k-triangle collision
hull to every skinned mesh, costing about 0.85 ms per visible NPC. A leftover
unconditional 10 ms sleep after each swap also capped play below the display refresh.

- `skin` returns only the mesh and attachment markers. `animate` keeps the collision
  stand-in for the offline viewer and packages without a world mesh.
- Play is paced by vsync (a 1 ms yield if vsync is unavailable). Automated smoke and
  world-smoke modes keep the fixed 10 ms pacing their frame-numbered stages were
  tuned against.
- `N3E_PROFILE` stays as an env-gated diagnostic.

Measured: 144 fps (display refresh) in town and at the worms. No package, wire or
server change. Evidence.

## D-108 — 2026-09-25 Merge the Moradon reference worm and frame-rate fix

After testing, the user accepted the frame-rate fix and requested merging everything
so far, then working on the HUD scaling findings. Merge `2682eff` of
`phase/ko-moradon-npc-data` (D-106, D-107; tip `1716264`) is conflict-free: main had not
moved since the branch base `ccb0107`, and the merged tree equals the tested tip. Next
phase: package-declared pixel HUD scale (`phase/ko-hud-pixel-scale`).

## D-109 — 2026-09-25 KO HUD pixel scale

The user asked that the HUD follow the supplied client, which never scales UI with
the viewport and only re-anchors panels (binary `00401660`, `00401690`, `005d23d0`,
`00429700`).

- Add a generic, optional HUD revision `N3HA`: N3H9 plus a package-declared scale
  policy, `fit` (the prior uniform `min(W/1024, H/768)`) or `pixel` (authored size,
  anchors only). Layout, hit tests, glyphs, tooltips and loot clamps share one scale.
- The Moradon feature HUD declares `pixel`, which also removes the fractional chat
  seam at 1280x1024.
- The launcher default stays 1280x1024 by earlier user preference.
- No wire, server or engine-version change: `hud.bin` is self-describing, and the
  server only hashes it.

Supersedes D-053's remark that complete historical panel scaling is out of scope.
Evidence.

## D-110 — 2026-09-25 Merge the KO HUD pixel scale

After testing, the user accepted D-109 and requested the merge, then work on its
recorded gaps. Merge `82655db` of `phase/ko-hud-pixel-scale` (tip `2a3ea16`) is
conflict-free; the merged tree equals the tested tip. Next phase: HUD gaps
(`phase/ko-hud-gaps`).

## D-111 — 2026-09-25 KO HUD gaps

The user asked to address the gaps recorded after D-109. From the binary evidence in
investigation J:

- Every imported KO HUD declares pixel scale (`N3HB` for the basic layout).
- `--fullscreen` / `N3E_FULLSCREEN=1` selects an exact W×H display mode, scaling
  the whole frame.
- Panel defaults follow `005d23d0`: command bar H−57, chat and msgoutput H−198,
  hotkey (0,65).
- `N3HC` adds generic draggable panel groups:
  - no clamp during a drag, an optional side-edge snap, and keyed positions saved
    client-side on normal exit;
  - clamped restore, where (0,0) means the default;
  - Moradon: chat and msgoutput as one group, the hotkey with a 10 px snap, and
    party draggable but unsaved.
- `N3HD` adds a generic overview map: a zone texture, a player-centred window at
  a package zoom, a heading arrow and entity markers, hidden until toggled. Moradon
  uses Zones column 8 with KO's zoom, sizes and colours; M and the map button toggle
  it; the zoom buttons are inert, as in the binary.

Server, wire and engine versions are unchanged: `hud.bin` is self-describing and
only hashed by the server. Saved layouts are client-local, never server state.

Not applicable: character-select scaling, the rogue zoom, clan/hostile/GM minimap
rules and saved visibility flags. Evidence.

## D-112 — 2026-09-25 Merge the KO HUD gaps

After testing, the user accepted D-111 and requested the merge. Merge `d36ec6d` of
`phase/ko-hud-gaps` (tip `cb6de00`) is conflict-free; main had not moved since the
branch base `84c6b75`, and the merged tree equals the tested tip.

## D-113 — 2026-09-25 Drop the remaining phases and the phase-spec files

The user dropped the remaining numbered phases and asked to delete all phase files
after extracting important information and documenting every feature gap. The user
wants to discuss product goals and design next (Discord identity and commerce,
PostHog analytics).

- **Deleted:** `docs/implementation/phases/` (0–6 and the KO feature specs),
  `docs/implementation/ko-phases/`, `PHASE4-KICKOFF.md` and
  `KO-EXPLORATION-KICKOFF.md`.
- **New:** `docs/ROADMAP.md` (history of completed work plus the dropped Phase 5/6
  goals with their intent and targets) and `docs/GAPS.md` (the consolidated gap
  register).
- **Moved:**
  - the KX research record into `docs/ko/MAP-EXPLORATION.md`;
  - the I1–I17 dispositions into `docs/ko/IMPACT.md` (renamed from `PHASE4-IMPACT.md`);
  - durable rules into CONTRACTS (integrity before readiness, no broken
    intermediate formats, entity ordering, live-balance activation), BINARY-POLICY
    (static research only, completion rule), the FEATURES record schema, the
    evidence README and the root README (Compose volume safety, spike commands).
- **Repointed** every link to a deleted file, to its evidence record, the roadmap or
  the research record. Corrected stale statements that later work had closed.
- **AGENTS.md** (and `CLAUDE.md`, which links to it) no longer names phase specs or
  the phase order. The branch, commit, test and merge workflow is unchanged.
- The reusable-engine principle (game differences as package data) stays. The
  two-game single-build proof is a dropped goal, not a requirement.

## D-114 — 2026-09-25 Original-asset exploration (Ashgrave)

The user asked for an exploration branch that runs a version of the Moradon demo on
custom-built assets, loosely inspired by occult-noir comics with a low-poly KO feel.

- **Package:** Ashgrave is generated entirely by `tools/assetc/ashgrave.py` (stdlib
  only) and targets engine 13. That is the richest level reachable without an
  original N3D2 render-detail path.
- **Engine:** no engine format change. The only client addition is the env-gated
  `N3E_TEST_TOUR` capture hook.
- **Theme:** original, with no licensed names or likenesses.
- **Status:** exploration code on its own branch, not a committed content direction.
  Adopting it would need a real art pipeline and an original producer for the
  engine 29+ formats (GAPS).

Evidence.

## D-115 — 2026-09-25 Blender character pipeline and CC0 characters (exploration)

The user asked to install Blender and try the Blender route.

- **Tooling:** Blender is a pinned portable tool (5.2.2 LTS, checksum-verified) in
  the ignored tool cache. It is never a system install or a required build step for
  existing packages.
- **Pipeline:** character import is a generic two-step pipeline. Blender headless
  joins, re-skins and exports each clip; `character_import.py` reduces the exports
  to the `gltf.cook` subset. No package or format change.
- **Third-party sources:** CC0 only, fetched at pinned commits on opt-in, licence
  checked, provenance recorded, not committed.
- **Engine:** `Scene::skin` reuses each skinned vertex across indices (identical
  arithmetic). GPU skinning remains a gap.

Evidence.

## D-116 — 2026-09-25 MPFB2 character base and KO style metrics (exploration)

The user asked to try an MPFB2 base and compare against KO.

- **Tooling:** MPFB 2.0.17 and the CC0 MakeHuman system assets live in a
  project-local Blender profile, pinned and checksum-verified by
  `tools/install-mpfb.sh`. The GPL add-on is not redistributed.
- **Rigging:** characters keep the package rig. MPFB's hand-authored weights are
  mapped onto it, so existing clips apply.
- **KO comparison:** kept as a local measurement tool. Style targets are expressed
  as numbers: about 1–2k triangles and about 200+ texels per metre, with strong
  baked shading. Reference renders are never committed or used as generator input.

Evidence.

## D-117 — 2026-09-25 Merge the roadmap cleanup

The user reviewed and accepted D-113 and requested the merge. Merge `75a7ba7` of
`phase/roadmap-cleanup` (tip `ccf4505`) is conflict-free; main had not moved since
the branch base `6995899`, and the merged tree equals the reviewed tip.

- **Decision numbers:** D-114–D-116 are used on the unmerged, paused
  `phase/original-assets-spike` (original-asset, Blender, MPFB and Meshy
  exploration), so they are left free here.
- **Next item:** per DISCUSSIONS, Discord identity and account
  linking, scoped by a separate kickoff request.

## D-118 — 2026-09-25 KO installer as the player-supplied source

The user paused the Discord work. Asset generation for a novel game is not yet good
enough, so the user leans toward a KO community server, and asked to assume that
each player brings the original installer. Evidence:
ko-installer-provenance.

- **Source file:** `KnightOnLineSetup_1298.exe`, SHA-256
  `54d1c65853bb09b3512ff8778a78697177a02f6c5a0f9fd583751fbcfbc50fe4` (349,738,649
  bytes). It installs the US 1299-labelled client whose exe speaks protocol
  `0x512` (1298). Its game data equals the user's 1299 client folder, and equals
  `ko-client-assets` except for CRLF line endings, `Texts_us.tbl` and the CSV
  exports.
- **Distribution:** players supply the file. n3e never commits, hosts, bundles or
  links it, and never needs it to build. This extends the existing local-only
  conversion rule to players.
- **Research tool:** `tools/ko-reference/unpack_installer.py` unpacks it without
  running it, checks the stored MD5s and writes a SHA-256 manifest.
- **Reference identity:**
  - The analyzed client exe is very likely this installer's exe after unpacking
    (identical section layout). That is an inference.
  - The pinned server hashes belong to patched copies of the 2005 `.exe.base`
    files. The patches change deployment paths, ODBC setup and SQL text lengths.
    Two small control-flow edits (Ebenezer `0042171b`, Aujard `0041c708`) are open
    gates before any Ebenezer or Aujard behavior near them is treated as original.
- **Not decided:**
  - whether a community server is the final content direction;
  - the importer's shape: on first run or as a separate step, and with identical
    output everywhere or a split between rules and presentation.
  - Ares (`ares_setup_0903_2006.exe`) is noted as possibly the same engine, a
    different game. Unverified.

## D-119 — 2026-09-25 Merge the KO installer provenance

The user asked to document the related-games findings and merge. The survey was
added as `0eb4aa2`. Merge `7890c02` of `phase/ko-installer-provenance` (tip
`0eb4aa2`) is conflict-free; main had not moved since the branch base `1075082`,
and the merged tree equals the tip. D-118 stands. The next request is research into
the abandonware and asset-rights status of the related games.

## D-120 — 2026-09-25 Asset-rights research and the next-step proposal

- **Asset rights:** none of the related games offers usable assets. Knight Online,
  Legend of Ares and the Laqia revival are live. Kingdom Online is closed, but its
  rights holder (Noah System / NTTGame) is active. Hero Online's rights sit with
  MGame and Netgame.
- **Routes:** D-118 player-supplied files remain the model. A licence (the
  realistic targets being NTTGame for Kingdom Online and KO, and MGame for Ares or
  Hero) or original assets are the only ways to ship assets. Findings and sources
  are in DISCUSSIONS.
- **Next step:** the user will choose it in a new session. Claude's recommendation
  (the player-supplied import: repeatability check, direct installer reading with
  a `.tbl` decoder, then the player flow) is recorded as a proposal, not
  authorized work.

## D-121 — 2026-09-25 Merge the asset-rights notes

The user requested the merge. Merge `95739b6` of `phase/asset-rights-notes` (tip
`1ffff29`) is conflict-free; main had not moved since the branch base `ffc1425`,
and the merged tree equals the tip. No work is in progress. The user will start
the next work in a new session, and the proposal in DISCUSSIONS is not authorized
work.

## D-122 — 2026-09-26 Synty POLYGON assets in the spike (exploration)

The user asked for a survey of the Synty Store and a trial of its free POLYGON
Starter Pack.

- **Sources:** Synty source files are licensed per team (five seats) and must not
  be shared outside it.
  - They live only in the ignored `build/synty`.
  - They are extracted from the user's own download, pinned by sha256.
  - They are an opt-in variant (`ASHGRAVE_CHARACTERS=synty`), never a required
    build step, and are never committed.
- **Rigging:** as with MPFB (D-116), Synty weights are mapped onto the package rig,
  so the existing clips apply. The shared mapping is `measured_rig`.
- **Style:** POLYGON characters use flat palette swatches. The free Starter Pack
  body is an untextured mannequin, painted per region from the Synty palette for
  the trial.
- **Purchase:** if the style passes, POLYGON Dark Fantasy is the best fit for
  Ashgrave and Fantasy Kingdom for a Moradon-like town. Distribution terms (open
  source, extraction, the compiled-in editor) need checking before any public
  release.

Evidence.

## D-123 — 2026-09-26 PS1 assets from a player-supplied disc (exploration)

The user asked, for educational purposes, to load assets from their own Shadow
Tower PS1 image.

- **Rights:** proprietary game data follows the D-118 model: the user's own image,
  pinned by sha256, read locally. Nothing extracted is committed or distributed,
  and it is never a required build step (`ASHGRAVE_NPC=shadow-tower` is opt-in).
- **Split:** generic PS1 formats (raw disc/ISO 9660, TIM/VRAM, TOD) live in
  `tools/assetc/psx.py`; the `.T` archives and the creature block layout live in
  `tools/assetc/shadow_tower.py`. The engine is unchanged; output is the existing
  `gltf.cook` subset.
- **Evidence level:** the formats are inferred from the disc's data and checked
  by rendering, not against the game executable. The 30 fps rate and the Euler
  order are recorded as unconfirmed assumptions.

Evidence.

## D-124 — 2026-09-26 Havok wavelet animation decoder (exploration)

The user asked for a decoder for Demon's Souls' wavelet-compressed animation.

- **Method:** clean-room from game data only, validated by quaternion unit length
  and block continuity. HavokLib (GPL) and the freely distributed Havok PC XS
  header were read for container semantics. No Havok implementation, binaries or
  leaked source were used, and no code was copied.
- **Split:** generic Havok packfile and wavelet decoding live in
  `tools/assetc/havok.py`; Demon's Souls containers (DCX, BND3, FLVER0, TPF) and
  the glTF export live in `tools/assetc/demons_souls.py`. The engine is unchanged.
- **Rights:** the dump follows D-118/D-123: user-supplied, local, never committed.

Evidence.

## D-125 — 2026-09-26 A Demon's Souls level and player in the spike (exploration)

The user asked for a Demon's Souls level as the world and a Demon's Souls player.

- **World:** a crop of the level is cooked into the existing `N3W1` world and
  `N3C1` collision.
  - Visuals are simplified by budget-driven vertex clustering.
  - Collision uses the game's own Havok mesh shapes.
  - No engine or format change.
- **Player:** built from equipment parts on the player skeleton, with rigid
  attachments on named bones. Skin joints are limited to weighted bones to meet
  the 64-joint limit.
- **Rights:** local, from the user's dump, under D-118/D-123. Nothing extracted is
  committed.

Evidence.

## D-126 — 2026-09-26 Demon's Souls characters on the KO Moradon map (exploration)

The user asked for the Demon's Souls character and mobs on the KO Moradon map.

- **Separate package:** `moradon-des`, with its own launcher, Compose project and
  port. The Moradon release and its realm are untouched.
- **Replaced:** presentation only, through existing contracts:
  - NPC clips and the instanced scene;
  - player clips for every state;
  - render-detail character, appearances and skin joints;
  - the combat node mask.
- **Unchanged:** gameplay rules, reference NPC AI, the world and collision.
- **Rights:** the Demon's Souls data is local only (D-118/D-123).

Evidence.

## D-127 — 2026-09-26 Merge the original-asset spike; stay with KO assets

The user concluded the spike: "for now we'll stick with all the KO assets". They
asked to merge it and keep the asset logic built for the exploration.

- **Merge:** merge `4982fe4` brings `phase/original-assets-spike` into `main`.
  Only documentation conflicted, and both sides were kept.
- **Content direction:** KO assets, player-supplied (D-118). The original-asset,
  Synty, PS1 and Demon's Souls paths stay as opt-in exploration tools, not
  product content.
- **Kept tooling:** everything is opt-in, local-input and never a required build
  step; nothing proprietary is committed.
  - Ashgrave and its variants.
  - `psx.py` and `shadow_tower.py`.
  - `havok.py`, including the Havok 5.5 wavelet decoder.
  - `demons_souls.py`, `moradon_des.py` and their launchers.
- **Unchanged:** the Moradon and procedural Ashgrave releases are byte-identical
  before and after the merge.

Checks on the merged tree:
- `make client server`;
- `make test` (exit 0, 148 PASS);
- `ko_bake.py moradon_xmas --features` (release
  `d47d35ecd2619f9ddf3c582dbf3cecd7652b657eb55a82ec231a52287e8224d8`, unchanged);
- `ashgrave.py` (release `3f90c75cc06704fa2c1ce885fb478606ec6f0301b17ba3704fdfccc16ae7cc08`,
  unchanged).

## D-128 — 2026-09-30 Parity loop: standing authorization, auto-merge, reference rig

The user asked for a Claude Code `/loop` that drives closure on every feature gap
and towards full parity with the official KO binaries in look, feel and features,
keeping server authority and fixing known bugs. Three decisions were the user's:

- **Merging:** the loop merges to `main` itself once its automated gate passes.
  The user tests `main` afterwards. This replaces the stop-at-handoff rule inside
  the loop only.
- **Look and feel reference:** a time-boxed reference-rig spike that runs the
  original 1298 client and the reference servers in isolation, using
  a local `ko-1298` collection among its inputs. This is the "explicitly scoped action"
  BINARY-POLICY requires for any runtime reference setup.
- **Paid systems** (KOF-0041/0042/0049/0050/0057): mechanics only, with
  entitlements granted by an audited operator command. No payment path.

Design choices made to carry those out (LOOP,
evidence):

- **State in the repository.** An ordered queue (`docs/parity/queue.jsonl`), an
  inbox for the user, and a log. A self-paced loop does not survive its session,
  so no iteration depends on conversation history.
- **Fresh context per item.** The loop session only selects, gates and merges; a
  worker agent delivers the item and a separate reviewer agent re-checks the
  binary claims and the authority rules before anything merges unseen.
- **A mechanical gate.** `tools/parity/gate.py` runs the checks on the merged
  commit and writes a marker; the `tools/parity/guard.py` hook refuses a push to
  `main` without it, and refuses force pushes, remote deletion, `git add --force`
  and writes under `ref/`. The hook applies to every Claude Code session here,
  so ordinary merges now run the gate too.
- **Coverage is checked.** The queue check fails unless all 81 catalog records and
  every open gap row have an item.
- **Two closing levels.** `static` (binary reading plus checks) and `rig`
  (compared against the running reference). User acceptance is tracked apart.
- **Server authority is fixed.** The invariants in LOOP are never traded for
  fidelity; KO logic bugs are corrected only with a BINARY-POLICY correction
  record.
- **Not granted:** deployment, release publication, force pushes and branch
  deletion. Permission allow-rules are left to the user; the committed settings
  only add the guard hook.

The authorization takes effect when the user merges `phase/parity-loop`.

## D-129 — 2026-09-30 Reference rig spike result; answers to the parked questions

Before merging the parity-loop design, the user asked for the reference-rig spike
(PQ-002) to run first. Their answers to the four questions parked in the queue:

| Item | Answer | Disposition |
|---|---|---|
| PQ-105 platform coverage | "One machine for now" | parked on the user |
| PQ-106 accounts | "For now it can just be a CLI command or something similar" | **deviation**: operator-created accounts stay |
| PQ-107 licence | "No licence right now" | parked on the user |
| PQ-108 deployment | "No, not for now" | parked on the user |

**Rig result:** pass, with a client limitation
(evidence).

- **Servers:** the pinned Ebenezer, AI server and Aujard run unmodified under
  Wine 8.0 in containers with no route out. They use the 1.298 database, maps
  and scripts from the user's local `ko-1298` collection, and its
  third-party login server.
- **Client:** it reaches Moradon by script from a fresh database in about
  6.5 minutes, passing through the launcher, login, server list, nation,
  character creation and the HUD.
- **ODBC:** unixODBC's cursor library rejects the servers' unbound
  `SQLFetch`/`SQLGetData` loads. The rig rebuilds that library with a two-change
  patch; the servers themselves are not changed.
- **The pinned client** does not start under Wine: it faults inside HackShield.
  Removing that start-up from the binary was refused by the session's safety
  classifier and was not attempted another way. The rig uses the archive's
  `KnightEmpire.exe`: the pinned build with 996 changed bytes in 33 places, some
  of them presentation (probable UI font sizes, display modes).
- **Consequences:** rig captures name the archive client until PQ-110 attributes
  its changes or the user decides PQ-109. World captures need the game clock and
  camera pinned (PQ-004). Rendering is software and there is no audio, so frame
  timing and sound are not rig evidence.
- **Guard:** a rule refuses Wine anywhere but the rig.

## D-130 — 2026-09-30 The rig keeps the archive client; the pinned client is not patched

The user answered PQ-109 through the parity inbox: "use the archive client
(`KnightEmpire.exe`) in the rig; that's totally fine. Do not patch the pinned
client."

- **Disposition:** PQ-109 closes as a **deviation**. The pinned
  `KnightOnLine.exe` is never modified to skip its HackShield start-up.
- **Consequences:** rig captures come from the archive client and are labelled
  with it. PQ-110 stays the way to read a capture as pinned behaviour: every one
  of the 33 changed sites is attributed statically against the pinned client.

## D-131 — 2026-09-30 The loop keeps its own agent definitions and skill current

PQ-001 changed the gate's live tier to always run `make live`, but the parity
worker and reviewer definitions under `.claude/agents/` still described the old
rule (list the Compose-backed suites in `checks`, or the gate refuses). Asked
whether the loop may correct them (PQ-113), the user answered in the loop session:
"Yes, please keep those files up-to-date with the latest policies always."

- **Standing permission:** an item that changes loop or gate policy
  (`docs/parity/LOOP.md`, `tools/parity/gate.py`, `tools/parity/queue.py`, or the
  queue, inbox and log conventions) updates `.claude/agents/parity-worker.md`,
  `.claude/agents/parity-reviewer.md` and `.claude/skills/parity/SKILL.md` in the
  same item, so no agent works from a superseded rule. The reviewer checks it.
- **Limits:** the permission covers those three files only. `.claude/settings.json`,
  `.claude/settings.local.json`, permission and allow rules, and the guard hook
  (`tools/parity/guard.py` and its registration) are not covered; they change only
  at the user's explicit request. The files may only be brought in line with policy
  already recorded in LOOP, the gate and decisions; they never grant the loop more
  than D-128 does.
- **Recorded in:** LOOP and the worker
  definition; PQ-113 evidence.

## D-132 — 2026-10-01 A test-only server tick for disposable live realms

PQ-115 asked for a simulation time scale so the live tier spends less real time
waiting on game timers. Measured before the change: `make live` (4 jobs, graphical
branches on) took 502 to 518 s with the CPU mostly idle (PQ-114: 83 to 89 % idle).

- **Selected:** `N3E_TEST_TICK_MS` (an integer from 10 to 50) shortens the
  wall-clock length of a tick. The server accepts it only with
  `N3E_TEST_REALM=disposable` and a realm named `test-...`, the same two-part guard
  as `N3E_TEST_PROGRESSION=disposable`; any other combination stops every server
  command before it touches a dependency, with an error naming the guard. An
  accepted tick prints a `WARNING: TEST-ONLY TICK SCALE ACTIVE` line at start and
  the health body reports `tick_ms=`. `compose.yaml` passes an explicit environment
  list and neither it nor `deploy/` names the variables (checked by
  `tests/tick_scale.py` in `make test`), so no production configuration reaches it.
- **Ticks stay the unit.** Every rule still counts ticks and one tick is still
  50 ms of game time; only the conversions between ticks and wall time read the
  tick: the simulation interval, the durable respawn deadline (`delay` ticks) and
  the durable skill cooldown (`cooldown_ms` of game time), written and read back at
  the same tick. Everything that bounds wall time for correctness stays in wall
  time: the 3 s realm lease and its 400 ms renewal, the 2 s admission deadline, the
  2 s network idle deadline, the per-second frame and request limits, the Redis
  login limits and TTLs, the 2 s and 4 s admission windows of commits, the 2 s
  checkpoint cadence and 4 s staleness check, statement and lock timeouts, retry
  budgets, loot TTLs and consumable delays and cooldowns (their rules are in wall
  milliseconds, with no tick counterpart). Rate limits counted in ticks (chat
  once per 20 ticks, party invitation `repeat_ticks`, friend presence
  `refresh_ticks`) are rules and follow the tick, so on a test realm they allow
  proportionally more per second of wall time; production is unchanged. Audit
  table in the evidence.
- **Considered:** scaling the wall-time bounds too (rejected: the lease, deadlines
  and limits protect correctness and abuse bounds, and suites test them as wall
  time); a cargo feature or a separate test image (rejected: the Compose suites
  use the production image, so a build switch would test a different binary); a
  scale factor instead of a tick length (equivalent; milliseconds read directly in
  logs and health).
- **Harness:** `tests/live.py` runs every suite at the production 50 ms tick
  by default, and so does the gate (it removes `LIVE_TICK_MS`). `--tick-ms=25`
  (`make live LIVE_TICK_MS=25`) is an opt-in developer knob that runs the suites
  marked `scaled` at 25 ms. A suite's graphical branch always runs at 50 ms: the
  client assumes 50 ms ticks (`client/render/melee.h`, `player_pose.h`,
  `hotbar.h`), so a window against a faster server would not show what a player
  sees. 10 ms was tried and lost fights to harness reaction time.
- **Why not the gate default (review of attempt 1):** measured at 25 ms in the
  gate configuration, the run stayed at 515-522 s, bounded by the graphical
  suites' display chain (PQ-121 owns that floor), while 22 suites lost their only
  production-tick run, wall-time windows spanned twice as many ticks (so
  tick/wall races would show less), and one `life_live` failure stayed
  unexplained (1 of 17 recorded runs at 25 ms, PQ-128). Switching the default is PQ-127, after PQ-121 and PQ-128.
- **Consequence:** a headless developer run at 25 ms took 342 s against 397 s at
  50 ms. Recorded in [CONTRACTS](CONTRACTS.md), LOOP "Gates" and the evidence.

## D-133 — 2026-10-01 The gate's graphical clients render offscreen on the GPU

PQ-116 made a display and a hardware GPU hard gate requirements and ran the seven
graphical suites' clients as desktop windows, one suite at a time: their chain
was the live tier's floor (506-509 s) and the windows took the desktop's focus for
about 8.5 minutes per run. PQ-121 asked for an isolated display per suite.

- **Selected:** SDL 3's offscreen video driver. `tests/live.py` gives every suite
  `SDL_VIDEO_DRIVER=offscreen` and removes `WAYLAND_DISPLAY` and `DISPLAY`; each
  client renders through EGL into a pbuffer on the GPU (renderer
  the NVIDIA GPU on the reference machine), with no window and
  no compositor, and its swaps are paced to 60 Hz because no display paces them
  (`client/render/viewer.cpp`, only when SDL reports the `offscreen` driver, which
  shows nothing and which no player runs). The graphical suites no longer hold
  `display`. The requirement is now **a hardware GPU, not a desktop**: a GPU probe
  (one offscreen `--smoke` client with `N3E_REQUIRE_HARDWARE_GL=1`) runs before
  any suite and fails the run without an EGL device or on a software rasteriser.
- **What the branches keep:** the GPU renderer and its refusal of llvmpipe; the
  replays' focus and pointer events, which were already scripted
  (`SDL_PushEvent`; the melee replay ignored native focus events) and now cannot
  be disturbed by the desktop; resize (`SDL_SetWindowSize` produces
  `SDL_EVENT_WINDOW_RESIZED`; no live suite asserts a native one); the 33 and 7 ms
  frame delays (20 and 30 fps under the 60 Hz pacing); captures, now at the
  requested 1280x800 instead of the tile size the window manager chose.
- **Lost, and where it stays tested:** the window-system path (Wayland surface,
  compositor resize, minimize and restore, real vsync) is no longer in the gate;
  `make graphical` (`tests/graphical.py`) still exercises it on a desktop.
  `make live LIVE_DISPLAY=desktop` keeps the PQ-116 run for watching, and
  `make live-ko` keeps desktop windows (until D-193: since PQ-129 it renders
  offscreen too).
- **Considered:** Xvfb per suite (measured: the NVIDIA GLX path renders on the
  GPU under Xvfb, EGL falls back to llvmpipe; it would add an X server per suite
  to start, number and clean up, and X11 is not the backend players use here);
  rootful Xwayland or a nested compositor (each opens a window on the
  desktop and needs a compositor installed); compositor window rules (host
  configuration). None was needed.
- **Consequence:** `make live` 450 s and 451 s (46/46), against 506-509 s; the
  floor is now the `ko-01` fixture chain (446-447 s, PQ-117). Evidence:
  pq-121.

## D-134 — 2026-10-01 The client's test harness is a separate test build

The client's replay, smoke and capture modes, `N3E_TEST_*` switches and automatic
login were compiled into the player client, and its replays hard-coded the demo
packages' `demo:item/*` IDs and the Moradon and demo warehouse passwords (GAPS
"Test harnesses in production client", PQ-006).

- **Selected:** one source, two executables per build directory. `n3e-client` is
  compiled with `N3E_HARNESS=0` and has none of the harness; `n3e-test-client`
  (`N3E_HARNESS=1`) adds it. The large replays moved into
  `client/harness/*.inc` fragments that only the test build includes inside
  `viewer()` (they drive the same SDL queue and viewer state a player's input
  does); small hooks stay in `viewer.cpp` behind `#if N3E_HARNESS`, and the few
  modes shared code tests are `constexpr false` in the player build.
  `tests/player_build.py` checks 16 harness markers absent from each player binary
  and present in its test binary, and that the player client refuses `--smoke`.
- **Game data:** replays take items by role from `N3E_TEST_ITEMS` and warehouse
  passwords from `N3E_TEST_STORAGE_PASSWORD`/`N3E_TEST_STORAGE_REPLACEMENT`, set by
  the suite that provisions them; neither client contains them.
- **Kept in the player client:** `--connect`, `--ca`, `--fixed-window`,
  `--fullscreen` and the developer frame profiler `N3E_PROFILE` (it measures the
  player build itself). The automatic login (`--auto-login` with
  `N3E_TEST_ACCOUNT`/`N3E_TEST_PASSWORD`) is test-only: the session tools, which
  use it, now start the test client; a player types credentials.
- **Considered:** a harness interface object receiving the viewer's state (about
  100 locals the replays read and write; too large a refactor to land with an
  unchanged replay suite) and `if constexpr` without moving code (still leaves the
  replays in the player source). Neither was needed now.
- **Consequence:** `viewer.cpp` 4254 to about 2700 lines; the client builds twice
  per directory (the network sources and ImGui once, as object libraries). No
  player-visible change and no server change. The server's test-fixture commands
  are PQ-131. Evidence: pq-006.

## D-135 — 2026-10-01 Review findings are blocking or non-blocking; up to three review rounds per attempt

Until now a parity attempt had two reviews: the first `REJECT` went back to a
worker once and a second `REJECT` failed the attempt, and the reviewer could not
approve with any open finding. Three attempts failed that way (LOG: PQ-123,
PQ-115 and PQ-128, attempt 1 each); PQ-115's second rejection named one stale
evidence row. The user, in the loop session on 2026-10-01: when a reviewer finds a
small issue such as a stale file:line reference, "having them address that
targeted issue would be fast" (INBOX, Processed; PQ-130).

- **Classification:** the reviewer marks each finding **blocking** or
  **non-blocking**. Blocking: wrong behaviour; safety or server authority;
  binary evidence (a claim resting on `ref/ko-src` alone or labelled more
  strongly than its evidence, a Ghidra address that does not decompile to what
  is described); any statement that would mislead a reader about behaviour, risk
  or evidence. Non-blocking: immaterial only (a drifted file:line that still
  leads to the right code, wording, cosmetic counts in narrative). A breach of
  the reviewer's other checks (package boundary, weakened checks, scope,
  correction records, committed reference data) and a finding the reviewer is
  unsure of are blocking. `REJECT` only for a blocking finding;
  non-blocking ones are listed under `APPROVE`.
- **Non-blocking fixes:** after an `APPROVE` that lists non-blocking findings,
  the same worker fixes them in one commit before the gate, with no re-review.
  The commit may only modify an allowed set: the item's own evidence record and
  the Markdown files the reviewed diff (`origin/main...<approved tip>`) already
  changed, minus the control files, which are never allowed (`.claude/`, `ref/`,
  `docs/parity/`, `tools/`, `AGENTS.md`, `CLAUDE.md`,
  `docs/ko/BINARY-POLICY.md`, `docs/implementation/DECISIONS.md`), so an
  unreviewed commit cannot rewrite the policy, the standing authorization, the
  user's inbox or a gate result. The orchestrator checks it mechanically. A
  commit that fails the check goes back to review as the next round; if no
  round is left, the orchestrator reverts it with one new commit, confirms the
  tree equals the approved tip and gates the approved content (outcome `failed`
  if that cannot be done cleanly).
- **Review rounds:** blocking findings go back to the same worker as targeted
  fixes, and a fresh independent reviewer reviews the whole branch again, up to
  three review rounds per attempt. An attempt fails only when a blocking finding
  survives the third review.
- **Unchanged:** the three-attempt budget, a fresh independent reviewer each
  round, the gate before merge, the gate-failure and rerun rules, never
  recording a failed gate as a pass, server authority and binary confirmation.
- **Recorded in:** LOOP, the parity skill (step 5),
  the reviewer and worker definitions (D-131); PQ-130
  evidence.

## D-136 — 2026-10-01 Input maps are package data; the engine keeps F11, F12 and the backtick

The client hard-coded one key layout that diverged from the KO client
(`KnightOnLine.exe` `005c6990`, investigation A): V ran, E respawned, Tab and Z
cycled every NPC, Space and 1 attacked, F looted, and F5 (reconnect) and F2 (tools
editor) sat inside KO's F1–F8 hotbar-page range (GAPS "Input map", PQ-009).

- **Selected:** a package declares an `input` table of bindings (engine action,
  key, required and forbidden modifiers, whether it fires while typing). The cooker
  writes it to `input.bin` (`N3I1`); the client validates it against the engine's
  action and key vocabularies and fails closed on an unknown name. A key may bind
  several press actions; they run in table order and a later one runs only when an
  earlier one declines the press (Enter: respawn while dead and ready, else chat).
  Held actions (movement, turning, turbo) read the key state every frame. Keys are
  physical positions (SDL scancodes), as KO's DirectInput codes are.
- **Engine-reserved keys:** F12 reconnects (was F5), F11 opens the tools editor
  (was F2), and the backtick opens the tools terminal. No package may bind them;
  KO's gameplay handler reads neither F11 nor F12. Login, character selection,
  text editing and Esc stay engine keys (Esc is PQ-010).
- **Packages:** the KO package (`games/moradon/input.json`, used by every KO bake)
  carries the KO table from the binary, including keys whose window or toggle
  n3e lacks (H, O, F9, left Shift+C, 9, 0, numpad −): they report "not
  implemented" until their items land. It has no loot key, because KO opens
  corpses by click only (`005c7c60`). The demo package uses the same layout plus
  F (collect nearest loot; the demo has no corpse window) and `[`/`]` window
  paging. A package with no table (older releases, `legacy-demo`) gets the
  pre-PQ-009 layout, so existing releases keep working.
- **Respawn:** KO respawns from a death window whose key handling is not
  located (open gate). n3e keeps its native death prompt; Enter confirms it, as a
  KO message box takes Enter before chat (`005e3f80`).
- **Considered:** SDL keycodes (layout-dependent; KO is not) and a JSON file the
  client reads directly (bypasses release identity and the cooker's validation).
- **Consequence:** client, cooker and server accept one more optional release
  asset (the server checks its magic and otherwise ignores it); no protocol
  change. Evidence: pq-009.

## D-137 — 2026-10-02 A statement timeout on the realm-fence lock is retried like a lock timeout

Claims (`loot.rs` `decide_routed`) and settlements (`settlements.rs` `settle`)
retry a failed attempt inside one 2 s deadline (at most four attempts, 50/100/200
ms backoff, each attempt's `transaction_timeout` set to the remaining budget), but
only for `40001`, `40P01` and `55P03`. PQ-011 attempt 3 saw a fence waiter fail
with `57014` instead: Postgres restarts `lock_timeout` (800 ms) each time a queued
waiter moves from the tuple lock to the next holder's transaction, but not
`statement_timeout` (1000 ms), so a waiter behind two holders can pass the
statement timeout with neither wait reaching the lock timeout (reproduced against
`postgres:17.4`, PQ-148).

- **Selected:** `persistence::fence` reports a `57014` raised by its row-lock
  statement as a typed `FenceWait`, and both retry loops treat it like `55P03`
  through one predicate, `persistence::retryable`. Deadline, attempt cap,
  backoff and every production timeout are unchanged.
- **Why retry:** a failed claim, settlement or expiry job invalidates the
  realm's health, which stops the realm process (`simulation.rs`), so failing
  closed here costs a realm restart, not one request. Whether a waiter in a
  queue gets `55P03` (already retried) or `57014` depends only on its place in the
  queue and when the holders hand over. A `57014` is an ERROR: the transaction is
  aborted and rolled back, the session survives, claim and settlement identities
  are idempotent, and the retry repeats the fence and every check.
- **Not retried:** `25P04` (transaction timeout). In PostgreSQL 17 it terminates
  the session (FATAL), and an attempt's `transaction_timeout` is the remaining
  budget, so it fires only when the deadline is spent. A `57014` from any other
  statement stays fatal to the attempt: it is a slow statement of unknown cause,
  not a queue, and nothing else in a claim or settlement waits on a row that
  production writers reach without the fence first.
- **Production stacks:** one durable worker per realm process means the realm's
  own jobs never queue against each other, but the row also takes the lease
  renewal `UPDATE` every 400 ms (a second connection), any other process's
  `acquire` for the realm (a duplicate realm process, `upgrade-progression`,
  `convert-progression`; `INSERT ... ON CONFLICT DO UPDATE` locks the row even
  when its `WHERE` refuses the takeover), and a former owner's backend whose
  transaction is still open. A second waiter is therefore possible in production;
  every such holder is brief unless the database stalls or a former owner is
  frozen mid-transaction (queued as PQ-151).
- **Considered:** failing closed (a realm restart for a queue position);
  raising `statement_timeout` for the fence statement (weakens a production
  timeout); `FOR UPDATE NOWAIT` with application polling (loses the queue's
  order and adds round trips); retrying every `57014` (retries slow statements
  blindly).
- **Recorded in:** [content/loot.md](../../content/loot.md),
  [content/progression.md](../../content/progression.md), PQ-148
  evidence.

## D-138 — 2026-10-02 Actor picks cast the cursor ray at package-bounded boxes; the tie-break tests the drawn mesh

n3e picked the actor whose projected chest point lay nearest the cursor within
45 pixels (PQ-011). KO (`KnightOnLine.exe` `004724c0`) casts the cursor ray at
each drawn actor's box, built from the skeleton's joint positions
(`0041c300`, `004482c0`), takes the only hit, and otherwise walks the hits in
camera-distance order (`00472250`) through a per-actor test (`0041c630`)
(PQ-146).

- **Selected:** the client casts the ray from the camera eye through the
  cursor at every drawn actor's box and keeps KO's order and rules: one hit
  wins; with several, the nearest actor (by distance from the eye to its
  position) whose drawn triangles the ray hits wins at LOD 0–1, and whose box it
  hits at LOD 2–3; otherwise nothing. The triangle test is KO's (front faces
  only, the 1e-4 determinant bounds, t ≥ 0). The box is axis-aligned in the
  model's space, taken in the idle clip's first frame for a living actor and
  the death clip's last frame once the death clip has played, and turned and
  placed as the model is drawn.
- **Package data:** an optional `pick` policy (`pick.bin`, `N3PK`) names the
  box source (`joints`: the joint positions, KO `0041c300`; `vertices`: the
  skinned mesh), the minimum box extent and its padding (KO: an axis shorter
  than 0.5 grows by 0.25 on each side) and the highest LOD whose mesh is tested
  (KO: 1). A release without it gets vertex boxes, no minimum and the mesh test
  at every LOD (vertex boxes because a joint box of a one- or two-joint
  stand-in rig is flat). The KO package (`games/moradon/pick.json`, every KO
  bake) carries KO's rule. The demo package keeps KO's extent and LOD values
  with vertex boxes: its synthetic rig has two joints on one vertical line, so
  a joint box would cover 1 m of its 1.73 m figure.
- **Correction:** KO's LOD 0–1 tie-break passes the world ray to character-local
  triangles and so never accepts a near actor; n3e keeps ray and triangles in one
  space (correction record in BINARY-POLICY, "Actor
  pick tie-break ray correction").
- **Considered:** keeping the projected-point proxy (not KO's geometry); a
  per-model box table cooked into each scene (format change for every model
  file, and KO derives the box from the skeleton at run time anyway); hard-coding
  KO's 0.5/0.25/LOD 1 in the engine (KO rules in an engine module).
- **Consequence:** client, cooker and server accept one more optional release
  asset (the server checks magic and bounds and otherwise ignores it); no
  protocol change; the pick reads the previous frame's drawn geometry.
  Evidence: pq-146.

## D-139 — 2026-10-02 Realm start-up waits out a previous owner's lease for up to 5 s

A realm process that dies without releasing its lease (SIGKILL, a crash, or a
database restart that drops its release) leaves `realm_ownership` live for up
to 3 s, and the lease of a process that already died can still be extended once
by a renewal it sent before dying (the `UPDATE` waits in the database's socket
buffer while Postgres is stalled and runs when it resumes). Start-up called
`acquire` once and exited with "realm already owned" inside that window; Compose
gives the server no restart policy, so the realm stayed down. PQ-146's full
`make live` hit it in `tests/gameplay.py`: after the Postgres-outage phase a
Postgres backend exited with code 2 on unpause, Postgres restarted every
backend, the old server's release was lost ("Closed"), and the restarted server
found the lease live 0.9 s later (PQ-153).

- **Selected:** server start-up (`main.rs`) takes ownership through
  `persistence::acquire_within(.., START_WAIT)`: it repeats `acquire`'s
  conditional takeover, sleeping until the lease's database expiry (plus 25 ms)
  between attempts, for at most `START_WAIT` = 5 s (one 3 s lease plus 2 s for a
  late renewal of a dead process), then fails with "realm already owned" as
  before. Admission is measured from the attempt that took ownership. The wait
  is printed once on stderr.
- **Never a takeover of a live owner:** every attempt is the unchanged
  `INSERT ... ON CONFLICT DO UPDATE ... WHERE expires<=clock_timestamp()`, so a
  live owner renewing every 400 ms refuses each one; a duplicate realm process
  now fails after 5 s instead of at once. Fencing, generations, lease length,
  renewal cadence and admission deadline are unchanged.
- **Not retried:** errors. A lock timeout behind a former owner's open
  transaction stays an error (PQ-151). Offline tools (`upgrade-progression`,
  `convert-progression`) keep the single attempt: operators run them against a
  stopped realm, and two launch scripts read their "realm already owned" as
  "already converted".
- **Considered:** a test-only wait in the suites (the same race hits a
  production restart after a crash); retrying until a fixed deadline at a short
  interval (each refused attempt takes the row lock, D-137); failing fast when a
  renewal is observed (a dead process's late renewal looks the same); a Compose
  restart policy (a deliberate stop on lease loss must stay stopped for the
  operator, CONTRACTS "PG/lease failure ... exits for explicit restart").
- **Recorded in:** [CONTRACTS](CONTRACTS.md), PQ-153
  evidence.

## D-140 — 2026-10-02 Postgres runs under an init process; realm start-up rides out 57P03 for up to 5 s

PQ-146's failed `make live` showed Postgres logging `server process (PID 1010)
exited with exit code 2` as the outage phase unpaused it, then killing every
backend and running crash recovery for 0.75 s (PQ-153 fixed the lease half of
that failure). PQ-155 found the process: not a backend but the Compose health
probe's `pg_isready`. The probe was `CMD-SHELL`, so Docker ran `/bin/sh -c`
(dash, which forks the command) and the shell ran `pg_isready`. Docker kills
the probe's shell when the probe outlives its 2 s timeout (Postgres or the host
stalled) and also when the container is paused with a probe in flight (pausing
stops the health monitor). `pg_isready` is then orphaned to PID 1 of the
container, which was the postmaster, and exits 2 ("no response") once its own
3 s connect timeout has passed. The postmaster takes any child it reaps with an
exit status other than 0 or 1 for a crashed backend (`CleanupBackend`,
PostgreSQL 17.4) and restarts the cluster. Reproduced three ways: pausing the
container while the probe's `pg_isready` was running (1 crash in 6 rounds, CPU
limited so the probe could be caught), a probe aimed at an unroutable address
with no pause, and an injected orphan (`sh -c '(sleep 1; exit 2) &'`). The realm then hits Postgres's recovery window:
a server started inside it gets FATAL 57P03 (`cannot_connect_now`: "the database
system is in recovery mode", "... is starting up", "... is not accepting
connections") at its first connection and exits.

- **Selected, deployment:** the Compose `postgres` service sets `init: true`, so
  Docker's init (tini) is PID 1 and reaps every orphan, and its health probe uses
  the exec form (`["CMD", "pg_isready", ...]`), so no shell stands between Docker
  and `pg_isready` to leave it orphaned. Each change alone prevents the crash
  (both were run); both are kept, because anything else orphaned in the
  container (an operator's `docker exec` session, a future probe) would crash
  the cluster the same way. Stop signal, data volume and the TCP probe target
  (PQ-001) are unchanged.
- **Selected, start-up:** realm start-up opens its connections through
  `persistence::connect_within(url, START_WAIT)`: the start-up connection that
  verifies the schema and takes the lease, and the account/checkpoint worker's
  connection, which is opened at the same moment. A refusal with SQLSTATE
  57P03 is retried every 100 ms (`CONNECT_RETRY`) until the 5 s `START_WAIT`
  runs out (a separate window from D-139's lease wait, which starts once
  connected), then that refusal is returned and start-up fails as before. The
  wait is printed once on stderr.
- **Why it is safe:** nothing durable happens before a connection exists, so a
  retried connect cannot repeat an effect; the lease, fencing and generations
  are untouched, and every connection after start-up still treats any failure
  as final (a lease failure still stops admission and exits for an explicit
  restart).
- **Not retried:** any other connect failure: a refused or timed-out socket,
  bad credentials (28P01), an unknown database. Those are configuration or a
  stopped Postgres, not Postgres announcing that it will accept shortly.
  Offline commands (`migrate`, `role`, `account-create`, the conversions) keep
  one attempt; Compose starts `migrate` only once Postgres reports healthy.
- **Considered:** a readiness wait in the suites after unpause (an unpaused
  Postgres is ready at once; the crash came from the probe, and production
  stalls hit the same probe); a Compose restart policy for the server (a stop
  on lease loss must stay stopped, D-139); `--init` only, or the exec-form probe
  only (each closes one path; see above); retrying all connect errors (would
  hide a misconfigured or stopped database for 5 s on every start).
- **Recorded in:** [CONTRACTS](CONTRACTS.md), PQ-155
  evidence.

## D-141 — 2026-10-02 The account/checkpoint worker connects before the lease; a worker that stops serving closes admission

`accounts::Database::start` opened the realm's one account/checkpoint connection
on its own thread, at the same moment as the start-up connection, and on any
connect error other than a 57P03 inside D-140's window the thread ended without
a word. Start-up went on, took the lease and ran its start-up writes. The first
worker call (the simulation's entity-id reservation, `instances`) then failed with "database
queue unavailable", which invalidated admission, and the renewal thread ended
the process with "admission expired; restart required" about 400 ms later. That
message hid the real error, the lease was left to expire (the release goes
through the dead worker), and a restart had to wait it out (D-139). Observed
once in three runs of the old binary against a role limited to one connection
(PQ-156). After start-up nothing watched the worker: a panicked job or a closed
connection left a realm that reported ready while every login, character and
checkpoint call failed, until some call made by the simulation happened to fail.

- **Selected, start-up:** `Database::start` returns once the worker's
  connection is open, or returns its connect error. `main.rs` calls it inside
  the start-up task after the start-up connection has verified the schema and
  before `acquire_within`, so a worker that cannot connect ends start-up with
  its own error and takes no lease (D-139's lease is never touched). The worker
  keeps D-140's 57P03 retry and nothing else. Because the worker now connects
  after the start-up connection instead of beside it, a start inside Postgres
  recovery waits for the start-up connection first; once that is in, Postgres
  is accepting and the worker connects at once.
- **Selected, after start-up:** the worker thread holds a guard that
  invalidates `Health` when the thread ends for any reason (a job panic
  included), and the worker ends when its connection is closed after a job
  (a closed `postgres::Client` never reopens). Invalidation is the existing
  fail-closed path: `/ready` answers 503 at once, the renewal thread sees
  admission gone and the process exits for an explicit restart. A job that only
  returns an error (a failed statement, a fence refusal) on a live connection
  stays that caller's error.
- **Considered:** a separate readiness flag for the worker while the realm
  keeps running (the worker cannot reconnect without new retry policy, and a
  realm that can serve nothing should not hold the lease); reconnecting the
  worker after start-up (every connection after start-up treats failure as
  final, D-140; reconnect would need its own fencing and queue semantics);
  opening the worker beside the start-up connection and joining both before
  the lease (keeps the concurrent race in which either connection can be the
  one refused, and the second connection is cheap once Postgres accepts).
- **Recorded in:** [CONTRACTS](CONTRACTS.md), PQ-156
  evidence.

## D-142 — 2026-10-02 A lease renewal that timed out behind the realm row is retried while admission lasts

Every durable mutation calls `persistence::fence`, which locks the realm's
`realm_ownership` row (`FOR UPDATE`) until its transaction commits, and the
renewal thread's conditional `UPDATE` of that row queues behind the lock. The
renewal made one attempt: when a mutation held the row longer than the session's
`lock_timeout` (800 ms), the attempt ended in SQLSTATE 55P03, the thread
invalidated admission and the process exited, although the lease had about
1.8 s left when the attempt timed out (more than 2 s when it started) and the
holder was the realm's own fenced write. PQ-148 had reproduced the 55P03 and
queued the question as PQ-149; this is the first of PQ-149's options. Observed under the
parallel `make live` load: `party_rewards_live`'s realm exited during its first
grouped kill with "canceling statement due to lock timeout ... while updating
tuple in relation realm_ownership" on the renewal statement, and both test peers
read EOF (PQ-154). The Postgres log does not name the holder; during a kill
the realm's fenced writes are the reward settlement and the account worker's
fenced writes (checkpoints, life transitions).

- **Selected:** `persistence::renew_within` retries the same conditional renewal
  at once when an attempt ended waiting for the row (55P03, 57014 statement
  timeout, 40P01 deadlock: an ERROR that aborted only that statement, so nothing
  was renewed and the session survives), but only while the local admission
  deadline still holds; it returns when the successful attempt started, and
  admission is measured from that start as before. No attempt starts after
  admission has ended, so the 3 s / 400 ms / 2 s values and the guarantee that
  admission ends before the database lease can run out are unchanged. A fenced
  renewal ("realm fenced": lease ran out, takeover, new generation), a closed
  connection and every other error still invalidate admission and end the
  process for restart at once.
- **Considered:** a longer `lock_timeout` for the renewal connection (one long
  wait could outlast admission with no attempt to observe it; the retry keeps
  each wait at 800 ms and checks admission between waits); a weaker fence lock
  mode (`FOR KEY SHARE` would no longer conflict with a takeover's generation
  update, losing the fence); shorter mutation transactions (they are already
  bounded per statement; the slow part under load was the commit); moving
  lease expiry off the fence row (PQ-149's second option: renewal would never
  wait behind a write, but every fence, takeover and release would have to
  read or lock a second row consistently, a schema and fencing change beyond
  a gate fix; it stays open in the narrowed PQ-149, as does whether a hold
  longer than admission, about 2 s, is reachable without a database stall).
- **Recorded in:** [CONTRACTS](CONTRACTS.md), PQ-149, PQ-154
  evidence.

## D-143 — 2026-10-02 Mode-3 camera input: right-drag yaw and distance, Home/End pitch and screen-edge yaw as package data

D-025 kept right-drag yaw + pitch with wheel zoom as "a labeled adaptation
awaiting user testing". No logic bug or exploit backs it, so under
BINARY-POLICY it is a fidelity gap, not a retained
deviation. KO mode 3 (`KnightOnLine.exe`, PQ-012): right-drag yaws the camera
horizontally and changes its distance vertically (`005e3e20` → `0063e240`,
`0063e2e0`; dragging down moves the camera away); Home and End raise and lower
the pitch at π/4 rad/s while no text field has focus (`005c6990`, DIK `0xc7`/
`0xcf` at `+0x133`/`+0x13b`, `DAT_006dfe20`; clamp 10°..70°, `0063e0e0`); the
cursor on the outermost pixel column yaws the camera at 2 rad/s, left edge as
dragging left (`005c6990`, `006e270c`).

- **Selected:** the camera data gains an optional extension, cooked as `N3V2`
  (the `N3V1` fields, then four more): `drag_vertical` (`pitch` or
  `distance`), `distance_per_pixel`, `key_pitch_rate` and `edge_yaw_rate`
  (0 disables either). The input map gains two held actions,
  `camera_pitch_up` and `camera_pitch_down`, which the package binds. A
  camera block without the extension still cooks to the same `N3V1` bytes and
  keeps yaw + pitch dragging with no key pitch or edge yaw.
- **Package data:** the KO package (`games/moradon/camera.json`, every KO
  bake) carries KO's mode 3 (distance dragging, Home/End at π/4 rad/s, edges at
  2 rad/s); `games/moradon/input.json` binds Home and End. The demo package and
  the KO-02 camera laboratory keep their camera unchanged (yaw + pitch
  dragging), as the demo kept its own key layout under D-136.
- **Correction:** KO scales each frame's drag pixels by the frame time; n3e
  applies a fixed per-pixel rate taken at the binary's nominal 1/30 s
  (correction record in BINARY-POLICY, "Right-drag frame-time scaling
  correction"). This retires D-025's "frame-independent pixel sensitivity"
  label as a separate adaptation: it is now this correction.
- **Kept n3e behaviour:** edge yaw needs the cursor inside the focused window
  (KO reads the raw cursor, so in a window it also turns only on the border
  column). n3e turns no edge yaw during a right-drag, a gap (PQ-160):
  KO's edge test reads that frame's raw cursor: `005c6990` loads x into ESI at `005c69c5`, calls the drag handler at `005c6a02` and compares the same ESI at `005c6ac6`–`005c6aed`, so it runs before `005e3e20` puts the cursor back, which `005e3e20` does only on frames with drag motion; `006400f0` then stores an x at or left of its rect's left edge (`+0x5c`, created empty by `0063ff40`) as left + 1 (`00640115`–`00640120`). So KO turns on drag frames whose
  cursor rests on a border column and not on frames that move away; after a
  moving frame on the left column the cursor probably sits on column 1 (an
  inference: no writer of that rect was found). n3e's existing end of a drag on death stays (KO keeps distance
  dragging and skips only the yaw while dead, PQ-160); the wheel's step and frame-time
  scaling are PQ-159;
  modes 0–2, F9, shake and transformed zoom are out of scope (PQ-042 owns
  modes).
- **Considered:** reinterpreting `pitch_per_pixel` as distance per pixel (the
  same bytes would mean different things to old and new readers); hard-coding
  KO's rates in the engine (KO rules in an engine module); mirroring the
  frame-time scaling (the correction above); binding Home/End in the engine
  (packages own keys, D-136).
- **Consequence:** client, cooker and server accept `N3V2` as well as `N3V1`
  (the server checks magic and bounds and otherwise ignores it); no protocol or
  database change. Evidence: pq-012.


## D-144 — 2026-10-03 KO 3-D sound: effect start test under 48 m from the camera, player listener, as package data

The 3-D sound gap (GAPS) read "a hard 30 m cut-off (KO: < 48 m, option 20–48),
generic panning, and moving sources are not tracked". The client binary
(`KnightOnLine.exe`, PQ-013) shows a narrower rule and corrects the last claim:

- `Sound.Distance` is read from `Option.ini` as an integer, default 48, clamped
  to 20–48 (`0064b9b0`), and copied to the float `006d4714` (static 48.0) at
  start-up (`006453b0`, `00645a7d`). Its only reader is `00475d20` (the FX bundle
  trigger, by source naming), which starts the bundle's sound only when the
  distance from the camera eye (`006e26d0`, copied from the camera by
  `004395c0`) to the bundle position is strictly below it (`00475e0c`
  `FCOMP`/`TEST AH,1`). Character sounds started through `004501b0` do not take
  this test.
- The Miles listener is the object at `00818794` (the player, by source naming):
  its position (`+0x98`) and its rotation's forward axis (`0045a200`), up
  (0, 1, 0) (`00646550` → `0044d350` → `004504f0`, `00450520`).
- A 3-D sample's position is set once when it starts (`004501b0`,
  `AIL_set_3D_position`); the per-frame tick `0044fdf0` changes only volume and
  fades, and the only other caller of that import positions the listener. So KO
  does **not** track moving sources; n3e's start-position voices already match.
- The provider is "Miles Fast 2D Positional Audio" (`00450560`), and KO imports
  no `AIL_set_3D_sample_distances`, so attenuation and pan follow the provider's
  defaults inside Miles, which the supplied client inputs do not include.

- **Selected:** the audio block gains an optional positional policy, cooked as
  `N3A2` (the `N3AU` data, then `listener`, `effect_distance` with its option
  bounds, `cutoff`, `reference`). Effect-bundle sounds (`effect:` keys) start
  only while the camera eye is strictly nearer than `effect_distance`, tested
  once in the audio chunk where the voice begins, and then play with no cut-off;
  other positional sounds keep the cut-off. `listener: character` puts the
  listener at the controlled character's drawn position and facing (camera
  while there is none). `AudioSpatial::start_distance(option)` clamps a player
  integer to the bounds as KO does; nothing passes one until local options exist
  (PQ-162, under PQ-048).
- **Package data:** the KO package (`games/moradon/audio.json`) carries
  `character`, 48 (20–48), cut-off 30 and reference 2. `N3AU` keeps its meaning
  (camera listener, no start test, 30 m cut-off for every positional voice); the
  demo package ships no audio.
- **Kept n3e behaviour (fidelity gaps, not deviations):** the inverse-distance
  gain from 2 m and the equal-power pan stand in for the unavailable Miles curves;
  character sounds (swing, struck, blow) keep the 30 m cut-off until KO's
  character-sound range is confirmed (PQ-161; source suggests load within 10 m,
  release beyond 20 m).
- **Considered:** one distance for every positional sound (KO applies
  `Sound.Distance` to effect sounds only); tracking moving sources (KO does not);
  hard-coding 48 m in the engine (a KO rule in an engine module); a new package
  file (the policy belongs with the clips it governs).
- **Consequence:** client and cooker accept `N3A2` as well as `N3AU`; the server
  checks only its presence against the engine version. No protocol or database change.
  Evidence: pq-013.

## D-145 — 2026-10-03 The realm fence locks its own row; lease renewal never waits behind a durable write

Refines [D-142](#d-142--2026-10-02-a-lease-renewal-that-timed-out-behind-the-realm-row-is-retried-while-admission-lasts).
The fence (`persistence::fence`, `FOR UPDATE`) and the lease (renewal's
conditional `UPDATE ... expires`) shared the `realm_ownership` row, so every
renewal queued behind every durable transaction of its own realm, and D-142's
retry only moved the limit from `lock_timeout` (800 ms) to admission (2 s). The
PQ-014 merge gate (`b9aa658`) then failed `melee_live` under the ordinary 4-way
`make live` load: the renewal timed out on the row at 09:36:35.218 and again at
09:36:36.018 (two consecutive 800 ms waits), admission ended, the realm exited
and both test peers read EOF. Postgres did not log the holder (`log_lock_waits`
is off); a 4-suite diagnostic run with `log_lock_waits=on` and
`deadlock_timeout=150ms` on the server's sessions showed no production waiter
over 150 ms in `melee_live` or `party_rewards_live`, whose 2012 and 613 fenced
transactions held the row for at most 55 ms and 35 ms. A row wait longer than
admission is therefore reachable under ordinary 4-way `make live` host load,
with no database outage, but rare; whether the holder was a descheduled client
or a stalled commit is not known (inference, PQ-149).

- **Selected:** a new `realm_fence(realm)` table (migration 021, backfilled from
  `realm_ownership`) carries the fence lock. `fence` locks the realm's
  `realm_fence` row `FOR UPDATE` (same lock, same D-137 wait and timeout
  behaviour) and then reads owner, generation and expiry from `realm_ownership`
  without locking it. A takeover (`acquire`, `acquire_within`) runs in one
  transaction: insert the `realm_fence` row if missing (`ON CONFLICT DO
  NOTHING`, no lock), lock it `FOR UPDATE`, then the unchanged conditional
  upsert of `realm_ownership`. Renewal, release, the start-up expiry read and
  every liveness reader keep their `realm_ownership` SQL unchanged.
- **Why it is safe:** a takeover holds the fence row until it commits, so no
  takeover commits while a fenced transaction is open, and a fence that locks
  after a takeover reads its new owner and generation (READ COMMITTED takes a
  new snapshot per statement). Renewal and release take `FOR NO KEY UPDATE` on
  `realm_ownership` only; the realm process's fenced transactions take at most
  `FOR KEY SHARE` on it (foreign-key checks of rows that reference the realm),
  which does not conflict. One fenced transaction is the exception: the offline
  `upgrade-progression` command (`reward_upgrades::upgrade`) extends the lease
  to 30 s with an `UPDATE realm_ownership` right after `fence`, holding
  `FOR NO KEY UPDATE` on the lease row until it commits (at most its 15 s
  `transaction_timeout`). It is safe because that owner is an offline command
  with no renewal thread, and it locks the fence row before the lease row, the
  same order as a takeover, so it adds no deadlock cycle; renewing during such
  an upgrade would wait behind it. So the realm process's renewal never waits
  behind a durable write; it can still wait briefly
  behind another process's takeover attempt (the upsert locks the row even when
  it refuses), which D-142's retry inside admission still covers. Release no
  longer waits for the owner's in-flight fenced writes; a later takeover does.
  Admission (2 s from the start of the last successful renewal attempt, before
  the 3 s database lease) and the 3 s / 400 ms values are unchanged. A fence on
  a realm whose `realm_fence` row is missing fails with "realm missing", as for a
  missing ownership row; only rows a test inserts directly can lack one.
- **Considered:** moving `expires` (and a copy of the generation) to a second
  row instead (the option PQ-149 named): the same decoupling, but every lease
  reader (renewal, release, start-up wait, turbo liveness, test helpers) would
  move, where moving the lock touches only the fence and the takeover; a weaker
  fence lock with `generation` made a key column by a unique index (renewal's
  non-key update would then not conflict with `FOR KEY SHARE`, a takeover's key
  update still would): it relies on Postgres's key-column rule, which its
  documentation says may change, and it would stop serialising the realm's
  fenced writes against each other, which existing transactions may rely on; a
  transaction-scoped advisory lock: no schema, but invisible in the schema and a
  different wait shape from D-137's tuple-lock queue; a longer `lock_timeout`
  or a longer admission: the lease guarantee bounds admission below 3 s.
- **Recorded in:** [CONTRACTS](CONTRACTS.md), `deploy/021-realm-fence.sql`,
  PQ-149. Evidence: pq-149.

## D-146 — 2026-10-10 The NPC info line follows the projected server.inspect; the projection refreshes only when a Registry arrives

KO's NPC label refresh (`00465070`, `KnightOnLine.exe`) adds a green line
`ID(%d) : TYPE(%d)` above an NPC's name only while the local player's MyInfo
authority byte (`+0x4a4`, written from the packet at `005c96f7`) is 0. When the
byte is not 0 it skips the line (`0046509e` → `00465177`) without clearing it;
the line goes only when the labels are freed (`00456b40`) or the NPC is
released (`00455e40`). The client-held byte is the authority in KO; n3e keeps
roles on the server (PQ-175, PQ-177).

- **Selected:** the client draws the line only while the capability set the
  server last projected (`Registry.capabilities`) holds `server.inspect`, the
  engine's inspection capability. The text and colour are package data
  (`names.npc_info`, `N3I7`); nothing local (a tools build, a flag, package
  data) can enable the line, and it shows only the entity id every client
  receives, so the server sends nothing new. The projection is refreshed as it
  is today: at session start (the client's one `registry` request) and with the
  final AdminResult of each admin job. A grant or revoke pushes nothing; the
  player build sends no later admin request, so it sees a change at its next
  session. Revocation follows the binary: from the next projection without the
  capability no line is set, and a line already shown stays until the NPC's
  label is dropped (lifetime rule, death, leaving view, new session). That is
  KO's own shape (the byte changes only when a MyInfo packet arrives), and a
  stale line discloses nothing and authorizes nothing: every privileged request
  is still checked against `character_roles` on the server.
- **Considered:** pushing a fresh Registry to the character's session on every
  grant or revoke (no KO counterpart, a new server path for a presentation
  aid that KO parity does not need; the tools terminal's completions would
  also benefit, so it is left to a separate request); hiding the line at once on revocation (a departure from
  `00465070` that would need a BINARY-POLICY correction record, and no logic
  bug or exploit is involved); a client role or a tools-build switch (imports
  KO's client-held authority).
- **Recorded in:** [CONTRACTS](CONTRACTS.md) C-05 and "Package input map",
  [content/nameplates.md](../../content/nameplates.md), PQ-177. Evidence:
  pq-177.

## D-147 — 2026-10-10 The NPC state trace reports the server's NPC behavior to leased server.inspect sessions in range

KO's operator command `+actpursue <id>` (Ebenezer `0042c1ba`) makes the AI
server mark an NPC (`00407651`, `+0xc54` = 1; only the NPC constructor
`00417873` clears it). Each AI step of a marked NPC then reports its state byte
(`+0x2b4`), and Ebenezer `0040b4d4` forwards it as client opcode `0x5d` to the
in-game users of the NPC's 3x3 regions whose authority byte is 0 (`0041e454`),
whose client shows it as `TYPE(%d)` in the operator NPC info line (PQ-177).
KO's states are its AI server's numbering; n3e's NPC AI has its own behaviors.

- **Selected:** a `server.inspect` holder marks an NPC with the admin operation
  `trace` (`AdminRequest.entity`), authorized in the admin worker against the
  authenticated character's roles; the simulation marks the entity only if it
  is an NPC it holds. Marks are global per NPC, as KO's flag is: at most 32 at
  once and 8 per session, with no unmark (KO has none). A mark lasts for the
  NPC's life, as KO's does (only the constructor `00417873` clears it, and the
  dispatcher turns a dead NPC's state 0 into 1 on the same object): when an
  n3e NPC takes a new entity id (the encounter reset when a damaged NPC's
  health rises in its step, as when it is healed at home, and respawn) the mark moves to the new id. It ends
  only when the NPC leaves the simulation (a temporary NPC expiring) or the
  server stops. Every World snapshot of a session whose `server.inspect` lease is
  current carries `World.traces` for the marked NPCs among the entities it
  already holds (n3e's interest area is KO's 3x3 rule). The lease comes from the
  existing authority read (every 2 ticks, off the tick, 500 ms, fail-closed), so
  a revocation stops reports within one lease, independent of the client's
  projection (D-146). The state is the engine's NPC behavior word
  (`Entity.behavior`) as of the snapshot. The package's info line may carry one
  state placeholder, `{state}` or `{state:FALLBACK}`, which shows the last
  reported state of a traced NPC and otherwise the package's FALLBACK (the
  engine default is empty; the KO table writes `{state:0}`, KO's initial byte,
  so no KO value is in engine code); the client keeps the last state until the
  entity leaves its snapshot, as KO keeps `+0x7c0`.
- **Considered:** KO's numbers in engine code (a KO numbering in the engine,
  against the package boundary); a package map from behaviors to KO numbers for
  the KO table (each correspondence rests on source names, n3e's `recover` has
  none, and the choice changes what an operator reads: parked as PQ-187, blocked
  on the user; the user chose the words, D-151); per-session marks seen only by their owner (narrower than KO,
  where every operator in range sees a marked NPC); a report on each change
  instead of each snapshot (KO reports each step, mostly the state at the
  step's start, not each change); gating reports on the projected Registry
  (the client's view of its own roles, refreshed only per D-146; the server
  leases the capability itself).
- **Recorded in:** [CONTRACTS](CONTRACTS.md) C-05 and "Package input map",
  [content/nameplates.md](../../content/nameplates.md), PQ-186. Evidence:
  pq-186.

## D-148 — 2026-10-10 KO's +pursue NPC snapshot stays a server-side record; inspect does not return it

KO's operator command `+pursue <id>` (Ebenezer `0042c1ba`) sends AI sub-opcode
`0x0e` with the NPC's ID. The AI server (`004074d7`) answers on the same
connection with the NPC's state byte, two values the log labels `HP`, and its
position. Ebenezer `0040b24e` then writes four lines comparing those values
with its own copy of the NPC. The lines go to its region log file (the `CFile`
at `+0x4c69c`, opened as `RegionLog_%d_%d_%d.txt` by `0041c15f`), not to a
console and not to a client. Neither packet names the operator.

- **Selected:** n3e's `inspect` admin operation is unchanged (it returns the
  latest world revision) and returns no NPC snapshot, because KO shows the
  snapshot to no one and BINARY-POLICY allows a deviation only for a logic bug
  or exploit. KO's `+pursue` maps onto a server-side record. A `server.inspect`
  admin operation, authorized in the admin worker against the authenticated
  character as `trace` is, makes the server write one log line. The line holds
  the NPC's entity id, name, behavior, health, maximum health and position from
  the simulation and is written outside the tick. The operator's result
  carries a status only (PQ-189). n3e has one authoritative simulation, so KO's
  AI-server-versus-game-server comparison has a single side.
- **Considered:** returning the snapshot in the `AdminResult` to the requesting
  holder (an operator-facing addition KO lacks, with no bug or exploit behind
  it; the user can request it); folding NPC state into `inspect` (its result is
  the world revision; this would change C-05's operation for behavior KO does
  not have); leaving `+pursue` unmapped (it is one of KO's operator commands,
  PQ-089's set).
- **Recorded in:** BINARY-INDEX KOF-0033,
  FEATURES KOF-0033,
  PQ-188, PQ-189. Evidence:
  pq-188.

## D-149 — 2026-10-10 Main moves only by a gated item merge, enforced by a git pre-push hook

PQ-123's review found that `tools/parity/guard.py` let any commit with a gate
marker move `main`, so a marker on a branch commit (as PQ-123's first attempt
left on `c8c7ee4`) would have let unreviewed work be pushed. The fix is a rule
that a marked commit moves `main` only as a parity item merge: a two-parent merge
whose first parent is the `main` the push replaces and whose second parent is a
`phase/pq-*` branch tip.

Attempts 1 and 2 of PQ-125 tried to enforce that rule inside the Claude Code Bash
hook by reading the command line and classifying the `git push`. Three review
rounds on attempt 1 and three on attempt 2 each found another shell shape the
text reader split differently from bash (a subcommand built from a variable, a
`!` alias, a `( cd … )` subshell, a `case`/`esac` or here-document inside a
substitution, a renamed git binary), so the reader kept growing without ever
being provably complete. On 2026-10-10 the user redirected the work (quoted
verbatim in the PQ-125 note): **"sure, go for it"** to the recommendation to add
a git pre-push hook, and **"if #1 addresses the issue then let's go with that and
keep things simple"** — so the merge-only check moves into git, and the text
parser is dropped. This is the one sanctioned change to the guard hook, under
D-131's exception for an explicit user request; `.claude/settings.json`, its hook
timeout and the permission rules are unchanged.

- **Selected: the check lives in git, in `tools/parity/pre-push`.**
  - git runs the hook for every `git push` from this clone, with `<remote>
    <url>` as arguments and one line per ref update on stdin (`<local ref>
    <local sha> <remote ref> <remote sha>`). It checks the ref update git
    reports, not the command text. It is not run for plumbing that updates a
    remote's refs directly (`git send-pack`, `git http-push`) or when the push
    skips it; "Limits" lists the known routes.
  - It parses each stdin line from the right (`rsplit(" ", 3)`): git writes the
    local-ref field as the source the user typed when that is an object
    expression, which can hold spaces (`HEAD@{0 seconds ago}`). A non-empty line
    that does not give four fields, with hex object names and a remote ref, and
    undecodable input refuse the push. Review round 1 of attempt 3 found that the
    first version split on whitespace and skipped any line without exactly four
    fields, so `git push origin 'HEAD@{0 seconds ago}:main'` of an ungated commit
    moved a temporary remote's `main`; the right-hand parse fixes it, and
    `gate_check.py` tests the spaced source and the malformed lines.
  - For each stdin line whose remote ref is `refs/heads/main` the hook refuses
    unless **all** hold: the local sha is not the zero sha (a deletion is
    refused); a gate marker `build/parity/gate/<local sha>.ok` exists; the commit
    has exactly two parents; the first parent equals the `<remote sha>` git
    itself passes (the `main` the push replaces — no `ls-remote`, no URL
    resolution, no tracking ref); and the second parent is the tip of a branch
    named `phase/pq-<digits>[-slug]`, local (`refs/heads/`) or the remote's
    tracking ref (`refs/remotes/<remote>/`). Lines for other refs pass. Any
    error, unreadable state or malformed stdin refuses.
  - **Installation.** `tools/parity/install-hooks.sh` symlinks
    `.git/hooks/pre-push` to the tracked script (preferred over `core.hooksPath`
    so nothing else is redirected) and refuses rather than clobber an existing,
    different pre-push hook. A fresh clone runs it once. `gate_check.py` fails
    when the hook is not installed in the clone, or its target is missing or not
    executable (git silently skips such a hook).
- **Selected: the Bash guard (`tools/parity/guard.py`) is simplified to a
  tripwire.** It returns to the pre-PQ-125 base, plus the refusals below and a
  fail-closed catch-all, and reads the command line with a plain split. It refuses a push to `main` of a
  commit without a gate marker, a push combined with other git state changes,
  force / `--force-with-lease` / delete / `--all` / `--mirror` / `--prune`
  pushes, `git add --force`, git writes under `ref/`, submodule `--remote`,
  hand-written gate markers and Wine outside the rig. New in PQ-125, it refuses,
  when typed plainly, some known ways of skipping the pre-push hook (not all;
  see "Limits"):
  - `git send-pack` and `git http-push`, as subcommands or as the dashed
    programs `git-send-pack` / `git-http-push` by path (review round 2 of
    attempt 3: `git send-pack <remote> HEAD:refs/heads/main` moved a temporary
    remote's `main` with the hook installed and never ran it);
  - `git push --no-verify` and every prefix of it from `--no-v` (git accepts
    the unambiguous abbreviations `--no-veri` and `--no-verif`, which skip the
    hook; shorter ones are ambiguous errors);
  - `git -c` / `--config-env` on a push (either could set `core.hooksPath` and
    so skip the pre-push hook);
  - a push line that sets `GIT_CONFIG*` (`GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`,
    `GIT_CONFIG_VALUE_*`, `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_GLOBAL`,
    `GIT_CONFIG`, ...), `HOME` or `XDG_CONFIG_HOME`, as a prefix, through `env`
    or anywhere else in the line: each but legacy `GIT_CONFIG` moved git's hooks
    path for one command in a probe with git 2.55 (review round 2 of attempt 3:
    `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x
    git push ...` was let through for a gated non-merge, and nothing persisted
    for `gate_check.py` to catch).

  Any uncaught exception exits 2 (fail closed); its git calls are fast and
  local, so the 7 s budget of the parser attempts is gone.
- **Considered:**
  - Keeping the bash-text reader (attempts 1–2). Dropped by the user for
    simplicity once a git-side check was available; a text reader of shell can
    never be provably complete, and each review round found another shape.
  - `core.hooksPath` instead of a symlink. A symlink changes only `pre-push` and
    leaves any other local hooks alone.
  - Having the hook read the remote with `ls-remote`. Unnecessary and slower:
    git already passes the remote sha the push would replace, and trusting it is
    exactly right for "the main this push replaces".
- **Limits (disclosed, not hidden — this is a best-effort tripwire plus an
  in-clone git hook, not a complete barrier):**
  - **Known routes that skip the pre-push hook include** the following; the list
    is not complete:
    - plumbing that updates a remote's refs without the hook: `git send-pack`
      and `git http-push` (refused by the tripwire when typed plainly, as
      subcommands or as `git-send-pack` / `git-http-push` by path; not when
      reached through an alias or a shape the tripwire mis-reads);
    - git configuration that sets `core.hooksPath` for one command: `git -c` /
      `--config-env`, or the environment (`GIT_CONFIG_COUNT` /
      `GIT_CONFIG_KEY_*` / `GIT_CONFIG_VALUE_*`, `GIT_CONFIG_PARAMETERS`,
      `GIT_CONFIG_GLOBAL`, `HOME`, `XDG_CONFIG_HOME`; refused by the tripwire on
      a push line typed plainly);
    - a persistent `core.hooksPath` written by `git config` (repository, global
      or system): `gate_check.py` fails at its next run, but pushes before then
      are unchecked;
    - `git push --no-verify` and its abbreviations `--no-verif` / `--no-veri`
      (refused by the tripwire when typed plainly);
    - editing or deleting the hook file or its symlink;
    - git run under another name (a symlink or copy), which the tripwire does
      not read, carrying one of the routes above;
    - a push from another clone or tool (`gh`, the GitHub API, a CI job, or
      `GIT_DIR` pointing at another repository);
    - any shape the tripwire mis-reads (below) that carries one of these.
  - The hook checks the merge's **parents, not its tree**: an amended trial
    merge or one built with `git commit-tree`, if gated, passes. Anyone can
    create a local `phase/pq-*` branch at any commit, so the second-parent rule
    proves the shape of the loop's merge, not that it was reviewed. Review stays
    procedural.
  - The Bash guard reads the line with a plain split, so **shapes it mis-splits
    are a disclosed class of limit**, not a closed one: a subcommand built from a
    variable, an alias, a here-document, a `case`/`esac`, a renamed git binary,
    and the like beat the tripwire. A `git push` they hide is still checked by
    the pre-push hook, unless the same line also skips the hook (above). Do not claim
    the tripwire refuses every push or that a mis-split construct cannot hide a
    command.
  - The hook trusts git's pre-push stdin format and the remote sha git passes.
    A future git that changed the format would most likely give lines the
    parse rejects, which refuse rather than pass; that is an expectation, not
    something tested.
  - The real barrier outside any one clone is a git-side protection on the host
    (branch protection). PQ-191 delivered the in-clone pre-push hook as the
    first form of it; host-side protection remains the long-term backstop.
- **Recorded in:** LOOP "Gates" and the guard list, the
  parity agent definitions and skill, `tools/parity/pre-push`,
  `tools/parity/install-hooks.sh`, `tools/parity/guard.py`,
  `tools/parity/gate_check.py` (`guard_push`, `hook_installed`), which also
  shows two of the known routes for real (`git send-pack` moving `main` without
  the hook; `GIT_CONFIG_*` moving the hooks path). Evidence:
  pq-125.

## D-150 — 2026-10-10 The server marks an operator's chat lines from the server.inspect lease; the package colours them

KO's chat handler (`KnightOnLine.exe` `005cac80`) colours a received line
`0xffcd9bff` (`005cb2f5`) when its type is not 7 and either the local player's
authority byte is 0 and the line is its own, or the sender, found in the
other-player map, has authority byte 0 (`005cb27d`–`005cb2e9`). The colour goes
to the chat window (`00543410`) and the balloon (`00456d90`). So KO shows every
player that a sender is an operator. The user agreed on 2026-10-10 ("Yes, let's
do the same", INBOX, PQ-178) and did not name a capability; the loop proposed
`server.inspect` and the user did not object.

- **Selected:** the capability that marks an operator is `server.inspect`, the
  one that already gates the operator NPC info line (PQ-177) and the NPC state
  trace (PQ-186), so one role covers KO's authority-0 presentation. The server
  sets `Chat.from_operator` from the sender's `server.inspect` lease (the
  existing off-tick authority read, `turbo::read`, every 2 ticks, valid 500 ms,
  never restored by an older generation), for every receiver of a local line,
  the sender's own copy included. A private line is marked only when the sender
  is in the recipient's interest area, as KO finds the sender in the
  other-player map. A request's value is ignored, so the client never asserts
  a role, and the client never infers one: it draws a marked line in the
  package's `names.operator_chat` colour (input table `N3I8`; the KO table
  writes `0xCD9BFF`) and every other line as before. Revoking `server.inspect`
  with `n3e-server role revoke` now waits, as revoking `movement.turbo` does,
  until the simulation has applied it, so the operator's next line is unmarked;
  a stale session (another generation) is never applied a read and never marked.
- **Considered:** a separate capability for the chat mark (finer, but the user
  named none, and KO uses one authority byte for both); sending each player's
  role with the entity, as KO's user-in does, and letting the client colour
  (that discloses the role whether or not the operator speaks and moves the
  decision into the client); marking from the projected `Registry` (the
  client's own view, refreshed only per D-146); a fixed engine colour (KO data
  in engine code).
- **Limits:** n3e has no balloons, so only the chat line is coloured (balloons
  are PQ-168 and PQ-079's). n3e has no type-7 (`N3_CHAT_PUBLIC` in the source)
  channel; when notices are added under PQ-079 they must not take the mark.
  Whether KO's separate private-message window (`+0x13c`, `0054fb10`) shows the
  colour was not traced. The cross-nation scramble exemption is PQ-180.
- **Recorded in:** [CONTRACTS](CONTRACTS.md) C-05 and "Package input map",
  protocol, PQ-178.
  Evidence: pq-178.

## D-151 — 2026-10-10 The traced NPC's TYPE keeps n3e's behavior words, not KO's state numbers

KO's operator NPC info line draws `TYPE(%d)` from the NPC byte `+0x7c0`
(client `00465070`, PQ-177), which opcode `0x5d` sets. Ebenezer `0040b4d4`
forwards that opcode from the AI server, and the value is the AI's raw state
byte `+0x2b4` of an NPC an operator marked (`+actpursue`, `+0xc54`). The AI
dispatcher `0042b86c` switches on that byte; only the routines for states 1, 2,
5, 6, 8, 10, 11, 12, 13, 16 and 17, and `00421f66` (which also reports 11),
test the mark and send a report. The state-7 routine `004184cb` (the source's
`NPC_TRACING`) has no mark test and sends no state report (no sub-opcode
`0x0f`; the packet it does send through `00422bc1`, led by the bytes 4
and 2 with position and speed, carries no state), and neither do the
routines for 18 and 19, and 0 is never reported (it is the client's initial byte). So while a KO NPC chases, its
line keeps the number of its last reported step. Evidence: PQ-186 audit runs
01–03 on `AI Server-official.exe` (SHA256 `8715084f…0435`), label binary
(pq-186, "The reports and states 16
and 17", "Where the reports go" and "Review fix (attempt 1, round 1)"). n3e sends the engine's NPC behavior word instead
(D-147), so a traced NPC that is chasing reads `TYPE(chase)`.

The user chose on 2026-10-10 (in chat, recorded in INBOX and the PQ-187 note):
"For question 3 let's go with Keep words, makes much more sense."

- **Selected:** the KO package keeps n3e's behavior words (`idle`, `chase`,
  `attack`, `return`, `recover`, `dead`) on the traced NPC's `TYPE` line, with
  `{state:0}` (KO's initial byte) as its fallback for an NPC no report has
  reached. The line is staff-only: it is drawn only while the server projects
  `server.inspect` (D-146), and the server sends traces only to sessions it
  leases that capability (D-147). PQ-187 closes as a recorded deviation. This
  is a user-directed presentation difference, not a BINARY-POLICY correction:
  no KO logic bug or exploit is claimed, and KO's state byte remains what the
  binary shows.
- **Considered:** a package map from behavior words to KO's numbers for the KO
  table. Each correspondence rests on source names only (`NPC_STANDING` 5,
  `NPC_FIGHTING` 8, `NPC_BACK` 10; label source-only), n3e's `recover` has no
  KO counterpart, and KO's chase shows the last reported number rather than a
  chase state, which a per-snapshot word map cannot reproduce. KO's numbers in
  engine code were already rejected by D-147 (package boundary).
- **Reversal:** needs no server, protocol or simulation change and no KO number
  in engine code, because the server already sends the behavior word. The KO
  table would carry a map from words to its text. The input-table format has no
  such field today (`names.npc_info` is colour and text, introduced by N3I7 and carried
  forward by N3I8), so a reversal
  adds one optional, game-neutral field that the cooker
  (`tools/assetc/input_map.py`) validates and the client's `npc_info_line`
  applies; the KO numbers stay package data.
- **Recorded in:** BINARY-POLICY "Disagreements and
  correction candidates", [content/nameplates.md](../../content/nameplates.md),
  PARITY, PQ-187. Evidence:
  pq-187.

## D-152 — 2026-10-10 The server withholds an operator from sessions without a current server.inspect lease

KO's client does not draw another player whose authority byte is 0 unless its
user-in u32 `+0x7e4` is 5 or more, and never one with 250 (`KnightOnLine.exe`
`00470d70`); an operator gets no arrival effect (`005ccc0b`), no minimap point
(`005dad78`) and no Z target (`00471f53`) (PQ-179 runs 02 and 06, binary). KO's
server does not hide operators. On the paths PQ-185 read (Ebenezer `004954d6`, `0049c286`,
`00423a38`, `00494beb`, `0049cd21`; runs 06, 08, 09 and 10, binary), every
in-game user of the cells gets an operator's records, and any client can ask
for any user's record by ID. A modified client therefore sees every operator
in its cells, and any operator's record by ID: a client-trust weakness
(BINARY-POLICY).
The user chose on 2026-10-10 (in chat; INBOX, PQ-184 note): "Yes, should be
hidden by default and yes we should have a capability like that."

- **Selected:** `server.inspect` both marks an operator as hidden and lets its
  holder see hidden actors, as it marks an operator's chat line (D-150) and
  gates the operator NPC views (D-146, D-147). KO uses one authority byte for all
  of these, and the user named no other capability. So operators see each other,
  and every session sees itself. The server decides each pair from the off-tick
  authority read the simulation already runs (`turbo::read`, every 2 ticks, valid
  500 ms, never restored by an older generation): an actor is hidden while its
  `server.inspect` lease is current, and while no read has been applied to its
  session; an observer sees hidden actors only while its own lease is current.
  The session's first read is taken before it joins, off the tick, so a login
  does not show an operator unless that read's 500 ms lease has lapsed before
  the simulation admits the session (then it is visible until the next read). A
  revocation (`n3e-server role revoke`, which returns once the simulation has
  applied it, D-150) or a lapsed lease makes the operator visible: once a session
  has had a read, a stalled read keeps no one hidden and lets no one see hidden
  actors. A grant hides the operator at the next read. The client is not told
  who is hidden and decides nothing.
- **What is withheld from an observer that may not see the operator:** its
  entity in `World.entities`, its id as another entity's `strike_target` or
  `cast_target` (zeroed in that observer's copy), presentation events with it as
  actor or target, and the name and entity lookups the observer makes. A
  private message to it is refused like one to an absent name, a party
  invitation is `unavailable`, a party removal by name answers as for an absent
  name (`not_member`) unless the operator is in the requester's own group (so a
  leader can still remove a hidden member), a friend addition is `unavailable`,
  friend presence reports it offline with character and entity 0, and a skill
  aimed at its entity id is `stale_target`. These name lookups ignore it in a
  case-folded match, so it makes no name ambiguous for that observer (a hidden
  member of the requester's own group still counts in a party removal). A
  private line it sends to such an observer is never marked (`from_operator`
  false), so the mark tells that observer neither its role nor whether it is in
  the observer's interest area.
- **What outlives a snapshot (PQ-184 attempt 2):** the server keeps
  presentation events for 40 ticks and an NPC keeps its last strike target
  until it strikes again, so withholding per snapshot is not enough. Each kept
  event carries two marks, one for its actor and one for its target, set when it
  is recorded if that party was withheld at the latest tick (or admitted
  withheld since), and at every tick while it is kept if that party is withheld
  then; a mark is never cleared. An observer
  whose lease is not current gets no marked event (the observer's own withheld
  part excepted), so an event stays withheld after the session leaves, takes a
  new entity id or is shown. A session admitted withheld is marked at its
  admission. Each tick, before any snapshot, a former id of a session withheld at
  the previous tick that no session now holds (it left or respawned under a new
  id) is cleared from every NPC's and player's strike and cast target. The
  retained state is the list of ids withheld now (at most one per session) and
  two marks per kept event (at most 128 events); the tick does no database I/O
  for it.
- **NPC AI (PQ-193):** KO's AI server skips an operator. It keeps the authority
  byte Ebenezer sends in its user-info packet (`0x65`, Ebenezer `004970cb`) at
  `+0xac` of its user record (AI `00405494`; `00406950` for the bulk list), and
  its find-enemy scan (`0041c21e`) passes over a user whose byte is 0 or 250,
  its attack routines (`0041de51`, `0041e628`) and tracing attack (`0041e9fd`)
  drop such a target, and its retarget on damage (`0041f715`) ignores such an
  attacker (PQ-193 runs 02–06 and 08, binary; the source checks 0 only). n3e
  maps this onto the same lease: an NPC neither picks nor keeps a session that
  `turbo::State::hidden` lists, in the policy AI and in the fixed melee AI. An
  NPC that is chasing or fighting a session when it becomes hidden drops it at
  its next tick and walks home, as n3e does for any lost target (KO's routines
  set the NPC standing, an existing difference in n3e's lost-target path);
  dropping it does not block it, so after a revocation or a lapsed lease the
  next scan can pick it again. A hidden session's strike on an NPC still lands,
  as in KO: the NPC's health falls and the damage counts in the contribution
  ledger, but the NPC does not turn on it. KO's fixed 30000 damage for an
  operator's basic attack on an NPC (AI `004430d8`) is not reproduced (queued as
  PQ-194; 2026-10-13: not copied at the user's choice, D-157). The tick reads only the in-memory lease.
- **What stays (deliberate, disclosed):** what the operator chooses to say or
  do towards a player still names it. Its private lines carry its name and
  entity id (unmarked, above). Its local lines go, as every local line does, to
  the sessions in its interest area with its name, entity id and operator mark
  (D-150), so receiving one shows that a hidden operator is nearby: inherent to
  local chat, and the operator chose to speak. The entity id gives no position
  through the lookups listed above, which check visibility. A party it invites a
  player to, or joins, lists it to the members (name, level, health, no position)
  and names it in their loot notices. `World.event_cursor` counts the events
  of the whole realm, withheld ones included, as it already counts events out
  of range: an observer sees a gap in the sequence, with no identity or
  position.
- **Considered:** separate capabilities for being hidden and for seeing hidden
  actors (finer, but the user named none and KO uses one byte); sending the role
  with the entity and letting the client hide, as KO does (the weakness above);
  filtering World snapshots only (the name and entity lookups would still answer
  for the operator); letting party members see each other (no KO basis, and the
  user tied seeing to a capability).
- **Limits:** since PQ-193 an NPC no longer turns on a hidden operator, but an
  NPC's health still falls when a hidden operator strikes it (an observer sees
  the health fall with no attacker in view, so someone within reach is fighting
  it); its damage also counts in the NPC's contribution ledger, so it lowers an
  ordinary contributor's experience share and can own the drop, as any
  contributor can.
  While a hidden operator's attack on an NPC awaits its durable commit, an
  observer's attack on that NPC answers `target_pending`, a direct reply that
  tells the observer someone is fighting it (no identity or position). An NPC
  strike already awaiting its durable commit when its target becomes hidden
  still completes. KO's `+0x7e4` ≥ 5 exception is KO's operator command
  `VIEW` (`0x29`/3 value 5); since PQ-192 a holder can show itself for its
  session with the admin operation `show` and hide again with `hide`
  ([D-153](#d-153--2026-10-10-a-serverinspect-holder-can-show-itself-to-ordinary-players-for-its-session-show-and-hide)). n3e has no stealthed actors yet; they
  arrive with magic type 9 (PQ-067), which must use this filter, and KO's
  half-alpha view of hidden hostile actors (`00458ef0`) comes with them. No 250
  tier exists (PQ-182), so KO's "never draw 250" has no counterpart. The
  operator's client is not told that it is hidden.
- **Recorded in:** [CONTRACTS](CONTRACTS.md) C-05,
  BINARY-POLICY,
  PQ-184. Evidence: pq-184.

## D-153 — 2026-10-10 A server.inspect holder can show itself to ordinary players for its session (`show` and `hide`)

KO has an operator "show me" switch (PQ-192 runs, `build/parity/binary/pq192/`,
binary). The client's GM command table holds the 21 commands that `0054eaf0`
loads from text IDs 9000–9020 (run 15), named `VISIBLE` … `PROGRAMLISTCHECK` in
Open-KO's `Texts_us.tbl` (local-asset). The command processor `0054e180` sends
`0x29`/3 with value 5 for index 14 (`VIEW`) and `0x29`/3 with value 1 for index 15
(`UNVIEW`), each only while the local player's `+0x4a8` is 0 and `+0x4ac` is
−1, the values `0046fa80` writes on the type-3 value-1 path; reading them as
"not transformed" is an inference (runs 01, 04, 11, 17). Ebenezer `004a8ad1` stores the value in
`+0x8864`, refuses value 5 unless the sender's authority byte is 0, and sends
the change to the cells (run 18). Each client's `0x29` handler `005d7720` stores
it at the actor's `+0x7e4` (`005d7b38`; for the local player also at `+0x7f4`),
and for values 5–99 does nothing more (run 01).
The draw loop `00470d70` then draws that operator (run 01). So `VIEW` shows an
operator to every client in its cells, and `UNVIEW` hides it again. Ebenezer's
user initializer `0048ff43` sets `+0x8864` to 1 (run 20). It is reached through
the thunk `00401a28`, whose only reference is the data at `00634a14` (runs 20,
21); that this runs at each connection is an inference from the source name
`CUser::Initialize`.

- **Selected:** two admin operations on the existing admin path, as `trace` and
  `record` (PQ-186, PQ-189). `show` withholds the holder no longer and `hide`
  restores the PQ-184 default. `administration::execute` authorizes the request
  off the tick against the authenticated character's roles and session
  generation (`server.inspect`; `denied` otherwise). The simulation applies it
  on the tick only to that live session generation, and only while its
  `server.inspect` lease is current (otherwise `denied`). The answer is `shown`
  or `hidden`. Like `trace`, the operation is read-only: no durable result, and
  a status lookup answers `unknown`. The tools terminal has the verbs `show` and
  `hide`.
- **State:** one flag per session in `turbo::State`, in memory only. A session
  starts hidden at every login, as KO's initializer `0048ff43` sets `+0x8864`
  to 1 (that it runs at each connection is the inference above). A read that finds no
  `server.inspect` (a revocation) clears the flag, so a regrant hides the
  operator again. A lapsed lease shows the operator anyway (D-152) and keeps the
  flag. The tick does no database I/O for it. The reset needs a read that
  observes the role gone: if `role revoke` fails its 6 s barrier, or a regrant
  commits before the simulation's next read, the flag survives to the regrant
  and the operator stays visible, as it chose (nothing leaks).
- **Seeing:** a shown operator still sees hidden actors. It keeps the capability,
  and `turbo::sees` looks only at the observer's lease.
- **Interplay:** while shown, the session is not in `turbo::State::hidden`, so
  every PQ-184 filter treats it as an ordinary player. It is in other sessions'
  World entities and lookups, and its private lines carry the D-150 mark. NPCs may
  pick it, chase it and turn on it (PQ-193). Events it made while hidden stay
  withheld for their 40 ticks. `hide` marks the presentation history at once,
  as a hidden login does, and the next tick's withhold step marks every kept
  event naming it. So after a `hide` its events from the shown period are
  withheld too, and an NPC chasing it drops it at its next tick.
- **Considered:** a client-held flag, as KO's client reads `+0x7e4` (the
  client-trust weakness of D-152); persisting the choice (KO's resets, and the
  user's answer says hidden "by default"); a separate capability (the user named
  none); KO's command names `VIEW` and `UNVIEW` as operation names (`show` and
  `hide` say what they do in n3e; the evidence maps them).
- **Not reproduced (gaps):**
  - KO's client still gives a shown operator no minimap point, Z target, arrival
    effect or selection. Those tests read the authority byte, and none of them
    reads `+0x7e4`: `005dad78`, `00471f53`, `005ccc0b` and `005d9d58` (run 23;
    PQ-179 run 02, PQ-147). Of the listed instructions with displacement `0x7e4`
    (run 03), only the draw loop reads another player's value; the rest are
    writers, the my-info handler's copy of the local player's own value
    (`005ca8e3`), and a string field of another structure (runs 04, 22). Three
    unlisted hits outside any defined function were not read. n3e entities carry
    no role, so a shown operator gets all four, as a player does. Queued as
    PQ-195, blocked on the user.
  - KO's `VISIBLE` and `INVISIBLE` commands (`0x29`/5 with 0 and 255) store
    nothing in Ebenezer, and the client's `0x29` handler has no branch for
    subtype 5 (runs 01, 18). Nothing observable to map.
  - In KO any other write of `+0x8864` replaces the value 5. Run 19 found the
    writers `0048ff43`, `004b4365`, `004b4582`, `004b97fe`, `004c4546` (each
    stores 1), `004c1294` (stores 4) and `0046a0a4` (stores its argument, whose
    range was not read; the catalog reads it as the transformation). The writes
    of 1 or 4 end `VIEW` (run 20). n3e has none of these paths.
  - KO accepts `UNVIEW` (value 1, the normal-size value) from any user. n3e's
    `hide` is for holders only: a non-holder is never hidden.
- **Recorded in:** [CONTRACTS](CONTRACTS.md) C-05,
  BINARY-POLICY,
  D-152, PQ-192. Evidence: pq-192.

## D-154 — 2026-10-10 No preset limited-operator tier: KO's authority 250 is not reproduced, capabilities stay individually granted

KO has a second operator value, authority 250 (source name
`AUTHORITY_LIMITED_MANAGER`), held in the same byte as the role and the
sanctions (Ebenezer user data `+0x71`, AI user `+0xac`, client actor
`+0x4a4`). The user chose on 2026-10-10 (in chat, recorded in INBOX and the
PQ-182 note): "Allow for any mix."

- **Selected:** n3e reproduces no preset tier. Roles stay one row per
  capability in `character_roles`, granted and revoked one at a time
  (`n3e-server role grant|revoke ACCOUNT CHARACTER_ID REALM CAPABILITY`, which
  refuses a name outside `administration::CAPS`), so an operator holds any
  subset of `world.edit`, `config.edit`, `entity.spawn`, `server.inspect` and
  `movement.turbo`. Every privileged operation is checked on the server against
  the authenticated character's capabilities (C-05); the client reads the
  projection for presentation only. PQ-182 closes as a recorded deviation.
  This is a user-directed product difference, not a BINARY-POLICY correction:
  no KO logic bug or exploit is certified. Where a KO 250 limit is held only
  by its client (rows below), that is a legacy trust weakness n3e would not
  copy in any case.
- **KO's authority 250, as read for this decision.** Every row was re-read in
  PQ-182 attempt 3 (rows C1–C9, S1–S10 and A1–A2 in headless runs 07 to 11
  and a disassembly scan, row D1 from the reference database export in run 12,
  evidence).
  The scan lists every compare with the immediate `0xfa` in the three
  executables; each one that reads an authority byte (client 19, Ebenezer 14,
  AI 7) is in a row, with its branch followed to where it leads. Rows S1 and
  S4–S6 come from tests that never name 250. A row states what the path read
  does and nothing about paths not read. Labels are binary unless stated;
  names taken from earlier records are marked as theirs. "none" means n3e has
  no counterpart.

  | Row | What KO does for 250 | Where (label) | n3e |
  |---|---|---|---|
  | C1 | Turbo: while the local player's byte is 0 or 250, the input handler sets `+0xb00` from the key state, clearing it while `+0x7f4` ≥ 5; for other values it skips the block (`005c6d6d`–`005c6d7d`) | C `005c6990` | `movement.turbo`, validated on the server against the authenticated character and leased to the simulation (CONTRACTS "Turbo"; the remainder is PQ-041) |
  | C2 | In the local move check, seven tests of the mover's own byte (`00468e14`, `004699be`, `00469a40`, `00469d55`, `0046a220`, `0046a2f4`, `0046a396`) take a 0 or 250 mover past a `return 1` (blocked) path; its first blocked return (the slot `+0x44` test at `00468df2` → `00468df9`) has none. What each path tests (other characters, shapes, distance and facing, slot `+0x48`, height step) is PQ-179's reading. The turn-when-blocked exemption tests 0 only (`00466d60`, `0046711a`) | C `00468ad0`, `00466d60` | none yet; a server-solver capability is PQ-183 (ready), grantable on its own |
  | C3 | In one loop of the same check another player with 0 or 250 is skipped (`00469e14`), so it is no obstacle there; the other loops skip 0 only (PQ-179) | C `00468ad0` | none yet; operators not being obstacles is in PQ-183 |
  | C4 | The chat sender jumps past the send when the local byte is 250 (`005c77ad` → `005c7a00`) | C `005c7730` | none: n3e capabilities only grant, never restrict, so an operator chats as any player |
  | C5 | For a local 250 the private-chat partner routine shows text 7635 and returns (`005c7a60`), the party invitation does nothing (`005c7e2b`) and the trade request returns false (`005d6d05`); the trade command `0054cc30` is one of the six command groups of row C7. Ebenezer's handlers for these requests read no `+0x71` (row S1) | C `005c7a40`, `005c7df0`, `005d6cc0` | none: an operator whispers and invites as any player (n3e has no trade, refusal toggle or mute: GAPS "Trade, upgrade, exchange, destroy", "Chat channels", "Moderation") |
  | C6 | The client hostility test `006164c0(a, b)` returns false when `a` has 250 (`006164e7`); `a` is the character asking (the mover in the move check, `00468e83`, `0046913a`, `0046957e`; the other callers per PQ-179), so a 250 asking finds no hostile character. Ebenezer's counterparts are rows S3 and S10, the AI server's row A2 | C `006164c0` | none: n3e has no PvP or hostility matrix (GAPS "PvP and hostility"), and no capability restricts combat |
  | C7 | The chat-command parser skips six command groups for a local 250 (`0054be20` → `0054bf72`, past `0054cc30`, `0054d690`, `0054d100`, `0054da60`, `0054df70` and `0054dc70`), and lets it use only index 1 of `0054c4d0` (`0054c545`) and indexes 8, 13, 17, 18 and 19 of the GM table `0054e180` (`0054e20f`); Open-KO's `Texts_us.tbl` names them `Town` and `ARREST`, `CUTOFF`, `SUMMONUSER`, `ATTACKDISABLE`, `ATTAKCENABLE` (local-asset). Ebenezer's side of the six groups and of the other indexes was not read (PQ-197) | C `0054ba10`, `0054c4d0`, `0054e180` | the subset follows from the capabilities granted; n3e has no per-capability limit on ordinary player commands |
  | C8 | The draw loop never draws another player with 250 (`00470eaa`); one with 0 is drawn only while its `+0x7e4` ≥ 5 (`00470e94`–`00470ea4`) | C `00470d70` | no equivalent: a `server.inspect` holder is withheld from sessions without a current lease and can `show` itself (D-152, D-153); a character without `server.inspect` is drawn as any player |
  | C9 | Z's nearest-enemy search skips another player with 0 or 250 (`00471f53`, compare at `00471f61`) | C `00471f10` | none for 250: a character without `server.inspect`, or a shown holder, is a Z target as any player (shown operators: PQ-195, blocked on the user) |
  | S1 | The partner, party and trade handlers (PQ-185's names) and their direct callees read no `+0x71`; the chat handler compares it only with 11 and 0 (row S4) | S `004ada30`, `004a99e3`, `004a9d1e`, `004ab6a3`, `004abb29`, `004989a8` | n3e checks every request on the server; no capability restricts these (C4, C5) |
  | S2 | The operator packet handler goes on for a sender with 0 or 250 (`004b1047`–`004b1050`) and returns (`004b1484`) for any other, so a 250 reaches every `0x40` subcommand | S `004b1022` | each admin operation names its own capability: `publish`/`revert` `world.edit`, `spawn` `entity.spawn`, `inspect`/`trace`/`record`/`show`/`hide` `server.inspect`. KO's `0x40` moderation subcommands (among them forbid-connect, mute, unmute, go-to, cut-off, summon and the attack toggles) have no n3e operation (GAPS "Moderation", KOF-0059; GM command parity, PQ-089) |
  | S3 | The hostility check `004c084a(attacker, target)` returns 0, not hostile, when the target's `+0x71` is 0 or 250 (`004c0877`–`004c0887` → `004c08c3`) and reads no other `+0x71`. The melee handler passes (attacker, target) (`00496419`–`0049641f`) and compares the attacker's byte only with 12 (`00496292`), so on the melee path read Ebenezer does not test a 250 attacker (callees other than `004c084a` not read). The magic handler refuses a 250 caster before it reaches its own call of `004c084a` (`00463904`; row S10) | S `004c084a`, `00496169` | none: n3e has no PvP or hostility matrix (GAPS "PvP and hostility") |
  | S4 | Chat: a sender with 11 (mute) is dropped (`00498a30`). A `+` line runs as an operator command (`004012d5` → `0042c1ba`) only for a sender with 0 while the flag `[+0x8748]+0x4c825` is 1, or for any sender while it is 2 (`00498a83`–`00498ab6`); otherwise it goes on as an ordinary line (`00498ab8`). Types 7 and `0x11` are dropped unless the sender has 0 (`00498ad6`) | S `004989a8` | operator actions are admin operations checked against the authenticated character's capability on every request, with no realm flag that opens them to every player; n3e has no type-7 channel (GAPS "Chat channels") |
  | S5 | Movement: when a move exceeds the distance limit (`00494ea1`), the counter, the `Speed Hack Kickout` kick (counter ≥ 10) and the `long distance Hack check` position reset (`0049b712`) apply only to a mover with 1 or 10–19 while the flag is not 2 (`00494eb3`–`00494ed9`); any other mover, 0 and 250 included, goes on (`00494fc8`). The handler's other checks apply to every mover (PQ-185) | S `00494beb` | none: n3e's server movement solver checks every mover alike; an exemption would be a server-solver capability (PQ-183) |
  | S6 | Rules for 0 only, so a 250 is a player there: cancelling another user's market-board entry (`004b84ac`, `004b84e4`; PQ-185's name), and the NPC state trace `0x5d`, which `0040b4d4` sends through `0041e2d8` with the flag that makes `0041e454` skip users whose `+0x71` is not 0 (`0041e515`) | S `004b845c`, `0040b4d4`, `0041e454` | n3e has no market board (GAPS "Stalls, rental, mall, coupons, premium, tax"); the trace is a `server.inspect` admin operation (D-147) |
  | S7 | Packet `0x1e` (dispatcher case at `00490aa4`): while the flag is 1, a sender with 0 or 250 reaches `0049b712` (the routine row S5 uses for its position reset) and any other is ignored (`00490aaf`–`00490ab9`); while the flag is 2 every sender reaches it; other flag values ignore it | S `00490919` | none: n3e has no client-requested position change; characters move on the server, and the operator warp to an NPC is PQ-190 |
  | S8 | Room routines (investigation D's rooms and challenges; what each path means is inference): `00486c20` gives −1 to a user with 0 or 250 (`00486cbc`); `00486ecb` admits one through `00485f9e(…, 1)` without `00482a31`'s check (`00486fee`, on the path where the room's status is not 2 and its count at most 86); `004843ee` returns 1 for one before its `+0x62` checks (`00484404`); `00482d7e` sends `0x62`/2 only for others (`00482db6`); `00483ed2`'s subcommand 1 returns for one (`00483f3e`, on the path where the room's `+0xa` is 0 and the user's `+0x89da` is 1); `00484646` sends one the `0x62`/10 record that users with `+0x89d8` = 0 get (`00484745`); `00484d00` returns for one (`00484dd0`, on the path where its second argument is 0) | S as listed | none: n3e has no rooms or challenges (GAPS "War, siege, challenge, arena, nation events, seasonal broadcasts") |
  | S9 | Zone counts: `00437c1a` counts a zone's users other than 0 or 250 (`00437c54`); `00437d3a` gives a zone item, logged `Give Zone Item`, to each such user (`00437d91`); `00435cba` returns 1 only when zone 55 holds a user other than 0 or 250 not in state 3 (`00435d2b`) | S `00437c1a`, `00437d3a`, `00435cba` | none: n3e has no zone head counts or zone item gifts (GAPS "Event-script engine", "War, siege, challenge, arena, nation events, seasonal broadcasts") |
  | S10 | Magic: the magic handler refuses every magic packet from a 250 caster (not a 0), as it does for a caster whose `+0x89d6` is 100 or 2 (investigation F's room status): `00463269` jumps to `00463156`, which calls `004024aa` → `0046e707` (builds `0x31`/4, MAGIC_FAIL in source naming, with code −103, sends it and sets `+0xc` to 1) and returns (`0046459a`), before the zone-48 tile checks (`00463273`), the magic table lookup (`00463334` → `0046f95e`) and the subcommand tests (from `004633a1`). Every path of a user caster that the earlier checks do not end passes `00463269` | S `004630a6` (`00463269` → `00463156`), `0046e707` | none: n3e applies no authority-based refusal to casts; no capability restricts combat (C6, A2) |
  | A1 | NPCs skip a user with 0 or 250 in six AI routines (`0041c43d`, `0041dfe5`, `0041e729`, `0041eab1`, `0041f880`, `00428687`); in `0041de51` and `0041e628` the NPC then calls `00417cad` (PQ-193: drops its target) and takes state 5 (`0041e481`, `0041e780`; what each routine is: PQ-193) | AI `0041c21e`, `0041de51`, `0041e628`, `0041e9fd`, `0041f715`, `004285d0` | NPCs skip a withheld session (PQ-193), so a hidden `server.inspect` holder, not any other mix |
  | A2 | A user's damage to an NPC is set to 10000 while `[+4]+0x3201` is set, to 30000 for 0, and to 0 for 250 (`0044314e` → `00443152`) before the damage call (`00443165`); "basic attack" is PQ-193's name | AI `004430d8` | none: n3e applies ordinary damage to any character's strike; KO's operator damage overrides, this one included, are PQ-194 (blocked on the user; 2026-10-13: not copied at the user's choice, an audited `kill` command gated by `entity.kill` instead, D-157) |
  | D1 | Clan points leave out members with 0, 250 or 255 | reference DB `RANK_KNIGHTS` (local-asset; no binary references it) | none: n3e has no clan rankings (GAPS "Clans, alliance, clan war, king, rename, rankings, manner points") |

  Behaviours that test authority 0 only (for example `00466d60`, `005ccc0b`,
  `005dad78`, `005d9d58`, `00458ef0`, `004fc3cb` on the client, PQ-179) treat
  a 250 as a player; their n3e counterparts, where they exist, key on
  `server.inspect`.

- **Open gates (PQ-197):** Ebenezer's side of the six command groups and
  the command indexes of row C7; the addresses of investigation D's "Server:
  0 only" rules (notice chat, weather and time, online count, operator
  invisibility, zone-entry bypass, lever, transformation zone rules), which D
  records without them. Neither changes this decision: n3e builds no 250
  limits either way. Read in PQ-197 (2026-10-13), conclusion unchanged
  (evidence).
- **Limits of "any mix":** the mix is over today's five capabilities.
  `server.inspect` is coarse: it carries inspection (`inspect`, `trace`,
  `record`), hiding from ordinary players (D-152), the operator chat mark
  (D-150) and the show switch (D-153) together, so a role that inspects but
  stays visible, or is hidden without inspecting, cannot be built today.
  Splitting it would be a new decision. No restricting capability (a staff
  account that may not chat, trade or fight) exists; the user asked for none.
- **Considered:** a preset 250 role mapped onto a fixed capability set
  (rejected by the user's answer); KO's 250 limits as they are (several are
  held only by its client, a client-trust weakness; any limit n3e builds is
  server-enforced).
- **Reversal:** a preset could be added as a server-side grant of a named
  capability set (one transaction writing its rows), with any limits as
  server-checked capabilities on each request path; no client or protocol
  change is needed for the grant itself.
- **Recorded in:** BINARY-POLICY "Source/binary
  disagreements — 2026-09-24 parity deep dive" (the KOF-0059 row) and
  "Source/binary disagreements — 2026-10-10 client authority gates (PQ-179)"
  (the "Authority 250 limits" row), PARITY,
  GAPS, PQ-182. Evidence:
  pq-182.

## D-155 — 2026-10-13 Disposable test Postgres clusters run without fsync; the realm lease is unchanged

The PQ-201 merge gate (`324dbb5`) failed `make live` 39/46 on suites unrelated
to PQ-201: three realms exited with "admission expired; restart required" and
the test peers of three more suites read a closed connection
(`item_drops_db` failed on its own timing window, PQ-205). Every suite's
Postgres cluster shares the host's one filesystem (btrfs on dm-crypt), so a
commit's WAL flush waits behind every other cluster's fsyncs. In the gate run,
`item_drops_db`'s Postgres logged `COMMIT`s of 890, 1676, 1221 and 480 ms. A
probe cluster beside an unchanged `make live` (one autocommit `UPDATE` every
50 ms) measured commits up to 1586 ms with fsync on, and at most 104 ms with
fsync off in the same run. That run failed 42/46 with the same signatures, one
of them within seconds of the probe's two slowest commits. A lease renewal is
one `UPDATE` and its commit. Admission ends 2 s after the start of the last
successful renewal, and the next renewal starts 400 ms after the previous one
returns. So two consecutive renewals that take more than 1.6 s between them let
admission lapse. A session that sends a frame during the lapse is closed
("realm ownership unavailable", `network.rs`), and a single renewal over 1.6 s
ends the process (`main.rs`). The server behaved as designed (fail closed,
D-142, D-145).

- **Selected:** the live tier's disposable clusters are created with
  `POSTGRES_INITDB_ARGS=--no-sync --set fsync=off`: `DISPOSABLE_POSTGRES` in
  `tests/isolation.py` for `docker run`, and `DISPOSABLE_COMPOSE`, which adds
  `tests/compose-disposable.yaml`, for Compose. initdb skips its own sync and
  writes `fsync = off` into the cluster's `postgresql.conf`, which the image's
  init server and every restart read. A commit still writes its WAL to the
  kernel before it returns; it only stops waiting for the disk. Every outage a
  suite produces (pausing, stopping, restarting or killing Postgres, removing
  its container) keeps every acknowledged commit; only a host crash could lose
  one, and the cluster is discarded. `compose.yaml` and `deploy/` keep
  Postgres's defaults. No server code, timeout, lease, admission or retry
  changes.
- **Why not the server, here:** riding out a commit stall of that length
  without a lapse needs admission longer than the renewal interval plus the
  stall, so a longer lease, which lengthens how long a restart waits out a
  crashed owner (D-139). That is a production trade-off between stall
  tolerance and failover time, not a gate fix; PQ-206 asks it.
- **Considered:** `synchronous_commit = off` (a commit returns before its WAL
  is written, so a crashed Postgres could lose acknowledged commits, which
  production never does); a tmpfs data directory (a container restart loses
  the cluster, and `multiplayer` restarts Postgres); fewer suites at a time
  (slower gate, and still exposed to the host's other disk users); a longer
  lease or admission in production (above).
- **Recorded in:** `tests/isolation.py`, `tests/compose-disposable.yaml`,
  GAPS, PQ-205, PQ-206. Evidence:
  pq-205.

## D-156 — 2026-10-13 `make live` refuses a Postgres start without the fsync-off options; the KO stacks follow in PQ-208

D-155 made every live-tier cluster skip fsync through two helpers
(`DISPOSABLE_POSTGRES`, `DISPOSABLE_COMPOSE`), but nothing stopped a new or
edited suite from starting Postgres without them and bringing the shared-disk
commit stalls back, unnoticed until a gate failed on load timing again.

- **Selected:** a runtime check in the run's existing audit hook. Every Python
  process `make live` starts already loads `tests/live_reads/sitecustomize.py`
  (PQ-124). With `N3E_LIVE_DISPOSABLE=1`, which `tests/live.py` gives every
  process it starts, the hook checks each command the process starts (the
  `subprocess.Popen`, `os.exec`, `os.posix_spawn` and `os.system` audit events)
  with `tests/disposable.py` `problem()`. A `docker run` or `docker create` of a
  postgres image without `DISPOSABLE_POSTGRES` before the image, or a `docker
  compose up`, `create` or `run` without `DISPOSABLE_COMPOSE` as its first
  options, raises before the command runs, and is written to the run's record
  directory. Each simple command is read from its first `docker`,
  `docker-compose` or shell token, so a wrapper before it (`env -u X`, `A=B`,
  `timeout 60`, `exec`, `nice`) does not hide a start, and a shell's command
  line (after any option cluster holding `c`: `-c`, `-lc`, `-ec`) is split at
  its operators and checked the same way. `tests/live.py` prints an `UNDISPOSABLE` line for each and fails
  the run even when a suite caught the error. The check fails closed: an
  argument that looks like a postgres image counts as one, Compose files given
  another way are refused, an error while checking refuses and records the
  command, and a hook that cannot load `tests/disposable.py` refuses every
  command. `tests/disposable.py` owns the two option lists;
  `tests/isolation.py` re-exports them. `tools/parity/gate_check.py` checks the
  rule on 23 commands (13 refused) and end to end with a fake `docker` on
  `PATH`, in every tier.
- **Why runtime, not a scan of the sources:** the suites build their commands
  in several ways (lists spread from variables, images in variables, one
  `run()` helper per file), so a text scan would miss starts or flag ones that
  are fine. The audit event sees the command as it is actually started,
  whatever built it, and the hook is already in every process of the run.
- **Opt-in and standalone starts:** `make live-ko` also runs up to four suites at
  once, each with its own cluster on the same disk, so its stacks
  (`tests/ko_stack.py`) and `turbo_live` and `camera_legacy_live` should skip
  fsync too. Switching them needs a `make live-ko` run with the player's KO
  data, so `tests/live_ko.py` turned the check off for its run until PQ-208.
  **PQ-208 (2026-10-13):** `tests/ko_stack.py` and `camera_legacy_live` start
  their Compose stacks with `DISPOSABLE_COMPOSE` and `turbo_live` its `docker
  run` cluster with `DISPOSABLE_POSTGRES`; `tests/live_ko.py` no longer turns the
  check off, prints the same `UNDISPOSABLE` lines and fails its run on them
  (`LIVE_KO_FAIL`, `summary.json` `undisposable`), and `gate_check.py` checks
  that nothing in it turns the check off and that its verdict (`outcome()`)
  fails with exit 1 on one refusal record. `tests/life_graphical.py` and
  `tests/animation_graphical.py` are run by hand, one at a time, by no runner;
  they keep Postgres's defaults, since there is no parallel load for fsync to
  stall behind. The persistent play stacks (`tools/play-moradon`,
  `tools/play-ko-field`) keep player data and keep fsync on. `compose.yaml`
  and `deploy/` are unchanged.
- **Considered:** one start function in `tests/isolation.py` that every suite
  calls (a refactor of about 30 call sites, and still bypassable by a direct
  `docker run`, so it needs the same check anyway); a static scan in
  `gate_check.py` (above); checking each cluster's `SHOW fsync` after it starts
  (needs a hook into every suite's start sequence).
- **Limits:** only commands started from Python processes are seen; the native
  client and server start no containers, and no live-tier shell script runs
  Docker today. A command hidden in one argument other than a shell's command
  line (`env -S "docker run ..."`, a script file a shell runs), a shell
  variable holding the image or the command (`docker run $IMG` in a shell's
  command line is read as the literal `$IMG`), a docker binary under another
  name, and a start by a child process whose environment drops `PYTHONPATH` or
  `N3E_LIVE_DISPOSABLE` (the hook is not loaded there, or does not check) are
  not seen. Failing closed has a cost: an
  argument spelled like a postgres image counts as one, so `docker run --name
  postgres redis` and `docker run redis redis-cli -h postgres` are refused (give
  such a container another name). A Compose override listed after `DISPOSABLE_COMPOSE` could set
  `POSTGRES_INITDB_ARGS` back; none does.
- **Recorded in:** `tests/disposable.py`, `tests/live_reads/sitecustomize.py`,
  `tests/live.py`, `tests/live_ko.py`, `tests/ko_stack.py`,
  `tests/turbo_live.py`, `tests/camera_legacy_live.py`,
  `tools/parity/gate_check.py`, LOOP "Gates",
  GAPS, PQ-207, PQ-208.
  Evidence: pq-207,
  pq-208.

## D-157 — 2026-10-13 KO's operator damage overrides are not copied; an audited kill command gated by entity.kill replaces them

KO's AI server overrides the damage of a user's basic attack on an NPC (AI
`004430d8`, case `0x33` via `00405f1c`; PQ-193 run 05 and PQ-194 run 01,
binary): it takes the computed damage (`00443a34`), sets 10000 while the
realm-wide flag `[ESI+4]+0x3201` is set (`0044313a`), then 30000 when the
user's authority byte `+0xac` is 0 (`00443149`) and 0 when it is 250
(`00443152`), and passes the result to the ordinary damage routine `004204b4`.
The authority tests come after the flag, so they win. The user chose on
2026-10-13 (in the loop session; recorded in the PQ-194 note): do not copy
the overrides, record that as a deliberate deviation, and add instead an
explicit operator kill command for testing, a server-checked command gated by
a capability the server checks against the authenticated character, audited
like other operator commands.

- **Selected:** an operator's strike deals the ordinary damage of any strike
  (no fixed value, no 0 for any tier, no realm-wide flag). A new engine
  capability `entity.kill`, granted and revoked individually with `n3e-server
  role` like the others (PQ-182, D-154: any mix, no preset tier), allows the
  admin operation `kill` with `AdminRequest.entity` (field 10), as `trace` and
  `record` name their NPC. The tools terminal has the verb `kill [NPC_ID]`:
  with no id it sends the viewer's current target (the NPC the player
  selected), a client convenience the server checks exactly as any id.
- **Authority:** `administration::execute` authorizes the request off the tick
  against the authenticated, session-fenced character's roles under the role
  lock (`denied` without `entity.kill`; `invalid_target` for 0 or an id above
  `i64::MAX`; `invalid_reason` for an empty reason or one with control
  characters). Nothing the client sends grants it.
- **Audit:** an authorized request writes its `admin_results` row (status
  `kill_authorized`, the entity in `detail`) and an `admin_audit` row (target
  `kill:<entity>`, the reason, the current world revision as before and after
  state, outcome `kill_authorized`) in the authorizing transaction, as
  `spawn` does. A denied or invalid request writes neither. The audit records
  the authorization; the outcome below goes to the operator's session only.
- **Effect:** the simulation applies it on its tick to that session generation
  (`stale_session` otherwise; `unavailable` while the realm drains for
  shutdown or the session is leaving, as a strike is refused there):
  `unknown_target` for an id that is not an NPC it
  holds, or one dormant; `target_dead` for one already dead;
  `target_pending` while a strike on it awaits its durable commit;
  `kill_limit` within 20 ticks of the session's previous kill; with a
  progression package, the ledger's own admission answers
  (`settlement_capacity`, `contributor_capacity`); without one,
  `reward_pending` while the operator's previous legacy reward is pending.
  Otherwise the NPC dies through the ordinary death path: with progression
  the operator is credited the NPC's remaining health in its contribution
  ledger and the encounter settles as any kill (XP, coins, items and loot
  ownership by the package's rules, recipients outside the reward radius
  getting nothing, as for any contributor); without it the operator gets the
  legacy kill reward. Corpse and respawn follow the NPC's rules. The answer is
  `killed`.
- **Retries:** only a fresh request can kill. The admin worker answers a
  retried request id from its stored result before the capability check (as
  for every operation), so a stored `kill_authorized` is returned as
  `kill_replayed` (detail cleared), for a retry with the same payload and for
  a `status` lookup alike, and the simulation never strikes on it. Otherwise
  a revoked character could replay an authorization stored while it held
  `entity.kill` (for example one refused by `kill_limit`, or one for a
  predictable id not yet spawned) and kill later (review round 1). A
  different payload is `payload_conflict`. A refused kill is retried with a
  new request id, which is checked and audited afresh. The answer to a lost
  acknowledgement is therefore `kill_replayed`, not the original outcome; the
  NPC's state shows it.
- **Why the death path, not a silent removal:** KO's override also feeds its
  value into the ordinary damage routine `004204b4` (binary), so an
  operator's lethal blow in KO kills through the same path as anyone's; and
  the command exists to test what follows a kill.
- **Considered:** reproducing the overrides behind a capability (the user
  declined); reusing `entity.spawn` (PQ-182 keeps capabilities separate);
  removing the NPC with no settlement (diverges from the ordinary path the
  command is meant to test); re-checking the capability and session before
  returning a stored kill row (still lets a holder's refused request strike
  later, and keeps two paths to a kill; never acting on a replay is simpler);
  a per-request memo in the simulation as `spawn` keeps (bounded state for no
  gain).
- **Limits:** the kill is typed in the tools terminal (`kill` for the current
  target, or an id, which every client receives); there is no click or HUD
  control for it. The magic and skill damage paths were not read
  for further overrides; the user's answer made that reading unnecessary.
- **Recorded in:** [CONTRACTS](CONTRACTS.md) C-05,
  BINARY-POLICY,
  PQ-194. Evidence: pq-194.

## D-158 — 2026-10-14 Large maps carry their heightfield natively in N3C2; the object grid is built at load

KO keeps a large map's terrain as a grid, not as triangles. Ebenezer's SMD
terrain reader `004735c4` reads the sample count `n` (int) and the unit (float),
allocates `n` row pointers and `n` floats per row, and reads `n × n` heights,
with no size cap; its collision reader `004ce6ff` (`CN3ShapeMgr::LoadCollisionData`)
reads the map width and length (accepted only in (0, 4096] m by `004ce922`:
`0.0` at `00633708`, `4096.0` at `00633ea0`), the face count and `faces × 36`
bytes, then walks 16 m main cells (`16.0` at `00634e0c`) with a per-cell exist
flag, each a `0x88`-byte cell of 4 × 4 sub-cells whose index lists `004d012b`
reads (Ebenezer-official.exe, binary), so 4 m sub-cells (inference: 16 m / 4). The client's terrain
loader `0059a010` allocates `n² × 8` with no fixed cap (KnightOnLine.exe,
binary). n3e's N3C1 carried a heightfield as a triangle soup capped at 196,608
vertices, so KO's 513-sample homelands (1,572,864 terrain vertices) could not
be cooked (PQ-213).

- **Selected:** a second collision encoding, `N3C2`: sample counts, X/Z origin,
  spacing, the cooker's diagonal rule, `width × depth` absolute f32 heights, then
  the object triangles as N3C1 lists them. The cooker writes N3C1, byte for byte
  as before, whenever the heightfield is at most 129 samples a side and the
  soup fits 196,608 vertices, and N3C2 otherwise. Bounds: 2..513 samples a side,
  spacing (0, 100] m, at most 4096 m a side (KO's own extent bound), coordinates
  within ±1e6, at most 393,216 object vertices; the cooker and both readers
  refuse anything else, including trailing bytes.
- **Index:** the uniform grid over the object triangles is built by each reader
  at load (4 m cells, KO's sub-cell size by inference, widened so a side has at most 1024
  cells), not stored. A query gathers the triangles whose X/Z bounds, padded by
  0.25 m + 1e-4 × their size (more than the narrow phase's 1e-6 barycentric
  tolerance and f32 rounding), meet the query box, plus the heightfield cells
  under the box with a margin, and the unchanged full-scan solvers run on that
  subset. Membership is decided per triangle, so the answer does not depend on
  cell boundaries and the server and client gather the same set. A triangle
  spanning more than 64 cells is kept in a list scanned (and still filtered by
  its bounds) on every query. The grid refuses nothing the format allows:
  memory is bounded by construction (at most 64 memberships per triangle, at
  most 1025 × 1025 cells, and the format's triangle caps), and a query's work
  is at most a scan of every triangle, what every non-exploration package paid
  before. Attempt 1 round 1 had refusal budgets (4096 listed triangles, 8192
  per cell, 4,000,000 memberships); review found they refused N3C1 packages the
  cooker still writes (a 129-sample heightfield at 30 m spacing or more) and
  they were removed. This one structure replaces the 8 m exploration index
  (CONTRACTS, turbo; it refused exploration packages at more than 4096 cells
  per triangle, 8192 per cell or 1,000,000 memberships) and the full scans of
  other packages; every N3C1 file the old readers loaded still loads.
- **Server authority unchanged:** the server reads `collision.bin` from the
  release and owns every movement answer; the client gathers the same set for
  prediction only.
- **Considered:** storing the grid in the file (the readers would have to check
  a derived structure against the triangles, a second source of truth to keep
  consistent); KO's SMD layout (server-only, and n3e bakes one collision for both
  runtimes from the client data, MAP-EXPLORATION); expanding the heightfield to
  a soup in memory (19 MB per runtime and the client's per-frame camera scan
  over 524,288 triangles); keeping the 8 m index for exploration packages only.
- **Limits:** the camera sweep (`orbit.h`, client presentation) gathers within
  its radius plus 1 m of the boom; KO-derived N3C1 data still matches the full
  scan except where `camera_geometry::hit`'s padded edge slabs report a hit on
  a triangle that never comes within the radius (an acute-corner overshoot of
  that test): 6 of 20,000 random sweeps on the local Moradon package, now not
  obstructions. A package with no world asset draws its whole collision as the
  stand-in surface every frame, 524,288 triangles for a 513 map. The importer
  (`ko_terrain`), world, atlas and colour-map caps that also keep the homelands
  out are PQ-216/PQ-217 and PQ-055.
- **Recorded in:** [CONTRACTS](CONTRACTS.md) (Phase 1 asset contract and KO-01
  turbo bounds), content/README.md, PQ-215.
  Evidence: pq-215.

## D-159 — 2026-10-14 Map-sized worlds become a chunked, streamed asset; N3W1 stays for worlds that fit

A 513-sample KO zone (2048 m) does not fit n3e's world presentation: N3W1's
196,608 vertices and 32 MiB file, N3L3's 2,000,000 indices, 16 MiB and 8192
parts, the 324-slot atlas and render detail's 1,024 textures all bind
separately (PQ-055 evidence, PQ-213). KO itself loads a zone whole and bounds
per-frame work: a fixed window of terrain patches re-pointed around the camera,
whose geometry is rebuilt when the camera crosses a patch (`0059b6f0`,
`0059b890`, `005a0410`), a 256 × 256 grid of 16 m object cells walked around
the camera (`005b5680`, `0.0625` at `006a8700`), and the whole colour-map grid
read at load (`0059eff0`) (KnightOnLine.exe, binary).

- **Selected:** a second world encoding, `N3W2`, that holds a square grid of
  self-contained chunks, each with its own vertices, indices, N3L3 parts and
  bounding box, drawn from its own buffers and culled by its box before its
  parts (PQ-231). The client streams chunks by distance under fixed residency
  limits (PQ-232). World textures move into their own bounded asset of several
  array banks (PQ-233). The KO bake writes N3W2 only for maps that do not fit
  N3W1 (PQ-234). The cooker keeps writing N3W1 (with N3L1-3), byte for byte, for
  every world that fits, so Moradon and the demo are unchanged, and the client
  keeps reading it.
- **Engine choice, not KO behaviour:** reading chunks from disk while the player
  moves has no KO counterpart. It is chosen because n3e cooks a world's geometry
  ahead of time instead of rebuilding terrain patches from the heightfield as KO
  does, so the cooked size grows with the map.
- **Server authority unchanged:** world presentation stays client-only. The
  server checks magic, size and engine pairing and hashes the bytes into release
  identity. Collision stays N3C1/N3C2 (D-158) and authoritative.
- **Considered:** raising the N3W1/N3L3 caps in place (one whole-map upload that
  grows with the zone, and per-patch variant lists alone outgrow every file
  bound); rebuilding terrain on the client from the heightfield as KO does
  (smaller files, but it moves `ko_lod`'s terrain bake into the client and
  changes how Moradon is drawn); one file per chunk (the release and manifest
  would list hundreds of files).
- **PQ-231 (2026-10-14):** `N3W2` replaces `world-lod.bin` rather than adding to
  it, so it pairs with the exploration policy (engine 13 on) and refuses a
  `world-lod.bin` beside it; no engine version was added (a client that
  predates it refuses the magic, as with N3L3 under D-056). Its parts add kind 0
  (plain distance levels) to N3L3's kinds so a world needs no progressive or
  terrain data, and the terrain policy is optional. The server now checks the
  N3W1 magic too. Evidence: pq-231.
- **PQ-232 (2026-10-14):** the client streams N3W2 with one worker thread and
  fixed limits (1024 chunks, 256 MiB of chunk bodies, resident and in flight);
  the reach is the far plane's corner distance, so it follows the window
  aspect. When the chunks in reach exceed the limits the nearest are kept up to
  the first that does not fit and the rest are not drawn, with a one-line
  notice, rather than the client stopping, so a window resize can never end a
  session (cook-time check: PQ-236); a single chunk over the byte limit is
  refused at start, so the chunk nearest the eye is always held. Whole-world totals bind
  only when a world is loaded whole; a terrain patch now belongs to the cell of
  its patch centre, so coverage and uniqueness are checked chunk by chunk. A
  target marker needs the whole terrain and is refused with a streamed world
  (PQ-235). Evidence: pq-232.
- **PQ-233 (2026-10-14):** an N3W2 world's textures are `world-textures.bin`
  (`N3WT`): up to 4096 authored mip chains and 384 MiB of pixels, grouped by
  top size and level count into banks of up to 2048 layers, at most 8 (the
  shader's existing `native` samplers; the 1,113 `Object` and 328 `DTex`
  textures of `ref/ko-src/assets/Client` fall into 6 and 1 size groups,
  local-asset). The N3W2
  header's atlas becomes a texture count in place (no package used the old
  layout; an older reader refuses the unlisted file). The client splits banks
  at the GPU's layer limit and refuses, with the limit named, more than 8 or an
  oversized texture; render detail's world subset stays N3W1's. Textures load
  whole at start, as KO reads its colour-map grid at load (`0059eff0`).
  Evidence: pq-233.
- **PQ-234 (2026-10-14):** the KO bake chooses N3W2 by the GTD header's sample
  count (above 129) and otherwise falls back to it only when an N3W1 / N3L3
  bound refuses the build, so a map that fits keeps N3W1 byte for byte. Chunks
  are 128 m (a 2048 m zone is 16 × 16, 4 × 4 terrain patches each); the N3WT
  holds each slot's native mip chain, and render detail's world subset is then
  the transparent slot alone. The local homelands bake to 256 chunks and
  597-676 textures (141 MiB of pixels at most), within every N3W2 and N3WT
  bound. Evidence: pq-234.
- **Recorded in:** PQ-055 (split into PQ-231 to PQ-234), GAPS "World asset",
  content/world.md. Evidence: pq-055.

## D-160 — 2026-10-14 A target marker on a streamed world follows the native heightfield; N3W2 packages always cook N3C2

A target marker's ground parts sampled the full-detail terrain parts of the
whole world, built once at start. A streamed `N3W2` world (D-159, PQ-232) is
never resident whole, so PQ-232 refused the pairing. KO's marker
(`005c4e20`, KnightOnLine.exe, binary) samples each ground vertex through
`005e9570` (call at `005c5105`), whose first query is the world's terrain
height (the terrain object's vtable `+0x30`; the slot's identity as
`GetHeightWithTerrain` is source-only), the heightfield interpolation of
`0059d330` (4 m tiles, `(ix + iz)` parity diagonal; binary, as D-158); its
second query (vtable `+0x50`) can return an object surface (PQ-237).

- **Selected:** with an N3W2 world the marker's ground is the package's native
  collision heightfield (`N3C2`) without the object triangles: bounded, loaded
  at start, independent of which chunks are resident, and the surface KO's
  terrain query reads. The cooker writes `N3C2` beside every N3W2 world,
  whatever the heightfield's size (so the client always has one), and the
  client refuses a target marker on an N3W2 world whose collision has no
  heightfield. N3W1 packages keep their terrain parts and packages without a
  world their collision surface, so Moradon and every N3C1 package keep their
  bytes and their marker.
- **Considered:** rebuilding the ground from the resident chunks' terrain parts
  (a collision structure rebuilt as chunks stream in and out, and no ground when
  the limits leave a target's chunk out); the whole collision surface (a marker
  on roofs and walls, which the terrain parts leave out); keeping the refusal
  (a KO map baked as N3W2 would lose its marker, PQ-234).
- **Limits:** the heightfield and the world's terrain parts must describe one
  surface; the KO bake cooks both from one heightfield with one diagonal rule
  (`heightfield_triangles`, `ko_lod.terrain`), and the synthetic check compares
  them along a path. A hand-made package whose terrain parts differ from its
  heightfield draws the marker on the heightfield. Server authority is
  unchanged: the marker is presentation and collision stays authoritative.
- **Recorded in:** [content/target-marker.md](../../content/target-marker.md),
  content/README.md, CONTRACTS (Phase 1 asset
  contract, world streaming), PQ-235. Evidence:
  pq-235.

## D-161 — 2026-10-15 A KO cook's release depends on its input values only; operator rows are identified and ordered canonically

PQ-051 asked whether converting the player's KO data is repeatable across runs and
sources, so that client and server release hashes agree and the operator-local NPC
and spawn imports (PQ-054, PQ-069, PQ-219) can build on it. Evidence:
pq-051.

- **Observed:** Moradon (plain, `--features`) and the homelands (keys 10, 20) cook
  end to end to the same release hashes from the pinned installer's files (plus
  the Open-KO CSV exports the installer lacks) as from `ko-client-assets`; under
  Python 3.14 and 3.15 with glibc; in another working directory, output path, hash
  seed, locale, time zone and environment; (plain Moradon, package step) with the
  PNG intermediates' zlib level changed; and (key 10) from a START_POSITION export in another row order, key
  order and layout. Under Python 3.13 with musl (Alpine) only parts ran, because
  the start survey and the feature routes need the host-built engine: the package
  step at the host's surveyed spawns gives the same plain-Moradon and homeland
  releases, and the feature cook's libm-dependent outputs (27 player clips and
  `effects.bin`) are byte-identical; no feature release was cooked there. Two fresh restores of the reference backup
  export byte-identical tables, equal to an export from an earlier session.
- **Selected:**
  - A KO cook's release is to depend only on the bytes the cooker reads and the
    operator rows' values (held in the comparisons above; other libcs,
    architectures and host tools are PQ-242 and PQ-243). Run-to-run identity is
    a standing check: Moradon's and
    now the homelands' release hashes are pinned in `tests/ko_bake_pin.py`, the
    homelands' per START_POSITION row.
  - An operator-local input is named by a canonical digest of the values the cook
    reads (`ko_start.row_digest`: the read columns, sorted keys, no spaces),
    recorded beside the export file's hash. The file hash stays as provenance; it
    changes with any re-export layout, the release does not.
  - Operator table imports (PQ-054 and its users) take a total canonical order:
    rows sorted by their full column tuple, a missing JSON key read as SQL NULL
    (`FOR JSON PATH` omits NULL columns), values type-checked and refused when
    wrong, and package data written in that order. The export query has no
    `ORDER BY`, and KO's AI server reads `K_NPCPOS` in the database's storage
    order too (AI `0043893e` opens the recordset without a sort; its SQL builder
    `0044b23e` adds `ORDER BY` only for a non-empty sort string), handing out NPC
    ids in that order. n3e's entity ids are its own, so the canonical order has
    no player-visible cost, and it makes the release independent of how an
    operator exported the table.
- **Considered:** keeping the export's row order (KO's storage order, stable for
  one backup and one pinned SQL Server image, but not guaranteed by SQL and
  different under another export tool); naming operator inputs by file hash
  (changes with formatting, so two operators with the same rows would not
  recognise each other's cook).
- **Not decided (queued):** a client cooked by a player from the installer and a
  server cooked by an operator agree only if every release input is the
  player's too; a package with operator rows is not (PQ-243, with D-118's open
  importer shape and the engine survey across compilers and architectures). The
  cook still runs the host's ImageMagick with a system font for the KO HUD and
  name font atlases and reads a `tests/` fixture (PQ-242). Neither blocks local
  play, where one cook serves both sides.
- **Recorded in:** GAPS "Player-supplied KO import", FEATURES KOF-0032,
  content/world.md, `tools/assetc/ko_start.py`, `tests/ko_bake_pin.py`, PQ-054's
  note.

## D-162 — 2026-10-15 NPC templates are package data, applied as each NPC's instance rules

PQ-249 (child of PQ-069) asked for many NPC templates per package, so the homeland
population (PQ-219) can carry every monster and NPC its zone uses. Evidence:
pq-249.

- **Observed (binary):** KO's AI server keeps one record per K_MONSTER and K_NPC
  row in two maps (`00437fb4`, `00438479`); the spawn load `0043893e` picks the map
  by the spawn row's act type (below 100: monsters), logs a missing template and
  abandons the whole spawn load (it returns 0 through `00439633`, and its caller
  `00436a34` then does not start the AI server), and copies the template into the
  NPC's own record `[NPC+0x4f4]`, which the attack, damage and kill-reward paths
  read (`0041de51`, `0041f535`, `004209da`; PQ-069 evidence).
  The NPC's step speed is the record's walk speed only in wander (`00419fd9`);
  chase and path movement use the run speed (`0041d5d1`) and the return twice it
  (`0042890f`). The NPC info record the AI sends (`0042214c`) carries
  the record's `sPid` (looks) and maximum health beside the NPC's current health;
  the client's NPC-in parse (`005cd620`) reads `sPid` and looks up the model row.
- **Selected:**
  - The template table belongs to the NPC policy (`N3N3`, model
    `reference_templates_v3`, engine 37 / wire 30), bounded at 256 templates;
    each slot names one. Template identity is a package rule ID (no KO ids in
    engine modules).
  - The slot's template is applied to the NPC's instance rules (`Rules::
    apply_template`, from `administration::cycle_rules`), and every server path
    that acts for an NPC reads those rules: the AI tick, both damage directions,
    retaliation forecasts, regeneration, death and respawn, the contribution
    reward, party rewards, item-drop level, the operator record line and editor
    spawns. The legacy reward path receives the instance rules but is unreachable
    for N3N3 (engine 37 requires progression). Packages without N3N3 behave as before.
  - The progression definition (its hash and durable checks) stays the realm's.
    A templated encounter's settlement records the template's level and XP in an
    `N3T1` trailer and validates its awards against them; untemplated payloads
    are byte-identical to before. No schema change: the payload is a stored
    `bytea`, compared byte for byte on retry and never re-parsed.
  - The entity carries `looks` (31) and `max_health` (32) only when spawned from
    a template; the client uses `max_health` for the target bar.
  - Respawn stays on the slot (KO: the spawn row's `RegTime`, `0041b89c`). The
    template carries the run speed only, which KO's chase and return read; the
    walk speed, which KO reads only in wander, joins the template with wander
    (PQ-070). A missing template refuses the package, as KO's failed spawn load
    keeps its AI server from starting.
- **Considered:** a separate template file beside N3N2 (two files to keep in
  step for one table); per-template progression definitions with their own
  hashes (would break the realm's single durable reward definition and every
  progress row's definition check); sending a template index instead of the
  looks key (ties the wire to table order).
- **Not decided (queued):** spawn and view scale (PQ-250), reference values and
  bounds (PQ-251, PQ-252), per-looks presentation (PQ-253, PQ-254).
- **Recorded in:** content/npc.md, CONTRACTS ("NPC templates"), protocol/README,
  GAPS "NPC archetypes", FEATURES KOF-0015, PARITY.

## D-163 — 2026-10-15 A zone's whole NPC population: 2,048 spawns, a population-sized id pool, and nearest-first views under the frame bound

PQ-250 (child of PQ-069) asked for a zone's whole NPC population, about 1,300
NPCs, on the path to the homeland maps (PQ-219). Evidence:
pq-250.

- **Observed (binary):** KO's AI spawn load has no fixed NPC cap: it numbers
  NPCs from the short at app `+0x31c6`, keys each in a map by that number, and
  hands them to `0x1dc`-byte objects (worker threads by source name) 50
  (`0x32`) at a time (AI `0043893e`). That load numbers each NPC once; whether
  KO's respawn keeps the number was not read (open: AI `0041b89c`, which
  PQ-219 cites for respawn, sets the NPC's health and state to 0 and a delay,
  reads the number at byte `+0x2b8` without writing it, and is reached from 14
  call sites, the damage routine `004204b4` among them, so it is not identified
  as the respawn). Ebenezer builds a region NPC-in list from
  the nine cells around a user (`00423be6` calling `004241dd` nine times). Each
  cell stops adding NPCs past 16,300 bytes (`0x3fac`); when the whole list
  reaches 49,100 bytes (`0xbfcc`, `00424000`) it logs `NpcInOutForMe - buffer
  overflow` (`0065f3ec`) and sends no list at all. The user list `00422351`
  has the same bounds. A session's region packet buffer is 16 KiB (`0x4000`):
  a packet that does not fit is dropped and counted, and the fourth overflow
  calls `00445f77`, which marks the socket (`+0x8034` = 3) and posts it to its
  completion port (`004462c2`; that this closes the session is the source name
  `CIOCPSocket2::Close`).
- **Observed (local-asset):** the largest zone in the local OpenKO rows has
  1,238 NPCs (zone 1; zone 2 1,233; zone 201 778), PQ-054's extract.
- **Selected:**
  - Spawn points (N3G2/N3G3), reference slots (N3N2/N3N3) and editing spawn
    targets are bounded at 2,048 per package (`MAX_SPAWNS`, server, client and
    cooker). No format or version change: older readers refuse a package past
    32. The editing table stays at 128 properties: a package may name the spawn
    points an editor can move (`editing.spawns`); without it every point is
    editable, as before, and a large population must name a few.
  - Runtime ids: startup reserves one per spawn plus 256, in batches of at most
    1,024; refills ask for half the population (256 to 1,024) below a quarter
    of it (at least 128); an NPC respawn never takes the last 64 ids, which
    player work (revives, wear events, claims, operator spawns) keeps. A respawn
    waiting on ids is delayed, never skipped. n3e keeps a new id per instance
    (the wire contract, protocol/wire.proto `World`); this is n3e's own rule,
    not compared with KO's respawn, which was not read.
  - Views: a `World` that does not fit one 65,536-byte frame keeps the viewer,
    every non-entity field and the nearest other entities (planar distance, then
    id) that fit; an event stays only with both parties kept; trace reports
    follow kept entities. Only a view whose viewer alone cannot fit is not sent,
    and that session is closed. This is a correction of KO's whole-list drop
    (BINARY-POLICY, "View frame overflow correction"). The server plans each
    view from references and copies only what it keeps.
  - Every NPC's instance rules share the package tables (`Arc`): a respawn or
    an NPC no longer copies the spawn list, slot and template tables or the
    inventory, progression, commerce and skill policies.
  - The health line reports `tick_max_us` and `queue_max` (largest of the last
    100 ticks), `npcs`, `ids`, `views_trimmed` and `views_over`.
- **Considered:** a package-declared population limit (one more number to keep
  in step with the engine bound, with no reader that needs it); dropping a
  crowded view as KO does (leaves a player beside NPCs it cannot see); KO's
  per-cell truncation (keeps arbitrary cells' NPCs, not the nearest); splitting
  a view across frames (breaks the atomic baseline the client relies on);
  reusing an NPC's id across respawns (breaks the wire contract that a new
  instance has a new id).
- **Not decided (queued):** the reference values (PQ-251, PQ-252), per-looks
  presentation (PQ-253, PQ-254) and the homeland population itself (PQ-219).
- **Recorded in:** content/npc.md, CONTRACTS ("NPC population scale"),
  protocol/README, GAPS "NPC archetypes", FEATURES KOF-0015, PARITY,
  BINARY-POLICY.
## D-164 — 2026-10-15 KO reference stats map onto N3N3 templates whose bounds cover the reference rows

PQ-251 (child of PQ-069) asked for a KO cook that builds one n3e template per
template a zone's K_NPCPOS rows use, each column read in the AI binary from the
template copy to its consumers, with n3e's bounds lifted where the rows exceed
them. Evidence: pq-251.

- **Observed (binary, AI server):** the loads `00437fb4`/`00438479` and the
  spawn copy `0043893e` put each column in the NPC's record. Run speed is
  `bySpeed2` × 1.5 m a step at one step per 1,500 ms (1 m/s a unit). The band
  routine `0041d266` lets a melee NPC strike only while the horizontal distance
  d to its target satisfies trunc(d − r) ≤ `byAttackRange` and d − r < r + 3.0,
  with the radius r = `sSize` × `sBulk` / 10⁴ (`byDirectAttack` 1: d − r < 30;
  2: the whole band). The attack routine returns `sAttackDelay` (ms) as the
  next delay. The scan takes players within the 3-D search range; act types
  1–4 clear its aggressive flag (`0042476d`), and it skips a player whose
  `+0x66` (the nation, by source name) equals the NPC's `byGroup`. The level is
  sent to the game server as one byte (`0042214c`). `sStandtime` is the
  standing delay, during which the NPC still scans (`0042b86c`), so its effect
  is the pause between wander moves.
- **Observed (local-asset):** the OpenKO homeland rows (zones 1, 2) use 108
  templates each with levels 22–110, health 318–150,000, run speed 0–9 m/s,
  search 4–25 m, strike distance 4.4–36 m; over every row of both tables level
  reaches 250, health 1,300,015, run speed 10, search 50, strike distance 38.
- **Selected:**
  - `tools/assetc/ko_npc.py` maps one row to one N3N3 template: name
    `<game>:monster|npc/<sSid>-<slug>`, looks `<game>:looks/<sPid>`, health
    `iHpPoint`, level `sLevel`, attack ticks ⌈`sAttackDelay` / 50⌉, speed
    `bySpeed2` m/s, attack range the strike distance min(2r + 3, A + r + 1)
    (`byDirectAttack` 1: min(r + 30, A + r + 1); 2: A + r + 1), search and
    tracing as the rows give them, passive for act types 1–4 or a group equal
    to the package's nation. Damage, N3D1 stats and XP are the caller's until
    PQ-252. Rows the bounds cannot carry are refused by name.
  - N3N3 keeps its layout; its bounds become health 1–2,000,000, level 1–255,
    speed 0–12 m/s (0 never moves), attack and search ranges up to 64 m, in the
    cooker, both readers, the N3T1 settlement and party rewards. They cover
    every row of the reference tables. An older reader refuses a package past
    the old bounds, so there is no version change (as D-163).
  - A chase or return faster than 3 m/s takes ⌈speed / 3⌉ solver substeps of
    at most 0.15 m; a chase stops at the substep that enters its range. Speeds
    up to 3 walk exactly as before, so the Moradon worm and its release pins
    are unchanged.
  - An encounter's credit (the damage each player deals, which shares the
    kill reward and the party loot) is bounded at 100,000,000 per recipient
    and in total (`progression::CREDIT_LIMIT`, fifty times the template
    health bound, since regeneration can heal an NPC while it is fought),
    instead of 100,000, in the settlement payload and validation, party
    rewards, party loot and the `encounter_recipients.credit` check
    (migration 022, widening only). `Ledger::credit` stops counting at the
    bound, so a settlement can always be written: before this a kill of a
    template past 100,000 health failed its settlement and stopped the realm
    (review round 1).
- **Considered:** mapping `sStandtime` to the policy's `recovery_ticks` per
  template, as the worm's package does (KO does not stop scanning while
  standing, so recovery is not its meaning; it joins the template with
  wander, PQ-070); `byAttackRange` as the strike distance itself (the band
  routine strikes a melee NPC only inside r + 3 of its radius); a new N3N4
  model (no layout change was needed); bounds sized to the homelands only
  (the next zones would need another lift).
- **Not decided (queued):** own-nation NPCs neither scanning, striking,
  retaliating nor being attackable (PQ-258, before PQ-219); damage, N3D1 and
  XP from the rows (PQ-252); wander, `bySpeed1`, `sStandtime`, ranged and
  magic attacks (PQ-070).
- **Recorded in:** content/npc.md, CONTRACTS ("NPC templates"), GAPS "NPC
  archetypes" and "NPC behaviour", FEATURES KOF-0015, PARITY, BINARY-INDEX
  KOF-0015.

## D-165 — 2026-10-15 KO reference combat and XP map onto the N3N3 template and the N3D1 model, with bounds that carry the homeland rows

PQ-252 (child of PQ-069) asked for NPC damage, the N3D1 stats and XP from the
K_MONSTER / K_NPC rows, each column read in the AI binary, with 0 XP and 0
damage representable. Evidence: pq-252.

- **Observed (binary, AI server):** the binding `0041737b` and the loads put
  `sAc`, `sHitRate`, `sEvadeRate`, `sDamage` at template `+0x54`..`+0x5a` and
  `iExp` at `+0x44`; the spawn load `0043893e` copies them to the NPC's record
  `+0x4c`, `+0x4e`, `+0x50`, `+0x52` and `+0x3c`. An NPC's strike on a user
  (`0041f535`, from the attack routine `0041de51`) is X = `sDamage` × 200 /
  (user `+0x94` + 240) as a short, the grade from `004235aa` for `sHitRate` /
  user `+0x90` (read as defence and evasion by use: inference) (the nine rows n3e's N3D1 already has; an unordered compare takes
  the last row), trunc(0.3 r) + trunc(0.85 X) with r = rand(0, X), ×3/2 on the
  highest grade, 0 for a miss or X ≤ 0, capped at trunc(2.6 × `sDamage`); the
  routine applies it (`00443525`) only when it is positive. A user's strike
  (dispatcher `00404cc6` case 0x33 → `00405f1c` → `004430d8` → `00443a34`) is
  X = user `+0x8a` × 200 / (`sAc` + 240), the grade from `00444164` for user
  `+0x8c` / `sEvadeRate`. The kill reward `004209da` shares `iExp` by damage
  dealt; 0 gives every recipient 0. `sAtk` (record `+0x4a`) is read by neither
  strike.
- **Observed (local-asset):** the OpenKO homeland rows (zones 1, 2) have
  `iExp` 0–460,150, `sDamage` 0–5,000, `sAc` 126–20,000, `sHitRate` 16–497,
  `sEvadeRate` 10–1,218; over every row, `iExp` reaches 39,438,375, `sDamage`
  32,000 (50 K_MONSTER rows above 10,000), `sAc` 20,000, `sEvadeRate` 10,467,
  and four K_NPC rows have `sHitRate` and `sEvadeRate` 0.
- **Selected:**
  - `tools/assetc/ko_npc.py` maps `iExp` → `xp`, `sDamage` → `damage` and
    `attack`, `sAc` → `defense`, `sHitRate` → `accuracy`, `sEvadeRate` →
    `evasion`; the caller's synthetic `combat` values are gone.
  - Template bounds (cooker, both readers): `xp` 0–50,000,000, `damage`
    0–100,000, `attack` 0–10,000, `defense`, `accuracy` and `evasion`
    0–32,767 (KO's shorts). Rows with `sDamage` above 10,000 are refused by
    name: that is past n3e's N3D1 attack bound; `0041f535`'s short result
    wraps only above about 22,800 (defence 0, PQ-260). A 0
    evasion takes the top grade row and a 0 hit rate the last, as KO's
    compares do; a NaN ratio (both 0, ruled out by the player's bounds) takes
    the last row, as KO's unordered compare does. The package-wide N3D1 sides
    keep 1–10,000.
  - XP: `progression::TEMPLATE_XP_LIMIT` = 50,000,000 in the N3T1 payload and
    party awards; the settlement row caps become `SOLO_XP_LIMIT` (9/5 of it,
    90,000,000) and `PARTY_XP_LIMIT` (`i32::MAX` / 10 = 214,748,364, the party
    policy's per-level cap `004438fa` at its largest), was 1,800,000 and
    13,200,000; `encounter_recipients.awarded_xp` is widened to match by
    migration 023 (widening only). The package's own progression definition
    keeps its 1–1,000,000 base.
- **Considered:** lifting `attack` to 32,767 with a correction record for KO's
  wrap (no homeland or Moradon row needs it; queued); reporting KO's result 0
  for an NPC strike of 0 damage (`0041de51`: no health change, result 0) as a
  miss (a presentation change to D-027's `hit 0`; queued); mapping `sAtk`
  (no strike reads it).
- **Not decided (queued):** the zero-damage strike result and its side effects
  (n3e's `hit 0` records `skill_hit` and the strike tick and stops resting; it
  creates no wear event); rows above 10,000 `sDamage`; the Moradon worm's combat columns;
  KO's types and ids a user's strike cannot damage (`00443a34`: `+0xc69` 0 or 1,
  `sSid` 10401 and 20401, `byType` 2 fixed 20) and NPC type 14's strike from
  user `+0x70` (`0041f535`), with PQ-258 and PQ-070; the user's `+0xc3` 103/100
  bonus and hand magic (`00443e17`); the byte `[+4]+0x3201` (meaning not read;
  it forces NPC strikes to 1 and user strikes to 10,000), not reproduced.
- **Recorded in:** content/npc.md, content/damage.md, CONTRACTS ("NPC
  templates"), GAPS "NPC archetypes" and "Stats and damage", FEATURES KOF-0015,
  PARITY, BINARY-INDEX KOF-0015.

## D-166 — 2026-10-15 NPC presentation is per looks key: a looks table and one model per entry, loaded once and drawn by the entity's key

PQ-253 (child of PQ-069) asked for the client to draw each NPC with the model,
clips and texture its template's looks key names, instead of the package's single
NPC scene, with KO's per-row presentation rules (the `NPC_Looks.tbl` column 36
name flag, the info line, the pick box) applied per template and memory and load
time bounded for about 52 looks per zone. Evidence:
pq-253.

- **Observed (binary, client `KnightOnLine.exe`):** NPC-in `005cd620` looks the
  record's resource ID up in the looks table `[0081875c]+0x14` (`005cdc58`,
  `00453230`) and passes the row to the actor's slot `+0x20` (`005cdd7f`), which
  is `0045dda0` in the NPC vtable `006a412c` (PQ-170). `0045dda0` stores the row
  at actor `+0x274`; when row `+0xec` is 0 it hands row `+0x14` to `0041b260`
  (actor `+0x148`) and row `+0x24` to `0041bd30` (actor `+0x1cc`), otherwise it
  hands row `+0xe4` to the object at actor `+0x50`. `0041b260` and `0041bd30`
  get their object from resource managers (`0041d740`, `0041e540`) that
  lower-case the name (`CharLowerA`), look it up (`005eb770`, `005ebb40`) and
  create an object and call its slot `+8` with the name (its load, by
  inference) only when the lookup finds none (strings
  "CN3Mng::Add …", `006d39a8`–`006d3a24`); `0041b260` then rebuilds the actor's
  box (`0041b378` → `0041b000`). On a missing resource ID NPC-in takes the
  table's first node when the table's count `+0x20` is not 0 (`005cdc73`–
  `005cdc95`, `00473b10`), formats "Normal NPC In : [Name(%s), ResourceID(%d)]"
  (`006d79f4`), logs it (`0044a330`) and, when `[ESP+0x58]+0x48` is set, passes
  it with `0xffff00ff` to `0052acd0`; with a count of 0 it does the same
  (`005cdc97` falls through to `005cdcb7`), then builds no model and
  logs "No Resource NPC In" (`006d795c`, `005cde85`–`005cde9f`). The name flag is the row
  byte `+0x14c`, read through `+0x274` by the manager tick (`00470baa`) and the
  name callback (`00459856`), so it is per row (PQ-170).
- **Inferred:** row `+0x14` and `+0x24` are `NPC_Looks.tbl` columns 3 and 4,
  the character's `.n3joint` and `.n3anim` files, and `+0xe4` column 16, the
  shape file (the row layout of PQ-170 and the installer's rows: local-asset);
  `+0xec` is the length of that column's string (MSVC 6 string layout), so a
  row with a shape file builds a shape object; the managers share one loaded
  object per file name (lookup before create, and `0041b260` decrements a
  count at `+0x10` and frees at 0); `00473b10`'s node (the head's first link)
  is the lowest key; `0052acd0` writes an in-game message line (from the colour
  argument; not traced).
- **Observed (local-asset):** the OpenKO homeland rows use 52 distinct looks keys
  per zone (PQ-069); the Moradon worm's cooked atlas is 512 × 256.
- **Selected:**
  - Engine 38 (wire stays 30: no wire change) adds `npc-looks.bin` (N3LK) and
    one `npc-looks-<i>.bin` (N3NM) per entry, required exactly at engine 38+ and
    only with N3N3 templates. N3LK: u32 count 1–128, then per entry a package
    rule ID key, u32 flags (bit 0: name kept at any range and past the camera
    limit) and four clip records (idle, walk, attack, death; animation.bin's
    bounds, attack and death never loop). N3NM is an N3S1 scene whose track list
    is repeated four times, so an atlas and mesh are stored and uploaded
    once per looks. The table's keys must equal the templates' looks keys
    (cooker, both readers): a package carries only the looks its NPCs use, and
    every NPC's key resolves.
  - Bounds: 128 entries, 16 MiB per model, 96 MiB of atlas texels and 192 MiB of
    model files in all (cooker, both readers; the readers check the budgets from
    the model headers before parsing or uploading any model (`load_npc_looks`);
    the release index has already read and hashed each file, each at most
    16 MiB). The cooker also refuses a
    release over the readers' 256-file index.
  - The client parses every looks model once at start (after the release
    index has read and hashed each file), uploads one texture per
    atlas, drops the CPU copy, keeps the mesh once (the other three scenes of a
    looks hold only nodes, joints and tracks), and draws one batch per looks in
    view with that looks' texture. An NPC's looks entry gives its clips and clip
    timing, its standing and death-pose pick boxes (built from its own model,
    as KO rebuilds the actor's box after `0041b260`'s load, `0041b378` →
    `0041b000`) and its name flag, which is OR-ed with the
    package-wide `names.npc_lifetime` flag; the flag also lifts the camera limit
    without a lifetime policy, and the info line follows the name as before.
  - A key the table lacks takes entry 0, as KO takes the table's first node
    (the lowest key, by inference); a valid
    package never sends one. An entity id that comes back with another looks
    restarts its animation.
- **Considered:** loading a looks on first sight, as KO's NPC-in builds the
  actor inside its handler (`005cd620` → `0045dda0` → `0041d740`; that the
  manager's load reads the file there is an inference); n3e would stall a
  frame, and the bounded eager load measured 21 ms parse and 13 ms upload for
  52 looks of
  512 × 512 on the reference machine); four N3S1 files per looks (52 looks
  would need 208 files against the 256-file index and four copies of each
  atlas); a package-wide flag only (KO reads it per row).
- **Not reproduced:** KO's conditional magenta line for a missing looks row
  (to `0052acd0`, an in-game line by inference; n3e refuses such a package, so
  the case cannot arise); KO's shape-object NPCs
  (`+0xec` set) as their own kind: an importer can give them static clips
  (PQ-254). KO's fallback is the map's first node (the lowest resource ID, by
  inference); n3e's
  entry 0 is the table's first entry, which an importer orders.
- **Not decided (queued):** the NPC name and info-line height per model
  (`00459820` places them at the actor's `+0x17c` × `+0x90` above its position,
  where n3e uses the HUD style's NPC height); per-template display names (KO
  NPC-in reads the name from the record; n3e sends the template's rule ID).
- **Recorded in:** content/npc.md, CONTRACTS ("NPC templates"), GAPS "NPC
  archetypes", FEATURES KOF-0015 and KOF-0031, PARITY, BINARY-INDEX KOF-0015.

## D-167 — 2026-10-15 KO NPC looks rows convert as the client builds the actor; each row converts or fails closed with a named reason

PQ-254 (child of PQ-069) asked for an importer that turns each looks key a
zone's templates use into the per-looks model of D-166, built from the
`NPC_Looks.tbl` row as KO's client builds the NPC, with clip indices taken from
the binary. Evidence:
pq-254.

- **Observed (binary, client `KnightOnLine.exe`):** `006113b0` loads
  `Data\NPC_Looks.tbl` (`006d8d08`, `006136dd`) through `00616b80`
  (`00613729`). `0045dda0` takes the column 16 path when row `+0xec` is not 0:
  it calls slot `+8` of the character object at actor `+0x50` with row `+0xe4`
  and slot `+0x24` with the actor's position; otherwise `0041b260(+0x14)`,
  `0041bd30(+0x24)` and, when `+0xfc` is not 0, `0041cb80(+0xf4)`. On both
  paths row `+0x148` = 0 clears actor `+0x45b`; the turn `00457910` does
  nothing while it is 0 (`004579d0` also reads it, not traced). NPC-in then calls the actor's slot `+0x2c` (`0045cd90`)
  for positions 0–5 with row `+0x34 + 16 i` (`005cdfd5`–`005ce035`); a
  non-empty name goes to `0041b6d0`, which returns 0 for an index at or past
  the part count and reloads the part (its slot `+8`) when the name differs;
  an empty name at positions 2 and 5 calls NPC slots `+0x28`/`+0x24`, a bare
  `RET` (`004465e0`), and at 0, 1, 3, 4 looks race 100 up in `[00818758]`.
  Clips for race 100: stand `0045bfe0` 0 (9 in 10) else 12 + rand() % 4; move
  `0045a950` 1, 2, 3 by mode (jump table `0045aca4`); the NPC tick `004647a0`
  picks mode 2 when speed `+0x33c` ≥ 2 × 1.5 (`006a4124`) × `+0x168` ×
  `+0x90`, else 1 (`00464c33`–`00464c88`); attack `0045bf70` 4 + rand() % 2;
  the death handler `005cf620` passes mode 2 to `0045acc0` (`005cf906`), which
  plays 10. `0041be40` plays nothing for an index at or past the clip count.
  An NPC-in record whose type byte is not 0 takes the object branch (string
  `006d79a4` at `005cde42`), not the looks row.
- **Observed (local-asset):** column 16 holds `.n3chr` names (28 of 163 rows);
  column 17 `.n3fxplug` names; the worm's K_MONSTER row has sPid 700, and row
  700's columns 3, 4, 5 and 7 name the same joint, clip table and two parts as
  `Chr/mob_worm.n3chr`.
- **Inferred:** slot `+8` of the character object is its file load (so column
  16 is a whole character, correcting D-166's "shape file" reading of row
  `+0xe4` and its "shape-object NPCs" note: KO's object NPCs come from the
  record's type byte and the zone's shapes, PQ-271); the `.n3chr` load sets
  the part count that `0041b6d0` bounds; `[00818758]` is UPC_DefaultLooks
  (ids 1–4, 11–13), so an empty part name changes nothing for an NPC;
  `+0x168` is a radius.
- **Selected:** `tools/assetc/ko_npc_looks.py` builds each row that way
  (columns 11–15 never read), converts it through
  `tools/assetc/ko_character.py` with the worm's conversion (no gutter,
  evenly spaced samples) and takes clips 0, 2, 4 and 10, attack and death not
  looping, `name_always` from column 36; entries ordered by resource ID. A row
  converts or fails closed with the file and the reason; `cook` refuses a zone
  with any failed key, so no template is drawn with another key's model. The
  Moradon worm's model comes from its looks row (sPid 700) through the same
  rules; its release pin is unchanged.
- **Adaptation:** n3e's walk clip is KO's run clip 2, because n3e moves an
  NPC only at its run speed (chase) or twice it (return); KO's walk below the
  size threshold, attack clip 5, the talk clips and column 35's fixed facing
  are queued (PQ-269), the column 17 and `.n3chr` effects too (PQ-270).
- **Not converted yet (fail closed, queued before PQ-219):** of the 52 looks
  keys each homeland zone uses, 13 convert per zone (14 of the 61 distinct);
  the others stop at wrapping UVs (29, PQ-264), non-opaque part materials (5,
  PQ-265), joint scale (5, PQ-266), five skin influences or more than 64
  joints (2, PQ-267) and clip tables without the clips (6, PQ-268). The
  per-NPC drawn scale NPC-in applies (`005cdd82`–`005cdda9` → `0041f800` →
  `0043b650`) is PQ-272, also before PQ-219.
- **Recorded in:** content/npc.md ("KO looks import"), GAPS "NPC archetypes",
  FEATURES KOF-0015, PARITY, BINARY-INDEX KOF-0015, tools/assetc/KO-CHARACTER.md.

## D-168 — 2026-10-15 KO character parts with wrapping UVs convert into a repeated atlas region

PQ-264 (child of PQ-069) asked how KO samples a character part's texture and
for the converter to take parts whose UVs leave 0..1 (29 of the 61 homeland
looks keys stopped there in PQ-254) without changing any output that converts
today. Evidence:
pq-264.

- **Observed (binary, client `KnightOnLine.exe`):** the character render
  `004196a0` draws each part through `00412570` (`0041997f`), which binds the
  part's texture to stage 0 (`004129f4`) and draws through `00440730`
  (`00412ad8`) without writing a stage-0 address state; its stage-1 WRAP
  writes (`004126fa`–`00412722`, environment layer) are written back. The
  other stage-0 ADDRESSU/V writes among the client's 496 `CALL [reg + 0xfc]`
  sites (`0043dd80`: CLAMP for a buffer flagged `0x200`; the terrain: MIRROR;
  `005acc55`: BORDER) are written back from the values read before them
  before their functions return; the state set-up `0043ade0` sets filters and
  LOD bias for stages 0–7 and no address mode; no WRAP0–7 render state and no
  state-block apply is called.
- **Inferred:** with Direct3D 8's documented default (WRAP; API, not binary),
  a part is sampled with wrap addressing, so a UV and that UV plus a whole
  number sample the same texel.
- **Selected:** `tools/assetc/ko_character.py` keeps a part inside 0..1 (the
  existing tolerance) exactly as before; for any other part it moves each
  out-of-range triangle, per axis, by the whole number of repeats that leaves
  the least of it outside 0..1, and gives the part an atlas region covering
  the moved corners filled with the texture repeated. A region past the
  1024-texel atlas is refused. The model format, both readers and PQ-253's
  bounds are unchanged; every previously converted homeland key and the
  Moradon and homeland releases are byte-identical.
- **Considered:** one texture per part drawn with a repeating sampler, which
  matches KO's draw more literally but changes the N3NM model, both readers
  and the one-batch draw of D-166 for no measured gain (regions grow by 1–5
  texels for most parts; atlases of the wrapping keys are at most
  1024 × 517).
- **Result:** 27 of the 29 keys convert; 12100 and 12200 now stop at a
  zero-length attack clip (PQ-273). Zone 1 converts 38 of 52 keys, zone 2
  36 of 52. The NPC-in resource ID is sign-extended (`005cd68f`), so the
  importer bounds IDs at 32,767.
- **Recorded in:** content/npc.md ("KO looks import"), GAPS "NPC archetypes",
  FEATURES KOF-0015, PARITY, BINARY-INDEX KOF-0015, tools/assetc/KO-CHARACTER.md.

## D-169 — 2026-10-15 KO clips that start and end on one frame convert as that frame's pose held

PQ-273 (child of PQ-069) asked what KO's client does with a clip whose end
frame equals its start frame (the shop and smith looks 12100 and 12200 stop
there: their attack, struck, guard and spell clips are single frames) and for
the converter to take such a clip without changing any output that converts
today. Evidence:
pq-273.

- **Observed (binary, client `KnightOnLine.exe`):** the clip start `0041be40`
  starts nothing without a clip table or for a negative index, the current
  index or one at or past the clip count; it never compares a clip's start
  and end frames. It sets the current
  frame (`+0x1dc`) to the clip record's `+0x10` and the blend time (`+0x1f0`)
  from the record's `+0x2c` (or the caller's value). The frame tick
  `00418b20` advances the frame only when no blend is running, clamps it up
  to `+0x10` and, once it passes `+0x14`, counts the clip played (`+0x1e4`)
  and sets it to `+0x14` (once-and-freeze or flag bit 0) or, with no such
  flag, moves it back by the clip's length when that is above 0 and to
  `+0x10` otherwise. `00418e00` poses each joint at the current frame (with
  no blend running) through joint slot `+0x20`.
- **Inferred:** `+0x10`/`+0x14` are the `.n3anim` start and end frames (their
  use in the tick and the file's field order); so a clip with equal frames
  shows the joints at that frame for as long as it is current, and counts as
  played on its first frame advance after any entry blend.
- **Selected:** `tools/assetc/ko_character.py` converts a clip whose end
  equals its start as two identical keys (the pose at that frame) 1/60 s
  apart, one sample of the converter's 60 Hz grid (both readers need two
  keys per track and at least 0.001 s); provenance records `held_frame`. A clip that
  ends before it starts stays refused (`clip ends before it starts`). No
  format, reader or bound changes; clips with length convert byte for byte
  as before.
- **Considered:** a zero-duration clip record meaning "hold" in N3S1/N3NM,
  which would change both readers' duration and track rules for no visible
  difference.
- **Result:** 12100 and 12200 convert; zone 1 still converts 38 of 52 keys,
  zone 2 38 of 52. Every file the start commit wrote for both zones is
  byte-identical.
- **Recorded in:** content/npc.md ("KO looks import"), GAPS "NPC archetypes",
  FEATURES KOF-0015, PARITY, BINARY-INDEX KOF-0015, tools/assetc/KO-CHARACTER.md.

## D-170 — 2026-10-15 The 1097 homelands cook as their own packages from the 1097 install's zone files, with the 2004 client's player and HUD and the operator's zone 1 and 2 START_POSITION rows checked on the 1097 ground

PQ-274 (user request, 2026-10-15) asked for the 2003 human and orc homelands:
the 1097 client's own `karus_start` and `elmorad_start` (its Zones.tbl keys 1
and 2), playable beside the 2004-era homelands of PQ-217/PQ-218. Evidence:
pq-274.

- **Observed (binary, client `KnightOnLine.exe` 1298):** `006113b0` opens
  `Data\Zones.tbl` (`006d8ddc`), decrypts it in memory with `0044f670`
  (each byte XOR the key's bits 8-15, then key = (cipher byte + key) x 0x6081
  + 0x1608, starting at 0x816) and parses it with `006264d0`: an int32 column
  count, one int32 type per column, an int32 row count, then the fields
  (`006359b0`: types 1/2 one byte, 3/4 two, 5/6/8 four, 9 eight, 7 an int32
  length and that many bytes). `006264d0` refuses a table whose computed row
  size (`00635be0`) is not 0x108 or whose first type is not 6.
- **Observed (local-asset):** the 1097 `Data\Zones.tbl` decodes with that
  cipher to its last byte: 15 columns, typed exactly as the 1298 table's
  columns 1, 2, 4, 5, 6 and 8-17, so it is that layout without the name
  (column 3) and OPDEXT (column 7) columns. Its rows 1 and 2 name
  `Zones\karus_start.*` and `Zones\elmorad_start.*`. Its GTD and OPD files
  have no version or name header (PQ-222). The 1097 install has no server
  data, no decoded tables and a Chinese UI (`UI_CH`).
- **Inferred:** the 1097 columns 2, 3, 5 and 6 are the 1298 columns 2, 4, 6
  and 8 (terrain, colour map, objects, overview map). With no name column
  and nameless files, the 1298 name check of `005a3110` has nothing to
  compare. The 1097 exe is packed, so neither is confirmed in its own loader.
- **Selected:**
  - `ko_zone.select(..., layout="1097")` reads that table through the
    committed decoder `ko_tbl` (types checked against the 15 observed ones,
    every byte consumed) and resolves those four columns. The headerless
    GTD and OPD are required (a headed file is refused). The name check is
    recorded as not applicable, and there is no OPDEXT.
  - `tools/assetc/ko_bake.py KEY --client=1097` cooks key 1 or 2 from
    `build/ko-reference/installer-1097/client`, the pinned PQ-221 unpack
    (its manifest must name the pinned installer), with the headerless
    readers threaded through the collision, world and survey bakes.
    Before anything is baked it checks that every file the zone refers to is
    present: the table's files, each GTT the GTD names, and each mesh and
    part texture the OPD's static shapes name. A missing file refuses the
    cook by name. A present mesh that n3e's mesh reader refuses (the two El
    Morad castle meshes, `KO normal`, also refused in 1264 and 1298) is
    listed by name in the provenance and skipped, as `ko_scene` skips it
    for every map.
  - The package keys are `ko-1097-zone-1` and `ko-1097-zone-2`, never
    `ko-zone-1` and `ko-zone-2`. Those names would read as the 1298 key
    scheme (zone x 10), and they would sit beside the current `ko-zone-10`
    and `ko-zone-20` with nothing to tell them apart. The play command is
    `tools/play-ko-zone karus-1097` or `elmorad-1097`: Compose projects
    `n3e-ko-1097-zone-1` and `-2`, ports 7797 and 7798, state under
    `build/ko-1097-zone-N-demo`. The 2004 stacks, `n3e-moradon` and the
    default project are untouched.
  - The map (terrain, tiles, colour map, objects, overview map) comes from
    the 1097 install. The player, HUD and render detail come from the 2004
    client data (`ref/ko-src/assets/Client`), as for every other KO
    package. The 1097 install's character tables are not decoded, and its
    UI is Chinese.
  - The start reuses the operator's START_POSITION rows for zones 1 and 2.
    The 1097 keys are the zone ids, so the row is ZoneID = key (`ko_start`
    `zone=`). Each nation's one-sided area is surveyed with the engine on the
    1097 collision, as for PQ-217, and the cook fails closed when an area
    holds no open spawn or the start reaches no walk target. The rows are
    the 2004-era server's: no 1097 server data exists, so that the 2003
    servers used the same coordinates is unconfirmed. The evidence records
    what stands at each start on the 1097 maps.
- **Considered:** reading the 1097 table by guessing its layout from the
  1298 CSV (refused: the column sets differ); keys `ko-zone-1`/`-2`
  (ambiguous, above); a whole-map survey for a spawn without
  START_POSITION (PQ-217 refuses it for 513-sample maps: no reference
  start, and the walk check's point bound); the 1097 install's own UI and
  character files (not decoded, Chinese UI, out of this item's scope).
- **Recorded in:** content/world.md, GAPS "Homeland maps" and "Secondary KO
  installers", FEATURES KOF-0005, PARITY, BINARY-INDEX KOF-0005, README.
- **2026-10-15 (PQ-276):** "no 1097 server data exists" is no longer
  accurate. The public ko4life-net ko-db and ko-assets (a secondary reference
  with unstated provenance; local-asset) hold server data that is probably
  1097-era (inference: their maps carry the 1097 heights). Their new-character rule (ZONE_INFO init point,
  KO 371,1573 / 1637,418) differs from the START_POSITION start chosen here.
  The 1298 binaries leave that position to the database (Aujard `00427e70`,
  `00424ac0`; binary); game start keeps it while it lies inside the map and
  otherwise uses the nation's HOME point (`004c66dc` → `004970cb(0)`,
  `00474574`; binary). The start chosen here stays until PQ-278 adopts the
  ko-db point (evidence).

## D-171 — 2026-10-15 The classic Moradon cooks from the pinned install's own unnamed Zones\moradon files through key 210's row renamed to that stem, as its own package and play stack chosen by `tools/play-moradon --layout classic`

PQ-223 (user request, INBOX 2026-10-13, chosen 2026-10-15) asked for the
non-Christmas Moradon that the pinned 1298 install ships but its Zones.tbl does
not name, as an option beside the default Moradon. Evidence:
pq-223.

- **Observed (binary, client `KnightOnLine.exe` 1298):** the world loader
  `005a3110` takes the zone row for the runtime key (`0046c9d0`) and loads the
  terrain, colour map and objects from the row's columns 2, 4 and 6, checking
  both internal names against column 3 (`lstrcmpiA`) and skipping the OPDEXT
  when column 7 is `Reserved` (as PQ-216 recorded). A strings search of the
  exe finds no zone file name and no `moradon` map path (the one `moradon`
  string, `006d6374`, is a UI control name, `btn_moradon`). Its row 210 names
  `Zones\Moradon_xmas.*`.
- **Observed (local-asset):** the pinned 1298 install carries
  `Zones\moradon.gtd`, `.tct`, `.opd` and `.dxt` (hashes in the evidence),
  whose internal names are `moradon`. Its row 210 with `Moradon_xmas`
  renamed to `Moradon`, less column 7 (OPDEXT, which the 1264 table lacks),
  is value for value the 1264 client's own row 210. It also agrees with the
  1453 client's row 210 in its first 23 columns (1453's column 24 names
  `Zones\Moradon.evtsub`, where 1298's is empty).
  Every GTT, mesh and texture the classic GTD and OPD name is in the 1298
  install.
- **Inferred:** the 1298 client reaches a map only through a table row, so
  it never loads `Zones\moradon.*`. A path assembled at run time, or a string
  Ghidra has not defined, is not ruled out. A client whose table named these files (1264, 1453) would load
  this map for zone 21; the 1298 client never does. The server rows that
  place the start and the worms (START_POSITION and K_NPCPOS for zone 21,
  `games/moradon/ko-reference.json`) are the zone's, not a layout's; which
  map the 2005 servers' own height data matched is not known.
- **Selected:**
  - `ko_zone.select(..., stem=...)` rewrites the row before anything is
    resolved (`restem`): column 3 becomes the stem and every column naming
    `Zones\<column 3>.<ext>` names `Zones\<stem>.<ext>`. Every path column
    must have that form, or the rewrite is refused. The files, the
    `005a3110` name check and the provenance then follow the rewritten row,
    and the provenance records each rewritten column. Without `stem` the
    selection and its record are unchanged.
  - `tools/assetc/ko_bake.py 210 --layout=classic [--features]` cooks it.
    Its four selected files must have the pinned installer's SHA-256
    (`MORADON_LAYOUTS`), and every file the map refers to must be present
    (`ko_scene.references`), or the cook is refused by name. It does not
    combine with `--client` or `--des`.
  - It cooks beside the default, never over it: package `moradon-classic`,
    source `ko-moradon-classic`, survey scratch `kx/survey-moradon-classic`.
    The default cooks keep their names and pinned releases.
  - The play option is `tools/play-moradon --layout classic` (default
    `xmas`, the table's own map). It has its own Compose project
    `n3e-moradon-classic`, server image tag `n3e-moradon-classic:local`,
    port 7799 (used by no launcher or code), `test-moradon-classic-<release>`
    realm and state under `build/moradon-classic-demo`. `n3e-moradon`, the
    `--des` stack and the default project are never touched. A layout is one
    entry of `LAYOUTS` in `tools/moradon_session.py`, so the 1097 Moradon
    (PQ-224) is added the same way (`--layout 1097`).
  - The feature data carries over unchanged where the engine proves it on the
    classic ground: the START_POSITION zone 21 start area (read as X ± bRange
    like the default's; PQ-240 tracks Ebenezer's one-sided area), the two worm
    spawn rows, the services beside the start and the combat points (each
    already engine-surveyed and fail-closed). The demo route to the second
    worm area is the one value that changes
    (`moradon_features.LAYOUT_ROUTES`): its default leg from (4, -28) is
    blocked on the classic map, so it turns at (2, -24). That route is n3e
    demo data, not KO data.
- **Considered:** a copied Zones.tbl or a hand-written row (refused: the
  rewrite of the install's own row keeps every other column KO's and records
  exactly what changed); a generic `--stem` option on the command line (it
  would accept any file name; a named layout carries its pinned hashes); reusing the default
  Moradon routes (the cook fails closed on them); moving every Moradon
  package to layout-named keys (would change the pinned default cooks).
- **Recorded in:** content/world.md, GAPS "Secondary KO installers", FEATURES
  KOF-0005, PARITY, README.

## D-172 — 2026-10-15 The 2003 Moradon cooks from the 1097 install's key 21 files as its own package, with the 2004 client's player, HUD, feature data and Moradon name rules, and plays as `tools/play-moradon --layout 1097`

PQ-224 (user request, INBOX 2026-10-13 and chat 2026-10-15: "the old
Moradon") asked for the 1097 installer's Moradon as a third Moradon option.
Evidence: pq-224.

- **Observed (binary, client `KnightOnLine.exe` 1298):** the world loader
  `005a3110` finds the row of the runtime zone key (`0046c9d0`, looked up by
  `0046d8c0`) and loads the map files that row names (PQ-216). The name-rule
  callback `0046ea90` reads the same row (`0046c9d0`, `0046d8c0`) for its
  party-name flag (column 23, PQ-166) and compares the key with `0x140`
  (PQ-173). The 2004 client's own Moradon row is key 210.
- **Observed (binary, `Ebenezer-official.exe`):** the start is the
  START_POSITION row of the character's zone (`004c6523`, with the random
  range of `00422261`), as PQ-217 recorded. n3e's Moradon start area is the
  committed zone 21 row (`games/moradon/ko-reference.json`).
- **Observed (local-asset):** the 1097 `KnightOnLine.exe`
  (`04ab5c54…2b771d4c`) is packed: its first three sections have no name and
  an entropy of 7.9 to 8.0 bits a byte, there is an `.adata` section, and the
  file holds no `Zones`, `moradon` or `.gtd` string. None of its loaders can
  be decompiled. Its `Data/Zones.tbl` key 21 names `Zones\Moradon.gtd`, `.tct`,
  `.opd` and `.dxt`. Both zone files are headerless (PQ-222). Every one of the
  545 files the map names (72 GTT, 289 meshes, 184 textures) is in the 1097
  install. 157 of them differ in content from the 2004 client's file of the
  same name (13 GTT, 144 meshes and textures); none is missing there. Its OPD
  places `obj_el_trans_stone4` at the same point as the 1298 classic map.
- **Inferred:** the 1097 table's columns mean what PQ-274 inferred, and its
  key 21 is the zone that the 1298 server's zone 21 rows (START_POSITION,
  K_NPCPOS) place. The packed exe confirms neither. Which name rules the 1097
  client applied cannot be read.
- **Selected:**
  - `tools/assetc/ko_bake.py 21 --client=1097 [--features]` cooks it, through
    PQ-274's `ko_zone.select(..., layout="1097")`, the pinned manifest check
    (`install_1097`) and `ko_scene.references`, which refuses the cook if any
    named file is missing. The start is surveyed on the 1097 ground inside the
    zone 21 start area (`ko_survey.survey(..., headerless=True)`), and the cook
    fails closed if no point qualifies. `--des` and `--layout` are refused with
    it.
  - It cooks beside the others: package `moradon-1097`, source
    `ko-moradon-1097`, survey scratch `kx/survey-moradon-1097`. The default
    and classic cooks keep their names and pinned releases.
  - The map, its GTT files, meshes, textures and overview map come from the
    1097 install. The player, HUD, keys, worm model, effects, skills and audio
    come from the 2004 client (`character_assets`), as for PQ-274's homelands.
    No 1097 UI text is imported (its UI is Chinese, `UI_CH`). The name rules
    are the 2004 client's for its own Moradon row, key 210 (`client_row`),
    because that client's player and HUD are what the package plays. The
    1097 row has no column 23, and its key 21 is not in the 2004 client's
    key scheme (zone x 10).
  - The feature data carries over where the engine re-checks it on the 1097
    ground: the zone 21 start area, the two worm spawn rows, the services
    beside the start and the combat points. The demo route to the second worm
    area takes the classic route (`moradon_features.LAYOUT_ROUTES["1097"]`):
    the default's leg from (4, -28) is blocked at (4.10, -27.82), beside that
    transport stone. That route is n3e demo data, not KO data.
  - The play option is `tools/play-moradon --layout 1097` (one more `LAYOUTS`
    entry). It has its own Compose project `n3e-moradon-1097`, image tag
    `n3e-moradon-1097:local`, port 7801 (used by no launcher or code), realm
    `test-moradon-1097-<release>` and state under `build/moradon-1097-demo`.
    The state records the 1097 key 21. When the 1097 install is not unpacked,
    the command first runs the pinned unpacker on the player's
    `KnightOnline_1097.exe`. Nothing in the installer is run.
  - Server-side Moradon data (NPCs, start, the n3e server's rules) is the 1298
    server's. The installer carries none.
- **Considered:** `--layout=1097` on the 1298 key 210 (it would read as a
  rewrite of the 1298 row, while these files come from another table); the
  1097 row for the name rules (no column 23, a key outside the 2004 scheme);
  new demo routes (the classic route already reaches both areas on this map);
  the 1097 install's tables for the player (none is decoded, and its texts
  are Chinese).
- **Recorded in:** content/world.md, GAPS "Secondary KO installers", FEATURES
  KOF-0005, PARITY, README.

## D-173 — 2026-10-16 KO part render states convert as N3SM clips and N3MM looks models (engine 39), drawn per run in part order

PQ-265 (child of PQ-069) asked which render states a KO character part's
material selects and for n3e to carry them as package data the client draws
(five homeland looks keys stopped at "nonopaque/custom KO material
unsupported"). Evidence, with every claim and its label:
pq-265.

- **Observed (binary, client `KnightOnLine.exe`):** the part renderer
  `00412570`, called only by the character render `004196a0` in part order,
  acts on the material's render flags only: 1 alpha blending with the
  material's source and destination factors, 2 fog off, 4 culling off,
  `0x40` lighting off, `0x800` a separate two-layer path; it never reads the
  material's colour op. The device set-up `0043ade0` turns the alpha test on
  with GREATER and no other code changes it outside two write-back windows.
  The texture load keeps DXT1 and DXT3 alpha.
- **Inferred:** every part is alpha-tested against 0 (the API default
  reference); blended parts keep z-write on and are not sorted; a part's
  alpha is its texture's for a diffuse alpha of 1 (which stage-0 alpha op is
  in force is not settled).
- **Selected:**
  - `tools/assetc/ko_character.py` reads flags 1, 4 and `0x40` into a
    render state (blend factors by D3DBLEND name, double-sided, lit) and
    refuses any other flag, flag 2 (fog off) included (no homeland part uses
    it and no check would show its draw; review round 1), a diffuse other than opaque white and a blend
    factor outside D3DBLEND 1–10 by name. DXT1 (with transparent texels) and
    DXT3 decode to RGBA.
  - A model with any non-opaque state or a texel below alpha 255 writes an
    RGBA atlas and one glTF primitive per run of consecutive parts sharing a
    state, each with an `N3E_render_state` material extension (alpha
    reference 0). Any other model converts byte for byte as before.
  - `gltf.cook(..., materials=True)` (only the looks clips, through
    `main.cook(..., materials=True)`) writes such a glTF as N3SM: N3S1 with
    the RGBA atlas and, after the indices, the runs (first index, count, flags
    1 blend / 2 double-sided / 4 unlit, alpha reference, source and
    destination factor). Every other cook refuses the extension.
  - Four N3SM clips make an N3MM looks model. A package with an N3MM model is
    engine 39 (wire 30, no wire change); without one it stays engine 38. The
    atlas budget counts 4 bytes a texel in N3MM. Both readers take N3MM only
    at engine 39; the client checks the runs.
  - The client draws an N3MM looks NPC by NPC, each NPC's runs in order with
    their state (GL blend factors, culling, unlit texture colour, a
    discard where the 8-bit alpha is not above the reference), and puts the
    frame's state back. Other looks draw in one call as before.
- **Considered:** one batch per run across all NPCs of a looks (fewer draws,
  but blended runs would no longer follow each character's part order, which
  KO keeps); sorting blended runs back to front (KO does not); the standard
  glTF `alphaMode`, `doubleSided` and `KHR_materials_unlit` (they cannot state
  KO's alpha test on blended parts or the blend factors, so a second source
  of truth would be needed).
- **Result:** looks 1638 and 4100 convert; 14001, 24000 and 24002 get past
  their parts and stop at their clip tables (PQ-268). Zone 1 converts 40 of
  52 keys, zone 2 40 of 52. Every file `main` wrote for both zones is
  byte-identical. The player path still refuses render states (PQ-280).
- **Recorded in:** content/npc.md ("KO looks import"), CONTRACTS (N3LK),
  protocol/README.md, tools/assetc/KO-CHARACTER.md, GAPS "NPC archetypes",
  FEATURES KOF-0015, PARITY, BINARY-INDEX KOF-0015.

## D-174 — 2026-10-16 A scaled KO joint converts as its node under a translation and scale node

- **Context:** PQ-266. `tools/assetc/ko_character.py` refused every KO joint
  with a scale other than (1, 1, 1) or a scale track, which stopped looks
  2020, 2100, 2200, 5100 and 5200 in homeland zones 1 and 2. KO's joint
  matrix rotates a joint's space and then scales it along the parent's axes;
  one glTF node (T × R × S) holds that only for a uniform scale, and the
  homeland scales are not exactly uniform. The claims and their labels are in
  the evidence record.
- **Selected:** a scaled joint keeps its node (its index, its rotation and
  rotation track) and gets a parent node, after the mesh node, with its
  translation, scale and their tracks; the pair is T × S × R, KO's matrix.
  Inverse binds use the same matrix at frame 0. Scale nodes count against the
  128-node scene; a scale of 0 or below is refused. A skeleton without a
  scaled joint converts byte for byte as before. The readers that build their
  own unscaled joint matrices (nameplates, render detail, target marker)
  keep refusing scaled joints. No format, cooker or client change.
- **Considered:** the scale on the joint's own node (exact only for a
  uniform scale; the homeland skeletons' near-unit and 0.356 scales differ
  in their last bits); a uniform-scale branch plus the scale node for the
  rest (two rules, two sets of checks, for no visible difference); a
  matrix per node in N3S1 (a format and client change, and tracks would
  still need a decomposition).
- **Result:** look 2100 converts; 2020, 5100 and 5200 now stop at the skin
  bounds (PQ-267) and 2200 at two NaN vertex normals (PQ-281). Zone 1
  converts 41 of 52 keys, zone 2 41 of 52; every file the start commit wrote
  for both zones is byte-identical.
- **Recorded in:** content/npc.md ("KO looks import"),
  tools/assetc/KO-CHARACTER.md, GAPS "NPC archetypes", FEATURES KOF-0015,
  PARITY, BINARY-INDEX KOF-0015.

## D-175 — 2026-10-16 KO skins past four influences keep their four largest weights within a measured bound, and skeletons past 64 joints skin with their weighted joints

- **Context:** PQ-267. `tools/assetc/ko_character.py` refused a skin vertex
  with more than four joint influences (looks 2600, 5100, 5200 in homeland
  zones 1 and 2) and a skeleton with more than 64 joints (2020, 3800). KO's
  client has neither bound: its skin load reads any number of influences
  and its CPU skinning sums every one with the weights as read; its joint
  set sizes its matrix arrays by the joint count. n3e's vertex holds four
  influences (glTF `JOINTS_0`/`WEIGHTS_0`, N3S1, the client's `Vertex`) and
  a skin at most 64 joints (cooker and client), with 128 nodes. The claims
  and their labels are in the
  evidence record.
- **Superseded in part:** the influence rule below (the four largest
  weights and their bound) is replaced by D-176 (2026-10-16): every
  influence is drawn. The weighted-joint skin past 64 joints stays.
- **Selected:**
  - A vertex with more than four influences keeps its four largest weights
    (ties in file order), renormalised. The converter measures, at every
    sample of the clip it converts, how far each such vertex of the drawn
    (maximum-detail) skin lands from KO's full weighted sum, and refuses the
    conversion when the largest distance passes one fiftieth of the model's
    largest bind-pose extent (`KO skin influences past four move a vertex …`).
    Provenance records the reduced vertices, the largest distance and the
    bound. A skin with at most four influences per vertex converts as before.
  - A skeleton with more than 64 joints (up to 127, so that the joints, the
    mesh node and any scale nodes fit the 128-node scene) skins with only
    the joints that carry weight in the drawn skin, in joint order, and
    refuses when more than 64 do; every joint keeps its node and tracks.
    Provenance lists the KO joint index of each skin joint. A skeleton with
    at most 64 joints keeps every joint in its skin, as before.
  - No format, cooker or client change. The other readers of KO skins and
    skeletons (render detail, appearance, nameplates, target marker) keep
    their bounds.
  - This replaces D-016's rule that a vertex past four influences is
    rejected rather than reduced: the reduction is bounded and recorded, not
    silent.
- **Considered:** more influences per vertex in N3S1 and the client (exact,
  but a format and engine change; queued separately for the vertices this
  bound refuses); raising the skin's joint bound to 127 in the cooker and
  the client (a reader change that needs an engine version; the weighted
  subset is exact for every drawn vertex); dropping every influence past
  four without a measured bound (one homeland vertex would move by a sixth
  of its model's height).
- **Result:** looks 2020 (61 of 67 joints weighted), 5100 and 5200 (235
  reduced vertices, largest distance 0.043 source units against a bound of
  0.112) convert; 2600 stops at the bound (0.170 against 0.075 in its idle
  clip; exact skinning queued as PQ-283) and 3800 (62 of 73 joints weighted)
  at the cooker's zero-length normal check (PQ-281). Zone 1 converts 44 of
  its 52 keys and zone 2 44 of 52; every file the start commit wrote for both
  zones is byte-identical.
- **Recorded in:** content/npc.md ("KO looks import"),
  tools/assetc/KO-CHARACTER.md, GAPS "NPC archetypes", FEATURES KOF-0015,
  PARITY, BINARY-INDEX KOF-0015.

## D-176 — 2026-10-16 KO skin vertices past four influences draw with every influence (N3SI/N3SJ clips, N3NI/N3MI looks models, engine 40); D-175's four-largest reduction is retired

- **Context:** PQ-283. D-175 kept the four largest of a KO skin vertex's
  influences and refused a model when that moved a drawn vertex past one
  fiftieth of its extent: look 2600 (centaur, homeland zones 1 and 2) stopped
  at that bound, and looks 5100 and 5200 drew vertices up to 0.043 source
  units from KO's sum. KO's skin load `004286f0` reads any number of
  influences per vertex and its CPU skinning `00419f00` sums every one with
  its weight as read (binary, re-read for this item). The claims and their
  labels are in the
  evidence record.
- **Selected:**
  - `tools/assetc/ko_character.py` keeps every influence of a vertex as read,
    in file order: the first four in glTF `JOINTS_0`/`WEIGHTS_0`, the rest in
    `JOINTS_1`, `WEIGHTS_1` and on (at most 16 sets, 64 influences; a vertex
    with more is refused by name). The weights are divided by their sum, as
    every vertex's already are. A model with no drawn vertex past four
    influences writes `JOINTS_0`/`WEIGHTS_0` only, byte for byte as before.
  - `tools/assetc/gltf.py` reads further sets only for NPC looks clips (the
    `materials` cook that only `ko_npc_looks` passes). A clip with a vertex
    whose further sets carry weight cooks as N3SI (N3S1 with an influence
    table) or N3SJ (N3SM with one); the table follows the vertices: u32 count
    of vertices with further influences, then per vertex (strictly
    increasing) u32 vertex, u32 n (1-60) and n pairs of u32 skin joint and
    f32 weight above 0. Four N3SI clips make an N3NI looks model and four
    N3SJ clips an N3MI. A package with such a model is engine 40 (wire 30, no
    wire change); otherwise it stays engine 39 or 38, byte for byte.
  - Both readers take N3NI and N3MI only at engine 40. The client checks the
    table (vertex order and range, counts, joints, positive weights, every
    influence's weight summing to 1) and its CPU skinning `Scene::skin` sums
    the four slots and then each further influence, in order.
  - The four-largest reduction, its bound (`INFLUENCE_BOUND_DIVISOR`) and
    provenance `reduced_influences` are retired. The player path refuses a
    drawn vertex past four influences by name, as it refuses render states
    (its scenes stay N3S1, PQ-280); any other non-looks scene (the Moradon
    worm path) is refused by the cooker. No pinned package's model has such a
    vertex. The strict skin readers (render detail, appearance, nameplates,
    target marker) keep refusing past four influences, as before.
  - This replaces D-175's influence rule; its weighted-joint skin past 64
    joints stays, now counted over every influence.
- **Considered:** keeping the reduction for the player path (code that no
  pinned data exercises; refusing is checkable); a variable-length vertex
  record (rewrites every vertex of every model); more slots in every vertex
  (16 times the joint bytes for every model); converting every model with
  such a vertex to N3MM (changes its atlas and its draw path).
- **Result:** on the operator's data the client's corners of looks 2600,
  5100 and 5200 are within 2.1 × 10⁻⁶ source units of KO's full sum (under
  D-175 the trees' were up to 0.043 away and 2600 was refused at 0.170). 5100 and 5200 now cook as
  N3MI models; their files are the only ones that changed in homeland zones 1
  and 2. 2600 gets past its influences and stops at two zero-length normals
  in its upper part (PQ-281). Zone 1 converts 44 of its 52 keys and zone 2
  44 of 52, as before.
- **Recorded in:** content/npc.md ("Influence tables", "KO looks import"), CONTRACTS (N3LK),
  protocol/README.md, tools/assetc/KO-CHARACTER.md, GAPS "NPC archetypes",
  FEATURES KOF-0015, PARITY, BINARY-INDEX KOF-0015.

## D-177 — 2026-10-16 A KO skin vertex normal with no direction (non-finite or shorter than 10⁻⁶) converts as its corner's face normal; KO's own lighting of it (no directional light) waits for the loaded-normal lighting item

- **Context:** PQ-281. Looks 2200 (harpy), 3800 (manticore) and 2600
  (centaur) of homeland zones 1 and 2 stop at their skins: the converter's
  reader refuses a non-finite vertex float (2200) and the cooker a normal
  shorter than 10⁻⁶ (`skin/normal`; 3800, 2600). KO draws each part vertex
  with its normal as loaded: the skin's mesh load reads it, the CPU skinning
  writes only the position, the part draw copies the normal into the
  fixed-function vertex unchanged, with lighting on and no normal
  normalisation set, so a zero or near-zero normal gets no directional light
  (binary chain, D3D8 behaviour by inference). n3e's lighting is its own
  direction-only lighting (KO-CHARACTER.md: the engine's simple lighting
  replaces KO material lighting); it cannot draw a vertex without directional
  light, and a normal with no direction cannot be normalised. Many such
  vertices are shared by two faces that face opposite ways, so a vertex
  normal rebuilt from its faces cancels to zero. The claims and their labels
  are in the evidence record.
- **Selected:**
  - `tools/assetc/ko_character.py` (`convert`): a drawn corner whose vertex
    normal is not finite or has a squared length below 10⁻¹² (the cooker's
    bound) is written with the unit normal of its own triangle, from the
    skin origins in file winding ((b − a) × (c − a), the side the loaded
    normals face), mirrored like every normal. A corner on a triangle whose
    cross product is zero is refused by name. Every other corner keeps its
    normal as read, so a model without such a vertex converts byte for byte
    as before. `rebuilt_normals` in provenance counts the vertices and
    corners.
  - The converter's skin reader takes a non-finite normal only for `convert`
    (an undrawn vertex is never written); the strict readers (render detail,
    appearance, nameplates, target marker) keep refusing it.
  - No format, cooker, client or engine change: the corner normal is an
    ordinary unit normal.
- **Considered:** KO's result in n3e (a zero normal drawn without
  directional light: the client, the cooker and an engine version would
  change, and the loaded-normal lighting item replaces that lighting anyway);
  a vertex normal from the sum of its faces (zero for two-sided vertices);
  a fixed normal (lights one side of a two-sided sheet only); refusing the
  looks (three homeland models stay missing).
- **Result:** a fidelity gap, not an exception: KO draws these corners with
  ambient light only, n3e lights them by their face. The queued item that
  draws KO's loaded normals as KO does (not turned by the joints, length as
  read, a zero normal without directional light) retires this rule.
- **Recorded in:** tools/assetc/KO-CHARACTER.md, content/npc.md ("KO looks
  import"), GAPS "NPC archetypes", FEATURES KOF-0015, PARITY, BINARY-INDEX
  KOF-0015.

## D-178 — 2026-10-16 A KO NPC state whose clip index is past its looks row's clip table converts as the clip KO keeps playing: the joints at frame 0 on a table without clips, clip 0 on a table of one or two

- **Context:** PQ-268 (child of PQ-069). Looks 14000, 14002, 24001, 30091,
  30092 and 30100 (the homeland monuments and camp gates) name
  `chr\default.n3anim`, a table without clips, and 24000, 24002 and 14001
  tables of one, one and two clips (local-asset), so the converter refused
  them and zones 1 and 2 converted 47 of their 52 keys each. n3e's looks
  entry (N3LK) carries four clips: idle 0, walk 2, attack 4, death 10
  (D-167). The claims and their labels are in the
  evidence record, its
  claims table.
- **Observed (binary, client `KnightOnLine.exe`):** the three clip starts
  (`0041be40`, `0041c160`, `0041c000`) start nothing for an index at or past
  the table's count, or on a table without clips, and leave the clip already
  playing as it was; every NPC clip start found (the stand, struck and
  dying states of the state setter `0045a2c0`, the move, the dying clip, the
  queued clip and the attack callers listed in the record's B4) goes
  through one of them. On a table without clips none of them starts a
  clip: the frame tick `00418b20` returns, and the render `004196a0`
  still poses every joint (`00418e00`) at the current frame, which the clip
  table set (`0041bd30`, or the `.n3chr` load `00418020`) left at 0 with no
  blend.
- **Inferred:** a table of one or two clips keeps its clip 0 playing in
  every state n3e carries (n3e never plays KO's walk clip 1, D-167); the
  joint slot `+0x20` samples the joint's keys at that frame, as the
  converter does.
- **Selected:** `tools/assetc/ko_npc_looks.py` (`clip_plan`): a table
  without clips converts every state as the rest pose
  (`ko_character.convert` with no clip index: the joints at frame 0 held,
  two keys 1/60 s apart, blend 0, no loop, no marker; every joint's rotation
  written as a held track so a skeleton without keys still has tracks); a
  table whose only carried clip is clip 0 (one or two clips) gives each
  missing state clip 0, converted as idle is (attack and death do not loop,
  as every attack and death clip); a table that has the walk clip but lacks
  attack or death (three to ten clips) is refused by name, because the clip
  KO keeps there depends on the state before (no row of the operator's
  table has such a table, local-asset). The converter's rest pose is
  refused for a table with clips, and a clip index on a table without clips
  stays refused (the player path). The report lists the clip each state
  takes. No format, reader, client or bound change; every other looks
  converts byte for byte as before.
- **Considered:** a looks-entry flag meaning "keep the clip already
  playing" (KO's exact rule: the client and N3LK would change, an engine
  version for nine models); refusing the nine looks (the homeland
  monuments and gates stay missing for PQ-219).
- **Result:** zones 1 and 2 convert 52 of 52 keys. Fidelity gaps, not
  exceptions: n3e restarts the reused clip, with its entry blend, at a state
  change where KO lets it run on, and n3e's death clip ends in its corpse
  state where KO's dying NPC leaves state 4, on the animation tick's path,
  only when the play count rises (by inference never on a table without
  clips; other paths unread, PQ-287); queued as PQ-287.
- **Recorded in:** tools/assetc/KO-CHARACTER.md, content/npc.md ("KO looks
  import"), GAPS "NPC archetypes", FEATURES KOF-0015, PARITY, BINARY-INDEX
  KOF-0015.

## D-179 — 2026-10-17 An NPC template carries its drawn scale (N3N4, engine 41); the server sends it as `Entity.scale` and the client applies it to the model, pick boxes, effect joints and name height

- **Context:** PQ-272 (child of PQ-069). n3e drew every NPC at its looks
  model's size; 47 of the 108 templates per OpenKO homeland zone have an
  `sSize` other than 100 (local-asset). The claims and their labels are in
  the evidence record.
- **Observed (binary):** the AI spawn load copies template `+0x28` (`sSize`)
  to record `+0x24` (AI `00438c42`–`00438c46`; also `00425911`), and both NPC
  info records send it as the fourth short after the id, `sSid` and `sPid`
  (`004221d5`, `0042246f`). Ebenezer's AI receiver stores that short at NPC
  `+0x22` (case 07 `00408f7d`, case 02 `00407987`) and every NPC-in builder
  read sends it after the looks key, the type byte and a u32 (`00479e7c`,
  `0047a462`, `0049da8c`, `00424322`, and case 07's inline record). The
  client's NPC-in reads it there (`005cd6d5`), multiplies it by 0.01
  (`[006a3b60]`), and passes it three times to the character's slot `+0x34`
  (`0041f800`), which stores it at character `+0x3c`/`+0x40`/`+0x44` and
  rebuilds the character matrix `+0x54` with it on the diagonal
  (`0043b650`); the character render passes that matrix with 256 to device
  slot `+0x94` (`004197e0`), and the actor pick tests the box with it
  (PQ-146; the part-mesh tie-break is D-138's correction, which n3e runs on
  the drawn, scaled triangles). The name callback places the name at
  y + h × s + 0.1 × h × s (`00459820`, actor `+0x90` = character `+0x40`).
- **Inferred:** that the matrix is the character's world (draw) transform:
  slot `+0x94` read as Direct3D 8 `SetTransform` and 256 as `D3DTS_WORLD`
  from the interface's method order.
- **Selected:**
  - An N3N3 template may carry `scale`, an integer percent 1–1000 (KO
    `sSize`; the reference rows hold 20–600, local-asset). A policy with any
    `scale` cooks as `N3N4` (model 4): N3N3 with a u32 scale after each
    template's tracing range (100 for a template without the key). Such a
    package is engine 41 (wire 30) and needs a looks table; every other
    package cooks byte for byte as before. Both readers take `N3N4` only at
    engine 41 and above, and refuse `N3N3` there.
  - The server keeps the template's scale in the NPC's instance rules and
    sends it as `Entity.scale` (field 33, output-only) for a templated NPC
    whose scale is not 100; every other entity sends 0, so older golden
    bytes are unchanged. The client refuses a scale on a player, on an NPC
    without a looks key, or above 1000, and treats 0 as 100.
  - The client multiplies the NPC's drawn vertices, its standing and
    death-pose pick boxes, its effect joint positions and its name anchor
    height (the style's NPC height and its padding) by scale / 100. Normals
    are unchanged (a uniform scale).
  - `tools/assetc/ko_npc.py` writes `scale` = `sSize` and refuses a row
    outside 1–1000; a caller cooking a package without a looks table passes
    `drawn_scale=False` and gets N3N3 templates without it (the reference
    stats and combat suites).
- **Considered:** a scale per looks entry (KO's scale is per template: two
  templates may share an `sPid` and differ in `sSize`); the client looking
  the scale up from its copy of the template table by entity name (PQ-263
  will make the name a display label); a new wire version (the field is
  additive and absent by default, as PQ-186's `World.traces`).
- **Bound, not a deviation:** KO takes any signed short; n3e refuses a
  scale of 0, a negative one or one above 1000 at cook and load. No
  reference row is outside 20–600.
- **Not carried (fidelity gaps):** the scale's other client uses, the
  walk/run clip threshold (`004647a0`, PQ-269) and the character LOD distance
  (`004196a0` divides by `+0x118` × `+0x3c`; n3e has no NPC LOD); per-model
  name height (actor `+0x17c`, PQ-262) — n3e multiplies the style's one NPC
  height.
- **Recorded in:** content/npc.md, CONTRACTS (NPC templates), protocol
  README, GAPS "NPC archetypes", FEATURES KOF-0015, PARITY, BINARY-INDEX
  KOF-0015.

## D-180 — 2026-10-18 The 1097 Karus homeland reads obj_ka_tree_brA's trunk from the 2004 client: a pinned correction of a 1097 install file that KO itself replaced

- **Context:** PQ-290. The user played the cooked KO maps and reported one
  tree type that looks disconnected partway up the trunk. A survey of every
  tree shape the five cooked maps place found one: `obj_ka_tree_brA` (54
  placements, the 1097 `karus_start` only), whose trunk stands 3.4 m (local,
  before the shape's scale) too low, so a stump sticks out of the ground and
  the crown floats above it with its own trunk ending in mid-air. The claims
  and their labels are in the
  evidence record.
- **Observed (binary, 1298 client `828ab0db…`):** `CN3Shape::Load`
  (`004445a0`) calls each part's `Load` (vtable `006a3e80` + `0xc` =
  `00443440`, which reads the pivot into part `+0x2c`), then sets the part
  matrix `+0x38` to the identity with the pivot as its translation and
  multiplies it by the shape's matrix (`0041dda0`, shape `+0x54`).
  `CN3SPart::Render` (`00443090`) sets that matrix as the world transform
  (`+0x94` with `0x100`) and draws the mesh's own vertices (`00441bb0`,
  stride `0x20`). No step recentres a mesh. n3e's bake applies the same rule.
- **Observed (local-asset):** every OPD that places `obj_ka_tree_brA`, in the
  1097, 1264, 1298 and 1453 installs, gives its trunk part
  `obj_ka_tree_bra_post.n3pmesh` the pivot (0.037, 0.018, 0.092). The 1097
  installer's mesh (SHA-256 `645099…8343`) is centred on its own box
  (y −3.44 to 3.44); the 1264, 1298 and 1453 installs ship another export
  (`eba7a6…dfe4`, y −0.19 to 6.62). Under the rule above the 1097 trunk spans
  y −3.42 to 3.46 while the crown parts start at 3.65; the later trunk spans
  −0.17 to 6.64. Every other tree trunk in the five maps reaches from the
  ground into its crown.
- **Inferred:** the 1097 client draws the tree the same broken way: its file
  formats are the ones the 1298 client reads, but its executable is
  ASProtect-packed, so its own part rule is unread (open gate).
- **Selected:** a correction of content, not of the client rule. `ko_bake`'s
  `CORRECTIONS_1097` names 1097 install files by base name with two pinned
  SHA-256 values, the 1097 file's and the 2004 client's (`CLIENT`, already the
  1097 bake's player and HUD source). For a 1097 zone whose OPD names such a
  file, the bake checks both hashes and reads the 2004 client's file in its
  place (`ko_scene.object_files` `substitutes`); a mismatch or a missing file
  refuses the cook by name. The package provenance records each applied
  correction (`zone.corrections`); a zone that names none cooks byte for byte
  as before (the 1097 El Morad homeland and Moradon keep their pins). The
  table holds one entry, the brA trunk. The 1097 crown meshes and the
  shared trunk texture stay the 1097 files: the later trunk joins them
  (measured and captured).
- **Considered:** leaving the 1097 data as it is (the tree stays broken, as
  the user reported); moving the 1097 trunk up by its own box (a placement
  no KO install has); reading every brA file, or every file that differs,
  from the 2004 client (it changes outputs that are already right: most
  differing 1097 meshes are consistent with their own pivots); a geometric
  rule that detects centred meshes (it would guess, and could move parts
  that are right).
- **Correction record:** BINARY-POLICY
  "1097 tree trunk content correction".
- **Recorded in:** BINARY-POLICY, MAP-EXPLORATION, GAPS, FEATURES KOF-0005,
  PARITY, STATUS.

## D-181 — 2026-10-19 The untemplated Moradon worm is drawn at its sSize through its NPC set's instance scale and the nameplate style's NPC height, not on the wire

- **Context:** PQ-288 (child of PQ-069). Since D-179 a templated NPC (N3N4)
  is drawn at its template's `sSize`, which the server sends as
  `Entity.scale`. The Moradon packages' one NPC, the worm (K_MONSTER row 750,
  `sSize` 120, local-asset), is an untemplated N3N2 reference NPC drawn from
  the package's NPC set (`npc-{idle,walk,attack,death}.bin`), so it stayed at
  its model's size. The claims and their labels are in the
  evidence record.
- **Observed (binary, re-read in PQ-288):** AI Server binds `sSize` after
  `sPid` (`0041737b`), the table load copies it into template `+0x28`
  (`00438139`), the spawn load copies that to record `+0x24` (`00438c42`) and
  the NPC info record sends it (`004221d5`); Ebenezer stores the AI's short at
  NPC `+0x22` (`00409139`) and writes it into the NPC-in record (`00479e7c`);
  the client's NPC-in reads it (`005cd6d5`), multiplies it by 0.01
  (`005cdd82`, `[006a3b60]` = 0.01) and passes it to the character's scale
  slot (`0041f800`), which puts it on the diagonal of the character matrix
  (`0043b650`); the name callback multiplies the name height `+0x17c` by the
  scale `+0x90` (`00459820`). Every NPC an NPC-in record creates gets it, the
  worm included.
- **Selected:**
  - `games/moradon/ko-reference.json` carries the worm's `sSize` (120, the
    operator's pinned OpenKO export; `tests/ko_npc_templates.py` checks the
    committed row against it).
  - The Moradon feature cook (`tools/assetc/moradon_features.py`) writes the
    four NPC clip scenes with the instance scale `sSize` / 100 (1.2), so the
    client's existing scene path draws the worm's vertices, effect joints and
    pick boxes at that size; the instanced scene (the editable decoration)
    keeps 1.
  - The feature HUD's nameplate style takes the NPC profile height (the worm
    skeleton's padded joint bounds, `ko_nameplates`) times the same factor,
    so the name sits at h × s × 1.1 as KO places it.
  - No format, engine, wire or server change: the scale is package data in
    files the readers already take. The worm's `Entity.scale` stays 0.
- **Considered:**
  - Making the worm an N3N4 template with a looks table (engine 41, the D-179
    path): it moves every worm rule (health, damage, XP, ranges, acquisition)
    into a template, changes the worm's wire looks key and settlement
    payloads, and needs combat columns the committed extract does not carry
    (PQ-261); that is the homeland population's path (PQ-219), not a size
    change.
  - A client-side factor for the untemplated NPC set: there is no field to
    carry it without a new engine version, and every engine from 38 on
    requires a looks table.
  - Scaling the model in the conversion (`ko_character.convert` `meters`):
    the same drawn result, but it hides the factor inside the vertices and
    joint translations; the instance scale names it.
- **Limits:** the pick box is built from the scaled joints and then padded
  (n3e's `targeting::model_box`), where KO pads the model-space box and then
  scales it with the character matrix (axes shorter than 0.5 m get the
  0.25 m pad on each side), so the worm's standing box is 0.813 m high where
  KO's would be 0.913 m (n3e's measured in the client, KO's computed from the
  unscaled box the client measured at 0.761 m): PQ-297. The target marker
  does not scale with the actor in n3e on either path: PQ-296, settled by
  [D-182](#d-182--2026-10-19-the-target-marker-follows-the-selected-actors-drawn-scale-the-cooks-npc-pair-for-an-untemplated-set-the-clients-factor-for-a-template)
  (the reading recorded here, that KO's symbol takes the selected actor's box
  corners `+0x11c`/`+0x128` through its matrix, was wrong: that branch is the
  picked scene object's). The walk/run threshold (PQ-269) and the label per model (PQ-262)
  stay open. The `--des` exploration replaces
  the worm's model but keeps the worm's scaled name height.
- **Recorded in:** GAPS, FEATURES, PARITY, content/npc.md, STATUS.

## D-182 — 2026-10-19 The target marker follows the selected actor's drawn scale: the cook's NPC pair for an untemplated set, the client's factor for a template

- **Context:** PQ-296 (child of PQ-069). n3e drew the target marker from the
  package's fixed player and NPC radius/height pairs (N3TM) for every actor,
  while since D-179 and D-181 NPCs are drawn at their `sSize`. The claims and
  their labels are in the
  evidence record.
- **Observed (binary, client):** the symbol routine `005c4e20` looks up the
  selected id (`[00818794]+0x454`) in the two actor maps (`0046b520`,
  `0046b4a0`). For an actor it scales the symbol by (2 × `0045a1d0`,
  1.3 × `00459ff0`, 2 × `0045a1d0`) (`[006a8540]` = 1.3); for an actor without
  a shape (`+0x450` = 0) those return `+0x168` × `+0x90` and `+0x17c` ×
  `+0x90`. The character is embedded at actor `+0x50` (`LEA ECX,[EBP+0x50]`,
  `005cdd89`), so these are its `+0x118` (the joint-bound radius `0041c300`
  writes), `+0x12c` (the padded joint box top) and `+0x40` (the scale `0041f800`
  stores, the NPC-in's `sSize` × 0.01). Only when no actor is selected does it
  take the scene-object pick `[00818794]+0xb14` and that object's box corners
  `+0x11c`/`+0x128` through its matrix `+0x54` (`005c4f13`–`005c4f4c`), which
  corrects the actor reading recorded in D-181.
- **Selected:**
  - The client multiplies the marker's pair by the selected actor's drawn
    scale, `Entity.scale` / 100 for a templated NPC and 1 otherwise
    (`target_marker_size`, `client/render/target_marker.h`): footprint,
    upright height and ground sample spacing.
  - The Moradon feature cook multiplies the N3TM NPC pair by the worm's
    `sSize` / 100 (`ko_target_marker.cook` `npc_scale`), as D-181 does for the
    nameplate style's NPC height; the player pair stays as measured.
  - No format, engine, wire or server change. The three Moradon feature pins
    change; no other pin does.
- **Considered:** the client multiplying by the NPC set's instance scale (it
  would cover the worm without a cook change, but an instance scale also
  carries a model's unit fit, as the `--des` exploration's does, so it is not
  the actor's KO scale); a scale field in N3TM (a format and engine change for
  a value the cook already knows).
- **Limits:** one NPC pair per package (the worm's), not one per looks model
  (PQ-300); the pair's height is the padded joint span where KO reads the
  padded box top (Tuarek 1.938 m against 1.798 m, the worm 0.739 m against
  0.526 m before scaling; PQ-301); no object targets.
- **Recorded in:** content/target-marker.md, content/npc.md, GAPS, FEATURES,
  PARITY, STATUS.
- **Amended 2026-10-19 (PQ-301):** the pair's height limit is closed. The
  cooks take the padded joint box top for the N3TM pairs and the nameplate
  style's heights (the stores of `0041c300` and the reads of `00459ff0`,
  `00459fa0` and `00459820`: binary; that `0041c300` runs at frame 0:
  inference from the call order, the reused-character path not traced); the
  radius is unchanged
  (evidence).

## D-183 — 2026-10-19 Equipped-item effects are an N3E2 record per appearance key, drawn for every player; a client-local Option.ini switches them

- **Context:** PQ-211. KO attaches an fx.tbl weapon effect to an equipped hand
  plug when the item's extension names one and draws it for every player while
  `Option.Ini` `WeaponEffect.EffectVisible` is on. The claims and their labels
  are in the evidence record.
- **Observed (binary, client):** `0045c6e0` picks the id (`0045ccc0`, else
  Item_Ext column 5), loads the main bundle (id) and tail (id + 1) through
  `00415370` with a trace colour (`0045cb5e`); `004158d0` calls `00415910`
  only while `006e268e` (`0064b9b0`, default 1) is set, which draws the plug's
  FX mesh three times with the main part's frames i, i + 1, i + 2 (as placed,
  turned −π/36 and moved +v, turned +π/36 and moved −v) and moves two tail
  bundles over the mesh box every frame.
- **Selected:**
  - The effect is package data on the appearance key: `effects.bin` becomes
    `N3E2` (N3EF plus the records). N3V1, N3D2, the wire and the server are
    unchanged, because the server already projects public keys from committed
    equipment; a new magic, accepted where N3EF is, keeps older readers failing
    closed, as the input map's and HUD's later magics do, without an engine
    version.
  - The engine draws generic records (frames, copies, jitter, tail box, tail
    links); KO's angles, constants and table rules stay in the cook
    (`tools/assetc/ko_weapon_fx.py`).
  - The switch is a client-local `Option.ini` read once at start
    (`$XDG_CONFIG_HOME/n3e/Option.ini`, KO's section, key and default), since
    n3e has no options page yet (PQ-048). It is presentation only.
  - The tail, an endless emitter in KO, is a cooked two-second clip the client
    restarts every half clip (a fidelity limit, not a correction).
- **Considered:** an engine version for N3E2 (nothing else in the package
  changes, and the magic already refuses older readers); the effect on N3D2's
  appearance geometry (the textures, tails and clips are effect data, which
  N3EF already holds); the server sending the KO item number (it would expose an
  identity the public key already stands for, and give the client a table it
  does not need).
- **Limits:** no swing trail, hit spark or preview effect; the unique, bow and
  Viper bundles are refused by the FX reader; the FX mesh is drawn at its
  highest level of detail; the tail is resampled at 30 Hz.
- **Recorded in:** content/appearance.md, content/presentation-events.md,
  CONTRACTS, GAPS, FEATURES, PARITY, STATUS.

## D-184 — 2026-10-20 The 2233 equipment glow is an N3E3 record per appearance key, cooked only on request from the player's 2145 tables, and drawn for every player behind its own Option.ini key

- **Context:** PQ-315. The user asked for glowing weapons and armour and for
  newer-client features labelled by version. The pinned 1298 client has no such
  glow (its part draw zeroes the material emissive, PQ-265 B7) and stays the
  source of truth; the 2233 image (PQ-314, a secondary reference) glows equipped
  parts and hand plugs by code. The claims and their labels are in the
  evidence record.
- **Observed (2233 IDB, binary for that image only):** `CPlayerBase::Tick`
  (`0057b3a0`) calls `0056ea30` for every player; it keeps one timer per player
  (rise to 1 s, hold to 3 s, fall to 0 at 5 s, restart past 5.5 s) and, for each
  equipped part slot (parts 0, 1, 3, 4, 5) and hand plug whose Item_Ext byte
  `+0x4c` is 11 or 12, writes the material emissive (the pulse or 1.0) and
  MODULATE or MODULATE2X from the u32 at `+0x90` % 100; `0042cf30` keeps that
  emissive and applies the stage-0 op; `0046fca0` passes it to the character
  shader as `g_vEmissive`; a skeletal plug hands it to its inner parts
  (`0042de90`, `00430f40`).
- **Selected:**
  - The engine draws a generic record: an appearance key, an emissive colour, a
    texture modulate (1, 2 or 4), and a steady or pulse wave with its rise, hold,
    fall and period. `effects.bin` becomes `N3E3` (N3E2 whose effect list may
    be empty, then up to 16 glow records). The client adds colour × intensity to
    the key's lighting, clamps at 1 and scales by the modulate, on one clock per
    actor from its first draw. N3V1, N3D2, the wire and the server are
    unchanged: the server already projects public keys from committed
    equipment and stays authoritative for them; the glow is presentation only.
    A new magic keeps older readers failing closed, as N3E2 did, without an
    engine version.
  - KO's rules (attribute 11/12, column 45, the item-number rule, the timing)
    stay in the cook, `tools/assetc/ko_glow_2233.py`. It runs only with
    `ko_bake.py … --features --glow-2233` (`tools/play-moradon --glow-2233`), reads
    the player's own 2145 unpack through `tools/ko-reference/tbl_2145.py` (the
    pinned installer's manifest, every table checked against it), and writes a
    package of its own, `moradon-glow2233`, on its own stack (port 7803). No
    default cook reads 2145 data, so every existing package and pin is unchanged.
  - Which items glow is the package's mapping row (`glow_2145_item`, a 2145 item
    number) with two n3e guards, not KO behaviour: an extension row whose
    Item_Ext column 3 is non-zero and names another base item is refused as
    that item's (the column is `dwBaseID`, `GameDef.h:889`, source-only;
    `0052f660` does not test it and whether 2233 tests it elsewhere is unread),
    and the row's artwork must be that item's model. Moradon's Round Shield is
    2145 item 170251015 (a pulse at 2×). The 1298 items carry no glow attribute;
    under the 2233 rule alone the blade and two-hander artwork reach 21 and 14
    glowing item numbers, all through rows that name `[Test]Raptor` and its
    neighbours, which the column-3 guard refuses, and the armour has none, so
    only the shield glows there.
  - The switch is n3e's own `Option.ini` key, `[Addition2233] EquipmentGlow`,
    default 1: the glow exists only in a package the operator cooked on request,
    2233 draws it with no switch, and the key lets the player compare with the
    1298 look. The section name, the package name, the client's start line and
    the launcher's banner label it a 2233/2145 addition.
- **Considered:** a fixed glow per item in package data with no table read (it
  would carry KO table values in the repository and could not be checked
  against the artwork); reading the 2145 tables in the default Moradon cook
  (it would make the default package depend on optional data and change its
  pins); default off (the package is already an explicit opt-in, and the user
  asked to see the glow); a server-sent mode (the mode is presentation data that
  the public key already selects).
- **Limits:** the player byte `+0x2f0` that gates `0056ea30` and the meanings of
  attribute 11/12 and column 45 are unread, so n3e always draws it; `0056e680`
  (zones 85 and 89) and slot 0's part 2 race case are not modelled; skeletal
  plugs wait for PQ-317; KO's hold keeps the last rise value (just under 1) where
  n3e holds 1; reading the 2145 tables with the 2233 rule and layout is an
  inference; no 2145 armour artwork can be read yet (PQ-308).
- **Recorded in:** content/appearance.md, content/presentation-events.md,
  CONTRACTS, GAPS, FEATURES, PARITY, STATUS, tools/ko-reference/README.md.
- **Amended 2026-10-20 (PQ-320):** a weapon glows too. A mapping row may name
  `glow_2233_source`, a hand plug that only the `--glow-2233` cook draws in
  place of the row's artwork; the item, its slots and the server's appearance
  key stay the row's, so equipment and the wire are unchanged and the default
  cooks never read it. The guards are unchanged and check the replacement.
  Moradon's two-hander is drawn there as Durandal (`1_2631_00_0`), 2145 item
  126311011 (Item_Ext_26 row 11, column 3 = 0: attribute 11, column 45 = 11), a
  pulse at 2×, the shield's mode. Chosen over the other guard-passing 1299
  artwork (Mirage `1_2641`, Slayer `1_2121`, Mirage Dagger `1_1111`) because it
  is a two-handed sword (class 22) like the row's Two-Handed Sword, so the
  slots, the left-hand block and 1298's ready pose (`0045bfe0`, class 22 → 50,
  binary) still fit, and the row carries no weapon effect (`ko_item`) to
  orphan; the blade's row does (PQ-211). Considered: a new demo item (a
  feature-data change that would move the default packages' pins); replacing
  the blade's artwork (two rows and its PQ-211 effect). The two-hander's icon
  and name stay its own in the glow package
  (evidence).
- **Amended 2026-10-20 (PQ-321):** the replaced artwork's name and icon follow
  it. A row with `glow_2233_source` names `glow_2233_label` and
  `glow_2233_icon`, which must be a 1298 Item_Org row of the replacement's
  model (name column 3, model column 7, icon column 8), and the glow cook alone
  writes them into the glow package's own `inventory.bin` and item icon map.
  The label is server package data, so it changes in that package's copy, which
  the server loads as its inventory policy; nothing is overridden on the client
  and the default packages keep their label, icon and pins. Moradon's two-hander
  is Durandal there (1298 Item_Org 126310000, icon 12631000; the icon path is
  `006157b0`'s, KnightOnLine.exe, binary). Considered: a client-side display
  override (it would let the client disagree with the server's item data); a
  label derived at cook time from the table with no package field (less
  reviewable, and a model can have several Item_Org rows); a new demo item
  (moves the default pins). A changed label changes the bag definition, so
  realms of an earlier glow package refuse it; the launcher already starts a
  new realm per package release
  (evidence).
- **Amended 2026-10-20 (PQ-318, research):** the Limits' open gates are read in
  the 2233 image, and the decision stands. `CN3Chr::CN3Chr` sets the gate byte
  `+0x2f0` to 1 (`00445e26`), and the scans found no store that clears it. The
  inventory preview character was not found to glow. Both are inferences
  within the scans' limits, and both match n3e. Attribute 11 and 12 are
  labelled "(Reverse upgrade item)" and "(Reverse unique item)" (tooltip
  `005aa8e0`; names from the 2145 texts, local-asset; inference for 2233), and
  for attribute 11 column 45 % 100 is printed as "(+N)". No 2233 path that
  tests Item_Ext column 3 was found (inference within the scans). The column-3
  guard stays n3e's own mapping guard, as this decision records: it protects
  which 2145 item number a demo row may claim (such as 120010884, whose row
  belongs to `[Test]Raptor`), and which numbers a 2145-era server issues is
  unread. No client behaviour differs. `0056e680` is the Guardian Deity
  transformation's glow in zones 85 and 89 (PQ-326, after transformations).
  The part-2 case belongs to races 6 and 14 (Kurian/Porutu, by inference),
  which n3e does not have
  (evidence).

## D-185 — 2026-10-20 The 2233 HDR bloom is a generic package post-process (N3PF), cooked per zone from the player's 2145 hdr.n3pp, drawn only with Option.ini [Addition2233] HDR=1, with an asynchronous read-back and a floored average

- **Context:** PQ-316. The 2233 image (PQ-314, a secondary reference) runs a
  screen post-process after the world and before its UI; the 2145 install
  ships its shaders (`SHC/pp.fx`, PQ-312) and per-zone settings
  (`Zones/hdr.n3pp`). The pinned 1298 client has none and stays the source of
  truth. Claims and labels are in the
  evidence record.
- **Observed (2233 IDB, binary for that image only; pass bodies 2145
  local-asset):** `00537030` draws the world into an A8R8G8B8 scene target
  (`00474b30`, targets `00474660`) and runs `00476b40` before the HUD; the
  passes are P0 bright pass (`00475000`), P1 then P2 five times down to one
  texel and a read-back of R/G/B / 255 (`00475350`), P3 4×4 downscale
  (`00475860`), P4/P5 nine-tap blur whose normalised Gaussian weights
  (variance 1.0, `00477bd0`) are multiplied by the zone's `+0x8c`
  (`004759f0`), and P6 (`00476690`): adapt by at most 0.3 × frame time
  (`00b905a8`, a double), then scene + bloom through an extended Reinhard tone
  map with white point max × (1 + `+0x8c`), exposure, lift and saturation.
  `hdr.n3pp` rows (`00477860`) feed threshold, `+0x8c`, exposure, saturation
  and lift on each zone entry (`00476f50`; defaults 0, 1.5, 1.2, 1.2, 0).
- **Selected:**
  - The engine gets a generic post-process: a package `postprocess` record
    (threshold, bloom, exposure, saturation, lift, adapt_rate,
    blur_variance) cooked to `postprocess.bin` (`N3PF`, seven f32), needing
    presentation and engine 33 like `effects.bin`. The client runs the fixed
    chain (its own GLSL, written from the reading; no 2145 shader bytes) over
    the world before the HUD. The server checks the file's bounds, hashes it
    with the release and otherwise ignores it: presentation only, no wire or
    authority change. A package is one zone, so "per zone" is the cook's
    choice of the zone's row, as for the zone's name distance.
  - KO's `hdr.n3pp` reading, the zone key and the 2233 constants (0.3 per
    second, variance 1.0) stay in the KO cook, `tools/assetc/ko_hdr_2233.py`.
    It runs only inside `ko_bake.py … --features --glow-2233`, the opt-in
    2233/2145 additions package (`moradon-glow2233`), from the player's own
    2145 unpack with both files checked against the pinned installer's
    manifest; no default cook or pin changes. Moradon is row 210: threshold
    0.367, bloom 0.7, exposure 0.1, saturation 1.0, lift 0.65.
  - The switch is n3e's own `Option.ini [Addition2233] HDR`, **default 0**:
    the item asked for it off; it relights the whole scene away from the 1298
    look (unlike the equipment glow, which touches only the glowing items);
    2233 itself has a switch in its options window (`btn_state_hdr`,
    option `+0x149`, `007d65d0`) whose default was not read.
  - **Read-back:** 2233 reads the one texel back synchronously each frame
    (`GetRenderTargetData` and a lock). n3e reads it into a ring of three
    pixel-pack buffers with a fence each and takes the newest completed one
    without waiting; with all three in flight no read is issued that frame.
    Only the first frame after the targets are built reads synchronously, so
    the first-frame snap (`+0x73`) uses that frame's value as 2233's does.
    The measured values are therefore one to three frames old; adaptation at
    0.3 per second makes that invisible except as that latency.
  - **Correction (BINARY-POLICY record):** n3e floors the adapted average and
    maximum at 1/255 before the composite's divisions. 2233 divides by them
    (pp.fx P6 preshader `rcp`), and a read-back of 0 (a frame whose 2×2
    blocks are black) drives the adapted value to 0, so every pixel becomes
    ∞ × 0 or ∞ / ∞.
- **Considered:** a fixed tone map with no read-back (it drops the
  adaptation the item names); a synchronous read like 2233's (a pipeline stall
  every frame); a separate `--hdr-2233` package and stack (one more package,
  port and launcher mode for data that already sits in the additions cook);
  default on (against the item; it changes every pixel of the 1298 look);
  half-float targets (2233 renders 8-bit, and its reduction clamps there);
  the 2145 DOF technique (2233 never runs it by name; out of scope).
- **Limits:** the 2145 exe is packed, so the 2145 field order is 2233's
  reading applied to the 2145 file (inference); the HDR sky of `Zones.tbl`
  column 9 is not drawn (queued as PQ-322); D3D9's linear filtering is assumed for
  every target from `00476b40`'s sampler 0 set-up and the scene start's
  sampler 1 set-up; n3e's targets follow the window size, KO's are built
  by `00477030` at start and on the options apply (`007d65d0`); no reference-rig comparison.
- **Recorded in:** content/presentation-events.md, CONTRACTS, GAPS, FEATURES,
  PARITY, STATUS, docs/ko/BINARY-POLICY.md, tools/ko-reference/README.md.

## D-186 — 2026-10-20 The 2233 cospre attachments are generic attached characters on appearance keys (N3AT): package equipment slots carry what is worn, a package table says what each key attaches and how it lights, and the client draws it for every player

- **Context:** PQ-328, from PQ-325. The 2233 image (PQ-314, a secondary
  reference) draws wings, fairies and emblems as attached characters
  (`CPlayerWing`); the pinned 1298 client has none and stays the source of
  truth. KO sells these items. The claims and their labels are in the
  evidence record.
- **Observed (2233 IDB, binary for that image only):** `00579560` attaches a
  `ChrTypePartItem.tbl` row (file, column 3, joint, slot, column 6) through
  `00568d80` into one of two `CN3Chr` slots; `CPlayerBase::Tick` calls
  `0056a710` for every player with one, which places each slot's character on
  the player joint (`00430440`, `0042c6e0`), picks its clip from the player's
  state (moving: clip 0 at 1.35; standing or sitting 1, attacking 3, struck 2,
  dead 5) and calls `00569590`, which advances one timer per player inside its
  slot loop (so two attached slots double the pulse rate) and lights every
  part with the pulse at MODULATE2X when column 3 > 0, else part 0 alone at 2×
  with its `+0x11e` left set (no visible emissive); `00568f30` draws slot 0
  only while `[Effect] Wing` is on (default 1).
- **Selected:**
  - **What is worn is server state, already.** Equipment slots are package
    data (N3Q1, up to 16); a cospre slot is one more package slot, its items
    package items that fit only there. The server validates every equip
    against that policy (`incompatible_slot` otherwise), commits the bag in
    Postgres (BagState, bound to the bag definition's hash per realm, which
    already refuses a changed slot set without an explicit migration), and
    projects public appearance keys from committed equipment only (wire field
    20). No server rule, wire field, schema or migration changes, and no client
    statement of what is worn is read. The new state is bounded by the existing
    16-slot and 128-key limits.
  - **What a key attaches is package presentation.** `attachments.bin`
    (`N3AT`) gives, per appearance key (1–16 entries): the wearer's skin joint,
    a scale, a group (0–15, at most one drawn per wearer, the last key in its
    list winning), an optional flag (drawn only with the client option), an
    emissive flag, a modulate (1, 2 or 4) and how many leading indices are lit
    (all, a first part, or none; a whole number of render runs), with four
    clips; the header gives the pulse (rise, hold, fall, period), its colour,
    and whether the wearer's one clock advances once per attachment (2233) or
    once per frame. Models are `attachment-<i>.bin` in the looks model formats
    (N3NM, N3MM, N3NI, N3MI), so a package with N3AT is engine 38 at least.
    Both readers check the table and model headers; the client also checks the
    joint against the player skeleton and the lit count against the mesh. A new
    file keeps older readers failing closed (their release file sets refuse
    it), so no engine number changes and no existing package moves.
  - **KO's two quirks are reproduced, not corrected.** The shared timer's
    double rate with two attachments and the unlit part 0 under column 3 = 0
    look unintended, but nothing shows a failing invariant or a way to exploit
    them; they change only how fast and where a cosmetic glow shows. Under
    BINARY-POLICY that is no ground for a correction, so a KO cook (PQ-331)
    selects them (`per_attachment`, `lit` = the first part with no emissive); another
    game's package need not.
  - **Option:** `Option.ini [Effect] Wing`, 2233's own key (`009e0883`,
    default 1), hides the optional attachments; the clock still advances, as
    `00569590` does not read it.
  - **Paid items:** mechanics only. A package grants the items (the fixture's
    are starting items); none is offered by a shop; mall delivery against
    operator entitlements stays PQ-095 and PQ-096. No payment path.
- **Considered:** a server-side cospre equipment subsystem with its own
  durable table and wire message (the generic slot set already does this,
  with its validation, persistence and projection, and a second store of worn
  items could disagree with the bag); drawing attachments as N3D2 appearance
  meshes on the wearer's skeleton (a wing has its own skeleton and clips);
  per-slot clocks (would correct the double rate without evidence of a bug);
  skipping the clock advance for a hidden slot 0 (2233 advances it).
- **Limits:** no KO wing is cooked yet: the 2145 parts sit in its Item pack
  (PQ-308) and every 2145 `.n3anim` clip table that holds a clip is
  enciphered (410 of 412 files: records of 76, 84 or 92 bytes whose first 16
  bytes are the same in every file; local-asset), so the opt-in
  2145 cook is queued (PQ-330, PQ-331). The 2233 source of the attached
  character's facing is not traced (`0056a710` passes only the player
  position, `+0xd8`–`+0xe0`, to vtable `+0x2c`); n3e places the model in the
  wearer's frame (position and facing) times the joint, the plug rule (D-081).
  Not modelled: the race 6/14 joint `0x2c` and scale 1.1, zones 85 and 89,
  the other-player load queue (one per tick), NPC attachments
  (`0053e050`), the inventory preview's second character (`+0x5a4`), the
  `+0x3e4` = 7 branch of `00579560`, the fairy's request loop (PQ-329); the
  clock advances only while the wearer is drawn.
- **Recorded in:** content/appearance.md, CONTRACTS, GAPS, FEATURES, PARITY,
  STATUS.

## D-187 — 2026-10-20 The 2233 skeletal weapon plugs are N3AT plug entries: an attached model on the hand joint with the plug's placement, played on its own clock through a package clip map, and a hand key that draws no rigid mesh

- **Context:** PQ-317, from PQ-302, PQ-308, PQ-314 and PQ-330. In the 2233
  image (a secondary reference) a hand item whose Item_Org row has `+0x90` set
  loads a `.n3chrplug`: a whole animated character on the hand joint
  (`CN3ChrTypePlug`). The 2145 data has 38 of them, among them the
  `<selfname>'s Azagai` bow. The pinned 1298 client has none and stays the
  source of truth. Claims and labels are in the
  evidence record.
- **Observed (2233 IDB, binary for that image only):** `CPlayerBase::PlugSet`
  (`00574830`) makes the skeletal plug (`CN3Chr::PlugSetNew` `0043fd30`) when
  the row's `+0x90` is non-zero, then for both kinds of hand plug sets a
  uniform scale of the plug's scale y × the player's height / 1.8 (`00550ab0`,
  the double at `00b907b8`) and overwrites the plug's joint with the looks
  row's hand joint (`MOV [EBP+0x6c],EAX` at `00574b70` and three more). The
  plug matrix is scale × the file's rotation with the scaled position
  (`0042d800`); each frame `00431060` copies the parent's joint matrix for that
  joint and `00434980` makes the inner character's world matrix plug matrix ×
  `+0x124` (identity: set so by the header load `00448650` and written nowhere
  else by the scans) × joint matrix × the inner character's own transform, then
  sets its clip with `00432760(+0x368, +0x36c, FLT_MIN, 0, 1)` and ticks it on
  its own clock (`00433b30(FLT_MIN, …)` → `0042e070`: frame += speed × frame
  time × the clip's fps; at the end a clip loops back by its length, or, when
  `+0x36c` was set, holds its end). `00432760` ignores the plug's current clip
  index and any index at or past the table's count. In the parent's render
  (`00435440`) the plug's clip comes from `0042df00` with the parent's clip
  index when the parent's byte `+0x2ac` is set, else is that index itself.
- **Selected:**
  - **N3AT plug entries.** Entry flag bit 2 marks a skeletal plug. After its
    four clip records it carries a 3×4 placement (the model's frame in the
    joint's, column vectors) and a clip map of 1–64 rows (kind, id, slot,
    once): kind 0 is a wearer pose state (0–9), kind 1 a combat-animation clip,
    kind 2 a skill animation. The client draws the model at wearer frame × the
    joint's posed matrix × placement × scale, every frame, for every player. Its
    clip follows the map: the row for the wearer's drawn clip (the casting
    skill's animation while it casts, else the combat clip or pose state the
    wearer is drawn with) names a slot; a different slot restarts at that moment
    and plays once and holds its end when `once` is set, else loops; the same
    slot, and a clip with no row, keep what plays. The model starts on slot 0,
    looped. A plug entry is never optional, lit or emissive, and does not
    advance the wearer's pulse clock. Both readers check the bounds, the kinds
    and duplicates; the client also checks the ids against the package's
    combat clips and skills.
  - **A plug key draws no rigid mesh.** An N3D2 appearance whose maximum-detail
    mesh is empty is accepted only when an N3AT plug entry names its key
    (client). 2233 draws no plug mesh for such an item (`00433af0` →
    `0042d8b0` draws nothing without a mesh; the Azagai plug names none).
  - **Engine 38+ without NPC templates.** `npc-looks.bin` is required exactly
    when the package is engine 38 or later and has NPC templates (both
    readers); before, every engine 38+ package had templates (N3LK required
    them), so every existing package reads the same. Such a package is wire 30,
    as every engine 38+ package; wire 30's template fields are output-only and
    empty for an untemplated NPC.
  - **The KO cook** (opt-in, `ko_bake.py … --features --glow-2233`, from the
    player's pinned 2145 install, `tools/assetc/ko_chrplug_2145.py`): the plug
    from the Item pack (PQ-308 reader), the inner `.n3chr` read to its eighth
    field as both 2233 loads do (`0044a990`, `0044a030`; the trailing copy of
    the plug record is ignored), its skeleton, part, skin and texture with the
    1299 readers, the clip table through `anim_2145.to_1298` (PQ-330); the
    placement is the plug matrix at the looks row's hand joint with the
    height / 1.8 factor, as n3e's rigid plugs already use; the map applies
    `0042df00` to the KO clip index each of the package's player clips and
    skill animations was cooked from. The 2145 item is a new package item in
    that package only; the server validates its equip as any other.
  - **The key sampler** takes a frame whose key index (truncated) equals the
    count as the last key, as 1298 (`00427640`, PQ-266) and 2233 (`0044b450`,
    `0044b560`) do, instead of refusing it; the Azagai's `magic` clip ends at
    frame 195, index 97 of 97 keys. A frame past that is still refused (KO
    leaves the joint unchanged there). Every clip the readers took before
    converts as before.
- **Considered:** baking the placement into the model's root joint (hides the
  plug matrix in the model, and n3e's skeleton reader would carry a scaled
  root); the four wearer-state clips of D-186 (cannot loop on death, restart on
  every state change, and have no cast state, so the bow would not play as
  2233 plays it); a degenerate triangle as the plug key's rigid mesh (draws
  nothing but is fake geometry); templated NPCs for the Moradon additions
  package (a large unrelated change); its own package (the additions package
  is where PQ-333 puts the rogue).
- **Limits:** the plug's FX mesh, its weapon effect and trail, and the glow
  2233 hands to the inner character (`0042de90`, `00430f40`) are not drawn
  (queued; the glow since PQ-337, below); the inner character's level of detail follows its parent in 2233
  (`+0x194`) while n3e draws the model's one mesh; the 2233
  struck clip (n3e has no struck state).
- **Amended (PQ-338, 2026-10-20):** the item icon is no longer a limit. The
  cook adds each skeletal plug item to that package's own icon map with its
  2145 icon by the 2233 rule (`009b3fc0`), read from the player's 2145 UI
  pack; an icon map entry may now name its own source and the 2233 rule
  (`ko_item_icons.cook`), which only this cook writes, and the HUD cook reads
  4-byte textures as 1298's `0043f090` does. Considered: naming the icon in
  `skeletal-plugs-2233.json` (PQ-321's pattern; redundant, since the 2145 rows
  give it and the label already comes from them) and copying the icon into the
  1298 client tree (writes outside `build/`). D-188 records the clip map applied to
  other players.
- **Amended (PQ-337, 2026-10-21):** the glow is no longer a limit. A plug
  entry stays unlit, at modulate 1 and outside the N3AT pulse, but its key's
  N3E3 equipment glow, when the package has one, shades the plug's whole model
  on the wearer's glow clock (2233: `0056ea30` → `0042de90` → `00430f40`, the
  colour and 2X flag copied into every inner part each frame); the glow cook
  gives a skeletal plug row its record as its own 2145 item, and the opt-in
  package carries the Azagai's +1 and +10 grades (Item_Ext_33 rows 1501 and
  1510) on the same plug model. The weapon effect is located: 2233 draws it on
  a skeletal plug as on a rigid one (vtable `+0x20` `00433af0` in both plug
  vtables → RenderFX `004304c0` on the embedded FX mesh at the plug matrix on
  the hand joint, set by `PlugSet` through `00437510`); it stays a limit
  because the Azagai's bundles (32120, 32121) are FX bundle versions 6 and 4,
  which n3e's reader refuses (PQ-339). Considered: giving plug entries their
  own glow fields in N3AT (a second copy of what N3E3 already says for the
  key); drawing the glow with the N3AT pulse (2233 uses the equipment glow's
  timer, not the CPlayerWing's).
- **Amended (PQ-339, 2026-10-21):** the weapon effect's main bundle is no
  longer a limit. A plug entry's key carries it as an ordinary N3E2 record:
  the cook reads the 2145 bundles in the 2233 layout (`0057f0b0`, `00589370`
  and the part loads; the 1298 reader unchanged) and draws 32120 on the
  `.n3chrplug`'s FX mesh at the plug placement on the hand joint (the rigid
  rule, `ko_weapon_fx.placed`), its DXT5 frames from the player's 2145 fx pack;
  fields 2233 added are drawn only at the values that leave RenderFX's path as
  1298's (`004304c0` reads the part's flags, blends, frames and the billboard
  tick's frame `005946a0`), any other value refused. The tail (32121) stays a
  limit (PQ-341). Considered: a separate N3AT field for a plug's effect (N3E2
  already keys effects by appearance key, and 2233 draws it on the parent's
  joint, not the inner character's).
- **Amended (PQ-341, 2026-10-21):** the tail is no longer a limit. The cook
  samples it (`ko_fx_tail_2233`) as 2233 ticks the two copies RenderFX
  (`004304c0`) moves to FX box points: mesh parts (a CN3FXShape turned by
  Rx × Ry × Rz of age × rotation, its scale keys wrapping, `0059a6f0`,
  `00599920`, `0059a1f0`) as triangle batches and particle parts (emitter
  kinds 1 and 2, `00590570`, `005915e0`) as quads, into the record's N3E2 tail
  clip; a link is the shortest of 1–10 s that every particle outlives no more
  than and that holds whole cycles of every mesh, so the client's N3EF clip
  bound rose from 10 s to 20 s (still 600 samples), and keys wearing the same
  tail share one clip. 2233's camera-distance particle thinning (`00592900`)
  is a fidelity gap (PQ-342). Considered: a 10 s clip (5 s links; one mesh's
  blink rhythm would restart off its cycle every link); a looping mesh record
  apart from the links (a format change for what the links already carry).
- **Amended (PQ-342, 2026-10-21):** the camera-distance particle thinning is
  no longer a gap; its format and rule are D-189.
- **Recorded in:** content/appearance.md, CONTRACTS, GAPS, FEATURES, PARITY,
  STATUS.

## D-188 — 2026-10-20 A skeletal plug follows the mapped clip on every player, the local player's rule in 2233, because 2233 reads an uninitialised byte for the others

- **Context:** PQ-317. The rule and evidence are the
  correction record.
- **Observed (2233 IDB):** the parent character's byte `+0x2ac` picks the
  plug's clip rule (`00435b12`). The player's character is embedded at player
  `+0x5c` (`CPlayerBase::CPlayerBase` `00578dd0` constructs it there,
  `00578e1d`), so the byte is player `+0x308`. Its only writer the scans found
  is `0056d4a0`, called once, by `CPlayerMySelf::CPlayerMySelf` with 1
  (`00558e4f`). `CN3Chr::CN3Chr` (`00445c70`) and `Release` (`00441d30`) set
  `+0x2ad` but not `+0x2ac`; another player is made by `operator new(0xcf8)`
  (`0052dcfc` in `MsgRecv_UserIn`) with no zeroing before `0055ccd0`. So the
  local player's plug plays the mapped clip, and another player's follows
  whatever byte the heap held.
- **Selected:** every player's plug follows the mapped clip (the map of D-187
  is applied to every wearer). This corrects a logic bug: the same equipped
  item on another player animates by uninitialised memory, an indeterminate
  result, and the direct rule would play the bow's `attackbreath`, `attack` and
  `die` clips for the parent's indices 1–3 (walk, run and walk back in
  ko-src's naming, source-only). No exploit is
  claimed; presentation only, in an opt-in 2233/2145 addition.
- **Considered:** the direct rule for other players (what a zeroed heap would
  give; not what the code defines, and not deterministic in 2233).
- **Limits:** the scans cover IDA function bodies' `[reg+disp]` writes of
  `0x2ac` and `0x308`; a write through another base or a block copy would not
  be seen.
- **Recorded in:** BINARY-POLICY, content/appearance.md, the evidence record.

## D-189 — 2026-10-21 The 2233 tail particles' camera-distance thinning is an N3E4 rule per tail-clip particle batch, applied by the client to cooked emission candidates

- **Context:** PQ-342. 2233's particle tick (`00592900`, assembly
  `005929ac`–`00592a37`; a secondary reference, 1298 stays the source of
  truth) sets the live count each tick from the camera's distance d to the
  part's bundle: the pool (`+0x428`) when d < near, else
  trunc(pool × (far − d) / far), negative past far; near and far are the
  version-9 values `+0x694` / `+0x698` when positive, else 10.0 (`00b8fbb8`)
  and 30.0 (`00b8fe4c`); the version-6 byte `+0x464` switches it off. The emit
  (`00592740`) runs only while the live particles (`+0x448`) are at most that
  count and takes the batch from the free pool (`005901b0`, `00590570`);
  live particles are never cut; the render (`0058e880`) draws none at a count
  of 0. n3e's tail clips are baked (PQ-341), so the rule must work on cooked
  particles, and it depends on each viewer's camera.
- **Selected:** a ruled part's cook writes every emission as a candidate
  (those the full pool takes draw from the part's generator as before, the
  rest from a second one), and `effects.bin` becomes `N3E4`: N3E3 whose glow
  list may be empty, then 1–64 rules, each on a tail clip that no binding plays
  and one particle batch material (texture, blends, flags) with a pool (1–1024)
  and near and far (0 < x ≤ 1000 m). The client keeps per tail link and rule
  which candidates it took: at each sample it reaches, the candidate born then
  is taken when the taken ones alive at the previous sample are at most the
  target at the camera's current distance to the link's newest tail point and
  fewer than the pool, counting with them the taken live ones the earlier
  link of its chain still draws (a chain is one 2233 tail copy, whose live
  list is one); it draws the taken ones, none at a target of 0. Within
  near a chain's first link draws exactly PQ-341's records; a later link
  starts while the copy's shared pool is still held by the older link
  (PQ-341 gave each link its own pool), so a part that fills its pool takes
  other candidates for the rest of that link's emission, within one particle
  of PQ-341's count once the older link's particles are gone; a part that
  never fills its pool takes the same ones. The cook refuses (n3e's guards)
  a ruled part with a batch above 1 (a candidate is known by its birth sample
  alone), a distance past 1000 m or not finite, and a texture and render state
  another particle part of the clip shares. A new magic keeps older clients
  failing closed, as N3E2 and N3E3 did; the server does not read the magic,
  `tools/assetc/main.py` accepts it; every other package, the 1298 tails and
  N3E2/N3E3 files cook byte for byte as before.
- **Inference (n3e's mapping):** 2233 decides per frame, n3e per 1/30 s sample
  (the PQ-341 sampling); across a link handover the newer link counts the
  older's taken live ones as of the frame (2233 has one copy and no
  handover); the distance is to the link's newest box point (2233:
  the copy's position RenderFX sets before the tick); the count is computed in
  double precision (2233: x87).
- **Considered:** a distance pair in each clip batch (it changes the batch
  layout every reader parses, and a batch carries no part identity across
  frames); thinning by a per-record rank (2233's rule depends on which
  particles are alive, not on a fixed order); baking a stream per count (21
  copies of the clip); cutting live particles past the count (2233 never does).
- **Recorded in:** content/presentation-events.md, content/appearance.md,
  CONTRACTS, GAPS, FEATURES, PARITY, STATUS, the evidence record.

## D-190 — 2026-10-21 The glow package's 2145 armour: 2233's artwork name and wear rules are applied at cook time to the package's one KO character profile, and each part is an ordinary package item in a package slot

- **Context:** PQ-319, from PQ-308 and PQ-315. The user asked to see the rogue
  Krowaz armour set worn and glowing. The 2145 data's rogue line is "Krowaz
  Assassin"; its artwork is 2145-only (the player's Item pack). The pinned
  1298 client has no 2145 item and stays the source of truth; the 2233 image
  is a secondary reference. Claims and labels are in the
  evidence record.
- **Observed (2233 IDB, binary for that image only):**
  `CGameBase::MakeResrcFileNameForUPC` (`009b3fc0`) names an armour part
  (attach byte `+0x5a` % 100 of 5–9, part slots 0, 1, 5, 3, 4) from the
  Item_Org model (`+0x48`) plus the wearer's race × 1000 (`0092fd30`), only for
  a class the race allows; the self (`00556370`) and other-player
  (`0052f660`) paths pass each player's own class (`+0x6b0`) and race
  (`+0x6a4`). `005e5a90` refuses an item by its need-race (`+0x5b`) and
  need-class (`+0x5c`) bytes and `00930030` by its kind (`+0x58`); 1298's
  `004a1750` has the same class groups. The tooltip (`005aa8e0`) names an
  attribute-11 item by its Item_Org name and "(+column 45 % 100)". 1298's
  `004a1ed0` puts each armour attach byte in one inventory area (5 → 4,
  6 → 10, 7 → 1, 8 → 12, 9 → 13).
- **Selected:**
  - **One profile, checked at cook time.** n3e has no per-character race or
    class (GAPS "Classes"); every character of a package shares one profile.
    `games/moradon/armour-2233.json` names its KO race and class (2, the male
    Tuarek the player model is; 108, a Karus rogue class that the set's
    need-class byte 8 admits). The cook (`tools/assetc/ko_armour_2145.py`)
    refuses a definition whose race is not the player model's, an item 2233
    would not let that profile wear (`005e5a90`, `00930030`) and an item for
    which `009b3fc0` names no artwork for it. Because no character of the
    package can be anything else, the server's existing equip rule (an item
    only in its package slots) is the whole runtime rule; no server field is
    added.
  - **Ordinary package items and slots.** Each part is a package item worn only
    in the slot of its inventory area, granted at start (no shop, no payment
    path), weightless, without wear or stats, with an N3V1 appearance row that
    draws its 2145 part on its part slot (the body part it hides) and, for an
    attribute 11 or 12 row, an N3E3 glow record. The glow package adds the
    slots the set needs (head, lower body, hands, feet) to features.json's
    five, and its HUD binds each to its inventory area. The realm is per
    release (tools/moradon_session.py), so no stored bag changes shape.
  - **Names and icons from the 2145 rows.** The label is `005aa8e0`'s; the icon
    is the 2233 rule's (PQ-338), from the player's 2145 UI pack.
  - **Grade:** one provisional row per part, Item_Ext row 15 of tables 37–41
    (attribute 11, column 45 = 15, a pulse at 2x), until PQ-346 says which
    grades and upgrade paths to carry.
- **Inference (n3e's mapping):** the 2145 column for each 2233 row offset is
  the field-size inference PQ-302 and PQ-338 use. A part's render state
  (alpha blend, double-sided) and texture alpha are not drawn on the player
  appearance path (PQ-280); the lower garment and the helmet have cut-out
  texels that draw opaque until then (PQ-348). Level and stat requirements
  are not carried.
- **Considered:** a class field in the equipment policy (a wire and schema
  change for a package that has one profile); reusing features.json's
  synthetic `race` number (it is not KO's race); the 1298 artwork rule
  (`006157b0` names armour from the item number: `2_4802_10_0` for this set,
  which no client ships).
- **Recorded in:** games/moradon/README.md, content/appearance.md, CONTRACTS,
  GAPS, FEATURES, PARITY, STATUS, the evidence record.

## D-191 — 2026-10-21 An equipped part draws with its KO part render state: an N3D3 render state per appearance key, written only when a part is not opaque

- **Context:** PQ-348 (a narrowed PQ-280). The opt-in `--glow-2233` package's
  2145 Krowaz Assassin parts carry render flags 5 (alpha blend, double-sided)
  with D3DBLEND 5/6, and the lower garment's and the helmet's DXT3 textures
  have texels of alpha 0–238; the appearance path drew every key culled, cut
  at alpha 0.5 and unblended. The claims and their labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** the armour setter `0045cd90`
  calls `CN3Chr` `0041b6d0`, which reloads the part in slot vector `+0x180`
  by name (vtable `+8` `00438e90` → `00438c40`: `CreateFileA`, then the part
  load `+0xc` = `00412180`, which reads the material); the character render
  `004196a0` (called by the player's render `00458ef0` and the in-rect render
  `00457420`) draws each part of that vector through `00412570`, then the
  plugs. `00412570`'s states (blend with the material's factors for flag 1,
  culling off for 4, lighting off for `0x40`) and the device's alpha test
  (`0043ade0`: GREATER, no reference set) are PQ-265's reading. **2233 (IDB,
  secondary):** `CN3CPart::Render` (`0042cf30`) sets the same states
  (`0042d18e`–`0042d243`) before the emissive and SetMaterial (`0042d24b`,
  `0042d275`) and the stage-0 colour op (`0042d2af`) of the same draw; its
  device set-up `0045d960` turns the alpha test on with GREATER and, of the
  884 calls through its SetRenderState wrapper (`0045d020`), the only two
  that set the reference write back what the same function read
  (`008f84f0`: `008f8757` then `008f89ff`; `008f9bb0`: `008f9ce0` then
  `008f9f45`).
- **Selected:**
  - `render-detail.bin` `N3D3`: N3D2 whose appearance entries each end with a
    render state (flags 1 blend and 2 double-sided, alpha reference, two
    blend factor indices), bounded as an N3SM run's state; both readers take
    it where they take N3D2, the server reads only the projection, older
    readers refuse the magic. No engine number, wire field or server rule.
  - The client draws an N3D3 key's range with its state, in the existing
    order, depth writes on, with its glow in the same draw (the glow scales
    the colour only), for self and others; a key that does not blend writes
    alpha 1. A test-client knob (`N3E_TEST_PART_STATES`) reports the states
    and draws a comparison frame without them; it is not a package switch.
  - The KO cook gives a 1298 or 2145 part row its part's state (reference 0,
    the device's alpha test) and a plug row the detail draw's own cut at 0.5,
    and writes N3D3 only when a part's state is not opaque, so every default
    package and pin is unchanged. An unlit part is refused on this path until
    a check draws one (PQ-280).
- **Considered:** a per-texture-slot state (it would also cover the body parts,
  PQ-280's, but changes what N3D2 packages mean); a new engine number (it
  would pull the glow package into engine 40/41's NPC rules for no reader
  difference: the magic already fails older readers closed, as N3E2–N3E4
  did); KO's reference 0 for plug keys too (a plug draw change outside this
  item, whose plug textures were not surveyed); the unlit flag (no fixture or
  KO part on this path to check it).
- **Limits:** n3e draws a character's default body first and the keys in key
  order, where KO draws the parts in slot order and then the plugs, so a key
  drawn later behind a translucent texel can differ (PQ-353); the inventory
  preview draws without states (PQ-352); the player's own body parts and
  attachments are PQ-280's.
- **Recorded in:** content/appearance.md, CONTRACTS, GAPS, FEATURES, PARITY,
  STATUS, the evidence record.

## D-192 — 2026-10-21 The glow package carries both KO upgrade paths, and a 2145 item's one-line label is 2233's tooltip name and kind line

- **Context:** PQ-350, from PQ-346 (research). KO 2145 data has a normal
  upgrade path (10-row Item_Ext blocks, attribute 4/5, never glowing under
  2233's `0056ea30`) and a reverse one (a separate Item_Org row, attribute
  11/12, column 45 the grade 1–30, glowing by band). D-190 carried the Krowaz
  set at one provisional reverse grade and named each item by `005aa8e0`'s
  name; PQ-337 named the Azagai's reverse grades by their Item_Ext name. A
  normal and a reverse grade of a unique share that name ("<selfname>'s
  Azagai(+10)"). Claims and labels are in the
  evidence record.
- **Observed (2233 image, binary for that image only):** the tooltip
  (`005aa8e0`) draws the name (the Item_Ext name for attributes 3, 4, 6 and
  12, `005aad74`; else the Item_Org name and "(+N)") and under it a kind line,
  a text by attribute through the jump tables at `005b2510` / `005b251c`
  (6811 for 4, 6812 for 5, 6817 for 11, 6816 for 12), replaced for a set item
  (need-race byte 101–199) by 6818 (attribute 11) or 6815 (`005aafe3`); both
  lines have per-attribute colours, and `004aad90` replaces `<selfname>` with
  the player's name. **2145 data (local-asset):** the texts are "(Unique
  Item)", "(Upgrade Item)", "(Reverse upgrade item)", "(Reverse unique item)",
  "(Set item)", "(Reverse set item)"; the Azagai's normal Item_Org row
  1110432000 has column 40 = 1 and the reverse row's model, so it draws the
  same `.n3chrplug`; the Krowaz rows have need race 124.
- **Selected:**
  - **Grades.** `games/moradon/skeletal-plugs-2233.json`: the plain Azagai,
    its normal +10 (1110432510) and reverse +1, +10 and +30;
    `games/moradon/armour-2233.json`: the five Krowaz parts at normal +10
    (248001020–248005020) and reverse +1 and +30 (258001001–258005001,
    258001030–258005030), replacing the provisional reverse +15. A normal row
    gets no glow record; 15 records in all. `ko_glow_2233.cook` refuses more
    than N3E3's 16 before the writer does.
  - **Labels.** The inventory label is `005aa8e0`'s name, a space and its kind
    line from the player's 2145 `Texts_us.tbl` (`ko_armour_2145.label`, for the
    armour and the skeletal plug rows alike): n3e's label is one line, and the
    kind line is the part of KO's tooltip that tells a reverse grade from a
    normal one. The N3I1 bound (64 printable ASCII) is unchanged; a longer
    label, an empty name or a kind text the table lacks is refused.
  - **Bag.** The glow package grants all 20 of its 2145 items at start (no
    shop, no payment path); with features.json's own and the progression's 8
    reward slots they need more than 32 slots, so that package's bag is 56
    (two pages of the HUD's 28-slot window; N3I1 allows 64). The realm is per
    release; no server rule changes.
- **Considered:** the KO name alone (two items of one name in the bag, the
  difference invisible); a kind line field in N3I1 and a second tooltip line
  (a format and client change; queued with the colours and the `<selfname>`
  substitution as PQ-354); granting only one grade at start (the showcase,
  PQ-333, compares grades on two players); fewer Azagai grades (the reverse
  +10 is kept as the steady 1x band).
- **Limits:** KO draws the kind line on its own line in its colour and
  replaces `<selfname>` (PQ-354); which grades a 2145-era server issues or
  steps to is unread (no binary); the 1298 client stays the source of truth
  and has no reverse path.
- **Recorded in:** games/moradon/README.md, content/appearance.md, CONTRACTS,
  GAPS, FEATURES, PARITY, BINARY-INDEX, STATUS, the evidence record.

## D-193 — 2026-10-22 `make live-ko` renders offscreen like `make live`, and the test client keeps its own relative mouse mode on the offscreen driver

- **Context:** PQ-129, with PQ-239 folded in. D-133 moved `make live`'s clients
  offscreen but `tests/live_ko.py` forced `live.DISPLAY = "desktop"`, so every
  `make live-ko` opened desktop windows that took the user's focus (user,
  2026-10-21: "it really interrupts my workflow"). PQ-238 had already run the
  then eleven KO suites offscreen by hand: ten passed, and `camera_legacy_live`
  failed only because SDL's offscreen driver refuses relative mouse mode
  (`SDL_SetWindowRelativeMouseMode`: "That operation is not supported") and the
  viewer cancels `orbit_drag` outside it.
- **Selected:**
  - `tests/live_ko.py` takes `tests/live.py`'s display rule unchanged:
    offscreen on the GPU by default (SDL offscreen driver, `WAYLAND_DISPLAY` and
    `DISPLAY` removed), `N3E_LIVE_DISPLAY=desktop` (`make live-ko
    LIVE_DISPLAY=desktop`) for watching. Its graphical suites hold `display`
    only on that opt-in. A `probe` prepare step cooks the synthetic legacy demo
    into `build/live-ko/work`, and the run opens one offscreen client on it
    (`live.gpu_probe`) before any suite: no EGL device or a software rasteriser
    is a failed `gpu-probe` step (`LIVE_KO_FAIL`) and every suite with a
    graphical branch is not run. The renderer and mode go to `summary.json`.
    A display is required only in desktop mode.
  - In the test client only (`N3E_HARNESS`), when SDL reports the `offscreen`
    driver and refuses relative mode, the mode the viewer asked for counts as
    granted (`client/render/viewer.cpp` `set_relative_mouse` /
    `relative_mouse`). Every other rule of the drag is unchanged (world pointer,
    focus, entry state, release, focus loss and death cancel it). A player's
    window, and any driver that grants or refuses relative mode itself, keeps
    SDL's answer.
  - Also in the test client on that driver only, the window never has the
    pointer for the camera's edge yaw. The driver gives its window the mouse
    focus when it is shown (it has no `ShowWindow` hook, so `SDL_ShowWindow`
    calls `SDL_SetMouseFocus`, SDL 3.4.18 `SDL_video.c`), and SDL's cursor stays
    at (0, 0), the left edge column, because the replays push their events: every
    offscreen KO client yawed its camera at the package's edge rate all run,
    which moved the other player's boxes in `moradon_armour_live` (found in this
    item's first full run). A desktop window turns only while the user's pointer
    rests on its edge, which the suites never rely on.
  - The replay is covered in the gate: `play_replay_live` (`make live`) runs
    `--play-smoke` on the demo package offscreen; `camera_legacy_live` runs the
    same script (`tests/play_replay_live.py`) on the KO field package.
  - No KO suite needs a window system, so none stays on the desktop and there is
    no opt-in KO desktop suite. `make graphical` (`tests/graphical.py`) remains
    the one test that needs one (it tests the Wayland and X11 backends, resize and
    focus); it is not a worker or gate step.
- **Considered:** warping SDL's cursor to the window's centre offscreen
  (`SDL_WarpMouseInWindow`; it would still give the window the pointer, and a
  replay's own pointer events would not move it); keeping `camera_legacy_live` on the desktop as an opt-in
  suite (the fallback is a four-line harness change, and the right drag is the
  replay's point); warping the pointer or injecting absolute motion instead of
  relative mode (it would change what the replay tests); Xvfb or a nested
  compositor (D-133's reasons hold).
- **Limits:** offscreen captures are not byte-identical to desktop ones (timing,
  animation phase); the evidence compares sizes, pixel statistics and the
  suites' own assertions. Relative mode itself (cursor hiding, pointer
  confinement) is a window-system feature and is not tested offscreen; `make
  live-ko LIVE_DISPLAY=desktop` (`camera_legacy_live`) and `make live
  LIVE_DISPLAY=desktop` (`play_replay_live`) still run the drag through it.
- **Recorded in:** LOOP.md, tests/live_ko.py, tests/live.py, README, GAPS,
  STATUS, the parity agent definitions and skill, the evidence record
  pq-129.

## D-194 — 2026-10-22 An item's tooltip head is package data (N3IH): a name colour, head lines under the name, and a package token the client replaces with the viewer's character name

- **Context:** PQ-354, from PQ-350 (D-192). n3e's tooltip drew one yellow name
  line from the N3I1 label; the opt-in `--glow-2233` package folded 2233's
  kind line into that label and kept `<selfname>` as text. Claims, addresses
  and labels are in the
  evidence record.
- **Observed (2233 image, binary for that image only):** `005aa8e0` sets the
  name line's colour by the Item_Ext attribute through the jump table at
  `005b24d4` (`005aac3c`), replaced for a set item (need race 101–199) by
  `+0x154` (attribute 11) or `+0x138` (`005aacc4`); it draws the kind line
  (`005aae12`–`005ab045`) as line 1 in the colour the same attribute picks
  (`005b2510`, `005b251c`, and the same set override at `005aafe3`), both
  lines centred (style `0x800000` on each line's string, `005aaa70`,
  `005aae52`); the colours are constants the constructor `005a9160` stores at
  `+0x124`–`+0x160`. Both name branches pass the name through `004aad90`,
  which replaces every occurrence of the static string `00c97274` (built from
  "<selfname>", `00b8f9f0`, by `00b78c60`) with the player's name (`[00e61920]
  + 0x684`, stored by `00574260` from `MsgRecv_MyInfo_All`, `00529599`).
  **1298 (binary):** `004d6320` colours the name by attribute 0–6 and draws a
  kind line for attributes 1–6 (texts 6808–6814) from its own constructor's
  colours (`004d5bd0`); it calls no replacement on the name.
- **Selected:**
  - **Format.** An optional client presentation file `item-heads.bin`, magic
    `N3IH`: a token (u32 length and 0–32 bytes; empty is none, otherwise
    printable ASCII 33–126), a head count (0–64; zero only with a token), then
    per head an inventory item id (a defined N3I1 item, unique), a name colour
    (0xRRGGBB, at most 0xffffff), a line count (0–4) and each line's text
    (1–64 printable ASCII 32–126) and colour. It needs engine 33, the
    presentation assets and `inventory.bin`; the cooker
    (`tools/assetc/item_heads.py`, manifest key `item_heads`), the client
    loader and the server's content check enforce the same bounds, and the
    server otherwise ignores it (it is hashed with the release like any file).
    A package without the file reads and draws exactly as before, so every
    existing package and pin is unchanged.
  - **Client.** A tooltip's first line is the item's label with the token
    replaced, in the head's name colour (yellow, as before, without a head);
    the head's lines follow it, each centred like the name, in their own
    colours; the rows after them are unchanged. The token is replaced by the
    viewer's own character name, from the world's self entity; only a name of
    1–24 ASCII letters, digits, `_` or `-` (the server's character name rule)
    is used, otherwise the label keeps the token. Each occurrence is replaced
    once, left to right, the search continuing after the inserted name, and
    the result is cut at 128 bytes. The server's item names stay package data;
    nothing is sent.
  - **Glow package.** The 2145 items' label is `005aa8e0`'s name alone; their
    heads carry the attribute's colour (the constructor's constants) for the
    name and the kind line, and the package token is KO's "<selfname>". This
    replaces D-192's one-line label.
- **Correction:** `004aad90` restarts its search one byte after the start of
  each replacement, so when the token occurs inside the replacement name at an
  offset of 1 or more it is replaced again without end (a name equal to the
  token, or holding it only at its start, ends the loop); n3e continues after
  the inserted name and bounds the result (BINARY-POLICY, "Self-name token
  correction"). For every name n3e's server accepts (no `<`), the result is
  2233's within the 128-byte bound.
- **Considered:** a kind line field in N3I1 (inventory.bin is the durable bag
  definition the server loads and hashes, so a presentation change would
  change the bag fingerprint and both inventory readers); an N3H HUD version
  (the HUD is versioned for layout, and item heads are item data); substituting
  in the server (the item name is data and the viewer's name a presentation
  choice); replacing the token in the head lines too (2233 replaces it in the
  name only).
- **Limits:** 2233's third line (the item type, `005ab04f`) and 1298's head
  for the default Moradon packages are not drawn (queued); `004aad90`'s other
  callers (chat and notices) are not carried.
- **Recorded in:** CONTRACTS ("Item tooltip heads"), content/inventory.md,
  content/appearance.md, games/moradon/README.md, BINARY-POLICY, GAPS,
  FEATURES, PARITY, BINARY-INDEX, STATUS, the evidence record.

## D-195 — 2026-10-22 An N3AT model (skeletal plug or cospre attachment) is lit with its wearer's equipped-part light

- **Context:** PQ-359, from PQ-358. n3e drew a wearer's render-detail parts,
  rigid hand plugs included, with the world branch's light,
  `0.35 + light × max(N·n(0.35, 0.85, 0.4), 0)`, but every N3AT model with the
  looks models' light, `0.15 + light × max(N·n(0.3, 0.4, 1), 0)`. So one
  character was lit by two lights, and the unglowing `<selfname>'s Azagai`
  front measured a light factor of 0.150 against the Krowaz armour's 0.353
  (PQ-358). Claims,
  addresses and labels are in the
  evidence record.
- **Observed (1298, binary, the source of truth):** the character render
  `004196a0` sets WORLD and the material source (render state `0x91` = 0),
  draws the parts (`00412570`) and then the plugs (`004158d0` → `004137d0`),
  each with SetMaterial (device `+0xa8`). None of the three calls SetLight
  (`+0xb0`) or LightEnable (`+0xb8`), so a character's parts and plugs take the
  same device lights. **2233 (binary, that image only):** `00435440` draws a
  skeletal plug's inner character (`00435400`) through the same part render
  `0042cf30` with no light call; every shader-drawn character takes the one
  `TCharacterShader` light (`009d7020`).
- **Selected:** the client draws every N3AT model, a skeletal plug entry or a
  cospre attachment, with the light its wearer's equipped parts take: the
  attachment pass sets a shader flag that selects the world branch's light term
  (one shader function, `partshade`, used by both). The model's own texture,
  its glow (`min(1, shade + emissive) × modulate`, PQ-328/PQ-337), its unlit
  runs (the texture's own colour), its render states and its fog are unchanged.
  NPC looks models, the base player model and every other draw keep their
  lights. No package, format, cook, wire, server or schema change.
- **Not a KO light model:** this unifies n3e's own fixed light across one
  character; what KO's character light is (1298's device light set-up, 2233's
  shader light, and the local player's fixed-function body in 2233,
  `0042e7e0`) is PQ-360. No deviation from the binary: 1298 lights parts and
  plugs alike, and n3e has one light per frame for every character.
- **Considered:** cooking the light into the attachment models (it is a
  per-frame draw rule, not data); lighting only skeletal plugs (cospre
  attachments are drawn by the same pass on the same wearer, and 1298 has one
  rule for parts and plugs).
- **Limits:** the light terms stay n3e's fixed formulas (PQ-360). Attachments
  drawn on NPCs (PQ-332) do not exist yet; the rule applies to any wearer the
  client draws with render detail.
- **Recorded in:** CONTRACTS ("Attached characters"), content/appearance.md,
  GAPS, FEATURES, PARITY, STATUS, the evidence record.

## D-196 — 2026-10-22 The default Moradon packages' KO item draws 1298's tooltip head: its attribute's name colour, its kind line and its item-type line (N3IH)

- **Context:** PQ-361, from PQ-354 (D-194). The default Moradon feature
  packages (default, classic and 1097 layouts) drew every item's tooltip name
  yellow with no line under it, because their cooks wrote no `item-heads.bin`.
  Claims, addresses and labels are in the
  evidence record.
- **Observed (1298 `KnightOnLine.exe`, binary):** the tooltip populate
  `004d6320` colours line 0 by the Item_Ext attribute (`+0x34`) through the
  jump table at `004dad0c` (0 and above 6 `+0xc8`, 1 `+0xb4`, 2 `+0xb0`, 3
  `+0xc4`, 4 `+0xb8`, 5 `+0xc0`, 6 `+0xbc`), the constants its constructor
  `004d5bd0` stores at `+0xb0`–`+0xcc` (ffff00, 8080ff, dcc77c, 19ffff,
  c87cc7, 80ff00, ffffff, ff3c3c); for attributes 1–6 it draws a kind line
  (texts 6808–6812 and 6814 through `004dad28`) in the same field's colour,
  skipped when the Item_Org name equals text 4533 (`004d6830`; "Coin" in the
  1298 data); unless Item_Org `+0x5a` is 1 or 3 it then draws the item type,
  `00614940`'s text for Item_Org `+0x40`, white (`004d6958`–`004d69a3`); each
  line is centred (style `0x800000` through vtable `+0x74`). The name colour is
  stored only when `004086d0` finds line 0's current text differs from the
  Item_Org name and suffix (`004d66f6`). The 1298 data has no attribute above
  6 (local-asset).
- **Selected:**
  - **Which items.** A package item is a KO item when its appearance rows name
    a KO item number (`ko_item`, PQ-211); in `games/moradon` that is the
    blade, KO item 120110048 (Short Blade, Item_Ext_1 row 48 Burning,
    attribute 5). The other default items are original fixtures whose icons
    were chosen as artwork only (ko-item-icons)
    and keep the yellow label. Rows of one item naming different KO items are
    refused.
  - **The head.** The cook (`tools/assetc/ko_item_heads.py`) reads the KO
    item's Item_Org, Item_Ext and Texts rows from the client data the package
    is cooked from and writes the item's N3IH head: the name colour by the
    attribute, the kind line for attributes 1–6 in that colour, and the type
    line in white unless the row is countable (`+0x5a` 1 or 3). For the blade:
    `c87cc7`, "(Upgrade Item)" `c87cc7`, "One-handed Sword" `ffffff`. No token
    (1298 calls no name replacement). The label stays the package's item name
    ("Practice blade"); 1298 would print "Short Blade(+8)" (queued).
  - **Refusals.** An item whose Item_Org name is text 4533 (1298 draws its
    count and name alone, `004d649d`–`004d65b7`), a type text `00614940`
    gives none for (it leaves the line empty, which N3IH cannot hold) and a
    missing Texts row are refused by name.
  - **Packages.** The default, classic and 1097 feature cooks (and `--des`,
    which builds on the default feature cook) write the heads; their three
    pins change. The `--glow-2233` cook keeps its 2233 heads (D-194) and its
    pin; its blade keeps the yellow label (queued). No client, server, wire,
    schema or format change: D-194's client draws the heads.
- **Correction:** `004d66f6` skips the colour store when the line already
  shows the same name text, so after an item of another attribute with the
  same name (120110048 Burning and 120110068 Strong are both "Short
  Blade(+8)", attributes 5 and 1) the name keeps the previous item's colour.
  n3e draws each item's own head colour every time (BINARY-POLICY, "Tooltip
  name colour correction").
- **Considered:** naming every default item by its icon's Item_Org row (the
  icons were chosen as artwork, not as an item identity, and most rows have no
  extension the package chose); replacing the label with 1298's name (it
  changes `inventory.bin`, the server's bag definition and fingerprint, and
  the tests and guides that name the items: a separate item); reading the KO
  tables in the client at run time (KO data is cook-time input; the package
  carries presentation data only); adding the blade's head to the glow package
  (2233's head rules for a 1298 item there are not read; its pin is kept).
- **Limits:** the rows after the head stay n3e's (1298's race, class and
  requirement lines, `004d69c9` on, are not carried); the coin branch is not
  carried (no package item is the coin); the 1298 tooltip's caching
  (`+0x334`) is not modelled.
- **Recorded in:** CONTRACTS ("Item tooltip heads"), content/inventory.md,
  games/moradon/README.md, BINARY-POLICY, GAPS, FEATURES, PARITY,
  BINARY-INDEX, STATUS, the evidence record.

## D-198 — 2026-10-22 Redis requests reuse the resolved address; readiness closes after two failed probes in a row; a refused handshake is logged with its reason

`gameplay` failed once in the gate (PQ-365's trial merge `f0cc44f`). After
the `before_response` crash restart, its relogin got an Error envelope instead
of the handshake reply. The suite dropped the code and detail, and the server
logged nothing, so the kept logs could not say which refusal it was (PQ-368).
Reading the code rules out three of them. The protocol and handshake-shape
refusals cannot happen: the suite sends a fixed, well-formed handshake. The
content refusal cannot happen either. The package is cooked once before the
suites start and nothing rewrites it during the run. Both trees hash it to the
same release. PQ-365's N3IN reader never runs for it, because `legacy-demo`
has no `item-heads.bin`. That leaves `realm not ready` (code 6), which comes
from admission (the lease deadline or an invalidation) or from Redis. The
server stayed up and printed nothing for more than 2 s after `LISTEN`. A lapsed
or invalidated admission ends the process and prints its error, so the logs fit
Redis better. Redis readiness was one probe every 300 ms: a fresh name lookup,
connect and PING within 700 ms. A single failed probe refused every handshake
until the next probe succeeded. Every login's rate-limit command also made a
fresh lookup and connect.

The diagnostics below then caught the mechanism in `gameplay` itself, in a
passing full `make live` run. Three seconds after start-up, while the suite
created its accounts, the probe got no PONG within 700 ms, twice in a row.
Docker read both log lines in the same 15 µs. Redis itself was serving. In a
Compose stack only the name lookup goes through dockerd (its embedded
resolver), and dockerd was evidently busy at that moment. Each probe therefore
depended on dockerd being responsive.

- **Selected, the endpoint:** the probe and every Redis request share one
  `cache::Endpoint`. It remembers the socket address that last connected,
  connects to it with no lookup, and forgets it after any failed request, so
  the next request looks the name up again. Every resolved address is tried
  in turn. A slow resolver therefore fails nothing while Redis serves. A
  restarted Redis at a new address fails one request, and the next request
  finds it. The 700 ms request deadline is unchanged, and a missed deadline
  names its step (name lookup, connect, reply).
- **Selected, readiness:** Redis readiness opens on a successful probe and
  closes after two failed probes in a row (`persistence::RedisReadiness`,
  `REDIS_FAILURES = 2`). This absorbs the one failed probe that a moved Redis
  or a single slow connect costs. Admission never opens before Redis has
  answered once. A real outage closes it within about two probe periods: in
  `multiplayer`'s stop, the cached address timed out at the connect and the
  next lookup failed. Login keeps its own fail-closed Redis rate-limit command
  ("login protections unavailable"), so no login is admitted without its rate
  limit while a probe is missed. The lease and admission rules (D-139, D-141,
  D-142, D-145) are unchanged.
- **Selected, diagnostics:** the server writes one stderr line per refused
  handshake with its reason. A `realm not ready` line names the failed part:
  lease not yet held, admission expired N ms ago, lease lost, stopping, Redis
  or listener. At most 10 lines are written a second, and the next line
  written counts the lines left out. The server also logs:
  - Redis readiness changes and each missed probe;
  - a lease renewal that started 1.2 s or more after the previous one;
  - why renewal stopped or failed;
  - how much of the first admission window start-up used.

  `Health::ready` is `Health::unready().is_none()`, so the logged reason and
  readiness come from the same checks. The test peer's handshake assertion
  carries the refusal's code and detail. `gameplay` keeps every server
  container's log before it replaces one (`build/gameplay/servers.txt`).
- **Considered:**
  - Retrying the suite's handshake on code 6: it would hide a realm that
    stops admitting, and suites do not retry refusals (PQ-001).
  - A longer request deadline: a stalled lookup still fails, and an outage
    is noticed later.
  - Only the two-failure rule: dockerd's stall outlasted two probes.
  - A persistent Redis connection: it needs reconnect and pipelining rules for
    the concurrent login commands; reusing the address removes the lookup,
    which was the only dockerd dependency.
- **Limits:** the refused relogin itself did not recur. Its component is
  inferred from the kept logs and the stall the diagnostics later caught, not
  observed in the failed run. A name lookup still happens after any failed
  request. The renewal connection, opened only after the lease is taken, is
  queued as PQ-369.
- **Recorded in:** CONTRACTS (Phase 2, Redis loss), GAPS, STATUS, the PQ-368
  evidence.

## D-199 — 2026-10-22 The lease-renewal connection opens before the lease, like the account/checkpoint worker's

The renewal thread opened its Postgres connection (`persistence::connect`) after
start-up had taken the lease and opened the first admission window, which ends
2 s after the attempt that took the lease. Neither the name lookup nor the
startup handshake is bounded by `connect_timeout` (1 s, the TCP connect alone),
and the thread then sleeps 400 ms before its first renewal. A connect that took
more than about 1.1 s (the 2 s window less the 400 ms sleep and the 500 ms that
start-up's own writes take in a debug build) therefore let admission lapse.
The realm had already bound its port and answered `/ready` 200, and it then
exited with "admission expired; restart required" (PQ-369). PQ-368 named this
as a candidate it could not rule out. A slow-connect proxy reproduced it with
the old binary in three of three runs.

- **Selected:** start-up opens the renewal connection in its start-up task,
  after the start-up connection has verified the schema and after the
  account/checkpoint worker has connected (D-141), and before `acquire_within`.
  It hands the open client to the renewal thread. A slow connect now delays
  start-up before the lease, where no window is running. A connect that fails
  ends start-up with its error and takes no lease. Like the worker, it rides out
  57P03 within D-140's 5 s window and nothing else. The worker still connects
  second, so the one-connection-role check of PQ-156 still refuses the worker.
  The realm opens the same three connections as before, in the same order.
- **Considered:**
  - Bounding the renewal connect by what is left of admission: the realm would
    then exit at start-up on a slow connect instead of reporting ready first,
    but it would still exit.
  - Renewing on the start-up connection: start-up's own writes would then
    share it with the renewals. D-142 and D-145 assume that renewal waits for
    nothing of the realm's own.
  - Opening all three connections at once and joining them: D-141 rejected
    this race for the worker.
- **Limits:** a renewal connection that closes after start-up still ends the
  process (no reconnect, D-140). The idle renewal connection is held for the
  length of start-up's writes. That is one connection the old code also held,
  only for less time.
- **Recorded in:** CONTRACTS (realm ownership), GAPS, STATUS, the PQ-369
  evidence.

## D-200 — 2026-10-23 A weapon effect's tail sparks and FX mesh copies sort by 1298's alpha-list keys: an N3E5 sort record per appearance effect

- **Context:** PQ-376, the fix PQ-373 queued. n3e's effect pass sorted each
  tail link as one draw, by the squared distance to its newest random box
  point, and each FX mesh copy by the squared distance to its vertex centroid.
  Where a non-additive glow and tail overlap, the order changed from frame to
  frame (PQ-370's 1.3 % of frames). The claims and their labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** an alpha particle part
  (`004840b0`, `0048410a`–`0048433c`) queues one primitive per live spark,
  keyed by the linear distance from the eye `006e26d0` to (v0 + v1 + v2) ×
  0.3333 of its quad. The quad's corners are the part's template (`00482820`:
  (−0.5, 0.5) UV (0, 0), (0.5, 0.5) UV (1, 0), (0.5, −0.5) UV (1, 1),
  (−0.5, −0.5) UV (0, 1)), scaled, turned in the camera-facing plane and
  added to the spark's centre (`00481f10`). `00415910` keys each FX mesh copy
  by the linear distance from the eye to its matrix's translation plus the FX
  mesh's y extent in mesh units (`00415a23`, `00416839`, `00416a0d`,
  `00416b72`). `0043dd80` sorts them together with `qsort` and `0043e6c0`, far
  to near, primitives with flag `0x1000` first.
- **Selected:**
  - `effects.bin` `N3E5`: N3E4 whose rule list may be empty (0..64), followed
    by 1–16 sort records, each on one appearance effect of the file (at most
    once): an origin in bind space, rigid to the effect's joint, and a bias
    (0..1000). An effect with a record sorts each copy by the linear distance
    from the eye to the origin moved by that copy's jitter, plus the bias, and
    each camera-facing quad of its tail links on its own, by the linear
    distance to the centroid of its first three corners in KO's corner order.
    An effect without one keeps n3e's order (each link by its newest point,
    each copy by its vertex centroid). Readers refuse a record on a key with
    no effect, a duplicate, values out of range and trailing bytes; older
    readers refuse the magic, as they refused N3E2–N3E4. No engine number,
    wire field or server rule.
  - The pass compares every key as a linear distance. The old squared keys
    become their square roots, so the order among them is unchanged.
    Consecutive draws of one material after the sort share one draw call,
    which keeps their order.
  - The KO cook gives every 1298 hand-plug effect a record: the plug origin
    (the FX mesh's origin through the plug placement, the copies' jitter
    origin) and the FX mesh's y extent as read, not scaled by the plug or the
    character. It refuses a 1298 tail particle part that does not alpha-blend
    (KO draws those at once, `004840b0`, which n3e does not model; none of the
    four 1298 weapon tails). The 2233 skeletal-plug records (PQ-339, PQ-341)
    get none until 2233's own order is read.
- **Considered:** a field in every N3E2 effect (it would change the N3E2 bytes
  of every package, the 2233 records included, for a rule they do not follow);
  deriving the origin from the jitter axis (it ties the sort to a field with
  another meaning; the record names it); keeping squared keys and squaring the
  biased sum (equivalent, but every key would then mean two things); KO's
  `0x1000` group (n3e's render flags have 11 bits, so no n3e draw is in it;
  who sets it is PQ-377's).
- **Limits:** ties keep insertion order (`std::stable_sort`) where KO's
  `qsort` leaves them unspecified. Only the effect pass's draws share the
  order: KO's one frame-wide list also holds the target symbol, world effects
  and other alpha draws, which n3e draws in other passes (PQ-377). n3e places
  the plug at height / 1.8 × the plug scale (PQ-211), so its world distances
  differ from KO's by that factor where it is not 1; the bias is KO's mesh
  units unscaled. Player effects (skills) keep one key per instance.
- **Recorded in:** content/presentation-events.md, content/appearance.md,
  CONTRACTS, GAPS, FEATURES, PARITY, STATUS, the evidence record.

## D-201 — 2026-10-23 World parts that 1298 alpha-blends draw in the frame's one far-to-near alpha pass: N3L4 and N3W3 alpha records

- **Context:** PQ-379, the fix PQ-377 queued. n3e alpha-tested every world
  shape part at 0.5 and drew it in the world pass. 1298 queues a shape part
  whose material has render flag 1 into its frame alpha list instead, and
  draws it blended, sorted with every other alpha primitive of the frame. In
  the 21 local 1298 zones 9,939 of the static parts the bake draws carry the
  flag (2,492 of Moradon's 4,111 parts); all of them blend 5/6. The claims and
  their labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** `00443090` (the shape part
  render, from `004442e0`) tests the material flags `+0xcc` bit 0
  (`004430f6`). Set, it takes a slot of the frame list (`0043e690` at
  `00443103`; with none left, `0044310c`, the part is not drawn) and
  fills it with the key, the linear distance from the eye `006e26d0` to the
  part matrix's translation (`+0x68`..`+0x70`), the blend `+0xd0`/`+0xd4`,
  the flags `+0xcc`, the texture, a triangle list of `+0x114` / 3 triangles
  over `+0x118` vertices (FVF `0x112`, stride 32) and the part matrix `+0x38`
  as its world matrix, and draws nothing. The shape load `004445a0` sets that
  matrix to the pivot (`+0x2c`) as a translation times the shape's matrix
  (`0041dda0`). The flush `0043dd80` sorts the list far to near (`0043e6c0`)
  and draws each primitive with blending on, its blend, fog off for flag 2,
  culling off for 4, lighting off for `0x40`, z-write off for `0x100`, z-test
  off for `0x400`, point mip filtering for `0x10`, clamped addressing for
  `0x200` and a diffuse-alpha stage for `0x80`. It never sets the alpha
  test. That the test is then still the device set-up's (on, GREATER against
  reference 0, `0043ade0`) is an inference (PQ-265 B12), not read at the
  flush.
- **Selected:**
  - `world-lod.bin` `N3L4`: N3L3 whose parts may set flag bit 4 (16), an
    **alpha part**, and `world.bin` `N3W3`: N3W2 whose chunk parts may. An
    alpha part is kind 1 (or, in N3W3, kind 0); after its kind's fields it
    carries an alpha record: u32 source and destination blend (1..10, the
    Direct3D numbering `effects.bin` uses), u32 state (bit 0 set; besides it
    only `0x40` unlit, `0x80` diffuse alpha, `0x100` no depth write, `0x400`
    no depth test, the flush's own bits; fog and culling stay the part's
    flag bits 0 and 3) and f32 sort point[3] (finite, within 1e6). The
    cooker writes the new magic only when a part carries a record, so every
    world without one keeps its N3L3 / N3W2 bytes. Older readers refuse the
    new magic. No engine number, wire field or server rule: the server still
    checks only the world's magic and size.
  - The client leaves an alpha part out of the world pass, chooses its level
    of detail there as for any part, and draws it in the effect pass, which
    becomes the frame's one far-to-near alpha pass: each alpha part is a draw
    keyed by the linear eye distance to its sort point, sorted with the
    effect draws (`effect_draws`, `std::stable_sort`). It draws with the
    world shader, its factors, depth writes and tests unless its state turns
    them off, its part's fog and culling, no light for `0x40`, and its
    fragments cut where the texture's 8-bit alpha is 0 (GREATER 0), its alpha
    the texture's. `0x80` changes nothing in n3e: a world vertex has no
    colour, and the stage's diffuse alpha is the fixed material's 1
    (inference from `0043dd80`'s material, diffuse 1).
  - The KO cook marks every drawn part whose material has flag 1, with its
    material's factors, its flags masked to the bits above and the part
    matrix's translation in n3e coordinates as the sort point. It refuses an
    alpha part with `0x10` or `0x200` (n3e's world samplers are linear with
    wrap or mirror; no local 1298 or 1097 zone has one).
- **Considered:** a flag bit in N3L3 / N3W2 (older readers would refuse the
  bit, but the magic would stop naming the layout); a separate alpha-part
  asset beside the world (a second file per world that must agree with it
  part by part); a pass of its own for world alpha parts before or after the
  effects (KO has one list, so either order is wrong wherever they overlap:
  the item's check fails both); keeping KO's flag word whole (fog and culling
  would then be stated twice per part).
- **Limits:** ties keep insertion order where KO's `qsort` leaves them
  unspecified. The target marker still draws in its own pass (PQ-380) and
  skill effects keep one key per instance (PQ-381). An N3W1 world without
  `world-lod.bin` has no parts and keeps the alpha test. Opaque world parts
  keep n3e's 0.5 alpha cut and its light (queued: PQ-382). KO's fixed light
  set is not n3e's (PQ-363). `RF_BOARD_Y` parts stay frozen.
- **Recorded in:** content/world.md, CONTRACTS, GAPS, FEATURES, PARITY,
  MAP-EXPLORATION, STATUS, the evidence record.

## D-202 — 2026-10-23 Opaque world parts take 1298's alpha test and unlit flag: N3L5 and N3W4 part bits

- **Context:** PQ-382, the fix PQ-379 queued. n3e cut every opaque world
  part's fragments where the texture's alpha is below one half and lit every
  one. 1298 draws a world shape part whose material has render flag 1 clear
  at once, alpha-tested as the device set-up leaves it, and unlit when the
  material has `RF_NOTUSELIGHT` (`0x40`). In the 21 local 1298 zones 461 of
  40,781 opaque static parts carry `0x40` (Moradon 18 of 1,591), and 918 of
  Moradon's opaque parts sample a texture with alpha between 1 and 127 (its
  trees and foliage), which n3e cut and KO draws. The claims and their labels
  are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** `00443090`'s opaque branch
  (`0044327f`, flag 1 clear at `004430f6`) saves and sets fog off for flag 2,
  culling off for 4 and lighting (state `0x89`) off for `0x40` (`004432da`),
  sets the material `+0x7c`, the texture and the stage-0 colour operation,
  draws (`00441bb0`) and restores those three states; it sets no alpha-test,
  alpha-reference or blend state. The world object's draw `005a3740` calls the
  shape list (`005b5870`, each shape's slot `+0x48`) before `005bda00`.
  Neither `005bda00` nor `005bb900` (the character draw's state window) sets
  the alpha-test states: each reads states 15, 24 and 25 with GetRenderState
  and writes the read values back, and `005bda00`'s inner draw `005bb7d0`
  sets no render state. So the shapes, and whatever those windows draw, are
  tested as the device set-up leaves the test (`0043ade0`: on, GREATER; no
  reference set, so Direct3D's default 0). That no reset between set-up and
  draw changes it is PQ-265 B12's inference.
- **Selected:**
  - `world-lod.bin` `N3L5` and `world.bin` `N3W4`: N3L4 and N3W3 whose kind 0
    and kind 1 parts that are not alpha parts may set flag bit 5 (32), **cut
    at zero** (fragments cut only where the texture's 8-bit alpha is 0, the
    Direct3D GREATER-against-0 test), and bit 6 (64), **unlit** (the part's
    colour is its texture's, no light). Both are refused on an alpha part (its
    record already states both) and on a terrain patch (its flags stay exactly
    2). The writers choose the lowest magic that holds the parts: N3L5 / N3W4
    when a part sets bit 5 or 6, else N3L4 / N3W3 with an alpha part, else
    N3L3 / N3W2. Older readers refuse the new magic. No engine number, wire
    field or server rule: the server checks only the world's magic and size.
  - The client draws such a part in the world pass, as before, with the
    world shader's alpha reference at 0 for bit 5 and no light for bit 6. A
    part without them keeps the one-half cut and n3e's light, so every other
    world draws as before.
  - The KO cook sets bit 5 on every drawn part whose material has flag 1
    clear and bit 6 on those that also have `0x40`; an alpha part keeps its
    record. Every KO world with parts becomes N3L5 or N3W4.
- **Considered:** changing the world shader's cut to 0 for every part (it
  would change every non-KO package's foliage, a game rule in the engine); a
  per-world alpha reference in the header (KO's terrain is drawn by other
  code, not read here, and a header field would apply to its patches too); a
  per-part reference value (no data needs a reference other than 0 and one
  half); bits 5 and 6 in N3L4 / N3W3 (the magic would stop naming the layout,
  as D-201 refused for its own bit).
- **Limits:** terrain patches keep the one-half cut; KO's terrain draw is not
  read here. An N3W1 world without `world-lod.bin` keeps the one-half cut and
  the light for everything. Unlit is the texture's colour: KO's vertex colour
  with lighting off is the FVF's default white (FVF `0x112` has no diffuse),
  times the texture through the material's colour operation (`+0xc0`), which
  n3e takes to be modulate (inference; n3e has no per-part colour operation).
  KO's light set for lit parts is not n3e's (PQ-363).
- **Recorded in:** content/world.md, CONTRACTS, GAPS, FEATURES, PARITY,
  STATUS, the evidence record.

## D-203 — 2026-10-23 1298's near colour-map tiles draw the colour-map texel unlit, by the documented Direct3D 8 rule applied by inference: N3W5 single-layer unlit vertices

- **Context:** PQ-388, the fix PQ-386 queued and PQ-389 made eligible. 1298
  draws a near tile without a tile texture from its patch's colour map
  (`005a2640`'s `005a29e1` path, PQ-384): stage 0 SELECTARG1 of the colour
  map, stage 1 MODULATE with COLORARG1 TEXTURE (`005a2a46`) and a texture
  `005a2a1e` sets to null, stage 2 MODULATE of CURRENT and DIFFUSE (the
  vertex light). n3e drew it as the colour map times its terrain light,
  which is wined3d's reading (Wine 8.0 passes such a stage through), shared
  by the rig. Microsoft's DirectX 8.1 SDK help for `IDirect3DDevice8`
  (`directx8_c.chm`, "Texture Blending", PQ-389 claim 14) and Direct3D 9's
  documentation say that a stage whose COLORARG1 is TEXTURE with a null
  texture stops processing at that stage and all after it, so stage 2's
  light is not applied. 1298 was built against the 8.0 SDK, whose help is
  silent (PQ-389 claims 1, 2, 16 to 18), so applying the rule to 1298 is an
  inference. What a Windows driver drew is not observed (PQ-390, blocked on
  the user). The claims and labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** the stage states above, and
  that the multiplying pass after the draw (`005a2acb`–`005a2b05`) is taken
  only when terrain `+0x4c20` is 0 and tex1 and tex2 are both in
  `[0, +0x4188)` (PQ-384 claim 6). A tile on the colour-map path whose tex1
  or tex2 is not a tile texture therefore never takes that pass.
- **Selected:**
  - `world.bin` `N3W5`: N3W4 whose vertices may set the second-layer slot
    to -1, a **single-layer unlit vertex**: the fragment is the first
    layer's texel (cut on its alpha as before), with no second layer added
    and no light. Every other slot stays an index below the texture count.
    The writer chooses N3W5 only when a vertex carries -1, else the magic
    `world_chunks.layout` chose (N3W2 to N3W4), so every world without such
    a vertex keeps its bytes. Older readers refuse the magic. `N3W1` and the
    `N3L` files cannot carry it: their readers keep refusing a negative
    slot, and the KO bake writes a map with such vertices chunked, keeping
    the reason as `n3w1_refused`, as it does for an overflow. No engine
    number, wire field or server rule changes: the server checks the world's
    magic and size only and admits N3W5 as N3W2.
  - The client keeps -1 through its native texture remap (the streamed and
    all-resident paths) and the world shader draws such a vertex's
    fragment as its first-layer texel, unlit.
  - The KO cook sets -1 on the four vertices of every near tile on the
    colour-map path that never takes the multiplying pass (tex1 or tex2 not
    a tile texture). A tile sent there only by a clear full bit, with tex1
    and tex2 both valid, keeps the lit draw: 1298 multiplies it by DIFFUSE
    in the pass when `+0x4c20` is 0, and n3e draws no pass (no local tile
    has a clear full bit). Of the cooked maps only `karus2004` (key 10)
    has such tiles, its six east-edge tiles, so only its release changes.
- **Considered:** an unlit part bit on the terrain patch (a patch mixes these
  tiles with lit ones, and its near level is one index list); splitting the
  tiles into their own part (they would leave the patch's level selection);
  a per-texture unlit flag in N3WT with a duplicated colour-map texture (a
  second format change and the texture's memory twice); a sentinel in the
  second-layer UVs (old readers accept the UVs and would draw it lit without
  refusing); a flat counterpart of N3W1 (a new flat magic for a case no
  local flat map has); keeping wined3d's reading (no Microsoft text supports
  it, PQ-389 claims 9 to 13).
- **Limits:** the cut is the documented Direct3D 8 rule from the 8.1 SDK on,
  applied to an 8.0-SDK build by inference, not a KO observation; it departs
  from the rig, whose wined3d keeps the light. The Windows-driver
  observation stays open (PQ-390). Fog still applies, taking Direct3D's
  fixed-function fog to follow the texture cascade (inference). Alpha: n3e keeps the terrain's one-half cut on
  the colour map's alpha, which every local colour-map texel holds at 255.
- **Recorded in:** content/world.md, CONTRACTS, GAPS, FEATURES, PARITY,
  BINARY-INDEX, STATUS, the evidence record.

## D-204 — 2026-10-23 1298's terrain light maps blend over the near patches around the eye: an N3WO world overlay

- **Context:** PQ-387, the fix PQ-385 queued. After its 64 tiles, 1298's near
  patch render `005a2640` draws a list of fans with stage 0 MODULATE of
  TEXTURE and DIFFUSE and SRCALPHA / INVSRCALPHA blending (`005a2c62`–
  `005a2dfc`). The tick `005a0410` fills the list from `0059c720`, which
  finds a texture per 4 × 4-tile block in the zone's `.tlt` (Zones.tbl
  column 5), loaded by `0059ba90` / `0059c450` for the 3 × 3 patches around
  the patch holding the camera eye only. n3e read no `.tlt` and drew no such
  pass. The claims and labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** the file layout and key
  (PQ-385 claims 1–12); the window centre is the eye's patch (`0059b6f0`:
  the eye `006e26d0` / `006e26d8` truncated, / 4, / 8, less `+0xbc` = 33,
  and `0059b890` adds `+0xb8` / 2 = 33, set at `00599a3e` / `00599a48`);
  both parity branches of `005a0410` write each corner's UV as the same
  affine function of the corner (u from x, v from z) and fan with the
  tile's own diagonal, on the tile's heights (`0059ad50`) and normals
  (`0059add0`); the pass sets no Z, LIGHTING or ALPHAOP state, and no
  function of the program writes ZFUNC.
- **Selected:**
  - A new optional package asset `world-overlay.bin`, magic `N3WO`:
    per-block RGBA8 mip chains on the terrain's tile grid, with the grid's
    patch and block size, the eye window radius and the texel layout of a
    block's map (texture side, texels per tile, inset) as data. The KO cook
    writes it from the `.tlt` for a zone with at least one map; a zone
    without maps writes no file, so its release is unchanged. Every
    `world.bin` format is unchanged.
  - The client draws, right after a terrain patch drawn at its near level
    whose patch lies within the window radius of the eye's patch (the
    patch the terrain LOD already takes, `world_lod::terrain_level`), the
    same index range again: each fragment takes its block's map at the
    position-derived UV, colour = texel × n3e's terrain light, alpha the
    texel's, blended SRC_ALPHA / ONE_MINUS_SRC_ALPHA, depth test LEQUAL,
    alpha 0 dropped. The window's maps are uploaded to a small array when
    the eye's patch changes, as 1298 loads its 3 × 3 window.
  - Cooker, client and server refuse the asset without a world and an
    exploration policy; the client also refuses it without a terrain
    policy or with a grid that does not match it. The server checks magic
    and size only: it is render data and changes no rule.
- **Considered:** the fans as world parts (an N3W3 alpha part draws in the
  frame's far-to-near alpha pass, not after its patch, and a static part
  cannot follow the eye's window); a third UV layer and per-tile slot in
  every world vertex (a format change of every world and 4,062 more
  N3WT slots for `elmo2004`); drawing every map wherever the patch is near
  (1298 draws none outside the 3 × 3 window); one GPU array of all maps
  (above the 2,048-layer array limit common GPUs report for `elmo2004`);
  fans with their own vertices (identical positions to the tile's, so the
  same depth, but an extra vertex stream per zone for no visible change).
- **Limits:** the texel colour is multiplied by n3e's terrain light, not
  Direct3D's vertex light with the `0059cd90` material, and that light
  being on at the pass is inference (only `elmo2004`, `elmorad_intro`,
  `karus_intro` and `freezone_b` have coloured texels; the rest are black,
  where the light is moot). Equal-depth passing relies on Direct3D 8's
  default LESSEQUAL (API rule; the program writes no ZFUNC) and n3e drawing
  the same vertices twice. A fragment on the seam between two tiles takes
  the tile its position rounds to, where 1298 takes the fan's; n3e takes the
  UV gradient from the position, so seams keep their mip level.
  Static only: no KO frame was compared.
- **Recorded in:** content/world.md, CONTRACTS, GAPS, FEATURES, PARITY,
  MAP-EXPLORATION, BINARY-INDEX, STATUS, the evidence record.

## D-205 — 2026-10-23 The KO world bake draws the bind points and warp gates 1298 shows at load, their animated magic part as its first frame

- **Context:** PQ-392, the fix PQ-391 queued. 1298's shape manager load
  (`005b4690`, `005b4a2f`–`005b4a73`) keeps a shape with a non-zero event
  id visible (`+0x151` = 1) only for event types 0 and 5 (bind points and
  warp gates; type names local-asset), and its tick and render draw a
  visible shape like any other (PQ-391 claims 1–9). n3e's KO bake placed only
  `ko_shapes.classify`'s `static` shapes, and these match its `event`, `npc`,
  `extra` and `animated_material` rules. 1298's load and draw read neither
  NPC field, and the `0x1000` kind keeps its loaded pose (PQ-391 claims 13,
  14). Each such shape has one "magic" part with 16 or 17 textures at 10 or
  6 fps, blended ONE/ONE; n3e cooks no texture animation (GAPS, KX map
  remainder). The claims and labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** the part render `00443090`
  draws the texture at index `ftol(+0x124)` of the part's list
  (`004430cd`–`004430ed`); the part constructor sets `+0x124` to 0
  (`004425d5`); the part tick `004429b0` adds frame time × fps (`+0xd8`) to
  it only when the part has more than one texture (`00442c65`–`00442c95`)
  and sets it back to 0 when it reaches the count (`00442c9b`–`00442cb2`).
  The manager render draws only the shapes the manager tick listed, a
  shape is listed only after its tick has ticked its parts (`005b5680`,
  `005b5870`, `00443f40`; PQ-391 claims 5, 8), and the part tick returns
  before the advance, marking the part undrawn (`+0x78` = 1, `00442e17`),
  when the part fails its distance or plane test. The frame time `[006d3ab0]` is bounded
  only to (0.001, 1.0) s, with 1/30 outside (`0043ac60`, PQ-012).
- **Inferred (from these, evidence claim 6):** every draw of the part
  follows an advance of its index in the same tick, so the first draw after
  load can already show frame 1 to 9 at 10 fps. The first texture is the
  frame the cycle starts from and returns to; which frame 1298 shows at a
  given moment, the first draw included, depends on the frame times. The
  first texture is therefore a chosen static stand-in, one of the frames
  1298 cycles through, not the frame 1298 is known to show.
- **Selected:**
  - `ko_shapes.classify` returns `event_shown` for a shape with an event id
    and event type 0 or 5 (tested before the `npc`, `extra` and
    `animated_material` rules, which 1298's load and draw do not apply to
    it); such a shape with animation keys stays `animated` and one without a
    mesh `empty` (none in the local OPDs). Every other event shape stays
    `event`, including a type with event id 0 (none in the local OPDs).
  - The bake places `ko_shapes.BAKED` = `static` and `event_shown` shapes
    with the existing part rules, so the magic part is an alpha part
    (blend 2/2, its flags) drawn with its first texture, the cycle's start
    frame, as a static approximation of the cycle. The report counts the
    event shapes and these first-frame parts and names the approximation.
  - No format, contract or engine change: the parts are ordinary world
    parts in the existing N3L5 / N3W4 / N3W5 layouts.
- **Considered:** leaving the magic part out (the stone and the posts would
  draw with no glow, where 1298 always draws one of the frames; every frame
  is a similar glow, mean channel values 8 to 53 of 255, local-asset);
  cooking the texture cycle (a new animated-material capability for every
  shape of that class, beyond this item: the GAPS row keeps it); opening the
  `npc` and `extra` rules for every shape (the binary basis covers these two
  event types; other `0x1000` shapes are turned by `00447b60`).
- **Limits:** the magic part does not cycle its frames, and which frame
  1298 shows at a moment is not modelled (inference, above); a Karus magic part's
  `0x8` (Y billboard, `004429b0` at `00442cc6`) is frozen as every
  `RF_BOARD_Y` part is. While the server's object NPCs bind to such a shape,
  1298 can hide it (`005cd620`, PQ-057); n3e has none, so it draws the load
  state, and play under the servers is PQ-393 (rig). The 1097 zones take
  1298's rule by inference (the 1097 exe is packed).
- **Recorded in:** GAPS, FEATURES, PARITY, MAP-EXPLORATION, BINARY-INDEX,
  STATUS, the evidence record. No package format, CONTRACTS or
  content/world.md change.

## D-206 — 2026-10-24 The KO world bake draws Moradon's magic anvil in the state 1298 gives it while its object NPC is in: a static draw, not object NPCs

- **Context:** PQ-395, the fix PQ-393 queued. 1298 hides the magic anvil
  `obj_co_itemup` (OPD event 5001, event type 8, `0x141b`) at load, and PQ-392's
  bake keeps it out (`event`, D-205). By PQ-393's binary chain, applied to the
  local server map and NPC tables (binary + local-asset; inference, not
  observed: rig frame open, PQ-396), 1298's AI server builds an object NPC for
  it and the client then shows the shape until NPC out hides it. The item asks
  for a choice between a static draw of that in-range state and n3e object NPCs
  (PQ-057, PQ-271). Claims and labels are in the
  evidence record.
- **Observed (binary):**
  - AI Server `00413693` calls the object-NPC builder for an SMD object event
    of type 1, 2, 3, 6, 7, 8 or 9 (`0041374d`–`00413788`); `0043bcaa` builds
    one only when the zone's server number matches (`0043bcc2`–`0043bcd0`) and
    the NPC table has a row for the event index (`0043bcd5`–`0043bcef`), and
    stores the record's status at `+0x50d` (`0043c085`–`0043c088`) and object
    type 1 at `+0x50f` (`0043c15b`); Ebenezer forwards both and writes them in
    every NPC-in (`00407745`, `00479d08`; PQ-393 E2, E3).
  - KnightOnLine.exe `005b4690` stores `+0x151` = 0 at load for an event
    shape whose type is neither 0 nor 5 (`005b4a5b`–`005b4a6a`). The NPC-in's
    object branch (`005cd620`) finds the shape by resource id (`005cde58`–
    `005cde5b`, `005b83a0`), and for a `0x1000` shape binds it (`005ce327`) and
    stores `+0x151` = 1 (`005ce334`); for event type 8 (`DEC` then `CMP 6`,
    `JA 005ce412`) it calls no part turn (`00447b60`) and, with status 1, stores
    1 again (`005ce447`; status 0 stores 0 at `005ce49d`). NPC out reaches
    `00455b70` and stores 0 (`005ce620`, PQ-393 C6).
  - Ebenezer gathers a user's NPC-in list from the nine region cells around
    the user's cell (`00423be6`, `00423cee`–`00423cef` and the eight further
    calls; PQ-250), and a map's region grid is its extent / 48 + 1 cells
    (`00472ebf`, `00472f6b`–`00472f80`), so the cells are 48 m.
- **Observed (local-asset):** the only type 8 shapes in the 21 1298 and seven
  1097 OPDs are `obj_co_itemup`, event 5001, NPC status 1: one in 1298
  `moradon_xmas` and one in `moradon` at (337.89, 389.95), one in the 1097
  `moradon` at (336.11, 399.48). Moradon's server map `moradon_0826.smd` has
  event 5001, type 8, status 1 at the 1298 position (PQ-393), and K_NPC 5001
  "Magic anvil" (`sPid` 5001, `byType` 24) is in the rig's 1.298 database
  and the OpenKO export. Its three parts: two unlit alpha parts (render flags
  `0x41`, blend 5/6) cycling 5 and 10 textures at 8 fps, and the table (one
  texture, flags 0).
- **Inferred:** a player in one of the nine 48 m cells around the anvil's
  cell (for the 1298 position, x in [288, 432) and z in [336, 480), with the
  cell taken as position / 48, which the user's cell writer, not read here,
  is assumed to do) has the anvil's NPC in and sees the anvil in its loaded
  pose; elsewhere 1298 hides it. The OPD's own NPC status equals the server
  record's for the anvil, so the bake reads the OPD's.
- **Selected:**
  - `ko_shapes.classify` returns `event_npc_shown` for a shape with an event
    id, event type 8 (`NPC_SHOWN_EVENT_TYPES`), OPD NPC status 1 and the
    `0x1000` kind (the object branch binds only that kind, `005ce31e`), with a
    mesh and no animation keys, and `ko_shapes.BAKED` takes it. The bake
    places it with the part rules every baked shape takes, its multi-texture
    parts on their first texture as D-205 does for the magic parts; the report
    counts these shapes (`npc_shown_shapes`) and the approximation is named.
  - Every other event shape keeps its class: types 1, 2 and 3 (1298 turns
    their parts through `00447b60`) and 6, 7 and 9 (their status can change
    in play by the AI's `byType` writers, PQ-393 A7) stay `event`; none is in
    a cooked zone. A type 8 shape with status other than 1 stays `event`.
  - The 1097 Moradon takes the rule by inference (the 1097 exe is packed and
    no 1097 server map is read), as D-205 did for the 1097 zones.
  - No format, protocol, server or client change: the parts are ordinary
    world parts. Server authority is untouched (render data only).
- **Considered:** object NPCs (PQ-271, PQ-057): a server entity bound to a
  world shape, sent to sessions in its interest cells, and a client that
  shows or hides the shape's parts with it. That is the faithful route but
  needs a package spawn record for object NPCs, an entity kind and shape id on
  the wire, per-shape toggling of baked world parts and the anvil's
  interaction, several items' work; it stays with PQ-271 and PQ-057, which
  then supersede this rule for the anvil. Leaving the anvil out (the current
  state) misses it wherever players stand near it, which is the whole centre
  of Moradon around the start.
- **Limits:** n3e draws the anvil from wherever its parts are in view, where
  1298 hides it outside the nine cells (inference, above), and from the first
  frame after load, before 1298's NPC-in arrives; the fx parts do not cycle
  (PQ-394). No interaction or name (PQ-057, PQ-271). The in-play visibility is
  binary + local-asset inference, not observed (PQ-396).
- **Recorded in:** GAPS, FEATURES, PARITY, MAP-EXPLORATION, BINARY-INDEX,
  STATUS, the evidence record. No package format, CONTRACTS or
  content/world.md change.

## D-207 — 2026-10-24 Movement admission holds one movement ahead: one applied per session per tick, one more held for the next, a third refused (amends D-014)

- **Context:** PQ-404, the fix PQ-403 queued. D-014 accepts "at most one
  queued movement per character per tick": the server refuses a second
  movement that reaches the same tick's command drain with code 4 'one
  movement per tick' (`server/src/simulation.rs`). The test client sends one
  movement in every 50 ms slot by its own clock (`client/network/world.cpp`),
  so a session whose sends reach the server near the drain boundary is
  refused whenever arrival jitter puts two in one drain. PQ-403 measured 19-24 %
  of moves refused with 20-40 ms of send jitter reaching the boundary, 59 of
  400 for a send 2 ms before the drain with no added jitter, and two per
  150 ms server stall for the real client
  (PQ-403 evidence). Each
  refused step is a snap back on the mover's screen.
- **Not KO-derived.** n3e's movement is intent-only and server-authoritative
  (LOOP.md "Kept different"; PARITY "Movement authority"). For context only:
  1298's client sends a start, a stop and a 1.5 s heartbeat without waiting on
  the server (KnightOnLine.exe `005c74b0`, `005d6430`, `005c403a`–`005c40aa`;
  binary, PQ-403), and Ebenezer refuses no single movement packet for its
  timing; it closes the session on the eleventh packet in a row under 0.1 s
  apart (Ebenezer-official.exe `00494beb`, `00494c65`–`00494cdc`; binary). No
  KO rule is imported.
- **Selected:**
  - A session's movement admission is a queue of two slots: the movement the
    next tick applies and one held behind it. A valid movement (the same
    session, entity, seq, direction and mode checks as before, code 3 when
    they fail) fills the first free slot; when both are full it is refused
    with code 4 and the same detail 'one movement per tick'.
  - Each tick applies at most one movement per session, the oldest, and moves
    the held one up. A drain that brings no movement therefore empties the
    hold. No session moves farther in any run of N ticks than N movements, as
    under D-014; the hold changes which arrivals are refused, never the bound.
  - Seq rules are unchanged: a held movement consumes its seq when it is
    admitted (a later seq must exceed it), a refused one does not, and the ack
    a view carries is the seq of the last movement applied.
  - Everything that clears or reads the pending movement does the same with
    the held one, through one type, so neither can be cleared alone: a
    respawn's request (its ack takes the newest admitted seq) and its
    completion, a skill cast's start, and a session's end (the player record
    is dropped). The rest (sit) admission and a skill's movement interrupt
    count a held moving input as movement; the layered attack pose reads only
    the movement this tick applies.
  - No wire, protocol, package or client change. The client's timing is not
    read or trusted: the hold depends only on how many movements the server
    has admitted and not yet applied.
- **Considered:** client ack pacing (rejected in PQ-403: it halves the
  movement rate on loopback, as acks come with 10 Hz views); a credit or token
  bucket that applies two movements in one tick after an empty one (no
  standing latency, but one extra step in a window of ticks, which loosens the
  bound); a deeper hold (more latency after a burst for refusals that only a
  server stall causes, where the server has fewer ticks than the client has
  slots and a refusal is the bound working); an intent held until changed, as
  an analogue of KO's event cadence (a wire and prediction change). None is
  selected.
- **Consequences:** while the hold stays full (sends keep pace with ticks
  after a burst) the server applies each movement one tick, about 50 ms,
  later; the mover predicts its own input and does not see it, others and
  server-side range checks do. Refusals after real server stalls remain, fewer
  (PQ-403's prototype: 51 to 34 per 20 s at 150 ms a second).
- **Recorded in:** D-014 (its admission sentence points here), GAPS
  "Movement admission", FEATURES, PARITY, CONTRACTS (movement admission),
  STATUS, the
  evidence record.

## D-208 — 2026-10-24 A server refusal names the request it answers: Error.request, and the client shows it on that feature only

- **Context:** PQ-405, queued by PQ-403. The wire `Error` carries a code and a
  detail and nothing else. Once a session exists the test client copied every
  Error's detail into the inventory, storage, friends and party status lines
  (`client/network/world.cpp`), so a movement refusal ('one movement per
  tick', 'invalid/stale movement or session') or a chat refusal replaced the
  bag and bank headers, the friends window, the party 'Last:' line and the HUD
  selection text until that feature's next reply. The client cannot tell what
  an Error answers from what it carries: code 4 (RATE_LIMITED) is shared by
  movement, inventory, storage, the social requests and chat; the detail is
  server prose; and the simulation (movement, storage, party, friend presence,
  consumables, chat) and the connection handler (bag, commerce, storage
  credential, friend list) send their refusals on one channel with no order
  between them, so an outstanding-request record per feature would still give
  a movement refusal to a bag request waiting at the same time.
- **Not KO-derived.** Engine protocol and client presentation; no KO rule is
  read or imported, and no binary claim is made.
- **Selected:**
  - `Error` gains `uint32 request = 3`: the Envelope body field number of the
    client message it refuses (9 Move, 11 Chat, 28 AdminRequest, 31
    PrivateMessage, 32 BagRequest, 34 StorageRequest, 36 StorageAuthRequest,
    38 FriendRequest, 40 FriendPresenceQuery, 42 PartyRequest, 45 Rest), and 0
    for an Error that answers no single request (handshake, login, character
    selection, the connection's frame and byte limits, a message the session
    does not accept). The server sets it at every refusal site
    (`server/src/network.rs` `refusal`, `simulation.rs` `reject`); the names
    are pinned against the encoded tags by a server unit test and a
    cross-language golden (`protocol/golden-error.hex`).
  - The client keeps the general status line: every Error's detail goes there
    as before (with the reconnect hint before a session). Once a session
    exists only the named feature's line takes it too: a BagRequest refusal
    the bag line, a StorageRequest refusal the bank line, a StorageAuthRequest
    refusal the bank and credential lines, a FriendRequest or
    FriendPresenceQuery refusal the friends line, a PartyRequest refusal the
    party line, each only when the package has that feature. A refusal of
    Move, Chat, PrivateMessage, Rest or AdminRequest, one naming 0, and one
    naming a number the client does not know reach no feature line.
  - The field is advisory presentation data. The server decides every
    refusal; the client neither retries nor changes state on it, and a wrong
    or missing value can only put a line in the wrong window.
  - No protocol version change: the field is additive proto3. A peer that does
    not set it (an older server) sends 0, so its refusals show on the general
    line only; one that ignores it reads the same code and detail as before.
- **Considered:** an outstanding-request record per feature in the client (no
  wire change, but the simulation's and the handler's refusals have no order,
  so it misroutes whenever a movement refusal arrives while a feature request
  waits); matching the detail text or the code (couples the client to server
  prose; code 4 is shared); a request id echoed in Error (bag, storage and
  friend requests carry string ids and movement a seq, party and presence
  their own sequence; naming the message kind is enough to choose the line).
- **Consequences:** a movement, chat or rest refusal no longer shows on any
  feature line; a feature's own refusal still does. A refusal of Chat,
  PrivateMessage, Rest or AdminRequest ('chat length/rate', 'invalid private
  message recipient', 'private message recipient unavailable', a rest
  refusal, 'admin queue full') now shows nowhere in the world: it reaches
  only the general line, which is drawn only on the login and selection
  panels (`client/render/play.h:53`) and is reset by the next World view.
  Before this decision these refusals showed in the world only by
  overwriting the bag, bank, friends and party lines and the HUD selection
  text. An in-world line for them is
  PQ-406.
- **Recorded in:** `protocol/wire.proto`, `protocol/README.md`, CONTRACTS
  (Phase 2 wire), GAPS "Movement admission", FEATURES (KOF-0006), PARITY,
  STATUS, the
  evidence record.

## D-209 — 2026-10-24 A chat, whisper, rest or admin refusal shows on the HUD's message line, not the chat line

- **Context:** PQ-406, queued by PQ-405 review round 1. Since D-208 a refusal
  of Chat, PrivateMessage, Rest or AdminRequest reaches only the general
  status line, which the world view does not draw, so in the world the player
  gets no feedback for it.
- **KO reference (binary, `KnightOnLine.exe`):** the 1298 client's reply to a
  whisper-target request (dispatcher `005c5140`, case `0x35`,
  `005c5cdb`–`005c5e24`) writes its failure text (text id `0x44d`, after the
  name; text `0x1dd4` when the reply's short is -1) in `0xffffff00` (yellow)
  to the message output window, `[ProcMain+0x48]` through `0052acd0`
  (`005c5d99`–`005c5dae`, `005c5de4`–`005c5dfa`), not to the chat window
  `[ProcMain+0x44]` (`00543410`, which takes received chat lines, PQ-178).
  `0052acd0` appends a line record with its colour at `+0x10` and keeps at
  most 255 lines. `005d23d0` loads `+0x44` and `+0x48` one after the other
  (`005d24a5`–`005d25c6`); the KO HUD cook already places them as
  `ka_chat_us` and `ka_msgoutput_us` (`tools/assetc/ko_hud.py`).
- **Selected:**
  - Once a session exists, a refusal naming Chat, PrivateMessage, Rest or
    AdminRequest also becomes the world's notice (`WorldState::notice`, with a
    count so a repeated text still counts as new). Move, request 0 and an
    unknown number stay off it, as they stay off the feature lines (D-208); the
    feature lines take nothing new.
  - The package HUD draws the notice where it already draws the client's own
    notices: the first line of its `combat` text, which the KO HUD binds to the
    message output window (`text_message` in `ka_msgoutput_us`) and the demo HUD
    to its right-hand message panel. The newest of a client notice and a server
    refusal wins. A package without a HUD draws it on a line of its own above
    the chat panel. The chat line keeps the last received chat line only.
  - The text is the server's detail, as on every other status line; no KO text
    id or game string enters the engine.
- **Not matched:** KO's yellow. The package HUD colours a text record as a
  whole and the message text shares one record with the combat status, so a
  per-line colour needs package data and a renderer change; queued as
  PQ-407.
  KO's message window keeps a scrolling log; n3e's line shows the newest notice.
- **Considered:** the chat line (`world.chat`, KO's chat window): KO puts the
  whisper failure in the message window instead, and the chat replays read
  `world.chat` as the last received chat line; the general status line drawn in
  the world (it carries login and connection text, and a movement refusal).
- **Server authority:** unchanged. The notice is presentation of a refusal the
  server decided; the client neither retries nor changes state on it.
- **Recorded in:** `client/network/world.h`, CONTRACTS, GAPS, FEATURES
  (KOF-0003), PARITY, STATUS, the
  evidence record.

## D-210 — 2026-10-24 The HUD message line keeps a short log, each line in the colour the package gives its kind

- **Context:** PQ-407, queued by PQ-406. Since D-209 a server refusal and the
  client's own notices share the first line of the package HUD's `combat`
  text, drawn in that record's one colour, and the newest replaces the last.
- **KO reference (binary, `KnightOnLine.exe`):** the message output window
  (`[ProcMain+0x48]`) appends each message through `0052acd0(text, colour)`:
  an empty text is ignored, the colour is kept per record (`+0x10`), at most
  255 records are kept and the oldest is dropped. `0052af90` wraps the text
  at `'\n'` and wherever the next character would pass the text area's width
  (`+0x124` - `+0x11c`), each wrapped line keeping the message's colour;
  in `0052acd0` wrapped lines past 100 are dropped, oldest first and one at a time, only while the scroll bar's `+0xc0` is above 0 and at most `+0xc0` of them (`0052ae7f`–`0052af17`). The window's load code
  (`0052a622`–`0052a72f`, in a function Ghidra has not defined) takes the child
  `text_message` as the text area and `0052aa10` cuts it into (height / the
  font's line height) single-line rows; `0052b4c0` fills them
  from the top with consecutive wrapped lines, each row in its line's colour
  (`+0xcc` from the record's `+0x10`), and empties the rest. A new message
  shows the last rows when the scroll bar's two values (`+0xb8`, `+0xc0`) were
  equal (`0052acd0`; reading `+0xb8` as the maximum and `+0xc0` as the position
  is an inference: `0052a970` redraws from `+0xc0`, and `0052acd0`, when the
  two were equal, sets the range to lines - rows and the position to that end). The colours callers pass are the
  caller's: the whisper-target failure from the server (`005c5da8`,
  `005c5df2`) and the client's own refusal of a whisper request (`005c7aa4`,
  `005c7b41`) are both `0xffffff00`; other messages use other colours
  (`0xffff00ff` NPC-in `005cdd41`, `0xff00ff00` `005da556`, `0xffff3b3b`
  `005cee0d`).
- **Selected:**
  - The HUD message line keeps a short log: the newest messages, wrapped as
    `0052af90` wraps (at `'\n'` and at the record's width, character by
    character), the last `rows` wrapped lines drawn oldest first from the top
    of the `combat` text, then the record's own lines (combat status, item,
    reward). An empty message is ignored. There is no scroll-back.
  - Each message has a kind, a server refusal (D-209) or a client notice, and
    each line is drawn in its kind's colour. The package gives `rows` and the
    two colours in an optional message block at the end of `hud.bin`
    (`N3HM`, any HUD version); without it a HUD keeps one row and the
    record's colour, the D-209 layout.
  - The KO HUD cook gives both kinds `0xffffff00`, the colour 1298 gives a
    refusal in this window from either side, and `rows` from `0052aa10`'s rule
    on `text_message` with the substitute font's line height, less the three
    rows n3e's combat status, item and reward lines take. The demo HUD gives its
    own colours and two rows.
  - The combat status stays in its record at a fixed row, the row after the
    message rows; the chat line is untouched.
- **Not matched:** the scroll bar and the 255-record / wrapped-line history (n3e
  keeps only what it draws); KO's other message kinds and colours, which n3e
  does not send; KO's font and DBCS extent wrapping (n3e wraps its monospaced
  substitute font by character).
- **Considered:** the log after the combat status (the newest message would
  then leave the line D-209 gave it, and the status would move up); a second
  record for the log (the KO window has one text area, `text_message`); one
  colour for every message (the binary passes a colour per message).
- **Server authority:** unchanged. The log is presentation of refusals the
  server decided and of the client's own notices; nothing is retried or sent.
- **Recorded in:** `client/render/message_log.h`, `client/render/presentation.h`,
  `client/assets/assets.cpp`, `tools/assetc/ko_hud.py`, CONTRACTS,
  `content/README.md`, GAPS, FEATURES (KOF-0003), PARITY, STATUS, the
  evidence record.

## D-211 — 2026-10-24 The HUD message line scrolls back through a bounded history; a message dropped past the record limit takes its wrapped lines with it

- **Context:** PQ-408, queued by PQ-407 (D-210). The message line keeps only
  the rows it draws, while 1298's message output window keeps a history behind
  a scroll bar.
- **KO reference (binary, `KnightOnLine.exe`):** `0052acd0` keeps at most 255
  message records (`+0xe4`), dropping the oldest record only; the wrapped lines
  (`+0x114`) are a separate list, of which those past 100 are dropped, oldest
  first, only while the track bar's position (`+0xc0`, read before the message)
  is above 0, one per drop and at most that position; the view then follows the
  bottom when the track bar's maximum (`+0xb8`) equalled its position, else
  keeps its first line. The window's `scroll` child (string `006d5b3c`) is a
  scroll bar (constructor `0040cf00`: type 5, line size `+0xbc` = 1) whose
  track bar (`+0xb0`; constructor `00410120`: type 7, maximum `+0xb8` = 10,
  minimum `+0xbc` = 0, position `+0xc0` = 0, page `+0xc4` = 2) is set by
  `00410660(min, max)` and `004106b0(pos)`, both clamping the position into
  the range. The scroll bar's `0040d090` moves the position by the line size
  on its up (reserved 0) or down (reserved 1) button's click (1) or repeat
  (`0x40000000`); the button (`00403c80`) sends the click on release after a
  press and the repeat on every pass while held once it has been held 0.5 s
  (`006a35e0`, a double). The track bar's `004103f0` starts a thumb drag on a
  press in the thumb (state `0xe`), moves by the page on a press above or
  below it, and while dragging moves the thumb by the cursor's motion
  (`004107f0`: the position is min + (max - min) × the thumb's fraction,
  truncated; past either end the position is that end and the thumb stays);
  a drag ends on release or when the cursor leaves the track. `00410700`
  places the thumb at position / (max - min) of the free track, unless the
  range is empty. Each change reaches the window as `0x100`, and `0052a970`
  redraws the rows from the position (`0052b4c0`).
- **Selected:**
  - An optional scroll block (`N3HS`) after the message block gives the
    record limit, the line limit, the line and page steps and the hold delay,
    and the HUD names four records: the up and down buttons and the track
    (click records `message_up`, `message_down`, `message_track`) and the
    thumb (an image, `message_thumb`). With it the message line keeps that
    history and scrolls as above; without it the line keeps D-210's log.
  - The KO HUD cook gives 255 records, 100 lines, steps 1 and 2 and 0.5 s
    from the binary, and binds the `scroll` child's buttons, track and thumb
    from `ka_msgoutput_us`. The demo HUD draws its own scroll bar and keeps a
    smaller history (12 records, 6 lines) so its replay reaches the limits.
  - **Correction** (record):
    a message dropped past the record limit takes the lines it wrapped to that
    are still kept, and the view's first line moves up with them (to the first
    line if it was among them). In 1298 the lines outlive their record, so
    while the view is off the bottom with its position at 0 (scrolled to the
    top, or brought there by trimming) every new message adds lines that
    nothing removes.
  - The track bar's first range: 1298's starts at 0 of 0–10, so the first
    message is drawn from its first line; n3e starts the same way without the
    10. Lines are wrapped when posted, at the record's current column count;
    when that count changes (a window resize in a HUD that scales) the kept
    records are wrapped again and the view returns to the bottom.
  - The combat status stays in its record on the row after the message rows;
    scrolling moves only the message rows.
- **Not matched:** the hold repeat runs on every client frame, as 1298's
  does, so its rate is the frame rate; the hold time counts only while the
  press that began on the button lasts (1298 counts it while any held button
  is over it); KO's font and DBCS wrapping (D-210).
- **Considered:** an absolute cap on lines (it would drop lines of messages
  the record limit still keeps, and has no 1298 counterpart); no record limit
  in n3e (the records would only bound memory, which the correction does); a
  mouse wheel (1298's message window handles none: `0052a970` takes only
  `0x100` and its off button).
- **Server authority:** unchanged. Presentation of refusals the server decided
  and of the client's own notices; nothing is sent.
- **Recorded in:** `client/render/message_log.h`, `client/render/presentation.h`,
  `client/render/viewer.cpp`, `client/assets/assets.cpp`,
  `tools/assetc/ko_hud.py`, `tools/assetc/demo_presentation.py`, CONTRACTS,
  `content/README.md`, BINARY-POLICY, GAPS, FEATURES (KOF-0003), PARITY,
  STATUS, the evidence record.

## D-212 — 2026-10-25 World parts cycle a texture sequence as 1298's part tick does: N3W6 sequence records (amends D-205, D-206)

- **Context:** PQ-394, the feature PQ-392 queued. 1298 cycles the texture
  of every shape part with more than one texture. n3e's KO bake drew the
  multi-texture parts it places (the bind points' and warp gates' magic
  parts, D-205, and the magic anvil's two fx parts, D-206) on their first
  texture as a static stand-in, and leaves every other shape with such a
  part (`animated_material`) out. The claims and labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** the part constructor
  `00442490` sets the texture index `+0x124` to 0 (`004425d5`) and the fps
  `+0xd8` to 10.0 (`004425c7`); the part load `00443440` reads the fps from
  the file into `+0xd8` (`0044356d`–`00443577`) and keeps one list entry per
  texture the file names, null for a texture that does not load. The part
  tick `004429b0`, only when the part has more than one texture
  (`00442c65`–`00442c81`), adds the frame time `[006d3ab0]` × fps to the
  index (`00442c83`–`00442c95`) and, when the sum is at least the count,
  stores sum − count × sum / count, that is 0 with the remainder dropped
  (`00442c9b`–`00442cb2`). It returns before the advance when the part fails
  its distance or plane test (`00442b74`, `00442baf` → `00442e17`). The part
  render `00443090` draws list entry `ftol(index)` when it is in
  `[0, count)` and not null, else no texture (`004430cd`–`004430ed`; an
  opaque part then draws its diffuse colour, `00443387`–`004433a2`); an
  `RF_ALPHABLENDING` part carries that texture into its alpha-list entry
  (`004431ff`). The frame time is
  bounded to (0.001, 1.0) s, with 1/30 outside (`0043ac60`, PQ-012).
- **Selected:**
  - `world.bin` `N3W6`: N3W5 whose kind 0 and kind 1 parts may set part
    flag bit 7 (`SEQUENCE`), a **texture sequence**: after the part's
    alpha record (if any) it carries u32 frame count (2 to 64), f32 frames
    per second (finite, above 0, at most 1000) and one u32 texture slot per
    frame (each below the world's texture count). Frame k draws its slot in
    place of the first-layer slot of every vertex the part draws; the
    second layer is unchanged. The writer requires every vertex the part
    names to carry frame 0's slot, so a reader that ignored the record would
    draw frame 0. The writer chooses N3W6 only when a part sets the bit,
    else the magic it chose before, so every world without one keeps its
    bytes. Older readers refuse the magic and the bit. `N3W1` and the `N3L`
    files cannot carry it (their part flags stay below bit 7). No engine
    number, wire field or server rule changes: the server checks the
    world's magic and size only and admits N3W6 as N3W2.
  - The sequence's meaning is the engine's, generic: a part's index starts
    at 0 when its chunk loads; each frame in which the client's world pass
    draws the part (its chunk resident, chunk box, parent and part sphere in
    view), the index grows by the frame time × fps in float32, and when it
    reaches the count it restarts at 0, the remainder dropped; the part
    draws frame `trunc(index)`, its alpha draw too. The frame time is the
    time between the client's world passes, bounded to (0.001, 1.0) s with
    1/30 s outside, the bound 1298 puts on its own frame time, here a
    generic stall guard. A test client may fix it (`N3E_TEST_SEQUENCE_SECONDS`)
    and log the sequence state (`N3E_TEST_SEQUENCE_LOG`).
  - The KO importer gives the sequence to every part it places that has
    more than one texture and an fps above 0: the frame textures in file
    order, the file's fps. Which parts cycle, their frames and their rates
    are package data; no KO rule is in the engine. A part whose frame
    textures are not all present keeps D-205's first-texture stand-in and is
    counted (`first_frame_parts`), as is every such part of an N3W1 build;
    the KO bake writes a map with sequences chunked, the reason kept as
    `n3w1_refused`. The bake report counts `sequence_parts`.
  - D-205 and D-206 change only in that their multi-texture parts now
    cycle; which shapes are placed is unchanged. The `animated_material`
    shapes stay out: 1298 Y-billboards most of their cycling parts
    (render flag `0x8`, `004429b0` at `00442cc6`), which n3e's world parts
    cannot (PQ-038); they are follow-up items.
- **Considered:** a phase from the clock, `trunc(t × fps) mod count` (it
  wraps the remainder where 1298 drops it, and advances while the part is
  out of view where 1298 holds it); per-frame vertex rewrites (an upload per
  part per frame); a texture-array animation in N3WT (a texture property,
  where 1298's sequence and rate belong to the part); keeping the static
  stand-in (the item's purpose).
- **Limits:** the advance follows n3e's own culling, not 1298's distance and
  plane tests (`004429b0`), and a streamed chunk that is evicted and loaded
  again restarts its parts at 0, where 1298 keeps a part's index while the
  zone is loaded. 1298 computes the reset on the x87 stack, so its stored
  value may differ from 0 by a rounding step (drawn as frame 0 either way);
  n3e stores 0. A frame whose texture failed to load draws untextured in
  1298; n3e does not bake such a sequence (none in the local data). Parts
  with several textures and fps 0 draw frame 0, exactly; fps below 0 (none
  locally) is not represented. The Karus magic parts' `0x8` Y billboard
  stays frozen (PQ-038). Not compared with a running 1298: static.
- **Server authority:** unchanged; render data only.
- **Recorded in:** content/world.md, CONTRACTS, GAPS, FEATURES (KOF-0005),
  PARITY, BINARY-INDEX, MAP-EXPLORATION, STATUS, the evidence record.

## D-213 — 2026-10-25 The KO bake places a static shape whose cycling parts do not billboard, with their texture sequences (amends D-212)

- **Context:** PQ-412, queued by PQ-394. D-212 gave world parts a texture
  sequence and the KO bake gave one to every multi-texture part it places,
  but `ko_shapes.classify` still leaves out every static shape with such a
  part (`animated_material`), because 1298 Y-billboards most of their
  cycling parts. The claims and labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** the shape manager load
  `005b4690` constructs a shape without the `0x1000` kind through `00443ae0`
  (`005b49a7`), which stores `+0x151` = 1 (`00443b41`), calls the shape's
  load (`005b4a28`) and touches `+0x151` only when the event id `+0x140` is
  not 0 (`005b4a2f`–`005b4a73`); the shape tick `00443f40` ticks every
  non-null part through `004429b0` (`00444226`) and the render `004442e0`
  draws every non-null part through `00443090`, testing only `+0x151` and
  `+0x150`. The part tick advances the texture index of any part with more
  than one texture whatever its render flags (D-212); after it, only flag
  `0x8` (the Y billboard, `00442cc6`) and flag `0x20` (a random timer,
  `_rand`) change the part's matrix. So a shape without an event id draws
  as any shape, and a cycling part without `0x8` or `0x20` is drawn in its
  loaded pose with its texture sequence: nothing beyond D-212 and the
  static bake's rules.
- **Selected:** `ko_shapes.classify` returns `material_cycle` for a shape
  that passes every rule a static shape passes (no event, NPC, extra kind or
  animation keys) and has a part with more than one texture and an fps above
  0, when none of those parts has render flag `0x8` (`RF_BOARD_Y`) or
  `0x20`, and it has a mesh; `material_cycle` is in `ko_shapes.BAKED`, so
  `ko_scene.object_geometry` places it as a static shape and gives its
  cycling parts their D-212 sequences. Its other parts are drawn by the
  static rules unchanged. A shape with a cycling part that has `0x8` or
  `0x20` stays `animated_material`, out of the bake (PQ-413, after PQ-038's
  world-part Y billboards). The bake report counts `material_shapes`. KO rules
  stay in the KO importer; no format, client or server change.
- **Considered:** returning `static` for these shapes (the report could not
  tell them apart); freezing the billboarding parts as the Karus magic
  parts are (the torches and fires would stand as flat quads at one angle).
- **Limits:** D-212's (n3e's culling, a streamed chunk restarts at 0). The
  1097 zones apply 1298's rule by inference (the 1097 exe is packed). No
  local cycling part has `0x20`. Not compared with a running 1298: static.
- **Server authority:** unchanged; render data only.
- **Recorded in:** content/world.md, GAPS, FEATURES (KOF-0005), PARITY,
  BINARY-INDEX, MAP-EXPLORATION, STATUS, the evidence record.

## D-214 — 2026-10-25 The target marker's parts draw in the frame's one far-to-near alpha pass, keyed by the part matrix's translation

- **Context:** PQ-380, the fix PQ-377 queued. n3e drew the target marker in
  a pass of its own after the actors and before the effect pass (ONE/ONE,
  depth test and writes on), its parts sorted only against each other by
  squared pivot distance, so every effect drew after it. The claims and their
  labels are in the
  evidence record.
- **Observed (1298 KnightOnLine.exe, binary):** the world frame `005c4c40`
  calls the target symbol `005c4e20` (`005c4d63`) after the actors and before
  the FX manager, then flushes the alpha list (`0043dd80` at `005c4d98`).
  `005c4e20` sets the shape's scale (slot `+0x34`, `0041f800`) and position
  (`+0x28`, `0041f740`), each of which rebuilds the part matrices
  (`004447f0`: the pivot as a translation times the shape matrix `0043b650`
  builds), ticks it (`+0x1c`, `00443f40` → `004429b0`, which for an upright
  part, flag 8, rebuilds the matrix with the same translation) and draws it
  through slot `+0x48` (`005c5129`: `004442e0` → `00443090`). With material
  flag 1 set on both parts (flags 9 and 1, local-asset), `00443090` queues
  each into the list keyed by the linear eye distance to the part matrix's
  translation (`+0x68`..`+0x70`), and draws nothing itself. The flush sorts the
  whole list far to near and sets z-write to its starting value for a
  primitive without `0x100` (read at `0043de41`, set at `0043e104`–`0043e10e`;
  `0x100` sets 0, `0043e0f7`).
- **Selected:** the client keys each marker part by the linear eye distance
  to the position plus its pivot at the symbol's horizontal and vertical
  scale (`target_marker_key`) and draws it as an external draw of the effect
  pass, after the world's alpha parts in the external list (D-201), sorted
  with every effect draw. Each part keeps N3TM's fixed material (ONE/ONE,
  depth test and writes, back faces culled, n3e's marker light and fog),
  which the KO cook already enforces against the shape's material; no format,
  engine number, wire field or server rule changes. Ties keep insertion
  order. The test client's marker comparison frame (`N3E_TEST_TARGET_MARKER`)
  leaves the marker out of that frame's pass and draws it alone after it,
  between its two captures, so the pair still differs by the marker only.
- **Considered:** carrying KO's flag word and blend factors in N3TM (the
  only local marker has one material, which the cook checks; a new magic for
  data with one value); a marker pass after the effects (wrong for every
  effect in front of the marker, as the old pass is for every effect behind
  it).
- **Limits:** the effect pass still keys skill effects once per instance
  (PQ-381); the swing trail and water are not drawn (PQ-307, PQ-028). KO's
  z-write for the marker is the device state at the flush's start, taken as
  on (D-201's reading). Static: not compared with a running 1298.
- **Server authority:** unchanged; presentation only.
- **Recorded in:** content/target-marker.md, CONTRACTS, GAPS, FEATURES
  (KOF-0009), PARITY, BINARY-INDEX, STATUS, the evidence record.

## D-215 — 2026-10-25 The renewal pause shortens to what is left of admission; a late landing that reopened admission is followed by the next renewal, not by the exit

- **Context:** PQ-415, found by PQ-414's review. Admission ends 2 s after the
  start of the last successful lease renewal attempt (D-142). An attempt that
  started inside admission and landed after it closed still succeeded: its
  conditional `UPDATE` found the database lease live and extended it to 3 s
  from its own commit. The landing therefore reopened admission until 2 s
  after the attempt's start. The renewal thread then slept its fixed 400 ms
  pause before checking admission, so an attempt of about 1.6-2 s ended the
  realm ("lease renewal stopped", "admission expired; restart required")
  although the lease had just been renewed. With a first renewal reply held
  1.8 s, the realm logged "admission was closed for 701 ms and lapses within
  the 400 ms renewal pause (198 ms left)" and exited (PQ-414 evidence). No KO
  behaviour is involved: realm ownership is an n3e engine rule (no binary
  counterpart; no Ghidra confirmation applies).
- **Question:** renew sooner after a late landing, or exit as the
  conservative outcome? The safety condition is that a realm never admits
  without a valid database lease (split-brain).
- **Safety reading:** a successful renewal proves the lease was live when its
  conditional `UPDATE` ran and extends it to at least 3 s after the attempt's
  start. A takeover needs an expired lease, so none can come before then.
  Admission until 2 s after that start is the same bound D-142 already grants
  every renewal, and the landing already reopened it. When the next attempt
  starts changes nothing about which lease admission trusts. Exiting buys no
  safety: the database lease outlives the reopened admission either way. It
  only turns a renewal that worked into an outage. This is an engine
  scheduling detail, not a product trade-off: lease length, admission length
  and failover time are unchanged, so it is not parked for the user.
- **Selected:** the pause before each renewal attempt is
  `persistence::renewal_pause`, computed from what is left of admission at the
  time: `min(400 ms, left - 400 ms)`, and zero when 400 ms or less is left.
  The next attempt therefore starts no later than 400 ms before admission
  ends, or at once when less than that is left. The rule applies to every
  pause, including the first one after start-up, which is measured from the
  attempt that took the lease (D-139). Normal renewals land in milliseconds,
  leaving about 2 s, so their pause stays 400 ms and the cadence is unchanged.
  What stays:
  - Admission is still measured from the start of the last successful attempt
    and lasts 2 s. It is reopened only by a successful conditional renewal.
  - The thread still checks admission before each attempt, and no attempt
    starts once admission has ended. An attempt that took 2 s or more lands
    with admission already ended, so the next check ends the realm as before.
  - A fenced renewal or any other error still invalidates admission and ends
    the process at once (D-142). The lock-wait retry is unchanged.
  - The thread stays the dedicated renewal thread on its own connection (D-199).
    No tick waits on it, and one attempt is in flight at a time.
  - Bounded: a zero pause follows only an attempt that itself took at least
    1.6 s, since 400 ms or less is left only then. The loop cannot spin, and
    it never retries a failed renewal.
  The late-renewal log line names the next pause, and its "lapses within the
  renewal pause" case is gone. An attempt that took 2 s or more logs that
  admission stays closed and that the next loop ends the realm.
- **Considered:**
  - Keeping the exit as the conservative outcome. It has no safety benefit (see
    above) and ends a realm whose lease was just renewed.
  - Renewing at once after every landing. That gives the same result here, but
    it renews back to back whenever a renewal takes over about 1.2 s and is
    harder to bound.
  - A longer lease or admission, start-to-start timing in general, and resuming
    admission after it expired. Those are PQ-206's failover trade-offs and stay
    there.
- **Limits:** an attempt that takes 2 s or more still ends the realm (its own
  window has passed). Admission is still closed between the old deadline and a
  late landing, so a session that sends a frame in that gap is still closed
  (PQ-206). A delay in thread scheduling longer than the few milliseconds left
  can still miss the check, and then the realm exits conservatively.
- **Server authority:** unchanged; the database lease and fence decide
  ownership, and admission never outlives a renewal's own 2 s.
- **Recorded in:** CONTRACTS (realm ownership), GAPS, STATUS, PQ-206's
  note, the evidence record.

## D-216 — 2026-10-25 A combat profile can be a ranged basic attack: a package range beyond the summed radii, checked in 3-D by the server; the client never chases into melee reach under it and does not shoot while it walks

- **Context:** PQ-416, queued by PQ-347. Since PQ-347 the opt-in glow
  package's bow selects 1298's bow profile (ready clip 92, the archery row's
  clip 26, 1450 ms), but the attack is still the melee swing: the client walks
  into melee reach before it strikes and the server refuses anything beyond
  it. The engine has no ranged basic attack.
- **KO reference (binary, `KnightOnLine.exe` 1298, SHA-256 `828ab0db…a5e5`):**
  with a left kind 70 or 80 bow or a right kind 71 crossbow, the auto-attack
  tick (`004659b0`, branch at `00465fd5`–`00465ff9`) never walks or chases:
  when the class's archery row's cast time × 0.1 + 0.15 s have passed since
  the last attack it calls the skill start `005819e0` and records the time
  whether or not the shot starts (`00466102`, `00466111`). For the archery
  rows (target type 7) `005819e0` checks the range with `00583780` and posts
  text `0xfa9` ("Skill Failed - Too far" in the 1298 installer's
  `Texts_us.tbl`, local-asset) when it fails; the range is the 3-D distance
  against (the hand item's `+0x4a` × 0.1 + the caster's radius + the
  target's radius + 1.0 + 1.0) × the type-2 add range / 100 (`00582b02`–
  `00582b26`, `005839a0`–`00583a2d`). The cast start (`00583f20`) stops the
  walk (`005d6430(0,1)` at `005844c2`); the cast tick (`00585830`) turns the
  caster to the target (`004579d0`) and cancels the cast (phase 4) once the
  caster's state leaves 6, as a walk does. A Ctrl or double click walks to
  the melee reach `00468620`, which for a bow alone in the left hand (attach
  `+0x42` 4) is half the summed radii + the bow's `+0x4a` × 0.1. For an NPC
  target the AI server's archery leaf (`AI Server-official.exe` `0040d471`)
  checks no range; Ebenezer's PvP leaf (`004664ea`) checks the 2-D distance
  against its own item field (`+0x3e` × add range / 100, squared) and its
  rate check (`00464b43`) refuses an archery effect less than 1.2 s
  (`00633e9c`) after the last.
- **Selected:**
  - An optional package file `ranged-attack.bin` (N3RB) names combat profiles
    that are ranged basic attacks. Each carries a `range` (metres beyond the
    actor's and the target's radii summed, 0.5–100) and a `reach` (metres
    beyond half the summed radii, 0–`range`), and the file carries one client
    notice text for a shot beyond range (at most 96 bytes, printable). It
    requires the N3A5 combat animation (engine 32) and the melee policy (the
    radii). No engine or wire version changes: the file is optional and both
    readers check it.
  - The server checks a strike under a ranged profile (the profile its
    committed equipment selects, as for the interval) against actor radius +
    target radius + `range` in 3-D, and refuses `out_of_range` beyond it;
    under a melee profile nothing changes. A ranged strike is never a moving
    strike (`Entity.strike_moving` false): KO's cast stops the walk.
  - The client never chases under a ranged profile: an armed attack whose
    target is beyond the strike range does not walk; it posts the package's
    notice and tries again one interval later, as `004659b0` does. A Ctrl or
    double click still walks, to half the summed radii + `reach`
    (`00468620`). It does not shoot while the player moves the character with
    the keys; otherwise it stops its own walk and faces the target when it
    shoots.
  - KO numbers stay package data. The glow cook gives the bow profile
    `reach` = the Azagai's range column × 0.1 and `range` = that + 2.0, from
    its 2145 Item_Org row (the column 1298's `+0x4a` reads: Item_Org's
    layout matches 1298's up to column 20, an inference by field sizes),
    refused unless the class's archery row is a type-2 row with no range of
    its own and an add range of 100 and all the bow's grades share one range;
    the notice is the 1298 text 4009.
- **Server authority:** the server, not the client, decides the range from
  committed equipment and positions. KO's AI server checks no range for an NPC
  target (a client-trust weakness, not imported); n3e keeps its server range
  check (LOOP.md "Kept different"). Ebenezer's own PvP formula is not used:
  n3e has no PvP. The glow package's bow keeps the server's 29-tick cooldown
  (1450 ms), stricter than Ebenezer's 1.2 s minimum but equal to what KO's
  client sends. The interval is per-profile package data with no engine 1.2 s
  floor, so a package can set a shorter one. An honest client sees KO's
  behaviour.
- **Considered:**
  - Archery as a package skill through the skill runtime: rejected. Each shot
    would take two durable cooldown gates, the skill damage is the NPC magic
    formula (`0040e7c4`), not archery's (`0040d471` adds to the basic attack's
    `00443a34`), and R is the basic attack.
  - A range per item in the equipment policy: not needed yet. The combat
    profile is already chosen per item row, so a bow family with another range
    takes its own profile.
  - Landing the strike at the cast's end, cancelled by a move: KO's real
    timing, but it needs a pending strike in the simulation and a second
    presentation event. Queued as PQ-420; this slice resolves the strike when
    the server accepts it, and the client draws its hit at the clip's marker
    as before.
  - Refusing a ranged strike while the server still holds queued movement:
    rejected. An honest client stops and shoots in the same 50 ms, so its last
    step can still be queued and the shot would be refused. Dropping the
    queued steps instead (as a skill cast does, D-207) would snap back what
    the client already showed.
- **Limits:** the strike lands at once, not 1.3 s later, and a later move
  does not cancel it (PQ-420). A modified client could shoot while walking;
  each shot still needs range, interval and a living target. No arrows are
  required or used (PQ-421); the damage is the basic attack's with the bow's
  package attack, which the glow package keeps at 0 (PQ-422); no cast FX 500
  and no clip stretched to the cast time (PQ-423); no arrow in flight
  (PQ-417). The package radii are n3e's melee radii (1 m each in Moradon),
  not KO's actor radii. The notice is the client's own text line, posted once
  per interval while the target stays beyond range.
- **Recorded in:** `content/combat-animation.md` (N3RB), CONTRACTS, GAPS
  ("Magic types"), FEATURES KOF-0011, PARITY, STATUS, the
  evidence record.

## D-217 — 2026-10-25 A ranged profile can carry a cast time: the server holds the shot and lands it when the stretched clip reaches its marker, unless the archer moves, dies, changes weapon or the target goes

- **Context:** PQ-420, queued by PQ-416 (D-216). Since PQ-416 the glow
  package's bow shot resolves when the server accepts it, as the melee swing,
  and its clip 26 plays at its own speed (1.6 s, a 0.2 s blend) with the hit
  drawn at its marker 1.57 s later. A walk after the shot does not cancel it,
  and a modified client can shoot while walking (D-216 Limits).
- **KO reference (binary, `KnightOnLine.exe` 1298, SHA-256 `828ab0db…a5e5`):**
  the cast start `00583f20` (a row with a cast time, `+0x78`) records the
  casting row (`+0xb04`) and target (`+0x48`), stops the walk
  (`005d6430(0,1)`), plays the row's start animation through `00461ab0` and
  sends the casting phase (1). `00461ab0` sets the clip's playback rate to
  (end frame − start frame) / (`+0x78` × 0.1 s) when that time is above 0.1 s
  (`006a40d8` and `006a3d1c` are both 0.1), so the whole clip spans the cast
  time, and puts the caster in action state 6. The receive of another
  player's casting phase (`00585a90`) plays the same clip through the same
  `00461ab0`. The cast tick `00585830` turns the caster to the target
  (`004579d0`) every frame, ends the cast through `00584b00` (the flying and
  effecting phases) once `004689f0` finds the state-6 clip's frame past its
  first marker (clip `+0x34`: previous frame below it, current frame at or
  past it) and cancels the cast with phase 4 (-100) once the action state is
  not 6 or the move state (`+0x308`) is not 0; a walk (`0045a950`, from
  `005d6430`) sets the move state and action state 0. The frame does not
  advance during the clip's entry blend (`00418b20`, PQ-273). Neither
  `00585830` nor `00584b00` checks the range again.
- **Selected:**
  - `ranged-attack.bin` gains a second layout, `N3RC`: each entry appends u32
    `cast_ms`, 0 (the shot lands when accepted, as `N3RB`, which both readers
    still accept) or 101–10000. A profile with a cast time has exactly one
    attack clip, that clip has a first marker and no other profile (and no
    other role of its own but its moving clip) uses it. Both readers stretch
    that clip to the cast time: its key times, duration and markers scale by
    `cast / duration`; the entry blend stays. The landing is
    ceiling((blend + first marker × cast / duration) / 50 ms) ticks after the
    acceptance, and must not exceed the profile's interval.
  - The server checks a shot under such a profile as D-216 does, then holds
    it instead of resolving it: the strike fields show the cast from the
    acceptance tick (`strike_tick`, `strike_target`, `strike_style`,
    `strike_sequence`; `strike_result` `casting`, no damage), so observers
    start the clip then, and the interval counts from it. At the landing tick
    it resolves the strike through the ordinary path (wear, damage, ledger,
    AI, death), keeps `strike_tick` at the cast start and publishes the hit as
    a new presentation event (kind 6, `hit`, the request sequence). The
    archer's `ActionResult` comes at the landing or the cancel.
  - The shot is cancelled, with no effect and no cost, when a movement input
    that moves is admitted after the acceptance (`interrupted`; inputs
    already queued at the acceptance may drain), the archer dies
    (`actor_dead`), its session or life changes (`stale_session`), the
    target is gone or dead (`stale_target`, `target_dead`) or the committed
    equipment selects another profile (`equipment_changed`). A cancel clears
    `strike_tick` and `strike_sequence`, so observers stop the clip. No other
    strike, skill or rest starts while a shot is held. The range is not
    checked again at the landing, as in KO. The landing waits, a tick at a
    time, while a durable combat write is pending on the archer or on the
    target (another player's wear commit) or the server has no combat or
    settlement capacity for it, since the interval is already spent; a shot
    still waiting 20 ticks (1 s) past its landing tick is dropped
    (`combat_pending`).
  - The client keeps the attack on after `interrupted` (`00585830`'s cancel
    does not touch auto-attack), waits for the result up to 2 s past the
    cast time, cancels its own predicted clip when the keys move it during a
    held shot, and draws the hit, blow and struck sounds on the kind 6 event
    with no marker delay; a held shot's start event draws no hit. Swing sound
    markers of a stretched clip scale with it.
  - The glow cook sets the bow profile's `cast_ms` to the archery row's cast
    time × 100 (13 → 1300 ms; refused unless above 100). Clip 26 (1.6 s,
    blend 0.2 s, marker 1.3737 s) then lands 27 ticks (1.35 s) after the
    shot, inside the 29-tick interval.
- **Server authority:** KO's client decides the landing (it sends the
  effecting phase when its arrow arrives) and its AI server applies the hit
  with no range check (`0040d471`); n3e's server checks the range at the
  acceptance, holds the shot on its own clock, and decides the cancel from
  its own movement admission, life, equipment and target state (LOOP.md
  "Kept different"). An honest client sees KO's timing; a client that keeps
  sending movement cannot land a shot.
- **Considered:**
  - The cast time as a separate server-side constant per profile, with the
    landing written by the cook: rejected; the landing derives from the clip
    both readers already bound, so the two cannot disagree.
  - Rolling the outcome at the acceptance and publishing it with the start
    event: rejected; it would tell the client the result 1.3 s before it
    lands, and the target may change meanwhile.
  - Cancelling on any displacement from the acceptance point (as a skill cast
    does, D-207): rejected; the honest client's last queued step can still
    apply after it stops and shoots (D-216), which would cancel every such
    shot. Dropping the queued steps would snap back what the client showed.
  - A cancel event (kind 7): not needed; clearing `strike_tick` reaches late
    joiners too.
- **Limits:** the shot lands at the clip's marker; the arrow's flight (PQ-417)
  adds its travel time later. The skeletal bow plug's own clip (PQ-317) plays
  at its speed, not stretched with the wearer's (PQ-424). Observers see the
  archer's facing as before (only the local client turns to the target).
  The tick quantization lands up to 50 ms after the marker, and the strike's
  wear write commits before its hit is published, as for every strike, which
  adds a tick or more.
- **Recorded in:** `content/combat-animation.md` (Cast time (N3RC)),
  CONTRACTS, GAPS ("Magic types"), FEATURES KOF-0011, PARITY, STATUS, the
  evidence record.
- **Amended (PQ-424, 2026-10-26):** the skeletal plug's clip is no longer a
  limit. In 2233 the cast stretch (`005719a0`, 1298's `00461ab0`) rewrites
  only the rate of the wearer's clip in the wearer's own animation control,
  and the plug tick (`00434980`) sets the inner character's speed to 1.0
  before each advance at its own clip's rate (binary, 2233 image `53ffa5c2…`),
  which is what n3e does. Evidence.

- **Amended (PQ-467, 2026-10-29):** a profile with a hold (N3RH, D-233) has
  its range checked again at the landing (and at the release of a shot with
  a flight) against that hold, as Ebenezer's magic packet checks `004c1dbe`
  on each phase of an archery row; the start limit is still checked only at
  the acceptance.
## D-218 — 2026-10-26 A ranged profile can consume an inventory item per shot: the server refuses a shot without it and removes it in the strike's durable commit

- **Context:** PQ-421, queued by PQ-416 (D-216). Since PQ-416 the glow
  package's bow shoots without arrows; 1298's archery needs them and uses one
  per shot.
- **KO reference (binary):** `KnightOnLine.exe` 1298 (SHA-256
  `828ab0db…a5e5`): the skill start `005819e0` calls the usable check
  `0057f7f0` (`005829e2`) before its range check `00583780`; a failure posts
  a text and casts nothing, and the bow tick (`004659b0`) still records the
  try, so it repeats once an interval. `0057f7f0` refuses a row whose need
  item (`+0x70`) is not 0 or 9 and matches neither hand item's kind (`+0x40`)
  / 10 (text `0xfa5`, 4005 "Skill Failed - Improper item"); for a row with an
  exhaust item (`+0x74`, not 0 or 379006000) and type 2 in either type
  column, it takes the item's count from the first of the 28 inventory slots
  holding it (`004a29e0`) and refuses when that count is below the type-2
  row's arrow count (`+0x14`; text `0xfa7`, 4007 "Skill Failed - Not enough
  item"), unless the item's extension row marks it as exempt (`+0x14` / 10^8
  of 2, or 3 with `+0x34` 4 or 6; the arrow's row is all zero there).
  `Ebenezer-official.exe` (SHA-256 `7d83cc28…bcb`): the flying phase
  `0046f3f1`, which the client sends at the cast's end, takes the main row
  (map `+0x1370`) and the type-2 row (map `+0x1398`) and calls `004b0792`
  (item `+0x14`, bag 1, count = type-2 `+0xc`, 0); a result below 2 fails
  the cast (4). `004b0792` scans the bag's slots (bag 1: the 28 inventory
  slots 14–41) for the first holding the item number; for a countable item
  (`+0x4e` ≠ 0) whose kind (`+0x36`) is not 255 it subtracts the count,
  restores it and returns 1 when that leaves it below 0, clears the slot at
  0, and returns 2 after sending the bag update (`0x3d`). No match, an
  unknown item or a user below the item's requirement stats returns 0. For a
  NeedArrow above 1 the flying phase also sets the multi-arrow counter
  `+0x89cc` that the rate check `00464b43` spends.
- **KO reference (local-asset, the player's 1298 tables):** every archery row
  (102003–208003) has need item 7 and exhaust item 391010000; their type-2
  rows have arrow count 1. Item_Org 391010000 is "Arrow", kind 120,
  countable, buy price 1, weight 0. KO's pickup clamps a stack at 9999
  (`Ebenezer-official.exe` `004a7f1b`, BINARY-POLICY; KOF-0022's trade too).
- **Selected:**
  - `ranged-attack.bin` gains a third layout, `N3RD`: each entry appends u32
    `ammo` (0, or a 1-based index into the inventory items) and u32
    `ammo_count` (0 with no ammo, else 1 to the item's stack limit); after the
    notice comes a second notice, the client's line for a shot without ammo
    (0-96 printable bytes). The ammo item must not wear (durability 0), and a
    package that names one must carry the wear policy, whose durable strike
    commit removes it. Both readers still take `N3RB` and `N3RC`.
  - The server refuses a strike under such a profile (`no_ammo`, no effect)
    when the first bag slot holding the item, in slot order, holds fewer
    than `ammo_count`, at the acceptance (spending no interval) and again at
    a held shot's landing (whose interval its cast start already began,
    D-217). A shot that lands removes `ammo_count` from that slot in the
    same transaction as its wear (the strike's durable commit, now made
    whenever the profile names ammo, even for a miss or no wear), clearing
    the slot at 0; if the locked durable bag no longer has enough, the
    commit applies nothing (neither wear nor ammo) and the strike fails
    `no_ammo`, its interval likewise already begun. A held shot that is
    cancelled consumes nothing (KO's flying phase is never sent). Only bag
    slots count: equipment and storage do not.
  - So that the commit does not delay the hit, a held shot under such a
    profile starts its landing (and its commit) one tick before its landing
    tick; the commit's completion publishes the hit at the landing tick, as
    a shot without a commit is. The result therefore still comes inside the
    interval (the glow bow: hit at 27 ticks, interval 29), and the client's
    1.45 s cadence is 1298's. The cancel window ends at that earlier tick: a
    move admitted in the last tick before the landing no longer cancels the
    shot (the glow bow: 1.30 s against 1298's marker at 1.316 s; before,
    1.35 s). A slow database still delays the hit, as for every commit.
  - The client counts the same first slot in its last bag state; without
    enough it sends no shot and posts the ammo notice once an interval,
    before the range check (as `0057f7f0` runs before `00583780`), and keeps
    the attack on after a `no_ammo` result.
  - The glow cook adds 1298's arrow as an inventory item from the player's
    Item_Org row (label, countable, stack 9999, no wear, weightless, price 1,
    sold by the supplies shop) with a starting stack, and gives the bow
    profile `ammo` = the arrow and `ammo_count` = the type-2 row's arrow
    count, refusing an archery row whose need item is not the bow kind / 10 or
    whose exhaust item is not that Item_Org row, and 1298's text 4007 as the
    ammo notice.
- **Server authority:** the client never names or counts the arrows it uses;
  the server reads its own bag, and the database transaction that locks the
  character decides the removal. KO's client checks the count and Ebenezer
  removes the arrows only when the client sends the flying phase, so a
  modified client that skips it shoots for free (its effecting phase is not
  tied to it); n3e removes them with the landing it decides itself (LOOP.md
  "Kept different").
- **Considered:**
  - A separate ammo transaction beside the wear one: rejected; two commits
    per shot could leave one without the other, and the hit already waits
    for one durable write.
  - Summing every stack of the item: rejected; both KO programs use the first
    slot holding it, and with a count of 1 the two agree whenever a stack
    exists.
  - Removing the arrow at the acceptance: rejected; a cancelled cast would
    spend it, which KO's does not.
- **Limits:** no multi-arrow skills (NeedArrow above 1 and `+0x89cc`); the
  item's requirement stats are not checked (the arrow has none); the
  improper-item check (4005) is met by construction, since the ranged
  profile is selected only by the bow; quivers, arrow types and an arrow
  slot are absent. The hit still waits for its commit when the database
  takes more than a tick.
- **Recorded in:** `content/combat-animation.md` (Ammunition (N3RD)),
  CONTRACTS, GAPS ("Magic types"), FEATURES KOF-0011, PARITY, STATUS, the
  evidence record.

## D-219 — 2026-10-26 A ranged profile can carry a type-2 skill hit: the server resolves its strike on an NPC with KO's type-2 damage terms; the glow bow gets its Item_Org attack and durability

- **Context:** PQ-422, queued by PQ-416 (D-216). Since PQ-416 a ranged shot
  deals the basic attack's damage, and the glow package's Azagai carries
  attack 0 (presentation only, PQ-317), so the bow hits with the bare-hand
  attack. 1298's archery is a skill (class × 1000 + 3) whose NPC damage the AI
  server resolves through its type-2 leaf.
- **KO reference (binary, `AI Server-official.exe`, SHA-256
  `8715084f…0435`):** the magic packet's effecting phase (3) dispatches on the
  MAGIC row's type (`+0x17`) and calls the type-2 leaf `0040d471` for type 2
  (`0040cd1d`). `0040d471` looks up the MAGIC_TYPE2 row (map `+0x160`; none:
  no effect), calls the user damage `00443a34` with the skill id, adds the
  row's AddDamagePlus (`+0xe`, a short) and applies the sum only when it is
  above 0; it checks no range. `00443a34` with a skill id above 0 takes the
  skill branch: for a type-2 row with HitType (`+4`) 0 the hit grade is the
  basic attack's grade function `00444164` of (hit rate / evasion) ×
  (HitRate (`+6`) × 0.01f) rounded to f32, and the damage base is
  `ftol`(AddDamage (`+8`) × 0.01f × (attack × 200 / (defence + 240))); on a
  grade of 1–3 the damage is `ftol`(base × 0.6f + rand(0..base) × 0.89f +
  0.99) (`00443c9c`–`00443ce8`; constants `004b3a6c` 0.01f, `004b43a8` 0.6f,
  `004b43a4` 0.89f, `004b4398` 0.99 double; `0045b150` is `__ftol`, which
  truncates), and 0 on grade 0. The basic attack (skill id 0) is n3e's
  existing player-to-NPC formula, base × 0.85f + rand(0..base) × 0.3f
  (`00443cef`–`00443d18`). HitType 1 and 2 roll a flat percentage and
  HitType 1 scales the raw attack instead; both then pass through the hand
  magic `00443e17` and the `+0xc3` bonus as the basic attack does. The
  MAGIC_TYPE2 binding (`004107ab`) and load (`0043b638`) put HitType at
  `+4`, HitRate `+6`, AddDamage `+8`, AddRange `+10`, NeedArrow `+0xc` and
  AddDamagePlus `+0xe`. `Ebenezer-official.exe` (SHA-256 `7d83cc28…bcb`):
  the item sum `0049e11c` divides a zero-durability item's damage by 10; the
  weapon attack `004a0d2a` takes a left-hand item of kind / 10 = 7, 8 or 10
  in full on the dexterity path with the class's bow coefficient (`+0x3c`).
  For a player target Ebenezer's own leaf `004664ea` deals the PvP core
  `0049e7e4` + AddDamage / 3 (/ 2 in one zone case) after its 2-D range test.
- **KO reference (local-asset):** the OpenKO backup's MAGIC_TYPE2 rows for
  every archery skill (102003–208003) are HitType 0, HitRate 100, AddDamage
  100, AddRange 100, NeedArrow 1, AddDamagePlus 0 (not binary-matched; the
  1298 client's `Skill_Magic_2.tbl` agrees except AddDamage 0, a column the
  client does not use for damage). The 2145 Item_Org row of the Azagai
  (1110532000 and its grades' base rows) has damage 116 (column 16) and
  durability 8000 (column 20); on the 11 kind-70 bows both 1298's Item_Org
  and the backup's ITEM table hold, columns 16, 17, 18 and 20 equal ITEM's
  Damage, Delay, Range and Duration.
- **Selected:**
  - `ranged-attack.bin` gains a fourth layout, `N3RE`: `N3RD` with, per
    entry after the ammo count, u32 `hit` (0: the basic attack's damage; 1:
    a type-2 skill hit) and u32 `hit_rate` (1–1000), `add_damage` (0–300,
    the largest AddDamage in the backup's MAGIC_TYPE2) and `add_damage_plus`
    (0–10000), all three 0 when `hit` is 0. Both readers still take
    `N3RB`–`N3RD`. No engine or wire version changes.
  - The server resolves a player's strike on an NPC under such a profile
    with KO's HitType-0 type-2 terms above (the same rolls and order as the
    basic attack: the grade, then the damage only on a hit) and adds
    `add_damage_plus`; a strike whose sum is above 0 is a hit, so a miss
    with `add_damage_plus` above 0 deals it, and a sum of 0 (a miss, or a
    hit for 0) is a miss, as `0040d471` applies nothing and reports both
    alike (its last field -104). The f32
    constants are promoted exactly and the sums are exact in f64 in the
    bounded domain, so truncation matches the x87 result. NPC strikes and
    profiles without the hit are unchanged.
  - The glow cook gives each bow profile entry the class archery row's
    MAGIC_TYPE2 values from the operator's own export
    (`tools/ko-reference/inspect_db.py --table MAGIC_TYPE2`, read through a
    checked binding in `tools/assetc/ko_tables.py`), refusing a missing
    export or row, a HitType other than 0, a row whose HitType, HitRate,
    AddRange or NeedArrow disagree with the 1298 client's type-2 row, or
    values outside the bounds above.
  - The glow cook gives the Azagai items (kind 70, worn alone in the left
    hand) the package's bow stats category (dexterity path, off hand in
    full: `004a0d2a`'s rule), attack = their 2145 Item_Org damage (column
    16) and an initial durability = its column 20, so that the bow is not
    counted as broken (`0049e11c`, n3e's stats rule). Their shots still
    wear nothing, because the glow package's wear policy gives the Azagai
    no attack slots; a ranged basic attack wears attack-slot items as a
    melee one does.
- **Server authority:** the server picks the profile from committed
  equipment and reads the skill terms from its own package; the client sends
  only the attack intent, as before. The AI server's missing range check is
  not imported (D-216).
- **Considered:**
  - The item's original premise, the basic attack's damage plus
    AddDamagePlus: rejected after decompiling `00443a34`, whose skill branch
    differs (HitRate scales the grade ratio, AddDamage the base, and the
    coefficients are 0.6f / 0.89f + 0.99 instead of 0.85f / 0.3f).
  - The class's own COEFFICIENT bow coefficient: not taken; the Moradon stats
    archetype is one shared class (class selection is still open), so the
    package's bow category keeps its coefficient.
  - Adding the Item_Ext grade bonuses (2145 Item_Ext column 9: +66, +32, +47,
    +84) to each grade's attack: not done; which field the server adds is
    not yet located in a binary. Queued. PQ-425 (2026-10-26) located it: both
    clients' tooltips show Item_Org column 16 + Item_Ext column 9 (1298
    `004d6320`, 2233 `005aa8e0`), and 1298's Ebenezer reads the worn number's
    own ITEM row (`0041f077`, `0044729b`), whose Damage holds that sum in the
    reference data; PQ-434 is to amend this rule. Amended 2026-10-26 by
    D-221 (PQ-434): each grade's attack is Item_Org column 16 + Item_Ext
    column 9 and its durability column 20 + Item_Ext column 13.
  - PvP (`004664ea`): n3e has no player targets yet (PQ-065); queued.
- **Limits:** HitType 1 and 2 are not supported (no archery row uses them);
  no hand magic (`00443e17`) or `+0xc3` bonus, as for the basic attack;
  the bow does not wear; one shared stats archetype. KO keeps the base and
  the damage in 16 bits (`MOVSX` of `DI`, the short return of `00443a34`):
  with `add_damage` above 263 and an attack near n3e's 10,000 limit against
  no defence the result passes 32,767, where KO's would wrap; n3e computes
  in 32 bits and does not emulate that overflow, as `content/stats.md`
  does not for the stats.
- **Recorded in:** `content/combat-animation.md` (Skill hit (N3RE)),
  `content/damage.md`, CONTRACTS, GAPS ("Stats and damage"), FEATURES
  KOF-0011, PARITY, STATUS, the
  evidence record.

## D-220 — 2026-10-26 A ranged profile can carry a cast effect: an effect clip drawn on the caster's joints, turned with its facing, from the cast start until the cast ends

- **Context:** PQ-423, queued by PQ-416 (D-216). Since PQ-420 (D-217) the
  glow bow's shot is a held cast with 1298's stretched clip 26, but nothing
  is drawn on the archer during it. 1298's archery rows (102003–208003)
  name a self FX, 500, at part 12, whose bundle `fx/arrow.fxb` holds one
  mesh part: the arrow, with its draw sound 311 (`bspear_pull_0.wav`).
- **KO reference (binary, `KnightOnLine.exe`, SHA-256
  `828ab0db…a5e5`):** the cast start `00583f20` (a row with a cast time)
  calls the FX manager's trigger `00479de0`(caster, `+0x44` % 1000, the
  row's self FX `+0x40`, caster, the same part, index -1, move type -1) at
  `0058447f`, and a second time with |`+0x44` / 1000| and index -2 at
  `0058449a` when that is not 0; then it stops the walk (`005844c2`) and,
  for a type-2 row (`+0x8c` or `+0x90` == 2), plays clip `0x1c` (28)
  instead of the row's start animation (`+0x34`) when either hand item's
  kind byte (`+0x40` of `+0x2c8` or `+0x2cc`) is `0x47` (71, a crossbow)
  (`005844c7`–`0058451f`). An observed player's casting phase `00585a90`
  does the same on that caster (`00585e30`, `00585e4b`; clip `0x1c` from
  the caster's own hands, `00585e7d`–`00585ea9`). The flying phase
  `00584b00` stops both (`0047a710`(caster, FX, -1 / -2, 1) at
  `00584f6f`/`00584f84`) when the row has a flying FX (`+0x50`; 590 for
  archery), as the observer's flying receive `00585f20` does
  (`00586043`/`00586058`) and the fail receive `00586fa0` does for a
  cancelled cast (-100) or an observed caster in state 6; `0047a710` with
  1 calls `00475e30`(1), which ends the bundle at once (state 0, every
  part's slot `+0x28`). The bundle tick `00477590` with move type -1 puts
  the bundle at the target joint's position (`+0x104`) every tick and,
  when source and target are one actor, its direction at that actor's
  `0045a200` (the rotation of +Z by its quaternion `+0x7c`) with y = 0,
  normalised (`004786ba`–`0047871c`); its velocity is not used. The mesh
  part tick `0048f440` turns the part from +Z (`+0x228`, set by the
  constructor `0048e840`) to the bundle direction (`0048f700`), scales it
  (`00490120`) and puts its translation at the bundle position plus the
  turned part position (`0048fd40`) in the shape's matrix `+0x14c`; the
  shape tick `00480a70` multiplies the shape's own matrix `+0x54` (scale,
  rotation and the file's position, `0043b480` → `0043b650`, copied from
  the loaded shape by `004815c0`) by it, so the shape's file position
  offsets the mesh in the turned frame. The bundle load `00478bc0` reads 26
  slots for version 1; past the end of a 16-slot file `ReadFile` leaves
  the kind at the last value read (0). The base trigger `00475d20` plays
  the FX row's sound (PQ-013).
- **KO reference (local-asset):** 1298 `Skill_Magic_Main_us.tbl` (SHA-256
  `d141e19b…d217`): every archery row has self FX 500 (column 8), part 12
  (column 9), flying FX 590 (column 12), start animation 26, type 2.
  `fx.tbl`: 500 → `fx/arrow.fxb`, sound 311; `sound.tbl` 311 →
  `Snd\bspear_pull_0.wav`. `arrow.fxb` (SHA-256 `365b7675…`, the same in
  the 1298 installer, `ref/ko-src` and the 2145 packs): version 1, life
  1000, velocity 77, 16 slots, one mesh part (version 4, base 1, life 500,
  blend 5/6, fade-out 0.2) on `fx/arrow/item_arrow.n3shape`, whose
  transform is position (1.782, 3.721, -0.409), no rotation, scale 1.
- **Selected:**
  - `ranged-attack.bin` gains a fifth layout, `N3RF`: `N3RE` with, per
    entry after the skill-hit fields, the cast effect: u32 key length
    (0–64) and the key (printable ASCII, an effect clip of the package's
    `effects.bin`; empty: none), then u32 joint count (0 without a key,
    1–2 with one) and the joints, u32 each, a skeleton joint index + 1
    (0: the actor's position; at most 128; distinct). A key needs a cast
    time. Both readers still take `N3RB`–`N3RE`; the server checks the
    bounds only; the client also checks the key and that the clip has only
    triangle records. No engine or wire version changes.
  - The client draws it from the cast start (the kind-2 strike event of a
    profile with a cast time: the local start of its own predicted shot,
    else the event tick), for the archer and every observer that receives
    the event, at each joint, every record turned about the joint by the
    caster's drawn facing (n3e's model forward is KO's +Z), plays the
    clip's `effect:` sound once per joint at the start, and ends it at once
    when the caster's strike fields stop showing that cast (`casting` with
    that strike tick): the landing, a cancel, death or a session change.
    An observer that arrives during a cast does not see it; KO probably
    does the same, an inference not a confirmed fact: of the callers of
    `00479de0` only the own casts `00583f20` and `00583b90` and the casting
    receive `00585a90` trigger a row's self FX (index -1 / -2).
  - The KO cook: `ko_fx` reads a version-1 bundle that ends after 16 slots
    as 16 slots; `ko_fx_bake` keeps an FX shape's file position as an
    offset of every mesh vertex (it still refuses a shape rotation, a scale
    other than 1 and animated keys) and draws a clip marked `self` with a
    bundle velocity (move type -1 never uses it). The glow cook adds the
    class archery row's self FX as a 10 s clip (the bundle life `00478bc0`
    keeps) and its parts as the bow profile's cast-effect joints; it checks
    the profile's attack clip against the crossbow rule above (`0x1c` for a
    type-2 row with a kind-71 item in either hand, else the row's start
    animation; the package has no crossbow, so it stays 26).
- **Server authority:** presentation only; the server's hold, landing and
  cancel rules (D-217) are unchanged, and the client draws from the
  server's events and strike fields.
- **Considered:**
  - A new `effects.bin` binding kind: rejected; bindings select by event
    kind, item key and attack variant, not by combat profile, and play on
    the target.
  - Drawing it from the caster's state alone (so a late observer sees it):
    rejected for now; by the callers of `00479de0` (an inference), KO
    starts it only from the casting event.
  - Particle and billboard records in a cast effect: refused by both the
    cook and the client until their emitter orientation in a turned bundle
    is read.
- **Limits:** the effect sound starts at the actor's position, where KO's
  starts at the bundle's (the joint); the arrow in flight (FX 590, PQ-417)
  is not drawn yet; the shape position's offset (about 3.7 m up and 1.8 m
  aside in the archer's frame) follows the binary reading above and is not
  yet compared on the rig (queued: PQ-429).
- **Corrected 2026-10-26 (PQ-429):** the reading of the shape's position
  above is incomplete. The mesh part's init (`0048ea70`, vtable `006a448c`
  `+0x28`), which ends its load (`0048ebf0`) and its duplicate (`00490540`,
  run by the bundle clone `00478850` for every trigger), sets the shape's
  position (`0041f740` → `0043b650`) to the bundle position (0 in a fresh
  bundle, `00475060`) plus the part's file position ((0, 0, 0) in
  `arrow.fxb`), so the shape file's position never reaches the draw (binary).
  The rig shows the arrow in the drawing hand, pointing along the archer's
  facing, and nothing 3.7 m above (rig, archive client). The cook rule
  "`ko_fx_bake` keeps an FX shape's file position" is therefore wrong; its
  correction is PQ-430 (evidence).
- **Cook corrected 2026-10-26 (PQ-430):** `ko_fx_bake` offsets an FX mesh
  part's shape by the part's own file position (`+0x98`, `0047def0`) instead
  of the shape file's, which it still reads and no longer uses. The offset is
  scaled and turned with the vertices, and the part's current position (the
  same position plus its motion) is added after: 1298's part matrix
  (`0048f440`: `0048f700`, `00490120`) multiplies the shape matrix whose
  translation is that position, and `0048fd40` overwrites only the
  translation row with the turned current position plus the bundle's
  (binary). The flying FX's trigger `0047a2d0` clones into a fresh bundle as
  `00479de0` does, so FX 590 (PQ-417) follows the same rule. n3e scales a
  mesh part in its own frame where 1298 scales along the world axes; they
  differ only for unequal x and z scale, which no cooked asset has (PQ-431)
  (evidence).
- **Cook guarded 2026-10-26 (PQ-431):** "along the world axes" above is
  precisely "along the axes the turn to the bundle direction ends in". A
  self or target FX (move type -1) has a flattened direction (`00477590`,
  `004786ba`), so its turn is about y and the two orders agree for equal x
  and z scale; a clip cannot carry a facing-dependent scale, so
  `ko_fx_bake` refuses a mesh part whose x and z scale or scale velocity
  differ (no cooked or otherwise readable 1298 mesh part is lost to it). The
  flying FX's direction is not flattened (`004770c0`), which PQ-417 must
  turn and which agrees with this cook's scale order only for a uniform
  scale (evidence).
- **Recorded in:** `content/combat-animation.md` (Cast effect (N3RF)),
  `content/presentation-events.md`, CONTRACTS, GAPS ("FX fidelity"),
  FEATURES KOF-0011, PARITY, STATUS, the
  evidence record.

## D-221 — 2026-10-26 An upgraded Azagai grade's attack and durability are its Item_Org value plus its Item_Ext bonus (amends D-219)

- **Context:** PQ-434, queued by PQ-425. D-219 gives every Azagai item of
  the opt-in `--glow-2233` package its 2145 Item_Org damage (column 16, 116)
  as attack and its column 20 (8000) as initial durability, so the four
  upgrade grades hit as hard as the plain bow. PQ-425 located the upgrade's
  bonus fields.
- **KO reference (binary):** both clients' item tooltips draw the attack as
  Item_Org + Item_Ext: 1298 `KnightOnLine.exe` (SHA-256 `828ab0db…a5e5`)
  `004d6320` sums Item_Org `+0x46` and Item_Ext `+0x36` (`004d6c58`–
  `004d6c80`) and the maximum durability Item_Org `+0x4e` + Item_Ext `+0x3e`
  (`004d7309`–`004d733e`); the 2233 image `seg_00401000.bin` (SHA-256
  `53ffa5c2…a0b9`) `005aa8e0` sums Item_Org `+0x5e` and Item_Ext `+0x4e`
  (`005abbed`–`005abbf5`) and Item_Org `+0x66` and Item_Ext `+0x56`
  (`005ac37e`–`005ac386`; re-read by PQ-434). The 1298 game server
  `Ebenezer-official.exe` (SHA-256 `7d83cc28…bcb`) holds no extension table:
  its ITEM loader `0041f077` keys one record per item number and copies
  Damage to record `+0x3a`, which the item sum `0049e11c` and the weapon
  attack `004a0d2a` read for the worn number (`0049e217`, `004a0d91`).
- **KO reference (local-asset / inference):** under PQ-314's row-layout
  inference those offsets are 2145 Item_Org columns 16 and 20 and Item_Ext
  columns 9 and 13 (all shorts). The OpenKO ITEM table's Damage equals
  1298 Item_Org column 16 + Item_Ext column 9 in all 61,278 rows that have
  both rows (Duration equals column 20 + column 13 in all but 693, three base
  items' grades). No 2145-era server or ITEM table is available, so that the
  2145 server's per-number row holds the sum is an inference.
- **Selected:** the glow cook gives each kind-70 Azagai item attack = 2145
  Item_Org column 16 + its Item_Ext row's column 9 and initial durability =
  Item_Org column 20 + Item_Ext column 13, the Item_Ext row being the one
  2233's item rule reaches (`ko_glow_2233.item`, PQ-314). For the package's
  grades: 116 / 8000 for the plain 1110532000 (Item_Ext_33 row 1000: 0, 0),
  182 / 17000 (normal +10), 148 / 14000 (reverse +1), 163 / 15000
  (reverse +10) and 200 / 17000 (reverse +30). The cook refuses an
  Item_Ext column 9 or 13 that is not a short, a negative bonus, and a sum
  outside D-219's bounds (attack 0..10000, durability 1..65535). n3e keeps
  one attack per item in package data, which is the shape of 1298's
  per-number ITEM row; the server is unchanged.
- **Server authority:** unchanged. The attack and durability stay package
  data that the server reads for committed equipment; the client sends only
  intents and draws no attack line.
- **Considered:**
  - Keeping D-219's base Item_Org damage for every grade: rejected; both
    clients show the sum, and the 1298 server's per-number rows carry it.
  - Adding the bonus in the server at run time from an extension table:
    rejected; KO's server reads one per-number row, and n3e's package
    already has one stats row per item.
- **Limits:** the 2145 server's values remain an inference; the grades'
  other non-zero Item_Ext columns (14, 26, 31, 52, 56) are not read; the bow
  still does not wear (D-219); n3e draws no attack or durability tooltip
  line.
- **Recorded in:** D-219 (amended), `content/combat-animation.md` (Skill hit
  (N3RE)), GAPS ("Stats and damage"), FEATURES KOF-0011, PARITY, STATUS, the
  evidence record.

## D-222 — 2026-10-27 A ranged profile with a cast time can carry a flight: an effect clip the client flies from the shooter's joint to the target's box at the landing, turned to its pitched direction, then a hit clip on the target

- **Context:** PQ-417, queued by PQ-347. Since PQ-423 (D-220) the glow bow
  draws 1298's archery self FX (the arrow in the drawing hand) until the
  server lands the shot, then nothing flies: the hit appears on the target
  with no arrow. 1298's archery rows (102003–208003) name flying FX 590
  (`fx/arrow.fxb`, the same arrow mesh, sound 5500) and target FX 550
  (`fx/blow.fxb`, a 0.5 s billboard, sound 5500) at target part 0.
- **KO reference (binary, `KnightOnLine.exe`, SHA-256 `828ab0db…a5e5`):**
  the release (`00584b00`, at `005855bc`) and an observer's flying receive
  (`00585f20`, at `00586677`, for a caster other than the local player) call
  `00587ac0` for a type-2 row. It plays sound `0x157c` (5500) at the
  shooter's position when the shooter's `+0x2cc` hand item has a kind 70–79,
  looks up the row's MAGIC_TYPE2 record and, for HitType (record `+4`) 0,
  triggers the row's flying FX `+0x50` through `0047a2d0`(shooter, part
  `+0x44` % 1000, FX, the target's box centre `00460bd0`, the packet's index,
  move type 0); with no target the decompile passes the shooter's position
  plus (its position plus its facing `0045a200`) (`00587c3d`–`00587c99`,
  `00587dca`–`00587e02`, the call at `00587e3e`; the `0xa28` branch at
  `00587d24` the same); with HitType not 0 it triggers `00479de0` toward the target's part
  `+0x58` with move type HitType instead. It then adds (NumArrow (record
  `+0x14`) − 1) >> 1 pairs of arrows aimed at the target point turned about
  y by ±i × π / 12 around the shooter. `0047a2d0` clones the bundle into a
  fresh one (`00476440`, `004792a0`, `00478850`) and places it (`004770c0`):
  source point the shooter's joint (`0045e160`), target point as given,
  direction their normalised difference with its pitch, and the FX row's
  sound through `00475d20`. The tick `00477590`, move type 0, moves the
  bundle by direction × frame time × its velocity `+0x44` (read from the
  file by `00478bc0`, copied by the clone `00478850`) and never ends it on
  arrival; the mesh part turns from +Z to the direction (`0048f700`). The FX
  manager's tick `0047a8d0` checks a live moving bundle only on the
  shooter's (or the target's) client: the segment of 1.2 frame steps ahead
  against the actor boxes within 16 m (`0045c2c0` → `004488b0`), then the
  terrain and objects; on a hit it puts the bundle at the hit point, stops
  it with `00475e30(0)` (state 1: every part's slot `+0x30`, its fade) and
  sends the effecting (3) and fail (4, -101) packets (`00583540`). The fail
  receive `00586fa0` with -101 stops the flying FX of that index on other
  clients (`0047a710(…, 0)`) and, for every receiver, triggers the row's
  target FX `+0x54` at the target's part `+0x58` (`00479de0`, move type -1,
  index 0), or at the packet's point when the target is not in view.
- **KO reference (local-asset):** `arrow.fxb` velocity 77 m/s, life 10 s;
  the archery rows' MAGIC_TYPE2 (`Skill_Magic_2.tbl`) HitType 0 and
  NumArrow 1; part `+0x44` 12, target part `+0x58` 0; `sound.tbl` 5500 →
  `Snd\arrow_pull_0.wav`.
- **Selected:**
  - `ranged-attack.bin` gains a sixth layout, `N3RG`: `N3RF` with, per
    entry after the cast effect, the flight: u32 key length (0–64) and the
    key (printable ASCII, an effects clip; empty: none), u32 source joint
    (a skeleton joint index + 1, 0: the actor's position; at most 128), f32
    speed (0 without a key, else 1–1000 m/s), u32 hit key length (0–64) and
    the hit clip key (empty: none), u32 hit joint (index + 1 as above), u32
    release key length (0–64) and an audio key (empty: none). Without a
    flight key every other field is 0 or empty; a flight needs a cast time.
    Both readers take `N3RB`–`N3RG`; the server checks the bounds only; the
    client also requires the flight key to be a clip with only triangle
    records and the hit key to be a clip. No engine or wire version
    changes.
  - The client starts the flight at the landing (the kind-6 event of a
    profile with a flight, hit or miss), at the event's time, for the
    archer and every observer that receives the event: from the shooter's
    source joint as drawn, toward the centre of the target's box as last
    drawn (the pick box, KO's actor box), else the target's drawn
    position; the direction keeps its pitch (the shooter's facing when the
    two points meet). Each frame the clip's anchor is the start plus the
    direction × speed × age, and every record turns from the model's
    forward (n3e's -z, KO's +Z) to the direction by the shortest turn
    (about y by π when they are opposite). The flight ends at once where
    the ray from its start first enters the target's current box; when the
    ray no longer meets the box, at the launch distance; then the hit clip
    starts at the target's hit joint (its position without one), with its
    `effect:` sound at the target. At the launch the client plays the
    flight clip's `effect:` sound and the release key at the shooter.
  - The glow cook adds the class archery row's flying FX as a flight clip
    (`ranged-flight-590`, 10 s, the bundle's velocity as the speed), its
    target FX as the hit clip (`ranged-hit-550`, as long as its parts) at
    the row's target part, the shooter part `+0x44` % 1000 as the source
    joint, and, for a bow of kind 70–79, the release key `ranged-release`
    bound to sound 5500. It refuses a row whose MAGIC_TYPE2 HitType is not
    0 (a homing flight) or whose NumArrow is not 1 (a spread).
- **Server authority:** presentation only. The server still resolves the
  shot at the landing tick (D-217) for every client; no client reports a
  hit. 1298's client-reported collision (`0047a8d0` → effecting) is not
  imported.
- **Considered:**
  - Delaying the strike's resolution by the flight time on the server, as
    1298's damage follows the shooter's collision report: not in this
    presentation item; queued (PQ-439), since it changes when damage lands.
  - Collision with every hostile actor, the terrain and objects (1298's
    `0047a8d0`, which on a terrain or object hit reports target -1, so
    `00586fa0` draws the target FX at the hit point, not on the target):
    not in this item; the server has already chosen the target, so only
    its box ends the flight, a ray that misses it ends at the launch
    distance, and the hit clip is drawn on the target either way. Queued
    (PQ-443), since what blocks a shot is a gameplay rule.
  - A homing flight (HitType 1 or 2) and the multi-arrow spread: refused by
    the cook (no row the packages cook uses them); queued (PQ-440).
- **Limits:** the arrow ends at once where 1298 fades it over its part's
  fade-out (0.2 s, `00475e30(0)`) (queued, PQ-441); the strike bindings and
  the melee blow and struck sounds still play at the landing event
  (queued for comparison with 1298's archery hit, PQ-442); the sounds start
  at the actors' positions, not at the bundles'; that 1298's server relays
  the -101 fail to every client in view (so the shooter and observers draw
  FX 550) is an inference, the relay not read; the hit clip is drawn
  unturned (PQ-432).
- **Recorded in:** `content/combat-animation.md` (Flight (N3RG)),
  `content/presentation-events.md`, CONTRACTS, GAPS ("FX fidelity"),
  FEATURES KOF-0011, PARITY, STATUS, the
  evidence record.

## D-223 — 2026-10-27 A held ranged shot with a flight is released at its landing tick and resolves when its arrow arrives: the server's 3-D distance over the profile's flight speed

- **Context:** PQ-439, queued by PQ-417 (D-222). Since PQ-420 (D-217) the
  server resolves a held ranged shot at its landing tick (the stretched
  clip's marker), and since PQ-417 the client launches the arrow at that
  landing event, so the damage lands before the drawn arrow does (0.1 to
  0.55 s for the glow bow's 6 to 42 m at 77 m/s).
- **KO reference (binary):**
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`, D-222): the release
    (`00584b00`) sends the flying phase (2) and flies the row's flying FX
    (`00587ac0` → `0047a2d0`, move type 0, the bundle velocity); the FX
    manager tick `0047a8d0` sends the effecting phase (3) only when that
    bundle collides with an actor box (`0045c2c0`), through `00583540`.
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`), the magic packet
    `004630a6`: the flying phase of a type-2 row runs `0046f3f1` (the arrow,
    D-218), sets the session byte `+0xd` to 3 (`0046378f`) and relays the
    packet; the effecting phase runs the admission and rate check `00464b43`
    (`004637b0`; its archery minimum of 1.2 s between effectings, PQ-416)
    and, for an NPC target (id 10000 or above, `00463b9c`), builds packet
    `0x3a` (phase 3, the magic, the target, the packet's data and a sum of
    three user fields, `00463c0e`) and sends it to the AI server at once (`00464027` →
    `004037e7` → `0041ea0e`). It drops the packet when its source user is
    in state 3 or has no HP, for any row but type 5 (`004635a1`, `004635b4`),
    and an NPC-target type-2 effecting when the type-2 row's arrow count
    (`+0xc`) is 1 and `+0xd` is 1 (`00463bef`). Nothing compares the
    effecting with the flying phase's time or the distance.
  - `AI Server-official.exe` (SHA-256 `8715084f…0435`): the magic handler
    `0040cd1d` acts only on phase 3 (`0040ce44`) and calls the type-2 leaf
    `0040d471` (`0040ce88`), which rolls (`00443a34`) and applies the damage
    (`004204b4`, `0040d546`) at once, after the NPC liveness checks; there is
    no timer.
  - So 1298's NPC loses HP when the AI server handles the effecting packet
    the shooter's client sends at the arrow's collision: the release plus
    the flight time (the distance over the bundle velocity) plus the network
    delay. The bow tick (`004659b0`, PQ-145, PQ-416) casts once an interval
    whether or not an arrow is still in flight (binary, by absence; read at
    PQ-439 attempt 2): its archery branch (`004660b1`–`00466102`) tests the
    target's state 4/5 and the interval and calls `005819e0`, whose
    refusals for the archery row are its own state 4, 5 or 6, a recorded
    cast `+0xb04` (`00582821`), the timed lock `+0xaf4` (`0058282e`), the
    row's entry in the recast list `+0x78` (`00581c55`–`00581c80`) and the
    item check `0057f7f0` (`005829e2`). The release `00584b00` clears
    `+0xb04` (`00584b40`) and enters the row in the recast list
    (`00584c08`) before it flies the arrow (`005855bc` -> `00587ac0`),
    which writes none of the three; `+0xaf4` is set only by `0046b090`
    (`0046b094`, from `0058a8c0`), and the cast start `00583f20` records a
    row with a cast time without a further test.
- **Selected:**
  - The server's ranged policy keeps the N3RG flight speed (0 without a
    flight). A held shot (D-217) under a profile with a flight is released
    at its landing tick, with D-217's cancel rules, no durable write and no
    roll: the archer's `strike_result` becomes `released` (its cast effect
    ends, the clip plays on) and the server publishes a release event
    (kind 7: actor, target, style, request sequence, both positions). The
    flight lasts ceiling(3-D distance between the archer's and the target's
    positions at the release / speed × 20) ticks, at most 200 (10 s, the
    flight clip's bound), and the shot resolves through D-217's landing at
    the release tick plus that (D-218's one-tick lead applies to it): the
    roll, wear, arrow, damage, ledger, AI, death, the kind-6 event and the
    archer's `ActionResult`.
  - In flight the shot is cancelled, with no effect and no cost, when the
    archer's session or life changes, it dies (as `004635a1` drops a dead
    source's effecting), the committed equipment selects another profile,
    or the target is gone or dead. A movement no longer cancels it.
  - The archer's next shot may be accepted while its arrow flies (the held
    cast and the flight are separate); a release that finds the archer's
    previous flight still pending waits for it, at most `DEFER` past its
    landing tick. An arrival while a newer cast is held leaves the archer's
    strike fields and interval to that cast; its kind-6 event carries its
    own request sequence and style. Skills and rest stay refused while a
    flight is pending, as while a shot is held (1298 does not refuse them;
    queued, PQ-447; allowed in flight since D-227).
  - (Review round 1.) A held cast writes nothing at its acceptance, so the
    archer's own pending arrival write (a cast's wear commit and the target
    it reserves) does not refuse the next held cast; that cast's landing
    waits for the write (D-217's busy rule), so that write does not delay
    the next shot past the profile's interval. A released cast
    refused at its arrival (`no_ammo`, `equipment_changed`, `stale_target`)
    keeps its `released` strike fields, as a cancel in flight does.
  - The client launches the flight at the release event (no longer at the
    kind-6 event, which still plays the blow and struck sounds and the
    strike bindings). Its auto-attack takes its own shot's `released` strike
    fields as the end of its wait for the result, so the next shot goes out
    once the interval has run; a ranged shot refused as `combat_pending` or
    `target_pending` (the arrival's durable write) is retried without
    spending an interval.
  - A profile with a cast time and no flight still resolves at its landing
    tick (D-217).
- **Server authority:** the server decides the flight time from its own
  positions and the package's speed and resolves the hit on its own clock;
  no client reports a collision (LOOP.md "Kept different", D-222). 1298's
  client-reported effecting is not imported.
- **Considered:**
  - Keeping the shot held in one slot until the arrival, the client waiting
    for its result: rejected; each shot would delay the next by its flight
    (up to 11 ticks at 42 m for the glow bow) where 1298's bow tick casts
    once an interval.
  - Writing the wear and the arrow at the release (1298 spends the arrow at
    the flying phase, `0046f3f1`) and applying the damage at the arrival:
    rejected here; the roll would come a flight early, the durable bag write
    would tell the client the outcome (wear needs damage) before the arrow
    lands, and the ledger and target checks would have to repeat. The
    arrow is spent at the arrival; queued (PQ-444).
  - The distance to the target's box rather than its position: the server
    has no box; the difference is the box's half depth over the speed
    (under a tick for the glow bow).
- **Limits:** the flight is measured between the two positions (the feet),
  not from the shooter's joint to the box (the client's arrow ends where
  its ray enters the box, up to a tick before the server's arrival); the
  tick quantization and the arrival's durable write add up to a tick or
  more; a target that moves during the flight is still hit (PQ-443); the
  client launches the arrow from a snapshot (about 0.05 s late), so a short
  flight may end before it is drawn (PQ-445); a shot cancelled in flight
  spends no arrow where 1298 spent it at the release (PQ-444); skills and
  rest are refused while an arrow flies, up to 0.55 s for the glow bow and
  up to 200 ticks for a slow package flight (PQ-447; lifted by D-227); a kill now lands
  after the interval has run (2-3 ticks for the glow bow at 6-12 m), so a
  shooter that keeps the same target is either refused `target_dead` until
  it sees the death and retargets (31-32 ticks between accepted shots in
  the glow suite instead of 29) or has its next cast accepted at the
  interval and cancelled `target_dead` before its release, its interval
  spent (the next released shot about 58 ticks after the previous); what
  1298 does with such a cast was not read, and that its shooter also learns
  of the kill only from the effecting reply is an inference (PQ-448).
- **Amends:** D-217 (a profile with a flight resolves at the arrival, not
  the landing tick; a movement after the release does not cancel it) and
  D-222 (the flight launches at the release event).
- **Recorded in:** `content/combat-animation.md` (Flight (N3RG)),
  `content/presentation-events.md`, CONTRACTS, GAPS ("FX fidelity"),
  FEATURES KOF-0011, PARITY, STATUS, the
  evidence record.

## D-224 — 2026-10-28 A ranged shot with a flight and ammunition spends it at the release, in a durable write of its own; the arrival commits only the wear

- **Context:** PQ-444, queued by PQ-439 (D-223). Since D-223 the server
  removes the arrow in the arrival's durable commit, with the wear and the
  damage, so a shot cancelled in flight spends none, and with one arrow left
  a shot released while the previous arrow flies is checked against a bag
  that still holds that arrow and is refused (`no_ammo`) only at its
  arrival, after its arrow was drawn.
- **KO reference (binary):**
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`), the magic packet
    `004630a6`: the flying phase (2) of a type-2 row calls `0046f3f1`
    (`00463770`–`00463777`: the magic id and the source id, `EBX`). For a
    source id 0–1499 (a user) `0046f3f1` removes the type-2 row's arrow
    count (`+0xc`) of the main row's exhaust item (`+0x14`) from bag 1
    through `004b0792`, which takes the first inventory slot holding it,
    writes the user's record at once and sends the bag update (`0x3d`); a
    result below 2 returns 4. (Before the arrow it returns 0 for a user
    whose `+0x8138` is 2 and, for a row with a flying FX, 0 when
    `0046dbe2` fails, 4 when the main row's `+0x26` is set and
    `004c2291`(`+0x26`, 2) fails, and 4 when the user's `+0x68`, likely its
    mana, is below the row's `+0xc`, otherwise subtracting it, `004a083f`;
    the callees' meaning is not read, and none is in this decision. A 0
    drops the packet with no relay, `00463781`.) A 4
    relays the packet with phase 4 to the region (`00463787` →
    `LAB_0046434c`, `0041e2d8`) and leaves `+0xd` as it was; a 2 sets
    `+0xd` to 3 (`0046378f`) and relays phase 2. Nothing there reads the
    target, the flight or the later effecting: the arrow is spent at the
    flying phase whatever the arrow then does.
  - The effecting phase drops an NPC-target type-2 effecting only when the
    row's arrow count is 1 and `+0xd` is 1 (`00463bef`); `+0xd` is set to 1
    only after a type-2 effecting at a user target (`00464328`; the NPC path
    returns at `00464042`–`00464053` after sending `0x3a`). So a failed
    flying phase does not by itself stop a later NPC-target effecting.
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`): the fail receive
    `00586fa0` acts on the packet's fourth data short (-101, -104, -103,
    -100: texts `0xbc7`, `0xfa4`, `0xfa2`); what a relayed phase 4 of the
    shooter's own flying phase carries there, and so what its client draws
    or sends next, was not read.
- **Selected:**
  - Under a ranged profile with a flight (D-222) that names ammunition
    (D-218), the release (D-223) spends it. At the release tick, once the
    archer's previous arrow has landed and no durable combat write of the
    archer's own (an arrival's wear, an incoming hit's wear) is pending, the
    server checks the first bag slot holding the item in its bag (fewer than
    `ammo_count`: `no_ammo` at once, no write) and starts a durable write of
    its own: D-218's strike event with no wear records (mode 1, damage 0, no
    roll) that removes `ammo_count` from that slot. The release (the kind-7
    event, the `released` strike fields, the flight measured from the
    positions then) follows that write's commit, in the same tick when the
    database answers within it: the write starts in the tick's simulation
    pass and its result is applied in that tick's command phase, so no lead
    tick is needed.
  - Committed: the arrow is gone and the shot flies. A shot cancelled after
    that (the target dead or gone, the archer dead, its session or its
    profile changed) has spent its arrow, as 1298's did at the flying phase.
    If the target is already dead or gone, or the archer dead or on another
    profile, when the write commits, the shot fails with that status at once
    (its strike fields marked `released`, as a cancel in flight leaves them;
    no kind-7 event), its arrow spent.
  - Not committed (the locked durable bag held too few): the shot fails
    `no_ammo` at the release, as 1298's flying phase fails with phase 4: no
    kind-7 event, no flight, no roll or damage, the cast cleared from the
    strike fields, the interval spent (it ran from the cast start), the
    durable bag state sent.
  - A write error is handled as every combat write's: the session fails
    and the realm's health is invalidated; the shot is dropped.
  - While the write is pending the shot is neither released nor cancelled;
    a movement admitted then no longer cancels it (as D-218's lead window).
    The release waits for the archer's own pending durable write, at most
    `DEFER` past its landing tick (`combat_pending`, no arrow spent); a
    pending write on the target does not hold it.
  - The arrival no longer checks or removes the ammunition and has no lead
    tick: it makes a durable commit only when the hit wears equipment. An
    unworn hit is published at the arrival tick, a worn one a tick after
    it, as every strike's wear is (D-217).
  - A profile without a flight keeps D-218: its ammunition goes in the
    strike's commit, which its landing starts a tick early.
  - The client is unchanged: its arrow count drops with the release's bag
    update, so with one arrow left its next shot is not sent (the ammo
    notice), and the server refuses one sent anyway at the acceptance.
- **Server authority:** the server decides the release on its own clock and
  reads its own bag; no client reports the flying phase or names the
  arrows. 1298's NPC-target effecting is not tied to a successful flying
  phase (above); n3e lands no hit for a shot whose arrow write did not
  commit (D-218's authority rule; LOOP.md "Kept different").
- **Considered:**
  - Releasing at once and writing the arrow in the background, cancelling
    the flight when the write fails: rejected; observers would draw an
    arrow for a shot that spent none, and nothing is published before its
    durable commit.
  - D-218's lead tick for the release: rejected; the write starts in the
    simulation pass, so a lead would release a tick early.
  - Keeping the arrival's lead tick: rejected; an unworn hit would land a
    tick before the arrival.
  - Moving the wear and the roll to the release too: D-223 rejected it.
- **Limits:** a database slower than a tick delays the release and its event
  past the landing tick (at most `DEFER`, then `combat_pending`); a worn
  hit comes a tick after the arrival tick; the flying phase's other
  refusals and its `+0x68` cost (likely mana) are not modelled (PQ-450); what 1298's shooter's
  client does with a relayed phase 4 was not read.
- **Amends:** D-218 (under a profile with a flight the ammunition is removed
  by the release's write, not the strike's commit, and the landing's lead
  tick applies only without a flight) and D-223 (a release that spends
  ammunition makes a durable write and waits for the archer's own pending
  write; a shot cancelled in flight has spent its arrow).
- **Recorded in:** `content/combat-animation.md` (Ammunition (N3RD), Flight
  (N3RG)), CONTRACTS, GAPS ("Magic types"), FEATURES KOF-0011, PARITY,
  BINARY-INDEX, STATUS, the
  evidence record.

## D-225 — 2026-10-28 The ranged release adds none of the archery flying phase's other checks; archery skills take their MP and reuse window at the release

- **Context:** PQ-450, queued by PQ-444 (D-224), whose Limits left
  Ebenezer's other refusals and cost before the arrow (`0046f3f1`) unread.
- **KO reference (binary, `Ebenezer-official.exe` SHA-256 `7d83cc28…7bcb`):**
  for a user source `0046f3f1` drops the flying phase of a sitting user
  (posture `+0x8138` 2, `004a8ad1`); for a row with a FlyingEffect it drops
  one within the row's reuse window (`0046dbe2`: (CastTime + ReCastTime) /
  10 whole seconds, refused while less than the window less 0.1 s has
  passed, the refusal restarting it); it fails (phase 4) a row whose Event
  quest is not at state 2 (`004c2291`) and a user whose MP (`+0x68`) is
  below the row's Msp, else takes the Msp (`004a083f`); after the arrow it
  takes the master-skill stone a BeforeAction 1–4 names (379059000–
  379062000). The MAGIC record offsets are the load's (`0041f4ca`,
  `004702f4`).
- **Rows (local-asset, the operator's OpenKO export; the 1298 client table
  agrees on Msp):** the six class archery rows (class × 1000 + 3) have Msp
  0, Event 0, BeforeAction 0, CastTime 13, ReCastTime 0 (a 0.9 s window). No
  type-2 row has an Event or a BeforeAction; the archery skills have Msp
  10–300 and windows of 1, 4 or 5 s.
- **Selected:** n3e's ranged basic attack keeps its release unchanged. Its
  archer is standing at every release (an attack's acceptance ends rest and
  rest is refused while a shot is held or flying; since D-227 only while it
  is held, which still covers every release), the bow's interval the
  server enforces from the cast start (1.45 s) is longer than the 0.9 s
  window, and the rows carry no Event, cost or stone. When archery skills
  arrive (PQ-067), their Msp is taken and their reuse window checked at the
  release, with the arrow, not at the cast start, and a shortfall fails the
  shot at the release as a missing arrow does (D-224).
- **Server authority:** unchanged; every check n3e makes is on the server's
  own clock and state.
- **Considered:** modelling the 0.9 s window for the basic attack: rejected;
  it never binds behind the server's interval, and a release held by the
  server's own write latency (D-224) is no player-timed phase.
- **Limits:** the rows are the OpenKO release's, not binary-matched; that
  quest state 2 means completed, which client field selects a stone, the
  client's own archery reuse timing, and where a master skill's stone is
  spent were not read.
- **Amends:** D-224's Limits (the flying phase's other checks are settled,
  none needed for the basic attack).
- **Recorded in:** GAPS ("Magic types"), FEATURES KOF-0011, PARITY,
  BINARY-INDEX, `docs/ko/domains/combat-skills.md`,
  `content/combat-animation.md`, STATUS, PQ-067's note, the
  evidence record.

## D-226 — 2026-10-28 The archer's own client launches its arrow at its predicted release and reconciles it with the server's release event

- **Context:** PQ-445, queued by PQ-439 (D-223). Since D-223 every client,
  the archer's included, launches the flight at the server's release event
  (kind 7), which reaches the archer about a snapshot (0.05 s) and a round
  trip after its own clip passed the marker, so at the glow bow's 77 m/s a
  flight under about 4 m ended before any frame drew it and only the target
  FX showed (PQ-417's limit).
- **KO reference (binary, `KnightOnLine.exe` 1298, SHA-256
  `828ab0db…a5e5`):** the cast tick `00585830` (called from the skill tick
  `005845d0` at `005846f0`) calls the release `00584b00` (`005858cf`) when
  `004689f0` (`005858c2`) sees the local player's own clip pass its first
  marker; nothing there waits for the server. The release sends the flying
  phase through the socket send `00451b80` (`00584f46`, which does not wait
  for a reply, PQ-403), stops the self FX (`0047a710` at `00584f6f`,
  `00584f84`) and flies the arrow at once (`005855bc` → `00587ac0` →
  `0047a2d0`). An observer's flying receive `00585f20` flies it only for a
  caster other than the local player (`00585fd6` compares with the player's
  id `+0x474`), so the shooter flies its arrow once, at its own release.
  The fail receive `00586fa0` stops a flying FX (`0047a710`(…, 0) at
  `00587634`, `00587652`) only on the -101 code (`00587579`) and only for a
  caster other than the local player (`0058758e` skips it for the player's
  own).
- **Selected:** presentation only. The archer's client predicts the release
  of its own held shot under a profile with a flight: its local start (when
  it sent the shot, as the drawn clip starts) plus the stretched attack
  clip's entry blend and first marker (the server's `landing_ticks` before
  it rounds up). On the first frame at or after that time, as 1298's
  per-frame cast tick releases, it launches the flight as D-222 does (from
  its joint toward the target's box as drawn then), starting it at that
  frame so that the frame draws it at its start, plays the flight and release
  sounds at itself and ends its cast effect, as 1298's release does. The
  flight is pending until the server's release event for the shot's request
  sequence: that event then confirms it and launches no second flight. A
  pending flight that reaches the target's box holds its hit clip until the
  event, which then starts it; a shot the server does not release (a refusal
  such as D-224's `no_ammo` at the release or `combat_pending`, a cancel, a
  death, a skill cast, a session change) ends the predicted flight where it
  is and drops its held hit and sounds; a hit or miss result confirms a
  flight whose release event was not seen. A release event that finds no
  pending flight (the target was not drawn at the prediction, or the
  prediction was cancelled first) launches the flight as before. Observers
  keep launching at the release event, as 1298's observers wait for the
  flying packet. The kind-6 landing, the damage, the arrow count and every
  server rule stay as D-223 and D-224 set them.
- **Server authority:** unchanged. The client predicts only a drawn arrow
  and its sounds; it sends nothing more, and the server still decides the
  release and the hit on its own clock. 1298's shooter sends the flying
  phase at its own release and the server relays a failed one as phase 4
  with the packet's own data (D-224); the release packet's fourth data
  short is the flying FX index (`00584b00`, from `00589fb0` at
  `00584b8e`/`00584bd8`), not one of the fail codes `00586fa0` stops a
  flight on, so 1298's shooter likely keeps its arrow in the air for a
  refused flying phase (inference: the relayed bytes were not observed) and,
  its effecting not tied to the flying phase (D-224), may still land the
  hit. n3e lands no hit for a shot whose arrow write did not commit (D-224,
  LOOP.md "Kept different"), so its predicted arrow ends there instead of
  drawing a hit the server will not apply.
- **Considered:**
  - Launching at the snapshot that shows the `released` strike fields: no
    earlier than the event and still a round trip late.
  - Starting the hit clip at the arrow's arrival whether or not the release
    was confirmed: rejected; a refused shot would draw a hit the server
    never applies.
  - Not ending a predicted arrow whose shot is refused (1298's likely
    shooter behaviour, above): rejected, as above.
- **Limits:** the prediction runs on the client's clock from its send, so
  the drawn arrow leaves up to a round trip and a tick's rounding before the
  server's release and arrives that much before the server's arrival (the
  hit clip, the kind-6 landing's sounds and the damage come later); a walk
  admitted between the predicted and the server's release cancels the shot
  on the server (D-217), so the predicted arrow ends where 1298's would
  have flown; an observer's short flight may still end before it is drawn,
  as an observer's in 1298 waits for the relayed packet; an own flight that
  starts inside the target's box ends at once, undrawn; 1298's handling of
  a relayed phase 4 for the shooter's own flying phase is an inference.
  (Review round 1.) A release event for a request whose prediction its hit
  or miss result already confirmed launches nothing, and the client
  reconciles after the frame's release events, so a release event and its
  result in one frame do not draw a second arrow.
- **Amends:** D-222 and D-223 (the archer's own client launches its flight
  at its predicted release, confirmed by the release event; observers still
  launch at the event).
- **Recorded in:** `content/combat-animation.md` (Flight (N3RG)),
  `content/presentation-events.md`, CONTRACTS, GAPS ("FX fidelity"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-227 — 2026-10-28 A skill or rest may start while the archer's arrow flies; a skill's impact waits for the caster's own arrival write or reward, and a hit no longer interrupts a cast at its impact

- **Context:** PQ-447, queued by PQ-439 (D-223). Since D-223 the server
  refused skills (`Player::skill_busy`) and rest (`Command::Rest`) while a
  released ranged shot was in flight, up to 0.55 s for the glow bow and up
  to 200 ticks for a slow package flight, where 1298's cast ends at the
  release.
- **KO reference (binary):**
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`): the skill start
    `005819e0` (from the bow tick and the skill bar callers `004dfb10`,
    `004e0940`) refuses a dead player (`+0x2fc` 4 or 5) and, for a
    non-basic row, the cast action state 6 (`00582814`), a recorded cast
    `+0xb04` (`00582821`) and the timed lock `+0xaf4` (`0058282e`); the sit
    command `005d91f0` refuses the same three through `0057e9a0` (with the
    dead states, the same posture, its 3 s sit cooldown and a moving player)
    and stops the auto-attack. The release `00584b00` clears `+0xb04`
    (`00584b40`); the animation tick `00457d90` requests the next action
    state (`+0x304`) when the clip ends (`00457e57`–`00457e62`), so state 6
    lasts until the cast clip ends (that the next state is the basic one is
    source-only). Nothing there reads an arrow in flight. The FX manager tick
    `0047a8d0` drops a flying bundle only when its caster, not the local
    player, is gone or in state 5 (`0047a9f7`–`0047aa1e`); the local
    player's bundle flies on and sends the effecting phase at its collision
    (`00583540` at `0047bac4`) whatever the player's posture or action.
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`): the posture packet
    `0x29` type 1 (`004a8ad1`) refuses a dead user (HP, state 3:
    `004a8b32`) and sitting from posture 4 or 5 (`004a8b78`), and tests no
    magic. The magic packet `004630a6` drops a sitting user's (posture 2)
    casting phase (phase 1) of a magic id below 400000
    (`0046346a`–`0046347d`) and any phase of posture 4 (`00463483`); the
    effecting phase tests the source user's state 3 and HP (`004635a1`,
    `004635b4`) and its admission `00464b43` the target user's state, not the
    source's posture. It writes no posture. So an arrow released before the
    archer sat lands, and the archer stays seated.
  - `KnightOnLine.exe` 1298 (attempt 2): the received attack `005cec10`
    rolls the cast interruption (`_rand() % 100` at `005ceda7` against the
    row's `+0x88` survival field at `005cedc8`, 100 under the actor flag
    `+0x470`) only when `0057e9a0` reports a cast and the recorded cast
    `+0xb04` (read at `005ced75`) names a skill row (`0046d7e0` at
    `005ced88`, the two misses at `005ced96` and `005ceda1`). The release
    sets `+0xb04` to -1 (`00584b40`), so a hit after the release rolls no
    interruption.
- **Selected:**
  - A released shot's flight no longer refuses a skill or rest; a held shot
    (cast, before the release) still refuses both, as 1298's cast does until
    its release. The archer's own durable combat write (an arrival's wear, an
    incoming hit's) still refuses both for its duration, as for every strike.
  - An arrival during a skill's cast or under a seated archer is checked
    and lands as before; it neither cancels the cast nor ends rest. Rest's
    recovery skips a tick while that write is pending, as before. The
    arrival keeps its own refusals, so a skill impact that comes before it
    can refuse it after its arrow was spent at the release: under a package
    whose basic attack costs resource, an impact that leaves the archer
    below that cost (`insufficient_resource`), and under a package without
    progression, a skill kill's pending reward (`reward_pending`); see
    Limits (PQ-454; closed by D-228: the release pays the cost and a
    pending reward holds the arrival).
  - A skill's impact waits, until its cast deadline, while the caster's own
    strike's wear write (during a cast only an arrow's arrival, as a new
    strike is refused while casting) or its reward is pending
    (`Player::impact_waits`): an arrow may now arrive between the recast
    commit and the impact, and the impact must not take its cost before the
    arrival's commit applies the basic attack's cost (checked at the
    arrival) nor start a second reward while one is pending. An incoming
    hit's pending write does not hold the impact (attempt 2): it changes only
    the caster's health, and before this item no impact waited for it. This
    covers an impact that comes after the arrival's write started; one that
    comes before the arrival is the case above. An arrival waits for a skill
    impact pending on its target (D-217's busy rule, a tick); neither waits
    on the other otherwise, so the two cannot hold each other.
  - A hit that commits on the caster while its cast is at the impact stage
    (stage 2: the cast time ended and the recast commit started) is counted
    but rolls no interruption (attempt 2), as 1298 rolls it only on the
    recorded cast that its release clears (`005cec10`, `00584b40`). Without
    this, a hit that committed while the impact waited (a miss or an
    unarmoured hit, which writes no wear, or any hit during a reward's wait)
    could cancel the cast `interrupted` after its recast was committed: the
    cooldown spent and no effect. A hit before the impact stage (stages 0
    and 1) still rolls, and its cancel spends no recast; stage 1 can last
    past the cast's end while the transition waits for a pending combat
    write (an incoming hit's, or the archer's arrival write), so such a
    hit after the cast's end still interrupts (Limits).
  - The client is unchanged. The server accepts a skill only after the
    release, and the client confirms a predicted flight on the release event
    before it reconciles, so a cast first seen with or after that event
    does not end the confirmed flight (D-226's rule ends only an unconfirmed
    one).
- **Server authority:** unchanged; every check is on the server's state.
  1298's client-reported effecting is not imported; the arrival stays the
  server's.
- **Considered:**
  - Refusing until the cast clip ends, as 1298's action state 6 does on the
    client: not in this item. It is the clip's tail after the marker (about
    0.18 s for the glow bow), a client input gate that exists with or
    without a flight; queued (PQ-451).
  - Holding the impact for every pending combat write of the caster,
    including an incoming hit's (attempt 1): rejected in review; it delayed
    impacts under NPC fire for no reason of this item, and a hit committing
    during that wait could interrupt a cast whose recast was committed.
  - Ignoring movement at the impact stage too: not in this item. A move
    then still cancels the cast with its recast committed and recovered
    (D-099's drain, tested by `skill_runtime::test_cancelled_commit`
    "move"); queued (PQ-455).
  - Letting an impact that comes after the arrival's write started proceed
    regardless: rejected; it would take its cost before the arrival's commit
    applied the basic attack's cost the arrival had checked (an underflow),
    or replace a pending reward. An impact that comes before the arrival
    still takes effect first, and the arrival then applies its own checks
    (Limits).
  - Taking the basic attack's cost at the release or holding a released
    arrival on a pending reward: not in this item; queued (PQ-454).
- **Limits:** a skill impact that comes before a released arrow's arrival
  can still refuse it after its arrow was spent at the release: under a
  package whose basic attack costs resource (`r.cost`, checked by
  `gameplay::landing` and taken at the arrival), an impact that leaves the
  archer below it (`insufficient_resource`), and under a package without
  progression, a skill kill's pending legacy reward (`reward_pending`);
  Ebenezer's effecting phase checks neither (`004630a6`). Neither shipped
  package reaches it (the demo's cost is 0; the demo and Moradon declare
  progression); queued (PQ-454), closed by D-228. n3e accepts a skill or rest from the release, where 1298's
  client refuses both until the cast clip ends (PQ-451); n3e's skill begin
  stands a seated caster, where Ebenezer drops a seated user's casting phase
  (PQ-452); the impact's wait is bounded by the cast deadline (5 s past the
  cast), past which the cast times out with its recast committed, as a cast
  that never ends does; a move while the impact waits cancels the cast with
  its recast committed, as a move during the recast commit already did
  (D-099), a window the wait lengthens by the arrival's write or a reward (a
  tick, longer with a slow database), where 1298's cast ends at the release
  (PQ-455, closed by D-231); a hit that commits after the cast's end while the stage-1 to
  impact-stage transition waits for a pending combat write (its own, or the
  archer's arrival write; a miss or an unarmoured hit commits at once) still
  interrupts the cast, at no recast cost, where 1298 rolls only before the
  release (PQ-455, closed by D-231); the archer's own combat write still
  refuses a skill or rest for a tick (longer only with a slow database)
  where 1298 refuses neither.
- **Amends:** D-223 (skills and rest are no longer refused in flight),
  D-225's reasoning (the archer is standing at every release because an
  attack's acceptance ends rest and rest is refused while a shot is held;
  rest during the flight comes after the release), and the skill runtime's
  incoming-hit interruption (`005cec10`, the ko-effects-skills audit): a hit
  no longer interrupts a cast at its impact stage, in every package.
- **Recorded in:** `content/combat-animation.md` (Flight (N3RG)), CONTRACTS,
  GAPS ("Magic types"), FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-228 — 2026-10-28 A shot with a flight pays the basic attack's cost at its release; a pending reward holds a landing instead of refusing it

- **Context:** PQ-454, queued by PQ-447's review (D-227 Limits). Since D-227
  a skill may start while a released arrow flies, and an impact that comes
  before the arrival could refuse the arrival after its arrow was spent at
  the release (D-224): `gameplay::landing` refused `insufficient_resource`
  when the impact left the archer below the package's basic attack cost
  (`cost`, taken by `finish_attack` at the arrival), and `reward_pending`
  while a skill kill's legacy reward job (a package without progression)
  was pending.
- **KO reference (binary, `Ebenezer-official.exe` SHA-256 `7d83cc28…7bcb`):**
  - The flying phase `0046f3f1`, for a user source and a row with a
    FlyingEffect (`+4` above 0, `0046f44e`), after the posture, reuse and
    quest checks (D-225), returns 4 when the user's MP (`+0x8098` →
    `+0x68`) is below the row's Msp (`+0xc`) (`0046f48a`–`0046f49b`) and
    otherwise takes it, `004a083f`(−Msp) (`0046f4a3`), before the arrow
    (`004b0792` at `0046f4b9`). An arrow result below 2 returns 4
    (`0046f4c0` → `0046f509`) with no call that gives the MP back.
  - `004a083f` adds its argument to `+0x68`, clamps it to 0 and to the
    maximum (`+0x8128`) and sends the user the MP update (`0x18`).
  - The effecting phase (phase 3 of `004630a6`) runs the admission
    `00464b43` (`004637b0`); for phase 3 (`00465462`) and a user whose `+0x8098` →
    `+0x71` is set (`0046547a`), a type-2 row (`+0x1b`, `0046548a`) with a
    FlyingEffect (`0046548f`) returns at `004654a1` (setting `+0xc` to 1)
    before either MP comparison (`004654b6`, `004654c5`); the effecting
    phase calls the reuse check `0046dbe2` only for a row not of type 2
    (`004637d9`–`004637e4`). So
    an archery effecting is neither refused for MP nor charged it: the cost
    belongs to the flying phase. (`+0x71`'s meaning was not read.)
  - Ebenezer has no asynchronous reward: nothing in these paths waits for
    one. n3e's reward hold below is its own durable write ordering, not a KO
    rule (n3e-internal).
- **Selected:**
  - Under a ranged profile with a flight (D-222), the basic attack's cost
    is checked and taken at the release, not at the arrival. At the release
    tick, once the release's holds pass (the previous arrow landed; when it
    spends ammunition, no durable write of the archer's own pending,
    D-224), an archer below the cost fails `insufficient_resource` at once:
    no write, no release, no arrow spent, its cast cleared, its interval
    spent (as `no_ammo` there). Otherwise the cost is taken, then the
    ammunition is checked and its write started (D-224); a `no_ammo` there,
    at once or when the durable bag held too few, keeps the cost, as
    `0046f3f1` keeps the MP. The arrival neither checks nor takes it
    (`CommittedHit::paid`, `finish_attack`'s `paid`).
  - Every held shot's landing (a released arrow's arrival, or a held shot
    without a flight) waits while the archer's reward is pending, as it
    waits for a pending combat write (D-217's busy rule, at most `DEFER`
    past its tick, then `combat_pending`), instead of refusing
    `reward_pending`. The reward job is one database write; the landing
    applies after it, so it neither replaces it nor is refused for it.
  - A profile without a flight, and an unheld strike, keep their cost
    checked at the acceptance (and at a held landing) and taken when the
    strike lands.
  - D-227's impact wait (`Player::impact_waits`) is unchanged; its reason
    is now only the reward (the arrival no longer takes a cost the impact
    could overtake).
- **Server authority:** unchanged; the server decides the release, the cost
  and the hold from its own state and clock. 1298's client-reported
  effecting is not imported.
- **Considered:**
  - Checking the cost at the release and taking it at the arrival
    (saturating): rejected; an impact during the flight could still leave
    the arrival unpaid, giving a free hit or a refusal after the arrow.
  - Refunding the cost when the arrow write does not commit: rejected;
    `0046f3f1` keeps the MP, and a refund would race regeneration's clamp.
  - Holding only a released arrival on a reward: one busy rule for every
    landing is simpler; a held shot without a flight met a reward only when
    a previous arrival's kill started one after its acceptance, and was
    refused for it.
  - Settling the reward synchronously: rejected; no durable write runs in
    the tick (CONTRACTS).
- **Limits:** a reward write slower than `DEFER` (1 s) still drops the
  landing `combat_pending`, its arrow spent; a shot refused `no_ammo` at its
  release now costs the basic attack's cost; no shipped package charges one
  (the demo's cost is 0, and the demo and Moradon declare progression, so
  neither path is reachable there; `ranged_attack_live` charges 2 to check
  the release); `+0x71` in `00464b43` was not read.
- **Amends:** D-217 (a pending reward holds a landing as a pending write
  does), D-224 (the release also takes the basic attack's cost, before the
  arrow), D-227 (its Limits' PQ-454 case is closed; the impact wait's cost
  reason is gone).
- **Recorded in:** `content/combat-animation.md` (Flight (N3RG)), CONTRACTS,
  GAPS ("Magic types"), FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-229 — 2026-10-28 Live suites' Compose stacks share a fixed pool of test networks, one suite per network at a time; `docker run` containers stay on docker0

Every Compose suite under `make live` and `make live-ko` gave its project its own
`<project>_default` bridge, created with an IPv4 address at `up` and removed at
`down`. On origin/main's code a full `make live` created and removed 9 such
bridges (18 bridge IPv4 address events, 36 including IPv6 link-local) beside
358 veth devices, and a browser on the
host aborted requests with ERR_NETWORK_CHANGED while the suites ran (PQ-457,
asked in chat).

- **Selected:** a fixed pool of Docker bridge networks, `n3e-test-net-0`, `-1`,
  ... (label `n3e.test-network=1`), created the first time a number is needed
  and kept. `tests/live.py` (and so `make live-ko`, which uses its runner) claims
  one for each suite it starts with `tests/isolation.py` `claim_network`: the
  lowest number whose host-wide flock (`/tmp/n3e-test-networks/<name>.lock`) no
  process holds and whose last suite has no process left. The runner starts each
  suite as the leader of its own session and records that session in the lock
  file (`TestNetwork.hold`); a claim skips a network while any process of the
  recorded session runs (`/proc/*/stat`), so a suite that outlives its runner
  (the runner SIGKILLed, or an interrupted runner exiting while a teardown still
  runs) keeps its network with every process it started. The suite gets `N3E_TEST_NETWORK`
  and `N3E_TEST_NETWORK_EXTERNAL=true`, and `tests/compose-disposable.yaml`
  (part of `DISPOSABLE_COMPOSE`) makes that network the project's external
  default network, so `up` creates and `down` removes no bridge. The claim
  removes any container an earlier holder left on the network (running or not)
  and the volumes of its Compose project, saving each container's `docker logs`
  first under `build/live/swept/<time>-<network>/`; after the suite the runner
  sweeps again, saving the logs with the suite's container logs (kept when it
  fails, PQ-128), and fails a suite that left containers. Without the variables (a suite
  run by hand) the project gets `<project>_default`, as before. After the
  change the same full run created 0 bridges and 0 bridge IPv4 addresses.
- **Isolation:** the stacks reach their services by the bare names `postgres`
  and `redis` (`compose.yaml`), and Docker's DNS on a shared network answers a
  name with every container that has it (two containers aliased `postgres` on
  one test network resolved to both addresses). So a network holds one suite
  at a time, by the lock and the recorded session, which also keep `make live`
  in another worktree or beside `make live-ko` off it, and no suite runs two Compose stacks at once
  (checked: each Compose suite and `tests/ko_stack.py` starts one project, and
  `play_replay_live`'s `replay()` is called once per suite). The disposable
  clusters, their fsync-off options (D-155) and per-suite volumes are
  unchanged.
- **`docker run` containers stay on docker0:** the plain helpers (the `*_db`
  suites, the native-server suites, `tools/demo_session.py`'s sessions) publish
  ports to the host and use no service names, Docker never creates or removes
  docker0, and a container gets a veth on any bridge, so moving them would
  change no count.
- **Not reduced:** a veth pair per container (179 attachments, 358 NetworkManager
  veth devices per full run, both before and after) and the IPv6 link-local
  address the kernel gives each host-side veth (about 136 added and 179 removed
  per run). Cutting those needs fewer containers per suite or a host setting,
  not a network layout; PQ-458 asks whether the remainder still disturbs the
  browser.
- **Considered:** one shared network for every stack (rejected: the bare
  service names would cross-talk); long-lived Postgres and Redis (rejected:
  suites stop, restart and stall Postgres, and PQ-205's per-suite fsync-off
  clusters stay); one network per numbered slot of a run (two runners on the
  host would share slot 0); containers sharing one network namespace per slot
  (`--network container:`: no veths, but fixed published ports, no `--add-host`
  and a leftover stack holding the slot's ports); macvlan or ipvlan (no
  published ports to the host).
- **Considered for the orphan case:** passing the lock's descriptor to the suite
  (`pass_fds`): a wrapper suite's own children (`tests/ko_stack.py`'s suite,
  `ko_presentation_live`'s `tests/gameplay.py`) would not inherit it, since
  Python's `subprocess` closes descriptors it is not told to pass; the session
  covers every process the suite starts (no suite or tool starts a session of
  its own).
- **Limits:** the lock lives in `/tmp`, so runners that do not share `/tmp`
  (another user, a service with a private `/tmp`) could claim the same network;
  a recorded session id reused by an unrelated session leader keeps that
  network out of the pool while the unrelated session lives (the pool takes the
  next number);
  a container someone attaches to a test network by hand is removed by the next
  claim; the pool keeps one /16 of Docker's default address pool per network
  ever used at once (four under the default `--jobs=4`).
- **Recorded in:** `tests/isolation.py`, `tests/live.py`,
  `tests/compose-disposable.yaml`, `tests/isolation_check.py`, LOOP ("Gates"),
  the parity agent definitions and skill, GAPS, STATUS, the
  evidence record.

## D-230 — 2026-10-29 The veth link-local churn left after D-229 still aborts browser requests; the route to remove it, at a cost in container containment or a host change, is the user's choice (PQ-460)

D-229 removed the per-run bridges but left a veth pair per container. The kernel
announces an IPv6 link-local address on each host-side veth once duplicate
address detection completes (about 1.6 s after the link comes up), and removes it
when the container stops. PQ-458 read Chromium's Linux
network-change path and measured it with a headless Chromium instance.

- **What the browser reacts to (source-read):** every announced address added or
  removed on any interface. The Linux notifier ignores no interface and no
  link-local address. Each change flushes the socket pools with
  `ERR_NETWORK_CHANGED`, aborts DNS jobs and closes HTTP/2 sessions (Linux
  closes rather than drains them). Link events count only through a
  connection-type change, and veths cause none.
- **Measured:** a full `make live` (68/68) gave 139 announced veth link-locals
  and 139 removals, 277 Chromium address-change notifications (median gap
  0.67 s) and 433 of 2220 probe requests failed `ERR_NETWORK_CHANGED`. The 36
  one-shot containers (`migrate`, `convert-progression`) end before DAD, so
  their addresses are never announced and the browser does not see them.
  Containers on `--network host` or `--network none` produced no netlink event.
- **Route (a), no veth for test containers (not accepted; the user
  decides).** The `make live` and `make live-ko` test containers would run in
  the host network namespace, each service bound to `127.0.0.1` on a port from
  `free_ports`. With no veth the
  browser sees no address change: the `--network host` control produced no
  netlink event, so 0 notifications is inferred, not measured over a run. Each
  suite keeps its own disposable Postgres and Redis. `compose.yaml`'s
  deployment defaults stay as they are. The approach has these consequences
  on the host:
  - **NET_RAW in the host namespace.** Docker's default capability set includes
    `CAP_NET_RAW` (`CapEff` `a80425fb`, bit 13, checked on the reference host;
    `--cap-drop NET_RAW` gives `a80405fb`). In the host namespace a test
    container (Postgres, Redis, the server) could open raw or packet sockets on
    the host's real interfaces (Ethernet, Wi-Fi, any VPN).
  - **Reach to every host loopback service,** including any other local
    stacks. Bridged containers cannot reach them.
  - **No Docker DNS names.** `postgres` and `redis` no longer resolve. Every
    address becomes `127.0.0.1:port`. D-229's isolation was one stack per test
    network, so that the bare names stay unambiguous; host networking replaces
    it with distinct ports, which is a different isolation model, not the same
    one.
  - **Host port space.** Services choose their ports in the host's port space,
    and a leftover container from a killed run holds its host ports until it is
    swept.
  - **All-interfaces defaults.** These were checked in the pinned images:
    Postgres's sample config sets `listen_addresses = '*'`, and Redis runs with
    `bind * -::*` and `protected-mode no`. The server's `N3E_LISTEN` is
    `0.0.0.0:7777` in `compose.yaml`. Unless overridden, all three would listen
    on the LAN.

  The mitigations PQ-460 must apply and check, if the user chooses this route:
  - Drop capabilities on every test container: `--cap-drop NET_RAW` at least,
    or `cap_drop: [ALL]` with only the minimum added back.
  - Bind every service to `127.0.0.1` explicitly, with a check that fails the
    run if any test container listens on a non-loopback address.
  - Allocate ports only from the slot's `free_ports` range.
  - Sweep leftovers by label, now that a test network no longer identifies
    them.
  - Repeat this item's browser probe over a full run.
- **The choice is the user's.** The trade-off lowers how well containers are
  contained on the developer's own machine. It is the same kind of machine-level call
  as the host setting below, so PQ-460 is parked on the user with the options:
  - host networking with the mitigations above (0 notifications, inferred);
  - sharing one network namespace per suite (`--network container:` /
    `network_mode: service:postgres`), which keeps one veth per stack, no
    containment change, and roughly half the notifications or fewer (inferred);
  - a host setting (`net.ipv6.conf.default.addr_gen_mode=1` or
    `disable_ipv6=1`). It needs no repository change and stops the kernel
    link-local on every interface created afterwards, including the host-side
    veths of any other Docker stacks. Its zero is inferred: it was
    demonstrated on a veth in a private namespace, not on the container
    side. NetworkManager adds its own link-local on the devices it manages
    (the Ethernet device: kernel `addrgenmode none`, `fe80::` present, observed);
  - doing nothing.
- **Rejected:** folding the one-shot containers, because they are already
  invisible to the browser.
- **Chromium side:** the Linux factory passes an empty interface ignore set,
  and no command-line switch that fills it was found (not searched
  exhaustively). No browser-side mitigation is known.
- **Recorded in:** GAPS, STATUS, the
  evidence record.

## D-231 — 2026-10-29 A skill cast ends at its release: after it, neither a move nor a hit cancels the cast, and its range is measured from where it was released

- **Context:** PQ-455, queued by PQ-447 (D-227 Limits). Since D-227 a hit no
  longer interrupted a cast at its impact stage (stage 2), but a move then
  still cancelled it `interrupted` with its recast committed and recovered
  (D-099's drain, tested by `skill_runtime::test_cancelled_commit` "move"),
  a window D-227's impact wait lengthens by the arrival's write or a reward;
  and the stage-1 tail after the cast time (`c.end`), while the transition to
  stage 2 waits for a pending combat write, still cancelled on a move and
  rolled a hit.
- **KO reference (binary):**
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`): the cast tick
    `00585830` (from `005845d0` at `005846f0`) acts only while the recorded
    cast `+0xb04` is set (`00585838`). When the clip passes its first marker
    (`004689f0`) it calls the release `00584b00` (`005858cf`); otherwise, when
    the action state `+0x2fc` is not 6 (`005858e0`) or the player moves
    (`+0x308` not 0, the move state in the source's names, `005858e9`), it
    clears `+0xb04` (`005858f3`) and the cast time
    `+0xb0c` and sends phase 4 with -100 (`00583540` at `00585944`). The
    release clears both (`00584b40`, `00584b50`) and sends phase 3 (effecting)
    at once for a row without a flying FX (`+0x50` 0, `00584b68`), else
    phase 2, through `00451b80` at `00584f46` (a row whose `+0x8c` or `+0x90`
    is 1 sends a separate 20-byte packet instead, `00584c34`–`00584c47`,
    `005857f0`). So a move cancels a cast only
    before its release; after it the tick returns at once, a non-flying
    effecting has already gone out (inference: from where the cast stood),
    and the FX tick
    `0047a8d0` sends a flying one at its collision with no test of the local
    caster's motion (PQ-447). The received attack `005cec10` rolls only on
    the same record (D-227).
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`): the magic packet
    `004630a6` keeps no casting record a move could clear (its own stores:
    `+0x8098` -> `+0x1099`, `+0x8a1c`, the session byte `+0xd`, `+0x8a74`,
    `+0x8a78`; the move handler `00494beb` itself stores to none of them).
    The move handler builds no phase-4 (fail) magic packet, nor do its
    callees read one level deep (evidence record). Its one magic-opcode
    packet is in a branch it shares with the magic packet: when the user's
    `+0x89a0` is 1
    (`00495012`) it clears that slot (`004c102d`(1) at `0049501f`), sets
    state 7 to 0 through `004cbdd3` -> `004a8ad1` (`00495029`), sends packet
    `0x70` (`004c10a0` at `0049504a`) and sends the user `0x31` [5, `0x5b`]
    (`0044557a` at `00495081`); the magic packet's effecting does the same,
    for a user source (id below 10000) and a row whose Type1 is below 4,
    when its connection's user's `+0x89a0` is set (`004637f4`–`0046388f`),
    and then goes on (`004638a6`), so that branch ends a state (its meaning
    not read), not the cast. The move handler does
    write the user's position, `+0x8098` -> `+0x40`/`+0x44`/`+0x48`: the
    previous packet's position, kept at `+0x812c`/`+0x8130`/`+0x8134`, when
    the packet's fourth short is not 0 (`004950a9`, `004950b8`, `004950c7`),
    the packet's own when it is 0 (`004950f6`, `00495108`, `0049511a`).
    `004c1dbe` reads that position when the magic packet calls it
    (`004635c8`), so a move handled before the effecting can move the point
    its range is measured from (see the inference below). So (inference from
    binary) the server cancels no cast on movement; 1298's client does,
    before the release.
  - `Ebenezer-official.exe` (review round 1): the magic packet checks the
    range on every phase it handles, the effecting included: for a user
    source and a row whose Type1 is below 4 (`004635bf`), after the source's
    state 3 and HP tests (`004635a1`, `004635b4`), it calls `004c1dbe`(source,
    target, magic) at `004635c8` and fails the packet (`0046e707`, phase 4
    with -103) when it returns 0. `004c1dbe` takes both ids' current server
    positions on the x/z plane (user `+0x8098` `+0x40`/`+0x44`, NPC
    `+0x10`/`+0x18`); for a magic id below 1 or above 99999 (an id of 0 is
    tested first, `004c1ef0`) it reads the main row (`0046f95e`, at
    `004c1f56`), and for a row whose Moral (`+6`) is 7 or at most 4
    (`004c1f63`–`004c1f71`, otherwise it passes) it passes the same id
    (`004c1f73`) and, for Type1 3 (`004c1f79`–`004c1f88`), passes while
    dx² + dz² is below (Range `+0x1e` + 15)² (`004c1f91`, `004c1fa0`, `pow`
    `00501179` at `004c1fb1`, `004c1fbf`). The type-3 executor `00466da0`
    (dispatched at `0046414a`, `0046426e`) has no distance test for a single
    target: its only distance callee, `0046cbf3` (`00466f06`), is in the
    area branch (target -1). The caster's server position when the
    effecting is handled is the one the move packets handled before it left
    (above; other writers of that position, such as the warp-back
    `0049b712`, were not surveyed). Since 1298 fails a cast on any move
    before its release and sends a non-flying effecting at the release, that
    position is inferred
    to be where the caster stood to cast, its release position (inference
    from binary: whether a move packet can be handled between the release
    and the effecting, the order of one connection's packets, and which move
    packet a standing 1298 client last sent were not read), measured to the
    target's position when the packet arrives.
- **Selected:**
  - A cast is released in the runtime tick in which its cast time has ended
    (`tick >= c.end` at stage 1) and it still stands (`Cast::released`),
    whether or not the stage-2 transition must wait for a pending combat
    write. Until then a move cancels it `interrupted` and a hit rolls its
    interruption, as before.
  - After the release a move does not cancel the cast, and a hit is counted
    but not rolled. The range is still checked until the impact, measured
    from the cast's origin (where it was released: a move before the release
    cancels it) to the target's current position, and a cast on the caster
    itself is in range, as Ebenezer's effecting check `004c1dbe` measures
    from the caster's current server position, inferred to be its release
    position (evidence record), and passes the same id (n3e's skills are all
    non-flying, type 3). So a caster's own move after the release cannot fail
    the cast; a target that leaves the range before the impact fails it
    `out_of_range`, with its recast committed and recovered once the recast
    commit started, as Ebenezer's effecting fails it. Everything else is
    still checked until the impact (session, life, death, the target's death
    or category, the cost, the weapon, the cast deadline), and the recast
    commit and the impact wait (D-227) are unchanged.
  - This replaces D-227's stage rule for hits: the release, not stage 2,
    ends the roll, so the stage-1 tail rolls no hit either.
  - D-099's drain test changes its "move" case: a move while the recast
    commit waits on PostgreSQL no longer cancels the cast; the cast lands
    once the commit returns (healed, its cost taken, its cooldown live). The
    drain stays tested by the "leave" and "death" cases.
- **Server authority:** unchanged; the release is the server's tick, the
  release position the server's own (`Cast::origin`), and the range is the
  server's check. No client report is trusted.
- **Considered:**
  - Not checking the range after the release (attempt 1, round 1):
    rejected in review; Ebenezer's effecting checks it (`004c1dbe` at
    `004635c8`).
  - Measuring from the caster's current position after the release:
    rejected; Ebenezer's caster position at the effecting is inferred to be
    the release position (above), and a caster's own move after the release
    would then fail a cast 1298 is inferred to land.
  - Releasing at the stage-2 transition: rejected; that transition can wait
    on a pending combat write for which 1298 has no counterpart.
  - Clearing the cast's presentation fields at the release: not in this
    item (presentation; see Limits).
- **Limits:** a caster that moves between the release and the impact (a
  tick, longer only with a slow database) keeps its cast pose while it moves
  until the impact clears the cast, where 1298's release has already
  cleared the cast record (what its walk shows after the release was not
  read). A target that leaves the range in n3e's window between the release
  and the impact (a tick, longer only with a slow database) fails the cast
  after its recast was committed; 1298's window is inferred to be the
  effecting packet's trip to the server. n3e's range test keeps its own form
  (the package's range, 3-D, no tolerance) where `004c1dbe` passes a type-3
  row below Range + 15 on the x/z plane (PQ-465). Death after the release still cancels the cast
  (`actor_dead`) with its recast committed, as Ebenezer's effecting phase
  tests the source's HP (`004635b4`) when it arrives.
- **Amends:** D-099's tested "move" case and D-227's stage-2 interruption
  rule (and its two PQ-455 Limits).
- **Recorded in:** `content/skills.md`, `content/combat-animation.md`,
  CONTRACTS, GAPS ("Magic types"), FEATURES KOF-0011, PARITY, BINARY-INDEX,
  STATUS, the evidence record.

## D-232 — 2026-10-29 A skill's range is 1298's client limit at its acceptance and Ebenezer's Range + 15 on the ground plane from its release to its impact, both package data

- **Context:** PQ-465, queued by PQ-455's review (D-231 Limits). n3e's
  server checked a skill's range as the 3-D distance against the package's
  range (Moradon 25, the client table's column 28), with no tolerance, at
  its acceptance and on every tick until the impact (after D-231, from the
  release position once released). The n3e client does not check a skill's
  range before sending it.
- **KO reference (binary):**
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`): the magic packet
    `004630a6`, for a user source (id below 1500) and a row whose Type1
    (`+0x1b`) is below 4 (`004635bf`), calls `004c1dbe`(source, target,
    magic id) at `004635c8` on every phase it reaches and on 0 fails the
    packet with phase 4, -103 (`0046e707`) (PQ-455). `004c1dbe` returns 1
    for a target id below 0 (`004c1ddf`). It reads two coordinates of each
    side (user `+0x8098` -> `+0x40`, `+0x44`; NPC `+0x10`, `+0x18`; the
    user's `+0x48` and the NPC's `+0x14` are not read) and sums the squares
    of their differences with `pow`(…, 2.0) (`00501179`, the double 2.0 at
    `00633578`), keeping the sum as a float (`004c1eed`), which the row
    tests below reload (`004c1f8e`, `004c2030`, `004c2041`). For a magic id
    above 99999 (or below 1) it reads the MAGIC row (`00402e37` at
    `004c1f56`); a row whose Moral (`+6`) is above 4 and not 7 passes
    (`004c1f63`–`004c1f71`), the same source and target id passes
    (`004c1f73`), and by Type1 (`004c1f79`–`004c1f88`): Type1 1 passes
    while the sum is below 15.0² (the double 15.0 at `00634b88`, `004c2041`–
    `004c2068`); Type1 2 passes while it is at most (`+0x3e` / 10, integer
    division)² + 1000.0 (the float at `00634b84`) of the item record that
    `00403ab2` returns for the number at the source's `+0x8098` -> `+0x150`,
    else `+0x120` (`004c1fcd`–`004c203d`; which slots those are was not
    read; `004664ea` compares the same item field as a range, PQ-416); Type1 3
    passes while it is below
    (Range `+0x1e` + 15)² (`004c1f91`, `004c1fa0`, `pow` at `004c1fb1`,
    `JBE` at `004c1fbf`); any other Type1 fails. Range, Moral and Type1 are
    the MAGIC load's fields (`0041f4ca`, PQ-450). An id of 0 tests the sum
    against 15.0² as well (`004c1ef0`–`004c1f16`), and an id from 1 to
    99999 against the id itself squared (`004c1f1b`–`004c1f45`).
  - The two coordinates are x and z, the ground plane (source-aided: the
    user record's `m_curx`, `m_curz`, `m_cury` and the NPC's `m_fCurX`,
    `m_fCurY`, `m_fCurZ` in `ref/ko-src`, the skipped one being the
    height).
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`): the skill start
    `005819e0` passes the range check `00583780` the caster's radius plus
    1.0 plus, with a target, the target's radius (`0045a1d0` on each,
    `00582b02`–`00582b26`; the float 1.0 at `006a3a64`; `0045a1d0` returns
    a size times a scale, the radius by its source name) for the target
    types that check it, among them `005819e0`'s cases 2 and 7 (the
    Moradon rows' types: local-asset, column 14 of the local
    `Skill_Magic_Main` table, 2 for 204001 and 7 for 204002, as
    `tools/assetc/ko_skills.py` asserts; that column 14 is the switched
    `+0x5c` is source-aided). `00583780` measures the 3-D distance from
    the player (`+0x98`/`+0x9c`/`+0xa0`) to the target and, for a row whose
    range (`+0x94`) is above 0, passes while it is at most range + that sum
    + 1.0; otherwise (after the Type1 1 and 2 weapon branches) it posts text
    `0xfa9` and casts nothing. The cast tick `00585830` and the release
    `00584b00` do not call it (PQ-420). That `+0x94` is the table's column
    28 (the range, 25 for both Moradon rows) is source-aided (the
    `__TABLE_UPC_SKILL` order, `+0x8c`/`+0x90` being the two table types
    `00583780` itself tests).
  - So (inference from binary): an unmodified 1298 client starts a type-3
    cast only within range + both radii + 2.0 in 3-D, and Ebenezer then
    lets it land while the target stays within Range + 15 on the ground
    plane at the effecting, which 1298 sends at the release (D-231); between
    the casting packet and the effecting neither checks the range (the
    release `00584b00` and the cast tick `00585830` do not call `00583780`;
    `004c1dbe`'s other callers pass a fixed distance or are the Type1 8
    check, evidence record).
  - Local asset (the OpenKO MAGIC export, not binary-matched): both Moradon
    rows have Range 25, Type1 3, Moral 2 (204001 Tiny Healing) and 7
    (204002 Light Strike), so both are range-checked; their server limit is
    40 m on the ground plane, their 1298 client start limit 29 m in 3-D with
    n3e's 1 m radii.
- **Selected:**
  - The skill policy (`skills.bin`, now N3K2) carries a package-level reach:
    `start` (a margin added at the acceptance), `hold` (a margin added from
    the release to the impact) and `plane` (`3d` or `xz`, the hold's
    measure). Moradon's are 2.0, 15.0 and `xz`: 1298's two 1.0 terms and
    Ebenezer's Type1 3 tolerance on the ground plane. The engine has no KO
    constant.
  - At the acceptance the server checks the 3-D distance against the
    skill's range + both actors' radii (the package's melee radii, as the
    ranged attack's limit does, D-216; 0 without melee rules) + `start`
    (inclusive), and the hold below. From the release to the impact it
    checks the hold: the distance on the hold's plane (from the cast's
    origin, D-231) below the range + `hold` (exclusive, as `JBE` fails at
    equality). Between the acceptance and the release the range is not
    checked; the session, life, death, target, cost, weapon and deadline
    checks stay every tick. A cast on the caster passes both.
  - Moradon: a cast starts within 29 m (3-D) and lands while the target
    stays within 40 m on the ground (was: 25 m in 3-D at every tick).
- **Server authority (kept different):** Ebenezer's own check would admit a
  cast up to Range + 15 on the ground plane; a cast beyond 1298's client
  limit comes only from a modified client. n3e's server enforces the
  client's start limit itself, so an unmodified client's start limit is
  matched, measured on the server's positions with the package's radii
  (near the 29 m bound it can refuse a cast that 1298, measuring its own
  positions and model radii, would send), and the client is trusted for
  nothing; the refusal's 1298 text `0xfa9` is PQ-466 (recorded with the
  standing deviations, PQ-098).
- **Considered:**
  - Ebenezer's check alone at every phase: rejected; it would start casts
    up to 40 m, which 1298's client refuses with text `0xfa9`, an 11 m
    start-range gain for a client that skips its own check.
  - Keeping the per-tick range check before the release: rejected; neither
    binary is inferred to check it between the casting packet and the
    effecting (above), so a
    target that steps out and back before the release would fail a cast
    1298 lands.
  - Folding the radii into the package's `start`: rejected; the ranged
    attack already sums the package's melee radii at run time (D-216), and
    a package that changed its radii would silently diverge.
  - Engine constants for 15 and 2.0, or a fixed plane: rejected; they are
    KO's rules and belong in package data.
- **Limits:** Type1 1 (15 m on the ground plane, weapon skills) and other
  Morals have no n3e skill to apply to. Type1 2, the archery row, passes
  `004c1dbe` at most (item `+0x3e` / 10)² + 1000 on the ground plane (about
  51 m if `+0x3e` holds the bow's 400, 40 m), on the phases the magic packet
  reaches (its archery phases not traced here), where n3e's ranged attack
  checks 1298's client limit at its acceptance only (D-216, D-217): PQ-467. The n3e client still does not check a skill's range
  before sending it, nor post 1298's text `0xfa9` on the server's
  `out_of_range`: PQ-466. 1298 measures between its own client positions;
  n3e between the server's. A package with no margins now refuses a target
  at exactly its range at the impact (the hold is exclusive), where it was
  inclusive.
- **Amends:** D-231 (the range form after the release and the per-tick check
  before it).
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-233 — 2026-10-29 A ranged profile can carry a hold: the target must stay within it at the shot's acceptance, release and arrival, as Ebenezer checks an archery row on every phase

- **Context:** PQ-467, queued by PQ-465 (D-232 Limits). Since D-216 and
  D-217 n3e's server checked a ranged shot's range once, at its acceptance,
  against 1298's client limit (both radii + the profile's range in 3-D; the
  glow bow's 44 m with n3e's 1 m radii), and not again at its release or its
  arrow's arrival (`gameplay::landing`).
- **KO reference (binary, `Ebenezer-official.exe`, SHA-256 `7d83cc28…7bcb`):**
  - The magic packet `004630a6` returns early for phases 6 and 8; otherwise,
    for a user source (id 0–1499), after returning for one whose `+0x8138`
    is 3 or whose `+0x8098` -> `+0x66` is below 1 (neither test for a Type1 5
    row), and for a row whose Type1 (`+0x1b`) is below 4, it calls `004c1dbe`(source, target, magic id) at `004635c8` and
    on 0 fails the packet through `0046e707` (`004635d1`–`004635d3`). That
    call comes before the phase dispatch: the flying phase (2) of a Type1 2
    row calls `0046f3f1` only after it (`00463770`–`00463777`; `0046f3f1`
    reads no position itself, its callees not read), and the effecting phase (3) reaches
    `00464b43` and its executors after it too. So the casting, flying and
    effecting phases of an archery row are each range-checked.
  - `004c1dbe` reads the MAGIC row for a magic id below 1 or above 99999 (an
    id of 0 is tested first); a row whose Moral (`+6`) is above 4 and not 7
    passes at once (`004c1f63`–`004c1f71`), so a Moral 7 row goes on to the
    Type1 test. Type1 2 (`004c1f85` -> `004c1fcd`): with no source user, or
    no item record, it returns 0; it reads the item number at the source's
    `+0x8098` -> `+0x150`, or `+0x120` when that is 0, looks it up through
    `00403ab2` (-> `0040bf13`, the table at `+0x8748` + `0x135c`) and passes
    while the float sum of the squared coordinate differences
    (`pow`(…, 2.0), the double at `00633578`) is at most (the record's
    `+0x3e` / 10, integer `IDIV`)² + 1000.0 (the float at `00634b84`,
    `0x447a0000`; `FADD` at `004c202a`, `JA` at `004c203d`: equality
    passes).
  - The item move `004a1aa4` addresses an equipment slot's item number at
    (slot × 3 + 0x12) × 8 = `+0x90` + slot × `0x18` of the same record
    (`LEA [r + r*2 + 0x12]`, `SHL 3` at `004a1bf9`, `004a1c25`; an equip
    takes a slot below 14), so `+0x120` is slot 6 and `+0x150` slot 8. The ITEM loader `0041f077` copies the
    recordset field at `EBP-0xac` to record `+0x3e`, eight bytes past the
    one it copies to `+0x3a`; the recordset binds `[Damage]` at `+0x120`
    (PQ-425) and `[Range]` (string `006629b0`, at `0044734c`) at `+0x128`,
    eight bytes past it (`0044729b`), so `+0x3e` is the ITEM table's Range
    (binary offsets; matching the two eight-byte steps is an inference).
  - Source-aided names: slot 6 is the right hand and slot 8 the left hand
    (`RIGHTHAND`, `LEFTHAND` in `ref/ko-src`); the coordinates are x and z
    (D-232). 1298's client sends the flying phase at the release and the
    effecting when its arrow's FX reaches the target's box, and does not
    check the range after the cast starts (`00584b00`, `0047a8d0`,
    `00585830`; D-217, D-223, D-231: binary, read there).
  - Local asset (the OpenKO MAGIC export, not binary-matched): the class
    archery rows 102003, 107003, 108003, 202003, 207003 and 208003 have
    Moral 7, Type1 2 and Range 0. In the OpenKO ITEM export the rows of kind
    70, 71 and 80 have Range 400 (2373 rows), 350 (937) or 0 (1); for the 15 such rows
    of the 1298 client's Item_Org whose number is an ITEM row, its column 17
    (0-based; the column the glow cook reads as the client's `+0x4a`) equals
    the ITEM Range. The glow Azagai's 2145 Item_Org range is 400.
  - So (inference from binary and local asset): Ebenezer lets an archery
    shot's casting, flying and effecting phases through while the target is
    within √((range / 10)² + 1000) of the archer on the ground plane, about
    51 m for a 400 bow, measured from the archer's server position when each
    packet is handled; at the effecting that is wherever the archer has
    walked since the release, as far as the move packets handled before it
    reach (the packet order was not read). A failed flying phase spends
    neither the Msp nor the arrow (`0046f3f1` is not reached); a failed
    effecting deals nothing.
- **Selected:**
  - `ranged-attack.bin` gains `N3RH`: `N3RG` with, per entry after the
    flight, f32 hold distance (0: none, else 0.5–200 m) and u32 plane (0
    3-D, 1 the ground plane; 0 without a hold). Manifest: an optional
    `"hold": {"distance", "plane"}` per entry. Both readers take all seven
    layouts and bound it; only the server uses it.
  - With a hold the server requires the target within it (inclusive, from
    the archer's current position) at the acceptance (besides the start
    limit, D-216), at the release of a shot with a flight (after the waits
    for the previous arrow and the archer's own write, before the cost:
    `out_of_range`, nothing spent, the cast cleared, the interval begun) and
    at the landing, which is the arrival for a shot with a flight and the
    release and impact at once without one (`out_of_range`, no hit; its
    arrow and cost stay spent). Between the acceptance and the release the
    range is not checked, as no phase reaches Ebenezer then.
  - The glow cook gives the bow `hold` √((range column // 10)² + 1000) on
    the ground plane: √2600 ≈ 50.99 m for its 400. The engine has no KO
    constant.
- **Server authority:** unchanged; positions, the hold and every check are
  the server's. The hold is Ebenezer's own per-phase check, so nothing is
  kept different here; the start limit stays 1298's client check enforced
  by the server (D-216), and the AI server's missing range check for an NPC
  target is still not imported.
- **Considered:**
  - Measuring the hold at the arrival from the release position, as D-231
    does for a skill: rejected; a skill's effecting leaves at its release
    (D-231), an arrow's at its arrival, so Ebenezer's archer position then is
    wherever the archer has walked, which n3e's current position is.
  - Checking the hold every tick of the flight: rejected; Ebenezer checks it
    only when a phase packet arrives.
  - Storing KO's form (an item range and the 1000 term) in the engine:
    rejected; the package carries the resulting distance and plane.
  - The skill policy's reach (D-232) for the bow: rejected; the archery
    bound is not the range plus a margin, and the shot is a combat profile,
    not a package skill (D-216).
- **Limits:** with the glow numbers the hold (51 m on the ground plane) lies
  outside the start limit (44 m in 3-D), so a glow shot fails it only when
  the archer or the target has moved apart after the acceptance (n3e's
  NPCs do not move during a shot here; the archer may walk after the
  release). Ebenezer's own item lookup (left hand, else right hand) has no
  n3e counterpart: the package gives each profile one hold, and the cook
  refuses bows of different ranges (D-216). What 1298's client shows for a
  failed flying or effecting phase (-103) was not read; n3e's client keeps
  attacking on `out_of_range` and a released arrow's own drawn flight is
  unaffected.
- **Amends:** D-217 (the range is checked again at the landing, by the
  hold) and D-216 (the acceptance also checks the hold).
- **Recorded in:** `content/combat-animation.md` (Hold (N3RH)), CONTRACTS,
  GAPS ("Magic types"), FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-234 — 2026-10-29 The client tests a skill's start limit before it sends the cast and, beyond it, posts the package's too-far notice and sends nothing; the server still checks the limit

- **Context:** PQ-466, queued by PQ-465 (D-232 Limits). Since D-232 n3e's
  server refuses a skill whose target lies beyond the start limit (the
  range + both actors' radii + the reach's `start`, 3-D) with
  `out_of_range`, and the n3e client sent every skill and showed no line for
  that refusal. 1298's client checks the same limit itself before it casts.
- **KO reference (binary, `KnightOnLine.exe` 1298, SHA-256
  `828ab0db…a5e5`):**
  - The skill start `005819e0` calls the range check `00583780` for the
    target types that check it and starts the cast through `00583f20` only
    when it returns non-zero; on 0 it jumps past that call (`00582bc1` /
    `00582bc8`, `00582c89` / `00582c90` → `005834c6`) (PQ-465 read the
    radii it passes).
  - `00583780`, after its range and weapon branches fail (D-232; a row
    whose `+0x38` is 113 passes at once, and the row id `0x7a513` after the
    range test), loads text
    `0xfa9` through `00615080` (`00583a6a`) from the table at `008186e8`
    (`Data\Texts`, PQ-361), formats it into an 80-byte buffer with
    `0067429f` (`00583a94`; it runs the formatter `00678dc8` with no length
    limit, a `sprintf` by its shape: inference) with one argument, the row's
    string at `+0x18` (the empty string `006a3560` when it is null), and passes
    the result with the colour `0xffffff00` to `005d7250` on the object at
    `+0x18` of `00583780`'s `this` (`00583afa`–`00583b0b`); `005d7250` calls
    `0052acd0`, the message output window's append (D-209, D-210), when its
    `+0x48` is set. It returns 0.
  - Source-aided: the `+0x18` string is the skill's name and the `+0x18`
    object the main game procedure (`__TABLE_UPC_SKILL`, `CMagicSkillMng`,
    `MsgOutput` in `ref/ko-src`).
  - Local asset: the player's 1298 `Texts_us.tbl` text 4009 is "Skill
    Failed - Too far", with no format field, so the name is not shown (as
    PQ-416 read for the bow).
  - So (inference from binary and local asset): an unmodified 1298 client
    never sends a skill beyond its start limit; it shows "Skill Failed - Too
    far" in yellow in the message window instead.
- **Selected:**
  - The skill policy gains an optional `notice` (N3K3: N3K2 with a string
    after the reach, 1–96 printable ASCII bytes, at most one `%s`, no other
    `%`; N3K2 stays valid with no notice). Both readers bound it; the server
    keeps nothing of it. `tools/assetc/ko_skills.py` cooks Moradon's from
    the player's text 4009; the engine has no KO text.
  - Before it sends a skill on another actor in its view, the client tests
    the 3-D distance from its own position to that actor against the
    server's start limit (the skill's range + the package's melee radii, 0
    without melee rules, + the reach's `start`; inclusive). Beyond it the
    client sends nothing and posts the notice, its `%s` replaced by the
    skill's label, on the HUD's notice line (the KO HUD draws client notices
    in 1298's `0xffffff00`, D-210). A cast on itself, or on an actor not in
    its view, is sent as before.
- **Server authority:** unchanged. The client test is a hint drawn from the
  same package data; the server checks the start limit on its own positions
  (D-232) and refuses `out_of_range` whatever the client decided. A client
  that skips the test gains nothing, and the client trusts nothing the
  server did not send.
- **Considered:**
  - Posting the notice on the server's `out_of_range` only: rejected; 1298
    sends nothing beyond its limit, and a refusal round trip costs a packet
    and a server check for every press. What 1298 shows for the
    server's own refusal (-103) was not read, so n3e posts nothing there
    (unchanged; queued as PQ-468).
  - Reusing the ranged attack's notice (N3RB): rejected; a package may have
    skills without a ranged profile, and the skill line takes a label.
  - Refusing a `%` in the notice (as N3RB does): rejected; 1298 formats the
    text with the row's `+0x18` string (the name, source-aided), so a package
    text that names the skill should work.
- **Limits:** 1298 measures between its own client positions and the radii
  of the models; n3e's client between its predicted position and the
  target's last projected position with the package's melee radii, as its
  server does. Their gap grows with the player's speed × (one-way latency
  + a tick), so near the limit the client can refuse a cast the server
  would accept, mostly while the player moves away from the target; the
  server's answer stands and the player can press again. A package with
  N3K2 (no notice) refuses beyond the limit silently: no packet, no line. 1298's special passes (the `+0x38` 113
  rows, row `0x7a513`) and its Type1 1/2 weapon ranges have no n3e skill
  to apply to. The level test still comes before the range test (`Requires
  level`); 1298's order of its other skill-start tests was not compared.
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-235 — 2026-10-29 The client posts the skill policy's failed line, in the policy's colour, when the server refuses a skill it sent `out_of_range`

- **Context:** PQ-469, queued by PQ-468. Since D-232 n3e's server refuses a
  skill whose target is beyond the start limit at the acceptance, or beyond
  the hold between the release and the impact, with `out_of_range`; it ends
  the cast (the cast fields cleared, the cast-end event 5) and the caster's
  client showed only the raw status in its combat record. D-234's client
  hint stops most such casts before they are sent, but the server's own
  refusal still happens when the two positions differ, at the hold, or from
  a client that skips the hint.
- **KO reference (binary):**
  - `Ebenezer-official.exe`: when `004c1dbe` returns 0 at `004635c8` the
    magic packet `004630a6` reaches `0046e707` (`0046315c`/`00463161`),
    which sends `0x31` phase 4 with -103 in the fourth data short
    (`0046e7b6`) (PQ-468; reread for PQ-469).
  - `KnightOnLine.exe` 1298: the fail receive `00586fa0`, on -103 and for
    the player only (`0058733c`–`00587347`), clears the recorded cast
    `+0xb04` (`00587353`), calls `005d91f0`(0, 0, 0), loads text `0xfa4`
    through `00615080` (`0058738c`), formats it with the row's `+0x18`
    string (`[EBP+0x18]` at `005873aa`, the empty string `006a3560` when
    null) through `0067429f` (`005873d2`) and passes it with `0xffff3b3b`
    to `005d7250` on `[manager+0x18]` (`00587431`–`00587446`), the message
    output window's append (D-209, D-210). Observers' clients take no text
    on this path (the text block follows the player test).
  - Source-aided: the `+0x18` string is the skill's name. Local asset: the
    player's 1298 text 4004 is "%s failed".
- **Selected:**
  - The skill policy gains N3K4: N3K3 with, after the notice, a `failed`
    line (bounded as the notice is: 1–96 printable ASCII bytes, at most one
    `%s`, no other `%`) and its colour (u32 ARGB, alpha not 0). A failed
    line needs a notice (N3K3 stays valid without one). Both readers bound
    it; the server keeps nothing of it. `tools/assetc/ko_skills.py` cooks
    Moradon's from the player's text 4004 with 1298's `0xffff3b3b`; the
    engine has no KO text or colour.
  - The colour lives with the line, not in the HUD's message block (N3HM):
    1298's callers pass a colour per message (D-210), and this caller's is
    not the window's refusal or notice colour. The HUD message log takes a
    post's own colour over its kind's for every line it wraps to.
  - The client remembers the newest 16 skill actions it sent (sequence
    number and skill). When an `ActionResult` with one of those numbers
    and the status `out_of_range` arrives, it posts the failed line, its
    `%s` replaced by that skill's label, in the policy's colour, once per
    action. Every received `ActionResult` is now kept in order (the newest
    32), so several in one poll each count. A melee or ranged action never
    enters the record; other skill refusals post nothing (unchanged).
  - The cast end is unchanged: the server's state and cast-end event
    already end it on every client.
- **Server authority:** unchanged. The server decides the refusal on its
  own positions and sends it to the caster only (as before); the client
  trusts only the status the server sent for a sequence number it chose
  itself, and the text and colour are package data. A client that skips
  the hint, or forges a sequence number, changes nothing on the server.
- **Considered:**
  - The line from the server (a text or code in `ActionResult`): rejected;
    the text is package data the client already has, and the status names
    the refusal.
  - A third message kind with its colour in N3HM: rejected; the colour is
    the caller's in 1298, and a HUD without the block would lose it.
  - Posting on every skill refusal: not done here. `0046e707` writes -103
    unconditionally (`0046e7b6`), so each of its six callers makes 1298
    post this line, but what those callers refuse, and so which of n3e's
    other statuses they match, was not read; those statuses stay as they
    were (PQ-471). 1298's -100 and -104 lines (texts `0xfa2`, `0xbc7`,
    PQ-468) come from elsewhere on the server, also unread. (PQ-471, D-242:
    read. The callers refuse states n3e has no counterpart for, so only
    `out_of_range` matches; -100 is the admission's, on every casting-phase
    refusal; -104 goes only into Type1 1 and 2 phase-3 packets.)
- **Limits:** only `out_of_range` posts the line, although every
  `0046e707` refusal is -103 in 1298 (PQ-471; D-242: no other n3e
  refusal is one of them). 1298's fail also stops the caster's self FX and returns its
  pose to state 0 on observers' clients, stands a seated player up and drops
  the client recast for every code but -101. n3e's cast-end event ends the
  cast pose and FX of a cast that began; its server stands a caster when it
  accepts a cast, so a cast refused at its acceptance leaves a seated caster
  seated, where 1298's `005d91f0` would stand it (whether 1298's client
  sends a skill while seated was not read); whether the cooldown stays is
  PQ-470. The colour is read from the binary call
  only; no rig capture was made. A package with N3K2 or N3K3 posts no line,
  as before.
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-236 — 2026-10-30 A skill refused after its release keeps no cooldown when Ebenezer answers the refusal before its reuse window; a refusal it drops silently, and n3e's own refusals, keep it

- **Context:** PQ-472, queued by PQ-470. Since D-099 n3e commits a skill's
  recast deadline to PostgreSQL when its cast time ends (the stage-2
  `skills::gate(…, true)`) and keeps it when the impact is then refused:
  `cancel_gate` drains the commit and recovers the deadline into the live
  cooldowns. Since D-231 and D-232 the hold (`out_of_range`) and the other
  requirements are checked from the release to the impact. PQ-470 read that
  Ebenezer's effecting checks its reuse window only after those checks.
- **KO reference (binary):**
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`), `004630a6` for an
    effecting (phase 3) of a user's row not of Type1 2: the reuse window
    `0046dbe2` is called at `004637e4`, after every requirement check. In
    order before it:
    - a dead source (`+0x8138` 3 at `004635a1`, HP `+0x66` below 1 at
      `004635b4`) returns with no packet;
    - the range `004c1dbe` (`004635c8`) fails the packet -103 through
      `0046e707`;
    - the type-3 check `0046e8ef` (`004636b9`), for a user target and a row
      whose Moral (`+6`) is at most 4 (`0046e929`), returns 0 with no packet
      for a missing target user (`0046e942`) or one whose HP is below 1
      (`0046e94e`); for an NPC target it returns 0 with no packet when the
      NPC is not found (`0046eaae`);
    - the admission `00464b43` (`004637b0`; a 0 returns at `004637b9`)
      refuses a missing or state-3 target user (`00464c01`, `00464c05`), a
      missing NPC or one whose `+0x60` is 0 (`00464d72`, `00464d78`), the
      class and level (`004653e2`–`00465450`) and the MP (`004654ba`,
      `004654c9`), each through `00464c1b`, which sends `0x31` phase 4 (to
      the source, or the region while the magic object's `+0xc` is 2) with
      -100 when the phase argument's low byte is 1 (set at `004654eb`),
      else 0 (`00464cc8`–`00464cd2`).
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`): the release puts the
    row in the recast list `+0x78` (`00584c08`), and the skill start refuses
    a row in it until its timer runs out (`00581c45`–`00581c80`). The list's
    entries are erased (`0058cf70`, `0058f100`, `0058c0a0`) only by the fail
    receive `00586fa0` (phase 4 of the magic receive `005d9f60`; for every
    code but -101, `005870b2`–`00587126`), by two result branches of the
    phase-3 receive `00586690` (its second data short -1, or -2, which post
    texts `0x1de0` and `0x1ddf`) and by the manager's teardown `0057e660`
    (callers by cross-reference).
  - So (inference from binary, no rig): a refusal answered with a phase-4
    packet leaves neither Ebenezer's window nor 1298's recast, and the
    skill can be cast again at once (unless an earlier window still runs);
    a refusal dropped with no packet starts no window either, but 1298's
    client keeps the recast it set at the release and refuses its own
    recast until that runs out, as after a landed skill.
  - Source-aided: `+0x8138` 3 is the dead state; NPC `+0x60` is the state
    byte the Game SERVER trace prints (PQ-188, binary), 0 the dead state by
    the source's `NPC_DEAD`. Local asset: Tiny Healing's Moral is 2, Light
    Strike's 7 (PQ-465).
- **Selected:**
  - A refusal of a released cast whose recast commit wrote a deadline
    deletes exactly that deadline when it is one Ebenezer answers with a
    packet before its window: `out_of_range`, `insufficient_resource`,
    `wrong_class`, `level_required`, `target_dead` on an NPC, and n3e's
    `weapon_required` and `invalid_target` (their nearest counterparts are
    the admission's item and Moral tests, an inference; the target's
    category cannot change after the acceptance). (PQ-479, D-243: the item
    tests count consumed items, not the hands, so the `weapon_required`
    correspondence is rejected; KO does not refuse a weapon removed
    mid-cast. PQ-480.) (PQ-480, D-244: n3e no longer tests the weapon
    after the acceptance, so `weapon_required` leaves this list.)
  - It keeps the deadline for the refusals Ebenezer drops with no packet:
    `actor_dead`, `target_dead` on a player (n3e's player-target skills are
    heals, Moral 2) and `stale_target`. 1298's client keeps its recast
    there, and n3e's client has no recast gate of its own: it shows the
    server's deadline (D-099). The server keeping it is what an unmodified
    1298 player meets, without trusting a client.
  - It keeps the deadline for n3e's own refusals, which have no counterpart
    before Ebenezer's window: `stale_session`, a leave (`interrupted`),
    `cast_timeout`, `skill_unavailable` (the commit's outcome unknown), and
    the NPC-write refusals at the impact (`target_pending`,
    `settlement_capacity`, `contributor_capacity`), which come where
    Ebenezer's executor runs after its window. Any other status keeps it.
  - The undo runs in the recovery that already drains a cancelled commit
    (D-099): once the commit returns a written deadline, one fenced
    transaction (the realm fence, the session's generation and online row,
    locked `FOR UPDATE` as the gate locks it) deletes the row only if its
    deadline is exactly the one written (the commit returns it, as
    microseconds), then reads the cooldowns back into the live snapshot. A
    stale fence, a failed commit or a failed undo leaves the deadline as
    written. A new cast is refused `combat_pending` until the recovery
    returns, as before.
- **Server authority:** unchanged. Postgres stays the only copy of a
  deadline. The undo is decided by the server's own refusal, never a client
  report; a refused impact is never applied or charged, so an undone
  deadline never follows an effect. No blocking I/O enters the tick.
- **Exploit check (BINARY-POLICY):** none found. A caster cannot fail its
  own released cast by moving (D-231 measures from the release), and an
  undone cast applied nothing and cost nothing, so a refusal it arranges (a
  friend leaving the hold, say) only lets it try again, as in KO. The undo
  costs no extra transaction: it is part of the recovery D-099 already ran.
  So no deviation is recorded.
- **Considered:**
  - Undoing every requirement refusal after the release, `actor_dead`
    included (the item's first reading): rejected; 1298 keeps its recast
    for the silent drops, so an n3e player would recast sooner than a 1298
    one.
  - Committing the deadline only at the impact: rejected; D-099 commits
    before the effect so that no effect lands without its durable cooldown.
  - Deleting any running deadline of the skill (no exact match): rejected;
    the exact match also protects a later write.
- **Limits:** whether 1298 clears its recast list on death or respawn was
  not read; with `actor_dead` kept, a caster that respawns within the
  skill's cooldown waits it out. What 1298's recast timer counts (`[006a3ffc]`,
  `[006a40d8]`, its per-tick update) was not read, so "as after a landed
  skill" assumes n3e's cooldown matches it. (PQ-474: 1298 keeps its
  recast list through its own death and respawn, and its timer counts
  ReCastTime / 10 s of frame time from the release, which matches n3e's
  `cooldown_ms` at frame times between 1 ms and 1 s while the device
  presents (a lost device leaves the frame time stale); binary within its
  scans' limits, no rig. The keep stands, no fix. See its
  evidence record.) The type-3 executor `00466da0`'s
  own refusals (after the window) were not read. Ebenezer's too-early try
  restarting its window is PQ-473. No rig capture was made.
- **Amends:** D-099 (a refused impact's commit is no longer always kept)
  and D-231's Limits (a target leaving the hold after the commit no longer
  keeps the recast).
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-237 — 2026-10-30 A skill pressed inside its cooldown is refused and its deadline stays: n3e's server gate stands in for 1298's client recast, which never reaches Ebenezer's window, so Ebenezer's restart of that window is not applied

- **Context:** PQ-473, queued by PQ-470. Since D-099 n3e's server is the
  only recast gate: `Runtime::begin` refuses a skill whose live deadline has
  not been reached with `cooldown`, at the acceptance, with no database work
  and no change to the deadline. n3e's client sends every press and shows the
  server's deadline (D-099, D-236). PQ-470 read that Ebenezer's reuse window
  restarts on a too-early try.
- **KO reference (binary):**
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`), `0046dbe2`: for a
    slot (`+0x8928`, 15 of them) that holds the magic id, it refuses while
    now + `[00633eb4]` is at most the slot's time (`+0x8964`) + (CastTime
    `+0x18` + ReCastTime `+0x19`) / 10 (integer division, `IDIV` at
    `0046dc82`; `FCOMPP`, `JNC` at `0046dc94`). Refused, it stores now in the
    slot (`0046dcab`) and returns 0; accepted, it stores the id and now
    (`0046dc9c`, `0046dca6`) and returns 1. `[00633eb4]` is the float 0.1
    (bits `3dcccccd`), a constant also read at six other places
    (`00499682`, `0049eb6f`, `0049eb9f`, `0046c857`, `0046c887`,
    `00494c6b`). Now is `004075b9`: `QueryPerformanceCounter` divided by
    `QueryPerformanceFrequency` (seconds), or, without a performance
    counter, `timeGetTime` undivided (milliseconds); the slot keeps it as a
    32-bit float. The refused path also calls `strlen` on the string the
    user's `+0x8098` pointer leads to (`005008b0` at `0046dcb6`; the
    character name by ko-src's naming) and discards the result (a
    compiled-out log, an inference).
  - Besides that test, the same function refuses in three other cases and
    passes in two others. A magic in none of the 15 slots takes the first slot whose id is below
    1 or whose time + the new magic's (CastTime + ReCastTime) / 10 is at
    most now, with no slack (`0046dcc8`–`0046dcfc`), stores the id and now
    there and returns 1 (`0046dd02`–`0046dd18`). With all 15 slots held by
    other magics still inside that window it returns 0 and stamps nothing
    (`0046dcfe` -> `0046dcbc`). Before any slot, a magic with no main row
    returns 0 (`0046dc06`), and a Type1 8 row returns 0 without its type-8
    row and 1, with no window, when that row's `+8` is 0x15
    (`0046dc0c`–`0046dc2d`; PQ-450).
  - The window is checked only at the effecting of a row not of Type1 2
    (`004637bf`–`004637eb`, after the requirement checks of `00464b43`) and at the flying
    phase of a type-2 row (`0046f462`); a 0 drops the packet with no answer
    (`004637eb` -> `0046459a`; `00463781`). The casting phase is not
    checked (PQ-470).
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`): the skill start
    refuses a row still in its recast list until its timer runs out
    (`00581c45`–`00581c80`), so it sends nothing; the release sets that
    recast (`00584c08`). `[006a3ffc]` is 10.0 and `[006a40d8]` 0.1
    (floats), but what the timer `+0x80` counts per tick was not read
    (PQ-474; read there: ReCastTime / 10 s of frame time from the release).
  - Package data (local-asset): n3e's `cooldown_ms` is ReCastTime × 100
    and `cast_ms` CastTime × 100 (`tools/assetc/ko_skills.py` checks both
    against `Skill_Magic_Main_us.tbl`). Light Strike (CastTime 15,
    ReCastTime 54) gets an Ebenezer window of 69 / 10 = 6 s; Tiny Healing
    (19, 0) of 1 s.
- **Reasoning:**
  - The window's test against the skill's own slot never refuses a cast
    n3e accepts, within the float limit at the end of this point. A release is at least
    (CastTime + ReCastTime) / 10 s of 50 ms ticks after the last release
    whose recast stands, that is, whose impact was not refused with a D-236
    undo. The reason: a cast accepted at or after that release's deadline
    still has `cast_ms` to run, and tick rounding and the gate's database
    round trip only lengthen it. A tick may start late, so the wall time
    between two releases falls short of their ticks by less than one tick
    (50 ms; the loop skips missed ticks, `MissedTickBehavior::Skip`).
    Ebenezer's test passes an effecting more than ⌊(CastTime + ReCastTime)
    / 10⌋ − 0.1 s after its slot's time. That leaves at least 0.05 s, plus
    the tenths that the integer division drops, for the slot's float32
    rounding, which is at most half a float step. Half a step stays below
    0.05 s while `004075b9` returns less than 2^20 s (about 12 days of
    counter time). For Moradon's two skills, whose dropped tenths are 0.9,
    the limit is 2^24 s (about 194 days).
  - This is not a minimum gap between any two releases. When the impact is
    refused with a D-236 undo (`out_of_range`, `insufficient_resource`,
    `wrong_class`, `level_required`, `weapon_required`, `invalid_target`,
    `target_dead` on an NPC), the deadline is deleted, durably and live, and
    the next release can follow after only `cast_ms` (1.5 s for Light
    Strike, against its 6 s window). Ebenezer makes those refusals before
    `0046dbe2` (`004637e4`, PQ-470), so they never stamp its slot. The
    skill's slot, if it still has one, holds the last effecting that
    reached the window, and the new release is more than one window after
    that. If another magic has taken the slot, the skill gets a fresh slot
    and passes, or meets the 15-slot refusal (KO reference).
  - The refusals D-236 keeps (`actor_dead`, `target_dead` on a player,
    `stale_target` and n3e's own) leave n3e's deadline in place even where
    Ebenezer would not have stamped its slot, so they only make n3e
    stricter. So, within the float limit, the test against the skill's own
    slot would not have refused a cast n3e accepts, and its restart is never
    reached by a cast n3e lets through.
  - The 15-slot refusal is not covered by that argument. With 15 other
    magics inside the new magic's window, Ebenezer refuses a cast that
    n3e, which has no slot cap, accepts. That difference is PQ-475's; this
    decision does not change it.
  - What n3e's `cooldown` refusal stands for is 1298's local recast refusal
    (`00581c45`), which happens on the client, sends no packet and restarts
    nothing. Ebenezer's restart is reached only by an effecting sent while
    that client gate should have held it: a client that skips its own gate,
    or one whose recast list was cleared by a relayed fail of any caster
    (`00586fa0`, PQ-468; an inference, no rig). (PQ-477, D-240, adds a
    third: a MyInfo sent during a session by KO's room system, which
    empties the list; the rule here stands.) (PQ-478, D-241: also by an
    unmodified client whose frame clock runs fast, or with uneven delivery;
    recorded as a correction.) n3e's server cannot tell
    those apart from an ordinary press, because n3e's client has no gate of
    its own (server authority, D-099).
  - Restarting n3e's deadline on every `cooldown` refusal would therefore
    punish ordinary presses that 1298 never sends: a player pressing a
    skill again more often than its window would keep it from ever casting,
    which no unmodified 1298 player sees. It would also make each refused
    press a durable write (the restart must outlive a reconnect, as D-099's
    commit does) where today it costs nothing.
  - Not restarting gives a client that sends early no advantage: its first
    accepted cast comes at the same deadline as an unmodified client's.
    It only spares such a client KO's penalty.
- **Selected:** keep `Runtime::begin` as it is. A press inside the cooldown
  is refused `cooldown`, writes nothing and leaves the deadline; the press
  at the deadline is accepted. This is a server-authority mapping (LOOP,
  "Kept different"): the visible behaviour of an unmodified client matches
  1298's local gate, so no deviation or correction is recorded (since D-241, PQ-478: recorded as a correction, the rule unchanged). The test
  `skill_runtime::tests::a_press_inside_the_cooldown_leaves_the_deadline`
  pins it.
- **Considered:**
  - Restarting the deadline on a `cooldown` refusal (a stricter server
    rule, durable like D-099's commit): rejected for the reasons above.
  - Restarting it only for a press whose effecting would come inside
    Ebenezer's window (now + cast time + 0.1 s at most the last release +
    ⌊(CastTime + ReCastTime) / 10⌋): rejected. It still restarts ordinary
    presses, because n3e's client sends them, and it needs the durable
    write.
  - Adding a client-side recast gate so that only a skipped gate reaches the
    server, then restarting: rejected for now. The client would have to
    predict the deadline at the release, before the server's snapshot, and
    1298's own timer is unread (PQ-474, since read); a press that raced the snapshot
    would be punished.
- **Limits:** this rests on 1298's client recast holding a press at least
  until Ebenezer's window would accept it. If PQ-474 finds 1298's recast
  shorter, an unmodified 1298 client would itself meet the restart, and
  this decision is revisited there. (PQ-474: the recast is ReCastTime / 10 s of
  frame time from the release, not shorter. The rest of the gap to the next
  effecting is the next cast up to its clip's first marker; frames of
  1 ms or less count 1/30 s; and while the device is lost the tick keeps
  subtracting the last frame time on every loop pass. Whether those, or a
  route not yet found, let an unmodified client meet the restart is PQ-478;
  the rule stands meanwhile. PQ-478: at ordinary frame times and with even
  delivery, the next cast keeps the gap above the window, by at least
  1.0 s for Light Strike and 1.2 s for Tiny Healing. Frames of 1 ms or
  less, a lost device and uneven delivery can still bring an unmodified
  client into the restart. So D-241 records this rule as a correction,
  and the rule is unchanged.) Ebenezer's window is coarser than n3e's
  deadline (whole seconds, 0.1 s slack, float time); that n3e paces a
  skill by `cooldown_ms` from the release whose recast stands rather than by
  that window is D-099's rule (with D-236's undo) and unchanged. The
  argument covers only the test against the skill's own slot:
  - With 15 slots held by other magics inside the new magic's window,
    Ebenezer refuses without stamping (`0046dcfe`). n3e has no slot cap and
    accepts; PQ-475 decides that difference.
  - When `004075b9` reads 2^20 s or more, the float32 slot time can be
    rounded up past the margin, and the test could refuse a cast near the
    end of its window that n3e accepts. That is a precision artefact of the
    reference clock, not imported.
  - On the `timeGetTime` fallback the window counts milliseconds, so it is
    a thousandth as long. The argument assumes the performance counter.
  - When Ebenezer clears the slots (login, zone change, death) was not read.
  No rig capture was made.
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, BINARY-POLICY, STATUS, the
  evidence record.

## D-238 — 2026-10-30 Ebenezer's 15-slot reuse table is not reproduced: a skill is refused only by its own deadline, never because 15 other skills are inside its window

- **Context:** PQ-475, queued by PQ-473 (D-237 Limits). Ebenezer's reuse
  window `0046dbe2` keeps 15 slots per user. A magic in none of them is
  refused, with no stamp and no packet, when all 15 are held by other magics
  still inside the new magic's window. n3e has no slot table: since D-099
  each skill has its own deadline (`character_skill_cooldowns.ready_at`,
  durable), and one cast runs at a time.
- **KO reference (binary):**
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`), `0046dbe2`
    (re-decompiled by PQ-475: the same code as PQ-473's output): the slots are
    the user's ids `+0x8928` and float times `+0x8964`, 15 each (`0xf`). A
    magic found in no slot takes the first slot whose id is below 1 or whose
    time + the new magic's (CastTime `+0x18` + ReCastTime `+0x19`) / 10 is
    at most now (`0046dcc8`–`0046dcfc`), and stores its id and now there
    (`0046dd02`–`0046dd18`). With all 15 held by other magics inside that
    window it returns 0 and stores nothing (`0046dcfe` -> `0046dcbc`). The 0
    drops the effecting (`004637eb` -> `0046459a`) or the flying phase
    (`00463781`) with no packet (PQ-450, PQ-470).
  - The slots are written only in `0046dbe2` and zeroed only in the loop of
    `0048ff43` (`0049032f`–`0049033a`), by PQ-470's operand scan (which
    finds an offset only where an operand spells it). `0048ff43`'s one
    caller is the thunk `00401a28`, whose one reference is `00634a14`
    (PQ-192, PQ-470). PQ-475 read that word as the entry at `+0xc` of the
    table at `00634a08`. The constructor `0048fd79` sets up the object's
    `+0x88b8` (`0048fdff`), a list that `0048ff43` drains
    (`004902d0`–`004902e5`), and stores `00634a08` last (`0048fe1d`).
    `0048fe82` is the class's destructor: its only caller is `0048fe5f`
    (`0048fe62`), which has the shape of a scalar deleting destructor (it
    passes the object on when its argument's bit 0 is set, `0048fe67`), and
    it stores the table (`0048fe93`) and then releases the members with the
    exception state counting down from 6.
  - In Ebenezer's code below `004d0000` three instructions call through
    `+0xc` of a table: `00407375` in `004072ea`, which logs
    `CloseProcess socketID` (`0065d210`); `00446016` in `00445fea`; and
    `004908e7` in `0049085b`, the entry at `+4` of the same table (thunk
    `004024b4`, `00634a0c`; the user's close by ko-src's naming,
    `CUser::CloseProcess`). That last call is on a user object, since
    `0049085b` is the user table's own entry.
  - The call in `00445fea` is virtual, so it reaches `0048ff43` only for an
    object whose table is `00634a08`. For the accept that is shown:
    `0041c15f` sets up the port object `006827e0` (`00444960` at
    `0041c677`, which allocates its arrays `+0x44` and `+0x48`), then builds
    1,500 objects with `0048fd79` (`0041c6a1`) and stores each in the array
    at `[006827e0 + 0x48]` (`[0x00682828]`, `0041c6aa`–`0041c6ba`). Its
    listen `00444ac0` (`0041c6ed`, the same port) starts the accept thread
    `004441e4` with that port as its argument (`00444c13` -> `00444d38`).
    The thread takes an object from the port's `+0x48` array (`00444ef7`,
    `0044427a`) and calls `00445fea` on it (`00444311`), after
    `WSAEnumNetworkEvents` with the accept bit 8 (`00444232`). The outbound
    connect `00445446` also calls `00445fea` (`004454e5`) on an object whose
    class was not traced.
  - So the window is emptied when a connection is accepted and when the
    user's session closes. No clear was found on a zone change, a death or a
    respawn. Limits of that reading: other writers of the port's `+0x48`
    array, besides `00444960`, `0041c15f` and `00444ef7`, were not scanned; the operand scan misses a pointer built
    from another base and a bulk `memset`; the `+0xc` call scan misses a
    call through a register loaded from the table; its 92 hits at or above
    `004d0000` were not examined one by one (the one read, `004d6773`, is
    `CRecordset` code by Ghidra's names).
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`): the release `00584b00`
    stores the row's `+0x7c` × `[006a40d8]` (0.1) in its `+0x80`
    (`00584bf0`–`00584c02`) and calls `0058ba10` on the recast list `+0x78`
    with the row object's address as the key (`MOV [ESP+0x10],EBP` at
    `00584be8`, passed at `00584bec`/`00584bf7`). `0058ba10` is an
    ordered-tree insert: it compares that key, unsigned, with each node's
    `+0xc`. When the tree's flag at `+8` is 0 it returns the node already
    holding the key, else it inserts; with the flag set it inserts in any
    case. The node insert `0058d0d0` allocates a 0x14-byte node, increments
    the count at `+0xc` and rebalances. Neither function compares the count
    or any size with a bound. The skill start's lookup matches: after
    `0058c170` (`00581c55`) finds the key `[ESP+0x1a4]` in the list, it
    loads that same key into `EDI` (`00581c61`) and reads the row's `+0x7c`
    and `+0x80` through it (`00581c6c`–`00581c75`). The flag's value for `+0x78`, and the helpers
    `004641c0`, `00565ed0` and `0058d880` that `0058ba10` calls, were not
    read. So nothing read caps how many distinct skills a 1298 client holds
    on recast, or sends effectings for, inside one window.
    Whether an unmodified player meets the cap depends on the skills it has
    and how it plays; that was not shown (no rig).
  - Package data (local-asset): Moradon casts two skills
    (`games/moradon/skills.json`), so the cap cannot be met there.
- **Reasoning:**
  - The refusal is a capacity limit, not a reuse rule. It falls only on a
    magic that holds no slot, that is, one never used since the connection
    or one whose slot another magic has taken. The same cast passes with 14
    other magics inside its window and is dropped with 15. The skill's own
    reuse does not decide it; its row only sets how long the window is in
    which the others are counted.
  - It is silent. The effecting or flying phase is dropped with no answer.
    The 1298 client has already played the cast and, at the release, set
    the row's `+0x80` and put the row in its recast list
    (`00584bf0`–`00584c08`), and a silent drop leaves that entry in place
    (PQ-472's inference: only the fail receive `00586fa0`, two branches of
    the phase-3 receive `00586690` and the list release `0057e660` erase
    from that list). The player sees the skill do nothing, waits out its recast
    and gets no message.
  - The table does not enforce the per-skill window it holds. A slot is
    reused by the new magic's window, not its holder's, so a holder can lose
    its slot while its own window runs and then pass into a fresh slot
    (`0046dcc8`–`0046dd18`). It is therefore neither a bound on distinct
    skills nor a complete per-skill gate.
  - Leaving it out opens no exploit. n3e gates every skill by its own
    deadline on the server (D-099, D-236, D-237) and runs one cast at a
    time, so a client that sends many distinct skills is still paced by
    each skill's cast time and cooldown. n3e is stricter than the table
    where a holder loses its slot: its deadline stands. An unmodified 1298
    client would not use that path either, because its skill start refuses
    a row while that row's own entry in its recast list runs
    (`00581c45`–`00581c80`), whatever other rows the list holds, so that
    part is the same
    server-authority mapping as D-237. (Narrowed by D-240, PQ-477: KO's
    room system sends MyInfo during a session, which empties that list, so
    an unmodified client can use the path, and n3e's deadline there is the
    correction of an exploit.)
  - Reproducing it would add a per-session record of the last release of
    every skill used, a 15-entry rule and a silent refusal with no n3e
    message to show. It would refuse ordinary players and protect nothing.
  - This is a correction of a logic bug under BINARY-POLICY: the failing
    invariant is that a skill whose own reuse has run is castable, and the
    refusal also leaves the client's recast and the server out of step. The
    correction record
    is written with this entry, before the test.
- **Selected:** n3e does not reproduce the 15-slot refusal. No slot count
  enters package data and the runtime does not change. A skill is refused
  for reuse only by its own deadline. The unit test
  `skill_runtime::tests::sixteen_skills_inside_one_window_all_cast` pins it:
  16 skills cast one after another, the 16th accepted while the other 15 are
  inside its window, and each of the 15 still refused `cooldown` by its own
  deadline.
- **Considered:**
  - A package slot count, refusing a skill while that many other skills
    sit inside its window (from `cast_ms` + `cooldown_ms`): rejected for the
    reasons above. It would also need a refusal status the client can show,
    where Ebenezer sends none.
  - Recording the difference with no test: rejected. The test is cheap and
    stops a later change from adding a cap by accident.
- **Observed, not changed:** Ebenezer empties the window at every new
  connection and at the close (within the limits above: the operand and
  call scans and the port pool's unscanned writers). The close alone makes
  a reconnect clear every reuse window on the server. n3e's deadline is durable and survives a reconnect
  (D-099's commit; CONTRACTS). Whether 1298's client keeps its recast list
  `+0x78` across a reconnect was not read (`0057e660`, called from
  `0057d810`, frees the lists; PQ-472). If it does not, an unmodified KO
  player can end a skill's recast early by reconnecting, which n3e does not
  allow. PQ-476 reads that and decides whether n3e's rule needs a
  correction record.
- **Limits:** the clearing sites rest on the limits above. That
  `0048fd79` builds the user is by the fields it shares with `0048ff43` and
  the `0x8bb0` objects `0041c15f` pools; that `0049085b` is the user's close
  is ko-src's name; that `004441e4` serves the accept is by its
  `WSAEnumNetworkEvents` test. Whether an unmodified 1298
  player can reach 16 overlapping skills, and what 1298 shows then, was not
  shown. No rig capture was made.
- **Recorded in:** BINARY-POLICY (correction record and table), CONTRACTS,
  `content/skills.md`, GAPS ("Magic types"), FEATURES KOF-0011, PARITY,
  BINARY-INDEX, STATUS, the
  evidence record.

## D-239 — 2026-10-30 A skill's deadline survives a relog: KO's relog ends every recast early, and n3e keeps its durable deadline as the correction of that exploit

- **Context:** PQ-476, queued by PQ-475 (D-238 "Observed, not changed").
  Ebenezer zeroes its reuse slots at the close (PQ-475). n3e's skill
  deadline is durable (`character_skill_cooldowns.ready_at`, D-099) and is
  read again at session entry (`skills::recover`). The question was whether
  1298 keeps its own recast across a reconnect or a return to character
  selection, so whether an unmodified KO player can end a recast early by
  leaving and coming back.
- **KO reference (binary):**
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`). The magic-skill
    manager (ProcMain `+0x18c`) is built once, in the main procedure's
    constructor `005c17a0` (`005c2b1c`), whose one caller is the start-up
    `006453b0` (`00645c6a`), and destroyed only in that procedure's
    destructor (`005c33b2`–`005c33c0` -> `0057d810` -> `0057e660`). The
    main procedure's `Release` (`005c37e0`), run when the procedure is left,
    calls the manager's `0042de30`, which touches only a string member.
  - The manager's reset `0057e520` empties the recast list `+0x78`
    (`0057e5b8`–`0057e62d`) and the tree `+0x38`, and calls `0058a170`,
    which empties `+0x68`. Its only callers are the manager's constructor
    (`0057e4fa`) and `MsgRecv_MyInfo_All` `005c87c0` (`005ca7c9`), which the
    main dispatch `005c5140` runs for packet `0x0e` (table entry
    `005c65e8`).
  - Every entry into the main procedure runs its `Init` `005c3bb0`
    (`006468e0` at `00646905`). `Init` sends `0d 01` and the name
    (`005c3d38`–`005c3d92`), with no return before it. Ebenezer's game
    start `004c66dc` answers a first byte of 1 with `004970cb(0)` (PQ-276).
    That function sends the `0x0e` packet (`00497749`, `00498160`) unless
    the user's zone has no map, no HOME row is found or the nation is
    neither 1 nor 2.
  - A lost connection (`FD_CLOSE`, `0064b12d`–`0064b138`) calls
    `00647e40(1)`. That posts text 1601 with behaviour 1, and the box's OK
    quits the process (`00526d00`, `00527027`–`00527029`).
  - The exit menu's `btn_chr` (`+0xb0`, `0055b6dd`), when no exit timer
    runs (ProcMain `+0x1f0` = -1.0), calls `0055ba70` (`0055b7ee`). That
    closes the socket (ws2 ordinal 3), sleeps 4,000 ms, reconnects to the
    same address and port, and switches to the character-select procedure
    `[008189b4]` (`ChrSelect` lights in its `Init` `005f98c0`). Character
    select switches back to the main procedure `[008189b8]` through
    `005fe280` (`005fe339`–`005fe33f`) and `005fea70`
    (`005feb6b`–`005feb71`), both reached from code in the range of its
    vtable `+0x20` entry `005faf10` (`005fb11c`; `005fb0fa` ->
    `005fe5b0` -> `005fe6f9`). The
    message box's behaviour 2 does the same with a 2,000 ms sleep (`00527034`–`005270ba`).
  - A scan of the recast tree type's nil sentinel `[0x008170c0]` (51
    instructions in 21 functions) finds `+0x78` emptied only by `0057e520`
    and the destructor. Single rows are erased by the fail and phase-3
    receives (PQ-472) and by the manager tick `005845d0` (`00584681`,
    `005846ca`), whose conditions are PQ-474's. PQ-472's list of the
    places that erase from `+0x78`, which D-236 and D-238 cite, followed
    three erase helpers and missed the reset and the tick.
  - The skill start tests a recast only for a row found in `+0x78`
    (`00581c55`, `00581c6a` -> `00581c86`; PQ-470).
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`): the slots are zeroed
    at the close (`0049085b` -> `0048ff43`) and at an accept (PQ-475,
    within its scans' limits).
- **Reasoning:**
  - After a disconnect the player starts a new client, whose list starts
    empty and is reset again on MyInfo. After a return to character
    selection the list is kept only until the world is entered again, when
    MyInfo empties it. Either way the close has emptied Ebenezer's slots, so
    neither program refuses the skill. An unmodified KO player ends every
    running recast early by relogging: through the exit menu (about 4 s plus
    the character choice) or by restarting the client after a disconnect.
  - That is a player exploit under BINARY-POLICY. The invariant both
    programs enforce inside a session is that a skill's reuse is its own
    (CastTime + ReCastTime) / 10 s (Ebenezer `0046dbe2`; 1298
    `00581c45`–`00581c80`). Leaving and re-entering breaks it, and the gain
    grows with the skill's ReCastTime.
  - n3e's rule is the correction: its deadline is committed durably at the
    release (D-099) and read again at session entry, where it re-arms both
    the server's admission and the client's recast display. Reproducing
    KO's reset would need n3e to drop committed deadlines on logout or
    character selection, which would hand players the same exploit.
  - The correction record
    is written with this entry. No code changes, so nothing is implemented
    after it.
- **Selected:** keep n3e's durable deadline across logout, reconnect and
  character selection, as a correction of KO's relog reset. No engine,
  wire, schema or package change. Checked by `skills_db` (gate tier:
  `skills::recover` returns the committed deadline) and by the opt-in
  `moradon_skills_live` (log out, reconnect, select: the strike is in the
  snapshot's recast list and refused `cooldown`; `make live-ko` passed
  for PQ-476).
- **Considered:**
  - Matching KO by clearing deadlines at logout or at character selection:
    rejected, since it reproduces the exploit.
  - Recording it as a match: rejected, since the behaviours differ and the
    difference is deliberate.
- **Limits:**
  - The sentinel scan is an operand-text scan. A walk through a sentinel
    pointer loaded elsewhere would be missed.
  - A second tree of the same type, `+0x88`, is not emptied by the reset.
    The skill start fills it for rows with no caster animation, timed by
    row `+0x78` (CastTime by ko-src's field order). So on the in-process
    path such a row could still be held at re-entry if its timer outlasts
    the relog (PQ-474). (PQ-474: the hold counts only in the main
    procedure's tick, so it pauses in character selection; after the reset
    the row resumes its hold, and the tick then sends its effecting with no
    recast entry after it. This is inside the relog exploit and changes
    nothing here.)
  - The exit-menu path is binary at each step. The disconnect-and-restart
    path also rests on four inferences, not traced:
    - that the message box's `+0xd0` is the behaviour `00647e40` passes;
    - that the window procedure's socket branch is the async-select
      message;
    - that the start-up runs once per process;
    - that a new process holds no recast state.
  - Character select's switch back to the main procedure is binary
    (`005fe280` and `005fea70` pass `[008189b8]` to `00646b50`, from code
    in the range of its vtable `+0x20` entry `005faf10`). Which selection
    reaches each branch was not read.
  - Who posts behaviour 2 was not scanned.
  - `004970cb(1)` also sends MyInfo (`00483753`, `00485eeb`, `0048600c`,
    `004869cf`). That could empty 1298's recast list during a session;
    queued as PQ-477. (PQ-477, D-240: all four are KO's room system. They
    empty 1298's list but leave Ebenezer's slots, so they do not reproduce
    this relog exploit; this decision is unchanged.)
  - No rig run: the relog time and an observed early recast were not
    measured.
- **Recorded in:** BINARY-POLICY (correction record and table), CONTRACTS,
  `content/skills.md`, GAPS ("Magic types"), FEATURES KOF-0011, PARITY,
  BINARY-INDEX, STATUS, the
  evidence record.

## D-240 — 2026-10-30 KO's room system resends MyInfo during a session: 1298 forgets every recast while Ebenezer keeps its slots, so a skill whose slot another magic took is cast early; n3e's per-skill deadline is the correction, and nothing changes

- **Context:** PQ-477, queued by PQ-476 (D-239 Limits). Ebenezer's
  `004970cb` sends MyInfo (`0x0e`) for any argument but 2, and 1298's MyInfo
  receive empties its recast list. Game start sends it with 0 (PQ-276). The
  four calls with 1 were not read. The question was whether they reach a
  connected, in-world user, so that an unmodified KO player could empty the
  client's recast during a session while Ebenezer keeps its reuse slots.
- **KO reference (binary):**
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`). With 1, `004970cb`
    needs only a map for the user's zone (`004970dd`–`004970f5`). It skips
    the position check (`00497449`), sends MyInfo (`00497749`, `00498160`)
    and returns (`004981fd`). The four calls are KO's room system
    (KOF-0052, opcodes `0x61` and `0x62`, five rooms allocated at start-up,
    `0041c1de` -> `00486a74`):
    - `00483753` in `004832a1(user, 1)`: leaving a room (`62 09`,
      `004828f8` case 9) or being expelled by a clan chief (`62 0f`,
      `00486851`). The user is moved to zone `0x15`. The close passes 0
      (`004908bb`) and sends nothing.
    - `00485eeb` in `00485cfd`: spectators at a room's end (state 4,
      `00484978`), and the in-game clan members of a chief who leaves
      (`00483629`).
    - `0048600c` in `00485f9e(user, 0)`: a spectator joins a started room
      (`61 04`, `0048750b`) and is moved to zone `0x28` + the room's index.
    - `004869cf` in `004869ac`: on the second room tick after a start
      (`0042fac6`, `0042fafe`–`0042fb0a`; the game-minute tick `00421d2d`),
      every user in the room's list `+0x17c` gets MyInfo. A start is
      `0048393d`, from `62 06` (`00483ed2`) or `61 0a` (`0048749d`).
    - A game start cannot be repeated in the world: `00490919` runs
      `004c66dc` only while `+0x8055` is not 3 (`00490a05`).
    - No function on these paths names Ebenezer's reuse slots
      `+0x8928`–`+0x899f`; PQ-470's scan finds them only in `0046dbe2` and
      `0048ff43`.
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`). Its room windows send
    `61 02`–`61 05` and `62 04`, `62 05`, `62 06`, `62 08`, `62 09`,
    `62 0c` and `62 0f` (`004f35da`, `004f36e1`, `004f42ba`, `004f44a0`,
    `004f6f82`, `004f9128`, `004f9238`, `004f93e1`, `004f947c`,
    `004f9592`, `004fb3ed`, `004fcaf6`). The windows open on `61 01`
    (`005c633d` -> `004f3800` case 1). Ebenezer sends `61 01` when a player
    talks to an NPC of type `0x2a` (`004a52a9`, `004a5506`). MyInfo reaches
    the reset `0057e520` (`005ca7c9`) on every path through `005c87c0`: one
    `RET`, no jump around the call, and the 14 jump-table targets lie
    before it.
  - `0046dbe2` (PQ-473, PQ-475): a magic found in its slot is refused in
    its window, and the refusal restarts the window (`0046dcab`). A magic
    in no slot takes the first slot, in index order, that is empty or
    whose time plus the new magic's window has passed
    (`0046dcc8`–`0046dcfc`).
  - Local data: OpenKO v0.1.2 has one NPC of `byType` 42 (15000,
    `Ijin[Arena]`), with no `K_NPCPOS` row (local-asset).
- **Reasoning:**
  - A room member, a spectator, a user who leaves or is expelled, and a
    clan member whose chief leaves each get MyInfo during a session. The
    client then holds no recast, and Ebenezer's slots stand.
  - For a skill still in its slot, a press is refused, silently, and the
    window restarts. That is a penalty, not a gain, and D-237's rule stands:
    n3e's client keeps no recast of its own that a message could empty, so
    an n3e player is never shown a skill as ready while its deadline runs.
  - For a skill whose slot another magic took, the next effecting takes a
    fresh slot and passes. Inside a session only 1298's own recast held such
    a skill (D-238's exploit check). After the room's MyInfo nothing does.
    So an unmodified player who can reach a room ends a skill's reuse early
    within a session. The steps: cast it, cast a magic that holds no slot
    once that magic's window has passed, then join, start or leave a room,
    and cast it again. That is a player exploit under BINARY-POLICY. The
    invariant it breaks, a skill's reuse is its own, is D-239's.
  - n3e already refuses it: each skill has one server deadline (D-099),
    which another skill's cast does not touch (D-238). That is now a
    correction of this exploit, where D-238 had called it a server-authority
    mapping.
  - It does not change D-239. Its exploit needs both sides cleared, and the
    room paths leave Ebenezer's slots.
  - The correction record
    is written with this entry. No code changes, so nothing is implemented
    after it.
- **Selected:** keep n3e's per-skill server deadline, and record it as the
  correction for a holder that loses its slot. n3e has no room system
  (KOF-0052 absent). When one is built, its transitions keep every skill's
  deadline and the recast shown from it, and do not reproduce MyInfo's
  reset. No engine, wire, schema or package change. Checked by
  `skill_runtime::tests::sixteen_skills_inside_one_window_all_cast` (each of
  15 skills is still refused `cooldown` by its own deadline after a 16th
  lands).
- **Considered:**
  - Leaving D-238's classification: rejected. Its premise, that an
    unmodified client never sends the press, fails after a room's MyInfo.
  - Reproducing the slot table so that a lost slot frees the skill: rejected
    (D-238), since it would import this exploit.
- **Limits:**
  - Only `004970cb`'s callers were followed. Another builder of `0x0e` was
    not looked for, and several room functions were not read: `00482c37`,
    `00484ccc`, `00484b4e`, `00484d00`, `0048661e`, `00487189`, `00487138`
    and `00482a31`.
  - The client sends were found by an operand scan for byte stores. Which
    window control sends each was not traced. Whether 1298 handles `0x62`
    outside the main dispatch, whose entry for it is the default, was not
    read.
  - Inferences:
    - that NPC `+0x57` is `byType` and `+0x8055` 3 is in game;
    - that a press after the reset reaches the window (PQ-470's start
      reading; the tree `+0x88` the reset leaves is PQ-474's: it holds
      only rows with no caster animation, for their cast time, and changes
      nothing here);
    - that some server places a type-42 NPC. The OpenKO data places none.
  - The eviction was read, not exercised. No rig run.
- **Recorded in:** BINARY-POLICY (correction record and table; D-239's
  record limit), CONTRACTS, `content/skills.md`, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-241 — 2026-10-30 An unmodified 1298 client can meet Ebenezer's reuse-window restart when its frame clock runs fast or its effectings arrive unevenly, so D-237's no-restart rule is recorded as a correction of those logic bugs

- **Context:** PQ-478, queued by PQ-474. D-237 keeps n3e's deadline on a
  press inside the cooldown and does not apply Ebenezer's restart of its
  reuse window. It called that a server-authority mapping, with no
  deviation, on the premise that an unmodified 1298 client's own recast
  holds every press until Ebenezer's window would accept the next
  effecting. PQ-474 read the recast as ReCastTime / 10 s of frame time from
  the release, and left three routes open: the next cast up to its clip's
  first marker, frames of 1 ms or less, and a lost device.
- **KO reference:**
  - The gap, from the binary (`KnightOnLine.exe` 1298, SHA-256
    `828ab0db…a5e5`). Two effectings of one skill are at least
    max(blend + C, R + blend + m × C) of frame time apart. C is
    CastTime / 10 s, R is ReCastTime / 10 s, blend is the clip's entry
    blend and m its first-marker fraction. The links:
    - the local player's `Action` `0046be20` (vtable `006a4198`) starts
      the state-6 clip with its own blend through `0041be40`;
    - `00457d90` sets its speed multiplier to 1.0 while it stands and
      casts;
    - `00418b20` holds the frame during the blend;
    - `00461ab0` stretches the clip over C;
    - `004689f0` releases at the marker, `+0x34`, which the loader
      `00410c00` fills from the file;
    - the recast and the clip-end refusal (PQ-474, PQ-447).
  - The values (local-asset; the four animation files are identical to
    the 1298 installer's). On every looks row with a marker, m is
    0.867–0.926 for clip 16 and 0.857–0.911 for clip 17, and blend is
    0.2 s.
    - Light Strike's gap is at least 6.90 s against Ebenezer's 5.9 s.
    - Tiny Healing's is at least 2.1 s against 0.9 s.
    - If the clip record is shared and re-stretched by another caster
      (not read), Light Strike's gap is still at least 6.47 s.
  - Frame rate (binary for the windowed device; the absence of a wait is
    within the scan's limits; the `Present` behaviour is documentation).
    1298 always creates its device windowed:
    `006453b0` stores 1 in `[00818a25]` (`00645482`) and passes it to
    `0043a530`, which writes the windowed word `006e2554`. `WindowMode`
    only picks the window style and the display mode. Among the import
    references no wait was found on the frame path, so no frame cap was
    found within the import-reference scan (see Limits), and the clamp
    `0043acc5`–`0043ace8` counts a frame of 1 ms or less as 1/30 s. A windowed `Present` not waiting for
    the vertical blank is Direct3D 8's documented behaviour, not read.
  - Device loss (binary). The window procedure `0064acf0` acts on
    `WA_INACTIVE` only while `[00818a25]` is 0 (`0064ad96`), so after
    start-up a deactivated client keeps ticking. While `Present` fails
    the tick subtracts the last frame time on every pass (PQ-474). The
    pass rate was not measured.
  - Delivery (inference). Ebenezer takes its time when it handles the
    effecting (`004075b9` in `0046dbe2`, PQ-473), so the gap it sees
    shrinks when the first effecting is delayed more than the second, by
    more than the margin.
- **Reasoning:**
  - At ordinary frame times and with even delivery, an unmodified client
    never meets the restart, and D-237's argument holds there.
  - The binary still allows the client's recast to end early on wall time
    in two ways, and no bound on either was found (within the scan's
    limits; see Limits):
    - the clamp counts a frame of 1 ms or less as 33 ms;
    - a pass that presented nothing keeps subtracting the last frame time.
  - Both are logic bugs in 1298's frame clock: in each, a recast meant to
    last ReCastTime / 10 s lasts less. Through them, and through uneven
    delivery, Ebenezer's restart reaches a player who only pressed when
    the client allowed it.
  - n3e's deadline is wall time on the server (D-099), and its client
    shows that deadline and keeps no clock of its own. So n3e has no
    counterpart of those bugs.
  - Applying the restart would still punish ordinary presses, which n3e's
    client sends (D-237). Not applying it gives an early sender nothing:
    its first accepted cast comes at the same deadline.
- **Selected:** keep D-237's rule. A press inside the cooldown is refused
  `cooldown`, writes nothing and leaves the deadline. Not applying
  Ebenezer's restart is recorded as a correction of a logic bug
  (BINARY-POLICY correction record). It is no longer called a mapping with
  no deviation. Nothing changes in code, schema, wire or package. The test
  `skill_runtime::tests::a_press_inside_the_cooldown_leaves_the_deadline`
  still pins the rule.
- **Considered:**
  - Keeping D-237's mapping classification until a machine is shown to
    reach the fast routes: rejected. The binary does not exclude them, and
    the item directs a correction when an unmodified client can meet the
    restart. The rule is the same either way.
  - Applying the restart only when n3e could tell a fast client clock
    from an ordinary press: rejected. n3e's server cannot tell them apart,
    and its client sends every press (D-237).
- **Limits:**
  - No fast frame, no lost-device pass rate and no uneven delivery was
    observed. These are what the binary allows. The Direct3D 8 runtime
    behaviour cited is documentation.
  - The wait search covers named imports' reference lists. Seven of nine
    unowned `Sleep` sites and `WaitForMultipleObjects` at `00670ebf` were
    not read.
  - Clip-record sharing between characters, and the clip argument at each
    of `00461ab0`'s seven callers, were not read.
  - The routes are not known to be complete.
  - No rig run: the rig runs the archive client, not 1298.
- **Recorded in:** BINARY-POLICY (the PQ-473 row and a correction record),
  CONTRACTS, `content/skills.md`, GAPS ("Magic types"), FEATURES KOF-0011,
  PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-242 — 2026-10-30 Only `out_of_range` posts 1298's failed line: no other n3e skill refusal has a -103 counterpart

- **Context:** PQ-471, queued by PQ-469's review. D-235 posts the skill
  policy's failed line (1298's text 4004 on Ebenezer's -103) only on
  `out_of_range`. Ebenezer writes -103 unconditionally in `0046e707`, so
  every one of its six callers makes 1298 post the line. What those callers
  refuse, and so which other n3e statuses should post it, was unread.
- **KO reference (binary unless marked):**
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`) writes the -103
    immediate only at `0046e7b6` (a linear-sweep scan of the
    disassembly). `0046e707`'s callers refuse the following:
    - In `004630a6`: a by-name target (id -3) whose lookup `004015b9`
      fails; a user source whose `+0x89d6` is 100 (a room spectator,
      PQ-477) or 2 (not identified), or whose authority byte is 250
      (`0046325a`–`0046326d`); and the range `004c1dbe` for a Type1 below
      4 (`004635bf`–`004635d3`).
    - The type checks:
      - `0046e8ef` (Type1 3): a target or caster with a running over-time
        slot (`+0x8540`), a transformation test (`+0x8728`, `+0x8864` /
        10000 = 45), area Moral 6, and an NPC in zone `0x1e`.
      - `0046eb6f` (Type1 4): a buff already held (`+0x86d3`).
      - `0046ece8`, `0046ef9f` and `0046f2a7` (Type1 6, 8, 9):
        transformation, warp and stealth rules.
    - The "over-time", "buff", "transformation", "warp" and "stealth" names
      are source-aided.
  - -100 comes from the admission `00464b43`. Its phase argument is the
    packet's command byte (`004637a6`). It writes -100 when that is 1
    (`00464cc8`–`00464cd2`) or when `004654eb` set it (the tests after the
    MP check), else 0. So a casting phase's refusals are all -100. An
    effecting's class, level, target, Moral and MP refusals are 0, and MP
    is checked only on an effecting (`00465462`). The only other literal
    phase-4 builder, the Type1 4 executor's (`00468e8e`), writes 0.
  - -104 is written only into Type1 1 and 2 executors' phase-3 packets
    (`0046623f`, `0046674c`; scan).
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`), `00586fa0`: on -100
    it posts text `0xfa2` ("Casting failed", local-asset). On 0 it posts
    nothing: `00587579` -> `0058782a`.
- **Selected:** keep D-235's rule. Only `out_of_range` posts the failed
  line.
  - n3e's skills are single-target type 3 with no over-time effects,
    buffs, transformations, warp, stealth, area skills, zone-`0x1e` rule,
    name targeting, room system or 250 tier (GAPS "Magic types", D-154). So
    no other refusal matches a `0046e707` caller.
  - The refusals D-236 keeps as silent drops (`actor_dead`, `target_dead`
    on a player, `stale_target`) gain no line. Nor do `cooldown` (1298's
    local recast, no packet) or n3e's own refusals.
  - An impact refused for class, level, a dead NPC or MP meets Ebenezer's
    code 0, on which 1298 posts nothing, as n3e does.
  - An impact refused `weapon_required` does not match. n3e rechecks the
    weapon each tick until the impact (a caster that unequips mid-cast
    meets it). Its nearest counterparts are the effecting's item-count
    tests (an inference, D-236). Those tests reach `004654eb` and so -100
    (binary: `004b0792` at `00465626`/`0046562d` on the row's `+0x14`, at
    `00465673`/`0046567a` on its `+0x24` item), on which 1298 posts
    "Casting failed". n3e posts nothing (PQ-479). (PQ-479, D-243: rejected.
    Those tests count consumed items, and nothing in KO refuses a weapon
    removed mid-cast, so 1298 posts nothing there either; n3e's refusal
    itself is PQ-480; D-244: n3e no longer refuses it.)
  - `tests/skills.cpp` pins the mapping for each status.
- **Server authority:** unchanged; the client is unchanged.
- **Considered:**
  - Posting text 4004 on every refusal (the item's premise): rejected. The
    callers refuse states n3e cannot reach, and Ebenezer answers n3e's
    other refusals -100, 0 or not at all.
  - Posting "Casting failed" for the acceptance refusals Ebenezer's
    admission would answer -100 (`wrong_class`, `level_required`,
    `target_dead` on an NPC, and `invalid_target` by inference), and for
    `weapon_required` at the impact (the item tests' -100, by inference):
    not done here. That needs a second policy line, and first a reading of what
    1298's skill start `005819e0` refuses locally before it sends a
    casting packet (PQ-479). (D-243: done with N3K5's refusal lines; 1298
    refuses class, MP and weapon itself with its own texts, so "Casting
    failed" is posted only for `level_required` and `target_dead` on an
    NPC.)
- **Limits:**
  - The constant scans are linear sweeps (constants built in registers or
    in desynchronised bytes are missed). The `0x31` builder list counts
    only literal phase bytes.
  - `invalid_target`'s and `weapon_required`'s KO counterparts are
    inferences, as in D-236.
  - Whether a region send (`0041e454`) reaches the sender was not read.
  - No rig capture was made.
- **Amends:** D-235's Considered and Limits (the unread callers are read).
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-243 — 2026-10-30 The client posts 1298's line for a skill the server refuses at its acceptance: 1298's own text where 1298 refuses before it sends, "Casting failed" where Ebenezer answers -100

- **Context:** PQ-479, queued by PQ-471. D-242 found that Ebenezer's
  admission `00464b43` answers every refusal of a casting phase -100, on
  which 1298 posts text `0xfa2` ("Casting failed"), while n3e's client posts
  nothing for its server's other acceptance refusals. It left open what
  1298 refuses itself before it sends a casting packet, and whether n3e's
  `weapon_required` at the impact matches Ebenezer's item-count tests.
- **KO reference (binary unless marked):**
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`). The skill start
    `005819e0` calls the usable check `0057f7f0` (`005829e2`) before its
    target dispatch (`00582b31`–`00582b46`, on row `+0x5c`). A refusal
    returns 0 (`005834c6`) and sends nothing. `0057f7f0` refuses, in order:
    - the class (row `+0x64` not 0, against the player's class group
      `00615210`): text `0xfa3` (`0057f8bc`);
    - the MP (player `+0x808` below row `+0x68`, `0057fae6`–`0057faec`):
      text `0xbbc` for a mage or priest group (`0057fb01`–`0057fb1b`);
      other groups post the buffer with no text loaded;
    - the HP (`+0x4a0` below row `+0x6c`): text `0xfa6`;
    - the need item kind (row `+0x70` not 0 or 9, and not either hand's
      kind / 10, `0057fe54`–`0057fe68`): text `0xfa5` (`0057fe8d`);
    - then item, ammunition, obstacle and other tests n3e has no
      counterpart for.
    Each of these texts goes to `005d7250` on `[this+0x18]` in `0xffffff00`
    (`0057f8d0`, `0057fb2f`, `0057fea5`).
  - Neither `005819e0` nor `0057f7f0` tests the row's level (`+0x60`)
    against the player's level (a scan of both listings for `+0x60`: one
    transformation test at `005826db` and one copy at `0058314b`).
  - For a hostile-target row (type 7, `00582e07`) the skill start returns
    0 with no text when there is no target (`00582e97`), when the target is
    in state 4 or 5 (`00582ea3`, `00582eac`) or when the hostility predicate
    `006164c0` refuses it (`0046c560` at `00582ebc`). It calls the range
    check `00583780` only after these. The exception is a row whose
    `+0x38` is 113 (`00582e0f`–`00582e35`): it checks the range
    (`00582e70`) and casts with target -1 (`00582e89`) before these tests.
  - The cast start `00583f20` sends phase 1 (`00583540` at `005845a2`) for
    a row with a cast time (`+0x78`). The release `00584b00` does not call
    `0057f7f0` (its call list). `0057f7f0`'s callers are `005819e0` and
    `005596f0` (cross-references).
  - On -100 for the player (`00587483`, `005874e5`) the fail receive
    `00586fa0` posts text `0xfa2` in `0xffff3b3b` (`0058752a`–`00587544`).
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`). The type-3 check
    `0046e8ef` takes no phase. For a user target and a row whose Moral is
    at most 4, it drops a target whose HP is below 1 with no packet
    (`0046e94e`). For an NPC target it drops only a missing NPC
    (`0046eaae`). The admission `00464b43` refuses a missing NPC or one
    whose `+0x60` is 0 (`00464d72`, `00464d78`) and the level, -100 on a
    casting phase. `00464b43` reads no hand slot (no `+0x120` or `+0x150` in
    its listing). Its item tests count the row's UseItem `+0x14` (looked up
    at `00465543`, counted at `00465626`) and the `+0x24` kinds 1–4 (ids
    379059000–379062000, `00465673`). The magic packet's one hand read
    (`00463d19`, `00463d4c` in `004630a6`) feeds the staff damage term of
    the AI request and refuses nothing.
  - Local asset (the player's 1298 `Texts_us.tbl`): 4002 "Casting failed",
    3004 "Skill Failed - Not enough MP", 4003 "You cannot user this
    Skill/Magic. ", 4005 "Skill Failed - Improper item". Moradon's rows have
    NeedSkill 2040, a priest's (group 3, `0057faaa`), need item 9 (no weapon
    test) and cast times 19 and 15.
- **Selected:**
  - The skill policy gains N3K5: N3K4 with, after the failed line, 1–8
    refusal lines. Each line has a status (`[a-z][a-z_]{0,31}`, one line per
    status, never `out_of_range`, which keeps the failed line), a target
    kind (0 any, 1 a player, 2 an NPC, as the client saw the target when it
    sent the skill), a text bounded as the notice is, with one `%s` for the
    skill's label, and a colour (alpha not 0). Both readers bound them. The
    server keeps nothing of them, and its refusals are unchanged.
  - The client posts a line only when the server's first answer to a skill
    it sent (its acceptance) is a refusal with that status, on a matching
    target. It posts at most one line per action. A refusal after the
    acceptance posts no refusal line: there 1298 meets Ebenezer's code 0,
    which posts nothing, or no refusal at all. `out_of_range` keeps D-235's
    failed line at every stage.
  - `tools/assetc/ko_skills.py` cooks Moradon's five lines from the
    player's texts:
    - `wrong_class` → 4003, `0xffffff00`;
    - `insufficient_resource` → 3004, `0xffffff00`;
    - `weapon_required` → 4005, `0xffffff00`;
    - `level_required` → 4002, `0xffff3b3b`;
    - `target_dead` on an NPC → 4002, `0xffff3b3b`.
    The first three are 1298's own refusals before it sends. The last two
    are Ebenezer's -100 to a casting phase: 1298 has no level test, and it
    sends a cast on a target it still sees alive.
  - The client does not send a target-2 (NPC) skill on a target it sees
    dead, and posts nothing, as 1298's skill start returns for a type-7 row
    on a target in state 4 or 5. So the server's `target_dead` at the
    acceptance means the NPC died on the server first, where 1298 meets
    -100. The hint is skipped by an unchecked press, as D-234's is.
  - No line, as in 1298:
    - `target_dead` on a player (Ebenezer drops it silently, `0046e94e`);
    - `invalid_target` (from n3e's client only a target-2 skill on a
      player, which 1298 refuses silently through `006164c0`);
    - `actor_dead`, `stale_target` and `cooldown` (1298 refuses these
      silently before it sends);
    - n3e's own refusals.
- **Rejected inference (item part 2):** n3e's `weapon_required` at the
  impact does not correspond to Ebenezer's item-count tests. Those count
  consumed items (UseItem and the `+0x24` kinds), not the hands. 1298 tests
  the weapon kind only at its skill start, and Ebenezer has no hand test in
  `00464b43` or `004630a6`. So a KO cast whose weapon is removed mid-cast is
  not refused, and 1298 posts nothing. n3e refuses it and posts nothing: the
  line matches, the refusal does not (PQ-480; D-244: n3e now tests the
  weapon only at the acceptance). This replaces the
  item-test correspondence that D-236 and D-242 named by inference.
- **Server authority:** unchanged. The server decides every refusal on its
  own state. The client trusts only the status the server sent for a
  sequence number it chose itself and the target kind it recorded itself;
  the texts and colours are package data. The dead-target hint sends less,
  never more.
- **Considered:**
  - The client making 1298's class, MP and weapon tests itself before it
    sends, as D-234's range hint does: not done. It would duplicate server
    rules in the client. It shows the same line, one round trip earlier.
  - Posting "Casting failed" for every acceptance refusal (the item's first
    reading): rejected. 1298 refuses class, MP and weapon itself with its
    own texts, and refuses a dead NPC target silently, so "Casting failed"
    meets only a level refusal or a target that died on the server first.
  - The line from the server (a text or code in `ActionResult`): rejected,
    as in D-235.
- **Limits:**
  - When n3e's server refuses at the acceptance where KO would not (n3e
    checks MP and the weapon at the acceptance; Ebenezer checks MP only at
    the effecting), the race case differs. Example: the MP is enough in
    1298's view but not on the server. 1298 casts, then meets code 0 and
    posts nothing; n3e posts the MP line.
  - Whether 1298's skill window lets a player press a skill above its
    level was not read. n3e's client keeps its own "Requires level N"
    notice before sending (PQ-481).
  - The check order differs (PQ-481).
  - The text 1298 posts for a warrior's or rogue's MP refusal (no text
    loaded) was not read. Moradon's class is a priest.
  - `0057f7f0`'s other local refusals (item counts `0x1db6`–`0x1db9`, the
    exhaust item `0xfa7`, obstacles `0xfaa`, `0x1dea`, `0x1de2`, and the
    class-digit lookup that posts `0xfa2` in `0xffff3b3b`) have no n3e
    counterpart and were not mapped.
  - n3e's `wrong_class` cannot occur with a cooked package (a skill's class
    is the policy's archetype). Moradon's skills need no weapon.
  - Address scans are of the named functions' listings only. No rig
    capture was made.
- **Amends:** D-242's Considered (the second line is added), and D-236's and
  D-242's `weapon_required` inference (rejected; PQ-480).
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-244 — 2026-10-30 A skill's weapon is tested only at its acceptance: a weapon removed during the cast no longer refuses it

- **Context:** PQ-480, queued by PQ-479. Since the skill policy gained
  weapons, `Policy::validate` tested a skill's weapon at the acceptance and
  again on every tick until the impact, so a caster that unequipped its
  weapon mid-cast met `weapon_required` there. D-236 undid the recast of a
  released cast refused that way, by its inferred correspondence with
  Ebenezer's item tests, which D-243 rejected (they count consumed items).
  The item asks first whether 1298 lets a caster change equipment while a
  cast runs.
- **KO reference (binary unless marked):**
  - `KnightOnLine.exe` 1298 (SHA-256 `828ab0db…a5e5`):
    - The need-item test (row `+0x70`, `0057fe54`–`0057fe68`, text `0xfa5`
      at `0057fe8d`) is in the usable check `0057f7f0`. Its only callers are
      the skill start `005819e0` (`005829e2`) and `005596f0` (`0055982c`),
      which sends a phase-3 packet on the player itself (`00583540` at
      `00559868`) with no cast (its role beyond that is not read). Neither
      the release `00584b00` nor the cast tick `00585830` calls `0057f7f0`
      or the slot getter `00578410` (their call lists).
    - The cast tick `00585830` fails a recorded cast (`+0xb04` on the player
      `[00818794]`) only for an action state `+0x2fc` other than 6 or a move
      state `+0x308` not 0 (`005858e0`–`00585944`); it clears a cast whose
      row it cannot find with no packet.
    - The item drop `0049f7c0` (called at `004a0186` and `004a1421`, in code
      Ghidra has not made into functions) sends the item move `0x1f`
      (`00451b80`) for directions 1–4. Its refusals test where the item was
      dropped (`004017b0`), the slots (`004a2250`, `004a1ed0`, `004a2340`,
      a full bag) and, while `004628f0`(`0xa28`, 0) holds, a hand item other
      than a bow (text `0xbda`, local-asset "You cannot equip any other
      weapon other than a bow"). It reads no `+0xb04` and
      no `+0x2fc` and does not call `0057e9a0`, the cast test (state 6,
      `+0xb04` set, or `+0xaf4` 1). A whole-program operand scan finds
      `+0xb04` read only in `004665f8` (no function), `004dfb10`,
      `004e0940`, `0057e9a0`, `005819e0`, `00585830`, `0058a720` and
      `005cec10`. `0057e9a0`'s callers are `005cec10`, `005d91f0` and
      `004662bb` (no function). The player reads in `004a0000`–`004a1500`
      are `+0x4ac` only (`004a0016`, `004a0f50`).
    - The move result `005cfa10` updates the stats and calls `004a0460`,
      which equips or unequips through `004a2430` and `004a25a0`. Those call
      the player's vtable `006a4198` (constructor `00465410`, `00465450`):
      `+0x24` `0046a5a0`, `+0x2c` `00467d50`, `+0x30` `00467b30`, `+0x34`
      `0045d5f0`. A breadth-first walk of direct calls from these and
      `005cfa10`, `004a0460`, `004a2430`, `004a25a0` (depth 8, 248
      functions; virtual and computed calls not followed) reaches no store
      to `+0x2fc`, `+0x304` or `+0xb04` and no call to `00583540` or
      `00451b80`.
  - `Ebenezer-official.exe` (SHA-256 `7d83cc28…7bcb`):
    - The item move `004a1aa4` refuses (`0x1f` with result 0 through
      `0044557a`) on `+0x8140` not -1, `+0x89dd`, `+0x89de` not -1,
      `+0x89fc`, `+0x89fd` (`004a1acb`–`004a1b34`), the directions and
      slots, and the item's race and class (`004ad9d9`). Its listing names
      none of the magic packet's stores (`+0x8098` -> `+0x1099`, `+0x8a1c`,
      `+0xd`, `+0x8a74`, `+0x8a78`; PQ-455).
    - The admission `00464b43` reads no hand slot (no `+0x120` or `+0x150`
      in its listing). The magic packet `004630a6` reads the right hand at
      `00463d19` and the left at `00463d4c` for the staff (kind / 10 = 11)
      damage term. A missing hand or another kind writes a zero term
      (`00463e66`, `00463e5b`) and the packet goes on (`00463e6e`). So that
      term follows the hand held at the effecting.
  - So (binary within those scans, no rig): neither 1298 nor Ebenezer
    refuses an item move while a cast runs, the move does not end the cast
    through the paths read, and the need item is tested only at the skill
    start. A KO cast whose weapon is removed mid-cast lands.
- **Selected:**
  - `Policy::validate` tests the weapon only at the acceptance
    (`Range::Start`). Between the acceptance and the impact (`Unchecked`,
    `Hold`) it does not. A cast whose weapon is removed lands and takes its
    cost, before or after its release. A press with no weapon is refused
    `weapon_required` at the acceptance as before, where 1298's skill start
    posts text 4005 (D-243).
  - `weapon_required` leaves D-236's undo list. It can no longer refuse a
    released cast. If it ever did, it would keep the recast like any status
    not named.
- **Server authority:** unchanged. The server tests the weapon on its own
  equipment state at the acceptance and never trusts a client report. The
  impact reads the caster's attributes and resource as they are on the
  server at the impact. n3e's skill damage has no weapon term.
- **Exploit check (BINARY-POLICY):** none found.
  - A removed weapon contributes nothing to the impact. `Skill::damage`
    reads the caster's current attributes (`Player::refresh_stats` after an
    equipment change). Ebenezer's staff term likewise follows the hand held
    at the effecting.
  - A weapon swapped in after the acceptance counts with its own stats.
    That is KO's rule too. The skill's own weapon must still be held when
    each cast is accepted.
  - The swap is an ordinary server-validated bag request, bounded by its
    rate limit. So no deviation is recorded.
- **Considered:**
  - Keeping the recheck as a correction: rejected. No logic bug or exploit
    is shown, and an unmodified 1298 player's cast lands where n3e's was
    refused.
  - Refusing equipment changes while a cast runs: rejected. Neither 1298
    nor Ebenezer does.
- **Limits:**
  - The scans are operand-text sweeps of disassembled code, and the
    call-graph walk follows direct calls only. An access built in a register
    or through a virtual call is missed.
  - The inventory code around `004a0186` and `004a1421` is not in Ghidra
    functions and was read only as a listing around those calls.
  - Whether the equip path's model rebuild (`00467b30` -> `0045c6e0`)
    changes the animation the cast tick's marker test `004689f0` reads was
    not read.
  - The branch at `00463dbf` (a held staff with a failed `00401a0a` lookup)
    jumps to `0046459a`, which was not read.
  - No rig capture was made. Moradon's skills need no weapon, so no Moradon
    play reaches the change.
- **Amends:** D-236's Selected (the `weapon_required` undo is removed) and
  CONTRACTS' D-231 paragraph ("the weapon … checks remain until the
  impact": the weapon only at the acceptance).
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.

## D-245 — 2026-10-30 The client picks a skill's recipient as 1298's skill start does and has no level test; a skill above the player's level does not go on the hotbar

- **Context:** PQ-481, queued by PQ-479 (D-243 Limits). Before a skill press
  n3e's client posted its own "Select an enemy first" for an NPC skill with
  no target and its own "Requires level N" below a skill's level, sending
  nothing for either. A player or self skill fell back to the caster on a
  dead or unseen player. Neither notice has a 1298 counterpart, and D-243
  left open whether 1298's skill window or hotbar keeps a skill above the
  player's level from being pressed.
- **KO reference (`KnightOnLine.exe` 1298, SHA-256 `828ab0db…a5e5`;
  binary unless marked):**
  - The skill start `005819e0` looks its target up with `006163d0(id, 0)`
    (`00582a72`). That returns 0 for an id below 0 or one it holds in
    neither actor map, the player for the player's own id, and otherwise
    the actor with no state test (second argument 0).
  - Type 2 (`00582b68`–`00582c1d`): no actor casts on the player
    (`00582b7b`). An actor the hostility predicate (`0046c560` ->
    `006164c0`) does not accept is cast on after the range check
    (`00582bc1`, `00582bdf`), whatever its state. An accepted one casts on
    the player (`00582c16`).
  - Type 7 (`00582e95`–`00582ec3`): no actor (`00582e97`), state 4 or 5
    (`00582ea3`, `00582eac`) or a target the predicate refuses
    (`00582ebc`) returns 0 (`005834c6`) with no packet and no text. A row
    whose `+0x38` is 113 casts with target -1 before these tests
    (`00582e0f`–`00582e89`, PQ-479).
  - Neither the skill start nor its usable check `0057f7f0` compares the
    row's level `+0x60` with the player (PQ-479's scan). `0057f7f0` does
    compare the player's `+0x498` (`005809d6`) with the level bounds of the
    item its row names at `+0x74` (the bytes `+0x64` and `+0x65` of one
    item record, each plus the word `+0x7c` of another, `005809dc`–`005809f6`),
    only for a row with such an item. Moradon's rows have none (local-asset:
    `ko_skills.py` checks column 20 is 0).
  - The skill tree builds its icons in `004e7320` (vtable entry
    `006a58ac`, no Ghidra function; recovered read-only). For a row whose
    `+0x64` % 10 is 0 (`004e7570`–`004e7584`) it passes 0 to `004ea6f0`
    (`004e766d`) when the row's `+0x60` is above the player's `+0x498`
    (`004e7595`), else 1. For `+0x64` % 10 of 5–8 it compares
    the tab's points (`+0xf8`–`+0x104`). `004ea6f0` names an icon passed 0
    `UI\skillicon_enigma.dxt` (`006d54a4`) and any other
    `UI\skillicon_%.2d_%d.dxt` (`006d4b70`).
  - The tree's message handler `004e3120` (vtable entry `006a5884`):
    - On message `0x4000000` over the icon the button went down on, it
      copies the icon to the hotbar only when its name is not the enigma
      name (`004e3ff5`–`004e400c`, the compare `004086d0`).
    - On message `0x40000` with a dragged icon dropped outside the tree
      and on the hotbar (`004017b0` at `004e3877` and `004e3888`), it
      deletes a dragged icon with the enigma name (`004e3895`–`004e38e3` ->
      `004e3933`), else gives it to the slot under the cursor (`004df680`
      -> `004df710`).
    - Neither posts a text. `004e3120` calls no `005819e0` (its call list).
  - `005819e0`'s callers are the hotbar's key press `004e0940`
    (`004e09a2`) and icon use `004dfb10` (`004dfd0f`), and the player tick
    (`00465f9f`, `00466102`, `004661b1`). The two hotbar paths call it with
    the player's target `+0x454` and the slot's row, with no level test.
  - The hotbar restore `004de6f0` restores a saved skill that `004e2ca0`
    finds anywhere in the tree, whatever its icon. So a skill bound before
    it became locked stays pressable.
  - Source-aided: `+0x498` is the player's level, `+0x64` NeedSkill and
    `+0x60` the need level (`ref/ko-src` `UISkillTreeDlg.cpp`
    `InitIconUpdate`, `IsSkillUsable`; `MagicSkillMng.cpp` line 432);
    messages `0x4000000` and `0x40000` are the right and left button's
    release.
  - So (inference from the binary): an unmodified 1298 client posts no
    line for a press with no target, and cannot put a basic skill above the
    player's level on its hotbar or cast it from the tree. Only a skill
    bound earlier reaches the skill start, which sends it, and Ebenezer's
    admission answers -100 ("Casting failed", D-243).
  - Local asset: `tools/assetc/ko_skills.py` checks Moradon's rows with
    target type 2 for n3e's kind 1 and 7 for kind 2, NeedSkill 2040 (a
    basic skill).
- **Selected:**
  - The client picks the recipient through `n3e::skill_recipient`
    (`client/render/skill_reach.h`):
    - Kind 1 goes to a player the client sees, whatever its health, and
      otherwise to the caster (no target, an unseen one, an NPC or the
      caster itself).
    - Kind 2 holds the press, with no packet and no line, when there is no
      target. A hinted press is also held when the client does not see the
      target, sees it dead (PQ-479) or sees it is not an NPC, in that
      order. An unchecked press with a target is sent.
    1298's hostility predicate maps onto "an NPC", as the server's target
    category does.
  - The client has no level test before it sends. The server refuses
    `level_required` and the policy's refusal line for it posts (D-243;
    Moradon's is text 4002 "Casting failed").
  - A skill goes on the hotbar only when the player's level is at least
    its level (`Hotbar::bind_skill`, `Hotbar::register_skill`), by drop or
    by the right button. A locked skill changes nothing and posts nothing.
    A skill already bound stays, and its press is sent.
- **Server authority:** unchanged. The holds send less, never more. The
  hotbar test is a local presentation rule. The server checks level,
  target, category and range on its own state whatever the client sent,
  and a dead player target is refused `target_dead` with no line (D-243).
- **Considered:**
  - Keeping "Requires level N" as a client hint, as D-234 keeps the range
    hint: rejected. 1298 sends such a press. Its tree keeps the skill off
    the hotbar instead, so the hotbar test is the matching rule.
  - Posting "Casting failed" locally for a locked press: rejected. The line
    is the server's refusal line, and the server decides.
  - Removing the skill window's double-click cast and drawing a locked
    skill with an enigma icon: not done here; queued as PQ-483.
- **Limits:**
  - 1298 tests a tab skill (`+0x64` % 10 of 5–8) against the tab's points
    and a row's `+0x98` against the tree's `+0xd8`. n3e has neither, and
    tests the level for every skill.
  - 1298's copy also needs the row's `+0x8c` not 0 (`004e401c`), as does
    its drag (`004e3b37`). n3e has no counterpart for that field.
  - 1298 casts a type-2 skill on a non-hostile NPC. n3e's kind 1 goes to
    the caster then, as its server refuses kind 1 on an NPC.
  - A dead player target is sent and refused at the acceptance, so no
    cast is shown. 1298 starts its own cast there and Ebenezer drops it
    silently (`0046e94e`). What the 1298 caster then sees was not read
    (PQ-484).
  - The local check order still differs: 1298 tests its own state, the
    recast, class, MP, HP and need item before the target, and n3e's client
    tests only the target and the range, the rest at the server (PQ-482).
  - The `+0x38` 113 rows have no n3e skill.
  - The scans are of the named functions' listings and call lists. No rig
    capture was made.
- **Amends:** D-243's Limits ("n3e's client keeps its own Requires level N
  notice", "the check order differs": the latter narrowed, PQ-482) and
  D-234's Limits ("the level test still comes before the range test": the
  level test is gone).
- **Recorded in:** `content/skills.md`, CONTRACTS, GAPS ("Magic types"),
  FEATURES KOF-0011, PARITY, BINARY-INDEX, STATUS, the
  evidence record.
