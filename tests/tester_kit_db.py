"""RQ-212: isolated PostgreSQL, the tester kit (specs/03-admin-api.md `POST /v1/characters/kit`).

The stats fixture (original items, tests/stats_live.py: one-handed blades and a
two-hander of equal attack, dual wield at half scale, a shield, rings) drives the
server's tester_kit::tests::durable_kit: an unknown name and a character in the
world are refused, the kit raises a character to the curve's cap and equips the
fixture's best arrangement for damage (two blades and two rings: 40 + 20 beats the
two-hander's 40), a second kit keeps the same records, and gear the kit takes off
needs a free bag slot (none: refused, nothing changed).
"""
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
from isolation import DISPOSABLE_POSTGRES, container_logs  # noqa: E402
from readiness import wait_postgres  # noqa: E402
from stats_live import prepare  # noqa: E402

package = prepare()
B = Path("build/ko-completion/tester-kit")
B.mkdir(parents=True, exist_ok=True)
name = "n3e-tester-kit-" + uuid.uuid4().hex[:10]


def run(*args, good=True, env=None):
    p = subprocess.run(args, capture_output=True, text=True, env=env, timeout=300)
    assert not good or p.returncode == 0, (args, p.stdout, p.stderr)
    return p


try:
    run("docker", "run", "-d", "--rm", "--name", name, "-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
        "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES, "-p", "127.0.0.1::5432",
        "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad")
    port = wait_postgres(name)
    env = {**os.environ, "N3E_PACKAGE": str(package),
           "N3E_TEST_DATABASE_URL": f"host=127.0.0.1 port={port} user=n3e password=test-only dbname=n3e"}
    p = run("cargo", "test", "--locked", "-p", "n3e-server", "tester_kit::tests::durable_kit", "--", "--ignored",
            "--exact", "--nocapture", env=env, good=False)
    (B / "database.log").write_text(p.stdout + p.stderr)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert 'kit arrangement ["demo:item/blade", "demo:item/blade", "demo:item/ring", "demo:item/ring"]' in p.stdout, \
        p.stdout
    assert "PASS tester kit" in p.stdout, p.stdout
    print("PASS tester kit: unknown and online characters refused; level cap and the fixture's best damage "
          "arrangement (two blades, two rings) in one audited transaction; a second kit keeps it; a full bag refuses")
finally:
    container_logs("postgres", ["docker", "logs", "--timestamps", name])
    run("docker", "rm", "-f", name, good=False)
