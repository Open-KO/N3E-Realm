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
                           (dict(refusals={"limit": 1}), "refusals"), (dict(extra=1), "needs exactly")]:
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
TYPES = [6, 7, 5, 5, 5, 5, 5, 5, 6]
TEXTS = ko_tbl.encrypt(ko_tbl.build(ko_front_end.TEXT_TYPES, [[n, "Row %d " % n] for n in rules["refusals"].values()]))


class Tree:
    def __init__(self, files):
        self.files = files

    def get(self, name):
        if name not in self.files:
            raise ValueError("missing %s" % name)
        return self.files[name]


def table(rows):
    return ko_tbl.encrypt(ko_tbl.build(TYPES, [[i, "x", *v, 0] for i, v in rows]))


BY_RACE = [(r["race"], [50 + r["race"], 50, 60, 70, 50, 10]) for r in rules["races"]]
BY_SPECIALTY = [(r["race"] * 10000 + s, [50, 50 + s % 100, 60, 70, 50, 10]) for r in rules["races"] for s in r["specialties"]]


def inputs(by_race, by_specialty):
    return ko_front_end.Inputs([Tree({"Data/NewChrValue.tbl": by_specialty, "Data/Texts_us.tbl": TEXTS}),
                                Tree({"Data/NewChrValue.tbl": by_race, "Data/Texts_us.tbl": TEXTS})],
                               [None, "installer-1264"])


good = inputs(table(BY_RACE), table(BY_SPECIALTY))
section, report = ko_create.build(plan, good)
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
for plan_, trees, expect in [
    (plan, inputs(table(BY_RACE + [(5, [1, 1, 1, 1, 1, 1])]), table(BY_SPECIALTY)), "rows 5 name a race"),
    (plan, inputs(table(BY_RACE[:1]), table(BY_SPECIALTY)), "no row 2 for race 2"),
    (dict(plan, table="1298"), inputs(table(BY_RACE), table([x for x in BY_SPECIALTY if x[0] != 20102])), "no row 20102"),
    (plan, inputs(table(BY_RACE + BY_RACE[:1]), table(BY_SPECIALTY)), "row 1 twice"),
    (plan, inputs(table([(2, [50, 50, 60, 70, 50, 1001])] + BY_RACE[2:]), table(BY_SPECIALTY)), "bonus"),
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
