# Frozen party XP

N3P2, engine25/wire18, extends the opt-in progression policy with
`model: contribution_party_v2` and a `party_rewards` object. Party membership is
required; item capabilities remain optional. N3P1 releases retain their old
arithmetic, canonical payload and durable policy mode.

Package fields: `bonus_tenths`0..8, finite double `level_minimum`0..1 and
`level_maximum`1..10, integer `level_gap`0..100, and ten positive signed32-bit
`level_xp` values. The first nine must exactly match successive cumulative
progression threshold differences; the last supplies the cap at the supported
terminal level. Radius must be an integer. The original fixture selects bonus8,
ratios2/3 and1.5, gap8 and original level costs. These are configurable data, not
an assertion that the supplied database/configuration matches the executables.

Encoding retains every N3P1 field after the changed four-byte magic, then appends
u32 bonus, f64 minimum/maximum, u32 gap and ten u32 level costs, little-endian.
The complete file hash is the durable reward definition. Both independent readers
reject a version, dependency, numeric or curve/table mismatch.

At death, the simulation freezes current accepted membership, leader level,
recipient level/life/zone/range, and positive contributors with valid current
identity/range. Pending invitations do not confer membership. Distance subtracts
f32 components, then sums double products in x/y/z order and takes the square root;
truncated distance must be no greater than the configured radius. Group recipient
eligibility additionally requires alive and same zone. Solo eligibility in this
new version follows the observed identity/range helper, which lacks those two
checks. Durable IDs replace the legacy numeric-socket/name identity pair.

The denominator retains all credited damage, including invalid contributors.
Each group sums only its valid contributors. A sole eligible member follows the
solo share and NPC-minus-player-level multiplier without the multi-member cap.
For two or more eligible members, round the group's proportional base XP up,
then apply the observed absolute-NPC-level multiplier: unchanged below2,
ceil1.2 at2..4, ceil1.5 at5..7, double at8+. Count eligible members satisfying
leader±gap OR the real-valued ratio interval. With at least two qualifying
members, multiply by `1+(qualified-1)*(bonus_tenths*0.1)`. Divide proportionally
by eligible level sum and round each award up. Cap each multi-member award at
integer `level_xp[level-1]/10`. Keep the binary floating-point operation order.

The resulting N3S3 canonical record includes sorted party IDs, leader levels,
sorted member IDs and valid contributing IDs. At most64 positive contributors,
64 groups of at most8 members,512 recipient rows and32KiB canonical bytes are
accepted. Recipient rows may have zero direct credit only within a captured
group. The database worker recomputes every award from the frozen record and
policy, locks all recipient rows in ID order, then commits XP, revisions,
immutable outcomes and the existing entitlement together. Disconnects or changes
to membership after capture cannot change the result. A retry must have identical
bytes; process failure before COMMIT pays nobody, failure after COMMIT pays once.
No database call occurs on the simulation tick.

Forward schema014 expands policy modes and recipient credit/award bounds without
rewriting migration005 or immutable history. New realms use the existing explicit
offline `convert-progression` command, which currently requires a `test-` realm
and `N3E_TEST_PROGRESSION=disposable`. General operator activation remains an
integration gate. A realm already bound to another reward
definition refuses startup/conversion. The explicit offline
[reward upgrade](reward-upgrades.md) preserves earned XP, conversion baselines,
immutable outcomes and pending claims when the curve and inventory identity match.
It also adopts the new package base without changing published world values.

Loot still follows the prior exclusive contributor entitlement; grouped loot
ownership, coin/item distribution and original pickup behavior remain open.
The supported progression curve is still1..10. High-level reductions, complete
level growth, loyalty, event/premium adjustments and regional/guild admission remain
open. This is a partial KOF-0004/KFC-05 capability, not complete reward fidelity.

## Binary evidence

AI Server-official.exe SHA256
8715084f693f7b5c86a585c81b2e3db73accda1d4f79c174bf34d72addcd0435:

- 004209da groups current party contributions;00424702 sums credit;
  004234bf checks contributor identity/range;00424ac8 checks party recipient
  life/range/zone.00422f33→004130a2/0041306d establishes vector precision stages.
- 0042670d uses absolute NPC level, unlike the source's level-difference formula.
  The assembly has no subtraction from that template level.
- 0043c413 reads SERVER/PARTYEXP, fallback0, into signed short+3202 and reports
  values outside0..8.004209da converts it by double0.1 at004b3b30. The local
  `server.ini.default` separately contains8; that is configuration evidence.
- 004438fa caps multi-member XP after high-level reductions.0040cc5a binds
  LEVEL_UP.level/Exp;0043cee3 populates the eight-byte level records, storing Exp
  at+4.00443950–00443954 divides that field by10. The loader appends recordset
  order and the consumer indexes by level−1; the new format validates ordered
  explicit level data rather than relying on unspecified SQL result ordering.
- 0044380e is the uncapped solo output path. Both outputs reduce61..80 by
  double0.5 and81..90 by double0.3; those levels remain unsupported here.
- Startup0045c377→0045e70d invokes pointer004cd4f8=0045afa8, which calls
  0045fe43→004663bc→00466387 with precision mask0x30000/value0x10000.
  0046648f maps this to x87 PC0x200 (53bits), installed by FLDCW004663b4.
  This confirms the default precision used for the new double arithmetic.

The stale-pointer attribution and order-dependent party bonus corrections are
recorded with instruction addresses in BINARY-POLICY.
Raw decompilations/configuration/database exports stay local under ignored paths.
No supplied executable was run.
