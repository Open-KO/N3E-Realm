# Ordinary recovery consumables (N3X1)

Engine33/wire26 adds `consumables` to the package and requires the current
inventory/combat presentation dependencies. Older packages retain their behavior.
The manifest is an array of `{item, health, resource, delay_ms, cooldown_ms}`.

`consumables.bin` contains little-endian `N3X1`, u32 count (1–64), then five u32
values per row: inventory-definition index+1, HP recovery, resource recovery,
activation delay and shared cooldown. IDs must be distinct, reference items with
zero durability, and have positive total recovery. Each recovery is0–100000,
delay0–2000ms, cooldown50–60000ms. Both readers reject missing files, truncation,
trailing data, duplicate references and invalid values.

Wire `BagRequest.operation=9` uses the existing request key, expected bag revision,
source slot and instance. Destination, service, item and quantity must be empty or
zero. The effect always targets the authenticated selected character. The client
uses a registered hotbar shortcut or `/use SLOT` (one-based). Right-clicking a
bag potion registers it on the current hotbar page without consuming it. Tooltips show the
recovery amounts; existing bag status displays `consumed`, `cooldown`,
`use_pending`, `not_usable`, `not_alive` or the existing identity/revision errors.
There is no client HP, MP, effect amount or cooldown claim.

D-090 allows an older expected bag revision for operation9 when the locked current
source still has the exact instance and is usable. Combat wear can advance the
bag revision during activation without changing that potion. Future revisions
remain invalid; moved/removed/replaced sources fail identity checks. Other bag
operations retain their existing revision rules. Regression evidence.

One asynchronous operation per player holds the activation delay outside the
simulation tick. Movement and combat continue; using an item does not grant
invulnerability. PostgreSQL locks/fences the character and bag, checks life,
current source slot/instance and shared cooldown at admission time, then atomically
commits one-item consumption, zero-stack removal, revision, cooldown and the
immutable bag-operation result. Migration019 adds the per-character durable
cooldown. Failures roll back both item and cooldown. Exact retries return the
original result with no new effect; conflicting reuse of a key is rejected.

After a fresh commit, the simulation clamps recovery against current maximum
vitals only for the original entity/life and only while alive. A character dying
while the operation completes is never revived; a replacement life never receives
that effect. Logout/shutdown waits for pending consumption. HP/MP retain the
existing ephemeral lifecycle contract: a process crash can interrupt presentation
of a committed recovery, but never restores the spent item, erases the cooldown or
reapplies the effect on retry. Reconnect does not replay old recovery into a new
entity. This is not a general durable-vitals or spell system.

Moradon maps Water of life to90HP and Potion of spirit to120MP, both with500ms
activation and2000ms shared cooldown after consumption. Full-vital use can consume
an item. [N3H8 hotbar shortcuts/counts/sweeps](hotbar.md) also activate this same operation.
D-092 supplies the supported HP/MP [particle FX and audio](presentation-events.md).
Other potion strengths, cures, buffs and duration effects remain fidelity/support gaps.
D-099 rechecks rollback, concurrent exact retries, combat wear during activation,
cooldown reconnect and life/session fences; the existing authority and ephemeral
vitals contract remains unchanged. Audit.

Binary evidence and verification.
