"""PQ-215: N3C2 large-map collision (513-sample heightfield plus gridded objects).

Cooks the generated 513 x 513 fixture (no KO data), loads it in both readers,
checks the server's walk, slope and wall answers, compares the C++ and Rust
answers line by line and the gathered answers with the full scan, and refuses
malformed N3C2 files in the cooker and both readers. For N3C1 it pins the bytes
the previous cooker wrote (the legacy-demo release and a coarse 129-sample
heightfield, hashes taken with the cooker at origin/main e5be06a) and loads
N3C1 files the old code loaded and the grid must not refuse: 129 samples at
32 m and 100 m spacing, and 65,532 triangles stacked in one 4 m cell.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import shutil
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import main  # noqa: E402
import large_map_fixture  # noqa: E402
from common import u, string  # noqa: E402

SERVER, CHECK, ASSET = "target/debug/n3e-server", "build/client/n3e-collision-check", "build/client/n3e-asset-check"
package = Path("build/packages/large-map")
started = time.monotonic()
large_map_fixture.cook(str(package), "build/pq-215/source")
cook_seconds = time.monotonic() - started
raw = (package / "collision.bin").read_bytes()
assert raw[:4] == b"N3C2" and struct.unpack("<II", raw[4:12]) == (513, 513)
assert len(raw) == 4 + 8 + 12 + 4 + 513 * 513 * 4 + 4 + 36 * 12, len(raw)


def run(command, good=True, env=None):
    p = subprocess.run(command, capture_output=True, text=True, env={**os.environ, **(env or {})})
    assert (p.returncode == 0) == good, (command, p.returncode, p.stdout[-2000:], p.stderr[-2000:])
    return p.stdout


def readers(path, good=True):
    a = run([ASSET, str(path)], good)
    b = run([SERVER, "--check-content"], good, {"N3E_PACKAGE": str(path)})
    if good:
        assert a.splitlines()[0] == b.splitlines()[0], (a, b)


# Both readers load the whole release and agree on its identity.
readers(package)

# Server walk, slope and wall answers (radius 0.35, height 1.8, step 0.4).
queries = [
    "0 0 0 0 0 1",          # flat spawn ground
    "1.5 0 1 0 1 1",        # thin object wall at x = 2
    "199.5 50 1 0 1 10",    # 56-degree terrain cliff at x = 200
    "-16 -8 1 0 0 1",       # bridge deck at 2.2 m
    "1100 0 1 0 0 1",       # off the map: no support
    "899.5 900 1 0 1 10",   # far-corner object wall
    "-600 300 1 0.5 1 1",   # rolling hills: walkable slope
]
rng = random.Random(215)
queries += ["%.4f %.4f %.4f %.4f %d %.3f" % (rng.uniform(-1030, 1030), rng.uniform(-1030, 1030),
            rng.uniform(-1, 1), rng.uniform(-1, 1), rng.randrange(3), rng.uniform(1, 10)) for _ in range(300)]
with tempfile.TemporaryDirectory(dir="build") as td:
    td = Path(td)
    (td / "q.txt").write_text("\n".join(queries) + "\n")
    rust = run([SERVER, "--collision-probe", str(package / "collision.bin"), str(td / "q.txt")]).splitlines()
    cpp = run([CHECK, "probe", str(package / "collision.bin"), str(td / "q.txt")]).splitlines()
    header = rust[0].split()
    assert header[:8] == cpp[0].split()[:8], (rust[0], cpp[0])  # decode hash and memory
    triangles, memory, load_ms = int(header[2]), int(header[8]), float(header[10])
    assert triangles == 512 * 512 * 2 + 12 and memory < 4 * 1024 * 1024, header
    assert rust[1:] == cpp[1:], [(a, b) for a, b in zip(rust[1:], cpp[1:]) if a != b][:5]
    flat, wall, cliff, bridge, off, far, hill = [list(map(float, l.split())) if l != "none" else None for l in rust[1:8]]
    assert flat == [0, 0, 0, 0]
    assert abs(wall[1] - (2 - 0.35)) < 1e-4, wall          # stopped by the radius
    assert 199 < cliff[1] < 200 - 0.35 + 1e-4, cliff       # steep cells are walls
    assert bridge[0] == bridge[2] == 2.200000048 and bridge[1] > -16, bridge
    assert off is None
    assert abs(far[1] - (900 - 0.35)) < 1e-3, far
    assert hill[1] > -600 and hill[0] != hill[2], hill     # moved and changed height on a slope

    # Gathered answers equal the full scan (C++ also checks camera and pick rays).
    for path, samples in [(package, 6), (Path("build/packages/legacy-demo"), 3000)]:
        out = run([SERVER, "--collision-compare", str(path / "collision.bin"), str(samples)])
        assert out.splitlines()[-1].endswith("mismatches 0"), out
        out = run([CHECK, "compare", str(path / "collision.bin"), str(max(samples, 30))])
        assert " mismatches 0 " in out.splitlines()[-1], out
    # N3C1 is untouched: the same probe agrees across languages there too.
    rust = run([SERVER, "--collision-probe", "build/packages/legacy-demo/collision.bin", str(td / "q.txt")]).splitlines()
    cpp = run([CHECK, "probe", "build/packages/legacy-demo/collision.bin", str(td / "q.txt")]).splitlines()
    assert rust[0].split()[:8] == cpp[0].split()[:8] and rust[1:] == cpp[1:]

    # Hostile N3C2: every reader refuses, after the release index is rehashed.
    work = td / "bad"
    shutil.copytree(package, work)
    manifest = json.loads((package / "recipe.json").read_text())["manifest"]

    def rehash(data):
        (work / "collision.bin").write_bytes(data)
        files = sorted(p.name for p in work.iterdir() if p.name not in ("release.bin", "release.sha256"))
        index = (b"N3R1" + u(1) + u(manifest["engine_version"]) + u(manifest["protocol_version"])
                 + string(manifest["game_id"]) + string(manifest["package_version"]) + u(len(files)))
        for name in files:
            b = (work / name).read_bytes()
            index += string(name) + u(len(b)) + hashlib.sha256(b).digest()
        (work / "release.bin").write_bytes(index)

    rehash(raw)
    readers(work)

    def patch(offset, value, fmt="<I"):
        b = bytearray(raw)
        b[offset:offset + 4] = struct.pack(fmt, value)
        return bytes(b)

    for bad in [raw[:-1], raw + b"\0", b"N3C3" + raw[4:], patch(4, 514), patch(8, 1),
                patch(20, 8.01, "<f"), patch(20, 0.0, "<f"), patch(24, 3), patch(28, float("nan"), "<f"),
                patch(28, 2e6, "<f"), patch(len(raw) - 36 * 12 - 4, 37)]:
        rehash(bad)
        readers(work, False)
        for command in ([SERVER, "--collision-probe", str(work / "collision.bin"), str(td / "q.txt")],
                        [CHECK, "probe", str(work / "collision.bin"), str(td / "q.txt")]):
            run(command, False)

# N3C1 bytes equal the previous cooker's (sha256 taken with origin/main e5be06a).
with tempfile.TemporaryDirectory(dir="build") as td:
    main.cook(Path("tests/fixtures/legacy-demo"), Path(td) / "legacy")
    for name, pinned in [("collision.bin", "e1cfdaabc94ca5d3c8a7c5433e6409da7e14a7d8ca6ceffdf5a632d54250bcd0"),
                         ("release.bin", "e4ff05983d5fba2dadfd7ce32136d8094c87e353087571f156f7bbd64abf3381")]:
        assert hashlib.sha256((Path(td) / "legacy" / name).read_bytes()).hexdigest() == pinned, name
coarse = dict(width=129, depth=129, origin=[-2048, 0, -2048], spacing=32, diagonal="alternating",
              heights=[round(math.sin(i * 0.37) * 5, 3) for i in range(129 * 129)])
coarse_bytes = main.collision_bytes(coarse, [])
assert hashlib.sha256(coarse_bytes).hexdigest() == "dcc14a8be23882aae66d17498d87e29eb9092d14229ae6b1c704fd633cfce80e"

# N3C1 the old readers loaded, which the grid must not refuse (no budget):
# coarse heightfields whose triangles span many cells, and one crowded cell.
stacked = [p for k in range(65532 // 3) for p in ([0, k * 0.01, 0], [1, k * 0.01, 0], [0, k * 0.01, 1])]
with tempfile.TemporaryDirectory(dir="build") as td:
    td = Path(td)
    (td / "q.txt").write_text("0.3 0.3 1 0 0 1\n10 10 1 1 1 2\n")
    for name, data in [("coarse32", coarse_bytes),
                       ("coarse100", main.collision_bytes({**coarse, "origin": [-6400, 0, -6400], "spacing": 100}, [])),
                       ("stacked", b"N3C1" + u(len(stacked)) + b"".join(struct.pack("<3f", *p) for p in stacked))]:
        assert data[:4] == b"N3C1", name
        (td / name).write_bytes(data)
        rust = run([SERVER, "--collision-probe", str(td / name), str(td / "q.txt")]).splitlines()
        cpp = run([CHECK, "probe", str(td / name), str(td / "q.txt")]).splitlines()
        assert rust[0].split()[:8] == cpp[0].split()[:8] and rust[1:] == cpp[1:], (name, rust, cpp)
        assert rust[1] != "none", (name, rust)
        out = run([SERVER, "--collision-compare", str(td / name), "20"])
        assert out.splitlines()[-1].endswith("mismatches 0"), out
        out = run([CHECK, "compare", str(td / name), "30"])
        assert " mismatches 0 " in out.splitlines()[-1], out

# Cooker bounds.
hf = dict(width=3, depth=3, origin=[0, 0, 0], spacing=2, heights=[0] * 9)
for edit, why in [(dict(width=513, depth=2, spacing=8.01, heights=[0] * 1026), "extent"),
                  (dict(width=513, depth=2, spacing=0.0001, heights=[0] * 1026), "degenerate")]:
    try:
        main.collision_bytes({**hf, **edit}, [])
    except ValueError:
        pass
    else:
        raise AssertionError(why)
# The cook itself refuses more than 513 samples a side.
source = large_map_fixture.source("build/pq-215/source-514")
meta = json.loads((source / "scene.json").read_text())
meta["heightfield"].update(width=514, heights=meta["heightfield"]["heights"] + [0] * 513)
(source / "scene.json").write_text(json.dumps(meta))
try:
    main.cook(source, Path("build/pq-215/package-514"))
except ValueError:
    pass
else:
    raise AssertionError("514 samples cooked")
assert not Path("build/pq-215/package-514").exists()
big = dict(width=130, depth=2, origin=[0, 0, 0], spacing=1, heights=[0] * 260)
assert main.collision_bytes(big, [])[:4] == b"N3C2"
try:
    main.collision_bytes({**big}, [[0, 0, 0]] * 3)
except ValueError:
    pass
else:
    raise AssertionError("degenerate object triangle")
try:
    main.collision_bytes({**big}, [[0, 0, 0], [1, 0, 0], [0, 0, 1]] * (main.N3C2_MAX_OBJECT_POINTS // 3 + 1))
except ValueError:
    pass
else:
    raise AssertionError("object vertex cap")
peak_kib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
print("PASS large-map collision: N3C2 513x513 (%d triangles, %d B held, load %.1f ms debug, cook %.1f s, "
      "child peak RSS %d KiB); walls, cliff, bridge, off-map, slope; C++/Rust identical on %d probes; "
      "gathered == full scan; hostile N3C2 refused by cooker and both readers; N3C1 bytes pinned to the previous cooker; "
      "coarse and crowded N3C1 load in both runtimes"
      % (triangles, memory, load_ms, cook_seconds, peak_kib, len(queries)))
