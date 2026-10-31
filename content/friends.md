# Directed friends

Optional `friends` requires engine23/wire16 and schema013. Source fields are
`capacity` (1..24), `name_bytes` (1..24), and `refresh_ticks` (1..1200), all integers.
`friends.bin` contains `N3F1` followed by those three little-endian u32 values.
The reference fixture selects24 entries,20-byte names and60 ticks (three seconds).
Names use the engine's bounded ASCII character-name vocabulary. Definition changes
or removal reject existing durable lists at startup until explicitly migrated.

Engine23 keeps the durable life/progression/editing foundation but makes item
capabilities optional. Dependencies remain inventory → commerce → repair → equipment
→ stats → wear → storage → credentials; each later capability requires its predecessor.
Stats also require damage and matching progression stat mode. Friends require none
of these item capabilities. Engines1..22 retain their prior required file sets.
Client/server requests check capability presence separately from wire version.

The authenticated selected character owns a directed roster: adding someone does
not modify their list or require consent. Simulation admission resolves the current
realm's target, exact name first and then unique ASCII-insensitive match. Add requires
an online, alive target. Admission remains valid for at most two seconds while the
database operation completes (n3e's own bound: KO's game server queues the add to its
DB agent with no time check, `004c59fa`/`00487ad9`/`004c5bbc`, PQ-289); an add whose
commit would pass it is refused and rolled back. Subsequent target logout does not
cancel an admitted add. Removal works offline. Self-add is allowed because the confirmed server path
does not reject it. Stable character IDs survive network entity lifetimes.

Schema013 stores definition/revision, physical slots and immutable operation results.
Mutations use expected revision, selected-session and realm fences, and one transaction
for membership, revision and result. The first empty slot is reused. Exact retries
return their original snapshot; changed payloads under the same ID return
`request_conflict`. Stale revisions, full/duplicate lists and absent removals cannot
mutate membership. Unavailable or expired admission is transient and does not claim
a durable operation ID. Clients never replace newer rosters with older retry snapshots.
Fault hooks exercise real process exits immediately before and after COMMIT.

Presence is separate ephemeral simulation state. Bounded names may be queried without
first storing them. The server limits each selected session by package ticks and
monotonically increasing sequence. Logged-in dead characters are online; offline
records carry no entity ID. Presence queries do no database I/O in ticks. With N3Z1
parties enabled, accepted and pending group affiliation set the party bit; packages
without parties report false. Party finder remains a separate open feature.

Native controls: `/friends`, `/friend NAME`, `/unfriend NAME`, `/friendretry`, and
`/friendhide`. The panel pages eight slots with bracket keys and refreshes visible
presence at the package interval. Login automatically loads the owner-only roster.
Original fixtures cover friends alone, the full item chain, every valid chain prefix,
and a second game namespace with a smaller capacity.

Binary grounding: client0056d810 and0056cde0/0056d060/0056d220/0056d530;
server004c59fa,0041de71,004b4b4d,004c5dec,004c5bbc; Aujard00415f80,
004347b0,00434f70. The supplied backup's existing-row INSERT procedure assigns the
owner instead of the requested friend, a local-data defect without proven executable
release correspondence. See binary index and
evidence.

Remaining fidelity work includes original UI interactions/ordering, global historical
name policy, immediate presence in load/mutation responses, full party integration and the
separate party-finder system. The original panel and split roster/presence messages
do not establish full historical presentation.
