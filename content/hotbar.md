# Action shortcuts and cooldown presentation (N3H8)

N3H8 extends N3H7's complete HUD layout, item icons, portrait views and tooltip
layout with:

- u32 action-icon count (0–64), followed by each action's string item ID, u32
  texture index and four f32 UV coordinates. IDs must be distinct supported
  consumables or engine34 skills in the release; rectangles are nonempty and within0..1.
- u32 ARGB cooldown overlay colour.
- Three u32 completion texture indices, each a valid non-font HUD texture.

All integers are little-endian. The native reader rejects malformed bounds,
unknown/duplicate actions, invalid texture/UV references and trailing bytes.
Older HUD versions remain supported. This is a cosmetic package extension;
engine33/wire26 consumable authority and persistence are unchanged. Older clients
reject the new HUD header when loading the package.

Ordinary HUD records supply the original UIF geometry: `item` records with keys
`hotbar:0` through `hotbar:7`, matching `action` hit records, `value` records
`count:hotbar:N`, and arrow actions `hotbar_prev`/`hotbar_next`. Eight pages each
hold eight package action IDs. Bag-to-hotbar drag copies the action assignment,
not an inventory instance. Right-click and release on the same bag slot registers
the potion in the first empty slot of the current page. Duplicates are allowed;
a full page does nothing. Registration saves the shortcut without a use request.
Numbers1–8 and releasing a click in the same slot use
it; dragging to another slot replaces that shortcut; dropping outside removes
it. Page arrows clamp at the endpoints. Keyboard shortcuts are captured only in
focused gameplay, not chat/dialogs/editor. F1–F8 select a page directly (Alt up, also while typing) and PgUp/PgDn step it, clamped (`004dfa70`, `004dfa30`, `004dfa50`; PQ-009); the keys come from the package input map. Reconnect moved to F12 (D-136).

Activation resolves an occupied current bag stack, then submits the existing
revision/instance-fenced operation9. Counts aggregate all bag stacks. Empty
shortcuts remain registered with count0. There is no optimistic inventory debit.
The client remembers at most32 recent request/status pairs to reconcile the
matching display timer without treating an unrelated inventory reply as success.
Duplicate shortcuts share one action timer; page changes do not reset it. A
rejected new use clears its tentative display, not an existing accepted timer.
Exact retries do not start a new timer or apply an effect.

The sweep is displayed on hotbar icons only, matching the supplied executable;
its inventory and shared icon renderers have no recast sweep.
The sweep starts at request submission and uses the package recast duration,
matching the audited binary's recast-only presentation. A clockwise reveal uses
sine-interpolated icon-edge geometry. After confirmation, expiry displays each
of the three completion textures for one rendered frame, as in the binary.
Server activation delay and shared cooldown remain independent; visual completion
is never authorization. Disconnect/new runtime entity clears transient timers;
server cooldown durability remains authoritative after reconnect. An unconfirmed
display times out after10s. Engine34 adds the bounded direct skills and reconnect-resynchronized spell timers
described in [skills](skills.md). General spells, potion timer resynchronization
and the optional completion sound remain support gaps.

Assignments are local preferences saved by replacement of a temporary file under
`$XDG_STATE_HOME/n3e/hotbars/`, falling back to `$HOME/.local/state/n3e/hotbars/`.
The filename hashes endpoint, game, account and character name. `N3B1` text has
one header and exactly64 item-ID lines, capped at16KiB on read. Unknown actions
are ignored; cooldowns and inventory are never restored from this file. Page
selection starts at page1. Preferences are not synchronized between machines.

Moradon uses original local skill-icon artwork for490011/490016 and the three
`Misc/RecastObject/64shot000N.dxt` textures. The existing bounded DXT3 importer
preserves their alpha; the offline cooker applies the binary's100/255 flash
opacity. The package owns textures and overlay colour; no legacy IDs or paths
are compiled into the engine.
