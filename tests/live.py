#!/usr/bin/env python3
"""Every disposable live and database suite, several at a time (PQ-001, PQ-114).

  python tests/live.py                 prepare, check coverage, run every suite
  python tests/live.py NAME...         the same, for the named suites only
  python tests/live.py --jobs=N        run at most N suites at once (default 4;
                                       --jobs=1 is the old one-at-a-time run)
  python tests/live.py --tick-ms=N     opt-in developer knob: server tick for the
                                       `scaled` suites (default 50, the production
                                       tick; 25 halves their timer waits)
  python tests/live.py --list          list suites, what each holds, and opt-ins
  python tests/live.py --no-prepare    skip the image and fixture builds
  N3E_LIVE_DISPLAY=desktop python tests/live.py
                                       graphical clients as windows on the desktop,
                                       one suite at a time (default offscreen:
                                       no window, on the GPU, overlapping)

`make live` builds the client, tools client, server and packages first, then runs
this (LIVE_JOBS=N, LIVE_TICK_MS=N, LIVE_DISPLAY=desktop and LIVE_SUITES=name...
pass through). Needs Docker and a hardware GPU.
Each suite makes its own containers, Compose project and realm and removes them;
no default volume or persistent stack is touched.

Graphical branches (PQ-116). With N3E_GRAPHICAL=1 in the environment, which the
suites inherit and `make live` sets unless LIVE_GRAPHICAL=0, the suites marked
`graphical` also start real build/client test clients, n3e-test-client (PQ-006:
the player n3e-client has no replay mode), for two-client captures and keyboard
replays. Such a suite passes only if its log carries the PASS line its graphical
branch prints; any UNVERIFIED line fails it. On a software rasteriser
(N3E_REQUIRE_HARDWARE_GL=1, set for every suite then) the client exits non-zero,
so the suite fails.
LIVE_GRAPHICAL=0 (N3E_GRAPHICAL unset) is a developer run that says so in its
summary.

Where the clients draw (PQ-121). By default (N3E_LIVE_DISPLAY empty or offscreen) every suite
gets SDL's offscreen video driver (SDL_VIDEO_DRIVER): each client renders on the
GPU through EGL into a pbuffer, with no window and no compositor, and paces its
swaps to 60 Hz (client/render/viewer.cpp, test client only). WAYLAND_DISPLAY and DISPLAY are
removed from the suites' environment, so a client that did not take the
offscreen driver fails ("No available video device") instead of opening a window
on the desktop. Nothing reaches the user's desktop or takes its focus, the
graphical suites hold nothing and overlap like the rest, and the replays' focus
and pointer events are the scripted ones only. Before any suite starts the run
opens one offscreen client (GPU_PROBE) and fails at once, LIVE_FAIL, if it does
not report a hardware renderer: no GPU, no EGL device, or a software rasteriser
fails the run, as a missing display did. Its renderer string is printed and kept
in summary.json. N3E_LIVE_DISPLAY=desktop (make live LIVE_DISPLAY=desktop) is the
PQ-116 behaviour for watching: real windows on WAYLAND_DISPLAY or DISPLAY, which
must be set, one graphical suite at a time (they hold "display": the tiling window
manager resizes windows sharing a workspace), taking the desktop's focus.

Concurrency. Up to --jobs suites run at once, each in a numbered slot. A slot owns
a loopback port range below the kernel ephemeral range, used by free_ports, and
the feature `prepare` chains are cooked once per run (tests/isolation.py). What a
suite still shares with others is declared in its `holds`: a suite starts only
when no running suite holds any of the same resources (see HOLDS). Suites that
hold resources start first, longest first by the last recorded durations
(build/live/durations.json), then the rest longest first. A failure never retries.

Test networks (PQ-457, D-229). Each suite also claims a Docker network from a fixed,
host-wide pool for as long as it runs (tests/isolation.py claim_network): its
Compose stack uses it as the project's default network (DISPOSABLE_COMPOSE), so
no bridge is created or removed per suite, and no other running suite, of this run
or another runner, is on it. Its result in summary.json names the network. What a
suite leaves on its network is removed when it ends (its logs saved with the
suite's container logs) and fails the suite; what an interrupted run left is
removed by the next claim of that network, its logs saved under
build/live/swept/<time>-<network>/ (the newest KEEP_RUNS kept). The suite runs as
the leader of its own session, which the claim records: a suite that outlives
its runner (SIGKILL, or a teardown still running when an interrupted runner
exits) keeps its network until every process of that session has exited.

Logs go to build/live/<name>.log and a summary to build/live/summary.json; PASS
and FAIL lines print in suite order, each as soon as it and every suite before it
has finished. The exit status is non-zero if any suite fails or the coverage check
finds an unowned suite or test.

Kept logs (PQ-128). Those paths are overwritten by the next run, and so are the
logs the suites write themselves (build/ko-06/live-server.log and the like). When
a suite or prepare step fails, its runner log and every log it wrote are copied
to build/live/failed/<run>/<suite>/ (<run> is the start time and process id),
which the FAIL line, the LIVE_FAIL line and summary.json ("kept") name; the
newest KEEP_RUNS such runs are kept and older ones removed, and a file longer
than KEEP_FILE_BYTES keeps its end. Nothing here hard-codes a suite's paths: a
suite reports them by writing them. The audit hook (tests/live_reads) lists each
*.log or *.txt file under build/ that a process of the suite opens for writing
(server, client and database logs, which the suites redirect into files they
open) in the suite's N3E_LIVE_KEEP file the moment it is opened, and the suite
saves its containers' output before removing them into its N3E_LIVE_LOGS
directory (tests/isolation.py container_logs), which is kept whole. build/ is
ignored by git, so kept logs never reach a commit; they are local only and may
hold the run's test-only credentials, so nothing prints their contents.

Host network record (PQ-456). A host event (a VPN connect installing ip rules and
an nft chain, a firewall reload) fails many suites at once with only symptoms in
their logs. From the start of the run to its end, tests/host_network.py samples
`ip rule`, `ip route` and the nft ruleset (when readable; nft needs root) every
few seconds, without the run's own Docker interfaces, Docker's nft chains and
route lifetimes. When a suite or prepare step fails, the run writes
build/live/failed/<run>/host.txt: its first and last failure times, each
source's digests at the start and the end, every change seen, and the network
services' journal around each failure (an allowlist, tests/host_network.py). The LIVE_FAIL
line ends with "host-network-changed" when any readable digest left its start
value during the run, and summary.json carries the digests ("host"). Diagnosis
only: no suite is retried, skipped or passed because of it.

Tick scale (PQ-115). Rules count server ticks, and a suite waiting on game timers
spends real time. By default every suite runs at the production 50 ms tick.
--tick-ms=N (make live
LIVE_TICK_MS=N, 10-49) is an opt-in developer knob: a suite marked `scaled` then
gets N3E_LIVE_TICK_MS=N and gives its server that tick, which the server accepts
only for a disposable test- realm (server/src/clock.rs, tests/timescale.py); its
tick-derived waits shrink with it, and wall-time bounds (leases, idle deadlines,
login limits, loot TTLs) stay as they are. A `graphical` suite stays at 50 ms
when N3E_GRAPHICAL=1: the client assumes 50 ms ticks (client/render/melee.h,
player_pose.h, hotbar.h), so a window against a faster server would not show
what a player sees. The tick of each suite is in summary.json. A scaled default
would drop those suites' only production-tick coverage (PQ-127).

Chance (PQ-123). The server rolls every strike, and load stretches wall time, so a
fight whose outcome rests on hit rolls is bounded by resolved strikes, approach
moves or swings (tests/world_peer.py Budget), never by elapsed seconds, with the
strike limit chosen from the fixture's hit rate. A death the suite does not test
is made impossible by the fixture (PQ-112) or, where the package is the shipped
one, met as a player would: respawn and fight again (the --check session).

Suites that need player-supplied KO assets or a local KO stack are in OPT_IN with
the reason, and never run here: `make live-ko` (tests/live_ko.py, PQ-111) cooks
their packages from the player's own KO data, gives each a disposable stack and
runs them with this runner, reporting a suite whose input is missing as NOT RUN.


Disposable Postgres (PQ-207, D-155). Every suite's Postgres skips fsync
(tests/isolation.py DISPOSABLE_POSTGRES and DISPOSABLE_COMPOSE, PQ-205). The same
hook refuses any command a process of the run starts that would create a
Postgres cluster without them (tests/disposable.py), and the run fails with an
UNDISPOSABLE line for each, so a new suite cannot bring back the shared-disk
commit stalls that ended realms' admission under the parallel load.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/live"
TIMEOUT = 1800
PY = sys.executable
# Measured on the reference machine (PQ-114 evidence): 4 is the default.
JOBS = 4
# Server tick for `scaled` suites (PQ-115): the production 50 ms by default, and
# --tick-ms=25 is the measured developer setting; 10 lost fights
# to harness reaction time. tests/timescale.py and server/src/clock.rs accept 10-50.
NOMINAL_TICK_MS, MIN_TICK_MS = 50, 10
TICK_MS = NOMINAL_TICK_MS
# Each slot's free_ports range; must end below the kernel ephemeral range.
PORT_BASE, PORT_SPAN = 20000, 500
# PQ-128: failed runs whose logs are kept under OUT/failed (newest first), and the
# most of one file kept (its end: where a failure is).
KEEP_RUNS = 10
KEEP_FILE_BYTES = 16 << 20
sys.path.insert(0, str(ROOT / "tests"))
import host_network  # noqa: E402
import isolation  # noqa: E402
import schema  # noqa: E402

PREPARE = [
    # Compose suites use the n3e-foundation image with --no-build; rebuild it so
    # they never test a stale server.
    ["docker", "compose", "build", "server"],
    [PY, "tools/assetc/main.py", "tests/fixtures/legacy-demo", "build/packages/legacy-demo"],
    # PQ-006: make live built both clients of both build directories; the player
    # ones (n3e-client) must carry no test harness. The suites run n3e-test-client.
    [PY, "tests/player_build.py", "--require-tools"],
    [PY, "tools/assetc/movement_fixture.py"],
    [PY, "tools/assetc/melee_fixture.py"],
    [PY, "tools/assetc/damage_fixture.py"],
    [PY, "tools/assetc/npc_fixture.py"],
    ["bash", "deploy/local-ca.sh"],
]
# Every Python process the run starts gets this directory on PYTHONPATH; its
# sitecustomize records the log files a suite opens (kept logs, PQ-128).
READS_HOOK = "tests/live_reads"
# PQ-207: the hook also refuses a non-disposable Postgres start (tests/disposable.py).
# tests/live_ko.py uses the same runner and check (PQ-208).
REQUIRE_DISPOSABLE = True


# Resources a suite holds for its whole run; two suites holding the same one never
# overlap. Everything not listed here is per suite (uuid container, Compose project
# and realm names, Docker-published or slot-range ports, own build/ output
# directories) or cooked once per run (tests/isolation.py once_per_run).
HOLDS = {
    # Only with N3E_GRAPHICAL=1 (make live's default) and N3E_LIVE_DISPLAY=desktop: the
    # suites marked `graphical` start build/client windows only then (each checks
    # os.environ["N3E_GRAPHICAL"] == "1"), and then hold "display": the tiling
    # window manager resizes windows sharing a workspace. Offscreen (the default,
    # PQ-121) they have no window and hold nothing. The session suites run
    # --*-check without --graphical, so their tools/demo_session.py graphical
    # replays (line 425) do not run here; PQ-122.
    "display": "starts graphical client windows (N3E_GRAPHICAL=1, N3E_LIVE_DISPLAY=desktop)",
    # tools/assetc life_fixture.cook() re-cooks build/packages/{movement, camera,
    # melee,damage,npc,life} from build/ko-01/source, which life_live then edits
    # in place; assetc replaces a package by removing and recopying it.
    "ko-01": "cooks or reads the build/ko-01 fixture packages",
    # progression_fixture/loot_fixture re-cook build/packages/progression-lab.
    "progression-lab": "cooks or reads build/packages/progression-lab",
}


GRAPHICAL = os.environ.get("N3E_GRAPHICAL") == "1"
# PQ-121: where graphical clients draw, from N3E_LIVE_DISPLAY (make live
# LIVE_DISPLAY=desktop; empty is offscreen). Read when a suite is defined (its "display" hold) and when it
# runs (display_env); a runner reusing this module (tests/live_ko.py, PQ-129)
# keeps it and defines its suites after importing this module.
DISPLAYS = ("offscreen", "desktop")
DISPLAY = os.environ.get("N3E_LIVE_DISPLAY") or "offscreen"
# The probe client and package (cooked by PREPARE): --smoke renders 60 frames. Every
# client a suite starts is the test client, n3e-test-client (PQ-006).
GPU_PROBE = ["build/client/n3e-test-client", "build/packages/legacy-demo", "--smoke"]


def display_env():
    """What a suite's processes get under N3E_GRAPHICAL=1. Clients inherit it and
    exit non-zero on a software rasteriser (client/render/viewer.cpp), so a
    missing GPU fails the suite. Offscreen, they get SDL's offscreen driver and
    lose the desktop's display variables (None removes a variable, see run())."""
    if not GRAPHICAL:
        return {}
    env = {"N3E_REQUIRE_HARDWARE_GL": "1"}
    if DISPLAY == "offscreen":
        # SDL 3 reads SDL_VIDEO_DRIVER; SDL_VIDEODRIVER is its SDL 2 name, set
        # too so a shell's leftover one cannot select another driver.
        env.update({"SDL_VIDEO_DRIVER": "offscreen", "SDL_VIDEODRIVER": "offscreen",
                    "WAYLAND_DISPLAY": None, "DISPLAY": None})
    return env


