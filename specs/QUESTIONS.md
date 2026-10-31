# Open questions

Raised while writing the specs. Ordered by how much depends on the answer. Each has a
**default** — the interpretation an agent should take if the question is still open when
it reaches the relevant work — except where marked **blocking**.

## Blocking (decide before M0)

*(none — Q3 resolved below)*

## Shapes a spec (safe default exists)

### Q4 — Require Discord guild membership to log in?

Spec 02 requests only `identify`. Requiring membership needs `guilds.members.read` (or
the Bot checking membership via its own token — simpler) and a policy for players who
leave the guild mid-session.
**Default:** not required for login; the Bot can `/ban` anyone. Revisit if the realm is
invite-only.

### Q6 — What do `/drop` and `/event` do?

**Answered in spec 10, confirmed against KO (`KO-FINDINGS.md` §2):** event *presets* defined in the package (`events.json`) as
patches over revision properties with a duration; `/event <preset>` activates one via
the admin API, no restart. `/drop` is subsumed (a preset sets `rate.drop`). Remaining
engine work: registry kinds `rate.exp/drop/coin`, `event.active`, timed reversion. The
KO reversing item (P1 rate events) still informs the semantics (scope, stacking) — keep
it in the pre-phase.

### Q10 — Client exit code for "update required"

Exit `3` on `VERSION`/`CONTENT` handshake refusal, with KO-derived wording
(`KO-FINDINGS.md` §5). Engine item after migration; until then the Launcher's "any
non-zero exit within 10 s → refetch once" heuristic applies. **Default:** as stated.
### Q11 — Raw KO asset tarball hosting

Resolved to option C (spec 10): one immutable `.tar.zst` (~740 MB), sha256-pinned,
hosted as a Release asset of `N3E-Realm` (`content-store` Release). Remaining: confirm
GitHub's 2 GiB per-asset limit is comfortable and whether the tarball should be split by
top-level dir (`Chr/`, `Object/`, …) so partial fetches are possible. **Default:** one
file.

### Q13 — In-game notice in v1?

**Yes (resolved by `KO-FINDINGS.md` §1, §3).** KO warns in game once per minute
before shutdown and shows a notice panel on world entry. Spec 03 now has
`realm/notice {in_game}` → yellow NOTICE chat line, `realm/motd`, and the engine items
(`Chat.notice`, `Notice{lines}`). CD's force path sends one line per minute.
### Q14 — Ban model: `mute` and `attack-disable`?

**Mute in v1, attack-disable deferred (resolved by `KO-FINDINGS.md` §4).**
`accounts.muted_until`, `account.mute` permission, `/mute`. Enforced server-side by
dropping chat; the player is told once per session. Attack-disable waits for PvP.
### Q15 — Monitoring and alerting beyond the Bot

Nothing pages a human if the VPS dies at 3 a.m. (the Bot dies with it). A free external
uptime check on `7777`/`7781` posting to the ops channel via webhook is ~10 minutes of
work. **Default:** add it in M7; not a spec.

### Q16 — Hot TLS reload

Every cert renewal is a gated realm restart (spec 07). A `SIGHUP`-reloads-cert feature
in the realm process (gateway under B; n3e under A) removes that. **Default:** not v1;
renewals are ~every 60 days and gated anyway.

### Q17 — Admin API reference: generated or hand-kept?

Spec 08 publishes `/api/admin.md`. Generating it from code (OpenAPI) is extra tooling;
hand-keeping drifts. **Default:** hand-kept in spec 03 (it *is* the reference); the
docs build copies it.

### Q18 — Which `games/*` package is the realm, and does Moradon alone suffice for launch?

`games/moradon` exists and `live-ko` exercises it. Is the launch realm Moradon only, or
do other zones need to be cooked (and does `assetc` support them yet)? **Default:**
Moradon only; `games/moradon` is `realm-assets`.

### Q26 — Code signing (later)

Launching **unsigned** (Windows Q2, option a). Revisit when the repo is public: apply to
SignPath Foundation (free OSS signing; needs an OSI licence on the code); fall back to an
OV certificate signed from CD via a cloud HSM. Spec 06 keeps a no-op `sign` stage so
enabling it is configuration. Player docs carry the SmartScreen note until then.

### Q19 — Public redistribution of KO-derived content

Resolved by the user: the Open-KO org has published KO content for a long time without
issue; Releases are public. Recorded here so the risk acceptance is explicit. The
content archive should carry a `PROVENANCE.md` naming the Open-KO source and pin.

### Q20 — Custom-asset scope for v1

Spec 10 opens items, NPC looks, effects, UI textures, tables, rates, presets. Zones and
terrain from non-KO sources are closed (importers are KO-specific). Confirm, and decide
whether *modified KO-derived* assets (e.g. a retextured KO model exported from Blender)
count as contributions or as KO material. **Default:** closed to zones; derived-from-KO
assets are KO material and not accepted.

