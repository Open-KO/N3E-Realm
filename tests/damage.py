"""Independent producer/consumer validation for N3D1, including forged rehashed releases."""

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
import damage
import damage_fixture
import main
from common import u, string, digest

package = damage_fixture.cook()


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

    def repack(changed, engine=5, protocol=2):
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

    original = files["damage.bin"]
    for data in [original[:-1], original + b"\0", b"BAD!" + original[4:]]:
        repack(dict(files, **{"damage.bin": data}))
        check(out, False)
    for field, value in (
        [(0, 0), (0, 2)]
        + [(i, 10001) for i in range(1, 9)]
        + [(i, 0) for i in (3, 4, 7, 8)]
    ):
        data = bytearray(original)
        struct.pack_into("<I", data, 4 + field * 4, value)
        repack(dict(files, **{"damage.bin": data}))
        check(out, False)
    for version in [1, 2, 3, 4, 6]:
        repack(files, version)
        check(out, False)
    missing = dict(files)
    missing.pop("damage.bin")
    repack(missing)
    check(out, False)
    repack(files, 5, 1)
    check(out, False)
    # Damage is independent of movement, melee, camera and imported presentations.
    root = Path(tmp) / "source"
    shutil.copytree("tests/fixtures/legacy-demo", root)
    simple = json.loads((root / "package.json").read_text())
    simple.update(engine_version=5, damage=m["damage"])
    for attack, defense, rate in [(0, 0, 1), (10000, 10000, 10000)]:
        for side in ["player", "npc"]:
            simple["damage"][side] = dict(
                attack=attack, defense=defense, accuracy=rate, evasion=rate
            )
        (root / "package.json").write_text(json.dumps(simple))
        main.cook(root, out)
        check(out)
    for side in ["player", "npc"]:
        for field in damage.STATS:
            for value in [True, -1, 10001, 1.5]:
                bad = copy.deepcopy(simple)
                bad["damage"][side][field] = value
                try:
                    damage.cook(bad["damage"])
                except ValueError:
                    pass
                else:
                    raise AssertionError((side, field, value))
    for bad in [{}, dict(m["damage"], model="unknown"), dict(m["damage"], extra=1)]:
        try:
            damage.cook(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
print(
    "PASS damage producer, both readers, malformed/hash/compatibility/stat boundaries and legacy-independent policy"
)
