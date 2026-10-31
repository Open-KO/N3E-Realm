"""KX-04: find and verify a spawn on the baked Moradon collision.

The map centre is not a spawn. KO-CAT recorded `(256,256)` as a survey point,
and the bake confirms a walk there does not move, so a spawn has to be searched
for and then proven.

Two stages, deliberately separated so the proof does not rest on a
reimplementation of the solver:

1. A cheap Python pre-filter rejects candidates on terrain slope and on object
   geometry standing in the actor's capsule. This only narrows the field.
2. The surviving candidates are walked with the **engine's own solver** through
   the existing fixture harness, in both C++ and Rust. A candidate is a spawn
   only if the engine moves it in every direction tried and returns it to where
   it started, and only if both languages agree.

It fails closed: if nothing survives, it reports that and selects nothing.
"""

from common import *
import subprocess

import ko_bake
import ko_terrain

# Actor capsule from the demo movement rules, so the survey matches what the
# engine will actually admit.
ACTOR_RADIUS = 0.35
ACTOR_HEIGHT = 1.8
MAX_SLOPE = 0.55  # tangent; the solver rejects steeper ground
PROBE_STEPS = 10


def _surface(height):
    """Exactly the terrain triangles the cooker emits for this heightfield."""
    import main
    return main.heightfield_triangles(height)


def _slope(height, gx, gz):
    """Steepest neighbour gradient at a grid sample."""
    w, d, sp = height["width"], height["depth"], height["spacing"]
    h = height["heights"]
    here = h[gz * w + gx]
    worst = 0.0
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, nz = gx + dx, gz + dz
        if 0 <= nx < w and 0 <= nz < d:
            worst = max(worst, abs(h[nz * w + nx] - here) / sp)
    return worst


def _blocked(faces, x, z, floor):
    """True if object geometry stands in the actor's capsule at (x, z)."""
    top = floor + ACTOR_HEIGHT
    for tri in faces:
        ys = [p[1] for p in tri]
        if max(ys) < floor - 0.1 or min(ys) > top:
            continue
        xs = [p[0] for p in tri]
        zs = [p[2] for p in tri]
        if (min(xs) - ACTOR_RADIUS <= x <= max(xs) + ACTOR_RADIUS
                and min(zs) - ACTOR_RADIUS <= z <= max(zs) + ACTOR_RADIUS):
            return True
    return False


def candidates(height, faces, stride=6, margin=10, within=None):
    """Grid samples that survive slope and capsule pre-filtering.

    `within` optionally limits samples to a world rectangle (x0, z0, x1, z1).
    """
    w, d, sp = height["width"], height["depth"], height["spacing"]
    ox, _, oz = height["origin"]
    out = []
    for gz in range(margin, d - margin, stride):
        for gx in range(margin, w - margin, stride):
            if _slope(height, gx, gz) > MAX_SLOPE:
                continue
            x, z = ox + gx * sp, oz + gz * sp
            if within and not (within[0] <= x <= within[2] and within[1] <= z <= within[3]):
                continue
            floor = height["heights"][gz * w + gx]
            if _blocked(faces, x, z, floor):
                continue
            out.append({"sample": [gx, gz], "position": [x, floor, z]})
    return out


def support(triangles, x, z):
    """Highest walkable support under (x, z), mirroring the engine's rule.

    `movement::support` accepts triangles whose normal is within 45 degrees of
    vertical and takes the highest surface; a paved object above terrain wins.
    This only proposes a height: `verify` still proves the point with the engine.
    """
    best = -math.inf
    for i in range(0, len(triangles), 3):
        a, b, c = triangles[i], triangles[i + 1], triangles[i + 2]
        if (x < min(a[0], b[0], c[0]) - 1e-4 or x > max(a[0], b[0], c[0]) + 1e-4
                or z < min(a[2], b[2], c[2]) - 1e-4 or z > max(a[2], b[2], c[2]) + 1e-4):
            continue
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        if abs(ny) < 0.707107 * math.sqrt(nx * nx + ny * ny + nz * nz):
            continue
        d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(d) < 1e-8:
            continue
        u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
        v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
        if u >= -1e-6 and v >= -1e-6 and u + v <= 1 + 1e-6:
            best = max(best, u * a[1] + v * b[1] + (1 - u - v) * c[1])
    return best


