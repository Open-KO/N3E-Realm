"""The loop gate's step planner (tools/loop/gate.py, docs/loop/LOOP.md "Gate") on
synthetic change lists: which checks a change gets per item, what runs daily, the
environment the steps get, SKIP lines and flake attribution. Runs nothing slow:
the only step it runs is a one-line Python command."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/loop"))
import gate  # noqa: E402


def steps(*files):
    return {name: (cmd, env) for name, cmd, env in gate.plan(list(files))}


def live(*files, target="make-live"):
    """The suites the per-item step runs: None (no step), "all", or a set."""
    found = steps(*files).get(target)
    if found is None:
        return None
    var = "LIVE_SUITES" if target == "make-live" else "LIVE_KO_SUITES"
    return set(found[1][var].split()) if var in found[1] else "all"


def ko(*files):
    return live(*files, target="make-live-ko")


# Docs only: the queue check alone. content/ and tools/loop/ are not docs (review
# 2026-11-01 section 6.7).
assert list(steps("docs/loop/LOOP.md", "specs/QUESTIONS.md", "content/front-end.md")) == ["queue"]
assert list(steps()) == ["queue"]
for path in ["content/package.schema.json", "tools/loop/gate.py", "tools/loop/queue.py"]:
    assert list(steps(path)) == ["queue", "make-test-fast"], (path, list(steps(path)))
print("PASS docs-only changes get the queue check; content/ and tools/loop/ get make test-fast")

# Crates: n3e-server also for what it compiles in or tests against (6.3); every
# crate for the workspace files and the toolchain.
for path in ["server/src/main.rs", "protocol/wire.proto", "protocol/golden-claim-payload.hex",
             "deploy/026-anything.sql", "tests/fixtures/npc-reference.hex", "bot/src/admin.rs"]:
    assert "cargo-test-server" in steps(path), path
assert "cargo-test-bot" in steps("bot/src/admin.rs")
assert "cargo-test-server" not in steps("deploy/local-ca.sh")
launcher = steps("launcher/src/main.rs")
assert "cargo-test-server" not in launcher and {"cargo-test-launcher", "clippy-launcher", "fmt-launcher"} <= set(launcher)
for path in ["rust-toolchain.toml", "Cargo.lock", "Cargo.toml"]:
    assert {f"cargo-test-{d}" for d in gate.CRATES} <= set(steps(path)), path
print("PASS cargo steps: touched crates, n3e-server's protocol, SQL, fixtures and bot contract, the toolchain")

# Engine changes get make test-fast but no live suite per item: the full make
# live and make live-ko are the daily gate's.
for path in ["server/src/main.rs", "client/render/viewer.cpp", "games/demo/package.json", "tools/assetc/main.py",
             "Makefile", "compose.yaml"]:
    assert "make-test-fast" in steps(path) and live(path) is None and ko(path) is None, (path, list(steps(path)))
print("PASS engine, content and build changes: make test-fast, no live suite per item")

# Live suites and shared harnesses select their suites (6.1), wherever the name.
assert live("tests/friends_db.py") == {"friends_db"}
assert live("tests/multiplayer.py") == {"multiplayer"}
assert live("tests/peer.cpp") == {"multiplayer"}
assert live("tests/gameplay.py") == {"gameplay"}
assert live("tests/administration.py") == {"administration"}
assert {"session_lifecycle", "chat_channels"} <= live("tests/session_lifecycle.py") | live("tests/chat_channels.py")
assert {"discord_login_live", "edge_live"} <= live("tests/discord_standin.py")
sessions = live("tools/demo_session.py")
assert {"session_check", "inventory_live", "friends_live_full", "item_drops_live"} <= sessions, sessions
assert len(live("tests/world_peer.py")) > 1 and len(live("tests/readiness.py")) > 1
assert live("tests/friends_live.py") >= {"friends_live", "friends_live_full"}
# A runner's own files run it whole; a new live suite no runner owns runs make live whole.
for path in ["tests/live.py", "tests/isolation.py", "tests/disposable.py", "tests/compose-disposable.yaml",
             "tests/live_reads/sitecustomize.py", "tests/host_network.py"]:
    assert live(path) == "all" and ko(path) == "all", path
assert live("tests/zz_new_suite_live.py") == "all" and live("tests/zz_new_db.py") == "all"
assert live("tests/live_ko.py") is None and ko("tests/live_ko.py") == "all"
print("PASS live suites, shared harnesses and runners select make live suites by their covers")

# KO suites, the front-end harness and the Moradon feature cook select make live-ko suites (6.2).
assert ko("tests/front_end_live.py") == {"front_end_live"}
assert ko("client/harness/front_end_flow.inc") == {"front_end_flow_live"}
assert ko("client/render/front_end.h", "games/moradon/front-end.json") == {"front_end_live", "front_end_flow_live"}
assert ko("tools/assetc/ko_front_end.py") == {"front_end_live", "front_end_flow_live"}
assert {"moradon_worm_live", "moradon_features_live", "front_end_live"} <= ko("tools/assetc/moradon_features.py")
assert "homeland_karus_live" not in ko("tools/assetc/moradon_features.py")
assert ko("tools/assetc/moradon_des.py") == ko("tools/assetc/moradon_features.py")
assert {"moradon_worm_live", "field_live", "homeland_karus_live"} <= ko("tests/ko_stack.py")
assert ko("tests/moradon_stack.py") and "field_live" not in ko("tests/moradon_stack.py")
assert ko("tests/moradon_route.py")
assert {"homeland_karus_live", "homeland_elmorad_1097_live"} <= ko("tests/homeland_live.py")
assert live("tests/front_end_live.py") is None
# The RQ-076 change: no full make live-ko, no make live, no bake pins re-cut per item...
rq076 = ["client/harness/front_end_flow.inc", "client/render/front_end.h", "content/front-end.md",
         "games/moradon/front-end.json", "specs/11-front-end.md", "tests/front_end_flow_live.py",
         "tools/assetc/SUPPORT.md", "tools/assetc/ko_front_end.py"]
assert ko(*rq076) == {"front_end_live", "front_end_flow_live"} and live(*rq076) is None
assert "make-test-slow" not in steps(*rq076)
# ...unless the change edits the pins themselves.
slow = steps(*rq076, "tests/ko_bake_pin.py")["make-test-slow"]
assert slow == (["make", "test-slow", "SLOW_TESTS=tests/ko_bake_pin.py"], {}), slow
print("PASS KO suites, front-end harness and Moradon feature cook select make live-ko suites; slow tests by script")

# Every covers entry names a file, so a typo cannot silently select nothing.
for target, suites in [("live", gate.live_suites()["live"]), ("live-ko", gate.live_suites()["live-ko"])]:
    for name, covers in suites:
        for path in covers:
            assert (ROOT / path).is_file(), f"{target} suite {name}: covers {path} is not a file"
for path in gate.slow_tests():
    assert (ROOT / path).is_file(), f"SLOW_TESTS names {path}, which is not a file"
assert gate.slow_tests(), "the Makefile names no SLOW_TESTS"
print("PASS every covers entry and SLOW_TESTS script is a file")

# Flake attribution uses covers (6.6): friends_live_full has no script of its own.
covers = dict(gate.live_suites()["live"])
assert gate.touches(["tests/friends_live.py"], covers["friends_live_full"])
assert gate.touches(["tools/demo_session.py"], covers["friends_live_full"])
assert not gate.touches(["tests/friends_live_full.py", "server/src/main.rs"], covers["friends_live_full"])
assert gate.touches(["tests/discord_standin.py"], covers["edge_live"])
print("PASS a failed suite is the change's when the change touches its covers, not tests/<name>.py")

# The daily gate: every crate, all of make test, all of make live and make live-ko.
daily = {name: (cmd, env) for name, cmd, env in gate.daily_plan()}
assert {f"cargo-test-{d}" for d in gate.CRATES} <= set(daily)
assert daily["make-test"][0] == ["make", "test"]
assert daily["make-live"] == (["make", "live"], {"LIVE_GRAPHICAL": "1"})
assert daily["make-live-ko"] == (["make", "live-ko"], {"LIVE_GRAPHICAL": "1"})
# A daily failure is blamed on the day's commits that touch it, else on all of them.
day = [("aaa", "RQ-1: friends", ["tests/friends_live.py"]), ("bbb", "RQ-2: server", ["server/src/main.rs"]),
       ("ccc", "RQ-3: pins", ["tests/ko_bake_pin.py"])]
assert gate.blame("make-live: friends_live_full failed again alone: LIVE_FAIL", day) == day[:1]
assert gate.blame("make-test: python tests/ko_bake_pin.py: make: *** Error 1", day) == day[2:]
assert gate.blame("make-live-ko: front_end_live failed again alone", day) == day
assert gate.blame("cargo-test-server: test result: FAILED", day) == day
print("PASS the daily gate runs every crate, make test, make live and make live-ko whole, and blames by covers")

# The environment (6.4, item point 8): tools/env.sh sourced, a shell's leftovers removed.
saved = {k: os.environ.get(k) for k in gate.CLEARED}
os.environ.update({k: "stray" for k in gate.CLEARED})
try:
    env = gate.run_env({"LIVE_GRAPHICAL": "1"})
finally:
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
assert not {"LIVE_SUITES", "LIVE_KO_SUITES", "LIVE_TICK_MS", "LIVE_DISPLAY"} & env.keys(), sorted(env)
assert env["LIVE_GRAPHICAL"] == "1"
assert env.get("IMGUI", "").endswith("imgui") and env.get("CARGO_HOME"), "tools/env.sh was not sourced"
print("PASS steps get tools/env.sh and none of LIVE_SUITES, LIVE_KO_SUITES, LIVE_TICK_MS, LIVE_DISPLAY")

# SKIP lines (6.5): a missing fixture fails make test unless only the maintainer holds it.
assert gate.unallowed_skips("PASS x\nSKIP 1264 key 210 row comparison: the 1264 install is not unpacked at y\n"
                            "SKIP installer pins: no ref/ko-bin/installer/KnightOnlineSetup_v2145.exe\n") == []
assert gate.unallowed_skips("SKIP Moradon release pins: local KO client data absent\n") == [
    "SKIP Moradon release pins: local KO client data absent"]
log_dir = ROOT / "build/loop/gate-test"
shutil.rmtree(log_dir, ignore_errors=True)
log_dir.mkdir(parents=True)
failure, _ = gate.check_step("make-test-fast", [sys.executable, "-c", "print('python tests/x.py'); "
                             "print('SKIP x: assets/ko absent')"], {}, log_dir, [], [])
assert failure and "SKIP x: assets/ko absent" in failure, failure
failure, _ = gate.check_step("make-test-fast", [sys.executable, "-c", "print('PASS')"], {}, log_dir, [], [])
assert failure is None, failure
failure, _ = gate.check_step("make-test-fast", [sys.executable, "-c",
                             "print('python tests/y.py'); raise SystemExit(2)"], {}, log_dir, [], [])
assert failure and "python tests/y.py" in failure, failure
assert (log_dir / "timings.tsv").read_text().count("make-test-fast\t") == 3
shutil.rmtree(log_dir)
print("PASS an unallowed SKIP fails a make test step; the failing command and each step's time are kept")

# The CLI plans a given change list.
out = subprocess.run([sys.executable, "tools/loop/gate.py", "plan", "tests/front_end_live.py"], cwd=ROOT,
                     capture_output=True, text=True, check=True).stdout
assert "make-live-ko: LIVE_GRAPHICAL=1 LIVE_KO_SUITES=front_end_live make live-ko" in out, out
print("PASS gate.py plan FILE... prints the per-item steps for that change")
