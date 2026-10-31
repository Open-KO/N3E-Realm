"""PQ-054: the operator-local import of K_MONSTER, K_NPC and K_NPCPOS (ko_tables).

Synthetic rows only are committed; they are original values, not reference
rows. With the operator's own export in `ko_tables.EXPORT` (never committed;
SKIP without it) the import is also run on it, and when its canonical digests
are the pinned OpenKO v0.1.2 ones its counts are checked. `tests/ko_terrain.py`
(so `make test`) runs this file; it also runs alone. (Named apart from
`tools/assetc/ko_tables.py`, so `import ko_tables` never finds this file.)
"""
import contextlib, io, json, random, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import ko_tables

B = Path("build/pq054-test")
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)


def template(sid, **kw):
    row = {c: 1 for c, _, _ in ko_tables.COLUMNS["K_MONSTER"]}
    row.update(sSid=sid, strName="Sample %d" % sid, sPid=sid + 1)
    row.update(kw)
    return row


def spawn(npc, act=1, **kw):
    row = {c: 0 for c, _, _ in ko_tables.COLUMNS["K_NPCPOS"]}
    del row["path"]  # FOR JSON PATH omits a NULL column
    row.update(ZoneID=7, NpcID=npc, ActType=act, LeftX=10, TopZ=20, RightX=30, BottomZ=40,
               NumNPC=3, RegTime=30)
    row.update(kw)
    return row


def export(name, tables, indent=None):
    folder = B / name
    folder.mkdir(parents=True, exist_ok=True)
    for table, rows in tables.items():
        (folder / (table + ".json")).write_text(json.dumps(rows, indent=indent))
    return folder


def refused(phrase, table, rows):
    folder = export("refused", {table: rows})
    try:
        ko_tables.load(table, folder)
    except ValueError as error:
        assert phrase in str(error), (phrase, str(error))
        return
    raise AssertionError("accepted %s: %s" % (table, phrase))


monsters = [template(30), template(10), template(20, strName=None)]
del monsters[1]["strName"]  # a missing key is NULL, as an explicit null is
npcs = [template(500, byType=163), template(400)]
spawns = [spawn(10), spawn(20, LeftX=5), spawn(10), spawn(400, act=100, NumNPC=1),
          spawn(500, act=102, DotCnt=2, path="0010002000300040"),
          spawn(999, SpecialType=7, TrapNumber=2),  # skipped by 0043893e
          spawn(998, NumNPC=0),                      # makes no NPC
          # Equal but for path, the NULL one exported last: the sort must put it first.
          spawn(30, LeftX=6, DotCnt=1, path="00100020"), spawn(30, LeftX=6, DotCnt=1)]
first = export("first", {"K_MONSTER": monsters, "K_NPC": npcs, "K_NPCPOS": spawns})
tables = {t: ko_tables.load(t, first) for t in ko_tables.TABLES}

# Canonical order: the full tuple in binding order, NULL first; duplicates kept.
m = tables["K_MONSTER"]
assert m["columns"][:3] == ["sSid", "strName", "sPid"] and len(m["columns"]) == 46
assert [r[0] for r in m["rows"]] == [10, 20, 30] and m["rows"][0][1] is None and m["rows"][1][1] is None
p = tables["K_NPCPOS"]
assert len(p["columns"]) == 20 and len(p["rows"]) == 9
pair = [r for r in p["rows"] if r[1] == 30]
assert [r[-1] for r in pair] == [None, "00100020"], pair
assert p["rows"].index(pair[0]) + 1 == p["rows"].index(pair[1])  # adjacent, NULL first
null_last = sorted(p["rows"], key=lambda row: tuple((2,) if v is None else (1, v) for v in row))
assert null_last != p["rows"] and ko_tables.digest("K_NPCPOS", p["columns"], null_last) != p["digest"]
assert p["rows"].count(ko_tables.canonical("K_NPCPOS", [spawn(10)])[0][0]) == 2  # two equal rows stay two
assert all(r[-1] is None for r in p["rows"] if r[1] not in (500, 30))
assert ko_tables.check_spawns(p, m, tables["K_NPC"]) == 7

