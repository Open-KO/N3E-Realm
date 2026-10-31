# Editing and administration (engine 11 / wire 6)

Phase 4 adds a bounded editor to the existing single-zone realm. Original
engine1–10 packages remain readable. The demo now opts into engine11/wire6;
its reward definition and original gameplay are unchanged. Engine11 requires
requested life and progression. `editing.bin` is hashed alongside every other
release dependency; old binaries reject this version.

## Package registry

`package.json.editing` contains `lighting` (0..1), 1..8 `decorations` and, since
PQ-250, an optional `spawns`: the ascending, distinct indexes of the spawn points
an editor may move. Without it every spawn point is editable, as before; a package
whose properties would pass the 128-property table (two per editable point) is
refused, so a zone's whole population names a few or none (`[]`).
Each decoration has a unique ASCII `id`, finite `position` (three numbers,
-1000..1000 metres), `yaw` (-π..π), uniform `scale` (.05..10), and
`visual: "scene.bin"`. Only that already cooked visual is supported; there is
no arbitrary asset loader, collision flag, event ID, or runtime prefab creation.
Decoration geometry is drawn separately and never enters the collision bake.
The original fixture banner is the demo prefab, not a Moradon scenery adapter.

The cooker emits N3T1: four-byte magic, little-endian u32 count (1..128), then
records of length-prefixed ASCII key, u32 kind, u32 target, and f32 initial/min/max.
Strings/counts/finite values, unique keys and kind/target slots, namespace,
complete six-field decorations, timer integrality and walkability are checked.
The server validates the complete initial state before becoming ready. Each
published state contains all values in registry order, not a chain of deltas.

| Kind | Key suffix | Target | Bounds | Activation |
|---|---|---|---|---|
| 0 | `lighting.intensity` | 0 | 0..1 | Next tick |
| 1–3 | `decoration.ID.x/y/z` | Decoration index | -1000..1000 | Next tick |
| 4 | `decoration.ID.yaw` | Decoration index | -π..π | Next tick |
| 5 | `decoration.ID.scale` | Decoration index | .05..10 | Next tick |
| 6 | `decoration.ID.visual` | Decoration index | Integer 0 = scene.bin | Next tick |
| 7–8 | `spawn.INDEX.x/z` | Existing spawn index | -1000..1000, walkable | Next spawn cycle |
| 9 | `npc.corpse_ticks` | 0 | Integer 0..1200 | Next spawn cycle |
| 10 | `npc.respawn_ticks` | 0 | Integer 1..12000, ≥ corpse | Next spawn cycle |

Keys carry the package namespace. Public `Property` metadata also contains type,
zone scope, `world.edit`, durable persistence, activation and schema version 1.
The inspector and terminal share this projection; the server sends validated
metadata, current capabilities and authority generation on registry/operation
responses. Cooked metadata permits offline local drafts. No arbitrary schema
reflection exists. Capability changes never depend on a tools build flag.

Live NPCs retain their position, contribution ledger and captured life timers.
A replacement gets fresh instance identity, current spawn values and
`Entity.definition_revision`. This does not rewrite player life deadlines or
pending/committed reward outcomes. Temporary spawns use an existing spawn index
and the package's existing NPC archetype, with fresh encounter identity, at most
16 simultaneous temporary NPCs, 60-second expiry, and 128 applied temporary
request identities per realm process. They do not respawn or survive restart.
Their authorization/result/audit survive, with `temporary_expired` on a later
realm generation; already committed rewards retain their ordinary lifetime.

## Editor and terminal

Build with `make client TOOLS=1`. The **backtick/tilde key (above Tab on US
keyboards)** toggles a terminal that slides down from the top and focuses its
command input. It works with the editor closed; Enter runs a command and retains
input focus. Press the same key to close it.

The terminal keeps a bounded scrollback of 512 lines. Each command is echoed as
`> command`, its output follows, and asynchronous typed results are appended once
in arrival order. Closing and reopening the terminal preserves the transcript;
`clear` discards it. The view follows new output but leaves a reader who scrolled
up alone. Tab completes and Up/Down recall command names.

Inspection commands read the package's own typed registry and the local draft:

| Command | Output |
|---|---|
| `help` | The supported command list. |
| `list [TEXT]` | Every editable property with its draft value, live value when they differ, and valid range; `TEXT` filters by substring. |
| `scene` | The release, game, live/draft revision, and one line per editable object with all of its fields. |
| `get KEY` | One property's draft and live value, range, and server registry metadata. |
| `draft` | Local draft state: changed count, base and live revision, undo/redo depth. |
| `clear` | Discard the transcript. |

`scene` lists editable objects only. Collision, events, terrain, players and live
NPCs are not editable properties and never appear.

