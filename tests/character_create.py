"""RQ-002: the package's character-create rules (content/character-create.md,
"The realm's create").

- tools/assetc/create.py cooks the manifest's `create` section into create.bin
  in the layout server/src/create.rs reads (one synthetic rule set, the same
  digest on both sides), and refuses a malformed section and a fixed choice the
  rules refuse.
- tools/assetc/ko_create.py plans the Moradon choice from
  games/moradon/character-create.json and realm-config.json (Q94, Q97, Q99),
  refusing a malformed choice before any KO file is read, and builds the section
  from synthetic KO tables (keyed by race, and by race and specialty), refusing a
  table whose rows the package lacks or that lacks a row the package needs.
- RQ-159: ko_create.dress resolves each specialty's create dress from the
  chosen table's item columns through synthetic KO item tables as
  tools/assetc/ko_item_files.py names KO's files (a robe upper leaving the lower
  bare, the client's exemption, a plug's Item_Ext resource), refuses an item
  that does not resolve to an existing part or plug of its column, and leaves
  the section and the provenance as they were.
- A package carrying create.bin passes the client's asset check and the
  server's content check, which reads its rules; a create.bin with a bad magic
  or version, rehashed into the release, fails both.
"""
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools/assetc"))
import create  # noqa: E402
import front_end_choice  # noqa: E402
import ko_create  # noqa: E402
import ko_front_end  # noqa: E402
import ko_item_files  # noqa: E402
import ko_tbl  # noqa: E402
import main  # noqa: E402
from common import digest, string, u  # noqa: E402

# --- create.bin, against server/src/create.rs -----------------------------------
SECTION = dict(
    stats=3, nation=1,
    races=[dict(race=7, nation=1, faces=4, hairs=3, specialties=[dict(specialty=70, bonus=5, base=[40, 30, 20]),
                                                                 dict(specialty=71, bonus=5, base=[20, 30, 40])]),
           dict(race=8, nation=2, faces=2, hairs=1, specialties=[dict(specialty=80, bonus=0, base=[10, 10, 10])])],
    name=dict(min=1, max=20, punctuation="_:;"), reserved=["staff"],
    refusals=dict(limit="No more.", mismatch="", taken="Taken.", failed="", name="Bad name.", stats=""),
    fixed=dict(race=7, specialty=71, face=0, hair=0, stats=[20, 30, 45]))
# server/src/create.rs tests::SYNTHETIC_SHA256: the same rules, built by hand.
SYNTHETIC_SHA256 = "c86175f18617f5c22ca89196b05e3b1d6a1bab6e7c071f273028a4ea99907c00"
cooked = create.cook(SECTION)
assert digest(cooked).hex() == SYNTHETIC_SHA256, digest(cooked).hex()
assert create.cook({k: v for k, v in SECTION.items() if k != "fixed"})[-4:] == u(0)


def refused(section, expect):
    try:
        create.cook(section)
    except ValueError as error:
        assert expect in str(error), (expect, str(error))
        return
    raise AssertionError("cooked a malformed create section (%s)" % expect)


def changed(path, value):
    s = copy.deepcopy(SECTION)
    at = s
    for k in path[:-1]:
        at = at[k]
    at[path[-1]] = value
    return s


for path, value, expect in [
    (("stats",), 0, "stats"), (("stats",), 9, "stats"), (("nation",), 256, "nation"),
    (("races",), [], "races"), (("races", 1, "race"), 7, "race 7 twice"),
    (("races", 0, "faces"), 0, "faces"), (("races", 0, "specialties"), [], "specialties"),
    (("races", 0, "specialties", 1, "specialty"), 70, "specialty 70 twice"),
    (("races", 0, "specialties", 0, "base"), [1, 2], "3 base stats"),
    (("races", 0, "specialties", 0, "bonus"), 1001, "bonus"),
    (("name", "max"), 25, "name max"), (("name", "min"), 21, "name min"),
    (("name", "punctuation"), "_a", "punctuation"), (("name", "punctuation"), "_ ", "punctuation"),
    (("reserved",), ["Staff"], "reserved"), (("reserved",), ["a b"], "reserved"),
    (("refusals", "limit"), "x" * 201, "refusal limit"), (("refusals", "name"), "café", "refusal name"),
    (("fixed", "stats"), [19, 30, 46], "fixed choice"), (("fixed", "stats"), [20, 30, 44], "fixed choice"),
    (("fixed", "race"), 8, "fixed choice"), (("fixed", "specialty"), 70, "fixed choice"),
    (("fixed", "face"), 4, "fixed choice"),
]:
    refused(changed(path, value), expect)
