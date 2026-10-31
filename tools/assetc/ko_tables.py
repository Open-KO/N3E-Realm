"""Operator-local import of reference server tables (PQ-054, D-161).

The rows are the operator's own: JSON exports of their reference database under
`build/` (by default the ones `tools/ko-reference/inspect_db.py --table T`
writes, `build/ko-completion/database-parity/<T>.json`: a list of row objects,
`FOR JSON PATH`), never committed. This module checks each table against how
the supplied AI server binds and loads it, puts its rows in one canonical
order and names them by a canonical digest, so the NPC and spawn cooks
(PQ-069, PQ-219) depend on the values alone. It writes nothing into a package;
`main` writes a checked extract under `build/ko-reference/`.

Binary meaning (`AI Server-official.exe`, binary unless noted; record:
docs/implementation/evidence/pq-054-reference-data-import.md):

* The recordsets bind columns by name with four field helpers: `0044ce2b` (a
  NULL stores `0x7ee4` in a 4-byte field), `0044cf4c` (`0x4a4d4120`, 4 bytes),
  `0044d06e` (`0xff`, one byte) and `0044ca70` (text, the callers pass 255 as
  its maximum; a NULL empties it). Reading them as MFC's RFX_Int, RFX_Long,
  RFX_Byte and RFX_Text is an inference from those constants.
  K_MONSTER (`0041737b`) and K_NPC (`0042b3dc`) bind the same 46 columns,
  K_NPCPOS (`0042ad3b`) 20; `COLUMNS` lists them in binding order.
* The template loads `00437fb4` (K_MONSTER) and `00438479` (K_NPC) narrow the
  RFX_Int columns to shorts, fail on an empty table (`MONSTER_DB_Empty`,
  `NPC_DB_Empty`) and stop on a name longer than 29 bytes (`0x1d`,
  `Monster_Name_Length_overflow`). They file templates by `sSid` in a map whose
  insert (`0043e3ef`) refuses an existing key and the load deletes the new
  template, so of two rows with one `sSid` the first in storage order wins.
* The spawn load `0043893e` (K_NPCPOS) skips a row whose SpecialType is 7 and
  TrapNumber at least 2, makes NumNPC NPCs from every other row of its server,
  looks the template up by NpcID narrowed to a short (`MOVSX` at `00438b1e`
  and `00438b3a`) in the K_MONSTER map when ActType < 100 and in the K_NPC
  map otherwise (storing ActType - 100), and fails the whole load when the
  template is missing (`Npc id` error `004cae70`) or the stored act type is 2
  or 3 with DotCnt 0 (`Path type Error`, `004cae14`). It stores the eight
  rectangle and limit columns as shorts.

So a value is accepted only when it is the declared column type and fits the
field the binary keeps it in; a NULL (a missing key: FOR JSON PATH omits NULL
columns) only in a column the database declares nullable, where the binary
would read an RFX pseudo-null value instead. A table that would fail or
depend on storage order in KO's load (empty, a duplicate `sSid`, a spawn row
without its template, a path type error) is refused. Text must be printable
ASCII, because the byte length the binary checks depends on a code page the
export does not record.
"""

import hashlib
import json
import pathlib
import sys

EXPORT = pathlib.Path("build/ko-completion/database-parity")
OUT = pathlib.Path("build/ko-reference")
LIMIT = 64 * 1024 * 1024  # bytes per export file

BYTE = (0, 255)
SHORT = (-32768, 32767)
LONG = (-2 ** 31, 2 ** 31 - 1)

