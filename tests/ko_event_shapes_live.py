"""Opt-in (make live-ko): the bind points and warp gates 1298 shows at load,
drawn offscreen on the Karus homeland cooked from the player's own KO data
(PQ-392, D-205).

1298's shape manager keeps a shape with an event id visible from load only for
event types 0 and 5 (`005b4690`, `005b4a5b`-`005b4a73`), and its tick and render
draw it as any shape; n3e's bake placed only static shapes, so the light maps'
round shadows beside the homeland starts had no caster (PQ-391).

Two frames are read from each client run (PQ-398): the world pass's own pair
(N3E_TEST_WORLD_OVERLAY, without and with the light maps), which the client
takes before the world's alpha parts draw, and the frame-40 capture, the whole
frame, alpha parts too. Each shape's magic part is an alpha part (ONE/ONE,
PQ-392), so only the whole frame can show it. Every camera is drawn on a
second cook of key 10 with the event shapes left out of the bake
(`ko_shapes.BAKED` = {"static"}, the bake before PQ-392), which this script
cooks into its own folder:

* provenance: `ko-zone-10` places the zone's 11 event shapes (4 bind points, 7
  warp gates) with 11 magic parts that cycle their textures (PQ-394, D-212),
  none left on its first frame, all of them alpha parts, 49
  parts more than the left-out cook, which places none and has the same
  collision;
* PQ-391's camera, 30 m above and 6 m south of the `karus2004` warp gate
  nearest the Karus start (OPD shape 126, `obj_ka_transmark00`, event 4006,
  type 5), aimed at its origin: the world-pass frames with the maps differ in
  at least 2,000 pixels, whose centroid lies within 40 px of the image centre,
  where the gate's origin projects;
* a camera 7 m in front of that gate's magic part, and one 7 m in front of the
  bind point's beside it (shape 127, `obj_ka_bindPoint`, event 101, type 0),
  each aimed at the part's centre: within the central box of the frame (an
  eighth in from each edge, which leaves out the FPS label) at least 1,000
  pixels of the whole frame differ from the left-out one where the world-pass
  frames do not (the magic part's own pixels), every one of them at least as
  bright in each channel (an additive glow), centred within 80 px of the image
  centre;
* negative control: a second capture of the left-out cook at each camera is
  the same frame (world pass byte for byte, whole frame within the box), so
  the checks above fail without the shapes;
* PQ-394: the captures above fix the sequences' frame time at 0, so every
  magic part stays on frame 0 and they repeat. At each front camera the part
  is then drawn cycling, at a fixed frame time of 0.05 s (0.0625 or 0.075 s if
  the capture comes round to frame 0): the client's sequence log for that part
  (found by its record centre) replays index + seconds x fps, 0 at the count,
  on every frame, and the whole frame differs from the frame-0 capture in at
  least 100 box pixels, near the centre, where the world pass is the same.

It also reports how many pixels within 160 px of the centre the maps darken by
more than 30 (PQ-391's spot measure) in each cook, and the whole frame's own
changes at PQ-391's camera, which the alpha parts take no part in: the magic
parts are one-sided upright quads drawn as authored (their RF_BOARD_Y turn
toward the eye is frozen, PQ-392), and from above the gate's faces away (PQ-398
saw no alpha-only pixel there). A pixel can change in the whole frame but not
in the world pass only through what draws after the world pass, and the event
shapes add no other alpha part, so the front checks read the magic parts
alone. No server or stack.
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
    # The negative-control cook: key 10 as tools/play-ko-zone cooks it, with the
    # event shapes left out of the bake as before PQ-392.
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import ko_shapes
    ko_shapes.BAKED = frozenset({"static"})
    sys.argv = ["tools/assetc/ko_bake.py", "10", "--into=" + sys.argv[2]]
    runpy.run_path("tools/assetc/ko_bake.py", run_name="__main__")
    sys.exit(0)

WORK = Path(os.environ.get("N3E_KO_WORK", "build/live-ko/work"))
B = Path("build/live-ko/event-shapes")
B.mkdir(parents=True, exist_ok=True)
LEFT_OUT = WORK / "event-shapes-left-out"
# karus2004's warp gate nearest the Karus start (PQ-391's table), and the bind
# point beside it.
SHAPE, NAME, EVENT = 126, "obj_ka_transmark00", (4006, 5)
BIND = 127, "obj_ka_bindPoint", (101, 0)
# Their magic parts' sequences (local-asset, PQ-392's parts.py): 16 textures at
# 10 fps each.
FRAMES, FPS = {"gate": 16, "bind": 16}, {"gate": 10.0, "bind": 10.0}

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED bind points and warp gates need N3E_GRAPHICAL=1 (make live-ko)")
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
    """The frame-40 capture (the whole frame) and the world pass's pair without
    and with the maps (no alpha part: the effect pass draws those later).

    PQ-394 (D-212): the magic parts cycle their textures. `seconds` fixes the
    sequences' frame time; at the default 0 every part stays on frame 0, the
    frame PQ-392 and PQ-398 measured, so the captures repeat. With `log` (a
    list) the client's sequence log is appended to it."""
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
    return [capture] + [Path(str(capture) + s) for s in (".no-overlay.ppm", ".overlay.ppm")]


