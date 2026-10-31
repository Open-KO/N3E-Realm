# Open discussions

This file holds product and design topics under discussion. Nothing here is scoped or
authorized work until the user turns it into a request. Record the outcome here
(and in DECISIONS once a choice is made).

## 2026-09-25 — Discord identity, Discord commerce and PostHog analytics

The user's idea:

- players log in with Discord;
- they can optionally join the project's Discord server;
- they buy power-ups and similar items through a Discord bot;
- player activity is logged to PostHog to improve the game experience, identify
  cheaters and tune server configuration and scaling.

### 1. Content and IP direction (decide first)

The playable demo is built on Knight Online's proprietary maps, models and UI,
which are used only locally (`ref/`, never redistributed). Charging for power-ups
on a server that uses those assets is commercial use of someone else's IP. That is
the usual way private servers get taken down, and it likely conflicts with
Discord's developer terms. The options:

- a non-commercial KO community server with no payments;
- an original game on n3e with its own assets, which is what the engine and package
  model were built for;
- licensing the KO content.

**Status 2026-09-25:** the Discord work is paused. The user leans toward a KO
community server, because asset generation is not yet good enough for a novel
game. For now, assume each player brings the original installer
`KnightOnLineSetup_1298.exe` and n3e converts it locally
(D-118, evidence
ko-installer-provenance).
Commerce does not fit a community server built on someone else's IP.

