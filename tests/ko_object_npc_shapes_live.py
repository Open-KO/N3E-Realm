"""Opt-in (make live-ko): Moradon's magic anvil drawn offscreen, in the state
1298 gives it while its object NPC is in, on the Moradon package cooked from
the player's own KO data (PQ-395, D-206).

1298 hides the anvil (`obj_co_itemup`, event 5001, event type 8) at load
(`005b4690` at `005b4a6a`); its AI server builds an object NPC for the SMD's
type 8 event (`00413693`, `0043bcaa`), and the client's NPC-in binds the shape
and shows it with status 1 (`005cd620`: `005ce31e`-`005ce334`, `005ce447`)
until NPC out hides it (`00455b70`). n3e has no object NPCs; the bake draws the
anvil always, in that state (binary + local-asset; inference, not observed:
rig frame open, PQ-396).

The camera stands 2.6 m south of the anvil's origin and 2.2 m above it, aimed
1.4 m above it. Two frames are read: the client's frame-40 capture, which
draws the whole frame (the world's alpha parts too: the fx parts are alpha
parts, which the world pass leaves to the alpha pass), and the world pass's
own capture (N3E_TEST_WORLD_OVERLAY, opaque parts only). The same camera is
drawn on a second cook of key 210 (`--features`, as the `moradon` prepare step
cooks it) with the anvil's class left out of the bake (`ko_shapes.BAKED` as
PQ-392 left it), which this script cooks into its own folder:

* provenance: the package places the one anvil (`npc_shown_shapes` 1) with its
  three parts, two of them fx parts that cycle their textures (PQ-394, D-212),
  where the left-out cook places none and has the same collision;
* within the central box of the frame (an eighth in from each edge, which
  leaves out the FPS label), the whole frames differ in at least 5,000 pixels
  centred within 80 px of the image centre, at least 1,000 of them green (the
  fx glow: G above R + 40 and above B), and the world-pass frames, without the
  alpha parts, differ in at least 2,000 (the table) with none of them green;
* negative control: a second capture of the left-out cook is the same frame
  within the box, so the checks above fail without the anvil;
* PQ-394: the captures above fix the sequences' frame time at 0 (every part on
  frame 0, so they repeat). Drawn again at a fixed frame time of 0.05 s (0.0625
  or 0.075 s if both fx parts come round to frame 0 at the capture), the two fx
  parts' sequence logs (5 and 10 frames at 8 fps) replay index + seconds x fps,
  0 at the count, on every frame, and the whole frame differs from the frame-0
  one in at least 100 box pixels where the world pass is the same.

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
    # The negative-control cook: key 210 as the moradon prepare step cooks it,
    # with the anvil's class left out of the bake as before PQ-395.
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import ko_shapes
    ko_shapes.BAKED = frozenset({"static", "event_shown"})
    sys.argv = ["tools/assetc/ko_bake.py", "210", "--features", "--into=" + sys.argv[2]]
    runpy.run_path("tools/assetc/ko_bake.py", run_name="__main__")
    sys.exit(0)

WORK = Path(os.environ.get("N3E_KO_WORK", "build/live-ko/work"))
B = Path("build/live-ko/object-npc-shapes")
B.mkdir(parents=True, exist_ok=True)
LEFT_OUT = WORK / "object-npc-shapes-left-out"
NAME, EVENT = "obj_co_itemup", (5001, 8)

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED Moradon's magic anvil needs N3E_GRAPHICAL=1 (make live-ko)")
    sys.exit(0)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(path):
    data = path.read_bytes()
    magic, size, _, body = data.split(b"\n", 3)
    width, height = map(int, size.split())
    assert magic == b"P6" and len(body) == width * height * 3, path
    return width, height, [body[i:i + 3] for i in range(0, len(body), 3)]


def draw(package, name, view, seconds="0", log=None):
    """PQ-394: `seconds` fixes the sequences' frame time (0: frame 0 throughout);
    with `log` (a list) the client's sequence log is appended to it."""
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


def changed(a, b):
    """Within the central box: the changed pixels' count, their centroid offset
    from the image centre, and how many of them are green in `b`."""
    width, height, p = pixels(a)
    _, _, q = pixels(b)
    at, green = [], 0
    for i, (u, v) in enumerate(zip(p, q)):
        x, y = i % width, i // width
        if u != v and width // 8 <= x < width - width // 8 and height // 8 <= y < height - height // 8:
            at.append((x, y))
            green += v[1] > v[0] + 40 and v[1] > v[2]
    if not at:
        return 0, None, 0
    cx = sum(x for x, _ in at) / len(at) - width / 2
    cy = sum(y for _, y in at) / len(at) - height / 2
    return len(at), (cx, cy), green