refused({k: v for k, v in SECTION.items() if k != "refusals"}, "create fields")
print("PASS create.bin: the server's layout (%d bytes), malformed sections refused" % len(cooked))

# --- the Moradon plan ------------------------------------------------------------
MORADON = pathlib.Path("games/moradon")
rules = ko_create.rules(MORADON)
plan = ko_create.plan(MORADON, "1097", {})
assert (plan["table"], plan["races"], plan["reserved"]) == ("1264", rules["content"], []), plan
assert ko_create.plan(MORADON, "1298", {})["table"] == "1298"
assert ko_create.plan(MORADON, "1097", {"table": "1298", "reserved": ["GM", "gm", "Staff"]})["reserved"] == ["gm", "staff"]
# RQ-158 (Q105): the package ships the create model of the Karus races that
# convert on the front-end path; create offers only content, the Tuarek.
assert (rules["models"], rules["content"]) == ({"create": [2, 3, 4]}, [2]), rules
# The races the screen offers per nation (1298 006060f0), every one in a table.
assert {r["race"]: r["specialties"] for r in rules["races"]} == {
    1: [101], 2: [102, 104], 3: [103], 4: [104], 11: [201], 12: [201, 202, 203, 204], 13: [201, 202, 203, 204]}


def plan_refused(expect, client="1097", config=None, game=MORADON):
    try:
        ko_create.plan(game, client, {} if config is None else config)
    except front_end_choice.Refused as error:
        assert expect in str(error), (expect, str(error))
        return
    raise AssertionError("planned (%s)" % expect)


plan_refused("create takes only", config={"tabel": "1264"})
plan_refused("create.table 'x' is not one of 1264, 1298", config={"table": "x"})
plan_refused("no create table for front end '2145'", client="2145")
plan_refused("has no player model", config={"races": [2, 12]})
plan_refused("create.races", config={"races": []})
plan_refused("create.reserved", config={"reserved": ["two words"]})
with tempfile.TemporaryDirectory(prefix="n3e-create-") as td:
    game = pathlib.Path(td)
    assert ko_create.plan(game, "1097", {}) is None
    plan_refused("create needs the package's", config={"races": [2]}, game=game)
    for change, expect in [(dict(content=[5]), "content names a race"), (dict(fixed=dict(rules["fixed"], race=1)), "fixed choice's race 1"),
                           (dict(columns={"stats": [2], "bonus": 7}), "columns"), (dict(front_ends={"1097": "x"}), "front_ends"),
                           (dict(refusals={"limit": 1}), "refusals"), (dict(extra=1), "needs exactly"),
                           (dict(player=1), "player names a race without a player model"),
                           (dict(player=True), "player names a race"),
                           (dict(races=[dict(r, looks="UPC_KA") for r in rules["races"]]), "race 1 looks"),
                           (dict(races=[{k: v for k, v in r.items() if k != "looks"} for r in rules["races"]]),
                            "each race needs exactly"),
                           # RQ-158: the races whose create model ships, every race in content among them.
                           (dict(models={}), "models needs exactly create"),
                           (dict(models={"create": [2], "world": [2]}), "models needs exactly create"),
                           (dict(models={"create": []}), "models.create"),
                           (dict(models={"create": [2, 5]}), "models.create names a race it does not list"),
                           (dict(models={"create": [3]}), "content names a race without a create model"),
                           # RQ-159: the item columns and each table's dress.
                           (dict(columns={"stats": [2, 3, 4, 5, 6], "bonus": 7}), "columns"),
                           (dict(columns=dict(rules["columns"], plugs=[])), "columns"),
                           (dict(columns=dict(rules["columns"], plugs=[8, 7])), "names a column twice"),
                           (dict(tables=dict(rules["tables"], x=dict(rules["tables"]["1298"], dress={}))), "dress is null"),
                           (dict(tables=dict(rules["tables"], x=dict(rules["tables"]["1298"], dress=dict(
                               rules["tables"]["1298"]["dress"], extensions="Data/Item_Ext.tbl")))), "dress is null"),
                           (dict(tables=dict(rules["tables"], x=dict(rules["tables"]["1298"], dress=dict(
                               rules["tables"]["1298"]["dress"], extensions="installer-1264:Data/Item_Ext_{}_us.tbl")))),
                            "dress is null"),
                           (dict(tables=dict(rules["tables"], x={k: v for k, v in rules["tables"]["1298"].items()
                                                                 if k != "dress"})), "table 'x' needs exactly")]:
        (game / ko_create.SOURCE).write_text(json.dumps({**rules, **change}))
        plan_refused(expect, game=game)
    # realm-config.json's `create` reaches the plan through the front-end choice.
    (game / ko_create.SOURCE).write_text(json.dumps(rules))
    (game / front_end_choice.CATALOGUE).write_text(json.dumps(
        {"1097": {"recipe": "front-end.json", "inputs": [{"tree": "trees/a", "get": "make a-tree"}]}}))
    (game / "front-end.json").write_text("{}")
    (game / "trees/a").mkdir(parents=True)
    (game / front_end_choice.CONFIG).write_text(json.dumps({"front_end": "1097", "create": {"table": "1298"}}))
    assert front_end_choice.choose(game, game)["create"]["table"] == "1298"
    (game / front_end_choice.CONFIG).write_text(json.dumps({"front_end": "1097", "create": {"races": [3]}}))
    try:
        front_end_choice.choose(game, game)
        raise AssertionError("chose a race without a player model")
    except front_end_choice.Refused as error:
        assert "has no player model" in str(error), str(error)
