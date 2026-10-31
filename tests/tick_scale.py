"""PQ-115: the test-only tick scale fails closed on the real server binary.

N3E_TEST_TICK_MS shortens the wall-clock tick only for a disposable realm
(N3E_TEST_REALM=disposable and a test-... realm, server/src/clock.rs). Here the
binary must refuse every other combination before it touches a dependency, for the
server start and for subcommands alike, announce an accepted scale loudly, and no
production configuration (compose.yaml, deploy/) may carry either variable.
No Docker, database or display: the accepted case stops at the database connect.
"""
import os
import re
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "target/debug/n3e-server"
PACKAGE = ROOT / "build/packages/demo"
KNOBS = ("N3E_TEST_TICK_MS", "N3E_TEST_REALM")


def closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server(*args, **extra):
    env = {k: v for k, v in os.environ.items() if k not in KNOBS and k != "N3E_REALM"}
    env.update(N3E_PACKAGE=str(PACKAGE), DATABASE_URL=f"host=127.0.0.1 port={closed_port()} user=n3e dbname=n3e connect_timeout=1",
               REDIS_ADDRESS=f"127.0.0.1:{closed_port()}", N3E_HEALTH=f"127.0.0.1:{closed_port()}",
               N3E_LISTEN=f"127.0.0.1:{closed_port()}")
    env.update(extra)
    return subprocess.run([str(SERVER), *args], env=env, capture_output=True, text=True, timeout=60)


GUARDS = "N3E_TEST_REALM=disposable"
cases = [
    # (variables, why it must be refused)
    ({"N3E_TEST_TICK_MS": "25"}, "no guard, default realm"),
    ({"N3E_TEST_TICK_MS": "25", "N3E_REALM": "test-a"}, "test- realm without N3E_TEST_REALM"),
    ({"N3E_TEST_TICK_MS": "25", "N3E_TEST_REALM": "disposable"}, "N3E_TEST_REALM on the default realm"),
    ({"N3E_TEST_TICK_MS": "25", "N3E_TEST_REALM": "disposable", "N3E_REALM": "n3e-ko06-x"}, "non-test realm"),
    ({"N3E_TEST_TICK_MS": "25", "N3E_TEST_REALM": "yes", "N3E_REALM": "test-a"}, "marker not 'disposable'"),
]
for variables, why in cases:
    for args in [(), ("health",), ("migrate",)]:
        r = server(*args, **variables)
        assert r.returncode != 0 and GUARDS in r.stderr, (why, args, r.returncode, r.stderr)
        assert "WARNING: TEST-ONLY TICK SCALE" not in r.stderr, (why, args, r.stderr)
for value in ["9", "51", "x", "25.5"]:
    r = server(N3E_TEST_TICK_MS=value, N3E_TEST_REALM="disposable", N3E_REALM="test-a")
    assert r.returncode != 0 and "not an integer from 10 to 50" in r.stderr, (value, r.stderr)

# Accepted: the guard passes, the warning names the tick, and the start then stops
# at the (closed) database port, so nothing else was reached.
r = server(N3E_TEST_TICK_MS="25", N3E_TEST_REALM="disposable", N3E_REALM="test-a")
assert r.returncode != 0 and "N3E_TEST_TICK_MS refused" not in r.stderr and "kind: Connect" in r.stderr, r.stderr
assert "WARNING: TEST-ONLY TICK SCALE ACTIVE: one simulation tick every 25 ms" in r.stderr, r.stderr
# Unset or empty is production: no warning, same database failure.
for extra in [{}, {"N3E_TEST_TICK_MS": ""}]:
    r = server(**extra, N3E_REALM="test-a", N3E_TEST_REALM="disposable")
    assert r.returncode != 0 and "kind: Connect" in r.stderr and "TICK" not in r.stderr, r.stderr

# No production configuration can carry the knobs.
tracked = subprocess.run(["git", "ls-files", "-z", "compose.yaml", "deploy"], cwd=ROOT, capture_output=True, text=True, check=True)
production = [ROOT / p for p in tracked.stdout.split("\0") if p]
assert ROOT / "compose.yaml" in production and len(production) > 1, production
for path in production:
    text = path.read_text(errors="replace")
    for knob in KNOBS:
        assert knob not in text, (path, knob)
# compose.yaml passes an explicit environment list; nothing from the caller's
# environment reaches the server container unless a test override adds it.
assert not re.search(r"^\s*env_file:", (ROOT / "compose.yaml").read_text(), re.M)
print(f"PASS test tick refused without a disposable realm ({len(cases)} cases x 3 commands, 4 bad values), "
      f"accepted case announced, absent from compose.yaml and {len(production) - 1} deploy files")
