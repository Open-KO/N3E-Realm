# Durability restoration (N3J1)

Engine17/wire10 adds required hashed `repair.bin` to the bag/merchant contracts.
The schema is `N3J1`, little-endian f64 exponent (.01–1), f32 linear coefficient
(0–1), u32 price offset (0–1000000), f32 final multiplier (0–1), u32 item count
(1–64), and unique length-prefixed repairable item IDs. IDs must occur in the
inventory definitions with maximum durability greater than1. Prices come from
the existing N3O1 records. Both runtime readers reject invalid fields, NaNs,
truncation, trailing bytes and incompatible release pairings.

The reusable price expression is:

```
base = trunc(((price - offset) * linear + pow(price, exponent))
             * (maximum - current) / maximum)
cost = trunc(base * multiplier)
```

The supplied server's parameters are exponent0.82, linear float0.0001 and offset10,
with a later optional50% discount. These values are package data, not engine
constants. Negative/nonfinite/overflowing prices, maximum<=1 and current>maximum
reject. Full durability costs zero. The initial implementation supports a fixed
package multiplier; per-character premium eligibility remains a separate feature.
Selected numerical vectors match independent high-precision evaluation; this is
not exhaustive equivalence to the historical CRT/x87 implementation near every
integer boundary.

BagRequest operation4 repairs the owned instance in `source`. Item ID and instance
must match the current slot and expected revision; quantity, destination and
service are empty/zero. The inspected repair leaf/receiver have no merchant-range
or HP check, so this operation adds neither. Current selected-session/realm fences,
bounded requests and fresh server-captured state still apply. The item must be in
the package repair allowlist. Restoring maximum durability and deducting coins
commit with the immutable original result. Insufficient funds change neither.
Retries, conflicts and snapshot revision rules remain those of the bag ledger.

The normal/tools inventory view displays the quoted cost next to a repairable
item. Enter `/repair SLOT` restores that numbered bag slot; `/retry` repeats the
last operation. Quote computation is independently implemented in C++ and Rust.
Readonly diagnostic interfaces are `n3e-asset-check PACKAGE --repair-cost PRICE
CURRENT MAXIMUM` and `N3E_PACKAGE=PACKAGE n3e-server --repair-cost PRICE CURRENT
MAXIMUM`.

Current scope is bag-item restoration. KO repair artwork/tooltips and
account-specific premium eligibility remain open; equipment repair, recalculated
combat stats and melee wear were added later (below, [stats](stats.md), [wear](wear.md)). Tests inject damaged records only into disposable realms;
that fixture setup is not an implemented player damage or administration command.

N3Q1 equipment packages also support operation8 and `/repairgear SLOT`, with the
same exact curve, item allowlist and transaction ledger. Repair selects the owned
equipment container; instance, location and quantity remain unchanged. Equipped
quotes appear beside the slot. Combat stats refresh from equipment ([stats](stats.md)) and melee wear is
[implemented](wear.md); spell/archery wear remains open (gap register).
