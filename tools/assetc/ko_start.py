"""A KO zone's start areas from START_POSITION, for the bake's start survey (PQ-217).

The rows are the operator's own: a START_POSITION export of their reference
database under `build/` (by default the one `tools/ko-reference/inspect_db.py`
writes, `build/ko-completion/database-parity/START_POSITION.json`: a JSON list
of row objects), never committed. The bake records its SHA-256 and refuses a
map that needs it when it is absent. Their meaning is the server's
(`Ebenezer-official.exe`, binary):

* `004325df` loads each row into a 0x18-byte record: ZoneID at `+0`, the Karus
  start at `+4`/`+6`, the El Morad start at `+8`/`+0xa` (shorts) and the ranges
  at `+0x14`/`+0x15` (bytes).
* `004c6523` places a player of nation 1 (user data `+0x4c`) at the Karus start
  and of nation 2 at the El Morad start (zone 30 and the war cases aside), each
  axis `start + rand(0, range)` through `00422261`, which returns an integer
  in `[min, max]`, both ends included. A start area is therefore
  `[X, X + bRangeX] x [Z, Z + bRangeZ]` in KO metres, on one side of the point.

The server zone is the Zones.tbl key's tens (`0046c9d0`: key = zone x 10 +
sub-zone). The 1097 client's table is keyed by the zone id itself (PQ-214,
local-asset); its caller passes `zone=` (PQ-274, D-170). KO (x, z) maps to n3e (x - half, half - z) for a map of extent
`2 x half` centred on the origin, as for the Moradon bake (`ko_collision`).
"""

import hashlib
import json

from common import *

EXPORT = pathlib.Path("build/ko-completion/database-parity/START_POSITION.json")
NATIONS = {"karus": ("sKarusX", "sKarusZ"), "elmorad": ("sElmoradX", "sElmoradZ")}
# n3e has no nation field (GAPS "PvP and hostility"), so a package starts every
# player at one nation's start: the zone's own, whose village it is (zone 1
# Karus, Breth; zone 2 El Morad, Piana; PQ-213). An n3e package choice, not KO
# data. A zone with a row but no entry here is refused.
PACKAGE_NATION = {1: "karus", 2: "elmorad"}
# The columns the bake reads from a zone's row (PQ-051: what `row_digest` covers).
COLUMNS = ("ZoneID", "sKarusX", "sKarusZ", "sElmoradX", "sElmoradZ", "bRangeX", "bRangeZ")


def load(export=EXPORT):
    """The export's rows and its SHA-256; (None, None) when the file is absent."""
    path = pathlib.Path(export)
    if not path.is_file():
        return None, None
    data = read(path)
    rows = json.loads(data)
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("%s is not a list of START_POSITION rows" % path)
    return rows, hashlib.sha256(data).hexdigest()


def row(key, rows, zone=None):
    """The START_POSITION row for a Zones.tbl key, or None when there is none.

    `zone` is the server zone when it is not the key's tens (the 1097 keys)."""
    if type(key) is not int or key < 0:
        raise ValueError("zone key must be a non-negative integer")
    zone = key // 10 if zone is None else zone
    # PQ-051 review: ZoneID is type-checked like the other read columns, so a
    # 1.0 or true does not stand for zone 1 (and change the row digest).
    if any(r.get("ZoneID") == zone and type(r.get("ZoneID")) is not int for r in rows):
        raise ValueError("START_POSITION zone %d: ZoneID is not an integer" % zone)
    found = [r for r in rows if r.get("ZoneID") == zone]
    if len(found) > 1:
        raise ValueError("START_POSITION has %d rows for zone %d" % (len(found), zone))
    if not found:
        return None
    found = found[0]
    for column in COLUMNS[1:]:
        if type(found.get(column)) is not int:
            raise ValueError("START_POSITION zone %d: %s is not an integer" % (zone, column))
    if not (0 <= found["bRangeX"] <= 255 and 0 <= found["bRangeZ"] <= 255):
        raise ValueError("START_POSITION zone %d: a range is not a byte" % zone)
    return found


def row_digest(found):
    """PQ-051: the SHA-256 of the columns a zone's row gives the bake, spelled one
    way (sorted keys, no spaces). The same row exported in another row order, key
    order or JSON layout has the same digest, where the file's hash (`load`)
    changes; the cooked release depends on the values alone."""
    canonical = json.dumps({c: found[c] for c in COLUMNS}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def nation(key, zone=None):
    """The nation whose start a zone's package uses (`zone` as for `row`)."""
    zone = key // 10 if zone is None else zone
    if zone not in PACKAGE_NATION:
        raise ValueError("zone %d has no package nation (ko_start.PACKAGE_NATION)" % zone)
    return PACKAGE_NATION[zone]


def areas(found, extent):
    """Each nation's start area as an n3e rectangle (x0, z0, x1, z1).

    `extent` is the map's side in metres. An area that leaves the map is refused:
    a start nobody can reach is not narrowed to the part that fits.
    """
    half = extent / 2.0
    out = {}
    for name, (cx, cz) in NATIONS.items():
        x, z, rx, rz = found[cx], found[cz], found["bRangeX"], found["bRangeZ"]
        if x < 0 or z < 0 or x + rx > extent or z + rz > extent:
            raise ValueError("the %s start [%d, %d] + [%d, %d] leaves the %g m map"
                             % (name, x, z, rx, rz, extent))
        out[name] = (x - half, half - (z + rz), x + rx - half, half - z)
    return out


def to_ko(position, extent):
    """An n3e position's KO (x, z), for reports."""
    half = extent / 2.0
    return [position[0] + half, half - position[2]]