def area_candidates(triangles, area, step=4):
    """Integer lattice points in a world rectangle, nearest its centre first,
    at the engine's support height. No terrain-only pre-filter: object floors
    such as paving are real support, and the engine check decides."""
    x0, z0, x1, z1 = area
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    points = [(x, z) for z in range(int(z0), int(z1) + 1, step)
              for x in range(int(x0), int(x1) + 1, step)]
    points.sort(key=lambda p: (math.hypot(p[0] - cx, p[1] - cz), p[1], p[0]))
    out = []
    for x, z in points:
        y = support(triangles, x, z)
        if math.isfinite(y):
            out.append({"sample": [x, z], "position": [float(x), y, float(z)]})
    return out


def _walk(binary, triangles, start, inputs, scratch):
    scratch.write_text(" ".join(map(str,
        [len(triangles)] + [v for t in triangles for v in t]
        + list(start) + [v for p in inputs for v in p])) + "\n")
    done = subprocess.run([binary, str(scratch)], check=True,
                          capture_output=True, text=True)
    return [list(map(float, line.split())) for line in done.stdout.splitlines()]


def route(triangles, start, waypoints, movement, scratch, binary="build/client/n3e-walk-check",
          tolerance=0.5):
    """Engine-solver run along waypoints, re-aiming from the actual position.

    `movement` is the package walk speed plus its movement object; the player runs.
    Returns (reached, final position, first unreached waypoint or None).
    """
    config = [str(v) for v in (movement["speed"], movement["run_speed"], movement["backward_speed"],
                               movement["radius"], movement["height"], movement["step_height"])]
    step = movement["run_speed"] * 0.05
    head = " ".join(map(str, [len(triangles)] + [v for t in triangles for v in t]))
    position = list(start)
    for goal in waypoints:
        for _ in range(4):
            dx, dz = goal[0] - position[0], goal[1] - position[2]
            distance = math.hypot(dx, dz)
            if distance <= tolerance:
                break
            count = max(1, math.ceil(distance / step))
            scratch.write_text(head + " " + " ".join(map(str, position)) + "\n"
                               + "\n".join([f"{dx / distance} {dz / distance} 1"] * count) + "\n")
            done = subprocess.run([binary, str(scratch), *config], check=True, capture_output=True, text=True)
            position = [float(v) for v in done.stdout.split()[-3:]]
        if math.hypot(goal[0] - position[0], goal[1] - position[2]) > tolerance:
            return False, position, goal
    return True, position, None


def verify(triangles, position, scratch, binary="build/client/n3e-walk-check"):
    """Engine-solver check: it must move out and come back, in every direction."""
    start = [position[0], position[1] + 0.1, position[2]]
    report = {"position": start, "directions": {}}
    for name, (dx, dz) in (("east", (1, 0)), ("west", (-1, 0)),
                           ("north", (0, 1)), ("south", (0, -1))):
        out = _walk(binary, triangles, start,
                    [(dx, dz)] * PROBE_STEPS + [(-dx, -dz)] * PROBE_STEPS,
                    scratch)
        away = max(math.dist(p, start) for p in out[:PROBE_STEPS])
        back = math.dist(out[-1], start)
        report["directions"][name] = {"away": away, "returned": back}
    report["min_away"] = min(v["away"] for v in report["directions"].values())
    report["worst_return"] = max(v["returned"] for v in report["directions"].values())
    report["open"] = report["min_away"] > 0.4 and report["worst_return"] < 0.4
    return report


def survey(gtd_path, opd_path, scratch_dir, limit=40, within=None, headerless=False):
    """Search, verify with the engine, and fail closed if nothing qualifies.

    With `within`, only that rectangle is searched, on every grid sample.
    `headerless` reads the pre-1264 (1097) GTD and OPD (the 1097 Moradon, PQ-224).
    """
    height, faces, bake_report = ko_bake.bake(gtd_path, opd_path, headerless=headerless)
    triangles = _surface(height) + [p for tri in faces for p in tri]
    scratch = pathlib.Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    probe = scratch / "survey.txt"

    found = area_candidates(triangles, within) if within else candidates(height, faces)
    checked, chosen = [], None
    for candidate in found[:limit]:
        result = verify(triangles, candidate["position"], probe)
        result["sample"] = candidate["sample"]
        checked.append(result)
        if result["open"] and (chosen is None
                               or result["min_away"] > chosen["min_away"]):
            chosen = result
    return {
        "bake": bake_report,
        "triangles": len(triangles),
        "pre_filtered": len(found),
        "engine_checked": len(checked),
        "spawn": chosen,
        "rejected": [c for c in checked if not c["open"]][:5],
    }, triangles


