# Generated currency drops

KFC-04/05/07; N3P4 engine27/wire20 and schema017 implement the bounded capability below.
This extends the existing singleton item reward with an independently claimable
currency entry from the same encounter. General item tables and original bundle
presentation remain open. [Binary observations](party-loot.md#coin-generation-follow-up-integration-verification-in-progress)
and correction record distinguish reference behavior
from the unimplemented premium, region/event and shared random-stream leaves.

## Package and frozen outcome

`progression.model` is `contribution_drops_v4`. All N3P3 fields remain, plus:

```json
"coins": {
  "currency": "demo:currency/coin",
  "base": 1000,
  "minimum_percent": 70,
  "maximum_percent": 100,
  "event_percent": 0,
  "party_bonus_percent": 20,
  "maximum": 32766,
  "overflow": 32000,
  "pickup_bonus_percent": 30,
  "bonus_cap": 32700
}
```

The ID must match the package inventory currency; a wallet is required, while
commerce/equipment/storage remain optional. Wallet limits must not exceed2100000000.
The reference profile uses70..100 inclusive,20% per extra eligible member,
maximum32766/fallback32000 and30% conditional pickup bonus capped32700. The actual
entitlement predicates are not implemented: current live recipients have no
premium bonus. Neither a client flag nor the package's bonus coefficient grants one.
The constant event percentage is a definition value; live royal-event activation
and its time/faction conditions remain separate work.

N3P4 appends the currency string and9 little-endian u32 fields in the displayed
order after the N3P3 radius. Base is0..21474836; draw endpoints0..100 are ordered;
event percentage0..32767; party and pickup bonuses0..100; maximum1..32766;
overflow1..maximum; bonus cap1..32766. The maximum signed intermediate over8
members must fit i32. Producers and both readers reject unsupported definitions.

At death the simulation captures one bounded random draw, the existing independently
validated winning group, and the generated amount. Generation first performs
integer base scaling, then event bonus/truncation, then party bonus/truncation,
then the overflow fallback. A party with zero eligible members still has its
observed factor; a solo winner has no party factor. Zero generated currency creates
no currency entry. The existing item remains independent.

N3S5 appends draw and amount as u32 after N3S4 contribution order. Canonical
validation recomputes the amount from the frozen recipients and definition.
The worker never rerolls. The drop stream reproduces AI0045b30e's CRT recurrence
and0040a9dd's modulo/repeat mapping, seeded by the server before simulation.
Remaining combat/AI random callers still use their earlier stream; full shared
reference random-call ordering is an explicit fidelity gap.

## Persistence, pickup and compatibility

Schema017 permits several claim operations for one encounter without rewriting
old settlement/result payloads. Existing rows retain kind0 and quantity1. New
kind1 entries carry the frozen currency amount, definition, original expiry and
saved private audience. Operation IDs come from the existing durable instance
sequence inside settlement. Duplicate settlement returns its committed result
and never creates another currency entry. Available entries remain bounded to64
per owner; an encounter needing two entries must fit both before either is created.

Pickup validates authenticated audience, semantic operation/encounter/currency/
quantity, fresh server capture, current requester session/life and original drop
range. The currently accepted party determines eligible wallet recipients. Their
current levels determine the integer shares; alive/session/range checks exclude
invalid members. Item capacity, carry weight and the item rotation cursor do not
limit currency. Horizontal member range retains the N3P3 binary rule.

The transaction locks current character/progression/bag records, applies all
wallet additions, records each nominal share, actual addition, final balance and
bag revision, and consumes the currency entry. Wallet saturation can make actual
addition smaller than nominal. Fractional remainders are not redistributed. A
failed transaction changes no wallet; exact retries return the immutable original
shares. An actual committed recipient may recover its result even if it joined
after the saved audience was captured; this does not grant listing or pickup
authority. Database-clock expiry consumes without payment. Pending logout waits for
completion and live state application, including all other recipients' bags.

Wire20 pages use operation cursors and add quantity/kind fields. Earlier packages
retain encounter cursors and zero-valued extensions. ClaimResult coins7 carries
at most8 immutable recipients; old count/revision fields remain0 for currency.
Clients request current bags after notices. The native pickup sends the advertised
quantity and shows the coin result; the ordinary inventory panel displays balance.
This remains original presentation rather than the complete historical bundle UI.

Explicit offline reward upgrades can activate N3P4 with unchanged other assets and
cannot remove coin support. Previously earned item/coin drops retain their stored
rules and amounts. A later generation-base change affects future encounters only.
Live deployment and user-tested catalog completion are not implied by these APIs.
