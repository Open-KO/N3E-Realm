#!/usr/bin/env python3
"""A disposable local KO stack around one opt-in suite (PQ-111).

  python tests/ko_stack.py moradon tests/moradon_worm_live.py [ARGS...]
  python tests/ko_stack.py field tests/field_live.py
  python tests/ko_stack.py ko-zone-10 tests/homeland_live.py
  python tests/ko_stack.py ko-1097-zone-1 tests/homeland_live.py
  python tests/ko_stack.py moradon-classic tests/moradon_layout_live.py
  python tests/ko_stack.py moradon-1097 tests/moradon_layout_live.py
  python tests/ko_stack.py moradon-glow2233 tests/moradon_glow_live.py

The moradon_*_live suites, field_live and homeland_live were written against the
persistent stacks tools/play-moradon, tools/play-ko-field and tools/play-ko-zone
start (fixed Compose projects, ports 7780, 7799, 7801, 7778 and 7793-7798, the user's
own accounts beside them). Under `make live-ko`
each instead gets a stack of its own: a Compose project and realm named for this
run and suite, a Docker-published port, fresh volumes, the n3e-foundation image
the run built, the package the run cooked from the player's KO data, and a
Postgres cluster that skips fsync (tests/isolation.py DISPOSABLE_COMPOSE). The
suite learns where it is through tests/moradon_stack.py (N3E_MORADON_STATE,
N3E_MORADON_PROJECT, N3E_IMAGE) or N3E_FIELD_PROJECT/N3E_FIELD_PORT. The stack
and its volumes are removed when the suite ends, fails or is interrupted.

Exit status: the suite's, or 3 when the stack could not be started (a failure,
never a pass).
"""
import json
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

from isolation import DISPOSABLE_COMPOSE, container_logs

ROOT = Path(__file__).resolve().parents[1]
KINDS = {
    # package below N3E_KO_WORK, whether the realm needs the progression policy
    # (tools/moradon_session.py), the Zones.tbl key the state names
    "moradon": ("packages/moradon", True, 210),
    # PQ-223: the classic Moradon (ko_bake.py 210 --layout=classic --features).
    "moradon-classic": ("packages/moradon-classic", True, 210),
    # PQ-224: the 1097 Moradon (ko_bake.py 21 --client=1097 --features), its 1097 key.
    "moradon-1097": ("packages/moradon-1097", True, 21),
    # PQ-315: Moradon with the 2233 equipment glow (ko_bake.py 210 --features --glow-2233).
    "moradon-glow2233": ("packages/moradon-glow2233", True, 210),
    "field": ("packages/ko-field", False, 210),
    # PQ-218: the homeland maps (tools/ko_zone_session.py); the copied demo rules
    # carry a reward policy, converted as the play stack converts it.
    "ko-zone-10": ("packages/ko-zone-10", True, 10),
    "ko-zone-20": ("packages/ko-zone-20", True, 20),
    # PQ-274: the 1097 homelands (ko_bake.py KEY --client=1097), keyed by zone id.
    "ko-1097-zone-1": ("packages/ko-1097-zone-1", True, 1),
    "ko-1097-zone-2": ("packages/ko-1097-zone-2", True, 2),
}
IMAGE = "n3e-foundation:local"


def main(argv):
    if len(argv) < 3 or argv[1] not in KINDS:
        raise SystemExit(__doc__)
    kind, command = argv[1], [sys.executable if a == "python" else a for a in argv[2:]]
    if command[0].endswith(".py"):
        command.insert(0, sys.executable)
    package, progression, zone = KINDS[kind]
    # make live-ko cooks into build/live-ko/work (N3E_KO_WORK); the default is the
    # build/ tree the persistent launchers cook into.
    package = (ROOT / os.environ.get("N3E_KO_WORK", "build") / package).resolve()
    release = (package / "release.sha256").read_text().strip()
    run_id = os.environ.get("N3E_KO_RUN", uuid.uuid4().hex[:8])
    suite = Path(next(a for a in command if a.endswith(".py"))).stem.replace("_", "-")[:24]
    project = f"n3e-kolive-{run_id}-{suite}-{uuid.uuid4().hex[:6]}"
    realm = f"test-kolive-{uuid.uuid4().hex[:12]}"
    out = Path(os.environ.get("N3E_KO_STACKS", ROOT / "build/live-ko/stacks"))
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "N3E_UID": str(os.getuid()), "N3E_GID": str(os.getgid()), "N3E_IMAGE": IMAGE,
           "N3E_PACKAGE_PATH": str(package), "N3E_REALM": realm, "N3E_PORT": "0"}
    # PQ-208 (D-155, D-156): the stack's cluster skips fsync like every make live one.
    compose = ["docker", "compose", *DISPOSABLE_COMPOSE, "-p", project]

    def dc(*args):
        p = subprocess.run([*compose, *args], cwd=ROOT, env=env, text=True, capture_output=True, timeout=300)
        print(f"ko_stack: docker compose {' '.join(args)}: exit {p.returncode}", flush=True)
        if p.returncode:
            raise RuntimeError(f"docker compose {' '.join(args)} exit {p.returncode}:\n{p.stdout[-1500:]}{p.stderr[-1500:]}")
        return p.stdout

    # SIGTERM (the runner's timeout path sends SIGINT) also reaches the teardown.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    code, stack_error = 3, None
    try:
        try:
            dc("up", "-d", "--wait", "postgres", "redis")
            dc("run", "--rm", "--no-deps", "migrate")
            if progression:
                dc("run", "--rm", "--no-deps", "-e", "N3E_TEST_PROGRESSION=disposable", "server", "convert-progression")
            dc("up", "-d", "--wait", "server")
            port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
        except (RuntimeError, ValueError, IndexError, subprocess.TimeoutExpired) as error:
            stack_error = error
        if stack_error is None:
            state = out / f"{project}.json"
            state.write_text(json.dumps({"port": port, "realm": realm, "release": release, "zone": zone,
                                         "project": project, "package": Path(KINDS[kind][0]).name},
                                        indent=1) + "\n")
            print(f"ko_stack: {kind} stack {project} realm {realm} on 127.0.0.1:{port}", flush=True)
            suite_env = {**env, "N3E_PORT": str(port), "N3E_MORADON_STATE": str(state),
                         "N3E_MORADON_PROJECT": project, "N3E_FIELD_PROJECT": project, "N3E_FIELD_PORT": str(port)}
            code = subprocess.run(command, cwd=ROOT, env=suite_env).returncode
        else:
            print(f"ko_stack: FAIL the {kind} stack did not start: {stack_error}", flush=True)
        if code:
            logs = subprocess.run([*compose, "logs", "--no-color", "--tail", "60"], cwd=ROOT, env=env,
                                  text=True, capture_output=True)
            print("ko_stack: stack log tail\n" + logs.stdout[-8000:], flush=True)
    finally:
        # PQ-128: every service's whole log, before the stack is removed; the runner
        # keeps it with the suite's log when the suite fails.
        container_logs("compose", [*compose, "logs", "--no-color", "--timestamps"], env=env)
        down = subprocess.run([*compose, "down", "-v", "--remove-orphans"], cwd=ROOT, env=env,
                              text=True, capture_output=True, timeout=180)
        print(f"ko_stack: docker compose down -v: exit {down.returncode}", flush=True)
    return code if down.returncode == 0 or code else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
