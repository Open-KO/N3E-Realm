"""Select a KO zone's map files by its Zones.tbl key, as the client's world loader does.

Offline only: this reads the player's own client data (`Data/Zones.tbl.csv`, the
decoded table, and the files it names) and returns local paths for the bake. It
holds no KO value of its own; the key comes from the caller (210 is Moradon).

Client behaviour (`KnightOnLine.exe`, PQ-213 and PQ-216, binary):

* `005a3110` takes the runtime zone key (`0046c9d0`, `zone x 10 + sub-zone`) and
  finds its row in the table map (`0046d8c0`); no row stops the load
  (`005a3161`-`005a317f`). The row holds the key at `+0` and 16-byte string
  objects (data pointer at `+4`) from `+0x4`, so column `c` sits at
  `+0x4 + (c - 2) * 0x10`.
* It loads the terrain from column 2 (`+0x4`, `005a31b8`), compares the terrain's
  name (`+0x4c24`, read by `0059a010`) with column 3 (`+0x14`) by `lstrcmpiA`
  (`005a31cc`-`005a31f9`), reads the colour map from column 4 (`+0x24`, `0059eff0`
  at `005a3243`), loads the objects from column 6 (`+0x44`, `005a3252`) and
  compares their name (`+0x40074`) with column 3 the same way (`005a325b`-`005a3283`).
* Column 7 (`+0x54`) is compared with `Reserved` (`006d75b4`) by a plain string
  compare (`005a32c6`-`005a32ec`); only when it differs is an OPDEXT loaded into
  the same shape manager (`005b4ef0`, `005a3324`) and the object name, which the
  OPDEXT may replace, checked against column 3 again; a mismatch appends the
  column 6 file name (`005a3329`-`005a3396`). `ko_opdext` reads and merges it
  (PQ-229).
* A mismatch appends the column 2 or column 6 file name to `Invalid Map Files`
  (`006d75c0`); if anything was appended the terrain and objects are released and
  the rest of the load is skipped (`005a339b` onwards).
* Column 8 names the zone's minimap (`00562b60` via `005ca842`, PQ-035).
* Column 5 (`+0x38`) names the terrain light maps, which `0059ba90` opens and
  `0059c450` reads for the patches around the eye (PQ-385, PQ-387;
  `ko_light_maps`). The client opens it with CreateFileA and tests the handle
  against 0 only; n3e refuses a missing file as it does the others.

The 1097 layout (PQ-274, D-170; `select(..., layout="1097")`). The 1097
client's `Data/Zones.tbl` has no decoded CSV beside it; `ko_tbl` decrypts and
parses it as the 1298 client parses its own (`006113b0`, `0044f670`,
`006264d0`; binary for 1298). Its 15 column types are exactly the 1298 table's
columns 1, 2, 4, 5, 6 and 8-17 (local-asset), so it is read as that layout
without the name and OPDEXT columns: key, terrain (column 2), colour map
(column 3), objects (column 5) and overview map (column 6), an inference the
packed 1097 exe cannot confirm. Its GTD and OPD have no header (PQ-222), so
they carry no name either and `005a3110`'s name check has nothing to compare;
the selection records it as not applicable and requires both files to be
headerless. Its keys are the zone ids (1, 2, 21, ...; PQ-214), not zone x 10.

A layout the table does not name (PQ-223, D-171; `select(..., stem=...)`). The
pinned 1298 install ships `Zones\\moradon.*` beside the `Zones\\Moradon_xmas.*` its
key 210 names. `005a3110` reads its zone files from the row and the exe holds
no zone file string (binary); that the 1298 client reaches maps only through
a row, and so never loads these, is inference (a path built at run time is not
ruled out).
`stem` rewrites the row before anything is resolved: column 3 becomes `stem`,
and every column naming `Zones\\<column 3>.<ext>` names `Zones\\<stem>.<ext>`
instead, so the files, the name check and the provenance all follow the
rewritten row. For key 210 and `Moradon` that row, less its column 7 (OPDEXT,
which the 1264 table lacks), is the 1264 client's own key 210 row, and it
agrees with the 1453 client's up to column 23 (local-asset, PQ-223). A path column naming any other file refuses the rewrite.

n3e differences, all in the fail-closed direction: a missing, ambiguous or unsafe
file (including the OPDEXT, which the client skips when it cannot open it), a
duplicate key and a malformed OPDEXT (`ko_opdext`) are refused.
Trailing spaces are trimmed from the path columns (a Win32 file open ignores them;
inference), and table paths resolve case-insensitively, as Windows paths do.
"""

