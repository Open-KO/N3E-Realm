# Party membership

N3Z1 engine24/wire17 provides bounded ephemeral parties. `party` source fields:
`capacity`2..8, `name_bytes`1..24, `level_minimum`finite0..1,
`level_maximum`finite1..10, `level_gap`0..100, `repeat_ticks`0..1200.
Binary layout: magic `N3Z1`, u32 capacity/name_bytes, f64 minimum/maximum,
u32 gap/repeat_ticks, all little endian. Original reference fixture:8 members,
20-byte names,2/3..1.5 ratios or an eight-level difference,60 repeat ticks.
The durable life/progression/editing foundation remains required; friends and
all item capabilities are independently optional subject to their dependencies.

Parties belong to the live realm process and selected character sessions. Inviting
creates a singleton group with the leader in physical slot0; pending invitees have
a separate token and are not accepted members. Accept fills the first empty slot.
Decline ends an unaccepted singleton. Any accepted member may leave, while only the
current leader may invite, remove another member or disband. Removing a leader
selects the first remaining physical slot; a group dissolves when only one member
would remain. Disconnect removes membership and pending invitations. Process restart
begins with no parties; no durable reward or character state is lost by that reset.

Server-generated invitation tokens bind the group, inviter session and target
session. Ending a group or replacing its leader clears pending invitations. Multiple
pending targets do not reserve slots; acceptance rechecks capacity. Invitation checks
online/alive and ordinary level eligibility; the confirmed accept leaf does not
repeat life/level checks. Monotonic command sequences and bounded per-connection
requests reject stale or excessive requests. A package tick interval limits repeated
invitations to the same target. No tick waits on database/network I/O.

Wire42 PartyRequest operations0..5: snapshot, invite by name, accept token, decline
token, remove (empty name means self), disband. Wire43 carries owner-visible roster
and/or invitation. Wire44 carries sequence/status. Current server names, identities,
level and HP/MP populate roster updates even outside world interest range. Pending
and accepted affiliation both appear in friend presence, matching the binary's
group-index test. Membership is ephemeral; these are not durable operation receipts.

Original native controls: `/party`, `/invite NAME`, `/accept`, `/decline`, `/leave`,
`/kick NAME`, `/disband`, `/partyhide`, `/partyblock`. Blocking is a local client
preference that automatically declines a received invitation, as in the reference.
The server remains responsible for consent and leader authority.

Binary server004a99e3/004a9d1e/004aa5ef/004a9bd7/004aad98/004ab38d establishes
membership;0049085b invokes self-removal during connection cleanup. Client005c7df0,
005c80b0 and005d85a0 establish leader controls, input pacing and roster/invitation
presentation. Authority corrections close concrete
client-only permission checks and stale pending-group references.

N3P2 now provides [frozen party XP](party-rewards.md).
Still open: party loot routing, faction/guild/special-zone/activity admission
branches, class labels, party finder/chat/targeting and full historical UI. This
membership implementation does not close KOF-0004 or KOF-0027. N3P1 rewards retain their original solo policy; N3P2 is an explicit new definition.
