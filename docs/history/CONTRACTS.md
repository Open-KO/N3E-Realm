# Cross-phase contracts

These are cross-phase obligations. Phase 0 has measured experimental implementations for C-02/03/04; Phase 1 now supplies production foundation schemas/modules, documented supported subsets and retained golden fixtures. See the content and protocol READMEs at repository root for exact layouts and bounds. Changes thereafter require a decision record and updates to both producers and consumers.

## C-01: build and content identity

Repository-root Make targets expose `make`/`make client`, `make client TOOLS=1`, `make assets GAME=demo`, and `make test`. Normal/tools builds have distinct caches and binaries. Server builds use a pinned Rust workspace and Compose image. Commands must work without proprietary content or Windows tooling.

A game release identifies `game_id`, `package_version`, `content_schema_version`, engine/protocol compatibility, and a hash over canonical manifest plus dependency hashes. Phase 1 defines a deterministic little-endian release index hashed with SHA-256 and dependencies including a canonical source recipe (content/README.md); raw JSON formatting must not change semantic identity accidentally. A changed required asset changes release identity. Override revisions bind to the base hash. Clients and server reject incompatible releases before world entry. The server verifies package integrity before reporting ready, and nothing silently downloads a missing asset from a legacy server. Each change owns its producer, consumer, package/wire and migration updates together; an incompatible release is rejected explicitly, never left as a broken intermediate format for later integration.

## C-02: coordinates and assets

Measured original-fixture conventions: right-handed, Y-up, meters, local camera forward -Z; CCW front faces; top-left UV/image origin; quaternion x/y/z/w with shortest-arc slerp. Serialized matrices are column-major, acting on column vectors: world = parent × local; skin palette uses joint-world × inverse-bind, followed by explicit instance transform. Normals use inverse transpose and normalization under nonuniform instance scaling. P0-03 numeric tolerance is 1e-6m/components; independent hardware pixel checks allow three byte levels. Do not infer matrix layout from host language defaults. Legacy coordinate/unit conversion remains unverified and must be calibrated in P1-04.

