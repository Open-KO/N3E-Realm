"""Independent producer/consumer validation for N3L1, including forged rehashed releases."""

import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import life
import life_fixture
import main
from common import u, string, digest

package = life_fixture.cook()


def check(out, good=True):
    results = []
    for cmd in [
        ["build/client/n3e-asset-check", str(out)],
        ["target/debug/n3e-server", "--check-content"],
    ]:
        p = subprocess.run(
            cmd,
            env={**os.environ, "N3E_PACKAGE": str(out)},
            capture_output=True,
            text=True,
        )
        assert (p.returncode == 0) == good, (cmd, p.stdout, p.stderr)
        if good:
            results.append(p.stdout.splitlines()[0])
    if good:
        assert results[0] in results[1]


check(package)
with tempfile.TemporaryDirectory(dir="build") as tmp:
    out = Path(tmp) / "release"
    shutil.copytree(package, out)
    files = {
        p.name: p.read_bytes()
        for p in out.iterdir()
        if p.name not in ("release.bin", "release.sha256")
    }
    m = json.loads((out / "recipe.json").read_text())["manifest"]

    def repack(changed, engine=7, protocol=3):
        index = (
            b"N3R1"
            + u(1)
            + u(engine)
            + u(protocol)
            + string(m["game_id"])
            + string(m["package_version"])
            + u(len(changed))
        )
        for name, data in sorted(changed.items()):
            (out / name).write_bytes(data)
            index += string(name) + u(len(data)) + digest(data)
        (out / "release.bin").write_bytes(index)

    original = files["life.bin"]
    for data in [original[:-1], original + b"\0", b"BAD!" + original[4:]]:
        repack(dict(files, **{"life.bin": data}))
        check(out, False)
    for field, value in [
        (0, 0),
        (0, 2),
        (1, 1201),
        (2, 1201),
        (3, 12001),
        (3, 0),
        (3, 1),
    ]:
        data = bytearray(original)
        struct.pack_into("<I", data, 4 + field * 4, value)
        repack(dict(files, **{"life.bin": data}))
        check(out, False)
    for version in [1, 2, 3, 4, 5, 6, 8]:
        repack(files, version)
        check(out, False)
    missing = dict(files)
    missing.pop("life.bin")
    repack(missing)
    check(out, False)
    repack(files, 7, 2)
    check(out, False)
    root = Path(tmp) / "source"
    shutil.copytree("tests/fixtures/legacy-demo", root)
    simple = json.loads((root / "package.json").read_text())
    simple.update(engine_version=7, protocol_version=3, life=m["life"])
    (root / "package.json").write_text(json.dumps(simple))
    main.cook(root, out)
    check(out)
    for endpoint in (0, 1):
        edge = copy.deepcopy(simple)
        for key, bounds in life.FIELDS.items():
            edge["life"][key] = bounds[endpoint]
        (root / "package.json").write_text(json.dumps(edge))
        main.cook(root, out)
        check(out)
    for field, (lo, hi) in life.FIELDS.items():
        for value in [True, lo - 1, hi + 1, 1.5]:
            bad = copy.deepcopy(simple["life"])
            bad[field] = value
            try:
                life.cook(bad)
            except ValueError:
                pass
            else:
                raise AssertionError((field, value))
    for bad in [{}, dict(m["life"], model="unknown"), dict(m["life"], extra=1)]:
        try:
            life.cook(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
print(
    "PASS life producer, both readers, malformed/hash/compatibility/timer boundaries and legacy-independent policy"
)