print("PASS create plan: Moradon validates against 1264's table for the 1097 choice; malformed choices refused")

# --- building the section from synthetic KO tables -------------------------------
# NewChrValue: id, name, five stats, bonus, then 12 item ids (KO's 1264 and 1298 layout).
TYPES = [6, 7, 5, 5, 5, 5, 5, 5] + [6] * 12
TEXTS = ko_tbl.encrypt(ko_tbl.build(ko_front_end.TEXT_TYPES, [[n, "Row %d " % n] for n in rules["refusals"].values()]))
# Synthetic KO item tables (original numbers, KO's column layout): Item_Org's
# number, extension table, two names, five fields, resource (column 7) ...
# class, robe and attach (11-13) ... and +0x54 (22); Item_Ext's number, name,
# base, remark, a field and resource (column 6).
ORG_TYPES = [6, 2, 7, 7, 6, 2, 6, 6, 6, 6, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 5, 5]
EXT_TYPES = [6, 7, 6, 7, 6, 6]


def org(number, ext, resource, kind, robe, attach, sale=0):
    return [number, ext, "x", "", 0, 0, resource, resource, 0, 0, kind, robe, attach, 0, 0, 0, 0, 0, 0, 0, 0, sale]


UPPER, LOWER, HANDS, FEET, ROBE = 300001000, 300002000, 300004000, 300005000, 310001000
WEAPON, SHIELD = 100110050, 100260020
ORGS = [org(UPPER, 0, 30000100, 210, 0, 5), org(LOWER, 0, 30000200, 210, 0, 6), org(HANDS, 0, 30000400, 210, 0, 8),
        org(FEET, 0, 30000500, 210, 0, 9), org(ROBE, 0, 31000100, 230, 1, 5), org(310002000, 0, 31000200, 230, 0, 6),
        org(100110000, 1, 10011000, 11, 0, 1), org(100260000, 1, 10026000, 60, 0, 2),
        org(500001000, 0, 50000100, 0, 0, 20), org(300007000, 0, 0, 210, 0, 8), org(100120000, 1, 10012000, 11, 0, 1),
        org(100130000, 24, 10013000, 11, 0, 1), org(300008000, 24, 30000400, 210, 0, 8)]
EXTS = {0: [], 1: [[50, "", 0, "", 0, 0], [20, "", 0, "", 0, 10027000]]}


def item_files(prefix, races):
    """The files KO names for the synthetic items worn by `races`."""
    files = {"Item/1_0011_00_0.n3cplug", "Item/1_0027_00_0.n3cplug"}
    for race in races:
        files |= {"Item/3_%04d_%d0_0.n3cpart" % (race, n) for n in (1, 2, 4, 5)}
        files |= {"Item/3_1%03d_%d0_0.n3cpart" % (race, n) for n in (1, 4, 5)}
    return {f: b"" for f in files}


