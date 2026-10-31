"""PQ-223 (D-171): a zone layout its Zones.tbl does not name, on synthetic data.

* `ko_zone.select(..., stem=...)` rewrites the row before it resolves anything
  (`ko_zone.restem`): column 3 and every `Zones\\<column 3>.<ext>` column take
  the new stem, case-insensitively and keeping the row's leading and trailing
  spaces; the other columns stay as they are. The files, the `005a3110` name
  check and the provenance then follow the rewritten row: a renamed file whose
  internal name is not the new stem is refused as `Invalid Map Files`, a path
  column naming another file refuses the rewrite, and without `stem` the
  selection and its record are what they were.
* `ko_bake.moradon_layout` refuses a layout whose selected files differ from
  the pinned installer's hashes, naming each file.
* `tools/assetc/ko_bake.py --layout=` refuses an unknown layout and the
  combinations it does not cook (`--client=1097`, `--des`) before reading any
  client data.
* PQ-224 (D-172): `ko_bake.package` with `character_assets` from another
  install refuses `--des`, and `--features` unless the layout is `1097`, before
  it writes anything.

The player's own classic Moradon cooks are pinned in tests/ko_bake_pin.py. Run
by tests/ko_terrain.py (so `make test`); it also runs alone. Original synthetic
data only.
"""
import csv
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))

import ko_bake  # noqa: E402
import ko_shapes_fixture as shapes  # noqa: E402
import ko_terrain_fixture as terrain  # noqa: E402
import ko_tiles_fixture as tiles  # noqa: E402
import ko_zone  # noqa: E402

B = Path("build/pq223-test")
shutil.rmtree(B, ignore_errors=True)
root = B / "client"
(root / "Data").mkdir(parents=True)
(root / "Zones").mkdir()


def refused(call, *args, **kw):
    try:
        call(*args, **kw)
    except ValueError as error:
        return str(error)
    raise AssertionError("accepted %r %r" % (args, kw))


# Two layouts of one town: the table names "Vale_fest"; "vale" is on disk, unnamed.
for stem, name in (("vale_fest", "Vale_fest"), ("vale", "VALE"), ("vale_wrong", "somewhere")):
    (root / "Zones" / (stem + ".gtd")).write_bytes(terrain.build(name=name))
    (root / "Zones" / (stem + ".opd")).write_bytes(shapes.build(name=name))
    (root / "Zones" / (stem + ".tct")).write_bytes(tiles.gtt(count=1))
    (root / "Zones" / (stem + ".dxt")).write_bytes(tiles.texture(seed=len(stem)))
    (root / "Zones" / (stem + ".tlt")).write_bytes(bytes(8))  # PQ-387: column 5


def zone_row(key, stem="Vale_fest", opd=None, opdext="Reserved"):
    # The 1298 layout's 24 columns, with a leading-space column 13 and a
    # trailing-space column 2 as real rows carry.
    return [str(key), "Zones\\%s.gtd " % stem, stem, "Zones\\%s.tct" % stem, "Zones\\%s.tlt" % stem,
            opd or "Zones\\%s.opd" % stem, opdext, "Zones\\%s.dxt" % stem, "Misc\\Sky\\Field.N3Sky", "1", "0",
            "Zones\\%s.glo" % stem, " Zones\\%s.gev" % stem, "0", "Zones\\%s.ens" % stem, "0.5",
            "Zones\\%s.flag" % stem, "20003", "20000", "20002", "20000", "Zones\\%s.opdsub" % stem, "1", ""]


rows = [["1 - UInt32"] + ["%d - String" % c for c in range(2, 25)],
        zone_row(9010),
        zone_row(9020, opd="Zones\\other.opd"),           # a path column naming another file
        zone_row(9030, stem="Zones\\odd"),                # column 3 is not a plain stem
        zone_row(9040, opdext="Zones\\Vale_fest.opdext")]  # an OPDEXT renames too
with (root / "Data" / "Zones.tbl.csv").open("w", newline="", encoding="utf-8") as handle:
    csv.writer(handle).writerows(rows)

default = ko_zone.select(root, 9010)
assert default["gtd"].name == "vale_fest.gtd" and "variant" not in default["provenance"], default["provenance"]
assert default["stem"] is None and default["row"] == rows[1]

classic = ko_zone.select(root, 9010, stem="Vale")
for kind, suffix in (("gtd", "gtd"), ("tct", "tct"), ("opd", "opd"), ("minimap", "dxt")):
    assert classic[kind] == root / "Zones" / ("vale." + suffix), (kind, classic[kind])
