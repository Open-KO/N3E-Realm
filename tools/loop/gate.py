"""The realm loop's gates (docs/loop/LOOP.md "Gate"): the per-item gate, picked from
the files the change touches, and the daily gate run on master before the push.
Logs and per-step timings go to build/loop/gate/<stamp>/ (daily: build/loop/daily/).

  python3 tools/loop/gate.py plan     print the per-item steps for the current change
  python3 tools/loop/gate.py run      run them; the last line is GATE_OK, GATE_FLAKE
                                      <suites> (passed after isolated reruns) or
                                      GATE_FAIL <step>: <why>
  python3 tools/loop/gate.py daily    every step on a clean master; the last line is
                                      DAILY_OK, DAILY_FLAKE <suites> or DAILY_FAIL
                                      <steps>, after one DAILY_BLAME line per failure

The change is the working tree against HEAD, untracked files included. Per item:
the queue check; cargo fmt, clippy and test for each crate whose inputs the change
touches; `make test-fast` for anything not docs-only; each slow test (Makefile
SLOW_TESTS) whose script the change touches; and the `make live` and `make
live-ko` suites whose covers it touches (a suite's covers in tests/live.py and
tests/live_ko.py, with the tests/ and tools/ scripts they import or name; a
change to a runner's own scripts runs that runner whole). The daily gate runs all
of it: every crate, the whole of `make test`, the whole of `make live` and
`make live-ko`, and attributes each failure to the commits since origin/master
that touch it.

A failed live suite whose covers the change does not touch is rerun once alone;
passing alone makes it a flake (the loop files an item), not a failure. A SKIP line
in a make test log fails the step unless SKIP_ALLOWED names it. The gate sources
tools/env.sh and removes CLEARED from the environment it passes on.
"""
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
DOCS = ("docs/", "specs/", ".claude/", "README.md", "AGENTS.md")
RUST_ALL = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")
# dir -> (package, what else it builds in or tests against: path prefixes ending
# "/" or fnmatch patterns). n3e-server compiles wire.proto (build.rs), the SQL
# migrations, the protocol golden payloads and the NPC fixtures, and tests its
# admin routes against realm-bot's (server/src/admin_api.rs).
CRATES = {
    "server": ("n3e-server", ("protocol/", "deploy/*.sql", "tests/fixtures/*.hex", "bot/Cargo.toml",
                              "bot/src/lib.rs", "bot/src/admin.rs")),
    "launcher": ("realm-launcher", ()),
    "bot": ("realm-bot", ()),
    "edge": ("realm-edge", ()),
}
# A shell's leftovers that would make a step run less, or other content, than the
# gate asks for: LIVE_SUITES/LIVE_KO_SUITES a subset, LIVE_TICK_MS a test tick,
# LIVE_DISPLAY windows, LIVE_JOBS another parallelism, GAME/TOOLS other packages
# and builds. The gate sets what it needs itself.
CLEARED = ("LIVE_SUITES", "LIVE_KO_SUITES", "LIVE_TICK_MS", "LIVE_DISPLAY", "LIVE_JOBS", "LIVE_GRAPHICAL",
           "SLOW_TESTS", "GAME", "TOOLS")
# SKIP lines for inputs only the maintainer holds (LOOP.md: any other missing
# fixture fails the gate). Each entry is a regex searched in the SKIP line.
SKIP_ALLOWED = (
    r"the 1264 install is not unpacked",               # tests/ko_bake_pin.py: no 1264 installer here
    r"no ref/ko-bin/installer/KnightOnlineSetup_v2145\.exe",  # ko_installer_unpack, ko_inno_unpack
)
# The scripts a covers closure follows: test scripts and helpers, top-level tools
# and the cook's synthetic fixtures (the cooker library itself is make test's).
TRACED = re.compile(r"(tests/[\w-]+\.py|tools/[\w-]+\.py|tools/assetc/\w*fixture\w*\.py)")
LIVE_RUNNERS = {"live": "tests/live.py", "live-ko": "tests/live_ko.py"}


