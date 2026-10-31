#!/usr/bin/env python3
"""The opt-in KO live suites, from the player's own KO data (PQ-111).

  python tests/live_ko.py               prepare, then run the 20 suites
  python tests/live_ko.py NAME...       the same, for the named suites only
  python tests/live_ko.py --jobs=N      at most N suites at once (default 4)
  python tests/live_ko.py --no-prepare  use the packages already under build/
  python tests/live_ko.py --list        list the suites and what each needs
  python tests/live_ko.py --check       the harness shape only (no Docker): the
                                        suites are exactly tests/live.py OPT_IN
                                        and every script compiles
  N3E_LIVE_DISPLAY=desktop python tests/live_ko.py
                                        graphical clients as windows on the desktop,
                                        one suite at a time (default offscreen: no
                                        window, on the GPU; PQ-129)

`make live-ko` builds the client and server, then runs this. It is never a
build prerequisite: its inputs are proprietary (AGENTS.md, D-118,
D-127). The KO client data at assets/ko comes from tools/fetch-ko-assets.sh
(UPSTREAM.md); everything cooked from it stays under ignored build/.

Prepare. The n3e-foundation server image and the local CA (as `make live`; the
CA script keeps an existing CA), then the KO packages from that data with the
existing importers, written only below build/live-ko/work (N3E_KO_WORK, which the
suites and tests/ko_stack.py read): `tools/assetc/ko_bake.py 210
--features --into=build/live-ko/work` (packages/moradon, ko-moradon, kx/survey),
`tools/assetc/test_field.py --into=build/live-ko/work` (ko-source/field,
ko-source/player, packages/ko-field) and, for the homeland maps (PQ-218),
`tools/assetc/ko_bake.py 10` and `20 --into=build/live-ko/work`
(packages/ko-zone-10 and -20, ko-zone-10 and -20, kx/survey-10 and -20), which
also need the operator's own START_POSITION export (START_POSITIONS), and, for
the 1097 homelands (PQ-274), `tools/assetc/ko_bake.py 1` and `2 --client=1097
--into=build/live-ko/work` (packages/ko-1097-zone-1 and -2), which also need
the player's 1097 install unpacked by tools/ko-reference/unpack_installer.py
(build/ko-reference/installer-1097; this script does not unpack it), and, for
the classic Moradon (PQ-223), `tools/assetc/ko_bake.py 210 --layout=classic
--features --into=build/live-ko/work` (packages/moradon-classic,
ko-moradon-classic, kx/survey-moradon-classic), and, for the 1097 Moradon
(PQ-224), `tools/assetc/ko_bake.py 21 --client=1097 --features
--into=build/live-ko/work` (packages/moradon-1097, ko-moradon-1097,
kx/survey-moradon-1097), which also needs the unpacked 1097 install, and, for
the 2233 equipment glow (PQ-315), `tools/assetc/ko_bake.py 210 --features
--glow-2233 --into=build/live-ko/work` (packages/moradon-glow2233,
ko-moradon-glow2233, kx/survey-glow2233), which also needs the player's 2145
install unpacked by tools/ko-reference/unpack_inno.py
(build/ko-reference/installer-2145; this script does not unpack it) and, since
PQ-422, the operator's own MAGIC_TYPE2 export (MAGIC_TYPE2:
tools/ko-reference/inspect_db.py --table MAGIC_TYPE2).
build/packages/moradon, build/packages/moradon-classic, build/packages/moradon-1097, build/packages/moradon-glow2233,
build/packages/ko-field and build/packages/ko-zone-*, which the persistent tools/play-moradon,
tools/play-ko-field and tools/play-ko-zone stacks mount, are never written. A step whose
player-supplied input is missing is skipped, and every suite needing it is NOT
RUN with that reason; a step that fails with its input present fails the run.

Stacks. The eight moradon_*_live suites, moradon_glow_live, moradon_skeletal_plug_live
(PQ-317) and moradon_armour_live (PQ-319), both on the same glow package, moradon_classic_live and
moradon_1097_live (tests/moradon_layout_live.py), field_live and the four homeland suites
(tests/homeland_live.py on keys 10 and 20, and on the 1097 keys 1 and 2) each run inside
tests/ko_stack.py, which starts a disposable Compose stack for that suite alone
and removes it afterwards; the persistent tools/play-moradon, play-ko-field and
play-ko-zone stacks and their accounts are never touched. turbo_live, camera_legacy_live and
ko_presentation_live start their own disposable servers already. Every cluster
skips fsync (tests/isolation.py DISPOSABLE_POSTGRES and DISPOSABLE_COMPOSE,
D-155), and the runner's audit hook refuses a Postgres start without them and
fails the run with an UNDISPOSABLE line, as under `make live` (PQ-207, PQ-208,
D-156).

Runner. tests/live.py's: per-suite logs, `holds`, slots and port ranges, the
graphical rules (N3E_GRAPHICAL=1, which `make live-ko` sets unless
LIVE_GRAPHICAL=0: a graphical suite passes only with its graphical PASS line;
any UNVERIFIED line fails it), and its kept logs (PQ-128): a
failed suite's or prepare step's runner log, the logs it wrote and its
containers' logs (tests/ko_stack.py saves the stack's before removing it) go to
build/live-ko/failed/<run>/<suite>/, named in its FAIL line, the last line and
summary.json ("kept"); and its host network record (PQ-456,
tests/host_network.py): build/live-ko/failed/<run>/host.txt when a suite or
prepare step failed, "host-network-changed" on a LIVE_KO_FAIL line when the
host's ip rules, routes or readable nft ruleset changed during the run, and
summary.json's "host". Suites that always start graphical clients are NOT RUN on
a headless run. Logs and summary.json go to build/live-ko/.

Display (PQ-129, D-193). As under `make live` (PQ-121), the clients render
offscreen on the GPU by default: every suite gets SDL's offscreen video driver
and loses WAYLAND_DISPLAY and DISPLAY, so no window reaches the desktop or takes
its focus, and a client that did not take the driver fails instead of opening
one. The graphical suites hold nothing and overlap like the rest. Before any
suite starts, the run opens one offscreen client (tests/live.py gpu_probe, on
the synthetic legacy demo the "probe" step cooks into the work tree); no EGL
device or a software rasteriser fails the run (a failed "gpu-probe" prepare
step, LIVE_KO_FAIL) and every suite with a graphical branch is not run. The
renderer and display mode go to summary.json. N3E_LIVE_DISPLAY=desktop (`make
live-ko LIVE_DISPLAY=desktop`) is the opt-in for watching: real windows on
WAYLAND_DISPLAY or DISPLAY (which must be set), one graphical suite at a time
(they hold "display"), taking the desktop's focus. The last line counts passed, failed and not run separately.
This script exits 0 only when every selected suite ran and passed, 1 when a
suite or prepare step failed or a Postgres start was refused (UNDISPOSABLE),
and 2 when none failed but some did not run. Under
`make live-ko` make turns any non-zero recipe status into its own exit 2, so
there only 0 (LIVE_KO_OK) is meaningful: read failed against not run from the
last line (LIVE_KO_FAIL / LIVE_KO_INCOMPLETE) or summary.json's "verdict".

`make live` never runs these suites. Of tests/live.py's read audit the
disposable-start check runs here too (UNDISPOSABLE lines fail the run,
summary.json "undisposable").
"""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import live  # noqa: E402

