"""RQ-154 (Q96): isolated PostgreSQL, a new character's start and starting items.

The equipment fixture (original items, tests/equipment_live.py) with synthetic
create rules (race 7 with specialties 70 and 71), the realm owner's start and
two starting sets, one empty (KO's operator gives none): the server's
inventory::kit_tests::durable_starting_items creates a character of each
specialty and one by name alone and checks where each stands and what its bag
starts with (content/character-create.md, "Start and starting items").
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
from equipment_live import prepare  # noqa: E402
from isolation import DISPOSABLE_POSTGRES, container_logs  # noqa: E402
from readiness import wait_postgres  # noqa: E402

prepare()
B = Path("build/ko-completion/character-create")
root, package = B / "source", B / "package"
shutil.rmtree(B, ignore_errors=True)
shutil.copytree("build/ko-completion/equipment/source", root)
m = json.loads((root / "package.json").read_text())
m["create"] = dict(
    stats=3, nation=1,
    races=[dict(race=7, nation=1, faces=4, hairs=3, specialties=[dict(specialty=70, bonus=5, base=[40, 30, 20]),
                                                                 dict(specialty=71, bonus=5, base=[20, 30, 40])]),
           dict(race=8, nation=2, faces=2, hairs=1, specialties=[dict(specialty=80, bonus=0, base=[10, 10, 10])])],
    name=dict(min=1, max=20, punctuation="_:;"), reserved=[],
    refusals=dict(limit="", mismatch="", taken="", failed="", name="", stats=""),
    # A point on the fixture's ground; specialty 70 starts with its own set,
    # 71 with none, 80 (not created here) with the package's starting items.
    start=[1.0, 1.0],
    items=[dict(specialty=70, items=[["demo:item/blade", 1], ["demo:item/potion", 3], ["demo:item/ring", 1]]),
           dict(specialty=71, items=[])])
(root / "package.json").write_text(json.dumps(m))
sys.path.insert(0, str(ROOT / "tools/assetc"))
import main  # noqa: E402

main.cook(root, package)
env = {**os.environ, "N3E_PACKAGE": str(package.resolve())}
checked = subprocess.run(["target/debug/n3e-server", "--check-content"], env=env, capture_output=True, text=True)
assert checked.returncode == 0, (checked.stdout, checked.stderr)
assert "create races=2 specialties=3 stats=3 nation=1 fixed=false start=1,1 items=2" in checked.stdout.splitlines(), \
    checked.stdout
name = "n3e-create-" + uuid.uuid4().hex[:10]


def run(*args, good=True, env=None):
    p = subprocess.run(args, capture_output=True, text=True, env=env, timeout=300)
    assert not good or p.returncode == 0, (args, p.stdout, p.stderr)
    return p


try:
    run("docker", "run", "-d", "--rm", "--name", name, "-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
        "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES, "-p", "127.0.0.1::5432",
        "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad")
    port = wait_postgres(name)
    env["N3E_TEST_DATABASE_URL"] = f"host=127.0.0.1 port={port} user=n3e password=test-only dbname=n3e"
    p = run("cargo", "test", "--locked", "inventory::kit_tests::durable_starting_items", "--", "--ignored", "--exact",
            "--nocapture", env=env, good=False)
    (B / "database.log").write_text(p.stdout + p.stderr)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "PASS create start and starting items" in p.stdout, p.stdout
    print("PASS create start and starting items: a new character starts at the realm owner's start with its "
          "specialty's set (an empty set none, a nameless create the package's starting items)")
finally:
    container_logs("postgres", ["docker", "logs", "--timestamps", name])
    run("docker", "rm", "-f", name, good=False)
