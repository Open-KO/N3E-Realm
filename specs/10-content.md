# 10 — Content: package vs. live tunables, raw KO input, contributions

How world content is sourced, split, built, delivered and contributed to. One repo
(`N3E-Realm`) holds everything that is *source*; the raw KO tree is a pinned build
input; live tunables live in Postgres through the engine's existing revision layer.

## Purpose

Let the community change the world through PRs where a rebuild is warranted, let
operators change tunables live where it isn't, and let anyone run their own realm from a
fork without a second repo or a second distribution system.

## The split

| Kind | Examples | Where | Changed via | Realm restart | Reaches players via |
|---|---|---|---|---|---|
| **Package** | models, textures, animations, terrain, tables, NPC archetypes, item definitions, default rates, event *presets*, spawn *names* | `games/<game>/` in the repo, cooked to a hash-pinned package | PR → CD | Yes, gated (O8) | Launcher, per-file (spec 04) |
| **Revision** | current rate multipliers, which preset is active, spawn positions, decoration placement, MOTD | Postgres `world_revisions` (engine's existing editor/revision layer, `content/editing.md`) | Admin API / Bot (spec 03, 05), or the in-game editor | No (next tick / next spawn cycle) | Wire (`Revision` in `World`) |
| **Raw KO input** | the original client asset tree | **Not in git.** One immutable tarball, pinned by sha256 in `UPSTREAM.md`, fetched into an ignored dir | Never (a new tarball = a new pin, reviewed) | — | — (only cooked output ships) |

Rule of thumb: if changing it needs an artist or a table edit, it's package. If an
operator should be able to flip it on a Saturday night, it's a revision property with
a package-defined default and bounds.

## Raw KO input (option C)

- `tools/fetch-ko-assets.sh`: downloads `ko-client-assets-<sha256>.tar.zst` from a
  Release asset of `N3E-Realm` (uploaded once by the maintainer; ~740 MB), verifies the
  hash in `UPSTREAM.md`, extracts to `assets/ko/` (git-ignored). Idempotent; cached by
  hash in CI.
- `tools/assetc` reads KO sources from `assets/ko/` (the migration renames the eight
  hardcoded `assets/ko` paths — spec 09 tweak list).
- Nothing from `assets/ko/` is ever committed, uploaded in a PR, or published
  uncooked. CI fails a PR that adds a file with a KO native extension (`.n3*`, `.gtd`,
  `.opd`, `.tbl`, …) anywhere under `games/`.
- Contributors who only edit JSON still need the tarball to cook locally; `make
  realm-assets` runs the fetch first. The PR check cooks in CI regardless, so a
  contributor *may* skip local cooking for small table edits.

## Package layout

```
games/moradon/
  package.json, *.json          # references, tables, rules (existing)
  assets/<name>/                # contributed assets: .gltf, .bin, .png, ≤ 8 MB/file
  events.json                   # event presets (new, below)
  PROVENANCE.md                 # one row per contributed asset (mandatory)
  README.md
```

### Asset references

Every asset reference is a `source` path. Two resolutions, decided by prefix:

- `ko:Item/1_2011_00_0.n3cplug` → `assets/ko/Item/…` (raw tree; read-only).
- `assets/ironfang/ironfang.gltf` → in-repo file (glTF 2.0 + PNG, cooked by `assetc`'s
  existing glTF path).

(Today the KO form is the bare path; the migration adds the `ko:` prefix so the two
kinds are unambiguous and a PR can never accidentally point at the raw tree with a
relative path.)

Replacing a KO asset = re-pointing its `source` to an in-repo file. The raw tree is
never edited.

### Spawn names (replaces the Bot's `spawns.toml`)

Each entry in the package's spawn table may carry `"name": "ironfang"` and
`"announce": "Ironfang has appeared near the north gate!"`. The server exposes them via
`GET /v1/world/catalog` (spec 03). The Bot resolves `/boss ironfang` through that, so
names and indexes can never drift from the content.

### Event presets (`events.json`)

```json
{
  "weekend-exp": {
    "title": "Weekend XP",
    "duration_s": 172800,
    "set": { "rate.exp": 1.5 },
    "announce": "Weekend XP is on: ×1.5 until Monday 00:00 UTC."
  },
  "boss-rush": { "title": "Boss rush", "duration_s": 3600,
                 "set": { "rate.drop": 2.0, "npc.respawn_ticks": 600 } }
}
```

A preset is a named patch over revision properties plus a duration. Activating one
(spec 03 `POST /v1/world/event`) publishes the patch as a revision with an expiry; the
server reverts to the previous values when it lapses or on `POST …/event/stop`. Presets
are package data, so adding or changing one is a PR; *activating* one is an operator
action. This is the answer to Q6.

KO reference (`KO-FINDINGS.md` §2): `/exp_add N` / `/money_add N` are a single global
additive percent each, 0–15, untimed, announced as a bold centre message when set and
repeated in the login notice for late joiners. Ours generalises (named, bounded
multipliers, timed) and keeps the two UX behaviours: **announce on start/stop in game**
and **show active presets to players entering the world** (via the MOTD/notice panel,
spec 03). Record the "> +15 %" deviation in `BALANCE.md`.

**Engine work implied (post-migration, in `server/`):** the revision registry today has
kinds for lighting, decorations, spawn positions and NPC timers (`content/editing.md`).
Add kinds `rate.exp`, `rate.drop`, `rate.coin` (bounds `0.1..10`, applied at reward
settlement time, **not** via `reward_policy_upgrades`, which stays the path for durable
policy changes), plus `event.active` (string id) and timed reversion. **The multiplier
in effect is written onto every settlement it affects** (new columns on
`encounter_settlements`, or the revision number it came from) — KO applies its bonus
with no record (`KO-FINDINGS.md` §2); n3e's audited, idempotent reward path must stay
explainable, so we do not copy that. Clients need no
change; `Revision` already flows in `World`.

**Boss spawns:** the engine's `spawn` operation creates a *temporary* NPC (≤ 16 at once,
60 s expiry — editor semantics). A boss event needs a longer life; add a
`duration_ticks` to the spawn request (bounded, e.g. ≤ 2 h) — **Q21**.

