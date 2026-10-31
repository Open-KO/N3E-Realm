# Ground loot presentation

D-089 adds optional `presentation["loot-model.bin"]`: a hashed static N3S1 model
for eligible durable bundles. It requires engine10 or later, progression and the
complete ordinary presentation set. Engine33/wire26 remain unchanged. Existing
packages without it retain the text/F fallback; older readers reject the extra
file instead of silently discarding it. Assetc includes it in release identity;
the server verifies its hash, not its cosmetic mesh geometry.

The native reader applies ordinary N3S1 limits, requires no animation tracks,
limits positive model/node scales to100 and posed coordinates to ±100m, and
rejects nonfinite geometry. This scene has no world collision payload. The
renderer creates one instance per nonzero encounter in the server's eligible
drop snapshot, at its authoritative position. Disconnect, expiry or the last
claim removes it. Multiple items share one model. No new entitlement is inferred
from a model or a click.

D-094 sets Moradon's package-owned durable loot TTL to 20 seconds, as requested
after the binary audit. Unclaimed rewards and their chest expire together from
settlement creation; taking all items removes the chest sooner. The client receives
expiry on its next list refresh (normally within one second), and an open pickup
panel closes when its entries disappear. Reconnect does not restart the timer.
This uses the existing server expiry transaction, not a client-only hidden chest.
The 20-second corpse/container lifetime is binary-confirmed; matching server
reward-expiry timing has not been established. Applying 20 seconds to the synthetic
demo reward TTL is the chosen integration of the user's requested disappearance.
Other game packages retain their own TTLs. Follow-up.

Both mouse buttons can select a visible mesh through a camera ray. Near/far bounds
and world collision block invalid picks; HUD/focus/editor capture takes precedence.
Left-click retains living-NPC selection precedence. A successful nearby selection
stops walking/autoattack and opens the existing six-slot pickup window at the
cursor with its vertical offset. Right-click does not start camera dragging when
it opens a bundle. F remains the nearest-bundle shortcut. Existing ownership,
range, capacity, retry, settlement and durable claim rules remain authoritative.
D-090 closes pickup immediately on walking/approach or keyboard turning input,
matching binary005d6430/005794c0 and005c6990. UI/text capture gates movement;
snapshot position correction alone does not close the window. Closing leaves
server-side claim completion intact. Audit.

D-097 also preserves client status-query recovery for the one in-flight claim
when movement, death, expiry or switching bundles closes the panel. A matching
result resolves it; unrelated results do not. Disconnect or changed session/entity
clears that client tracking, while reconnect rebuilds durable bag and eligible
loot state. Neither closing nor retrying authorizes a grant or extends expiry.
Lifecycle audit and race verification.

Moradon's offline `games/moradon/loot-model.json` owns the legacy source path and
1.5 scale. The importer accepts the observed static one-part opaque shape with
identical texture frames and rejects unsupported variants. No imported asset is
committed. Binary/asset evidence and verification.

D-099 adds optional `presentation["loot-policy.bin"]`, requiring `loot-model.bin`.
Its eight bytes are `N3LP` followed by a little-endian float32 open radius, finite
and in (0,100]. Assetc and both readers validate it; it participates in the release
hash. Opted-in packages use strict three-dimensional distance < radius for opening
and keeping the panel open. Packages without it retain inclusive claim-radius
opening. No wire or database change is needed.

Moradon selects the binary-confirmed 10-meter opening radius; its server pickup
radius remains 3 meters. Inspecting a chest grants no pickup authority. At 10 meters
opening fails; at 3–10 meters inspecting is allowed but pickup rejects out of range.
Movement still closes the panel. The 20-second reward lifetime is unchanged.

Support remains partial: the binary uses a corpse-side rotated offset and corpse/
container collision picking. Current drops retain an authoritative origin but no
corpse orientation; exact placement therefore remains a gap. Binary00458ef0 fades
the corpse during its last ten seconds, restores render state through004196a0,
and renders the separate container without passing that alpha. Do not infer a
chest fade from corpse fading. Exact input precedence, corpse fading/open-triggered
aging and public audiences remain gaps. The supplied chest asset provides no
changing lid animation; opening displays loot.
Current audit and evidence.

Since PQ-199 (2026-10-13) a slain NPC leaves the actor pick once its death clip
has ended (at once for the stand-in model), as KO moves it to the corpse map at
state 5, so a left click on it reaches this bundle pick instead of selecting it.
The corpse body itself is still not a pick target; KO's corpse pick tests it
(`00471990` → `005c7c60`), PQ-201.
Evidence.
