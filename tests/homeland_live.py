"""Opt-in: walk a KO homeland map on its play stack (PQ-218).

  python tests/ko_stack.py ko-zone-10 tests/homeland_live.py       (make live-ko)
  python tests/ko_stack.py ko-1097-zone-1 tests/homeland_live.py   (make live-ko, PQ-274)
  python tests/homeland_live.py karus|elmorad|karus-1097|elmorad-1097   the persistent stack

Under `make live-ko` tests/ko_stack.py gives this suite a disposable stack of
its own on the package the run cooked from the player's own KO data and START_POSITION
export (build/live-ko/work/packages/ko-zone-KEY) and names it through
N3E_MORADON_STATE / N3E_MORADON_PROJECT. With a zone name it probes the stack
tools/play-ko-zone started (build/ko-zone-KEY-demo/session.json, project
n3e-ko-zone-KEY) with an account of its own; the player's account and
characters are not touched.

The 1097 homelands (PQ-274, D-170: packages ko-1097-zone-1 and -2, keys 1 and
2, cooked by `ko_bake.py KEY --client=1097`) are walked the same way; the suite
also checks that their provenance names the 1097 layout, the headerless zone
files and the pinned 1097 installer, and that no referenced file was missing.

A new character enters at the package start, which is the zone's own nation's
START_POSITION point inside its one-sided area [X, X + bRangeX] x [Z, Z + bRangeZ]
(Ebenezer 004c6523, 00422261; PQ-217). It then walks, through the server, to
the point the bake surveyed for it (start.walk in provenance.json: the engine
solver reached it from the start on the cooked map) and back, ending where the
solver ended. Before it a direction 1000 times too long is sent: the server
refuses it and the character stays put. The first second of the walk asks for
turbo from a character without the movement.turbo role: the server holds it to
the package's run speed.
"""
import json
import math
import os
import secrets
import select
import subprocess
import sys
import time
import uuid
from pathlib import Path

from world_peer import Peer, first, integer, real

ROOT = Path(__file__).resolve().parents[1]
ZONES = {"karus": "ko-zone-10", "elmorad": "ko-zone-20", "karus-1097": "ko-1097-zone-1",
         "elmorad-1097": "ko-1097-zone-2"}
# package -> (Zones.tbl key, nation: tools/assetc/ko_start.py PACKAGE_NATION, Zones.tbl layout)
PACKAGES = {"ko-zone-10": (10, "karus", "1298"), "ko-zone-20": (20, "elmorad", "1298"),
            "ko-1097-zone-1": (1, "karus", "1097"), "ko-1097-zone-2": (2, "elmorad", "1097")}
INSTALLER_1097 = "d7571e183663be3d063af491d68d7db3dc52219f58471c9595d0b745c0b8a93b"
TICK = 0.05

if len(sys.argv) > 1:
    name = ZONES[sys.argv[1]]
    state_path = ROOT / ("build/%s-demo/session.json" % name)
    project = "n3e-%s" % name
else:
    state_path = Path(os.environ["N3E_MORADON_STATE"])
    project = os.environ["N3E_MORADON_PROJECT"]
state = json.loads(state_path.read_text())
key = state["zone"]
# Stacks started before PQ-274 name no package: theirs is ko-zone-KEY.
name = state.get("package", "ko-zone-%d" % key)
assert PACKAGES[name][0] == key, (name, key)
work = ROOT / os.environ.get("N3E_KO_WORK", "build")
package = work / "packages" / name
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
report = json.loads((work / name / "provenance.json").read_text())
assert (package / "release.sha256").read_text().strip() == state["release"], "the stack serves another cook"
start = report["start"]
nation = start["nation"]
assert nation == PACKAGES[name][1], (name, nation)
layout = PACKAGES[name][2]
assert report["zone"].get("layout", "1298") == layout, (name, report["zone"].get("layout"))
if layout == "1097":
    # The 1097 map (D-170): the 1097 table's own files, read headerless, from the
    # pinned installer's unpack, with nothing it names missing.
    install = report["zone"]["install"]
    assert install["installer_sha256"] == INSTALLER_1097, install
    assert report["terrain"]["format"].startswith("N3 GTD headerless"), report["terrain"]["format"]
    assert report["objects"]["format"].startswith("N3 OPD headerless"), report["objects"]["format"]
    assert report["references"]["missing"] == [], report["references"]
    print("PASS key %d (%s) is the 1097 map: %s and %s read headerless from the pinned 1097 installer's "
          "files (%d checked against its manifest); %d GTT, %d meshes and %d textures referenced, none missing"
          % (key, nation, Path(report["zone"]["files"]["gtd"]).name, Path(report["zone"]["files"]["opd"]).name,
             len(install["files"]), report["references"]["gtt"], report["references"]["meshes"],
             report["references"]["textures"]), flush=True)

