"""The realm loop's merge gate (docs/loop/LOOP.md "Gate"): the checks the working
tree's change needs, picked from the files it touches, run in order, logged to
build/loop/gate/<stamp>/.

  python3 tools/loop/gate.py plan     print the steps for the current change
  python3 tools/loop/gate.py run      run them; the last line is GATE_OK, GATE_FLAKE
                                      <suites> (passed after isolated reruns) or
                                      GATE_FAIL <step>

The change is the working tree against HEAD, untracked files included. A live
suite that fails, and whose own script the change does not touch, is rerun once
alone; passing alone makes it a flake (the loop files an item), not a failure.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CRATES = {"server": "n3e-server", "launcher": "realm-launcher", "bot": "realm-bot", "edge": "realm-edge"}
DOCS = ("docs/", "specs/", "content/", "README.md", "AGENTS.md", ".claude/", "tools/loop/")
LIVE = ("server/", "client/", "protocol/", "deploy/", "compose.yaml", "Cargo.toml", "Cargo.lock",
        "CMakeLists.txt", "Makefile", "edge/", "launcher/", "bot/", "tools/assetc/", "games/",
        "tests/live.py", "tests/peer.cpp", "tests/schema.py")
LIVE_KO = ("games/moradon/", "tools/assetc/ko", "client/render/front_end", "client/render/viewer.cpp",
           "tests/live_ko.py")


def changed():
    out = subprocess.run(["git", "status", "--porcelain=v1", "-uall"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return sorted({line[3:].split(" -> ")[-1] for line in out.splitlines() if line.strip()})


def rq021_done():
    for line in (ROOT / "docs/loop/queue.jsonl").read_text().splitlines():
        if '"RQ-021"' in line:
            return json.loads(line)["status"] == "done"
    return False


def plan(files):
    steps = [("queue", ["python3", "tools/loop/queue.py", "check"], {})]
    if not files or all(f.startswith(DOCS) or f.endswith(".md") for f in files):
        return steps
    for crate_dir, crate in CRATES.items():
        if any(f.startswith(crate_dir + "/") for f in files) or any(f.startswith("Cargo.") for f in files):
            if crate_dir != "server" or rq021_done():
                steps.append((f"fmt-{crate_dir}", ["cargo", "fmt", "-p", crate, "--check"], {}))
                steps.append((f"clippy-{crate_dir}",
                              ["cargo", "clippy", "-p", crate, "--all-targets", "--", "-D", "warnings"], {}))
            steps.append((f"cargo-test-{crate_dir}", ["cargo", "test", "-p", crate], {}))
    steps.append(("make-test", ["make", "test"], {}))
    if any(f.startswith(LIVE) or (f.startswith("tests/") and f.endswith("_live.py")) for f in files):
        steps.append(("make-live", ["make", "live"], {"LIVE_GRAPHICAL": "1"}))
    if any(f.startswith(LIVE_KO) for f in files):
        steps.append(("make-live-ko", ["make", "live-ko"], {"LIVE_GRAPHICAL": "1"}))
    return steps


def run_step(name, cmd, env, log_dir):
    log = log_dir / f"{name}.log"
    started = time.time()
    with log.open("w") as out:
        code = subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                              env={**os.environ, **env}).returncode
    tail = log.read_text(errors="replace").strip().splitlines()[-1:] or [""]
    print(f"{name}: exit {code} in {int(time.time() - started)}s, {log.relative_to(ROOT)}", flush=True)
    return code, tail[0]


def live_failures(since):
    """The suites build/live/summary.json names as failed, when this run wrote it."""
    summary = ROOT / "build/live/summary.json"
    if not summary.exists() or summary.stat().st_mtime < since:
        return None
    return json.loads(summary.read_text()).get("failed", [])


def suite_script(name):
    script = ROOT / "tests" / f"{name}.py"
    return script.relative_to(ROOT).as_posix() if script.exists() else None


def main(argv):
    verb = argv[0] if argv else ""
    files = changed()
    steps = plan(files)
    if verb == "plan":
        print(f"{len(files)} changed files")
        for name, cmd, env in steps:
            print(f"{name}:", *(f"{k}={v}" for k, v in env.items()), *cmd)
        return 0
    if verb != "run":
        raise SystemExit(__doc__)
    log_dir = ROOT / "build/loop/gate" / time.strftime("%Y%m%d-%H%M%S")
    log_dir.mkdir(parents=True)
    (log_dir / "files.txt").write_text("".join(f + "\n" for f in files))
    flakes = []
    for name, cmd, env in steps:
        started = time.time()
        code, last = run_step(name, cmd, env, log_dir)
        if name == "make-live-ko":
            ok = last.startswith("LIVE_KO_OK")
            if not ok:
                print(f"GATE_FAIL {name}: {last}")
                return 1
            continue
        if code == 0:
            continue
        failed = live_failures(started) if name == "make-live" else None
        if not failed:
            print(f"GATE_FAIL {name}: {last}")
            return 1
        touched = [s for s in failed if suite_script(s) in files]
        if touched:
            print(f"GATE_FAIL {name}: {', '.join(failed)} (the change touches {', '.join(touched)})")
            return 1
        for suite in failed:
            code, last = run_step(f"rerun-{suite}", ["make", "live"], {**env, "LIVE_SUITES": suite}, log_dir)
            if code != 0:
                print(f"GATE_FAIL {name}: {suite} failed again alone: {last}")
                return 1
            flakes.append(suite)
    print(f"GATE_FLAKE {' '.join(flakes)}" if flakes else "GATE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
