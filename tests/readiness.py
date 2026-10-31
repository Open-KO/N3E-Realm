"""Readiness wait for the disposable Postgres containers the live suites start.

The postgres image initialises a fresh data directory with a temporary server that
listens only on its Unix socket, then restarts it with TCP enabled. Until the final
server listens, Docker's published host port accepts and then closes or resets the
connection, so a client sees `Error { kind: Closed }`, `Connection reset by peer`
or, one step later, `the database system is starting up`. Measured on 2026-09-30
(PQ-001 attempt 2): about 3 s of those states on an idle machine.

`wait_postgres` returns only when both ends are ready: `pg_isready` over TCP inside
the container (so not the temporary server) and a real postmaster answering an
SSLRequest through the published host port. Callers then connect once and treat
every error as real; no caller retries a migration or query on error text.
"""
import socket
import struct
import subprocess
import time

from isolation import free_ports  # noqa: F401  (re-exported; PQ-114 port ranges)

SSL_REQUEST = struct.pack("!ii", 8, 80877103)


def _host_port(name):
    p = subprocess.run(["docker", "port", name, "5432"], capture_output=True, text=True)
    lines = p.stdout.split()
    return lines[0].rsplit(":", 1)[1] if p.returncode == 0 and lines else None


def _postmaster_answers(port):
    """True when the published port reaches a postmaster: it replies to an
    SSLRequest with one byte, 'S' or 'N'. A proxy with no backend closes or
    resets instead."""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1) as s:
            s.sendall(SSL_REQUEST)
            return s.recv(1) in (b"S", b"N")
    except OSError:
        return False


def wait_postgres(name, timeout=90, user="n3e"):
    """Block until container `name` accepts Postgres connections on its published
    port 5432 and return that host port as a string. Raises with the container's
    last log lines when the deadline passes; it never falls through silently."""
    deadline = time.monotonic() + timeout
    port, last = None, ""
    while time.monotonic() < deadline:
        port = port or _host_port(name)
        check = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", user],
                               capture_output=True, text=True)
        last = (check.stdout + check.stderr).strip()
        if check.returncode == 0 and port and _postmaster_answers(port):
            return port
        time.sleep(0.1)
    logs = subprocess.run(["docker", "logs", "--tail", "20", name], capture_output=True, text=True)
    raise AssertionError(f"Postgres in {name} not ready after {timeout} s "
                         f"(host port {port}, pg_isready: {last!r})\n{logs.stdout}{logs.stderr}")