import csv
import hashlib
import re

from common import *
import ko_opdext
import ko_shapes
import ko_tbl
import ko_terrain

RESERVED = "Reserved"
# Zero-based CSV columns of the table's one-based columns 1-8.
KEY, GTD, NAME, TCT, TLT, OPD, OPDEXT, MINIMAP = 0, 1, 2, 3, 4, 5, 6, 7
# PQ-274: the 1097 table's column types (local-asset) and the zero-based columns
# the selection reads from it.
LEGACY_TYPES = (6, 7, 7, 7, 7, 7, 7, 5, 5, 7, 7, 5, 7, 8, 7)
LEGACY = {"gtd": 1, "tct": 2, "opd": 4, "minimap": 5}
# PQ-387: the 1097 table's fourth column names Zones\<stem>.tlt (local-asset),
# 1298's column 5 by the same layout reading.
LEGACY_TLT = 3
LAYOUTS = ("1298", "1097")


def table(assets):
    """The decoded Zones.tbl rows (header first) and the table's path."""
    path = pathlib.Path(assets) / "Data" / "Zones.tbl.csv"
    if not path.is_file():
        raise ValueError("no Zones.tbl.csv under %s" % pathlib.Path(assets))
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        return path, list(csv.reader(handle))


def legacy_table(assets):
    """The 1097 `Data/Zones.tbl` (encrypted, no CSV): rows as text, header first,
    and the table's path. Refuses any other column layout."""
    path = resolve(assets, "Data/Zones.tbl", "the 1097 layout")
    types, rows = ko_tbl.load(path)
    if tuple(types) != LEGACY_TYPES:
        raise ValueError("%s has column types %s, not the 1097 layout's %s" % (path, types, list(LEGACY_TYPES)))
    header = ["%d - type %d" % (i + 1, t) for i, t in enumerate(types)]
    return path, [header] + [[repr(v) if isinstance(v, float) else str(v) for v in r] for r in rows]


def row(rows, key):
    """The one row whose column 1 is `key`; refuse a missing or repeated key."""
    if type(key) is not int:
        raise ValueError("zone key must be an integer")
    found = []
    for candidate in rows[1:]:
        try:
            if candidate and int(candidate[KEY].strip()) == key:
                found.append(candidate)
        except ValueError:
            continue
    if not found:
        raise ValueError("Zones.tbl has no row for zone key %d" % key)
    if len(found) > 1:
        raise ValueError("Zones.tbl has %d rows for zone key %d" % (len(found), key))
    if len(found[0]) <= MINIMAP:
        raise ValueError("Zones.tbl row %d has %d columns, fewer than 8" % (key, len(found[0])))
    return found[0]


def resolve(assets, value, where):
    """A table path below the client root, trailing spaces trimmed, any case."""
    text = value.rstrip(" ")
    parts = text.replace("\\", "/").split("/")
    if not text or any(p in ("", ".", "..") or ":" in p or p != p.strip() for p in parts):
        raise ValueError("%s names %r, which is not a relative client path" % (where, value))
    here = pathlib.Path(assets)
    for part in parts:
        matches = [c.name for c in here.iterdir() if c.name.lower() == part.lower()] if here.is_dir() else []
        if len(matches) != 1:
            raise ValueError("%s names %r, which %s under %s" % (
                where, value, "is ambiguous" if matches else "is not a local file", pathlib.Path(assets)))
        here = here / matches[0]
    if not here.is_file():
        raise ValueError("%s names %r, which is not a file" % (where, value))
    return here


