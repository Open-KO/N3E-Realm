"""PQ-006: no script starts the player client with a test-harness argument.

The player n3e-client refuses the test client's arguments and ignores its
N3E_TEST_* switches (tests/player_build.py), so a launcher that hands them to it
breaks. This reads every tracked script that can start a client (tools/,
tests/, deploy/, spikes/, the Makefile): one that names the player binary must
use no harness argument or switch anywhere, unless it is listed below with the
reason it names the player binary without starting it that way.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The player binary as a path (build/client/n3e-client, "n3e-client" joined to a
# build directory), not n3e-test-client and not the word in prose.
PLAYER = re.compile(r"""[/'"]n3e-client(?![\w-])""")
# The test client's own arguments (client/render/viewer.cpp under N3E_HARNESS).
ARGUMENTS = ["--auto-login", "--smoke", "--capture", "--npc-observe", "--unsupported", "--time"]


def switches():
    """Every environment switch the client reads, from its sources: all of them
    exist only in the test build (N3E_PROFILE, the one the player keeps, aside)."""
    names = set()
    for source in (ROOT / "client").rglob("*"):
        if source.suffix in (".cpp", ".h", ".inc"):
            names.update(re.findall(r"\b(N3E_(?:TEST|EDIT)_[A-Z_]+|N3E_REQUIRE_HARDWARE_GL)\b", source.read_text()))
    return names


# Scripts that name the player binary only to inspect it, never to start it with
# a harness argument.
ALLOWED = {
    "tests/client_launchers.py": "this check",
    "tests/player_build.py": "reads both binaries; runs the player with --smoke to see it refused",
    "tests/editing.py": "nm of the player binary (no editor symbols)",
    "tests/graphical.py": "nm of the player binary; its runs use n3e-test-client",
    "tests/demo.py": "hashes the binaries across game packages",
    "tests/launcher_live.py": "its releases name their client n3e-client as the Launcher requires: a stub, "
                              "or a wrapper that runs n3e-test-client",
}
ROOTS = ("tools/", "tests/", "deploy/", "spikes/", "Makefile")


def main():
    listed = subprocess.run(["git", "ls-files", "-z", *ROOTS], cwd=ROOT, capture_output=True, text=True, check=True)
    harness = re.compile("|".join([*(re.escape(a) + r"(?![\w-])" for a in ARGUMENTS), r"--\w+-smoke(?![\w-])",
                                   *(rf"\b{n}\b" for n in sorted(switches(), key=len, reverse=True))]))
    failures, launchers = [], 0
    for path in sorted(p for p in listed.stdout.split("\0") if p):
        if path.endswith((".md", ".json", ".png", ".bin", ".ppm", ".hex", ".cpp", ".h")):
            continue
        try:
            text = (ROOT / path).read_text()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        if not PLAYER.search(text):
            if path in ALLOWED:
                failures.append(f"{path} is allowed to name n3e-client but no longer does: drop it from ALLOWED")
            continue
        launchers += 1
        used = sorted(set(harness.findall(text)))
        if used and path not in ALLOWED:
            failures.append(f"{path} names build/.../n3e-client and uses harness-only {', '.join(used)}: "
                            "start n3e-test-client instead")
    for failure in failures:
        print("FAIL", failure)
    if failures:
        sys.exit(1)
    print(f"PASS no launcher gives the player client a harness argument ({launchers} scripts name n3e-client, "
          f"{len(ALLOWED)} only to inspect it)")


if __name__ == "__main__":
    main()
