"""KX-01 GTD importer and the cooker's quad diagonal convention.

Uses original asymmetric fixtures only; no reference asset is required.
"""
import json, math, shutil, struct, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import ko_terrain, ko_terrain_fixture as fixture, main

B = Path("build/kx")
B.mkdir(parents=True, exist_ok=True)


def parse(**kw):
    path = B / "fixture.gtd"
    path.write_bytes(fixture.build(**kw))
    return ko_terrain.load(path)


def rejects(reason, **kw):
    try:
        parse(**kw)
    except ValueError:
        return
    raise AssertionError("accepted invalid GTD: " + reason)


SAMPLES = 17
parsed = parse()

# Header and bounded structure.
assert parsed["version"] == 2 and parsed["name"] == "fixture_terrain"
assert parsed["samples"] == SAMPLES and parsed["spacing"] == 4.0
assert parsed["grass"] == "Grass/original.n3pmesh"
assert len(parsed["patches"]) == ((SAMPLES - 1) // 8) ** 2
assert parsed["tile_sources"] == ["Tile/original_a.gtt", "Tile/original_b.gtt"]
assert parsed["tile_references"] == [
    {"source": 0, "tile": 0},
    {"source": 1, "tile": 3},
    {"source": 0, "tile": 7},
]
# Reaching the deprecated lightmap count with value zero proves every preceding
# offset; the reader must also have consumed the whole file.
assert parsed["parsed_bytes"] == parsed["total_bytes"], parsed
assert parsed["unused_bit_records"] == 0
# Bit 31 belongs to no field. Real local data sets it on a few records, so it is
# counted and reported rather than rejected, and it must not disturb decoding.
marked = parse(reserved=True)
assert marked["unused_bit_records"] == SAMPLES * SAMPLES
assert marked["tiles"] == parsed["tiles"] and marked["heights"] == parsed["heights"]

# Orientation: the reference stores MAPDATA x-major, n3e heightfields are
# z-major. The fixture is asymmetric, so a transposed import fails here.
assert parsed["heights"] == fixture.expected_heights(SAMPLES)
assert parsed["heights"][1 * SAMPLES + 0] != parsed["heights"][0 * SAMPLES + 1]
assert parsed["height_range"] == [
    min(parsed["heights"]),
    max(parsed["heights"]),
]

# Bitfield decode by explicit bit range, not compiler layout.
for x, z in [(0, 0), (1, 0), (0, 1), (5, 11), (SAMPLES - 1, SAMPLES - 1)]:
    assert parsed["tiles"][z * SAMPLES + x] == fixture.tile(x, z, SAMPLES), (x, z)
assert ko_terrain.unpack_tile(ko_terrain.pack_tile(True, 31, 30, 1023, 1022)) == dict(
    full=True, dir1=31, dir2=30, tex1=1023, tex2=1022
)

# Bounds and rejections.
rejects("version", version=3)
rejects("negative version", version=-1)
rejects("name length", name="x" * 31)
rejects("map size not a whole number of patches", samples=18)
rejects("map size beyond the supported heightfield", samples=201)
rejects("deprecated lightmap data", lightmap=1)
rejects("tile reference outside the GTT table", references=((2, 0),))
rejects("negative tile reference", references=((-1, 0),))
truncated = B / "truncated.gtd"
truncated.write_bytes(fixture.build()[:-64])
try:
    ko_terrain.load(truncated)
except ValueError:
    pass
else:
    raise AssertionError("accepted truncated GTD")
print("PASS GTD header, x-major transpose, explicit tile bitfields, GTT references, bounds and rejections")

# The cooker's quad diagonal. KO splits by (x + z) % 2; the original fixed split
# disagrees on half the quads, so visuals and collision must share the choice.
def cook(diagonal):
    with tempfile.TemporaryDirectory(dir=B) as td:
        source = Path(td) / "package"
        shutil.copytree("games/demo", source)
        meta = json.loads((source / "scene.json").read_text())
        meta["heightfield"] = dict(
            width=3, depth=3, origin=[0, 0, 0], spacing=2,
            heights=[0, 1, 0, 2, 5, 3, 0, 4, 0],
        )
        if diagonal:
            meta["heightfield"]["diagonal"] = diagonal
        (source / "scene.json").write_text(json.dumps(meta))
        out = Path(td) / "cooked"
        main.cook(source, out)
        raw = (out / "collision.bin").read_bytes()
        assert raw[:4] == b"N3C1"
        n = struct.unpack("<I", raw[4:8])[0]
        pts = [struct.unpack("<fff", raw[8 + i * 12 : 20 + i * 12]) for i in range(n)]
        return [tuple(pts[i : i + 3]) for i in range(0, len(pts), 3)]


fixed, alternating = cook(None), cook("alternating")
mirrored = cook("alternating-mirrored")
assert cook("fixed") == fixed, "explicit fixed must equal the default"
assert len(fixed) == len(alternating) == len(mirrored) == 8
# Quad (0,0) has (x + z) % 2 == 0, so both conventions split it identically.
assert fixed[0:2] == alternating[0:2]
# Quad (1,0) is odd, so the alternating convention must split the other way.
assert fixed[2:4] != alternating[2:4]
corners = lambda quad: sorted({p for tri in quad for p in tri})
assert corners(fixed[2:4]) == corners(alternating[2:4]), "same quad corners"
shared = lambda quad: sorted(set(quad[0]) & set(quad[1]))
assert shared(fixed[2:4]) != shared(alternating[2:4]), "diagonal must differ"
# Mirroring an axis inverts the parity, so the mirrored phase splits every quad
# the other way while keeping the same corners and winding.
for a, b in zip(alternating, mirrored):
    assert sorted({p for tri in (a,) for p in tri}) != [] and set(a) != set(b) or a == b
for quad in range(0, 8, 2):
    assert shared(alternating[quad:quad + 2]) != shared(mirrored[quad:quad + 2]), (
        "mirrored phase must flip every quad's diagonal, not just some")
    assert corners(alternating[quad:quad + 2]) == corners(mirrored[quad:quad + 2])
for name, quads in [("fixed", fixed), ("alternating", alternating),
                    ("alternating-mirrored", mirrored)]:
    for tri in quads:
        a, b, c = tri
        ab = [b[k] - a[k] for k in range(3)]
        ac = [c[k] - a[k] for k in range(3)]
        cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2],
                 ab[0] * ac[1] - ab[1] * ac[0]]
        assert cross[1] > 0, (name, "upward winding must stay consistent", tri)
print("PASS quad diagonal conventions, mirrored phase, preserved default, shared corners and consistent winding")

# ---------------------------------------------------------------------------
# KX-02: OPD collision block.
import ko_shapes, ko_shapes_fixture as shapes


def parse_opd(**kw):
    path = B / "fixture.opd"
    path.write_bytes(shapes.build(**kw))
    return ko_shapes.load_collision(path)


def rejects_opd(reason, **kw):
    try:
        parse_opd(**kw)
    except ValueError:
        return
    raise AssertionError("accepted invalid OPD: " + reason)


o = parse_opd()
assert o["version"] == 1 and o["name"] == "fixture_shapes"
assert [o["width"], o["depth"]] == [64.0, 32.0]
# 64x32 metres over 16-metre cells, and the grid is asymmetric on purpose.
assert o["cell_grid"] == [4, 2]
assert o["faces"] == 6 and o["usable_faces"] == 6
assert o["shape_count"] == 3
assert o["parsed_bytes"] == o["total_bytes"], o
# Cells are stored z-major; the fixture places faces in distinct cells so a
# swapped walk would report different coordinates here.
assert [(c["x"], c["z"]) for c in o["cells"]] == [(0, 0), (1, 1)]
assert [len(c["sub_cells"]) for c in o["cells"]] == [1, 1]
assert o["cells"][0]["sub_cells"][0]["faces"] == 2
assert o["cells"][1]["sub_cells"][0]["indices"] == [6, 7, 8]
assert o["cells"][0]["shapes"] == [0] and o["cells"][1]["shapes"] == [17]

# Anomalies present in real local data are classified, never silently baked.
marked = parse_opd(degenerate=(3,), sentinel=(4,), tall=(5,))
assert marked["face_kinds"]["degenerate"]["faces"] == 1
assert marked["face_kinds"]["sentinel"]["faces"] == 1
assert marked["face_kinds"]["tall"]["faces"] == 1
assert marked["usable_faces"] == 3
# A sentinel coordinate is finite, so an isfinite check alone would pass it.
import math as _math
assert _math.isfinite(shapes.SENTINEL)
# Classification counts what a cell actually references.
used = parse_opd(sentinel=(0,), cells=((0, 0, (0,)),))
assert used["face_kinds"]["sentinel"] == {"faces": 1, "referenced": 1, "examples": [0]}

rejects_opd("version", version=3)
rejects_opd("name length", name="x" * 31)
rejects_opd("zero map size", width=0.0)
rejects_opd("map size not a multiple of four", width=66.0)
rejects_opd("map size beyond the cell grid", width=8192.0)
rejects_opd("collision index outside the triangle soup", bad_index=True)
truncated_opd = B / "truncated.opd"
truncated_opd.write_bytes(shapes.build()[:-32])
try:
    ko_shapes.load_collision(truncated_opd)
except ValueError:
    pass
else:
    raise AssertionError("accepted truncated OPD")
print("PASS OPD header, z-major cells, sub-cell indices, face classification, bounds and rejections")

# ---------------------------------------------------------------------------
# KX-03: the shared collision bake.
import ko_bake

BAKE_SAMPLES = 17  # 17 samples at spacing 4 -> a 64 m square, matching the OPD


def bake_pair(**opd):
    gtd = B / "bake.gtd"
    gtd.write_bytes(fixture.build(samples=BAKE_SAMPLES))
    opd.setdefault("width", 64.0)
    opd.setdefault("depth", 64.0)
    path = B / "bake.opd"
    path.write_bytes(shapes.build(**opd))
    return ko_bake.bake(gtd, path)


hf, tris, prov = bake_pair()
assert prov["extent_metres"] == 64.0
assert hf["origin"] == [-32.0, 0.0, -32.0]
assert hf["diagonal"] == "alternating-mirrored", "the bake must use the KO quad split"
assert hf["width"] == hf["depth"] == BAKE_SAMPLES
# The z flip is expressed by reversing sample order, so the surface is mirrored
# while the grid the cooker triangulates is untouched.
plain = ko_terrain.load(B / "bake.gtd")["heights"]
assert hf["heights"][0] == plain[(BAKE_SAMPLES - 1) * BAKE_SAMPLES]
assert hf["heights"] != plain, "an asymmetric surface must actually be flipped"

# Terrain rows and object vertices must land on the same line for the same
# KO coordinate, or collision and the surface disagree.
for ko_z in (0.0, 16.0, 64.0):
    row = int(round((64.0 - ko_z) / hf["spacing"]))
    assert abs((hf["origin"][2] + row * hf["spacing"]) - (32.0 - ko_z)) < 1e-6, ko_z

# A terrain/object extent mismatch is a hard error, not a silent rescale.
try:
    bake_pair(width=32.0, depth=32.0)
except ValueError:
    pass
else:
    raise AssertionError("accepted mismatched terrain and object extents")

# Each anomaly class is resolved explicitly.
base = bake_pair()[2]["collision_faces"]
dropped = bake_pair(degenerate=(2,))
assert dropped[2]["faces_dropped_degenerate"] == 1
assert dropped[2]["collision_faces"] == base - 1

barrier = bake_pair(sentinel=(2,))
# One placeholder footprint becomes a closed four-wall box: eight triangles.
assert barrier[2]["sentinel_footprints"] == 1
assert barrier[2]["barrier_faces"] == 8
assert barrier[2]["collision_faces"] == base - 1 + 8
lo, hi = barrier[2]["barrier_clamp"]
for tri in barrier[1][-8:]:
    for p in tri:
        assert lo - 1e-3 <= p[1] <= hi + 1e-3, p
assert any(abs(p[1] - lo) < 1e-3 for tri in barrier[1][-8:] for p in tri)
assert any(abs(p[1] - hi) < 1e-3 for tri in barrier[1][-8:] for p in tri)

tall = bake_pair(tall=(2,))
assert tall[2]["vertices_clamped"] >= 1
lo, hi = tall[2]["barrier_clamp"]
for tri in tall[1]:
    for p in tri:
        assert lo - 1e-3 <= p[1] <= hi + 1e-3, "a span beyond the margin survived"

# Negating z mirrors handedness, so object triangles reverse to keep facing.
def normal(tri):
    a, b, c = tri
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    return [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0]]


raw = ko_shapes.load_collision(B / "bake.opd")["vertices"]
source = [raw[0], raw[1], raw[2]]
flipped = [[p[0] - 32.0, p[1], 32.0 - p[2]] for p in source][::-1]
assert normal(tris[0]) == normal(flipped), "object winding was not preserved"
print("PASS collision bake: extent match, z-flip consistency, degenerate drop, sentinel barrier, span clamp, winding")

# ---------------------------------------------------------------------------
# KX-03 equality gate: both runtimes must agree on the real bake, not a fixture.
# Skipped when the optional local assets are absent; it never silently passes.
import subprocess

zones = Path("assets/ko/Zones")
gtd, opd = zones / "moradon_xmas.gtd", zones / "moradon_xmas.opd"
if not (gtd.exists() and opd.exists()):
    print("SKIP shared-bake equality: local Moradon assets absent")
else:
    height, faces, report = ko_bake.bake(gtd, opd)
    # Rebuild the surface the cooker would emit, so the walk runs on exactly
    # what ships in collision.bin rather than on the object faces alone.
    w, d, sp = height["width"], height["depth"], height["spacing"]
    ox, _, oz = height["origin"]
    surface = main.heightfield_triangles(height)
    triangles = surface + [p for tri in faces for p in tri]
    assert len(triangles) == report["terrain_points"] + report["collision_points"]
    assert len(triangles) <= 196608, "bake exceeds the collision vertex cap"

    fixture_path = B / "moradon-walk.txt"
    # Not the map centre: KO-CAT records (256,256) as a survey point rather
    # than a spawn, and the bake confirms it — a walk there does not move.
    # Take the first sample the KX-04 pre-filter accepts instead of a
    # hand-picked cell, so this gate does not depend on one coordinate staying
    # open as the surface is refined.
    import ko_survey
    open_ground = ko_survey.candidates(height, faces)
    assert open_ground, "no open ground on the baked Moradon surface"
    start = list(open_ground[0]["position"])
    start[1] += 0.1
    inputs = [(1, 0)] * 12 + [(0, 1)] * 12 + [(-1, -1)] * 12
    fixture_path.write_text(" ".join(map(str,
        [len(triangles)] + [f for v in triangles for f in v]
        + start + [f for v in inputs for f in v])) + "\n")

    runs = []
    for command in (["build/client/n3e-walk-check", str(fixture_path)],
                    ["target/debug/n3e-server", "--walk-fixture", str(fixture_path)]):
        done = subprocess.run(command, check=True, capture_output=True, text=True)
        runs.append([list(map(float, line.split()))
                     for line in done.stdout.splitlines()])
    assert len(runs[0]) == len(inputs) and len(runs[1]) == len(inputs)
    worst = max(abs(a - b) for x, y in zip(*runs) for a, b in zip(x, y))
    assert worst < 1e-6, "C++ and Rust disagree on the shared bake: %g" % worst
    moved = math.dist(runs[0][-1], start)
    assert moved > 0.5, "the walk did not move across the baked surface"
    assert all(abs(p[1]) < 200 for p in runs[0]), "a placeholder height leaked in"
    print("PASS shared bake: %d collision points, C++/Rust agree within %.1e over %.1f m"
          % (len(triangles), worst, moved))

