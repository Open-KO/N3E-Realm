"""KO-01 producer/reader compatibility and hostile policy/input regressions."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import main
import rules
import movement_fixture
from common import u, string

package = movement_fixture.cook()
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
base = rules.cook(manifest["gameplay"], "demo")
assert base[:4] == b"N3G3"
for key, value in [
    ("run_speed", 6.01),
    ("run_speed", float("nan")),
    ("backward_speed", 2),
    ("radius", 0.09),
    ("height", 0.49),
    ("step_height", 0),
    ("radius", True),
]:
    r = copy.deepcopy(manifest["gameplay"])
    r["movement"][key] = value
    try:
        rules.cook(r, "demo")
    except ValueError:
        pass
    else:
        raise AssertionError((key, value))
for edit in [
    lambda r: r["movement"].pop("radius"),
    lambda r: r["movement"].update(unknown=1),
    lambda r: r.update(speed=6.01),
    lambda r: r.update(speed=float("nan")),
    lambda r: r["movement"].update(height=.5, step_height=.5),
]:
    r = copy.deepcopy(manifest["gameplay"])
    edit(r)
    try:
        rules.cook(r, "demo")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid/missing/unknown movement policy accepted")

with tempfile.TemporaryDirectory(dir="build/ko-01") as td:
    root = Path(td) / "source"
    shutil.copytree("build/ko-01/source", root)
    out = Path(td) / "package"

    def readers(good):
        hashes = []
        for command in [
            ["build/client/n3e-asset-check", str(out)],
            ["target/debug/n3e-server", "--check-content"],
        ]:
            p = subprocess.run(
                command,
                env={**os.environ, "N3E_PACKAGE": str(out)},
                capture_output=True,
                text=True,
            )
            assert (p.returncode == 0) == good, (command, p.stdout, p.stderr)
            if good:
                hashes.append(p.stdout.splitlines()[0])
        if good:
            assert hashes[0] == hashes[1]

    digest = main.cook(root, out)
    readers(True)
    # Every movement field participates in canonical recipe and cooked identity.
    for key in rules.MOVEMENT:
        changed = copy.deepcopy(manifest)
        changed["gameplay"]["movement"][key] += (
            0.01 if key != "backward_speed" else -0.01
        )
        (root / "package.json").write_text(json.dumps(changed))
        assert main.cook(root, out) != digest
        readers(True)
    (root / "package.json").write_text(json.dumps(manifest))
    main.cook(root, out)

    def rehash(data, engine=2, protocol=2):
        (out / "gameplay.bin").write_bytes(data)
        files = sorted(["collision.bin", "gameplay.bin", "recipe.json", "scene.bin"])
        index = (
            b"N3R1"
            + u(1)
            + u(engine)
            + u(protocol)
            + string("demo")
            + string(manifest["package_version"])
            + u(len(files))
        )
        for name in files:
            b = (out / name).read_bytes()
            index += string(name) + u(len(b)) + hashlib.sha256(b).digest()
        (out / "release.bin").write_bytes(index)

    for offset, value in [
        (0, 6.01),
        (0, float("inf")),
        (4, 2),
        (8, 0),
        (12, 0.4),
        (16, 0.6),
    ]:
        data = bytearray(base)
        data[len(base) - 20 + offset : len(base) - 16 + offset] = struct.pack(
            "<f", value
        )
        rehash(data)
        readers(False)
    for data in [base[:-1], base + b"\0", b"N3G9" + base[4:]]:
        rehash(data)
        readers(False)
    for engine, protocol in [(1, 1), (2, 1), (1, 2), (3, 3)]:
        rehash(base, engine, protocol)
        readers(False)
    for version in [1, 3]:
        changed = copy.deepcopy(manifest)
        changed["engine_version"] = changed["protocol_version"] = version
        (root / "package.json").write_text(json.dumps(changed))
        try:
            main.cook(root, out)
        except ValueError:
            pass
        else:
            raise AssertionError("producer compatibility")
    # Legacy recipes stay byte-compatible and use v1; nonzero modes are rejected live.
    legacy = json.loads(Path("tests/fixtures/legacy-demo/package.json").read_text())
    assert rules.cook(legacy["gameplay"], "demo")[:4] == b"N3G1"
    fixture = Path(td) / "input.txt"
    fixture.write_text("0 0 0 0 1 0 99\n")
    for command in [
        ["build/client/n3e-walk-check", str(fixture)],
        ["target/debug/n3e-server", "--walk-fixture", str(fixture)],
    ]:
        for config in [
            [1.5, 4.5, 1.5, 0.2, 1.6, 0.25],
            [1.5, 7, 1.5, 0.2, 1.6, 0.25],
            [1.5, 4.5, 1.5, float("nan"), 1.6, 0.25],
        ]:
            p = subprocess.run(command + list(map(str, config)), capture_output=True)
            assert p.returncode != 0, (command, config)
print(
    "PASS movement producer/independent readers, changed identity, rehashed invalid bounds/NaN/infinity/truncation/version, invalid mode/config"
)
