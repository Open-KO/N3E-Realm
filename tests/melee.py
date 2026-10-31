"""Both release readers enforce optional melee identity, compatibility and bounds."""

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
import melee
import melee_fixture
import main
from common import u, string, digest

package = melee_fixture.cook()
subprocess.run(["build/client/n3e-melee-check", str(package)], check=True)


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
        results.append(p.stdout.splitlines()[0] if p.returncode == 0 else "")
    if good:
        assert results[0] in results[1], results


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

    def repack(changed, engine=4, protocol=2):
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

    offset = 4
    for _ in range(3):
        offset += 4 + struct.unpack_from("<I", files["gameplay.bin"], offset)[0]
    for field, value in [(1, 0), (1, 100001), (3, 100001), (4, 0), (4, 1201)]:
        data = bytearray(files["gameplay.bin"])
        struct.pack_into("<I", data, offset + field * 4, value)
        repack(dict(files, **{"gameplay.bin": data}))
        check(out, False)
    original = files["melee.bin"]
    for data in [original[:-1], original + b"\0", b"BAD!" + original[4:]]:
        repack(dict(files, **{"melee.bin": data}))
        check(out, False)
    for field, value in [
        (0, 0),
        (0, float("nan")),
        (1, 6),
        (2, -1),
        (2, float("inf")),
        (3, 1),
    ]:
        data = bytearray(original)
        struct.pack_into("<f", data, 4 + field * 4, value)
        repack(dict(files, **{"melee.bin": data}))
        check(out, False)
    repack(files, 3)
    check(out, False)
    missing = dict(files)
    missing.pop("melee.bin")
    repack(missing)
    check(out, False)
    repack(missing, 3)
    check(out, False)  # zero cost cannot enter a legacy package
    repack(files, 4, 1)
    check(out, False)  # movement version mismatch
    # Optional camera and movement are independent of melee, protocol remains 1/2.
    root = Path(tmp) / "source"
    shutil.copytree("tests/fixtures/legacy-demo", root)
    m = json.loads((root / "package.json").read_text())
    m.update(
        engine_version=4,
        melee=dict(actor_radius=0.5, target_radius=1.5, reach=0, facing_dot=0.7),
    )
    m["gameplay"]["cost"] = 0
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    check(out)
    m["gameplay"]["cost"] = 1
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    check(out)
    for k in melee.FIELDS:
        bad = copy.deepcopy(m)
        bad["melee"][k] = True
        (root / "package.json").write_text(json.dumps(bad))
        try:
            main.cook(root, out)
        except ValueError:
            pass
        else:
            raise AssertionError(k)
print(
    "PASS melee C++/Rust release agreement, malformed/bounds/compatibility, zero and positive cost"
)