# ---------------------------------------------------------------------------
# KX-02 visual half: the placed object records after the collision block.
spec = [
    dict(label="tree", position=(10.0, 1.0, 20.0),
         parts=(("xmas_tree.n3pmesh", ("bark.dxt", "leaf.dxt"), 0.0,
                 ko_shapes.RF_ALPHABLENDING | ko_shapes.RF_DOUBLESIDED, 0.5),)),
    dict(label="gate", event_id=1100, event_type=1),
    dict(label="banner", anim_keys=4),
    dict(label="torch", parts=(("torch.n3pmesh", ("f0.dxt", "f1.dxt"), 8.0),)),
    dict(label="guard", npc_id=42, npc_status=1),
    dict(label="extra", kind=0x400 | ko_shapes.OBJ_SHAPE_EXTRA),
    dict(label="hollow", parts=()),
    # PQ-392 (D-205): 1298 shows a shape with an event id at load only for event
    # types 0 and 5 (005b4690 at 005b4a5b-005b4a73), whatever its NPC fields and
    # 0x1000 kind; such a shape is still refused when it animates or has no mesh.
    dict(label="bindpoint", kind=0x141b, event_id=101, event_type=0, npc_status=1,
         parts=(("bind.n3pmesh", ("glow0.dxt", "glow1.dxt"), 10.0),)),
    dict(label="warpgate", kind=0x141b, event_id=4006, event_type=5, npc_id=12, npc_status=1),
    dict(label="itemup", kind=0x141b, event_id=1, event_type=8),
    dict(label="turning gate", event_id=7, event_type=5, anim_keys=2),
    dict(label="no id", event_type=5),
    dict(label="hollow gate", event_id=8, event_type=0, parts=()),
    # PQ-395 (D-206): 1298's object NPC shows a 0x1000 shape of event type 8
    # with status 1 (005cd620: 005ce31e, 005ce447); the bake draws it in that
    # state. Without the 0x1000 kind, with another status (the item-up above has
    # 0) or as type 6 it stays out; it is still refused when it animates or has
    # no mesh.
    dict(label="anvil", kind=0x141b, event_id=5001, event_type=8, npc_status=1,
         parts=(("anvil.n3pmesh", ("fx0.dxt", "fx1.dxt"), 8.0),)),
    dict(label="plain anvil", kind=0x400, event_id=5001, event_type=8, npc_status=1),
    dict(label="barricade", kind=0x141b, event_id=3200, event_type=6, npc_status=1),
    dict(label="turning anvil", kind=0x141b, event_id=5001, event_type=8, npc_status=1, anim_keys=2),
    dict(label="hollow anvil", kind=0x141b, event_id=5001, event_type=8, npc_status=1, parts=()),
    # PQ-412 (D-213): a static shape's cycling part is placed with its sequence
    # (the "torch" above, flags 0) unless one of its cycling parts turns after
    # the advance: RF_BOARD_Y (00442cc6) or the RF_WOBBLE timer (004429b0). A
    # billboard on a part that does not cycle, or two textures at fps 0, keeps
    # the shape static; a cycling shape without a mesh is empty.
    dict(label="fire", parts=(("fire.n3pmesh", ("f0.dxt", "f1.dxt"), 10.0, ko_shapes.RF_BOARD_Y | 1),
                              ("brazier.n3pmesh", ("iron.dxt",), 10.0))),
    dict(label="wobble", parts=(("leaf.n3pmesh", ("l0.dxt", "l1.dxt"), 4.0, ko_shapes.RF_WOBBLE),)),
    dict(label="falls", parts=(("falls.n3pmesh", ("w0.dxt", "w1.dxt", "w2.dxt"), 10.0, 0x3, 1.0, (2, 2)),
                               ("rock.n3pmesh", ("rock.dxt",), 10.0, ko_shapes.RF_BOARD_Y))),
    dict(label="held", parts=(("held.n3pmesh", ("h0.dxt", "h1.dxt"), 0.0, ko_shapes.RF_BOARD_Y),)),
    dict(label="hollow falls", parts=(("", ("w0.dxt", "w1.dxt"), 10.0),)),
]
path = B / "shapes.opd"
path.write_bytes(shapes.build(shapes=spec))
placed = ko_shapes.load_shapes(path)
assert placed["parsed_bytes"] == placed["total_bytes"], "shape parse must reach EOF"
got = placed["shapes"]
assert len(got) == len(spec)
assert got[0]["name"] == "tree" and got[0]["position"] == [10.0, 1.0, 20.0]
assert got[0]["parts"][0]["mesh"] == "xmas_tree.n3pmesh"
assert got[0]["parts"][0]["textures"] == ["bark.dxt", "leaf.dxt"]
assert got[0]["parts"][0]["pivot"] == [0.5, 0.25, 0.125]
# The part's material is decoded, not skipped: `CN3SPart::Render` (FUN_00443090)
# turns RF_DOUBLESIDED into D3DCULL_NONE, so the bake has to know about it.
assert got[0]["parts"][0]["render_flags"] == 0x5
assert got[0]["parts"][0]["double_sided"] is True
assert got[0]["parts"][0]["diffuse_alpha"] == 0.5
assert got[3]["parts"][0]["double_sided"] is False, "flags must be per part"
assert got[2]["animated_keys"] == 4
assert [ko_shapes.classify(s) for s in got] == [
    "static", "event", "animated", "material_cycle", "npc", "extra", "empty",
    "event_shown", "event_shown", "event", "animated", "event", "empty",
    "event_npc_shown", "event", "event", "animated", "empty",
    "animated_material", "animated_material", "material_cycle", "static", "empty"]
assert {"static", "event_shown", "event_npc_shown", "material_cycle"} == ko_shapes.BAKED
assert [len(ko_shapes.cycling_parts(s)) for s in got[-5:]] == [1, 1, 1, 0, 1]

# Bounds are enforced on the record fields too.
for bad in (dict(label="x" * 300), dict(parts=tuple(("m", (), 0.0) for _ in range(2000)))):
    try:
        bad_path = B / "bad.opd"
        bad_path.write_bytes(shapes.build(shapes=[dict(spec[0], **bad)]))
        ko_shapes.load_shapes(bad_path)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted an out-of-range shape record")
print("PASS OPD shape records: transform, parts, materials, textures, event/NPC fields, classification "
      "(PQ-412: a static shape cycling without RF_BOARD_Y or RF_WOBBLE is material_cycle)")

if opd.exists():
    real = ko_shapes.load_shapes(opd)
    assert real["parsed_bytes"] == real["total_bytes"], (
        "real shape parse left %d bytes" % (real["total_bytes"] - real["parsed_bytes"]))
    kinds = {}
    for s in real["shapes"]:
        kinds[ko_shapes.classify(s)] = kinds.get(ko_shapes.classify(s), 0) + 1
    assert kinds["static"] > 1500 and sum(kinds.values()) == len(real["shapes"])
    print("PASS real Moradon shapes: %d records parsed to exact EOF, %s"
          % (len(real["shapes"]), ", ".join("%s %d" % kv for kv in sorted(kinds.items()))))
else:
    print("SKIP real Moradon shapes: local assets absent")

# ---------------------------------------------------------------------------
# KX-04 (partial): spawn survey, verified by the engine's own solver.
import ko_survey

# Fail-closed behaviour on a surface with nowhere to stand: a wall of object
# geometry over every candidate must yield no spawn rather than a guess.
flat = {"width": 33, "depth": 33, "origin": [-64.0, 0.0, -64.0], "spacing": 4.0,
        "diagonal": "alternating-mirrored", "heights": [0.0] * (33 * 33)}
assert ko_survey.candidates(flat, []) != [], "an open plain must offer candidates"
blocked = []
for gz in range(0, 33):
    for gx in range(0, 33):
        x, z = -64.0 + gx * 4.0, -64.0 + gz * 4.0
        blocked.append([[x - 2, 0.0, z - 2], [x + 2, 0.0, z + 2], [x - 2, 3.0, z - 2]])
assert ko_survey.candidates(flat, blocked) == [], "capsule blocking must reject"
steep = dict(flat, heights=[(i % 33) * 40.0 for i in range(33 * 33)])
assert ko_survey.candidates(steep, []) == [], "slope must reject"
print("PASS spawn pre-filter: open plain accepted, capsule blocking and slope rejected")

if gtd.exists() and opd.exists():
    found, tri = ko_survey.survey(gtd, opd, B / "survey", limit=24)
    spawn = found["spawn"]
    assert spawn is not None, "no spawn qualified on Moradon"
    assert found["pre_filtered"] > 50 and found["engine_checked"] == 24
    # The engine must move it in every direction and bring it back.
    assert spawn["min_away"] > 0.4 and spawn["worst_return"] < 0.4
    assert len(spawn["directions"]) == 4
    # Both solvers must agree at the chosen coordinate, not just the C++ one.
    scratch = B / "survey" / "cross.txt"
    s = spawn["position"]
    moves = [(1, 0)] * 10 + [(-1, 0)] * 10
    scratch.write_text(" ".join(map(str, [len(tri)] + [v for t in tri for v in t]
                                   + list(s) + [v for p in moves for v in p])) + "\n")
    both = []
    for cmd in (["build/client/n3e-walk-check", str(scratch)],
                ["target/debug/n3e-server", "--walk-fixture", str(scratch)]):
        done = subprocess.run(cmd, check=True, capture_output=True, text=True)
        both.append([list(map(float, l.split())) for l in done.stdout.splitlines()])
    delta = max(abs(a - b) for u, v in zip(*both) for a, b in zip(u, v))
    assert delta < 1e-6, "solvers disagree at the surveyed spawn: %g" % delta
    # The map centre must still be rejected, which is why a survey is needed.
    centre = ko_survey.verify(tri, [0.0, flat["heights"][0], 0.0], scratch)
    assert not centre["open"], "the map centre unexpectedly qualified"
    # PQ-217: near a start area the survey's crop answers as the whole map does.
    area = (s[0] - 6, s[2] - 6, s[0] + 6, s[2] + 6)
    local = ko_survey.crop(tri, area)
    assert 0 < len(local) < len(tri) // 4, (len(local), len(tri))
    near = ko_survey.area_candidates(tri, area)
    assert near and near == ko_survey.area_candidates(local, area)
    for point in [c["position"] for c in near[:3]] + [[s[0], s[1] - 0.1, s[2]]]:
        assert ko_survey.verify(local, point, scratch) == ko_survey.verify(tri, point, scratch), point
    print("PASS Moradon crop: %d of %d collision points around the spawn give the same "
          "candidates and engine walks as the whole map" % (len(local), len(tri)))
    print("PASS Moradon spawn: %d pre-filtered, engine-verified at [%.0f, %.2f, %.0f], "
          "solvers agree %.1e, centre still rejected"
          % (found["pre_filtered"], s[0], s[1], s[2], delta))
else:
    print("SKIP Moradon spawn survey: local assets absent")

# ---------------------------------------------------------------------------
# Level of detail: progressive meshes are flattened to maximum detail.
import ko as ko_mesh


def pmesh(splits=(), lods=0, trailing=b"", vertices=3, indices=3,
          min_vertices=None, min_indices=None, index_changes=None):
    """One PMesh image. `splits` is the edge-collapse list, in file order.

    Each split is `(indices_to_lose, change_positions, vertices_to_lose)`, the
    fields `CN3PMeshInstance::SplitOne` (`FUN_00441b20`) consumes; the change
    positions are flattened into the shared index-change table and referenced by
    offset, as the format does.
    """
    changes, records = [], []
    for lose_i, positions, lose_v in splits:
        records.append((lose_i, len(positions), lose_v, len(changes), 0))
        changes.extend(positions)
    if index_changes is not None:
        changes = list(index_changes)
    grown_v = sum(r[2] for r in records)
    grown_i = sum(r[0] for r in records)
    min_vertices = vertices - grown_v if min_vertices is None else min_vertices
    min_indices = indices - grown_i if min_indices is None else min_indices
    body = struct.pack("<i", 0)  # empty name
    body += struct.pack("<6i", len(records), len(changes), vertices, indices,
                        min_vertices, min_indices)
    for i in range(vertices):
        body += struct.pack("<8f", float(i), 0.0, float(i), 0.0, 1.0, 0.0, 0.0, 0.0)
    body += b"".join(struct.pack("<H", i % max(1, min_vertices))
                     for i in range(indices))
    for lose_i, change_count, lose_v, first, collapse_to in records:
        body += struct.pack("<5i", lose_i, change_count, lose_v, first, collapse_to)
        body += b"\x01" + b"\0" * 3  # bool bShouldCollapse, padded to 24
    body += b"".join(struct.pack("<i", c) for c in changes)
    body += struct.pack("<i", lods) + b"".join(struct.pack("<fi", float(j*20), max(min_vertices, vertices-j)) for j in range(lods))
    return body + trailing


mesh_path = B / "probe.n3pmesh"
mesh_path.write_bytes(pmesh())
plain = ko_mesh.import_mesh(mesh_path, 1.0)
assert plain["progressive"] is False and plain["lod_control_values"] == 0
assert plain["indices"] == [0, 2, 1], plain["indices"]

# A progressive mesh is stored at its LOWEST detail. Reading the index array as
# it lies gives the maximum triangle count wired to collapsed vertices — torn,
# hole-ridden geometry. The splits have to be replayed.
#   stored: 3 vertices, 3 of the 9 indices live, all reading 0,1,2
#   split 0: +3 indices, +1 vertex, rewrite position 1 to vertex 3
#   split 1: +3 indices, +1 vertex, rewrite positions 4 and 7 to vertex 4
refined = pmesh(vertices=5, indices=9,
                splits=((3, (1,), 1), (3, (4, 7), 1)), lods=3)
