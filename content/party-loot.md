# Party loot

N3P3 engine26/wire19 implements party routing for the existing single reward item,
including aggregate-party ownership, a durable private audience and atomic claims.
This is KFC-04/05/07, KOF-0004, and remains a partial loot capability. General
stackable drops, currency delivery and the full bundle UI remain open. Coin
arithmetic has unit evidence but is not connected to runtime rewards yet.

## Confirmed behavior

Static binary evidence, Ebenezer-official.exe SHA256
7d83cc2872c92acb776e81366b6d6451625f141dc554e1b292e5b903d2fa7bcb:

- 00407088 is the recovered AI packet dispatcher, reached by tracing the
  distinctive `RecvUserFail` diagnostic at00409d87 back to0040725f. Its opcode8
  calls004099b6: create a56-byte bundle with6 item/count pairs, position/time and
  sequential ID, then notify the selected user or accepted party. Winner−1000
  instead broadcasts to the region.00473a82 advances bundle IDs;0041e8d5 sends
  to accepted physical party slots, without life/range filtering.
- 004a76f1→004c6a4f opens by ID in the current/nearby regions;004a7f1b picks up
  an item.004745fb resolves its region-map record;00473b42 removes it. The latter
  runs before bag/carry checks, a documented loss bug corrected by an atomic claim.
- 004aa5b3 initializes routing cursor0.004b48de scans physical slots0..7, wraps
  all8, skips absent/wrong-group/dead/pending/far/other-zone members, trade+8140
  and flags+89fc/+89fd, then checks carrying and a destination slot. A successful
  choice advances the cursor. At most16 attempts and8 missing members bound work.
  Zone54 bypasses party routing to the requester; zone-specific integration remains
  open. Names/meanings of the two additional inventory-blocking flags are not yet
  established by their writers.
- 004c78ec compares requester/member positions in the horizontal plane, requires
  the same zone byte and truncates distance before `<51`.00460b01 stores coordinate
  differences as f32;00460acc squares/sums in x87 default53-bit precision, writes
  a double and calls sqrt. The server startup precision trace is in the party
  evidence. Vertical distance is ignored here, unlike party XP range.
- 004b464c searches28 inventory slots for the first empty slot, then prefers an
  existing matching stack if the definition is countable. Routing's stack weight
  incorrectly multiplies a missing-slot counter rather than its quantity argument;
  the assembly and correction are recorded in BINARY-POLICY.
- 004a7f1b recognizes currency item900000000. Incoming amount must be1..32766.
  For a party, recipients are alive/accepted/in range/same zone; trade flags do
  not exclude coin recipients.004a8613–004a861c computes
  `trunc((member_level / total_eligible_levels) * amount)` using double arithmetic.
  The optional bonus is applied after that truncation as
  `trunc(share + share * 0.3)`, capped32700.00634ac0/00634ac4 contain the
  double bits3fd3333333333333. Bonus predicates read character data+127c or
  premium type+1284 equal3/4; entitlement acquisition remains a separate gate.
  Each wallet saturates at2100000000. Fractional remainders are not redistributed.

AI Server-official.exe SHA256
8715084f693f7b5c86a585c81b2e3db73accda1d4f79c174bf34d72addcd0435:
004204b4 fills the first free damage entry and updates existing entries in place.
004209da compares accepted party aggregate credit or solo credit with strict
`greater-than`, retaining the first damage entry on ties and recording its user
at NPC+13c.00424702 is the group credit helper; stale-pointer corrections already
recorded for party XP also apply to this ownership calculation.00421896→00423e5e
uses that selected user for drop generation. General drop probabilities and
regional/event generation are still separate open leaves.

KnightOnLine.exe SHA256
828ab0db5679da4705d3822e5f53870f70504a73756c869a8f734300e643a5e5:
005c5140 opcode0x26→005d7270 reads result types1/2/3/5, including bundle ID for
party types2/3/5, then invokes004d46a0. Recipient inventory updates and party
recipient-name notices are distinct. This differs from the source parser, which
omits those bundle IDs. Detailed original dialog behavior remains open.

## Format, authority and persistence

The progression model `contribution_party_loot_v3` retains all N3P2 fields and
requires `party_loot: {"radius": 50}`. The radius is an integer1..100, appended
as a little-endian u32 after the N3P2 fields. The reference profile uses50.
Producer and both readers require engine26/wire19 and party membership. The item
capability chain remains optional. Existing item-enabled packages must still use
the existing singleton reward definition; this is not a general drop-table format.

N3S4 appends at most64 first-contribution IDs after the frozen party records.
Every positive contributor appears exactly once. The worker recomputes ownership
from independently valid party aggregate/solo credit and this order; ties preserve
the first valid contributor. A dead contributor can still establish winning party
credit, while pickup recipients must be alive. The old N3P1/N3P2 definitions and
N3S2/N3S3 outcome bytes are unchanged.

