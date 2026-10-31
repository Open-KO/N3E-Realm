# Equipment-derived stats (N3Y1)

Engine19/wire12 adds `stats.bin`, requires equipment and contested melee damage,
and pairs with N3P1 `stat_policy=equipment_v1` (mode2). Mode1 remains `fixed_v1`.
All item/category IDs, archetype values and coefficients are package data. The
current ten-level original progression curve and shared archetype are retained;
character class selection, allocated points and the historical level table remain
open. This is the ordinary equipment calculation, without buffs, mastery passives,
transformations, special-zone overrides, resistances or weapon effects.

Binary layout is little endian, with length-prefixed strings:

- Magic N3Y1, then 13 u32 values: primary/secondary slot, dual_wield,
  dexterity_attack, weapon_floor, attack_base, attack_offset,
  broken_weapon_divisor, broken_raw_divisor, strength_threshold,
  stamina_threshold, weight_scale, rate_initial.
- Nine f32 coefficients: secondary_scale, attack_linear, defense_coefficient,
  accuracy_coefficient, evasion_coefficient, strength_attack, stamina_defense,
  rate_scale, rate_base.
- Three polynomials (health, mana, stamina_resource): f32 coefficient, linear
  coefficient (health f64; other two f32), u32 divisor/base/attribute/offset.
- Category count1..32, then ID, f32 coefficient, u32 dexterity flag and offhand
  mode0/1/2 (ignored/scaled/full). IDs are unique in the game namespace.
- Item count equal to equipment definitions, then item ID, category ID,
  u32 attack/defense/health/resource/accuracy/evasion and five u32 attributes.
  Coverage must be exact; references and duplicate IDs are checked.

See the producer's ordered vocabulary for bounds. Rates and coefficients must be
finite. Attribute bonuses are currently nonnegative u8 values; signed/cursed
bonuses remain open. One resource polynomial must have a nonzero coefficient.
Current derived health/resource must be1..32767, attack/defense0..10000 and
accuracy/evasion0.000001..1000000. Every durable equipment arrangement is validated
at each of the ten reachable levels before it can commit; invalid combinations
roll back. Empty equipment is checked at package load. No signed legacy overflow
or unbounded arithmetic is emulated.

Ordinary calculation follows supplied Ebenezer0049e11c/004a0d2a/00499422/00499595:
weapon contributions use configured hand slots and offhand rules. Broken weapons
contribute divided attack; broken armor/attribute/rate bonuses contribute zero.
Item health/resource bonuses remain even when broken. Strength and precision
attack branches retain separate weapon aggregation and broken-weapon handling.
Health/resource use a quadratic level term, a linear term and integer attribute
quotient. Mana's attribute offset and base differ from stamina resource. Constants
are package data: the supplied binary's ordinary linear coefficients are HP f64
0.1, mana f32 0.2 and stamina resource f32 0.1. Do not substitute source formulas.
Input f32 values are promoted exactly; final rates round to f32. Bounded arithmetic
uses f64; independent high-precision vectors cover the supported domain.

Bag definition identity becomes SHA256(previous inventory/equipment identity ||
SHA256(stats.bin)). N3P1 mode also changes the progression identity. Existing
realms require an explicit compatible migration; no automatic reset or rewriting
of immutable outcomes. This addition changes no durable record layout/schema.

Selection loads durable gear off the simulation thread. Successful bag responses
queue their committed snapshot before later player actions; simulation ignores
older revisions, including original immutable retries. Equipment and level changes
recalculate combat and carrying values. Stat changes clamp health/resource to the
new maxima and never heal on a maximum increase. Respawn fills the current maxima.
Player attacks, NPC attacks, and NPC target forecasts use the actor's derived
values. Purchases calculate weight allowance from gear and durable level inside
the existing fenced transaction. No database I/O occurs in a simulation tick.

World field13 carries owner-only DerivedStats: attack1, defense2, float accuracy3,
float evasion4, max_health5, max_resource6, carry_limit7, packed attributes8, and
equipment_revision9. World
fields8/9 agree with the derived maxima. The native `/equipment` panel displays
server totals only when their equipment revision matches the displayed bag;
otherwise it shows an update indicator. Independent C++ packet checks bound values and the five attributes;
`golden-stats.hex` covers packed attributes and noninteger float rates. Equipment
mesh attachment and runtime durability wear are separate open capabilities.
