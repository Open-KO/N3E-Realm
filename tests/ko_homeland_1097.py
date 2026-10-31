"""PQ-274: the 1097 client's zone table and homeland bake, on synthetic data.

* `ko_tbl` decrypts a client table as the 1298 client does (`006113b0` ->
  `0044f670`, key 0x816, 0x6081, 0x1608) and parses it as `006264d0` /
  `006359b0` do; a truncated, oversized or over-long table is refused. With the
  player's data present, the decoder is checked against independent data: the
  1298 client's encrypted `Data/Zones.tbl` decodes to exactly the rows of the
  Open-KO CSV export beside it (`assets/ko`, local-asset).
* `ko_zone.select(..., layout="1097")` reads a 15-column table of the 1097
  types, resolves columns 2, 3, 5 and 6, requires headerless GTD and OPD files,
  and refuses any other column layout, a headed file, or a missing file.
* The same map baked from headed files and from the same files without their
  headers (`headerless=True`) gives byte-identical collision, N3W2 world and
  N3WT textures (a 161-sample map on the chunked path the 1097 homelands take).
* `ko_scene.references` names every file a zone refers to that is not there,
  and `ko_bake.package` refuses such a 1097 zone by name before writing.
* `ko_bake.install_1097` refuses an absent unpack, another installer's
  manifest, and a zone file that differs from the manifest.
* `ko_start.row` / `nation` take the 1097 zone id (`zone=`).
* PQ-290 (D-180): a part's vertex lands at ((v + pivot) * scale) + position (the
  client's `004445a0` / `0041dda0` / `00443090`), measured on a synthetic zone;
  `ko_scene`'s file substitutes are read by the world bake, the texture chains
  and the references check; `ko_bake.corrections_1097` applies a pinned file only
  where the zone names it and refuses a changed or missing file by name. With
  the player's data, every trunked tree in the three 1097 maps (with their
  corrections) and the two 2004 homelands reaches from the ground into its
  crown, and `obj_ka_tree_brA` does not without its correction.

The player's own 1097 homeland cooks are pinned in tests/ko_bake_pin.py. Run by
tests/ko_terrain.py (so `make test`); it also runs alone. Original synthetic
data only; nothing from the player's KO data is written outside build/.
"""
import csv
import hashlib
import json
import re
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))

import ko_bake  # noqa: E402
import ko_large_zone_fixture as large_zone  # noqa: E402
import ko_scene  # noqa: E402
import ko_shapes  # noqa: E402
import ko_shapes_fixture as shapes_fixture  # noqa: E402
import ko_start  # noqa: E402
import ko_tbl  # noqa: E402
import ko_terrain  # noqa: E402
import ko_terrain_fixture as terrain_fixture  # noqa: E402
import ko_tiles_fixture as tiles_fixture  # noqa: E402
import ko_zone  # noqa: E402

B = Path("build/pq274-test")
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)


def refused(call, *args, **kw):
    try:
        call(*args, **kw)
    except ValueError as error:
        return str(error)
    raise AssertionError("accepted %r %r" % (args, kw))


