# Rest posture and recovery (N3E1)

Engine30/wire23 adds `rest.bin`, a complete N3A3 animation set and authoritative
posture. All fields are little-endian u32 after magic `N3E1`: interval in simulation
ticks (1..12000), sit cooldown ticks (0..1200), level-row count (1..255), then each
row's health increment, resource numerator, resource denominator and resource
addend. Row values are0..100000, denominator is at least1. No trailing bytes.
The producer and both readers validate the same bounds and dependencies. N3Z1
remains the unrelated party format. Rest requires the current appearance and
complete player/NPC presentation capability set.

At each eligible interval, living seated players gain the row's health increment
and `floor(max_resource * numerator / denominator) + addend`, clamped to current
derived maxima. Level indexes are clamped to the available rows. Rest never
revives a dead actor. Standing retains the existing resource recovery rule.
No game formula, artwork path or historical ID resides in runtime engine code.

Envelope45 `Rest` carries session generation, strictly increasing nonzero sequence,
current entity and explicit desired sitting state. Public Entity field21 replicates
that state. Requests require an authenticated selected player, current realm
ownership, matching generation/entity and an available living actor. Pending
combat/leave/shutdown and movement reject sitting. Starting rest resets its recovery
deadline; repeated identical posture requests do not. Sitting has a package-defined
cooldown; standing does not. Accepted movement cancels posture before recovery in
the same simulation tick. Attacks, incoming attack outcomes, death and revive also
clear it. Posture is ephemeral; reconnect starts standing and grants no offline
recovery. Existing durable death/equipment operations remain authoritative.

The C key and original bottom Sit/Stand icons submit the same intent. N3H7
visibility4 hides Sit while sitting; visibility5 hides Stand while standing.
Both drawing and hit testing use replicated state. Input respects text/modal
ownership. N3A3 indexes7/8/9 play sit-down, seated idle and stand-up; transitions
blend through the existing animation player and death takes precedence.

Moradon ordinary recovery uses101 ticks (the binary tests strictly greater than
five seconds at20Hz), sit cooldown60, health `trunc(level*(1+level/30))+3`, and
resource `floor(max_resource*5/(level+29))+3`. Class/premium/effect/zone multipliers
remain fidelity gaps. Standing health recovery is not added: the supplied server
requires an effect flag, disagreeing with the source's unconditional standing path.
Binary findings and verification.