### Q21 — Boss spawn lifetime

The engine's `spawn` is a temporary NPC with a 60 s expiry and ≤ 16 concurrent (editor
semantics). A boss event needs longer. Add `duration_ticks` to the spawn authorisation,
bounded (≤ 2 h?), still non-persistent across restart. **Default:** add it, cap 2 h.

### Q22 — Licence for contributed assets

CC-BY 4.0 or CC0. CC0 is simplest for redistribution; CC-BY credits artists in
`PROVENANCE.md`, which we keep anyway. **Default:** CC-BY 4.0.

### Q23 — Software-GL preview renders in content CI

llvmpipe offscreen capture of changed assets as a PR artifact. Nice, not required.
**Default:** not v1.

### Q24 — Preset behaviour across a realm restart

A preset active at restart: resume if still within its wall-clock window, or always
revert? Resuming is friendlier for "weekend XP" spanning a Saturday deploy. The expiry
is already stored in the revision, so resuming is the natural implementation.
**Default:** resume.

### Q25 — Content store location

Release assets on a rolling `content-store` Release (per-asset limit 2 GiB; no
documented count limit but thousands of assets on one Release is untested). If it
becomes a problem, an object store behind the same `base_url`. **Default:** Release
assets; watch the count.

## Resolved

| Q | Resolution |
|---|---|
| Q1 | **In-process, in `N3E-Realm`.** The engine migrates into `N3E-Realm` (spec 09); the realm service (01–03) is implemented inside `n3e-server`/`n3e-client` there. No gateway. `n3e` freezes as reference/research. |
| Q2 | **Client runs the OAuth flow** (architecture ① stands); `discord_client_id` comes from the realm config via the manifest, not compiled in. |
| Q3 | **Windows is a v1 requirement; the client stays C++.** Port in M4b (CMake/vcpkg, POSIX audit, Windows cert-store → OpenSSL, `%APPDATA%` paths). Tested by (d2) a client-local `--smoke-local` CI job on both `ubuntu-latest` and `windows-latest` plus (a) a Discord canary role for early releases; a real-GPU Windows run is manual: the maintainer runs the client on their own Windows machine periodically (2026-10-30); automating it is the upgrade path. macOS not v1. A Rust client is explicitly deferred (arguments on record: cross-compile ergonomics, shared collision crate with the server) — not before launch. |
| Q9 | `realm.restart` removed from `architecture.md`; restart is a CD/compose action. |
| Q5 | Moot (Launcher does not hold the token). |
| Q7 | Moot (no gateway). `N3E_MAX_CONNECTIONS` replaces the hardcoded 64. |
| Q8 | Moot (no gateway). Existing throttle applies per real client IP. |
| Q12 | **KO content, published publicly.** Raw KO tree as a pinned tarball (spec 10, option C); `games/moradon` is the first package. See Q11, Q18, Q19. |
| Q27 | **Kept, optional** (2026-10-30). The realm is Moradon from the client tree alone. The KO extras — installers (1097/2145/2233 zones and visuals) and the KO server database export (`tools/ko-reference/inspect_db.py`, restored for this) — stay operator-supplied inputs under ignored `build/`; the code is kept and its tests SKIP or report NOT RUN without them. |
| Q28 | **Synthetic schema states** (2026-10-30). The downgrade and pre-progression upgrade checks no longer need a server built from n3e history: `tests/schema_states.py` builds a database at migration N from `deploy/` exactly as `persistence::migrate` does, and one migration ahead of the server by adding an unknown `schema_migrations` row. `progression_db` pins the shipped 001–004 digests. The legacy-server binary and `N3E_HISTORY` are gone. |

## Raised during implementation

*(Agents append here. Format: `### Qnn — title`, context, options, default taken.)*

### Q29 — Admin listen address inside compose

Spec 03 refuses any `N3E_ADMIN_LISTEN` that is not loopback or RFC 1918 (test 8 names
`0.0.0.0:7780`); spec 07 set `0.0.0.0:7780` in compose so the Bot and the host publish
could reach it. Options: allow `0.0.0.0` behind a flag; bind the container's address
discovered at start; give the server a static compose-network address. **Default taken
(M1):** the static address — compose network subnet `172.31.77.0/24`, `server` at
`172.31.77.10`, `N3E_ADMIN_LISTEN=172.31.77.10:7780`. The rule stays one line with no
escape hatch; spec 07 updated. Revisit if the subnet collides on the VPS.

### Q30 — Motd and account routes in M1

M1 is spec 03 minus world operations, but the motd route needs the revision property
store (M5) and the account routes need sessions and moderation (M3/M6). **Default
taken:** M1 ships status, drain, resume, notice and deploy-pending; every other route is
routed and permission-checked and answers `501 not_implemented` until its milestone.
