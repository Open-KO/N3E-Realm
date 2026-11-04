"""KO's character-create rules for the package (RQ-002, content/character-create.md).

The package source names them in `games/<game>/character-create.json`: the
races KO's create screen offers with each one's nation and specialties (1298
`006060f0`), the face and hair counts (1298 `00604f90`), the races the package
has a player model for (`content`), the stat tables a realm may validate
against (`tables`: each a KO `Data/NewChrValue.tbl` read from the chosen front
end's inputs, its row key and the text table its refusals are worded from), the
table each front end draws (Q97 (b)), the refusals' text rows (1298 `00600750`),
the name rule (Q99) and the fixed choice a create without a race takes (Q52).
The realm owner's `realm-config.json` may name, under `create`, another `table`
(Q97), the `races` offered (Q94, default `content`) and `reserved` words (Q99).

`plan` checks both files and resolves the choice before any KO file is read;
`build` reads the table and texts and returns the manifest's `create` section
(tools/assetc/create.py's form). This module knows KO's table layout only
through the package's `columns` and `key`; no race or specialty id is here.
"""
import hashlib
import pathlib

import create
import front_end_choice

SOURCE = "character-create.json"
KEYS = {"stats", "nation", "faces", "hairs", "races", "content", "tables", "columns",
        "front_ends", "refusals", "name", "fixed"}
RACE_KEYS = {"race", "nation", "specialties"}
TABLE_KEYS = {"values", "key", "texts"}
FIXED_KEYS = {"race", "specialty", "face", "hair", "points"}
# realm-config.json's `create`: the realm owner's choices (Q94, Q97, Q99).
CONFIG_KEYS = {"table", "races", "reserved"}


class Refused(front_end_choice.Refused):
    """A create choice the cook will not make, with the reason a realm owner reads."""


def ids(v, what, low=1, high=65535):
    if type(v) is not list or not v or any(type(x) is not int or not low <= x <= high for x in v) or \
            len(set(v)) != len(v):
        raise Refused("%s: distinct integers %d..%d" % (what, low, high))
    return v


def rules(game):
    """The package's character-create.json, checked, or None when it has none."""
    path = game / SOURCE
    if not path.exists():
        return None
    r = front_end_choice.read(path, "the package's create rules; content/character-create.md")
    if set(r) != KEYS:
        raise Refused("%s: needs exactly %s" % (path, ", ".join(sorted(KEYS))))
    stats = r["stats"]
    if type(stats) is not int or not 1 <= stats <= create.MAX_STATS:
        raise Refused("%s: stats 1..%d" % (path, create.MAX_STATS))
    races = r["races"]
    if type(races) is not list or not races:
        raise Refused("%s: races, a list" % path)
    for race in races:
        if type(race) is not dict or set(race) != RACE_KEYS:
            raise Refused("%s: each race needs exactly %s" % (path, ", ".join(sorted(RACE_KEYS))))
        ids([race["race"]], "%s race" % path)
        ids([race["nation"]], "%s race %r nation" % (path, race["race"]), high=255)
        ids(race["specialties"], "%s race %r specialties" % (path, race["race"]))
    known = [race["race"] for race in races]
    ids(known, "%s races" % path)
    if not set(ids(r["content"], "%s content" % path)) <= set(known):
        raise Refused("%s: content names a race it does not list" % path)
    tables = r["tables"]
    if type(tables) is not dict or not tables:
        raise Refused("%s: tables, by id" % path)
    for tid, t in tables.items():
        if not front_end_choice.CLIENT_ID.match(tid) or type(t) is not dict or set(t) != TABLE_KEYS:
            raise Refused("%s: table %r needs exactly %s" % (path, tid, ", ".join(sorted(TABLE_KEYS))))
        if type(t["values"]) is not str or type(t["texts"]) is not str or type(t["key"]) is not dict or \
                set(t["key"]) != {"race", "specialty"} or \
                any(type(v) is not int or not 0 <= v <= 1000000 for v in t["key"].values()) or t["key"]["race"] == 0:
            raise Refused("%s: table %r: values and texts paths and a key {race, specialty}" % (path, tid))
    columns = r["columns"]
    if type(columns) is not dict or set(columns) != {"stats", "bonus"} or type(columns["stats"]) is not list or \
            len(columns["stats"]) != stats or \
            any(type(c) is not int or not 1 <= c <= 63 for c in columns["stats"] + [columns["bonus"]]):
        raise Refused("%s: columns {stats: %d column numbers, bonus}" % (path, stats))
    front_ends = r["front_ends"]
    if type(front_ends) is not dict or any(v not in tables for v in front_ends.values()):
        raise Refused("%s: front_ends maps a client id to one of its tables" % path)
    if type(r["refusals"]) is not dict or set(r["refusals"]) != set(create.REFUSALS) or \
            any(type(v) is not int or v <= 0 for v in r["refusals"].values()):
        raise Refused("%s: refusals, a text row for each of %s" % (path, ", ".join(create.REFUSALS)))
    fixed = r["fixed"]
    if fixed is not None and (type(fixed) is not dict or set(fixed) != FIXED_KEYS or
                              type(fixed["points"]) is not list or len(fixed["points"]) != stats or
                              any(type(v) is not int or v < 0 for v in fixed["points"])):
        raise Refused("%s: fixed is null or exactly %s, with %d points" % (path, ", ".join(sorted(FIXED_KEYS)), stats))
    return r