mesh_path.write_bytes(refined)
rich = ko_mesh.import_mesh(mesh_path, 1.0)
assert rich["progressive"] is True and rich["lod_control_values"] == 3
# File order is 0,1,2 repeated; the splits rewrite three of those positions,
# and the winding swap then exchanges the second and third of each triangle.
assert rich["indices"] == [0, 2, 3, 0, 2, 4, 0, 2, 4], rich["indices"]
assert any("minimum level of detail" in w for w in rich["warnings"])
assert not any("minimum level of detail" in w for w in plain["warnings"])

# Reaching exactly the declared maxima is what proves the collapse stride and
# field order; a record layout that does not land on both totals is rejected.
for reason, kw in [
    ("splits that do not reach the maximum",
     dict(vertices=5, indices=9, splits=((3, (1,), 1),), min_vertices=3,
          min_indices=3)),
    ("a split beyond the declared maximum",
     dict(vertices=4, indices=6, splits=((3, (1,), 1), (3, (4,), 1)),
          min_vertices=4, min_indices=6)),
    ("an index-change position outside the index array",
     dict(vertices=4, indices=6, splits=((3, (99,), 1),))),
    ("trailing data", dict(vertices=5, indices=9,
                           splits=((3, (1,), 1), (3, (4, 7), 1)), lods=3,
                           trailing=b"\x00")),
]:
    mesh_path.write_bytes(pmesh(**kw))
    try:
        ko_mesh.import_mesh(mesh_path, 1.0)
    except ValueError:
        continue
    raise AssertionError("accepted a malformed progressive mesh: " + reason)
print("PASS progressive mesh: splits replayed from the stored minimum detail, "
      "declared maxima reached, malformed records rejected")

if opd.exists():
    objects = Path("assets/ko/Object")
    index = {f.name.lower(): f for f in objects.iterdir() if f.is_file()}
    placed = ko_shapes.load_shapes(opd)["shapes"]
    names = sorted({p["mesh"] for s in placed for p in s["parts"] if p["mesh"]})
    read = sum(1 for n in names if n.split("\\")[-1].lower() in index
               and ko_mesh.import_mesh(index[n.split("\\")[-1].lower()], 1.0))
    assert read == len(names), "only %d of %d placed meshes read" % (read, len(names))
    print("PASS every one of the %d placed Moradon meshes now reads at max detail" % read)
else:
    print("SKIP placed Moradon meshes: local assets absent")

# ---------------------------------------------------------------------------
# KX-02 texturing: the tile files behind the terrain surface.
import ko_tiles, ko_tiles_fixture as tiles_fixture

# A GTT has no index: an ordinal means "skip that many textures". Selectively
# decoding one tile must produce exactly what a full walk produces, which is
# what proves the skip stride from `CN3Texture::SkipFileHandle` (FUN_0043f7e0).
gtt = tiles_fixture.gtt(count=5)
every = ko_tiles.tiles(gtt)
assert sorted(every) == [0, 1, 2, 3, 4]
for ordinal in (0, 2, 4):
    picked = ko_tiles.tiles(gtt, {ordinal})
    assert list(picked) == [ordinal]
    assert picked[ordinal] == every[ordinal], ordinal
# Different seeds per ordinal, so a stride error would silently return a
# neighbour rather than failing; this catches that.
assert len({bytes(v[2]) for v in every.values()}) == 5

# DXT1 keeps its one-bit alpha instead of being refused, and DXT3 carries the
# explicit alpha nibble. Foliage and the partial terrain tiles need both.
punch = ko_tiles.texture(tiles_fixture.texture(seed=1))
assert punch[2][3::4].count(0) > 0, "punch-through DXT1 must produce alpha 0"
opaque = ko_tiles.texture(tiles_fixture.texture(seed=0))
assert set(opaque[2][3::4]) == {255}, "opaque DXT1 must stay opaque"
graded = ko_tiles.texture(tiles_fixture.texture(fmt=ko_tiles.DXT3))
assert graded[2][3] == 255 and graded[2][7] == 238, "DXT3 alpha ramp"

# A mip level at least as large as the atlas cell is used rather than the base,
# so an atlas keeps the reference's own filtered pixels.
assert ko_tiles.texture(tiles_fixture.texture(32, 32), 8)[:2] == (8, 8)
assert ko_tiles.texture(tiles_fixture.texture(32, 32), 64)[:2] == (32, 32)
assert ko_tiles.texture(tiles_fixture.texture(32, 32))[:2] == (32, 32)

for reason, blob in [
    ("bad magic", b"\x00\x00\x00\x00NTX\x03" + struct.pack("<4i", 8, 8, ko_tiles.DXT1, 1)),
    ("unsupported format", b"\x00\x00\x00\x00NTF\x03" + struct.pack("<4i", 8, 8, 0x35545844, 1)),
    ("non power of two", b"\x00\x00\x00\x00NTF\x03" + struct.pack("<4i", 12, 8, ko_tiles.DXT1, 1)),
    ("truncated", tiles_fixture.texture()[:-8]),
]:
    try:
        ko_tiles.texture(blob)
    except ValueError:
        continue
    raise AssertionError("accepted an invalid KO texture: " + reason)
print("PASS GTT ordinals and skip stride, DXT1 alpha, DXT3 alpha, mip selection, texture rejections")