def gpu_probe():
    """Open one offscreen client with the suites' environment. Returns (renderer
    string or None, problem or None); a problem fails the run before any suite."""
    log = OUT / "gpu-probe.log"
    try:
        code = run(GPU_PROBE, log, env=display_env(), timeout=120)
        text = log.read_text(errors="replace")
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"probe could not run: {error!r}"
    renderer = re.search(r"^backend=(\S+) .*? renderer=(.*?) version=", text, re.M)
    if code != 0 or not renderer:
        last = [l for l in text.splitlines() if l.strip()][-1:] or ["(no output)"]
        return None, f"exit {code}: {last[0][:300]}"
    if renderer.group(1) != "offscreen":
        return renderer.group(2), f"client used the {renderer.group(1)} video driver, not offscreen"
    return renderer.group(2), None


def suite(name, *argv, covers=(), env=None, holds=(), graphical=None, scaled=False):
    """`graphical`: the PASS line the suite prints only from its graphical branch,
    which runs when N3E_GRAPHICAL=1. The suite then passes only if that line is in
    its log (and holds "display" when the clients are desktop windows), so a branch that silently stops running fails.
    `scaled`: the suite derives its waits from tests/timescale.py and gives its
    server the run's tick (PQ-115)."""
    script = next((a for a in argv if a.endswith(".py")), None)
    assert set(holds) <= HOLDS.keys() - {"display"}, holds
    holds = [*holds, *(["display"] if graphical and GRAPHICAL and DISPLAY == "desktop" else [])]
    return {"name": name, "argv": [PY if a == "python" else a for a in argv], "graphical": graphical,
            "covers": sorted({script, *covers} - {None}), "env": env or {}, "holds": sorted(holds),
            "scaled": scaled}