# K_MONSTER and K_NPC: one binding function body each (0041737b, 0042b3dc).
# (name, kind, bound) with kind "int" (bound = inclusive range) or "text"
# (bound = longest value in bytes); the database declares only strName nullable.
_TEMPLATE = (
    ("sSid", "int", SHORT), ("strName", "text", 29), ("sPid", "int", SHORT),
    ("sSize", "int", SHORT), ("iWeapon1", "int", LONG), ("iWeapon2", "int", LONG),
    ("byGroup", "int", BYTE), ("byActType", "int", BYTE), ("byType", "int", BYTE),
    ("byFamily", "int", BYTE), ("byRank", "int", BYTE), ("byTitle", "int", BYTE),
    ("iSellingGroup", "int", LONG), ("sLevel", "int", SHORT), ("iExp", "int", LONG),
    ("iLoyalty", "int", LONG), ("iHpPoint", "int", LONG), ("sMpPoint", "int", SHORT),
    ("sAtk", "int", SHORT), ("sAc", "int", SHORT), ("sHitRate", "int", SHORT),
    ("sEvadeRate", "int", SHORT), ("sDamage", "int", SHORT), ("sAttackDelay", "int", SHORT),
    ("bySpeed1", "int", BYTE), ("bySpeed2", "int", BYTE), ("sStandtime", "int", SHORT),
    ("iMagic1", "int", LONG), ("iMagic2", "int", LONG), ("iMagic3", "int", LONG),
    ("sFireR", "int", SHORT), ("sColdR", "int", SHORT), ("sLightningR", "int", SHORT),
    ("sMagicR", "int", SHORT), ("sDiseaseR", "int", SHORT), ("sPoisonR", "int", SHORT),
    ("sLightR", "int", SHORT), ("sBulk", "int", SHORT), ("byAttackRange", "int", BYTE),
    ("bySearchRange", "int", BYTE), ("byTracingRange", "int", BYTE), ("iMoney", "int", LONG),
    ("sItem", "int", SHORT), ("byDirectAttack", "int", BYTE), ("byMagicAttack", "int", BYTE),
    ("byMoneyType", "int", BYTE),
)
# K_NPCPOS (0042ad3b). NpcID is an int column bound with RFX_Long but looked up
# as a short; the rectangle and limits are ints stored as shorts; byDirection is
# an int column bound with RFX_Byte. path (text, at most 255) is nullable.
_SPAWN = (
    ("ZoneID", "int", SHORT), ("NpcID", "int", SHORT), ("ActType", "int", BYTE),
    ("RegenType", "int", BYTE), ("DungeonFamily", "int", BYTE), ("SpecialType", "int", BYTE),
    ("TrapNumber", "int", BYTE), ("LeftX", "int", SHORT), ("TopZ", "int", SHORT),
    ("RightX", "int", SHORT), ("BottomZ", "int", SHORT), ("LimitMinX", "int", SHORT),
    ("LimitMinZ", "int", SHORT), ("LimitMaxX", "int", SHORT), ("LimitMaxZ", "int", SHORT),
    ("NumNPC", "int", BYTE), ("RegTime", "int", SHORT), ("byDirection", "int", BYTE),
    ("DotCnt", "int", BYTE), ("path", "text", 255),
)
# MAGIC_TYPE2 (PQ-422, D-219): the AI server's binding 004107ab (iNum with
# 0044cf4c, HitType and NeedArrow with 0044d06e, the rest with 0044ce2b) and
# load 0043b638, which narrows HitRate, AddDamage, AddDamagePlus and AddRange
# to shorts (record +6, +8, +0xe, +10), refuses an empty table
# (MagicType2_Empty) and keeps the first row of an iNum (0043ea73's refused
# insert frees the new record); the import refuses a duplicate iNum instead,
# as for sSid, since the export does not keep storage order. Name and
# Description (text, bound but never read by a rule here) are not checked and
# are reported as ignored.
_MAGIC_TYPE2 = (
    ("iNum", "int", LONG), ("HitType", "int", BYTE), ("HitRate", "int", SHORT),
    ("AddDamage", "int", SHORT), ("AddDamagePlus", "int", SHORT), ("AddRange", "int", SHORT),
    ("NeedArrow", "int", BYTE),
)
COLUMNS = {"K_MONSTER": _TEMPLATE, "K_NPC": _TEMPLATE, "K_NPCPOS": _SPAWN, "MAGIC_TYPE2": _MAGIC_TYPE2}
NULLABLE = {"K_MONSTER": {"strName"}, "K_NPC": {"strName"}, "K_NPCPOS": {"path"}, "MAGIC_TYPE2": set()}
# Tables whose loads file rows by a key and keep the first (0043e3ef, 0043ea73);
# canonical() refuses a duplicate key.
KEYS = {"K_MONSTER": "sSid", "K_NPC": "sSid", "MAGIC_TYPE2": "iNum"}