Cooked visuals and collision share source transforms and release identity. Collision is `N3C1` (a triangle soup, at most 196,608 vertices, the encoding of every heightfield up to 129 samples a side that fits it, unless the package has an `N3W2` world) or, since PQ-215, `N3C2` (a native heightfield of up to 513 samples and 4096 m a side plus object triangles the readers grid at load; always beside an N3W2 world since PQ-235, D-160); the layout is in content/README.md and the choice in [D-158](DECISIONS.md#d-158--2026-10-14-large-maps-carry-their-heightfield-natively-in-n3c2-the-object-grid-is-built-at-load). Authoritative definitions cannot depend on missing cosmetic fallbacks. Parsers reject malformed lengths, nonfinite coordinates, out-of-range indices, path traversal, cycles, and oversized allocations. Phase 1 publishes the supported glTF/KO subset and counts in tools/assetc/SUPPORT.md and content/README.md; unsupported features produce explicit diagnostics.

## C-03: protocol and identity

Measured framing: unsigned 32-bit network-byte-order payload length followed by one Protobuf envelope, within verified TLS. P0-04 selects 1..65,536-byte inbound and outbound payloads as the initial cap. Certificate chain and hostname verification are mandatory. Validate length before allocation. The spike proves bounded processing with one active peer, no request queue, two-second inactivity timeouts, 10,000 inputs and an eight-second absolute connection deadline. Those serial/lifetime controls remain experimental. P1-02 replaces them with 64 async peers, two-second absolute per-frame/handshake/write deadlines, 100 frames and 1 MiB actual inbound bytes per fixed one-second window, no application queue and independently bounded output; the adverse-peer tests pass against that implementation. Since PQ-427 the server writes one stderr line per session it ends itself (the frame or byte bound, a read or write deadline, a full queue, a failed writer, a lost admission or a failed final save), naming why, at most ten a second; a session the client ends (EOF, reset, broken pipe, TLS failure) gets none. Production gameplay must not inherit an eight-second connection lifetime. Framing works across partial reads and multiple frames per read. Never use native struct layout.

Envelope families: handshake, authentication, character selection, movement input, action request, state snapshot, entity lifecycle, chat, admin request/result, revision update, and typed error. Common identifiers include protocol version, request ID, session generation, entity ID, simulation tick, and revision where applicable. Version/release negotiation precedes world admission; credentials travel only inside verified TLS.

Entity IDs identify a runtime instance and cannot alias a respawned entity while stale requests remain valid. Character/account IDs are durable identities. The server derives actor identity from the authenticated session; it does not trust an actor field supplied by a client. Reconnect increments session generation and invalidates stale writes/connections.

Entity creation precedes any dependent state update, and a despawn invalidates stale targets that name the entity.

Typed errors distinguish malformed/unsupported, unauthenticated, forbidden, conflict, invalid property, restart required, dependency unavailable, and rate limited. Retryable requests carry stable IDs; the same ID with a different payload is rejected. Terminal failures and timeouts must not be represented as success.

## C-04: simulation and durability

One owner mutates each zone. External tasks submit bounded commands and return I/O results. Admission, command ordering, tick advancement, and snapshot publication are explicit. Rendering is independent from simulation tick rate.

Durable operation states are received → validated → pending commit → committed → applied. Pending does not grant spendable rewards or report durable success. A database transaction includes mutation, request result, and necessary audit data. Tick activation is separate; replay/startup reconstructs committed state. Request status resolves a lost acknowledgement.

Simulation revision is monotonic per documented scope. Shared edits compare expected revision inside the committing transaction. Duplicate requests return the previous result; conflicting payload reuse fails. Revert produces a new revision. P0-05 establishes actor-role row locking before realm/revision row locking; revocation locks that same role row. A new mutation checks capability under those locks. Matching actor/payload retries return their existing committed result even after capability revocation, without a new mutation or active-revision regression. Production session identity/authentication must be established before lookup.

Realm ownership uses a Postgres lease/generation; writes verify ownership atomically. A lease-renewal failure stops simulation admission before ownership can expire, and takeover increments generation. P0-05 proves rejection after takeover using database clock_timestamp() and ownership checks under the realm row lock. The tested 3s lease renews around every 400ms; admission expires 2s from successful renewal attempt start, conservatively before DB expiry. Durable transactions lock the realm's `realm_fence` row (`FOR UPDATE`) and then check owner, generation and expiry on the `realm_ownership` lease row without locking it; a takeover locks the fence row before its conditional upsert, so it waits for every open fenced transaction and none commits after it, while renewal and release update the lease row only and never wait behind a durable write of the realm process (the offline `upgrade-progression` command also holds the lease row, D-145) ([D-145](DECISIONS.md#d-145--2026-10-03-the-realm-fence-locks-its-own-row-lease-renewal-never-waits-behind-a-durable-write)). A renewal attempt that only timed out waiting for the lease row (lock timeout, statement timeout or deadlock, now only behind another process's takeover attempt) is retried at once while admission lasts, and no attempt starts after it has ended; a fenced renewal or any other error still ends the process ([D-142](DECISIONS.md#d-142--2026-10-02-a-lease-renewal-that-timed-out-behind-the-realm-row-is-retried-while-admission-lasts)). Start-up retries the conditional takeover until a previous owner's lease runs out, for at most 5s, and never takes over a live lease; admission is measured from the attempt that took ownership ([D-139](DECISIONS.md#d-139--2026-10-02-realm-start-up-waits-out-a-previous-owners-lease-for-up-to-5-s)). Before that, start-up retries a connection Postgres refuses with SQLSTATE 57P03 (starting up, crash recovery, standby) every 100ms for at most 5s; any other connect failure ends start-up at once, and connections after start-up never retry ([D-140](DECISIONS.md#d-140--2026-10-02-postgres-runs-under-an-init-process-realm-start-up-rides-out-57p03-for-up-to-5-s)). The account/checkpoint worker's connection is opened after the start-up connection and before the lease; if it cannot be opened, start-up ends with its error and takes no lease, and a worker that later stops serving (its thread ends or its connection closes) invalidates admission, so the realm exits for restart ([D-141](DECISIONS.md#d-141--2026-10-02-the-accountcheckpoint-worker-connects-before-the-lease-a-worker-that-stops-serving-closes-admission)). The lease-renewal connection is opened after the worker's and also before the lease, so a slow name lookup, connect or handshake delays start-up instead of spending the first 2s admission window; if it cannot be opened, start-up ends with its error and takes no lease ([D-199](DECISIONS.md#d-199--2026-10-22-the-lease-renewal-connection-opens-before-the-lease-like-the-accountcheckpoint-workers)). A renewal attempt that started inside admission and lands after admission closed reopens it until 2 s after that attempt's start, if that is still ahead (its conditional update found the database lease live). The pause before each renewal attempt is the usual 400 ms cut to what is left of admission (at most what is left less 400 ms, and zero when 400 ms or less is left), so after such a landing the next attempt starts before the reopened admission ends; an attempt that took 2 s or more reopens nothing, and the next check finds admission expired and the realm exits. A zero pause follows only an attempt of at least 1.6 s, and no attempt starts once admission has ended ([D-215](DECISIONS.md#d-215--2026-10-25-the-renewal-pause-shortens-to-what-is-left-of-admission-a-late-landing-that-reopened-admission-is-followed-by-the-next-renewal-not-by-the-exit)). The realm logs how long admission was closed, how long it is open and the next pause, or that it stays closed (PQ-414, PQ-415). Database I/O, output I/O, commands and completed results are isolated from the tick with bounded queues and bounded per-tick drains. Phase 1 retains those values on a dedicated postgres worker; actual library expiry/takeover/fencing, database outage and conservative admission checks now have renewed evidence. Later mutation/result/tick integration still requires its own fault tests. Session generations similarly fence delayed per-character writes.

Acknowledged inventory/progression/config/world changes survive restart. Position alone may roll back to its five-second checkpoint. Active NPC/combat state can reset. Redis loss must never erase durable results or grant privileges.

## C-05: property and permission registry

Each editable property specifies key, type, scope, bounds, capability, persistence class, activation policy, and schema version. The server validates the registry; clients use its public projection for inspectors/completion. Secrets and role grants are excluded from the initial registry.

Tools mode enables local draft editing. Shared publication requires `world.edit`; configuration mutation requires `config.edit`; temporary spawn requires `entity.spawn`; inspection requires `server.inspect`; the operator kill of a named NPC requires `entity.kill` (PQ-194). Capabilities derive from the current character and realm/zone scope. All privileged requests revalidate server-side.

The capability projection (`Registry.capabilities`, the character's realm-wide `character_roles` rows) reaches a session in two ways only: the reply to the `registry` admin request the client sends once at session start (`client/network/world.cpp`), and the Registry the server sends just before the final AdminResult of each admin job (`server/src/simulation.rs`; the `pending` AdminResult carries none, and a job that finds the session stale returns an empty one). A role grant or revoke (`n3e-server role`) changes Postgres and the audit and pushes nothing, so a session sees it at its next admin request or its next session; the player build sends no admin request after the first. The client reads the projection for presentation only: the tools terminal's completions, and the NPC info line (PQ-177), which the client draws only while the latest projection holds `server.inspect`. A tools build, a client flag or package data cannot enable the line, and the line shows the entity id every client receives and, for an NPC a `server.inspect` holder traced, the state the server sends only to sessions it leases `server.inspect` (below). As in KO, where the NPC label refresh `00465070` stops setting the line when the local authority byte is not 0 but never clears it, a line already shown stays after a revocation until the NPC's label is dropped (its lifetime rule, death, leaving view or a new session) ([D-146](DECISIONS.md#d-146--2026-10-10-the-npc-info-line-follows-the-projected-serverinspect-the-projection-refreshes-only-when-a-registry-arrives)).

The NPC state trace (PQ-186, [D-147](DECISIONS.md#d-147--2026-10-10-the-npc-state-trace-reports-the-servers-npc-behavior-to-leased-serverinspect-sessions-in-range)): the admin operation `trace` with `AdminRequest.entity` (field 10) requires `server.inspect`, checked in the admin worker against the authenticated, session-fenced character's roles (`denied`, `invalid_target` for 0 or an id above `i64::MAX`); it is read-only (no durable result, no audit row). The simulation then marks the entity if it is an NPC it holds (`traced`; `unknown_target`, `stale_session`, or `trace_limit` beyond 32 marks or 8 per session). A mark lasts for the NPC's life: when the NPC takes a new entity id (an encounter reset after damage, a respawn) it moves to the new id; it ends only when the NPC leaves the simulation (a temporary NPC expiring) or the server stops. Marks outlive the marking session and cannot be removed, so marks on NPCs that never leave can fill the 32 until a restart. Each World snapshot (every 2 ticks) of a session whose `server.inspect` lease is current carries `World.traces` (field 17, `NpcTrace{entity, state}`) for the marked NPCs among that snapshot's entities; `state` is the NPC's behavior word. The lease is the authority read the simulation already runs every 2 ticks off the tick (`turbo::read`, now also reporting `server.inspect`), valid 500 ms after the read and never restored by an older generation, so a revocation or a stalled read stops reports within one lease. A session without the capability never receives `traces`. The client accepts at most 64 traces per snapshot, each naming an NPC of the same snapshot once, with a lower-case word of at most 16 bytes, and keeps the last state per NPC until the NPC leaves its snapshot or the session changes.

The NPC snapshot record (PQ-189, [D-148](DECISIONS.md#d-148--2026-10-10-kos-pursue-npc-snapshot-stays-a-server-side-record-inspect-does-not-return-it)): the admin operation `record` with `AdminRequest.entity` (field 10) requires `server.inspect`, checked in the admin worker against the authenticated, session-fenced character's roles exactly as `trace` is (`denied`, `invalid_target` for 0 or an id above `i64::MAX`, `stale_session`); it is read-only (no durable result, no audit row, so a `status` lookup says `unknown`). The simulation then takes the snapshot on its tick from the NPC it holds (`unknown_target` for an id that is not a held, non-dormant NPC, a player's entity included; `stale_session` when the session changed meanwhile; `record_limit` within 20 ticks of the session's previous record) and hands one line to the blocking pool, which writes it to the server's stderr (the container log) off the tick: `npc record tick=<tick> entity=<id> name="<name>" behavior="<behavior word>" health=<health> max_health=<package npc_health> x=<x> y=<y> z=<z>` (strings escaped, positions to two decimals). The operator's `AdminResult` is `recorded` with its id and status only: no detail, tick, revision or state, so no NPC value reaches any client. The line names no operator (as KO's does not) and, like any log line, is lost if the process ends before the pool writes it; a retried request id is not deduplicated: it writes another line once the session's 20-tick interval has passed, and is `record_limit` inside it.

The operator chat mark (PQ-178, [D-150](DECISIONS.md#d-150--2026-10-10-the-server-marks-an-operators-chat-lines-from-the-serverinspect-lease-the-package-colours-them)): the server sets `Chat.from_operator` (field 5) on a chat line when the sender's `server.inspect` lease (the same authority read) is current, for every receiver of a local line, the sender's own copy included, and on a private line only when the sender is in the recipient's interest area and, since PQ-184, the recipient may see the sender. A request's field 5 is ignored, a session before its first read or after a revocation's read is never marked, and `n3e-server role revoke … server.inspect` (as `movement.turbo`) returns only once the simulation has applied the revocation, so the next line is unmarked. The client never decides who is an operator: it draws a marked line in the package's `names.operator_chat` colour (Package input map) and an unmarked line, or any line without that style, as before.

The operator kill (PQ-194, [D-157](DECISIONS.md#d-157--2026-10-13-kos-operator-damage-overrides-are-not-copied-an-audited-kill-command-gated-by-entitykill-replaces-them)): the admin operation `kill` with `AdminRequest.entity` (field 10) requires `entity.kill`, an individually granted capability (`n3e-server role grant … entity.kill`) that no other capability implies, checked in the admin worker against the authenticated, session-fenced character's roles under the role lock (`denied`; `invalid_target` for 0 or an id above `i64::MAX`; `invalid_reason` for an empty reason or one with control characters; `stale_session`). An authorized request commits its `admin_results` row (status `kill_authorized`, the entity in `detail`) and an `admin_audit` row (target `kill:<entity>`, the request's reason, the current world revision as before and after state, outcome `kill_authorized`) in one transaction; a refused request writes neither. The simulation then applies it on its tick to that session generation (`stale_session` otherwise; `unavailable` while the realm drains for shutdown or the session is leaving, as a strike is refused): `unknown_target` for an id that is not a held NPC or is dormant, `target_dead` for a dead NPC, `target_pending` while a strike on it awaits its durable commit, `kill_limit` within 20 ticks of the session's previous kill, the ledger's `settlement_capacity` or `contributor_capacity` with a progression package, `reward_pending` without one while the operator's legacy reward is pending; otherwise the NPC dies through the ordinary death path and the answer is `killed`. With progression the operator is credited the NPC's remaining health in its contribution ledger and the encounter settles as any kill (`encounter_settlements`; recipients by the package's rules); without it the operator gets the legacy kill reward; corpse and respawn follow the NPC's rules. A refusal changes nothing and does not spend the interval. Only a fresh request kills: the admin worker returns a stored kill authorization as `kill_replayed` (detail cleared) for a retry with the same payload and for a `status` lookup, and the simulation does not act on it, so a stored authorization cannot strike later, after a revocation included; another payload under the same id is `payload_conflict`; a refused kill is retried under a new request id. The audit records the authorization; the outcome reaches only the operator's session. An operator's strike deals ordinary damage: KO's operator damage overrides (AI `004430d8`) are not copied. The tools terminal verb is `kill [NPC_ID]` (it sends the Reason field; with no id, the viewer's current target), offered for completion while the projection holds `entity.kill`.

Operator visibility (PQ-184, [D-152](DECISIONS.md#d-152--2026-10-10-the-server-withholds-an-operator-from-sessions-without-a-current-serverinspect-lease)): a session whose `server.inspect` lease is current is hidden, and the server withholds it from every session whose own `server.inspect` lease is not current. So holders see each other and every session sees itself. The lease is the same authority read. A session's first read is taken before it joins the simulation (off the tick, in its connection task), so an operator is withheld from its first snapshot unless that read's 500 ms lease has lapsed before the simulation admits the session; a session with no applied read is treated as hidden. Withheld from such an observer: the operator's entity in `World.entities`, its id as any entity's `strike_target` or `cast_target` (zeroed in that observer's copy), presentation events naming it as actor or target, and the name and entity lookups the observer makes. Presentation events stay withheld after the operator leaves, takes a new entity id or is shown: the 40-tick event history marks an event's actor or target when it is recorded (if withheld at the latest tick, or admitted withheld since) and at every tick while it is kept (if withheld then), and such an observer gets no marked event except where the marked party is the observer itself. Before each snapshot the server clears from every NPC's and player's strike and cast target a former id of a session withheld at the previous tick that no session holds any more (it left or respawned). The retained state is bounded: the ids withheld now and two marks per kept event (at most 128). A private message to it is refused as to an absent name (`private message recipient unavailable`), a party invitation is `unavailable`, a party removal by name answers `not_member` as for an absent name unless the operator is in the requester's own group (a leader can still remove a hidden member), a friend addition is `unavailable`, friend presence reports it offline with character and entity 0, a skill aimed at its entity is `stale_target`, and these case-folded name matches ignore it (a hidden member of the requester's own group still counts in a party removal). A private line the operator sends to such an observer is never marked (`Chat.from_operator` false). Disclosed, not withheld: its private lines carry its name and entity id; its local lines reach the sessions in its interest area with name, entity id and mark, so receiving one shows a hidden operator is nearby; a party it joins lists it to the members; while its attack on an NPC awaits its durable commit, an observer's attack on that NPC answers `target_pending`; and `World.event_cursor` counts withheld events as it counts events out of range (a gap, no identity or position). A revocation's read or a lapsed lease (500 ms without a read) shows the operator again; `n3e-server role revoke … server.inspect` returns once the simulation has applied it. The wire format is unchanged and the client is not told who is hidden. NPCs (PQ-193) neither pick nor keep a session the server withholds: an NPC chasing or fighting one when it becomes hidden drops it at its next tick and walks home, and does not turn on one that strikes it; the strike still lowers the NPC's health and counts in its contribution ledger, and an NPC strike already awaiting its durable commit still completes. The check is the in-memory lease (no I/O in the tick). A holder's show switch (PQ-192, [D-153](DECISIONS.md#d-153--2026-10-10-a-serverinspect-holder-can-show-itself-to-ordinary-players-for-its-session-show-and-hide)): the admin operations `show` and `hide` need `server.inspect` (`denied` otherwise), authorized off the tick against the authenticated, session-fenced character, and the simulation applies them to that session generation only while its lease is current (`shown` or `hidden`; `denied` when the lease is not current, `stale_session` when the session is gone). They are read-only like `trace`: no durable result, so a status lookup answers `unknown`. While shown, the session is not hidden: every rule above treats it as an ordinary player, NPCs included, and it still sees hidden actors. `hide` marks the event history at once. The flag is per session and in memory: a session starts hidden at each login, and a read that finds no `server.inspect` (a revocation) clears it, so a regrant hides the operator again.

Registry activation policies are next tick, next spawn cycle, or restart required. Persistent responses identify committed revision and eventual applied tick. Temporary operations are explicitly labeled and do not silently survive restart. Local preview state cannot change authoritative collision or inventory.

Any future live balance or stat property needs its own deterministic activation and recovery design; persistent spawn overrides stay separate from reward-definition changes.

## C-06: game boundary

Game packages declare presentation, zones, archetypes, stats, actions, items, progression, and starting state with stable namespaced IDs. Engine systems execute generic supported operations. Phase 3 published the minimum rule vocabulary. The goal is that games differ in package data without changing executable hashes; the two-game proof (former Phase 5) is a dropped goal recorded in ROADMAP.

One Compose realm runs one game package. Separate deployments have separate realm identity/storage scope and configurable ports/project names. Cross-game live migration, arbitrary scripts, and dynamic native plugins are out of scope.


## Phase 2 implementation of C-03/C-04

[D-014](DECISIONS.md#d-014--2026-09-18-bounded-authenticated-multiplayer-defaults)
and wire policy supersede the foundation diagnostic
traffic/readiness behavior above. Authenticated directional inputs advance at 20Hz,
at most one applied per session per tick; one more admitted input is held for the
next tick and a third is refused with code 4 (movement admission,
[D-207](DECISIONS.md#d-207--2026-10-24-movement-admission-holds-one-movement-ahead-one-applied-per-session-per-tick-one-more-held-for-the-next-a-third-refused-amends-d-014));
10Hz full interest baselines encode entity lifecycle atomically. Durable runtime
instance allocation prevents reconnect aliasing. One active session per character,
realm/session fencing and monotonic position sequence protect checkpoint/final saves.
A refusal (`Error`) names the client request it answers in `request`, that
request's Envelope field number, 0 when it answers none; the client shows it on
that feature's status line only, and every refusal stays the server's decision
([D-208](DECISIONS.md#d-208--2026-10-24-a-server-refusal-names-the-request-it-answers-errorrequest-and-the-client-shows-it-on-that-feature-only)).
A Chat, PrivateMessage, Rest or AdminRequest refusal is shown in the world on
the HUD's message line (the package HUD's `combat` text, where the client's own
notices go; a line of its own without a HUD), never on the chat line or a
feature line
([D-209](DECISIONS.md#d-209--2026-10-24-a-chat-whisper-rest-or-admin-refusal-shows-on-the-huds-message-line-not-the-chat-line)).
That line keeps a short log of the newest refusals and client notices, each in
the colour the package HUD's message block (`N3HM`) gives its kind; the client
draws it and sends nothing for it
([D-210](DECISIONS.md#d-210--2026-10-24-the-hud-message-line-keeps-a-short-log-each-line-in-the-colour-the-package-gives-its-kind)).
With the HUD's scroll block (`N3HS`) the line keeps a bounded history of
messages and wrapped lines behind a scroll bar; scrolling is client
presentation only
([D-211](DECISIONS.md#d-211--2026-10-24-the-hud-message-line-scrolls-back-through-a-bounded-history-a-message-dropped-past-the-record-limit-takes-its-wrapped-lines-with-it)).
Checkpoints every 2s, a 2.5s outstanding-write cutoff and a 4s committed-snapshot-age cutoff retain the
five-second position rollback window. Logout success follows final commit.

Redis loss keeps existing sessions alive and blocks new login: each login's own
Redis rate-limit command fails closed, and handshake admission closes after two
failed readiness probes in a row (one probe 300 ms after the previous one ended, 700 ms bound each), not
after one. Redis requests and probes reuse the address the name last resolved to
and look it up again only after a failed request (D-198). A refused handshake is logged with its reason, at most 10 lines
a second (D-198). PG/lease failure
stops admission/ticks and exits for explicit restart; the restarted process waits
out the dead owner's remaining lease (D-139) and rides out Postgres refusing
connections with 57P03 for up to 5s (D-140). An account/checkpoint worker that
cannot connect at start-up, or stops serving later, also stops admission (D-141). The Compose Postgres runs under an
init process with an exec-form health probe, so no orphaned process can be
reaped by the postmaster and read as a crashed backend (D-140). Bounded I/O workers and queues
are documented and exercised by the P2 evidence.
The client predicts/reconciles and interpolates, but only the server's position is
authoritative. This supplies character movement durability, not later reward/admin
request deduplication, role mutation or revision activation guarantees.

## Phase 3 implementation of C-01/C-03/C-04/C-06

[D-015](DECISIONS.md#d-015--2026-09-19-bounded-combat-vocabulary-and-transactional-rewards)
and [gameplay vocabulary](../../content/gameplay.md) define the required hashed
`gameplay.bin`, targeted action validation, transient combat/respawn and durable
inventory/progression. Atomic snapshot baselines include combat state and owner
inventory; respawn replaces runtime identity. Action sequences prevent repeat damage;
server-authored encounter IDs deduplicate transactional reward mutation/result.
Authenticated read-only status queries recover lost acknowledgement. Full inventory
records a terminal result with no partial grant. PG failure pauses simulation and
requires restart; pending items never appear as committed inventory. This does not
supply Phase 4 administrative mutation or property activation behavior.

## Post-Phase-3 local field extension

[D-017](DECISIONS.md#d-017--2026-09-19-playable-local-field-before-tools-phase)
adds optional N3G2 spawn/interest data and a network-play camera/HUD. Legacy N3G1
packages remain supported; the wire, database, authority and reward contracts are
unchanged. See [exact bounds/layout](../../content/gameplay.md#optional-field-extension-n3g2).

The user-requested D-018 follow-up adds an optional **complete** player/HUD asset
set, covered by recipe/dependency/release hashes. C++ validates visual/HUD structure;
Rust verifies the exact release file set, sizes/hashes and authoritative assets.
Old four-file packages remain supported. Animation/HUD events only present replicated
state or submit ordinary action requests; they never grant damage, loot or authority.
See format and bounds.

## KO-01 movement extension

[D-024](DECISIONS.md#d-024--2026-09-19-approved-ko-01-calibration-deviation-and-bounded-movement)
adds optional N3G3 movement policy under explicit engine/protocol 2/2 compatibility.
Old packages retain 1/1. Mode is authenticated bounded intent; package data and the
server tick determine speed/displacement. Matching C++ prediction uses bounded
collision substeps; presentation remains independent. No durable schema or combat
contract changes. Adopted physical scale and synthetic dimensions are an explicitly
user-approved deviation, not verified historical calibration.

## KO-02 presentation extension

Optional N3V1 camera/input data requires engine 3 while retaining protocol 1 or 2
according to gameplay/movement policy. The producer and both readers enforce
compatibility, bounds and release identity; older packages remain supported.
See [camera contract](../../content/camera.md) and D-025. PQ-012 (D-143) adds
N3V2, the N3V1 fields plus the vertical drag axis and the key-pitch and
screen-edge yaw rates; a camera block without them still cooks to N3V1, and both
readers accept either. Existing N3C1 static
collision is also used for client camera obstruction and nearest-surface picking.
No server movement, combat, wire message or durable schema changes.

## KO-03 melee extension

Optional N3M1 requires engine 4 and retains protocol 1/2 based on movement.
[Policy](../../content/melee.md) binds gameplay radii, reach and client facing to
release identity; existing cooldown/cost fields remain authoritative. Zero cost
requires opt-in. Client-owned bounded repeat/approach uses existing authenticated
Action requests, never grants damage, and cancels across identity/input/life
boundaries. The server validates horizontal size-aware range for each opted-in
request. No durable schema or reward change; legacy releases keep old behavior.

## KO-04 damage extension

Optional N3D1 requires engine 5 with existing protocol 1/2 movement selection.
Both readers and producer enforce bounded stats and release identity. Server-owned
RNG follows successful authority validation; hit and miss both consume cooldown
and cost. Additive snapshot results and ActionResult miss never authorize damage.
[Contract](../../content/damage.md), D-027. Durable state/schema, NPC behavior and
reward semantics retain their previous contracts.

## KO-05 NPC extension

Optional hashed N3N1 requires engine 6 and retains wire 1/2 according to movement.
The [NPC contract](../../content/npc.md) defines state/timer bounds, reference
acquisition/retaliation policy and explicit navigation/recovery adaptations.
Both readers and producer reject incompatible/malformed releases. Identity-bound
server targeting, bounded collision work and existing authenticated action checks
preserve C-03/04. No durable schema, reward, privileged spawn or corpse/respawn
policy changes. Older packages retain legacy AI. See D-028.

## KO-06 life extension

Optional N3L1 requires engine 7/wire 3, independent of optional movement/AI policies.
[Life contract](../../content/life.md) and D-029 define authenticated requested
player respawn, explicit life states, independent NPC corpse/respawn deadlines and
snapshot ID replacement. Old packages retain their behavior. Migration 004 commits
requested player death/eligibility/location and respawn
before publication. Reconnect restores committed death with fresh runtime identity.
Lifecycle revisions fence checkpoints; pending rewards continue against durable
character/session identity and cannot overwrite replacement entities. NPC life and
nonlethal HP/resource remain transient. See D-030.

## KO-07 animation extension

[D-031](DECISIONS.md#d-031--2026-09-19-bounded-whole-body-animation-presentation)
adds optional N3A1 under engine 8 and existing wire selection. Both readers verify
bounded metadata, complete file sets and release hashes; C++ checks shared clip
geometry/skeletons and duration before rendering. Local TRS blends and cosmetic
markers never affect authoritative outcomes. See [format](../../content/animation.md).

## KO-08 reward design (not implemented)

[D-032](DECISIONS.md#d-032--2026-09-19-reward-settlement-and-claim-design) and
KO-REWARDS specify a future opt-in policy. One settlement commits
all eligible XP and any promised loot entitlement atomically; separate claim/expiry
transactions record immutable terminal results. Inventory fullness never suppresses
new-policy kill XP. Earned settlement uses character identity across disconnect;
claim admission still fences current session/life. Legacy rewards retain Phase 3
semantics. Forward migration/explicit conversion cannot rewrite old results or
migration checksums. KO-09 remains test-only until KO-10 verifies claims. No runtime
contract is changed by this documentation-only phase.


## KO-09 settlement/progression extension

Optional N3P1 requires engine 9/wire 4 and an explicit disposable test realm.
Migration 005 atomically commits all contribution XP/outcomes and any promised
single-item entitlement, independently of bag capacity. Lifetime and curve XP are
separate; inventory count is not changed. Immutable canonical payload/result
identity, character-bound credit across sessions, realm fencing and revision-only
application preserve C-03/04. Legacy reward families remain distinct; no client
message authorizes settlement. Fixed stats never heal or revive on level change.
[Format, bounds and conversion](../../content/progression.md), D-033,
evidence. KO-10 claims/expiry and ordinary activation
remain unimplemented and gated.

## KO-10 claim/expiry extension

Optional engine10/wire5 retains N3P1 and migration005, adding bounded authenticated
owner discovery and atomic one-item C/E operations. Full bags preserve eligible
kill XP and leave claims retryable. Terminal results are immutable; DB-clock expiry
and realm/session/life fences protect mutation, while owner-only status recovers
history after disconnect/restart. Server-authoritative admission position is
compared to the durable drop on the worker, with no blocking I/O in a tick.
[Exact contract](../../content/loot.md), D-034,
evidence. Engine9/wire4 remains test-only; engine10 can
start normally after explicit offline test-realm conversion. Legacy releases,
results and prior migration checksums remain unchanged. No live conversion or
next-phase demo assembly is implied.

## Phase 4 implementation of C-01/C-03/C-04/C-05

[D-042](DECISIONS.md#d-042--2026-09-20-typed-tools-registry-and-durable-revision-implementation)
and the [editing contract](../../content/editing.md) define engine11/wire6,
hashed N3T1, and additive migration006. Typed request/result/registry messages and
full world revision snapshots implement authenticated publication, expected-revision
conflicts, immutable retries, revert-as-new-revision, and tick activation. A stable
authority row serializes mutations/revocation before realm/session fencing;
operator role changes carry durable generations/audit. Matching result retrieval
remains available after revocation, after current session authentication.

Revisions/results/audit commit atomically on the existing bounded worker; startup
validates the override base and replays before readiness. Full snapshots avoid
out-of-order delta application. Next-cycle definitions are captured per NPC,
without modifying current combat, reward payloads or saved player life. Temporary
NPC authorization is durable but its effect is process-generation-bound and expires.

Both normal/tools clients apply published visuals; only tools clients link local
editor/terminal UI. Local previews never change collision or authoritative state.
Export bakes absolute values into a new release; explicit cosmetic draft rebase
rejects changed authoritative dependencies. A fresh realm begins at revision zero;
incompatible existing realms fail closed. Weather/time and all other accepted
I1–I17 deferrals remain outside the registry. This extends production C-04/05;
historical paragraphs above describe the earlier phases, not current limitations.

## KX exploration and turbo extension (kickoff proposal, historical)

Implemented as engine13/wire7; see the section below for the delivered contract. Proposed at the KX kickoff under [D-043](DECISIONS.md#d-043--2026-09-20-kx-kickoff-and-server-authority-direction);
nothing here is implemented, and every value is provisional until measured.

Terrain and collision. One offline adapter produces the terrain surface, bounded
static scenery and a single collision bake; the C++ client and the Rust server
load the same bake and compare its identity, which participates in the release
hash. Unknown collision becomes a conservative barrier. Any centring translation
is shared by visuals, collision, spawns and saved positions. The accepted scale-1
adoption and `(x,y,z) -> (x,y,-z)` are retained. KO names and paths stay in
adapter and package data, never in engine modules.

Turbo. A `movement.turbo` capability is provisioned through the Phase 4 operator
path and validated against the authenticated character, realm and zone. The client
submits a bounded boolean held intent with session, life and input sequence, and
never a speed, role, destination or elapsed time. The server selects the effective
speed from immutable package policy and publishes effective mode and a permission
generation so prediction, replay and observers resolve to the same authoritative
result. Held intent expires under a bounded server-side input timeout; the
authorization lease fails closed; revocation invalidates the generation before the
next movement admission and is acknowledged only after simulation invalidation is
known applied. New life or session starts false.

Compatibility. The speed bound is a versioned movement extension. Existing 6 m/s
readers reject it explicitly rather than clamping, and an unsupported
speed/package combination is rejected at load. Substep count and per-actor
per-tick collision work are bounded and measured, not enlarged to cover speed.

## Engine 12 static world asset

[D-044](DECISIONS.md#d-044--2026-09-20-engine-12-static-world-asset-and-the-corrected-tile-diagonal)
adds one optional cooked asset, `world.bin`, and retains wire 6 and the engine 11
editing contract. `N3W1` is `magic, atlas width, atlas height, cell, pad, RGBA atlas, vertex count,
{position, normal, uv, uv2, slot, slot2} per vertex, index count, indices`. It is
a package's static visible geometry: never posed, never skinned, uploaded once
and drawn in its own pass against its own atlas. `scene.bin` keeps its existing
meaning as the instanced model a package repeats per entity and per editable
decoration.

The atlas is a grid of `cell`-wide slots whose outer `pad` texels hold the
wrapped opposite edge. A vertex names the slot each of its two layers samples and
carries **cell-local** UVs that may leave `[0, 1]`; the renderer repeats inside
the slot, with gradients taken from the unwrapped UV so the mip level does not
collapse along a seam. Surfaces therefore tile — a wall keeps its brick courses —
without a triangle crossing a tile boundary being torn apart, which is what
per-vertex wrapping into a baked UV does.

Bounds belong to the asset, not to assets in general: 2048² atlas with
power-of-two sides, a cell of at least 8 that fits the atlas, padding of at most
a quarter cell, 196,608 vertices, 589,824 indices (a multiple of three, each
index in range), UVs within ±1024 tiles, integral in-range slots, non-zero
normals, and a 32 MiB file. Every other cooked file keeps the 16 MiB bound. The
manifest key `world` names the package file; it requires the editing contract and
pins `engine_version` to 12. The server verifies presence against the engine
version, checks the magic and size (PQ-231) and hashes the bytes into release
identity, and does not interpret them.
A client without the asset renders exactly as before, so engine 11 packages are
unaffected.

The second UV layer exists because KO terrain composes two tile textures
additively per tile (`CN3TerrainPatch::Render`); the shader adds the two samples
and alpha-tests the first, which also gives imported foliage its cutout. A part
the source marks double-sided (`RF_DOUBLESIDED`, which `CN3SPart::Render` turns
into `D3DCULL_NONE`) is emitted with both faces rather than by switching cull
state mid-pass. Cooked heightfields gain a `"alternating-mirrored"` diagonal for
grids that mirror one of the reference's axes, since mirroring inverts the
quad-split parity as well as the winding.

## Engine 13 exploration and wire 7

[D-047](DECISIONS.md#d-047--2026-09-21-preview-fog-object-lod-and-authorized-turbo)
extends engine 12 with two release-hashed files. Older engine/protocol pairs
remain supported; engine 13 requires wire 7, movement policy and editing.

`exploration.bin` is `N3X1` followed by six little-endian f32 values: turbo
multiplier [1,10], fog start/end (0 <= start < end <= 1000), RGB [0,1]. Values
must be finite. Normal directional speeds retain their existing <=6 m/s bounds.
The package selects the multiplier; a network peer never supplies one.

`world-lod.bin` is `N3L1` or `N3L2`, u32 part count (<=8192), then per part: f32 center[3],
radius [0,2000], positive scale <=1000, u32 flags, u32 level count
(1..65), then each level's f32 distance and u32 count/indices. Distances start
at zero and strictly increase; indices reference `world.bin` vertices. Index
counts are multiples of three, <=589824 per level and <=2000000 overall;
file <=16 MiB. The server hashes presentation bytes; the client validates them.
Flags: bit 0 disables fog; `N3L2` additionally allows bit 1 for mirrored U/V
addressing and bit 2 for radial far-distance sphere culling before the frustum
check. Unknown bits fail closed (`N3L1` permits only bit 0). New cooks use `N3L2`;
legacy data retains repeat and depth/frustum culling. Engine/wire versions remain
13/7; old clients reject new presentation magic.
This changes drawing only: full authoritative collision is unchanged.

### N3L3 progressive world presentation

D-056 adds `N3L3` within engine 13/wire 7. N3L1/N3L2 keep their existing
selection semantics; old clients reject N3L3. New local Moradon cooks use N3L3.
All fields below are little-endian; all floats must be finite, within the common
absolute 1e6 bound. The file retains the 16 MiB and 2,000,000 total-index bounds.

After magic: terrain origin f32[3], patch size f32 [.01,1000], far-plane factor
f32 (0,1], distance-rounding bias f32 [0,1), minimum near-band radius u32 [1,64],
middle-band width u32 [1,64], square patch-grid width u32 [1,256]. Patch X grows
along world +X; patch Z grows along world -Z from the supplied origin. Three
levels use rounded grid distance, the near radius `max(minimum,trunc(far*factor))`,
and a middle band of the supplied width. Coarse variants select refined edges
against neighboring levels, including virtual neighbors beyond the map edge.

Next: parent count u32 [0,8192], then each parent's position f32[3], radial
distance allowance f32 [0,10000], sphere center f32[3], radius f32 [0,10000].
Position-distance and center radial/frustum checks both apply before part checks.

Next: part count and the same part/level layout as N3L2 (center, radius, scale,
flags, level count, distance/count/indices). N3L3 permits flag bit 3 for disabling
backface culling; its indices are single-sided. Each part then carries kind u32:

- Kind 1, progressive object: exactly one level containing the full-capacity
  **minimum-state** index buffer. Follow with parent index, global vertex base,
  minimum vertex count, minimum active index count, maximum vertex count (<=65536),
  control count (<=4096), controls `(f32 metric,u32 vertex budget)`, split count
  (<=65536), split records of six u32s `(index delta,edit count,vertex delta,
  first edit,group flag,collapse target)`, edit count (<=196608), and u32 edit
  positions. Controls strictly increase from a nonnegative metric; budgets lie
  between the vertex bounds. Split totals must reach declared maxima; triangle
  counts, edit positions/ranges/targets, active indices and reversible writes are
  checked at load. Sum of split counts plus referenced edits across all parts
  is <=2,000,000. Dynamic rendering mutates only this part's preallocated indices.
- Kind 2, terrain: exactly 33 levels, then patch X/Z u32. Level entry 0 is full
  detail; entries 1..16 are middle-level edge masks 0..15; entries 17..32 are
  far-level edge masks. Mask bits refine left/+Z/right/-Z edges. Only bit 1
  (value 2, mirrored sampling) is permitted. Every grid patch must occur once.

Object metric is camera distance times projection FOV divided by part scale.
Vertex budgets truncate the signed interpolated change **before** adding the
starting budget. Equality at the last control preserves state. No controls means
maximum detail. Refinement/collapse preserves instance history, finishing grouped
splits; exact-current-budget requests do nothing. This is discrete progressive
topology selected from a continuously evaluated budget, not vertex morphing.

The producer supplies transforms, parent/part bounds and terrain policy. No game
asset names, map IDs or permission decisions enter the runtime LOD module. The
server hashes these presentation bytes and retains full collision geometry.

World texture cells now upload to independent array layers, excluding
padding. Per-part samplers select repeat or mirrored repeat on both layers; each
layer receives its own mip chain. This supersedes the engine 12
atlas-filtering description (the historical cooker actually clamped padding).
The renderer rejects insufficient GPU array-layer capacity explicitly.

Wire 7 Move fields 6/7/8 are held turbo, expected runtime entity and observed
permission generation. Existing session and increasing sequence checks remain.
World fields 11/12 report permission and generation; Entity field 19 reports
active turbo; World.speed reports server-selected directional effective speed.
Old peers cannot enter an engine 13 release. The server binds all permission
checks to its authenticated character, realm and wildcard zone role.

`movement.turbo` uses the existing operator role path. Worker reads carry a
500 ms fail-closed lease measured from dispatch; the simulation applies them
before admitting movement. Role revocation is durable before its observation
barrier and is acknowledged only after the matching session/realm generation
observes it, or becomes inactive. A six-second barrier timeout reports durable
revocation with unconfirmed invalidation; it does not report success. Worker
I/O never blocks the tick. Input is never repeated; active presentation expires
after three ticks without fresh movement (150 ms at 20 Hz).

Client Q must be released after capture/focus/life/session/permission changes
before turbo rearms. Prediction and replay use server permission, matching
entity/generation and immutable policy. Both solvers retain <=0.05 m substeps
and cap work at 61 substeps. Since PQ-215 (D-158) every package's collision,
N3C1 or N3C2, is queried through one gather: the triangles whose padded X/Z
bounds meet the move's reach (distance plus radius, <=4 m), from a 4 m object
grid built at load (a triangle spanning more than 64 cells is scanned on every
query instead) plus the heightfield cells under it. The grid refuses nothing
the format allows; the old index's load-time refusal of exploration packages is
gone. The gathered answers equal the full scan's.

Bridge correction (D-054): movement selects the highest walkable surface at or
below the previous foot height plus the package step limit. It still rejects
support changes beyond that limit in either direction. Higher surfaces are
overhead candidates; the nearest must clear the destination foot height plus
the package body height. Both solvers use the same selection and arithmetic.
Unanchored ground/spawn queries retain their existing highest-surface semantics.
No collision bytes, release format, wire or durable schema changes.

Stair correction (D-055): steep/vertical triangles whose highest point is at or
below destination feet plus the package step limit do not block the body. This
replaces the unrelated 5cm margin so a reachable riser cannot stop the body radius
before the centre reaches the upper support. Higher walls still block; support,
step/drop and overhead-clearance tests remain authoritative and unchanged.

### N3W2 chunked world

[D-159](DECISIONS.md#d-159--2026-10-14-map-sized-worlds-become-a-chunked-streamed-asset-n3w1-stays-for-worlds-that-fit)
and PQ-231 add a second encoding of `world.bin` for worlds that do not fit
`N3W1`. The engine and wire versions are unchanged: an N3W2 world needs an
exploration policy (engine 13 or later) and replaces `world-lod.bin`, which it
must not be paired with; a client that predates it refuses the magic. N3W1 with
N3L1-3 keeps loading and keeps its 32 MiB bound. Little-endian; floats finite
and within the common 1e6 bound.

```text
"N3W2"
u32 texture count [1, 4096]   # PQ-233: world-textures.bin's count; no atlas
f32 grid origin x, z; f32 chunk size [1, 4096]; u32 grid side [1, 64]
u32 terrain [0, 1]; if 1: the N3L3 terrain policy (origin, patch size, far
    factor, bias, minimum, band, width) with N3L3's bounds
u32 chunk count [1, side²]
chunk table, per chunk: u32 x, z (< side); f32 box min[3], max[3] (min <= max);
    u32 body bytes. Strictly increasing z × side + x; the bodies' bytes sum to
    the rest of the file
chunk bodies, in table order, each exactly its byte count:
    u32 vertex count [1, 196608], N3W1's 12-float vertices
    u32 parent count [0, 8192], N3L3 parents
    u32 part count [1, 8192], N3L3 parts
```

Every index, progressive vertex base and parent index in a chunk is
chunk-local. Parts are N3L3's (flags <= 15, kind 1 progressive, kind 2 terrain)
plus kind 0, plain distance levels as N3L1/N3L2 parts are drawn. Kind 2 needs
the terrain policy; patches keep global coordinates, and with a policy every
patch occurs exactly once across all chunks, so neighbour-edge selection never
depends on chunk boundaries. Since PQ-232 a terrain patch (x, z) belongs to the
cell of its patch centre, (origin.x + (x + .5) × patch size, origin.z − (z + .5)
× patch size), computed in double precision from the float32 header values with
`floor((c − grid origin) / chunk size)`: every patch's cell must have a chunk,
and each chunk holds exactly the patches of its cell, which gives coverage and
uniqueness chunk by chunk. A chunk's box contains every part sphere it holds
(checked in double precision); each parent's position and each kind 0 part's
centre lies in the chunk's grid cell, widened by a thousandth of the chunk size
(a kind 1 part lives with its parent). Per chunk: 2,000,000 indices over all
levels (589,824 per level) and 2,000,000 progressive split work, as N3L3 per
file. Totals, checked when a world is loaded whole (`n3e-asset-check`, the
all-resident test path): 4,194,304 vertices, 33,554,432 indices, 65,536 parts,
65,536 parents, 16,777,216 split work; file <= 384 MiB. Trailing bytes are
refused.

The generic writer is `tools/assetc/world_chunks.py`: it takes the world's
texture count, the vertices (each slot an integer below the count) and the
N3L3-shaped parts, parents and optional terrain policy, and puts each part in the cell of its centre (a progressive part in its
parent's, a terrain patch in its patch centre's), copying each chunk's vertices
and keeping a progressive part's range contiguous. The client draws each chunk
from its own vertex and index buffers
and tests the chunk's box against the view planes before its parts; the box
test culls only when every corner is more than 1 cm outside one plane, so it
never hides a part the part's own test would draw. N3W1 loads as one chunk with
no box. The cooker checks the magic and the bound and requires the exploration
policy without `lod`; the server checks the magic, the size (N3W1 <= 32 MiB,
N3W2 <= 384 MiB) and the pairing, hashes the bytes and interprets nothing else.
Collision stays N3C1/N3C2 and authoritative.

**World textures (PQ-233).** An N3W2 world's textures are the release-hashed
`world-textures.bin` (manifest key `world_textures`), present exactly with an
N3W2 world; the N3W2 header's texture count must equal its count, and every
vertex slot is below it. Until PQ-233 N3W2 carried N3W1's atlas header; no
package was published with that layout, so the layout changed in place; a
client or server that predates the change refuses the release (an unlisted
file, `world-textures.bin`). Render
detail's world texture subset applies only to N3W1 worlds.

```text
"N3WT"
u32 texture count [1, 4096]
per texture: u32 level count [1, 12]; per level: u32 width, height [1, 2048],
    powers of two, each level max(1, half) of the one before (N3D1's rule; no
    generated tail), then width × height × 4 RGBA8 bytes
```

Decoded pixels <= 384 MiB; trailing bytes are refused; file <= 8 + 4096 × (4 +
12 × 8) bytes + 384 MiB. Textures with one (width, height, level count) form a
group; each group is split, in texture order, into banks of at most 2048
textures, and at most 8 banks are allowed (the shader's eight `native`
samplers). A texture's slot is `bank × 2048 + layer`, a flat varying (D-058).
The client loads the file whole at start (the levels point into it; one
bank level is copied at a time for upload, then the file is freed), splits
groups at min(`GL_MAX_ARRAY_TEXTURE_LAYERS`, 2048) and refuses, before any
upload, more than 8 banks at that limit (`world textures need N array banks of
at most L layers on this GPU; the client binds 8`) or a texture above
`GL_MAX_TEXTURE_SIZE`; the test client can lower both limits
(`N3E_TEST_WORLD_TEXTURE_LAYERS`, `N3E_TEST_WORLD_TEXTURE_SIZE`). The generic
writer and checker is `tools/assetc/world_textures.py`; the cooker checks the
file as the client does and its count against the world's. The server checks
the magic and the pairing (`world textures compatibility`), hashes the bytes
(read under the file bound) and interprets nothing else. KO reads a zone's
whole colour-map grid at load (`0059eff0`, binary), so loading world textures
whole is KO-like; streaming them has no measured need.

**Alpha parts (PQ-379, D-201).** `world-lod.bin` `N3L4` is N3L3 whose kind 1
parts may set flag bit 4 (16; flags <= 31), and `world.bin` `N3W3` is N3W2
whose kind 0 and kind 1 parts may; a kind 2 part never does (its flags are
exactly 2). After its kind's fields an alpha part carries u32 source and
destination blend [1, 10], u32 state (bit 0 set; no bits beyond `0x1`,
`0x40`, `0x80`, `0x100`, `0x400`) and f32 sort point[3] (finite, within 1e6).
The client leaves an alpha part out of the world pass (its level is chosen
there) and draws it in the effect pass, keyed by the linear eye distance to its
sort point among the effect draws (`effect_draws` external keys, a stable sort,
effects first on a tie): blend on with its factors, depth writes off for
`0x100`, depth test off for `0x400`, the part's fog and culling, no light for
`0x40`, fragments cut at 8-bit texture alpha 0 and the texture's alpha to the
blend. Without `effects.bin` the pass draws the alpha parts alone. Writers keep
N3L3 / N3W2 when no part is an alpha part; old clients refuse the new magic;
the cooker accepts N3L4 and N3W3 by magic, and the server accepts N3W3 as it
accepts N3W2 (magic and size only). No engine number or wire field changes.

**Target marker in the alpha pass (PQ-380, D-214).** The N3TM marker's parts
are external draws of the same pass, after the world's alpha parts in the
external list: each keyed by the linear eye distance to the selected actor's
position plus its pivot at the symbol's horizontal and vertical scale (1298's
part matrix translation, `00443090`), drawn with N3TM's fixed material
(ONE/ONE, depth test and writes, back faces culled). Without `effects.bin` the
pass draws them with the world's alpha parts. No format, engine number, wire
field or server change ([contract](../../content/target-marker.md)).

**Opaque part bits (PQ-382, D-202).** `world-lod.bin` `N3L5` is N3L4 whose kind
0 and kind 1 parts may set flag bit 5 (32, cut at zero: fragments cut only where
the texture's 8-bit alpha is 0, not below one half) and bit 6 (64, unlit);
flags <= 127. `world.bin` `N3W4` is N3W3 with the same bits. Neither bit on an
alpha part (`world alpha part opaque bits`) or a terrain patch (its flags stay
exactly 2). The client draws such a part in the world pass with the world
shader's alpha reference 0 for bit 5 and no light for bit 6; a part without
them keeps the one-half cut and n3e's light. Writers choose the lowest magic
that holds the parts (`world_chunks.layout`); old clients refuse the new magic;
the cooker accepts N3L5 and N3W4 by magic, the server N3W4 as N3W2. No engine
number or wire field changes.

**Single-layer unlit vertices (PQ-388, D-203).** `world.bin` `N3W5` is N3W4
whose vertices may set the second-layer slot (float 11) to -1: the fragment is
the first layer's texel, cut on its alpha as before, with no second layer and
no light (fog still applies). Every other slot names a texture below the
world's count; -1 in the first slot, any other negative value and -1 under an
older magic are refused (`world atlas slot`). The writer chooses N3W5 only
when a vertex carries -1 (`world_chunks.serialize`), so other worlds keep their
bytes; N3W1 and the N3L files cannot carry it, and the KO bake writes a map
with such vertices chunked (`n3w1_refused`). The client keeps -1 through its
native texture remaps (all-resident and streamed). The cooker accepts N3W5 by
magic and the server admits it as N3W2. No engine number or wire field changes.

**Texture sequences (PQ-394, D-212).** `world.bin` `N3W6` is N3W5 whose kind
0 and kind 1 parts may set part flag bit 7, each then followed (after its alpha
record, if any) by u32 frame count [2, 64], f32 fps (finite, (0, 1000]) and a
u32 texture slot per frame (below the world's count); frame k draws its slot
in place of the first-layer slot of the part's vertices, which the writer
requires to carry frame 0's. The client keeps a float32 index per part (0 when
its chunk loads), adds the frame time × fps each frame its world pass draws the
part, restarts at 0 when it reaches the count (remainder dropped) and draws
frame trunc(index), in the world or the alpha pass; the frame time is bounded
to (0.001, 1.0) s, 1/30 s outside. Refused: the bit under an older magic or on
a terrain patch (`world part bounds`), a count outside [2, 64] (`cooked
count`), the fps bound (`world sequence part fps`), a slot at or above the
count (`world sequence part slot`); N3W1 and the N3L files cannot carry it, and
the KO bake writes a map with sequences chunked (`n3w1_refused`). The client
remaps the slots with the vertices' (all-resident and streamed). The cooker
accepts N3W6 by magic and the server admits it as N3W2. No engine number or
wire field changes.

**Terrain overlay maps (PQ-387, D-204).** An optional `world-overlay.bin`
(`N3WO`, manifest `world_overlay`; `tools/assetc/world_overlay.py`) holds
per-block RGBA8 mip chains on the terrain policy's tile grid: header u32
patch_tiles [1, 64], block_tiles (divides it, at most 4 blocks a patch side),
window [0, 2], side (power of two, 4..256), cell (block_tiles · cell = side),
inset (2 · inset < cell), levels [1, log2(side) + 1], width (blocks a side,
= terrain width · patch_tiles / block_tiles), count [1, min(width², 65536)];
then per map u32 bx, bz and its levels, in strictly increasing bz · width + bx
order, nothing after. The window's maps fit one array of at most 256 layers.
The client draws a near terrain patch within `window` patches of the eye's
patch again with its block maps (texel × terrain light, source alpha blend,
depth LEQUAL, alpha 0 dropped; UV in content/world.md). Cooker and client
refuse it without a world, an exploration policy and a terrain policy, or with
a grid that differs from the policy; the server checks magic, a 256 MiB pixel
bound and the world / exploration pairing, and hashes it. The KO bake writes
it from the zone's `.tlt` (Zones.tbl column 5, `ko_light_maps`) when the zone
has a map. No engine number, wire field or world format changes.

**KO bake (PQ-234).** `ko_scene.bake_world` writes N3W1 + N3L3 (N3L4 with alpha parts, PQ-379; N3L5 with opaque part bits, PQ-382) for a KO map
that fits them (Moradon's release hashes are pinned, `tests/ko_bake_pin.py`)
and N3W2 (N3W3 with alpha parts, N3W4 with opaque part bits, N3W5 with single-layer unlit vertices, PQ-388, N3W6 with texture sequences, PQ-394) + N3WT + N3C2 otherwise: above `ko_terrain.MAX_SUPPORTED_SAMPLES`
(129) by the GTD header's sample count, reading the map up to
`CHUNKED_MAX_SAMPLES` (513, the N3C2 bound), or after an N3W1 / N3L3 bound
refuses the build (`ko_lod.WorldTooLarge`, kept as `n3w1_refused` in the
provenance; a texture sequence is refused that way too, PQ-394), or when the build has single-layer unlit vertices (PQ-388). The chunked build (`ko_scene.expand(chunked=True)`) has the same
vertices and parts with a slot table (`ko_scene.Slots`) in place of the atlas;
`ko_scene.world2_bytes` writes 128 m chunks; `ko_scene.world_textures_bytes` writes
each slot's native mip chain (slot 0 the transparent 4 × 4), and render
detail's world subset is then that transparent slot alone. The 129-sample cap
still binds the N3W1 path and the spawn survey.

**Streaming (PQ-232).** The client reads an N3W2 world's header and
chunk table at start (`load_world_index`) and no chunk body; release identity
still hashes the whole file, now in 1 MiB blocks rather than held whole. A
single worker thread (`client/assets/world_stream.{h,cpp}`) reads one body at a
time from the file opened at start and validates it with every per-chunk check
above (`load_world_chunk`; then each vertex slot becomes its world texture's
bank and layer, PQ-233). Each frame the
render thread measures every table box's distance to the eye against the view
reach, `far × sqrt(1 + (aspect × tan(fov/2))² + tan(fov/2)²)` (the far plane's
corner distance; far is the camera far plane with render detail, else the fog
end), and:

- holds the chunks within reach + 128 m, nearest first (ties by table order),
  up to the limits; resident chunks outside that set are evicted (buffers freed);
- requests chunks within reach + 64 m that are not resident or in flight,
  nearest first, while fewer than 8 are in flight and resident plus in flight
  stay within the limits;
- uploads at most 4 finished chunks (at least one, then up to 32 MiB of chunk
  body bytes) and discards finished chunks no longer held.

Limits: 1024 chunks and 256 MiB of chunk-body bytes, counted over resident and
in-flight chunks together and never exceeded; body bytes bound the vertex and
index bytes uploaded. A table entry larger than 256 MiB could never be held: the
stream refuses it at start (`world chunk x,z: larger than the stream byte
limit`), as a bad package, so the nearest chunk to the eye always fits and is
always held. When the chunks in reach do not all fit, the nearest are held up
to the first that does not fit, and none farther; the rest are not drawn. The
client prints one line, in both builds, the first time that happens (`world
streaming: N chunks in reach exceed the client limits ...`); per-frame
`limited` and `missing` counts appear only in the test client's `WORLD_STREAM`
lines (PQ-236 adds a cook-time check). A chunk that fails validation stops the client with
`world chunk x,z: <reason>` when its result reaches the render thread, before
any of it is uploaded, as a bad package does. The worker is stopped and joined
when the viewer exits or unwinds. N3W1 worlds load whole as before. A target marker
on an N3W2 world takes its ground from the package's native heightfield (N3C2,
always cooked beside N3W2), not from resident chunks; one whose collision has
no heightfield is refused (PQ-235, D-160). `n3e-asset-check PACKAGE --marker`
compares that ground with the all-resident terrain parts along a path. The test client adds `N3E_TEST_WORLD_WHOLE` (load every chunk at
start), `N3E_TEST_WORLD_PATH` (a scripted camera path) and per-frame
`WORLD_STREAM` lines; `n3e-asset-check PACKAGE --stream` drives the streamer
without GL.

## Stateful HUD presentation

[D-048](DECISIONS.md#d-048--2026-09-22-hud-controls-preserve-visibility-and-button-state)
extends the optional hashed HUD asset to `N3H2`, retaining `N3H1`. A bounded
parent-before-child table expresses visibility, selection and enabled state;
records reference controls and artwork-state masks. The same visibility rules
must gate rendering and hit testing, including descendants. Disabled regions
block world input without dispatching actions. Package/UIF names stay in the
converter; engine predicates refer only to generic local presentation state.
This does not grant server privileges or add authoritative gameplay states.
Format and bounds.


HUD text follow-up (D-051): optional hashed `N3H3` carries measured fixed-cell
font metrics and single-line/vertical alignment flags. Text origins are calculated
in integer layout coordinates, then viewport-scaled; single-line overflow truncates.
Readers retain H1/H2 behavior. The server's opaque presentation hashing and all
authority boundaries are unchanged. Exact bounds: HUD format.

KX stop correction: optional N3A2 carries exactly seven player clip records in
existing N3A1 record order/encoding, independently of NPC presentation. N3A1
retains eleven records. Both readers reject mismatched/partial sets and invalid
metrics; player clip geometry/duration checks remain. No wire or authoritative
movement change. See [animation contract](../../content/animation.md).

### N3D1 native textures and character detail

Engine14/wire7 requires hashed `render-detail.bin` (128 MiB maximum) alongside
world/exploration/player presentation; older engines reject this addition.
Little-endian layout: magic N3D1; F32 vertical FOV radians/near/far; sixteen F32
thresholds (four increasing rows); three increasing U32 workload boundaries;
U32 world texture subset count and total texture count. Each texture has U32
level count and, per level, U32 width/height followed by width×height×4 RGBA8
bytes. Power-of-two levels halve; at most eight distinct dimension/level banks,
1,024 textures, 12 levels and 112 MiB decoded pixels. No generated mip tail.

F32 character radius and U32 level count (exactly four) follow. A mesh starts
with U32 vertex/index counts, then vertices (position3/normal3/UV2 F32, four U32
joint indices, four F32 weights, U32 texture slot), then U32 indices. Level zero
must be nonempty; lower levels may be empty. Each mesh is bounded at 65,536
vertices/196,608 indices; aggregate bounds are 262,144/786,432.

U32 attachment count (0–16) follows. Each attachment contains a mesh, U32 minimum
vertex/index counts, control count and (F32 metric,U32 budget) controls, split
count and six-U32 split records (index delta, edit count, vertex delta, first edit,
group flag, collapse target), then edit count/U32 offsets. Validate reversible
programs and activated indices at load time; bound aggregate work to two million.
Runtime instances own separate cursors/indices and use the character metric.
Attachments must already be expressed in the packaged skeleton's skin space;
this contract is not a raw historical equipment loader.

The server verifies hash, size, engine pairing and projection header; visual
mesh/texture programs are client-only and are fully validated by the client.
Full-detail collision stays independent and authoritative. Camera projection is
shared by drawing, picking and LOD; legacy packages keep prior projection defaults.

Texture slots are categorical per-triangle values. GPU bank/layer encodings must
use flat varyings; perspective interpolation followed by integer truncation can
cross a bank boundary and sample unrelated pixels (D-058).

## Private message extension

D-059 adds Envelope 31 private intent and server-authored name/private fields to
Chat. Authentication supplies sender identity; the active realm's actor map
supplies the recipient. Private and local chat share rate/length/queue bounds.
A separate envelope ensures older servers reject private intent instead of
broadcasting it. See protocol contract.
No persistence, package, version-negotiation or other channel changes.

## KFC item bag extension

D-060 adds engine15/wire8 N3I1 and migration008. Producer and both readers enforce
bounded, namespaced item/currency definitions and enough bag capacity for existing
reward counts. Authenticated bag requests use revision/source-instance checks and
immutable transaction results. Claims update materialized bags in the same durable
transaction; old aggregate history remains intact. Exact retry snapshots cannot
roll the client back. Full format, authority and compatibility details are in
[the item bag contract](../../content/inventory.md).

D-061 extends the same ledger with engine16/wire9 N3O1 merchant transactions.
Range/alive state is captured by the simulation; DB work stays off the tick and
checks expiration plus durable life/session/realm fences. Money and item changes
commit with the original result. See [merchant contract](../../content/commerce.md).

D-062 adds engine17/wire10 N3J1 repair parameters and repairable definitions.
Bag repair restores durability and debits currency in the same acknowledged
transaction; original retries do not charge again. Independent quote readers
retain the binary's truncation stages. [Repair contract](../../content/repair.md).

D-063 adds engine18/wire11 N3Q1 equipment slots and BagState field6. Schema009
blocks old readers that could erase unknown durable fields. One transaction and
revision covers both containers, including automatic single-item displacement.
Requirements use package base attributes/race/title; no client values establish
eligibility. [Equipment contract](../../content/equipment.md).

D-068 adds engine23/wire16 N3F1 and migration013 directed durable friends with
independent live presence. Item capabilities become optional with explicit reader
dependencies; older engine contracts remain exact. See [friends](../../content/friends.md).

D-069 adds engine24/wire17 N3Z1 ephemeral parties and independent live roster/vitals.
Invitation tokens bind current sessions; authenticated leaders control membership
administration. This does not change durable reward settlement yet. See [parties](../../content/party.md).


## KFC grouped reward extension

N3P2 engine25/wire18 freezes accepted parties and level/eligibility inputs at death,
including zero-damage recipients. Schema014/N3S3 preserves old immutable N3S2
settlements and adds configured weighting/bonus/caps through the existing bounded
database worker. All recipient XP/revisions and outcomes commit together; exact
retries return immutable results. Membership changes after capture cannot change
earned rewards. Existing definitions refuse implicit conversion.
[Encoding, binary evidence and remaining gates](../../content/party-rewards.md).

D-071/schema015 adds an explicit offline, lease-fenced reward-definition transition.
It preserves earned values and immutable history, records full source/target rules,
and atomically adopts the destination world base with unchanged published values.
Pending claims use their original rules; authorized historical editor reverts may
cross only the proven compatible chain. [Upgrade contract](../../content/reward-upgrades.md).


D-072/N3P3 engine26/wire19 and schema016 add frozen contribution order and private
loot audiences. Current party slots route a singleton item using captured server
life/session/range proofs and durable capacity/weight checks. Recipient inventory,
immutable result and rotation cursor commit atomically; no full-bag failure consumes
a drop. ClaimResult fields5/6 identify the recipient. Logout drains admitted claims
and their other-player updates before removing the requester.
[Party loot contract](../../content/party-loot.md).

D-073/N3P4 engine27/wire20 freezes generation in N3S5 and adds schema017 multiple
operations per encounter. Atomic currency claims update every eligible wallet and
immutable recipient outcome together; retries never reroll or repay. Older rows,
payloads and protocol pagination semantics are preserved. New pages use operation
cursors. [Coin contract and remaining integration gates](../../content/coin-loot.md).


## Moradon integration adapter (D-074)

For exploration packages, `gameplay.spawn_x/spawn_z` must have finite collision
ground. New-character creation and both authoritative respawn paths use that
declared location; stored positions are preserved. Other packages retain the
existing generic spawn search. This is package data, not a hardcoded zone rule.

Optional N3H1 bindings `equipment`, `party` and `features` open native controls.
Inventory, service, friend and party actions use the existing bounded authenticated
requests; a visible button or tools build grants no server authority. Text entry
is drawn above open panels and warehouse secrets retain masked prompts. No new
wire format or durable schema is needed for this adapter.

The current local launcher composes engine33/wire26 definitions and original
fixture balance, including verified direct/group N3P5 item drops.
Imported assets, provenance, credentials and captures remain ignored local output.

D-075 adds opt-in N3H4 panel ownership and bounded value/meter/action keys, with
shared draw/hit visibility and modal input ownership. Original UIF imports bind
existing capabilities; input never bypasses server authorization or durable
acknowledgement. D-076 separates window toggles, idempotent tab selection and
panel-owned close actions. H1–H3 remain compatible. [Dialog contract](../../content/dialogs.md).


D-078/N3H5 adds bounded package-owned item artwork; D-079/N3H6 adds bounded
character-preview keys/camera parameters and a native item drag capture lifecycle.
Preview/icon data grants no item authority. Drag releases share existing command
construction, identity/revision checks and durable server operations; invalid or
stale captures do not mutate snapshots. [Format and input contract](../../content/dialogs.md).

D-080 adds public equipped cosmetic keys and N3D2 geometry, independent of private
bag data, plus H7 hover tooltips and stable per-operation pickup slots. Rendering
and grants share committed server state. [Appearance](../../content/appearance.md),
[item drops](../../content/item-drops.md), [UI](../../content/dialogs.md).


D-081 adds [N3E1 authoritative rest](../../content/rest.md), wire23 Rest45 and
Entity.sitting21, plus complete N3A3 sit/idle/stand animation metadata. Health and
resource recovery use bounded package rows and current derived maxima. Posture
remains ephemeral and cannot revive. Right-click equipment reuses existing durable
operations; bag op1 now merges compatible stacks with conserved overflow before
falling back to whole-record swapping. [Inventory](../../content/inventory.md),
verification.

D-083 adds [N3A4 combat animation](../../content/combat-animation.md), engine31/wire24.
Entity.combat_style22 follows committed equipment; strike_style23 freezes the
accepted attack's profile through asynchronous durability completion. Both are
public cosmetics; private bag/instance data remains private. Deterministic visual
variants agree between observers and use selected clip timings. No damage, RNG,
reward or durable schema change. KO mappings stay in offline Moradon data.

## Combat intervals, upper-body motion and ordinary consumables (D-085)

D-085 adds package-owned N3A5 intervals/masks and N3X1 recovery policies. Accepted
attacks freeze interval/style/motion across durable wear; replication never trusts
a client interval or movement-animation claim. Root/lower locomotion remains
independent of upper attacks. Clip-rate buffs remain outside this contract.

D-216 (PQ-416) adds the optional [N3RB ranged basic attack](../../content/combat-animation.md#ranged-basic-attacks-n3rb)
on N3A5 profiles, with no engine or wire change: the server checks a strike under
a ranged profile (selected from committed equipment) against both melee radii
summed plus the profile's range in 3-D and never marks it moving; the client
never chases under it. The client sends intent only; range, interval, hostility
and damage stay the server's.

D-217 (PQ-420) adds the N3RC layout of that file: a cast time per profile. The
server holds a shot under it from its acceptance (`strike_tick`,
`strike_sequence`, `strike_result` `casting`) and lands it through the ordinary
hit path when the profile's one attack clip, stretched to the cast time,
reaches its first marker, publishing the hit as presentation event kind 6
(`hit`, `request_sequence`); a movement input admitted after the acceptance,
death, a session or life change, a profile change or a lost target cancels it
with no effect and clears the cast. The landing waits while a durable combat
write is pending on the archer or the target, or there is no combat or
settlement capacity, for at most 20 ticks past its landing tick (then
`combat_pending`). The `ActionResult` comes at the landing or the cancel. Clients accept kind 6 only for a profile with a cast time. No engine
or wire version changes.

D-218 (PQ-421) adds the [N3RD layout](../../content/combat-animation.md#ammunition-n3rd):
a ranged profile may name an inventory item (durability 0) and a count each
shot needs, with the client's ammo notice; a package that names one carries
the wear policy. The server refuses a shot without that count in the first
bag slot holding the item (`no_ammo`), at the acceptance (spending no
interval) and at a held shot's landing (its interval already begun at the
cast start), and removes it in the strike's wear transaction
(`durability_operations`, its payload extended only when ammunition is
present, so earlier events replay unchanged), which is then made for every
such shot; a locked bag with too few commits nothing (`committed` false) and
the strike fails `no_ammo`. A held shot under such a profile starts that
commit one tick before its landing tick, so the hit is still published at the
landing tick when the commit completes within a tick (a slower database delays
it). The client never names or counts the ammunition it uses. No engine, wire or schema version changes.

D-219 (PQ-422) adds the [N3RE layout](../../content/combat-animation.md#skill-hit-n3re):
a ranged profile may carry a type-2 skill hit (hit rate 1–1000, add damage
0–300, add damage plus 0–10000). The server resolves a player's strike on an
NPC under it with KO's type-2 terms (AI `0040d471` -> `00443a34`, HitType 0)
plus the add damage plus, a sum of 0 being a miss; the client sends only the
attack intent and only checks the terms. No engine, wire or schema version
changes.

D-220 (PQ-423) adds the [N3RF layout](../../content/combat-animation.md#cast-effect-n3rf):
a ranged profile with a cast time may carry a cast effect (a clip key of the
package's `effects.bin` with only triangle records, and 1–2 joints). The
client draws it on the caster's joints from the held shot's start event,
turned with the caster's facing, plays its `effect:` sound, and ends it when
the caster's strike fields stop showing the cast; the server only bounds the
fields. Presentation only; no engine, wire or schema version changes.

D-222 (PQ-417) adds the [N3RG layout](../../content/combat-animation.md#flight-n3rg):
a ranged profile with a cast time may carry a flight (a clip key with only
triangle records, a source joint, a speed of 1–1000 m/s, an optional hit clip
and joint and a release audio key). At the landing event the client flies the
clip from the shooter's joint to the target's box, turned to its direction,
ends it where it enters the box and draws the hit clip on the target; the
server only bounds the fields and still resolves the shot at the landing
tick, and no client reports a hit. Presentation only; no engine, wire or
schema version changes.

D-223 (PQ-439) makes the flight's speed a server rule: a held shot under a
profile with a flight is released at its landing tick (no roll, no durable
write; `strike_result` `released`; presentation event kind 7 with the actor,
target, style, request sequence and both positions) and resolves through the
landing path at the release tick plus ceiling(3-D distance between the two
positions / speed × 20) ticks, at most 200. A movement after the release no
longer cancels it; death, a session or life change, another profile and a
lost or dead target do, and a released shot cancelled in flight or refused
at its arrival keeps its `released` strike fields. The archer's next shot may
be held while the arrow flies, also while the archer's own arrival write is
pending; an arrival under a newer cast leaves the strike fields and interval to
that cast; a release waits for the archer's previous arrow, at most 20 ticks
past its landing tick. The client accepts kind 7 only under a profile with a
flight, launches the flight at it and ends its wait for the shot's result at
the `released` strike fields. The ActionResult still comes at the
resolution; no client reports a hit. No engine, wire or schema version
changes (kind 7 is a new value of the existing field, as kind 6 was).

D-224 (PQ-444) moves a flight profile's ammunition to the release: under a
profile with a flight that names ammunition, the release makes a durable
write of its own (D-218's `durability_operations` event with no wear records,
mode 1, damage 0; no roll) that removes the count from the first bag slot
holding the item, and the release (kind 7, `released`) follows its commit.
The release waits for the archer's own pending durable combat write (at most
20 ticks past its landing tick); an in-memory shortfall refuses it `no_ammo`
without a write; a locked bag with too few (`committed` false) fails the shot
`no_ammo` with no release, the cast cleared; a write error fails the session
as every combat write's. A shot cancelled after that commit has spent its
ammunition. The arrival then neither checks nor removes ammunition, has no
lead tick, and commits only the wear. The client is unchanged. No engine,
wire or schema version changes.

D-226 (PQ-445) is client presentation only: the archer's own client launches
its held shot's flight at its predicted release (the local send time plus the
stretched attack clip's entry blend and first marker), pending until the
server's kind-7 event with the shot's request sequence confirms it; that event
then launches no second flight. A pending flight's hit clip waits for the
confirmation; a shot whose result is a refusal or cancel, or whose local
attempt is forgotten (death, a skill cast, a session change), ends the pending
flight and drops its held hit and its launch sounds; a hit or miss result
confirms it. Observers still launch at kind 7. The client sends nothing new
and the server is unchanged. No engine, wire or schema version changes.

D-227 (PQ-447) lets a skill (`Action` naming a skill) and rest (`Rest`) be
accepted while the archer's released shot is in flight; a held shot, the
archer's own pending durable combat write and the other existing conditions
still refuse them (`combat_pending`, `rest_unavailable`). The arrival is
checked and lands as before during the cast or under the seated archer and
changes neither; it keeps its own refusals (since D-228 neither the basic
attack's cost nor a pending reward refuses it, below).
A skill's impact waits, within its cast deadline, for the caster's own
strike's pending wear write (the arrival) or reward before it takes its cost
or applies; an incoming hit's write does not hold it. A hit that commits
once the cast reached its impact stage (cast time over, recast commit
started) rolls no interruption, in every package, as 1298 rolls it only
before the release (`005cec10`); since D-231 the release, below, ends both
the roll and the move cancel. The client is unchanged. No
engine, wire or schema version changes.

D-231 (PQ-455) ends a skill cast at its release: the server tick in which
its cast time (`cast_end`) has ended while the cast still stands, whether or
not the transition to the recast commit must wait for a pending combat
write. Before it a move cancels the cast (`interrupted`) and a hit rolls its
interruption, as before; after it a move does not cancel the cast and a hit
is not rolled. The range is checked until the impact, from the cast's
origin (its release position) to the target's current position, and a cast
on the caster itself is in range (Ebenezer `004c1dbe` measures current
server positions and passes the same id; the caster's position at the
effecting is inferred to be its release position), so a target that
leaves the range before the impact still fails it `out_of_range`. The
session, life, death, target, cost, weapon and deadline checks remain until
the impact (D-244: the weapon only at the acceptance). A move while the recast commit waits on
PostgreSQL therefore no longer cancels it (D-099's drain keeps its leave and
death cases). The client is unchanged. No engine, wire or schema version
changes.

D-232 (PQ-465) changes the skill policy to N3K2: after the archetype and
label it carries the package's reach, f32 `start`, f32 `hold` (each 0–50) and
u32 plane (0 3-D, 1 the ground plane x/z); both readers refuse N3K1, other
values and trailing data. The server accepts a cast while the 3-D distance
to the target is at most the skill's range + both melee radii (0 without
melee rules) + `start` and the hold below passes (1298's client limit
`00583780`, enforced by the server); between the acceptance and the release
it does not check the range; from the release to the impact the distance on
the hold's plane, from the cast's origin, must stay below the range + `hold`
(Ebenezer `004c1dbe`: Range + 15 on the ground plane for Type1 3). A cast on
the caster passes. Moradon: 2, 15, the ground plane (29 m to start, 40 m to
land). The client reads and bounds the reach but does not check a skill's
range. `n3e-server --check-content` prints the reach and radii it loaded.
No engine, wire or schema version changes.

D-234 (PQ-466) adds N3K3: N3K2 with, after the reach, the client's too-far
notice (a string of 1–96 printable ASCII bytes, at most one `%s` and no
other `%`); N3K2 stays valid with no notice, and both readers bound the
notice the same way (the server keeps nothing of it). Before the client
sends a skill on another actor in its view it tests the server's start limit
(the skill's range + the package's melee radii + `start`, 3-D, inclusive)
from its own predicted position; beyond it it sends nothing and posts the
notice, its `%s` replaced by the skill's label; an N3K2 package refuses
silently (no packet, no line). The server's checks and its
`out_of_range` refusal are unchanged and stay authoritative. Moradon's
notice is the player's 1298 text 4009. No engine, wire or schema version
changes.

D-235 (PQ-469) adds N3K4: N3K3 with, after the notice, the client's failed
line (bounded as the notice is) and its colour (u32 ARGB, alpha not 0); a
failed line needs a notice, N3K2 and N3K3 stay valid, and both readers bound
it (the server keeps nothing of it). The client remembers the newest 16
skill actions it sent; when an `ActionResult` for one of them carries
`out_of_range` it posts the failed line, its `%s` replaced by the skill's
label, on the HUD message log in the policy's colour (a log post may carry
its own colour over its kind's), once per action. The client keeps the
newest 32 `ActionResult`s in order so each one is read. The server's
refusal, its recipient (the caster) and the cast end are unchanged.
Moradon's line is the player's 1298 text 4004 in `0xffff3b3b`. No engine,
wire or schema version changes. D-242 (PQ-471) keeps that rule: no other
skill refusal status posts the line (`tests/skills.cpp` pins each one).

D-243 (PQ-479) adds N3K5: N3K4 with, after the failed line, a u32 count
(1–8) of refusal lines, each a status string (`[a-z][a-z_]{0,31}`, one line
per status, never `out_of_range`), a u32 target kind (0 any, 1 a player, 2
an NPC), a text bounded as the notice is and a u32 ARGB colour (alpha not
0). N3K2–N3K4 stay valid with no lines, and both readers bound them the same
way (the server keeps nothing of them). The client records, with each skill
action it sends, whether its target was an NPC in its view. When the
server's first `ActionResult` for that action (its acceptance) is a refusal
with a line's status, on a matching target kind, it posts that line, its
`%s` replaced by the skill's label, in the line's colour, once per action;
later refusals post no refusal line, and `out_of_range` keeps the failed
line. The client also sends no NPC-target (target 2) skill on a target it
sees dead and posts nothing (a hint an unchecked press skips; the server
still refuses `target_dead`). The server's refusals are unchanged.
Moradon's lines are the player's 1298 texts 4003 (`wrong_class`), 3004
(`insufficient_resource`) and 4005 (`weapon_required`) in `0xffffff00`,
and 4002 (`level_required`, and `target_dead` on an NPC) in `0xffff3b3b`.
No engine, wire or schema version changes.

D-244 (PQ-480) tests a skill's weapon only at the acceptance. Between the
acceptance and the impact the server no longer refuses a cast whose weapon
was unequipped: it lands and takes its cost, as in KO (1298 tests the need
item only at its skill start; neither 1298 nor Ebenezer refuses an item
move while a cast runs). A press with no weapon is still refused
`weapon_required` at the acceptance. The impact reads the caster's
attributes as they then are; skill damage has no weapon term. No engine,
wire or schema version changes.

D-245 (PQ-481) changes the client's choices before it sends a skill. A
target-1 skill goes to a player the client sees, whatever its health, and
otherwise to the caster. A target-2 skill with no target is held back, as
is a hinted press on a target the client does not see, sees dead or sees is
not an NPC: no action and no line (this replaces D-243's dead-target hint,
which it includes, and the client's "Select an enemy first"). The client
has no level test before it sends (its "Requires level N" is removed); the
server's `level_required` refusal posts the policy's refusal line. A skill
goes on the hotbar only when the player's level is at least its level; a
skill already bound stays. The server's checks are unchanged and stay
authoritative. No engine, wire, package or schema version changes.

D-236 (PQ-472) changes what a skill refused after its recast commit leaves.
When the refusal is `out_of_range`, `insufficient_resource`, `wrong_class`,
`level_required`, `invalid_target`, or `target_dead` on an NPC (D-244
removed `weapon_required`, which no longer refuses a released cast), the
recovery that drains the commit (D-099) first deletes the
deadline that commit wrote, in the same fenced transaction (realm fence,
the session's online character row locked as the gate locks it), and only
if the row still holds exactly that deadline. The skill is then ready again
both durably and in the live snapshot. `actor_dead`, `target_dead` on a
player, `stale_target`, `stale_session`, a leave, `cast_timeout`,
`skill_unavailable`, the NPC-write refusals and any other status keep the
deadline, as before. A failed fence, commit, undo or recovery leaves the
deadline as written. No engine, wire or schema version changes.

D-237 (PQ-473) records that a skill action inside the skill's live cooldown
is refused `cooldown` at the acceptance, starts no database work and leaves
the deadline unchanged, however often it is repeated; an action at the
deadline tick is accepted. Ebenezer's restart of its reuse window on a
too-early effecting is not applied, because n3e's server gate stands in for
1298's client recast refusal. No engine, wire or schema version changes.
D-241 (PQ-478) records this as a correction of logic bugs in 1298's frame
clock: at ordinary frame times an unmodified client stays outside
Ebenezer's window, but frames of 1 ms or less, a lost device or uneven
delivery can bring it in. The rule above is unchanged.

D-238 (PQ-475) records that a skill is refused for reuse only by its own
deadline: Ebenezer's 15-slot reuse table (`0046dbe2`, which drops a skill
while 15 other skills sit inside its window) is not reproduced, as a
correction of a logic bug, and no slot count is package data. No engine,
wire or schema version changes.

D-239 (PQ-476) records that a skill's durable deadline
(`character_skill_cooldowns.ready_at`) survives logout, reconnect and
character selection, and is read again at session entry (`skills::recover`)
for both admission and the client's recast display. KO's client empties its
recast list on every world entry (MyInfo) and Ebenezer zeroes its reuse slots
at the close, so a KO relog ends every recast early; keeping the deadline is
the correction of that exploit. No engine, wire or schema version changes.

D-240 (PQ-477) records that the same per-skill deadline, which no other
skill's cast touches, is the correction for a skill whose Ebenezer reuse slot
another magic took: KO's room system sends MyInfo during a session
(`004970cb(1)`), which empties 1298's recast list while Ebenezer keeps its
slots, so in KO such a skill is cast early. n3e has no room system; one built
later keeps every skill's deadline, and the recast shown from it, across its
transitions. No engine, wire or schema version changes.

D-228 (PQ-454) moves a held shot's basic attack cost (the gameplay `cost`)
to its release under a ranged profile with a flight: at the release tick,
after the release's holds, an archer below the cost fails
`insufficient_resource` (no write, no release, no arrow spent, its cast
cleared, its interval spent); otherwise the cost is taken, before the
ammunition is checked and written (a `no_ammo` then keeps it). The arrival
neither checks nor takes it. Every held shot's landing waits while the
archer's reward is pending, as for a pending combat write (at most `DEFER`,
then `combat_pending`), instead of refusing `reward_pending`. A profile
without a flight and an unheld strike are unchanged. No engine, wire or
schema version changes.

D-233 (PQ-467) adds the [N3RH layout](../../content/combat-animation.md#hold-n3rh)
of `ranged-attack.bin`: `N3RG` with, per entry after the flight, f32 hold
distance (0: none, else 0.5–200 m) and u32 plane (0 3-D, 1 the ground plane
x/z; 0 without a hold); both readers take all seven layouts and refuse other
values and trailing data. With a hold the server also requires the target
within it (inclusive, from where the archer stands then) at the acceptance,
at the release of a shot with a flight (after the release's waits, before the
cost: `out_of_range` with nothing spent, the cast cleared) and at the landing
or arrival (`out_of_range`, no hit; an arrow and cost spent at the release
stay spent). Between the acceptance and the release the range is not
checked. The client bounds the hold and does not use it. No engine, wire or
schema version changes.

Consumables use migration019 plus the existing immutable bag ledger. Character,
realm/session/life, revision, instance, delay and shared cooldown are validated;
one transaction consumes one item and persists the cooldown/result. Only a fresh
commit can recover current living vitals in the same runtime identity/life. Work
stays outside simulation ticks and grants no combat immunity. Exact retries do
not reapply effects; logout drains pending work. HP/MP retain their existing
ephemeral lifecycle rather than claiming durable healing across a process crash.
[Format/authority](../../content/consumables.md), evidence.

## ES-02–04 presentation and direct skills

Engine34/wire27 adds [cosmetic events, FX and sound](../../content/presentation-events.md)
and [bounded direct skills](../../content/skills.md). Postgres migration20 owns
spell cooldown deadlines; the existing contribution/reward path owns spell kills.
PQ-013 (D-144) lets the audio block carry a positional policy (`N3A2`: listener,
effect start distance with option bounds, cut-off, reference distance); the
client and cooker accept it beside `N3AU`, and the server checks only the file's
presence against the engine version.

## D-095 ordinary local strike presentation

Engine35/wire28 adds output-only accepted request identity to player strikes and
presentation events. Ordinary eligible sends may predict a local swing and swing
sound; all authoritative World values remain untouched. Server completion after
admission/durable wear supplies the identity, hit/miss and outcome. Only confirmed
hits create impact FX/audio. Bounded client reconciliation preserves animation
start, deduplicates swing sound and clears rejected/expired/life/session cosmetics.
No input-supplied timing, damage, style or RNG is trusted; cooldown and economic
transactions are unchanged. [Contract](../../content/presentation-events.md),
evidence.

## D-099 existing item, skill and chest reconciliation

Client item waits match request identity, result family and send-relative sequence;
refreshes do not acknowledge mutations. Exact retries are bounded and preserve the
server's immutable operation contract. Unknown completion releases only the UI wait,
not a claim of rollback or success. Session replacement clears local tracking.

Interrupted skill commits are drained asynchronously and their durable recast deadline
is recovered for live snapshots without applying the cancelled effect or MP cost.
Since D-236 the recovery first deletes that deadline when Ebenezer would have
answered the refusal before its reuse window (above).
Potion spending/cooldown and ephemeral-vitals boundaries remain unchanged.

Optional hashed N3LP controls presentation opening distance; server pickup admission
still uses progression policy and authoritative position. Moradon opens strictly
inside10m, retains3m pickup and the requested20-second durable TTL. No wire/schema
version change. Audit and limits,
[loot format](../../content/loot-visual.md), [item recovery](../../content/inventory.md).

## Test-only simulation tick (PQ-115, D-132)

Production ticks every 50 ms of wall time and has no setting for it. A server
started with `N3E_TEST_TICK_MS=<10..50>`, `N3E_TEST_REALM=disposable` and
`N3E_REALM=test-...` ticks every `N3E_TEST_TICK_MS` ms instead; with the first set
and either of the others missing, every server command exits non-zero before
touching Postgres or Redis. One tick remains 50 ms of game time for every rule.
Durable deadlines that stand for ticks (`characters.respawn_ready_at`,
`character_skill_cooldowns.ready_at`) are written and read at the running tick, so
a realm keeps one tick for its lifetime; a disposable realm restarted at another
tick reads its outstanding deadlines at the new tick. Wall-time bounds (lease,
deadlines, per-second rate limits, TTLs, admission windows, checkpoints) are
unchanged; rate limits counted in ticks (chat, party invitations, friend
presence) follow the tick. `make live` and the gate run at 50 ms;
`LIVE_TICK_MS=25` is a developer opt-in. The
health body ends `tick_ms=<n>`; an accepted test tick logs a
`WARNING: TEST-ONLY TICK SCALE ACTIVE` line. Neither variable appears in
`compose.yaml` or `deploy/`.

## Player and test clients (PQ-006)

Each client build directory produces two executables from one source:
`n3e-client`, the player client, and `n3e-test-client`. Only the test client
(`N3E_HARNESS=1`, `client/harness/`) has the replay, smoke, capture and
automatic-login modes: `--smoke`, `--unsupported`, `--time`, `--capture`,
`--auto-login`, the `--*-smoke` and `--npc-observe` replays, every `N3E_TEST_*`
and `N3E_EDIT_TEST`/`N3E_EDIT_OBSERVE` switch, `N3E_REQUIRE_HARDWARE_GL`, the
60 Hz offscreen pacing and two offscreen-driver rules (PQ-129, D-193): the
relative mouse mode the viewer asks for counts as granted when that driver
refuses it, so a scripted right drag turns the camera, and the window never has
the pointer for edge yaw, since SDL's cursor rests at (0, 0) there. The player client accepts `--connect`, `--ca`,
`--fixed-window` and `--fullscreen` and refuses any other argument; it still reads
the developer `N3E_PROFILE` switch. A replay takes game data from its suite, never
from the client: `N3E_TEST_ITEMS="role=id;..."` names package items by role and
`N3E_TEST_STORAGE_PASSWORD`/`N3E_TEST_STORAGE_REPLACEMENT` carry the warehouse
passwords the suite provisioned. Tests, `make live`, `make live-ko` and the session
tools run the test client; `tests/player_build.py` checks the player client of
each build carries none of the harness. Both clients speak the same protocol and
hold no server authority.

## Package input map (PQ-009, D-136)

A package may declare `input: {"bindings": [...]}`; each binding names an engine
action, 1–4 keys, optional `require`/`forbid` modifier lists (`Shift`, `LeftShift`,
`Ctrl`, `Alt`) and an optional `typing` flag (also fires while a text field has
focus). The cooker (`tools/assetc/input_map.py`) writes `input.bin`: `N3I1`, u32
count (1–128), then per key binding the action and key as length-prefixed ASCII and
u32 require, forbid and flags (bit 0 typing). The vocabularies are
`client/assets/input_names.h` (53 actions, 78 key names; PQ-010 added `cancel` and `Escape`, PQ-011 `attack_pick`, `attack_target` and the mouse gestures `MouseLeft` and `MouseLeftDouble`, PQ-012 `camera_pitch_up` and `camera_pitch_down`) and the cooker's
lists, which `tests/input_map.py` keeps equal. F11, F12 and Grave are
engine-reserved (tools editor, reconnect, tools terminal) and refused. The client
refuses an unknown name, a reserved key, a contradictory modifier, an unknown flag
or a duplicate binding; the server checks only the magic, hashes the file with the
release and otherwise ignores it. Keys are physical positions (SDL scancodes).
Press actions bound to one key run in table order until one accepts the press;
held actions (`move_forward`, `move_backward`, `turn_left`, `turn_right`, `turbo`,
`camera_pitch_up`, `camera_pitch_down`) are read every frame. A release without `input.bin` gets the pre-PQ-009 layout
(plus Esc → `cancel`).
An optional `names: {"shown": bool, "hides": [...]}` (PQ-014) sets the name
display that `names_toggle` flips: `shown` is the state at start and `hides` a
non-empty set of `self`, `players`, `npcs`. A table with `names` cooks as `N3I2`:
the `N3I1` layout followed by one u32 (bit 0 shown, bits 1–3 self, players,
NPCs); the client refuses other bits or an empty class set, the server accepts
either magic. Without `names` (N3I1, or no table) every name is shown and the
toggle hides every class. The state is per session; nothing persists it.
`names` may carry `lifetime: {"from": "self"|"camera", "acquire": m, "release":
m, "exempt": [...]}` (PQ-169): other players' labels exist from the first frame
their 3-D distance to the measuring point is below `acquire` until the first
frame it is above `release` (`exempt` classes, now only `party`, at any range).
`0 < acquire <= release <= 1000`, finite. A table with a lifetime cooks as `N3I3`:
the `N3I2` layout followed by u32 from (0 self, 1 camera), f32 acquire, f32
release and u32 exempt (bit 0 party); the client refuses anything else, the
server accepts the magic. Without a lifetime every other player keeps a label.
`names` may carry `party: {"while_hidden": bool, "beyond_distance": bool,
"color": 0xRRGGBB}` (PQ-166; `color` optional) for other players in the local
player's party: `while_hidden` keeps their names drawn while the toggle hides
other players, `beyond_distance` lifts the nameplate style's camera `distance`
for them, and `color` replaces the other-player colour. The colour is the one
taken at the label's last refresh: with a lifetime, every frame the label is
exempt or inside `acquire`; the end of the local player's party (its group
changes) refreshes every label; without a lifetime it follows membership. A
table with `party` cooks as `N3I4`: the `N3I2` layout, u32 1 and the `N3I3`
lifetime record (or u32 0 without a lifetime), then u32 flags (bit 0
while_hidden, bit 1 beyond_distance, bit 2 colour set) and u32 colour (at most
0xFFFFFF, 0 when unset); the client refuses anything else, the server accepts the
magic. Tables without `party` keep their N3I1–N3I3 layout.
`names` may carry `distance: {"self"|"players"|"npcs": m, ...}` (PQ-173): a
camera distance limit per name class that replaces the nameplate style's
`distance` for that class (party members with `beyond_distance` still skip it).
Non-empty, known classes, finite `0 < m <= 1000`. A table with `distance` cooks
as `N3I5`: the `N3I2` layout, u32 0/1 and the `N3I3` lifetime record when 1,
u32 0/1 and the `N3I4` party record (flags, colour) when 1, then u32 class mask
(bit 0 self, bit 1 other players, bit 2 NPCs; at least one) and one f32 per set
bit in that order; the client refuses anything else, the server accepts the
magic. Tables without `distance` keep their N3I1–N3I4 layout.
`names` may carry `npc_lifetime: {"from": "self"|"camera", "acquire": m,
"release": m, "rule": "band"|"beyond", "always": bool, "drop_dead": bool}`
(PQ-174; every field required): NPC labels exist from the first frame an NPC's
3-D distance to the measuring point is below `acquire` (or not a number); `band`
drops them only on a frame where `acquire <= d < release` and keeps them at
`release` or more, `beyond` drops them once `d > release`. `always` keeps every
NPC's label at any range and lifts the camera `distance` for NPCs; `drop_dead`
drops a dead NPC's label once its death clip has played (at once without one)
and makes none while it stays dead. `0 < acquire <= release <= 1000`, finite. A
table with `npc_lifetime` cooks as `N3I6`: the `N3I5` layout with a class mask
that may be 0 (then no limits), followed by u32 from (0 self, 1 camera), f32
acquire, f32 release and u32 flags (bit 0 band, bit 1 always, bit 2
drop_dead); the client refuses anything else, the server accepts the magic.
Without `npc_lifetime` every NPC keeps a label. Tables without it keep their
N3I1–N3I5 layout.
`names` may carry `npc_info: {"color": 0xRRGGBB, "text": "...{id}..."}`
(PQ-177; both required): the operator info line drawn above an NPC's name in
the NPC font, the style's gap plus the font's height above the name and centred
on it, after the name and with the same black outline. The client replaces the
one `{id}` with the NPC's entity id and an optional single state placeholder
(PQ-186), `{state}` or `{state:FALLBACK}` (FALLBACK 1–16 printable ASCII bytes
without a brace), with the last state the server reported for that NPC in
`World.traces` (C-05), or with FALLBACK (empty for `{state}`) when none was
reported. The KO table writes `{state:0}`. It sets the line at each label refresh
(every frame that takes the acquire branch, or every frame without
`npc_lifetime`) while the projected capability set holds `server.inspect`
(C-05), never clears it on a later refresh, and drops it with the label. `text`
is 1–64 printable ASCII bytes with exactly one `{id}`, at most one state
placeholder and no other brace. A table with `npc_info` cooks as `N3I7`: the `N3I5` layout with a class mask that
may be 0, u32 0/1 and the `N3I6` NPC lifetime record when 1, then u32 colour
(at most 0xFFFFFF) and the text (u32 length, bytes); the client refuses anything
else, the server accepts the magic. Tables without it keep their N3I1–N3I6
layout. Without H9 nameplates (the H1–H8 fallback labels) the line is drawn in
the fallback alphabet one text line above the label.
`names` may carry `operator_chat: {"color": 0xRRGGBB}` (PQ-178; the colour is
required and nothing else is allowed): the colour of a chat line the server
marked as an operator's (`Chat.from_operator`, C-05), used in place of the chat
text's colour (keeping its alpha byte) in the package HUD's `chat` text and the
fallback HUD. The KO table writes `0xCD9BFF` (KO's `0xffcd9bff`). It styles a
marked line and cannot mark one; without it a marked line looks like any other.
A table with `operator_chat` cooks as `N3I8`: the `N3I7` layout with a u32 0/1
before the NPC info line (present when 1), then the u32 colour (at most
0xFFFFFF); the client refuses anything else, the server accepts the magic.
Tables without it keep their N3I1–N3I7 layout.
Login, character selection and text editing stay engine keys: before the player is
in the world Esc quits, and while a text field or prompt has focus Esc ends it.
`cancel` (PQ-010) closes the front-most open dialog window (inventory, character,
skills, help, shop, warehouse), one per press, as its close button would; the
order is the order the windows were opened (`client/render/window_stack.h`). The
party list, minimap and loot window are not closed, and combat, movement and the
target are untouched. Every action
sends only the intent the old keys sent (move direction and mode, melee or action
request, target selection is local); no protocol change.
Mouse gestures (PQ-011) bind press actions only and never take the typing flag
(cooker and client refuse otherwise). `MouseLeft` fires on a left press in the
world after the ordinary click (pick, select, walk or loot) and acts on that
click's pick; `MouseLeftDouble` fires on the left release that completes a double
click (within 500 ms of the previous left release, under 6 px on each axis) when
the pointer is over the world. `attack_pick` (Ctrl+click in the KO and demo
packages) and `attack_target` (double click) send the attack toggle's intent: the
client starts its melee intent when the target is attackable (walking first,
when out of reach, until strictly inside the reach measured in 3-D), or walks
to a non-attackable actor and stops on that same arrival; the server validates every attack
request (reach, hostility, life) as before. The click pick set is every entity
in the snapshot except the player's own.

## Package actor pick policy (PQ-146, D-138)

A package may declare `pick: {"box": "joints" | "vertices", "min_extent": m,
"pad": p, "mesh_lod": l}` (`0 ≤ m, p ≤ 4`, `0 ≤ l ≤ 3`). The cooker
(`tools/assetc/pick.py`) writes `pick.bin`: `N3PK`, u32 box source (0 vertices,
1 joints), f32 min_extent, f32 pad, u32 mesh_lod. The client refuses a bad
source, bound, length or magic; the server checks the same, hashes the file with
the release and otherwise ignores it. A release without it behaves as
`{"box": "vertices", "min_extent": 0, "pad": 0, "mesh_lod": 3}`.
The client's actor pick (`client/render/pick_attack.h`) casts the ray from the
camera eye through the cursor (`Orbit::ray`) at the actors drawn in the previous
frame. Each actor model's box is axis-aligned in model space over its joint
positions (`joints`) or skinned vertices (`vertices`; also the fallback for a
model without joints), in the idle clip's first frame, or in the death clip's
last frame once a dead actor's death clip has played; each axis shorter than
`min_extent` grows by `pad` on each side; the box is scaled, turned and placed
as the model is drawn. Candidates are the pick set's actors drawn at LOD 0–3
(render-detail LOD, else 0) whose box the ray enters through a front face at
t ≥ 0, ordered by distance from the eye to the actor's position. One candidate
wins; with several, the first wins that is coarser than `mesh_lod` or whose drawn
triangles (body parts, not attachments) the ray hits; otherwise nothing. The KO
package (`games/moradon/pick.json`) uses `joints`, 0.5, 0.25, 1; the demo package
`vertices`, 0.5, 0.25, 1. The pick is client presentation: no protocol change,
and the server validates every request a pick leads to as before.

## NPC templates (PQ-249, D-162)

Engine 37 / wire 30 admits the N3N3 NPC policy
([content/npc.md](../../content/npc.md#template-table-n3n3-engine-37--wire-30)): a
bounded table of up to 256 templates, one named by each reference slot. The server
applies the slot's template to that NPC's instance rules; every NPC path (AI,
damage both ways, regeneration, death and respawn, rewards, party rewards, drop
level, operator record, editor spawns) reads them. Older engine/wire pairs and
N3N1/N3N2 packages are unchanged; older readers reject `N3N3` and engine 37.

Wire: output-only `Entity.looks` (31, a package rule ID) and `Entity.max_health`
(32), set only for an NPC spawned from a template; both default empty, so earlier
golden bytes are unchanged. `golden-template.hex` pins them in both languages. The
client never sends them and never decides anything from them but presentation
(the target bar's maximum).

Durable data: a templated encounter's settlement payload (`encounter_settlements.
payload`, digest beside it) ends with `N3T1`, u32 level (1–255 since PQ-251;
1–10 before), u32 XP (0–50,000,000 since PQ-252; 1–1,000,000 before); the server recomputes and checks every award
against those values and the realm's unchanged reward definition. Untemplated
payloads are unchanged. The level lift needs no table, column or migration change: payloads are
stored and compared, never re-parsed, so stored level 1–10 payloads stay valid
(the credit bound below does need migration 022).

PQ-251 (D-164) lifted the template bounds without a layout or version change:
health 1–2,000,000, level 1–255, speed 0–12 m/s, attack and search ranges up to
64 m, in the cooker, both readers, the N3T1 payload and party rewards (member
levels stay 1–10). An older reader refuses a package past the old bounds.
Encounter credit (damage dealt) is bounded at 100,000,000 per recipient and in
total (`progression::CREDIT_LIMIT`; was 100,000) in the settlement payload,
party rewards, party loot and `encounter_recipients.credit` (migration
`deploy/022-npc-credit.sql`, widening the check only; stored rows stay valid);
the ledger stops counting at the bound. A
chase or return faster than 3 m/s takes ⌈speed / 3⌉ solver substeps of at most
0.15 m. `tools/assetc/ko_npc.py` cooks templates from the operator's KO rows
([content/npc.md](../../content/npc.md#ko-reference-templates-pq-251)).

PQ-252 (D-165) cooks the combat columns too (`iExp`, `sDamage`, `sAc`,
`sHitRate`, `sEvadeRate`) and lifts their template bounds without a layout or
version change: XP 0–50,000,000, damage 0–100,000, defence, accuracy and
evasion 0–32,767 (attack stays 0–10,000), in the cooker, both readers, the N3T1
payload (XP 0–50,000,000) and party awards. A settlement row's XP is bounded at
90,000,000 solo and 214,748,364 in a party (was 1,800,000 and 13,200,000) in
the payload and in `encounter_recipients.awarded_xp` (migration
`deploy/023-npc-xp.sql`, widening the check only; stored rows stay valid).

PQ-253 (D-166) adds engine 38 with wire 30 (no wire change): an N3N3 package
carries `npc-looks.bin` (N3LK) and one `npc-looks-<i>.bin` (N3NM) per entry,
exactly at engine 38 and later
([content/npc.md](../../content/npc.md#per-template-presentation-n3lk-engine-38--wire-30)).
The table's keys equal the templates' looks keys; at most 128 entries, 16 MiB
per model, 96 MiB of atlases and 192 MiB of models, checked by the cooker and
both readers; the cooker refuses a release over the readers' 256-file index.
The client draws each NPC with the entry its `Entity.looks` names (its model,
clips, pick boxes and name flag); the server only validates the files.
Engine 37 and older packages are unchanged; older readers reject engine 38.

PQ-265 (D-173) adds engine 39 with wire 30 (no wire change): a looks model may
be `N3MM`, an `N3NM` with an RGBA atlas and render runs (blend factors,
double-sided, unlit, alpha reference) cooked from `N3SM` clips, which
only the looks cooker accepts. A package with an `N3MM` model is engine 39;
one without stays engine 38, byte for byte. The atlas budget counts 4 bytes a
texel for `N3MM`; both readers take `N3MM` only at engine 39 and the client
checks the runs ([render runs](../../content/npc.md#render-runs-n3sm-n3mm-engine-39)).
Older readers reject engine 39.

PQ-283 (D-176) adds engine 40 with wire 30 (no wire change): a looks model may
be `N3NI` or `N3MI`, an `N3NM` or `N3MM` whose vertices may have up to 60
joint influences past their four slots, in an influence table between the
vertices and the indices, cooked from `N3SI` or `N3SJ` clips, which only the
looks cooker accepts. A package with such a model is engine 40; one without
stays engine 39 or 38, byte for byte. Both readers take `N3NI` and `N3MI`
only at engine 40 (atlas budget as `N3NM` and `N3MM`); the client checks the
table and sums every influence
([influence tables](../../content/npc.md#influence-tables-n3si-n3sj-n3ni-n3mi-engine-40)).
Older readers reject engine 40.

PQ-272 (D-179) adds engine 41 with wire 30: an N3N3 template may carry `scale`,
its drawn size in percent (1–1000; KO `sSize`). A policy with any `scale`
cooks as `N3N4` (model 4: N3N3 with a u32 scale after each template's tracing
range, 100 for a template without the key) and needs a looks table; the
package is then engine 41, and every other package cooks byte for byte as
before. Both readers take `N3N4` only at engine 41 and refuse `N3N3` there
([drawn scale](../../content/npc.md#drawn-scale-n3n4-engine-41)). Wire:
output-only `Entity.scale` (33, percent), set only for a templated NPC whose
scale is not 100; 0 means 100, so earlier golden bytes are unchanged and no
wire version changes. The client refuses a scale on a player, on an NPC
without a looks key or above 1000, and scales the NPC's drawn vertices, pick
boxes, effect joints and name height by it; no rule reads it. Older readers
reject engine 41.

## NPC population scale (PQ-250, D-163)

A package carries at most 2,048 spawn points (N3G2/N3G3), one reference slot per
point (N3N2/N3N3), and editing spawn targets below 2,048; server, client and
cooker share the bound, and older readers refuse a package past 32. The editing
table stays at 128 properties: `editing.spawns` names the editable points.

Runtime ids: before the first tick the server reserves one id per spawn plus 256
(Postgres `entity_instances`, batches of at most 1,024); refills ask for half the
population (256 to 1,024) below a quarter of it (at least 128), one at a time,
off the tick. An NPC respawn never takes the last 64 ids, which player work
keeps; a respawn waiting on ids is delayed, never skipped. A failed reservation
or refill closes realm admission, as before.

Views: a World that would pass the 65,536-byte frame keeps the viewer, every
non-entity field and the nearest other entities (planar distance, then id) that
fit; events keep both parties; traces follow kept entities. A view whose viewer
alone cannot fit is not sent and the session is closed. No wire change: a client
already treats a missing id as despawned. The health line adds `tick_max_us`,
`queue_max` (largest of the last 100 ticks), `npcs`, `ids`, `views_trimmed` and
`views_over`.

NPC instance rules share the package tables (spawn list, slot and template
tables, inventory, progression, commerce, skill and other policies) by reference
count; no table is copied per NPC or per respawn.

## Equipped-item effects (PQ-211, D-183)

`effects.bin` may be `N3E2`: N3EF followed by up to 16 effects, each on one N3V1
appearance key, rigid to one skeleton joint, with a texture frame sequence,
blend and flags, up to four textured copies with a shared jitter, a tail box,
up to four looping tail links of a named clip and a carried trace colour
([N3E2](../../content/presentation-events.md#appearance-effects-n3e2)). It is
client presentation only: no engine, wire or server change. The server checks
only that `effects.bin` is allowed (engine 33 and presentation), as before; the
client checks the keys against N3V1 and the joints against the skeleton and
refuses the release otherwise. The client draws the effect on every player it
draws with render detail whose public keys hold the key, so it follows the
server's committed equipment for self and others, and a client-local
`Option.ini` (`[WeaponEffect] EffectVisible`, default 1) turns it off without
any server state. The KO cook fills it from a mapping row's `ko_item`; every
other package cooks byte for byte as before. An effect with no tail links names
no tail clip (an empty string), which the client reads since PQ-339. A key may
be a skeletal plug entry's (N3AT, D-187): since PQ-339 the opt-in `--glow-2233`
cook gives the Azagai grades' keys their 2233 weapon effect, read with the
2233 FX bundle layout from the player's 2145 fx pack
(PQ-339), and since
PQ-341 its tail: a 20 s clip of two 10 s links (the client's N3EF clip bound
rose from 10 s to 20 s; still at most 600 samples) holding the tail's turning
meshes as triangle batches and its particles, one clip both keys name
(PQ-341).
Since PQ-342 (D-189) that package's `effects.bin` is `N3E4`: N3E3 whose glow
list may be empty, followed by 1–64 camera-distance rules on tail clips' particle
batches ([N3E4](../../content/presentation-events.md#tail-particle-distance-rules-n3e4)):
the cook writes every emission of a ruled particle part as a candidate and the
client takes and draws them by the 2233 particle tick's live count at the
camera's distance to each link. Client presentation only: no engine, wire or
server change, and the server does not read the file's magic (only
`tools/assetc/main.py`'s release check, which accepts N3E4, and the client do);
an older client refuses an N3E4 file, as it refused N3E3. Every other package,
the 1298 tails and the N3E2/N3E3 files cook byte for byte as before.
Since PQ-376 (D-200) a package whose effects carry 1298's alpha-list keys has
an `N3E5` `effects.bin`: N3E4 whose rule list may be empty, followed by 1–16
sort records, each on one effect of the file: a sort origin rigid to the
effect's joint and a bias
([N3E5](../../content/presentation-events.md#alpha-sort-records-n3e5)). The
client sorts that effect's copies by the eye distance to the origin moved by
the copy's jitter, plus the bias, and its tail quads one by one by the eye
distance to their first three corners; every key of the effect pass is a
linear eye distance, so an effect without a record keeps its order. Client
presentation only: no engine, wire or server change; `tools/assetc/main.py`'s
release check accepts N3E5 and an older client refuses it. The KO cook writes a
record for every 1298 weapon effect (the plug origin and the FX mesh's y extent),
so the default, classic and 1097 Moradon feature packages and the
`--glow-2233` package change; the 2233 effects carry none.

## Equipment glow (PQ-315, D-184)

`effects.bin` may be `N3E3`: N3E2 whose effect list may be empty, followed by
up to 16 glow records, each on one N3V1 appearance key, with an emissive colour,
a texture modulate (1, 2 or 4) and a steady or pulse wave with its timing
([N3E3](../../content/presentation-events.md#equipment-glow-n3e3)). It is client
presentation only: no engine, wire or server change; the server still projects
the public keys from committed equipment and stays authoritative for them. The
client checks the keys against N3V1 and refuses the release otherwise, and draws
the glow on every player it draws with render detail, on one clock per actor; a
client-local `Option.ini` (`[Addition2233] EquipmentGlow`, default 1) turns it
off. Only the opt-in KO cook `ko_bake.py … --features --glow-2233` writes N3E3,
from the player's own 2145 tables under the 2233 client's rule (a 2233/2145
addition); every other package cooks byte for byte as before. In that package a
row whose artwork the cook replaces also gives its item the replacement's name
and icon (PQ-321), in the package's own `inventory.bin` and HUD item icon map:
ordinary package data that the server's inventory policy loads as it loads any
label, so the server stays authoritative for the item and the wire is unchanged.
The skeletal plug items the same cook adds (PQ-338) take their icon into that
map from the player's 2145 UI pack by the 2233 rule (`009b3fc0`); the HUD file
format is unchanged (the cook decodes the 2145 X8R8G8B8 texture to the same
RGBA texels). Since PQ-337 a glow record on a key that an N3AT plug entry draws
shades that plug's whole model, on the same actor clock and switch (2233 hands
the glow to the plug's inner character, `0042de90`, `00430f40`); the format,
readers and server are unchanged, as a plug key was already an N3V1 key.
Since PQ-319 (D-190) the same cook also adds 2145 armour parts
([2145 armour parts](../../content/appearance.md#2145-armour-parts-pq-319-d-190)):
ordinary package items, each worn only in one package equipment slot (the
glow package adds head, lower body, hands and feet to the five, 9 of the 16
an N3Q1 policy allows), with an N3D2 appearance part from the player's 2145
Item pack and an N3E3 record; the HUD binds the added slots to their
inventory window areas. KO's race and class rules are applied at cook time to
the package's one character profile; the server validates every equip
against the slots and stays authoritative for what is worn. No engine number,
wire field, schema or server rule changes; the realm is per release, so no
stored bag changes shape. Every other package cooks byte for byte as before.
PQ-346 (research) found that under the 2233 rule only reverse upgrade grades
glow (Item_Ext attribute 11/12, column 45); a normal grade, +10 included, gets
no N3E3 record. Since PQ-350 (D-192) the glow package carries normal +10 (no
glow record), reverse +1 and reverse +30 of the Azagai and the Krowaz set,
keeping the Azagai's reverse +10: 15 glow records, within the bound of 16
(`ko_glow_2233.cook` refuses a 17th before the N3E3 writer). Each 2145 item's
inventory label is 2233's tooltip name (`005aa8e0`); since PQ-354 its kind
line from the player's 2145 `Texts_us.tbl` ("(Reverse unique item)", "(Set
item)"), which tells a reverse grade from a normal one of the same name, is
its tooltip head line ([item tooltip heads](#item-tooltip-heads-pq-354-d-194)),
not part of the label (PQ-350 had joined them); the N3I1 label bound (1–64
printable ASCII) is unchanged and the cook refuses a longer one. The glow
package's bag is 56 slots (N3I1 allows 64) so its 20 starting 2145 items fit
beside the progression's reward slots.

PQ-348 (D-191) adds `render-detail.bin` `N3D3`
([part render states](../../content/appearance.md#part-render-states-n3d3-pq-348-d-191)):
N3D2 whose appearance entries each end, after their four geometries, with a
render state of 16 bytes: u32 flags (1 blend, 2 double-sided; nothing else),
f32 alpha reference in [0, 1), u32 source and destination blend factors (the
N3SM run's indices 0–9, both 0 without blend). Both readers take it at the
same engine numbers as N3D2 (29 and up, with appearance keys); the server
reads only its projection, as for N3D2; the client checks the states and
draws each key with its own, for every player it draws with render detail,
in the same draw as the key's N3E3 glow. A package writes N3D3 only when an
appearance part's state is not opaque, so every default package and pin
cooks byte for byte as before; older readers refuse the magic. No engine
number, wire field, schema or server rule changes: what is worn stays the
server's projection. The opt-in `--glow-2233` package is the only N3D3
package today (its five 2145 Krowaz parts blend and are double-sided).

## Attached characters (PQ-328, D-186)

A package with appearance keys may carry `attachments.bin` (`N3AT`) and one
model per entry, `attachment-<i>.bin`, in the NPC looks model formats
([N3AT](../../content/appearance.md#attached-characters-n3at-pq-328)): per
N3V1 key a wearer joint, a scale, a group, an optional flag, an emissive flag,
a modulate, a lit index count and four clips, with the pulse timing, colour and
clock rule in the header; bounded to 16 entries, 16 MiB per model, 32 MiB of
atlas bytes and 64 MiB of models. A package with it is engine 38 at least, as
its models are; no engine number, wire field, server rule or schema changes,
and older readers refuse the new file. The server checks the table and model
headers so both readers accept the same packages, and otherwise ignores them:
which items a character wears in which slot stays the server's, through the
package's equipment slots (a cospre slot is one of them), its equip validation,
the committed bag in Postgres and the appearance keys it projects (wire field
20). The client also checks the joint and the lit count against the player
skeleton and the mesh, draws each attachment on every player it draws with
render detail, and keeps one clock per wearer; a client-local `Option.ini`
(`[Effect] Wing`, default 1) hides the optional ones. No default package
carries N3AT; every package cooks byte for byte as before. Since PQ-359
(D-195) the client lights every N3AT model with its wearer's equipped-part
light (a draw rule; no format change).

PQ-317 (D-187, D-188) adds skeletal plugs to N3AT
([plug entries](../../content/appearance.md#skeletal-plugs-n3at-plug-entries-pq-317)):
an entry with flag bit 2 carries, after its clips, a 3×4 placement and a clip
map of 1–64 rows (a wearer pose state, combat clip or skill animation to a
model slot and a once flag). It is never optional, lit or emissive and does
not advance the wearer's pulse clock (its key's N3E3 glow, when it has one,
shades it since PQ-337: that is the equipment glow, not the N3AT pulse); the
client draws it at wearer frame ×
joint × placement and plays the slot the drawn clip's row names on its own
clock, for every wearer. Both readers check its bounds and rows; the client
also checks the combat and skill ids. An N3D2 appearance may have an empty
mesh only when a plug entry names its key (client). `npc-looks.bin` is now
present exactly when the package is engine 38 or later **and** has NPC
templates (both readers): an engine 38+ package without templates is new, and
every earlier package has templates, so every package reads as before. Such a
package is wire 30 (its template fields stay empty, as for any untemplated
NPC). Older readers refuse flag bit 2 (their entry bound is 3). No wire field,
server rule, schema or migration changes: what is worn stays the server's
equipment and appearance projection. The opt-in `--glow-2233` Moradon package
is engine 39 / wire 30 with three plug entries (the Azagai and its reverse +1
and +10 grades on one plug model, PQ-337; the reverse path, PQ-346); the
default packages cook byte for byte as before.

## Screen post-process (PQ-316, D-185)

A package may carry `postprocess.bin` (`N3PF`, seven f32: threshold, bloom,
exposure, saturation, lift, adaptation rate, blur variance), cooked from the
manifest's `postprocess` record
([N3PF](../../content/presentation-events.md#screen-post-process-n3pf)). It
needs the presentation assets and engine 33. It is client presentation only:
no engine version, wire or server-state change. The server checks the file's
magic, size and bounds (`content::postprocess`), hashes it with the release and
otherwise ignores it; the client refuses the release on the same faults. The
client draws the bloom and tone map over the world, before the HUD, only when
a client-local `Option.ini` (`[Addition2233] HDR`, default 0) turns it on;
the luminance read-back is asynchronous and bounded (three pixel-pack buffers,
never waited on). Only the opt-in KO cook `ko_bake.py … --features
--glow-2233` writes it, from the player's own 2145 `Zones/hdr.n3pp` under the
2233 client's reading (a 2233/2145 addition); every other package cooks byte
for byte as before.

## Item tooltip heads (PQ-354, D-194)

A package may carry `item-heads.bin` (`N3IH`), cooked from the manifest's
`item_heads` record
([N3IH](../../content/inventory.md#item-tooltip-heads-n3ih-pq-354-d-194)): an
optional token (0–32 bytes; printable ASCII 33–126) and up to 64 heads, each
an N3I1 item (defined, named once) with a name colour (0xRRGGBB) and 0–4 lines
of 1–64 printable ASCII bytes with their colours; zero heads only with a token.
It needs engine 33, the presentation assets and `inventory.bin`. It is client
presentation only: no engine version, wire, schema or server-state change.
The server checks it (`content::item_heads`: magic, bounds, items against its
inventory policy), hashes it with the release and otherwise ignores it; the
client refuses the release on the same faults. A tooltip's first line is the
item's label in the head's name colour (yellow, as before, without a head), the
token replaced by the viewer's own character name (the self entity's, used only
when it is a name the server accepts: 1–24 ASCII letters, digits, `_` or `-`;
each occurrence once, left to right, the result at most 128 bytes); the head's
lines follow it, centred like it, in their colours; the other rows are
unchanged. Item names stay package data: the server sends item ids, never a
substituted name. The opt-in KO cook `ko_bake.py … --features
--glow-2233` writes it for its 2145 items, under the 2233 client's tooltip
head (`005aa8e0`, `004aad90`). Since PQ-361 (D-196) the default Moradon
feature cooks (default, classic and 1097 layouts) write it for each item whose
appearance rows name a KO item (`ko_item`; the blade, 120110048) under the
1298 client's head (`004d6320`): the name colour by the Item_Ext attribute,
the kind line for attributes 1–6 in that colour and the white item-type line
unless the item is countable, no token (`tools/assetc/ko_item_heads.py`). The
1298 rule stores the name colour only when the line's text changes
(`004d66f6`); n3e draws each item's own head every time (BINARY-POLICY
"Tooltip name colour correction"). Every other package cooks byte for byte as
before and reads and draws as before.