def session(name, *flags, covers=()):
    # tools/demo_session.py gives its server the tick and refuses a graphical
    # replay while scaled; the --*-check runs here never start a client.
    return suite(name, "python", "tools/demo_session.py", *flags, covers=covers, scaled=True)


# Output order: database suites first (isolated Postgres only), then Compose, then
# native-server protocol suites. Start order is by `holds` and duration (main).
SUITES = [
    *[suite(p.stem, "python", f"tests/{p.name}") for p in sorted((ROOT / "tests").glob("*_db.py"))],
    # tests/peer.cpp builds build/client/n3e-peer, which multiplayer runs (PQ-123).
    suite("multiplayer", "python", "tests/multiplayer.py", covers=["tests/schema.py", "tests/peer.cpp"],
          graphical="PASS two simultaneous graphical clients rendered networked entities"),
    suite("gameplay", "python", "tests/gameplay.py", covers=["tests/schema.py"],
          graphical="PASS simultaneous graphical combat walkthrough"),
    suite("movement_live", "python", "tests/movement_live.py", holds=["ko-01"],
          graphical="PASS two real graphical clients at different frame rates"),
    # PQ-129 (PQ-239): the field input replay's right drag offscreen, on the demo package.
    suite("play_replay_live", "python", "tests/play_replay_live.py",
          graphical="PASS demo package right drag/release, zoom, click travel, HUD/chat and target replay"),
    suite("melee_live", "python", "tests/melee_live.py", holds=["ko-01"],
          graphical="PASS real graphical melee at two frame rates"),
    suite("damage_live", "python", "tests/damage_live.py", holds=["ko-01"], scaled=True),
    suite("npc_live", "python", "tests/npc_live.py", holds=["ko-01"],
          graphical="PASS graphical chase/attack/return/recovery capture"),
    suite("life_live", "python", "tests/life_live.py", holds=["ko-01"], scaled=True),
    suite("loot_live", "python", "tests/loot_live.py", holds=["progression-lab"],
          graphical="two graphical clients: shared kill XP, owner drop and keyboard claim/result/inventory: pass"),
    suite("progression_live", "python", "tests/progression_live.py", holds=["progression-lab"]),
    suite("readiness_live", "python", "tests/readiness_live.py"),
    # specs/03-admin-api.md (M1): tokens, bearer auth, drain/notice/deploy-pending, realm:events.
    suite("admin_api_live", "python", "tests/admin_api_live.py"),
    # specs/01-connection-hardening.md (M2): admission limits, idle, drain, PROXY v2, cost.
    suite("connections_live", "python", "tests/connections_live.py"),
    # Spec 02 (M3): Discord login against a loopback stand-in, sessions, kick, ban, mute.
    suite("discord_login_live", "python", "tests/discord_login_live.py",
          graphical="PASS client expiry: the server says expired, the client drops session.json and runs the browser flow"),
    # Spec 05 (M6): the Discord bot against stand-ins for Discord's gateway/REST and GitHub.
    suite("bot_live", "python", "tests/bot_live.py"),
    # Spec 04 (M4): the launcher against releases on a loopback file server; the
    # graphical branch runs the real client from a release against a native server.
    suite("launcher_live", "python", "tests/launcher_live.py",
          graphical="PASS graphical update required: the realm refuses other content, the real client exits 3, "
                    "the launcher exits 20"),
    # PQ-405 (D-208): refusals name their request; the client routes them by it.
    # PQ-406 (D-209): chat and whisper refusals reach the HUD message line;
    # PQ-407 (D-210): its log keeps two rows, each in its kind's colour;
    # PQ-408 (D-211): its scroll bar scrolls back through a bounded history.
    suite("refusal_routing_live", "python", "tests/refusal_routing_live.py",
          graphical="PASS client refusal routing: a movement refusal left the bag, storage, friends and party lines; "
                    "the bag and party refusals reached only their own line; "
                    "the chat and private message refusals reached only the HUD message line, "
                    "which kept the newest two messages, refusals in the package's refusal colour and a client notice in its notice colour"),
    # PQ-249: N3N3 NPC templates on a synthetic engine 37 package, native server.
    suite("npc_templates_live", "python", "tests/npc_templates_live.py",
          graphical="PASS graphical client renders the N3N3 package"),
    # PQ-250: 1,300 NPCs, 48 sessions in one crowded window, native server.
    suite("npc_population_live", "python", "tests/npc_population_live.py",
          graphical="PASS graphical client renders the crowded window"),
    # PQ-253: per-template NPC models (N3LK + N3NM, engine 38) on a synthetic
    # package, native server; the 52-looks load bound offscreen.
    suite("npc_looks_live", "python", "tests/npc_looks_live.py",
          graphical="PASS graphical client draws two templates side by side with their own models"),
    # PQ-265: NPC looks models with render states (N3SM clips, N3MM, engine 39)
    # on a synthetic package, native server.
    suite("npc_materials_live", "python", "tests/npc_materials_live.py",
          graphical="PASS graphical client draws NPC looks runs with their render states"),
    # PQ-272: per-template NPC drawn scale (N3N4, engine 41) on a synthetic
    # package, native server: one looks model at two templates' scales.
    suite("npc_scale_live", "python", "tests/npc_scale_live.py",
          graphical="PASS graphical client draws one looks model at each template's scale"),
    # PQ-211: effects on equipped appearance keys (N3E2) on the PQ-272 package,
    # native server: the local and the other player, the option off.
    suite("appearance_effects_live", "python", "tests/appearance_effects_live.py",
          graphical="PASS graphical client draws the equipped-item effect on the local and the other player"),
    # PQ-315: the 2233 equipment glow on equipped appearance keys (N3E3) on the
    # PQ-272 package, native server: both players, the pulse, the option off.
    suite("equipment_glow_live", "python", "tests/equipment_glow_live.py",
          graphical="PASS graphical client draws the equipment glow on the local and the other player"),
    # PQ-348: an equipped part drawn with its KO part render state (N3D3) on the
    # PQ-315 package, native server: blend factors, the alpha reference, both
    # faces, with and without the glow, on the local and the other player.
    suite("appearance_states_live", "python", "tests/appearance_states_live.py",
          graphical="PASS graphical client draws the equipped part with its render state on the local and the other player"),
    # PQ-328: the 2233 attached characters (N3AT) on the PQ-272 package with two
    # cospre slots, native server: the server's slot authority, the wing on both
    # players on the wearer's joint, the pulse, the shared clock, the option off.
    suite("attached_characters_live", "python", "tests/attached_characters_live.py",
          graphical="PASS graphical client draws the attached wing on the local and the other player"),
    # PQ-317: skeletal weapon plugs (N3AT plug entries) on the PQ-328 package,
    # native server: the server's slot authority, the bow on both players at
    # joint x placement from the drawn vertices, its clip on its own clock.
    suite("skeletal_plugs_live", "python", "tests/skeletal_plugs_live.py",
          graphical="PASS graphical client draws the animated skeletal bow on the local and the other player"),
    # PQ-416: a ranged basic attack (N3RB) on the PQ-249 package, native server:
    # the server's ranged limit from committed equipment, no chase in the client.
    suite("ranged_attack_live", "python", "tests/ranged_attack_live.py",
          graphical="PASS graphical client does not chase a target beyond the ranged limit"),
    # PQ-316: the 2233 screen bloom and tone map (N3PF) on the PQ-272 package,
    # offline client: a known picture's every stage, adaptation, on and off.
    suite("postprocess_live", "python", "tests/postprocess_live.py",
          graphical="PASS graphical client draws the HDR bloom and tone map on and off"),
    # PQ-354: item tooltip heads (N3IH) on the PQ-272 package with a synthetic
    # N3H7 HUD, native server: the head's colours and lines, the self-name token.
    suite("item_heads_live", "python", "tests/item_heads_live.py",
          graphical="PASS graphical client draws the item tooltip head"),
    # PQ-251: KO reference stats (synthetic K_MONSTER/K_NPC/K_NPCPOS rows) cooked
    # into N3N3 templates by tools/assetc/ko_npc.py, native server; no client.
    suite("npc_reference_stats_live", "python", "tests/npc_reference_stats_live.py"),
    # PQ-252: KO reference combat and XP (sDamage, sAc, sHitRate, sEvadeRate,
    # iExp) cooked into N3N3 templates, native server; no client.
    suite("npc_reference_combat_live", "python", "tests/npc_reference_combat_live.py"),
    # PQ-379: a world alpha part (N3L4, D-201) drawn between two non-additive
    # effects in the one far-to-near pass, on the PQ-249 package; offline client.
    suite("world_alpha_live", "python", "tests/world_alpha_live.py",
          graphical="PASS graphical client draws the world alpha part between the effects in one far-to-near pass"),
    # PQ-380: the target marker's part drawn between two non-additive effects
    # in the one far-to-near pass, on the PQ-249 package; offline client.
    suite("target_marker_order_live", "python", "tests/target_marker_order_live.py",
          graphical="PASS graphical client draws the target marker between the effects in one far-to-near pass"),
    # PQ-231/PQ-232: synthetic N3W2 world at map size, streamed; no containers.
    suite("world_chunks_live", "python", "tests/world_chunks_live.py",
          graphical="PASS N3W2 streaming: a corrupt chunk in the far corner stops the client when reached"),
    # PQ-234: the KO bake writes N3W2 + N3WT for a synthetic 513-sample zone; no containers.
    suite("ko_world_live", "python", "tests/ko_world_live.py",
          graphical="PASS KO N3W2 graphical: the baked 2048 m zone draws"),
    # PQ-217: the zone overview map on the basic HUD (N3HE), synthetic package.
    suite("overview_map_live", "python", "tests/overview_map_live.py",
          graphical="PASS N3HE overview map graphical"),
    suite("administration", "python", "tests/administration.py",
          graphical="PASS simultaneous tools publisher/normal observer and normal/tools observers after restart; NPC info line only with the projected server.inspect; traced NPC state only to the holder; operator chat colour only on a server-marked line"),
    session("session_check", "--check"),
    session("session_restart", "--restart-check"),
    session("session_lifecycle", "--lifecycle", covers=["tests/session_lifecycle.py"]),
    session("chat_channels", "--chat-check", covers=["tests/chat_channels.py"]),
    session("inventory_live", "--inventory-check", covers=["tests/inventory_live.py"]),
    session("commerce_live", "--commerce-check", covers=["tests/commerce_live.py"]),
    session("repair_live", "--repair-check", covers=["tests/repair_live.py"]),
    session("equipment_live", "--equipment-check", covers=["tests/equipment_live.py"]),
    session("stats_live", "--stats-check", covers=["tests/stats_live.py"]),
    session("wear_live", "--wear-check", covers=["tests/wear_live.py"]),
    session("storage_live", "--storage-check", covers=["tests/storage_live.py"]),
    session("storage_auth_live", "--storage-auth-check", covers=["tests/storage_auth_live.py"]),
    session("friends_live", "--friends-check", covers=["tests/friends_live.py"]),
    session("friends_live_full", "--friends-check", "--friends-full", covers=["tests/friends_live.py"]),
    session("party_live", "--party-check", covers=["tests/party_live.py"]),
    session("party_rewards_live", "--party-rewards-check", covers=["tests/party_rewards_live.py"]),
    session("reward_upgrades_live", "--reward-upgrade-check", covers=["tests/reward_upgrades_live.py"]),
    session("party_loot_live", "--party-loot-check", covers=["tests/party_loot_live.py"]),
    session("coin_loot_live", "--coin-loot-check", covers=["tests/coin_loot_live.py"]),
    session("item_drops_live", "--item-drops-check", covers=["tests/item_drops_live.py"]),
]

