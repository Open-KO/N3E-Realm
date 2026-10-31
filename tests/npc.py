"""Independent producer/consumer validation for N3N1, including forged rehashed releases."""

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
import npc
import npc_fixture
import main
from common import u, string, digest

package = npc_fixture.cook()


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

    def repack(changed, engine=6, protocol=2):
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

    original = files["npc.bin"]
    for data in [original[:-1], original + b"\0", b"BAD!" + original[4:]]:
        repack(dict(files, **{"npc.bin": data}))
        check(out, False)
    for field, value in [(0,0),(0,2)] + [(i, 12001) for i in range(1,7)] + [(i,0) for i in (1,3,4,5,6)]:
        data = bytearray(original)
        struct.pack_into("<I", data, 4 + field * 4, value)
        repack(dict(files, **{"npc.bin": data}))
        check(out, False)
    for version in [1,2,3,4,5,7]:
        repack(files, version)
        check(out, False)
    missing = dict(files)
    missing.pop("npc.bin")
    repack(missing)
    check(out, False)
    repack(files, 6, 1)
    check(out, False)
    root = Path(tmp) / "source"
    shutil.copytree("tests/fixtures/legacy-demo", root)
    simple = json.loads((root / "package.json").read_text())
    simple.update(engine_version=6, npc=m["npc"])
    (root / "package.json").write_text(json.dumps(simple))
    main.cook(root, out)
    check(out)
    for endpoint in (0, 1):
        edge = copy.deepcopy(simple)
        for key, bounds in npc.FIELDS.items():
            edge["npc"][key] = bounds[endpoint]
        (root / "package.json").write_text(json.dumps(edge))
        main.cook(root, out)
        check(out)
    for field, (lo, hi) in npc.FIELDS.items():
        for value in [True, lo-1, hi+1, 1.5]:
            bad = copy.deepcopy(simple["npc"])
            bad[field] = value
            try:
                npc.cook(bad)
            except ValueError:
                pass
            else:
                raise AssertionError((field, value))
    for bad in [{}, dict(m["npc"], model="unknown"), dict(m["npc"], extra=1)]:
        try:
            npc.cook(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
print("PASS NPC producer, both readers, malformed/hash/compatibility/timer boundaries and legacy-independent policy")