# --- ko_tbl --------------------------------------------------------------------
# 0044f670 by hand for two bytes: the first cipher byte is XOR-ed with 0x08 (the
# key 0x816's bits 8-15); the key then becomes (0x08 + 0x816) * 0x6081 + 0x1608,
# from the cipher byte, and the second byte is XOR-ed with that key's bits 8-15.
key = ((0x08 + 0x816) * 0x6081 + 0x1608) & 0xFFFFFFFF
assert ko_tbl.decrypt(bytes([0x08, 0x00])) == bytes([0x00, (key >> 8) & 0xFF])
types = [6, 7, 1, 2, 3, 4, 5, 8, 9]
rows = [[7, "Zones\\a.gtd", -3, 250, -300, 60000, -70000, 1.5, 0.25], [8, "", 0, 0, 0, 0, 0, 0.0, 0.0]]
plain = ko_tbl.build(types, rows)
cipher = ko_tbl.encrypt(plain)
assert cipher != plain and ko_tbl.decrypt(cipher) == plain
assert ko_tbl.parse(plain) == (types, rows)
(B / "t.tbl").write_bytes(cipher)
assert ko_tbl.load(B / "t.tbl") == (types, rows)
assert "after the last row" in refused(ko_tbl.parse, plain + b"\0")
assert "past the end" in refused(ko_tbl.parse, plain[:-1])
assert "column type 0" in refused(ko_tbl.parse, ko_tbl.build([0], []))
assert "0 columns" in refused(ko_tbl.parse, struct.pack("<i", 0))
assert "rows" in refused(ko_tbl.parse, struct.pack("<iii", 1, 6, -1))
assert "rows" in refused(ko_tbl.parse, struct.pack("<iii", 1, 6, 1000))
long_string = struct.pack("<iii", 1, 7, 1) + struct.pack("<i", ko_tbl.MAX_STRING + 1) + b"x" * (ko_tbl.MAX_STRING + 1)
assert "byte string" in refused(ko_tbl.parse, long_string)
print("PASS KO client table: 0044f670 cipher (key 0x816, x 0x6081 + 0x1608) round trip, 006359b0 field sizes for "
      "types 1-9, and truncated, trailing, unknown-type, negative and oversized tables refused")

client = Path("assets/ko/Data")
if (client / "Zones.tbl").is_file() and (client / "Zones.tbl.csv").is_file():
    types, rows = ko_tbl.load(client / "Zones.tbl")
    with (client / "Zones.tbl.csv").open(encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.reader(handle))
    assert len(types) == len(exported[0]) == 24, len(types)
    # The export lists the rows by key; the table keeps its own order.
    by_key = {row[0]: row for row in rows}
    assert len(by_key) == len(rows) and sorted(by_key) == sorted(int(r[0]) for r in exported[1:]), sorted(by_key)
    for other in exported[1:]:
        row = by_key[int(other[0])]
        for t, value, text in zip(types, row, other):
            if t == 8:
                assert abs(value - float(text)) < 1e-6, (value, text)
            elif t != 7:
                assert value == int(text), (value, text)
            elif text.isascii():  # the export is UTF-8; the decoder keeps ASCII only
                assert value == text, (value, text)
    print("PASS the 1298 client's encrypted Data/Zones.tbl decodes to the %d rows and %d typed columns of the "
          "Open-KO CSV beside it, value for value by key (local-asset)" % (len(rows), len(types)))
else:
    print("SKIP 1298 Zones.tbl against its CSV: local KO client data absent")

# --- ko_zone, the 1097 layout ---------------------------------------------------
root = B / "client-1097"
(root / "Data").mkdir(parents=True)
(root / "Zones").mkdir()
zones = root / "Zones"
(zones / "orig_home.gtd").write_bytes(terrain_fixture.build(headerless=True))
(zones / "orig_home.opd").write_bytes(shapes_fixture.build(headerless=True))
(zones / "orig_home.tct").write_bytes(tiles_fixture.gtt(count=1))
(zones / "orig_home.dxt").write_bytes(tiles_fixture.texture())
(zones / "orig_home.tlt").write_bytes(bytes(8))  # PQ-387: the fourth column
(zones / "headed.gtd").write_bytes(terrain_fixture.build())
(zones / "headed.opd").write_bytes(shapes_fixture.build())


def legacy_row(key, gtd="Zones\\Orig_Home.GTD", opd="Zones\\orig_home.opd", tct="Zones\\orig_home.tct",
               dxt="Zones\\ORIG_HOME.dxt"):
    return [key, gtd, tct, "Zones\\orig_home.tlt", opd, dxt,
            "Misc\\Sky\\none.N3Sky", 1, 0, "Zones\\orig_home.glo", "Zones\\orig_home.gev", 0,
            "Zones\\orig_home.ens", 1.0, "Later"]


