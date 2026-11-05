"""RQ-165: front-end.bin whose models are past four joint influences (N3FE
version 30, 32 since RQ-005's select characters, 34 since RQ-198's select
faces and hairs; engine 45; content/front-end.md).

A KO race whose create model has drawn vertices with more than four joint
influences (the Arch Tuarek's looks lower part: 49 with five) keeps every one
in the front end as on the player path, as KO's skinning 00419f00 sums them
(D-176): its model records and parts are N3SI or N3SJ, and the file is version
34, written only then, so a file without one stays version 33 byte for byte.
The client loader's reading of the records and its skinning are
tests/front_end.py's (n3e-front-end-check); the race's cook is
tests/ko_player_races.py's. This test is the package's:

Synthetic, no KO data: the engine 41 package of tests/npc_scale_live.py with a
front-end.bin of a version 33 or 34 header and zeros, which neither the cook
nor either release load reads past (as tests/front_end_bound.py). Checks:

- the cooker takes version 34 at engine 45 only (42 and 44 refused) and
  version 33 at 42, not 45;
- both release loads take the engine 45 package (the client's engine bound,
  the server's header read);
- the server refuses a version 34 header in a package re-indexed at engine 44,
  a version 35 header at 45, and RQ-198's predecessors 31 and 32 at 45.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools/assetc"))
sys.path.append(str(ROOT / "tests"))
import main  # noqa: E402
import ko_front_end  # noqa: E402
from common import string, u  # noqa: E402
import npc_scale_live  # noqa: E402

assert ko_front_end.TABLES_VERSION == main.FRONT_END_TABLES_VERSION == 34, ko_front_end.TABLES_VERSION
assert ko_front_end.VERSION == 33, ko_front_end.VERSION
assert main.FRONT_END_INFLUENCES_ENGINE == 45 > main.DETAIL_INFLUENCES_ENGINE > main.PLAYER_INFLUENCES_ENGINE


def front_end(path, version):
    """A front-end.bin of a `version` header (3 slots, 1024x768) and zeros."""
    path.write_bytes(b"N3FE" + struct.pack("<4I", version, 3, 1024, 768) + bytes(4096))


def source(root, version, engine):
    m = json.loads((root / "package.json").read_text())
    m["engine_version"] = engine
    (root / "package.json").write_text(json.dumps(m))
    front_end(root / "front-end.bin", version)


def readers(out):
    """(exit code, output) of the client's asset check and the server's content check."""
    results = []
    for cmd in (["build/client/n3e-asset-check", str(out)], ["target/debug/n3e-server", "--check-content"]):
        p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
        results.append((p.returncode, p.stdout + p.stderr))
    return results


def reindex(out, engine, version=None):
    """`out` with its release index at `engine` and, with `version`, its
    front-end.bin's header that version (the index carrying its digest)."""
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    if version is not None:
        front_end(out / "front-end.bin", version)
    names = sorted(p.name for p in out.iterdir() if p.name not in ("release.bin", "release.sha256"))
    index = b"N3R1" + u(1) + u(engine) + u(m["protocol_version"]) + string(m["game_id"]) + \
        string(m["package_version"]) + u(len(names))
    for name in names:
        data = (out / name).read_bytes()
        index += string(name) + u(len(data)) + hashlib.sha256(data).digest()
    (out / "release.bin").write_bytes(index)
    (out / "release.sha256").write_text(hashlib.sha256(index).hexdigest() + "\n")


(ROOT / "build").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="front-end-influences-") as td:
    fixture = npc_scale_live.prepare().parent / "source"
    root = Path(td) / "source"
    shutil.copytree(fixture, root)
    m = json.loads((root / "package.json").read_text())
    m["presentation"]["front-end.bin"] = "front-end.bin"
    (root / "package.json").write_text(json.dumps(m))

    # The cooker: version 34 is engine 45 exactly; version 33 stays 42.
    for version, engine in ((34, 42), (34, 44), (33, 45)):
        source(root, version, engine)
        try:
            main.cook(root, Path(td) / "refused")
            raise AssertionError("the cook took version %d at engine %d" % (version, engine))
        except ValueError as error:
            assert "incompatible" in str(error), (version, engine, error)
    source(root, 33, 42)
    main.cook(root, Path(td) / "package-33")
    assert all(code == 0 for code, _ in readers(Path(td) / "package-33")), readers(Path(td) / "package-33")
    source(root, 34, 45)
    out = Path(td) / "package-34"
    main.cook(root, out)
    assert json.loads((out / "recipe.json").read_text())["manifest"]["engine_version"] == 45
    assert (out / "front-end.bin").read_bytes()[4:8] == u(34)
    assert all(code == 0 for code, _ in readers(out)), readers(out)

    # The server: version 34 only from engine 45; no version past 34, and
    # neither 31 nor 32, which carry no select faces and hairs (RQ-198).
    for engine, version in ((44, None), (45, 35), (45, 31), (45, 32)):
        reindex(out, engine, version)
        code, text = readers(out)[1]
        assert code != 0 and "front end magic/version" in text, (engine, version, text[-400:])
print("PASS front-end influences (RQ-165): a version 34 front-end.bin cooks at engine 45 only (42 and 44 refused; "
      "version 33 at 42, not 45) and both release loads take it; the server refuses version 34 at engine 44 and "
      "versions 35, 31 and 32")
