"""Opt-in (make live-ko): 1298's terrain light maps over the near terrain, drawn
offscreen on the packages cooked from the player's own KO data (PQ-387, D-204).

For each cooked map the test client draws one frame from a fixed camera above
the package start twice, without (pass 0) and with (pass 1) its N3WO maps
(N3E_TEST_WORLD_OVERLAY), and the two captures are compared:

* a zone with light maps (the default, classic and 1097 Moradon; homelands 10
  and 20) draws its maps on at least one near patch of the eye's 3 x 3
  window, and at least 2,000 pixels change; where every map texel is black
  (all but elmo2004, PQ-385 claim 20) no pixel gets brighter;
* the 1097 Karus homeland, whose `.tlt` holds no map, has no overlay: no
  patch draws one and the two captures are byte-identical;
* the negative control: the 1298 Karus homeland's camera (key 10,
  `ko-zone-10`, `karus2004`, 3,649 maps) with the maps turned off
  (N3E_TEST_WORLD_OVERLAY_OFF) draws byte-identical captures, so the positive
  check above fails without the maps.

The camera is the package start's ground (the cooked collision, read with the
client's own probe) seen from 45 m up and 28 m south. No server or stack.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

WORK = Path(os.environ.get("N3E_KO_WORK", "build/live-ko/work"))
B = Path("build/live-ko/terrain-overlay")
B.mkdir(parents=True, exist_ok=True)
# package, source folder (its package.json), light maps (PQ-385), all black
PACKAGES = [("moradon", "ko-moradon", 530, True), ("moradon-classic", "ko-moradon-classic", 519, True),
            ("moradon-1097", "ko-moradon-1097", 394, True), ("ko-zone-10", "ko-zone-10", 3649, True),
            ("ko-zone-20", "ko-zone-20", 4062, False), ("ko-1097-zone-1", "ko-1097-zone-1", 0, True)]

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED terrain light maps need N3E_GRAPHICAL=1 (make live-ko)")
    sys.exit(0)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(path):
    data = path.read_bytes().split(b"\n", 3)[3]
    return [data[i:i + 3] for i in range(0, len(data), 3)]


def ground(package, x, z):
    queries = B / "probe.txt"
    queries.write_text("%r %r 0 0 0 1\n" % (x, z))
    out = subprocess.run(["build/client/n3e-collision-check", "probe", str(package / "collision.bin"), str(queries)],
                         capture_output=True, text=True, check=True).stdout.splitlines()[1]
    return float(out.split()[0])


def draw(package, name, view, extra=None):
    capture = B / (name + ".ppm")
    run = subprocess.run(["build/client/n3e-test-client", str(package), "--smoke", "--capture", str(capture)],
                         capture_output=True, text=True, timeout=600,
                         env={**os.environ, "N3E_TEST_WORLD_OVERLAY": "1", "N3E_TEST_WORLD_VIEW": view, **(extra or {})})
    (B / (name + "-client.log")).write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "PASS world overlay matched-camera captures" in run.stdout, \
        (name, run.stdout[-2000:], run.stderr[-2000:])
    rows = re.findall(r"^WORLD_OVERLAY pass=(\d) patches=(\d+) centre=(-?\d+),(-?\d+) uploads=\d+ withheld=\d+$",
                      run.stdout, re.M)[-2:]
    shown = re.findall(r"^world overlay maps=(\d+) layers=(\d+)$", run.stdout, re.M)
    return [Path(str(capture) + s) for s in (".no-overlay.ppm", ".overlay.ppm")], rows, shown


results = []
for name, source, maps, black in PACKAGES:
    package = WORK / "packages" / name
    manifest = json.loads((WORK / source / "package.json").read_text())
    x, z = manifest["gameplay"]["spawn_x"], manifest["gameplay"]["spawn_z"]
    y = ground(package, x, z)
    view = "%r %r %r %r %r %r" % (x, y + 45, z + 28, x, y, z)
    (plain, lit), rows, shown = draw(package, name, view)
    if not maps:
        assert not (package / "world-overlay.bin").exists() and shown == [] and rows == [], (name, rows, shown)
        assert digest(plain) == digest(lit), name
        results.append("%s no maps, captures identical" % name)
        continue
    assert shown == [(str(maps), "36")], (name, shown)
    assert rows[0][:2] == ("0", "0") and rows[1][0] == "1" and int(rows[1][1]) >= 1, (name, rows)
    a, b = pixels(plain), pixels(lit)
    changed = [(p, q) for p, q in zip(a, b) if p != q]
    brighter = sum(1 for p, q in changed if sum(q) > sum(p))
    assert len(changed) >= 2000, (name, len(changed))
    if black:
        assert brighter == 0, (name, brighter)
    results.append("%s %d maps, %s near patches drawn with maps, %d pixels changed (%d brighter)"
                   % (name, maps, rows[1][1], len(changed), brighter))

# Negative control: the maps off draw the frame unchanged, so the checks above fail.
package = WORK / "packages" / "ko-zone-10"
manifest = json.loads((WORK / "ko-zone-10" / "package.json").read_text())
x, z = manifest["gameplay"]["spawn_x"], manifest["gameplay"]["spawn_z"]
y = ground(package, x, z)
(plain, lit), rows, _ = draw(package, "ko-zone-10-off", "%r %r %r %r %r %r" % (x, y + 45, z + 28, x, y, z),
                             {"N3E_TEST_WORLD_OVERLAY_OFF": "1"})
assert digest(plain) == digest(lit) and rows[1][:2] == ("1", "0"), rows
print("PASS KO terrain light maps graphical (PQ-387): " + "; ".join(results)
      + "; with the maps off the key 10 captures are identical")