class Tree:
    def __init__(self, files):
        self.files = files

    def get(self, name):
        if name not in self.files:
            raise ValueError("missing %s" % name)
        return self.files[name]

    def has(self, name):
        return name in self.files


def table(rows):
    return ko_tbl.encrypt(ko_tbl.build(TYPES, [[i, "x", *v, *(items if items is not None else DRESS)]
                                               for i, v, items in rows]))


def items(upper=UPPER, lower=LOWER, right=WEAPON, left=0, hands=HANDS):
    return [right, left, upper, lower, 0, hands, FEET, 0, 0, 0, 0, 0]


DRESS = items()
# The Wrinkle Tuarek (3) in a robe, the Puri Tuarek (4) with a shield.
WORN = {3: items(upper=ROBE, lower=310002000), 4: items(left=SHIELD)}
BY_RACE = [(r["race"], [50 + r["race"], 50, 60, 70, 50, 10], WORN.get(r["race"])) for r in rules["races"]]
BY_SPECIALTY = [(r["race"] * 10000 + s, [50, 50 + s % 100, 60, 70, 50, 10], WORN.get(r["race"]))
                for r in rules["races"] for s in r["specialties"]]
ITEM_TABLES = {"Data/Item_Org_us.tbl": ko_tbl.encrypt(ko_tbl.build(ORG_TYPES, ORGS))}
ITEM_TABLES.update({"Data/Item_Ext_%d_us.tbl" % i: ko_tbl.encrypt(ko_tbl.build(EXT_TYPES, rows)) for i, rows in EXTS.items()})
RACES = [r["race"] for r in rules["races"]]


def inputs(by_race, by_specialty, orgs=None, files=None):
    tables = ITEM_TABLES if orgs is None else dict(ITEM_TABLES, **{"Data/Item_Org_us.tbl": orgs})
    worn = item_files("", RACES) if files is None else files
    return ko_front_end.Inputs([Tree({"Data/NewChrValue.tbl": by_specialty, "Data/Texts_us.tbl": TEXTS, **tables, **worn}),
                                Tree({"Data/NewChrValue.tbl": by_race, "Data/Texts_us.tbl": TEXTS, **tables, **worn})],
                               [None, "installer-1264"])


good = inputs(table(BY_RACE), table(BY_SPECIALTY))
section, report = ko_create.build(plan, good)
# RQ-159: the dress is checked, not cooked: the section and provenance keep their fields.
assert set(report) == {"table", "values", "values_sha256", "texts", "texts_sha256", "races"}, report
assert set(section) == create.KEYS | {"fixed"}, section
assert section["races"] == [dict(race=2, nation=1, faces=4, hairs=3, specialties=[
    dict(specialty=102, bonus=10, base=[52, 50, 60, 70, 50]), dict(specialty=104, bonus=10, base=[52, 50, 60, 70, 50])])], section
assert section["fixed"] == dict(race=2, specialty=104, face=0, hair=0, stats=[52, 50, 60, 70, 60]), section["fixed"]
assert section["refusals"]["taken"] == "Row 1912 " and section["name"] == rules["name"], section
assert report["table"] == "1264" and report["values"] == "installer-1264:Data/NewChrValue.tbl", report
everyone = dict(plan, table="1298", races=[r["race"] for r in rules["races"]], rules=dict(rules, content=[r["race"] for r in rules["races"]]))
section, _ = ko_create.build(everyone, good)
assert [(r["race"], [s["specialty"] for s in r["specialties"]]) for r in section["races"]] == \
    [(r["race"], r["specialties"]) for r in rules["races"]], section["races"]
assert section["races"][-1]["specialties"][-1]["base"] == [50, 54, 60, 70, 50]
create.cook(section)