F11 opens the world editor for Lighting/Spawn/NPC timers and the zone hierarchy.
Select a prop there or at its screen marker; drag X/Z handles or use inspector
sliders (Ctrl-click for precise values). Scale is uniform and rotation is yaw
only. Prefab selection has one supported choice. There are 64 local undo/redo
snapshots. The terminal and the editor share one local draft: undo/reset,
save/load and Publish apply to the entire draft. `Preview local draft` affects
rendering, never collision, movement, combat, inventory or another client. The
panel labels local draft base and current live revision. Reset to live discards
local changes and adopts the newest expected revision; conflicts display current
values for manual reconciliation. Local undo sends no request. After a successful
publish, reset to live before preparing the next edit.

Opening either the editor or the terminal captures gameplay input and releases
held movement, ground walking, repeat melee and relative camera dragging. While
captured, the client keeps SDL text input started so the command field and the
editor's text fields receive characters; gameplay otherwise stops text input so
movement keys never reach a text field. Normal clients render shared values but
link neither editor/terminal nor ImGui. Tools users without roles may use local
drafts; the server denies shared mutations.

| Terminal command | Effect / required capability |
|---|---|
| `help` | Bounded command reference |
| `set KEY NUMBER` | Local typed draft only |
| `publish` | Full draft, expected base revision; world.edit |
| `revert REVISION` | New revision restoring an old complete state; world.edit |
| `status REQUEST_ID` | Current authenticated character's recorded result |
| `retry` | Same request ID and payload; current authenticated session |
| `registry` | Public metadata, current character capabilities/generation |
| `inspect` | Shared revision inspection; server.inspect |
| `spawn INDEX` | Temporary normal NPC at configured spawn; entity.spawn |
| `show` / `hide` | Show this character to ordinary players for the session, or hide it again (PQ-192); server.inspect |

Tab completes registry keys and currently allowed privileged verbs; Up/Down
recall 64 recognized verb names. Arguments and unrecognized input are not retained
in history, avoiding storage of arbitrary text/secrets. No shell, SQL, credential,
role, inventory, XP, currency, entitlement, treasury or saved-life setter exists.
Weather/time is explicitly excluded. Collision/assets/stats/movement/tick-rate
requests receive restart-required feedback, never live application. Unknown
properties return invalid-property. Even restart cannot change a converted
realm's reward definition without its separately reviewed migration.

## Roles, transactions and recovery

Use the operator's existing `DATABASE_URL` with the native server CLI:

```bash
target/debug/n3e-server role grant ACCOUNT CHARACTER_ID REALM world.edit
target/debug/n3e-server role grant ACCOUNT CHARACTER_ID REALM entity.spawn
target/debug/n3e-server role grant ACCOUNT CHARACTER_ID REALM server.inspect
target/debug/n3e-server role revoke ACCOUNT CHARACTER_ID REALM world.edit
```

Provision accounts/characters first. The CLI checks the account/character/realm
association and only accepts the four C-05 capability names (including reserved
`config.edit`). Roles have realm-wide `*` zone scope in this single-zone release.
There is no first-player admin, and no inference from guild, elected or premium
status. Role changes increment a durable authority generation and append role
audit. Future held capabilities must implement their own simulation admission,
expiry and reset semantics; the returned generation is not a turbo implementation.

