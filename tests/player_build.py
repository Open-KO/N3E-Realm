"""PQ-006: the player clients carry no test harness.

One source builds two clients per build directory (CMakeLists.txt): n3e-client,
the player build, compiled with N3E_HARNESS=0, and n3e-test-client, which adds
the replay, smoke, capture and automatic-login modes the suites drive. This
reads both binaries of build/client and build/client-tools: no harness marker
may appear in a player binary, and every marker must appear in the matching test
binary, so a marker that stopped naming harness code fails here instead of
passing vacuously. It also runs each player binary with a test argument, which it
must refuse.

  python tests/player_build.py                  make test: build/client, and
                                                build/client-tools if this tree built it
  python tests/player_build.py --require-tools  make live (tests/live.py PREPARE,
                                                after both builds): both, always
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Strings only the harness compiles in: its switches and arguments, replay
# output, capture paths, and the game data and credentials the replays once
# hard-coded (now supplied by their suites through N3E_TEST_ITEMS and
# N3E_TEST_STORAGE_*).
MARKERS = [
    b"N3E_TEST_",                 # every replay switch, N3E_TEST_ACCOUNT/PASSWORD
    b"N3E_EDIT_TEST",             # tools-client editor replay
    b"N3E_REQUIRE_HARDWARE_GL",   # live-suite GPU refusal
    b"--smoke",
    b"-smoke",                    # --world-smoke, --melee-smoke, ...
    b"--auto-login",
    b"--capture",
    b"--npc-observe",
    b"--unsupported",
    b"automatic login requires test credentials",
    b"offscreen swaps paced",     # PQ-121 offscreen pacing
    b"PASS ",                     # replay verdicts
    b"replay",                    # replay failure messages
    b".ppm",                      # capture files
    b"N3E_TEST_ITEMS",
    b"N3E_TEST_STORAGE_PASSWORD",
]
# Never in either binary: the replays take these from the suite now.
FORBIDDEN_EVERYWHERE = [b"demo:item/", b"Moradon1", b"Original_123", b"Replacement_123"]


def main():
    builds = [ROOT / "build/client"]
    tools = ROOT / "build/client-tools"
    if "--require-tools" in sys.argv[1:] or (tools / "n3e-test-client").exists():
        builds.append(tools)
    else:
        # make test builds only build/client; a tools build from an older tree
        # has no n3e-test-client and is not this tree's. make live checks it.
        print("NOTE build/client-tools not built by this tree; make live checks it")
    failures = []
    for build in builds:
        player, test = build / "n3e-client", build / "n3e-test-client"
        for binary in (player, test):
            if not binary.is_file():
                failures.append(f"{binary.relative_to(ROOT)} missing")
        if failures:
            continue
        player_bytes, test_bytes = player.read_bytes(), test.read_bytes()
        for marker in MARKERS:
            if marker in player_bytes:
                failures.append(f"{player.relative_to(ROOT)} contains harness marker {marker!r}")
            if marker not in test_bytes:
                failures.append(f"{test.relative_to(ROOT)} lacks {marker!r}: the marker no longer names harness code")
        for value in FORBIDDEN_EVERYWHERE:
            for binary, data in ((player, player_bytes), (test, test_bytes)):
                if value in data:
                    failures.append(f"{binary.relative_to(ROOT)} hard-codes {value!r}")
        # The player build refuses a test argument before opening any window.
        refused = subprocess.run([str(player), "build/packages/legacy-demo", "--smoke"], cwd=ROOT,
                                 capture_output=True, text=True, timeout=60)
        if refused.returncode == 0 or "argument --smoke" not in refused.stderr:
            failures.append(f"{player.relative_to(ROOT)} accepted --smoke: exit {refused.returncode} "
                            f"{refused.stderr.strip()[-200:]!r}")
    for failure in failures:
        print("FAIL", failure)
    if failures:
        sys.exit(1)
    print(f"PASS player clients carry no test harness ({', '.join(b.relative_to(ROOT).as_posix() for b in builds)}): "
          f"{len(MARKERS)} markers absent from n3e-client and present in n3e-test-client, "
          "no hard-coded item IDs or warehouse passwords, --smoke refused")


if __name__ == "__main__":
    main()