# The start the bake chose: inside the nation's one-sided START_POSITION area.
row, extent = start["row"], start["extent_metres"]
spawn = start["areas"][nation]["spawn"]
columns = {"karus": ("sKarusX", "sKarusZ"), "elmorad": ("sElmoradX", "sElmoradZ")}[nation]
kx, kz = spawn[0] + extent / 2, extent / 2 - spawn[2]
assert row[columns[0]] <= kx <= row[columns[0]] + row["bRangeX"], (kx, row)
assert row[columns[1]] <= kz <= row[columns[1]] + row["bRangeZ"], (kz, row)
assert [manifest["gameplay"]["spawn_x"], manifest["gameplay"]["spawn_z"]] == [spawn[0], spawn[2]]
walk = start["walk"]
target, engine_end = walk["target"], walk["engine_end"]
movement = manifest["gameplay"]["movement"]
run_speed = movement["run_speed"]

compose = ["docker", "compose", "-p", project]
env = {**os.environ, "N3E_REALM": state["realm"], "N3E_PORT": str(state["port"]),
       "N3E_PACKAGE_PATH": str(package.resolve())}
account, password = "walker" + secrets.token_hex(4), secrets.token_urlsafe(24)
subprocess.run([*compose, "exec", "-T", "server", "n3e-server", "account-create", account], input=password + "\n",
               env=env, text=True, check=True, capture_output=True)
p = Peer(state["port"], account, password, content=state["release"], game=manifest["game_id"],
         protocol=manifest["protocol_version"])
p.select(p.create("Walker" + uuid.uuid4().hex[:6]))
last_ping = 0.0


def frame():
    """The next world view, every view already received taken first."""
    global last_ping
    while True:
        if time.monotonic() - last_ping > 0.5:
            p.send(14)
            last_ping = time.monotonic()
        tag, data = p.receive()
        assert tag != 4, data
        if tag == 10 and not (p.s.pending() or select.select([p.s], [], [], 0)[0]):
            return p.entities[p.id]


def where(me):
    return first(me, 3), first(me, 4), first(me, 5)


def turbo_move(dx, dz):
    # A run move with field 6 (turbo) set, from a character without the movement.turbo role.
    p.seq += 1
    p.send(9, integer(1, p.session) + integer(2, p.seq) + real(3, dx) + real(4, dz) + integer(5, 1)
           + integer(6, 1) + (integer(7, p.id) if p.protocol >= 7 else b""))


def overlong_move(dx, dz):
    """A direction 1000 times too long is refused (Error 3) and moves nothing."""
    before = where(frame())
    p.move(dx * 1000, dz * 1000, mode=1)
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        tag, data = p.receive()
        if tag == 4:
            assert first(data, 1) == 3, data
            p.seq -= 1  # refused: the next move may reuse its sequence number
            break
    else:
        raise AssertionError("an over-long move was not refused")
    after = where(frame())
    assert math.dist(before, after) < 1e-4, (before, after)