## Provenance and licence

- `PROVENANCE.md` has a table row for every file under `assets/`: path, author (GitHub
  handle), licence, tool, derivation ("original", "derived from <in-repo file>"). CI
  fails if a file lacks a row or a row lacks a file.
- Contributed assets are licensed **CC-BY 4.0** unless the repo decides otherwise
  (**Q22**); `CONTRIBUTING.md` states it; commits are DCO signed-off.
- KO-derived material is never contributed; it comes only from the pinned tarball. A
  contributor who "fixes" a KO texture must do so as an original replacement under the
  in-repo path, not by editing the raw file.

## CI checks on a content PR

Runs in the ordinary N3E-Realm workflow (`.github/workflows/ci.yml`, not CD):

1. Path policy: no KO-native extensions under `games/`; file size caps; `PROVENANCE.md`
   ↔ `assets/` consistency; DCO.
2. Cook: `tools/fetch-ko-assets.sh` (cached) then `python tools/assetc/main.py
   games/moradon out/` must succeed. `assetc` is strict; unsupported glTF features fail
   here.
3. Schema: `content/package.schema.json`, `events.json` schema, spawn names unique,
   preset keys exist in the registry with values inside bounds.
4. Progression diff: if `package.json.progression` changed, label the PR `balance` and
   require the `upgrade-progression` step in the deploy (spec 06).
5. Content tests: the CPU-only subset of `tests/` that reads the cooked package.
6. (Optional, **Q23**) Software-GL preview: render each new/changed asset offscreen with
   llvmpipe to a PNG and attach it as a workflow artifact for review.

GPU-dependent checks (`make live`, `live-ko`) remain GPU-host CI; a maintainer runs them
before merging asset PRs that touch rendering.

## Contribution flow

1. Fork; branch.
2. Add `assets/<name>/…` and a `PROVENANCE.md` row; reference it from the right JSON —
   or, for a balance change, edit the table and say why in the PR.
3. `make realm-assets` locally (optional for table-only changes); test in the local
   stack if you can.
4. PR using the template: *what*, *why*, *screenshot/recording* (assets), *balance
   rationale* (rates), checkbox for provenance.
5. CI as above. CODEOWNERS routes `games/**` to content maintainers, `server/**` to
   engine maintainers; a PR touching both needs both.
6. Merge → next CD cron → Release with the new package → gated restart → Launcher pulls
   only changed files.

`BALANCE.md` in `games/moradon/` states the realm's balance philosophy so rate PRs have
something to argue against.

## Running your own realm (forks)

Everything a realm needs is in the fork: engine, `games/<yours>/`, CD, deploy. A fork
publishes to its own Releases, hosts its own manifest (anywhere HTTPS), and its players
add a **realm profile** to the Launcher (spec 04). The manifest carries the realm's host,
port and Discord `client_id`; the fork registers its own Discord application. No
central registry, no shared infrastructure.

## v1 contribution scope (Q20)

Open: items, NPC looks, effects, UI textures, tables, rates, presets, spawn names and
announcements — anything that fills an **existing asset slot** or table row. Not yet:
new zones/terrain from non-KO sources (the terrain importers are KO-specific), new
engine features disguised as content. Say so in `CONTRIBUTING.md`.

## Acceptance tests

1. A PR adding a glTF + PNG with a provenance row cooks green; the same PR without the
   row fails on check 1.
2. A PR adding `foo.n3cplug` under `games/` fails on check 1.
3. `events.json` preset referencing an unknown key fails on check 3.
4. After merge and deploy, `GET /v1/world/catalog` lists the new spawn name; `/boss
   <name>` works without any Bot config change.
5. Activating a preset changes `rate.exp` for the next settlement; stopping it reverts;
   restart mid-preset: the preset is **not** resumed (revision expiry is wall-clock and
   recorded in the revision; on restart the server reverts anything expired) — or
   resumed if still within duration. Pick one and test it (**Q24**).
6. A fork with a different `games/<x>/` and manifest URL: the Launcher profile connects
   to it, and its Discord login uses the fork's `client_id`.

## Open questions

Q6 (now answered by presets; engine work remains), Q11, Q20–Q24.