# PQ-129 (D-193): where the graphical clients draw is tests/live.py's rule, read
# from N3E_LIVE_DISPLAY (make live-ko LIVE_DISPLAY=desktop): offscreen on the GPU by
# default, no window; desktop windows, one graphical suite at a time ("display"),
# only on that opt-in. live.DISPLAY is read when the suites below are defined.

PY = sys.executable
OUT = ROOT / "build/live-ko"
# Every KO cook output of this run, apart from the persistent launchers' build/ tree.
WORK = "build/live-ko/work"
CLIENT = "assets/ko"
# The operator's own START_POSITION export (tools/assetc/ko_start.py EXPORT; never committed).
START_POSITIONS = "build/ko-completion/database-parity/START_POSITION.json"
# PQ-422 (D-219): the operator's own MAGIC_TYPE2 export (tools/assetc/ko_tables.py EXPORT;
# never committed): the glow bow's archery damage terms.
MAGIC_TYPE2 = "build/ko-completion/database-parity/MAGIC_TYPE2.json"
# The player's 1097 install, unpacked by tools/ko-reference/unpack_installer.py (PQ-221).
INSTALL_1097 = "build/ko-reference/installer-1097"
# The player's 2145 install, unpacked by tools/ko-reference/unpack_inno.py (PQ-227).
INSTALL_2145 = "build/ko-reference/installer-2145"
# PQ-129: the GPU probe's package, the synthetic legacy demo cooked into this run's
# work tree (make live-ko does not build `make assets`' build/packages/legacy-demo).
PROBE_PACKAGE = f"{WORK}/packages/legacy-demo"
live.GPU_PROBE = [live.GPU_PROBE[0], PROBE_PACKAGE, *live.GPU_PROBE[2:]]