`server.inspect` also hides its holder (PQ-184,
D-152):
while its lease is current the server withholds the character from the
sessions without a current `server.inspect` lease: World snapshots, targets,
events (also those kept after it leaves, respawns or is shown), and the private message, party invitation, party removal (outside the
requester's group), friend and skill lookups. NPCs neither pick, chase nor
strike it (an NPC strike already awaiting its durable commit still
completes), and do not turn on it when it strikes them (PQ-193); its strike
still lowers the NPC's health. Holders see each other. Its chat
lines and a party it joins still name it, and a local line shows it is nearby;
a lapsed lease shows it (D-152). Revoking it shows the character again once
`role revoke` returns.

The holder can show itself (PQ-192,
D-153):
the terminal command `show` answers `shown`, and from then on the server treats
the character as an ordinary player for every session (it still sees hidden
actors); `hide` answers `hidden` and withholds it again. The server checks the
current `server.inspect` lease for both (`denied` otherwise). The choice lasts
for the session only: every login starts hidden, and a revocation resets it,
so a regrant hides the character again.

Migration 006 preserves all previous checksums. Transactions lock a stable
character authority row, then realm ownership, then authenticate current online
character/session generation. The realm lock serializes revision CAS. Matching
result lookup happens after authentication/fencing and before new capability
checks, so revoked characters can recover their existing results. Reused IDs
with different payloads conflict. Session generation is excluded from canonical
payload identity to permit authenticated reconnect retries. Other characters
cannot retrieve results. New mutations require current roles under the same
lock that revocation takes.

World revisions, immutable results and before/after audit commit atomically.
Audit has account/character/realm, request, operation target, reason, revision,
time and outcome. Temporary authorization is also audited transactionally.
Failed audit writes roll back everything. Denied requests increment rejection
metrics and produce rate-bounded, redacted security diagnostics.

The existing 128-slot dedicated database worker performs all blocking I/O.
The tick admits at most 16 outstanding admin jobs, drains at most eight completed
jobs per tick, and activates only committed monotonic complete snapshots.
Requests/results remain bounded by the 65,536-byte frame and 32,768-byte stored
payload/state caps. IDs are 1..64 ASCII alphanumeric/underscore/hyphen; reasons
are nonempty printable text ≤160 bytes. One request has ≤128 values. Full
snapshots at the existing 10 Hz delivery rate carry base hash, active revision
and applied tick; coalescing/out-of-order delivery does not require replaying
missing patches. Reconnect receives the full current state. Responses distinguish
pending, applied (with revision/tick), conflict, denied, invalid, restart-required,
and temporary outcomes; the database preserves committed results. A lost reply
is recovered with status/retry. Restart loads the committed full state before
readiness; acknowledgement is never based on Redis. Revocation ordering is
edit-before-revoke commits, or revoke-before-edit denies.

## Drafts, export and explicit rebase

Save/load accepts only a simple draft name under `build/drafts/NAME.n3draft`.
Drafts are bounded Protobuf Revision snapshots, checked against release identity,
keys, finite ranges and count. They contain values, not external paths or assets.
Symlink draft files and traversal names are refused. The export tool independently
validates inputs and copies only declared, path-validated recipe dependencies.

```bash
# Write a new source tree and cooked release; destination must not exist.
python tools/assetc/drafts.py export games/demo build/drafts/draft.n3draft build/edited-demo
# Rebase only after explicitly choosing old/new source packages.
python tools/assetc/drafts.py rebase games/demo build/cosmetic-source build/drafts/draft.n3draft build/rebased.n3draft
```

Export bakes absolute property values exactly once. It creates a different base
hash; it does not copy Postgres overrides, roles, characters or rewards. Deploying
it is a separate operator action. Verification uses a **new disposable realm**,
which starts at revision zero with the baked values. Existing realms reject an
incompatible override base before readiness, including baseline revision zero.
Never delete overrides to bypass that check. In-place adoption/migration of a
populated realm is not implemented by this export flow.

Rebase is an explicit offline draft operation. It requires matching property
identities/types/bounds and byte-identical collision, gameplay, progression, life,
NPC, damage and melee definitions. Cosmetic dependency/default changes can rebase;
authoritative dependency changes fail and need separate release/migration work.
Rebase resets expected revision to zero and retains absolute values, so the output
is for the chosen new base, not an automatic merge into an existing edited realm.

## Disposable user review

```bash
source tools/env.sh
./tools/play-tools
```

The launcher builds/cooks, creates isolated PG/Redis/realm resources, and opens
Explorer (moderator) plus Companion (unprivileged), both tools-enabled. Close both
clients to remove only that disposable session. No existing realm is deployed.
`./tools/play-tools --ko` first cooks the optional local KO artwork package and
reviews that instead; it is a cosmetic override, so the registry, gameplay,
collision and camera are the same, and the editable set stays lighting plus the
package's decorations.
Use `~` for the terminal (`help`, `scene`, `list`, `get`, `set`, `publish`) and
F11 for the sliders and handles; observe Companion. Companion's
local preview is private and its publish is denied. Test undo/redo, save/load,
conflict feedback, status/retry, shared revert and temporary spawn. For revocation,
while the review session remains running, in another repository shell:

```bash
source tools/env.sh
source build/p4/session.env
target/debug/n3e-server role revoke explorer "$N3E_REVIEW_CHARACTER" "$N3E_REALM" world.edit
```

That ignored mode-0600 file contains only this disposable session's operator
connection and identities. Repeat a prior request with `retry` and attempt a new
publish; the first recovers the result and the second is denied. Use `role grant`
to restore it. Automated restart/crash/export tests are:

```bash
N3E_GRAPHICAL=1 python tests/administration.py
```

At the Phase 4 merge no Moradon import, held-Q turbo, noclip, doors, room events,
weather/time, quest/trade/guild/war, king/premium, currency/economy, emblem upload
or shortcut persistence existed. Later work added the Moradon import and turbo (KX),
coins/merchants and client-local shortcuts; the rest are in the
gap register. The numbered phase order was dropped on 2026-09-25
(ROADMAP). No new KO behavioral fidelity or
bug/exploit exception is claimed.