package = WORK / "packages" / "moradon"
report = json.loads((WORK / "ko-moradon" / "provenance.json").read_text())
cook = subprocess.run([sys.executable, __file__, "--cook-left-out", str(LEFT_OUT)],
                      capture_output=True, text=True, timeout=1800)
(B / "left-out-cook.log").write_text(cook.stdout + cook.stderr)
assert cook.returncode == 0, cook.stderr[-2000:]
left_package = LEFT_OUT / "packages" / "moradon"
left_report = json.loads((LEFT_OUT / "ko-moradon" / "provenance.json").read_text())
drawn, left = report["visuals"]["objects"], left_report["visuals"]["objects"]
assert (drawn["npc_shown_shapes"], left["npc_shown_shapes"], drawn["event_shapes"], left["event_shapes"]) \
    == (1, 0, 2, 2), (drawn, left)
assert (drawn["first_frame_parts"], left["first_frame_parts"]) == (0, 0), (drawn, left)
assert drawn["sequence_parts"] - left["sequence_parts"] == 2, (drawn, left)
assert drawn["placements"] - left["placements"] == 3 and drawn["skipped_parts"] == left["skipped_parts"], \
    (drawn, left)
assert digest(package / "collision.bin") == digest(left_package / "collision.bin")
assert digest(package / "release.sha256") != digest(left_package / "release.sha256")

# The anvil's origin, from the player's OPD as the bake read it.
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko_shapes  # noqa: E402
opd = report["objects"]["source"]
(anvil,) = [s for s in ko_shapes.load_shapes(opd)["shapes"] if (s["event_id"], s["event_type"]) == EVENT]
assert anvil["name"] == NAME and ko_shapes.classify(anvil) == "event_npc_shown", anvil["name"]
half = report["extent_metres"] / 2
x, y, z = anvil["position"][0] - half, anvil["position"][1], half - anvil["position"][2]
view = "%r %r %r %r %r %r" % (x, y + 2.2, z + 2.6, x, y + 1.4, z)
whole, world = draw(package, "drawn", view)
left_whole, left_world = draw(left_package, "left-out", view)
count, centroid, green = changed(left_whole, whole)
assert count >= 5000 and green >= 1000 and max(map(abs, centroid)) <= 80, (count, centroid, green)
world_count, world_centroid, world_green = changed(left_world, world)
assert world_count >= 2000 and world_green == 0 and max(map(abs, world_centroid)) <= 80, \
    (world_count, world_centroid, world_green)
# Negative control: without the anvil the same capture is the same frame.
again_whole, again_world = draw(left_package, "left-out-again", view)
assert changed(left_whole, again_whole) == (0, None, 0) and digest(again_world) == digest(left_world)
# PQ-394 (D-212): the fx parts cycle (their records are the only 8-fps sequences
# in the zone; the warp gates' run at 10).
for seconds in ("0.05", "0.0625", "0.075"):
    log = []
    c_whole, c_world = draw(package, "cycle-" + seconds, view, seconds, log)
    fx_rows = [r for r in world_sequence_log.rows(log[0]).values() if float(r[0]["fps"]) == 8.0]
    assert sorted(int(r[0]["frames"]) for r in fx_rows) == [5, 10], [r[0] for r in fx_rows]
    shown = [world_sequence_log.replay(r) for r in fx_rows]
    assert all(40 in s for s in shown), [sorted(s)[-3:] for s in shown]
    if any(s[40] for s in shown):
        break
else:
    raise AssertionError("both fx parts at frame 0 at every capture")
assert digest(c_world) == digest(world)  # the world pass holds no alpha part
cycled, cycled_centroid, _ = changed(whole, c_whole)
assert cycled >= 100, (seconds, cycled)
print("PASS KO magic anvil graphical (PQ-395): moradon places %s (event %d, type %d) with %d parts, 2 cycling "
      "fx parts, where the left-out cook places none; the whole frame differs from the left-out one in %d pixels "
      "(%d green, the fx glow), centroid %+.1f, %+.1f px from the centre; the world pass alone in %d (none green); "
      "the left-out cook's second capture is the same frame"
      % (NAME, *EVENT, drawn["placements"] - left["placements"], count, green, *centroid, world_count))
print("PASS KO magic anvil cycles (PQ-394, D-212): its two fx parts (5 and 10 frames at 8 fps) replay their sequence "
      "logs on every frame at %s s and show frames %s at the capture; the whole frame differs from frame 0's in %d "
      "box pixels where the world pass is the same" % (seconds, "/".join(str(s[40]) for s in shown), cycled))
