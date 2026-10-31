"""Opt-in (make live-ko): a static KO shape whose cycling part does not
billboard, drawn offscreen with its texture sequence on the 1097 Moradon
package cooked from the player's own KO data (PQ-412, D-213).

1298's shape manager load keeps a shape without an event id visible
(`00443ae0` stores `+0x151` = 1 at `00443b41`; `005b4690` touches it only for
an event id, `005b4a2f`-`005b4a73`), and its tick and render take every part
(`00443f40` at `00444226`, `004442e0`); the part tick cycles a multi-texture
part whatever its flags (`004429b0`, D-212) and only RF_BOARD_Y (`00442cc6`)
or RF_WOBBLE then move it. n3e's bake left every static shape with a cycling
part out (`animated_material`); it now places the ones whose cycling parts do
neither (`material_cycle`). The 1097 Moradon has one: the dungeon gate
(`obj_dun_dungate`, OPD shape 2308) with four opaque parts and a fire part,
14 textures at 7 fps, alpha (SRCALPHA / INVSRCALPHA) and double-sided (0x5)
(local-asset; the 1097 exe is packed, so applying 1298's rule is inference).

The camera stands in front of the fire part, on the side of its normal that
faces the map centre, aimed at the part's centre. Each client run gives the
frame-40 capture (the whole frame, alpha parts too) and the world pass's own
capture (N3E_TEST_WORLD_OVERLAY, opaque parts only). The same camera is drawn
on a second cook of key 21 (`--client=1097 --features`, as the `moradon-1097`
prepare step cooks it) with `material_cycle` left out of `ko_shapes.BAKED`
(the bake before PQ-412), which this script cooks into its own folder:

* provenance: the package places the one gate (`material_shapes` 1) with its
  five parts, one of them an alpha part that cycles (PQ-394, D-212), where the
  left-out cook places none and has the same collision;
* within the central box (an eighth in from each edge, clear of the FPS
  label), the world-pass frames differ from the left-out one in at least 2,000
  pixels (the gate's opaque parts), centred within 120 px of the image centre;
* negative control: a second capture of the left-out cook is the same frame
  (world pass byte for byte, whole frame within the box);
* the captures above fix the sequences' frame time at 0 (frame 0 throughout).
  Drawn again at a fixed frame time of 0.05 s (0.0625 or 0.075 s if the
  capture comes round to frame 0), the fire part's sequence log (the zone's
  only 14-frame, 7-fps sequence, centred on the part) replays index + seconds x fps, 0 at the count, on every frame
  with 14 frames at 7 fps, and the whole frame differs from the frame-0 one in
  at least 100 box pixels centred within 120 px of the centre, where the world
  pass is the same (the fire's own pixels).

No server or stack.
"""
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import world_sequence_log  # noqa: E402

if sys.argv[1:2] == ["--cook-left-out"]:
    # The negative-control cook: key 21 as the moradon-1097 prepare step cooks
    # it, with the material_cycle class left out of the bake as before PQ-412.
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import ko_shapes
    ko_shapes.BAKED = ko_shapes.BAKED - {"material_cycle"}
    sys.argv = ["tools/assetc/ko_bake.py", "21", "--client=1097", "--features", "--into=" + sys.argv[2]]
    runpy.run_path("tools/assetc/ko_bake.py", run_name="__main__")
    sys.exit(0)

WORK = Path(os.environ.get("N3E_KO_WORK", "build/live-ko/work"))
B = Path("build/live-ko/material-shapes")
B.mkdir(parents=True, exist_ok=True)
LEFT_OUT = WORK / "material-shapes-left-out"
NAME, FRAMES, FPS = "obj_dun_dungate", 14, 7.0

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED the 1097 Moradon's dungeon gate fire needs N3E_GRAPHICAL=1 (make live-ko)")
    sys.exit(0)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(path):
    data = path.read_bytes()
    magic, size, _, body = data.split(b"\n", 3)
    width, height = map(int, size.split())
    assert magic == b"P6" and len(body) == width * height * 3, path
    return width, height, [body[i:i + 3] for i in range(0, len(body), 3)]