# The same values in another row order, key order, layout and with an unbound
# column give the same digest; the file hash changes and the column is listed.
shuffled = {}
rng = random.Random(54)
for table, rows in (("K_MONSTER", monsters), ("K_NPC", npcs), ("K_NPCPOS", spawns)):
    rows = [dict(sorted(r.items(), reverse=True), Extra=rng.randrange(9)) for r in rows]
    rng.shuffle(rows)
    shuffled[table] = rows
second = export("second", shuffled, indent=2)
for table in ko_tables.TABLES:
    again = ko_tables.load(table, second)
    assert again["digest"] == tables[table]["digest"] and again["rows"] == tables[table]["rows"], table
    assert again["sha256"] != tables[table]["sha256"] and again["ignored"] == ["Extra"], table
# An explicit null equals a missing key; a changed value changes the digest.
nulls = export("nulls", {"K_MONSTER": [dict(r, strName=None) if r["sSid"] == 10 else r for r in monsters]})
assert ko_tables.load("K_MONSTER", nulls)["digest"] == m["digest"]
assert ko_tables.load("K_MONSTER", export("other", {"K_MONSTER": [dict(monsters[0], iExp=2)] + monsters[1:]}))["digest"] != m["digest"]
assert ko_tables.load("K_NPC", B / "absent") is None

# Refusals: types, ranges, NULLs, text, JSON shape, keys and empty tables.
for phrase, table, rows in (
        ("NULL in a NOT NULL column", "K_MONSTER", [{k: v for k, v in template(1).items() if k != "iHpPoint"}]),
        ("NULL in a NOT NULL column", "K_NPCPOS", [spawn(1, NumNPC=None)]),
        ("not an integer", "K_MONSTER", [template(1, sLevel=True)]),
        ("not an integer", "K_MONSTER", [template(1, sLevel=1.0)]),
        ("not an integer", "K_MONSTER", [template(1, sLevel="1")]),
        ("outside [0, 255]", "K_MONSTER", [template(1, byActType=256)]),
        ("outside [0, 255]", "K_NPCPOS", [spawn(1, byDirection=256)]),     # int column, RFX_Byte
        ("outside [-32768, 32767]", "K_MONSTER", [template(32768)]),
        ("outside [-32768, 32767]", "K_NPCPOS", [spawn(40000)]),           # looked up as a short
        ("outside [-32768, 32767]", "K_NPCPOS", [spawn(1, RightX=-40000)]),  # stored as a short
        ("outside [-2147483648, 2147483647]", "K_NPC", [template(1, iExp=2 ** 31)]),
        ("longer than 29 bytes", "K_MONSTER", [template(1, strName="x" * 30)]),
        ("longer than 255 bytes", "K_NPCPOS", [spawn(1, path="0" * 256)]),
        ("not printable ASCII", "K_NPC", [template(1, strName="Wörm")]),
        ("not text", "K_NPC", [template(1, strName=7)]),
        ("two rows with sSid 5", "K_NPC", [template(5), template(5, iExp=9)]),
        ("is empty", "K_NPCPOS", []),
        ("not a list of row objects", "K_MONSTER", {"rows": [template(1)]}),
        ("not a list of row objects", "K_MONSTER", [template(1), 3])):
    refused(phrase, table, rows)
for text, phrase in (('[{"sSid": 1, "sSid": 2}]', "repeats a key"), ('[{"sSid": NaN}]', "NaN")):
    (B / "refused" / "K_MONSTER.json").write_text(text)
    try:
        ko_tables.load("K_MONSTER", B / "refused")
    except ValueError as error:
        assert phrase in str(error), (phrase, error)
        continue
    raise AssertionError("accepted " + text)
try:
    ko_tables.load("ITEM", first)
except ValueError as error:
    assert "no binary-checked binding" in str(error)
else:
    raise AssertionError("loaded a table without a checked binding")