# name -> (command, player-supplied inputs it needs (empty: none), what it produces)
PREPARE = {
    "image": (["docker", "compose", "build", "server"], [], []),
    "ca": (["bash", "deploy/local-ca.sh"], [], ["deploy/local/ca.pem"]),
    # PQ-129: the offscreen GPU probe's package (original fixture, no KO data).
    "probe": ([PY, "tools/assetc/main.py", "tests/fixtures/legacy-demo", PROBE_PACKAGE], [],
              [f"{PROBE_PACKAGE}/release.sha256"]),
    # Zone key 210 (Moradon): its Zones.tbl row names the map files (PQ-216).
    "moradon": ([PY, "tools/assetc/ko_bake.py", "210", "--features", f"--into={WORK}"],
                [f"{CLIENT}/Data/Zones.tbl.csv", f"{CLIENT}/Zones/moradon_xmas.gtd", f"{CLIENT}/Zones/moradon_xmas.opd"],
                [f"{WORK}/packages/moradon/release.sha256", f"{WORK}/ko-moradon/provenance.json"]),
    "ko-field": ([PY, "tools/assetc/test_field.py", f"--into={WORK}"], [f"{CLIENT}/Chr/mob_worm.n3chr"],
                 [f"{WORK}/packages/ko-field/release.sha256", f"{WORK}/ko-source/field/package.json"]),
    # PQ-218: the homeland maps (Zones.tbl keys 10 and 20, PQ-217) as tools/play-ko-zone
    # cooks them; their start comes from the operator's own START_POSITION export.
    **{name: ([PY, "tools/assetc/ko_bake.py", str(key), f"--into={WORK}"],
              [f"{CLIENT}/Data/Zones.tbl.csv", f"{CLIENT}/Zones/{map_name}.gtd", f"{CLIENT}/Zones/{map_name}.opd",
               START_POSITIONS],
              [f"{WORK}/packages/ko-zone-{key}/release.sha256", f"{WORK}/ko-zone-{key}/provenance.json"])
       for name, key, map_name in (("karus", 10, "karus2004"), ("elmorad", 20, "elmo2004"))},
    # PQ-274: the 1097 homelands (its Zones.tbl keys 1 and 2), from the player's
    # unpacked 1097 install, as tools/play-ko-zone karus-1097 / elmorad-1097 cooks them.
    **{name: ([PY, "tools/assetc/ko_bake.py", str(key), "--client=1097", f"--into={WORK}"],
              [f"{INSTALL_1097}/manifest.json", f"{INSTALL_1097}/client/Zones/{map_name}.gtd",
               f"{INSTALL_1097}/client/Zones/{map_name}.opd", f"{CLIENT}/Data/Zones.tbl.csv", START_POSITIONS],
              [f"{WORK}/packages/ko-1097-zone-{key}/release.sha256", f"{WORK}/ko-1097-zone-{key}/provenance.json"])
       for name, key, map_name in (("karus-1097", 1, "karus_start"), ("elmorad-1097", 2, "elmorad_start"))},
    # PQ-223: the classic Moradon (the install's own unnamed Zones/moradon.*), as
    # tools/play-moradon --layout classic cooks it.
    "moradon-classic": ([PY, "tools/assetc/ko_bake.py", "210", "--layout=classic", "--features", f"--into={WORK}"],
                        [f"{CLIENT}/Data/Zones.tbl.csv", f"{CLIENT}/Zones/moradon.gtd", f"{CLIENT}/Zones/moradon.opd"],
                        [f"{WORK}/packages/moradon-classic/release.sha256",
                         f"{WORK}/ko-moradon-classic/provenance.json"]),
    # PQ-224: the 1097 Moradon (the 1097 install's key 21), as
    # tools/play-moradon --layout 1097 cooks it.
    "moradon-1097": ([PY, "tools/assetc/ko_bake.py", "21", "--client=1097", "--features", f"--into={WORK}"],
                     [f"{INSTALL_1097}/manifest.json", f"{INSTALL_1097}/client/Zones/moradon.gtd",
                      f"{INSTALL_1097}/client/Zones/moradon.opd", f"{CLIENT}/Data/Zones.tbl.csv"],
                     [f"{WORK}/packages/moradon-1097/release.sha256", f"{WORK}/ko-moradon-1097/provenance.json"]),
    # PQ-315: Moradon with the 2233 client's equipment glow from the player's 2145
    # tables, as tools/play-moradon --glow-2233 cooks it.
    "moradon-glow2233": ([PY, "tools/assetc/ko_bake.py", "210", "--features", "--glow-2233", f"--into={WORK}"],
                         [f"{CLIENT}/Data/Zones.tbl.csv", f"{CLIENT}/Zones/moradon_xmas.gtd",
                          f"{CLIENT}/Zones/moradon_xmas.opd", f"{INSTALL_2145}/manifest.json",
                          f"{INSTALL_2145}/client/Data/Item_Org_us.tbl", MAGIC_TYPE2],
                         [f"{WORK}/packages/moradon-glow2233/release.sha256",
                          f"{WORK}/ko-moradon-glow2233/provenance.json"]),
}