assert classic["names"] == {"gtd": "VALE", "opd": "VALE"}, classic["names"]
assert classic["tlt"] == root / "Zones" / "vale.tlt", classic["tlt"]  # PQ-387: column 5 follows the stem
row = classic["row"]
assert row[ko_zone.NAME] == "Vale" and row[1] == "Zones\\Vale.gtd " and row[12] == " Zones\\Vale.gev", row
unchanged = [i for i, (a, b) in enumerate(zip(rows[1], row)) if a == b]
assert unchanged == [0, 6, 8, 9, 10, 13, 15, 17, 18, 19, 20, 22, 23], unchanged
variant = classic["provenance"]["variant"]
assert variant["stem"] == "Vale" and variant["table_stem"] == "Vale_fest", variant
assert sorted(variant["rewritten_columns"], key=int) == ["2", "3", "4", "5", "6", "8", "12", "13", "15", "17",
                                                         "22"], variant
assert variant["rewritten_columns"]["6"] == ["Zones\\Vale_fest.opd", "Zones\\Vale.opd"], variant
assert classic["provenance"]["columns"]["3"] == "Vale" and classic["provenance"]["names"] == classic["names"]
# The stem matches the table's case-insensitively, as Windows paths do.
assert ko_zone.select(root, 9010, stem="vale")["gtd"] == classic["gtd"]

# The 005a3110 name check follows the rewritten row.
assert "Invalid Map Files" in refused(ko_zone.select, root, 9010, stem="vale_wrong")
assert "not a local file" in refused(ko_zone.select, root, 9010, stem="absent")
assert "refusing to rename" in refused(ko_zone.select, root, 9020, stem="Vale")
assert "not a file stem" in refused(ko_zone.select, root, 9030, stem="Vale")
for bad in ("..", "Zones\\vale", "va le", "", "x" * 65):
    assert "a zone file stem" in refused(ko_zone.select, root, 9010, stem=bad), bad
assert "1298 layout only" in refused(ko_zone.select, root, 1, layout="1097", stem="Vale")
renamed_ext, _ = ko_zone.restem(rows[4], "Vale")
assert renamed_ext[ko_zone.OPDEXT] == "Zones\\Vale.opdext", renamed_ext
print("PASS zone layout rewrite: column 3 and every Zones\\<stem>.* column renamed (case and spaces kept, "
      "11 of 24 columns); files, name check and provenance follow it; another file name, a bad stem, a "
      "wrong internal name and a missing file refused; without a stem the selection is unchanged")

# The layout's files must be the pinned installer's.
hashes = {kind: hashlib.sha256(Path(classic[kind]).read_bytes()).hexdigest()
          for kind in ("gtd", "tct", "opd", "minimap")}
saved = dict(ko_bake.MORADON_LAYOUTS)
try:
    ko_bake.MORADON_LAYOUTS["synthetic"] = ("Vale", hashes)
    assert ko_bake.moradon_layout(classic, "synthetic") == hashes
    ko_bake.MORADON_LAYOUTS["synthetic"] = ("Vale", dict(hashes, opd="0" * 64, minimap="1" * 64))
    message = refused(ko_bake.moradon_layout, classic, "synthetic")
    assert "vale.opd (opd)" in message and "vale.dxt (minimap)" in message and "vale.gtd" not in message, message
finally:
    ko_bake.MORADON_LAYOUTS.clear()
    ko_bake.MORADON_LAYOUTS.update(saved)

# The command refuses what it does not cook before it reads any client data.
for flags, phrase in ((["--layout=nope"], "--layout takes classic"),
                      (["--layout=classic", "--client=1097"], "does not combine"),
                      (["--layout=classic", "--des"], "does not combine")):
    run = subprocess.run([sys.executable, "tools/assetc/ko_bake.py", "210", *flags, "--into=%s" % (B / "out")],
                         capture_output=True, text=True)
    assert run.returncode != 0 and phrase in run.stderr, (flags, run.stderr[-800:])
    assert not (B / "out").exists(), flags
print("PASS layout files checked against the pinned hashes by name; ko_bake.py refuses an unknown layout and "
      "--layout with --client=1097 or --des before cooking")

# PQ-224 (D-172): a map from another install takes its features from the player's
# client only as the 1097 Moradon; --des never. Refused before anything is written.
for kw, phrase in ((dict(des=True, features=True, layout="1097"), "--des needs"),
                   (dict(features=True), "--features needs"), (dict(features=True, layout="classic"), "--features needs")):
    assert phrase in refused(ko_bake.package, "games/demo", classic, str(B / "separate"), None,
                             character_assets=B / "other-client", **kw), kw
    assert not (B / "separate").exists(), kw
print("PASS a package whose player comes from another install refuses --des, and --features unless it is the "
      "1097 Moradon layout, before writing anything")