# Spawns whose KO load would fail are refused; skipped and empty rows are not looked up.
for bad, phrase in (([spawn(11)], "NpcID 11 (ActType 1) has no K_MONSTER template"),
                    ([spawn(10, act=100)], "NpcID 10 (ActType 100) has no K_NPC template"),
                    ([spawn(400, act=101)], None),
                    ([spawn(10, act=2)], "act type 2 needs a path"),
                    ([spawn(400, act=103)], "act type 3 needs a path")):
    rows = ko_tables.load("K_NPCPOS", export("spawns", {"K_NPCPOS": bad}))
    try:
        ko_tables.check_spawns(rows, m, tables["K_NPC"])
    except ValueError as error:
        assert phrase and phrase in str(error), (phrase, error)
        continue
    assert phrase is None, phrase

# The extract writes the canonical tables and a manifest; the same values give
# the same files.
def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ko_tables.main(list(argv))
    return code, out.getvalue() + err.getvalue()


code, text = run("--export", str(first), "--out", str(B / "out1"))
assert code == 0 and "K_NPCPOS rows used=7" in text, text
assert run("--export", str(second), "--out", str(B / "out2"))[0] == 0
for table in ko_tables.TABLES:
    assert (B / "out1" / (table + ".json")).read_bytes() == (B / "out2" / (table + ".json")).read_bytes()
manifest = json.loads((B / "out1" / "manifest.json").read_text())
assert manifest["spawn_rows_used"] == 7 and manifest["tables"]["K_NPCPOS"]["rows"] == 9
export("missing", {"K_MONSTER": monsters, "K_NPC": npcs})
code, text = run("--export", str(B / "missing"), "--out", str(B / "out3"))
assert code == 2 and "REFUSED" in text and "K_NPCPOS.json is missing" in text, text
assert not (B / "out3").exists()
print("PASS reference tables: K_MONSTER, K_NPC and K_NPCPOS checked against the AI server's "
      "bindings (types, field widths, NULL only where declared, ASCII text, 29-byte names, "
      "unique sSid, spawn templates and path types), sorted by the full tuple with NULL first, "
      "named by a digest that row order, key order, layout and unbound columns leave alone")

# ---------------------------------------------------------------------------
# The operator's own export (never committed). Pinned: OpenKO v0.1.2
# (backup db11af06...8679) as tools/ko-reference/inspect_db.py exports it.
PINNED = {"K_MONSTER": "576fa0944adf750192af08e35166c0623df408eeb3ab55b7eacd549805ed2310",
          "K_NPC": "e293e09652303d49c7808824887248f56276bb5bd2f6140661a71e79fbc94c28",
          "K_NPCPOS": "d4487f5e905ec15ee6f2e5372c4110fc3aafcd9310b5002f181f0f4116d6278c"}
if not all((ko_tables.EXPORT / (t + ".json")).is_file() for t in ko_tables.TABLES):
    print("SKIP reference tables, operator export: %s lacks K_MONSTER, K_NPC or K_NPCPOS" % ko_tables.EXPORT)
else:
    real = {t: ko_tables.load(t) for t in ko_tables.TABLES}
    used = ko_tables.check_spawns(real["K_NPCPOS"], real["K_MONSTER"], real["K_NPC"])
    # Another row order and layout of the same export names the same rows.
    rows = json.loads((ko_tables.EXPORT / "K_NPCPOS.json").read_text())
    random.Random(1).shuffle(rows)
    assert ko_tables.load("K_NPCPOS", export("real", {"K_NPCPOS": rows}, indent=1))["digest"] == real["K_NPCPOS"]["digest"]
    if any(real[t]["digest"] != PINNED[t] for t in ko_tables.TABLES):
        print("SKIP reference tables, pinned counts: the export is not the pinned OpenKO v0.1.2 one "
              "(it imports: %d spawn rows used)" % used)
    else:
        spawns = ko_tables.rows_as_dicts(real["K_NPCPOS"])
        assert [len(real[t]["rows"]) for t in ko_tables.TABLES] == [723, 474, 1730] and used == 1537
        counts = {}
        for zone in (1, 2):
            rows = [s for s in spawns if s["ZoneID"] == zone]
            kept = [s for s in rows if not ko_tables.spawn_skipped(s)]
            counts[zone] = (len(rows), len(kept), len({s["NpcID"] for s in kept}), sum(s["NumNPC"] for s in kept))
        assert counts == {1: (354, 321, 108, 1238), 2: (355, 322, 108, 1233)}, counts
        print("PASS reference tables, operator export: the pinned OpenKO v0.1.2 rows import (723 "
              "monsters, 474 NPCs, 1,730 spawn rows, 1,537 used); zone 1 keeps 321 of 354 rows "
              "(108 templates, 1,238 NPCs) and zone 2 322 of 355 (108, 1,233) after the "
              "SpecialType 7 skip")

