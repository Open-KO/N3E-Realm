"""Expected schema migrations, derived from the SQL the server embeds.

Live suites compare `schema_migrations` against this instead of a hard-coded
count, so adding a migration does not silently break them (PQ-001).
"""
import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def migrations():
    """[(version, sha256 hex)] for deploy/NNN-*.sql, checked against persistence.rs."""
    files = sorted(ROOT.glob("deploy/[0-9][0-9][0-9]-*.sql"))
    source = (ROOT / "server/src/persistence.rs").read_text()
    listed = re.findall(r'\((\d+),\s*include_str!\("\.\./\.\./(deploy/[^"]+)"\)\)', source)
    paths = [f.relative_to(ROOT).as_posix() for f in files]
    assert [p for _, p in listed] == paths, ("persistence.rs MIGRATIONS and deploy/*.sql differ", listed, paths)
    assert [int(v) for v, _ in listed] == list(range(1, len(paths) + 1)), ("migration versions are not 1..N", listed)
    return [(i + 1, hashlib.sha256(f.read_bytes()).hexdigest()) for i, f in enumerate(files)]


def rows():
    """The expected `SELECT version||':'||digest ... ORDER BY version` output lines."""
    return [f"{version}:{digest}" for version, digest in migrations()]


QUERY = "SELECT version||':'||digest FROM schema_migrations ORDER BY version"

# Ignored Rust tests that need only a migrated shared database. The Compose
# suites (multiplayer.py, gameplay.py) run exactly these; every other ignored
# test needs its own fixture package and is owned by a feature suite
# (tests/live.py checks that each one has an owner).
CORE_TESTS = [
    "accounts::database_tests::character_and_realm_fences",
    "persistence::migration_tests::fresh_upgrade_and_failed_second_migration_rollback",
    "persistence::tests::ownership_generation_and_atomic_fence",
    "persistence::tests::start_waits_out_a_dead_owner_and_never_takes_a_live_one",
    "persistence::tests::renewal_rides_out_a_realm_row_wait_inside_admission",
    "persistence::tests::renewal_never_waits_behind_a_fenced_write",
    "rewards::tests::atomic_rewards_and_conflicts",
]


def core_test_command():
    return ["cargo", "test", "--locked", "--", "--ignored", "--exact", *CORE_TESTS, "--test-threads=1"]


def assert_core_tests(output):
    assert f"test result: ok. {len(CORE_TESTS)} passed" in output, output