def inside(i, width, height):
    """The central box: an eighth in from each edge, clear of the FPS label."""
    x, y = i % width, i // width
    return width // 8 <= x < width - width // 8 and height // 8 <= y < height - height // 8


def centroid(at, width, height):
    if not at:
        return None
    return (sum(i % width for i in at) / len(at) - width / 2, sum(i // width for i in at) / len(at) - height / 2)


def changed(a, b, box=False):
    """The changed pixels' count and centroid offset from the image centre,
    within the central box when `box`."""
    width, height, p = pixels(a)
    _, _, q = pixels(b)
    at = [i for i, (u, v) in enumerate(zip(p, q)) if u != v and (not box or inside(i, width, height))]
    return len(at), centroid(at, width, height)


def alpha_only(left_whole, whole, left_world, world):
    """Within the central box, the pixels where the whole frames differ and the
    world-pass frames (with the maps) do not: what the alpha parts add. Returns
    their count, centroid, and how many are darker in some channel."""
    width, height, p = pixels(left_whole)
    _, _, q = pixels(whole)
    _, _, r = pixels(left_world)
    _, _, s = pixels(world)
    at = [i for i in range(width * height) if p[i] != q[i] and r[i] == s[i] and inside(i, width, height)]
    darker = sum(1 for i in at if any(v < u for u, v in zip(p[i], q[i])))
    return len(at), centroid(at, width, height), darker


def darkened(plain, lit, radius=160):
    """PQ-391's spot measure: pixels within `radius` of the centre that the maps
    darken by more than 30 in their RGB sum."""
    width, height, p = pixels(plain)
    _, _, q = pixels(lit)
    return sum(1 for i, (u, v) in enumerate(zip(p, q))
               if (i % width - width / 2) ** 2 + (i // width - height / 2) ** 2 <= radius * radius
               and sum(u) - sum(v) > 30)


package = WORK / "packages" / "ko-zone-10"
report = json.loads((WORK / "ko-zone-10" / "provenance.json").read_text())
cook = subprocess.run([sys.executable, __file__, "--cook-left-out", str(LEFT_OUT)],
                      capture_output=True, text=True, timeout=1800)
(B / "left-out-cook.log").write_text(cook.stdout + cook.stderr)
assert cook.returncode == 0, cook.stderr[-2000:]
left_package = LEFT_OUT / "packages" / "ko-zone-10"
left_report = json.loads((LEFT_OUT / "ko-zone-10" / "provenance.json").read_text())
drawn, left = report["visuals"]["objects"], left_report["visuals"]["objects"]
assert (drawn["event_shapes"], drawn["first_frame_parts"], drawn["sequence_parts"], left["event_shapes"],
        left["first_frame_parts"], left["sequence_parts"]) == (11, 0, 11, 0, 0, 0), (drawn, left)
assert drawn["placements"] - left["placements"] == 49 and drawn["skipped_parts"] == left["skipped_parts"] == 0, \
    (drawn, left)
# The 11 magic parts are the only alpha parts the event shapes add.
assert drawn["alpha_parts"] - left["alpha_parts"] == 11, (drawn, left)
assert digest(package / "collision.bin") == digest(left_package / "collision.bin")
assert digest(package / "release.sha256") != digest(left_package / "release.sha256")

# The shapes' origins and magic parts, from the player's OPD and meshes as the
# bake read them.
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko  # noqa: E402
import ko_scene  # noqa: E402
import ko_shapes  # noqa: E402
opd = report["objects"]["source"]
shapes = ko_shapes.load_shapes(opd)["shapes"]
objects = ko_scene.object_files(Path(opd).parents[1])
half = report["extent_metres"] / 2


def magic(index, name, event):
    """The shape's origin and its magic part's centre and front normal, placed
    as `ko_scene.object_geometry` places a part's vertices."""
    shape = shapes[index]
    assert (shape["name"], shape["event_id"], shape["event_type"]) == (name, *event), shape["name"]
    assert ko_shapes.classify(shape) == "event_shown"
    (part,) = [p for p in shape["parts"] if len(p["textures"]) > 1 and p["texture_fps"] > 0]
    assert part["render_flags"] & ko_shapes.RF_ALPHABLENDING and not part["double_sided"], part
    assert (part["source_blend"], part["destination_blend"]) == (2, 2), part
    mesh = ko.import_mesh(objects[ko_scene._basename(part["mesh"])], 1.0)
    qx, qy, qz, qw = shape["rotation"]
    q, (sx, sy, sz), (px, py, pz) = [-qx, -qy, qz, qw], shape["scale"], shape["position"]
    origin = [px - half, py, half - pz]
    ax, ay, az = part["pivot"]
    points = [[o + w for o, w in zip(origin, ko_scene._rotate(q, [(v[0] + ax) * sx, (v[1] + ay) * sy,
                                                                 (v[2] - az) * sz]))]
              for v in mesh["vertices"]]
    assert len(points) == 4 and len(mesh["indices"]) == 6, (name, len(points), len(mesh["indices"]))
    a, b, c = (points[i] for i in mesh["indices"][:3])
    u, v = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
    # The world draw culls clockwise faces (GL_CCW front), so the drawn side
    # is the one this counter-clockwise normal points to.
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    length = sum(x * x for x in n) ** 0.5
    centre = [sum(p[k] for p in points) / 4 for k in range(3)]
    return origin, centre, [x / length for x in n]


def front_view(centre, normal, distance=7.0):
    """A camera `distance` in front of the part, aimed at its centre, at its
    centre's height or 1.8 m above the ground there, whichever is higher."""
    ex, ez = centre[0] + normal[0] * distance, centre[2] + normal[2] * distance
    ey = max(centre[1] + normal[1] * distance, ground(package, ex, ez) + 1.8)
    return "%r %r %r %r %r %r" % (ex, ey, ez, *centre)


x, y, z = magic(SHAPE, NAME, EVENT)[0]
y = ground(package, x, z)
view = "%r %r %r %r %r %r" % (x, y + 30, z + 6, x, y, z)
whole, plain, lit = draw(package, "drawn", view)
left_whole, left_plain, left_lit = draw(left_package, "left-out", view)
count, offset = changed(left_lit, lit)
assert count >= 2000 and offset is not None and max(map(abs, offset)) <= 40, (count, offset)
# From above the whole frame adds what the alpha parts draw: reported only.
top_whole, _ = changed(left_whole, whole, box=True)
top_alpha, _, _ = alpha_only(left_whole, whole, left_lit, lit)
# Negative control: without the shape the same capture is the same frame.
again_whole, again_plain, again_lit = draw(left_package, "left-out-again", view)
assert digest(again_lit) == digest(left_lit) and changed(left_lit, again_lit) == (0, None)
assert changed(left_whole, again_whole, box=True) == (0, None)
spot, spot_left = darkened(plain, lit), darkened(left_plain, left_lit)

fronts, cycles = [], []
for tag, (index, name, event) in (("gate", (SHAPE, NAME, EVENT)), ("bind", BIND)):
    _, centre, normal = magic(index, name, event)
    front = front_view(centre, normal)
    f_whole, _, f_lit = draw(package, tag + "-drawn", front)
    l_whole, _, l_lit = draw(left_package, tag + "-left-out", front)
    a_whole, _, a_lit = draw(left_package, tag + "-left-out-again", front)
    alpha, alpha_offset, darker = alpha_only(l_whole, f_whole, l_lit, f_lit)
    assert alpha >= 1000 and darker == 0 and max(map(abs, alpha_offset)) <= 80, \
        (tag, alpha, alpha_offset, darker)
    assert digest(a_lit) == digest(l_lit) and changed(l_whole, a_whole, box=True) == (0, None), tag
    fronts.append((name, *event, alpha, *alpha_offset, changed(l_lit, f_lit, box=True)[0]))
    # PQ-394 (D-212): with a frame time the part cycles. The client's log for
    # this part (its record centre) replays index + seconds x fps with the reset
    # to 0 on every frame, and once the capture shows a frame other than 0 the
    # whole frame differs from the frame-0 one where the world pass does not
    # (the part's own pixels), near the centre. A capture that reached frame 0
    # again is repeated at the next frame time.
    for seconds in ("0.05", "0.0625", "0.075"):
        log = []
        c_whole, _, c_lit = draw(package, "%s-cycle-%s" % (tag, seconds), front, seconds, log)
        mine = [r for r in world_sequence_log.rows(log[0]).values()
                if max(abs(a - b) for a, b in zip(r[0]["center"], centre)) < 0.01]
        assert len(mine) == 1, (tag, seconds, len(mine))
        shown = world_sequence_log.replay(mine[0])
        frames, fps = int(mine[0][0]["frames"]), float(mine[0][0]["fps"])
        assert (frames, fps) == (FRAMES[tag], FPS[tag]) and 40 in shown, (tag, frames, fps, sorted(shown)[-3:])
        if shown[40]:
            break
    else:
        raise AssertionError("%s: every capture reached frame 0" % tag)
    assert digest(c_lit) == digest(f_lit), tag  # the world pass holds no alpha part
    cycled, cycled_offset, _ = alpha_only(f_whole, c_whole, f_lit, c_lit)
    assert cycled >= 100 and max(map(abs, cycled_offset)) <= 80, (tag, seconds, cycled, cycled_offset)
    cycles.append((name, frames, fps, seconds, shown[40], len(set(shown.values())), cycled))

print("PASS KO bind points and warp gates graphical (PQ-392, PQ-398, PQ-394): ko-zone-10 places 11 event shapes (%d "
      "parts, 11 cycling magic parts, all alpha parts) where the left-out cook places none; at %s (event %d, type %d) "
      "%d world-pass pixels differ from the left-out frame, centroid %+.1f, %+.1f px from the centre; the maps "
      "darken %d centre pixels with the gate drawn, %d without; from above the whole frame differs in %d box "
      "pixels, %d of them alpha only; %s; the left-out cook's second captures are the same frames"
      % (drawn["placements"] - left["placements"], NAME, *EVENT, count, *offset, spot, spot_left, top_whole,
         top_alpha, "; ".join("7 m in front of %s's magic part (event %d, type %d) %d whole-frame box pixels "
                              "change where the world pass does not, none darker, centroid %+.1f, %+.1f px "
                              "(world pass %d)" % f for f in fronts)))
print("PASS KO magic parts cycle (PQ-394, D-212): %s" % "; ".join(
    "%s's magic part (%d frames at %g fps) replays its sequence log on every frame at %s s and shows frame %d at "
    "the capture (%d frames over the run), %d whole-frame box pixels from frame 0's where the world pass is the same"
    % c for c in cycles))