GRAPHICAL = live.GRAPHICAL
# turbo_live's graphical branch (one client against the Moradon wire) runs under
# its own switch; the fixed drawable makes it print a PASS line.
TURBO_ENV = {"N3E_TURBO_GRAPHICS": "1", "N3E_TEST_WINDOW_SIZE": "1280x1024"} if GRAPHICAL else {}


def stacked(name, kind, script, graphical=None):
    return live.suite(name, "python", "tests/ko_stack.py", kind, script,
                      covers=[script, "tests/moradon_stack.py"] if kind.startswith("moradon") else [script],
                      graphical=graphical)


# (suite, prepare steps it needs, True when it always starts graphical clients)
KO_SUITES = [
    (live.suite("turbo_live", "python", "tests/turbo_live.py", env=TURBO_ENV,
                graphical="PASS Moradon fixed drawable"), ["moradon"], False),
    (live.suite("camera_legacy_live", "python", "tests/camera_legacy_live.py",
                graphical="PASS legacy package right drag/release"), ["ko-field"], True),
    (stacked("field_live", "field", "tests/field_live.py"), ["ko-field"], False),
    (live.suite("ko_presentation_live", "python", "tests/ko_presentation_live.py",
                graphical="PASS actual player idle/attack/death/respawn"), ["ko-field"], True),
    (stacked("moradon_combat_potions_live", "moradon", "tests/moradon_combat_potions_live.py"), ["moradon"], False),
    (stacked("moradon_features_live", "moradon", "tests/moradon_features_live.py"), ["moradon"], False),
    (stacked("moradon_melee_sequence_live", "moradon", "tests/moradon_melee_sequence_live.py"), ["moradon"], False),
    (stacked("moradon_panels_live", "moradon", "tests/moradon_panels_live.py",
             graphical="PASS minimap hidden at start"), ["moradon"], True),
    (stacked("moradon_skills_live", "moradon", "tests/moradon_skills_live.py",
             graphical="PASS Moradon skill too far graphical"), ["moradon"], False),
    (stacked("moradon_uif_live", "moradon", "tests/moradon_uif_live.py",
             graphical="PASS native actions:"), ["moradon"], True),
    (stacked("moradon_weapon_effects_live", "moradon", "tests/moradon_weapon_effects_live.py",
             graphical="PASS Moradon weapon effect graphical"), ["moradon"], False),
    (stacked("moradon_worm_live", "moradon", "tests/moradon_worm_live.py"), ["moradon"], False),
    (stacked("moradon_glow_live", "moradon-glow2233", "tests/moradon_glow_live.py",
             graphical="PASS Moradon equipment glow graphical"), ["moradon-glow2233"], False),
    (stacked("moradon_skeletal_plug_live", "moradon-glow2233", "tests/moradon_skeletal_plug_live.py",
             graphical="PASS Moradon skeletal plug graphical"), ["moradon-glow2233"], False),
    (stacked("moradon_armour_live", "moradon-glow2233", "tests/moradon_armour_live.py",
             graphical="PASS Moradon Krowaz Assassin glow graphical"), ["moradon-glow2233"], False),
    (stacked("moradon_classic_live", "moradon-classic", "tests/moradon_layout_live.py"), ["moradon-classic"], False),
    (stacked("moradon_1097_live", "moradon-1097", "tests/moradon_layout_live.py"), ["moradon-1097"], False),
    (stacked("homeland_karus_live", "ko-zone-10", "tests/homeland_live.py"), ["karus"], False),
    (stacked("homeland_elmorad_live", "ko-zone-20", "tests/homeland_live.py"), ["elmorad"], False),
    (stacked("homeland_karus_1097_live", "ko-1097-zone-1", "tests/homeland_live.py"), ["karus-1097"], False),
    (stacked("homeland_elmorad_1097_live", "ko-1097-zone-2", "tests/homeland_live.py"), ["elmorad-1097"], False),
    # PQ-387 (D-204): the cooked maps' light maps drawn offscreen, without and
    # with them, from one camera over each start; no stack.
    (live.suite("ko_terrain_overlay_live", "python", "tests/ko_terrain_overlay_live.py",
                graphical="PASS KO terrain light maps graphical"),
     ["moradon", "moradon-classic", "moradon-1097", "karus", "elmorad", "karus-1097"], True),
    # PQ-392 (D-205): the Karus warp gate drawn offscreen over its light-map
    # shadow, against a cook of key 10 with the event shapes left out; no stack.
    (live.suite("ko_event_shapes_live", "python", "tests/ko_event_shapes_live.py",
                graphical="PASS KO bind points and warp gates graphical"), ["karus"], True),
    # PQ-395 (D-206): Moradon's magic anvil drawn offscreen in its object NPC's
    # state, against a cook of key 210 with it left out; no stack.
    (live.suite("ko_object_npc_shapes_live", "python", "tests/ko_object_npc_shapes_live.py",
                graphical="PASS KO magic anvil graphical"), ["moradon"], True),
    # PQ-412 (D-213): the 1097 Moradon's dungeon gate, a static shape whose fire
    # part cycles without billboarding, drawn offscreen against a cook of key 21
    # with that class left out; no stack.
    (live.suite("ko_material_shapes_live", "python", "tests/ko_material_shapes_live.py",
                graphical="PASS KO animated-material shapes graphical"), ["moradon-1097"], True),
]
SUITES = [s for s, _, _ in KO_SUITES]
SCRIPTS = sorted({"tests/live_ko.py", "tests/ko_stack.py", "tests/moradon_stack.py",
                  *(f for s in SUITES for f in s["covers"])})