# Run by `make live-ko` (tests/live_ko.py), never here; it checks it owns exactly these.
LOCAL_KO = "needs the KO package build/packages/moradon cooked from player-supplied data (D-127); make live-ko"
OPT_IN = {
    "tests/turbo_live.py": LOCAL_KO,
    "tests/camera_legacy_live.py": "needs the local KO field package build/packages/ko-field; make live-ko",
    "tests/field_live.py": "needs a local KO field stack (build/packages/ko-field); make live-ko",
    "tests/ko_presentation_live.py": "needs the local KO field sources build/ko-source/field; make live-ko",
    **{f"tests/moradon_{n}_live.py": "needs a local Moradon stack (build/packages/moradon); make live-ko"
       for n in ["combat_potions", "features", "melee_sequence", "panels", "skills", "uif", "weapon_effects", "worm"]},
    "tests/moradon_glow_live.py": "needs the Moradon glow package (build/packages/moradon-glow2233) cooked from "
                                  "player-supplied 1298 and 2145 data; make live-ko",
    "tests/moradon_skeletal_plug_live.py": "needs the Moradon glow package (build/packages/moradon-glow2233) "
                                          "cooked from player-supplied 1298 and 2145 data; make live-ko",
    "tests/moradon_armour_live.py": "needs the Moradon glow package (build/packages/moradon-glow2233) cooked "
                                    "from player-supplied 1298 and 2145 data; make live-ko",
    "tests/moradon_layout_live.py": "needs the classic or 1097 Moradon package (build/packages/moradon-classic, "
                                    "moradon-1097) cooked from player-supplied data; make live-ko",
    "tests/ko_terrain_overlay_live.py": "needs the Moradon and homeland packages cooked from player-supplied "
                                        "data (light maps, PQ-387); make live-ko",
    "tests/ko_event_shapes_live.py": "needs the Karus homeland package (build/packages/ko-zone-10) cooked from "
                                     "player-supplied data and START_POSITION export (PQ-392); make live-ko",
    "tests/ko_object_npc_shapes_live.py": "needs the Moradon package (build/packages/moradon) cooked from "
                                         "player-supplied data (PQ-395); make live-ko",
    "tests/ko_material_shapes_live.py": "needs the 1097 Moradon package (build/packages/moradon-1097) cooked "
                                       "from player-supplied data (PQ-412); make live-ko",
    "tests/homeland_live.py": "needs the KO homeland packages (build/packages/ko-zone-10, -20, "
                              "ko-1097-zone-1, -2) cooked from player-supplied data and START_POSITION "
                              "export; make live-ko",
}