# --- RQ-159: each specialty's create dress ------------------------------------------
worn = ko_create.dress(plan, good)
# 1264's table keyed by race: race 2's one set for both its specialties, from the
# installer's input; the offered race and the races with a create model.
assert sorted(worn) == [2, 3, 4] and worn[2][102] == worn[2][104], worn
assert worn[2][104] == dict(
    parts=[dict(slot=0, item=UPPER, file="installer-1264:Item/3_0002_10_0.n3cpart"),
           dict(slot=1, item=LOWER, file="installer-1264:Item/3_0002_20_0.n3cpart"),
           dict(slot=3, item=HANDS, file="installer-1264:Item/3_0002_40_0.n3cpart"),
           dict(slot=4, item=FEET, file="installer-1264:Item/3_0002_50_0.n3cpart")],
    plugs=[dict(slot=0, item=WEAPON, kind=11, file="installer-1264:Item/1_0011_00_0.n3cplug")]), worn[2]
# A robe upper leaves the lower bare (00467d50); the left plug takes its Item_Ext resource.
assert worn[3][103]["parts"][:2] == [dict(slot=0, item=ROBE, file="installer-1264:Item/3_1003_10_0.n3cpart"),
                                      dict(slot=1, item=310002000, file=None)], worn[3]
assert worn[4][104]["plugs"][1] == dict(slot=1, item=SHIELD, kind=60, file="installer-1264:Item/1_0027_00_0.n3cplug")
# 1298's table by race and specialty, from the first input, for every race asked.
by_class = ko_create.dress(dict(plan, table="1298"), good, races=RACES)
assert sorted(by_class) == RACES and by_class[12][203]["parts"][0]["file"] == "Item/3_0012_10_0.n3cpart", by_class
# The client's robe exemption (nation, number / 10^6) draws the lower.
exempt = dict(plan, rules=dict(rules, tables=dict(rules["tables"], **{"1264": dict(rules["tables"]["1264"], dress=dict(
    rules["tables"]["1264"]["dress"], robe_exempt=[[1, 310]]))})))
lower = ko_create.dress(exempt, inputs(table(BY_RACE), table(BY_SPECIALTY),
                                       files={**item_files("", RACES), "Item/3_1003_20_0.n3cpart": b""}))[3][103]["parts"][1]
assert lower == dict(slot=1, item=310002000, file="installer-1264:Item/3_1003_20_0.n3cpart"), lower
# A table without item columns (1097's) has no dress: KO draws the looks parts.
bare = dict(plan, rules=dict(rules, tables=dict(rules["tables"], **{"1264": dict(rules["tables"]["1264"], dress=None)})))
assert ko_create.dress(bare, good) is None
narrow = ko_tbl.encrypt(ko_tbl.build(TYPES[:8], [[i, "x", *v] for i, v, _ in BY_RACE]))
assert ko_create.build(bare, inputs(narrow, table(BY_SPECIALTY)))[0] == ko_create.build(plan, good)[0]


def dress_refused(expect, rows=None, orgs=None, files=None, chosen=plan):
    trees = inputs(table(rows if rows is not None else BY_RACE), table(BY_SPECIALTY),
                   orgs=None if orgs is None else ko_tbl.encrypt(ko_tbl.build(ORG_TYPES, orgs)), files=files)
    for call in (lambda: ko_create.dress(chosen, trees), lambda: ko_create.build(chosen, trees)):
        try:
            call()
        except front_end_choice.Refused as error:
            assert expect in str(error), (expect, str(error))
            continue
        raise AssertionError("dressed (%s)" % expect)


def tuarek(**worn):
    return [(i, v, items(**worn) if i == 2 else w) for i, v, w in BY_RACE]


dress_refused("item 999001000 has no row 999001000", rows=tuarek(upper=999001000))
dress_refused("item %d is plug 0, not part 0" % WEAPON, rows=tuarek(upper=WEAPON))
dress_refused("item %d is part 1, not part 0" % LOWER, rows=tuarek(upper=LOWER))
dress_refused("item %d is part 0, not plug 0" % UPPER, rows=tuarek(right=UPPER))
dress_refused("item 500001000 is an icon, not part 3", rows=tuarek(hands=500001000))
dress_refused("item 300007000 names no file", rows=tuarek(hands=300007000))
dress_refused("item 100120030 names no file", rows=tuarek(right=100120030))  # Item_Ext_1 has no row 30
# An Item_Ext table past KO's 24 is refused by name, for a plug and a part:
# the name function indexes the tables with it unbounded (006157b0, 005d2a80).
dress_refused("item 100130050 names Item_Ext table 24: KO has tables 0..23", rows=tuarek(right=100130050))
dress_refused("item 300008000 names Item_Ext table 24: KO has tables 0..23", files={
    **item_files("", RACES), "Item/3_0002_80_0.n3cpart": b""}, rows=tuarek(hands=300008000))
