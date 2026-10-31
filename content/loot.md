# Single-item loot: engine 10 / wire 5

KO-10 extends the [N3P1 progression policy](progression.md) and accepted
reward contract. The producer accepts
engine10/wire5 with the same hashed progression definition. Engine9/wire4 remains
settlement-only and disposable-test gated. Older readers reject engine10; new
readers retain legacy releases and engine9. Engine10 also requires the existing requested-life asset, so concurrent death/respawn
is fenced durably rather than using legacy transient death. No migration or reinterpretation of
old reward results is introduced; migration 005 reserved all C/E tables.

Normal startup accepts the engine10 profile only in a realm already converted to
its exact definition. Conversion remains explicit, offline, restricted to `test-`
realms and `N3E_TEST_PROGRESSION=disposable`. No automatic live conversion, demo
activation, deployment or release publication occurs. The laboratory can run
without the test environment variable after conversion.

## Wire and identity

Envelope tags 23–27 are `LootList`, `LootPage`, `Claim`, `ClaimResult`, `ClaimStatus`;
see [wire.proto](../protocol/wire.proto). Only wire5 admits them. TLS/authenticated
character selection supplies the actor; IDs and item names grant no authority.

- Discovery returns only the current owner's unexpired available rows, ordered by
  encounter, with `after` keyset cursor, at most 64 entries and an optional next
  cursor. Positions and absolute Unix expiry milliseconds come from durable rows.
  The client polls the first page once per second and replaces its bounded list.
  At most 64 unexpired entitlements can exist for an owner, so this page is complete.
- Claims carry current session, monotonic sequence, expected runtime instance,
  server-created operation and encounter IDs, item and quantity=1. The tick checks
  session/sequence/instance/alive and reserves a claim slot. It freezes authoritative
  position and durable life revision. The worker checks the saved death zone/range
  against this admission snapshot, then fences current session/life under locks.
  Movement after admission cannot change the result. This performs the immutable
  drop comparison outside the tick, avoiding a stale in-memory entitlement cache;
  it implements the same ordered-admission range rule.
- One outstanding claim per character; identical semantic pending requests coalesce,
  conflicting item/encounter/quantity returns `conflict`, a different operation is
  `busy`. A realm semaphore holds at most 64 jobs, including disconnected drains.
  Settlement and claim completions share an eight-per-tick application budget. DB jobs use the existing bounded
  dedicated worker; no SQL or network write waits in the simulation tick.
- `pending`, `busy`, `stale_request`, `stale_session`, `stale_entity`, `not_alive`,
  `out_of_range`, `unknown`, `conflict`, and `inventory_full_not_committed` never
  acknowledge inventory mutation. Full inventory leaves the same claim available.
- Terminal `claimed`/`expired` results contain the immutable historical count and
  progression revision. Owner-only `ClaimStatus` returns history irrespective of
  current life/range. Unknown and other-owner IDs both return `unknown`. A status
  reply is history, not a current inventory snapshot.

Semantic bytes: ASCII `N3C1`, operation/encounter/owner as positive signed-bigint-
bounded u64 little-endian values, item UTF-8 byte length u32 little-endian, item
bytes (1–128), quantity u32 little-endian equal to one. Session, sequence, position,
instance and life revision are admission proofs excluded from semantic identity.
Store and compare canonical bytes as well as SHA-256. The envelope golden is
[golden-claim.hex](../protocol/golden-claim.hex); C++ and Rust outputs are checked
against an independent Python wire encoder.

## Transactions and recovery

C/E use realm ownership → policy → owner character → inventory/progression →
settlement → entitlement locks. The realm lock serializes unique result creation.
Definition, session, life and lease checks precede the final locked DB-clock test.
`clock_timestamp() >= expires_at` chooses expiry, including equality; a claim
admitted before expiry can expire while queued. Locks remain held through commit.
A decision before the deadline may commit just afterward.

C increments the single aggregate item count and progression revision, inserts its
immutable result and changes the entitlement state atomically. It never changes
XP, health or entity identity. E writes an expired result and terminal entitlement,
without count/XP mutation. Full capacity writes neither result nor state. Checked
revision arithmetic rejects overflow. Original schema history triggers remain.

Only known rollback codes retry (40001/40P01/55P03, and 57014 on the realm-fence
lock, D-137; never 25P04), at most three retries with 50/100/200ms backoff
within a two-second transaction-worker budget. Ambiguous commits fail closed;
reconnect/status uses the original ID. Fault injection is process environment only.
Expiry runs one outstanding worker with pages of 64 due rows, ordered by expiry
and encounter; terminal transitions remove rows from the next available-state
page. It does not load history, require an online owner or depend on NPC/Redis
lifetime. Server-down time counts. Discovery hides due rows even before cleanup.

Claim completion reloads committed inventory, applies progression only at a newer
or equal revision and never replaces a newer life/session. Count is monotonic in
this no-spending scope, so an older completion still advances count without
regressing newer XP. Disconnect and shutdown drain pending claims; restart reloads
committed state and discovers saved drops.

## Presentation and limits

In packages that bind it (the demo binds F, D-136) the collect-loot key claims the nearest owned drop; floating text marks its saved location. The
shared overlay shows available count and pending/result feedback. No corpse is
required and no client event grants an item. The two-slot original lab makes full
capacity easy to test. It has fixed stats, a synthetic ten-level curve and guaranteed
one-unit drops. No equipment, item use/spending, inventory dragging, multi-item
loot table, trade, public reassignment or party routing is supported.