# ---------------------------------------------------------------------------
# The quad diagonal, checked against the reference height function rather than
# against our own restatement of it.
def reference_height(heights, samples, x, z, tile=4.0):
    """`CN3Terrain::GetHeight` (FUN_0059d330), in reference map coordinates.

    MAPDATA is x-major and `ko_terrain` transposes on import, so the sample at
    reference (x, z) is `heights[z * samples + x]` here. The parity test is the
    binary's `(ix + iz) & 0x80000001`; each branch interpolates within the
    triangle that parity selects.
    """
    ix, iz = int(x // tile), int(z // tile)
    if not (0 <= ix <= samples - 2 and 0 <= iz <= samples - 2):
        return None
    fx, fz = (x - ix * tile) / tile, (z - iz * tile) / tile
    at = lambda a, b: heights[b * samples + a]
    if (ix + iz) % 2 == 0:
        h00, h11 = at(ix, iz), at(ix + 1, iz + 1)
        if fx < fz:
            edge = (at(ix, iz + 1) - h00) * fz + h00
            return (fx / fz) * (((h11 - h00) * fz + h00) - edge) + edge
        if fx != 0.0:
            edge = (at(ix + 1, iz) - h00) * fx + h00
            return (fz / fx) * (((h11 - h00) * fx + h00) - edge) + edge
        return h00
    h10, h01 = at(ix + 1, iz), at(ix, iz + 1)
    if fz + fx <= 1.0:
        if fx == 1.0:
            return h10
        h00 = at(ix, iz)
        near = (h10 - h00) * fx + h00
        far = (h10 - h01) * fx + h01
        return (far - near) * (fz / (1.0 - fx)) + near
    if fz == 0.0:
        return h10
    h11 = at(ix + 1, iz + 1)
    near = (h11 - h10) * fz + h10
    far = (h01 - h10) * fz + h10
    return ((1.0 - fx) / fz) * (far - near) + near


def surface_height(triangles, x, z):
    """Highest cooked triangle over (x, z), the way the engine samples ground."""
    best = None
    for i in range(0, len(triangles), 3):
        a, b, c = triangles[i], triangles[i + 1], triangles[i + 2]
        det = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(det) < 1e-9:
            continue
        u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / det
        v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / det
        if u >= -1e-9 and v >= -1e-9 and u + v <= 1 + 1e-9:
            h = u * a[1] + v * b[1] + (1 - u - v) * c[1]
            best = h if best is None else max(best, h)
    return best


def diagonal_agrees(gtd_path, probes):
    """Sample the cooked surface against the reference function."""
    source = ko_terrain.load(gtd_path)
    height, _, _ = ko_bake.bake(gtd_path, B / "diagonal.opd")
    surface = main.heightfield_triangles(height)
    extent = (source["samples"] - 1) * source["spacing"]
    half = extent / 2.0
    worst = 0.0
    for rx, rz in probes:
        want = reference_height(source["heights"], source["samples"], rx, rz)
        assert want is not None, (rx, rz)
        # Reference (x, z) -> package coordinates: centred, with z mirrored.
        got = surface_height(surface, rx - half, half - rz)
        assert got is not None, (rx, rz)
        worst = max(worst, abs(got - want))
    return worst


# The bake needs matching object extents, so give it a minimal OPD of the same
# size as the fixture terrain.
(B / "diagonal.opd").write_bytes(shapes.build(width=64.0, depth=64.0))
probes = [(x + 0.7, z + 2.9) for x in range(0, 60, 4) for z in range(0, 60, 4)]
probes += [(x + 3.3, z + 1.1) for x in range(0, 60, 4) for z in range(0, 60, 4)]
worst = diagonal_agrees(B / "bake.gtd", probes)
assert worst < 1e-4, (
    "the cooked surface disagrees with CN3Terrain::GetHeight by %g m; the quad "
    "diagonal phase is wrong" % worst)
# And the wrong phase must actually be detectable, or the check proves nothing.
plain = ko_terrain.load(B / "bake.gtd")
flipped = ko_bake.bake(B / "bake.gtd", B / "diagonal.opd")[0]
flipped["diagonal"] = "alternating"
flipped_surface = main.heightfield_triangles(flipped)
half = (plain["samples"] - 1) * plain["spacing"] / 2.0
mistaken = max(
    abs(surface_height(flipped_surface, rx - half, half - rz)
        - reference_height(plain["heights"], plain["samples"], rx, rz))
    for rx, rz in probes)
assert mistaken > 1e-3, "the probe set cannot tell the two phases apart"
print("PASS quad diagonal matches CN3Terrain::GetHeight within %.1e m "
      "(wrong phase differs by %.2f m)" % (worst, mistaken))


# ---------------------------------------------------------------------------
# KX-02: the drawn map, built from the same fixtures. The surface the player
# sees must be the surface the server collides against, tile for tile.
import ko_scene
import ko

WORLD_SAMPLES = 17
world_assets = B / "world-assets"
shutil.rmtree(world_assets, ignore_errors=True)
(world_assets / "DTex").mkdir(parents=True)
(world_assets / "Object").mkdir(parents=True)
for name, count in (("original_a.gtt", 4), ("original_b.gtt", 4)):
    (world_assets / "DTex" / name).write_bytes(tiles_fixture.gtt(count=count))
# Enough references that every fixture tile index resolves, cycling over the
# eight distinct (file, ordinal) pairs the two files hold. Distinct indices
# naming the same pair must share one atlas slot.
world_refs = tuple((i % 2, (i // 2) % 4) for i in range(1024))
world_gtd = B / "world.gtd"
world_gtd.write_bytes(fixture.build(samples=WORLD_SAMPLES, references=world_refs))
(world_assets / "Object" / "probe.n3pmesh").write_bytes(pmesh(vertices=3, indices=3))
(world_assets / "Object" / "probe.dxt").write_bytes(tiles_fixture.texture())
world_opd = B / "world.opd"
world_opd.write_bytes(shapes.build(width=64.0, depth=64.0, shapes=[
    dict(label="probe", position=(10.0, 1.0, 20.0),
         parts=(("probe.n3pmesh", ("probe.dxt",), 0.0),)),
    dict(label="both", position=(20.0, 1.0, 20.0),
         parts=(("probe.n3pmesh", ("probe.dxt",), 0.0,
                 ko_shapes.RF_DOUBLESIDED),)),
]))

world_height, _, _ = ko_bake.bake(world_gtd, world_opd)
built = ko_scene.expand(world_gtd, world_opd, world_assets, world_height)
report = built["report"]
quads = (WORLD_SAMPLES - 1) ** 2
assert report["terrain"]["tiles"] == quads
# Four unshared vertices and two triangles per tile, as FUN_005a0410 builds it.
assert report["terrain_vertices"] == quads * 4
assert report["terrain_triangles"] == quads * 2
# Eight distinct tile images behind 1024 reference indices, plus the one object
# texture: indices that name the same (file, ordinal) must share an atlas slot.
assert report["atlas"]["decoded"] == 9, report["atlas"]
assert report["terrain"]["tile_textures_missing"] == 0
assert report["terrain"]["tiles_blended"] == quads, "every fixture tile has a second layer"
assert report["objects"]["placements"] == 2 and report["objects"]["skipped_parts"] == 0
assert report["objects"]["double_sided_parts"] == 1

# The drawn triangles must be exactly the cooked collision surface. Anything
# else means the player stands on a different shape from the one they see.
drawn = []
for t in range(0, len(built["indices"]), 3):
    drawn.append(tuple(sorted(
        tuple(round(c, 6) for c in built["vertices"][built["indices"][t + k]][:3])
        for k in range(3))))
drawn = drawn[:quads * 2]
cooked = main.heightfield_triangles(world_height)
expected = [tuple(sorted(tuple(round(c, 6) for c in p)
                         for p in cooked[i:i + 3]))
            for i in range(0, len(cooked), 3)]
assert sorted(drawn) == sorted(expected), "drawn terrain is not the collision surface"

# Winding stays upward after the z mirror, or the ground is backface-culled.
for t in range(0, quads * 6, 3):
    a, b, c = (built["vertices"][built["indices"][t + k]][:3] for k in range(3))
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    assert ab[2] * ac[0] - ab[0] * ac[2] > 0, "terrain triangle faces down"

# A double-sided part is emitted with both faces, because the world pass culls
# backfaces like any other geometry and the reference instead drops culling for
# exactly these materials.
object_indices = len(built["indices"]) - quads * 6
one_sided = len(ko.import_mesh(world_assets / "Object" / "probe.n3pmesh", 1.0)["indices"])
assert object_indices == one_sided * 3, (object_indices, one_sided)
face = built["indices"][quads * 6:quads * 6 + 3]
backs = built["indices"][quads * 6 + one_sided:]
assert list(backs[:3]) != list(face), "the back face must not repeat the front"
for t in range(0, one_sided, 3):
    front = list(built["indices"][quads * 6 + one_sided + t:][:3])
    back = list(built["indices"][quads * 6 + one_sided * 2 + t:][:3])
    assert back == front[::-1], (front, back)

# Direction UVs: a tile's four corners must cover its whole cell, and both
# layers must name a real atlas slot.
corner_uv = [tuple(built["vertices"][i][6:8]) for i in range(4)]
assert sorted(corner_uv) == [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)], corner_uv
objects = built["vertices"][report["terrain_vertices"]:]
assert all(v[11] == float(ko_scene.CLEAR) for v in objects), (
    "object vertices must point their second layer at the transparent slot")
assert all(v[10] != float(ko_scene.CLEAR) for v in objects), "objects are textured"
for v in built["vertices"]:
    for slot in v[10:12]:
        assert slot == int(slot) and 0 <= slot < ko_scene.SLOTS, slot

# Object UVs are kept as authored, including the ones past 1: the client tiles
# inside the cell, and wrapping per vertex would tear every triangle that
# crosses a tile boundary.
probe = ko.import_mesh(world_assets / "Object" / "probe.n3pmesh", 1.0)
authored = sorted(tuple(v[6:8]) for v in probe["vertices"])
assert sorted(tuple(v[6:8]) for v in objects[:len(probe["vertices"])]) == authored

# Serialisation round-trips through the engine's own reader.
blob = ko_scene.world_bytes(built)
assert blob[:4] == b"N3W1"
assert struct.unpack_from("<IIII", blob, 4) == (
    ko_scene.ATLAS, ko_scene.ATLAS, ko_scene.CELL, ko_scene.PAD)
print("PASS drawn map: four vertices per tile, shared atlas slots, drawn surface "
      "equals the collision surface, upward winding, cleared second layer")

# ---------------------------------------------------------------------------
# PQ-216: a zone is chosen by its Zones.tbl key. The client's world loader
# (005a3110) reads the row's column 2 GTD, column 4 colour map and column 6 OPD,
# compares both internal names with column 3 ignoring case (lstrcmpiA), loads an
# OPDEXT only when column 7 is not exactly "Reserved" (005a32c6), and releases the
# map on a mismatch ("Invalid Map Files"). Original synthetic rows and files only.
import csv
import ko_lod
import ko_zone

zone_root = B / "zone-client"
shutil.rmtree(zone_root, ignore_errors=True)
(zone_root / "Data").mkdir(parents=True)
(zone_root / "Zones").mkdir()
# Lower-case files on disk; the table names them in mixed case, some with the
# trailing space real rows carry, and the internal names differ in case only.
(zone_root / "Zones" / "orig_vale.gtd").write_bytes(fixture.build(name="Orig_Vale"))
(zone_root / "Zones" / "orig_vale.opd").write_bytes(shapes.build(name="ORIG_VALE"))
(zone_root / "Zones" / "orig_vale.tct").write_bytes(tiles_fixture.gtt(count=1))
(zone_root / "Zones" / "orig_vale.dxt").write_bytes(tiles_fixture.texture())
# PQ-387: column 5's light maps; ko_zone only resolves it (the overlay is
# tests/world_overlay.py's). A version and an empty patch table.
(zone_root / "Zones" / "orig_vale.tlt").write_bytes(bytes(8))
(zone_root / "Zones" / "other.opd").write_bytes(shapes.build(name="other_place"))
# PQ-229: OPDEXT files (005b4ef0): a nameless one, one that renames the shape
# manager, one that renames it to column 3, and a malformed one.
import ko_opdext, ko_opdext_fixture as opdext_fixture
(zone_root / "Zones" / "orig_vale.opdext").write_bytes(opdext_fixture.build())
(zone_root / "Zones" / "renamed.opdext").write_bytes(opdext_fixture.build(name="elsewhere"))
(zone_root / "Zones" / "fixing.opdext").write_bytes(opdext_fixture.build(name="Orig_Vale"))
(zone_root / "Zones" / "broken.opdext").write_bytes(opdext_fixture.build(version=2))
# A case-sensitive disk can hold two files a Windows path cannot tell apart.
(zone_root / "Zones" / "twin.gtd").write_bytes(fixture.build(name="Orig_Vale"))
(zone_root / "Zones" / "Twin.gtd").write_bytes(fixture.build(name="Orig_Vale"))


def zone_row(key, gtd="Zones\\Orig_Vale.GTD ", name="orig_vale", opd="Zones\\Orig_Vale.opd",
             opdext="Reserved"):
    return ([str(key), gtd, name, "Zones\\ORIG_VALE.tct ", "Zones\\Orig_Vale.tlt", opd, opdext,
             "Zones\\Orig_Vale.dxt "] + ["empty"] * 16)


zone_rows = [["1 - UInt32"] + ["%d - String" % c for c in range(2, 25)],
             zone_row(7010),
             zone_row(7020, opd="Zones\\other.opd"),        # OPD named other_place
             zone_row(7030, name="other_vale"),              # neither name matches
             zone_row(7040, opdext="Zones\\Orig_Vale.OPDEXT"),
             zone_row(7041, opdext="reserved"),              # the compare is exact
             zone_row(7042, opdext="Zones\\renamed.opdext"),  # renames the objects
             zone_row(7043, opd="Zones\\other.opd", opdext="Zones\\fixing.opdext"),
             zone_row(7044, opdext="Zones\\broken.opdext"),
             zone_row(7045, opdext="Zones\\fixing.opdext"),
             zone_row(7050, gtd="..\\escape.gtd"),
             zone_row(7060, gtd="Zones\\missing.gtd"),
             zone_row(7080, gtd="Zones\\TWIN.gtd"),       # two files differ in case only
             zone_row(7070), zone_row(7070)]
with (zone_root / "Data" / "Zones.tbl.csv").open("w", newline="", encoding="utf-8") as handle:
    csv.writer(handle).writerows(zone_rows)

picked = ko_zone.select(zone_root, 7010)
for kind, suffix in (("gtd", "gtd"), ("tct", "tct"), ("opd", "opd"), ("minimap", "dxt")):
    assert picked[kind] == zone_root / "Zones" / ("orig_vale." + suffix), (kind, picked[kind])
assert picked["names"] == {"gtd": "Orig_Vale", "opd": "ORIG_VALE"}, picked["names"]
assert picked["tlt"] == zone_root / "Zones" / "orig_vale.tlt", picked["tlt"]
assert picked["provenance"]["light_maps"]["column"] == "5", picked["provenance"]
assert picked["row"][0] == "7010" and picked["provenance"]["opdext"].startswith("skipped")


def zone_refused(key, phrase):
    try:
        ko_zone.select(zone_root, key)
    except ValueError as error:
        assert phrase in str(error), error
        return str(error)
    raise AssertionError("zone %d was accepted" % key)


bad_opd = zone_refused(7020, "Invalid Map Files")
assert "other.opd" in bad_opd and "orig_vale.gtd" not in bad_opd, bad_opd
bad_both = zone_refused(7030, "Invalid Map Files")
assert "orig_vale.gtd" in bad_both and "orig_vale.opd" in bad_both, bad_both
# Column 7 names an OPDEXT: it is read against the OPD, merged, and the shape
# manager's name is checked against column 3 again (005a3329-005a3396).
with_ext = ko_zone.select(zone_root, 7040)
assert with_ext["opdext"] == zone_root / "Zones" / "orig_vale.opdext"
assert with_ext["names"] == picked["names"]
ext_record = with_ext["provenance"]["opdext"]
assert ext_record["format"] == "N3 OPDEXT version 1" and ext_record["effective_name"] == "ORIG_VALE"
assert ext_record["extension_faces"] == 3 and ext_record["created_cells"] == 1
assert ext_record["reflagged_cells"] == 1 and ext_record["face_threshold"] == 4
assert with_ext["provenance"]["files"]["opdext"].endswith("orig_vale.opdext")
assert with_ext["extension"]["merged"]["baked_faces"] == 6  # the OPD's faces only
assert "opdext" not in picked["provenance"]["files"]
zone_refused(7041, "not a local file")  # 'reserved' is a file name, and none exists
renamed = zone_refused(7042, "Invalid Map Files")
assert "is named 'elsewhere' after" in renamed and "orig_vale.gtd" not in renamed, renamed
# The OPD's own mismatch is appended before the OPDEXT loads; renaming afterwards
# does not clear it.
still_bad = zone_refused(7043, "Invalid Map Files")
assert "other.opd is named 'other_place'" in still_bad and "after" not in still_bad, still_bad
zone_refused(7044, "OPDEXT version 2")
assert ko_zone.select(zone_root, 7045)["provenance"]["opdext"]["effective_name"] == "Orig_Vale"
zone_refused(7050, "not a relative client path")
zone_refused(7060, "not a local file")
assert "TWIN.gtd" in zone_refused(7080, "is ambiguous")  # PQ-217: never pick one of two
zone_refused(7070, "2 rows")
zone_refused(7999, "no row for zone key 7999")
# The name check reads only the header, so it still answers for a map that the
# sample cap then refuses. PQ-234: the cap binds the N3W1 path (and the spawn
# survey); the chunked bake reads up to N3C2's 513 samples, chosen by the
# header's sample count.
over_cap = zone_root / "Zones" / "over_cap.gtd"
over_cap.write_bytes(fixture.build(samples=ko_terrain.MAX_SUPPORTED_SAMPLES + 8, name="Over_Cap"))
assert ko_terrain.header_name(over_cap) == "Over_Cap"
assert ko_terrain.header_samples(over_cap) == 137
try:
    ko_terrain.load(over_cap)
except ValueError as error:
    assert "129-sample" in str(error), error
else:
    raise AssertionError("the N3W1 sample cap moved")
assert ko_terrain.load(over_cap, ko_terrain.CHUNKED_MAX_SAMPLES)["samples"] == 137
assert ko_terrain.CHUNKED_MAX_SAMPLES == main.COLLISION_MAX_SAMPLES
past_chunked = zone_root / "Zones" / "past_chunked.gtd"
past_chunked.write_bytes(fixture.build(samples=ko_terrain.CHUNKED_MAX_SAMPLES + 8, name="Past"))
for bound, reason in ((ko_terrain.CHUNKED_MAX_SAMPLES, "513-sample"), (1024, "GTD sample bound")):
    try:
        ko_terrain.load(past_chunked, bound)
    except ValueError as error:
        assert reason in str(error), (reason, error)
        continue
    raise AssertionError("loaded a 521-sample GTD with bound %d" % bound)

# PQ-234: a map that fits N3W1 keeps the N3W1 + N3L3 bake, byte for byte what
# ko_scene writes for it; the chunked bake of the same map is N3W2 + N3WT whose
# slot table and N3WT agree. (tests/ko_world_live.py bakes the 513-sample and
# overflowing maps and draws them; Moradon's pins are tests/ko_bake_pin.py.)
import ko_large_zone_fixture as large_zone
import world_textures
import world_chunks
small_zone = large_zone.write(B / "pq234-zone", samples=33)
small = ko_scene.bake_world(small_zone["gtd"], small_zone["opd"], small_zone["assets"], small_zone["tct"])
assert not small["chunked"] and small["textures"] is None and "n3w1_refused" not in small["report"]
direct = ko_scene.expand(small_zone["gtd"], small_zone["opd"], small_zone["assets"], small["heightfield"],
                         detail=True, color_map=small_zone["tct"])
assert small["world"] == ko_scene.world_bytes(direct) and small["lod"] == ko_scene.lod_bytes(direct)
chunked = ko_scene.expand(small_zone["gtd"], small_zone["opd"], small_zone["assets"], small["heightfield"],
                          detail=True, color_map=small_zone["tct"], chunked=True)
assert chunked["atlas"] is None and chunked["texture_slots"] == direct["texture_slots"]
assert chunked["vertices"] == direct["vertices"] and len(chunked["chunks"]) == len(direct["chunks"])
n3w2 = ko_scene.world2_bytes(chunked)
n3wt, n3wt_report = ko_scene.world_textures_bytes(small_zone["assets"], chunked)
# PQ-382 (D-202): the zone's opaque object parts set bit 5, so the chunked world is N3W4.
assert n3w2[:4] == b"N3W4" and struct.unpack_from("<I", n3w2, 4)[0] == chunked["texture_count"]
assert world_textures.check(n3wt)[0] == chunked["texture_count"] == 1 + 8 + 1 + 2, n3wt_report
# Render detail's world subset is the N3W1 world's textures; with N3W2 it is
# the transparent slot alone, the world's own are in N3WT.
assert ko_scene.world_chains(small_zone["assets"], direct)[0] == ko_scene.world_chains(
    small_zone["assets"], chunked)[0]
try:
    ko_scene.world2_bytes(direct)
except ValueError as error:
    assert "chunked build" in str(error), error
else:
    raise AssertionError("wrote an atlas build as N3W2")

# PQ-384: 1298 draws a near tile from its patch's colour map when tex1 is not
# below the tile-texture count (005a2825) or its full bit is clear (005a2832):
# stage 0 the colour map (005a29f2) with 005a0410's colour-map UVs, no tex2.
# n3e used to give such a tile the transparent slot, which the alpha cut
# removed. The fixture keeps 1000 of its 1024 references, so tex1 1000..1023
# is not a tile texture (1000 is the count itself: 005a2640 draws it from the
# colour map, but 005a0410 tests count < tex1 and gives it the direction UVs),
# and its every odd tile has the full bit clear.
COUNT = 1000
holes_zone = large_zone.write(B / "pq384-zone", samples=33)
holes_zone["gtd"].write_bytes(fixture.build(
    samples=33, name="orig_large_zone", sources=tuple("DTex/" + f for f in large_zone.TILE_FILES),
    references=large_zone.REFERENCES[:COUNT], surface=large_zone.surface))
holes_gtd = ko_terrain.load(holes_zone["gtd"])
holes = ko_scene.bake_world(holes_zone["gtd"], holes_zone["opd"], holes_zone["assets"], holes_zone["tct"])
# PQ-388 (D-203): its colour-map tiles without the multiplying pass are
# single-layer unlit vertices, which only N3W5 carries, so the map that fits
# N3W1 is baked chunked (below).
assert holes["chunked"] and holes["report"]["n3w1_refused"] == "single-layer unlit vertices need N3W5", holes["report"]
holes_chunked = holes["built"]
holes_flat = ko_scene.expand(holes_zone["gtd"], holes_zone["opd"], holes_zone["assets"], holes["heightfield"],
                             detail=True, color_map=holes_zone["tct"])
slots = holes_flat["texture_slots"]
assert holes_chunked["texture_slots"] == slots
colour_slots = {key[1]: slot for key, slot in slots.items() if key[0] == "color-map"}
assert len(colour_slots) == 1, colour_slots  # 33 samples: one 32-tile region
# The colour map is placed after every tile and object texture, so the slots
# every other map already had keep their numbers.
assert min(colour_slots.values()) > max(s for k, s in slots.items() if k[0] != "color-map")
# The UVs, from 005a0410's constants (006a8320 3.9375, 006a3a64 1, 006a831c
# 1/128, 006a8318 126, 006a8314 4.9375, 006a8310 1/32), worked by hand: the
# far edge converts the converted near edge again.
assert ko_lod.near_color_uv(0, 0) == [(0.0078125, 0.9921875), (0.0078125, 0.95373535156250),
                                      (0.0462646484375, 0.95373535156250), (0.0462646484375, 0.9921875)]
assert ko_lod.near_color_uv(63, 33)[0] == ((31 * 3.9375 + 1) / 128, (31 * 3.9375 + 1) / 128)
want = {"colour": 0, "count": 0, "tile": 0}
unlit_tiles = set()
for build in (holes_flat, holes_chunked):
    vertices = build["vertices"]
    for z in range(32):
        for x in range(32):
            tz = 31 - z  # n3e row z is reference tile row 31 - z (the bake mirrors z)
            tile = holes_gtd["tiles"][tz * 33 + x]  # ko_terrain stores reference (x, tz) at tz * 33 + x
            quad = vertices[(z * 32 + x) * 4:(z * 32 + x) * 4 + 4]
            if tile["tex1"] >= COUNT or not tile["full"]:
                kind = "count" if tile["tex1"] == COUNT and tile["full"] else "colour"
                # PQ-388: unlit unless both indices are tile textures (the
                # multiplying pass, 005a2acb-005a2b05, would light it again).
                single = not (tile["tex1"] < COUNT and tile["tex2"] < COUNT)
                second = world_chunks.UNLIT_VERTEX if single else ko_scene.CLEAR
                assert all(v[10] == colour_slots[0] and v[11] == second for v in quad), (x, z, quad)
                if single:
                    unlit_tiles.add((x, z))
                uv = [tuple(v[6:8]) for v in quad]
                if kind == "colour":
                    assert uv == ko_lod.near_color_uv(x, tz), (x, z, uv)
                else:
                    assert sorted(uv) == [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)], uv
            else:
                kind = "tile"
                assert all(v[10] not in (ko_scene.CLEAR, colour_slots[0]) for v in quad), (x, z, quad)
                assert all(v[11] != world_chunks.UNLIT_VERTEX for v in quad), (x, z, quad)
            want[kind] += 1
assert want["count"] == 2 and want["colour"] > 0 and want["tile"] > 0, want  # each counted in both builds
terrain = holes["built"]["report"]["terrain"]
assert terrain["tiles_colour_map"] == (want["colour"] + want["count"]) // 2 and terrain["tile_textures_missing"] == 0, terrain
assert holes_flat["report"]["terrain"] == terrain
# The colour map the near tile now samples is opaque, so no cut removes it
# (slot 0, the old one, is transparent everywhere).
chains = ko_scene.world_chains(holes_zone["assets"], holes_chunked)[0]
assert all(rgba[3::4] == b"\xff" * (w * h) for w, h, rgba in chains[colour_slots[0]]), "colour map alpha"
assert set(ko_scene.CLEAR_TEXTURE[0][2][3::4]) == {0}
# The coarse levels sample the same region: one colour-map slot in the whole map.
coarse = {v[10] for p in holes["built"]["chunks"] if p["kind"] == 2 for _, ix in p["levels"][1:]
          for v in (holes["built"]["vertices"][i] for i in ix)}
assert coarse == {float(colour_slots[0])}, coarse
# PQ-388: the coarse levels (the colour map MODULATE diffuse, 005a2726) stay lit.
assert all(holes["built"]["vertices"][i][11] == ko_scene.CLEAR for p in holes["built"]["chunks"] if p["kind"] == 2
           for _, ix in p["levels"][1:] for i in ix)
# Without a colour map (the terrain-only expand) a tile keeps its tex1 as before,
# and a tex1 that is not a tile texture the transparent slot, counted missing.
plain = ko_scene.expand(holes_zone["gtd"], holes_zone["opd"], holes_zone["assets"], holes["heightfield"])
invalid = [(x, 31 - tz) for tz in range(32) for x in range(32) if holes_gtd["tiles"][tz * 33 + x]["tex1"] >= COUNT]
assert plain["report"]["terrain"]["tile_textures_missing"] == len(invalid) > 0, plain["report"]["terrain"]
assert plain["report"]["terrain"]["tiles_colour_map"] == 0
assert all(v[10] == ko_scene.CLEAR for x, z in invalid for v in plain["vertices"][(z * 32 + x) * 4:(z * 32 + x) * 4 + 4])
print("PASS PQ-384 near tiles without a tile texture draw the colour map (%d with 005a0410's colour-map UVs, "
      "%d at the count with direction UVs, %d tile tiles; the flat and chunked builds agree)"
      % (want["colour"] // 2, want["count"] // 2, want["tile"] // 2))

# PQ-388 (D-203): a colour-map tile that never takes the multiplying pass (tex1
# or tex2 not a tile texture) is four single-layer unlit vertices; a tile sent
# there only by a clear full bit with both indices valid keeps the lit draw.
# The fixture has both kinds. The flat build cannot be written as N3W1, the
# chunked one is N3W5; the unlit count is in the report.
lit_colour = (want["colour"] + want["count"]) // 2 - len(unlit_tiles)
assert unlit_tiles and lit_colour > 0, (len(unlit_tiles), lit_colour)
assert terrain["tiles_unlit"] == len(unlit_tiles), terrain
assert sum(v[11] == world_chunks.UNLIT_VERTEX for v in holes_chunked["vertices"]) == 4 * len(unlit_tiles)
assert holes["world"][:4] == b"N3W5" and holes["lod"] is None
try:
    ko_scene.world_bytes(holes_flat)
except ValueError as error:
    assert "single-layer unlit" in str(error), error
else:
    raise AssertionError("wrote unlit vertices as N3W1")
# The map without such tiles keeps its N3W1 bytes (the PQ-234 block above).
assert small["built"]["report"]["terrain"]["tiles_unlit"] == 0 and small["world"][:4] == b"N3W1"
print("PASS PQ-388 near colour-map tiles without the multiplying pass are single-layer unlit (%d tiles, %d kept lit "
      "for the pass); N3W1 refused, baked as N3W5" % (len(unlit_tiles), lit_colour))

# PQ-379 (D-201): a part whose material has RF_ALPHABLENDING becomes an alpha
# part (flag bit 4) with its material's factors, its flags masked to the
# flush's own state bits, and the part matrix's translation as its sort point:
# 00443090 keys it by the eye distance to +0x68, which 004445a0 sets to the
# pivot times the shape's matrix (0041dda0). The map that fits writes N3W1 +
# N3L4, the chunked one N3W3; a part needing point sampling or clamped
# addressing is refused. Pivot (0.5, 0.25, 0.125) (ko_shapes_fixture).
alpha_zone = large_zone.write(B / "pq379-zone", samples=33)
half = (33 - 1) * 4 / 2.0
alpha_shapes = [
    dict(label="glass", position=(10.0, 1.0, 20.0), scale=(2.0, 3.0, 4.0),
         parts=(("orig_pyramid.n3pmesh", ("orig_stone_0.dxt",), 0.0,
                 ko_shapes.RF_ALPHABLENDING | ko_shapes.RF_DOUBLESIDED | ko_shapes.RF_NOTUSELIGHT),)),
    # Half a turn about y: x and z of pivot x scale change sign, whichever
    # handedness the quaternion has.
    dict(label="turned", position=(30.0, 2.0, 40.0), rotation=(0.0, 1.0, 0.0, 0.0), scale=(2.0, 3.0, 4.0),
         parts=(("orig_pyramid.n3pmesh", ("orig_stone_1.dxt",), 0.0, ko_shapes.RF_ALPHABLENDING),)),
    dict(label="solid", position=(50.0, 0.0, 50.0),
         parts=(("orig_pyramid.n3pmesh", ("orig_stone_0.dxt",), 0.0, ko_shapes.RF_DOUBLESIDED),)),
    # PQ-382: an opaque part with RF_NOTUSELIGHT (00443090 at 004432da).
    dict(label="dark", position=(60.0, 0.0, 70.0),
         parts=(("orig_pyramid.n3pmesh", ("orig_stone_1.dxt",), 0.0, ko_shapes.RF_NOTUSELIGHT),)),
]
alpha_zone["opd"].write_bytes(shapes.build(name="orig_large_zone", width=128.0, depth=128.0, shapes=alpha_shapes))
alpha_bake = ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
# PQ-382 (D-202): the opaque parts set bit 5 (cut at zero), so the files are
# N3L5 / N3W4; the alpha parts set neither opaque bit.
assert not alpha_bake["chunked"] and alpha_bake["lod"][:4] == b"N3L5" and alpha_bake["world"][:4] == b"N3W1"
alpha_parts = [p for p in alpha_bake["built"]["chunks"] if p["kind"] == 1]
assert [p["flags"] & (16 | 32 | 64) for p in alpha_parts] == [16, 16, 32, 32 | 64], [p["flags"] for p in alpha_parts]
assert alpha_bake["built"]["report"]["objects"]["alpha_parts"] == 2
assert alpha_bake["built"]["report"]["objects"]["unlit_parts"] == 1
expected = [dict(source=5, destination=6, state=0x41, point=[10 + 1 - half, 1 + 0.75, half - (20 + 0.5)]),
            dict(source=5, destination=6, state=0x1, point=[30 - 1 - half, 2 + 0.75, half - (40 - 0.5)])]
for part, want in zip(alpha_parts, expected):
    got = part["alpha"]
    assert (got["source"], got["destination"], got["state"]) == (want["source"], want["destination"], want["state"])
    assert max(abs(a - b) for a, b in zip(got["point"], want["point"])) < 1e-9, (got["point"], want["point"])
assert "alpha" not in alpha_parts[2] and "alpha" not in alpha_parts[3]
assert alpha_parts[0]["flags"] & 8 and not alpha_parts[1]["flags"] & 8 and not alpha_parts[3]["flags"] & 8
alpha_chunked = ko_scene.expand(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_bake["heightfield"],
                                detail=True, color_map=alpha_zone["tct"], chunked=True)
assert ko_scene.world2_bytes(alpha_chunked)[:4] == b"N3W4"
assert [p["flags"] & (16 | 32 | 64) for p in alpha_chunked["chunks"] if p["kind"] == 1] == [16, 16, 32, 32 | 64]
alpha_shapes[2]["parts"] = (("orig_pyramid.n3pmesh", ("orig_stone_0.dxt",), 0.0,
                             ko_shapes.RF_ALPHABLENDING | ko_shapes.RF_POINTSAMPLING),)
alpha_zone["opd"].write_bytes(shapes.build(name="orig_large_zone", width=128.0, depth=128.0, shapes=alpha_shapes))
try:
    ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
except ValueError as error:
    assert "point sampling and clamped addressing" in str(error), error
else:
    raise AssertionError("baked an alpha part with point sampling")
print("PASS KO alpha parts (PQ-379): RF_ALPHABLENDING parts carry their factors, the flush's state bits and the "
      "part matrix's translation (pivot x scale, turned, at the placement) as alpha records; "
      "point sampling is refused")
print("PASS KO opaque parts (PQ-382, D-202): every opaque part is cut at zero, an RF_NOTUSELIGHT one is unlit, "
      "alpha parts set neither bit; N3W1 + N3L5 and N3W4")

# PQ-392 (D-205): the bind points and warp gates 1298 shows at load (event types
# 0 and 5, 005b4690) are placed like static shapes, whatever their NPC fields and
# 0x1000 kind; the other event types are not. The multi-texture "magic" part is
# an alpha part with its own blend (2/2, ONE/ONE) and flags, drawn with its first
# texture: the part constructor zeroes the frame index +0x124 (004425d5) that
# 00443090 draws (004430cd). Shapes left out: an item-up (type 8) with status 0,
# which 1298's object NPC would hide (005ce49d, PQ-395), and a gate door (type 1).
magic = ("orig_pyramid.n3pmesh", ("orig_stone_1.dxt", "orig_stone_0.dxt"), 10.0,
         ko_shapes.RF_ALPHABLENDING | ko_shapes.RF_NOTUSEFOG | 0x8 | ko_shapes.RF_NOTUSELIGHT, 1.0, (2, 2))
stone = ("orig_pyramid.n3pmesh", ("orig_stone_0.dxt",), 10.0)
event_shapes = [
    dict(label="obj_bindpoint", kind=0x141b, position=(20.0, 1.0, 20.0), event_id=101, event_type=0,
         npc_status=1, parts=(stone, magic)),
    dict(label="obj_transmark", kind=0x141b, position=(60.0, 1.0, 20.0), event_id=4006, event_type=5,
         npc_id=12, npc_status=1, parts=(magic, stone)),
    dict(label="obj_itemup", kind=0x141b, position=(20.0, 1.0, 60.0), event_id=1, event_type=8, parts=(stone,)),
    dict(label="obj_gate_door", kind=0x141b, position=(60.0, 1.0, 60.0), event_id=2, event_type=1, parts=(stone,)),
    dict(label="obj_rock", position=(90.0, 1.0, 90.0), parts=(stone,)),
    # Two textures at fps 0: 004429b0 never advances its index, so it is a static
    # part drawn exactly, not a frozen cycle, and not counted as one.
    dict(label="obj_banner", position=(100.0, 1.0, 40.0),
         parts=(("orig_pyramid.n3pmesh", ("orig_stone_1.dxt", "orig_stone_0.dxt"), 0.0),)),
    # PQ-395 (D-206): the magic anvil, event type 8 with status 1 and the 0x1000
    # kind, drawn as its object NPC shows it; its fx part an unlit SRCALPHA /
    # INVSRCALPHA alpha part (0x41, 5/6) on its first texture.
    dict(label="obj_co_itemup", kind=0x141b, position=(100.0, 1.0, 100.0), event_id=5001, event_type=8,
         npc_status=1, parts=(("orig_pyramid.n3pmesh", ("orig_stone_1.dxt", "orig_stone_0.dxt"), 8.0,
                               ko_shapes.RF_ALPHABLENDING | ko_shapes.RF_NOTUSELIGHT, 1.0, (5, 6)), stone)),
]
alpha_zone["opd"].write_bytes(shapes.build(name="orig_large_zone", width=128.0, depth=128.0, shapes=event_shapes))
event_bake = ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
objects = event_bake["built"]["report"]["objects"]
assert (objects["placements"], objects["event_shapes"], objects["npc_shown_shapes"], objects["first_frame_parts"],
        objects["sequence_parts"], objects["alpha_parts"], objects["unlit_parts"],
        objects["skipped_parts"]) == (8, 2, 1, 0, 3, 3, 0, 0), objects
# PQ-394 (D-212): the three magic parts cycle, so the zone, which fits N3W1
# otherwise, is written chunked as N3W6.
assert event_bake["chunked"] and event_bake["world"][:4] == b"N3W6" and event_bake["lod"] is None
assert event_bake["report"]["n3w1_refused"] == "texture sequences need N3W6 (D-212)", event_bake["report"]
event_parts = [p for p in event_bake["built"]["chunks"] if p["kind"] == 1]
slots, vertices = event_bake["built"]["texture_slots"], event_bake["built"]["vertices"]
assert [p["parent"] for p in event_parts] == [0, 0, 1, 1, 2, 3, 4, 4], [p["parent"] for p in event_parts]
frames = [slots[("object", "orig_stone_1.dxt")], slots[("object", "orig_stone_0.dxt")]]
for part, blend, state, fps in ((event_parts[1], (2, 2), 0x41, 10.0), (event_parts[2], (2, 2), 0x41, 10.0),
                                (event_parts[6], (5, 6), 0x41, 8.0)):
    assert part["flags"] & 16 and (part["alpha"]["source"], part["alpha"]["destination"]) == blend, part
    assert part["alpha"]["state"] == state, part["alpha"]
    drawn = {vertices[part["base"] + i][10] for i in range(part["max_vertices"])}
    assert drawn == {float(frames[0])}, drawn
    # The frame textures in file order, at the part's fps (00443440 reads the
    # fps into +0xd8; 004429b0 cycles the list).
    assert part["flags"] & 128 and part["sequence"] == dict(slots=frames, fps=fps), part.get("sequence")
assert not event_parts[7]["flags"] & 16 and "alpha" not in event_parts[7]
# The 0-fps banner and every single-texture part carry no sequence.
assert [p for p in event_parts if p["flags"] & 128] == [event_parts[1], event_parts[2], event_parts[6]]
# A magic part with a frame texture that is not present keeps its first
# texture (D-205's stand-in) and no sequence; the other two still cycle.
missing_frame = [dict(shape) for shape in event_shapes]
missing_frame[1]["parts"] = ((magic[0], ("orig_stone_1.dxt", "orig_missing.dxt")) + magic[2:], stone)
alpha_zone["opd"].write_bytes(shapes.build(name="orig_large_zone", width=128.0, depth=128.0, shapes=missing_frame))
missing_bake = ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
objects = missing_bake["built"]["report"]["objects"]
assert (objects["placements"], objects["first_frame_parts"], objects["sequence_parts"]) == (8, 1, 2), objects
assert sum(1 for p in missing_bake["built"]["chunks"] if p["flags"] & 128) == 2
alpha_zone["opd"].write_bytes(shapes.build(name="orig_large_zone", width=128.0, depth=128.0, shapes=event_shapes))
# Negative control for PQ-395: with BAKED as PQ-392 left it, the anvil is not
# placed and the world differs.
ko_shapes.BAKED, kept = frozenset({"static", "event_shown"}), ko_shapes.BAKED
try:
    no_anvil = ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
finally:
    ko_shapes.BAKED = kept
objects = no_anvil["built"]["report"]["objects"]
assert (objects["placements"], objects["event_shapes"], objects["npc_shown_shapes"],
        objects["first_frame_parts"], objects["sequence_parts"]) == (6, 2, 0, 0, 2), objects
assert no_anvil["world"] != event_bake["world"]
# Negative control: with the event shapes left out of BAKED, as before PQ-392,
# only the rock and the banner are placed and no part draws a frozen first frame.
ko_shapes.BAKED, kept = frozenset({"static"}), ko_shapes.BAKED
try:
    left_out = ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
finally:
    ko_shapes.BAKED = kept
objects = left_out["built"]["report"]["objects"]
assert (objects["placements"], objects["event_shapes"], objects["first_frame_parts"],
        objects["sequence_parts"]) == (2, 0, 0, 0), objects
assert left_out["world"] != event_bake["world"] and left_out["world"] != no_anvil["world"]
# Without a sequence part the zone stays N3W1 + N3L5, as before PQ-394.
assert not left_out["chunked"] and left_out["world"][:4] == b"N3W1" and left_out["lod"][:4] == b"N3L5"
print("PASS KO texture sequences (PQ-394, D-212): the three placed magic parts carry their frame textures in file "
      "order at the part's fps, the zone is written as N3W6 (N3W1 refused for it), a 0-fps part carries none, a "
      "part with a missing frame texture keeps its first texture, and without them the zone stays N3W1 + N3L5")
print("PASS KO bind points and warp gates (PQ-392, D-205): event types 0 and 5 are placed whatever their NPC fields "
      "and 0x1000 kind, their magic part an ONE/ONE alpha part whose vertices name its first texture (its cycle's "
      "frame 0; a 0-fps multi-texture part carries no cycle); type 8 with status 0 and type 1 are not; with them left "
      "out only the static shapes are placed")
print("PASS KO magic anvil (PQ-395, D-206): a 0x1000 event type 8 shape with status 1 is placed as its object NPC "
      "shows it, its fx part a 5/6 unlit alpha part cycling from its first texture; without the 0x1000 kind, with status 0 "
      "or as type 6 it is not; with BAKED as before PQ-395 it is left out and the world differs")

# PQ-412 (D-213): a static shape whose cycling parts neither billboard nor
# wobble is placed as any static shape (1298's load keeps +0x151 = 1 without an
# event id, 00443ae0 at 00443b41; its tick and render take every part,
# 00443f40 at 00444226, 004442e0), its cycling parts with their sequences and
# its other parts by the static rules. Local shapes of each kind: a waterfall's
# ONE/ONE alpha part (1097 karus_start, 0x3), a bridge whose opaque part names
# one texture twice (1298 moradon, 0x0), a dungeon gate's fire beside four
# opaque parts (1097 moradon, 0x5). A torch (RF_BOARD_Y) and a wobbling leaf
# (RF_WOBBLE) stay out.
falls = ("orig_pyramid.n3pmesh", ("orig_stone_1.dxt", "orig_stone_0.dxt"), 10.0,
         ko_shapes.RF_ALPHABLENDING | ko_shapes.RF_NOTUSEFOG, 1.0, (2, 2))
material_shapes = [
    dict(label="obj_rock", position=(90.0, 1.0, 90.0), parts=(stone,)),
    dict(label="obj_el_falls01", position=(20.0, 1.0, 20.0), parts=(falls, stone)),
    dict(label="obj_mora_bri", position=(60.0, 1.0, 20.0),
         parts=(("orig_pyramid.n3pmesh", ("orig_stone_0.dxt", "orig_stone_0.dxt"), 10.0),)),
    dict(label="obj_torch", position=(20.0, 1.0, 60.0),
         parts=((falls[0], falls[1], 10.0, ko_shapes.RF_ALPHABLENDING | ko_shapes.RF_BOARD_Y, 1.0, (2, 2)), stone)),
    dict(label="obj_leaf", position=(60.0, 1.0, 60.0), parts=((falls[0], falls[1], 4.0, ko_shapes.RF_WOBBLE),)),
]
alpha_zone["opd"].write_bytes(shapes.build(name="orig_large_zone", width=128.0, depth=128.0, shapes=material_shapes))
material_bake = ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
objects = material_bake["built"]["report"]["objects"]
assert (objects["placements"], objects["material_shapes"], objects["event_shapes"], objects["npc_shown_shapes"],
        objects["sequence_parts"], objects["first_frame_parts"], objects["alpha_parts"],
        objects["skipped_parts"]) == (4, 2, 0, 0, 2, 0, 1, 0), objects
assert material_bake["chunked"] and material_bake["world"][:4] == b"N3W6", material_bake["world"][:4]
material_parts = [p for p in material_bake["built"]["chunks"] if p["kind"] == 1]
slots, vertices = material_bake["built"]["texture_slots"], material_bake["built"]["vertices"]
assert [p["parent"] for p in material_parts] == [0, 1, 1, 2], [p["parent"] for p in material_parts]
one, zero = slots[("object", "orig_stone_1.dxt")], slots[("object", "orig_stone_0.dxt")]
for part, sequence, alpha in ((material_parts[1], [one, zero], True), (material_parts[3], [zero, zero], False)):
    assert part["flags"] & 128 and part["sequence"] == dict(slots=sequence, fps=10.0), part.get("sequence")
    assert bool(part["flags"] & 16) == alpha and bool(part["flags"] & 32) != alpha, part["flags"]
    assert {vertices[part["base"] + i][10] for i in range(part["max_vertices"])} == {float(sequence[0])}
assert (material_parts[1]["alpha"]["source"], material_parts[1]["alpha"]["destination"]) == (2, 2)
assert material_parts[1]["flags"] & 1, "RF_NOTUSEFOG kept as the part's fog bit"
assert not material_parts[0]["flags"] & 128 and not material_parts[2]["flags"] & 128
# Negative control: with material_cycle left out of BAKED, as before PQ-412,
# only the rock is placed and the zone stays N3W1 + N3L5.
ko_shapes.BAKED, kept = ko_shapes.BAKED - {"material_cycle"}, ko_shapes.BAKED
try:
    no_material = ko_scene.bake_world(alpha_zone["gtd"], alpha_zone["opd"], alpha_zone["assets"], alpha_zone["tct"])
finally:
    ko_shapes.BAKED = kept
objects = no_material["built"]["report"]["objects"]
assert (objects["placements"], objects["material_shapes"], objects["sequence_parts"]) == (1, 0, 0), objects
assert not no_material["chunked"] and no_material["world"][:4] == b"N3W1"
alpha_zone["opd"].write_bytes(shapes.build(name="orig_large_zone", width=128.0, depth=128.0, shapes=event_shapes))
print("PASS KO animated-material shapes (PQ-412, D-213): a static shape whose cycling parts do not billboard is "
      "placed with each cycling part's sequence (an ONE/ONE alpha part, an opaque part naming one texture twice) and "
      "its other parts static; RF_BOARD_Y and RF_WOBBLE shapes stay out; with the class left out only the static "
      "shape is placed and the zone stays N3W1")

# The colour map: (patches * 32) / 128 textures a side (0059eff0), counted
# exactly and bounded by the grid instead of the 8 MiB / 64-texture GTT bound.
assert [ko_tiles.color_map_side(p) for p in (4, 16, 64)] == [1, 4, 16]
for bad in (0, 2, 6, 17):
    try:
        ko_tiles.color_map_side(bad)
    except ValueError:
        continue
    raise AssertionError("accepted a %d-patch colour-map grid" % bad)
grid = tiles_fixture.gtt(count=256)  # 16 x 16, as a 513-sample (64-patch) map needs
colors = ko_tiles.tiles(grid, count=256)
assert sorted(colors) == list(range(256)) and colors[0] != colors[1]
assert len(ko_tiles.mip_chains(grid, count=256)) == 256
for data, count, reason in ((grid, None, "GTT tile count"), (grid, 255, "color-map count"),
                            (grid + tiles_fixture.texture(), 256, "color-map count"),
                            (grid[:-1], 256, "truncated")):
    try:
        ko_tiles.tiles(data, wanted=set(), count=count)
    except ValueError as error:
        assert reason in str(error), (reason, error)
        continue
    raise AssertionError("accepted a colour map that is not the grid: " + reason)
try:
    ko_tiles.mip_chains(grid + tiles_fixture.texture(), count=256)
except ValueError as error:
    assert "color-map count" in str(error), error
else:
    raise AssertionError("mip_chains accepted 257 colour-map textures")
# The homeland maps' 256 textures fill 11 MB, past the GTT file bound.
large = tiles_fixture.texture(256, 256) * 256
assert len(large) > ko_tiles.MAX_TEXTURE_FILE
try:
    ko_tiles.tiles(large, wanted=set())
except ValueError as error:
    assert "file bound" in str(error), error
else:
    raise AssertionError("the GTT bound no longer applies")
assert sorted(ko_tiles.tiles(large, wanted={255}, count=256)) == [255]

# The LOD terrain reads the colour map it is given (column 4), not a name derived
# from the GTD, and places texture i at region (i // side, i % side), x-major.
lod_side = 4
lod_samples = lod_side * 32 + 1
lod_height = {"width": lod_samples, "depth": lod_samples, "origin": [0.0, 0.0, 0.0],
              "spacing": 4.0, "heights": [0.0] * (lod_samples * lod_samples)}
lod_map = zone_root / "Zones" / "lod_colours.tct"
lod_map.write_bytes(tiles_fixture.gtt(count=lod_side * lod_side))
lod_atlas, lod_vertices = ko_scene.Atlas(), []
lod_chunks, _ = ko_lod.terrain(lod_map, lod_height, lod_atlas, lod_vertices, [], ko_scene.CLEAR)
lod_slots = {key[1]: slot for key, slot in lod_atlas.slots.items() if key[0] == "color-map"}
assert sorted(lod_slots) == list(range(lod_side * lod_side)), lod_slots
for chunk in lod_chunks:
    px, pz = chunk["patch"]
    used = {lod_vertices[i][10] for _, ix in chunk["levels"][1:] for i in ix}
    assert used == {float(lod_slots[(px // 4) * lod_side + pz // 4])}, (chunk["patch"], used)
lod_map.write_bytes(tiles_fixture.gtt(count=lod_side * lod_side - 1))
try:
    ko_lod.terrain(lod_map, lod_height, ko_scene.Atlas(), [], [], ko_scene.CLEAR)
except ValueError as error:
    assert "color-map count" in str(error), error
else:
    raise AssertionError("the LOD terrain accepted a short colour-map grid")
print("PASS zone key: Zones.tbl columns 2/4/6/8 trimmed and resolved (two files differing "
      "only in case refused as ambiguous), column 3 name check fails closed, OPDEXT read unless Reserved and the merged name re-checked, "
      "16x16 colour-map grid; the 129-sample cap binds the N3W1 path only and a map "
      "that fits keeps its N3W1 + N3L3 bake (PQ-234)")

# ---------------------------------------------------------------------------
# PQ-229: the OPDEXT reader and merge (005b4ef0, 005b52b0). Original fixtures.
ext_opd = parse_opd()  # 64 x 32 m, cells (0, 0) and (1, 1), six faces, flag 1


def parse_ext(opd=ext_opd, **kw):
    path = B / "fixture.opdext"
    path.write_bytes(opdext_fixture.build(**kw))
    return ko_opdext.load(path, opd)


def ext_refused(reason, opd=ext_opd, **kw):
    try:
        parse_ext(opd, **kw)
    except ValueError as error:
        assert reason in str(error), (reason, error)
        return
    raise AssertionError("accepted invalid OPDEXT: " + reason)


ext = parse_ext()
assert ext["version"] == 1 and ext["name"] is None and ext["faces"] == 3
assert ext["vertices"][0] == [10.0, -5000.0, 3.0] and ext["threshold"] == 4
# Cells are z-major like the OPD's; the faces sit in the second sub-cell written,
# which the OPD reader's order calls x = 1, z = 0.
assert [(c["x"], c["z"], c["flag"]) for c in ext["cells"]] == [(0, 0, 3), (2, 1, 1)]
assert ext["cells"][0]["sub_cells"] == [{"x": 1, "z": 0, "faces": 2,
                                         "indices": [0, 1, 2, 3, 4, 5]}]
assert ext["indexed_faces"] == 3
assert [c["flag"] for c in ext_opd["cells"]] == [1, 1]
merged = ko_opdext.merge(ext_opd, ext)
assert merged["name"] == "fixture_shapes"  # a zero-length name keeps the OPD's
assert merged["cell_flags"] == {(0, 0): 3, (1, 1): 1, (2, 1): 1}
assert merged["created_cells"] == [[2, 1]] and merged["reflagged_cells"] == [[0, 0, 1, 3]]
assert merged["skipped_cells"] == [] and merged["baked_faces"] == ext_opd["faces"]
assert merged["extension_faces"] == 3 and len(merged["extension_cells"]) == 2
assert ko_opdext.merge(ext_opd, parse_ext(name="Renamed"))["name"] == "Renamed"
assert ko_opdext.merge(ext_opd, parse_ext(cells=((1, 1, 2, ()),)))["skipped_cells"] == [[1, 1]]
# Version 0 carries no +0x6c value; a negative cell version reads no sub-cells.
assert parse_ext(version=0)["threshold"] == 0
assert parse_ext(cell_version=-1)["cells"][1]["sub_cells"] == []
assert parse_ext(name="ab\0\0")["name"] == "ab"  # the text up to the first NUL
assert parse_ext(faces=0, cells=((0, 0, 1, ()),))["faces"] == 0

ext_refused("OPDEXT version 2", version=2)
ext_refused("OPDEXT version -1", version=-1)
ext_refused("name length 31", name="x" * 31)
ext_refused("name length -1", name_length=-1)
ext_refused("name is empty", name="\0\0")
ext_refused("non-ASCII", name="caf\xe9")
ext_refused("differs from the OPD", width=48.0)
ext_refused("differs from the OPD", depth=48.0)
ext_refused("whole 16 m cells", opd=parse_opd(width=68.0), width=68.0)
ext_refused("face count -1", faces=-1, cells=())
ext_refused("nonfinite", vertex=float("nan"))
ext_refused("polygon count -1", count=-1)
ext_refused("outside its triangle soup", bad_index=True)
ext_refused("threshold -1", threshold=-1)
ext_refused("trailing", trailing=b"\0")
truncated_ext = B / "truncated.opdext"
truncated_ext.write_bytes(opdext_fixture.build()[:-1])
try:
    ko_opdext.load(truncated_ext, ext_opd)
except ValueError as error:
    assert "truncated" in str(error), error
else:
    raise AssertionError("accepted a truncated OPDEXT")
print("PASS OPDEXT: header, optional name, extent match, separate soup, z-major cells with "
      "flags and sub-cell lists, +0x6c value, merge keeps the OPD faces, malformed refused")

# ---------------------------------------------------------------------------
# PQ-217: START_POSITION start areas and the cropped start survey. Original
# extracts and maps only; the homelands themselves are tests/ko_bake_pin.py's.
import ko_start


def start_extract(rows):
    path = B / "pq217-start.json"
    path.write_text(json.dumps(rows))
    return path


home = dict(ZoneID=7, sKarusX=100, sKarusZ=40, sElmoradX=20, sElmoradZ=90, bRangeX=10, bRangeZ=6,
            sKarusGateX=0, sKarusGateZ=0, sElmoGateX=0, sElmoGateZ=0)
rows, digest = ko_start.load(start_extract([home, dict(home, ZoneID=8)]))
assert len(digest) == 64 and ko_start.load(B / "pq217-absent.json") == (None, None)
assert ko_start.row(70, rows) == home and ko_start.row(79, rows) == home  # key // 10
assert ko_start.row(90, rows) is None
# 004c6523: start + rand(0, range) on each axis, so the area lies on one side of
# the point: KO x 100..110 and z 40..46, which is n3e x -28..-18 and z 18..24 on
# a 256 m map (x - 128, 128 - z).
assert ko_start.areas(home, 256.0) == {"karus": (-28.0, 82.0, -18.0, 88.0),
                                       "elmorad": (-108.0, 32.0, -98.0, 38.0)}
assert ko_start.to_ko([-28.0, 0.0, 88.0], 256.0) == [100.0, 40.0]
for bad, key, phrase in (([home, home], 70, "2 rows"),
                         ([dict(home, bRangeX=256)], 70, "not a byte"),
                         ([dict(home, sKarusZ="40")], 70, "not an integer"),
                         ([dict(home, ZoneID=7.0)], 70, "ZoneID is not an integer"),
                         ([dict(home, ZoneID=True)], 10, "ZoneID is not an integer")):
    try:
        ko_start.row(key, ko_start.load(start_extract(bad))[0])
    except ValueError as error:
        assert phrase in str(error), (phrase, error)
        continue
    raise AssertionError("accepted a start row: " + phrase)
for blob in ({"start_position": [home]}, [home, 3]):
    try:
        ko_start.load(start_extract(blob))
    except ValueError as error:
        assert "not a list of START_POSITION rows" in str(error), error
        continue
    raise AssertionError("accepted an export that is not a list of rows")
for bad in (dict(home, sKarusX=250), dict(home, sElmoradZ=-1)):
    try:
        ko_start.areas(bad, 256.0)
    except ValueError as error:
        assert "leaves the 256 m map" in str(error), error
        continue
    raise AssertionError("accepted a start area off the map")
# PQ-051: the row digest covers the read columns spelled one way: key order and
# columns the bake does not read leave it alone, a read value changes it.
assert ko_start.row_digest(home) == ko_start.row_digest(dict(reversed(list(home.items())), sKarusGateX=9))
assert ko_start.row_digest(home) != ko_start.row_digest(dict(home, bRangeZ=7))
# The package nation is n3e's choice per zone; a zone without one is refused.
assert [ko_start.nation(k) for k in (10, 20)] == ["karus", "elmorad"]
try:
    ko_start.nation(70)
except ValueError as error:
    assert "no package nation" in str(error), error
else:
    raise AssertionError("zone 7 has a package nation")

# A crop keeps exactly the triangles whose bounds reach the grown area, in order.
soup = [[0, 0, 0], [1, 0, 0], [0, 0, 1], [50, 0, 50], [51, 0, 50], [50, 0, 51],
        [-40, 0, 5], [40, 0, 5], [0, 0, 6]]
assert ko_survey.crop(soup, (0, 0, 2, 2), margin=10) == soup[:3] + soup[6:]

# Flat ground with a wall beside the area: the crop gives the same candidates and
# engine walks as the whole map, a steep area has no candidate (fail closed), and
# a map whose soup is past the walk check's bound still surveys on its crop.
spot = B / "pq217-flat"
spot.mkdir(exist_ok=True)
(spot / "flat.gtd").write_bytes(fixture.build(samples=33, name="flat", surface=lambda x, z: 0.0))
(spot / "steep.gtd").write_bytes(fixture.build(samples=33, name="steep", surface=lambda x, z: 6.0 * x))
(spot / "flat.opd").write_bytes(shapes.build(name="flat", width=128.0, depth=128.0))
flat_areas = {"open": (-30.0, -30.0, -20.0, -20.0), "objects": (-60.0, 40.0, -50.0, 50.0)}
found, whole = ko_survey.survey_starts(spot / "flat.gtd", spot / "flat.opd", spot / "survey", flat_areas)
assert found["starts"]["open"]["spawn"] is not None
for name, area in flat_areas.items():
    result = found["starts"][name]
    near = ko_survey.area_candidates(whole, area)
    assert near == ko_survey.area_candidates(ko_survey.crop(whole, area), area)
    assert result["pre_filtered"] == len(near) and result["crop_points"] < len(whole), (name, result)
    expected = None  # the survey's choice, made on the whole map
    for c in near[:24]:
        r = dict(ko_survey.verify(whole, c["position"], spot / "survey" / "whole.txt"), sample=c["sample"])
        if r["open"] and (expected is None or r["min_away"] > expected["min_away"]):
            expected = r
    assert result["spawn"] == expected, (name, result["spawn"], expected)
# PQ-218: the walk target is the farthest open point the engine solver reaches
# from the start within the reach.
rules = json.loads(Path("games/demo/package.json").read_text())["gameplay"]
movement = dict(rules["movement"], speed=rules["speed"])
open_area, open_spawn = flat_areas["open"], found["starts"]["open"]["spawn"]["position"]
walk = ko_survey.walk_target(ko_survey.crop(whole, open_area), open_area, open_spawn, movement, spot / "walk")
far = max(math.hypot(c["position"][0] - open_spawn[0], c["position"][2] - open_spawn[2])
          for c in ko_survey.area_candidates(whole, (open_area[0] - 24, open_area[1] - 24,
                                                     open_area[2] + 24, open_area[3] + 24), 8))
assert walk is not None and walk["tried"] == 1 and abs(walk["distance"] - far) < 1e-9, (walk, far)
assert math.hypot(walk["engine_end"][0] - walk["target"][0], walk["engine_end"][2] - walk["target"][2]) <= 0.5, walk
# A floor with walls: every candidate is supported and at least 8 m away, so the
# engine decides. Walled in at the start, the solver reaches none of them: each is
# tried and the bake gets None (fail closed). With only the farthest candidate
# walled off, it is skipped and a nearer one is chosen.
def box(cx, cz, half, height=3.0):
    corners = [(cx - half, cz - half), (cx + half, cz - half), (cx + half, cz + half), (cx - half, cz + half)]
    out = []
    for (ax, az), (bx, bz) in zip(corners, corners[1:] + corners[:1]):
        out += [[ax, 0, az], [bx, 0, bz], [bx, height, bz], [ax, 0, az], [bx, height, bz], [ax, height, az]]
    return out
floor = [[-40, 0, -40], [40, 0, -40], [40, 0, 40], [-40, 0, -40], [40, 0, 40], [-40, 0, 40]]
start_area, start_point = (-1, -1, 1, 1), [0, 0.1, 0]
lattice = [c for c in ko_survey.area_candidates(floor, (-17, -17, 17, 17), 8)
           if math.hypot(c["position"][0], c["position"][2]) >= 8]
assert len(lattice) > 1
counted = []
original_route = ko_survey.route
def counting_route(*args, **kwargs):
    counted.append(args[2])
    return original_route(*args, **kwargs)
ko_survey.route = counting_route
try:
    assert ko_survey.walk_target(floor + box(0, 0, 4), start_area, start_point, movement, spot / "walk",
                                 reach=16, limit=len(lattice)) is None
finally:
    ko_survey.route = original_route
assert len(counted) == len(lattice), (len(counted), len(lattice))  # every candidate open, none reached
farthest = max(lattice, key=lambda c: math.hypot(c["position"][0], c["position"][2]))
fx, fz = farthest["sample"]
detour = ko_survey.walk_target(floor + box(fx, fz, 2.5), start_area, start_point, movement, spot / "walk", reach=16)
assert detour is not None and detour["tried"] > 1 and (detour["target"][0], detour["target"][2]) != (fx, fz), detour
assert detour["distance"] < math.hypot(fx, fz), detour
steep, _ = ko_survey.survey_starts(spot / "steep.gtd", spot / "flat.opd", spot / "survey", {"cliff": (-30.0, -30.0, -20.0, -20.0)})
assert steep["starts"]["cliff"]["spawn"] is None and steep["starts"]["cliff"]["pre_filtered"] == 0, steep["starts"]
big = large_zone.write(B / "pq217-zone")  # 513 samples, 2048 m
found, whole = ko_survey.survey_starts(big["gtd"], big["opd"], spot / "survey", {"home": (-924.0, -924.0, -914.0, -914.0)})
assert len(whole) > ko_survey.WALK_POINTS and found["starts"]["home"]["spawn"] is not None, found["starts"]
del whole
print("PASS start areas: START_POSITION X + rand(0, range) as an n3e rectangle per nation from an "
      "operator export (file and canonical row hashed; malformed exports and rows, off-map areas and zones without a package "
      "nation refused); the survey crop gives the whole map's answers, a steep area "
      "fails closed, the walk target is the farthest point the engine reaches (%.1f m; walled in at the "
      "start, all %d candidates are tried and none is reached; with the farthest walled off, candidate %d "
      "of %.1f m is chosen), and a 513-sample map surveys on a crop of %d points"
      % (walk["distance"], len(lattice), detour["tried"], detour["distance"], found["starts"]["home"]["crop_points"]))

# ---------------------------------------------------------------------------
# PQ-222: the pre-1264 (1097) zone files have no version or name: the GTD starts
# with the sample count and the OPD with the width. The caller selects that
# layout (`headerless=True`); it is never guessed. The 1453 encoded-name header
# (an int32 n, n encoded bytes, a zero int32) is refused by name.
legacy = B / "pq222"
legacy.mkdir(exist_ok=True)


def refusal(load, path, **kw):
    try:
        load(path, **kw)
    except ValueError as e:
        return str(e)
    raise AssertionError("accepted %s with %s" % (path.name, kw))


headed_gtd, bare_gtd = legacy / "headed.gtd", legacy / "bare.gtd"
headed_gtd.write_bytes(fixture.build())
bare_gtd.write_bytes(fixture.build(headerless=True))
header_bytes = 8 + len("fixture_terrain")
assert bare_gtd.read_bytes() == headed_gtd.read_bytes()[header_bytes:]
headed, bare = ko_terrain.load(headed_gtd), ko_terrain.load(bare_gtd, headerless=True)
assert bare["version"] is None and bare["name"] == "" and headed["version"] == 2
assert bare["parsed_bytes"] == bare["total_bytes"] == headed["parsed_bytes"] - header_bytes
for key in ("samples", "heights", "tiles", "patches", "grass", "tile_sources", "tile_references", "height_range"):
    assert bare[key] == headed[key], key
assert ko_terrain.header_samples(bare_gtd, headerless=True) == SAMPLES
assert ko_terrain.provenance(bare_gtd, bare)["format"] == "N3 GTD headerless (pre-1264)"
assert ko_terrain.provenance(headed_gtd, headed)["format"] == "N3 GTD version 2"
# The flag decides: the default reads a headerless file's sample count as a version.
assert refusal(ko_terrain.load, bare_gtd) == "GTD version"
assert refusal(ko_terrain.header_samples, bare_gtd) == "GTD version"
for version in range(ko_terrain.MAX_VERSION + 1):
    path = legacy / ("v%d.gtd" % version)
    path.write_bytes(fixture.build(version=version))
    assert refusal(ko_terrain.load, path, headerless=True) == "GTD " + ko_terrain.HAS_HEADER
    assert refusal(ko_terrain.header_samples, path, headerless=True) == "GTD " + ko_terrain.HAS_HEADER
# A headerless map larger than N3W1 takes the chunked bound like a headed one.
bare_big = legacy / "bare-137.gtd"
bare_big.write_bytes(fixture.build(samples=137, headerless=True))
assert ko_terrain.header_samples(bare_big, headerless=True) == 137
assert "exceeds" in refusal(ko_terrain.load, bare_big, headerless=True)
assert ko_terrain.load(bare_big, ko_terrain.CHUNKED_MAX_SAMPLES, headerless=True)["samples"] == 137
# The gate before the lightmap count still fires without a header.
bad_light = legacy / "bare-lightmap.gtd"
bad_light.write_bytes(fixture.build(headerless=True, lightmap=1))
assert "lightmap" in refusal(ko_terrain.load, bad_light, headerless=True)

# The 1453 header: n = 7 encoded name bytes, then a zero int32, then the map.
ENCODED = ko_terrain.ENCODED_HEADER
encoded = struct.pack("<i", 7) + bytes([0x65, 0x13, 0xAF, 0xDB, 0x0D, 0x6E, 0x3B]) + struct.pack("<i", 0)
enc_gtd = legacy / "encoded.gtd"
enc_gtd.write_bytes(encoded + fixture.build(headerless=True))
for kw in ({}, {"headerless": True}):
    assert refusal(ko_terrain.load, enc_gtd, **kw) == "GTD " + ENCODED, kw
    assert refusal(ko_terrain.header_samples, enc_gtd, **kw) == "GTD " + ENCODED, kw
assert refusal(ko_terrain.header_name, enc_gtd) == "GTD " + ENCODED
# Without the zero int32 it stays the plain version refusal.
enc_gtd.write_bytes(encoded[:11] + struct.pack("<i", 1) + fixture.build(headerless=True))
assert refusal(ko_terrain.load, enc_gtd) == "GTD version"
# A leading value that is legal where it stands is never taken for the 1453
# header: a headerless 9-sample map whose int32 at byte 13 is zero still reads.
flat = bytearray(fixture.build(samples=9, headerless=True, surface=lambda x, z: 0.0))
flat[16] = 0  # tile (0, 1)'s low byte; bytes 13-15 are its zero height
assert struct.unpack_from("<i", flat, 13)[0] == 0
flat_gtd = legacy / "flat-9.gtd"
flat_gtd.write_bytes(bytes(flat))
assert ko_terrain.load(flat_gtd, headerless=True)["samples"] == 9
assert refusal(ko_terrain.load, flat_gtd) == "GTD " + ENCODED  # 9 is no version
print("PASS headerless GTD (pre-1264): same map as the headed file %d bytes shorter, chosen by the "
      "caller (default refuses it as 'GTD version', headerless refuses versions 0-%d), chunked bound "
      "and lightmap gate kept; the 1453 encoded header refused by name in both modes and never taken "
      "for a legal leading value" % (header_bytes, ko_terrain.MAX_VERSION))

headed_opd, bare_opd = legacy / "headed.opd", legacy / "bare.opd"
headed_opd.write_bytes(shapes.build(shapes=spec))
bare_opd.write_bytes(shapes.build(shapes=spec, headerless=True))
opd_header = 8 + len("fixture_shapes")
assert bare_opd.read_bytes() == headed_opd.read_bytes()[opd_header:]
h_col, b_col = ko_shapes.load_collision(headed_opd), ko_shapes.load_collision(bare_opd, headerless=True)
assert b_col["version"] is None and b_col["name"] == "" and h_col["version"] == 1
assert b_col["parsed_bytes"] == h_col["parsed_bytes"] - opd_header
for key in ("width", "depth", "faces", "face_kinds", "usable_faces", "vertices", "cells", "cell_grid",
            "indexed_faces", "referenced_vertices", "shape_count"):
    assert b_col[key] == h_col[key], key
h_sh, b_sh = ko_shapes.load_shapes(headed_opd), ko_shapes.load_shapes(bare_opd, headerless=True)
assert b_sh["parsed_bytes"] == b_sh["total_bytes"] and b_sh["shapes"] == h_sh["shapes"]
assert len(b_sh["shapes"]) == len(spec)
assert ko_shapes.provenance(bare_opd, b_col)["format"] == "N3 OPD headerless (pre-1264)"
assert refusal(ko_shapes.load_collision, bare_opd) == "OPD version"
assert refusal(ko_shapes.load_shapes, bare_opd) == "OPD version"
for version in range(ko_shapes.MAX_VERSION + 1):
    path = legacy / ("v%d.opd" % version)
    path.write_bytes(shapes.build(version=version))
    assert refusal(ko_shapes.load_collision, path, headerless=True) == "OPD " + ko_terrain.HAS_HEADER
enc_opd = legacy / "encoded.opd"
enc_opd.write_bytes(encoded + shapes.build(headerless=True))
for kw in ({}, {"headerless": True}):
    assert refusal(ko_shapes.load_collision, enc_opd, **kw) == "OPD " + ENCODED, kw
    assert refusal(ko_shapes.load_shapes, enc_opd, **kw) == "OPD " + ENCODED, kw
assert refusal(ko_shapes.header_name, enc_opd) == "OPD " + ENCODED
print("PASS headerless OPD (pre-1264): same collision block and %d shape records as the headed file "
      "%d bytes shorter, chosen by the caller (default refuses it as 'OPD version', headerless refuses "
      "versions 0-%d); the 1453 encoded header refused by name in both modes"
      % (len(spec), opd_header, ko_shapes.MAX_VERSION))

# PQ-275: the 1298 client reads a name length only after a positive version
# (terrain 0059a09e-0059a0a2, shape manager 005b46de-005b46e2; binary), so a
# version-0 file is the version int32 and then the map. Synthetic files only:
# no local GTD or OPD has version 0 (local-asset, PQ-222).
zero_gtd, zero_opd = legacy / "v0-bare.gtd", legacy / "v0-bare.opd"
zero_gtd.write_bytes(fixture.build(version=0))
zero_opd.write_bytes(shapes.build(version=0, shapes=spec))
assert zero_gtd.read_bytes() == struct.pack("<i", 0) + bare_gtd.read_bytes()
assert zero_opd.read_bytes() == struct.pack("<i", 0) + bare_opd.read_bytes()
zero = ko_terrain.load(zero_gtd)
assert zero["version"] == 0 and zero["name"] == "" and zero["parsed_bytes"] == zero["total_bytes"]
for key in ("samples", "heights", "tiles", "patches", "grass", "tile_sources", "tile_references", "height_range"):
    assert zero[key] == headed[key], key
assert ko_terrain.header_samples(zero_gtd) == SAMPLES and ko_terrain.header_name(zero_gtd) == ""
assert ko_terrain.provenance(zero_gtd, zero)["format"] == "N3 GTD version 0"
z_sh = ko_shapes.load_shapes(zero_opd)
assert z_sh["collision"]["version"] == 0 and z_sh["collision"]["name"] == ""
assert z_sh["parsed_bytes"] == z_sh["total_bytes"] and z_sh["shapes"] == h_sh["shapes"]
for key in ("width", "depth", "faces", "cells", "cell_grid", "shape_count"):
    assert z_sh["collision"][key] == h_col[key], key
assert ko_shapes.header_name(zero_opd) == ""
# The old n3e reading (a name length after version 0) is gone: a version-0 file
# that carries a zero name length now reads that zero as the map size or width.
old_gtd, old_opd = legacy / "v0-named.gtd", legacy / "v0-named.opd"
old_gtd.write_bytes(struct.pack("<ii", 0, 0) + bare_gtd.read_bytes())
old_opd.write_bytes(struct.pack("<ii", 0, 0) + bare_opd.read_bytes())
assert refusal(ko_terrain.load, old_gtd) == "GTD map size"
assert refusal(ko_terrain.header_samples, old_gtd) == "GTD map size"
assert refusal(ko_shapes.load_collision, old_opd) == "OPD map size"
# Versions 1 and 2 still read the name; n3e's own bounds (no negative version,
# none above 2) still refuse what the client would read without a name.
for version in (1, 2):
    named = legacy / ("named-v%d.gtd" % version)
    named.write_bytes(fixture.build(version=version))
    assert ko_terrain.header_name(named) == "fixture_terrain"
    named_opd = legacy / ("named-v%d.opd" % version)
    named_opd.write_bytes(shapes.build(version=version))
    assert ko_shapes.header_name(named_opd) == "fixture_shapes"
for version in (-1, ko_terrain.MAX_VERSION + 1):
    bad = legacy / ("bound-%d.gtd" % version)
    bad.write_bytes(fixture.build(version=version))
    assert refusal(ko_terrain.load, bad) == "GTD version"
    bad_opd = legacy / ("bound-%d.opd" % version)
    bad_opd.write_bytes(shapes.build(version=version))
    assert refusal(ko_shapes.load_collision, bad_opd) == "OPD version"
# The caller still picks the layout: headerless refuses a version-0 file, and
# the default refuses a headerless one, in both formats.
assert refusal(ko_terrain.load, zero_gtd, headerless=True) == "GTD " + ko_terrain.HAS_HEADER
assert refusal(ko_shapes.load_shapes, zero_opd, headerless=True) == "OPD " + ko_terrain.HAS_HEADER
assert refusal(ko_terrain.load, bare_gtd) == "GTD version"
assert refusal(ko_shapes.load_shapes, bare_opd) == "OPD version"
print("PASS version-0 GTD and OPD headers (PQ-275): no name length after version 0, so each is the "
      "headerless file plus a 4-byte version and reads to its last byte with the same map, collision "
      "block and %d shape records; a zero name length after version 0 is now read as the map size "
      "(refused), versions 1-2 keep their names, -1 and %d stay refused, and the caller's headerless "
      "choice still refuses version 0" % (len(spec), ko_terrain.MAX_VERSION + 1))

# With the player's 1097 installer unpacked (python3 -I
# tools/ko-reference/unpack_installer.py ref/ko-bin/installer/KnightOnline_1097.exe),
# the zones PQ-274 and PQ-224 cook read headerless: each GTD through the lightmap
# gate, each OPD (collision and every shape record) to its last byte. The default
# refuses each by its version. Hashes only; the files stay the player's.
import hashlib
zones_1097 = Path("build/ko-reference/installer-1097/client/Zones")
LEGACY_1097 = {  # zone: GTD sha256, OPD sha256, samples, collision faces, shape records
    "moradon": ("ff27c10ae5283e9d200b0a7715cc2db589f2df543b4357ad06485f84537df810",
                "b07e0d6b1136bfe8dc1efd07b482b0c85c2a3da4e2251340013f603862a3f743", 129, 9335, 2834),
    "karus_start": ("fed893b1a6d9c0607dbb052632a2c9bbd9ad38e8bcc05e841ae7e22c2fc49ea0",
                    "a582f2007fefc194ccd02cc4dd05c636a1c48ae716216c73c3e83e51b45d8548", 513, 22699, 1461),
    "elmorad_start": ("fc893af9e4b09f4bccf90a22499de2682d2d68af4755998bd3a319ba7563ecdb",
                      "571fe6da794886efda71e98bf813ad237de0dc5ff73dc2ddfa4d0a9af8a6e0c0", 513, 26172, 1917),
}
for zone, (gtd_sha, opd_sha, samples, faces, records) in LEGACY_1097.items():
    gtd_path, opd_path = zones_1097 / (zone + ".gtd"), zones_1097 / (zone + ".opd")
    if not (gtd_path.is_file() and opd_path.is_file()):
        print("SKIP 1097 %s: %s not unpacked" % (zone, zones_1097))
        continue
    if (hashlib.sha256(gtd_path.read_bytes()).hexdigest(), hashlib.sha256(opd_path.read_bytes()).hexdigest()) != (gtd_sha, opd_sha):
        print("SKIP 1097 %s: not the pinned installer's files" % zone)
        continue
    terrain = ko_terrain.load(gtd_path, ko_terrain.CHUNKED_MAX_SAMPLES, headerless=True)
    assert terrain["version"] is None and terrain["samples"] == samples, (zone, terrain["samples"])
    assert ko_terrain.header_samples(gtd_path, headerless=True) == samples
    objects = ko_shapes.load_shapes(opd_path, headerless=True)
    assert objects["parsed_bytes"] == objects["total_bytes"], zone
    assert objects["collision"]["faces"] == faces and len(objects["shapes"]) == records, zone
    assert refusal(ko_terrain.load, gtd_path, max_samples=ko_terrain.CHUNKED_MAX_SAMPLES) == "GTD version"
    assert refusal(ko_shapes.load_collision, opd_path) == "OPD version"
    print("PASS 1097 %s read headerless: GTD %d samples through the lightmap gate (%d of %d bytes; no n3e "
          "importer reads past that gate for any version), OPD %g m with %d faces and %d shape "
          "records to its last byte; the default refuses both by version"
          % (zone, samples, terrain["parsed_bytes"], terrain["total_bytes"], objects["collision"]["width"],
             faces, records))

# ---------------------------------------------------------------------------
# PQ-054: the operator-local import of the NPC tables (tests/ko_tables_import.py;
# synthetic rows, plus the operator's export when present).
# PQ-221: the research installer unpacker's pins (tests/ko_installer_unpack.py;
# a synthetic installer, plus the player's 2145 installer when present).
# PQ-227: the research Inno Setup 5.2.3 reader (tests/ko_inno_unpack.py; synthetic
# installers, plus a listing of the player's 2145 installer when present).
# PQ-309: the research 2145 table reader (tests/ko_tbl_2145.py; the FIPS 46-3 DES
# example and synthetic tables, plus the player's 2145 Zones.tbl when present).
# PQ-308: the research 2145 pack reader (tests/ko_pack_2145.py; synthetic packs,
# plus the player's four 2145 packs when present).
# PQ-330: the research 2145 clip-table reader (tests/ko_anim_2145.py; synthetic
# tables, plus the player's 2145 clip tables when present).
# PQ-274: the 1097 zone table, layout and headerless bake (tests/ko_homeland_1097.py,
# synthetic); the player's 1097 homeland cooks are pinned in tests/ko_bake_pin.py.
import subprocess
sys.stdout.flush()  # keep this file's lines ahead of the child's in a captured log
subprocess.run([sys.executable, "tests/ko_tables_import.py"], check=True)
subprocess.run([sys.executable, "tests/ko_homeland_1097.py"], check=True)
# PQ-223: a zone layout the table does not name (tests/ko_zone_layout.py, synthetic);
# the player's classic Moradon cooks are pinned in tests/ko_bake_pin.py, which make
# test runs itself, as a slow test (Makefile SLOW_TESTS, RQ-064).
subprocess.run([sys.executable, "tests/ko_zone_layout.py"], check=True)
subprocess.run([sys.executable, "tests/ko_installer_unpack.py"], check=True)
subprocess.run([sys.executable, "tests/ko_inno_unpack.py"], check=True)
subprocess.run([sys.executable, "tests/ko_tbl_2145.py"], check=True)
subprocess.run([sys.executable, "tests/ko_pack_2145.py"], check=True)
subprocess.run([sys.executable, "tests/ko_anim_2145.py"], check=True)