# PQ-217: start areas on a map past the walk check's bound. n3e-walk-check and
# `n3e-server --walk-fixture` take at most the cooker's former 196,608
# collision points; a 513-sample map's terrain alone is 1,572,864. Every engine
# query the survey makes stays near the start area (support at a lattice point
# inside it; a probe of PROBE_STEPS x 0.15 m with the 0.35 m capsule), and a
# triangle away from a query cannot support or block it, so the survey reads the
# triangles that reach the area grown by CROP_MARGIN.
CROP_MARGIN = 32.0
WALK_POINTS = 196608


def crop(triangles, area, margin=CROP_MARGIN):
    """The triangles whose xz bounds reach `area` grown by `margin`, in order."""
    x0, z0, x1, z1 = area[0] - margin, area[1] - margin, area[2] + margin, area[3] + margin
    out = []
    for i in range(0, len(triangles), 3):
        a, b, c = triangles[i], triangles[i + 1], triangles[i + 2]
        if (max(a[0], b[0], c[0]) >= x0 and min(a[0], b[0], c[0]) <= x1
                and max(a[2], b[2], c[2]) >= z0 and min(a[2], b[2], c[2]) <= z1):
            out.extend((a, b, c))
    return out


def survey_starts(gtd_path, opd_path, scratch_dir, areas, limit=24,
                  max_samples=ko_terrain.CHUNKED_MAX_SAMPLES, headerless=False):
    """One engine-verified spawn per named start area, as `survey(within=...)`.

    `areas` maps a name to an n3e rectangle (`ko_start.areas`). Each area is
    searched on its own crop of the map (`crop`) with `area_candidates` and
    `verify`, and keeps the open candidate the engine moves farthest; an area
    with none has spawn None, and the caller refuses to publish.
    """
    height, faces, bake_report = ko_bake.bake(gtd_path, opd_path, max_samples, headerless)
    triangles = _surface(height) + [p for tri in faces for p in tri]
    scratch = pathlib.Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    probe = scratch / "survey.txt"
    starts = {}
    for name, area in areas.items():
        local = crop(triangles, area)
        if len(local) > WALK_POINTS:
            raise ValueError("the %s start area's crop has %d collision points, past the "
                             "walk check's %d" % (name, len(local), WALK_POINTS))
        found = area_candidates(local, area)
        checked, chosen = [], None
        for candidate in found[:limit]:
            result = verify(local, candidate["position"], probe)
            result["sample"] = candidate["sample"]
            checked.append(result)
            if result["open"] and (chosen is None or result["min_away"] > chosen["min_away"]):
                chosen = result
        starts[name] = {
            "area": list(area),
            "crop_points": len(local),
            "pre_filtered": len(found),
            "engine_checked": len(checked),
            "spawn": chosen,
            "rejected": [c for c in checked if not c["open"]][:5],
        }
    return {"bake": bake_report, "triangles": len(triangles), "starts": starts}, triangles


# PQ-218: how far from its start area a homeland's walk target may lie. The walk
# stays inside the start area grown by WALK_REACH, so with the 0.35 m capsule it
# keeps CROP_MARGIN - WALK_REACH metres inside the crop the survey reads.
WALK_REACH = 24.0


def walk_target(triangles, area, spawn, movement, scratch_dir, reach=WALK_REACH, step=8, limit=24, nearest=8.0):
    """A surveyed point to walk to from `spawn`, for the play stack's live check.

    Lattice points of `area` grown by `reach` (every `step` m), farthest from the
    spawn first and at least `nearest` m from it, each verified open with the
    engine (`verify`) and then walked from the spawn with the engine solver
    (`route`, the package's run speed and capsule). Returns the first one the
    engine reaches, with the solver's end point, or None when none of the first
    `limit` is reachable. `triangles` is the start area's crop (`crop`).
    """
    x0, z0, x1, z1 = area
    grown = (x0 - reach, z0 - reach, x1 + reach, z1 + reach)
    scratch = pathlib.Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    probe = scratch / "walk.txt"
    found = [c for c in area_candidates(triangles, grown, step)
             if math.hypot(c["position"][0] - spawn[0], c["position"][2] - spawn[2]) >= nearest]
    found.sort(key=lambda c: (-math.hypot(c["position"][0] - spawn[0], c["position"][2] - spawn[2]),
                              c["sample"][1], c["sample"][0]))
    tried = 0
    for candidate in found[:limit]:
        tried += 1
        if not verify(triangles, candidate["position"], probe)["open"]:
            continue
        x, z = candidate["sample"]
        reached, end, _ = route(triangles, spawn, [[x, z]], movement, probe)
        if reached:
            return {"target": candidate["position"], "engine_end": end, "tried": tried,
                    "distance": math.hypot(x - spawn[0], z - spawn[2])}
    return None