The answer shapes everything below. The original-asset exploration (2026-09-25,
[below](#2026-09-25--original-asset-exploration)) is a first look at the second
option.

### 2. Discord login

- **Flow:** the native client opens the system browser for Discord's OAuth2
  authorization-code flow with PKCE, using a loopback `http://127.0.0.1:<port>`
  redirect. The client sends the one-time code to the game server over the
  existing TLS connection.
- **Secrets:** the server is the confidential client. It exchanges the code with the
  application secret, which never ships in the client.
- **Accounts:** the server maps the Discord user ID to an n3e account through a new
  Postgres table (provider, subject → account). It then issues its own session, so
  gameplay does not depend on Discord being up.
- **Scopes:** request `identify`, and `guilds.join` only if the player opts into
  joining the server (which also needs a bot token). Avoid `email` unless there is a
  concrete need.
- **To evaluate:** the Discord Social SDK (presence, friends, account linking) and
  its Linux support.
- **Open:** Discord-only login, or keep password accounts for operators and tests?
  Is joining the server required or optional?

### 3. Purchases through a Discord bot

- **Provider options:**
  - Discord's native app monetization: SKUs, entitlements, subscriptions and
    consumables. Discord is the merchant of record and handles VAT; eligibility
    rules and a revenue share apply.
  - Stripe checkout links posted by the bot: more control, but tax is ours.
- **Fulfilment:**
  - Every purchase is a durable Postgres ledger entry, idempotent by the provider's
    transaction or entitlement ID.
  - Grants go through the existing durable reward/grant path: commit before ack,
    audited, retried with the same ID.
  - Refunds and chargebacks revoke or claw back.
  - Entitlements are reconciled periodically, not only through webhooks.
- **Bot boundaries:** the bot is a separate service with a narrow, authenticated,
  audited API. It has no general admin capability; privileged operations stay
  character- and role-authorized on the server (C-05).
- **Design choice:** "power-ups" could be stat power (pay-to-win), convenience (XP
  boosts, storage, cooldowns) or cosmetic. KO's premium, mall and PC-bang systems
  are cataloged (KOF-0041/0042/0057) as reference.
- **Other considerations:** minors (Discord is 13+), loot-box rules in some regions,
  consumer refund law.

### 4. PostHog

- **Good fit:** product analytics such as funnels, retention, session length and
  where players get stuck, plus client UI experiments.
- **Event sources:** mostly the Rust server, which is authoritative; client events
  are advisory. Emission goes through a bounded, batched, asynchronous queue, never
  blocking I/O in the simulation tick. Dropping events under backpressure is
  acceptable, because analytics is never authority.
- **Privacy:**
  - pseudonymous distinct IDs (not Discord IDs or usernames);
  - never send chat or payment data;
  - a published privacy notice with consent (GDPR for EU players) and a retention
    policy;
  - PostHog EU cloud or self-hosted.
- **Cheating:** PostHog is not an anti-cheat system. The authoritative server
  already rejects most cheats. Detections such as movement anomalies, impossible
  action rates, economy outliers and bot patterns should run server-side, with
  their evidence in Postgres because it must support sanctions. That needs the
  missing moderation and sanctions capability ([GAPS](GAPS.md), KOF-0059) first.
  Signals can be mirrored to PostHog for dashboards.
- **Scaling and config:**
  - Infrastructure metrics belong in Prometheus/Grafana (the server already exposes
    `/live`, `/ready` and metrics).
  - Server configuration changes go through n3e's audited config revisions, not
    PostHog feature flags. Flags are fine for client presentation experiments.

### 5. Suggested order

1. Decide the content and IP direction.
2. Discord identity and account linking.
3. The server-side analytics pipeline, with consent.
4. Moderation and sanctions.
5. Commerce, once the legal and tax questions are settled.

### Open questions for the user

- KO community server, or an original game on n3e?
- Discord-only login? Is joining the server required or optional?
- What kind of power-ups? Discord payments or Stripe?
- PostHog cloud (which region) or self-hosted? Where are the players?
- Linux-only client for now?

## 2026-09-25 — Original-asset exploration

The user asked for an exploration branch that runs a version of the Moradon demo
with custom-built assets instead of KO's. The theme is loosely inspired by
occult-noir comics (*Hellblazer*), keeping the same low-poly, authentic KO feel.
The theme is original: no licensed character names, likenesses or trademarks.

Outcome: **Ashgrave**, on branch `phase/original-assets-spike`.

- It is a fully procedural, stdlib-generated borough: chapel, terraces, pub, gas
  lamps and graveyard. A trench-coated investigator faces horned imps under
  night fog.
- It runs on the unchanged engine (engine 13) through `./tools/play-ashgrave`.
- The practical limit is engine 29+ features: Moradon's equipment visuals,
  skills, sitting and UIF dialogs need an original `N3D2`/dialog-HUD authoring
  path.
- A real art pipeline (Blender → constrained glTF) is the next need if this
  direction is chosen.

Evidence.

Follow-up the same day: Blender 5.2.2 is installed (`tools/install-blender.sh`).
- A generic Blender → `gltf.cook` character pipeline now brings CC0 KayKit
  characters into Ashgrave (`ASHGRAVE_CHARACTERS=kaykit`) in about 2 s each.
- Quality is far above the box figures, but KayKit's chunky style differs from
  KO's proportions.
- Options surveyed but not yet tried: Tripo, Rodin and Sloyd (hosted generators);
  TRELLIS.2 and TripoSR (MIT, local on a consumer GPU); Hunyuan3D (its licence
  excludes the EU/UK/South Korea); Kimodo and Rokoko Vision for motion;
  Quaternius UAL, KayKit and Kenney (CC0) for assets and animation.

## 2026-09-25 — Related games (Ares, Hero Online, Deicide/Laqia)

Survey: related-games-survey.

- **Likely relatives of KO's engine:**
  - Hero Online: the user says it uses KO's engine.
  - The Legend of Ares (Ares Online, also known as Repent Online, by MGame): likely.
  - Kingdom Online (Noah System): possible.
- **The user's `ares_setup_0903_2006.exe`** on Google Drive is not examined yet.
  The Drive connector cannot fetch it, because of its 10 MB limit.
- **Deicide Online is not a relative.** Its 2009 client is Laqia Online on its own
  Wind3D engine. A 2026 revival at `laqia.co.kr` ships a launcher that downloads
  its data from a CDN and adds a Windows Defender exclusion. It has not been run.
- **Possible use:** a real relative could test the engine's reuse claim with a
  second real content set. It would still be proprietary content that players must
  supply, under the same rules as D-118.

## 2026-09-25 — Asset rights ("abandonware") for KO and related games

The user asked whether any related game is abandonware with assets we could use.
Web research found none that is usable. This is not legal advice.

**No legal abandonware status.** Korea protects works made for hire for 70 years
after publication (Wikimedia Commons, "Copyright rules by territory/South Korea"),
and the US for 95 years. Assets from 2002–2009 stay protected into the 2070s,
whether or not anyone runs a server.

| Game | Status (2026-09-25) | Rights holder |
|---|---|---|
| Knight Online | Live (NTTGame) | Noah System / NTTGame |
| Legend of Ares / Repent | Live. Reforgix relaunched it in August 2024, with patches and maintenance through 2025 (legendofares.com, ares.reforgix.com). | MGame, licensed to Reforgix |
| Hero Online / Hero Plus | On Steam since 2018 (app 747920; developer MGAME Corporation, publisher Netgame). Current operation unclear. | MGame / Netgame |
| Kingdom Online | Closed: NTTGame posted a "Kingdom Online Farewell" notice (support.nttgame.com, not readable, date unknown). | Noah System / NTTGame, still active |
| Laqia / Deicide | Revived commercially at `laqia.co.kr` by a registered Korean sole proprietorship, with a Korean game-rating classification dated 2026-07-10. Also "Laqia 2" and "2.5" sites. Licensing unknown. | Developed by TeamMei (the `TEAMMAY` texture tag) and published by Daum Game |
| Droiyan Online, Eternal City | Not researched | MGame (developer unconfirmed) |

**Consequences:**

1. Taking assets from any of these games is ruled out: each is live or has an
   active rights holder.
2. Player-supplied files (D-118) remain the safe model, and would extend in the
   same way to Ares or Hero Online as a second game.
3. Licensing is the only route to shipping assets. The realistic targets:
   - Noah System / NTTGame for the closed Kingdom Online. They also own KO, so one
     conversation could cover both.
   - MGame for Ares or Hero Online. Reforgix's Ares licence shows MGame licenses
     old titles.

   Any approach needs a lawyer to check the chain of title first.
4. Original or CC0 assets remain the fallback (the paused original-asset spike).

## 2026-09-25 — Proposed next steps (not scoped)

The user will choose and start the next work in a new session. This is Claude's
recommendation, not authorized work.

**Recommended: the player-supplied KO import (D-118), as three reviewable branches.**

1. **Repeatability check (small spike).**
   - Run the Moradon conversion (`tools/assetc/ko_bake.py`) twice, and once with
     `build/ko-reference/installer/client` as the source in place of
     `ref/ko-src/assets/Client`. Compare the release hashes.
   - If they match, each player can convert locally and get the server's package.
   - If they don't, choose between making the output repeatable and splitting the
     package into strictly checked rules/collision and a local presentation layer.
2. **Read the installer directly.**
   - Promote the unpacker into an import step and pin a manifest of the files the
     converter reads.
   - Add a `.tbl` decoder in place of the six Open-KO CSV exports (`UPC_DefaultLooks`,
     `Zones`, `sound`, `fx`, `Skill_Magic_Main_us`, `skill_magic_3`). Check the
     format in Ghidra against the client's loader first.
   - Done when Moradon builds from `KnightOnLineSetup_1298.exe` alone and matches
     today's package.
3. **Player flow.**
   - The client asks for the installer on first run, converts and caches the
     result, and refuses wrong or incomplete inputs.
   - The server uses the same import. NPC rows still come from the reference
     database.

**After that:** the gameplay gaps for a playable KO, in this order: zones and warps,
moderation, then classes and magic types ([GAPS](GAPS.md)).

**Smaller options:**

- confirm the engine family from the Ares or a Hero Online client (install `7zip`;
  get the file from Google Drive in a browser);
- close the provenance gates: Ebenezer `0042171b`, Aujard `0041c708`,
  `Texts_us.tbl`.

## 2026-09-26 — Original-asset spike concluded: stay with KO assets

The spike tried several ways to replace KO's content:
- procedural, Blender/MPFB, KayKit, Synty and Meshy assets;
- a Shadow Tower ghoul from a PS1 disc;
- Demon's Souls characters, including a clean-room Havok wavelet decoder, its
  level 1-1, and its characters on KO's Moradon.

The user's conclusion: "for now we'll stick with all the KO assets". The spike was
merged (D-127) and its tooling kept as opt-in exploration paths.

Lessons for later:
- **Level fit:** corridor-style levels such as Demon's Souls fit KO's open,
  height-mapped zones poorly. Games with heightmap and tile terrain fit n3e's
  world format best.
- **Shippable art:** 0 A.D. (CC BY-SA 3.0) and Ryzom (CC BY-SA 3.0 / FAL 1.3)
  are the licensed candidates if shippable art is ever needed.
- **KO relatives:** Hero Online and Legend of Ares remain the closest technical
  relatives for a second player-supplied game.

Evidence.