def ground(package, x, z):
    queries = B / "probe.txt"
    queries.write_text("%r %r 0 0 0 1\n" % (x, z))
    out = subprocess.run(["build/client/n3e-collision-check", "probe", str(package / "collision.bin"), str(queries)],
                         capture_output=True, text=True, check=True).stdout.splitlines()[1]
    return float(out.split()[0])


def draw(package, name, view, seconds="0", log=None):
    """The frame-40 capture and the world pass's capture with the maps.
    `seconds` fixes the sequences' frame time (0: frame 0 throughout); with
    `log` (a list) the client's sequence log is appended to it."""
    capture = B / (name + ".ppm")
    run = subprocess.run(["build/client/n3e-test-client", str(package), "--smoke", "--capture", str(capture)],
                         capture_output=True, text=True, timeout=600,
                         env={**os.environ, "N3E_TEST_WORLD_OVERLAY": "1", "N3E_TEST_WORLD_VIEW": view,
                              "N3E_TEST_SEQUENCE_SECONDS": seconds,
                              **({"N3E_TEST_SEQUENCE_LOG": "1"} if log is not None else {})})
    if log is not None:
        log.append(run.stdout)
    (B / (name + "-client.log")).write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "PASS world overlay matched-camera captures" in run.stdout, \
        (name, run.stdout[-2000:], run.stderr[-2000:])
    # PQ-387's world-pass pair waits for the stream; the frame-40 capture is
    # whole only once every chunk in reach is resident by then.
    assert re.search(r"WORLD_STREAM frame=3\d .* settled=1", run.stdout), (name, run.stdout[-2000:])
    return capture, Path(str(capture) + ".overlay.ppm")


def inside(i, width, height):
    """The central box: an eighth in from each edge, clear of the FPS label."""
    x, y = i % width, i // width
    return width // 8 <= x < width - width // 8 and height // 8 <= y < height - height // 8


