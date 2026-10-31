"""Opt-in: a Moradon layout on its play stack (PQ-223, D-171; PQ-224, D-172).

  python tests/ko_stack.py moradon-classic tests/moradon_layout_live.py   (make live-ko)
  python tests/ko_stack.py moradon-1097 tests/moradon_layout_live.py      (make live-ko)
  python tests/moradon_layout_live.py classic    the persistent stack of
                                                 tools/play-moradon --layout classic
  python tests/moradon_layout_live.py 1097       ... of tools/play-moradon --layout 1097

Under `make live-ko` tests/ko_stack.py gives this suite a disposable stack of its
own on the package the run cooked (`ko_bake.py 210 --layout=classic --features`
or `ko_bake.py 21 --client=1097 --features`, `--into=build/live-ko/work`) and
names it through N3E_MORADON_STATE / N3E_MORADON_PROJECT. With a layout name it
probes the persistent stack (build/moradon-LAYOUT-demo/session.json, project
n3e-moradon-LAYOUT) with an account of its own; the player's account and
characters are not touched.

It checks that the stack serves the layout's map: the provenance names the
layout and no missing file; for classic, the install's own Zones/moradon.*
with the pinned installer's hashes; for 1097, the 1097 table's key 21 files
(Zones/moradon.*), headerless, checked against the pinned 1097 installer's
manifest, with the 2004 client's player and HUD. A new character enters at the package start, inside the
START_POSITION zone 21 area (games/moradon/ko-reference.json) as the Moradon
feature cook reads it (X +- bRange; PQ-240 tracks Ebenezer's one-sided area),
on the ground.
It then walks, through the server, each demo route the bake proved with the
engine solver on the classic collision to its worm area, where the worms it
sees stand idle at integer points inside the KO spawn rectangles with the
reference HP, and back to the start.
"""
import json
import math
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

from world_peer import Peer, first
from moradon_route import walker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko_bake  # noqa: E402  (the layouts and their pinned file hashes)

LAYOUTS = [*ko_bake.MORADON_LAYOUTS, "1097"]
if len(sys.argv) > 1:
    layout = sys.argv[1]
    assert layout in LAYOUTS, layout
    state_path = ROOT / ("build/moradon-%s-demo/session.json" % layout)
    project = "n3e-moradon-%s" % layout
else:
    state_path = Path(os.environ["N3E_MORADON_STATE"])
    project = os.environ["N3E_MORADON_PROJECT"]
state = json.loads(state_path.read_text())
name = state["package"]
layout = name[len("moradon-"):]
assert layout in LAYOUTS, layout
work = ROOT / os.environ.get("N3E_KO_WORK", "build")
package = work / "packages" / name
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
report = json.loads((work / ("ko-" + name) / "provenance.json").read_text())
assert (package / "release.sha256").read_text().strip() == state["release"], "the stack serves another cook"
zone, features = report["zone"], report["features"]
assert features["layout"] == layout, features.get("layout")
assert report["references"]["missing"] == [], report["references"]
counts = (report["references"]["gtt"], report["references"]["meshes"], report["references"]["textures"])
if layout == "1097":
    # PQ-224: the 1097 table's key 21, its files as the pinned installer shipped them.
    assert state["zone"] in (21, "21"), state
    install = zone["install"]
    assert zone["layout"] == "1097" and install["installer_sha256"] == ko_bake.INSTALLER_1097_SHA256, zone
    assert sorted(Path(f).name.lower() for f in zone["files"].values()) == [
        "moradon.dxt", "moradon.gtd", "moradon.opd", "moradon.tct"], zone["files"]
    # PQ-387: the light maps (the table's fourth column) are checked too.
    assert sorted(install["files"]) == ["Data/Zones.tbl", "Zones/moradon.dxt", "Zones/moradon.gtd",
                                        "Zones/moradon.opd", "Zones/moradon.tct", "Zones/moradon.tlt"], install["files"]
    assert zone["client_row"]["key"] == 210 and report["party_names"]["zone_key"] == 210, zone["client_row"]
    assert Path(report["character_assets"]).resolve() == ko_bake.CLIENT.resolve(), report["character_assets"]
    print("PASS 1097 Moradon package: the 1097 table's key 21 (%s), each file the pinned 1097 "
          "installer's (manifest); %d GTT, %d meshes and %d textures referenced, none missing; player, HUD "
          "and name rules from the 2004 client (its key 210 row)"
          % (", ".join(sorted(Path(f).name for f in zone["files"].values())), *counts), flush=True)