table = [legacy_row(1), legacy_row(2, gtd="Zones\\headed.gtd"), legacy_row(3, opd="Zones\\headed.opd"),
         legacy_row(4, gtd="Zones\\missing.gtd"), legacy_row(5), legacy_row(5)]
(root / "Data" / "Zones.tbl").write_bytes(ko_tbl.encrypt(ko_tbl.build(list(ko_zone.LEGACY_TYPES), table)))
picked = ko_zone.select(root, 1, layout="1097")
for kind, suffix in (("gtd", "gtd"), ("tct", "tct"), ("opd", "opd"), ("minimap", "dxt")):
    assert picked[kind] == zones / ("orig_home." + suffix), (kind, picked[kind])
assert picked["headerless"] and picked["layout"] == "1097" and picked["zone_id"] == 1 and picked["opdext"] is None
assert picked["tlt"] == zones / "orig_home.tlt" and picked["provenance"]["light_maps"]["column"] == "4", picked["tlt"]
assert picked["provenance"]["names"].startswith("not applicable") and picked["provenance"]["layout"] == "1097"
assert picked["row"][0] == "1" and picked["row"][13] == "1.0"
# The same table never reads under the 1298 layout, which wants its CSV export.
assert "no Zones.tbl.csv" in refused(ko_zone.select, root, 1)
assert "unknown Zones.tbl layout" in refused(ko_zone.select, root, 1, layout="1264")
assert ko_terrain.HAS_HEADER in refused(ko_zone.select, root, 2, layout="1097")
assert ko_terrain.HAS_HEADER in refused(ko_zone.select, root, 3, layout="1097")
assert "not a local file" in refused(ko_zone.select, root, 4, layout="1097")
assert "2 rows" in refused(ko_zone.select, root, 5, layout="1097")
assert "no row for zone key 9" in refused(ko_zone.select, root, 9, layout="1097")
# Another column layout (the 1298 table's 24 types) is refused, not re-mapped.
types_1298 = [6, 7, 7, 7, 7, 7, 7, 7, 7, 5, 5, 7, 7, 5, 7, 8, 7, 6, 6, 6, 6, 7, 5, 7]
other = B / "client-1298-table"
(other / "Data").mkdir(parents=True)
(other / "Data" / "Zones.tbl").write_bytes(ko_tbl.encrypt(ko_tbl.build(types_1298, [])))
assert "not the 1097 layout" in refused(ko_zone.select, other, 1, layout="1097")
print("PASS 1097 Zones.tbl layout: 15 columns of the 1097 types, key = zone id, columns 2/3/5/6 resolved, "
      "headerless GTD and OPD required; a headed file, a missing file, a repeated key and the 1298 "
      "layout refused")

# --- the headerless bake equals the headed bake ---------------------------------
headed = large_zone.write(B / "headed-zone", samples=161)
bare = B / "bare-zone"
shutil.copytree(B / "headed-zone", bare)
name = "orig_large_zone"
for suffix in ("gtd", "opd"):
    data = (bare / "Zones" / (name + "." + suffix)).read_bytes()
    assert struct.unpack_from("<i", data, 4)[0] == len(name)
    (bare / "Zones" / (name + "." + suffix)).write_bytes(data[8 + len(name):])
a = ko_scene.bake_world(headed["gtd"], headed["opd"], headed["assets"], headed["tct"])
b = ko_scene.bake_world(bare / "Zones" / (name + ".gtd"), bare / "Zones" / (name + ".opd"), bare,
                        bare / "Zones" / (name + ".tct"), headerless=True)
assert a["chunked"] and b["chunked"] and a["world"][:4] == b"N3W4"  # PQ-382: opaque parts set bit 5
assert a["world"] == b["world"] and a["textures"] == b["textures"] and a["lod"] is b["lod"] is None
assert a["heightfield"] == b["heightfield"] and a["triangles"] == b["triangles"]
assert b["report"]["terrain"]["format"] == "N3 GTD headerless (pre-1264)"
assert "GTD version" in refused(ko_scene.bake_world, bare / "Zones" / (name + ".gtd"),
                                bare / "Zones" / (name + ".opd"), bare, bare / "Zones" / (name + ".tct"))