Schema016 records the winning party's accepted members in an immutable private
`loot_audience`, including members who earned no XP. A solo audience contains its
owner. Audience membership is retained across leaving and reconnect; current party
membership at pickup determines the routing candidates. A guessed ID grants no
listing or pickup access. Status is also available to a committed recipient, so
a newly joined member can recover a payment it actually received. Public/event audiences are not implemented yet.

The simulation captures current physical slots and authoritative sessions, life,
positions and a two-second admission deadline. One realm currently has one zone;
per-member zone transitions and the two legacy inventory-blocking flags remain open.
The database locks the realm and character records, verifies those proofs and
current definitions, then selects a live fitting member. It checks aggregate token
capacity, materialized bag space and current equipment-derived carrying limits.
All reads and writes run on the bounded database worker, never on the simulation tick.

`party_loot_cursors` is keyed by realm ownership generation and ephemeral party ID.
The initial cursor is0; a successful pickup advances beyond the chosen physical
slot, wrapping across the package's2..8 slots. The same transaction grants the
item/count, advances progression and bag revisions, records the immutable result
and recipient metadata, consumes the entitlement and advances the cursor. Full,
overweight, stale or failed claims do not consume an item or advance the cursor.
Database-clock expiry records a terminal expired result without a grant or rotation.
Concurrent and exact retries observe one committed result and never rotate twice.

ClaimResult fields5/6 carry recipient character ID/name. Both claimant and recipient
receive updated durable inventory state; other captured party members receive the
recipient notice. Native clients display the name and refresh their bag. Logout
waits for an admitted pending claim to finish so other recipients' live refreshes
are applied before the claimant is removed. Restart creates new ephemeral parties
and cursor keys, while old outcomes remain retryable by their saved audience.

Explicit [reward upgrades](reward-upgrades.md) may activate N3P3 while preserving
old pending claims and world values; removing party loot again is rejected. Initial
conversion and changes to unrelated capabilities retain their existing gates.

Remaining: multi-item bundles, generated item definitions/durability, stackable loot,
coin generation/durable distribution and premium entitlements, special zone54,
public/event bundles, full original pickup dialogs and remaining progression rules.
The isolated coin kernel alone is not evidence that coin rewards are implemented.

## Coin-generation follow-up (integration verification in progress)

AI00423e5e reads template money at+94 and starts with signed integer
`base * draw / 100`, where0040282e→0040a9dd draws70..100 inclusive. The helper
uses15-bit CRT draws, modulo mapping and at most10 attempts to avoid repeating
its previous result; equal fixed bounds return directly. The last-result state
is shared by helper callers, so a source-only independent uniform draw is not
an equivalent claim.

Positive server event percent+3212 applies before party scaling: truncate
`amount + amount * (percent * 0.01)`.004b31c0/004b31c4 contain double bits
3f847ae147ae147b. If the winning contributor is in a party,00424ac8 counts alive
members in the NPC's zone within truncated3D distance50, then truncate
`amount * (1 + (members - 1) * 0.2)`. Constants004b3b58/004b3b5c contain
3fc999999999999a;004b3b00/004b3b04 contain3ff0000000000000. This includes the
zero-eligible-member factor0.8. The positive amount goes into the first bundle
slot; overflow fallback is32000. The exact32767 counterpart mismatch and
six-slot append bound are recorded in BINARY-POLICY before implementation.

The supplied backup is supporting data only: K_MONSTER has723 rows with iMoney
0..279618, K_NPC474 rows with0..32000, K_MONSTER_ITEM666 rows and K_NPC_ITEM202
rows with5 item/chance pairs. ITEM_GROUP is empty. Those schemas do not establish
matching binary table semantics or justify inventing absent group definitions.
Local export hashes and the safe empty-table exporter fix are in the work evidence.

AI CRT0045b30e stores `state = state * 0x343fd + 0x269ec3` modulo2^32
and returns `(state >> 16) & 0x7fff`. The new drop generator reproduces this
recurrence and the bounded interval helper with a server-owned entropy seed. Its
stream currently covers drop generation; consolidating the remaining combat/AI
random callers is still a fidelity gap, since the reference shares thread/global
state across those callers. There is no client-supplied seed.

N3P4 engine27/wire20, N3S5 and schema017 are in progress. Coin outcomes freeze the
generation draw and amount before persistence. Multiple claim operations per
encounter retain old singleton rows and results. Coin pickup distributes level-
weighted integer shares into all eligible wallets in one transaction, recording
nominal share, actual addition, final balance and bag revision. Premium acquisition
and active entitlement flags remain unimplemented; current live coin recipients
have no premium bonus. Do not treat the tested bonus kernel as entitlement support.