def shape():
    """Problems with the harness shape: the suites must be exactly tests/live.py
    OPT_IN, and every script this run starts must compile."""
    problems = []
    owned = {f for s in SUITES for f in s["covers"] if f.endswith("_live.py")}
    for path in sorted(set(live.OPT_IN) - owned):
        problems.append(f"{path} is opt-in in tests/live.py but tests/live_ko.py does not run it")
    for path in sorted(owned - set(live.OPT_IN)):
        problems.append(f"{path} is run by tests/live_ko.py but is not opt-in in tests/live.py")
    for path in sorted(owned & {f for s in live.SUITES for f in s["covers"]}):
        problems.append(f"{path} is run by both make live and make live-ko")
    for name, (command, _, _) in PREPARE.items():
        problems += [f"prepare {name}: {a} is missing" for a in command if a.endswith((".py", ".sh")) and not (ROOT / a).is_file()]
    for path in SCRIPTS:
        try:
            compile((ROOT / path).read_text(), path, "exec")
        except (SyntaxError, ValueError, OSError) as error:
            problems.append(f"{path} does not compile: {error}")
    return problems


def missing_inputs(paths):
    return [p for p in paths if not (ROOT / p).exists()]


def prepare(names, run_it, kept_dir):
    """Run the prepare steps `names` need. Returns {step: None (ready) or
    ("not run", reason) or ("failed", reason)} and the results of steps that ran;
    a failed step's log is kept under `kept_dir` (tests/live.py keep_failed)."""
    state, results = {}, []
    for name, (command, inputs, outputs) in PREPARE.items():
        if name not in names:
            continue
        absent = missing_inputs(inputs)
        if absent:
            state[name] = ("not run", f"player-supplied KO data missing: {', '.join(absent)} (see README, Local KO live suites)")
            print(f"SKIP        prepare {name}: {state[name][1]}", flush=True)
            continue
        if not run_it:
            absent = missing_inputs(outputs)
            state[name] = ("not run", f"--no-prepare and {', '.join(absent)} not built") if absent else None
            continue
        t = time.time()
        code = live.run(command, OUT / f"prepare-{name}.log",
                        env={"N3E_UID": str(os.getuid()), "N3E_GID": str(os.getgid())})
        ok = code == 0 and not missing_inputs(outputs)
        kept = None if ok else live.keep_failed(f"prepare-{name}", kept_dir)
        state[name] = None if ok else ("failed", f"prepare {name} failed (logs kept in {kept})")
        results.append({"name": f"prepare-{name}", "exit": code if code or ok else "outputs missing",
                        "seconds": round(time.time() - t), "kept": kept, "ended": round(time.time(), 3)})
        shown = " ".join(command[1:] if command[0] == PY else command)
        print(f"{'PASS' if ok else 'FAIL'} {round(time.time() - t):>5}s  prepare {name}: {shown}"
              f"{f'  logs kept in {kept}' if kept else ''}", flush=True)
        if not ok and name in ("image", "ca"):
            break
    for name in names:
        state.setdefault(name, ("failed", "an earlier prepare step failed"))
    return state, results


