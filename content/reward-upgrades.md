# Preserving reward policy upgrades

Implemented and verified on the active KO completion branch. This is an
operator capability, not a live deployment or a completed catalog milestone.

With the realm stopped, database schema migrated, and both cooked packages available:

```bash
source tools/env.sh
N3E_PACKAGE=/absolute/path/to/new/package N3E_REALM=your-realm \
  target/debug/n3e-server upgrade-progression /absolute/path/to/old/package
```

`DATABASE_URL` selects the durable database. The command verifies both release
packages, acquires the exclusive realm lease and checks the current definition
against the supplied source. A running owner prevents acquisition. The target
must be an N3P2/N3P3/N3P4 party policy; source N3P1 through N3P4 is supported.
Existing party-loot and coin capabilities cannot be removed by this command. Existing lifetime
XP, curve XP, level meaning, original conversion baselines, inventory identity
and counts remain unchanged. Therefore curve ID/thresholds, reward item,
inventory capacity and starting count must match. Curve rebasing, item conversion
and downgrades are separate unsupported operations. All non-reward cooked assets
must be byte-identical. Adding the first party membership policy is permitted;
changing an existing party policy or another capability requires separate migration
work. Recipe/release metadata may change with the new reward definition.

Schema015 adds immutable `reward_policy_upgrades` records containing both complete
bounded policy encodings and their hashes, plus a monotonic activation pointer.
The original `realm_reward_policy` row stays immutable. A new world revision
adopts the destination package hash and keeps every published property value.
Both release hashes and before/after world snapshots are recorded in the same
immutable transition. Old world revisions remain intact; an authorized editor can
revert their values across this verified chain using the usual current revision
and role checks. `active_reward_policy`
resolves either that baseline or the latest committed transition. All current
policy checks/new-character initialization use this view under existing realm
authority. Up to64 transitions per realm are supported; prior destination
definitions cannot be reactivated.

The transition locks the realm and characters, verifies each saved definition,
inserts the immutable transition, advances saved definition/progression revisions,
appends the destination world revision and activates the pointer in one transaction. It never rewrites settlement or
claim history. Concurrent upgrades from one source cannot both succeed. Retrying
the exact completed transition returns its recorded revision without incrementing
character revisions again. A stale source, differing retry or active current
session is rejected.

Old pending loot resolves the immutable source policy stored in the transition.
It keeps its original pickup radius and already-frozen item, quantity and expiry;
already-completed claims keep their original retry result. Current progress still
must match the active definition. Unknown historical definitions fail closed.
This prevents the new package from invalidating an earned item or reinterpreting
its pickup conditions. Grouped loot itself remains a separate feature gap.

The offline operation has a15-second transaction deadline and10-second statement
limit. It extends its locked lease to30 seconds within the transaction; failure
before commit rolls that extension back. A crash after commit may require waiting
for that lease to expire before a new process can acquire ownership. Normal
completion explicitly releases it. Neither SQL nor package reading runs on a
simulation tick. There is no client privilege or network request for upgrades.

Initial conversion still follows the existing test-realm/disposable guard.
This capability upgrades already-converted realms; it does not remove that initial
activation gate. No supplied executable behavior is invented here: this is generic
durable engine lifecycle support for the binary-grounded N3P2 reward extension.

PostgreSQL checks currently pass for preserved XP/baselines/history, old claimed
and pending loot, original-radius retention, current-session/source/rollback/lease
fences, new characters, competing destinations, exact retry, and real process
termination during mutation/before commit/after commit. World-base adoption and authorized historical reverts also pass database checks.
Live TLS restart/claim and normal Wayland/tools X11 native replays also pass, including a
published lighting edit across the transition and new grouped XP after restart.
Legacy loot/progression persistence, backup/restore and authenticated editor
regressions pass; full CPU suite:100 PASS, Rust36 passed/20 ignored database tests.