STEM = re.compile(r"[A-Za-z0-9_]{1,64}")


def restem(found, stem):
    """PQ-223 (D-171): the row with its map files renamed from column 3's stem to `stem`.

    Returns the rewritten row and {column: [old, new]} for each changed column.
    Column 3 must be a plain stem and every path column (2, 4, 5, 6, 8, and 7
    unless `Reserved`) must name `Zones\\<column 3>.<ext>`; anything else is refused."""
    if not isinstance(stem, str) or not STEM.fullmatch(stem):
        raise ValueError("a zone file stem is letters, digits and _, not %r" % (stem,))
    old = found[NAME]
    if not STEM.fullmatch(old):
        raise ValueError("Zones.tbl row %s column 3 is %r, not a file stem" % (found[KEY], old))
    named = re.compile(r"^( *Zones\\)" + re.escape(old) + r"(\.[A-Za-z0-9]{1,8} *)$", re.IGNORECASE)
    paths = [GTD, TCT, TLT, OPD, MINIMAP] + ([] if found[OPDEXT] == RESERVED else [OPDEXT])
    for index in paths:
        if not named.match(found[index]):
            raise ValueError("Zones.tbl row %s column %d names %r, not Zones\\%s.*; refusing to rename it"
                             % (found[KEY], index + 1, found[index], old))
    rewritten, changed = list(found), {}
    for index, value in enumerate(found):
        new = stem if index == NAME else named.sub(lambda m: m.group(1) + stem + m.group(2), value)
        if new != value:
            rewritten[index] = new
            changed[str(index + 1)] = [value, new]
    return rewritten, changed


def check_names(key, column_3, gtd, opd, opdext=None):
    """`005a3110`: both internal names must equal column 3, ignoring case.

    With an OPDEXT (column 7 not `Reserved`) it is read against the OPD and merged
    (`ko_opdext`), and the shape manager's name after the merge must equal column 3
    too (`005a3329`-`005a3355`). Returns the names and the merge (or None); raises
    `Invalid Map Files` listing each file that differs, as the client does before
    it releases the map.
    """
    names = {"gtd": ko_terrain.header_name(gtd), "opd": ko_shapes.header_name(opd)}
    bad = ["%s is named %r" % (path, names[kind]) for kind, path in (("gtd", gtd), ("opd", opd))
           if names[kind].lower() != column_3.lower()]
    extension = None
    if opdext is not None:
        collision = ko_shapes.load_collision(opd)
        ext = ko_opdext.load(opdext, collision)
        extension = {"read": ext, "merged": ko_opdext.merge(collision, ext)}
        merged_name = extension["merged"]["name"]
        if merged_name.lower() != column_3.lower():
            # The client appends the column 6 name again (005a3357).
            bad.append("%s is named %r after %s" % (opd, merged_name, opdext))
    if bad:
        raise ValueError("Invalid Map Files: zone %d column 3 is %r, but %s"
                         % (key, column_3, "; ".join(bad)))
    return names, extension