def release_hashes():
    """The cooked releases' SHA-256 (no content): what this run tested."""
    out = {}
    for package in ["moradon", "moradon-classic", "moradon-1097", "moradon-glow2233", "ko-field", "ko-presentation-combat", "ko-zone-10", "ko-zone-20"]:
        path = ROOT / WORK / "packages" / package / "release.sha256"
        if path.is_file():
            out[package] = path.read_text().strip()
    return out


def sweep(run_id):
    """Remove any stack of this run that a suite left behind (an interrupted run)."""
    listed = subprocess.run(["docker", "compose", "ls", "-a", "--format", "json"], capture_output=True, text=True)
    try:
        projects = [p["Name"] for p in json.loads(listed.stdout or "[]")]
    except ValueError:
        return []
    left = [p for p in projects if p.startswith(f"n3e-kolive-{run_id}-")]
    for project in left:
        subprocess.run(["docker", "compose", "-p", project, "down", "-v", "--remove-orphans"],
                       capture_output=True, text=True, timeout=180)
    return left


def outcome(failed, reads, not_run):
    """(verdict, exit status, refused starts) of a run. PQ-208 (D-156): a Postgres
    start the audit hook refused (a `*.undisposable` record under `reads`) fails
    the run like a failed suite, even when the suite caught the error."""
    refused = live.undisposable(reads)
    if failed or refused:
        return "FAIL", 1, refused
    return ("INCOMPLETE", 2, refused) if not_run else ("OK", 0, refused)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    options = [a for a in argv[1:] if a.startswith("--")]
    jobs = live.JOBS
    for option in options:
        if option.startswith("--jobs=") and option[7:].isdigit() and int(option[7:]) >= 1:
            jobs = int(option[7:])
        elif option not in ("--list", "--no-prepare", "--check"):
            raise SystemExit(f"live_ko.py: unknown option {option}; see the module docstring")
    if "--check" in options:
        problems = shape()
        for p in problems:
            print(f"FAIL {p}")
        print(f"LIVE_KO_SHAPE_{'FAIL' if problems else 'OK'} {len(SUITES)} suites, {len(SCRIPTS)} scripts")
        return 1 if problems else 0
    if "--list" in options:
        for s, needs, windows in KO_SUITES:
            print(f"{s['name']:28} needs {', '.join(needs)}{'  [always starts clients]' if windows else ''}"
                  f"{'  [graphical]' if s['graphical'] else ''}")
        return 0
    unknown = set(args) - {s["name"] for s in SUITES}
    if unknown:
        raise SystemExit(f"live_ko.py: unknown suite(s) {sorted(unknown)}; see --list")
    if live.PORT_BASE + jobs * live.PORT_SPAN > live.ephemeral_low():
        raise SystemExit(f"live_ko.py: --jobs={jobs} port ranges would reach the ephemeral range")
    # PQ-129: offscreen (the default) needs a GPU, which the probe below checks;
    # only the desktop opt-in needs a display.
    if live.DISPLAY not in live.DISPLAYS:
        raise SystemExit(f"LIVE_KO_FAIL live_ko.py: N3E_LIVE_DISPLAY={live.DISPLAY!r}; "
                         f"use one of {', '.join(live.DISPLAYS)}")
    if GRAPHICAL and live.DISPLAY == "desktop" and not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        raise SystemExit("LIVE_KO_FAIL live_ko.py: N3E_LIVE_DISPLAY=desktop needs a display (WAYLAND_DISPLAY or DISPLAY); "
                         "the default, offscreen, needs only a GPU")
    problems = shape()
    for p in problems:
        print(f"FAIL harness: {p}", flush=True)
    if problems:
        return 1
    # The shared runner writes its logs, slot port state and prepare cache under OUT.
    live.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in ["prepared", "reads", "stacks"]:
        shutil.rmtree(OUT / stale, ignore_errors=True)
    (OUT / "reads").mkdir()
    for log in OUT.glob("*.log"):
        log.unlink()
    run_id = uuid.uuid4().hex[:8]
    os.environ.update(N3E_KO_RUN=run_id, N3E_KO_STACKS=str(OUT / "stacks"), N3E_KO_WORK=WORK)
    started = time.time()
    kept_dir = live.new_kept_dir()
    watch = live.host_network.Watch().start()
    chosen = [(s, needs, windows) for s, needs, windows in KO_SUITES if not args or s["name"] in args]
    probe = GRAPHICAL and live.DISPLAY == "offscreen"
    steps = ["image", "ca", *(["probe"] if probe else []), *sorted({n for _, needs, _ in chosen for n in needs})]
    state, results = prepare(steps, "--no-prepare" not in options, kept_dir)
    # PQ-129: as tests/live.py, one offscreen client before any suite; no GPU (no
    # EGL device, a software rasteriser) fails the run here, never as a pass.
    renderer = None
    if probe and not state["probe"] and not state["image"] and not state["ca"]:
        t = time.time()
        renderer, problem = live.gpu_probe()
        print(f"{'FAIL' if problem else 'PASS'} {round(time.time() - t):>5}s  GPU probe: offscreen renderer "
              f"{renderer or 'none'}{f' ({problem})' if problem else ''}", flush=True)
        if problem:
            kept = live.keep_failed("gpu-probe", kept_dir)
            results.append({"name": "prepare-gpu-probe", "exit": "no hardware GPU", "seconds": round(time.time() - t),
                            "kept": kept, "ended": round(time.time(), 3)})
            state["probe"] = ("failed", f"graphical branches need a hardware GPU; the offscreen probe failed: {problem}")
    not_run, runnable = {}, []
    for s, needs, windows in chosen:
        # A failed probe stops every suite with a graphical branch.
        gpu = ["probe"] if probe and (windows or s["graphical"]) else []
        blocked = next((state[n] for n in ["image", "ca", *gpu, *needs] if state[n]), None)
        if blocked:
            not_run[s["name"]] = blocked[1]
        elif windows and not GRAPHICAL:
            not_run[s["name"]] = "always starts graphical clients; needs N3E_GRAPHICAL=1 (LIVE_GRAPHICAL=1)"
        else:
            runnable.append(s)
    for s, _, _ in chosen:
        if s["name"] in not_run:
            print(f"NOT RUN     {s['name']}: {not_run[s['name']]}", flush=True)
    if runnable:
        print(f"running {len(runnable)} KO suites, at most {jobs} at once, graphical branches "
              f"{f'on ({live.DISPLAY})' if GRAPHICAL else 'OFF (headless)'}", flush=True)
        try:
            results += live.run_suites(runnable, jobs, kept_dir=kept_dir)
        finally:
            left = sweep(run_id)
            if left:
                print(f"swept {len(left)} leftover stacks: {' '.join(left)}", flush=True)
    suites = [r for r in results if not r["name"].startswith("prepare-")]
    passed = [r["name"] for r in suites if r["exit"] == 0]
    failed = [r["name"] for r in results if r["exit"] != 0]
    verdict, code, refused = outcome(failed, OUT / "reads", not_run)
    for line in refused:
        print(f"UNDISPOSABLE {line} (start it with tests/isolation.py DISPOSABLE_POSTGRES or DISPOSABLE_COMPOSE)",
              flush=True)
    host, flag = live.host_record(watch, results, kept_dir)
    kept = kept_dir.relative_to(ROOT).as_posix() + "/" if kept_dir.is_dir() else None
    live.prune_failed()
    summary = {"verdict": verdict, "results": results, "passed": passed, "failed": failed, "kept": kept,
               "not_run": not_run, "undisposable": refused,
               "releases": release_hashes(), "jobs": jobs, "graphical": GRAPHICAL,
               "display": live.DISPLAY if GRAPHICAL else None, "renderer": renderer,
               "seconds": round(time.time() - started), "host": host}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    failed_suites = [n for n in failed if not n.startswith("prepare-")]
    print(f"LIVE_KO_{verdict} {len(passed)} passed, {len(failed_suites)} failed, {len(not_run)} not run "
          f"of {len(chosen)} KO suites; {len(failed) - len(failed_suites)} prepare steps failed; "
          f"{len(refused)} undisposable starts; "
          f"{summary['seconds']} s, jobs {jobs}, graphical {f'on ({live.DISPLAY})' if GRAPHICAL else 'OFF'}; "
          f"logs in build/live-ko/"
          f"{f'; failed logs kept in {kept}' if kept else ''}{flag if verdict == 'FAIL' else ''}",
          flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