# PQ-422 (D-219): MAGIC_TYPE2, as the AI server binds (004107ab) and loads
# (0043b638) it: the numeric columns, HitRate / AddDamage / AddDamagePlus /
# AddRange narrowed to shorts, HitType and NeedArrow bytes. The binary keeps
# the first row of a duplicate iNum in storage order (0043ea73); the import,
# which does not keep the export's order, refuses a duplicate. Name and
# Description are bound but not checked (ignored).
def magic2(num, **kw):
    row = dict(iNum=num, Name="Sample", Description="?\x00", HitType=0, HitRate=100, AddDamage=100,
               AddRange=100, NeedArrow=1, AddDamagePlus=0)
    row.update(kw)
    return row


t2 = ko_tables.load("MAGIC_TYPE2", export("magic2", {"MAGIC_TYPE2": [magic2(208003), magic2(102003, AddDamagePlus=5)]}))
assert t2["columns"] == ["iNum", "HitType", "HitRate", "AddDamage", "AddDamagePlus", "AddRange", "NeedArrow"], t2
assert t2["rows"] == [[102003, 0, 100, 100, 5, 100, 1], [208003, 0, 100, 100, 0, 100, 1]], t2["rows"]
assert t2["ignored"] == ["Description", "Name"], t2["ignored"]
refused("empty", "MAGIC_TYPE2", [])
refused("two rows with iNum 102003", "MAGIC_TYPE2", [magic2(102003), magic2(102003, HitRate=50)])
refused("HitType 256 is outside", "MAGIC_TYPE2", [magic2(102003, HitType=256)])
refused("AddDamage 40000 is outside", "MAGIC_TYPE2", [magic2(102003, AddDamage=40000)])
refused("AddDamagePlus is NULL", "MAGIC_TYPE2", [{k: v for k, v in magic2(102003).items() if k != "AddDamagePlus"}])
refused("HitRate is not an integer", "MAGIC_TYPE2", [magic2(102003, HitRate="100")])
print("PASS MAGIC_TYPE2 import (PQ-422): 004107ab's numeric columns in their binary widths; a duplicate iNum (the "
      "binary keeps the first in storage order, 0043ea73), an empty table, a NULL and a non-integer value refused")
if not (ko_tables.EXPORT / "MAGIC_TYPE2.json").is_file():
    print("SKIP MAGIC_TYPE2, operator export: %s/MAGIC_TYPE2.json is missing" % ko_tables.EXPORT)
else:
    real2 = ko_tables.rows_as_dicts(ko_tables.load("MAGIC_TYPE2"))
    archery = [r for r in real2 if r["iNum"] % 1000 == 3 and r["iNum"] // 1000 in
               (101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 201, 202, 203, 204, 205, 206, 207, 208,
                209, 210, 211, 212)]
    print("PASS MAGIC_TYPE2, operator export: %d rows import; class archery rows %s: %s" % (
        len(real2), [r["iNum"] for r in archery],
        sorted({(r["HitType"], r["HitRate"], r["AddDamage"], r["AddDamagePlus"], r["AddRange"], r["NeedArrow"])
                for r in archery})))