def centroid(at, width, height):
    if not at:
        return None
    return (sum(i % width for i in at) / len(at) - width / 2, sum(i // width for i in at) / len(at) - height / 2)


def changed(a, b, worlds=None):
    """Within the central box, the pixels where `a` and `b` differ (and, with
    `worlds`, where that pair of world-pass frames does not): count, centroid."""
    width, height, p = pixels(a)
    _, _, q = pixels(b)
    r = s = None
    if worlds:
        r, s = (pixels(w)[2] for w in worlds)
    at = [i for i in range(width * height)
          if p[i] != q[i] and inside(i, width, height) and (r is None or r[i] == s[i])]
    return len(at), centroid(at, width, height)


package = WORK / "packages" / "moradon-1097"
report = json.loads((WORK / "ko-moradon-1097" / "provenance.json").read_text())
cook = subprocess.run([sys.executable, __file__, "--cook-left-out", str(LEFT_OUT)],
                      capture_output=True, text=True, timeout=1800)
(B / "left-out-cook.log").write_text(cook.stdout + cook.stderr)
assert cook.returncode == 0, cook.stderr[-2000:]
left_package = LEFT_OUT / "packages" / "moradon-1097"
left_report = json.loads((LEFT_OUT / "ko-moradon-1097" / "provenance.json").read_text())
drawn, left = report["visuals"]["objects"], left_report["visuals"]["objects"]
assert (drawn["material_shapes"], left["material_shapes"], drawn["first_frame_parts"], left["first_frame_parts"]) \
    == (1, 0, 0, 0), (drawn, left)
assert (drawn["placements"] - left["placements"], drawn["sequence_parts"] - left["sequence_parts"],
        drawn["alpha_parts"] - left["alpha_parts"]) == (5, 1, 1), (drawn, left)
assert drawn["skipped_parts"] == left["skipped_parts"], (drawn, left)
assert digest(package / "collision.bin") == digest(left_package / "collision.bin")
assert digest(package / "release.sha256") != digest(left_package / "release.sha256")

# The gate and its fire part, from the player's OPD and mesh as the bake read them.
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko  # noqa: E402
import ko_scene  # noqa: E402
import ko_shapes  # noqa: E402
opd = report["objects"]["source"]
(gate,) = [s for s in ko_shapes.load_shapes(opd, headerless=True)["shapes"]
           if ko_shapes.classify(s) == "material_cycle"]
assert gate["name"] == NAME and len(gate["parts"]) == 5, gate["name"]
(fire,) = ko_shapes.cycling_parts(gate)
assert (fire["render_flags"], fire["source_blend"], fire["destination_blend"], len(fire["textures"]),
        fire["texture_fps"]) == (0x5, 5, 6, FRAMES, FPS), fire
objects = ko_scene.object_files(Path(opd).parents[1])
mesh = ko.import_mesh(objects[ko_scene._basename(fire["mesh"])], 1.0)
half = report["extent_metres"] / 2
qx, qy, qz, qw = gate["rotation"]
q, (sx, sy, sz), (px, py, pz) = [-qx, -qy, qz, qw], gate["scale"], gate["position"]
origin = [px - half, py, half - pz]
ax, ay, az = fire["pivot"]
points = [[o + w for o, w in zip(origin, ko_scene._rotate(q, [(v[0] + ax) * sx, (v[1] + ay) * sy, (v[2] - az) * sz]))]
          for v in mesh["vertices"]]
assert len(points) == 4 and len(mesh["indices"]) == 6, (len(points), len(mesh["indices"]))
centre = [sum(p[k] for p in points) / 4 for k in range(3)]
a, b, c = (points[i] for i in mesh["indices"][:3])
u, v = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
length = sum(x * x for x in n) ** 0.5
n = [x / length for x in n]
# The part is double-sided: stand on the side that faces the map centre.
if n[0] * -centre[0] + n[2] * -centre[2] < 0:
    n = [-x for x in n]
ex, ez = centre[0] + n[0] * 9.0, centre[2] + n[2] * 9.0
ey = max(centre[1], ground(package, ex, ez) + 1.8)
view = "%r %r %r %r %r %r" % (ex, ey, ez, *centre)

whole, world = draw(package, "drawn", view)
left_whole, left_world = draw(left_package, "left-out", view)
world_count, world_offset = changed(left_world, world)
assert world_count >= 2000 and max(map(abs, world_offset)) <= 120, (world_count, world_offset)
whole_count, _ = changed(left_whole, whole)
# Negative control: without the gate the same capture is the same frame.
again_whole, again_world = draw(left_package, "left-out-again", view)
assert digest(again_world) == digest(left_world) and changed(left_whole, again_whole) == (0, None)

# The fire cycles. Its log (the zone's one 14-frame, 7-fps sequence, its record
# centre within 1 m of the quad's) replays on every
# frame; once the capture shows a frame other than 0, the whole frame differs
# from the frame-0 capture where the world pass does not.
for seconds in ("0.05", "0.0625", "0.075"):
    log = []
    c_whole, c_world = draw(package, "cycle-" + seconds, view, seconds, log)
    mine = [r for r in world_sequence_log.rows(log[0]).values()
            if (int(r[0]["frames"]), float(r[0]["fps"])) == (FRAMES, FPS)]
    assert len(mine) == 1, (seconds, len(mine))
    assert max(abs(x - y) for x, y in zip(mine[0][0]["center"], centre)) < 1.0, (mine[0][0], centre)
    shown = world_sequence_log.replay(mine[0])
    assert 40 in shown, sorted(shown)[-3:]
    if shown[40]:
        break
else:
    raise AssertionError("the fire came round to frame 0 at every capture")
assert digest(c_world) == digest(world)  # the world pass holds no alpha part
cycled, cycled_offset = changed(whole, c_whole, (world, c_world))
assert cycled >= 100 and max(map(abs, cycled_offset)) <= 120, (seconds, cycled, cycled_offset)
print("PASS KO animated-material shapes graphical (PQ-412, D-213): moradon-1097 places %s (%d parts, 1 cycling "
      "fire part) where the left-out cook places none; 9 m in front of the fire the world pass differs from the "
      "left-out frame in %d box pixels, centroid %+.1f, %+.1f px (whole frame %d); the left-out cook's second "
      "capture is the same frame; the fire (%d frames at %g fps, 0x5, 5/6) replays its sequence log on every frame "
      "at %s s, shows frame %d at the capture (%d frames over the run) and the whole frame differs from frame 0's "
      "in %d box pixels, centroid %+.1f, %+.1f px, where the world pass is the same"
      % (NAME, drawn["placements"] - left["placements"], world_count, *world_offset, whole_count, FRAMES, FPS,
         seconds, shown[40], len(set(shown.values())), cycled, *cycled_offset))