dress_refused("3_0002_10_0.n3cpart is not in the input",
              files={k: v for k, v in item_files("", RACES).items() if k != "Item/3_0002_10_0.n3cpart"})
dress_refused("row 300001000 twice", orgs=ORGS + ORGS[:1])
dress_refused("a row without the stat and item columns",
              rows=None, chosen=dict(plan, rules=dict(rules, columns=dict(rules["columns"], parts=[10, 11, None, 13, 14, 15, 16, 17, 18, 20]))))
# The client's switch: a part for a race and class it does not accept names a
# stack address; a class of 11 or less names nothing (006157b0).
part = org(UPPER, 0, 30000100, 210, 0, 5)
assert ko_item_files.name(part, None, 2, 104) == "Item/3_0002_10_0.n3cpart"
assert ko_item_files.name(part, None, 2, 11) == "" and ko_item_files.name(part, None, 20, 104) == ""
assert ko_item_files.name(org(377771000, 0, 1, 210, 0, 5), None, 13, 201) == "Item/77_3_7713_10_0.n3cpart"
assert ko_item_files.name(org(377771000, 0, 1, 210, 0, 5, sale=2), None, 13, 201) == "Item/3_7713_10_0.n3cpart"
for race, specialty in ((2, 101), (5, 104), (1, 102)):
    try:
        ko_item_files.name(part, None, race, specialty)
        raise AssertionError("named race %d class %d" % (race, specialty))
    except ValueError as error:
        assert "stack address" in str(error), str(error)
print("PASS create dress: KO's item columns resolved through the item tables to existing parts and plugs")

for plan_, trees, expect in [
    (plan, inputs(table(BY_RACE + [(5, [1, 1, 1, 1, 1, 1], None)]), table(BY_SPECIALTY)), "rows 5 name a race"),
    (plan, inputs(table(BY_RACE[:1]), table(BY_SPECIALTY)), "no row 2 for race 2"),
    (dict(plan, table="1298"), inputs(table(BY_RACE), table([x for x in BY_SPECIALTY if x[0] != 20102])), "no row 20102"),
    (plan, inputs(table(BY_RACE + BY_RACE[:1]), table(BY_SPECIALTY)), "row 1 twice"),
    (plan, inputs(table([(2, [50, 50, 60, 70, 50, 1001], None)] + BY_RACE[2:]), table(BY_SPECIALTY)), "bonus"),
]:
    try:
        ko_create.build(plan_, trees)
        raise AssertionError("built (%s)" % expect)
    except ValueError as error:
        assert expect in str(error), (expect, str(error))
print("PASS create build: KO's tables by race and by race and specialty, the refusals' rows")

# --- a package with create.bin through both readers ------------------------------
with tempfile.TemporaryDirectory(dir="build", prefix="character-create-") as td:
    root, out = pathlib.Path(td) / "source", pathlib.Path(td) / "package"
    shutil.copytree("tests/fixtures/legacy-demo", root)
    m = json.loads((root / "package.json").read_text())
    m["create"] = SECTION
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    assert (out / "create.bin").read_bytes() == cooked

    def check(good):
        results = [subprocess.run(c, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
                   for c in (["build/client/n3e-asset-check", str(out)], ["target/debug/n3e-server", "--check-content"])]
        for r in results:
            assert (r.returncode == 0) == good, (r.stdout, r.stderr)
        return results[1].stdout

    assert "create races=2 specialties=3 stats=3 nation=1 fixed=true" in check(True).splitlines()
    files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}

    def repack(data):
        changed = {**files, "create.bin": data}
        index = b"N3R1" + u(1) + u(m["engine_version"]) + u(m["protocol_version"]) + string(m["game_id"]) + \
            string(m["package_version"]) + u(len(changed))
        for name, body in sorted(changed.items()):
            (out / name).write_bytes(body)
            index += string(name) + u(len(body)) + digest(body)
        (out / "release.bin").write_bytes(index)

    for bad in (b"N3CX" + cooked[4:], cooked[:4] + u(2) + cooked[8:]):
        repack(bad)
        check(False)
    repack(cooked)
    check(True)
print("PASS create.bin through the client's asset check and the server's content check")