else:
    assert state["zone"] in (210, "210"), state
    stem, hashes = ko_bake.MORADON_LAYOUTS[layout]
    variant = zone["variant"]
    assert variant["layout"] == layout and variant["stem"] == stem and variant["sha256"] == hashes, variant
    assert sorted(Path(f).name.lower() for f in zone["files"].values()) == sorted(
        "%s.%s" % (stem.lower(), e) for e in ("dxt", "gtd", "opd", "tct")), zone["files"]
    print("PASS %s Moradon package: key 210's row renamed from %s to %s (%d columns), the install's own %s "
          "with the pinned installer's hashes; %d GTT, %d meshes and %d textures referenced, none missing"
          % (layout, variant["table_stem"], stem, len(variant["rewritten_columns"]),
             ", ".join(sorted(Path(f).name for f in zone["files"].values())), *counts), flush=True)

reference = json.loads((ROOT / "games/moradon/ko-reference.json").read_text())
start = reference["start_position"]
spawn = features["spawn"]
gameplay = manifest["gameplay"]
assert [gameplay["spawn_x"], gameplay["spawn_z"]] == [spawn[0], spawn[2]], (gameplay["spawn_x"], spawn)

compose = ["docker", "compose", "-p", project]
env = {**os.environ, "N3E_REALM": state["realm"], "N3E_PORT": str(state["port"]),
       "N3E_PACKAGE_PATH": str(package.resolve())}
account, password = "layout" + secrets.token_hex(4), secrets.token_urlsafe(24)
subprocess.run([*compose, "exec", "-T", "server", "n3e-server", "account-create", account], input=password + "\n",
               env=env, text=True, check=True, capture_output=True)
p = Peer(state["port"], account, password, content=state["release"], game=manifest["game_id"],
         protocol=manifest["protocol_version"])
p.select(p.create("Layout" + uuid.uuid4().hex[:6]))
p.pump(.5)
walk = walker(p, first, .5)


def me():
    return p.entities[p.id]


def worms():
    return [e for e in p.entities.values() if first(e, 9) and first(e, 7) and first(e, 2) == gameplay["npc"].encode()]


def inside(e, area):
    return area[0] <= first(e, 3) <= area[2] and area[1] <= first(e, 5) <= area[3]


try:
    x, y, z = first(me(), 3), first(me(), 4), first(me(), 5)
    kx, kz = x + 256, 256 - z  # the centred 512 m Moradon bake (moradon_features.HALF)
    assert (x, z) == (spawn[0], spawn[2]), ((x, y, z), spawn)
    assert start["sKarusX"] - start["bRangeX"] <= kx <= start["sKarusX"] + start["bRangeX"], (kx, start)
    assert start["sKarusZ"] - start["bRangeZ"] <= kz <= start["sKarusZ"] + start["bRangeZ"], (kz, start)
    # The survey stands the start 0.1 m above the ground the server keeps it on.
    assert abs(y - (spawn[1] - 0.1)) < 0.05, ((x, y, z), spawn)
    # The Moradon feature cook's area is X +- bRange (moradon_features.start_area;
    # Ebenezer's one-sided [X, X + bRange], 004c6523, is PQ-240's open gap).
    one_sided = (start["sKarusX"] <= kx <= start["sKarusX"] + start["bRangeX"]
                 and start["sKarusZ"] <= kz <= start["sKarusZ"] + start["bRangeZ"])
    print("PASS %s start: a new character enters at KO %.0f,%.0f, inside the feature cook's START_POSITION "
          "zone %d area %d+-%d, %d+-%d (%s the one-sided area of PQ-240), on the ground (y %.2f)"
          % (layout, kx, kz, start["ZoneID"], start["sKarusX"], start["bRangeX"], start["sKarusZ"],
             start["bRangeZ"], "also inside" if one_sided else "outside", y), flush=True)
    areas = [w["area"] for w in features["worm"]]
    for index, worm in enumerate(features["worm"]):
        t0 = time.monotonic()
        for wx, wz in worm["route"]:
            walk(wx, wz)
        p.pump(1)
        seen = worms()
        here = [e for e in seen if inside(e, worm["area"])]
        assert here, ("no worm in view inside area", index, worm["area"], seen)
        for e in seen:
            # Idle worms stand at their spawn home: an integer point in a KO area.
            assert any(inside(e, a) for a in areas), e
        for e in here:
            assert first(e, 12) == b"idle" and first(e, 3) == int(first(e, 3)) and first(e, 5) == int(first(e, 5)), e
            assert first(e, 7) == gameplay["npc_health"], e
        out = time.monotonic() - t0
        for wx, wz in reversed(worm["route"][:-1]):
            walk(wx, wz)
        walk(spawn[0], spawn[2])
        bx, bz = first(me(), 3), first(me(), 5)
        assert math.hypot(bx - spawn[0], bz - spawn[2]) < 0.5, (bx, bz, spawn)
        print("PASS %s worm area %d %s: the server walked the route %s in %.1f s; %d worms idle at integer "
              "points inside it with %d HP (%d in view, all inside the KO spawn rectangles); and back to the start"
              % (layout, index, worm["area"], worm["route"], out, len(here), gameplay["npc_health"], len(seen)),
              flush=True)
    p.logout()
finally:
    p.s.close()