def plan(game, client, config):
    """The create choice for front end `client` and realm-config.json's
    `config` ({} or its `create`), before any KO file is read: {rules, table
    (id), races (offered), reserved}, or None for a package without create
    rules. Refuses, naming the file to change, a malformed choice, a table the
    package lacks, a race without a player model and a fixed choice whose race
    is not offered."""
    game = pathlib.Path(game)
    path = game / front_end_choice.CONFIG
    r = rules(game)
    if r is None:
        if config:
            raise Refused("%s: create needs the package's %s" % (path, game / SOURCE))
        return None
    if type(config) is not dict or set(config) - CONFIG_KEYS:
        raise Refused("%s: create takes only %s" % (path, ", ".join(sorted(CONFIG_KEYS))))
    table = config.get("table", r["front_ends"].get(client))
    if table is None:
        raise Refused("%s: no create table for front end %r; name one under create.table (%s)"
                      % (game / SOURCE, client, ", ".join(sorted(r["tables"]))))
    if table not in r["tables"]:
        raise Refused("%s: create.table %r is not one of %s (%s)" % (path, table, ", ".join(sorted(r["tables"])), game / SOURCE))
    races = config.get("races", r["content"])
    try:
        ids(races, "create.races")
    except Refused as error:
        raise Refused("%s: %s" % (path, error))
    without = sorted(set(races) - set(r["content"]))
    if without:
        raise Refused("%s: create.races names race %s, which has no player model in the package (content, %s)"
                      % (path, ", ".join(map(str, without)), game / SOURCE))
    reserved = config.get("reserved", [])
    if type(reserved) is not list or len(reserved) > create.MAX_RESERVED or \
            not all(type(w) is str and create.WORD.match(w.lower()) for w in reserved):
        raise Refused("%s: create.reserved: up to %d printable ASCII words of 1 to %d bytes, no space"
                      % (path, create.MAX_RESERVED, create.MAX_WORD))
    if r["fixed"] is not None and r["fixed"]["race"] not in races:
        raise Refused("%s: the fixed choice's race %r is not offered (create.races)" % (path, r["fixed"]["race"]))
    return dict(rules=r, table=table, races=races, reserved=sorted({w.lower() for w in reserved}))


def build(chosen, assets):
    """The manifest's `create` section and its provenance, from `plan`'s choice
    and the front end's inputs (`ko_front_end.Inputs`). Refuses a table whose
    rows name a race or specialty the package lacks, or that lacks a row the
    package's offered races need (Q97)."""
    import ko_front_end
    import ko_tbl
    r, tid = chosen["rules"], chosen["table"]
    table = r["tables"][tid]
    data = assets.get(table["values"])
    _, rows = ko_tbl.parse(ko_tbl.decrypt(data))
    columns, key = r["columns"], table["key"]
    width = max(columns["stats"] + [columns["bonus"]]) + 1
    by_id = {}
    for row in rows:
        if len(row) < width or any(type(row[c]) is not int for c in [0] + columns["stats"] + [columns["bonus"]]):
            raise Refused("create table %s (%s): a row without the stat columns" % (tid, table["values"]))
        if row[0] in by_id:
            raise Refused("create table %s (%s): row %d twice" % (tid, table["values"], row[0]))
        by_id[row[0]] = row
    row_id = lambda race, specialty: race * key["race"] + specialty * key["specialty"]  # noqa: E731
    known = {row_id(race["race"], s) for race in r["races"] for s in race["specialties"]}
    extra = sorted(set(by_id) - known)
    if extra:
        raise Refused("create table %s (%s): rows %s name a race or specialty %s lacks"
                      % (tid, table["values"], ", ".join(map(str, extra)), SOURCE))
    races = []
    for race in r["races"]:
        if race["race"] not in chosen["races"]:
            continue
        specialties = []
        for s in race["specialties"]:
            row = by_id.get(row_id(race["race"], s))
            if row is None:
                raise Refused("create table %s (%s): no row %d for race %d specialty %d"
                              % (tid, table["values"], row_id(race["race"], s), race["race"], s))
            specialties.append(dict(specialty=s, bonus=row[columns["bonus"]], base=[row[c] for c in columns["stats"]]))
        races.append(dict(race=race["race"], nation=race["nation"], faces=r["faces"], hairs=r["hairs"],
                          specialties=specialties))
    refusals = {kind: ko_front_end.text_row(assets, {"table": table["texts"], "row": row}, "create refusal %s" % kind)
                for kind, row in r["refusals"].items()}
    section = dict(stats=r["stats"], nation=r["nation"], races=races, name=r["name"],
                   reserved=chosen["reserved"], refusals=refusals)
    fixed = r["fixed"]
    if fixed is not None:
        race = next(x for x in races if x["race"] == fixed["race"])
        specialty = next((s for s in race["specialties"] if s["specialty"] == fixed["specialty"]), None)
        if specialty is None:
            raise Refused("%s: the fixed specialty %r is not one race %d offers" % (SOURCE, fixed["specialty"], race["race"]))
        section["fixed"] = dict(race=fixed["race"], specialty=fixed["specialty"], face=fixed["face"], hair=fixed["hair"],
                                stats=[b + p for b, p in zip(specialty["base"], fixed["points"])])
    try:
        create.check(section)
    except ValueError as error:
        raise Refused("%s: %s" % (SOURCE, error))
    texts = assets.get(table["texts"])
    report = dict(table=tid, values=table["values"], values_sha256=hashlib.sha256(data).hexdigest(),
                  texts=table["texts"], texts_sha256=hashlib.sha256(texts).hexdigest(), races=chosen["races"])
    return section, report