def select(assets, key, layout="1298", stem=None):
    """Resolve and check one zone's GTD, TCT, OPD, OPDEXT (unless `Reserved`) and minimap.

    `layout="1097"` reads the 1097 client's table instead (`select_1097`).
    `stem` selects the same install's files of another name through the row
    `restem` writes (PQ-223, D-171); the provenance records the rewrite."""
    if layout not in LAYOUTS:
        raise ValueError("unknown Zones.tbl layout %r" % (layout,))
    if layout == "1097":
        if stem is not None:
            raise ValueError("a file stem applies to the 1298 layout only")
        return select_1097(assets, key)
    assets = pathlib.Path(assets)
    path, rows = table(assets)
    found = row(rows, key)
    variant = None
    if stem is not None:
        original = found
        found, changed = restem(found, stem)
        variant = {"stem": stem, "table_stem": original[NAME], "rewritten_columns": changed,
                   "rule": "column 3 and every Zones\\<column 3>.<ext> path renamed; nothing else changed"}

    def column(index):
        return resolve(assets, found[index], "Zones.tbl row %d column %d" % (key, index + 1))

    files = {"gtd": column(GTD), "tct": column(TCT), "opd": column(OPD), "minimap": column(MINIMAP)}
    tlt = column(TLT)
    opdext = None if found[OPDEXT] == RESERVED else column(OPDEXT)
    names, extension = check_names(key, found[NAME], files["gtd"], files["opd"], opdext)
    record = {
        "zone_key": key,
        "zones_table": str(path),
        "zones_table_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "columns": {str(i + 1): found[i] for i in (GTD, NAME, TCT, OPD, OPDEXT, MINIMAP)},
        "files": {kind: str(files[kind]) for kind in ("gtd", "tct", "opd", "minimap")},
        "names": names,
        "opdext": "skipped: column 7 is Reserved (005a32c6)",
        "binary": "KnightOnLine.exe 005a3110 (row, names, Reserved), 0059eff0 (colour map)",
    }
    # PQ-387 (D-204): kept apart from "files" and "columns", whose pinned
    # entries stay as they were.
    record["light_maps"] = {"column": "5", "value": found[TLT], "file": str(tlt),
                            "binary": "KnightOnLine.exe 0059ba90 (row +0x38), 0059c450"}
    if opdext is not None:
        record["files"]["opdext"] = str(opdext)
        record["opdext"] = ko_opdext.provenance(opdext, extension["read"], extension["merged"])
    if variant is not None:
        # The default record stays exactly as it was: its cooks are pinned.
        record["variant"] = variant
    return dict(files, tlt=tlt, key=key, row=found, table=path, assets=assets, names=names,
                opdext=opdext, extension=extension, provenance=record, layout="1298",
                headerless=False, zone_id=key // 10, stem=stem)


def select_1097(assets, key):
    """The 1097 layout's GTD, TCT, OPD and minimap for `key` (see the module notes).

    Both zone files must be headerless (`ko_terrain.header_samples` and
    `ko_shapes.load_collision` with `headerless=True` refuse a headed file).
    There is no name to check and no OPDEXT column."""
    assets = pathlib.Path(assets)
    path, rows = legacy_table(assets)
    found = row(rows, key)
    files = {kind: resolve(assets, found[index], "Zones.tbl row %d column %d" % (key, index + 1))
             for kind, index in LEGACY.items()}
    tlt = resolve(assets, found[LEGACY_TLT], "Zones.tbl row %d column %d" % (key, LEGACY_TLT + 1))
    for kind in ("gtd", "opd"):
        try:
            if kind == "gtd":
                ko_terrain.header_samples(files[kind], headerless=True)
            else:
                ko_shapes.load_collision(files[kind], headerless=True)
        except ValueError as error:
            raise ValueError("Zones.tbl row %d: %s: %s" % (key, files[kind], error))
    record = {
        "zone_key": key,
        "layout": "1097",
        "zones_table": str(path),
        "zones_table_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "columns": {str(i + 1): found[i] for i in sorted(LEGACY.values())},
        "files": {kind: str(files[kind]) for kind in ("gtd", "tct", "opd", "minimap")},
        "names": "not applicable: the 1097 table has no name column and its GTD and OPD no header",
        "opdext": "not applicable: the 1097 table has no OPDEXT column",
        "binary": "KnightOnLine.exe 1298 006113b0, 0044f670, 006264d0 (table cipher and parse); "
                  "the column meanings and the absent name check are inferred for the packed 1097 exe",
        "light_maps": {"column": str(LEGACY_TLT + 1), "value": found[LEGACY_TLT], "file": str(tlt),
                       "binary": "the 1298 reading (0059ba90, 0059c450), inferred for the packed 1097 exe"},
    }
    return dict(files, tlt=tlt, key=key, row=found, table=path, assets=assets, names=None, opdext=None,
                extension=None, provenance=record, layout="1097", headerless=True, zone_id=key)
