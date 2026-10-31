# Ordinary durability wear (N3U1)

Engine20/wire13 adds package `wear` and requires equipment-derived stats. Binary
layout: N3U1, f64 positive scale<=1, u32 item count (exact equipment coverage),
then each item ID and u32 attack/defense slot masks. Masks must be subsets of the
item's allowed equipment slots. Producer arrays use zero-based slot indices.
All classifications and tuning remain game-package data.

For ordinary positive damage, loss=floor(sqrt(damage*scale)). A zero result does
nothing. Eligible nonzero-durability records are frozen by instance at the hit's
admission. The supplied server004ae6fc uses double0.1; outgoing wear selects the
hands except shield items, incoming wear selects five armor positions and shields
in either hand. Generic masks express this without importing slot/class IDs.
004af09a clamps broken durability to0 and recalculates derived stats. The client
receives committed BagResult snapshots and shows actual durability and ordinary
stat changes; wear cannot be requested through a network BagRequest operation.

Migration010 adds immutable `durability_operations`, keyed by realm and a server
allocated event identity. Canonical N3WE payload: magic, u64 event ID/bag revision/
source entity/tick, u32 mode/damage/record count, then sorted u32 slot and a
length-prefixed ItemStack. At most16 distinct singleton records; damage<=1,000,000,
positive signed-bigint identities and bounded integer revisions. A selected
character/session/realm fence and the current bag definition hash are mandatory.
The wear policy hash extends the composite inventory identity. Existing realms
need explicit compatible data migration; no state reset is automatic.

Wear follows the frozen instance across current bag and equipment slots. Unrelated
bag revisions do not cancel a hit or redirect wear onto replacement gear. Apply the
loss to current durability (including a repair that committed first). A sold or
consumed instance no longer exists and cannot receive wear; never mutate another
character's bag. [Account storage](storage.md) orders deposits after pending wear and guards later
equipment races with the bag revision, while allowing combat during storage I/O.
Future ownership-transfer capabilities must preserve this guarantee. A changed instance definition
or a future bag revision is an error. Increment the bag revision only if durability
actually changes. Record the full immutable original result in the same transaction;
exact retries return it without applying loss again.

Simulation pauses the affected exchange while the bounded database worker commits.
Only finished tasks are polled; ticks never wait on database I/O. Player attacks
retain their damage roll and admission-based cooldown. NPC attacks retain the
resolved damage against the struck equipment. A committed event precedes hit
publication and any resulting kill settlement. Equipment changes cannot cancel a
hit by provoking revision conflicts. Logout and shutdown drain pending wear before
releasing character ownership. A database failure invalidates world admission
without publishing that hit. Reserve encounter/claim capacity before deferred
outgoing damage, and protect reserved NPCs from reset/temporary expiry.

Durability is durable, while ordinary NPC combat state remains ephemeral. A process
crash after wear commits but before hit publication can retain that wear for an
unacknowledged hit; reconnect loads the durable record. It must not replay a hit
against a new NPC incarnation or duplicate a reward. Both before-commit and after-commit process crashes are verified against real PG
and TLS: rollback before commit; exactly one retained wear event after commit,
without a published hit or reward. Full load behavior remains an integration gate.
Verification record.

The current capability covers ordinary melee wear only. Binary negative-damage
armor/shield restoration, explicit-amount calls, mage/recent-spell adjustments,
spell-specific callers, legacy appearance thresholds and signed-overflow domains
remain open fidelity gates. No unsupported branch is classified as permanently
unnecessary. Client attachment/material changes remain separate presentation work.

Native continuous melee keeps its target and normal retry pacing for temporary
combat/target/capacity deferrals. A durable wear wait does not turn a continuing
attack intent off. Fatal/dead/stale target responses still stop it.
