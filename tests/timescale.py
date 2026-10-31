"""Test-only simulation tick for disposable live realms (PQ-115).

tests/live.py sets N3E_LIVE_TICK_MS for the suites it marks `scaled`; a suite run
by hand, or one live.py leaves unscaled, sees 50 (production timing) and every
helper here is then the identity. A scaled suite gives its server
server_env(realm), whose realm must be named test-..., and the server refuses to
start otherwise (server/src/clock.rs). Rules still count ticks; only the wall time
of a tick changes, so:

- a wait that stands for a number of ticks uses ticks(n) or scaled(seconds), where
  seconds is the production wall time (n x 50 ms);
- a deadline that only bounds a condition stays as it is (it is not loosened, and
  the condition arrives sooner);
- anything bounded by wall time on the server (the 3 s realm lease, the 2 s idle
  network deadline, admission windows, checkpoints, loot TTLs, consumable delays)
  stays in wall time, and so do the waits that rely on it.
"""
import os
import re

NOMINAL_MS = 50
MIN_MS = 10


def _tick_ms():
    value = os.environ.get("N3E_LIVE_TICK_MS") or str(NOMINAL_MS)
    assert value.isdigit() and MIN_MS <= int(value) <= NOMINAL_MS, ("N3E_LIVE_TICK_MS", value)
    return int(value)


TICK_MS = _tick_ms()
ACTIVE = TICK_MS != NOMINAL_MS
WARNING = f"TEST-ONLY TICK SCALE ACTIVE: one simulation tick every {TICK_MS} ms"


def ticks(n):
    """Wall seconds for n server ticks."""
    return n * TICK_MS / 1000


def scaled(seconds):
    """Wall seconds for a wait of `seconds` at the production 50 ms tick."""
    return seconds * TICK_MS / NOMINAL_MS


def server_env(realm):
    """Variables a scaled suite's server needs; empty values when unscaled, so a
    Compose override can always name them."""
    if not ACTIVE:
        return {"N3E_TEST_TICK_MS": "", "N3E_TEST_REALM": ""}
    assert realm.startswith("test-"), ("a scaled server needs a test- realm", realm)
    return {"N3E_TEST_TICK_MS": str(TICK_MS), "N3E_TEST_REALM": "disposable"}


# Compose suites add this to their server's environment in an override file:
# compose.yaml passes an explicit environment list, so nothing else reaches it.
COMPOSE_ENV = '      N3E_TEST_TICK_MS: "${N3E_TEST_TICK_MS:-}"\n      N3E_TEST_REALM: "${N3E_TEST_REALM:-}"\n'


def compose_override(path):
    """Writes a Compose override handing the server the tick variables (from the
    environment the suite gives docker compose) and returns its -f arguments,
    which follow the suite's base files (isolation.DISPOSABLE_COMPOSE)."""
    path.write_text("services:\n  server:\n    environment:\n" + COMPOSE_ENV)
    return ["-f", str(path)]


def confirm_health(body):
    """The server's /live or /ready body reports the tick it runs; a scaled suite
    derives its waits from TICK_MS, so the two must agree."""
    found = re.search(r"\btick_ms=(\d+)", body)
    assert found and int(found.group(1)) == TICK_MS, ("server tick", body, TICK_MS)


def confirm_log(text):
    """For a server whose health port is not published: its log announces a test
    tick, and only when one is active."""
    assert (WARNING in text) == ACTIVE, ("server tick announcement", TICK_MS, text[-2000:])