print("PASS headerless bake: a 161-sample map read without its headers cooks byte-identical N3W2 world, N3WT "
      "textures, heightfield and collision to the headed files; the default refuses the headerless files")

# --- every referenced file present, or refused by name --------------------------
found = ko_scene.references(bare / "Zones" / (name + ".gtd"), bare / "Zones" / (name + ".opd"), bare, True)
assert found["missing"] == [] and found["unreadable_meshes"] == {} and found["meshes"] == 1, found
assert found["gtt"] == large_zone.TILE_FILES.__len__() and found["textures"] == 2, found
(bare / "Object" / "orig_stone_1.dxt").unlink()
(bare / "DTex" / large_zone.TILE_FILES[0]).unlink()
(bare / "Object" / "orig_pyramid.n3pmesh").write_bytes(b"\0" * 8)
found = ko_scene.references(bare / "Zones" / (name + ".gtd"), bare / "Zones" / (name + ".opd"), bare, True)
assert found["missing"] == ["DTex/" + large_zone.TILE_FILES[0].lower(), "Object/orig_stone_1.dxt"], found
assert list(found["unreadable_meshes"]) == ["orig_pyramid.n3pmesh"], found
# The bake refuses such a 1097 zone by name, before it writes anything.
(bare / "Data").mkdir()
(bare / "Zones" / "orig.dxt").write_bytes(tiles_fixture.texture())
(bare / "Zones" / "orig_home.tlt").write_bytes(bytes(8))  # PQ-387: the fourth column
(bare / "Data" / "Zones.tbl").write_bytes(ko_tbl.encrypt(ko_tbl.build(list(ko_zone.LEGACY_TYPES), [
    legacy_row(1, gtd="Zones\\%s.gtd" % name, opd="Zones\\%s.opd" % name, tct="Zones\\%s.tct" % name,
               dxt="Zones\\orig.dxt")])))
zone = ko_zone.select(bare, 1, layout="1097")
out = B / "refused-package"
error = refused(ko_bake.package, "games/demo", zone, str(out), None, overview=True,
                character_assets="assets/ko")
assert "2 missing files" in error and "orig_stone_1.dxt" in error and large_zone.TILE_FILES[0].lower() in error, error
assert not out.exists()
print("PASS 1097 references: every GTT, mesh and part texture the zone names is looked up; missing ones are "
      "named and the package is refused before anything is written; an unreadable mesh is listed by name")