def reads_env():
    """What every process of the run gets so the audit hook records its reads."""
    hook = str(ROOT / READS_HOOK)
    path = os.environ.get("PYTHONPATH")
    return {"PYTHONPATH": hook + (os.pathsep + path if path else ""), "N3E_LIVE_READS": str(OUT / "reads"),
            "N3E_LIVE_DISPOSABLE": "1" if REQUIRE_DISPOSABLE else None}


def undisposable(directory):
    """The non-disposable Postgres starts the hook refused (PQ-207), one line each."""
    lines = set()
    for record in Path(directory).glob("*.undisposable"):
        lines.update(l for l in record.read_text(errors="replace").splitlines() if l.strip())
    return sorted(lines)


def coverage():
    """Names of live/db suites and ignored Rust tests with no owner here."""
    run_set = {f for s in SUITES for f in s["covers"]}
    missing = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "tests").glob("*_live.py"))
               + sorted((ROOT / "tests").glob("*_db.py"))]
    missing = [p for p in missing if p not in run_set and p not in OPT_IN]
    missing += [f"{p} (opt-in entry has no file)" for p in OPT_IN if not (ROOT / p).is_file()]
    listed = subprocess.run(["cargo", "test", "--locked", "--", "--ignored", "--list"], cwd=ROOT,
                            capture_output=True, text=True)
    if listed.returncode:
        return missing + ["cargo test --list failed:\n" + listed.stderr[-2000:]]
    makefile = (ROOT / "Makefile").read_text()
    owners = "\n".join((ROOT / f).read_text() for f in run_set if f.endswith(".py"))
    owners += "".join((ROOT / f).read_text() for f in set(re.findall(r"tests/\w+\.py", makefile)))
    rust = "".join(p.read_text() for p in (ROOT / "server/src").glob("*.rs"))
    for line in listed.stdout.splitlines():
        if not line.endswith(": test"):
            continue
        test = line[: -len(": test")]
        # Owned when a run suite or `make test` names it, it is a shared-schema
        # test, or the server re-executes it as a fault worker child.
        if test in schema.CORE_TESTS or f"'{test}'" in owners or f'"{test}"' in owners:
            continue
        if test.endswith("::fault_worker") and f'"{test}"' in rust:
            continue
        missing.append(f"ignored Rust test {test}")
    return missing


