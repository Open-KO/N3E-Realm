"""Original camera package compatibility, validation, and analytic geometry checks."""

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import camera
import camera_fixture
import main
from common import u, string, digest

package = camera_fixture.cook()
subprocess.run(["build/client/n3e-camera-check", str(package)], check=True)


def check(out, good=True):
    results = []
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
        results.append(p.stdout.splitlines()[0] if p.returncode == 0 else "")
    if good:
        assert results[0] in results[1], results


check(package)
with tempfile.TemporaryDirectory(dir="build") as tmp:
    root = Path(tmp) / "source"
    shutil.copytree("tests/fixtures/legacy-demo", root)
    m = json.loads((root / "package.json").read_text())
    m.update(camera=camera_fixture.PROFILE, engine_version=3)
    (root / "package.json").write_text(json.dumps(m))
    out = Path(tmp) / "release"
    main.cook(root, out)
    check(out)  # wire 1 also supported
    original = (out / "camera.bin").read_bytes()
    files = {
        p.name: p.read_bytes()
        for p in out.iterdir()
        if p.name not in ("release.bin", "release.sha256")
    }

    def repack(data, engine=3, omit=False):
        changed = dict(files)
        if omit:
            changed.pop("camera.bin")
        else:
            changed["camera.bin"] = data
        index = (
            b"N3R1"
            + u(1)
            + u(engine)
            + u(1)
            + string(m["game_id"])
            + string(m["package_version"])
            + u(len(changed))
        )
        for name, data in sorted(changed.items()):
            (out / name).write_bytes(data)
            index += string(name) + u(len(data)) + digest(data)
        (out / "release.bin").write_bytes(index)

    malformed = [original[:-1], original + b"\0", b"BAD!" + original[4:]]
    for field, value in [
        (0, float("nan")),
        (1, 1.39),
        (2, 0.1),
        (3, 100),
        (4, 8),
        (5, 3),
        (6, -1),
        (7, 2),
        (8, 0),
        (9, 1),
        (10, 0),
        (11, 0),
        (12, 0),
        (13, 2),
    ]:
        b = bytearray(original)
        struct.pack_into("<f", b, 4 + field * 4, value)
        malformed.append(bytes(b))
    malformed.append(original[:-4] + u(2))
    for data in malformed:
        repack(data)
        check(out, False)
    repack(original, engine=2)
    check(out, False)
    repack(original, omit=True)
    check(out, False)
    main.cook(root, out)
    (out / "camera.bin").write_bytes(b"tampered")
    check(out, False)
    for key, value in [
        ("pitch", float("inf")),
        ("distance_min", 11),
        ("clearance", 0.01),
        ("facing_relative", 1),
        ("extra", 0),
    ]:
        c = copy.deepcopy(camera_fixture.PROFILE)
        c[key] = value
        try:
            camera.cook(c)
        except ValueError:
            pass
        else:
            raise AssertionError(key)
# PQ-012 (D-143): the KO camera extension, N3V2. The KO package's values are
# the client binary's (KnightOnLine.exe 005e3e20, 005c6990; drag factors at the
# nominal frame time 1/30 s, the D-143 correction).
ko = json.loads(Path("games/moradon/camera.json").read_text())
assert ko["drag_vertical"] == "distance"
assert abs(ko["yaw_per_pixel"] - 0.02 * math.pi / 30) < 1e-12
assert abs(ko["distance_per_pixel"] - 0.02 * math.pi * 4 / 30) < 1e-12
assert abs(ko["key_pitch_rate"] - math.pi / 4) < 1e-12 and ko["edge_yaw_rate"] == 2
assert (ko["pitch_min"], ko["pitch_max"], ko["distance_min"], ko["distance_max"]) == (
    camera_fixture.PROFILE["pitch_min"], camera_fixture.PROFILE["pitch_max"], 2, 10)
assert camera.cook(camera_fixture.PROFILE)[:4] == b"N3V1" and len(camera.cook(camera_fixture.PROFILE)) == 64
extended = {**camera_fixture.PROFILE, **ko}
with tempfile.TemporaryDirectory(dir="build") as tmp:
    root = Path(tmp) / "source"
    shutil.copytree("tests/fixtures/legacy-demo", root)
    m = json.loads((root / "package.json").read_text())
    m.update(camera=extended, engine_version=3)
    (root / "package.json").write_text(json.dumps(m))
    out = Path(tmp) / "release"
    main.cook(root, out)
    original = (out / "camera.bin").read_bytes()
    assert original[:4] == b"N3V2" and len(original) == 80, len(original)
    assert original[4:64] == camera.cook({k: extended[k] for k in camera_fixture.PROFILE})[4:]
    check(out)
    subprocess.run(["build/client/n3e-camera-check", str(out)], check=True)
    files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}
    malformed = [original[:-1], original + b"\0", original[:64], b"N3V3" + original[4:]]
    for offset, packed in [(64, u(2)), (68, struct.pack("<f", 0)), (68, struct.pack("<f", 1)),
                           (72, struct.pack("<f", -0.1)), (72, struct.pack("<f", 7)),
                           (76, struct.pack("<f", float("nan"))), (76, struct.pack("<f", 6.4))]:
        b = bytearray(original)
        b[offset:offset + 4] = packed
        malformed.append(bytes(b))
    for data in malformed:
        repack(data)
        check(out, False)
    for key, value in [("drag_vertical", "yaw"), ("drag_vertical", 1), ("distance_per_pixel", 0),
                       ("key_pitch_rate", -1), ("edge_yaw_rate", float("inf")), ("edge_yaw_rate", True)]:
        c = {**extended, key: value}
        try:
            camera.cook(c)
        except ValueError:
            pass
        else:
            raise AssertionError((key, value))
    partial = dict(extended)
    partial.pop("edge_yaw_rate")
    try:
        camera.cook(partial)
    except ValueError:
        pass
    else:
        raise AssertionError("partial extension")
print(
    "PASS camera C++/Rust release identity, wire 1/2, engine compatibility, rehashed malformed bounds/truncation/trailing/tamper, producer validation, N3V2 KO extension"
)