# --- the 1097 install's manifest -----------------------------------------------
install = B / "install"
assert "no 1097 install" in refused(ko_bake.install_1097, picked, install)
install.mkdir()
shutil.copytree(root, install / "client")
picked = ko_zone.select(install / "client", 1, layout="1097")
entries = [{"path": p.relative_to(install / "client").as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in (install / "client").rglob("*") if p.is_file()]
(install / "manifest.json").write_text(json.dumps({"sha256": "0" * 64, "manifest": entries}))
assert "not the pinned 1097 installer" in refused(ko_bake.install_1097, picked, install)
(install / "manifest.json").write_text(json.dumps({"sha256": ko_bake.INSTALLER_1097_SHA256, "manifest": entries}))
record = ko_bake.install_1097(picked, install)
assert sorted(record["files"]) == ["Data/Zones.tbl", "Zones/orig_home.dxt", "Zones/orig_home.gtd",
                                   "Zones/orig_home.opd", "Zones/orig_home.tct", "Zones/orig_home.tlt"], record
(install / "client" / "Zones" / "orig_home.tct").write_bytes(tiles_fixture.gtt(count=2))
assert "differs from the 1097 installer" in refused(ko_bake.install_1097, picked, install)
print("PASS 1097 install check: an absent unpack, another installer's manifest and a changed zone file refused")

# --- the start row by zone id ----------------------------------------------------
start_rows = [dict(ZoneID=1, sKarusX=441, sKarusZ=1625, sElmoradX=1859, sElmoradZ=170, bRangeX=10, bRangeZ=10),
              dict(ZoneID=21, sKarusX=1, sKarusZ=1, sElmoradX=1, sElmoradZ=1, bRangeX=1, bRangeZ=1)]
assert ko_start.row(1, start_rows, zone=1)["sKarusX"] == 441 and ko_start.row(10, start_rows)["sKarusX"] == 441
assert ko_start.row(1, start_rows) is None  # key 1 under the 1298 scheme is zone 0
assert ko_start.nation(1, zone=1) == "karus" and ko_start.nation(2, zone=2) == "elmorad"
assert "no package nation" in refused(ko_start.nation, 21, zone=21)
print("PASS START_POSITION rows by the 1097 zone id: key 1 is zone 1 with zone=, zone 0 without; zone 21 has "
      "no package nation")

# --- PQ-290 (D-180): the part rule, file substitutes and the 1097 corrections ------
# The client's part rule (004445a0, 0041dda0, 00443090): a part's vertex lands at
# ((v + pivot) * scale) * rotation + position, measured on a synthetic zone whose
# one lattice pyramid stands at the map centre (scale 4, no rotation) and whose
# part pivot is the fixture's (0.5, 0.25, 0.125).
import ko  # noqa: E402

small = large_zone.write(B / "pq290-zone", samples=33)
plain = ko_scene.bake_world(small["gtd"], small["opd"], small["assets"], small["tct"])
assert not plain["chunked"] and plain["world"][:4] == b"N3W1"
first = plain["built"]["report"]["terrain_vertices"]
mesh = ko.import_mesh(small["assets"] / "Object" / "orig_pyramid.n3pmesh", 1.0)["vertices"]
ground = large_zone.surface(16, 16)
drawn = plain["built"]["vertices"][first:first + len(mesh)]
for v, out in zip(mesh, drawn):
    want = [(v[0] + 0.5) * 4, ground + (v[1] + 0.25) * 4, (v[2] - 0.125) * 4]  # z is reflected by import_mesh
    assert all(abs(a - b) < 1e-4 for a, b in zip(out[:3], want)), (v, out[:3], want)
# A substitute is read in place of the zone's file: here a re-export standing 3 m higher.
elsewhere = B / "pq290-2004"
(elsewhere / "Object").mkdir(parents=True)
risen = elsewhere / "Object" / "orig_pyramid.n3pmesh"
risen.write_bytes(large_zone.pmesh([(-1, 3, -1, 0, 0), (1, 3, -1, 2, 0), (1, 3, 1, 2, 2), (-1, 3, 1, 0, 2),
                                    (0, 6, 0, 1, 1)], [(0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0), (0, 1, 2), (0, 2, 3)]))
moved = ko_scene.bake_world(small["gtd"], small["opd"], small["assets"], small["tct"],
                            substitutes={"ORIG_PYRAMID.n3pmesh": risen})
assert moved["built"]["vertices"][:first] == plain["built"]["vertices"][:first]  # terrain untouched
shapes = ko_shapes.load_shapes(small["opd"])["shapes"]
assert len(shapes) == 2
for k, shape in enumerate(shapes):
    for a, b in zip(plain["built"]["vertices"][first + 5 * k:first + 5 * k + 5],
                    moved["built"]["vertices"][first + 5 * k:first + 5 * k + 5]):
        assert abs(b[1] - a[1] - 3 * shape["scale"][1]) < 1e-4 and a[0] == b[0] and a[2] == b[2], (k, a, b)
assert moved["world"] != plain["world"] and moved["built"]["substitutes"] == {"ORIG_PYRAMID.n3pmesh": risen}
# The texture chains and the references check look a substituted name up at the substitute.
stone = elsewhere / "Object" / "orig_stone_0.dxt"
stone.write_bytes(tiles_fixture.texture(16, 16, seed=40))
textured = ko_scene.bake_world(small["gtd"], small["opd"], small["assets"], small["tct"],
                               substitutes={"orig_stone_0.dxt": stone})
_, sources = ko_scene.world_chains(small["assets"], textured["built"])
assert str(stone) in sources and str(small["assets"] / "Object" / "orig_stone_0.dxt") not in sources, sources
(small["assets"] / "Object" / "orig_stone_1.dxt").rename(elsewhere / "Object" / "orig_stone_1.dxt")
found = ko_scene.references(small["gtd"], small["opd"], small["assets"])
assert found["missing"] == ["Object/orig_stone_1.dxt"], found
found = ko_scene.references(small["gtd"], small["opd"], small["assets"],
                            substitutes={"orig_stone_1.dxt": elsewhere / "Object" / "orig_stone_1.dxt"})
assert found["missing"] == [], found
(elsewhere / "Object" / "broken.n3pmesh").write_bytes(b"\0" * 8)
found = ko_scene.references(small["gtd"], small["opd"], small["assets"],
                            substitutes={"orig_stone_1.dxt": elsewhere / "Object" / "orig_stone_1.dxt",
                                         "orig_pyramid.n3pmesh": elsewhere / "Object" / "broken.n3pmesh"})
assert list(found["unreadable_meshes"]) == ["orig_pyramid.n3pmesh"], found
(elsewhere / "Object" / "orig_stone_1.dxt").rename(small["assets"] / "Object" / "orig_stone_1.dxt")
print("PASS part rule: each vertex at ((v + pivot) * scale) + position (004445a0, 0041dda0, 00443090); a "
      "substitute mesh is read in place of the zone's (every part 3 m x scale higher, terrain untouched), and "
      "the texture chains and the references check look a substituted name up at the substitute")

# ko_bake.corrections_1097: only files the zone names, both hashes pinned, refused by name otherwise.
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


zone = dict(opd=small["opd"], assets=small["assets"])
table = {"orig_pyramid.n3pmesh": (sha(small["assets"] / "Object" / "orig_pyramid.n3pmesh"), sha(risen)),
         "orig_unused.n3pmesh": ("0" * 64, "0" * 64)}
substitutes, records = ko_bake.corrections_1097(zone, client=elsewhere, table=table)
assert substitutes == {"orig_pyramid.n3pmesh": risen}, substitutes
assert records == [dict(file="Object/orig_pyramid.n3pmesh", replaced_sha256=table["orig_pyramid.n3pmesh"][0],
                        source=str(risen), sha256=table["orig_pyramid.n3pmesh"][1], decision="D-180")], records
assert ko_bake.corrections_1097(zone, client=elsewhere, table={"orig_unused.n3pmesh": ("0" * 64,) * 2}) == ({}, [])
stale, fixed = table["orig_pyramid.n3pmesh"]
assert "not the pinned 1097 install's file" in refused(ko_bake.corrections_1097, zone, client=elsewhere,
                                                        table={"orig_pyramid.n3pmesh": ("1" * 64, fixed)})
assert "not the pinned 2004 client's file" in refused(ko_bake.corrections_1097, zone, client=elsewhere,
                                                       table={"orig_pyramid.n3pmesh": (stale, "1" * 64)})
assert "2004 client's file is missing" in refused(ko_bake.corrections_1097, zone, client=B / "no-client",
                                                   table={"orig_pyramid.n3pmesh": (stale, fixed)})
assert all(len(a) == len(b) == 64 for a, b in ko_bake.CORRECTIONS_1097.values())
assert list(ko_bake.CORRECTIONS_1097) == ["obj_ka_tree_bra_post.n3pmesh"], ko_bake.CORRECTIONS_1097
print("PASS 1097 corrections: a pinned file the zone names is read from the 2004 client and recorded "
      "(D-180); one it does not name changes nothing; a changed file on either side or a missing 2004 file is "
      "refused by name")


# On the player's data: every trunked tree's trunk reaches from the ground into its
# crown, in the three 1097 maps (with their corrections) and the two 2004 homelands.
# A trunk part's base name ends `_post`, `_po` (obj_war_tree_a01..a04_po), `_tr`
# (obj_dun_pondtree01_tr) or `_body` (obj_el_TreeHouse01_tree_body).
TRUNK = re.compile(r"_(post|po|tr|body)\.n3pmesh$")


def trunks(zone, substitutes):
    """(names of the trunked tree shapes, those whose trunk part does not reach from
    the shape's origin into its lowest other part), shape-local metres before scale."""
    objects = ko_scene.object_files(Path(zone["assets"]), substitutes)
    spans, seen, broken = {}, set(), {}
    for shape in ko_shapes.load_shapes(zone["opd"], headerless=zone.get("headerless", False))["shapes"]:
        if ko_shapes.classify(shape) != "static" or "tree" not in shape["name"].lower() or shape["name"] in seen:
            continue
        seen.add(shape["name"])
        rows = []
        for part in shape["parts"]:
            name = ko_scene._basename(part["mesh"])
            if name not in objects:
                continue
            if name not in spans:
                ys = [v[1] for v in ko.import_mesh(objects[name], 1.0)["vertices"]]
                spans[name] = (min(ys), max(ys))
            rows.append((name, spans[name][0] + part["pivot"][1], spans[name][1] + part["pivot"][1]))
        posts = [r for r in rows if TRUNK.search(r[0])]
        others = [r for r in rows if not TRUNK.search(r[0])]
        if not posts or not others:
            seen.discard(shape["name"])
            continue
        lowest = min(r[1] for r in others)
        for _, bottom, top in posts:
            if bottom > 0.5 or top < lowest:
                broken[shape["name"]] = (round(bottom, 2), round(top, 2), round(lowest, 2))
    return seen, broken


install_1097 = ko_bake.INSTALL_1097
if (install_1097 / "manifest.json").is_file() and (ko_bake.CLIENT / "Data" / "Zones.tbl.csv").is_file():
    lines = []
    for key in (1, 2, 21):
        picked = ko_zone.select(install_1097 / "client", key, layout="1097")
        substitutes, records = ko_bake.corrections_1097(picked)
        assert sorted(substitutes) == (["obj_ka_tree_bra_post.n3pmesh"] if key == 1 else []), (key, substitutes)
        seen, broken = trunks(picked, substitutes)
        count = len(seen)
        assert count > 0 and broken == {}, (key, broken)
        if key == 2:
            assert "obj_el_TreeHouse01_tree" in seen, sorted(seen)
        if key == 1:
            _, before = trunks(picked, {})
            assert list(before) == ["obj_ka_tree_brA"] and before["obj_ka_tree_brA"][0] < -3, before
            lines.append("1097 key 1: %d trunked trees joined; without the correction obj_ka_tree_brA's trunk spans "
                         "y %s..%s under a crown from %s" % (count, *before["obj_ka_tree_brA"]))
        else:
            lines.append("1097 key %d: %d trunked trees joined, no correction" % (key, count))
    for key in (10, 20):
        seen, broken = trunks(ko_zone.select(ko_bake.CLIENT, key), {})
        count = len(seen)
        assert count > 0 and broken == {}, (key, broken)
        if key == 20:
            assert {"obj_war_tree_a0%d" % n for n in (1, 2, 3, 4)} | {"obj_dun_pondtree01"} <= seen, sorted(seen)
        lines.append("2004 key %d: %d trunked trees joined" % (key, count))
    print("PASS tree trunks on the player's data (local-asset): " + "; ".join(lines))
else:
    print("SKIP tree trunks on the player's data: the 1097 install or the 2004 client is absent")