def run(command, log, env=None, timeout=TIMEOUT, procs=None, started=None):
    """Run in its own session and process group; on timeout SIGINT first so
    cleanup runs. `procs` registers the child so an interrupted parallel run can
    stop it; `started` is called with its pid (= its session id) once it runs."""
    with log.open("w") as out:
        out.write("$ " + " ".join(command) + "\n")
        out.flush()
        # Spec 03: every server opens an admin listener, 127.0.0.1:7780 unless told
        # otherwise; parallel suites take an ephemeral loopback port instead. Spec 01
        # (Q31): every suite connects from one address (loopback, or the Compose
        # gateway), so the per-source limits are lifted; global and pre-auth stay.
        # Spec 02: the suites log in with account/password fixtures (N3E_LEGACY_LOGIN).
        merged = {"N3E_ADMIN_LISTEN": "127.0.0.1:0", "N3E_IP_MAX_CONCURRENT": "1000000",
                  "N3E_IP_CONNECT_RATE": "1000000", "N3E_LEGACY_LOGIN": "1",
                  **os.environ, **reads_env(), **(env or {})}
        p = subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                             env={k: v for k, v in merged.items() if v is not None}, start_new_session=True)
        if procs is not None:
            procs[p.pid] = p
        if started is not None:
            started(p.pid)
        try:
            return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGINT)
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
            out.write(f"\nlive.py: timeout after {timeout} s\n")
            return "timeout"
        except KeyboardInterrupt:
            os.killpg(p.pid, signal.SIGINT)
            p.wait(timeout=60)
            raise
        finally:
            if procs is not None:
                procs.pop(p.pid, None)


def new_kept_dir():
    """Where this run keeps failed suites' logs; created only when one fails."""
    return OUT / "failed" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"


def suite_log_env(name):
    """A suite's container-log directory (emptied) and its written-log list (removed):
    N3E_LIVE_LOGS and N3E_LIVE_KEEP (tests/isolation.py, tests/live_reads)."""
    logs = OUT / "logs" / name
    shutil.rmtree(logs, ignore_errors=True)
    logs.mkdir(parents=True)
    written = OUT / "logs" / f"{name}.written"
    written.unlink(missing_ok=True)
    return {"N3E_LIVE_LOGS": str(logs), "N3E_LIVE_KEEP": str(written)}


def _copy_end(source, target):
    """Copy `source` to `target`, only its last KEEP_FILE_BYTES if it is longer."""
    target.parent.mkdir(parents=True, exist_ok=True)
    size = source.stat().st_size
    if size <= KEEP_FILE_BYTES:
        shutil.copyfile(source, target)
        return size, size
    with source.open("rb") as src, target.open("wb") as out:
        src.seek(size - KEEP_FILE_BYTES)
        out.write(f"[live.py kept the last {KEEP_FILE_BYTES} of {size} bytes]\n".encode())
        shutil.copyfileobj(src, out)
    return size, KEEP_FILE_BYTES


def keep_failed(name, kept_dir):
    """Copy failed suite or prepare step `name`'s logs to kept_dir/name/: its runner
    log (runner.log), its container logs (containers/) and each file in its
    written-log list at its repository path. Returns that directory relative to
    the repository, ending in '/'."""
    dest = kept_dir / name
    dest.mkdir(parents=True, exist_ok=True)
    index = []

    def take(source, target):
        try:
            size, kept = _copy_end(source, target)
            index.append({"source": source.relative_to(ROOT).as_posix(), "bytes": size, "kept": kept})
        except (OSError, ValueError) as error:
            index.append({"source": str(source), "error": repr(error)})

    take(OUT / f"{name}.log", dest / "runner.log")
    logs = OUT / "logs" / name
    for source in sorted(logs.glob("*")) if logs.is_dir() else []:
        if source.is_file():
            take(source, dest / "containers" / source.name)
    try:
        listed = (OUT / "logs" / f"{name}.written").read_text(errors="replace").splitlines()
    except OSError:
        listed = []
    build, failed = (ROOT / "build").resolve(), (OUT / "failed").resolve()
    for line in dict.fromkeys(l for l in listed if l):
        source = Path(line).resolve()
        # Only logs under build/, never kept copies; the hook lists nothing else.
        if not source.is_relative_to(build) or source.is_relative_to(failed):
            continue
        if source.is_file():
            take(source, dest / source.relative_to(ROOT))
        else:
            index.append({"source": source.relative_to(ROOT).as_posix(), "error": "gone before it was kept"})
    (dest / "kept.json").write_text(json.dumps(index, indent=1) + "\n")
    return dest.relative_to(ROOT).as_posix() + "/"


def prune_failed():
    """Remove all but the newest KEEP_RUNS kept runs (names sort by start time), and
    of the leftover stacks' logs a claim saved (OUT/swept, PQ-457)."""
    for kept in ("failed", "swept"):
        runs = sorted((d for d in (OUT / kept).glob("*") if d.is_dir()), key=lambda d: d.name)
        for old in runs[:-KEEP_RUNS]:
            shutil.rmtree(old, ignore_errors=True)


def host_record(watch, results, kept_dir):
    """PQ-456: stop `watch` (tests/host_network.py, started with the run) and, when
    a suite or prepare step failed, write the host network record to
    kept_dir/host.txt. Returns (its summary.json entry, the text the LIVE_FAIL
    line ends with: "; host-network-changed (...)" when any readable source's
    digest left its start value, else ""). Diagnosis only: it changes no result,
    and a record it cannot write is named in the entry, never an error."""
    watch.stop()
    host = {**watch.summary(), "record": None}
    failures = [(r["name"], r.get("ended") or watch.ended) for r in results if r["exit"] != 0]
    if failures:
        record = kept_dir / "host.txt"
        try:
            host_network.write_record(record, watch, failures)
            host["record"] = record.relative_to(ROOT).as_posix()
        except Exception as error:  # never turns the failure into something else
            host["record"] = f"not written: {error!r}"
    where = f" (see {host['record']})" if host["record"] and not host["record"].startswith("not ") else ""
    return host, (f"; host-network-changed{where}" if host["changed"] else "")