def changed():
    out = subprocess.run(["git", "status", "--porcelain=v1", "-uall"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return sorted({line[3:].split(" -> ")[-1] for line in out.splitlines() if line.strip()})


def is_doc(path):
    return path.startswith(DOCS) or path.endswith(".md")


def matches(path, patterns):
    return any(path.startswith(p) if p.endswith("/") else fnmatch.fnmatchcase(path, p) for p in patterns)


def rq021_done():
    for line in (ROOT / "docs/loop/queue.jsonl").read_text().splitlines():
        if '"RQ-021"' in line:
            return json.loads(line)["status"] == "done"
    return False


def slow_tests():
    """The scripts the Makefile's SLOW_TESTS names (make test-slow)."""
    text = (ROOT / "Makefile").read_text()
    found = re.search(r"^SLOW_TESTS\s*:?=((?:.*\\\n)*.*)$", text, re.M)
    return found.group(1).replace("\\\n", " ").split() if found else []


def search_path(path, text):
    """Where `path` finds a module, approximately as Python would: the directories
    it puts first with sys.path.insert(0, ...) (the last one first), its own, then
    those it appends."""
    def dirs(call):
        out = []
        for found in re.finditer(r"sys\.path\.%s\((.*)\)" % call, text):
            arg = found.group(1).replace('" / "', "/").replace("' / '", "/")
            named = [d for d in ("tools/assetc", "tools/loop", "tests") if d in arg]
            out += named or (["tools"] if re.search(r"[\"']tools[\"']", arg) else [])
        return out
    own = str(Path(path).parent)
    order = [*reversed(dirs("insert")), own, *dirs("append")]
    return list(dict.fromkeys(order))


def references(path, scripts=True):
    """The repository files `path` imports (by module name, from tests/, tools/ or
    a cook fixture) or names as a string literal (scripts=False: only its non-Python
    files under tests/, so a runner does not reach every suite it lists)."""
    try:
        text = (ROOT / path).read_text(errors="replace")
    except OSError:
        return set()
    names = set()
    for found in re.finditer(r"^[ \t]*(?:from[ \t]+(\w+)[ \t]+import|import[ \t]+([\w \t,]+))", text, re.M):
        names.update([found.group(1)] if found.group(1) else
                     (part.split()[0] for part in found.group(2).split(",") if part.strip()))
    out, where = set(), search_path(path, text)
    for name in names:
        found = next((f"{base}/{name}.py" for base in where if (ROOT / base / f"{name}.py").is_file()), None)
        if found and TRACED.fullmatch(found):
            out.add(found)
    for literal in re.findall(r"""["']((?:tests|tools)/[\w./-]+)["']""", text):
        data = literal.startswith("tests/") and not literal.endswith((".py", ".cpp"))
        if ((scripts and TRACED.fullmatch(literal)) or data) and (ROOT / literal).is_file():
            out.add(literal)
    return out


def closure(paths, scripts=True, cache={}):
    """`paths` and every traced script they reach through references()."""
    key = (tuple(sorted(paths)), scripts)
    if key not in cache:
        out, todo = set(), list(paths)
        while todo:
            path = todo.pop()
            if path in out:
                continue
            out.add(path)
            if TRACED.fullmatch(path):
                todo.extend(references(path, scripts) - out)
        cache[key] = out
    return cache[key]


def touches(files, covers):
    """Whether any of `files` is one of `covers`' closure (a covers entry ending in
    "/" covers everything below it)."""
    reached = closure([c for c in covers if not c.endswith("/")])
    prefixes = tuple(c for c in covers if c.endswith("/"))
    return any(f in reached or (prefixes and f.startswith(prefixes)) for f in files)


def live_suites(cache={}):
    """{"live": [(name, covers)], "live-ko": [...]} from the runners themselves."""
    if not cache:
        sys.path.insert(0, str(ROOT / "tests"))
        try:
            import live
            import live_ko
        finally:
            sys.path.remove(str(ROOT / "tests"))
        cache["live"] = [(s["name"], s["covers"]) for s in live.SUITES]
        cache["live-ko"] = [(s["name"], s["covers"]) for s in live_ko.SUITES]
        cache["owned"] = {f for s in live.SUITES + live_ko.SUITES for f in s["covers"]} | set(live.OPT_IN)
    return cache


def runner_files(target):
    """What every suite of a runner depends on: the runner, the modules it imports
    and the files they name under tests/ (live_reads/ is matched as a prefix); for
    live-ko also tests/live.py's, whose runner it reuses."""
    files = set(closure([LIVE_RUNNERS[target]], scripts=False))
    if target == "live-ko":
        files |= runner_files("live")
    return files


def live_selection(files, target):
    """None (nothing to run), "all", or the suites of `target` to run alone."""
    suites = live_suites()
    runner = runner_files(target)
    unowned = [f for f in files if re.fullmatch(r"tests/\w+_(live|db)\.py", f) and f not in suites["owned"]]
    if any(f in runner or f.startswith("tests/live_reads/") for f in files) or (target == "live" and unowned):
        return "all"
    chosen = [name for name, covers in suites[target] if touches(files, covers)]
    return chosen or None


def run_env(extra=None):
    """The environment every step gets: the caller's, tools/env.sh sourced, CLEARED
    removed, then `extra`."""
    sourced = subprocess.run(["bash", "-c", "source tools/env.sh && env -0"], cwd=ROOT, capture_output=True,
                             check=True).stdout.decode(errors="replace")
    env = dict(kv.split("=", 1) for kv in sourced.split("\0") if "=" in kv)
    for name in CLEARED:
        env.pop(name, None)
    env.update(extra or {})
    return env


def crate_steps(dirs):
    steps = []
    for crate_dir in dirs:
        crate = CRATES[crate_dir][0]
        if crate_dir != "server" or rq021_done():
            steps.append((f"fmt-{crate_dir}", ["cargo", "fmt", "-p", crate, "--check"], {}))
            steps.append((f"clippy-{crate_dir}",
                          ["cargo", "clippy", "-p", crate, "--all-targets", "--", "-D", "warnings"], {}))
        steps.append((f"cargo-test-{crate_dir}", ["cargo", "test", "-p", crate], {}))
    return steps


def live_step(target, selection):
    name, var = ("make-live", "LIVE_SUITES") if target == "live" else ("make-live-ko", "LIVE_KO_SUITES")
    env = {"LIVE_GRAPHICAL": "1"}
    if selection != "all":
        env[var] = " ".join(selection)
    return (name, ["make", target], env)


def plan(files):
    """The per-item steps for a change to `files`: (name, command, extra env)."""
    steps = [("queue", ["python3", "tools/loop/queue.py", "check"], {})]
    if not files or all(is_doc(f) for f in files):
        return steps
    steps += crate_steps([d for d, (_, inputs) in CRATES.items()
                          if any(f.startswith(d + "/") or f in RUST_ALL or matches(f, inputs) for f in files)])
    steps.append(("make-test-fast", ["make", "test-fast"], {}))
    slow = [t for t in slow_tests() if touches(files, [t])]
    if slow:
        # A command-line variable: the Makefile's own SLOW_TESTS assignment wins over the environment.
        steps.append(("make-test-slow", ["make", "test-slow", f"SLOW_TESTS={' '.join(slow)}"], {}))
    for target in LIVE_RUNNERS:
        selection = live_selection(files, target)
        if selection:
            steps.append(live_step(target, selection))
    return steps


def daily_plan():
    steps = [("queue", ["python3", "tools/loop/queue.py", "check"], {})]
    steps += crate_steps(list(CRATES))
    steps.append(("make-test", ["make", "test"], {}))
    steps += [live_step(target, "all") for target in LIVE_RUNNERS]
    return steps


def run_step(name, cmd, env, log_dir, timings):
    log = log_dir / f"{name}.log"
    started = time.time()
    with log.open("w") as out:
        code = subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                              env=run_env(env)).returncode
    seconds = int(time.time() - started)
    timings.append((name, code, seconds))
    with (log_dir / "timings.tsv").open("a") as out:
        out.write(f"{name}\t{code}\t{seconds}\n")
    tail = log.read_text(errors="replace").strip().splitlines()[-1:] or [""]
    print(f"{name}: exit {code} in {seconds}s, {log.relative_to(ROOT)}", flush=True)
    return code, tail[0]


def unallowed_skips(text):
    return [line.strip() for line in text.splitlines() if line.startswith("SKIP")
            and not any(re.search(allowed, line) for allowed in SKIP_ALLOWED)]


def live_failures(target, since):
    """The suites the runner's summary.json names as failed, when this run wrote it
    (None otherwise); for live-ko also the suites it did not run."""
    summary = ROOT / ("build/live/summary.json" if target == "live" else "build/live-ko/summary.json")
    # Two seconds of slack: Linux stamps mtimes from a coarse clock (docs/history/GAPS.md,
    # PQ-143), and a run's summary is written minutes after it starts.
    if not summary.exists() or summary.stat().st_mtime < since - 2:
        return None
    data = json.loads(summary.read_text())
    return data.get("failed", []), sorted(data.get("not_run", {}))


def times_line(timings):
    return "; ".join(f"{name} {code} {seconds}s" for name, code, seconds in timings)


def check_step(name, cmd, env, log_dir, timings, files):
    """Run one step. Returns (failure or None, flaky suites). A failed live suite
    whose covers `files` do not touch (files=None: always) is rerun alone once."""
    started = time.time()
    code, last = run_step(name, cmd, env, log_dir, timings)
    log = (log_dir / f"{name}.log").read_text(errors="replace")
    if name.startswith("make-test"):
        if code != 0:
            ran = [line for line in log.splitlines() if re.match(r"(python3? |build/client/)", line)]
            return f"{name}: {ran[-1] if ran else '?'}: {last}", []
        skips = unallowed_skips(log)
        return (f"{name}: SKIP for a fixture this checkout should have: {skips[0]}" if skips else None), []
    target = cmd[1] if name.startswith("make-live") else None
    ok = code == 0 and (target != "live-ko" or last.startswith("LIVE_KO_OK"))
    if ok or target is None:
        return (None if ok else f"{name}: {last}"), []
    found = live_failures(target, started)
    if not found or found[1]:
        return f"{name}: {last}" + (f" (not run: {', '.join(found[1])})" if found and found[1] else ""), []
    failed = found[0]
    covers = dict(live_suites()[target])
    if not failed or any(s not in covers for s in failed):
        return f"{name}: {last}", []
    if files is not None:
        touched = [s for s in failed if touches(files, covers[s])]
        if touched:
            return f"{name}: {', '.join(failed)} (the change touches {', '.join(touched)})", []
    var = "LIVE_SUITES" if target == "live" else "LIVE_KO_SUITES"
    flakes = []
    for suite in failed:
        code, last = run_step(f"rerun-{suite}", cmd, {**env, var: suite}, log_dir, timings)
        if code != 0 or (target == "live-ko" and not last.startswith("LIVE_KO_OK")):
            return f"{name}: {suite} failed again alone: {last}", flakes
        flakes.append(suite)
    return None, flakes


def new_log_dir(kind):
    log_dir = ROOT / "build/loop" / kind / time.strftime("%Y%m%d-%H%M%S")
    log_dir.mkdir(parents=True)
    return log_dir


def gate(files):
    log_dir = new_log_dir("gate")
    (log_dir / "files.txt").write_text("".join(f + "\n" for f in files))
    timings, flakes = [], []
    for name, cmd, env in plan(files):
        failure, flaky = check_step(name, cmd, env, log_dir, timings, files)
        flakes += flaky
        if failure:
            print(f"GATE_TIMES {times_line(timings)}")
            print(f"GATE_FAIL {failure}")
            return 1
    print(f"GATE_TIMES {times_line(timings)}")
    print(f"GATE_FLAKE {' '.join(flakes)}" if flakes else "GATE_OK")
    return 0


def day_commits():
    """(sha, subject, files) for each commit on master since origin/master."""
    base = "origin/master" if subprocess.run(["git", "rev-parse", "-q", "--verify", "origin/master"], cwd=ROOT,
                                             capture_output=True).returncode == 0 else "HEAD~1"
    shas = subprocess.run(["git", "rev-list", "--reverse", f"{base}..HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.split()
    out = []
    for sha in shas:
        shown = subprocess.run(["git", "show", "--name-only", "--format=%s", sha], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.splitlines()
        out.append((sha[:10], shown[0], [f for f in shown[1:] if f.strip()]))
    return out


def blame(failure, commits):
    """The day's commits a daily failure points at: those touching the failed
    suites' covers or the failed test's script, else all of them."""
    suites = dict(live_suites()["live"] + live_suites()["live-ko"])
    named = [s for s in re.findall(r"[\w-]+", failure) if s in suites]
    scripts = re.findall(r"tests/[\w-]+\.py", failure)
    hit = [c for c in commits if any(touches(c[2], suites[s]) for s in named)
           or (scripts and touches(c[2], scripts))]
    return hit or commits


def daily():
    dirty = [f for f in changed() if f != "docs/loop/INBOX.md"]
    if dirty:
        print(f"DAILY_FAIL the tree is not clean ({len(dirty)} files): the daily gate runs on committed master")
        return 1
    log_dir = new_log_dir("daily")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (log_dir / "head.txt").write_text(head + "\n")
    timings, flakes, failures = [], [], []
    for name, cmd, env in daily_plan():
        failure, flaky = check_step(name, cmd, env, log_dir, timings, None)
        flakes += flaky
        if failure:
            failures.append(failure)
    commits = day_commits()
    for failure in failures:
        hit = blame(failure, commits)
        print(f"DAILY_BLAME {failure} <- " + ("; ".join(f"{sha} {subject}" for sha, subject, _ in hit)
                                              if hit else "no commit since origin/master"))
    verdict = ("FAIL " + "; ".join(f.split(":")[0] for f in failures) if failures
               else f"FLAKE {' '.join(flakes)}" if flakes else "OK")
    (ROOT / "build/loop/daily-last.json").write_text(json.dumps(
        {"head": head, "verdict": verdict, "at": int(time.time()), "log": log_dir.relative_to(ROOT).as_posix(),
         "flakes": flakes, "failures": failures}, indent=1) + "\n")
    print(f"DAILY_TIMES {times_line(timings)}")
    print(f"DAILY_{verdict}")
    return 1 if failures else 0


def main(argv):
    verb = argv[0] if argv else ""
    if verb == "plan":
        files = argv[1:] or changed()
        steps = plan(files)
        print(f"{len(files)} changed files")
        for name, cmd, env in steps:
            print(f"{name}:", *(f"{k}={v!r}" if " " in v else f"{k}={v}" for k, v in env.items()), *cmd)
        return 0
    if verb == "run":
        return gate(changed())
    if verb == "daily":
        return daily()
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
