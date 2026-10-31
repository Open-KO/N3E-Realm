"""Synthetic durable-schema states for the Postgres suites, built from deploy/ alone (Q28).

A database "at migration N" is what persistence::migrate leaves after the first N
entries of MIGRATIONS: each file's SQL applied and (version, SHA-256 of the file)
recorded, under the same advisory lock, in one transaction. A database "ahead of
the server" is the current schema plus one schema_migrations row the server does
not know, as a newer release would leave it after a rollback; persistence::verify
must refuse it ("migration version mismatch") before any durable state is read.
Neither needs an older server build."""
import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "target/debug/n3e-server"


def migrations():
    """(version, path) in persistence.rs MIGRATIONS order, the files the server embeds."""
    text = (ROOT / "server/src/persistence.rs").read_text()
    found = [(int(v), ROOT / p) for v, p in re.findall(r'\((\d+), include_str!\("\.\./\.\./(deploy/[^"]+)"\)\)', text)]
    assert found and [v for v, _ in found] == list(range(1, len(found) + 1)), found
    return found


def psql(container, script, db="n3e"):
    p = subprocess.run(["docker", "exec", "-i", container, "psql", "-v", "ON_ERROR_STOP=1", "-1", "-q", "-U", "n3e", "-d", db],
                       input=script.encode(), capture_output=True, timeout=180)
    assert p.returncode == 0, (p.stdout.decode(), p.stderr.decode())


def migrate_to(container, version, db="n3e"):
    """Bring an empty database to migration `version` exactly as persistence::migrate would."""
    steps = ["SELECT pg_advisory_xact_lock(731001);",
             "CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY, digest text NOT NULL);"]
    for v, path in migrations()[:version]:
        sql = path.read_bytes()
        steps += [sql.decode(), f";\nINSERT INTO schema_migrations VALUES({v},'{hashlib.sha256(sql).hexdigest()}');"]
    psql(container, "\n".join(steps), db)


def ahead_of_server(container, db="n3e"):
    """Record one migration the server does not know; returns the server binary to run against it."""
    psql(container, "INSERT INTO schema_migrations SELECT max(version)+1,'synthetic-future' FROM schema_migrations;", db)
    subprocess.run(["cargo", "build", "--locked"], cwd=ROOT, check=True, capture_output=True, timeout=600)
    return SERVER