def _strict(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("a row object repeats a key")
    return dict(pairs)


def _constant(name):
    raise ValueError("non-standard JSON constant " + name)


def _value(table, column, kind, bound, row):
    if column not in row or row[column] is None:
        if column in NULLABLE[table]:
            return None
        raise ValueError("%s: %s is NULL in a NOT NULL column" % (table, column))
    value = row[column]
    if kind == "int":
        if type(value) is not int:
            raise ValueError("%s: %s is not an integer: %r" % (table, column, value))
        if not bound[0] <= value <= bound[1]:
            raise ValueError("%s: %s %d is outside [%d, %d]" % (table, column, value, *bound))
        return value
    if type(value) is not str:
        raise ValueError("%s: %s is not text: %r" % (table, column, value))
    if any(not " " <= ch <= "~" for ch in value):
        raise ValueError("%s: %s is not printable ASCII: %r" % (table, column, value))
    if len(value) > bound:
        raise ValueError("%s: %s is longer than %d bytes: %r" % (table, column, bound, value))
    return value


def _order(row):
    # SQL NULL sorts first, as SQL Server orders it; a column holds one kind.
    return tuple((0,) if v is None else (1, v) for v in row)


def canonical(table, rows):
    """The table's checked rows as lists in binding order, sorted by the full
    tuple, and their digest. `rows` are export row objects."""
    if table not in COLUMNS:
        raise ValueError("no binary-checked binding for table %r" % table)
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("%s export is not a list of row objects" % table)
    if not rows:
        raise ValueError("%s is empty (the AI server's load fails)" % table)
    spec = COLUMNS[table]
    out = sorted(([_value(table, c, k, b, r) for c, k, b in spec] for r in rows), key=_order)
    if table in KEYS:
        at = [c for c, _, _ in spec].index(KEYS[table])
        seen = set()
        for row in out:
            if row[at] in seen:
                raise ValueError("%s has two rows with %s %d (KO keeps the first in storage order)"
                                 % (table, KEYS[table], row[at]))
            seen.add(row[at])
    columns = [c for c, _, _ in spec]
    return out, digest(table, columns, out)


def digest(table, columns, rows):
    """SHA-256 of the canonical table spelled one way (no spaces, ASCII)."""
    text = json.dumps({"table": table, "columns": columns, "rows": rows},
                      separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def load(table, export=EXPORT):
    """The checked table from `<export>/<table>.json`, or None when the file is
    absent: {table, columns, rows, digest, source, sha256, ignored}. The file's
    SHA-256 is provenance; `digest` names the values."""
    if table not in COLUMNS:
        raise ValueError("no binary-checked binding for table %r" % table)
    path = pathlib.Path(export) / (table + ".json")
    if not path.is_file():
        return None
    if path.stat().st_size > LIMIT:
        raise ValueError("%s exceeds %d MiB" % (path, LIMIT // (1024 * 1024)))
    data = path.read_bytes()
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_strict, parse_constant=_constant)
    except UnicodeDecodeError as error:
        raise ValueError("%s is not UTF-8: %s" % (path, error)) from None
    rows, name = canonical(table, raw)
    bound = {c for c, _, _ in COLUMNS[table]}
    ignored = sorted({k for r in raw for k in r} - bound)
    return {"table": table, "columns": [c for c, _, _ in COLUMNS[table]], "rows": rows,
            "digest": name, "source": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "ignored": ignored}


def spawn_skipped(spawn):
    """0043893e skips a K_NPCPOS row whose SpecialType is 7 and TrapNumber >= 2."""
    return spawn["SpecialType"] == 7 and spawn["TrapNumber"] >= 2


def spawn_template(spawn):
    """(template table, stored act type) for a K_NPCPOS row: ActType < 100 is a
    K_MONSTER template, else a K_NPC one with ActType - 100 stored."""
    if spawn["ActType"] < 100:
        return "K_MONSTER", spawn["ActType"]
    return "K_NPC", spawn["ActType"] - 100


def rows_as_dicts(table):
    """A loaded table's rows as {column: value} in canonical order."""
    return [dict(zip(table["columns"], row)) for row in table["rows"]]


def check_spawns(spawns, monsters, npcs):
    """Refuse a K_NPCPOS table whose load would fail in KO: a used row (not
    skipped, NumNPC > 0) without its template, or with stored act type 2 or 3
    and DotCnt 0. Returns the number of used rows."""
    ids = {"K_MONSTER": {r["sSid"] for r in rows_as_dicts(monsters)},
           "K_NPC": {r["sSid"] for r in rows_as_dicts(npcs)}}
    used = 0
    for spawn in rows_as_dicts(spawns):
        if spawn_skipped(spawn) or spawn["NumNPC"] == 0:
            continue
        source, act = spawn_template(spawn)
        if spawn["NpcID"] not in ids[source]:
            raise ValueError("K_NPCPOS zone %d NpcID %d (ActType %d) has no %s template"
                             % (spawn["ZoneID"], spawn["NpcID"], spawn["ActType"], source))
        if act in (2, 3) and spawn["DotCnt"] == 0:
            raise ValueError("K_NPCPOS zone %d NpcID %d: act type %d needs a path (DotCnt 0)"
                             % (spawn["ZoneID"], spawn["NpcID"], act))
        used += 1
    return used


TABLES = ("K_MONSTER", "K_NPC", "K_NPCPOS")


def extract(export=EXPORT, out=OUT):
    """Check the three NPC tables from `export` (all must be present), cross-check
    the spawns, and write `<out>/<table>.json` and `<out>/manifest.json`."""
    tables = {}
    for name in TABLES:
        table = load(name, export)
        if table is None:
            raise ValueError("%s/%s.json is missing" % (export, name))
        tables[name] = table
    used = check_spawns(tables["K_NPCPOS"], tables["K_MONSTER"], tables["K_NPC"])
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"tables": {}, "spawn_rows_used": used}
    for name, table in tables.items():
        body = {k: table[k] for k in ("table", "columns", "rows", "digest")}
        (out / (name + ".json")).write_text(
            json.dumps(body, separators=(",", ":"), ensure_ascii=True) + "\n")
        manifest["tables"][name] = {k: table[k] for k in ("digest", "source", "sha256", "ignored")}
        manifest["tables"][name]["rows"] = len(table["rows"])
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Check and canonicalize the operator's "
                                     "K_MONSTER, K_NPC and K_NPCPOS exports (PQ-054).")
    parser.add_argument("--export", type=pathlib.Path, default=EXPORT)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    args = parser.parse_args(argv)
    try:
        manifest = extract(args.export, args.out)
    except ValueError as error:
        print("REFUSED " + str(error), file=sys.stderr)
        return 2
    for name, entry in sorted(manifest["tables"].items()):
        print("%s rows=%d digest=%s file_sha256=%s" % (name, entry["rows"], entry["digest"], entry["sha256"]))
    print("K_NPCPOS rows used=%d; written to %s" % (manifest["spawn_rows_used"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