def walk_to(x, z, tolerance=0.5, turbo=0.0):
    """Steer toward (x, z) one acknowledged move per tick; returns the stop point
    and, when the first `turbo` seconds asked for turbo, the largest speed between
    two consecutive views seen then."""
    here = where(frame())
    deadline = time.monotonic() + 30 + math.hypot(x - here[0], z - here[2]) / 1.5
    turbo_until = time.monotonic() + turbo
    last_view, fastest = None, 0.0
    while time.monotonic() < deadline:
        me = frame()
        if time.monotonic() < turbo_until:
            # Every view while turbo is asked for: no turbo flag, and between two
            # views no faster than the run speed.
            assert not first(me, 19), "turbo granted without the movement.turbo role"
            position = where(me)
            if last_view is not None and p.tick > last_view[0]:
                moved = math.hypot(position[0] - last_view[1][0], position[2] - last_view[1][2])
                fastest = max(fastest, moved / ((p.tick - last_view[0]) * TICK))
            last_view = (p.tick, position)
        if first(me, 6) < p.seq:  # one movement per tick: wait for the last one's ack
            continue
        position = where(me)
        dx, dz = x - position[0], z - position[2]
        d = math.hypot(dx, dz)
        if time.monotonic() < turbo_until:
            turbo_move(dx / max(d, 1e-3), dz / max(d, 1e-3))
            continue
        if d < tolerance:
            p.move(0, 0)
            for _ in range(4):
                me = frame()
            return where(me), fastest
        p.move(dx / max(1, d), dz / max(1, d), mode=1)
    raise AssertionError(("route blocked", (x, z), where(p.entities[p.id])))


try:
    me = frame()
    x, y, z = where(me)
    assert abs(x - spawn[0]) < 0.01 and abs(z - spawn[2]) < 0.01, ((x, y, z), spawn)
    # The survey stands the start 0.1 m above the ground the server keeps it on.
    assert abs(y - (spawn[1] - 0.1)) < 0.05, ((x, y, z), spawn)
    assert not first(me, 19), "a new character must not move in turbo"
    print("PASS key %d (%s) start: a new character enters at KO %.0f,%.0f, inside %s's START_POSITION area "
          "[%d, %d] x [%d, %d], on the ground (y %.2f)"
          % (key, nation, kx, kz, nation, row[columns[0]], row[columns[0]] + row["bRangeX"], row[columns[1]],
             row[columns[1]] + row["bRangeZ"], y), flush=True)
    d = math.hypot(target[0] - x, target[2] - z)
    overlong_move((target[0] - x) / d, (target[2] - z) / d)
    t0 = time.monotonic()
    (ex, ey, ez), fastest = walk_to(target[0], target[2], turbo=1.0)
    assert 0 < fastest <= run_speed * 1.05, (fastest, run_speed)
    # Both stop within 0.5 m of the target (walk_to here, ko_survey.route in the bake).
    assert math.hypot(ex - target[0], ez - target[2]) < 0.5, ((ex, ey, ez), target)
    assert math.hypot(ex - engine_end[0], ez - engine_end[2]) < 1.0, ((ex, ey, ez), engine_end)
    assert abs(ey - engine_end[1]) < 0.3, ((ex, ey, ez), engine_end)
    out = time.monotonic() - t0
    (bx, by, bz), _ = walk_to(spawn[0], spawn[2])
    assert math.hypot(bx - spawn[0], bz - spawn[2]) < 0.5 and abs(by - (spawn[1] - 0.1)) < 0.3, (bx, by, bz)
    print("PASS key %d (%s) walk: the server walked the character %.1f m from the start to the surveyed point "
          "(%.1f, %.1f) in %.1f s, ending %.2f m from the engine solver's end at height %.2f (solver %.2f), and "
          "back; an over-long move was refused, and turbo moves without the role went at most %.2f m/s between "
          "views, never flagged turbo (run speed %.1f)"
          % (key, nation, walk["distance"], target[0], target[2], out,
             math.hypot(ex - engine_end[0], ez - engine_end[2]), ey, engine_end[1], fastest, run_speed),
          flush=True)
    p.logout()
finally:
    p.s.close()