def ephemeral_low():
    try:
        return int(Path("/proc/sys/net/ipv4/ip_local_port_range").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 32768


def tick_of(s, tick_ms):
    """The server tick suite `s` runs at: the run's tick if it is scaled, never for
    a graphical branch (the client assumes 50 ms), else production."""
    return tick_ms if s["scaled"] and not (s["graphical"] and GRAPHICAL) else NOMINAL_TICK_MS


def slot_env(slot):
    """Per-slot port range (tests/isolation.py free_ports) and the run's prepare cache."""
    lo = PORT_BASE + slot * PORT_SPAN
    return {"N3E_TEST_PORTS": f"{lo}-{lo + PORT_SPAN - 1}", "N3E_TEST_PORT_STATE": str(OUT / f"ports-{slot}"),
            "N3E_LIVE_CACHE": str(OUT / "prepared")}


def graphical_verdict(s, code):
    """With N3E_GRAPHICAL=1, a suite that exits 0 still fails when it printed an
    UNVERIFIED line or, if marked graphical, never printed its graphical PASS line."""
    if code != 0 or not GRAPHICAL:
        return code
    try:
        text = (OUT / f"{s['name']}.log").read_text(errors="replace")
    except OSError as error:
        return f"log unreadable: {error!r}"
    if re.search(r"^UNVERIFIED", text, re.M):
        return "UNVERIFIED line under N3E_GRAPHICAL=1"
    if s["graphical"] and s["graphical"] not in text:
        return "graphical branch did not report its PASS line"
    return code


def run_suites(selected, jobs, tick_ms=TICK_MS, kept_dir=None):
    """Run `selected` with at most `jobs` at once and never two that hold the same
    resource. Prints PASS/FAIL in suite order; returns results in suite order. A
    failed suite's logs are kept under `kept_dir` (default: a new one, see
    new_kept_dir) and its result names them ("kept")."""
    kept_dir = kept_dir or new_kept_dir()
    try:
        last = json.loads((OUT / "durations.json").read_text())
    except (OSError, ValueError):
        last = {}
    order = sorted(selected, key=lambda s: (not s["holds"], -last.get(s["name"], 0), selected.index(s)))
    cond = threading.Condition()
    pending, held, slots, done, procs, threads = list(order), set(), list(range(jobs)), {}, {}, []
    printed, began = 0, time.time()

    def work(s, slot):
        t = time.time()
        tick = tick_of(s, tick_ms)
        network = None
        try:
            # PQ-457: the suite's Compose stack goes on a test network of its own
            # for the run (tests/isolation.py claim_network), which no other
            # running suite, here or in another runner on the host, holds.
            # The suite's session holds the network until its last process exits,
            # even if this runner dies first.
            with isolation.claim_network(logs=OUT / "swept") as claimed:
                network = claimed.name
                # Every suite gets the variable, so one started under a shell that
                # exported it still runs at the tick this run chose.
                logs = suite_log_env(s["name"])
                env = {**s["env"], **slot_env(slot), **display_env(), **logs,
                       **isolation.network_env(network), "N3E_LIVE_TICK_MS": str(tick)}
                code = run(s["argv"], OUT / f"{s['name']}.log", env=env, procs=procs, started=claimed.hold)
                code = graphical_verdict(s, code)
                # PQ-128: their logs go with the suite's container logs, kept if it fails.
                left = isolation.sweep_network(network, logs["N3E_LIVE_LOGS"])
            with (OUT / f"{s['name']}.log").open("a") as out:
                out.write(f"\nlive.py: test network {network}"
                          f"{' (created for this suite)' if claimed.created else ''}\n")
                if claimed.swept:
                    out.write(f"live.py: removed what an earlier run left on {network} before the suite: "
                              f"{' '.join(claimed.swept)} (their logs: "
                              f"{claimed.swept_logs.relative_to(ROOT).as_posix()}/)\n")
                if left:
                    out.write(f"live.py: the suite left containers on {network}; removed: {' '.join(left)} "
                              f"(their logs: left-*.log with its container logs)\n")
            if left and code == 0:
                code = f"left {len(left)} containers on its test network {network}"
        except Exception as error:  # a runner fault is a failed suite, never a pass
            code = f"runner error: {error!r}"
        kept = None
        if code != 0:
            try:
                kept = keep_failed(s["name"], kept_dir)
            except Exception as error:  # never turns the failure into something else
                kept = f"not kept: {error!r}"
        with cond:
            done[s["name"]] = {"name": s["name"], "exit": code, "seconds": round(time.time() - t),
                               "slot": slot, "network": network, "start": round(t - began), "tick_ms": tick,
                               "kept": kept, "ended": round(time.time(), 3)}
            held.difference_update(s["holds"])
            slots.append(slot)
            slots.sort()
            cond.notify_all()

    try:
        with cond:
            while True:
                while printed < len(selected) and selected[printed]["name"] in done:
                    r = done[selected[printed]["name"]]
                    why = f"  ({r['exit']})" if isinstance(r["exit"], str) else ""
                    why += f"  logs kept in {r['kept']}" if r["kept"] else ""
                    print(f"{'PASS' if r['exit'] == 0 else 'FAIL'} {r['seconds']:>5}s  {r['name']}{why}", flush=True)
                    printed += 1
                if printed == len(selected):
                    break
                while slots:
                    ready = next((s for s in pending if not held.intersection(s["holds"])), None)
                    if ready is None:
                        break
                    pending.remove(ready)
                    held.update(ready["holds"])
                    thread = threading.Thread(target=work, args=(ready, slots.pop(0)), daemon=True)
                    thread.start()
                    threads.append(thread)
                cond.wait(timeout=1)
    except KeyboardInterrupt:
        for p in list(procs.values()):
            os.killpg(p.pid, signal.SIGINT)
        for thread in threads:
            thread.join(timeout=70)
        raise
    last.update({r["name"]: r["seconds"] for r in done.values()})
    (OUT / "durations.json").write_text(json.dumps(dict(sorted(last.items())), indent=1) + "\n")
    return [done[s["name"]] for s in selected]


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    options = [a for a in argv[1:] if a.startswith("--")]
    jobs, tick_ms = JOBS, TICK_MS
    for option in options:
        if option.startswith("--jobs=") and option[7:].isdigit() and int(option[7:]) >= 1:
            jobs = int(option[7:])
        elif (option.startswith("--tick-ms=") and option[10:].isdigit()
              and MIN_TICK_MS <= int(option[10:]) <= NOMINAL_TICK_MS):
            tick_ms = int(option[10:])
        elif option not in ("--list", "--no-prepare"):
            raise SystemExit(f"live.py: unknown option {option}; see the module docstring")
    if PORT_BASE + jobs * PORT_SPAN > ephemeral_low():
        raise SystemExit(f"live.py: --jobs={jobs} port ranges would reach the ephemeral range {ephemeral_low()}")
    if "--list" in argv:
        for s in SUITES:
            holds = f"  [holds {', '.join(s['holds'])}]" if s["holds"] else ""
            mark = ("  [graphical]" if s["graphical"] else "") + ("  [scaled]" if s["scaled"] else "")
            print(f"{s['name']:24} {' '.join(Path(a).name if a == PY else a for a in s['argv'])}{holds}{mark}")
        for path, reason in OPT_IN.items():
            print(f"{'(opt-in)':24} {path}: {reason}")
        return 0
    unknown = set(args) - {s["name"] for s in SUITES}
    if unknown:
        raise SystemExit(f"live.py: unknown suite(s) {sorted(unknown)}; see --list")
    # PQ-121: windows need a desktop; offscreen needs a GPU (gpu_probe, below).
    if DISPLAY not in DISPLAYS:
        raise SystemExit(f"LIVE_FAIL live.py: N3E_LIVE_DISPLAY={DISPLAY!r}; use one of {', '.join(DISPLAYS)}")
    if GRAPHICAL and DISPLAY == "desktop" and not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        raise SystemExit("LIVE_FAIL live.py: N3E_LIVE_DISPLAY=desktop needs a display (WAYLAND_DISPLAY or DISPLAY); "
                         "the default, offscreen, needs only a GPU")
    OUT.mkdir(parents=True, exist_ok=True)
    # Prepared packages are cooked once per run (tests/isolation.py); start empty.
    shutil.rmtree(OUT / "prepared", ignore_errors=True)
    shutil.rmtree(OUT / "reads", ignore_errors=True)
    (OUT / "reads").mkdir()
    started = time.time()
    kept_dir = new_kept_dir()
    watch = host_network.Watch().start()
    missing = coverage()
    for m in missing:
        print(f"UNOWNED {m}", flush=True)
    results = []
    if "--no-prepare" not in argv:
        for i, command in enumerate(PREPARE):
            t = time.time()
            code = run(command, OUT / f"prepare-{i}.log", env={"N3E_UID": str(os.getuid()), "N3E_GID": str(os.getgid())})
            kept = keep_failed(f"prepare-{i}", kept_dir) if code != 0 else None
            print(f"{'PASS' if code == 0 else 'FAIL'} {round(time.time() - t):>5}s  prepare: "
                  f"{' '.join(command[1:] if command[0] == PY else command)}{f'  logs kept in {kept}' if kept else ''}",
                  flush=True)
            if code != 0:
                results.append({"name": f"prepare-{i}", "exit": code, "seconds": round(time.time() - t), "kept": kept,
                                "ended": round(time.time(), 3)})
                break
    renderer = None
    if GRAPHICAL and DISPLAY == "offscreen" and not any(r["exit"] for r in results):
        t = time.time()
        renderer, problem = gpu_probe()
        print(f"{'FAIL' if problem else 'PASS'} {round(time.time() - t):>5}s  GPU probe: offscreen renderer "
              f"{renderer or '(none)'}{f' ({problem})' if problem else ''}", flush=True)
        if problem:
            print("LIVE_FAIL live.py: graphical branches need a hardware GPU; the offscreen probe failed "
                  "(build/live/gpu-probe.log)", flush=True)
            results.append({"name": "gpu-probe", "exit": problem, "seconds": round(time.time() - t), "kept": None,
                            "ended": round(time.time(), 3)})
    if not any(r["exit"] for r in results):
        selected = [s for s in SUITES if not args or s["name"] in args]
        scaled = sum(1 for s in selected if tick_of(s, tick_ms) != NOMINAL_TICK_MS)
        print(f"running {len(selected)} suites, at most {jobs} at once, graphical branches "
              f"{f'on ({DISPLAY})' if GRAPHICAL else 'OFF (headless developer run)'}, "
              + (f"{scaled} at a {tick_ms} ms test tick (developer opt-in; the rest at {NOMINAL_TICK_MS} ms)"
                 if tick_ms != NOMINAL_TICK_MS else f"every suite at the production {NOMINAL_TICK_MS} ms tick"), flush=True)
        results += run_suites(selected, jobs, tick_ms, kept_dir)
    failed = [r["name"] for r in results if r["exit"] != 0]
    host, flag = host_record(watch, results, kept_dir)
    kept = kept_dir.relative_to(ROOT).as_posix() + "/" if kept_dir.is_dir() else None
    prune_failed()
    # PQ-207: a Postgres start without the fsync-off options, even one a suite caught.
    refused = undisposable(OUT / "reads")
    for line in refused:
        print(f"UNDISPOSABLE {line} (start it with tests/isolation.py DISPOSABLE_POSTGRES or DISPOSABLE_COMPOSE)",
              flush=True)
    bad = failed or missing or refused
    summary = {"results": results, "failed": failed, "kept": kept, "unowned": missing,
               "undisposable": refused,
               "jobs": jobs, "tick_ms": tick_ms,
               "graphical": GRAPHICAL, "display": DISPLAY if GRAPHICAL else None, "renderer": renderer,
               "opt_in": OPT_IN, "seconds": round(time.time() - started), "host": host}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    # A failed prepare step or GPU probe is in `failed` but is not a suite.
    suites = [r for r in results if not r["name"].startswith("prepare-") and r["name"] != "gpu-probe"]
    ran, passed = len(suites), sum(1 for r in suites if r["exit"] == 0)
    print(f"LIVE_{'FAIL' if bad else 'OK'} {passed}/{ran} suites passed, "
          f"{len(missing)} unowned, {len(refused)} undisposable starts, "
          f"{len(OPT_IN)} opt-in not run, "
          f"{summary['seconds']} s, jobs {jobs}, tick {tick_ms} ms, graphical {f'on ({DISPLAY})' if GRAPHICAL else 'OFF'}; "
          f"logs in build/live/{f'; failed logs kept in {kept}' if kept else ''}{flag if bad else ''}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
